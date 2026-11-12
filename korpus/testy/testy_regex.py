import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'src'))
import warstwa_regex as wr

PRZYPADKI = [
    # (tekst, oczekiwany pesel, oczekiwany status pesel, oczekiwany telefon)
    ("PESEL: 44051401358, tel 602000000", "44051401358", "zla_suma", "602000000"),
    ("44000001357 to mój pesel, dzwońcie 602000000", "44000001357", "ok", "602000000"),
    ("tel 602000000, bez pesela", None, "brak", "602000000"),
    ("PESEL 85091204, tel 602000001", None, "zly_ksztalt", "602000001"),
    ("nie mam przy sobie peselu, telefon 602000002", None, "brak", "602000002"),
    ("telefon 22 000 00 01 (domowy), komorka 602 000 003", None, "brak", "602000003"),
    ("numer umowy 884102, prosze o zwrot", None, "brak", None),
    ("tel. +48 602 000 004", None, "brak", "602000004"),
    ("telefon 000000000", None, "brak", None),
]

bledy = 0
for tekst, exp_pesel, exp_status, exp_tel in PRZYPADKI:
    w = wr.przetworz(tekst)
    pesel = w["pola"].get("uczestnicy[0].pesel")
    status = w["statusy"].get("uczestnicy[0].pesel", "brak")
    tel = w["pola"].get("kontakt.telefon")
    ok = (pesel == exp_pesel) and (status == exp_status) and (tel == exp_tel)
    if not ok:
        bledy += 1
    print(("OK  " if ok else "BŁĄD") + f"  {tekst[:46]:<48}")
    if not ok:
        print(f"        pesel {pesel!r}/{status!r} (oczekiwano {exp_pesel!r}/{exp_status!r})"
              f"  tel {tel!r} (oczekiwano {exp_tel!r})")

print()
print(f"{len(PRZYPADKI) - bledy}/{len(PRZYPADKI) } przypadków przeszło")


# --- przypadki znalezione na korpusie 40 maili ---------------------------------

PRZYPADKI_2 = [
    # (tekst, ścieżka, oczekiwana wartość)
    ("Kowalska 3, ur. 01.01.1970, tel 602 000 005", "wyjazd.data_od", None),
    ("Kowalska 3, ur. 01.01.1970, tel 602 000 005", "uczestnicy[0].data_urodzenia", "1970-01-01"),
    ("Kowalska 29, 602 000 006, ur. 01.01.1970", "wyjazd.data_od", None),
    ("Reklamacja dotyczy wyjazdu 21-26.09.2026", "wyjazd.data_od", "2026-09-21"),
    ("uczyłam się sama z YouTube'a", "zgloszenie.liczba_osob", None),
    ("prowadzący zajmował się dwiema osobami, reszta radziła sobie sama",
     "zgloszenie.liczba_osob", None),
    ("jadę prawdopodobnie sama, ale może dołączy siostra", "zgloszenie.liczba_osob", 1),
    ("chcielibyśmy zapisać się dwie osoby", "zgloszenie.liczba_osob", 2),
    ("Nowe zgłoszenie z formularza\nE-mail: ewa.k@\nTelefon: 000000000",
     "kontakt.email", None),
]

bledy_2 = 0
print()
for tekst, sciezka, oczekiwana in PRZYPADKI_2:
    w = wr.przetworz(tekst, "formularz@biuro-przykladowe.example")
    otrzymana = w["pola"].get(sciezka)
    ok = otrzymana == oczekiwana
    if not ok:
        bledy_2 += 1
    print(("OK  " if ok else "BŁĄD") + f"  {sciezka:<30} {tekst[:34]!r}")
    if not ok:
        print(f"        otrzymano {otrzymana!r}, oczekiwano {oczekiwana!r}")

print()
print(f"{len(PRZYPADKI_2) - bledy_2}/{len(PRZYPADKI_2)} przypadków z korpusu przeszło")
sys.exit(1 if (bledy or bledy_2) else 0)
