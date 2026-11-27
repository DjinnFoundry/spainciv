// Sunrise, sunset, solar noon and day length on Spain's official clocks, for the lens "Atardecer" (index.js).
// No DOM, so tests/test_sun_js.py runs it in node.
//
// The sun: the NOAA solar position equations (NOAA Global Monitoring Laboratory, "Solar Calculation Details",
// https://gml.noaa.gov/grad/solcalc/calcdetails.html, from Jean Meeus, "Astronomical Algorithms"), as NOAA's own
// calculator (https://gml.noaa.gov/grad/solcalc/) evaluates them: sunrise and sunset when the sun's centre is 0.833°
// below a sea-level horizon (refraction and the sun's radius), each time evaluated again at the time first found.
// NOAA gives them as accurate to within a minute between ±72° of latitude; hills, buildings and the hex's height are
// left out.
// The clock: Central European Time (UTC+1) in the peninsula, the Balearic Islands, Ceuta and Melilla; Western European
// Time (UTC+0) in the Canary Islands; summer time (+1 h) by the EU rule (Directive 2000/84/EC), from 01:00 UTC on the
// last Sunday of March to 01:00 UTC on the last Sunday of October. Sunrise and sunset in Spain are always well after
// 01:00 UTC, so the date alone says which offset they read.

const RAD = Math.PI / 180;
const DAY_MIN = 1440;
const SUN_ZENITH = 90.833; // degrees: the sun's upper edge on the horizon, refraction included

/** The quantities the lens can show, in the order of its switch. */
export const MODES = ["sunset", "sunrise", "day", "noon"];
/** Their names in the URL (#sol=puesta). */
export const MODE_SLUG = { sunset: "puesta", sunrise: "salida", day: "dia", noon: "mediodia" };

// --- dates ---------------------------------------------------------------------------------------------------------

/** {y, m, d} of a local Date. */
export const localDay = (date = new Date()) => ({ y: date.getFullYear(), m: date.getMonth() + 1, d: date.getDate() });

const daysIn = (y, m) => new Date(Date.UTC(y, m, 0)).getUTCDate();

/** A day from the URL or a date input ("2026-06-21") or null. */
export function parseDay(v) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(v ?? ""));
  if (!m) return null;
  const y = +m[1], mo = +m[2], d = +m[3];
  return y >= 1901 && y <= 2099 && mo >= 1 && mo <= 12 && d >= 1 && d <= daysIn(y, mo) ? { y, m: mo, d } : null;
}

/** "2026-06-21". */
export const isoDay = ({ y, m, d }) => `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;

export const sameDay = (a, b) => a.y === b.y && a.m === b.m && a.d === b.d;

/** The day of the last Sunday of a month. */
function lastSunday(y, m) {
  const last = daysIn(y, m);
  return last - new Date(Date.UTC(y, m - 1, last)).getUTCDay();
}

/** Is the EU's summer time in force on that day (after 01:00 UTC)? */
export function summerTime({ y, m, d }) {
  const k = m * 100 + d;
  return k >= 300 + lastSunday(y, 3) && k < 1000 + lastSunday(y, 10);
}

// --- time zones ----------------------------------------------------------------------------------------------------

/** The official zone of a point in Spain: the Canary Islands (west of 12° W) keep Western European Time. */
export const zoneOf = (lon) => (lon < -12 ? "WE" : "CE");

/** {offset (hours east of UTC), abbr} of a zone on a day: CET / CEST, WET / WEST. */
export function clockOf(zone, day) {
  const summer = summerTime(day);
  return { offset: (zone === "WE" ? 0 : 1) + (summer ? 1 : 0), abbr: `${zone}${summer ? "S" : ""}T` };
}

// --- the sun (NOAA) ------------------------------------------------------------------------------------------------

/** Julian day at 0h UTC of a Gregorian day. */
export function julianDay({ y, m, d }) {
  if (m <= 2) {
    y -= 1;
    m += 12;
  }
  const a = Math.floor(y / 100);
  return Math.floor(365.25 * (y + 4716)) + Math.floor(30.6001 * (m + 1)) + d + 2 - a + Math.floor(a / 4) - 1524.5;
}

/** The sun's declination (degrees) and the equation of time (minutes) at a Julian day. */
export function sunAt(jd) {
  const t = (jd - 2451545) / 36525; // Julian centuries since J2000.0
  const l0 = (((280.46646 + t * (36000.76983 + 0.0003032 * t)) % 360) + 360) % 360; // geometric mean longitude
  const m = 357.52911 + t * (35999.05029 - 0.0001537 * t); // mean anomaly
  const e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t); // orbit eccentricity
  const mr = m * RAD;
  const c = Math.sin(mr) * (1.914602 - t * (0.004817 + 0.000014 * t)) + Math.sin(2 * mr) * (0.019993 - 0.000101 * t)
    + Math.sin(3 * mr) * 0.000289; // equation of centre
  const omega = (125.04 - 1934.136 * t) * RAD;
  const lambda = (l0 + c - 0.00569 - 0.00478 * Math.sin(omega)) * RAD; // apparent longitude
  const e0 = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60; // mean obliquity
  const eps = (e0 + 0.00256 * Math.cos(omega)) * RAD; // corrected obliquity
  const decl = Math.asin(Math.sin(eps) * Math.sin(lambda)) / RAD;
  const yy = Math.tan(eps / 2) ** 2, l0r = l0 * RAD;
  const eot = yy * Math.sin(2 * l0r) - 2 * e * Math.sin(mr) + 4 * e * yy * Math.sin(mr) * Math.cos(2 * l0r)
    - 0.5 * yy * yy * Math.sin(4 * l0r) - 1.25 * e * e * Math.sin(2 * mr);
  return { decl, eot: (4 * eot) / RAD };
}

/** Minutes after 0h UTC of `jd` at which the sun rises (`rising` true), sets (false) or crosses the meridian (null):
 *  found at local noon's sun, then again at the sun of the time found. */
function crossing(jd, lat, lon, rising) {
  const at = (minutes) => {
    const { decl, eot } = sunAt(jd + minutes / DAY_MIN);
    if (rising == null) return 720 - 4 * lon - eot;
    const la = lat * RAD, de = decl * RAD;
    const cos = Math.cos(SUN_ZENITH * RAD) / (Math.cos(la) * Math.cos(de)) - Math.tan(la) * Math.tan(de);
    const ha = Math.acos(Math.max(-1, Math.min(1, cos))) / RAD; // clamped: no midnight sun or polar night in Spain
    return 720 - 4 * (lon + (rising ? ha : -ha)) - eot;
  };
  return at(at(720 - 4 * lon));
}

/** Sunrise, solar noon and sunset in minutes after 0h UTC of `day`, at latitude / longitude (degrees, east +). */
export function sunTimesUTC(day, lat, lon) {
  const jd = julianDay(day);
  return { sunrise: crossing(jd, lat, lon, true), noon: crossing(jd, lat, lon, null), sunset: crossing(jd, lat, lon, false) };
}

/** The day at a place on Spain's clocks: {sunrise, noon, sunset} as whole minutes after local midnight, `day` = the
 *  minutes between the sunrise and the sunset shown (so the three always agree), the zone's abbreviation, and
 *  `exact`, the same four unrounded. */
export function sunDay(day, lat, lon) {
  const { offset, abbr } = clockOf(zoneOf(lon), day);
  const utc = sunTimesUTC(day, lat, lon);
  const exact = { sunrise: utc.sunrise + offset * 60, noon: utc.noon + offset * 60, sunset: utc.sunset + offset * 60 };
  exact.day = exact.sunset - exact.sunrise;
  const sunrise = Math.round(exact.sunrise), sunset = Math.round(exact.sunset);
  return { sunrise, noon: Math.round(exact.noon), sunset, day: sunset - sunrise, abbr, exact };
}

// --- the lens ------------------------------------------------------------------------------------------------------

/** For each hex in `points` ([{cell, lat, lon}]) on a grid of `n` hexes: its day (sunDay) on `day`, `values` = the
 *  `mode`'s minutes (null off the points), and the hexes with the lowest and highest value (`low`, `high`: {cell,
 *  value}). A tie on the minute goes to the exact time, so the extremes are the real first and last hexes. */
export function sunLayer(points, n, day, mode) {
  const days = new Array(n).fill(null);
  const values = new Array(n).fill(null);
  let low = null, high = null;
  for (const p of points) {
    const s = sunDay(day, p.lat, p.lon);
    days[p.cell] = s;
    values[p.cell] = s[mode];
    const x = s.exact[mode];
    if (!low || x < low.exact) low = { cell: p.cell, value: s[mode], exact: x };
    if (!high || x > high.exact) high = { cell: p.cell, value: s[mode], exact: x };
  }
  return { days, values, low, high };
}
