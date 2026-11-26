// Culture advisor ("Keeper of Wonders"): wonders by published rule (wonders.json), the Faith and Amenities lenses with
// their caveats (counties.json columns), and disasters (disasters.json: FEMA declarations, NOAA billion-dollar events).
import { esc, fin, el as mk, colorScale } from "../core/util.js";
import { int, pct, money, count3, fixed } from "../core/fmt.js";
import { barList, shareBar, histogram } from "../core/charts.js";
import { createTable } from "../core/table.js";
import { section, tiles, segmented, mapPicker, sourcesHtml } from "../core/view.js";
import { rowsHighlight } from "../core/data.js";
import { frameBox, focusPoint } from "../core/frame.js";
import { t } from "../../../i18n.js";

// Labels are read when shown (i18n: the language is known once the data has loaded).
const KIND = {
  natural: { get label() { return t("adv.cult.kind.natural"); }, color: "#6aa84f" },
  university: { get label() { return t("adv.cult.kind.university"); }, color: "#4a86d6" },
  landmark: { get label() { return t("adv.cult.kind.landmark"); }, color: "#e0b54c" },
};
const RULE_TITLE = {
  national_park: "adv.cult.rule.national_park", park_unit: "adv.cult.rule.park_unit", research_university: "adv.cult.rule.research_university",
  landmark: "adv.cult.rule.landmark", world_heritage: "adv.cult.rule.world_heritage", cathedral: "adv.cult.rule.cathedral",
};
const ruleTitle = (id) => (RULE_TITLE[id] ? t(RULE_TITLE[id]) : null);
// The headline's count of wonders per rule, for wonder sets other than the original parks / universities / landmarks.
const RULE_COUNT = { world_heritage: "adv.cult.count.world_heritage", national_park: "adv.cult.count.national_park", cathedral: "adv.cult.count.cathedral" };
const ORIGINAL_RULES = new Set(["national_park", "park_unit", "research_university", "landmark"]);
const DIS_COLOR = { hurricane: "#4f9ad6", flood: "#2fa4b8", fire: "#e8774a", severe_storm: "#9a7bc9", winter: "#c9dcef", other: "#9a9aa8" };

export async function mount(ctx) {
  const { app, data, el, link } = ctx;
  const disastersP = app.loadData("disasters").catch(() => null); // lazy: only this advisor needs it
  const won = await app.loadData("wonders");
  const { states: stLevel, counties } = data.levels;
  const lensFaith = app.lensById?.get("faith"), lensTrad = app.lensById?.get("faith_tradition");
  const lensAmen = app.lensById?.get("amenities"), lensDis = app.lensById?.get("disasters");

  // --- headline -------------------------------------------------------------------------------------------------
  const wonders = (won?.wonders || []).map((w) => ({ ...w, key: w.id }));
  const byKind = (k) => wonders.filter((w) => w.kind === k).length;
  let adherents = null;
  if (counties) {
    let a = 0, p = 0;
    for (const r of counties.rows) if (fin(r.v.faith) && fin(r.v.population)) { a += (r.v.faith / 100) * r.v.population; p += r.v.population; }
    adherents = p ? (a / p) * 100 : null;
  }
  const tileEl = mk("div");
  el.appendChild(tileEl);
  const drawTiles = (dis) => {
    tileEl.innerHTML = tiles([
      { label: t("adv.cult.wonders"), value: int(wonders.length), sub: wondersSub() },
      ...(fin(won?.national?.park_visits) ? [{ label: t("adv.cult.parkVisits"), value: count3(won.national.park_visits), sub: t("adv.cult.parkVisitsSub", { year: won.national.park_visits_year || "" }) }] : []),
      ...(dis?.noaa?.national
        ? [{ label: t("adv.cult.billion"), value: int(dis.noaa.national.events), sub: `${dis.noaa.years?.join("–") || ""} · ${money(dis.noaa.national.cost_usd)}` }]
        : counties ? [{ label: t("adv.cult.adherents"), value: fin(adherents) ? t("adv.cult.per100", { v: fixed(adherents, 0) }) : "–", sub: t("adv.cult.adherentsSub") }] : []),
    ]);
  };
  function wondersSub() {
    const byRule = (...ids) => wonders.filter((w) => ids.includes(w.rule)).length;
    const rules = (won?.rules || []).map((r) => r.id);
    if (rules.every((id) => ORIGINAL_RULES.has(id))) {
      return t("adv.cult.wondersSub", { parks: byRule("national_park", "park_unit"), unis: byRule("research_university"), landmarks: byRule("landmark") });
    }
    return rules.map((id) => (RULE_COUNT[id] ? t(RULE_COUNT[id], { n: int(byRule(id)) }) : `${int(byRule(id))} ${id}`)).join(" · ");
  }
  drawTiles(null);

  // --- map colour -----------------------------------------------------------------------------------------------
  const mapRow = mk("div", "adv-sec adv-mapsec");
  el.appendChild(mapRow);
  const picker = mapPicker(ctx, mapRow, {
    value: "terrain",
    options: [
      { value: "terrain", label: t("adv.terrain"), lens: () => null },
      ...(lensFaith ? [{ value: "faith", label: t("adv.cult.faith"), lens: () => "faith" }] : []),
      ...(lensTrad ? [{ value: "trad", label: t("adv.cult.tradition"), lens: () => "faith_tradition" }] : []),
      ...(lensAmen ? [{ value: "amen", label: t("adv.cult.amenities"), lens: () => "amenities" }] : []),
      ...(lensDis ? [{ value: "dis", label: t("adv.cult.disasters"), lens: () => "disasters" }] : []),
    ],
  });

  // --- wonders --------------------------------------------------------------------------------------------------
  let wonderBars = [];
  const bubbles = ctx.bubbles("wonders", {
    rMax: 9, minR: 9, alpha: 0.28,
    tip: (b) => `<b>${esc(b.it.name)}</b><br>${esc(ruleTitle(b.it.rule) || b.it.kind)} #${b.it.rank} · ${esc(metricText(b.it))}${b.it.curated ? `<br><span class="sub">${t("adv.cult.handPicked")}</span>` : ""}`,
    onHover: (b) => { for (const w of wonderBars) w.setHot(b ? b.key : null); },
    onClick: (b) => flyTo(b.it),
  });
  if (won && wonders.length) {
    const wBody = section(el, { title: t("adv.cult.wonders"), kicker: t("adv.cult.kicker"), note: t("adv.cult.note") });
    let kind = "all";
    segmented(wBody, {
      label: t("adv.cult.kind"), value: kind,
      options: [{ value: "all", label: t("adv.all") }, ...Object.entries(KIND).filter(([k]) => byKind(k)).map(([k, v]) => ({ value: k, label: v.label }))],
      onChange: (v) => { kind = v; drawWonders(); },
    });
    const wHost = mk("div");
    wBody.appendChild(wHost);
    function drawWonders() {
      wHost.innerHTML = "";
      wonderBars = [];
      const vis = wonders.filter((w) => kind === "all" || w.kind === kind);
      for (const rule of won.rules || []) {
        const list = vis.filter((w) => w.rule === rule.id);
        if (!list.length) continue;
        wHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">${esc(ruleTitle(rule.id) || rule.id)}</h4><p class="adv-note adv-rule">${esc(rule.text)}</p>`);
        const host = mk("div");
        wHost.appendChild(host);
        const val = (w) => (w.kind === "university" ? w.metrics?.rd_usd : w.kind === "natural" ? w.metrics?.visits : null);
        wonderBars.push(barList(host, {
          rank: !rule.curated, compact: true, ariaLabel: ruleTitle(rule.id) || rule.id,
          rows: list.map((w) => ({ key: w.key, label: w.short || w.name, full: w.name, sub: w.state, value: val(w), text: metricText(w), color: KIND[w.kind]?.color })),
          onHover: (r) => {
            const w = r ? wonders.find((x) => x.key === r.key) : null;
            link.hover(w ? { cells: new Set(w.cells && w.cells.length ? w.cells : w.cell != null ? [w.cell] : []), label: w.short || w.name } : null);
            bubbles.setHot(w ? w.key : null);
          },
          onClick: (r) => flyTo(wonders.find((x) => x.key === r.key)),
        }));
      }
      bubbles.set(vis.filter((w) => fin(w.x) && fin(w.y)).map((w) => ({ key: w.key, x: w.x, y: w.y, value: 1, color: KIND[w.kind]?.color || "#ccc", it: w })), { vMax: 1 });
    }
    drawWonders();
    wBody.insertAdjacentHTML("beforeend", `<p class="adv-note">${t("adv.cult.markers", { natural: KIND.natural.color, university: KIND.university.color, landmark: KIND.landmark.color })}</p>`);
  } else el.insertAdjacentHTML("beforeend", `<p class="adv-empty pad">${t("adv.cult.noWonders")}</p>`);
  function flyTo(w) {
    if (!w) return;
    if (w.cells && w.cells.length > 2) {
      const b = app.highlightBounds({ cells: new Set(w.cells) });
      if (b) return frameBox(app, b, { pad: 60, maxScale: 3 });
    }
    focusPoint(app, w.x, w.y, Math.min(app.cam.maxScale, Math.max(app.cam.scale, (app.cam.fitScale || 1) * 3.2)));
  }

  // --- faith ----------------------------------------------------------------------------------------------------
  let faithStates = null;
  if (counties && lensTrad) {
    const fBody = section(el, { title: "Faith", kicker: "2020 U.S. Religion Census" });
    fBody.insertAdjacentHTML("beforeend", `<p class="adv-callout adv-caveat">${esc(lensTrad.note || lensFaith?.note || "")}</p>`);
    const cats = lensTrad.categories || [];
    const catByName = new Map(cats.map((c) => [c.name, c]));
    const popBy = new Map();
    for (const r of counties.rows) {
      const c = catByName.get(r.v.faith_tradition);
      if (c && fin(r.v.population)) popBy.set(c.id, (popBy.get(c.id) || 0) + r.v.population);
    }
    fBody.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Residents of counties where each tradition is the largest</h4>`);
    const tradRows = (id) => counties.rows.filter((r) => catByName.get(r.v.faith_tradition)?.id === id);
    shareBar(fBody, {
      parts: cats.map((c) => ({ key: c.id, label: c.name, value: popBy.get(c.id) || 0, color: c.color, text: `${count3(popBy.get(c.id) || 0)} people` })),
      onHover: (p) => link.hover(p ? rowsHighlight(counties, tradRows(p.key), { dim: true, label: p.label }) : null),
      onClick: () => picker.set("trad"),
    });
    fBody.insertAdjacentHTML("beforeend", `<p class="adv-note">"Largest" can be a plurality of a small share of residents. Click to colour the map by tradition.</p>`);
    let order = "most";
    const sRow = mk("div", "adv-row");
    fBody.appendChild(sRow);
    sRow.insertAdjacentHTML("beforeend", `<span class="adv-note" style="margin:0">States by adherents per 100 residents ≈</span>`);
    segmented(sRow, { label: "Order", value: order, options: [{ value: "most", label: "Most" }, { value: "fewest", label: "Fewest" }], onChange: (v) => { order = v; drawFaith(); } });
    const sHost = mk("div");
    fBody.appendChild(sHost);
    const fColor = colorScale({ type: "seq", domain: [0, 100], ramp: lensFaith?.ramp });
    function drawFaith() {
      sHost.innerHTML = "";
      const list = stLevel.rows.filter((r) => fin(r.v.faith)).sort((a, b) => (order === "most" ? b.v.faith - a.v.faith : a.v.faith - b.v.faith)).slice(0, 10);
      faithStates = barList(sHost, {
        rank: true, compact: true, max: 100, ariaLabel: "States by adherents per 100 residents",
        rows: list.map((r) => ({ key: r.key, label: r.name, value: Math.min(100, r.v.faith), text: r.v.faith.toFixed(0), color: fColor(r.v.faith) })),
        onHover: (x) => link.hover(x ? rowsHighlight(stLevel, [stLevel.byKey.get(x.key)], { dim: true }) : null),
        onClick: (x) => { picker.set("faith"); stLevel.focus(stLevel.byKey.get(x.key)); },
      });
    }
    drawFaith();
    fBody.insertAdjacentHTML("beforeend", `<p class="adv-note">State figures are population-weighted means of county rates (≈). Adherents are counted where congregations meet, so a county can pass 100.</p>`);
  }

  // --- amenities ------------------------------------------------------------------------------------------------
  let amenHist = null, amenTable = null;
  if (counties && lensAmen) {
    const aBody = section(el, { title: "Amenities and wellbeing", kicker: "CDC PLACES" });
    aBody.insertAdjacentHTML("beforeend", `<p class="adv-callout adv-caveat">${esc(lensAmen.note || "")}</p><p class="adv-note">${esc(lensAmen.description || "")}</p>`);
    const rows = counties.rows.filter((r) => fin(r.v.amenities));
    const aColor = colorScale({ type: "seq", domain: lensAmen.domain || [85, 120], ramp: lensAmen.ramp });
    amenHist = histogram(aBody, {
      values: rows.map((r) => ({ key: r.key, v: r.v.amenities })), bins: 30, domain: lensAmen.domain ? [lensAmen.domain[0] - 10, lensAmen.domain[1] + 10] : undefined,
      fmt: (v) => v.toFixed(0), unitLabel: "counties", label: "Histogram of county Amenities index",
      colorOf: (v) => aColor(v), markers: [{ v: 100, label: "average county" }],
      onHover: (bin) => link.hover(bin ? rowsHighlight(counties, bin.keys.map((k) => counties.byKey.get(k)), { dim: true }) : null),
    });
    amenTable = createTable(aBody, {
      caption: "Counties by Amenities", rank: true, maxHeight: 240, search: "Search counties",
      rows: rows.filter((r) => (r.v.population || 0) >= 50000),
      columns: [
        { key: "name", label: "County", align: "l", width: "minmax(0,1.6fr)", value: (r) => r.name, html: (r) => `${esc(r.name)} <span class="sub">${esc(r.sub)}</span>` },
        { key: "amenities", label: "Index", value: (r) => r.v.amenities, text: (r) => r.v.amenities.toFixed(1), bar: { max: 130, color: "rgba(126,207,142,.3)" } },
        { key: "mhlth", label: "Distress", short: "Mental distress", value: (r) => r.v.mhlth, text: (r) => pct(r.v.mhlth), title: "Adults with 14+ poor mental-health days a month" },
        { key: "loneliness", label: "Lonely", value: (r) => r.v.loneliness, text: (r) => pct(r.v.loneliness), title: "Adults who feel lonely at least sometimes (not published for some states)", hideBelow: 400 },
      ],
      sort: { key: "amenities", dir: "desc" },
      onHover: (r) => link.hover(r ? rowsHighlight(counties, [r]) : null),
      onClick: (r) => counties.focus(r),
    });
    aBody.insertAdjacentHTML("beforeend", `<p class="adv-note">Counties of 50,000+ people. Kentucky and Pennsylvania have no PLACES data in this release and are left blank, never filled in.</p>`);
  }

  // --- disasters (lazy) -----------------------------------------------------------------------------------------
  const dSec = section(el, { title: t("adv.cult.disasters"), kicker: lensDis ? t("adv.cult.disKicker") : "" });
  dSec.innerHTML = `<p class="adv-loading">${t("adv.cult.disLoading")}</p>`;
  const srcEl = mk("div");
  el.appendChild(srcEl);
  const drawSources = (dis) => {
    srcEl.innerHTML = sourcesHtml(data, [...(won?.sources || []), "usrc_2020", "cdc_places", ...(dis?.sources || ["fema_declarations", "noaa_billions"])], [
      // Each caveat only where its data is on this map (the US map has them all).
      ...(lensFaith ? [t("adv.cult.c.faith", { note: esc(lensFaith.note || t("adv.cult.c.faithDefault")) })] : []),
      ...(lensAmen ? [t("adv.cult.c.amen", { note: esc(lensAmen.note || t("adv.cult.c.amenDefault")) })] : []),
      ...(lensDis ? [t("adv.cult.c.fema"), t("adv.cult.c.noaa")] : []),
      ...(fin(won?.national?.park_visits) ? [t("adv.cult.c.parks")] : []),
      ...(wonders.some((w) => w.kind === "university") ? [t("adv.cult.c.unis")] : []),
    ]);
  };
  drawSources(null);
  let dState = null, dCounty = null;
  // The disaster records arrive after the rest of the dashboard is up (the view may be gone by then).
  disastersP.then((dis) => {
    if (!active()) return;
    if (!dis) dSec.innerHTML = `<p class="adv-empty">${t("adv.cult.noDisasters")}</p>`;
    else drawDisasters(dis);
    drawTiles(dis);
    drawSources(dis);
  });

  function drawDisasters(D) {
    dSec.innerHTML = "";
    const fema = D.fema || {}, noaa = D.noaa || {};
    dSec.insertAdjacentHTML("beforeend", `<p class="adv-callout adv-caveat">A declaration is an administrative act that unlocks federal aid, not a measure of damage.</p><p class="adv-note">${esc(fema.rule || "")}</p>`);
    // County rows by geoid.
    const cols = fema.counties?.columns || [];
    const ci = Object.fromEntries(cols.map((k, j) => [k, j]));
    const cRows = new Map((fema.counties?.rows || []).map((r) => [r[ci.geoid], r]));
    const types = fema.types || [];
    const nat = {};
    for (const s of Object.values(fema.states || {})) for (const [k, v] of Object.entries(s.by_type || {})) nat[k] = (nat[k] || 0) + (v || 0);
    const natTotal = Object.values(fema.states || {}).reduce((a, s) => a + (s.total || 0), 0);
    dSec.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">${int(natTotal)} major-disaster declarations since ${esc((fema.window || [])[0]?.slice(0, 4) || "2000")}, by type (all states and territories)</h4>`);
    const typeCounties = (id) => counties ? counties.rows.filter((r) => { const x = cRows.get(r.key); return x && x[ci[id]] > 0; }) : [];
    shareBar(dSec, {
      parts: types.map((t) => ({ key: t.id, label: t.name, value: nat[t.id] || 0, color: DIS_COLOR[t.id] || "#999", text: int(nat[t.id] || 0) })),
      onHover: (p) => link.hover(p ? rowsHighlight(counties, typeCounties(p.key), { dim: true, label: `Counties with a ${p.label.toLowerCase()} declaration` }) : null),
      onClick: () => picker.set("dis"),
    });

    // States: FEMA + NOAA.
    const abbrs = [...new Set([...Object.keys(fema.states || {}), ...Object.keys(noaa.states || {})])];
    const sum = (o) => Object.values(o || {}).reduce((a, v) => a + (fin(v) ? v : 0), 0);
    const sRows = abbrs.map((a) => {
      const f = fema.states?.[a], n = noaa.states?.[a], row = stLevel.byKey.get(a);
      return { key: a, name: row?.name || a, row, fema: f?.total ?? null, nEvents: n ? sum(n.count) : null, nCost: n ? sum(n.cost_usd) : null, n };
    });
    dSec.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">By state</h4>`);
    dState = createTable(dSec, {
      caption: "Disasters by state", rank: true, maxHeight: 240, search: "Search states",
      rows: sRows,
      columns: [
        { key: "name", label: "State", align: "l", width: "minmax(0,1.4fr)", value: (r) => r.name, html: (r) => `${esc(r.name)}${r.row ? "" : ` <span class="sub">off map</span>`}` },
        { key: "fema", label: "FEMA", short: "FEMA decl&shy;arations", value: (r) => r.fema, text: (r) => (fin(r.fema) ? int(r.fema) : "–") },
        { key: "nEvents", label: "$1B+ events", short: "$1B+ events", value: (r) => r.nEvents, text: (r) => (fin(r.nEvents) ? int(r.nEvents) : "–"), title: `NOAA billion-dollar events that touched the state, ${(noaa.years || []).join("–")}` },
        { key: "nCost", label: "Their cost", short: "Its share of the cost", value: (r) => r.nCost, text: (r) => money(r.nCost), bar: { max: Math.max(...sRows.map((r) => r.nCost || 0), 1), color: "rgba(232,119,74,.3)" }, title: `The state's share of those events' CPI-adjusted cost (${noaa.unit || "USD"})` },
      ],
      sort: { key: "nCost", dir: "desc" },
      onHover: (r) => link.hover(r?.row ? rowsHighlight(stLevel, [r.row], { dim: true }) : null),
      onClick: (r) => { if (r.row) stLevel.focus(r.row); },
    });
    dSec.insertAdjacentHTML("beforeend", `<p class="adv-note">${esc(noaa.rule || "")}${noaa.final ? " NOAA's final release: the series is no longer updated." : ""}</p>`);

    // Counties with the most declarations.
    if (counties) {
      dSec.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Most-declared counties</h4>`);
      const rows = counties.rows.filter((r) => cRows.has(r.key)).map((r) => ({ ...r, dx: cRows.get(r.key) }));
      dCounty = createTable(dSec, {
        caption: "Counties by disaster declarations", rank: true, maxHeight: 240, search: "Search counties", rows,
        columns: [
          { key: "name", label: "County", align: "l", width: "minmax(0,1.6fr)", value: (r) => r.name, html: (r) => `${esc(r.name)} <span class="sub">${esc(r.sub)}</span>` },
          { key: "total", label: "Declared", value: (r) => r.dx[ci.total], text: (r) => int(r.dx[ci.total]), bar: { max: Math.max(...rows.map((r) => r.dx[ci.total] || 0), 1), color: "rgba(207,106,74,.3)" } },
          { key: "top", label: "Mostly", align: "l", width: "minmax(0,1fr)", hideBelow: 380, value: (r) => topType(r.dx), text: (r) => types.find((t) => t.id === topType(r.dx))?.name.split(/[ ,&]/)[0] || "–" },
          { key: "last", label: "Last", align: "l", width: "78px", value: (r) => r.dx[ci.last_date], text: (r) => r.dx[ci.last_date] || "–" },
        ],
        sort: { key: "total", dir: "desc" },
        onHover: (r) => link.hover(r ? rowsHighlight(counties, [counties.byKey.get(r.key)]) : null),
        onClick: (r) => counties.focus(counties.byKey.get(r.key)),
      });
      function topType(x) {
        let best = null, bv = 0;
        for (const t of types) if ((x[ci[t.id]] || 0) > bv) { bv = x[ci[t.id]]; best = t.id; }
        return best;
      }
    }

    // The last 12 months.
    const recent = fema.recent || [];
    if (recent.length) {
      dSec.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Declared in the last ${Math.round((fema.recent_days || 365) / 30)} months (to ${esc(fema.as_of || "")})</h4>`);
      createTable(dSec, {
        caption: "Recent declarations", maxHeight: 220, rowKey: (r) => r.disaster,
        rows: recent,
        columns: [
          { key: "date", label: "Date", align: "l", width: "78px", value: (r) => r.date, text: (r) => r.date },
          { key: "state", label: "State", align: "l", width: "38px", value: (r) => r.state, text: (r) => r.state },
          { key: "type", label: "What", align: "l", width: "minmax(0,1.6fr)", value: (r) => r.title, html: (r) => `<i class="dot" style="background:${DIS_COLOR[r.type] || "#999"}"></i>${esc(titleCase(r.title))}`, tip: (r) => `DR-${r.disaster}: ${r.incident_type} · ${titleCase(r.title)}` },
          { key: "areas", label: "Areas", value: (r) => r.areas, text: (r) => (r.statewide ? "statewide" : int(r.areas)), title: "FEMA's designated areas (counties and tribal areas, including ones off the map)" },
        ],
        sort: { key: "date", dir: "desc" },
        onHover: (r) => {
          if (!r) return link.hover(null);
          const rows = counties ? (r.counties || []).map((g) => counties.byKey.get(g)).filter(Boolean) : [];
          const i = stLevel.byKey.get(r.state)?.ref;
          link.hover(rows.length ? rowsHighlight(counties, rows, { dim: true, label: `${titleCase(r.title)}, ${r.state}` }) : i != null ? { states: new Set([i]), dimOthers: true, label: r.state } : null);
        },
        onClick: (r) => {
          const rows = counties ? (r.counties || []).map((g) => counties.byKey.get(g)).filter(Boolean) : [];
          const b = rows.length ? app.highlightBounds(counties.highlight(rows)) : null;
          if (b) frameBox(app, b, { pad: 50, maxScale: 2.6 });
        },
      });
    }

    // NOAA by year and the costliest events.
    const years = noaa.national?.by_year || [];
    if (years.length) {
      dSec.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Billion-dollar disasters per year, ${(noaa.years || []).join("–")} (NOAA, ${esc(noaa.unit || "CPI-adjusted")})</h4>`);
      dSec.appendChild(columnChart(years, (y) => y.events, (y) => `${y.year}: ${y.events} events, ${money(y.cost_usd)}`));
      const worst = noaa.national?.costliest || [];
      if (worst.length) {
        dSec.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">The costliest</h4><ol class="adv-olist">${worst.map((e) => `<li><b>${esc(e.name)}</b> <span class="sub">${money(e.cost_usd)}${fin(e.deaths) ? ` · ${int(e.deaths)} deaths` : ""}</span></li>`).join("")}</ol>`);
      }
    }
  }

  const api = {
    onMapHover(h) {
      const owner = h.cell >= 0 ? app.w.raw.owner[h.cell] : -1;
      const sr = owner >= 0 ? stLevel.rows[owner] : null;
      faithStates?.setHot(sr ? sr.key : null);
      dState?.setHot(sr ? sr.key : null, false);
      const c = h.cell >= 0 && counties ? counties.rowAtCell(h.cell) : null;
      amenHist?.setHot(c && amenHist.binOf ? amenHist.binOf(c.v.amenities)?.i ?? null : null);
      amenTable?.setHot(c ? c.key : null, false);
      dCounty?.setHot(c ? c.key : null, false);
      if (h.item?.kind === "wonder") for (const w of wonderBars) w.setHot(h.item.data?.id ?? null);
    },
    onMapClick(ev) {
      if (ev.item?.kind !== "wonder") return false;
      flyTo(wonders.find((w) => w.id === ev.item.data?.id));
      return true;
    },
  };
  return api;

  function active() { return el.isConnected; }
}

function metricText(w) {
  const m = w.metrics || {};
  if (w.kind === "university") return fin(m.rd_usd) ? t("adv.cult.rd", { v: money(m.rd_usd) }) : "–";
  if (w.kind === "natural") return fin(m.visits) ? t("adv.cult.visits", { v: count3(m.visits) }) : "–";
  if (fin(m.visits)) return t("adv.cult.visits", { v: count3(m.visits) });
  return fin(m.designated) ? t("adv.cult.landmarkSince", { year: m.designated }) : t("adv.cult.landmarkWord");
}

const titleCase = (s) => String(s || "").toLowerCase().replace(/\b([a-z])/g, (c) => c.toUpperCase()).replace(/\b(And|Of|The|In)\b/g, (w) => w.toLowerCase());

/** A small SVG column chart (one column per item). */
function columnChart(items, val, label) {
  const W = 400, H = 110, m = { l: 4, r: 4, t: 6, b: 18 };
  const max = Math.max(1, ...items.map(val));
  const bw = (W - m.l - m.r) / items.length;
  const div = document.createElement("div");
  div.className = "adv-hist adv-cols-chart";
  const first = items[0]?.year, last = items[items.length - 1]?.year;
  div.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="none" role="img" aria-label="Events per year">
    ${items.map((it, i) => { const h = (val(it) / max) * (H - m.t - m.b); return `<g class="bin"><rect class="hit" x="${(m.l + i * bw).toFixed(2)}" y="${m.t}" width="${bw.toFixed(2)}" height="${H - m.t - m.b}"/><rect class="bar" x="${(m.l + i * bw + 0.4).toFixed(2)}" y="${(H - m.b - h).toFixed(2)}" width="${Math.max(0.5, bw - 0.8).toFixed(2)}" height="${h.toFixed(2)}" fill="#cf6a4a"/><title>${esc(label(it))}</title></g>`; }).join("")}
    <line x1="${m.l}" x2="${W - m.r}" y1="${H - m.b + 0.5}" y2="${H - m.b + 0.5}" class="axis"/>
    <text x="${m.l}" y="${H - 5}" class="tick">${first ?? ""}</text><text x="${W - m.r}" y="${H - 5}" text-anchor="end" class="tick">${last ?? ""}</text>
    <text x="${m.l + 2}" y="${m.t + 9}" class="tick">${max} max</text>
  </svg>`;
  return div;
}

