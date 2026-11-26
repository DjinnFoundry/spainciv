"""Builder helpers for the City view, Explorer and Advisors: footprints, ranks, peers, pop series,
resource summaries and state land shares / energy (pure functions on tiny inputs)."""

import shutil
import subprocess
import unittest

from pipeline.build import cities, counties, resources, states
from pipeline.core.paths import ROOT


@unittest.skipUnless(shutil.which("node"), "Node is required to render the City View modules")
class CityViewSourceTest(unittest.TestCase):
    def test_city_view_uses_the_loaded_countrys_sources(self):
        result = subprocess.run(["node", "--input-type=module", "-e", r"""
            import assert from 'node:assert/strict';
            import { readFileSync } from 'node:fs';
            import { setCountry } from './web/js/app/country.js';
            import { districtsHtml } from './web/js/ext/cityView/districts.js';
            import { render } from './web/js/ext/cityView/screen.js';

            const load = (dir, name) => JSON.parse(readFileSync(`${dir}/${name}.json`, 'utf8'));
            for (const dir of ['sites/es/data', 'web/data']) {
                const world = load(dir, 'world');
                const cityList = load(dir, 'cities');
                const city = cityList[0];
                const nation = load(dir, 'nation');
                setCountry(world);
                const model = { city, cityList, nation, stateRGB: [0, 0, 0], states: [],
                    sites: [], tiles: [], inds: [], gdpInds: [], peers: [], hexArea: 87 };
                const el = { classList: { add() {} }, style: { setProperty() {} },
                    querySelector: () => ({ addEventListener() {} }), querySelectorAll: () => [] };
                render(el, model, { loadCounties: () => null });
                const districts = districtsHtml(model, load(dir, 'districts'), null);
                if (world.country?.id === 'es') {
                    for (const label of ['Municipios miembros', 'Censo anual de población del INE', 'nivel de provincia', 'Vista de ciudad']) {
                        assert.ok(el.innerHTML.includes(label), `Spanish City View omits ${label}`);
                    }
                    for (const english of ['City View', 'Workforce', 'Member ', 'Loading', 'Rent burden']) {
                        assert.ok(!el.innerHTML.includes(english) && !districts.includes(english), `Spanish City View still says ${english}`);
                    }
                    const wrongSource = el.innerHTML.match(/\bUS [\d€]|\b(?:ACS|BEA|QCEW)\b|U\.S\.|current dollars|Census population estimates/);
                    assert.equal(wrongSource?.[0], undefined);
                    assert.ok(!districts.includes('×US'), 'Spanish districts compare against Spain');
                } else {
                    assert.match(el.innerHTML, /ACS 5-year county estimates/);
                    assert.match(el.innerHTML, /Share of U\.S\. GDP/);
                }
            }
        """], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class FootprintTest(unittest.TestCase):
    def test_majority_of_samples(self):
        world = {
            "owner": [0, 0, 0, -1],
            "counties": ["01001", "01003", "01005"],
            # cell 0: 4 of 7 in CBSA A → A; cell 1: 3 A + 3 B + 1 none → nobody; cell 2: all B; cell 3: water
            "county_samples": [[0, 0, 1, 1, -1, 0, 0], [0, 0, 0, 2, 2, 2, -1], [2] * 7, []],
        }
        members = {"A": ["01001", "01003"], "B": ["01005"]}
        # samples in 01001 or 01003 count for A: cell 0 has 6, cell 1 has 3
        self.assertEqual(cities.footprints(world, members), {"A": {0}, "B": {2}})

    def test_water_cell_never_in_footprint(self):
        world = {"owner": [-1], "counties": ["01001"], "county_samples": [[0] * 7]}
        self.assertEqual(cities.footprints(world, {"A": ["01001"]}), {})


class RanksTest(unittest.TestCase):
    def city(self, id, pop, gdp, growth, food):
        return {"id": id, "population": pop, "gdp": gdp, "growth": growth,
                "yields": {"food": food, "production": 1, "gold": gdp, "science": None, "culture": 1}}

    def test_ranks_and_peers(self):
        cs = [self.city("A", 1000, 100.0, 0.01, 5), self.city("B", 500, 100.0, None, 9),
              self.city("C", 450, None, 0.05, 1), self.city("D", 100, 1.0, 0.02, 1)]
        cities.add_ranks(cs)
        r = {c["id"]: c["ranks"] for c in cs}
        self.assertEqual([r[i]["population"] for i in "ABCD"], [1, 2, 3, 4])
        self.assertEqual([r[i]["gdp_per_capita"] for i in "ABCD"], [2, 1, None, 3])
        self.assertEqual([r[i]["growth"] for i in "ABCD"], [3, None, 1, 2])
        self.assertEqual([r[i]["food"] for i in "ABCD"], [2, 1, 3, 4])  # tie C/D keeps population order
        self.assertIsNone(r["A"]["science"])
        self.assertEqual(set(r["A"]), set(cities.RANK_KEYS))
        self.assertEqual(cs[1]["peers"][:2], ["C", "A"])  # by ratio: 450/500 is closer than 1000/500
        self.assertTrue(all(c["id"] not in c["peers"] and len(c["peers"]) == 3 for c in cs))


class PopSeriesTest(unittest.TestCase):
    pep = {"years": [2020, 2021, 2022], "cbsa": {"A": {"pop": [10.0, None, 12.4], "counties": ["01001", "01003"]}}}

    def test_series(self):
        self.assertEqual(cities.pop_series(self.pep, "A", ["01003", "01001"]), {"2020": 10, "2021": None, "2022": 12})

    def test_missing_or_different_counties(self):
        self.assertIsNone(cities.pop_series(self.pep, "B", None))
        self.assertIsNone(cities.pop_series(self.pep, "A", ["01001"]))
        self.assertIsNone(cities.pop_series(None, "A", None))


class ResourceSummaryTest(unittest.TestCase):
    def test_summary(self):
        types = [{"id": "wind", "unit": "MW"}, {"id": "oil", "unit": "km² play area"}, {"id": "gold", "unit": "employees"}]
        items = [{"type": "wind", "value": 500, "state": "TX"}, {"type": "wind", "value": 700.4, "state": "TX"},
                 {"type": "wind", "value": 600, "state": "IA"}, {"type": "oil", "value": 9000, "state": "TX"},
                 {"type": "oil", "value": 9000, "state": "TX"}]
        s = resources.summarize(items, types)
        self.assertEqual(s["national"]["wind"], {"count": 3, "value": 1800, "unit": "MW"})
        self.assertEqual(s["national"]["oil"], {"count": 2, "value": None, "unit": "km² play area"})
        self.assertEqual(s["national"]["gold"], {"count": 0, "value": 0, "unit": "employees"})
        self.assertEqual(list(s["states"]), ["IA", "TX"])
        self.assertEqual(s["states"]["TX"]["wind"]["value"], 1200)
        self.assertNotIn("gold", s["states"]["TX"])
        self.assertTrue(s["note"])


class StateLandTest(unittest.TestCase):
    def test_land_shares(self):
        keys = states.PCT_KEYS
        world = {"owner": [0, 0, 0, 1], "cover": [1, 7, 0, 1],
                 "pct": {k: ([100, 50, 0, 10] if k == "forest" else [0, 50, 0, 0] if k == "crop" else [0] * 4) for k in keys}}
        land = states.land_shares(world, 0)  # cell 2 has no land-cover samples: left out
        self.assertEqual(land["forest"], 0.75)
        self.assertEqual(land["crop"], 0.25)
        self.assertIsNone(states.land_shares(world, 5))


class CountyFieldsTest(unittest.TestCase):
    def test_fields_cover_requested_metrics(self):
        keys = [f["key"] for f in counties.fields()]
        for k in ("geoid", "name", "state", "population", "land_km2", "density", "bachelors", "median_age", "poverty",
                  "broadband", "commute", "foreign_born", "homeownership", "uninsured", "income", "home_value",
                  "forest", "crop", "pasture", "developed", "cbsa"):
            self.assertIn(k, keys)
        self.assertEqual(len(keys), len(set(keys)))
        # Only the land shares and the map-hex column are about hexes; lens descriptions are reworded for a county.
        self.assertTrue(all("hex" not in f["description"].lower() or f["key"] in counties.LAND or f["key"] == "cell" for f in counties.fields()))


if __name__ == "__main__":
    unittest.main()
