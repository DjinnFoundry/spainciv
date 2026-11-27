// The climate of a month on the map, from clima.json (docs/DATA_CONTRACTS.md): each hex's value for a variable and a
// month, and where that value comes from. No DOM, so tests/test_clima_js.py runs it in node.
//
// The four variables and where a land hex takes its value:
//   temp   mean temperature, (tmax + tmin) / 2 of the hex's ROCIO grid means; a hex without them takes its province's
//          AEMET normal (tmed)
//   prec   the month's rain, the same way (the province's normal prec otherwise)
//   frost  days with a minimum of 0 °C or less, on the grid only: no province figure exists, so no grid, no value
//   sun    sunshine hours at the WMO stations that measure them, on the station's hex; every other hex has none and
//          names its nearest station with sunshine instead (sunshine is never spread between stations)
// Every hex also lists the stations on it with their own WMO normal for the variable.

export const VARIABLES = ["temp", "prec", "frost", "sun"];
export const LENS_ID = { temp: "clima_temp", prec: "clima_lluvia", frost: "clima_heladas", sun: "clima_sol" };
// Colours keep the map's habit, dark for little and light for much; the temperature ramp diverges from blue to red.
export const RAMPS = {
  temp: ["#2b3f8f", "#4f7fc4", "#9cc3df", "#f1ead2", "#efa565", "#d0533a", "#8e1d27"],
  prec: ["#1c1a1f", "#26344f", "#2d5684", "#3d82b3", "#73b3d6", "#c6e6f2"],
  frost: ["#15122a", "#2d2a63", "#4f4a9a", "#7d76c4", "#b3abe2", "#ece8ff"],
  sun: ["#231a08", "#5a3f0e", "#94681a", "#cf9a2b", "#f0cf5a", "#fff3a8"],
};
export const SCALE = { temp: "linear", prec: "log", frost: "linear", sun: "linear" };
const STATION_VAR = { temp: "tmed", prec: "prec", frost: "frost", sun: "sun" };
const EARTH_KM = 6371.0088;

/**
 * clima.json on a map. ctx = {n: hexes, province(i) → INE code of a land hex | null, lonlat(i) → [lon, lat] of its
 * centre}. The nearest station with sunshine of each hex is found the first time it is asked for.
 */
export function climateModel(doc, ctx) {
  const index = new Int32Array(ctx.n).fill(-1);
  doc.cells.forEach((c, k) => (index[c] = k));
  const onCell = new Map();
  for (const s of doc.stations) {
    if (!onCell.has(s.cell)) onCell.set(s.cell, []);
    onCell.get(s.cell).push(s);
  }
  const sunny = doc.stations.filter((s) => s.sun);
  const nearest = new Map(); // cell → station
  return {
    doc, ctx, index, onCell,
    /** The station with sunshine nearest the centre of hex i (great-circle distance). */
    nearestSun(i) {
      if (!nearest.has(i)) {
        const [lon, lat] = ctx.lonlat(i);
        let best = null, bd = Infinity;
        for (const s of sunny) {
          const d = greatCircle(lon, lat, s.lon, s.lat);
          if (d < bd) [best, bd] = [s, d];
        }
        nearest.set(i, best);
      }
      return nearest.get(i);
    },
  };
}

function greatCircle(lon1, lat1, lon2, lat2) {
  const r = Math.PI / 180, dl = (lat2 - lat1) * r, dn = (lon2 - lon1) * r;
  const a = Math.sin(dl / 2) ** 2 + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(dn / 2) ** 2;
  return 2 * EARTH_KM * Math.asin(Math.min(1, Math.sqrt(a)));
}

const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);

/** A station's sunshine for the year: the sum of its twelve monthly totals. */
export const annualSun = (s) => (s.sun ? s.sun.reduce((a, b) => a + b, 0) : null);

/**
 * One month (1–12) of a variable: values[i] for every hex (null off land or without data), domain (the same for the
 * twelve months, clima.json `domains`) and facts(i), what the tooltip says of hex i:
 *   {source: "grid" | "province" | null, max, min (temperature only), stations: [{name, alt, value}],
 *    nearest: the nearest station with sunshine, {name, value: its month, annual}, for a sunshine hex without one
 *    (else null)}
 */
export function layer(model, variable, month) {
  if (!VARIABLES.includes(variable)) throw new Error(`clima: no variable ${variable}`);
  const { doc, ctx, index, onCell } = model;
  const m = month - 1, g = doc.grid;
  const values = new Array(ctx.n).fill(null);
  const source = new Array(ctx.n).fill(null);
  for (let i = 0; i < ctx.n; i++) {
    const code = ctx.province(i);
    if (code == null) continue;
    const k = index[i];
    if (variable === "sun") {
      const own = (onCell.get(i) || []).filter((s) => s.sun).map((s) => s.sun[m]);
      values[i] = mean(own);
      continue;
    }
    let v = null;
    if (k >= 0) {
      if (variable === "temp") {
        const a = g.tmax[m][k], b = g.tmin[m][k];
        v = a == null || b == null ? null : (a + b) / 2;
      } else v = g[variable][m][k];
    }
    if (v != null) {
      values[i] = v;
      source[i] = "grid";
    } else if (variable !== "frost" && doc.provinces[code]) {
      values[i] = doc.provinces[code][variable === "temp" ? "tmed" : "prec"][m];
      source[i] = "province";
    }
  }

  function facts(i) {
    const code = ctx.province(i);
    if (code == null) return null;
    const out = { source: source[i], max: null, min: null, stations: [], nearest: null };
    if (variable === "temp") {
      const k = index[i];
      const p = doc.provinces[code];
      if (source[i] === "grid") [out.max, out.min] = [g.tmax[m][k], g.tmin[m][k]];
      else if (source[i] === "province") [out.max, out.min] = [p.tmax[m], p.tmin[m]];
    }
    out.stations = (onCell.get(i) || []).map((s) => ({ name: s.name, alt: s.alt, value: s[STATION_VAR[variable]]?.[m] ?? null }));
    if (variable === "sun" && values[i] == null) {
      const s = model.nearestSun(i);
      out.nearest = s && { name: s.name, value: s.sun[m], annual: annualSun(s) };
    }
    return out;
  }

  return { values, domain: doc.domains[variable], facts };
}

/**
 * What the tooltip says under a hex's value (facts from layer()): where the value comes from, the stations on the
 * hex and, for sunshine, the nearest station. say(key, params) is i18n's t; value(v) formats a value of the lens;
 * frost: the frost lens, whose stations count days below 0 °C (the grid counts days at 0 °C or less).
 */
export function tipLines(f, { say, value, frost = false, month = "" }) {
  if (!f) return [];
  const lines = [];
  const from = f.source && say(`clima.tip.${f.source}`);
  if (f.max != null && f.min != null) lines.push([say("clima.tip.range", { max: value.temp(f.max), min: value.temp(f.min) }), from].join(" · "));
  else if (from) lines.push(from);
  for (const s of f.stations) {
    const key = s.value == null ? "clima.tip.station.none" : frost ? "clima.tip.station.frost" : "clima.tip.station";
    lines.push(say(key, { name: s.name, alt: value.int(s.alt), value: s.value == null ? "" : value.lens(s.value) }));
  }
  if (f.nearest) {
    lines.push(say("clima.tip.nearest", { name: f.nearest.name, value: value.lens(f.nearest.value), month, hours: value.int(f.nearest.annual) }));
  }
  return lines;
}

/**
 * The stations with the most and the least of a month's frost or sunshine ({name, value}), from their WMO normals:
 * the panel's summary for the two variables that have no figure for peninsular Spain. null for temperature and rain,
 * and for frost in a month when no station has any.
 */
export function stationExtremes(doc, variable, month) {
  const key = { frost: "frost", sun: "sun" }[variable];
  if (!key) return null;
  const vals = doc.stations.filter((s) => s[key]).map((s) => ({ name: s.name, value: s[key][month - 1] }));
  if (!vals.length) return null;
  const top = vals.reduce((a, b) => (b.value > a.value ? b : a));
  if (!(top.value > 0)) return null;
  return { top, bottom: vals.reduce((a, b) => (b.value < a.value ? b : a)) };
}

/** The month strip's bars: AEMET's normal for "España peninsular", 0..1 of the year's highest, for temperature and
 *  rain; null for frost and sunshine (no peninsular figure). */
export function stripBars(doc, variable) {
  const row = { temp: doc.peninsular.tmed, prec: doc.peninsular.prec }[variable];
  if (!row) return null;
  const top = Math.max(...row);
  return row.map((v) => (top > 0 ? Math.max(0, v) / top : 0));
}
