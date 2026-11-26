"""Spain's tile improvements: motorways, main roads and railroads on hex links (the US rule in infrastructure.py).

Roads: class 0 = every motorway (Natural Earth "Major Highway" marked as an expressway: autovías and autopistas), class 1
= other roads at scale rank <= MAIN_MAX_SCALERANK. Rail: the US tiers. Lines over Portugal, France, Andorra or Morocco are
dropped.

Airports: the AENA network, each in the FAA hub class its share of Spain's passengers would give it (large ≥ 1%, medium
≥ 0.25%, small ≥ 0.05%, the rest nonhub), so the map draws them on the US scale. Passengers count arrivals plus
departures (the US file counts boardings). Ports: the 28 Port Authorities, at their largest port's service area. Cargo
and tonnage are converted to the contract's units (pounds, short tons).
"""

from __future__ import annotations

from ..core.geo import Shape, ShapeIndex
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, load_interim_payload, write_web
from ..countries import active
from .infrastructure import HUBS, RAIL_MAIN_SCALERANK, RAIL_MAX_SCALERANK, RAIL_TIERS, SAMPLE_KM, build_rail, build_roads
from .spain_wonders import Placer

REQUIRES = ["_world", "natural_earth_roads_es", "natural_earth_es", "aena_airports", "puertos_estado", "cities.json",
            "world.json"]
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
    "ports": "The 28 Port Authorities of Puertos del Estado by total freight traffic, each at the land service area of "
             "its largest port.",
    "airports": "Every airport and heliport of the AENA network, classed like the FAA hubs by its share of Spain's "
                "passengers (large 1% or more, medium 0.25%, small 0.05%, the rest nonhub).",
}


def es_road_class(f: dict) -> tuple[int, str | None] | None:
    sr = f["scalerank"] if f["scalerank"] is not None else 99
    if f["type"] == "Major Highway" and f["expressway"]:
        return 0, f["name"]
    if sr <= MAIN_MAX_SCALERANK and f["type"] in ("Major Highway", "Secondary Highway", "Road"):
        return 1, f["name"]
    return None


KG_TO_LB = 2.20462262
TONNE_TO_SHORT_TON = 1.10231131
HUB_SHARES = [("L", 0.01), ("M", 0.0025), ("S", 0.0005)]


def hub_class(passengers: int, total: int) -> str:
    share = passengers / total if total else 0
    return next((h for h, floor in HUB_SHARES if share >= floor), "N")


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
    placer = Placer(world)
    aena_p, ports_p = load_interim_payload("aena_airports"), load_interim_payload("puertos_estado")
    total = sum(a.get("passengers") or 0 for a in aena_p["data"]["airports"])
    airports = [{
        "id": a["id"], "name": a["name"], "city": None, "hub": hub_class(a.get("passengers") or 0, total),
        "enplanements": a.get("passengers"), "enplanements_prev": None,
        "cargo_lbs": round(a["cargo_kg"] * KG_TO_LB) if a.get("cargo_kg") else None, "year": aena_p["data"]["year"],
        **placer.place(a["lon"], a["lat"], unique=False),
    } for a in aena_p["data"]["airports"]]
    ports = [{
        "id": p["id"], "name": p["name"], "type": "coastal", "rank": k + 1,
        "tons": round(p["tonnes"] * TONNE_TO_SHORT_TON), "domestic": None, "foreign": None, "imports": None,
        "exports": None, "year": ports_p["data"]["year"], **placer.place(p["lon"], p["lat"], unique=False),
    } for k, p in enumerate(ports_p["data"]["ports"])]
    write_web("infrastructure.json", {
        "version": 1,
        "vintage": {"roads": vintage, "rail": vintage, "ports": ports_p["vintage"], "airports": aena_p["vintage"]},
        "sources": ["natural_earth_roads_es", "aena_airports", "puertos_estado"],
        "rules": RULES,
        "road_classes": ROAD_CLASSES,
        "rail_tiers": RAIL_TIERS,
        "hubs": HUBS,
        "roads": roads,
        "rail": rail,
        "ports": ports,
        "airports": airports,
    })
    n0 = sum(1 for r in roads if r[2] == 0)
    print(f"    roads: {n0} motorway + {len(roads) - n0} main-road links; rail: {len(rail)} links; {len(airports)} airports, "
          f"{len(ports)} ports")
