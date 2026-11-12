"""Wczytywanie konfiguracji. Jedno miejsce prawdy o ścieżkach i ustawieniach."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

KORZEN = Path(__file__).resolve().parent.parent

load_dotenv(KORZEN / ".env")


class Konfiguracja:
    def __init__(self, dane: dict[str, Any]):
        self._dane = dane

    def __getitem__(self, klucz: str) -> Any:
        return self._dane[klucz]

    def get(self, sciezka: str, domyslnie: Any = None) -> Any:
        """Dostęp kropkowy: cfg.get('modele.duzy')."""
        biezacy: Any = self._dane
        for czesc in sciezka.split("."):
            if not isinstance(biezacy, dict) or czesc not in biezacy:
                return domyslnie
            biezacy = biezacy[czesc]
        return biezacy

    def sciezka(self, nazwa: str) -> Path:
        """Ścieżka z sekcji sciezki, zawsze absolutna, katalog tworzony w razie potrzeby.

        Zmienna środowiskowa BIURO_BAZA nadpisuje ścieżkę bazy danych. Istnieje
        po to, żeby testy nie pisały do produkcyjnej bazy — przed tą zmianą
        `testy/test_dokumenty.py` robił DELETE na tabelach zgloszenia, umowy,
        rezerwacje i dane_wrazliwe w pliku wskazanym przez config.yaml.
        Uruchomienie testów po wejściu prawdziwych zgłoszeń usunęłoby je.
        """
        if nazwa == "baza":
            nadpisanie = os.getenv("BIURO_BAZA")
            if nadpisanie:
                p = Path(nadpisanie)
                p.parent.mkdir(parents=True, exist_ok=True)
                return p

        wzgledna = self.get(f"sciezki.{nazwa}")
        if wzgledna is None:
            raise KeyError(f"Brak sciezki.{nazwa} w config.yaml")
        p = KORZEN / wzgledna
        if p.suffix:
            p.parent.mkdir(parents=True, exist_ok=True)
        else:
            p.mkdir(parents=True, exist_ok=True)
        return p

    # --- sekrety: tylko ze zmiennych środowiskowych, nigdy z config.yaml ---

    @property
    def imap_user(self) -> str:
        return os.getenv("IMAP_USER") or self.get("poczta.uzytkownik", "")

    @property
    def imap_password(self) -> str:
        haslo = os.getenv("IMAP_PASSWORD")
        if not haslo:
            raise RuntimeError(
                "Brak IMAP_PASSWORD. Ustaw hasło aplikacji w pliku .env "
                "(nie hasło do konta Google)."
            )
        return haslo

    def opis_firmy(self) -> str:
        """Blok tekstowy o firmie wstawiany do promptów."""
        f = self._dane.get("firma", {})
        linie = [f"Nazwa: {f.get('nazwa', '')}", f"Branża: {f.get('branza', '')}"]
        if f.get("www"):
            linie.append(f"Strona: {f['www']}")
        if f.get("email"):
            linie.append(f"E-mail: {f['email']}")
        if f.get("telefon"):
            linie.append(f"Telefon: {f['telefon']}")
        return "\n".join(linie)


@lru_cache(maxsize=1)
def cfg() -> Konfiguracja:
    plik = KORZEN / "config.yaml"
    if not plik.exists():
        raise RuntimeError(
            "Brak config.yaml. Skopiuj config.example.yaml do config.yaml i wypełnij."
        )
    # config.yaml jest edytowany ręcznie, więc literówka w składni YAML jest
    # normalnym zdarzeniem, nie awarią. Bez tego przechwycenia użytkownik
    # dostaje dwudziestoliniowy stos wywołań z wnętrza parsera, w którym
    # numer wadliwej linii jest na końcu i łatwo go przeoczyć.
    tekst = plik.read_text(encoding="utf-8")
    try:
        dane = yaml.safe_load(tekst)
    except yaml.YAMLError as e:
        linia = None
        znacznik = getattr(e, "problem_mark", None)
        if znacznik is not None:
            linia = znacznik.line + 1
        komunikat = [f"Błąd składni w {plik.name}"]
        if linia:
            komunikat.append(f"  linia {linia}, kolumna {znacznik.column + 1}")
            wiersze = tekst.splitlines()
            for nr in range(max(0, linia - 3), min(len(wiersze), linia + 2)):
                wskaznik = ">>" if nr + 1 == linia else "  "
                komunikat.append(f"  {wskaznik} {nr + 1:3d} | {wiersze[nr]}")
        if getattr(e, "problem", None):
            komunikat.append(f"  {e.problem}")
        komunikat.append(
            "\nNajczęstsza przyczyna: wcięcie. Wartość wielolinijkowa po znaku |"
            "\nmusi być wcięta GŁĘBIEJ niż jej klucz:"
            "\n    podpis: |"
            "\n      Pozdrawiam"
            "\n      Imię"
        )
        raise RuntimeError("\n".join(komunikat)) from None
    if not isinstance(dane, dict):
        raise RuntimeError(
            f"{plik.name} nie zawiera mapy klucz-wartość. "
            "Skopiuj config.example.yaml i wypełnij go od nowa."
        )
    return Konfiguracja(dane)


def prompt(nazwa: str) -> str:
    """Wczytuje prompt z katalogu prompty/. Trzymamy je w plikach,
    żeby dało się je kalibrować bez dotykania kodu.

    `{WARUNKI}` w treści promptu jest podmieniane na sekcję listy zamkniętej
    warunków flagi, wyciętą z `klasyfikacja.md`. Lista jest w jednym pliku,
    a czytają ją trzy miejsca: prompt klasyfikacji, prompt flagi i narzędzie
    do wypełniania ground truth. Skopiowana rozjechałaby się przy pierwszej
    poprawce i wtedy klasyfikator oceniałby inne warunki niż te, według
    których powstał zbiór odniesienia.
    """
    plik = cfg().sciezka("prompty") / f"{nazwa}.md"
    if not plik.exists():
        raise FileNotFoundError(f"Brak promptu: {plik}")
    tekst = plik.read_text(encoding="utf-8")
    if "{WARUNKI}" in tekst:
        tekst = tekst.replace("{WARUNKI}", sekcja_warunkow())
    return tekst


def sekcja_warunkow() -> str:
    """Sekcja „Flaga do człowieka" z promptu klasyfikacji, bez nagłówka pliku."""
    plik = cfg().sciezka("prompty") / "klasyfikacja.md"
    tekst = plik.read_text(encoding="utf-8")
    poczatek = tekst.find("## Flaga do człowieka")
    if poczatek == -1:
        raise RuntimeError(
            f"W {plik.name} nie ma sekcji '## Flaga do człowieka'. "
            "To jedyne źródło listy zamkniętej warunków — nie zmieniaj nagłówka."
        )
    koniec = tekst.find("\n## ", poczatek + 1)
    return tekst[poczatek:koniec if koniec != -1 else len(tekst)].strip()
