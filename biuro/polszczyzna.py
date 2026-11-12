"""Odmiana liczebników. Jedna reguła zamiast „1 osób" w pięciu miejscach.

Polski ma trzy formy przy liczbie: pojedynczą (1 osoba), mnogą dla dwóch,
trzech i czterech (2 osoby) i dopełniaczową dla reszty (5 osób). Wyjątek
dotyczy nastek: 12, 13, 14 biorą formę dopełniaczową, mimo że kończą się
na 2, 3, 4.

Komunikaty biura czyta człowiek i mają brzmieć jak zdanie, a nie jak wydruk
z bazy. „Lista uczestników — Walia: 1 osób" wygląda na usterkę programu
nawet wtedy, gdy liczba jest poprawna.
"""

from __future__ import annotations


def odmien(liczba: int, jedna: str, dwie: str, wiele: str) -> str:
    """Sama forma słowa, bez liczby."""
    if abs(liczba) == 1:
        return jedna
    reszta_dziesiatek = abs(liczba) % 10
    reszta_setek = abs(liczba) % 100
    if 2 <= reszta_dziesiatek <= 4 and not 12 <= reszta_setek <= 14:
        return dwie
    return wiele


def ile(liczba: int, jedna: str, dwie: str, wiele: str) -> str:
    """Liczba razem z odmienionym słowem: 'ile(3, ...)' → '3 osoby'."""
    return f"{liczba} {odmien(liczba, jedna, dwie, wiele)}"


def osob(liczba: int) -> str:
    return ile(liczba, "osoba", "osoby", "osób")


def umow(liczba: int) -> str:
    return ile(liczba, "umowa", "umowy", "umów")


def wiadomosci(liczba: int) -> str:
    return ile(liczba, "wiadomość", "wiadomości", "wiadomości")


def zgloszen(liczba: int) -> str:
    return ile(liczba, "zgłoszenie", "zgłoszenia", "zgłoszeń")


def odpowiedzi(liczba: int) -> str:
    return ile(liczba, "odpowiedź", "odpowiedzi", "odpowiedzi")


def dni(liczba: int) -> str:
    return ile(liczba, "dzień", "dni", "dni")
