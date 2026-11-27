"""The daily game "Adivina el hexágono" (web/js/ext/game/puzzle.js): the day's hex, distances, points, the share
text, the saved game and stats, the clues it builds from Spain's data (sites/es/data) and how far they narrow the
answer. Run with node; skipped without it."""

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
const names = [...w.raw.counties, ...w.raw.states, ...cities].map((x) => x.name);
const people = load('personajes').people;
const g = P.gameData({ w, proj, lenses, names, cities, people, wonders: load('wonders').wonders, resources: load('resources'),
                       infrastructure: load('infrastructure') });
const pool = g.pool; // land hexes with things of their own, in cell order
const own = (cell) => [w.raw.counties[w.raw.county[cell]].name, ...w.raw.states[w.raw.owner[cell]].name.split('/')];
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

    def test_pool_is_land_with_distinctive_things_of_two_kinds(self):
        got = run("""
            const { t } = await import('./web/js/i18n.js');
            const things = new Set(P.SOURCES.map((s) => t(`game.k.${s.id}`)));
            out({ n: pool.length, land: g.land.length, sorted: pool.every((c, k) => !k || pool[k - 1] < c),
                  land_ok: pool.every((c) => w.raw.owner[c] >= 0 && w.raw.county[c] >= 0),
                  kinds_ok: pool.every((c) => g.kinds(c).size >= P.MIN_KINDS),
                  named_ok: pool.every((c) => things.has(P.buildClues(g, c)[2].facts[0].label)),
                  villarrobledo: pool.includes(12111), // the playtest's day 1: nothing of its own until the last clue
                  kinds: Object.fromEntries([...new Set(pool.flatMap((c) => [...g.kinds(c)]))].map((k) => [k, pool.filter((c) => g.kinds(c).has(k)).length])) });
        """)
        self.assertTrue(got["sorted"] and got["land_ok"] and got["kinds_ok"] and got["named_ok"])
        self.assertFalse(got["villarrobledo"])
        self.assertGreater(got["n"], 2.5 * 365)  # over two and a half years without a repeat
        self.assertLess(got["n"], got["land"] / 3)  # most of Spain's hexes have too little of their own
        for kind in ("fiestas", "castles", "museums", "people", "wonders", "works", "food", "city"):
            self.assertGreater(got["kinds"].get(kind, 0), 0, kind)

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
        # A changed seed, pool rule or epoch changes every day's puzzle: this pins them (day 1 is Guadix).
        self.assertEqual(got["first"], [16283, 16452, 15748])

    def test_a_game_saved_for_another_hex_starts_afresh(self):
        got = run("""
            const saved = { today: { day: 1, cell: 16283, guesses: [9492], clues: 2 } };
            out([P.savedGame(saved, 1, 16283), P.savedGame(saved, 1, 14118), P.savedGame(saved, 2, 16283),
                 P.savedGame({ today: { day: 1, guesses: [9492], clues: 2 } }, 1, 16283), P.savedGame({}, 1, 16283), P.savedGame(null, 1, 1)]);
        """)
        self.assertEqual(got[0], {"day": 1, "cell": 16283, "guesses": [9492], "clues": 2})
        self.assertEqual(got[1:], [None, None, None, None, None])  # another hex, another day, a game saved before cells were


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
            const hg = { cx: (i) => [0, 10, 0, -10, 10][i], cy: (i) => [0, 0, -10, 0, 10][i] };
            out([P.arrow(hg, 0, 1), P.arrow(hg, 0, 2), P.arrow(hg, 0, 3), P.arrow(hg, 0, 4), P.arrow(hg, 4, 0), P.arrow(hg, 0, 0)]);
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
        got = run("""const m = P.placeMasker(['Villaviciosa', 'Alicante/Alacant', 'Vic', 'Sella', 'Castro-Urdiales', "L'Hospitalet de Llobregat"], ['Vic']);
            out([m('Festival de la Manzana, Villaviciosa'), m('Hogueras de Alacant'), m('Salchichón de Vic'), m('Sellado de Vicente'),
                 m('Plaza de toros de Castro Urdiales'), m("Fira de l'Hospitalet de Llobregat"), m('VILLAVICIOSA y alicante'),
                 m('Miel de Villaviciosa (DOP)')]);""")
        self.assertEqual(got, ["Festival de la Manzana, …", "Hogueras de …", "Salchichón de …", "Sellado de Vicente",
                               "Plaza de toros de …", "", "", ""])  # a name that is mostly place says nothing: left out

    def test_readable_turns_hidden_places_into_prose(self):
        got = run("""out([P.readable('El Cascamorras de … y …'), P.readable('Festival de la Manzana, …'), P.readable("Fira de l'…"),
                       P.readable('Cordero Segureño (IGP)'), P.readable('Plaza de toros de …'), P.readable('… de Pascua')]);""")
        self.assertEqual(got, ["El Cascamorras", "Festival de la Manzana", "Fira", "Cordero Segureño (IGP)", "Plaza de toros",
                               "Pascua"])

    def test_clues_come_from_the_data(self):
        for lang in ("es", "en"):
            got = run("""
                const { t } = await import('./web/js/i18n.js');
                const { int } = await import('./web/js/format.js');
                const cell = P.dailyCell(pool, 1); // Guadix
                const clues = P.buildClues(g, cell);
                const L = (id) => lenses.get(id);
                out({ ids: clues.map((c) => c.id), titles: clues.map((c) => c.title), facts: clues.map((c) => c.facts.map(({ label, value }) => ({ label, value }))),
                      density: formatLensValue(L('density'), L('density').values[cell]),
                      lang: formatLensValue(L('languages'), L('languages').values[cell]),
                      relief: w.tables.relief.find((r) => r.id === w.relief[cell]).name, elev: `${int(world.elev[cell])} m`,
                      initial: w.raw.states[w.raw.owner[cell]].name[0], person: people.find((p) => p.cell === cell),
                      fiesta: t('game.k.fiestas'), zone: t('game.zone.s'), seaLabel: t('game.f.sea'), sea: t('game.sea.100'),
                      position: t('game.f.position') });
            """, lang)
            self.assertEqual(got["ids"], ["where", "people", "thing", "near", "city", "last"])
            self.assertTrue(all(got["titles"]) and all(got["facts"]), lang)
            flat = [f["value"] for clue in got["facts"] for f in clue]
            first = {f["label"]: f["value"] for f in got["facts"][0]}
            self.assertEqual(first[got["seaLabel"]], got["sea"])
            for v in (got["zone"], got["density"], got["lang"], got["relief"], got["elev"], f"«{got['initial']}»"):
                self.assertIn(v, flat, lang)
            self.assertIn(got["person"]["name"], " ".join(f["value"] for f in got["facts"][5]))  # the most famous native, last
            # The Cascamorras by clue 4, its place names hidden; the hex placed from the city of Granada by clue 5,
            # unnamed first ("a city on the map"), then as the province's capital (naming Granada would name the province).
            self.assertIn("El Cascamorras (", [f["value"] for f in got["facts"][3] if f["label"] == got["fiesta"]][0])
            self.assertFalse(any("…" in v for v in flat), lang)  # hidden places read as prose, never as "…"
            near, named = ([f["value"] for f in got["facts"][k] if f["label"] == got["position"]][0] for k in (3, 4))
            self.assertRegex(near, r"50 km")
            self.assertNotIn("Granada", near + named)

    def test_many_centenarians_is_a_number_in_clue_2_where_the_hex_stands_out(self):
        for lang in ("es", "en"):
            got = run("""
                const { t } = await import('./web/js/i18n.js');
                const L = lenses.get('centenarians'), label = t('game.f.centenarians');
                const fact = (c) => P.buildClues(g, c)[1].facts.find((f) => f.label === label) || null;
                const over = pool.find((c) => L.values[c] >= P.STANDOUT * L.national);
                const guadix = P.dailyCell(pool, 1);
                const f = fact(over);
                out({ national: L.national, over, value: f && f.value, num: f && f.num, rate: L.values[over],
                      guadix: fact(guadix), guadixRate: L.values[guadix],
                      everyOver: pool.every((c) => !!fact(c) === (L.values[c] >= P.STANDOUT * L.national)) });
            """, lang)
            self.assertAlmostEqual(got["national"], 3.66, places=2)  # 18,164 centenarians in the census of 2026
            self.assertIsNotNone(got["over"], lang)
            self.assertTrue(got["num"], lang)  # a number: it does not narrow the map
            times = got["rate"] / got["national"]
            rate, ratio = (f"{got['rate']:.1f}", f"{times:.1f}") if lang == "en" else (
                f"{got['rate']:.1f}".replace(".", ","), f"{times:.1f}".replace(".", ","))
            self.assertEqual(got["value"], f"{rate} por 10.000 ({ratio} veces España)" if lang == "es"
                             else f"{rate} per 10,000 ({ratio} times Spain's)")
            self.assertIsNone(got["guadix"], lang)  # day 1's clue 2 stays as it was: Guadix's 3.67 is under the cut
            self.assertLess(got["guadixRate"], 1.5 * got["national"])
            self.assertTrue(got["everyOver"], lang)

    def test_every_fact_fits_its_own_answer(self):
        """The measure below counts the hexes a clue fits; the answer must always be one of them."""
        got = run("""
            out(pool.flatMap((c) => P.buildClues(g, c).flatMap((cl) => cl.facts.filter((f) => !f.same(c)).map((f) => [c, f.label, f.value]))));
        """)
        self.assertEqual(got, [])

    def test_no_clue_names_the_answer(self):
        """Over the whole pool no clue holds the answer's municipality or province name (a hyphen or a space alike)."""
        got = run(r"""
            const leaks = [];
            for (const cell of pool) {
              const text = P.buildClues(g, cell).flatMap((c) => c.facts.map((f) => `${f.label}: ${f.value}`)).join(' | ');
              for (const n of own(cell)) {
                const re = new RegExp(`(?<![\\p{L}])${n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/[\s-]+/g, '[\\s-]+')}(?![\\p{L}])`, 'iu');
                if (re.test(text)) leaks.push([cell, n, text]);
              }
            }
            out(leaks);
        """)
        self.assertEqual(got, [])


@unittest.skipUnless(NODE, "node is not installed")
class GuessabilityTest(unittest.TestCase):
    """How many land hexes of Spain still fit the clues after each one, over the first year of puzzles (P.candidates):
    a category or a name must match, a count must be there; numbers do not narrow (a reader cannot search the map for
    "42.8 years"). The playtest's day 1 under the old clues fitted 1,143 hexes until clue 4 and 11 after the last."""

    def test_each_clue_narrows_and_a_named_thing_settles_it_by_clue_3(self):
        got = run("""
            const rows = Array.from({ length: 365 }, (_, k) => P.candidates(g, P.dailyCell(pool, k + 1)));
            const median = (k) => { const a = rows.map((r) => r[k]).sort((x, y) => x - y); return a[a.length >> 1]; };
            out({ land: g.land.length, pool: pool.length, medians: [0, 1, 2, 3, 4, 5].map(median),
                  first: Math.min(...rows.map((r) => r[0])), fifth: Math.max(...rows.map((r) => r[4])),
                  narrowing: rows.every((r) => r.every((n, k) => !k || n <= r[k - 1])),
                  allFirst: Math.min(...pool.map((c) => P.candidates(g, c)[0])) });
        """)
        m = got["medians"]
        self.assertGreaterEqual(m[0], 50)  # the first clue is a region, not an answer
        self.assertGreaterEqual(got["allFirst"], 20)  # on any day of the pool (P.MIN_FIRST)
        self.assertGreater(m[0], m[1])
        self.assertGreater(m[1], m[2])
        self.assertLessEqual(m[2], min(5, 0.05 * got["pool"]))  # a named thing pins the hex by clue 3 on most days
        self.assertLessEqual(got["fifth"], 3)  # and on every day the last clue only confirms it
        self.assertTrue(got["narrowing"])


@unittest.skipUnless(NODE, "node is not installed")
class AlbumTest(unittest.TestCase):
    """The province album (web/js/ext/game/album.js) on Spain's data: provinces by community from states.json, how
    often each comes up from the pool, and the album's share text."""

    SETUP = """
        const A = await import('./web/js/ext/game/album.js');
        const states = load('states');
        const fipsSet = new Set(states.map((s) => s.fips));
        const view = (album, stats) => A.albumView({ album, states, raw: w.raw, pool, firstFits: g.firstFits, stats });
        const byName = (v, name) => v.communities.find((c) => c.name === name);
        const fipsOf = (name) => states.find((s) => s.name === name).fips;
    """

    def album(self, body, lang="es"):
        return run(self.SETUP + body, lang)

    def test_normalize_drops_what_is_not_a_list_of_days(self):
        got = self.album("""out([null, 'x', 7, { '18': '1' }, { '99': [1] }, { '18': [3, 1, 3, -2, 1.5, 0] }, { '18': [] }, [1]]
            .map((a) => A.normalize(a, fipsSet)));""")
        self.assertEqual(got, [{}, {}, {}, {}, {}, {"18": [1, 3]}, {}, {}])

    def test_add_win_is_idempotent_and_does_not_mutate(self):
        got = self.album("""
            const a = { '18': [3] }, b = A.addWin(a, '18', 1), c = A.addWin(b, '18', 1), d = A.addWin(undefined, '15', 2);
            out([a, b, c, b === c, d]);
        """)
        self.assertEqual(got[0], {"18": [3]})
        self.assertEqual(got[1], {"18": [1, 3]})
        self.assertEqual(got[2], {"18": [1, 3]})
        self.assertFalse(got[3])  # always a new object
        self.assertEqual(got[4], {"15": [2]})

    def test_empty_album_counts_the_provinces_that_can_come_up(self):
        got = self.album("""
            const v = view({}, null), provs = A.provincesOf(v);
            out({ communities: v.communities.length, total: v.total, got: v.got, complete: v.complete, cTotal: v.communitiesTotal,
                  outside: v.outside.map((o) => [o.name, o.reason, o.fits < P.MIN_FIRST]),
                  hexSum: provs.reduce((n, p) => n + p.hexes, 0), pool: pool.length, poolSize: v.poolSize,
                  allPositive: provs.every((p) => p.hexes > 0),
                  galicia: byName(v, 'Galicia').total, codes: v.communities.map((c) => c.code),
                  slow: provs.filter((p) => p.slow).map((p) => p.fips).sort(),
                  slowExpected: provs.filter((p) => Math.round(pool.length / p.hexes) > A.LONG_WAIT_DAYS).map((p) => p.fips).sort(),
                  every: provs.every((p) => p.everyDays === Math.round(pool.length / p.hexes)),
                  unassigned: [view({}, { won: 3 }).unassigned, view({ '18': [1, 2] }, { won: 1 }).unassigned, view({}, undefined).unassigned] });
        """)
        # Ceuta and Melilla are the only land hexes in their first-clue area, under MIN_FIRST (E89).
        self.assertEqual(got["outside"], [["Ceuta", "first", True], ["Melilla", "first", True]])
        self.assertEqual((got["communities"], got["cTotal"], got["total"]), (17, 17, 50))
        self.assertEqual((got["got"], got["complete"]), (0, 0))
        self.assertEqual(got["hexSum"], got["pool"])
        self.assertEqual(got["poolSize"], got["pool"])
        self.assertTrue(got["allPositive"] and got["every"])
        self.assertEqual(got["galicia"], 4)
        self.assertEqual(got["codes"], sorted(got["codes"]))  # INE order
        self.assertEqual(got["slow"], got["slowExpected"])
        self.assertEqual(got["unassigned"], [3, 0, 0])

    def test_a_full_community_is_complete(self):
        got = self.album("""
            const galicia = states.filter((s) => s.community.name === 'Galicia').map((s) => s.fips);
            const album = Object.fromEntries(galicia.map((f, k) => [f, [k + 1]]));
            album[fipsOf('Granada')] = [9, 12];
            const v = view(A.normalize(album, fipsSet), { won: 9 });
            const pick = (c) => ({ got: c.got, total: c.total, complete: c.complete });
            const gr = byName(v, 'Andalucía').provinces.find((p) => p.name === 'Granada');
            out({ galicia: pick(byName(v, 'Galicia')), andalucia: pick(byName(v, 'Andalucía')), got: v.got, complete: v.complete,
                  granada: gr.days, unassigned: v.unassigned });
        """)
        self.assertEqual(got["galicia"], {"got": 4, "total": 4, "complete": True})
        self.assertEqual(got["andalucia"], {"got": 1, "total": 8, "complete": False})
        self.assertEqual((got["got"], got["complete"]), (5, 1))
        self.assertEqual(got["granada"], [9, 12])
        self.assertEqual(got["unassigned"], 3)  # 9 won, 6 days recorded

    SHARE = """
        const galicia = states.filter((s) => s.community.name === 'Galicia').map((s) => s.fips);
        const some = Object.fromEntries([...galicia, fipsOf('Granada'), fipsOf('La Rioja')].map((f) => [f, [1]]));
        const allBut = (names) => Object.fromEntries(A.provincesOf(view({}, null)).filter((p) => !names.includes(p.name)).map((p) => [p.fips, [2]]));
        const texts = [some, {}, allBut(['Soria', 'Teruel']), allBut(['Soria', 'Teruel', 'Lugo', 'Jaén', 'Cádiz', 'Huesca'])]
          .map((a) => A.shareText(view(a, null), 'https://x/#juego'));
        const v = view(some, null);
        out({ texts, communities: v.communities.map((c) => c.name), provinces: A.provincesOf(v).map((p) => p.name) });
    """

    def test_share_text(self):
        for lang in ("es", "en"):
            got = self.album(self.SHARE, lang)
            some, empty, two, six = (t.split("\n") for t in got["texts"])
            with self.subTest(lang):
                self.assertIn("6", some[0])
                self.assertIn("50", some[0])
                self.assertEqual(len(some[1]), 17)  # one square per community (each one code point)
                self.assertEqual(some[1].count("🟩"), 2)  # Galicia and La Rioja
                self.assertEqual(some[1].count("🟨"), 1)  # Andalucía
                self.assertIn("Galicia, La Rioja", some[2])
                self.assertIn("2", some[2])
                self.assertEqual(some[-1], "https://x/#juego")
                self.assertEqual(len(some), 4)  # 44 missing: none named
                self.assertEqual(set(empty[1]), {"⬜"})
                self.assertIn("0", empty[2])
                self.assertEqual(len(two), 5)
                self.assertIn("Teruel, Soria", two[3])  # community by community: Aragón before Castilla y León
                self.assertEqual(len(six), 4)  # six missing: none named
                # No province is named unless its community is complete or it is missing.
                named = {p for p in got["provinces"] if p in got["texts"][0]} - set(got["communities"])
                self.assertEqual(named, set())
                self.assertNotIn("Granada", got["texts"][0])
        es = self.album(self.SHARE)["texts"]
        self.assertEqual(es[0].split("\n")[0], "Álbum de «Adivina el hexágono»: 6 de 50 provincias")
        self.assertEqual(es[1].split("\n")[2], "Ninguna comunidad completa (0 de 17)")
        self.assertTrue(es[2].split("\n")[3].startswith("Me faltan: "))

    def test_share_text_in_english_has_no_spanish_ui_words(self):
        got = self.album(self.SHARE, "en")
        text = "\n".join(got["texts"])
        for name in got["communities"] + got["provinces"]:
            text = text.replace(name, "")
        for word in ("Álbum", "provincias", "comunidad", "Completas", "Ninguna", "Me faltan", "Adivina"):
            self.assertNotIn(word, text)

    def test_album_news_says_new_or_already_there_by_the_days_before(self):
        got = self.album("""
            const gr = fipsOf('Granada'), v = view({ [gr]: [9, 12] }, null);
            out([A.albumNews(v, gr, 9), A.albumNews(v, gr, 12), A.albumNews(view({}, null), gr, 3), A.albumNews(v, '51', 1),
                 A.albumNews(v, undefined, 1)]);
        """)
        self.assertEqual(got[0], {"fresh": True, "province": "Granada", "community": "Andalucía", "got": 1, "total": 8})
        self.assertFalse(got[1]["fresh"])  # won on day 9 already
        self.assertTrue(got[2]["fresh"])
        self.assertEqual(got[2]["got"], 0)
        self.assertEqual(got[3:], [None, None])  # Ceuta is out of the game; no province

    def test_completion_day_follows_the_daily_order(self):
        got = self.album("""
            const provs = A.provincesOf(view({}, null)), comes = (d) => w.raw.owner[P.dailyCell(pool, d)];
            const seen = (from, to) => new Set(Array.from({ length: to - from + 1 }, (_, k) => comes(from + k)));
            const d1 = A.completionDay(view({}, null), pool, w.raw, 1), d40 = A.completionDay(view({}, null), pool, w.raw, 40);
            const soria = provs.find((p) => p.name === 'Soria');
            const allButSoria = Object.fromEntries(provs.filter((p) => p !== soria).map((p) => [p.fips, [1]]));
            const lone = A.completionDay(view(allButSoria, null), pool, w.raw, 7);
            let first = 7;
            while (comes(first) !== soria.idx) first++;
            out({ d1, all: provs.every((p) => seen(1, d1).has(p.idx)), tight: provs.some((p) => !seen(1, d1 - 1).has(p.idx)),
                  d40all: provs.every((p) => seen(40, d40).has(p.idx)), tight40: provs.some((p) => !seen(40, d40 - 1).has(p.idx)),
                  lone, first, full: A.completionDay(view(Object.fromEntries(provs.map((p) => [p.fips, [1]])), null), pool, w.raw, 3),
                  n: pool.length });
        """)
        self.assertTrue(1 <= got["d1"] <= got["n"])
        self.assertTrue(got["all"] and got["tight"] and got["d40all"] and got["tight40"])
        self.assertEqual(got["lone"], got["first"])
        self.assertIsNone(got["full"])

    NOTES = SETUP + """
        const AP = await import('./web/js/ext/game/albumPanel.js');
        const soria = fipsOf('Soria'), noSoria = pool.filter((c) => states[w.raw.owner[c]].fips !== soria);
        const v0 = view({}, { won: 1 }), done = A.completionDay(v0, pool, w.raw, 4);
        const vr = A.albumView({ album: {}, states, raw: w.raw, pool: noSoria, firstFits: g.firstFits, stats: { won: 3 } });
        const line = (name, album) => { const v = view(album, null); return AP.provinceLine(A.provincesOf(v).find((p) => p.name === name), v); };
        out({ empty: AP.notes(v0, { g, storageOk: false, from: 4 }), done,
              rules: AP.notes(vr, { g: { ...g, pool: noSoria }, storageOk: true, from: 1 }),
              some: AP.notes(view({ [fipsOf('Granada')]: [2] }, { won: 1 }), { g, storageOk: true, from: 3 }),
              segovia: line('Segovia', {}), barcelona: line('Barcelona', { [fipsOf('Barcelona')]: [1, 9] }),
              granada: line('Granada', { [fipsOf('Granada')]: [2] }), outside: vr.outside.map((o) => [o.name, o.reason]) });
    """

    def test_notes_and_province_lines_in_spanish(self):
        got = run(self.NOTES)
        e = got["empty"]
        self.assertEqual(e[0], "Este navegador no deja guardar el álbum.")
        self.assertEqual(e[1], "Gana una partida para colorear tu primera provincia.")
        self.assertEqual(e[2], f"Si ganas las próximas {got['done'] - 3} partidas, completas el álbum el día {got['done']} del juego.")
        self.assertTrue(e[3].startswith("Cada día sale un hexágono distinto y ninguno se repite en 1054 días."), e[3])
        self.assertIn("de 50 (Barcelona) a 6 (Segovia)", e[3])
        self.assertEqual(e[4], "Ceuta y Melilla no salen en el juego: la primera pista («Norte de África», en la costa) solo "
                               "dejaría 2 hexágonos posibles, y tiene que dejar al menos 20 para no regalar la respuesta.")
        self.assertEqual(e[5], "1 partida ganada antes del álbum no tiene provincia.")
        self.assertEqual(len(e), 6)
        # A province taken out for another reason gets its own line; the counts are plural.
        self.assertEqual(got["outside"], [["Soria", "rules"], ["Ceuta", "first"], ["Melilla", "first"]])  # INE order
        self.assertIn("Soria no sale en el juego: ningún hexágono suyo cumple las reglas del juego.", got["rules"])
        self.assertIn("3 partidas ganadas antes del álbum no tienen provincia.", got["rules"])
        self.assertNotIn("Gana una partida para colorear tu primera provincia.", got["some"])
        self.assertEqual(got["segovia"], "Segovia · 6 de los 1054 hexágonos del juego · sale una vez cada 176 días de media · aún no la tienes")
        self.assertTrue(got["barcelona"].endswith("ganada 2 veces"))
        self.assertTrue(got["granada"].endswith("ganada una vez"))

    def test_notes_and_province_lines_in_english(self):
        got = run(self.NOTES, "en")
        e = got["empty"]
        self.assertEqual(e[0], "This browser does not let the album be saved.")
        self.assertEqual(e[4], "Ceuta and Melilla never come up in the game: the first clue (“North Africa”, on the coast) would "
                               "leave only 2 possible hexes, and it must leave at least 20 so it doesn't give the answer away.")
        self.assertEqual(e[5], "1 game won before the album has no province.")
        self.assertIn("Soria never comes up in the game: none of its hexes meets the game's rules.", got["rules"])
        self.assertIn("3 games won before the album have no province.", got["rules"])
        self.assertTrue(got["segovia"].startswith("Segovia · 6 of the game's 1,054 hexes · comes up once every 176 days"),
                        got["segovia"])
        self.assertTrue(got["barcelona"].endswith("won 2 times"), got["barcelona"])
        self.assertTrue(got["granada"].endswith("won once"), got["granada"])

    def test_collected_chips_keep_their_text_readable(self):
        got = run("""
            const { STATE_PALETTE, contrast, parseHex } = await import('./web/js/color.js');
            const { chipInk } = await import('./web/js/ext/game/albumPanel.js');
            const ratio = (c) => contrast(c, parseHex(chipInk(c)));
            out([Math.min(...STATE_PALETTE.map(ratio)), Math.min(...w.stateColor.filter(Boolean).map(ratio))]);
        """)
        self.assertGreaterEqual(min(got), 4.2)


@unittest.skipUnless(NODE, "node is not installed")
class GameDockTest(unittest.TestCase):
    """The game as the page runs it (web/js/ext/game/index.js) against a stand-in app and localStorage: map clicks as
    guesses, the album tab, what is saved, and the album written over what another tab saved."""

    SETUP = """
        setCountry({ country: { ...world.country, lang: LANG, locale: 'es-ES', game: true,
                                data: ['personajes', 'wonders', 'resources', 'infrastructure'] } }, null);
        const mem = new Map(), KEY = 'spainciv.game';
        Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
          getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) } });
        globalThis.Path2D = class { moveTo() {} lineTo() {} };
        // An element that takes any call or property: the album panel's canvas and buttons.
        const stub = () => new Proxy(function () {}, {
          get: (o, k) => (k in o ? o[k] : k === Symbol.toPrimitive ? () => '' : k === 'then' ? undefined : (o[k] = stub())),
          apply: () => stub() });
        const states = load('states');
        const saved = () => JSON.parse(mem.get(KEY) || '{}');
        const tick = () => new Promise((r) => setTimeout(r, 0));
        const { install } = await import('./web/js/ext/game/index.js');
        function harness() {
          const modes = {}, on = {}, els = new Map();
          const dock = { innerHTML: '', classList: stub(), querySelectorAll: () => [],
                         querySelector: (s) => (els.has(s) ? els : els.set(s, stub())).get(s) };
          const app = { w, mode: null, data: { world, cities, states }, lensById: lenses, state: {},
            cam: { scale: 1, moving: false, toScreen: () => [0, 0] },
            ui: { addTopButton: () => null, dock: () => dock, undock() {}, toast() {} },
            on: (e, f) => (on[e] ||= []).push(f), hash: { register() {} }, registerMode: (n, m) => (modes[n] = m),
            registerOverlay: () => () => {}, clearSelection() {}, requestDraw() {}, setHighlight() {}, flyTo() {},
            loadData: async (n) => load(n),
            setMode(n) { if (app.mode) modes[app.mode].exit(); app.mode = n; if (n) modes[n].enter(); } };
          install(app);
          return {
            dock, async open() { app.setMode('game'); while (!dock.innerHTML.includes('gm-head')) await tick(); },
            close: () => app.setMode(null), click: (cell) => on.mapclick[0]({ cell }),
            key: (key) => dock.querySelector('.gm-tabs').onkeydown({ key, preventDefault() {} }),
            selected: () => /aria-labelledby="gm-tab-(\w+)"/.exec(dock.innerHTML)?.[1] };
        }
        const day = P.dayNumber(), cell = P.dailyCell(pool, day), fips = states[w.raw.owner[cell]].fips;
        const far = g.land.find((c) => Math.abs(w.grid.cx(c) - w.grid.cx(cell)) > 300);
        const other = states.find((s) => s.community && s.fips !== fips).fips;
    """

    def test_album_tab_ignores_map_clicks_and_every_opening_starts_on_today(self):
        got = run(self.SETUP + """
            const h = harness();
            await h.open();
            const first = h.selected();
            h.key('ArrowRight');
            const album = h.selected(), tabindex = /id="gm-tab-album"[^>]*tabindex="0"/.test(h.dock.innerHTML);
            const inAlbum = h.click(far), guessesInAlbum = saved().today?.guesses?.length ?? 0;
            h.close();
            await h.open();
            const reopened = h.selected(), taken = h.click(far);
            h.key('End');
            const end = h.selected();
            h.key('ArrowRight');
            const wrapped = h.selected();
            h.close();
            out({ first, album, tabindex, inAlbum, guessesInAlbum, reopened, taken, guesses: saved().today.guesses, far, end, wrapped });
        """)
        self.assertEqual((got["first"], got["album"]), ("today", "album"))
        self.assertTrue(got["tabindex"])
        self.assertFalse(got["inAlbum"])
        self.assertEqual(got["guessesInAlbum"], 0)
        self.assertEqual(got["reopened"], "today")  # closing on the album does not reopen there
        self.assertTrue(got["taken"])
        self.assertEqual(got["guesses"], [got["far"]])
        self.assertEqual((got["end"], got["wrapped"]), ("album", "today"))

    def test_a_win_goes_in_the_album_over_what_another_tab_saved(self):
        got = run(self.SETUP + """
            const h = harness();
            await h.open();
            h.click(far);
            // Another tab writes its album and stats meanwhile (a win in another province on some day).
            mem.set(KEY, JSON.stringify({ ...saved(), album: { [other]: [3] }, stats: { played: 4, won: 4 } }));
            h.click(cell);
            const s = saved();
            const html = h.dock.innerHTML;
            h.close();
            out({ album: s.album, stats: s.stats, guesses: s.today.guesses.length, fresh: html.includes('Nueva en tu álbum'),
                  want: { [fips]: [day], [other]: [3] } });
        """)
        self.assertEqual(got["album"], got["want"])  # the day's province, not the winning click's, and the other tab's
        self.assertEqual(got["stats"]["played"], 5)
        self.assertEqual(got["stats"]["won"], 5)
        self.assertEqual(got["guesses"], 2)
        self.assertTrue(got["fresh"])

    def test_a_game_won_before_the_album_is_put_in_it_on_opening(self):
        got = run(self.SETUP + """
            mem.set(KEY, JSON.stringify({ today: { day, cell, guesses: [cell], clues: 1 }, stats: { played: 1, won: 1 } }));
            const h = harness();
            await h.open();
            const s = saved();
            h.close();
            out({ album: s.album, fips, day });
        """)
        self.assertEqual(got["album"], {got["fips"]: [got["day"]]})


if __name__ == "__main__":
    unittest.main()
