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
from .texts_es import RAIL_TIERS as RAIL_TIER_NAMES, num

REQUIRES = ["_world", "natural_earth_roads_es", "natural_earth_es"]
PRODUCES = ["infrastructure.json"]
COUNTRIES = ("es",)

MAIN_MAX_SCALERANK = 7
ROAD_CLASSES = [{"id": "interstate", "name": "Autovía o autopista"}, {"id": "major", "name": "Carretera principal"}]
RULES = {
    "roads": f"Carreteras de Natural Earth 1:10m en España, muestreadas cada {num(SAMPLE_KM)} km y ajustadas a enlaces entre "
             "centros de hexágono. Clase 0: todas las autovías y autopistas (las carreteras principales de Natural Earth "
             f"marcadas como vías rápidas). Clase 1: las demás carreteras de rango de escala {MAIN_MAX_SCALERANK} o menos de "
             "Natural Earth, donde ninguna autovía une ya los mismos dos hexágonos. Los tramos sobre países vecinos se "
             "descartan.",
    "rail": f"Ferrocarriles de Natural Earth 1:10m de rango de escala {RAIL_MAX_SCALERANK} o menos, muestreados cada "
            f"{num(SAMPLE_KM)} km y ajustados a enlaces entre centros de hexágono; el nivel 0 (línea principal) es el rango "
            f"de escala {RAIL_MAIN_SCALERANK} o menos. Natural Earth solo recoge las líneas principales y no trae datos de "
            "tráfico.",
    "ports": "Aún sin cartografiar en España.",
    "airports": "Aún sin cartografiar en España.",
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
        "rail_tiers": [{**t, "name": RAIL_TIER_NAMES[t["id"]]} for t in RAIL_TIERS],
        "hubs": {},
        "roads": roads,
        "rail": rail,
        "ports": [],
        "airports": [],
    })
    n0 = sum(1 for r in roads if r[2] == 0)
    print(f"    roads: {n0} motorway + {len(roads) - n0} main-road links; rail: {len(rail)} links")
