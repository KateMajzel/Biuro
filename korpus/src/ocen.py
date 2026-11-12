#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ewaluacja ekstrakcji i klasyfikacji na korpusie testowym.

Liczy cztery rzeczy, celowo rozdzielone, bo mają różną wagę biznesową:

  1. TRAFNOŚĆ PÓL      — ile pól, które powinny być wyciągnięte, jest poprawnych.
  2. HALUCYNACJE       — ile pól, które MUSZĄ zostać puste, model wypełnił.
  3. KLASYFIKACJA      — trafność intencji + macierz pomyłek.
  4. FLAGA DO CZŁOWIEKA — osobno czułość i precyzja, bo koszt jest asymetryczny:
                          niewystawiona flaga to wysłany draft o skutkach prawnych,
                          flaga nadmiarowa to tylko minuta czytania.

Jedna liczba "skuteczność 97%" ukrywa wszystkie cztery. Dlatego raport ich nie łączy.

Użycie:
    python src/ocen.py --gold gold/gold_zgloszenia.json \
                       --predykcje out/predykcje_7b_hybryda.jsonl \
                       --tryb "7B hybryda" --bledy out/bledy_7b.csv

Format predykcji: JSONL, jedna linia na wiadomość:
    {"id": "MAIL_01", "intencja": "...", "do_czlowieka": false,
     "pytania_liczba": 0, "pola": {"wyjazd.nazwa": "...", ...}}
Pola mogą być też zagnieżdżone ({"wyjazd": {"nazwa": "..."}}) — zostaną spłaszczone.
Nazwy pól różne od kanonicznych mapuje schemat/mapowanie_pol.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# korpus/src/ocen.py -> korpus/schemat/
DOMYSLNE_ETYKIETY = Path(__file__).resolve().parent.parent / "schemat" / "etykiety.json"
DOMYSLNE_MAPOWANIE = (
    Path(__file__).resolve().parent.parent / "schemat" / "mapowanie_pol.json"
)
# Ścieżki, które schemat produkcyjny w ogóle próbuje wypełnić. Plik pisze
# adapter.py przy każdym przebiegu, więc lista nie może rozjechać się z kodem.
def _etykiety_produkcyjne() -> set[str]:
    """Nazwy typów produkcyjnych, których w gold być nie może."""
    if not DOMYSLNE_ETYKIETY.exists():
        return set()
    dane = json.loads(DOMYSLNE_ETYKIETY.read_text(encoding="utf-8"))
    return set(dane.get("_tylko_produkcyjne", []))


ETYKIETY_PRODUKCYJNE: set[str] = _etykiety_produkcyjne()

PLIK_POKRYCIA = Path(__file__).resolve().parent.parent / "schemat" / "pokryte.json"
POKRYTE_SCIEZKI: set[str] = (
    set(json.loads(PLIK_POKRYCIA.read_text(encoding="utf-8")))
    if PLIK_POKRYCIA.exists() else set()
)

# --- normalizacja -------------------------------------------------------------

MIESIACE = {
    "stycznia": 1, "styczen": 1, "styczeń": 1,
    "lutego": 2, "luty": 2,
    "marca": 3, "marzec": 3,
    "kwietnia": 4, "kwiecien": 4, "kwiecień": 4,
    "maja": 5, "maj": 5,
    "czerwca": 6, "czerwiec": 6,
    "lipca": 7, "lipiec": 7,
    "sierpnia": 8, "sierpien": 8, "sierpień": 8,
    "wrzesnia": 9, "września": 9, "wrzesien": 9, "wrzesień": 9,
    "pazdziernika": 10, "października": 10, "pazdziernik": 10, "październik": 10,
    "listopada": 11, "listopad": 11,
    "grudnia": 12, "grudzien": 12, "grudzień": 12,
}

PRAWDA = {"true", "tak", "t", "yes", "1", "prawda"}
FALSZ = {"false", "nie", "n", "no", "0", "falsz", "fałsz"}

PUSTE_TEKSTY = {"", "-", "--", "brak", "nie podano", "null", "none", "n/a", "nie dotyczy", "?", "xxx"}


def bez_ogonkow(tekst: str) -> str:
    rozlozony = unicodedata.normalize("NFD", tekst)
    return "".join(z for z in rozlozony if unicodedata.category(z) != "Mn")


def czy_puste(wartosc: Any) -> bool:
    if wartosc is None:
        return True
    if isinstance(wartosc, str):
        return wartosc.strip().lower() in PUSTE_TEKSTY
    if isinstance(wartosc, (list, dict)):
        return len(wartosc) == 0
    return False


def tylko_cyfry(wartosc: Any) -> str:
    return re.sub(r"\D", "", str(wartosc))


def normalizuj_telefon(wartosc: Any) -> str:
    cyfry = tylko_cyfry(wartosc)
    if len(cyfry) > 9 and cyfry.startswith("48"):
        cyfry = cyfry[2:]
    if len(cyfry) > 9 and cyfry.startswith("0"):
        cyfry = cyfry.lstrip("0")
    return cyfry


def normalizuj_date(wartosc: Any) -> str:
    """Zwraca RRRR-MM-DD, jeśli da się rozpoznać; inaczej tekst znormalizowany."""
    s = str(wartosc).strip()
    t = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if t:
        return f"{t.group(1)}-{t.group(2)}-{t.group(3)}"
    t = re.match(r"^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})", s)
    if t:
        return f"{t.group(3)}-{int(t.group(2)):02d}-{int(t.group(1)):02d}"
    t = re.match(r"^(\d{1,2})\s+([a-ząćęłńóśźż]+)\s+(\d{4})", bez_ogonkow(s.lower()))
    if t:
        mies = MIESIACE.get(t.group(2))
        if mies:
            return f"{t.group(3)}-{mies:02d}-{int(t.group(1)):02d}"
    return normalizuj_tekst(s)


def normalizuj_tekst(wartosc: Any, fold: bool = False) -> str:
    s = str(wartosc).strip().lower()
    s = s.replace("—", "-").replace("–", "-")
    s = re.sub(r"\s+", " ", s)
    s = s.strip(" .,:;")
    if fold:
        s = bez_ogonkow(s)
    return s


def rodzaj_pola(sciezka: str) -> str:
    goly = sciezka.split(".")[-1]
    if goly.startswith("telefon"):
        return "telefon"
    if goly in ("nip", "pesel", "kod_dostepu", "kod_dostepu_zapasowy"):
        return "cyfry"
    if goly.startswith("email") or goly == "adres_do_odpowiedzi" or goly == "cc":
        return "email"
    if goly.startswith("data") or goly.startswith("termin") or goly.endswith("_do") or goly.endswith("_od"):
        return "data"
    if goly.startswith(("liczba", "wiek", "procent", "kwota", "budzet", "zaplacono",
                        "kaucja", "wklad_wlasny", "wklad_wlasny_podstawowy",
                        "wklad_wlasny_po_obnizeniu", "rok_urodzenia")) or goly in (
        "liczba_dni", "liczba_osob", "liczba_zarzutow", "pytania_liczba",
        "kwota_do_zaplaty_pozniej", "bagaz_rejestrowany_szt", "liczba_segmentow",
        "liczba_pasazerow", "liczba_gosci", "liczba_kierowcow", "termin_platnosci_dni",
    ):
        return "liczba"
    return "tekst"


def rowne(oczekiwane: Any, otrzymane: Any, sciezka: str, fold: bool) -> bool:
    """Porównanie z tolerancją zależną od rodzaju pola. oczekiwane może być listą wariantów."""
    warianty = oczekiwane if isinstance(oczekiwane, list) else [oczekiwane]
    rodzaj = rodzaj_pola(sciezka)

    for w in warianty:
        if isinstance(w, bool) or isinstance(otrzymane, bool):
            a = w if isinstance(w, bool) else normalizuj_tekst(w) in PRAWDA
            b = (
                otrzymane
                if isinstance(otrzymane, bool)
                else (normalizuj_tekst(otrzymane) in PRAWDA)
                if normalizuj_tekst(otrzymane) in PRAWDA | FALSZ
                else None
            )
            if b is not None and a == b:
                return True
            continue

        if rodzaj == "liczba":
            try:
                if abs(float(str(w).replace(",", ".").replace(" ", ""))
                       - float(str(otrzymane).replace(",", ".").replace(" ", ""))) < 0.011:
                    return True
            except (TypeError, ValueError):
                pass
            continue

        if rodzaj == "telefon":
            if normalizuj_telefon(w) and normalizuj_telefon(w) == normalizuj_telefon(otrzymane):
                return True
            continue

        if rodzaj == "cyfry":
            if tylko_cyfry(w) and tylko_cyfry(w) == tylko_cyfry(otrzymane):
                return True
            # Wartość zamaskowana w opublikowanym korpusie ("XXXXXXXXXX") nie ma
            # cyfr — porównujemy ją wtedy jako tekst.
            if not tylko_cyfry(w) and normalizuj_tekst(w) == normalizuj_tekst(otrzymane):
                return True
            continue

        if rodzaj == "email":
            if normalizuj_tekst(w) == normalizuj_tekst(otrzymane):
                return True
            continue

        if rodzaj == "data":
            if normalizuj_date(w) == normalizuj_date(otrzymane):
                return True
            # tolerancja: oczekiwana data pełna, otrzymany sam rok/miesiąc opisowy
            continue

        a = normalizuj_tekst(w, fold)
        b = normalizuj_tekst(otrzymane, fold)
        if a == b:
            return True
        # tekst: zaliczamy też zawieranie w jedną stronę, gdy oczekiwany jest krótszy
        if a and len(a) >= 4 and a in b:
            return True

    return False


# --- spłaszczanie i mapowanie -------------------------------------------------


def splaszcz(obiekt: Any, prefiks: str = "") -> dict[str, Any]:
    """Zamienia zagnieżdżony słownik/listę na ścieżki kropkowe z indeksami."""
    wynik: dict[str, Any] = {}
    if isinstance(obiekt, dict):
        for klucz, wartosc in obiekt.items():
            nowa = f"{prefiks}.{klucz}" if prefiks else str(klucz)
            if isinstance(wartosc, (dict, list)) and wartosc and not all(
                isinstance(x, (str, int, float, bool)) for x in
                (wartosc if isinstance(wartosc, list) else [])
            ):
                wynik.update(splaszcz(wartosc, nowa))
            elif isinstance(wartosc, list) and wartosc and all(
                isinstance(x, dict) for x in wartosc
            ):
                wynik.update(splaszcz(wartosc, nowa))
            else:
                wynik[nowa] = wartosc
    elif isinstance(obiekt, list):
        for i, element in enumerate(obiekt):
            wynik.update(splaszcz(element, f"{prefiks}[{i}]"))
    else:
        wynik[prefiks] = obiekt
    return wynik


def zastosuj_mapowanie(pola: dict[str, Any], mapowanie: dict[str, str]) -> dict[str, Any]:
    """Mapowanie jest kanoniczne -> nazwa modelu; tu idziemy w drugą stronę."""
    if not mapowanie:
        return pola
    odwrotne = {v: k for k, v in mapowanie.items()}
    wynik: dict[str, Any] = {}
    for klucz, wartosc in pola.items():
        wynik[odwrotne.get(klucz, klucz)] = wartosc
    return wynik


# --- ocena --------------------------------------------------------------------


def ocen(
    gold: list[dict[str, Any]],
    predykcje: dict[str, dict[str, Any]],
    mapowanie: dict[str, str],
    fold: bool,
    na_zgrubne: dict[str, str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    na_zgrubne = na_zgrubne or {}
    liczniki = Counter()
    bledy: list[dict[str, str]] = []
    pomylki_intencji: Counter = Counter()
    pomylki_zgrubne: Counter = Counter()
    zgrubne_per_klasa: dict[str, Counter] = defaultdict(Counter)
    na_rekord: list[dict[str, Any]] = []
    braki_predykcji: list[str] = []
    przewidziane_etykiety: set[str] = set()
    # Słownik gold, liczony z samego gold. Etykieta przewidziana poza tym
    # zbiorem nie może trafić — nie dlatego, że model się myli, ale dlatego,
    # że odpowiada w innym słowniku. `spam` i `systemowy` są w obu, więc
    # sprawdzanie przynależności do listy produkcyjnej nie wystarcza.
    etykiety_gold: set[str] = {
        str(w["intencja"]) for w in gold if w.get("intencja")
    }

    for wpis in gold:
        ident = wpis["id"]
        pred = predykcje.get(ident)
        if pred is None:
            braki_predykcji.append(ident)
            continue

        pred_pola = zastosuj_mapowanie(
            splaszcz(pred.get("pola", pred.get("fields", {}))), mapowanie
        )

        rekord = {"id": ident, "pola_ok": 0, "pola_zle": 0, "pola_brak": 0, "halucynacje": 0}

        # 1. pola wymagane
        for sciezka, oczekiwane in (wpis.get("pola") or {}).items():
            otrzymane = pred_pola.get(sciezka)
            w_zakresie = sciezka in POKRYTE_SCIEZKI
            if czy_puste(otrzymane):
                liczniki["pola_brak"] += 1
                rekord["pola_brak"] += 1
                if w_zakresie:
                    liczniki["zakres_brak"] += 1
                bledy.append({
                    "id": ident, "typ": "brak_pola", "pole": sciezka,
                    "oczekiwano": json.dumps(oczekiwane, ensure_ascii=False),
                    "otrzymano": "",
                })
            elif rowne(oczekiwane, otrzymane, sciezka, fold):
                liczniki["pola_ok"] += 1
                rekord["pola_ok"] += 1
                if w_zakresie:
                    liczniki["zakres_ok"] += 1
            else:
                liczniki["pola_zle"] += 1
                rekord["pola_zle"] += 1
                if w_zakresie:
                    liczniki["zakres_zle"] += 1
                bledy.append({
                    "id": ident, "typ": "zla_wartosc", "pole": sciezka,
                    "oczekiwano": json.dumps(oczekiwane, ensure_ascii=False),
                    "otrzymano": json.dumps(otrzymane, ensure_ascii=False),
                })

        # 2. pola, które muszą zostać puste
        for sciezka in wpis.get("pola_puste") or []:
            otrzymane = pred_pola.get(sciezka)
            if not czy_puste(otrzymane):
                liczniki["halucynacje"] += 1
                rekord["halucynacje"] += 1
                bledy.append({
                    "id": ident, "typ": "HALUCYNACJA", "pole": sciezka,
                    "oczekiwano": "(puste)",
                    "otrzymano": json.dumps(otrzymane, ensure_ascii=False),
                })
            else:
                liczniki["puste_ok"] += 1

        # 3. zakazane podłańcuchy (przeciek danych między polami)
        for sciezka, zakazane in (wpis.get("pola_nie_zawieraja") or {}).items():
            otrzymane = pred_pola.get(sciezka)
            if czy_puste(otrzymane):
                continue
            tekst = normalizuj_tekst(otrzymane, fold=True)
            for fragment in zakazane:
                if bez_ogonkow(fragment.lower()) in tekst:
                    liczniki["przecieki"] += 1
                    bledy.append({
                        "id": ident, "typ": "PRZECIEK_POLA", "pole": sciezka,
                        "oczekiwano": f"bez fragmentu '{fragment}'",
                        "otrzymano": json.dumps(otrzymane, ensure_ascii=False),
                    })
                    break

        # 4. intencja
        oczekiwana_int = wpis.get("intencja")
        otrzymana_int = pred.get("intencja") or pred.get("intent")
        if otrzymana_int:
            przewidziane_etykiety.add(str(otrzymana_int))
            if str(otrzymana_int) not in etykiety_gold:
                liczniki["intencja_inny_slownik"] += 1
        if oczekiwana_int:
            if normalizuj_tekst(otrzymana_int) == normalizuj_tekst(oczekiwana_int):
                liczniki["intencja_ok"] += 1
            else:
                liczniki["intencja_zle"] += 1
                pomylki_intencji[(oczekiwana_int, str(otrzymana_int))] += 1
                bledy.append({
                    "id": ident, "typ": "zla_intencja", "pole": "intencja",
                    "oczekiwano": str(oczekiwana_int), "otrzymano": str(otrzymana_int),
                })

        # 4a. klasyfikacja zgrubna — jedyny poziom mierzalny na 40 wiadomościach
        if oczekiwana_int and na_zgrubne:
            gold_zgr = na_zgrubne.get(oczekiwana_int, "(nieprzypisana)")
            pred_zgr = na_zgrubne.get(
                normalizuj_tekst(otrzymana_int), na_zgrubne.get(str(otrzymana_int), "(nieprzypisana)")
            )
            zgrubne_per_klasa[gold_zgr]["razem"] += 1
            if gold_zgr == pred_zgr:
                liczniki["zgrubna_ok"] += 1
                zgrubne_per_klasa[gold_zgr]["ok"] += 1
            else:
                liczniki["zgrubna_zle"] += 1
                pomylki_zgrubne[(gold_zgr, pred_zgr)] += 1
                bledy.append({
                    "id": ident, "typ": "ZLA_TRASA", "pole": "klasa_zgrubna",
                    "oczekiwano": gold_zgr, "otrzymano": pred_zgr,
                })

        # 4b. intencje dodatkowe (sprawy, które giną przy jednej etykiecie)
        dodatkowe_gold = set(wpis.get("intencje_dodatkowe") or [])
        if dodatkowe_gold:
            dodatkowe_pred = set(pred.get("intencje_dodatkowe") or [])
            trafione = dodatkowe_gold & dodatkowe_pred
            liczniki["intencje_dodatkowe_ok"] += len(trafione)
            liczniki["intencje_dodatkowe_razem"] += len(dodatkowe_gold)
            for brak in dodatkowe_gold - dodatkowe_pred:
                bledy.append({
                    "id": ident, "typ": "pominieta_sprawa", "pole": "intencje_dodatkowe",
                    "oczekiwano": brak, "otrzymano": ", ".join(sorted(dodatkowe_pred)) or "",
                })

        # 5. flaga do człowieka
        gold_flaga = bool(wpis.get("do_czlowieka"))
        pred_flaga = bool(pred.get("do_czlowieka"))
        if gold_flaga and pred_flaga:
            liczniki["flaga_tp"] += 1
        elif gold_flaga and not pred_flaga:
            liczniki["flaga_fn"] += 1
            bledy.append({
                "id": ident, "typ": "BRAK_FLAGI_DO_CZLOWIEKA", "pole": "do_czlowieka",
                "oczekiwano": f"true — {wpis.get('powod_do_czlowieka') or ''}",
                "otrzymano": "false",
            })
        elif not gold_flaga and pred_flaga:
            liczniki["flaga_fp"] += 1
        else:
            liczniki["flaga_tn"] += 1

        # 6. liczba pytań klienta
        if "pytania_liczba" in wpis:
            try:
                otrzymana_liczba = int(pred.get("pytania_liczba", -1))
            except (TypeError, ValueError):
                otrzymana_liczba = -1
            oczekiwana_liczba = int(wpis["pytania_liczba"])
            liczniki["pytania_razem"] += 1
            if otrzymana_liczba == oczekiwana_liczba:
                liczniki["pytania_dokladnie"] += 1
            if otrzymana_liczba >= 0 and abs(otrzymana_liczba - oczekiwana_liczba) <= 1:
                liczniki["pytania_blisko"] += 1
            if 0 <= otrzymana_liczba < oczekiwana_liczba:
                liczniki["pytania_pominiete"] += 1

        rekord["bez_poprawek"] = (
            rekord["pola_zle"] == 0
            and rekord["pola_brak"] == 0
            and rekord["halucynacje"] == 0
        )
        na_rekord.append(rekord)

    wynik = {
        "liczniki": liczniki,
        "na_rekord": na_rekord,
        "pomylki_intencji": pomylki_intencji,
        "pomylki_zgrubne": pomylki_zgrubne,
        "zgrubne_per_klasa": zgrubne_per_klasa,
        "braki_predykcji": braki_predykcji,
        "rekordow": len(na_rekord),
        # Czy klasyfikator w ogóle odpowiada w tym samym słowniku co gold.
        # Jeśli każda przewidziana etykieta jest nazwą typu produkcyjnego,
        # metryka etykiety szczegółowej nie mierzy modelu, tylko różnicę
        # słowników — i raport musi to powiedzieć, a nie wypisać 0%.
        "etykiety_poza_slownikiem": sorted(przewidziane_etykiety - etykiety_gold),
    }
    return wynik, bledy


def procent(licznik: int, mianownik: int) -> str:
    if mianownik == 0:
        return "   — "
    return f"{100.0 * licznik / mianownik:5.1f}%"


def raport(wynik: dict[str, Any], tryb: str) -> None:
    c: Counter = wynik["liczniki"]
    n = wynik["rekordow"]

    print()
    print("=" * 72)
    print(f"RAPORT EWALUACJI — {tryb}   ({n} wiadomości)")
    print("=" * 72)

    if wynik["braki_predykcji"]:
        print(f"\nUWAGA: brak predykcji dla {len(wynik['braki_predykcji'])} wiadomości: "
              f"{', '.join(wynik['braki_predykcji'][:8])}"
              f"{' …' if len(wynik['braki_predykcji']) > 8 else ''}")

    pola_razem = c["pola_ok"] + c["pola_zle"] + c["pola_brak"]
    zakres_razem = c["zakres_ok"] + c["zakres_zle"] + c["zakres_brak"]

    print("\n1. TRAFNOŚĆ PÓL")
    if zakres_razem:
        # Liczba, którą wolno podawać jako wynik ekstrakcji. Gold opisuje
        # 237 pól, a schemat produkcyjny celowo wypełnia kilkanaście — reszta
        # jest poza zakresem i w liczniku globalnym wygląda jak porażka
        # modelu, choć jest decyzją o zakresie. Obie liczby są prawdziwe,
        # ale mierzą różne rzeczy i żadna nie zastępuje drugiej.
        print(f"   W ZAKRESIE SCHEMATU ({len(POKRYTE_SCIEZKI)} ścieżek)")
        print(f"     poprawne          {c['zakres_ok']:4d} / {zakres_razem:<4d}  "
              f"{procent(c['zakres_ok'], zakres_razem)}")
        print(f"     zła wartość       {c['zakres_zle']:4d}        "
              f"{procent(c['zakres_zle'], zakres_razem)}")
        print(f"     nie wyciągnięte   {c['zakres_brak']:4d}        "
              f"{procent(c['zakres_brak'], zakres_razem)}")
        print(f"   WSZYSTKIE POLA GOLD (z polami poza zakresem schematu)")
    print(f"   poprawne            {c['pola_ok']:4d} / {pola_razem:<4d}  {procent(c['pola_ok'], pola_razem)}")
    print(f"   zła wartość         {c['pola_zle']:4d}        {procent(c['pola_zle'], pola_razem)}")
    print(f"   nie wyciągnięte     {c['pola_brak']:4d}        {procent(c['pola_brak'], pola_razem)}")
    if not zakres_razem:
        print("   (brak schemat/pokryte.json — nie wiem, które pola schemat "
              "próbuje wypełnić,\n    więc nie mogę oddzielić błędu modelu "
              "od decyzji o zakresie. Uruchom adapter.py.)")

    puste_razem = c["halucynacje"] + c["puste_ok"]
    print("\n2. HALUCYNACJE (pola, które miały zostać puste)")
    print(f"   wypełnione mimo braku danych   {c['halucynacje']:4d} / {puste_razem:<4d}  "
          f"{procent(c['halucynacje'], puste_razem)}")
    print(f"   poprawnie puste                {c['puste_ok']:4d}        "
          f"{procent(c['puste_ok'], puste_razem)}")
    if c["przecieki"]:
        print(f"   przecieki między polami        {c['przecieki']:4d}   "
              f"(dane jednej osoby w polu innej)")

    zgr_razem = c["zgrubna_ok"] + c["zgrubna_zle"]
    if zgr_razem:
        print("\n3. KLASYFIKACJA — TRASA (6 klas, poziom mierzalny)")
        print(f"   trafność trasy      {c['zgrubna_ok']:4d} / {zgr_razem:<4d}  "
              f"{procent(c['zgrubna_ok'], zgr_razem)}")
        for klasa, licz in sorted(
            wynik["zgrubne_per_klasa"].items(), key=lambda x: -x[1]["razem"]
        ):
            print(f"     {klasa:<18} {licz['ok']:3d} / {licz['razem']:<3d}  "
                  f"{procent(licz['ok'], licz['razem'])}")

    int_razem = c["intencja_ok"] + c["intencja_zle"]
    print("\n3b. KLASYFIKACJA — ETYKIETA SZCZEGÓŁOWA (19 klas, orientacyjnie)")
    # Klasyfikator produkcyjny ma własny, grubszy słownik typów (`zapytanie`,
    # `formularz`, `uczestnik`), gold używa etykiet szczegółowych
    # (`pytanie_przedsprzedazowe`, `zgloszenie_nowe`). Predykcja z innego
    # słownika nie może trafić — i nie mówi nic o modelu. Podawanie dla niej
    # 0% byłoby prawdziwe arytmetycznie i fałszywe jako ocena.
    inny = c["intencja_inny_slownik"]
    porownywalne = int_razem - inny
    print(f"   predykcji w innym słowniku  {inny:4d} / {int_razem:<4d}"
          "   — nieporównywalne, nie liczone")
    if porownywalne > 0:
        print(f"   trafność na porównywalnych  {c['intencja_ok']:4d} / "
              f"{porownywalne:<4d}  {procent(c['intencja_ok'], porownywalne)}")
    else:
        print("   Żadnej predykcji nie da się porównać na tym poziomie.")
        print("   Mierzalny poziom klasyfikacji to TRASA, punkt 3.")
    if wynik.get("etykiety_poza_slownikiem"):
        poza = ", ".join(wynik["etykiety_poza_slownikiem"][:8])
        print(f"   etykiety spoza słownika gold: {poza}")
    if porownywalne > 0 and c["intencje_dodatkowe_razem"]:
        print(f"   sprawy dodatkowe    {c['intencje_dodatkowe_ok']:4d} / "
              f"{c['intencje_dodatkowe_razem']:<4d}  "
              f"{procent(c['intencje_dodatkowe_ok'], c['intencje_dodatkowe_razem'])}"
              "   (maile o dwóch sprawach)")

    print("\n4. FLAGA DO CZŁOWIEKA  — koszt błędu asymetryczny")
    czulosc_m = c["flaga_tp"] + c["flaga_fn"]
    precyzja_m = c["flaga_tp"] + c["flaga_fp"]
    print(f"   czułość (złapane)   {c['flaga_tp']:4d} / {czulosc_m:<4d}  {procent(c['flaga_tp'], czulosc_m)}"
          "   <- to jest metryka bezpieczeństwa")
    print(f"   precyzja            {c['flaga_tp']:4d} / {precyzja_m:<4d}  {procent(c['flaga_tp'], precyzja_m)}")
    if c["flaga_fn"]:
        print(f"   BŁĄD KRYTYCZNY: {c['flaga_fn']} wiadomości poszłoby do automatycznej "
              "odpowiedzi mimo skutków prawnych lub finansowych")

    if c["pytania_razem"]:
        print("\n5. KOMPLETNOŚĆ — liczba pytań klienta")
        print(f"   dokładnie           {c['pytania_dokladnie']:4d} / {c['pytania_razem']:<4d}  "
              f"{procent(c['pytania_dokladnie'], c['pytania_razem'])}")
        print(f"   z tolerancją ±1     {c['pytania_blisko']:4d} / {c['pytania_razem']:<4d}  "
              f"{procent(c['pytania_blisko'], c['pytania_razem'])}")
        if c["pytania_pominiete"]:
            print(f"   zaniżone (pytanie zginęłoby w draftcie): {c['pytania_pominiete']}")

    bez_poprawek = sum(1 for r in wynik["na_rekord"] if r["bez_poprawek"])
    print("\n6. PODSUMOWANIE NA WIADOMOŚĆ")
    print(f"   bez żadnej poprawki {bez_poprawek:4d} / {n:<4d}  {procent(bez_poprawek, n)}")

    if wynik.get("pomylki_zgrubne"):
        print("\n   Pomyłki trasy (wiadomość poszłaby w niewłaściwą ścieżkę):")
        for (gold_i, pred_i), ile in wynik["pomylki_zgrubne"].most_common(8):
            print(f"     {gold_i:<20} -> {pred_i:<20} x{ile}")

    if wynik["pomylki_intencji"]:
        print("\n   Najczęstsze pomyłki etykiety szczegółowej:")
        for (gold_i, pred_i), ile in wynik["pomylki_intencji"].most_common(6):
            print(f"     {gold_i:<28} -> {pred_i:<28} x{ile}")

    # dolna granica przedziału Wilsona dla wyniku 100% przy n próbach
    dolna_100 = 100.0 * (1.0 / (1.0 + 3.8415 / n)) if n else 0.0
    print()
    print(f"Próba: {n} wiadomości. Przedział ufności jest szeroki — dla wyniku 100%")
    print(f"sięga w dół do około {dolna_100:.0f}%. Te liczby mówią, czy pipeline działa,")
    print("nie jaka będzie skuteczność na prawdziwej skrzynce w sezonie.")
    print()


def main() -> int:
    p = argparse.ArgumentParser(description="Ewaluacja ekstrakcji i klasyfikacji.")
    p.add_argument("--gold", required=True, help="plik gold .json (tablica)")
    p.add_argument("--predykcje", required=True, help="plik .jsonl z wyjściem modelu")
    p.add_argument("--mapowanie", help="schemat/mapowanie_pol.json")
    p.add_argument(
        "--etykiety",
        help="schemat/etykiety.json — ocena trasy (6 klas). Domyślnie brany "
             "z katalogu korpusu, bo bez niego najważniejsza metryka nie liczy się wcale",
    )
    p.add_argument("--tryb", default="bez nazwy", help="etykieta przebiegu do raportu")
    p.add_argument("--bledy", help="zapisz listę błędów do CSV")
    p.add_argument(
        "--bez-ogonkow",
        action="store_true",
        help="porównuj tekst ignorując polskie znaki diakrytyczne",
    )
    args = p.parse_args()

    gold = json.loads(Path(args.gold).read_text(encoding="utf-8"))

    predykcje: dict[str, dict[str, Any]] = {}
    for numer, linia in enumerate(Path(args.predykcje).read_text(encoding="utf-8").splitlines(), 1):
        if not linia.strip():
            continue
        try:
            rekord = json.loads(linia)
        except json.JSONDecodeError as e:
            print(f"BŁĄD: linia {numer} w {args.predykcje} nie jest poprawnym JSON: {e}",
                  file=sys.stderr)
            return 2
        if "id" not in rekord:
            print(f"BŁĄD: linia {numer} bez pola 'id'", file=sys.stderr)
            return 2
        predykcje[rekord["id"]] = rekord

    sciezka_mapowania = Path(args.mapowanie) if args.mapowanie else DOMYSLNE_MAPOWANIE
    mapowanie: dict[str, str] = {}
    if sciezka_mapowania.exists():
        surowe = json.loads(sciezka_mapowania.read_text(encoding="utf-8"))
        mapowanie = {k: v for k, v in surowe.items() if not k.startswith("_") and v}

    # Trasa to jedyny poziom klasyfikacji mierzalny na czterdziestu
    # wiadomościach — poziom szczegółowy ma po jednym przypadku na klasę.
    # Wcześniej `--etykiety` było opcjonalne i bez niego raport po cichu
    # pomijał sekcję trasy, a drukował tylko tę orientacyjną. Raport bez
    # najważniejszej metryki nie może wyglądać jak kompletny raport.
    sciezka_etykiet = Path(args.etykiety) if args.etykiety else DOMYSLNE_ETYKIETY
    na_zgrubne: dict[str, str] = {}
    if sciezka_etykiet.exists():
        dane_etykiet = json.loads(sciezka_etykiet.read_text(encoding="utf-8"))
        na_zgrubne = dane_etykiet.get("szczegolowe_na_zgrubne", {})
    if not na_zgrubne:
        print("UWAGA: nie ma mapowania etykiet na trasy "
              f"({sciezka_etykiet}), więc TRASA nie zostanie policzona.",
              file=sys.stderr)
        print("       To najważniejsza metryka tego raportu — nie publikuj "
              "wyników bez niej.", file=sys.stderr)

    wynik, bledy = ocen(gold, predykcje, mapowanie, args.bez_ogonkow, na_zgrubne)
    raport(wynik, args.tryb)

    if args.bledy:
        sciezka = Path(args.bledy)
        sciezka.parent.mkdir(parents=True, exist_ok=True)
        with sciezka.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["id", "typ", "pole", "oczekiwano", "otrzymano"])
            w.writeheader()
            kolejnosc = {"BRAK_FLAGI_DO_CZLOWIEKA": 0, "HALUCYNACJA": 1, "PRZECIEK_POLA": 2,
                         "ZLA_TRASA": 3, "zla_intencja": 4, "zla_wartosc": 5,
                         "pominieta_sprawa": 6, "brak_pola": 7}
            for b in sorted(bledy, key=lambda x: (kolejnosc.get(x["typ"], 9), x["id"])):
                w.writerow(b)
        print(f"Błędy zapisane do {sciezka} ({len(bledy)} pozycji, "
              "posortowane od najdroższych)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
