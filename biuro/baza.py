"""SQLite jako źródło prawdy. Z tej bazy lecą umowy, rejestr i CSV do UFG.

Arkusze Google zostają jako lustro do podglądu, ale nie są już źródłem.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime
from typing import Iterator

from .config import cfg
from .schemas import DaneWrazliwe, Rezerwacja, Uczestnik  # noqa: F401  (w adnotacjach)

SCHEMAT = """
CREATE TABLE IF NOT EXISTS zgloszenia (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    utworzono       TEXT NOT NULL,
    zrodlo          TEXT NOT NULL,          -- formularz | mail | telefon | dyktowanie | reczne
    message_id      TEXT,                   -- id maila, jeśli ze skrzynki
    imie            TEXT,
    nazwisko        TEXT,
    nazwa_firmy     TEXT,
    kraj_region     TEXT,
    ulica           TEXT,
    kod_pocztowy    TEXT,
    miasto          TEXT,
    telefon         TEXT,
    email           TEXT,
    dodatkowe       TEXT,
    wymagania_innych TEXT,                  -- wymagania osób innych niż zgłaszający
    liczba_osob     INTEGER DEFAULT 1,
    -- czego dotyczy zgłoszenie (dołożone po przebiegu harnessu)
    wyjazd_kierunek TEXT,
    wyjazd_termin   TEXT,                   -- termin tak, jak podał nadawca
    wyjazd_data_od  TEXT,
    wyjazd_data_do  TEXT,
    budzet          TEXT,
    nip             TEXT,                   -- NIP nabywcy do faktury
    typ_dokumentu   TEXT,                   -- pesel | paszport | dowod_osobisty | inny
    numer_dokumentu TEXT,                   -- paszport uczestnika zagranicznego
    braki           TEXT,                   -- JSON: lista brakujących pól
    status          TEXT NOT NULL DEFAULT 'nowe'  -- nowe | umowa | oplacone | anulowane
);

CREATE TABLE IF NOT EXISTS umowy (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    zgloszenie_id   INTEGER NOT NULL REFERENCES zgloszenia(id),
    numer           TEXT NOT NULL UNIQUE,
    data_zawarcia   TEXT NOT NULL,
    wyjazd          TEXT,
    data_wyjazdu    TEXT,
    kwota           REAL,
    plik_docx       TEXT,
    plik_pdf        TEXT,
    zgloszone_ufg   INTEGER NOT NULL DEFAULT 0
);

-- Dane wrażliwe w osobnej tabeli, nie jako kolumny zgłoszenia. Dzięki temu
-- da się je usunąć po wyjeździe jednym DELETE, bez ruszania rejestru umów,
-- który trzeba trzymać dla UFG.
CREATE TABLE IF NOT EXISTS dane_wrazliwe (
    zgloszenie_id   INTEGER PRIMARY KEY REFERENCES zgloszenia(id),
    zapisano        TEXT NOT NULL,
    data_urodzenia  TEXT,
    pesel           TEXT,
    numer_dokumentu TEXT,
    ulica           TEXT,
    kod_pocztowy    TEXT,
    miasto          TEXT,
    usunac_po       TEXT          -- data, po której te dane mają zniknąć
);

CREATE TABLE IF NOT EXISTS maile_przetworzone (
    message_id      TEXT PRIMARY KEY,
    przetworzono    TEXT NOT NULL,
    typ             TEXT,
    draft_utworzony INTEGER NOT NULL DEFAULT 0
);

-- Rezerwacje należą do wyjazdu, nie do uczestnika. Wyjątek: lot albo transfer
-- kupiony dla jednej osoby - wtedy wypełnione jest zgloszenie_id.
CREATE TABLE IF NOT EXISTS rezerwacje (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    utworzono           TEXT NOT NULL,
    wyjazd              TEXT,                   -- klucz z wyjazdy.yaml
    zgloszenie_id       INTEGER REFERENCES zgloszenia(id),
    message_id          TEXT,
    typ                 TEXT NOT NULL,          -- lot | nocleg | samochod | ubezpieczenie | inne
    dostawca            TEXT,
    numer_rezerwacji    TEXT,
    data_od             TEXT,
    data_do             TEXT,
    dane                TEXT NOT NULL,          -- JSON: pełna Rezerwacja
    braki               TEXT                    -- JSON: lista pól krytycznych, których brak
);

CREATE INDEX IF NOT EXISTS idx_rezerwacje_wyjazd ON rezerwacje(wyjazd, typ);

CREATE TABLE IF NOT EXISTS rozmowy (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    utworzono       TEXT NOT NULL,
    osoba           TEXT NOT NULL,
    plik_audio      TEXT,
    transkrypcja    TEXT,
    notatka         TEXT,                   -- JSON: NotatkaRozmowy
    zgloszenie_id   INTEGER REFERENCES zgloszenia(id)
);

CREATE INDEX IF NOT EXISTS idx_zgloszenia_nazwisko ON zgloszenia(nazwisko);
CREATE INDEX IF NOT EXISTS idx_rozmowy_osoba ON rozmowy(osoba);
"""


@contextmanager
def polaczenie() -> Iterator[sqlite3.Connection]:
    sciezka = cfg().sciezka("baza")
    conn = sqlite3.connect(sciezka)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# Kolumny dołożone po pierwszym wdrożeniu. CREATE TABLE IF NOT EXISTS nie
# dodaje kolumn do istniejącej tabeli, więc bazy z wcześniejszych przebiegów
# trzeba dociągnąć ALTER-em. Lista jest dopisywana, nigdy nie skracana.
MIGRACJE: tuple[tuple[str, str, str], ...] = (
    ("zgloszenia", "wymagania_innych", "TEXT"),
    ("zgloszenia", "liczba_osob", "INTEGER DEFAULT 1"),
    ("zgloszenia", "typ_dokumentu", "TEXT"),
    ("zgloszenia", "numer_dokumentu", "TEXT"),
    ("zgloszenia", "wyjazd_kierunek", "TEXT"),
    ("zgloszenia", "wyjazd_termin", "TEXT"),
    ("zgloszenia", "wyjazd_data_od", "TEXT"),
    ("zgloszenia", "wyjazd_data_do", "TEXT"),
    ("zgloszenia", "budzet", "TEXT"),
    ("zgloszenia", "nip", "TEXT"),
    # klucz wyjazdu z wyjazdy.yaml, ustalany przy wpływie zgłoszenia
    ("zgloszenia", "wyjazd_klucz", "TEXT"),
)


def inicjuj() -> None:
    with polaczenie() as conn:
        conn.executescript(SCHEMAT)
        for tabela, kolumna, typ in MIGRACJE:
            istniejace = {
                w[1] for w in conn.execute(f"PRAGMA table_info({tabela})")
            }
            if kolumna not in istniejace:
                conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {kolumna} {typ}")


def zapisz_zgloszenie(
    uczestnik: Uczestnik, zrodlo: str, message_id: str | None = None
) -> int:
    """Zapisuje zgłoszenie i zwraca jego id.

    Jeśli zgłoszenie z tego samego maila już jest w bazie, nadpisuje je
    zamiast dokładać drugi wiersz. Powtórny przebieg po tej samej skrzynce
    — przy kalibracji promptu albo po błędzie — wstawiał wcześniej drugi
    zestaw tych samych osób: trzydzieści dwa wiersze dla szesnastu zgłoszeń.
    Przy wystawianiu umowy nie dałoby się powiedzieć, który wiersz jest ten
    właściwy.
    """
    if message_id:
        with polaczenie() as conn:
            istniejace = conn.execute(
                "SELECT id FROM zgloszenia WHERE message_id = ?", (message_id,)
            ).fetchone()
        if istniejace:
            zid = int(istniejace[0])
            _nadpisz_zgloszenie(zid, uczestnik)
            return zid
    with polaczenie() as conn:
        kursor = conn.execute(
            """INSERT INTO zgloszenia
               (utworzono, zrodlo, message_id, imie, nazwisko, nazwa_firmy,
                kraj_region, ulica, kod_pocztowy, miasto, telefon, email,
                dodatkowe, wymagania_innych, liczba_osob, typ_dokumentu,
                numer_dokumentu, wyjazd_kierunek, wyjazd_termin, wyjazd_data_od,
                wyjazd_data_do, budzet, nip, braki)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                datetime.now().isoformat(timespec="seconds"),
                zrodlo,
                message_id,
                uczestnik.imie,
                uczestnik.nazwisko,
                uczestnik.nazwa_firmy,
                uczestnik.kraj_region,
                uczestnik.ulica,
                uczestnik.kod_pocztowy,
                uczestnik.miasto,
                uczestnik.telefon,
                uczestnik.email,
                uczestnik.dodatkowe_informacje,
                uczestnik.wymagania_innych_osob,
                # NULL, gdy klient nic nie napisał o liczbie osób. Odbiorcy
                # tego pola stosują `or 1`; w bazie zostaje ślad, że to nasze
                # założenie, a nie liczba podana w zgłoszeniu.
                uczestnik.liczba_osob,
                uczestnik.typ_dokumentu.value if uczestnik.typ_dokumentu else None,
                uczestnik.numer_dokumentu,
                uczestnik.wyjazd_kierunek,
                uczestnik.wyjazd_termin,
                uczestnik.wyjazd_data_od,
                uczestnik.wyjazd_data_do,
                uczestnik.budzet,
                uczestnik.nip,
                json.dumps(uczestnik.braki(), ensure_ascii=False),
            ),
        )
        return int(kursor.lastrowid)


@dataclass
class Dopasowanie:
    """Wynik szukania zgłoszenia, do którego należy przychodzący mail."""

    id: int | None = None
    kandydaci: list[tuple[int, str]] = dataclass_field(default_factory=list)
    powod: str = ""

    def __bool__(self) -> bool:
        return self.id is not None


def dopasuj_zgloszenie(
    email: str | None, nazwisko: str | None, tekst: str | None = None
) -> Dopasowanie:
    """Szuka zgłoszenia, do którego należy mail z danymi albo akceptacją.

    Najpierw po adresie, bo jest pewniejszy, potem po nazwisku.

    Jedna osoba może zgłosić się na kilka wyjazdów i każdy taki wyjazd jest
    osobnym zgłoszeniem i osobną umową. Ta funkcja brała wcześniej
    NAJNOWSZE zgłoszenie z danego adresu — czyli uczestnik, który zapisał się
    na Lofoty i na Svalbard, a potem dosłał PESEL do umowy na Lofoty,
    wpisywał go do zgłoszenia na Svalbard. Zapis danych wrażliwych działa
    przez INSERT OR REPLACE, więc przy kolejnym mailu dane podmieniłyby się
    po cichu: jedna umowa bez numeru, druga z numerem przysłanym w innej
    sprawie.

    Gdy kandydatów jest więcej niż jeden, próbujemy rozstrzygnąć po kierunku
    wymienionym w treści maila. Jeśli to nie wystarcza, **nie zgadujemy** —
    zwracamy brak dopasowania z listą kandydatów, a sprawa idzie do człowieka.
    Dopisanie PESEL-u do niewłaściwej umowy jest gorsze niż zgłoszenie bez
    dopasowania.
    """
    with polaczenie() as conn:
        kandydaci: list[tuple[int, str]] = []
        if email:
            kandydaci = [
                (int(r["id"]), r["wyjazd_kierunek"] or "")
                for r in conn.execute(
                    "SELECT id, wyjazd_kierunek FROM zgloszenia "
                    "WHERE lower(email) = lower(?) ORDER BY id",
                    (email,),
                )
            ]
        if not kandydaci and nazwisko:
            kandydaci = [
                (int(r["id"]), r["wyjazd_kierunek"] or "")
                for r in conn.execute(
                    "SELECT id, wyjazd_kierunek FROM zgloszenia "
                    "WHERE lower(nazwisko) = lower(?) ORDER BY id",
                    (nazwisko,),
                )
            ]

    if not kandydaci:
        return Dopasowanie()
    if len(kandydaci) == 1:
        return Dopasowanie(id=kandydaci[0][0], kandydaci=kandydaci)

    # Kilku kandydatów: rozstrzygamy po kierunku wymienionym w treści.
    if tekst:
        nisko = tekst.lower()
        trafione = [
            (zid, kier) for zid, kier in kandydaci
            if kier and kier.lower() in nisko
        ]
        if len(trafione) == 1:
            return Dopasowanie(
                id=trafione[0][0], kandydaci=kandydaci,
                powod=f"rozstrzygnięte po kierunku '{trafione[0][1]}'",
            )

    opis = ", ".join(f"[{zid}] {kier or 'bez kierunku'}" for zid, kier in kandydaci)
    return Dopasowanie(
        kandydaci=kandydaci,
        powod=f"kilka zgłoszeń tej osoby i treść nie wskazuje, o które chodzi: {opis}",
    )


def zapisz_dane_wrazliwe(zgloszenie_id: int, dane: "DaneWrazliwe", usunac_po: str | None = None) -> None:
    """Zapis do osobnej tabeli. Nic z tych pól nie trafia do logów ani do promptów."""
    with polaczenie() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO dane_wrazliwe
               (zgloszenie_id, zapisano, data_urodzenia, pesel, numer_dokumentu,
                ulica, kod_pocztowy, miasto, usunac_po)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                zgloszenie_id,
                datetime.now().isoformat(timespec="seconds"),
                dane.data_urodzenia,
                dane.pesel,
                dane.numer_dokumentu,
                dane.ulica,
                dane.kod_pocztowy,
                dane.miasto,
                usunac_po,
            ),
        )


def _nadpisz_zgloszenie(zgloszenie_id: int, uczestnik: Uczestnik) -> None:
    """Aktualizuje istniejące zgłoszenie danymi z nowego przebiegu.

    Nie dotyka kolumn `status` ani `utworzono`: status mógł zostać zmieniony
    ręcznie po pierwszym przebiegu, a data utworzenia to data pierwszego
    wpływu zgłoszenia i nie zmienia jej powtórne przetworzenie maila.
    """
    with polaczenie() as conn:
        conn.execute(
            """UPDATE zgloszenia SET
                 imie = ?, nazwisko = ?, nazwa_firmy = ?, kraj_region = ?,
                 ulica = ?, kod_pocztowy = ?, miasto = ?, telefon = ?,
                 email = ?, dodatkowe = ?, wymagania_innych = ?,
                 liczba_osob = ?, typ_dokumentu = ?, numer_dokumentu = ?,
                 wyjazd_kierunek = ?, wyjazd_termin = ?, wyjazd_data_od = ?,
                 wyjazd_data_do = ?, budzet = ?, nip = ?, braki = ?
               WHERE id = ?""",
            (
                uczestnik.imie,
                uczestnik.nazwisko,
                uczestnik.nazwa_firmy,
                uczestnik.kraj_region,
                uczestnik.ulica,
                uczestnik.kod_pocztowy,
                uczestnik.miasto,
                uczestnik.telefon,
                uczestnik.email,
                uczestnik.dodatkowe_informacje,
                uczestnik.wymagania_innych_osob,
                uczestnik.liczba_osob,
                uczestnik.typ_dokumentu.value if uczestnik.typ_dokumentu else None,
                uczestnik.numer_dokumentu,
                uczestnik.wyjazd_kierunek,
                uczestnik.wyjazd_termin,
                uczestnik.wyjazd_data_od,
                uczestnik.wyjazd_data_do,
                uczestnik.budzet,
                uczestnik.nip,
                ", ".join(uczestnik.braki_krytyczne()) or None,
                zgloszenie_id,
            ),
        )


def ustaw_status(zgloszenie_id: int, status: str) -> None:
    with polaczenie() as conn:
        conn.execute("UPDATE zgloszenia SET status = ? WHERE id = ?", (status, zgloszenie_id))


def zgloszenia_do_wyboru() -> list[dict]:
    """Zgłoszenia uporządkowane po nazwisku, z informacją o umowie.

    Do wyboru uczestnika w panelu i w skryptach. Panel pytał wcześniej o numer
    zgłoszenia, czyli o liczbę, której nikt nie pamięta. Tu przychodzi lista,
    na której widać nazwisko, kierunek i to, czy umowa już jest — więc wybór
    jest wskazaniem osoby, nie przypomnieniem sobie identyfikatora.
    """
    with polaczenie() as conn:
        wiersze = conn.execute(
            """SELECT z.id, z.imie, z.nazwisko, z.email, z.wyjazd_kierunek,
                      z.wyjazd_termin, z.wyjazd_klucz, z.liczba_osob, z.status,
                      u.numer AS numer_umowy, u.wyjazd AS wyjazd_umowy
               FROM zgloszenia z
               LEFT JOIN umowy u ON u.zgloszenie_id = z.id
               ORDER BY lower(coalesce(z.nazwisko, 'zzz')),
                        lower(coalesce(z.imie, '')), z.id"""
        ).fetchall()
    return [dict(w) for w in wiersze]


def czy_przetworzony(message_id: str) -> bool:
    """Nie dotykamy flag na serwerze IMAP - trzymamy własną listę.
    Dzięki temu nie psujemy stanu skrzynki i można bezpiecznie powtarzać przebieg."""
    with polaczenie() as conn:
        return (
            conn.execute(
                "SELECT 1 FROM maile_przetworzone WHERE message_id = ?", (message_id,)
            ).fetchone()
            is not None
        )


def rodzaje_przetworzonych(message_id: list[str]) -> dict[str, str]:
    """message_id -> rodzaj, dla wiadomości już obsłużonych.

    Podsumowanie przebiegu wypisuje wszystkie wiadomości z okna, także te
    pominięte. Bez tego pominięte byłyby bezrodzajowe i wyglądałyby jak
    wiadomości, których program nie rozumie — a to są te, które już obsłużył.
    """
    if not message_id:
        return {}
    znaki = ",".join("?" for _ in message_id)
    with polaczenie() as conn:
        return {
            w["message_id"]: w["typ"]
            for w in conn.execute(
                f"SELECT message_id, typ FROM maile_przetworzone "
                f"WHERE message_id IN ({znaki})",
                message_id,
            )
        }


def oznacz_przetworzony(message_id: str, typ: str, draft: bool) -> None:
    with polaczenie() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO maile_przetworzone
               (message_id, przetworzono, typ, draft_utworzony) VALUES (?,?,?,?)""",
            (message_id, datetime.now().isoformat(timespec="seconds"), typ, int(draft)),
        )


USUNIETE = "usuniete"


def usun_zgloszenia(identyfikatory: list[int]) -> int:
    """Usuwa zgłoszenia razem z ich danymi wrażliwymi. Zwraca liczbę usuniętych.

    Wiadomość, z której zgłoszenie powstało, zostaje oznaczona jako usunięta
    ręcznie. Bez tego następny przebieg poczty zobaczyłby w skrzynce formularz
    bez zgłoszenia i odtworzył je — czyli usunięcie działałoby do pierwszego
    kliknięcia „Sprawdź pocztę". Zgłoszeń, które mają umowę, nie usuwa:
    rejestr umów nie może wskazywać na osobę, której nie ma.
    """
    if not identyfikatory:
        return 0
    znaki = ",".join("?" for _ in identyfikatory)
    teraz = datetime.now().isoformat(timespec="seconds")
    with polaczenie() as conn:
        wiersze = conn.execute(
            f"""SELECT z.id, z.message_id FROM zgloszenia z
                WHERE z.id IN ({znaki})
                  AND NOT EXISTS (SELECT 1 FROM umowy u WHERE u.zgloszenie_id = z.id)""",
            identyfikatory,
        ).fetchall()
        for w in wiersze:
            conn.execute("DELETE FROM dane_wrazliwe WHERE zgloszenie_id = ?", (w["id"],))
            conn.execute("UPDATE rezerwacje SET zgloszenie_id = NULL WHERE zgloszenie_id = ?", (w["id"],))
            conn.execute("UPDATE rozmowy SET zgloszenie_id = NULL WHERE zgloszenie_id = ?", (w["id"],))
            conn.execute("DELETE FROM zgloszenia WHERE id = ?", (w["id"],))
            if w["message_id"]:
                zmienione = conn.execute(
                    "UPDATE maile_przetworzone SET typ = ? WHERE message_id = ?",
                    (USUNIETE, w["message_id"]),
                ).rowcount
                if not zmienione:
                    conn.execute(
                        "INSERT INTO maile_przetworzone (message_id, przetworzono, typ, "
                        "draft_utworzony) VALUES (?,?,?,0)",
                        (w["message_id"], teraz, USUNIETE),
                    )
    return len(wiersze)


def wiadomosci_usuniete() -> set[str]:
    """message_id wiadomości, których zgłoszenia usunięto ręcznie."""
    with polaczenie() as conn:
        return {
            w["message_id"] for w in conn.execute(
                "SELECT message_id FROM maile_przetworzone WHERE typ = ?", (USUNIETE,))
        }


def zapisz_rezerwacje(
    rezerwacja: "Rezerwacja",
    wyjazd: str | None,
    message_id: str | None = None,
    zgloszenie_id: int | None = None,
) -> int:
    with polaczenie() as conn:
        kursor = conn.execute(
            """INSERT INTO rezerwacje
               (utworzono, wyjazd, zgloszenie_id, message_id, typ, dostawca,
                numer_rezerwacji, data_od, data_do, dane, braki)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                datetime.now().isoformat(timespec="seconds"),
                wyjazd,
                zgloszenie_id,
                message_id,
                rezerwacja.typ.value,
                rezerwacja.dostawca,
                rezerwacja.numer_rezerwacji,
                rezerwacja.data_od,
                rezerwacja.data_do,
                rezerwacja.model_dump_json(),
                json.dumps(rezerwacja.braki_krytyczne(), ensure_ascii=False),
            ),
        )
        return int(kursor.lastrowid)


def rezerwacje_wyjazdu(wyjazd: str) -> list[dict]:
    with polaczenie() as conn:
        wiersze = conn.execute(
            "SELECT * FROM rezerwacje WHERE wyjazd = ? ORDER BY typ, data_od",
            (wyjazd,),
        ).fetchall()
    return [dict(w) for w in wiersze]


def rezerwacje_nieprzypisane() -> list[dict]:
    with polaczenie() as conn:
        wiersze = conn.execute(
            "SELECT * FROM rezerwacje WHERE wyjazd IS NULL ORDER BY id"
        ).fetchall()
    return [dict(w) for w in wiersze]


def przypisz_rezerwacje(rezerwacja_id: int, wyjazd: str) -> None:
    with polaczenie() as conn:
        conn.execute(
            "UPDATE rezerwacje SET wyjazd = ? WHERE id = ?", (wyjazd, rezerwacja_id)
        )


def uczestnicy_wyjazdu(wyjazd: str) -> list[dict]:
    """Uczestnicy wyjazdu razem z danymi wrażliwymi.

    Na listę trafia każdy, kto ma umowę na ten wyjazd, oraz każdy, kto się na
    niego zgłosił i umowy jeszcze nie ma. Wcześniej lista brała wyłącznie
    osoby z umową, więc do chwili wystawienia pierwszej umowy arkusz był
    pusty, choć zgłoszenia leżały w bazie. Kolumna `nr_umowy` jest pusta
    u osób bez umowy — po tym widać, komu trzeba ją jeszcze wystawić.

    Używane WYŁĄCZNIE do listy uczestników i do zgłoszenia do ubezpieczyciela.
    """
    with polaczenie() as conn:
        wiersze = conn.execute(
            """SELECT z.*, u.numer AS nr_umowy, u.data_zawarcia, u.kwota,
                      d.data_urodzenia, d.pesel, d.numer_dokumentu,
                      d.ulica AS w_ulica, d.kod_pocztowy AS w_kod, d.miasto AS w_miasto
               FROM zgloszenia z
               LEFT JOIN umowy u ON u.zgloszenie_id = z.id
               LEFT JOIN dane_wrazliwe d ON d.zgloszenie_id = z.id
               WHERE u.wyjazd = ?
                  OR (u.numer IS NULL AND z.wyjazd_klucz = ?)
               ORDER BY z.nazwisko, z.imie""",
            (wyjazd, wyjazd),
        ).fetchall()
    return [dict(w) for w in wiersze]


def ustaw_wyjazd(
    zgloszenie_id: int,
    klucz: str,
    kierunek: str | None = None,
    termin: str | None = None,
) -> None:
    """Zapisuje przy zgłoszeniu klucz wyjazdu z wyjazdy.yaml.

    Kierunek i termin słowami uzupełnia tylko tam, gdzie są puste — to, co
    napisał nadawca, ma pierwszeństwo przed nazwą z katalogu.
    """
    with polaczenie() as conn:
        conn.execute(
            """UPDATE zgloszenia SET
                 wyjazd_klucz = ?,
                 wyjazd_kierunek = COALESCE(NULLIF(wyjazd_kierunek, ''), ?),
                 wyjazd_termin = COALESCE(NULLIF(wyjazd_termin, ''), ?)
               WHERE id = ?""",
            (klucz, kierunek, termin, zgloszenie_id),
        )


# pole zgłoszenia -> kolumna w tabeli, dla danych odczytanych z formularza
_KOLUMNY_FORMULARZA = {
    "imie": "imie", "nazwisko": "nazwisko", "nazwa_firmy": "nazwa_firmy",
    "kraj_region": "kraj_region", "ulica": "ulica", "kod_pocztowy": "kod_pocztowy",
    "miasto": "miasto", "telefon": "telefon", "email": "email",
    "dodatkowe_informacje": "dodatkowe", "typ_dokumentu": "typ_dokumentu",
    "numer_dokumentu": "numer_dokumentu", "nip": "nip",
    "wyjazd_kierunek": "wyjazd_kierunek", "wyjazd_termin": "wyjazd_termin",
}


def uzupelnij_z_formularza(zgloszenie_id: int, pola: dict[str, str]) -> None:
    """Nadpisuje w zgłoszeniu te pola, które formularz podaje wprost.

    Pól, których w formularzu nie ma, nie rusza — to, co zapisano wcześniej,
    zostaje. Nazwy kolumn pochodzą ze stałej tabeli, nie z danych wejściowych.
    """
    pary = [(_KOLUMNY_FORMULARZA[p], w) for p, w in pola.items()
            if p in _KOLUMNY_FORMULARZA and w]
    if not pary:
        return
    ustawienia = ", ".join(f"{kolumna} = ?" for kolumna, _ in pary)
    with polaczenie() as conn:
        conn.execute(
            f"UPDATE zgloszenia SET {ustawienia} WHERE id = ?",
            (*[w for _, w in pary], zgloszenie_id),
        )


def zgloszenia_wg_wiadomosci() -> dict[str, tuple[int, bool]]:
    """message_id → (id zgłoszenia, czy ma już klucz wyjazdu), dla formularzy."""
    with polaczenie() as conn:
        wiersze = conn.execute(
            "SELECT id, message_id, wyjazd_klucz FROM zgloszenia "
            "WHERE message_id IS NOT NULL AND zrodlo = 'formularz'"
        ).fetchall()
    return {w["message_id"]: (int(w["id"]), bool(w["wyjazd_klucz"])) for w in wiersze}


def ma_zgloszenie(message_id: str) -> bool:
    with polaczenie() as conn:
        return conn.execute(
            "SELECT 1 FROM zgloszenia WHERE message_id = ?", (message_id,)
        ).fetchone() is not None


def ma_dane_wrazliwe(zgloszenie_id: int) -> bool:
    with polaczenie() as conn:
        return conn.execute(
            "SELECT 1 FROM dane_wrazliwe WHERE zgloszenie_id = ?", (zgloszenie_id,)
        ).fetchone() is not None


def popraw_osobe(zgloszenie_id: int, imie: str | None, nazwisko: str | None) -> None:
    """Nadpisuje imię i nazwisko danymi z pól formularza."""
    with polaczenie() as conn:
        conn.execute(
            "UPDATE zgloszenia SET imie = COALESCE(?, imie), "
            "nazwisko = COALESCE(?, nazwisko) WHERE id = ?",
            (imie, nazwisko, zgloszenie_id),
        )


def zgloszenia_bez_wyjazdu() -> dict[str, int]:
    """message_id → id zgłoszeń z formularza, które nie mają klucza wyjazdu."""
    with polaczenie() as conn:
        wiersze = conn.execute(
            "SELECT id, message_id FROM zgloszenia "
            "WHERE message_id IS NOT NULL AND zrodlo = 'formularz' "
            "AND (wyjazd_klucz IS NULL OR wyjazd_klucz = '')"
        ).fetchall()
    return {w["message_id"]: int(w["id"]) for w in wiersze}


def zapisz_rozmowe(
    osoba: str, transkrypcja: str, notatka_json: str, plik_audio: str | None = None
) -> int:
    with polaczenie() as conn:
        kursor = conn.execute(
            """INSERT INTO rozmowy (utworzono, osoba, plik_audio, transkrypcja, notatka)
               VALUES (?,?,?,?,?)""",
            (
                datetime.now().isoformat(timespec="seconds"),
                osoba,
                plik_audio,
                transkrypcja,
                notatka_json,
            ),
        )
        return int(kursor.lastrowid)


def notatki_osoby(nazwisko: str) -> list[dict]:
    """Potrzebne do odprawy przedwyjazdowej: co ta osoba mówiła przez telefon."""
    with polaczenie() as conn:
        wiersze = conn.execute(
            "SELECT * FROM rozmowy WHERE osoba LIKE ? ORDER BY utworzono DESC",
            (f"%{nazwisko}%",),
        ).fetchall()
    return [dict(w) for w in wiersze]


def stan_biura() -> dict[str, int]:
    """Liczby na panel dziennej odprawy."""
    with polaczenie() as conn:
        def licz(sql: str) -> int:
            return int(conn.execute(sql).fetchone()[0])

        return {
            "nowe_zgloszenia": licz("SELECT COUNT(*) FROM zgloszenia WHERE status='nowe'"),
            "drafty_utworzone": licz(
                "SELECT COUNT(*) FROM maile_przetworzone WHERE draft_utworzony=1"
            ),
            "umowy_do_zgloszenia_ufg": licz(
                "SELECT COUNT(*) FROM umowy WHERE zgloszone_ufg=0"
            ),
            "zgloszenia_z_brakami": licz(
                "SELECT COUNT(*) FROM zgloszenia WHERE braki != '[]'"
            ),
            "rozmowy_w_bazie": licz("SELECT COUNT(*) FROM rozmowy"),
        }
