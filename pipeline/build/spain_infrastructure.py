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
from .infrastructure import RAIL_MAIN_SCALERANK, RAIL_MAX_SCALERANK, RAIL_TIERS, SAMPLE_KM, build_rail, build_roads
from .spain_wonders import Placer
from .texts_es import HUBS, num, vintage
from .texts_es import RAIL_TIERS as RAIL_TIER_NAMES

REQUIRES = ["_world", "natural_earth_roads_es", "natural_earth_es", "aena_airports", "puertos_estado", "cities.json",
            "world.json"]
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
    "ports": "Las 28 Autoridades Portuarias de Puertos del Estado por tráfico total de mercancías, cada una en la zona de "
             "servicio terrestre de su puerto más grande.",
    "airports": "Todos los aeropuertos y helipuertos de la red de AENA, clasificados como los hubs de la FAA según su "
                "cuota de los pasajeros de España (grande, 1 % o más; mediano, 0,25 %; pequeño, 0,05 %; el resto, no hub).",
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
    ne = vintage(load_interim_payload("natural_earth_roads_es")["vintage"])
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
        "vintage": {"roads": ne, "rail": ne, "ports": vintage(ports_p["vintage"]), "airports": vintage(aena_p["vintage"])},
        "sources": ["natural_earth_roads_es", "aena_airports", "puertos_estado"],
        "rules": RULES,
        "road_classes": ROAD_CLASSES,
        "rail_tiers": [{**t, "name": RAIL_TIER_NAMES[t["id"]]} for t in RAIL_TIERS],
        "hubs": HUBS,
        "roads": roads,
        "rail": rail,
        "ports": ports,
        "airports": airports,
    })
    n0 = sum(1 for r in roads if r[2] == 0)
    print(f"    roads: {n0} motorway + {len(roads) - n0} main-road links; rail: {len(rail)} links; {len(airports)} airports, "
          f"{len(ports)} ports")
