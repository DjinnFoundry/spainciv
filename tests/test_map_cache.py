"""The pan path of the cached map (web/js/render/map.js shiftRegions): after shifting the cache by (dx, dy) device
pixels, the repainted rectangles and the kept pixels must cover the canvas exactly once, and every kept pixel must
come from at least `pad` inside the old canvas (its edge lacks the art of the cells beyond it). Run with node."""

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class ShiftRegionsTest(unittest.TestCase):
    def test_regions_and_kept_pixels_tile_the_canvas(self):
        result = subprocess.run(["node", "--input-type=module", "-e", r"""
            import assert from 'node:assert/strict';
            import { shiftRegions } from './web/js/render/map.js';

            const W = 37, H = 23, pad = 3;
            for (let dx = -W; dx <= W; dx++) {
                for (let dy = -H; dy <= H; dy++) {
                    const regions = shiftRegions(W, H, dx, dy, pad);
                    const keepsNothing = (dx && Math.abs(dx) + pad >= W) || (dy && Math.abs(dy) + pad >= H);
                    if (keepsNothing) {
                        assert.equal(regions, null, `shift ${dx},${dy} keeps nothing: render it whole`);
                        continue;
                    }
                    for (let y = 0; y < H; y++) {
                        for (let x = 0; x < W; x++) {
                            const n = regions.filter((r) => x >= r.x0 && x < r.x1 && y >= r.y0 && y < r.y1).length;
                            assert.ok(n <= 1, `pixel ${x},${y} repainted twice after shift ${dx},${dy}`);
                            // the old canvas pixel this one is copied from, and how far it sits from the old edge
                            const ox = x + dx, oy = y + dy;
                            const fromEdge = Math.min(dx ? (dx > 0 ? W - 1 - ox : ox) : Infinity, dy ? (dy > 0 ? H - 1 - oy : oy) : Infinity);
                            if (n === 0) assert.ok(fromEdge >= pad, `pixel ${x},${y} kept from ${ox},${oy}, too near the old edge (${dx},${dy})`);
                            else assert.ok(fromEdge < pad || ox < 0 || oy < 0 || ox >= W || oy >= H, `pixel ${x},${y} repainted needlessly (${dx},${dy})`);
                        }
                    }
                }
            }
            assert.deepEqual(shiftRegions(W, H, 0, 0, pad), [], 'no shift, nothing to repaint');
        """], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_margin_regions_tile_the_margin(self):
        """A view-first render paints the inner rectangle; marginRegions must cover the rest exactly once."""
        result = subprocess.run(["node", "--input-type=module", "-e", r"""
            import assert from 'node:assert/strict';
            import { marginRegions } from './web/js/render/map.js';

            for (const [W, H, m] of [[37, 23, 5], [10, 10, 4], [9, 30, 4], [8, 8, 4], [12, 7, 0]]) {
                const regions = marginRegions(W, H, m);
                const inner = 2 * m < W && 2 * m < H;
                for (let y = 0; y < H; y++) {
                    for (let x = 0; x < W; x++) {
                        const n = regions.filter((r) => x >= r.x0 && x < r.x1 && y >= r.y0 && y < r.y1).length;
                        const inside = inner && x >= m && x < W - m && y >= m && y < H - m;
                        assert.equal(n, inside ? 0 : 1, `pixel ${x},${y} of ${W}x${H} inset ${m}`);
                    }
                }
            }
        """], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
