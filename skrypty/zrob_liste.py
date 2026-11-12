#!/usr/bin/env python3
"""Arkusz wyjazdu: lista uczestników, rezerwacje, logistyka na jednej stronie.

    python skrypty/zrob_liste.py --lista
    python skrypty/zrob_liste.py dolomity-jesien-2026
    python skrypty/zrob_liste.py dolomity-jesien-2026 --okrojona
    python skrypty/zrob_liste.py --przypisz 4 dolomity-jesien-2026
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from biuro import baza  # noqa: E402
from biuro.listy import zrob_arkusz  # noqa: E402
from biuro.pii import zamaskuj_kod  # noqa: E402
from biuro.polszczyzna import osob as odmiana_osob  # noqa: E402
from biuro.schemas import Rezerwacja  # noqa: E402
from biuro.umowy import wyjazdy  # noqa: E402


def pokaz_stan() -> None:
    baza.inicjuj()
    print("WYJAZDY")
    for klucz, dane in wyjazdy().items():
        uczestnicy = baza.uczestnicy_wyjazdu(klucz)
        rezerwacje = baza.rezerwacje_wyjazdu(klucz)
        typy = sorted({r["typ"] for r in rezerwacje})
        print(f"  {klucz}")
        print(f"    {dane.get('nazwa','')} | {dane.get('termin_od','?')}")
        print(f"    uczestników z umową: {len(uczestnicy)} | "
              f"rezerwacji: {len(rezerwacje)} {typy or ''}")

    nieprzypisane = baza.rezerwacje_nieprzypisane()
    if nieprzypisane:
        print("\nREZERWACJE BEZ PRZYPISANEGO WYJAZDU")
        for r in nieprzypisane:
            rez = Rezerwacja.model_validate_json(r["dane"])
            print(f"  [{r['id']:3d}] {rez.etykieta()} | {rez.data_od or '?'} - {rez.data_do or '?'}")
        print("\n  Przypisz: python skrypty/zrob_liste.py --przypisz <id> <klucz-wyjazdu>")

    braki = [
        r for klucz in wyjazdy() for r in baza.rezerwacje_wyjazdu(klucz)
        if r["braki"] and r["braki"] != "[]"
    ]
    if braki:
        print("\nREZERWACJE Z BRAKAMI")
        for r in braki:
            rez = Rezerwacja.model_validate_json(r["dane"])
            print(f"  {rez.etykieta()}: brak {r['braki']}")

    # osobne ostrzeżenie o samochodach bez ubezpieczenia wkładu własnego
    ostrzezenia = []
    for klucz in wyjazdy():
        for r in baza.rezerwacje_wyjazdu(klucz):
            if r["typ"] != "samochod":
                continue
            rez = Rezerwacja.model_validate_json(r["dane"])
            if rez.ubezpieczenie_wkladu is not True:
                ostrzezenia.append((klucz, rez))
    if ostrzezenia:
        print("\nSAMOCHODY BEZ POTWIERDZONEGO UBEZPIECZENIA WKŁADU WŁASNEGO")
        for klucz, rez in ostrzezenia:
            print(f"  {klucz}: {rez.dostawca or '?'} | wkład własny: {rez.wklad_wlasny or '?'}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wyjazd", nargs="?", help="klucz z wyjazdy.yaml")
    parser.add_argument("--lista", action="store_true", help="pokaż stan wyjazdów i rezerwacji")
    parser.add_argument("--okrojona", action="store_true",
                        help="bez PESEL-i, numerów dokumentów i kodów dostępu")
    parser.add_argument("--oba", action="store_true",
                        help="zrób od razu wariant pełny i okrojony")
    parser.add_argument("--przypisz", nargs=2, metavar=("ID", "WYJAZD"),
                        help="przypisz rezerwację do wyjazdu")
    args = parser.parse_args()

    baza.inicjuj()

    if args.przypisz:
        rez_id, klucz = args.przypisz
        if klucz not in wyjazdy():
            print(f"Nie ma wyjazdu '{klucz}'. Dostępne: {', '.join(wyjazdy())}")
            return 1
        baza.przypisz_rezerwacje(int(rez_id), klucz)
        print(f"Rezerwacja {rez_id} przypisana do {klucz}.")
        return 0

    if args.lista or not args.wyjazd:
        pokaz_stan()
        return 0

    nazwa = str(wyjazdy().get(args.wyjazd, {}).get("nazwa", args.wyjazd))
    ilu = len(baza.uczestnicy_wyjazdu(args.wyjazd))

    if args.oba:
        pelna = zrob_arkusz(args.wyjazd, wrazliwe=True)
        okrojona = zrob_arkusz(args.wyjazd, wrazliwe=False)
        print(f"Lista uczestników — {nazwa}: {odmiana_osob(ilu)}.")
        print(f"Folder: {pelna.parent}")
        print(f"  do biura (z PESEL-ami):        {pelna.name}")
        print(f"  do wysłania na zewnątrz:       {okrojona.name}")
        return 0

    plik = zrob_arkusz(args.wyjazd, wrazliwe=not args.okrojona)
    wariant = ("bez PESEL-i — można wysłać na zewnątrz" if args.okrojona
               else "z PESEL-ami — tylko do biura")
    print(f"Lista uczestników — {nazwa}: {odmiana_osob(ilu)}, {wariant}.")
    print(f"Folder: {plik.parent}")
    print(f"Plik:   {plik.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
