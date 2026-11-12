#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generator szkieletu ground truth.

Czyta zaimportowaną pocztę, przepuszcza ją przez warstwę deterministyczną
i wypluwa dwa pliki:

  *.json  — szkielet w formacie gold, gotowy dla ocen.py
  *.csv   — ten sam szkielet jako arkusz, jedna wiadomość w wierszu

Pola, które ustala regex z walidacją (e-mail, telefon, PESEL, NIP, kod pocztowy,
daty, kwota, liczba osób, numer umowy, kierunek z zamkniętej listy), są już
wypełnione. Kolumna `pola_puste` jest wstępnie wypełniona propozycją: pola,
dla których warstwa regex nie znalazła nic. Przepisywanie zmienia się wtedy
w potwierdzanie i dopisywanie tego, co wymaga przeczytania treści.

Czego generator NIE robi: nie przypisuje intencji, nie ustawia flagi do człowieka
i nie zgaduje nazwisk. To są decyzje, które mają być w ground truth podjęte
przez człowieka, bo inaczej mierzysz model jego własną odpowiedzią.

Użycie:
    python src/szkielet_gold.py --zrodlo out/maile.jsonl --wyjscie out/szkielet
    python src/szkielet_gold.py --zrodlo poczta.csv --wyjscie out/szkielet \
        --kierunki wyjazdy_kierunki.txt

Wejście: JSONL z parsera (naglowki.od, tresc) albo dowolny JSONL/CSV —
kolumny nadawcy, tematu i treści są rozpoznawane po nazwach.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import warstwa_regex as wr  # noqa: E402

# Kolumny arkusza. Kolejność ma znaczenie — od najczęściej wypełnianych.
KOLUMNY_POL = [
    "wyjazd.nazwa",
    "wyjazd.kierunek",
    "wyjazd.data_od",
    "wyjazd.data_do",
    "wyjazd.termin_opis",
    "zgloszenie.liczba_osob",
    "zgloszenie.pokoj",
    "kontakt.imie_nazwisko",
    "kontakt.email",
    "kontakt.telefon",
    "uczestnicy[0].imie_nazwisko",
    "uczestnicy[0].data_urodzenia",
    "uczestnicy[0].pesel",
    "uczestnicy[0].dokument",
    "uczestnicy[1].imie_nazwisko",
    "uczestnicy[1].rola",
    "faktura.wymagana",
    "faktura.nabywca",
    "faktura.nip",
    "faktura.adres",
    "wymagania.dieta",
    "wymagania.zdrowie",
    "wymagania.inne_osoby",
    "platnosc.kwota",
    "platnosc.data",
    "umowa.numer",
    "zgody.regulamin",
    "zgody.marketing",
]

KOLUMNY_STALE = [
    "id", "temat", "intencja", "intencje_dodatkowe", "do_czlowieka",
    "powod_do_czlowieka", "pytania_liczba",
]
KOLUMNY_KONCOWE = [
    "pola_puste", "braki_do_zgloszenia", "uwagi",
    "_propozycja_pustych", "_z_regexu", "_ostrzezenia",
]

# Pola, dla których warto rozważyć oznaczenie jako pułapka, gdy regex nic nie
# znalazł. Lista jest krótka celowo: propozycja ma być do przejrzenia w pół
# minuty, nie do odklikania. Kolumna `pola_puste` zostaje PUSTA — przenosisz
# do niej tylko te ścieżki, dla których sprawdziłaś, że w treści naprawdę
# nic nie ma. Źle oznaczona pułapka odwraca metrykę: model dostaje karę za
# poprawnie wyciągniętą wartość.
KANDYDACI_NA_PULAPKI = [
    "wyjazd.nazwa",
    "wyjazd.kierunek",
    "wyjazd.data_od",
    "zgloszenie.liczba_osob",
    "zgloszenie.pokoj",
    "kontakt.imie_nazwisko",
    "kontakt.email",
    "kontakt.telefon",
    "uczestnicy[0].pesel",
    "uczestnicy[0].data_urodzenia",
    "faktura.nip",
    "faktura.nabywca",
    "platnosc.kwota",
    "platnosc.data",
    "umowa.numer",
]

# nazwy kolumn/kluczy rozpoznawane na wejściu
KLUCZE_NADAWCY = ("od", "from", "nadawca", "sender", "od_adres", "email_od")
KLUCZE_TEMATU = ("temat", "subject", "tytul", "title")
KLUCZE_TRESCI = ("tresc", "body", "text", "message", "tresc_nowa", "content", "plain")
KLUCZE_ID = ("id", "uid", "message_id", "nr", "numer")


def pierwszy_klucz(rekord: dict[str, Any], kandydaci: tuple[str, ...]) -> Any:
    for k in kandydaci:
        if k in rekord and rekord[k]:
            return rekord[k]
    # zagnieżdżone naglowki.* z parsera
    naglowki = rekord.get("naglowki")
    if isinstance(naglowki, dict):
        for k in kandydaci:
            if naglowki.get(k):
                return naglowki[k]
    return None


def czytaj_wejscie(sciezka: Path) -> list[dict[str, Any]]:
    tekst = sciezka.read_text(encoding="utf-8")
    rekordy: list[dict[str, Any]] = []

    if sciezka.suffix.lower() == ".csv":
        for wiersz in csv.DictReader(tekst.splitlines()):
            rekordy.append(dict(wiersz))
        return rekordy

    for numer, linia in enumerate(tekst.splitlines(), 1):
        if not linia.strip():
            continue
        try:
            rekordy.append(json.loads(linia))
        except json.JSONDecodeError:
            # może to jeden JSON z tablicą
            if numer == 1:
                try:
                    dane = json.loads(tekst)
                    if isinstance(dane, list):
                        return dane
                except json.JSONDecodeError:
                    pass
            print(f"UWAGA: pominięto linię {numer} — niepoprawny JSON", file=sys.stderr)
    return rekordy


def zamaskuj(wartosc: Any) -> str:
    s = str(wartosc)
    return f"{s[:2]}{'*' * max(0, len(s) - 4)}{s[-2:]}" if len(s) > 4 else "****"


def main() -> int:
    p = argparse.ArgumentParser(description="Szkielet ground truth z zaimportowanej poczty.")
    p.add_argument("--zrodlo", required=True, help="JSONL z parsera albo dowolny JSONL/CSV")
    p.add_argument("--wyjscie", required=True, help="prefiks plików wyjściowych (bez rozszerzenia)")
    p.add_argument(
        "--kierunki",
        help="plik tekstowy, jeden kierunek w linii (z wyjazdy.yaml). "
             "Bez niego używana jest lista domyślna.",
    )
    p.add_argument("--limit", type=int, help="przetwórz tylko pierwsze N wiadomości")
    args = p.parse_args()

    kierunki = wr.KIERUNKI_DOMYSLNE
    if args.kierunki:
        kierunki = [
            l.strip() for l in Path(args.kierunki).read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.strip().startswith("#")
        ]

    zrodlo = Path(args.zrodlo)
    if not zrodlo.exists():
        print(f"BŁĄD: nie ma pliku {zrodlo}", file=sys.stderr)
        return 2

    rekordy = czytaj_wejscie(zrodlo)
    if args.limit:
        rekordy = rekordy[: args.limit]
    if not rekordy:
        print("BŁĄD: wejście puste albo nierozpoznane.", file=sys.stderr)
        return 1

    szkielet: list[dict[str, Any]] = []
    wiersze_csv: list[dict[str, Any]] = []
    statystyki = {"pesel_ok": 0, "pesel_zla_suma": 0, "pesel_zly_ksztalt": 0,
                  "nip_zla_suma": 0, "wiele_kierunkow": 0, "bez_kontaktu": 0}

    for i, rekord in enumerate(rekordy, 1):
        ident = str(pierwszy_klucz(rekord, KLUCZE_ID) or f"REAL_{i:03d}")
        temat = str(pierwszy_klucz(rekord, KLUCZE_TEMATU) or "")
        nadawca = str(pierwszy_klucz(rekord, KLUCZE_NADAWCY) or "")
        tresc = str(pierwszy_klucz(rekord, KLUCZE_TRESCI) or "")

        if not tresc:
            print(f"UWAGA: {ident} bez rozpoznanej treści — sprawdź nazwy kolumn",
                  file=sys.stderr)

        wynik = wr.przetworz(f"{temat}\n{tresc}", nadawca, kierunki)
        pola = wynik["pola"]
        statusy = wynik["statusy"]

        st_pesel = statusy.get("uczestnicy[0].pesel", "brak")
        if st_pesel == "ok":
            statystyki["pesel_ok"] += 1
        elif st_pesel == "zla_suma":
            statystyki["pesel_zla_suma"] += 1
        elif st_pesel == "zly_ksztalt":
            statystyki["pesel_zly_ksztalt"] += 1
        if statusy.get("faktura.nip") == "zla_suma":
            statystyki["nip_zla_suma"] += 1
        if statusy.get("wyjazd.kierunek") == "wiele":
            statystyki["wiele_kierunkow"] += 1
        if not pola.get("kontakt.email") and not pola.get("kontakt.telefon"):
            statystyki["bez_kontaktu"] += 1

        # propozycja pól-pułapek — do przejrzenia, nie do przyjęcia na wiarę
        propozycja_pustych = [k for k in KANDYDACI_NA_PULAPKI if k not in pola]

        z_regexu = sorted(pola.keys())
        ostrzezenia = list(wynik["do_czlowieka"])
        if statusy.get("_telefony_odrzucone"):
            ostrzezenia.append(f"odrzucone liczby w polach numerycznych: {statusy['_telefony_odrzucone']}")

        wpis = {
            "id": ident,
            "intencja": None,
            "intencje_dodatkowe": [],
            "do_czlowieka": None,
            "powod_do_czlowieka": None,
            "pytania_liczba": None,
            "pola": pola,
            "pola_puste": [],
            "braki_do_zgloszenia": wynik["braki"],
            "uwagi": "",
            "_propozycja_pustych": propozycja_pustych,
            "_z_regexu": z_regexu,
            "_ostrzezenia": ostrzezenia,
            "_temat": temat,
        }
        szkielet.append(wpis)

        wiersz = {k: "" for k in KOLUMNY_STALE + KOLUMNY_POL + KOLUMNY_KONCOWE}
        wiersz["id"] = ident
        wiersz["temat"] = temat
        for sciezka, wartosc in pola.items():
            if sciezka in wiersz:
                wiersz[sciezka] = wartosc
        wiersz["pola_puste"] = ""
        wiersz["_propozycja_pustych"] = "; ".join(propozycja_pustych)
        wiersz["braki_do_zgloszenia"] = "; ".join(wynik["braki"])
        wiersz["_z_regexu"] = "; ".join(z_regexu)
        wiersz["_ostrzezenia"] = " | ".join(ostrzezenia)
        wiersze_csv.append(wiersz)

    prefiks = Path(args.wyjscie)
    prefiks.parent.mkdir(parents=True, exist_ok=True)

    sciezka_json = prefiks.with_suffix(".json")
    sciezka_json.write_text(
        json.dumps(szkielet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    sciezka_csv = prefiks.with_suffix(".csv")
    with sciezka_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=KOLUMNY_STALE + KOLUMNY_POL + KOLUMNY_KONCOWE)
        w.writeheader()
        w.writerows(wiersze_csv)

    n = len(szkielet)
    wypelnione = sum(len(w["pola"]) for w in szkielet)
    print(f"Przetworzono {n} wiadomości.")
    print(f"  {sciezka_json}  — szkielet w formacie gold")
    print(f"  {sciezka_csv}  — ten sam szkielet jako arkusz (UTF-8 z BOM, otworzy się w Excelu)")
    print()
    print(f"Pól wypełnionych przez regex: {wypelnione} "
          f"(średnio {wypelnione / n:.1f} na wiadomość)")
    print("Do uzupełnienia ręcznie w każdym wierszu: intencja, do_czlowieka, "
          "pytania_liczba oraz pola wymagające przeczytania treści.")
    print()
    print("Kolumna pola_puste jest PUSTA i to jest celowe. W _propozycja_pustych")
    print("masz kandydatów — przenosisz do pola_puste tylko te, dla których")
    print("sprawdziłaś w treści, że danej naprawdę nie ma. Źle oznaczona pułapka")
    print("odwraca metrykę: model dostaje karę za poprawnie wyciągniętą wartość.")
    print()
    print("Warstwa walidacji:")
    print(f"  PESEL poprawny                {statystyki['pesel_ok']:3d}")
    print(f"  PESEL zła suma kontrolna      {statystyki['pesel_zla_suma']:3d}"
          "   <- zostaje w danych, idzie do człowieka")
    print(f"  PESEL zły kształt             {statystyki['pesel_zly_ksztalt']:3d}"
          "   <- usunięty, zgłoszony jako brak")
    print(f"  NIP zła suma kontrolna        {statystyki['nip_zla_suma']:3d}")
    print(f"  wiele kierunków w treści      {statystyki['wiele_kierunkow']:3d}")
    print(f"  bez żadnego kontaktu          {statystyki['bez_kontaktu']:3d}")
    print()
    print("Wartości PESEL nie są wypisywane na ekran. Są w plikach wyjściowych —")
    print("trzymaj je lokalnie i nie commituj do repozytorium.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
