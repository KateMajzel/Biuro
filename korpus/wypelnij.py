#!/usr/bin/env python3
"""Szybkie wypełnianie ground truth — klawiszami zamiast przepisywania.

    python korpus/wypelnij.py --csv korpus/out/szkielet.csv \
        --zrodlo korpus/out/poczta_prawdziwa.jsonl --przebieg 1
    python korpus/wypelnij.py --csv korpus/out/szkielet.csv --przebieg 2
    python korpus/wypelnij.py --csv korpus/out/szkielet.csv --przebieg 3
    python korpus/wypelnij.py --csv korpus/out/szkielet.csv --stan

Po co: wąskim gardłem pomiaru jest przepisywanie czterdziestu wierszy w arkuszu.
To narzędzie nie zmienia tego, CO wpisujesz — zmienia tylko liczbę uderzeń
w klawiaturę. Zamiast wpisywać `pytanie_przedsprzedazowe` wybierasz numer
z listy zamkniętej.

**Czego to narzędzie nie robi: nie proponuje odpowiedzi.** Nie ma domyślnej
intencji, domyślnej flagi ani podpowiedzi „pewnie to". Enter zawsze znaczy
„pomiń", nigdy „zgadzam się z sugestią". Gdyby podpowiadało, ground truth
byłoby odpowiedzią systemu na własne pytanie, a pomiar mierzyłby zgodność
z samym sobą.

Trzy przebiegi, w tej kolejności — tak jest najszybciej:

  1. intencja, flaga do człowieka, liczba pytań  (po temacie i pierwszym akapicie)
  2. pola wymagające czytania treści
  3. pola-pułapki, z listy kandydatów

Zapis po KAŻDYM wierszu. Można wyjść w dowolnym momencie przez Ctrl+C
i wrócić później — narzędzie pominie to, co już wypełnione.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KORZEN))

from biuro.pii import zamaskuj  # noqa: E402

PROMPT_KLASYFIKACJI = KORZEN / "prompty" / "klasyfikacja.md"
ETYKIETY = Path(__file__).resolve().parent / "schemat" / "etykiety.json"


def warunki_flagi() -> list[str]:
    """Czyta listę zamkniętą z promptu produkcyjnego — jedno źródło prawdy.

    Gdyby lista była tu zapisana osobno, rozjechałaby się z promptem przy
    pierwszej poprawce, a wtedy ground truth i klasyfikator mówiłyby
    o różnych warunkach.
    """
    if not PROMPT_KLASYFIKACJI.exists():
        print(f"BŁĄD: brak {PROMPT_KLASYFIKACJI}", file=sys.stderr)
        return []
    tekst = PROMPT_KLASYFIKACJI.read_text(encoding="utf-8")
    return re.findall(r"^\d+\.\s+`([a-z_]+)`", tekst, flags=re.MULTILINE)


def etykiety_po_trasie() -> dict[str, list[str]]:
    dane = json.loads(ETYKIETY.read_text(encoding="utf-8"))
    mapa = dane["szczegolowe_na_zgrubne"]
    # Nazwy typów produkcyjnych muszą być w szczegolowe_na_zgrubne, bo ocen.py
    # po nich mapuje wyjście klasyfikatora na trasę. Ale do ground truth nie
    # wolno ich dopuścić: gdyby dało się oznaczyć wiersz gold nazwą
    # `formularz` zamiast `zgloszenie_nowe`, metryka etykiety szczegółowej
    # porównywałaby dwa różne słowniki.
    produkcyjne = set(dane.get("_tylko_produkcyjne", []))
    po_trasie: dict[str, list[str]] = {t: [] for t in dane["zgrubne"]}
    for etykieta, trasa in mapa.items():
        if etykieta.startswith("_") or etykieta in produkcyjne:
            continue
        if trasa in po_trasie:
            po_trasie[trasa].append(etykieta)
    return {t: sorted(e) for t, e in po_trasie.items() if e}


def wczytaj_tresci(sciezka: Path | None) -> dict[str, dict]:
    if sciezka is None or not sciezka.exists():
        return {}
    rekordy = {}
    for linia in sciezka.read_text(encoding="utf-8").splitlines():
        if not linia.strip():
            continue
        rekord = json.loads(linia)
        rekordy[str(rekord.get("id", ""))] = rekord
    return rekordy


def pokaz_wiadomosc(wiersz: dict, tresci: dict[str, dict], ile_linii: int) -> None:
    ident = wiersz["id"]
    print("\n" + "=" * 72)
    print(f"{ident}   {wiersz.get('temat', '')[:60]}")
    print("=" * 72)

    rekord = tresci.get(ident, {})
    tresc = rekord.get("tresc") or ""
    if tresc:
        for linia in zamaskuj(tresc, daty=False).splitlines()[:ile_linii]:
            print(f"  | {linia[:98]}")
        pozostalo = max(0, len(zamaskuj(tresc, daty=False).splitlines()) - ile_linii)
        if pozostalo:
            print(f"  | ... (jeszcze {pozostalo} linii, --linie zwiększa)")
    else:
        print("  (treść niedostępna — podaj --zrodlo, żeby ją widzieć)")

    if wiersz.get("_z_regexu"):
        print(f"\n  regex ustalił: {wiersz['_z_regexu']}")
    if wiersz.get("_ostrzezenia"):
        print(f"  ostrzeżenia:   {wiersz['_ostrzezenia']}")


def pytaj_wybor(etykieta: str, opcje: list[str], obecna: str = "") -> str | None:
    """Zwraca wybraną wartość, "" dla pominięcia, None dla przerwania."""
    print(f"\n  {etykieta}" + (f"  [teraz: {obecna}]" if obecna else ""))
    szerokosc = max((len(o) for o in opcje), default=10) + 2
    for nr, opcja in enumerate(opcje, start=1):
        koniec = "\n" if nr % 3 == 0 else ""
        print(f"    {nr:2d}) {opcja:<{szerokosc}}", end=koniec)
    if len(opcje) % 3:
        print()
    while True:
        odp = input("  numer (Enter = pomiń, q = koniec): ").strip().lower()
        if odp == "q":
            return None
        if not odp:
            return ""
        if odp.isdigit() and 1 <= int(odp) <= len(opcje):
            return opcje[int(odp) - 1]
        print("  nie ma takiego numeru")


def pytaj_tekst(etykieta: str, obecna: str = "") -> str | None:
    print(f"  {etykieta}" + (f"  [teraz: {obecna}]" if obecna else ""))
    odp = input("  wartość (Enter = pomiń, q = koniec): ").strip()
    if odp.lower() == "q":
        return None
    return odp


def wyglada_na_polecenie(odp: str) -> bool:
    """Czy to wklejone polecenie powłoki, a nie odpowiedź na pytanie."""
    poszlaki = ("select-string", "get-child", "copy-item", "python ", "cd ",
                "-path", "-pattern", "-filter", "\\", "|")
    return len(odp) > 12 and any(p in odp.lower() for p in poszlaki)


def pytaj_z_walidacja(pytanie: str, poprawna, podpowiedz: str) -> str | None:
    """Pyta, dopóki odpowiedź nie jest poprawna.

    Zwraca wartość, "" dla Enter (pomiń wiersz), None dla q (koniec).

    Po co walidacja. Wcześniej błędna odpowiedź była po cichu ignorowana:
    narzędzie przechodziło do następnego pytania, kolumna zostawała pusta
    i nie było po tym żadnego śladu. Raz skończyło się to przebiegiem,
    w którym po dwudziestu czterech minutach pracy plik był pusty.
    Milczące odrzucenie odpowiedzi jest gorsze niż brak odpowiedzi.
    """
    while True:
        odp = input(pytanie).strip().lower()
        if odp == "q":
            return None
        if not odp:
            return ""
        if poprawna(odp):
            return odp
        if wyglada_na_polecenie(odp):
            print("    To wygląda na polecenie PowerShella wklejone w pytanie.")
            print("    Narzędzie czeka na odpowiedź; polecenia wklejaj po `q`.")
        else:
            skrot = odp[:40] + ("…" if len(odp) > 40 else "")
            print(f"    Nie rozumiem: {skrot}")
        print(f"    {podpowiedz}")


def zapisz(sciezka: Path, wiersze: list[dict], kolumny: list[str]) -> None:
    with sciezka.open("w", encoding="utf-8-sig", newline="") as fh:
        zapis = csv.DictWriter(fh, fieldnames=kolumny)
        zapis.writeheader()
        zapis.writerows(wiersze)


def stan(wiersze: list[dict]) -> None:
    razem = len(wiersze)
    z_intencja = sum(1 for w in wiersze if w.get("intencja"))
    z_flaga = sum(1 for w in wiersze if str(w.get("do_czlowieka", "")).strip())
    z_pytaniami = sum(1 for w in wiersze if str(w.get("pytania_liczba", "")).strip())
    flagowane = sum(1 for w in wiersze if str(w.get("do_czlowieka", "")).lower()
                    in ("1", "true", "tak", "t", "y"))
    z_pustymi = sum(1 for w in wiersze if w.get("pola_puste"))

    print(f"\nWiersze: {razem}")
    print(f"  intencja wypełniona:        {z_intencja:3d} / {razem}")
    print(f"  flaga do człowieka:         {z_flaga:3d} / {razem}   (z tego TAK: {flagowane})")
    print(f"  liczba pytań:               {z_pytaniami:3d} / {razem}")
    print(f"  pola-pułapki wpisane:       {z_pustymi:3d} / {razem}")
    print("\nPrzebieg 1 kończysz, gdy trzy pierwsze są pełne. To daje dwie z czterech")
    print("metryk na pełnej próbie — trasę i flagę do człowieka.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="plik szkieletu z szkielet_gold.py")
    parser.add_argument("--zrodlo", help="JSONL z treściami wiadomości")
    parser.add_argument("--przebieg", type=int, choices=[1, 2, 3], default=1)
    parser.add_argument("--stan", action="store_true", help="pokaż postęp i zakończ")
    parser.add_argument("--linie", type=int, default=14, help="ile linii treści pokazywać")
    parser.add_argument("--od", help="zacznij od tego id")
    parser.add_argument("--wszystkie", action="store_true",
                        help="pokaż też wiersze już wypełnione")
    args = parser.parse_args()

    plik = Path(args.csv)
    if not plik.exists():
        print(f"Brak {plik}. Najpierw:")
        print("  python korpus/src/szkielet_gold.py --zrodlo <poczta>.jsonl "
              "--wyjscie korpus/out/szkielet")
        return 1

    with plik.open(encoding="utf-8-sig", newline="") as fh:
        czytnik = csv.DictReader(fh)
        kolumny = list(czytnik.fieldnames or [])
        wiersze = [dict(w) for w in czytnik]

    if args.stan:
        stan(wiersze)
        return 0

    tresci = wczytaj_tresci(Path(args.zrodlo) if args.zrodlo else None)
    warunki = warunki_flagi()
    po_trasie = etykiety_po_trasie()
    plaskie_etykiety = [e for lista in po_trasie.values() for e in lista]

    kolumny_pol = [
        k for k in kolumny
        if "." in k or k.startswith("uczestnicy") or k.startswith("pasazerowie")
    ]

    print(f"Przebieg {args.przebieg}. Enter pomija, q kończy i zapisuje.")
    if args.przebieg == 1:
        print("Idź po temacie i pierwszym akapicie. Nie czytaj całości — to przebieg 2.")

    zaczac = args.od is None
    zrobione = 0

    try:
        for wiersz in wiersze:
            if not zaczac:
                if wiersz["id"] == args.od:
                    zaczac = True
                else:
                    continue

            if args.przebieg == 1 and not args.wszystkie and wiersz.get("intencja"):
                continue
            if args.przebieg == 3 and not args.wszystkie and wiersz.get("pola_puste"):
                continue

            pokaz_wiadomosc(wiersz, tresci, args.linie)

            if args.przebieg == 1:
                print("\n  --- intencja ---")
                for trasa, etykiety in po_trasie.items():
                    numery = [plaskie_etykiety.index(e) + 1 for e in etykiety]
                    pary = ", ".join(f"{n}={e}" for n, e in zip(numery, etykiety))
                    print(f"  {trasa:16s} {pary}")
                ile = len(plaskie_etykiety)
                odp = pytaj_z_walidacja(
                    "\n  numer intencji (Enter = pomiń, q = koniec): ",
                    lambda o: o.isdigit() and 1 <= int(o) <= ile,
                    f"Podaj liczbę od 1 do {ile} z listy powyżej.",
                )
                if odp is None:
                    break
                if odp:
                    wiersz["intencja"] = plaskie_etykiety[int(odp) - 1]

                flaga = pytaj_z_walidacja(
                    "  do człowieka? t/n (Enter = pomiń, q = koniec): ",
                    lambda o: o in ("t", "tak", "y", "1", "n", "nie", "0"),
                    "Wpisz t albo n.",
                )
                if flaga is None:
                    break
                if flaga in ("t", "tak", "y", "1"):
                    wiersz["do_czlowieka"] = "tak"
                    wybor = pytaj_wybor("warunek z listy zamkniętej", warunki,
                                        wiersz.get("powod_do_czlowieka", ""))
                    if wybor is None:
                        break
                    if wybor:
                        wiersz["powod_do_czlowieka"] = wybor
                elif flaga:
                    wiersz["do_czlowieka"] = "nie"
                    wiersz["powod_do_czlowieka"] = ""

                pytania = pytaj_z_walidacja(
                    "  ile pytań klienta? (Enter = pomiń, q = koniec): ",
                    lambda o: o.isdigit(),
                    "Podaj liczbę, na przykład 0.",
                )
                if pytania is None:
                    break
                if pytania:
                    wiersz["pytania_liczba"] = pytania

            elif args.przebieg == 2:
                print("\n  --- pola (Enter przeskakuje, q kończy) ---")
                przerwane = False
                for kolumna in kolumny_pol:
                    wartosc = pytaj_tekst(kolumna, wiersz.get(kolumna, ""))
                    if wartosc is None:
                        przerwane = True
                        break
                    if wartosc:
                        wiersz[kolumna] = wartosc
                if przerwane:
                    break

            else:  # przebieg 3
                kandydaci = [
                    k.strip() for k in (wiersz.get("_propozycja_pustych") or "").split(";")
                    if k.strip()
                ]
                if not kandydaci:
                    print("  brak kandydatów na pola-pułapki")
                else:
                    print("\n  --- które z tych pól MUSZĄ zostać puste? ---")
                    print("  Zaznacz tylko te, dla których sprawdziłaś, że w treści nic nie ma.")
                    print("  Źle oznaczona pułapka odwraca metrykę: model dostaje karę")
                    print("  za poprawnie wyciągniętą wartość.\n")
                    wybrane = []
                    przerwane = False
                    for kandydat in kandydaci:
                        odp = input(f"    {kandydat}  t/n (Enter = nie, q = koniec): ").strip().lower()
                        if odp == "q":
                            przerwane = True
                            break
                        if odp in ("t", "tak", "y", "1"):
                            wybrane.append(kandydat)
                    if wybrane:
                        wiersz["pola_puste"] = "; ".join(wybrane)
                    if przerwane:
                        break

            zrobione += 1
            zapisz(plik, wiersze, kolumny)  # zapis po każdym wierszu
            pelne = sum(1 for w in wiersze if w.get("intencja"))
            print(f"    >>> ZAPISANO {wiersz['id']}  "
                  f"(wypełnionych w pliku: {pelne}/{len(wiersze)})")
            print(f"        {plik.resolve()}")

    except KeyboardInterrupt:
        print("\n\nPrzerwane. Stan zapisany.")

    zapisz(plik, wiersze, kolumny)
    print(f"\nWypełnione w tej sesji: {zrobione}")
    stan(wiersze)
    print(f"\nPlik: {plik}")
    print("Gdy przebieg 1 jest pełny:")
    print(f"  python korpus/src/csv_na_gold.py --csv {args.csv} "
          "--wyjscie korpus/gold/gold_prod.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
