#!/usr/bin/env python3
"""Pierwszy skrypt do uruchomienia. Sprawdza, czy Ollama odpowiada
i jakie modele faktycznie masz lokalnie.

Nazwy tagów Bielika w Ollamie trzeba zweryfikować, a nie zgadywać -
wpisz do config.yaml dokładnie to, co wypisze ten skrypt.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from biuro.config import cfg  # noqa: E402
from biuro.llm import BladModelu, chat, dostepne_modele  # noqa: E402


def main() -> int:
    try:
        modele = dostepne_modele()
    except Exception as e:
        print(f"Nie mogę pobrać listy modeli: {e}")
        print("Uruchom `ollama serve` i spróbuj ponownie.")
        return 1

    print("Modele dostępne lokalnie:")
    for nazwa in modele:
        print(f"  - {nazwa}")

    k = cfg()
    print("\nModele wpisane w config.yaml:")
    problemy = False
    for rola in ("duzy", "maly"):
        nazwa = k.get(f"modele.{rola}")
        # Ollama dopuszcza nazwę bez tagu, więc porównujemy po prefiksie
        ok = any(m == nazwa or m.startswith(f"{nazwa}:") for m in modele)
        print(f"  {rola}: {nazwa}  ->  {'OK' if ok else 'NIE MA TAKIEGO MODELU'}")
        problemy = problemy or not ok

    if problemy:
        print("\nPopraw sekcję `modele` w config.yaml na nazwy z listy powyżej.")
        return 1

    print("\nTest generowania na dużym modelu...")
    try:
        odpowiedz = chat(
            "Odpowiedz jednym zdaniem: czym jest biuro podróży?",
            limit_tokenow=80,
        )
        print(f"  {odpowiedz}")
    except BladModelu as e:
        print(f"  BŁĄD: {e}")
        return 1

    print("\nWszystko działa. Następny krok: python skrypty/indeksuj.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
