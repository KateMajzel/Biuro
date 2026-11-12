#!/usr/bin/env python3
"""Testy wyboru wiadomości ze skrzynki. Bez sieci — atrapa połączenia IMAP.

    python testy/test_pobieranie_poczty.py

Powód, dla którego ten plik istnieje. Pomiar na prawdziwej poczcie dał raz 31
wiadomości, a raz 20, choć skrzynka się nie zmniejszyła. Przyczyną było
`poczta.limit_na_przebieg` — ograniczenie sensowne w produkcji (jeden przebieg
nie przetwarza całej skrzynki), które przeciekło do skryptu pomiarowego i po
cichu obcięło próbkę. Ani `--dni`, ani `--ile` tego nie podnosiły, bo limit
ciął listę wcześniej. Próbka obcięta bez śladu w logu nie jest powtarzalna,
a na niepowtarzalnej próbce nie wolno podawać żadnej metryki.
"""

import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KORZEN))

from biuro.mail.imap_client import Skrzynka  # noqa: E402

SUROWY = (
    b"Message-ID: <{nr}@example.com>\r\n"
    b"From: Jan Nowak <jan@example.com>\r\n"
    b"Subject: wiadomosc {nr}\r\n"
    b"Date: Mon, 2 Nov 2026 10:00:00 +0100\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"\r\n"
    b"tresc {nr}\r\n"
)


class AtrapaPolaczenia:
    """Minimum, z którego korzysta `nowe()`. Zapamiętuje, o co ją pytano."""

    def __init__(self, ile: int) -> None:
        self.identyfikatory = [str(nr).encode() for nr in range(1, ile + 1)]
        self.pobrane: list[bytes] = []
        self.kryteria: list[str] = []
        self.dodane: list[tuple] = []

    def select(self, folder, readonly=False):  # noqa: ARG002
        return "OK", [b"1"]

    def search(self, charset, kryterium):  # noqa: ARG002
        self.kryteria.append(kryterium)
        return "OK", [b" ".join(self.identyfikatory)]

    def fetch(self, nr, czesc):
        self.pobrane.append(nr)
        assert "PEEK" in czesc, "fetch bez PEEK zmieniłby flagę \\Seen"
        surowy = SUROWY.replace(b"{nr}", nr)
        return "OK", [(b"1 (BODY[])", surowy)]

    def list(self):
        return "OK", [br'(\HasNoChildren \Drafts) "/" "[Gmail]/Wersje robocze"']

    def append(self, folder, flagi, data, wiadomosc):
        self.dodane.append((folder, flagi, data, wiadomosc))
        return "OK", [b"[APPENDUID 1 1] (Success)"]


def skrzynka_z_atrapa(ile: int) -> tuple[Skrzynka, AtrapaPolaczenia]:
    skrzynka = Skrzynka.__new__(Skrzynka)  # bez logowania do serwera
    atrapa = AtrapaPolaczenia(ile)
    skrzynka._conn = atrapa  # `conn` to property tylko do czytania
    return skrzynka, atrapa


PRZYPADKI: list[tuple[str, dict, int]] = [
    ("domyślnie — limit z konfiguracji (produkcja)", {}, 20),
    ("limit=0 — całe okno (pomiar)", {"limit": 0}, 31),
    ("limit=5 — jawne obcięcie", {"limit": 5}, 5),
    ("limit większy niż skrzynka", {"limit": 500}, 31),
]


def main() -> int:
    bledy: list[str] = []

    for nazwa, argumenty, oczekiwane in PRZYPADKI:
        skrzynka, atrapa = skrzynka_z_atrapa(31)
        maile = skrzynka.nowe(dni=120, **argumenty)
        if len(maile) != oczekiwane:
            bledy.append(f"{nazwa}: {len(maile)} wiadomości, oczekiwano {oczekiwane}")
            print(f"  BŁĄD  {nazwa}: {len(maile)} != {oczekiwane}")
        else:
            print(f"  ok    {nazwa}: {len(maile)}")

    # Limit bierze najnowsze, nie najstarsze. Gdyby brał z początku listy,
    # pomiar chodziłby po archiwum, a nie po świeżych zgłoszeniach.
    skrzynka, atrapa = skrzynka_z_atrapa(31)
    skrzynka.nowe(dni=120, limit=3)
    if atrapa.pobrane != [b"29", b"30", b"31"]:
        bledy.append(f"limit bierze nie te wiadomości: {atrapa.pobrane}")
        print(f"  BŁĄD  limit=3 pobrał {atrapa.pobrane}, oczekiwano 29–31")
    else:
        print("  ok    limit bierze najnowsze wiadomości")

    # Domyślnie czytamy wszystko z okna, nie tylko nieprzeczytane. Gdyby
    # kryterium było UNSEEN, próbka kurczyłaby się za każdym razem, gdy
    # Kasia zajrzy do skrzynki — a wyniku nie dałoby się odtworzyć.
    skrzynka, atrapa = skrzynka_z_atrapa(5)
    skrzynka.nowe(dni=120, limit=0)
    if "UNSEEN" in atrapa.kryteria[0]:
        bledy.append("domyślne kryterium zawiera UNSEEN")
        print(f"  BŁĄD  domyślne kryterium: {atrapa.kryteria[0]}")
    else:
        print(f"  ok    domyślne kryterium bez UNSEEN: {atrapa.kryteria[0]}")

    skrzynka, atrapa = skrzynka_z_atrapa(5)
    skrzynka.nowe(dni=120, tylko_nieprzeczytane=True, limit=0)
    if "UNSEEN" not in atrapa.kryteria[0]:
        bledy.append("tylko_nieprzeczytane=True nie dodaje UNSEEN")
        print(f"  BŁĄD  kryterium: {atrapa.kryteria[0]}")
    else:
        print("  ok    tylko_nieprzeczytane=True dodaje UNSEEN")

    # --- draft: data z rzeczywistego zapisu do skrzynki ---
    #
    # Trzy gotowe drafty padły na prawdziwej poczcie z `ValueError: date_time
    # must be aware`. Nowsze wersje Pythona odrzucają datę bez strefy czasowej,
    # starsze ją przyjmowały, więc błąd pojawił się dopiero po zmianie
    # interpretera — i to na ostatnim kroku, po klasyfikacji, ekstrakcji
    # i wygenerowaniu odpowiedzi. Cała praca szła do kosza przy zapisie.
    skrzynka, atrapa = skrzynka_z_atrapa(1)
    skrzynka._foldery = []
    skrzynka._wczytaj_foldery()
    oryginal = skrzynka.nowe(dni=120, limit=0)[0]
    folder = skrzynka.wstaw_draft(oryginal, "Re: test", "Treść odpowiedzi.")

    if not atrapa.dodane:
        bledy.append("wstaw_draft nic nie dodał do skrzynki")
        print("  BŁĄD  draft nie został dodany")
    else:
        _, flagi, data, surowy = atrapa.dodane[0]
        print(f"  ok    draft zapisany do {folder!r}, data: {data}")
        if "\\Draft" not in flagi:
            bledy.append(f"draft bez flagi Draft: {flagi}")
            print(f"  BŁĄD  flagi draftu: {flagi}")
        else:
            print("  ok    draft ma flagę \\Draft")
        # Strefa czasowa w dacie: imaplib wymaga daty świadomej strefy
        # i formatuje ją z przesunięciem, np. "+0100".
        if not any(z in data for z in ("+", "-")) or data.count(":") < 2:
            bledy.append(f"data draftu bez strefy czasowej: {data}")
            print(f"  BŁĄD  data bez strefy: {data}")
        else:
            print("  ok    data draftu ma strefę czasową")
        if b"Re: test" not in surowy:
            bledy.append("temat nie trafił do draftu")
            print("  BŁĄD  brak tematu w draftcie")
        else:
            print("  ok    temat i treść są w draftcie")

    # Podpis dokłada aplikacja, nie model. Bez tego model zostawiał w treści
    # "[DO UZUPEŁNIENIA: imię]" w każdej odpowiedzi — do poprawiania ręcznie.
    skrzynka, atrapa = skrzynka_z_atrapa(1)
    skrzynka._foldery = []
    skrzynka._wczytaj_foldery()
    oryginal = skrzynka.nowe(dni=120, limit=0)[0]
    skrzynka.wstaw_draft(oryginal, "Re: test", "Treść odpowiedzi.",
                         podpis="Pozdrawiam\nMichał")
    surowy = atrapa.dodane[-1][3].decode("utf-8", errors="replace")
    if "Michał" not in surowy:
        bledy.append("podpis z konfiguracji nie trafił do draftu")
        print("  BŁĄD  podpis nie trafił do draftu")
    else:
        print("  ok    podpis z konfiguracji jest w draftcie")
    if surowy.count("Treść odpowiedzi.") != 1:
        bledy.append("treść draftu zduplikowana albo zgubiona")
        print("  BŁĄD  treść draftu wystąpiła inną liczbę razy niż raz")
    else:
        print("  ok    treść draftu nietknięta")

    print()
    if bledy:
        print(f"BŁĘDY: {len(bledy)}")
        for blad in bledy:
            print(f"  - {blad}")
        return 1
    print("Wszystkie przypadki przeszły.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
