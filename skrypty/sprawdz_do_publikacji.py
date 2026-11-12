#!/usr/bin/env python3
"""Sprawdza, czy w plikach idących do repozytorium nie ma prawdziwych danych.

    python skrypty/sprawdz_do_publikacji.py

Uruchom to **przed `git push`**. Skrypt przechodzi po plikach, które NIE są
wykluczone przez `.gitignore`, i szuka w nich rzeczy, które nie powinny
opuścić Twojego dysku: numerów PESEL z poprawną sumą kontrolną, numerów NIP,
numerów rachunków, adresów e-mail poza domenami przykładowymi oraz nazwy
i domeny Twojej firmy.

Dlaczego to istnieje. `.gitignore` chroni katalogi, ale nie chroni przed
wklejeniem prawdziwego PESEL-u do testu, komentarza albo pliku README. Raz
wypchnięte do publicznego repozytorium dane zostają w historii gita nawet po
usunięciu pliku — a przy danych uczestników to nie jest usterka do poprawienia
następnym commitem.

Skrypt **nie wypisuje znalezionych wartości**. Pokazuje plik, numer linii
i rodzaj trafienia, żeby jego własne wyjście nie stało się drugim wyciekiem.

Kod wyjścia: 0 gdy czysto, 1 gdy cokolwiek znalazł.
"""

from __future__ import annotations

import re
import subprocess
from collections import Counter
import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent

# Domeny, które są przykładami i mają prawo zostać w repozytorium.
DOMENY_PRZYKLADOWE = (
    "example.com", "example.org", "example.net", "example.uk", "example.pl",
    "przyklad.example", "example", "localhost",
)

ROZSZERZENIA_TEKSTOWE = {
    ".py", ".md", ".yaml", ".yml", ".json", ".txt", ".csv", ".jsonl",
    ".toml", ".cfg", ".ini", ".html", ".css", ".js", ".example", "",
}

WAGI_PESEL = (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)
WAGI_NIP = (6, 5, 7, 2, 3, 4, 5, 6, 7)

WZ_11_CYFR = re.compile(r"(?<!\d)(\d{11})(?!\d)")
WZ_10_CYFR = re.compile(r"(?<!\d)(\d{10})(?!\d)")
WZ_RACHUNEK = re.compile(r"(?<!\d)(?:PL)?[\s-]?(\d[\s-]?){26}(?!\d)", re.IGNORECASE)
WZ_EMAIL = re.compile(r"\b[\w.+-]+@([\w-]+\.[\w.-]+)\b")


WIEK_PO_MIESIACU = {0: 1900, 20: 2000, 40: 2100, 60: 2200, 80: 1800}


def pesel_moze_byc_czyjs(cyfry: str) -> bool:
    """Czy ten numer PESEL może należeć do żywej osoby.

    Suma kontrolna nie wystarcza. Numery używane w testach tego projektu mają
    poprawną cyfrę kontrolną, ale kodują datę urodzenia `00-00`, która nie
    istnieje w żadnym wieku — dlatego wolno je trzymać w repozytorium.
    Zgłaszanie ich jako wyciek zasypałoby prawdziwe trafienia szumem,
    a skrypt, którego wyjście się ignoruje, nie chroni przed niczym.

    Ta sama reguła działa w drugą stronę w `biuro/deterministyczne.py`: numer
    kodujący nieistniejący dzień zostaje tam oznaczony do weryfikacji, bo
    z taką datą nie wolno wystawić umowy.
    """
    if len(cyfry) != 11:
        return False
    suma = sum(int(c) * w for c, w in zip(cyfry[:10], WAGI_PESEL))
    if (10 - suma % 10) % 10 != int(cyfry[10]):
        return False

    rr, mm, dd = int(cyfry[0:2]), int(cyfry[2:4]), int(cyfry[4:6])
    przesuniecie = (mm // 20) * 20
    wiek = WIEK_PO_MIESIACU.get(przesuniecie)
    if wiek is None:
        return False
    from datetime import date
    try:
        date(wiek + rr, mm - przesuniecie, dd)
    except ValueError:
        return False
    return True


def nip_poprawny(cyfry: str) -> bool:
    if len(cyfry) != 10:
        return False
    suma = sum(int(c) * w for c, w in zip(cyfry[:9], WAGI_NIP))
    return suma % 11 == int(cyfry[9])


def pliki_do_publikacji() -> list[Path]:
    """Pliki, których git NIE wyklucza. Bez gita — wszystko poza oczywistymi."""
    try:
        wynik = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=KORZEN, capture_output=True, text=True, timeout=30, check=True,
        )
        sciezki = [KORZEN / linia for linia in wynik.stdout.splitlines() if linia]
        if sciezki:
            return [p for p in sciezki if p.is_file()]
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass

    print("UWAGA: nie udało się zapytać gita, co jest wykluczone.")
    print("       Przechodzę po wszystkich plikach poza .venv, __pycache__ i .git.")
    print("       Wynik może zawierać pliki, które i tak nie trafiłyby do repo.\n")
    pomijane_katalogi = {".git", ".venv", "venv", "__pycache__", ".pytest_cache",
                         "dane", "nagrania", "wsad", "kopie_zapasowe", "out"}
    # Bez gita nie znamy reguł z .gitignore, więc pomijamy przynajmniej pliki,
    # które z definicji nigdy nie trafiają do repozytorium. Inaczej skrypt
    # zgłosiłby hasło z `.env` jako wyciek, choć ten plik jest wykluczony.
    pomijane_pliki = {".env", "config.yaml", "wyjazdy.yaml"}
    return [
        p for p in KORZEN.rglob("*")
        if p.is_file()
        and not (set(p.relative_to(KORZEN).parts) & pomijane_katalogi)
        and p.name not in pomijane_pliki
    ]


def wlasne_slowa() -> list[str]:
    """Nazwa i domena firmy z lokalnej konfiguracji, do wyszukania w repo.

    Czytamy je z `config.yaml`, który sam do repozytorium nie trafia. Chodzi
    o przypadek, w którym nazwa firmy albo adres jej strony wyciekły do
    komentarza, testu albo przykładu w dokumentacji.
    """
    plik = KORZEN / "config.yaml"
    if not plik.exists():
        return []
    slowa: list[str] = []
    for linia in plik.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" not in linia:
            continue
        klucz, _, wartosc = linia.partition(":")
        if not any(k in klucz.lower() for k in ("nazwa", "domena", "strona", "www")):
            continue
        wartosc = wartosc.strip().strip('"\'')
        if len(wartosc) >= 6 and not wartosc.startswith("["):
            slowa.append(wartosc)
    return slowa


def main() -> int:
    pliki = pliki_do_publikacji()
    slowa_firmy = wlasne_slowa()

    print(f"Plików do publikacji: {len(pliki)}")
    if slowa_firmy:
        print(f"Szukam też {len(slowa_firmy)} nazw własnych z config.yaml "
              "(nie wypisuję ich)")
    print()

    trafienia: list[tuple[str, int, str]] = []
    maile_po_pliku: "Counter[tuple[str, str]]" = Counter()
    nieczytane = 0

    for plik in sorted(pliki):
        wzgledna = plik.relative_to(KORZEN).as_posix()
        if plik.suffix.lower() not in ROZSZERZENIA_TEKSTOWE:
            continue
        try:
            tekst = plik.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            nieczytane += 1
            continue

        wlasny_plik = wzgledna.endswith("skrypty/sprawdz_do_publikacji.py")

        for nr, linia in enumerate(tekst.splitlines(), 1):
            if wlasny_plik:
                continue

            for dopasowanie in WZ_11_CYFR.finditer(linia):
                if pesel_moze_byc_czyjs(dopasowanie.group(1)):
                    trafienia.append((wzgledna, nr, "PESEL mogący należeć do osoby"))

            for dopasowanie in WZ_10_CYFR.finditer(linia):
                if nip_poprawny(dopasowanie.group(1)):
                    trafienia.append((wzgledna, nr, "NIP z poprawną sumą kontrolną"))

            if WZ_RACHUNEK.search(linia):
                trafienia.append((wzgledna, nr, "numer rachunku (26 cyfr)"))

            for dopasowanie in WZ_EMAIL.finditer(linia):
                domena = dopasowanie.group(1).lower()
                if not any(domena == d or domena.endswith("." + d)
                           for d in DOMENY_PRZYKLADOWE):
                    # Grupujemy po pliku i domenie, bo korpus testowy ma
                    # kilkadziesiąt adresów i wypisanie każdej linii osobno
                    # zasypałoby trafienia, na które naprawdę trzeba spojrzeć.
                    maile_po_pliku[(wzgledna, domena)] += 1

            niska = linia.lower()
            for slowo in slowa_firmy:
                if slowo.lower() in niska:
                    trafienia.append((wzgledna, nr, "nazwa własna z config.yaml"))

    if nieczytane:
        print(f"(pominięto {nieczytane} plików nietekstowych)\n")

    if not trafienia and not maile_po_pliku:
        print("CZYSTO — nic podejrzanego w plikach idących do repozytorium.")
        print("\nTo nie zwalnia z przeczytania `git status` i `git diff --cached`")
        print("linia po linii przed pierwszym pushem.")
        return 0

    if maile_po_pliku:
        print("ADRESY E-MAIL w domenach, które nie są przykładowe:\n")
        poprzedni_plik = ""
        for (sciezka, domena), ile in sorted(maile_po_pliku.items()):
            if sciezka != poprzedni_plik:
                print(f"  {sciezka}")
                poprzedni_plik = sciezka
            print(f"      {domena}: {ile}")
        print("\n  W korpusie syntetycznym to adresy wymyślone — ale wymyślona")
        print("  część przed @ może przypadkiem trafić w czyjś prawdziwy adres")
        print("  u dużego dostawcy. Jeśli publikujesz korpus, rozważ zamianę")
        print("  domen na example.com.\n")

    if not trafienia:
        print("Poza adresami e-mail nic podejrzanego.")
        return 1

    print(f"ZNALEZIONO {len(trafienia)} rzeczy do sprawdzenia:\n")
    poprzedni = ""
    for sciezka, nr, co in trafienia:
        if sciezka != poprzedni:
            print(f"  {sciezka}")
            poprzedni = sciezka
        print(f"      linia {nr}: {co}")

    print("\nWartości nie są wypisane celowo — to wyjście samo mogłoby stać się")
    print("wyciekiem. Otwórz wskazane linie i oceń każdą osobno.")
    print("\nNie każde trafienie to wyciek: adres w domenie Twojej firmy w pliku")
    print("README bywa zamierzony, a numer z poprawną sumą kontrolną może być")
    print("numerem wygenerowanym do testów. Ale każde trzeba zobaczyć.")
    print("\nJeśli coś takiego już trafiło do publicznego repozytorium, usunięcie")
    print("pliku nie wystarcza — dane zostają w historii gita.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
