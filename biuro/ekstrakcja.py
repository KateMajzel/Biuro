"""Ekstrakcja danych zgłoszeniowych: warstwa deterministyczna plus model.

Dwa tryby, przełączane w config.yaml. Który jest lepszy, zależy od ROZMIARU
modelu, nie od upodobań - to wniosek z pomiaru 7 XI 2026, nieoczywisty i
niemożliwy do wydedukowania z zasad:

    wariant        pola krytyczne   zgłoszenia bez poprawek
    7B hybryda     100%             100%
    7B llm         100%             100%  (p95 dwa razy dłuższe)
    4.5B llm        98,1%            83,3%
    4.5B hybryda    96,3%            66,7%
    sam regex       44,4%             0%

Zabieranie pól ze schematu pomaga 7B i szkodzi 4.5B. Przy zmianie modelu na
mniejszy trzeba przestawić tryb na "llm".

Wiersz z samym regexem jest w tej tabeli najważniejszy: pokazuje, że model
wykonuje pracę nieredukowalną, a warstwa deterministyczna obsługuje tylko to,
co ma sztywny format.

Zestaw pomiarowy: 12 zgłoszeń SYNTETYCZNYCH, pisanych pod schemat pól. Przy tej
liczebności przedział ufności dla 100% sięga w dół do około 75%. Te liczby mówią,
że pipeline działa, a nie jak zachowa się na prawdziwej poczcie.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, create_model

from .config import cfg, prompt
from .deterministyczne import WynikDeterministyczny, ustal
from .llm import chat_json
from .schemas import DaneWrazliwe, Uczestnik

# Pola, które warstwa deterministyczna umie ustalić z walidacją.
# Tylko te mogą zostać wyprowadzone ze schematu w trybie hybrydowym.
# `data_urodzenia` doszła po dopisaniu walidacji kalendarzowej: warstwa
# deterministyczna sprawdza, czy taka data istnieje, i czy zgadza się z datą
# zakodowaną w numerze PESEL. Model tego nie policzy — i nie powinien,
# bo prompt zabrania mu wnioskowania daty z numeru.
POLA_DETERMINISTYCZNE = ("pesel", "telefon", "email", "kod_pocztowy", "data_urodzenia")


@dataclass
class RaportEkstrakcji:
    uczestnik: Uczestnik
    tryb: str
    pola_z_regexu: list[str] = field(default_factory=list)
    pola_z_modelu: list[str] = field(default_factory=list)
    do_weryfikacji: list[str] = field(default_factory=list)
    odrzucone: list[str] = field(default_factory=list)
    # Dane do umowy, złożone z pól wrażliwych. `Uczestnik` nie ma daty
    # urodzenia, a warstwa deterministyczna ją ustala i waliduje — bez tego
    # pola wartość ginęła między warstwami. PESEL z formularza też ginął:
    # ścieżka formularza zapisywała wyłącznie zgłoszenie i nigdy nie wołała
    # zapisu danych wrażliwych, więc umowy nie dało się wystawić dla żadnego
    # zgłoszenia przyszłego tą drogą — czyli dla całego normalnego ruchu.
    wrazliwe: "DaneWrazliwe | None" = None

    def podsumowanie(self) -> str:
        czesci = [f"tryb={self.tryb}"]
        if self.pola_z_regexu:
            czesci.append(f"regex: {', '.join(self.pola_z_regexu)}")
        if self.pola_z_modelu:
            czesci.append(f"model: {', '.join(self.pola_z_modelu)}")
        if self.do_weryfikacji:
            czesci.append(f"DO WERYFIKACJI: {', '.join(self.do_weryfikacji)}")
        return " | ".join(czesci)


def _schemat_bez(pola_do_usuniecia: set[str]) -> type[BaseModel]:
    """Buduje wariant schematu Uczestnika bez wskazanych pól.

    Model nie może wpisać wartości do pola, którego nie widzi. To jest cała
    mechanika trybu hybrydowego - i jednocześnie jej pułapka: pole zabrane
    bez pokazania jego wartości zostawia wolną rubrykę, w którą model wsadza
    coś innego. Dlatego wartości zawsze wędrują do promptu osobnym blokiem.
    """
    pola: dict[str, Any] = {}
    for nazwa, info in Uczestnik.model_fields.items():
        if nazwa in pola_do_usuniecia:
            continue
        pola[nazwa] = (info.annotation, info)
    return create_model("UczestnikCzesciowy", **pola)


def zloz_wrazliwe(
    wynik_det: WynikDeterministyczny, uczestnik: Uczestnik
) -> DaneWrazliwe:
    """Dane do umowy: pola wrażliwe z obu warstw w jednym obiekcie.

    Składane tutaj, bo tylko tutaj widać jednocześnie wynik warstwy
    deterministycznej i wynik modelu. PESEL, data urodzenia i kod pocztowy
    pochodzą wyłącznie z walidowanego regexu — modelowi nie wolno ich zgadywać
    ani wyliczać daty z numeru.

    Osobna funkcja, bo bez niej ta logika istniała tylko w środku `ekstrahuj`,
    czyli za wywołaniem modelu, i nie dawała się przetestować. Skutek:
    rozjechane wersje `ekstrakcja.py` i `pipeline.py` przeszły pełny zestaw
    testów, a wywaliły się na pierwszym prawdziwym mailu.
    """
    det = wynik_det.wartosci()
    return DaneWrazliwe(
        pesel=det.get("pesel"),
        data_urodzenia=det.get("data_urodzenia"),
        numer_dokumentu=uczestnik.numer_dokumentu,
        ulica=uczestnik.ulica,
        kod_pocztowy=det.get("kod_pocztowy") or uczestnik.kod_pocztowy,
        miasto=uczestnik.miasto,
        imie=uczestnik.imie,
        nazwisko=uczestnik.nazwisko,
    )


def ekstrahuj(tekst: str, tryb: str | None = None) -> RaportEkstrakcji:
    k = cfg()
    tryb = tryb or k.get("ekstrakcja.tryb", "hybryda")
    wynik_det: WynikDeterministyczny = ustal(
        tekst, flaguj_bledna_sume=k.get("ekstrakcja.flaguj_bledna_sume", True)
    )

    blok_przypisanych = wynik_det.blok_dla_modelu()
    tresc_promptu = f"{prompt('ekstrakcja')}\n\n### Treść wiadomości\n{tekst}"
    if blok_przypisanych:
        tresc_promptu = (
            f"{prompt('ekstrakcja')}\n\n{blok_przypisanych}\n\n"
            f"### Treść wiadomości\n{tekst}"
        )

    if tryb == "hybryda" and wynik_det.pola():
        do_usuniecia = wynik_det.pola() & set(POLA_DETERMINISTYCZNE)
        schemat = _schemat_bez(do_usuniecia)
        czesciowy = chat_json(tresc_promptu, schemat, maly=False)
        dane = czesciowy.model_dump()
    else:
        # tryb llm: model widzi pełny schemat, regex nadal nadpisuje po fakcie
        do_usuniecia = set()
        pelny = chat_json(tresc_promptu, Uczestnik, maly=False)
        dane = pelny.model_dump()

    # Warstwa deterministyczna ma pierwszeństwo ZAWSZE, też w trybie llm.
    # Zwalidowana cyfra bije cyfrę przepisaną przez model.
    #
    # Nadpisujemy tylko pola, które schemat zna. Warstwa deterministyczna
    # ustala też `data_urodzenia`, której `Uczestnik` nie ma — bez tego
    # warunku klucz wchodziłby do słownika i był po cichu odrzucany przy
    # walidacji. Pydantic nadmiarowe klucze ignoruje, więc taki błąd nie
    # zgłasza się sam i siedzi w kodzie, dopóki ktoś nie doda pola.
    for nazwa, wartosc in wynik_det.wartosci().items():
        if nazwa in Uczestnik.model_fields:
            dane[nazwa] = wartosc

    # Tu było wymuszenie `liczba_osob = 1`, gdy model nie podał liczby.
    # Zdjęte: ekstrakcja ma zwracać to, co jest w wiadomości. Milczenie
    # klienta o liczbie osób to brak danej, nie liczba jeden. Założenie
    # „jedna osoba" stosują odbiorcy tego pola (umowa, arkusz, wykaz UFG,
    # odprawa) przez `or 1`, więc zachowanie produkcyjne się nie zmienia —
    # zmienia się to, że w bazie widać różnicę między liczbą podaną przez
    # klienta a przyjętą przez nas.
    uczestnik = Uczestnik.model_validate(dane)

    # Jedynka była tu wykluczana, bo `liczba_osob` dostawała ją zawsze
    # z wymuszenia powyżej i zaśmiecałaby listę pól wypełnionych przez model.
    # Po zdjęciu wymuszenia jedynka jest zwykłą wartością i jej ukrywanie
    # kłamałoby w raporcie — a przy okazji ukrywało każde inne pole o wartości
    # 1, bo w Pythonie `True == 1`.
    pola_z_modelu = [
        nazwa for nazwa, wartosc in dane.items()
        if wartosc not in (None, "") and nazwa not in wynik_det.pola()
    ]

    return RaportEkstrakcji(
        uczestnik=uczestnik,
        tryb=tryb if do_usuniecia else f"{tryb} (bez pól do wyprowadzenia)",
        pola_z_regexu=sorted(wynik_det.pola()),
        pola_z_modelu=sorted(pola_z_modelu),
        do_weryfikacji=list(wynik_det.do_weryfikacji),
        odrzucone=list(wynik_det.odrzucone),
        wrazliwe=zloz_wrazliwe(wynik_det, uczestnik),
    )
