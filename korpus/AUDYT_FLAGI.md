# Audyt flagi do człowieka przeciw korpusowi

Przebieg 7 listopada 2026, wieczór. **Bez modelu** — porównanie listy warunków
z `prompty/klasyfikacja.md` z ground truth dla 40 wiadomości, przypadek po
przypadku, przez przeczytanie treści.

Po co: `BRAK_FLAGI_DO_CZLOWIEKA` jest najdroższym błędem w tym systemie, a jedyny
akceptowalny wynik to zero. Jeśli lista warunków w prompcie nie pokrywa
wszystkich przypadków z korpusu, model nie ma jak ich złapać — i nie jest to
wtedy wina modelu. Taki audyt można zrobić czytając, więc nie ma powodu płacić
za niego czasem GPU.

## Wynik pierwszego przejścia: 15 z 20

Lista jedenastu warunków przepuściłaby **pięć flagowanych wiadomości**, a dwa
warunki były na tyle szerokie, że zapalałyby się na wiadomościach, których
ground truth nie flaguje.

### Przepuszczone (brak warunku na liście)

| mail | sprawa | brakujący warunek |
|---|---|---|
| MAIL_10 | pytanie o wpis do rejestru, składki TFG, zakres polisy | `skutki_prawne_odpowiedzi` |
| MAIL_18 | zmiana nazwiska po podpisaniu umowy, bilety na stare nazwisko | `zmiana_w_podpisanej_umowie` |
| MAIL_24 | uczestnikiem ma być 16-latek | `uczestnik_nieletni` |
| MAIL_25 | oczekiwanie gwarancji zorzy i rekompensaty za pogodę | `obietnica_bez_pokrycia` |
| MAIL_36 | szanse na niedźwiedzia, wypożyczenie 600 mm na miejscu | `obietnica_bez_pokrycia` |
| MAIL_22 | voucher kwotowy z terminem ważności | `produkt_poza_oferta` |

MAIL_22 łapał się słabo pod `decyzja_handlowa`, więc dostał własny warunek.

### Za szerokie (ryzyko fałszywej flagi)

| warunek | zapalałby się na | dlaczego to błąd |
|---|---|---|
| `brak_kontekstu` | MAIL_11 (nie podaje wyjazdu), MAIL_19 („ile") | o brakującą informację można dopytać zwykłą odpowiedzią; ground truth tych nie flaguje |
| `decyzja_handlowa` ze słowem „rabat" | MAIL_06 (rezygnacja z dopłaty do jedynki) | dopłata jest w cenniku, rezygnacja z niej to operacja standardowa |
| `rola_nadawcy_niejasna` | MAIL_04 (mąż za żonę), MAIL_17 (córka za matkę) | role są jasne, brakuje tylko danych jednej osoby |
| `dane_osobowe` | MAIL_13 (celiakia), MAIL_03 (krążenie w dłoniach) | podanie informacji o sobie nie jest sprawą o przetwarzanie danych |

## Lista po poprawce: 16 warunków, 20 z 20

`brak_kontekstu` zawężony do odwołań do ustaleń poza skrzynką („jak ustaliliśmy
telefonicznie", „tego dokumentu"). Trzy pozostałe warunki dostały wprost
wypisane kontrprzykłady, bo przy modelu tej wielkości zdanie „to **nie** jest
ten warunek" działa lepiej niż doprecyzowanie definicji.

| mail | powód z ground truth | warunek z listy |
|---|---|---|
| MAIL_02 | brak działającego kontaktu | `dane_zlego_ksztaltu` |
| MAIL_07 | rozliczenie potrąceń, cesja miejsca | `rezygnacja` |
| MAIL_08 | odwołanie do ustaleń telefonicznych | `brak_kontekstu` |
| MAIL_10 | rejestr, TFG, zakres ubezpieczenia | `skutki_prawne_odpowiedzi` |
| MAIL_12 | wpłata z konta żony, brak na liście | `niezgodnosc_platnosci` |
| MAIL_14 | wycena grupowa, oferta do dotacji | `decyzja_handlowa` |
| MAIL_18 | zmiana nazwiska w podpisanej umowie | `zmiana_w_podpisanej_umowie` |
| MAIL_20 | przelew osoby trzeciej, tytuł bez numeru umowy | `niezgodnosc_platnosci` |
| MAIL_21 | reklamacja z żądaniem rekompensaty | `reklamacja` |
| MAIL_22 | voucher kwotowy | `produkt_poza_oferta` |
| MAIL_24 | uczestnik niepełnoletni | `uczestnik_nieletni` |
| MAIL_25 | gwarancja zorzy, rekompensata za pogodę | `obietnica_bez_pokrycia` |
| MAIL_28 | dwie osoby i pokój jednoosobowy | `niezgodnosc_w_zgloszeniu` |
| MAIL_30 | przesunięcie terminu dopłaty | `niezgodnosc_platnosci` |
| MAIL_31 | współpraca barterowa | `decyzja_handlowa` |
| MAIL_34 | PESEL złej długości, pytanie o podstawę prawną | `dane_zlego_ksztaltu` + `dane_osobowe` |
| MAIL_36 | szanse na zwierzęta, wypożyczenie sprzętu | `obietnica_bez_pokrycia` |
| MAIL_37 | wypowiedź prasowa, licencja na zdjęcia | `decyzja_handlowa` |
| MAIL_38 | zgubiony bagaż w trakcie wyjazdu | `sprawa_pilna` |
| MAIL_40 | ograniczenie użycia wizerunku | `zadanie_po_wyjezdzie` + `dane_osobowe` |

Dwadzieścia na dwadzieścia, każdy przez nazwany warunek.

## Czego ten audyt nie dowodzi

Że model wystawi flagę. Dowodzi tylko, że **ma czym** — że dla każdego przypadku
z korpusu istnieje warunek, który da się rozpoznać z treści wiadomości. To jest
warunek konieczny, nie wystarczający.

Pomiar rzeczywistej czułości wymaga przebiegu z modelem:

```bash
python korpus/adapter.py --zrodlo korpus/out/maile.jsonl \
    --wyjscie korpus/out/predykcje.jsonl --tryb hybryda
python korpus/src/ocen.py --gold korpus/gold/gold_zgloszenia.json \
    --predykcje korpus/out/predykcje.jsonl \
    --etykiety korpus/schemat/etykiety.json \
    --tryb "7B hybryda" --bledy korpus/out/bledy.csv
```

W raporcie patrz najpierw na sekcję 4 i na początek `bledy.csv`. Jeśli
`BRAK_FLAGI_DO_CZLOWIEKA` nie jest zerem, sprawdź najpierw, czy brakujący
przypadek ma warunek na liście — jeśli ma, to problem jest w prompcie albo
w modelu, a jeśli nie ma, to w tym pliku.

Drugi kierunek: jeśli precyzja flagi jest niska, sprawdź, które z czterech
zawężonych warunków zapaliły się za szeroko. Kontrprzykłady w prompcie są po to,
żeby tego nie robiły, ale są zmierzone tylko tym korpusem.
