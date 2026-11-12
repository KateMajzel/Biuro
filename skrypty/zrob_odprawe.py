#!/usr/bin/env python3
"""Odprawa przedwyjazdowa dla uczestnika, jako projekt maila.

    python skrypty/zrob_odprawe.py --lista
    python skrypty/zrob_odprawe.py 3 dolomity-jesien-2026
    python skrypty/zrob_odprawe.py 3 dolomity-jesien-2026 --do-skrzynki
    python skrypty/zrob_odprawe.py --wszyscy dolomity-jesien-2026

Bez --do-skrzynki odprawa ląduje jako plik tekstowy w dane/odprawy/.
Z --do-skrzynki trafia do folderu wersji roboczych i czeka na wysłanie ręczne.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from biuro import baza, odprawa  # noqa: E402
from biuro.pii import zamaskuj  # noqa: E402
from biuro.umowy import wyjazdy, wyjazd_dla_zgloszenia  # noqa: E402


def lista() -> None:
    baza.inicjuj()
    print("UCZESTNICY Z UMOWĄ")
    for klucz, dane in wyjazdy().items():
        uczestnicy = baza.uczestnicy_wyjazdu(klucz)
        if not uczestnicy:
            continue
        print(f"\n  {klucz} — {dane.get('nazwa','')}")
        for u in uczestnicy:
            print(f"    [{u['id']:3d}] {u['imie'] or ''} {u['nazwisko'] or ''} "
                  f"<{zamaskuj(u['email'] or '')}>")
    print("\nWYJAZDY: " + ", ".join(wyjazdy()))


def jedna(zgloszenie_id: int, klucz: str, do_skrzynki: bool) -> int:
    wynik = odprawa.przygotuj(zgloszenie_id, klucz)
    projekt = wynik.projekt

    kto = " ".join(
        x for x in (wynik.uczestnik.imie, wynik.uczestnik.nazwisko) if x
    ) or f"zgłoszenie {zgloszenie_id}"

    if do_skrzynki:
        folder = odprawa.wstaw_do_skrzynki(wynik)
        print(f"\nOdprawa gotowa — {kto}.")
        print(f"Czeka jako wersja robocza w folderze: {folder}")
    else:
        plik = odprawa.zapisz_do_pliku(wynik)
        print(f"\nOdprawa gotowa — {kto}.")
        print(f"Plik:   {plik.name}")
        print(f"Folder: {plik.parent}")

    if projekt.do_uzupelnienia:
        print("\nPrzed wysłaniem uzupełnij:")
        for pozycja in projekt.do_uzupelnienia:
            print(f"  - {pozycja}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("zgloszenie_id", nargs="?", type=int)
    parser.add_argument("wyjazd", nargs="?")
    parser.add_argument("--lista", action="store_true")
    parser.add_argument("--wszyscy", metavar="WYJAZD",
                        help="odprawy dla wszystkich uczestników wyjazdu")
    parser.add_argument("--do-skrzynki", action="store_true",
                        help="wstaw jako wersję roboczą w skrzynce")
    args = parser.parse_args()

    baza.inicjuj()

    if args.lista or (not args.wszyscy and args.zgloszenie_id is None):
        lista()
        return 0

    if args.wszyscy:
        if args.wszyscy not in wyjazdy():
            print(f"Nie ma wyjazdu '{args.wszyscy}'. Dostępne: {', '.join(wyjazdy())}")
            return 1
        uczestnicy = baza.uczestnicy_wyjazdu(args.wszyscy)
        if not uczestnicy:
            print(f"Brak uczestników z umową na {args.wszyscy}.")
            return 1
        bledy = 0
        for u in uczestnicy:
            try:
                jedna(u["id"], args.wszyscy, args.do_skrzynki)
            except Exception as e:
                bledy += 1
                print(f"\nBŁĄD dla zgłoszenia {u['id']}: {e}")
        print(f"\nGotowe: {len(uczestnicy) - bledy}/{len(uczestnicy)} odpraw.")
        return 1 if bledy else 0

    wyjazd = args.wyjazd
    if not wyjazd:
        # Tak samo jak przy umowie: wyjazd wynika ze zgłoszenia.
        wynik = wyjazd_dla_zgloszenia(args.zgloszenie_id)
        if wynik.klucz is None:
            print(f"Nie umiem ustalić wyjazdu: {wynik.powod}")
            if wynik.kandydaci:
                print("Podaj klucz jako drugi argument. Pasują: "
                      + ", ".join(wynik.kandydaci))
            return 1
        wyjazd = wynik.klucz
        print(f"Wyjazd: {wyjazd} ({wynik.powod})")

    try:
        return jedna(args.zgloszenie_id, wyjazd, args.do_skrzynki)
    except RuntimeError as e:
        print(f"BŁĄD: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
