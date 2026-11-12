"""IMAP: czytanie skrzynki i wstawianie draftów.

Dlaczego IMAP, a nie Gmail API: hasło aplikacji działa od razu i z każdą
skrzynką, nie tylko Gmailem. To warunek tego, żeby inna mała firma
mogła uruchomić aplikację bez przechodzenia przez Google Cloud.

Dwie rzeczy, które tu łatwo zepsuć i są zrobione świadomie:
1. Nazwy folderów Gmaila są przetłumaczone ("[Gmail]/Wersje robocze"),
   więc szukamy folderu po fladze special-use, nie po nazwie.
2. Czytamy przez BODY.PEEK, żeby nie oznaczać maili jako przeczytanych.
"""

from __future__ import annotations

import email
import imaplib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

from ..config import cfg

imaplib._MAXLINE = 10_000_000  # Gmail potrafi przysłać długie linie


@dataclass
class Mail:
    message_id: str
    od: str
    od_nazwa: str
    temat: str
    data: str
    tresc: str
    references: str = ""
    zalaczniki: list[str] = field(default_factory=list)

    def skrot(self, limit: int = 2000) -> str:
        return self.tresc[:limit]


def _naglowek(wiadomosc: email.message.Message, nazwa: str) -> str:
    wartosc = wiadomosc.get(nazwa)
    if not wartosc:
        return ""
    try:
        return str(make_header(decode_header(wartosc))).strip()
    except Exception:
        return wartosc.strip()


def _tresc_tekstowa(wiadomosc: email.message.Message) -> tuple[str, list[str]]:
    """Zwraca (tekst, nazwy_zalacznikow). Preferujemy text/plain,
    HTML tylko jako fallback z grubsza odtagowany."""
    zalaczniki: list[str] = []
    plain: list[str] = []
    html: list[str] = []

    for czesc in wiadomosc.walk():
        dyspozycja = str(czesc.get("Content-Disposition") or "")
        if "attachment" in dyspozycja:
            nazwa = czesc.get_filename()
            if nazwa:
                try:
                    nazwa = str(make_header(decode_header(nazwa)))
                except Exception:
                    pass
                zalaczniki.append(nazwa)
            continue
        typ = czesc.get_content_type()
        if typ not in ("text/plain", "text/html"):
            continue
        try:
            surowe = czesc.get_payload(decode=True)
            if surowe is None:
                continue
            kodowanie = czesc.get_content_charset() or "utf-8"
            tekst = surowe.decode(kodowanie, errors="replace")
        except Exception:
            continue
        (plain if typ == "text/plain" else html).append(tekst)

    if plain:
        tekst = "\n".join(plain)
    elif html:
        tekst = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", "\n".join(html), flags=re.S | re.I)
        tekst = re.sub(r"<br\s*/?>|</p>", "\n", tekst, flags=re.I)
        tekst = re.sub(r"<[^>]+>", " ", tekst)
        tekst = re.sub(r"&nbsp;?", " ", tekst)
    else:
        tekst = ""

    tekst = re.sub(r"[ \t]+", " ", tekst)
    tekst = re.sub(r"\n{3,}", "\n\n", tekst)
    return tekst.strip(), zalaczniki


class Skrzynka:
    """Kontekstowy klient IMAP. Użycie:

        with Skrzynka() as skrzynka:
            for mail in skrzynka.nowe(dni=3):
                ...
    """

    def __init__(self) -> None:
        self._conn: imaplib.IMAP4_SSL | None = None
        self._foldery: list[tuple[set[str], str]] = []

    def __enter__(self) -> "Skrzynka":
        k = cfg()
        self._conn = imaplib.IMAP4_SSL(
            k.get("poczta.serwer_imap"), int(k.get("poczta.port_imap", 993))
        )
        self._conn.login(k.imap_user, k.imap_password)
        self._wczytaj_foldery()
        return self

    def __exit__(self, *_) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            try:
                self._conn.logout()
            except Exception:
                pass

    @property
    def conn(self) -> imaplib.IMAP4_SSL:
        if self._conn is None:
            raise RuntimeError("Użyj Skrzynki jako context managera (with Skrzynka() as ...).")
        return self._conn

    # --- foldery ---

    def _wczytaj_foldery(self) -> None:
        status, linie = self.conn.list()
        if status != "OK":
            return
        for linia in linie:
            if isinstance(linia, bytes):
                linia = linia.decode("utf-8", errors="replace")
            dopasowanie = re.match(r"\((?P<flagi>[^)]*)\)\s+\"?[^\"]*\"?\s+\"?(?P<nazwa>.+?)\"?$", linia)
            if not dopasowanie:
                continue
            flagi = {f.lower() for f in dopasowanie.group("flagi").split()}
            self._foldery.append((flagi, dopasowanie.group("nazwa")))

    def folder_po_fladze(self, flaga: str, awaryjny: str) -> str:
        """flaga np. '\\drafts' albo '\\sent'."""
        for flagi, nazwa in self._foldery:
            if flaga.lower() in flagi:
                return nazwa
        return awaryjny

    def folder_draftow(self) -> str:
        return self.folder_po_fladze("\\drafts", "Drafts")

    def folder_wyslanych(self) -> str:
        return self.folder_po_fladze("\\sent", "Sent")

    # --- czytanie ---

    def liczba_w_skrzynce(self) -> int:
        """Ile wiadomości jest w folderze wejściowym w ogóle.

        Potrzebne do podsumowania przebiegu: sama liczba wiadomości z okna
        nic nie mówi, dopóki nie wiadomo, z ilu zostały wybrane.
        """
        folder = cfg().get("poczta.folder_wejsciowy", "INBOX")
        status, dane = self.conn.select(f'"{folder}"', readonly=True)
        if status != "OK" or not dane or not dane[0]:
            return 0
        try:
            return int(dane[0])
        except (TypeError, ValueError):
            return 0

    def nowe(
        self,
        dni: int = 7,
        tylko_nieprzeczytane: bool = False,
        limit: int | None = None,
    ) -> list[Mail]:
        """Wiadomości z okna `dni` dni.

        `limit` to maksymalna liczba wiadomości; brane są najnowsze.
        None  — bierz `poczta.limit_na_przebieg` z konfiguracji (tak działa
                produkcja: jeden przebieg nie przetwarza całej skrzynki).
        0     — bez limitu, całe okno. Tego potrzebuje pomiar: próbka obcięta
                po cichu do dwudziestu wiadomości nie jest powtarzalna.
        """
        folder = cfg().get("poczta.folder_wejsciowy", "INBOX")
        self.conn.select(f'"{folder}"', readonly=True)

        od_kiedy = (datetime.now() - timedelta(days=dni)).strftime("%d-%b-%Y")
        kryterium = f'(SINCE {od_kiedy})'
        if tylko_nieprzeczytane:
            kryterium = f'(UNSEEN SINCE {od_kiedy})'

        status, dane = self.conn.search(None, kryterium)
        if status != "OK" or not dane or not dane[0]:
            return []

        if limit is None:
            limit = int(cfg().get("poczta.limit_na_przebieg", 20))
        identyfikatory = dane[0].split()
        if limit > 0:
            identyfikatory = identyfikatory[-limit:]
        maile: list[Mail] = []
        for nr in identyfikatory:
            # PEEK: nie zmieniamy flagi \Seen
            status, surowe = self.conn.fetch(nr, "(BODY.PEEK[])")
            if status != "OK" or not surowe or not isinstance(surowe[0], tuple):
                continue
            wiadomosc = email.message_from_bytes(surowe[0][1])
            tresc, zalaczniki = _tresc_tekstowa(wiadomosc)
            nazwa, adres = parseaddr(_naglowek(wiadomosc, "From"))
            maile.append(
                Mail(
                    message_id=_naglowek(wiadomosc, "Message-ID") or f"brak-id-{nr.decode()}",
                    od=adres,
                    od_nazwa=nazwa,
                    temat=_naglowek(wiadomosc, "Subject"),
                    data=_naglowek(wiadomosc, "Date"),
                    tresc=tresc,
                    references=_naglowek(wiadomosc, "References"),
                    zalaczniki=zalaczniki,
                )
            )
        return maile

    def moje_dawne_odpowiedzi(self, ile: int = 5) -> list[str]:
        """Przykłady stylu z folderu Wysłane. To zastępuje dostrajanie modelu:
        model widzi, jak Ty piszesz, i naśladuje ton."""
        folder = self.folder_wyslanych()
        try:
            self.conn.select(f'"{folder}"', readonly=True)
        except imaplib.IMAP4.error:
            return []
        status, dane = self.conn.search(None, "ALL")
        if status != "OK" or not dane or not dane[0]:
            return []
        przyklady: list[str] = []
        for nr in reversed(dane[0].split()):
            status, surowe = self.conn.fetch(nr, "(BODY.PEEK[])")
            if status != "OK" or not surowe or not isinstance(surowe[0], tuple):
                continue
            tresc, _ = _tresc_tekstowa(email.message_from_bytes(surowe[0][1]))
            # odcinamy cytowaną historię
            tresc = re.split(r"\n\s*(?:>|W dniu|On .* wrote:|-{2,}\s*Oryginalna)", tresc)[0].strip()
            if 150 < len(tresc) < 2500:
                przyklady.append(tresc)
            if len(przyklady) >= ile:
                break
        return przyklady

    # --- pisanie draftu ---

    def wstaw_draft(
        self,
        oryginal: Mail,
        temat: str,
        tresc: str,
        podpis: str | None = None,
        jako_odpowiedz: bool = True,
    ) -> str:
        """Tworzy draft w folderze wersji roboczych.

        jako_odpowiedz=True podłącza draft do wątku oryginału i dokłada "Re: ".
        jako_odpowiedz=False tworzy nową wiadomość - tak powstaje odprawa
        przedwyjazdowa, która nie jest odpowiedzią na nic.

        Aplikacja NIGDY nie wysyła maila. Draft czeka na Twoje kliknięcie.
        """
        wiadomosc = EmailMessage()
        wiadomosc["From"] = cfg().imap_user
        wiadomosc["To"] = oryginal.od
        wiadomosc["Date"] = formatdate(localtime=True)
        wiadomosc["Message-ID"] = make_msgid()

        if jako_odpowiedz and oryginal.message_id:
            wiadomosc["Subject"] = (
                temat if temat.lower().startswith("re:") else f"Re: {oryginal.temat}"
            )
            # te dwa nagłówki decydują o tym, czy odpowiedź wpadnie w ten sam wątek
            wiadomosc["In-Reply-To"] = oryginal.message_id
            wiadomosc["References"] = (
                f"{oryginal.references} {oryginal.message_id}".strip()
                if oryginal.references
                else oryginal.message_id
            )
        else:
            wiadomosc["Subject"] = temat
        pelna_tresc = tresc if podpis is None else f"{tresc}\n\n{podpis}"
        wiadomosc.set_content(pelna_tresc)

        folder = self.folder_draftow()
        self.conn.append(
            f'"{folder}"',
            "(\\Draft)",
            # Data MUSI mieć strefę czasową. Nowsze wersje Pythona odrzucają
            # datę naiwną (`ValueError: date_time must be aware`), a starsze
            # ją przyjmowały, więc ten błąd pojawia się dopiero po zmianie
            # interpretera i wyłącznie na etapie zapisu draftu — czyli po
            # wykonaniu całej pracy: klasyfikacji, ekstrakcji i wygenerowaniu
            # odpowiedzi. Draft był gotowy i ginął przy ostatnim kroku.
            imaplib.Time2Internaldate(datetime.now(timezone.utc).astimezone()),
            wiadomosc.as_bytes(),
        )
        return folder
