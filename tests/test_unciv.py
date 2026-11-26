"""The Unciv export: the hex geometry and file format (pipeline/build/unciv.py), Spain's map (pipeline/build/spain_unciv.py,
sites/es/data/unciv.json) and its mod, downloads and page (pipeline/play.py)."""

import base64
import gzip
import io
import json
import math
import unittest
import zipfile
from unittest import mock

from pipeline import countries, play, site
from pipeline.build import spain_unciv, unciv
from pipeline.build.world import COAST, LAKE, LAND, OCEAN
from pipeline.core.hexgrid import HexGrid

ES = countries.COUNTRIES["es"]


def built() -> dict:
    return json.loads((ES.web_data_dir / "unciv.json").read_text(encoding="utf-8"))


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
        self.assertEqual(set(self.files), {play.PAGE, play.MOD_ZIP, play.MAP_FILE, play.PREVIEW, play.SCREENSHOT[0]})
        self.assertEqual(play.files(countries.COUNTRIES["us"]), {})
        self.assertEqual(site.page_config(ES)["play"], play.PAGE)

    def test_the_mod_zip_is_one_folder_unciv_can_install(self):
        z = zipfile.ZipFile(io.BytesIO(self.files[play.MOD_ZIP]()))
        names = z.namelist()
        self.assertEqual({n.split("/")[0] for n in names}, {self.folder})
        inner = {n.split("/", 1)[1] for n in names}
        map_name = self.doc["summary"]["map_name"]
        self.assertEqual(inner, {"jsons/ModOptions.json", "jsons/TileResources.json", f"maps/{map_name}",
                                 "Images/ResourceIcons/Cerdo ibérico.png", "game.png", "game.atlas", "Atlases.json",
                                 "preview.png", "README.md", "LICENSE"})
        read = lambda p: z.read(f"{self.folder}/{p}")
        options = json.loads(read("jsons/ModOptions.json"))
        self.assertEqual((options["isBaseRuleset"], options["topics"]), (False, ["unciv-mod-maps"]))
        self.assertEqual(json.loads(read("jsons/TileResources.json")), unciv.tile_resources_json())
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

    def test_the_bare_map_is_the_map_without_the_mod(self):
        self.assertEqual(unciv.decode(self.files[play.MAP_FILE]()), unciv.without_mod(self.doc["map"]))

    def test_the_page(self):
        html = self.files[play.PAGE]().decode("utf-8")
        s = self.doc["summary"]
        self.assertIn('<html lang="es">', html)
        self.assertNotIn("$", html)
        for needle in (play.MOD_ZIP, play.MAP_FILE, play.SCREENSHOT[0], f"https://{ES.site_url}/{play.MOD_ZIP}",
                       f'download="{s["map_name"]}"', s["mod"]["repo"], "Descargar mod con Enlace", "Mods de extensión"):
            self.assertIn(needle, html)
        names = play.resource_texts(s, "es")
        for resource, n in s["resources"].items():
            self.assertIn(f"<td>{names[resource][0]}</td><td class=n>{n}</td>", html)
        for start in s["starts"][1:]:
            self.assertIn(start["city"], html)


if __name__ == "__main__":
    unittest.main()
