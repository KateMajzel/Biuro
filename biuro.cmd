@echo off
rem ============================================================
rem  Biuro na Bieliku - uruchamianie bez wpisywania komend.
rem
rem  Skrot do tego pliku mozesz wrzucic na pulpit: prawy przycisk
rem  na biuro.cmd -> Pokaz wiecej opcji -> Utworz skrot, potem
rem  przenies skrot na pulpit. Nie przenos samego pliku.
rem
rem  Jesli dwuklik daje komunikat o niebezpiecznym pliku, to Mark of the
rem  Web - znacznik, ktory Windows dokleja do plikow pobranych z sieci.
rem  Zdejmij go w PowerShellu:  Get-ChildItem -Recurse -File | Unblock-File
rem
rem  Tekst w tym pliku jest bez polskich znakow celowo. Konsola
rem  Windows otwiera pliki .cmd w stronie kodowej systemu, nie
rem  w UTF-8, i polskie znaki zamienilyby sie w krzaki. Skrypty
rem  Pythona wywolywane nizej wypisuja juz normalna polszczyzne.
rem ============================================================

setlocal
cd /d "%~dp0"

set PY=.venv\Scripts\python.exe
if not exist "%PY%" (
    echo.
    echo Nie ma srodowiska .venv w tym katalogu.
    echo Uruchom najpierw instalacje z pliku DLA-TWOJEJ-FIRMY.md
    echo.
    pause
    exit /b 1
)

:menu
cls
echo ============================================================
echo    BIURO NA BIELIKU
echo ============================================================
echo.
echo   1.  Sprawdz poczte - PROBNIE (nic nie zapisze)
echo   2.  Sprawdz poczte - na serio (zapis + wersje robocze)
echo.
echo   3.  Lista zgloszen i wyjazdow
echo   4.  Wystaw umowe
echo   5.  Lista uczestnikow wyjazdu (arkusz)
echo   6.  Odprawa przedwyjazdowa
echo.
echo   7.  Wykaz umow dla UFG (CSV)
echo   8.  Ile dni do deklaracji TFG
echo.
echo   9.  Przebuduj baze wiedzy
echo  10.  Sprawdzenie gotowosci
echo  11.  Testy
echo.
echo   0.  Koniec
echo.
set /p wybor="Numer: "

if "%wybor%"=="1"  goto poczta_probnie
if "%wybor%"=="2"  goto poczta_serio
if "%wybor%"=="3"  goto lista
if "%wybor%"=="4"  goto umowa
if "%wybor%"=="5"  goto arkusz
if "%wybor%"=="6"  goto odprawa
if "%wybor%"=="7"  goto ufg
if "%wybor%"=="8"  goto tfg
if "%wybor%"=="9"  goto wiedza
if "%wybor%"=="10" goto gotowosc
if "%wybor%"=="11" goto testy
if "%wybor%"=="0"  exit /b 0
goto menu

:poczta_probnie
echo.
set /p dni="Ile dni wstecz [3]: "
if "%dni%"=="" set dni=3
"%PY%" skrypty\sprawdz_maile.py --na-sucho --dni %dni%
goto koniec_akcji

:poczta_serio
echo.
echo UWAGA: powstana wersje robocze w skrzynce. Nic nie zostanie wyslane.
set /p dni="Ile dni wstecz [3]: "
if "%dni%"=="" set dni=3
"%PY%" skrypty\sprawdz_maile.py --dni %dni%
goto koniec_akcji

:lista
echo.
"%PY%" skrypty\zrob_umowe.py --lista
goto koniec_akcji

:umowa
echo.
"%PY%" skrypty\zrob_umowe.py --lista
echo.
set /p zid="Numer zgloszenia: "
set /p wyj="Klucz wyjazdu (np. irlandia-2026): "
"%PY%" skrypty\zrob_umowe.py %zid% %wyj%
goto koniec_akcji

:arkusz
echo.
set /p wyj="Klucz wyjazdu: "
echo.
echo   p = pelny (z PESEL, kodami do skrytki)
echo   o = okrojony (dla przewoznika albo hotelu)
set /p war="Wariant [p]: "
if /i "%war%"=="o" (
    "%PY%" skrypty\zrob_liste.py %wyj% --okrojona
) else (
    "%PY%" skrypty\zrob_liste.py %wyj%
)
goto koniec_akcji

:odprawa
echo.
"%PY%" skrypty\zrob_umowe.py --lista
echo.
set /p zid="Numer zgloszenia: "
set /p wyj="Klucz wyjazdu: "
"%PY%" skrypty\zrob_odprawe.py %zid% %wyj%
goto koniec_akcji

:ufg
echo.
rem wmic zostalo usuniete z Windows 11 24H2, wiec date bierzemy z Pythona,
rem ktory i tak musi dzialac, zeby to menu mialo sens.
for /f "tokens=1,2" %%a in ('"%PY%" -c "from datetime import date; d=date.today(); print(d.year, d.month)"') do (
    set rok=%%a
    set mies=%%b
)
set /p r="Rok [%rok%]: "
if "%r%"=="" set r=%rok%
set /p m="Miesiac [%mies%]: "
if "%m%"=="" set m=%mies%
"%PY%" skrypty\zrob_csv_ufg.py %r% %m%
goto koniec_akcji

:tfg
echo.
"%PY%" skrypty\sprawdz_maile.py --na-sucho --dni 1
goto koniec_akcji

:wiedza
echo.
"%PY%" skrypty\indeksuj.py
goto koniec_akcji

:gotowosc
echo.
"%PY%" skrypty\sprawdz_gotowosc.py
goto koniec_akcji

:testy
echo.
"%PY%" testy\uruchom_wszystkie.py
goto koniec_akcji

:koniec_akcji
echo.
echo ------------------------------------------------------------
pause
goto menu
