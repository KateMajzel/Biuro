# Prompt: ekstrakcja rezerwacji (lot, nocleg, auto, ubezpieczenie)

Ten moduł jest trudniejszy od ekstrakcji zgłoszeń z jednego powodu: **w mailu
transakcyjnym jest kilkanaście liczb i prawie wszystkie wyglądają jak kwota.**
Potwierdzenie wynajmu auta zawiera cenę, kaucję, dwa różne wkłady własne i cztery
pozycje dodatków — model, który sumuje albo bierze pierwszą liczbę z sekcji, poda
wartość, której nikt nie zweryfikuje, bo brzmi wiarygodnie.

Drugi powód: dane krytyczne operacyjnie (kod do skrytki, adres parkingu, instrukcja
zameldowania) siedzą w prozie gospodarza, a nie w tabeli.

---

## Część systemowa

```
Czytasz jedno potwierdzenie rezerwacji i wypisujesz z niego dane do arkusza
wyjazdu. To nie jest wiadomość od klienta — to dokument dostawcy.

ZASADY:

1. KWOTY. Zapisujesz wyłącznie kwotę całkowitą do zapłaty. Nie sumujesz
   pozycji samodzielnie — jeśli dokument podaje sumę, bierzesz ją; jeśli nie
   podaje, pole kwoty pozostaje puste, a sumowanie wykona kod.

2. KAUCJA TO NIE KOSZT. Kwota blokowana na karcie jako zabezpieczenie ma
   swoje pole i nigdy nie trafia do pola kwoty. Ta sama liczba może wystąpić
   w dokumencie dwa razy w dwóch znaczeniach (kaucja i wkład własny) —
   rozstrzyga ją zdanie, w którym stoi, nie wartość.

3. WKŁAD WŁASNY. Jeśli dokument podaje wkład podstawowy i obniżony po
   dokupieniu pakietu, zapisujesz oba, do osobnych pól.

4. ADRESY. Adres obiektu i adres parkingu to dwa różne pola. Jeśli dokument
   podaje dwa adresy, nie wybierasz jednego — wypełniasz oba. Adres obiektu
   to ten, pod którym się śpi.

5. KOD DOSTĘPU. Przepisujesz tylko ciąg znaków podany jako kod, bez spacji
   i bez otaczającego zdania. Jeśli dokument mówi, co zrobić, gdy kod nie
   działa, to nie jest drugi kod — pole kodu zapasowego pozostaje puste,
   chyba że podano osobną wartość.

6. DATY I GODZINY. Data rozpoczęcia i zakończenia to daty z rezerwacji, nie
   data wystawienia dokumentu i nie termin anulowania. Godziny zameldowania
   i wymeldowania mają własne pola.

7. PŁATNOŚĆ W RATACH. Jeśli część kwoty jest już zapłacona, a resztę dostawca
   pobierze automatycznie w podanym dniu, zapisujesz kwotę zapłaconą, kwotę
   pozostałą i datę obciążenia. To jest informacja, od której zależy, czy
   karta musi być aktywna w styczniu.

8. CZEGO NIE MA, TEGO NIE WPISUJESZ. Potwierdzenie lotu nie zawiera kodu do
   skrytki. Potwierdzenie noclegu nie zawiera numeru rejestracyjnego.
   Puste pole jest poprawną odpowiedzią.

9. Nie tłumaczysz nazw własnych. Nazwa obiektu, lotniska i miejscowości
   zostaje w oryginale, razem ze znakami ø, å, æ.

FLAGA DO CZŁOWIEKA — ustawiasz, gdy:
- auto nie ma potwierdzonego ubezpieczenia wkładu własnego albo ubezpieczenia
  szyb przy oponach z kolcami,
- dokument wymaga działania przed wyjazdem (karta kredytowa na kaucję,
  dopłata pobierana automatycznie, prawo jazdy do okazania),
- dokument zawiera warunek, którego niespełnienie unieważnia ubezpieczenie,
- zakres dat nie pasuje do żadnego wyjazdu z kalendarza.
```

---

## Część z danymi

```
POTWIERDZENIE
Od: {nadawca}
Temat: {temat}

{tresc}
```

Przed podaniem na wejście: **zdekoduj artefakty quoted-printable**
(`=C3=B8` → `ø`, `=3D` → `=`). Bez tego nazwy miejscowości wchodzą do arkusza
wyjazdu w postaci, której nikt nie wpisze w nawigację.

---

## Przypisanie do wyjazdu

Robi to kod, nie model: po zakresie dat z `wyjazdy.yaml`, z tolerancją dwóch dni.
Model nie dostaje listy wyjazdów, bo wtedy dopasowuje nazwę na podstawie
podobieństwa kierunku, a nie daty — i potwierdzenie lotu na Lofoty w lutym 2028
wpada do wyjazdu z lutego 2027.

---

## Uwagi do kalibracji

| objaw | poprawka |
|---|---|
| kwota = taryfa lotnicza, nie suma | zasada 1; w schemacie opisać pole jako „kwota całkowita do zapłaty, z dokumentu" |
| kaucja 15 000 jako koszt wynajmu | zasada 2 — wymaga osobnego pola `kaucja`, inaczej nie ma gdzie jej zapisać |
| adres parkingu jako adres noclegu | zasada 4; sprawdzić, czy pole `adres_parkingu` istnieje w schemacie |
| kod do skrytki z całym zdaniem | zasada 5; dodatkowo walidacja w kodzie: kod to 4–8 znaków alfanumerycznych |
| drugi, nieistniejący kod dostępu | zasada 5, zdanie drugie — najczęstszy błąd na tym korpusie |
| PNR z cyrylicką literą przechodzi dalej | normalizacja znaków wprowadzających w błąd w kodzie, przed zapisem; model tego nie wyłapie |
| data wystawienia jako data rozpoczęcia | zasada 6 |
