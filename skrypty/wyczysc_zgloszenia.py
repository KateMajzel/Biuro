#!/usr/bin/env python3
"""Usuwa zgłoszenia uczestników — po próbach albo po błędzie w danych.

    python skrypty/wyczysc_zgloszenia.py                       # pokaż, nic nie rusz
    python skrypty/wyczysc_zgloszenia.py --id 11-30 53 --zrob  # wskazane numery
    python skrypty/wyczysc_zgloszenia.py --bez-wyjazdu --zrob  # bez przypisanego wyjazdu
    python skrypty/wyczysc_zgloszenia.py --wszystkie --zrob    # wszystkie

Bez `--zrob` tylko pokazuje, co zostałoby usunięte. Przed usunięciem kopiuje
całą bazę do `kopie_zapasowe/`. Razem ze zgłoszeniem znikają jego dane do
umowy (PESEL, dokument, adres).

Zgłoszenia, do którego jest umowa, skrypt nie usuwa — najpierw trzeba usunąć
umowę (`wyczysc_umowy.py`), bo rejestr umów nie może wskazywać na osobę,
której nie ma w bazie.

Usunięte zgłoszenie nie wraca przy następnym sprawdzeniu poczty: wiadomość,
z której powstało, zostaje oznaczona jako usunięta ręcznie.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KORZEN))

from biuro import baza  # noqa: E402
from biuro.config import cfg  # noqa: E402
from biuro.polszczyzna import zgloszen as odmiana_zgloszen  # noqa: E402


def numery(zapisy: list[str]) -> set[int]:
    """'11-30', '53' → {11, …, 30, 53}"""
    wynik: set[int] = set()
    for zapis in zapisy:
        for czesc in zapis.replace(",", " ").split():
            if "-" in czesc:
                od, do = czesc.split("-", 1)
                wynik.update(range(int(od), int(do) + 1))
            else:
                wynik.add(int(czesc))
    return wynik


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", nargs="+", default=[], metavar="NR",
                        help="numery zgłoszeń, także zakresy: 11-30 53")
    parser.add_argument("--bez-wyjazdu", action="store_true",
                        help="zgłoszenia bez przypisanego wyjazdu")
    parser.add_argument("--wszystkie", action="store_true")
    parser.add_argument("--zrob", action="store_true", help="wykonaj usunięcie")
    args = parser.parse_args()

    baza.inicjuj()
    zgloszenia = baza.zgloszenia_do_wyboru()
    if not zgloszenia:
        print("W bazie nie ma zgłoszeń.")
        return 0

    try:
        wskazane = numery(args.id)
    except ValueError:
        print("Numery podaj tak: --id 11-30 53 62")
        return 1

    def wybrane(z: dict) -> bool:
        return (args.wszystkie or z["id"] in wskazane
                or (args.bez_wyjazdu and not z["wyjazd_klucz"]))

    print(f"W bazie: {odmiana_zgloszen(len(zgloszenia))}.\n")
    for z in sorted(zgloszenia, key=lambda w: w["id"]):
        osoba = " ".join(x for x in (z["imie"], z["nazwisko"]) if x) or "?"
        umowa = f"  [umowa {z['numer_umowy']}]" if z["numer_umowy"] else ""
        znak = "x" if wybrane(z) else " "
        print(f" {znak} [{z['id']:>3}] {osoba:<32} "
              f"{(z['wyjazd_klucz'] or 'bez wyjazdu'):<24}{umowa}")

    if not (args.wszystkie or wskazane or args.bez_wyjazdu):
        print("\nNic nie usunięto. Wskaż zgłoszenia: --id 11-30 53, "
              "--bez-wyjazdu albo --wszystkie.")
        return 0

    do_usuniecia = [z for z in zgloszenia if wybrane(z) and not z["numer_umowy"]]
    z_umowa = [z for z in zgloszenia if wybrane(z) and z["numer_umowy"]]
    if z_umowa:
        print("\nZostają, bo mają umowę (najpierw wyczysc_umowy.py): "
              + ", ".join(str(z["id"]) for z in z_umowa))
    if not do_usuniecia:
        print("\nNie ma czego usuwać.")
        return 0

    print(f"\nDo usunięcia (x): {odmiana_zgloszen(len(do_usuniecia))}.")
    if not args.zrob:
        print("To była próba. Dodaj --zrob, żeby usunąć.")
        return 0

    kopia = KORZEN / "kopie_zapasowe" / datetime.now().strftime("zgloszenia_%Y-%m-%d_%H%M%S")
    kopia.mkdir(parents=True, exist_ok=True)
    plik_bazy = Path(cfg().sciezka("baza"))
    shutil.copy2(plik_bazy, kopia / plik_bazy.name)

    usuniete = baza.usun_zgloszenia([z["id"] for z in do_usuniecia])
    print(f"\nUsunięte zgłoszenia: {usuniete}. "
          f"Zostało w bazie: {len(zgloszenia) - usuniete}.")
    print(f"Kopia bazy sprzed usunięcia: {kopia}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
