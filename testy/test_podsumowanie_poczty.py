#!/usr/bin/env python3
"""Testy podsumowania przebiegu poczty.

    python testy/test_podsumowanie_poczty.py

Podsumowanie to jedyna rzecz, którą widzi osoba klikająca „Sprawdź pocztę".
Wcześniej był to surowy słownik liczników — „pobrane: 9, pominiete: 8" —
z którego nie dało się wyczytać ani co przyszło, ani co z tego powstało,
ani dlaczego nowa jest tylko jedna wiadomość z dziewięciu.

Tu sprawdzamy, że na liście są WSZYSTKIE wiadomości z okna, także te
obsłużone wcześniej, że widać rodzaj każdej i że wiadomości wymagające
reakcji człowieka są oznaczone.
"""

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KORZEN))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(KORZEN / "skrypty"))

import baza_testowa  # noqa: E402,F401

from biuro.mail.pipeline import Wiersz, WynikPrzebiegu  # noqa: E402

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "sprawdz_maile", KORZEN / "skrypty" / "sprawdz_maile.py"
)
sprawdz_maile = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sprawdz_maile)


def przyklad() -> WynikPrzebiegu:
    return WynikPrzebiegu(
        liczby={
            "w_skrzynce": 214, "w_oknie": 9, "pobrane": 9, "pominiete": 7,
            "zgloszenia": 1, "dane_do_umowy": 1, "akceptacje": 0,
            "rezerwacje": 0, "do_czlowieka": 1, "do_weryfikacji": 0,
            "drafty": 1, "bledy": 0, "przetworzone": 2, "odlozone": 0,
        },
        wiadomosci=[
            Wiersz(od="Beata L", rodzaj="formularz",
                   temat="Zgłoszenie na wyjazd — Walia", wczesniej=True),
            Wiersz(od="Marek W", rodzaj="dane_do_umowy",
                   temat="Dane do umowy", wczesniej=False, draft=True),
            Wiersz(od="Ewa K", rodzaj="pytanie",
                   temat="Czy można przesunąć termin wpłaty?",
                   wczesniej=False, do_czlowieka=True),
        ],
    )


def main() -> int:
    bledy = 0

    def sprawdz(nazwa: str, warunek: bool, szczegol: str = "") -> None:
        nonlocal bledy
        if warunek:
            print(f"OK    {nazwa}")
        else:
            bledy += 1
            print(f"BŁĄD  {nazwa}   {szczegol}")

    bufor = io.StringIO()
    with redirect_stdout(bufor):
        sprawdz_maile.wypisz_podsumowanie(przyklad(), dni=3, na_sucho=False)
    tekst = bufor.getvalue()

    sprawdz("podaje liczbę wiadomości w skrzynce", "214" in tekst)
    sprawdz("podaje liczbę wiadomości w oknie czasu",
            "ostatnich 3 dni" in tekst and "9" in tekst)
    sprawdz("rozdziela obsłużone wcześniej od obsłużonych teraz",
            "obsłużone wcześniej" in tekst and "obsłużone teraz" in tekst)

    for kto in ("Beata L", "Marek W", "Ewa K"):
        sprawdz(f"na liście jest {kto}", kto in tekst)
    sprawdz("wiadomość obsłużona wcześniej też jest na liście",
            "Zgłoszenie na wyjazd — Walia" in tekst)

    sprawdz("rodzaj po ludzku, nie kluczem",
            "zgłoszenie z formularza" in tekst and "dane do umowy" in tekst,
            tekst)
    sprawdz("widać, że draft powstał", "draft gotowy" in tekst)
    sprawdz("widać, co wymaga reakcji człowieka", "DO CIEBIE" in tekst)

    sprawdz("podaje liczbę draftów",
            "robocze wersje odpowiedzi:    1" in tekst, tekst)
    sprawdz("podaje liczbę zapisanych zgłoszeń",
            "zgłoszenia zapisane w bazie:  1" in tekst, tekst)
    sprawdz("ma sekcję z tym, co wymaga uwagi",
            "Wymaga Twojej uwagi" in tekst)
    sprawdz("liczebnik odmieniony poprawnie przy jednej wiadomości",
            "1 wiadomość oznaczona do Ciebie" in tekst, tekst)

    for ile, oczekiwane in ((1, "1 zgłoszenie"), (3, "3 zgłoszenia"),
                            (5, "5 zgłoszeń"), (12, "12 zgłoszeń"),
                            (22, "22 zgłoszenia"), (25, "25 zgłoszeń")):
        sprawdz(f"odmiana dla {ile}",
                sprawdz_maile.odmien(ile, "zgłoszenie", "zgłoszenia",
                                     "zgłoszeń") == oczekiwane,
                sprawdz_maile.odmien(ile, "zgłoszenie", "zgłoszenia", "zgłoszeń"))

    # Tryb na sucho musi być widoczny — inaczej łatwo uznać, że coś zapisano.
    bufor = io.StringIO()
    with redirect_stdout(bufor):
        sprawdz_maile.wypisz_podsumowanie(przyklad(), dni=7, na_sucho=True)
    sprawdz("tryb na sucho jest zaznaczony",
            "nic nie zostało zapisane" in bufor.getvalue())

    # Pusty przebieg nie może wyglądać jak awaria.
    pusty = WynikPrzebiegu(
        liczby={k: 0 for k in przyklad().liczby}, wiadomosci=[]
    )
    bufor = io.StringIO()
    with redirect_stdout(bufor):
        sprawdz_maile.wypisz_podsumowanie(pusty, dni=3, na_sucho=False)
    tekst = bufor.getvalue()
    sprawdz("pusty przebieg nie wypisuje listy", "Wiadomości:" not in tekst)
    sprawdz("pusty przebieg nie wypisuje sekcji uwag",
            "Wymaga Twojej uwagi" not in tekst)
    sprawdz("pusty przebieg nadal podaje liczby", "Co z tego powstało" in tekst)

    # Odłożone wiadomości muszą być widoczne: to one znikały po cichu.
    z_odlozonymi = przyklad()
    z_odlozonymi.liczby["odlozone"] = 12
    bufor = io.StringIO()
    with redirect_stdout(bufor):
        sprawdz_maile.wypisz_podsumowanie(z_odlozonymi, dni=3, na_sucho=False)
    sprawdz("odłożone wiadomości są widoczne",
            "czekają na kolejny przebieg: 12" in bufor.getvalue())

    print()
    if bledy:
        print(f"BŁĘDY: {bledy}")
        return 1
    print("Wszystkie przypadki przeszły.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
