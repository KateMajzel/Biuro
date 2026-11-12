#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generator sztucznych predykcji — do sprawdzenia samego harnessu, nie modelu.

Buduje plik predykcji z gold i wstrzykuje w niego błędy w zadanych proporcjach.
Służy do dwóch rzeczy:

  1. Weryfikacji, że ocen.py liczy to, co ma liczyć: przy --psuj 0 raport musi
     pokazać 100% we wszystkich metrykach, przy znanych proporcjach błędów —
     proporcjonalne spadki. Harness, którego nikt nie sprawdził, podaje liczby
     bez pokrycia dokładnie tak samo jak model.
  2. Ustalenia poziomu odniesienia: ile wynosi raport, gdy model zgaduje
     najczęstszą etykietę i wypełnia pola byle czym.

Użycie:
    python src/symuluj_predykcje.py --gold gold/gold_zgloszenia.json \
        --wyjscie out/predykcje_symulacja.jsonl --psuj 0.15 --ziarno 7
    python src/symuluj_predykcje.py --gold gold/gold_zgloszenia.json \
        --wyjscie out/predykcje_idealne.jsonl --psuj 0
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any


def pierwszy_wariant(wartosc: Any) -> Any:
    return wartosc[0] if isinstance(wartosc, list) and wartosc else wartosc


def main() -> int:
    p = argparse.ArgumentParser(description="Sztuczne predykcje do testu harnessu.")
    p.add_argument("--gold", required=True)
    p.add_argument("--wyjscie", required=True)
    p.add_argument(
        "--psuj",
        type=float,
        default=0.15,
        help="udział wstrzykiwanych błędów, 0 = predykcje idealne",
    )
    p.add_argument("--ziarno", type=int, default=7)
    args = p.parse_args()

    rng = random.Random(args.ziarno)
    gold = json.loads(Path(args.gold).read_text(encoding="utf-8"))
    etykiety = sorted({w["intencja"] for w in gold if w.get("intencja")})

    linie: list[str] = []
    for wpis in gold:
        pola: dict[str, Any] = {}

        # pola wymagane: część gubimy, część przekręcamy
        for sciezka, oczekiwane in (wpis.get("pola") or {}).items():
            los = rng.random()
            if los < args.psuj * 0.6:
                continue  # pole nie wyciągnięte
            if los < args.psuj:
                pola[sciezka] = "WARTOSC_PRZEKRECONA"
                continue
            pola[sciezka] = pierwszy_wariant(oczekiwane)

        # pola, które mają zostać puste: czasem wypełniamy cudzą wartością
        wartosci_z_maila = [v for v in pola.values() if isinstance(v, (str, int, float))]
        for sciezka in wpis.get("pola_puste") or []:
            if rng.random() < args.psuj and wartosci_z_maila:
                pola[sciezka] = rng.choice(wartosci_z_maila)

        # przeciek między polami: wstawiamy zakazany fragment
        for sciezka, zakazane in (wpis.get("pola_nie_zawieraja") or {}).items():
            if rng.random() < args.psuj and zakazane:
                obecne = pola.get(sciezka) or ""
                pola[sciezka] = f"{obecne}, {zakazane[0]}".strip(", ")

        intencja = wpis.get("intencja")
        if rng.random() < args.psuj and etykiety:
            intencja = rng.choice([e for e in etykiety if e != intencja] or etykiety)

        flaga = bool(wpis.get("do_czlowieka"))
        if flaga and rng.random() < args.psuj * 1.5:
            flaga = False  # najdroższy błąd, celowo częstszy niż inne

        pytania = wpis.get("pytania_liczba", 0)
        if rng.random() < args.psuj and pytania > 0:
            pytania = max(0, pytania - rng.randint(1, 2))

        dodatkowe = list(wpis.get("intencje_dodatkowe") or [])
        if dodatkowe and rng.random() < args.psuj * 2:
            dodatkowe = dodatkowe[:-1]

        rekord = {
            "id": wpis["id"],
            "intencja": intencja,
            "intencje_dodatkowe": dodatkowe,
            "do_czlowieka": flaga,
            "pytania_liczba": pytania,
            "pola": pola,
        }
        linie.append(json.dumps(rekord, ensure_ascii=False))

    wyjscie = Path(args.wyjscie)
    wyjscie.parent.mkdir(parents=True, exist_ok=True)
    wyjscie.write_text("\n".join(linie) + "\n", encoding="utf-8")
    print(f"Zapisano {len(linie)} predykcji do {wyjscie} (psuj={args.psuj}, ziarno={args.ziarno})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
