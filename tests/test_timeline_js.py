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
        # The JS count and tie rule are Python's hex_values and dominant(): exact equality on the whole map, but for
        # land with nobody, which the year's lens leaves empty (grey) rather than 0.
        got = run("""
            const all = L.yearLayer(P, owner.length, () => true);
            out({ count: all.count, kind: all.kind });
        """)
        lenses = {l["id"]: l for l in json.loads((ROOT / "sites/es/data/lenses.json").read_text())["lenses"]}
        self.assertEqual(got["count"], [v or None for v in lenses["great_people"]["values"]])
        self.assertEqual(got["kind"], lenses["great_people_kind"]["values"])

    def test_a_tie_goes_to_the_lowest_category(self):
        got = run("""
            const p = (cell, kind) => ({ cell, kind, life: [1, 2] });
            const tie = L.pack([p(1, 5), p(1, 2), p(1, 5), p(1, 2), p(2, 7)], 8);
            const layer = L.yearLayer(tie, 4, L.aliveIn(tie, 1));
            out(layer);
        """)
        self.assertEqual(got, {"count": [None, 4, 1, None], "kind": [None, 2, 7, None],
                               "labels": [None, [0, 1, 2, 3], [4], None], "alive": 5, "approx": 0})

    def test_the_year_1000(self):
        got = run("""
            const y = L.yearLayer(P, owner.length, L.aliveIn(P, 1000));
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
        # Signed as people write years: -670 is 670 BC (-669), -1 is 1 BC (0); there is no year 0.
        got = run("out([['1550', '-670', '-1', '3000', '-5000', '0', '-0', '1550.5', 'abc', '', null, ' 1550', '1e3']"
                  ".map((v) => L.parseYear(v, -669, 2026)), [1520, 1, 0, -669].map(L.urlYear)]);")
        self.assertEqual(got, [[1550, -669, 0, 2026, -669, None, None, None, None, None, None, None, None],
                               ["1520", "1", "-1", "-670"]])

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


# The extension itself (web/js/ext/timeline/index.js) on a stand-in for main.js's app: the real hash state, modes and
# events of app/api.js, Spain's lenses and people, a dock whose elements are plain objects, and a browser history
# that Back walks. `go(hash)` loads the page at a link; `paste(hash)` puts another link in the address bar;
# `back()` is the Back button.
APP = """
import { readFileSync } from 'node:fs';
const read = (n) => JSON.parse(readFileSync(`sites/es/data/${n}.json`, 'utf8'));
const world = read('world');
const { setCountry } = await import('./web/js/app/country.js');
setCountry({ country: { ...world.country, lang: 'es', locale: 'es-ES', data: ['personajes'] } }, null);
const listeners = {};
const stack = [''];
let at = 0;
Object.assign(globalThis, {
  window: globalThis,
  addEventListener: (type, fn) => (listeners[type] ||= []).push(fn),
  location: { pathname: '/', search: '', hash: '' },
  history: {
    pushState(_, __, url) { stack.splice(++at, Infinity, url.replace(/^[^#]*/, '')); location.hash = stack[at]; },
    replaceState(_, __, url) { stack[at] = url.replace(/^[^#]*/, ''); location.hash = stack[at]; },
  },
  document: { hidden: false, addEventListener() {}, removeEventListener() {} },
  requestAnimationFrame: (f) => setTimeout(f, 0),
  cancelAnimationFrame: clearTimeout,
});
const node = () => {
  const kids = new Map();
  return { classList: { add() {}, remove() {} }, setAttribute() {}, removeAttribute() {}, querySelectorAll: () => [],
           querySelector: (s) => (kids.has(s) || kids.set(s, node()), kids.get(s)) };
};
const { createEmitter, createHashState, createModes } = await import('./web/js/app/api.js');
const lenses = read('lenses').lenses;
const lensById = new Map(lenses.map((l) => [l.id, l]));
const state = { lens: null, highlight: null };
const app = createEmitter();
const modes = createModes(app);
let dock = null;
function setLens(ref) {
  const lens = ref == null ? null : typeof ref === 'string' ? lensById.get(ref) || null : ref;
  if (lens === state.lens) return;
  state.lens = lens;
  url.schedule();
  app.emit('lens', lens);
}
const url = createHashState({
  read: () => ({ lens: state.lens?.id || null }),
  apply(p) { setLens(p.lens ? lensById.get(p.lens) || null : null); },
});
const people = read('personajes');
Object.assign(app, {
  registerMode: modes.registerMode, setMode: modes.setMode, lensById, state, setLens,
  hash: { register: url.register, update: url.schedule, value: url.value },
  w: { raw: { owner: world.owner } },
  addLens(lens) { lensById.set(lens.id, lens); },
  refreshLens() {}, registerOverlay: () => () => {}, setHighlight(h) { state.highlight = h; }, highlightBounds: () => null,
  loadData: async () => people,
  ui: { dock: () => (dock = node()), undock() { dock = null; } },
});
Object.defineProperty(app, 'mode', { get: () => modes.mode });
const tick = () => new Promise((r) => setTimeout(r, 0));
const settle = async () => { await tick(); await tick(); url.flush(); };
const go = async (hash) => { location.hash = hash; stack[at] = hash; url.applyCurrent(true); (await import('./web/js/ext/timeline/index.js')).install(app); await settle(); };
const paste = async (hash) => { stack.splice(++at, Infinity, hash); location.hash = hash; listeners.hashchange.forEach((f) => f()); await settle(); };
const back = async () => { location.hash = stack[--at]; listeners.popstate.forEach((f) => f()); await settle(); };
const shown = () => ({ hash: location.hash, entries: stack.length, mode: app.mode, year: dock?.querySelector('.tl-y').textContent ?? null,
                       lens: state.lens?.name ?? null });
const out = (x) => console.log(JSON.stringify(x));
"""


def drive(body: str):
    res = subprocess.run([NODE, "--input-type=module", "-e", APP + body], cwd=ROOT, capture_output=True, text=True)
    if res.returncode:
        raise AssertionError(res.stderr)
    return json.loads(res.stdout)


@unittest.skipUnless(NODE, "node is not installed")
class TimelineLinkTest(unittest.TestCase):
    def test_back_to_the_picker_entry_shows_the_download_year_again(self):
        # Opened from the picker (no anio), a step back writes anio; Back returns to the download year, and a later
        # write of the hash adds no year and no history entry, so Forward still has the step.
        got = drive("""
            await go('');
            setLens('great_people_year');
            await settle();
            const opened = shown();
            dock.querySelector('.tl-prev').onclick();
            await settle();
            const stepped = shown();
            await back();
            const backed = shown();
            url.flush();
            out({ opened, stepped, backed, after: shown(), forward: stack[at + 1] });
        """)
        self.assertEqual(got["opened"], {"hash": "#lens=great_people_year", "entries": 2, "mode": "timeline",
                                         "year": "2026", "lens": "Personajes vivos en 2026"})
        self.assertEqual((got["stepped"]["hash"], got["stepped"]["year"], got["stepped"]["entries"]),
                         ("#lens=great_people_year&anio=2020", "2020", 3))
        self.assertEqual(got["backed"], got["opened"] | {"entries": 3})
        self.assertEqual(got["after"], got["backed"])
        self.assertEqual(got["forward"], "#lens=great_people_year&anio=2020")

    def test_a_link_names_the_year_as_people_write_it(self):
        got = drive("""
            await go('#lens=great_people_year&anio=-201');
            const bc = shown();
            dock.querySelector('.tl-next').onclick();
            await settle();
            const next = shown();
            await paste('#lens=great_people_year&anio=0');
            out({ bc, next, zero: shown() });
        """)
        self.assertEqual((got["bc"]["year"], got["bc"]["mode"]), ("201 a. C.", "timeline"))
        self.assertEqual((got["next"]["year"], got["next"]["hash"]), ("200 a. C.", "#lens=great_people_year&anio=-200"))
        self.assertEqual(got["zero"]["year"], "2026")  # there is no year 0: the download year

    def test_a_year_without_the_lens_opens_the_timeline_and_no_year_without_it_does_nothing(self):
        got = drive("""
            await go('#anio=1520');
            const open = shown();
            setLens(null);
            await settle();
            const closed = shown();
            await back();
            out({ open, closed, again: shown() });
        """)
        self.assertEqual((got["open"]["mode"], got["open"]["year"], got["open"]["lens"]),
                         ("timeline", "1520", "Personajes vivos en 1520"))
        self.assertEqual((got["closed"]["mode"], got["closed"]["hash"]), (None, ""))
        self.assertEqual((got["again"]["mode"], got["again"]["year"]), ("timeline", "1520"))


if __name__ == "__main__":
    unittest.main()
