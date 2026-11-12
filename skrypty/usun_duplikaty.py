#!/usr/bin/env python3
"""Usuwa zduplikowane zgłoszenia — te same maile zapisane kilka razy.

    python skrypty/usun_duplikaty.py          # pokaż, co by usunął
    python skrypty/usun_duplikaty.py --zrob   # usuń

Skąd duplikaty. `zapisz_zgloszenie` wstawiało nowy wiersz przy każdym
przebiegu, więc powtórne przetworzenie skrzynki — przy kalibracji promptu
albo po błędzie — dokładało drugi zestaw tych samych osób. Od poprawki
zapis nadpisuje wiersz o tym samym `message_id`, ale wiersze powstałe
wcześniej zostają.

Dlaczego to nie jest kosmetyka: z rejestru umów powstaje wykaz dla UFG.
Zdublowane zgłoszenie znaczy zdublowaną umowę w dokumencie, który idzie
do urzędu.

Co zostaje, a co leci. Dla każdego `message_id` zostaje wiersz
o **najmniejszym id** — czyli ten z pierwszego przebiegu, ten, na który
mogą już wskazywać umowy i rezerwacje. Nowsze kopie są usuwane razem
ze swoimi danymi wrażliwymi.

Wiersz, do którego jest przypisana umowa albo rezerwacja, NIE jest usuwany
nigdy, nawet jako kopia — zgłoszenie z umową nie jest duplikatem do
wyrzucenia, tylko sytuacją do obejrzenia przez człowieka.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KORZEN))

from biuro import baza  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zrob", action="store_true", help="wykonaj usunięcie")
    args = parser.parse_args()

    baza.inicjuj()

    with baza.polaczenie() as conn:
        grupy = list(
            conn.execute(
                """SELECT message_id, COUNT(*) AS ile, MIN(id) AS zostaje
                   FROM zgloszenia
                   WHERE message_id IS NOT NULL AND message_id != ''
                   GROUP BY message_id
                   HAVING COUNT(*) > 1
                   ORDER BY MIN(id)"""
            )
        )
        bez_id = conn.execute(
            "SELECT COUNT(*) FROM zgloszenia WHERE message_id IS NULL OR message_id = ''"
        ).fetchone()[0]

    if not grupy:
        print("Brak duplikatów.")
        if bez_id:
            print(f"({bez_id} zgłoszeń bez message_id — wpisane ręcznie albo "
                  "z innego źródła, nie da się ich porównać po mailu.)")
        return 0

    do_usuniecia: list[int] = []
    chronione: list[tuple[int, str]] = []

    with baza.polaczenie() as conn:
        for grupa in grupy:
            kopie = [
                int(r[0]) for r in conn.execute(
                    "SELECT id FROM zgloszenia WHERE message_id = ? AND id != ? ORDER BY id",
                    (grupa["message_id"], grupa["zostaje"]),
                )
            ]
            for zid in kopie:
                umowy = conn.execute(
                    "SELECT COUNT(*) FROM umowy WHERE zgloszenie_id = ?", (zid,)
                ).fetchone()[0]
                rez = conn.execute(
                    "SELECT COUNT(*) FROM rezerwacje WHERE zgloszenie_id = ?", (zid,)
                ).fetchone()[0]
                if umowy or rez:
                    chronione.append(
                        (zid, f"ma {umowy} umów i {rez} rezerwacji — nie usuwam")
                    )
                else:
                    do_usuniecia.append(zid)

            nazwa = conn.execute(
                "SELECT imie, nazwisko FROM zgloszenia WHERE id = ?", (grupa["zostaje"],)
            ).fetchone()
            osoba = " ".join(x for x in (nazwa["imie"], nazwa["nazwisko"]) if x) or "?"
            print(f"  {osoba:32} {grupa['ile']}x  zostaje [{grupa['zostaje']}], "
                  f"kopie: {kopie or 'brak'}")

    print()
    print(f"Grup z duplikatami: {len(grupy)}")
    print(f"Wierszy do usunięcia: {len(do_usuniecia)}")
    if chronione:
        print(f"Chronionych (mają umowę albo rezerwację): {len(chronione)}")
        for zid, powod in chronione:
            print(f"  [{zid}] {powod}")

    if not args.zrob:
        print("\nTo był podgląd. Nic nie zmieniłam. Żeby wykonać:")
        print("  python skrypty/usun_duplikaty.py --zrob")
        return 0

    if not do_usuniecia:
        print("\nNie ma czego usuwać.")
        return 0

    with baza.polaczenie() as conn:
        znaki = ",".join("?" * len(do_usuniecia))
        conn.execute(
            f"DELETE FROM dane_wrazliwe WHERE zgloszenie_id IN ({znaki})",
            do_usuniecia,
        )
        conn.execute(
            f"DELETE FROM zgloszenia WHERE id IN ({znaki})", do_usuniecia
        )

    print(f"\nUsunięte: {len(do_usuniecia)} zgłoszeń razem z danymi wrażliwymi.")
    print("Sprawdź stan: python skrypty/zrob_umowe.py --lista")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
