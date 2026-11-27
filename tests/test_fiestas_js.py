"""The fiesta calendar (web/js/ext/fiestas/calendar.js): the fiestas of a month, their order, the hexes they paint and
the ones with no month, on made-up fiestas and on Spain's fiestas.json. Run with node; skipped without it."""

import json
import shutil
import subprocess
import unittest

from pipeline.core.paths import ROOT

NODE = shutil.which("node")

PRELUDE = """
import { readFileSync } from 'node:fs';
const C = await import('./web/js/ext/fiestas/calendar.js');
const spain = JSON.parse(readFileSync('sites/es/data/fiestas.json', 'utf8')).fiestas;
const out = (x) => console.log(JSON.stringify(x));
const fiesta = (name, category, months, cells = [], place = null, community = 'Aragón') =>
  ({ name, category, months, cells, place, community, when: months.length ? 'una fecha' : null });
"""


def run(body: str):
    res = subprocess.run([NODE, "--input-type=module", "-e", PRELUDE + body], cwd=ROOT, capture_output=True, text=True)
    if res.returncode:
        raise AssertionError(res.stderr)
    return json.loads(res.stdout)


@unittest.skipUnless(NODE, "node is not installed")
class MonthTest(unittest.TestCase):
    def test_month_from_the_local_date_and_from_the_url(self):
        got = run("out([C.currentMonth(new Date(2026, 7, 31, 23, 59)), C.currentMonth(new Date(2027, 0, 1, 0, 0)), "
                  "['8', '12', '1', '0', '13', '8.5', 'agosto', '', null, ' 8', '08'].map(C.parseMonth)]);")
        self.assertEqual(got, [8, 1, [8, 12, 1, None, None, None, None, None, None, None, None]])

    def test_a_fiesta_is_in_every_month_its_source_names_and_undated_ones_in_none(self):
        got = run("""
            const list = [fiesta('A', 'autonomica', [8]), fiesta('B', 'nacional', [7, 8, 9]), fiesta('C', 'internacional', []),
                          fiesta('D', 'autonomica', [12])];
            out({ aug: C.monthFiestas(list, 8, 'es').map((f) => f.name), jan: C.monthFiestas(list, 1, 'es').length,
                  per: C.perMonth(list), undated: C.undated(list) });
        """)
        self.assertEqual(got, {"aug": ["B", "A"], "jan": 0, "per": [0, 0, 0, 0, 0, 0, 1, 2, 1, 0, 0, 1], "undated": 1})

    def test_order_is_category_then_name_as_the_language_sorts_it(self):
        got = run("""
            const list = [fiesta('Zurracapote', 'autonomica', [8]), fiesta('ÁNIMAS', 'autonomica', [8]),
                          fiesta('«El Cipotegato»', 'nacional', [8]), fiesta('Romería', 'internacional', [8]),
                          fiesta('Ñora', 'autonomica', [8]), fiesta('nabo', 'autonomica', [8]),
                          fiesta('San Roque', 'autonomica', [8], [], 'Teruel'), fiesta('San Roque', 'autonomica', [8], [], 'Calatayud'),
                          fiesta('Batalla', 'autonomica', [8])];
            out(C.monthFiestas(list, 8, 'es').map((f) => f.place ? `${f.name} (${f.place})` : f.name));
        """)
        self.assertEqual(got, ["Romería", "«El Cipotegato»", "ÁNIMAS", "Batalla", "nabo", "Ñora", "San Roque (Calatayud)",
                               "San Roque (Teruel)", "Zurracapote"])

    def test_a_hex_takes_its_highest_fiesta_and_lists_them_all(self):
        got = run("""
            const list = C.monthFiestas([fiesta('Regional', 'autonomica', [8], [1, 2]), fiesta('Estatal', 'nacional', [8], [2]),
                                         fiesta('Sin lugar', 'internacional', [8], [])], 8, 'es');
            const layer = C.monthLayer(list, 4, (f) => `${f.name}!`);
            out(layer);
        """)
        # Order: Sin lugar (internacional, no hex), Estatal (nacional), Regional (autonómica).
        self.assertEqual(got, {"values": [None, 2, 1, None], "labels": [None, [2], [1, 2], None],
                               "names": ["Sin lugar!", "Estatal!", "Regional!"]})


@unittest.skipUnless(NODE, "node is not installed")
class SpainCalendarTest(unittest.TestCase):
    def test_every_fiesta_of_spain_is_in_its_months_or_counted_as_undated(self):
        got = run("""
            const months = Array.from({ length: 12 }, (_, k) => C.monthFiestas(spain, k + 1, 'es'));
            const per = C.perMonth(spain);
            out({ n: spain.length, undated: C.undated(spain), dated: spain.filter((f) => f.months.length).length,
                  same: months.every((l, k) => l.length === per[k]),
                  covered: spain.every((f) => !f.months.length || f.months.every((m) => months[m - 1].includes(f))),
                  categories: [...new Set(spain.map((f) => f.category))].every((c) => C.CATEGORIES.includes(c)),
                  ordered: months.every((l) => l.every((f, k) => !k || C.CATEGORIES.indexOf(l[k - 1].category) <= C.CATEGORIES.indexOf(f.category))),
                  august: [...new Set(months[7].map((f) => f.category))] });
        """)
        self.assertEqual(got["undated"] + got["dated"], got["n"])
        self.assertGreater(got["undated"], 0)
        self.assertTrue(got["same"] and got["covered"] and got["categories"] and got["ordered"])
        # The State's fiestas carry the dates of their community's entry: August has fiestas of every category.
        self.assertEqual(got["august"], ["internacional", "nacional", "autonomica"])

    def test_the_month_layer_puts_each_fiesta_on_its_hexes(self):
        got = run("""
            const list = C.monthFiestas(spain, 8, 'es');
            const n = 1 + Math.max(...spain.flatMap((f) => f.cells));
            const layer = C.monthLayer(list, n, (f) => f.name);
            const onHexes = list.every((f, k) => f.cells.every((c) => layer.labels[c].includes(k)));
            const painted = layer.values.filter((v) => v != null).length;
            const cells = new Set(list.flatMap((f) => f.cells)).size;
            out({ onHexes, same: painted === cells, names: layer.names.length === list.length });
        """)
        self.assertEqual(got, {"onHexes": True, "same": True, "names": True})


if __name__ == "__main__":
    unittest.main()
