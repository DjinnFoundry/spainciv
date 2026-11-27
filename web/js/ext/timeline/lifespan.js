// Who was alive in a year, from personajes.json (docs/DATA_CONTRACTS.md): each person's `life` = [from, to], the
// astronomical years (0 = 1 BC) in which the builder says they may have been alive, both included
// (pipeline/build/spain_personajes.py lifespan, DECISIONS E105); `approx` marks a decade or a century among the dates. No DOM, so tests/test_timeline_js.py runs it in node;
// the twins of the builder's dominant(), roman(), ordinal() and century arithmetic are pinned there against Python.

const NONE_FROM = 2 ** 31 - 1; // a person without `life` is alive in no year
const NONE_TO = -(2 ** 31);

/** The people in typed arrays, in file order (k = the index in doc.people and in the names of ui/lenses.js
 *  namesFrom): from, to, cell, kind, approx (1 = dates by decade or century); `dated` = how many have a `life`,
 *  `kinds` = the number of categories. */
export function pack(people, kinds = 1 + Math.max(0, ...people.map((p) => p.kind))) {
  const n = people.length;
  const P = { n, kinds, dated: 0, from: new Int32Array(n), to: new Int32Array(n), cell: new Int32Array(n), kind: new Uint8Array(n),
    approx: new Uint8Array(n) };
  people.forEach((p, k) => {
    P.cell[k] = p.cell;
    P.kind[k] = p.kind;
    P.approx[k] = p.approx ? 1 : 0;
    P.from[k] = p.life ? p.life[0] : NONE_FROM;
    P.to[k] = p.life ? p.life[1] : NONE_TO;
    if (p.life) P.dated++;
  });
  return P;
}

/** A person (from personajes.json) alive in year y: born then or before, and dead then or after. */
export const alive = (p, y) => !!p.life && p.life[0] <= y && y <= p.life[1];

/** keep(k) for yearLayer: person k of `P` alive in year y. */
export const aliveIn = (P, y) => (k) => P.from[k] <= y && y <= P.to[k];

/** The earliest year of life in the data and the last (the download year, timeline.until). */
export function range(P, until) {
  let min = until;
  for (let k = 0; k < P.n; k++) if (P.from[k] < min) min = P.from[k];
  return { min, max: until };
}

/** The two lenses' per-hex data for the people that keep(k) keeps: `count` (people per hex, null where nobody is,
 *  so the map greys a hex with nobody alive instead of giving it the colour of one person), `kind` (the category with
 *  most of them, a tie going to the lowest index as Python's dominant(), null where nobody is), `labels` (their
 *  indices, in file order, so most famous first), `alive` (how many in all) and `approx` (how many of them by a
 *  decade or a century). `n` is the number of hexes. */
export function yearLayer(P, n, keep) {
  const count = new Array(n).fill(null);
  const kind = new Array(n).fill(null);
  const labels = new Array(n).fill(null);
  const per = new Map(); // cell → people per category
  let total = 0, approx = 0;
  for (let k = 0; k < P.n; k++) {
    if (!keep(k)) continue;
    const c = P.cell[k];
    count[c] = (count[c] || 0) + 1;
    approx += P.approx[k];
    (labels[c] ||= []).push(k);
    let a = per.get(c);
    if (!a) per.set(c, (a = new Int32Array(P.kinds)));
    a[P.kind[k]]++;
    total++;
  }
  for (const [c, a] of per) {
    let best = 0;
    for (let i = 1; i < a.length; i++) if (a[i] > a[best]) best = i;
    kind[c] = best;
  }
  return { count, kind, labels, alive: total, approx };
}

const floorDiv = (a, b) => Math.floor(a / b);

/** People alive at some time in each decade from min's to max's (decades of astronomical years: -670…-661, …,
 *  2020…2029): {base, counts}, counts[i] for the decade starting at base + 10 i. A sweep over a difference array. */
export function perDecade(P, min, max) {
  const b0 = floorDiv(min, 10);
  const bins = floorDiv(max, 10) - b0 + 1;
  const diff = new Int32Array(bins + 1);
  for (let k = 0; k < P.n; k++) {
    const from = Math.max(P.from[k], min), to = Math.min(P.to[k], max);
    if (from > to) continue;
    diff[floorDiv(from, 10) - b0]++;
    diff[floorDiv(to, 10) - b0 + 1]--;
  }
  const counts = new Array(bins);
  let run = 0;
  for (let i = 0; i < bins; i++) counts[i] = run += diff[i];
  return { base: b0 * 10, counts };
}

/** The first `top` people alive in year y, in file order (most sitelinks first): their indices. */
export function famous(P, y, top = 10) {
  const out = [];
  for (let k = 0; k < P.n && out.length < top; k++) if (P.from[k] <= y && y <= P.to[k]) out.push(k);
  return out;
}

// Steps land on round historical years: 1555 → 1560 by decade, 670 BC (-669) → 600 BC (-599) by century. The
// signed historical year has no 0 (… -2, -1 = 1 BC, 1, 2 …): a step that would land on it goes on to the next round
// year, AD 100 after 100 BC by century, 10 BC before AD 10 by decade.
const signed = (y) => (y <= 0 ? y - 1 : y);
const fromSigned = (s) => (s < 0 ? s + 1 : s);
const land = (s, step) => fromSigned(s === 0 ? step : s);
const clamp = (y, min, max) => Math.min(max, Math.max(min, y));

/** The next round year after y (step 10 or 100), within [min, max]. */
export const next = (y, step, min = -Infinity, max = Infinity) =>
  clamp(land(floorDiv(signed(y), step) * step + step, step), min, max);

/** The round year before y (step 10 or 100), within [min, max]. */
export const prev = (y, step, min = -Infinity, max = Infinity) =>
  clamp(land(Math.ceil(signed(y) / step) * step - step, -step), min, max);

/** A year from the URL, as people write it with a sign (-201 = 201 BC, no year 0; urlYear): the astronomical year,
 *  clamped to [min, max]; null for anything else. */
export function parseYear(v, min, max) {
  if (v == null || !/^-?\d{1,6}$/.test(String(v)) || Number(v) === 0) return null;
  return clamp(fromSigned(Number(v)), min, max);
}

/** The URL's spelling of astronomical year y: 1520, or -201 for 201 BC (-200). */
export const urlYear = (y) => String(signed(y));

/** The year as people write it: {n, bc} (0 is 1 BC, -669 is 670 BC). */
export const historical = (y) => (y <= 0 ? { n: 1 - y, bc: true } : { n: y, bc: false });

/** The century of a year: {c, bc} (1401–1500 are the 15th; the 1st century BC is -99…0). */
export function century(y) {
  const { n, bc } = historical(y);
  return { c: floorDiv(n - 1, 100) + 1, bc };
}

const ROMAN = [[1000, "M"], [900, "CM"], [500, "D"], [400, "CD"], [100, "C"], [90, "XC"], [50, "L"], [40, "XL"], [10, "X"],
  [9, "IX"], [5, "V"], [4, "IV"], [1, "I"]];

/** 16 → "XVI". */
export function roman(n) {
  let out = "";
  for (const [v, s] of ROMAN) while (n >= v) { out += s; n -= v; }
  return out;
}

/** 1st, 2nd, 3rd, 4th… 11th, 12th, 13th, 21st. */
export const ordinal = (n) => `${n}${n % 100 >= 10 && n % 100 <= 20 ? "th" : { 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th"}`;
