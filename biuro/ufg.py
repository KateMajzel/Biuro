"""Miesięczny wykaz umów dla UFG/TFG.

Formatu tego pliku NIE zgadujemy. Kolumny i ich kolejność definiuje
`config.yaml` w sekcji `ufg.kolumny`, bo to plik regulacyjny, a wymagania
portalu zmieniają się niezależnie od tej aplikacji.

    python skrypty/zrob_csv_ufg.py --pola        # jakie wartości są dostępne
    python skrypty/zrob_csv_ufg.py 2026 10       # wykaz za październik 2026

Model nie bierze w tym udziału na żadnym etapie.
"""

from __future__ import annotations

import csv
from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .baza import polaczenie
from .config import cfg

# Wartości dostępne do zmapowania na kolumny. Klucz to nazwa, której używasz
# w config.yaml; wartość to opis pokazywany przez --pola.
DOSTEPNE_POLA: dict[str, str] = {
    "nr_umowy": "numer umowy z rejestru",
    "data_zawarcia": "data zawarcia umowy (RRRR-MM-DD)",
    "data_zawarcia_pl": "data zawarcia umowy (DD.MM.RRRR)",
    "wyjazd_klucz": "identyfikator wyjazdu z wyjazdy.yaml",
    "wyjazd_nazwa": "nazwa imprezy",
    "data_rozpoczecia": "data rozpoczęcia imprezy",
    "data_zakonczenia": "data zakończenia imprezy",
    "kraj": "kraj albo miejsce imprezy",
    "liczba_osob": "liczba podróżnych objętych umową",
    "kwota": "cena imprezy zapisana w rejestrze",
    "imie": "imię podróżnego",
    "nazwisko": "nazwisko podróżnego",
    "email": "adres e-mail podróżnego",
    "telefon": "telefon podróżnego",
    "miasto": "miasto podróżnego",
    "kod_pocztowy": "kod pocztowy podróżnego",
}


def _nieuzupelnione(wartosc: Any) -> bool:
    """Pusto albo placeholder z wyjazdy.yaml, np. "[kwota]"."""
    tekst = str(wartosc or "").strip()
    return not tekst or (tekst.startswith("[") and tekst.endswith("]"))


@dataclass
class WynikUFG:
    plik: Path
    wiersze: int
    okres: str
    braki: list[str]
    nieuzupelnione_kwoty: int


def _wiersze_okresu(rok: int, miesiac: int) -> list[dict[str, Any]]:
    from .umowy import wyjazdy  # import tutaj, żeby uniknąć cyklu

    ostatni = monthrange(rok, miesiac)[1]
    poczatek = f"{rok:04d}-{miesiac:02d}-01"
    koniec = f"{rok:04d}-{miesiac:02d}-{ostatni:02d}"

    with polaczenie() as conn:
        umowy_okresu = conn.execute(
            """SELECT u.*, z.imie, z.nazwisko, z.email, z.telefon, z.miasto,
                      z.kod_pocztowy, z.liczba_osob
               FROM umowy u JOIN zgloszenia z ON z.id = u.zgloszenie_id
               WHERE u.data_zawarcia BETWEEN ? AND ?
               ORDER BY u.data_zawarcia, u.numer""",
            (poczatek, koniec),
        ).fetchall()

    katalog_wyjazdow = wyjazdy()
    wiersze: list[dict[str, Any]] = []
    for u in umowy_okresu:
        dane_wyjazdu = katalog_wyjazdow.get(u["wyjazd"], {})
        data_pl = ""
        if u["data_zawarcia"]:
            rok_s, mies_s, dzien_s = u["data_zawarcia"].split("-")
            data_pl = f"{dzien_s}.{mies_s}.{rok_s}"
        wiersze.append({
            "nr_umowy": u["numer"],
            "data_zawarcia": u["data_zawarcia"],
            "data_zawarcia_pl": data_pl,
            "wyjazd_klucz": u["wyjazd"],
            "wyjazd_nazwa": dane_wyjazdu.get("nazwa", u["wyjazd"]),
            "data_rozpoczecia": dane_wyjazdu.get("termin_od", u["data_wyjazdu"]),
            "data_zakonczenia": dane_wyjazdu.get("termin_do", ""),
            "kraj": dane_wyjazdu.get("miejsce", ""),
            "liczba_osob": u["liczba_osob"] or 1,
            "kwota": u["kwota"] if u["kwota"] is not None else dane_wyjazdu.get("cena", ""),
            "imie": u["imie"] or "",
            "nazwisko": u["nazwisko"] or "",
            "email": u["email"] or "",
            "telefon": u["telefon"] or "",
            "miasto": u["miasto"] or "",
            "kod_pocztowy": u["kod_pocztowy"] or "",
            "_id_umowy": u["id"],
        })
    return wiersze


def generuj(rok: int, miesiac: int, oznacz_zgloszone: bool = False) -> WynikUFG:
    k = cfg()
    kolumny = k.get("ufg.kolumny") or []
    if not kolumny:
        raise RuntimeError(
            "Brak sekcji ufg.kolumny w config.yaml. Format wykazu jest zależny od "
            "wymagań portalu, więc aplikacja go nie zgaduje. Uruchom "
            "`python skrypty/zrob_csv_ufg.py --pola`, żeby zobaczyć dostępne wartości."
        )

    nieznane = [
        kol.get("pole") for kol in kolumny
        if kol.get("pole") not in DOSTEPNE_POLA and kol.get("pole") is not None
    ]
    if nieznane:
        raise RuntimeError(
            f"W config.yaml są kolumny odwołujące się do nieznanych pól: "
            f"{', '.join(str(x) for x in nieznane)}. Lista dostępnych: "
            f"`python skrypty/zrob_csv_ufg.py --pola`."
        )

    wiersze = _wiersze_okresu(rok, miesiac)

    katalog = cfg().sciezka("umowy").parent / "ufg"
    katalog.mkdir(parents=True, exist_ok=True)
    plik = katalog / f"wykaz-umow-{rok:04d}-{miesiac:02d}.csv"

    separator = k.get("ufg.separator", ";")
    kodowanie = k.get("ufg.kodowanie", "utf-8-sig")

    with plik.open("w", encoding=kodowanie, newline="") as fh:
        zapis = csv.writer(fh, delimiter=separator, quoting=csv.QUOTE_MINIMAL)
        zapis.writerow([kol.get("naglowek", kol.get("pole", "")) for kol in kolumny])
        for wiersz in wiersze:
            zapis.writerow([
                kol.get("stala", wiersz.get(kol.get("pole"), ""))
                if kol.get("pole") is None else wiersz.get(kol["pole"], "")
                for kol in kolumny
            ])

    # Sprawdzamy KAŻDE zmapowane pole, nie wybrane. Wartość w nawiasach
    # kwadratowych to nieuzupełniony placeholder z wyjazdy.yaml - w pliku
    # regulacyjnym jest równie zła jak pustka.
    braki: list[str] = []
    bez_kwoty = 0
    mapowane = [kol["pole"] for kol in kolumny if kol.get("pole")]
    for wiersz in wiersze:
        if _nieuzupelnione(wiersz.get("kwota")):
            bez_kwoty += 1
        for pole in mapowane:
            if pole == "kwota":
                continue
            if _nieuzupelnione(wiersz.get(pole)):
                braki.append(
                    f"umowa {wiersz['nr_umowy']}: {pole} = "
                    f"{wiersz.get(pole) or 'pusto'}"
                )

    if oznacz_zgloszone and wiersze:
        with polaczenie() as conn:
            conn.executemany(
                "UPDATE umowy SET zgloszone_ufg = 1 WHERE id = ?",
                [(w["_id_umowy"],) for w in wiersze],
            )

    return WynikUFG(
        plik=plik,
        wiersze=len(wiersze),
        okres=f"{miesiac:02d}/{rok}",
        braki=braki,
        nieuzupelnione_kwoty=bez_kwoty,
    )
