"""Ścieżka od maila do draftu. To jest serce projektu.

Przebieg:
  1. pobierz nowe maile (pomijając już przetworzone)
  2. zaklasyfikuj typ maila (mały model)
  3. jeśli to zgłoszenie z formularza - parser deterministyczny,
     a mały model tylko jako awaryjny; wynik do bazy
  4. jeśli to pytanie - RAG po bazie wiedzy + duży model pisze draft
  5. draft wstaw do folderu wersji roboczych, nic nie wysyłaj
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from ..baza import (
    czy_przetworzony,
    dopasuj_zgloszenie,
    oznacz_przetworzony,
    rodzaje_przetworzonych,
    ustaw_status,
    zapisz_dane_wrazliwe,
    zapisz_rezerwacje,
    ma_dane_wrazliwe,
    uzupelnij_z_formularza,
    wiadomosci_usuniete,
    ustaw_wyjazd,
    zapisz_zgloszenie,
    zgloszenia_wg_wiadomosci,
)
from .. import historia
from ..config import cfg, prompt
from ..ekstrakcja import RaportEkstrakcji, ekstrahuj, zloz_wrazliwe
from ..llm import chat_json
from ..pii import oczysc_dla_promptu, zamaskuj, zamaskuj_kod
from ..rag import kontekst
from ..deterministyczne import WynikDeterministyczny, ustal, warunki_deterministyczne
from ..schemas import (
    DaneWrazliwe,
    Klasyfikacja,
    OcenaFlagi,
    ProjektOdpowiedzi,
    Rezerwacja,
    TypMaila,
    Uczestnik,
)
from ..umowy import wyjazd_z_wiadomosci, wyjazdy
from .imap_client import Mail, Skrzynka

# --- 3a. parser deterministyczny dla maili z formularza ---

# Formularz na stronie wysyła wiersze „Etykieta: wartość", zawsze te same.
# Odczytanie ich wprost jest pewniejsze od modelu i kosztuje zero: model
# potrafił wziąć nazwisko z podpisu biura, telefon z kontaktu awaryjnego,
# a adres e-mail z nagłówka wiadomości, która przychodzi z adresu biura.
#
# Etykiety są porównywane bez polskich znaków i bez wielkości liter.
_WIERSZ_POLA = re.compile(r"^(?P<etykieta>[^\W\d_][^:\n]{0,45}?)\s*:\s*(?P<wartosc>.*)$")
_ADRES = re.compile(r"^(?P<ulica>.+?)[,\s]+(?P<kod>\d{2}-\d{3})\s+(?P<miasto>[^,]+)")
_NIP = re.compile(r"NIP\D{0,3}((?:\d[\s-]?){10})", re.IGNORECASE)
_PUSTE = {"", "-", "—", "brak", "nie dotyczy", "n/d"}

# pola przepisywane jeden do jednego: etykieta -> pole zgłoszenia
_PROSTE: dict[str, str] = {
    "imie": "imie", "nazwisko": "nazwisko", "nazwa firmy": "nazwa_firmy",
    "kraj": "kraj_region", "kraj / region": "kraj_region", "kraj/region": "kraj_region",
    "ulica": "ulica", "kod pocztowy": "kod_pocztowy", "miasto": "miasto",
    "telefon": "telefon", "numer telefonu": "telefon", "tel": "telefon", "tel.": "telefon",
    "e-mail": "email", "email": "email", "adres e-mail": "email", "adres email": "email",
    "wyjazd": "wyjazd_kierunek", "termin": "wyjazd_termin",
}
# pola, które trafiają razem do uwag o uczestniku, w tej kolejności
_DO_UWAG: tuple[tuple[str, str], ...] = (
    ("pokoj", "Pokój"),
    ("dieta / ograniczenia", "Dieta"), ("dieta", "Dieta"),
    ("kontakt w naglych wypadkach", "Kontakt w nagłych wypadkach"),
    ("obywatelstwo", "Obywatelstwo"),
    ("doswiadczenie fotograficzne", "Doświadczenie"),
    ("sprzet", "Sprzęt"),
    ("dodatkowe informacje", "Uwagi"), ("uwagi", "Uwagi"), ("wiadomosc", "Uwagi"),
)


def _bez_ogonkow(tekst: str) -> str:
    zamiany = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")
    return re.sub(r"\s+", " ", tekst.translate(zamiany).strip().lower())


def pola_formularza(tresc: str) -> dict[str, str]:
    """Wiersze „Etykieta: wartość" z treści, razem z wierszami kontynuacji.

    Długie pola (Uwagi, Faktura) formularz łamie na kilka wierszy z wcięciem.
    Wiersz zaczynający się od odstępu należy więc do pola nad nim. Pierwsze
    wystąpienie etykiety wygrywa — niżej bywa cytat poprzedniej wiadomości.
    """
    pola: dict[str, str] = {}
    biezace: str | None = None
    for wiersz in tresc.splitlines():
        if not wiersz.strip():
            biezace = None
            continue
        if wiersz[0] in " \t" and biezace:
            pola[biezace] = f"{pola[biezace]} {wiersz.strip()}".strip()
            continue
        dopasowanie = _WIERSZ_POLA.match(wiersz)
        if not dopasowanie:
            biezace = None
            continue
        etykieta = _bez_ogonkow(dopasowanie.group("etykieta"))
        if etykieta in pola:
            biezace = None
            continue
        pola[etykieta] = dopasowanie.group("wartosc").strip()
        biezace = etykieta
    return pola


def dane_z_formularza(tresc: str) -> dict[str, str]:
    """Pola zgłoszenia odczytane z formularza. Tylko te, które są wypełnione."""
    pola = {e: w for e, w in pola_formularza(tresc).items()
            if w.strip().lower() not in _PUSTE}
    dane: dict[str, str] = {}

    for etykieta, pole in _PROSTE.items():
        if etykieta in pola and pole not in dane:
            dane[pole] = pola[etykieta]

    # „Imię i nazwisko: Joanna Przybylak" — ostatni człon to nazwisko;
    # nazwisko dwuczłonowe pisane z łącznikiem zostaje w całości.
    osoba = pola.get("imie i nazwisko")
    if osoba and " " in osoba.strip():
        imiona, _, nazwisko = osoba.strip().rpartition(" ")
        dane["imie"], dane["nazwisko"] = imiona.strip(), nazwisko.strip()

    adres = pola.get("adres zamieszkania") or pola.get("adres")
    if adres:
        dopasowanie = _ADRES.match(adres)
        if dopasowanie:
            dane.setdefault("ulica", dopasowanie.group("ulica").strip(" ,"))
            dane.setdefault("kod_pocztowy", dopasowanie.group("kod"))
            dane.setdefault("miasto", dopasowanie.group("miasto").strip())

    dokument = pola.get("dokument")
    if dokument:
        maly = _bez_ogonkow(dokument)
        if maly.startswith("paszport"):
            dane["typ_dokumentu"] = "paszport"
        elif maly.startswith("dowod"):
            dane["typ_dokumentu"] = "dowod_osobisty"
        numer = re.sub(r"^(paszport|dow[oó]d(\s+osobisty)?)\s*", "",
                       dokument.strip(), flags=re.IGNORECASE)
        numer = numer.split(",")[0].split(";")[0].strip()
        if numer:
            dane["numer_dokumentu"] = numer

    faktura = pola.get("faktura")
    if faktura:
        nip = _NIP.search(faktura)
        if nip:
            dane["nip"] = re.sub(r"\D", "", nip.group(1))
        firma = re.match(r"^\s*tak\s*[—–-]\s*(?P<nazwa>[^,]+)", faktura, re.IGNORECASE)
        if firma:
            dane.setdefault("nazwa_firmy", firma.group("nazwa").strip())

    uwagi: list[str] = []
    widziane: set[str] = set()
    for etykieta, nazwa in _DO_UWAG:
        if etykieta in pola and nazwa not in widziane:
            widziane.add(nazwa)
            wartosc = pola[etykieta]
            if nazwa == "Uwagi" and len(wartosc) > 300:
                wartosc = wartosc[:297].rstrip() + "…"
            uwagi.append(f"{nazwa}: {wartosc}")
    if uwagi:
        dane["dodatkowe_informacje"] = "; ".join(uwagi)
    return dane


def to_formularz(tresc: str) -> bool:
    """Czy treść wygląda na formularz ze strony, niezależnie od tematu."""
    pola = pola_formularza(tresc)
    ma_osobe = "imie i nazwisko" in pola or ("imie" in pola and "nazwisko" in pola)
    reszta = sum(1 for e in ("wyjazd", "termin", "telefon", "e-mail", "email",
                             "pesel", "adres zamieszkania", "zgoda na regulamin")
                 if e in pola)
    return ma_osobe and reszta >= 3


def parsuj_formularz(tresc: str) -> Uczestnik:
    return Uczestnik(**dane_z_formularza(tresc))


def wyciagnij_dane(mail: Mail) -> RaportEkstrakcji:
    """Warstwa deterministyczna plus model, w trybie z config.yaml.

    Parser pól etykietowanych z formularza nadal działa i uzupełnia to, czego
    nie obsługuje warstwa walidowana (imię, nazwisko, ulica, miasto).
    """
    # Temat MUSI wejść do ekstrakcji. W prawdziwych zgłoszeniach nazwa wyjazdu
    # i termin bywają wyłącznie w temacie ("Zgłoszenie na wyjazd — Lofoty,
    # 12-19.02.2027"), a nie w treści. Bez tego pola wyjazd_kierunek
    # i wyjazd_termin zostawały puste, mimo że dane były w wiadomości.
    raport = ekstrahuj(f"{mail.temat}\n\n{mail.skrot(3000)}")

    # pola etykietowane z formularza: tanie, pewne, bez modelu
    dane = raport.uczestnik.model_dump()
    # Pole z etykietą WYGRYWA z modelem, a nie tylko wypełnia po nim luki.
    # Formularz przychodzi z adresu biura i ma pod spodem podpis biura, więc
    # model potrafił wziąć imię i nazwisko z podpisu — i zgłoszenie klientki
    # trafiało do bazy pod nazwiskiem właścicielki. Wiersz „Imię i nazwisko: …"
    # jest jednoznaczny; podpis nie jest. To samo z telefonem (w treści jest
    # też numer kontaktu awaryjnego) i z adresem e-mail.
    pola = dane_z_formularza(mail.tresc)
    for nazwa, z_pola in pola.items():
        if dane.get(nazwa) != z_pola:
            dane[nazwa] = z_pola
            raport.pola_z_regexu.append(nazwa)

    # adres zwrotny jest pewniejszy niż to, co model wyczyta z treści
    if not dane.get("email") and mail.od:
        dane["email"] = mail.od
        raport.pola_z_regexu.append("email (z nagłówka)")

    raport.uczestnik = Uczestnik.model_validate(dane)
    raport.pola_z_regexu = sorted(set(raport.pola_z_regexu))
    if pola:
        # Dane do umowy składamy jeszcze raz, już z polami formularza:
        # numer dokumentu i adres mają pochodzić z wierszy „Dokument:"
        # i „Adres zamieszkania:", a nie z tego, co przepisał model.
        raport.wrazliwe = zloz_wrazliwe(ustal(mail.tresc), raport.uczestnik)
    return raport


# --- 2. klasyfikacja ---


FORMULA_AKCEPTACJI = re.compile(r"akceptuj[ęe]\s+warunki\s+umowy", re.IGNORECASE)

DATA_W_TEKSCIE = re.compile(r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\b")
DATA_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def przypisz_wyjazd(
    zgloszenie_id: int, temat: str | None,
    kierunek: str | None = None, termin: str | None = None,
) -> str | None:
    """Zapisuje przy zgłoszeniu, na który wyjazd z wyjazdy.yaml ono jest.

    Bez tego zgłoszenie leżało w bazie z kierunkiem „słowami" albo bez niego,
    a każdy dalszy krok — umowa, lista uczestników, odprawa, wykaz dla UFG —
    musiał pytać człowieka, dokąd ta osoba jedzie. Tymczasem formularz sam
    wpisuje nazwę i termin wyjazdu do tematu wiadomości.

    Zwraca klucz wyjazdu albo None, gdy nie da się go ustalić jednoznacznie.
    Wtedy nic nie zapisujemy: lepiej zapytać przy umowie, niż zgadnąć tutaj.
    """
    try:
        katalog = wyjazdy()
    except RuntimeError:
        return None
    wynik = wyjazd_z_wiadomosci(temat, kierunek, termin, katalog)
    if wynik.klucz is None:
        return None
    dane = katalog.get(wynik.klucz, {})
    od, do = dane.get("termin_od"), dane.get("termin_do")
    termin_katalogu = f"{od}–{do}" if od and do else (str(od) if od else None)
    ustaw_wyjazd(zgloszenie_id, wynik.klucz,
                 str(dane.get("nazwa") or wynik.klucz), termin_katalogu)
    return wynik.klucz


def uzupelnij_wczesniejsze(wiadomosci: list[Mail]) -> int:
    """Dopisuje dane z formularza do zgłoszeń sprzed tej poprawki.

    Zgłoszenia zapisane wcześniej nie mają klucza wyjazdu, część ma imię
    i nazwisko z podpisu biura, a pola formularza w ogóle nie były czytane.
    Wiadomości nadal są w skrzynce, więc da się to naprawić bez modelu:
    wszystko z wierszy formularza, wyjazd z pola „Wyjazd:" albo z tematu.
    Zwraca liczbę zgłoszeń, którym udało się przypisać wyjazd.
    """
    znane = zgloszenia_wg_wiadomosci()
    usuniete = wiadomosci_usuniete()
    naprawione = 0
    for mail in wiadomosci:
        pola = dane_z_formularza(mail.tresc)
        zgl_id, mial_wyjazd = znane.get(mail.message_id, (None, False))
        if zgl_id is None:
            # Formularz, który kiedyś poszedł trasą zwykłego pytania, nie ma
            # zgłoszenia wcale, a jako „obsłużony" nie wróciłby już nigdy.
            # Zgłoszenia usuniętego ręcznie nie odtwarzamy.
            if not to_formularz(mail.tresc) or mail.message_id in usuniete:
                continue
            zgl_id = zapisz_zgloszenie(Uczestnik(**pola), "formularz", mail.message_id)
        if pola:
            # Także dla zgłoszeń, które wyjazd już mają: nazwisko, telefon
            # i adres mogły zostać zapisane z podpisu biura. Zapis tych samych
            # wartości drugi raz niczego nie zmienia.
            uzupelnij_z_formularza(zgl_id, pola)
            if not ma_dane_wrazliwe(zgl_id):
                zapisz_dane_wrazliwe(
                    zgl_id, zloz_wrazliwe(ustal(mail.tresc), Uczestnik(**pola)))
        if mial_wyjazd:
            continue
        if przypisz_wyjazd(zgl_id, mail.temat,
                           pola.get("wyjazd_kierunek"), pola.get("wyjazd_termin")):
            naprawione += 1
        else:
            _zglos_brak_wyjazdu(pola.get("nazwisko"), pola.get("wyjazd_kierunek"))
    return naprawione


def _zglos_brak_wyjazdu(nazwisko: str | None, kierunek: str | None) -> None:
    """Jedno zdanie o zgłoszeniu, którego nie dało się przypisać do wyjazdu."""
    print(f"UWAGA: zgłoszenie bez wyjazdu — {nazwisko or 'bez nazwiska'}. "
          f"W formularzu: '{kierunek or 'brak'}'. "
          "Nie ma takiego wyjazdu w wyjazdy.yaml albo pasuje kilka.")


def _na_date(tekst: str | None) -> date | None:
    if not tekst:
        return None
    m = DATA_W_TEKSCIE.search(tekst)
    if m:
        d, mi, r = (int(x) for x in m.groups())
        try:
            return date(r, mi, d)
        except ValueError:
            return None
    m = DATA_ISO.search(tekst)
    if m:
        r, mi, d = (int(x) for x in m.groups())
        try:
            return date(r, mi, d)
        except ValueError:
            return None
    return None


def dopasuj_wyjazd(rezerwacja: Rezerwacja) -> str | None:
    """Przypisuje rezerwację do wyjazdu po zakresie dat z wyjazdy.yaml.

    Mail od wypożyczalni nie zawiera nazwy wyjazdu, ale zawiera daty. Jeśli
    zakresy nachodzą, to wystarczy. Przy braku dopasowania zostawiamy puste -
    przypiszesz ręcznie przez skrypty/zrob_liste.py --przypisz.
    """
    poczatek = _na_date(rezerwacja.data_od)
    if poczatek is None:
        return None
    try:
        wszystkie = wyjazdy()
    except RuntimeError:
        return None

    for klucz, dane in wszystkie.items():
        od = _na_date(str(dane.get("termin_od", "")))
        do = _na_date(str(dane.get("termin_do", ""))) or od
        if od is None:
            continue
        # tolerancja: rezerwacje robi się przed wyjazdem, nocleg może zaczynać
        # się dzień wcześniej, a samochód zwracać dzień później
        if (od - timedelta(days=2)) <= poczatek <= (do + timedelta(days=2)):
            return klucz
    return None


def wyciagnij_rezerwacje(mail: Mail) -> Rezerwacja:
    return chat_json(
        f"{prompt('rezerwacja')}\n\n### Temat\n{mail.temat}\n\n"
        f"### Treść maila\n{mail.skrot(4000)}",
        Rezerwacja,
        maly=False,   # tu opłaca się większy model: pól jest dużo i są drobne
        proby=2,
    )


def wyciagnij_dane_wrazliwe(mail: Mail) -> tuple[DaneWrazliwe, WynikDeterministyczny]:
    """Osobna ścieżka dla maili z PESEL-em i numerem dokumentu.

    Model widzi te dane, bo musi je przepisać do bazy, ale nic z nich
    nie idzie do logu, do bazy wiedzy ani do treści draftu.

    Ta funkcja długo miała dwie wady, które wyszły dopiero na prawdziwej
    poczcie. Pytała mały model 4.5B i **nie używała warstwy deterministycznej
    w ogóle** — czyli najwrażliwsze dane w całym systemie, te, z których
    powstaje umowa i zgłoszenie do ubezpieczyciela, zależały wyłącznie od
    najsłabszego modelu. Na dwudziestu prawdziwych zgłoszeniach dawało to
    `brakuje: data_urodzenia, pesel, numer_dokumentu` w szesnastu
    przypadkach, choć zwalidowany regex odczytał w tych samych
    wiadomościach 26 poprawnych numerów PESEL.

    Teraz jest tak jak w zwykłej ekstrakcji: zwalidowana cyfra bije cyfrę
    przepisaną przez model, a model dostaje informację, które pola są już
    przypisane, żeby nie wstawiał ich w inne miejsce.
    """
    wynik_det = ustal(mail.tresc)

    dane = chat_json(
        f"{prompt('dane_do_umowy')}\n\n{wynik_det.blok_dla_modelu()}\n\n"
        f"### Temat\n{mail.temat}\n\n"
        f"### Treść maila\n{mail.skrot(2500)}",
        DaneWrazliwe,
        maly=False,
    )

    # Nadpisanie deterministyczne — zawsze, też gdy model coś wpisał.
    for nazwa, wartosc in wynik_det.wartosci().items():
        if nazwa in DaneWrazliwe.model_fields:
            setattr(dane, nazwa, wartosc)

    if not dane.nazwisko and mail.od_nazwa:
        czesci = mail.od_nazwa.split()
        if len(czesci) >= 2:
            dane.imie, dane.nazwisko = czesci[0], czesci[-1]
    return dane, wynik_det


def _trasa_po_wzorcu(mail: Mail) -> tuple[TypMaila, str] | None:
    """Typ ustalony wzorcem, bez modelu. Nie rozstrzyga o fladze."""
    if FORMULA_AKCEPTACJI.search(mail.tresc[:600]):
        return (TypMaila.AKCEPTACJA_UMOWY,
                "Treść zawiera formułę akceptacji warunków umowy.")

    temat_formularza = cfg().get("poczta.temat_formularza", "")
    if temat_formularza and temat_formularza.lower() in mail.temat.lower():
        return (TypMaila.FORMULARZ,
                "Temat zgodny z szablonem formularza na stronie.")
    # Temat formularza zależy od ustawień strony i bywa zmieniany; układ
    # pól w treści jest stały. Bez tego zgłoszenie z innym tematem szło
    # trasą zwykłego pytania i nie trafiało do bazy wcale.
    if to_formularz(mail.tresc):
        return (TypMaila.FORMULARZ, "Treść ma układ pól formularza ze strony.")
    return None


def _czy_cytat_w_tresci(cytat: str, mail: Mail) -> bool:
    """Czy model przepisał fragment z wiadomości, czy go wymyślił.

    Porównanie po zwinięciu białych znaków i wielkości liter, bo model gubi
    łamania wiersza z formularza. Krótkie fragmenty odrzucamy z góry: „nie",
    „umowa" czy „rezygnacja" trafiłyby przypadkiem w niemal każdy tekst
    i potwierdzałyby cokolwiek.
    """
    def zwin(s: str) -> str:
        return " ".join(s.lower().split())

    igla = zwin(cytat)
    if len(igla) < 12:
        return False
    return igla in zwin(f"{mail.temat}\n{mail.tresc}")


def _ocen_flage(mail: Mail) -> OcenaFlagi:
    """Czy sprawa musi trafić do człowieka. Osobne wywołanie, osobny prompt.

    Dwa powody, oba zmierzone.

    Pierwszy: flaga nie może zależeć od tego, czy typ udało się ustalić wzorcem.
    Wcześniej zależała — dla maila z formularza funkcja klasyfikująca zwracała
    wynik bez pytania modelu, a `do_czlowieka` brało wartość domyślną `False`.
    Wszystkie zgłoszenia z prawdziwej skrzynki przychodzą z formularza, więc
    flaga nie zapaliła się na nich ani razu.

    Drugi: pytany o siedem pól naraz, model 7B flagę gubi. Przy wspólnym
    prompcie i wspólnym schemacie czułość wyniosła 1/20. Wąski schemat
    i prompt mówiący wyłącznie o liście zamkniętej warunków to ta sama
    lista i ten sam model — pytanie jest tylko jedno.
    """
    return chat_json(
        f"{prompt('flaga')}\n\n### Temat\n{mail.temat}\n\n"
        f"### Treść\n{zamaskuj(mail.skrot(1200))}",
        OcenaFlagi,
        maly=False,
    )


def zaklasyfikuj(mail: Mail) -> Klasyfikacja:
    # Warunki mechaniczne — zły kształt danych, data poza kalendarzem, PESEL
    # niezgodny z datą urodzenia. Nie przechodzą przez model i nie zależą
    # od tego, czy typ ustalił wzorzec czy model.
    wynik_det = ustal(mail.tresc)
    warunki_mech = warunki_deterministyczne(wynik_det)

    # Flaga zawsze osobnym wywołaniem, niezależnie od tego, jak ustalono typ.
    ocena = _ocen_flage(mail)

    wzorzec = _trasa_po_wzorcu(mail)
    if wzorzec is not None:
        typ, uzasadnienie = wzorzec
        klasyfikacja = Klasyfikacja(
            typ=typ,
            pewnosc=1.0,
            uzasadnienie=uzasadnienie,
            wymaga_odpowiedzi=True,
        )
    else:
        # do klasyfikacji wystarczy tekst zamaskowany - typ rozpoznaje się
        # po obecności znacznika [PESEL], nie po samym numerze
        klasyfikacja = chat_json(
            f"{prompt('klasyfikacja')}\n\n### Temat\n{mail.temat}\n\n"
            f"### Treść\n{zamaskuj(mail.skrot(1200))}",
            Klasyfikacja,
            maly=False,
        )

    # Wynik wąskiego wywołania wygrywa z tym, co model podał przy okazji
    # klasyfikacji typu — to ta sama lista warunków, ale zadana jako jedyne
    # pytanie, i tylko ta wersja jest mierzona.
    klasyfikacja.do_czlowieka = ocena.do_czlowieka
    klasyfikacja.powod_do_czlowieka = ocena.powod_do_czlowieka
    klasyfikacja.pytania_liczba = ocena.pytania_liczba

    # Czy cytat, którym model uzasadnił flagę, faktycznie jest w wiadomości.
    # Flagi NIE zdejmujemy, gdy go nie ma — koszt przeoczenia rezygnacji jest
    # wyższy niż koszt jednej minuty czytania. Ale oznaczamy ją, bo flaga bez
    # oparcia w treści to inna jakość informacji niż flaga z cytatem, i tylko
    # rozdzielenie tych dwóch rzeczy pozwala zmierzyć, ile jest których.
    if ocena.do_czlowieka and ocena.cytat:
        klasyfikacja.cytat_potwierdzony = _czy_cytat_w_tresci(ocena.cytat, mail)
        klasyfikacja.cytat = ocena.cytat
    elif ocena.do_czlowieka:
        klasyfikacja.cytat_potwierdzony = False

    # Warunek mechaniczny podnosi flagę niezależnie od tego, co powiedział
    # model. W drugą stronę nie działa: model może dodać warunek, którego
    # regex nie widzi, i tej flagi nie zdejmujemy.
    if warunki_mech and not klasyfikacja.do_czlowieka:
        klasyfikacja.do_czlowieka = True
        klasyfikacja.powod_do_czlowieka = warunki_mech[0]
    return klasyfikacja


# --- 4. draft odpowiedzi ---


def napisz_draft(mail: Mail, przyklady_stylu: list[str]) -> ProjektOdpowiedzi:
    # treść maila wchodzi do promptu TYLKO zamaskowana
    tresc_bezpieczna = oczysc_dla_promptu(mail.skrot())
    zapytanie = f"{mail.temat}\n{tresc_bezpieczna[:800]}"
    blok_kontekstu, zrodla = kontekst(zapytanie)
    blok_historii = historia.dla_adresu(mail.od).blok_dla_modelu()

    if not blok_kontekstu and cfg().get("bezpieczenstwo.tylko_z_bazy_wiedzy", True):
        return ProjektOdpowiedzi(
            temat=f"Re: {mail.temat}",
            tresc=(
                f"{cfg().get('bezpieczenstwo.fraza_niepewnosci')}\n\n"
                f"Pytanie klienta: {tresc_bezpieczna[:400]}"
            ),
            uzyte_zrodla=[],
            pewnosc=0.0,
            do_uzupelnienia=["Brak materiału w bazie wiedzy - odpowiedz ręcznie "
                             "albo uzupełnij folder wiedza/."],
        )

    blok_stylu = ""
    if przyklady_stylu:
        oddzielone = "\n\n~~~\n\n".join(przyklady_stylu)
        blok_stylu = (
            "\n\n### Przykłady moich dawnych odpowiedzi (naśladuj ton i układ, "
            "nie kopiuj treści)\n" + oddzielone
        )

    tresc_promptu = (
        f"{prompt('odpowiedz')}\n\n"
        f"### Dane firmy\n{cfg().opis_firmy()}\n\n"
        f"### Baza wiedzy (jedyne dopuszczalne źródło faktów)\n{blok_kontekstu}\n\n"
        f"{blok_historii}"
        f"{blok_stylu}\n\n"
        f"### Mail od klienta\nTemat: {mail.temat}\nOd: {mail.od_nazwa} <{mail.od}>\n\n{tresc_bezpieczna}"
    )

    # Projekt odpowiedzi to kilka akapitów tekstu w polu JSON, czyli rząd
    # wielkości więcej tokenów niż klasyfikacja czy wyciągnięcie PESEL-u.
    # Przy wspólnym limicie 1200 odpowiedź urywała się w połowie zdania
    # i cały przebieg kończył się zerem draftów.
    projekt = chat_json(
        tresc_promptu, ProjektOdpowiedzi, maly=False, proby=3,
        limit_tokenow=cfg().get("modele.limit_tokenow_draft", 2400),
    )
    if not projekt.uzyte_zrodla:
        projekt.uzyte_zrodla = zrodla
    return projekt


# --- przebieg ---


def wybierz_do_przetworzenia(
    maile: list[Mail],
    przetworzony,
    limit: int,
) -> tuple[list[Mail], int, int]:
    """Które wiadomości wchodzą do tego przebiegu.

    Zwraca (do przetworzenia, liczba pominiętych, liczba odłożonych).

    Dwie rzeczy, które muszą być spełnione naraz, a wcześniej nie były.

    Limit z konfiguracji dotyczy liczby wiadomości PRZETWARZANYCH, nie
    oglądanych. Wcześniej warstwa IMAP brała dwadzieścia najnowszych, a pętla
    pomijała już przetworzone — więc przy skrzynce z większą liczbą wiadomości
    w oknie każdy kolejny przebieg oglądał te same najnowsze, pomijał je
    wszystkie i do starszych nie docierał NIGDY. Pięćdziesiąt zgłoszeń po
    urlopie znaczyło trzydzieści nieobsłużonych, bez żadnego sygnału.

    Kolejność jest od najstarszych. Zaległości idą tak, jak przyszły, więc
    klient czekający najdłużej dostaje odpowiedź pierwszy. Warstwa IMAP
    zwraca najnowsze na końcu, stąd odwrócenie.
    """
    nieprzetworzone = []
    pominiete = 0
    for mail in maile:
        if przetworzony(mail):
            pominiete += 1
        else:
            nieprzetworzone.append(mail)

    nieprzetworzone.reverse()
    odlozone = 0
    if limit > 0 and len(nieprzetworzone) > limit:
        odlozone = len(nieprzetworzone) - limit
        nieprzetworzone = nieprzetworzone[:limit]
    return nieprzetworzone, pominiete, odlozone


@dataclass
class Wiersz:
    """Jedna wiadomość w podsumowaniu przebiegu."""

    od: str
    rodzaj: str
    temat: str
    wczesniej: bool          # obsłużona w którymś z wcześniejszych przebiegów
    do_czlowieka: bool = False
    draft: bool = False


@dataclass
class WynikPrzebiegu:
    liczby: dict[str, int]
    wiadomosci: list[Wiersz]


def przebieg(dni: int = 7, na_sucho: bool = False,
             ponownie: bool = False,
             szczegoly: bool = False) -> WynikPrzebiegu:
    """Jedno przejście po skrzynce. na_sucho=True nie zapisuje nic
    i nie tworzy draftów - przydatne przy kalibracji promptów.

    szczegoly=True wypisuje diagnostykę każdej wiadomości: co wyciągnął regex,
    co model, jakie pola odrzuciła walidacja. Domyślnie wyłączone, bo w
    codziennej pracy liczy się lista wiadomości i to, co z nich powstało,
    a nie przebieg rozumowania.

    ponownie=True ignoruje własną listę przetworzonych wiadomości. Potrzebne
    przy kalibracji promptu odpowiedzi: po każdej zmianie w `odpowiedz.md`
    chce się zobaczyć drafty dla TYCH SAMYCH wiadomości, a lista przetworzonych
    to blokuje. Flag na serwerze IMAP to nie dotyka tak samo jak zwykły
    przebieg — lista jest nasza, w bazie.

    Uwaga: z ponownie=True drafty powstają po raz drugi, więc w folderze
    wersji roboczych pojawią się duplikaty. Przy kalibracji to jest cena,
    którą się płaci; starą wersję usuwa się w Gmailu.
    """
    def opis(tekst: str) -> None:
        if szczegoly:
            print(tekst)

    wiersze: list[Wiersz] = []
    statystyki = {
        "w_skrzynce": 0,
        "w_oknie": 0,
        "pobrane": 0,
        "pominiete": 0,
        "zgloszenia": 0,
        "dane_do_umowy": 0,
        "akceptacje": 0,
        "rezerwacje": 0,
        "do_czlowieka": 0,
        "do_weryfikacji": 0,
        "drafty": 0,
        "bledy": 0,
        "przetworzone": 0,
        "odlozone": 0,
    }

    with Skrzynka() as skrzynka:
        przyklady = skrzynka.moje_dawne_odpowiedzi(cfg().get("poczta.styl_przyklady", 5))

        # Limit dotyczy liczby wiadomości PRZETWARZANYCH w jednym przebiegu,
        # nie liczby oglądanych. Wcześniej `nowe()` brało dwadzieścia
        # najnowszych, a pętla pomijała już przetworzone — więc przy skrzynce
        # z większą liczbą wiadomości w oknie każdy kolejny przebieg oglądał
        # te same najnowsze, pomijał je wszystkie i do starszych nie docierał
        # NIGDY. Pięćdziesiąt zgłoszeń po urlopie znaczyło trzydzieści
        # nieobsłużonych bez żadnego sygnału.
        limit = int(cfg().get("poczta.limit_na_przebieg", 20))
        wszystkie = skrzynka.nowe(dni=dni, limit=0)

        do_zrobienia, pominiete, odlozone = wybierz_do_przetworzenia(
            wszystkie,
            przetworzony=(lambda _m: False) if ponownie
            else (lambda m: czy_przetworzony(m.message_id)),
            limit=limit,
        )
        if odlozone:
            print(f"W oknie jest {len(do_zrobienia) + odlozone} nieprzetworzonych "
                  f"wiadomości, limit na przebieg to {limit}.")
            print(f"Przetwarzam {len(do_zrobienia)} najstarszych. Pozostałe "
                  f"{odlozone} wejdą w następnym przebiegu.")

        statystyki["w_skrzynce"] = skrzynka.liczba_w_skrzynce()
        statystyki["w_oknie"] = len(wszystkie)
        statystyki["pobrane"] = len(wszystkie)
        statystyki["pominiete"] = pominiete
        statystyki["przetworzone"] = len(do_zrobienia)
        statystyki["odlozone"] = odlozone

        # Wiadomości obsłużone wcześniej też trafiają na listę — z rodzajem
        # zapamiętanym przy tamtym przebiegu. Bez tego lista pokazywałaby
        # jedną nową wiadomość z dziewięciu i wyglądałoby to tak, jakby
        # program nie widział reszty skrzynki.
        do_zrobienia_id = {m.message_id for m in do_zrobienia}
        wczesniejsze = [m for m in wszystkie if m.message_id not in do_zrobienia_id]
        rodzaje = rodzaje_przetworzonych([m.message_id for m in wczesniejsze])
        for mail in wczesniejsze:
            wiersze.append(Wiersz(
                od=mail.od_nazwa or mail.od,
                rodzaj=rodzaje.get(mail.message_id, "czeka na kolejny przebieg"),
                temat=mail.temat,
                wczesniej=mail.message_id in rodzaje,
            ))

        if not na_sucho:
            uzupelnione = uzupelnij_wczesniejsze(wczesniejsze)
            if uzupelnione:
                print(f"Uzupełniono wyjazd przy wcześniejszych zgłoszeniach: "
                      f"{uzupelnione}.")

        for mail in do_zrobienia:
            try:
                klasyfikacja = zaklasyfikuj(mail)
                wiersz = Wiersz(
                    od=mail.od_nazwa or mail.od,
                    rodzaj=klasyfikacja.typ.value,
                    temat=mail.temat,
                    wczesniej=False,
                    do_czlowieka=bool(klasyfikacja.do_czlowieka),
                )
                wiersze.append(wiersz)
                # Jeden wiersz na żywo, żeby w panelu było widać postęp.
                # Pełna lista i tak pojawi się w podsumowaniu.
                print(f"  przetwarzam: {mail.temat[:62]}")
                hist = historia.dla_adresu(mail.od)
                if not hist.pusta():
                    opis(f"    historia: {hist.linia_do_konsoli()}")

                if klasyfikacja.typ is TypMaila.SPAM:
                    if not na_sucho:
                        oznacz_przetworzony(mail.message_id, klasyfikacja.typ.value, False)
                    continue

                if klasyfikacja.typ is TypMaila.FORMULARZ:
                    raport = wyciagnij_dane(mail)
                    uczestnik = raport.uczestnik
                    opis(f"    dane: {uczestnik.pelne_nazwisko()}")
                    opis(f"    {raport.podsumowanie()}")
                    if uczestnik.braki_krytyczne():
                        opis(f"    BRAKI KRYTYCZNE: {', '.join(uczestnik.braki_krytyczne())}")
                    if raport.odrzucone:
                        opis(f"    odrzucone przez walidację: {'; '.join(raport.odrzucone)}")
                    if not na_sucho:
                        zgl_id = zapisz_zgloszenie(
                            uczestnik, "formularz", mail.message_id
                        )
                        # Dane wrażliwe do osobnej tabeli, z własną retencją.
                        # Bez tego zwalidowany PESEL z formularza był
                        # wyrzucany i umowy nie dało się wystawić dla żadnego
                        # zgłoszenia przyszłego tą drogą.
                        if raport.wrazliwe is not None:
                            zapisz_dane_wrazliwe(zgl_id, raport.wrazliwe)
                        klucz_wyjazdu = przypisz_wyjazd(
                            zgl_id, mail.temat,
                            uczestnik.wyjazd_kierunek, uczestnik.wyjazd_termin,
                        )
                        opis(f"    wyjazd: {klucz_wyjazdu or 'NIE USTALONO — zapytam przy umowie'}")
                        if not klucz_wyjazdu:
                            _zglos_brak_wyjazdu(uczestnik.nazwisko, uczestnik.wyjazd_kierunek)
                    statystyki["zgloszenia"] += 1
                    if raport.do_weryfikacji:
                        statystyki["do_weryfikacji"] += 1

                elif klasyfikacja.typ is TypMaila.DANE_DO_UMOWY:
                    dane, det = wyciagnij_dane_wrazliwe(mail)
                    # Treść idzie do dopasowania, bo jedna osoba może mieć
                    # kilka zgłoszeń na różne wyjazdy i wtedy kierunek
                    # wymieniony w mailu rozstrzyga, o które chodzi.
                    dopasowanie = dopasuj_zgloszenie(
                        mail.od, dane.nazwisko, f"{mail.temat}\n{mail.tresc}"
                    )
                    zgl_id = dopasowanie.id
                    # świadomie NIE wypisujemy wartości, tylko co się udało wyciągnąć
                    wypelnione = [k for k, v in dane.model_dump().items() if v]
                    z_regexu = [p for p in det.pola() if p in DaneWrazliwe.model_fields]
                    opis(f"    dane do umowy: pola {wypelnione or 'brak'} "
                          f"| brakuje: {dane.braki_do_umowy() or 'nic'} "
                          f"| zgłoszenie: {zgl_id or 'NIE DOPASOWANO'}")
                    if dopasowanie.powod:
                        opis(f"      {dopasowanie.powod}")
                    if z_regexu:
                        opis(f"      zwalidowane regexem: {', '.join(sorted(z_regexu))}")
                    if det.do_weryfikacji:
                        opis(f"      DO WERYFIKACJI: {', '.join(det.do_weryfikacji)}")
                    if det.odrzucone:
                        opis(f"      odrzucone (zły kształt): {len(det.odrzucone)}")
                    if not na_sucho and zgl_id:
                        zapisz_dane_wrazliwe(zgl_id, dane)
                        ustaw_status(zgl_id, "dane_komplet" if not dane.braki_do_umowy() else "dane_czesciowe")
                    statystyki["dane_do_umowy"] += 1

                elif klasyfikacja.typ is TypMaila.REZERWACJA:
                    rez = wyciagnij_rezerwacje(mail)
                    klucz = dopasuj_wyjazd(rez)
                    opis(f"    rezerwacja: {rez.etykieta()} "
                          f"| {rez.data_od or '?'} - {rez.data_do or '?'} "
                          f"| wyjazd: {klucz or 'DO PRZYPISANIA'}")
                    if rez.kod_dostepu:
                        opis(f"    kod dostępu: {zamaskuj_kod(rez.kod_dostepu)} (zapisany w bazie)")
                    if rez.typ.value == "samochod" and rez.ubezpieczenie_wkladu is not True:
                        opis("    UWAGA: brak potwierdzenia ubezpieczenia wkładu własnego")
                    if rez.braki_krytyczne():
                        opis(f"    brakuje: {', '.join(rez.braki_krytyczne())}")
                    if not na_sucho:
                        zapisz_rezerwacje(rez, klucz, mail.message_id)
                    statystyki["rezerwacje"] += 1

                elif klasyfikacja.typ is TypMaila.AKCEPTACJA_UMOWY:
                    dopasowanie = dopasuj_zgloszenie(
                        mail.od, None, f"{mail.temat}\n{mail.tresc}"
                    )
                    zgl_id = dopasowanie.id
                    opis(f"    akceptacja umowy | zgłoszenie: {zgl_id or 'NIE DOPASOWANO'}")
                    if dopasowanie.powod:
                        opis(f"      {dopasowanie.powod}")
                    if not na_sucho and zgl_id:
                        ustaw_status(zgl_id, "umowa_zaakceptowana")
                    statystyki["akceptacje"] += 1

                if klasyfikacja.do_czlowieka:
                    # Flaga do człowieka wyłącza draft. Nie dlatego, że model nie
                    # umie napisać odpowiedzi - dlatego, że w tych sprawach wysłana
                    # obietnica jest nieodwracalna.
                    opis(f"    DO CZŁOWIEKA: {klasyfikacja.powod_do_czlowieka or 'bez podanego powodu'}")
                    if klasyfikacja.cytat_potwierdzony is False:
                        opis("      cytat NIEPOTWIERDZONY — model nie wskazał "
                              "fragmentu wiadomości; flaga zostaje, ale "
                              "prawdopodobnie jest zbędna")
                    elif klasyfikacja.cytat:
                        print(f'      cytat: "{klasyfikacja.cytat[:90]}"')
                    opis("    draft NIE został przygotowany (zamierzone)")
                    if not na_sucho:
                        oznacz_przetworzony(mail.message_id, klasyfikacja.typ.value, False)
                    statystyki["do_czlowieka"] += 1
                    continue

                draft_zrobiony = False
                if klasyfikacja.wolno_draftowac():
                    projekt = napisz_draft(mail, przyklady)
                    opis(f"    draft: pewność {projekt.pewnosc:.2f}, "
                          f"źródła: {', '.join(projekt.uzyte_zrodla) or 'brak'}")
                    if projekt.do_uzupelnienia:
                        opis(f"    do uzupełnienia: {'; '.join(projekt.do_uzupelnienia)}")
                    if not na_sucho:
                        # Podpis z konfiguracji, nie od modelu. Model nie zna
                        # imienia właścicielki i zostawiał w treści znacznik
                        # "[DO UZUPEŁNIENIA: imię]" w każdej odpowiedzi.
                        folder = skrzynka.wstaw_draft(
                            mail, projekt.temat, projekt.tresc,
                            podpis=cfg().get("poczta.podpis") or None,
                        )
                        opis(f"    zapisano w: {folder}")
                        draft_zrobiony = True
                        wiersz.draft = True
                        statystyki["drafty"] += 1

                if not na_sucho:
                    oznacz_przetworzony(mail.message_id, klasyfikacja.typ.value, draft_zrobiony)

            except Exception as e:  # jeden zły mail nie zatrzymuje przebiegu
                statystyki["bledy"] += 1
                # Błąd pokazujemy zawsze, także w trybie zwięzłym: wiadomość,
                # która się nie udała, jest tą jedną, o której trzeba wiedzieć.
                print(f"    BŁĄD przy: {mail.temat[:60]}")
                print(f"           {type(e).__name__}: {str(e)[:200]}")
                wiersze.append(Wiersz(
                    od=mail.od_nazwa or mail.od, rodzaj="błąd",
                    temat=mail.temat, wczesniej=False,
                ))

    return WynikPrzebiegu(liczby=statystyki, wiadomosci=wiersze)
