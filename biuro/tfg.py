"""Licznik dni do deklaracji TFG.

Zero modelu, kilkadziesiąt linijek, a chroni przed konsekwencją ustawową.
Jedyny element wzięty z modułu dziennej odprawy - jako przypomnienie,
nie jako ekran.

Aplikacja nie zna przepisu, tylko odlicza dni do dnia wpisanego w config.yaml.
Dzień graniczny sprawdź w aktualnym stanie prawnym; tu jest tylko arytmetyka.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date

from .baza import polaczenie
from .config import cfg

MIESIACE = (
    "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec",
    "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień",
)


@dataclass
class StanTFG:
    okres: str                  # miesiąc, za który składa się deklarację
    termin: date
    dni_do_terminu: int
    umowy_w_okresie: int
    umowy_niezgloszone: int
    po_terminie: bool

    def pilne(self) -> bool:
        prog = cfg().get("tfg.ostrzegaj_od_dni", 7)
        return self.po_terminie or (self.dni_do_terminu <= prog and self.umowy_w_okresie > 0)

    def komunikat(self) -> str:
        if self.po_terminie:
            return (
                f"TERMIN MINĄŁ: deklaracja TFG za {self.okres} miała być złożona "
                f"do {self.termin:%d.%m.%Y} ({abs(self.dni_do_terminu)} dni temu). "
                f"Umów w okresie: {self.umowy_w_okresie}."
            )
        if self.umowy_w_okresie == 0:
            return (
                f"Deklaracja TFG za {self.okres}: termin {self.termin:%d.%m.%Y} "
                f"(za {self.dni_do_terminu} dni). Brak umów w okresie."
            )
        return (
            f"Deklaracja TFG za {self.okres}: termin {self.termin:%d.%m.%Y} "
            f"(za {self.dni_do_terminu} dni). Umów w okresie: {self.umowy_w_okresie}, "
            f"niezgłoszonych: {self.umowy_niezgloszone}."
        )


def _poprzedni_miesiac(dzisiaj: date) -> tuple[int, int]:
    return (dzisiaj.year - 1, 12) if dzisiaj.month == 1 else (dzisiaj.year, dzisiaj.month - 1)


def stan(dzisiaj: date | None = None) -> StanTFG:
    """Deklarację za miesiąc poprzedni składa się do wskazanego dnia
    miesiąca bieżącego."""
    dzisiaj = dzisiaj or date.today()
    dzien = int(cfg().get("tfg.dzien_deklaracji", 21))

    rok_okresu, miesiac_okresu = _poprzedni_miesiac(dzisiaj)
    # dzień graniczny przycięty do długości miesiąca, żeby nie wyjść poza kalendarz
    dzien_terminu = min(dzien, monthrange(dzisiaj.year, dzisiaj.month)[1])
    termin = date(dzisiaj.year, dzisiaj.month, dzien_terminu)

    poczatek = f"{rok_okresu:04d}-{miesiac_okresu:02d}-01"
    koniec = f"{rok_okresu:04d}-{miesiac_okresu:02d}-{monthrange(rok_okresu, miesiac_okresu)[1]:02d}"

    with polaczenie() as conn:
        wiersz = conn.execute(
            """SELECT COUNT(*) AS wszystkie,
                      SUM(CASE WHEN zgloszone_ufg = 0 THEN 1 ELSE 0 END) AS niezgloszone
               FROM umowy WHERE data_zawarcia BETWEEN ? AND ?""",
            (poczatek, koniec),
        ).fetchone()

    return StanTFG(
        okres=f"{MIESIACE[miesiac_okresu - 1]} {rok_okresu}",
        termin=termin,
        dni_do_terminu=(termin - dzisiaj).days,
        umowy_w_okresie=int(wiersz["wszystkie"] or 0),
        umowy_niezgloszone=int(wiersz["niezgloszone"] or 0),
        po_terminie=termin < dzisiaj,
    )
