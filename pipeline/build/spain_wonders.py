"""Spain's wonders: every World Heritage site, every National Park and every cathedral, each by a published rule.

* **World Heritage** (rule `world_heritage`): the 50 UNESCO sites with a Spanish component (Wikidata, grouped by UNESCO
  site number), in order of that number (roughly the order of inscription). A site sits on its main component (or the
  first one with coordinates); natural sites (only criteria vii–x) are natural wonders.
* **National Parks** (rule `national_park`): all 16 (OAPN boundaries), ranked by 2025 visitors; a park covers the hexes
  whose centre is inside it. A park that is also a World Heritage site stays a park and is not repeated.
* **Cathedrals** (rule `cathedral`): every cathedral and co-cathedral Wikidata records in Spain, alphabetically, except
  those already inside a World Heritage site (Burgos, Sevilla, Santiago…).

Two wonders never share a hex: a later one moves to the nearest free land hex. Each wonder carries a `motif` (the sprite
drawn on its plinth) chosen from what it is.
"""

from __future__ import annotations

import math
import re
import unicodedata

from ..core.geo import Shape, ShapeIndex, ring_area, ring_centroid
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, load_interim_payload, load_web, write_web
from ..countries import active
from ..sources.es.oapn import short_name
from .cities import nearest_land

REQUIRES = ["_world", "oapn_parques", "wikidata_es", "cities.json", "world.json"]
PRODUCES = ["wonders.json"]
COUNTRIES = ("es",)

RULES = [
    {"id": "world_heritage", "kind": "landmark", "kinds": ["landmark", "natural"], "year": None,
     "text": "Every UNESCO World Heritage site with a component in Spain (50, as Wikidata records them), in order of their "
             "UNESCO number, roughly the order of inscription. Natural sites are natural wonders."},
    {"id": "national_park", "kind": "natural", "kinds": ["natural", "coastal"], "year": None,
     "text": "Every one of Spain's 16 National Parks (Red de Parques Nacionales, OAPN), ranked by their 2025 visitors "
             "(OAPN's yearly report): the Teide first, with over 5 million."},
    {"id": "cathedral", "kind": "landmark", "kinds": ["landmark"], "year": None,
     "text": "Every cathedral and co-cathedral in Spain that Wikidata records, alphabetically, except those that are part "
             "of a World Heritage site (already a wonder)."},
]
# What stands on the plinth (web/js/render/art/sites.js WONDER_MOTIFS), by words in the wonder's name.
MOTIFS = [
    (r"catedral|seo|basílica", "spire"), (r"monasterio|abad|cartuja|colegiata", "mission"),
    (r"cueva|rupestre|dolm|talay|megal|atapuerca|siega verde|côa", "mound"), (r"acueducto|puente|torre de hércules", "bridge"),
    (r"ciudad|casco|centro histórico|conjunto|villa|barrio", "quarter"), (r"palau|palacio|alhambra|alcázar|mezquita", "rotunda"),
    (r"teide|pirineo|monte|sierra|caldera|picos", "peak"), (r"bosque|hayas|garajonay", "forest"),
    (r"doñana|ibiza|cabrera|islas|marítim", "coast"), (r"camino|ruta|paisaje", "memorial"),
]


def slug(name: str) -> str:
    t = unicodedata.normalize("NFD", short_name(name).lower())
    return re.sub(r"[^a-z0-9]+", "-", "".join(ch for ch in t if unicodedata.category(ch) != "Mn")).strip("-")


def motif(name: str, natural: bool) -> str:
    n = name.lower()
    for pattern, m in MOTIFS:
        if re.search(pattern, n):
            return m
    return "forest" if natural else "obelisk"


class Placer:
    """Puts wonders on land hexes, one per hex, and fills in the hex's municipality, city and province."""

    def __init__(self, world: dict):
        self.world, self.grid, self.owner = world, HexGrid(**world["grid"]), world["owner"]
        self.proj = active().world_projection(world)
        self.abbrs = [s["abbr"] for s in load_web("world.json")["states"]]
        self.city_of = {g: c["id"] for c in load_web("cities.json") for g in c.get("counties") or []}
        self.taken: set[int] = set()

    def place(self, lon: float, lat: float, unique: bool = True) -> dict:
        """Where a site at lon/lat goes: the nearest land hex (one site per hex when `unique`)."""
        grid, owner = self.grid, self.owner
        x, y = self.proj(lon, lat)
        cell = nearest_land(grid, owner, max(grid.cell_at(x, y), 0), x, y, -1)
        if cell < 0 or (unique and cell in self.taken):
            cx, cy = (x, y)
            cell = min((c for c in range(grid.size) if owner[c] >= 0 and c not in self.taken),
                       key=lambda c: math.dist(grid.center(*grid.col_row(c)), (cx, cy)))
        self.taken.add(cell)
        ci = self.world["county"][cell]
        geoid = self.world["counties"][ci] if ci >= 0 else None
        return {"x": round(x, 1), "y": round(y, 1), "cell": cell, "county": geoid, "cbsa": self.city_of.get(geoid),
                "state": self.abbrs[owner[cell]]}

    def in_country(self, lon: float, lat: float) -> bool:
        """True when lon/lat falls on the mapped country's land, or on water next to it (a lighthouse, a harbour front),
        and not on a foreign component of a shared site."""
        c = self.grid.cell_at(*self.proj(lon, lat))
        return c >= 0 and (self.owner[c] >= 0 or (self.owner[c] == -1 and any(self.owner[n] >= 0 for n in self.grid.neighbours(c))))

    def covered(self, rings_lonlat: list) -> list[int] | None:
        shape = ShapeIndex([Shape([[self.proj(lon, lat) for lon, lat in r] for r in rings_lonlat if len(r) >= 3])], cell_km=50)
        cells = [i for i in range(self.grid.size)
                 if self.owner[i] >= 0 and shape.locate(*self.grid.center(*self.grid.col_row(i))) >= 0]
        return sorted(cells) or None


def build() -> None:
    world = load_interim("_world")
    parks_p = load_interim_payload("oapn_parques")
    wd_p = load_interim_payload("wikidata_es")
    wd = wd_p["data"]
    placer = Placer(world)
    wonders = []

    # National Parks first: they claim their hexes before the World Heritage sites that overlap them (Doñana, Teide…).
    park_names = set()
    parks = []
    year = parks_p["data"]["visitors_year"]
    for park in sorted(parks_p["data"]["parks"], key=lambda p: -p["visitors"]):
        name = park["name"]
        park_names.add(slug(name))
        main = max(park["rings"], key=lambda r: abs(ring_area(r)))
        parks.append({
            "id": f"pn-{slug(name)}", "name": name, "short": short_name(name),
            "kind": "coastal" if "Marítimo-Terrestre" in name else "natural", "rule": "national_park",
            "rank": len(parks) + 1,
            "metrics": {"visits": park["visitors"], "year": year, "area_km2": round(park["area_ha"] / 100, 1) if park["area_ha"] else None,
                        "unit_type": "Parque Nacional", "declared": park["declared"]},
            **placer.place(*ring_centroid(main)), "cells": placer.covered(park["rings"]), "curated": False,
            "motif": motif(name, True),
        })

    heritage = []
    for site in sorted(wd["world_heritage"], key=lambda s: int(s["unesco_id"])):
        here = [c for c in site["components"] if placer.in_country(*c["coord"])]  # shared sites: Spanish parts only
        if not here or slug(site["name"]) in park_names:
            continue
        main = next((c for c in here if c["qid"] == site["qid"]), here[0])
        heritage.append({
            "id": f"whs-{site['unesco_id']}", "name": site["name"][:1].upper() + site["name"][1:], "short": None,
            "kind": "natural" if site["natural"] else "landmark", "rule": "world_heritage", "rank": len(heritage) + 1,
            "metrics": {"unesco_id": int(site["unesco_id"]), "components": len(here),
                        "criteria": site["criteria"], "wikidata": site["qid"]},
            **placer.place(*main["coord"]), "cells": None, "curated": False,
            "motif": motif(site["name"], site["natural"]),
        })

    cathedrals = []
    for c in sorted(wd["cathedrals"], key=lambda c: (c["label"] or c["qid"]).lower()):
        if c["world_heritage"] or not c["coord"] or not c["label"]:
            continue
        cathedrals.append({
            "id": f"cat-{c['qid']}", "name": c["label"][:1].upper() + c["label"][1:], "short": None, "kind": "landmark",
            "rule": "cathedral", "rank": len(cathedrals) + 1, "metrics": {"wikidata": c["qid"]},
            **placer.place(*c["coord"]), "cells": None, "curated": False, "motif": "spire",
        })

    for w in heritage + parks + cathedrals:
        w["short"] = w["short"] or w["name"]
    wonders = heritage + parks + cathedrals  # rule order, as in RULES
    write_web("wonders.json", {
        "version": 1,
        "vintage": {"parks": parks_p["vintage"], "boundaries": parks_p["vintage"], "heritage": wd_p["vintage"]},
        "sources": ["wikidata_es", "oapn_parques"],
        "rules": RULES,
        "national": {"park_visits": sum(p["visitors"] for p in parks_p["data"]["parks"]), "park_visits_year": year,
                     "r1_universities": None,
                     "world_heritage_sites": len(heritage), "cathedrals": len(cathedrals)},
        "wonders": wonders,
    })
    print(f"    {len(heritage)} World Heritage sites, {len(parks)} National Parks, {len(cathedrals)} cathedrals")
