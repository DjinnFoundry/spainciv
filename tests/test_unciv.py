"""The Unciv export: the hex geometry and file format (pipeline/build/unciv.py), Spain's map (pipeline/build/spain_unciv.py,
sites/es/data/unciv.json) and its mod, downloads and page (pipeline/play.py)."""

import base64
import gzip
import io
import json
import math
import unittest
import zipfile
from collections import Counter
from html import escape
from unittest import mock

from pipeline import countries, play, site
from pipeline.core.lang import pick
from pipeline.build import spain_flags, spain_unciv, unciv
from pipeline.core.paths import ROOT
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

    def test_the_bare_map_starts_spain_in_madrid_and_the_others_far_apart(self):
        starts = self.doc["bare"]["startingLocations"]
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
            self.assertTrue(all(len(v) == 3 for v in texts[lang].values()), lang)  # name, source, word in a sentence
        self.assertEqual(texts["en"]["Horses"][2], "horse")  # "the map's 19 horse tiles"
        self.assertTrue(set(unciv.REVEALED_BY) <= {r for r, (kind, _, _) in unciv.RESOURCES.items() if kind == "Strategic"})

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
        bare = unciv.without_mod(doc, built()["bare"])
        self.assertEqual(bare["mapParameters"]["mods"], [])
        self.assertEqual({s["nation"] for s in bare["startingLocations"]}, {"Spain", unciv.SPECTATOR})
        self.assertIn("España empieza en Madrid", bare["description"])
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
        self.assertEqual(set(self.files), {*play.PAGES.values(), play.MOD_ZIP, play.MAP_FILE, play.PREVIEW, play.SCREENSHOT[0]})
        self.assertEqual(play.files(countries.COUNTRIES["us"]), {})
        self.assertEqual(site.page_config(ES)["play"], play.PAGES["es"])
        self.assertEqual(site.page_config(ES)["texts"]["en"]["play"], play.PAGES["en"])

    def test_the_mod_zip_is_one_folder_unciv_can_install(self):
        z = zipfile.ZipFile(io.BytesIO(self.files[play.MOD_ZIP]()))
        names = z.namelist()
        self.assertEqual({n.split("/")[0] for n in names}, {self.folder})
        inner = {n.split("/", 1)[1] for n in names}
        map_name = self.doc["summary"]["map_name"]
        nations = [n["name"] for n in self.doc["summary"]["nations"]]
        self.assertEqual(inner, {"jsons/ModOptions.json", "jsons/TileResources.json", "jsons/Nations.json",
                                 "jsons/translations/Spanish.properties", f"maps/{map_name}",
                                 "Images/ResourceIcons/Cerdo ibérico.png", "game.png", "game.atlas", "Atlases.json",
                                 "preview.png", "README.md", "LICENSE",
                                 *(f"Images/NationPortraits/{n}.png" for n in nations),
                                 # a city-state's banner shows its type's icon, never a NationIcon (unciv.py)
                                 *(f"Images/NationIcons/{n['name']}.png" for n in self.doc["summary"]["nations"]
                                   if not n["city_state"])})
        read = lambda p: z.read(f"{self.folder}/{p}")
        options = json.loads(read("jsons/ModOptions.json"))
        self.assertEqual((options["isBaseRuleset"], options["topics"]), (False, ["unciv-mod-maps"]))
        self.assertEqual(json.loads(read("jsons/TileResources.json")), unciv.tile_resources_json())
        self.assertEqual(read("Atlases.json").strip(), b"[game]")
        regions = [line for line in read("game.atlas").decode("utf-8").splitlines() if "/" in line and ":" not in line]
        self.assertEqual(sorted(regions), sorted(n.removeprefix("Images/").removesuffix(".png") for n in inner if n.startswith("Images/")))
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

    def test_the_bare_map_is_the_map_without_the_mod(self):
        self.assertEqual(unciv.decode(self.files[play.MAP_FILE]()), unciv.without_mod(self.doc["map"], self.doc["bare"]))

    def test_the_page(self):
        """One page per language, each linking to the other and back to the map in its language; the Unciv menu names
        are the game's own in that language (android/assets/jsons/translations)."""
        s = self.doc["summary"]
        menus = {"es": ("Descargar mod con Enlace", "Mods de extensión", "Escoger mapa", "Humano",
                        "Seleccionar jugadores según las posiciones iniciales", "Juega con tu comunidad"),
                 "en": ("Download mod from URL", "Extension mods", "Map file", "Human",
                        "Select players from starting locations", "Play as your community")}
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
            for row in play.nation_rows(s, lang):
                self.assertIn("<tr>" + "".join(f"<td>{escape(c)}</td>" for c in row[:play.PAGE_COLUMNS]) + "</tr>", html)
            # The nations' table fits a phone: three columns, in a box that scrolls rather than clips; long words and
            # the mod's address break.
            table = html.split('<div class="scroll"><table id="nations">', 1)[1].split("</table></div>", 1)[0]
            self.assertEqual(table.count("<th>"), play.PAGE_COLUMNS)
            self.assertIn("main code { overflow-wrap: anywhere; }", html)
            self.assertIn(play.moved_starts(s), html)
            self.assertIn(escape(play.unique_fallback(s, lang)), html)
            for name in s["not_placed_designations"]:
                self.assertIn(escape(pick(name, lang)), html)
        self.assertIn("(PDO)", self.files[play.PAGES["en"]]().decode("utf-8"))


class NationRulesTest(unittest.TestCase):
    """The rules that pick a nation's start bias, unique resource and starting tile (pipeline/build/spain_unciv.py)."""

    def test_start_bias_is_the_most_over_represented_terrain_on_enough_land(self):
        spain = Counter({"Plains": 60, "Forest": 20, "Coast": 20, "Hill": 10})
        # Forest: 40 % of its land, twice Spain's share; Hill is rarer still in Spain but on 20 % only.
        self.assertEqual(spain_unciv.start_bias(Counter({"Plains": 5, "Forest": 4, "Hill": 2}), 10, spain, 100), "Forest")
        self.assertIsNone(spain_unciv.start_bias(Counter({"Plains": 6, "Hill": 2}), 10, spain, 100))  # Plains: lift 1

    def test_unique_resource_prefers_enough_tiles_then_the_highest_lift(self):
        totals = Counter({"Wine": 100, "Copper": 4, "Salt": 10})
        held = Counter({"Wine": 10, "Copper": 1, "Salt": 2})
        self.assertEqual(spain_unciv.unique_resource(held, totals, 0.05), "Salt")  # Copper's 1 tile is not enough
        self.assertEqual(spain_unciv.unique_resource(Counter({"Copper": 1, "Wine": 1}), totals, 0.05), "Copper")
        self.assertIsNone(spain_unciv.unique_resource(Counter(), totals, 0.05))

    def test_a_seat_too_close_to_a_larger_start_moves_to_its_own_nearest_free_tile(self):
        grid = unciv.Grid(25.0, 12, 9, (150.0, 112.0))
        tiles = [unciv.Tile(base="Plains") for _ in grid.tiles]
        a = grid.locate(150.0, 112.0)
        b = grid.ring(a)[0]
        of_tile = {t: "A" for t in range(len(tiles))} | {t: "B" for t in range(len(tiles)) if grid.center(t)[0] > 175}
        placed = spain_unciv.seat_starts(grid, tiles, of_tile, [("A", *grid.center(a)), ("B", *grid.center(b))])
        self.assertEqual(placed["A"], (a, 0))
        tb, off = placed["B"]
        self.assertEqual(of_tile[tb], "B")
        self.assertEqual(spain_unciv.distance(grid, a, tb), spain_unciv.MIN_SEAT_GAP)
        self.assertEqual(off, spain_unciv.distance(grid, tb, b))

    def test_a_sea_tile_belongs_to_the_land_around_it_not_to_other_sea(self):
        # One land tile of community 12 in a sea: only its ring of coast is 12's; the open sea is no one's.
        world = fine_world()
        fine = HexGrid(**world["grid"])
        grid = unciv.Grid.covering(fine, 25.0)
        t = grid.locate(world["width"] / 2, world["height"] / 2)
        set_land(world, unciv.resample(world, grid)[t].cells, owner=0)
        world["states"] = [{"fips": "15"}]  # A Coruña: Galicia
        tiles = unciv.resample(world, grid)
        unciv.terrain(world, grid, tiles)
        of_tile = spain_unciv.tile_communities(world, grid, fine, tiles)
        self.assertEqual(set(of_tile), {t, *grid.ring(t)})
        self.assertEqual(set(of_tile.values()), {"12"})


class NationsTest(unittest.TestCase):
    """The nations of unciv.json as built, and the mod's Nations.json and translation made of them."""

    @classmethod
    def setUpClass(cls):
        cls.doc = built()
        cls.summary = cls.doc["summary"]
        cls.nations = cls.summary["nations"]
        cls.grid = grid_of(cls.summary)
        cls.tiles = unciv.tiles_from_map(cls.doc["map"])
        z = zipfile.ZipFile(io.BytesIO(play.files(ES)[play.MOD_ZIP]()))
        folder = cls.summary["mod"]["name"]
        cls.nations_json = json.loads(z.read(f"{folder}/jsons/Nations.json"))
        cls.spanish = z.read(f"{folder}/jsons/translations/Spanish.properties").decode("utf-8")

    def test_the_communities_are_civilizations_and_the_cities_city_states(self):
        from pipeline.sources.es.provinces import COMMUNITIES
        self.assertEqual({n["code"] for n in self.nations}, set(COMMUNITIES))
        self.assertEqual({n["code"] for n in self.nations if n["city_state"]}, {"18", "19"})
        self.assertEqual(len({n["name"] for n in self.nations}), len(self.nations))
        for n in self.nations:
            self.assertNotIn("/", n["name"])  # the name is a file name in Images/
        by_name = {n["name"]: n for n in self.nations_json}
        self.assertEqual(by_name["Ceuta"]["cityStateType"], "Maritime")
        self.assertEqual(by_name["Euskadi (País Vasco)"]["leaderName"], "Lendakari")  # LO 3/1979 art. 24.1

    def test_every_nation_starts_at_its_seat_far_enough_from_the_others(self):
        by_pos = {p: i for i, p in enumerate(self.grid.positions)}
        starts = self.doc["map"]["startingLocations"]
        self.assertEqual([s["nation"] for s in starts], [n["name"] for n in self.nations])
        idx = []
        for s, n in zip(starts, self.nations):
            self.assertEqual(s["usage"], "Normal" if n["city_state"] else "Human")
            t = by_pos[(s["position"]["x"], s["position"]["y"])]
            self.assertTrue(self.tiles[t].passable_land, n["name"])
            idx.append(t)
        for i, a in enumerate(idx):
            for b in idx[i + 1:]:
                self.assertGreaterEqual(spain_unciv.distance(self.grid, a, b), spain_unciv.MIN_SEAT_GAP)
        moved = {n["name"]: n["start_off_seat"] for n in self.nations if n["start_off_seat"]}
        self.assertEqual(set(moved), {"Castilla-La Mancha", "La Rioja"})  # Toledo by Madrid, Logroño by Vitoria
        self.assertTrue(all(0 < v < spain_unciv.MIN_SEAT_GAP for v in moved.values()))

    def test_cities_are_the_seat_then_the_most_populous_municipalities(self):
        padron = json.loads((ROOT / "data" / "interim" / "es" / "ine_padron.json").read_text(encoding="utf-8"))["data"]
        year = spain_unciv.padron_year(padron)
        siane = json.loads((ROOT / "data" / "interim" / "es" / "siane.json").read_text(encoding="utf-8"))["data"]
        from pipeline.sources.es.provinces import COMMUNITY_OF
        code_of = {(COMMUNITY_OF[m["geoid"][:2]], m["name"]): m["geoid"] for m in siane["municipalities"]}
        firsts = {n["name"]: n["cities"][0] for n in self.nations}
        self.assertEqual(firsts["Canarias"], "Las Palmas de Gran Canaria")
        self.assertEqual(firsts["Euskadi (País Vasco)"], "Vitoria-Gasteiz")
        self.assertEqual(firsts["Galicia"], "Santiago de Compostela")
        self.assertEqual(firsts["Castilla y León"], "Valladolid")
        for n in self.nations:
            if n["city_state"]:
                self.assertEqual(n["cities"], [n["name"]])
                continue
            self.assertEqual(len(n["cities"]), spain_unciv.CITY_NAMES)
            self.assertEqual(code_of[n["code"], n["cities"][0]], n["seat"])
            pops = [padron["municipalities"][code_of[n["code"], c]]["pop"][year] for c in n["cities"][1:]]
            self.assertEqual(pops, sorted(pops, reverse=True), n["name"])

    def test_bias_unique_and_texts(self):
        for n, j in zip(self.nations, self.nations_json):
            self.assertEqual(j["name"], n["name"])
            if n["city_state"]:
                continue
            self.assertIn(n["resource"], unciv.RESOURCES)
            self.assertEqual(j["uniques"], [unciv.NATION_UNIQUE.format(resource=n["resource"])])
            self.assertLessEqual(n["resource_tiles"], n["resource_map_tiles"])
            self.assertTrue(n["start_bias"] is None or n["start_bias"] in spain_unciv.BIAS_TERRAINS)
            self.assertTrue(pick(n["leader"], "es").startswith("Presidencia") or n["code"] == "16", n["name"])
            en, es = (play.nation_texts(self.summary, n, lang) for lang in ("en", "es"))
            for key, field in ((j["leaderName"], "leader"), (j["uniqueName"], "unique_name"), (j["startIntroPart1"], "intro")):
                self.assertEqual(key, en[field])
                if es[field] != key:  # every English text has its Spanish line, unless it is the same ("Lendakari")
                    self.assertIn(f"{key} = {es[field]}\n", self.spanish)
        self.assertIn("Tierra de vino", self.spanish)

    def test_municipalities_are_those_of_the_last_padron(self):
        # The Padrón's series keeps the codes of merged municipalities (Cerdedo and Cotobade, Cesuras and Oza dos Ríos
        # in Galicia) without a population in its last year: they are not counted.
        padron = json.loads((ROOT / "data" / "interim" / "es" / "ine_padron.json").read_text(encoding="utf-8"))["data"]
        year = spain_unciv.padron_year(padron)
        live = [m for m in padron["municipalities"].values() if m["pop"].get(year) is not None]
        cities = sum(len(spain_unciv.community_municipalities(padron, n["code"])) for n in self.nations if n["city_state"])
        self.assertEqual(sum(n.get("municipalities", 0) for n in self.nations) + cities, len(live))
        by_name = {n["name"]: n for n in self.nations}
        self.assertEqual(by_name["Galicia"]["municipalities"], 313)
        self.assertEqual(sum(n.get("population", 0) for n in self.nations) + sum(
            spain_unciv.population(m, year) for n in self.nations if n["city_state"]
            for m in spain_unciv.community_municipalities(padron, n["code"]).values()),
            sum(spain_unciv.population(m, year) for m in live))

    def test_the_texts_say_where_a_moved_nation_starts_and_when_its_resource_shows(self):
        by_name = {n["name"]: n for n in self.nations}
        clm, rioja, cyl = by_name["Castilla-La Mancha"], by_name["La Rioja"], by_name["Castilla y León"]
        self.assertIn("Empiezas a 1 casilla de Toledo.", play.nation_texts(self.summary, clm, "es")["intro"])
        self.assertIn("You start 2 tiles from Logroño.", play.nation_texts(self.summary, rioja, "en")["intro"])
        self.assertEqual(play.nation_texts(self.summary, rioja, "es")["starts_in"], "Logroño (a 2 casillas)")
        self.assertEqual(play.nation_texts(self.summary, by_name["Galicia"], "es")["starts_in"], "Santiago de Compostela")
        asturias = by_name["Asturias"]
        self.assertEqual(asturias["resource"], "Coal")  # dormant until Industrialization: the texts say so
        self.assertIn("hasta que descubres Industrialización", play.nation_texts(self.summary, asturias, "es")["intro"])
        self.assertIn("revealed by Industrialization", play.nation_texts(self.summary, asturias, "en")["advantage"])
        self.assertNotIn("revealed", play.nation_texts(self.summary, cyl, "en")["advantage"])  # sheep: always seen
        self.assertNotIn("revealed", play.nation_texts(self.summary, by_name["Canarias"], "en")["advantage"])

    def test_editorial_picks_are_held_and_said(self):
        by_code = {n["code"]: n for n in self.nations}
        for code, resource in spain_unciv.UNIQUE_PICKS.items():
            n = by_code[code]
            self.assertEqual((n["resource"], n["resource_editorial"]), (resource, True))
            self.assertGreater(n["resource_tiles"], 0, n["name"])
        self.assertFalse(by_code["08"]["resource_editorial"])  # Castilla-La Mancha keeps the rule's wine
        es = play.unique_fallback(self.summary, "es")
        self.assertIn("elegido a mano en", es)
        self.assertIn("Galicia (", es)
        self.assertNotIn("Galicia", es.split("entre todos")[-1])  # a picked nation is not listed as a fallback

    def test_terrain_and_technology_names_are_unciv_s_own(self):
        # Unciv 5.0.1, android/assets/jsons/translations/Spanish.properties: what its nation picker shows.
        spanish = {"Coast": "Costa", "Hill": "Colinas", "Mountain": "Montaña", "Forest": "Bosque", "Marsh": "Pantano",
                   "Grassland": "Pradera", "Plains": "Sabana", "Desert": "Desierto", "Tundra": "Tundra"}
        techs = {"Animal Husbandry": "Ganadería", "Iron Working": "Trabajo del hierro",
                 "Industrialization": "Industrialización", "Biology": "Biología", "Electricity": "Electricidad",
                 "Atomic Theory": "Teoría atómica"}
        es, en = play.nation_templates("es"), play.nation_templates("en")
        self.assertEqual(es["terrains"], spanish)
        self.assertEqual(en["terrains"], {t: t for t in spain_unciv.BIAS_TERRAINS})
        self.assertEqual(es["techs"], techs)
        self.assertEqual(en["techs"], {t: t for t in techs})
        self.assertEqual(set(techs), set(unciv.REVEALED_BY.values()))

    def test_colours_contrast_as_unciv_asks_and_no_two_nations_share_both(self):
        pairs = [(tuple(n["outer"]), tuple(n["inner"])) for n in self.nations]
        self.assertEqual(len(set(pairs)), len(pairs))
        for outer, inner in pairs:
            self.assertGreaterEqual(spain_flags.contrast(outer, inner), 3)  # RulesetValidator.checkContrasts

    def test_flag_images(self):
        n = unciv.ICON_PX
        for nation in self.nations:
            portrait, icon = play.flag_images(nation)
            self.assertEqual((len(portrait), len(icon)), (4 * n * n, 4 * n * n))
            self.assertEqual((portrait[3], icon[3]), (0, 0))  # outside the disc
            middle = 4 * (n * (n // 2) + n // 2)
            self.assertEqual(portrait[middle + 3], 255)
            if not nation["city_state"]:  # the icon shows the inner colour's part of the flag
                self.assertTrue(any(icon[k] for k in range(3, len(icon), 4)), nation["name"])
        galicia = next(x for x in self.nations if x["name"] == "Galicia")
        portrait, _ = play.flag_images(galicia)
        centre = 4 * (n * (n // 2) + n // 2)
        self.assertEqual(tuple(portrait[centre:centre + 3]), spain_flags.CELESTE)  # the band crosses the centre


class FormatHelpersTest(unittest.TestCase):
    def test_nation_json(self):
        major = unciv.nation_json("Galicia", (1, 2, 3), (4, 5, 6), ["Santiago"], leader="President", start_bias="Forest",
                                  unique_name="Land of Iron", resource="Iron", intro="Hola")
        self.assertEqual((major["startBias"], major["uniques"]), (["Forest"], ["[+1 Food, +1 Production, +1 Gold] from [Iron] tiles [in all cities]"]))
        cs = unciv.nation_json("Ceuta", (0, 0, 0), (255, 255, 255), ["Ceuta"], city_state_type="Maritime")
        self.assertEqual(set(cs), {"name", "cityStateType", "outerColor", "innerColor", "cities"})

    def test_properties(self):
        self.assertEqual(unciv.properties({"Land of Iron": "Tierra de hierro", "a\nb": "c\nd"}),
                         "Land of Iron = Tierra de hierro\na\\nb = c\\nd\n")
        for bad in ("[x] of y", "a = b"):
            with self.assertRaises(ValueError):
                unciv.properties({bad: "z"})

    def test_contrast(self):
        self.assertAlmostEqual(spain_flags.contrast((0, 0, 0), (255, 255, 255)), 21)
        self.assertAlmostEqual(spain_flags.contrast((1, 2, 3), (1, 2, 3)), 1)

    def test_atlas_packs_every_image(self):
        images = {f"NationIcons/{k}": bytes(4 * unciv.ICON_PX ** 2) for k in range(12)}
        out = play.icon_atlas(images)
        text = out["game.atlas"].decode("utf-8")
        self.assertIn("size: 1024, 256", text)
        self.assertEqual(sum(line.startswith("NationIcons/") for line in text.splitlines()), 12)



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
