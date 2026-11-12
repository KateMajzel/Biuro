#!/usr/bin/env python3
"""Zrzuca treść strony firmowej do folderu wiedza/ jako pliki markdown.

To najszybszy sposób na zbudowanie bazy wiedzy w piętnaście minut.
Potem przejrzyj pliki i usuń śmieci (menu, stopki, cookies) - jakość
bazy wiedzy decyduje o jakości draftów bardziej niż model.

    python skrypty/zrzut_strony.py
    python skrypty/zrzut_strony.py --max-stron 40
"""

import argparse
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402
from markdownify import markdownify  # noqa: E402

from biuro.config import cfg  # noqa: E402

POMIJAJ = re.compile(
    r"(wp-admin|wp-login|/feed|\?p=|#|\.jpg|\.jpeg|\.png|\.pdf|\.zip|"
    r"polityka-cookies|koszyk|cart|checkout)",
    re.IGNORECASE,
)


def nazwa_pliku(url: str, numer: int) -> str:
    sciezka = urlparse(url).path.strip("/") or "strona-glowna"
    czysta = re.sub(r"[^a-z0-9]+", "-", sciezka.lower()).strip("-")[:60]
    return f"{numer:02d}-{czysta or 'strona'}.md"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=None, help="domyślnie firma.www z config.yaml")
    parser.add_argument("--max-stron", type=int, default=30)
    parser.add_argument("--przerwa", type=float, default=1.0, help="sekundy między żądaniami")
    args = parser.parse_args()

    start = args.url or cfg().get("firma.www")
    if not start:
        print("Podaj --url albo wypełnij firma.www w config.yaml")
        return 1

    katalog = cfg().sciezka("wiedza")
    domena = urlparse(start).netloc
    kolejka = [start]
    odwiedzone: set[str] = set()
    zapisane = 0

    sesja = requests.Session()
    sesja.headers["User-Agent"] = "biuro-bielik/0.1 (zrzut wlasnej strony do bazy wiedzy)"

    while kolejka and zapisane < args.max_stron:
        url = kolejka.pop(0)
        if url in odwiedzone or POMIJAJ.search(url):
            continue
        odwiedzone.add(url)

        try:
            odp = sesja.get(url, timeout=30)
            odp.raise_for_status()
        except requests.RequestException as e:
            print(f"  pomijam {url}: {e}")
            continue
        if "text/html" not in odp.headers.get("Content-Type", ""):
            continue

        zupa = BeautifulSoup(odp.text, "html.parser")
        for tag in zupa(["script", "style", "nav", "footer", "header", "form", "noscript"]):
            tag.decompose()

        tytul = (zupa.title.string if zupa.title else url).strip()
        glowna = zupa.find("main") or zupa.find("article") or zupa.body
        if glowna is None:
            continue

        markdown = markdownify(str(glowna), heading_style="ATX")
        markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()
        if len(markdown) < 200:
            continue

        zapisane += 1
        plik = katalog / nazwa_pliku(url, zapisane)
        plik.write_text(
            f"# {tytul}\n\nŹródło: {url}\n\n{markdown}\n", encoding="utf-8"
        )
        print(f"  [{zapisane}] {plik.name}  <- {url}")

        for link in glowna.find_all("a", href=True):
            pelny = urljoin(url, link["href"]).split("#")[0]
            if urlparse(pelny).netloc == domena and pelny not in odwiedzone:
                kolejka.append(pelny)

        time.sleep(args.przerwa)

    print(f"\nZapisano {zapisane} plików w {katalog}")
    print("Przejrzyj je, usuń śmieci, a potem: python skrypty/indeksuj.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
