"""Reservoirs week by week: cleaning the Boletín Hidrológico's table (pipeline/sources/es/embalses.py), the Wikidata
reservoirs and dams (pipeline/sources/es/presas_wikidata.py), placing the reservoirs and hexes
(pipeline/build/spain_embalses.py) and the check of the files it writes."""

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from pipeline.build import spain_embalses as B
from pipeline.core.geo import Shape, lonlat_scale
from pipeline.core.hexgrid import HexGrid
from pipeline.sources.es import embalses as E
from pipeline.sources.es import presas_wikidata as W

T0 = date(1988, 1, 5)


def week(k: int) -> date:
    return T0 + timedelta(days=7 * k)


def square(x0, y0, x1, y1):
    return [[(x0, y0), (x1, y0), (x1, y1), (x0, y1)]]


KX, KY = lonlat_scale(40.0)


def deg(x_km: float, y_km: float) -> tuple[float, float]:
    """A point x_km east and y_km north of (0°, 40°N) in lon/lat, flat-earth (core.geo.flat_km's scale)."""
    return round(x_km / KX, 5), round(40.0 + y_km / KY, 5)


def km(lon: float, lat: float) -> tuple[float, float]:
    """deg's inverse: the projection of the tests, map km from (0°, 40°N)."""
    return lon * KX, (lat - 40.0) * KY


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

    def test_capacity_report(self):
        res = E.series([("S", "Fuensanta", week(0), "210,00", "60,00", 1), ("S", "Fuensanta", week(1), "203,00", "70,00", 1),
                        ("S", "Guístolas", week(0), "5,00", "8,00", 0), ("S", "Guístolas", week(1), "5,00", "6,00", 0),
                        ("S", "Lanuza", week(1), "17,00", "18,00", 0)])["reservoirs"]
        self.assertEqual(E.capacity_report(res), {"changing": 1, "runs": 4, "over": 3, "over_reservoirs": 2,
                                                  "top": [("Guístolas", 2), ("Lanuza", 1)]})

    def test_layer_week(self):
        dates = [week(k).isoformat() for k in range(3)]
        self.assertEqual(E.layer_week(dates, dates[-1], "DDHH"), (2, None))
        k, note = E.layer_week(dates, dates[1], "DDHH")  # the layer still on last week: compared there
        self.assertEqual(k, 1)
        self.assertIn(f"DDHH is for {dates[1]} and the database ends on {dates[2]}: compared on that week", note)
        k, note = E.layer_week(dates, week(3).isoformat(), "DDHH")  # a week ahead of the zip: noted, not compared
        self.assertIsNone(k)
        self.assertIn("not compared", note)
        with self.assertRaises(ValueError):
            E.layer_week(dates, week(4).isoformat(), "DDHH")

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

    def test_display_name(self):
        cases = {"Breña, La": "La Breña", "Breña II, La": "La Breña II", "Vellón,El-(Pedrezuela)": "El Vellón (Pedrezuela)",
                 "Loteta (La)": "La Loteta", "Parras (Las)": "Las Parras", "Malpasillo ( Jauja )": "Malpasillo (Jauja)",
                 "Porma-(Juan Benet)": "Porma (Juan Benet)", "Agavanzal, Nª Sª de": "Nª Sª de Agavanzal",
                 "Peares, Os": "Os Peares", "Negro (Lago)": "Negro (Lago)", "Jerte - Plasencia": "Jerte - Plasencia",
                 "Torrejón (Tajo - Tietar)": "Torrejón (Tajo - Tietar)", "Alcántara": "Alcántara"}
        self.assertEqual({k: B.display_name(k) for k in cases}, cases)

    def test_match_wikidata(self):
        basin = Shape(square(0, 0, 100, 100))
        items = B.wikidata_index([
            {"id": "Q1", "names": ["Embalse de La Breña"], "points": [deg(50, 50)], "dam": False},
            {"id": "Q2", "names": ["presa de la Breña"], "points": [deg(51, 50.5)], "dam": True},
            {"id": "Q3", "names": ["Embalse de Tort"], "points": [deg(20, 20)], "dam": False},
            {"id": "Q4", "names": ["Lago Tort"], "points": [deg(25, 20)], "dam": False},  # 5 km from Q3: two places
            {"id": "Q5", "names": ["Embalse del Mar"], "points": [deg(150, 50)], "dam": False},  # in another basin
            {"id": "Q6", "names": ["Escarra"], "points": [deg(101.5, 50)], "dam": False},  # 1.5 km outside the basin
            {"id": "Q7", "names": ["Embalse de Yesa"], "points": [deg(60, 60)], "dam": False},
            {"id": "Q8", "names": ["Presa de Yesa"], "points": [deg(62.2, 60)], "dam": True},  # 2.2 km: the dam wins
            {"id": "Q9", "names": ["Embalse de Sau"], "points": [deg(70, 70)], "dam": True},
            {"id": "Q10", "names": ["Presa de Sau"], "points": [deg(73, 70)], "dam": True},  # two dams: none
        ])
        got = B.match_wikidata("Breña, La", basin, items, km)
        self.assertEqual(got["qids"], ["Q1", "Q2"])
        self.assertEqual(got["rule"], "same")
        self.assertAlmostEqual(got["lon"], (deg(50, 50)[0] + deg(51, 50.5)[0]) / 2, places=5)
        self.assertIsNone(B.match_wikidata("Tort (Lago)", basin, items, km))
        self.assertIsNone(B.match_wikidata("Mar (Lago)", basin, items, km))
        self.assertIsNone(B.match_wikidata("Nadie", basin, items, km))
        self.assertEqual(B.match_wikidata("Escarra", basin, items, km)["qids"], ["Q6"])
        yesa = B.match_wikidata("Yesa", basin, items, km)
        self.assertEqual((yesa["qids"], yesa["rule"], (yesa["lon"], yesa["lat"])), (["Q8"], "dam", deg(62.2, 60)))
        self.assertIsNone(B.match_wikidata("Sau", basin, items, km))

    def test_unplaced_share(self):
        res = [{"actual": [90, 80], "capacity": [[0, 100]]}, {"actual": [5, None], "capacity": [[0, 10]]},
               {"actual": [None, 30], "capacity": [[1, 50]]}]
        got = B.unplaced_share(res, {1}, 2)
        self.assertAlmostEqual(got["capacity"][0], 10 / 110)
        self.assertAlmostEqual(got["actual"][0], 5 / 95)
        self.assertEqual((got["capacity"][1], got["actual"][1]), (0, 0))

    def test_basin_cells(self):
        grid = HexGrid(5.0, 30, 12)
        # owner: province 0 (peninsula) everywhere but the last 3 columns (province 1, the Balearics)
        codes = ["45", "07"]
        owner = [-1 if c < 2 else (1 if c >= 27 else 0) for i in range(grid.size) for c in [i % grid.cols]]
        shapes = [Shape(square(0, -10, 60, 200)), Shape(square(60, -10, 120, 200))]
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


TABLE = "T_Datos Embalses 1988-2026"


class FakeDb:
    """What BoletinHidrologico.process reads from core.mdb.Jet4: one table, its rows and its recorded row count."""

    def __init__(self, rows, count=None):
        self._rows, self._count = rows, len(rows) if count is None else count

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def tables(self):
        return {TABLE: 1, "f_Data": 2}

    def rows(self, table, cols):
        for basin, name, day, total, actual, flag in self._rows:
            yield {"AMBITO_NOMBRE": basin, "EMBALSE_NOMBRE": name, "FECHA": datetime(day.year, day.month, day.day),
                   "AGUA_TOTAL": total, "AGUA_ACTUAL": actual, "ELECTRICO_FLAG": flag}

    def row_count(self, table):
        return self._count


MANIFEST = {E.ZIP_FILE: {"retrieved": "2026-11-27T10:00:00+00:00", "sha256": "a"}}
ROWS = [("Segura", "Fuensanta", week(0), "210,00", "60,00", 1), ("Segura", "Fuensanta", week(1), "210,00", "61,00", 1),
        ("Segura", "Cenajo", week(1), "437,00", "190,00", 1)]


class ProcessTest(unittest.TestCase):
    """BoletinHidrologico.process on a fake table and the two map layers written to a temporary raw folder."""

    def run_process(self, rows=ROWS, count=None, basin="Segura", stored=251, pct=100 * 251 / 647, day=None):
        day = day or week(1)
        stamp = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp() * 1000)
        points = [{"attributes": {"embalse_nombre": n, "ambito_nombre": "Segura", "ambito_id": 7, "agua_total": c,
                                  "agua_actual": a, "Fecha_str": day.strftime("%d%m%Y")}, "geometry": {"x": -1.9, "y": 38.1}}
                  for n, c, a in (("Fuensanta", 210, 61), ("Cenajo", 437, 190))]
        basins = [{"attributes": {"NOM_DEMAR": basin, "Agua": stored, "Porc_Agua_Cuenca": pct, "Fecha": stamp},
                   "geometry": {"rings": [[[-2.0, 38.0], [-1.0, 38.0], [-1.0, 39.0], [-2.0, 38.0]]]}}]
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()) as log, \
                mock.patch.object(E.BoletinHidrologico, "raw_dir", new_callable=mock.PropertyMock, return_value=Path(d)), \
                mock.patch.object(E.BoletinHidrologico, "mdb", return_value=FakeDb(rows, count)), \
                mock.patch.object(E, "read_manifest", return_value=MANIFEST):
            for file, feats in ((E.POINTS_FILE, points), (E.BASINS_FILE, basins)):
                (Path(d) / file).write_text(json.dumps({"features": feats}))
                (Path(d) / file.replace(".json", "_count.json")).write_text(json.dumps({"count": len(feats)}))
            out = E.BoletinHidrologico().process()
        return out, log.getvalue()

    def test_process(self):
        out, log = self.run_process()
        self.assertEqual((out["table"], out["dates"], out["dropped"]), (TABLE, [week(0).isoformat(), week(1).isoformat()], 0))
        self.assertEqual([(r["name"], r["first"], r["last"]) for r in out["reservoirs"]], [("Fuensanta", 0, 1), ("Cenajo", 1, 1)])
        self.assertEqual([(p["name"], p["date"]) for p in out["points"]], [("Fuensanta", week(1).isoformat()),
                                                                          ("Cenajo", week(1).isoformat())])
        self.assertEqual((out["basins"][0]["name"], out["basins"][0]["date"]), ("Segura", week(1).isoformat()))
        self.assertIn("3 rows, 2 reservoirs, 2 weeks", log)
        self.assertIn("capacity: 0 reservoirs change it (2 runs in all); 0 weekly values above it, in 0 reservoirs", log)
        self.assertNotIn("NOTE", log)

    def test_the_basin_layer_must_be_the_databases_sums(self):
        self.run_process(stored=251.4)  # within 0.5 hm³
        with self.assertRaisesRegex(ValueError, "DDHH Segura .* but the database sums 251 of 647"):
            self.run_process(stored=252)

    def test_a_layer_a_week_off_is_noted_and_more_is_an_error(self):
        _, log = self.run_process(stored=999, day=week(2))  # a week after the zip: not compared, said
        self.assertIn(f"NOTE: DDHH is for {week(2).isoformat()} and the database ends on {week(1).isoformat()}: "
                      "not compared", log)
        _, log = self.run_process(day=week(0), stored=60, pct=100 * 60 / 210)  # still on the week before: compared there
        self.assertIn("compared on that week", log)
        with self.assertRaisesRegex(ValueError, "DDHH Segura"):
            self.run_process(day=week(0), stored=251)  # that week holds 60 hm³
        with self.assertRaisesRegex(ValueError, "more than a week apart"):
            self.run_process(day=week(3))

    def test_basins_must_be_the_databases_ambitos(self):
        with self.assertRaisesRegex(ValueError, "are not the database's ámbitos"):
            self.run_process(basin="Segura y Mar Menor")

    def test_every_row_the_table_holds_is_read(self):
        with self.assertRaisesRegex(ValueError, "read 3 rows of the 4"):
            self.run_process(count=4)

    def test_the_database_is_extracted_again_when_the_zip_changes(self):
        def zipped(folder: Path, members: dict):
            with zipfile.ZipFile(folder / E.ZIP_FILE, "w") as z:
                for name, data in members.items():
                    z.writestr(name, data)

        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(E.BoletinHidrologico, "raw_dir", new_callable=mock.PropertyMock, return_value=Path(d)), \
                mock.patch.object(E, "Jet4", side_effect=lambda path: Path(path).read_bytes()), \
                mock.patch.object(E, "read_manifest") as manifest:
            src = E.BoletinHidrologico()
            manifest.return_value = {E.ZIP_FILE: {"sha256": "a"}}
            zipped(Path(d), {"BD-Embalses.mdb": b"one"})
            self.assertEqual(src.mdb(), b"one")
            zipped(Path(d), {"BD-Embalses.mdb": b"two"})
            self.assertEqual(src.mdb(), b"one", "same sha256: the extracted file is kept")
            manifest.return_value = {E.ZIP_FILE: {"sha256": "b"}}
            self.assertEqual(src.mdb(), b"two")
            self.assertEqual((Path(d) / f"{E.MDB_FILE}.sha256").read_text(), "b")
            zipped(Path(d), {"a.mdb": b"1", "b.MDB": b"2"})
            manifest.return_value = {E.ZIP_FILE: {"sha256": "c"}}
            with self.assertRaisesRegex(ValueError, "2 .mdb members"):
                src.mdb()


class WikidataTest(unittest.TestCase):
    def test_one_item_per_qid_with_its_names_points_and_whether_it_is_a_dam(self):
        item = lambda q, cls, coord, name: {"s": {"value": f"http://www.wikidata.org/entity/{q}"},
                                            "class": {"value": f"http://www.wikidata.org/entity/{cls}"},
                                            "coord": {"value": coord}, "name": {"value": name}}
        rows = [item("Q20", W.RESERVOIR, "Point(-5.05 37.84)", "Embalse de la Breña"),
                item("Q20", W.DAM, "Point(-5.05 37.84)", "Embalse de la Breña"),  # a reservoir and a dam, one row each
                item("Q20", W.RESERVOIR, "Point(-5.05 37.84)", " embalse de La Breña "),
                item("Q20", W.RESERVOIR, "Point(-5.04 37.82)", "Embalse de la Breña"),
                item("Q3", W.RESERVOIR, "Point(-1.0 42.0)", "Pantà de Sau"),
                item("Q4", W.DAM, "not a point", "Presa de Nadie")]
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(W.WikidataPresas, "raw_dir", new_callable=mock.PropertyMock, return_value=Path(d)), \
                mock.patch("pipeline.sources.es.playas.read_manifest", return_value={W.FILE: {"retrieved": "2026-11-27T20:19"}}):
            (Path(d) / W.FILE).write_text(json.dumps({"results": {"bindings": rows}}))
            out = W.WikidataPresas().process()
        self.assertEqual(out["vintage"], "Wikidata, 2026-11-27")
        self.assertEqual(out["items"], [
            {"id": "Q3", "names": ["Pantà de Sau"], "points": [[-1.0, 42.0]], "dam": False},
            {"id": "Q20", "names": ["Embalse de la Breña", "embalse de La Breña"], "points": [[-5.05, 37.84], [-5.04, 37.82]],
             "dam": True}])


def world_and_boletin(points: list[dict]):
    """A 4 × 4 grid of land in province 45, one basin square around it and one reservoir, A, reporting both weeks."""
    world = {"grid": {"radius": 5.0, "cols": 4, "rows": 4}, "owner": [0] * 16, "states": ["45"]}
    ring = [deg(-10, -10), deg(40, -10), deg(40, 40), deg(-10, 40)]
    src = {"dates": [week(0).isoformat(), week(1).isoformat()], "points": points,
           "basins": [{"name": "Segura", "rings": [ring]}],
           "reservoirs": [{"basin": "Segura", "name": "Breña, La", "use": "consuntivo", "actual": [5, 6],
                           "capacity": [[0, 10]], "first": 0, "last": 1}]}
    return world, src


def interim(**docs):
    return lambda name: docs[name]


class BuildTest(unittest.TestCase):
    def build(self, points):
        world, src = world_and_boletin(points)
        written = {}
        with mock.patch.object(B, "load_interim", side_effect=interim(_world=world, boletin_hidrologico=src,
                                                                      wikidata_presas={"items": []})), \
                mock.patch.object(B, "active", return_value=mock.Mock(world_projection=lambda w: km)), \
                mock.patch.object(B, "write_web", side_effect=lambda f, doc: written.setdefault(f, doc)), \
                contextlib.redirect_stdout(io.StringIO()):
            B.build()
        return written

    def test_a_reservoir_of_the_latest_week_needs_its_map_point(self):
        with self.assertRaisesRegex(ValueError, "Breña, La \\(Segura\\) reports in the latest week"):
            self.build([])
        lon, lat = deg(10, 10)
        doc = self.build([{"basin": "Segura", "name": "Breña, La", "lon": lon, "lat": lat, "actual": 6}])["embalses.json"]
        r = doc["reservoirs"][0]
        self.assertEqual((r["name"], r["boletin_name"], r["placed"], r["actual"], r["capacity"]),
                         ("La Breña", "Breña, La", "boletin", 6, 10))
        self.assertEqual(doc["basins"][0]["actual"], [5, 6])


class CheckTest(unittest.TestCase):
    def write(self, folder: Path, basin_actual, placed=None):
        dates = [week(k).isoformat() for k in range(2)]
        res = [{"name": "A", "basin": 0, "use": "consuntivo", "lon": None, "lat": None, "x": None, "y": None, "cell": None,
                "placed": None, "first": 0, "last": 1, "capacity": 10, "actual": 6}]
        if placed:
            res[0].update(placed=placed[0], lon=placed[1][0], lat=placed[1][1])
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

    def check_against(self, points, placed=("boletin", deg(10, 10))):
        world, src = world_and_boletin(points)
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(B, "load_interim", side_effect=interim(_world=world, boletin_hidrologico=src)), \
                mock.patch.object(B, "active", return_value=mock.Mock(world_projection=lambda w: km)):
            self.write(Path(d), [5, 6], placed)
            return B.check(d)

    def test_the_boletin_map_and_the_basins(self):
        at = lambda day, actual: [{"date": day.isoformat(), "actual": actual}]
        self.assertEqual(self.check_against(at(week(1), 6))[-1][0], "PASS")
        self.assertEqual(self.check_against(at(week(1), 6.4))[-1][0], "PASS")  # within 0.5 hm³
        got = self.check_against(at(week(1), 7))[-1]
        self.assertEqual(got[0], "FAIL")
        self.assertIn(f"week {week(1).isoformat()}: 6 hm³, the Boletín map 7 hm³", got[1])
        got = self.check_against(at(week(0), 5))  # the map still on the week before: compared there, noted
        self.assertEqual([lvl for lvl, _ in got], ["NOTE", "PASS"])
        self.assertIn("compared on that week", got[0][1])
        got = self.check_against(at(week(2), 99))  # a week ahead: noted, not compared
        self.assertEqual([lvl for lvl, _ in got], ["NOTE", "PASS"])
        self.assertIn("not compared", got[0][1])
        got = self.check_against(at(week(3), 6))[-1]
        self.assertEqual(got[0], "FAIL")
        self.assertIn("more than a week apart", got[1])

    def test_a_placed_point_outside_its_basin_fails(self):
        points = [{"date": week(1).isoformat(), "actual": 6}]
        self.assertEqual(self.check_against(points, ("wikidata", deg(41.5, 10)))[-1][0], "PASS")  # 1.5 km out
        got = self.check_against(points, ("wikidata", deg(45, 10)))[-1]
        self.assertEqual(got[0], "FAIL")
        self.assertIn("1 points outside their basin (A)", got[1])


if __name__ == "__main__":
    unittest.main()
