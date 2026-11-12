#!/usr/bin/env python3
"""Testy ustalania wyjazdu ze zgłoszenia.

    python testy/test_wybor_wyjazdu.py

Zgłoszenie trzyma kierunek słowami nadawcy („Irlandia", „wyjazd do Irlandii
w maju"), a umowa potrzebuje klucza z wyjazdy.yaml, bo stąd bierze termin,
cenę i program. Dotąd ten klucz wpisywał człowiek, czyli musiał pamiętać, kto
gdzie jedzie.

Najważniejszy jest tu przypadek, w którym funkcja ma NIE odpowiedzieć:
dwa wyjazdy w ten sam rejon i zgłoszenie, które nie rozstrzyga, o który chodzi.
Umowa na niewłaściwy wyjazd ma zły termin, złą cenę i zły program, a podpisuje
ją uczestnik — więc brak odpowiedzi jest tu wynikiem poprawnym, a zgadnięcie
błędem.
"""

import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KORZEN))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import baza_testowa  # noqa: E402  — ustawia BIURO_BAZA i BIURO_WYJAZDY

from biuro import baza  # noqa: E402
from biuro.umowy import dopasuj_wyjazd, wyjazd_dla_zgloszenia  # noqa: E402

KATALOG = {
    "irlandia-2026": {
        "nazwa": "Warsztaty fotograficzne — Irlandia",
        "miejsce": "Irlandia — Connemara, Klify Moheru",
        "termin_od": "15.05.2026",
        "termin_do": "22.05.2026",
    },
    "dolomity-jesien-2026": {
        "nazwa": "Jesienne Dolomity",
        "miejsce": "Włochy, Dolomity — Cortina d'Ampezzo",
        "termin_od": "11.10.2026",
        "termin_do": "18.10.2026",
    },
    "dolomity-zima-2027": {
        "nazwa": "Zimowe Dolomity",
        "miejsce": "Włochy, Dolomity — Cortina d'Ampezzo",
        "termin_od": "20.01.2027",
        "termin_do": "27.01.2027",
    },
    "lake-district-2027": {
        "nazwa": "Lake District",
        "miejsce": "Anglia — Lake District",
        "termin_od": "05.04.2027",
        "termin_do": "11.04.2027",
    },
    "wyspy-owcze-2027": {
        "nazwa": "Wyspy Owcze",
        "miejsce": "Wyspy Owcze — Saksun, Gasadalur",
        "termin_od": "12.06.2027",
        "termin_do": "19.06.2027",
    },
}


def main() -> int:
    bledy = 0

    def sprawdz(nazwa: str, warunek: bool, szczegol: str = "") -> None:
        nonlocal bledy
        if warunek:
            print(f"OK    {nazwa}")
        else:
            bledy += 1
            print(f"BŁĄD  {nazwa}   {szczegol}")

    # --- jeden pasujący wyjazd ---------------------------------------------
    w = dopasuj_wyjazd("Irlandia", None, KATALOG)
    sprawdz("sama nazwa kraju wystarcza", w.klucz == "irlandia-2026", str(w))

    w = dopasuj_wyjazd("wyjazd do Irlandii w maju", None, KATALOG)
    sprawdz("odmieniona nazwa w zdaniu", w.klucz == "irlandia-2026", str(w))
    # „Irlandii" ma wspólny przedrostek z kluczem, bo porównujemy po
    # wystąpieniu słowa w kluczu i nazwie, nie po równości.

    w = dopasuj_wyjazd("Wyspy Owcze", None, KATALOG)
    sprawdz("nazwa dwuczłonowa", w.klucz == "wyspy-owcze-2027", str(w))

    w = dopasuj_wyjazd("Lake District", None, KATALOG)
    sprawdz("nazwa po angielsku", w.klucz == "lake-district-2027", str(w))

    # --- polskie znaki ------------------------------------------------------
    w = dopasuj_wyjazd("wyspy owcze, czerwiec", None, KATALOG)
    sprawdz("małe litery i przecinek", w.klucz == "wyspy-owcze-2027", str(w))

    # --- dwa wyjazdy w ten sam rejon ---------------------------------------
    w = dopasuj_wyjazd("Dolomity", None, KATALOG)
    sprawdz("dwa wyjazdy w Dolomity bez terminu to brak odpowiedzi",
            w.klucz is None, str(w))
    sprawdz("podani są obaj kandydaci",
            set(w.kandydaci) == {"dolomity-jesien-2026", "dolomity-zima-2027"},
            str(w.kandydaci))
    sprawdz("powód mówi, czego brakuje", "termin" in w.powod, w.powod)

    w = dopasuj_wyjazd("Dolomity", "11.10.2026", KATALOG)
    sprawdz("rok z terminu rozstrzyga", w.klucz == "dolomity-jesien-2026", str(w))

    w = dopasuj_wyjazd("Dolomity", "styczeń 2027", KATALOG)
    sprawdz("rok w terminie słownym też rozstrzyga",
            w.klucz == "dolomity-zima-2027", str(w))

    w = dopasuj_wyjazd("Dolomity", "chętnie w górach", KATALOG)
    sprawdz("termin bez roku nie rozstrzyga", w.klucz is None, str(w))

    # --- nazwa własna wyjazdu ----------------------------------------------
    w = dopasuj_wyjazd("Jesienne Dolomity", None, KATALOG)
    sprawdz("pełna nazwa wyjazdu rozstrzyga bez terminu",
            w.klucz == "dolomity-jesien-2026", str(w))

    # --- brak danych --------------------------------------------------------
    w = dopasuj_wyjazd(None, None, KATALOG)
    sprawdz("brak kierunku to brak odpowiedzi", w.klucz is None, str(w))
    sprawdz("przy braku kierunku kandydatami są wszystkie wyjazdy",
            len(w.kandydaci) == len(KATALOG), str(w.kandydaci))

    w = dopasuj_wyjazd("Grenlandia", None, KATALOG)
    sprawdz("kierunek poza ofertą to brak odpowiedzi", w.klucz is None, str(w))
    sprawdz("powód nazywa kierunek, którego nie ma",
            "Grenlandia" in w.powod, w.powod)

    # --- słowa, które same nic nie znaczą ----------------------------------
    w = dopasuj_wyjazd("warsztaty fotograficzne", None, KATALOG)
    sprawdz("'warsztaty fotograficzne' nie wskazuje wyjazdu",
            w.klucz is None, str(w))
    # Bez listy nieistotnych słów to zapytanie pasowałoby do każdego wyjazdu,
    # a przy jednym wyjeździe w ofercie wystawiłoby umowę na chybił trafił.

    w = dopasuj_wyjazd("chciałabym jechać na warsztaty do Irlandii", None, KATALOG)
    sprawdz("nieistotne słowa nie psują dopasowania",
            w.klucz == "irlandia-2026", str(w))

    # --- pusty katalog ------------------------------------------------------
    w = dopasuj_wyjazd("Irlandia", None, {})
    sprawdz("pusty wyjazdy.yaml to brak odpowiedzi", w.klucz is None, str(w))

    # --- warstwa bazy -------------------------------------------------------
    # Tu sprawdzamy to, czego nie widać w czystej funkcji: skąd biorą się
    # kierunek i termin, i co ma pierwszeństwo, gdy umowa już istnieje.
    baza_testowa.wymagaj_bazy_testowej()
    baza.inicjuj()
    with baza.polaczenie() as conn:
        conn.execute("DELETE FROM umowy")
        conn.execute("DELETE FROM zgloszenia")
        conn.execute(
            """INSERT INTO zgloszenia (id, utworzono, zrodlo, imie, nazwisko,
                                       wyjazd_kierunek, wyjazd_termin)
               VALUES (901, '2026-11-09', 'formularz', 'Anna', 'Nowak',
                       'Dolomity', 'październik 2026')"""
        )
        conn.execute(
            """INSERT INTO zgloszenia (id, utworzono, zrodlo, imie, nazwisko,
                                       wyjazd_kierunek)
               VALUES (902, '2026-11-09', 'formularz', 'Jan', 'Nowak', 'Walia')"""
        )
        conn.execute(
            """INSERT INTO zgloszenia (id, utworzono, zrodlo, imie, nazwisko,
                                       wyjazd_kierunek)
               VALUES (903, '2026-11-09', 'formularz', 'Ewa', 'Nowak', NULL)"""
        )

    w = wyjazd_dla_zgloszenia(901)
    sprawdz("wyjazd wyliczony ze zgłoszenia",
            w.klucz == "dolomity-jesien-2026", str(w))
    sprawdz("powód mówi, z czego wynika", "Dolomity" in w.powod, w.powod)

    w = wyjazd_dla_zgloszenia(902)
    sprawdz("drugi kierunek też się rozstrzyga", w.klucz == "walia-2027", str(w))

    w = wyjazd_dla_zgloszenia(903)
    sprawdz("zgłoszenie bez kierunku nie dostaje umowy", w.klucz is None, str(w))

    # Umowa w rejestrze ma pierwszeństwo nad wyliczeniem. Druga umowa dla
    # tego samego zgłoszenia musi dotyczyć tego samego wyjazdu, bo inaczej
    # rejestr i wykaz dla UFG przestają się zgadzać.
    with baza.polaczenie() as conn:
        conn.execute(
            """INSERT INTO umowy (zgloszenie_id, numer, data_zawarcia, wyjazd)
               VALUES (901, '99/2026', '2026-11-09', 'walia-2027')"""
        )
    w = wyjazd_dla_zgloszenia(901)
    sprawdz("istniejąca umowa wygrywa z wyliczeniem",
            w.klucz == "walia-2027", str(w))
    sprawdz("powód wskazuje rejestr", "rejestr" in w.powod, w.powod)

    try:
        wyjazd_dla_zgloszenia(99999)
        sprawdz("nieznane zgłoszenie podnosi błąd", False, "nie podniosło")
    except ValueError:
        sprawdz("nieznane zgłoszenie podnosi błąd", True)

    # --- lista do wyboru ----------------------------------------------------
    wiersze = baza.zgloszenia_do_wyboru()
    sprawdz("lista zawiera wszystkie zgłoszenia", len(wiersze) == 3, str(len(wiersze)))
    sprawdz("lista jest po nazwisku i imieniu",
            [w["imie"] for w in wiersze] == ["Anna", "Ewa", "Jan"],
            str([w["imie"] for w in wiersze]))
    sprawdz("widać, że umowa już jest",
            [w["numer_umowy"] for w in wiersze if w["id"] == 901] == ["99/2026"],
            str(wiersze[0]))

    print()
    if bledy:
        print(f"BŁĘDY: {bledy}")
        return 1
    print("Wszystkie przypadki przeszły.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
