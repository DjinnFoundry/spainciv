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
  const gdpInd = n.gdp_by_industry || {};
  const jobInd = Object.keys(nation.industries || {});

  // --- headline -------------------------------------------------------------------------------------------------
  const topInd = Object.entries(gdpInd).filter(([, v]) => fin(v)).sort((a, b) => b[1] - a[1])[0];
  el.insertAdjacentHTML("beforeend", tiles([
    { label: t("adv.eco.gdpYear", { year: n.gdp_year || "" }), value: money(n.gdp), sub: t("adv.eco.currentDollars") },
    { label: t("adv.eco.perPerson"), value: money(ratio(n.gdp, n.population)), sub: t("adv.eco.gdpPerResident") },
    { label: t("adv.eco.topIndustry"), value: topInd ? short(nation.gdp_industries?.[topInd[0]] || topInd[0]) : "–", sub: topInd ? t("adv.eco.ofGdp", { share: pct(topInd[1] / n.gdp) }) : "" },
  ]));

  // --- GDP by industry ------------------------------------------------------------------------------------------
  const stRows = data.levels.states.rows;
  const indBody = section(el, { title: t("adv.eco.byIndustry"), kicker: country().name, note: t("adv.eco.byIndustry.note") });
  const indRows = Object.entries(gdpInd).filter(([, v]) => fin(v)).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({
    key: k, label: short(nation.gdp_industries?.[k] || k), full: nation.gdp_industries?.[k], value: v, text: money(v), sub: pct(v / n.gdp), icon: indIcon(k),
  }));
  const states = app.data.states || [];
  const indBars = barList(indBody, {
    rows: indRows, ariaLabel: t("adv.eco.byIndustry"),
    onHover: (r) => {
      if (!r) return link.hover(null);
      const top = states.map((s, i) => ({ i, v: ratio(s.gdp_by_industry?.[r.key], s.gdp) })).filter((x) => fin(x.v)).sort((a, b) => b.v - a.v).slice(0, 8);
      link.hover({ states: new Set(top.map((x) => x.i)), dimOthers: true });
    },
    onClick: (r) => { setIndustry(r.key === "government" ? "public_admin" : r.key); specBody.scrollIntoView({ behavior: "smooth", block: "start" }); },
  });

  // --- map: metro GDP circles -----------------------------------------------------------------------------------
  const mapBody = section(el, { title: t("adv.eco.map.title"), note: t("adv.eco.map.note") });
  const ppDomain = robustDomain(rows.filter((r) => r.v.population >= 100000).map((r) => r.v.gdp_pc), 0.03, true) || [30000, 120000];
  const ppColor = colorScale({ type: "seq", domain: ppDomain, ramp: RAMPS.gold });
  const gMax = Math.max(...rows.map((r) => r.v.gdp || 0));
  const bubbles = ctx.bubbles("gdp", {
    rMax: 30, minR: 1.5, alpha: 0.6,
    tip: (b) => `<b>${esc(b.row.name)}</b> <span class="sub">${esc(b.row.sub)}</span><br>${t("adv.eco.tip", { gdp: money(b.row.v.gdp), pc: money(b.row.v.gdp_pc), people: count3(b.row.v.population) })}`,
    onHover: (b) => { table.setHot(b ? b.key : null); scatter.setHot(b ? b.key : null); link.hover(b ? rowsHighlight(metros, [b.row]) : null); },
    onClick: (b) => app.selectCity(b.row.ref),
  });
  const bubbleItems = rows.filter((r) => fin(r.v.gdp)).map((r) => ({ key: r.key, x: app.w.grid.cx(r.ref.cell), y: app.w.grid.cy(r.ref.cell), value: r.v.gdp, color: ppColor(r.v.gdp_pc), row: r }));
  bubbles.set(bubbleItems, { vMax: gMax });
  const showBubbles = document.createElement("label");
  showBubbles.className = "adv-check";
  showBubbles.innerHTML = `<input type="checkbox" checked> ${t("adv.eco.showCircles")}`;
  showBubbles.querySelector("input").addEventListener("change", (e) => bubbles.set(e.target.checked ? bubbleItems : [], { vMax: gMax }));
  mapBody.appendChild(showBubbles);
  mapBody.insertAdjacentHTML("beforeend", rampLegend({ ramp: RAMPS.gold, domain: ppDomain, fmt: money, label: t("adv.eco.gdpPc") })
    + sizeLegend([1e10, 1e11, 1e12].filter((v) => v <= gMax), (v) => 30 * Math.sqrt(v / gMax) , money, t("adv.eco.circleArea")));

  // --- leaders --------------------------------------------------------------------------------------------------
  const lBody = section(el, { title: t("adv.eco.leaders"), note: t("adv.eco.leaders.note", { min: count3(METRO_MIN) }) });
  const big = rows.filter((r) => (r.v.population || 0) >= METRO_MIN);
  segmented(lBody, {
    label: t("adv.rankBy"), value: "gdp",
    options: [{ value: "gdp", label: t("adv.eco.largestGdp") }, { value: "gdp_pc", label: t("adv.eco.gdpPc") }, { value: "growth", label: t("adv.eco.fastest") }],
    onChange: (v) => { table.setRows(v === "gdp" ? rows : big); table.setColumns(cols, { key: v, dir: "desc" }); },
  });
  const cols = [
    { key: "name", label: t("adv.metro"), align: "l", value: (r) => r.name, html: (r) => `${esc(r.name)} <span class="sub">${esc(r.sub)}</span>` },
    { key: "gdp", label: t("adv.gdp"), value: (r) => r.v.gdp, text: (r) => money(r.v.gdp), bar: { max: gMax, color: "rgba(224,181,76,.35)" } },
    { key: "gdp_pc", label: t("adv.eco.perPerson"), value: (r) => r.v.gdp_pc, text: (r) => money(r.v.gdp_pc) },
    { key: "growth", label: t("adv.growth"), value: (r) => r.v.growth, text: (r) => signedPct(r.v.growth) },
  ];
  const table = createTable(lBody, {
    caption: t("adv.eco.metrosByGdp"), columns: cols, rows, sort: { key: "gdp", dir: "desc" }, rank: true, maxHeight: 280,
    search: t("adv.searchMetros"),
    onHover: (r) => { link.hover(r ? rowsHighlight(metros, [r]) : null); bubbles.setHot(r ? r.key : null); scatter.setHot(r ? r.key : null); },
    onClick: (r) => app.selectCity(r.ref),
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
    const o = r.ref;
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
  const scBody = section(el, { title: t("adv.eco.scatter.title"), note: t("adv.eco.scatter.note") });
  const scCtl = document.createElement("div");
  scCtl.className = "adv-row";
  scBody.appendChild(scCtl);
  let colorBy = "lq", allMetros = false;
  selectBox(scCtl, {
    label: t("adv.colour"), value: colorBy,
    options: [{ value: "lq", label: t("adv.eco.specChosen") }, { value: "unemployment", label: t("adv.f.unemployment.tile") }, { value: "median_income", label: t("adv.income") }, { value: "none", label: t("adv.none") }],
    onChange: (v) => { colorBy = v; drawScatter(); },
  });
  segmented(scCtl, { label: t("adv.metros"), value: "big", options: [{ value: "big", label: `${count3(METRO_MIN)}+` }, { value: "all", label: t("adv.all") }], onChange: (v) => { allMetros = v === "all"; drawScatter(); } });
  const legendEl = document.createElement("div");
  const scatter = createScatter(scBody, {
    points: [], height: 300,
    x: { label: t("adv.eco.gdpPc"), fmt: (v) => money(v), log: true },
    y: { label: t("adv.eco.popGrowth"), fmt: (v) => fmtShort("signed", v) },
    size: { label: t("adv.population"), fmt: count3, max: 15, min: 2 },
    refY: [{ v: n.growth ?? 0, label: t("adv.nationValue", { v: signedPct(n.growth) }) }],
    onHover: (p) => { link.hover(p ? rowsHighlight(metros, [p.row]) : null); bubbles.setHot(p ? p.key : null); table.setHot(p ? p.key : null, false); },
    onClick: (p) => app.selectCity(p.row.ref),
    onBrush: (set) => {
      const sel = set ? rows.filter((r) => set.has(r.key)) : [];
      link.base(sel.length ? rowsHighlight(metros, sel, { dim: true }) : specHighlight(), { frame: sel.length > 1 });
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
    return `${t("adv.eco.brush", { n: sel.length, people: count3(pop), gdp: money(gdp), share: pct(gdp / n.gdp) })} ${frameBtn()}<button type="button" class="adv-mini" data-clear>${t("adv.clear")}</button>`;
  }
  brushInfo.addEventListener("click", (e) => { if (e.target.closest("[data-clear]")) { scatter.setSelected(null); link.base(specHighlight()); bubbles.setSelected(null); brushInfo.innerHTML = ""; } });

  function drawScatter() {
    const list = rows.filter((r) => allMetros || (r.v.population || 0) >= METRO_MIN);
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
    indBars.setSelected(k === "public_admin" ? "government" : k);
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
      scatter.setHot(r ? r.key : null);
      specTable.setHot(r ? r.key : null);
    },
    onEscape() {
      if (scatter.selected) { scatter.setSelected(null); link.base(specHighlight()); bubbles.setSelected(null); brushInfo.innerHTML = ""; return true; }
      return false;
    },
  };
}
