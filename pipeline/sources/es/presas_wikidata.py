"""Reservoirs and dams of Spain in Wikidata (CC0), one cached query: the position of the reservoirs the Boletín
Hidrológico no longer reports, which its map layer has no point for (pipeline/build/spain_embalses.py, E91)."""

from __future__ import annotations

import json
import urllib.parse

from ...core.source import Source, SourceInfo
from .playas import provenance
from .wikidata import ENDPOINT, HEADERS, point, qid

NAME_LANGS = ("es", "ca", "gl", "eu")
RESERVOIR, DAM = "Q131681", "Q12323"
# Reservoirs (Q131681) and dams (Q12323), with their subclasses, in Spain with coordinates, and every label and
# alias in the languages of Spain; ?class says which of the two trees the item's type is in. The query runs in the
# order written (optimizer "None"): from the classes to their instances, then Spain. Left to the optimizer it starts
# elsewhere and times out.
QUERY = """
SELECT ?s ?class ?coord ?name WHERE {
  hint:Query hint:optimizer "None".
  VALUES ?class { wd:%s wd:%s }
  ?type wdt:P279* ?class.
  ?s wdt:P31 ?type.
  ?s wdt:P17 wd:Q29.
  ?s wdt:P625 ?coord.
  { ?s rdfs:label ?name } UNION { ?s skos:altLabel ?name }
  FILTER(LANG(?name) IN (%s))
}""" % (RESERVOIR, DAM, ", ".join(f'"{lang}"' for lang in NAME_LANGS))
FILE = "presas.json"


class WikidataPresas(Source):
    info = SourceInfo(
        id="wikidata_presas",
        title="Wikidata: reservoirs and dams in Spain with coordinates and names",
        publisher="Wikidata (Wikimedia Foundation and volunteer editors)",
        homepage="https://www.wikidata.org/",
        license="CC0 1.0 (public domain dedication)",
        description="Every Wikidata item in Spain that is a reservoir (Q131681) or a dam (Q12323), or of a subclass, "
        "with coordinates, with its labels and aliases in Spanish, Catalan, Galician and Basque. Used only for the "
        "reservoirs the Boletín Hidrológico stopped reporting, which its map has no point for; volunteer-edited.",
        used_for=["Reservoirs lens: the position of reservoirs no longer in the Boletín"],
    )

    def fetch(self, force=False):
        self.download(ENDPOINT + urllib.parse.quote(" ".join(QUERY.split())), FILE, force=force, headers=HEADERS)

    def process(self):
        """One item per QID: its names (labels and aliases, in query order), its points and `dam` (true when one of
        its types is in the dam tree, Q12323)."""
        items: dict[str, dict] = {}
        for b in json.loads((self.raw_dir / FILE).read_text())["results"]["bindings"]:
            lonlat = point(b["coord"]["value"])
            if not lonlat:
                continue
            item = items.setdefault(qid(b["s"]["value"]), {"names": [], "points": [], "dam": False})
            item["dam"] |= qid(b["class"]["value"]) == DAM
            name = b["name"]["value"].strip()
            if name and name not in item["names"]:
                item["names"].append(name)
            if list(lonlat) not in item["points"]:
                item["points"].append(list(lonlat))
        out = [{"id": k, **v} for k, v in sorted(items.items(), key=lambda kv: int(kv[0][1:]))]
        return {**provenance(self.id, "Wikidata", FILE), "items": out}
