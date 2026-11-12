#!/usr/bin/env python3
"""Czy w plikach repozytorium jest numer PESEL, który mógłby należeć do osoby.

Numer jest groźny tylko wtedy, gdy ma jednocześnie poprawną sumę kontrolną
i koduje datę, która istnieje w kalendarzu. Przykłady w testach celowo łamią
jeden z tych warunków: literówka w numerze (zła suma) albo dzień 33.
Poprzednia wersja tego sprawdzenia wymagała daty 00-00 i odrzucała oba takie
przypadki, choć żaden z nich nie może być prawdziwym numerem.
"""
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from biuro.deterministyczne import data_z_peselu, suma_kontrolna_pesel  # noqa: E402

pliki = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                       check=True).stdout.splitlines()
grozne = []
for nazwa in pliki:
    if not nazwa.endswith((".py", ".md", ".txt", ".json", ".yaml", ".yml", ".csv")):
        continue
    try:
        tekst = Path(nazwa).read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    for nr, linia in enumerate(tekst.splitlines(), 1):
        for kandydat in re.findall(r"(?<!\d)\d{11}(?!\d)", linia):
            if suma_kontrolna_pesel(kandydat) and data_z_peselu(kandydat) is not None:
                grozne.append(f"{nazwa}, linia {nr}")

if grozne:
    print("BŁĄD: numer z poprawną sumą kontrolną i istniejącą datą urodzenia:")
    for g in sorted(set(grozne)):
        print(f"  {g}")
    sys.exit(1)
print(f"OK: w {len(pliki)} plikach nie ma numeru PESEL, który mógłby należeć do osoby")
