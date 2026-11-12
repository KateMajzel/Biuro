#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parser korpusu testowego na JSONL.

Rozbija pliki .txt z korpusem na pojedyncze wiadomości, zdejmuje metadane [CASE],
rozdziela nagłówki, treść nową i treść cytowaną/przekazaną, dolicza cechy
pomocnicze (czy nadawca automatyczny, czy brak polskich znaków, udział wersalików).

Bez zależności zewnętrznych. Python 3.9+.

Użycie:
    python src/parsuj_korpus.py --zrodlo dane/*.txt --podglad
    python src/parsuj_korpus.py --zrodlo dane/maile_testowe_biuro_podrozy.txt \
                                --wyjscie out/maile.jsonl

Wyjście: JSON Lines, jedna wiadomość w linii. Pola opisane w README.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

# --- wzorce struktury korpusu -------------------------------------------------

SEPARATOR = re.compile(
    r"^={5,}\s+(MAIL|POTWIERDZENIE|ZGLOSZENIE)\s+(\d+)\s*"
    r"(?:[—–-]+\s*(?P<etykieta>.*?)\s*)?={5,}\s*$"
)
LINIA_CASE = re.compile(r"^\[CASE\]\s*(.*)$")
NAGLOWEK = re.compile(
    r"^(Od|Do|Cc|Bcc|Reply-To|Temat|Data|Subject|From|To|Date):\s*(.*)$",
    re.IGNORECASE,
)

MAPA_NAGLOWKOW = {
    "od": "od",
    "from": "od",
    "do": "do",
    "to": "do",
    "cc": "cc",
    "bcc": "bcc",
    "reply-to": "reply_to",
    "temat": "temat",
    "subject": "temat",
    "data": "data",
    "date": "data",
}

# linie otwierające blok przekazany / cytowany
MARKERY_PRZEKAZANIA = [
    re.compile(r"^-{2,}\s*Przekazana wiadomo", re.IGNORECASE),
    re.compile(r"^-{2,}\s*Original message", re.IGNORECASE),
    re.compile(r"^-{2,}\s*Forwarded message", re.IGNORECASE),
    re.compile(r"^-{2,}\s*Wiadomo(ść|sc) oryginalna", re.IGNORECASE),
]

# "W dniu ... napisał(a):" na początku cytatu
MARKER_W_DNIU = re.compile(
    r"^\s*(W dniu .{0,80}napisa(ł|l)\(?a?\)?:|On .{0,80}wrote:)\s*$", re.IGNORECASE
)

NADAWCY_AUTOMATYCZNI = (
    "no-reply",
    "noreply",
    "no_reply",
    "donotreply",
    "mailer-daemon",
    "postmaster",
    "automated@",
    "automat@",
    "formularz@",
    "confirmations@",
    "notification",
    "bounce",
)

STOPKA_MOBILNA = re.compile(
    r"^\s*(Wys(ł|l)ane z|Sent from|Pozdrawiam,? wys(ł|l)ane z)\b.*$", re.IGNORECASE
)

EMAIL_W_TEKSCIE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

POLSKIE_ZNAKI = set("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")


# --- pomocnicze ---------------------------------------------------------------


def adres_z_naglowka(wartosc: str) -> str | None:
    """Wyciąga sam adres z pola typu 'Jan Kowalski <jan@x.pl>' albo 'jan@x.pl'."""
    if not wartosc:
        return None
    w_nawiasach = re.search(r"<([^>]+)>", wartosc)
    if w_nawiasach:
        kandydat = w_nawiasach.group(1).strip()
    else:
        kandydat = wartosc.strip()
    trafienie = EMAIL_W_TEKSCIE.search(kandydat)
    return trafienie.group(0).lower() if trafienie else None


def udzial_wersalikow(tekst: str) -> float:
    """Udział wielkich liter wśród liter alfabetu. Wykrywa maile pisane CAPS LOCKiem."""
    litery = [z for z in tekst if z.isalpha()]
    if not litery:
        return 0.0
    duze = sum(1 for z in litery if z.isupper())
    return round(duze / len(litery), 3)


def ma_polskie_znaki(tekst: str) -> bool:
    return any(z in POLSKIE_ZNAKI for z in tekst)

def wyglada_na_polski_bez_ogonkow(tekst: str) -> bool:
    """
    Heurystyka: tekst jest po polsku, ale pisany bez znaków diakrytycznych.
    Szukamy słów, które w poprawnej polszczyźnie mają ogonki.
    """
    probki = (
        # korespondencja
        "dzien dobry", "prosze", "dziekuje", "pozdrawiam", "zalacznik", "bede",
        "moglbym", "mozliwosc", "wyjazd", "pieniadze", "niestety", "wiec",
        "czesc", "jesli", "zgloszenie", "plec", "miesiac", "wlasnie",
        # etykiety formularza zgłoszeniowego
        "imie i nazwisko", "pokoj", "doswiadczenie", "sprzet", "naglych",
        "mieszkania", "obywatelstwo", "urodzenia", "ograniczenia", "skad",
    )
    maly = tekst.lower()
    return sum(1 for p in probki if p in maly) >= 2


def znormalizuj_puste_linie(linie: list[str]) -> list[str]:
    """Zwija ciągi pustych linii do maksymalnie jednej."""
    wynik: list[str] = []
    poprzednia_pusta = False
    for linia in linie:
        pusta = not linia.strip()
        if pusta and poprzednia_pusta:
            continue
        wynik.append(linia)
        poprzednia_pusta = pusta
    while wynik and not wynik[0].strip():
        wynik.pop(0)
    while wynik and not wynik[-1].strip():
        wynik.pop()
    return wynik


# --- rozbiór jednej wiadomości ------------------------------------------------


def rozdziel_case(linie: list[str]) -> tuple[str | None, list[str]]:
    """
    Zdejmuje blok [CASE] z początku wiadomości.
    Obsługuje kontynuacje: linie wcięte następujące bezpośrednio po [CASE].
    """
    case_fragmenty: list[str] = []
    i = 0
    while i < len(linie):
        linia = linie[i]
        if not linia.strip():
            if case_fragmenty:
                i += 1
                continue
            i += 1
            continue
        trafienie = LINIA_CASE.match(linia)
        if trafienie:
            case_fragmenty.append(trafienie.group(1).strip())
            i += 1
            # kontynuacje: wcięte linie, dopóki nie trafimy na nagłówek lub treść
            while i < len(linie) and linie[i].startswith((" ", "\t")) and linie[i].strip():
                case_fragmenty.append(linie[i].strip())
                i += 1
            continue
        break
    reszta = linie[i:]
    case_note = " ".join(case_fragmenty) if case_fragmenty else None
    return case_note, reszta


def rozdziel_naglowki(linie: list[str]) -> tuple[dict[str, str], list[str]]:
    """
    Czyta nagłówki tylko z bloku na samym początku wiadomości, do pierwszej
    pustej linii. Dzięki temu 'Od:' wewnątrz wiadomości przekazanej (FW)
    nie jest brane za nagłówek maila nadrzędnego.
    """
    naglowki: dict[str, str] = {}
    i = 0
    ostatni_klucz: str | None = None

    while i < len(linie):
        linia = linie[i]
        if not linia.strip():
            break
        trafienie = NAGLOWEK.match(linia)
        if trafienie:
            surowy = trafienie.group(1).lower()
            klucz = MAPA_NAGLOWKOW.get(surowy, surowy)
            wartosc = trafienie.group(2).strip()
            if klucz in naglowki:
                naglowki[klucz] += " " + wartosc
            else:
                naglowki[klucz] = wartosc
            ostatni_klucz = klucz
            i += 1
            continue
        # kontynuacja zawijanego nagłówka (linia wcięta)
        if ostatni_klucz and linia.startswith((" ", "\t")):
            naglowki[ostatni_klucz] += " " + linia.strip()
            i += 1
            continue
        break

    return naglowki, linie[i:]


def rozdziel_cytaty(linie: list[str]) -> tuple[list[str], list[str]]:
    """
    Dzieli treść na nową i cytowaną/przekazaną.

    Za cytat uznajemy:
      - linie zaczynające się od '>' (dowolna liczba poziomów),
      - wszystko od markera przekazania ('---- Przekazana wiadomość ----'),
      - linię 'W dniu ... napisał(a):' wraz z całą resztą, jeśli po niej idą cytaty.
    """
    nowa: list[str] = []
    cytat: list[str] = []
    w_cytacie = False

    for idx, linia in enumerate(linie):
        goly = linia.lstrip()

        if not w_cytacie:
            if any(m.match(goly) for m in MARKERY_PRZEKAZANIA):
                w_cytacie = True
                cytat.append(linia)
                continue
            if goly.startswith(">"):
                w_cytacie = True
                cytat.append(linia)
                continue
            if MARKER_W_DNIU.match(linia):
                # cytat tylko jeśli dalej faktycznie coś następuje
                dalej = [l.lstrip() for l in linie[idx + 1 :] if l.strip()]
                if dalej:
                    w_cytacie = True
                    cytat.append(linia)
                    continue
            nowa.append(linia)
        else:
            cytat.append(linia)

    return nowa, cytat


def zdejmij_stopke_mobilna(linie: list[str]) -> tuple[list[str], str | None]:
    """Odcina 'Wysłane z iPhone'a' i podobne. Zwraca treść i zdjętą stopkę."""
    for i in range(len(linie) - 1, max(len(linie) - 4, -1), -1):
        if STOPKA_MOBILNA.match(linie[i]):
            return linie[:i], linie[i].strip()
    return linie, None


def policz_poziomy_cytowania(cytat: list[str]) -> int:
    """Najgłębszy poziom cytowania w bloku cytatu."""
    maks = 0
    for linia in cytat:
        goly = linia.lstrip()
        poziom = 0
        for znak in goly:
            if znak == ">":
                poziom += 1
            elif znak == " ":
                continue
            else:
                break
        maks = max(maks, poziom)
    return maks


def parsuj_wiadomosc(
    rodzaj: str,
    numer: str,
    blok: list[str],
    zrodlo: str,
    etykieta: str | None = None,
) -> dict[str, Any]:
    case_note, reszta = rozdziel_case(blok)
    naglowki, tresc_linie = rozdziel_naglowki(reszta)
    tresc_linie = znormalizuj_puste_linie(tresc_linie)
    nowa, cytat = rozdziel_cytaty(tresc_linie)
    nowa, stopka = zdejmij_stopke_mobilna(znormalizuj_puste_linie(nowa))

    tresc_nowa = "\n".join(nowa).strip()
    tresc_cytowana = "\n".join(znormalizuj_puste_linie(cytat)).strip()
    tresc_pelna = "\n".join(tresc_linie).strip()

    od = naglowki.get("od", "")
    adres_od = adres_z_naglowka(od)
    domena = adres_od.split("@", 1)[1] if adres_od and "@" in adres_od else None

    automatyczny = bool(
        adres_od and any(wzor in adres_od for wzor in NADAWCY_AUTOMATYCZNI)
    )
    # Dwa układy formularza: powiadomienie ("Nowe zgłoszenie z formularza")
    # oraz zrzut pól ("Wyjazd: … Zgoda na regulamin: TAK").
    poczatek = tresc_pelna.lstrip().lower()
    formularz = (
        poczatek.startswith(("nowe zgłoszenie", "nowe zgloszenie"))
        or bool(re.search(r"^\s*(wyjazd|trip)\s*:", tresc_pelna, re.IGNORECASE | re.MULTILINE))
        and bool(re.search(r"zgoda na regulamin|^\s*regulamin\s*:",
                           tresc_pelna, re.IGNORECASE | re.MULTILINE))
    )

    rekord: dict[str, Any] = {
        "id": f"{rodzaj}_{int(numer):02d}",
        "rodzaj": rodzaj.lower(),
        "etykieta_korpusu": etykieta or None,
        "zrodlo": zrodlo,
        "case_note": case_note,
        "naglowki": {
            "od": od or None,
            "od_adres": adres_od,
            "od_domena": domena,
            "do": naglowki.get("do"),
            "cc": naglowki.get("cc"),
            "reply_to": naglowki.get("reply_to"),
            "temat": naglowki.get("temat"),
            "data": naglowki.get("data"),
        },
        "tresc": tresc_nowa,
        "tresc_cytowana": tresc_cytowana or None,
        "tresc_pelna": tresc_pelna,
        "stopka_mobilna": stopka,
        "cechy": {
            "znakow_tresc": len(tresc_nowa),
            "linii_tresc": len([l for l in nowa if l.strip()]),
            "ma_cytat": bool(tresc_cytowana),
            "poziomy_cytowania": policz_poziomy_cytowania(cytat),
            "nadawca_automatyczny": automatyczny,
            "zgloszenie_z_formularza": formularz,
            "ma_polskie_znaki": ma_polskie_znaki(tresc_nowa),
            "polski_bez_ogonkow": (
                not ma_polskie_znaki(tresc_nowa)
                and wyglada_na_polski_bez_ogonkow(tresc_nowa)
            ),
            "udzial_wersalikow": udzial_wersalikow(tresc_nowa),
            "wspomina_zalacznik": bool(
                re.search(r"za(ł|l)(ą|a)cz", tresc_nowa, re.IGNORECASE)
            ),
            "ma_artefakty_kodowania": bool(
                re.search(r"=[0-9A-F]{2}", tresc_pelna)
            ),
            "temat_pusty": not naglowki.get("temat")
            or naglowki.get("temat", "").strip().lower() in ("(bez tematu)", "brak"),
        },
    }
    return rekord


# --- wejście/wyjście ----------------------------------------------------------


def parsuj_plik(sciezka: Path) -> list[dict[str, Any]]:
    tekst = sciezka.read_text(encoding="utf-8")
    # normalizacja: ujednolicenie końców linii i NBSP, które psują regexy
    tekst = tekst.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")

    wiadomosci: list[dict[str, Any]] = []
    biezacy_rodzaj: str | None = None
    biezacy_numer: str | None = None
    biezaca_etykieta: str | None = None
    bufor: list[str] = []

    for linia in tekst.split("\n"):
        trafienie = SEPARATOR.match(linia)
        if trafienie:
            if biezacy_rodzaj is not None:
                wiadomosci.append(
                    parsuj_wiadomosc(
                        biezacy_rodzaj,
                        biezacy_numer or "0",
                        bufor,
                        sciezka.name,
                        biezaca_etykieta,
                    )
                )
            biezacy_rodzaj = trafienie.group(1)
            biezacy_numer = trafienie.group(2)
            biezaca_etykieta = trafienie.group("etykieta")
            bufor = []
            continue
        if biezacy_rodzaj is None:
            continue  # preambuła pliku
        # linia samych znaków '=' to ozdobnik rozdzielający, nie treść
        if set(linia.strip()) == {"="} and len(linia.strip()) >= 20:
            continue
        bufor.append(linia)

    if biezacy_rodzaj is not None:
        wiadomosci.append(
            parsuj_wiadomosc(
                biezacy_rodzaj,
                biezacy_numer or "0",
                bufor,
                sciezka.name,
                biezaca_etykieta,
            )
        )

    return wiadomosci


def podglad(wiadomosci: list[dict[str, Any]]) -> None:
    naglowek = f"{'id':<18} {'zn.':>5} {'cyt':>3} {'auto':>4} {'CAPS':>5}  temat"
    print(naglowek)
    print("-" * len(naglowek))
    for w in wiadomosci:
        c = w["cechy"]
        temat = (w["naglowki"]["temat"] or "(brak)")[:44]
        print(
            f"{w['id']:<18} {c['znakow_tresc']:>5} "
            f"{c['poziomy_cytowania']:>3} "
            f"{'tak' if c['nadawca_automatyczny'] else '  -':>4} "
            f"{c['udzial_wersalikow']:>5.2f}  {temat}"
        )
    print()
    print(f"Razem wiadomości: {len(wiadomosci)}")
    bez_ogonkow = sum(1 for w in wiadomosci if w["cechy"]["polski_bez_ogonkow"])
    z_cytatem = sum(1 for w in wiadomosci if w["cechy"]["ma_cytat"])
    auto = sum(1 for w in wiadomosci if w["cechy"]["nadawca_automatyczny"])
    formularze = sum(1 for w in wiadomosci if w["cechy"]["zgloszenie_z_formularza"])
    print(
        f"  z cytatem/przekazaniem: {z_cytatem}   "
        f"bez polskich znaków: {bez_ogonkow}   "
        f"nadawca automatyczny: {auto}   "
        f"z formularza: {formularze}"
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Parser korpusu maili na JSONL.")
    p.add_argument(
        "--zrodlo", nargs="+", required=True, help="pliki .txt z korpusem"
    )
    p.add_argument("--wyjscie", help="plik .jsonl; bez niego tylko podgląd")
    p.add_argument(
        "--podglad", action="store_true", help="wypisz tabelę kontrolną na stdout"
    )
    p.add_argument(
        "--zachowaj-case",
        action="store_true",
        help="zostaw pole case_note w wyjściu (domyślnie usuwane, bo to metadana testowa)",
    )
    args = p.parse_args()

    wszystkie: list[dict[str, Any]] = []
    for wzor in args.zrodlo:
        sciezki = sorted(Path().glob(wzor)) if any(z in wzor for z in "*?[") else [Path(wzor)]
        for sciezka in sciezki:
            if not sciezka.exists():
                print(f"BŁĄD: nie ma pliku {sciezka}", file=sys.stderr)
                return 2
            wszystkie.extend(parsuj_plik(sciezka))

    if not wszystkie:
        print("BŁĄD: nie znaleziono żadnej wiadomości — sprawdź separatory.", file=sys.stderr)
        return 1

    identyfikatory = [w["id"] for w in wszystkie]
    duplikaty = {i for i in identyfikatory if identyfikatory.count(i) > 1}
    if duplikaty:
        print(f"UWAGA: powtórzone id: {sorted(duplikaty)}", file=sys.stderr)

    if args.podglad or not args.wyjscie:
        podglad(wszystkie)

    if args.wyjscie:
        wyjscie = Path(args.wyjscie)
        wyjscie.parent.mkdir(parents=True, exist_ok=True)
        with wyjscie.open("w", encoding="utf-8") as f:
            for w in wszystkie:
                rekord = dict(w)
                if not args.zachowaj_case:
                    rekord.pop("case_note", None)
                f.write(json.dumps(rekord, ensure_ascii=False) + "\n")
        print(f"Zapisano {len(wszystkie)} wiadomości do {wyjscie}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
