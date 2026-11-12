# Baza wiedzy

To jedyne źródło faktów dla modułu pisania odpowiedzi i dla czatu. Model nie korzysta
z własnej wiedzy o Arktyce, cenach czy terminach — tylko z tego, co jest w tym folderze.

**Jakość tych plików decyduje o jakości draftów bardziej niż wybór modelu.**

## Jak to wypełnić

1. Zrzuć treść strony: `python skrypty/zrzut_strony.py`
2. Przejrzyj powstałe pliki i usuń śmieci: menu, stopki, komunikaty o cookies, powtórzone bloki.
3. Dopisz ręcznie to, czego na stronie nie ma, a o co ludzie pytają w mailach.
4. Przebuduj indeks: `python skrypty/indeksuj.py`

## Co warto mieć

Pliki markdown, jeden temat na plik, z nagłówkami. Nagłówki są ważne, bo po nich
dzielimy tekst na fragmenty i po nich model wskazuje źródło odpowiedzi.

Przydatne pliki:

- `00-oferta-*.md` — opis każdego wyjazdu osobno: program, termin, cena, co wliczone, co nie
- `10-faq.md` — pytania, które powtarzają się w mailach, z Twoimi odpowiedziami
- `20-sprzet.md` — co zabrać, jaki sprzęt fotograficzny, ubranie, warunki
- `30-warunki.md` — płatności, zaliczki, rezygnacja, ubezpieczenie
- `40-regulamin.md` — regulamin uczestnictwa
- `50-logistyka.md` — dojazd, zakwaterowanie, wyżywienie

## Czego tu nie wkładać

Danych osobowych uczestników, skanów umów, list nazwisk. Ten folder jest kontekstem
dla modelu, nie archiwum. Dane uczestników żyją w bazie SQLite.
