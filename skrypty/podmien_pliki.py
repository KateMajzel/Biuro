#!/usr/bin/env python3
"""Podmienia pliki projektu wersjami z katalogu Pobrane.

    python skrypty/podmien_pliki.py              # pokaż, co by zrobił
    python skrypty/podmien_pliki.py --zrob       # wykonaj

Po co. Przeglądarka zapisuje pliki do Pobranych, czasem dokładając „(1)"
do nazwy. Ręczne przenoszenie ich do właściwych katalogów to miejsce, gdzie
łatwo nadpisać niewłaściwy plik albo przenieść starszą kopię — raz już tak
cofnęły się zmiany z całego dnia.

Jak ustala, gdzie co trafia:

  1. TRASY poniżej — dla plików, których w projekcie jeszcze nie ma.
  2. Jeśli pliku nie ma w TRASACH, szuka tej samej nazwy w projekcie.
     Gdy znajdzie dokładnie jedno miejsce, tam go kładzie. Gdy znajdzie
     kilka — nie zgaduje, tylko wypisuje i pomija.

Przed każdą podmianą robi kopię starej wersji w `kopie_zapasowe/<data>/`,
z zachowaniem struktury katalogów. Nic nie jest usuwane.

Bierze tylko pliki zmienione w Pobranych w ciągu ostatnich `--godziny`
godzin (domyślnie 24), żeby nie wciągnąć przypadkiem kopii z poprzedniego
tygodnia. Gdy ta sama nazwa występuje w kilku wariantach („plik.py",
„plik (1).py"), wybiera najnowszy.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent

# Pliki, których w projekcie jeszcze nie ma — nie da się ich znaleźć po nazwie.
TRASY: dict[str, str] = {
    "test_pobieranie_poczty.py": "testy",
    "wypelnij.py": "korpus",
    "import_skrzynki.py": "korpus",
    "imap_client.py": "biuro/mail",
    "uruchom_wszystkie.py": "testy",
    "baza_testowa.py": "testy",
    "adapter.py": "korpus",
    "podmien_pliki.py": "skrypty",
    "wyczysc_umowy.py": "skrypty",
    "wyczysc_zgloszenia.py": "skrypty",
}

# Katalogi, w których nie szukamy miejsca docelowego ani plików do kopii.
POMIJANE = {
    ".git", ".venv", "venv", "__pycache__", "kopie_zapasowe",
    "out", "dane", ".pytest_cache", "node_modules",
}

NUMER_KOPII = re.compile(r"^(?P<nazwa>.+?) \(\d+\)(?P<rozsz>\.[A-Za-z0-9]+)$")


def katalog_pobranych(podany: str | None) -> Path:
    if podany:
        return Path(podany).expanduser()
    dom = Path.home()
    for nazwa in ("Downloads", "Pobrane"):
        kandydat = dom / nazwa
        if kandydat.is_dir():
            return kandydat
    return dom / "Downloads"


def nazwa_bazowa(plik: Path) -> str:
    """'imap_client (1).py' -> 'imap_client.py'"""
    dopasowanie = NUMER_KOPII.match(plik.name)
    if dopasowanie:
        return dopasowanie.group("nazwa") + dopasowanie.group("rozsz")
    return plik.name


def w_pomijanym(sciezka: Path) -> bool:
    return any(czesc in POMIJANE for czesc in sciezka.parts)


def miejsca_w_projekcie(nazwa: str) -> list[Path]:
    znalezione = [
        p for p in KORZEN.rglob(nazwa)
        if p.is_file() and not w_pomijanym(p.relative_to(KORZEN))
    ]
    return sorted(znalezione)


def zbierz_kandydatow(pobrane: Path, godziny: float) -> dict[str, Path]:
    """nazwa bazowa -> najnowszy plik z Pobranych o tej nazwie."""
    if not pobrane.is_dir():
        print(f"Nie ma katalogu {pobrane}. Wskaż go przez --pobrane.")
        return {}

    granica = time.time() - godziny * 3600
    najnowsze: dict[str, Path] = {}
    for plik in pobrane.iterdir():
        if not plik.is_file() or plik.stat().st_mtime < granica:
            continue
        nazwa = nazwa_bazowa(plik)
        obecny = najnowsze.get(nazwa)
        if obecny is None or plik.stat().st_mtime > obecny.stat().st_mtime:
            najnowsze[nazwa] = plik
    return najnowsze


def ustal_cel(nazwa: str) -> tuple[Path | None, str]:
    """Zwraca (ścieżka docelowa, powód)."""
    if nazwa in TRASY:
        return KORZEN / TRASY[nazwa] / nazwa, "z tabeli TRASY"

    miejsca = miejsca_w_projekcie(nazwa)
    if len(miejsca) == 1:
        return miejsca[0], "jedno miejsce w projekcie"
    if not miejsca:
        # Nowy test nie wymaga dopisywania do TRASY: pliki test_*.py mają
        # jedno możliwe miejsce.
        if nazwa.startswith("test_") and nazwa.endswith(".py"):
            return KORZEN / "testy" / nazwa, "nowy test"
        return None, "nie ma takiego pliku w projekcie i nie ma go w TRASACH"
    lista = ", ".join(str(p.relative_to(KORZEN)) for p in miejsca)
    return None, f"nazwa występuje w {len(miejsca)} miejscach: {lista}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pobrane", help="katalog Pobranych, gdy nie jest standardowy")
    parser.add_argument("--godziny", type=float, default=24,
                        help="bierz pliki zmienione w ciągu tylu godzin")
    parser.add_argument("--zrob", action="store_true",
                        help="wykonaj podmianę (bez tego tylko podgląd)")
    parser.add_argument("--tylko", nargs="*", metavar="NAZWA",
                        help="ogranicz do podanych nazw plików")
    args = parser.parse_args()

    pobrane = katalog_pobranych(args.pobrane)
    print(f"Pobrane:  {pobrane}")
    print(f"Projekt:  {KORZEN}")
    print(f"Okno:     pliki zmienione w ostatnich {args.godziny:g} h\n")

    kandydaci = zbierz_kandydatow(pobrane, args.godziny)
    if args.tylko:
        kandydaci = {k: v for k, v in kandydaci.items() if k in set(args.tylko)}
    if not kandydaci:
        print("Brak plików do podmiany w tym oknie czasowym.")
        print("Jeśli pobrałaś je dawniej, zwiększ --godziny.")
        return 1

    do_zrobienia: list[tuple[Path, Path]] = []
    pominiete: list[tuple[str, str]] = []

    for nazwa in sorted(kandydaci):
        zrodlo = kandydaci[nazwa]
        cel, powod = ustal_cel(nazwa)
        if cel is None:
            pominiete.append((nazwa, powod))
            continue
        do_zrobienia.append((zrodlo, cel))
        wzgledna = cel.relative_to(KORZEN)
        stan = "nadpisze" if cel.exists() else "NOWY plik"
        wariant = "" if zrodlo.name == nazwa else f"  [z {zrodlo.name}]"
        print(f"  {nazwa:32} -> {wzgledna}   ({stan}, {powod}){wariant}")

    if pominiete:
        print("\nPominięte — nie zgaduję, gdzie mają trafić:")
        for nazwa, powod in pominiete:
            print(f"  {nazwa:32} {powod}")
        print("  Dopisz je do tabeli TRASY w tym skrypcie albo przenieś ręcznie.")

    if not do_zrobienia:
        return 1

    if not args.zrob:
        print(f"\nTo był podgląd. Nic nie zmieniłam. Żeby wykonać:")
        print("  python skrypty/podmien_pliki.py --zrob")
        return 0

    znacznik = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    kopie = KORZEN / "kopie_zapasowe" / znacznik
    print()
    for zrodlo, cel in do_zrobienia:
        wzgledna = cel.relative_to(KORZEN)
        if cel.exists():
            kopia = kopie / wzgledna
            kopia.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cel, kopia)
        cel.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(zrodlo, cel)
        print(f"  podmienione  {wzgledna}")

    print(f"\nKopie starych wersji: kopie_zapasowe\\{znacznik}\\")
    print("\nSprawdź, czy nic się nie zepsuło:")
    print("  python testy/uruchom_wszystkie.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
