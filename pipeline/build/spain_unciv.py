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

Nations (COMMUNITY_NATIONS, CITY_STATES, nations()): the mod adds the 17 autonomous communities as civilizations and
Ceuta and Melilla as city-states, each starting at the municipality where its government sits. A nation's cities are
its municipalities by population (Padrón), its government's seat first; its start bias, the terrain over-represented
in its land on this map; its unique, a bonus on the resource it holds most of relative to its size; its colours and
icon, its flag's (spain_flags). The map also keeps the starting locations of the bare map (starts()): Spain in Madrid
and "Any Civ" in the largest urban areas, which is what the base ruleset alone can use.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from ..core.geo import ring_area, ring_centroid
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, load_web, write_web
from ..core.lang import pick, tr
from ..countries import active
from ..sources.es.provinces import COMMUNITY_OF
from . import spain_flags, unciv
from .world import LAND
from .spain_wonders import municipality_finder

REQUIRES = ["world.json", "cities.json", "resources.json", "lenses.json", "_world", "calidad_diferenciada",
            "igme_minas", "siane", "natural_earth_es", "ine_censo_agrario", "ine_padron"]
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
    "Carne de Salamanca (IGP · provincia)": "Cattle", "Carne de Cantabria (IGP)": "Cattle",
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

# The autonomous communities as Unciv nations, by INE code (pipeline/sources/es/provinces.py COMMUNITIES): the nation's
# name, the INE code of the municipality where its government sits, and its leader. Each is read in the community's
# Statute of Autonomy, in the BOE's consolidated text (DECISIONS.md, E87):
# * name: INE's, in reading order ("Madrid, Comunidad de" → "Madrid"), with the other name in brackets: the one the
#   Statute itself gives ("Euskadi o País Vasco", LO 3/1979 art. 1, in its order) or the one in the co-official
#   language where it differs (Catalunya). Brackets and not a slash: the name is also the file name of its icon;
# * seat: the capital or seat of its government the Statute names, or the law it leaves that to (Castilla y León, Ley
#   13/1987; Castilla-La Mancha, Ley 3/1983; Galicia, Ley 1/1982; Euskadi, Decreto Legislativo 6/2023). Canarias has
#   two capitals (LO 1/2018 art. 5.1) and its Presidency sits in each in turn by legislature: the nation starts in the
#   larger by population, Las Palmas de Gran Canaria, and Santa Cruz de Tenerife is the next city in its list;
# * leader: the office, never a person: the Statute's title of the head of government, which Unciv shows as
#   "<title> de <name>" ("Presidencia de la Junta de Andalucía"; English "President of the Junta of Andalucía").
COMMUNITY_NATIONS = {
    "01": ("Andalucía", "41091", tr("Presidencia de la Junta", "President of the Junta")),
    "02": ("Aragón", "50297", tr("Presidencia", "President")),
    "03": ("Asturias", "33044", tr("Presidencia del Principado", "President of the Principality")),
    "04": ("Illes Balears", "07040", tr("Presidencia", "President")),
    "05": ("Canarias", "35016", tr("Presidencia", "President")),
    "06": ("Cantabria", "39075", tr("Presidencia de la Comunidad Autónoma", "President of the Autonomous Community")),
    "07": ("Castilla y León", "47186", tr("Presidencia de la Junta", "President of the Junta")),
    "08": ("Castilla-La Mancha", "45168", tr("Presidencia de la Junta de Comunidades", "President of the Junta de Comunidades")),
    "09": ("Cataluña (Catalunya)", "08019", tr("Presidencia de la Generalitat", "President of the Generalitat")),
    "10": ("Comunitat Valenciana", "46250", tr("Presidencia de la Generalitat", "President of the Generalitat")),
    "11": ("Extremadura", "06083", tr("Presidencia", "President")),
    "12": ("Galicia", "15078", tr("Presidencia de la Xunta", "President of the Xunta")),
    "13": ("Madrid", "28079", tr("Presidencia de la Comunidad", "President of the Community")),
    "14": ("Murcia", "30030", tr("Presidencia de la Comunidad Autónoma", "President of the Autonomous Community")),
    "15": ("Navarra", "31201", tr("Presidencia de la Comunidad Foral", "President of the Foral Community")),
    "16": ("Euskadi (País Vasco)", "01059", tr("Presidencia del Gobierno", "President of the Government")),
    "17": ("La Rioja", "26089", tr("Presidencia de la Comunidad Autónoma", "President of the Autonomous Community")),
}
# The autonomous cities, city-states of the type of their port (Unciv's CityStateTypes.json: Maritime).
CITY_STATES = {"18": ("Ceuta", "51001"), "19": ("Melilla", "52001")}
CITY_STATE_TYPE = "Maritime"
CITY_NAMES = 40  # a nation's list: its seat and its most populous municipalities (Unciv's own lists hold 30 to 40)
# Start bias: the terrain (or the coast) whose share of the community's land tiles is the highest relative to Spain's,
# among those covering at least this share of its land; none if no terrain does.
BIAS_SHARE = 0.25
BIAS_TERRAINS = ("Coast", "Hill", "Mountain", "Forest", "Marsh", "Grassland", "Plains", "Desert", "Tundra")
# The unique's resource: the one whose share of the map's tiles of it in the community's land and coast is the highest
# relative to the community's share of the land, among those it holds at least this many tiles of (or, if it holds
# none so many, among all it holds).
UNIQUE_MIN_TILES = 2
# Unciv lets no city be founded within 3 tiles of another (ModConstants.minimalCityDistance, Tile.canBeSettled): a
# nation whose seat is closer than this to a larger one's start begins on the nearest tile of its own land that is not.
MIN_SEAT_GAP = 4

DESCRIPTION = ("España de spainciv (spainciv.djinnfoundry.com): costa, relieve, ríos, cubierta del suelo y recursos "
               "sacados de datos abiertos (IGN, Copernicus CORINE, ETOPO, Natural Earth, IGME, INE y Ministerio de "
               "Agricultura). Casillas de {km:g} km. {starts}")
STARTS_TEXT = "Cada comunidad autónoma empieza en su capital; Ceuta y Melilla son ciudades-estado."  # the mod's map
BARE_STARTS_TEXT = "España empieza en Madrid; los demás, en las mayores áreas urbanas."  # the bare map


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


def tile_communities(world: dict, grid: unciv.Grid, fine: HexGrid, tiles) -> dict[int, str]:
    """Unciv tile → INE code of the autonomous community holding most of its Spanish land hexes; a water tile, the
    community holding most of the land tiles around it (so a sea resource counts for the coast it lies off)."""
    fips = [s["fips"] for s in world["states"]]
    votes: dict[int, Counter] = defaultdict(Counter)
    for c, owner in enumerate(world["owner"]):
        if owner >= 0 and world["water"][c] == LAND:
            votes[grid.locate(*fine.center(*fine.col_row(c)))][COMMUNITY_OF[fips[owner]]] += 1
    land = {t: plurality(v) for t, v in votes.items() if tiles[t].is_land}
    out = dict(land)
    for t, tile in enumerate(tiles):
        if not tile.is_land:
            around = Counter(land[n] for n in grid.ring(t) if n in land)
            if around:
                out[t] = plurality(around)
    return out


def plurality(votes: Counter) -> str:
    """The key with the most votes, the smallest on a tie."""
    return min(votes, key=lambda k: (-votes[k], k))


def lift(part: int, whole: int, share: float) -> float:
    """How over-represented something is: its share `part / whole` over the reference `share`."""
    return part / whole / share


def start_bias(terrains: Counter, n_land: int, spain: Counter, spain_land: int) -> str | None:
    """The BIAS_TERRAINS entry with the highest lift over Spain among those on BIAS_SHARE of the community's land."""
    lifts = {t: lift(terrains[t], n_land, spain[t] / spain_land) for t in BIAS_TERRAINS if terrains[t] >= BIAS_SHARE * n_land}
    ok = [t for t in lifts if lifts[t] > 1]
    return max(ok, key=lambda t: (lifts[t], -BIAS_TERRAINS.index(t)), default=None)


def unique_resource(held: Counter, totals: Counter, land_share: float) -> str | None:
    """The resource with the highest lift (its share of the map's tiles of it over `land_share`) among those held on
    UNIQUE_MIN_TILES tiles or more, or among all held if none is."""
    pool = [r for r in held if held[r] >= UNIQUE_MIN_TILES] or list(held)
    return max(pool, key=lambda r: (lift(held[r], totals[r], land_share), held[r], r), default=None)


def tile_terrains(grid: unciv.Grid, tiles, t: int) -> set[str]:
    """What a land tile counts as for the start bias: its terrains, and Coast if it touches the sea (Unciv's own
    "Coast" start bias: a start next to water)."""
    return tiles[t].terrains() | ({"Coast"} if any(not tiles[n].is_land for n in grid.ring(t)) else set())


def terrain_counts(grid: unciv.Grid, tiles, land: list[int]) -> Counter:
    """How many of the land tiles `land` count as each terrain for the start bias (tile_terrains)."""
    return Counter(x for t in land for x in tile_terrains(grid, tiles, t))


def padron_year(padron: dict) -> str:
    return str(max(padron["years"]))


def population(municipality: dict, year: str) -> int:
    """A municipality's population in the Padrón of `year` (0 if it has none that year)."""
    return municipality["pop"].get(year) or 0


def community_municipalities(padron: dict, code: str) -> dict[str, dict]:
    """INE code → Padrón entry of the municipalities of the community (or autonomous city) `code`."""
    return {g: m for g, m in padron["municipalities"].items() if COMMUNITY_OF.get(g[:2]) == code}


def city_names(code: str, seat: str, padron: dict, names: dict[str, str]) -> list[str]:
    """A community's CITY_NAMES municipalities by their SIANE names (`names`, INE code → name, in reading order): its
    government's seat, then by population in the Padrón's last year, the larger first."""
    year = padron_year(padron)
    munis = community_municipalities(padron, code)
    order = sorted(munis, key=lambda g: (g != seat, -population(munis[g], year), g))
    return [names[g] for g in order[:CITY_NAMES]]


def flag_fields(code: str) -> dict:
    """A nation's Unciv colours and the layers of its flag (spain_flags), as unciv.json keeps them."""
    flag = spain_flags.FLAGS[code]
    return {"outer": list(flag.outer), "inner": list(flag.inner), "flag": flag.json()}


def seat_starts(grid: unciv.Grid, tiles, of_tile: dict[int, str], seats: list[tuple[str, float, float]]) -> dict[str, tuple[int, int]]:
    """Nation code → (its starting tile, tiles from its seat's tile): its seat's tile (start_tile), or the nearest
    passable tile of its own land MIN_SEAT_GAP tiles or more from every start placed before it (`seats` in order)."""
    out: dict[str, tuple[int, int]] = {}
    for code, x, y in seats:
        seat = start_tile(grid, tiles, x, y)
        ok = lambda t: tiles[t].passable_land and all(distance(grid, t, s) >= MIN_SEAT_GAP for s, _ in out.values())
        if ok(seat):
            out[code] = (seat, 0)
            continue
        own = [t for t, k in of_tile.items() if k == code and ok(t)]
        if not own:
            raise RuntimeError(f"no starting tile for nation {code}")
        t = min(own, key=lambda t: (distance(grid, t, seat), t))
        out[code] = (t, distance(grid, t, seat))
    return out


def nations(world: dict, grid: unciv.Grid, fine: HexGrid, tiles, padron: dict, names: dict[str, str],
            seat_xy: dict[str, tuple[float, float]]) -> list[dict]:
    """The communities and the autonomous cities as nations of the mod, with what the mod and its page say of each
    (COMMUNITY_NATIONS, CITY_STATES and the rules above) and its starting tile ("start"). `names` gives a
    municipality's name by its INE code and `seat_xy` its position on the map."""
    of_tile = tile_communities(world, grid, fine, tiles)
    land = [t for t in of_tile if tiles[t].is_land and of_tile[t] in COMMUNITY_NATIONS]
    spain_terrains = terrain_counts(grid, tiles, land)
    held_by: dict[str, Counter] = defaultdict(Counter)  # community → resource → its tiles in the community's land and coast
    for t, k in of_tile.items():
        if tiles[t].resource:
            held_by[k][tiles[t].resource] += 1
    resources = sum((held_by[k] for k in COMMUNITY_NATIONS), Counter())
    year = padron_year(padron)
    out = []
    for code, (name, seat, leader) in COMMUNITY_NATIONS.items():
        mine = [t for t in land if of_tile[t] == code]
        held = held_by[code]
        resource = unique_resource(held, resources, len(mine) / len(land))
        munis = community_municipalities(padron, code).values()
        out.append({
            "code": code, "name": name, "city_state": False, "leader": leader, "seat": seat,
            "cities": city_names(code, seat, padron, names), "population": sum(population(m, year) for m in munis),
            "municipalities": len(munis), "land_tiles": len(mine),
            "start_bias": start_bias(terrain_counts(grid, tiles, mine), len(mine), spain_terrains, len(land)),
            "resource": resource, "resource_tiles": held[resource], "resource_map_tiles": resources[resource],
            **flag_fields(code),
        })
    for code, (name, seat) in CITY_STATES.items():
        out.append({"code": code, "name": name, "city_state": True, "type": CITY_STATE_TYPE, "seat": seat,
                    "cities": city_names(code, seat, padron, names)[:1], **flag_fields(code)})
    order = sorted(out, key=lambda n: (n["city_state"], -n.get("population", 0), n["code"]))
    placed = seat_starts(grid, tiles, of_tile, [(n["code"], *seat_xy[n["seat"]]) for n in order])
    for n in out:
        n["start"], n["start_off_seat"] = placed[n["code"]]
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
    # The designations' names in every language, for the Unciv page's list of those left out ("(DOP)", "(PDO)").
    food_names = next(lens for lens in load_web("lenses.json", texts=True)["lenses"] if lens["id"] == "food")["names"]
    families = {n["name"]: n["family"] for n in load_interim("calidad_diferenciada")["names"]}
    by_designation = designation_resources(food["names"], families)
    weights = area_weights(grid, lambda c: fine.center(*fine.col_row(c)), food["labels"], set(by_designation))
    horses = horse_areas(world, grid, fine, load_interim("ine_censo_agrario"))

    for resource in ORDER:
        done, missed = place_points(resource, points.get(resource, []), grid, tiles)
        placed[resource] += done
        unplaced[resource] += missed
        designations = [k for k, r in by_designation.items() if r == resource]
        areas = [(weights[k], food_names[k])  # smaller areas first
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
    munis = {m["geoid"]: m for m in load_interim("siane")["municipalities"]}
    padron = load_interim("ine_padron")
    nation_list = nations(world, grid, fine, tiles, padron, {g: m["name"] for g, m in munis.items()},
                          {g: proj(*m["centre"]) for g, m in munis.items()})
    nation_starts = [(n.pop("start"), n["name"], "Normal" if n["city_state"] else "Human") for n in nation_list]
    doc = unciv.tile_map(grid, tiles, MAP_NAME, DESCRIPTION.format(km=TILE_KM, starts=STARTS_TEXT), nation_starts, MOD_NAME)
    bare = unciv.tile_map(grid, tiles, MAP_NAME, DESCRIPTION.format(km=TILE_KM, starts=BARE_STARTS_TEXT),
                          [s[:3] for s in start_list])
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
        "not_placed_designations": sorted(unplaced_names, key=lambda n: pick(n, "es")),
        "natural_wonders": [wonder],
        "start_gap_tiles": START_GAP,
        "starts": [{"nation": nation, "usage": usage, "city": city} for _, nation, usage, city in start_list],
        "nations": nation_list, "padron_year": padron_year(padron),
    }
    write_web("unciv.json", {"summary": summary, "map": doc,
                             "bare": {k: bare[k] for k in ("startingLocations", "description")}})
    print(f"    {grid.width}×{grid.height} tiles, {len(land)} land; " + ", ".join(f"{r} {n}" for r, n in summary["resources"].items())
          + f"; {n_river_edges} river edges; not placed: {summary['not_placed']}")
