"""web/js/ui/lenses.js helpers that the people lenses rely on, and the icon or emoji every lens needs in the quick row
(run with node; skipped without it)."""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from test_lens_panel_js import PRELUDE, SPAIN, run as run_panel

ROOT = Path(__file__).resolve().parents[1]
LENSES_JS = ROOT / "web" / "js" / "ui" / "lenses.js"
ICONS_JS = ROOT / "web" / "js" / "icons.js"
NODE = shutil.which("node")


@unittest.skipUnless(NODE, "node is not installed")
class LensesJsTest(unittest.TestCase):
    def run_js(self, body: str):
        script = (f"Promise.all([import({json.dumps(LENSES_JS.as_uri())}), import({json.dumps(ICONS_JS.as_uri())})])"
                  f".then(([m, I]) => {{ console.log(JSON.stringify({body})); }});")
        out = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
        return json.loads(out.stdout)

    def test_names_from_lists_each_hexs_people_in_file_order(self):
        doc = {"people": [{"name": "Pablo Picasso", "note": "pintor, 1881–1973", "cell": 2},
                          {"name": "Antonio Banderas", "note": "actor, n. 1960", "cell": 2},
                          {"name": "Sin nota", "cell": 0}]}
        got = self.run_js(f"m.namesFrom({json.dumps(doc)}, 4)")
        self.assertEqual(got["names"], ["Pablo Picasso (pintor, 1881–1973)", "Antonio Banderas (actor, n. 1960)",
                                        "Sin nota"])
        self.assertEqual(got["labels"], [[2], None, [0, 1], None])

    def test_a_lens_can_name_its_empty_hexes(self):
        got = self.run_js("[m.formatLensValue({format: 'category', null_label: 'Nadie'}, null), "
                          "m.formatLensValue({format: 'category', categories: [{name: 'A'}]}, 0)]")
        self.assertEqual(got, ["Nadie", "A"])

    def test_a_lens_with_decimals_writes_them_all_and_the_default_does_not(self):
        # The climate lenses ask for one decimal ("23,0 °C" next to "23,1 °C"); without `decimals` nothing changes.
        got = self.run_js("[1, 0].map((d) => [23, 23.1, 6].map((v) => m.formatLensValue({format: 'float', unit: '°C', decimals: d}, v)))"
                          ".concat([[23, 6].map((v) => m.formatLensValue({format: 'float', unit: '°C'}, v))])")
        self.assertEqual(got, [["23.0 °C", "23.1 °C", "6.0 °C"], ["23 °C", "23 °C", "6 °C"], ["23 °C", "6.0 °C"]])

    def test_time_lenses_show_clock_times_and_durations(self):
        # A browser-built lens holds minutes (the sun lens): times of day on the legend's ticks, durations in hours.
        clock, dur = "{format: 'clock', domain: [1255, 1340]}", "{format: 'duration', domain: [534, 927]}"
        got = self.run_js(f"[m.formatLensValue({clock}, 1321), m.formatLensTick({clock}, 0, 0), m.formatLensTick({clock}, 1, 4), "
                          f"m.formatLensValue({dur}, 927), m.formatLensValue({dur}, 54), m.formatLensValue({dur}, 60), "
                          f"m.isTimeLens({clock}), m.isTimeLens({dur}), m.isTimeLens({{format: 'int'}})]")
        self.assertEqual(got, ["22:01", "≤ 20:55", "≥ 22:20", "15 h 27 min", "54 min", "1 h", True, True, False])

    def test_a_bounded_share_reads_in_whole_percent_and_says_of_what(self):
        # The wildlife lenses (spain_fauna.py): a share from 0 to 1 on its natural range. The tooltip value carries the
        # unit and no false decimals; the legend's ticks drop the unit and the ≤/≥ marks of a clamped scale.
        fauna = "{format: 'pct', domain: [0, 1], bounded: true, decimals: 0, unit_in_value: true, unit: 'of the hex'}"
        plain = "{format: 'pct', domain: [0, 1]}"
        got = self.run_js(f"[m.formatLensValue({fauna}, 1), m.formatLensValue({fauna}, 0.07), "
                          f"m.formatLensTick({fauna}, 0, 0), m.formatLensTick({fauna}, 1, 4), "
                          f"m.formatLensValue({plain}, 0.07), m.formatLensTick({plain}, 1, 4)]")
        self.assertEqual(got, ["100% of the hex", "7% of the hex", "0%", "100%", "7.0%", "≥ 100%"])

    def test_a_lens_built_in_the_browser_never_takes_the_lens_files_vintage(self):
        # The file's lenses with a source sources.json lacks show the file's vintage; a lens added later (app.addLens
        # splices it into the same list) shows only its source, dated or not.
        got = self.run_js("""(() => {
          const file = {vintage: 'INE Padrón, 1 January 2025', lenses: [{id: 'a', source: 'ine'}, {id: 'b', source: 'dated'}]};
          const sources = [{id: 'noaa_solar', title: 'NOAA Solar Calculator', vintage: null},
                           {id: 'dated', title: 'Dated', vintage: '2024'}];
          const line = m.lensSourceLine(file, sources);
          const sun = {id: 'sun', source: 'noaa_solar'}, loose = {id: 'x', source: 'free text'};
          file.lenses.push(sun, loose);
          return [line(file.lenses[0]), line(file.lenses[1]), line(sun), line(loose)];
        })()""")
        self.assertEqual(got, ["ine · INE Padrón, 1 January 2025", "Dated · 2024", "NOAA Solar Calculator", "free text"])

    def test_years_take_decimals_and_a_long_unit_leaves_the_ticks_bare(self):
        # Spain's life expectancy at 65 ("años más a los 65") prints its unit on its own line, so "20,0 años21,0 años"
        # never overprints; the US age lens ("years") keeps its ticks as they were.
        life = "{format: 'years', unit: 'more years at 65', domain: [20, 24], decimals: 1}"
        age = "{format: 'years', unit: 'years', domain: [31, 54]}"
        got = self.run_js(f"[m.formatLensValue({life}, 22.2), m.formatLensValue({{format: 'years', decimals: 2}}, 22.16), "
                          f"m.formatLensTick({life}, 0, 0), m.formatLensTick({life}, 0.25, 1), m.formatLensTick({life}, 1, 4), "
                          f"m.formatLensTick({age}, 0, 0), m.formatLensValue({age}, 38.44)]")
        self.assertEqual(got, ["22.2 yrs", "22.16 yrs", "≤ 20.0", "21.0", "≥ 24.0", "≤ 31.0 yrs", "38.4 yrs"])

    def test_a_lens_with_also_sources_names_each(self):
        got = self.run_js("""(() => {
          const sources = [{id: 'census', title: 'Census', vintage: '2026'}, {id: 'life', title: 'Life', vintage: '2024'}];
          const line = m.lensSourceLine({lenses: []}, sources);
          return [line({source: 'census', also_sources: ['life']}), line({source: 'census'})];
        })()""")
        self.assertEqual(got, ["Census · 2026 + Life · 2024", "Census · 2026"])

    # The quick row shows only icons when it would not fit (ui/lenses.js fitQuick): a lens without an SVG icon or an
    # emoji would be an empty chip.
    def test_every_us_lens_has_an_svg_icon(self):
        # So the US quick row never holds an emoji. Spain's lenses are checked in the browser below.
        lenses = [{"id": l["id"], "icon": l.get("icon")} for l in json.loads((ROOT / "web/data/lenses.json").read_text())["lenses"]]
        got = self.run_js(f"{json.dumps(lenses)}.filter((l) => !I.hasIcon(l.icon)).map((l) => l.id)")
        self.assertEqual(got, [])

    def test_every_spanish_lens_has_an_icon_or_an_emoji(self):
        # Every lens of Spain, from the file or built in the browser by an extension.
        got = run_panel("""
            setCountry({ country: { ...world.country, lang: 'es', locale: 'es-ES', sunset: true,
                                    data: ['fiestas', 'clima', 'embalses', 'transit', 'personajes'] } }, null);
            const { glyph } = await import('./web/js/ui/icon.js');
            const app = spainApp('');
            Object.assign(app, { registerOverlay: () => () => {}, requestDraw() {}, invalidate() {}, cam: { scale: 1 } });
            for (const x of ['fiestas', 'sun', 'clima', 'embalses', 'transit', 'timeline']) (await import(`./web/js/ext/${x}/index.js`)).install(app);
            await tick();
            out([...app.lensById.values()].map((l) => { const g = glyph(l, 15);
              return [l.id, /<svg[^>]*>[\s\S]*<path/.test(g) || /class="emoji"[^>]*>(?!•<)[^<]+</.test(g)]; }));
        """, PRELUDE + SPAIN)
        ids = [i for i, _ in got]
        for lens in ("density", "lynx", "fiestas_mes", "atardecer", "clima_temp", "clima_lluvia", "clima_heladas", "clima_sol",
                     "embalses", "rail_madrid", "great_people_year", "great_people_year_kind"):
            self.assertIn(lens, ids)
        self.assertEqual([i for i, ok in got if not ok], [])

    def test_category_helpers_match_the_legend_rule(self):
        got = self.run_js("""(() => {
          const cats = [{name: 'A', color: '#111'}, {name: 'B'}, {name: 'C'}];
          const lens = {categories: cats, ramp: ['#a00', '#0b0'], values: [0, 1, 1, null, 2, 0.6]};
          const counts = m.categoryCounts(lens, [0, 0, -1, 0, -1, 3]);
          return {counts, all: m.shownCategories(lens, counts), hidden: m.shownCategories({...lens, hide_empty: true}, counts),
                  colors: [0, 1, 2].map((k) => m.categoryColor(lens, k))};
        })()""")
        # owner < 0 (sea) and null are not counted; 0.6 rounds to 1
        self.assertEqual(got["counts"], [1, 2, 0])
        self.assertEqual(got["all"], [0, 1, 2])
        self.assertEqual(got["hidden"], [0, 1])
        self.assertEqual(got["colors"], ["#111", "#0b0", "#888"])

    def test_a_quick_chip_without_an_svg_has_its_emoji_and_its_name_in_the_title(self):
        # When the row would not fit only the glyph shows (style.css .icons): the chip keeps the emoji glyph() writes
        # and a title, from which the browser names an icon-only button.
        script = """
          import { readFileSync } from 'node:fs';
          const el = () => ({ innerHTML: '', hidden: false, title: '', classList: { add() {}, remove() {}, toggle() {} },
            setAttribute() {}, addEventListener() {}, querySelector: () => null, querySelectorAll: () => [] });
          const els = {};
          Object.defineProperty(globalThis, 'localStorage', { value: { getItem: () => '["lynx","density"]', setItem() {} }, configurable: true });
          globalThis.window = { addEventListener() {} };
          globalThis.document = { getElementById: (id) => (els[id] ||= el()), addEventListener() {}, contains: () => false };
          const world = JSON.parse(readFileSync('sites/es/data/world.json', 'utf8'));
          (await import('./web/js/app/country.js')).setCountry({ country: { ...world.country, lang: 'es', locale: 'es-ES' } }, null);
          const { initLensDock } = await import('./web/js/ui/lenses.js');
          initLensDock({ lenses: JSON.parse(readFileSync('sites/es/data/lenses.json', 'utf8')), onPick() {}, onBand() {} }).render(null);
          console.log(JSON.stringify([...els['lens-quick'].innerHTML.matchAll(/<button[^>]*data-id="([^"]*)"[^>]*title="([^"]*)">([\\s\\S]*?)<\\/button>/g)]
            .map(([, id, title, body]) => [id, title, /<svg/.test(body), /<span class="emoji"[^>]*>([^<]*)</.exec(body)?.[1] ?? null])));
        """
        out = subprocess.run([NODE, "--input-type=module", "-e", script], cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(out.stdout), [["", "Terreno (sin lente)", True, None],
                                                  ["lynx", "Lente Lince ibérico", False, "🐈"],
                                                  ["density", "Lente Población", True, None],
                                                  ["income", "Lente Renta", True, None]])
