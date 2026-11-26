// Interface strings in the country's language (world.json country.lang, or the page's <script id="country-page">).
//
// Each language is one table in i18n/<lang>.js: {key: string | {one, other}}. English is the original usaciv text and
// the fallback for any key a table lacks. A string may hold HTML (the tables are ours) and {name} placeholders; the
// values passed in are inserted as they are, so callers escape data with format.js esc() first. A {one, other} entry
// is picked by vars.n with the language's plural rules. Call t() when rendering, never at module load: the country
// (and so the language) is only known once main.js has read world.json.
import { country } from "./app/country.js";
import en from "./i18n/en.js";
import es from "./i18n/es.js";

export const TABLES = { en, es };

export const lang = () => (TABLES[country().lang] ? country().lang : "en");

const plurals = new Map();
function pluralForm(n) {
  const l = lang();
  if (!plurals.has(l)) plurals.set(l, new Intl.PluralRules(l));
  return plurals.get(l).select(n);
}

/** The string for `key`, with {placeholders} filled from `vars`. An unknown key comes back as the key itself. */
export function t(key, vars) {
  let s = TABLES[lang()][key] ?? en[key];
  if (s == null) {
    console.warn(`i18n: no string for "${key}"`);
    return key;
  }
  if (typeof s === "object") s = s[pluralForm(vars?.n ?? 0)] ?? s.other;
  return vars ? s.replace(/\{(\w+)\}/g, (m, k) => (vars[k] == null ? m : String(vars[k]))) : s;
}

// The static text of web/index.html, which is written in English for the United States: [selector, attribute or
// null for the text, key]. Another language replaces it when the page starts (tests/test_i18n.py checks that every
// English entry still matches index.html).
export const PAGE_STRINGS = [
  ["#yields", "aria-label", "page.yields"],
  ["#search-input", "placeholder", "page.search.placeholder"],
  ["#search-input", "aria-label", "page.search.label"],
  ["#btn-share", "aria-label", "page.share.label"],
  ["#btn-share", "title", "page.share.title"],
  ["#btn-help", "aria-label", "page.help.label"],
  ["#btn-help", "title", "page.help.title"],
  ["#btn-pedia", "aria-label", "page.pedia.label"],
  ["#btn-pedia", "title", "page.pedia.title"],
  ["#city-panel", "aria-label", "page.panel"],
  ["#lens-picker", "aria-label", "page.lensPicker"],
  ["#legend", "aria-label", "page.legend"],
  ["#lens-dock", "aria-label", "page.lensDock"],
  ["#btn-res", "aria-label", "page.res.label"],
  ["#btn-res", "title", "page.res.title"],
  ["#minimap", "aria-label", "page.minimap"],
  ["#btn-minimap", "aria-label", "page.minimap.show"],
  ["#search-results", "aria-label", "page.searchResults"],
  ["#share-pop", "aria-label", "page.sharePop"],
  ["#yield-report", "aria-label", "page.report"],
  ["#pedia .modal-card", "aria-label", "page.pedia"],
  ["#pedia [data-close]", "aria-label", "page.pedia.close"],
  ["#pedia-nav", "aria-label", "page.pedia.nav"],
  ["#loading", null, "page.loading"],
];

/** Put index.html's static text in the country's language (nothing to do for English). */
export function translatePage(doc = globalThis.document) {
  if (lang() === "en" || !doc) return;
  for (const [sel, attr, key] of PAGE_STRINGS) {
    const el = doc.querySelector(sel);
    if (!el) continue;
    if (attr) el.setAttribute(attr, t(key));
    else el.textContent = t(key);
  }
}
