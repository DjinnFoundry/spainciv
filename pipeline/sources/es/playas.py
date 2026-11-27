"""Where Spain's beaches are, by name: Wikidata beach items (CC0) and OpenStreetMap natural=beach with a name (ODbL),
one cached query each. They place the Blue Flag beaches, which ADEAC lists by municipality only, at the beach itself
(pipeline/build/spain_beaches.py).

The Ministry's beach guide (Guía de Playas, MITECO) would rank first, but it is not published any more: its
datos.gob.es entry answers 404, its WMS (wms.mapama.gob.es/sig/Costas/Playas) fails on every request, and the IDE
download page of MITECO has no beach layer (checked 2026-11-27).
"""

from __future__ import annotations

import csv
import io
import json
import urllib.parse

from ...core.fetch import read_manifest
from ...core.source import Source, SourceInfo
from .wikidata import ENDPOINT, HEADERS, point, qid

# Beaches (Q40080 and subclasses: river beaches, coves, nudist beaches…) in Spain with coordinates, their names in the
# languages of Spain (labels and aliases) and the INE code (P772) of every place they are in (P131, transitively).
NAME_LANGS = ("es", "gl", "ca", "eu", "ast", "an", "oc", "mul")
WIKIDATA_QUERY = """
SELECT ?s ?coord ?ine ?name WHERE {
  ?s wdt:P31/wdt:P279* wd:Q40080; wdt:P17 wd:Q29; wdt:P625 ?coord.
  OPTIONAL { ?s wdt:P131+ ?m. ?m wdt:P772 ?ine. }
  { ?s rdfs:label ?name } UNION { ?s skos:altLabel ?name }
  FILTER(LANG(?name) IN (%s))
}""" % ", ".join(f'"{lang}"' for lang in NAME_LANGS)
WIKIDATA_FILE = "beaches.json"

OVERPASS = "https://overpass-api.de/api/interpreter?data="
OSM_NAMES = ("name", "name:es", "name:ca", "name:gl", "name:eu", "name:ast", "alt_name", "official_name", "loc_name",
             "old_name")
OSM_COLUMNS = ",".join(f'"{k}"' for k in OSM_NAMES)
OSM_QUERY = (f'[out:csv(::type,::id,::lat,::lon,{OSM_COLUMNS};false;"\\t")]'
             '[timeout:300];area["ISO3166-1"="ES"][admin_level=2]->.es;nwr["natural"="beach"]["name"](area.es);'
             'out center;')
OSM_FILE = "beaches.tsv"


def names_of(*values: str | None) -> list[str]:
    """Distinct names, in order; OSM separates several in one tag with ';'."""
    out: list[str] = []
    for v in values:
        for n in (v or "").split(";"):
            if (n := n.strip()) and n not in out:
                out.append(n)
    return out


def provenance(source_id: str, publisher: str, file: str) -> dict:
    """The vintage (publisher and retrieval date) and raw file of a source's one cached download."""
    retrieved = read_manifest(source_id)[file]["retrieved"][:10]
    return {"vintage": f"{publisher}, {retrieved}", "_files": [file]}


class WikidataPlayas(Source):
    info = SourceInfo(
        id="wikidata_playas",
        title="Wikidata: beaches in Spain with coordinates, names and municipality",
        publisher="Wikidata (Wikimedia Foundation and volunteer editors)",
        homepage="https://www.wikidata.org/",
        license="CC0 1.0 (public domain dedication)",
        description="Every Wikidata item in Spain that is a beach (Q40080 or a subclass) with coordinates, with its "
        "labels and aliases in Spanish, Galician, Catalan, Basque, Asturian, Aragonese, Occitan and 'mul', and the INE "
        "code of the municipality it is in. Volunteer-edited: some coasts are far better covered than others.",
        used_for=["Blue Flag beaches lens: each beach's position"],
    )

    def fetch(self, force=False):
        self.download(ENDPOINT + urllib.parse.quote(" ".join(WIKIDATA_QUERY.split())), WIKIDATA_FILE, force=force,
                      headers=HEADERS)

    def process(self):
        rows = json.loads((self.raw_dir / WIKIDATA_FILE).read_text())["results"]["bindings"]
        items: dict[str, dict] = {}
        for b in rows:
            item = items.setdefault(qid(b["s"]["value"]), {"names": [], "ine": [], "lonlat": point(b["coord"]["value"])})
            name, ine = b["name"]["value"].strip(), b.get("ine", {}).get("value")
            if name and name not in item["names"]:
                item["names"].append(name)
            if ine and len(ine) == 5 and ine not in item["ine"]:
                item["ine"].append(ine)
        beaches = [{"id": k, **v} for k, v in sorted(items.items(), key=lambda kv: int(kv[0][1:])) if v["lonlat"]]
        return {**provenance(self.id, "Wikidata", WIKIDATA_FILE), "beaches": beaches}


class OsmPlayas(Source):
    info = SourceInfo(
        id="osm_playas",
        title="Named beaches in Spain (OpenStreetMap, natural=beach)",
        publisher="OpenStreetMap contributors, via the Overpass API",
        homepage="https://www.openstreetmap.org/",
        license="ODbL 1.0 (© OpenStreetMap contributors)",
        description="Every OpenStreetMap node, way or relation in Spain tagged natural=beach with a name, at its "
        "position (the centre of a way), with its names (name, name:es, name:ca, name:gl, name:eu, name:ast, alt_name, "
        "official_name, loc_name, old_name). Volunteer-mapped.",
        used_for=["Blue Flag beaches lens: each beach's position, where Wikidata has none"],
    )

    def fetch(self, force=False):
        self.download(OVERPASS + urllib.parse.quote(OSM_QUERY), OSM_FILE, force=force)

    def process(self):
        text = (self.raw_dir / OSM_FILE).read_text(encoding="utf-8")
        rows = csv.reader(io.StringIO(text), delimiter="\t", quoting=csv.QUOTE_NONE)
        beaches = [{"id": f"{kind}/{osm_id}", "names": names_of(*names), "lonlat": [round(float(lon), 5), round(float(lat), 5)]}
                   for kind, osm_id, lat, lon, *names in rows if lat]
        return {**provenance(self.id, "OpenStreetMap", OSM_FILE), "beaches": beaches}
