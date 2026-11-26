"""Spain's tile improvements: motorways, main roads and railroads on hex links (the US rule in infrastructure.py).

Roads: class 0 = every motorway (Natural Earth "Major Highway" marked as an expressway: autovías and autopistas), class 1
= other roads at scale rank <= MAIN_MAX_SCALERANK. Rail: the US tiers. Lines over Portugal, France, Andorra or Morocco are
dropped. Ports and airports are not mapped yet (ROADMAP.md): the lists are empty, not invented.
"""

from __future__ import annotations

from ..core.geo import Shape, ShapeIndex
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, load_interim_payload, write_web
from ..countries import active
from .infrastructure import RAIL_MAIN_SCALERANK, RAIL_MAX_SCALERANK, RAIL_TIERS, SAMPLE_KM, build_rail, build_roads

REQUIRES = ["_world", "natural_earth_roads_es", "natural_earth_es"]
PRODUCES = ["infrastructure.json"]
COUNTRIES = ("es",)

MAIN_MAX_SCALERANK = 7
ROAD_CLASSES = [{"id": "interstate", "name": "Motorway (autovía, autopista)"}, {"id": "major", "name": "Main road"}]
RULES = {
    "roads": f"Natural Earth 1:10m roads in Spain, sampled every {SAMPLE_KM:g} km and snapped to hex-centre links. Class 0: "
             "every motorway (Natural Earth major highways marked as expressways: autovías and autopistas). Class 1: "
             f"other roads at Natural Earth scale rank {MAIN_MAX_SCALERANK} or less, where no motorway already joins the "
             "same two hexes. Lines over neighbouring countries are dropped.",
    "rail": f"Natural Earth 1:10m railroads at scale rank {RAIL_MAX_SCALERANK} or less, sampled every {SAMPLE_KM:g} km and "
            f"snapped to hex-centre links; tier 0 (main line) is scale rank {RAIL_MAIN_SCALERANK} or less. Natural Earth "
            "holds only the main lines and no traffic data.",
    "ports": "Not mapped yet for Spain.",
    "airports": "Not mapped yet for Spain.",
}


def es_road_class(f: dict) -> tuple[int, str | None] | None:
    sr = f["scalerank"] if f["scalerank"] is not None else 99
    if f["type"] == "Major Highway" and f["expressway"]:
        return 0, f["name"]
    if sr <= MAIN_MAX_SCALERANK and f["type"] in ("Major Highway", "Secondary Highway", "Road"):
        return 1, f["name"]
    return None


def build() -> None:
    world = load_interim("_world")
    grid, proj, owner = HexGrid(**world["grid"]), active().world_projection(world), world["owner"]
    ne = load_interim("natural_earth_roads_es")
    foreign = load_interim("natural_earth_es")["countries"]
    foreign_idx = ShapeIndex([Shape([[proj(lon, lat) for lon, lat in r] for r in c["rings"]]) for c in foreign],
                             cell_km=100)
    roads = build_roads(grid, proj, owner, ne, es_road_class)
    rail = build_rail(grid, proj, owner, ne, foreign_idx)
    vintage = load_interim_payload("natural_earth_roads_es")["vintage"]
    write_web("infrastructure.json", {
        "version": 1,
        "vintage": {"roads": vintage, "rail": vintage, "ports": None, "airports": None},
        "sources": ["natural_earth_roads_es"],
        "rules": RULES,
        "road_classes": ROAD_CLASSES,
        "rail_tiers": RAIL_TIERS,
        "hubs": {},
        "roads": roads,
        "rail": rail,
        "ports": [],
        "airports": [],
    })
    n0 = sum(1 for r in roads if r[2] == 0)
    print(f"    roads: {n0} motorway + {len(roads) - n0} main-road links; rail: {len(rail)} links")
