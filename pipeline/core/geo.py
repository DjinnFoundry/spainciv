"""Small, dependency-free geometry helpers.

Everything on the map lives in "map km": an equal-area projection of the country (Albers for the contiguous
US, Lambert azimuthal for Spain; see pipeline/countries), shifted so the top-left of the map is (0, 0) and y
points *down* (like screen coordinates). Both the hex grid and the browser use this space.
"""

from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from typing import IO, Iterable, Iterator

R_EARTH_KM = 6371.0088


class Albers:
    """Albers equal-area conic, standard USGS parameters for the lower 48."""

    def __init__(self, lat1=29.5, lat2=45.5, lat0=37.5, lon0=-96.0):
        self.params = {"lat1": lat1, "lat2": lat2, "lat0": lat0, "lon0": lon0}
        p1, p2, p0 = map(math.radians, (lat1, lat2, lat0))
        self.lon0 = math.radians(lon0)
        self.n = (math.sin(p1) + math.sin(p2)) / 2
        self.c = math.cos(p1) ** 2 + 2 * self.n * math.sin(p1)
        self.rho0 = R_EARTH_KM * math.sqrt(self.c - 2 * self.n * math.sin(p0)) / self.n

    def __call__(self, lon: float, lat: float) -> tuple[float, float]:
        rho = R_EARTH_KM * math.sqrt(self.c - 2 * self.n * math.sin(math.radians(lat))) / self.n
        theta = self.n * (math.radians(lon) - self.lon0)
        return rho * math.sin(theta), self.rho0 - rho * math.cos(theta)

    def inverse(self, x: float, y: float) -> tuple[float, float]:
        """Albers km → (lon, lat)."""
        dy = self.rho0 - y
        rho = math.hypot(x, dy)
        theta = math.atan2(x, dy)
        s = (self.c - (rho * self.n / R_EARTH_KM) ** 2) / (2 * self.n)
        return math.degrees(self.lon0 + theta / self.n), math.degrees(math.asin(max(-1.0, min(1.0, s))))

    def to_web(self) -> dict:
        """The projection for the browser (web/js/geo.js), as world.json country.projection describes it."""
        return {"kind": "albers", **self.params, "radius_km": R_EARTH_KM}


class AlbersEllipsoid:
    """Ellipsoidal Albers equal-area (Snyder 1987, eqs. 14-3..14-6), output in metres.

    Defaults are EPSG:5070 (NAD83 / Conus Albers): GRS80, lat0 23, lon0 -96,
    standard parallels 29.5 and 45.5. Used to look up rasters such as NLCD.
    """

    def __init__(self, lat1=29.5, lat2=45.5, lat0=23.0, lon0=-96.0, a=6378137.0, inv_f=298.257222101):
        f = 1 / inv_f
        self.a = a
        self.e2 = f * (2 - f)
        self.e = math.sqrt(self.e2)
        self.lon0 = math.radians(lon0)
        p1, p2, p0 = map(math.radians, (lat1, lat2, lat0))
        m1, m2 = self._m(p1), self._m(p2)
        q1, q2, q0 = self._q(p1), self._q(p2), self._q(p0)
        self.n = (m1 * m1 - m2 * m2) / (q2 - q1)
        self.c = m1 * m1 + self.n * q1
        self.rho0 = a * math.sqrt(self.c - self.n * q0) / self.n

    def _m(self, phi: float) -> float:
        s = math.sin(phi)
        return math.cos(phi) / math.sqrt(1 - self.e2 * s * s)

    def _q(self, phi: float) -> float:
        s, e = math.sin(phi), self.e
        return (1 - self.e2) * (s / (1 - self.e2 * s * s) - math.log((1 - e * s) / (1 + e * s)) / (2 * e))

    def __call__(self, lon: float, lat: float) -> tuple[float, float]:
        rho = self.a * math.sqrt(self.c - self.n * self._q(math.radians(lat))) / self.n
        theta = self.n * (math.radians(lon) - self.lon0)
        return rho * math.sin(theta), self.rho0 - rho * math.cos(theta)


class LambertAzimuthal:
    """Lambert azimuthal equal-area, spherical (Snyder 1987, eqs. 24-2..24-4 and 20-14..20-18), output in km.

    The map projection for countries far from the Albers belt: centred on the country, so north stays up.
    """

    def __init__(self, lat0: float, lon0: float):
        self.lat0, self.lon0 = lat0, lon0
        self._p0, self._l0 = math.radians(lat0), math.radians(lon0)

    def __call__(self, lon: float, lat: float) -> tuple[float, float]:
        p, dl = math.radians(lat), math.radians(lon) - self._l0
        sp0, cp0 = math.sin(self._p0), math.cos(self._p0)
        k = math.sqrt(2 / (1 + sp0 * math.sin(p) + cp0 * math.cos(p) * math.cos(dl)))
        return (
            R_EARTH_KM * k * math.cos(p) * math.sin(dl),
            R_EARTH_KM * k * (cp0 * math.sin(p) - sp0 * math.cos(p) * math.cos(dl)),
        )

    def inverse(self, x: float, y: float) -> tuple[float, float]:
        """km → (lon, lat)."""
        rho = math.hypot(x, y)
        if rho == 0:
            return self.lon0, self.lat0
        c = 2 * math.asin(min(1.0, rho / (2 * R_EARTH_KM)))
        sp0, cp0, sc, cc = math.sin(self._p0), math.cos(self._p0), math.sin(c), math.cos(c)
        lat = math.asin(max(-1.0, min(1.0, cc * sp0 + y * sc * cp0 / rho)))
        lon = self._l0 + math.atan2(x * sc, rho * cp0 * cc - y * sp0 * sc)
        return math.degrees(lon), math.degrees(lat)

    def to_web(self) -> dict:
        return {"kind": "laea", "lat0": self.lat0, "lon0": self.lon0, "radius_km": R_EARTH_KM}


class LambertAzimuthalEllipsoid:
    """Ellipsoidal Lambert azimuthal equal-area (Snyder 1987, eqs. 3-12, 24-11..24-14), output in metres.

    Defaults are EPSG:3035 (ETRS89-extended / LAEA Europe): GRS80, centre 52°N 10°E, false easting 4,321 km and
    false northing 3,210 km. Used to look up rasters published in EPSG:3035, such as CORINE Land Cover.
    """

    def __init__(self, lat0=52.0, lon0=10.0, false_e=4321000.0, false_n=3210000.0, a=6378137.0, inv_f=298.257222101):
        f = 1 / inv_f
        self.a, self.e2 = a, f * (2 - f)
        self.e = math.sqrt(self.e2)
        self.lon0, self.fe, self.fn = math.radians(lon0), false_e, false_n
        p0 = math.radians(lat0)
        self.qp = self._q(math.pi / 2)
        self.rq = a * math.sqrt(self.qp / 2)
        self.b0 = math.asin(self._q(p0) / self.qp)
        m0 = math.cos(p0) / math.sqrt(1 - self.e2 * math.sin(p0) ** 2)
        self.d = a * m0 / (self.rq * math.cos(self.b0))

    def _q(self, phi: float) -> float:
        s, e = math.sin(phi), self.e
        return (1 - self.e2) * (s / (1 - self.e2 * s * s) - math.log((1 - e * s) / (1 + e * s)) / (2 * e))

    def __call__(self, lon: float, lat: float) -> tuple[float, float]:
        beta = math.asin(max(-1.0, min(1.0, self._q(math.radians(lat)) / self.qp)))
        dl = math.radians(lon) - self.lon0
        sb0, cb0 = math.sin(self.b0), math.cos(self.b0)
        b = self.rq * math.sqrt(2 / (1 + sb0 * math.sin(beta) + cb0 * math.cos(beta) * math.cos(dl)))
        x = b * self.d * math.cos(beta) * math.sin(dl)
        y = b / self.d * (cb0 * math.sin(beta) - sb0 * math.cos(beta) * math.cos(dl))
        return self.fe + x, self.fn + y


@dataclass(frozen=True)
class Inset:
    """A region drawn away from where it really is (e.g. the Canary Islands in a box off the coast).

    Points inside the lon/lat window are projected and then shifted by (dx, dy) km in the base projection's
    plane (y up). `box` is the shifted window's extent in that plane, so the inverse knows which points to
    shift back. Build one with Inset.make().
    """

    name: str
    lon: tuple[float, float]
    lat: tuple[float, float]
    dx: float
    dy: float
    box: tuple[float, float, float, float]

    @classmethod
    def make(cls, base, name: str, lon: tuple[float, float], lat: tuple[float, float], dx: float, dy: float) -> "Inset":
        pts = [base(lon[0] + (lon[1] - lon[0]) * i / 20, lat[0] + (lat[1] - lat[0]) * j / 20) for i in range(21) for j in range(21)]
        xs, ys = [p[0] + dx for p in pts], [p[1] + dy for p in pts]
        return cls(name, lon, lat, dx, dy, (min(xs), min(ys), max(xs), max(ys)))

    def holds(self, lon: float, lat: float) -> bool:
        return self.lon[0] <= lon <= self.lon[1] and self.lat[0] <= lat <= self.lat[1]

    def to_dict(self) -> dict:
        return {"name": self.name, "lon": list(self.lon), "lat": list(self.lat), "dx": self.dx, "dy": self.dy, "box": list(self.box)}


class InsetProjection:
    """A base projection (km, y up) with insets: lon/lat in an inset's window is shifted into its box."""

    def __init__(self, base, insets: list[Inset]):
        self.base, self.insets = base, list(insets)

    def __call__(self, lon: float, lat: float) -> tuple[float, float]:
        x, y = self.base(lon, lat)
        for s in self.insets:
            if s.holds(lon, lat):
                return x + s.dx, y + s.dy
        return x, y

    def inverse(self, x: float, y: float) -> tuple[float, float]:
        for s in self.insets:
            x0, y0, x1, y1 = s.box
            if x0 <= x <= x1 and y0 <= y <= y1:
                lon, lat = self.base.inverse(x - s.dx, y - s.dy)
                if s.holds(lon, lat):
                    return lon, lat
        return self.base.inverse(x, y)

    def occluded(self, lon: float, lat: float) -> bool:
        """True for a real point outside every inset window that the projection puts inside an inset's box (the sea
        under the Canary box): data there would mix with the inset's."""
        if any(s.holds(lon, lat) for s in self.insets):
            return False
        x, y = self.base(lon, lat)
        return any(s.box[0] <= x <= s.box[2] and s.box[1] <= y <= s.box[3] for s in self.insets)

    def to_web(self) -> dict:
        return {**self.base.to_web(), "insets": [s.to_dict() for s in self.insets]}


@dataclass
class MapProjection:
    """lon/lat → map km (origin top-left, y down).

    `base` is any projection in km with y up (`__call__` and `inverse`); the default is the US Albers.
    """

    min_x: float
    max_y: float
    margin: float
    base: object = None

    def __post_init__(self):
        if self.base is None:
            self.base = Albers()

    def __call__(self, lon: float, lat: float) -> tuple[float, float]:
        x, y = self.base(lon, lat)
        return x - self.min_x + self.margin, self.max_y - y + self.margin

    def inverse(self, x: float, y: float) -> tuple[float, float]:
        """map km → (lon, lat)."""
        return self.base.inverse(x + self.min_x - self.margin, self.max_y + self.margin - y)

    def occluded(self, lon: float, lat: float) -> bool:
        """True when the point is hidden under an inset box (see InsetProjection.occluded)."""
        occ = getattr(self.base, "occluded", None)
        return bool(occ and occ(lon, lat))

    def to_dict(self) -> dict:
        return {"min_x": self.min_x, "max_y": self.max_y, "margin": self.margin}


def ring_contains(ring: list[tuple[float, float]], x: float, y: float) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def ring_area(ring: list[tuple[float, float]]) -> float:
    """Signed shoelace area of a ring, in its own units (positive when counter-clockwise)."""
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1])) / 2


def ring_centroid(ring: list[tuple[float, float]]) -> tuple[float, float]:
    """Planar centroid of a ring (its first point if it has no area). On lon/lat rings the distortion is negligible at
    the scale of a municipality."""
    a = ring_area(ring)
    if a == 0:
        return ring[0]
    cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        cross = x0 * y1 - x1 * y0
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    return cx / (6 * a), cy / (6 * a)


def ring_edges(rings: Iterable[list[tuple[float, float]]]) -> Iterator[tuple[tuple, tuple]]:
    """Every edge (a, b) of the rings, each ring closed."""
    for ring in rings:
        yield from zip(ring, ring[1:] + ring[:1])


def row_crossings(rings: Iterable[list[tuple[float, float]]], dy: float, offset: float = 0.0) -> dict[int, list[float]]:
    """Scanline: for each row k (y = (k + offset)·dy) the edges cross, the sorted x of the crossings. A point of a row
    is inside (even-odd rule, holes included) when an odd number of them lie left of it. Half-open in y, like
    ring_contains, so a vertex on a row counts once."""
    rows: dict[int, list[float]] = {}
    for (x1, y1), (x2, y2) in ring_edges(rings):
        if y1 == y2:
            continue
        lo, hi = sorted((y1, y2))
        for k in range(math.ceil(lo / dy - offset), math.ceil(hi / dy - offset)):
            y = (k + offset) * dy
            rows.setdefault(k, []).append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    for xs in rows.values():
        xs.sort()
    return rows


KM_PER_DEG_LAT = 110.57  # a degree of latitude, and of longitude at the equator, in km (flat-earth distances)
KM_PER_DEG_LON = 111.32


def lonlat_scale(lat: float) -> tuple[float, float]:
    """km per degree of longitude and of latitude at `lat`, for flat-earth distances over a few km."""
    return KM_PER_DEG_LON * math.cos(math.radians(lat)), KM_PER_DEG_LAT


def flat_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distance in km between two lon/lat points, flat-earth at their mean latitude (fine over a few km)."""
    kx, ky = lonlat_scale((a[1] + b[1]) / 2)
    return math.hypot((a[0] - b[0]) * kx, (a[1] - b[1]) * ky)


def segment_distance(p: tuple[float, float], a: tuple, b: tuple, kx: float = 1.0, ky: float = 1.0) -> float:
    """Distance from p to the segment a-b, the x and y offsets scaled by kx and ky: 1 and 1 in map km, lonlat_scale
    of p's latitude for lon/lat points in km."""
    ax, ay, bx, by = (a[0] - p[0]) * kx, (a[1] - p[1]) * ky, (b[0] - p[0]) * kx, (b[1] - p[1]) * ky
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
    return math.hypot(ax + t * dx, ay + t * dy)


def spread_mean(points: list[tuple[float, float]], limit_km: float) -> tuple[float, float] | None:
    """One place from lon/lat points that may be the same place (a thing mapped in pieces, or twice): their mean,
    rounded to 5 decimals, when they all lie within `limit_km` of each other (flat_km), else None (two places of one
    name). None for no points."""
    if not points or any(flat_km(p, q) > limit_km for p in points for q in points):
        return None
    lon, lat = (round(sum(axis) / len(points), 5) for axis in zip(*points))
    return lon, lat


class Shape:
    """A (multi)polygon as a bag of rings; even-odd rule handles holes."""

    def __init__(self, rings: Iterable[list[tuple[float, float]]]):
        self.rings = [r for r in rings if len(r) >= 3]
        xs = [p[0] for r in self.rings for p in r] or [0]
        ys = [p[1] for r in self.rings for p in r] or [0]
        self.bbox = (min(xs), min(ys), max(xs), max(ys))

    def contains(self, x: float, y: float) -> bool:
        x0, y0, x1, y1 = self.bbox
        if x < x0 or x > x1 or y < y0 or y > y1:
            return False
        inside = False
        for r in self.rings:
            if ring_contains(r, x, y):
                inside = not inside
        return inside

    def distance(self, x: float, y: float, kx: float = 1.0, ky: float = 1.0) -> float:
        """0 inside; outside, the distance to the nearest edge (segment_distance, with its kx and ky)."""
        if self.contains(x, y):
            return 0.0
        return min((segment_distance((x, y), a, b, kx, ky) for a, b in ring_edges(self.rings)), default=math.inf)


class ShapeIndex:
    """Bucket shapes by coarse grid square so point lookups only test a few shapes."""

    def __init__(self, shapes: list[Shape], cell_km: float = 100.0):
        self.shapes = shapes
        self.cell = cell_km
        self.buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
        for k, s in enumerate(shapes):
            x0, y0, x1, y1 = s.bbox
            for gx in range(int(x0 // cell_km), int(x1 // cell_km) + 1):
                for gy in range(int(y0 // cell_km), int(y1 // cell_km) + 1):
                    self.buckets[(gx, gy)].append(k)

    def locate(self, x: float, y: float) -> int:
        for k in self.buckets.get((int(x // self.cell), int(y // self.cell)), ()):
            if self.shapes[k].contains(x, y):
                return k
        return -1


# --- file formats -----------------------------------------------------------

KML_NS = "{http://www.opengis.net/kml/2.2}"


def read_kml_placemarks(fileobj: IO[bytes]) -> Iterator[tuple[dict, list[list[tuple[float, float]]]]]:
    """Yield (properties, rings) for each Placemark in a Census cartographic KML."""
    for _, el in ET.iterparse(fileobj):
        if el.tag != KML_NS + "Placemark":
            continue
        props = {sd.get("name"): (sd.text or "") for sd in el.iter(KML_NS + "SimpleData")}
        rings = []
        for coords in el.iter(KML_NS + "coordinates"):
            pts = []
            for tok in (coords.text or "").split():
                lon, lat = tok.split(",")[:2]
                pts.append((round(float(lon), 5), round(float(lat), 5)))
            rings.append(pts)
        yield props, rings
        el.clear()


def geojson_rings(geom: dict) -> list[list[tuple[float, float]]]:
    t, c = geom["type"], geom["coordinates"]
    polys = [c] if t == "Polygon" else c if t == "MultiPolygon" else []
    return [[(round(x, 5), round(y, 5)) for x, y, *_ in ring] for poly in polys for ring in poly]


def geojson_lines(geom: dict) -> list[list[tuple[float, float]]]:
    t, c = geom["type"], geom["coordinates"]
    lines = [c] if t == "LineString" else c if t == "MultiLineString" else []
    return [[(round(x, 5), round(y, 5)) for x, y, *_ in line] for line in lines]


def load_geojson(path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["features"]


def bbox_intersects(points: Iterable[tuple[float, float]], bbox: tuple[float, float, float, float]) -> bool:
    x0, y0, x1, y1 = bbox
    return any(x0 <= x <= x1 and y0 <= y <= y1 for x, y in points)
