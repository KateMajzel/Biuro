#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Konwersja arkusza z ground truth na format gold dla ocen.py.

Droga powrotna po `szkielet_gold.py`: wypełniasz CSV w arkuszu, zapisujesz,
uruchamiasz to i masz plik gold gotowy do pomiaru.

Konwencje arkusza:
  - komórka pusta           -> pole nie występuje w gold (ani wymagane, ani pułapka)
  - komórka z wartością     -> pole wymagane, wartość oczekiwana
  - kilka wariantów         -> rozdziel znakiem |   (np. "Lofoty | Lofoty — zorze i zima")
  - kolumna pola_puste      -> lista ścieżek rozdzielona ;  (pola, które MUSZĄ być puste)
  - do_czlowieka            -> tak/nie, true/false, 1/0
  - pytania_liczba          -> liczba całkowita
  - intencje_dodatkowe      -> lista rozdzielona ;

Walidacja: skrypt odmawia zapisu, jeśli ta sama ścieżka jest jednocześnie
wypełniona i wpisana do pola_puste, albo jeśli brakuje intencji lub flagi
do_czlowieka — bo wtedy pomiar policzy je jako błąd modelu, a to byłby błąd
ground truth.

Użycie:
    python src/csv_na_gold.py --csv out/szkielet.csv --wyjscie gold/gold_prod.json
    python src/csv_na_gold.py --csv out/szkielet.csv --wyjscie gold/gold_prod.json --luzno
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

PRAWDA = {"tak", "true", "1", "t", "y", "yes", "prawda", "x"}
FALSZ = {"nie", "false", "0", "n", "no", "falsz", "fałsz", ""}

KOLUMNY_NIE_POLA = {
    "id", "temat", "intencja", "intencje_dodatkowe", "do_czlowieka",
    "powod_do_czlowieka", "pytania_liczba", "pola_puste",
    "braki_do_zgloszenia", "uwagi", "_z_regexu", "_ostrzezenia", "_temat",
}

POLA_LOGICZNE = {
    "faktura.wymagana", "zgody.regulamin", "zgody.marketing",
    "umowa.podpisana_skan", "zgloszenie.gotowosc_dzielenia_pokoju",
    "platnosc.potwierdzona_przez_klienta", "nocleg.samoobsluga",
    "auto.opony_zimowe", "auto.ubezpieczenie_szyb_wykupione",
    "rezerwacja.oplacona",
}


def na_logiczna(tekst: str) -> bool | None:
    maly = tekst.strip().lower()
    if maly in PRAWDA:
        return True
    if maly in FALSZ:
        return False if maly != "" else None
    return None


def na_liczbe(tekst: str) -> Any:
    czysty = tekst.strip().replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        wartosc = float(czysty)
    except ValueError:
        return None
    return int(wartosc) if wartosc.is_integer() else wartosc


def przetworz_wartosc(sciezka: str, surowa: str) -> Any:
    surowa = surowa.strip()
    if "|" in surowa:
        return [przetworz_wartosc(sciezka, cz) for cz in surowa.split("|") if cz.strip()]
    if sciezka in POLA_LOGICZNE:
        wynik = na_logiczna(surowa)
        return wynik if wynik is not None else surowa
    goly = sciezka.split(".")[-1]
    if goly.startswith(("liczba", "wiek", "kwota", "procent", "budzet", "rok_urodzenia")) \
            or goly in ("liczba_osob", "liczba_dni", "liczba_zarzutow"):
        liczba = na_liczbe(surowa)
        return liczba if liczba is not None else surowa
    return surowa


def main() -> int:
    p = argparse.ArgumentParser(description="Arkusz CSV -> plik gold.")
    p.add_argument("--csv", required=True)
    p.add_argument("--wyjscie", required=True)
    p.add_argument(
        "--luzno",
        action="store_true",
        help="nie przerywaj na brakującej intencji ani flagi — zapisz, co jest",
    )
    args = p.parse_args()

    sciezka = Path(args.csv)
    if not sciezka.exists():
        print(f"BŁĄD: nie ma pliku {sciezka}", file=sys.stderr)
        return 2

    tekst = sciezka.read_text(encoding="utf-8-sig")
    wiersze = list(csv.DictReader(tekst.splitlines()))
    if not wiersze:
        print("BŁĄD: arkusz pusty.", file=sys.stderr)
        return 1

    gold: list[dict[str, Any]] = []
    problemy: list[str] = []

    for nr, wiersz in enumerate(wiersze, 2):  # 2, bo wiersz 1 to nagłówek
        ident = (wiersz.get("id") or "").strip()
        if not ident:
            problemy.append(f"wiersz {nr}: brak id")
            continue

        pola: dict[str, Any] = {}
        for kolumna, surowa in wiersz.items():
            if kolumna in KOLUMNY_NIE_POLA or kolumna is None:
                continue
            if not (surowa or "").strip():
                continue
            pola[kolumna] = przetworz_wartosc(kolumna, surowa)

        pola_puste = [
            cz.strip() for cz in (wiersz.get("pola_puste") or "").split(";") if cz.strip()
        ]
        kolizje = sorted(set(pola) & set(pola_puste))
        if kolizje:
            problemy.append(
                f"{ident}: te ścieżki są jednocześnie wypełnione i w pola_puste: "
                f"{', '.join(kolizje)}"
            )
            for k in kolizje:
                pola_puste.remove(k)

        intencja = (wiersz.get("intencja") or "").strip() or None
        flaga_surowa = (wiersz.get("do_czlowieka") or "").strip()
        flaga = na_logiczna(flaga_surowa)

        if intencja is None:
            problemy.append(f"{ident}: brak intencji")
        if flaga is None:
            problemy.append(f"{ident}: brak do_czlowieka (wpisz tak albo nie)")

        pytania = (wiersz.get("pytania_liczba") or "").strip()
        wpis: dict[str, Any] = {
            "id": ident,
            "intencja": intencja,
            "intencje_dodatkowe": [
                cz.strip() for cz in (wiersz.get("intencje_dodatkowe") or "").split(";")
                if cz.strip()
            ],
            "do_czlowieka": bool(flaga),
            "powod_do_czlowieka": (wiersz.get("powod_do_czlowieka") or "").strip() or None,
            "pola": pola,
            "pola_puste": pola_puste,
            "braki_do_zgloszenia": [
                cz.strip() for cz in (wiersz.get("braki_do_zgloszenia") or "").split(";")
                if cz.strip()
            ],
            "uwagi": (wiersz.get("uwagi") or "").strip(),
        }
        if pytania:
            liczba = na_liczbe(pytania)
            if liczba is not None:
                wpis["pytania_liczba"] = int(liczba)

        gold.append(wpis)

    if problemy:
        print(f"Znaleziono {len(problemy)} problemów w ground truth:", file=sys.stderr)
        for linia in problemy[:30]:
            print(f"  - {linia}", file=sys.stderr)
        if len(problemy) > 30:
            print(f"  … i {len(problemy) - 30} dalszych", file=sys.stderr)
        if not args.luzno:
            print("\nNie zapisano. Popraw arkusz albo uruchom z --luzno.", file=sys.stderr)
            return 1
        print("\n--luzno: zapisuję mimo problemów.", file=sys.stderr)

    wyjscie = Path(args.wyjscie)
    wyjscie.parent.mkdir(parents=True, exist_ok=True)
    wyjscie.write_text(json.dumps(gold, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    pol_wymaganych = sum(len(w["pola"]) for w in gold)
    pol_pustych = sum(len(w["pola_puste"]) for w in gold)
    do_czlowieka = sum(1 for w in gold if w["do_czlowieka"])
    print(f"Zapisano {len(gold)} rekordów do {wyjscie}")
    print(f"  pól wymaganych: {pol_wymaganych}")
    print(f"  pól-pułapek:    {pol_pustych}"
          f"  ({100 * pol_pustych / max(1, pol_wymaganych + pol_pustych):.0f}% wszystkich ocen)")
    print(f"  do człowieka:   {do_czlowieka} / {len(gold)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
