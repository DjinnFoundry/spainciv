"""Reservoirs week by week: cleaning the Boletín Hidrológico's table (pipeline/sources/es/embalses.py), placing its
reservoirs and hexes (pipeline/build/spain_embalses.py) and the check of the files it writes."""

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from pipeline.build import spain_embalses as B
from pipeline.core.hexgrid import HexGrid
from pipeline.sources.es import embalses as E

T0 = date(1988, 1, 5)


def week(k: int) -> date:
    return T0 + timedelta(days=7 * k)


def square(x0, y0, x1, y1):
    return [[(x0, y0), (x1, y0), (x1, y1), (x0, y1)]]


class CleaningTest(unittest.TestCase):
    def test_hm3_numbers(self):
        self.assertEqual([E.parse_hm3(v) for v in ("91,00", "8", "0,00", "", None, "  ")], [91, 8, 0, None, None, None])
        self.assertEqual(E.parse_hm3("12,50"), 12.5)
        for bad in ("91.00", "1.091,00", "-3,00", "n/d", "9,"):
            with self.assertRaises(ValueError, msg=bad):
                E.parse_hm3(bad)

    def test_series(self):
        rows = [
            ("Segura", "Fuensanta", date(1987, 12, 29), "210,00", "50,00", 1),  # before the series: dropped
            ("Segura", "Fuensanta", week(0), "210,00", "60,00", 1),
            ("Segura", "Fuensanta", week(1), "210,00", "", 1),  # empty: reports nothing that week
            ("Segura", "Fuensanta", week(2), "210,00", "61,00", 1),
            ("Segura", "Fuensanta", week(4), "203,00", "70,00", 0),  # week 3 missing; new capacity; latest flag 0
            ("Segura", "Guístolas", week(3), "5,00", "8,00", 0),  # above capacity, kept as written
            ("Ebro", "Ebro", week(1), "540,00", "300,00", 1),
        ]
        out = E.series(rows)
        self.assertEqual(out["dates"], [week(k).isoformat() for k in range(5)])
        self.assertEqual(out["dropped"], 1)
        fu, gu, eb = out["reservoirs"]
        self.assertEqual((fu["name"], fu["use"], fu["actual"], fu["capacity"], fu["first"], fu["last"]),
                         ("Fuensanta", "consuntivo", [60, None, 61, None, 70], [[0, 210], [4, 203]], 0, 4))
        self.assertEqual((gu["actual"], gu["capacity"], gu["first"], gu["last"]), ([None, None, None, 8, None], [[3, 5]], 3, 3))
        self.assertEqual(eb["use"], "hidroelectrico")
        totals = E.basin_totals(out["reservoirs"], ["Segura", "Ebro"], 5)
        self.assertEqual(totals["Segura"], {"actual": [60, None, 61, 8, 70], "capacity": [210, None, 210, 5, 203]})
        self.assertEqual(totals["Ebro"], {"actual": [None, 300, None, None, None], "capacity": [None, 540, None, None, None]})

    def test_series_rejects_gaps_strays_and_twins(self):
        with self.assertRaises(ValueError):  # a week with no row at all
            E.series([("A", "a", week(0), "1", "1", 0), ("A", "a", week(2), "1", "1", 0)])
        with self.assertRaises(ValueError):  # not a Tuesday
            E.series([("A", "a", week(0) + timedelta(days=1), "1", "1", 0)])
        with self.assertRaises(ValueError):  # two rows for one reservoir and week
            E.series([("A", "a", week(0), "1", "1", 0), ("A", "a", week(0), "2", "1", 0)])

    def test_capacity_runs(self):
        runs = [[0, 210], [4, 203]]
        self.assertEqual([E.capacity_at(runs, k) for k in (0, 3, 4, 9)], [210, 210, 203, 203])
        self.assertIsNone(E.capacity_at([[2, 5]], 1))

    def test_basin_sums_are_the_boletins_figures(self):
        # The Boletín's DDHH layer for Segura on 24-11-2026: 522 hm³, 45.79 %; the reservoirs' rows must sum to it.
        rows = [("Segura", name, week(0), cap, act, 0) for name, cap, act in
                (("Fuensanta", "210,00", "105,00"), ("Cenajo", "437,00", "190,00"), ("Otros", "493,00", "227,00"))]
        s = E.basin_totals(E.series(rows)["reservoirs"], ["Segura"], 1)["Segura"]
        self.assertEqual((s["actual"][0], s["capacity"][0]), (522, 1140))
        self.assertAlmostEqual(100 * s["actual"][0] / s["capacity"][0], 45.79, places=2)

    def test_arcgis_answers_must_be_complete(self):
        feats = [{"attributes": {}}] * 3
        self.assertEqual(len(E.check_layer({"features": feats}, {"count": 3}, "x")), 3)
        for doc, count in (({"features": feats, "exceededTransferLimit": True}, {"count": 3}),
                           ({"features": feats}, {"count": 4}), ({"error": {"code": 400}}, {"count": 3})):
            with self.assertRaises(ValueError):
                E.check_layer(doc, count, "x")


class PlacingTest(unittest.TestCase):
    def test_name_key(self):
        same = ["Breña, La", "Embalse de La Breña", "embalse de la Breña", "Presa de la Breña"]
        self.assertEqual({B.name_key(n) for n in same}, {"brena"})
        self.assertEqual(B.name_key("Negro (Lago)"), B.name_key("Lago Negro"))
        self.assertEqual(B.name_key("Malpasillo ( Jauja )"), "malpasillo jauja")
        self.assertEqual(B.name_key("Derivación Retortillo"), B.name_key("Presa y embalse de Derivación Del Retortillo"))
        self.assertEqual(B.name_key("Pantà de Sau"), B.name_key("Embassament de Sau"))
        self.assertNotEqual(B.name_key("Retortillo"), B.name_key("Derivación Retortillo"))  # no fuzzy matching

    def test_match_wikidata(self):
        ident = lambda lon, lat: (lon, lat)  # km in, km out
        shapes = [square(0, 0, 100, 100), square(100, 0, 200, 100)]
        edges = B.Edges(shapes, B.WIKIDATA_KM)
        items = B.wikidata_index([
            {"id": "Q1", "names": ["Embalse de La Breña"], "points": [[50, 50]]},
            {"id": "Q2", "names": ["presa de la Breña"], "points": [[51, 50.5]]},
            {"id": "Q3", "names": ["Embalse de Tort"], "points": [[20, 20]]},
            {"id": "Q4", "names": ["Lago Tort"], "points": [[25, 20]]},  # 5 km from Q3: two places
            {"id": "Q5", "names": ["Embalse del Mar"], "points": [[150, 50]]},  # in the other basin
            {"id": "Q6", "names": ["Escarra"], "points": [[101.5, 50]]},  # 1.5 km outside basin 0
        ])
        got = B.match_wikidata("Breña, La", 0, items, shapes[0], edges, ident)
        self.assertEqual(got, {"lon": 50.5, "lat": 50.25, "qids": ["Q1", "Q2"]})
        self.assertIsNone(B.match_wikidata("Tort (Lago)", 0, items, shapes[0], edges, ident))
        self.assertIsNone(B.match_wikidata("Mar (Lago)", 0, items, shapes[0], edges, ident))
        self.assertIsNone(B.match_wikidata("Nadie", 0, items, shapes[0], edges, ident))
        self.assertEqual(B.match_wikidata("Escarra", 0, items, shapes[0], edges, ident)["qids"], ["Q6"])

    def test_basin_cells(self):
        grid = HexGrid(5.0, 30, 12)
        # owner: province 0 (peninsula) everywhere but the last 3 columns (province 1, the Balearics)
        codes = ["45", "07"]
        owner = [-1 if c < 2 else (1 if c >= 27 else 0) for i in range(grid.size) for c in [i % grid.cols]]
        shapes = [square(0, -10, 60, 200), square(60, -10, 120, 200)]
        cells, stats = B.basin_cells(grid, owner, codes, shapes, snap_km=10)
        x = lambda c: grid.center(*grid.col_row(c))[0]
        for c in range(grid.size):
            if owner[c] < 0 or codes[owner[c]] == "07":
                self.assertEqual(cells[c], -1)
            elif x(c) < 60:
                self.assertEqual(cells[c], 0)
            elif x(c) < 120:
                self.assertEqual(cells[c], 1)
            elif x(c) <= 130:
                self.assertEqual(cells[c], 1, "a coastal hex within 10 km joins the nearest basin")
            else:
                self.assertEqual(cells[c], -1, "further out, none")
        self.assertGreater(stats["snapped"], 0)
        self.assertGreater(stats["outside"], 0)
        self.assertEqual(stats["off"], sum(1 for o in owner if o == 1))


class CheckTest(unittest.TestCase):
    def write(self, folder: Path, basin_actual):
        dates = [week(k).isoformat() for k in range(2)]
        res = [{"name": "A", "basin": 0, "use": "consuntivo", "lon": None, "lat": None, "x": None, "y": None, "cell": None,
                "placed": None, "first": 0, "last": 1, "capacity": 10, "actual": 6}]
        (folder / "embalses.json").write_text(json.dumps({"vintage": dates[-1], "provisional": True, "dates": dates,
            "basins": [{"name": "Segura", "cells": [], "actual": basin_actual, "capacity": [10, 10]}], "reservoirs": res}))
        (folder / "embalses_semanas.json").write_text(json.dumps({"vintage": dates[-1], "actual": [[5], [6]],
                                                                  "capacity": [[[0, 10]]]}))

    def test_check_passes_and_catches_a_broken_sum(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(B, "load_interim", side_effect=FileNotFoundError):
            self.write(Path(d), [5, 6])
            self.assertEqual([lvl for lvl, _ in B.check(d)], ["NOTE", "PASS"])
            self.write(Path(d), [5, 7])
            self.assertEqual(B.check(d)[-1][0], "FAIL")
            self.assertEqual(B.check(Path(d) / "nothing"), [])


if __name__ == "__main__":
    unittest.main()
