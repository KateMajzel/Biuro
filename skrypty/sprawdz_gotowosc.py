#!/usr/bin/env python3
"""Sprawdzenie gotowości przed uruchomieniem produkcyjnym.

    python skrypty/sprawdz_gotowosc.py
    python skrypty/sprawdz_gotowosc.py --bez-skrzynki   # pomiń łączenie z pocztą

Jedno polecenie zamiast dziesięciu pytań „a czy to na pewno działa".
Pierwsza rzecz do uruchomienia po pobraniu repozytorium i po każdej zmianie
konfiguracji. Kod wyjścia 0 znaczy gotowe.
"""

import argparse
import shutil
import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KORZEN))

OK = "  OK  "
BRAK = " BRAK "
UWAGA = "UWAGA "


class Wynik:
    def __init__(self) -> None:
        self.blokujace: list[str] = []
        self.ostrzezenia: list[str] = []

    def ok(self, co: str, szczegol: str = "") -> None:
        print(f"[{OK}] {co}" + (f" — {szczegol}" if szczegol else ""))

    def blokada(self, co: str, jak_naprawic: str) -> None:
        print(f"[{BRAK}] {co}")
        print(f"         → {jak_naprawic}")
        self.blokujace.append(co)

    def ostrzezenie(self, co: str, konsekwencja: str) -> None:
        print(f"[{UWAGA}] {co}")
        print(f"         → {konsekwencja}")
        self.ostrzezenia.append(co)


def sprawdz_pliki(w: Wynik) -> bool:
    print("\n--- pliki konfiguracyjne ---")
    komplet = True

    for nazwa, wzor, naprawa in (
        ("config.yaml", "config.example.yaml",
         "Copy-Item config.example.yaml config.yaml, potem wypełnij sekcję firma"),
        ("wyjazdy.yaml", "wyjazdy.example.yaml",
         "Copy-Item wyjazdy.example.yaml wyjazdy.yaml, potem wypełnij termin i cenę"),
        (".env", ".env.example",
         "Copy-Item .env.example .env, potem wpisz hasło aplikacji do skrzynki"),
    ):
        if (KORZEN / nazwa).exists():
            w.ok(nazwa)
        else:
            w.blokada(f"brak {nazwa}", naprawa)
            komplet = False
    return komplet


def sprawdz_konfiguracje(w: Wynik) -> None:
    from biuro.config import cfg

    print("\n--- dane firmy ---")
    k = cfg()

    wymagane = {
        "firma.pelna_nazwa": "nazwa do umów",
        "firma.nip": "NIP do umów",
        "firma.adres": "adres do umów",
        "firma.email": "adres kontaktowy w umowie i odprawie",
        "firma.rejestr_nr": "numer wpisu do rejestru organizatorów turystyki",
    }
    for sciezka, opis in wymagane.items():
        wartosc = str(k.get(sciezka) or "").strip()
        if wartosc and not (wartosc.startswith("[") and wartosc.endswith("]")):
            w.ok(sciezka, opis)
        else:
            w.blokada(f"{sciezka} nie jest wypełnione ({opis})",
                      "uzupełnij config.yaml")

    print("\n--- gwarancja, polisa, rachunek ---")
    miekkie = {
        "gwarancja.numer": "numer gwarancji w §8 umowy",
        "gwarancja.suma": "suma gwarancji w §8 umowy",
        "ubezpieczenie.ubezpieczyciel": "ubezpieczyciel w §8 umowy",
        "ubezpieczenie.polisa": "numer polisy w §8 umowy",
        "rachunek.numer": "numer rachunku w §2 umowy",
    }
    for sciezka, opis in miekkie.items():
        wartosc = str(k.get(sciezka) or "").strip()
        if wartosc and not (wartosc.startswith("[") and wartosc.endswith("]")):
            w.ok(sciezka)
        else:
            w.ostrzezenie(f"{sciezka} nie jest wypełnione",
                          f"umowa wyjdzie z luką w: {opis}")


def sprawdz_model(w: Wynik) -> None:
    print("\n--- model ---")
    from biuro.config import cfg
    from biuro.llm import chat, dostepne_modele

    try:
        modele = dostepne_modele()
    except Exception as e:
        w.blokada(f"Ollama nie odpowiada ({type(e).__name__})",
                  "uruchom aplikację Ollama, sprawdź: ollama list")
        return

    w.ok("Ollama odpowiada", f"{len(modele)} modeli lokalnie")

    k = cfg()
    brakuje = []
    for rola in ("duzy", "maly"):
        nazwa = k.get(f"modele.{rola}")
        if any(m == nazwa or m.startswith(f"{nazwa}:") for m in modele):
            w.ok(f"modele.{rola}", nazwa)
        else:
            brakuje.append((rola, nazwa))

    for rola, nazwa in brakuje:
        w.blokada(f"modele.{rola} nie jest pobrany: {nazwa}",
                  f"ollama pull {nazwa}  albo popraw nazwę w config.yaml "
                  f"(dostępne: {', '.join(modele) or 'brak'})")

    if brakuje:
        return

    try:
        odpowiedz = chat("Odpowiedz jednym słowem: tak", limit_tokenow=20)
        w.ok("model generuje odpowiedź", odpowiedz[:40])
    except Exception as e:
        w.blokada(f"model nie odpowiada ({type(e).__name__}: {e})",
                  "sprawdź, czy model mieści się w pamięci karty")


def sprawdz_baze_wiedzy(w: Wynik) -> None:
    print("\n--- baza wiedzy ---")
    from biuro.config import cfg

    katalog = cfg().sciezka("wiedza")
    pliki = [
        p for p in katalog.rglob("*")
        if p.suffix.lower() in {".md", ".txt"} and p.name != "README.md"
    ]
    if not pliki:
        w.blokada("folder wiedza/ jest pusty",
                  "python skrypty/zrzut_strony.py, potem przejrzyj pliki")
        return
    w.ok(f"pliki bazy wiedzy: {len(pliki)}")

    if len(pliki) == 1 and pliki[0].name == "00-przyklad.md":
        w.ostrzezenie("w bazie wiedzy jest tylko plik przykładowy",
                      "drafty będą prawie zawsze oznaczane jako [DO UZUPEŁNIENIA]")

    indeks = cfg().sciezka("indeks")
    if (indeks / "wektory.npy").exists() and (indeks / "fragmenty.json").exists():
        w.ok("indeks zbudowany")
        najnowszy_plik = max(p.stat().st_mtime for p in pliki)
        if najnowszy_plik > (indeks / "wektory.npy").stat().st_mtime:
            w.ostrzezenie("baza wiedzy zmieniona po zbudowaniu indeksu",
                          "uruchom: python skrypty/indeksuj.py")
    else:
        w.blokada("indeks nie jest zbudowany",
                  "python skrypty/indeksuj.py")


def sprawdz_dokumenty(w: Wynik) -> None:
    print("\n--- dokumenty ---")
    from biuro.config import cfg

    szablon = cfg().sciezka("szablony") / "umowa.docx"
    if szablon.exists():
        w.ok("szablon umowy")
    else:
        w.blokada("brak szablonu umowy",
                  "wrzuć swoją umowę do wsad/umowa_zrodlo.docx, potem "
                  "python skrypty/zbuduj_szablon_umowy.py wsad/umowa_zrodlo.docx")

    if shutil.which("soffice") or shutil.which("libreoffice"):
        w.ok("LibreOffice", "umowy będą konwertowane do PDF")
    else:
        w.ostrzezenie("brak LibreOffice",
                      "umowy powstaną jako .docx bez wersji PDF")

    kolumny = cfg().get("ufg.kolumny") or []
    if kolumny:
        w.ok(f"wykaz UFG: {len(kolumny)} kolumn zmapowanych")
    else:
        w.ostrzezenie("brak sekcji ufg.kolumny w config.yaml",
                      "generator wykazu dla UFG nie zadziała")


def sprawdz_skrzynke(w: Wynik) -> None:
    print("\n--- skrzynka ---")
    from biuro.config import cfg

    try:
        cfg().imap_password
    except RuntimeError as e:
        w.blokada(str(e), "wpisz IMAP_PASSWORD w pliku .env")
        return

    if not cfg().imap_user:
        w.blokada("brak adresu skrzynki",
                  "wpisz IMAP_USER w .env albo poczta.uzytkownik w config.yaml")
        return

    from biuro.mail.imap_client import Skrzynka

    try:
        with Skrzynka() as skrzynka:
            w.ok("logowanie do skrzynki", cfg().imap_user)
            folder_draftow = skrzynka.folder_draftow()
            w.ok("folder wersji roboczych", folder_draftow)
            if folder_draftow in ("Drafts",) and "gmail" in cfg().get("poczta.serwer_imap", ""):
                w.ostrzezenie(
                    "folder wersji roboczych znaleziony awaryjnie, nie po fladze",
                    "drafty mogą trafić w złe miejsce — sprawdź pierwszy ręcznie",
                )
            nowe = skrzynka.nowe(dni=3)
            w.ok(f"czytanie skrzynki", f"{len(nowe)} wiadomości z ostatnich 3 dni")
            przyklady = skrzynka.moje_dawne_odpowiedzi(3)
            if przyklady:
                w.ok(f"przykłady stylu z folderu Wysłane", f"{len(przyklady)}")
            else:
                w.ostrzezenie("brak przykładów stylu z folderu Wysłane",
                              "drafty nie będą naśladować Twojego tonu")
    except Exception as e:
        w.blokada(f"nie mogę połączyć się ze skrzynką ({type(e).__name__}: {e})",
                  "sprawdź hasło aplikacji i serwer IMAP w config.yaml")


def sprawdz_baze_danych(w: Wynik) -> None:
    print("\n--- baza danych ---")
    from biuro import baza
    from biuro.config import cfg

    try:
        baza.inicjuj()
        stan = baza.stan_biura()
        w.ok("baza SQLite", str(cfg().sciezka("baza").name))
        for klucz, wartosc in stan.items():
            print(f"         {klucz}: {wartosc}")
    except Exception as e:
        w.blokada(f"nie mogę otworzyć bazy ({type(e).__name__}: {e})",
                  "sprawdź uprawnienia do katalogu dane/")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bez-skrzynki", action="store_true",
                        help="pomiń łączenie z pocztą")
    parser.add_argument("--bez-modelu", action="store_true",
                        help="pomiń sprawdzanie Ollamy")
    args = parser.parse_args()

    w = Wynik()
    print("=" * 64)
    print("SPRAWDZENIE GOTOWOŚCI")
    print("=" * 64)

    if not sprawdz_pliki(w):
        print("\nBrak plików konfiguracyjnych — dalsze sprawdzenia pominięte.")
        return 1

    sprawdz_konfiguracje(w)
    if not args.bez_modelu:
        sprawdz_model(w)
    sprawdz_baze_wiedzy(w)
    sprawdz_dokumenty(w)
    sprawdz_baze_danych(w)
    if not args.bez_skrzynki:
        sprawdz_skrzynke(w)

    print("\n" + "=" * 64)
    if w.blokujace:
        print(f"NIE GOTOWE: {len(w.blokujace)} rzeczy blokujących")
        for pozycja in w.blokujace:
            print(f"  - {pozycja}")
        if w.ostrzezenia:
            print(f"\nDodatkowo {len(w.ostrzezenia)} ostrzeżeń.")
        return 1

    if w.ostrzezenia:
        print(f"GOTOWE, z {len(w.ostrzezenia)} ostrzeżeniami:")
        for pozycja in w.ostrzezenia:
            print(f"  - {pozycja}")
        print("\nMożesz uruchamiać. Ostrzeżenia oznaczają luki w dokumentach "
              "albo gorszą jakość draftów, nie awarię.")
        return 0

    print("GOTOWE. Wszystko sprawdzone, bez zastrzeżeń.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
