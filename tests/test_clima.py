"""The climate of the month (Spain): AEMET's sources (province normals, WMO station normals, ROCIO grids) and
clima.json (pipeline/build/spain_clima.py) with its check."""

import json
import math
import tempfile
import unittest
from array import array
from pathlib import Path
from unittest import mock

from pipeline.build import spain_clima as C
from pipeline.core.hexgrid import HexGrid
from pipeline.sources.es import aemet_normales as N
from pipeline.sources.es import aemet_rocio as R
from pipeline.sources.es import omm_normales as O

# Trimmed from NCEI's BURGOSVILLAFRIA_8075.csv: its real rows, fewer blocks (and a MaxMon row to skip).
BURGOS_CSV = "\ufeff" + "\r\n".join([
    "World Meteorological Organization Climate Normals for 1991-2020,,,,,,,,,,,,,,,,",
    "Country_Name,Spain,,,,,,,,,,,,,,,",
    "Station_Name,BURGOS/VILLAFRÍA,,,,,,,,,,,,,,,",
    ",,,,,,,,,,,,,,,,",
    "WMO_Number,Latitude,Longitude,Station_Height,,,,,,,,,,,,,,",
    "8075,42|21|25|N,003|37|13|W,891.000000,,,,,,,,,,,,,",
    "Parameter_Code,Parameter_Name,Units,,,,,,,,,,,,,,",
    "1,Precipitation_Total,mm,,,,,,,,,,,,,,",
    "WMO_Number,Parameter_Code,Calculation_Name,Calculation_Code,January,February,March,April,May,June,July,August,"
    "September,October,November,December,Annual",
    "8075,1,Sum,4,47.2,35.0,44.1,59.9,57.3,43.0,24.1,18.8,33.4,62.8,63.3,57.4,546.3",
    "8075,1,MaxMon,19,145.3,83.5,147.1,126.8,194.0,146.0,100.8,63.8,85.0,131.8,151.5,166.4,",
    "8075,3,Mean,1,7.6,9.4,13.1,15.2,19.3,24.3,27.8,27.9,23.3,17.7,11.2,8.4,17.1",
    "8075,4,Mean,1,-0.4,-0.7,1.2,2.9,5.9,9.3,11.4,11.5,8.7,6.0,2.5,0.3,4.9",
    "8075,5,Mean,1,3.6,4.4,7.2,9.1,12.6,16.8,19.6,19.7,16.0,11.8,6.8,4.3,11.0",
    "8075,8,Sum,4,85.4,120.7,176.0,192.6,240.3,278.8,327.4,305.9,229.7,163.1,94.9,82.7,2297.5",
    "8075,15,Count,5,16.6,16.7,11.2,5.6,0.8,0.0,0.0,0.0,0.1,1.5,7.5,14.6,74.6",
])


class WmoStationTest(unittest.TestCase):
    def test_burgos_blocks_and_calculations(self):
        s = O.parse_station(BURGOS_CSV)
        self.assertEqual((s["wmo"], s["name"], s["alt"]), ("08075", "BURGOS/VILLAFRÍA", 891))
        self.assertAlmostEqual(s["lat"], 42 + 21 / 60 + 25 / 3600, places=4)
        self.assertAlmostEqual(s["lon"], -(3 + 37 / 60 + 13 / 3600), places=4)
        self.assertEqual(s["prec"][0], 47.2)  # the Sum row, not MaxMon
        self.assertEqual(s["tmean"][0], 3.6)  # the Mean row
        self.assertEqual(s["tmin"][0], -0.4)
        self.assertEqual(s["frost_lt0"][0], 16.6)  # Count
        self.assertEqual(round(sum(s["sun"]), 1), 2297.5)

    def test_missing_sunshine_is_none(self):
        text = BURGOS_CSV.replace("8075,8,Sum,4,85.4,", "8075,8,Sum,4,-9999,")
        self.assertIsNone(O.parse_station(text)["sun"])
        no_block = "\r\n".join(line for line in BURGOS_CSV.split("\r\n") if not line.startswith("8075,8,"))
        self.assertIsNone(O.parse_station(no_block)["sun"])

    def test_aemet_page_coordinates_win_over_a_wrong_header(self):
        wmo = O.parse_station(BURGOS_CSV.replace("003|37|13|W", "003|37|53|W"))  # a Murcia-like wrong longitude
        page = O.parse_page("<p><b>Estación</b>:&nbsp;Burgos Aeropuerto&nbsp;-&nbsp;<b>Periodo</b> :&nbsp;1981-2010"
                            "&nbsp;-&nbsp;Altitud (m) :&nbsp;891&nbsp;</p><p>Latitud :&nbsp;42° 21' 25'' N&nbsp;-&nbsp;"
                            "Longitud :&nbsp;3° 37' 13'' O</p>")
        s = O.station(wmo, page, {"aemet": "2331", "province": "09"})
        self.assertEqual((s["name"], s["coords"], s["aemet"], s["province"]), ("Burgos Aeropuerto", "aemet", "2331", "09"))
        self.assertAlmostEqual(s["lon"], -(3 + 37 / 60 + 13 / 3600), places=4)
        header = O.station(wmo, None, {"aemet": None, "province": "09", "name": None})
        self.assertEqual((header["coords"], header["name"], header["lon"]), ("wmo", "Burgos/Villafría", wmo["lon"]))

    def test_a_station_without_an_aemet_page_takes_the_tables_name_or_a_clean_header(self):
        rota = O.parse_station(BURGOS_CSV.replace("BURGOS/VILLAFRÍA", "ROTA B.N.OBSERVATORIO'"))
        named = O.station(rota, None, {"aemet": None, "province": "11", "name": "Rota, Base Naval"})
        self.assertEqual(named["name"], "Rota, Base Naval")
        self.assertEqual(O.station(rota, None, {"aemet": None, "province": "11", "name": None})["name"],
                         "Rota B.N.Observatorio")  # no stray quote, not in capitals

    def test_the_word_estacion_is_dropped_from_an_aemet_page_name(self):
        page = ("<p><b>Estación</b>:&nbsp;Estación de Tortosa (Roquetes)&nbsp;-&nbsp;<b>Periodo</b> :&nbsp;1981-2010"
                "&nbsp;-&nbsp;Altitud (m) :&nbsp;50&nbsp;</p><p>Latitud :&nbsp;40° 49' 13'' N&nbsp;-&nbsp;"
                "Longitud :&nbsp;0° 29' 29'' E</p>")
        self.assertEqual(O.parse_page(page)["name"], "Tortosa (Roquetes)")

    def test_a_station_without_a_required_parameter_fails(self):
        text = "\r\n".join(line for line in BURGOS_CSV.split("\r\n") if not line.startswith("8075,15,"))
        with self.assertRaisesRegex(ValueError, "frost_lt0"):
            O.station(O.parse_station(text), None, {"aemet": None, "province": "09"})

    def test_committed_table_lists_83_stations_with_provinces(self):
        table = O.read_table()
        self.assertEqual(len(table), 83)
        self.assertEqual(table["08430"], {"aemet": "7178I", "province": "30", "name": None})  # Murcia: its header is wrong
        self.assertEqual(table["08449"], {"aemet": None, "province": "11", "name": "Rota, Base Naval"})  # no AEMET page
        self.assertEqual([w for w, r in table.items() if r["name"]], ["08449"])  # only a station without a page
        self.assertTrue(all(len(r["province"]) == 2 for r in table.values()))


class ProvinceNormalsTest(unittest.TestCase):
    def csv(self, names, param="Temperatura media"):
        head = "Parámetro;periodo de referencia;región;" + ";".join(N.MONTHS) + ";anual"
        body = [f"{param};1991-2020;{n};" + ";".join(f"{k + m / 10:.1f}" for m in range(12)) + ";9.9"
                for k, n in enumerate(names)]
        return "\r\n".join([head, *body])

    def test_all_52_names_map_to_distinct_ine_codes(self):
        names = list(N.PROVINCE_CODES)
        rows = N.rows(self.csv(names).encode("latin-1").decode("latin-1"))  # the files are Latin-1
        self.assertEqual(rows["CASTELLON/CASTELLÓ"][:2], [names.index("CASTELLON/CASTELLÓ"), names.index("CASTELLON/CASTELLÓ") + 0.1])
        out = N.by_province({p: rows for p in N.PARAMS})
        self.assertEqual(len(out), 52)
        self.assertEqual(sorted(out), [f"{c:02d}" for c in range(1, 53)])
        self.assertEqual(out["46"]["tmed"], rows["VALENCIA/VALÈNCIA"])
        self.assertEqual(out["35"]["prec"], rows["LAS PALMAS"])

    def test_an_unmapped_name_or_a_missing_province_fails(self):
        names = list(N.PROVINCE_CODES)
        with self.assertRaisesRegex(ValueError, "without an INE code"):
            N.by_province({"tmed": N.rows(self.csv(names + ["ATLÁNTIDA"]))})
        with self.assertRaisesRegex(ValueError, "missing"):
            N.by_province({"tmed": N.rows(self.csv(names[1:]))})
        with self.assertRaisesRegex(ValueError, "two rows"):
            N.rows(self.csv(names + names[:1]))
        with self.assertRaisesRegex(ValueError, "not 1991-2020"):
            N.rows(self.csv(names).replace(";1991-2020;", ";1981-2010;"))

    def test_the_real_zip_when_cached(self):
        from pipeline.core.paths import RAW
        path = RAW / "aemet_normales_provincias" / N.ZIP
        if not path.exists():
            self.skipTest("AEMET normals zip not fetched")
        provinces, peninsula, _ = N.read_zip(path)
        self.assertEqual(provinces["09"]["tmed"][0], 3.6)  # BURGOS, January
        self.assertEqual(round(sum(provinces["09"]["prec"]), 1), 658.4)
        self.assertEqual(len(peninsula["tmed"]), 12)


def days_in(year, month):
    from datetime import date
    return (date(year + month // 12, month % 12 + 1, 1) - date(year, month, 1)).days


class RocioNormalsTest(unittest.TestCase):
    """Two points, the years 2019-2020 (2020 is a leap year)."""

    def year(self, year, value, missing_at=None):
        """A year of daily data, 2 points a day: point 0 = value(day), point 1 = 10 + value(day)."""
        from datetime import date, timedelta
        dates = [date(year, 1, 1) + timedelta(days=d) for d in range(366 if year % 4 == 0 else 365)]
        data = array("f")
        for k, d in enumerate(dates):
            v = value(d)
            data.extend([-9999.0 if missing_at == (d, 0) else v, v + 10])
        return data, dates

    def run_years(self, kind, value, missing_at=None, offset=0.0):
        with mock.patch.object(R, "FIRST", 2019), mock.patch.object(R, "LAST", 2020):
            acc = R.Accumulator(2, kind)
            for y in (2019, 2020):
                data, dates = self.year(y, value, missing_at)
                R.flush(acc, data, dates, -9999.0, offset)
            return acc.result()

    def test_leap_february_means_and_rain_sums(self):
        out = self.run_years("tmax", lambda d: float(d.day))
        # February: days 1..28 (2019) and 1..29 (2020): mean of 57 days
        feb = (sum(range(1, 29)) + sum(range(1, 30))) / 57
        self.assertEqual(out["tmax"][1][0], round(feb, 1))
        self.assertEqual(out["tmax"][1][1], round(feb + 10, 1))
        rain = self.run_years("prec", lambda d: 1.0)
        self.assertEqual(rain["prec"][1][0], round((28 + 29) / 2, 1))  # the mean of the two monthly totals
        self.assertEqual(rain["prec"][0][1], 11 * 31)

    def test_frost_counts_minimums_at_or_below_zero(self):
        out = self.run_years("tmin", lambda d: 0.0 if d.day <= 3 else (-0.5 if d.day == 4 else 0.5))
        self.assertEqual(out["frost"][0][0], 4.0)  # three days at 0 and one below
        self.assertEqual(out["frost"][0][1], 0.0)
        self.assertIn("tmin", out)

    def test_kelvin_offset(self):
        out = self.run_years("tmin", lambda d: 273.15, offset=-R.KELVIN)
        self.assertEqual(out["tmin"][0][0], 0.0)
        self.assertEqual(out["frost"][0][0], 31.0)  # 0 °C counts as frost

    def test_a_missing_day_nulls_that_point_month_only(self):
        from datetime import date
        out = self.run_years("tmax", lambda d: 5.0, missing_at=(date(2020, 3, 10), 0))
        self.assertIsNone(out["tmax"][2][0])
        self.assertEqual(out["tmax"][2][1], 15.0)
        self.assertEqual(out["tmax"][3][0], 5.0)

    def test_a_year_missing_fails(self):
        with mock.patch.object(R, "FIRST", 2019), mock.patch.object(R, "LAST", 2020):
            acc = R.Accumulator(2, "tmax")
            data, dates = self.year(2019, lambda d: 1.0)
            R.flush(acc, data, dates, -9999.0, 0.0)
            with self.assertRaisesRegex(ValueError, "2020"):
                acc.result()

    def test_month_spans_and_time_units(self):
        from datetime import date
        self.assertEqual(R.days_since("days since 1990-1-1 06:00:00"), date(1990, 1, 1))
        self.assertEqual(R.days_since("days since 2020-01-01 06:00:00"), date(2020, 1, 1))
        dates = R.step_dates([0.0, 1.0, 31.0], "days since 1991-01-01 06:00:00")
        self.assertEqual(R.month_spans(dates), {(1991, 1): (0, 2), (1991, 2): (2, 3)})
        with self.assertRaisesRegex(ValueError, "consecutive"):
            R.month_spans([date(1991, 1, 1), date(1991, 2, 1), date(1991, 1, 2)])


class Flat:
    """A projection for the tests: lon/lat are map km already."""

    def __call__(self, lon, lat):
        return lon, lat

    def occluded(self, lon, lat):
        return False


GRID = HexGrid(25.0, 12, 9)  # tests/make_hex_fixture.py's grid


def centre(c):
    return GRID.center(*GRID.col_row(c))


def region(points, spacing=5.5, value=lambda k: 1.0):
    return {"lon": [p[0] for p in points], "lat": [p[1] for p in points], "spacing_km": spacing,
            **{v: [[value(k) + m for m in range(12)] for k in range(len(points))] for v in C.GRID_VARS}}


class ClimaBuilderTest(unittest.TestCase):
    def setUp(self):
        self.owner = [0] * GRID.size
        for c in (0, 1, 2):
            self.owner[c] = -1  # sea

    def test_a_hex_takes_the_mean_of_its_points(self):
        x, y = centre(20)
        reg = region([(x - 3, y), (x + 3, y), (x, y + 2)], value=lambda k: [1.0, 2.0, None][k] if k < 2 else 9.0)
        reg["tmax"][2] = [None] * 12  # a null point is left out of the mean
        cells, counts, vals = C.grid_layer({"ibeb": reg}, Flat(), GRID, self.owner)
        k = cells.index(20)
        self.assertEqual(counts[k], 3)
        self.assertEqual(vals["tmax"][0][k], 1.5)
        self.assertEqual(vals["tmin"][0][k], round((1 + 2 + 9) / 3, 1))
        self.assertEqual(vals["tmax"][11][k], 12.5)

    def test_a_land_hex_without_points_takes_one_within_its_spacing(self):
        owner = list(self.owner)
        x, y = centre(30)
        owner[30] = 0
        px, py = centre(31)  # the only point, on the sea hex next door (25 km hexes: a spacing of 50 km reaches it)
        owner[31] = -1
        reg = {"ibeb": region([(px, py)], spacing=50.0)}
        cells, counts, vals = C.grid_layer(reg, Flat(), GRID, owner)
        self.assertIn(30, cells)
        self.assertEqual(counts[cells.index(30)], 0)  # the nearest point
        self.assertEqual(vals["prec"][0][cells.index(30)], 1.0)
        tight = {"ibeb": region([(px, py)], spacing=5.5)}
        cells, _, _ = C.grid_layer(tight, Flat(), GRID, owner)
        self.assertNotIn(30, cells)  # 43 km away: beyond one spacing

    def test_station_takes_its_province_hex_near_a_boundary(self):
        owner = [0] * GRID.size
        owner[41] = 1  # the station's province
        x, y = centre(40)  # the station is on hex 40, of province 0, next to hex 41
        x += 0.4 * GRID.radius
        self.assertEqual(C.station_cell(GRID, owner, x, y, 1), 41)
        self.assertEqual(C.station_cell(GRID, owner, x, y, 0), 40)

    def test_domains_span_all_months(self):
        grid_vals = {"tmax": [[m + 10.0] * 50 for m in range(12)], "tmin": [[m * 1.0] * 50 for m in range(12)],
                     "prec": [[m + 1.0] * 50 for m in range(12)], "frost": [[0.0] * 50 for _ in range(12)]}
        grid_vals["frost"][0] = [5.0] * 50
        d = C.domains(grid_vals, [{"sun": [100.0 + m for m in range(12)]}, {"sun": None}])
        self.assertLessEqual(d["temp"][0], 5.0)
        self.assertGreaterEqual(d["temp"][1], 15.5)  # July's (16 + 5) / 2 … December's (21 + 11) / 2
        self.assertEqual(d["frost"][0], 0)
        self.assertGreaterEqual(d["frost"][1], 5)
        self.assertEqual(d["sun"], [100, 111])  # the stations' lowest and highest: 76 values, none clamped


def good_doc(owner):
    cells = [c for c, o in enumerate(owner) if o >= 0]
    n = len(cells)
    row = lambda v: [v] * n  # noqa: E731
    station = {"wmo": "08075", "aemet": "2331", "name": "Burgos Aeropuerto", "province": "09", "lon": 0, "lat": 0,
               "alt": 891, "coords": "aemet", "cell": cells[0], "tmed": [3.6] * 12, "tmax": [8.9] * 12,
               "tmin": [-1.6] * 12, "prec": [47.2] * 12, "frost": [16.6] * 12, "sun": [190.0] * 12}
    return {"version": 1, "vintage": "1991-2020", "sources": [], "rules": {}, "cells": cells, "points": [1] * n,
            "grid": {"tmax": [row(10.0)] * 12, "tmin": [row(2.0)] * 12, "prec": [row(50.0)] * 12, "frost": [row(1.0)] * 12},
            "provinces": {f"{c:02d}": {"tmed": [6.0] * 12, "tmax": [10.0] * 12, "tmin": [2.0] * 12, "prec": [50.0] * 12}
                          for c in range(1, 53)},
            "peninsular": {"tmed": [6.0] * 12, "prec": [50.0] * 12}, "stations": [station],
            "domains": {"temp": [3, 27], "prec": [3, 180], "frost": [0, 21], "sun": [86, 380]},
            "provinces_period": "1991-2020"}


class ClimaCheckTest(unittest.TestCase):
    owner = [-1, 0, 0, 1, 1, -1]
    world = {"owner": owner, "grid": {"radius": 25.0, "cols": 6, "rows": 1}, "states": [{"fips": "09"}, {"fips": "30"}],
             "country": {"id": "es"}}

    def run_check(self, doc, world=None):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "world.json").write_text(json.dumps(world or self.world))
            if doc is not None:
                (Path(tmp) / "clima.json").write_text(json.dumps(doc))
            return C.check(tmp)

    def levels(self, lines):
        return [level for level, _ in lines]

    def test_missing_file_is_a_note_on_spain_and_nothing_elsewhere(self):
        self.assertEqual(self.levels(self.run_check(None)), ["NOTE"])
        self.assertEqual(self.run_check(None, {**self.world, "country": {"id": "us"}}), [])

    def test_a_good_file_passes(self):
        lines = self.run_check(good_doc(self.owner))
        self.assertNotIn("FAIL", self.levels(lines))
        self.assertNotIn("WARN", self.levels(lines))
        self.assertEqual(self.levels(lines)[-1], "PASS")

    def test_bad_shape_fails(self):
        doc = good_doc(self.owner)
        doc["grid"]["prec"] = doc["grid"]["prec"][:11]
        self.assertEqual(self.levels(self.run_check(doc)), ["FAIL"])
        doc = good_doc(self.owner)
        doc["grid"]["tmax"] = [[60.0] * 4] * 12
        self.assertIn("outside", self.run_check(doc)[0][1])
        doc = good_doc(self.owner)
        del doc["provinces"]["52"]
        self.assertEqual(self.levels(self.run_check(doc)), ["FAIL"])

    def test_a_station_in_the_wrong_province_fails(self):
        doc = good_doc(self.owner)
        doc["stations"][0]["cell"] = 3  # a hex of province 30
        lines = self.run_check(doc)
        self.assertTrue(any(level == "FAIL" and "Burgos" in m for level, m in lines))
        doc["stations"][0]["cell"] = 0  # sea
        self.assertIn("FAIL", self.levels(self.run_check(doc)))

    def test_province_deviation_warns(self):
        doc = good_doc(self.owner)
        doc["provinces"]["09"]["tmax"] = [12.0] * 12  # the grid's 10 °C is 2 °C below
        warn = [m for l, m in self.run_check(doc) if l == "WARN"]
        self.assertTrue(warn and "09" in warn[0] and "30" not in warn[0])
        doc = good_doc(self.owner)
        doc["provinces"]["30"]["prec"] = [40.0] * 12  # rain 25 % above
        self.assertIn("30 (", [m for l, m in self.run_check(doc) if l == "WARN"][0])

    def test_a_deviation_with_some_figures_missing_warns_without_failing(self):
        doc = good_doc(self.owner)
        k = doc["cells"].index(3)  # province 30's hexes: no complete maximum, rain 25 % above AEMET's
        doc["grid"]["tmax"] = [list(r) for r in doc["grid"]["tmax"]]
        doc["grid"]["tmax"][5][k] = doc["grid"]["tmax"][5][k + 1] = None
        doc["provinces"]["30"]["prec"] = [40.0] * 12
        warn = [m for l, m in self.run_check(doc) if l == "WARN"][0]
        self.assertIn("30 (max n/a °C, min +0.0 °C, rain +25%)", warn)

    def test_the_largest_station_gaps_are_listed(self):
        doc = good_doc(self.owner)
        note = [m for l, m in self.run_check(doc) if l == "NOTE" and "gaps" in m]
        self.assertEqual(len(note), 1)
        self.assertIn("Burgos Aeropuerto, month 12: 6.0 vs 3.6 °C", note[0])

    def test_a_world_without_a_grid_fails_rather_than_raising(self):
        world = {k: v for k, v in self.world.items() if k != "grid"}
        lines = self.run_check(good_doc(self.owner), world)
        self.assertEqual(self.levels(lines), ["FAIL"])
        self.assertIn("no grid", lines[0][1])
        self.assertIn("FAIL", self.levels(self.run_check(good_doc(self.owner), {"country": {"id": "es"}})))

    def test_a_file_without_the_province_period_fails(self):
        doc = good_doc(self.owner)
        del doc["provinces_period"]
        self.assertIn("provinces_period", self.run_check(doc)[0][1])


class RealClimaTest(unittest.TestCase):
    def test_built_file_when_present(self):
        from pipeline.countries import COUNTRIES
        path = COUNTRIES["es"].web_data_dir / "clima.json"
        if not path.exists():
            self.skipTest("clima.json not built")
        doc = json.loads(path.read_text())
        burgos = next(s for s in doc["stations"] if s["wmo"] == "08075")
        self.assertEqual((burgos["tmed"][0], burgos["frost"][0], round(sum(burgos["sun"]), 1)), (3.6, 16.6, 2297.5))
        self.assertEqual(doc["provinces"]["09"]["tmed"][0], 3.6)
        self.assertEqual(sum(s["sun"] is not None for s in doc["stations"]), 76)
        murcia = next(s for s in doc["stations"] if s["wmo"] == "08430")
        self.assertEqual((murcia["coords"], murcia["province"]), ("aemet", "30"))
        self.assertEqual(doc["provinces_period"], "1991-2020")
        for s in doc["stations"]:  # the tooltip writes "Estación {name}"
            self.assertFalse("'" in s["name"] or s["name"].isupper() or s["name"].lower().startswith("estación"),
                             s["name"])
        self.assertEqual(next(s["name"] for s in doc["stations"] if s["wmo"] == "08449"), "Rota, Base Naval")

    def test_each_scale_clamps_little_of_any_month(self):
        """One scale for twelve months puts the extreme months near its ends; under 2 % of a month's land hexes, and
        no sunshine station, may fall beyond them."""
        from pipeline.countries import COUNTRIES
        path = COUNTRIES["es"].web_data_dir / "clima.json"
        if not path.exists():
            self.skipTest("clima.json not built")
        doc = json.loads(path.read_text())
        g, d = doc["grid"], doc["domains"]
        temp = [[None if a is None or b is None else (a + b) / 2 for a, b in zip(g["tmax"][m], g["tmin"][m])]
                for m in range(12)]
        for var, rows in (("temp", temp), ("prec", g["prec"]), ("frost", g["frost"])):
            lo, hi = d[var]
            for m, row in enumerate(rows):
                vals = [v for v in row if v is not None]
                out = sum(not lo <= v <= hi for v in vals) / len(vals)
                self.assertLess(out, 0.02, f"{var} month {m + 1}: {out:.1%} beyond {lo}..{hi}")
        sun = [v for s in doc["stations"] if s["sun"] for v in s["sun"]]
        self.assertEqual(d["sun"], [math.floor(min(sun)), math.ceil(max(sun))])


if __name__ == "__main__":
    unittest.main()
