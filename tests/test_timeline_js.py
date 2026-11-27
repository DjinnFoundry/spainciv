"""Who was alive in a year (web/js/ext/timeline/lifespan.js), on made-up people and on Spain's personajes.json. The
JavaScript twins of the builder (pipeline/build/spain_personajes.py: dominant, roman, ordinal, centuries) are pinned
against the Python output. Run with node; skipped without it."""

import json
import shutil
import subprocess
import unittest

from pipeline.build.spain_personajes import date_text
from pipeline.core.paths import ROOT

NODE = shutil.which("node")

PRELUDE = """
import { readFileSync } from 'node:fs';
const L = await import('./web/js/ext/timeline/lifespan.js');
const doc = JSON.parse(readFileSync('sites/es/data/personajes.json', 'utf8'));
const spain = doc.people;
const owner = JSON.parse(readFileSync('sites/es/data/world.json', 'utf8')).owner;
const P = L.pack(spain, doc.categories.length);
const out = (x) => console.log(JSON.stringify(x));
"""


def run(body: str):
    res = subprocess.run([NODE, "--input-type=module", "-e", PRELUDE + body], cwd=ROOT, capture_output=True, text=True)
    if res.returncode:
        raise AssertionError(res.stderr)
    return json.loads(res.stdout)


@unittest.skipUnless(NODE, "node is not installed")
class YearLayerTest(unittest.TestCase):
    def test_everyone_kept_gives_the_lenses_the_builder_wrote(self):
        # The JS count and tie rule are Python's hex_values and dominant(): exact equality on the whole map.
        got = run("""
            const all = L.yearLayer(P, owner, () => true);
            out({ count: all.count, kind: all.kind });
        """)
        lenses = {l["id"]: l for l in json.loads((ROOT / "sites/es/data/lenses.json").read_text())["lenses"]}
        self.assertEqual(got["count"], lenses["great_people"]["values"])
        self.assertEqual(got["kind"], lenses["great_people_kind"]["values"])

    def test_a_tie_goes_to_the_lowest_category(self):
        got = run("""
            const p = (cell, kind) => ({ cell, kind, life: [1, 2] });
            const tie = L.pack([p(1, 5), p(1, 2), p(1, 5), p(1, 2), p(2, 7)], 8);
            const layer = L.yearLayer(tie, [-1, 0, 0, 0], L.aliveIn(tie, 1));
            out(layer);
        """)
        self.assertEqual(got, {"count": [None, 4, 1, 0], "kind": [None, 2, 7, None],
                               "labels": [None, [0, 1, 2, 3], [4], None], "alive": 5})

    def test_the_year_1000(self):
        got = run("""
            const y = L.yearLayer(P, owner, L.aliveIn(P, 1000));
            const sum = y.count.reduce((a, b) => a + (b || 0), 0);
            const max = y.count.indexOf(Math.max(...y.count.filter((v) => v != null)));
            const labelled = y.labels.flatMap((l, c) => (l || []).map((k) => [c, k]));
            out({ sum, alive: y.alive, n: spain.filter((p) => L.alive(p, 1000)).length,
                  cordoba: [...new Set(y.labels[max].map((k) => spain[k].place))],
                  names: y.labels[max].map((k) => spain[k].name),
                  ordered: y.labels.every((l) => !l || l.every((k, i) => !i || l[i - 1] < k)),
                  onlyAlive: labelled.every(([c, k]) => spain[k].cell === c && L.alive(spain[k], 1000)) });
        """)
        self.assertEqual(got["sum"], got["n"])
        self.assertEqual(got["alive"], got["n"])
        self.assertIn("Córdoba", got["cordoba"])
        self.assertIn("Ibn Hazm", got["names"])
        self.assertTrue(got["ordered"] and got["onlyAlive"])

    def test_per_decade_is_the_brute_force_count(self):
        got = run("""
            const { min, max } = L.range(P, doc.timeline.until);
            const fast = L.perDecade(P, min, max);
            const slow = fast.counts.map((_, i) => {
              const d0 = fast.base + 10 * i;
              return spain.filter((p) => p.life && p.life[0] <= d0 + 9 && p.life[1] >= d0).length;
            });
            out({ min, max, base: fast.base, same: JSON.stringify(slow) === JSON.stringify(fast.counts), n: fast.counts.length });
        """)
        self.assertEqual((got["min"], got["max"], got["base"]), (-669, 2026, -670))
        self.assertEqual(got["n"], 270)
        self.assertTrue(got["same"])

    def test_famous_are_the_first_alive_in_file_order(self):
        got = run("""
            out([1520, 2026, -1000].map((y) => [L.famous(P, y, 10), spain.map((p, k) => [p, k]).filter(([p]) => L.alive(p, y)).slice(0, 10).map(([, k]) => k)]));
        """)
        for fast, slow in got:
            self.assertEqual(fast, slow)
        self.assertEqual(len(got[0][0]), 10)
        self.assertEqual(got[2][0], [])


@unittest.skipUnless(NODE, "node is not installed")
class YearStepsTest(unittest.TestCase):
    def test_steps_land_on_round_years(self):
        got = run("""
            out([L.next(1555, 10), L.prev(1555, 10), L.next(1550, 10), L.prev(1550, 10), L.next(1555, 100), L.prev(1555, 100),
                 L.next(-669, 100), L.prev(-599, 100), L.next(-669, 10), L.next(-9, 10), L.next(0, 10), L.prev(1, 10),
                 L.prev(0, 100), L.next(2020, 10, -669, 2026), L.prev(-660, 100, -669, 2026), L.next(2026, 100, -669, 2026),
                 L.next(-99, 100), L.prev(100, 100)]);
        """)
        # -669 = 670 BC → 600 BC (-599), 600 BC → 700 BC (-699); there is no year 0 to land on: 10 BC (-9) and 1 BC (0)
        # → AD 10, AD 1 → 10 BC (-9), 1 BC → 100 BC (-99), 100 BC → AD 100.
        self.assertEqual(got, [1560, 1550, 1560, 1540, 1600, 1500, -599, -699, -659, 10, 10, -9, -99, 2026, -669, 2026, 100,
                               -99])

    def test_a_year_from_the_url(self):
        got = run("out(['1550', '-669', '3000', '-5000', '1550.5', 'abc', '', null, ' 1550', '1e3'].map((v) => L.parseYear(v, -669, 2026)));")
        self.assertEqual(got, [1550, -669, 2026, -669, None, None, None, None, None, None])

    def test_historical_years_and_centuries_match_the_builder(self):
        years = [-669, -100, -99, 0, 1, 100, 101, 1500, 1501, 1550, 2026]
        got = run(f"""
            const es = (await import('./web/js/i18n/es/timeline.js')).default, en = (await import('./web/js/i18n/en/timeline.js')).default;
            const fill = (s, c) => s.replace('{{c}}', c);
            out({{ h: [L.historical(0), L.historical(-669)],
                  es: {json.dumps(years)}.map((y) => {{ const {{ c, bc }} = L.century(y); return fill(es[bc ? 'timeline.centuryBc' : 'timeline.century'], L.roman(c)); }}),
                  en: {json.dumps(years)}.map((y) => {{ const {{ c, bc }} = L.century(y); return fill(en[bc ? 'timeline.centuryBc' : 'timeline.century'], L.ordinal(c)); }}),
                  ord: [1, 2, 3, 4, 11, 12, 13, 21, 22, 101, 111, 112].map(L.ordinal) }});
        """)
        self.assertEqual(got["h"], [{"n": 1, "bc": True}, {"n": 670, "bc": True}])
        self.assertEqual(got["es"], [date_text({"year": y, "precision": 7}) for y in years])
        self.assertEqual(got["en"], [date_text({"year": y, "precision": 7}, "en") for y in years])
        self.assertEqual(got["es"][0], "s. VII a. C.")
        from pipeline.build.spain_personajes import ordinal
        self.assertEqual(got["ord"], [ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 101, 111, 112)])


if __name__ == "__main__":
    unittest.main()
