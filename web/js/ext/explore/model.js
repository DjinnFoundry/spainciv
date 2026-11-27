// The explored land of the fog of war (ext/explore): which land hexes the player has seen, the shares explored of the
// whole country and of each group of regions, and how the set is kept in localStorage. No DOM, no drawing.

export const RADIUS = 1; // a reveal uncovers the hex and its neighbours
const VERSION = 1;

/** The cells within `radius` steps of `cell` (the cell first), on any grid with neighbour(i, d) for d = 0..5. */
export function around(grid, cell, radius = RADIUS) {
  if (!(cell >= 0 && cell < grid.size)) return [];
  const seen = new Set([cell]);
  let ring = [cell];
  for (let r = 0; r < radius; r++) {
    const next = [];
    for (const i of ring) {
      for (let d = 0; d < 6; d++) {
        const j = grid.neighbour(i, d);
        if (j >= 0 && !seen.has(j)) {
          seen.add(j);
          next.push(j);
        }
      }
    }
    ring = next;
  }
  return [...seen];
}

/**
 * The explored set over the land hexes of `owner` (a region index per cell, < 0 = sea or abroad).
 *   reveal(cell, radius) → the land cells it explored that were not before (empty when nothing changed)
 *   isExplored(i), count, total, owners() → [{explored, total}] per region index, reset()
 *   encode() → string; decode(string) → true if it matched this map (else the set is left as it was)
 */
export function createExplored(grid, owner) {
  const land = [];
  for (let i = 0; i < grid.size; i++) if (owner[i] >= 0) land.push(i);
  const slot = new Int32Array(grid.size).fill(-1);
  land.forEach((cell, k) => (slot[cell] = k));
  const bits = new Uint8Array(land.length);
  const nRegions = land.reduce((n, i) => Math.max(n, owner[i] + 1), 0);
  const totals = new Array(nRegions).fill(0);
  for (const i of land) totals[owner[i]]++;
  const done = new Array(nRegions).fill(0);
  let count = 0;
  // The map the set belongs to: another grid or another coastline makes a saved set meaningless.
  const key = `${grid.cols}x${grid.rows}:${land.length}`;

  function mark(cell) {
    const k = slot[cell];
    if (k < 0 || bits[k]) return false;
    bits[k] = 1;
    done[owner[cell]]++;
    count++;
    return true;
  }

  return {
    key,
    land,
    get count() { return count; },
    get total() { return land.length; },
    isExplored: (i) => i >= 0 && i < grid.size && slot[i] >= 0 && bits[slot[i]] === 1,
    reveal: (cell, radius = RADIUS) => around(grid, cell, radius).filter(mark),
    owners: () => totals.map((total, r) => ({ explored: done[r], total })),
    reset() {
      bits.fill(0);
      done.fill(0);
      count = 0;
    },
    encode() {
      const bytes = new Uint8Array(Math.ceil(land.length / 8));
      bits.forEach((b, k) => b && (bytes[k >> 3] |= 1 << (k & 7)));
      return JSON.stringify({ v: VERSION, key, bits: btoa(String.fromCharCode(...bytes)) });
    },
    decode(text) {
      let saved, raw;
      try {
        saved = JSON.parse(text);
        raw = atob(saved.bits);
      } catch {
        return false;
      }
      if (!saved || saved.v !== VERSION || saved.key !== key || raw.length !== Math.ceil(land.length / 8)) return false;
      this.reset();
      land.forEach((cell, k) => raw.charCodeAt(k >> 3) & (1 << (k & 7)) && mark(cell));
      return true;
    },
  };
}

/**
 * Progress of each group of regions: groups = [{name, regions: [region code]}], codes = the code of each region index
 * (world.json states[i].fips). → [{name, explored, total}] in the groups' order, without the groups that have no land.
 */
export function groupProgress(model, groups, codes) {
  const byCode = new Map(codes.map((code, r) => [code, r]));
  const owners = model.owners();
  return (groups || []).map(({ name, regions }) => {
    let explored = 0, total = 0;
    for (const code of regions || []) {
      const o = owners[byCode.get(code)];
      if (o) {
        explored += o.explored;
        total += o.total;
      }
    }
    return { name, explored, total };
  }).filter((g) => g.total > 0);
}

/**
 * The share explored as it is shown: {x, d}, the fraction and its decimals for format.pct. One decimal below 10 %,
 * none above; always rounded down, so 100 % means everything and a first reveal never shows 0 %.
 */
export function shownShare(explored, total) {
  if (!(total > 0) || !(explored > 0)) return { x: 0, d: 0 };
  const f = Math.min(1, explored / total);
  const d = f < 0.1 ? 1 : 0;
  const step = 10 ** (2 + d);
  return { x: Math.max(1, Math.floor(f * step + 1e-9)) / step, d };
}

/** The saved set from `storage` (localStorage or alike) into `model`; false when absent, unreadable or blocked. */
export function load(model, storage, storeKey) {
  try {
    const text = storage?.getItem(storeKey);
    return text ? model.decode(text) : false;
  } catch {
    return false; // storage blocked (private mode, sandbox): start from fog
  }
}

/** Keep the set in `storage`; false when it could not be written (the map keeps working, it just forgets). */
export function save(model, storage, storeKey) {
  try {
    if (!storage) return false;
    storage.setItem(storeKey, model.encode());
    return true;
  } catch {
    return false;
  }
}
