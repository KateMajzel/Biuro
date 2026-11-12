# Zastrzeżenia

Oprogramowanie udostępniane jest na licencji MIT, bez żadnej gwarancji
(patrz plik `LICENSE`). Poniższe punkty rozwijają to, co w praktyce znaczy
„bez gwarancji" przy obsłudze biura podróży.

## To nie jest porada prawna

Aplikacja nie zna przepisów. Odlicza dni do daty wpisanej w `config.yaml`
i podstawia dane w szablon, który dostarcza użytkownik. Dzień graniczny
deklaracji TFG, treść umowy, zakres obowiązku informacyjnego i wszystko inne,
co wynika z ustawy, sprawdza i ustala **użytkownik**, we własnym zakresie
i w aktualnym stanie prawnym.

## Odpowiedzialność za treść dokumentów

Model językowy nie uczestniczy w tworzeniu treści umowy. Dane są podstawiane
w szablon deterministycznie, a wygenerowany dokument jest **projektem** —
przed przekazaniem uczestnikowi wymaga sprawdzenia przez człowieka.

Generator wypisuje listę pól pustych albo nieuzupełnionych i mówi wprost, że
umowa nie jest gotowa do podpisu. Brak takiego komunikatu **nie jest**
potwierdzeniem, że dokument jest poprawny — znaczy tylko, że nie wykryto
pustych pól.

## Odpowiedzialność za odpowiedzi do klientów

Aplikacja nie wysyła poczty. Każda odpowiedź powstaje jako wersja robocza
w folderze skrzynki i czeka na decyzję człowieka. Projekt odpowiedzi może
zawierać błąd merytoryczny, zwłaszcza gdy baza wiedzy jest niekompletna —
dlatego ścieżka wysyłki automatycznej nie istnieje i nie jest planowana.

## Dane osobowe

Aplikacja przechowuje dane uczestników lokalnie, w pliku SQLite na komputerze
użytkownika. Model działa lokalnie, więc dane nie są wysyłane do żadnego
dostawcy zewnętrznego. **Nie zwalnia to użytkownika** z obowiązków
administratora danych: podstawy prawnej przetwarzania, obowiązku
informacyjnego, retencji, kopii zapasowych i zabezpieczenia samego komputera.

Dane wrażliwe (PESEL, numer dokumentu) trafiają do osobnej tabeli z kolumną
`usunac_po`, co ułatwia ich usunięcie po wyjeździe. Usunięcie w terminie
pozostaje decyzją i obowiązkiem użytkownika.

## Wyniki pomiarów

Liczby skuteczności podawane w dokumentacji pochodzą z zestawu **12 zgłoszeń
syntetycznych**, napisanych pod schemat pól. Przy tej liczebności przedział
ufności dla wyniku 100% sięga w dół do około 75%. Te liczby mówią, że pipeline
działa — nie jak zachowa się na cudzej, prawdziwej poczcie.

Dlatego razem z aplikacją dostarczany jest harness ewaluacyjny: każda firma
może zmierzyć skuteczność na własnych wiadomościach, zamiast ufać cudzym
liczbom.

## Model

Modele Bielik rozwijane są przez Fundację SpeakLeash we współpracy z ACK
Cyfronet AGH i udostępniane na licencji Apache 2.0. Ta aplikacja jedynie
z nich korzysta przez lokalny serwer Ollama; nie zawiera wag modelu ani ich
nie redystrybuuje.
