#!/usr/bin/env python3
"""Retencja danych wrażliwych.

    python skrypty/retencja.py                    # co by się usunęło
    python skrypty/retencja.py --usun             # faktyczne usunięcie
    python skrypty/retencja.py --ustaw-terminy    # wypełnij brakujące daty usunięcia

PESEL i numer dokumentu są potrzebne do wykupienia polisy i przygotowania
umowy. Po wyjeździe nie są potrzebne do niczego. Rejestr umów zostaje,
bo wymaga go obowiązek sprawozdawczy — znikają tylko dane wrażliwe.

Usunięcie w terminie jest obowiązkiem administratora danych, nie uprzejmością.
Ten skrypt to narzędzie, nie automat: domyślnie tylko pokazuje, co by zrobił.
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KORZEN))

from biuro import baza  # noqa: E402
from biuro.umowy import wyjazdy  # noqa: E402

# Ile dni po zakończeniu wyjazdu dane wrażliwe mają zniknąć.
# Miesiąc daje czas na rozliczenie ubezpieczenia i ewentualną reklamację.
DNI_PO_WYJAZDZIE = 30


def _na_date(tekst: str | None) -> date | None:
    if not tekst:
        return None
    for format_daty in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            from datetime import datetime
            return datetime.strptime(tekst.strip(), format_daty).date()
        except ValueError:
            continue
    return None


def ustaw_terminy() -> int:
    """Wypełnia usunac_po dla zgłoszeń, które mają umowę na wyjazd
    o znanej dacie zakończenia."""
    katalog = wyjazdy()
    ustawione = 0
    with baza.polaczenie() as conn:
        wiersze = conn.execute(
            """SELECT d.zgloszenie_id, u.wyjazd
               FROM dane_wrazliwe d
               JOIN umowy u ON u.zgloszenie_id = d.zgloszenie_id
               WHERE d.usunac_po IS NULL"""
        ).fetchall()

        for wiersz in wiersze:
            dane_wyjazdu = katalog.get(wiersz["wyjazd"], {})
            koniec = _na_date(str(dane_wyjazdu.get("termin_do", ""))) or _na_date(
                str(dane_wyjazdu.get("termin_od", ""))
            )
            if koniec is None:
                continue
            termin = koniec + timedelta(days=DNI_PO_WYJAZDZIE)
            conn.execute(
                "UPDATE dane_wrazliwe SET usunac_po = ? WHERE zgloszenie_id = ?",
                (termin.isoformat(), wiersz["zgloszenie_id"]),
            )
            ustawione += 1
    return ustawione


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--usun", action="store_true",
                        help="faktycznie usuń dane wrażliwe po terminie")
    parser.add_argument("--ustaw-terminy", action="store_true",
                        help="wypełnij brakujące daty usunięcia na podstawie wyjazdy.yaml")
    args = parser.parse_args()

    baza.inicjuj()
    dzisiaj = date.today()

    if args.ustaw_terminy:
        ile = ustaw_terminy()
        print(f"Ustawiono termin usunięcia dla {ile} zgłoszeń "
              f"({DNI_PO_WYJAZDZIE} dni po zakończeniu wyjazdu).")

    with baza.polaczenie() as conn:
        wszystkie = conn.execute(
            """SELECT d.zgloszenie_id, d.usunac_po, z.imie, z.nazwisko,
                      (SELECT u.wyjazd FROM umowy u
                       WHERE u.zgloszenie_id = d.zgloszenie_id LIMIT 1) AS wyjazd
               FROM dane_wrazliwe d
               JOIN zgloszenia z ON z.id = d.zgloszenie_id
               ORDER BY d.usunac_po IS NULL, d.usunac_po"""
        ).fetchall()

    if not wszystkie:
        print("Brak danych wrażliwych w bazie.")
        return 0

    po_terminie = []
    bez_terminu = []
    w_przyszlosci = []
    for wiersz in wszystkie:
        termin = _na_date(wiersz["usunac_po"])
        if termin is None:
            bez_terminu.append(wiersz)
        elif termin <= dzisiaj:
            po_terminie.append(wiersz)
        else:
            w_przyszlosci.append((wiersz, termin))

    print(f"\nDane wrażliwe w bazie: {len(wszystkie)} zgłoszeń\n")

    if po_terminie:
        print(f"DO USUNIĘCIA ({len(po_terminie)}):")
        for wiersz in po_terminie:
            print(f"  [{wiersz['zgloszenie_id']:3d}] {wiersz['imie'] or ''} "
                  f"{wiersz['nazwisko'] or ''} | wyjazd: {wiersz['wyjazd'] or '?'} "
                  f"| termin minął {wiersz['usunac_po']}")

    if bez_terminu:
        print(f"\nBEZ USTAWIONEGO TERMINU ({len(bez_terminu)}):")
        for wiersz in bez_terminu:
            print(f"  [{wiersz['zgloszenie_id']:3d}] {wiersz['imie'] or ''} "
                  f"{wiersz['nazwisko'] or ''} | wyjazd: {wiersz['wyjazd'] or 'brak umowy'}")
        print("\n  Uruchom z --ustaw-terminy, żeby wypełnić daty z wyjazdy.yaml.")
        print("  Zgłoszenia bez umowy nie dostaną terminu automatycznie.")

    if w_przyszlosci:
        najblizszy = min(termin for _, termin in w_przyszlosci)
        print(f"\nW TERMINIE ({len(w_przyszlosci)}), najbliższe usunięcie: {najblizszy}")

    if not po_terminie:
        print("\nNic do usunięcia.")
        return 0

    if not args.usun:
        print(f"\nTo był podglad. Uruchom z --usun, żeby usunąć {len(po_terminie)} wpisów.")
        return 0

    with baza.polaczenie() as conn:
        conn.executemany(
            "DELETE FROM dane_wrazliwe WHERE zgloszenie_id = ?",
            [(w["zgloszenie_id"],) for w in po_terminie],
        )
    print(f"\nUsunięto dane wrażliwe dla {len(po_terminie)} zgłoszeń.")
    print("Rejestr umów i dane kontaktowe zostały nietknięte — wymaga ich "
          "obowiązek sprawozdawczy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
