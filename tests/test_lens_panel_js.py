"""Lenses with a panel in the left dock (web/js/app/lensPanel.js) on a stub app: the real modes and events of
web/js/app/api.js, a lens state like main.js setLens, docks and elements that only record what is done to them, and a
URL hash whose keys are applied the way createHashState applies them to a key registered after the page loaded (once,
in a microtask). Then the two lenses that use it, the fiesta calendar and the sun lens, installed on Spain's data and
opened from links, and the reservoirs lens the same way. Run with node; skipped without it."""

import json
import shutil
import subprocess
import unittest

from pipeline.core.paths import ROOT

NODE = shutil.which("node")

PRELUDE = """
import { readFileSync } from 'node:fs';
import { setCountry } from './web/js/app/country.js';
const { createEmitter, createModes } = await import('./web/js/app/api.js');
const { lensPanel } = await import('./web/js/app/lensPanel.js');
const out = (x) => console.log(JSON.stringify(x));
const tick = () => new Promise((r) => setTimeout(r, 0));

// An element that takes anything: what the panels write into the dock is not under test here.
const fakeEl = () => {
  const classes = new Set(), listeners = [];
  return {
    classes, listeners, innerHTML: '', value: '', textContent: '', style: { setProperty() {} },
    classList: { add: (c) => classes.add(c), remove: (c) => classes.delete(c), toggle() {}, contains: (c) => classes.has(c) },
    setAttribute() {}, removeAttribute() {}, focus() {},
    addEventListener: (type, fn) => listeners.push(fn), removeEventListener: (type, fn) => listeners.splice(listeners.indexOf(fn), 1),
    querySelector: () => fakeEl(), querySelectorAll: () => [],
  };
};
globalThis.document = { body: fakeEl() };

function makeApp(link = '', extra = {}) {
  const hash = new URLSearchParams(link.replace(/^#/, ''));
  const app = { ...createEmitter(), state: { lens: null }, log: [], refreshed: 0 };
  const modes = createModes(app);
  Object.defineProperty(app, 'mode', { get: () => modes.mode });
  Object.assign(app, {
    registerMode: modes.registerMode, setMode: modes.setMode, escape: modes.escape,
    setLens(l) { const changed = l !== app.state.lens; app.state.lens = l; if (changed) app.emit('lens', l); },
    refreshLens() { app.refreshed++; },
    dockEl: null, undocks: 0,
    ui: {
      dock: (side, o) => { app.log.push(`dock ${side} ${o.width}`); return (app.dockEl = fakeEl()); },
      undock: (side) => { app.undocks++; app.log.push(`undock ${side}`); },
    },
    keys: new Map(),
    hash: {
      value: (k) => hash.get(k),
      update() {},
      register(key, h) {
        app.keys.set(key, h);
        if (hash.has(key)) queueMicrotask(() => h.set(hash.get(key)));
      },
    },
  }, extra);
  return app;
}
"""

SPAIN = """
const file = (n) => JSON.parse(readFileSync(`sites/es/data/${n}.json`, 'utf8'));
const world = file('world');
setCountry({ country: { ...world.country, lang: 'es', locale: 'es-ES', data: ['fiestas'], sunset: true } }, null);
const { prepareWorld } = await import('./web/js/world.js');
const w = prepareWorld(world, file('cities'), {});
const lensFile = file('lenses');
function spainApp(link) {
  const lensById = new Map(lensFile.lenses.map((l) => [l.id, l]));
  return makeApp(link, {
    w, lensById, data: { world, lenses: lensFile },
    addLens(l) { lensById.set(l.id, l); },
    loadData: async (n) => file(n),
    fitBounds() {}, setHighlight() {}, highlightBounds: () => null,
  });
}
"""


def run(body: str, prelude: str = PRELUDE):
    res = subprocess.run([NODE, "--input-type=module", "-e", prelude + body], cwd=ROOT, capture_output=True, text=True)
    if res.returncode:
        raise AssertionError(res.stderr)
    return json.loads(res.stdout)


@unittest.skipUnless(NODE, "node is not installed")
class LensPanelTest(unittest.TestCase):
    def setUp(self):
        self.body = """
            const app = makeApp(LINK);
            const lens = { id: 'cal' }, other = { id: 'other' };
            const calls = [];
            const panel = lensPanel(app, lens, { mode: 'cal', width: 320,
              open: (dock) => calls.push(['open', dock === app.dockEl, app.state.lens === lens]),
              close: () => calls.push(['close', app.mode]) });
            const snap = () => ({ mode: app.mode, lens: app.state.lens?.id ?? null, dock: !!panel.dock, calls: calls.splice(0) });
        """

    def go(self, steps: str, link: str = ""):
        return run(self.body.replace("LINK", json.dumps(link)) + steps)

    def test_picking_the_lens_opens_the_panel_and_closing_the_mode_clears_the_lens(self):
        got = self.go("""
            const s = [snap()];
            app.setLens(lens); s.push(snap(), app.dockEl.classes.has('lens-panel'));
            app.setMode(null); s.push(snap(), app.undocks);
            out(s);
        """)
        self.assertEqual(got, [
            {"mode": None, "lens": None, "dock": False, "calls": []},
            {"mode": "cal", "lens": "cal", "dock": True, "calls": [["open", True, True]]}, True,
            {"mode": None, "lens": None, "dock": False, "calls": [["close", "cal"]]}, 1,
        ])

    def test_entering_the_mode_picks_the_lens(self):
        got = self.go("app.setMode('cal'); out(snap());")
        self.assertEqual(got, {"mode": "cal", "lens": "cal", "dock": True, "calls": [["open", True, True]]})

    def test_another_lens_closes_the_panel_and_stays(self):
        got = self.go("app.setLens(lens); snap(); app.setLens(other); out(snap());")
        self.assertEqual(got, {"mode": None, "lens": "other", "dock": False, "calls": [["close", "cal"]]})

    def test_esc_and_the_close_button_close_both(self):
        got = self.go("""
            app.setLens(lens); snap(); app.escape(); const a = snap();
            app.setLens(lens); snap();
            app.dockEl.listeners[0]({ target: { closest: (sel) => sel === '[data-close]' } });
            const b = snap();
            app.setLens(lens); snap();
            app.dockEl.listeners[0]({ target: { closest: () => null } }); // a click elsewhere in the panel
            out([a, b, snap()]);
        """)
        self.assertEqual(got, [{"mode": None, "lens": None, "dock": False, "calls": [["close", "cal"]]},
                               {"mode": None, "lens": None, "dock": False, "calls": [["close", "cal"]]},
                               {"mode": "cal", "lens": "cal", "dock": True, "calls": []}])

    def test_a_link_naming_the_lens_opens_it_once_after_the_caller_is_ready(self):
        got = self.go("const before = snap(); await tick(); out([before, snap()]);", link="#lens=cal")
        self.assertEqual(got, [{"mode": None, "lens": None, "dock": False, "calls": []},
                               {"mode": "cal", "lens": "cal", "dock": True, "calls": [["open", True, True]]}])
        got = self.go("await tick(); out(snap());", link="#lens=other")
        self.assertEqual(got, {"mode": None, "lens": None, "dock": False, "calls": []})


@unittest.skipUnless(NODE, "node is not installed")
class CalendarPanelTest(unittest.TestCase):
    def open(self, link: str):
        return run(f"""
            const app = spainApp({json.dumps(link)});
            (await import('./web/js/ext/fiestas/index.js')).install(app);
            await tick(); await tick();
            const lens = app.lensById.get('fiestas_mes');
            out({{ mode: app.mode, lens: app.state.lens?.id ?? null, month: app.keys.get('mes').get(),
                   painted: lens.values.filter((v) => v != null).length }});
        """, PRELUDE + SPAIN)

    def test_a_link_with_the_lens_and_a_month_or_the_lens_alone_opens_the_calendar(self):
        month = self.open("#lens=fiestas_mes&mes=8")
        self.assertEqual((month["mode"], month["lens"], month["month"]), ("fiestas", "fiestas_mes", "8"))
        self.assertGreater(month["painted"], 0)
        alone = self.open("#lens=fiestas_mes")
        self.assertEqual((alone["mode"], alone["lens"]), ("fiestas", "fiestas_mes"))
        self.assertIsNotNone(alone["month"])

    def test_no_link_no_calendar(self):
        self.assertEqual(self.open("#lens=fiestas"), {"mode": None, "lens": None, "month": None, "painted": 0})


@unittest.skipUnless(NODE, "node is not installed")
class SunPanelTest(unittest.TestCase):
    def open(self, link: str, then: str = ""):
        return run(f"""
            const app = spainApp({json.dumps(link)});
            (await import('./web/js/ext/sun/index.js')).install(app);
            const lens = app.lensById.get('atardecer');
            const painted = () => lens.values.filter((v) => v != null).length;
            const before = painted();
            await tick(); await tick();
            {then}
            const cell = lens.values.findIndex((v) => v != null);
            out({{ before, mode: app.mode, lens: app.state.lens?.id ?? null, dia: app.keys.get('dia').get(),
                   sol: app.keys.get('sol').get(), heading: lens.heading ?? null, painted: painted(),
                   land: w.raw.owner.filter((o) => o >= 0).length, tip: cell >= 0 ? lens.tip(cell) : null,
                   source: lens.source, icon: lens.icon }});
        """, PRELUDE + SPAIN)

    def test_a_link_with_a_day_and_a_time_opens_the_lens_on_them(self):
        got = self.open("#lens=atardecer&dia=2026-06-21&sol=salida")
        self.assertEqual(got["before"], 0)  # nothing is worked out before the panel opens
        self.assertEqual((got["mode"], got["lens"], got["dia"], got["sol"], got["heading"]),
                         ("sun", "atardecer", "2026-06-21", "salida", "Salida del sol"))
        self.assertEqual(got["painted"], got["land"])
        # The tooltip gives the rest of the day, without the sunrise the lens already shows, and the zone.
        self.assertRegex(got["tip"], r"^Mediodía solar \d\d:\d\d · Puesta \d\d:\d\d · \d+ h( \d+ min)? de luz · (CEST|WEST)$")
        self.assertEqual((got["source"], got["icon"]), ("noaa_solar", "l-sunset"))

    def test_either_key_opens_it_and_back_or_forward_changes_the_time(self):
        got = self.open("#sol=mediodia", then="app.keys.get('sol').set('dia');")
        self.assertEqual((got["mode"], got["sol"], got["heading"]), ("sun", "dia", "Horas de luz"))
        self.assertNotIn("de luz", got["tip"])

    def test_a_day_before_1996_or_an_unknown_time_opens_nothing(self):
        for link in ("#dia=1995-10-15", "#sol=atardecer", "#lens=heritage"):
            with self.subTest(link=link):
                got = self.open(link)
                self.assertEqual((got["mode"], got["lens"], got["painted"], got["dia"]), (None, None, 0, None))

    def test_the_lens_alone_opens_on_spains_today(self):
        got = self.open("#lens=atardecer")
        today = run("out(S.isoDay(S.spainToday()));", "const S = await import('./web/js/ext/sun/solar.js');"
                    "const out = (x) => console.log(JSON.stringify(x));")
        self.assertEqual((got["mode"], got["sol"], got["dia"]), ("sun", "puesta", today))


@unittest.skipUnless(NODE, "node is not installed")
class ReservoirsPanelTest(unittest.TestCase):
    """The reservoirs lens (web/js/ext/embalses) on Spain's embalses.json, opened from links: the dock keeps the
    elements it is asked for, so what the panel writes can be read."""

    def open(self, link: str, then: str = "", weeks: bool = True):
        return run(f"""
            setCountry({{ country: {{ ...world.country, lang: 'es', locale: 'es-ES', data: ['embalses', 'embalses_semanas'] }} }}, null);
            globalThis.requestAnimationFrame = (f) => setTimeout(f, 0);
            globalThis.cancelAnimationFrame = (id) => clearTimeout(id);
            const app = spainApp({json.dumps(link)});
            const els = new Map(), loads = [];
            const keep = (el) => Object.assign(el, {{ querySelector: (sel) => (els.has(sel) || els.set(sel, keep(fakeEl())), els.get(sel)) }});
            app.ui.dock = () => (app.dockEl = keep(fakeEl()));
            Object.assign(app, {{
              registerStaticLayer() {{}}, requestDraw() {{}}, cam: {{ scale: 1 }},
              loadData: async (n) => (loads.push(n), n === 'embalses_semanas' && !{json.dumps(weeks)} ? null : file(n)),
            }});
            (await import('./web/js/ext/embalses/index.js')).install(app);
            const lens = app.lensById.get('embalses');
            for (let i = 0; i < 5; i++) await tick();
            {then}
            for (let i = 0; i < 5; i++) await tick();
            out({{ mode: app.mode, lens: app.state.lens?.id ?? null, semana: app.keys.get('semana').get(),
                   embalse: app.keys.get('embalse').get(), painted: lens.values.filter((v) => v != null).length, loads,
                   count: els.get('[data-count]')?.textContent ?? null, res: els.get('[data-res]')?.innerHTML ?? null }});
        """, PRELUDE + SPAIN)

    def test_a_link_with_the_lens_and_a_week_opens_it_on_that_week(self):
        got = self.open("#lens=embalses&semana=1995-11-09")  # between two Tuesdays: the one before
        self.assertEqual((got["mode"], got["lens"], got["semana"]), ("embalses", "embalses", "1995-11-07"))
        self.assertEqual(got["loads"], ["embalses", "embalses_semanas"])
        self.assertGreater(got["painted"], 5000)
        self.assertRegex(got["count"], r"^\d+ embalses en el Boletín esa semana")

    def test_the_lens_alone_opens_the_latest_week_without_the_matrix(self):
        got = self.open("#lens=embalses")
        latest = json.loads((ROOT / "sites/es/data/embalses.json").read_text())["dates"][-1]
        self.assertEqual((got["mode"], got["semana"], got["loads"]), ("embalses", latest, ["embalses"]))

    def test_a_week_that_is_not_a_date_or_another_lens_opens_nothing(self):
        for link in ("#semana=nada", "#semana=1995-02-30", "#lens=density&semana=1995-11-07", "#lens=density&embalse=Alcántara"):
            with self.subTest(link=link):
                got = self.open(link)
                self.assertEqual((got["mode"], got["lens"], got["loads"]), (None, None, []))

    def test_a_week_after_the_data_loaded(self):
        got = self.open("#lens=embalses", then="app.keys.get('semana').set('nada'); app.keys.get('semana').set('2005-06-14');")
        self.assertEqual(got["semana"], "2005-06-14")

    def test_a_reservoir_in_the_link_is_picked_and_kept(self):
        got = self.open("#lens=embalses&embalse=Alcántara")
        self.assertEqual((got["mode"], got["embalse"]), ("embalses", "Alcántara"))
        self.assertIn("embalses_semanas", got["loads"])
        self.assertIn("Alcántara", got["res"])
        self.assertIsNone(self.open("#lens=embalses&embalse=Nadie")["embalse"])

    def test_a_failed_weekly_load_says_so(self):
        got = self.open("#lens=embalses&semana=1995-11-07&embalse=Alcántara", weeks=False)
        self.assertEqual(got["semana"], "1995-11-07")
        self.assertEqual(got["count"], "No se ha podido cargar la serie semanal: los anillos y los embalses solo están "
                                        "en la última semana.")
        self.assertIn("No se ha podido cargar la serie semanal", got["res"])


if __name__ == "__main__":
    unittest.main()
