# Pokrycie: co produkcyjny schemat próbuje wyciągnąć, a czego nie

Stan na 7 listopada 2026, wieczór. Powstało z pierwszego przebiegu harnessu
przeciw kodowi produkcyjnemu.

**Dlaczego ten plik istnieje.** Gold obejmuje 237 pól wymaganych w 101 ścieżkach
kanonicznych. Produkcyjny schemat `Uczestnik` celuje w pola formularza
zgłoszeniowego i obejmuje ich część. Raport z harnessu podany bez tej informacji
mówiłby „trafność 3%" i byłby liczbą nie na temat: schemat nie pudłuje w tych
polach, on ich nie próbuje wypełnić.

## Co harness odsłonił w kodzie

Trzy rzeczy, każda naprawiona 7 listopada wieczorem:

**1. Brakowało dwóch tras i całej flagi bezpieczeństwa.** `TypMaila` nie miał
odpowiednika dla `sprawa_trudna` (4 wiadomości w korpusie) ani `biznes` (3).
Rezygnacja i reklamacja wpadały jako `uczestnik` i dostawały **automatyczny
projekt odpowiedzi** — czyli dokładnie `BRAK_FLAGI_DO_CZLOWIEKA`, najdroższy
błąd w tym systemie. Doszły oba typy, flaga `do_czlowieka` z listą zamkniętą
11 warunków w prompcie oraz reguła, że flaga wyłącza draft.

**2. Schemat wyciągał KTO się zgłasza, ale nie CZEGO chce.** Harness wypełniał
`wyjazd.kierunek` i `wyjazd.termin_opis` w 22 miejscach na 40 wiadomościach,
produkcja w żadnym — nie miała takich pól. Dla biura podróży to centralny fakt
zgłoszenia. Doszło sześć pól: kierunek, termin opisowy, data od, data do, budżet, NIP.

**3. `etykiety.json` miało trasę bez definicji.** Etykiety `rezerwacja_*`
mapowały się na trasę `rezerwacja`, której nie było w `zgrubne` — każde
potwierdzenie od dostawcy wychodziło jako trasa nieprzypisana. Dopisana.

## Ścieżki, które produkcja wypełnia

| ścieżka kanoniczna | pole w `Uczestnik` | kto ustala |
|---|---|---|
| `kontakt.email` | `email` | regex z walidacją |
| `kontakt.telefon` | `telefon` | regex z walidacją |
| `kontakt.imie_nazwisko` | `imie` + `nazwisko` | model |
| `kontakt.organizacja` | `nazwa_firmy` | model |
| `kontakt.kraj` | `kraj_region` | model |
| `uczestnicy[0].adres` | `ulica` + `kod_pocztowy` + `miasto` | model |
| `uczestnicy[0].adres_kod_pocztowy` | `kod_pocztowy` | regex |
| `uczestnicy[0].pesel` | `pesel` | regex z sumą kontrolną |
| `uczestnicy[0].dokument` | `numer_dokumentu` | model |
| `zgloszenie.liczba_osob` | `liczba_osob` | model, domyślnie 1 |
| `zgloszenie.budzet` | `budzet` | model |
| `wyjazd.kierunek` | `wyjazd_kierunek` | model |
| `wyjazd.termin_opis` | `wyjazd_termin` | model |
| `wyjazd.data_od` | `wyjazd_data_od` | model |
| `wyjazd.data_do` | `wyjazd_data_do` | model |
| `faktura.nip` | `nip` | model |
| `wymagania.dieta` | `dodatkowe_informacje` | model |
| `wymagania.inne_osoby` | `wymagania_innych_osob` | model |

Osiemnaście ścieżek. Plus rezerwacje, które mają własny schemat `Rezerwacja`
i własny plik gold.

## Ścieżek, których produkcja nie modeluje — i dlaczego

Nie wszystkie braki są brakami. Trzy kategorie:

**Do rozważenia, bo mają zastosowanie operacyjne.** `kontakt.telefon_stacjonarny`
(3 wystąpienia w korpusie), `platnosc.kwota` i `platnosc.waluta` (po 2),
`umowa.numer` (1), `uczestnicy[0].data_urodzenia` wyciągana z PESEL-u (2),
`zgloszenie.pokoj`, `zgody.regulamin`, `zgody.marketing`. Harness wypełnia je
deterministycznie, więc dołożenie ich to praca na schemacie, nie na prompcie.

**Świadomie poza zakresem, bo należą do odłożonych modułów.** `reklamacja.*`
i `zdarzenie.rodzaj` dotyczą modułu 7 (copilot kompletności, odłożony).
`priorytet`, `decyzja_klienta`, `jezyk_odpowiedzi` to pola sterujące draftem,
których moduł 3 nie używa — draft korzysta z bazy wiedzy i historii kontaktu.

**Poza zakresem na stałe.** `system.adres_niedostarczony`, `system.kod_bledu`
dotyczą wiadomości systemowych, które trasa `nieobslugiwane` odrzuca bez
przetwarzania. `wyposazenie.aparat`, `logistyka.dolaczenie_w_trasie` to pola
jednostkowe z pojedynczych trudnych maili.

## Jak czytać raport przy tym pokryciu

Przy tym stanie schematu **cztery metryki znaczą cztery różne rzeczy**:

| metryka | czy znacząca | dlaczego |
|---|---|---|
| halucynacje | **tak, w pełni** | pola nieobjęte schematem wychodzą puste, czyli poprawnie |
| trasa (6 klas) | **tak, w pełni** | klasyfikator zwraca wszystkie potrzebne klasy |
| flaga do człowieka | **tak, w pełni** | lista zamknięta pokrywa wszystkie 11 warunków z korpusu |
| trafność pól | **tylko na podzbiorze** | licznik obejmuje ścieżki, których schemat nie próbuje |

Dlatego do zgłoszenia konkursowego trafność pól podaje się **z liczbą ścieżek
objętych schematem**, a nie jako ułamek z 237. Albo: podaje się trafność
liczoną wyłącznie po ścieżkach z tabeli powyżej.

## Co wypełnia warstwa deterministyczna, u mnie i w harnessie

`korpus/src/warstwa_regex.py` jest szerszy od produkcyjnego
`biuro/deterministyczne.py`:

| | harness | produkcja |
|---|---|---|
| e-mail, telefon, kod pocztowy, PESEL | tak | tak |
| suma kontrolna PESEL | tak | tak |
| suma kontrolna NIP | tak | **nie** |
| data urodzenia z PESEL-u | tak | nie (świadomie — zakaz wnioskowania) |
| telefon stacjonarny osobno | tak | nie |
| zakres dat, termin opisowy | tak | nie |
| kwota i waluta | tak | nie |
| numer umowy | tak | nie |
| kierunek z listy zamkniętej | tak, z ostrzeżeniem | nie |

Na 40 wiadomościach harness wypełnia 61 pól bez listy kierunków.
**Przeniesienie tej warstwy do produkcji jest najtańszym dostępnym ulepszeniem
jakości** — kod jest napisany i ma 18 przypadków testowych. Nie zrobione jeszcze,
bo wymaga uzgodnienia, które z tych pól faktycznie wchodzą do schematu, a które
tylko zaśmiecą prompt.

## Czego ten harness nie zmierzy

Powtórzone z `README.md` harnessu, bo przy każdej liczbie trzeba to napisać:

- korpus jest **syntetyczny**, pisany pod trudne przypadki, nie pod rozkład sezonu
- **40 wiadomości**; dla wyniku 100% przedział ufności sięga w dół do około 91%
- **żaden PESEL w korpusie nie ma poprawnej sumy kontrolnej**, więc statystyki
  wyłapywania literówek w prawdziwych numerach z tego zestawu nie da się policzyć
- połowa wiadomości wymaga człowieka, bo tak została zbudowana — czułość flagi
  jest zmierzona na próbie wzbogaconej celowo

To test regresji i zestaw przypadków brzegowych. Liczba podawana jako skuteczność
wdrożenia musi pochodzić z prawdziwej skrzynki.
