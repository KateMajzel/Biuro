"""Klient Bielika przez Ollamę.

Najważniejsza rzecz w tym pliku: chat_json() wymusza schemat odpowiedzi,
więc model fizycznie nie może zwrócić czegoś, co się nie sparsuje.
To eliminuje główną przyczynę wysypywania się takich pipeline'ów.
"""

from __future__ import annotations

import json
import time
from typing import Any, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from .config import cfg

T = TypeVar("T", bound=BaseModel)

CZAS_OCZEKIWANIA = 300


class BladModelu(RuntimeError):
    pass


def _zadanie(sciezka: str, ladunek: dict[str, Any]) -> dict[str, Any]:
    host = cfg().get("modele.host", "http://localhost:11434").rstrip("/")
    try:
        odp = requests.post(f"{host}{sciezka}", json=ladunek, timeout=CZAS_OCZEKIWANIA)
    except requests.RequestException as e:
        raise BladModelu(
            f"Nie mogę połączyć się z Ollamą na {host}. Czy działa `ollama serve`?"
        ) from e
    if odp.status_code != 200:
        raise BladModelu(f"Ollama zwróciła {odp.status_code}: {odp.text[:300]}")
    return odp.json()


def dostepne_modele() -> list[str]:
    host = cfg().get("modele.host", "http://localhost:11434").rstrip("/")
    odp = requests.get(f"{host}/api/tags", timeout=30)
    odp.raise_for_status()
    return sorted(m["name"] for m in odp.json().get("models", []))


def chat(
    uzytkownik: str,
    system: str | None = None,
    *,
    maly: bool = False,
    temperatura: float | None = None,
    limit_tokenow: int | None = None,
) -> str:
    """Zwykła odpowiedź tekstowa. maly=True kieruje zadanie na Bielika 4.5B."""
    k = cfg()
    model = k.get("modele.maly") if maly else k.get("modele.duzy")
    if temperatura is None:
        temperatura = k.get("modele.temperatura_zadania" if maly else "modele.temperatura_pisanie", 0.3)

    wiadomosci = []
    if system:
        wiadomosci.append({"role": "system", "content": system})
    wiadomosci.append({"role": "user", "content": uzytkownik})

    wynik = _zadanie(
        "/api/chat",
        {
            "model": model,
            "messages": wiadomosci,
            "stream": False,
            "options": {
                "temperature": temperatura,
                "num_predict": limit_tokenow or k.get("modele.limit_tokenow", 1200),
                "num_ctx": k.get("modele.kontekst", 8192),
            },
        },
    )
    return wynik["message"]["content"].strip()


def _urwane(wynik: dict, blad: Exception) -> bool:
    """Czy odpowiedź urwała się na limicie tokenów, zamiast być po prostu zła.

    Ollama mówi to wprost w `done_reason: "length"`. Starsze wersje tego pola
    nie mają, więc zapasowo patrzymy na treść błędu parsera: niedomknięty
    napis albo nawias to zawsze urwanie, nigdy pomyłka w schemacie.
    """
    if wynik.get("done_reason") == "length":
        return True
    tekst = str(blad)
    return ("EOF while parsing" in tekst
            or "Unterminated string" in tekst
            or "Expecting ',' delimiter" in tekst)


def chat_json(
    uzytkownik: str,
    schemat: type[T],
    system: str | None = None,
    *,
    maly: bool = True,
    proby: int = 3,
    limit_tokenow: int | None = None,
) -> T:
    """Odpowiedź wymuszona schematem pydantic. Domyślnie na małym modelu,
    bo ekstrakcja i klasyfikacja nie potrzebują 11B.

    `limit_tokenow` nadpisuje `modele.limit_tokenow` z konfiguracji. Potrzebne
    tam, gdzie odpowiedź jest z natury długa — projekt maila do klienta ma
    kilka akapitów, a wyciągnięcie PESEL-u mieści się w dwóch linijkach.
    """
    k = cfg()
    model = k.get("modele.maly") if maly else k.get("modele.duzy")

    wiadomosci = []
    if system:
        wiadomosci.append({"role": "system", "content": system})
    wiadomosci.append({"role": "user", "content": uzytkownik})
    poczatkowe = list(wiadomosci)

    budzet = int(limit_tokenow or k.get("modele.limit_tokenow", 1200))
    sufit = int(k.get("modele.limit_tokenow_max", 4096))

    ostatni_blad: Exception | None = None
    for nr in range(proby):
        wynik = _zadanie(
            "/api/chat",
            {
                "model": model,
                "messages": wiadomosci,
                "stream": False,
                # Ollama przyjmuje schemat JSON i wymusza go na dekodowaniu
                "format": schemat.model_json_schema(),
                "options": {
                    "temperature": 0.0,
                    "num_predict": budzet,
                    "num_ctx": k.get("modele.kontekst", 8192),
                },
            },
        )
        tresc = wynik["message"]["content"]
        try:
            return schemat.model_validate_json(tresc)
        except (ValidationError, json.JSONDecodeError) as e:
            ostatni_blad = e
            if _urwane(wynik, e) and budzet < sufit:
                # Odpowiedź była poprawna, tylko się nie zmieściła. Prośba
                # o poprawkę nic tu nie da — przy tym samym limicie urwie się
                # w tym samym miejscu, co widać po „po 2 próbach" z dokładnie
                # tym samym błędem. Zaczynamy od nowa z większym budżetem,
                # bez doklejania urwanej odpowiedzi, bo ta zjadłaby kontekst.
                budzet = min(budzet * 2, sufit)
                wiadomosci = list(poczatkowe)
                continue
            # Dokładamy komunikat o błędzie i prosimy o poprawkę
            wiadomosci.append({"role": "assistant", "content": tresc})
            wiadomosci.append(
                {
                    "role": "user",
                    "content": "Odpowiedź nie spełnia schematu. Popraw i zwróć wyłącznie poprawny JSON.",
                }
            )
            time.sleep(0.5 * (nr + 1))

    powod = "odpowiedź urywała się na limicie tokenów" if ostatni_blad and \
        _urwane({}, ostatni_blad) else "odpowiedź nie spełniała schematu"
    raise BladModelu(
        f"Model nie zwrócił poprawnego JSON po {proby} próbach ({powod}): "
        f"{ostatni_blad}"
    )


def zmierz(funkcja, *args, **kwargs) -> tuple[Any, float]:
    """Pomocnik do metryk: zwraca (wynik, czas_w_sekundach)."""
    start = time.perf_counter()
    wynik = funkcja(*args, **kwargs)
    return wynik, time.perf_counter() - start
