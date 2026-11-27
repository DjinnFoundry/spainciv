"""The train lens in the browser: the duration format (web/js/ui/lenses.js), the rail layer that a lens hides
(web/js/ext/layers/layers.js, hides_layers) and the rules of web/js/ext/transit/model.js. Run with node; skipped
without it."""

import json
import shutil
import subprocess
import unittest

from pipeline.core.paths import ROOT

NODE = shutil.which("node")


def run(body: str, lang: str = "es"):
    locale = {"es": "es-ES", "en": "en-IE"}[lang]
    prelude = f"""
        const {{ setCountry }} = await import('./web/js/app/country.js');
        setCountry({{ country: {{ id: 'es', lang: '{lang}', locale: '{locale}' }} }}, null);
        const L = await import('./web/js/ui/lenses.js');
        const M = await import('./web/js/ext/transit/model.js');
        const out = (x) => console.log(JSON.stringify(x));
    """
    res = subprocess.run([NODE, "--input-type=module", "-e", prelude + body], cwd=ROOT, capture_output=True, text=True)
    if res.returncode:
        raise AssertionError(res.stderr)
    return json.loads(res.stdout)


SEVILLA = {"name": "Sevilla-Santa Justa", "x": 0, "y": 0, "cell": 0, "stops": ["51003"], "trains": [83, 0, 142],
           "best": {"min": 156, "dep": "07:00", "arr": "09:36", "to": "Madrid-Puerta de Atocha", "changes": 0,
                    "legs": [["AVE 02060", "Sevilla-Santa Justa", "Madrid-Puerta de Atocha"]]}}
GANDIA = {"name": "Gandia", "x": 0, "y": 0, "cell": 0, "stops": ["69110"], "trains": [0, 0, 1],
          "best": {"min": 208, "dep": "06:10", "arr": "09:38", "to": "Madrid-Chamartín", "changes": 1,
                   "legs": [["C1", "Gandia", "València Nord"], [None, "València Nord", "València-Joaquín Sorolla"],
                            ["AVE 05071", "València-Joaquín Sorolla", "Madrid-Chamartín"]]}}
NORD = {"name": "València-Estació del Nord", "x": 0, "y": 0, "cell": 0, "stops": ["65000"], "trains": [14, 32, 133],
        "best": {"min": 129, "dep": "07:28", "arr": "09:38", "to": "Madrid-Chamartín", "changes": 0,
                 "legs": [[None, "València-Estació del Nord", "València-Joaquín Sorolla"],
                          ["Iryo 06083", "València-Joaquín Sorolla", "Madrid-Chamartín"]]}}


@unittest.skipUnless(NODE, "node is not installed")
class DurationTest(unittest.TestCase):
    def test_values_and_ticks(self):
        got = run("""
            const lens = { format: 'duration', domain: [45, 420], scale: 'linear', null_label: 'Lejos' };
            out([[156, 45, 120, 59.6, 600, null].map((v) => L.formatLensValue(lens, v)),
                 [0, 1, 2, 3, 4].map((k) => L.formatLensTick(lens, k / 4, k))]);
        """)
        self.assertEqual(got, [["2 h 36 min", "45 min", "2 h", "1 h", "10 h", "Lejos"],
                               ["≤ 45 min", "2,5 h", "4 h", "5,5 h", "≥ 7 h"]])

    def test_english(self):
        got = run("out(L.formatLensTick({ format: 'duration', domain: [45, 420], scale: 'linear' }, 0.25, 1));", "en")
        self.assertEqual(got, "2.5 h")


@unittest.skipUnless(NODE, "node is not installed")
class HidesLayersTest(unittest.TestCase):
    def test_a_lens_hides_the_rail_layer_while_it_is_open(self):
        got = run("""
            const { makeLayers } = await import('./web/js/ext/layers/layers.js');
            const app = { state: { lens: null } };
            const model = { net: {}, parks: [], ranges: [], ports: [], airports: [], installations: [], wonders: [], routes: [], w: {}, version: 1 };
            const layers = makeLayers(model, { rail: true, roads: true }, { app });
            const rail = layers.find((l) => l.id === 'rail'), roads = layers.find((l) => l.id === 'roads');
            const seen = [rail.visible()];
            app.state.lens = { id: 'income' };
            seen.push(rail.visible());
            app.state.lens = { id: 'rail_madrid', hides_layers: ['rail'] };
            seen.push(rail.visible(), roads.visible());
            const gallery = makeLayers(model, { rail: true }).find((l) => l.id === 'rail');  // no app: the art gallery
            out([...seen, gallery.visible()]);
        """)
        self.assertEqual(got, [True, True, False, True, True])


@unittest.skipUnless(NODE, "node is not installed")
class ModelTest(unittest.TestCase):
    def test_bands_sizes_and_line_classes(self):
        got = run("""
            out({ bands: [1, 9, 10, 49, 50, 900].map(M.band),
                  lines: M.lineClasses({ links: [[1, 2, 3], [2, 3, 60]], ghost: [[4, 5]] }),
                  bigger: M.stationRadius(900, 8) > M.stationRadius(9, 8), zoom: M.stationRadius(100, 30) > M.stationRadius(100, 4) });
        """)
        self.assertEqual(got, {"bands": [0, 0, 1, 1, 2, 2], "lines": {"served": [[1, 2, 0], [2, 3, 2]], "ghost": [[4, 5, "g"]]},
                               "bigger": True, "zoom": True})

    def test_station_tooltips(self):
        got = run(f"""
            out([M.stationTip({json.dumps(SEVILLA)}, M.dayLabel('2026-12-09')), M.stationTip({json.dumps(GANDIA)}, '9 de diciembre'),
                 M.stationTip({{ name: 'Madrid-Atocha', trains: [1, 1, 1], best: null, madrid: true }}, 'x'),
                 M.stationTip({{ name: 'Lejos <b>', trains: [0, 1, 0], best: null }}, 'x')]);
        """)
        self.assertEqual(got[0], "<b>Sevilla-Santa Justa</b>: 225 trenes el 9 de diciembre (83 de alta velocidad y larga "
                                 "distancia y 142 de Cercanías).<br>A Madrid en 2 h 36 min: sale "
                                 "07:00, llega 09:36 a Madrid-Puerta de Atocha, sin transbordos (AVE 02060)")
        self.assertIn("1 tren el 9 de diciembre (1 de Cercanías).", got[1])
        self.assertIn("1 transbordo (C1 Gandia → València Nord; a pie a València-Joaquín Sorolla; AVE 05071 "
                      "València-Joaquín Sorolla → Madrid-Chamartín)", got[1])
        self.assertTrue(got[2].endswith("<br>En Madrid."))
        self.assertIn("&lt;b&gt;", got[3])
        self.assertTrue(got[3].endswith("Ese día ningún tren lleva de aquí a Madrid."))
        self.assertIn("1 tren el x (1 de media distancia).", got[3])

    def test_a_journey_that_starts_on_foot(self):
        got = run(f"out([M.stationTip({json.dumps(NORD)}, 'x'), M.stationTip({{ name: 'Madrid-Recoletos', trains: [0, 0, 0], best: null, madrid: true }}, 'x')]);")
        self.assertIn("14 de alta velocidad y larga distancia, 32 de media distancia y 133 de Cercanías", got[0])
        self.assertTrue(got[0].endswith("sin transbordos (a pie a València-Joaquín Sorolla; Iryo 06083 "
                                        "València-Joaquín Sorolla → Madrid-Chamartín)"), got[0])
        self.assertEqual(got[1], "<b>Madrid-Recoletos</b>: 0 trenes el x.<br>En Madrid.")  # no empty split
        en = run(f"out(M.stationTip({json.dumps(NORD)}, 'x'));", "en")
        self.assertIn("(walk to València-Joaquín Sorolla; Iryo 06083 València-Joaquín Sorolla → Madrid-Chamartín)", en)

    def test_english_tooltips(self):
        got = run(f"""
            out([M.stationTip({json.dumps(SEVILLA)}, M.dayLabel('2026-12-09')), M.linkTip({{ kind: 'ghost' }}, M.dayLabel('2026-12-09')),
                 M.linkTip({{ kind: 'served', n: 1 }}, '9 December')]);
        """, "en")
        self.assertEqual(got[0], "<b>Sevilla-Santa Justa</b>: 225 trains on 9 December (83 high-speed and long-distance "
                                 "and 142 Cercanías).<br>To Madrid in 2 h 36 min: leaves 07:00, arrives "
                                 "09:36 at Madrid-Puerta de Atocha, direct (AVE 02060)")
        self.assertEqual(got[1], "Adif track with no passenger trains on 9 December (may carry freight)")
        self.assertEqual(got[2], "1 passenger train on 9 December")

    def test_link_tooltips_and_lens_layer(self):
        got = run("""
            const doc = { stations: [{ name: 'Teruel' }], lens: { values: [300, null], station: [0, null] } };
            out([M.linkTip({ kind: 'ghost' }, '9 de diciembre'), M.linkTip({ kind: 'served', n: 1234 }, '9 de diciembre'),
                 M.lensLayer(doc)]);
        """)
        self.assertEqual(got[0], "Vía de Adif sin trenes de viajeros el 9 de diciembre (puede tener mercancías)")
        self.assertEqual(got[1], "1234 trenes de viajeros el 9 de diciembre")
        self.assertEqual(got[2], {"values": [300, None], "names": ["desde Teruel"], "labels": [[0], None]})

    def test_hits(self):
        got = run("""
            const { makeGrid } = await import('./web/js/hex.js');
            const grid = makeGrid({ radius: 5, cols: 6, rows: 3 });
            const idx = M.linkIndex({ links: [[0, 1, 12]], ghost: [[1, 2]] });
            const mid = (a, b) => [(grid.cx(a) + grid.cx(b)) / 2, (grid.cy(a) + grid.cy(b)) / 2];
            const big = { x: 0, y: 0, trains: [900, 0, 0] }, small = { x: 0.2, y: 0, trains: [1, 0, 0] };
            out([M.hitLink(idx, grid, ...mid(0, 1), 10), M.hitLink(idx, grid, ...mid(1, 2), 10)?.kind,
                 M.hitLink(idx, grid, mid(0, 1)[0], 3, 10), M.hitStation([big, small], 0.1, 0, 10, 5) === small,
                 M.hitStation([big, small], 30, 0, 10, 5)]);
        """)
        self.assertEqual(got, [{"kind": "served", "a": 0, "b": 1, "n": 12}, "ghost", None, True, None])


@unittest.skipUnless(NODE, "node is not installed")
class LayersTest(unittest.TestCase):
    INSTALL = """
        setCountry({ country: { id: 'es', lang: 'es', locale: 'es-ES', data: ['transit'] } }, null);
        const I = await import('./web/js/ext/transit/index.js');
        const layers = [];
        const after = { id: 'commuters', group: 'g' };
        const app = { lensById: new Map([['commuters', after]]), w: { grid: { size: 4, R: 5 } }, addLens() {},
                      on() {}, hash: { value: () => null }, state: { lens: null }, registerStaticLayer: (l) => layers.push(l) };
        I.install(app);
        const byId = Object.fromEntries(layers.map((l) => [l.id, l]));
    """

    def test_stations_win_the_hit_over_landmarks(self):
        got = run(self.INSTALL + """
            const { makeLayers } = await import('./web/js/ext/layers/layers.js');
            const model = { net: {}, parks: [], ranges: [], ports: [], airports: [], installations: [], wonders: [], routes: [], w: {}, version: 1 };
            const z = Object.fromEntries(makeLayers(model, {}).map((l) => [l.id, l.z]));
            out({ stations: byId['transit-stations'].z, lines: byId['transit-lines'].z, z });
        """)
        for over in ("hubs", "forts", "wonders", "plates"):
            self.assertGreater(got["stations"], got["z"][over], over)
        self.assertEqual(got["lines"], got["z"]["rail"])  # the lens's track replaces the rail layer it hides

    def test_a_tap_shows_the_tooltip(self):
        got = run(self.INSTALL + """
            const shown = [];
            const click = I.tapShows((it) => `tip ${it}`, (x, y, html) => shown.push([x, y, html]));
            const touch = click('a', { pointerType: 'touch', x: 10, y: 20 }), pen = click('b', { pointerType: 'pen', x: 1, y: 2 });
            const mouse = click('c', { pointerType: 'mouse', x: 0, y: 0 });
            out({ touch, pen, mouse, shown, layers: ['transit-stations', 'transit-lines'].map((id) => typeof byId[id].click) });
        """)
        self.assertEqual(got, {"touch": True, "pen": True, "mouse": False, "shown": [[10, 20, "tip a"], [1, 2, "tip b"]],
                               "layers": ["function", "function"]})


if __name__ == "__main__":
    unittest.main()
