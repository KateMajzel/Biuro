# Prompt: klasyfikacja wiadomości

## Dlaczego dwa przebiegi, a nie jeden

W korpusie jest 19 etykiet szczegółowych na 40 wiadomości — dwanaście z nich występuje
raz. Dawanie modelowi 7B listy dziewiętnastu opcji w jednym zapytaniu daje wynik, którego
nie da się zmierzyć i którego nie da się poprawić: nie wiadomo, czy błąd to pomyłka
klasyfikacji, czy nieostra definicja etykiety.

Dlatego klasyfikacja ma dwa poziomy:

**Przebieg 1 — trasa (6 klas).** To jedyna decyzja, która naprawdę coś zmienia: czy
wiadomość idzie do ekstrakcji, do bazy wiedzy, do rejestru płatności, czy wprost do
człowieka. Sześć klas przy 40 wiadomościach to 3–13 przykładów na klasę, więc wynik
ma jakąkolwiek wymowę.

**Przebieg 2 — etykieta szczegółowa.** Uruchamiany tylko dla klas `zgloszenie`
i `pieniadze`, gdzie od etykiety zależy szablon draftu. Lista opcji ma wtedy 3–4
pozycje, nie 19. Dla pozostałych klas etykietę szczegółową ustala kod, bo wynika
jednoznacznie z trasy.

---

## Przebieg 1 — część systemowa

```
Czytasz jedną wiadomość przychodzącą do biura podróży i przypisujesz ją do
jednej z sześciu tras. Wybierasz dokładnie jedną.

zgloszenie
  Klient chce jechać, zapisuje się, przesyła dane do umowy albo zmienia dane,
  które już podał. Także wtedy, gdy nie napisał, o który wyjazd chodzi.

pytanie
  Pyta o wyjazd, cenę, sprzęt, warunki, program — i nie zapisuje się.
  Także pytania techniczne i pytania po wyjeździe o rzeczy praktyczne.

pieniadze
  Faktura, potwierdzenie przelewu, wpłata która się nie zgadza, prośba
  o przesunięcie terminu płatności.

sprawa_trudna
  Rezygnacja, reklamacja, żądanie zwrotu, skarga na obsługę, żądanie dotyczące
  wizerunku albo danych osobowych, oraz każda sprawa osoby, która jest
  w tej chwili w trakcie wyjazdu.

biznes
  Wycena dla grupy albo firmy, propozycja współpracy, barteru, patronatu,
  zapytanie od redakcji.

nieobslugiwane
  Reklama i oferty handlowe skierowane do nas, sprawa innej firmy wysłana
  pomyłkowo, wiadomość wygenerowana przez serwer poczty, oraz wiadomość,
  która odwołuje się do ustaleń nieobecnych w skrzynce i bez nich nie znaczy nic.

ROZSTRZYGANIE PRZYPADKÓW GRANICZNYCH:

- Jeśli wiadomość jest i zgłoszeniem, i czymś innym, trasa to zgloszenie,
  a drugą sprawę wpisujesz do sprawy_dodatkowe.
- Jeśli wiadomość jest i pytaniem, i rezygnacją albo reklamacją, trasa to
  sprawa_trudna. Trudniejsza sprawa wygrywa.
- Pochwała na początku i podziękowanie na końcu nie są treścią wiadomości.
  Patrzysz na to, czego klient żąda w środku.
- Reklama wspominająca wyjazdy, zorzę i fotografię to nadal reklama.
  Patrzysz, kto komu coś oferuje.
- Wiadomość od serwera o niedostarczeniu poczty to nieobslugiwane, nawet
  jeśli zawiera w cytacie pełną treść naszego zgłoszenia.

SPRAWY DODATKOWE:
Jeśli w wiadomości jest więcej niż jedna niezależna sprawa, wymieniasz
pozostałe. Dwa pytania o ten sam wyjazd to jedna sprawa. Zgłoszenie plus
propozycja współpracy to dwie. Podziękowanie plus żądanie plus pytanie
o przyszły sezon to trzy.

LICZBA PYTAŃ:
Podajesz, na ile osobnych pytań trzeba odpowiedzieć. Liczysz pytania
wymagające odrębnej odpowiedzi, nie znaki zapytania.

PILNOŚĆ:
Ustawiasz pilnosc na "pilna" tylko wtedy, gdy klient jest w trakcie wyjazdu
albo w podróży i sprawa traci sens po kilku godzinach. Zbliżający się termin
płatności albo deadline redakcji nie są pilnością w tym znaczeniu.

FLAGA DO CZŁOWIEKA:
Ustawiasz, gdy trasa to sprawa_trudna albo biznes, oraz gdy:
- klient pyta o gwarancje, ubezpieczenie, rejestr organizatorów albo TFG,
- oczekuje zapewnienia o pogodzie, zorzy albo obecności zwierząt,
- uczestnik jest niepełnoletni,
- wpłata przyszła z konta innej osoby albo bez numeru umowy,
- w zgłoszeniu są dane, które się wzajemnie wykluczają,
- wiadomość nie ma kontekstu i bez niego nie da się jej zrozumieć,
- zgłoszenie nie zawiera żadnego działającego kontaktu do klienta.
```

## Przebieg 1 — część z danymi

```
Od: {nadawca}
Temat: {temat}

{tresc}
```

Cytowana historia **nie wchodzi** do klasyfikacji. Jedyny wyjątek to wiadomość
o treści krótszej niż jedno zdanie — wtedy dokładamy pierwszy poziom cytatu,
oznaczony, bo inaczej „Tak, biorę." nie daje się zaklasyfikować.

---

## Przebieg 2 — etykieta szczegółowa

Uruchamiany warunkowo, z listą zawężoną do trasy z przebiegu 1.

**Dla trasy `zgloszenie`:**
```
Wybierz jedną:
  zgloszenie_nowe       — klient zapisuje się pierwszy raz
  uzupelnienie_danych   — dosyła dane do zgłoszenia, które już istnieje
  zmiana_danych         — zmienia dane, które wcześniej podał (nazwisko, dokument)
```

**Dla trasy `pieniadze`:**
```
Wybierz jedną:
  faktura                    — prosi o fakturę albo podaje dane do faktury
  platnosc_potwierdzenie     — zgłasza, że zapłacił
  platnosc_niezgodnosc       — twierdzi, że zapłacił, a my tego nie widzimy
  platnosc_prosba_o_zmiane   — prosi o inny termin albo inny podział płatności
```

**Dla pozostałych tras** etykietę ustala kod:
`sprawa_trudna` → po słowach kluczowych w temacie i pierwszym akapicie
(`rezygnacja`, `reklamacja`, `wizerunek`, `pilne`); `biznes` → `oferta_grupowa`,
gdy w treści jest liczba osób większa od 5, inaczej `wspolpraca_media`;
`nieobslugiwane` → `systemowy` dla nadawcy `mailer-daemon`/`postmaster`,
`inne_wymaga_kontekstu`, gdy treść ma mniej niż 200 znaków i odwołuje się do
rozmowy, w pozostałych przypadkach `spam` albo `nie_nasza_sprawa` po tym,
czy nadawca oferuje nam coś, czy czegoś od nas chce.

---

## Czego ten korpus nie zmierzy

Trafność per etykieta szczegółowa. Dwanaście klas ma po jednym przykładzie —
jedna pomyłka to 0% dla tej klasy, jedno trafienie to 100%. Obie liczby są
bez wartości. Mierzalna jest tylko trasa i tylko w sumie.

Drugie ograniczenie: korpus jest syntetyczny i napisany przez jedną osobę, więc
rozkład etykiet nie odpowiada sezonowi. Na prawdziwej skrzynce `zgloszenie`
i `pytanie` będą zdecydowanie częstsze, a `sprawa_trudna` rzadsza — co znaczy,
że czułość flagi do człowieka zmierzona tutaj (20 przypadków) jest zmierzona
na próbie wzbogaconej celowo i nie przeniesie się wprost.
