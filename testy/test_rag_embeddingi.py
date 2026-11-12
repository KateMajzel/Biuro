#!/usr/bin/env python3
"""Testy liczenia embeddingów. Bez sieci — żądanie do Ollamy jest podstawiane.

    python testy/test_rag_embeddingi.py

Skąd ten plik. Embeddingi liczył `sentence_transformers`, a ten ciągnie
`transformers`, a `transformers` paczkę `regex`, której biblioteka natywna
została na maszynie docelowej zablokowana przez Smart App Control. Import nie
przechodził wcale, więc cała baza wiedzy — a z nią drafty — była nieosiągalna.
Wektory liczy teraz Ollama, czyli usługa, która i tak musi działać.

Testy pilnują trzech rzeczy, z których każda cicho psuje wyszukiwanie:
normalizacji (bez niej iloczyn skalarny nie jest podobieństwem cosinusowym),
zgody na starsze API Ollamy, i odmowy przeszukania indeksu zbudowanego innym
modelem — ten ostatni przypadek nie daje błędu sam z siebie, tylko zwraca
losowe fragmenty oferty.
"""

import json
import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KORZEN))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from baza_testowa import wymagaj_bazy_testowej  # noqa: E402

wymagaj_bazy_testowej()

import numpy as np  # noqa: E402

from biuro import llm, rag  # noqa: E402


class AtrapaOllamy:
    """Podstawia _zadanie. `nowe_api=False` udaje Ollamę bez /api/embed."""

    def __init__(self, wymiar: int = 4, nowe_api: bool = True) -> None:
        self.wymiar = wymiar
        self.nowe_api = nowe_api
        self.sciezki: list[str] = []
        self.partie: list[int] = []

    def __call__(self, sciezka: str, ladunek: dict):
        self.sciezki.append(sciezka)
        if sciezka == "/api/embed":
            if not self.nowe_api:
                raise llm.BladModelu("404: unknown path /api/embed")
            teksty = ladunek["input"]
            self.partie.append(len(teksty))
            # wektory o różnych długościach — normalizacja musi je wyrównać
            return {"embeddings": [[float(i + 1)] * self.wymiar
                                   for i in range(len(teksty))]}
        if sciezka == "/api/embeddings":
            self.partie.append(1)
            return {"embedding": [2.0] * self.wymiar}
        raise AssertionError(f"nieoczekiwana ścieżka: {sciezka}")


def z_atrapa(atrapa, funkcja):
    stare = llm._zadanie
    llm._zadanie = atrapa
    try:
        return funkcja()
    finally:
        llm._zadanie = stare


def main() -> int:
    bledy = 0

    def sprawdz(nazwa: str, warunek: bool, szczegol: str = "") -> None:
        nonlocal bledy
        if warunek:
            print(f"OK    {nazwa}")
        else:
            bledy += 1
            print(f"BŁĄD  {nazwa}   {szczegol}")

    teksty = ["pierwszy fragment", "drugi fragment", "trzeci fragment"]

    # 1. Nowe API, jedna partia.
    atrapa = AtrapaOllamy()
    wektory = z_atrapa(atrapa, lambda: rag._osadz_ollama(teksty))
    sprawdz("kształt zgadza się z liczbą tekstów", wektory.shape == (3, 4),
            str(wektory.shape))
    sprawdz("użyte nowe /api/embed", atrapa.sciezki == ["/api/embed"],
            str(atrapa.sciezki))
    dlugosci = np.linalg.norm(wektory, axis=1)
    sprawdz("wektory znormalizowane do długości 1",
            bool(np.allclose(dlugosci, 1.0)), str(dlugosci))
    sprawdz("typ float32 — indeks zapisuje się bez konwersji",
            wektory.dtype == np.float32, str(wektory.dtype))

    # 2. Starsza Ollama bez /api/embed — fallback na jeden tekst na żądanie.
    atrapa = AtrapaOllamy(nowe_api=False)
    wektory = z_atrapa(atrapa, lambda: rag._osadz_ollama(teksty))
    sprawdz("fallback daje tyle wektorów, ile tekstów", wektory.shape == (3, 4),
            str(wektory.shape))
    sprawdz("fallback poszedł na /api/embeddings",
            atrapa.sciezki.count("/api/embeddings") == 3, str(atrapa.sciezki))

    # 3. Partie: 40 tekstów przy partia=16 to trzy żądania, nie jedno.
    #    Jedno żądanie z całym korpusem przekracza czas oczekiwania.
    atrapa = AtrapaOllamy()
    z_atrapa(atrapa, lambda: rag._osadz_ollama([f"tekst {i}" for i in range(40)]))
    sprawdz("teksty dzielone na partie", atrapa.partie == [16, 16, 8],
            str(atrapa.partie))

    # 4. Indeks zbudowany innym modelem — odmowa, nie losowe wyniki.
    katalog = KORZEN / "dane" / "indeks_testowy"
    katalog.mkdir(parents=True, exist_ok=True)
    np.save(katalog / "wektory.npy", np.zeros((2, 4), dtype=np.float32))
    (katalog / "fragmenty.json").write_text("[]", encoding="utf-8")
    (katalog / rag.PLIK_METADANYCH).write_text(
        json.dumps({"silnik": "sentence_transformers", "model": "inny-model"}),
        encoding="utf-8",
    )

    stary_cfg = rag.cfg

    class Konf:
        def get(self, klucz, domyslna=None):
            return stary_cfg().get(klucz, domyslna)

        def sciezka(self, _nazwa):
            return katalog

    rag.cfg = lambda: Konf()
    rag._cache = None
    try:
        rag._wczytaj_indeks()
        sprawdz("niezgodny indeks odrzucony", False, "nie podniesiono wyjątku")
    except RuntimeError as e:
        sprawdz("niezgodny indeks odrzucony", "Przebuduj" in str(e), str(e))
    finally:
        rag.cfg = stary_cfg
        rag._cache = None
        for plik in katalog.iterdir():
            plik.unlink()
        katalog.rmdir()

    print()
    if bledy:
        print(f"BŁĘDY: {bledy}")
        return 1
    print("Wszystkie przypadki przeszły.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
