# Jak uruchomić to u siebie

Ten plik jest dla osoby, która pobrała repozytorium i chce użyć go we własnej
firmie. Krótka wersja jest w [README.md](README.md); opis budowy i pomiarów
w [TECHNICZNIE.md](TECHNICZNIE.md).
Jeśli wdrażasz go na stałe i chcesz kolejności etapów —
[WDROZENIE.md](WDROZENIE.md).

Pierwsze wdrożenie powstało dla biura podróży wpisanego do rejestru
organizatorów turystyki. Im bliżej jesteś tego profilu, tym mniej pracy —
ale większość rzeczy, które trzeba zmienić, to **pliki tekstowe, nie kod**.

---

## Czego to wymaga

| | |
|---|---|
| system | Windows, Linux albo macOS |
| Python | 3.11 lub nowszy |
| [Ollama](https://ollama.com) | z pobranym Bielikiem i modelem do embeddingów |
| karta graficzna | 8 GB VRAM dla 7B w Q8; na słabszej 4.5B w trybie `llm` |
| skrzynka | IMAP z hasłem aplikacji (nie zwykłym hasłem do konta) |
| LibreOffice | opcjonalnie, tylko do konwersji umów na PDF |

Instalacja pakietów Pythona to kilkanaście megabajtów. Wektory liczy Ollama,
więc **nie ma tu `torch` ani `sentence-transformers`** — to była świadoma
zmiana po tym, jak na Windowsie z włączonym Smart App Control biblioteka
natywna jednej z zależności została zablokowana i import nie przechodził
wcale.

---

## Instalacja

```bash
git clone <adres-repozytorium> biuro-bielik
cd biuro-bielik

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Na Windowsie wywołuj `python -m pip`, nie `pip` — Smart App Control blokuje
`pip.exe` jako niepodpisany plik wykonywalny.

Jeśli pobrałeś repozytorium jako ZIP zamiast `git clone`, Windows oznaczy
wszystkie pliki jako pochodzące z internetu i odmówi uruchomienia `biuro.cmd`
komunikatem o niebezpiecznym pliku. Zdejmij oznaczenie raz, dla całego
katalogu:

```powershell
Get-ChildItem -Recurse -File | Unblock-File
```

Przy `git clone` ten problem nie występuje.

Modele:

```bash
ollama pull SpeakLeash/bielik-minitron-7B-v3.0-instruct:Q8_0
ollama pull bge-m3
```

Drugi to model do embeddingów bazy wiedzy, około 1,2 GB. Jest wielojęzyczny
i obsługuje polski. Jeśli wolisz polski model `mmlw` i masz gdzie go
uruchomić, zmień `embeddingi.silnik` na `sentence_transformers` i odkomentuj
dwie paczki w `requirements.txt`.

Sprawdź, co faktycznie masz lokalnie, i wpisz dokładne tagi do konfiguracji:

```bash
python skrypty/sprawdz_modele.py
```

---

## Co musisz zmienić — pięć plików i jedna tabela

Kolejność ma znaczenie: każdy następny plik korzysta z poprzedniego.

### 1. `.env` — dostęp do skrzynki

```bash
cp .env.example .env
```

Wpisz adres i **hasło aplikacji**, nie hasło do konta. W Gmailu hasło
aplikacji ma 16 znaków; jeśli Twoje ma inną długość, to nie jest hasło
aplikacji. Generuje się je w ustawieniach bezpieczeństwa konta, przy
włączonej weryfikacji dwuetapowej, i trzeba je wygenerować **na tym samym
koncie**, z którego czytasz pocztę.

Ten plik nigdy nie trafia do repozytorium.

### 2. `config.yaml` — dane firmy

```bash
cp config.example.yaml config.yaml
```

Plik jest obszerny, ale podzielony na sekcje i każda ma komentarz. Co trzeba
wypełnić koniecznie:

- **dane firmy** — nazwa, adres, NIP, REGON, kontakt
- **wpis do rejestru** — jeśli Twoja branża go wymaga; dla organizatora
  turystyki to numer i organ rejestrowy
- **gwarancja i polisa** — podmiot, numer, suma, okres
- **rachunek bankowy** — do umowy
- `poczta.temat_formularza` — **fragment** tematu maila, który wysyła
  formularz z Twojej strony. To jedno pole decyduje, czy zgłoszenia są
  rozpoznawane. Zła wartość nie daje błędu, tylko po cichu wyłącza całą
  szybką trasę i zgłoszenia idą jako „dane dosyłane do umowy" — nowe
  zgłoszenie w bazie nie powstaje. Wpisz dokładnie to, co widzisz w swojej
  skrzynce.
- `poczta.podpis` — podpis dokładany do każdego projektu odpowiedzi. Model
  go nie pisze, bo nie zna Twojego imienia
- `umowy.wzor_numeru` — **wzór**, nie gotowa wartość. `"{nr}/{rok}"`, nie
  `"7/2024"`. Program odmówi uruchomienia, jeśli we wzorze nie ma `{nr}`
- `ufg.kolumny` — nazwy kolumn w pliku, który wysyłasz do urzędu; patrz
  niżej, osobny punkt

### 3. `wyjazdy.yaml` — to, co sprzedajesz

```bash
cp wyjazdy.example.yaml wyjazdy.yaml
```

Jeden wpis na imprezę: termin, cena, transport, zakwaterowanie, program,
terminy płatności. Z tego pliku bierze dane umowa, arkusz uczestników, wykaz
dla urzędu i odprawa przedwyjazdowa — **wpisujesz raz, nie w czterech
miejscach**.

Pola zostawione w nawiasach kwadratowych generator wypisze jako braki
i **nie nazwie umowy gotową do podpisu**. To nie jest usterka, tylko jedyna
rzecz, która stoi między niekompletnym plikiem a dokumentem u klienta.

Jeśli nie sprzedajesz imprez turystycznych, ten plik jest Twoim katalogiem
produktów: zostaw pola, które mają sens, resztę usuń ze wzorca umowy.

### 4. `wiedza/` — baza wiedzy

To jedyne źródło faktów dla projektów odpowiedzi. Model nie korzysta
z własnej wiedzy o Twojej ofercie, cenach ani terminach.

**Jakość tych plików decyduje o jakości odpowiedzi bardziej niż wybór
modelu.** Przeczytaj [wiedza/README.md](wiedza/README.md) i
[wiedza/00-przyklad.md](wiedza/00-przyklad.md) — drugi pokazuje format
nagłówka z metadanymi i pole `status_sprzedazy`, które blokuje potwierdzanie
wolnych miejsc na wyprzedanej imprezie.

Jeśli masz stronę, zacznij od zrzutu i przejrzyj wynik:

```bash
python skrypty/zrzut_strony.py
python skrypty/indeksuj.py
```

Jedna rzecz, o którą łatwo nie pomyśleć: w każdym pliku warto mieć sekcję
**„czego tu NIE MA"**. Model ją czyta i przy pytaniu o te rzeczy napisze
`[DO UZUPEŁNIENIA]`, zamiast wymyślić odpowiedź. Bez takiej listy nie
powstrzyma się — nie wie, czego nie wie.

### 5. Wzorzec umowy

Jeśli generujesz umowy, podstaw swój wzorzec:

```bash
cp twoja-umowa.docx wsad/umowa_zrodlo.docx
python skrypty/zbuduj_szablon_umowy.py wsad/umowa_zrodlo.docx
```

Wzorzec ma mieć pola w nawiasach kwadratowych — `[imię i nazwisko]`,
`[kwota]`. Skrypt zamienia je na znaczniki w konkretnych miejscach:
komórkach tabel po współrzędnych i wybranych akapitach po numerze.

**Tu trzeba zajrzeć w kod.** Mapowanie jest w tabeli `KOMORKI` i `AKAPITY`
na początku `skrypty/zbuduj_szablon_umowy.py` i jest dopasowane do układu
jednego konkretnego wzorca. Przy innym dokumencie trzeba je przepisać —
to kilkadziesiąt linijek w rodzaju `(1, 2): "{{ p_pesel }}"`.

Skrypt sprawdza, czy komórka, którą nadpisuje, zawiera pole w nawiasie
kwadratowym, i **odmawia zapisania szablonu**, gdy trafi na gotową treść.
Bez tego sprawdzenia dopisanie jednego wiersza w tabeli przesuwałoby
wszystko poniżej i dane uczestnika trafiłyby do niewłaściwych rubryk,
a dokument wyglądałby poprawnie.

Po każdej ręcznej zmianie wzorca przebuduj szablon i uruchom testy.

### 6. Pola formularza zgłoszeniowego

Zgłoszenie z formularza na stronie program czyta wprost, bez modelu:
z wierszy „Etykieta: wartość". Pierwsze wdrożenie wysyła takie pola:

```
Wyjazd: …
Termin: …
Imię i nazwisko: …
PESEL: …
Data urodzenia: …
Dokument: paszport AB 1234567, ważny do …
Adres zamieszkania: ulica i numer, 00-000 Miasto
E-mail: …
Telefon: …
Pokój: …
Dieta / ograniczenia: …
Kontakt w nagłych wypadkach: …
Faktura: tak — nazwa firmy, adres, NIP …
Uwagi: …
```

Jeśli Twój formularz nazywa pola inaczej, dopisz swoje etykiety w tabelach
`_PROSTE` (pole formularza → pole zgłoszenia) i `_DO_UWAG` (pola, które
trafiają do kolumny uwag na liście uczestników) na początku
`biuro/mail/pipeline.py`. Etykiety wpisujesz małymi literami i bez polskich
znaków. Pola, których program nie zna, są pomijane bez błędu — dlatego po
pierwszym przebiegu otwórz listę uczestników i sprawdź, czy niczego nie
brakuje.

Dwie rzeczy decydują o tym, czy reszta działa:

- wartość pola `Wyjazd` musi pasować do nazwy albo klucza wpisu
  w `wyjazdy.yaml`. Bez tego zgłoszenie zostaje bez wyjazdu i program
  wypisuje ostrzeżenie; przy umowie zapyta, o który wyjazd chodzi;
- wiadomość jest uznawana za formularz, gdy ma imię i nazwisko oraz co
  najmniej trzy inne znane pola, albo gdy jej temat zawiera
  `poczta.temat_formularza`.

---

## Plik dla urzędu — sprawdź, zanim zaufasz

Jeśli Twoja branża wymaga okresowego wykazu umów, mapowanie kolumn jest
w `config.yaml`, w sekcji `ufg.kolumny`. Dostępne wartości:

```bash
python skrypty/zrob_csv_ufg.py --pola
```

Wygeneruj plik i **porównaj go z tym, który dziś wysyłasz ręcznie**. Dopóki
się nie zgadzają, rób to dalej ręcznie. Nazwy kolumn w pierwszym wdrożeniu
zostały potwierdzone przez właścicielkę firmy na jej prawdziwym pliku — Twój
urząd albo Twoja branża mogą wymagać innych.

Generator liczy braki i jeśli jakieś są, pisze wprost, że **plik nie jest
gotowy do wysłania**.

---

## Pierwsze uruchomienie

```bash
python skrypty/sprawdz_gotowosc.py
```

To jest cała instrukcja instalacji. Wypisze, czego brakuje, i rozróżni
**blokady** od **ostrzeżeń**: ostrzeżenie znaczy „zadziała, ale umowa wyjdzie
z luką", blokada znaczy „nie ruszaj".

```bash
python testy/uruchom_wszystkie.py
```

Trzynaście zestawów, **bez sieci i bez modelu**.
Możesz sprawdzić, że kod jest sprawny, przed pobraniem wag. Testy używają
osobnej bazy i osobnego katalogu imprez — nie dotkną Twoich danych.

```bash
python skrypty/sprawdz_maile.py --na-sucho --dni 14
```

Nic nie zapisuje i nie tworzy projektów odpowiedzi. Czytasz rozpoznane typy
wiadomości i sprawdzasz, czy się zgadzają. Jeśli któryś jest zły, popraw
`prompty/klasyfikacja.md` i powtórz. Warto w tej pętli posiedzieć —
klasyfikacja decyduje o wszystkim dalej.

Dalsze etapy, po jednym na raz, są w [WDROZENIE.md](WDROZENIE.md).

---

## Nie ufaj naszym liczbom

W repozytorium jest harness pomiarowy razem z korpusem trudnych wiadomości
i ręcznie przepisanymi odpowiedziami wzorcowymi. **Zmierz skuteczność na
własnej poczcie**, zamiast przyjmować cudzą.

```bash
python korpus/src/parsuj_korpus.py \
    --zrodlo korpus/dane/maile_testowe_biuro_podrozy.txt \
    --wyjscie korpus/out/maile.jsonl

python korpus/adapter.py --zrodlo korpus/out/maile.jsonl \
    --wyjscie korpus/out/predykcje.jsonl --tryb hybryda

python korpus/src/ocen.py --gold korpus/gold/gold_zgloszenia.json \
    --predykcje korpus/out/predykcje.jsonl --tryb "u mnie" \
    --bledy korpus/out/bledy.csv
```

Raport podaje **cztery metryki osobno**, nigdy jednej liczby: trafność pól,
halucynacje, trasę i czułość flagi do człowieka. Razem z punktem odniesienia
bez modelu — żeby było widać, co wnosi model, a co zwykły regex.

Na własnej poczcie: `python korpus/import_skrzynki.py --dni 120 --zapisz`,
potem `szkielet_gold.py` i `wypelnij.py`. Import czyta skrzynkę tylko do
odczytu, nie oznacza wiadomości jako przeczytanych i nie zmienia flag.

---

## Co zmienić, jeśli nie jesteś biurem podróży

Rzeczy specyficzne dla branży i miejsca, w którym siedzą:

| co | gdzie | ile pracy |
|---|---|---|
| typy wiadomości (11 tras) | `prompty/klasyfikacja.md` | plik tekstowy |
| warunki „do człowieka" (16) | `prompty/klasyfikacja.md`, sekcja listy zamkniętej | plik tekstowy |
| ton i zasady odpowiedzi | `prompty/odpowiedz.md` | plik tekstowy |
| pola wyciągane ze zgłoszeń | `biuro/schemas.py`, klasa `Uczestnik` | kod, opisy pól są promptem |
| walidacja numerów | `biuro/deterministyczne.py` | kod |
| katalog produktów | `wyjazdy.yaml` | plik tekstowy |
| wzorzec umowy | `wsad/`, mapowanie w `skrypty/zbuduj_szablon_umowy.py` | kod |
| plik dla urzędu | `config.yaml`, sekcja `ufg.kolumny` | plik tekstowy |
| licznik terminu sprawozdawczego | `biuro/tfg.py` | kod |

Lista szesnastu warunków „do człowieka" jest w **jednym** miejscu i czytają
ją trzy rzeczy: prompt klasyfikacji, prompt flagi i narzędzie do wypełniania
odpowiedzi wzorcowych. Dopisanie warunku w jednym pliku wystarcza. Nie
kopiuj tej listy — rozjedzie się przy pierwszej poprawce i klasyfikator
będzie oceniał inne warunki niż te, według których mierzysz.

Warstwa walidacji jest polska: PESEL z sumą kontrolną, NIP, kod pocztowy,
numer telefonu. Poza Polską trzeba ją wymienić — ale **architektura jest
ważniejsza niż te konkretne wzorce**: cztery najwrażliwsze pola nie
przechodzą przez model wcale, bo zwalidowana cyfra bije cyfrę przepisaną
przez model.

---

## Czego ten program nie robi

- **nie wysyła maili** — każda odpowiedź czeka jako wersja robocza w Twojej
  skrzynce, w tym samym wątku, na Twoją decyzję
- **nie publikuje treści** i nie ma modułu publicznego
- nie podejmuje decyzji handlowych, prawnych ani finansowych
- nie twierdzi, że wyciąga dane bezbłędnie — stąd cztery osobne metryki
  i flaga do człowieka na liście zamkniętej warunków
- nie wysyła niczego na zewnątrz: model, baza, indeks i dokumenty są na
  Twoim dysku

Ograniczenia, o których warto wiedzieć przed wdrożeniem, są
w [ZASTRZEZENIA.md](ZASTRZEZENIA.md).

---

## Licencja

MIT — patrz [LICENSE](LICENSE). Możesz używać, zmieniać i wdrażać u klientów.
Wzorzec umowy, regulamin i treść oferty pierwszego wdrożenia **nie są częścią
repozytorium**; zostały wyłączone celowo.
