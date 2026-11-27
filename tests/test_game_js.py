"""The daily game "Adivina el hexágono" (web/js/ext/game/puzzle.js): the day's hex, distances, points, the share
text, the saved stats and the clues it builds from Spain's data (sites/es/data). Run with node; skipped without it."""

import json
import shutil
import subprocess
import unittest

from pipeline.core.paths import ROOT

NODE = shutil.which("node")

# Spain's data in `lang` (with its overlay), the world prepared as the map prepares it, and the puzzle module.
PRELUDE = """
import { readFileSync } from 'node:fs';
import { setCountry } from './web/js/app/country.js';
import { overlay } from './web/js/app/data.js';
const LANG = %(lang)s;
const file = (n) => JSON.parse(readFileSync(`sites/es/data/${n}.json`, 'utf8'));
const load = (n) => (LANG === 'es' ? file(n) : overlay(file(n), file(`${n}.${LANG}`)));
const world = load('world');
setCountry({ country: { ...world.country, lang: LANG, locale: LANG === 'es' ? 'es-ES' : 'en-IE' } }, null);
const { prepareWorld } = await import('./web/js/world.js');
const { mapProjection } = await import('./web/js/geo.js');
const { formatLensValue } = await import('./web/js/ui/lenses.js');
const P = await import('./web/js/ext/game/puzzle.js');
const cities = load('cities');
const w = prepareWorld(world, cities, {});
const lenses = new Map(load('lenses').lenses.map((l) => [l.id, l]));
const proj = mapProjection(world.country.projection);
const pool = P.puzzlePool(w.raw, lenses.get('density'));
const names = [...w.raw.counties, ...w.raw.states, ...cities].map((x) => x.name);
const people = load('personajes').people;
const out = (x) => console.log(JSON.stringify(x));
"""


def run(body: str, lang: str = "es"):
    script = PRELUDE % {"lang": json.dumps(lang)} + body
    res = subprocess.run([NODE, "--input-type=module", "-e", script], cwd=ROOT, capture_output=True, text=True)
    if res.returncode:
        raise AssertionError(res.stderr)
    return json.loads(res.stdout)


@unittest.skipUnless(NODE, "node is not installed")
class DailyPickTest(unittest.TestCase):
    def test_day_number_follows_the_local_calendar_day(self):
        got = run("out([P.dayNumber(new Date(2026, 10, 27, 0, 1)), P.dayNumber(new Date(2026, 10, 27, 23, 59)), "
                  "P.dayNumber(new Date(2026, 10, 28, 0, 0)), P.dayNumber(new Date(2026, 10, 26, 12)), P.dayNumber(new Date(2027, 10, 27))]);")
        self.assertEqual(got, [1, 1, 2, 0, 366])

    def test_pool_is_inhabited_land_with_a_municipality(self):
        got = run("""
            const d = lenses.get('density').values;
            out({ n: pool.length, sorted: pool.every((c, k) => !k || pool[k - 1] < c),
                  ok: pool.every((c) => w.raw.owner[c] >= 0 && w.raw.county[c] >= 0 && d[c] >= P.POOL_DENSITY),
                  missed: d.filter((v, c) => v >= P.POOL_DENSITY && w.raw.owner[c] >= 0 && w.raw.county[c] >= 0).length });
        """)
        self.assertTrue(got["sorted"] and got["ok"])
        self.assertEqual(got["missed"], got["n"])
        self.assertGreater(got["n"], 1000)

    def test_the_same_hex_for_everyone_and_no_repeat_until_the_pool_runs_out(self):
        got = run("""
            const days = Array.from({ length: pool.length }, (_, k) => P.dailyCell(pool, k + 1));
            out({ again: P.dailyCell([...pool], 1) === days[0], distinct: new Set(days).size, n: pool.length,
                  inPool: days.every((c) => pool.includes(c)), wraps: P.dailyCell(pool, pool.length + 1) === days[0],
                  before: P.dailyCell(pool, 0) === days[pool.length - 1], notInOrder: days.slice(0, 5).join() !== pool.slice(0, 5).join(),
                  first: days.slice(0, 3) });
        """)
        self.assertTrue(got["again"] and got["inPool"] and got["wraps"] and got["before"] and got["notInOrder"])
        self.assertEqual(got["distinct"], got["n"])
        # A changed seed, pool rule or epoch changes every day's puzzle: this pins them.
        self.assertEqual(got["first"], [12111, 9667, 14885])


@unittest.skipUnless(NODE, "node is not installed")
class DistanceAndPointsTest(unittest.TestCase):
    def test_distances_are_on_the_ground_even_across_the_canary_inset(self):
        got = run("""
            const at = (lon, lat) => { // the map hex nearest a lon/lat, by brute force over the land
              let best = -1, bd = Infinity;
              for (let i = 0; i < w.grid.size; i++) {
                if (w.raw.owner[i] < 0) continue;
                const [x, y] = proj.inverse(w.grid.cx(i), w.grid.cy(i)), d = (x - lon) ** 2 + (y - lat) ** 2;
                if (d < bd) { bd = d; best = i; }
              }
              return best;
            };
            const madrid = at(-3.7038, 40.4168), bcn = at(2.1734, 41.3851), lpa = at(-15.43, 28.1);
            out([P.cellKm(w.grid, proj, madrid, madrid), P.cellKm(w.grid, proj, madrid, bcn), P.cellKm(w.grid, proj, madrid, lpa),
                 P.haversineKm([-3.7038, 40.4168], [2.1734, 41.3851])]);
        """)
        self.assertEqual(got[0], 0)
        self.assertAlmostEqual(got[1], got[3], delta=12)  # hex centres are within ~6 km of the cities
        self.assertAlmostEqual(got[3], 505, delta=3)
        self.assertAlmostEqual(got[2], 1750, delta=30)  # Madrid–Las Palmas, not the inset's map distance

    def test_arrow_points_from_the_guess_to_the_hex_on_the_map(self):
        got = run("""
            const g = { cx: (i) => [0, 10, 0, -10, 10][i], cy: (i) => [0, 0, -10, 0, 10][i] };
            out([P.arrow(g, 0, 1), P.arrow(g, 0, 2), P.arrow(g, 0, 3), P.arrow(g, 0, 4), P.arrow(g, 4, 0), P.arrow(g, 0, 0)]);
        """)
        self.assertEqual(got, ["→", "↑", "←", "↘", "↖", ""])  # map y runs down

    def test_points_and_squares(self):
        got = run("""out([[0, 25, 25.4, 312.5, 600, 900].map(P.distancePoints), P.score(10, 1), P.score(10, 3), P.score(200, 6),
                         P.score(900, 6), [25, 26, 100, 101, 300, 301].map(P.square)]);""")
        self.assertEqual(got[0], [100, 100, 100, 50, 0, 0])
        self.assertEqual(got[1:5], [100, 80, 20, 0])
        self.assertEqual(got[5], ["🟩", "🟨", "🟨", "🟧", "🟧", "🟥"])

    def test_standing_wins_within_hit_km_and_ends_after_six_guesses(self):
        got = run("""
            const cell = P.dailyCell(pool, 1), far = pool.find((c) => P.cellKm(w.grid, proj, c, cell) > 400);
            const s = (guesses, clues = 1) => P.standing({ grid: w.grid, proj, cell, guesses, clues });
            out([s([cell]), s([far, far, far, far, far], 5).over, s(Array(6).fill(far), 9)]);
        """)
        self.assertEqual(got[0], {"kms": [0], "best": 0, "won": True, "over": True, "clues": 1})
        self.assertFalse(got[1])
        self.assertTrue(got[2]["over"])
        self.assertFalse(got[2]["won"])
        self.assertEqual(got[2]["clues"], 6)


@unittest.skipUnless(NODE, "node is not installed")
class ShareAndStatsTest(unittest.TestCase):
    BODY = """out([P.shareText({ day: 12, kms: [412, 180, 64, 8], won: true, clues: 4, url: 'https://x/#juego' }),
                   P.shareText({ day: 3, kms: [700, 650, 640, 630, 620, 610], won: false, clues: 6, url: 'u' })]);"""

    def test_share_text_in_both_languages_without_the_place(self):
        es = run(self.BODY)
        self.assertEqual(es[0], "Adivina el hexágono n.º 12 · 4/6 · 70 puntos\n🟥🟧🟨🟩\nPistas: 4/6\nhttps://x/#juego")
        self.assertEqual(es[1], "Adivina el hexágono n.º 3 · X/6 · 0 puntos\n🟥🟥🟥🟥🟥🟥\nPistas: 6/6\nu")
        en = run(self.BODY, "en")
        self.assertEqual(en[0], "Guess the hex No. 12 · 4/6 · 70 points\n🟥🟧🟨🟩\nClues: 4/6\nhttps://x/#juego")
        self.assertIn("X/6 · 0 points", en[1])

    def test_streaks(self):
        got = run("""
            let s = P.recordResult(undefined, 5, true);
            const a = s;
            s = P.recordResult(s, 6, true);
            const b = s, again = P.recordResult(s, 6, false);
            s = P.recordResult(s, 8, true);
            const c = s;
            s = P.recordResult(s, 9, false);
            out([a, b, again === b || JSON.stringify(again) === JSON.stringify(b), c, s,
                 [P.currentStreak(b, 6), P.currentStreak(b, 7), P.currentStreak(b, 8), P.currentStreak(null, 8)]]);
        """)
        self.assertEqual(got[0], {"played": 1, "won": 1, "streak": 1, "best": 1, "lastDay": 5, "lastWin": 5})
        self.assertEqual(got[1], {"played": 2, "won": 2, "streak": 2, "best": 2, "lastDay": 6, "lastWin": 6})
        self.assertTrue(got[2])  # a day counts once
        self.assertEqual((got[3]["streak"], got[3]["best"]), (1, 2))  # day 7 was missed
        self.assertEqual(got[4], {"played": 4, "won": 3, "streak": 0, "best": 2, "lastDay": 9, "lastWin": 8})
        self.assertEqual(got[5], [2, 2, 0, 0])


@unittest.skipUnless(NODE, "node is not installed")
class CluesTest(unittest.TestCase):
    def test_masker_hides_place_names_as_whole_words(self):
        got = run("""const m = P.placeMasker(['Villaviciosa', 'Alicante/Alacant', 'Vic', 'Sella'], ['Vic']);
            out([m('Festival de la Manzana, Villaviciosa'), m('Hogueras de Alacant'), m('Salchichón de Vic'), m('Sellado de Vicente')]);""")
        self.assertEqual(got, ["Festival de la Manzana, …", "Hogueras de …", "Salchichón de …", "Sellado de Vicente"])

    def test_clues_come_from_the_data(self):
        for lang in ("es", "en"):
            got = run("""
                const cell = P.dailyCell(pool, 300);
                const clues = P.buildClues({ w, lenses, people, names }, cell);
                const L = (id) => lenses.get(id);
                out({ ids: clues.map((c) => c.id), titles: clues.map((c) => c.title), facts: clues.map((c) => c.facts),
                      density: formatLensValue(L('density'), L('density').values[cell]),
                      lang: formatLensValue(L('languages'), L('languages').values[cell]),
                      castles: L('castles').values[cell], unitCastles: L('castles').unit,
                      relief: w.tables.relief.find((r) => r.id === w.relief[cell]).name, elev: world.elev[cell],
                      initial: w.raw.states[w.raw.owner[cell]].name[0],
                      person: people.find((p) => p.cell === cell), foodName: L('food').name, foods: (L('food').labels[cell] || []).map((k) => L('food').names[k]) });
            """, lang)
            self.assertEqual(got["ids"], ["terrain", "people", "money", "roots", "heritage", "last"])
            self.assertTrue(all(got["titles"]) and all(got["facts"]), lang)
            values = {f["label"]: f["value"] for clue in got["facts"] for f in clue}
            flat = [f["value"] for clue in got["facts"] for f in clue]
            self.assertIn(got["density"], flat)
            self.assertIn(got["lang"], flat)
            self.assertIn(got["relief"], flat)
            self.assertIn(f"{got['elev']} m", flat)
            self.assertEqual(values[got["unitCastles"][0].upper() + got["unitCastles"][1:]], str(got["castles"]))
            self.assertIn(f"«{got['initial']}»", flat)
            self.assertIn(got["person"]["name"], " ".join(flat))
            # A denomination of the hex, with any place name in it hidden.
            food = values[got["foodName"]]
            self.assertTrue(any(f == food or ("…" in food and f.startswith(food.split("…")[0])) for f in got["foods"]), food)

    def test_no_clue_names_the_answer(self):
        """Over the first 200 days no clue holds the answer's municipality or province name."""
        got = run("""
            const leaks = [];
            for (let d = 1; d <= 200; d++) {
              const cell = P.dailyCell(pool, d);
              const text = P.buildClues({ w, lenses, people, names }, cell).flatMap((c) => c.facts.map((f) => f.value)).join(' | ');
              const own = [w.raw.counties[w.raw.county[cell]].name, ...w.raw.states[w.raw.owner[cell]].name.split('/')];
              for (const n of own) {
                const re = new RegExp(`(?<![\\\\p{L}])${n.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&')}(?![\\\\p{L}])`, 'iu');
                if (re.test(text)) leaks.push([d, n, text]);
              }
            }
            out(leaks);
        """)
        self.assertEqual(got, [])


if __name__ == "__main__":
    unittest.main()
