# Korpus testowy i harness ewaluacyjny — skrzynka biura podróży

Zestaw do zmierzenia, jak ekstrakcja i klasyfikacja radzą sobie na poczcie, która
nie jest wzorowa. Korpus jest **syntetyczny** i napisany pod trudne przypadki, nie
pod rozkład sezonu — patrz „Ograniczenia" na końcu.

Bez zależności zewnętrznych. Python 3.9+.

## Co tu jest

```
dane/     maile_testowe_biuro_podrozy.txt   40 wiadomości przychodzących
          maile_testowe_potwierdzenia.txt    3 potwierdzenia (lot, nocleg, auto)
src/      parsuj_korpus.py                   .txt -> .jsonl
          warstwa_regex.py                   dane ustalane deterministycznie
          szkielet_gold.py                   poczta -> szkielet ground truth (.json + .csv)
          csv_na_gold.py                     wypełniony arkusz -> plik gold
          ocen.py                            raport z czterech metryk
          symuluj_predykcje.py               sprawdzenie samego harnessu
testy/    testy_regex.py                     18 przypadków, bez modelu i bez sieci
schemat/  mapowanie_pol.json                 nazwy kanoniczne -> nazwy z schemas.py
          etykiety.json                      6 tras + 19 etykiet szczegółowych
gold/     gold_zgloszenia.json               ground truth dla 40 wiadomości
          gold_rezerwacje.json               ground truth dla 3 potwierdzeń
prompty/  ekstrakcja_zgloszenia.md
          ekstrakcja_rezerwacji.md
          klasyfikacja.md
```

## Ground truth na prawdziwej poczcie — droga najkrótsza

To jest ścieżka na dziś i niedzielę. Wąskim gardłem jest przepisywanie, więc
warstwa deterministyczna wypełnia to, co umie, a ty potwierdzasz i dopisujesz resztę.

```bash
# 1. zaimportowana poczta -> szkielet w dwóch formatach
python src/szkielet_gold.py --zrodlo <twoj_eksport>.jsonl \
    --wyjscie out/szkielet --kierunki wyjazdy_kierunki.txt

# 2. otwierasz out/szkielet.csv w arkuszu i uzupełniasz
#    (UTF-8 z BOM, Excel i LibreOffice otwierają bez pytania o kodowanie)

# 3. arkusz -> plik gold
python src/csv_na_gold.py --csv out/szkielet.csv --wyjscie gold/gold_prod.json

# 4. pomiar
python src/ocen.py --gold gold/gold_prod.json --predykcje out/predykcje_7b.jsonl \
    --mapowanie schemat/mapowanie_pol.json --etykiety schemat/etykiety.json \
    --tryb "7B hybryda, poczta prawdziwa" --bledy out/bledy_prod.csv
```

Wejście w kroku 1 może być JSONL z `parsuj_korpus.py`, dowolnym innym JSONL albo CSV —
kolumny nadawcy, tematu i treści są rozpoznawane po nazwach (`od`/`from`/`nadawca`,
`temat`/`subject`, `tresc`/`body`/`text`). Jeśli twój eksport ma inne, dopisz je do
`KLUCZE_*` w `src/szkielet_gold.py`.

**Co wypełnia regex:** e-mail, telefon (z rozdzieleniem komórka/stacjonarny), PESEL,
NIP, kod pocztowy, zakres dat, kwota, liczba osób, numer umowy, kierunek z zamkniętej
listy. Na korpusie 40 maili daje to 110 pól, średnio 2,8 na wiadomość.

**Czego regex nie robi i nie będzie robił:** nie przypisuje intencji, nie ustawia flagi
do człowieka, nie zgaduje nazwisk. Gdyby to robił, mierzyłabyś model jego własną
odpowiedzią.

**Kolumna `pola_puste` jest pusta i to jest celowe.** Kandydaci są w `_propozycja_pustych`
— przenosisz tylko te, dla których sprawdziłaś, że w treści nic nie ma. Źle oznaczona
pułapka odwraca metrykę: model dostaje karę za poprawnie wyciągniętą wartość.
`csv_na_gold.py` odmawia zapisu, gdy ta sama ścieżka jest jednocześnie wypełniona
i wpisana jako pułapka, oraz gdy brakuje intencji albo flagi — bo wtedy pomiar
policzyłby błąd ground truth jako błąd modelu.

**Walidacja numerów** trzyma się twojej zasady: zły kształt usuwamy i zgłaszamy jako
brak, złą sumę kontrolną zostawiamy w danych i flagujemy do człowieka. Sumy kontrolne
PESEL i NIP są liczone, a z poprawnego PESEL-u wyciągana jest data urodzenia — masz
wtedy darmowe porównanie z datą podaną jawnie.

## Jak uruchomić

```bash
# 1. korpus na JSONL
python src/parsuj_korpus.py \
    --zrodlo dane/maile_testowe_biuro_podrozy.txt dane/maile_testowe_potwierdzenia.txt \
    --wyjscie out/maile.jsonl --podglad

# 2. sprawdzenie, że harness liczy to, co ma liczyć
python src/symuluj_predykcje.py --gold gold/gold_zgloszenia.json \
    --wyjscie out/idealne.jsonl --psuj 0
python src/ocen.py --gold gold/gold_zgloszenia.json --predykcje out/idealne.jsonl \
    --etykiety schemat/etykiety.json --tryb "kontrola harnessu"
# musi dać 100% we wszystkich metrykach

# 3. prawdziwy przebieg
python src/ocen.py --gold gold/gold_zgloszenia.json \
    --predykcje out/predykcje_7b_hybryda.jsonl \
    --mapowanie schemat/mapowanie_pol.json \
    --etykiety schemat/etykiety.json \
    --tryb "7B hybryda" --bledy out/bledy_7b.csv
```

Pole `case_note` w korpusie to metadana testowa — parser usuwa je domyślnie,
`--zachowaj-case` zostawia. Na wejście modelu nie może pójść, bo zawiera opis
pułapki.

## Format predykcji

JSONL, jedna linia na wiadomość:

```json
{"id": "MAIL_01", "intencja": "zgloszenie_nowe", "intencje_dodatkowe": ["faktura"],
 "do_czlowieka": false, "pytania_liczba": 0,
 "pola": {"wyjazd.nazwa": "Lofoty — zorze i zima", "zgloszenie.liczba_osob": 1}}
```

Pola mogą być zagnieżdżone (`{"wyjazd": {"nazwa": "..."}}`) — zostaną spłaszczone
do ścieżek kropkowych. Jeśli nazwy pól różnią się od kanonicznych, uzupełnia się
`schemat/mapowanie_pol.json` i gold nie wymaga żadnych zmian.

## Cztery metryki i dlaczego nie są jedną liczbą

| metryka | co liczy | koszt błędu |
|---|---|---|
| trafność pól | 237 pól, które mają zostać wyciągnięte | poprawka ręczna, minuty |
| halucynacje | 145 pól, które **muszą zostać puste** | zły PESEL w umowie, zły adres w arkuszu |
| trasa (6 klas) | czy wiadomość idzie we właściwą ścieżkę | draft na reklamację, zgłoszenie w spamie |
| flaga do człowieka | 20 wiadomości o skutkach prawnych lub finansowych | wysłana obietnica, której nie da się wycofać |

Rozdzielenie jest celowe. Model, który wypełnia każde pole czymkolwiek, dostanie
dobrą trafność i katastrofalny wynik na halucynacjach — i to drugie jest tym,
co zabija wdrożenie. Zestaw jest skonstruowany tak, że **wstrzymanie się od
odpowiedzi jest punktowane**: 145 pól to pola-pułapki, czyli 38% wszystkich ocen.

Piąta metryka, liczba pytań klienta, jest przybliżeniem kompletności draftu.
Nie mierzy jakości treści — tego nie da się zmierzyć trafnością.

## Czego szukać w raporcie najpierw

Kolejność w `bledy_*.csv` jest od najdroższych:

1. `BRAK_FLAGI_DO_CZLOWIEKA` — każdy taki wiersz to wiadomość, na którą poszłaby
   automatyczna odpowiedź mimo skutków prawnych. Zero jest jedynym akceptowalnym
   wynikiem; jeśli nie jest zero, to warunki flagi muszą być listą zamkniętą w prompcie.
2. `HALUCYNACJA` — pole wypełnione bez danych w treści.
3. `PRZECIEK_POLA` — dane jednej osoby w polu innej (np. alergia męża w diecie żony).
4. `ZLA_TRASA` — wiadomość w niewłaściwej ścieżce.
5. dalej: złe wartości i pola niewyciągnięte.

## Pułapki wbudowane w korpus

Grupy, które warto sprawdzać osobno, bo każda wskazuje inną warstwę do poprawy:

- **Cytaty** (MAIL_06, 23, 35, 39). Kwoty i nazwiska występują wyłącznie w cytowanej
  historii. Jeśli model je podaje, na wejście poszła `tresc_pelna` zamiast `tresc` —
  to błąd parsera, nie promptu.
- **Nadawca ≠ uczestnik** (MAIL_09, 17, 22, 24). Księgowa, córka, żona, syn.
- **Brak wyjazdu** (MAIL_08, 10, 11, 12, 19, 25, 27, 34). Osiem wiadomości, w których
  pola wyjazdu muszą zostać puste. Pokusa dopisania najbliższego terminu z kalendarza.
- **Odwrócone role** (MAIL_32). Klient prosi o NASZ NIP — pole NIP nabywcy puste.
- **Zły kształt danych** (MAIL_02, 34). E-mail urwany, telefon 000000000, PESEL
  z ośmiu cyfr. Do usunięcia i zgłoszenia jako brak, nie do zapisania.
- **Niezgodność wewnętrzna** (MAIL_28). 2 osoby i pokój jednoosobowy — zapisać obie
  wartości i zgłosić, nie naprawiać po cichu.
- **Liczby o różnym znaczeniu** (POTWIERDZENIE_01, 03). Taryfa a suma; kaucja
  a wkład własny — ta sama liczba 15 000 w dwóch rolach.
- **Dane operacyjne w prozie** (POTWIERDZENIE_02). Kod do skrytki `4 7 2 9` w zdaniu,
  dwa adresy (dom 118, parking 104), zdanie o tym, co zrobić, gdy kod nie działa —
  które nie jest drugim kodem.

## Co trzeba uzgodnić przed podłączeniem do produkcji

1. **Nazwy pól.** Gold używa nazw kanonicznych. Jeśli `schemas.py` ma inne, wpisuje
   się je do `schemat/mapowanie_pol.json` raz.
2. **Sześć tras.** Moduł 1 ma już zaimplementowane rozpoznawanie 6 typów. Nazwy
   w `schemat/etykiety.json` są propozycją i trzeba je zrównać z tymi z kodu, zanim
   raport cokolwiek znaczy — inaczej każda wiadomość wyjdzie jako zła trasa.
3. **Wartość domyślna `liczba_osob`.** Przy jawnym „-" w formularzu (MAIL_02) gold
   traktuje to pole jako tolerowane, bo to decyzja projektowa: czy „-" to milczenie
   (wtedy 1), czy jawne „nie wiem" (wtedy puste). Trzeba ją podjąć i wpisać do opisu
   pola w schemacie.

## Ograniczenia

Korpus jest **syntetyczny**, napisany przez jedną osobę, pod trudne przypadki.
Z tego wynikają trzy rzeczy, które trzeba napisać przy każdej liczbie z tego harnessu:

- **Rozkład nie jest sezonowy.** Połowa wiadomości wymaga człowieka, bo tak została
  zbudowana. Na prawdziwej skrzynce ten udział będzie znacznie niższy, więc czułość
  flagi zmierzona tutaj jest zmierzona na próbie wzbogaconej celowo.
- **Liczebność.** 40 wiadomości. Dla wyniku 100% przedział ufności sięga w dół do
  około 91%, dla 95% — do około 83%. Dla etykiet szczegółowych (12 klas po jednym
  przykładzie) nie ma sensu liczyć niczego per klasa.
- **Dane osobowe w opublikowanej wersji są zamaskowane.** Nazwiska mają postać
  „Kowalska 1", „Kowalska 2"…, telefony „602 xxx xxx", NIP-y „XXXXXXXXXX", adresy
  „Miasto: xxxxx", daty urodzenia „xx.xx.xxxx". Skutek dla pomiaru: warstwa regex
  nie ma w tych wiadomościach telefonu, NIP-u, kodu pocztowego ani daty urodzenia
  do odczytania, więc jej wynik na tej wersji jest niższy (pola w zakresie
  41,2% zamiast 48,5%; pól odczytanych 75 zamiast 96). Liczby podawane w opisie
  projektu pochodzą z wersji sprzed maskowania, która nie jest publikowana.
  Odczyt numerów sprawdza `testy/testy_regex.py` na numerach jawnie sztucznych.
- **PESEL-e i numery są zmyślone.** Numer w MAIL_34 miał celowo zły kształt (w wersji opublikowanej jest zamaskowany), żeby
  sprawdzić warstwę walidacji. W korpusie nie ma ani jednego PESEL-u z poprawną
  sumą kontrolną, więc **ten zestaw nie zmierzy statystyki wyłapywania literówek
  w prawdziwych numerach** — do tego potrzebna jest prawdziwa poczta.

Ten harness jest testem regresji i zestawem przypadków brzegowych. Nie zastępuje
pomiaru na prawdziwej skrzynce i nie powinien być źródłem liczby podawanej jako
skuteczność wdrożenia.
