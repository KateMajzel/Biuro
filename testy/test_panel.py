#!/usr/bin/env python3
"""Testy panelu okienkowego — bez otwierania okna.

    python testy/test_panel.py

Panel nie liczy niczego sam: każdy przycisk uruchamia skrypt z `skrypty/`.
Najłatwiej zepsuć w nim dwie rzeczy i obie ujawniają się dopiero po
kliknięciu, czyli w najgorszym możliwym momencie — przy kamerze albo przy
kliencie. Pierwsza to literówka w nazwie pliku. Druga to nieistniejący
przełącznik: `--okrojony` zamiast `--okrojona` wywala skrypt dopiero wtedy,
gdy ktoś poprosi o listę uczestników dla przewoźnika.

Te testy czytają kod panelu bez jego uruchamiania — wyciągają z niego
wszystkie wywołania `self.uruchom(...)` i sprawdzają każde wobec
rzeczywistych skryptów i ich zadeklarowanych argumentów. Dzięki temu
działają też tam, gdzie nie ma tkintera.
"""

import argparse
import ast
import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KORZEN))
sys.path.insert(0, str(Path(__file__).resolve().parent))

PANEL = KORZEN / "skrypty" / "panel.py"


def wywolania_uruchom() -> list[list[str]]:
    """Listy argumentów ze wszystkich wywołań self.uruchom() w panelu.

    Z listy bierzemy tylko elementy, które są stałymi napisami — numer
    zgłoszenia czy klucz wyjazdu pochodzą z okienka i w kodzie są zmiennymi.
    """
    drzewo = ast.parse(PANEL.read_text(encoding="utf-8"))
    znalezione: list[list[str]] = []
    for wezel in ast.walk(drzewo):
        if not isinstance(wezel, ast.Call):
            continue
        cel = wezel.func
        if not (isinstance(cel, ast.Attribute) and cel.attr == "uruchom"):
            continue
        if not wezel.args:
            continue
        pierwszy = wezel.args[0]
        if isinstance(pierwszy, ast.List):
            elementy = [
                e.value for e in pierwszy.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            ]
            if elementy:
                znalezione.append(elementy)
        elif isinstance(pierwszy, ast.Name):
            # lista budowana warunkowo (wariant okrojony arkusza) —
            # szukamy jej w przypisaniach w tej samej funkcji
            for inny in ast.walk(drzewo):
                if isinstance(inny, ast.Assign) and isinstance(inny.value, ast.List):
                    nazwy = [t.id for t in inny.targets if isinstance(t, ast.Name)]
                    if pierwszy.id in nazwy:
                        znalezione.append([
                            e.value for e in inny.value.elts
                            if isinstance(e, ast.Constant) and isinstance(e.value, str)
                        ])
    return znalezione


def doklejane_przelaczniki() -> list[str]:
    """Przełączniki dokładane przez .append(), np. '--okrojona'."""
    drzewo = ast.parse(PANEL.read_text(encoding="utf-8"))
    return [
        w.args[0].value
        for w in ast.walk(drzewo)
        if isinstance(w, ast.Call)
        and isinstance(w.func, ast.Attribute)
        and w.func.attr == "append"
        and w.args
        and isinstance(w.args[0], ast.Constant)
        and isinstance(w.args[0].value, str)
        and w.args[0].value.startswith("--")
    ]


def metody_przyciskow() -> tuple[list[str], set[str]]:
    """(metody podpięte pod przyciski, metody zdefiniowane w panelu).

    Literówka w nazwie metody przy tworzeniu przycisku nie jest błędem
    składni — panel wywala się dopiero przy otwieraniu okna, z AttributeError.
    """
    drzewo = ast.parse(PANEL.read_text(encoding="utf-8"))
    podpiete: list[str] = []
    zdefiniowane: set[str] = set()
    for wezel in ast.walk(drzewo):
        if isinstance(wezel, ast.ClassDef):
            zdefiniowane.update(
                w.name for w in wezel.body
                if isinstance(w, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
        if (isinstance(wezel, ast.Call)
                and isinstance(wezel.func, ast.Attribute)
                and wezel.func.attr in ("_przycisk", "Button")):
            for arg in list(wezel.args) + [k.value for k in wezel.keywords]:
                if (isinstance(arg, ast.Attribute)
                        and isinstance(arg.value, ast.Name)
                        and arg.value.id == "self"):
                    podpiete.append(arg.attr)
    return podpiete, zdefiniowane


def _komplet_z_kodu() -> list[tuple[str, str, str]]:
    """Lista KOMPLET odczytana z kodu panelu, bez jego uruchamiania.

    Panel importuje tkintera, którego nie ma na każdej maszynie — a ten test
    ma działać wszędzie, bo pilnuje spójności plików, nie okna.
    """
    drzewo = ast.parse(PANEL.read_text(encoding="utf-8"))
    for wezel in ast.walk(drzewo):
        cele = (wezel.targets if isinstance(wezel, ast.Assign)
                else [wezel.target] if isinstance(wezel, ast.AnnAssign) else [])
        if any(isinstance(c, ast.Name) and c.id == "KOMPLET" for c in cele):
            return [
                tuple(e.value for e in krotka.elts)  # type: ignore[misc]
                for krotka in wezel.value.elts      # type: ignore[union-attr]
            ]
    return []


def _braki_z_kodu() -> list[str]:
    braki = []
    for sciezka, znak, po_co in _komplet_z_kodu():
        plik = KORZEN / sciezka
        if not plik.exists():
            braki.append(f"{sciezka} — brak pliku ({po_co})")
        elif znak not in plik.read_text(encoding="utf-8"):
            braki.append(f"{sciezka} — stara wersja ({po_co})")
    return braki


def przelaczniki_skryptu(sciezka: Path) -> set[str]:
    """Przełączniki zadeklarowane w add_argument() danego skryptu."""
    drzewo = ast.parse(sciezka.read_text(encoding="utf-8"))
    nazwy: set[str] = set()
    for wezel in ast.walk(drzewo):
        if (isinstance(wezel, ast.Call)
                and isinstance(wezel.func, ast.Attribute)
                and wezel.func.attr == "add_argument"):
            for arg in wezel.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    nazwy.add(arg.value)
    return nazwy


def main() -> int:
    bledy = 0

    def sprawdz(nazwa: str, warunek: bool, szczegol: str = "") -> None:
        nonlocal bledy
        if warunek:
            print(f"OK    {nazwa}")
        else:
            bledy += 1
            print(f"BŁĄD  {nazwa}   {szczegol}")

    sprawdz("panel istnieje", PANEL.exists(), str(PANEL))
    if not PANEL.exists():
        return 1

    try:
        ast.parse(PANEL.read_text(encoding="utf-8"))
        sprawdz("panel ma poprawną składnię", True)
    except SyntaxError as e:
        sprawdz("panel ma poprawną składnię", False, f"linia {e.lineno}: {e.msg}")
        return 1

    wywolania = wywolania_uruchom()
    sprawdz("panel ma przyciski uruchamiające skrypty",
            len(wywolania) >= 5, f"znaleziono {len(wywolania)}")

    wszystkie_przelaczniki: set[tuple[str, str]] = set()
    for argumenty in wywolania:
        skrypt = KORZEN / argumenty[0]
        sprawdz(f"skrypt istnieje: {argumenty[0]}", skrypt.exists())
        if not skrypt.exists():
            continue
        for a in argumenty[1:]:
            if a.startswith("--"):
                wszystkie_przelaczniki.add((argumenty[0], a))

    # przełączniki dokładane warunkowo trafiają do skryptu listy uczestników
    for przelacznik in doklejane_przelaczniki():
        wszystkie_przelaczniki.add(("skrypty/zrob_liste.py", przelacznik))

    for sciezka_wzgl, przelacznik in sorted(wszystkie_przelaczniki):
        skrypt = KORZEN / sciezka_wzgl
        if not skrypt.exists():
            continue
        zadeklarowane = przelaczniki_skryptu(skrypt)
        sprawdz(f"{sciezka_wzgl} zna {przelacznik}",
                przelacznik in zadeklarowane,
                f"skrypt deklaruje: {sorted(z for z in zadeklarowane if z.startswith('--'))}")

    # Panel musi wskazywać interpreter ze środowiska .venv, nie systemowy.
    # Systemowy nie ma zależności projektu, a różnica wyszłaby dopiero po
    # kliknięciu, jako błąd importu w okienku.
    podpiete, zdefiniowane = metody_przyciskow()
    sprawdz("przyciski mają podpięte metody", len(podpiete) >= 6,
            f"znaleziono {len(podpiete)}")
    for nazwa in sorted(set(podpiete)):
        sprawdz(f"panel ma metodę {nazwa}", nazwa in zdefiniowane)

    tresc = PANEL.read_text(encoding="utf-8")
    sprawdz("panel szuka interpretera w .venv", '".venv"' in tresc)
    sprawdz("panel uruchamia skrypty w katalogu projektu", "cwd=KORZEN" in tresc)
    sprawdz("panel nie wysyła poczty samodzielnie",
            "smtp" not in tresc.lower() and "sendmail" not in tresc.lower())
    # Bez tego polskie litery w wyjściu skryptów ginęły: Python na Windowsie
    # pisze do rury w cp1250, a panel czyta UTF-8.
    sprawdz("panel wymusza UTF-8 w uruchamianych skryptach",
            'PYTHONIOENCODING' in tresc and 'env=srodowisko' in tresc)
    sprawdz("panel nie wypisuje ścieżek przy starcie",
            'f"Katalog:' not in tresc and 'f"Python:' not in tresc)
    sprawdz("panel nie pyta o potwierdzenie przed przebiegiem poczty",
            "askokcancel" not in tresc)

    # Sprawdzenie kompletu plików ma sens tylko wtedy, gdy wymienione w nim
    # pliki naprawdę istnieją i naprawdę zawierają swoje znaki rozpoznawcze.
    # Inaczej panel krzyczałby o braki przy kompletnej instalacji.
    # Listę czytamy z kodu, a nie przez import panelu: panel bez tkintera
    # kończy proces, a ten test ma działać także tam, gdzie okien nie ma.
    komplet = _komplet_z_kodu()
    braki = _braki_z_kodu()

    sprawdz("lista kompletu nie jest pusta", len(komplet) >= 5,
            f"pozycji: {len(komplet)}")
    sprawdz("komplet plików jest spójny", not braki, "; ".join(braki))

    print()
    if bledy:
        print(f"BŁĘDY: {bledy}")
        return 1
    print("Wszystkie przypadki przeszły.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
