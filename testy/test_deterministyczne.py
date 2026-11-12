#!/usr/bin/env python3
"""Testy warstwy deterministycznej. Czysty Python, bez zależności.

    python testy/test_deterministyczne.py

Każdy przypadek wyszedł z pomiaru albo z błędu, który faktycznie wystąpił.
Jeśli dopisujesz nowy wzorzec maila, dopisz tu przypadek.

Numery PESEL w tych testach mają poprawną sumę kontrolną, ale zakodowaną datę
urodzenia 00-00, która nie istnieje w żadnym wieku, więc nie mogą należeć do
żadnej osoby. Jeśli dopisujesz nowy przypadek, zrób tak samo — nie bierz numeru
z prawdziwego zgłoszenia.

Od dopisania walidacji kalendarzowej te numery wychodzą jako `[weryf.]`, czyli
zachowane, ale niezweryfikowane — i tak ma być, bo numer kodujący 00-00 jest
nieprawidłowy. Testy sprawdzają, czy wartość jest wyciągnięta pod właściwe pole,
nie czy przechodzi walidację.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from biuro.ekstrakcja import RaportEkstrakcji, zloz_wrazliwe  # noqa: E402
from biuro.schemas import DaneWrazliwe, Uczestnik  # noqa: E402
from biuro.deterministyczne import (  # noqa: E402
    data_istnieje,
    data_z_peselu,
    ustal,
    warunki_deterministyczne,
)

PRZYPADKI: list[tuple[str, str, dict[str, str | None]]] = [
    (
        "pełne zgłoszenie z formularza",
        """Imie: Tomasz
Nazwisko: Nowak
Kod pocztowy: 40-001
Numer telefonu: +48 601 234 567
Adres email: tomasz@example.com
PESEL: 44000001357""",
        # prefiks kraju z wejścia zostaje w zapisie znormalizowanym
        {"pesel": "44000001357", "telefon": "+48 601 234 567",
         "kod_pocztowy": "40-001", "email": "tomasz@example.com"},
    ),
    (
        "PESEL z literówką i telefon w tej samej linii",
        "PESEL: 44000001356, tel 601234567",
        {"pesel": "44000001356", "telefon": "601234567"},
    ),
    (
        "brak PESEL-u, jest telefon",
        "Dzien dobry, nazywam sie Jan Kowalski, telefon 601 234 567, mail jan@example.com",
        {"pesel": None, "telefon": "601234567", "email": "jan@example.com"},
    ),
    (
        "dziewięć cyfr podpisanych jako PESEL to zły kształt",
        "PESEL: 601234567",
        {"pesel": None},
    ),
    (
        "NIP i numer konta nie są brane za PESEL ani telefon",
        "NIP: 6342801402\nKonto: 61109010140000071219812874\nPESEL: 44000001357",
        {"pesel": "44000001357", "telefon": None},
    ),
    (
        "data urodzenia nie jest brana za telefon",
        "Data urodzenia: 01.01.1944\nPESEL: 44000001357\nTel: 601-234-567",
        {"pesel": "44000001357", "telefon": "601234567"},
    ),
    (
        "tekst swobodny, etykieta stoi po liczbie",
        "Chcialbym jechac na Walie. 44000001357 to moj pesel, dzwoncie 601234567.",
        {"pesel": "44000001357", "telefon": "601234567"},
    ),
    (
        "numer z prefiksem kraju bez plusa",
        "Kontakt: 48 601 234 567",
        {"telefon": "+48 601 234 567"},
    ),
    (
        "pusty tekst nie wywala się",
        "",
        {"pesel": None, "telefon": None, "email": None},
    ),
]


def _cyfry(tekst: str | None) -> str | None:
    return re.sub(r"\D", "", tekst) if tekst else tekst


def main() -> int:
    bledy = 0
    for nazwa, tekst, oczekiwane in PRZYPADKI:
        wynik = ustal(tekst)
        otrzymane = wynik.wartosci()
        niezgodnosci = []

        for pole, wartosc in oczekiwane.items():
            if wartosc is None:
                if pole in otrzymane:
                    niezgodnosci.append(f"{pole}: oczekiwano braku, jest {otrzymane[pole]!r}")
                continue
            if pole not in otrzymane:
                niezgodnosci.append(f"{pole}: brak, oczekiwano {wartosc!r}")
                continue
            if pole in {"pesel", "telefon"}:
                zgoda = _cyfry(otrzymane[pole]) == _cyfry(wartosc)
            else:
                zgoda = otrzymane[pole] == wartosc
            if not zgoda:
                niezgodnosci.append(f"{pole}: {otrzymane[pole]!r} != {wartosc!r}")

        if niezgodnosci:
            bledy += 1
            print(f"BŁĄD  {nazwa}")
            for n in niezgodnosci:
                print(f"        {n}")
            print(f"        ustalono: {otrzymane}")
            if wynik.odrzucone:
                print(f"        odrzucono: {wynik.odrzucone}")
        else:
            szczegoly = ", ".join(
                f"{k}={v}" + ("" if wynik.ustalenia[k].zweryfikowane else " [weryf.]")
                for k, v in otrzymane.items()
            )
            print(f"OK    {nazwa}")
            if szczegoly:
                print(f"        {szczegoly}")

    bledy += sprawdz_daty()
    bledy += sprawdz_dane_do_umowy()

    print(f"\n{len(PRZYPADKI) - bledy}/{len(PRZYPADKI)} przypadków przeszło")
    return 1 if bledy else 0


def sprawdz_dane_do_umowy() -> int:
    """Dane wrażliwe składane dla umowy: z regexu, nie od modelu.

    Ten test istnieje, bo jego brak kosztował osiemnaście błędów na prawdziwej
    poczcie. Ścieżka formularza nie zapisywała danych wrażliwych w ogóle,
    więc zwalidowany PESEL był wyrzucany i umowy nie dało się wystawić dla
    żadnego zgłoszenia ze strony. Poprawka weszła bez testu, a potem
    rozjechane wersje dwóch plików przeszły pełny zestaw i wywaliły się
    dopiero na pierwszym mailu.
    """
    print("\n--- dane wrażliwe do umowy ---")
    bledy = 0

    def sprawdz(nazwa: str, warunek: bool, szczegol: str = "") -> None:
        nonlocal bledy
        if warunek:
            print(f"OK    {nazwa}")
        else:
            bledy += 1
            print(f"BŁĄD  {nazwa}   {szczegol}")

    sprawdz("raport ekstrakcji ma pole na dane do umowy",
            "wrazliwe" in RaportEkstrakcji.__dataclass_fields__,
            str(list(RaportEkstrakcji.__dataclass_fields__)))

    tekst = (
        "Imię i nazwisko: Jan Przykładowy\n"
        "PESEL: 44000001357\n"
        "Data urodzenia: 1944-01-01\n"
        "Kod pocztowy: 40-001\n"
        "Adres e-mail: jan@example.com\n"
    )
    wynik = ustal(tekst)
    uczestnik = Uczestnik(
        imie="Jan", nazwisko="Przykładowy", numer_dokumentu="ABC123456",
        ulica="Kwiatowa 1", miasto="Katowice", kod_pocztowy="99-999",
    )
    dane = zloz_wrazliwe(wynik, uczestnik)

    sprawdz("PESEL pochodzi z warstwy deterministycznej",
            dane.pesel == "44000001357", str(dane.pesel))
    sprawdz("data urodzenia pochodzi z warstwy deterministycznej",
            dane.data_urodzenia == "1944-01-01", str(dane.data_urodzenia))
    # Kod pocztowy z regexu bije kod przepisany przez model — model podał tu
    # 99-999, w treści jest 40-001.
    sprawdz("zwalidowany kod pocztowy bije wartość od modelu",
            dane.kod_pocztowy == "40-001", str(dane.kod_pocztowy))
    sprawdz("numer dokumentu bierzemy od modelu, bo regex go nie zna",
            dane.numer_dokumentu == "ABC123456", str(dane.numer_dokumentu))
    sprawdz("adres i nazwisko przepisane",
            dane.ulica == "Kwiatowa 1" and dane.nazwisko == "Przykładowy",
            f"{dane.ulica} / {dane.nazwisko}")

    # Numer dokumentu bez dopisków. Formularz podaje go razem z datą
    # ważności w jednej linii, model przepisuje całość, a wtedy limit
    # długości pola odrzucał cały rekord — razem z poprawnym numerem.
    for wejscie, oczekiwane in (
        ("ES 7742019, ważny do 28.03.2029", "ES 7742019"),
        ("paszport ES 7742019, ważny do 28.03.2029", "ES 7742019"),
        ("dowód osobisty ABC123456", "ABC123456"),
        ("AB1234567, ważny do 2031-11-18", "AB1234567"),
        ("ABC123456", "ABC123456"),
    ):
        wynik_num = DaneWrazliwe(numer_dokumentu=wejscie).numer_dokumentu
        sprawdz(f"numer dokumentu: {wejscie[:34]!r}",
                wynik_num == oczekiwane, f"-> {wynik_num!r}, oczekiwano {oczekiwane!r}")

    # Brak danych w treści nie ma być zastąpiony niczym.
    puste = zloz_wrazliwe(ustal("Dzień dobry, pytanie o termin."), Uczestnik())
    sprawdz("bez danych w treści pola zostają puste",
            puste.pesel is None and puste.data_urodzenia is None,
            f"{puste.pesel} / {puste.data_urodzenia}")
    sprawdz("brak PESEL-u i dokumentu to brak gotowości do umowy",
            "pesel" in puste.braki_do_umowy(), str(puste.braki_do_umowy()))

    return bledy


def sprawdz_daty() -> int:
    """Walidacja kalendarzowa daty urodzenia i zgodności z PESEL-em.

    Wszystkie trzy przypadki wyszły z pierwszego prawdziwego zgłoszenia
    w skrzynce: `Data urodzenia: 1978-04-33` razem z numerem `780433...`,
    który ma poprawną cyfrę kontrolną i koduje ten sam nieistniejący dzień.
    Suma kontrolna liczy się z cyfr, nie z kalendarza, więc do tej pory
    przechodziło jedno i drugie.
    """
    print("\n--- data urodzenia: kalendarz i zgodność z PESEL-em ---")
    bledy = 0

    def sprawdz(nazwa: str, warunek: bool, szczegol: str = "") -> None:
        nonlocal bledy
        if warunek:
            print(f"OK    {nazwa}")
        else:
            bledy += 1
            print(f"BŁĄD  {nazwa}   {szczegol}")

    sprawdz("33 kwietnia nie istnieje", not data_istnieje(1978, 4, 33))
    sprawdz("30 lutego nie istnieje", not data_istnieje(2026, 2, 30))
    sprawdz("29 lutego 2024 istnieje (rok przestępny)", data_istnieje(2024, 2, 29))
    sprawdz("29 lutego 2026 nie istnieje", not data_istnieje(2026, 2, 29))
    sprawdz("3 kwietnia istnieje", data_istnieje(1978, 4, 3))

    sprawdz("PESEL kodujący 33 kwietnia nie daje daty",
            data_z_peselu("78043364614") is None)

    w = ustal("Data urodzenia: 1978-04-33\nPESEL: 78043364614")
    sprawdz("nieistniejąca data trafia do odrzuconych",
            any("nie ma takiej daty" in o for o in w.odrzucone), str(w.odrzucone))
    sprawdz("data o złym kształcie nie trafia do ustaleń",
            "data_urodzenia" not in w.ustalenia)
    sprawdz("PESEL z nieistniejącą datą zostaje, ale niezweryfikowany",
            "pesel" in w.ustalenia and not w.ustalenia["pesel"].zweryfikowane)
    sprawdz("oba przypadki dają warunek flagi do człowieka",
            "dane_zlego_ksztaltu" in warunki_deterministyczne(w),
            str(warunki_deterministyczne(w)))

    # Zapis dzień.miesiąc.rok też musi być rozpoznany — formularz na stronie
    # używa myślnika, ale klienci piszą w mailach kropkami.
    w2 = ustal("Data urodzenia: 33.04.1978")
    sprawdz("zapis z kropkami też jest sprawdzany",
            any("nie ma takiej daty" in o for o in w2.odrzucone), str(w2.odrzucone))

    # Brak daty w treści nie może nic zgłaszać.
    w3 = ustal("Adres email: ktos@example.com")
    sprawdz("brak daty nie generuje ostrzeżeń",
            not w3.odrzucone and not w3.do_weryfikacji,
            f"{w3.odrzucone} {w3.do_weryfikacji}")
    sprawdz("brak danych wrażliwych nie daje warunku flagi",
            warunki_deterministyczne(w3) == [])

    return bledy


if __name__ == "__main__":
    raise SystemExit(main())
