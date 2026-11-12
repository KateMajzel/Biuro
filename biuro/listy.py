"""Arkusz wyjazdu: lista uczestników, rezerwacje i jednostronicowa logistyka.

Powstają dwa warianty tego samego pliku:

  pełny      - z PESEL-em i numerem dokumentu. Dla Ciebie i dla ubezpieczyciela.
  okrojony   - bez danych wrażliwych. Do wysłania pilotowi, lokalnemu
               przewodnikowi albo obiektowi.

Wariant okrojony istnieje dlatego, że lista uczestników krąży po wyjeździe
i nie ma powodu, żeby numery PESEL krążyły razem z nią.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .baza import rezerwacje_wyjazdu, uczestnicy_wyjazdu
from .config import cfg
from .schemas import Rezerwacja

NAGLOWEK = Font(bold=True, color="FFFFFF")
TLO_NAGLOWKA = PatternFill("solid", fgColor="2F4F6F")
TYTUL = Font(bold=True, size=14)
WYROZNIENIE = Font(bold=True)
TLO_UWAGI = PatternFill("solid", fgColor="FFF3CD")


def _naglowki(arkusz, kolumny: list[str], wiersz: int = 1) -> None:
    for nr, nazwa in enumerate(kolumny, start=1):
        komorka = arkusz.cell(row=wiersz, column=nr, value=nazwa)
        komorka.font = NAGLOWEK
        komorka.fill = TLO_NAGLOWKA
        komorka.alignment = Alignment(vertical="center", wrap_text=True)
    # jako tekst, nie przez .cell() - odwołanie do komórki by ją utworzyło
    # i append() zaczynałby od pustego wiersza
    arkusz.freeze_panes = f"A{wiersz + 1}"


def _dopasuj_szerokosci(arkusz, maks: int = 55) -> None:
    for kolumna in arkusz.columns:
        dlugosc = max((len(str(k.value)) for k in kolumna if k.value is not None), default=0)
        litera = get_column_letter(kolumna[0].column)
        arkusz.column_dimensions[litera].width = min(max(dlugosc + 2, 10), maks)


def _arkusz_uczestnikow(wb: Workbook, uczestnicy: list[dict], wrazliwe: bool) -> None:
    arkusz = wb.create_sheet("Uczestnicy")
    kolumny = ["#", "Nazwisko", "Imię", "Telefon", "E-mail", "Adres"]
    if wrazliwe:
        kolumny += ["Data urodzenia", "PESEL", "Dokument"]
    kolumny += ["Nr umowy", "Uwagi / wymagania", "Status"]
    _naglowki(arkusz, kolumny)

    for nr, u in enumerate(uczestnicy, start=1):
        adres = ", ".join(
            x for x in (
                u.get("w_ulica") or u.get("ulica"),
                f"{u.get('w_kod') or u.get('kod_pocztowy') or ''} "
                f"{u.get('w_miasto') or u.get('miasto') or ''}".strip(),
            ) if x
        )
        wiersz = [nr, u.get("nazwisko"), u.get("imie"), u.get("telefon"), u.get("email"), adres]
        if wrazliwe:
            wiersz += [u.get("data_urodzenia"), u.get("pesel"), u.get("numer_dokumentu")]
        wiersz += [u.get("nr_umowy"), u.get("dodatkowe"), u.get("status")]
        arkusz.append(wiersz)

    if wrazliwe and uczestnicy:
        ostatni = arkusz.max_row + 2
        komorka = arkusz.cell(
            row=ostatni, column=1,
            value="Ten arkusz zawiera dane wrażliwe (PESEL, numer dokumentu). "
                  "Nie przesyłaj go dalej - do udostępniania użyj wariantu okrojonego.",
        )
        komorka.font = WYROZNIENIE
        komorka.fill = TLO_UWAGI
    _dopasuj_szerokosci(arkusz)


def _arkusz_rezerwacji(wb: Workbook, rezerwacje: list[dict], wrazliwe: bool) -> None:
    arkusz = wb.create_sheet("Rezerwacje")
    _naglowki(arkusz, [
        "Typ", "Dostawca", "Nr rezerwacji", "Od", "Do", "Kwota", "Opłacone",
        "Szczegóły", "Uwagi", "Braki",
    ])

    for r in rezerwacje:
        rez = Rezerwacja.model_validate_json(r["dane"])
        szczegoly: list[str] = []
        if rez.typ.value == "lot":
            if rez.numery_lotow:
                szczegoly.append("Loty: " + ", ".join(rez.numery_lotow))
            if rez.trasa:
                szczegoly.append(f"Trasa: {rez.trasa}")
            if rez.godziny:
                szczegoly.append(f"Godziny: {rez.godziny}")
            if rez.bagaz:
                szczegoly.append(f"Bagaż: {rez.bagaz}")
        elif rez.typ.value == "nocleg":
            if rez.adres:
                szczegoly.append(f"Adres: {rez.adres}")
            if rez.zameldowanie:
                szczegoly.append(f"Zameldowanie: {rez.zameldowanie}")
            if rez.kontakt:
                szczegoly.append(f"Kontakt: {rez.kontakt}")
            if rez.kod_dostepu:
                szczegoly.append(
                    f"Kod dostępu: {rez.kod_dostepu}" if wrazliwe
                    else "Kod dostępu: w wariancie pełnym"
                )
        elif rez.typ.value == "samochod":
            if rez.pojazd:
                szczegoly.append(f"Pojazd: {rez.pojazd}")
            if rez.miejsce_odbioru:
                szczegoly.append(f"Odbiór: {rez.miejsce_odbioru}")
            if rez.miejsce_zwrotu:
                szczegoly.append(f"Zwrot: {rez.miejsce_zwrotu}")
            if rez.wklad_wlasny:
                szczegoly.append(f"Wkład własny: {rez.wklad_wlasny}")
            szczegoly.append(
                "Ubezpieczenie wkładu: "
                + {True: "wykupione", False: "BRAK", None: "nieznane"}[rez.ubezpieczenie_wkladu]
            )

        braki = json.loads(r["braki"] or "[]")
        arkusz.append([
            rez.typ.value, rez.dostawca, rez.numer_rezerwacji, rez.data_od, rez.data_do,
            f"{rez.kwota or ''} {rez.waluta or ''}".strip(),
            {True: "tak", False: "nie", None: "?"}[rez.oplacone],
            "\n".join(szczegoly), rez.uwagi, ", ".join(braki),
        ])

    for wiersz in arkusz.iter_rows(min_row=2):
        for komorka in wiersz:
            komorka.alignment = Alignment(vertical="top", wrap_text=True)
    _dopasuj_szerokosci(arkusz)


def _arkusz_logistyki(
    wb: Workbook, klucz: str, dane_wyjazdu: dict, rezerwacje: list[dict],
    liczba_uczestnikow: int, wrazliwe: bool,
) -> None:
    """Jedna strona, którą można wydrukować i mieć w kieszeni."""
    arkusz = wb.create_sheet("Logistyka", 0)
    arkusz.cell(row=1, column=1, value=dane_wyjazdu.get("nazwa", klucz)).font = TYTUL

    wiersz = 3

    def sekcja(tytul: str) -> None:
        nonlocal wiersz
        komorka = arkusz.cell(row=wiersz, column=1, value=tytul)
        komorka.font = NAGLOWEK
        komorka.fill = TLO_NAGLOWKA
        arkusz.cell(row=wiersz, column=2).fill = TLO_NAGLOWKA
        wiersz += 1

    def para(etykieta: str, wartosc) -> None:
        nonlocal wiersz
        arkusz.cell(row=wiersz, column=1, value=etykieta).font = WYROZNIENIE
        komorka = arkusz.cell(row=wiersz, column=2, value=wartosc if wartosc else "—")
        komorka.alignment = Alignment(vertical="top", wrap_text=True)
        wiersz += 1

    sekcja("WYJAZD")
    para("Termin", f"{dane_wyjazdu.get('termin_od','?')} – {dane_wyjazdu.get('termin_do','?')}")
    para("Miejsce", dane_wyjazdu.get("miejsce"))
    para("Uczestników", liczba_uczestnikow)
    para("Zbiórka", f"{dane_wyjazdu.get('wyjazd_miejsce','')} "
                    f"({dane_wyjazdu.get('wyjazd_data','')})".strip())
    para("Powrót", f"{dane_wyjazdu.get('powrot_miejsce','')} "
                   f"({dane_wyjazdu.get('powrot_data','')})".strip())
    para("Pilot", f"{dane_wyjazdu.get('pilot_imie','')} "
                  f"{dane_wyjazdu.get('pilot_telefon','')}".strip())
    wiersz += 1

    for typ, naglowek in (
        ("nocleg", "NOCLEG"), ("lot", "LOT"), ("samochod", "SAMOCHÓD"),
        ("ubezpieczenie", "UBEZPIECZENIE"),
    ):
        pasujace = [r for r in rezerwacje if r["typ"] == typ]
        if not pasujace:
            continue
        sekcja(naglowek)
        for r in pasujace:
            rez = Rezerwacja.model_validate_json(r["dane"])
            para("Dostawca", rez.dostawca)
            para("Nr rezerwacji", rez.numer_rezerwacji)
            para("Termin", f"{rez.data_od or '?'} – {rez.data_do or '?'}")
            if typ == "nocleg":
                para("Adres", rez.adres)
                para("Zameldowanie", rez.zameldowanie)
                para("Kod dostępu",
                     rez.kod_dostepu if wrazliwe else "(tylko w wariancie pełnym)")
                para("Kontakt", rez.kontakt)
            elif typ == "lot":
                para("Loty", ", ".join(rez.numery_lotow) or None)
                para("Trasa", rez.trasa)
                para("Godziny", rez.godziny)
                para("Bagaż", rez.bagaz)
            elif typ == "samochod":
                para("Pojazd", rez.pojazd)
                para("Odbiór", rez.miejsce_odbioru)
                para("Zwrot", rez.miejsce_zwrotu)
                para("Wkład własny", rez.wklad_wlasny)
                etykieta = {True: "wykupione", False: "BRAK — DOKUPIĆ", None: "nieznane"}
                arkusz.cell(row=wiersz, column=1, value="Ubezp. wkładu").font = WYROZNIENIE
                komorka = arkusz.cell(
                    row=wiersz, column=2, value=etykieta[rez.ubezpieczenie_wkladu]
                )
                if rez.ubezpieczenie_wkladu is not True:
                    komorka.font = WYROZNIENIE
                    komorka.fill = TLO_UWAGI
                wiersz += 1
            if rez.uwagi:
                para("Uwagi", rez.uwagi)
            wiersz += 1

    arkusz.column_dimensions["A"].width = 18
    arkusz.column_dimensions["B"].width = 75
    return None


def zrob_arkusz(klucz_wyjazdu: str, wrazliwe: bool = True) -> Path:
    from .umowy import wyjazd  # import tutaj, żeby uniknąć cyklu

    dane_wyjazdu = wyjazd(klucz_wyjazdu)
    uczestnicy = uczestnicy_wyjazdu(klucz_wyjazdu)
    rezerwacje = rezerwacje_wyjazdu(klucz_wyjazdu)

    wb = Workbook()
    wb.remove(wb.active)
    _arkusz_uczestnikow(wb, uczestnicy, wrazliwe)
    _arkusz_rezerwacji(wb, rezerwacje, wrazliwe)
    _arkusz_logistyki(wb, klucz_wyjazdu, dane_wyjazdu, rezerwacje, len(uczestnicy), wrazliwe)

    katalog = cfg().sciezka("umowy").parent / "listy"
    katalog.mkdir(parents=True, exist_ok=True)
    sufiks = "pelna" if wrazliwe else "okrojona"
    plik = katalog / f"{date.today():%Y-%m-%d}-{klucz_wyjazdu}-lista-{sufiks}.xlsx"
    wb.save(plik)
    return plik
