"""The country as a playable Unciv map, and the Unciv mod that ships it.

Unciv (https://github.com/yairm210/Unciv) is the open-source remake of Civilization V, for Windows, macOS, Linux and
Android. Everything below was read in its source at the release the map is tested with (UNCIV_RELEASE):

* A map is a `TileMap` (core/src/com/unciv/logic/map/TileMap.kt) serialized to JSON: `mapParameters`, `tileList`,
  `startingLocations` (position, nation, usage) and `description`. A tile (core/src/com/unciv/logic/map/tile/Tile.kt)
  has `position`, `baseTerrain`, `terrainFeatures`, `naturalWonder`, `resource`, `resourceAmount` and three river
  flags, `hasBottomRightRiver`, `hasBottomRiver` and `hasBottomLeftRiver`: a river runs along a tile's edge, and each
  tile owns its three lower edges.
* The file is that JSON gzipped and then base64-encoded (core/src/com/unciv/logic/files/FileConversions.kt); a plain
  JSON file loads too. It has no extension: its name is the map's name. Unciv lists the files in its own `maps/` folder
  and in the `maps/` folder of every installed mod (core/src/com/unciv/ui/screens/newgamescreen/MapFileSelectTable.kt).
* Hexes are flat-topped and laid out in columns (core/src/com/unciv/logic/map/HexMath.kt): a rectangular map of
  width × height has columns -width/2 … (width-1)/2 and rows -height/2 … (height-1)/2, odd columns half a row higher,
  and column c, row r is the hex coordinate ((2r + odd - c) / 2, (2r + odd + c) / 2) (`getTileCoordsFromColumnRow`).
  The neighbour at 12 o'clock is (+1, +1), at 2 (0, +1), at 4 (-1, 0), at 6 (-1, -1), at 8 (0, -1) and at 10 (+1, 0)
  (`clockPositionToHexcoordMap`).
* Loading a map normalizes each tile to the ruleset (core/src/com/unciv/logic/map/tile/TileNormalizer.kt): a feature
  that does not occur on the base terrain and a resource whose terrains the tile lacks are dropped, and a natural
  wonder with `turnsInto` turns its tile into that terrain. So the map only puts things where the base ruleset (Civ V
  - Gods & Kings, android/assets/jsons/Civ V - Gods & Kings/Terrains.json and TileResources.json) allows them.
* A starting location names a nation, or "Spectator", which the map editor shows as "Any Civ": a player whose nation
  has no location of its own takes one of those (core/src/com/unciv/logic/GameStarter.kt, getCivStartingLocation).
  The `Human` usage marks the nation the new-game screen offers the human player ("Use nations from map").
* A mod is a folder with `jsons/ModOptions.json`, `maps/` and `preview.png` (preview.jpg or .png, shown by the mod
  manager: core/src/com/unciv/ui/screens/modmanager/ModInfoAndActionPane.kt). The in-game mod browser lists the GitHub
  repositories with the topic `unciv-mod`, and the Maps category those with `unciv-mod-maps`
  (core/src/com/unciv/logic/github/GithubAPI.kt, android/assets/jsons/ModCategories.json). "Download mod from URL"
  also takes any zip whose single top folder is the mod (GithubAPI.kt: Repo.parseUrl, resolveZipStructure).

This module turns world.json's fine hex grid into a coarser Unciv grid (resample), each Unciv tile's terrain from the
fine hexes under it (terrain), rivers onto tile edges (river_edges), and writes the map file and the mod. What goes on
the map besides the terrain (resources, wonders, starting locations) is chosen by each country's builder
(pipeline/build/spain_unciv.py) with the helpers here, which keep every resource on a terrain the ruleset allows.
"""

from __future__ import annotations

import base64
import gzip
import json
import math
from collections import Counter, deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from functools import cached_property

from ..core.hexgrid import HexGrid
from ..core.raster import Canvas
from .world import COAST_DEPTH_M, GROUP_ID, LAKE, LAND, MOUNTAINS, PEAKS

UNCIV_RELEASE = "5.0.1"  # https://github.com/yairm210/Unciv/releases/tag/5.0.1 (2026-11-17)
BASE_RULESET = "Civ V - Gods & Kings"
SPECTATOR = "Spectator"  # the "Any Civ" starting location (core/src/com/unciv/Constants.kt)
SQRT3 = math.sqrt(3)

# Hex-coordinate step to the neighbour at each clock position, and which tile owns the edge between them: a tile's
# flags cover its bottom-right (4), bottom (6) and bottom-left (8) edges; the other three belong to the neighbour.
CLOCK = {12: (1, 1), 2: (0, 1), 4: (-1, 0), 6: (-1, -1), 8: (0, -1), 10: (1, 0)}
RIVER_FLAG = {4: "hasBottomRightRiver", 6: "hasBottomRiver", 8: "hasBottomLeftRiver"}
OPPOSITE = {12: 6, 2: 8, 4: 10, 6: 12, 8: 2, 10: 4}
EDGE_CLOCK = (2, 12, 10, 8, 6, 4)  # the clock position across the edge from corner k to corner k + 1 (Grid.corners)

# --- the base ruleset (android/assets/jsons/Civ V - Gods & Kings) -----------------------------------------------------

# Terrains.json `occursOn` of the features the map uses.
FEATURE_ON = {"Hill": {"Tundra", "Plains", "Grassland", "Desert", "Snow"},
              "Forest": {"Tundra", "Plains", "Grassland", "Hill"},
              "Marsh": {"Grassland"}}
WATER_TERRAINS = {"Ocean", "Coast", "Lakes"}
# TileResources.json: the terrains (base or feature) each resource the map uses can be found on, its type, and for a
# strategic one its `majorDepositAmount` "default" (the amount the map generator gives a major deposit).
RESOURCES = {
    "Iron": ("Strategic", {"Grassland", "Plains", "Desert", "Tundra", "Snow", "Hill", "Marsh"}, 6),
    "Horses": ("Strategic", {"Plains", "Grassland", "Hill"}, 4),
    "Coal": ("Strategic", {"Grassland", "Plains", "Hill", "Jungle", "Forest", "Marsh"}, 7),
    "Oil": ("Strategic", {"Desert", "Coast", "Tundra", "Snow", "Marsh", "Jungle"}, 7),
    "Aluminum": ("Strategic", {"Desert", "Tundra", "Hill", "Snow", "Jungle"}, 8),
    "Uranium": ("Strategic", {"Marsh", "Jungle", "Forest", "Tundra", "Snow"}, 4),
    "Gold Ore": ("Luxury", {"Desert", "Hill", "Forest", "Jungle"}, 0),
    "Silver": ("Luxury", {"Hill", "Forest", "Jungle", "Tundra", "Grassland"}, 0),
    "Copper": ("Luxury", {"Hill", "Forest", "Jungle", "Grassland", "Tundra"}, 0),
    "Marble": ("Luxury", {"Desert", "Plains", "Hill", "Grassland"}, 0),
    "Salt": ("Luxury", {"Desert", "Tundra", "Plains", "Forest"}, 0),
    "Wine": ("Luxury", {"Grassland", "Plains"}, 0),
    "Citrus": ("Luxury", {"Jungle", "Forest", "Flood plains"}, 0),
    "Spices": ("Luxury", {"Jungle", "Forest", "Marsh"}, 0),
    "Cattle": ("Bonus", {"Grassland"}, 0),
    "Sheep": ("Bonus", {"Hill"}, 0),
    "Fish": ("Bonus", {"Coast"}, 0),
    "Stone": ("Bonus", {"Grassland", "Desert", "Tundra"}, 0),
    "Bananas": ("Bonus", {"Jungle"}, 0),
}
# Resources a mod adds to the base ruleset: its TileResources.json entry (TileResource.kt fields). "Doesn't generate
# naturally" keeps the map generator from scattering it on other maps while the mod is on.
MOD_RESOURCES = {
    "Cerdo ibérico": {
        "resourceType": "Luxury", "terrainsCanBeFoundOn": ["Plains", "Grassland", "Hill"], "food": 1, "gold": 1,
        "improvement": "Pasture", "improvementStats": {"gold": 1}, "uniques": ["Doesn't generate naturally"],
    },
}
RESOURCES |= {name: (r["resourceType"], set(r["terrainsCanBeFoundOn"]), 0) for name, r in MOD_RESOURCES.items()}
# Terrains.json "RGB" of each terrain, for the preview image (Forest and Marsh have none: these are their map colours).
RGB = {"Ocean": (43, 87, 151), "Coast": (70, 138, 216), "Lakes": (0, 171, 169), "Grassland": (0, 163, 0),
       "Plains": (153, 180, 51), "Tundra": (124, 62, 57), "Desert": (230, 172, 0), "Snow": (230, 238, 255),
       "Mountain": (102, 102, 102), "Hill": (105, 125, 72), "Forest": (34, 102, 34), "Marsh": (70, 120, 110)}

# --- terrain rules (each documented in DECISIONS.md and on the play page) ---------------------------------------------

LAND_SHARE = 0.5  # a tile is land when at least half of the fine hexes under it are
MOUNTAIN_SHARE = 0.85  # Mountain: this share of its land hexes are mountains (relief ≥ 2), or one is a peak (3)
HILL_SHARE = 0.25  # Hill: this share of its land hexes are mountains (relief ≥ 2)
TUNDRA_ELEV_M = 1500  # Tundra: mean altitude of its land hexes
FOREST_PCT = 35  # Forest: mean forest share of its land cover
MARSH_PCT = 25  # Marsh: mean wetland share of its land cover

COVER_BARREN, COVER_ICE = GROUP_ID["barren"], GROUP_ID["ice"]


@dataclass(frozen=True)
class Grid:
    """A rectangular Unciv map laid over the map's km frame (x right, y down), centred on it."""

    spacing: float  # km between the centres of neighbouring tiles (the width of a tile, flat side to flat side)
    width: int  # columns
    height: int  # rows
    centre: tuple[float, float]  # km position of column 0, row 0

    @classmethod
    def covering(cls, fine: HexGrid, spacing: float) -> "Grid":
        """The smallest grid, centred on the fine grid, whose tiles hold every fine hex centre."""
        width_km, height_km = fine.center(fine.cols - 1, 1)[0], fine.center(0, fine.rows - 1)[1]
        half_cols = math.ceil(width_km / 2 / (1.5 * spacing / SQRT3))  # odd sizes: the tiles reach as far both ways
        half_rows = math.ceil(height_km / 2 / spacing)
        return cls(spacing, 2 * half_cols + 1, 2 * half_rows + 1, (width_km / 2, height_km / 2))

    @property
    def radius(self) -> float:
        return self.spacing / SQRT3

    @cached_property
    def tiles(self) -> list[tuple[int, int]]:
        """(column, row) of every tile, in the order TileMap's rectangular constructor lists them."""
        span = lambda n: range(-(n // 2), (n - 1) // 2 + 1)  # Kotlin's -n / 2 rounds toward zero
        return [(c, r) for c in span(self.width) for r in span(self.height)]

    @cached_property
    def _index(self) -> dict[tuple[int, int], int]:
        return {cr: i for i, cr in enumerate(self.tiles)}

    @cached_property
    def positions(self) -> list[tuple[int, int]]:
        return [hex_coord(c, r) for c, r in self.tiles]

    @cached_property
    def _by_position(self) -> dict[tuple[int, int], int]:
        return {p: i for i, p in enumerate(self.positions)}

    def center(self, i: int) -> tuple[float, float]:
        c, r = self.tiles[i]
        return self.centre[0] + 1.5 * self.radius * c, self.centre[1] - self.spacing * (r + 0.5 * (abs(c) % 2))

    def locate(self, x: float, y: float) -> int:
        """The tile whose hex holds (x, y) (the nearest centre), or -1 off the map."""
        c0 = round((x - self.centre[0]) / (1.5 * self.radius))
        best = None
        for c in (c0 - 1, c0, c0 + 1):
            r0 = round((self.centre[1] - y) / self.spacing - 0.5 * (abs(c) % 2))
            for r in (r0 - 1, r0, r0 + 1):
                i = self._index.get((c, r))
                if i is not None:
                    d = math.dist(self.center(i), (x, y))
                    if best is None or d < best[0]:
                        best = (d, i)
        return -1 if best is None or best[0] > self.radius else best[1]

    def neighbours(self, i: int) -> dict[int, int]:
        """clock position → tile index of each neighbour on the map."""
        x, y = self.positions[i]
        out = {}
        for clock, (dx, dy) in CLOCK.items():
            j = self._by_position.get((x + dx, y + dy))
            if j is not None:
                out[clock] = j
        return out

    def ring(self, i: int) -> list[int]:
        return list(self.neighbours(i).values())

    def corners(self, i: int) -> list[tuple[int, int]]:
        """The tile's six corners as exact lattice keys (half-radius steps across, half-spacing steps up), from the
        right one counter-clockwise; corner k and k + 1 bound the edge toward EDGE_CLOCK[k]."""
        c, r = self.tiles[i]
        u, v = 3 * c, 2 * r + abs(c) % 2
        return [(u + du, v + dv) for du, dv in ((2, 0), (1, 1), (-1, 1), (-2, 0), (-1, -1), (1, -1))]

    def edges(self, i: int) -> list[tuple[int, tuple[int, int], tuple[int, int]]]:
        """(clock position across it, one end corner, the other) of each of the tile's six edges."""
        k = self.corners(i)
        return [(clock, k[e], k[(e + 1) % 6]) for e, clock in enumerate(EDGE_CLOCK)]

    def corner_xy(self, key: tuple[int, int]) -> tuple[float, float]:
        u, v = key
        return self.centre[0] + u * self.radius / 2, self.centre[1] - v * self.spacing / 2

    def map_size(self) -> dict:
        """mapParameters.mapSize of a custom rectangular map (MapSize.kt: radius = getEquivalentHexagonalRadius)."""
        n = self.width * self.height
        return {"name": "Custom", "radius": round((math.sqrt(12 * n - 3) - 3) / 6), "width": self.width, "height": self.height}


def hex_coord(column: int, row: int) -> tuple[int, int]:
    """HexMath.getTileCoordsFromColumnRow."""
    two_rows = 2 * row + abs(column) % 2
    return (two_rows - column) // 2, (two_rows + column) // 2


# --- resampling and terrain ---------------------------------------------------------------------------------------------


@dataclass
class Tile:
    """What one Unciv tile covers of the fine grid, and what the map puts on it."""

    cells: list[int] = field(default_factory=list)  # fine hexes whose centre falls in the tile
    land: list[int] = field(default_factory=list)  # those that are land
    national: list[int] = field(default_factory=list)  # those that are the country's own land
    base: str = "Ocean"
    features: list[str] = field(default_factory=list)
    resource: str | None = None
    wonder: str | None = None
    rivers: set[int] = field(default_factory=set)  # clock positions of its edges with a river

    @property
    def is_land(self) -> bool:
        return self.base not in WATER_TERRAINS

    @property
    def passable_land(self) -> bool:
        return self.is_land and self.base != "Mountain" and self.wonder is None

    def terrains(self) -> set[str]:
        return {self.base, *self.features}


def resample(world: dict, grid: Grid) -> list[Tile]:
    """Each Unciv tile with the fine hexes under it; land where at least LAND_SHARE of them are land, and every island
    of the fine map keeps at least one land tile (the one holding most of its hexes)."""
    fine = HexGrid(**world["grid"])
    water, owner = world["water"], world["owner"]
    tiles = [Tile() for _ in grid.tiles]
    tile_of = [-1] * fine.size
    for c in range(fine.size):
        t = grid.locate(*fine.center(*fine.col_row(c)))
        if t < 0:
            raise ValueError(f"fine hex {c} falls off the Unciv grid: build it with Grid.covering")
        tile_of[c] = t
        tiles[t].cells.append(c)
        if water[c] == LAND:
            tiles[t].land.append(c)
            if owner[c] >= 0:
                tiles[t].national.append(c)
    land = {t for t, tile in enumerate(tiles) if tile.cells and len(tile.land) >= LAND_SHARE * len(tile.cells)}
    for island in components([c for c in range(fine.size) if water[c] == LAND], fine.neighbours):
        held = Counter(tile_of[c] for c in island)
        if held and not land & held.keys():
            land.add(min(held, key=lambda t: (-held[t], t)))
    for t in land:
        tiles[t].base = "Plains"  # terrain() decides
    return tiles


def components(cells: list[int], neighbours: Callable[[int], Iterable[int]]) -> list[list[int]]:
    """Connected groups of `cells`, `neighbours` giving the cells next to one (HexGrid.neighbours, Grid.ring)."""
    todo, out = set(cells), []
    while todo:
        start = todo.pop()
        group, queue = [start], deque([start])
        while queue:
            for n in neighbours(queue.popleft()):
                if n in todo:
                    todo.remove(n)
                    group.append(n)
                    queue.append(n)
        out.append(sorted(group))
    return out


def terrain(world: dict, grid: Grid, tiles: list[Tile]) -> None:
    """Base terrain and features of every tile, from the fine hexes under it (the rules above)."""
    water, elev, relief, cover, pct = world["water"], world["elev"], world["relief"], world["cover"], world["pct"]
    for t, tile in enumerate(tiles):
        if not tile.is_land:
            tile.base = water_terrain(tile, tiles, grid.ring(t), water, elev)
            continue
        land = tile.land or tile.cells  # an island kept on a tile mostly of sea
        rugged = sum(relief[c] >= MOUNTAINS for c in land) / len(land)
        if rugged >= MOUNTAIN_SHARE or any(relief[c] == PEAKS for c in land):
            tile.base = "Mountain"
            continue
        tile.base = land_base(tile, elev, cover, pct, land)
        if rugged >= HILL_SHARE and tile.base in FEATURE_ON["Hill"]:
            tile.features.append("Hill")
        if tile.national:
            mean = lambda k: sum(pct[k][c] for c in tile.national) / len(tile.national)
            if mean("wetland") >= MARSH_PCT and "Hill" not in tile.features:
                tile.base = "Grassland"
                tile.features.append("Marsh")
            elif mean("forest") >= FOREST_PCT and tile.base in FEATURE_ON["Forest"]:
                tile.features.append("Forest")


def water_terrain(tile: Tile, tiles: list[Tile], ring: list[int], water: list[int], elev: list[int]) -> str:
    """Lakes where most of its water hexes are lake; else Coast next to land or on the shelf (mean depth above
    COAST_DEPTH_M, the fine map's own coast rule), Ocean beyond."""
    wet = [c for c in tile.cells if water[c] != LAND] or tile.cells
    if not wet:
        return "Ocean"
    if sum(water[c] == LAKE for c in wet) * 2 > len(wet):
        return "Lakes"
    if any(tiles[n].is_land for n in ring) or sum(elev[c] for c in wet) / len(wet) >= COAST_DEPTH_M:
        return "Coast"
    return "Ocean"


def land_base(tile: Tile, elev: list[int], cover: list[int], pct: dict, land: list[int]) -> str:
    """Snow or Desert where ice or bare ground is the commonest cover of its own land; Tundra high up; Grassland where
    meadows, pastures and wetlands outweigh crops and scrub; Plains otherwise, and on land with no land cover (abroad)."""
    if tile.national:
        commonest = Counter(cover[c] for c in tile.national).most_common(1)[0][0]
        if commonest == COVER_ICE:
            return "Snow"
        if commonest == COVER_BARREN:
            return "Desert"
    if sum(elev[c] for c in land) / len(land) >= TUNDRA_ELEV_M:
        return "Tundra"
    if tile.national:
        share = lambda keys: sum(pct[k][c] for k in keys for c in tile.national)
        if share(("pasture", "grass", "wetland")) > share(("crop", "shrub")):
            return "Grassland"
    return "Plains"


# --- rivers -------------------------------------------------------------------------------------------------------------


def river_edges(grid: Grid, tiles: list[Tile], rivers: list[list[tuple[float, float]]]) -> int:
    """Lay each river (a polyline in map km) on tile edges: every point snaps to the nearest corner of its tile, and
    consecutive corners are joined by the shortest run of edges. Only edges between two land tiles carry a river.
    Returns the number of river edges."""
    edges_at: dict[tuple, list[tuple[tuple, int, int]]] = {}  # corner → (other corner, tile, clock)
    for t in range(len(tiles)):
        for clock, a, b in grid.edges(t):
            edges_at.setdefault(a, []).append((b, t, clock))
            edges_at.setdefault(b, []).append((a, t, clock))
    for line in rivers:
        path = []
        for x, y in densify(line, grid.radius / 3):
            t = grid.locate(x, y)
            if t < 0:
                continue
            corner = min(grid.corners(t), key=lambda k: math.dist(grid.corner_xy(k), (x, y)))
            if not path:
                path.append(corner)
            elif corner != path[-1]:
                path += corner_path(path[-1], corner, edges_at)[1:]
        for a, b in zip(path, path[1:]):
            for other, t, clock in edges_at[a]:
                if other == b:
                    n = grid.neighbours(t).get(clock)
                    if n is not None and tiles[t].is_land and tiles[n].is_land:
                        tiles[t].rivers.add(clock)
                        tiles[n].rivers.add(OPPOSITE[clock])
    return sum(len(t.rivers) for t in tiles) // 2


def densify(line: list[tuple[float, float]], step: float) -> list[tuple[float, float]]:
    out = [line[0]]
    for (xa, ya), (xb, yb) in zip(line, line[1:]):
        n = max(1, math.ceil(math.dist((xa, ya), (xb, yb)) / step))
        out += [(xa + (xb - xa) * k / n, ya + (yb - ya) * k / n) for k in range(1, n + 1)]
    return out


def corner_path(start: tuple, goal: tuple, edges_at: dict) -> list[tuple]:
    """Fewest edges from corner `start` to corner `goal` (breadth first)."""
    came = {start: None}
    queue = deque([start])
    while queue:
        k = queue.popleft()
        if k == goal:
            break
        for other, _, _ in edges_at.get(k, ()):
            if other not in came:
                came[other] = k
                queue.append(other)
    path, k = [], goal
    while k is not None:
        path.append(k)
        k = came[k]
    return path[::-1]


# --- resources -----------------------------------------------------------------------------------------------------------


def fits(resource: str, tile: Tile) -> bool:
    """The ruleset lets `resource` stand on the tile (TileNormalizer would keep it), and the tile has none yet."""
    return tile.resource is None and tile.wonder is None and bool(RESOURCES[resource][1] & tile.terrains())


def place_first(resource: str, tiles: list[Tile], candidates) -> int:
    """Put `resource` on the first candidate tile where it fits and return it; -1 if none."""
    for t in candidates:
        if fits(resource, tiles[t]):
            tiles[t].resource = resource
            return t
    return -1


def place_at(resource: str, grid: Grid, tiles: list[Tile], x: float, y: float, rings: int = 1) -> int:
    """A resource found at a point: on its tile, or on the nearest tile within `rings` rings where it fits; -1 if
    none."""
    t = grid.locate(x, y)
    if t < 0:
        return -1
    near, frontier = {t}, [t]
    for _ in range(rings):
        frontier = [n for c in frontier for n in grid.ring(c) if n not in near]
        near.update(frontier)
    nearest = sorted(near, key=lambda c: (c != t, math.dist(grid.center(c), (x, y)), c))
    return place_first(resource, tiles, nearest)


def place_in(resource: str, grid: Grid, tiles: list[Tile], weight: dict[int, int]) -> int:
    """A resource of an area (tile → how many of the area's fine hexes it holds): on the tile with most of the area
    where it fits; a sea resource on the coast tile touching most of the area. -1 if none."""
    sea = Counter()
    for t, w in weight.items():
        for n in grid.ring(t):
            if not tiles[n].is_land and n not in weight:
                sea[n] += w
    by_weight = lambda cands: sorted(cands, key=lambda t: (-cands[t], t))
    return place_first(resource, tiles, [*by_weight(weight), *by_weight(sea)])


# --- the map file and the mod ---------------------------------------------------------------------------------------------


def position_json(position: tuple[int, int]) -> dict:
    return {"x": position[0], "y": position[1]}


def tile_json(position: tuple[int, int], tile: Tile) -> dict:
    out = {"position": position_json(position), "baseTerrain": tile.base}
    if tile.features:
        out["terrainFeatures"] = list(tile.features)
    if tile.wonder:
        out["naturalWonder"] = tile.wonder
    if tile.resource:
        out["resource"] = tile.resource
        amount = RESOURCES[tile.resource][2]
        if amount:
            out["resourceAmount"] = amount
    for clock, flag in RIVER_FLAG.items():
        if clock in tile.rivers:
            out[flag] = True
    return out


def tile_map(grid: Grid, tiles: list[Tile], name: str, description: str, starts: list[tuple[int, str, str]],
             mod: str | None = None) -> dict:
    """The TileMap JSON: a rectangular custom map for the base ruleset; starts are (tile, nation, usage). A map that
    uses MOD_RESOURCES names its `mod` in mapParameters.mods: choosing the map in a new game turns the mod on
    (MapFileSelectTable.onFileSelectBoxChange), and the map editor loads it with the mod's ruleset."""
    return {
        "mapParameters": {"name": name, "type": "Empty", "shape": "Rectangular", "mapSize": grid.map_size(),
                          "baseRuleset": BASE_RULESET, "mods": [mod] if mod else [], "worldWrap": False,
                          "createdWithVersion": f"{UNCIV_RELEASE} (exported by the spainciv pipeline)"},
        "tileList": [tile_json(grid.positions[i], tile) for i, tile in enumerate(tiles)],
        "startingLocations": [{"position": position_json(grid.positions[t]), "nation": nation, "usage": usage}
                              for t, nation, usage in starts],
        "description": description,
    }


def without_mod(map_json: dict) -> dict:
    """The same map for the base ruleset alone: no mod in its parameters and no mod resource on its tiles (for the bare
    map file, which works without installing the mod)."""
    tiles = [{k: v for k, v in t.items() if k not in ("resource", "resourceAmount")} if t.get("resource") in MOD_RESOURCES
             else t for t in map_json["tileList"]]
    return map_json | {"mapParameters": map_json["mapParameters"] | {"mods": []}, "tileList": tiles}


def tiles_from_map(map_json: dict) -> list[Tile]:
    """The tiles of a TileMap JSON, in its order (the inverse of tile_json, without the fine hexes)."""
    return [Tile(base=t["baseTerrain"], features=list(t.get("terrainFeatures", [])), resource=t.get("resource"),
                 wonder=t.get("naturalWonder"), rivers={c for c, flag in RIVER_FLAG.items() if t.get(flag)})
            for t in map_json["tileList"]]


def encode(map_json: dict) -> bytes:
    """The map file as Unciv saves it: gzip, then base64 (FileConversions.zip). Deterministic (no gzip timestamp)."""
    raw = json.dumps(map_json, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(gzip.compress(raw, compresslevel=9, mtime=0))


def decode(data: bytes) -> dict:
    """A map file back to its JSON: gzip+base64 or plain JSON, as FileConversions.readJson accepts both."""
    try:
        raw = gzip.decompress(base64.b64decode(data, validate=True))
    except (ValueError, OSError):
        raw = data
    return json.loads(raw)


def mod_options(author: str, url: str) -> dict:
    """jsons/ModOptions.json of a mod that adds maps and resources to the base ruleset, an extension mod (ModOptions.kt
    fields; the mod manager fills in the rest from GitHub when the mod is installed from there)."""
    return {"isBaseRuleset": False, "author": author, "modUrl": url, "topics": ["unciv-mod-maps"], "uniques": []}


def tile_resources_json() -> list[dict]:
    """jsons/TileResources.json of the mod: MOD_RESOURCES. Unciv merges an extension mod's resources into the base
    ruleset's (Ruleset.kt: add), and draws each with the image ResourceIcons/<name> of the mod's atlas."""
    return [{"name": name, **fields} for name, fields in MOD_RESOURCES.items()]


ICON_PX = 100  # the size of Unciv's own resource icons (android/assets/Icons.atlas: ResourceIcons/*)


def atlas(page: str, size: tuple[int, int], regions: dict[str, tuple[int, int]]) -> str:
    """A libGDX texture atlas in the layout Unciv's own atlases use (android/assets/Icons.atlas): one page and the
    ICON_PX square regions at the given positions. Desktop Unciv repacks a mod's Images/ itself (ImagePacker.kt), but
    Android only reads the atlas the mod ships (ImageGetter.loadModAtlases, through Atlases.json)."""
    lines = [page, f"size: {size[0]}, {size[1]}", "format: RGBA8888", "filter: MipMapLinearLinear, Linear", "repeat: none"]
    for name, (x, y) in regions.items():
        lines += [name, "  rotate: false", f"  xy: {x}, {y}", f"  size: {ICON_PX}, {ICON_PX}",
                  f"  orig: {ICON_PX}, {ICON_PX}", "  offset: 0, 0", "  index: -1"]
    return "\n".join(lines) + "\n"


def preview_png(grid: Grid, tiles: list[Tile], width_px: int = 640) -> bytes:
    """A picture of the map in Unciv's own terrain colours: the mod manager's preview."""
    r = grid.radius
    xs = [grid.center(i)[0] for i in range(len(tiles))]
    ys = [grid.center(i)[1] for i in range(len(tiles))]
    x0, y0 = min(xs) - r, min(ys) - r * SQRT3 / 2
    scale = width_px / (max(xs) + r - x0)
    height_px = math.ceil((max(ys) + r * SQRT3 / 2 - y0) * scale)

    def px(corner: tuple[int, int]) -> tuple[float, float]:
        x, y = grid.corner_xy(corner)
        return (x - x0) * scale, (y - y0) * scale

    canvas = Canvas(width_px, height_px, RGB["Ocean"])
    for i, tile in enumerate(tiles):
        top = tile.features[-1] if tile.features else tile.base
        colour = (255, 215, 0) if tile.wonder else RGB[top]
        canvas.fill([[px(k) for k in grid.corners(i)]], colour)
    for i, tile in enumerate(tiles):
        for clock, a, b in grid.edges(i):
            if clock in tile.rivers and clock in RIVER_FLAG:  # each river edge once, by the tile that owns it
                canvas.stroke([px(a), px(b)], 1.6, RGB["Coast"])
    return canvas.png()
