"""Spain's wonders: the 16 National Parks (OAPN), all of them, ranked by official area.

The US rule ranks parks by recreation visits; Spain's visitor counts are not in a downloadable table yet (ROADMAP.md),
so every National Park is a wonder, `visits` is null and the rank is by declared area. A park sits on the land hex
nearest the centroid of its largest outline, and covers (protected land) the hexes whose centre is inside it.
"""

from __future__ import annotations

import re

from ..core.geo import Shape, ShapeIndex, ring_area, ring_centroid
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, load_interim_payload, load_web, write_web
from ..countries import active
from .cities import nearest_land

REQUIRES = ["_world", "oapn_parques", "cities.json"]
PRODUCES = ["wonders.json"]
COUNTRIES = ("es",)

RULE = ("Every one of Spain's 16 National Parks (Red de Parques Nacionales, OAPN), ranked by the area their declaring law "
        "gives them. Spain publishes no downloadable table of park visitors yet, so they are not ranked by visits as on "
        "the US map. Maritime-terrestrial parks count their sea area too.")
PREFIX = re.compile(r"^Parque Nacional (Marítimo-Terrestre )?(de las |de los |de la |del |de )?", re.IGNORECASE)


def short_name(name: str) -> str:
    """'Parque Nacional de la Sierra de Guadarrama' → 'Sierra de Guadarrama'."""
    return PREFIX.sub("", name).strip() or name


def slug(name: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFD", short_name(name).lower())
    return re.sub(r"[^a-z0-9]+", "-", "".join(ch for ch in t if unicodedata.category(ch) != "Mn")).strip("-")


def build() -> None:
    world = load_interim("_world")
    grid, owner = HexGrid(**world["grid"]), world["owner"]
    proj = active().world_projection(world)
    payload = load_interim_payload("oapn_parques")
    abbrs = {i: s for i, s in enumerate(load_web("world.json")["states"])}
    city_of = {g: c["id"] for c in load_web("cities.json") for g in c.get("counties") or []}
    taken: set[int] = set()
    wonders = []
    for park in sorted(payload["data"]["parks"], key=lambda p: -(p["area_ha"] or 0)):
        rings = [[proj(lon, lat) for lon, lat in r] for r in park["rings"] if len(r) >= 3]
        main = max(park["rings"], key=lambda r: abs(ring_area(r)))
        x, y = proj(*ring_centroid(main))
        cell = nearest_land(grid, owner, max(grid.cell_at(x, y), 0), x, y, -1)
        if cell in taken:  # two parks never share a hex: take the nearest free land hex
            cell = min((c for c in range(grid.size) if owner[c] >= 0 and c not in taken),
                       key=lambda c: (grid.center(*grid.col_row(c))[0] - x) ** 2 + (grid.center(*grid.col_row(c))[1] - y) ** 2)
        taken.add(cell)
        shape = ShapeIndex([Shape(rings)], cell_km=50)
        cells = [i for i in range(grid.size) if owner[i] >= 0 and shape.locate(*grid.center(*grid.col_row(i))) >= 0]
        ci = world["county"][cell]
        geoid = world["counties"][ci] if ci >= 0 else None
        name = park["name"]
        wonders.append({
            "id": f"pn-{slug(name)}", "name": name, "short": short_name(name),
            "kind": "coastal" if "Marítimo-Terrestre" in name else "natural", "rule": "national_park",
            "rank": len(wonders) + 1,
            "metrics": {"visits": None, "year": None, "area_km2": round(park["area_ha"] / 100, 1) if park["area_ha"] else None,
                        "unit_type": "Parque Nacional", "declared": park["declared"]},
            "x": round(x, 1), "y": round(y, 1), "cell": cell, "cells": sorted(cells) or None,
            "county": geoid, "cbsa": city_of.get(geoid), "state": abbrs[owner[cell]]["abbr"], "curated": False,
        })
    write_web("wonders.json", {
        "version": 1,
        "vintage": {"parks": payload["vintage"], "boundaries": payload["vintage"]},
        "sources": ["oapn_parques"],
        "rules": [{"id": "national_park", "kind": "natural", "kinds": ["natural", "coastal"], "year": None, "text": RULE}],
        "national": {"park_visits": None, "park_visits_year": None, "r1_universities": None},
        "wonders": wonders,
    })
    print(f"    {len(wonders)} National Parks; {sum(len(w['cells'] or []) for w in wonders)} protected hexes")
