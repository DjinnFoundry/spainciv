// The album tab of «Adivina el hexágono»: Spain's silhouette with the collected provinces in their map colours, a
// banner per autonomous community, the notes on how often each province comes up, and the share buttons and card.
// The model is album.js. The silhouette is a small canvas painted when the tab opens, never part of the map's render.
import { country } from "../../app/country.js";
import { SANS, SERIF, fit, siteLabel } from "../../app/share.js";
import { css, luminance } from "../../color.js";
import { esc, int } from "../../format.js";
import { lang, t } from "../../i18n.js";
import { LONG_WAIT_DAYS, provincesOf } from "./album.js";
import { MIN_FIRST } from "./puzzle.js";

const SEA = "#0d2a47";
const NEUTRAL = "rgb(78,74,62)"; // a province not collected yet
const GOLD = "#ecd08e";
const CLOCK = `<svg class="al-clock" width="11" height="11" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="9.5" fill="none" stroke="currentColor" stroke-width="2.4"/><path d="M12 6.5V12l3.6 2.4" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>`;

// The land's extent in map km (the Canary inset included), worked out once per world.
const boxes = new WeakMap();
function landBox(w) {
  if (boxes.has(w)) return boxes.get(w);
  const { grid, raw } = w, b = [Infinity, Infinity, -Infinity, -Infinity];
  for (let i = 0; i < grid.size; i++) {
    if (raw.owner[i] < 0) continue;
    const x = grid.cx(i), y = grid.cy(i);
    b[0] = Math.min(b[0], x); b[1] = Math.min(b[1], y); b[2] = Math.max(b[2], x); b[3] = Math.max(b[3], y);
  }
  const pad = grid.R * 1.5, box = { x: b[0] - pad, y: b[1] - pad, w: b[2] - b[0] + 2 * pad, h: b[3] - b[1] + 2 * pad };
  boxes.set(w, box);
  return box;
}

/** The silhouette's height for a width, in the same units. */
export const silhouetteHeight = (w, width) => { const b = landBox(w); return (width * b.h) / b.w; };

/**
 * Paint the silhouette at `k` px per map km with the land box's corner at (x0, y0): every land hex as a rect (the
 * minimap's way), collected provinces in their map colour, then province borders (faint), community borders and, in
 * gold, the outline of each complete community.
 */
function paintSilhouette(ctx, w, view, k, x0, y0) {
  const { grid, raw } = w, box = landBox(w);
  const communityOf = new Map(), complete = new Set(), fill = new Map();
  for (const c of view.communities) {
    if (c.complete) complete.add(c.code);
    for (const p of c.provinces) {
      communityOf.set(p.idx, c.code);
      fill.set(p.idx, p.days.length ? css(w.stateColor[p.idx] || [190, 190, 190]) : NEUTRAL);
    }
  }
  const X = (x) => x0 + (x - box.x) * k, Y = (y) => y0 + (y - box.y) * k;
  const cw = grid.W * k + 0.6, ch = grid.H * k + 0.6;
  for (let i = 0; i < grid.size; i++) {
    const o = raw.owner[i];
    if (o < 0) continue;
    ctx.fillStyle = fill.get(o) || NEUTRAL;
    ctx.fillRect(X(grid.cx(i) - grid.W / 2), Y(grid.cy(i) - grid.H / 2), cw, ch);
  }
  // Each hex edge between two provinces once (from the lower index), and every edge on the outline of a complete
  // community.
  const edges = { province: new Path2D(), community: new Path2D(), complete: new Path2D() };
  const edge = (path, i, d) => {
    const [ax, ay] = grid.corners[d], [bx, by] = grid.corners[(d + 1) % 6], x = grid.cx(i), y = grid.cy(i);
    path.moveTo(X(x + ax), Y(y + ay));
    path.lineTo(X(x + bx), Y(y + by));
  };
  for (let i = 0; i < grid.size; i++) {
    const o = raw.owner[i];
    if (o < 0) continue;
    const ci = communityOf.get(o);
    for (let d = 0; d < 6; d++) {
      const j = grid.neighbour(i, d), q = j < 0 ? -1 : raw.owner[j];
      if (q === o) continue;
      const cj = q < 0 ? undefined : communityOf.get(q);
      if (complete.has(ci) && cj !== ci) edge(edges.complete, i, d);
      if (q < 0 || j < i) continue;
      edge(ci === cj && ci != null ? edges.province : edges.community, i, d);
    }
  }
  const stroke = (path, style, width) => { ctx.strokeStyle = style; ctx.lineWidth = width; ctx.stroke(path); };
  ctx.lineJoin = "round";
  stroke(edges.province, "rgba(20,16,10,.35)", Math.max(0.5, k * 0.9));
  stroke(edges.community, "rgba(12,10,6,.9)", Math.max(0.9, k * 1.8));
  stroke(edges.complete, GOLD, Math.max(1.4, k * 3));
}

/** Draw the silhouette into `canvas`, `cssWidth` CSS px wide, at the device's pixel ratio. */
export function drawSilhouette(canvas, w, view, cssWidth) {
  const dpr = globalThis.devicePixelRatio || 1, cssHeight = Math.round(silhouetteHeight(w, cssWidth));
  canvas.width = Math.round(cssWidth * dpr);
  canvas.height = Math.round(cssHeight * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssWidth, cssHeight);
  paintSilhouette(ctx, w, view, cssWidth / landBox(w).w, 0, 0);
}

// A list of names in the language ("Ceuta y Melilla", "Ceuta and Melilla").
const list = (names) => {
  try {
    return new Intl.ListFormat(lang(), { type: "conjunction" }).format(names);
  } catch {
    return names.join(", ");
  }
};

const counts = (view) => ({
  count: t("game.album.count", { got: view.got, total: view.total }),
  communities: t("game.album.communities", { n: view.complete, total: view.communitiesTotal }),
});

/** What a province's chip says: its pool hexes, how often it comes up and how many times it was won. */
export function provinceLine(p, view) {
  return [
    p.name,
    t("game.album.hexes", { n: p.hexes, pool: int(view.poolSize) }),
    t("game.album.every", { n: p.everyDays }),
    p.days.length ? t("game.album.won", { n: p.days.length }) : t("game.album.notYet"),
  ].join(" · ");
}

// The notes under the banners, all worked out from the view.
function notes(view, { g, stats, storageOk }) {
  const provs = provincesOf(view), out = [];
  if (!storageOk) out.push(t("game.album.noStorage"));
  if (!view.got) out.push(t("game.album.empty"));
  if (provs.length) {
    const most = Math.max(...provs.map((p) => p.hexes)), least = Math.min(...provs.map((p) => p.hexes));
    const named = (n) => list(provs.filter((p) => p.hexes === n).map((p) => p.name));
    out.push(t("game.album.note", { pool: int(view.poolSize), most, mostName: named(most), least, leastName: named(least),
      days: LONG_WAIT_DAYS }));
  }
  // Provinces out of the game, one line per reason (and per first-clue area).
  const groups = new Map();
  for (const o of view.outside) {
    const area = o.reason === "first" && o.cell >= 0 ? `${g.zone(o.cell)}|${g.sea(o.cell)}|${o.fits}` : "";
    const key = `${o.reason}|${area}`;
    if (!groups.has(key)) groups.set(key, { ...o, names: [] });
    groups.get(key).names.push(o.name);
  }
  for (const o of groups.values()) {
    const n = o.names.length, names = list(o.names);
    if (o.reason === "first" && o.cell >= 0) {
      const sea = t(`game.sea.${g.sea(o.cell)}`);
      out.push(t("game.album.outside.first", { n, list: names, zone: t(`game.zone.${g.zone(o.cell)}`),
        sea: sea[0].toLocaleLowerCase(lang()) + sea.slice(1), fits: t("game.album.hexCount", { n: o.fits }), min: MIN_FIRST }));
    } else out.push(t("game.album.outside.rules", { n, list: names }));
  }
  if (view.unassigned) out.push(t("game.album.unassigned", { n: view.unassigned }));
  return out;
}

/**
 * Fill `el` with the album. ctx: {w, g (gameData), stats, storageOk, canShare, onCopy, onShare, onImage}. The
 * silhouette is painted once here; the chips show their line on a tap (a phone has no tooltips).
 */
export function renderAlbum(el, view, ctx) {
  const c = counts(view);
  const chip = (p) => {
    const line = provinceLine(p, view), times = p.days.length > 1 ? `<span class="al-times">×${p.days.length}</span>` : "";
    const rgb = ctx.w.stateColor[p.idx] || [190, 190, 190];
    const style = p.days.length ? ` style="--al-c:${css(rgb)};--al-t:${luminance(rgb) > 0.28 ? "#14100a" : "#fbf4e2"}"` : "";
    const slow = p.slow ? CLOCK : "";
    return `<button type="button" class="al-chip${p.days.length ? " got" : ""}"${style} title="${esc(line)}" data-line="${esc(line)}"
      aria-label="${esc(line)}">${slow}<span>${esc(p.name)}</span>${times}</button>`;
  };
  const banners = view.communities.map((cm) => `
    <li class="al-comm${cm.complete ? " complete" : ""}">
      <h4><span>${esc(cm.name)}</span> <span class="al-of">${cm.got}/${cm.total}</span></h4>
      <div class="al-bar" aria-hidden="true"><i style="width:${(100 * cm.got) / cm.total}%"></i></div>
      <div class="al-chips">${cm.provinces.map(chip).join("")}</div>
      <p class="al-line muted" hidden></p></li>`).join("");
  el.innerHTML = `
    <section class="al">
      <h3 class="al-title">${esc(t("game.album.title"))}</h3>
      <p class="al-counts">${esc(c.count)} · ${esc(c.communities)}</p>
      <canvas class="al-map" role="img" aria-label="${esc(t("game.album.mapLabel", c))}"></canvas>
      <ul class="al-comms">${banners}</ul>
      ${notes(view, ctx).map((n) => `<p class="al-note muted">${esc(n)}</p>`).join("")}
      <div class="gm-buttons al-buttons"><button type="button" class="btn al-copy">${esc(t("game.album.copy"))}</button>
        ${ctx.canShare ? `<button type="button" class="btn al-native">${esc(t("game.share"))}</button>` : ""}
        <button type="button" class="btn al-image">${esc(t("game.album.image"))}</button></div>
    </section>`;
  const canvas = el.querySelector(".al-map");
  drawSilhouette(canvas, ctx.w, view, canvas.getBoundingClientRect().width || 320);
  el.querySelectorAll(".al-chip").forEach((b) => (b.onclick = () => {
    const p = b.closest(".al-comm").querySelector(".al-line"), same = !p.hidden && p.textContent === b.dataset.line;
    p.hidden = same;
    p.textContent = same ? "" : b.dataset.line;
  }));
  el.querySelector(".al-copy").onclick = ctx.onCopy;
  el.querySelector(".al-image").onclick = ctx.onImage;
  const native = el.querySelector(".al-native");
  if (native) native.onclick = ctx.onShare;
}

export const CARD_W = 1200;
export const CARD_H = 630;

/** The album as a 1200 × 630 card: the silhouette, the counts, the site and the boundaries' licence notice. */
export function albumCard(view, w) {
  const cv = document.createElement("canvas");
  cv.width = CARD_W;
  cv.height = CARD_H;
  const ctx = cv.getContext("2d");
  const bg = ctx.createLinearGradient(0, 0, 0, CARD_H);
  bg.addColorStop(0, "#1a2a3c");
  bg.addColorStop(1, "#0f1822");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, CARD_W, CARD_H);

  // The silhouette on the sea, left, as large as fits.
  const mapW = 760, pad = 28, box = landBox(w);
  const k = Math.min((mapW - 2 * pad) / box.w, (CARD_H - 2 * pad - 24) / box.h);
  const sw = box.w * k, sh = box.h * k, sx = pad + (mapW - 2 * pad - sw) / 2, sy = pad + (CARD_H - 2 * pad - 24 - sh) / 2;
  ctx.fillStyle = SEA;
  ctx.fillRect(pad, pad, mapW - 2 * pad, CARD_H - 2 * pad);
  paintSilhouette(ctx, w, view, k, sx, sy);

  // The licence notice the boundaries must carry, under the map.
  const notice = (country().notices || []).join(" · ");
  if (notice) {
    ctx.font = `13px ${SANS}`;
    ctx.fillStyle = "#d8cba8";
    ctx.textBaseline = "middle";
    ctx.fillText(fit(ctx, notice, mapW - 2 * pad - 16), pad + 8, CARD_H - pad - 12);
  }

  // The counts, right.
  const x = mapW + 12, right = CARD_W - 48;
  ctx.textBaseline = "alphabetic";
  ctx.fillStyle = "#b9ab88";
  ctx.font = `italic 22px ${SERIF}`;
  ctx.fillText(fit(ctx, t("game.title"), right - x), x, 120);
  ctx.fillStyle = GOLD;
  ctx.font = `36px ${SERIF}`;
  ctx.fillText(fit(ctx, t("game.album.cardTitle"), right - x), x, 168);
  ctx.fillStyle = "#c9a45c";
  ctx.fillRect(x, 192, right - x, 2);
  ctx.fillStyle = "#f3e6c4";
  ctx.font = `bold 92px ${SERIF}`;
  ctx.fillText(`${view.got}/${view.total}`, x, 300);
  const c = counts(view);
  ctx.font = `24px ${SERIF}`;
  ctx.fillText(fit(ctx, c.count, right - x), x, 344);
  ctx.fillStyle = "#d8cba8";
  ctx.font = `20px ${SANS}`;
  ctx.fillText(fit(ctx, c.communities, right - x), x, 384);
  ctx.fillStyle = "#c9a45c";
  ctx.font = `bold 20px ${SERIF}`;
  ctx.fillText(fit(ctx, siteLabel(), right - x), x, CARD_H - 60);

  ctx.strokeStyle = "rgba(201,164,92,.85)";
  ctx.lineWidth = 2;
  ctx.strokeRect(1, 1, CARD_W - 2, CARD_H - 2);
  return cv;
}
