"""Map projections: the US Albers must not move, the Spanish LAEA and its Canary inset must invert exactly. Then the
planar helpers the builders share: scanlines, distances to an outline, one place from several points, name keys."""

import math
import unittest

from pipeline import countries
from pipeline.core.geo import (
    Albers,
    AlbersEllipsoid,
    Inset,
    InsetProjection,
    LambertAzimuthal,
    LambertAzimuthalEllipsoid,
    MapProjection,
    R_EARTH_KM,
    Shape,
    flat_km,
    row_crossings,
    segment_distance,
    spread_mean,
)
from pipeline.core.names import name_key

# Values from the original usaciv code (tag upstream-2026-11-26) with the shipped world's projection.
SHIPPED = (-2350.109311515341, 1559.2228881834299, 200)
US_GOLDEN = {
    (-122.4194, 37.7749): (280.1637917555213, 1410.8180863538482),  # San Francisco
    (-74.006, 40.7128): (4371.712248483895, 1186.8770369098993),  # New York
    (-96.0, 37.5): (2550.109311515341, 1759.2228881834299),  # projection centre
    (-80.19, 25.76): (4141.682110102824, 2935.629632837986),  # Miami
}


def spherical_area_km2(lon0, lat0, lon1, lat1):
    return R_EARTH_KM**2 * math.radians(lon1 - lon0) * (math.sin(math.radians(lat1)) - math.sin(math.radians(lat0)))


def projected_area(proj, lon0, lat0, lon1, lat1, n=40):
    """Shoelace area of the projected lon/lat box outline."""
    ring = (
        [(lon0 + (lon1 - lon0) * i / n, lat0) for i in range(n)]
        + [(lon1, lat0 + (lat1 - lat0) * i / n) for i in range(n)]
        + [(lon1 - (lon1 - lon0) * i / n, lat1) for i in range(n)]
        + [(lon0, lat1 - (lat1 - lat0) * i / n) for i in range(n)]
    )
    pts = [proj(lo, la) for lo, la in ring]
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))) / 2


class AlbersTest(unittest.TestCase):
    def test_map_projection_default_is_unchanged(self):
        proj = MapProjection(*SHIPPED)
        for (lon, lat), (x, y) in US_GOLDEN.items():
            px, py = proj(lon, lat)
            self.assertAlmostEqual(px, x, places=9)
            self.assertAlmostEqual(py, y, places=9)

    def test_us_country_projection_matches_default(self):
        us, default = countries.COUNTRIES["us"].map_projection(*SHIPPED), MapProjection(*SHIPPED)
        for lon, lat in US_GOLDEN:
            self.assertEqual(us(lon, lat), default(lon, lat))

    def test_roundtrip(self):
        proj = MapProjection(*SHIPPED)
        for lon in range(-124, -66, 7):
            for lat in range(25, 50, 4):
                lo, la = proj.inverse(*proj(lon, lat))
                self.assertAlmostEqual(lo, lon, places=9)
                self.assertAlmostEqual(la, lat, places=9)

    def test_ellipsoid_nlcd_point(self):
        x, y = AlbersEllipsoid()(-74.006, 40.7128)
        self.assertAlmostEqual(x, 1826303.9688559824, places=4)
        self.assertAlmostEqual(y, 2179112.0265995543, places=4)

    def test_equal_area(self):
        a = Albers()
        self.assertAlmostEqual(projected_area(a, -100, 35, -99, 36) / spherical_area_km2(-100, 35, -99, 36), 1, places=4)

    def test_to_web(self):
        self.assertEqual(Albers().to_web(), {"kind": "albers", "lat1": 29.5, "lat2": 45.5, "lat0": 37.5, "lon0": -96.0, "radius_km": R_EARTH_KM})


class LambertAzimuthalTest(unittest.TestCase):
    proj = LambertAzimuthal(40.0, -3.7)

    def test_centre_is_origin(self):
        x, y = self.proj(-3.7, 40.0)
        self.assertAlmostEqual(x, 0, places=9)
        self.assertAlmostEqual(y, 0, places=9)
        self.assertEqual(self.proj.inverse(0, 0), (-3.7, 40.0))

    def test_north_is_up_on_the_central_meridian(self):
        (x0, y0), (x1, y1) = self.proj(-3.7, 37), self.proj(-3.7, 43)
        self.assertAlmostEqual(x0, 0, places=9)
        self.assertAlmostEqual(x1, 0, places=9)
        self.assertGreater(y1, y0)

    def test_roundtrip(self):
        for lon in (-18.0, -9.3, -3.7, 0.0, 3.3, 4.3):
            for lat in (27.6, 35.9, 40.0, 43.8):
                lo, la = self.proj.inverse(*self.proj(lon, lat))
                self.assertAlmostEqual(lo, lon, places=9)
                self.assertAlmostEqual(la, lat, places=9)

    def test_equal_area(self):
        for box in ((-9, 42, -8, 43), (2, 39, 3, 40), (-16, 28, -15, 29)):
            self.assertAlmostEqual(projected_area(self.proj, *box) / spherical_area_km2(*box), 1, places=4)

    def test_distance_madrid_barcelona(self):
        # ~505 km great-circle; an equal-area azimuthal projection centred nearby distorts it by well under 1%.
        (x0, y0), (x1, y1) = self.proj(-3.7038, 40.4168), self.proj(2.1734, 41.3851)
        self.assertAlmostEqual(math.dist((x0, y0), (x1, y1)) / 505, 1, delta=0.01)


class Epsg3035Test(unittest.TestCase):
    def test_guidance_note_example(self):
        # EPSG Guidance Note 7-2, Lambert Azimuthal Equal Area (EPSG:3035) worked example: 50°N 5°E.
        e, n = LambertAzimuthalEllipsoid()(5.0, 50.0)
        self.assertAlmostEqual(e, 3962799.45, delta=0.01)
        self.assertAlmostEqual(n, 2999718.85, delta=0.01)

    def test_origin(self):
        e, n = LambertAzimuthalEllipsoid()(10.0, 52.0)
        self.assertAlmostEqual(e, 4321000.0, places=6)
        self.assertAlmostEqual(n, 3210000.0, places=6)


class InsetTest(unittest.TestCase):
    def setUp(self):
        self.base = LambertAzimuthal(40.0, -3.7)
        self.inset = Inset.make(self.base, "Canarias", (-18.4, -13.2), (27.5, 29.6), 600.0, 650.0)
        self.proj = InsetProjection(self.base, [self.inset])

    def test_inset_points_are_shifted_and_invert(self):
        lon, lat = -15.43, 28.1  # Las Palmas
        bx, by = self.base(lon, lat)
        x, y = self.proj(lon, lat)
        self.assertEqual((x, y), (bx + 600.0, by + 650.0))
        lo, la = self.proj.inverse(x, y)
        self.assertAlmostEqual(lo, lon, places=9)
        self.assertAlmostEqual(la, lat, places=9)

    def test_other_points_are_untouched(self):
        for lon, lat in ((-3.7, 40.4), (-5.35, 36.14), (2.65, 39.57)):  # Madrid, Ceuta's strait, Palma
            self.assertEqual(self.proj(lon, lat), self.base(lon, lat))
            lo, la = self.proj.inverse(*self.proj(lon, lat))
            self.assertAlmostEqual(lo, lon, places=9)
            self.assertAlmostEqual(la, lat, places=9)

    def test_to_web(self):
        web = self.proj.to_web()
        self.assertEqual(web["kind"], "laea")
        self.assertEqual(web["insets"][0]["name"], "Canarias")
        self.assertEqual(len(web["insets"][0]["box"]), 4)


class SpainProjectionTest(unittest.TestCase):
    def test_canary_box_sits_off_the_peninsula_and_clear_of_africa(self):
        es = countries.COUNTRIES["es"]
        proj = es.base_projection()
        x0, y0, x1, y1 = proj.insets[0].box
        # The inset box lies south-west of Cabo de São Vicente and west of Morocco's Atlantic coast.
        sv_x, sv_y = proj(-8.99, 37.02)
        rabat_x, _ = proj(-6.84, 34.02)
        self.assertLess(y1, sv_y)
        self.assertLess(x1, rabat_x)
        for lon, lat in ((-13.5, 29.0), (-18.0, 27.7), (-15.6, 28.0)):  # Lanzarote, El Hierro, Gran Canaria
            x, y = proj(lon, lat)
            self.assertTrue(x0 <= x <= x1 and y0 <= y <= y1)

    def test_hex_is_ten_km_across(self):
        self.assertAlmostEqual(math.sqrt(3) * countries.COUNTRIES["es"].hex_radius_km, 10.0, places=12)


class PlanarTest(unittest.TestCase):
    SQUARE_WITH_HOLE = [[(0, 0), (10, 0), (10, 10), (0, 10)], [(4, 4), (6, 4), (6, 6), (4, 6)]]

    def test_row_crossings_even_odd_and_half_open(self):
        rows = row_crossings(self.SQUARE_WITH_HOLE, 2.0)  # rows at y = 0, 2, …, 8 (y = 10 is the top edge: out)
        self.assertEqual(sorted(rows), [0, 1, 2, 3, 4])
        self.assertEqual(rows[1], [0, 10])
        self.assertEqual(rows[2], [0, 4, 6, 10])  # the hole's bottom edge row: inside it, half-open like ring_contains
        half = row_crossings(self.SQUARE_WITH_HOLE, 2.0, 0.5)  # rows at y = 1, 3, …, 9
        self.assertEqual(sorted(half), [0, 1, 2, 3, 4])
        self.assertEqual(half[2], [0, 4, 6, 10])

    def test_shape_distance(self):
        s = Shape(self.SQUARE_WITH_HOLE)
        self.assertEqual(s.distance(2, 2), 0.0)
        self.assertEqual(s.distance(5, 5), 1.0)  # in the hole: outside, 1 from its edges
        self.assertEqual(s.distance(13, 14), 5.0)  # off a corner
        self.assertEqual(s.distance(-2, 5), 2.0)
        self.assertEqual(s.distance(-2, 5, kx=3.0), 6.0)  # scaled offsets
        self.assertEqual(segment_distance((1, 1), (3, 3), (3, 3)), math.hypot(2, 2))  # a point segment

    def test_flat_km_and_spread_mean(self):
        self.assertAlmostEqual(flat_km((-4.0, 40.0), (-4.0, 40.1)), 11.057, places=3)
        self.assertAlmostEqual(flat_km((-4.0, 40.0), (-3.9, 40.0)), 11.132 * math.cos(math.radians(40)), places=3)
        near = [(-4.0, 40.0), (-4.0, 40.01)]  # 1.1 km apart
        self.assertEqual(spread_mean(near, 2.0), (-4.0, 40.005))
        self.assertIsNone(spread_mean(near + [(-4.0, 40.03)], 2.0))  # the third is 3.3 km from the first
        self.assertIsNone(spread_mean([], 2.0))

    def test_name_key(self):
        self.assertEqual(name_key("Pantà de L'Àliga, El"), "panta de l aliga el")
        self.assertEqual(name_key("Pantà de L'Àliga, El", {"panta", "de", "l", "el"}), "aliga")
        self.assertEqual(name_key("Ñora"), "nora")
class EeaGridTest(unittest.TestCase):
    """The EEA 10 km square of a point, through the EPSG:3035 projection (checked against PROJ 9 via pyproj 3.7.1:
    (3159401.70, 2027957.63) and (2857207.98, 1705377.10) m)."""

    def test_points_fall_in_their_squares(self):
        from pipeline.build.spain_fauna import cell_code

        laea = LambertAzimuthalEllipsoid()
        self.assertEqual(cell_code(*laea(-3.70, 40.40)), "10kmE315N202")  # Madrid
        self.assertEqual(cell_code(*laea(-6.45, 37.00)), "10kmE285N170")  # Doñana
        x, y = laea(-3.70, 40.40)
        self.assertAlmostEqual(x, 3159401.70, places=1)
        self.assertAlmostEqual(y, 2027957.63, places=1)


if __name__ == "__main__":
    unittest.main()
