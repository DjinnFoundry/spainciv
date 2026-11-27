// A Walter-Lieth climate diagram as an SVG string, after the conventions of Walter and Lieth, Klimadiagramm-Weltatlas
// (VEB Gustav Fischer, Jena, 1960-1967): the mean temperature of each month (red, left axis) and its rain (blue, right
// axis) on one scale, 10 °C = 20 mm, so a month whose temperature line runs above its rain line is dry (dotted) and
// one below it is humid (hatched). Above 100 mm the rain scale shrinks to a tenth and that part is filled solid. The
// bar under the months marks those whose mean daily minimum is below 0 °C. Walter and Lieth also hatch the months whose
// absolute minimum is below 0 °C; the data drawn here (AEMET's province normals) have no absolute minimum, so that bar
// is left out. No DOM, so tests/test_clima_js.py runs it in node.

const W = 328, H = 228;
const PAD = { left: 30, right: 36, top: 44, bottom: 30 };
const COLORS = { temp: "#e0533f", prec: "#4f8fdc", dry: "#e8b04a", solid: "#2f62a8", frost: "#9cc3ff" };

/** Rain in mm as the height of the temperature scale (°C): 2 mm a degree up to 100 mm, then 20 mm a degree. */
export const scaleP = (mm) => (mm <= 100 ? mm / 2 : 50 + (mm - 100) / 20);
/** The rain in mm at a height of the temperature scale (the right axis). */
export const mmAt = (u) => (u <= 50 ? u * 2 : 100 + (u - 50) * 20);

/** Each month dry (its temperature above its scaled rain) or humid. */
export const seasons = (tmed, prec) => tmed.map((t, k) => (t > scaleP(prec[k]) ? "dry" : "humid"));
/** The months whose mean daily minimum is below 0 °C. */
export const frostMonths = (tmin) => tmin.map((t) => t < 0);

/** The scale and the twelve points of both lines, in degrees (rain scaled): {lo, hi, temp: [12], prec: [12]}. */
export function geometry(tmed, prec) {
  const p = prec.map(scaleP);
  const lo = Math.min(0, Math.floor(Math.min(...tmed) / 10) * 10);
  const hi = Math.max(30, Math.ceil(Math.max(...tmed, ...p) / 10) * 10);
  return { lo, hi, temp: tmed.slice(), prec: p };
}

// Between two months the lines are straight; a stretch is split where they cross and where the rain crosses 100 mm, so
// each piece is one kind (dry, humid, very humid) and its areas are four-sided.
function pieces(temp, prec) {
  const out = [];
  for (let k = 0; k < 11; k++) {
    const at = (a, b, s) => a + (b - a) * s;
    const T = (s) => at(temp[k], temp[k + 1], s), P = (s) => at(prec[k], prec[k + 1], s);
    const cuts = [0, 1];
    const cross = (f0, f1) => (f0 * f1 < 0 ? f0 / (f0 - f1) : null);
    for (const s of [cross(prec[k] - temp[k], prec[k + 1] - temp[k + 1]), cross(prec[k] - 50, prec[k + 1] - 50)]) {
      if (s != null) cuts.push(s);
    }
    cuts.sort((a, b) => a - b);
    for (let j = 0; j + 1 < cuts.length; j++) {
      const a = cuts[j], b = cuts[j + 1];
      if (b - a < 1e-9) continue;
      const mid = (a + b) / 2;
      out.push({ x0: k + a, x1: k + b, t: [T(a), T(b)], p: [P(a), P(b)], humid: P(mid) > T(mid), wet: P(mid) > 50 });
    }
  }
  return out;
}

const f = (n) => +n.toFixed(1);
const escText = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

/**
 * The diagram. opts: {tmed, prec, tmin (12 each), place, period ("1991-2020"), months (12 short names), num(v, d) (a
 * number in the page's locale), labels: {frost (the bar's title)}, id (prefix for the patterns, unique on the page)}.
 */
export function walterSvg({ tmed, prec, tmin, place, period, months, num, labels = {}, id = "wl" }) {
  const g = geometry(tmed, prec);
  const pw = W - PAD.left - PAD.right, ph = H - PAD.top - PAD.bottom;
  const X = (k) => PAD.left + ((k + 0.5) * pw) / 12;
  const Y = (u) => PAD.top + ((g.hi - u) / (g.hi - g.lo)) * ph;
  const pt = (k, u) => `${f(X(k))},${f(Y(u))}`;
  const quad = (x0, x1, top, bottom) => `${pt(x0, top[0])} ${pt(x1, top[1])} ${pt(x1, bottom[1])} ${pt(x0, bottom[0])}`;

  const areas = pieces(g.temp, g.prec).map((s) => {
    const cap = s.p.map((v) => Math.min(v, 50));
    const parts = [];
    if (s.humid) {
      parts.push(`<polygon points="${quad(s.x0, s.x1, cap, s.t)}" fill="url(#${id}-humid)"/>`);
      if (s.wet) parts.push(`<polygon points="${quad(s.x0, s.x1, s.p, [50, 50])}" fill="${COLORS.solid}"/>`);
    } else parts.push(`<polygon points="${quad(s.x0, s.x1, s.t, s.p)}" fill="url(#${id}-dry)"/>`);
    return parts.join("");
  }).join("");

  const ticks = [];
  for (let u = g.lo; u <= g.hi; u += 10) {
    const y = f(Y(u));
    ticks.push(`<line x1="${PAD.left}" x2="${W - PAD.right}" y1="${y}" y2="${y}" class="wl-grid"${u === 50 && g.hi > 50 ? ' stroke-dasharray="3 3"' : ""}/>`,
      `<text x="${PAD.left - 4}" y="${y + 3}" text-anchor="end" fill="${COLORS.temp}">${escText(num(u, 0))}</text>`);
    if (u >= 0) ticks.push(`<text x="${W - PAD.right + 4}" y="${y + 3}" fill="${COLORS.prec}">${escText(num(mmAt(u), 0))}</text>`);
  }
  const base = H - PAD.bottom;
  const frost = frostMonths(tmin).map((on, k) => (on
    ? `<rect x="${f(X(k) - pw / 24)}" y="${base + 3}" width="${f(pw / 12)}" height="5" fill="${COLORS.frost}"><title>${escText(labels.frost || "")}</title></rect>`
    : "")).join("");
  const names = months.map((m, k) => `<text x="${f(X(k))}" y="${base + 20}" text-anchor="middle">${escText(m)}</text>`).join("");
  const line = (vals, color) => `<polyline points="${vals.map((u, k) => pt(k, u)).join(" ")}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round"/>`;
  const tMean = tmed.reduce((a, b) => a + b, 0) / 12, pSum = prec.reduce((a, b) => a + b, 0);

  return `<svg class="wl" viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${escText(`${place}, ${period}`)}" xmlns="http://www.w3.org/2000/svg" font-size="10" fill="currentColor">
  <defs>
    <pattern id="${id}-humid" width="4" height="4" patternUnits="userSpaceOnUse"><path d="M2 0V4" stroke="${COLORS.prec}" stroke-width="1"/></pattern>
    <pattern id="${id}-dry" width="4" height="4" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="0.9" fill="${COLORS.dry}"/></pattern>
  </defs>
  <text x="${PAD.left}" y="13" font-size="12" font-weight="600">${escText(place)}</text>
  <text x="${PAD.left}" y="26">${escText(period)}</text>
  <text x="${W - PAD.right}" y="26" text-anchor="end"><tspan fill="${COLORS.temp}">${escText(num(tMean, 1))} °C</tspan>  <tspan fill="${COLORS.prec}">${escText(num(pSum, 0))} mm</tspan></text>
  ${ticks.join("")}
  ${areas}
  ${line(g.prec, COLORS.prec)}
  ${line(g.temp, COLORS.temp)}
  <line x1="${PAD.left}" x2="${W - PAD.right}" y1="${base}" y2="${base}" class="wl-axis"/>
  ${frost}${names}
  <text x="${PAD.left - 4}" y="${PAD.top - 6}" text-anchor="end" fill="${COLORS.temp}">°C</text>
  <text x="${W - PAD.right + 4}" y="${PAD.top - 6}" fill="${COLORS.prec}">mm</text>
</svg>`;
}
