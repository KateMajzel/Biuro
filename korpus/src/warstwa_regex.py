#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Warstwa deterministyczna: dane, które ustala regex z walidacją, a nie model.

Zasada z pomiarów: zły KSZTAŁT usuwamy (dziewięć cyfr w polu PESEL to numer
telefonu w złej rubryce — pomyłka maszyny), złą SUMĘ KONTROLNĄ zostawiamy
i flagujemy (jedenaście cyfr z błędną sumą to literówka uczestnika — tylko
człowiek może dopytać).

Każda funkcja zwraca (wartosc, status), gdzie status to jedno z:
  "ok"              — wartość poprawna, suma kontrolna się zgadza
  "zla_suma"        — kształt poprawny, suma kontrolna nie — ZOSTAJE, do człowieka
  "zly_ksztalt"     — do usunięcia, zgłaszane jako brak
  "brak"            — nie znaleziono

Importowane przez szkielet_gold.py. Nie ma zależności zewnętrznych.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any

# --- wzorce -------------------------------------------------------------------

EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]{2,}\b")
KOD_POCZTOWY = re.compile(r"\b(\d{2})-(\d{3})\b")
NIP_SUROWY = re.compile(r"\b(?:NIP[:\s]*)?(\d[\d\s-]{8,13}\d)\b", re.IGNORECASE)
UMOWA = re.compile(r"\b([A-Z]{2,4}[/-]\d{4}[/-]\d{3,5})\b")

# telefon polski: 9 cyfr, opcjonalnie +48, rozdzielone spacjami/myślnikami
TELEFON = re.compile(
    r"(?<![\d-])(?:\+?48[\s-]?)?((?:\d[\s-]?){8}\d)(?![\d-])"
)

# kwota: 2 400, 2400,50, 2.400 zł / PLN / NOK / EUR
KWOTA = re.compile(
    r"\b(\d{1,3}(?:[  .]\d{3})+|\d+)(?:[,.](\d{1,2}))?\s*(z(?:ł|l)|PLN|NOK|EUR|USD)\b",
    re.IGNORECASE,
)

# zakres dat: 12-19.02.2027 / 12.02-19.02.2027 / 21–26.09.2026
ZAKRES_DAT = re.compile(
    r"\b(\d{1,2})(?:\.(\d{1,2}))?\s*[-–—]\s*(\d{1,2})\.(\d{1,2})\.(\d{4})\b"
)
DATA_KROPKI = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
DATA_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

LICZBA_OSOB_CYFRA = re.compile(
    r"\b(\d{1,2})\s*(?:os(?:oby|ób|ob|\.)|uczestnik(?:ów|ow|a)?)\b", re.IGNORECASE
)

# Frazy dopasowywane z granicą słowa. Z pomiaru na korpusie: samo "sam" jako
# podłańcuch łapało "uczyłam się sama", "radziła sobie sama" i "sensu" —
# trzy maile dostawały liczba_osob = 1 bez żadnej podstawy. Dlatego wyrazy
# oznaczające samotną podróż wymagają czasownika ruchu obok (SOLO poniżej),
# a nie stoją w tym słowniku.
LICZBA_OSOB_SLOWO = {
    "jedna osoba": 1, "jednej osoby": 1,
    "dwie osoby": 2, "dwoje": 2, "dwóch osób": 2, "dwoch osob": 2, "we dwoje": 2,
    "trzy osoby": 3, "troje": 3, "trzech osób": 3, "trzech osob": 3,
    "cztery osoby": 4, "czworo": 4,
    "pięć osób": 5, "piec osob": 5,
}

SOLO = re.compile(
    r"\b(?:jad[eę]|lec[eę]|wybieram\s+si[eę]|b[eę]d[eę]|chc[eę]\s+jecha[ćc]|"
    r"zapisuj[eę]\s+si[eę])\s+(?:\w+\s+){0,2}?sam[aą]?\b",
    re.IGNORECASE,
)

# Etykiety daty urodzenia. Bez nich data urodzenia podana w zgłoszeniu
# ("Kowalska 3, ur. 01.01.1970") trafiała do wyjazd.data_od.
ETYKIETY_URODZENIA = ("ur.", "ur ", "urodz", "data ur", "rocznik", "pesel", "r. ur")

MIESIACE_SLOWNIE = {
    "stycznia": 1, "styczeń": 1, "styczen": 1,
    "lutego": 2, "luty": 2,
    "marca": 3, "marzec": 3,
    "kwietnia": 4, "kwiecień": 4, "kwiecien": 4,
    "maja": 5, "maj": 5,
    "czerwca": 6, "czerwiec": 6,
    "lipca": 7, "lipiec": 7,
    "sierpnia": 8, "sierpień": 8, "sierpien": 8,
    "września": 9, "wrzesnia": 9, "wrzesień": 9, "wrzesien": 9,
    "października": 10, "pazdziernika": 10, "październik": 10, "pazdziernik": 10,
    "listopada": 11, "listopad": 11,
    "grudnia": 12, "grudzień": 12, "grudzien": 12,
}

# Okno przypisania etykiety do liczby. Z pomiaru: 30 znaków przyklejało etykietę
# "pesel" do numeru telefonu stojącego dalej w zdaniu. 15 znaków i sprawdzanie
# etykiety PRZED i PO liczbie rozwiązało oba przypadki.
OKNO_ETYKIETY = 15


def bez_ogonkow(tekst: str) -> str:
    return "".join(
        z for z in unicodedata.normalize("NFD", tekst)
        if unicodedata.category(z) != "Mn"
    )


# --- sumy kontrolne -----------------------------------------------------------


def suma_pesel(cyfry: str) -> bool:
    if len(cyfry) != 11 or not cyfry.isdigit():
        return False
    wagi = [1, 3, 7, 9, 1, 3, 7, 9, 1, 3]
    s = sum(int(c) * w for c, w in zip(cyfry[:10], wagi))
    return (10 - s % 10) % 10 == int(cyfry[10])


def data_z_pesel(cyfry: str) -> date | None:
    """Data urodzenia zakodowana w PESEL — do porównania z podaną jawnie."""
    if len(cyfry) != 11 or not cyfry.isdigit():
        return None
    rr, mm, dd = int(cyfry[0:2]), int(cyfry[2:4]), int(cyfry[4:6])
    wiek_offset = {0: 1900, 1: 2000, 2: 2100, 3: 2200, 4: 1800}
    stulecie = wiek_offset.get(mm // 20)
    if stulecie is None:
        return None
    mm = mm % 20
    try:
        return date(stulecie + rr, mm, dd)
    except ValueError:
        return None


def suma_nip(cyfry: str) -> bool:
    if len(cyfry) != 10 or not cyfry.isdigit():
        return False
    wagi = [6, 5, 7, 2, 3, 4, 5, 6, 7]
    s = sum(int(c) * w for c, w in zip(cyfry[:9], wagi))
    return s % 11 == int(cyfry[9])


# --- wyciąganie pól -----------------------------------------------------------


NEGACJE = ("bez ", "brak ", "nie mam", "nie podaj", "nie chce", "nie znam", "zamiast ")

ETYKIETY_TELEFONU = ("tel", "telefon", "kom", "komorka", "dzwon", "numer kontakt", "whatsapp")
ETYKIETY_PESEL = ("pesel",)
ETYKIETY_NIP = ("nip",)
ETYKIETY_INNE_NUMERY = ("umow", "nr konta", "iban", "zamowien", "faktur", "rezerwacj")


def _zanegowana(fragment: str, pozycja: int) -> bool:
    """Czy etykieta jest poprzedzona zaprzeczeniem ('bez peselu', 'nie mam NIP-u')."""
    poprzedzajacy = fragment[max(0, pozycja - 12):pozycja]
    return any(n in poprzedzajacy for n in NEGACJE)


def odleglosc_etykiety(
    tekst: str, start: int, koniec: int, slowa: tuple[str, ...],
    okno: int = OKNO_ETYKIETY,
) -> int | None:
    """
    Odległość w znakach od liczby do najbliższej etykiety z podanej grupy,
    albo None, gdy żadnej nie ma. Etykieta zaprzeczona się nie liczy.

    Z pomiaru: sprawdzanie tylko obecności etykiety w oknie dawało dwa błędy
    naraz — 'tel 602000000, bez pesela' zabierało telefon do pola PESEL,
    bo etykieta 'pesel' była w oknie, mimo że stała po zaprzeczeniu i dalej
    niż etykieta 'tel'. Dlatego liczy się odległość, a nie obecność.
    """
    przed = bez_ogonkow(tekst[max(0, start - okno):start].lower())
    po = bez_ogonkow(tekst[koniec:koniec + okno].lower())
    najlepsza: int | None = None

    for s in slowa:
        klucz = bez_ogonkow(s)
        i = przed.rfind(klucz)
        if i >= 0 and not _zanegowana(przed, i):
            odleglosc = len(przed) - (i + len(klucz))
            najlepsza = odleglosc if najlepsza is None else min(najlepsza, odleglosc)
        j = po.find(klucz)
        if j >= 0 and not _zanegowana(po, j):
            najlepsza = j if najlepsza is None else min(najlepsza, j)

    return najlepsza


def blizej(a: int | None, b: int | None) -> bool:
    """Czy etykieta a stoi bliżej liczby niż etykieta b."""
    if a is None:
        return False
    if b is None:
        return True
    return a < b


def wyciagnij_email(tekst: str, naglowek_od: str | None = None) -> tuple[Any, str]:
    kandydaci = EMAIL.findall(tekst)
    # odrzucamy adresy własne i systemowe
    kandydaci = [
        k for k in kandydaci
        if not any(x in k.lower() for x in
                   ("biuro-przykladowe", "no-reply", "noreply", "mailer-daemon",
                    "postmaster", "formularz@"))
    ]
    if kandydaci:
        return kandydaci[0].lower(), "ok"
    if naglowek_od:
        z_naglowka = EMAIL.search(naglowek_od)
        # ten sam filtr co dla treści — bez niego zgłoszenie z formularza
        # dostawało jako kontakt adres naszego własnego formularza
        if z_naglowka and not any(
            x in z_naglowka.group(0).lower()
            for x in ("biuro-przykladowe", "no-reply", "noreply", "mailer-daemon",
                      "postmaster", "formularz@")
        ):
            return z_naglowka.group(0).lower(), "ok"
    return None, "brak"


def wyciagnij_telefony(tekst: str) -> dict[str, Any]:
    """
    Zwraca {'komorka': ..., 'stacjonarny': ..., 'odrzucone': [...]}.
    Rozdzielenie po prefiksie: 45/50/51/53/57/60/66/69/72/73/78/79/88 to komórki.
    """
    komorki: list[str] = []
    stacjonarne: list[str] = []
    odrzucone: list[str] = []

    for t in TELEFON.finditer(tekst):
        cyfry = re.sub(r"\D", "", t.group(1))
        if len(cyfry) != 9:
            continue
        # liczba stojąca bliżej etykiety PESEL/NIP/umowy niż etykiety telefonu
        # to nie telefon
        d_tel = odleglosc_etykiety(tekst, t.start(), t.end(), ETYKIETY_TELEFONU)
        d_inne = min(
            (d for d in (
                odleglosc_etykiety(tekst, t.start(), t.end(), ETYKIETY_PESEL),
                odleglosc_etykiety(tekst, t.start(), t.end(), ETYKIETY_NIP),
                odleglosc_etykiety(tekst, t.start(), t.end(), ETYKIETY_INNE_NUMERY),
            ) if d is not None),
            default=None,
        )
        if blizej(d_inne, d_tel):
            odrzucone.append(cyfry)
            continue
        if cyfry == "000000000" or len(set(cyfry)) == 1:
            odrzucone.append(cyfry)
            continue
        if cyfry[:2] in {"45", "50", "51", "53", "57", "60", "66", "69",
                         "72", "73", "78", "79", "88"}:
            komorki.append(cyfry)
        else:
            stacjonarne.append(cyfry)

    return {
        "komorka": komorki[0] if komorki else None,
        "stacjonarny": stacjonarne[0] if stacjonarne else None,
        "wszystkie": komorki + stacjonarne,
        "odrzucone": odrzucone,
    }


def wyciagnij_pesel(tekst: str) -> tuple[Any, str]:
    """
    Szuka liczby przy etykiecie 'pesel'. Zły kształt odrzucamy, złą sumę zostawiamy.
    """
    for t in re.finditer(r"\b(\d[\d\s]{4,15}\d)\b", tekst):
        cyfry = re.sub(r"\D", "", t.group(1))
        d_pesel = odleglosc_etykiety(tekst, t.start(), t.end(), ETYKIETY_PESEL)
        if d_pesel is None:
            continue
        # etykieta telefonu bliżej niż 'pesel' — to numer telefonu w zdaniu
        # wspominającym PESEL, nie PESEL
        d_tel = odleglosc_etykiety(tekst, t.start(), t.end(), ETYKIETY_TELEFONU)
        if blizej(d_tel, d_pesel):
            continue
        if len(cyfry) != 11:
            return None, "zly_ksztalt"
        if suma_pesel(cyfry):
            return cyfry, "ok"
        return cyfry, "zla_suma"
    return None, "brak"


def wyciagnij_nip(tekst: str) -> tuple[Any, str]:
    for t in NIP_SUROWY.finditer(tekst):
        cyfry = re.sub(r"\D", "", t.group(1))
        if len(cyfry) != 10:
            continue
        ma_etykiete = (
            odleglosc_etykiety(tekst, t.start(), t.end(), ETYKIETY_NIP) is not None
            or "nip" in bez_ogonkow(t.group(0).lower())
        )
        if not ma_etykiete:
            continue
        if suma_nip(cyfry):
            return cyfry, "ok"
        return cyfry, "zla_suma"
    return None, "brak"


def wyciagnij_kod_pocztowy(tekst: str) -> tuple[Any, str]:
    t = KOD_POCZTOWY.search(tekst)
    return (f"{t.group(1)}-{t.group(2)}", "ok") if t else (None, "brak")


def _czy_data_urodzenia(tekst: str, start: int, koniec: int, rok: int) -> bool:
    """
    Czy ta data to data urodzenia, a nie termin wyjazdu.
    Dwa sygnały: etykieta obok ('ur.', 'rocznik') oraz rok przed 2000 —
    biuro nie organizuje wyjazdów w latach dziewięćdziesiątych.
    """
    if rok < 2000:
        return True
    return odleglosc_etykiety(tekst, start, koniec, ETYKIETY_URODZENIA, okno=20) is not None


def wyciagnij_daty(tekst: str) -> dict[str, Any]:
    """
    Zakres dat wyjazdu, jeśli da się rozpoznać. Nie zgaduje roku.
    Daty urodzenia są odfiltrowane i zwracane osobno.
    """
    urodzenia: list[str] = []

    t = ZAKRES_DAT.search(tekst)
    if t:
        dzien_od = int(t.group(1))
        mies_od = int(t.group(2)) if t.group(2) else int(t.group(4))
        dzien_do, mies_do, rok = int(t.group(3)), int(t.group(4)), int(t.group(5))
        try:
            return {
                "data_od": date(rok, mies_od, dzien_od).isoformat(),
                "data_do": date(rok, mies_do, dzien_do).isoformat(),
                "status": "ok",
            }
        except ValueError:
            return {"data_od": None, "data_do": None, "status": "zly_ksztalt"}

    iso = DATA_ISO.findall(tekst)
    if iso:
        posortowane = sorted(f"{r}-{m}-{d}" for r, m, d in iso)
        return {
            "data_od": posortowane[0],
            "data_do": posortowane[-1] if len(posortowane) > 1 else None,
            "status": "ok",
        }

    daty: list[str] = []
    for t in DATA_KROPKI.finditer(tekst):
        d, m, r = t.group(1), t.group(2), t.group(3)
        try:
            jako_data = date(int(r), int(m), int(d))
        except ValueError:
            continue
        if _czy_data_urodzenia(tekst, t.start(), t.end(), int(r)):
            urodzenia.append(jako_data.isoformat())
            continue
        daty.append(jako_data.isoformat())

    if daty:
        daty.sort()
        return {
            "data_od": daty[0],
            "data_do": daty[-1] if len(daty) > 1 else None,
            "data_urodzenia": urodzenia[0] if urodzenia else None,
            "status": "ok",
        }

    return {
        "data_od": None,
        "data_do": None,
        "data_urodzenia": urodzenia[0] if urodzenia else None,
        "status": "brak",
    }


def wyciagnij_termin_opisowy(tekst: str) -> tuple[Any, str]:
    """Miesiąc słownie, z rokiem jeśli stoi obok. Dla maili bez konkretnej daty."""
    maly = bez_ogonkow(tekst.lower())
    for nazwa, numer in MIESIACE_SLOWNIE.items():
        klucz = bez_ogonkow(nazwa)
        poz = maly.find(klucz)
        if poz < 0:
            continue
        rok = re.search(r"\b(20\d{2})\b", maly[poz:poz + 25])
        return (f"{nazwa} {rok.group(1)}" if rok else nazwa), "ok"
    return None, "brak"


def wyciagnij_kwote(tekst: str) -> tuple[Any, Any, str]:
    t = KWOTA.search(tekst)
    if not t:
        return None, None, "brak"
    calosc = re.sub(r"[  .]", "", t.group(1))
    grosze = t.group(2) or "0"
    waluta = t.group(3).upper()
    if waluta in ("ZŁ", "ZL"):
        waluta = "PLN"
    try:
        wartosc = float(f"{calosc}.{grosze}")
    except ValueError:
        return None, None, "zly_ksztalt"
    return (int(wartosc) if wartosc.is_integer() else wartosc), waluta, "ok"


def wyciagnij_liczbe_osob(tekst: str) -> tuple[Any, str]:
    t = LICZBA_OSOB_CYFRA.search(tekst)
    if t:
        liczba = int(t.group(1))
        if 1 <= liczba <= 60:
            return liczba, "ok"
    maly = bez_ogonkow(tekst.lower())
    for fraza, liczba in LICZBA_OSOB_SLOWO.items():
        wzor = r"\b" + re.escape(bez_ogonkow(fraza)) + r"\b"
        if re.search(wzor, maly):
            return liczba, "ok"
    if SOLO.search(tekst):
        return 1, "ok"
    return None, "brak"


def wyciagnij_numer_umowy(tekst: str) -> tuple[Any, str]:
    t = UMOWA.search(tekst)
    return (t.group(1), "ok") if t else (None, "brak")


def wyciagnij_kierunek(tekst: str, kierunki: list[str]) -> tuple[Any, str]:
    """Dopasowanie do zamkniętej listy kierunków z wyjazdy.yaml. Bez listy nie zgaduje."""
    maly = bez_ogonkow(tekst.lower())
    trafienia = [k for k in kierunki if bez_ogonkow(k.lower()) in maly]
    if len(trafienia) == 1:
        return trafienia[0], "ok"
    if len(trafienia) > 1:
        return trafienia, "wiele"
    return None, "brak"


# --- złożenie -----------------------------------------------------------------

KIERUNKI_DOMYSLNE = [
    "Lofoty", "Senja", "Islandia", "Grenlandia", "Svalbard", "Spitsbergen",
    "Walia", "Norwegia", "Finlandia", "Szkocja", "Wyspy Owcze",
]


def przetworz(tekst: str, naglowek_od: str | None = None,
              kierunki: list[str] | None = None) -> dict[str, Any]:
    """
    Zwraca {'pola': {ścieżka: wartość}, 'statusy': {ścieżka: status},
            'do_czlowieka': [powody], 'braki': [ścieżki]}
    """
    kierunki = kierunki or KIERUNKI_DOMYSLNE
    pola: dict[str, Any] = {}
    statusy: dict[str, str] = {}
    do_czlowieka: list[str] = []
    braki: list[str] = []

    def zapisz(sciezka: str, wartosc: Any, status: str) -> None:
        statusy[sciezka] = status
        if status in ("ok", "zla_suma") and wartosc is not None:
            pola[sciezka] = wartosc
        elif status == "zly_ksztalt":
            braki.append(sciezka)
        elif status == "brak":
            braki.append(sciezka)

    email, st = wyciagnij_email(tekst, naglowek_od)
    zapisz("kontakt.email", email, st)

    tel = wyciagnij_telefony(tekst)
    zapisz("kontakt.telefon", tel["komorka"], "ok" if tel["komorka"] else "brak")
    if tel["stacjonarny"]:
        zapisz("kontakt.telefon_stacjonarny", tel["stacjonarny"], "ok")
    if tel["odrzucone"]:
        statusy["_telefony_odrzucone"] = ", ".join(tel["odrzucone"])

    pesel, st = wyciagnij_pesel(tekst)
    zapisz("uczestnicy[0].pesel", pesel, st)
    if st == "zla_suma":
        do_czlowieka.append("PESEL ma poprawną długość, ale błędną sumę kontrolną — literówka uczestnika, trzeba dopytać")
    if st == "zly_ksztalt":
        do_czlowieka.append("w polu PESEL jest liczba o innej długości niż 11 cyfr — do usunięcia i dopytania")
    if pesel and st == "ok":
        z_pesel = data_z_pesel(pesel)
        if z_pesel:
            pola["uczestnicy[0].data_urodzenia"] = z_pesel.isoformat()
            statusy["uczestnicy[0].data_urodzenia"] = "ok_z_pesel"

    nip, st = wyciagnij_nip(tekst)
    zapisz("faktura.nip", nip, st)
    if st == "zla_suma":
        do_czlowieka.append("NIP ma 10 cyfr, ale błędną sumę kontrolną — do weryfikacji przed wystawieniem faktury")

    kod, st = wyciagnij_kod_pocztowy(tekst)
    if st == "ok":
        zapisz("uczestnicy[0].adres_kod_pocztowy", kod, st)

    daty = wyciagnij_daty(tekst)
    if daty.get("data_urodzenia") and "uczestnicy[0].data_urodzenia" not in pola:
        zapisz("uczestnicy[0].data_urodzenia", daty["data_urodzenia"], "ok")
    if daty["status"] == "ok":
        zapisz("wyjazd.data_od", daty["data_od"], "ok")
        if daty["data_do"]:
            zapisz("wyjazd.data_do", daty["data_do"], "ok")
    else:
        termin, st_t = wyciagnij_termin_opisowy(tekst)
        if st_t == "ok":
            zapisz("wyjazd.termin_opis", termin, "ok")
        braki.append("wyjazd.data_od")

    kwota, waluta, st = wyciagnij_kwote(tekst)
    if st == "ok":
        zapisz("platnosc.kwota", kwota, "ok")
        zapisz("platnosc.waluta", waluta, "ok")

    liczba, st = wyciagnij_liczbe_osob(tekst)
    zapisz("zgloszenie.liczba_osob", liczba, st)

    umowa, st = wyciagnij_numer_umowy(tekst)
    if st == "ok":
        zapisz("umowa.numer", umowa, "ok")

    kierunek, st = wyciagnij_kierunek(tekst, kierunki)
    if st == "ok":
        zapisz("wyjazd.kierunek", kierunek, "ok")
        # Dopasowanie do listy nie rozróżnia wyboru od wspomnienia. W korpusie
        # jest mail, w którym Spitsbergen pojawia się jako zdjęcia ojca
        # z lat siedemdziesiątych, a nie jako wybrany wyjazd. Dlatego kierunek
        # z regexu jest zawsze kandydatem do potwierdzenia, nie wartością.
        do_czlowieka.append(
            f"kierunek '{kierunek}' dopasowany do listy — sprawdź, czy klient go "
            "wybiera, czy tylko wspomina"
        )
    elif st == "wiele":
        statusy["wyjazd.kierunek"] = "wiele"
        do_czlowieka.append(
            f"w treści jest więcej niż jeden kierunek ({', '.join(kierunek)}) — "
            "nie wiadomo, który klient wybiera"
        )
        braki.append("wyjazd.kierunek")
    else:
        braki.append("wyjazd.kierunek")

    return {
        "pola": pola,
        "statusy": statusy,
        "do_czlowieka": do_czlowieka,
        "braki": sorted(set(braki)),
    }


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Użycie: python src/warstwa_regex.py \"treść wiadomości\"")
        raise SystemExit(1)
    print(json.dumps(przetworz(sys.argv[1]), ensure_ascii=False, indent=2))
