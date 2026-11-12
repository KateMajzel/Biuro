#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Eksport korpusu na pliki .eml — gotowe do wrzucenia na skrzynkę.

Każda wiadomość dostaje poprawne nagłówki RFC 5322: From, To, Cc, Subject,
Date, Message-ID, a odpowiedzi w wątku dostają In-Reply-To i References.
Dla wiadomości z cytatem generowana jest też wiadomość nadrzędna (od biura
do klienta), żeby wątek na skrzynce był kompletny i dało się sprawdzić,
czy draft trafia do właściwego wątku.

Linie [CASE] są usuwane. Do nagłówków trafia tylko `X-Korpus-Id`, bez opisu
pułapki — inaczej odpowiedź leżałaby w wiadomości, którą model czyta.

Użycie:
    python src/eksport_eml.py --zrodlo dane/*.txt --katalog out/eml
    python src/eksport_eml.py --zrodlo dane/zgloszenia_formularze_30.txt \
        --katalog out/eml --od-dnia 2026-10-01 --bez-watkow
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parsuj_korpus as pk  # noqa: E402

DOMENA_TESTOWA = "korpus.test"
ADRES_BIURA = "biuro@biuro-przykladowe.example"

MIESIACE = {
    "stycznia": 1, "lutego": 2, "marca": 3, "kwietnia": 4, "maja": 5,
    "czerwca": 6, "lipca": 7, "sierpnia": 8, "września": 9, "wrzesnia": 9,
    "października": 10, "pazdziernika": 10, "listopada": 11, "grudnia": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

WARSZAWA = timezone(timedelta(hours=1))  # CET; dla korpusu testowego wystarcza


def data_z_naglowka(tekst: str | None) -> datetime | None:
    """Parsuje 'Data: 4 listopada 2026, 14:07' i '5 November 2026, 09:41'."""
    if not tekst:
        return None
    t = re.match(
        r"\s*(\d{1,2})\s+([A-Za-ząćęłńóśźżĄĆĘŁŃÓŚŹŻ]+)\s+(\d{4})"
        r"(?:\s*,?\s*(\d{1,2}):(\d{2}))?",
        tekst,
    )
    if not t:
        return None
    mies = MIESIACE.get(t.group(2).lower())
    if not mies:
        return None
    godz = int(t.group(4) or 9)
    minuta = int(t.group(5) or 0)
    try:
        return datetime(int(t.group(3)), mies, int(t.group(1)), godz, minuta,
                        tzinfo=WARSZAWA)
    except ValueError:
        return None


def adres_lub_zastepczy(pole: str | None, zapas: str) -> str:
    if pole and "@" in pole:
        return pole.strip()
    return zapas


def zbuduj(
    wiadomosc: dict[str, Any],
    data: datetime,
    msgid_rodzica: str | None = None,
) -> EmailMessage:
    n = wiadomosc["naglowki"]
    m = EmailMessage()
    m["From"] = adres_lub_zastepczy(n.get("od"), f"nadawca@{DOMENA_TESTOWA}")
    m["To"] = adres_lub_zastepczy(n.get("do"), ADRES_BIURA)
    if n.get("cc"):
        m["Cc"] = n["cc"]
    if n.get("reply_to"):
        m["Reply-To"] = n["reply_to"]
    m["Subject"] = n.get("temat") or "(bez tematu)"
    m["Date"] = format_datetime(data)
    m["Message-ID"] = make_msgid(idstring=wiadomosc["id"].lower(), domain=DOMENA_TESTOWA)
    m["X-Korpus-Id"] = wiadomosc["id"]
    if msgid_rodzica:
        m["In-Reply-To"] = msgid_rodzica
        m["References"] = msgid_rodzica
    m.set_content(wiadomosc["tresc_pelna"] or "", subtype="plain", charset="utf-8")
    return m


def zbuduj_rodzica(
    wiadomosc: dict[str, Any], data: datetime
) -> tuple[EmailMessage, str] | None:
    """
    Wiadomość nadrzędna odtworzona z cytatu: od biura do klienta, datowana
    wcześniej. Bez niej odpowiedź klienta wisi na skrzynce bez wątku.
    """
    cytat = wiadomosc.get("tresc_cytowana")
    if not cytat:
        return None
    n = wiadomosc["naglowki"]
    tresc = "\n".join(
        re.sub(r"^\s*>+\s?", "", linia) for linia in cytat.splitlines()
    ).strip()
    # zdejmujemy wprowadzenie do cytatu — należy do odpowiedzi, nie do rodzica
    tresc = re.sub(
        r"^\s*(W dniu .{0,80}napisa(ł|l)\(?a?\)?:|On .{0,80}wrote:|"
        r"-{2,}\s*(Przekazana wiadomo|Original message|Forwarded message).{0,40})\s*\n",
        "",
        tresc,
        flags=re.IGNORECASE,
    ).strip()
    if not tresc:
        return None

    temat = n.get("temat") or "(bez tematu)"
    temat_rodzica = re.sub(r"^(\s*(Re|Odp|Fwd|FW)\s*:\s*)+", "", temat, flags=re.IGNORECASE)

    m = EmailMessage()
    m["From"] = ADRES_BIURA
    m["To"] = adres_lub_zastepczy(n.get("od"), f"nadawca@{DOMENA_TESTOWA}")
    m["Subject"] = temat_rodzica or "(bez tematu)"
    m["Date"] = format_datetime(data - timedelta(days=1, hours=3))
    msgid = make_msgid(idstring=f"{wiadomosc['id'].lower()}-rodzic", domain=DOMENA_TESTOWA)
    m["Message-ID"] = msgid
    m["X-Korpus-Id"] = f"{wiadomosc['id']}-RODZIC"
    m.set_content(tresc, subtype="plain", charset="utf-8")
    return m, msgid


def main() -> int:
    p = argparse.ArgumentParser(description="Korpus -> pliki .eml.")
    p.add_argument("--zrodlo", nargs="+", required=True)
    p.add_argument("--katalog", default="out/eml")
    p.add_argument(
        "--od-dnia",
        help="data pierwszej wiadomości, RRRR-MM-DD. Domyślnie 30 dni przed dzisiaj. "
             "Wiadomości bez własnego nagłówka Data dostają kolejne godziny.",
    )
    p.add_argument(
        "--bez-watkow",
        action="store_true",
        help="nie generuj wiadomości nadrzędnych dla odpowiedzi z cytatem",
    )
    args = p.parse_args()

    if args.od_dnia:
        try:
            start = datetime.fromisoformat(args.od_dnia).replace(tzinfo=WARSZAWA)
        except ValueError:
            print("BŁĄD: --od-dnia w formacie RRRR-MM-DD", file=sys.stderr)
            return 2
    else:
        start = datetime.now(WARSZAWA) - timedelta(days=30)

    wiadomosci: list[dict[str, Any]] = []
    for wzor in args.zrodlo:
        sciezki = sorted(Path().glob(wzor)) if any(z in wzor for z in "*?[") else [Path(wzor)]
        for sciezka in sciezki:
            if not sciezka.exists():
                print(f"BŁĄD: nie ma pliku {sciezka}", file=sys.stderr)
                return 2
            wiadomosci.extend(pk.parsuj_plik(sciezka))

    katalog = Path(args.katalog)
    katalog.mkdir(parents=True, exist_ok=True)

    licznik = 0
    rodzicow = 0
    krok = 0
    for w in wiadomosci:
        data = data_z_naglowka(w["naglowki"].get("data"))
        if data is None:
            data = start + timedelta(hours=krok * 7 + (krok % 5) * 3)
            krok += 1

        msgid_rodzica = None
        if not args.bez_watkow:
            rodzic = zbuduj_rodzica(w, data)
            if rodzic:
                m_rodzic, msgid_rodzica = rodzic
                (katalog / f"{w['id']}-00-rodzic.eml").write_bytes(m_rodzic.as_bytes())
                rodzicow += 1

        m = zbuduj(w, data, msgid_rodzica)
        (katalog / f"{w['id']}.eml").write_bytes(m.as_bytes())
        licznik += 1

    print(f"Zapisano {licznik} plików .eml do {katalog}")
    if rodzicow:
        print(f"  w tym {rodzicow} wiadomości nadrzędnych odtworzonych z cytatów "
              "(pliki *-00-rodzic.eml), żeby wątki na skrzynce były kompletne")
    print()
    print("Nagłówki: From, To, Cc, Subject, Date, Message-ID, In-Reply-To, References.")
    print("Linie [CASE] usunięte. W nagłówku X-Korpus-Id jest identyfikator")
    print("wiadomości — bez opisu pułapki, żeby odpowiedź nie leżała w mailu.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
