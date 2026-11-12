"""Warstwa deterministyczna: pola o sztywnym formacie bez udziału modelu.

Pomiar z 7 XI 2026: PESEL, telefon, e-mail i kod pocztowy wyciągnięte regexem
z walidacją dały 100% trafności. Sam regex na całym zgłoszeniu to 44,4% pól
krytycznych i 0% zgłoszeń bez poprawek, więc model wykonuje pracę nieredukowalną
— ale cyfry nie mają po co przez niego przechodzić.

Najważniejsza zasada tego pliku:

    zły KSZTAŁT usuwamy, złą SUMĘ KONTROLNĄ zostawiamy i flagujemy

Dziewięć cyfr w polu PESEL to pomyłka maszyny: numer telefonu wpadł w złą
rubrykę, bo była wolna. Takiej wartości nie chcemy nigdzie.
Jedenaście cyfr z błędną sumą kontrolną to literówka uczestnika. Taka wartość
zostaje, bo tylko człowiek może zadzwonić i dopytać.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

# PESEL: dokładnie 11 cyfr, dopuszczamy spacje i myślniki w zapisie
PESEL_KANDYDAT = re.compile(r"(?<!\d)(\d[\d\s-]{9,15}\d)(?!\d)")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]{2,}\b")
KOD_POCZTOWY = re.compile(r"(?<!\d)(\d{2})\s?-\s?(\d{3})(?!\d)")
# telefon polski: 9 cyfr, opcjonalny prefiks kraju, dowolne separatory
TELEFON = re.compile(
    r"(?:(?<!\w)(?:\+?\s?48|0048)[\s-]?)?(?<!\d)(\d{3})[\s-]?(\d{3})[\s-]?(\d{3})(?!\d)"
)

WAGI_PESEL = (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)

# Etykiety poprzedzające liczby. Przypisanie idzie po NAJBLIŻSZEJ etykiecie
# przed liczbą, nie po oknie znaków - okno powodowało, że numer telefonu
# w tym samym wierszu co słowo "PESEL" był odrzucany jako telefon.
ETYKIETY_LICZB = re.compile(
    r"\b(pesel|numer\s+telefonu|telefonu|telefon|tel|kom|mobile|"
    r"kod\s+pocztowy|nip|regon|konto|iban|nr\s+rach|paszport|dow[oó]d|"
    r"karta|faktur|data\s+urodzenia)\b\.?",
    re.IGNORECASE,
)

# wszystkie ciągi cyfr z dopuszczonymi separatorami wewnątrz
CIAG_CYFR = re.compile(r"(?<![\d])(\d[\d\s-]{0,18}\d|\d)(?![\d])")

ETYKIETY_TELEFONU = {"numer telefonu", "telefonu", "telefon", "tel", "kom", "mobile"}
ETYKIETY_OBCE = {
    "kod pocztowy", "nip", "regon", "konto", "iban", "nr rach",
    "paszport", "dowod", "dowód", "karta", "faktur", "data urodzenia",
}

# Okno jest wąskie świadomie. Przy 30 znakach w zdaniu "44000001357 to mój
# pesel, dzwońcie 601234567" słowo "pesel" przyklejało się do numeru telefonu,
# mimo że etykietuje liczbę stojącą PRZED nim. Etykieta opisuje liczbę tylko
# wtedy, gdy stoi bezpośrednio przy niej.
OKNO_ETYKIETY = 15


def _etykieta_przed(tekst: str, pozycja: int, okno: int = OKNO_ETYKIETY) -> str | None:
    """Najbliższa etykieta przed daną pozycją. Zwraca None, jeśli liczba
    stoi bez etykiety - wtedy przypisujemy ją po samym kształcie."""
    fragment = tekst[max(0, pozycja - okno): pozycja]
    trafienia = list(ETYKIETY_LICZB.finditer(fragment))
    if not trafienia:
        return None
    return re.sub(r"\s+", " ", trafienia[-1].group(1).lower())


def normalizuj_telefon(surowy: str) -> str:
    """Jednolity zapis numeru. Nie jest to wnioskowanie - to ten sam numer
    w jednym formacie, żeby umowa i lista uczestników nie miały czterech
    wariantów zapisu tego samego."""
    cyfry = tylko_cyfry(surowy)
    if len(cyfry) == 11 and cyfry.startswith("48"):
        cyfry = cyfry[2:]
        prefiks = "+48 "
    elif "+48" in surowy or surowy.strip().startswith("48 "):
        prefiks = "+48 "
    else:
        prefiks = ""
    if len(cyfry) != 9:
        return surowy.strip()
    return f"{prefiks}{cyfry[0:3]} {cyfry[3:6]} {cyfry[6:9]}"


def tylko_cyfry(tekst: str) -> str:
    return re.sub(r"\D", "", tekst)


def suma_kontrolna_pesel(pesel: str) -> bool:
    """Waga 1,3,7,9 powtórzona, cyfra kontrolna = (10 - suma mod 10) mod 10."""
    cyfry = tylko_cyfry(pesel)
    if len(cyfry) != 11:
        return False
    suma = sum(int(c) * w for c, w in zip(cyfry[:10], WAGI_PESEL))
    return (10 - suma % 10) % 10 == int(cyfry[10])


# Data urodzenia: etykieta plus zapis rok-miesiąc-dzień albo dzień.miesiąc.rok.
DATA_URODZENIA = re.compile(
    r"data\s+urodzenia\s*:?\s*"
    r"(?:(?P<r>\d{4})[-./](?P<m>\d{1,2})[-./](?P<d>\d{1,2})"
    r"|(?P<d2>\d{1,2})[-./](?P<m2>\d{1,2})[-./](?P<r2>\d{4}))",
    re.IGNORECASE,
)

# Miesiąc w PESEL-u koduje wiek: +20 to lata 2000, +40 lata 2100, +60 lata 2200,
# +80 lata 1800. Bez tej tabeli nie da się porównać daty z numerem.
WIEK_PO_MIESIACU = {0: 1900, 20: 2000, 40: 2100, 60: 2200, 80: 1800}


def data_istnieje(rok: int, miesiac: int, dzien: int) -> bool:
    """Czy taka data jest w kalendarzu. 2026-02-30 i 1978-04-33 nie są."""
    try:
        date(rok, miesiac, dzien)
    except ValueError:
        return False
    return True


def data_z_peselu(pesel: str) -> date | None:
    """Data urodzenia zakodowana w numerze albo None, gdy numer jej nie koduje.

    Numer może mieć poprawną sumę kontrolną i jednocześnie nieistniejącą datę —
    suma kontrolna liczy się z cyfr, nie z kalendarza.
    """
    cyfry = tylko_cyfry(pesel)
    if len(cyfry) != 11:
        return None
    rr, mm, dd = int(cyfry[0:2]), int(cyfry[2:4]), int(cyfry[4:6])
    przesuniecie = (mm // 20) * 20
    wiek = WIEK_PO_MIESIACU.get(przesuniecie)
    if wiek is None:
        return None
    try:
        return date(wiek + rr, mm - przesuniecie, dd)
    except ValueError:
        return None


@dataclass
class Ustalenie:
    """Jedno pole ustalone bez modelu."""

    pole: str
    wartosc: str
    zrodlo: str                      # "regex" albo "regex+etykieta"
    zweryfikowane: bool = True       # False = kształt ok, ale walidacja nie przeszła
    uwaga: str | None = None


@dataclass
class WynikDeterministyczny:
    ustalenia: dict[str, Ustalenie] = field(default_factory=dict)
    odrzucone: list[str] = field(default_factory=list)
    do_weryfikacji: list[str] = field(default_factory=list)

    def wartosci(self) -> dict[str, str]:
        return {nazwa: u.wartosc for nazwa, u in self.ustalenia.items()}

    def pola(self) -> set[str]:
        return set(self.ustalenia)

    def blok_dla_modelu(self) -> str:
        """Wartości ustalone, pokazywane modelowi z adnotacją.

        Bez tego bloku model w mailu bez PESEL-u wstawiał do pola PESEL numer
        telefonu, bo pole telefonu zostało zabrane ze schematu i była to jedyna
        wolna rubryka na numer. Pokazanie wartości usuwa ten mechanizm.
        """
        if not self.ustalenia:
            return ""
        linie = [
            "### Pola już przypisane (ustalone poza modelem)",
            "",
            "Te wartości są JUŻ wpisane do odpowiednich pól. Nie ma ich w schemacie,",
            "którego masz użyć. Podaję je wyłącznie do wiadomości, żebyś nie wstawił",
            "ich ponownie w inne pole. Każda z nich jest przypisana i zamknięta:",
            "",
        ]
        for nazwa, u in self.ustalenia.items():
            adnotacja = "" if u.zweryfikowane else "  (do weryfikacji przez człowieka)"
            linie.append(f"- {nazwa}: {u.wartosc}{adnotacja}")
        if self.odrzucone:
            linie += [
                "",
                "Następujących wartości NIE przypisano, bo miały zły format. "
                "Nie wstawiaj ich nigdzie:",
                "",
            ]
            linie += [f"- {x}" for x in self.odrzucone]
        return "\n".join(linie)


def _etykietowany(tekst: str, etykieta: str) -> str | None:
    """Szuka wartości po konkretnej etykiecie, np. 'PESEL: 44000001357'."""
    dopasowanie = re.search(
        rf"^\s*(?:{etykieta})\s*[:\-]\s*(?P<wartosc>.+?)\s*$",
        tekst, flags=re.IGNORECASE | re.MULTILINE,
    )
    return dopasowanie.group("wartosc").strip() if dopasowanie else None


def ustal(tekst: str, flaguj_bledna_sume: bool = True) -> WynikDeterministyczny:
    wynik = WynikDeterministyczny()
    if not tekst:
        return wynik

    # --- e-mail ---
    etykietowany = _etykietowany(tekst, r"(?:adres\s+)?e-?mail")
    znalezione_maile = EMAIL.findall(etykietowany or "") or EMAIL.findall(tekst)
    if znalezione_maile:
        wynik.ustalenia["email"] = Ustalenie(
            "email", znalezione_maile[0], "regex+etykieta" if etykietowany else "regex"
        )

    # --- kod pocztowy ---
    etykietowany = _etykietowany(tekst, r"kod\s+pocztowy")
    dopasowanie = KOD_POCZTOWY.search(etykietowany or tekst)
    if dopasowanie:
        wynik.ustalenia["kod_pocztowy"] = Ustalenie(
            "kod_pocztowy", f"{dopasowanie.group(1)}-{dopasowanie.group(2)}", "regex"
        )

    # --- liczby: jedno przejście, przypisanie po najbliższej etykiecie ---
    # Zbieramy wszystkie ciągi cyfr razem z ich etykietą, a potem rozdzielamy.
    # Dzięki temu "PESEL: 44000001356, tel 601234567" rozkłada się poprawnie
    # na oba pola, a nie odrzuca jednego z powodu bliskości drugiego.
    kandydaci_pesel: list[tuple[str, str | None]] = []
    kandydaci_telefon: list[tuple[str, str | None]] = []

    for dopasowanie in CIAG_CYFR.finditer(tekst):
        surowy = dopasowanie.group(1).strip()
        cyfry = tylko_cyfry(surowy)
        etykieta = _etykieta_przed(tekst, dopasowanie.start())

        if etykieta == "pesel":
            kandydaci_pesel.append((surowy, etykieta))
            continue
        if etykieta in ETYKIETY_TELEFONU:
            kandydaci_telefon.append((surowy, etykieta))
            continue
        if etykieta in ETYKIETY_OBCE:
            continue  # inna rubryka, nie nasza sprawa

        # bez etykiety: przypisujemy po kształcie
        znormalizowane = cyfry[2:] if len(cyfry) == 11 and cyfry.startswith("48") else cyfry
        if len(cyfry) == 11 and not cyfry.startswith("48"):
            kandydaci_pesel.append((surowy, None))
        elif len(znormalizowane) == 9:
            kandydaci_telefon.append((surowy, None))

    # telefon: pierwszy kandydat o poprawnej długości
    for surowy, _ in kandydaci_telefon:
        cyfry = tylko_cyfry(surowy)
        if len(cyfry) == 11 and cyfry.startswith("48"):
            cyfry = cyfry[2:]
        if len(cyfry) != 9:
            wynik.odrzucone.append(
                f"{surowy} (jako telefon: {len(cyfry)} cyfr, wymagane 9)"
            )
            continue
        wynik.ustalenia["telefon"] = Ustalenie(
            "telefon", normalizuj_telefon(surowy), "regex"
        )
        break

    # PESEL: etykietowane mają pierwszeństwo nad znalezionymi po kształcie
    kandydaci_pesel.sort(key=lambda para: para[1] is None)
    for surowy, etykieta in kandydaci_pesel:
        cyfry = tylko_cyfry(surowy)
        if len(cyfry) != 11:
            # zły KSZTAŁT - pomyłka maszyny, wartość nie trafia nigdzie
            wynik.odrzucone.append(
                f"{surowy} (jako PESEL: {len(cyfry)} cyfr, wymagane 11)"
            )
            continue
        if suma_kontrolna_pesel(cyfry):
            if data_z_peselu(cyfry) is None:
                # Suma kontrolna liczy się z cyfr, nie z kalendarza: numer
                # 780433... ma poprawną cyfrę kontrolną i koduje 33 kwietnia.
                # Kształt jest poprawny, więc wartość zostaje — ale nie jako
                # zweryfikowana, bo z taką datą nie wolno wystawić umowy.
                wynik.ustalenia["pesel"] = Ustalenie(
                    "pesel", cyfry, "regex", zweryfikowane=False,
                    uwaga="suma kontrolna poprawna, ale numer koduje datę, "
                          "której nie ma w kalendarzu",
                )
                wynik.do_weryfikacji.append("pesel")
            else:
                wynik.ustalenia["pesel"] = Ustalenie("pesel", cyfry, "regex")
        elif flaguj_bledna_sume:
            # zła SUMA KONTROLNA - literówka uczestnika, zostaje dla człowieka
            wynik.ustalenia["pesel"] = Ustalenie(
                "pesel", cyfry, "regex", zweryfikowane=False,
                uwaga="błędna suma kontrolna - prawdopodobna literówka, dopytaj uczestnika",
            )
            wynik.do_weryfikacji.append("pesel")
        else:
            wynik.odrzucone.append(f"{cyfry} (jako PESEL: błędna suma kontrolna)")
        break

    # --- data urodzenia: kalendarz, a potem zgodność z PESEL-em ---
    # Pierwsze prawdziwe zgłoszenie w skrzynce miało "Data urodzenia: 1978-04-33".
    # Sama suma kontrolna PESEL-u tego nie wyłapie, bo liczy się z cyfr, nie z dat.
    dopasowanie = DATA_URODZENIA.search(tekst)
    if dopasowanie:
        g = dopasowanie.groupdict()
        rok, miesiac, dzien = (
            (int(g["r"]), int(g["m"]), int(g["d"])) if g["r"]
            else (int(g["r2"]), int(g["m2"]), int(g["d2"]))
        )
        zapis = f"{rok:04d}-{miesiac:02d}-{dzien:02d}"
        if not data_istnieje(rok, miesiac, dzien):
            # zły KSZTAŁT: takiego dnia nie ma w kalendarzu, wartość nie trafia nigdzie
            wynik.odrzucone.append(f"{zapis} (jako data urodzenia: nie ma takiej daty)")
        else:
            podana = date(rok, miesiac, dzien)
            z_numeru = data_z_peselu(wynik.ustalenia["pesel"].wartosc) if "pesel" in wynik.ustalenia else None
            if z_numeru is not None and z_numeru != podana:
                # kształt obu wartości jest poprawny, ale przeczą sobie —
                # zostają w danych z adnotacją, decyzję podejmuje człowiek
                wynik.ustalenia["data_urodzenia"] = Ustalenie(
                    "data_urodzenia", podana.isoformat(), "regex",
                    zweryfikowane=False,
                    uwaga=f"data nie zgadza się z zakodowaną w PESEL-u ({z_numeru.isoformat()})",
                )
                wynik.do_weryfikacji.append("data_urodzenia")
            else:
                wynik.ustalenia["data_urodzenia"] = Ustalenie(
                    "data_urodzenia", podana.isoformat(), "regex"
                )

    return wynik


# Warunki flagi do człowieka, które da się stwierdzić bez modelu. Nazwy są
# z listy zamkniętej w prompty/klasyfikacja.md — ten sam słownik po obu stronach.
#
# Po co osobna funkcja. Flaga do człowieka była wyliczana wyłącznie przez model,
# a `zaklasyfikuj` dla maili z formularza w ogóle modelu nie pytała: trasa
# ustalana po temacie zwracała `do_czlowieka=False` z wartości domyślnej. Ponieważ
# wszystkie zgłoszenia w prawdziwej skrzynce przychodzą z formularza, flaga nie
# mogła się na nich zapalić nigdy — także przy dacie, której nie ma w kalendarzu.
# Warunki mechaniczne nie mogą zależeć od modelu ani od trasy.
def warunki_deterministyczne(wynik: WynikDeterministyczny) -> list[str]:
    # Oba przypadki to ten sam warunek: podana dana jest niemożliwa.
    # `do_weryfikacji` dostawało wcześniej `niezgodnosc_w_zgloszeniu`, co było
    # błędem — ten warunek znaczy „wiadomość sama sobie przeczy" (dwie osoby
    # i pokój jednoosobowy), a numer PESEL kodujący 33 kwietnia to zły kształt
    # danej, nie sprzeczność w treści. Sprzeczności treściowych warstwa
    # regexowa nie widzi i widzieć nie może; ocenia je model.
    if wynik.odrzucone or wynik.do_weryfikacji:
        return ["dane_zlego_ksztaltu"]
    return []
