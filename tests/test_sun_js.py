"""The sunset lens (web/js/ext/sun/solar.js): the sun's times against NOAA's calculator, Spain's clocks and summer
time, and the lens on Spain's hexes (web/js/geo.js gives each hex's longitude and latitude). Run with node; skipped
without it."""

import json
import shutil
import subprocess
import unittest

from pipeline.core.paths import ROOT

NODE = shutil.which("node")

PRELUDE = """
import { readFileSync } from 'node:fs';
const S = await import('./web/js/ext/sun/solar.js');
const { clock } = await import('./web/js/format.js');
const { makeGrid } = await import('./web/js/hex.js');
const { mapProjection } = await import('./web/js/geo.js');
const out = (x) => console.log(JSON.stringify(x));
const day = (s) => S.parseDay(s);
const spain = () => {
  const w = JSON.parse(readFileSync('sites/es/data/world.json', 'utf8'));
  const grid = makeGrid(w.grid), proj = mapProjection(w.country.projection);
  const points = [];
  for (let i = 0; i < grid.size; i++) {
    if (w.owner[i] < 0) continue;
    const [lon, lat] = proj.inverse(grid.cx(i), grid.cy(i));
    points.push({ cell: i, lon, lat });
  }
  const near = (lat, lon) => points.reduce((a, p) => (Math.hypot(p.lat - lat, (p.lon - lon) * Math.cos(lat * Math.PI / 180))
    < Math.hypot(a.lat - lat, (a.lon - lon) * Math.cos(lat * Math.PI / 180)) ? p : a));
  return { w, grid, points, near, place: (cell) => w.counties[w.county[cell]].name };
};
"""

# Sunrise, solar noon and sunset (local clock) from NOAA's own calculator code (https://gml.noaa.gov/grad/solcalc/,
# its main.js: calcSunriseSet and calcSolNoon, shown to the minute with its timeString), run for these places with
# the official offset of each day: CET/CEST in Madrid, A Coruña and Maó, WET/WEST in Las Palmas.
PLACES = {"Madrid": (40.4168, -3.7038), "A Coruña": (43.3623, -8.4115), "Maó": (39.8885, 4.2658), "Las Palmas": (28.1235, -15.4363)}
NOAA = {
    ("Madrid", "2026-03-20"): ("07:18", "13:22", "19:27"),
    ("Madrid", "2026-06-21"): ("06:45", "14:17", "21:49"),
    ("Madrid", "2026-09-23"): ("08:03", "14:07", "20:11"),
    ("Madrid", "2026-12-21"): ("08:34", "13:13", "17:51"),
    ("A Coruña", "2026-03-20"): ("07:37", "13:41", "19:46"),
    ("A Coruña", "2026-06-21"): ("06:53", "14:35", "22:18"),
    ("A Coruña", "2026-09-23"): ("08:22", "14:26", "20:29"),
    ("A Coruña", "2026-12-21"): ("09:03", "13:31", "18:01"),
    ("Maó", "2026-03-20"): ("06:47", "12:51", "18:55"),
    ("Maó", "2026-06-21"): ("06:15", "13:45", "21:15"),
    ("Maó", "2026-09-23"): ("07:31", "13:36", "19:39"),
    ("Maó", "2026-12-21"): ("08:01", "12:41", "17:21"),
    ("Las Palmas", "2026-03-20"): ("07:06", "13:09", "19:13"),
    ("Las Palmas", "2026-06-21"): ("07:06", "14:03", "21:01"),
    ("Las Palmas", "2026-09-23"): ("07:51", "13:54", "19:57"),
    ("Las Palmas", "2026-12-21"): ("07:49", "13:00", "18:11"),
}
TOLERANCE = 2  # minutes


def run(body: str):
    res = subprocess.run([NODE, "--input-type=module", "-e", PRELUDE + body], cwd=ROOT, capture_output=True, text=True)
    if res.returncode:
        raise AssertionError(res.stderr)
    return json.loads(res.stdout)


def minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


@unittest.skipUnless(NODE, "node is not installed")
class NoaaTest(unittest.TestCase):
    def test_times_match_noaas_calculator(self):
        cases = [[name, date, *PLACES[name]] for name, date in NOAA]
        got = run(f"""
            out({json.dumps(cases)}.map(([name, date, lat, lon]) => {{
              const s = S.sunDay(day(date), lat, lon);
              return [clock(s.sunrise), clock(s.noon), clock(s.sunset), s.abbr];
            }}));
        """)
        for (name, date, _, _), (rise, noon, sset, abbr) in zip(cases, got):
            with self.subTest(place=name, date=date):
                for mine, ref in zip((rise, noon, sset), NOAA[name, date]):
                    self.assertLessEqual(abs(minutes(mine) - minutes(ref)), TOLERANCE, (mine, ref))
                summer = date[5:7] in ("06", "09")
                self.assertEqual(abbr, ("WEST" if summer else "WET") if name == "Las Palmas" else ("CEST" if summer else "CET"))

    def test_day_length_is_the_sunset_minus_the_sunrise_shown(self):
        got = run("const s = S.sunDay(day('2026-06-21'), 40.4168, -3.7038); out([s.day, s.sunset - s.sunrise, s.exact.day]);")
        self.assertEqual(got[0], got[1])
        self.assertAlmostEqual(got[0], got[2], delta=1)


@unittest.skipUnless(NODE, "node is not installed")
class ClockTest(unittest.TestCase):
    def test_summer_time_follows_the_eu_rule(self):
        # 2026: from Sunday 29 March to Sunday 25 October; 2027: 28 March to 31 October.
        got = run("out(['2026-03-28', '2026-03-29', '2026-10-24', '2026-10-25', '2027-03-27', '2027-03-28', '2027-10-30', "
                  "'2027-10-31', '2026-01-15', '2026-07-15'].map((d) => S.summerTime(day(d))));")
        self.assertEqual(got, [False, True, True, False, False, True, True, False, False, True])

    def test_zones_of_spain(self):
        got = run("""
            out([[-3.70, '2026-01-15'], [4.27, '2026-07-15'], [-5.32, '2026-07-15'], [-2.94, '2026-01-15'],
                 [-15.44, '2026-01-15'], [-17.92, '2026-07-15']].map(([lon, d]) => S.clockOf(S.zoneOf(lon), day(d))));
        """)
        # Madrid, Maó, Ceuta, Melilla: Central European Time; Las Palmas, El Hierro: Western European Time.
        self.assertEqual(got, [{"offset": 1, "abbr": "CET"}, {"offset": 2, "abbr": "CEST"}, {"offset": 2, "abbr": "CEST"},
                               {"offset": 1, "abbr": "CET"}, {"offset": 0, "abbr": "WET"}, {"offset": 1, "abbr": "WEST"}])

    def test_days_from_the_url_and_the_clock_format(self):
        got = run("""
            out([['2026-06-21', '2024-02-29', '2026-02-29', '2026-13-01', '2026-6-21', 'hoy', '', null, '1900-01-01']
                   .map((v) => S.parseDay(v) && S.isoDay(S.parseDay(v))),
                 [0, 59.5, 1321, 1439.6, -1].map(clock), S.localDay(new Date(2026, 5, 21, 23, 59))]);
        """)
        self.assertEqual(got, [["2026-06-21", "2024-02-29", None, None, None, None, None, None, None],
                               ["00:00", "01:00", "22:01", "00:00", "23:59"], {"y": 2026, "m": 6, "d": 21}])


@unittest.skipUnless(NODE, "node is not installed")
class SpainLensTest(unittest.TestCase):
    def test_the_hex_of_each_place_gives_its_noaa_time(self):
        # A hex is about 10 km across: its centre is at most a few km from the place, well under a minute of sun.
        cases = [[name, date, *PLACES[name]] for name, date in NOAA if date == "2026-06-21" or date == "2026-12-21"]
        got = run(f"""
            const {{ points, near, place }} = spain();
            out({json.dumps(cases)}.map(([name, date, lat, lon]) => {{
              const p = near(lat, lon);
              const layer = S.sunLayer(points, 1 + points.at(-1).cell, day(date), 'sunset');
              return [place(p.cell), clock(layer.values[p.cell]), layer.days[p.cell].abbr];
            }}));
        """)
        for (name, date, _, _), (where, sset, abbr) in zip(cases, got):
            with self.subTest(place=name, date=date):
                self.assertLessEqual(abs(minutes(sset) - minutes(NOAA[name, date][2])), TOLERANCE, (where, sset))
                self.assertEqual(abbr[0], "W" if name == "Las Palmas" else "C")

    def test_spread_runs_from_the_far_west_to_the_far_east(self):
        got = run("""
            const { points, place } = spain();
            const n = 1 + points.at(-1).cell;
            const res = {};
            for (const [d, mode] of [['2026-06-21', 'sunset'], ['2026-06-21', 'noon'], ['2026-12-21', 'sunrise'], ['2026-06-21', 'day']]) {
              const l = S.sunLayer(points, n, day(d), mode);
              const lonOf = (c) => points.find((p) => p.cell === c).lon;
              res[`${d} ${mode}`] = { high: place(l.high.cell), low: place(l.low.cell), diff: l.high.value - l.low.value,
                highLon: lonOf(l.high.cell), lowLon: lonOf(l.low.cell),
                painted: l.values.filter((v) => v != null).length, land: points.length };
            }
            out(res);
        """)
        # Solar noon: one clock from the Costa da Morte (Muxía, beside Fisterra) to Maó, 13.5° of longitude apart.
        noon = got["2026-06-21 noon"]
        self.assertEqual((noon["high"], noon["low"], noon["diff"]), ("Muxía", "Maó", 54))
        # The latest sunset of the summer solstice is on the Galician coast; the earliest in the Canaries, whose clock
        # is an hour behind (Fuerteventura and Lanzarote, the easternmost islands).
        june = got["2026-06-21 sunset"]
        self.assertLess(june["highLon"], -9)
        self.assertTrue(-14.6 < june["lowLon"] < -13, june)
        self.assertTrue(75 <= june["diff"] <= 95, june)
        self.assertEqual(june["painted"], june["land"])
        # In December the latest sunrise is in the far west too; the longest summer day in the far north.
        self.assertLess(got["2026-12-21 sunrise"]["highLon"], -9)
        self.assertGreater(got["2026-06-21 day"]["diff"], 60)


if __name__ == "__main__":
    unittest.main()
