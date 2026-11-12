#!/usr/bin/env python3
"""Testy składania promptów, bez modelu i bez sieci.

    python testy/test_skladanie_promptow.py

Po co: błąd w składaniu promptu jest cichy. Model odpowiada, JSON się parsuje,
nikt nic nie zauważa, a jakość spada, bo brakuje jednej sekcji albo dane
wrażliwe weszły tam, gdzie nie powinny. Te testy podstawiają klienta modelu
i patrzą, co dokładnie dostałby na wejściu.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# MUSI być przed importami z biuro: przestawia bazę na testową,
# żeby czyszczenie tabel nie dotknęło danych produkcyjnych.
import baza_testowa  # noqa: E402

baza_testowa.wymagaj_bazy_testowej()
baza_testowa.wyczysc()

from biuro import baza, historia, llm, odprawa, rag  # noqa: E402
from biuro.mail import pipeline  # noqa: E402
from biuro.mail.imap_client import Mail  # noqa: E402
from biuro.schemas import DaneWrazliwe, ProjektOdpowiedzi, Uczestnik  # noqa: E402

PRZECHWYCONE: list[str] = []


def _udawany_chat_json(tresc, schemat, system=None, *, maly=True, proby=3,
                       limit_tokenow=None):
    """Zapisuje prompt i zwraca minimalny poprawny obiekt.

    `limit_tokenow` przyjmujemy, bo projekt odpowiedzi prosi o większy budżet
    niż klasyfikacja — podpis atrapy musi nadążać za prawdziwym.
    """
    PRZECHWYCONE.append(tresc)
    return ProjektOdpowiedzi(
        temat="Re: test", tresc="treść testowa", uzyte_zrodla=["test"], pewnosc=0.9
    )


def _udawany_kontekst(zapytanie, ile=None, prog=0.35):
    return ("[fragment bazy wiedzy: zbiórka o 9:00 w Katowicach]", ["test.md / Zbiórka"])


def przygotuj_baze() -> int:
    baza.inicjuj()
    with baza.polaczenie() as conn:
        conn.execute("DELETE FROM dane_wrazliwe")
        conn.execute("DELETE FROM umowy")
        conn.execute("DELETE FROM zgloszenia")
    uczestnik = Uczestnik(
        imie="Tomasz", nazwisko="Nowak", email="tomasz@example.com",
        telefon="601 234 567", kraj_region="Polska", ulica="Kwiatowa 1",
        kod_pocztowy="40-001", miasto="Katowice", liczba_osob=2,
        dodatkowe_informacje="dieta wegetariańska",
        wymagania_innych_osob="partner: bez laktozy",
    )
    zid = baza.zapisz_zgloszenie(uczestnik, "formularz", "<hist1>")
    baza.zapisz_dane_wrazliwe(
        zid, DaneWrazliwe(pesel="44000001357", data_urodzenia="01.01.1944",
                          numer_dokumentu="XX0000000")
    )
    return zid


def main() -> int:
    bledy = 0
    zid = przygotuj_baze()

    llm.chat_json = _udawany_chat_json
    pipeline.chat_json = _udawany_chat_json
    pipeline.kontekst = _udawany_kontekst
    odprawa.chat_json = _udawany_chat_json
    odprawa.kontekst = _udawany_kontekst
    rag.kontekst = _udawany_kontekst

    def sprawdz(nazwa: str, warunek: bool, szczegol: str = "") -> None:
        nonlocal bledy
        if warunek:
            print(f"OK    {nazwa}")
        else:
            bledy += 1
            print(f"BŁĄD  {nazwa}")
            if szczegol:
                print(f"        {szczegol}")

    # --- draft odpowiedzi ---
    PRZECHWYCONE.clear()
    mail = Mail(
        message_id="<m1>", od="tomasz@example.com", od_nazwa="Tomasz Nowak",
        temat="Pytanie o zbiórkę",
        data="",
        tresc="Cześć, o której zbiórka? Mój PESEL to 44000001357, "
              "dowód XX0000000, tel 601234567.",
    )
    pipeline.napisz_draft(mail, przyklady_stylu=["Cześć, wyjeżdżamy o 9:00."])
    prompt_draftu = PRZECHWYCONE[-1]

    sprawdz("draft: PESEL nie wchodzi do promptu",
            "44000001357" not in prompt_draftu,
            "numer PESEL znalazł się w treści promptu")
    sprawdz("draft: numer dokumentu nie wchodzi do promptu",
            "XX0000000" not in prompt_draftu)
    sprawdz("draft: maskowanie zostawia znacznik",
            "[PESEL]" in prompt_draftu)
    sprawdz("draft: baza wiedzy jest w promptcie",
            "fragment bazy wiedzy" in prompt_draftu)
    sprawdz("draft: historia kontaktu jest w promptcie",
            "Historia kontaktu" in prompt_draftu)
    sprawdz("draft: wymagania ze zgłoszenia są w historii",
            "wegetariańska" in prompt_draftu)
    sprawdz("draft: przykłady stylu są w promptcie",
            "Przykłady moich dawnych odpowiedzi" in prompt_draftu)
    sprawdz("draft: instrukcja o tonie jest w promptcie",
            "nieformalnie" in prompt_draftu)

    # --- historia nie wynosi danych wrażliwych ---
    blok = historia.dla_adresu("tomasz@example.com").blok_dla_modelu()
    sprawdz("historia: mówi ŻE dane są, nie jakie",
            "44000001357" not in blok and "przysłane" in blok)
    sprawdz("historia: liczba osób ze zgłoszenia",
            "2 osoby" in blok, blok)
    sprawdz("historia: wymagania innych osób",
            "bez laktozy" in blok)

    # --- odprawa przedwyjazdowa ---
    PRZECHWYCONE.clear()
    wynik = odprawa.przygotuj(zid, "dolomity-jesien-2026")
    prompt_odprawy = PRZECHWYCONE[-1]

    sprawdz("odprawa: dane uczestnika są w promptcie",
            "Tomasz" in prompt_odprawy and "wegetariańska" in prompt_odprawy)
    sprawdz("odprawa: wymagania pozostałych osób są w promptcie",
            "bez laktozy" in prompt_odprawy)
    sprawdz("odprawa: dane wyjazdu są w promptcie",
            "Jesienne Dolomity" in prompt_odprawy)
    sprawdz("odprawa: baza wiedzy jest w promptcie",
            "fragment bazy wiedzy" in prompt_odprawy)
    sprawdz("odprawa: PESEL nie wchodzi do promptu",
            "44000001357" not in prompt_odprawy)
    sprawdz("odprawa: zakaz wymyślania jest w promptcie",
            "wyłącznie z sekcji" in prompt_odprawy)

    plik = odprawa.zapisz_do_pliku(wynik)
    sprawdz("odprawa: plik powstaje z adresem i tematem",
            plik.exists() and "tomasz@example.com" in plik.read_text(encoding="utf-8"))

    # --- brak bazy wiedzy = brak odprawy, zamiast wymyślonej ---
    odprawa.kontekst = lambda *a, **k: ("", [])
    try:
        odprawa.przygotuj(zid, "walia-2027")
        sprawdz("odprawa: brak bazy wiedzy przerywa generowanie", False,
                "wygenerowała odprawę bez materiału w bazie wiedzy")
    except RuntimeError:
        sprawdz("odprawa: brak bazy wiedzy przerywa generowanie", True)

    print(f"\n{bledy} błędów" if bledy else "\nwszystkie testy przeszły")
    return 1 if bledy else 0


if __name__ == "__main__":
    raise SystemExit(main())
