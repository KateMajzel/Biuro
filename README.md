# Biuro na Bieliku

Zaplecze biurowe dla małej firmy, które działa w całości na jednym komputerze
i korzysta z polskiego modelu językowego [Bielik](https://bielik.ai),
uruchamianego lokalnie przez Ollamę. Dane klientów nie opuszczają maszyny.

Program powstał dla biura podróży **Warsztaty Arktyczne** (organizator
turystyki, warsztaty fotograficzne) i jest zrobiony tak, żeby inna mała firma
mogła go pobrać i dopasować do siebie przez pliki tekstowe, bez pisania kodu.

## Co robi

Czyta skrzynkę pocztową firmy i prowadzi zgłoszenie od maila do dokumentów:

| Krok | Co powstaje |
|---|---|
| Sprawdzenie poczty | zgłoszenia zapisane w lokalnej bazie i robocze wersje odpowiedzi w tym samym wątku |
| Umowa | plik `.docx` (i PDF) z Twojego wzorca, z kolejnym numerem, wpisany do rejestru |
| Lista uczestników | arkusz Excel w dwóch wariantach: pełny do biura i bez danych wrażliwych do wysłania |
| Odprawa przedwyjazdowa | robocza wersja maila do uczestnika |
| Wykaz umów | plik CSV za wybrany miesiąc, w układzie kolumn, który sam ustawiasz |

Czego nie robi: **nie wysyła żadnej wiadomości**. Odpowiedzi czekają jako
wersje robocze w skrzynce, a wysyła je człowiek. Sprawy z zamkniętej listy
szesnastu sytuacji (między innymi rezygnacja, reklamacja, niezgodna wpłata,
dane, które nie mogą być prawdziwe) program oznacza „do człowieka”
i nie przygotowuje do nich odpowiedzi. Listę znajdziesz w `prompty/klasyfikacja.md`.

## Czego potrzebujesz

| | |
|---|---|
| System | Windows, Linux albo macOS |
| Python | 3.11 lub nowszy |
| [Ollama](https://ollama.com) | z modelem Bielik i modelem do wyszukiwania w bazie wiedzy |
| Karta graficzna | 8 GB VRAM dla Bielika 7B; na słabszej wariant 4.5B |
| Skrzynka | IMAP z hasłem aplikacji (nie zwykłym hasłem do konta) |
| LibreOffice | opcjonalnie, do zapisu umów w PDF |

## Instalacja

```bash
git clone https://github.com/KateMajzel/Biuro.git biuro-bielik
cd biuro-bielik

python -m venv .venv
.venv\Scripts\Activate.ps1          # Linux i macOS: source .venv/bin/activate
python -m pip install -r requirements.txt

ollama pull SpeakLeash/bielik-minitron-7B-v3.0-instruct:Q8_0
ollama pull bge-m3
```

Na Windowsie pisz `python -m pip`, nie `pip`: Smart App Control potrafi
zablokować `pip.exe`. Jeśli pobierasz repozytorium jako ZIP, zdejmij z plików
oznaczenie „z internetu”: `Get-ChildItem -Recurse -File | Unblock-File`.

Sprawdź, czy kod jest sprawny. Testy nie potrzebują modelu ani sieci:

```bash
python testy/uruchom_wszystkie.py
```

## Co musisz dodać albo zmienić

W repozytorium nie ma żadnych danych firmy. Zanim program zrobi cokolwiek
pożytecznego, uzupełniasz sześć rzeczy, w tej kolejności:

| # | Plik | Jak powstaje | Co wpisujesz |
|---|---|---|---|
| 1 | `.env` | kopia `.env.example` | adres skrzynki i hasło aplikacji |
| 2 | `config.yaml` | kopia `config.example.yaml` | dane firmy, rachunek, gwarancja, podpis pod odpowiedziami, wzór numeru umowy, kolumny wykazu |
| 3 | `wyjazdy.yaml` | kopia `wyjazdy.example.yaml` | to, co sprzedajesz: nazwa, termin, cena, program, warunki |
| 4 | `wiedza/*.md` | piszesz sam, wzór w `wiedza/00-przyklad.md` | fakty o ofercie; jedyne źródło, z którego model pisze odpowiedzi |
| 5 | `szablony/umowa.docx` | `python skrypty/zbuduj_szablon_umowy.py twoja-umowa.docx` | Twój wzorzec umowy z polami w nawiasach kwadratowych |
| 6 | pola formularza | tabela na początku `biuro/mail/pipeline.py` | etykiety, które wysyła formularz na Twojej stronie |

Po każdej zmianie w `wiedza/` przebuduj indeks: `python skrypty/indeksuj.py`.

Punkt 6 wymaga wyjaśnienia. Program czyta zgłoszenie z wierszy
„Etykieta: wartość” i oczekuje takich etykiet jak `Wyjazd`, `Termin`,
`Imię i nazwisko`, `PESEL`, `Adres zamieszkania`, `E-mail`, `Telefon`,
`Dokument`. Jeśli Twój formularz nazywa pola inaczej, dopisz swoje nazwy
w tabelach `_PROSTE` i `_DO_UWAG`. Wartość pola `Wyjazd` musi dać się
dopasować do nazwy albo klucza wpisu w `wyjazdy.yaml`.

Szczegóły każdego z tych kroków, razem z pułapkami, są w
[DLA-TWOJEJ-FIRMY.md](DLA-TWOJEJ-FIRMY.md). Tam też jest rozdział dla firm,
które nie są biurem podróży.

Gdy wszystko jest wpisane, jedno polecenie mówi, czego jeszcze brakuje:

```bash
python skrypty/sprawdz_gotowosc.py
```

## Codzienna praca

Program obsługuje się z okna:

```bash
python skrypty/panel.py
```

| Przycisk | Co robi | Gdzie szukać wyniku |
|---|---|---|
| Sprawdź pocztę | czyta wiadomości z wybranej liczby dni, zapisuje zgłoszenia, przygotowuje odpowiedzi | wersje robocze w skrzynce |
| Lista zgłoszeń | pokazuje zgłoszenia i wyjazdy | okno panelu |
| Wystaw umowę | wybierasz osobę po nazwisku; wyjazd wynika ze zgłoszenia | `dane/umowy/` |
| Lista uczestników | wybierasz wyjazd; powstają oba warianty arkusza | `dane/listy/` |
| Odprawa przedwyjazdowa | wybierasz osobę | `dane/odprawy/` |
| Wykaz umów (CSV) | wybierasz rok i miesiąc zawarcia umów | `dane/ufg/` |

Skrót na pulpicie w Windowsie (uruchom raz, w katalogu projektu):

```powershell
$k=(Get-Location).Path; $s=(New-Object -ComObject WScript.Shell).CreateShortcut("$env:USERPROFILE\Desktop\Biuro.lnk"); $s.TargetPath="$k\.venv\Scripts\pythonw.exe"; $s.Arguments="`"$k\skrypty\panel.py`""; $s.WorkingDirectory=$k; $s.IconLocation="$k\zasoby\biuro.ico"; $s.Save()
```

Zanim puścisz program na prawdziwą skrzynkę, zrób przebieg próbny. Nic nie
zapisuje i nie tworzy odpowiedzi, tylko pokazuje, jak rozpoznał wiadomości:

```bash
python skrypty/sprawdz_maile.py --na-sucho --dni 14
```

## Polecenia pomocnicze

| Polecenie | Do czego |
|---|---|
| `python skrypty/sprawdz_gotowosc.py` | czego brakuje w konfiguracji |
| `python skrypty/sprawdz_modele.py` | jakie modele masz w Ollamie |
| `python skrypty/kopia_zapasowa.py` | kopia bazy i dokumentów |
| `python skrypty/retencja.py` | usuwanie danych wrażliwych po wyjeździe |
| `python skrypty/wyczysc_umowy.py` | usunięcie umów próbnych z rejestru |
| `python skrypty/wyczysc_zgloszenia.py` | usunięcie zgłoszeń próbnych |
| `python skrypty/zadania_harmonogramu.py` | automatyczne sprawdzanie poczty co kilka godzin (Windows) |
| `python skrypty/sprawdz_wersje.py` | czy pliki kodu zgadzają się ze spisem `WERSJE.txt` |

Skrypty czyszczące bez przełącznika `--zrob` tylko pokazują, co by usunęły,
a przed usunięciem robią kopię bazy.

## Co jest w repozytorium, a czego nie ma

```
biuro/          kod: poczta, ekstrakcja, umowy, listy, wykaz, baza
skrypty/        polecenia i panel okienkowy
prompty/        instrukcje dla modelu, do czytania i poprawiania
testy/          testy bez modelu i bez sieci
korpus/         syntetyczne wiadomości z odpowiedziami wzorcowymi i narzędzie pomiarowe
wiedza/         opis formatu bazy wiedzy i jeden przykład
*.example.*     wzory plików konfiguracyjnych
```

Nie ma i nie powinno być: `.env`, `config.yaml`, `wyjazdy.yaml`, katalogu
`dane/` (baza, umowy, listy), własnych plików w `wiedza/`, wzorca umowy
w `szablony/` i `wsad/`. Pilnuje tego `.gitignore`. Przed każdą publikacją
własnej kopii uruchom `python skrypty/sprawdz_do_publikacji.py`, który szuka
numerów PESEL, NIP, rachunków i adresów w plikach przeznaczonych do wysłania.

## Na ile można temu ufać

Program był mierzony na korpusie syntetycznym i na prawdziwej skrzynce
pierwszego wdrożenia. Wyniki, metoda i ograniczenia są w
[TECHNICZNIE.md](TECHNICZNIE.md). Te liczby dotyczą jednej firmy i jednego
rodzaju poczty, więc zmierz program na swojej: narzędzie jest w `korpus/`.

Numery PESEL, telefony, adresy e-mail i kody pocztowe wyciąga i sprawdza
zwykły kod z walidacją, a nie model. Model klasyfikuje wiadomości, czyta to,
czego nie da się opisać regułą, i pisze projekty odpowiedzi.

## Dokumenty

- [DLA-TWOJEJ-FIRMY.md](DLA-TWOJEJ-FIRMY.md): pełna instrukcja dopasowania do własnej firmy
- [WDROZENIE.md](WDROZENIE.md): wdrażanie etapami, kopie zapasowe, retencja danych
- [TECHNICZNIE.md](TECHNICZNIE.md): budowa, pomiary, decyzje projektowe
- [ZASTRZEZENIA.md](ZASTRZEZENIA.md): odpowiedzialność za dokumenty i dane osobowe

## Licencja

Kod: MIT, patrz [LICENSE](LICENSE). Modele Bielik rozwija Fundacja SpeakLeash
we współpracy z ACK Cyfronet AGH i publikuje na licencji Apache 2.0.
