#!/usr/bin/env python3
"""Usuwa umowy z rejestru — po próbach albo po błędzie w danych.

    python skrypty/wyczysc_umowy.py                      # pokaż rejestr, nic nie rusz
    python skrypty/wyczysc_umowy.py --bez-wyjazdu --zrob # usuń umowy bez wyjazdu
    python skrypty/wyczysc_umowy.py --wszystkie --zrob   # usuń wszystkie

Rejestr umów jest podstawą wykazu dla UFG, więc ten skrypt nie robi niczego
po cichu. Bez `--zrob` tylko pokazuje, co zostałoby usunięte. Przed usunięciem
kopiuje całą bazę do `kopie_zapasowe/`, a pliki umów (.docx, .pdf) przenosi
tam samo, zamiast je kasować. Umów oznaczonych jako zgłoszone do UFG nie
usuwa wcale — tych nie wolno ruszać bez korekty deklaracji.

Zgłoszenia uczestników zostają nietknięte: usuwana jest tylko umowa, więc
można ją wystawić od nowa. Numeracja wraca do pierwszego wolnego numeru.
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
from biuro.polszczyzna import umow as odmiana_umow  # noqa: E402


def rejestr() -> list[dict]:
    with baza.polaczenie() as conn:
        wiersze = conn.execute(
            """SELECT u.id, u.numer, u.data_zawarcia, u.wyjazd, u.plik_docx,
                      u.plik_pdf, u.zgloszone_ufg, z.imie, z.nazwisko
               FROM umowy u LEFT JOIN zgloszenia z ON z.id = u.zgloszenie_id
               ORDER BY u.data_zawarcia, u.id"""
        ).fetchall()
    return [dict(w) for w in wiersze]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bez-wyjazdu", action="store_true",
                        help="tylko umowy bez przypisanego wyjazdu")
    parser.add_argument("--wszystkie", action="store_true", help="wszystkie umowy")
    parser.add_argument("--zrob", action="store_true", help="wykonaj usunięcie")
    args = parser.parse_args()

    baza.inicjuj()
    umowy = rejestr()
    if not umowy:
        print("Rejestr umów jest pusty.")
        return 0

    print(f"W rejestrze: {odmiana_umow(len(umowy))}.\n")
    for u in umowy:
        osoba = " ".join(x for x in (u["imie"], u["nazwisko"]) if x) or "?"
        znak = "  [zgłoszona do UFG]" if u["zgloszone_ufg"] else ""
        print(f"  {u['numer']:<10} {u['data_zawarcia']}  "
              f"{(u['wyjazd'] or 'BEZ WYJAZDU'):<24} {osoba}{znak}")

    if not (args.bez_wyjazdu or args.wszystkie):
        print("\nNic nie usunięto. Wybierz --bez-wyjazdu albo --wszystkie.")
        return 0

    do_usuniecia = [
        u for u in umowy
        if not u["zgloszone_ufg"] and (args.wszystkie or not u["wyjazd"])
    ]
    chronione = [u for u in umowy if u["zgloszone_ufg"]
                 and (args.wszystkie or not u["wyjazd"])]
    if chronione:
        print("\nZostają, bo są zgłoszone do UFG: "
              + ", ".join(u["numer"] for u in chronione))
    if not do_usuniecia:
        print("\nNie ma czego usuwać.")
        return 0

    print("\nDo usunięcia: " + ", ".join(u["numer"] for u in do_usuniecia)
          + f" ({odmiana_umow(len(do_usuniecia))})")
    if not args.zrob:
        print("To była próba. Dodaj --zrob, żeby usunąć.")
        return 0

    kopia = KORZEN / "kopie_zapasowe" / datetime.now().strftime("umowy_%Y-%m-%d_%H%M%S")
    kopia.mkdir(parents=True, exist_ok=True)
    plik_bazy = Path(cfg().sciezka("baza"))
    shutil.copy2(plik_bazy, kopia / plik_bazy.name)

    for u in do_usuniecia:
        for sciezka in (u["plik_docx"], u["plik_pdf"]):
            if sciezka and Path(sciezka).exists():
                shutil.move(str(sciezka), str(kopia / Path(sciezka).name))
    with baza.polaczenie() as conn:
        conn.executemany("DELETE FROM umowy WHERE id = ?",
                         [(u["id"],) for u in do_usuniecia])

    print(f"\nUsunięte umowy: {len(do_usuniecia)}. "
          f"Zostało w rejestrze: {len(umowy) - len(do_usuniecia)}.")
    print(f"Kopia bazy i pliki usuniętych umów: {kopia}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
