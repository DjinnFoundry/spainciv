"""The climate of the month in the browser: each hex's value and its origin for a variable and a month
(web/js/ext/clima/season.js), on a made-up clima.json and on Spain's, and the Walter-Lieth diagram
(web/js/ext/clima/walter.js). Run with node; skipped without it."""

import json
import shutil
import subprocess
import unittest

from pipeline.core.paths import ROOT

NODE = shutil.which("node")

PRELUDE = """
import { readFileSync } from 'node:fs';
const S = await import('./web/js/ext/clima/season.js');
const WL = await import('./web/js/ext/clima/walter.js');
const out = (x) => console.log(JSON.stringify(x));
const months = (f) => Array.from({ length: 12 }, (_, k) => f(k + 1));

// Six hexes: 0 sea; 1 and 2 grid hexes of province 09 (2 holds a station with sunshine); 3 a land hex of 09 without
// grid; 4 a hex of province 52 without grid holding a station without sunshine; 5 a grid hex of 35 (the Canaries).
const fake = {
  cells: [1, 2, 5], points: [2, 1, 0],
  grid: {
    tmax: months((m) => [10 + m, 8 + m, 20 + m]), tmin: months((m) => [m - 4, m - 6, m === 3 ? null : 15]),
    prec: months((m) => [40, 60, 0.5]), frost: months((m) => [m < 3 ? 12 : 0, m < 3 ? 18 : 0, 0]),
  },
  provinces: { '09': { tmed: months((m) => 2 + m), tmax: months((m) => 8 + m), tmin: months((m) => m - 4), prec: months(() => 55) },
               '52': { tmed: months(() => 17), tmax: months(() => 21), tmin: months(() => 13), prec: months(() => 30) },
               '35': { tmed: months(() => 20), tmax: months(() => 24), tmin: months(() => 16), prec: months(() => 10) } },
  peninsular: { tmed: months((m) => 5 + m), prec: months((m) => 80 - m) },
  stations: [
    { name: 'Burgos Aeropuerto', alt: 891, lon: -3.63, lat: 42.36, cell: 2, tmed: months((m) => 3 + m), tmax: months(() => 0), tmin: months(() => 0),
      prec: months(() => 50), frost: months((m) => (m < 3 ? 16.6 : 0)), sun: months((m) => 100 + m) },
    { name: 'Melilla', alt: 47, lon: -2.95, lat: 35.28, cell: 4, tmed: months(() => 18), tmax: months(() => 0), tmin: months(() => 0),
      prec: months(() => 25), frost: months(() => 0), sun: null },
    { name: 'Lanzarote Aeropuerto', alt: 14, lon: -13.6, lat: 28.95, cell: 5, tmed: months(() => 21), tmax: months(() => 0), tmin: months(() => 0),
      prec: months(() => 5), frost: months(() => 0), sun: months(() => 250) },
  ],
  domains: { temp: [0, 30], prec: [2, 150], frost: [0, 20], sun: [90, 300] },
};
const PROVINCE = [null, '09', '09', '09', '52', '35'];
const LONLAT = [[0, 0], [-3.7, 42.3], [-3.6, 42.4], [-3.0, 42.0], [-2.95, 35.29], [-13.6, 28.9]];
const model = S.climateModel(fake, { n: 6, province: (i) => PROVINCE[i], lonlat: (i) => LONLAT[i] });
"""

SPAIN = """
const doc = JSON.parse(readFileSync('sites/es/data/clima.json', 'utf8'));
const world = JSON.parse(readFileSync('sites/es/data/world.json', 'utf8'));
const { mapProjection } = await import('./web/js/geo.js');
const { makeGrid } = await import('./web/js/hex.js');
const proj = mapProjection(world.country.projection);
const grid = makeGrid(world.grid);
const n = world.owner.length;
const fips = world.states.map((s) => s.fips);
const spain = S.climateModel(doc, { n, province: (i) => (world.owner[i] >= 0 ? fips[world.owner[i]] : null),
                                    lonlat: (i) => proj.inverse(grid.cx(i), grid.cy(i)) });
const land = world.owner.filter((o) => o >= 0).length;
"""


def run(body: str, prelude: str = PRELUDE):
    res = subprocess.run([NODE, "--input-type=module", "-e", prelude + body], cwd=ROOT, capture_output=True, text=True)
    if res.returncode:
        raise AssertionError(res.stderr)
    return json.loads(res.stdout)


@unittest.skipUnless(NODE, "node is not installed")
class SeasonTest(unittest.TestCase):
    def test_temperature_is_the_mean_of_max_and_min_and_the_province_fills_a_hex_without_grid(self):
        got = run("""
            const jan = S.layer(model, 'temp', 1), mar = S.layer(model, 'temp', 3);
            out({ jan: jan.values, mar: mar.values, f1: jan.facts(1), f3: jan.facts(3), f5mar: mar.facts(5), sea: jan.facts(0) });
        """)
        self.assertEqual(got["jan"], [None, 4, 2, 3, 17, 18])  # (11 + -3) / 2, (9 + -5) / 2, 09's tmed, 52's, (21 + 15) / 2
        # A month with a missing minimum on the grid takes the province's normal, and says so.
        self.assertEqual(got["mar"][5], 20)
        self.assertEqual(got["f5mar"]["source"], "province")
        self.assertEqual((got["f5mar"]["max"], got["f5mar"]["min"]), (24, 16))
        self.assertEqual(got["f1"], {"source": "grid", "max": 11, "min": -3, "stations": [], "nearest": None})
        self.assertEqual((got["f3"]["source"], got["f3"]["max"], got["f3"]["min"]), ("province", 9, -3))
        self.assertIsNone(got["sea"])

    def test_rain_and_frost_come_from_the_grid_and_frost_has_no_province_figure(self):
        got = run("""
            const p = S.layer(model, 'prec', 7), f = S.layer(model, 'frost', 1), f8 = S.layer(model, 'frost', 8);
            out({ prec: p.values, frost: f.values, aug: f8.values, src: [p.facts(3).source, f.facts(3).source] });
        """)
        self.assertEqual(got["prec"], [None, 40, 60, 55, 30, 0.5])
        self.assertEqual(got["frost"], [None, 12, 18, None, None, 0])
        self.assertEqual(got["aug"], [None, 0, 0, None, None, 0])  # 0 is a value, not a gap
        self.assertEqual(got["src"], ["province", None])

    def test_stations_on_a_hex_give_their_own_normal_for_the_variable(self):
        got = run("""
            out([S.layer(model, 'temp', 1).facts(2).stations, S.layer(model, 'frost', 1).facts(2).stations,
                 S.layer(model, 'sun', 1).facts(4).stations]);
        """)
        self.assertEqual(got, [[{"name": "Burgos Aeropuerto", "alt": 891, "value": 4}],
                               [{"name": "Burgos Aeropuerto", "alt": 891, "value": 16.6}],
                               [{"name": "Melilla", "alt": 47, "value": None}]])

    def test_sunshine_only_on_station_hexes_and_the_rest_name_the_nearest_station(self):
        got = run("""
            const L = S.layer(model, 'sun', 6);
            out({ values: L.values, f1: L.facts(1).nearest, f4: L.facts(4).nearest, f5: L.facts(5).nearest,
                  f2: L.facts(2).nearest });
        """)
        self.assertEqual(got["values"], [None, None, 106, None, None, 250])
        self.assertEqual(got["f1"], {"name": "Burgos Aeropuerto", "value": 106, "annual": sum(100 + m for m in range(1, 13))})
        self.assertEqual(got["f4"]["name"], "Burgos Aeropuerto")  # Melilla's station has no sunshine
        self.assertIsNone(got["f5"])
        self.assertIsNone(got["f2"])

    def test_the_domain_is_the_same_every_month_and_the_strip_has_bars_only_for_temperature_and_rain(self):
        got = run("""
            out({ domains: S.VARIABLES.map((v) => months((m) => S.layer(model, v, m).domain)),
                  bars: S.VARIABLES.map((v) => S.stripBars(fake, v)) });
        """)
        for v, per in zip(["temp", "prec", "frost", "sun"], got["domains"]):
            self.assertEqual(len({tuple(d) for d in per}), 1, v)
        temp, prec, frost, sun = got["bars"]
        self.assertEqual(temp[-1], 1)
        self.assertAlmostEqual(temp[0], 6 / 17)
        self.assertEqual(prec[0], 1)
        self.assertIsNone(frost)
        self.assertIsNone(sun)

    def test_the_tooltip_lines_say_where_the_value_comes_from(self):
        got = run("""
            const say = (k, p = {}) => k + JSON.stringify(p);
            const value = { temp: (x) => x.toFixed(1), int: String, lens: (x) => `${x} u` };
            out({ temp: S.tipLines(S.layer(model, 'temp', 1).facts(2), { say, value }),
                  frost: S.tipLines(S.layer(model, 'frost', 1).facts(2), { say, value, frost: true }),
                  noSun: S.tipLines(S.layer(model, 'sun', 6).facts(4), { say, value, month: 'junio' }),
                  near: S.tipLines(S.layer(model, 'sun', 6).facts(1), { say, value, month: 'junio' }),
                  sea: S.tipLines(null, { say, value }) });
        """)
        self.assertEqual(got["temp"], ['clima.tip.range{"max":"9.0","min":"-5.0"} · clima.tip.grid{}',
                                       'clima.tip.station{"name":"Burgos Aeropuerto","alt":"891","value":"4 u"}'])
        self.assertEqual(got["frost"], ["clima.tip.grid{}",
                                        'clima.tip.station.frost{"name":"Burgos Aeropuerto","alt":"891","value":"16.6 u"}'])
        self.assertEqual(got["noSun"][-2], 'clima.tip.station.none{"name":"Melilla","alt":"47","value":""}')
        self.assertEqual(got["noSun"][-1], 'clima.tip.nearest{"name":"Burgos Aeropuerto","value":"106 u","month":"junio","hours":"1278"}')
        self.assertEqual(got["near"], ['clima.tip.nearest{"name":"Burgos Aeropuerto","value":"106 u","month":"junio","hours":"1278"}'])
        self.assertEqual(got["sea"], [])

    def test_the_stations_with_the_most_and_least_frost_and_sunshine(self):
        got = run("out([S.stationExtremes(fake, 'sun', 6), S.stationExtremes(fake, 'frost', 1), "
                  "S.stationExtremes(fake, 'frost', 7), S.stationExtremes(fake, 'temp', 1)]);")
        self.assertEqual(got[0], {"top": {"name": "Lanzarote Aeropuerto", "value": 250},
                                  "bottom": {"name": "Burgos Aeropuerto", "value": 106}})
        self.assertEqual(got[1]["top"], {"name": "Burgos Aeropuerto", "value": 16.6})
        self.assertIsNone(got[2])  # no station has frost in July
        self.assertIsNone(got[3])

    def test_an_unknown_variable_fails(self):
        with self.assertRaises(AssertionError):
            run("S.layer(model, 'wind', 1);")


@unittest.skipUnless(NODE, "node is not installed")
class SpainSeasonTest(unittest.TestCase):
    def test_every_land_hex_has_a_temperature_and_rain_and_sunshine_only_at_stations(self):
        got = run("""
            const t1 = S.layer(spain, 'temp', 1), p7 = S.layer(spain, 'prec', 7), s1 = S.layer(spain, 'sun', 1);
            const f1 = S.layer(spain, 'frost', 1);
            const count = (vs) => vs.filter((v) => v != null).length;
            const sunCells = new Set(doc.stations.filter((s) => s.sun).map((s) => s.cell));
            const burgos = doc.stations.find((s) => s.wmo === '08075');
            const melilla = doc.stations.find((s) => s.name === 'Melilla');
            const noSun = s1.values.findIndex((v, i) => v == null && world.owner[i] >= 0);
            out({ land, temp: count(t1.values), prec: count(p7.values), frost: count(f1.values), sun: count(s1.values),
                  sunCells: sunCells.size, onlyStations: s1.values.every((v, i) => v == null || sunCells.has(i)),
                  burgos: S.layer(spain, 'temp', 1).facts(burgos.cell).stations.find((s) => s.name === burgos.name),
                  burgosTmed: burgos.tmed[0], melilla: t1.facts(melilla.cell).source,
                  nearest: s1.facts(noSun).nearest, sorted: Object.keys(doc.domains).sort() });
        """, PRELUDE + SPAIN)
        self.assertEqual(got["temp"], got["land"])
        self.assertEqual(got["prec"], got["land"])
        self.assertGreater(got["frost"], got["land"] - 5)
        self.assertEqual(got["sun"], got["sunCells"])
        self.assertTrue(got["onlyStations"])
        self.assertEqual(got["burgos"]["value"], got["burgosTmed"])
        self.assertEqual(got["melilla"], "grid")  # ROCIO has a point in Melilla
        self.assertIsNotNone(got["nearest"]["name"])
        self.assertGreater(got["nearest"]["annual"], 1500)


@unittest.skipUnless(NODE, "node is not installed")
class WalterLiethTest(unittest.TestCase):
    def test_the_scale_is_10_degrees_to_20_mm_and_a_tenth_above_100_mm(self):
        got = run("out([WL.scaleP(40), WL.scaleP(100), WL.scaleP(150), WL.scaleP(300), WL.mmAt(20), WL.mmAt(60)]);")
        self.assertEqual(got, [20, 50, 52.5, 60, 40, 300])

    def test_dry_and_humid_months_and_the_frost_bar(self):
        got = run("""
            const tmed = [3, 4, 7, 9, 13, 17, 20, 20, 17, 12, 7, 4], prec = [60, 45, 40, 60, 60, 30, 20, 18, 30, 60, 70, 150];
            out({ seasons: WL.seasons(tmed, prec), frost: WL.frostMonths([-1.2, -0.4, 0, 2, 5, 8, 10, 10, 8, 5, 1, -0.1]),
                  g: WL.geometry(tmed, prec) });
        """)
        self.assertEqual(got["seasons"], ["humid"] * 5 + ["dry", "dry", "dry", "dry"] + ["humid"] * 3)
        self.assertEqual(got["frost"], [True, True, False, False, False, False, False, False, False, False, False, True])
        self.assertEqual(len(got["g"]["temp"]), 12)
        self.assertEqual(got["g"]["prec"][11], 52.5)  # 150 mm on the compressed scale
        self.assertEqual((got["g"]["lo"], got["g"]["hi"]), (0, 60))

    def test_the_svg_has_both_lines_the_kinds_of_month_and_its_header(self):
        got = run("""
            const tmed = [-2, 0, 4, 8, 12, 17, 22, 22, 17, 10, 4, -1], prec = [30, 30, 40, 50, 60, 40, 10, 15, 40, 60, 160, 40];
            const svg = WL.walterSvg({ tmed, prec, tmin: tmed.map((t) => t - 5), place: 'Burgos & <Soria>', period: '1991-2020',
              months: 'EFMAMJJASOND'.split(''), num: (v, d) => v.toFixed(d).replace('.', ',') });
            const pts = [...svg.matchAll(/<polyline points="([^"]+)"/g)].map((m) => m[1].split(' ').length);
            out({ pts, humid: svg.includes('url(#wl-humid)'), dry: svg.includes('url(#wl-dry)'), solid: svg.includes('#2f62a8"/>'),
                  frost: (svg.match(/<rect /g) || []).length, header: svg.includes('Burgos &amp; &lt;Soria&gt;'),
                  annual: svg.includes('9,4 °C') && svg.includes('575 mm'), months: (svg.match(/text-anchor="middle"/g) || []).length });
        """)
        self.assertEqual(got["pts"], [12, 12])
        self.assertTrue(got["humid"] and got["dry"] and got["solid"] and got["header"] and got["annual"])
        self.assertEqual(got["frost"], 5)  # the months whose minimum (here tmed - 5) is below 0 °C
        self.assertEqual(got["months"], 12)

    def test_burgos_and_cordoba_from_aemets_province_normals(self):
        got = run("""
            const doc = JSON.parse(readFileSync('sites/es/data/clima.json', 'utf8'));
            out(['09', '14'].map((c) => WL.seasons(doc.provinces[c].tmed, doc.provinces[c].prec)));
        """)
        burgos, cordoba = got
        self.assertIn("dry", burgos)  # Burgos has a dry summer
        self.assertEqual(cordoba[6], "dry")  # Córdoba in July
        self.assertEqual(cordoba[0], "humid")


if __name__ == "__main__":
    unittest.main()
