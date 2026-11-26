"""Fiestas de Interés Turístico Internacional and Nacional, from the two lists of the Secretaría de Estado de Turismo
(turismo.gob.es), each placed in its municipalities by the table in data/fiestas_interes_turistico.csv.

The pages list each fiesta under its autonomous community as "Name (year of the declaration)". A fiesta promoted to
Internacional often stays on the Nacional page too, and one entry is split across two items; the table's `same_as`
joins those to the entry they belong to, so every fiesta counts once, at its highest category. The table must cover
the pages exactly: a new declaration, or a renamed one, fails the build until it is placed.
"""

from __future__ import annotations

import csv
import html
import re
from pathlib import Path

from ...core.fetch import read_manifest
from ...core.source import Source, SourceInfo

PAGES = {
    "internacional": "https://turismo.gob.es/desarrollo-sostenibilidad/fiestas/Paginas/"
    "Fiestas-de-Inter%c3%a9s-Tur%c3%adstico-Internacional.aspx",
    "nacional": "https://turismo.gob.es/desarrollo-sostenibilidad/fiestas/Paginas/"
    "Fiestas-de-Inter%c3%a9s-Tur%c3%adstico-Nacional.aspx",
}
TABLE = Path(__file__).parent / "data" / "fiestas_interes_turistico.csv"
ENTRY = re.compile(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", re.S)
YEAR = re.compile(r"\s*\((\d{4})\b.*\)\s*$")


def clean(text: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", text)).split())


def entries(page: str) -> list[tuple[str, str]]:
    """(community, item text) of every fiesta on one of the lists, in page order."""
    return [(clean(dt), clean(li)) for dt, dd in ENTRY.findall(page) for li in re.findall(r"<li>(.*?)</li>", dd, re.S)]


def split_year(text: str) -> tuple[str, int | None]:
    """'Semana Santa de Zamora (1982)' → ('Semana Santa de Zamora', 1982); a fragment without a year → (text, None)."""
    m = YEAR.search(text)
    return (text[:m.start()].strip(), int(m.group(1))) if m else (text, None)


def fiestas(listed: dict[str, list[tuple[str, str]]], table: list[dict]) -> list[dict]:
    """The listed fiestas, each once at its highest category, with the municipalities the table gives it."""
    rows = {(r["category"], r["name"]): r for r in table}
    keys = [(cat, text) for cat, items in listed.items() for _, text in items]
    missing, stale = sorted(set(keys) - set(rows)), sorted(set(rows) - set(keys))
    if missing or stale:
        raise RuntimeError(f"fiestas table out of date: not placed {missing}, no longer listed {stale}")
    community = {(cat, text): comm for cat, items in listed.items() for comm, text in items}
    out: dict[str, dict] = {}
    for cat, text in keys:
        r = rows[(cat, text)]
        if r["same_as"]:
            continue
        name, year = split_year(text)
        municipalities = r["municipalities"].split()
        if not municipalities:
            raise RuntimeError(f"fiesta {text!r}: no municipalities")
        out[text] = {"name": name, "category": cat, "year": year, "community": community[(cat, text)],
                     "municipalities": municipalities}
    for cat, text in keys:
        target = rows[(cat, text)]["same_as"]
        if not target:
            continue
        owner = out.get(target)
        if owner is None:
            raise RuntimeError(f"fiesta {text!r}: same_as {target!r} is not a placed entry")
        name, year = split_year(text)
        if year is None:  # a fragment the page split off: the start of the owner's name
            owner["name"] = f"{name} {owner['name']}"
    return list(out.values())


class FiestasInteresTuristico(Source):
    info = SourceInfo(
        id="fiestas_interes_turistico",
        title="Fiestas de Interés Turístico Internacional and Nacional (Secretaría de Estado de Turismo)",
        publisher="Ministerio de Industria y Turismo, Secretaría de Estado de Turismo",
        homepage="https://turismo.gob.es/desarrollo-sostenibilidad/fiestas/Paginas/fiestas-interes-turistico.aspx",
        license="Public-sector information, reuse citing the source (Ley 37/2007)",
        description="The two official lists of fiestas declared of International and National Tourist Interest (Orden "
        "ICT/851/2019), by autonomous community with the year of each declaration, placed in their municipalities by "
        "a table kept in this repository. A fiesta on both lists counts once, as Internacional.",
        used_for=["Fiestas lens", "Party index lens"],
    )

    def fetch(self, force=False):
        for cat, url in PAGES.items():
            self.download(url, f"{cat}.html", force=force)

    def process(self):
        listed = {cat: entries((self.raw_dir / f"{cat}.html").read_text(encoding="utf-8")) for cat in PAGES}
        with open(TABLE, encoding="utf-8") as f:
            table = list(csv.DictReader(line for line in f if not line.startswith("#")))
        found = fiestas(listed, table)
        retrieved = read_manifest(self.id)["internacional.html"]["retrieved"][:10]
        return {"vintage": f"turismo.gob.es, {retrieved}", "_files": [f"{cat}.html" for cat in PAGES], "fiestas": found}
