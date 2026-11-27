"""The reservoirs' weekly series in the browser (web/js/ext/embalses/series.js): the week of a URL, Spain's and the
basins' fill, the series' extremes, the same week a year on, rings and the hex values, on made-up basins and on
Spain's embalses.json. Run with node; skipped without it."""

import json
import shutil
import subprocess
import unittest

from pipeline.core.paths import ROOT

NODE = shutil.which("node")

PRELUDE = """
import { readFileSync } from 'node:fs';
const S = await import('./web/js/ext/embalses/series.js');
const spain = JSON.parse(readFileSync('sites/es/data/embalses.json', 'utf8'));
const out = (x) => console.log(JSON.stringify(x));
const dates = ['1995-10-31', '1995-11-07', '1995-11-14', '1996-11-05', '1996-11-12'];
const basins = [
  { name: 'Segura', cells: [1, 2], actual: [90, 83, null, 300, 310], capacity: [1078, 1078, null, 1100, 1100] },
  { name: 'Ebro', cells: [4], actual: [2000, 2426, 2500, 5000, 5100], capacity: [6383, 6383, 6383, 7000, 7000] },
];
"""


def run(body: str):
    res = subprocess.run([NODE, "--input-type=module", "-e", PRELUDE + body], cwd=ROOT, capture_output=True, text=True)
    if res.returncode:
        raise AssertionError(res.stderr)
    return json.loads(res.stdout)


@unittest.skipUnless(NODE, "node is not installed")
class WeekTest(unittest.TestCase):
    def test_week_from_the_url(self):
        got = run("out(['1995-11-07', '1995-11-09', '1995-10-31', '1995-10-30', '2030-01-01', '1995-02-30', '7-11-1995', "
                  "'', null, 'semana'].map((v) => S.parseWeek(v, dates)));")
        # exact; between two Tuesdays → the one before; the first; before the first → none; after the last → the last
        self.assertEqual(got, [1, 1, 0, None, 4, None, None, None, None, None])

    def test_same_week_a_year_on(self):
        got = run("out([S.sameWeekNextYear(dates, 1), S.sameWeekNextYear(dates, 3), S.sameWeekIn(dates, 1, 1996), "
                  "S.sameWeekIn(dates, 1, 1990)]);")
        self.assertEqual(got, [3, None, 3, None])

    def test_same_week_on_the_real_dates_never_drifts(self):
        got = run("""
            const i = S.parseWeek('1995-11-07', spain.dates), first = +spain.dates[0].slice(0, 4), last = +spain.dates.at(-1).slice(0, 4);
            const weeks = [];
            for (let y = first; y <= last; y++) { const j = S.sameWeekIn(spain.dates, i, y); if (j != null) weeks.push(spain.dates[j]); }
            out(weeks);""")
        self.assertEqual(len(got), 39)
        self.assertEqual((got[0], got[7], got[-1]), ("1988-11-08", "1995-11-07", "2026-11-10"))
        for d in got:  # each within half a week of 7 November
            self.assertTrue("11-04" <= d[5:] <= "11-10", d)


@unittest.skipUnless(NODE, "node is not installed")
class FillTest(unittest.TestCase):
    def test_national_and_basins(self):
        got = run("out([S.national(basins, 1), S.national(basins, 2), S.basinPct(basins[0], 2), S.basinPct(basins[0], 1)]);")
        self.assertEqual(got[0], {"actual": 2509, "capacity": 7461, "pct": 2509 / 7461})
        self.assertEqual(got[1], {"actual": 2500, "capacity": 6383, "pct": 2500 / 6383})  # Segura did not report
        self.assertIsNone(got[2])
        self.assertAlmostEqual(got[3], 83 / 1078)

    def test_extremes_of_the_real_series(self):
        got = run("const e = S.extremes(spain.basins); out([spain.dates[e.min], spain.dates[e.max], "
                  "S.national(spain.basins, e.min).pct, S.national(spain.basins, e.max).pct]);")
        self.assertEqual(got[:2], ["1995-11-07", "2013-05-07"])
        self.assertEqual((round(got[2] * 100, 1), round(got[3] * 100, 1)), (24.8, 85.8))

    def test_driest_first(self):
        got = run("out([S.basinsByDryness(basins, 1), S.basinsByDryness(basins, 2), S.basinsByDryness(basins, 4)]);")
        self.assertEqual(got, [[0, 1], [1, 0], [0, 1]])

    def test_hex_values_null_outside_the_basins(self):
        got = run("out(S.hexValues(basins, 1, 6));")
        self.assertEqual(got[0], None)
        self.assertAlmostEqual(got[1], 83 / 1078)
        self.assertEqual(got[3], None)
        self.assertEqual(got[5], None)
        # On Spain's map: every peninsular land hex has a value, no hex of the islands, Ceuta or Melilla does.
        got = run("""
            const world = JSON.parse(readFileSync('sites/es/data/world.json', 'utf8'));
            const v = S.hexValues(spain.basins, spain.dates.length - 1, world.owner.length);
            const off = new Set(['07', '35', '38', '51', '52']), count = {};
            world.owner.forEach((o, c) => {
              if (o < 0) return;
              const k = (off.has(world.states[o].fips) ? 'off' : 'pen') + (v[c] == null ? 'Null' : 'Value');
              count[k] = (count[k] || 0) + 1;
            });
            out(count);""")
        self.assertEqual(set(got), {"offNull", "penValue"})


@unittest.skipUnless(NODE, "node is not installed")
class RingTest(unittest.TestCase):
    def test_arc_capped_over_capacity(self):
        got = run("out([S.ringArc(43, 91), S.ringArc(8, 5), S.ringArc(0, 5), S.ringArc(null, 5), S.ringArc(3, 0)]);")
        self.assertAlmostEqual(got[0]["frac"], 43 / 91)
        self.assertFalse(got[0]["over"])
        self.assertEqual(got[1], {"frac": 1, "over": True})
        self.assertEqual(got[2], {"frac": 0, "over": False})
        self.assertEqual(got[3:], [None, None])

    def test_radius_and_capacity_runs(self):
        got = run("out([[1, 50, 200, 5000].map(S.ringRadius), [0, 3, 4, 9].map((i) => S.capacityAt([[0, 210], [4, 203]], i)), "
                  "S.capacityAt([[2, 5]], 1)]);")
        self.assertEqual(got[0], [3, 3, 6, 14])
        self.assertEqual(got[1:], [[210, 210, 203, 203], None])

    def test_reporting_needs_the_matrix_off_the_latest_week(self):
        got = run("""
            const res = [{ last: 4, actual: 7, capacity: 10 }, { last: 2, actual: 1, capacity: 2 }];
            const weeks = { actual: [[1, null], [2, 1], [3, 1], [4, null], [7, null]], capacity: [[[0, 9], [3, 10]], [[0, 2]]] };
            out([S.reporting(res, null, 4, 4), S.reporting(res, null, 2, 4), S.reporting(res, weeks, 2, 4)]);""")
        self.assertEqual(got[0], [{"k": 0, "actual": 7, "capacity": 10}])
        self.assertIsNone(got[1])
        self.assertEqual(got[2], [{"k": 0, "actual": 3, "capacity": 9}, {"k": 1, "actual": 1, "capacity": 2}])


if __name__ == "__main__":
    unittest.main()
