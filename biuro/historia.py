"""Historia kontaktu z uczestnikiem.

Nie wymaga nowych danych — powstaje ze składowania ekstrakcji, umów, rozmów
i rezerwacji, które i tak są w bazie. Przy drugim mailu od tej samej osoby
widać, o co pytała wcześniej i na czym stoi jej sprawa.

Dwa zastosowania:
  1. do konsoli, przy przebiegu po skrzynce — żeby nie odpisywać komuś po raz
     trzeci na to samo
  2. do promptu pisania draftu — żeby odpowiedź nie zaczynała się od zera

Dane wrażliwe nie wchodzą tu nigdzie. Historia mówi, ŻE dane są kompletne,
nie jakie są.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .baza import polaczenie
from .pii import zamaskuj


@dataclass
class Historia:
    email: str
    zgloszenia: list[dict] = field(default_factory=list)
    umowy: list[dict] = field(default_factory=list)
    rozmowy: list[dict] = field(default_factory=list)
    ma_dane_do_umowy: bool = False
    statusy: list[str] = field(default_factory=list)

    def pusta(self) -> bool:
        return not (self.zgloszenia or self.umowy or self.rozmowy)

    def linia_do_konsoli(self) -> str:
        if self.pusta():
            return "pierwszy kontakt"
        czesci = []
        if self.zgloszenia:
            czesci.append(f"zgłoszeń: {len(self.zgloszenia)}")
        if self.umowy:
            numery = ", ".join(u["numer"] for u in self.umowy)
            czesci.append(f"umowy: {numery}")
        if self.rozmowy:
            czesci.append(f"rozmów: {len(self.rozmowy)}")
        czesci.append("dane do umowy: " + ("tak" if self.ma_dane_do_umowy else "brak"))
        if self.statusy:
            czesci.append(f"status: {', '.join(sorted(set(self.statusy)))}")
        return " | ".join(czesci)

    def blok_dla_modelu(self) -> str:
        """Kontekst do promptu pisania odpowiedzi.

        Świadomie bez danych wrażliwych i bez wartości pól - model ma wiedzieć,
        czego ta osoba już dopytywała i na jakim etapie jest jej sprawa,
        a nie dysponować jej numerem PESEL.
        """
        if self.pusta():
            return ""
        linie = ["### Historia kontaktu z tą osobą", ""]

        for z in self.zgloszenia:
            opis = f"- zgłoszenie z {z['utworzono'][:10]}"
            if z.get("liczba_osob") and z["liczba_osob"] > 1:
                opis += f", {z['liczba_osob']} osoby"
            linie.append(opis)
            czego_dotyczylo = ", ".join(
                x for x in (z.get("wyjazd_kierunek"), z.get("wyjazd_termin")) if x
            )
            if czego_dotyczylo:
                linie.append(f"  pytała o: {czego_dotyczylo}")
            if z.get("dodatkowe"):
                linie.append(f"  wymagania: {z['dodatkowe']}")
            if z.get("wymagania_innych"):
                linie.append(f"  wymagania innych osób: {z['wymagania_innych']}")

        from .umowy import wyjazdy  # import tutaj, żeby uniknąć cyklu

        try:
            katalog = wyjazdy()
        except RuntimeError:
            katalog = {}
        for u in self.umowy:
            nazwa = katalog.get(u["wyjazd"], {}).get("nazwa", u["wyjazd"])
            linie.append(f"- umowa {u['numer']} z {u['data_zawarcia']} na: {nazwa}")

        for r in self.rozmowy:
            linie.append(f"- rozmowa telefoniczna z {r['utworzono'][:10]}")

        linie.append(
            "- dane do umowy i polisy: "
            + ("przysłane" if self.ma_dane_do_umowy else "jeszcze nieprzysłane")
        )
        linie += [
            "",
            "Wykorzystaj to, żeby nie pytać o rzeczy, które ta osoba już podała, "
            "i żeby nie powtarzać informacji, które już dostała. Nie wymieniaj tej "
            "historii w treści odpowiedzi — służy Tobie, nie klientowi.",
        ]
        return "\n".join(linie)


def dla_adresu(email: str | None) -> Historia:
    if not email:
        return Historia(email="")

    with polaczenie() as conn:
        zgloszenia = [dict(w) for w in conn.execute(
            "SELECT * FROM zgloszenia WHERE lower(email) = lower(?) ORDER BY id",
            (email,),
        ).fetchall()]

        if not zgloszenia:
            return Historia(email=email)

        identyfikatory = [z["id"] for z in zgloszenia]
        znaki = ",".join("?" * len(identyfikatory))

        umowy = [dict(w) for w in conn.execute(
            f"SELECT * FROM umowy WHERE zgloszenie_id IN ({znaki}) ORDER BY id",
            identyfikatory,
        ).fetchall()]

        nazwiska = [z["nazwisko"] for z in zgloszenia if z["nazwisko"]]
        rozmowy = []
        if nazwiska:
            warunki = " OR ".join("osoba LIKE ?" for _ in nazwiska)
            rozmowy = [dict(w) for w in conn.execute(
                f"SELECT * FROM rozmowy WHERE {warunki} ORDER BY id",
                [f"%{n}%" for n in nazwiska],
            ).fetchall()]

        ma_dane = conn.execute(
            f"SELECT COUNT(*) FROM dane_wrazliwe WHERE zgloszenie_id IN ({znaki})",
            identyfikatory,
        ).fetchone()[0] > 0

    return Historia(
        email=email,
        zgloszenia=zgloszenia,
        umowy=umowy,
        rozmowy=rozmowy,
        ma_dane_do_umowy=bool(ma_dane),
        statusy=[z["status"] for z in zgloszenia],
    )


def opis_do_logu(email: str | None) -> str:
    """Bezpieczna linia do konsoli - adres zamaskowany."""
    historia = dla_adresu(email)
    return f"{zamaskuj(email or '')}: {historia.linia_do_konsoli()}"
