// The province album of «Adivina el hexágono», without the DOM: what the player has collected and how often each
// province comes up. albumPanel.js draws it; tests/test_game_js.py runs it in node.
//
// A win puts the day's hex's province in the album (its INE code, from states.json), with the puzzle day. Provinces
// are grouped by their autonomous community (states.json `community`, from INE table 69962). A province with no hex
// in the pool can never come up and stays out of the counts. The pool is shuffled once and each of its hexes comes
// up once per pool-length cycle of days (puzzle.js), so a province with k hexes in the pool comes up exactly k times
// every pool.length days.
import { t } from "../../i18n.js";
import { MIN_FIRST } from "./puzzle.js";

/** A province that comes up less than once in this many days gets the clock (a UI convention, DECISIONS E84). */
export const LONG_WAIT_DAYS = 100;

/** The album as saved, cleaned: {INE province code: [puzzle day, …]} with known codes only and each list sorted
 *  positive whole days without repeats. Anything else (null, a string, a tampered entry) is dropped. */
export function normalize(album, fipsSet) {
  const out = {};
  if (!album || typeof album !== "object" || Array.isArray(album)) return out;
  for (const [fips, days] of Object.entries(album)) {
    if (!fipsSet.has(fips) || !Array.isArray(days)) continue;
    const ok = [...new Set(days.filter((d) => Number.isInteger(d) && d > 0))].sort((a, b) => a - b);
    if (ok.length) out[fips] = ok;
  }
  return out;
}

/** The album with puzzle `day` won for province `fips` (a new object; a day already there changes nothing). */
export function addWin(album, fips, day) {
  const days = album?.[fips] || [];
  if (days.includes(day)) return { ...album };
  return { ...album, [fips]: [...days, day].sort((a, b) => a - b) };
}

/** How many pool hexes each province has: {fips: n} (provinces without one are absent). */
export function poolByProvince(pool, raw) {
  const out = {};
  for (const c of pool) {
    const fips = raw.states[raw.owner[c]]?.fips;
    if (fips) out[fips] = (out[fips] || 0) + 1;
  }
  return out;
}

/**
 * What the album tab shows. album: normalize()d; states: states.json (world.json's order, with `community`); raw:
 * world.json as prepared; pool and firstFits: gameData()'s; stats: the game's saved stats.
 * Returns {communities: [{code, name, got, total, complete, provinces: [{fips, name, idx, days, hexes, everyDays,
 * slow}]}], got, total, complete, communitiesTotal, outside: [{fips, name, reason, fits, cell}], poolSize, unassigned}.
 * `outside` holds the provinces with no pool hex: reason "first" when even their best hex shares the first clue with
 * fewer than MIN_FIRST land hexes (`fits` of them, from `cell`), "rules" otherwise.
 */
export function albumView({ album, states, raw, pool, firstFits, stats }) {
  const hexes = poolByProvince(pool, raw), poolSize = pool.length;
  const best = new Map(); // province index → its land hex that shares the first clue with the most land hexes
  for (let c = 0; c < raw.owner.length; c++) {
    const o = raw.owner[c];
    if (o < 0 || raw.county[c] < 0) continue;
    const f = firstFits(c);
    if (!best.has(o) || f > best.get(o).fits) best.set(o, { cell: c, fits: f });
  }
  const byCode = new Map(), outside = [];
  states.forEach((s, idx) => {
    const n = hexes[s.fips] || 0;
    if (!n) {
      const b = best.get(idx) || { cell: -1, fits: 0 };
      outside.push({ fips: s.fips, name: s.name, reason: b.fits < MIN_FIRST ? "first" : "rules", fits: b.fits, cell: b.cell });
      return;
    }
    const { code, name } = s.community;
    if (!byCode.has(code)) byCode.set(code, { code, name, provinces: [] });
    const everyDays = Math.round(poolSize / n);
    byCode.get(code).provinces.push({ fips: s.fips, name: s.name, idx, days: album[s.fips] || [], hexes: n, everyDays,
      slow: everyDays > LONG_WAIT_DAYS });
  });
  const communities = [...byCode.values()].sort((a, b) => a.code.localeCompare(b.code)).map((c) => {
    const provinces = c.provinces.sort((a, b) => a.fips.localeCompare(b.fips));
    const got = provinces.filter((p) => p.days.length).length;
    return { ...c, provinces, got, total: provinces.length, complete: got === provinces.length };
  });
  const sum = (f) => communities.reduce((n, c) => n + f(c), 0);
  const days = sum((c) => c.provinces.reduce((n, p) => n + p.days.length, 0));
  outside.sort((a, b) => a.fips.localeCompare(b.fips));
  return {
    communities, outside, poolSize,
    got: sum((c) => c.got), total: sum((c) => c.total),
    complete: communities.filter((c) => c.complete).length, communitiesTotal: communities.length,
    unassigned: Math.max(0, (stats?.won | 0) - days),
  };
}

/** The provinces of a view, community by community. */
export const provincesOf = (view) => view.communities.flatMap((c) => c.provinces);

/** Most missing provinces the share text names. */
export const MISSING_NAMED = 5;

/** What the album shares: the counts, a square per community (🟩 complete, 🟨 started, ⬜ none), the complete
 *  communities, the missing provinces when only a few are, and the game's link. */
export function shareText(view, url) {
  const done = view.communities.filter((c) => c.complete).map((c) => c.name);
  const missing = provincesOf(view).filter((p) => !p.days.length).map((p) => p.name);
  return [
    t("game.album.share.head", { got: view.got, total: view.total }),
    view.communities.map((c) => (c.complete ? "🟩" : c.got ? "🟨" : "⬜")).join(""),
    done.length ? t("game.album.share.complete", { n: done.length, total: view.communitiesTotal, list: done.join(", ") })
      : t("game.album.share.none", { total: view.communitiesTotal }),
    missing.length && missing.length <= MISSING_NAMED ? t("game.album.share.missing", { list: missing.join(", ") }) : null,
    url,
  ].filter((x) => x != null).join("\n");
}
