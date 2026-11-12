#!/usr/bin/env python3
"""Testy generowania dokumentów: umowa, arkusz wyjazdu, wykaz CSV dla UFG.

    python testy/test_dokumenty.py

Bez modelu i bez sieci. Sprawdza, czy dane z bazy faktycznie trafiają
do dokumentów i czy walidacja wyłapuje nieuzupełnione pola.

Wymaga szablonu umowy. Jeśli go nie ma, test umowy jest pomijany
z komunikatem, a pozostałe i tak się wykonują.
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

from openpyxl import load_workbook  # noqa: E402

from biuro import baza, listy, ufg, umowy  # noqa: E402
from biuro.config import cfg  # noqa: E402
from biuro.schemas import (  # noqa: E402
    DaneWrazliwe, Rezerwacja, TypDokumentu, TypRezerwacji, Uczestnik,
)

WYJAZD = "dolomity-jesien-2026"


def przygotuj() -> tuple[int, int]:
    baza.inicjuj()
    with baza.polaczenie() as conn:
        for tabela in ("dane_wrazliwe", "rezerwacje", "umowy", "zgloszenia"):
            conn.execute(f"DELETE FROM {tabela}")

    krajowy = Uczestnik(
        imie="Tomasz", nazwisko="Nowak", email="tomasz@example.com",
        telefon="+48 601 234 567", kraj_region="Polska", ulica="Kwiatowa 1/2",
        kod_pocztowy="40-001", miasto="Katowice", liczba_osob=2,
        dodatkowe_informacje="dieta wegetariańska",
        wymagania_innych_osob="partner: bez laktozy",
    )
    id_krajowy = baza.zapisz_zgloszenie(krajowy, "formularz", "<pl1>")
    baza.zapisz_dane_wrazliwe(
        id_krajowy,
        DaneWrazliwe(pesel="44000001357", data_urodzenia="01.01.1944",
                     numer_dokumentu="XX0000000", ulica="Kwiatowa 1/2",
                     kod_pocztowy="40-001", miasto="Katowice"),
    )

    # uczestnik zagraniczny: paszport zamiast PESEL-u
    zagraniczny = Uczestnik(
        imie="Megan", nazwisko="Price", email="megan@example.uk",
        telefon="+44 7700 900123", kraj_region="Wielka Brytania",
        ulica="High St 4", kod_pocztowy="LL55 4NY", miasto="Llanberis",
        typ_dokumentu=TypDokumentu.PASZPORT, numer_dokumentu="ZZ0000000",
    )
    id_zagraniczny = baza.zapisz_zgloszenie(zagraniczny, "formularz", "<uk1>")

    nocleg = Rezerwacja(
        typ=TypRezerwacji.NOCLEG, dostawca="Apartamenty Cortina",
        numer_rezerwacji="BK-99217", data_od="11.10.2026", data_do="17.10.2026",
        adres="Via Roma 12, Cortina d'Ampezzo", kod_dostepu="4729#",
        zameldowanie="od 16:00, skrytka po lewej od wejścia",
        kontakt="+39 333 1122334", kwota="4200", waluta="EUR", oplacone=False,
    )
    auto = Rezerwacja(
        typ=TypRezerwacji.SAMOCHOD, dostawca="Hertz Venezia",
        numer_rezerwacji="HZ-556012", data_od="11.10.2026", data_do="17.10.2026",
        pojazd="VW Caravelle", miejsce_odbioru="Wenecja Marco Polo",
        wklad_wlasny="1500 EUR", ubezpieczenie_wkladu=False,
    )
    baza.zapisz_rezerwacje(nocleg, WYJAZD, "<rez1>")
    baza.zapisz_rezerwacje(auto, WYJAZD, "<rez2>")

    return id_krajowy, id_zagraniczny


def wpisz_umowy_wprost(identyfikatory: list[int]) -> None:
    """Wpisuje umowy do rejestru bez generowania dokumentu.

    Potrzebne, gdy nie ma szablonu .docx — a nie ma go u nikogo, kto pobrał
    repozytorium, bo wzorce umów są wyłączone z publikacji. Bez tego arkusz
    wyjazdu i wykaz dla UFG nie miałyby na czym pracować i pięć testów
    przechodziłoby jako nieuruchomione.
    """
    from datetime import date

    with baza.polaczenie() as conn:
        for nr, zgloszenie_id in enumerate(identyfikatory, start=1):
            conn.execute(
                """INSERT OR REPLACE INTO umowy
                   (zgloszenie_id, numer, data_zawarcia, wyjazd, data_wyjazdu,
                    kwota, plik_docx, plik_pdf)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (zgloszenie_id, f"TEST-{nr}/{date.today().year}",
                 date.today().isoformat(), WYJAZD, "11.10.2026", None, None, None),
            )


def main() -> int:
    bledy = 0

    def sprawdz(nazwa: str, warunek: bool, szczegol: str = "") -> None:
        nonlocal bledy
        if warunek:
            print(f"OK    {nazwa}")
        else:
            bledy += 1
            print(f"BŁĄD  {nazwa}")
            if szczegol:
                print(f"        {szczegol}")

    id_krajowy, id_zagraniczny = przygotuj()

    # --- umowa ---
    if not (cfg().sciezka("szablony") / "umowa.docx").exists():
        print("POMIN testy umowy — brak szablonu "
              "(python skrypty/zbuduj_szablon_umowy.py wsad/umowa_zrodlo.docx)")
        print("      rejestr umów wypełniany wprost, żeby testy arkusza i UFG "
              "miały na czym pracować")
        wpisz_umowy_wprost([id_krajowy, id_zagraniczny])
    else:
        from docx import Document

        docx, _, braki = umowy.generuj(id_krajowy, WYJAZD)
        tekst = "\n".join(p.text for p in Document(docx).paragraphs)
        for tabela in Document(docx).tables:
            for wiersz in tabela.rows:
                tekst += "\n" + " | ".join(k.text for k in wiersz.cells)

        sprawdz("umowa: dane uczestnika wchodzą", "Tomasz Nowak" in tekst)
        sprawdz("umowa: PESEL wchodzi", "44000001357" in tekst)
        sprawdz("umowa: nazwa i termin wyjazdu wchodzą",
                "Jesienne Dolomity" in tekst and "11.10.2026" in tekst)
        sprawdz("umowa: wymagania uczestnika wchodzą", "wegetariańska" in tekst)
        sprawdz("umowa: brak nieuzupełnionych znaczników jinja",
                "{{" not in tekst)
        sprawdz("umowa: walidacja wypisuje nieuzupełnione pola", len(braki) > 0,
                "walidacja nie znalazła pustych pól, choć wyjazdy.yaml ma placeholdery")

        docx_uk, _, _ = umowy.generuj(id_zagraniczny, WYJAZD)
        tekst_uk = ""
        for tabela in Document(docx_uk).tables:
            for wiersz in tabela.rows:
                tekst_uk += "\n" + " | ".join(k.text for k in wiersz.cells)
        sprawdz("umowa: uczestnik bez PESEL-u dostaje dokument w rubryce",
                "ZZ0000000" in tekst_uk and "paszport" in tekst_uk.lower())

    # --- arkusz wyjazdu ---
    pelny = listy.zrob_arkusz(WYJAZD, wrazliwe=True)
    okrojony = listy.zrob_arkusz(WYJAZD, wrazliwe=False)

    def zawartosc(plik: Path) -> str:
        wb = load_workbook(plik)
        tekst = ""
        for arkusz in wb.worksheets:
            for wiersz in arkusz.iter_rows(values_only=True):
                tekst += " | ".join(str(k) for k in wiersz if k is not None) + "\n"
        return tekst

    tekst_pelny = zawartosc(pelny)
    tekst_okrojony = zawartosc(okrojony)

    sprawdz("arkusz pełny: PESEL jest", "44000001357" in tekst_pelny)
    sprawdz("arkusz pełny: kod do skrytki jest", "4729#" in tekst_pelny)
    sprawdz("arkusz okrojony: PESEL-u NIE MA", "44000001357" not in tekst_okrojony,
            "wariant okrojony zawiera PESEL - to jest wyciek")
    sprawdz("arkusz okrojony: kodu do skrytki NIE MA", "4729#" not in tekst_okrojony,
            "wariant okrojony zawiera kod dostępu - to jest wyciek")
    sprawdz("arkusz okrojony: uczestnicy i logistyka zostają",
            "Nowak" in tekst_okrojony and "Apartamenty Cortina" in tekst_okrojony)
    sprawdz("arkusz: samochód bez ubezpieczenia wkładu jest wyróżniony",
            "DOKUPIĆ" in tekst_pelny)

    # --- wykaz CSV dla UFG ---
    from datetime import date

    dzisiaj = date.today()
    wynik = ufg.generuj(dzisiaj.year, dzisiaj.month)
    csv_tekst = wynik.plik.read_text(encoding=cfg().get("ufg.kodowanie", "utf-8-sig"))

    sprawdz("UFG: plik ma nagłówki z config.yaml", "Numer umowy" in csv_tekst)
    sprawdz("UFG: umowy z okresu są w pliku", "Nowak" in csv_tekst)
    sprawdz("UFG: liczba podróżnych ze zgłoszenia", ";2;" in csv_tekst,
            "liczba_osob nie trafiła do pliku")
    sprawdz("UFG: walidacja wyłapuje placeholdery z wyjazdy.yaml",
            wynik.nieuzupelnione_kwoty > 0 or len(wynik.braki) > 0)
    sprawdz("UFG: separator z konfiguracji", ";" in csv_tekst)

    # --- numeracja umów ---
    #
    # Numer umowy idzie do wykazu dla UFG, więc powtórzony numer to błąd
    # w dokumencie dla urzędu, nie literówka. Wzór wpisany w konfiguracji
    # jako gotowa wartość („7/2024") przechodził przez format() bez zmian
    # i KAŻDA umowa dostawała ten sam numer. Wyszło na prawdziwej umowie
    # wystawionej w listopadzie 2026 z numerem z 2024 roku.
    import biuro.umowy as modul_umow

    stary_cfg = modul_umow.cfg

    class KonfZeWzorem:
        def __init__(self, wzor):
            self.wzor = wzor

        def get(self, klucz, domyslna=None):
            if klucz == "umowy.wzor_numeru":
                return self.wzor
            return stary_cfg().get(klucz, domyslna)

    try:
        modul_umow.cfg = lambda: KonfZeWzorem("7/2024")
        try:
            modul_umow.nastepny_numer_umowy()
            sprawdz("numeracja: wzór bez {nr} jest odrzucany", False,
                    "nie podniesiono wyjątku")
        except RuntimeError as e:
            sprawdz("numeracja: wzór bez {nr} jest odrzucany",
                    "wzor_numeru" in str(e), str(e)[:60])

        modul_umow.cfg = lambda: KonfZeWzorem("{nr}/{rok}")
        nr_a = modul_umow.nastepny_numer_umowy()
        sprawdz("numeracja: numer zawiera bieżący rok",
                str(date.today().year) in nr_a, nr_a)
        with baza.polaczenie() as conn:
            zajete = {
                r[0] for r in conn.execute(
                    "SELECT numer FROM umowy WHERE numer IS NOT NULL"
                )
            }
        sprawdz("numeracja: nowy numer nie jest już zajęty",
                nr_a not in zajete, f"{nr_a} jest w {sorted(zajete)}")
    finally:
        modul_umow.cfg = stary_cfg

    print(f"\n{bledy} błędów" if bledy else "\nwszystkie testy przeszły")
    return 1 if bledy else 0


if __name__ == "__main__":
    raise SystemExit(main())
