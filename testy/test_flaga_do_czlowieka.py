#!/usr/bin/env python3
"""Testy flagi do człowieka. Bez modelu — wywołanie modelu jest podstawiane.

    python testy/test_flaga_do_czlowieka.py

Dlaczego ten plik powstał. Pomiar na korpusie dał czułość flagi 0/20, przy zerze
fałszywych alarmów — model nie podniósł jej ani razu. Przyczyną nie był model:
`zaklasyfikuj` dla maila, którego typ dawał się ustalić wzorcem tematu, zwracała
wynik **bez wywołania modelu**, a `do_czlowieka` brało wtedy wartość domyślną
`False`. Wszystkie zgłoszenia w prawdziwej skrzynce przychodzą z formularza, więc
flaga nie mogła się zapalić na żadnym z nich. Zgłoszenie ze sprzecznością albo
z PESEL-em o złej długości dostawało automatyczny projekt odpowiedzi.

Reguła, którą te testy pilnują: **żadna optymalizacja trasy nie zdejmuje flagi.**
Warunek stwierdzony mechanicznie podnosi ją niezależnie od modelu; model może
dodać warunek, którego regex nie widzi, i tej flagi nikt nie zdejmuje.
"""

import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KORZEN))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from baza_testowa import wymagaj_bazy_testowej  # noqa: E402

wymagaj_bazy_testowej()

from biuro.mail import pipeline  # noqa: E402
from biuro.mail.imap_client import Mail  # noqa: E402
from biuro.schemas import Klasyfikacja, OcenaFlagi, TypMaila  # noqa: E402

TEMAT_FORMULARZA = "Zgłoszenie na wyjazd"

ZGLOSZENIE_ZLE = """Wyjazd: Lofoty — zorze i zima
Imię i nazwisko: Jan Przykładowy
PESEL: 44000001357
Data urodzenia: 1978-04-33
Adres email: jan@example.com
"""

ZGLOSZENIE_CZYSTE = """Wyjazd: Lofoty — zorze i zima
Imię i nazwisko: Jan Przykładowy
Data urodzenia: 1978-04-03
Adres email: jan@example.com
"""


def mail(temat: str, tresc: str) -> Mail:
    return Mail(
        message_id="<test@example.com>",
        od="jan@example.com",
        od_nazwa="Jan Przykładowy",
        temat=temat,
        data="Sun, 8 Nov 2026 16:00:00 +0100",
        tresc=tresc,
        zalaczniki=[],
    )


class AtrapaModelu:
    """Podstawia chat_json. Zapamiętuje, o co i jakim schematem pytano."""

    def __init__(self, flaga: bool = False, powod: str | None = None,
                 cytat: str | None = None) -> None:
        self.flaga = flaga
        self.powod = powod
        self.cytat = cytat
        self.wywolania: list[tuple[str, bool]] = []

    def __call__(self, tresc, schemat, system=None, *, maly=True, proby=3):  # noqa: ARG002
        self.wywolania.append((schemat.__name__, maly))
        if schemat is OcenaFlagi:
            return OcenaFlagi(
                do_czlowieka=self.flaga,
                powod_do_czlowieka=self.powod,
                cytat=self.cytat,
                pytania_liczba=0,
            )
        if schemat is Klasyfikacja:
            return Klasyfikacja(
                typ=TypMaila.ZAPYTANIE,
                pewnosc=0.9,
                uzasadnienie="atrapa",
                wymaga_odpowiedzi=True,
                do_czlowieka=self.flaga,
                powod_do_czlowieka=self.powod,
                pytania_liczba=0,
            )
        raise AssertionError(f"nieoczekiwany schemat: {schemat}")


def z_atrapa(atrapa, temat: str, tresc: str) -> Klasyfikacja:
    stary_chat = pipeline.chat_json
    stary_cfg = pipeline.cfg
    pipeline.chat_json = atrapa

    class Konf:
        def get(self, klucz, domyslna=None):
            if klucz == "poczta.temat_formularza":
                return TEMAT_FORMULARZA
            return stary_cfg().get(klucz, domyslna)

    pipeline.cfg = lambda: Konf()
    try:
        return pipeline.zaklasyfikuj(mail(temat, tresc))
    finally:
        pipeline.chat_json = stary_chat
        pipeline.cfg = stary_cfg


def main() -> int:
    bledy = 0

    def sprawdz(nazwa: str, warunek: bool, szczegol: str = "") -> None:
        nonlocal bledy
        if warunek:
            print(f"OK    {nazwa}")
        else:
            bledy += 1
            print(f"BŁĄD  {nazwa}   {szczegol}")

    # 1. Mail z formularza, dane niemożliwe, model mówi „bez flagi".
    #    To jest dokładnie ten przypadek, który wcześniej przechodził.
    atrapa = AtrapaModelu(flaga=False)
    k = z_atrapa(atrapa, f"{TEMAT_FORMULARZA} — Lofoty", ZGLOSZENIE_ZLE)
    sprawdz("typ nadal ustalany wzorcem tematu", k.typ is TypMaila.FORMULARZ,
            str(k.typ))
    sprawdz("warunek mechaniczny podnosi flagę mimo 'nie' od modelu",
            k.do_czlowieka is True, f"do_czlowieka={k.do_czlowieka}")
    sprawdz("powód wzięty z listy zamkniętej",
            k.powod_do_czlowieka == "dane_zlego_ksztaltu", str(k.powod_do_czlowieka))
    sprawdz("flaga blokuje automatyczny draft", k.wolno_draftowac() is False)
    sprawdz("model jest pytany o flagę także na szybkiej trasie",
            ("OcenaFlagi", False) in atrapa.wywolania, str(atrapa.wywolania))
    sprawdz("ocena flagi idzie na duży model",
            all(not maly for nazwa, maly in atrapa.wywolania if nazwa == "OcenaFlagi"),
            str(atrapa.wywolania))

    # 2. Mail z formularza, dane poprawne, model mówi „bez flagi" — flagi nie ma.
    #    Bez tego przypadku poprawka zamieniłaby jeden błąd na drugi: flagowanie
    #    wszystkiego jest równie bezużyteczne jak nieflagowanie niczego.
    atrapa = AtrapaModelu(flaga=False)
    k = z_atrapa(atrapa, f"{TEMAT_FORMULARZA} — Lofoty", ZGLOSZENIE_CZYSTE)
    sprawdz("czyste zgłoszenie nie dostaje flagi", k.do_czlowieka is False,
            f"do_czlowieka={k.do_czlowieka} powód={k.powod_do_czlowieka}")
    sprawdz("czyste zgłoszenie wolno draftować", k.wolno_draftowac() is True)

    # 3. Mail z formularza, dane poprawne, ale model widzi warunek treściowy.
    #    Regex go nie zobaczy — uczestnik niepełnoletni wynika z treści, nie
    #    z kształtu danych. Tej flagi nie wolno zdjąć.
    atrapa = AtrapaModelu(flaga=True, powod="uczestnik_nieletni")
    k = z_atrapa(atrapa, f"{TEMAT_FORMULARZA} — Lofoty", ZGLOSZENIE_CZYSTE)
    sprawdz("warunek widziany tylko przez model zostaje", k.do_czlowieka is True)
    sprawdz("powód od modelu nie jest nadpisywany",
            k.powod_do_czlowieka == "uczestnik_nieletni", str(k.powod_do_czlowieka))

    # 4. Mail bez wzorca w temacie — klasyfikacja pełna, na dużym modelu.
    atrapa = AtrapaModelu(flaga=False)
    k = z_atrapa(atrapa, "pytanko o Walię", "Czy są jeszcze miejsca?")
    sprawdz("bez wzorca typ ustala model", k.typ is TypMaila.ZAPYTANIE, str(k.typ))
    sprawdz("pełna klasyfikacja idzie na duży model",
            ("Klasyfikacja", False) in atrapa.wywolania, str(atrapa.wywolania))

    # 5. Formuła akceptacji umowy to też szybka trasa — i też nie zwalnia z flagi.
    atrapa = AtrapaModelu(flaga=False)
    k = z_atrapa(atrapa, "Re: umowa", "Akceptuję warunki umowy.\n" + ZGLOSZENIE_ZLE)
    sprawdz("akceptacja umowy: typ z formuły",
            k.typ is TypMaila.AKCEPTACJA_UMOWY, str(k.typ))
    sprawdz("akceptacja umowy: flaga mechaniczna też działa",
            k.do_czlowieka is True, f"do_czlowieka={k.do_czlowieka}")

    # 6. Cytat uzasadniający flagę. Na prawdziwej poczcie model oznaczał
    #    zwykłe zgłoszenie z formularza jako `rezygnacja` albo
    #    `zmiana_w_podpisanej_umowie`, choć w treści nie było o tym ani słowa —
    #    19 flag na 20 wiadomości, czyli system nie oszczędzał ani minuty.
    #    Wymóg wskazania fragmentu nie zdejmuje flagi (koszt przeoczenia
    #    rezygnacji jest wyższy niż minuta czytania), ale oddziela flagi
    #    oparte w treści od wymyślonych, i dopiero to da się zmierzyć.
    tresc_z_rezygnacja = ZGLOSZENIE_CZYSTE + "\nNiestety muszę zrezygnować z wyjazdu.\n"

    atrapa = AtrapaModelu(flaga=True, powod="rezygnacja",
                          cytat="muszę zrezygnować z wyjazdu")
    k = z_atrapa(atrapa, f"{TEMAT_FORMULARZA} — Lofoty", tresc_z_rezygnacja)
    sprawdz("cytat obecny w treści jest potwierdzony",
            k.cytat_potwierdzony is True, str(k.cytat_potwierdzony))

    atrapa = AtrapaModelu(flaga=True, powod="rezygnacja",
                          cytat="klient prosi o zwrot całej wpłaty")
    k = z_atrapa(atrapa, f"{TEMAT_FORMULARZA} — Lofoty", ZGLOSZENIE_CZYSTE)
    sprawdz("cytat wymyślony jest oznaczony jako niepotwierdzony",
            k.cytat_potwierdzony is False, str(k.cytat_potwierdzony))
    sprawdz("flaga z wymyślonym cytatem NIE jest zdejmowana",
            k.do_czlowieka is True, f"do_czlowieka={k.do_czlowieka}")

    atrapa = AtrapaModelu(flaga=True, powod="rezygnacja", cytat=None)
    k = z_atrapa(atrapa, f"{TEMAT_FORMULARZA} — Lofoty", ZGLOSZENIE_CZYSTE)
    sprawdz("brak cytatu też znaczy niepotwierdzony",
            k.cytat_potwierdzony is False, str(k.cytat_potwierdzony))

    # Krótki fragment trafiłby przypadkiem w niemal każdy tekst.
    atrapa = AtrapaModelu(flaga=True, powod="rezygnacja", cytat="wyjazd")
    k = z_atrapa(atrapa, f"{TEMAT_FORMULARZA} — Lofoty", tresc_z_rezygnacja)
    sprawdz("zbyt krótki cytat nie potwierdza niczego",
            k.cytat_potwierdzony is False, str(k.cytat_potwierdzony))

    atrapa = AtrapaModelu(flaga=False)
    k = z_atrapa(atrapa, f"{TEMAT_FORMULARZA} — Lofoty", ZGLOSZENIE_CZYSTE)
    sprawdz("bez flagi nie ma czego potwierdzać",
            k.cytat_potwierdzony is None, str(k.cytat_potwierdzony))

    print()
    if bledy:
        print(f"BŁĘDY: {bledy}")
        return 1
    print("Wszystkie przypadki przeszły.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
