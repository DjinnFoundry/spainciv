"""The social card drawn from the data (pipeline/card.py) and what draws it: core.font, core.raster, core.png.encode."""

import json
import shutil
import subprocess
import unittest

from pipeline import card, countries
from pipeline.core import png
from pipeline.core.font import cinzel
from pipeline.core.hexgrid import HexGrid
from pipeline.core.paths import ROOT
from pipeline.core.raster import Canvas

NODE = shutil.which("node")
ES = countries.COUNTRIES["es"]


def world_es():
    return json.loads((ES.web_data_dir / "world.json").read_text(encoding="utf-8"))


class FontTest(unittest.TestCase):
    def setUp(self):
        self.font = cinzel()

    def test_metrics(self):
        self.assertEqual(self.font.units_per_em, 1000)
        self.assertAlmostEqual(self.font.width("SPAIN", 100), 2 * self.font.width("SPAIN", 50))
        self.assertAlmostEqual(self.font.width("AB", 40, tracking=5), self.font.width("A", 40) + self.font.width("B", 40) + 5)

    def test_spanish_letters_have_outlines(self):
        for ch in "ÑñáéíóúüÁÉÍÓÚàèòç·":
            gid = self.font.glyph(ch)
            self.assertNotEqual(gid, 0, ch)
            self.assertTrue(self.font.contours(gid), ch)
        # Ñ is a composite glyph (N and a tilde): it has the N's contours and more, the tilde above the N.
        n, enye = self.font.contours(self.font.glyph("N")), self.font.contours(self.font.glyph("Ñ"))
        self.assertGreater(len(enye), len(n))
        self.assertGreater(max(y for c in enye for _, y in c), max(y for c in n for _, y in c))

    def test_outline_is_placed_in_pixels_y_down(self):
        polys = self.font.outline("I", 100, 10, 200)
        xs = [x for p in polys for x, _ in p]
        ys = [y for p in polys for _, y in p]
        self.assertTrue(10 <= min(xs) and max(xs) <= 10 + self.font.width("I", 100))
        self.assertLess(min(ys), 200)  # the letter stands above its baseline
        self.assertAlmostEqual(max(ys), 200, delta=1)

    def test_missing_glyph_is_notdef(self):
        self.assertEqual(self.font.glyph("中"), 0)


class RasterTest(unittest.TestCase):
    def test_exact_coverage(self):
        c = Canvas(4, 2, (0, 0, 0))
        c.rect(0.5, 0, 2, 2, (200, 100, 0))
        self.assertEqual([c.get(x, 0) for x in range(4)], [(100, 50, 0), (200, 100, 0), (0, 0, 0), (0, 0, 0)])

    def test_overlapping_strokes_unite_and_counters_stay_open(self):
        c = Canvas(20, 20)
        # Two overlapping pieces of one stroke: the overlap is painted once, not twice at half strength.
        c.stroke([(2, 10), (10, 10), (18, 10)], 4, (255, 255, 255), 0.5)
        self.assertEqual(c.get(10, 10), (128, 128, 128))
        # An "O": its inner contour winds the other way and stays empty.
        c = Canvas(120, 120)
        c.text(cinzel(), "O", 100, 10, 100, (255, 255, 255))
        self.assertEqual(c.get(55, 64), (0, 0, 0))
        self.assertGreater(sum(c.get(x, 64)[0] for x in range(120)), 0)

    def test_png_roundtrip(self):
        c = Canvas(7, 5, (10, 20, 30))
        for x in range(7):
            c.set(x, x % 5, (x * 30, 255 - x * 30, 7))
        w, h, rows = png.decode(c.png())
        self.assertEqual((w, h), (7, 5))
        self.assertEqual(rows, [[c.get(x, y) for x in range(7)] for y in range(5)])


class GridTest(unittest.TestCase):
    def test_neighbour_by_direction(self):
        g = HexGrid(1.0, 4, 3)
        i = g.index(1, 1)  # odd row: shifted right
        self.assertEqual([g.col_row(g.neighbour(i, d)) for d in range(6)], [(2, 1), (2, 2), (1, 2), (0, 1), (1, 0), (2, 0)])
        self.assertEqual(g.neighbour(g.index(0, 0), 3), -1)
        self.assertEqual(g.neighbours(g.index(0, 0)), [g.index(1, 0), g.index(0, 1)])


class CardLayoutTest(unittest.TestCase):
    def test_wrap_breaks_evenly_and_fits(self):
        font = cinzel()
        title = ES.page.in_lang('es').card_title
        lines = card.wrap(font, title, 30, 330)
        self.assertEqual(" ".join(lines), title)
        self.assertTrue(all(font.width(line, 30) <= 330 for line in lines))
        self.assertEqual(card.wrap(font, "una", 30, 1), ["una"])

    def test_frame_holds_every_hex_and_the_canary_inset(self):
        world = world_es()
        view = card.frame(world, card.PANEL_X, card.HEIGHT)
        grid = card.grid_of(world)
        boxes = card.inset_boxes(world)
        self.assertEqual(len(boxes), 1)
        points = [grid.center(*grid.col_row(i)) for i, o in enumerate(world["owner"]) if o >= 0]
        points += [b[:2] for b in boxes] + [b[2:] for b in boxes]
        for x, y in map(lambda p: view.px(*p), points):
            self.assertTrue(0 <= x <= card.PANEL_X and 0 <= y <= card.HEIGHT, (x, y))
        # Canarias sits in the south-west, inside its box.
        canarias = [grid.center(*grid.col_row(i)) for i, o in enumerate(world["owner"]) if o >= 0 and world["states"][o]["fips"] in ("35", "38")]
        x0, y0, x1, y1 = boxes[0]
        self.assertTrue(canarias and all(x0 <= x <= x1 and y0 <= y <= y1 for x, y in canarias))

    def test_us_has_no_drawn_card(self):
        with self.assertRaises(ValueError):
            card.card_png(countries.COUNTRIES["us"])


@unittest.skipUnless(NODE, "node is not installed")
class HexColourParityTest(unittest.TestCase):
    def test_same_colours_as_the_web_map(self):
        script = (
            f"import({json.dumps((ROOT / 'web' / 'js' / 'world.js').as_uri())}).then(({{prepareWorld}}) => {{"
            f"const w = prepareWorld(JSON.parse(require('fs').readFileSync({json.dumps(str(ES.web_data_dir / 'world.json'))})), []);"
            "console.log(JSON.stringify(w.terrainColors)); });"
        )
        js = json.loads(subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True).stdout)
        py = card.hex_colours(world_es())
        self.assertEqual(len(js), len(py))
        worst = max(abs(a - b) for cj, cp in zip(js, py) for a, b in zip(cj, cp))
        self.assertLess(worst, 1e-3)  # the web map keeps its hill-shading in a Float32Array


class SpainCardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.png = card.card_png(ES)
        cls.w, cls.h, cls.rows = png.decode(cls.png)

    def px(self, x, y):
        return self.rows[round(y)][round(x)]

    def test_size_and_determinism(self):
        self.assertEqual((self.w, self.h), (card.WIDTH, card.HEIGHT))
        self.assertEqual(card.card_png(ES), self.png)
        self.assertLess(len(self.png), 5_000_000)  # X's limit for card images

    def test_map_and_panel(self):
        world = world_es()
        view = card.frame(world, card.PANEL_X, card.HEIGHT)
        grid = card.grid_of(world)
        cities = {c["id"]: c for c in json.loads((ES.web_data_dir / "cities.json").read_text(encoding="utf-8"))}
        madrid = cities[ES.capital_city]
        r, g, b = self.px(*view.px(madrid["x"], madrid["y"]))
        self.assertTrue(r > 220 and g > 190 and b > 120, (r, g, b))  # the capital's gold marker
        # Deep sea west of Galicia is blue; inland Spain south of Madrid is land (red and green over blue).
        r, g, b = self.px(*view.px(grid.center(5, 40)[0], grid.center(5, 40)[1]))
        self.assertGreater(b, r)
        land = next(i for i in range(madrid["cell"] + 6 * grid.cols, grid.size) if world["owner"][i] >= 0 and not world["water"][i])
        r, g, b = self.px(*view.px(*grid.center(*grid.col_row(land))))
        self.assertGreater(min(r, g), b)
        # The panel: dark, with the title in gold somewhere along its title line.
        self.assertTrue(all(v < 40 for v in self.px(card.WIDTH - 10, 10)))
        title_row = [self.px(x, 230) for x in range(card.PANEL_X + 10, card.WIDTH - 10)]
        self.assertTrue(any(r > 200 and g > 170 and b < 170 for r, g, b in title_row))


if __name__ == "__main__":
    unittest.main()
