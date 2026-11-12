#!/usr/bin/env python3
"""Przerabia wzorzec umowy w .docx na szablon docxtpl.

Wzorzec ma pola w nawiasach kwadratowych, np. [pełna nazwa firmy]. Ten skrypt
podmienia je na znaczniki jinja, np. {{ firma_nazwa }}, w konkretnych miejscach:
komórki tabel po współrzędnych i wybrane akapity po numerze.

Odpalasz raz, po każdej zmianie wzorca umowy:

    python skrypty/zbuduj_szablon_umowy.py wsad/umowa_zrodlo.docx

Wynik ląduje w szablony/umowa.docx.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docx import Document  # noqa: E402

# --- komórki tabel: (nr tabeli, nr wiersza) -> treść komórki wartości ---
KOMORKI: dict[tuple[int, int], str] = {
    # tabela 0: organizator
    (0, 1): "{{ firma_nazwa }}",
    (0, 2): "{{ firma_adres }}",
    (0, 3): "{{ firma_nip }} / {{ firma_regon }}",
    (0, 4): "Rejestr Organizatorów Turystyki i Przedsiębiorców Ułatwiających "
            "Nabywanie Powiązanych Usług Turystycznych, nr {{ firma_rejestr_nr }}, "
            "organ: Marszałek Woj. {{ firma_rejestr_organ }}",
    (0, 5): "tel. {{ firma_telefon }}, e-mail {{ firma_email }}, {{ firma_www }}",
    # tabela 1: podróżny
    (1, 1): "{{ p_imie }} {{ p_nazwisko }}",
    (1, 2): "{{ p_pesel }} / {{ p_data_urodzenia }}",
    (1, 3): "{{ p_adres }}",
    (1, 4): "{{ p_telefon }} / {{ p_email }}",
    (1, 5): "{{ p_dokument }}",
    # tabela 2: impreza
    (2, 1): "{{ w_nazwa }}",
    (2, 2): "{{ w_miejsce }}",
    (2, 3): "od {{ w_termin_od }} do {{ w_termin_do }}",
    (2, 4): "{{ w_dni }} dni, {{ w_noclegi }} noclegów",
    (2, 6): "od {{ w_uczestnicy_min }} do {{ w_uczestnicy_max }} osób",
    (2, 7): "polski (zajęcia i opieka pilota); {{ w_jezyk_lokalni }}",
    # tabela 3: transport
    (3, 1): "{{ w_transport_rodzaj }}",
    (3, 2): "{{ w_wyjazd_miejsce }} — {{ w_wyjazd_data }}",
    (3, 3): "{{ w_powrot_miejsce }} — {{ w_powrot_data }}",
    (3, 4): "{{ w_postoje }}",
    (3, 5): "{{ w_transport_na_miejscu }}",
    # tabela 4: zakwaterowanie
    (4, 1): "{{ w_obiekt }}",
    (4, 2): "{{ w_obiekt_kategoria }}",
    (4, 3): "{{ w_pokoje }}",
    (4, 4): "{{ w_doplata_1os }}",
    # tabela 5: cena
    (5, 1): "{{ w_cena }} {{ w_waluta }}",
    (5, 2): "{{ w_doplata_1os }}",
    (5, 3): "{{ w_do_zaplaty }} {{ w_waluta }}",
    (5, 4): "{{ w_termin_zaplaty_dni }} dni od zawarcia umowy, tj. do {{ w_termin_zaplaty_data }}",
    # tabela 6: zabezpieczenie finansowe
    (6, 1): "{{ g_forma }}",
    (6, 2): "{{ g_podmiot }}",
    (6, 3): "{{ g_adres_kontakt }}",
    (6, 4): "{{ g_numer }}, {{ g_suma }}",
    (6, 5): "od {{ g_od }} do {{ g_do }}",
    # tabela 7: ubezpieczenie
    (7, 1): "{{ u_kl }}",
    (7, 2): "{{ u_nnw }}",
    (7, 3): "{{ u_bagaz }}",
    (7, 4): "{{ u_assistance }}",
    (7, 5): "{{ u_sprzet }}",
}

# --- akapity: nr akapitu -> lista (wzorzec do znalezienia, zamiennik) ---
AKAPITY: dict[int, list[tuple[str, str]]] = {
    0: [("[…/…/20…]", "{{ nr_umowy }}")],
    1: [("[miejscowość]", "{{ miejscowosc }}"), ("[data]", "{{ data_zawarcia }}")],
    7: [
        ("[imię i nazwisko pilota/rezydenta]", "{{ w_pilot_imie }}"),
        ("[numer]", "{{ w_pilot_telefon }}"),
        ("[…]", "{{ w_pilot_komunikator }}"),
        ("[adres]", "{{ w_pilot_email }}"),
    ],
    12: [("[…]", "{{ w_miejsce_rozpoczecia }}")],
    16: [("[Zajęcia warsztatowe — liczba sesji, zakres tematyczny, prowadzący]",
          "{{ w_program_warsztaty }}")],
    17: [("[Plenery fotograficzne — liczba, lokalizacje]", "{{ w_program_plenery }}")],
    18: [("[Przeglądy zdjęć / omówienia / konsultacje]", "{{ w_program_przeglady }}")],
    19: [("[Bilety wstępu, przewodnicy lokalni, licencje fotograficzne]",
          "{{ w_program_wstepy }}")],
    24: [("[Przeloty do miejsca zbiórki, wszystkie posiłki i napoje, wstępy poza "
          "programem, wypożyczenie sprzętu fotograficznego, wydatki własne, dopłata "
          "do pokoju 1-os.]", "{{ w_swiadczenia_nieobjete }}")],
    26: [("[jest / nie jest]", "{{ w_dostepnosc }}"),
         ("[opis: np. kilkukilometrowych przejść w terenie, wchodzenia na punkty "
          "widokowe, noszenia sprzętu, pobytu na zimnie przez […] godzin]",
          "{{ w_dostepnosc_opis }}")],
    28: [("[nazwa banku]", "{{ bank_nazwa }}"),
         ("[numer rachunku]", "{{ bank_numer }}"),
         ("[nie są / są]", "{{ rachunek_powierniczy }}")],
    33: [("[np. paszportu ważnego co najmniej […] miesięcy od daty powrotu / dowodu "
          "osobistego]", "{{ w_dokumenty_wymagane }}"),
         ("[np. wiza nie jest wymagana przy pobycie do […] dni / wymagana jest "
          "elektroniczna autoryzacja […], którą Podróżny uzyskuje samodzielnie]",
          "{{ w_wizy }}"),
         ("[np. brak obowiązkowych szczepień; zalecane […]]", "{{ w_sanitarne }}")],
    38: [("[dieta, pokój na parterze, wypożyczenie […], inne — albo: nie zgłoszono]",
          "{{ p_wymagania_specjalne }}")],
    43: [("[informacja, czy ubezpieczenie z §8 obejmuje sprzęt i do jakiej kwoty]",
          "{{ u_sprzet_info }}")],
    63: [("[adres]", "{{ firma_email }}")],
    69: [("[liczba]", "{{ w_uczestnicy_min }}")],
    83: [("[numer]", "{{ w_pilot_telefon }}"), ("[e-mail]", "{{ firma_email }}")],
    88: [("[adres]", "{{ firma_email }}")],
    97: [("Marszałek Woj. […]", "Marszałek Woj. {{ firma_rejestr_organ }}")],
    100: [("[nazwa ubezpieczyciela]", "{{ u_ubezpieczyciel }}"),
          ("[numer]", "{{ u_polisa }}")],
    102: [("[wykupuje / nie wykupuje]", "{{ u_rezygnacja }}")],
    105: [("[kraj]", "{{ w_kraj_poza_eog }}")],
    106: [("[e-mail]", "{{ firma_email }}")],
    109: [("[wyraża / nie wyraża]", "{{ p_zgoda_wizerunek }}")],
}


def podmien_w_akapicie(akapit, pary: list[tuple[str, str]]) -> int:
    """Podmienia tekst w akapicie, zachowując jego styl.

    Tekst sklejamy ze wszystkich przebiegów, podmieniamy, a wynik wkładamy
    do pierwszego przebiegu. Formatowanie wewnątrz akapitu (pogrubienia w
    środku zdania) przepada, ale styl akapitu zostaje. Dla prozy prawnej
    to akceptowalny kompromis.
    """
    pelny = "".join(r.text for r in akapit.runs)
    zmieniony = pelny
    trafienia = 0
    for szukaj, zamien in pary:
        # tolerujemy różnice w spacjach i w typie łącznika
        wzorzec = re.escape(szukaj).replace(r"\ ", r"\s+").replace("—", "[—-]")
        nowy, ile = re.subn(wzorzec, zamien.replace("\\", r"\\"), zmieniony)
        if ile:
            zmieniony = nowy
            trafienia += ile
    if zmieniony == pelny or not akapit.runs:
        return 0
    akapit.runs[0].text = zmieniony
    for r in akapit.runs[1:]:
        r.text = ""
    return trafienia


def ustaw_komorke(komorka, tekst: str) -> None:
    """Wpisuje treść do komórki, zachowując formatowanie pierwszego przebiegu."""
    akapit = komorka.paragraphs[0]
    if akapit.runs:
        akapit.runs[0].text = tekst
        for r in akapit.runs[1:]:
            r.text = ""
    else:
        akapit.add_run(tekst)
    for extra in komorka.paragraphs[1:]:
        for r in extra.runs:
            r.text = ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("zrodlo", help="wzorzec umowy w .docx")
    parser.add_argument("--wyjscie", default="szablony/umowa.docx")
    args = parser.parse_args()

    korzen = Path(__file__).resolve().parent.parent
    dokument = Document(args.zrodlo)

    # tabele
    #
    # Mapowanie idzie po współrzędnych (numer tabeli, numer wiersza), bo
    # etykiety w rubrykach wzorca się powtarzają. Słaby punkt: dopisanie
    # jednego wiersza we wzorcu przesuwa wszystko poniżej i dane trafiają
    # do niewłaściwych rubryk — po cichu, bo podmiana i tak się udaje.
    #
    # Stąd sprawdzenie: każda komórka, którą nadpisujemy, musi zawierać
    # pole w nawiasie kwadratowym albo być pusta. Komórka z gotową treścią
    # oznacza, że współrzędne się rozjechały ze wzorcem, i wtedy przerywamy
    # zamiast wyprodukować umowę z nazwiskiem w rubryce „Postoje".
    zmienione_komorki = 0
    podejrzane: list[str] = []
    for (nr_tabeli, nr_wiersza), tresc in KOMORKI.items():
        try:
            wiersz = dokument.tables[nr_tabeli].rows[nr_wiersza]
            komorka = wiersz.cells[1]
        except IndexError:
            podejrzane.append(
                f"tabela {nr_tabeli}, wiersz {nr_wiersza} — nie istnieje we wzorcu"
            )
            continue

        etykieta = wiersz.cells[0].text.strip()
        obecne = komorka.text.strip()
        if obecne and "[" not in obecne and "…" not in obecne:
            podejrzane.append(
                f"tabela {nr_tabeli}, wiersz {nr_wiersza} "
                f"({etykieta[:30]}) ma gotowa tresc: {obecne[:40]} "
                f"- mialo tam byc pole do podmiany na {tresc[:30]}"
            )
            continue

        ustaw_komorke(komorka, tresc)
        zmienione_komorki += 1

    if podejrzane:
        print("\nSZABLON NIE ZOSTAŁ ZAPISANY — współrzędne rozjechały się ze wzorcem:")
        for linia in podejrzane:
            print(f"  - {linia}")
        print("\nWe wzorcu doszedł albo zniknął wiersz w tabeli. Trzeba poprawić")
        print("tabelę KOMORKI w tym skrypcie albo przywrócić układ wzorca.")
        print("Gdyby szablon powstał z takimi współrzędnymi, dane uczestnika")
        print("trafiłyby do niewłaściwych rubryk umowy, a plik wyglądałby poprawnie.")
        return 1

    # akapity
    zmienione_akapity = 0
    for nr, pary in AKAPITY.items():
        if nr >= len(dokument.paragraphs):
            print(f"  UWAGA: nie ma akapitu {nr}")
            continue
        if podmien_w_akapicie(dokument.paragraphs[nr], pary):
            zmienione_akapity += 1
        else:
            print(f"  UWAGA: akapit {nr} bez zmian — sprawdź wzorzec")

    wyjscie = korzen / args.wyjscie
    wyjscie.parent.mkdir(parents=True, exist_ok=True)
    dokument.save(wyjscie)

    # co zostało nieobsłużone
    pozostale: list[str] = []
    for i, p in enumerate(dokument.paragraphs):
        for znalezione in re.findall(r"\[[^\]]{1,120}\]", p.text):
            pozostale.append(f"akapit {i}: {znalezione}")
    for nr_t, t in enumerate(dokument.tables):
        for nr_w, r in enumerate(t.rows):
            for c in r.cells:
                for znalezione in re.findall(r"\[[^\]]{1,120}\]", c.text):
                    pozostale.append(f"tabela {nr_t}/{nr_w}: {znalezione}")

    print(f"\nZapisano {wyjscie}")
    print(f"Podmieniono: {zmienione_komorki} komórek, {zmienione_akapity} akapitów")
    if pozostale:
        print(f"\nPola do wypełnienia RAZ, wprost w szablonie ({len(pozostale)}):")
        for linia in pozostale:
            print(f"  {linia}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
