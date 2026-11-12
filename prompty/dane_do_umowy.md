Uczestnik odesłał mailem dane potrzebne do przygotowania umowy i wykupienia polisy ubezpieczeniowej. Wyciągnij je.

Pola:

- `imie`, `nazwisko` — tylko jeśli uczestnik podał je w tym mailu (bo bywają inne niż w zgłoszeniu)
- `ulica` — nazwa ulicy z numerem domu i lokalu
- `kod_pocztowy`, `miasto`
- `data_urodzenia` — w formacie, w jakim podał nadawca
- `pesel` — jedenaście cyfr
- `numer_dokumentu` — numer dowodu osobistego albo paszportu

Zasady:

1. **Nie wymyślaj.** Czego nie ma w mailu, to `null`. To jest poprawna odpowiedź.
2. **Nie przeliczaj i nie wnioskuj.** Nie wyciągaj daty urodzenia z numeru PESEL, nawet jeśli potrafisz. Nie uzupełniaj miasta na podstawie kodu pocztowego. Jeśli uczestnik podał tylko jedno z dwóch, drugie zostaje `null`.
3. Nie poprawiaj formatu. Przepisujesz dokładnie to, co napisał nadawca.
4. Jeśli w mailu jest kilka numerów jedenastocyfrowych, wybierz ten opisany jako PESEL. Jeśli żaden nie jest opisany, zostaw `null` — pomyłka w tym polu jest gorsza niż brak.
5. Nie komentujesz, nie podsumowujesz, nie dopisujesz uwag.

Odpowiedz wyłącznie obiektem JSON zgodnym ze schematem.
