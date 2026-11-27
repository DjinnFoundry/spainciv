// The fiestas of a month, from fiestas.json (docs/DATA_CONTRACTS.md): which ones, in what order and on which hexes
// (the month itself, its name and the URL key are ext/month.js).
// No DOM, so tests/test_fiestas_js.py runs it in node. A fiesta is in a month when its `months` (the months its
// source's date text names) has it; one with no months is counted apart, never placed in a month.

/** The categories from the top of the ladder down: a hex takes the colour (the lens value, an index here) of its
 *  highest fiesta of the month. */
export const CATEGORIES = ["internacional", "nacional", "autonomica"];
export const COLORS = { internacional: "#ffd34a", nacional: "#f0703c", autonomica: "#c255a6" };

const rank = (f) => CATEGORIES.indexOf(f.category);

/** How many fiestas each month has (index 0 = January). */
export function perMonth(fiestas) {
  const n = new Array(12).fill(0);
  for (const f of fiestas) for (const m of f.months) n[m - 1]++;
  return n;
}

/** The fiestas whose source names no month. */
export const undated = (fiestas) => fiestas.filter((f) => !f.months.length).length;

/** The fiestas of `month`, by category (Internacional first) and then by name as `locale` sorts it (no case, accent
 *  or punctuation differences), place and community breaking ties. */
export function monthFiestas(fiestas, month, locale) {
  const c = new Intl.Collator(locale, { sensitivity: "base", ignorePunctuation: true });
  return fiestas.filter((f) => f.months.includes(month)).sort((a, b) => rank(a) - rank(b)
    || c.compare(a.name, b.name) || c.compare(a.place || "", b.place || "") || c.compare(a.community, b.community));
}

/** A lens's per-hex data for a list of fiestas (from monthFiestas) on a grid of `n` hexes: `values` = the highest
 *  category on the hex (an index into CATEGORIES) or null, `labels` = the indices of its fiestas in list order, and
 *  `names` = label(fiesta) for each. */
export function monthLayer(list, n, label) {
  const values = new Array(n).fill(null);
  const labels = new Array(n).fill(null);
  list.forEach((f, k) => {
    for (const c of f.cells) {
      (labels[c] ||= []).push(k);
      values[c] = values[c] == null ? rank(f) : Math.min(values[c], rank(f));
    }
  });
  return { values, labels, names: list.map(label) };
}
