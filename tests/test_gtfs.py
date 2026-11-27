"""pipeline/core/gtfs.py: GTFS read from a zip as the Spanish feeds write it, and the choice of a representative day."""

import io
import unittest
import zipfile
from datetime import date

from pipeline.core.archive import zip_bytes
from pipeline.core.gtfs import Calendar, NoDayError, clock, columns, days_between, failing, pick_day, seconds, trips_by_day


def feed(**files: str) -> zipfile.ZipFile:
    """A GTFS zip from {file stem: CSV text}."""
    return zipfile.ZipFile(io.BytesIO(zip_bytes({f"{k}.txt": v.encode("utf-8") for k, v in files.items()})))


class ReadTest(unittest.TestCase):
    def test_padded_fields_bom_and_missing_columns(self):
        z = feed(stops="﻿stop_id ,stop_name                ,stop_lat\n04040,Zaragoza Delicias       ,41.65\n\n")
        self.assertEqual(list(columns(z, "stops.txt", ("stop_id", "stop_name", "stop_lon"))),
                         [("04040", "Zaragoza Delicias", "")])
        self.assertEqual(list(columns(z, "shapes.txt", ("shape_id",))), [])

    def test_times_without_a_leading_zero_and_past_midnight(self):
        self.assertEqual(seconds("8:30:00"), 30600)
        self.assertEqual(seconds(" 08:30:00 "), 30600)
        self.assertEqual(seconds("25:10:00"), 90600)
        self.assertEqual(clock(90600), "25:10")
        self.assertEqual(clock(30600), "08:30")


class CalendarTest(unittest.TestCase):
    Z = feed(
        calendar="service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
                 "WK,1,1,1,1,1,0,0,20261201,20261231\n"
                 "SAT,0,0,0,0,0,1,0,20261201,20261231\n",
        calendar_dates="service_id,date,exception_type\nWK,20261208,2\nXTRA,20261208,1\nXTRA,20270105,1\n",
    )

    def test_weekly_patterns_and_exceptions(self):
        cal = Calendar(self.Z)
        self.assertEqual(cal.on(date(2026, 12, 9)), {"WK"})
        self.assertEqual(cal.on(date(2026, 12, 12)), {"SAT"})
        self.assertEqual(cal.on(date(2026, 12, 8)), {"XTRA"})  # removed WK, added XTRA
        self.assertEqual(cal.on(date(2026, 11, 30)), set())
        self.assertEqual(cal.window(), (date(2026, 12, 1), date(2027, 1, 5)))

    def test_a_feed_with_only_calendar_dates(self):
        cal = Calendar(feed(calendar_dates="service_id,date,exception_type\nA,20261209,1\n"))
        self.assertEqual(cal.on(date(2026, 12, 9)), {"A"})
        self.assertEqual(cal.window(), (date(2026, 12, 9), date(2026, 12, 9)))
        self.assertIsNone(Calendar(feed()).window())

    def test_trips_by_day_per_group(self):
        cal = Calendar(self.Z)
        days = days_between(date(2026, 12, 8), date(2026, 12, 9))
        got = trips_by_day([("WK", "10"), ("WK", "10"), ("XTRA", "51"), ("SAT", "10")], cal, days)
        self.assertEqual(got, {"10": {date(2026, 12, 8): 0, date(2026, 12, 9): 2},
                               "51": {date(2026, 12, 8): 1, date(2026, 12, 9): 0}})


class PickDayTest(unittest.TestCase):
    TUE1, WED2, THU3, TUE8, WED9, THU10 = (date(2026, 12, d) for d in (1, 2, 3, 8, 9, 10))

    def counts(self, **groups):
        return {g: dict(zip((self.TUE1, self.WED2, self.THU3, self.TUE8, self.WED9, self.THU10), v)) for g, v in groups.items()}

    def test_a_network_with_no_trips_is_skipped(self):
        # Rodalies (51) runs nothing from 1 to 3 December; the 8th is a holiday below 90 %.
        c = self.counts(av=[1610, 1600, 1610, 1410, 1600, 1610], **{"51": [0, 0, 0, 900, 905, 905]})
        cands = [self.TUE1, self.WED2, self.THU3, self.TUE8, self.WED9, self.THU10]
        self.assertEqual(pick_day(c, cands, 0.9), self.WED9)
        self.assertEqual(failing(c, self.TUE1, 0.9), ["51 0/900"])
        self.assertEqual(failing(c, self.TUE8, 0.9), ["av 1410/1610"])

    def test_each_day_against_its_own_weekday(self):
        # Iryo runs 60 trains on Wednesdays and 68 on Thursdays: a Wednesday is full at 60.
        c = self.counts(iryo=[64, 60, 68, 64, 60, 68])
        self.assertEqual(pick_day(c, [self.WED2, self.THU3], 0.9), self.WED2)
        # Against the busiest day of any weekday, 60 < 0.9 × 68 would skip every Wednesday.
        self.assertLess(60, 0.9 * 68)

    def test_no_candidate_raises(self):
        c = self.counts(av=[1000, 1000, 1000, 10, 10, 10])
        with self.assertRaises(NoDayError):
            pick_day(c, [self.TUE8, self.WED9, self.THU10], 0.9)


if __name__ == "__main__":
    unittest.main()
