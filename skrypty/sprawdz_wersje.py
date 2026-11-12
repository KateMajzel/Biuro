#!/usr/bin/env python3
"""Które pliki kodu różnią się od spisu WERSJE.txt.

    python skrypty/sprawdz_wersje.py           # pokaż różnice
    python skrypty/sprawdz_wersje.py --zapisz  # zapisz obecny stan jako wzorzec

Po co to istnieje. Aktualizacja projektu polega na przegraniu kilku plików
ręcznie. Pominięcie jednego nie daje żadnego sygnału od razu: program
uruchamia się normalnie, a rozjazd wychodzi dopiero przy kliknięciu, jako
`cannot import name …` albo jako komunikat ze starej wersji skryptu. Wtedy
wygląda to na błąd programu, a nie na braki w kopiowaniu, i szuka się nie
tam, gdzie trzeba.

Spis obejmuje wyłącznie kod: `biuro/`, `skrypty/`, `testy/`. Nie ma w nim
`config.yaml`, `wyjazdy.yaml` ani niczego z `dane/` — te pliki mają być
inne u każdej firmy i porównywanie ich nie miałoby sensu.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
SPIS = KORZEN / "WERSJE.txt"
KATALOGI = ("biuro", "skrypty", "testy")
POMIJANE = {"__pycache__", ".pytest_cache"}


def pliki_kodu() -> list[Path]:
    znalezione: list[Path] = []
    for katalog in KATALOGI:
        podstawa = KORZEN / katalog
        if not podstawa.exists():
            continue
        for plik in podstawa.rglob("*.py"):
            if any(czesc in POMIJANE for czesc in plik.parts):
                continue
            znalezione.append(plik)
    return sorted(znalezione)


def odcisk(plik: Path) -> str:
    """Skrót treści, odporny na różnicę końców wiersza.

    Windows zapisuje CRLF, a plik pobrany z przeglądarki bywa LF. Gdyby
    liczyć skrót z surowych bajtów, każdy plik wyglądałby na zmieniony po
    jednym otwarciu w notatniku.
    """
    tekst = plik.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(tekst.encode("utf-8")).hexdigest()[:16]


def wczytaj_spis() -> dict[str, str]:
    if not SPIS.exists():
        return {}
    wpisy: dict[str, str] = {}
    for linia in SPIS.read_text(encoding="utf-8").splitlines():
        linia = linia.strip()
        if not linia or linia.startswith("#"):
            continue
        skrot, _, sciezka = linia.partition("  ")
        if sciezka:
            wpisy[sciezka.strip()] = skrot.strip()
    return wpisy


def zapisz_spis() -> int:
    linie = ["# Skróty plików kodu. Nie poprawiaj ręcznie.",
             "# Sprawdzenie: python skrypty/sprawdz_wersje.py", ""]
    for plik in pliki_kodu():
        wzgledna = plik.relative_to(KORZEN).as_posix()
        linie.append(f"{odcisk(plik)}  {wzgledna}")
    SPIS.write_text("\n".join(linie) + "\n", encoding="utf-8")
    print(f"Zapisano {len(linie) - 3} pozycji do {SPIS.name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zapisz", action="store_true",
                        help="zapisz obecny stan jako wzorzec")
    args = parser.parse_args()

    if args.zapisz:
        return zapisz_spis()

    wzorzec = wczytaj_spis()
    if not wzorzec:
        print(f"Brak {SPIS.name} — nie mam z czym porównać.")
        return 1

    obecne = {p.relative_to(KORZEN).as_posix(): odcisk(p) for p in pliki_kodu()}

    inne = sorted(s for s, h in wzorzec.items()
                  if s in obecne and obecne[s] != h)
    brakujace = sorted(s for s in wzorzec if s not in obecne)
    nadmiarowe = sorted(s for s in obecne if s not in wzorzec)

    if not inne and not brakujace:
        print(f"Komplet: {len(obecne)} plików kodu zgodnych ze spisem.")
        if nadmiarowe:
            print("\nPliki spoza spisu (Twoje własne — to w porządku):")
            for s in nadmiarowe:
                print(f"  {s}")
        return 0

    if brakujace:
        print("BRAKUJE — te pliki trzeba dograć:")
        for s in brakujace:
            print(f"  {s}")
    if inne:
        print("\nSTARA WERSJA — te pliki trzeba nadpisać:")
        for s in inne:
            print(f"  {s}")
    if nadmiarowe:
        print("\nspoza spisu (Twoje własne — to w porządku):")
        for s in nadmiarowe:
            print(f"  {s}")

    print(f"\nRazem do poprawienia: {len(inne) + len(brakujace)} "
          f"z {len(wzorzec)} plików.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
