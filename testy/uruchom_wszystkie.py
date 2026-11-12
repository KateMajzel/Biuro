#!/usr/bin/env python3
"""Uruchamia wszystkie testy, które nie potrzebują modelu ani sieci.

    python testy/uruchom_wszystkie.py

Co jest sprawdzane:
  - warstwa deterministyczna: PESEL, telefon, e-mail, kod pocztowy, walidacja
  - składanie promptów: czy sekcje wchodzą i czy dane wrażliwe NIE wchodzą
  - generowanie umowy z szablonu i wykazu CSV dla UFG

Czego te testy NIE sprawdzają: jakości odpowiedzi modelu. Tego nie da się
zmierzyć testem jednostkowym - do tego jest harness ewaluacyjny.
"""

import os
import subprocess
import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KORZEN))

TESTY = (
    "testy/test_deterministyczne.py",
    "testy/test_skladanie_promptow.py",
    "testy/test_dokumenty.py",
    "testy/test_pobieranie_poczty.py",
    "testy/test_flaga_do_czlowieka.py",
    "testy/test_rag_embeddingi.py",
    "testy/test_dopasowanie_zgloszen.py",
    "testy/test_polszczyzna.py",
    "testy/test_wybor_wyjazdu.py",
    "testy/test_wyjazd_przy_zgloszeniu.py",
    "testy/test_urwany_json.py",
    "testy/test_podsumowanie_poczty.py",
    "testy/test_panel.py",
)


def main() -> int:
    # Baza testowa startuje pusta. Bez tego wiersze z poprzednich przebiegów
    # zostają i testy dokumentów trafiają na zgłoszenie z wczoraj — u jednej
    # osoby cały zestaw przechodził, u drugiej dawał dziewięć błędów na tym
    # samym kodzie. Wynik testów nie może zależeć od tego, ile razy je
    # wcześniej uruchomiono. Plik jest artefaktem testowym i jest w .gitignore;
    # produkcyjnej bazy ta ścieżka nie dotyka (patrz testy/baza_testowa.py).
    baza_testowa = KORZEN / "dane" / "testowa.sqlite"
    if baza_testowa.exists():
        baza_testowa.unlink()
        print(f"Usunięta stara baza testowa: {baza_testowa.name}")

    bledy = []
    for sciezka in TESTY:
        print(f"\n{'=' * 64}\n{sciezka}\n{'=' * 64}")
        srodowisko = dict(os.environ)
        # izolacja bazy także dla podprocesów
        srodowisko["BIURO_BAZA"] = str(KORZEN / "dane" / "testowa.sqlite")
        srodowisko["BIURO_WYJAZDY"] = str(KORZEN / "testy" / "wyjazdy_testowe.yaml")
        wynik = subprocess.run(
            [sys.executable, str(KORZEN / sciezka)], cwd=KORZEN, env=srodowisko
        )
        if wynik.returncode != 0:
            bledy.append(sciezka)

    print(f"\n{'=' * 64}")
    if bledy:
        print(f"NIEPOWODZENIE w: {', '.join(bledy)}")
        return 1
    print(f"Wszystkie zestawy testów przeszły ({len(TESTY)}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
