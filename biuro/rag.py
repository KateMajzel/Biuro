"""Baza wiedzy o firmie: indeksowanie i wyszukiwanie.

Bez zewnętrznej bazy wektorowej. Przy kilkuset fragmentach numpy
liczy podobieństwo w milisekundach, a mamy o jedną zależność mniej,
która może się posypać w sobotę.

Embeddingów nie robi Bielik - do tego jest osobny model wielojęzyczny.

Domyślnie liczy je Ollama, czyli ta sama usługa, która obsługuje Bielika.
Powód jest praktyczny: `sentence_transformers` ciągnie `torch` i `transformers`,
a `transformers` zależy od paczki `regex`, której biblioteka natywna została
na maszynie docelowej zablokowana przez Smart App Control ("Zasady kontroli
aplikacji zablokowały ten plik"). Obejścia dla `.pyd` w środku paczki nie ma,
a instalacja kilku gigabajtów zależności po to, żeby policzyć wektory, i tak
była najcięższym elementem całego wdrożenia. Ollama musi działać niezależnie,
bo bez niej nie ma modelu językowego.

Silnik `sentence_transformers` zostaje jako opcja w konfiguracji — jeśli ktoś
chce polski model mmlw i ma gdzie go uruchomić, wystarczy zmienić jedno pole.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np

from .config import cfg

_model = None

# Nazwa silnika i modelu trafia do indeksu. Bez tego wyszukiwanie w indeksie
# zbudowanym innym modelem nie wywala się, tylko po cichu zwraca bzdury —
# wektory mają inny rozkład, a iloczyn skalarny policzy się tak samo chętnie.
PLIK_METADANYCH = "indeks.json"


def _silnik() -> str:
    return cfg().get("embeddingi.silnik", "ollama")


def _nazwa_modelu() -> str:
    if _silnik() == "ollama":
        return cfg().get("embeddingi.model_ollama", "bge-m3")
    return cfg().get("embeddingi.model", "sdadas/mmlw-retrieval-roberta-large")


def model_embeddingow():
    """Ładowany leniwie, bo ciągnie torch i kilkaset MB wag."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(cfg().get("embeddingi.model"))
    return _model


def _osadz_ollama(teksty: list[str]) -> np.ndarray:
    """Wektory z Ollamy. Obsługuje nowe /api/embed i starsze /api/embeddings."""
    from .llm import BladModelu, _zadanie

    model = _nazwa_modelu()
    partia = int(cfg().get("embeddingi.partia", 16))
    wektory: list[list[float]] = []

    for poczatek in range(0, len(teksty), partia):
        kawalek = teksty[poczatek:poczatek + partia]
        try:
            odp = _zadanie("/api/embed", {"model": model, "input": kawalek})
            osadzenia = odp.get("embeddings")
        except BladModelu:
            osadzenia = None
        if not osadzenia:
            # starsze Ollamy: jeden tekst na żądanie, inna nazwa pola
            osadzenia = [
                _zadanie("/api/embeddings", {"model": model, "prompt": t})["embedding"]
                for t in kawalek
            ]
        wektory.extend(osadzenia)

    macierz = np.asarray(wektory, dtype=np.float32)
    if macierz.ndim != 2 or macierz.shape[0] != len(teksty):
        raise RuntimeError(
            f"Ollama zwróciła {macierz.shape} wektorów dla {len(teksty)} tekstów. "
            f"Czy model '{model}' jest pobrany? `ollama pull {model}`"
        )
    # normalizacja, żeby iloczyn skalarny był podobieństwem cosinusowym
    normy = np.linalg.norm(macierz, axis=1, keepdims=True)
    normy[normy == 0] = 1.0
    return macierz / normy


def osadz(teksty: list[str], gadatliwie: bool = False) -> np.ndarray:
    if _silnik() == "ollama":
        if gadatliwie:
            print(f"Embeddingi przez Ollamę, model {_nazwa_modelu()}")
        return _osadz_ollama(teksty)
    wektory = model_embeddingow().encode(
        teksty, normalize_embeddings=True, show_progress_bar=gadatliwie, batch_size=16
    )
    return np.asarray(wektory, dtype=np.float32)


FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Pola frontmattera, które doklejamy do KAŻDEGO fragmentu z danego pliku.
# Powód jest konkretny: `status_sprzedazy: brak_w_magazynie` dla Lake District
# siedzi w nagłówku pliku, a wyszukiwanie zwraca fragment z programem albo
# z ceną. Bez doklejenia model widziałby opis wyjazdu i nie wiedziałby, że
# sprzedaż jest zamknięta - czyli mógłby potwierdzić wolne miejsca.
POLA_METRYCZKI = ("wyjazd", "termin_od", "termin_do", "cena", "waluta", "status_sprzedazy")


def _frontmatter(tekst: str) -> tuple[dict[str, str], str]:
    """Zwraca (pola frontmattera, treść bez frontmattera)."""
    dopasowanie = FRONTMATTER.match(tekst)
    if not dopasowanie:
        return {}, tekst
    pola: dict[str, str] = {}
    for linia in dopasowanie.group(1).splitlines():
        if ":" not in linia or linia.lstrip().startswith("#"):
            continue
        klucz, wartosc = linia.split(":", 1)
        pola[klucz.strip()] = wartosc.strip().strip("\"'")
    return pola, tekst[dopasowanie.end():]


def _metryczka(pola: dict[str, str]) -> str:
    if not pola:
        return ""
    czesci = []
    if pola.get("wyjazd"):
        czesci.append(pola["wyjazd"])
    if pola.get("termin_od"):
        termin = pola["termin_od"]
        if pola.get("termin_do"):
            termin += f" – {pola['termin_do']}"
        czesci.append(termin)
    if pola.get("cena"):
        czesci.append(f"{pola['cena']} {pola.get('waluta', '')}".strip())

    status = pola.get("status_sprzedazy", "")
    if status and status != "dostepny":
        czesci.append(f"SPRZEDAŻ ZAMKNIĘTA ({status}) — nie potwierdzaj wolnych miejsc")
    elif status:
        czesci.append(f"status: {status}")

    return "[" + " | ".join(czesci) + "]" if czesci else ""


@dataclass
class Fragment:
    tekst: str
    zrodlo: str      # nazwa pliku
    naglowek: str    # najbliższy nagłówek markdown, do cytowania


def _podziel(tekst: str, zrodlo: str) -> list[Fragment]:
    """Dzielimy po nagłówkach markdown, a długie sekcje dodatkowo po znakach.
    Nagłówek zostaje przy fragmencie, żeby dało się wskazać źródło odpowiedzi.
    Metryczka z frontmattera trafia do każdego fragmentu z danego pliku."""
    rozmiar = cfg().get("embeddingi.rozmiar_chunka", 900)
    zakladka = cfg().get("embeddingi.zakladka", 150)

    pola, tekst = _frontmatter(tekst)
    metryczka = _metryczka(pola)

    sekcje: list[tuple[str, str]] = []
    biezacy_naglowek = ""
    bufor: list[str] = []
    for linia in tekst.splitlines():
        if re.match(r"^#{1,6}\s+", linia):
            if bufor:
                sekcje.append((biezacy_naglowek, "\n".join(bufor).strip()))
                bufor = []
            biezacy_naglowek = linia.lstrip("#").strip()
        else:
            bufor.append(linia)
    if bufor:
        sekcje.append((biezacy_naglowek, "\n".join(bufor).strip()))

    def z_metryczka(kawalek: str) -> str:
        return f"{metryczka}\n{kawalek}".strip() if metryczka else kawalek

    fragmenty: list[Fragment] = []
    for naglowek, tresc in sekcje:
        if not tresc:
            continue
        if len(tresc) <= rozmiar:
            fragmenty.append(Fragment(z_metryczka(tresc), zrodlo, naglowek))
            continue
        start = 0
        while start < len(tresc):
            kawalek = tresc[start : start + rozmiar]
            fragmenty.append(Fragment(z_metryczka(kawalek.strip()), zrodlo, naglowek))
            start += rozmiar - zakladka
    return fragmenty


def zbuduj_indeks(gadatliwie: bool = True) -> int:
    """Czyta wszystkie .md i .txt z folderu wiedza/ i buduje indeks."""
    katalog_wiedzy = cfg().sciezka("wiedza")
    katalog_indeksu = cfg().sciezka("indeks")

    fragmenty: list[Fragment] = []
    for plik in sorted(katalog_wiedzy.rglob("*")):
        if plik.suffix.lower() not in {".md", ".txt"} or plik.name == "README.md":
            continue
        fragmenty.extend(_podziel(plik.read_text(encoding="utf-8"), plik.name))

    if not fragmenty:
        raise RuntimeError(
            f"Folder {katalog_wiedzy} jest pusty. Uruchom najpierw "
            "skrypty/zrzut_strony.py albo wrzuć tam pliki .md."
        )

    # Pasaże bez prefiksu, zapytania z prefiksem — tak działają modele
    # mmlw-retrieval. bge-m3 prefiksu nie potrzebuje, w konfiguracji jest pusty.
    wektory = osadz([f.tekst for f in fragmenty], gadatliwie=gadatliwie)

    np.save(katalog_indeksu / "wektory.npy", np.asarray(wektory, dtype=np.float32))
    (katalog_indeksu / "fragmenty.json").write_text(
        json.dumps([asdict(f) for f in fragmenty], ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    (katalog_indeksu / PLIK_METADANYCH).write_text(
        json.dumps(
            {"silnik": _silnik(), "model": _nazwa_modelu(),
             "wymiar": int(wektory.shape[1]), "fragmentow": len(fragmenty)},
            ensure_ascii=False, indent=1,
        ),
        encoding="utf-8",
    )
    if gadatliwie:
        print(f"Zaindeksowano {len(fragmenty)} fragmentów z {katalog_wiedzy}")
    return len(fragmenty)


_cache: tuple[np.ndarray, list[Fragment]] | None = None


def _wczytaj_indeks() -> tuple[np.ndarray, list[Fragment]]:
    global _cache
    if _cache is None:
        katalog = cfg().sciezka("indeks")
        plik_w = katalog / "wektory.npy"
        plik_f = katalog / "fragmenty.json"
        if not plik_w.exists() or not plik_f.exists():
            raise RuntimeError("Brak indeksu. Uruchom: python skrypty/indeksuj.py")
        wektory = np.load(plik_w)
        fragmenty = [Fragment(**d) for d in json.loads(plik_f.read_text(encoding="utf-8"))]

        # Indeks zbudowany innym modelem da się przeszukać bez błędu i zwróci
        # bzdury, bo iloczyn skalarny policzy się dla każdych wektorów o zgodnym
        # wymiarze. Lepiej odmówić niż podać modelowi losowe fragmenty oferty.
        plik_m = katalog / PLIK_METADANYCH
        if plik_m.exists():
            meta = json.loads(plik_m.read_text(encoding="utf-8"))
            if meta.get("model") != _nazwa_modelu() or meta.get("silnik") != _silnik():
                raise RuntimeError(
                    f"Indeks zbudowano modelem {meta.get('model')} "
                    f"({meta.get('silnik')}), a teraz w konfiguracji jest "
                    f"{_nazwa_modelu()} ({_silnik()}). "
                    "Przebuduj: python skrypty/indeksuj.py"
                )
        _cache = (wektory, fragmenty)
    return _cache


def szukaj(zapytanie: str, ile: int | None = None) -> list[tuple[Fragment, float]]:
    wektory, fragmenty = _wczytaj_indeks()
    ile = ile or cfg().get("embeddingi.liczba_wynikow", 6)
    prefiks = cfg().get("embeddingi.prefiks_zapytania", "")

    wektor = osadz([prefiks + zapytanie])[0]
    podobienstwa = wektory @ np.asarray(wektor, dtype=np.float32)
    najlepsze = np.argsort(-podobienstwa)[:ile]
    return [(fragmenty[i], float(podobienstwa[i])) for i in najlepsze]


def kontekst(zapytanie: str, ile: int | None = None, prog: float = 0.35) -> tuple[str, list[str]]:
    """Zwraca (blok kontekstu do promptu, lista źródeł).

    Próg odcięcia jest ważny: jeśli nic nie przeszło, moduł pisania
    odpowiedzi ma nie wymyślać, tylko oznaczyć pytanie do ręcznej obsługi.
    """
    trafienia = [(f, s) for f, s in szukaj(zapytanie, ile) if s >= prog]
    if not trafienia:
        return "", []

    bloki = []
    zrodla = []
    for fragment, wynik in trafienia:
        etykieta = f"{fragment.zrodlo}" + (f" / {fragment.naglowek}" if fragment.naglowek else "")
        bloki.append(f"[{etykieta}] (trafność {wynik:.2f})\n{fragment.tekst}")
        if etykieta not in zrodla:
            zrodla.append(etykieta)
    return "\n\n---\n\n".join(bloki), zrodla
