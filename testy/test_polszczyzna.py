#!/usr/bin/env python3
"""Testy odmiany liczebników.

    python testy/test_polszczyzna.py

Reguła ma jeden wyjątek, o który łatwo się potknąć: 12, 13 i 14 biorą formę
dopełniaczową („12 osób"), mimo że kończą się na 2, 3 i 4, a 22, 23 i 24 już
nie („22 osoby"). Bez tego wyjątku komunikat biura wyglądałby na usterkę
dokładnie wtedy, gdy grupa jest największa.
"""

import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KORZEN))

from biuro.polszczyzna import ile, odmien, osob, umow, wiadomosci  # noqa: E402


def main() -> int:
    bledy = 0

    def sprawdz(nazwa: str, otrzymano: str, oczekiwano: str) -> None:
        nonlocal bledy
        if otrzymano == oczekiwano:
            print(f"OK    {nazwa}: {otrzymano}")
        else:
            bledy += 1
            print(f"BŁĄD  {nazwa}: {otrzymano!r}, oczekiwano {oczekiwano!r}")

    sprawdz("zero", osob(0), "0 osób")
    sprawdz("jeden", osob(1), "1 osoba")
    sprawdz("dwa", osob(2), "2 osoby")
    sprawdz("cztery", osob(4), "4 osoby")
    sprawdz("pięć", osob(5), "5 osób")

    # nastki — wyjątek od reguły końcówki
    sprawdz("dwanaście", osob(12), "12 osób")
    sprawdz("trzynaście", osob(13), "13 osób")
    sprawdz("czternaście", osob(14), "14 osób")

    # dziesiątki wyższe — reguła końcówki znów działa
    sprawdz("dwadzieścia dwa", osob(22), "22 osoby")
    sprawdz("dwadzieścia pięć", osob(25), "25 osób")
    sprawdz("sto dwa", osob(102), "102 osoby")
    sprawdz("sto dwanaście", osob(112), "112 osób")

    sprawdz("umowy 1", umow(1), "1 umowa")
    sprawdz("umowy 3", umow(3), "3 umowy")
    sprawdz("umowy 11", umow(11), "11 umów")

    # wiadomość ma tę samą formę dla obu liczb mnogich
    sprawdz("wiadomości 2", wiadomosci(2), "2 wiadomości")
    sprawdz("wiadomości 7", wiadomosci(7), "7 wiadomości")
    sprawdz("wiadomość 1", wiadomosci(1), "1 wiadomość")

    sprawdz("samo słowo", odmien(3, "dzień", "dni", "dni"), "dni")
    sprawdz("własne słowa", ile(21, "plik", "pliki", "plików"), "21 plików")

    print()
    if bledy:
        print(f"BŁĘDY: {bledy}")
        return 1
    print("Wszystkie przypadki przeszły.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
