"""Izolacja danych testowych od produkcyjnych.

**Importuj to PRZED jakimkolwiek importem z `biuro`.** Ustawia BIURO_BAZA
i BIURO_WYJAZDY, czyli ścieżki, których `biuro` używa zamiast tych
z `config.yaml`.

Dlaczego to istnieje: `test_dokumenty.py` i `test_skladanie_promptow.py`
czyszczą tabele przed przebiegiem, żeby wynik nie zależał od poprzedniego.
Dopóki szły do bazy z `config.yaml`, uruchomienie testów po wejściu
prawdziwych zgłoszeń usuwałoby je razem z umowami i rejestrem dla UFG.

Druga warstwa zabezpieczenia jest w `wymagaj_bazy_testowej()`: test odmawia
uruchomienia, jeśli BIURO_BAZA nie jest ustawione. Sam import tego modułu je
ustawia, więc warunek jest spełniony — ale gdyby ktoś w przyszłości dopisał
test bez tego importu, dostanie błąd zamiast wyczyszczonej bazy firmy.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
PLIK_TESTOWY = KORZEN / "dane" / "testowa.sqlite"
WYJAZDY_TESTOWE = Path(__file__).resolve().parent / "wyjazdy_testowe.yaml"

# musi być ustawione przed pierwszym użyciem biuro.config
os.environ["BIURO_BAZA"] = str(PLIK_TESTOWY)

# Katalog wyjazdów też musi być testowy. Testy generujące umowę i odprawę
# szukały wyjazdu z pliku przykładowego, więc wpisanie prawdziwych wyjazdów
# firmy wywracało je z KeyError. Przebieg testów nie może zależeć od tego,
# co firma aktualnie sprzedaje.
os.environ["BIURO_WYJAZDY"] = str(WYJAZDY_TESTOWE)


def wymagaj_bazy_testowej() -> None:
    if not os.getenv("BIURO_BAZA"):
        print(
            "PRZERWANE: BIURO_BAZA nie jest ustawione. Ten test czyści tabele, "
            "więc bez izolacji usunąłby dane produkcyjne.\n"
            "Dopisz `import baza_testowa` jako PIERWSZY import w pliku testu.",
            file=sys.stderr,
        )
        raise SystemExit(2)


def wyczysc() -> None:
    """Usuwa plik bazy testowej, żeby każdy przebieg startował od zera."""
    wymagaj_bazy_testowej()
    plik = Path(os.environ["BIURO_BAZA"])
    if plik.exists():
        plik.unlink()
