"""Military installations of Spain: their boundaries from OpenStreetMap (ODbL) and, as a cross-check, the bases,
barracks and academies Wikidata records (CC0). Each is one cached query.

The Ministry of Defence publishes no open list or map of its installations, so the boundaries are the volunteers' (OSM
landuse=military and military=*). OSM also tags as military=training_area some airsoft fields and as military=range some
shooting clubs; the builder keeps a training or danger area only inside military land (landuse=military). Wikidata
names fewer sites and many old barracks that are museums today; the builder uses it only to link the sites OSM has.
"""

from __future__ import annotations

import json
import re
import urllib.parse

from ...core.fetch import read_manifest
from ...core.source import Source, SourceInfo
from ..mirta import simplify_rings
from .osm_bares import OVERPASS
from .wikidata import ENDPOINT, HEADERS, label, point, qid, value

# Military land and the military=* features that are places (bunkers, trenches, checkpoints and gun mounts are not).
FEATURES = ("base", "barracks", "airfield", "naval_base", "training_area", "range", "danger_area", "office")
NAMED_NODES = ("base", "barracks", "airfield", "naval_base", "office")
_ALT = "|".join(FEATURES)
QUERY = ('[out:json][timeout:600];area["ISO3166-1"="ES"][admin_level=2]->.es;('
         'way["landuse"="military"](area.es);relation["landuse"="military"](area.es);'
         f'way["military"~"^({_ALT})$"](area.es);relation["military"~"^({_ALT})$"](area.es);'
         f'node["military"~"^({"|".join(NAMED_NODES)})$"]["name"](area.es);node["landuse"="military"]["name"](area.es););'
         'out geom;')
OSM_FILE = "military.json"
TAGS = ("name", "official_name", "landuse", "military", "operator", "military_service", "wikidata")
SIMPLIFY_DEG = 0.0005  # ~50 m: far finer than a 10 km hex, enough for an area to 1 %

# Wikidata classes of current military sites (the items of a subclass are listed by their own class): barracks,
# military academy and school, air base, military base, training centre and camp, military installation, naval base and
# station, naval air station, arsenal, air depot (maestranza), military hospital, ammunition depot, training ground.
WIKIDATA_CLASSES = ("Q131263 Q917182 Q695850 Q245016 Q29918961 Q18691599 Q1198413 Q1935049 Q1745026 Q12622609 Q15966126 "
                    "Q113481415 Q113481408 Q1324633 Q2153495 Q4698330 Q1522839 Q81669 Q7432476 Q1898357 Q1778846 Q55624858 "
                    "Q6981985 Q42908058 Q2387974").split()
WIKIDATA_QUERY = """
SELECT ?s ?sLabel ?coord ?opLabel ?branchLabel WHERE {
  VALUES ?class { %s }
  ?s wdt:P31 ?class; wdt:P17 wd:Q29; wdt:P625 ?coord.
  FILTER NOT EXISTS { ?s wdt:P576 ?end. }
  FILTER NOT EXISTS { ?s wdt:P31 wd:Q30559999. }
  OPTIONAL { ?s wdt:P137 ?op. }
  OPTIONAL { ?s wdt:P241 ?branch. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "es,mul,en". }
}""" % " ".join(f"wd:{q}" for q in WIKIDATA_CLASSES)
WIKIDATA_FILE = "wikidata_military.json"


def _key(p: dict) -> tuple[float, float]:
    return round(p["lon"], 7), round(p["lat"], 7)


def assemble(ways: list[list[dict]]) -> list[list[dict]]:
    """Closed rings from the way geometries of a multipolygon role, joining ways that share an end node (OSM splits
    long boundaries into several ways). A chain that never closes is dropped."""
    open_, rings = [list(w) for w in ways if len(w) >= 2], []
    while open_:
        ring = open_.pop()
        while _key(ring[0]) != _key(ring[-1]):
            end = _key(ring[-1])
            for i, w in enumerate(open_):
                if _key(w[0]) == end:
                    ring += w[1:]
                elif _key(w[-1]) == end:
                    ring += w[-2::-1]
                else:
                    continue
                open_.pop(i)
                break
            else:
                ring = None
                break
        if ring and len(ring) >= 4:
            rings.append(ring)
    return rings


def _rings(rings: list[list[dict]]) -> list[list[list[float]]]:
    """Overpass node lists → simplified [lon, lat] rings; a ring smaller than the tolerance (a single building) keeps
    its own points."""
    out = []
    for r in rings:
        pts = [[p["lon"], p["lat"]] for p in r]
        out += simplify_rings({"type": "Polygon", "coordinates": [pts]}, SIMPLIFY_DEG) or \
            [[[round(x, 5), round(y, 5)] for x, y in pts]]
    return out


def element(e: dict) -> dict | None:
    """One Overpass element → {osm, tags, outer, inner (rings of [lon, lat]), point}; None without a usable shape."""
    tags = {k: e["tags"][k] for k in TAGS if k in e.get("tags", {})}
    out = {"osm": f"{e['type'][0]}{e['id']}", "tags": tags, "outer": [], "inner": [], "point": None}
    if e["type"] == "node":
        out["point"] = [round(e["lon"], 5), round(e["lat"], 5)]
    elif e["type"] == "way":
        geom = e.get("geometry") or []
        if len(geom) < 4 or _key(geom[0]) != _key(geom[-1]):
            return None  # an open way (a fence line) is not an area
        out["outer"] = _rings([geom])
    else:
        for role in ("outer", "inner"):
            ways = [m["geometry"] for m in e.get("members", []) if m["type"] == "way" and m.get("geometry")
                    and (m.get("role") or "outer") == role]
            out[role] = _rings(assemble(ways)) if ways else []
    return out if out["outer"] or out["point"] else None


class OsmMilitar(Source):
    info = SourceInfo(
        id="osm_militar",
        title="Military land and installations in Spain (OpenStreetMap, landuse=military and military=*)",
        publisher="OpenStreetMap contributors, via the Overpass API",
        homepage="https://wiki.openstreetmap.org/wiki/Key:military",
        license="ODbL 1.0 (© OpenStreetMap contributors)",
        description="Every OpenStreetMap area in Spain tagged landuse=military or military=base, barracks, airfield, "
        "naval_base, training_area, range, danger_area or office, with its boundary, name and operator, plus the named "
        "points with those tags. Volunteer-mapped: names and operators are the mappers', and some boundaries cover only "
        "part of a site.",
        used_for=["Military advisor: installations, ranges and garrisons", "Military map layer (forts and restricted ground)"],
    )

    def fetch(self, force=False):
        self.download(OVERPASS + urllib.parse.quote(QUERY), OSM_FILE, force=force)

    def process(self):
        raw = json.loads((self.raw_dir / OSM_FILE).read_text(encoding="utf-8"))
        items = [x for x in (element(e) for e in raw["elements"]) if x]
        items.sort(key=lambda x: x["osm"])
        return {"vintage": f"OpenStreetMap, {read_manifest(self.id)[OSM_FILE]['retrieved'][:10]}", "_files": [OSM_FILE],
                "features": list(FEATURES), "items": items}


class WikidataMilitar(Source):
    info = SourceInfo(
        id="wikidata_militar",
        title="Wikidata: military bases, barracks, academies and arsenals in Spain",
        publisher="Wikidata (Wikimedia Foundation and volunteer editors)",
        homepage="https://www.wikidata.org/",
        license="CC0 1.0 (public domain dedication)",
        description="Items in Spain whose class is a barracks, military academy or school, air, naval or military base, "
        "naval station, arsenal, air depot, military hospital, training centre or ground, with coordinates, operator "
        "(P137) and military branch (P241), leaving out those Wikidata records as dissolved or as historic military "
        "sites. Used to link the OpenStreetMap installations to their Wikidata items and to fill in a branch OSM lacks.",
        used_for=["Military advisor: Wikidata links and branches of installations"],
    )

    def fetch(self, force=False):
        self.download(ENDPOINT + urllib.parse.quote(" ".join(WIKIDATA_QUERY.split())), WIKIDATA_FILE, force=force,
                      headers=HEADERS)

    def process(self):
        items: dict[str, dict] = {}
        for b in json.loads((self.raw_dir / WIKIDATA_FILE).read_text())["results"]["bindings"]:
            q, coord = qid(b["s"]["value"]), point(value(b, "coord"))
            if not coord or not label(b):
                continue
            it = items.setdefault(q, {"qid": q, "label": label(b), "coord": coord, "operators": []})
            for k in ("opLabel", "branchLabel"):
                v = value(b, k)
                if v and not re.fullmatch(r"Q\d+", v) and v not in it["operators"]:
                    it["operators"].append(v)
        return {"vintage": f"Wikidata, {read_manifest(self.id)[WIKIDATA_FILE]['retrieved'][:10]}", "_files": [WIKIDATA_FILE],
                "items": sorted(items.values(), key=lambda i: i["qid"])}
