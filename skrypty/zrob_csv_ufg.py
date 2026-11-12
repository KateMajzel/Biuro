#!/usr/bin/env python3
"""Miesięczny wykaz umów dla portalu UFG/TFG.

    python skrypty/zrob_csv_ufg.py --pola          # dostępne wartości do mapowania
    python skrypty/zrob_csv_ufg.py                 # za miesiąc poprzedni
    python skrypty/zrob_csv_ufg.py 2026 10         # za październik 2026
    python skrypty/zrob_csv_ufg.py 2026 10 --oznacz-zgloszone

Model nie bierze w tym udziału. Format kolumn pochodzi z config.yaml.
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from biuro import baza, tfg, ufg  # noqa: E402
from biuro.polszczyzna import umow as odmiana_umow  # noqa: E402


def pokaz_pola() -> None:
    print("Wartości dostępne do zmapowania na kolumny (config.yaml -> ufg.kolumny):\n")
    for nazwa, opis in ufg.DOSTEPNE_POLA.items():
        print(f"  {nazwa:20s} {opis}")
    print("\nPrzykład wpisu w config.yaml:")
    print('    - naglowek: "Numer umowy"')
    print("      pole: nr_umowy")
    print('    - naglowek: "Waluta"')
    print('      stala: "PLN"')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rok", nargs="?", type=int)
    parser.add_argument("miesiac", nargs="?", type=int)
    parser.add_argument("--pola", action="store_true",
                        help="wypisz dostępne wartości i zakończ")
    parser.add_argument("--oznacz-zgloszone", action="store_true",
                        help="oznacz umowy jako zgłoszone do UFG po wygenerowaniu pliku")
    args = parser.parse_args()

    if args.pola:
        pokaz_pola()
        return 0

    baza.inicjuj()

    if args.rok and args.miesiac:
        rok, miesiac = args.rok, args.miesiac
    else:
        dzisiaj = date.today()
        rok, miesiac = (
            (dzisiaj.year - 1, 12) if dzisiaj.month == 1 else (dzisiaj.year, dzisiaj.month - 1)
        )
        print(f"Bez podanego okresu biorę miesiąc poprzedni: {miesiac:02d}/{rok}\n")

    try:
        wynik = ufg.generuj(rok, miesiac, oznacz_zgloszone=args.oznacz_zgloszone)
    except RuntimeError as e:
        print(f"BŁĄD: {e}")
        return 1

    # Pierwsze zdanie ma odpowiadać na pytanie „i co z tego": za jaki okres,
    # ile umów, gdzie leży plik. Ostrzeżenia idą niżej i tylko wtedy, gdy są.
    print(f"Wykaz umów dla UFG — {wynik.okres}: {odmiana_umow(wynik.wiersze)}.")
    print(f"Folder: {Path(wynik.plik).parent}")
    print(f"Plik:   {Path(wynik.plik).name}")

    if wynik.wiersze == 0:
        print("\nW tym okresie nie zawarto żadnej umowy, więc plik ma same "
              "nagłówki. Sprawdź, czy deklaracja zerowa jest u Ciebie wymagana.")
        # Wykaz liczy się po dacie ZAWARCIA umowy, nie po terminie wyjazdu.
        # Umowa podpisana w listopadzie na wyjazd wrześniowy jest w wykazie
        # listopadowym — i to pytanie wraca, więc program sam podpowiada,
        # w których miesiącach umowy są.
        with baza.polaczenie() as conn:
            miesiace = conn.execute(
                "SELECT substr(data_zawarcia, 1, 7) AS okres, COUNT(*) AS ile "
                "FROM umowy GROUP BY okres ORDER BY okres"
            ).fetchall()
        if miesiace:
            print("\nWykaz obejmuje umowy ZAWARTE w danym miesiącu, a nie wyjazdy "
                  "odbywające się w tym miesiącu. Umowy w rejestrze:")
            for m in miesiace:
                rok_m, mies_m = m["okres"].split("-")
                print(f"  {mies_m}/{rok_m}: {odmiana_umow(m['ile'])}")

    if wynik.nieuzupelnione_kwoty:
        print(f"\nUWAGA: {odmiana_umow(wynik.nieuzupelnione_kwoty)} bez wpisanej ceny.")
        print("Uzupełnij `cena` w wyjazdy.yaml albo kwotę w rejestrze umów "
              "i wygeneruj plik ponownie.")

    if wynik.braki:
        print(f"\nUWAGA: {len(wynik.braki)} braków w danych:")
        for brak in wynik.braki:
            print(f"  - {brak}")

    if wynik.nieuzupelnione_kwoty or wynik.braki:
        print("\nPlik powstał, ale NIE JEST GOTOWY do wysłania do portalu.")
    elif wynik.wiersze:
        print("\nWszystkie pola wypełnione.")

    if args.oznacz_zgloszone and wynik.wiersze:
        print(f"\nOznaczono {odmiana_umow(wynik.wiersze)} jako zgłoszone do UFG.")

    print(f"\n{tfg.stan().komunikat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
