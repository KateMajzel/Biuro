"""Odprawa przedwyjazdowa jako projekt maila.

U Warsztatów Arktycznych odprawa jest mailem, nie dokumentem — więc generujemy
mail, nie .docx. Dzięki temu moduł korzysta z tej samej maszynerii co drafty
odpowiedzi: baza wiedzy, historia kontaktu, folder wersji roboczych.

Tak jak wszędzie: aplikacja nie wysyła. Odprawa czeka w wersjach roboczych.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import historia
from .baza import polaczenie
from .config import cfg, prompt
from .llm import chat_json
from .rag import kontekst
from .schemas import ProjektOdpowiedzi, Uczestnik


@dataclass
class WynikOdprawy:
    projekt: ProjektOdpowiedzi
    uczestnik: Uczestnik
    wyjazd: str
    plik: Path | None = None
    folder_skrzynki: str | None = None


def _dane_uczestnika(zgloszenie_id: int) -> tuple[Uczestnik, dict]:
    with polaczenie() as conn:
        wiersz = conn.execute(
            "SELECT * FROM zgloszenia WHERE id = ?", (zgloszenie_id,)
        ).fetchone()
    if wiersz is None:
        raise ValueError(f"Nie ma zgłoszenia o id {zgloszenie_id}")
    z = dict(wiersz)
    uczestnik = Uczestnik(
        imie=z["imie"], nazwisko=z["nazwisko"], nazwa_firmy=z["nazwa_firmy"],
        kraj_region=z["kraj_region"], ulica=z["ulica"], kod_pocztowy=z["kod_pocztowy"],
        miasto=z["miasto"], telefon=z["telefon"], email=z["email"],
        dodatkowe_informacje=z["dodatkowe"],
        wymagania_innych_osob=z["wymagania_innych"],
        liczba_osob=z["liczba_osob"] or 1,
    )
    return uczestnik, z


def _blok_uczestnika(uczestnik: Uczestnik, dane_wyjazdu: dict) -> str:
    linie = [
        "### Uczestnik",
        "",
        f"- imię: {uczestnik.imie or '[nieznane]'}",
        f"- liczba osób w zgłoszeniu: {uczestnik.liczba_osob or 1}",
    ]
    if uczestnik.dodatkowe_informacje:
        linie.append(f"- zgłoszone wymagania: {uczestnik.dodatkowe_informacje}")
    if uczestnik.wymagania_innych_osob:
        linie.append(f"- wymagania pozostałych osób: {uczestnik.wymagania_innych_osob}")
    linie += [
        "",
        "### Wyjazd",
        "",
        f"- nazwa: {dane_wyjazdu.get('nazwa', '')}",
        f"- termin: {dane_wyjazdu.get('termin_od', '?')} – {dane_wyjazdu.get('termin_do', '?')}",
        f"- miejsce: {dane_wyjazdu.get('miejsce', '')}",
    ]
    return "\n".join(linie)


def przygotuj(zgloszenie_id: int, klucz_wyjazdu: str) -> WynikOdprawy:
    from .umowy import wyjazd  # import tutaj, żeby uniknąć cyklu

    uczestnik, _ = _dane_uczestnika(zgloszenie_id)
    dane_wyjazdu = wyjazd(klucz_wyjazdu)

    # Baza wiedzy pytana o odprawę dla tej destynacji. Bez trafień nie
    # generujemy nic - to jest ta sama zasada co przy draftach odpowiedzi.
    zapytanie = (
        f"odprawa przedwyjazdowa {dane_wyjazdu.get('nazwa', '')} "
        f"{dane_wyjazdu.get('miejsce', '')} zbiórka nocleg bagaż sprzęt formalności"
    )
    blok_wiedzy, zrodla = kontekst(zapytanie, ile=12)

    if not blok_wiedzy:
        raise RuntimeError(
            f"Baza wiedzy nie zawiera materiału na odprawę dla '{klucz_wyjazdu}'. "
            f"Dopisz plik do folderu wiedza/ (np. odprawa dla tej destynacji) "
            f"i przebuduj indeks: python skrypty/indeksuj.py"
        )

    blok_historii = historia.dla_adresu(uczestnik.email).blok_dla_modelu()

    tresc_promptu = (
        f"{prompt('odprawa')}\n\n"
        f"### Dane firmy\n{cfg().opis_firmy()}\n\n"
        f"### Baza wiedzy (jedyne dopuszczalne źródło faktów)\n{blok_wiedzy}\n\n"
        f"{_blok_uczestnika(uczestnik, dane_wyjazdu)}\n\n"
        f"{blok_historii}"
    )

    projekt = chat_json(tresc_promptu, ProjektOdpowiedzi, maly=False, proby=2)
    if not projekt.uzyte_zrodla:
        projekt.uzyte_zrodla = zrodla

    return WynikOdprawy(projekt=projekt, uczestnik=uczestnik, wyjazd=klucz_wyjazdu)


def zapisz_do_pliku(wynik: WynikOdprawy) -> Path:
    katalog = cfg().sciezka("umowy").parent / "odprawy"
    katalog.mkdir(parents=True, exist_ok=True)
    nazwa = (
        f"{wynik.wyjazd}-{(wynik.uczestnik.nazwisko or 'bez-nazwiska').lower()}.txt"
    )
    plik = katalog / nazwa
    plik.write_text(
        f"Do: {wynik.uczestnik.email or '[brak adresu]'}\n"
        f"Temat: {wynik.projekt.temat}\n\n"
        f"{wynik.projekt.tresc}\n",
        encoding="utf-8",
    )
    wynik.plik = plik
    return plik


def wstaw_do_skrzynki(wynik: WynikOdprawy) -> str:
    """Odprawa jako nowa wersja robocza w skrzynce, gotowa do wysłania ręcznie."""
    from .mail.imap_client import Mail, Skrzynka

    if not wynik.uczestnik.email:
        raise RuntimeError("Zgłoszenie nie ma adresu e-mail — nie ma gdzie wstawić draftu.")

    # Mail zastępczy: odprawa nie jest odpowiedzią na nic, więc nie ma wątku,
    # do którego miałaby się podłączyć.
    pseudo = Mail(
        message_id="", od=wynik.uczestnik.email, od_nazwa=wynik.uczestnik.imie or "",
        temat=wynik.projekt.temat, data="", tresc="",
    )
    with Skrzynka() as skrzynka:
        folder = skrzynka.wstaw_draft(
            pseudo, wynik.projekt.temat, wynik.projekt.tresc, jako_odpowiedz=False
        )
    wynik.folder_skrzynki = folder
    return folder
