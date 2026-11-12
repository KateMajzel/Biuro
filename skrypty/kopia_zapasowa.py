#!/usr/bin/env python3
"""Kopia zapasowa bazy i dokumentów.

    python skrypty/kopia_zapasowa.py
    python skrypty/kopia_zapasowa.py --katalog "D:\\kopie-biuro"
    python skrypty/kopia_zapasowa.py --ile-trzymac 30

Baza SQLite jest źródłem prawdy dla umów i rejestru UFG. Jej utrata to
nie niedogodność, to brak danych do obowiązku sprawozdawczego.

Kopia bazy robiona jest przez `VACUUM INTO`, czyli spójnie, nawet jeśli
w tym czasie ktoś pisze do bazy. Zwykłe skopiowanie pliku .sqlite podczas
zapisu daje kopię, która może się nie otworzyć.
"""

import argparse
import shutil
import sqlite3
import sys
import zipfile
from datetime import datetime
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KORZEN))

from biuro.config import cfg  # noqa: E402


def kopia_bazy(docelowy: Path) -> Path:
    zrodlo = cfg().sciezka("baza")
    plik = docelowy / "biuro.sqlite"
    # VACUUM INTO daje spójną kopię bez zatrzymywania pracy
    conn = sqlite3.connect(zrodlo)
    try:
        conn.execute("VACUUM INTO ?", (str(plik),))
    finally:
        conn.close()
    return plik


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--katalog", default=None,
                        help="gdzie zapisać kopię (domyślnie dane/kopie)")
    parser.add_argument("--ile-trzymac", type=int, default=14,
                        help="ile ostatnich kopii zostawić (domyślnie 14)")
    args = parser.parse_args()

    katalog = Path(args.katalog) if args.katalog else cfg().sciezka("baza").parent / "kopie"
    katalog.mkdir(parents=True, exist_ok=True)

    znacznik = datetime.now().strftime("%Y-%m-%d-%H%M")
    tymczasowy = katalog / f"tmp-{znacznik}"
    tymczasowy.mkdir(exist_ok=True)

    try:
        plik_bazy = kopia_bazy(tymczasowy)
        print(f"baza:       {plik_bazy.stat().st_size // 1024} KB")

        archiwum = katalog / f"kopia-{znacznik}.zip"
        with zipfile.ZipFile(archiwum, "w", zipfile.ZIP_DEFLATED) as zip_plik:
            zip_plik.write(plik_bazy, "biuro.sqlite")

            # konfiguracja: bez .env, bo to sekret, nie dane
            for nazwa in ("config.yaml", "wyjazdy.yaml"):
                if (KORZEN / nazwa).exists():
                    zip_plik.write(KORZEN / nazwa, nazwa)

            # dokumenty i baza wiedzy
            ile_plikow = 0
            for podkatalog in ("umowy", "listy", "ufg", "odprawy"):
                katalog_zrodlowy = cfg().sciezka("baza").parent / podkatalog
                if not katalog_zrodlowy.exists():
                    continue
                for plik in katalog_zrodlowy.rglob("*"):
                    if plik.is_file():
                        zip_plik.write(plik, f"{podkatalog}/{plik.name}")
                        ile_plikow += 1
            for plik in cfg().sciezka("wiedza").rglob("*"):
                if plik.is_file():
                    zip_plik.write(plik, f"wiedza/{plik.name}")
                    ile_plikow += 1
            for plik in cfg().sciezka("szablony").rglob("*.docx"):
                zip_plik.write(plik, f"szablony/{plik.name}")
                ile_plikow += 1
            print(f"dokumenty:  {ile_plikow} plików")
    finally:
        shutil.rmtree(tymczasowy, ignore_errors=True)

    rozmiar = archiwum.stat().st_size / 1_048_576
    print(f"\nkopia:      {archiwum}  ({rozmiar:.1f} MB)")
    print("UWAGA: archiwum zawiera dane osobowe uczestników, w tym PESEL-e.")
    print("       Trzymaj je tam, gdzie trzymasz umowy, nie w chmurze publicznej.")

    # rotacja
    kopie = sorted(katalog.glob("kopia-*.zip"))
    if len(kopie) > args.ile_trzymac:
        do_usuniecia = kopie[: len(kopie) - args.ile_trzymac]
        for plik in do_usuniecia:
            plik.unlink()
        print(f"\nusunięto {len(do_usuniecia)} najstarszych kopii "
              f"(trzymam {args.ile_trzymac})")

    print(f"kopii razem: {len(list(katalog.glob('kopia-*.zip')))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
