// The country the loaded data describes: world.json `country` (pipeline/countries), with the original usaciv values
// for data that predates the block, and the page's own settings on top (<script id="country-page">, written by
// pipeline/site.py when the site is served or packaged: lang, site_url, data_credit, notices). The page's settings
// apply from the start, so the interface language is known before the data loads; main.js calls setCountry(world)
// once; everything else reads country().

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

let current = { ...US, ...pageSettings(globalThis.document) };

export function setCountry(world, doc = globalThis.document) {
  current = { ...US, ...(world && world.country), ...pageSettings(doc) };
  return current;
}

export const country = () => current;

/** Show the country's name in the page chrome (title, brand, map description). */
export function applyCountryChrome(doc = document) {
  const c = current;
  if (c.id === "us") return; // index.html is written for the United States
  doc.documentElement.lang = c.lang;
  doc.title = `${c.product} — ${c.name}`;
  const brand = doc.querySelector("#topbar .brand");
  if (brand) {
    brand.title = c.name;
    const text = brand.querySelector(".brand-text");
    if (text) text.textContent = c.name;
  }
}
