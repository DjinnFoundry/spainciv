"""Lenses with a panel in the left dock (web/js/app/lensPanel.js) on a stub app: the real modes and events of
web/js/app/api.js, a lens state like main.js setLens, docks and elements that only record what is done to them, and a
URL hash whose keys are applied the way createHashState applies them to a key registered after the page loaded (once,
in a microtask). Then the lenses that use it, the fiesta calendar, the sun lens and the climate of the month, installed on
Spain's data and opened from links, and the reservoirs lens the same way. Run with node; skipped without it."""

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
const M = await import('./web/js/ext/month.js');
const out = (x) => console.log(JSON.stringify(x));
const tick = () => new Promise((r) => setTimeout(r, 0));

// An element that takes anything; querySelector gives the same child for the same selector, so a test can read what a
// panel wrote there. A dock (strict) has no child of a class its HTML does not name, as a real one would not: a panel
// that reads its parts before writing them fails as it does in the browser. querySelectorAll('[data-x]') gives one
// element per data-x="…" in the HTML, the same ones until the HTML changes, so a test can read their attributes.
const fakeEl = (strict = false) => {
  const classes = new Set(), listeners = [], kids = new Map(), lists = new Map(), attrs = {};
  const el = {
    classes, listeners, attrs, innerHTML: '', value: '', textContent: '', style: { setProperty() {} },
    classList: { add: (c) => classes.add(c), remove: (c) => classes.delete(c), toggle() {}, contains: (c) => classes.has(c) },
    setAttribute: (k, v) => (attrs[k] = String(v)), removeAttribute: (k) => delete attrs[k], focus() {}, scrolled: 0, scrollIntoView() { el.scrolled++; },
    addEventListener: (type, fn) => listeners.push(fn), removeEventListener: (type, fn) => listeners.splice(listeners.indexOf(fn), 1),
    querySelector(sel) {
      const cls = /^\\.([\\w-]+)/.exec(sel)?.[1];
      if (strict && cls && !el.innerHTML.split(/class="([^"]*)"/).some((c, k) => k % 2 && c.split(' ').includes(cls))) return null;
      return kids.has(sel) ? kids.get(sel) : kids.set(sel, fakeEl()).get(sel);
    },
    querySelectorAll(sel) {
      const name = /^\\[data-([\\w-]+)\\]$/.exec(sel)?.[1];
      if (!name) return [];
      const key = name.replace(/-(\\w)/g, (_, c) => c.toUpperCase());
      if (lists.get(sel)?.html !== el.innerHTML) {
        const found = [...el.innerHTML.matchAll(new RegExp(`data-${name}="([^"]*)"`, 'g'))];
        lists.set(sel, { html: el.innerHTML, els: found.map(([, v]) => Object.assign(fakeEl(), { dataset: { [key]: v } })) });
      }
      return lists.get(sel).els;
    },
  };
  return el;
};
// What the app's emitter reports when a handler throws (createEmitter logs and carries on).
const errors = [];
console.error = (...a) => {
  const m = a.map(String).join(" ");
  if (["handler failed", "enter() failed", "exit() failed"].some((f) => m.includes(f))) errors.push(m);
};
globalThis.document = { body: fakeEl(), hidden: false, addEventListener() {}, removeEventListener() {} };

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
      dock: (side, o) => { app.log.push(`dock ${side} ${o.width}`); return (app.dockEl = fakeEl(true)); },
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
setCountry({ country: { ...world.country, lang: 'es', locale: 'es-ES', data: ['fiestas', 'clima'], sunset: true } }, null);
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
    layers: new Map(), registerStaticLayer(l) { this.layers.set(l.id, l); }, phone: false, isMobile() { return this.phone; },
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

    def test_a_panel_of_several_lenses_stays_open_between_them(self):
        got = run("""
            const app = makeApp('#lens=b');
            const a = { id: 'a' }, b = { id: 'b' }, c = { id: 'c' }, other = { id: 'other' };
            const calls = [];
            let chosen = c;
            const panel = lensPanel(app, [a, b, c], { mode: 'multi', pick: () => chosen,
              open: () => calls.push(['open', app.state.lens.id]), close: () => calls.push(['close']) });
            const snap = () => ({ mode: app.mode, lens: app.state.lens?.id ?? null, calls: calls.splice(0) });
            await tick();
            const s = [snap()];             // the link's lens opens the panel on it
            app.setLens(a); s.push(snap());  // another of its lenses: the panel stays open
            app.setLens(other); s.push(snap());
            app.setMode('multi'); s.push(snap()); // entering the mode opens on pick()
            app.setMode(null); s.push(snap(), !!panel.dock);
            out(s);
        """)
        self.assertEqual(got, [
            {"mode": "multi", "lens": "b", "calls": [["open", "b"]]},
            {"mode": "multi", "lens": "a", "calls": []},
            {"mode": None, "lens": "other", "calls": [["close"]]},
            {"mode": "multi", "lens": "c", "calls": [["open", "c"]]},
            {"mode": None, "lens": None, "calls": [["close"]]}, False,
        ])


@unittest.skipUnless(NODE, "node is not installed")
class CalendarPanelTest(unittest.TestCase):
    def open(self, link: str):
        return run(f"""
            const app = spainApp({json.dumps(link)});
            (await import('./web/js/ext/fiestas/index.js')).install(app);
            await tick(); app.emit('extensions', []); await tick();
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

    def test_a_month_alone_opens_the_calendar_on_it(self):
        got = self.open("#mes=8")
        self.assertEqual((got["mode"], got["lens"], got["month"]), ("fiestas", "fiestas_mes", "8"))
        self.assertGreater(got["painted"], 0)

    def test_no_link_no_calendar(self):
        self.assertEqual(self.open("#lens=fiestas"), {"mode": None, "lens": None, "month": None, "painted": 0})


@unittest.skipUnless(NODE, "node is not installed")
class ClimatePanelTest(unittest.TestCase):
    def open(self, link: str, then: str = "", extra: str = ""):
        return run(f"""
            const app = spainApp({json.dumps(link)});
            for (const x of ['fiestas', 'clima']) (await import(`./web/js/ext/${{x}}/index.js`)).install(app);
            await tick(); app.extensions = []; app.emit('extensions', []); await tick(); await tick();
            const clima = JSON.parse(readFileSync('sites/es/data/clima.json', 'utf8'));
            const burgos = clima.stations.find((s) => s.wmo === '08075');
            const lens = () => app.state.lens;
            {then}
            out({{ mode: app.mode, lens: lens()?.id ?? null, mes: app.keys.get('mes').get(),
                   painted: lens()?.values.filter((v) => v != null).length ?? 0, land: w.raw.owner.filter((o) => o >= 0).length,
                   heading: lens()?.heading ?? null, burgos: lens()?.tip?.(burgos.cell) ?? null, {extra} }});
        """, PRELUDE + SPAIN)

    def test_a_link_with_a_climate_lens_and_a_month_opens_that_month(self):
        got = self.open("#lens=clima_temp&mes=1")
        self.assertEqual((got["mode"], got["lens"], got["mes"], got["heading"]),
                         ("clima", "clima_temp", "1", "Temperatura media en enero"))
        self.assertEqual(got["painted"], got["land"])
        self.assertEqual(got["burgos"][0][:5], "máx. ")
        self.assertIn("rejilla diaria ROCIO de AEMET, media 1991-2020 calculada por spainciv", got["burgos"][0])
        self.assertIn("Estación Burgos Aeropuerto (891 m), normal OMM 1991-2020: 3,6 °C", got["burgos"])

    def test_the_lens_alone_opens_this_month_and_the_month_alone_still_opens_the_fiestas(self):
        alone = self.open("#lens=clima_lluvia")
        self.assertEqual((alone["mode"], alone["lens"]), ("clima", "clima_lluvia"))
        self.assertIsNotNone(alone["mes"])
        fiestas = self.open("#mes=8")
        self.assertEqual((fiestas["mode"], fiestas["lens"], fiestas["mes"]), ("fiestas", "fiestas_mes", "8"))

    def test_moving_between_variables_keeps_the_panel_and_sunshine_is_only_at_stations(self):
        got = self.open("#lens=clima_temp&mes=7", then="app.setLens(app.lensById.get('clima_sol'));",
                        extra="stations: clima.stations.filter((s) => s.sun).length, "
                              "nosun: lens().tip(lens().values.findIndex((v, i) => v == null && w.raw.owner[i] >= 0)), "
                              "label: lens().null_label")
        self.assertEqual((got["mode"], got["lens"], got["mes"]), ("clima", "clima_sol", "7"))
        self.assertLessEqual(got["painted"], got["stations"])
        self.assertGreater(got["painted"], 60)
        self.assertEqual(got["label"], "Sin estación con horas de sol")
        self.assertRegex(got["nosun"][-1], r"^Estación más cercana: .+, \d+,\d h en julio \(\d[\d.]* h al año\)$")

    def test_closing_and_reopening_on_another_variable_throws_nothing(self):
        # Esc, then the lens picker on another of the four: the dock holds the loading line when the lens event comes.
        got = self.open("#lens=clima_temp&mes=3", then="""
            app.escape();
            const closed = [app.mode, app.keys.get('mes').get()];
            app.setLens(app.lensById.get('clima_lluvia'));
            const loading = app.dockEl.innerHTML.includes('Cargando');
            await tick(); await tick();
        """, extra="closed, loading, errors, tabs: app.dockEl.innerHTML.includes('cl-tabs'), "
                   "now: M.currentMonth(), month: M.monthState(app).month")
        self.assertEqual(got["errors"], [])
        self.assertEqual(got["closed"], [None, None])
        self.assertTrue(got["loading"] and got["tabs"])
        self.assertEqual((got["mode"], got["lens"]), ("clima", "clima_lluvia"))
        self.assertEqual(got["month"], got["now"])  # closed, the month went back to this one, as the URL says
        self.assertEqual(got["mes"], str(got["now"]))

    def test_before_the_data_the_lenses_have_no_scale_and_say_they_are_loading(self):
        got = run("""
            const app = spainApp('');
            (await import('./web/js/ext/clima/index.js')).install(app);
            const l = app.lensById.get('clima_temp');
            out([l.domain, l.heading, l.click_hint, l.decimals]);
        """, PRELUDE + SPAIN)
        self.assertEqual(got, [None, "Cargando el clima…", "Haz clic para fijar su diagrama de Walter-Lieth", 1])

    def test_grid_lenses_and_the_sunshine_lens_name_their_own_source(self):
        got = self.open("#lens=clima_lluvia&mes=11", then="const rain = lens().note; app.setLens(app.lensById.get('clima_sol'));",
                        extra="rain, sun: lens().note, sum: app.dockEl.querySelector('.cl-sum').textContent")
        self.assertEqual(got["rain"], "Media 1991-2020 de noviembre, calculada por spainciv con la rejilla ROCIO de AEMET.")
        self.assertEqual(got["sun"], "Normal OMM 1991-2020 de noviembre. Fuente: AEMET.")
        self.assertRegex(got["sum"], r"^Más sol en noviembre: .+, \d+,\d h; menos: .+, \d+,\d h \(normales OMM 1991-2020\)\.$")

    def test_the_sunshine_stations_are_discs_with_their_own_tooltip(self):
        got = self.open("#lens=clima_temp&mes=7", then="""
            const layer = app.layers.get('clima-sun');
            const izana = clima.stations.find((s) => s.name === 'Izaña');
            const before = layer.visible();
            app.setLens(app.lensById.get('clima_sol'));
            const x = w.grid.cx(izana.cell), y = w.grid.cy(izana.cell);
            const hit = layer.hit(x + 2 * w.grid.R, y, 2); // 2 px hexes: the disc reaches beyond the hex
            const miss = layer.hit(x + 2 * w.grid.R, y, 40);
        """, extra="before, after: layer.visible(), hit: hit?.name, miss, tip: layer.tooltip(hit), sig: layer.sig()")
        self.assertFalse(got["before"])
        self.assertTrue(got["after"])
        self.assertEqual((got["hit"], got["miss"], got["sig"]), ("Izaña", None, "7"))
        self.assertIn("Estación Izaña", got["tip"])
        self.assertIn("Horas de sol en julio: <b>402,4 h</b>", got["tip"])

    def test_on_a_phone_the_panel_has_the_colour_key_the_touch_hints_and_brings_a_pinned_diagram_up(self):
        got = self.open("#lens=clima_temp&mes=1", then="""
            app.phone = true;
            app.emit('lens', lens()); // nothing changes: the same variable
            const hint = app.dockEl.querySelector('.cl-chart').innerHTML;
            app.emit('mapclick', { cell: burgos.cell, city: null });
            const chart = app.dockEl.querySelector('.cl-chart');
        """, extra="hint, pinned: chart.innerHTML, scrolled: chart.scrolled, "
                   "key: app.dockEl.querySelector('.pk-key').querySelector('.pk-ticks').innerHTML, "
                   "ramp: app.dockEl.querySelector('.pk-key').querySelector('.pk-ramp').style.background")
        self.assertIn("Pasa el puntero", got["hint"])  # built on the desktop
        self.assertIn("Toca otra provincia para cambiarla.", got["pinned"])
        self.assertEqual(got["scrolled"], 1)
        self.assertEqual(got["key"], "<span>0 °C</span><span>14,0 °C</span><span>≥ 28,0 °C</span>")
        self.assertTrue(got["ramp"].startswith("linear-gradient(90deg, #2b3f8f"))
        self.assertIn("normales de AEMET 1991-2020", got["pinned"])

    def test_the_link_to_the_fiestas_keeps_the_month_and_back(self):
        got = self.open("#lens=clima_heladas&mes=2", then="""
            M.monthState(app).follow({ target: { closest: () => ({ dataset: { monthPage: 'fiestas' } }) } });
            const there = [app.mode, app.keys.get('mes').get()];
            M.monthState(app).follow({ target: { closest: () => ({ dataset: { monthPage: 'clima' } }) } });
        """, extra="there")
        self.assertEqual(got["there"], ["fiestas", "2"])
        self.assertEqual((got["mode"], got["lens"], got["mes"]), ("clima", "clima_heladas", "2"))

    def test_the_diagram_follows_the_pointer_and_a_click_pins_it(self):
        got = self.open("#lens=clima_temp&mes=1", then="""
            const chart = app.dockEl.querySelector('.cl-chart');
            const cordoba = w.raw.owner.findIndex((o) => o >= 0 && w.raw.states[o].fips === '14');
            app.emit('hover', { cell: burgos.cell });
            const first = chart.innerHTML;
            const taken = app.emit('mapclick', { cell: burgos.cell, city: null, state: w.raw.owner[burgos.cell] });
            app.emit('hover', { cell: cordoba });
            const pinned = chart.innerHTML;
        """, extra="first: first.includes('>Burgos<'), taken, pinned: pinned.includes('>Burgos<') && pinned.includes('data-unpin')")
        self.assertEqual((got["first"], got["taken"], got["pinned"]), (True, True, True))

    def test_without_clima_in_the_data_nothing_is_added(self):
        got = run("""
            setCountry({ country: { ...world.country, lang: 'es', locale: 'es-ES', data: ['fiestas'] } }, null);
            const app = spainApp('#lens=clima_temp&mes=1');
            (await import('./web/js/ext/clima/index.js')).install(app);
            await tick();
            out([...app.lensById.keys()].filter((k) => k.startsWith('clima')));
        """, PRELUDE + SPAIN)
        self.assertEqual(got, [])


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



@unittest.skipUnless(NODE, "node is not installed")
class TimelinePanelTest(unittest.TestCase):
    """The great people timeline (web/js/ext/timeline) on Spain's personajes.json: two lenses, one panel."""

    def open(self, link: str, then: str = ""):
        return run(f"""
            setCountry({{ country: {{ ...world.country, lang: 'es', locale: 'es-ES', data: ['personajes'] }} }}, null);
            const app = spainApp({json.dumps(link)});
            const overlays = [], labels = [];
            let loads = 0;
            const dock = app.ui.dock;
            Object.assign(app, {{
              registerOverlay: (o) => (overlays.push(o.id), () => overlays.push(`-${{o.id}}`)),
              loadData: async (n) => (loads++, file(n)),
              ui: {{ ...app.ui, dock: (side, o) => (labels.push(o.label), dock(side, o)) }},
            }});
            (await import('./web/js/ext/timeline/index.js')).install(app);
            const lens = (id) => app.lensById.get(id);
            const snap = () => ({{ mode: app.mode, lens: app.state.lens?.id ?? null, log: app.log.splice(0), undocks: app.undocks,
              panel: app.dockEl?.classes.has('lens-panel') ?? false, year: app.keys.get('anio').get(),
              slider: app.dockEl?.innerHTML.includes('tl-slider') ?? false, refreshed: app.refreshed, overlays: overlays.splice(0),
              names: [lens('great_people_year').name, lens('great_people_year_kind').name],
              pressed: (app.dockEl?.querySelectorAll('[data-lens]') ?? []).map((b) => [b.dataset.lens, b.attrs['aria-pressed']]),
              famousHead: app.dockEl?.querySelector('.tl-h3')?.hidden ?? null,
              text: app.dockEl?.innerHTML.replace(/<[^>]*>/g, ' ').replace(/\\s+/g, ' ').trim() ?? null }});
            for (let i = 0; i < 3; i++) await tick();
            const s = [snap()];
            {then}
            out({{ s, loads, labels, errors }});
        """, PRELUDE + SPAIN)

    def test_a_link_with_the_kind_lens_and_a_year_opens_the_timeline_on_both(self):
        got = self.open("#lens=great_people_year_kind&anio=1520")
        first = {k: v for k, v in got["s"][0].items() if k not in ("text", "famousHead")}
        self.assertEqual(first | {"refreshed": 0}, {
            "mode": "timeline", "lens": "great_people_year_kind", "log": ["dock left 360"], "undocks": 0, "panel": True,
            "year": "1520", "slider": True, "refreshed": 0, "overlays": ["timeline-dots"],
            "names": ["Personajes vivos en 1520", "Oficios en 1520"],
            "pressed": [["great_people_year", "false"], ["great_people_year_kind", "true"]]})
        self.assertEqual((got["loads"], got["labels"], got["errors"]), (1, ["Personajes en el tiempo"], []))

    def test_a_year_alone_opens_it_on_the_people_alive(self):
        got = self.open("#anio=1520")
        self.assertEqual((got["s"][0]["mode"], got["s"][0]["lens"], got["s"][0]["year"]),
                         ("timeline", "great_people_year", "1520"))

    def test_moving_between_its_two_lenses_keeps_the_panel(self):
        got = self.open("#lens=great_people_year&anio=1520", then="""
            app.setLens(lens('great_people_year_kind')); await tick(); s.push(snap());
            app.setLens(lens('great_people_year')); await tick(); s.push(snap());
        """)
        count, kind = (["great_people_year", "true"], ["great_people_year_kind", "false"]), \
            (["great_people_year", "false"], ["great_people_year_kind", "true"])
        self.assertEqual([(x["mode"], x["lens"], x["log"], x["undocks"], x["pressed"]) for x in got["s"]], [
            ("timeline", "great_people_year", ["dock left 360"], 0, list(count)),
            ("timeline", "great_people_year_kind", [], 0, list(kind)),
            ("timeline", "great_people_year", [], 0, list(count))])
        self.assertEqual(got["loads"], 1)

    def test_another_lens_closes_the_panel_and_stays(self):
        got = self.open("#lens=great_people_year&anio=1520", then="app.setLens(lens('great_people')); s.push(snap());")
        self.assertEqual({k: got["s"][1][k] for k in ("mode", "lens", "log", "undocks", "overlays", "panel")}, {
            "mode": None, "lens": "great_people", "log": ["undock left"], "undocks": 1, "overlays": ["-timeline-dots"],
            "panel": False})

    def test_esc_and_the_close_button_close_both_without_repainting_the_map(self):
        # lensPanel calls close() with the lens still on: renaming the lenses to the download year must not repaint.
        got = self.open("#lens=great_people_year&anio=1520", then="""
            app.escape(); s.push(snap());
            app.setLens(lens('great_people_year')); for (let i = 0; i < 3; i++) await tick(); s.push(snap());
            app.keys.get('anio').set('1520'); s.push(snap());
            app.dockEl.listeners[0]({ target: { closest: (sel) => (sel === '[data-close]' ? {} : null) } }); s.push(snap());
        """)
        opened, esc, reopened, moved, closed = got["s"]
        for c, before in ((esc, opened), (closed, moved)):
            self.assertEqual((c["mode"], c["lens"], c["panel"], c["log"]), (None, None, False, ["undock left"]))
            self.assertEqual(c["refreshed"], before["refreshed"])
            self.assertEqual(c["names"], ["Personajes vivos en 2026", "Oficios en 2026"])
        self.assertEqual((reopened["mode"], reopened["year"], reopened["names"][0]),
                         ("timeline", None, "Personajes vivos en 2026"))  # from the picker: the download year
        self.assertEqual(moved["names"][0], "Personajes vivos en 1520")
        self.assertEqual(closed["undocks"], 2)
        # The dock's name is the panel's own, not the year's that paint() wrote on the lenses.
        self.assertEqual(got["labels"], ["Personajes en el tiempo"] * 2)
        self.assertEqual((got["loads"], got["errors"]), (1, []))

    def test_closing_while_the_people_load_leaves_the_dock_alone(self):
        got = self.open("", then="""
            let resolve;
            app.loadData = () => (loads++, new Promise((r) => (resolve = r)));
            app.setLens(lens('great_people_year')); await tick();
            const loading = app.dockEl;
            app.escape();
            resolve(file('personajes')); for (let i = 0; i < 3; i++) await tick();
            s.push(snap(), loading.innerHTML.includes('tl-slider'));
        """)
        self.assertEqual((got["s"][0]["mode"], got["s"][1]["mode"], got["s"][2]), (None, None, False))
        self.assertEqual((got["loads"], got["errors"]), (1, []))

    def test_a_year_with_nobody_alive_has_no_famous_heading(self):
        alive, nobody = self.open("#lens=great_people_year&anio=1520", then="""
            app.keys.get('anio').set('-101'); s.push(snap());
        """)["s"]
        self.assertEqual((alive["famousHead"], nobody["year"], nobody["famousHead"]), (False, "-101", True))

    def test_the_panel_has_its_head_and_close_button_when_the_people_fail_to_load(self):
        for link, fail, line in (("#lens=great_people_year", "async () => { throw new Error('blocked'); }",
                                  "No se han podido cargar los personajes."),
                                 ("#lens=great_people_year", "async () => ({ people: [{ name: 'x' }] })",
                                  "Este mapa no tiene fechas de los personajes.")):
            with self.subTest(line=line):
                got = self.open("", then=f"""
                    app.loadData = {fail};
                    app.setLens(lens('great_people_year')); for (let i = 0; i < 3; i++) await tick(); s.push(snap());
                    s.push(app.dockEl.innerHTML.includes('data-close'));
                    app.dockEl.listeners[0]({{ target: {{ closest: (sel) => (sel === '[data-close]' ? {{}} : null) }} }}); s.push(snap());
                """)
                failed, close, closed = got["s"][1:]
                self.assertEqual((failed["mode"], failed["text"], close), ("timeline", f"Personajes en el tiempo ✕ {line}", True))
                self.assertEqual((closed["mode"], closed["lens"]), (None, None))


if __name__ == "__main__":
    unittest.main()
