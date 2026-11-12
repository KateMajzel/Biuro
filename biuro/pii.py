"""Maskowanie danych wrażliwych.

Uczestnicy odsyłają mailem PESEL, datę urodzenia i numer dokumentu, bo bez
tego nie da się wykupić polisy ani przygotować umowy. Te dane są potrzebne
aplikacji, ale nie są potrzebne nigdzie poza bazą i szablonem umowy.

Zasady:
- do konsoli i logów idzie tylko wersja zamaskowana
- do bazy wiedzy i do promptu pisania odpowiedzi nie idą wcale
- draft odpowiedzi nigdy ich nie powtarza

Przy modelu lokalnym to wszystko zostaje na jednym komputerze. W rozwiązaniu
chmurowym PESEL uczestnika poszedłby do zewnętrznego dostawcy.
"""

from __future__ import annotations

import re

PESEL = re.compile(r"\b\d{11}\b")
DOKUMENT = re.compile(r"\b[A-Z]{2,3}\s?\d{6,7}\b")          # dowód / paszport
DATA_URODZENIA = re.compile(r"\b\d{2}[.\-/]\d{2}[.\-/]\d{4}\b")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?\d{4}){4,7}\b")
KARTA = re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")


def zamaskuj_kod(kod: str | None) -> str:
    """Kod do skrytki na klucze albo do drzwi to zabezpieczenie obiektu,
    nie dane osobowe, ale do konsoli i tak nie ma po co trafiać."""
    if not kod:
        return ""
    return f"{kod[0]}{'•' * max(len(kod) - 1, 3)}"


def zamaskuj(tekst: str | None, daty: bool = True) -> str:
    """Podmienia dane wrażliwe na znaczniki. Używaj przy każdym print()
    i przy każdym zapisie do logu.

    daty=False zostawia daty widoczne. Potrzebne tam, gdzie człowiek czyta
    podglad treści i musi widzieć termin wyjazdu — wzorzec daty nie rozróżnia
    `12-19.02.2027` od daty urodzenia, więc przy domyślnym maskowaniu termin
    wyjazdu znika razem z nią. W ścieżce pisania draftu zostaw domyślne True:
    tam data urodzenia nie ma po co trafiać do modelu.
    """
    if not tekst:
        return ""
    wynik = KARTA.sub("[KARTA]", tekst)
    wynik = IBAN.sub("[IBAN]", wynik)
    wynik = PESEL.sub("[PESEL]", wynik)
    wynik = DOKUMENT.sub("[DOKUMENT]", wynik)
    if daty:
        wynik = DATA_URODZENIA.sub("[DATA-UR]", wynik)
    return wynik


def zawiera_dane_wrazliwe(tekst: str | None) -> bool:
    """Czy w tekście jest coś, czego nie wolno wkładać do promptu
    ani do bazy wiedzy."""
    if not tekst:
        return False
    return any(w.search(tekst) for w in (PESEL, DOKUMENT, IBAN, KARTA))


def oczysc_dla_promptu(tekst: str | None) -> str:
    """Treść maila przed włożeniem do promptu pisania odpowiedzi.

    Model ma odpowiedzieć na pytanie, a nie recytować PESEL uczestnika
    w treści odpowiedzi. Maskujemy, zanim cokolwiek zobaczy.
    """
    return zamaskuj(tekst)
