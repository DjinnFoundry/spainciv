"""web/js/ui/lenses.js helpers that the people lenses rely on (run with node; skipped without it)."""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

LENSES_JS = Path(__file__).resolve().parents[1] / "web" / "js" / "ui" / "lenses.js"
NODE = shutil.which("node")


@unittest.skipUnless(NODE, "node is not installed")
class LensesJsTest(unittest.TestCase):
    def run_js(self, body: str):
        script = f"import({json.dumps(LENSES_JS.as_uri())}).then((m) => {{ console.log(JSON.stringify({body})); }});"
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

    def test_time_lenses_show_clock_times_and_durations(self):
        # A browser-built lens holds minutes (the sunset lens): times of day on the legend's ticks, durations in hours.
        clock, dur = "{format: 'clock', domain: [1255, 1340]}", "{format: 'duration', domain: [534, 927]}"
        got = self.run_js(f"[m.formatLensValue({clock}, 1321), m.formatLensTick({clock}, 0, 0), m.formatLensTick({clock}, 1, 4), "
                          f"m.formatLensValue({dur}, 927), m.formatLensValue({dur}, 54), m.formatLensValue({dur}, 60), "
                          f"m.isTimeLens({clock}), m.isTimeLens({dur}), m.isTimeLens({{format: 'int'}})]")
        self.assertEqual(got, ["22:01", "≤ 20:55", "≥ 22:20", "15 h 27 min", "54 min", "1 h", True, True, False])
