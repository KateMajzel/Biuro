#!/usr/bin/env python3
"""Testy dopasowania maila do zgłoszenia. Baza testowa, bez sieci.

    python testy/test_dopasowanie_zgloszen.py

Skąd ten plik. Jedna osoba może zgłosić się na kilka wyjazdów i każdy taki
wyjazd jest osobnym zgłoszeniem i osobną umową. Dopasowanie brało wcześniej
NAJNOWSZE zgłoszenie z danego adresu, więc uczestnik zapisany na dwa wyjazdy,
dosyłając PESEL do pierwszej umowy, wpisywał go do drugiego zgłoszenia.
Zapis danych wrażliwych działa przez INSERT OR REPLACE, więc kolejny mail
podmieniłby dane po cichu: jedna umowa bez numeru, druga z numerem
przysłanym w zupełnie innej sprawie.

Reguła, której pilnują te testy: przy kilku kandydatach rozstrzyga kierunek
wymieniony w treści, a gdy to nie wystarcza, dopasowania NIE MA. Zgłoszenie
bez dopasowania trafia do człowieka; PESEL w niewłaściwej umowie nie trafia
nigdzie, dopóki ktoś tego nie zauważy.
"""

import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KORZEN))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from baza_testowa import wymagaj_bazy_testowej  # noqa: E402

wymagaj_bazy_testowej()

from biuro import baza  # noqa: E402
from biuro.schemas import Uczestnik  # noqa: E402

ADRES = "uczestnik@example.com"


def zgloszenie(kierunek: str, message_id: str, nazwisko: str = "Testowy") -> int:
    return baza.zapisz_zgloszenie(
        Uczestnik(
            imie="Jan", nazwisko=nazwisko, email=ADRES,
            telefon="601234567", wyjazd_kierunek=kierunek,
        ),
        "formularz",
        message_id,
    )


def main() -> int:
    baza.inicjuj()
    with baza.polaczenie() as conn:
        conn.execute("DELETE FROM dane_wrazliwe")
        conn.execute("DELETE FROM zgloszenia")

    bledy = 0

    def sprawdz(nazwa: str, warunek: bool, szczegol: str = "") -> None:
        nonlocal bledy
        if warunek:
            print(f"OK    {nazwa}")
        else:
            bledy += 1
            print(f"BŁĄD  {nazwa}   {szczegol}")

    # 1. Jedno zgłoszenie — dopasowanie bez żadnych wątpliwości.
    lofoty = zgloszenie("Lofoty", "<a@example.com>")
    d = baza.dopasuj_zgloszenie(ADRES, None, "Przesyłam dane do umowy.")
    sprawdz("jedno zgłoszenie dopasowuje się wprost", d.id == lofoty,
            f"{d.id} != {lofoty}")
    sprawdz("przy jednym kandydacie nie ma powodu do raportowania",
            d.powod == "", d.powod)

    # 2. Drugi wyjazd tej samej osoby — to NIE jest duplikat.
    svalbard = zgloszenie("Svalbard", "<b@example.com>")
    sprawdz("drugi wyjazd to osobne zgłoszenie", svalbard != lofoty,
            f"{svalbard} == {lofoty}")

    # 3. Dwa zgłoszenia, treść nie mówi o który chodzi — BRAK dopasowania.
    d = baza.dopasuj_zgloszenie(ADRES, None, "Przesyłam dane do umowy.")
    sprawdz("przy dwóch zgłoszeniach i niejasnej treści nie zgadujemy",
            d.id is None, f"dopasowano {d.id}")
    sprawdz("zwracana jest lista kandydatów", len(d.kandydaci) == 2,
            str(d.kandydaci))
    sprawdz("podany jest powód braku dopasowania", "kilka zgłoszeń" in d.powod,
            d.powod)

    # 4. Treść wymienia kierunek — rozstrzyga.
    d = baza.dopasuj_zgloszenie(ADRES, None, "Dane do umowy na Lofoty, PESEL w załączniku.")
    sprawdz("kierunek w treści rozstrzyga dopasowanie", d.id == lofoty,
            f"{d.id} != {lofoty}")
    sprawdz("powód mówi, czym rozstrzygnięto", "Lofoty" in d.powod, d.powod)

    d = baza.dopasuj_zgloszenie(ADRES, None, "W sprawie wyjazdu na Svalbard — dosyłam paszport.")
    sprawdz("ten sam mechanizm dla drugiego wyjazdu", d.id == svalbard,
            f"{d.id} != {svalbard}")

    # 5. Treść wymienia OBA kierunki — znowu nie zgadujemy.
    d = baza.dopasuj_zgloszenie(
        ADRES, None, "Jadę na Lofoty i na Svalbard, przesyłam dane."
    )
    sprawdz("dwa kierunki w treści to nadal brak rozstrzygnięcia",
            d.id is None, f"dopasowano {d.id}")

    # 6. Nieznany adres — brak kandydatów, bez powodu do raportowania.
    d = baza.dopasuj_zgloszenie("nikt@example.com", None, "cokolwiek")
    sprawdz("nieznany adres nie dopasowuje się do niczego", d.id is None)
    sprawdz("brak kandydatów to brak powodu", d.powod == "", d.powod)

    # 7. Dopasowanie po nazwisku, gdy adres nie pasuje — ta sama reguła.
    d = baza.dopasuj_zgloszenie("inny@example.com", "Testowy", "Dane na Lofoty")
    sprawdz("nazwisko też rozstrzyga po kierunku", d.id == lofoty,
            f"{d.id} != {lofoty}")

    # 8. Dane wrażliwe nie podmieniają się między wyjazdami.
    #    To jest konsekwencja, z której powstał cały ten plik.
    from biuro.schemas import DaneWrazliwe
    baza.zapisz_dane_wrazliwe(lofoty, DaneWrazliwe(pesel="44000001357"))
    baza.zapisz_dane_wrazliwe(svalbard, DaneWrazliwe(pesel="44000001356"))
    with baza.polaczenie() as conn:
        ile = conn.execute("SELECT COUNT(*) FROM dane_wrazliwe").fetchone()[0]
        osobno = conn.execute(
            "SELECT COUNT(DISTINCT zgloszenie_id) FROM dane_wrazliwe"
        ).fetchone()[0]
    sprawdz("każdy wyjazd ma własne dane wrażliwe", ile == 2 and osobno == 2,
            f"wierszy {ile}, zgłoszeń {osobno}")

    print()
    if bledy:
        print(f"BŁĘDY: {bledy}")
        return 1
    print("Wszystkie przypadki przeszły.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
