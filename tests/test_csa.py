"""pipeline/core/csa.py: the shortest timetabled journey of the day to a set of target stops (profile Connection Scan)."""

import unittest

from pipeline.core.csa import Connection, footpaths, profile, trip_connections

H = 3600
M = 60


def ride(trip, *calls, board=None, alight=None):
    """Connections of one trip from (stop, arrival, departure) calls; `board` / `alight` = stops where one cannot."""
    return trip_connections(trip, [(s, a, d, s not in (board or ()), s not in (alight or ())) for s, a, d in calls])


class ScanTest(unittest.TestCase):
    def best(self, conns, targets=("MAD",), stop="A", change=10 * M, walks=None):
        return profile(conns, set(targets), change, walks or {}).best(stop)

    def test_direct_beats_a_transfer(self):
        conns = ride("d", ("A", 8 * H, 8 * H), ("MAD", 10 * H, 10 * H)) + \
            ride("x1", ("A", 8 * H, 8 * H), ("B", 8 * H + 30 * M, 8 * H + 30 * M)) + \
            ride("x2", ("B", 8 * H + 50 * M, 8 * H + 50 * M), ("MAD", 10 * H + 30 * M, 10 * H + 30 * M))
        j = self.best(conns)
        self.assertEqual((j.dep, j.arr, j.changes), (8 * H, 10 * H, 0))
        self.assertEqual([(l.trip, l.frm, l.to) for l in j.legs], [("d", "A", "MAD")])

    def test_a_change_takes_ten_minutes(self):
        first = ride("x1", ("A", 8 * H, 8 * H), ("B", 9 * H, 9 * H))
        tight = ride("x2", ("B", 9 * H + 9 * M, 9 * H + 9 * M), ("MAD", 10 * H, 10 * H))
        self.assertIsNone(self.best(first + tight))
        ok = ride("x3", ("B", 9 * H + 10 * M, 9 * H + 10 * M), ("MAD", 10 * H + 5 * M, 10 * H + 5 * M))
        j = self.best(first + tight + ok)
        self.assertEqual((j.duration, j.changes), (2 * H + 5 * M, 1))
        self.assertEqual([(l.trip, l.frm, l.to, l.dep, l.arr) for l in j.legs],
                         [("x1", "A", "B", 8 * H, 9 * H), ("x3", "B", "MAD", 9 * H + 10 * M, 10 * H + 5 * M)])

    def test_a_later_shorter_departure_wins(self):
        slow = ride("s", ("A", 7 * H, 7 * H), ("MAD", 11 * H, 11 * H))
        fast = ride("f", ("A", 15 * H, 15 * H), ("MAD", 17 * H, 17 * H))
        j = self.best(slow + fast)
        self.assertEqual((j.dep, j.duration), (15 * H, 2 * H))
        # the profile also keeps the earlier departure, which arrives first
        self.assertEqual([(e.dep, e.arr) for e in profile(slow + fast, {"MAD"}, 10 * M, {}).entries("A")],
                         [(15 * H, 17 * H), (7 * H, 11 * H)])

    def test_riding_through_a_stop_with_no_drop_off(self):
        # Cáceres: the train calls at B, where nobody may get off, on its way to Madrid.
        conns = ride("t", ("A", 8 * H, 8 * H), ("B", 9 * H, 9 * H), ("MAD", 11 * H, 11 * H), alight={"B"})
        self.assertEqual(self.best(conns).duration, 3 * H)
        self.assertEqual(self.best(conns, stop="B").duration, 2 * H)
        # but nobody can change trains there
        other = ride("u", ("C", 7 * H, 7 * H), ("B", 8 * H, 8 * H), alight={"B"})
        self.assertIsNone(self.best(conns + other, stop="C"))

    def test_no_boarding_where_pickup_is_one(self):
        conns = ride("t", ("A", 8 * H, 8 * H), ("B", 9 * H, 9 * H), ("MAD", 11 * H, 11 * H), board={"B"})
        self.assertIsNone(self.best(conns, stop="B"))
        self.assertEqual(self.best(conns).duration, 3 * H)

    def test_footpath_to_a_nearby_stop_and_to_a_target(self):
        # Gandia → València Nord, walk to Joaquín Sorolla, AVE to Madrid.
        walks = {"NORD": [("JS", 13 * M)], "JS": [("NORD", 13 * M)]}
        conns = ride("c", ("G", 7 * H, 7 * H), ("NORD", 8 * H, 8 * H)) + \
            ride("ave", ("JS", 8 * H + 30 * M, 8 * H + 30 * M), ("MAD", 10 * H + 20 * M, 10 * H + 20 * M))
        j = self.best(conns, stop="G", walks=walks)
        self.assertEqual((j.duration, j.changes), (3 * H + 20 * M, 1))
        self.assertEqual([(l.trip, l.frm, l.to) for l in j.legs], [("c", "G", "NORD"), (None, "NORD", "JS"), ("ave", "JS", "MAD")])
        self.assertEqual((j.legs[1].dep, j.legs[1].arr), (8 * H, 8 * H + 13 * M))
        # 13 min walk + 10 min change: a 08:22 train is missed
        early = ride("ave", ("JS", 8 * H + 22 * M, 8 * H + 22 * M), ("MAD", 9 * H, 9 * H))
        self.assertIsNone(self.best(ride("c", ("G", 7 * H, 7 * H), ("NORD", 8 * H, 8 * H)) + early, stop="G", walks=walks))
        # a walk into a target stop ends the journey there
        walks2 = {"MAD2": [("MAD", 5 * M)]}
        j = self.best(ride("r", ("A", 8 * H, 8 * H), ("MAD2", 9 * H, 9 * H)), walks=walks2)
        self.assertEqual((j.arr, j.to, j.changes), (9 * H + 5 * M, "MAD", 0))
        self.assertEqual([(l.trip, l.frm, l.to) for l in j.legs], [("r", "A", "MAD2"), (None, "MAD2", "MAD")])

    def test_a_journey_may_start_on_foot(self):
        # València Nord: the C6 out and back is slower than walking to Joaquín Sorolla for the AVE.
        walks = {"NORD": [("JS", 13 * M)], "JS": [("NORD", 13 * M)]}
        conns = ride("c6", ("NORD", 7 * H, 7 * H), ("X", 7 * H + 20 * M, 7 * H + 20 * M)) + \
            ride("c6b", ("X", 7 * H + 30 * M, 7 * H + 30 * M), ("NORD", 7 * H + 50 * M, 7 * H + 50 * M)) + \
            ride("ave", ("JS", 8 * H + 30 * M, 8 * H + 30 * M), ("MAD", 10 * H + 20 * M, 10 * H + 20 * M))
        p = profile(conns, {"MAD"}, 10 * M, walks)
        j = p.best("NORD")
        self.assertEqual((j.dep, j.arr, j.duration, j.changes), (8 * H + 17 * M, 10 * H + 20 * M, 2 * H + 3 * M, 0))
        self.assertEqual([(l.trip, l.frm, l.to, l.dep, l.arr) for l in j.legs],
                         [(None, "NORD", "JS", 8 * H + 17 * M, 8 * H + 30 * M), ("ave", "JS", "MAD", 8 * H + 30 * M, 10 * H + 20 * M)])
        self.assertIn("NORD", p.stops())
        # a train from the stop itself wins when it is shorter than walking first
        direct = ride("d", ("NORD", 9 * H, 9 * H), ("MAD", 10 * H + 30 * M, 10 * H + 30 * M))
        j = profile(conns + direct, {"MAD"}, 10 * M, walks).best("NORD")
        self.assertEqual([l.trip for l in j.legs], ["d"])

    def test_several_targets(self):
        conns = ride("a", ("A", 8 * H, 8 * H), ("ATOCHA", 10 * H, 10 * H)) + \
            ride("b", ("A", 9 * H, 9 * H), ("CHAMARTIN", 10 * H + 30 * M, 10 * H + 30 * M))
        j = self.best(conns, targets=("ATOCHA", "CHAMARTIN"))
        self.assertEqual((j.duration, j.to), (90 * M, "CHAMARTIN"))
        self.assertIsNone(self.best(conns, targets=("ATOCHA", "CHAMARTIN"), stop="ATOCHA"))

    def test_times_past_midnight_stay_in_order(self):
        conns = ride("n", ("A", 23 * H, 23 * H), ("B", 24 * H + 30 * M, 24 * H + 35 * M), ("MAD", 26 * H, 26 * H))
        self.assertEqual(self.best(conns).arr, 26 * H)

    def test_connections_of_a_trip(self):
        got = trip_connections("t", [("A", 0, 10, True, True), ("B", 20, 25, False, False), ("C", 30, 30, True, True)])
        self.assertEqual(got, [Connection(10, 20, "A", "B", "t", True, False, 0),
                               Connection(25, 30, "B", "C", "t", False, True, 1)])


class FootpathTest(unittest.TestCase):
    def test_pairs_within_reach_at_walking_speed(self):
        # València Nord and Joaquín Sorolla are about 1 km apart; Gandia is 60 km away.
        coords = {"NORD": (-0.3772, 39.4660), "JS": (-0.3817, 39.4580), "G": (-0.1806, 38.9715)}
        got = footpaths(coords, 1.5, 4.5)
        self.assertEqual([j for j, _ in got["NORD"]], ["JS"])
        self.assertAlmostEqual(got["NORD"][0][1], 0.97 / 4.5 * 3600, delta=60)
        self.assertNotIn("G", got)


if __name__ == "__main__":
    unittest.main()
