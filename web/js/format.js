import { country } from "./app/country.js";

// Numbers follow the country's locale (world.json country.locale, or the chosen language's, app/country.js). The
// original en-US formats stay exactly as usaciv wrote them ("1.2K", "$3.4B", "12.5%"); any other locale goes through
// Intl, which for es-ES gives "1,2 mil", "35 M", "16 mil M €", "1,5 B €" (billón = 10¹²), "12,5 %" and "35.000 €"
// (four-digit numbers ungrouped, as the RAE asks), and for en-IE (Spain in English) "1.2K", "€1.5T", "12.5%".
const ORIGINAL = "en-US";
const locale = () => country().locale || ORIGINAL;
const original = () => locale() === ORIGINAL;
const formats = new Map();
function nf(opts) {
  const key = locale() + JSON.stringify(opts);
  let f = formats.get(key);
  if (!f) formats.set(key, (f = new Intl.NumberFormat(locale(), opts)));
  return f;
}

/** x with d decimals in the country's locale: "3.5" (en-US), "3,5" (es-ES). */
export const fixed = (x, d = 0) => (original() ? x.toFixed(d) : nf({ minimumFractionDigits: d, maximumFractionDigits: d }).format(x));

/** A day of the calendar (year, month 1–12, day) written out in the country's locale: "16 de noviembre de 2026". */
export const longDate = (y, m, d) => new Intl.DateTimeFormat(locale(), { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })
  .format(new Date(Date.UTC(y, m - 1, d)));

/** x in its shortest form: "0.03" (en-US), "0,03" (es-ES). */
export const plain = (x) => (original() ? String(x) : nf({ maximumFractionDigits: 20 }).format(x));

/** x.toLocaleString() as usaciv printed it (the browser's locale) for en-US, else in the country's locale. */
export const localeNum = (x) => (original() ? x.toLocaleString() : x.toLocaleString(locale()));

export function compact(n) {
  if (n == null || Number.isNaN(n)) return "–";
  const a = Math.abs(n);
  if (!original()) return nf({ notation: "compact", maximumFractionDigits: 1 }).format(n);
  if (a >= 1e12) return (n / 1e12).toFixed(a >= 1e13 ? 1 : 2) + "T";
  if (a >= 1e9) return (n / 1e9).toFixed(a >= 1e11 ? 0 : 1) + "B";
  if (a >= 1e6) return (n / 1e6).toFixed(a >= 1e8 ? 0 : 1) + "M";
  if (a >= 1e3) return (n / 1e3).toFixed(a >= 1e5 ? 0 : 1).replace(/\.0$/, "") + "K";
  return String(Math.round(n));
}

const SYMBOL = { USD: "$", EUR: "€" };
/** The country's currency symbol (world.json country.currency). */
export const currency = () => SYMBOL[country().currency] ?? country().currency + " ";
/** True when the locale writes the currency symbol before the amount ("€12K", en-IE), not after it ("12 mil €"). */
const symbolFirst = () => {
  const parts = nf({ style: "currency", currency: country().currency || "USD" }).formatToParts(1).map((p) => p.type);
  return parts.indexOf("currency") < parts.indexOf("integer");
};
/** A formatted amount with the currency symbol where the locale puts it: "$12K" (en-US), "€12K" (en-IE), "12 mil €" (es-ES). */
export const withCurrency = (s) => (original() || symbolFirst() ? currency() + s : `${s}\u00a0${currency().trim()}`);
/** True for a money unit or format: "usd" (the original data) or "eur". */
export const isMoney = (unit) => unit === "usd" || unit === "eur";
export const money = (n) => (n == null ? "–" : withCurrency(compact(n)));
export const dollars = (n) => (n == null ? "–" : withCurrency(Math.round(n).toLocaleString(locale())));
/** "22:01" for minutes after midnight (rounded to the minute; the 24-hour clock in every language of the site). */
export function clock(minutes) {
  const m = ((Math.round(minutes) % 1440) + 1440) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}
export const int = (n) => (n == null ? "–" : Math.round(n).toLocaleString(locale()));
export const pct = (x, d = 1) => (x == null ? "–" : original() ? (x * 100).toFixed(d) + "%" : nf({ style: "percent", minimumFractionDigits: d, maximumFractionDigits: d }).format(x));

/** x with at most d decimals, trailing zeros dropped: "12.5" (en-US), "12,5" (es-ES). */
export const trimmed = (x, d) => (original() ? String(+x.toFixed(d)) : nf({ maximumFractionDigits: d }).format(x));
/** x to three significant figures: "0.123" (en-US), "0,123" (es-ES). */
export const sig3 = (x) => (original() ? String(+x.toPrecision(3)) : nf({ maximumSignificantDigits: 3 }).format(x));
/** True when the locale puts a space before the percent sign ("12 %", es-ES), not ("12%", en-US, en-IE). */
const spacedPct = () => nf({ style: "percent" }).formatToParts(0.5).some((p) => p.type === "literal");
/** A formatted number with the percent sign where the locale puts it: "12%" (en-US, en-IE), "12 %" (es-ES). */
export const withPct = (s) => (original() || !spacedPct() ? `${s}%` : `${s}\u00a0%`);
/** A growth rate with its sign: "+2.1%", "−0.4%" (en-US); "+2,1 %" (es-ES). */
export const signedPct = (g, d = 1) => (Number.isFinite(g) ? `${g >= 0 ? "+" : "−"}${pct(Math.abs(g), d)}` : "–");

// Counts to three significant figures (1.12M vs 1.11M rather than 1.1M twice); es-ES: "1,12 M", "12,3 mil".
export function count3(n) {
  if (!Number.isFinite(n)) return "–";
  const a = Math.abs(n);
  if (!original()) return a >= 1e4 ? nf({ notation: "compact", maximumSignificantDigits: 3 }).format(n) : int(n);
  const sig = (d, unit) => (n / d).toFixed(a / d >= 100 ? 0 : a / d >= 10 ? 1 : 2) + unit;
  if (a >= 1e12) return sig(1e12, "T");
  if (a >= 1e9) return sig(1e9, "B");
  if (a >= 1e6) return sig(1e6, "M");
  if (a >= 1e4) return sig(1e3, "K");
  return int(n);
}

// Weights in the data are in the original US units, short tons and pounds (docs/DATA_CONTRACTS.md,
// infrastructure.json); any other locale shows both in tonnes.
/** A weight given in short tons, in the unit the country's map shows ("t" is a short ton in en-US, a tonne else). */
export const shownTons = (shortTons) => (shortTons == null || original() ? shortTons : shortTons * 0.90718474);
/** A weight given in pounds (air cargo), in the unit the country's map shows: pounds in en-US, tonnes else. */
export const shownWeight = (lb) => (lb == null || original() ? lb : lb * 0.00045359237);

export function yieldValue(y, v) {
  return isMoney(y.unit) ? money(v) : compact(v);
}

export function popShort(n) {
  if (!original()) return nf({ notation: "compact", maximumFractionDigits: n >= 1e6 && n < 1e7 ? 1 : 0 }).format(n);
  if (n >= 1e7) return Math.round(n / 1e6) + "M";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  return Math.round(n / 1e3) + "K";
}

export const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
