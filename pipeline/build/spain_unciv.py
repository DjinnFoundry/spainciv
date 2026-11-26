"""Spain as an Unciv map (unciv.json): the terrain of world.json on 25 km tiles, with real resources, the Rock of
Gibraltar and starting locations at the largest urban areas. pipeline/build/unciv.py has the format, the resampling
and the terrain rules; this builder chooses what Spain's data puts on the map. `pipeline package` (pipeline/site.py,
pipeline/play.py) turns unciv.json into the map file, the mod zip and the "Jugar en Unciv" page.

Tiles are 25 km across, the hexes of the original usaciv map: 83 × 53 tiles (4,399) cover the whole map, below Unciv's
Huge preset (87 × 57), with some 950 tiles of Spanish land. Smaller tiles would make a map larger than any Unciv
preset, slow on a phone.

Resources, one per tile and only where the ruleset lets them stand (DEPOSITS, MINE_TYPES, SUBSTANCES, FAMILIES and
DESIGNATIONS below):
* points: the BDMIN's large and medium deposits, worked or not (coal, uranium, bauxite, iron, gold, copper, silver), and
  the IGME's active workings of 2019 by substance, at their deposit (copper, gold) or their municipality's centre (iron
  oxides, hydrocarbons, marble, salt, ornamental stone), on their tile or the nearest neighbour that fits. Several of one
  resource on a tile or next to one already placed make one.
* areas: the protected designations whose product is an Unciv resource (wine, citrus, saffron and paprika, beef, lamb,
  fish) or the mod's own Iberian pig (the four Iberian ham DOPs), each on the tile holding most of its area where it
  fits (a sea resource on the coast tile touching most of it); smaller areas first, so the large ones that overlap them
  take another tile. Horses go to the agricultural comarcas densest in equines (horse_areas), the same way.
No cheese or other ham: Unciv has no such resource. The map names the mod (MOD_NAME) because of the pig.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from ..core.geo import ring_area, ring_centroid
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, load_web, write_web
from ..countries import active
from . import unciv
from .spain_wonders import municipality_finder

REQUIRES = ["world.json", "cities.json", "resources.json", "lenses.json", "_world", "calidad_diferenciada",
            "igme_minas", "siane", "natural_earth_es", "ine_censo_agrario"]
PRODUCES = ["unciv.json"]
COUNTRIES = ("es",)

TILE_KM = 25.0
MAP_NAME = "España"
MOD_NAME = "Spainciv Unciv"  # the folder Unciv makes from the repository's name (Github.kt: repoNameToFolderName)
MOD_REPO = "DjinnFoundry/Spainciv-Unciv"
STARTS = 12  # Spain at Madrid and "Any Civ" at the 11 largest urban areas far enough apart
START_GAP = 6  # tiles between starting locations (150 km)
MIN_START_LANDMASS = 100  # tiles: no starting location on an island smaller than this (Mallorca, the Canaries)

# IGME substance → resource. Copper and gold come placed from resources.json (their BDMIN deposits).
MINE_TYPES = {"copper": "Copper", "gold": "Gold Ore"}
SUBSTANCES = {
    "ÓXIDOS DE HIERRO": "Iron", "HIDROCARBUROS": "Oil",
    "MÁRMOL ORNAMENTAL": "Marble", "MÁRMOL (OTROS USOS)": "Marble",
    "SAL GEMA": "Salt", "SAL MARINA": "Salt", "SAL MANANTIAL": "Salt",
    "GRANITO ORNAMENTAL": "Stone", "CALIZA ORNAMENTAL": "Stone", "PIZARRA ORNAMENTAL": "Stone",
    "ARENISCA ORNAMENTAL": "Stone", "CUARCITA ORNAMENTAL": "Stone",
}
# BDMIN substance → resource, for its large and medium deposits, worked or not (a deposit of several gives each).
DEPOSITS = {"Hulla": "Coal", "Antracita": "Coal", "Lignito": "Coal", "Carbón": "Coal", "Uranio y radiactivos": "Uranium",
            "Bauxita": "Aluminum", "Hierro": "Iron", "Oro": "Gold Ore", "Cobre": "Copper", "Plata": "Silver"}
# Resources Unciv allows on so few terrains that most deposits fall on none of them (uranium: forest, tundra, marsh;
# aluminium: hill, desert, tundra, snow): they look for an allowed tile this many rings out (2 rings: up to ~50 km).
RINGS = {"Uranium": 2, "Aluminum": 2}
# Horses: the agricultural comarcas with at least HORSE_DENSITY times Spain's equines per km² (Censo Agrario 2020).
HORSE_DENSITY = 4.0
# Municipalities the 2019 list names as they were called then → their name in SIANE 2026; "SIN DEFINIR" (no
# municipality) leaves a working unplaced.
RENAMED = {"Castrillo Matajudíos": "Castrillo Mota de Judíos", "Sant Carles de la Ràpita": "La Ràpita"}
UNDEFINED = "SIN DEFINIR"
# Protected designations (MAPA) → resource: a whole family, or one name.
FAMILIES = {"Vinos": "Wine", "Pescados, Moluscos, Crustáceos": "Fish"}
DESIGNATIONS = {
    "Cítricos Valencianos (IGP)": "Citrus", "Clementinas de las Tierras del Ebro (IGP)": "Citrus",
    "Azafrán de La Mancha (DOP)": "Spices", "Pimentón de Murcia (DOP)": "Spices", "Pimentón de la Vera (DOP)": "Spices",
    "Carne Morucha de Salamanca (IGP)": "Cattle", "Carne de Cantabria (IGP)": "Cattle",
    "Carne de Vacuno del País Vasco o Euskal Okela (IGP)": "Cattle", "Carne de la Sierra de Guadarrama (IGP)": "Cattle",
    "Carne de Ávila (IGP)": "Cattle", "Ternera Asturiana (IGP)": "Cattle", "Ternera Gallega (IGP)": "Cattle",
    "Ternera de Extremadura (IGP)": "Cattle", "Ternera de Navarra o Nafarroako Aratxea (IGP)": "Cattle",
    "Cordero Manchego (IGP)": "Sheep", "Cordero Segureño (IGP)": "Sheep", "Cordero de Extremadura (IGP)": "Sheep",
    "Cordero de Navarra o Nafarroako Arkumea (IGP)": "Sheep", "Lechazo de Castilla y león (IGP)": "Sheep",
    "Ternasco de Aragón (IGP)": "Sheep",
    "Plátano de Canarias (IGP)": "Bananas",
    # The four DOPs of Iberian ham; Teruel, Trévelez and Serón protect hams of white pigs, which are not Iberian.
    "Dehesa de Extremadura (DOP)": "Cerdo ibérico", "Guijuelo (DOP)": "Cerdo ibérico", "Jabugo (DOP)": "Cerdo ibérico",
    "Los Pedroches (DOP)": "Cerdo ibérico",
}
# Placement order: strategic, then luxury, then bonus resources; points before areas within a kind.
ORDER = ["Iron", "Horses", "Coal", "Oil", "Aluminum", "Uranium", "Gold Ore", "Silver", "Copper", "Marble", "Salt",
         "Wine", "Cerdo ibérico", "Citrus", "Spices", "Cattle", "Sheep", "Fish", "Bananas", "Stone"]
WONDER = ("Rock of Gibraltar", "Gibraltar")  # Unciv's natural wonder, and the Natural Earth country it stands on

DESCRIPTION = ("España de spainciv (spainciv.djinnfoundry.com): costa, relieve, ríos, cubierta del suelo y recursos "
               "sacados de datos abiertos (IGN, Copernicus CORINE, ETOPO, Natural Earth, IGME y Ministerio de "
               "Agricultura). Casillas de {km:g} km. España empieza en Madrid; los demás, en las mayores áreas urbanas.")


def designation_resources(names: list[str], families: dict[str, str]) -> dict[int, str]:
    """Index in the food lens's names → the resource of that designation."""
    missing = sorted(set(DESIGNATIONS) - set(names))
    if missing:
        raise RuntimeError(f"designations not in the food lens: {missing}")
    out = {}
    for k, name in enumerate(names):
        resource = DESIGNATIONS.get(name) or FAMILIES.get(families.get(name, ""))
        if resource:
            out[k] = resource
    return out


def area_weights(grid: unciv.Grid, fine_centers, labels: list[list[int] | None], wanted: set[int]) -> dict[int, Counter]:
    """designation index → Counter of Unciv tile → fine hexes of its area in that tile."""
    out: dict[int, Counter] = defaultdict(Counter)
    for c, ks in enumerate(labels):
        for k in ks or ():
            if k in wanted:
                t = grid.locate(*fine_centers(c))
                if t >= 0:
                    out[k][t] += 1
    return out


def horse_areas(world: dict, grid: unciv.Grid, fine: HexGrid, census: dict) -> dict[str, Counter]:
    """The comarcas with HORSE_DENSITY times Spain's equines per km² or more → Counter of Unciv tile → their fine hexes.
    A comarca's area is its fine land hexes (each municipality's hexes belong to its comarca)."""
    comarca_of, heads = census["comarca_of"], {c: v["heads"] for c, v in census["comarcas"].items() if v["heads"]}
    geoids = [c["geoid"] for c in world["counties"]]
    cells: dict[str, list[int]] = defaultdict(list)
    for c, county in enumerate(world["county"]):
        if county >= 0 and (comarca := comarca_of.get(geoids[county])):
            cells[comarca].append(c)
    spain = sum(heads.values()) / sum(len(v) for v in cells.values())
    density = {c: heads[c] / len(cells[c]) for c in heads if cells.get(c)}
    dense = sorted((c for c, d in density.items() if d >= HORSE_DENSITY * spain), key=lambda c: (-density[c], c))
    tile_of = lambda cell: grid.locate(*fine.center(*fine.col_row(cell)))
    return {c: Counter(t for t in map(tile_of, cells[c]) if t >= 0) for c in dense}


def place_points(resource: str, points: list[tuple[float, float]], grid: unciv.Grid, tiles) -> tuple[int, int]:
    """Point resources, one per tile and none next to a tile that already has the same one: (placed, not placed)."""
    placed = unplaced = 0
    for x, y in points:
        t = grid.locate(x, y)
        if t >= 0 and any(tiles[c].resource == resource for c in [t, *grid.ring(t)]):
            continue
        if unciv.place_at(resource, grid, tiles, x, y, RINGS.get(resource, 1)) >= 0:
            placed += 1
        else:
            unplaced += 1
    return placed, unplaced


def landmasses(grid: unciv.Grid, tiles) -> list[int]:
    """Each tile's landmass size in tiles (0 for water)."""
    size = [0] * len(tiles)
    for group in unciv.components([t for t, tile in enumerate(tiles) if tile.is_land], grid.ring):
        for t in group:
            size[t] = len(group)
    return size


def start_tile(grid: unciv.Grid, tiles, x: float, y: float) -> int:
    """The passable land tile nearest to (x, y), within two rings."""
    t = grid.locate(x, y)
    cands = {t, *grid.ring(t)}
    cands |= {n for c in list(cands) for n in grid.ring(c)}
    ok = [c for c in cands if tiles[c].passable_land]
    return min(ok, key=lambda c: (abs(grid.center(c)[0] - x) + abs(grid.center(c)[1] - y), c)) if ok else -1


def distance(grid: unciv.Grid, a: int, b: int) -> int:
    """Tiles between two tiles (HexMath.getDistance: the cube distance of the hex coordinates)."""
    (ax, ay), (bx, by) = grid.positions[a], grid.positions[b]
    dx, dy = ax - bx, ay - by
    return max(abs(dx), abs(dy), abs(dx - dy))


def starts(grid: unciv.Grid, tiles, cities: list[dict], capital: str) -> list[tuple[int, str, str, str]]:
    """(tile, nation, usage, city): Spain at the capital, then "Any Civ" at the largest areas START_GAP tiles apart."""
    mass = landmasses(grid, tiles)
    out = []
    for c in sorted(cities, key=lambda c: (c["id"] != capital, -c["population"])):
        t = start_tile(grid, tiles, c["x"], c["y"])
        if t < 0 or mass[t] < MIN_START_LANDMASS or any(distance(grid, t, s[0]) < START_GAP for s in out):
            continue
        out.append((t, "Spain", "Human", c["name"]) if c["id"] == capital else (t, unciv.SPECTATOR, "Player", c["name"]))
        if len(out) == STARTS:
            break
    if not out or out[0][1] != "Spain":
        raise RuntimeError("no starting location for Spain at the capital")
    return out


def build() -> None:
    world = load_web("world.json")
    proj = active().world_projection(load_interim("_world"))
    fine = HexGrid(**world["grid"])
    grid = unciv.Grid.covering(fine, TILE_KM)
    tiles = unciv.resample(world, grid)
    unciv.terrain(world, grid, tiles)
    rivers = [list(zip(r["pts"][::2], r["pts"][1::2])) for r in world["rivers"]]
    n_river_edges = unciv.river_edges(grid, tiles, rivers)

    # The natural wonder: the Rock of Gibraltar on the tile of Gibraltar (Natural Earth's polygon).
    wonder, country = WONDER
    ring = max((r for c in load_interim("natural_earth_es")["countries"] if c["name"] == country for r in c["rings"]),
               key=lambda r: abs(ring_area(r)))
    t = start_tile(grid, tiles, *proj(*ring_centroid(ring)))
    tiles[t].base, tiles[t].features, tiles[t].wonder = "Mountain", [], wonder

    # Point resources.
    find = municipality_finder(load_interim("siane")["municipalities"])
    points: dict[str, list[tuple[float, float]]] = defaultdict(list)
    placed, unplaced, unplaced_names = Counter(), Counter(), []
    for it in load_web("resources.json")["items"]:
        if it["type"] in MINE_TYPES:
            points[MINE_TYPES[it["type"]]].append((it["x"], it["y"]))
    igme = load_interim("igme_minas")
    for d in igme["deposits"]:
        for substance in d["substances"]:
            points[DEPOSITS[substance]].append(proj(d["lon"], d["lat"]))
    for w in igme["workings"]:
        resource = SUBSTANCES.get(w["substance"])
        if not resource:
            continue
        if w["municipality"] == UNDEFINED:
            unplaced[resource] += 1
        else:
            muni = find(RENAMED.get(w["municipality"], w["municipality"]), w["province"])
            points[resource].append(proj(*muni["centre"]))

    # Area resources.
    food = next(lens for lens in load_web("lenses.json")["lenses"] if lens["id"] == "food")
    families = {n["name"]: n["family"] for n in load_interim("calidad_diferenciada")["names"]}
    by_designation = designation_resources(food["names"], families)
    weights = area_weights(grid, lambda c: fine.center(*fine.col_row(c)), food["labels"], set(by_designation))
    horses = horse_areas(world, grid, fine, load_interim("ine_censo_agrario"))

    for resource in ORDER:
        done, missed = place_points(resource, points.get(resource, []), grid, tiles)
        placed[resource] += done
        unplaced[resource] += missed
        designations = [k for k, r in by_designation.items() if r == resource]
        areas = [(weights[k], food["names"][k])  # smaller areas first
                 for k in sorted(designations, key=lambda k: (sum(weights[k].values()), k))]
        if resource == "Horses":
            areas += [(area, None) for area in horses.values()]
        for area, name in areas:
            if area and unciv.place_in(resource, grid, tiles, area) >= 0:
                placed[resource] += 1
            else:
                unplaced[resource] += 1
                if name:
                    unplaced_names.append(name)

    cities = load_web("cities.json")
    start_list = starts(grid, tiles, cities, world["country"]["capital_city"])
    doc = unciv.tile_map(grid, tiles, MAP_NAME, DESCRIPTION.format(km=TILE_KM), [s[:3] for s in start_list], MOD_NAME)
    land = [t for t in tiles if t.is_land]
    summary = {
        "unciv_release": unciv.UNCIV_RELEASE, "map_name": MAP_NAME, "mod": {"name": MOD_NAME, "repo": MOD_REPO},
        "tile_km": TILE_KM, "horse_comarcas": len(horses), "horse_density": HORSE_DENSITY,
        "grid": {"spacing": grid.spacing, "width": grid.width, "height": grid.height, "centre": list(grid.centre)},
        "tiles": len(tiles), "land_tiles": len(land), "national_land_tiles": sum(1 for t in land if t.national),
        "terrain": dict(sorted(Counter(t.base for t in tiles).items())),
        "features": dict(sorted(Counter(f for t in tiles for f in t.features).items())),
        "river_edges": n_river_edges,
        "resources": {r: placed[r] for r in ORDER if placed[r]},
        "not_placed": {r: unplaced[r] for r in ORDER if unplaced[r]},
        "not_placed_designations": sorted(unplaced_names),
        "natural_wonders": [wonder],
        "start_gap_tiles": START_GAP,
        "starts": [{"nation": nation, "usage": usage, "city": city} for _, nation, usage, city in start_list],
    }
    write_web("unciv.json", {"summary": summary, "map": doc})
    print(f"    {grid.width}×{grid.height} tiles, {len(land)} land; " + ", ".join(f"{r} {n}" for r, n in summary["resources"].items())
          + f"; {n_river_edges} river edges; not placed: {summary['not_placed']}")
