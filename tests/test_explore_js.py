"""The fog of war «España por descubrir» (web/js/ext/explore/model.js): the hexes a reveal explores, the shares shown,
the progress by group of regions and how the explored set is kept, on a made-up grid and on Spain's world
(sites/es/data). Run with node; skipped without it."""

import json
import shutil
import subprocess
import unittest

from pipeline import countries, site
from pipeline.core.paths import ROOT

NODE = shutil.which("node")

PRELUDE = """
import { readFileSync } from 'node:fs';
import { makeGrid } from './web/js/hex.js';
const M = await import('./web/js/ext/explore/model.js');
const out = (x) => console.log(JSON.stringify(x));
// A 6 × 5 grid: regions 0 (columns 0-2) and 1 (columns 3-4) on land, column 5 is sea.
const grid = makeGrid({ radius: 1, cols: 6, rows: 5 });
const owner = Array.from({ length: grid.size }, (_, i) => (i % 6 === 5 ? -1 : i % 6 < 3 ? 0 : 1));
// localStorage stand-ins: a working one, one that throws (blocked storage) and one that is full.
const memory = () => { const m = new Map(); return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, String(v)), m }; };
const blocked = { getItem() { throw new Error('SecurityError'); }, setItem() { throw new Error('SecurityError'); } };
const full = { getItem: () => null, setItem() { throw new Error('QuotaExceededError'); } };
"""


def run(body: str):
    res = subprocess.run([NODE, "--input-type=module", "-e", PRELUDE + body], cwd=ROOT, capture_output=True, text=True)
    if res.returncode:
        raise AssertionError(res.stderr)
    return json.loads(res.stdout)


@unittest.skipUnless(NODE, "node is not installed")
class RevealTest(unittest.TestCase):
    def test_around_is_the_hex_and_its_neighbours_inside_the_grid(self):
        got = run("out([M.around(grid, 14).sort((a, b) => a - b), M.around(grid, 0).sort((a, b) => a - b), M.around(grid, 14, 0), "
                  "M.around(grid, 14, 2).length, M.around(grid, -1), M.around(grid, 30)]);")
        # Row 2 is even: 14's neighbours are 13, 15, 8, 9 (row 1) and 20, 21 (row 3) in the odd-r layout.
        self.assertEqual(got[0], [7, 8, 13, 14, 15, 19, 20])
        self.assertEqual(got[1], [0, 1, 6])
        self.assertEqual(got[2:], [[14], 19, [], []])

    def test_reveal_counts_land_once_and_skips_the_sea(self):
        got = run("""
            const m = M.createExplored(grid, owner);
            const first = m.reveal(16).sort((a, b) => a - b);   // 16 is land next to the sea column (17, 11, 23)
            const again = m.reveal(16);
            const overlap = m.reveal(15).sort((a, b) => a - b);
            out({ total: m.total, first, again, overlap, count: m.count, owners: m.owners(), sea: m.isExplored(17),
                  land: m.isExplored(16), out: m.isExplored(-1) });
        """)
        self.assertEqual(got["total"], 25)
        self.assertEqual(got["first"], [9, 10, 15, 16, 21, 22])
        self.assertEqual(got["again"], [])
        self.assertEqual(got["overlap"], [8, 14, 20])
        self.assertEqual(got["count"], 9)
        self.assertEqual(got["owners"], [{"explored": 3, "total": 15}, {"explored": 6, "total": 10}])
        self.assertEqual([got["sea"], got["land"], got["out"]], [False, True, False])

    def test_reset_clears_everything(self):
        got = run("const m = M.createExplored(grid, owner); m.reveal(8); m.reset(); "
                  "out([m.count, m.owners(), m.isExplored(8), m.reveal(8).length]);")
        self.assertEqual(got, [0, [{"explored": 0, "total": 15}, {"explored": 0, "total": 10}], False, 7])


@unittest.skipUnless(NODE, "node is not installed")
class ShareTest(unittest.TestCase):
    def test_shown_share_rounds_down_with_one_decimal_below_ten_percent(self):
        got = run("out([[0, 100], [1, 5843], [5, 1000], [99, 1000], [100, 1000], [129, 1000], [999, 1000], [1000, 1000], "
                  "[3, 0], [5, 4]].map(([e, t]) => M.shownShare(e, t)));")
        self.assertEqual(got, [
            {"x": 0, "d": 0},
            {"x": 0.001, "d": 1},  # a first reveal never shows 0 %
            {"x": 0.005, "d": 1},
            {"x": 0.099, "d": 1},
            {"x": 0.1, "d": 0},
            {"x": 0.12, "d": 0},
            {"x": 0.99, "d": 0},  # 100 % only when everything is explored
            {"x": 1, "d": 0},
            {"x": 0, "d": 0},
            {"x": 1, "d": 0},
        ])

    def test_group_progress_sums_its_regions_and_drops_empty_groups(self):
        got = run("""
            const m = M.createExplored(grid, owner);
            m.reveal(16);
            out(M.groupProgress(m, [{ name: 'Oeste', regions: ['A'] }, { name: 'Todo', regions: ['A', 'B', 'Z'] },
                                    { name: 'Nada', regions: ['Z'] }, { name: 'Este', regions: ['B'] }], ['A', 'B']));
        """)
        # 16 and its neighbours lie in columns 3-4, region B.
        self.assertEqual(got, [{"name": "Oeste", "explored": 0, "total": 15}, {"name": "Todo", "explored": 6, "total": 25},
                               {"name": "Este", "explored": 6, "total": 10}])


@unittest.skipUnless(NODE, "node is not installed")
class PersistenceTest(unittest.TestCase):
    def test_a_saved_set_loads_back_the_same(self):
        got = run("""
            const s = memory();
            const a = M.createExplored(grid, owner);
            a.reveal(0); a.reveal(24);
            const saved = M.save(a, s, 'k');
            const b = M.createExplored(grid, owner);
            const loaded = M.load(b, s, 'k');
            out({ saved, loaded, same: a.land.every((i) => a.isExplored(i) === b.isExplored(i)), count: [a.count, b.count],
                  owners: JSON.stringify(a.owners()) === JSON.stringify(b.owners()), keys: [...s.m.keys()] });
        """)
        self.assertTrue(got["saved"] and got["loaded"] and got["same"] and got["owners"])
        self.assertEqual(got["count"][0], got["count"][1])
        self.assertEqual(got["keys"], ["k"])

    def test_blocked_full_or_missing_storage_never_throws(self):
        got = run("""
            const m = M.createExplored(grid, owner);
            m.reveal(8);
            out([M.save(m, blocked, 'k'), M.load(m, blocked, 'k'), M.save(m, full, 'k'), M.save(m, null, 'k'),
                 M.load(m, null, 'k'), M.load(m, memory(), 'k'), m.count]);
        """)
        self.assertEqual(got, [False, False, False, False, False, False, 7])

    def test_a_set_from_another_map_or_garbage_is_ignored(self):
        got = run("""
            const s = memory();
            const other = M.createExplored(makeGrid({ radius: 1, cols: 6, rows: 6 }), [...owner, 0, 0, 0, 0, 0, -1]);
            other.reveal(0);
            M.save(other, s, 'k');
            const m = M.createExplored(grid, owner);
            m.reveal(8);
            const results = [M.load(m, s, 'k')];
            for (const text of ['{', 'null', '{"v":1}', JSON.stringify({ v: 2, key: m.key, bits: '' }),
                                JSON.stringify({ v: 1, key: m.key, bits: '%%%' }), JSON.stringify({ v: 1, key: m.key, bits: 'AAAAAAAA' })]) {
                s.setItem('k', text);
                results.push(M.load(m, s, 'k'));
            }
            out({ results, count: m.count });
        """)
        self.assertEqual(got["results"], [False] * 7)
        self.assertEqual(got["count"], 7)  # left as it was

    def test_spain_fits_in_a_small_entry(self):
        got = run("""
            const world = JSON.parse(readFileSync('sites/es/data/world.json', 'utf8'));
            const g = makeGrid(world.grid);
            const m = M.createExplored(g, world.owner);
            for (const i of m.land) if (i % 3 === 0) m.reveal(i, 0);
            const s = memory();
            M.save(m, s, 'k');
            const back = M.createExplored(g, world.owner);
            out({ total: m.total, count: m.count, loaded: M.load(back, s, 'k'), backCount: back.count, bytes: s.getItem('k').length,
                  regions: m.owners().length, states: world.states.length });
        """)
        self.assertEqual(got["total"], 5843)
        self.assertTrue(got["loaded"])
        self.assertEqual(got["backCount"], got["count"])
        self.assertLess(got["bytes"], 1100)
        self.assertEqual(got["regions"], got["states"])


class PageSettingsTest(unittest.TestCase):
    def test_spain_counts_by_autonomous_community_in_both_languages(self):
        es = countries.COUNTRIES["es"]
        cfg = site.page_config(es)
        groups, english = cfg["explore"]["groups"], cfg["texts"]["en"]["explore"]["groups"]
        self.assertEqual(len(groups), 19)
        regions = [r for g in groups for r in g["regions"]]
        self.assertEqual(len(regions), len(set(regions)))  # every province in one community
        world = json.loads((es.web_data_dir / "world.json").read_text(encoding="utf-8"))
        self.assertEqual(set(regions), {s["fips"] for s in world["states"]})
        self.assertEqual([g["regions"] for g in groups], [g["regions"] for g in english])
        self.assertEqual((groups[0]["name"], english[0]["name"]), ("Andalucía", "Andalusia"))
        self.assertIn({"name": "Galicia", "regions": ["15", "27", "32", "36"]}, groups)

    def test_the_fog_is_the_page_choice(self):
        page = countries.Page(title="t", card_title="t", description="d", image_alt="a", data_credit="c")
        with countries.using("es", page=page) as c:
            self.assertNotIn("explore", site.page_config(c))


if __name__ == "__main__":
    unittest.main()
