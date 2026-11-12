#!/usr/bin/env python3
"""Panel biura — uruchamianie wszystkiego bez wiersza poleceń.

    python skrypty/panel.py

Po co okno, skoro jest `biuro.cmd`. Bo Smart App Control na Windowsie blokuje
pliki `.cmd` jako niepodpisane skrypty i `Unblock-File` tego nie zdejmuje.
Ten panel jest zwykłym programem w Pythonie, więc uruchamia go `python.exe`
— plik podpisany, który SAC przepuszcza.

Panel niczego nie liczy sam. Każdy przycisk uruchamia ten sam skrypt, który
uruchomiłabyś ręcznie, i pokazuje jego wyjście słowo w słowo. Nie ma tu
drugiej implementacji niczego — gdyby była, mogłaby zachowywać się inaczej
niż to, co mierzymy i testujemy.

Wygląd jest zrobiony na tkinterze bez żadnych dodatkowych bibliotek: motyw
`clam`, własna paleta, systemowy krój pisma i jeden kolor wiodący. Powód jest
praktyczny, nie estetyczny — każda dodatkowa biblioteka graficzna to kolejny
niepodpisany plik wykonywalny, czyli dokładnie to, co SAC blokuje.

Skrót na pulpit, żeby nie wpisywać ścieżki:
  cel:          C:\\...\\biuro-bielik\\.venv\\Scripts\\pythonw.exe
  argumenty:    skrypty\\panel.py
  rozpocznij w: C:\\...\\biuro-bielik
`pythonw.exe` zamiast `python.exe` — wtedy pod oknem nie otwiera się czarna
konsola.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from datetime import date
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import messagebox, simpledialog, ttk
except ImportError:
    print("Brak modułu tkinter — nie da się otworzyć okna.")
    print("Na Windowsie zwykle jest w komplecie z Pythonem. Jeśli go nie ma,")
    print("zainstaluj Pythona z python.org i zaznacz 'tcl/tk and IDLE'.")
    sys.exit(1)

KORZEN = Path(__file__).resolve().parent.parent

# ---- paleta ---------------------------------------------------------------
# Jeden kolor wiodący, dwie szarości tła, jedna linia. Kolory znaczeniowe
# (zielony, czerwony, żółty) pojawiają się tylko w wyjściu skryptów, i tylko
# tam, gdzie coś znaczą.

TLO = "#f4f6f8"          # tło okna
BOK = "#eceff3"          # pasek boczny
BIEL = "#ffffff"
RAMKA = "#dfe4ea"
TEKST = "#1e2733"
PRZYGASZONY = "#6d7885"
AKCENT = "#1f5f7a"       # arktyczny granat-turkus
AKCENT_TLO = "#e4eef2"
AKCENT_CIEMNY = "#174a60"
ZIELEN = "#1f7a4d"
CZERWIEN = "#a32f2f"
ZOLTY = "#8a5a00"

KROJE_TEKST = ("Segoe UI", "Inter", "Helvetica Neue", "DejaVu Sans", "Arial")
KROJE_MASZYNOWY = ("Cascadia Mono", "Consolas", "Menlo", "DejaVu Sans Mono",
                   "Courier New")


def interpreter() -> Path:
    """Python ze środowiska .venv, nie systemowy.

    Systemowy nie ma zainstalowanych zależności projektu, a różnica
    objawiłaby się dopiero przy pierwszym imporcie — po kliknięciu.
    """
    for kandydat in (
        KORZEN / ".venv" / "Scripts" / "python.exe",   # Windows
        KORZEN / ".venv" / "bin" / "python",           # Linux, macOS
    ):
        if kandydat.exists():
            return kandydat
    return Path(sys.executable)


def nazwa_firmy() -> str:
    """Nazwa firmy z config.yaml, do nagłówka okna.

    Panel ma działać też wtedy, gdy konfiguracji jeszcze nie ma — wtedy
    w nagłówku jest słowo ogólne, a nie komunikat o błędzie.
    """
    try:
        sys.path.insert(0, str(KORZEN))
        from biuro.config import cfg

        return str(cfg().get("firma.nazwa") or "Biuro") or "Biuro"
    except Exception:
        return "Biuro"


# Pliki, które muszą być w parze z tym panelem, i znak rozpoznawczy każdego.
# Powód jest z życia: aktualizacja projektu polega na przegraniu kilku plików
# ręcznie i łatwo o pominięcie jednego. Wtedy panel otwiera się normalnie,
# a dopiero kliknięcie pokazuje „cannot import name …" albo komunikat ze
# starej wersji skryptu — i wygląda to na błąd programu, nie na braki.
KOMPLET: tuple[tuple[str, str, str], ...] = (
    ("biuro/baza.py", "def zgloszenia_do_wyboru", "wybór osoby z listy"),
    ("biuro/umowy.py", "def wyjazd_dla_zgloszenia", "ustalanie wyjazdu"),
    ("biuro/polszczyzna.py", "def odmien", "odmiana liczebników"),
    ("biuro/mail/pipeline.py", '"w_skrzynce"', "liczniki przebiegu poczty"),
    ("biuro/mail/pipeline.py", "def przypisz_wyjazd", "zapis wyjazdu przy zgłoszeniu"),
    ("biuro/baza.py", "def ustaw_wyjazd", "zapis wyjazdu przy zgłoszeniu"),
    ("biuro/mail/pipeline.py", "def dane_z_formularza", "odczyt pól formularza"),
    ("biuro/baza.py", "def uzupelnij_z_formularza", "odczyt pól formularza"),
    ("skrypty/sprawdz_maile.py", "def wypisz_podsumowanie", "podsumowanie poczty"),
    ("skrypty/zrob_umowe.py", "opis_uczestnika", "potwierdzenie umowy"),
    ("skrypty/zrob_odprawe.py", "wyjazd_dla_zgloszenia", "odprawa bez klucza"),
    ("skrypty/zrob_liste.py", '"--oba"', "oba warianty listy naraz"),
    ("skrypty/zrob_csv_ufg.py", "odmiana_umow", "podsumowanie wykazu UFG"),
)


def braki_w_komplecie() -> list[str]:
    """Pliki, których nie ma albo są w starszej wersji niż panel."""
    braki = []
    for sciezka, znak, po_co in KOMPLET:
        plik = KORZEN / sciezka
        if not plik.exists():
            braki.append(f"{sciezka} — brak pliku ({po_co})")
            continue
        try:
            if znak not in plik.read_text(encoding="utf-8"):
                braki.append(f"{sciezka} — stara wersja ({po_co})")
        except OSError as e:
            braki.append(f"{sciezka} — nie daje się odczytać ({e})")
    return braki


def _dostepny(okno: tk.Misc, kandydaci: tuple[str, ...], zapas: str) -> str:
    rodziny = {r.lower() for r in tkfont.families(okno)}
    for krój in kandydaci:
        if krój.lower() in rodziny:
            return krój
    return zapas


class Motyw:
    """Kroje pisma i style ttk. Ustawiane raz, po utworzeniu okna."""

    def __init__(self, okno: tk.Tk) -> None:
        self.tekst = _dostepny(okno, KROJE_TEKST, "TkDefaultFont")
        self.maszynowy = _dostepny(okno, KROJE_MASZYNOWY, "TkFixedFont")

        # Kroje systemowe obejmują też okienka dialogowe (pytania, ostrzeżenia),
        # których nie stylujemy osobno — stąd zmiana nazwanych czcionek Tk.
        for nazwa, rozmiar in (
            ("TkDefaultFont", 10), ("TkTextFont", 10), ("TkMenuFont", 10),
            ("TkHeadingFont", 10),
        ):
            try:
                tkfont.nametofont(nazwa).configure(family=self.tekst, size=rozmiar)
            except tk.TclError:
                pass

        s = ttk.Style(okno)
        s.theme_use("clam")

        s.configure(".", background=TLO, foreground=TEKST,
                    font=(self.tekst, 10))
        s.configure("TFrame", background=TLO)
        s.configure("Biel.TFrame", background=BIEL)
        s.configure("Bok.TFrame", background=BOK)
        s.configure("Ramka.TFrame", background=RAMKA)

        s.configure("TLabel", background=TLO, foreground=TEKST)
        s.configure("Tytul.TLabel", background=BIEL, foreground=TEKST,
                    font=(self.tekst, 15, "bold"))
        s.configure("Podtytul.TLabel", background=BIEL, foreground=PRZYGASZONY,
                    font=(self.tekst, 10))
        s.configure("Sekcja.TLabel", background=BOK, foreground=PRZYGASZONY,
                    font=(self.tekst, 8, "bold"))
        s.configure("Podpowiedz.TLabel", background=BOK, foreground=PRZYGASZONY,
                    font=(self.tekst, 8))
        s.configure("Status.TLabel", background=TLO, foreground=TEKST,
                    font=(self.tekst, 10))
        s.configure("Stopka.TLabel", background=BIEL, foreground=PRZYGASZONY,
                    font=(self.tekst, 9))
        s.configure("Dialog.TLabel", background=BIEL, foreground=TEKST,
                    font=(self.tekst, 10))
        s.configure("DialogSzary.TLabel", background=BIEL,
                    foreground=PRZYGASZONY, font=(self.tekst, 9))

        # Przyciski paska bocznego: płaskie, tekst do lewej, bez efektu 3D.
        s.configure(
            "Bok.TButton", background=BIEL, foreground=TEKST,
            bordercolor=RAMKA, lightcolor=BIEL, darkcolor=BIEL,
            borderwidth=1, relief="flat", anchor="w",
            padding=(12, 7), font=(self.tekst, 10),
        )
        s.map(
            "Bok.TButton",
            background=[("disabled", BOK), ("pressed", AKCENT_TLO),
                        ("active", AKCENT_TLO)],
            foreground=[("disabled", "#a7b0ba")],
            bordercolor=[("active", AKCENT), ("pressed", AKCENT)],
            lightcolor=[("active", AKCENT_TLO), ("pressed", AKCENT_TLO)],
            darkcolor=[("active", AKCENT_TLO), ("pressed", AKCENT_TLO)],
        )
        s.configure(
            "Akcent.TButton", background=AKCENT, foreground=BIEL,
            bordercolor=AKCENT, lightcolor=AKCENT, darkcolor=AKCENT,
            borderwidth=1, relief="flat", anchor="w",
            padding=(12, 7), font=(self.tekst, 10, "bold"),
        )
        s.map(
            "Akcent.TButton",
            background=[("disabled", "#b9c4cc"), ("pressed", AKCENT_CIEMNY),
                        ("active", AKCENT_CIEMNY)],
            bordercolor=[("disabled", "#b9c4cc"), ("active", AKCENT_CIEMNY)],
            lightcolor=[("active", AKCENT_CIEMNY), ("pressed", AKCENT_CIEMNY)],
            darkcolor=[("active", AKCENT_CIEMNY), ("pressed", AKCENT_CIEMNY)],
            foreground=[("disabled", BIEL)],
        )
        s.configure("Cichy.TButton", background=BOK, foreground=PRZYGASZONY,
                    bordercolor=BOK, lightcolor=BOK, darkcolor=BOK,
                    borderwidth=1, relief="flat", padding=(8, 6),
                    font=(self.tekst, 9))
        s.map("Cichy.TButton",
              background=[("active", RAMKA), ("pressed", RAMKA)],
              foreground=[("active", TEKST)])
        s.configure("Dialog.TButton", background=BIEL, foreground=TEKST,
                    bordercolor=RAMKA, lightcolor=BIEL, darkcolor=BIEL,
                    borderwidth=1, relief="flat", padding=(14, 8))
        s.map("Dialog.TButton",
              background=[("active", AKCENT_TLO), ("pressed", AKCENT_TLO)],
              bordercolor=[("active", AKCENT)])

        s.configure("TEntry", fieldbackground=BIEL, bordercolor=RAMKA,
                    lightcolor=RAMKA, darkcolor=RAMKA, borderwidth=1,
                    padding=7, relief="flat")
        s.map("TEntry", bordercolor=[("focus", AKCENT)],
              lightcolor=[("focus", AKCENT)], darkcolor=[("focus", AKCENT)])

        s.configure("Praca.Horizontal.TProgressbar",
                    background=AKCENT, troughcolor=RAMKA,
                    bordercolor=RAMKA, lightcolor=AKCENT, darkcolor=AKCENT,
                    borderwidth=0, thickness=4)

        s.configure("Lista.Treeview", background=BIEL, fieldbackground=BIEL,
                    foreground=TEKST, bordercolor=RAMKA, borderwidth=0,
                    rowheight=30, font=(self.tekst, 10))
        s.configure("Lista.Treeview.Heading", background=BOK,
                    foreground=PRZYGASZONY, relief="flat",
                    padding=(8, 7), font=(self.tekst, 9, "bold"))
        s.map("Lista.Treeview",
              background=[("selected", AKCENT)],
              foreground=[("selected", BIEL)])
        s.map("Lista.Treeview.Heading", background=[("active", BOK)])

        s.configure("TScrollbar", background=BOK, troughcolor=TLO,
                    bordercolor=TLO, arrowcolor=PRZYGASZONY,
                    lightcolor=BOK, darkcolor=BOK, borderwidth=0)
        s.configure("TSeparator", background=RAMKA)


class Panel:
    def __init__(self, okno: tk.Tk, motyw: Motyw) -> None:
        self.okno = okno
        self.motyw = motyw
        self.kolejka: queue.Queue[str | None] = queue.Queue()
        self.dziala = False
        self.przyciski: list[ttk.Button] = []

        okno.title("Biuro na Bieliku")
        okno.configure(background=TLO)
        # Wysokość nie jest kwestią gustu: pasek boczny ma jedenaście
        # przycisków i trzy podpowiedzi, czyli około 550 punktów treści.
        # Przy niższym oknie dolne przyciski zostałyby obcięte.
        okno.minsize(920, 680)
        self._wysrodkuj(1080, 760)

        okno.columnconfigure(0, weight=1)
        okno.rowconfigure(1, weight=1)

        self._naglowek(okno)

        srodek = ttk.Frame(okno)
        srodek.grid(row=1, column=0, sticky="nsew")
        srodek.columnconfigure(1, weight=1)
        srodek.rowconfigure(0, weight=1)

        self._pasek_boczny(srodek)
        self._obszar_wyjscia(srodek)
        self._stopka(okno)

        # Ścieżki katalogu i interpretera trafiają tylko do tytułu okna.
        # W oknie wyjścia zabierały dwa pierwsze wiersze i pokazywały na
        # nagraniu układ dysku, a przy zgłoszeniu błędu i tak widać je
        # w komunikacie.
        okno.title(f"Biuro na Bieliku — {KORZEN.name}")

        # Przy komplecie plików okno zaczyna puste. Komunikat pojawia się
        # tylko wtedy, gdy jest o czym mówić.
        braki = braki_w_komplecie()
        if braki:
            self.pisz("  Niekompletna aktualizacja", "naglowek")
            self.pisz("  " + "─" * 58, "linia")
            self.pisz("Te pliki są starsze niż panel. Dopóki ich nie "
                      "przegrasz, część przycisków pokaże błąd:", "uwaga")
            for brak in braki:
                self.pisz(f"  - {brak}", "blad")
            self.pisz("")

        self.okno.after(100, self.odbieraj)

    # ---- budowanie interfejsu -------------------------------------------

    def _wysrodkuj(self, szer: int, wys: int) -> None:
        """Okno na środku, ale nigdy większe niż ekran.

        Na laptopie 1366×768 okno o wysokości 760 schowałoby stopkę pod
        paskiem zadań.
        """
        ekran_szer = self.okno.winfo_screenwidth()
        ekran_wys = self.okno.winfo_screenheight()
        szer = min(szer, ekran_szer - 40)
        wys = min(wys, ekran_wys - 90)
        x = max(0, (ekran_szer - szer) // 2)
        y = max(0, (ekran_wys - wys) // 3)
        self.okno.geometry(f"{szer}x{wys}+{x}+{y}")

    def _naglowek(self, rodzic: tk.Misc) -> None:
        pasek = ttk.Frame(rodzic, style="Biel.TFrame", padding=(22, 16, 22, 14))
        pasek.grid(row=0, column=0, sticky="ew")
        pasek.columnconfigure(1, weight=1)

        ttk.Label(pasek, text="Biuro na Bieliku", style="Tytul.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            pasek,
            text=f"{nazwa_firmy()}  ·  model pracuje na tym komputerze",
            style="Podtytul.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        prawy = ttk.Frame(pasek, style="Biel.TFrame")
        prawy.grid(row=0, column=2, rowspan=2, sticky="e")
        self.lampka = tk.Label(
            prawy, text="●", font=(self.motyw.tekst, 11),
            foreground=ZIELEN, background=BIEL,
        )
        self.lampka.pack(side="left", padx=(0, 6))
        self.status = ttk.Label(prawy, text="Gotowe", style="Podtytul.TLabel")
        self.status.pack(side="left")

        tk.Frame(rodzic, height=1, background=RAMKA).grid(
            row=0, column=0, sticky="sew"
        )

    def _pasek_boczny(self, rodzic: tk.Misc) -> None:
        bok = ttk.Frame(rodzic, style="Bok.TFrame", padding=(16, 12, 16, 14))
        bok.grid(row=0, column=0, sticky="ns")

        self._sekcja(bok, "Poczta")
        self._przycisk(bok, "Sprawdź pocztę", self.poczta_serio,
                       "Zapisuje zgłoszenia i tworzy robocze wersje odpowiedzi.",
                       akcent=True)

        self._sekcja(bok, "Dokumenty")
        self._przycisk(bok, "Lista zgłoszeń", self.lista)
        self._przycisk(bok, "Wystaw umowę", self.umowa)
        self._przycisk(bok, "Lista uczestników", self.arkusz)
        self._przycisk(bok, "Odprawa przedwyjazdowa", self.odprawa)

        self._sekcja(bok, "Urząd")
        self._przycisk(bok, "Wykaz umów (CSV)", self.ufg)

        tk.Frame(rodzic, width=1, background=RAMKA).grid(
            row=0, column=0, sticky="nse"
        )

    def _obszar_wyjscia(self, rodzic: tk.Misc) -> None:
        prawa = ttk.Frame(rodzic, padding=(18, 14, 18, 16))
        prawa.grid(row=0, column=1, sticky="nsew")
        prawa.rowconfigure(2, weight=1)
        prawa.columnconfigure(0, weight=1)

        gora = ttk.Frame(prawa)
        gora.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        gora.columnconfigure(0, weight=1)

        self.opis_zadania = ttk.Label(
            gora, text="Przebieg pojawi się tutaj", style="Status.TLabel"
        )
        self.opis_zadania.grid(row=0, column=0, sticky="w")
        ttk.Button(gora, text="Wyczyść", style="Cichy.TButton",
                   command=self.wyczysc).grid(row=0, column=1, sticky="e")

        # Pasek postępu ma własny wiersz i jest widoczny zawsze: puste
        # korytko wygląda jak cienka linia i oddziela nagłówek od wyjścia.
        # Gdyby pojawiał się dopiero na czas pracy, układ podskakiwałby
        # przy każdym kliknięciu.
        self.postep = ttk.Progressbar(
            prawa, style="Praca.Horizontal.TProgressbar",
            mode="determinate", value=0,
        )
        self.postep.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        obwodka = ttk.Frame(prawa, style="Ramka.TFrame", padding=1)
        obwodka.grid(row=2, column=0, sticky="nsew")
        obwodka.rowconfigure(0, weight=1)
        obwodka.columnconfigure(0, weight=1)

        # Text plus ttk.Scrollbar, a nie ScrolledText: ten drugi dokłada suwak
        # w starym stylu systemowym, który odstaje od reszty okna.
        self.wyjscie = tk.Text(
            obwodka, wrap="word", font=(self.motyw.maszynowy, 10),
            background=BIEL, foreground=TEKST, insertbackground=TEKST,
            selectbackground=AKCENT_TLO, selectforeground=TEKST,
            relief="flat", borderwidth=0, highlightthickness=0,
            padx=14, pady=12, spacing1=1, spacing3=1,
        )
        suwak = ttk.Scrollbar(obwodka, orient="vertical",
                              command=self.wyjscie.yview)
        self.wyjscie.configure(yscrollcommand=suwak.set)
        self.wyjscie.grid(row=0, column=0, sticky="nsew")
        suwak.grid(row=0, column=1, sticky="ns")
        self.wyjscie.configure(state="disabled")

        self.wyjscie.tag_configure("naglowek", foreground=AKCENT,
                                   font=(self.motyw.tekst, 11, "bold"),
                                   spacing1=8, spacing3=4)
        self.wyjscie.tag_configure("linia", foreground=RAMKA)
        self.wyjscie.tag_configure("ok", foreground=ZIELEN)
        self.wyjscie.tag_configure("blad", foreground=CZERWIEN,
                                   font=(self.motyw.maszynowy, 10, "bold"))
        self.wyjscie.tag_configure("uwaga", foreground=ZOLTY)
        self.wyjscie.tag_configure("szary", foreground=PRZYGASZONY)
        self.wyjscie.tag_configure("panel", foreground=AKCENT)

    def _stopka(self, rodzic: tk.Misc) -> None:
        tk.Frame(rodzic, height=1, background=RAMKA).grid(
            row=2, column=0, sticky="ew"
        )
        pasek = ttk.Frame(rodzic, style="Biel.TFrame", padding=(22, 10))
        pasek.grid(row=3, column=0, sticky="ew")
        ttk.Label(
            pasek, style="Stopka.TLabel",
            text="Żadna wiadomość nie jest wysyłana. Odpowiedzi czekają "
                 "jako wersje robocze w Twojej skrzynce.",
        ).pack(anchor="w")

    def _sekcja(self, rodzic: tk.Misc, tytul: str) -> None:
        ttk.Label(rodzic, text=tytul.upper(), style="Sekcja.TLabel").pack(
            anchor="w", pady=(12, 4)
        )

    def _przycisk(self, rodzic: tk.Misc, etykieta: str, akcja,
                  podpowiedz: str = "", akcent: bool = False) -> None:
        b = ttk.Button(
            rodzic, text=etykieta, width=24, command=akcja,
            style="Akcent.TButton" if akcent else "Bok.TButton",
        )
        b.pack(fill="x", pady=2)
        if podpowiedz:
            ttk.Label(rodzic, text=podpowiedz, style="Podpowiedz.TLabel",
                      wraplength=196, justify="left").pack(
                anchor="w", pady=(2, 4), padx=2
            )
        self.przyciski.append(b)

    # ---- uruchamianie ----------------------------------------------------

    def uruchom(self, argumenty: list[str], opis: str) -> None:
        if self.dziala:
            messagebox.showinfo("Chwila", "Poczekaj, aż skończy się poprzednie.",
                                parent=self.okno)
            return
        self.dziala = True
        for b in self.przyciski:
            b.state(["disabled"])
        self.status.configure(text="Pracuje…")
        self.lampka.configure(foreground=AKCENT)
        self.opis_zadania.configure(text=opis)
        self.postep.configure(mode="indeterminate")
        self.postep.start(14)

        self.pisz(f"  {opis}", "naglowek")
        self.pisz("  " + "─" * 58, "linia")

        threading.Thread(
            target=self._w_tle, args=(argumenty,), daemon=True
        ).start()

    def _w_tle(self, argumenty: list[str]) -> None:
        """Czyta wyjście procesu linia po linii i wkłada je do kolejki.

        Osobny wątek, bo bez niego okno zamarłoby na czas przebiegu —
        a przejście po skrzynce z modelem trwa minuty, nie sekundy.
        Do widgetów tkintera pisze wyłącznie wątek główny, przez kolejkę.
        """
        # Wymuszamy UTF-8 po stronie uruchamianego skryptu. Python na
        # Windowsie, pisząc do rury zamiast na konsolę, używa domyślnego
        # kodowania systemu (cp1250). Panel czytał to jako UTF-8, więc
        # polskie litery w wyjściu skryptów ginęły — na przyciskach były,
        # bo przyciski nie przechodzą przez rurę.
        srodowisko = dict(os.environ)
        srodowisko["PYTHONIOENCODING"] = "utf-8"
        srodowisko["PYTHONUTF8"] = "1"

        # Panel działa pod pythonw.exe, czyli bez konsoli. Skrypt uruchamiany
        # przez python.exe konsoli potrzebuje, więc Windows otwierał mu czarne
        # okno, które znikało po zakończeniu — przy każdym kliknięciu.
        # CREATE_NO_WINDOW każe uruchomić proces bez okna; wyjście i tak
        # idzie rurą do panelu.
        bez_okna = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            proces = subprocess.Popen(
                [str(interpreter()), *argumenty],
                cwd=KORZEN,
                env=srodowisko,
                creationflags=bez_okna,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            assert proces.stdout is not None
            for linia in proces.stdout:
                self.kolejka.put(linia.rstrip("\n"))
            proces.wait()
            if proces.returncode == 0:
                self.kolejka.put("[gotowe]")
            else:
                self.kolejka.put(f"[zakończone z kodem {proces.returncode}]")
        except Exception as e:  # noqa: BLE001
            self.kolejka.put(f"BŁĄD URUCHOMIENIA: {e}")
        finally:
            self.kolejka.put(None)

    def odbieraj(self) -> None:
        try:
            while True:
                element = self.kolejka.get_nowait()
                if element is None:
                    self.dziala = False
                    for b in self.przyciski:
                        b.state(["!disabled"])
                    self.postep.stop()
                    self.postep.configure(mode="determinate", value=0)
                    self.status.configure(text="Gotowe")
                    self.lampka.configure(foreground=ZIELEN)
                    self.opis_zadania.configure(text="Przebieg zakończony")
                else:
                    self.pisz(element)
        except queue.Empty:
            pass
        self.okno.after(100, self.odbieraj)

    def _tag(self, linia: str) -> str | None:
        """Kolor wiersza po jego treści.

        Skrypty wypisują wyniki w stałym formacie: „OK" i „BŁĄD" na początku
        wiersza w testach, „UWAGA" przy brakach w umowie. Kolorujemy tylko to,
        co coś znaczy — reszta zostaje czarna, żeby kolor nie stracił wagi.
        """
        goly = linia.strip()
        if goly.startswith(("BŁĄD", "BLAD", "Traceback", "  File \"",
                            "Error", "ERROR")):
            return "blad"
        if goly.startswith(("OK", "Wszystkie przypadki", "Wszystkie zestawy")):
            return "ok"
        if goly.startswith(("UWAGA", "Uwaga", "Brak ")):
            return "uwaga"
        if goly.startswith("[panel]"):
            return "panel"
        if goly in ("[gotowe]",):
            return "ok"
        if goly.startswith("[zakończone"):
            return "uwaga"
        return None

    def pisz(self, tekst: str, tag: str | None = "auto") -> None:
        if tag == "auto":
            tag = self._tag(tekst)
        self.wyjscie.configure(state="normal")
        self.wyjscie.insert("end", tekst + "\n", tag or ())
        self.wyjscie.see("end")
        self.wyjscie.configure(state="disabled")

    def wyczysc(self) -> None:
        self.wyjscie.configure(state="normal")
        self.wyjscie.delete("1.0", "end")
        self.wyjscie.configure(state="disabled")
        self.opis_zadania.configure(text="Przebieg pojawi się tutaj")

    # ---- akcje -----------------------------------------------------------

    def _dni(self, domyslnie: int = 3) -> int | None:
        return simpledialog.askinteger(
            "Zakres", "Ile dni wstecz?", initialvalue=domyslnie,
            minvalue=1, maxvalue=365, parent=self.okno,
        )

    def poczta_serio(self) -> None:
        # Bez pytania „czy na pewno". Przebieg nie wysyła ani nie kasuje
        # niczego — tworzy wersje robocze, które i tak trzeba otworzyć
        # i kliknąć wyślij. Okienko potwierdzenia przy czynności, której
        # nie da się zepsuć, uczy tylko klikania „OK" bez czytania.
        dni = self._dni()
        if not dni:
            return
        self.uruchom(
            ["skrypty/sprawdz_maile.py", "--dni", str(dni)],
            f"Poczta — ostatnie {dni} dni",
        )

    # ---- wybór z listy ---------------------------------------------------
    #
    # Panel pytał dotąd o numer zgłoszenia i o klucz wyjazdu. Oba są
    # identyfikatorami dla programu, nie dla człowieka: nikt nie pamięta, że
    # Kowalska to 14, ani że jedzie na „irlandia-2026". Teraz panel pokazuje
    # tabelę z nazwiskiem i kierunkiem, a klucz wyjazdu wylicza skrypt
    # ze zgłoszenia.

    def _wybor_z_tabeli(
        self,
        tytul: str,
        podtytul: str,
        kolumny: list[tuple[str, str, int]],
        wiersze: list[tuple[tuple[str, ...], object]],
    ) -> object | None:
        """Okno z tabelą i polem do zawężania. Zwraca wartość albo None."""
        if not wiersze:
            messagebox.showinfo(tytul, "Lista jest pusta.", parent=self.okno)
            return None

        okno = tk.Toplevel(self.okno)
        okno.title(tytul)
        okno.configure(background=BIEL)
        okno.transient(self.okno)
        okno.geometry("720x460")
        okno.minsize(560, 360)
        wybrane: dict[str, object] = {}

        gora = ttk.Frame(okno, style="Biel.TFrame", padding=(20, 18, 20, 10))
        gora.pack(fill="x")
        ttk.Label(gora, text=tytul, style="Tytul.TLabel").pack(anchor="w")
        ttk.Label(gora, text=podtytul, style="DialogSzary.TLabel").pack(
            anchor="w", pady=(3, 0)
        )

        srodek = ttk.Frame(okno, style="Biel.TFrame", padding=(20, 0, 20, 0))
        srodek.pack(fill="both", expand=True)
        srodek.rowconfigure(2, weight=1)
        srodek.columnconfigure(0, weight=1)

        szukaj = tk.StringVar()
        pole = ttk.Entry(srodek, textvariable=szukaj, font=(self.motyw.tekst, 10))
        pole.grid(row=0, column=0, sticky="ew", pady=(6, 3))
        ttk.Label(srodek, text="Wpisz kilka liter, żeby zawęzić listę.",
                  style="DialogSzary.TLabel").grid(row=1, column=0, sticky="w",
                                                   pady=(0, 8))

        obwodka = ttk.Frame(srodek, style="Ramka.TFrame", padding=1)
        obwodka.grid(row=2, column=0, sticky="nsew")
        obwodka.rowconfigure(0, weight=1)
        obwodka.columnconfigure(0, weight=1)

        tabela = ttk.Treeview(
            obwodka, style="Lista.Treeview", show="headings",
            columns=[k[0] for k in kolumny], selectmode="browse",
        )
        for klucz, naglowek, szerokosc in kolumny:
            tabela.heading(klucz, text=naglowek, anchor="w")
            tabela.column(klucz, width=szerokosc, anchor="w",
                          stretch=(klucz == kolumny[0][0]))
        suwak = ttk.Scrollbar(obwodka, orient="vertical", command=tabela.yview)
        tabela.configure(yscrollcommand=suwak.set)
        tabela.grid(row=0, column=0, sticky="nsew")
        suwak.grid(row=0, column=1, sticky="ns")
        tabela.tag_configure("parzysty", background="#fafbfc")

        widoczne: list[object] = []

        def odswiez(*_) -> None:
            fraza = szukaj.get().strip().lower()
            widoczne.clear()
            tabela.delete(*tabela.get_children())
            for komorki, wartosc in wiersze:
                if fraza and fraza not in " ".join(komorki).lower():
                    continue
                znaczniki = ("parzysty",) if len(widoczne) % 2 else ()
                tabela.insert("", "end", iid=str(len(widoczne)),
                              values=komorki, tags=znaczniki)
                widoczne.append(wartosc)
            if widoczne:
                tabela.selection_set("0")
                tabela.focus("0")

        def zatwierdz(*_) -> None:
            zaznaczone = tabela.selection()
            if zaznaczone:
                wybrane["wartosc"] = widoczne[int(zaznaczone[0])]
                okno.destroy()

        szukaj.trace_add("write", odswiez)
        tabela.bind("<Double-Button-1>", zatwierdz)
        tabela.bind("<Return>", zatwierdz)
        pole.bind("<Return>", zatwierdz)
        pole.bind("<Down>", lambda _: tabela.focus_set())
        okno.bind("<Escape>", lambda _: okno.destroy())

        stopka = ttk.Frame(okno, style="Biel.TFrame", padding=(20, 14, 20, 18))
        stopka.pack(fill="x")
        ttk.Button(stopka, text="Wybierz", style="Akcent.TButton",
                   command=zatwierdz).pack(side="right")
        ttk.Button(stopka, text="Anuluj", style="Dialog.TButton",
                   command=okno.destroy).pack(side="right", padx=8)

        odswiez()
        pole.focus_set()
        okno.grab_set()
        self.okno.wait_window(okno)
        return wybrane.get("wartosc")

    def wybierz_zgloszenie(self, tytul: str) -> tuple[int, str] | None:
        """Zwraca (id zgłoszenia, opis do nagłówka) albo None.

        W tabeli nie ma adresów ani numerów PESEL. Panel bywa widoczny na
        nagraniu i na ekranie w biurze, a do wskazania osoby wystarczy
        nazwisko i kierunek.
        """
        try:
            sys.path.insert(0, str(KORZEN))
            from biuro.baza import inicjuj, zgloszenia_do_wyboru

            inicjuj()
            dane = zgloszenia_do_wyboru()
        except Exception as e:
            # Panel ma działać nawet przy zepsutej konfiguracji — wtedy
            # pytamy o numer tak jak dawniej, zamiast nie dać się otworzyć.
            messagebox.showwarning(
                tytul,
                f"Nie mogę wczytać listy zgłoszeń ({e}).\n"
                "Podaj numer zgłoszenia ręcznie — lista jest pod przyciskiem "
                "„Lista zgłoszeń”.",
                parent=self.okno,
            )
            zid = simpledialog.askinteger(
                tytul, "Numer zgłoszenia:", parent=self.okno, minvalue=1
            )
            return (zid, f"zgłoszenie {zid}") if zid else None

        wiersze: list[tuple[tuple[str, ...], object]] = []
        for w in dane:
            osoba = " ".join(x for x in (w["nazwisko"], w["imie"]) if x) \
                or "bez nazwiska"
            wiersze.append((
                (
                    osoba,
                    w["wyjazd_kierunek"] or "kierunek nieustalony",
                    w["wyjazd_termin"] or "—",
                    w["numer_umowy"] or "—",
                ),
                (int(w["id"]), osoba),
            ))

        wynik = self._wybor_z_tabeli(
            tytul, "Wybierz osobę z listy. Wyjazd program ustali sam.",
            [("osoba", "Osoba", 220), ("kierunek", "Kierunek", 190),
             ("termin", "Termin", 140), ("umowa", "Umowa", 90)],
            wiersze,
        )
        return wynik  # type: ignore[return-value]

    def wybierz_wyjazd(self, tytul: str) -> str | None:
        try:
            sys.path.insert(0, str(KORZEN))
            from biuro.umowy import wyjazdy

            katalog = wyjazdy()
        except Exception as e:
            messagebox.showwarning(
                tytul, f"Nie mogę wczytać wyjazdy.yaml ({e}).", parent=self.okno
            )
            odpowiedz = simpledialog.askstring(
                tytul, "Klucz wyjazdu:", parent=self.okno
            )
            return odpowiedz.strip() if odpowiedz else None

        wynik = self._wybor_z_tabeli(
            tytul, "Lista pochodzi z pliku wyjazdy.yaml.",
            [("nazwa", "Wyjazd", 280), ("termin", "Termin od", 130),
             ("klucz", "Klucz", 180)],
            self._wiersze_wyjazdow(sorted(katalog), katalog),
        )
        return str(wynik) if wynik else None

    @staticmethod
    def _wiersze_wyjazdow(
        klucze: list[str], katalog: dict
    ) -> list[tuple[tuple[str, ...], object]]:
        return [
            (
                (
                    str(katalog.get(k, {}).get("nazwa", k)),
                    str(katalog.get(k, {}).get("termin_od", "—")),
                    k,
                ),
                k,
            )
            for k in klucze
        ]

    def lista(self) -> None:
        self.uruchom(["skrypty/zrob_umowe.py", "--lista"], "Lista zgłoszeń i wyjazdów")

    def umowa(self) -> None:
        wybor = self.wybierz_zgloszenie("Umowa — dla kogo?")
        if wybor is None:
            return
        zid, opis = wybor
        # Klucza wyjazdu nie pytamy, dopóki da się go wyliczyć ze zgłoszenia.
        # Pytanie pojawia się tylko wtedy, gdy kierunek pasuje do kilku
        # wyjazdów — np. dwa terminy w te same Dolomity.
        argumenty = ["skrypty/zrob_umowe.py", str(zid)]
        wyjazd = self._dopytaj_o_wyjazd(zid)
        if wyjazd == "anulowano":
            return
        if wyjazd:
            argumenty.append(wyjazd)
        self.uruchom(argumenty, f"Umowa — {opis}")

    def _dopytaj_o_wyjazd(self, zgloszenie_id: int) -> str | None:
        """Klucz wyjazdu, gdy zgłoszenie go nie rozstrzyga.

        Zwraca None, gdy pytać nie trzeba (skrypt policzy sam), klucz wyjazdu
        wybrany przez człowieka, albo 'anulowano'. Panel używa tej samej
        funkcji co skrypt, więc nie ma tu drugiej implementacji dopasowania —
        tylko sprawdzenie, czy warto o cokolwiek pytać.
        """
        try:
            sys.path.insert(0, str(KORZEN))
            from biuro.umowy import wyjazd_dla_zgloszenia, wyjazdy

            wynik = wyjazd_dla_zgloszenia(zgloszenie_id)
        except Exception:
            return None  # niech skrypt sam powie, co jest nie tak

        if wynik.klucz is not None or not wynik.kandydaci:
            return None

        try:
            katalog = wyjazdy()
        except Exception:
            katalog = {}
        self.pisz(f"[panel] {wynik.powod}", "panel")
        wybrany = self._wybor_z_tabeli(
            "Który wyjazd?",
            "Kierunek ze zgłoszenia pasuje do kilku wyjazdów.",
            [("nazwa", "Wyjazd", 280), ("termin", "Termin od", 130),
             ("klucz", "Klucz", 180)],
            self._wiersze_wyjazdow(wynik.kandydaci, katalog),
        )
        return str(wybrany) if wybrany else "anulowano"

    def arkusz(self) -> None:
        wyjazd = self.wybierz_wyjazd("Lista uczestników — który wyjazd?")
        if not wyjazd:
            return
        # Bez pytania o wariant: skrypt robi oba pliki naraz i mówi, który
        # jest do wysłania na zewnątrz, a który do użytku wewnętrznego.
        # Pytanie zadawane za każdym razem i tak padało zawsze tak samo,
        # a pomyłka oznaczałaby wysłanie przewoźnikowi listy z PESEL-ami.
        self.uruchom(["skrypty/zrob_liste.py", wyjazd, "--oba"],
                     f"Lista uczestników — {wyjazd}")

    def odprawa(self) -> None:
        wybor = self.wybierz_zgloszenie("Odprawa — dla kogo?")
        if wybor is None:
            return
        zid, opis = wybor
        self.uruchom(["skrypty/zrob_odprawe.py", str(zid)], f"Odprawa — {opis}")

    def ufg(self) -> None:
        dzis = date.today()
        rok = simpledialog.askinteger(
            "Wykaz UFG", "Rok:", initialvalue=dzis.year,
            minvalue=2020, maxvalue=2100, parent=self.okno,
        )
        if not rok:
            return
        miesiac = simpledialog.askinteger(
            "Wykaz UFG", "Miesiąc:", initialvalue=dzis.month,
            minvalue=1, maxvalue=12, parent=self.okno,
        )
        if miesiac:
            self.uruchom(
                ["skrypty/zrob_csv_ufg.py", str(rok), str(miesiac)],
                f"Wykaz umów dla UFG — {miesiac:02d}/{rok}",
            )


# Czynności obsługowe — kopia zapasowa, przebudowa bazy wiedzy, sprawdzenie
# gotowości, testy — nie mają przycisków: w codziennej pracy biura nikt ich
# nie klika, a zaśmiecały pasek. Zostają w wierszu poleceń:
#
#   python skrypty/kopia_zapasowa.py
#   python skrypty/indeksuj.py
#   python skrypty/sprawdz_gotowosc.py
#   python testy/uruchom_wszystkie.py
#
# Przebieg próbny poczty, który nic nie zapisuje, też jest tylko tam:
#
#   python skrypty/sprawdz_maile.py --na-sucho --dni 3


def main() -> int:
    okno = tk.Tk()
    motyw = Motyw(okno)
    Panel(okno, motyw)
    okno.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
