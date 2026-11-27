// The fog of war's art: parchment clouds over the unexplored land hexes, painted once into an offscreen canvas in
// world km and drawn over the map with one drawImage per frame (an overlay, outside the cached static map, so the
// static cache, its region repaints on a pan and its idle margin work are untouched: DECISIONS A18, A26).
// A reveal repaints only the rectangle around the cells it uncovered.
import { hash01 } from "../../hex.js";

const MAX_PX = 4096; // longest side of the fog canvas
const PX_PER_KM = 2; // at most: a 10 km hex is 20 px across, soft enough for clouds when zoomed in (Spain: 3100 × 2250 px)
const PAPER = "#e6d7b4";
const SHADOW = "rgba(70, 52, 28, 0.42)";
const SPECKS = ["rgba(150,120,70,.20)", "rgba(255,248,228,.35)", "rgba(120,92,50,.14)"];

// The puffs of one hex, [dx, dy, r] in units of the hex radius: a round core and two smaller ones off-centre, so the
// edge of the fog is a row of cloud tops rather than hexagons. They reach about 1.05 R from the centre.
function puffs(i) {
  const a = hash01(i, 11) * Math.PI * 2, b = a + 2.1 + hash01(i, 12) * 2;
  const o = 0.42;
  return [[0, 0, 0.98], [Math.cos(a) * o, Math.sin(a) * o, 0.62], [Math.cos(b) * o, Math.sin(b) * o, 0.58]];
}
const MOTTLE = [[21, "rgba(255, 251, 238, .28)"], [31, "rgba(125, 95, 52, .10)"]];
const REACH = 1.1; // the farthest puff edge, in hex radii, plus the shadow's offset
const SHADOW_OFF = [0.12, 0.16];

// A small parchment tile: paper with specks and faint fibres, repeated across the fog.
function paperTile() {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d");
  g.fillStyle = PAPER;
  g.fillRect(0, 0, 128, 128);
  for (let k = 0; k < 900; k++) {
    g.fillStyle = SPECKS[k % SPECKS.length];
    const r = 0.4 + hash01(k, 3) * 1.6;
    g.beginPath();
    g.arc(hash01(k, 1) * 128, hash01(k, 2) * 128, r, 0, Math.PI * 2);
    g.fill();
  }
  g.strokeStyle = "rgba(140,110,60,.10)";
  g.lineWidth = 1;
  for (let k = 0; k < 40; k++) {
    const x = hash01(k, 5) * 128, y = hash01(k, 6) * 128, len = 10 + hash01(k, 7) * 30, a = hash01(k, 8) * Math.PI;
    g.beginPath();
    g.moveTo(x, y);
    g.lineTo(x + Math.cos(a) * len, y + Math.sin(a) * len);
    g.stroke();
  }
  return c;
}

/**
 * createFog(grid, model) → {draw(ctx), paint(cells?), bounds}
 *   draw(ctx)      ctx in world km (an app overlay): one drawImage of the fog canvas
 *   paint(cells)   repaint the fog around these cells (all of it when cells is omitted)
 */
export function createFog(grid, model) {
  const R = grid.R;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const i of model.land) {
    const x = grid.cx(i), y = grid.cy(i);
    if (x < x0) x0 = x;
    if (x > x1) x1 = x;
    if (y < y0) y0 = y;
    if (y > y1) y1 = y;
  }
  const pad = R * (REACH + 0.3);
  x0 -= pad; y0 -= pad; x1 += pad; y1 += pad;
  const k = Math.min(PX_PER_KM, MAX_PX / Math.max(x1 - x0, y1 - y0, 1));
  const cv = document.createElement("canvas");
  cv.width = Math.ceil((x1 - x0) * k);
  cv.height = Math.ceil((y1 - y0) * k);
  const g = cv.getContext("2d");
  const paper = g.createPattern(paperTile(), "repeat");
  // The pattern is laid in canvas pixels, whatever the km transform.
  if (paper?.setTransform && typeof DOMMatrix === "function") paper.setTransform(new DOMMatrix().translate(x0, y0).scale(1 / k));
  const toPx = (x, y) => [(x - x0) * k, (y - y0) * k];

  function puffPath(i, ox = 0, oy = 0, grow = 1) {
    const cx = grid.cx(i) + ox * R, cy = grid.cy(i) + oy * R;
    for (const [dx, dy, r] of puffs(i)) {
      g.moveTo(cx + dx * R + r * R * grow, cy + dy * R);
      g.arc(cx + dx * R, cy + dy * R, r * R * grow, 0, Math.PI * 2);
    }
  }

  // Paint the fog inside [rx0, ry0, rx1, ry1] km (whole device px), from every unexplored hex that reaches into it.
  function paintRect(rx0, ry0, rx1, ry1) {
    const [px0, py0] = toPx(rx0, ry0), [px1, py1] = toPx(rx1, ry1);
    const X0 = Math.max(0, Math.floor(px0)), Y0 = Math.max(0, Math.floor(py0));
    const X1 = Math.min(cv.width, Math.ceil(px1)), Y1 = Math.min(cv.height, Math.ceil(py1));
    if (X1 <= X0 || Y1 <= Y0) return;
    g.save();
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.clearRect(X0, Y0, X1 - X0, Y1 - Y0);
    g.beginPath();
    g.rect(X0, Y0, X1 - X0, Y1 - Y0);
    g.clip();
    g.setTransform(k, 0, 0, k, -x0 * k, -y0 * k);
    const reach = R * (REACH + 0.2);
    const cells = model.land.filter((i) => !model.isExplored(i) && grid.cx(i) + reach > rx0 && grid.cx(i) - reach < rx1
      && grid.cy(i) + reach > ry0 && grid.cy(i) - reach < ry1);
    // Shadows first, all of them, so a cloud's shadow never darkens the cloud next to it.
    g.beginPath();
    for (const i of cells) puffPath(i, SHADOW_OFF[0], SHADOW_OFF[1], 1.04);
    g.fillStyle = SHADOW;
    g.fill();
    g.beginPath();
    for (const i of cells) puffPath(i);
    g.fillStyle = paper || PAPER;
    g.fill();
    // Mottling: a light and a dark spot per hex, so the clouds are not one flat sheet.
    MOTTLE.forEach(([salt, color]) => {
      g.beginPath();
      for (const i of cells) {
        const a = hash01(i, salt) * Math.PI * 2, o = hash01(i, salt + 1) * 0.5 * R, r = (0.35 + hash01(i, salt + 2) * 0.4) * R;
        const x = grid.cx(i) + Math.cos(a) * o, y = grid.cy(i) + Math.sin(a) * o;
        g.moveTo(x + r, y);
        g.arc(x, y, r, 0, Math.PI * 2);
      }
      g.fillStyle = color;
      g.fill();
    });
    g.restore();
  }

  function paint(cells) {
    if (!cells) return paintRect(x0, y0, x1, y1);
    if (!cells.length) return;
    let a = Infinity, b = Infinity, c = -Infinity, d = -Infinity;
    for (const i of cells) {
      const x = grid.cx(i), y = grid.cy(i);
      if (x < a) a = x;
      if (x > c) c = x;
      if (y < b) b = y;
      if (y > d) d = y;
    }
    const m = R * (REACH + 0.2); // what the uncovered hexes' own puffs and shadows had painted
    paintRect(a - m, b - m, c + m, d + m);
  }

  return {
    bounds: { x0, y0, x1, y1 },
    canvas: cv,
    paint,
    draw(ctx) {
      ctx.imageSmoothingEnabled = true;
      ctx.drawImage(cv, x0, y0, cv.width / k, cv.height / k);
    },
  };
}
