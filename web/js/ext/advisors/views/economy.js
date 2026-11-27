// Economy advisor: GDP by industry, metro GDP on the map, leaders, specialisation and growth vs output.
import { esc, fin, ratio, colorScale, robustDomain, RAMPS } from "../core/util.js";
import { money, dollars, pct, int, signedPct, count3, fmtShort, times } from "../core/fmt.js";
import { barList, rampLegend, sizeLegend } from "../core/charts.js";
import { createTable } from "../core/table.js";
import { createScatter } from "../core/scatter.js";
import { section, tiles, segmented, selectBox, sourcesHtml, frameBtn } from "../core/view.js";
import { rowsHighlight } from "../core/data.js";
import { icon } from "../../../ui/icon.js";
import { hasIcon } from "../../../icons.js";
import { t } from "../../../i18n.js";
import { country } from "../../../app/country.js";

export const METRO_MIN = 250000;
const short = (s) => String(s || "").replace(/\s*\(.*\)\s*$/, "");
const indIcon = (k) => (hasIcon(`i-${k}`) ? icon(`i-${k}`, "•", { size: 14 }) : k === "government" ? icon("i-public_admin", "🏛", { size: 14 }) : "");

export function mount(ctx) {
  const { app, data, el, link, params } = ctx;
  const nation = app.data.nation;
  const n = nation.nation || {};
  const metros = data.levels.metros;
  const rows = metros.rows;
  const states = app.data.states || [];
  const jobInd = Object.keys(nation.industries || {});
  // Industries by GDP where the country publishes it (US: BEA), else by the residents they employ (Spain: INE Censo).
  const gdpInd = n.gdp_by_industry || {};
  const byGdp = Object.values(gdpInd).some(fin);
  const ind = byGdp
    ? { values: gdpInd, total: n.gdp, names: nation.gdp_industries, fmt: money, share: (s, k) => ratio(s.gdp_by_industry?.[k], s.gdp) }
    : { values: n.jobs || {}, total: n.employed, names: nation.industries, fmt: count3, share: (s, k) => ratio(s.jobs?.[k], s.employed) };
  // The bar list keys BEA's "government"; the jobs table (and the specialisation picker) call it "public_admin".
  const toBar = (k) => (byGdp && k === "public_admin" ? "government" : k);
  const fromBar = (k) => (byGdp && k === "government" ? "public_admin" : k);
  // GDP by place: metros where they have it (US), else the regions (Spain: the INE stops at the province, DECISIONS E9).
  const metroGdp = rows.some((r) => fin(r.v.gdp));
  const place = metroGdp
    ? { level: metros, min: METRO_MIN, name: t("adv.metro"), open: (r) => app.selectCity(r.ref), at: (r) => [app.w.grid.cx(r.ref.cell), app.w.grid.cy(r.ref.cell)] }
    : { level: data.levels.states, min: 0, name: data.levels.states.field("name").label, open: (r) => data.levels.states.focus(r), at: (r) => [states[r.ref].label.x, states[r.ref].label.y] };
  const pRows = place.level.rows;
  const placeHi = (list, o) => rowsHighlight(place.level, list, o);

  // --- headline -------------------------------------------------------------------------------------------------
  const topInd = Object.entries(ind.values).filter(([, v]) => fin(v)).sort((a, b) => b[1] - a[1])[0];
  el.insertAdjacentHTML("beforeend", tiles([
    { label: t("adv.eco.gdpYear", { year: n.gdp_year || "" }), value: money(n.gdp), sub: t("adv.eco.currentDollars") },
    { label: t("adv.eco.perPerson"), value: money(ratio(n.gdp, n.population)), sub: t("adv.eco.gdpPerResident") },
    { label: t("adv.eco.topIndustry"), value: topInd ? short(ind.names?.[topInd[0]] || topInd[0]) : "–", sub: topInd ? t(byGdp ? "adv.eco.ofGdp" : "adv.eco.ofJobs", { share: pct(topInd[1] / ind.total) }) : "" },
  ]));

  // --- GDP (or jobs) by industry --------------------------------------------------------------------------------
  const indTitle = t(byGdp ? "adv.eco.byIndustry" : "adv.eco.jobsByIndustry");
  const indBody = section(el, { title: indTitle, kicker: country().name, note: t(byGdp ? "adv.eco.byIndustry.note" : "adv.eco.jobsByIndustry.note") });
  const indRows = Object.entries(ind.values).filter(([, v]) => fin(v)).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({
    key: k, label: short(ind.names?.[k] || k), full: ind.names?.[k], value: v, text: ind.fmt(v), sub: pct(v / ind.total), icon: indIcon(k),
  }));
  const indBars = barList(indBody, {
    rows: indRows, ariaLabel: indTitle,
    onHover: (r) => {
      if (!r) return link.hover(null);
      const top = states.map((s, i) => ({ i, v: ind.share(s, r.key) })).filter((x) => fin(x.v)).sort((a, b) => b.v - a.v).slice(0, 8);
      link.hover({ states: new Set(top.map((x) => x.i)), dimOthers: true });
    },
    onClick: (r) => { setIndustry(fromBar(r.key)); specBody.scrollIntoView({ behavior: "smooth", block: "start" }); },
  });

  // --- map: GDP circles -----------------------------------------------------------------------------------------
  const mapBody = section(el, { title: t(metroGdp ? "adv.eco.map.title" : "adv.eco.map.title.region"), note: t(metroGdp ? "adv.eco.map.note" : "adv.eco.map.note.region") });
  const ppDomain = robustDomain(pRows.filter((r) => r.v.population >= 100000).map((r) => r.v.gdp_pc), 0.03, true) || [30000, 120000];
  const ppColor = colorScale({ type: "seq", domain: ppDomain, ramp: RAMPS.gold });
  const gMax = Math.max(...pRows.map((r) => r.v.gdp || 0));
  const bubbles = ctx.bubbles("gdp", {
    rMax: 30, minR: 1.5, alpha: 0.6,
    tip: (b) => `<b>${esc(b.row.name)}</b> <span class="sub">${esc(b.row.sub)}</span><br>${t("adv.eco.tip", { gdp: money(b.row.v.gdp), pc: money(b.row.v.gdp_pc), people: count3(b.row.v.population) })}`,
    onHover: (b) => { table.setHot(b ? b.key : null); scatter.setHot(b ? b.key : null); link.hover(b ? placeHi([b.row]) : null); },
    onClick: (b) => place.open(b.row),
  });
  const bubbleItems = pRows.filter((r) => fin(r.v.gdp)).map((r) => { const [x, y] = place.at(r); return { key: r.key, x, y, value: r.v.gdp, color: ppColor(r.v.gdp_pc), row: r }; });
  bubbles.set(bubbleItems, { vMax: gMax });
  const showBubbles = document.createElement("label");
  showBubbles.className = "adv-check";
  showBubbles.innerHTML = `<input type="checkbox" checked> ${t("adv.eco.showCircles")}`;
  showBubbles.querySelector("input").addEventListener("change", (e) => bubbles.set(e.target.checked ? bubbleItems : [], { vMax: gMax }));
  mapBody.appendChild(showBubbles);
  mapBody.insertAdjacentHTML("beforeend", rampLegend({ ramp: RAMPS.gold, domain: ppDomain, fmt: money, label: t("adv.eco.gdpPc") })
    + sizeLegend([1e10, 1e11, 1e12].filter((v) => v <= gMax), (v) => 30 * Math.sqrt(v / gMax) , money, t("adv.eco.circleArea")));

  // --- leaders --------------------------------------------------------------------------------------------------
  const lBody = section(el, { title: t(metroGdp ? "adv.eco.leaders" : "adv.eco.leaders.region"), note: metroGdp ? t("adv.eco.leaders.note", { min: count3(METRO_MIN) }) : t("adv.eco.leaders.note.region") });
  const big = rows.filter((r) => (r.v.population || 0) >= METRO_MIN);
  const pBig = pRows.filter((r) => (r.v.population || 0) >= place.min);
  segmented(lBody, {
    label: t("adv.rankBy"), value: "gdp",
    options: [{ value: "gdp", label: t("adv.eco.largestGdp") }, { value: "gdp_pc", label: t("adv.eco.gdpPc") }, { value: "growth", label: t("adv.eco.fastest") }],
    onChange: (v) => { table.setRows(v === "gdp" ? pRows : pBig); table.setColumns(cols, { key: v, dir: "desc" }); },
  });
  const cols = [
    { key: "name", label: place.name, align: "l", value: (r) => r.name, html: (r) => `${esc(r.name)} <span class="sub">${esc(r.sub)}</span>` },
    { key: "gdp", label: t("adv.gdp"), value: (r) => r.v.gdp, text: (r) => money(r.v.gdp), bar: { max: gMax, color: "rgba(224,181,76,.35)" } },
    { key: "gdp_pc", label: t("adv.eco.perPerson"), value: (r) => r.v.gdp_pc, text: (r) => money(r.v.gdp_pc) },
    { key: "growth", label: t("adv.growth"), value: (r) => r.v.growth, text: (r) => signedPct(r.v.growth) },
  ];
  const table = createTable(lBody, {
    caption: t(metroGdp ? "adv.eco.metrosByGdp" : "adv.eco.regionsByGdp"), columns: cols, rows: pRows, sort: { key: "gdp", dir: "desc" }, rank: true, maxHeight: 280,
    search: metroGdp ? t("adv.searchMetros") : t("adv.ex.search", { level: place.level.label.toLowerCase() }),
    onHover: (r) => { link.hover(r ? placeHi([r]) : null); bubbles.setHot(r ? r.key : null); scatter.setHot(r ? r.key : null); },
    onClick: (r) => place.open(r),
  });

  // --- specialisation -------------------------------------------------------------------------------------------
  const specBody = section(el, { title: t("adv.eco.spec.title"), note: t("adv.eco.spec.note", { min: count3(METRO_MIN) }) });
  let industry = params.industry && jobInd.includes(params.industry) ? params.industry : "manufacturing";
  const indSel = selectBox(specBody, {
    label: t("adv.industry"), value: industry,
    options: jobInd.map((k) => ({ value: k, label: short(nation.industries[k]) })),
    onChange: (v) => setIndustry(v),
  });
  const specInfo = document.createElement("p");
  specInfo.className = "adv-note";
  specBody.appendChild(specInfo);
  const lq = (r, k = industry) => {
    const o = r.level === "states" ? states[r.ref] : r.ref; // a state row's ref is its index in states.json
    const us = ratio(n.jobs?.[k], n.employed);
    return us ? ratio(ratio(o.jobs?.[k], o.employed), us) : null;
  };
  const specTable = createTable(specBody, {
    caption: t("adv.eco.mostSpecialised"), rank: true, maxHeight: 260, rows: [],
    columns: [
      { key: "name", label: t("adv.metro"), align: "l", value: (r) => r.name, html: (r) => `${esc(r.name)} <span class="sub">${esc(r.sub)}</span>` },
      { key: "share", label: t("adv.shareOfJobs"), value: (r) => ratio(r.ref.jobs?.[industry], r.ref.employed), text: (r) => pct(ratio(r.ref.jobs?.[industry], r.ref.employed)) },
      { key: "lq", label: t("adv.lq"), value: (r) => lq(r), text: (r) => (fin(lq(r)) ? times(lq(r), 2) : "–"), bar: { max: 1, color: "rgba(74,134,214,.4)" } },
      { key: "workers", label: t("adv.workers"), value: (r) => r.ref.jobs?.[industry], text: (r) => count3(r.ref.jobs?.[industry]) },
    ],
    sort: { key: "lq", dir: "desc" },
    onHover: (r) => { link.hover(r ? rowsHighlight(metros, [r]) : null); scatter.setHot(r ? r.key : null); bubbles.setHot(r ? r.key : null); },
    onClick: (r) => app.selectCity(r.ref),
  });

  // --- scatter --------------------------------------------------------------------------------------------------
  const scBody = section(el, { title: t("adv.eco.scatter.title"), note: t(metroGdp ? "adv.eco.scatter.note" : "adv.eco.scatter.note.region") });
  const scCtl = document.createElement("div");
  scCtl.className = "adv-row";
  scBody.appendChild(scCtl);
  let colorBy = "lq", allMetros = false;
  selectBox(scCtl, {
    label: t("adv.colour"), value: colorBy,
    options: [{ value: "lq", label: t("adv.eco.specChosen") }, { value: "unemployment", label: t("adv.f.unemployment.tile") }, { value: "median_income", label: t("adv.income") }, { value: "none", label: t("adv.none") }],
    onChange: (v) => { colorBy = v; drawScatter(); },
  });
  if (place.min) segmented(scCtl, { label: t("adv.metros"), value: "big", options: [{ value: "big", label: `${count3(METRO_MIN)}+` }, { value: "all", label: t("adv.all") }], onChange: (v) => { allMetros = v === "all"; drawScatter(); } });
  const legendEl = document.createElement("div");
  const scatter = createScatter(scBody, {
    points: [], height: 300,
    x: { label: t("adv.eco.gdpPc"), fmt: (v) => money(v), log: true },
    y: { label: t("adv.eco.popGrowth"), fmt: (v) => fmtShort("signed", v) },
    size: { label: t("adv.population"), fmt: count3, max: 15, min: 2 },
    refY: [{ v: n.growth ?? 0, label: t("adv.nationValue", { v: signedPct(n.growth) }) }],
    onHover: (p) => { link.hover(p ? placeHi([p.row]) : null); bubbles.setHot(p ? p.key : null); table.setHot(p ? p.key : null, false); },
    onClick: (p) => place.open(p.row),
    onBrush: (set) => {
      const sel = set ? pRows.filter((r) => set.has(r.key)) : [];
      link.base(sel.length ? placeHi(sel, { dim: true }) : specHighlight(), { frame: sel.length > 1 });
      bubbles.setSelected(set);
      brushInfo.innerHTML = sel.length ? brushSummary(sel) : "";
    },
  });
  scBody.appendChild(legendEl);
  const brushInfo = document.createElement("div");
  brushInfo.className = "adv-brushinfo";
  scBody.appendChild(brushInfo);
  function brushSummary(sel) {
    const pop = sel.reduce((a, r) => a + (r.v.population || 0), 0);
    const gdp = sel.reduce((a, r) => a + (r.v.gdp || 0), 0);
    return `${t(metroGdp ? "adv.eco.brush" : "adv.eco.brush.region", { n: sel.length, people: count3(pop), gdp: money(gdp), share: pct(gdp / n.gdp) })} ${frameBtn()}<button type="button" class="adv-mini" data-clear>${t("adv.clear")}</button>`;
  }
  brushInfo.addEventListener("click", (e) => { if (e.target.closest("[data-clear]")) { scatter.setSelected(null); link.base(specHighlight()); bubbles.setSelected(null); brushInfo.innerHTML = ""; } });

  function drawScatter() {
    const list = pRows.filter((r) => allMetros || (r.v.population || 0) >= place.min);
    const cv = (r) => (colorBy === "lq" ? lq(r) : colorBy === "none" ? null : r.v[colorBy]);
    let color = null, legend = "";
    if (colorBy !== "none") {
      const dom = robustDomain(list.map(cv), 0.03, colorBy === "lq") || [0, 1];
      const spec = colorBy === "lq" ? { type: "seq", domain: [Math.max(0.2, dom[0]), Math.max(1.5, dom[1])], log: true, ramp: RAMPS.seq } : { type: "seq", domain: dom, ramp: colorBy === "unemployment" ? RAMPS.heat : RAMPS.gold };
      const cs = colorScale(spec);
      color = (c) => cs(c);
      const f = colorBy === "lq" ? (v) => times(v, 1) : colorBy === "unemployment" ? (v) => pct(v) : money;
      legend = rampLegend({ ramp: spec.ramp, domain: spec.domain, fmt: f, log: spec.log, label: colorBy === "lq" ? t("adv.eco.specIn", { industry: short(nation.industries[industry]).toLowerCase() }) : colorBy === "unemployment" ? t("adv.f.unemployment.tile") : t("adv.eco.medianIncome") });
    }
    const labels = [...list].sort((a, b) => (b.v.population || 0) - (a.v.population || 0)).slice(0, 8).map((r) => r.key);
    scatter.update({
      points: list.filter((r) => fin(r.v.gdp_pc) && fin(r.v.growth)).map((r) => ({ key: r.key, x: r.v.gdp_pc, y: r.v.growth, s: r.v.population, c: cv(r), label: r.name, sub: r.sub, row: r })),
      color, labels, colorLabel: colorBy === "none" ? null : colorBy === "lq" ? t("adv.lq") : colorBy === "unemployment" ? t("adv.f.unemployment.tile") : t("adv.income"),
      colorFmt: colorBy === "lq" ? (v) => times(+v, 2) : colorBy === "unemployment" ? pct : dollars,
    });
    legendEl.innerHTML = legend;
  }

  let specTop = [];
  const specHighlight = () => (specTop.length ? rowsHighlight(metros, specTop, { ringMax: 15 }) : null);
  function setIndustry(k) {
    industry = k;
    indSel.set(k);
    const list = big.filter((r) => fin(lq(r))).sort((a, b) => lq(b) - lq(a));
    specTop = list.slice(0, 15);
    const maxLq = Math.max(1, ...list.slice(0, 40).map((r) => lq(r)));
    specTable.setColumns([
      { key: "name", label: t("adv.metro"), align: "l", value: (r) => r.name, html: (r) => `${esc(r.name)} <span class="sub">${esc(r.sub)}</span>` },
      { key: "share", label: t("adv.shareOfJobs"), value: (r) => ratio(r.ref.jobs?.[industry], r.ref.employed), text: (r) => pct(ratio(r.ref.jobs?.[industry], r.ref.employed)) },
      { key: "lq", label: t("adv.lq"), value: (r) => lq(r), text: (r) => (fin(lq(r)) ? times(lq(r), 2) : "–"), bar: { max: maxLq, color: "rgba(74,134,214,.45)" } },
      { key: "workers", label: t("adv.workers"), value: (r) => r.ref.jobs?.[industry], text: (r) => count3(r.ref.jobs?.[industry]) },
    ], { key: "lq", dir: "desc" });
    specTable.setRows(list);
    const us = ratio(n.jobs?.[k], n.employed);
    specInfo.innerHTML = t("adv.eco.specInfo", { share: pct(us), people: count3(n.jobs?.[k]), industry: esc(short(nation.industries[k]).toLowerCase()) });
    if (!scatter.selected) link.base(specHighlight());
    indBars.setSelected(toBar(k));
    drawScatter();
  }
  setIndustry(industry);

  el.insertAdjacentHTML("beforeend", sourcesHtml(data, ["bea_gdp", "acs_1yr", "pep_population", "cbsa_delineation"], [
    t("adv.eco.c1"),
    t("adv.eco.c2", { gdpVintage: esc(nation.gdp_vintage || "BEA"), vintage: esc(nation.vintage || "ACS") }),
    t("adv.eco.c3"),
  ]));

  return {
    onMapHover(h) {
      const r = h.cell >= 0 ? metros.rowAtCell(h.cell) : null;
      const p = h.cell >= 0 ? place.level.rowAtCell(h.cell) : null;
      scatter.setHot(p ? p.key : null);
      specTable.setHot(r ? r.key : null);
    },
    onEscape() {
      if (scatter.selected) { scatter.setSelected(null); link.base(specHighlight()); bubbles.setSelected(null); brushInfo.innerHTML = ""; return true; }
      return false;
    },
  };
}
