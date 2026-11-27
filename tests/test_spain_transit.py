"""Hours to Madrid by train: the train sources (pipeline/sources/es/trenes.py) and the rules and check of
pipeline/build/spain_transit.py (DECISIONS E101–E104)."""

import copy
import io
import json
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from unittest import mock

from pipeline.build import spain_transit as st
from pipeline.core.archive import zip_bytes
from pipeline.core.csa import Journey, Leg
from pipeline.core.geo import Shape, ShapeIndex
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


def feed_zip(path: Path, written: date, service_end: str, removed: dict[str, str] | None = None, route="AVE",
             stops=("51003", "60000")):
    """A one-train GTFS zip whose files were written on `written`; `removed` = {date: service} calendar exceptions."""
    a, b = stops
    files = {
        "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
                        f"S,1,1,1,1,1,0,0,20261201,{service_end}\n",
        "calendar_dates.txt": "service_id,date,exception_type\n" + "".join(f"{sid},{d},2\n" for d, sid in (removed or {}).items()),
        "routes.txt": f"route_id,route_short_name,route_type\n51R1,{route},2\n",
        "trips.txt": "route_id,service_id,trip_id,trip_short_name\n51R1,S,t1,02060\n",
        "stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence,pickup_type,drop_off_type\n"
                          f"t1,7:00:00,7:00:00,{a},1,0,1\nt1,9:36:00,9:36:00,{b},2,1,0\n",
        "stops.txt": f"stop_id,stop_name,stop_lat,stop_lon\n{a},Sevilla-Santa Justa,37.39,-5.97\n{b},Madrid-Puerta de Atocha,40.41,-3.69\n",
    }
    with zipfile.ZipFile(path, "w") as z:
        for name, text in files.items():
            z.writestr(zipfile.ZipInfo(name, (written.year, written.month, written.day, 0, 0, 0)), text)


class ProcessTest(unittest.TestCase):
    """HorariosTren.process on fixture zips: the day rule, the skipped days and the optional Feve feed."""

    def process(self, feve_end: str | None):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            written = date(2026, 11, 27)
            feed_zip(raw / "renfe_av_ld.zip", written, "20261231")
            feed_zip(raw / "renfe_cercanias.zip", written, "20261231", {"20261202": "S"})  # no Cercanías on Wed 2
            feed_zip(raw / "ouigo.zip", date(2026, 7, 2), "20261212", stops=("007151003", "007160000"))
            feed_zip(raw / "iryo.zip", written, "20261231", {"20261201": "S"})  # no Iryo on Tue 1
            if feve_end:
                feed_zip(raw / "renfe_feve.zip", written, feve_end)
            src = trenes.HorariosTren()
            with mock.patch.object(trenes.HorariosTren, "raw_dir", raw), mock.patch.object(trenes, "read_manifest", lambda _id: {}):
                return src.process()

    def test_the_day_rule_skips_short_days(self):
        out = self.process(None)
        self.assertEqual(out["date"], "2026-12-03")  # Tue 1 lacks Iryo, Wed 2 lacks Cercanías
        self.assertEqual(out["window"], ["2026-12-01", "2026-12-12"])  # Ouigo's file ends first
        self.assertEqual([(d["date"], d["short"]) for d in out["skipped"]],
                         [("2026-12-01", ["iryo 0/1"]), ("2026-12-02", ["renfe_cercanias:51 0/1"])])
        self.assertEqual(out["week"], ["2026-11-30", "2026-12-06"])
        self.assertEqual([f["id"] for f in out["feeds"]], ["renfe_av_ld", "renfe_cercanias", "ouigo", "iryo"])
        self.assertEqual({f["id"]: f["file_date"] for f in out["feeds"]}["ouigo"], "2026-07-02")
        self.assertEqual({t[0] for t in out["trips"]}, {"renfe_av_ld", "renfe_cercanias", "ouigo", "iryo"})
        self.assertEqual(sorted(out["stops"]), ["51003", "60000"])  # Ouigo's UIC prefix stripped: the same stations
        self.assertEqual(out["stops"]["51003"][3], "renfe_av_ld")  # named after the first feed

    def test_feve_only_when_its_file_covers_the_day(self):
        self.assertIn("renfe_feve", [f["id"] for f in self.process("20261231")["feeds"]])
        out = self.process("20261202")  # ends before the day the others pick; it does not move the day
        self.assertEqual(out["date"], "2026-12-03")
        self.assertNotIn("renfe_feve", [f["id"] for f in out["feeds"]])


class StationsTest(unittest.TestCase):
    def test_puertollano_is_one_station(self):
        stops = {"37300": ["Puertollano", -4.1100, 38.6900, "renfe_av_ld"],
                 "37700": ["Puertollano", -4.1110, 38.6905, "iryo"],
                 "37500": ["Otra", -4.1300, 38.6900, "renfe_av_ld"]}  # 1.7 km away
        groups = sorted(st.cluster(stops))
        self.assertEqual(groups, [["37300", "37700"], ["37500"]])
        self.assertEqual(st.named_stop(["37700", "37300"], stops), "37300")
        self.assertEqual(st.named_stop(["9", "8"], {"9": ["A", 0, 0, "renfe_av_ld"], "8": ["B", 0, 0, "iryo"]}), "9")
        # Atocha: both stops are in the AV/LD feed; the Cercanías one boards far more trains, but none long distance
        atocha = {"18000": ["Madrid-Atocha Cercanías", 0, 0, "renfe_av_ld"],
                  "60000": ["Madrid-Puerta de Atocha", 0, 0, "renfe_av_ld"]}
        board = {"18000": {"cer": set(range(998)), "md": set(range(40))}, "60000": {"ld": set(range(111)), "md": set(range(24))}}
        self.assertEqual(st.named_stop(["18000", "60000"], atocha, board), "60000")
        self.assertEqual(st.named_stop(["18000", "60000"], atocha, {"18000": {"cer": {1}}, "60000": {}}), "18000")

    def test_leg_labels(self):
        self.assertEqual(st.leg_label(["ouigo", "ld", "TGV", "TGV 6540", "TGV 6540", []]), "Ouigo 6540")
        self.assertEqual(st.leg_label(["iryo", "ld", "", "06083", "06083", []]), "Iryo 06083")
        self.assertEqual(st.leg_label(["renfe_av_ld", "ld", "AVE", "02061", "02061", []]), "AVE 02061")
        self.assertEqual(st.leg_label(["renfe_cercanias", "cer", "C6", "", "x", []]), "C6")

    def test_a_journey_record_shows_its_walks(self):
        trips = [["renfe_cercanias", "cer", "C1", "", "c", []], ["iryo", "ld", "", "06083", "06083", []]]
        stops = {"G": ["Gandia"], "N": ["València-Estació del Nord"], "JS": ["València-Joaquín Sorolla"], "M": ["Madrid-Chamartín"]}
        j = Journey(6 * 3600, 9 * 3600, "M", [Leg("0", "G", "N", 6 * 3600, 7 * 3600), Leg(None, "N", "JS", 7 * 3600, 7 * 3600 + 780),
                                               Leg("1", "JS", "M", 7 * 3600 + 1800, 9 * 3600)])
        self.assertEqual(st.journey_record(j, trips, stops),
                         {"min": 180, "dep": "06:00", "arr": "09:00", "to": "Madrid-Chamartín", "changes": 1,
                          "legs": [["C1", "Gandia", "València-Estació del Nord"],
                                   [None, "València-Estació del Nord", "València-Joaquín Sorolla"],
                                   ["Iryo 06083", "València-Joaquín Sorolla", "Madrid-Chamartín"]]})

    def test_border_stops_by_the_outline_not_the_hex(self):
        # Spain is x < 100 (a square); Cerbère-like stop 0.8 km beyond the border, Santa Susanna-like 20 m off the coast
        spain = ShapeIndex([Shape([[(0, 0), (100, 0), (100, 100), (0, 100)]])])
        self.assertTrue(st.in_spain(spain, 50, 50))
        self.assertTrue(st.in_spain(spain, 100.02, 50))
        self.assertFalse(st.in_spain(spain, 100.8, 50))
        self.assertFalse(st.in_spain(spain, 300, 50))

    def test_cut_lines(self):
        stops = {"G": ["La Garriga", 2.28, 41.68], "V": ["Vic", 2.25, 41.93], "T": ["La Tor de Querol-Enveig", 1.88, 42.46],
                 "B": ["Barcelona-Sants", 2.14, 41.38]}
        r3 = lambda *ids: ["renfe_cercanias", "cer", "R3", "", "x" + "".join(ids), [[i, 0, 0, 1, 1] for i in ids]]
        trips = [r3("G", "V"), r3("V", "T"), r3("T", "G"), ["renfe_cercanias", "cer", "R2", "", "y", [["B", 0, 0, 1, 1], ["G", 9, 9, 1, 1]]]]
        self.assertEqual(st.cut_lines(trips, stops, {"G", "V", "T"}), [{"route": "R3", "from": "La Garriga", "to": "La Tor de Querol-Enveig"}])
        self.assertEqual(st.cut_lines(trips, stops, {"V", "T"}), [])  # La Garriga still has a journey

    def test_boardings_count_distinct_trains(self):
        trips = [["renfe_av_ld", "ld", "AVE", "1", "1", [["A", 0, 0, 1, 1], ["B", 60, 60, 1, 1]]],
                 ["renfe_av_ld", "ld", "AVE", "1", "1", [["A", 0, 0, 1, 1], ["C", 90, 90, 1, 1]]],
                 ["renfe_cercanias", "cer", "C1", "", "c9", [["A", 0, 0, 0, 1], ["B", 60, 60, 1, 1]]]]
        b = st.boardings(trips)
        self.assertEqual(len(b["A"]["ld"]), 1)
        self.assertNotIn("cer", b["A"])  # no boarding where pickup_type = 1
        self.assertNotIn("B", b)  # a last call is not a boarding
        self.assertEqual(st.stop_pairs(trips), {("A", "B", "hs"): {("renfe_av_ld", "1")}, ("A", "C", "hs"): {("renfe_av_ld", "1")},
                                                ("A", "B", "conv"): {("renfe_cercanias", "c9")}})
        self.assertEqual(st.track_class("md", "AVANT"), "hs")
        self.assertEqual(st.track_class("md", "Regional"), "conv")


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


def chain(cells, hs=False, refs=("100",)):
    return {(min(a, b), max(a, b)): st.Track({"adif"}, hs=hs, conv=not hs, refs=set(refs)) for a, b in zip(cells, cells[1:])}


def counts(served):
    return {l: len(who) for l, who in served.items()}


class TrackTest(unittest.TestCase):
    ROW0 = [GRID.index(c, 0) for c in range(10)]
    ROW1 = [GRID.index(c, 1) for c in range(10)]

    def test_classifies_operators_gauges_and_high_speed(self):
        line = [list(centre(0)), list(centre(4))]
        ident = lambda lon, lat: (lon, lat)
        for tags, what in (({"operator": "Adif", "gauge": "1668"}, "adif"), ({"operator": "ADIF;Renfe"}, "adif"),
                           ({"operator": "Adif", "railway": "narrow_gauge", "gauge": "1000"}, "adif_metre"),
                           ({"operator": "Adif", "gauge": "1000"}, "adif_metre"),
                           ({"operator": "FGC"}, "other"), ({}, "other")):
            with self.subTest(tags=tags):
                links = st.track_links(GRID, ident, owner(), [{"tags": tags, "line": line}])
                self.assertTrue(links)
                self.assertEqual(set().union(*(t.what for t in links.values())), {what})
        hs = st.track_links(GRID, ident, owner(), [{"tags": {"operator": "Adif", "highspeed": "yes", "ref": "050;040"}, "line": line},
                                                   {"tags": {"operator": "Adif", "ref": "200"}, "line": line}])
        t = next(iter(hs.values()))
        self.assertEqual((t.hs, t.conv, t.refs), (True, True, {"050", "040", "200"}))

    def test_path_accepted(self):
        links = chain(self.ROW0)
        where = {"A": centre(0), "B": centre(3)}
        served, tally = st.match_pairs(GRID, links, {("A", "B", "conv"): {("f", "1"), ("f", "2")}}, where, set())
        self.assertEqual(counts(served), {(self.ROW0[i], self.ROW0[i + 1]): 2 for i in range(3)})
        self.assertEqual((tally["pairs"], tally["unmatched"]), (1, 0))

    def test_parallel_lines_each_take_their_trains(self):
        # A high-speed line along row 0 and a conventional one along row 1, joined at both ends: the AVE keeps to
        # row 0 and the regional to row 1, though row 0 is two links shorter for it. By length alone (the old rule)
        # both took row 0 and left the conventional line a ghost.
        hs, conv = chain(self.ROW0[:6], hs=True, refs=("050",)), chain(self.ROW1[:6], refs=("200",))
        ends = {(min(a, b), max(a, b)): st.Track({"adif"}, conv=True, refs={"200"})
                for a, b in ((self.ROW0[0], self.ROW1[0]), (self.ROW0[5], self.ROW1[5]))}
        links = {**hs, **conv, **ends}
        where = {"A": centre(0), "B": centre(5)}
        pairs = {("A", "B", "hs"): {("renfe_av_ld", "AVE")}, ("A", "B", "conv"): {("renfe_av_ld", "MD")}}
        served, _ = st.match_pairs(GRID, links, pairs, where, set())
        self.assertTrue(all(served[l] == {("renfe_av_ld", "AVE")} for l in hs))
        self.assertTrue(all(served[l] == {("renfe_av_ld", "MD")} for l in conv))
        self.assertEqual(st.ghosts(GRID, links, served, False, [])[0], [])
        self.assertEqual(st.hs_ghosts(links, served, []), 0)
        only_hs = {("A", "B", "hs"): {("renfe_av_ld", "AVE")}}
        served, _ = st.match_pairs(GRID, links, only_hs, where, set())
        self.assertEqual(set(served), set(hs))

    def test_one_train_written_as_several_trips_counts_once(self):
        # Regional 18034: Valdepeñas → Linares-Baeza → Jaén and Valdepeñas → Vilches → Jaén, on one line
        trips = [["renfe_av_ld", "md", "Regional", "18034", "18034", [["V", 0, 0, 1, 1], ["L", 60, 60, 1, 1], ["J", 90, 90, 1, 1]]],
                 ["renfe_av_ld", "md", "Regional", "18034", "18034", [["V", 0, 0, 1, 1], ["X", 30, 30, 1, 1], ["J", 90, 90, 1, 1]]]]
        where = {"V": centre(0), "X": centre(2), "L": centre(4), "J": centre(6)}
        served, _ = st.match_pairs(GRID, chain(self.ROW0), st.stop_pairs(trips), where, set())
        self.assertEqual(set(counts(served).values()), {1})
        self.assertEqual(len(served), 6)

    def test_a_detour_or_no_track_is_unmatched(self):
        row1 = [GRID.index(c, 1) for c in range(9, -1, -1)]
        self.assertIn(row1[0], GRID.neighbours(self.ROW0[-1]))
        links = chain(self.ROW0 + row1)  # down row 0, back along row 1: 150 km for a 7.5 km pair
        where = {"A": centre(0), "B": centre(0, 1), "C": centre(0, 2), "F": centre(11)}
        pairs = {("A", "B", "conv"): {1, 2, 3}, ("A", "C", "conv"): {1, 2}, ("A", "C", "hs"): {9}, ("A", "F", "hs"): {1}}
        served, tally = st.match_pairs(GRID, links, pairs, where, {"F"})
        self.assertEqual(served, {})
        self.assertEqual((tally["pairs"], tally["unmatched"], tally["abroad"]), (3, 2, 1))
        self.assertEqual(tally["unmatched_pairs"], [("A", "B"), ("A", "C")])

    def test_ghosts_only_on_unserved_adif_track(self):
        a, b, c, d, e = self.ROW0[:5]
        T = lambda what, refs=(): st.Track({what}, conv=True, refs=set(refs))
        links = {(a, b): T("adif", "1"), (b, c): T("adif", "2"), (c, d): T("other"), (d, e): T("adif_metre")}
        served = {(a, b): {1, 2}}
        self.assertEqual(st.ghosts(GRID, links, served, False, [])[0], [(b, c)])
        self.assertEqual(st.ghosts(GRID, links, served, True, [])[0], [(b, c), (d, e)])

    def test_no_ghost_where_trains_may_run_unmatched(self):
        links = chain(self.ROW0[:4])
        far = [(centre(0, 2), (centre(0, 2)[0] + 1, centre(0, 2)[1]))]
        near = [(centre(0), centre(3))]  # a stop pair with no track path along the same line
        self.assertEqual(len(st.ghosts(GRID, links, {}, False, far)[0]), 3)
        kept, tally = st.ghosts(GRID, links, {}, False, near)
        self.assertEqual((kept, tally["near_unmatched"]), ([], 3))

    def test_a_short_unused_run_beside_its_own_line_is_not_a_ghost(self):
        line = chain(self.ROW0, refs=("050",))
        served = {l: {1} for l in list(line)[:3] + list(line)[6:]}  # links 3-5 unused: a 3-link gap
        kept, tally = st.ghosts(GRID, line, served, False, [])
        self.assertEqual((kept, tally["short_runs"], tally["ghost_runs"]), ([], 1, 0))
        served = {l: {1} for l in list(line)[:2]}  # 7 links unused: a real stretch without trains
        self.assertEqual(len(st.ghosts(GRID, line, served, False, [])[0]), 7)
        other = {l: st.Track({"adif"}, conv=True, refs={"200"}) for l in line}  # a gap on another line's track
        self.assertEqual(len(st.ghosts(GRID, {**line, **{l: other[l] for l in list(line)[3:6]}},
                                       {l: {1} for l in list(line)[:3] + list(line)[6:]}, False, [])[0]), 3)

    def test_high_speed_ghost_beside_served_high_speed_track(self):
        line = chain(self.ROW0[:6], hs=True, refs=("050",))
        ls = sorted(line)
        served = {l: {1} for l in ls[:2]}
        self.assertEqual(st.hs_ghosts(line, served, ls[2:]), 1)  # only the link that touches the served track
        self.assertEqual(st.hs_ghosts(chain(self.ROW0[:6], refs=("050",)), served, ls[2:]), 0)  # conventional


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
        # the Feve trains of the AV/LD file count; only the Feve file is missing, and with it unused metre gauge
        self.assertIn("Los trenes de Feve que trae el fichero de Renfe de alta velocidad, larga y media distancia cuentan", note)
        self.assertIn("Renfe Feve no entra", note)
        self.assertNotIn("Feve", st.texts(date(2026, 12, 9), (date(2026, 12, 7), date(2026, 12, 13)),
                                          [{"id": "renfe_feve"}])["lens"]["note"]["es"])
        self.assertEqual(tx["lens"]["null_label"]["es"], "A más de 30 km de una estación con tren a Madrid ese día")
        self.assertIn("convenciones del mapa, no tiempos medidos", note)  # in the note, which phones show too
        self.assertLess(len(tx["lens"]["description"]["es"]), 160)  # three legend lines

    def test_note_counts_what_is_not_drawn_and_names_cut_lines(self):
        cuts = [{"route": "R3", "from": "La Garriga", "to": "La Tor de Querol-Enveig"}]
        tx = st.texts(date(2026, 12, 9), (date(2026, 12, 7), date(2026, 12, 13)), [{"id": "renfe_av_ld"}],
                      unmatched=16, stranded=56, cuts=cuts)
        self.assertIn("16 pares de paradas seguidas no casan con las vías de OpenStreetMap", tx["lens"]["note"]["es"])
        self.assertTrue(tx["lens"]["note"]["es"].endswith(
            "Desde 56 estaciones con tren no se llega a Madrid ese día; entre ellas, las de la R3, que ese día solo "
            "tiene trenes de La Garriga a La Tor de Querol-Enveig."), tx["lens"]["note"]["es"])
        self.assertIn("those of the R3, whose trains that day only run from La Garriga", tx["lens"]["note"]["en"])

    def test_day_rule_says_how_many_days_it_compared(self):
        feeds = [{"id": "renfe_av_ld", "file_date": "2026-11-27"}, {"id": "ouigo", "file_date": "2026-07-02"}]
        tx = st.texts(date(2026, 12, 9), (date(2026, 12, 7), date(2026, 12, 13)), feeds,
                      window=(date(2026, 11, 28), date(2026, 12, 12)))
        self.assertIn("solo coinciden del 28 de noviembre al 12 de diciembre, así que ese día se compara con 1 "
                      "miércoles más", tx["rules"]["day"]["es"])
        self.assertIn("compared with 1 other Wednesday", tx["rules"]["day"]["en"])
        self.assertTrue(tx["rules"]["day"]["es"].endswith(
            "Ficheros: Renfe AV/LD, del 27 de noviembre de 2026; Ouigo, del 2 de julio de 2026."))


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
            "feeds": [{"id": "renfe_av_ld", "window": ["2026-11-26", "2027-09-29"], "file_date": "2026-11-27"}],
            "matching": {"pairs": 10, "abroad": 1, "unmatched": 2, "unmatched_pairs": [["X", "Y"], ["Z", "W"]], "hs_ghost": 0}}


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
        self.assertNotIn("ends", notes)

    def test_a_feed_that_ends_soon_after_the_day_is_noted(self):
        doc = good_doc()
        doc["feeds"].append({"id": "ouigo", "window": ["2026-06-26", "2026-12-12"], "file_date": "2026-07-02"})
        notes = [m for lv, m in self.run_check(doc) if lv == "NOTE"]
        self.assertIn("transit.json: the ouigo file ends 3 days after the day of the timetable (2026-12-12, file of "
                      "2026-07-02): refetch it, or take its NAP copy", notes)

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
            "high-speed ghost beside its line": lambda d: d["matching"].update(hs_ghost=2),
            "station with no train to board": lambda d: d["stations"][0].update(trains=[0, 0, 0]),
        }
        for what, change in cases.items():
            doc = copy.deepcopy(good_doc())
            change(doc)
            with self.subTest(what=what):
                self.assertTrue([m for lv, m in self.run_check(doc) if lv == "FAIL"], what)


if __name__ == "__main__":
    unittest.main()
