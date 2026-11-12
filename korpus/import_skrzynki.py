#!/usr/bin/env python3
"""Import prawdziwej poczty wprost ze skrzynki do pomiaru.

    python korpus/import_skrzynki.py --dni 120 --podglad
    python korpus/import_skrzynki.py --dni 120 --ile 50 --zapisz

Po co osobny skrypt, skoro w tamtej sesji powstał `import_maili.py`:
ten czyta **wprost ze skrzynki** przez ten sam klient IMAP, którego używa
produkcja, i zapisuje JSONL w kształcie, który `szkielet_gold.py` rozumie bez
żadnego mapowania kolumn. Nie trzeba eksportować poczty do pliku tekstowego,
zgadywać wzorca granicy między wiadomościami ani dopisywać nazw do `KLUCZE_*`.

Co z tego wychodzi:

    out/poczta_prawdziwa.jsonl   id, od, temat, tresc, tresc_pelna, data

`tresc` to treść nowa, `tresc_pelna` to treść z cytowaną historią. Rozdzielenie
jest potrzebne, żeby raport rozróżniał błąd parsera od błędu promptu: cztery
wiadomości w korpusie syntetycznym mają kluczowe liczby wyłącznie w cytacie.

**Te pliki zostają na Twoim dysku.** Nic nie jest nigdzie wysyłane, a `out/`
jest w .gitignore. Podgląd maskuje dane wrażliwe, żeby dało się go wkleić
w rozmowę bez wynoszenia PESEL-i.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KORZEN))

from biuro.config import cfg  # noqa: E402
from biuro.mail.imap_client import Skrzynka  # noqa: E402
from biuro.pii import zamaskuj  # noqa: E402

# Granica cytowanej historii. Wszystko od tego miejsca w dół to cytat.
CYTAT = re.compile(
    r"^\s*(?:>|W dniu .{0,60}napisa|On .{0,60}wrote:|-{2,}\s*(?:Przekazana|Oryginalna|"
    r"Original|Forwarded)|Od:\s|From:\s|_{5,})",
    re.IGNORECASE | re.MULTILINE,
)


def rozdziel_cytat(tresc: str) -> tuple[str, str]:
    """Zwraca (treść nowa, treść pełna)."""
    dopasowanie = CYTAT.search(tresc)
    nowa = tresc[: dopasowanie.start()].strip() if dopasowanie else tresc.strip()
    return nowa, tresc.strip()


def zbierz(dni: int, ile: int | None) -> list[dict[str, str]]:
    # limit=0 — bez limitu. Pomiar musi wziąć całe okno, a nie tyle, ile
    # produkcja przetwarza w jednym przebiegu (poczta.limit_na_przebieg).
    with Skrzynka() as skrzynka:
        maile = skrzynka.nowe(dni=dni, limit=ile or 0)

    rekordy: list[dict[str, str]] = []
    for nr, mail in enumerate(maile, start=1):
        nowa, pelna = rozdziel_cytat(mail.tresc)
        if not nowa and not pelna:
            continue
        rekordy.append({
            "id": f"REAL_{nr:03d}",
            "od": mail.od,
            "od_nazwa": mail.od_nazwa,
            "temat": mail.temat,
            "data": mail.data,
            "tresc": nowa,
            "tresc_pelna": pelna,
            "zalaczniki": ", ".join(mail.zalaczniki),
        })
        if ile and len(rekordy) >= ile:
            break
    return rekordy


def podglad(rekordy: list[dict[str, str]], ile_maili: int, ile_linii: int) -> None:
    print(f"\nZnaleziono {len(rekordy)} wiadomości.\n")
    print("Podgląd z zamaskowanymi danymi wrażliwymi — można go wkleić w rozmowę:")
    for rekord in rekordy[:ile_maili]:
        print("\n" + "=" * 70)
        print(f"{rekord['id']}  od: {zamaskuj(rekord['od'])}")
        print(f"temat: {rekord['temat'][:70]}")
        print(f"treść nowa: {len(rekord['tresc'])} znaków, "
              f"z cytatami: {len(rekord['tresc_pelna'])} znaków")
        if rekord["zalaczniki"]:
            print(f"załączniki: {rekord['zalaczniki']}")
        print("-" * 70)
        for linia in zamaskuj(rekord["tresc"]).splitlines()[:ile_linii]:
            print(f"| {linia[:100]}")

    # ile wiadomości ma treść wyłącznie w cytacie - to przyszłe pułapki
    tylko_cytat = sum(1 for r in rekordy if len(r["tresc"]) < 40 <= len(r["tresc_pelna"]))
    print("\n" + "=" * 70)
    print(f"Wiadomości, w których nowa treść jest bardzo krótka, a historia długa: "
          f"{tylko_cytat}")
    if tylko_cytat:
        print("  To odpowiedzi w wątku. Jeśli kluczowe dane są tylko w cytacie,")
        print("  użyj --pelna-tresc w adapterze, żeby sprawdzić, czy raport")
        print("  rozróżnia błąd parsera od błędu promptu.")
    print("\nJeśli liczba wiadomości i struktura się zgadzają, uruchom ponownie z --zapisz")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dni", type=int, default=120,
                        help="jak daleko w przeszłość (domyślnie 120)")
    parser.add_argument("--ile", type=int, default=None,
                        help="maksymalnie tyle wiadomości (do pomiaru wystarczy 30-50)")
    parser.add_argument("--podglad", action="store_true",
                        help="pokaż, co znalazł, bez zapisywania")
    parser.add_argument("--zapisz", action="store_true", help="zapisz JSONL")
    parser.add_argument("--wyjscie", default="korpus/out/poczta_prawdziwa.jsonl")
    parser.add_argument("--ile-maili", type=int, default=3, help="ile pokazać w podglądzie")
    parser.add_argument("--ile-linii", type=int, default=10)
    args = parser.parse_args()

    if not args.podglad and not args.zapisz:
        args.podglad = True

    # limit_na_przebieg z config.yaml ogranicza pobieranie - do pomiaru
    # potrzebujemy więcej niż dzienny przebieg po skrzynce
    if args.ile and args.ile > int(cfg().get("poczta.limit_na_przebieg", 20)):
        cfg()._dane.setdefault("poczta", {})["limit_na_przebieg"] = args.ile

    try:
        rekordy = zbierz(args.dni, args.ile)
    except Exception as e:
        print(f"Nie mogę pobrać poczty: {type(e).__name__}: {e}")
        print("Sprawdź: python skrypty/sprawdz_gotowosc.py")
        return 1

    if not rekordy:
        print(f"Brak wiadomości z ostatnich {args.dni} dni.")
        return 1

    if args.podglad:
        podglad(rekordy, args.ile_maili, args.ile_linii)
        return 0

    wyjscie = KORZEN / args.wyjscie
    wyjscie.parent.mkdir(parents=True, exist_ok=True)
    with wyjscie.open("w", encoding="utf-8") as fh:
        for rekord in rekordy:
            fh.write(json.dumps(rekord, ensure_ascii=False) + "\n")

    print(f"Zapisano {len(rekordy)} wiadomości do {wyjscie}")
    print(f"Okno: ostatnie {args.dni} dni. Limit: "
          + (f"{args.ile} (--ile)" if args.ile else "bez limitu, całe okno")
          + ".")
    if args.ile and len(rekordy) >= args.ile:
        print("  UWAGA: liczba wiadomości równa limitowi — próbka może być "
              "obcięta. Podnieś --ile albo pomiń je całkiem.")
    print("\nTen plik zawiera prawdziwe dane uczestników. Zostaje na dysku, "
          "jest w .gitignore.\n")
    print("Następny krok — szkielet ground truth do wypełnienia w arkuszu:")
    print(f"  python korpus/src/szkielet_gold.py \\")
    print(f"      --zrodlo {args.wyjscie} \\")
    print(f"      --wyjscie korpus/out/szkielet")
    print("\nPotem otwierasz korpus/out/szkielet.csv w arkuszu.")
    print("Kolejność, która idzie najszybciej: najpierw intencja i do_czlowieka")
    print("dla wszystkich wierszy naraz, potem pola wymagające czytania treści.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
