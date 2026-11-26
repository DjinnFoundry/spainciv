// Map km → lon/lat, mirroring pipeline/core/geo.py (Albers, LambertAzimuthal, InsetProjection, MapProjection).
// world.json `country.projection` describes the projection: {kind: "albers"|"laea", ...params, radius_km, min_x, max_y,
// margin, insets?: [{name, lon, lat, dx, dy, box}]}. Keep in sync with the Python side (tests/test_geo.py).

const RAD = Math.PI / 180;

function albers({ lat1, lat2, lat0, lon0, radius_km: RE }) {
  const p1 = lat1 * RAD, p2 = lat2 * RAD, p0 = lat0 * RAD;
  const n = (Math.sin(p1) + Math.sin(p2)) / 2;
  const c = Math.cos(p1) ** 2 + 2 * n * Math.sin(p1);
  const rho0 = (RE * Math.sqrt(c - 2 * n * Math.sin(p0))) / n;
  return {
    n, lon0,
    inverse(x, y) {
      const dy = rho0 - y, rho = Math.hypot(x, dy);
      const s = (c - ((rho * n) / RE) ** 2) / (2 * n);
      return [lon0 + Math.atan2(x, dy) / n / RAD, Math.asin(Math.max(-1, Math.min(1, s))) / RAD];
    },
  };
}

function laea({ lat0, lon0, radius_km: RE }) {
  const sp0 = Math.sin(lat0 * RAD), cp0 = Math.cos(lat0 * RAD);
  return {
    n: 0, lon0, // no conic convergence: meridians are near-vertical around the centre
    inverse(x, y) {
      const rho = Math.hypot(x, y);
      if (rho === 0) return [lon0, lat0];
      const c = 2 * Math.asin(Math.min(1, rho / (2 * RE))), sc = Math.sin(c), cc = Math.cos(c);
      const lat = Math.asin(Math.max(-1, Math.min(1, cc * sp0 + (y * sc * cp0) / rho)));
      return [lon0 + Math.atan2(x * sc, rho * cp0 * cc - y * sp0 * sc) / RAD, lat / RAD];
    },
  };
}

const KINDS = { albers, laea };

/** {inverse(mapX, mapY) → [lon, lat], n, lon0} for a world.json country.projection, or null if unknown. */
export function mapProjection(p) {
  const make = p && KINDS[p.kind];
  if (!make) return null;
  const base = make(p), insets = p.insets || [];
  const holds = (s, lon, lat) => lon >= s.lon[0] && lon <= s.lon[1] && lat >= s.lat[0] && lat <= s.lat[1];
  return {
    n: base.n, lon0: base.lon0,
    inverse(mx, my) {
      const x = mx + p.min_x - p.margin, y = p.max_y + p.margin - my;
      for (const s of insets) {
        const [x0, y0, x1, y1] = s.box;
        if (x >= x0 && x <= x1 && y >= y0 && y <= y1) {
          const ll = base.inverse(x - s.dx, y - s.dy);
          if (holds(s, ll[0], ll[1])) return ll;
        }
      }
      return base.inverse(x, y);
    },
  };
}

// The original usaciv world.json (no country block): the lower-48 Albers with the shipped grid's fit.
export const US_ALBERS = { kind: "albers", lat1: 29.5, lat2: 45.5, lat0: 37.5, lon0: -96, radius_km: 6371.0088 };
