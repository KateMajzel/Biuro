# Biuro na Bieliku — opis techniczny

Ten plik opisuje, jak program jest zbudowany, jak był mierzony i dlaczego
podjęto takie decyzje. Instrukcja uruchomienia jest w [README.md](README.md).

Wdrożenie pierwotne: **Warsztaty Arktyczne** — biuro podróży organizujące warsztaty
i wyprawy fotograficzne, wpisane do rejestru organizatorów turystyki.

## Teza

Biuro podróży przetwarza dane, których nie wolno wkleić do chmurowego czatu:
PESEL, numer paszportu, adres, informację o diecie. Małe biuro ma dziś dwa
wyjścia — przepisywać ręcznie albo podpisać umowę powierzenia z dostawcą chmury
i wysłać dane uczestników na zewnątrz. Lokalny Bielik usuwa ten wybór: dane nie
opuszczają maszyny, więc nie ma powierzenia, transferu ani pytania o podstawę
prawną.

Efekt operacyjny: **dane uczestnika wpisywane raz, a nie cztery razy**
(mail → arkusz → umowa → rejestr).

## Zakres

Dziewięć modułów wdrożonych, cztery w planie. Odłożone są opisane jako plan, nie
jako funkcje — jedno „to jeszcze nie działa" przy demo kosztuje więcej niż
uczciwa lista.

| # | Moduł | Status | Kto wykonuje |
|---|---|---|---|
| 1 | skrzynka IMAP, 11 typów wiadomości + flaga do człowieka | wdrożone | kod + model |
| 2 | ekstrakcja danych zgłoszeniowych do bazy | wdrożone | regex + model |
| 3 | drafty odpowiedzi do folderu roboczego, w tym samym wątku | wdrożone | model |
| 4 | umowa z szablonu .docx i PDF, numerowana, w rejestrze | wdrożone | tylko kod |
| 5 | odprawa przedwyjazdowa jako projekt maila | wdrożone | model |
| 6 | rejestr umów i miesięczny CSV dla UFG/TFG | wdrożone | tylko kod |
| 11 | arkusz wyjazdu: lista uczestników, rezerwacje, logistyka | wdrożone | tylko kod |
| 12 | rejestr rezerwacji z maili: lot, nocleg, samochód | wdrożone | model |
| 13 | historia kontaktu z uczestnikiem | wdrożone | tylko kod |
| — | licznik dni do deklaracji TFG | wdrożone | tylko kod |
| 7 | copilot kompletności dokumentów | plan | — |
| 8 | notatki z rozmów z plików audio | plan | — |
| 9 | dyktowanie | plan | — |
| 10 | dzienna odprawa (poza licznikiem TFG) | plan | — |

Dziewięć modułów wdrożonych, cztery w planie. Moduł 7 jest odłożony świadomie:
to jedyne zadanie, w którym błąd modelu uderza w odpowiedzialność ustawową
organizatora turystyki, a nie w wygodę. Gdy wróci, musi być jednostronny —
wypisywać „brakuje X", nigdy nie orzekać, że dokument jest kompletny.

Poza zakresem całkowicie: **czat na stronie** — jedyny moduł publiczny, czyli
jedyny, w którym pomyłka modelu zostaje w internecie zamiast czekać na
akceptację. **Aplikacja nigdy nie wysyła maila ani nie publikuje treści.**
Każda odpowiedź czeka w folderze wersji roboczych na decyzję człowieka.

## Dwa katalogi pomiarowe — co jest czym

| katalog | co mierzy | wejście | runner |
|---|---|---|---|
| `korpus/` | 43 trudne wiadomości z ground truth; cztery rozdzielone metryki | `gold/*.json` | `src/ocen.py` |
| `ewaluacja/` | warianty modelu i trybu (llm / regex / hybryda), latencja | `data/ground_truth.csv` | `run_eval.py` |

Liczby skuteczności z tabeli poniżej pochodzą z `ewaluacja/`. Flaga do człowieka,
halucynacje i trasa — z `korpus/`. To dwa osobne zestawy i nie należy mieszać
ich wyników w jednym zdaniu.

## Harness korpusowy

W `korpus/` jest korpus 43 trudnych wiadomości z ręcznie przepisanym ground
truth i narzędzie do pomiaru. **Nikt nie powinien ufać cudzym liczbom
skuteczności**, więc razem z aplikacją dostajesz narzędzie do zmierzenia jej na
własnej poczcie.

```bash
# korpus na JSONL
python korpus/src/parsuj_korpus.py \
    --zrodlo korpus/dane/maile_testowe_biuro_podrozy.txt \
             korpus/dane/maile_testowe_potwierdzenia.txt \
    --wyjscie korpus/out/maile.jsonl

# predykcje z produkcyjnego kodu (tryb regex nie wymaga Ollamy)
python korpus/adapter.py --zrodlo korpus/out/maile.jsonl \
    --wyjscie korpus/out/predykcje.jsonl --tryb hybryda

# raport
python korpus/src/ocen.py --gold korpus/gold/gold_zgloszenia.json \
    --predykcje korpus/out/predykcje.jsonl \
    --etykiety korpus/schemat/etykiety.json \
    --tryb "7B hybryda" --bledy korpus/out/bledy.csv
```

Cztery metryki rozdzielone, nigdy jedna liczba: trafność pól, halucynacje,
trasa, flaga do człowieka. **38% ocen w zestawie to pola, które muszą zostać
puste** — wstrzymanie się od odpowiedzi jest punktowane tak samo jak poprawna
wartość. Model wypełniający każde pole czymkolwiek dostanie dobrą trafność
i katastrofalny wynik na halucynacjach, a to drugie zabija wdrożenie.

Co ten harness odsłonił w kodzie i jakie ścieżki produkcja pokrywa:
**[korpus/POKRYCIE.md](korpus/POKRYCIE.md)**.

## Skuteczność

Dwie niezależne próbki, rozdzielone celowo. Przy każdej liczbie stoi, skąd jest
— mieszanie ich w jednym zdaniu dałoby liczbę, której nie da się obronić.

### Korpus 40 wiadomości z ręcznie przepisanym ground truth

Pomiar z 8 XI 2026, Bielik 7B minitron Q8, tryb hybrydowy. W kolumnie obok
wynik **samego regexu, bez modelu**: wszystko powyżej tej kolumny jest wkładem
modelu. Bez takiego punktu odniesienia zdanie „system rozpoznaje intencje" nie
znaczy nic.

| metryka | sam regex | Bielik 7B |
|---|---:|---:|
| trasa (6 klas) | 10,0% | **65,0%** (26/40) |
| flaga do człowieka — czułość | 0,0% | **80,0%** (16/20) |
| flaga — precyzja | — | 51,6% (16/31) |
| pola w zakresie schematu (18 ścieżek) | 5,9% | **25,0%** (34/136) |
| halucynacje (pola, które miały zostać puste) | 0,7% | **6,2%** (9/145) |
| kompletność pytań, tolerancja ±1 | 22,5% | **80,0%** (32/40) |

Przy czterdziestu wiadomościach przedział ufności jest szeroki — dla wyniku
100% sięga w dół do około 91%, a dla 65% znacznie niżej. Te liczby mówią, że
pipeline działa, nie jak zachowa się na cudzej poczcie.

**Kompromis tej architektury, wprost:** sam regex ma mniej halucynacji niż
model (0,7% kontra 6,2%). Model podnosi trafność pól czterokrotnie i trasę
sześciokrotnie, ale płaci się za to tym, że czasem wpisze coś, czego
w wiadomości nie było. Dlatego cztery najwrażliwsze pola — PESEL, telefon,
e-mail, kod pocztowy — nie przechodzą przez model wcale.

**Osobne pytanie zamiast jednego dużego.** Flaga do człowieka mierzona
w ramach wspólnej klasyfikacji dawała czułość 5%. Ta sama lista szesnastu
warunków, ten sam model i ta sama treść promptu, ale zadane jako **jedyne
pytanie** — 80%. Na tej wielkości modelu wygrywa architektura, nie większy
model.

### Prawdziwa skrzynka, 36 wiadomości

236 pól wypełnionych walidowanym regexem bez udziału modelu. Walidacja PESEL:
26 poprawnych, 1 błędna suma kontrolna, 2 zły kształt. Próbka jest jednorodna
— to w większości zgłoszenia z formularza — więc mierzy pola i walidację, nie
trasę.

### Warianty modelu i trybu

Pomiar z 7 XI 2026 na **12 zgłoszeniach syntetycznych**, napisanych pod schemat
pól. Mniejsza i łatwiejsza próbka niż powyższa; służy do porównania wariantów
między sobą, nie do podawania skuteczności.

| wariant | pola krytyczne | zgłoszenia bez poprawek | mediana | p95 |
|---|---:|---:|---:|---:|
| 7B hybryda | 100% | 100% | 4,35 s | 4,81 s |
| 7B llm | 100% | 100% | 4,96 s | 8,18 s |
| 4.5B llm | 98,1% | 83,3% | 5,13 s | 8,37 s |
| 4.5B hybryda | 96,3% | 66,7% | 4,34 s | 5,03 s |
| sam regex, bez modelu | 44,4% | 0% | — | — |

Ostatni wiersz jest najważniejszy: model wykonuje pracę nieredukowalną, a
warstwa deterministyczna obsługuje tylko to, co ma sztywny format.

Nie ufaj tym liczbom u siebie — zmierz własne. Harness ewaluacyjny jest
częścią repozytorium właśnie dlatego.

## Wymagania

- Python 3.11 lub nowszy
- [Ollama](https://ollama.com) z pobranym Bielikiem **i modelem do
  embeddingów** (`bge-m3`, ok. 1,2 GB)
- karta z co najmniej **8 GB VRAM** dla modelu 7B w kwantyzacji Q8
  (wariant na słabszym sprzęcie: 4.5B w trybie `llm`)
- LibreOffice, opcjonalnie, do konwersji umów na PDF
- skrzynka z obsługą IMAP i hasłem aplikacji

Pakiety Pythona to kilkanaście megabajtów. Wektory bazy wiedzy liczy Ollama,
więc **nie ma tu `torch` ani `sentence-transformers`** — wypadły po tym, jak
na Windowsie ze Smart App Control biblioteka natywna jednej z ich zależności
została zablokowana i import nie przechodził wcale. Kto chce polskiego modelu
`mmlw`, przestawia `embeddingi.silnik` i odkomentowuje dwie paczki
w `requirements.txt`.

## Uruchomienie

```bash
# 1. środowisko
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt

# 2. konfiguracja
cp config.example.yaml config.yaml    # dane firmy, gwarancja, polisa, rachunek
cp wyjazdy.example.yaml wyjazdy.yaml  # termin, cena i program każdego wyjazdu
cp .env.example .env                  # hasło aplikacji do skrzynki

# 3. modele - sprawdź, jakie tagi masz lokalnie, i wpisz je do config.yaml
ollama serve &
ollama pull SpeakLeash/bielik-minitron-7B-v3.0-instruct:Q8_0
ollama pull bge-m3                    # embeddingi bazy wiedzy
python skrypty/sprawdz_modele.py

# 4. baza wiedzy
python skrypty/zrzut_strony.py        # zrzuca treść strony do wiedza/
#    przejrzyj pliki w wiedza/, usuń śmieci, dopisz czego brakuje
python skrypty/indeksuj.py

# 5. pierwszy przebieg po skrzynce, bez zapisu i bez draftów
python skrypty/sprawdz_maile.py --na-sucho

# 6. na serio
python skrypty/sprawdz_maile.py

# 7. szablon umowy z Twojego wzorca + pierwsza umowa
python skrypty/zbuduj_szablon_umowy.py wsad/umowa_zrodlo.docx
python skrypty/zrob_umowe.py --lista
python skrypty/zrob_umowe.py 1 dolomity-jesien-2026

# 8. arkusz wyjazdu
python skrypty/zrob_liste.py --lista
python skrypty/zrob_liste.py dolomity-jesien-2026              # wariant pełny
python skrypty/zrob_liste.py dolomity-jesien-2026 --okrojona    # do wysłania dalej

# 9. odprawa przedwyjazdowa
python skrypty/zrob_odprawe.py --lista
python skrypty/zrob_odprawe.py 1 dolomity-jesien-2026 --do-skrzynki
python skrypty/zrob_odprawe.py --wszyscy dolomity-jesien-2026

# 10. wykaz umów dla UFG/TFG
python skrypty/zrob_csv_ufg.py --pola      # dostępne wartości do zmapowania
python skrypty/zrob_csv_ufg.py 2026 10
```

## Pierwsze polecenie po pobraniu

```bash
python skrypty/sprawdz_gotowosc.py
```

Wypisze, czego brakuje i co z tym zrobić: pliki konfiguracyjne, dane firmy,
model w Ollamie, indeks bazy wiedzy, szablon umowy, LibreOffice, logowanie do
skrzynki. Rozróżnia blokady od ostrzeżeń — ostrzeżenie znaczy „zadziała, ale
umowa wyjdzie z luką", blokada znaczy „nie ruszaj".

Uruchamianie na stałe, kopie zapasowe, retencja danych i publikacja
repozytorium: **[WDROZENIE.md](WDROZENIE.md)**.

Jeśli pobrałeś to repozytorium i chcesz uruchomić u siebie — które pliki
zmienić, w jakiej kolejności i co wymaga zajrzenia w kod:
**[DLA-TWOJEJ-FIRMY.md](DLA-TWOJEJ-FIRMY.md)**. Znane ograniczenia:
**[ZASTRZEZENIA.md](ZASTRZEZENIA.md)**.

## Testy

```bash
python testy/uruchom_wszystkie.py
```

Działają bez modelu i bez sieci, więc możesz sprawdzić, że kod jest sprawny,
jeszcze przed pobraniem kilku gigabajtów wag.

Siedem zestawów, ponad 120 przypadków, bez modelu i bez sieci. Każdy przypadek
wyszedł z pomiaru albo z błędu, który faktycznie wystąpił:

- **warstwa deterministyczna** — PESEL, telefon, e-mail, kod pocztowy, suma
  kontrolna, przypisanie po etykiecie, kalendarzowa poprawność daty urodzenia
  i jej zgodność z datą zakodowaną w numerze PESEL.
- **składanie promptów** — czy sekcje wchodzą do promptu i, co ważniejsze, czy
  dane wrażliwe **nie** wchodzą. Błąd w składaniu promptu jest cichy: model
  odpowiada, JSON się parsuje, nikt nic nie zauważa.
- **dokumenty** — czy dane z bazy trafiają do umowy, arkusza i wykazu CSV; czy
  wariant okrojony arkusza faktycznie nie zawiera PESEL-i ani kodów dostępu;
  czy numeracja umów nie potrafi wystawić dwóch dokumentów o tym samym numerze.
- **pobieranie poczty** — czy limit przebiegu nie gubi zaległości, czy fetch
  nie zmienia flagi przeczytania i czy zapis projektu odpowiedzi trafia do
  właściwego folderu z datą ze strefą czasową.
- **flaga do człowieka** — czy warunek stwierdzony mechanicznie podnosi flagę
  wbrew modelowi, czy czyste zgłoszenie jej **nie** dostaje i czy cytat
  uzasadniający jest weryfikowany w treści wiadomości.
- **embeddingi** — normalizacja wektorów, podział na partie, zgodność indeksu
  z modelem, którym go zbudowano.
- **dopasowanie zgłoszeń** — czy mail z danymi trafia do właściwego zgłoszenia,
  gdy jedna osoba zapisała się na kilka wyjazdów, i czy przy wątpliwości
  program **odmawia zgadywania**.

Czego te testy nie sprawdzają: jakości odpowiedzi modelu. Tego nie da się
zmierzyć testem jednostkowym — do tego służy harness ewaluacyjny.

## Arkusz wyjazdu

`zrob_liste.py` składa trzy arkusze w jednym pliku .xlsx:

- **Logistyka** — jedna strona do wydrukowania: termin, zbiórka, pilot, nocleg
  z adresem i kodem do skrytki, loty, samochód. To, co trzeba mieć pod ręką na miejscu.
- **Uczestnicy** — lista z danymi do polisy i uwagami (dieta, pokój na parterze).
- **Rezerwacje** — wszystkie rezerwacje wyjazdu z warunkami i brakami.

Powstają dwa warianty tego samego pliku. **Pełny** zawiera PESEL-e, numery
dokumentów i kody dostępu — dla Ciebie i dla ubezpieczyciela. **Okrojony**
(`--okrojona`) nie zawiera ich wcale — ten można wysłać pilotowi, lokalnemu
przewodnikowi albo obiektowi. Lista uczestników krąży po wyjeździe i nie ma
powodu, żeby numery PESEL krążyły razem z nią.

Samochód bez potwierdzonego ubezpieczenia wkładu własnego jest wypisywany jako
ostrzeżenie — i w konsoli, i wyróżniony w arkuszu. To ubezpieczenie kupuje się
zwykle osobno, poza wypożyczalnią, więc łatwo o nim zapomnieć.

## Trzy warstwy danych umowy

Umowa składa się z trzech źródeł, i to jest kluczowa decyzja projektowa:

| Warstwa | Plik | Jak często się zmienia |
|---|---|---|
| firma | `config.yaml` | raz w roku (gwarancja, polisa, rachunek) |
| wyjazd | `wyjazdy.yaml` | raz na imprezę (termin, cena, program, pilot) |
| uczestnik | baza SQLite | przy każdej umowie |

Dzięki temu termin i cenę wpisujesz **raz**, a korzystają z nich umowa, rejestr
umów, plik dla UFG i odprawa przedwyjazdowa.

`zrob_umowe.py` wypisuje na koniec listę pól pustych albo wciąż w nawiasach
kwadratowych i mówi wprost, że umowa nie jest gotowa do podpisu. To jest zalążek
copilota kompletności.

## Struktura

```
config.yaml          dane firmy - JEDYNY plik do zmiany przy wdrożeniu u innej firmy
wiedza/              baza wiedzy w markdownie - DRUGI I OSTATNI taki plik
prompty/             prompty w plikach, do kalibracji bez dotykania kodu
szablony/            szablony .docx umowy i odprawy
dane/                baza SQLite, wygenerowane umowy, Excel z rozmowami (poza repo)
nagrania/            pliki audio do transkrypcji (poza repo)

biuro/
  config.py          wczytywanie konfiguracji, sekrety tylko z .env
  llm.py             klient Bielika przez Ollamę, JSON wymuszony schematem
  schemas.py         kontrakt danych między modelem a aplikacją
  deterministyczne.py  PESEL, telefon, e-mail, kod pocztowy - regex z walidacją
  ekstrakcja.py      tryb hybrydowy i llm, składanie obu warstw
  pii.py             maskowanie danych wrażliwych przed logiem i promptem
  rag.py             indeksowanie i wyszukiwanie w bazie wiedzy
  baza.py            SQLite - źródło prawdy dla umów, rejestru i UFG
  historia.py        historia kontaktu z uczestnikiem
  umowy.py           generator umów z szablonu
  odprawa.py         odprawa przedwyjazdowa jako projekt maila
  listy.py           arkusz wyjazdu: uczestnicy, rezerwacje, logistyka
  ufg.py             miesięczny wykaz umów dla portalu UFG/TFG
  tfg.py             licznik dni do deklaracji
  mail/
    imap_client.py   IMAP: czytanie i wstawianie draftów
    pipeline.py      ścieżka od maila do draftu
testy/               siedem zestawów, bez modelu i bez sieci
skrypty/
  sprawdz_gotowosc.py  czy wszystko jest na miejscu - pierwsze polecenie
  sprawdz_maile.py     przebieg po skrzynce (--na-sucho do kalibracji)
  zrob_umowe.py        umowa dla zgłoszenia
  zrob_odprawe.py      odprawa przedwyjazdowa (--wszyscy dla całego wyjazdu)
  zrob_liste.py        arkusz wyjazdu (--okrojona bez danych wrażliwych)
  zrob_csv_ufg.py      miesięczny wykaz umów (--pola pokazuje mapowanie)
  kopia_zapasowa.py    spójna kopia bazy i dokumentów
  retencja.py          usuwanie danych wrażliwych po terminie
  indeksuj.py          przebudowa indeksu bazy wiedzy
  zrzut_strony.py      treść strony www do bazy wiedzy
  zbuduj_szablon_umowy.py  wzorzec .docx na szablon z polami
```

## Jak wdrożyć to w innej firmie

Podmień dwie rzeczy: `config.yaml` i zawartość folderu `wiedza/`. Resztę zostaw.
Kod nie zawiera nic specyficznego dla Warsztatów Arktycznych — nazwy wyjazdów,
ceny i warunki są w bazie wiedzy, dane firmy w konfiguracji.

## Decyzje projektowe i dlaczego takie

**IMAP, nie Gmail API.** Hasło aplikacji działa od razu i z każdą skrzynką. Gmail API
wymagałby od każdej firmy przejścia przez projekt w Google Cloud i ekran zgody, co
zabija ideę rozwiązania do samodzielnego uruchomienia.

**Wymuszony schemat JSON.** Model dostaje schemat i fizycznie nie może zwrócić
czegoś, co się nie sparsuje. To główna przyczyna awarii takich pipeline'ów.

**Cyfry nie przechodzą przez model.** PESEL, telefon, e-mail i kod pocztowy
ustala regex z walidacją — zawsze, nie tylko gdy model zawiedzie. W pomiarze
100% bez udziału modelu. To nie jest optymalizacja kosztu, to usunięcie całej
klasy błędów.

**Zły kształt usuwamy, złą sumę kontrolną zostawiamy i flagujemy.** Dziewięć
cyfr w polu PESEL to pomyłka maszyny: numer telefonu wpadł w wolną rubrykę.
Takiej wartości nie chcemy nigdzie. Jedenaście cyfr z błędną sumą kontrolną to
literówka uczestnika — zostaje i idzie do człowieka, bo tylko on może zadzwonić
i dopytać.

**Pola ustalone regexem wychodzą ze schematu, ale ich wartości idą do promptu.**
Bez drugiej części tego zdania w mailu bez PESEL-u model wstawiał do pola PESEL
numer telefonu, bo pole telefonu zostało zabrane i była to jedyna wolna rubryka
na numer. Zabranie pola zostawia dziurę; pokazanie wartości ją zamyka.

**Tryb hybrydowy dla 7B, czysty `llm` dla 4.5B.** Zabieranie pól ze schematu
pomaga 7B i szkodzi 4.5B (83,3% → 66,7% zgłoszeń bez poprawek). Optymalna
architektura zależy od rozmiaru modelu — wniosek wyszedł wyłącznie z pomiaru.
Przy zmianie modelu na mniejszy przestaw `ekstrakcja.tryb` na `llm`.

**Domyślności deklarowane wprost w opisach pól.** Im mniejszy model, tym
literalniej wykonuje instrukcje. Pole „liczba osób" bez zadeklarowanej wartości
domyślnej dało u 4.5B 16,7% trafności, a po dopisaniu jednego zdania do opisu
pola — 100%. Opisy pól w `schemas.py` to nie dokumentacja, to prompt.

**Gdy model wsadza wartość w złe pole, najpierw sprawdź, czy właściwe pole
istnieje.** Dieta współuczestnika trafiała do zgłaszającego, bo nie było rubryki
`wymagania_innych_osob`. Uczestnicy zagraniczni nie mają PESEL-u, więc doszły
`typ_dokumentu` i `numer_dokumentu` — paszport nie ma sumy kontrolnej, a cała
warstwa deterministyczna stała na PESEL-u.

**Flaga do człowieka wyłącza draft, a jej warunki są listą zamkniętą.** Jedenaście
warunków wypisanych w `prompty/klasyfikacja.md`, nie opis „gdy sprawa jest
poważna" — przy modelu tej wielkości lista zamknięta działa, opis nie. Koszt
błędu jest asymetryczny: niewystawiona flaga to wysłana obietnica, której nie da
się wycofać, flaga nadmiarowa to minuta czytania. Rezygnacja, reklamacja, wycena
grupowa i współpraca nie dostają projektu odpowiedzi nigdy, niezależnie od flagi.

**Model nie pisze umów.** Treść umowy podstawiana jest deterministycznie w szablon.
Model może najwyżej sprawdzić kompletność danych.

**Brak kontekstu to brak odpowiedzi.** Jeśli baza wiedzy nie zawiera materiału na
pytanie, draft dostaje znacznik `[DO UZUPEŁNIENIA]`, a nie wymyśloną odpowiedź.
Dla biura podróży zmyślona cena albo termin to realna odpowiedzialność.

**Własna lista przetworzonych maili.** Nie dotykamy flag na serwerze IMAP, więc
przebieg można bezpiecznie powtarzać i nie psujemy stanu skrzynki.

## Poza zakresem pierwszej wersji

- nagrywanie rozmów telefonicznych (wejściem jest gotowy plik audio)
- publiczny czat na stronie (ten sam silnik, uruchamiany lokalnie)
- dostrajanie modelu (zamiast tego przykłady stylu z folderu Wysłane w promptcie)

## Licencja i model

Modele Bielik rozwijane są przez Fundację SpeakLeash we współpracy z ACK Cyfronet AGH
i publikowane na licencji Apache 2.0.
