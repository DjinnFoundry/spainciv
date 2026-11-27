"""Spain's military layer: OSM parsing (pipeline/sources/es/military.py) and the placement and naming rules of
pipeline/build/spain_military.py."""

import unittest

from pipeline.build import spain_military as sm
from pipeline.sources.es import military as src


def pts(coords):
    return [{"lon": x, "lat": y} for x, y in coords]


def square(x0, y0, size):
    return [[x0, y0], [x0 + size, y0], [x0 + size, y0 + size], [x0, y0 + size], [x0, y0]]


def item(osm, tags, outer=None, inner=(), point=None):
    return {"osm": osm, "tags": tags, "outer": [outer] if outer else [], "inner": list(inner), "point": point}


def feature(*args, **kw):
    return sm.Feature(item(*args, **kw), lambda lon, lat: (lon, lat))  # plane coordinates: area in "degrees²"


class AssembleTest(unittest.TestCase):
    def test_joins_split_and_reversed_ways_into_one_ring(self):
        a = pts([(0, 0), (1, 0), (1, 1)])
        b = pts([(0, 1), (1, 1)])  # runs backwards
        c = pts([(0, 1), (0, 0)])
        rings = src.assemble([a, b, c])
        self.assertEqual(len(rings), 1)
        self.assertEqual(src._key(rings[0][0]), src._key(rings[0][-1]))
        self.assertEqual(len(rings[0]), 5)

    def test_drops_a_chain_that_never_closes(self):
        self.assertEqual(src.assemble([pts([(0, 0), (1, 0), (1, 1)])]), [])

    def test_element_shapes(self):
        node = src.element({"type": "node", "id": 7, "lon": -3.123456, "lat": 40.654321, "tags": {"name": "X", "foo": "y"}})
        self.assertEqual(node["osm"], "n7")
        self.assertEqual(node["point"], [-3.12346, 40.65432])
        self.assertEqual(node["tags"], {"name": "X"})  # only the tags the builder reads
        fence = {"type": "way", "id": 1, "tags": {}, "geometry": pts([(0, 0), (1, 0), (1, 1), (2, 2)])}
        self.assertIsNone(src.element(fence))  # an open way is a line, not an area
        rel = {"type": "relation", "id": 2, "tags": {"landuse": "military"}, "members": [
            {"type": "way", "role": "outer", "geometry": pts(square(0, 0, 0.1))},
            {"type": "way", "role": "inner", "geometry": pts(square(0.04, 0.04, 0.02))},
        ]}
        out = src.element(rel)
        self.assertEqual((len(out["outer"]), len(out["inner"])), (1, 1))

    def test_a_building_smaller_than_the_tolerance_keeps_its_points(self):
        tiny = {"type": "way", "id": 3, "tags": {"military": "barracks"}, "geometry": pts(square(0, 0, 0.0001))}
        self.assertEqual(len(src.element(tiny)["outer"][0]), 5)


class RulesTest(unittest.TestCase):
    def test_left_out(self):
        self.assertEqual(sm.excluded({"name": "Casa Cuartel de la Guardia Civil"}), "police")
        self.assertEqual(sm.excluded({"name": "Base", "operator": "Ertzaintza"}), "police")
        self.assertEqual(sm.excluded({"name": "Estaleiros de Navantia"}), "civil")
        self.assertEqual(sm.excluded({"name": "Antiguo Cuartel de Carabineros"}), "former")
        self.assertEqual(sm.excluded({"name": "Batería de costa del Cap des Pinar"}), "former")
        self.assertIsNone(sm.excluded({"name": "Acuartelamiento Aéreo de Los Alcázares"}))
        self.assertIsNone(sm.excluded({"name": "Base Aérea de Morón"}))

    def test_branch_order(self):
        self.assertEqual(sm.branch({"name": "Base Aérea de Morón", "operator": "Spanish Air and Space Force;United States Air Force"}),
                         ("air_force", "operator"))
        self.assertEqual(sm.branch({"name": "Acuartelamiento Aéreo de Los Alcázares"}), ("air_force", "name"))  # not army
        self.assertEqual(sm.branch({"name": "Acuartelamiento del Tercio de Levante de Infantería de Marina"}), ("navy", "name"))
        self.assertEqual(sm.branch({"name": "Base Naval de Rota"}), ("navy", "name"))
        self.assertEqual(sm.branch({"name": "Campo de Maniobras y Tiro de El Teleno"}), ("army", "name"))
        self.assertEqual(sm.branch({"name": "Batallón de la UME"}), ("ume", "name"))
        self.assertEqual(sm.branch({"name": "Son Sant Joan", "military": "airfield"}), ("air_force", "tag"))
        self.assertEqual(sm.branch({"name": "Finca El Doctor"}, ["Ejército de Tierra de España"]), ("army", "wikidata"))
        self.assertEqual(sm.branch({"name": "Instituto Tecnológico La Marañosa"}), ("other", None))

    def test_tiers(self):
        self.assertEqual([sm.tier(a) for a in (None, 0.1, 0.5, 9.9, 10.0)], ["site", "site", "base", "base", "major"])


class FoldTest(unittest.TestCase):
    def test_nested_features_fold_into_the_outermost(self):
        big = feature("w1", {"landuse": "military"}, square(0, 0, 10))
        mid = feature("w2", {"name": "Base Aérea de X", "military": "airfield"}, square(1, 1, 4))
        small = feature("w3", {"name": "Hangar"}, square(2, 2, 1))
        node = feature("n4", {"name": "Puesto de mando"}, point=[8, 8])
        alone = feature("w5", {"name": "Cuartel"}, square(20, 20, 1))
        heads = sm.fold([big, mid, small, node, alone])
        self.assertEqual({h.osm for h in heads}, {"w1", "w5"})
        self.assertEqual([p.osm for p in big.parts], ["w2", "w3", "n4"])  # largest first
        tags = sm.head_tags(big)  # an unnamed head takes its largest named part's name
        self.assertEqual(tags["name"], "Base Aérea de X")
        self.assertEqual(sm.branch(tags), ("air_force", "name"))

    def test_the_same_outline_twice_folds_into_the_older_element(self):
        a = feature("w10", {"name": "Centro Deportivo La Dehesa"}, square(0, 0, 2))
        b = feature("w9", {"name": "Cdscm La Dehesa"}, square(0, 0, 2))
        heads = sm.fold([a, b])
        self.assertEqual([h.osm for h in heads], ["w9"])

    def test_training_areas_only_on_military_land(self):
        airsoft = feature("w1", {"name": "VIETNAM", "military": "training_area"}, square(0, 0, 1))
        self.assertEqual(sm.keep(sm.head_tags(airsoft)), "outside military land")
        land = feature("w2", {"name": "Campo de Maniobras", "landuse": "military"}, square(0, 0, 5))
        inner = feature("w3", {"name": "Zona de tiro", "military": "range"}, square(1, 1, 1))
        sm.fold([land, inner])
        self.assertIsNone(sm.keep(sm.head_tags(land)))
        unnamed = feature("w4", {"landuse": "military"}, square(9, 9, 1))
        self.assertEqual(sm.keep(sm.head_tags(unnamed)), "unnamed")


def inst(id, area, cell, cbsa=None, comp="army", tier=None, state="Z"):
    return {"id": id, "name": id, "component": comp, "area_km2": area, "cell": cell, "cells": None, "cbsa": cbsa,
            "state": state, "tier": tier or sm.tier(area)}


class BlocksTest(unittest.TestCase):
    def test_ranges_are_the_largest_boundaries(self):
        insts = [inst("a", 300.0, 1), inst("b", 25.0, 2), inst("c", 19.9, 3)]
        insts[0]["cells"] = [10, 11]
        r = sm.ranges(insts)
        self.assertEqual([x["id"] for x in r], ["a", "b"])
        self.assertEqual(r[0]["cells"], [10, 11])
        self.assertEqual(r[1]["cells"], [2])  # covers no hex centre: drawn on its point's hex

    def test_garrisons(self):
        insts = [inst("base", 2.0, 1, cbsa="C1", comp="navy"), inst("office", 0.01, 2, cbsa="C2"),
                 inst("range", 50.0, 9, cbsa=None)]
        rngs = sm.ranges(insts)
        cities = [{"id": "C1", "footprint": [1]}, {"id": "C2", "footprint": [2]}, {"id": "C3", "footprint": [9]}]
        g = sm.garrisons(insts, rngs, cities)
        self.assertEqual(set(g), {"C1", "C3"})  # a 'site' alone does not garrison a city; a range hex does
        self.assertTrue(g["C1"]["naval"])
        self.assertEqual(g["C3"]["installations"], ["range"])

    def test_provinces_count_every_region(self):
        p = sm.provinces([inst("a", 12.0, 1, state="Z"), inst("b", None, 2, state="Z", comp="navy")],
                         [{"abbr": "Z", "population": 10}, {"abbr": "M", "population": 20}])
        self.assertEqual(p["Z"]["installations"], 2)
        self.assertEqual(p["Z"]["by_component"], {"army": 1, "navy": 1})
        self.assertEqual(p["Z"]["major"], 1)
        self.assertEqual(p["M"]["installations"], 0)


if __name__ == "__main__":
    unittest.main()
