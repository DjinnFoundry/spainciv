"""The trade-route geometry of web/js/render/art/improvements.js (prepareRoutes, routeSize), with node; skipped without
it. Spain's routes (trade.json in tonnes, no `path`) are straight lines; the US routes keep their arcs and order."""

import json
import shutil
import subprocess
import unittest

from pipeline.core.paths import ROOT

NODE = shutil.which("node")
SPAIN = ROOT / "sites" / "es" / "data"


def run(body: str):
    """`body` (an expression) with `m` = improvements.js and `grid` = a hex grid, under a stub Path2D."""
    script = f"""
        globalThis.Path2D = class {{ moveTo() {{}} lineTo() {{}} quadraticCurveTo() {{}} }};
        const m = await import('./web/js/render/art/improvements.js');
        const {{ makeGrid }} = await import('./web/js/hex.js');
        const grid = makeGrid({{ radius: 10, cols: 20, rows: 20 }});
        console.log(JSON.stringify({body}));
    """
    out = subprocess.run([NODE, "--input-type=module", "-e", script], cwd=ROOT, capture_output=True, text=True)
    if out.returncode:
        raise AssertionError(out.stderr)
    return json.loads(out.stdout)


def zone(zid, cell):
    return {"id": zid, "anchor": {"cell": cell}}


@unittest.skipUnless(NODE, "node is not installed")
class TradeJsTest(unittest.TestCase):
    def test_route_size_follows_the_measure(self):
        r = {"tons_k": 5, "value_musd": 7}
        self.assertEqual(run(f"[m.routeSize({{measure: 'tons'}}, {json.dumps(r)}), m.routeSize({{}}, {json.dumps(r)}), "
                             f"m.routeSize(null, {json.dumps(r)}), m.routeSize({{measure: 'tons'}}, {{}})]"), [5, 7, 7, 0])

    def test_routes_without_a_path_are_straight_and_ordered_by_tonnes(self):
        trade = {"measure": "tons", "zones": [zone("a", 21), zone("b", 300), zone("c", 150)],
                 "routes": [{"a": "a", "b": "c", "tons_k": 10, "rank": 2}, {"a": "a", "b": "b", "tons_k": 40, "rank": 1},
                            {"a": "b", "b": "c", "tons_k": 5, "rank": 3, "value_musd": 999}]}
        got = run(f"m.prepareRoutes({{grid}}, {json.dumps(trade)}).map((r) => [r.route.rank, r.bow, r.top, +r.weight.toFixed(4)])")
        self.assertEqual(got, [[1, 0, True, 1.0], [2, 0, True, 0.5], [3, 0, True, 0.3536]])

    def test_us_routes_keep_their_arcs(self):
        """Paths given, sizes by value: the order and the fanning bows of the US map."""
        trade = {"zones": [zone("a", 21), zone("b", 300), zone("c", 150)],
                 "routes": [{"a": "b", "b": "c", "value_musd": 10, "tons_k": 900, "path": [300, 150]},
                            {"a": "a", "b": "b", "value_musd": 30, "tons_k": 1, "path": [21, 300]},
                            {"a": "a", "b": "c", "value_musd": 20, "tons_k": 1, "path": [21, 150]}]}
        got = run(f"m.prepareRoutes({{grid}}, {json.dumps(trade)}).map((r) => [r.route.value_musd, +r.bow.toFixed(4)])")
        self.assertEqual(got, [[30, 0.12], [20, -0.2], [10, -0.2]])

    @unittest.skipUnless((SPAIN / "trade.json").exists(), "Spain's trade.json is not built")
    def test_spains_file(self):
        trade = json.loads((SPAIN / "trade.json").read_text())
        world = json.loads((SPAIN / "world.json").read_text())["grid"]
        got = run(f"""(() => {{
            const g = makeGrid({json.dumps(world)});
            const rs = m.prepareRoutes({{grid: g}}, {json.dumps(trade)});
            return {{n: rs.length, bows: [...new Set(rs.map((r) => r.bow))], tons: rs.map((r) => r.route.tons_k),
                     top: rs.filter((r) => r.top).length, first: [rs[0].route.a, rs[0].route.b]}};
        }})()""")
        self.assertEqual(got["n"], len(trade["routes"]))
        self.assertEqual(got["bows"], [0])
        self.assertEqual(got["tons"], sorted(got["tons"], reverse=True))
        self.assertEqual(got["top"], 10)
        self.assertEqual(got["first"], ["08", "13"])


if __name__ == "__main__":
    unittest.main()
