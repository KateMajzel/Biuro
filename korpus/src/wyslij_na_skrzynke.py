#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wrzucenie plików .eml na skrzynkę przez IMAP APPEND.

APPEND wkłada wiadomość do folderu tak, jakby przyszła — i NIC NIE WYSYŁA.
To jest ważne, bo adresy nadawców w korpusie wyglądają jak prawdziwe
(gmail.com, wp.pl). Przy wysyłce przez SMTP część z nich mogłaby trafić do
istniejących ludzi albo wrócić jako odbicia i zepsuć reputację domeny.
Przy APPEND nie wychodzi ani jedna wiadomość.

Zachowany jest oryginalny nagłówek Date, więc wiadomości ustawiają się
na skrzynce w kolejności z korpusu, a nie wszystkie na tę samą minutę.

Dane dostępowe bierze ze zmiennych środowiskowych, nie z argumentów —
argumenty zostają w historii powłoki:

    export IMAP_HOST=imap.gmail.com
    export IMAP_USER=biuro@biuro-przykladowe.example
    export IMAP_PASS=xxxx-xxxx-xxxx-xxxx      # hasło aplikacji, nie hasło do konta

Użycie:
    python src/wyslij_na_skrzynke.py --katalog out/eml --folder Korpus --podglad
    python src/wyslij_na_skrzynke.py --katalog out/eml --folder Korpus

Gmail: trzeba mieć włączone IMAP (Ustawienia -> Przekazywanie i POP/IMAP)
i wygenerowane hasło aplikacji przy włączonej weryfikacji dwuetapowej.
Zalecany osobny folder, nie INBOX — po testach usuwasz folder i nie zostaje
śmietnik w prawdziwej skrzynce.
"""

from __future__ import annotations

import argparse
import imaplib
import os
import re
import sys
import time
from email import message_from_bytes, policy
from email.utils import parsedate_to_datetime
from pathlib import Path


def czas_imap(surowe: bytes) -> str | None:
    """Zamienia nagłówek Date na format, którego oczekuje APPEND."""
    try:
        wiadomosc = message_from_bytes(surowe)
        data = parsedate_to_datetime(wiadomosc["Date"])
    except (TypeError, ValueError, KeyError):
        return None
    if data is None:
        return None
    return imaplib.Time2Internaldate(data.timestamp())


def nazwa_folderu(nazwa: str) -> str:
    """Folder z polskimi znakami albo spacją musi być w cudzysłowach."""
    if re.search(r"[\s\"]", nazwa):
        return '"' + nazwa.replace('"', '\\"') + '"'
    return nazwa


def main() -> int:
    p = argparse.ArgumentParser(description="Pliki .eml -> skrzynka przez IMAP APPEND.")
    p.add_argument("--katalog", default="out/eml", help="katalog z plikami .eml")
    p.add_argument("--folder", default="Korpus", help="folder docelowy na skrzynce")
    p.add_argument(
        "--podglad",
        action="store_true",
        help="pokaż, co zostałoby wrzucone, i nie łącz się ze skrzynką",
    )
    p.add_argument(
        "--przeczytane",
        action="store_true",
        help="oznacz jako przeczytane. Domyślnie nieprzeczytane, żeby moduł "
             "skrzynki zobaczył je jako nowe.",
    )
    p.add_argument("--przerwa", type=float, default=0.3,
                   help="przerwa między wiadomościami w sekundach")
    p.add_argument("--limit", type=int, help="wrzuć tylko pierwsze N plików")
    args = p.parse_args()

    katalog = Path(args.katalog)
    if not katalog.is_dir():
        print(f"BŁĄD: nie ma katalogu {katalog}. Najpierw uruchom eksport_eml.py.",
              file=sys.stderr)
        return 2

    pliki = sorted(katalog.glob("*.eml"))
    if args.limit:
        pliki = pliki[: args.limit]
    if not pliki:
        print(f"BŁĄD: brak plików .eml w {katalog}", file=sys.stderr)
        return 1

    if args.podglad:
        print(f"PODGLĄD — nic nie zostanie wrzucone na skrzynkę.\n")
        print(f"Folder docelowy: {args.folder}")
        print(f"Plików: {len(pliki)}\n")
        for sciezka in pliki:
            wiadomosc = message_from_bytes(sciezka.read_bytes(), policy=policy.default)
            temat = str(wiadomosc["Subject"] or "")
            print(f"  {sciezka.name:<28} {str(wiadomosc['Date'])[:31]:<33} "
                  f"{temat[:46]}")
        print()
        print("Żeby wrzucić, ustaw IMAP_HOST / IMAP_USER / IMAP_PASS "
              "i uruchom bez --podglad.")
        return 0

    host = os.environ.get("IMAP_HOST")
    user = os.environ.get("IMAP_USER")
    haslo = os.environ.get("IMAP_PASS")
    brakujace = [n for n, v in (("IMAP_HOST", host), ("IMAP_USER", user),
                                ("IMAP_PASS", haslo)) if not v]
    if brakujace:
        print(f"BŁĄD: brak zmiennych środowiskowych: {', '.join(brakujace)}",
              file=sys.stderr)
        print("Patrz nagłówek tego pliku — dane dostępowe nie idą w argumentach.",
              file=sys.stderr)
        return 2

    flagi = "(\\Seen)" if args.przeczytane else None

    print(f"Łączę się z {host} jako {user}")
    try:
        poczta = imaplib.IMAP4_SSL(host)
        poczta.login(user, haslo)
    except imaplib.IMAP4.error as e:
        print(f"BŁĄD logowania: {e}", file=sys.stderr)
        print("Gmail wymaga hasła aplikacji i włączonego IMAP.", file=sys.stderr)
        return 1

    folder = nazwa_folderu(args.folder)
    status, _ = poczta.create(folder)
    if status == "OK":
        print(f"Utworzono folder {args.folder}")
    else:
        print(f"Folder {args.folder} już istnieje — dokładam do niego")

    udane = 0
    nieudane: list[str] = []
    for sciezka in pliki:
        surowe = sciezka.read_bytes()
        data = czas_imap(surowe)
        try:
            status, odpowiedz = poczta.append(folder, flagi, data, surowe)
        except imaplib.IMAP4.error as e:
            nieudane.append(f"{sciezka.name}: {e}")
            continue
        if status == "OK":
            udane += 1
            print(f"  + {sciezka.name}")
        else:
            nieudane.append(f"{sciezka.name}: {odpowiedz}")
        time.sleep(args.przerwa)

    poczta.logout()

    print()
    print(f"Wrzucono {udane} z {len(pliki)} wiadomości do folderu {args.folder}.")
    if nieudane:
        print(f"Nie udało się {len(nieudane)}:")
        for linia in nieudane[:10]:
            print(f"  - {linia}")
    print()
    print("Nic nie zostało wysłane — APPEND tylko wkłada wiadomości do folderu.")
    print("Po testach usuń folder i skrzynka wraca do stanu wyjściowego.")
    return 0 if not nieudane else 1


if __name__ == "__main__":
    raise SystemExit(main())
