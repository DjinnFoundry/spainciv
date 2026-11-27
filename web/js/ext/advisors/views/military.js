// Military advisor ("General"): the installations and ranges of military.json on the map, by region, and the cities
// they garrison. On the US map it adds troops by state (DMDC), defense dollars by state (OLDCC), the Encampment metros,
// and veterans and armed-forces residents by county (ACS, counties.json); Spain's file has none of those blocks.
import { esc, fin, el as mk } from "../core/util.js";
import { int, pct, money, count3, dollars } from "../core/fmt.js";
import { stackedBars, sizeLegend, swatchLegend } from "../core/charts.js";
import { createTable } from "../core/table.js";
import { section, tiles, chips, segmented, mapPicker, sourcesHtml } from "../core/view.js";
import { rowsHighlight, extendData } from "../core/data.js";
import { countyLens, stateLens } from "../core/lenses.js";
import { frameBox, focusPoint } from "../core/frame.js";
import { t, usOr } from "../../../i18n.js";
import { country } from "../../../app/country.js";

// Original colours per component (branch hues; reserve = lighter, Guard = gold tones; Spain's UME in its orange).
const COMP_COLOR = {
  army: "#7d9a46", navy: "#3f6fc2", air_force: "#6fb3e0", marines: "#c24a3e",
  army_reserve: "#a8bd78", navy_reserve: "#8aa6db", air_force_reserve: "#a9d3ee", marine_reserve: "#e08f86",
  army_guard: "#d6b04a", air_guard: "#e6cf86", ume: "#e08a3c", other: "#9a9aa8",
};
// Short component labels (adv.mil.comp.<id>); the data's own name is used for any other id.
const COMP_SHORT = new Set(Object.keys(COMP_COLOR));
const COMP_GROUPS = [
  { id: "active", ids: ["army", "navy", "air_force", "marines"] },
  { id: "reserve", ids: ["army_reserve", "navy_reserve", "air_force_reserve", "marine_reserve"] },
  { id: "guard", ids: ["army_guard", "air_guard"] },
  { id: "other", ids: ["other"] },
];
const tierLabel = (tier) => (["major", "base", "site"].includes(tier) ? t(`adv.mil.tier.${tier}`) : tier);
const statusLabel = (s) => (["act", "semi", "care"].includes(s) ? t(`adv.mil.status.${s}`) : s);
// km²: circles stop growing at the largest of these the data reaches (3,000 in the US, where a few ranges are 10,000 km²+)
const AREA_CAPS = [3000, 1000, 300, 100];
const STEEL_RAMP = ["#141b26", "#2a3a52", "#46627f", "#6f91ad", "#a9c3d6", "#eef4f8"];
const SPEND_RAMP = ["#1b1410", "#3e2a1c", "#6e4626", "#a66f34", "#d9a457", "#f8e2a6"];

export async function mount(ctx) {
  const { app, data, el, link } = ctx;
  await extendData(data, ["military"]);
  const mil = app.data.military;
  if (!mil) {
    el.innerHTML = `<p class="adv-empty pad">${t("adv.military.none")}</p>`;
    return {};
  }
  const US = country().id === "us";
  const region = country().levels.region, regionLc = region.one.toLowerCase();
  const { states: stLevel, metros, counties } = data.levels;
  const comps = (mil.components || []).map((c) => ({ ...c, color: COMP_COLOR[c.id] || "#9a9aa8", short: COMP_SHORT.has(c.id) ? t(`adv.mil.comp.${c.id}`) : c.name }));
  const compById = new Map(comps.map((c) => [c.id, c]));
  const insts = (mil.installations || []).map((it, i) => ({ ...it, key: it.id || String(i) }));
  const instByKey = new Map(insts.map((it) => [it.key, it]));
  const nat = mil.national || {};
  const maxArea = Math.max(0, ...insts.map((it) => it.area_km2 || 0));
  const AREA_CAP = AREA_CAPS.find((c) => c <= maxArea) ?? AREA_CAPS.at(-1);
  const regionCol = US ? "40px" : "46px";
  const vint = mil.vintage || {};
  const stateIdx = (abbr) => stLevel.byKey.get(abbr)?.ref ?? null;
  const stateName = (abbr) => stLevel.byKey.get(abbr)?.name || STATE_NAMES[abbr] || abbr;
  const instCells = (it) => (it.cells && it.cells.length ? it.cells : it.cell != null ? [it.cell] : []);
  // cell → the installation boundaries covering it (largest first), for map → dashboard.
  const cellInst = new Map();
  for (const it of insts) for (const c of it.cells || []) if (!cellInst.has(c)) cellInst.set(c, it);
  const cellRange = new Map();
  for (const r of mil.ranges || []) for (const c of r.cells || []) if (!cellRange.has(c)) cellRange.set(c, r);

  const st = { comps: new Set(comps.map((c) => c.id)), tier: "big", state: null };

  // --- headline -------------------------------------------------------------------------------------------------
  const P = nat.personnel || {}, S = nat.spending || {};
  const ranges = (mil.ranges || []).map((r) => ({ ...r, key: r.id }));
  const nTier = (tier) => insts.filter((it) => it.tier === tier).length;
  el.insertAdjacentHTML("beforeend", tiles(US ? [
    { label: t("adv.mil.activeDuty"), value: count3(P.active?.total), sub: t("adv.mil.plusGuard", { n: count3(P.guard_reserve?.total) }), color: "#a9c3d6" },
    { label: t("adv.mil.spending"), value: money(S.total), sub: t("adv.mil.spendingSub", { pct: pct(S.pct_gdp), vintage: esc(vint.spending || "") }) },
    { label: t("adv.mil.veterans"), value: count3(nat.veterans), sub: t("adv.mil.veteransSub") },
  ] : [
    { label: t("adv.mil.installations"), value: int(insts.length), sub: t("adv.mil.tierCounts", { major: int(nTier("major")), base: int(nTier("base")) }), color: "#a9c3d6" },
    { label: t("adv.mil.land"), value: `${count3(nat.area_km2)} km²`, sub: t("adv.mil.landSub") },
    { label: t("adv.mil.ranges.tile"), value: int(ranges.length), sub: t("adv.mil.rangesSub", { km2: count3(ranges.reduce((a, r) => a + (r.area_km2 || 0), 0)) }) },
  ]) + `<p class="adv-callout">${usOr("adv.mil.callout")}</p>`);

  // --- map colour -----------------------------------------------------------------------------------------------
  const mapRow = mk("div", "adv-sec adv-mapsec");
  el.appendChild(mapRow);
  const afLens = () => countyLens(data, "armed_forces_pct", {
    name: t("adv.mil.lens.af"), emoji: "🎖️", ramp: STEEL_RAMP, description: t("adv.mil.lens.af.desc"),
  });
  const perResLens = () => stateLens(data, "def-per-resident", (abbr) => mil.states?.[abbr]?.spending?.per_resident ?? null, {
    name: t("adv.mil.lens.perRes"), emoji: "💵", format: "usd", unit: t("adv.mil.lens.perRes.unit"), ramp: SPEND_RAMP, source: "oldcc_spending",
    description: t("adv.mil.lens.perRes.desc", { vintage: vint.spending || "OLDCC" }),
  });
  const landLens = () => stateLens(data, "mil-land", (abbr) => mil.states?.[abbr]?.area_km2 ?? null, {
    name: t("adv.mil.lens.land"), emoji: "🎖️", format: "float", unit: "km²", ramp: STEEL_RAMP, source: (mil.sources || [])[0] || "",
    description: t("adv.mil.lens.land.desc", { region: regionLc, vintage: vint.installations || "" }),
  });
  mapPicker(ctx, mapRow, {
    value: "terrain",
    options: [
      { value: "terrain", label: t("adv.mil.map.terrain"), lens: () => null },
      ...(app.lensById?.get("veterans") ? [{ value: "veterans", label: t("adv.mil.veterans"), lens: () => "veterans" }] : []),
      ...(US && counties ? [{ value: "af", label: t("adv.mil.map.af"), lens: afLens }] : []),
      ...(US ? [{ value: "dollars", label: t("adv.mil.map.perRes"), lens: perResLens }] : [{ value: "land", label: t("adv.mil.lens.land"), lens: landLens }]),
    ],
  });

  // --- installations --------------------------------------------------------------------------------------------
  const iBody = section(el, {
    title: t("adv.mil.installations"), kicker: esc(vint.installations || "DoD MIRTA"),
    note: usOr("adv.mil.inst.note", { cap: int(AREA_CAP), rule: esc(mil.rules?.tier || "") }),
  });
  const counts = new Map();
  for (const it of insts) counts.set(it.component, (counts.get(it.component) || 0) + 1);
  const compChips = chips(iBody, {
    label: t("adv.mil.components"),
    items: comps.filter((c) => counts.get(c.id)).map((c) => ({ key: c.id, label: c.short, color: c.color, count: counts.get(c.id) })),
    onChange: (on) => { st.comps = on; apply(); },
  });
  const groups = US ? COMP_GROUPS : [];
  const qRow = mk("div", "adv-row");
  qRow.innerHTML = groups.map((g) => `<button type="button" class="adv-mini" data-g="${g.id}">${esc(t(`adv.mil.group.${g.id}`))}</button>`).join("") + `<button type="button" class="adv-mini" data-g="all">${t("adv.mil.all")}</button>`;
  iBody.appendChild(qRow);
  qRow.addEventListener("click", (e) => {
    const g = e.target.closest("[data-g]")?.dataset.g;
    if (!g) return;
    st.comps = g === "all" ? new Set(comps.map((c) => c.id)) : new Set(groups.find((x) => x.id === g).ids);
    compChips.set(st.comps);
    apply();
  });
  const tRow = mk("div", "adv-row");
  iBody.appendChild(tRow);
  segmented(tRow, {
    label: t("adv.mil.size"), value: st.tier,
    options: [{ value: "major", label: t("adv.mil.tier.major") }, { value: "big", label: t("adv.mil.size.big") }, { value: "all", label: t("adv.mil.size.all") }],
    onChange: (v) => { st.tier = v; apply(); },
  });
  const stateChip = mk("div", "adv-row adv-filterbar");
  iBody.appendChild(stateChip);
  stateChip.addEventListener("click", (e) => { if (e.target.closest("[data-clear-state]")) setState(null); });
  const legend = mk("div");
  legend.innerHTML = sizeLegend([AREA_CAP / 30, AREA_CAP / 3, AREA_CAP], (v) => 14 * Math.sqrt(v / AREA_CAP), (v) => `${int(v)} km²`, t("adv.mil.sizeLegend"));
  iBody.appendChild(legend);
  const instTable = createTable(iBody, {
    caption: usOr("adv.mil.inst.caption"), search: t("adv.mil.inst.search", { regions: region.many.toLowerCase() }), rank: true, maxHeight: 280,
    searchText: (r) => `${r.name} ${r.state} ${compById.get(r.component)?.name || ""}`,
    columns: [
      { key: "name", label: t("adv.mil.col.installation"), align: "l", width: "minmax(0,1.9fr)", value: (r) => r.name, html: (r) => `<i class="dot" style="background:${esc(compById.get(r.component)?.color || "#999")}"></i>${esc(r.name)}${r.joint ? ` <span class="sub">${t("adv.mil.joint")}</span>` : ""}`, tip: (r) => `${r.name} · ${compById.get(r.component)?.name || r.component}${r.status !== "act" ? ` · ${statusLabel(r.status)}` : ""}` },
      { key: "component", label: t("adv.mil.col.service"), align: "l", width: "minmax(0,.9fr)", hideBelow: 400, value: (r) => compById.get(r.component)?.short, text: (r) => compById.get(r.component)?.short || r.component },
      { key: "tier", label: t("adv.mil.col.tier"), align: "l", width: "46px", value: (r) => ({ major: 0, base: 1, site: 2 })[r.tier], text: (r) => tierLabel(r.tier) },
      { key: "state", label: region.one, align: "l", width: regionCol, value: (r) => r.state, text: (r) => r.state || "–" },
      { key: "area", label: t("adv.mil.col.area"), width: "minmax(0,.8fr)", value: (r) => r.area_km2, text: (r) => (fin(r.area_km2) ? `${count3(r.area_km2)} km²` : "–"), title: t("adv.mil.col.areaTitle") },
    ],
    rows: [], sort: { key: "area", dir: "desc" },
    onHover: (r) => {
      link.hover(r ? { cells: new Set(instCells(r)), label: r.name } : null);
      bubbles.setHot(r ? r.key : null);
    },
    onClick: (r) => flyTo(r),
  });
  function flyTo(r) {
    if (r.cells && r.cells.length > 2) {
      const b = app.highlightBounds({ cells: new Set(r.cells) });
      if (b) return frameBox(app, b, { pad: 60, maxScale: 3 });
    }
    focusPoint(app, r.x, r.y, Math.min(app.cam.maxScale, Math.max(app.cam.scale, (app.cam.fitScale || 1) * 3)));
  }

  // --- by state -------------------------------------------------------------------------------------------------
  const sBody = section(el, {
    title: usOr("adv.mil.byState.title", { region: regionLc }),
    note: usOr("adv.mil.byState.note", { personnel: esc(vint.personnel || "DMDC"), spending: esc(vint.spending || "OLDCC"), region: regionLc, vintage: esc(vint.installations || "") }),
  });
  const sCtl = mk("div", "adv-row");
  sBody.appendChild(sCtl);
  const METRICS = US ? {
    troops: {
      label: t("adv.mil.m.troops"),
      keys: [{ key: "active", label: t("adv.mil.activeDuty"), color: "#6f91ad" }, { key: "guard", label: t("adv.mil.guardReserve"), color: "#d6b04a" }, { key: "civ", label: t("adv.mil.civilians"), color: "#9a9aa8" }],
      parts: (s) => ({ active: s.personnel?.active?.total, guard: s.personnel?.guard_reserve?.total, civ: s.personnel?.civilian?.total }),
      total: (s) => s.personnel?.total, fmt: count3,
    },
    dollars: {
      label: t("adv.mil.m.dollars"),
      keys: [{ key: "contracts", label: t("adv.mil.contracts"), color: "#d9a457" }, { key: "payroll", label: t("adv.mil.payroll"), color: "#6f91ad" }, { key: "grants", label: t("adv.mil.grants"), color: "#8fcbb8" }],
      parts: (s) => ({ contracts: s.spending?.contracts, payroll: s.spending?.payroll, grants: s.spending?.grants }),
      total: (s) => s.spending?.total, fmt: money,
    },
    perres: { label: t("adv.mil.m.perres"), keys: [{ key: "v", label: t("adv.mil.lens.perRes.unit"), color: "#d9a457" }], parts: (s) => ({ v: s.spending?.per_resident }), total: (s) => s.spending?.per_resident, fmt: dollars },
    gdp: { label: t("adv.mil.m.gdp"), keys: [{ key: "v", label: t("adv.mil.m.gdpKey"), color: "#c46a4f" }], parts: (s) => ({ v: s.spending?.pct_gdp }), total: (s) => s.spending?.pct_gdp, fmt: (v) => pct(v) },
  } : {
    sites: {
      label: t("adv.mil.installations"),
      keys: comps.map((c) => ({ key: c.id, label: c.short, color: c.color })),
      parts: (s) => s.by_component || {}, total: (s) => s.installations, fmt: int,
    },
    land: { label: t("adv.mil.m.land"), keys: [{ key: "v", label: t("adv.mil.m.land"), color: "#6f91ad" }], parts: (s) => ({ v: s.area_km2 }), total: (s) => s.area_km2, fmt: (v) => `${count3(v)} km²` },
  };
  let metric = Object.keys(METRICS)[0], showAll = false;
  segmented(sCtl, {
    label: t("adv.mil.measure"), value: metric,
    options: Object.entries(METRICS).map(([value, m]) => ({ value, label: m.label })),
    onChange: (v) => { metric = v; drawStates(); },
  });
  const allBtn = mk("button", "adv-mini");
  allBtn.type = "button";
  sCtl.appendChild(allBtn);
  allBtn.addEventListener("click", () => { showAll = !showAll; drawStates(); });
  const sHost = mk("div");
  sBody.appendChild(sHost);
  const sLegend = mk("div");
  sBody.appendChild(sLegend);
  const detail = mk("div", "adv-detail");
  sBody.appendChild(detail);
  let stacks = null;
  const milStates = Object.entries(mil.states || {}).filter(([, s]) => s);
  function drawStates() {
    const M = METRICS[metric];
    const rows = milStates
      .map(([abbr, s]) => ({ key: abbr, label: stateName(abbr), sub: stateIdx(abbr) == null ? t("adv.mil.offMap") : "", parts: M.parts(s), total: M.total(s), text: M.fmt(M.total(s)) }))
      .filter((r) => fin(r.total) && (US || r.total > 0))
      .sort((a, b) => b.total - a.total);
    const shown = showAll ? rows : rows.slice(0, 15);
    allBtn.textContent = showAll ? t("adv.mil.top15") : t("adv.mil.allN", { n: rows.length });
    sHost.innerHTML = "";
    stacks = stackedBars(sHost, {
      rows: shown, keys: M.keys, fmt: (v) => M.fmt(v), ariaLabel: usOr("adv.mil.byState.aria", { region: regionLc }),
      onHover: (x) => {
        if (!x) return link.hover(null);
        const i = stateIdx(x.row.key);
        link.hover(i != null ? { states: new Set([i]), dimOthers: true, label: x.row.label } : null);
      },
      onClick: (x) => setState(st.state === x.row.key ? null : x.row.key, true),
    });
    if (st.state) stacks.setSelected(st.state);
    sLegend.innerHTML = M.keys.length > 1 ? swatchLegend(M.keys) : "";
  }

  function drawDetail() {
    const abbr = st.state;
    const s = abbr ? mil.states?.[abbr] : null;
    if (!abbr) { detail.innerHTML = ""; return; }
    if (!s) { detail.innerHTML = `<p class="adv-empty">${t("adv.mil.noFigures", { name: esc(stateName(abbr)) })}</p>`; return; }
    detail.innerHTML = US ? usDetail(abbr, s) : regionDetail(abbr, s);
    const sp = s.spending;
    detail.querySelectorAll("[data-county]").forEach((b) => {
      const c = sp.top_counties[+b.dataset.county];
      const row = c.county ? counties?.byKey.get(c.county) : null;
      if (!row) return;
      b.addEventListener("pointerenter", () => link.hover(rowsHighlight(counties, [row])));
      b.addEventListener("pointerleave", () => link.hover(null));
      b.addEventListener("click", () => counties.focus(row));
    });
  }
  function usDetail(abbr, s) {
    const p = s.personnel, sp = s.spending;
    const branch = p ? [["army", p.active?.army], ["navy", p.active?.navy], ["marines", p.active?.marines], ["air_force", p.active?.air_force], ["space_force", p.active?.space_force], ["coast_guard", p.active?.coast_guard]] : [];
    const nInst = insts.filter((it) => it.state === abbr).length;
    return `<div class="adv-card-detail">
      <h4 class="adv-h4">${esc(stateName(abbr))}</h4>
      ${tiles([
        { label: t("adv.mil.activeDuty"), value: p ? int(p.active?.total) : "–", sub: p ? t("adv.mil.guardN", { n: int(p.guard_reserve?.total) }) : t("adv.mil.noDmdc") },
        { label: t("adv.mil.defense"), value: sp ? money(sp.total) : "–", sub: sp ? t("adv.mil.defenseSub", { pct: pct(sp.pct_gdp), per: dollars(sp.per_resident) }) : t("adv.mil.noOldcc") },
        { label: t("adv.mil.installations"), value: int(nInst), sub: t("adv.mil.filedHere") },
      ])}
      ${p ? `<p class="adv-note">${t("adv.mil.byService", { list: branch.filter(([, v]) => fin(v) && v > 0).map(([k, v]) => `${esc(t(`adv.mil.service.${k}`))} ${int(v)}`).join(" · "), civ: int(p.civilian?.total) })}</p>` : ""}
      ${sp ? `<p class="adv-note">${t("adv.mil.whereMoney", { contracts: money(sp.contracts), payroll: money(sp.payroll), grants: money(sp.grants) })}</p>` : ""}
      ${sp?.top_vendors?.length ? `<p class="adv-note">${t("adv.mil.topVendors", { list: sp.top_vendors.map((v) => `${esc(v.name)} ${money(v.contracts)}`).join(" · ") })}</p>` : ""}
      ${sp?.top_counties?.length ? `<h4 class="adv-h4">${t("adv.mil.byCounty")}</h4><div class="adv-chiplist">${sp.top_counties.map((c, i) => `<button type="button" class="adv-mini" data-county="${i}"${c.county ? "" : ` disabled title="${t("adv.mil.notCounty")}"`}>${esc(c.name)} <b>${money(c.contracts)}</b></button>`).join("")}</div>` : ""}
    </div>`;
  }
  function regionDetail(abbr, s) {
    const mine = insts.filter((it) => it.state === abbr).sort((a, b) => (b.area_km2 || 0) - (a.area_km2 || 0));
    const byComp = comps.filter((c) => s.by_component?.[c.id]).map((c) => `${esc(c.short)} ${int(s.by_component[c.id])}`).join(" · ");
    return `<div class="adv-card-detail">
      <h4 class="adv-h4">${esc(stateName(abbr))}</h4>
      ${tiles([
        { label: t("adv.mil.installations"), value: int(s.installations), sub: t("adv.mil.majorN", { n: int(s.major) }) },
        { label: t("adv.mil.m.land"), value: `${count3(s.area_km2)} km²`, sub: t("adv.mil.landSub") },
      ])}
      ${byComp ? `<p class="adv-note">${t("adv.mil.byBranch", { list: byComp })}</p>` : ""}
      ${mine.length ? `<p class="adv-note">${t("adv.mil.largest", { list: mine.slice(0, 5).map((it) => esc(it.name)).join(" · ") })}</p>` : ""}
    </div>`;
  }

  // --- garrisons ------------------------------------------------------------------------------------------------
  const gBody = section(el, { title: usOr("adv.mil.garrisons"), note: esc(mil.rules?.encampment || mil.rules?.garrisons || mil.rule || "") });
  const garrisonsByCity = mil.cities || mil.garrisons || {};
  const garrisons = Object.entries(garrisonsByCity).map(([id, c]) => ({ ...c, key: id, row: metros.byKey.get(id) })).filter((g) => g.row);
  const sitesTip = (g) => `${g.row.name}: ${(g.installations || []).map((id) => instByKey.get(id)?.name || id).join(", ")}`;
  const gTable = createTable(gBody, {
    caption: usOr("adv.mil.garrisons"), rank: true, maxHeight: 250, search: t("adv.mil.searchMetros", { metros: country().levels.metro.many.toLowerCase() }),
    searchText: (g) => g.row.name,
    columns: US ? [
      { key: "name", label: t("adv.mil.col.metro"), align: "l", width: "minmax(0,1.8fr)", value: (g) => g.row.name, html: (g) => `${esc(g.row.name)} <span class="sub">${esc(g.row.sub)}</span>`, tip: sitesTip },
      { key: "tier", label: t("adv.mil.col.tier"), align: "l", width: "minmax(0,.8fr)", value: (g) => (g.tier === "fortress" ? 0 : 1), text: (g) => `${g.tier === "fortress" ? t("adv.mil.fortress") : t("adv.mil.garrison")}${g.naval ? " ⚓" : ""}` },
      { key: "af", label: t("adv.mil.col.uniform"), value: (g) => g.armed_forces, text: (g) => count3(g.armed_forces), title: t("adv.mil.col.uniformTitle") },
      { key: "share", label: t("adv.mil.col.share"), value: (g) => g.share, text: (g) => pct(g.share), title: t("adv.mil.col.shareTitle"), bar: { max: Math.max(...garrisons.map((g) => g.share || 0), 0.01), color: "rgba(135,150,171,.35)" } },
    ] : [
      { key: "name", label: country().levels.metro.one, align: "l", width: "minmax(0,1.8fr)", value: (g) => g.row.name, html: (g) => `${esc(g.row.name)}${g.naval ? " ⚓" : ""} <span class="sub">${esc(g.row.sub)}</span>`, tip: sitesTip },
      { key: "n", label: t("adv.mil.installations"), value: (g) => g.installation_count, text: (g) => int(g.installation_count) },
      { key: "area", label: t("adv.mil.col.area"), value: (g) => g.area_km2, text: (g) => `${count3(g.area_km2)} km²`, bar: { max: Math.max(...garrisons.map((g) => g.area_km2 || 0), 1), color: "rgba(135,150,171,.35)" } },
    ],
    rows: garrisons, sort: { key: US ? "share" : "area", dir: "desc" },
    onHover: (g) => link.hover(g ? rowsHighlight(metros, [g.row]) : null),
    onClick: (g) => metros.focus(g.row),
  });
  gBody.insertAdjacentHTML("beforeend", `<p class="adv-note">${usOr("adv.mil.navalNote")}</p>`);

  // --- ranges ---------------------------------------------------------------------------------------------------
  const rBody = section(el, { title: t("adv.mil.ranges"), note: esc(mil.rules?.ranges || "") });
  const rTable = createTable(rBody, {
    caption: t("adv.mil.ranges.caption"), rank: true, maxHeight: 240,
    columns: [
      { key: "name", label: t("adv.mil.col.range"), align: "l", width: "minmax(0,2fr)", value: (r) => r.name, html: (r) => `<i class="dot" style="background:${esc(compById.get(r.component)?.color || "#999")}"></i>${esc(r.name)}` },
      { key: "state", label: region.one, align: "l", width: regionCol, value: (r) => r.state, text: (r) => r.state || "–" },
      { key: "area", label: t("adv.mil.col.area"), width: "minmax(0,.9fr)", value: (r) => r.area_km2, text: (r) => `${count3(r.area_km2)} km²`, bar: { max: Math.max(...ranges.map((r) => r.area_km2 || 0), 1), color: "rgba(194,74,62,.3)" } },
    ],
    rows: ranges, sort: { key: "area", dir: "desc" },
    onHover: (r) => link.hover(r ? { cells: new Set(r.cells || []), dimOthers: true, color: "#f09a7f", label: r.name } : null),
    onClick: (r) => { const b = app.highlightBounds({ cells: new Set(r.cells || []) }); if (b) frameBox(app, b, { pad: 60, maxScale: 2.6 }); },
  });

  // --- veterans -------------------------------------------------------------------------------------------------
  let vTable = null, vLevel = "states";
  if (US) {
    const vBody = section(el, {
      title: t("adv.mil.vets.title"),
      note: t("adv.mil.vets.note", { vintage: esc(vint.acs || data.countyVintage) }),
    });
    const vCtl = mk("div", "adv-row");
    vBody.appendChild(vCtl);
    segmented(vCtl, {
      label: t("adv.mil.places"), value: vLevel,
      options: [{ value: "states", label: t("adv.mil.places.states") }, { value: "metros", label: t("adv.mil.places.metros") }, ...(counties ? [{ value: "counties", label: t("adv.mil.places.counties") }] : [])],
      onChange: (v) => { vLevel = v; vTable.setRows(vRows()); },
    });
    const vRows = () => data.levels[vLevel].rows.filter((r) => fin(r.v.veterans_pct) && (vLevel !== "counties" || (r.v.population || 0) >= 10000));
    vTable = createTable(vBody, {
      caption: t("adv.mil.vets.caption"), rank: true, maxHeight: 260, search: t("adv.mil.searchPlaces"),
      columns: [
        { key: "name", label: t("adv.mil.col.place"), align: "l", width: "minmax(0,1.7fr)", value: (r) => r.name, html: (r) => `${esc(r.name)}${r.level !== "states" && r.sub ? ` <span class="sub">${esc(r.sub)}</span>` : ""}` },
        { key: "veterans", label: t("adv.mil.veterans"), value: (r) => r.v.veterans, text: (r) => count3(r.v.veterans) },
        { key: "veterans_pct", label: t("adv.mil.col.share"), value: (r) => r.v.veterans_pct, text: (r) => pct(r.v.veterans_pct), bar: { max: 0.2, color: "rgba(135,150,171,.35)" }, title: t("adv.mil.col.vetsTitle") },
        { key: "armed_forces_pct", label: t("adv.mil.col.uniform"), value: (r) => r.v.armed_forces_pct, text: (r) => pct(r.v.armed_forces_pct), title: t("adv.mil.col.afTitle") },
      ],
      rows: vRows(), sort: { key: "veterans_pct", dir: "desc" },
      onHover: (r) => link.hover(r ? rowsHighlight(data.levels[vLevel], [r]) : null),
      onClick: (r) => data.levels[vLevel].focus(r),
    });
    vBody.insertAdjacentHTML("beforeend", `<p class="adv-note">${t("adv.mil.vets.small")}</p>`);
  }

  el.insertAdjacentHTML("beforeend", sourcesHtml(data, mil.sources || ["mirta", "dmdc_personnel", "oldcc_spending", "acs_5yr"], (US ? [
    esc(mil.caveats || ""),
    t("adv.mil.c.vintages.us", { personnel: esc(vint.personnel || "DMDC"), spending: esc(vint.spending || "OLDCC") }),
    t("adv.mil.c.tiers.us"),
    t("adv.mil.c.filed.us"),
    t("adv.mil.c.offMap.us"),
  ] : [
    esc(mil.caveats || ""),
    esc(mil.rules?.installations || ""),
    esc(mil.rules?.branch || ""),
    esc(mil.rules?.joint || ""),
    t("adv.mil.c.tiers"),
    t("adv.mil.c.links", { n: int(nat.linked || 0), total: int(insts.length) }),
  ]).filter(Boolean)));

  // --- map ------------------------------------------------------------------------------------------------------
  const bubbles = ctx.bubbles("bases", {
    rMax: 14, minR: 2.6, alpha: 0.6,
    tip: (b) => {
      const it = b.it, c = compById.get(it.component);
      return `<b>${esc(it.name)}</b><br>${esc(c?.name || it.component)} · ${esc(tierLabel(it.tier))}${fin(it.area_km2) ? ` · ${count3(it.area_km2)} km²` : ""}${it.state ? ` · ${esc(it.state)}` : ""}${it.status !== "act" ? `<br><span class="sub">${esc(statusLabel(it.status))}</span>` : ""}`;
    },
    onHover: (b) => {
      instTable.setHot(b ? b.key : null);
      link.hover(b && b.it.cells?.length ? { cells: new Set(b.it.cells), noBeacon: true } : null);
    },
    onClick: (b) => { instTable.setHot(b.key); flyTo(b.it); },
  });

  function visible() {
    return insts.filter((it) => st.comps.has(it.component) && (st.tier === "all" || it.tier === "major" || (st.tier === "big" && it.tier === "base")) && (!st.state || it.state === st.state));
  }
  function setState(abbr, fly = false) {
    st.state = abbr;
    stacks?.setSelected(abbr);
    if (!abbr) stacks?.setSelected(null);
    apply();
    drawDetail();
    const i = abbr ? stateIdx(abbr) : null;
    if (i != null && fly) {
      const b = app.highlightBounds({ states: new Set([i]) });
      if (b) frameBox(app, b, { pad: 30, maxScale: 2.6 });
    }
  }
  function apply() {
    const vis = visible();
    instTable.setRows(vis);
    bubbles.set(vis.map((it) => ({ key: it.key, x: it.x, y: it.y, value: fin(it.area_km2) ? Math.min(AREA_CAP, it.area_km2) : 0, color: compById.get(it.component)?.color || "#999", it })), { vMax: AREA_CAP });
    const i = st.state ? stateIdx(st.state) : null;
    link.base(i != null ? { states: new Set([i]), dimOthers: true } : null);
    stateChip.innerHTML = st.state
      ? `<span class="adv-fchip">${esc(region.one)}: <b>${esc(stateName(st.state))}</b> · ${t("adv.mil.nSites", { n: vis.length, count: int(vis.length) })}<button type="button" data-clear-state aria-label="${t("adv.mil.clearRegion", { region: regionLc })}">✕</button></span>`
      : "";
  }
  drawStates();
  apply();

  return {
    onMapHover(h) {
      const owner = h.cell >= 0 ? app.w.raw.owner[h.cell] : -1;
      const abbr = owner >= 0 ? stLevel.rows[owner]?.key : null;
      stacks?.setHot(abbr || null);
      const r = h.cell >= 0 ? cellRange.get(h.cell) : null;
      rTable.setHot(r ? r.id : null, !!r);
      // A fort or range drawn by the map-art layer names its record; otherwise the boundary under the pointer.
      const inst = h.item?.kind === "fort" ? instByKey.get(h.item.data?.id) : h.cell >= 0 ? cellInst.get(h.cell) : null;
      if (inst) instTable.setHot(inst.key);
      if (h.item?.kind === "range") rTable.setHot(h.item.data?.id ?? null);
      const m = h.cell >= 0 ? metros.rowAtCell(h.cell) : null;
      gTable.setHot(m && garrisonsByCity[m.key] ? m.key : null, false);
      const vr = vTable && h.cell >= 0 ? data.levels[vLevel]?.rowAtCell(h.cell) : null;
      vTable?.setHot(vr ? vr.key : null, false);
    },
    onMapClick(ev) {
      const fort = ev.item?.kind === "fort" ? instByKey.get(ev.item.data?.id) : null;
      if (fort) { instTable.setHot(fort.key); flyTo(fort); return true; }
      // A click on a state (not a city) filters the General's view to it; a second click clears it.
      if (ev.city || ev.state == null) return false;
      const abbr = stLevel.rows[ev.state]?.key;
      if (!abbr) return false;
      setState(st.state === abbr ? null : abbr);
      return true;
    },
    onEscape() {
      if (st.state) { setState(null); return true; }
      return false;
    },
  };
}

const STATE_NAMES = { AK: "Alaska", HI: "Hawaii", PR: "Puerto Rico" };
