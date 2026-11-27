"""The Unciv export: the hex geometry and file format (pipeline/build/unciv.py), Spain's map (pipeline/build/spain_unciv.py,
sites/es/data/unciv.json) and its mod, downloads and page (pipeline/play.py)."""

import base64
import gzip
import io
import json
import math
import re
import tempfile
import unittest
import zipfile
from html import escape
from pathlib import Path
from unittest import mock

from pipeline import countries, play, site
from pipeline.core.lang import Text, pick
from pipeline.build import spain_unciv, unciv
from pipeline.build import spain_unciv_fire as fire
from pipeline.build.world import COAST, LAKE, LAND, OCEAN
from pipeline.core.hexgrid import HexGrid

ES = countries.COUNTRIES["es"]


def built() -> dict:
    """unciv.json as built, its texts in Spanish and English."""
    return play.load(ES)


def grid_of(summary: dict) -> unciv.Grid:
    g = summary["grid"]
    return unciv.Grid(g["spacing"], g["width"], g["height"], tuple(g["centre"]))


class HexGeometryTest(unittest.TestCase):
    """Unciv's hex coordinates (core/src/com/unciv/logic/map/HexMath.kt, TileMap.kt) and the tiles laid over the map."""

    def setUp(self):
        self.grid = unciv.Grid(25.0, 6, 5, (100.0, 100.0))

    def test_column_row_to_hex_coordinates(self):
        # getTileCoordsFromColumnRow, and the neighbours of the origin in TileMap's diagram.
        self.assertEqual(unciv.hex_coord(0, 0), (0, 0))
        self.assertEqual(unciv.hex_coord(0, 1), (1, 1))  # above
        self.assertEqual(unciv.hex_coord(1, 0), (0, 1))  # up right: odd columns sit half a row higher
        self.assertEqual(unciv.hex_coord(-1, 0), (1, 0))  # up left
        self.assertEqual(unciv.hex_coord(1, -1), (-1, 0))  # down right
        self.assertEqual(unciv.hex_coord(-1, -1), (0, -1))  # down left

    def test_tiles_in_the_rectangular_constructor_order(self):
        # Even widths run -w/2 … w/2 - 1, columns outside and rows inside (TileMap(width, height)).
        self.assertEqual(len(self.grid.tiles), 30)
        self.assertEqual(self.grid.tiles[0], (-3, -2))
        self.assertEqual(self.grid.tiles[-1], (2, 2))
        self.assertEqual(len(set(self.grid.positions)), 30)
        # Odd sizes are centred: w=5 → -2..2, h=5 → -2..2.
        odd = unciv.Grid(25.0, 5, 5, (0, 0)).tiles
        self.assertEqual((odd[0], odd[-1]), ((-2, -2), (2, 2)))

    def test_neighbours_sit_where_their_clock_says(self):
        g = self.grid
        i = g.tiles.index((0, 0))
        x, y = g.center(i)
        for clock, j in g.neighbours(i).items():
            nx, ny = g.center(j)
            self.assertAlmostEqual(math.dist((x, y), (nx, ny)), g.spacing)
            angle = math.degrees(math.atan2(y - ny, nx - x)) % 360  # map y runs down
            self.assertAlmostEqual(angle, (90 - 30 * clock) % 360, places=6)
        self.assertEqual(len(g.neighbours(i)), 6)

    def test_locate_finds_each_centre_and_nothing_off_the_map(self):
        g = self.grid
        for i in range(len(g.tiles)):
            self.assertEqual(g.locate(*g.center(i)), i)
        self.assertEqual(g.locate(-500, -500), -1)

    def test_neighbouring_tiles_share_the_corners_of_their_edge(self):
        g = self.grid
        for i in range(len(g.tiles)):
            k = g.corners(i)
            for e, clock in enumerate(unciv.EDGE_CLOCK):
                j = g.neighbours(i).get(clock)
                if j is not None:
                    self.assertEqual({k[e], k[(e + 1) % 6]} & set(g.corners(j)), {k[e], k[(e + 1) % 6]})
                    for key in (k[e], k[(e + 1) % 6]):
                        self.assertAlmostEqual(math.dist(g.corner_xy(key), g.center(i)), g.radius)

    def test_map_size_is_a_custom_rectangle(self):
        size = unciv.Grid(25.0, 80, 52, (0, 0)).map_size()
        self.assertEqual(size, {"name": "Custom", "radius": 37, "width": 80, "height": 52})


def fine_world(cols=24, rows=20, radius=10 / math.sqrt(3)) -> dict:
    """A small world.json: all ocean, deep."""
    n = cols * rows
    return {"grid": {"radius": radius, "cols": cols, "rows": rows}, "owner": [-1] * n, "water": [OCEAN] * n,
            "elev": [-3000] * n, "relief": [0] * n, "cover": [0] * n,
            "pct": {k: [0] * n for k in ("forest", "crop", "pasture", "grass", "shrub", "wetland", "developed")},
            "width": cols * 10.0, "height": rows * 1.5 * radius}


def set_land(world, cells, owner=0, **pct):
    for c in cells:
        world["water"][c], world["owner"][c], world["elev"][c] = LAND, owner, 600
        for k, v in pct.items():
            world["pct"][k][c] = v
        if owner >= 0:
            world["cover"][c] = 7


class ResampleAndTerrainTest(unittest.TestCase):
    def setUp(self):
        self.world = fine_world()
        self.fine = HexGrid(**self.world["grid"])
        self.grid = unciv.Grid.covering(self.fine, 25.0)

    def terrain(self):
        tiles = unciv.resample(self.world, self.grid)
        unciv.terrain(self.world, self.grid, tiles)
        return tiles

    def middle(self):
        return self.grid.locate(self.world["width"] / 2, self.world["height"] / 2)

    def test_every_fine_hex_falls_in_one_tile(self):
        tiles = unciv.resample(self.world, self.grid)
        cells = [c for t in tiles for c in t.cells]
        self.assertEqual(sorted(cells), list(range(self.fine.size)))

    def test_land_needs_half_of_the_tile(self):
        # A tile next to a land tile, with the fine hexes nearest to it on land (one landmass, so no island rule).
        a = self.middle()
        b = self.grid.ring(a)[0]
        tiles = unciv.resample(self.world, self.grid)
        set_land(self.world, tiles[a].cells, crop=80)
        near = sorted(tiles[b].cells, key=lambda c: math.dist(self.fine.center(*self.fine.col_row(c)), self.grid.center(a)))
        set_land(self.world, near[: math.ceil(len(near) / 2) - 1], crop=80)
        self.assertFalse(unciv.resample(self.world, self.grid)[b].is_land)
        set_land(self.world, near[: math.ceil(len(near) / 2)], crop=80)
        self.assertTrue(unciv.resample(self.world, self.grid)[b].is_land)

    def test_an_island_keeps_a_tile(self):
        t = self.middle()
        one = unciv.resample(self.world, self.grid)[t].cells[0]
        set_land(self.world, [one])
        tiles = unciv.resample(self.world, self.grid)
        self.assertEqual([i for i, tile in enumerate(tiles) if tile.is_land], [t])

    def whole_tile(self, **pct):
        t = self.middle()
        cells = unciv.resample(self.world, self.grid)[t].cells
        set_land(self.world, cells, **pct)
        return t, cells

    def test_plains_grassland_forest_marsh(self):
        t, _ = self.whole_tile(crop=60, shrub=10, pasture=20)
        self.assertEqual((self.terrain()[t].base, self.terrain()[t].features), ("Plains", []))
        t, _ = self.whole_tile(crop=10, shrub=10, pasture=40, grass=10)
        self.assertEqual(self.terrain()[t].base, "Grassland")
        t, _ = self.whole_tile(forest=unciv.FOREST_PCT)
        self.assertEqual(self.terrain()[t].features, ["Forest"])
        t, _ = self.whole_tile(forest=0, wetland=unciv.MARSH_PCT)
        self.assertEqual((self.terrain()[t].base, self.terrain()[t].features), ("Grassland", ["Marsh"]))

    def test_relief(self):
        t, cells = self.whole_tile(crop=80)
        for c in cells[: math.ceil(unciv.HILL_SHARE * len(cells))]:
            self.world["relief"][c] = 2
        self.assertEqual(self.terrain()[t].features, ["Hill"])
        for c in cells[: math.ceil(unciv.MOUNTAIN_SHARE * len(cells))]:
            self.world["relief"][c] = 2
        self.assertEqual((self.terrain()[t].base, self.terrain()[t].features), ("Mountain", []))
        for c in cells:
            self.world["relief"][c] = 0
        self.world["relief"][cells[0]] = 3  # one peak makes a mountain
        self.assertEqual(self.terrain()[t].base, "Mountain")

    def test_tundra_desert_snow(self):
        t, cells = self.whole_tile(crop=80)
        for c in cells:
            self.world["elev"][c] = unciv.TUNDRA_ELEV_M
        self.assertEqual(self.terrain()[t].base, "Tundra")
        for c in cells:
            self.world["elev"][c] = 600
            self.world["cover"][c] = unciv.COVER_BARREN
        self.assertEqual(self.terrain()[t].base, "Desert")
        for c in cells:
            self.world["cover"][c] = unciv.COVER_ICE
        self.assertEqual(self.terrain()[t].base, "Snow")

    def test_foreign_land_is_plains_with_real_relief(self):
        t = self.middle()
        cells = unciv.resample(self.world, self.grid)[t].cells
        set_land(self.world, cells, owner=-2)
        for c in cells:
            self.world["relief"][c] = 2
        tile = self.terrain()[t]
        self.assertEqual((tile.base, tile.national), ("Mountain", []))
        for c in cells:
            self.world["relief"][c] = 0
        self.assertEqual((self.terrain()[t].base, self.terrain()[t].features), ("Plains", []))

    def test_coast_ocean_and_lakes(self):
        t, _ = self.whole_tile(crop=80)
        tiles = self.terrain()
        for n in self.grid.ring(t):
            self.assertEqual(tiles[n].base, "Coast")  # next to land
        far = self.grid.locate(5, 5)
        self.assertEqual(tiles[far].base, "Ocean")
        for c in tiles[far].cells:
            self.world["elev"][c] = -100  # the shelf
        self.assertEqual(self.terrain()[far].base, "Coast")
        for c in tiles[far].cells:
            self.world["water"][c] = LAKE
        self.assertEqual(self.terrain()[far].base, "Lakes")
        self.assertNotEqual(COAST, LAKE)


class RiverTest(unittest.TestCase):
    def setUp(self):
        self.grid = unciv.Grid(25.0, 10, 8, (125.0, 100.0))
        self.tiles = [unciv.Tile(base="Plains") for _ in self.grid.tiles]

    def test_a_river_runs_along_connected_edges_owned_by_the_right_tile(self):
        n = unciv.river_edges(self.grid, self.tiles, [[(20.0, 100.0), (230.0, 100.0)]])
        self.assertGreater(n, 5)
        corners = {}
        for t, tile in enumerate(self.tiles):
            k = self.grid.corners(t)
            for e, clock in enumerate(unciv.EDGE_CLOCK):
                if clock in tile.rivers:
                    j = self.grid.neighbours(t)[clock]
                    self.assertIn(unciv.OPPOSITE[clock], self.tiles[j].rivers)
                    for key in (k[e], k[(e + 1) % 6]):
                        corners[key] = corners.get(key, 0) + 1
        # A path: two corners end it, every other corner joins two edges (each edge counted from both tiles).
        ends = [key for key, c in corners.items() if c == 2]
        self.assertEqual(len(ends), 2)
        self.assertTrue(all(c == 4 for key, c in corners.items() if key not in ends))
        json_tiles = [unciv.tile_json(self.grid.positions[i], t) for i, t in enumerate(self.tiles)]
        flags = sum(sum(1 for f in unciv.RIVER_FLAG.values() if t.get(f)) for t in json_tiles)
        self.assertEqual(flags, n)  # each edge is stored once, on the tile that owns it

    def test_no_river_between_water_tiles(self):
        for t in self.tiles:
            t.base = "Coast"
        self.assertEqual(unciv.river_edges(self.grid, self.tiles, [[(20.0, 100.0), (230.0, 100.0)]]), 0)


class ResourceTest(unittest.TestCase):
    def setUp(self):
        self.grid = unciv.Grid(25.0, 6, 5, (100.0, 100.0))
        self.tiles = [unciv.Tile(base="Plains") for _ in self.grid.tiles]
        self.mid = self.grid.locate(100.0, 100.0)

    def test_the_ruleset_decides_where_a_resource_stands(self):
        self.assertTrue(unciv.fits("Wine", unciv.Tile(base="Plains")))
        self.assertFalse(unciv.fits("Cattle", unciv.Tile(base="Plains")))
        self.assertTrue(unciv.fits("Sheep", unciv.Tile(base="Plains", features=["Hill"])))
        self.assertTrue(unciv.fits("Fish", unciv.Tile(base="Coast")))
        self.assertFalse(unciv.fits("Wine", unciv.Tile(base="Plains", resource="Salt")))
        self.assertFalse(unciv.fits("Wine", unciv.Tile(base="Mountain", wonder="Rock of Gibraltar")))

    def test_a_point_goes_to_its_tile_or_the_nearest_neighbour_that_fits(self):
        x, y = self.grid.center(self.mid)
        self.assertEqual(unciv.place_at("Wine", self.grid, self.tiles, x, y), self.mid)
        self.assertNotIn(unciv.place_at("Salt", self.grid, self.tiles, x, y), (-1, self.mid))  # the tile is taken
        self.assertEqual(unciv.place_at("Cattle", self.grid, self.tiles, x, y), -1)  # no grassland near
        self.assertEqual(unciv.place_at("Wine", self.grid, self.tiles, -900, -900), -1)

    def test_two_rings_reach_a_tile_two_steps_away(self):
        # A forest two tiles from the point: uranium finds it with two rings, not with one.
        x, y = self.grid.center(self.mid)
        ring1 = set(self.grid.ring(self.mid))
        far = next(n for c in ring1 for n in self.grid.ring(c) if n != self.mid and n not in ring1)
        self.tiles[far].features = ["Forest"]
        self.assertEqual(unciv.place_at("Uranium", self.grid, self.tiles, x, y), -1)
        self.assertEqual(unciv.place_at("Uranium", self.grid, self.tiles, x, y, rings=2), far)
        self.assertEqual(spain_unciv.RINGS, {"Uranium": 2, "Aluminum": 2})

    def test_an_area_takes_its_largest_tile_and_a_sea_resource_its_coast(self):
        ring = self.grid.ring(self.mid)
        weight = {self.mid: 3, ring[0]: 5}
        self.assertEqual(unciv.place_in("Wine", self.grid, self.tiles, weight), ring[0])
        for n in ring[1:]:
            self.tiles[n].base = "Coast"
        sea = unciv.place_in("Fish", self.grid, self.tiles, {self.mid: 4})
        self.assertIn(sea, ring[1:])
        self.assertEqual(self.tiles[sea].resource, "Fish")


class FileFormatTest(unittest.TestCase):
    def map_json(self):
        grid = unciv.Grid(25.0, 4, 3, (50.0, 40.0))
        tiles = [unciv.Tile(base="Ocean") for _ in grid.tiles]
        tiles[0] = unciv.Tile(base="Plains", features=["Hill", "Forest"], resource="Iron", rivers={4, 6})
        tiles[1] = unciv.Tile(base="Mountain", wonder="Rock of Gibraltar")
        return unciv.tile_map(grid, tiles, "Prueba ñ", "descripción", [(0, "Spain", "Human"), (1, unciv.SPECTATOR, "Player")])

    def test_tile_fields(self):
        doc = self.map_json()
        t0, t1 = doc["tileList"][:2]
        self.assertEqual(t0["terrainFeatures"], ["Hill", "Forest"])
        self.assertEqual((t0["resource"], t0["resourceAmount"]), ("Iron", 6))
        self.assertTrue(t0["hasBottomRightRiver"] and t0["hasBottomRiver"])
        self.assertNotIn("hasBottomLeftRiver", t0)
        self.assertEqual((t1["naturalWonder"], t1["baseTerrain"]), ("Rock of Gibraltar", "Mountain"))
        p = doc["mapParameters"]
        self.assertEqual((p["shape"], p["baseRuleset"], p["mapSize"]["name"]), ("Rectangular", unciv.BASE_RULESET, "Custom"))
        grid = unciv.Grid(25.0, 4, 3, (50.0, 40.0))
        self.assertEqual(doc["startingLocations"][1], {"position": dict(zip("xy", grid.positions[1])), "nation": "Spectator", "usage": "Player"})

    def test_gzip_base64_round_trip_and_plain_json(self):
        doc = self.map_json()
        data = unciv.encode(doc)
        self.assertEqual(data, unciv.encode(doc))  # deterministic
        self.assertEqual(json.loads(gzip.decompress(base64.b64decode(data))), doc)  # FileConversions.unzip
        self.assertEqual(unciv.decode(data), doc)
        self.assertEqual(unciv.decode(json.dumps(doc).encode()), doc)

    def test_tiles_from_map_inverts_tile_json(self):
        doc = self.map_json()
        back = unciv.tiles_from_map(doc)
        self.assertEqual((back[0].base, back[0].features, back[0].resource, back[0].rivers), ("Plains", ["Hill", "Forest"], "Iron", {4, 6}))
        self.assertEqual(back[1].wonder, "Rock of Gibraltar")


class SpainMapTest(unittest.TestCase):
    """sites/es/data/unciv.json as built: playable and within the base ruleset."""

    @classmethod
    def setUpClass(cls):
        cls.doc = built()
        cls.summary, cls.map = cls.doc["summary"], cls.doc["map"]
        cls.grid = grid_of(cls.summary)
        cls.tiles = unciv.tiles_from_map(cls.map)

    def test_size(self):
        self.assertEqual(self.summary["tile_km"], spain_unciv.TILE_KM)
        self.assertEqual(len(self.map["tileList"]), self.grid.width * self.grid.height)
        self.assertEqual([(t["position"]["x"], t["position"]["y"]) for t in self.map["tileList"]], self.grid.positions)
        self.assertLessEqual(len(self.map["tileList"]), 87 * 57)  # no larger than Unciv's Huge preset
        self.assertGreater(self.summary["national_land_tiles"], 800)

    def test_every_terrain_feature_and_resource_is_allowed_where_it_stands(self):
        known = {"Ocean", "Coast", "Lakes", "Grassland", "Plains", "Tundra", "Desert", "Snow", "Mountain"}
        for t in self.tiles:
            self.assertIn(t.base, known)
            for f in t.features:
                self.assertIn(t.base, unciv.FEATURE_ON[f])
            if t.resource:
                self.assertTrue(unciv.RESOURCES[t.resource][1] & t.terrains(), (t.resource, t.base, t.features))
        counted = {r: sum(t.resource == r for t in self.tiles) for r in unciv.RESOURCES}
        self.assertEqual({r: n for r, n in counted.items() if n}, self.summary["resources"])

    def test_the_rock_of_gibraltar(self):
        rock = [t for t in self.tiles if t.wonder]
        self.assertEqual(len(rock), 1)
        self.assertEqual((rock[0].wonder, rock[0].base, rock[0].features, rock[0].resource), ("Rock of Gibraltar", "Mountain", [], None))

    def test_rivers_only_between_land_tiles(self):
        self.assertGreater(self.summary["river_edges"], 100)
        for i, t in enumerate(self.tiles):
            for clock in t.rivers:
                self.assertTrue(t.is_land and self.tiles[self.grid.neighbours(i)[clock]].is_land)

    def test_spain_starts_in_madrid_and_the_others_far_apart(self):
        starts = self.map["startingLocations"]
        self.assertEqual((starts[0]["nation"], starts[0]["usage"]), ("Spain", "Human"))
        self.assertEqual(self.summary["starts"][0]["city"], "Madrid")
        self.assertTrue(all(s["nation"] == unciv.SPECTATOR for s in starts[1:]))
        self.assertEqual(len(starts), spain_unciv.STARTS)
        by_pos = {p: i for i, p in enumerate(self.grid.positions)}
        idx = [by_pos[(s["position"]["x"], s["position"]["y"])] for s in starts]
        for i in idx:
            self.assertTrue(self.tiles[i].passable_land)
        for a in idx:
            for b in idx:
                if a != b:
                    self.assertGreaterEqual(spain_unciv.distance(self.grid, a, b), spain_unciv.START_GAP)

    def test_islands_are_kept(self):
        # Balearics and Canaries: land tiles in their parts of the frame (the Canaries in their inset box).
        world = json.loads((ES.web_data_dir / "world.json").read_text(encoding="utf-8"))
        fine = HexGrid(**world["grid"])
        islands = {"Mallorca": (2.9, 39.6), "Tenerife": (-16.6, 28.3), "El Hierro": (-18.0, 27.75)}
        proj = ES.map_projection(**{k: world["country"]["projection"][k] for k in ("min_x", "max_y", "margin")})
        for name, lonlat in islands.items():
            x, y = proj(*lonlat)
            near = [self.grid.locate(x, y), *self.grid.ring(self.grid.locate(x, y))]
            self.assertTrue(any(self.tiles[t].is_land for t in near), name)
        self.assertTrue(fine.size)


class DesignationsTest(unittest.TestCase):
    def test_a_named_designation_missing_from_the_lens_fails(self):
        with self.assertRaises(RuntimeError):
            spain_unciv.designation_resources(["Rioja (DOP)"], {"Rioja (DOP)": "Vinos"})

    def test_families_and_names(self):
        names = sorted(spain_unciv.DESIGNATIONS) + ["Rioja (DOP)", "Queso Manchego (DOP)"]
        got = spain_unciv.designation_resources(names, {"Rioja (DOP)": "Vinos", "Queso Manchego (DOP)": "Quesos y Mantequillas"})
        self.assertEqual(got[names.index("Rioja (DOP)")], "Wine")
        self.assertNotIn(names.index("Queso Manchego (DOP)"), got)  # Unciv has no cheese
        self.assertEqual(got[names.index("Ternasco de Aragón (IGP)")], "Sheep")

    def test_every_resource_has_a_place_in_the_order_and_texts_in_both_languages(self):
        used = set(spain_unciv.DESIGNATIONS.values()) | set(spain_unciv.FAMILIES.values()) | set(spain_unciv.SUBSTANCES.values()) \
            | set(spain_unciv.MINE_TYPES.values()) | set(spain_unciv.DEPOSITS.values()) | {"Horses"}
        self.assertEqual(used, set(spain_unciv.ORDER))
        self.assertTrue(used <= set(unciv.RESOURCES))
        texts = json.loads((play.TEMPLATES / "unciv-resources.json").read_text(encoding="utf-8"))
        for lang in ("es", "en"):
            self.assertEqual(set(texts[lang]), set(unciv.RESOURCES), lang)

    def test_the_iberian_ham_dops_give_the_mod_pig(self):
        pig = {n for n, r in spain_unciv.DESIGNATIONS.items() if r == "Cerdo ibérico"}
        self.assertEqual(pig, {"Jabugo (DOP)", "Guijuelo (DOP)", "Dehesa de Extremadura (DOP)", "Los Pedroches (DOP)"})
        self.assertIn("Cerdo ibérico", unciv.MOD_RESOURCES)


class HorseTest(unittest.TestCase):
    def test_only_comarcas_dense_enough(self):
        # Two comarcas of two municipalities' hexes each: A with 10 head on 2 hexes, B with 1 head on 2 hexes.
        world = fine_world(cols=8, rows=6)
        world["counties"] = [{"geoid": "01001"}, {"geoid": "01002"}]
        world["county"] = [-1] * len(world["owner"])
        world["county"][:2], world["county"][2:4] = [0, 0], [1, 1]
        census = {"comarca_of": {"01001": "0101", "01002": "0102"},
                  "comarcas": {"0101": {"name": "A", "heads": 10}, "0102": {"name": "B", "heads": 1}}}
        fine = HexGrid(**world["grid"])
        grid = unciv.Grid.covering(fine, 25.0)
        areas = spain_unciv.horse_areas(world, grid, fine, census)  # Spain: 11 head on 4 hexes, 2.75 a hex
        self.assertEqual(list(areas), [])  # A has 5 a hex: 1.8 times Spain, under HORSE_DENSITY
        with mock.patch.object(spain_unciv, "HORSE_DENSITY", 1.5):  # A has 5 a hex, 1.8 times Spain
            areas = spain_unciv.horse_areas(world, grid, fine, census)
        self.assertEqual(list(areas), ["0101"])
        self.assertEqual(sum(areas["0101"].values()), 2)


class ModResourceTest(unittest.TestCase):
    def test_tile_resources_json(self):
        (pig,) = unciv.tile_resources_json()
        self.assertEqual(pig["name"], "Cerdo ibérico")
        self.assertEqual((pig["resourceType"], pig["improvement"]), ("Luxury", "Pasture"))
        self.assertIn("Doesn't generate naturally", pig["uniques"])

    def test_atlas_in_unciv_layout(self):
        text = unciv.atlas("game.png", (128, 128), {"ResourceIcons/Cerdo ibérico": (0, 0)})
        self.assertEqual(text.splitlines()[:6], ["game.png", "size: 128, 128", "format: RGBA8888",
                                                 "filter: MipMapLinearLinear, Linear", "repeat: none", "ResourceIcons/Cerdo ibérico"])
        self.assertIn("  size: 100, 100", text)

    def test_the_icon_is_rgba_with_a_transparent_corner(self):
        from pipeline.core import png
        px = play.pig_icon()
        self.assertEqual(len(px), 4 * unciv.ICON_PX ** 2)
        self.assertEqual(px[3], 0)  # top-left corner transparent
        middle = 4 * (unciv.ICON_PX * 52 + 46)
        self.assertEqual(px[middle + 3], 255)  # the pig's body opaque
        w, h, rows = png.decode(png.encode(unciv.ICON_PX, unciv.ICON_PX, px, channels=4))
        self.assertEqual((w, h), (unciv.ICON_PX, unciv.ICON_PX))
        self.assertIsNone(rows[0][0])  # decode reads alpha 0 as transparent

    def test_the_map_names_its_mod_and_the_bare_map_needs_none(self):
        doc = built()["map"]
        self.assertEqual(doc["mapParameters"]["mods"], [spain_unciv.MOD_NAME])
        self.assertTrue(any(t.get("resource") == "Cerdo ibérico" for t in doc["tileList"]))
        bare = unciv.without_mod(doc)
        self.assertEqual(bare["mapParameters"]["mods"], [])
        self.assertFalse(any(t.get("resource") in unciv.MOD_RESOURCES for t in bare["tileList"]))
        self.assertEqual(len(bare["tileList"]), len(doc["tileList"]))
        self.assertEqual(doc["mapParameters"]["mods"], [spain_unciv.MOD_NAME])  # the original is untouched


class ModAndPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = play.files(ES)
        cls.doc = built()
        cls.folder = cls.doc["summary"]["mod"]["name"]

    def test_spain_has_the_page_and_downloads_and_the_us_none(self):
        shots = [path for path, _ in play.FIRE_SHOT.values()]
        self.assertEqual(set(self.files), {*play.PAGES.values(), play.MOD_ZIP, play.MAP_FILE, play.PREVIEW, play.SCREENSHOT[0],
                                           *shots})
        self.assertEqual(len(set(shots)), len(play.PAGES))  # one popup per language
        for path in shots:
            self.assertTrue(self.files[path]().startswith(b"\xff\xd8"), path)  # a JPEG
        self.assertEqual(play.files(countries.COUNTRIES["us"]), {})
        self.assertEqual(site.page_config(ES)["play"], play.PAGES["es"])
        self.assertEqual(site.page_config(ES)["texts"]["en"]["play"], play.PAGES["en"])

    def test_the_mod_zip_is_one_folder_unciv_can_install(self):
        z = zipfile.ZipFile(io.BytesIO(self.files[play.MOD_ZIP]()))
        names = z.namelist()
        self.assertEqual({n.split("/")[0] for n in names}, {self.folder})
        inner = {n.split("/", 1)[1] for n in names}
        map_name = self.doc["summary"]["map_name"]
        self.assertEqual(inner, {"jsons/ModOptions.json", "jsons/TileResources.json", "jsons/Events.json",
                                 "jsons/GlobalUniques.json", "jsons/translations/Spanish.properties", f"maps/{map_name}",
                                 "Images/ResourceIcons/Cerdo ibérico.png", "game.png", "game.atlas", "Atlases.json",
                                 "preview.png", "README.md", "LICENSE"})
        read = lambda p: z.read(f"{self.folder}/{p}")
        options = json.loads(read("jsons/ModOptions.json"))
        self.assertEqual((options["isBaseRuleset"], options["topics"]), (False, ["unciv-mod-maps"]))
        self.assertEqual(json.loads(read("jsons/TileResources.json")), unciv.tile_resources_json())
        fire_season = self.doc["summary"]["fire_season"]
        self.assertEqual(json.loads(read("jsons/Events.json")), fire.events_json(fire_season))
        self.assertEqual(json.loads(read("jsons/GlobalUniques.json")), fire.global_uniques_json(fire_season))
        self.assertEqual(read("jsons/translations/Spanish.properties").decode("utf-8"),
                         unciv.properties(fire.translations(fire_season)))
        self.assertEqual(read("Atlases.json").strip(), b"[game]")
        self.assertIn("ResourceIcons/Cerdo ibérico", read("game.atlas").decode("utf-8"))
        self.assertEqual(unciv.decode(read(f"maps/{map_name}")), self.doc["map"])
        self.assertTrue(read("preview.png").startswith(b"\x89PNG"))
        self.assertEqual(self.files[play.MOD_ZIP](), self.files[play.MOD_ZIP]())  # deterministic

    def test_the_readme_is_bilingual(self):
        z = zipfile.ZipFile(io.BytesIO(self.files[play.MOD_ZIP]()))
        text = z.read(f"{self.folder}/README.md").decode("utf-8")
        self.assertIn("## Español", text)
        self.assertIn("## English", text)
        self.assertNotIn("$", text)
        for lang in ("es", "en"):
            names = play.resource_texts(self.doc["summary"], lang)
            for resource, n in self.doc["summary"]["resources"].items():
                self.assertIn(f"| {names[resource][0]} | {n} |", text)

    def test_the_readme_has_the_fire_season_in_both_languages(self):
        z = zipfile.ZipFile(io.BytesIO(self.files[play.MOD_ZIP]()))
        text = z.read(f"{self.folder}/README.md").decode("utf-8")
        f = self.doc["summary"]["fire_season"]
        self.assertIn("### Temporada de incendios", text)
        self.assertIn("### Fire season", text)
        self.assertIn("Convención", text)
        self.assertIn("Convention", text)
        for c in f["classes"]:
            for lang in ("es", "en"):
                self.assertIn(f"| {play.FIRE_CLASSES[lang][c['class']]} | {c['tiles']} |", text)
            self.assertIn(f" | {c['weight']} |", text)
        self.assertIn(f"{f['great_fires']} incendios", text)
        self.assertIn(f"{f['great_fires']} fires", text)
        self.assertIn("EFFIS", z.read(f"{self.folder}/LICENSE").decode("utf-8"))

    def test_the_ai_odds_are_unciv_weights(self):
        """Unciv multiplies a choice's AI weight by 1 + pct/100 (IHasUniques.getWeightForAiDecision)."""
        for pct, odds in ((100, (2, 3)), (50, (3, 5)), (200, (3, 4))):
            with mock.patch.object(fire, "AI_PAY_WEIGHT_PCT", pct):
                f = play.fire_fields(self.doc["summary"], "en")
            self.assertEqual((f["fire_ai"], f["fire_ai_of"]), odds, pct)

    def test_the_readme_links_to_the_page_in_each_language(self):
        z = zipfile.ZipFile(io.BytesIO(self.files[play.MOD_ZIP]()))
        text = z.read(f"{self.folder}/README.md").decode("utf-8")
        spanish, english = text.split("## English")
        self.assertIn(f"https://{ES.site_url}/{play.PAGES['es']}", spanish)
        self.assertIn(f"https://{ES.site_url}/{play.PAGES['en']}", english)

    def test_the_bare_map_is_the_map_without_the_mod(self):
        self.assertEqual(unciv.decode(self.files[play.MAP_FILE]()), unciv.without_mod(self.doc["map"]))

    def test_the_page(self):
        """One page per language, each linking to the other and back to the map in its language; the Unciv menu names
        are the game's own in that language (android/assets/jsons/translations)."""
        s = self.doc["summary"]
        menus = {"es": ("Descargar mod con Enlace", "Mods de extensión", "Escoger mapa"),
                 "en": ("Download mod from URL", "Extension mods", "Map file")}
        for lang, other in (("es", "en"), ("en", "es")):
            html = self.files[play.PAGES[lang]]().decode("utf-8")
            self.assertIn(f'<html lang="{lang}">', html)
            self.assertNotIn("$", html)
            for needle in (play.MOD_ZIP, play.MAP_FILE, play.SCREENSHOT[0], f"https://{ES.site_url}/{play.MOD_ZIP}",
                           f'download="{s["map_name"]}"', s["mod"]["repo"], *menus[lang], f'href="./#lang={lang}"',
                           f'href="{play.PAGES[other]}" lang="{other}"', f'<link rel="canonical" href="https://{ES.site_url}/{play.PAGES[lang]}">'):
                self.assertIn(needle, html)
            names = play.resource_texts(s, lang)
            for resource, n in s["resources"].items():
                self.assertIn(f"<td>{escape(names[resource][0])}</td><td class=n>{n}</td>", html)
            for start in s["starts"][1:]:
                self.assertIn(start["city"], html)
            for name in s["not_placed_designations"]:
                self.assertIn(escape(pick(name, lang)), html)
        self.assertIn("(PDO)", self.files[play.PAGES["en"]]().decode("utf-8"))

    def test_the_page_explains_the_fire_season(self):
        f = self.doc["summary"]["fire_season"]
        w = fire.weights(f)
        words = {"es": ("Temporada de incendios", "Convención:", "Supuesto:", "Enviar brigadas"),
                 "en": ("Fire season", "Convention:", "Assumption:", "Send fire brigades")}
        for lang in ("es", "en"):
            html = self.files[play.PAGES[lang]]().decode("utf-8")
            for needle in (*words[lang], play.FIRE_SHOT[lang][0], f"{f['great_fires']} ", f"{f['threshold_ha']} ha"):
                self.assertIn(needle, html)
            self.assertGreaterEqual(html.count(words[lang][1]), 5)  # one line per convention
            for c in f["classes"]:
                self.assertIn(f"<td>{escape(play.FIRE_CLASSES[lang][c['class']])}</td><td class=n>{c['tiles']}</td>", html)
                self.assertIn(f"<td class=n>{c['weight']}</td></tr>", html)
            spain = {c["class"]: c["tiles"] for c in f["classes"]}
            self.assertIn(f"<td>{escape(play.FIRE_EXAMPLES[lang][-1])}</td><td class=n>{spain['Land']}</td><td class=n>{spain['Hill']}</td><td class=n>{spain['Mountain']}</td>"
                          f"<td class=n>100{' %' if lang == 'es' else '%'}</td>", html)
            for start, end, gold in fire.COSTS:
                self.assertIn(str(gold), html)


class FireSeasonTest(unittest.TestCase):
    """pipeline/build/spain_unciv_fire.py: the rates from EFFIS's fires, the chance bands and the mod's files."""

    def setUp(self):
        self.fine = HexGrid(radius=10.0, cols=5, rows=1)  # cell centres every 17.32 km along y = 0
        x = lambda c: self.fine.center(c, 0)[0]
        self.box = lambda c: [(x(c) - 2, -1.0), (x(c) + 2, -1.0), (x(c) + 2, 1.0), (x(c) - 2, 1.0), (x(c) - 2, -1.0)]
        self.tiles = [unciv.Tile(cells=[0], national=[0], base="Mountain"),
                      unciv.Tile(cells=[1], national=[1], base="Plains", features=["Hill", "Forest"]),
                      unciv.Tile(cells=[2], national=[2], base="Grassland"),
                      unciv.Tile(cells=[3], national=[], base="Plains"),  # foreign land
                      unciv.Tile(cells=[4], national=[4], base="Ocean")]

    def fire(self, cell, ha, month=8, year=2020):
        return {"year": year, "month": month, "area_ha": ha, "rings": [self.box(cell)]}

    def season(self, fires):
        return fire.season({"years": [2020, 2021], "fires": fires}, self.tiles, self.fine, lambda lon, lat: (lon, lat))

    def test_classes_follow_uncivs_filters(self):
        self.assertEqual([fire.tile_class(t) for t in self.tiles[:3]], ["Mountain", "Hill", "Land"])
        self.assertEqual(fire.tile_class(unciv.Tile(base="Mountain", features=["Hill"])), "Mountain")  # never Hill

    def test_rates_by_class_from_the_great_fires_on_spanish_land(self):
        s = self.season([self.fire(1, 600, 7), self.fire(3, 800), self.fire(2, 400, 6), self.fire(0, 1000, 3),
                         self.fire(2, 700, 8, 2021), self.fire(4, 900)])
        by = {c["class"]: c for c in s["classes"]}
        # 500 ha and more: 5 fires; off Spanish land (foreign tile, sea tile) they count for nothing.
        self.assertEqual((s["great_fires"], s["on_spanish_tiles"], s["seasons"]), (5, 3.0, 2))
        self.assertEqual(s["per_season"], [4, 1])
        self.assertEqual({k: c["per_tile_season"] for k, c in by.items()}, {"Mountain": 0.5, "Hill": 0.5, "Land": 0.5})
        self.assertEqual({k: c["tiles"] for k, c in by.items()}, {"Mountain": 1, "Hill": 1, "Land": 1})
        self.assertAlmostEqual(sum(c["weight"] * c["tiles"] for c in s["classes"]), fire.UNIT, delta=len(fire.CLASSES))
        self.assertEqual(s["summer_share"], round((600 + 800 + 400 + 700 + 900) / 4400, 3))
        self.assertIsInstance(s["texts"]["event"], Text)

    def test_the_popup_counts_every_great_fire(self):
        """'about N a season' sits next to the count of all great fires, those off Spain's land tiles too."""
        s = self.season([self.fire(1, 600), self.fire(2, 600), self.fire(4, 600)])  # the last at sea
        self.assertEqual((s["great_fires"], s["on_spanish_tiles"], s["fires_per_season"]), (3, 2.0, 1.0))
        self.assertIn("unos 2 por temporada", s["texts"]["event"]["es"])
        self.assertIn("about 2 a season", s["texts"]["event"]["en"])
        self.assertFalse(s["texts"]["event"]["es"].startswith("Verano"))  # the event fires in any season

    def test_a_fire_on_a_hill_counts_for_hill_only(self):
        s = self.season([self.fire(1, 600), self.fire(0, 600), self.fire(2, 600)])
        self.assertEqual([c["per_tile_season"] for c in s["classes"]], [0.5, 0.5, 0.5])
        s = self.season([self.fire(1, 600), self.fire(1, 600), self.fire(0, 600), self.fire(2, 600)])
        by = {c["class"]: c["per_tile_season"] for c in s["classes"]}
        self.assertEqual(by, {"Mountain": 0.5, "Hill": 1.0, "Land": 0.5})

    def test_bands_are_contiguous_and_their_chance_is_the_formula(self):
        bands = fire.bands()
        self.assertEqual([p for p, _, _ in bands], list(range(1, 101)))
        self.assertEqual(fire.chance(bands[0][1] - 1), 0)  # below the first band: no line, no chance
        self.assertEqual(fire.chance(0), 0)
        for (p, lo, hi), nxt in zip(bands, bands[1:] + [None]):
            formula = lambda x: round(100 * (1 - (1 - min(x, fire.UNIT) / fire.UNIT) ** fire.CHECK_TURNS))
            self.assertEqual(formula(lo), p)
            if nxt:
                self.assertEqual((formula(hi), nxt[1]), (p, hi + 1))
        self.assertIsNone(bands[-1][2])
        self.assertEqual(fire.chance(fire.UNIT), 100)

    def summary(self):
        return {"classes": [{"class": "Mountain", "tiles": 60, "weight": 230}, {"class": "Hill", "tiles": 190, "weight": 200},
                            {"class": "Land", "tiles": 700, "weight": 67}],
                "texts": {k: t.format(n=311, ha=500, seasons=10, per=30, times=3, k=fire.CHECK_TURNS)
                          for k, t in fire.TEXTS.items()}}

    def test_global_uniques_evaluate_to_the_weighted_tiles(self):
        doc = fire.global_uniques_json(self.summary())
        w = fire.weights(self.summary())
        self.assertEqual(len(doc["uniques"]), 100)
        expr = re.compile(r"<when number of \[\[Owned \[Land\] Tiles\] \* (\d+) \+ \[Owned \[Hill\] Tiles\] \* (\d+)"
                          r" \+ \[Owned \[Mountain\] Tiles\] \* (\d+)\] (?:is between \[(\d+)\] and \[(\d+)\]|is more than \[(\d+)\])>")
        for line in doc["uniques"]:
            for part in (f"<every [{fire.CHECK_TURNS}] turns>", "<for [Major] Civilizations>", "<hidden from users>",
                         f"Triggers a [{fire.EVENT}] event <upon turn start>"):
                self.assertIn(part, line)
            land, hill, mountain, *_ = map(lambda g: int(g) if g else None, expr.search(line).groups())
            self.assertEqual((land, hill, mountain), (w["Land"], w["Hill"] - w["Land"], w["Mountain"] - w["Land"]))
        # Unciv counts Land over every land tile, hills and mountains too: the expression is Σ weight × tiles.
        land, hill, mountain = map(int, expr.search(doc["uniques"][0]).groups()[:3])
        for tiles in ({"Land": 7, "Hill": 0, "Mountain": 0}, {"Land": 24, "Hill": 6, "Mountain": 2}):
            unciv_value = land * sum(tiles.values()) + hill * tiles["Hill"] + mountain * tiles["Mountain"]
            self.assertEqual(unciv_value, fire.owned(tiles, w))
        p = int(re.search(r"<with \[(\d+)\]% chance>", doc["uniques"][-1]).group(1))
        self.assertEqual((p, "is more than" in doc["uniques"][-1]), (100, True))
        self.assertEqual(doc["civilopediaText"], [{"text": self.summary()["texts"]["pedia"]["en"]}])

    def test_one_brigades_choice_in_every_era_and_penalties_never_overlap(self):
        (event,) = fire.events_json(self.summary())
        pays = [c for c in event["choices"] if c["text"] == fire.TEXTS["pay"]["en"]]
        self.assertEqual(len(pays), len(fire.COSTS))
        for era_number, era in enumerate(unciv.ERAS):
            def available(choice):
                only = next(u for u in choice["uniques"] if u.startswith("Only available"))
                start = re.search(r"<starting from the \[(.+?)\]>", only)
                end = re.search(r"<before the \[(.+?)\]>", only)
                return ((not start or unciv.ERAS.index(start.group(1)) <= era_number)
                        and (not end or era_number < unciv.ERAS.index(end.group(1))))
            self.assertEqual(sum(map(available, pays)), 1, era)
        for choice, (_, _, gold) in zip(pays, fire.COSTS):
            self.assertIn(f"Gain [-{gold}] [Gold] <(modified by game speed)>", choice["uniques"])
            only = next(u for u in choice["uniques"] if u.startswith("Only available"))
            # The bound is the cost, both scaled by speed: a civilization that pays never goes below zero gold.
            self.assertIn(f"<when above [{gold}] [Gold]>", only)
            self.assertIn("<(modified by game speed)>", only)
        burn = event["choices"][-1]
        self.assertEqual(fire.PENALTY_TURNS, fire.CHECK_TURNS)
        self.assertEqual(burn["uniques"], [f"[{fire.PENALTY_PCT}]% [Production] [in all cities] <for [{fire.CHECK_TURNS}] turns>"])
        self.assertEqual(fire.costs_by_era()["Ancient era"], fire.COSTS[0][2])

    def test_every_game_text_has_its_spanish_and_unciv_reads_it_back(self):
        summary = self.summary()
        (event,) = fire.events_json(summary)
        english = {event["text"], *(c["text"] for c in event["choices"]),
                   *(t["text"] for t in fire.global_uniques_json(summary)["civilopediaText"])}
        pairs = dict(fire.translations(summary))
        self.assertLessEqual(english, set(pairs))
        for text in [*pairs, *pairs.values()]:
            self.assertIsNone(re.search(r"\d{4}", text), text)  # Unciv would write a year as 2.016
        self.assertEqual(unciv.properties([("Fire season", "Temporada de incendios")]), "Fire season = Temporada de incendios\n")
        for bad in ([("A = B", "x")], [("a", "b [c]")], [("a", "b\nc")], [("a {b}", "c")], [("# a", "b")], [("a", "b"), ("a", "c")]):
            with self.assertRaises(ValueError):
                unciv.properties(bad)

    def test_the_built_map_has_its_fire_season(self):
        f = built()["summary"]["fire_season"]
        self.assertEqual(f["threshold_ha"], fire.GREAT_FIRE_HA)
        self.assertEqual(sum(f["per_season"]), f["great_fires"])
        self.assertTrue(all(f["per_season"]))  # a great fire every season
        self.assertEqual(sum(c["tiles"] for c in f["classes"]), built()["summary"]["national_land_tiles"])
        self.assertAlmostEqual(sum(c["weight"] * c["tiles"] for c in f["classes"]), fire.UNIT, delta=fire.UNIT / 100)
        w = fire.weights(f)
        self.assertGreater(w["Hill"], w["Land"])
        self.assertGreater(w["Mountain"], w["Land"])

    def test_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(fire.check(tmp), [])  # no Unciv map (the US): nothing to say
            doc = {"summary": {"fire_season": {"classes": [{"class": "Land", "tiles": 10, "weight": 10_200}],
                                               "unit": fire.UNIT, "great_fires": 3, "threshold_ha": 500, "fires_per_season": 1.0,
                                               "on_spanish_tiles": 2.9}}}
            (Path(tmp) / "unciv.json").write_text(json.dumps(doc))
            self.assertEqual(fire.check(tmp)[0][0], "FAIL")
            doc["summary"]["fire_season"]["classes"][0]["weight"] = 10_000
            (Path(tmp) / "unciv.json").write_text(json.dumps(doc))
            self.assertEqual(fire.check(tmp)[0][0], "PASS")


class BdminPositionTest(unittest.TestCase):
    def test_the_geometry_not_the_utm_fields(self):
        # BDMIN's X and Y are sometimes UTM metres (Salave); the geometry asked for in WGS84 is right.
        import tempfile
        from pathlib import Path
        from pipeline.sources.es.mines import IgmeMinas

        feature = {"attributes": {"Codigo_indicio": "0010009", "Nombre_mina": "Salave", "Municipio": "Tapia de Casariego",
                                  "Provincia": "ASTURIAS", "Sustancia": " Oro", "Tamaño_indicio": "grande",
                                  "X": 668599.97427368, "Y": 4825949.9889806},
                   "geometry": {"x": -6.912208999999962, "y": 43.56745100000006}}
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "bdmin_yacimientos_0.json").write_text(json.dumps({"features": [feature]}))
            with mock.patch.object(IgmeMinas, "raw_dir", Path(d)):
                (deposit,), files = IgmeMinas().deposits("bdmin_yacimientos")
        self.assertEqual((deposit["lon"], deposit["lat"]), (-6.912209, 43.567451))
        self.assertEqual(files, ["bdmin_yacimientos_0.json"])


if __name__ == "__main__":
    unittest.main()
