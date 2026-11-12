# Wdrożenie produkcyjne

Dwie osobne rzeczy: **uruchomienie u siebie na stałe** i **opublikowanie kodu
do pobrania**. Pierwsza jest w tym pliku, druga na końcu.

---

# Część A. Uruchomienie u siebie

## Zasada etapowa

Nie włączaj wszystkiego naraz. Każdy etap ma warunek przejścia do następnego
i każdy można cofnąć bez konsekwencji.

| Etap | Co robi | Warunek przejścia dalej |
|---|---|---|
| 0 | sprawdzenie gotowości | `sprawdz_gotowosc.py` kończy się „GOTOWE" |
| 1 | przebieg na sucho na prawdziwej skrzynce | typy wiadomości rozpoznane poprawnie |
| 2 | drafty w skrzynce, nic więcej | pięć draftów z rzędu wysyłalnych po jednej poprawce |
| 3 | umowy i rejestr | jedna umowa sprawdzona ręcznie linia po linii |
| 4 | wykaz dla UFG | plik zgodny z tym, który dziś wrzucasz ręcznie |
| 5 | harmonogram, codziennie automatycznie | dwa tygodnie bez niespodzianek |

### Etap 0 — gotowość

```powershell
python skrypty\sprawdz_gotowosc.py
```

Sprawdza: pliki konfiguracyjne, dane firmy, gwarancję i polisę, dostępność
modelu w Ollamie, bazę wiedzy i jej indeks, szablon umowy, LibreOffice,
mapowanie kolumn UFG, bazę SQLite, logowanie do skrzynki, folder wersji
roboczych, przykłady stylu z folderu Wysłane.

Rozróżnia **blokady** od **ostrzeżeń**. Ostrzeżenie znaczy „zadziała, ale
umowa wyjdzie z luką" albo „drafty będą gorsze". Blokada znaczy „nie ruszaj".

### Etap 1 — na sucho

```powershell
python skrypty\sprawdz_maile.py --na-sucho --dni 14
```

Nic nie zapisuje i nie tworzy draftów. Czytasz wypisane typy wiadomości
i sprawdzasz, czy się zgadzają. Jeśli jakiś mail jest zaklasyfikowany źle,
popraw `prompty\klasyfikacja.md` i powtórz. To jest pętla kalibracji i warto
w niej posiedzieć — klasyfikacja decyduje o wszystkim dalej.

### Etap 2 — tylko drafty

```powershell
python skrypty\sprawdz_maile.py --dni 7
```

Drafty lądują w wersjach roboczych. **Czytaj każdy przed wysłaniem.** Przez
pierwszy tydzień notuj w trzech kubełkach: wysłać bez zmian / poprawić
drobiazg / napisać od nowa. Ten rozkład jest potem jedyną sensowną miarą
jakości draftów i wchodzi do zgłoszenia konkursowego.

Jeśli wiele draftów ma znacznik `[DO UZUPEŁNIENIA]`, problem jest w bazie
wiedzy, nie w modelu. Dopisz brakującą treść do `wiedza\` i przebuduj indeks.

### Etap 3 — umowy

```powershell
python skrypty\zrob_umowe.py --lista
python skrypty\zrob_umowe.py 1 dolomity-jesien-2026
```

Pierwszą umowę przeczytaj całą, porównując z wzorcem. Sprawdź zwłaszcza §8
(gwarancja i polisa) i §2 (rachunek), bo te dane pochodzą z `config.yaml`,
a nie ze zgłoszenia.

Generator na końcu wypisuje pola puste i nieuzupełnione. Dopóki ta lista nie
jest pusta, umowa nie jest gotowa do podpisu.

### Etap 4 — wykaz dla UFG

```powershell
python skrypty\zrob_csv_ufg.py --pola
python skrypty\zrob_csv_ufg.py 2026 10
```

**Porównaj wynik z plikiem, który wrzuciłaś do portalu ostatnio ręcznie.**
Kolumny i ich kolejność ustaw w `config.yaml` tak, żeby pliki się zgadzały.
Dopiero gdy się zgadzają, przestań robić to ręcznie.

Po wysłaniu do portalu:

```powershell
python skrypty\zrob_csv_ufg.py 2026 10 --oznacz-zgloszone
```

### Etap 5 — harmonogram

Codzienne przejście po skrzynce przez Harmonogram zadań Windows.

1. Menu Start → „Harmonogram zadań" → **Utwórz zadanie** (nie „podstawowe").
2. Zakładka **Ogólne**: nazwa `Biuro Bielik - poczta`, zaznacz
   „Uruchom niezależnie od tego, czy użytkownik jest zalogowany" tylko jeśli
   Ollama też startuje jako usługa; w przeciwnym razie zostaw
   „Uruchom tylko, gdy użytkownik jest zalogowany".
3. Zakładka **Wyzwalacze** → Nowy → Codziennie, godzina np. 8:00.
4. Zakładka **Akcje** → Nowy:
   - Program: `C:\Users\kasia\Desktop\biuro-bielik\.venv\Scripts\python.exe`
   - Argumenty: `skrypty\sprawdz_maile.py --dni 3`
   - Rozpocznij w: `C:\Users\kasia\Desktop\biuro-bielik`
5. Zakładka **Warunki**: odznacz „Uruchamiaj tylko wtedy, gdy komputer jest
   zasilany z sieci", jeśli to laptop.

Podaj pełną ścieżkę do `python.exe` z katalogu `.venv`, nie samo `python` —
zadanie nie zna Twojego środowiska. Nie wywołuj niczego ze `Scripts\*.exe`
poza `python.exe`: Smart App Control blokuje niepodpisane pliki wykonywalne.

Drugie zadanie, raz w tygodniu, na kopię zapasową:

- Argumenty: `skrypty\kopia_zapasowa.py --katalog "D:\kopie-biuro"`

Trzecie, raz w miesiącu, na retencję — ale **bez** `--usun`, żeby najpierw
zobaczyć, co by zniknęło:

- Argumenty: `skrypty\retencja.py --ustaw-terminy`

## Kopie zapasowe

```powershell
python skrypty\kopia_zapasowa.py
python skrypty\kopia_zapasowa.py --katalog "D:\kopie-biuro" --ile-trzymac 30
```

Baza SQLite jest źródłem prawdy dla rejestru umów. Jej utrata to nie
niedogodność, to brak danych do obowiązku sprawozdawczego. Kopia robiona jest
przez `VACUUM INTO`, czyli spójnie, nawet jeśli w tym czasie coś pisze do bazy —
zwykłe skopiowanie pliku `.sqlite` podczas zapisu daje archiwum, które może
się nie otworzyć.

Archiwum zawiera PESEL-e uczestników. Trzymaj je tam, gdzie trzymasz umowy.
`.env` nie wchodzi do kopii, bo to sekret, nie dane.

## Retencja danych wrażliwych

```powershell
python skrypty\retencja.py                   # podgląd
python skrypty\retencja.py --ustaw-terminy   # wypełnij daty z wyjazdy.yaml
python skrypty\retencja.py --usun            # faktyczne usunięcie
```

PESEL i numer dokumentu są potrzebne do polisy i umowy. Po wyjeździe nie są
potrzebne do niczego. Domyślnie termin to 30 dni po zakończeniu wyjazdu.

Usunięcie zdejmuje **tylko** dane wrażliwe. Rejestr umów i dane kontaktowe
zostają, bo wymaga ich obowiązek sprawozdawczy.

Skrypt nigdy nie usuwa niczego bez `--usun`. To narzędzie, nie automat.

## Gdy coś pójdzie nie tak

**Drafty trafiają w zły folder.** `sprawdz_gotowosc.py` wypisuje, który folder
został rozpoznany jako wersje robocze. Jeśli to nie ten, czego się spodziewasz,
nazwa folderu w Twojej skrzynce nie ma flagi `\Drafts` — ustaw
`poczta.folder_wejsciowy` i zgłoś, który to folder.

**Ten sam mail obrobiony dwa razy.** Nie powinno się zdarzyć: aplikacja trzyma
własną listę przetworzonych identyfikatorów w tabeli `maile_przetworzone`
i nie dotyka flag na serwerze. Jeśli chcesz przetworzyć mail ponownie, usuń
jego wiersz z tej tabeli.

**Model nie odpowiada po restarcie komputera.** Ollama musi działać przed
uruchomieniem skryptu. Sprawdź `ollama list`.

**Pierwszy przebieg dnia jest wolny.** Model ładuje się do pamięci karty przy
pierwszym zapytaniu. To normalne i nie wpływa na kolejne.

**Umowa wyszła z luką.** Generator wypisał ją na liście pól nieuzupełnionych —
ta lista jest po to, żeby nie trafiła do uczestnika. Uzupełnij `config.yaml`
albo `wyjazdy.yaml` i wygeneruj ponownie.

---

# Część B. Publikacja kodu do pobrania

## Co nie może wyjechać

Są już w `.gitignore`, ale sprawdź **przed** pierwszym wysłaniem:

| Plik | Dlaczego |
|---|---|
| `.env` | hasło aplikacji do skrzynki |
| `config.yaml` | NIP, numery gwarancji i polisy, numer rachunku |
| `wyjazdy.yaml` | ceny i warunki handlowe |
| `dane/` | PESEL-e uczestników, umowy, kopie zapasowe |
| `wsad/`, `szablony/*.docx` | wzorzec umowy firmy |
| `wiedza/` poza README i przykładem | treść oferty |

Kontrola automatyczna jest w `.github/workflows/testy.yml` — zadanie
`brak-danych-firmy` wywala build, jeśli którykolwiek z tych plików trafi do
repozytorium, i sprawdza, czy wszystkie 11-cyfrowe numery w kodzie mają
zakodowaną datę urodzenia `00-00`, czyli nieistniejącą.

## Kroki

```powershell
cd C:\Users\kasia\Desktop\biuro-bielik
git init
git add -A
git status          # PRZECZYTAJ listę przed commitem
```

Na liście nie może być `.env`, `config.yaml`, `wyjazdy.yaml`, `dane/`, `wsad/`
ani żadnego `.docx`. Jeśli coś z tego widzisz, zatrzymaj się i popraw
`.gitignore`.

```powershell
git commit -m "Biuro na Bieliku: lokalne back office dla biura podrozy"
git branch -M main
gh repo create biuro-bielik --public --source=. --push
```

Bez `gh`: utwórz repozytorium na GitHubie przez stronę, potem
`git remote add origin <adres>` i `git push -u origin main`.

## Gdyby sekret już wyjechał

Usunięcie pliku kolejnym commitem **nie wystarcza** — zostaje w historii.
Trzeba zmienić hasło aplikacji w koncie Google (stare natychmiast przestaje
działać) i przepisać historię albo usunąć i utworzyć repozytorium od nowa.
Zmiana hasła jest ważniejsza i szybsza niż czyszczenie historii.

## Wydanie do pobrania bez gita

Część osób nie używa gita. Zrób wydanie:

```powershell
git tag v0.1.0
git push origin v0.1.0
gh release create v0.1.0 --title "v0.1.0" --notes-file WYDANIE.md
```

GitHub sam dołączy archiwum `.zip` z kodem. Nie dołączaj własnego archiwum
ręcznie — łatwo spakować do niego `config.yaml`.

## Co powinna zobaczyć osoba, która pobiera

Pierwsze polecenie po pobraniu to `python skrypty/sprawdz_gotowosc.py`.
Wypisze dokładnie, czego brakuje, i co zrobić. To jest cała instrukcja
instalacji — reszta jest w README.

Druga rzecz: `python testy/uruchom_wszystkie.py`. Działa bez modelu i bez
sieci, więc ktoś może sprawdzić, że kod jest sprawny, jeszcze przed pobraniem
siedmiu gigabajtów wag.

Trzecia: harness ewaluacyjny. Nikt nie powinien ufać cudzym liczbom
skuteczności, więc razem z aplikacją dostaje narzędzie do zmierzenia jej na
własnej poczcie.
