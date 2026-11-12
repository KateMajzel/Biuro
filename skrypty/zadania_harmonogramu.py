#!/usr/bin/env python3
"""Rejestruje zadania w Harmonogramie zadań Windows.

    python skrypty/zadania_harmonogramu.py                # pokaż, co zrobi
    python skrypty/zadania_harmonogramu.py --zrob         # zarejestruj
    python skrypty/zadania_harmonogramu.py --stan         # co jest teraz
    python skrypty/zadania_harmonogramu.py --usun --zrob  # wypisz zadania

Po co skrypt, gdy to samo da się zrobić w okienku. Zadanie w Harmonogramie
wymaga ustawienia pięciu rzeczy w czterech zakładkach i każda z nich ma
domyślną wartość, która tu nie pasuje: ścieżka do `python.exe` musi być
z katalogu `.venv`, katalog startowy musi być katalogiem projektu, a zadanie
musi działać w kontekście zalogowanego użytkownika, bo Ollama startuje jako
Twój proces. Pomyłka w którejkolwiek z nich daje zadanie, które **uruchamia
się i cicho nie działa** — w historii Harmonogramu widać „zakończono
pomyślnie", bo python wystartował i zaraz padł.

Co rejestruje:

| zadanie | kiedy | co robi |
|---|---|---|
| poczta | co 4 godziny | przejście po skrzynce, wersje robocze odpowiedzi |
| kopia | raz w tygodniu | kopia bazy i dokumentów |
| retencja | raz w miesiącu | wyznacza terminy usunięcia danych, NIC nie usuwa |

Przebieg poczty **nie wysyła żadnej wiadomości** — tworzy wersje robocze
w Twojej skrzynce. Zadanie retencji działa bez `--usun`: wypisuje, co byłoby
do usunięcia, decyzję podejmujesz sama.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
PYTHON = KORZEN / ".venv" / "Scripts" / "python.exe"

PRZEDROSTEK = "Biuro Bielik"

ZADANIA = [
    {
        "nazwa": f"{PRZEDROSTEK} - poczta",
        "plik": "poczta",
        "skrypt": r"skrypty\sprawdz_maile.py",
        "argumenty": "--dni 3",
        "harmonogram": ["/SC", "HOURLY", "/MO", "4", "/ST", "07:00"],
        "opis": "co 4 godziny od 7:00 — przejście po skrzynce",
    },
    {
        "nazwa": f"{PRZEDROSTEK} - kopia zapasowa",
        "plik": "kopia-zapasowa",
        "skrypt": r"skrypty\kopia_zapasowa.py",
        "argumenty": "",
        "harmonogram": ["/SC", "WEEKLY", "/D", "SUN", "/ST", "22:00"],
        "opis": "w niedziele o 22:00 — kopia bazy i dokumentów",
    },
    {
        "nazwa": f"{PRZEDROSTEK} - retencja",
        "plik": "retencja",
        "skrypt": r"skrypty\retencja.py",
        "argumenty": "--ustaw-terminy",
        "harmonogram": ["/SC", "MONTHLY", "/D", "1", "/ST", "21:00"],
        "opis": "pierwszego dnia miesiąca o 21:00 — wyznacza terminy, nie usuwa",
    },
]


def czy_windows() -> bool:
    return os.name == "nt"


KATALOG_ZADAN = KORZEN / "zadania"

OGONKI = str.maketrans({
    "ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n", "ó": "o",
    "ś": "s", "ź": "z", "ż": "z", "—": "-", "–": "-",
})


def bez_ogonkow(tekst: str) -> str:
    return tekst.translate(OGONKI).encode("ascii", "ignore").decode("ascii")


def zapisz_opakowanie(zadanie: dict) -> Path:
    """Tworzy plik .cmd, na który wskaże Harmonogram.

    Bez opakowania polecenie dla `schtasks` musiałoby zawierać cudzysłowy
    wewnątrz cudzysłowów — ścieżkę do python.exe i katalog projektu wewnątrz
    wartości `/TR`. `schtasks` tego nie parsuje poprawnie i tworzy zadanie,
    które przy uruchomieniu nie znajduje interpretera. Plik .cmd sprowadza
    `/TR` do jednej ścieżki bez zagnieżdżeń.

    Drugi zysk jest praktyczny: to, co uruchamia Harmonogram, możesz kliknąć
    dwukrotnie i zobaczyć na własne oczy. Zadanie, które „kończy się
    pomyślnie" i nic nie robi, jest najtrudniejsze do zdiagnozowania.
    """
    KATALOG_ZADAN.mkdir(exist_ok=True)
    plik = KATALOG_ZADAN / (zadanie["plik"] + ".cmd")
    polecenie = f'"%PY%" {zadanie["skrypt"]} {zadanie["argumenty"]}'.rstrip()
    plik.write_text(
        "@echo off\n"
        "rem Plik generowany przez skrypty/zadania_harmonogramu.py\n"
        "rem Na ten plik wskazuje zadanie w Harmonogramie zadan Windows.\n"
        # Plik .cmd musi być czystym ASCII — konsola Windows otwiera go
        # w stronie kodowej systemu, nie w UTF-8.
        f"rem {bez_ogonkow(zadanie['opis'])}\n"
        "rem Mozesz go kliknac dwukrotnie, zeby sprawdzic, co robi zadanie.\n"
        "\n"
        'cd /d "%~dp0.."\n'
        "set PY=.venv\\Scripts\\python.exe\n"
        "if not exist \"%PY%\" (\n"
        "    echo Brak srodowiska .venv w katalogu projektu.\n"
        "    exit /b 1\n"
        ")\n"
        f"{polecenie}\n",
        encoding="ascii",
        # CRLF jawnie. Pliki wsadowe Windowsa wymagają tych końców linii —
        # przy samym LF etykiety i `goto` potrafią się rozsypać, a okno
        # konsoli miga i znika bez komunikatu. Domyślne zachowanie dałoby
        # tu CRLF tylko dlatego, że skrypt uruchamiany jest na Windowsie;
        # jawny zapis nie zależy od tego, gdzie plik powstał.
        newline="\r\n",
    )
    return plik


def polecenie_tworzace(zadanie: dict) -> list[str]:
    # /IT - zadanie widzi sesję zalogowanego użytkownika. Bez tego Ollama,
    #       która działa jako proces użytkownika, jest nieosiągalna.
    return [
        "schtasks", "/Create",
        "/TN", zadanie["nazwa"],
        "/TR", str(KATALOG_ZADAN / (zadanie["plik"] + ".cmd")),
        *zadanie["harmonogram"],
        "/IT",
        "/F",
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zrob", action="store_true", help="wykonaj")
    parser.add_argument("--usun", action="store_true", help="wypisz zadania")
    parser.add_argument("--stan", action="store_true", help="pokaż zarejestrowane")
    args = parser.parse_args()

    if not czy_windows():
        print("Ten skrypt działa tylko na Windowsie (używa schtasks).")
        print("Na Linuksie albo macOS użyj crona — przykładowe wpisy:")
        for z in ZADANIA:
            print(f"  # {z['opis']}")
            unix = z["skrypt"].replace("\\", "/")
            print(f"  cd {KORZEN} && .venv/bin/python {unix} {z['argumenty']}".rstrip())
        return 1

    if args.stan:
        for z in ZADANIA:
            wynik = subprocess.run(
                ["schtasks", "/Query", "/TN", z["nazwa"], "/FO", "LIST"],
                capture_output=True, text=True,
            )
            if wynik.returncode == 0:
                print(f"JEST       {z['nazwa']}")
                for linia in wynik.stdout.splitlines():
                    if any(k in linia for k in ("Następny", "Next", "Stan", "Status")):
                        print(f"           {linia.strip()}")
            else:
                print(f"brak       {z['nazwa']}")
        return 0

    if not PYTHON.exists():
        print(f"Nie ma {PYTHON}")
        print("Zadania muszą wskazywać python.exe ze środowiska .venv, nie systemowy.")
        return 1

    if args.usun:
        print("Zadania do wypisania z Harmonogramu:\n")
        for z in ZADANIA:
            print(f"  {z['nazwa']}")
        if not args.zrob:
            print("\nTo był podgląd. Żeby wykonać: --usun --zrob")
            return 0
        for z in ZADANIA:
            wynik = subprocess.run(
                ["schtasks", "/Delete", "/TN", z["nazwa"], "/F"],
                capture_output=True, text=True,
            )
            print(f"  {'usunięte' if wynik.returncode == 0 else 'nie było'}  {z['nazwa']}")
        return 0

    print(f"Katalog projektu: {KORZEN}")
    print(f"Python:           {PYTHON}\n")
    for z in ZADANIA:
        print(f"  {z['nazwa']}")
        print(f"      {z['opis']}")
        print(f"      {z['skrypt']} {z['argumenty']}".rstrip())
    print()

    if not args.zrob:
        print("To był podgląd. Nic nie zostało zarejestrowane. Żeby wykonać:")
        print("  python skrypty/zadania_harmonogramu.py --zrob")
        print("\nUruchom to z wiersza poleceń otwartego JAKO ADMINISTRATOR —")
        print("bez tego schtasks odmówi utworzenia zadania.")
        return 0

    bledy = 0
    for z in ZADANIA:
        opakowanie = zapisz_opakowanie(z)
        print(f"  plik            {opakowanie.relative_to(KORZEN)}")
        wynik = subprocess.run(polecenie_tworzace(z), capture_output=True, text=True)
        if wynik.returncode == 0:
            print(f"  zarejestrowane  {z['nazwa']}")
        else:
            bledy += 1
            komunikat = (wynik.stderr or wynik.stdout).strip().splitlines()
            print(f"  BŁĄD            {z['nazwa']}")
            print(f"                  {komunikat[0] if komunikat else wynik.returncode}")

    if bledy:
        print(f"\n{bledy} z {len(ZADANIA)} zadań się nie udało.")
        print("Najczęstsza przyczyna: wiersz poleceń bez uprawnień administratora.")
        return 1

    print("\nGotowe. Sprawdź, czy pierwsze przejście faktycznie coś zrobiło:")
    print("  python skrypty/zadania_harmonogramu.py --stan")
    print("\nZadanie, które 'zakończyło się pomyślnie' w Harmonogramie, nie znaczy,")
    print("że przebieg się udał — python mógł wystartować i zaraz paść. Po pierwszym")
    print("uruchomieniu zajrzyj do skrzynki i sprawdź, czy są nowe wersje robocze.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
