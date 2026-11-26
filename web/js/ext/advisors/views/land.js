// Land advisor: national land cover, where each cover dominates, the states' make-up and who works the land.
import { esc, fin, ratio } from "../core/util.js";
import { pct, int, count3 } from "../core/fmt.js";
import { shareBar, barList, donut, smallMultiples } from "../core/charts.js";
import { createTable } from "../core/table.js";
import { section, tiles, segmented, lensButton, sourcesHtml, topBy, frameBtn } from "../core/view.js";
import { LAND_KEYS, LAND_LABEL, LAND_COLOR, rowsHighlight } from "../core/data.js";
import { t } from "../../../i18n.js";

const SHORT = { forest: "adv.landShort.forest", crop: "adv.landShort.crop", pasture: "adv.landShort.pasture", grass: "adv.landShort.grass",
  shrub: "adv.landShort.shrub", wetland: "adv.landShort.wetland", developed: "adv.landShort.developed" };

const LENS_OF = { forest: "forest", crop: "farmland", pasture: "farmland", developed: "developed" };

export function mount(ctx) {
  const { app, data, el, link } = ctx;
  const w = app.w;
  const P = w.raw.pct;
  const owner = w.raw.owner;
  const { states } = data.levels;
  if (!P) {
    el.innerHTML = `<p class="adv-empty pad">${t("adv.land.noCover")}</p>`;
    return {};
  }

  // --- national shares and dominant cover per hex ---------------------------------------------------------------
  const sums = Object.fromEntries(LAND_KEYS.map((k) => [k, 0]));
  const dominant = new Map(LAND_KEYS.map((k) => [k, []]));
  let cells = 0;
  for (let i = 0; i < w.grid.size; i++) {
    if (!(owner[i] >= 0)) continue;
    let tot = 0, best = null, bv = 0;
    for (const k of LAND_KEYS) {
      const v = P[k]?.[i] || 0;
      tot += v;
      if (v > bv) { bv = v; best = k; }
    }
    if (tot <= 0) continue; // no land-cover samples
    cells++;
    for (const k of LAND_KEYS) sums[k] += P[k]?.[i] || 0;
    dominant.get(best).push(i);
  }
  const share = Object.fromEntries(LAND_KEYS.map((k) => [k, cells ? sums[k] / (cells * 100) : 0]));
  const other = Math.max(0, 1 - LAND_KEYS.reduce((a, k) => a + share[k], 0));

  el.insertAdjacentHTML("beforeend", tiles([
    { label: t("adv.land.forestTile"), value: pct(share.forest, 0), sub: t("adv.land.ofLand"), color: LAND_COLOR.forest },
    { label: t("adv.land.farmland"), value: pct(share.crop + share.pasture, 0), sub: t("adv.land.cropsPasture"), color: LAND_COLOR.crop },
    { label: t("adv.land.builtUp"), value: pct(share.developed, 1), sub: t("adv.land.developedLand"), color: LAND_COLOR.developed },
  ]));

  // --- composition ----------------------------------------------------------------------------------------------
  const cBody = section(el, { title: t("adv.land.title"), kicker: t("adv.land.kicker"), note: t("adv.land.note") });
  let pinned = null;
  const parts = [...LAND_KEYS.map((k) => ({ key: k, label: LAND_LABEL[k], value: share[k], color: LAND_COLOR[k], text: pct(share[k]) })), { key: "other", label: t("adv.land.other"), value: other, color: "#6c6358", text: pct(other) }].sort((a, b) => (a.key === "other") - (b.key === "other") || b.value - a.value);
  const domHighlight = (k, dim = true) => (dominant.has(k) ? { cells: new Set(dominant.get(k)), dimOthers: dim, color: LAND_COLOR[k] } : null);
  const sb = shareBar(cBody, {
    parts,
    onHover: (p) => link.hover(p && p.key !== "other" ? { ...domHighlight(p.key), color: "#fff3c4" } : null),
    onClick: (p) => pin(p.key === "other" || pinned === p.key ? null : p.key),
  });
  const pinInfo = document.createElement("div");
  pinInfo.className = "adv-brushinfo";
  cBody.appendChild(pinInfo);
  const lensRow = document.createElement("div");
  lensRow.className = "adv-row";
  for (const [id, label] of [["forest", t("adv.land.forestLens")], ["farmland", t("adv.land.farmLens")], ["developed", t("adv.land.builtLens")]]) {
    const b = lensButton(app, id, label);
    if (b) lensRow.appendChild(b);
  }
  cBody.appendChild(lensRow);
  function pin(k) {
    pinned = k;
    sb.setSelected(k);
    link.base(k ? domHighlight(k) : null, { frame: true });
    if (!k) { pinInfo.innerHTML = ""; return; }
    const n = dominant.get(k).length;
    const lens = LENS_OF[k] && app.lensById.get(LENS_OF[k]);
    pinInfo.innerHTML = `${t("adv.land.pinned", { cover: esc(LAND_LABEL[k]), n: int(n), share: pct(n / cells, 0), all: pct(share[k]) })}
      ${lens ? `<button type="button" class="adv-mini" data-lens="${lens.id}">${t("adv.land.showLens", { name: esc(lens.name) })}</button>` : ""}${frameBtn()}<button type="button" class="adv-mini" data-clear>${t("adv.clear")}</button>`;
  }
  pinInfo.addEventListener("click", (e) => {
    if (e.target.closest("[data-clear]")) pin(null);
    const l = e.target.closest("[data-lens]")?.dataset.lens;
    if (l) app.setLens(l);
  });

  // --- per state ------------------------------------------------------------------------------------------------
  const sBody = section(el, { title: t("adv.land.states.title"), note: t("adv.land.states.note") });
  const stRows = states.rows.filter((r) => LAND_KEYS.some((k) => fin(r.v[`land_${k}`])));
  const comp = (r) => `<span class="adv-minibar">${LAND_KEYS.map((k) => {
    const v = r.v[`land_${k}`];
    return fin(v) && v > 0 ? `<i style="width:${(v * 100).toFixed(2)}%;background:${LAND_COLOR[k]}" title="${esc(`${LAND_LABEL[k]} ${pct(v)}`)}"></i>` : "";
  }).join("")}</span>`;
  const domOf = (r) => LAND_KEYS.reduce((b, k) => ((r.v[`land_${k}`] ?? -1) > (r.v[`land_${b}`] ?? -1) ? k : b), LAND_KEYS[0]);
  let sortKey = "forest";
  const colsFor = (k) => [
    { key: "name", label: states.field("name").label, align: "l", width: "minmax(0,1.1fr)", value: (r) => r.name, text: (r) => r.name },
    { key: "comp", label: t("adv.land.col.land"), align: "l", width: "minmax(0,1.6fr)", value: (r) => r.v[`land_${k}`], html: comp, title: t("adv.table.sortBy", { label: LAND_LABEL[k].toLowerCase() }) },
    { key: "share", label: LAND_LABEL[k], value: (r) => r.v[`land_${k}`], html: (r) => `<span class="dot" style="background:${LAND_COLOR[k]}"></span>${pct(r.v[`land_${k}`], 0)}` },
    { key: "dom", label: t("adv.land.col.largest"), align: "l", width: "minmax(0,.9fr)", value: (r) => LAND_LABEL[domOf(r)], text: (r) => LAND_LABEL[domOf(r)] },
  ];
  const sortSeg = document.createElement("div");
  sortSeg.className = "adv-row";
  sBody.appendChild(sortSeg);
  segmented(sortSeg, {
    label: t("adv.sortBy"), value: sortKey,
    options: LAND_KEYS.map((k) => ({ value: k, label: t(SHORT[k]) })),
    onChange: (k) => { sortKey = k; table.setColumns(colsFor(k), { key: "share", dir: "desc" }); drawShape(); },
  });
  let shape = "table";
  segmented(sortSeg, { label: t("adv.showAs"), value: shape, options: [{ value: "table", label: t("adv.table.tab") }, { value: "grid", label: t("adv.grid") }], onChange: (v) => { shape = v; drawShape(); } });
  const tableHost = document.createElement("div");
  const gridHost = document.createElement("div");
  sBody.append(tableHost, gridHost);
  const table = createTable(tableHost, {
    caption: t("adv.land.caption"), rank: true, maxHeight: 320, rows: stRows, columns: colsFor(sortKey), sort: { key: "share", dir: "desc" },
    onHover: (r) => link.hover(r ? rowsHighlight(states, [r]) : null),
    onClick: (r) => states.focus(r),
  });
  // Small multiples: one donut per state, sorted by the chosen cover.
  let grid = null;
  function drawShape() {
    tableHost.hidden = shape !== "table";
    gridHost.hidden = shape !== "grid";
    if (shape !== "grid") return;
    gridHost.innerHTML = "";
    const sorted = [...stRows].sort((a, b) => (b.v[`land_${sortKey}`] ?? -1) - (a.v[`land_${sortKey}`] ?? -1));
    grid = smallMultiples(gridHost, {
      min: 92,
      items: sorted.map((r) => ({ key: r.key, label: r.v.abbr || r.key, sub: pct(r.v[`land_${sortKey}`], 0), row: r })),
      render: (cell, it) => donut(cell, {
        interactive: false, size: 62, thickness: 12,
        parts: LAND_KEYS.map((k) => ({ key: k, label: LAND_LABEL[k], value: it.row.v[`land_${k}`], color: LAND_COLOR[k] })),
        center: { big: pct(it.row.v[`land_${sortKey}`], 0), small: "" },
        ariaLabel: `${it.row.name}: ${LAND_KEYS.map((k) => `${LAND_LABEL[k]} ${pct(it.row.v[`land_${k}`], 0)}`).join(", ")}`,
      }),
      onHover: (it) => link.hover(it ? rowsHighlight(states, [it.row]) : null),
      onClick: (it) => states.focus(it.row),
    });
  }
  drawShape();

  // --- who works the land ---------------------------------------------------------------------------------------
  const food = app.data.nation.yields?.find((y) => y.key === "food");
  const fBody = section(el, { title: t("adv.land.food.title"), note: t("adv.land.food.note", { desc: esc(food?.description || t("adv.land.food.fallback")) }) });
  const fHost = document.createElement("div");
  let fLevel = "states";
  segmented(fBody, { label: t("adv.areas"), value: fLevel, options: [{ value: "states", label: states.label }, { value: "metros", label: data.levels.metros.label }], onChange: (v) => { fLevel = v; drawFood(); } });
  fBody.appendChild(fHost);
  function drawFood() {
    fHost.innerHTML = "";
    const lv = data.levels[fLevel];
    const list = topBy(lv.rows, (r) => ratio(r.v.y_food, r.v.employed), { n: 10, min: fLevel === "metros" ? 100000 : 0 });
    barList(fHost, {
      rank: true, ariaLabel: t("adv.land.food.aria"),
      rows: list.map((x) => ({ key: x.r.key, label: x.r.name, sub: t("adv.nWorkers", { n: count3(x.r.v.y_food) }), value: x.v, text: pct(x.v), color: food?.color, row: x.r })),
      onHover: (r) => link.hover(r ? rowsHighlight(lv, [r.row]) : null),
      onClick: (r) => lv.focus(r.row),
    });
    if (fLevel === "metros") fHost.insertAdjacentHTML("beforeend", `<p class="adv-note">${t("adv.land.food.metroMin")}</p>`);
  }
  drawFood();

  el.insertAdjacentHTML("beforeend", sourcesHtml(data, ["nlcd", "acs_1yr"], [
    t("adv.land.c1"),
    t("adv.land.c2"),
    t("adv.land.c3"),
  ]));

  return {
    onMapHover(h) {
      const r = h.cell >= 0 ? states.rowAtCell(h.cell) : null;
      table.setHot(r ? r.key : null);
      if (shape === "grid") grid?.setHot(r ? r.key : null);
      if (h.cell >= 0 && owner[h.cell] >= 0) {
        let best = null, bv = 0;
        for (const k of LAND_KEYS) { const v = P[k]?.[h.cell] || 0; if (v > bv) { bv = v; best = k; } }
        sb.setHot(best);
      } else sb.setHot(null);
    },
    onEscape() {
      if (pinned) { pin(null); return true; }
      return false;
    },
  };
}
