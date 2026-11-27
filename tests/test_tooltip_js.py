"""The hex tooltip (web/js/ui/tooltip.js) on a stub document and a two-hex world: a lens's own lines (lens.tip(i), a
string or a list) and the click hint a lens can put in place of "Click to open <province>". Run with node; skipped
without it."""

import json
import shutil
import subprocess
import unittest

from pipeline.core.paths import ROOT

NODE = shutil.which("node")

PRELUDE = """
const box = { innerHTML: '', hidden: true, style: {}, getBoundingClientRect: () => ({ width: 100, height: 40 }) };
globalThis.document = { getElementById: () => box };
globalThis.window = { innerWidth: 1200, innerHeight: 800 };
const { setCountry } = await import('./web/js/app/country.js');
setCountry({ country: { id: 'es', lang: 'es', locale: 'es-ES' } }, null);
const { showCellTooltip } = await import('./web/js/ui/tooltip.js');
const out = (x) => console.log(JSON.stringify(x));
const w = {
  raw: { elev: [12, 640], owner: [-1, 0], county: [-1, 0], counties: [{ name: 'Burgos' }], states: [{ name: 'Burgos' }] },
  cityByCell: new Map(), water: [0, 0], cover: [0, 0], relief: [0, 0], tables: { cover: [], relief: [], water: [] },
  resources: null,
};
const lens = (extra) => ({ id: 'x', name: 'Lluvia', format: 'float', unit: 'mm', values: [null, 47.2], ...extra });
const lines = (l) => { showCellTooltip(0, 0, w, 1, l, false); return box.innerHTML.split('<br>'); };
"""


def run(body: str):
    res = subprocess.run([NODE, "--input-type=module", "-e", PRELUDE + body], cwd=ROOT, capture_output=True, text=True)
    if res.returncode:
        raise AssertionError(res.stderr)
    return json.loads(res.stdout)


@unittest.skipUnless(NODE, "node is not installed")
class CellTooltipTest(unittest.TestCase):
    def test_a_lens_tip_may_be_one_line_or_several_and_is_escaped(self):
        got = run("""
            out([lines(lens({ tip: () => 'rejilla ROCIO' })), lines(lens({ tip: () => ['a <b>', null, 'c'] })),
                 lines(lens({ tip: () => null }))]);
        """)
        one, many, none = got
        self.assertIn('<span class="muted">rejilla ROCIO</span>', one)
        self.assertIn('<span class="muted">a &lt;b&gt;</span>', many)
        self.assertIn('<span class="muted">c</span>', many)
        self.assertEqual(len(many), len(one) + 1)  # the empty line is left out
        self.assertEqual(len(none), len(one) - 1)

    def test_a_lens_click_hint_replaces_the_open_province_line(self):
        got = run("out([lines(lens({})).at(-1), lines(lens({ click_hint: 'Haz clic para fijar <su> diagrama' })).at(-1)]);")
        self.assertIn("Burgos", got[0])
        self.assertEqual(got[1], '<span class="muted">Haz clic para fijar &lt;su&gt; diagrama</span>')


if __name__ == "__main__":
    unittest.main()
