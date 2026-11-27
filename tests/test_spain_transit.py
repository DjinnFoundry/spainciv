"""Hours to Madrid by train: the train sources (pipeline/sources/es/trenes.py) and the rules and check of
pipeline/build/spain_transit.py (DECISIONS E84–E87)."""

import copy
import io
import json
import tempfile
import unittest
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

from pipeline.build import spain_transit as st
from pipeline.core.archive import zip_bytes
from pipeline.core.hexgrid import HexGrid
from pipeline.sources.es import trenes

GRID = HexGrid(5.0, 12, 3)  # cells 8.66 km apart along a row
ISLAND = GRID.index(11, 0)
SEA = GRID.index(10, 0)


def owner():
    """Land everywhere (community 0) but column 10 (sea); column 11 is an island."""
    return [-1 if GRID.col_row(i)[0] == 10 else 0 for i in range(GRID.size)]


def centre(col, row=0):
    return GRID.center(col, row)


def gtfs_zip(**files: str) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(zip_bytes({f"{k}.txt": v.encode("utf-8") for k, v in files.items()})))


class TimetableTest(unittest.TestCase):
    FILES = dict(
        calendar="service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
                 "S,1,1,1,1,1,0,0,20261201,20261231\n",
        routes="route_id,route_short_name,route_type\nR1,AVE ,2\nR2,Regional,2\nRB,BUS,3\n",
        trips="route_id,service_id,trip_id,trip_short_name\nR1,S,t1,02060\nR1,S,t1b,02060\nR2,S,t2,18000\nRB,S,b1,9\n",
        stop_times="trip_id,arrival_time,departure_time,stop_id,stop_sequence,pickup_type,drop_off_type\n"
                   "t1,7:00:00,7:00:00,51003,1,0,1\nt1,9:36:00,9:36:00,60000,2,1,0\n"
                   "t1b,7:00:00,7:00:00,51003,1,0,1\nt1b,9:36:00,9:36:00,60000,2,1,0\n"
                   "t2,23:50:00,23:50:00,51003,1,0,0\nt2,24:20:00,24:20:00,50500,2,0,0\n"
                   "b1,10:00:00,10:00:00,51003,1,0,0\nb1,11:00:00,11:00:00,99999,2,0,0\n",
        stops="stop_id,stop_name,stop_lat,stop_lon\n51003,Sevilla-Santa Justa,37.39,-5.97\n"
              "60000,Madrid-Puerta de Atocha,40.41,-3.69\n50500,Córdoba,37.89,-4.79\n99999,Bus stop,0,0\n",
    )

    def table(self, files=None, feed=None):
        t = trenes.Timetable.__new__(trenes.Timetable)
        z = gtfs_zip(**(files or self.FILES))
        feed = feed or trenes.FEEDS[0]
        trenes.Timetable.__init__(t, feed, io.BytesIO(z.fp.getvalue()))
        return t

    def test_uic_prefix(self):
        self.assertEqual(trenes.uic_to_adif("007160000"), "60000")
        self.assertEqual(trenes.uic_to_adif("60000"), "60000")

    def test_trips_of_a_day(self):
        trips, stops = self.table().day(date(2026, 12, 9))
        self.assertEqual([t[2] for t in trips], ["AVE", "AVE", "Regional"])  # the bus is left out, padding stripped
        self.assertEqual([t[1] for t in trips], ["ld", "ld", "md"])
        self.assertEqual(trips[0][4], trips[1][4])  # two trips of one numbered train are one train
        self.assertEqual(trips[0][5], [["51003", 7 * 3600, 7 * 3600, 1, 0], ["60000", 9 * 3600 + 36 * 60, 9 * 3600 + 36 * 60, 0, 1]])
        self.assertEqual(trips[2][5][1][1], 24 * 3600 + 20 * 60)  # past midnight, same service day
        self.assertNotIn("99999", stops)
        self.assertEqual(stops["60000"], ["Madrid-Puerta de Atocha", -3.69, 40.41])
        self.assertEqual(self.table().day(date(2026, 12, 12))[0], [])  # Saturday: nothing runs

    def test_unknown_route_name_fails(self):
        files = dict(self.FILES, routes=self.FILES["routes"].replace("Regional", "Tren Turístico"))
        with self.assertRaises(ValueError):
            self.table(files).day(date(2026, 12, 9))

    def test_ouigo_stops_lose_their_prefix(self):
        files = {k: v.replace("60000", "007160000").replace("51003", "007151003") for k, v in self.FILES.items()}
        trips, stops = self.table(files, trenes.FEEDS[2]).day(date(2026, 12, 9))
        self.assertEqual({c[0] for t in trips for c in t[5]}, {"51003", "60000", "50500"})
        self.assertEqual({t[1] for t in trips}, {"ld"})  # every Ouigo train is long distance
        self.assertIn("60000", stops)


class StationsTest(unittest.TestCase):
    def test_puertollano_is_one_station(self):
        stops = {"37300": ["Puertollano", -4.1100, 38.6900, "renfe_av_ld"],
                 "37700": ["Puertollano", -4.1110, 38.6905, "iryo"],
                 "37500": ["Otra", -4.1300, 38.6900, "renfe_av_ld"]}  # 1.7 km away
        groups = sorted(st.cluster(stops))
        self.assertEqual(groups, [["37300", "37700"], ["37500"]])
        self.assertEqual(st.named_stop(["37700", "37300"], stops), "37300")
        self.assertEqual(st.named_stop(["9", "8"], {"9": ["A", 0, 0, "renfe_av_ld"], "8": ["B", 0, 0, "iryo"]}), "9")
        atocha = {"18000": ["Madrid-Atocha Cercanías", 0, 0, "renfe_av_ld"],
                  "60000": ["Madrid-Puerta de Atocha", 0, 0, "renfe_av_ld"]}
        self.assertEqual(st.named_stop(["18000", "60000"], atocha, {"18000": 40, "60000": 300}), "60000")

    def test_boardings_count_distinct_trains(self):
        trips = [["renfe_av_ld", "ld", "AVE", "1", "1", [["A", 0, 0, 1, 1], ["B", 60, 60, 1, 1]]],
                 ["renfe_av_ld", "ld", "AVE", "1", "1", [["A", 0, 0, 1, 1], ["C", 90, 90, 1, 1]]],
                 ["renfe_cercanias", "cer", "C1", "", "c9", [["A", 0, 0, 0, 1], ["B", 60, 60, 1, 1]]]]
        b = st.boardings(trips)
        self.assertEqual(len(b["A"]["ld"]), 1)
        self.assertNotIn("cer", b["A"])  # no boarding where pickup_type = 1
        self.assertNotIn("B", b)  # a last call is not a boarding
        self.assertEqual(st.stop_pairs(trips), {("A", "B"): 2, ("A", "C"): 1})


class HexValueTest(unittest.TestCase):
    def test_formula_reach_and_islands(self):
        x, y = centre(0)
        values, station = st.hex_values(GRID, owner(), [(x, y, 3600, 4)])
        self.assertEqual(values[0], 60)
        d = GRID.center(2, 0)[0] - x  # 17.3 km at 40 km/h: 26 min
        self.assertEqual(values[GRID.index(2, 0)], round((3600 + d / 40 * 3600) / 60))
        self.assertEqual(station[GRID.index(2, 0)], 4)
        self.assertIsNone(values[GRID.index(4, 0)])  # 34.6 km: beyond 30 km
        self.assertIsNone(values[ISLAND])
        self.assertIsNone(values[SEA])

    def test_the_best_of_two_stations(self):
        values, station = st.hex_values(GRID, owner(), [(*centre(0), 7200, 0), (*centre(3), 600, 1)])
        self.assertEqual((values[GRID.index(1, 0)], station[GRID.index(1, 0)]), (round((600 + 2 * 8.660254 / 40 * 3600) / 60), 1))


def chain(cells):
    return {(min(a, b), max(a, b)): {"adif"} for a, b in zip(cells, cells[1:])}


class TrackTest(unittest.TestCase):
    ROW0 = [GRID.index(c, 0) for c in range(10)]

    def test_classifies_operators_and_gauges(self):
        line = [list(centre(0)), list(centre(4))]
        ident = lambda lon, lat: (lon, lat)
        for tags, what in (({"operator": "Adif", "gauge": "1668"}, "adif"), ({"operator": "ADIF;Renfe"}, "adif"),
                           ({"operator": "Adif", "railway": "narrow_gauge", "gauge": "1000"}, "adif_metre"),
                           ({"operator": "Adif", "gauge": "1000"}, "adif_metre"),
                           ({"operator": "FGC"}, "other"), ({}, "other")):
            with self.subTest(tags=tags):
                links = st.track_links(GRID, ident, owner(), [{"tags": tags, "line": line}])
                self.assertTrue(links)
                self.assertEqual(set().union(*links.values()), {what})

    def test_path_accepted(self):
        links = chain(self.ROW0)
        where = {"A": centre(0), "B": centre(3)}
        served, tally = st.match_pairs(GRID, links, {("A", "B"): 7}, where, set())
        self.assertEqual(served, Counter({(self.ROW0[i], self.ROW0[i + 1]): 7 for i in range(3)}))
        self.assertEqual((tally["pairs"], tally["unmatched"]), (1, 0))

    def test_a_detour_or_no_track_is_unmatched(self):
        row1 = [GRID.index(c, 1) for c in range(9, -1, -1)]
        self.assertIn(row1[0], GRID.neighbours(self.ROW0[-1]))
        links = chain(self.ROW0 + row1)  # down row 0, back along row 1: 150 km for a 7.5 km pair
        where = {"A": centre(0), "B": centre(0, 1), "C": centre(0, 2), "F": centre(11)}
        served, tally = st.match_pairs(GRID, links, {("A", "B"): 3, ("A", "C"): 2, ("A", "F"): 1}, where, {"F"})
        self.assertEqual(served, Counter())
        self.assertEqual((tally["unmatched"], tally["abroad"]), (2, 1))
        self.assertEqual(tally["unmatched_pairs"], [("A", "B"), ("A", "C")])

    def test_ghosts_only_on_unserved_adif_track(self):
        a, b, c, d, e = self.ROW0[:5]
        links = {(a, b): {"adif"}, (b, c): {"adif"}, (c, d): {"other"}, (d, e): {"adif_metre"}}
        served = Counter({(a, b): 5})
        self.assertEqual(st.ghosts(links, served, feve=False), [(b, c)])
        self.assertEqual(st.ghosts(links, served, feve=True), [(b, c), (d, e)])


class TextsTest(unittest.TestCase):
    def test_dates(self):
        self.assertEqual(st.day_text(date(2026, 12, 9)),
                         {"es": "miércoles 9 de diciembre de 2026", "en": "Wednesday 9 December 2026"})
        self.assertEqual(st.week_text(date(2026, 12, 7), date(2026, 12, 13)), {"es": "del 7 al 13", "en": "7 to 13 December"})
        self.assertEqual(st.week_text(date(2026, 11, 30), date(2026, 12, 6))["es"], "del 30 de noviembre al 6 de diciembre")

    def test_note_names_the_day_and_what_is_left_out(self):
        tx = st.texts(date(2026, 12, 9), (date(2026, 12, 7), date(2026, 12, 13)), [{"id": "renfe_av_ld"}])
        note = tx["lens"]["note"]["es"]
        self.assertTrue(note.startswith("Horario del miércoles 9 de diciembre de 2026 (semana del 7 al 13)"), note)
        self.assertIn("FGC, Euskotren, FGV, SFM", note)
        self.assertIn("Renfe Feve", note)  # metre gauge not drawn without the Feve feed
        self.assertNotIn("Renfe Feve", st.texts(date(2026, 12, 9), (date(2026, 12, 7), date(2026, 12, 13)),
                                                [{"id": "renfe_feve"}])["lens"]["note"]["es"])
        self.assertEqual(tx["lens"]["null_label"]["es"], "A más de 30 km de una estación con tren a Madrid ese día")


def good_doc():
    values = [None] * GRID.size
    station = [None] * GRID.size
    for c in range(3):
        values[GRID.index(c, 0)], station[GRID.index(c, 0)] = 156 + 13 * c, 0
    a, b, c = (GRID.index(i, 0) for i in range(3))
    madrid = {"name": "Madrid-Puerta de Atocha", "x": 400.0, "y": 0.0, "cell": GRID.index(5, 2), "stops": ["60000"],
              "trains": [300, 100, 900], "best": None, "madrid": True}
    sevilla = {"name": "Sevilla-Santa Justa", "x": centre(0)[0], "y": 0.0, "cell": a, "stops": ["51003"],
               "trains": [83, 0, 142], "best": {"min": 156, "dep": "07:00", "arr": "09:36", "to": "Madrid-Puerta de Atocha",
                                                "changes": 0, "legs": [["AVE", "02060", "Sevilla-Santa Justa", "Madrid-Puerta de Atocha"]]}}
    return {"version": 1, "date": "2026-12-09", "params": {"access_km": 30},
            "lens": {"values": values, "station": station}, "stations": [sevilla, madrid],
            "links": [[a, b, 12]], "ghost": [[b, c]],
            "matching": {"pairs": 10, "abroad": 1, "unmatched": 2, "unmatched_pairs": [["X", "Y"], ["Z", "W"]]}}


class CheckTest(unittest.TestCase):
    def run_check(self, doc):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "world.json").write_text(json.dumps({"grid": GRID.to_dict(), "owner": owner()}))
            if doc is not None:
                (Path(tmp) / "transit.json").write_text(json.dumps(doc))
            return st.check(Path(tmp))

    def test_missing_file_is_a_note(self):
        self.assertEqual([lv for lv, _ in self.run_check(None)], ["NOTE"])

    def test_good_file_passes_with_notes(self):
        lines = self.run_check(good_doc())
        self.assertFalse([m for lv, m in lines if lv in ("FAIL", "WARN")], lines)
        notes = " ".join(m for lv, m in lines if lv == "NOTE")
        self.assertIn("3 of 33 land hexes", notes)
        self.assertIn("2 of 10 stop pairs", notes)

    def test_violations_fail(self):
        far = GRID.index(5, 0)
        cases = {
            "non-neighbour link": lambda d: d["links"].append([0, far, 1]),
            "served and ghost": lambda d: d["ghost"].append(d["links"][0][:2]),
            "station off land": lambda d: d["stations"][0].update(cell=SEA),
            "negative minute": lambda d: d["lens"]["values"].__setitem__(0, -5),
            "short values": lambda d: d["lens"]["values"].pop(),
            "short stations": lambda d: d["lens"]["station"].pop(),
            "faster than 350 km/h": lambda d: d["stations"][0]["best"].update(min=60),
            "value at sea": lambda d: (d["lens"]["values"].__setitem__(SEA, 100), d["lens"]["station"].__setitem__(SEA, 0)),
            "station without value": lambda d: d["lens"]["station"].__setitem__(5, 0),
            "zero trains": lambda d: d["links"][0].__setitem__(2, 0),
        }
        for what, change in cases.items():
            doc = copy.deepcopy(good_doc())
            change(doc)
            with self.subTest(what=what):
                self.assertTrue([m for lv, m in self.run_check(doc) if lv == "FAIL"], what)


if __name__ == "__main__":
    unittest.main()
