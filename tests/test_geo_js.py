"""web/js/geo.js must invert exactly what pipeline/core/geo.py projects (run with node; skipped without it)."""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from pipeline import countries

GEO_JS = Path(__file__).resolve().parents[1] / "web" / "js" / "geo.js"
NODE = shutil.which("node")

POINTS = {
    "us": [(-122.4194, 37.7749), (-74.006, 40.7128), (-104.99, 39.74), (-80.19, 25.76)],
    "es": [(-3.7038, 40.4168), (2.1734, 41.3851), (-8.41, 43.36), (2.65, 39.57), (-15.43, 28.1), (-17.9, 27.8), (-5.31, 35.89)],
}


@unittest.skipUnless(NODE, "node is not installed")
class GeoJsTest(unittest.TestCase):
    def roundtrip(self, country_id):
        c = countries.COUNTRIES[country_id]
        proj = c.map_projection(-1000.0, 900.0, c.margin_km)
        web = {**proj.base.to_web(), **proj.to_dict()}
        pts = [proj(lon, lat) for lon, lat in POINTS[country_id]]
        script = (
            f"import({json.dumps(GEO_JS.as_uri())}).then(({{mapProjection}}) => {{"
            f"const p = mapProjection({json.dumps(web)});"
            f"console.log(JSON.stringify({json.dumps(pts)}.map(([x, y]) => p.inverse(x, y))));}});"
        )
        out = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
        for (lon, lat), (jlon, jlat) in zip(POINTS[country_id], json.loads(out.stdout)):
            self.assertAlmostEqual(jlon, lon, places=9)
            self.assertAlmostEqual(jlat, lat, places=9)

    def test_us_albers(self):
        self.roundtrip("us")

    def test_es_laea_with_canary_inset(self):
        self.roundtrip("es")


if __name__ == "__main__":
    unittest.main()
