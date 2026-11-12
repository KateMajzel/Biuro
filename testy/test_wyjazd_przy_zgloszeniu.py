#!/usr/bin/env python3
"""Testy zapisu wyjazdu przy zgłoszeniu.

    python testy/test_wyjazd_przy_zgloszeniu.py

Zgłoszenie z formularza ma w temacie nazwę i termin wyjazdu. Dopóki przebieg
poczty tego nie zapisywał, wszystko dalej stało: lista uczestników była
pusta, umowa i odprawa pytały „dokąd jedzie ta osoba", a wykaz dla UFG nie
miał z czego powstać. Te testy pilnują trzech rzeczy: że nowe zgłoszenie
dostaje klucz wyjazdu, że stare zgłoszenia da się uzupełnić z wiadomości,
które nadal leżą w skrzynce, i że nazwisko bierze się z pola formularza,
a nie z podpisu biura.
"""

import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KORZEN))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import baza_testowa  # noqa: E402

from biuro import baza  # noqa: E402
from biuro.mail import pipeline  # noqa: E402
from biuro.mail.imap_client import Mail  # noqa: E402
from biuro.schemas import Uczestnik  # noqa: E402

TEMAT = "Zgłoszenie na wyjazd — Walia — klify i zamki (21–26.09.2027) — Beata L"
TRESC = (
    "Imię: Beata\n"
    "Nazwisko: Lewandowska\n"
    "Miasto: Gliwice\n"
    "Dodatkowe informacje: proszę o pokój jednoosobowy\n"
    "\n--\nAnna Biurowa\nBiuro Przykładowe\n"
)


def _mail(mid: str, temat: str = TEMAT, tresc: str = TRESC) -> Mail:
    return Mail(message_id=mid, od="biuro@example.com", od_nazwa="Formularz",
                temat=temat, data="2026-11-10", tresc=tresc)


def _wiersz(zid: int) -> dict:
    with baza.polaczenie() as conn:
        return dict(conn.execute(
            "SELECT * FROM zgloszenia WHERE id = ?", (zid,)).fetchone())


def main() -> int:
    bledy = 0

    def sprawdz(nazwa: str, warunek: bool, szczegol: str = "") -> None:
        nonlocal bledy
        if warunek:
            print(f"OK    {nazwa}")
        else:
            bledy += 1
            print(f"BŁĄD  {nazwa}   {szczegol}")

    baza_testowa.wymagaj_bazy_testowej()
    baza.inicjuj()
    with baza.polaczenie() as conn:
        conn.execute("DELETE FROM umowy")
        conn.execute("DELETE FROM zgloszenia")

    # --- nowe zgłoszenie: wyjazd z tematu ----------------------------------
    zid = baza.zapisz_zgloszenie(
        Uczestnik(imie="Beata", nazwisko="Lewandowska"), "formularz", "<m1@test>")
    klucz = pipeline.przypisz_wyjazd(zid, TEMAT)
    w = _wiersz(zid)
    sprawdz("wyjazd ustalony z tematu", klucz == "walia-2027", str(klucz))
    sprawdz("klucz zapisany przy zgłoszeniu", w["wyjazd_klucz"] == "walia-2027",
            str(w["wyjazd_klucz"]))
    sprawdz("pusty kierunek uzupełniony nazwą wyjazdu",
            "Walia" in (w["wyjazd_kierunek"] or ""), str(w["wyjazd_kierunek"]))
    sprawdz("pusty termin uzupełniony z katalogu",
            "21.09.2027" in (w["wyjazd_termin"] or ""), str(w["wyjazd_termin"]))

    # --- to, co napisał nadawca, nie jest nadpisywane -----------------------
    zid2 = baza.zapisz_zgloszenie(
        Uczestnik(imie="Jan", nazwisko="Nowak", wyjazd_kierunek="Walia jesienią",
                  wyjazd_termin="wrzesień 2027"), "formularz", "<m2@test>")
    pipeline.przypisz_wyjazd(zid2, TEMAT)
    w2 = _wiersz(zid2)
    sprawdz("kierunek słowami nadawcy zostaje",
            w2["wyjazd_kierunek"] == "Walia jesienią", str(w2["wyjazd_kierunek"]))
    sprawdz("ale klucz jest zapisany", w2["wyjazd_klucz"] == "walia-2027")

    # --- temat bez wyjazdu: nic nie zgadujemy -------------------------------
    zid3 = baza.zapisz_zgloszenie(
        Uczestnik(imie="Ewa", nazwisko="Kot"), "formularz", "<m3@test>")
    klucz3 = pipeline.przypisz_wyjazd(zid3, "Pytanie o warsztaty")
    sprawdz("temat bez kierunku nie przypisuje wyjazdu", klucz3 is None, str(klucz3))
    sprawdz("i nic nie zapisuje", not _wiersz(zid3)["wyjazd_klucz"])

    # --- wyjazd widać tam, gdzie był potrzebny -------------------------------
    na_liscie = [u["id"] for u in baza.uczestnicy_wyjazdu("walia-2027")]
    sprawdz("zgłoszeni są na liście uczestników jeszcze przed umową",
            zid in na_liscie and zid2 in na_liscie, str(na_liscie))
    from biuro.umowy import wyjazd_dla_zgloszenia
    sprawdz("umowa i odprawa nie pytają już o wyjazd",
            wyjazd_dla_zgloszenia(zid).klucz == "walia-2027")
    sprawdz("zgłoszenie bez wyjazdu nadal wraca do człowieka",
            wyjazd_dla_zgloszenia(zid3).klucz is None)

    # --- stare zgłoszenia: uzupełnienie z wiadomości w skrzynce -------------
    with baza.polaczenie() as conn:
        conn.execute("DELETE FROM zgloszenia")
    stare = baza.zapisz_zgloszenie(
        Uczestnik(imie="Anna", nazwisko="Biurowa"), "formularz", "<stare@test>")
    sprawdz("stare zgłoszenie jest na liście do uzupełnienia",
            "<stare@test>" in baza.zgloszenia_bez_wyjazdu())
    ile = pipeline.uzupelnij_wczesniejsze([_mail("<stare@test>"), _mail("<obce@test>")])
    w = _wiersz(stare)
    sprawdz("uzupełniono jedno zgłoszenie", ile == 1, str(ile))
    sprawdz("stare zgłoszenie dostało wyjazd", w["wyjazd_klucz"] == "walia-2027")
    sprawdz("nazwisko z podpisu biura zastąpione nazwiskiem z formularza",
            (w["imie"], w["nazwisko"]) == ("Beata", "Lewandowska"),
            f"{w['imie']} {w['nazwisko']}")
    sprawdz("po uzupełnieniu lista do naprawy jest pusta",
            not baza.zgloszenia_bez_wyjazdu())
    sprawdz("drugi przebieg niczego nie zmienia",
            pipeline.uzupelnij_wczesniejsze([_mail("<stare@test>")]) == 0)

    # --- prawdziwy układ formularza ze strony --------------------------------
    # Etykiety łączone („Imię i nazwisko", „Adres zamieszkania"), pola łamane
    # na kilka wierszy i drugi numer telefonu w kontakcie awaryjnym.
    FORMULARZ = (
        "Wyjazd: Walia\n"
        "Termin: 21–26.09.2027\n"
        "Imię i nazwisko: Joanna Testowa-Przykład\n"
        "PESEL: 44000001357\n"
        "Obywatelstwo: polskie\n"
        "Dokument: paszport AB 1234567, ważny do 01.01.2035\n"
        "Adres zamieszkania: ul. Przykładowa 1/2, 00-001 Warszawa\n"
        "E-mail: joanna@example.com\n"
        "Telefon: 600 100 200\n"
        "Kontakt w nagłych wypadkach: Maciej Testowy, 600 100 201\n"
        "Pokój: dwuosobowy do dzielenia\n"
        "Dieta / ograniczenia: wegetarianka\n"
        "Faktura: tak — STUDIO PRZYKŁAD, ul. Przykładowa 1/2,\n"
        "  00-001 Warszawa, NIP 1234567890\n"
        "Uwagi: Czy są jeszcze miejsca?\n"
        "  Jeździ Pan po Snowdonii: czy to stałe lokalizacje?\n"
        "Zgoda na regulamin: TAK\n"
        "\n--\nAnna Biurowa\nBiuro Przykładowe\nTelefon: 500 000 000\n"
    )
    d = pipeline.dane_z_formularza(FORMULARZ)
    sprawdz("imię i nazwisko z jednego pola",
            (d.get("imie"), d.get("nazwisko")) == ("Joanna", "Testowa-Przykład"), str(d))
    sprawdz("wyjazd i termin z pól formularza",
            (d.get("wyjazd_kierunek"), d.get("wyjazd_termin")) == ("Walia", "21–26.09.2027"))
    sprawdz("adres rozbity na ulicę, kod i miasto",
            (d.get("ulica"), d.get("kod_pocztowy"), d.get("miasto"))
            == ("ul. Przykładowa 1/2", "00-001", "Warszawa"), str(d))
    sprawdz("e-mail uczestnika, nie biura", d.get("email") == "joanna@example.com")
    sprawdz("telefon uczestnika, nie kontaktu awaryjnego ani biura",
            d.get("telefon") == "600 100 200", str(d.get("telefon")))
    sprawdz("sam numer dokumentu, bez daty ważności",
            d.get("numer_dokumentu") == "AB 1234567", str(d.get("numer_dokumentu")))
    sprawdz("rodzaj dokumentu", d.get("typ_dokumentu") == "paszport")
    sprawdz("NIP z pola łamanego na dwa wiersze", d.get("nip") == "1234567890")
    uwagi = d.get("dodatkowe_informacje", "")
    sprawdz("pokój, dieta i kontakt awaryjny w uwagach",
            all(x in uwagi for x in ("dwuosobowy", "wegetarianka", "Maciej Testowy")), uwagi)
    sprawdz("wiersz kontynuacji z dwukropkiem nie staje się polem",
            "Snowdonii" in uwagi, uwagi)
    sprawdz("układ pól rozpoznany jako formularz", pipeline.to_formularz(FORMULARZ))
    sprawdz("zwykła wiadomość z telefonem to nie formularz",
            not pipeline.to_formularz("Dzień dobry,\nczy są miejsca?\nTelefon: 600 100 200"))

    # stare zgłoszenie z danymi z podpisu: formularz je poprawia w całości
    with baza.polaczenie() as conn:
        conn.execute("DELETE FROM dane_wrazliwe")
        conn.execute("DELETE FROM zgloszenia")
    zle = baza.zapisz_zgloszenie(
        Uczestnik(imie="Anna", nazwisko="Biurowa", email="biuro@example.com",
                  telefon="500 000 000"), "formularz", "<zle@test>")
    pipeline.uzupelnij_wczesniejsze([_mail("<zle@test>", "Nowe zgłoszenie", FORMULARZ)])
    w = _wiersz(zle)
    sprawdz("osoba poprawiona z formularza",
            (w["imie"], w["nazwisko"]) == ("Joanna", "Testowa-Przykład"))
    sprawdz("e-mail i telefon poprawione",
            (w["email"], w["telefon"]) == ("joanna@example.com", "600 100 200"))
    sprawdz("wyjazd ustalony z pola, choć temat nic nie mówi",
            w["wyjazd_klucz"] == "walia-2027", str(w["wyjazd_klucz"]))
    sprawdz("termin słowami klientki zachowany", w["wyjazd_termin"] == "21–26.09.2027")
    with baza.polaczenie() as conn:
        dw = conn.execute("SELECT * FROM dane_wrazliwe WHERE zgloszenie_id = ?",
                          (zle,)).fetchone()
    sprawdz("dane do umowy zapisane", dw is not None)
    sprawdz("numer dokumentu i adres do umowy z formularza",
            dw is not None and (dw["numer_dokumentu"], dw["kod_pocztowy"], dw["miasto"])
            == ("AB 1234567", "00-001", "Warszawa"))
    na_liscie = baza.uczestnicy_wyjazdu("walia-2027")
    sprawdz("osoba jest na liście uczestników z uwagami",
            len(na_liscie) == 1 and "wegetarianka" in (na_liscie[0]["dodatkowe"] or ""))

    # formularz, który kiedyś nie został zapisany jako zgłoszenie
    ile = pipeline.uzupelnij_wczesniejsze([_mail("<nigdy@test>", "Pytanie", FORMULARZ)])
    sprawdz("pominięty formularz dostaje zgłoszenie", ile == 1 and baza.ma_zgloszenie("<nigdy@test>"))
    sprawdz("ponowny przebieg nie tworzy duplikatu",
            pipeline.uzupelnij_wczesniejsze([_mail("<nigdy@test>", "Pytanie", FORMULARZ)]) == 0
            and len(baza.uczestnicy_wyjazdu("walia-2027")) == 2)

    # --- usunięte zgłoszenie nie wraca -----------------------------------------
    wszystkie = [z["id"] for z in baza.zgloszenia_do_wyboru()]
    with baza.polaczenie() as conn:
        conn.execute(
            "INSERT INTO umowy (zgloszenie_id, numer, data_zawarcia, wyjazd) "
            "VALUES (?, '77/2026', '2026-11-11', 'walia-2027')", (zle,))
    usuniete = baza.usun_zgloszenia(wszystkie)
    sprawdz("zgłoszenie z umową nie daje się usunąć",
            usuniete == len(wszystkie) - 1 and baza.ma_zgloszenie("<zle@test>"),
            str(usuniete))
    sprawdz("zgłoszenie bez umowy znika", not baza.ma_zgloszenie("<nigdy@test>"))
    sprawdz("przebieg poczty nie odtwarza usuniętego zgłoszenia",
            pipeline.uzupelnij_wczesniejsze([_mail("<nigdy@test>", "Pytanie", FORMULARZ)]) == 0
            and not baza.ma_zgloszenie("<nigdy@test>"))
    sprawdz("wiadomość nadal uchodzi za obsłużoną",
            baza.czy_przetworzony("<nigdy@test>"))

    print()
    if bledy:
        print(f"BŁĘDY: {bledy}")
        return 1
    print("Wszystkie przypadki przeszły.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
