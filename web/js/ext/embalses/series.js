// The weekly series of embalses.json and embalses_semanas.json (docs/DATA_CONTRACTS.md): weeks, percentages and
// rings. No DOM, so tests/test_embalses_js.py runs it in node. A week is an index into `dates` (every Boletín Tuesday,
// ascending). A basin's figure for a week is Σ water stored ÷ Σ capacity of its reservoirs that reported that week,
// as the pipeline summed them; Spain's is the same sum over the basins.

const ISO = /^\d{4}-\d{2}-\d{2}$/;

/** Is v a real calendar day written YYYY-MM-DD ("1995-11-07"; not "1995-02-30")? */
export function isoDay(v) {
  const s = String(v ?? "");
  return ISO.test(s) && !Number.isNaN(Date.parse(s + "T00:00:00Z")) && new Date(s + "T00:00:00Z").toISOString().slice(0, 10) === s;
}

/** The week of a URL value ("1995-11-07"): that Boletín Tuesday, or the latest one before a date between two;
 *  null for anything that is not a date or falls before the first week. */
export function parseWeek(v, dates) {
  const s = String(v ?? "");
  if (!isoDay(s)) return null;
  let lo = 0, hi = dates.length - 1;
  if (!dates.length || s < dates[0]) return null;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (dates[mid] <= s) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

/** A share 0–1, or null where nothing reported (or the capacity is 0). */
const share = (a, c) => (a == null || !c ? null : a / c);

/** A basin's fill in week i (0–1), or null. */
export const basinPct = (b, i) => share(b.actual[i], b.capacity[i]);

/** Spain's (the Boletín's peninsula) total in week i: {actual, capacity, pct}. */
export function national(basins, i) {
  let actual = 0, capacity = 0;
  for (const b of basins) {
    if (b.actual[i] == null) continue;
    actual += b.actual[i];
    capacity += b.capacity[i];
  }
  return { actual, capacity, pct: share(actual, capacity) };
}

/** The weeks of the series' lowest and highest national fill: {min, max} (the first such week on a tie). */
export function extremes(basins) {
  const n = basins[0]?.actual.length ?? 0;
  let min = null, max = null, lo = Infinity, hi = -Infinity;
  for (let i = 0; i < n; i++) {
    const p = national(basins, i).pct;
    if (p == null) continue;
    if (p < lo) { lo = p; min = i; }
    if (p > hi) { hi = p; max = i; }
  }
  return { min, max };
}

const day = (iso) => Date.parse(iso + "T00:00:00Z");

/** The week of `year` nearest the same day of the year as week i (the earlier one on a tie), or null when `year` has
 *  no week within half a week of it (before the first, after the last). */
export function sameWeekIn(dates, i, year) {
  const d = new Date(day(dates[i]));
  const m = d.getUTCMonth(), dd = d.getUTCDate();
  const target = Date.UTC(year, m, m === 1 && dd === 29 ? 28 : dd);
  const k = parseWeek(new Date(target).toISOString().slice(0, 10), dates);
  let best = null, gap = Infinity;
  for (const j of [k, k == null ? 0 : k + 1]) {
    if (j == null || j < 0 || j >= dates.length) continue;
    const g = Math.abs(day(dates[j]) - target);
    if (g < gap) { gap = g; best = j; }
  }
  return gap <= 3.5 * 86400e3 ? best : null;
}

/** The same week a year after week i, or null past the last week. */
export const sameWeekNextYear = (dates, i) => sameWeekIn(dates, i, new Date(day(dates[i])).getUTCFullYear() + 1);

/** The lens values of week i on a grid of n hexes: each basin's fill on its hexes, null elsewhere. */
export function hexValues(basins, i, n) {
  const out = new Array(n).fill(null);
  for (const b of basins) {
    const p = basinPct(b, i);
    for (const c of b.cells) out[c] = p;
  }
  return out;
}

/** A ring's arc: {frac} of the full circle (capped at 1) and {over} when the Boletín gives more than the capacity;
 *  null without both numbers. */
export function ringArc(actual, capacity) {
  if (actual == null || !capacity) return null;
  return { frac: Math.min(1, Math.max(0, actual / capacity)), over: actual > capacity };
}

/** A ring's radius in css px from the reservoir's capacity (hm³): 3·√(capacity / 50), between 3 and 14. */
export const ringRadius = (capacity) => Math.max(3, Math.min(14, 3 * Math.sqrt(Math.max(0, capacity) / 50)));

/** Map scale (css px per km) from which the rings have their full ringRadius; zoomed further out they shrink with
 *  the map, and below RING_MIN_PX they are not drawn, so the country view shows the large reservoirs and the basins
 *  (a drawing convention). */
export const RING_FULL_SCALE = 1;
export const RING_MIN_PX = 2.5;

/** The radius in css px of a ring of ringRadius r at map scale s, or null when it is too small to draw. */
export function ringPx(r, s) {
  const px = r * Math.min(1, s / RING_FULL_SCALE);
  return px >= RING_MIN_PX ? px : null;
}

/** The index of the reservoir with this name (as embalses.json writes it), or null. */
export function findReservoir(reservoirs, name) {
  const k = reservoirs.findIndex((r) => r.name === name);
  return k < 0 ? null : k;
}

/** The capacity in force in week i from a reservoir's runs [[from week, hm³], …] (null before the first). */
export function capacityAt(runs, i) {
  let cap = null;
  for (const [from, v] of runs) {
    if (from > i) break;
    cap = v;
  }
  return cap;
}

/** Basin indices from the driest in week i to the fullest; basins without a figure go last, in file order. */
export function basinsByDryness(basins, i) {
  return basins.map((b, k) => [k, basinPct(b, i)])
    .sort((a, b) => (a[1] == null) - (b[1] == null) || (a[1] ?? 0) - (b[1] ?? 0) || a[0] - b[0])
    .map(([k]) => k);
}

/** The reservoirs reporting in week i: [{k, actual, capacity}] from the weekly matrix, or, without it, from each
 *  reservoir's last report when i is the latest week (null when the matrix is needed and missing). */
export function reporting(reservoirs, weeks, i, latest) {
  const out = [];
  if (weeks) {
    const row = weeks.actual[i];
    for (let k = 0; k < reservoirs.length; k++) {
      if (row[k] != null) out.push({ k, actual: row[k], capacity: capacityAt(weeks.capacity[k], i) });
    }
    return out;
  }
  if (i !== latest) return null;
  reservoirs.forEach((r, k) => {
    if (r.last === latest && r.actual != null) out.push({ k, actual: r.actual, capacity: r.capacity });
  });
  return out;
}
