---
wyjazd: Bieszczady — przykład
slug: bieszczady-przyklad
termin_od: 2027-05-14
termin_do: 2027-05-18
cena: 2400
waluta: PLN
status_sprzedazy: dostepny
zrodlo: https://przyklad.example/produkt/bieszczady/
pobrano: 2026-11-08
---

# Bieszczady — plik przykładowy

**To jest przykład formatu, nie prawdziwa oferta.** Firma, ceny i terminy są
wymyślone. Skasuj ten plik, gdy wstawisz swoje — albo zostaw, bo indeks i tak
go rozpozna jako przykładowy po slugu.

Plik pokazuje dwie rzeczy: jak wygląda nagłówek z metadanymi i jak dzielić
treść na sekcje.

## Po co jest nagłówek na górze

To, co stoi między liniami `---`, nie jest ozdobą. Indeks czyta te pola
i **dokleja je do każdego fragmentu tego pliku**, zanim trafi do modelu.
Dzięki temu model widzi przy każdym akapicie, o który wyjazd chodzi, w jakim
terminie i za ile — nawet gdy sam akapit mówi tylko „zbiórka o ósmej".

Najważniejsze pole to `status_sprzedazy`. Jedyna wartość, która pozwala pisać
o wolnych miejscach, to **`dostepny`**. Każda inna — `brak_w_magazynie`,
`wycofany`, cokolwiek wpiszesz — dokłada do fragmentu ostrzeżenie
„SPRZEDAŻ ZAMKNIĘTA", a model wtedy **nie potwierdzi dostępności**, nie
zaproponuje zapisu i nie poda ceny jako aktualnej; zgłosi sprawę do decyzji
człowieka.

Ta domyślność jest celowa: literówka w statusie zamyka sprzedaż, a nie
otwiera ją. Bez tego pola model mógłby w dobrej wierze zaprosić kogoś na
wyjazd, którego już nie sprzedajesz.

## Cena zawiera

- 4 noclegi w pokojach dwuosobowych
- transport na miejscu
- zajęcia warsztatowe, 3 sesje

Nagłówki sekcji są granicami fragmentów. Model, odpowiadając na pytanie
„co jest w cenie", wskaże jako źródło właśnie `Cena zawiera` — i ta nazwa
pojawi się w logu, nigdy w treści maila do klienta.

## Cena nie zawiera

- dojazdu do miejsca zbiórki
- posiłków
- ubezpieczenia sprzętu fotograficznego

## Warunki uczestnictwa

Zaliczka 600 PLN przy zapisie, dopłata do 30 dni przed terminem.
Rezygnacja do 45 dni przed terminem — zwrot zaliczki w całości.

## Czego w tym pliku NIE MA

Ta sekcja jest ważniejsza, niż wygląda, i warto ją mieć w każdym pliku.

- nazwiska prowadzącego
- szczegółowego programu dzień po dniu
- minimalnej liczby uczestników

Model czyta ten spis i przy pytaniu o którąkolwiek z tych rzeczy napisze
`[DO UZUPEŁNIENIA]` zamiast wymyślić odpowiedź. Brak takiej listy nie znaczy,
że model się powstrzyma — znaczy, że nie wie, czego nie wie.
