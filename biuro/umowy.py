"""Generowanie umów z szablonu.

Umowa składa się z trzech warstw danych:
  firma     - config.yaml, zmienia się raz w roku (gwarancja, polisa, rachunek)
  wyjazd    - wyjazdy.yaml, zmienia się raz na imprezę (termin, cena, program)
  uczestnik - baza SQLite, inne dla każdej umowy

Zasada, od której nie odstępujemy: **model nie pisze treści umowy**. Podstawiamy
dane w szablon deterministycznie. Bielik może najwyżej sprawdzić kompletność
danych, i to robi osobny moduł.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from docxtpl import DocxTemplate

from .baza import polaczenie
from .config import KORZEN, cfg
from .schemas import DaneWrazliwe, Uczestnik


def wyjazdy() -> dict[str, dict[str, Any]]:
    """Katalog wyjazdów z wyjazdy.yaml.

    Zmienna środowiskowa BIURO_WYJAZDY nadpisuje ścieżkę, tak samo jak
    BIURO_BAZA dla bazy. Powód jest ten sam: testy nie mogą zależeć od
    produkcyjnej konfiguracji. `test_dokumenty.py` i `test_skladanie_promptow.py`
    szukały wyjazdu z pliku przykładowego, więc wpisanie prawdziwych wyjazdów
    firmy wywracało je z KeyError — a przebieg testów nie może mówić nic
    o tym, jakie wyjazdy firma aktualnie sprzedaje.
    """
    nadpisanie = os.getenv("BIURO_WYJAZDY")
    plik = Path(nadpisanie) if nadpisanie else KORZEN / cfg().get("sciezki.wyjazdy", "wyjazdy.yaml")
    if not plik.exists():
        raise RuntimeError(
            f"Brak {plik.name}. Skopiuj wyjazdy.example.yaml do {plik.name} i wypełnij."
        )
    with plik.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def wyjazd(klucz: str) -> dict[str, Any]:
    wszystkie = wyjazdy()
    if klucz not in wszystkie:
        raise KeyError(
            f"Nie ma wyjazdu '{klucz}'. Dostępne: {', '.join(wszystkie) or 'brak'}"
        )
    return wszystkie[klucz]


@dataclass
class WyjazdZgloszenia:
    """Wynik szukania wyjazdu, na który jest zgłoszenie."""

    klucz: str | None = None
    powod: str = ""
    kandydaci: list[str] = field(default_factory=list)


def _uprosc(tekst: str | None) -> str:
    """Małe litery bez polskich znaków — do porównywania nazw kierunków."""
    if not tekst:
        return ""
    bez_ogonkow = unicodedata.normalize("NFKD", tekst)
    bez_ogonkow = "".join(z for z in bez_ogonkow if not unicodedata.combining(z))
    return bez_ogonkow.replace("ł", "l").replace("Ł", "L").lower()


# Słowa, które są w nazwie prawie każdego wyjazdu albo w każdym zgłoszeniu
# i same nie wskazują kierunku. Bez tej listy „warsztaty fotograficzne"
# pasowałoby do wszystkiego, a nazwa miesiąca mogłaby trafić w nazwę miejsca.
NIEISTOTNE = {
    "warsztaty", "warsztat", "warsztatow", "warsztatach",
    "fotograficzne", "fotograficzny", "fotograficznych", "fotografia", "foto",
    "wyjazd", "wyjazdu", "wyjazdem", "wyprawa", "wyprawy", "wyprawe",
    "impreza", "plener", "plenery", "zgloszenie", "zgloszenia",
    "chcialbym", "chcialabym", "chetnie", "jechac", "pojechac", "jade",
    "termin", "terminie", "cena", "osoby", "osob", "osoba",
    # miesiące — mówią o terminie, nie o kierunku
    "stycznia", "styczniu", "lutego", "lutym", "marca", "marcu",
    "kwietnia", "kwietniu", "maja", "maju", "czerwca", "czerwcu",
    "lipca", "lipcu", "sierpnia", "sierpniu", "wrzesnia", "wrzesniu",
    "pazdziernika", "pazdzierniku", "listopada", "listopadzie",
    "grudnia", "grudniu",
}

# Ile początkowych liter musi być wspólnych, żeby uznać dwa słowa za to samo.
# Polska odmiana zmienia końcówkę, nie początek: „Irlandia" w zgłoszeniu bywa
# „Irlandii", „Lofoty" bywają „Lofotach". Porównanie całych napisów odrzucałoby
# te zgłoszenia i kazałoby wpisywać klucz ręcznie.
WSPOLNY_RDZEN = 5


def _slowa(tekst: str | None) -> list[str]:
    uproszczony = _uprosc(tekst)
    return [s for s in re.split(r"[^a-z0-9]+", uproszczony) if s]


def _slowa_kierunku(kierunek: str | None) -> list[str]:
    return [
        s for s in _slowa(kierunek)
        if len(s) >= 4 and s not in NIEISTOTNE
    ]


def _to_samo_slowo(a: str, b: str) -> bool:
    if a == b:
        return True
    wspolny = 0
    for z1, z2 in zip(a, b):
        if z1 != z2:
            break
        wspolny += 1
    return wspolny >= WSPOLNY_RDZEN


def _lata(*teksty: str | None) -> set[str]:
    znalezione: set[str] = set()
    for t in teksty:
        if t:
            znalezione.update(re.findall(r"20\d{2}", t))
    return znalezione


def dopasuj_wyjazd(
    kierunek: str | None,
    termin: str | None,
    katalog: dict[str, dict[str, Any]],
) -> WyjazdZgloszenia:
    """Szuka klucza wyjazdu po kierunku, który podał nadawca.

    Zgłoszenie trzyma kierunek słowami nadawcy — „Irlandia", „wyjazd do
    Irlandii w maju" — a nie klucz z wyjazdy.yaml. Umowa potrzebuje klucza,
    bo stąd bierze termin, cenę i program. Dotąd ten klucz wpisywała osoba
    wystawiająca umowę, co znaczyło, że musiała pamiętać, kto gdzie jedzie.
    Ta funkcja wylicza go z danych, które są już w bazie.

    Rozstrzygamy w dwóch krokach: najpierw po słowach kierunku, potem, gdy
    pasuje więcej niż jeden wyjazd, po roku z terminu. Gdy to nie wystarcza,
    **nie zgadujemy** — zwracamy listę kandydatów i pytanie wraca do
    człowieka. Umowa na niewłaściwy wyjazd ma zły termin, złą cenę i zły
    program, a podpisuje ją uczestnik.
    """
    slowa = _slowa_kierunku(kierunek)
    if not slowa:
        return WyjazdZgloszenia(
            kandydaci=sorted(katalog),
            powod="zgłoszenie nie mówi, o jaki kierunek chodzi",
        )

    punkty: dict[str, int] = {}
    for klucz, dane in katalog.items():
        stog = _slowa(" ".join([
            klucz,
            str(dane.get("nazwa", "")),
            str(dane.get("miejsce", "")),
        ]))
        trafienia = sum(
            1 for s in slowa if any(_to_samo_slowo(s, w) for w in stog)
        )
        if trafienia:
            punkty[klucz] = trafienia

    if not punkty:
        return WyjazdZgloszenia(
            kandydaci=sorted(katalog),
            powod=f"żaden wyjazd nie pasuje do kierunku '{kierunek}'",
        )

    najlepsze = max(punkty.values())
    wybrane = sorted(k for k, p in punkty.items() if p == najlepsze)
    if len(wybrane) == 1:
        return WyjazdZgloszenia(
            klucz=wybrane[0], kandydaci=wybrane,
            powod=f"po kierunku '{kierunek}'",
        )

    # Kilka wyjazdów w ten sam rejon — rozstrzygamy po roku z terminu.
    lata_zgloszenia = _lata(termin)
    if lata_zgloszenia:
        po_roku = [
            k for k in wybrane
            if _lata(str(katalog[k].get("termin_od", "")),
                     str(katalog[k].get("termin_do", ""))) & lata_zgloszenia
        ]
        if len(po_roku) == 1:
            return WyjazdZgloszenia(
                klucz=po_roku[0], kandydaci=wybrane,
                powod=f"po kierunku '{kierunek}' i roku {sorted(lata_zgloszenia)[0]}",
            )

    return WyjazdZgloszenia(
        kandydaci=wybrane,
        powod=(
            f"kierunek '{kierunek}' pasuje do kilku wyjazdów "
            f"({', '.join(wybrane)}), a termin tego nie rozstrzyga"
        ),
    )


def wyjazd_dla_zgloszenia(zgloszenie_id: int) -> WyjazdZgloszenia:
    """Klucz wyjazdu dla zgłoszenia — z istniejącej umowy albo z kierunku.

    Gdy umowa dla tego zgłoszenia już jest w rejestrze, bierzemy klucz z niej.
    Druga umowa dla tego samego zgłoszenia musi dotyczyć tego samego wyjazdu,
    bo inaczej rejestr i wykaz dla UFG przestają się zgadzać.
    """
    with polaczenie() as conn:
        z = conn.execute(
            "SELECT wyjazd_kierunek, wyjazd_termin, wyjazd_data_od, wyjazd_klucz "
            "FROM zgloszenia WHERE id = ?",
            (zgloszenie_id,),
        ).fetchone()
        if z is None:
            raise ValueError(f"Nie ma zgłoszenia o id {zgloszenie_id}")
        u = conn.execute(
            "SELECT wyjazd FROM umowy WHERE zgloszenie_id = ? AND wyjazd IS NOT NULL",
            (zgloszenie_id,),
        ).fetchone()

    if u is not None and u["wyjazd"]:
        return WyjazdZgloszenia(
            klucz=u["wyjazd"], kandydaci=[u["wyjazd"]],
            powod="z umowy, która już jest w rejestrze",
        )

    katalog = wyjazdy()
    # Klucz zapisany przy wpływie zgłoszenia — ustalony z tematu formularza,
    # czyli z tego, co klient sam wybrał na stronie.
    if z["wyjazd_klucz"] and z["wyjazd_klucz"] in katalog:
        return WyjazdZgloszenia(
            klucz=z["wyjazd_klucz"], kandydaci=[z["wyjazd_klucz"]],
            powod="zapisany przy zgłoszeniu",
        )

    termin = " ".join(
        t for t in (z["wyjazd_termin"], z["wyjazd_data_od"]) if t
    )
    return dopasuj_wyjazd(z["wyjazd_kierunek"], termin, katalog)


def wyjazd_z_wiadomosci(
    temat: str | None,
    kierunek: str | None,
    termin: str | None,
    katalog: dict[str, dict[str, Any]],
) -> WyjazdZgloszenia:
    """Wyjazd, którego dotyczy zgłoszenie — najpierw z tematu, potem z treści.

    Formularz na stronie składa temat sam: „Zgłoszenie na wyjazd — Walia —
    klify i zamki (20–25.09.2027) — Beata L". Nazwa wyjazdu i termin są więc
    w wiadomości zawsze i w stałym miejscu, i nie trzeba pytać o nie modelu.
    Dopiero gdy temat nic nie mówi (zwykły mail, nie formularz), próbujemy
    kierunku, który model wyczytał z treści.
    """
    z_tematu = dopasuj_wyjazd(temat, f"{temat or ''} {termin or ''}", katalog)
    if z_tematu.klucz is not None:
        z_tematu.powod = "z tematu wiadomości"
        return z_tematu
    z_tresci = dopasuj_wyjazd(kierunek, termin, katalog)
    if z_tresci.klucz is not None:
        return z_tresci
    # brak rozstrzygnięcia: oddajemy węższą z dwóch list kandydatów
    if z_tematu.kandydaci and len(z_tematu.kandydaci) < len(katalog):
        return z_tematu
    return z_tresci


def opis_uczestnika(zgloszenie_id: int) -> str:
    """Imię i nazwisko do potwierdzenia na ekranie, bez danych wrażliwych."""
    with polaczenie() as conn:
        z = conn.execute(
            "SELECT imie, nazwisko FROM zgloszenia WHERE id = ?",
            (zgloszenie_id,),
        ).fetchone()
    if z is None:
        return f"zgłoszenie {zgloszenie_id}"
    osoba = " ".join(x for x in (z["imie"], z["nazwisko"]) if x)
    return osoba or f"zgłoszenie {zgloszenie_id}"


def nastepny_numer_umowy() -> str:
    """Kolejny numer umowy w roku bieżącym, wg wzoru z konfiguracji.

    Dwa zabezpieczenia, oba z prawdziwej wtopy. Wzór bez `{nr}` — na przykład
    wpisana na próbę gotowa wartość „7/2024" — przechodził przez `format()`
    bez zmian, więc KAŻDA umowa dostawała ten sam numer. Numer umowy idzie
    do wykazu dla UFG, a powtórzony numer w dokumencie dla urzędu to nie
    literówka. Drugie: nawet poprawny wzór może dać numer już zajęty, jeśli
    ktoś dopisał umowę ręcznie albo zmienił wzór w trakcie roku — wtedy
    szukamy pierwszego wolnego, zamiast wystawiać duplikat.
    """
    rok = date.today().year
    wzor = cfg().get("umowy.wzor_numeru", "{nr}/{rok}")
    if "{nr}" not in wzor:
        raise RuntimeError(
            f"umowy.wzor_numeru w config.yaml to '{wzor}' — brak miejsca na "
            "numer kolejny, więc każda umowa dostałaby ten sam numer.\n"
            "Wpisz wzór, nie gotową wartość, na przykład:\n"
            '    wzor_numeru: "{nr}/{rok}"'
        )

    with polaczenie() as conn:
        zajete = {
            r[0] for r in conn.execute("SELECT numer FROM umowy WHERE numer IS NOT NULL")
        }
        ile = conn.execute(
            "SELECT COUNT(*) FROM umowy WHERE numer LIKE ?", (f"%/{rok}",)
        ).fetchone()[0]

    nr = int(ile) + 1
    while wzor.format(nr=nr, rok=rok) in zajete:
        nr += 1
    return wzor.format(nr=nr, rok=rok)


def _kontekst(
    uczestnik: Uczestnik,
    dane_wrazliwe: DaneWrazliwe | None,
    dane_wyjazdu: dict[str, Any],
    nr_umowy: str,
    nadpisania: dict[str, Any] | None = None,
) -> dict[str, Any]:
    k = cfg()
    f = k["firma"]
    g = k.get("gwarancja", {}) or {}
    u = k.get("ubezpieczenie", {}) or {}
    r = k.get("rachunek", {}) or {}
    w = dane_wrazliwe or DaneWrazliwe()

    # adres do umowy: najpierw ten odesłany mailem, bo bywa aktualniejszy
    ulica = w.ulica or uczestnik.ulica or ""
    kod = w.kod_pocztowy or uczestnik.kod_pocztowy or ""
    miasto = w.miasto or uczestnik.miasto or ""

    kontekst: dict[str, Any] = {
        # meta
        "nr_umowy": nr_umowy,
        "miejscowosc": k.get("umowy.miejscowosc", ""),
        "data_zawarcia": date.today().strftime("%d.%m.%Y"),
        # firma
        "firma_nazwa": f.get("pelna_nazwa") or f.get("nazwa", ""),
        "firma_adres": ", ".join(
            x for x in (f.get("adres"), f"{f.get('kod_pocztowy','')} {f.get('miasto','')}".strip()) if x
        ),
        "firma_nip": f.get("nip", ""),
        "firma_regon": f.get("regon", ""),
        "firma_rejestr_nr": f.get("rejestr_nr", ""),
        "firma_rejestr_organ": f.get("rejestr_organ", ""),
        "firma_telefon": f.get("telefon", ""),
        "firma_email": f.get("email", ""),
        "firma_www": f.get("www", ""),
        # podróżny
        "p_imie": w.imie or uczestnik.imie or "",
        "p_nazwisko": w.nazwisko or uczestnik.nazwisko or "",
        # Uczestnik zagraniczny nie ma PESEL-u. Wtedy w rubryce identyfikacyjnej
        # umowy staje dokument tożsamości, a nie pusta kratka.
        "p_pesel": w.pesel or (
            f"{(uczestnik.typ_dokumentu.value if uczestnik.typ_dokumentu else 'dokument')}: "
            f"{uczestnik.numer_dokumentu}"
            if uczestnik.numer_dokumentu else ""
        ),
        "p_data_urodzenia": w.data_urodzenia or "",
        "p_adres": f"{ulica}, {kod} {miasto}".strip(" ,"),
        "p_telefon": uczestnik.telefon or "",
        "p_email": uczestnik.email or "",
        "p_dokument": w.numer_dokumentu or uczestnik.numer_dokumentu or "",
        "p_wymagania_specjalne": uczestnik.dodatkowe_informacje or "nie zgłoszono",
        "p_zgoda_wizerunek": "wyraża",
        # rachunek
        "bank_nazwa": r.get("bank", ""),
        "bank_numer": r.get("numer", ""),
        "rachunek_powierniczy": r.get("powierniczy", "nie są"),
        # gwarancja
        "g_forma": g.get("forma", ""),
        "g_podmiot": g.get("podmiot", ""),
        "g_adres_kontakt": g.get("adres_kontakt", ""),
        "g_numer": g.get("numer", ""),
        "g_suma": g.get("suma", ""),
        "g_od": g.get("od", ""),
        "g_do": g.get("do", ""),
        # ubezpieczenie
        "u_ubezpieczyciel": u.get("ubezpieczyciel", ""),
        "u_polisa": u.get("polisa", ""),
        "u_kl": u.get("kl", ""),
        "u_nnw": u.get("nnw", ""),
        "u_bagaz": u.get("bagaz", ""),
        "u_assistance": u.get("assistance", ""),
        "u_sprzet": u.get("sprzet", ""),
        "u_sprzet_info": u.get("sprzet_info", ""),
        "u_rezygnacja": u.get("rezygnacja", "nie wykupuje"),
    }

    # wyjazd: wszystkie klucze z wyjazdy.yaml dostają prefiks w_
    for klucz, wartosc in dane_wyjazdu.items():
        kontekst[f"w_{klucz}"] = wartosc

    if nadpisania:
        kontekst.update(nadpisania)
    return kontekst


def braki_w_kontekscie(kontekst: dict[str, Any]) -> list[str]:
    """Pola puste albo wciąż w nawiasach kwadratowych.
    Wywołujemy przed zapisem, żeby nie wygenerować umowy z dziurami."""
    braki = []
    for klucz, wartosc in kontekst.items():
        tekst = str(wartosc or "")
        if not tekst.strip() or (tekst.startswith("[") and tekst.endswith("]")):
            braki.append(klucz)
    return sorted(braki)


def do_pdf(plik_docx: Path) -> Path | None:
    """Konwersja przez LibreOffice. Jeśli go nie ma, zwraca None
    i zostaje sam .docx - to nie powód, żeby przerywać pracę."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir",
         str(plik_docx.parent), str(plik_docx)],
        check=True, capture_output=True, timeout=180,
    )
    pdf = plik_docx.with_suffix(".pdf")
    return pdf if pdf.exists() else None


def _wczytaj_uczestnika(zgloszenie_id: int) -> tuple[Uczestnik, DaneWrazliwe | None]:
    with polaczenie() as conn:
        z = conn.execute("SELECT * FROM zgloszenia WHERE id = ?", (zgloszenie_id,)).fetchone()
        if z is None:
            raise ValueError(f"Nie ma zgłoszenia o id {zgloszenie_id}")
        d = conn.execute(
            "SELECT * FROM dane_wrazliwe WHERE zgloszenie_id = ?", (zgloszenie_id,)
        ).fetchone()

    uczestnik = Uczestnik(
        imie=z["imie"], nazwisko=z["nazwisko"], nazwa_firmy=z["nazwa_firmy"],
        kraj_region=z["kraj_region"], ulica=z["ulica"], kod_pocztowy=z["kod_pocztowy"],
        miasto=z["miasto"], telefon=z["telefon"], email=z["email"],
        dodatkowe_informacje=z["dodatkowe"],
        numer_dokumentu=z["numer_dokumentu"],
        typ_dokumentu=z["typ_dokumentu"],
    )
    wrazliwe = (
        DaneWrazliwe(
            data_urodzenia=d["data_urodzenia"], pesel=d["pesel"],
            numer_dokumentu=d["numer_dokumentu"], ulica=d["ulica"],
            kod_pocztowy=d["kod_pocztowy"], miasto=d["miasto"],
        )
        if d is not None
        else None
    )
    return uczestnik, wrazliwe


def generuj(
    zgloszenie_id: int,
    klucz_wyjazdu: str,
    nadpisania: dict[str, Any] | None = None,
    zapisz_w_rejestrze: bool = True,
) -> tuple[Path, Path | None, list[str]]:
    """Zwraca (ścieżka_docx, ścieżka_pdf_albo_None, lista_brakujących_pól)."""
    plik_szablonu = cfg().sciezka("szablony") / "umowa.docx"
    if not plik_szablonu.exists():
        raise FileNotFoundError(
            f"Brak {plik_szablonu}. Uruchom: "
            "python skrypty/zbuduj_szablon_umowy.py wsad/umowa_zrodlo.docx"
        )

    uczestnik, wrazliwe = _wczytaj_uczestnika(zgloszenie_id)
    dane_wyjazdu = wyjazd(klucz_wyjazdu)
    nr = nastepny_numer_umowy()
    kontekst = _kontekst(uczestnik, wrazliwe, dane_wyjazdu, nr, nadpisania)
    braki = braki_w_kontekscie(kontekst)

    dokument = DocxTemplate(plik_szablonu)
    dokument.render(kontekst)

    katalog = cfg().sciezka("umowy")
    bazowa = (
        f"{nr.replace('/', '-')}-{(uczestnik.nazwisko or 'bez-nazwiska').lower()}"
        f"-{klucz_wyjazdu}"
    )
    docx = katalog / f"{bazowa}.docx"
    dokument.save(docx)

    try:
        pdf = do_pdf(docx)
    except Exception:
        pdf = None

    if zapisz_w_rejestrze:
        with polaczenie() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO umowy
                   (zgloszenie_id, numer, data_zawarcia, wyjazd, data_wyjazdu,
                    kwota, plik_docx, plik_pdf)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    # w kolumnie wyjazd trzymamy KLUCZ z wyjazdy.yaml, nie nazwę -
                    # po nim łączymy umowy z rezerwacjami i listą uczestników
                    zgloszenie_id, nr, date.today().isoformat(),
                    klucz_wyjazdu,
                    str(dane_wyjazdu.get("termin_od", "")),
                    None, str(docx), str(pdf) if pdf else None,
                ),
            )

    return docx, pdf, braki
