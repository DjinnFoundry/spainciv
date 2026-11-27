"""The fog of war «España por descubrir» (web/js/ext/explore): the hexes a reveal explores, the shares shown, the
progress by group of regions and how the explored set is kept (model.js), on a made-up grid and on Spain's world
(sites/es/data); the extension itself (index.js) on a stub app and a stub DOM; and the order main.js draws and
dispatches in. Run with node; skipped without it."""

import json
import re
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


@unittest.skipUnless(NODE, "node is not installed")
class RadiusAndSyncTest(unittest.TestCase):
    def test_a_reveal_clears_about_the_same_screen_size_at_any_zoom(self):
        got = run("out([[4.5, 28], [4.5, 40], [1.5, 40], [0.2, 40], [34, 40], [0, 40], [NaN, 40]].map(([r, px]) => M.revealRadius(r, px)));")
        # Spain at the default desktop zoom (Rpx 4.5): 4 rings hovering, 5 clicking; a phone (1.5): 15 → capped at 8.
        self.assertEqual(got, [4, 5, 8, 8, 1, 1, 1])

    def test_two_tabs_add_up_and_a_newer_start_wins(self):
        got = run("""
            const a = M.createExplored(grid, owner), b = M.createExplored(grid, owner);
            a.reveal(0); b.reveal(24);
            const added = a.merge(b.encode()), again = a.merge(b.encode()), both = a.count;
            b.reset(1000); b.reveal(12);                       // b starts again: its newer start replaces a's set
            const replaced = a.merge(b.encode()), afterReset = [a.count, a.isExplored(0), a.isExplored(12), a.epoch];
            const older = M.createExplored(grid, owner); older.reveal(0);
            const stale = a.merge(older.encode());              // a set from before the start is ignored
            const s = memory(); M.save(b, s, 'k');
            const c = M.createExplored(grid, owner);
            out({ added, again, both, replaced, afterReset, stale, pulled: M.pull(c, s, 'k'), c: c.count,
                  blocked: M.pull(c, blocked, 'k'), none: M.pull(c, memory(), 'k'), garbage: c.merge('{') });
        """)
        self.assertEqual([got["added"], got["again"], got["both"]], [True, False, 6])
        self.assertEqual([got["replaced"], got["afterReset"], got["stale"]], [True, [4, False, True, 1000], False])
        self.assertEqual([got["pulled"], got["c"], got["blocked"], got["none"], got["garbage"]], [True, 4, False, False, False])

    def test_share_squares_per_group_or_tenths(self):
        got = run("""
            const m = M.createExplored(grid, owner);
            const g = (explored, total) => ({ explored, total });
            out([M.progressSquares(m, [g(10, 10), g(3, 15), g(0, 4)]), M.progressSquares(m, []),
                 (m.reveal(8), m.reveal(16), M.progressSquares(m, null))]);
        """)
        self.assertEqual(got, ["🟩🟨⬜", "⬜" * 10, "🟩" * 4 + "⬜" * 6])  # 11 of 25 land hexes


# The extension on a stub app: a 6 × 5 grid (as above) whose regions A and B are the groups West and East, a camera
# whose reveal radius is 1, a DOM of stand-ins and a localStorage in memory. HOVER_MS is 650: `wait` sleeps past it.
APP = """
import { setCountry } from './web/js/app/country.js';
const LANG = __LANG__;
setCountry({ country: { id: 'es', name: LANG === 'es' ? 'España' : 'Spain', product: 'spainciv',
  site_url: 'spainciv.djinnfoundry.com', lang: LANG, data_lang: 'es', locale: LANG === 'es' ? 'es-ES' : 'en-IE',
  explore: { groups: [{ name: 'Oeste', regions: ['A'] }, { name: 'Este', regions: ['B'] }] } } }, null);
const ctx2d = new Proxy({}, { get: (o, k) => (k in o ? o[k] : k === 'createPattern' ? () => null : () => {}), set: (o, k, v) => ((o[k] = v), true) });
class El {
  constructor(tag) { this.tag = tag; this.style = {}; this.dataset = {}; this.attrs = {}; this.kids = new Map(); this.on = {};
    this.textContent = ''; this.innerHTML = ''; this.removed = false; const cls = new Set();
    this.classList = { toggle: (c, v) => ((v ?? !cls.has(c)) ? cls.add(c) : cls.delete(c)), contains: (c) => cls.has(c), add: (c) => cls.add(c) }; }
  getContext() { return ctx2d; }
  setAttribute(k, v) { this.attrs[k] = v; }
  addEventListener(k, f) { this.on[k] = f; }
  querySelector(sel) { if (sel === '.ex-groups ol' && !this.innerHTML.includes('ex-groups')) return null;
    if (!this.kids.has(sel)) this.kids.set(sel, new El(sel)); return this.kids.get(sel); }
  appendChild(el) { this.kids.set(el, el); return el; }
  remove() { this.removed = true; }
}
const winOn = {}, docOn = {};
globalThis.addEventListener = (k, f) => { (winOn[k] ||= []).push(f); };
globalThis.document = { visibilityState: 'visible', createElement: (tag) => new El(tag), body: new El('body'),
  addEventListener: (k, f) => { (docOn[k] ||= []).push(f); } };
const mem = new Map();
globalThis.localStorage = { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) };
let copied = null;
Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { clipboard: { writeText: async (t) => { copied = t; } } } });
const { makeGrid } = await import('./web/js/hex.js');
const M = await import('./web/js/ext/explore/model.js');
const { install } = await import('./web/js/ext/explore/index.js');
const grid = makeGrid({ radius: 1, cols: 6, rows: 5 });
const owner = Array.from({ length: grid.size }, (_, i) => (i % 6 === 5 ? -1 : i % 6 < 3 ? 0 : 1));
const handlers = {}, overlays = [], toasts = [], covers = [];
let toggle = null;
const app = {
  w: { grid, raw: { owner, states: [{ fips: 'A' }, { fips: 'B' }] } },
  cam: { scale: 40 }, state: { lens: null },
  on(k, f) { (handlers[k] ||= []).push(f); return () => handlers[k].splice(handlers[k].indexOf(f), 1); },
  emit(k, ev) { (handlers[k] || []).forEach((f) => f(ev)); },
  registerOverlay(o) { overlays.push(o); return () => overlays.splice(overlays.indexOf(o), 1); },
  requestDraw() {}, minimap: { setCover: (c) => covers.push(c) },
  ui: { toast: (m) => toasts.push(m), addMapToggle: (t) => (toggle = t),
        mapToggles: () => [{ id: 'roads', on: true }, { id: 'rail', on: false }, { id: 'explore', on: toggle.get() }] },
};
install(app);
const panel = () => [...document.body.kids.values()].find((el) => !el.removed) ?? null;
const click = (act) => panel().on.click({ target: { closest: () => ({ dataset: { act } }) } });
const wait = (ms = 700) => new Promise((r) => setTimeout(r, ms));
const out = (x) => { console.log(JSON.stringify(x)); process.exit(0); };
"""


def run_app(body: str, lang: str = "en"):
    script = APP.replace("__LANG__", json.dumps(lang)) + body
    res = subprocess.run([NODE, "--input-type=module", "-e", script], cwd=ROOT, capture_output=True, text=True)
    if res.returncode:
        raise AssertionError(res.stderr)
    return json.loads(res.stdout)


@unittest.skipUnless(NODE, "node is not installed")
class ExtensionTest(unittest.TestCase):
    def test_nothing_counts_while_the_toggle_is_off(self):
        got = run_app("""
            app.emit('tap', { cell: 8 });
            app.emit('select', { kind: 'city', city: { cell: 8 } });
            const off = [toggle.get(), overlays.length, panel()];
            toggle.set(true);
            out({ off, on: toggle.get(), z: overlays.map((o) => o.z), cover: covers.length, hovers: handlers.hover.length,
                  line: panel().querySelector('.ex-line').innerHTML });
        """)
        self.assertEqual(got["off"], [False, 0, None])
        self.assertTrue(got["on"])
        self.assertEqual(got["z"], [-10])  # under the selection, the hover outline and the highlights
        self.assertEqual([got["cover"], got["hovers"]], [1, 1])
        self.assertIn("<b>0%</b>", got["line"])  # the tap and the city selected while it was off did not count

    def test_tap_select_and_hover_explore_land_only(self):
        got = run_app("""
            toggle.set(true);
            const stored = () => M.createExplored(grid, owner).decode(localStorage.getItem('spainciv.explore'));
            app.emit('tap', { cell: 5 });                      // the sea: nothing
            const sea = panel().querySelector('.ex-line').innerHTML;
            app.emit('tap', { cell: 8 });
            const tapped = panel().querySelector('.ex-line').innerHTML;
            app.emit('select', { kind: 'city', city: { cell: 26 } });
            app.emit('select', { kind: 'state', index: 0 });
            const selected = panel().querySelector('.ex-line').innerHTML;
            app.emit('hover', { cell: 11 }); await wait();     // a sea hex beside land: nothing
            const seaHover = panel().querySelector('.ex-line').innerHTML;
            app.emit('hover', { cell: 3 }); app.emit('hover', { cell: -1 }); await wait();   // moved off before 650 ms
            const moved = panel().querySelector('.ex-line').innerHTML;
            app.emit('hover', { cell: 3 }); await wait();
            const hovered = panel().querySelector('.ex-line').innerHTML;
            const beforeFlush = localStorage.getItem('spainciv.explore');
            winOn.pagehide.forEach((f) => f());
            out({ sea, tapped, selected, seaHover, moved, hovered, beforeFlush, saved: stored() });
        """)
        self.assertIn("<b>0%</b>", got["sea"])
        self.assertIn("<b>28%</b>", got["tapped"])  # 7 of 25
        self.assertIn("<b>48%</b>", got["selected"])  # 12: a city explores, a province does not
        self.assertEqual(got["seaHover"], got["selected"])
        self.assertEqual(got["moved"], got["selected"])
        self.assertIn("<b>52%</b>", got["hovered"])  # 13: 3 and its neighbours, of which 2, 8 and 9 were known
        self.assertTrue(got["saved"])

    def test_a_group_cheers_once_and_the_share_text(self):
        got = run_app("""
            toggle.set(true);
            for (const c of [16, 4, 28]) app.emit('tap', { cell: c });
            const once = [...toasts];
            app.emit('tap', { cell: 22 });
            await click('share');
            out({ once, toasts, copied });
        """)
        self.assertEqual(got["once"], ["Este: no fog left"])
        self.assertEqual(got["toasts"], ["Este: no fog left", "Copied: paste it anywhere"])
        self.assertEqual(got["copied"].split("\n"), [
            "I have explored 40% of Spain on spainciv 🧭",
            "⬜🟩",
            "https://spainciv.djinnfoundry.com/#layers=roads,explore&lang=en",
        ])

    def test_reset_takes_two_clicks_and_switching_off_disarms_it(self):
        got = run_app("""
            toggle.set(true);
            app.emit('tap', { cell: 8 });
            const label = () => panel().querySelector('[data-act="reset"]').textContent;
            click('reset');
            const armed = [label(), M.createExplored(grid, owner).decode(localStorage.getItem('spainciv.explore')) || 'unsaved'];
            toggle.set(false); toggle.set(true);
            const fresh = label();
            click('reset'); click('reset');
            const back = M.createExplored(grid, owner);
            back.decode(localStorage.getItem('spainciv.explore'));
            out({ armed, fresh, line: panel().querySelector('.ex-line').innerHTML, saved: back.count, label: label() });
        """)
        self.assertEqual(got["armed"], ["Sure? Click again", "unsaved"])
        self.assertEqual(got["fresh"], "Start again")
        self.assertIn("<b>0%</b>", got["line"])
        self.assertEqual([got["saved"], got["label"]], [0, "Start again"])

    def test_another_tab_progress_comes_in(self):
        got = run_app("""
            toggle.set(true);
            app.emit('tap', { cell: 8 });
            const other = M.createExplored(grid, owner);
            other.reveal(28);
            winOn.storage.forEach((f) => f({ key: 'spainciv.explore', newValue: other.encode() }));
            const merged = panel().querySelector('.ex-line').innerHTML;
            localStorage.setItem('spainciv.explore', other.encode());   // saved there while this tab waits to save
            document.visibilityState = 'hidden';
            app.emit('tap', { cell: 0 });
            docOn.visibilitychange.forEach((f) => f());
            const back = M.createExplored(grid, owner);
            back.decode(localStorage.getItem('spainciv.explore'));
            out({ merged, saved: back.count, mine: back.isExplored(8), theirs: back.isExplored(28) });
        """)
        self.assertIn("<b>44%</b>", got["merged"])  # 7 + 4 (28 and its land neighbours)
        self.assertTrue(got["mine"] and got["theirs"])
        self.assertEqual(got["saved"], 14)

    def test_community_toasts_read_in_both_languages(self):
        es = countries.COUNTRIES["es"]
        cfg = site.page_config(es)
        for lang, groups, form in (("es", cfg["explore"]["groups"], "{}: ya no queda niebla"),
                                   ("en", cfg["texts"]["en"]["explore"]["groups"], "{}: no fog left")):
            names = [g["name"] for g in groups]
            got = run_app(f"const {{ t }} = await import('./web/js/i18n.js'); "
                          f"out({json.dumps(names)}.map((name) => t('explore.groupDone', {{ name }})));", lang)
            # The name stands alone before the colon: no article or gender to agree with ("País Vasco", "Canarias").
            self.assertEqual(got, [form.format(n) for n in names])
            self.assertEqual(len(got), 19)


class MainOrderTest(unittest.TestCase):
    """main.js: the fog (overlays below z 0) goes under the selection, the hover and the highlights, and every click is
    a "tap" before a layer, a mode or the default can take it."""

    main = (ROOT / "web/js/main.js").read_text(encoding="utf-8")

    def test_overlays_below_zero_draw_before_the_marks(self):
        frame = self.main[self.main.index("zMax: 0 })"):]
        self.assertLess(frame.index("drawOverlay(ctx, cam, w, state)"), frame.index("drawHighlight(ctx"))
        self.assertLess(frame.index("drawHighlight(ctx"), frame.index("zMin: 0, zMax: 100"))
        self.assertLess(frame.index("zMin: 0, zMax: 100"), frame.index("zMin: 100"))
        self.assertNotIn("drawOverlay(ctx, cam, w, state)", self.main[:self.main.index("zMax: 0 })")].split("function draw")[-1])

    def test_tap_comes_before_layer_click_and_mapclick(self):
        click = self.main[self.main.index('canvas.addEventListener("pointerup"'):]
        tap = click.index('events.emit("tap", ev)')
        self.assertLess(tap, click.index("const layerClick"))
        self.assertLess(tap, click.index('events.emit("mapclick", ev)'))
        self.assertIsNone(re.search(r'if \(events\.emit\("tap"', click))  # a tap handler cannot consume the click


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

    def test_every_community_has_one_interface_name(self):
        from pipeline.sources.es.provinces import COMMUNITIES, COMMUNITY_NAMES

        self.assertEqual(COMMUNITY_NAMES.keys(), COMMUNITIES.keys())

    def test_the_fog_is_the_page_choice(self):
        page = countries.Page(title="t", card_title="t", description="d", image_alt="a", data_credit="c")
        with countries.using("es", page=page) as c:
            self.assertNotIn("explore", site.page_config(c))


if __name__ == "__main__":
    unittest.main()
