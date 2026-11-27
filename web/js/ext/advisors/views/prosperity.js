// Prosperity & Housing advisor: income vs home values, poverty, rents and unemployment.
import { esc, fin, colorScale, RAMPS } from "../core/util.js";
import { money, dollars, pct, int, count3, fmtShort, fixed, times } from "../core/fmt.js";
import { barList, histogram, rampLegend } from "../core/charts.js";
import { createTable } from "../core/table.js";
import { createScatter } from "../core/scatter.js";
import { section, tiles, segmented, lensButton, sourcesHtml, topBy, frameBtn } from "../core/view.js";
import { rowsHighlight } from "../core/data.js";
import { t } from "../../../i18n.js";

const METRO_MIN = 250000;
const BIG_METRO = 500000;

export function mount(ctx) {
  const { app, data, el, link } = ctx;
  const n = data.nat;
  const { states, metros, counties } = data.levels;
  // Housing cost against income: home value where the country publishes it (US), else a year's rent (Spain: no
  // official home value by place, DECISIONS E49; rent from SERPAVI, E29).
  const byHome = fin(n.home_value);
  const cost = byHome
    ? { of: (r) => r.v.home_value, domain: [2, 10], ref: [3, 5, 8].map((k) => ({ k, label: `${k}×` })), fmt: (v) => times(+v, 1), legendFmt: (v) => `×${v}` }
    : { of: (r) => (fin(r.v.median_rent) ? r.v.median_rent * 12 : null), domain: [0.1, 0.3], ref: [0.1, 0.2, 0.3].map((k) => ({ k, label: pct(k, 0) })), fmt: (v) => pct(+v), legendFmt: (v) => pct(v, 0) };

  el.insertAdjacentHTML("beforeend", tiles([
    { label: t("adv.pros.medianIncome"), value: dollars(n.median_income), sub: t("adv.pros.perHousehold") },
    byHome
      ? { label: t("adv.pros.medianHome"), value: money(n.home_value), sub: fin(n.home_value / n.median_income) ? t("adv.pros.timesIncome", { x: fixed(n.home_value / n.median_income, 1) }) : "" }
      : { label: t("adv.pros.medianRent"), value: t("adv.perMonth", { v: dollars(n.median_rent) }), sub: fin(n.rent_burden) ? t("adv.pros.ofIncome", { share: pct(n.rent_burden) }) : "" },
    { label: t("adv.f.unemployment.tile"), value: pct(n.unemployment), sub: data.vintageOf("unemployment") },
  ]));

  // --- income vs home value (or yearly rent) --------------------------------------------------------------------
  const aBody = section(el, { title: t(byHome ? "adv.pros.afford.title" : "adv.pros.rentAfford.title"), note: t(byHome ? "adv.pros.afford.note" : "adv.pros.rentAfford.note") });
  const aCtl = document.createElement("div");
  aCtl.className = "adv-row";
  aBody.appendChild(aCtl);
  let level = counties ? "counties" : "metros";
  segmented(aCtl, { label: t("adv.places"), value: level, options: [...(counties ? [{ value: "counties", label: counties.label }] : []), { value: "metros", label: metros.label }], onChange: (v) => { level = v; drawAfford(); } });
  for (const [id, label] of [["income", t("adv.pros.incomeLens")], ["home", t("adv.pros.homeLens")]]) {
    const b = lensButton(app, id, label);
    if (b) aCtl.appendChild(b);
  }
  const ratioColor = colorScale({ type: "seq", domain: cost.domain, ramp: RAMPS.heat });
  const lv = () => data.levels[level];
  const inc = (r) => (level === "counties" ? r.v.income : r.v.median_income);
  const ratioOf = (r) => (fin(cost.of(r)) && fin(inc(r)) && inc(r) > 0 ? cost.of(r) / inc(r) : null);
  const scatter = createScatter(aBody, {
    height: 310, points: [],
    x: { label: t("adv.pros.x"), fmt: money, log: true },
    y: { label: t(byHome ? "adv.pros.y" : "adv.pros.yRent"), fmt: money, log: true },
    size: { label: t("adv.population"), fmt: count3, max: 14, min: 1.4 },
    refLines: cost.ref,
    color: (c) => ratioColor(c), colorLabel: t(byHome ? "adv.pros.homeIncome" : "adv.pros.rentIncome"), colorFmt: cost.fmt,
    onHover: (p) => { link.hover(p ? rowsHighlight(lv(), [p.row]) : null); affTable.setHot(p ? p.key : null, false); },
    onClick: (p) => lv().focus(p.row),
    onBrush: (set) => {
      const sel = set ? lv().rows.filter((r) => set.has(r.key)) : [];
      link.base(sel.length ? rowsHighlight(lv(), sel, { dim: true }) : null, { frame: sel.length > 1 });
      affTable.setSelected(set);
      selInfo.innerHTML = sel.length ? `${t("adv.selected", { n: int(sel.length), what: esc(lv().label.toLowerCase()), people: count3(sel.reduce((a, r) => a + (r.v.population || 0), 0)) })} ${frameBtn()}<button type="button" class="adv-mini" data-clear>${t("adv.clear")}</button>` : "";
    },
  });
  aBody.insertAdjacentHTML("beforeend", rampLegend({ ramp: RAMPS.heat, domain: cost.domain, fmt: cost.legendFmt, label: t(byHome ? "adv.pros.homeValueIncome" : "adv.pros.rentIncome") }));
  const selInfo = document.createElement("div");
  selInfo.className = "adv-brushinfo";
  aBody.appendChild(selInfo);
  const clearSel = () => { scatter.setSelected(null); affTable.setSelected(null); link.base(null); selInfo.innerHTML = ""; };
  selInfo.addEventListener("click", (e) => { if (e.target.closest("[data-clear]")) clearSel(); });
  aBody.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">${t("adv.pros.affTable")}</h4>`);
  const affTable = createTable(aBody, {
    caption: t(byHome ? "adv.pros.affCaption" : "adv.pros.rentAffCaption"), rank: true, maxHeight: 260, rows: [], search: t("adv.searchPlaces"),
    columns: [
      { key: "name", label: t("adv.place"), align: "l", value: (r) => r.name, html: (r) => `${esc(r.name)} <span class="sub">${esc(r.sub)}</span>` },
      { key: "inc", label: t("adv.income"), value: inc, text: (r) => money(inc(r)) },
      { key: "home", label: t(byHome ? "adv.home" : "adv.pros.rentYear"), value: cost.of, text: (r) => money(cost.of(r)) },
      { key: "ratio", label: t("adv.ratio"), value: (r) => ratioOf(r), html: (r) => fin(ratioOf(r)) ? `<span class="dot" style="background:${ratioColor(ratioOf(r))}"></span>${cost.fmt(ratioOf(r))}` : "–" },
    ],
    sort: { key: "ratio", dir: "desc" },
    onHover: (r) => { link.hover(r ? rowsHighlight(lv(), [r]) : null); scatter.setHot(r ? r.key : null); },
    onClick: (r) => lv().focus(r),
  });
  function drawAfford() {
    clearSel();
    const rows = lv().rows.filter((r) => fin(ratioOf(r)));
    scatter.update({
      points: rows.map((r) => ({ key: r.key, x: inc(r), y: cost.of(r), s: r.v.population, c: ratioOf(r), label: r.name, sub: r.sub, row: r })),
      labels: topBy(rows, (r) => r.v.population, { n: 6 }).map((x) => x.r.key),
    });
    affTable.setRows(rows);
  }
  drawAfford();

  // --- poverty --------------------------------------------------------------------------------------------------
  let povHist = null;
  if (counties) {
    const pBody = section(el, { title: "Poverty", note: "Counties by the share of people below the official poverty line. Hover a bar to outline those counties; the table lists them all." });
    const pCtl = document.createElement("div");
    pCtl.className = "adv-row";
    pBody.appendChild(pCtl);
    const lb = lensButton(app, "poverty", "Poverty lens");
    if (lb) pCtl.appendChild(lb);
    const pHost = document.createElement("div");
    pBody.appendChild(pHost);
    const usPov = (() => {
      let a = 0, w = 0;
      for (const r of counties.rows) if (fin(r.v.poverty) && fin(r.v.population)) { a += r.v.poverty * r.v.population; w += r.v.population; }
      return w ? a / w : null;
    })();
    povHist = histogram(pHost, {
      values: counties.rows.map((r) => ({ key: r.key, v: r.v.poverty, w: r.v.population })), bins: 30, domain: [0, 0.45], height: 120,
      fmt: (v) => fmtShort("pct", v), unitLabel: "counties", label: "Histogram of county poverty rates",
      colorOf: (_, t) => colorScale({ type: "seq", domain: [0, 1], ramp: RAMPS.heat })(t),
      markers: fin(usPov) ? [{ v: usPov, label: `Lower 48 ${pct(usPov)}` }] : [],
      onHover: (bin) => link.hover(bin ? rowsHighlight(counties, bin.keys.map((k) => counties.byKey.get(k)), { dim: true }) : null),
    });
    const povTable = createTable(pBody, {
      caption: "County poverty rates", rank: true, maxHeight: 240, rows: counties.rows.filter((r) => fin(r.v.poverty)), search: "Search counties",
      columns: [
        { key: "name", label: "County", align: "l", value: (r) => r.name, html: (r) => `${esc(r.name)} <span class="sub">${esc(r.sub)}</span>` },
        { key: "population", label: "People", value: (r) => r.v.population, text: (r) => count3(r.v.population) },
        { key: "poverty", label: "Poverty", value: (r) => r.v.poverty, text: (r) => pct(r.v.poverty), bar: { max: 0.5, color: "rgba(232,119,74,.4)" } },
        { key: "income", label: "Income", value: (r) => r.v.income, text: (r) => money(r.v.income) },
      ],
      sort: { key: "poverty", dir: "desc" },
      onHover: (r) => link.hover(r ? rowsHighlight(counties, [r]) : null),
      onClick: (r) => counties.focus(r),
    });
    ctx.cleanup(() => povTable.destroy());
  }

  // --- rent -----------------------------------------------------------------------------------------------------
  const rBody = section(el, { title: t("adv.pros.rent.title"), note: t("adv.pros.rent.note", { min: count3(METRO_MIN) }) });
  const rentRows = (list) => list.map((x) => ({ key: x.r.key, label: x.r.name, sub: t("adv.perMonth", { v: dollars(x.r.v.median_rent) }), value: x.v, text: pct(x.v), row: x.r }));
  const rOpts = { onHover: (r) => link.hover(r ? rowsHighlight(metros, [r.row]) : null), onClick: (r) => metros.focus(r.row) };
  const hi = topBy(metros.rows, (r) => r.v.rent_burden, { n: 10, min: METRO_MIN });
  const lo = topBy(metros.rows, (r) => r.v.rent_burden, { n: 5, min: METRO_MIN, asc: true });
  const rmax = Math.max(...hi.map((x) => x.v));
  rBody.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">${t("adv.pros.heaviest")}</h4>`);
  barList(rBody, { ...rOpts, rows: rentRows(hi), max: rmax, ariaLabel: t("adv.pros.heaviestAria") });
  rBody.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">${t("adv.pros.lightest")}</h4>`);
  barList(rBody, { ...rOpts, rows: rentRows(lo), max: rmax, ariaLabel: t("adv.pros.lightestAria") });

  // --- unemployment ---------------------------------------------------------------------------------------------
  const uBody = section(el, { title: t("adv.f.unemployment.tile"), note: t("adv.pros.unemp.note", { vintage: esc(data.vintageOf("unemployment")), min: count3(BIG_METRO) }) });
  const uHost = document.createElement("div");
  let uLevel = "states";
  segmented(uBody, { label: t("adv.areas"), value: uLevel, options: [{ value: "states", label: states.label }, { value: "metros", label: t("adv.largeMetros") }], onChange: (v) => { uLevel = v; drawU(); } });
  uBody.appendChild(uHost);
  function drawU() {
    uHost.innerHTML = "";
    const lvU = uLevel === "states" ? states : metros;
    const min = uLevel === "states" ? 0 : BIG_METRO;
    const high = topBy(lvU.rows, (r) => r.v.unemployment, { n: 8, min });
    const low = topBy(lvU.rows, (r) => r.v.unemployment, { n: 8, min, asc: true });
    const max = Math.max(...high.map((x) => x.v));
    const mk = (list) => list.map((x) => ({ key: x.r.key, label: x.r.name, sub: uLevel === "metros" ? x.r.sub : "", value: x.v, text: pct(x.v), tone: x.v > n.unemployment * 1.03 ? "bad" : x.v < n.unemployment * 0.97 ? "good" : null, row: x.r }));
    const o = { max, onHover: (r) => link.hover(r ? rowsHighlight(lvU, [r.row]) : null), onClick: (r) => lvU.focus(r.row) };
    uHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">${t("adv.highest")}</h4>`);
    barList(uHost, { ...o, rows: mk(high) });
    uHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">${t("adv.lowest")}</h4>`);
    barList(uHost, { ...o, rows: mk(low) });
  }
  drawU();

  el.insertAdjacentHTML("beforeend", sourcesHtml(data, ["acs_1yr", "acs_5yr"], [
    counties ? t("adv.pros.c1", { vintage: esc(data.vintage), countyVintage: esc(data.countyVintage) }) : t("adv.pros.c1NoCounties", { vintage: esc(data.vintage) }),
    t("adv.pros.c2"),
    t("adv.pros.c3"),
    t("adv.pros.c4"),
    ...(data.countiesOffMap ? [t("adv.offMapCounties", { n: int(data.countiesOffMap) })] : []),
  ]));

  return {
    onMapHover(h) {
      const l = lv();
      const r = h.cell >= 0 ? l.rowAtCell(h.cell) : null;
      scatter.setHot(r ? r.key : null);
      affTable.setHot(r ? r.key : null);
      if (povHist && counties) {
        const c = h.cell >= 0 ? counties.rowAtCell(h.cell) : null;
        povHist.setHot(c ? povHist.binOf(c.v.poverty)?.i ?? null : null);
      }
    },
    onEscape() {
      if (scatter.selected) { clearSel(); return true; }
      return false;
    },
  };
}
