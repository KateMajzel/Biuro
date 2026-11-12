#!/usr/bin/env python3
"""Testy zachowania przy urwanej odpowiedzi modelu.

    python testy/test_urwany_json.py

Powód powstania: przebieg poczty skończył się zerem draftów, a w logu było
„Model nie zwrócił poprawnego JSON po 2 próbach: EOF while parsing a string".
Odpowiedź modelu nie była zła — była ucięta na limicie tokenów. Ponowna próba
dostawała ten sam limit, więc ucinała się w tym samym miejscu, a do promptu
dochodziła jeszcze urwana poprzednia odpowiedź.

Tu sprawdzamy, że przy urwaniu program zwiększa budżet i zaczyna od czystego
promptu, a przy zwykłym błędzie schematu nadal prosi model o poprawkę.
"""

import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KORZEN))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import baza_testowa  # noqa: E402,F401  — izolacja konfiguracji

from pydantic import BaseModel  # noqa: E402

from biuro import llm  # noqa: E402


class Odpowiedz(BaseModel):
    tresc: str


def main() -> int:
    bledy = 0

    def sprawdz(nazwa: str, warunek: bool, szczegol: str = "") -> None:
        nonlocal bledy
        if warunek:
            print(f"OK    {nazwa}")
        else:
            bledy += 1
            print(f"BŁĄD  {nazwa}   {szczegol}")

    # --- rozpoznawanie urwania ---------------------------------------------
    blad_urwania = ValueError("Invalid JSON: EOF while parsing a string at line 25")
    blad_schematu = ValueError("1 validation error for Odpowiedz: field required")

    sprawdz("done_reason=length to urwanie",
            llm._urwane({"done_reason": "length"}, blad_schematu))
    sprawdz("EOF w treści błędu to urwanie",
            llm._urwane({}, blad_urwania))
    sprawdz("niedomknięty napis to urwanie",
            llm._urwane({}, ValueError("Unterminated string starting at")))
    sprawdz("brak pola to nie urwanie",
            not llm._urwane({"done_reason": "stop"}, blad_schematu))

    # --- podwajanie budżetu -------------------------------------------------
    # Podstawiamy _zadanie, żeby nie odpytywać modelu. Pierwsze dwa wywołania
    # udają ucięcie, trzecie zwraca poprawny JSON.
    wywolania: list[dict] = []
    oryginalne = llm._zadanie

    def atrapa(sciezka: str, ladunek: dict) -> dict:
        # kopia, bo chat_json dopisuje do tej samej listy wiadomości
        wywolania.append({**ladunek, "messages": list(ladunek["messages"])})
        if len(wywolania) < 3:
            return {"message": {"content": '{"tresc": "zaczyna sie i nie koncz'},
                    "done_reason": "length"}
        return {"message": {"content": '{"tresc": "cala odpowiedz"}'},
                "done_reason": "stop"}

    llm._zadanie = atrapa
    try:
        wynik = llm.chat_json("pytanie", Odpowiedz, proby=3, limit_tokenow=500)
    finally:
        llm._zadanie = oryginalne

    sprawdz("po urwaniach zwraca poprawny wynik",
            wynik.tresc == "cala odpowiedz", str(wynik))
    budzety = [w["options"]["num_predict"] for w in wywolania]
    sprawdz("budżet tokenów rośnie przy każdym urwaniu",
            budzety == [500, 1000, 2000], str(budzety))
    dlugosci = [len(w["messages"]) for w in wywolania]
    sprawdz("prompt nie puchnie o urwane odpowiedzi",
            dlugosci == [1, 1, 1], str(dlugosci))

    # --- zwykły błąd schematu ----------------------------------------------
    # Tu odpowiedź jest kompletna, tylko nie pasuje do schematu. Wtedy prośba
    # o poprawkę ma sens i prompt ma prawo rosnąć, a budżet zostaje ten sam.
    wywolania.clear()

    def atrapa_schemat(sciezka: str, ladunek: dict) -> dict:
        # kopia, bo chat_json dopisuje do tej samej listy wiadomości
        wywolania.append({**ladunek, "messages": list(ladunek["messages"])})
        if len(wywolania) < 2:
            return {"message": {"content": '{"co_innego": 1}'},
                    "done_reason": "stop"}
        return {"message": {"content": '{"tresc": "poprawione"}'},
                "done_reason": "stop"}

    llm._zadanie = atrapa_schemat
    try:
        wynik = llm.chat_json("pytanie", Odpowiedz, proby=3, limit_tokenow=500)
    finally:
        llm._zadanie = oryginalne

    sprawdz("po poprawce schematu zwraca wynik",
            wynik.tresc == "poprawione", str(wynik))
    budzety = [w["options"]["num_predict"] for w in wywolania]
    sprawdz("przy błędzie schematu budżet się nie zmienia",
            budzety == [500, 500], str(budzety))
    dlugosci = [len(w["messages"]) for w in wywolania]
    sprawdz("przy błędzie schematu prompt rośnie o prośbę o poprawkę",
            dlugosci == [1, 3], str(dlugosci))

    # --- sufit --------------------------------------------------------------
    # Urwania nie mogą zwiększać budżetu w nieskończoność: po przekroczeniu
    # sufitu program ma się poddać z czytelnym komunikatem, a nie mielić.
    wywolania.clear()

    def atrapa_zawsze_urwane(sciezka: str, ladunek: dict) -> dict:
        # kopia, bo chat_json dopisuje do tej samej listy wiadomości
        wywolania.append({**ladunek, "messages": list(ladunek["messages"])})
        return {"message": {"content": '{"tresc": "urwane'},
                "done_reason": "length"}

    llm._zadanie = atrapa_zawsze_urwane
    try:
        llm.chat_json("pytanie", Odpowiedz, proby=3, limit_tokenow=4096)
        sprawdz("przy stałym urwaniu podnosi BladModelu", False, "nie podniósł")
    except llm.BladModelu as e:
        sprawdz("przy stałym urwaniu podnosi BladModelu", True)
        sprawdz("komunikat mówi, że odpowiedź się urywała",
                "urywał" in str(e), str(e)[:90])
    finally:
        llm._zadanie = oryginalne

    print()
    if bledy:
        print(f"BŁĘDY: {bledy}")
        return 1
    print("Wszystkie przypadki przeszły.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
