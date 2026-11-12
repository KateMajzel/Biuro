#!/usr/bin/env python3
"""Generuje umowę dla zgłoszenia z bazy.

    python skrypty/zrob_umowe.py --lista
    python skrypty/zrob_umowe.py 3 dolomity-jesien-2026
    python skrypty/zrob_umowe.py 3 dolomity-jesien-2026 --bez-rejestru
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from biuro import baza, umowy  # noqa: E402
from biuro.pii import zamaskuj  # noqa: E402


def lista() -> None:
    baza.inicjuj()
    with baza.polaczenie() as conn:
        zgloszenia = conn.execute(
            """SELECT z.id, z.imie, z.nazwisko, z.email, z.status,
                      (SELECT COUNT(*) FROM dane_wrazliwe d WHERE d.zgloszenie_id = z.id) AS ma_dane
               FROM zgloszenia z ORDER BY z.id"""
        ).fetchall()

    print("ZGŁOSZENIA")
    if not zgloszenia:
        print("  (brak - uruchom najpierw skrypty/sprawdz_maile.py)")
    for z in zgloszenia:
        znacznik = "dane do umowy: tak" if z["ma_dane"] else "dane do umowy: BRAK"
        print(f"  [{z['id']:3d}] {z['imie'] or ''} {z['nazwisko'] or ''} "
              f"<{zamaskuj(z['email'])}> | {z['status']} | {znacznik}")

    print("\nWYJAZDY")
    try:
        katalog = umowy.wyjazdy()
    except RuntimeError as e:
        # Brak wyjazdy.yaml to normalny stan przy pierwszym uruchomieniu
        # u nowej firmy — ma być czytelnym komunikatem, nie wyjątkiem.
        print(f"  {e}")
        return
    for klucz, dane in katalog.items():
        print(f"  {klucz}  —  {dane.get('nazwa', '')} ({dane.get('termin_od', '?')})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("zgloszenie_id", nargs="?", type=int)
    parser.add_argument("wyjazd", nargs="?")
    parser.add_argument("--lista", action="store_true", help="pokaż zgłoszenia i wyjazdy")
    parser.add_argument("--bez-rejestru", action="store_true",
                        help="nie zapisuj w rejestrze umów (test)")
    args = parser.parse_args()

    if args.lista or args.zgloszenie_id is None:
        lista()
        return 0

    baza.inicjuj()

    wyjazd = args.wyjazd
    if not wyjazd:
        # Klucza wyjazdu nie trzeba podawać: zgłoszenie wie, czego dotyczy.
        wynik = umowy.wyjazd_dla_zgloszenia(args.zgloszenie_id)
        if wynik.klucz is None:
            print(f"Nie umiem ustalić wyjazdu: {wynik.powod}")
            if wynik.kandydaci:
                print("\nPodaj klucz jako drugi argument. Pasują:")
                katalog = umowy.wyjazdy()
                for klucz in wynik.kandydaci:
                    dane = katalog.get(klucz, {})
                    print(f"  {klucz}  —  {dane.get('nazwa', '')} "
                          f"({dane.get('termin_od', '?')})")
            return 1
        wyjazd = wynik.klucz
        print(f"Wyjazd: {wyjazd} ({wynik.powod})")

    kto = umowy.opis_uczestnika(args.zgloszenie_id)
    nazwa_wyjazdu = umowy.wyjazdy().get(wyjazd, {}).get("nazwa", wyjazd)

    docx, pdf, braki = umowy.generuj(
        args.zgloszenie_id, wyjazd, zapisz_w_rejestrze=not args.bez_rejestru
    )

    # Potwierdzenie mówi najpierw DLA KOGO i NA CO, a dopiero potem gdzie leży
    # plik. Przy dziesięciu umowach dziennie to pierwsze jest tym, co się
    # sprawdza wzrokiem.
    print(f"\nUmowa gotowa — {kto}, {nazwa_wyjazdu}.")
    print(f"Plik:   {docx.name}")
    print(f"Folder: {docx.parent}")
    if pdf:
        print(f"PDF:    {pdf.name}")
    else:
        print("PDF:    nie powstał (brak LibreOffice) — jest sam .docx")

    if braki:
        print(f"\nUWAGA: {len(braki)} pól pustych albo wciąż w nawiasach "
              "kwadratowych. Umowa NIE JEST GOTOWA do podpisu.")
        print("Uzupełnij w config.yaml albo wyjazdy.yaml:")
        for pole in braki:
            print(f"  - {pole}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
