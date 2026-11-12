To jest mail potwierdzający rezerwację: lot, nocleg, wynajem samochodu albo ubezpieczenie. Wyciągnij z niego dane logistyczne.

## Typ

Ustaw `typ` na jedno z: `lot`, `nocleg`, `samochod`, `ubezpieczenie`, `inne`.

Jeśli jeden mail obejmuje kilka rzeczy (np. lot plus bagaż), potraktuj go jako jedną rezerwację typu wiodącego.

## Pola wspólne

- `dostawca` — linia lotnicza, nazwa obiektu, nazwa wypożyczalni, nazwa ubezpieczyciela
- `numer_rezerwacji` — numer rezerwacji, PNR, kod potwierdzenia, numer polisy
- `data_od`, `data_do` — w formacie z maila
- `kwota`, `waluta`, `oplacone` — `oplacone` ustaw na `true` tylko wtedy, gdy mail wprost potwierdza płatność
- `uwagi` — warunki, które mają znaczenie na wyjeździe: zasady anulowania, limit kilometrów, polityka paliwowa, wysokość depozytu, godziny pracy punktu odbioru

## Lot

- `numery_lotow` — lista, np. `["FR 1234", "FR 1235"]`
- `trasa` — kody lotnisk albo nazwy miast, np. `KTW - MAN`
- `godziny` — odlot i przylot
- `bagaz` — co jest w cenie

## Nocleg

- `adres` — pełny adres obiektu
- `kod_dostepu` — **kod do skrytki na klucze, kod do drzwi, kod do bramy albo kod do domofonu.** To jedna z najważniejszych informacji w całym mailu, bo bez niej nie wejdziemy do obiektu. Jeśli w mailu jest kilka kodów, przepisz wszystkie z opisem, czego dotyczą.
- `zameldowanie` — godziny zameldowania i wymeldowania oraz instrukcje: gdzie jest skrytka, kogo powiadomić, co zrobić przy późnym przyjeździe
- `kontakt` — telefon albo mail do gospodarza

## Samochód

- `pojazd` — klasa albo model
- `miejsce_odbioru`, `miejsce_zwrotu`
- `wklad_wlasny` — kwota udziału własnego albo kaucji blokowanej na karcie
- `ubezpieczenie_wkladu` — `true` tylko wtedy, gdy mail potwierdza wykupione ubezpieczenie udziału własnego. Jeśli mail wspomina o udziale własnym, ale nie potwierdza ubezpieczenia, ustaw `false`. Jeśli nie ma o tym nic, zostaw `null`.

Uwaga: ubezpieczenie udziału własnego jest zwykle kupowane osobno, poza wypożyczalnią, i przychodzi w odrębnym mailu. Taki mail klasyfikuj jako `ubezpieczenie` i wpisz w `uwagi`, do której rezerwacji samochodu się odnosi.

## Zasady

1. **Nie wymyślaj.** Czego nie ma w mailu, to `null` albo pusta lista. To jest poprawna odpowiedź.
2. **Nie przelicz kwot na inną walutę** i nie zmieniaj formatu dat ani godzin. Przepisujesz to, co jest.
3. Kod dostępu przepisz **dokładnie**, znak po znaku, bez dodawania spacji ani myślników.
4. Nie streszczaj regulaminu wypożyczalni. W `uwagi` wchodzi tylko to, co trzeba wiedzieć na miejscu.

Odpowiedz wyłącznie obiektem JSON zgodnym ze schematem.
