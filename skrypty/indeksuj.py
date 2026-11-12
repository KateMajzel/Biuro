#!/usr/bin/env python3
"""Buduje indeks bazy wiedzy z folderu wiedza/.

Uruchamiaj po każdej zmianie w plikach bazy wiedzy.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from biuro import baza  # noqa: E402
from biuro.rag import kontekst, zbuduj_indeks  # noqa: E402


def main() -> int:
    baza.inicjuj()
    liczba = zbuduj_indeks()

    # szybki test sensowności indeksu
    print("\nTest wyszukiwania:")
    for pytanie in ("co zabrać na wyjazd", "ile kosztuje wyprawa", "kiedy jest termin"):
        blok, zrodla = kontekst(pytanie, ile=3)
        status = ", ".join(zrodla) if zrodla else "BRAK TRAFIEŃ"
        print(f"  '{pytanie}' -> {status}")

    print(f"\nGotowe: {liczba} fragmentów.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
