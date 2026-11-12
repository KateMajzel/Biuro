#!/usr/bin/env python3
"""Pomost między produkcją a harnessem.

Czyta korpus w JSONL, przepuszcza każdą wiadomość przez produkcyjny
klasyfikator i ekstrakcję z `biuro/`, i wypisuje predykcje w formacie,
który rozumie `src/ocen.py` — czyli w ścieżkach kanonicznych.

    # bez modelu, działa wszędzie: sama warstwa deterministyczna
    python korpus/adapter.py --zrodlo korpus/out/maile.jsonl \
        --wyjscie korpus/out/predykcje_regex.jsonl --tryb regex

    # z modelem, wymaga Ollamy
    python korpus/adapter.py --zrodlo korpus/out/maile.jsonl \
        --wyjscie korpus/out/predykcje_hybryda.jsonl --tryb hybryda

Tłumaczenie nazw dzieje się TUTAJ, nie w `schemat/mapowanie_pol.json`.
Dzięki temu plik mapowania zostaje tożsamościowy, a gold nie wie nic
o `schemas.py` i nie trzeba go ruszać przy zmianie schematu.

Czego ten adapter nie udaje: produkcyjny schemat `Uczestnik` celuje w pola
formularza zgłoszeniowego, a gold obejmuje znacznie szerszy zestaw.
Ścieżki, których schemat nie próbuje wypełnić, wychodzą puste i są liczone
jako niewyciągnięte. Patrz POKRYCIE.md — raport bez tej informacji
podawałby liczbę nie na temat.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KORZEN))

from biuro.deterministyczne import ustal  # noqa: E402
from biuro.schemas import TypMaila, Uczestnik  # noqa: E402

# Ścieżki kanoniczne, które produkcyjny schemat umie wypełnić.
# Lewa strona: ścieżka z gold. Prawa: pole w Uczestniku albo w wyniku regexu.
POKRYTE: dict[str, str] = {
    "kontakt.email": "email",
    "kontakt.telefon": "telefon",
    "kontakt.organizacja": "nazwa_firmy",
    "kontakt.kraj": "kraj_region",
    "zgloszenie.liczba_osob": "liczba_osob",
    "zgloszenie.budzet": "budzet",
    "uczestnicy[0].pesel": "pesel",
    "uczestnicy[0].dokument": "numer_dokumentu",
    "uczestnicy[0].adres_kod_pocztowy": "kod_pocztowy",
    "wymagania.inne_osoby": "wymagania_innych_osob",
    "wymagania.dieta": "dodatkowe_informacje",
    # dołożone po analizie pokrycia: schemat wyciągał KTO, ale nie CZEGO chce
    "wyjazd.kierunek": "wyjazd_kierunek",
    "wyjazd.termin_opis": "wyjazd_termin",
    "wyjazd.data_od": "wyjazd_data_od",
    "wyjazd.data_do": "wyjazd_data_do",
    "faktura.nip": "nip",
}

# Pełny zbiór ścieżek, które `na_kanoniczne` może wypełnić: klucze POKRYTE
# plus dwie składane z kilku pól Uczestnika. Wyliczane raz, zapisywane do
# schemat/pokryte.json przy każdym przebiegu — ręcznie utrzymywana liczba
# rozjechałaby się z kodem przy pierwszym dołożonym polu.
SCIEZKI_POKRYTE: set[str] = set(POKRYTE) | {
    "kontakt.imie_nazwisko",   # imie + nazwisko
    "uczestnicy[0].adres",     # adres_ulica + adres_kod_pocztowy + adres_miasto
}


def na_kanoniczne(uczestnik: Uczestnik) -> dict[str, object]:
    """Produkcyjny Uczestnik -> ścieżki kanoniczne gold."""
    dane = uczestnik.model_dump()
    pola: dict[str, object] = {}

    for sciezka, pole in POKRYTE.items():
        wartosc = dane.get(pole)
        if wartosc not in (None, ""):
            pola[sciezka] = wartosc

    # imię i nazwisko są w gold jednym polem, w schemacie dwoma
    czesci = [x for x in (uczestnik.imie, uczestnik.nazwisko) if x]
    if czesci:
        pola["kontakt.imie_nazwisko"] = " ".join(czesci)

    # adres: gold trzyma ulicę i miasto razem
    adres = ", ".join(
        x for x in (
            uczestnik.ulica,
            " ".join(y for y in (uczestnik.kod_pocztowy, uczestnik.miasto) if y).strip(),
        ) if x
    )
    if adres:
        pola["uczestnicy[0].adres"] = adres

    return pola


def tylko_regex(tekst: str) -> dict[str, object]:
    """Wariant bez modelu: tylko warstwa deterministyczna.

    Odpowiednik wiersza „sam regex" w tabeli pomiarów. Działa bez Ollamy,
    więc da się go policzyć wszędzie, także w CI.
    """
    wynik = ustal(tekst)
    pola: dict[str, object] = {}
    for nazwa, ustalenie in wynik.ustalenia.items():
        for sciezka, pole in POKRYTE.items():
            if pole == nazwa:
                pola[sciezka] = ustalenie.wartosc
    return pola


def przez_model(tekst: str, tryb: str) -> tuple[dict[str, object], str, bool, int]:
    """Wariant z modelem: klasyfikacja i pełna ekstrakcja."""
    from biuro.ekstrakcja import ekstrahuj
    from biuro.mail.imap_client import Mail
    from biuro.mail.pipeline import zaklasyfikuj

    raport = ekstrahuj(tekst, tryb=tryb)
    pola = na_kanoniczne(raport.uczestnik)

    pseudo = Mail(
        message_id="", od="", od_nazwa="", temat="", data="", tresc=tekst
    )
    klasyfikacja = zaklasyfikuj(pseudo)
    return (
        pola,
        klasyfikacja.typ.value,
        klasyfikacja.do_czlowieka,
        klasyfikacja.pytania_liczba,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zrodlo", required=True, help="korpus w JSONL")
    parser.add_argument("--wyjscie", required=True, help="plik predykcji JSONL")
    parser.add_argument("--tryb", default="hybryda",
                        choices=["regex", "llm", "hybryda"],
                        help="regex nie wymaga Ollamy")
    parser.add_argument("--pelna-tresc", action="store_true",
                        help="podaj modelowi treść z cytatami (do sprawdzenia parsera)")
    args = parser.parse_args()

    zrodlo = Path(args.zrodlo)
    if not zrodlo.exists():
        print(f"Brak pliku {zrodlo}. Uruchom najpierw:")
        print("  python korpus/src/parsuj_korpus.py --zrodlo "
              "korpus/dane/maile_testowe_biuro_podrozy.txt "
              "--wyjscie korpus/out/maile.jsonl")
        return 1

    wiadomosci = [
        json.loads(linia) for linia in zrodlo.read_text(encoding="utf-8").splitlines()
        if linia.strip()
    ]

    wyjscie = Path(args.wyjscie)
    wyjscie.parent.mkdir(parents=True, exist_ok=True)

    klucz_tresci = "tresc_pelna" if args.pelna_tresc else "tresc"
    bledy = 0

    with wyjscie.open("w", encoding="utf-8") as fh:
        for nr, wiadomosc in enumerate(wiadomosci, start=1):
            ident = wiadomosc.get("id") or f"MAIL_{nr:02d}"
            tekst = wiadomosc.get(klucz_tresci) or wiadomosc.get("tresc") or ""
            temat = wiadomosc.get("temat") or ""
            pelny = f"{temat}\n\n{tekst}" if temat else tekst

            try:
                if args.tryb == "regex":
                    pola = tylko_regex(pelny)
                    intencja, do_czlowieka, pytania = "inne", False, 0
                else:
                    pola, intencja, do_czlowieka, pytania = przez_model(pelny, args.tryb)
            except Exception as e:
                bledy += 1
                print(f"  {ident}: BŁĄD {type(e).__name__}: {e}")
                pola, intencja, do_czlowieka, pytania = {}, "inne", False, 0

            fh.write(json.dumps({
                "id": ident,
                "intencja": intencja,
                "intencje_dodatkowe": [],
                "do_czlowieka": do_czlowieka,
                "pytania_liczba": pytania,
                "pola": pola,
            }, ensure_ascii=False) + "\n")

    print(f"Zapisano {len(wiadomosci)} predykcji do {wyjscie} (tryb: {args.tryb})")
    if bledy:
        print(f"Błędów w trakcie: {bledy}")
    # Lista dla ocen.py — pisana przy każdym przebiegu, żeby nie rozjechała
    # się z kodem. Bez niej raport nie umie oddzielić błędu modelu od decyzji
    # o zakresie schematu i podaje jedną liczbę, która wygląda jak porażka.
    plik_pokrycia = Path(__file__).resolve().parent / "schemat" / "pokryte.json"
    plik_pokrycia.write_text(
        json.dumps(sorted(SCIEZKI_POKRYTE), ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"\nŚcieżek kanonicznych, które schemat produkcyjny próbuje wypełnić: "
          f"{len(SCIEZKI_POKRYTE)}  (lista: {plik_pokrycia.name})")
    print("Pozostałe wyjdą puste i będą policzone jako niewyciągnięte — "
          "patrz korpus/POKRYCIE.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
