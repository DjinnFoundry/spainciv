// "Adivina el hexágono" / "Guess the hex", without the DOM: the day's hex, its clues, distances, points, the
// share text and the saved progress. ext/game/index.js draws it; tests/test_game_js.py runs it in node.
//
// Everyone gets the same hex on the same (local) day: the pool is every land hex with a municipality and at least
// POOL_DENSITY residents per km² (lens `density`), in cell order, shuffled once with a fixed seed; day n takes the
// pool's n-th hex, so no hex repeats until the pool runs out (about 2,300 days on Spain's data). Rebuilding the data
// may change the pool, and so the hexes of the days to come.
import { t } from "../../i18n.js";
import { int, dollars } from "../../format.js";
import { formatLensValue } from "../../ui/lenses.js";

export const EPOCH = Date.UTC(2026, 10, 27); // day 1
export const POOL_DENSITY = 25;
export const MAX_GUESSES = 6;
export const HIT_KM = 25; // a guess this close to the hex's centre wins
export const ZERO_KM = 600; // a guess this far or farther scores nothing
export const CLUE_COST = 10; // points per clue after the first
const SEED = 0x5ca1ab1e;

/** The puzzle number of a date's local calendar day: 1 on 27 November 2026. */
export function dayNumber(date = new Date()) {
  return Math.floor((Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) - EPOCH) / 864e5) + 1;
}

/** The hexes a puzzle can be: land with a municipality and POOL_DENSITY people per km² or more, in cell order. */
export function puzzlePool(raw, density) {
  const out = [];
  for (let i = 0; i < raw.owner.length; i++) {
    if (raw.owner[i] >= 0 && raw.county[i] >= 0 && density.values[i] >= POOL_DENSITY) out.push(i);
  }
  return out;
}

// mulberry32: a small seeded generator, the same in every browser.
function random(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let x = Math.imul(a ^ (a >>> 15), 1 | a);
    x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x;
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}

/** The pool in the fixed shuffled order (Fisher–Yates with SEED). */
export function shuffled(pool) {
  const out = [...pool], rnd = random(SEED);
  for (let k = out.length - 1; k > 0; k--) {
    const j = Math.floor(rnd() * (k + 1));
    [out[k], out[j]] = [out[j], out[k]];
  }
  return out;
}

/** The hex of puzzle `day`. */
export function dailyCell(pool, day) {
  const order = shuffled(pool);
  return order[(((day - 1) % order.length) + order.length) % order.length];
}

// --- distance and direction ---------------------------------------------------------------------------------------

const RAD = Math.PI / 180;
const EARTH_KM = 6371.0088;

/** Great-circle km between two [lon, lat]. */
export function haversineKm([lon1, lat1], [lon2, lat2]) {
  const a = Math.sin(((lat2 - lat1) * RAD) / 2) ** 2 + Math.cos(lat1 * RAD) * Math.cos(lat2 * RAD) * Math.sin(((lon2 - lon1) * RAD) / 2) ** 2;
  return 2 * EARTH_KM * Math.asin(Math.min(1, Math.sqrt(a)));
}

/** Km between the centres of two hexes, on the ground (so a guess in the Canary inset is measured from the islands). */
export function cellKm(grid, proj, a, b) {
  if (a === b) return 0;
  const ll = (i) => proj.inverse(grid.cx(i), grid.cy(i));
  return haversineKm(ll(a), ll(b));
}

const ARROWS = ["→", "↗", "↑", "↖", "←", "↙", "↓", "↘"];
/** Which way the hex lies from a guess on the map (map y runs down): one of eight arrows, "" on the hex itself. */
export function arrow(grid, from, to) {
  const dx = grid.cx(to) - grid.cx(from), dy = grid.cy(from) - grid.cy(to);
  if (!dx && !dy) return "";
  return ARROWS[((Math.round(Math.atan2(dy, dx) / (Math.PI / 4)) % 8) + 8) % 8];
}

// --- points and share text ----------------------------------------------------------------------------------------

/** 100 within HIT_KM, falling evenly to 0 at ZERO_KM. */
export const distancePoints = (km) => Math.round(Math.max(0, Math.min(100, (100 * (ZERO_KM - km)) / (ZERO_KM - HIT_KM))));

/** The game's points: the best guess's distance points, less CLUE_COST for every clue after the first. */
export const score = (bestKm, clues) => Math.max(0, distancePoints(bestKm) - CLUE_COST * Math.max(0, clues - 1));

/** The square of one guess in the share text. */
export const square = (km) => (km <= HIT_KM ? "🟩" : km <= 100 ? "🟨" : km <= 300 ? "🟧" : "🟥");

/** What a finished game shares: the puzzle number, tries, points, a square per guess and the clues used, no place. */
export function shareText({ day, kms, won, clues, url }) {
  const points = score(Math.min(...kms), clues);
  return [
    t("game.share.head", { n: day, tries: won ? kms.length : "X", max: MAX_GUESSES, points: t("game.points", { n: points }) }),
    kms.map(square).join(""),
    t("game.share.clues", { n: clues, max: CLUES.length }),
    url,
  ].join("\n");
}

// --- clues --------------------------------------------------------------------------------------------------------

// A lens value as the map's tooltip writes it, except money in full ("12.512 €", "1.830 €/m²").
const lensFact = (lens, i) => {
  const v = lens?.values?.[i];
  if (v == null) return null;
  const perM2 = /\/\s*m²$/.test(lens.unit || "") ? "/m²" : "";
  return { label: lens.name, value: lens.format === "eur" || lens.format === "usd" ? dollars(v) + perM2 : formatLensValue(lens, v) };
};
// A count of things in the hex, named by the lens's unit: "Castillos: 2".
const countFact = (lens, i) => {
  const v = lens?.values?.[i];
  return v == null || !lens.unit ? null : { label: lens.unit[0].toUpperCase() + lens.unit.slice(1), value: int(v) };
};
// One of the names a lens lists in the hex, with the place names hidden: the hex's own pick (so neighbouring days do
// not all show the first in the list) among those that still say something once hidden.
function named(lens, i, mask) {
  const all = (lens?.labels?.[i] || []).map((k) => mask(lens.names[k]));
  const telling = all.filter((s) => /\p{L}{4}/u.test(s.replace(/\([^)]*\)/g, "")));
  return telling.length ? telling[i % telling.length] : null;
}

/** A function that hides place names in a text: every municipality, province and city name of four letters or more,
 *  and `own` (the answer's municipality and province) whatever its length, whole words only, become "…". */
export function placeMasker(names, own = []) {
  const parts = new Set();
  const add = (n, min) => String(n || "").split("/").map((s) => s.trim()).filter((s) => s.length >= min).forEach((s) => parts.add(s));
  names.forEach((n) => add(n, 4));
  own.forEach((n) => add(n, 1));
  if (!parts.size) return (s) => s;
  const alts = [...parts].sort((a, b) => b.length - a.length).map((s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const re = new RegExp(`(?<![\\p{L}\\p{N}])(?:${alts.join("|")})(?![\\p{L}\\p{N}])`, "giu");
  return (s) => s.replace(re, "…");
}

// The clues, vaguest first. Each is {id, facts: [{label, value}]}; facts without data are left out.
export const CLUES = [
  // The ground: land cover, relief, height and whether the sea is next to it.
  ["terrain", ({ w, cell }) => {
    const { raw, grid, tables, water } = w;
    const name = (table, id) => table.find((r) => r.id === id)?.name;
    let coast = false;
    for (let d = 0; d < 6; d++) {
      const j = grid.neighbour(cell, d);
      if (j >= 0 && (water[j] === 1 || water[j] === 2)) coast = true; // ocean or coastal water, not a lake
    }
    return [
      { label: t("game.f.cover"), value: w.cover[cell] > 0 ? name(tables.cover, w.cover[cell]) : null },
      { label: t("game.f.relief"), value: name(tables.relief, w.relief[cell]) },
      { label: t("game.f.elev"), value: `${int(raw.elev[cell])} m` },
      { label: t("game.f.sea"), value: t(coast ? "game.v.coast" : "game.v.inland") },
    ];
  }],
  ["people", ({ lenses, cell }) => ["density", "age", "life_expectancy"].map((id) => lensFact(lenses.get(id), cell))],
  ["money", ({ lenses, cell }) => ["income", "home", "foreign_born"].map((id) => lensFact(lenses.get(id), cell))],
  // A category can name a place too ("Euskera: zona mixta de Navarra").
  ["roots", ({ lenses, cell, mask }) => ["languages", "peoples"].map((id) => lensFact(lenses.get(id), cell)).map((f) => f && { ...f, value: mask(f.value) })],
  ["heritage", ({ lenses, cell, mask }) => {
    const fiesta = named(lenses.get("fiestas"), cell, mask);
    return [
      ...["heritage", "castles", "museums", "beaches", "fiestas"].map((id) => countFact(lenses.get(id), cell)),
      fiesta && { label: t("game.f.fiesta"), value: fiesta },
    ];
  }],
  // The giveaway: the province's initial, the most famous person born there, a food denomination and a dish.
  ["last", ({ w, lenses, cell, people, mask }) => {
    const province = w.raw.states[w.raw.owner[cell]]?.name || "";
    const person = people?.find((p) => p.cell === cell);
    const food = named(lenses.get("food"), cell, mask), dish = named(lenses.get("dishes"), cell, mask);
    return [
      province && { label: t("game.f.initial"), value: `«${province[0].toUpperCase()}»` },
      person && { label: t("game.f.person"), value: person.note ? `${person.name} (${person.note})` : person.name },
      food && { label: lenses.get("food").name, value: food },
      dish && { label: lenses.get("dishes").name, value: dish },
    ];
  }],
].map(([id, make]) => ({ id, make }));

/**
 * The day's clues for `cell`: [{id, title, facts: [{label, value}]}], in the order they are revealed.
 * ctx: {w (world.js prepareWorld), lenses: Map<id, lens>, people (personajes.json people, or null), names (every
 * municipality, province and city name, to hide)}.
 */
export function buildClues({ w, lenses, people = null, names = [] }, cell) {
  const raw = w.raw;
  const own = [raw.counties[raw.county[cell]]?.name, raw.states[raw.owner[cell]]?.name];
  const mask = placeMasker(names, own);
  return CLUES.map(({ id, make }) => ({
    id,
    title: t(`game.clue.${id}`),
    facts: make({ w, lenses, cell, people, mask }).filter((f) => f && f.value != null && f.value !== ""),
  }));
}

// --- saved progress -----------------------------------------------------------------------------------------------

export const NO_STATS = { played: 0, won: 0, streak: 0, best: 0, lastDay: 0, lastWin: 0 };

/** Stats after finishing puzzle `day`: a win extends the streak if the last win was the day before. */
export function recordResult(stats, day, won) {
  const s = { ...NO_STATS, ...stats };
  if (s.lastDay === day) return s; // already counted
  const streak = won ? (s.lastWin === day - 1 ? s.streak + 1 : 1) : 0;
  return { played: s.played + 1, won: s.won + (won ? 1 : 0), streak, best: Math.max(s.best, streak), lastDay: day, lastWin: won ? day : s.lastWin };
}

/** The streak as of `today`: it lapses once a day passes without a win. */
export const currentStreak = (stats, today) => (stats && stats.lastWin >= today - 1 ? stats.streak : 0);

/** Where a game stands: {kms, best, won, over, clues} from the answer, the guesses and the clues shown. */
export function standing({ grid, proj, cell, guesses, clues }) {
  const kms = guesses.map((g) => cellKm(grid, proj, g, cell));
  const best = kms.length ? Math.min(...kms) : Infinity;
  const won = best <= HIT_KM;
  return { kms, best, won, over: won || guesses.length >= MAX_GUESSES, clues: Math.min(CLUES.length, Math.max(1, clues)) };
}
