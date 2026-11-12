"""Schematy danych. To one są kontraktem między modelem a resztą aplikacji."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import ClassVar

from pydantic import BaseModel, Field, field_validator


class TypMaila(str, Enum):
    FORMULARZ = "formularz"          # zgłoszenie z formularza na stronie
    ZAPYTANIE = "zapytanie"          # pytanie o ofertę, wolne miejsca, cenę
    DANE_DO_UMOWY = "dane_do_umowy"  # uczestnik odsyła dane: adres, data ur., PESEL, nr dokumentu
    AKCEPTACJA_UMOWY = "akceptacja"  # "Akceptuję Warunki Umowy"
    REZERWACJA = "rezerwacja"        # potwierdzenie od linii lotniczej, hotelu, wypożyczalni
    UCZESTNIK = "uczestnik"          # pytanie od osoby już zapisanej
    ORGANIZACYJNY = "organizacyjny"  # faktury, przelewy, niezgodności płatności
    # Dwa typy dołożone po przebiegu harnessu ewaluacyjnego na korpusie
    # 40 trudnych wiadomości. Bez nich rezygnacja i reklamacja wpadały jako
    # "uczestnik" i dostawały automatyczny draft - czyli dokładnie najdroższy
    # możliwy błąd tego systemu.
    SPRAWA_TRUDNA = "sprawa_trudna"  # rezygnacja, reklamacja, sprawa pilna, żądanie po wyjeździe, RODO
    BIZNES = "biznes"                # wycena grupowa, współpraca, media, barter
    SPAM = "spam"
    INNE = "inne"


# Typy, przy których aplikacja NIGDY nie przygotowuje draftu odpowiedzi.
# Nie dlatego, że model nie umie - dlatego, że w tych sprawach treść odpowiedzi
# jest decyzją handlową albo ma skutki prawne.
TYPY_BEZ_DRAFTU = frozenset({
    TypMaila.SPRAWA_TRUDNA,
    TypMaila.BIZNES,
    TypMaila.SPAM,
    TypMaila.REZERWACJA,
})


class OcenaFlagi(BaseModel):
    """Tylko flaga do człowieka, bez rozstrzygania typu.

    Osobny schemat, bo typ maila z formularza ustala wzorzec tematu i nie trzeba
    pytać o niego modelu — ale flagi nie wolno wtedy pominąć. Wcześniej była
    pomijana: funkcja klasyfikująca zwracała wynik bez wywołania modelu, więc
    `do_czlowieka` brało wartość domyślną `False` dla każdego zgłoszenia
    z formularza, czyli dla całego prawdziwego ruchu w skrzynce.

    Węższy schemat ma drugą zaletę: model odpowiada na jedno pytanie, a nie
    na cztery naraz, i na liście zamkniętej szesnastu warunków trafia lepiej.
    """

    do_czlowieka: bool = Field(
        description="Czy sprawa ma skutki prawne albo finansowe i musi trafić "
                    "do człowieka bez automatycznego projektu odpowiedzi.",
    )
    powod_do_czlowieka: str | None = Field(
        default=None,
        max_length=200,
        description="Który warunek z listy zamkniętej został spełniony. "
                    "Wypełnij tylko gdy do_czlowieka jest true.",
    )
    cytat: str | None = Field(
        default=None,
        max_length=160,
        description="Dosłowny fragment wiadomości, który spełnia ten warunek — "
                    "przepisany znak w znak, bez parafrazy i bez uzupełniania. "
                    "Wypełnij tylko gdy do_czlowieka jest true. Jeśli nie da "
                    "się wskazać takiego fragmentu, to warunek NIE jest "
                    "spełniony: ustaw do_czlowieka na false.",
    )
    pytania_liczba: int = Field(
        default=0,
        description="Ile odrębnych pytań albo prośb zawiera wiadomość. "
                    "Jeśli nie ma żadnego, wpisz 0.",
    )


class Klasyfikacja(BaseModel):
    # Dwa pola wypełniane przez aplikację, nie przez model: cytat, którym
    # model uzasadnił flagę, i informacja, czy ten cytat faktycznie znalazł
    # się w treści wiadomości. Flaga bez oparcia w treści to inna jakość
    # informacji niż flaga z cytatem — i tylko rozdzielenie ich pozwala
    # zmierzyć, ile jest których.
    cytat: str | None = None
    cytat_potwierdzony: bool | None = None

    typ: TypMaila
    pewnosc: float = Field(ge=0.0, le=1.0)
    uzasadnienie: str = Field(max_length=300)
    wymaga_odpowiedzi: bool

    # Metryka bezpieczeństwa tego systemu. Koszt błędu jest asymetryczny:
    # niewystawiona flaga to wysłana obietnica, której nie da się wycofać,
    # flaga nadmiarowa to minuta czytania. Dlatego warunki są listą zamkniętą
    # w prompcie, a nie opisem - przy modelu tej wielkości opis nie działa.
    do_czlowieka: bool = Field(
        default=False,
        description="Czy sprawa ma skutki prawne albo finansowe i musi trafić "
                    "do człowieka bez automatycznego projektu odpowiedzi.",
    )
    powod_do_czlowieka: str | None = Field(
        default=None,
        max_length=200,
        description="Który warunek z listy zamkniętej został spełniony. "
                    "Wypełnij tylko gdy do_czlowieka jest true.",
    )
    pytania_liczba: int = Field(
        default=0,
        description="Ile odrębnych pytań albo prośb zawiera wiadomość. "
                    "Jeśli nie ma żadnego, wpisz 0.",
    )

    def wolno_draftowac(self) -> bool:
        return (
            self.wymaga_odpowiedzi
            and not self.do_czlowieka
            and self.typ not in TYPY_BEZ_DRAFTU
        )


class TypDokumentu(str, Enum):
    PESEL = "pesel"
    PASZPORT = "paszport"
    DOWOD = "dowod_osobisty"
    INNY = "inny"


class Uczestnik(BaseModel):
    """Pola formularza na stronie plus to, co wyszło z pomiaru.

    Opisy pól nie są dokumentacją - model je czyta i wykonuje literalnie.
    Im mniejszy model, tym literalniej.

    Historia pola `liczba_osob` jest tu warta zapisania, bo wnioski z pierwszego
    pomiaru były błędne. Najpierw opis nie deklarował wartości domyślnej i 4.5B
    zwracał `null`, gdy liczba wynikała z milczenia — 16,7% trafności. Dopisanie
    zdania „przyjmij 1" dało 100% i wyglądało na rozwiązanie. Przy pomiarze
    halucynacji okazało się, że to pole odpowiada za 18 z 27 przypadków
    wypełnienia wbrew danym: model wpisywał 1 tam, gdzie zbiór odniesienia
    wymaga pustego, bo wiadomość o liczbie osób nie mówi nic.

    Oba pomiary były poprawne, tylko mierzyły różne rzeczy. Błąd był
    w umieszczeniu założenia: ekstrakcja ma mówić, co jest w wiadomości,
    a nie co firma zakłada w razie milczenia. Założenie „jedna osoba" jest
    sensowne i zostaje, ale w aplikacji — każdy odbiorca tego pola stosuje
    `or 1`, a w bazie zostaje `NULL`, żeby nie zgubić różnicy między liczbą
    podaną przez klienta a przyjętą przez nas.
    """

    imie: str | None = None
    nazwisko: str | None = None
    nazwa_firmy: str | None = Field(
        default=None, description="Tylko jeśli podana. Jeśli nie ma, zwróć null."
    )
    kraj_region: str | None = None
    ulica: str | None = Field(
        default=None, description="Nazwa ulicy z numerem domu i lokalu."
    )
    kod_pocztowy: str | None = None
    miasto: str | None = None
    telefon: str | None = None
    email: str | None = None

    # Czego dotyczy zgłoszenie. Pola dołożone po przebiegu harnessu: schemat
    # wyciągał KTO się zgłasza, ale nie CZEGO chce. Harness wypełniał kierunek
    # i termin w 22 miejscach na 40 wiadomościach, produkcja w żadnym.
    wyjazd_kierunek: str | None = Field(
        default=None,
        description="Kierunek albo nazwa wyjazdu, którego dotyczy wiadomość. "
                    "Wpisz tylko wtedy, gdy nadawca wskazuje, że chce jechać "
                    "właśnie tam. Samo wspomnienie miejsca nie wystarcza: "
                    "zdanie o zdjęciach z Islandii zrobionych przez ojca nie "
                    "znaczy, że nadawca wybiera Islandię. W razie wątpliwości null.",
    )
    wyjazd_termin: str | None = Field(
        default=None,
        description="Termin tak, jak go podał nadawca, nawet nieprecyzyjnie: "
                    "'luty 2027', 'druga połowa marca', 'dowolny zimowy'. "
                    "Nie przeliczaj na daty i nie uzupełniaj z kalendarza.",
    )
    wyjazd_data_od: str | None = Field(
        default=None,
        description="Data początku, tylko jeśli podana wprost. Nie wyciągaj jej "
                    "z nazwy wyjazdu ani z daty urodzenia.",
    )
    wyjazd_data_do: str | None = Field(
        default=None, description="Data końca, tylko jeśli podana wprost."
    )
    budzet: str | None = Field(
        default=None,
        description="Budżet albo kwota, którą nadawca podaje jako swoją granicę. "
                    "Nie wpisuj tu ceny wyjazdu ani kwoty wpłaty.",
    )
    nip: str | None = Field(
        default=None,
        description="NIP do faktury, jeśli nadawca go podaje. Jeśli nadawca PROSI "
                    "o nasz NIP, zostaw null - to nie jest jego numer.",
    )

    liczba_osob: int | None = Field(
        default=None,
        description="Ile osób zgłasza się razem z tą wiadomością. Wypełnij "
                    "tylko wtedy, gdy wiadomość podaje liczbę albo wymienia "
                    "osoby. Jeśli nie mówi o tym nic, zwróć null — nie "
                    "zakładaj jednej osoby.",
    )
    dodatkowe_informacje: str | None = Field(
        default=None,
        description="Uwagi, pytania i wymagania DOTYCZĄCE OSOBY ZGŁASZAJĄCEJ: "
                    "dieta, sprzęt, doświadczenie, preferencje. Maksymalnie trzy zdania.",
    )
    wymagania_innych_osob: str | None = Field(
        default=None,
        description="Wymagania osób innych niż zgłaszający, jeśli zgłoszenie obejmuje "
                    "więcej niż jedną osobę - np. dieta współuczestnika. "
                    "Jeśli zgłoszenie dotyczy jednej osoby, zwróć null.",
    )

    # Uczestnicy zagraniczni (Walia, Arktyka) nie mają PESEL-u, a paszport nie ma
    # sumy kontrolnej, więc warstwa deterministyczna go nie zweryfikuje.
    # Bez tych dwóch pól zagraniczne zgłoszenia wpadały w tryb "brak danych"
    # albo model wstawiał numer paszportu do pola PESEL.
    typ_dokumentu: TypDokumentu | None = Field(
        default=None,
        description="Rodzaj dokumentu tożsamości, jeśli wiadomość go wskazuje. "
                    "Nie zgaduj na podstawie kraju ani nazwiska.",
    )
    numer_dokumentu: str | None = Field(
        default=None,
        description="Numer paszportu albo dowodu, jeśli podany. "
                    "NIE wpisuj tu numeru PESEL.",
    )

    # pola wyłącznie informacyjne, wypełniane przez warstwę deterministyczną
    pesel: str | None = Field(
        default=None,
        description="Numer PESEL. Ustala go walidator poza modelem - "
                    "jeśli widzisz to pole w schemacie, zostaw null.",
    )

    POLA_OPCJONALNE: ClassVar[tuple[str, ...]] = (
        "nazwa_firmy", "dodatkowe_informacje", "wymagania_innych_osob",
        "typ_dokumentu", "numer_dokumentu", "pesel", "liczba_osob",
        "wyjazd_kierunek", "wyjazd_termin", "wyjazd_data_od", "wyjazd_data_do",
        "budzet", "nip",
    )

    def braki(self) -> list[str]:
        """Pola obowiązkowe, których nie udało się wyciągnąć."""
        return [
            nazwa
            for nazwa, wartosc in self.model_dump().items()
            if nazwa not in self.POLA_OPCJONALNE and not wartosc
        ]

    def braki_krytyczne(self) -> list[str]:
        """Bez tych pól nie da się odpisać ani przygotować umowy.
        To one są mierzone w harnessie ewaluacyjnym."""
        return [
            p for p in ("imie", "nazwisko", "email", "telefon")
            if not getattr(self, p)
        ]

    def pelne_nazwisko(self) -> str:
        return " ".join(x for x in (self.imie, self.nazwisko) if x) or "nieznany"


class DaneWrazliwe(BaseModel):
    """Dane, które uczestnik odsyła mailem do umowy i polisy.

    OSTRZEŻENIE DLA KAŻDEGO, KTO TU DOPISUJE KOD:
    te pola nigdy nie trafiają do bazy wiedzy, do promptu pisania odpowiedzi,
    do treści draftu ani do konsoli. Są potrzebne wyłącznie do wypełnienia
    umowy i zgłoszenia do ubezpieczyciela. Do logowania używaj
    biuro.pii.zamaskuj().
    """

    # Opisy i ograniczenia długości nie są kosmetyką. Bez nich model dopisywał
    # w pole własny komentarz („brak w mailu, więc null", „zasada 1") i łańcuch
    # rósł, aż JSON urywał się w połowie — dwie wiadomości na dwadzieścia
    # padały z BladModelu po trzech próbach. Ograniczenie długości zamyka tę
    # drogę na poziomie dekodowania, nie prośbą w prompcie.
    data_urodzenia: str | None = Field(
        default=None, max_length=10,
        description="Data urodzenia dokładnie w formacie RRRR-MM-DD. "
                    "Jeśli w wiadomości jej nie ma, zwróć null.",
    )
    pesel: str | None = Field(
        default=None, max_length=11,
        description="Numer PESEL, 11 cyfr bez spacji. Jeśli go nie ma, null.",
    )
    numer_dokumentu: str | None = Field(
        default=None, max_length=40,
        description="Numer dowodu osobistego albo paszportu — SAM NUMER. "
                    "Bez daty ważności, bez słowa 'paszport' ani 'dowód', "
                    "bez przecinków i dopisków. Z 'paszport ES 7742019, "
                    "ważny do 28.03.2029' bierzesz 'ES 7742019'. "
                    "Nie wpisuj tu numeru PESEL. Jeśli go nie ma, null.",
    )
    # adres z maila bywa inny niż ten ze zgłoszenia - umowa wymaga aktualnego
    ulica: str | None = Field(
        default=None, max_length=120,
        description="Ulica z numerem domu i lokalu, bez kodu i miasta.",
    )
    kod_pocztowy: str | None = Field(
        default=None, max_length=6,
        description="Kod pocztowy w formacie 00-000.",
    )
    miasto: str | None = Field(default=None, max_length=80)
    imie: str | None = Field(default=None, max_length=60)
    nazwisko: str | None = Field(default=None, max_length=60)

    @field_validator("numer_dokumentu", mode="before")
    @classmethod
    def _sam_numer(cls, v):
        """Obcina to, co model dopisuje do numeru dokumentu.

        Formularz podaje numer razem z datą ważności w jednej linii
        ("paszport ES 7742019, ważny do 28.03.2029") i model przepisuje
        całość. Przy limicie długości pola walidacja odrzucała wtedy cały
        rekord — poprawny numer, który jest w środku, szedł do kosza razem
        z dopiskiem. Opis pola mówi modelowi, czego nie dopisywać; to jest
        druga linia obrony, bo opis w prompcie nie jest gwarancją.
        """
        if not isinstance(v, str):
            return v
        tekst = v.strip()
        for separator in (",", ";", " ważny", " wazny", " ważne", " do "):
            pozycja = tekst.lower().find(separator.lower())
            if pozycja > 0:
                tekst = tekst[:pozycja].strip()
        # przedrostki w rodzaju "paszport ES 7742019" albo "dowód ABC12345"
        for przedrostek in ("paszport", "dowód osobisty", "dowod osobisty",
                            "dowód", "dowod"):
            if tekst.lower().startswith(przedrostek):
                tekst = tekst[len(przedrostek):].strip(" :-")
        return tekst or None

    def braki_do_umowy(self) -> list[str]:
        wymagane = ("data_urodzenia", "pesel", "numer_dokumentu")
        return [p for p in wymagane if not getattr(self, p)]


class ProjektOdpowiedzi(BaseModel):
    temat: str
    tresc: str
    uzyte_zrodla: list[str] = Field(default_factory=list)
    pewnosc: float = Field(ge=0.0, le=1.0)
    do_uzupelnienia: list[str] = Field(
        default_factory=list,
        description="Rzeczy, których nie było w bazie wiedzy i wymagają ręcznego dopisania",
    )


class TypRezerwacji(str, Enum):
    LOT = "lot"
    NOCLEG = "nocleg"
    SAMOCHOD = "samochod"
    UBEZPIECZENIE = "ubezpieczenie"   # np. ubezpieczenie wkładu własnego do auta
    INNE = "inne"


class Rezerwacja(BaseModel):
    """Jedna rezerwacja wyciągnięta z maila potwierdzającego.

    Jeden schemat na wszystkie typy, z polami opcjonalnymi. Dla modelu jest to
    łatwiejsze niż wybór między trzema schematami, a w arkuszu i tak lądują
    w osobnych sekcjach.
    """

    typ: TypRezerwacji
    dostawca: str | None = Field(
        default=None, description="linia lotnicza, nazwa obiektu, wypożyczalnia"
    )
    numer_rezerwacji: str | None = None
    data_od: str | None = None
    data_do: str | None = None

    # lot
    numery_lotow: list[str] = Field(default_factory=list)
    trasa: str | None = Field(default=None, description="np. KTW - MAN")
    godziny: str | None = Field(default=None, description="odlot i przylot")
    bagaz: str | None = None

    # nocleg
    adres: str | None = None
    kod_dostepu: str | None = Field(
        default=None, description="kod do skrytki na klucze, kod do drzwi, kod do bramy"
    )
    zameldowanie: str | None = Field(
        default=None, description="godziny i instrukcje zameldowania oraz wymeldowania"
    )
    kontakt: str | None = Field(default=None, description="telefon lub mail do gospodarza")

    # samochód
    pojazd: str | None = Field(default=None, description="klasa albo model pojazdu")
    miejsce_odbioru: str | None = None
    miejsce_zwrotu: str | None = None
    wklad_wlasny: str | None = Field(
        default=None, description="kwota udziału własnego / kaucji"
    )
    ubezpieczenie_wkladu: bool | None = Field(
        default=None,
        description="czy ubezpieczenie wkładu własnego jest wykupione; "
                    "zwykle kupowane osobno, poza wypożyczalnią",
    )

    # wspólne
    kwota: str | None = None
    waluta: str | None = None
    oplacone: bool | None = None
    uwagi: str | None = Field(
        default=None, description="istotne warunki: anulowanie, limit km, paliwo, depozyt"
    )

    def etykieta(self) -> str:
        czesci = [self.typ.value, self.dostawca or "", self.numer_rezerwacji or ""]
        return " / ".join(c for c in czesci if c)

    def braki_krytyczne(self) -> list[str]:
        """Pola, bez których rezerwacja jest bezużyteczna na wyjeździe."""
        if self.typ is TypRezerwacji.NOCLEG:
            return [p for p in ("adres", "data_od", "zameldowanie") if not getattr(self, p)]
        if self.typ is TypRezerwacji.LOT:
            braki = [p for p in ("trasa", "godziny") if not getattr(self, p)]
            if not self.numery_lotow:
                braki.append("numery_lotow")
            return braki
        if self.typ is TypRezerwacji.SAMOCHOD:
            return [
                p for p in ("dostawca", "miejsce_odbioru", "data_od") if not getattr(self, p)
            ]
        return []


class NotatkaRozmowy(BaseModel):
    osoba: str
    data: date | None = None
    pytania_klienta: list[str] = Field(default_factory=list)
    potrzeby: list[str] = Field(default_factory=list)
    ustalenia: list[str] = Field(default_factory=list)
    kolejny_krok: str | None = None
    podsumowanie: str


class PozycjaKompletnosci(BaseModel):
    wymog: str
    spelniony: bool
    komentarz: str = Field(max_length=400)


class RaportKompletnosci(BaseModel):
    """Walidacja kompletności dokumentu wobec checklisty.
    To NIE jest opinia prawna - to sprawdzenie listy pól."""

    dokument: str
    pozycje: list[PozycjaKompletnosci]

    def braki(self) -> list[PozycjaKompletnosci]:
        return [p for p in self.pozycje if not p.spelniony]
