// The rules of the train lens that need no canvas (ext/transit/index.js draws; tests/test_transit_js.py runs this in
// node): link bands, station sizes, hit tests and the tooltip texts. transit.json is described in docs/DATA_CONTRACTS.md.
import { t } from "../../i18n.js";
import { esc, int } from "../../format.js";
import { country } from "../../app/country.js";
import { formatDuration } from "../../ui/lenses.js";

// Passenger trains a day on a link: 1–9, 10–49, 50 or more (DECISIONS E103).
export const BANDS = [10, 50];
export const band = (n) => (n >= BANDS[1] ? 2 : n >= BANDS[0] ? 1 : 0);
export const GHOST = "g";

/** transit.json links → [[a, b, band]] for the line pieces, and ghost links → [[a, b, "g"]]. */
export function lineClasses(doc) {
  return {
    served: (doc.links || []).map(([a, b, n]) => [a, b, band(n)]),
    ghost: (doc.ghost || []).map(([a, b]) => [a, b, GHOST]),
  };
}

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
/** Lines and dots grow with the zoom (hex radius in css px), within limits. */
export const zoomFactor = (Rpx) => clamp(Rpx / 8, 0.7, 2);
/** Served line width in css px by band. */
export const lineWidth = (b, Rpx) => [1, 1.8, 2.8][b] * zoomFactor(Rpx);
/** A station's dot radius in css px: the area follows its trains of the day. */
export const stationRadius = (trains, Rpx) => clamp(0.7 + 0.11 * Math.sqrt(trains), 1, 5) * zoomFactor(Rpx);
export const totalTrains = (st) => st.trains.reduce((p, q) => p + q, 0);

/** "9 de diciembre" / "9 December": the day of the timetable without the year. */
export function dayLabel(iso, locale = country().locale) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat(locale, { day: "numeric", month: "long", timeZone: "UTC" }).format(new Date(Date.UTC(y, m - 1, d)));
}

/** The lens arrays from transit.json: values (minutes), and each hex's station as a label ("desde Sevilla-Santa Justa"). */
export function lensLayer(doc) {
  const names = doc.stations.map((s) => t("transit.hex.from", { name: s.name }));
  const labels = doc.lens.station.map((k) => (k == null ? undefined : [k]));
  return { values: doc.lens.values, names, labels };
}

/** The legs of a journey: [train label, from, to], a walk's label null ("a pie a València-Joaquín Sorolla"). */
function legs(list) {
  const leg = ([label, from, to]) => (label == null ? t("transit.station.walk", { to: esc(to) }) : esc(`${label} ${from} → ${to}`));
  if (list.length === 1 && list[0][0] != null) return esc(list[0][0]);
  return list.map(leg).join("; ");
}

/** "(14 de alta velocidad y larga distancia y 133 de Cercanías)": the kinds of train a station has, zeros left out. */
function split(trains, locale = country().locale) {
  const parts = ["ld", "md", "cer"].map((k, i) => (trains[i] ? t(`transit.station.kind.${k}`, { n: int(trains[i]) }) : null)).filter(Boolean);
  return parts.length ? t("transit.station.split", { kinds: new Intl.ListFormat(locale, { type: "conjunction" }).format(parts) }) : "";
}

/** The tooltip of a station (HTML; data escaped). */
export function stationTip(st, date) {
  const n = totalTrains(st);
  const lines = [`<b>${esc(st.name)}</b>: ${t("transit.station.trains", { n, count: int(n), date })}${n ? ` ${split(st.trains)}` : "."}`];
  const b = st.best;
  if (st.madrid) lines.push(t("transit.station.madrid"));
  else if (!b) lines.push(t("transit.station.none"));
  else {
    const changes = b.changes ? t("transit.station.changes", { n: b.changes }) : t("transit.station.direct");
    lines.push(t("transit.station.best", { time: formatDuration(b.min), dep: b.dep, arr: b.arr, to: esc(b.to), changes, legs: legs(b.legs) }));
  }
  return lines.join("<br>");
}

/** The tooltip of a stretch of track. */
export const linkTip = (it, date) =>
  it.kind === "ghost" ? t("transit.link.ghost", { date }) : t("transit.link.served", { n: it.n, count: int(it.n), date });

/** The station whose dot holds (x, y) (world km), the smallest on top (drawn last), or null. */
export function hitStation(list, x, y, Rpx, R) {
  const s = Rpx / R;
  for (let k = list.length - 1; k >= 0; k--) {
    const st = list[k];
    const r = (stationRadius(totalTrains(st), Rpx) + 2) / s;
    if ((st.x - x) ** 2 + (st.y - y) ** 2 <= r * r) return st;
  }
  return null;
}

function segDist(px, py, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay;
  const l2 = dx * dx + dy * dy;
  const u = l2 ? clamp(((px - ax) * dx + (py - ay) * dy) / l2, 0, 1) : 0;
  return Math.hypot(px - (ax + u * dx), py - (ay + u * dy));
}

/** {cell: [link items]} for hit tests: item = {kind: "served" | "ghost", a, b, n}. */
export function linkIndex(doc) {
  const by = new Map();
  const add = (it) => {
    for (const c of [it.a, it.b]) {
      if (!by.has(c)) by.set(c, []);
      by.get(c).push(it);
    }
  };
  for (const [a, b, n] of doc.links || []) add({ kind: "served", a, b, n });
  for (const [a, b] of doc.ghost || []) add({ kind: "ghost", a, b, n: 0 });
  return by;
}

/** The link within a few css px of (x, y) (world km), the nearest; links of the pointer's hex and its neighbours. */
export function hitLink(index, grid, x, y, Rpx) {
  const cell = grid.cellAt(x, y);
  if (cell < 0) return null;
  const s = Rpx / grid.R;
  const cells = [cell];
  for (let d = 0; d < 6; d++) cells.push(grid.neighbour(cell, d));
  let best = null, bestD = Infinity;
  for (const c of cells) {
    for (const it of index.get(c) || []) {
      const tol = ((it.kind === "ghost" ? 1 : lineWidth(band(it.n), Rpx)) / 2 + 3) / s;
      const d = segDist(x, y, grid.cx(it.a), grid.cy(it.a), grid.cx(it.b), grid.cy(it.b));
      if (d <= tol && d < bestD) { best = it; bestD = d; }
    }
  }
  return best;
}
