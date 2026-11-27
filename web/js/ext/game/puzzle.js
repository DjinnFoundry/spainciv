// "Adivina el hexágono" / "Guess the hex", without the DOM: the game's view of the data, the day's hex, its clues,
// distances, points, the share text and the saved progress. ext/game/index.js draws it; tests/test_game_js.py runs it
// in node and measures how far each clue narrows the answer.
//
// Everyone gets the same hex on the same (local) day. The pool is every land hex with things of its own: named
// things of MIN_KINDS kinds or more (a fiesta, a castle, a museum, a native among the FAME most famous, a World
// Heritage site, a power plant, a small denomination of origin, a city of the map…; see gameData), one of them
// other than its most famous native. It is shuffled once with a fixed seed; day n takes the pool's n-th hex, so no
// hex repeats until the pool runs out. Rebuilding the data may change the pool, and so the hexes of the days to come;
// a saved game remembers its hex and starts afresh when today's is another.
import { t } from "../../i18n.js";
import { int, dollars } from "../../format.js";
import { formatLensValue } from "../../ui/lenses.js";

export const EPOCH = Date.UTC(2026, 10, 27); // day 1
export const MAX_GUESSES = 6;
export const HIT_KM = 25; // a guess this close to the hex's centre wins
export const ZERO_KM = 600; // a guess this far or farther scores nothing
export const CLUE_COST = 10; // points per clue after the first
export const FAME = 3000; // a native is notable among the FAME most famous (personajes.json lists people by fame)
export const DISTINCT = 10; // a named thing is distinctive when its name, as shown, is on DISTINCT land hexes or fewer
export const MIN_KINDS = 2; // a hex enters the pool with distinctive things of this many kinds
export const MIN_FIRST = 20; // the first clue (area and sea) fits at least this many land hexes: it never gives the answer
export const RIVER_KM = 400; // the rivers a clue names: at least this long across Spain's land on the map
const SEED = 431; // day 1, the launch day, is Guadix (Granada); re-picked when the pool changed with the readable clues

/** The puzzle number of a date's local calendar day: 1 on 27 November 2026. */
export function dayNumber(date = new Date()) {
  return Math.floor((Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) - EPOCH) / 864e5) + 1;
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

/** The hex of puzzle `day` (`order`, shuffled(pool), can be passed to look up many days). */
export function dailyCell(pool, day, order = shuffled(pool)) {
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

const lonLat = (grid, proj, i) => proj.inverse(grid.cx(i), grid.cy(i));

/** Km between the centres of two hexes, on the ground (so a guess in the Canary inset is measured from the islands). */
export function cellKm(grid, proj, a, b) {
  return a === b ? 0 : haversineKm(lonLat(grid, proj, a), lonLat(grid, proj, b));
}

const ARROWS = ["→", "↗", "↑", "↖", "←", "↙", "↓", "↘"];
/** Which way the hex lies from a guess on the map (map y runs down): one of eight arrows, "" on the hex itself. */
export function arrow(grid, from, to) {
  const dx = grid.cx(to) - grid.cx(from), dy = grid.cy(from) - grid.cy(to);
  if (!dx && !dy) return "";
  return ARROWS[((Math.round(Math.atan2(dy, dx) / (Math.PI / 4)) % 8) + 8) % 8];
}

export const COMPASS = ["n", "ne", "e", "se", "s", "sw", "w", "nw"];
/** The compass point (one of COMPASS) of `to` seen from `from`, both [lon, lat], on the ground. */
export function compass([lon1, lat1], [lon2, lat2]) {
  const east = (lon2 - lon1) * Math.cos(((lat1 + lat2) / 2) * RAD), north = lat2 - lat1;
  return COMPASS[((Math.round(Math.atan2(east, north) / (Math.PI / 4)) % 8) + 8) % 8];
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

// --- place names --------------------------------------------------------------------------------------------------

/** A function that hides place names in a text: every municipality, province and city name of four letters or more,
 *  and `own` (the answer's municipality and province) whatever its length, whole words only, become "…". A hyphen
 *  and a space count as the same ("Castro-Urdiales", "Castro Urdiales"). A name that is more place than anything
 *  else ("Montes de Toledo", "Miel de Granada") comes back empty, so no clue shows it: what is left would say
 *  nothing. `readable` turns the "…" into prose for the reader. */
export function placeMasker(names, own = []) {
  const fold = (s) => s.toLowerCase().replace(/[\s-]+/g, " ");
  const parts = new Set();
  let most = 0; // the most words in a name
  const add = (n, min) => String(n || "").split("/").map((s) => s.trim()).filter((s) => s.length >= min).forEach((s) => {
    parts.add(fold(s));
    most = Math.max(most, s.match(WORD).length);
  });
  names.forEach((n) => add(n, 4));
  own.forEach((n) => add(n, 1));
  if (!parts.size) return (s) => s;
  // Whole words: from each word, the longest run of words that is a name (a list of ~8,000 names is far faster as
  // a set than as one regular expression).
  return (s) => {
    const words = [...s.matchAll(WORD)].map((m) => [m.index, m.index + m[0].length]);
    let out = "", from = 0, hidden = 0;
    for (let i = 0; i < words.length; i++) {
      for (let j = Math.min(words.length, i + most) - 1; j >= i; j--) {
        if (!parts.has(fold(s.slice(words[i][0], words[j][1])))) continue;
        out += s.slice(from, words[i][0]) + "…";
        for (let k = i; k <= j; k++) hidden += words[k][1] - words[k][0];
        from = words[j][1];
        i = j;
        break;
      }
    }
    const bracketed = [...s.matchAll(/\([^)]*\)/g)].map((m) => [m.index, m.index + m[0].length]);
    const outside = ([a]) => !bracketed.some(([x, y]) => a >= x && a < y); // "(DOP)" is not part of the name
    const letters = words.filter(outside).reduce((n, [a, b]) => n + b - a, 0);
    return hidden * 2 > letters ? "" : out + s.slice(from);
  };
}
const WORD = /[\p{L}\p{N}]+/gu;

/** A masked name as prose: each "…" goes with the little word that tied it to the rest ("El Cascamorras de … y …"
 *  → "El Cascamorras", "Festival de la Manzana, …" → "Festival de la Manzana"). */
export function readable(s) {
  return String(s)
    .replace(/(?:,\s*|\s+(?:de|del|dels|des|do|da|dos|das|y|i|e|en|a|al)\s+|\s+)?(?:[ld]['’])?…/giu, "")
    .replace(/^\s*(?:de|del|y|i|e|en)\s+/iu, "")
    .replace(/\s+([,.;)])/g, "$1").replace(/\(\s*\)/g, "").replace(/\s{2,}/g, " ").trim();
}

// Compares two arrays of numbers element by element, for sorting by several keys.
const lex = (a, b) => { for (let k = 0; k < a.length; k++) if (a[k] !== b[k]) return a[k] - b[k]; return 0; };

// A function of a hex worked out once per hex.
const memo = (f) => { const m = new Map(); return (c) => (m.has(c) ? m.get(c) : m.set(c, f(c)).get(c)); };

// The name of a hex's province ("" off the map).
const provinceOf = (raw, c) => raw.states[raw.owner[c]]?.name || "";

// A name says something once its place names are hidden: four letters in a row outside brackets.
const telling = (s) => /\p{L}{4}/u.test(String(s).replace(/\([^)]*\)/g, ""));

// --- the game's view of the data ----------------------------------------------------------------------------------

// The named things a hex can hold, by source, in the order a clue prefers them (between equally distinctive
// names): from a file or from a lens that lists names in the hex. `notable: false` sources name a clue but do not
// make a hex notable (a regional dish is the whole province's).
export const SOURCES = [
  { id: "wonders" },
  { id: "fiestas", lens: "fiestas" },
  { id: "castles", lens: "castles" },
  { id: "food", lens: "food" },
  { id: "museums", lens: "museums" },
  { id: "people" }, // natives besides the most famous, who waits for the last clue
  { id: "works" }, // power plants and mines (resources.json)
  { id: "airports" },
  { id: "ports" },
  { id: "bullrings", lens: "bullrings" },
  { id: "beaches", lens: "beaches" },
  { id: "dishes", lens: "dishes", notable: false },
];
const PICKS = SOURCES.filter((s) => s.notable !== false).map((s) => s.id);
const COUNTS = ["heritage", "castles", "museums", "bullrings", "beaches", "fiestas"]; // lenses counted in clue 3
const ISLANDS = { PM: "med", GC: "atl", TF: "atl", CE: "africa", ML: "africa" }; // provinces off the mainland
const SEA_KM = [[0, "coast"], [30, "30"], [100, "100"], [200, "200"], [Infinity, "far"]];
const CITY_KM = 15; // closer than this a hex is "in" its city

/**
 * Everything the pool and the clues read, worked out once. ctx: {w (world.js prepareWorld), proj (geo.js
 * mapProjection), lenses: Map<id, lens>, names (every municipality, province and city name, to hide), cities,
 * people (personajes.json people, in fame order), wonders (wonders.json wonders), resources (resources.json),
 * infrastructure (infrastructure.json)}; the files may be missing (null), their things then are too.
 */
export function gameData({ w, proj, lenses, names = [], cities = [], people = null, wonders = null, resources = null, infrastructure = null }) {
  const { raw, grid, water } = w;
  const isLand = (c) => c >= 0 && raw.owner[c] >= 0 && raw.county[c] >= 0;
  const land = [];
  for (let i = 0; i < grid.size; i++) if (isLand(i)) land.push(i);
  const mask = placeMasker(names);

  // Named things: index[source] = Map<shown name, Set<cell>> and byCell = Map<cell, [{src, key, show}]>, where key
  // is the name with every place name hidden (what the clue shows and the measure compares).
  const index = new Map(SOURCES.map((s) => [s.id, new Map()])), byCell = new Map();
  const put = (src, cell, key, show = key, extra = null) => {
    if (!isLand(cell) || !telling(key)) return;
    const m = index.get(src);
    if (!m.has(key)) m.set(key, new Set());
    if (m.get(key).has(cell)) return;
    m.get(key).add(cell);
    if (!byCell.has(cell)) byCell.set(cell, []);
    byCell.get(cell).push({ src, key, show, ...extra });
  };
  for (const s of SOURCES) {
    const lens = s.lens && lenses.get(s.lens);
    if (!lens?.labels) continue;
    const shown = lens.names.map((n) => { const k = mask(n); return telling(k) ? k : null; });
    land.forEach((c) => (lens.labels[c] || []).forEach((k) => shown[k] && put(s.id, c, shown[k])));
  }
  (wonders || []).forEach((x) => (x.cells || [x.cell]).forEach((c) => put("wonders", c, mask(x.short || x.name))));
  const typeName = new Map((resources?.types || []).map((x) => [x.id, x.name]));
  (resources?.items || []).forEach((x) => put("works", x.cell, mask(`${typeName.get(x.type) || ""} · ${x.name}`)));
  (infrastructure?.ports || []).forEach((x) => put("ports", x.cell, mask(x.name)));
  (infrastructure?.airports || []).forEach((x) => put("airports", x.cell, mask(x.name)));
  (people || []).forEach((p, rank) => put("people", p.cell, p.name, p.note ? `${p.name} (${p.note})` : p.name, { rank }));

  const count = (src, key) => index.get(src).get(key)?.size || 0;
  const has = (src, cell, key) => !!index.get(src).get(key)?.has(cell);
  const top = (c) => (byCell.get(c) || []).find((x) => x.src === "people") || null; // people went in by fame
  const distinctive = (x) => (x.src === "people" ? x.rank < FAME : count(x.src, x.key) <= DISTINCT);
  /** The hex's named things a clue can show, best first: the distinctive ones, whole names before ones with a place
   *  hidden, by source, rarest first; one of each source before any second. Its most famous native is kept back for
   *  the last clue, and a common name with a place hidden is left out. */
  const picks = (c) => {
    const best = top(c);
    const rank = (x) => [distinctive(x) ? 0 : 1, x.key.includes("…") ? 1 : 0, PICKS.indexOf(x.src), count(x.src, x.key)];
    const all = (byCell.get(c) || []).filter((x) => PICKS.includes(x.src) && x !== best && (distinctive(x) || !x.key.includes("…")))
      .sort((a, b) => lex(rank(a), rank(b))); // "Castillo de …" on 675 hexes says less than the castle count
    const seen = new Set(), first = all.filter((x) => !seen.has(x.src) && seen.add(x.src));
    return [...first, ...all.filter((x) => !first.includes(x))];
  };
  /** The kinds of distinctive things in the hex (a source each, and "city" for a city of the map). */
  const kinds = (c) => {
    const k = new Set((byCell.get(c) || []).filter((x) => PICKS.includes(x.src) && distinctive(x)).map((x) => x.src));
    if (w.cityByCell?.has(c)) k.add("city");
    return k;
  };
  // Where: the mainland split in nine by its extent, the islands and North Africa by their provinces.
  const at = memo((c) => lonLat(grid, proj, c));
  const abbr = (c) => raw.states[raw.owner[c]]?.abbr;
  const box = [Infinity, Infinity, -Infinity, -Infinity];
  land.forEach((c) => {
    if (ISLANDS[abbr(c)]) return;
    const [lon, lat] = at(c);
    box[0] = Math.min(box[0], lon); box[1] = Math.min(box[1], lat); box[2] = Math.max(box[2], lon); box[3] = Math.max(box[3], lat);
  });
  const third = (v, lo, hi) => Math.min(2, Math.max(0, Math.floor((3 * (v - lo)) / (hi - lo))));
  const zone = (c) => {
    if (ISLANDS[abbr(c)]) return ISLANDS[abbr(c)];
    const [lon, lat] = at(c);
    return [["nw", "n", "ne"], ["w", "c", "e"], ["sw", "s", "se"]][2 - third(lat, box[1], box[3])][third(lon, box[0], box[2])];
  };

  // The sea: hex steps over land from the nearest land hex beside the sea (ocean or coastal water, not a lake).
  const steps = new Int32Array(grid.size).fill(-1), queue = [];
  for (let i = 0; i < grid.size; i++) {
    if (water[i]) continue;
    for (let d = 0; d < 6; d++) {
      const j = grid.neighbour(i, d);
      if (j >= 0 && (water[j] === 1 || water[j] === 2)) { steps[i] = 0; queue.push(i); break; }
    }
  }
  for (let q = 0; q < queue.length; q++) {
    for (let d = 0; d < 6; d++) {
      const j = grid.neighbour(queue[q], d);
      if (j >= 0 && !water[j] && steps[j] < 0) { steps[j] = steps[queue[q]] + 1; queue.push(j); }
    }
  }
  const sea = (c) => SEA_KM.find(([km]) => steps[c] * grid.W <= km)[1];

  // The great rivers: named lines with at least RIVER_KM across Spain's land (map units are km).
  const segs = [], spanish = new Map();
  for (const r of raw.rivers || []) {
    for (let k = 0; k + 3 < r.pts.length; k += 2) {
      const [x1, y1, x2, y2] = r.pts.slice(k, k + 4);
      segs.push({ name: r.name, x1, y1, x2, y2 });
      if (isLand(grid.cellAt((x1 + x2) / 2, (y1 + y2) / 2))) spanish.set(r.name, (spanish.get(r.name) || 0) + Math.hypot(x2 - x1, y2 - y1));
    }
  }
  const great = segs.filter((s) => (spanish.get(s.name) || 0) >= RIVER_KM);
  const river = memo((c) => {
    const x = grid.cx(c), y = grid.cy(c);
    let best = null;
    for (const s of great) {
      const dx = s.x2 - s.x1, dy = s.y2 - s.y1, len2 = dx * dx + dy * dy;
      const u = len2 ? Math.max(0, Math.min(1, ((x - s.x1) * dx + (y - s.y1) * dy) / len2)) : 0;
      const km = Math.hypot(x - s.x1 - u * dx, y - s.y1 - u * dy);
      if (!best || km < best.km) best = { name: s.name, km };
    }
    if (!best || best.km > 30) return null;
    return { name: best.name, by: best.km <= 12 ? "on" : "near" };
  });

  // The cities of the map, nearest first, with the compass point of the hex as seen from each.
  const places = (cities || []).filter((x) => x.cell >= 0);
  const near = memo((c) => places.map((x) => ({ city: x, km: cellKm(grid, proj, x.cell, c), dir: compass(at(x.cell), at(c)) }))
    .sort((a, b) => a.km - b.km).slice(0, 4));

  // The pool: notable hexes whose first clue leaves enough of Spain open.
  const areas = new Map(), area = (c) => `${zone(c)} ${sea(c)}`;
  land.forEach((c) => areas.set(area(c), (areas.get(area(c)) || 0) + 1));
  const firstFits = (c) => areas.get(area(c)) || 0; // the land hexes that share the first clue's area and sea
  const pool = land.filter((c) => firstFits(c) >= MIN_FIRST && kinds(c).size >= MIN_KINDS && picks(c).some(distinctive));

  return { w, proj, lenses, land, pool, mask, count, has, top, picks, kinds, zone, sea, firstFits, river, near };
}

// --- clues --------------------------------------------------------------------------------------------------------

// Every fact is {label, value, same(cell)}: `same` says whether another hex fits what the fact shows, as a reader
// would check it (the same category, the same name, a number within 10 %). Numbers carry `num: true`: a reader can
// check one against a lens, but a number alone points nowhere on the map.
const fact = (label, value, same, num = false) => {
  const shown = typeof value === "string" && value.includes("…") ? readable(value) : value;
  return shown == null || shown === "" ? null : { label, value: shown, same, num };
};
const sameBy = (key, cell) => { const k = key(cell); return (c) => key(c) === k; };

// A lens value as the map's tooltip writes it, except money in full ("12.512 €", "1.830 €/m²").
function lensFact(lens, cell, mask = (s) => s) {
  const v = lens?.values?.[cell];
  if (v == null) return null;
  if (lens.format === "category") return fact(lens.name, mask(formatLensValue(lens, v)), (c) => lens.values[c] === v);
  const perM2 = /\/\s*m²$/.test(lens.unit || "") ? "/m²" : "";
  const value = lens.format === "eur" || lens.format === "usd" ? dollars(v) + perM2 : formatLensValue(lens, v);
  return fact(lens.name, value, (c) => Math.abs((lens.values[c] ?? NaN) - v) <= 0.1 * Math.abs(v), true);
}

// A named thing of the hex as a clue: its label by source ("Una fiesta"), its name with the place names hidden.
const thingFact = (g, x, own) => x && fact(t(`game.k.${x.src}`), own(x.show), (c) => g.has(x.src, c, x.key));

// The hex seen from its nearest city of the map: named, or "a city" while the clues are still vague. A city named
// after the answer's municipality is skipped and one named after its province is "the province's capital".
function cityFact(g, cell, named) {
  const own = ownMasker(g, cell);
  const province = placeMasker([], [provinceOf(g.w.raw, cell)]);
  const unhidden = (x) => own(x.city.name) === x.city.name; // not named after the answer's municipality or province
  const o = named ? g.near(cell).find((x) => unhidden(x) || province(x.city.name) !== x.city.name) : g.near(cell)[0];
  if (!o) return null;
  let city = t("game.v.aCity");
  if (named) city = unhidden(o) ? o.city.name : t("game.v.capital");
  const value = o.km < CITY_KM ? t("game.v.inCity", { city, km: CITY_KM }) : t("game.v.fromCity", { km: int(Math.round(o.km / 10) * 10), dir: t(`game.dir.${o.dir}`), city });
  const fits = (p) => p && (o.km < CITY_KM ? p.km < CITY_KM : p.km >= CITY_KM && p.dir === o.dir && Math.abs(p.km - o.km) <= 10);
  return fact(t("game.f.position"), value, named ? (c) => fits(g.near(c).find((x) => x.city === o.city)) : (c) => fits(g.near(c)[0]));
}

// The answer's own municipality and province, hidden whatever their length (cached per hex).
const owns = new WeakMap();
function ownMasker(g, cell) {
  if (!owns.has(g)) owns.set(g, new Map());
  const m = owns.get(g), raw = g.w.raw;
  if (!m.has(cell)) m.set(cell, placeMasker([], [raw.counties[raw.county[cell]]?.name, provinceOf(raw, cell)]));
  return m.get(cell);
}

// One of the names a lens lists in the hex (a denomination, a dish) not shown yet: the hex's own pick among them, so
// neighbouring days do not all show the first in the list.
function listed(g, src, cell, shown) {
  const lens = g.lenses.get(SOURCES.find((s) => s.id === src).lens);
  const keys = [...new Set((lens?.labels?.[cell] || []).map((k) => g.mask(lens.names[k])))].filter((k) => telling(k) && !shown.has(k));
  const key = keys[cell % keys.length];
  return key && { src, key, show: key };
}

// The clues, vaguest first; each make(g, cell, own, picks) returns facts (null ones are left out).
export const CLUES = [
  // Where in Spain, how far from the sea, how high (the pool's MIN_FIRST rule reads the same area and sea).
  ["where", (g, cell) => {
    const elev = g.w.raw.elev;
    return [
      fact(t("game.f.zone"), t(`game.zone.${g.zone(cell)}`), sameBy(g.zone, cell)),
      fact(t("game.f.sea"), t(`game.sea.${g.sea(cell)}`), sameBy(g.sea, cell)),
      fact(t("game.f.elev"), `${int(elev[cell])} m`, (c) => Math.abs(elev[c] - elev[cell]) <= Math.max(50, 0.1 * Math.abs(elev[cell])), true),
    ];
  }],
  // The land and who lives there: relief, a great river, the language, the people of antiquity, how many and how
  // well off.
  ["people", (g, cell, own) => {
    const { w } = g, r = g.river(cell);
    const river = (c) => { const x = g.river(c); return x && `${x.name}|${x.by}`; };
    return [
      fact(t("game.f.relief"), w.tables.relief.find((x) => x.id === w.relief[cell])?.name, sameBy((c) => w.relief[c], cell)),
      r && fact(t("game.f.river"), t(`game.river.${r.by}`, { river: own(r.name) }), sameBy(river, cell)),
      lensFact(g.lenses.get("languages"), cell, (s) => own(g.mask(s))), // a category can name a place ("Euskera: zona mixta de Navarra")
      lensFact(g.lenses.get("peoples"), cell, own),
      lensFact(g.lenses.get("density"), cell),
      lensFact(g.lenses.get("income"), cell),
    ];
  }],
  // Its most distinctive named thing and what the heritage lenses count there (only what there is).
  ["thing", (g, cell, own, picks) => {
    const counted = COUNTS.map((id) => g.lenses.get(id)).filter((l) => l?.unit && l.values[cell] > 0);
    return [
      thingFact(g, picks[0], own),
      ...counted.map((l) => fact(l.unit[0].toUpperCase() + l.unit.slice(1), int(l.values[cell]), (c) => l.values[c] > 0)),
      !counted.length && fact(t("game.f.heritage"), t("game.v.nothing"), (c) => COUNTS.every((id) => !(g.lenses.get(id)?.values[c] > 0))),
    ];
  }],
  // A second named thing and how far the hex is from a city of the map, without naming it.
  ["near", (g, cell, own, picks) => [thingFact(g, picks[1], own), cityFact(g, cell, false)]],
  // The city named, a third thing and a dish of the province.
  ["city", (g, cell, own, picks) => [cityFact(g, cell, true), thingFact(g, picks[2], own), thingFact(g, listed(g, "dishes", cell, new Set()), own)]],
  // The giveaway: the province's initial, the most famous person born there and a denomination of origin.
  ["last", (g, cell, own, picks) => {
    const province = provinceOf(g.w.raw, cell);
    const initial = (c) => provinceOf(g.w.raw, c)[0]?.toUpperCase();
    const person = g.top(cell);
    return [
      province && fact(t("game.f.initial"), `«${initial(cell)}»`, sameBy(initial, cell)),
      person && fact(t("game.f.person"), own(person.show), (c) => g.top(c)?.key === person.key),
      thingFact(g, listed(g, "food", cell, new Set(picks.slice(0, 3).map((x) => x.key))), own),
    ];
  }],
].map(([id, make]) => ({ id, make }));

/**
 * The day's clues for `cell`: [{id, title, facts: [{label, value, same, num}]}], in the order they are revealed.
 * `g` is gameData(); every fact holds for the answer itself (fact.same(cell)).
 */
export function buildClues(g, cell) {
  const own = ownMasker(g, cell);
  const picks = g.picks(cell).filter((x) => own(x.show) === x.show); // a thing named after the answer would give it away
  return CLUES.map(({ id, make }) => ({
    id,
    title: t(`game.clue.${id}`),
    facts: make(g, cell, own, picks).filter(Boolean),
  }));
}

/**
 * How many land hexes still fit the clues after each one is shown: [n after clue 1, …, n after the last] (a reader
 * does not know the pool, so any hex of Spain is a candidate). With `numbers: false` a number does not narrow (a
 * reader cannot search the map for "42.8 years"); with `numbers: true` it does, within 10 %.
 */
export function candidates(g, cell, { numbers = false } = {}) {
  let left = g.land;
  return buildClues(g, cell).map(({ facts }) => {
    const use = facts.filter((f) => numbers || !f.num);
    left = left.filter((c) => use.every((f) => f.same(c)));
    return left.length;
  });
}

// --- saved progress -----------------------------------------------------------------------------------------------

/** Today's saved game, if it is for this puzzle: the same day and the same hex (a game saved before the data or the
 *  pick changed is for another hex and starts afresh). */
export const savedGame = (saved, day, cell) => (saved?.today?.day === day && saved.today.cell === cell ? saved.today : null);

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
