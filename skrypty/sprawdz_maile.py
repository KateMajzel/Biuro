#!/usr/bin/env python3
"""Jedno przejście po skrzynce: klasyfikacja, ekstrakcja, drafty.

    python skrypty/sprawdz_maile.py --na-sucho     # nic nie zapisuje, nie tworzy draftów
    python skrypty/sprawdz_maile.py --dni 14
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from biuro import baza, tfg  # noqa: E402
from biuro.mail.pipeline import przebieg  # noqa: E402


RODZAJE_PO_LUDZKU = {
    "formularz": "zgłoszenie z formularza",
    "dane_do_umowy": "dane do umowy",
    "akceptacja_umowy": "akceptacja umowy",
    "rezerwacja": "rezerwacja",
    "pytanie": "pytanie",
    "spam": "spam",
    "usuniete": "zgłoszenie usunięte ręcznie",
    "inne": "inne",
    "błąd": "BŁĄD",
    "czeka na kolejny przebieg": "czeka na kolejny przebieg",
}


def odmien(ile: int, jedna: str, dwie: str, piec: str) -> str:
    """Polska odmiana liczebnika: 1 wiadomość, 2 wiadomości, 5 wiadomości.

    „1 wiadomości oznaczonych do Ciebie" to drobiazg, ale widoczny w każdym
    przebiegu i w każdym zrzucie ekranu.
    """
    if ile == 1:
        return f"{ile} {jedna}"
    reszta_10, reszta_100 = ile % 10, ile % 100
    if 2 <= reszta_10 <= 4 and not 12 <= reszta_100 <= 14:
        return f"{ile} {dwie}"
    return f"{ile} {piec}"


def _skroc(tekst: str, ile: int) -> str:
    tekst = (tekst or "").replace("\n", " ").strip()
    return tekst if len(tekst) <= ile else tekst[: ile - 1] + "…"


def wypisz_podsumowanie(wynik, dni: int, na_sucho: bool) -> None:
    """Podsumowanie pisane dla osoby, która właśnie kliknęła „Sprawdź pocztę".

    Odpowiada na cztery pytania w kolejności, w jakiej się je zadaje: ile tego
    było, co to było, co z tego powstało, co wymaga mojej uwagi. Surowy
    słownik liczników odpowiadał tylko na trzecie, i to szyfrem.
    """
    liczby = wynik.liczby
    print(f"\n{'=' * 64}")
    print(f"Wiadomości w skrzynce:        {liczby['w_skrzynce']}")
    print(f"Wiadomości z ostatnich {dni} dni: {liczby['w_oknie']}")
    print(f"  obsłużone wcześniej:        {liczby['pominiete']}")
    print(f"  obsłużone teraz:            {liczby['przetworzone']}")
    if liczby["odlozone"]:
        print(f"  czekają na kolejny przebieg: {liczby['odlozone']}")

    if wynik.wiadomosci:
        print("\nWiadomości:")
        for w in wynik.wiadomosci:
            rodzaj = RODZAJE_PO_LUDZKU.get(w.rodzaj, w.rodzaj)
            znaczniki = []
            if w.wczesniej:
                znaczniki.append("obsłużone wcześniej")
            if w.do_czlowieka:
                znaczniki.append("DO CIEBIE")
            if w.draft:
                znaczniki.append("draft gotowy")
            ogon = f"   [{', '.join(znaczniki)}]" if znaczniki else ""
            print(f"  {_skroc(w.od, 28):<28} {rodzaj:<24} "
                  f"{_skroc(w.temat, 46)}{ogon}")

    print("\nCo z tego powstało:")
    print(f"  zgłoszenia zapisane w bazie:  {liczby['zgloszenia']}")
    print(f"  uzupełnione dane do umowy:    {liczby['dane_do_umowy']}")
    print(f"  akceptacje umów:              {liczby['akceptacje']}")
    print(f"  rezerwacje:                   {liczby['rezerwacje']}")
    print(f"  robocze wersje odpowiedzi:    {liczby['drafty']}")

    uwaga = []
    if liczby["do_czlowieka"]:
        uwaga.append(
            odmien(liczby["do_czlowieka"], "wiadomość oznaczona",
                   "wiadomości oznaczone", "wiadomości oznaczonych")
            + " do Ciebie — bez draftu, odpowiedz sama"
        )
    if liczby["do_weryfikacji"]:
        uwaga.append(
            odmien(liczby["do_weryfikacji"], "zgłoszenie", "zgłoszenia",
                   "zgłoszeń") + " z danymi do sprawdzenia"
        )
    if liczby["bledy"]:
        uwaga.append(
            odmien(liczby["bledy"], "wiadomość zakończona",
                   "wiadomości zakończone", "wiadomości zakończonych")
            + " błędem — szczegóły wyżej"
        )
    if uwaga:
        print("\nWymaga Twojej uwagi:")
        for linia in uwaga:
            print(f"  - {linia}")

    if na_sucho:
        print("\n(tryb na sucho — nic nie zostało zapisane)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dni", type=int, default=7, help="jak daleko w przeszłość")
    parser.add_argument(
        "--na-sucho",
        action="store_true",
        help="pokaż, co by się stało, bez zapisu i bez tworzenia draftów",
    )
    parser.add_argument(
        "--ponownie",
        action="store_true",
        help="przetwórz też wiadomości już przetworzone (kalibracja promptu; "
             "w folderze wersji roboczych powstaną duplikaty draftów)",
    )
    parser.add_argument(
        "--szczegoly",
        action="store_true",
        help="wypisz diagnostykę każdej wiadomości: co wyciągnął regex, "
             "co model, co odrzuciła walidacja",
    )
    args = parser.parse_args()

    baza.inicjuj()
    wynik = przebieg(dni=args.dni, na_sucho=args.na_sucho,
                     ponownie=args.ponownie, szczegoly=args.szczegoly)
    wypisz_podsumowanie(wynik, dni=args.dni, na_sucho=args.na_sucho)

    # Przypomnienie o TFG pokazujemy tu, bo ten skrypt uruchamia się codziennie.
    # Przypomnienie w miejscu, do którego się nie zagląda, nie jest przypomnieniem.
    stan_tfg = tfg.stan()
    if stan_tfg.pilne():
        print(f"\n!!! {stan_tfg.komunikat()}")
    else:
        print(f"\n{stan_tfg.komunikat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
