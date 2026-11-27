// The country the loaded data describes: world.json `country` (pipeline/countries), with the original usaciv values
// for data that predates the block, and the page's own settings on top (<script id="country-page">, written by
// pipeline/site.py when the site is served or packaged: lang, site_url, data_credit, notices, and `play`, the Unciv page
// of a country with an Unciv map). The page's settings apply from the start, so the interface language is known before
// the data loads; main.js calls setCountry(world) once; everything else reads country().
//
// A country published in several languages (page settings `langs`: {lang: number locale}, the first being the
// language of its data files, `data_lang`) shows the one in the URL (#lang=en), else the one the visitor picked last
// (localStorage), else the first of the browser's languages it has, else its first. `lang` and `locale` are then the
// chosen one's, and `texts[lang]` (credits, notices, the Unciv page) lies over the page settings.

const US = {
  id: "us", name: "United States", product: "usaciv", site_url: "karpathy.ai/usaciv", lang: "en", locale: "en-US",
  currency: "USD", capital_city: "47900",
  levels: { region: { one: "State", many: "States" }, unit: { one: "County", many: "Counties" }, metro: { one: "Metro", many: "Metros" } },
  data_credit: "Data: Census ACS, BEA, NOAA, USGS/MRLC, EIA, Natural Earth", notices: [],
};

function pageSettings(doc) {
  try {
    const el = doc?.getElementById("country-page");
    return el ? JSON.parse(el.textContent) : {};
  } catch {
    return {};
  }
}

const STORE_KEY = "lang";

function stored() {
  try {
    return globalThis.localStorage?.getItem(STORE_KEY) ?? null;
  } catch {
    return null; // storage blocked (private mode, sandbox): the choice is not remembered
  }
}

const hashParams = (loc) => new URLSearchParams(String(loc?.hash || "").replace(/^#/, ""));

function hashLang(loc) {
  try {
    return hashParams(loc).get("lang");
  } catch {
    return null;
  }
}

/** The language to show of a page's `langs` (see above). */
export function pickLang(langs, { loc = globalThis.location, saved = stored(), browser = globalThis.navigator?.languages } = {}) {
  const offered = Object.keys(langs || {});
  if (!offered.length) return null;
  const primary = (tag) => String(tag || "").toLowerCase().split("-")[0];
  const wanted = [hashLang(loc), saved, ...(browser || []).map(primary)];
  return wanted.find((l) => offered.includes(l)) ?? offered[0];
}

function withLang(c) {
  const lang = pickLang(c.langs);
  if (!lang) return c;
  return { ...c, ...(c.texts?.[lang] || {}), lang, locale: c.langs[lang], data_lang: Object.keys(c.langs)[0] };
}

let current = withLang({ ...US, ...pageSettings(globalThis.document) });

export function setCountry(world, doc = globalThis.document) {
  current = withLang({ ...US, ...(world && world.country), ...pageSettings(doc) });
  return current;
}

/** Show the page in `lang`: remembered for the next visits, put in the URL, and the page reloads in it. */
export function switchLang(lang) {
  if (!current.langs?.[lang] || lang === current.lang) return;
  try {
    globalThis.localStorage?.setItem(STORE_KEY, lang);
  } catch {
    /* not remembered; the URL still carries it */
  }
  const p = hashParams(location);
  p.set("lang", lang);
  try {
    history.replaceState(null, "", `${location.pathname}${location.search}#${p}`);
  } catch {
    /* the reload falls back on the remembered choice */
  }
  location.reload();
}

export const country = () => current;

/** Show the country's name in the page chrome (title, brand, map description). */
export function applyCountryChrome(doc = document) {
  const c = current;
  if (c.id === "us") return; // index.html is written for the United States
  doc.documentElement.lang = c.lang;
  doc.title = `${c.product} — ${c.name}`;
  if (c.lang !== c.data_lang) {
    if (c.description) doc.querySelector('meta[name="description"]')?.setAttribute("content", c.description);
    const credits = doc.getElementById("map-credits");
    if (credits && c.credits) credits.innerHTML = c.credits;
  }
  const brand = doc.querySelector("#topbar .brand");
  if (brand) {
    brand.title = c.name;
    const text = brand.querySelector(".brand-text");
    if (text) text.textContent = c.name;
  }
}
