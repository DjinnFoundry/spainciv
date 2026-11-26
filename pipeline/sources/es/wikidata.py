"""Cultural heritage of Spain from Wikidata (CC0), via its keyless SPARQL endpoint.

Each query is cached as its JSON answer, like any other download, so a build is reproducible from the cache; a new
fetch with --force takes Wikidata as it is that day. Wikidata is edited by volunteers: counts can differ slightly from
the official registers (the World Heritage list has 50 Spanish sites; Wikidata records 49 with a Spanish component).
"""

from __future__ import annotations

import json
import re
import urllib.parse

from ...core.fetch import read_manifest
from ...core.source import Source, SourceInfo

ENDPOINT = "https://query.wikidata.org/sparql?format=json&query="
HEADERS = {"User-Agent": "spainciv/0.1 (https://github.com/DjinnFoundry/spainciv)", "Accept": "application/sparql-results+json"}

_QUERIES = {
    # Every item in Spain designated World Heritage, with its UNESCO site id (components share the site's number).
    "world_heritage": """
SELECT ?s ?id ?sLabel ?coord ?crit WHERE {
  ?s wdt:P1435 wd:Q9259; wdt:P17 wd:Q29; wdt:P757 ?id.
  OPTIONAL { ?s wdt:P625 ?coord. }
  OPTIONAL { ?s wdt:P2614 ?c. ?c rdfs:label ?crit. FILTER(LANG(?crit) = "en") }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "%s". }
}""",
    # Spanish parts of World Heritage sites whose own items sit abroad or lack a Spanish position (beech forests, Almadén).
    "world_heritage_parts": """
SELECT ?s ?sLabel ?id ?coord WHERE {
  ?site wdt:P1435 wd:Q9259; wdt:P757 ?id.
  ?s wdt:P361 ?site; wdt:P17 wd:Q29; wdt:P625 ?coord.
  SERVICE wikibase:label { bd:serviceParam wikibase:language "%s". }
}""",
    # Cathedrals and co-cathedrals in Spain with coordinates.
    "cathedrals": """
SELECT ?s ?sLabel ?coord ?whid WHERE {
  VALUES ?t { wd:Q2977 wd:Q56242215 wd:Q2306160 }
  ?s wdt:P31 ?t; wdt:P17 wd:Q29; wdt:P625 ?coord.
  OPTIONAL { ?s wdt:P757 ?whid. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "%s". }
}""",
    # Bienes de Interés Cultural (Spain's highest heritage protection) with coordinates.
    "bic": """
SELECT ?s ?coord WHERE { ?s wdt:P1435 wd:Q23712; wdt:P625 ?coord. }""",
}

LANGUAGES = "es,mul,en,gl,ca,eu"  # label fallback order (Wikidata now keeps many labels only in "mul")
QUERIES = {k: (v % LANGUAGES if "%s" in v else v) for k, v in _QUERIES.items()}
POINT = re.compile(r"Point\(([-\d.eE]+) ([-\d.eE]+)\)")


def point(wkt: str | None) -> tuple[float, float] | None:
    m = POINT.match(wkt or "")
    return (round(float(m.group(1)), 5), round(float(m.group(2)), 5)) if m else None


def qid(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def value(b: dict, key: str) -> str | None:
    return b[key]["value"] if key in b else None


def label(b: dict) -> str | None:
    """The label service's answer; it returns the bare QID when no language in LANGUAGES has a label."""
    v = value(b, "sLabel")
    return None if v is None or re.fullmatch(r"Q\d+", v) else v


class WikidataEs(Source):
    info = SourceInfo(
        id="wikidata_es",
        title="Wikidata: World Heritage sites, cathedrals and Bienes de Interés Cultural in Spain",
        publisher="Wikidata (Wikimedia Foundation and volunteer editors)",
        homepage="https://www.wikidata.org/",
        license="CC0 1.0 (public domain dedication)",
        description="Items in Spain designated World Heritage (grouped by their UNESCO site number), cathedrals and "
        "co-cathedrals, and Bienes de Interés Cultural, with their coordinates, from Wikidata's SPARQL service. "
        "Volunteer-edited: coverage is close to, but not exactly, the official registers.",
        used_for=["World Heritage and cathedral wonders", "Heritage lens (Bienes de Interés Cultural)"],
    )

    def fetch(self, force=False):
        for name, sparql in QUERIES.items():
            self.download(ENDPOINT + urllib.parse.quote(" ".join(sparql.split())), f"{name}.json", force=force,
                          headers=HEADERS)

    def _rows(self, name: str) -> list[dict]:
        return json.loads((self.raw_dir / f"{name}.json").read_text())["results"]["bindings"]

    def process(self):
        sites: dict[str, dict] = {}
        for b in self._rows("world_heritage"):
            raw_id = value(b, "id")
            site = re.match(r"\d+", raw_id).group(0)
            s = sites.setdefault(site, {"unesco_id": site, "items": {}, "criteria": set()})
            item = s["items"].setdefault(qid(b["s"]["value"]), {"label": label(b), "coord": None, "main": False})
            item["coord"] = item["coord"] or point(value(b, "coord"))
            item["main"] = item["main"] or raw_id == site
            if value(b, "crit"):
                s["criteria"].add(value(b, "crit"))
        for b in self._rows("world_heritage_parts"):
            site = re.match(r"\d+", value(b, "id")).group(0)
            if site in sites:
                sites[site]["items"].setdefault(qid(b["s"]["value"]), {"label": label(b), "coord": point(value(b, "coord")),
                                                                      "main": False})
        heritage = []
        for site, s in sorted(sites.items(), key=lambda kv: int(kv[0])):
            items = [{"qid": k, **v} for k, v in s["items"].items()]
            main = next((i for i in items if i["main"]), None) or items[0]
            crit = sorted(s["criteria"])
            natural = bool(crit) and all(c.strip("()").lower() in ("vii", "viii", "ix", "x") for c in crit)
            heritage.append({
                "unesco_id": site, "name": main["label"] or next((i["label"] for i in items if i["label"]), site),
                "qid": main["qid"], "natural": natural, "criteria": crit,
                "components": [{"qid": i["qid"], "label": i["label"], "coord": i["coord"]} for i in items if i["coord"]],
            })
        cathedrals = {}
        for b in self._rows("cathedrals"):
            q = qid(b["s"]["value"])
            c = cathedrals.setdefault(q, {"qid": q, "label": label(b), "coord": point(value(b, "coord")),
                                          "world_heritage": None})
            if value(b, "whid"):
                c["world_heritage"] = re.match(r"\d+", value(b, "whid")).group(0)
        bic = {qid(b["s"]["value"]): point(value(b, "coord")) for b in self._rows("bic")}
        return {
            "vintage": f"Wikidata, {read_manifest(self.id)['world_heritage.json']['retrieved'][:10]}",
            "_files": [f"{n}.json" for n in QUERIES],
            "world_heritage": heritage,
            "cathedrals": sorted(cathedrals.values(), key=lambda c: c["label"] or c["qid"]),
            "bic": [c for c in bic.values() if c],
        }
