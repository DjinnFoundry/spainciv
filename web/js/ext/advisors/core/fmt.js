// Number formatting for the advisor kit, built on web/js/format.js.
// Formats follow lenses.json / counties.json: int | usd | pct (0..1 fraction) | float | minutes | years | km2 | text,
// plus a few of our own: money (compact $), signed (signed %), lq (×1.23), mw, count, ratio (×4.2).
import { compact, count3, dollars, fixed, int, money, pct, sig3, signedPct, trimmed as trim, withCurrency, withPct } from "../../../format.js";
import { country } from "../../../app/country.js";
import { t } from "../../../i18n.js";
import { fin } from "./util.js";

export { compact, count3, dollars, fixed, int, money, pct, signedPct };

const original = () => (country().locale || "en-US") === "en-US";
/** "×1.23" with d decimals. */
export const times = (v, d) => `×${fixed(v, d)}`;

export const mw = (v) => (fin(v) ? (Math.abs(v) >= 10000 ? `${fixed(v / 1000, v >= 1e5 ? 0 : 1)} GW` : `${int(v)} MW`) : "–");

/** Full-ish text for a value in a given format (tables, tooltips). */
export function fmtValue(format, v, unit) {
  if (format === "text") return v == null || v === "" ? "–" : String(v);
  if (!fin(v)) return "–";
  switch (format) {
    case "int": case "count": return Math.abs(v) >= 1e6 ? count3(v) : int(v);
    case "usd": case "eur": return Math.abs(v) >= 1e6 ? money(v) : dollars(v);
    case "money": return money(v);
    case "pct": return pct(v);
    case "signed": return signedPct(v);
    case "lq": return times(v, 2);
    case "ratio": return times(v, 1);
    case "minutes": return t("adv.unit.min", { v: fixed(v, 1) });
    case "years": return t("adv.unit.yrs", { v: fixed(v, 1) });
    case "km2": return `${int(v)} km²`;
    case "mw": return mw(v);
    case "float": return Math.abs(v) >= 100 ? int(v) : Math.abs(v) >= 10 ? fixed(v, 1) : fixed(v, 2);
    default:
      if (unit === "MW") return mw(v);
      return Math.abs(v) >= 1e4 ? count3(v) : Math.abs(v) >= 100 ? int(v) : fixed(v, 2);
  }
}

/** Compact text for a table cell, so numbers fit narrow columns: $121K, 9.4M, +2.1%, 12.3%, 4,210 km². */
export function fmtCell(format, v, unit) {
  if (format === "text") return v == null || v === "" ? "–" : String(v);
  if (!fin(v)) return "–";
  const a = Math.abs(v);
  switch (format) {
    case "int": case "count": return a >= 1e4 ? count3(v) : int(v);
    case "usd": case "eur": return a >= 1e4 ? withCurrency(count3(v)) : dollars(v);
    case "money": return money(v);
    case "km2": return a >= 1e5 ? `${count3(v)} km²` : `${int(v)} km²`;
    case "float": return a >= 1e4 ? count3(v) : fmtValue(format, v, unit);
    default: return fmtValue(format, v, unit);
  }
}

/** Short text for axis ticks and chips. */
export function fmtShort(format, v) {
  if (!fin(v)) return "–";
  switch (format) {
    case "usd": case "eur": case "money": return money(v);
    case "pct": return withPct(trim(v * 100, Math.abs(v) < 0.1 && v !== 0 ? 1 : 0));
    case "signed": return `${v > 0 ? "+" : v < 0 ? "−" : ""}${withPct(trim(Math.abs(v * 100), 1))}`;
    case "lq": case "ratio": return `×${trim(v, 1)}`;
    case "mw": return mw(v);
    case "minutes": case "years": return trim(v, 0);
    default: return Math.abs(v) >= 1000 ? compact(v) : sig3(v);
  }
}

/** Parse "1.5M", "250k", "12%", "$80K", "-3%" into a number in the field's units (pct → fraction). Outside en-US
 * the locale's forms are read too: "1,5 M", "12 %", "35.000 €", "250 mil", "1,5 B" (es-ES: billón = 10¹²). */
export function parseNum(text, format) {
  if (text == null) return null;
  if (!original()) return parseLocal(text, format);
  let s = String(text).trim().replace(/[,$\s]/g, "").replace(/^−/, "-");
  if (!s) return null;
  let isPct = false;
  if (s.endsWith("%")) { isPct = true; s = s.slice(0, -1); }
  const m = /^(-?\d*\.?\d+)([kmbt]?)$/i.exec(s);
  if (!m) return null;
  let v = parseFloat(m[1]) * ({ "": 1, k: 1e3, m: 1e6, b: 1e9, t: 1e12 })[m[2].toLowerCase()];
  if ((format === "pct" || format === "signed") && (isPct || Math.abs(v) > 1)) v /= 100;
  return v;
}

// Decimal comma and grouping dot (es-ES); "mil" = 10³, "M" = 10⁶, "mil M" = 10⁹, "B" = 10¹². A dot followed by exactly
// three digits groups thousands; any other dot is read as a decimal point, so English input still works.
const LOCAL_MULT = { "": 1, k: 1e3, mil: 1e3, m: 1e6, "milm": 1e9, b: 1e12 };
function parseLocal(text, format) {
  let s = String(text).trim().toLowerCase().replace(/[€$\s\u00a0]/g, "").replace(/^−/, "-");
  if (!s) return null;
  let isPct = false;
  if (s.endsWith("%")) { isPct = true; s = s.slice(0, -1); }
  const m = /^(-?[\d.,]*\d)(k|mil|m|milm|b)?$/.exec(s);
  if (!m) return null;
  let num = m[1];
  if (num.includes(",")) num = num.replace(/\./g, "").replace(",", ".");
  else if (/^-?\d{1,3}(\.\d{3})+$/.test(num)) num = num.replace(/\./g, "");
  let v = parseFloat(num) * LOCAL_MULT[m[2] || ""];
  if (!Number.isFinite(v)) return null;
  if ((format === "pct" || format === "signed") && (isPct || Math.abs(v) > 1)) v /= 100;
  return v;
}
