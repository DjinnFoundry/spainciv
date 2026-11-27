// Commerce advisor ("Master of Trade"): freight routes between zones (trade.json: FAF5 values between US metros and
// states, or EPTMC road tonnes between Spain's autonomous communities), the busiest ports and airports and the road and
// rail network (infrastructure.json). The trade section reads either file through one adapter (`size`, `fmt`, the
// zone cells); the US text of the FAF file stays in its branches.
import { esc, fin, el as mk, withAlpha } from "../core/util.js";
import { int, pct, money, count3, signedPct, shownTons, shownWeight } from "../core/fmt.js";
import { longDate } from "../../../format.js";
import { country } from "../../../app/country.js";
import { barList, shareBar, stackedBars, swatchLegend, sizeLegend } from "../core/charts.js";
import { createTable } from "../core/table.js";
import { section, tiles, segmented, sourcesHtml } from "../core/view.js";
import { frameBox, focusPoint } from "../core/frame.js";
import { routeSize } from "../../../render/art/improvements.js";
import { t } from "../../../i18n.js";

// Route colours by FAF mode (original palette: ochre road, iron rail, blue water, lilac air, sea-green mixed,
// dark copper pipeline drawn dashed).
const MODE_COLOR = { truck: "#d9a457", rail: "#a3acb8", water: "#4f9ad6", air: "#c9a0e0", multiple: "#8fcbb8", pipeline: "#b0703e", other: "#9a9aa8" };
const PORT_COLOR = "#4f9ad6", AIR_COLOR = "#e6cf86";
const MUSD = 1e6; // trade.json values are million dollars

export async function mount(ctx) {
  const { app, el, link, data } = ctx;
  const [trade, infra] = await Promise.all([app.loadData("trade"), app.loadData("infrastructure")]);
  if (!trade && !infra) {
    el.innerHTML = `<p class="adv-empty pad">${t("adv.com.none")}</p>`;
    return {};
  }
  const grid = app.w.grid;
  const metros = data.levels.metros;
  const api = { hotRoute: null };
  let zoneOfCity = null;
  // The file's measure: "tons" (Spain, thousand tonnes) or value (the US, million dollars).
  const tons = trade?.measure === "tons";
  const size = (r) => routeSize(trade, r);
  // Every tonne figure of the section takes three significant digits ("54,6 M t", "932 mil t"), the table's too.
  const fmt = tons ? (kt) => (fin(kt) ? t("adv.tons", { v: count3(kt * 1e3) }) : "–") : (musd) => money(musd * MUSD);
  const nb = (s) => s.replace(/ /g, "\u00a0"); // an amount never breaks between number and unit ("9,5 M t")
  // A community's cells: those of its provinces (zone.provinces, the world's state fips).
  const fips = (app.w.raw.states || []).map((st) => st.fips);
  const zoneOfProvince = new Map((trade?.zones || []).flatMap((z) => (z.provinces || []).map((p) => [p, z.id])));
  const provinceCells = (z) => {
    const want = new Set(z.provinces || []), cells = new Set(), own = app.w.raw.owner;
    for (let i = 0; i < own.length; i++) if (own[i] >= 0 && want.has(fips[own[i]])) cells.add(i);
    return cells;
  };

  // --- headline -------------------------------------------------------------------------------------------------
  const nm = trade?.national_musd || {}, nk = trade?.national_k || {};
  const topPort = infra?.ports?.[0], topAir = infra?.airports?.[0];
  const headline = tons
    ? { label: t("adv.com.interregional"), value: fmt(nk.interregional), sub: t("adv.com.byTons", { vintage: esc(trade.vintage || "") }) }
    : { label: t("adv.com.freight"), value: fin(nm.domestic) ? money(nm.domestic * MUSD) : "–", sub: t("adv.com.byValue", { vintage: esc(trade?.vintage || "FAF") }) };
  const callout = tons
    ? t("adv.com.callout.es", { intra: fmt(nk.intra), sent: fmt(nk.intl_sent), received: fmt(nk.intl_received) })
    : `Freight values are model estimates from the Freight Analysis Framework, in current dollars: what moves between places, not what each place produces. Imports ${money(nm.import * MUSD)} and exports ${money(nm.export * MUSD)} are counted separately.`;
  el.insertAdjacentHTML("beforeend", tiles([
    // A headline only for what this map has (the US map has all three).
    ...(trade ? [headline] : []),
    ...(topPort ? [{ label: t("adv.com.busiestPort"), value: t("adv.tons", { v: count3(shownTons(topPort.tons)) }), sub: topPort.name }] : []),
    ...(topAir ? [{ label: t("adv.com.busiestAirport"), value: count3(topAir.enplanements), sub: t("adv.com.boardings", { id: topAir.id, year: topAir.year }) }] : []),
  ]) + (trade ? `<p class="adv-callout">${callout}</p>` : ""));

  // --- trade routes ---------------------------------------------------------------------------------------------
  let routes = [], zoneById = new Map(), routeCells = new Map(), overlayOff = null;
  const st = { mode: null, zone: null, route: null };
  let routeBars = null, zTable = null;
  const rDetail = mk("div", "adv-detail");
  if (trade) {
    zoneById = new Map((trade.zones || []).map((z) => [z.id, z]));
    const modeName = new Map((trade.modes || []).map((m) => [m.id, m.name]));
    const comm = trade.commodities || {};
    const zName = (id) => zoneById.get(id)?.short || zoneById.get(id)?.name || id;
    // A route's line: its path's cells (the US), or the straight segment between its zones' anchors (Spain).
    const anchorPt = (id) => { const a = zoneById.get(id)?.anchor; return a && a.cell >= 0 && a.cell < grid.size ? [grid.cx(a.cell), grid.cy(a.cell)] : null; };
    routes = (trade.routes || []).map((r) => {
      const pts = Array.isArray(r.path) ? r.path.filter((c) => c >= 0 && c < grid.size).map((c) => [grid.cx(c), grid.cy(c)])
        : [anchorPt(r.a), anchorPt(r.b)].filter(Boolean);
      return { ...r, key: `${r.a}-${r.b}`, label: `${zName(r.a)} ⇄ ${zName(r.b)}`, pts, path2d: smoothPath(pts) };
    });
    routes.forEach((r) => { for (const c of r.path || segmentCells(r.pts, grid)) { if (!routeCells.has(c)) routeCells.set(c, []); routeCells.get(c).push(r); } });
    for (const list of routeCells.values()) list.sort((a, b) => size(b) - size(a));
    const vMax = Math.max(1, ...routes.map(size));

    const rBody = section(el, { title: t("adv.com.routes"), kicker: esc(trade.vintage || ""), note: `${esc(trade.rule || "")}` });
    // Mode mix of the routes, value-weighted (a file with one mode, Spain's road survey, has no mix to show).
    const modeTot = {};
    for (const r of routes) for (const [m, s] of Object.entries(r.modes || {})) modeTot[m] = (modeTot[m] || 0) + (s || 0) * size(r);
    const oneMode = (trade.modes || []).length === 1;
    const modeParts = (trade.modes || []).map((m) => ({ key: m.id, label: m.name, value: modeTot[m.id] || 0, color: MODE_COLOR[m.id] || "#999", text: money((modeTot[m.id] || 0) * MUSD) })).filter((p) => p.value > 0);
    if (!oneMode) rBody.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">How the ${routes.length} routes' freight moves (by value)</h4>`);
    const modeBar = oneMode ? { setSelected() {} } : shareBar(rBody, {
      parts: modeParts,
      onHover: (p) => { api.modeHot = p ? p.key : null; redraw(); },
      onClick: (p) => setMode(st.mode === p.key ? null : p.key),
    });
    const fRow = mk("div", "adv-row adv-filterbar");
    rBody.appendChild(fRow);
    fRow.addEventListener("click", (e) => {
      if (e.target.closest("[data-clear-mode]")) setMode(null);
      if (e.target.closest("[data-clear-zone]")) setZone(null);
    });
    const rHost = mk("div");
    rBody.appendChild(rHost);
    rBody.appendChild(rDetail);
    rBody.insertAdjacentHTML("beforeend", oneMode ? `<p class="adv-note">${esc(trade.path_note || "")} ${t("adv.com.widthTons")}</p>`
      : `<p class="adv-note">${esc(trade.path_note || "")} Line width follows value; colour, the main mode (pipeline dashed).</p>${swatchLegend((trade.modes || []).filter((m) => modeTot[m.id] > 0).map((m) => ({ label: m.name, color: MODE_COLOR[m.id] })))}`);

    const routeHighlight = (r) => {
      const za = zoneById.get(r.a), zb = zoneById.get(r.b);
      const cells = new Set();
      const cities = new Set();
      for (const z of [za, zb]) {
        if (z?.anchor?.city) cities.add(z.anchor.city);
        for (const id of z?.cities || []) for (const c of metros.byKey.get(id)?.ref.footprint || []) cells.add(c);
        if (z?.provinces) for (const c of provinceCells(z)) cells.add(c);
      }
      return { cells, cities, label: r.label };
    };
    const visibleRoutes = () => routes.filter((r) => (!st.mode || r.top_mode === st.mode) && (!st.zone || r.a === st.zone || r.b === st.zone));
    const drawRoutes = () => {
      const vis = visibleRoutes();
      rHost.innerHTML = "";
      routeBars = barList(rHost, {
        rank: !st.mode && !st.zone, wrap: tons, ariaLabel: t("adv.com.routesAria"), max: vMax,
        rows: vis.map((r) => ({
          key: r.key, label: r.label, value: size(r), text: fmt(size(r)), color: MODE_COLOR[r.top_mode],
          sub: tons ? t("adv.com.dirs", { a: zName(r.a), b: zName(r.b), ab: nb(fmt(r.ab_k)), ba: nb(fmt(r.ba_k)) }) // barList escapes it
            : `${modeName.get(r.top_mode) || r.top_mode} · ${comm[r.top_commodity] || "–"}`,
          full: `#${r.rank} ${zoneById.get(r.a)?.name || r.a} ⇄ ${zoneById.get(r.b)?.name || r.b}`,
        })),
        selected: st.route?.key,
        onHover: (row) => {
          const r = row ? routes.find((x) => x.key === row.key) : null;
          setHotRoute(r);
          link.hover(r ? routeHighlight(r) : null);
        },
        onClick: (row) => selectRoute(routes.find((x) => x.key === row.key)),
      });
      fRow.innerHTML = (st.mode ? `<span class="adv-fchip">Mode: <b>${esc(modeName.get(st.mode) || st.mode)}</b><button type="button" data-clear-mode aria-label="Clear the mode filter">✕</button></span>` : "")
        + (st.zone ? `<span class="adv-fchip">${t("adv.com.zoneFilter", { name: esc(zName(st.zone)), n: vis.length })}<button type="button" data-clear-zone aria-label="${t("adv.com.clearZone")}">✕</button></span>` : "");
      if (!vis.length) rHost.innerHTML = tons ? `<p class="adv-empty">${t("adv.com.noRoutes", { n: routes.length })}</p>`
        : `<p class="adv-empty">None of the ${routes.length} largest routes${st.zone ? " touches this zone" : ""}${st.mode ? " goes mainly by this mode" : ""}.</p>`;
      modeBar.setSelected(st.mode);
      redraw();
    };
    function setMode(m) { st.mode = m; drawRoutes(); }
    function setZone(id) {
      st.zone = id;
      drawRoutes();
      zTable?.setSelected(id ? new Set([id]) : null);
      const z = id ? zoneById.get(id) : null;
      if (z) {
        const h = zoneHighlight(z);
        link.base({ ...h, dimOthers: true }, { frame: true });
      } else link.base(null);
      drawZoneDetail();
    }
    function selectRoute(r) {
      st.route = st.route === r ? null : r;
      routeBars?.setSelected(st.route?.key ?? null);
      drawRouteDetail();
      redraw();
      if (st.route) frameRoute(st.route);
    }
    function frameRoute(r) {
      if (!r.pts.length) return;
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (const [x, y] of r.pts) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); }
      const R = grid.R * 3;
      frameBox(app, { x0: x0 - R, y0: y0 - R, x1: x1 + R, y1: y1 + R }, { pad: 40, maxScale: 2.6 });
    }
    function drawRouteDetail() {
      const r = st.route;
      if (!r) { rDetail.innerHTML = ""; return; }
      const parts = Object.entries(r.modes || {}).filter(([, s]) => s > 0).sort((a, b) => b[1] - a[1]);
      const head = `<h4 class="adv-h4">#${r.rank} ${esc(zoneById.get(r.a)?.name || r.a)} ⇄ ${esc(zoneById.get(r.b)?.name || r.b)}</h4>`;
      const close = `<button type="button" class="adv-mini" data-unpin>${t("adv.com.closeRoute")}</button>`;
      rDetail.innerHTML = tons ? `<div class="adv-card-detail">${head}
        ${tiles([
          { label: t("adv.com.route.tons"), value: fmt(r.tons_k), sub: t("adv.com.route.both") },
          // a long "A → B" label would be cut in a tile: the destination goes in the label, the origin below
          { label: t("adv.com.route.to", { b: zName(r.b) }), value: fmt(r.ab_k), sub: t("adv.com.route.from", { a: zName(r.a) }) },
          { label: t("adv.com.route.to", { b: zName(r.a) }), value: fmt(r.ba_k), sub: t("adv.com.route.from", { a: zName(r.b) }) },
          { label: t("adv.com.route.haul"), value: fin(r.haul_km) ? `${int(r.haul_km)} km` : "–", sub: t("adv.com.route.haulSub") },
        ])}
        ${close}</div>` : `<div class="adv-card-detail">
        ${head}
        ${tiles([
          { label: "Value", value: money(r.value_musd * MUSD), sub: "both directions" },
          { label: "Weight", value: `${count3(r.tons_k * 1000)} t`, sub: "short tons" },
          { label: "Distance", value: `${int(r.dist_km)} km`, sub: `${count3(r.tmiles_m * 1e6)} ton-miles` },
        ])}
        <p class="adv-note"><b>By mode:</b> ${parts.map(([m, s]) => `${esc(modeName.get(m) || m)} ${pct(s)}`).join(" · ")}. <b>Largest commodity:</b> ${esc(comm[r.top_commodity] || "–")} (among each zone pair's top five).</p>
        ${close}</div>`;
      rDetail.querySelector("[data-unpin]").addEventListener("click", () => selectRoute(st.route));
    }

    // Zones table: FAF zones (the US) or autonomous communities (Spain).
    const zoneHighlight = (z) => {
      const cells = z.provinces ? provinceCells(z) : new Set();
      for (const id of z.cities || []) for (const c of metros.byKey.get(id)?.ref.footprint || []) cells.add(c);
      if (!cells.size && z.anchor?.cell != null) cells.add(z.anchor.cell);
      return { cells, cities: z.anchor?.city ? new Set([z.anchor.city]) : undefined, label: z.name };
    };
    const zones = (trade.zones || []).map((z) => ({ ...z, key: z.id }));
    const zBody = section(el, tons ? { title: t("adv.com.zones"), note: t("adv.com.zones.note") } : {
      title: "Freight zones",
      note: "FAF splits the country into metro areas and the rest of each state. Value of freight that starts or ends in each zone (domestic), plus its trade with other countries. Hover to outline a zone's cities; click to see its routes and partners.",
    });
    const tk = (z, k) => z.totals_k?.[k];
    const tkCol = (key, k, extra = {}) => ({ key, value: (z) => tk(z, k), text: (z) => fmt(tk(z, k)), ...extra });
    const intl = (z) => (fin(tk(z, "intl_sent")) || fin(tk(z, "intl_received")) ? (tk(z, "intl_sent") || 0) + (tk(z, "intl_received") || 0) : null);
    zTable = createTable(zBody, tons ? {
      caption: t("adv.com.zones"), rank: true, maxHeight: 320, search: t("adv.com.zoneSearch"),
      searchText: (z) => z.name,
      columns: [
        // 124px keeps "Castilla-La Mancha" whole
        { key: "name", label: t("adv.com.col.zone"), align: "l", width: "minmax(124px,2fr)", value: (z) => z.short || z.name, html: (z) => esc(z.short || z.name), tip: (z) => z.name },
        tkCol("within", "within", { label: t("adv.com.col.within"), title: t("adv.com.col.withinTitle") }),
        // one-word headers that fit the 56px column with the sort arrow; the full wording is the button's title
        tkCol("sent", "sent", { label: t("adv.com.col.sent"), title: t("adv.com.col.sentTitle"), bar: { max: Math.max(...zones.map((z) => tk(z, "sent") || 0), 1), color: "rgba(217,164,87,.35)" } }),
        tkCol("received", "received", { label: t("adv.com.col.received"), title: t("adv.com.col.receivedTitle") }),
        // dropped on a phone; the community's card gives the same figures
        { key: "intl", label: t("adv.com.col.intl"), title: t("adv.com.col.intlTitle"), value: intl, text: (z) => fmt(intl(z)), hideBelow: 380 },
      ],
      rows: zones, sort: { key: "sent", dir: "desc" },
      onHover: (z) => link.hover(z ? zoneHighlight(z) : null),
      onClick: (z) => setZone(st.zone === z.id ? null : z.id),
    } : {
      caption: "FAF freight zones", rank: true, maxHeight: 260, search: "Search zones",
      searchText: (z) => `${z.name} ${(z.states || []).join(" ")}`,
      columns: [
        { key: "name", label: "Zone", align: "l", width: "minmax(0,1.9fr)", value: (z) => z.short || z.name, html: (z) => `${esc(z.short || z.name)} <span class="sub">${esc((z.states || []).join("–"))}</span>`, tip: (z) => z.name },
        { key: "within", label: "Within", value: (z) => z.totals_musd?.within, text: (z) => money((z.totals_musd?.within ?? NaN) * MUSD), title: "Freight that starts and ends inside the zone" },
        { key: "other", label: "To & from zones", short: "To & from other zones", value: (z) => z.totals_musd?.other_zones, text: (z) => money((z.totals_musd?.other_zones ?? NaN) * MUSD), bar: { max: Math.max(...zones.map((z) => z.totals_musd?.other_zones || 0), 1), color: "rgba(47,164,184,.3)" } },
        { key: "foreign", label: "Imports + exports", short: "Foreign trade", value: (z) => (z.totals_musd ? (z.totals_musd.import || 0) + (z.totals_musd.export || 0) : null), text: (z) => (z.totals_musd ? money(((z.totals_musd.import || 0) + (z.totals_musd.export || 0)) * MUSD) : "–"), hideBelow: 380 },
      ],
      rows: zones, sort: { key: "other", dir: "desc" },
      onHover: (z) => link.hover(z ? zoneHighlight(z) : null),
      onClick: (z) => setZone(st.zone === z.id ? null : z.id),
    });
    const zDetail = mk("div", "adv-detail");
    zBody.appendChild(zDetail);
    const partnerBars = (host, z, sub) => barList(host, {
      compact: true, ariaLabel: tons ? t("adv.com.partners") : "Top partner zones",
      rows: (z.partners || []).map(([id, v, m]) => ({ key: id, label: zoneById.get(id)?.name || `Zone ${id} (off the map)`, value: v, text: fmt(v), sub: sub(m), color: MODE_COLOR[m] })),
      onHover: (row) => { const pz = row ? zoneById.get(row.key) : null; link.hover(pz ? zoneHighlight(pz) : null); },
      onClick: (row) => { if (zoneById.has(row.key)) setZone(row.key); },
    });
    function drawZoneDetail() {
      const z = st.zone ? zoneById.get(st.zone) : null;
      if (!z) { zDetail.innerHTML = ""; return; }
      if (tons) { drawCommunityDetail(z); return; }
      zDetail.innerHTML = `<div class="adv-card-detail"><h4 class="adv-h4">${esc(z.name)}</h4>
        <p class="adv-note">${z.kind === "rest_of_state" ? "The rest of the state outside its FAF metro zones. " : ""}${int(z.counties)} counties on the map · cities: ${(z.cities || []).slice(0, 6).map((id) => esc(metros.byKey.get(id)?.name || id)).join(", ") || "none on the map"}${(z.cities || []).length > 6 ? "…" : ""}</p>
        <h4 class="adv-h4">Top partners (any state)</h4><div class="adv-zp"></div></div>`;
      partnerBars(zDetail.querySelector(".adv-zp"), z, (m) => modeName.get(m) || m);
    }
    // A community: its provinces, partners, goods classes sent and received (table 7.5) and its balance.
    function drawCommunityDetail(z) {
      const names = new Map((app.w.raw.states || []).map((st) => [st.fips, st.name]));
      const provs = (z.provinces || []).map((p) => esc(names.get(p) || p)).join(", ");
      const goods = (kind) => (z.goods_k?.[kind] || []).map((v, k) => [k, v]).filter(([, v]) => fin(v)).sort((a, b) => b[1] - a[1]).slice(0, 3)
        .map(([k, v]) => `${esc(comm[k] || k)} ${fmt(v)}`).join(" · ") || "–";
      const sent = tk(z, "sent"), rec = tk(z, "received");
      const balance = fin(sent) && fin(rec) ? `${sent - rec >= 0 ? "+" : "−"}${fmt(Math.abs(sent - rec))}` : "–";
      zDetail.innerHTML = `<div class="adv-card-detail"><h4 class="adv-h4">${esc(z.name)}</h4>
        <p class="adv-note">${t("adv.com.provinces", { list: provs })}${z.significant ? "" : ` ${t("adv.com.notSignificant")}`}</p>
        ${z.significant ? `<h4 class="adv-h4">${t("adv.com.partners")}</h4><div class="adv-zp"></div>
        <p class="adv-note"><b>${t("adv.com.goodsSent")}</b> ${goods("sent")}<br><b>${t("adv.com.goodsReceived")}</b> ${goods("received")}</p>` : ""}
        <p class="adv-note">${t("adv.com.balance", { v: balance })}<br>${t("adv.com.abroad", { sent: fmt(tk(z, "intl_sent")), received: fmt(tk(z, "intl_received")) })}</p></div>`;
      if (z.significant) partnerBars(zDetail.querySelector(".adv-zp"), z, () => "");
    }

    // The routes overlay: all visible routes (unless the map-art layer already draws them), the hovered one on top.
    const tradeLayerOn = () => {
      try { return (app.staticLayers?.() || []).some((l) => /trade/i.test(l.id) && (typeof l.visible !== "function" || l.visible())); } catch { return false; }
    };
    const overlay = {
      id: "adv-commerce-routes", z: 18, space: "world",
      draw(ctx2, cam) {
        const s = cam.scale;
        ctx2.save();
        ctx2.lineCap = "round";
        ctx2.lineJoin = "round";
        const vis = visibleRoutes();
        const hot = api.hotRoute || st.route;
        if (!tradeLayerOn()) {
          for (const r of vis) {
            if (r === hot) continue;
            const wpx = 1.2 + 4.5 * Math.sqrt(size(r) / vMax);
            const faded = api.modeHot && r.top_mode !== api.modeHot;
            ctx2.setLineDash(r.top_mode === "pipeline" ? [6 / s, 4 / s] : []);
            ctx2.strokeStyle = "rgba(10,8,4,.55)";
            ctx2.lineWidth = (wpx + 2) / s;
            if (!faded) ctx2.stroke(r.path2d);
            ctx2.strokeStyle = withAlpha(MODE_COLOR[r.top_mode] || "#999", faded ? 0.18 : 0.85);
            ctx2.lineWidth = wpx / s;
            ctx2.stroke(r.path2d);
          }
        }
        if (hot) {
          ctx2.setLineDash([]);
          const wpx = 2.5 + 5 * Math.sqrt(size(hot) / vMax);
          ctx2.strokeStyle = "rgba(10,8,4,.9)";
          ctx2.lineWidth = (wpx + 4) / s;
          ctx2.stroke(hot.path2d);
          ctx2.strokeStyle = "#ffd36a";
          ctx2.lineWidth = wpx / s;
          ctx2.stroke(hot.path2d);
          for (const p of [hot.pts[0], hot.pts[hot.pts.length - 1]]) {
            if (!p) continue;
            ctx2.beginPath();
            ctx2.arc(p[0], p[1], 5 / s, 0, Math.PI * 2);
            ctx2.fillStyle = "#fff3c4";
            ctx2.fill();
            ctx2.strokeStyle = "rgba(10,8,4,.9)";
            ctx2.lineWidth = 1.5 / s;
            ctx2.stroke();
          }
        }
        ctx2.restore();
      },
    };
    overlayOff = app.registerOverlay(overlay);
    ctx.cleanup(() => overlayOff?.());
    function setHotRoute(r) {
      if (api.hotRoute === r) return;
      api.hotRoute = r || null;
      redraw();
    }
    api.setHotRoute = setHotRoute;
    api.selectRoute = selectRoute;
    api.drawRoutes = drawRoutes;
    drawRoutes();
  }
  function redraw() { app.requestDraw(); }

  // --- ports and airports -----------------------------------------------------------------------------------------
  let portBars = null, airBars = null, portBubbles = null, airBubbles = null;
  if (infra) {
    const v = infra.vintage || {};
    // Weights in the country's units (format.js shownTons, shownWeight); the bars split a port's tonnage only where
    // the data does (the US ports; Spain's have a total only).
    const ports = (infra.ports || []).map((p) => ({ ...p, key: `p${p.id}`, tons: shownTons(p.tons), domestic: shownTons(p.domestic), imports: shownTons(p.imports), exports: shownTons(p.exports) }));
    const split = ports.some((p) => p.domestic != null || p.imports != null || p.exports != null);
    const pBody = section(el, { title: t("adv.com.ports"), kicker: esc(v.ports || ""), note: split ? t("adv.com.portsNote", { rule: esc(infra.rules?.ports || "") }) : esc(infra.rules?.ports || "") });
    const PK = [{ key: "domestic", label: t("adv.com.domestic"), color: "#8fcbb8" }, { key: "imports", label: t("adv.com.imports"), color: "#4f9ad6" }, { key: "exports", label: t("adv.com.exports"), color: "#d9a457" }];
    const portHover = (p) => {
      link.hover(p ? { cells: new Set(p.cell != null ? [p.cell] : []), label: p.name } : null);
      portBubbles?.setHot(p ? p.key : null);
    };
    portBars = stackedBars(pBody, {
      wrap: country().id !== "us", // Spain's port names are long ("Bahía de Algeciras"); the US list stays as it was
      rows: ports.slice(0, 15).map((p) => ({ key: p.key, label: p.name, sub: p.state, parts: { domestic: p.domestic, imports: p.imports, exports: p.exports }, total: p.tons, text: t("adv.tons", { v: count3(p.tons) }) })),
      keys: PK, fmt: (x) => t("adv.tons", { v: count3(x) }), ariaLabel: t("adv.com.portsAria"),
      onHover: (x) => portHover(x ? ports.find((p) => p.key === x.row.key) : null),
      onClick: (x) => flyTo(ports.find((p) => p.key === x.row.key)),
    });
    if (ports.length) pBody.insertAdjacentHTML("beforeend", (split ? swatchLegend(PK) : "") + `<p class="adv-note">${t("adv.com.top15", { n: int(ports.length) })}</p>`);

    const aBody = section(el, { title: t("adv.com.airports"), kicker: esc(v.airports || ""), note: esc(infra.rules?.airports || "") });
    const airports = (infra.airports || []).map((a) => ({ ...a, key: `a${a.id}`, cargo: shownWeight(a.cargo_lbs) }));
    let aMode = "pax";
    const aHost = mk("div");
    segmented(aBody, { label: t("adv.rankBy"), value: aMode, options: [{ value: "pax", label: t("adv.com.passengers") }, { value: "cargo", label: t("adv.com.cargo") }], onChange: (x) => { aMode = x; drawAir(); } });
    aBody.appendChild(aHost);
    const airHover = (a) => {
      link.hover(a ? { cells: new Set(a.cell != null ? [a.cell] : []), label: `${a.id} · ${a.name}` } : null);
      airBubbles?.setHot(a ? a.key : null);
    };
    function drawAir() {
      aHost.innerHTML = "";
      const k = aMode === "pax" ? "enplanements" : "cargo";
      const list = airports.filter((a) => fin(a[k])).sort((a, b) => b[k] - a[k]).slice(0, 15);
      airBars = barList(aHost, {
        rank: true, ariaLabel: aMode === "pax" ? t("adv.com.airAriaPax") : t("adv.com.airAriaCargo"),
        rows: list.map((a) => {
          const ch = aMode === "pax" && fin(a.enplanements_prev) && a.enplanements_prev > 0 ? a.enplanements / a.enplanements_prev - 1 : null;
          return {
            key: a.key, label: `${a.id} ${a.city || a.name}`, full: a.name, value: a[k],
            text: aMode === "pax" ? count3(a[k]) : t("adv.com.weight", { v: count3(a[k]) }),
            sub: aMode === "pax" ? (fin(ch) ? t("adv.com.onYear", { change: signedPct(ch), year: a.year - 1 }) : "") : `${a.state}`,
            tone: fin(ch) ? (ch >= 0 ? "good" : "bad") : undefined, color: AIR_COLOR,
          };
        }),
        onHover: (r) => airHover(r ? airports.find((a) => a.key === r.key) : null),
        onClick: (r) => flyTo(airports.find((a) => a.key === r.key)),
      });
      if (airports.length) aHost.insertAdjacentHTML("beforeend", `<p class="adv-note">${aMode === "pax" ? t("adv.com.paxNote") : t("adv.com.cargoNote")}</p>`);
    }
    drawAir();

    // On the map: circles for ports (tons) and airports (boardings or cargo).
    const mBody = section(el, { title: t("adv.com.onMap") });
    let show = "both";
    segmented(mBody, {
      label: t("adv.com.show"), value: show,
      options: [{ value: "both", label: t("adv.com.both") }, { value: "ports", label: t("adv.com.ports") }, { value: "air", label: t("adv.com.airports") }, { value: "none", label: t("adv.com.routesOnly") }],
      onChange: (x) => { show = x; drawSites(); },
    });
    const sizeBox = mk("div");
    mBody.appendChild(sizeBox);
    portBubbles = ctx.bubbles("ports", {
      rMax: 20, alpha: 0.5,
      tip: (b) => `<b>${esc(b.it.name)}</b><br>${t("adv.com.portTip", { tons: t("adv.tons", { v: count3(b.it.tons) }), year: b.it.year, rank: b.it.rank })}${split ? t("adv.com.portSplitTip", { domestic: count3(b.it.domestic), imports: count3(b.it.imports), exports: count3(b.it.exports) }) : ""}`,
      onHover: (b) => portBars?.setHot(b ? b.key : null),
      onClick: (b) => { portBars?.setHot(b.key); flyTo(b.it); },
    });
    airBubbles = ctx.bubbles("airports", {
      rMax: 16, alpha: 0.5,
      tip: (b) => `<b>${esc(b.it.id)} · ${esc(b.it.name)}</b><br>${t("adv.com.airTip", { hub: esc(infra.hubs?.[b.it.hub] || t("adv.com.cargoAirport")), n: count3(b.it.enplanements) })}${fin(b.it.cargo) ? `<br><span class="sub">${t("adv.com.airCargoTip", { v: count3(b.it.cargo) })}</span>` : ""}`,
      onHover: (b) => airBars?.setHot(b ? b.key : null),
      onClick: (b) => { airBars?.setHot(b.key); flyTo(b.it); },
    });
    function drawSites() {
      const pMax = Math.max(1, ...ports.map((p) => p.tons || 0)), aMax = Math.max(1, ...airports.map((a) => a.enplanements || 0));
      portBubbles.set(show === "both" || show === "ports" ? ports.filter((p) => fin(p.tons)).map((p) => ({ key: p.key, x: p.x, y: p.y, value: p.tons, color: PORT_COLOR, it: p })) : [], { vMax: pMax });
      airBubbles.set(show === "both" || show === "air" ? airports.filter((a) => fin(a.enplanements) && a.hub && a.hub !== "N").map((a) => ({ key: a.key, x: a.x, y: a.y, value: a.enplanements, color: AIR_COLOR, it: a })) : [], { vMax: aMax });
      sizeBox.innerHTML = (show === "both" || show === "ports" ? sizeLegend([10e6, 100e6], (x) => 20 * Math.sqrt(x / pMax), (x) => t("adv.tons", { v: count3(x) }), t("adv.com.portsLegend")) : "")
        + (show === "both" || show === "air" ? sizeLegend([1e6, 20e6], (x) => 16 * Math.sqrt(x / aMax), (x) => count3(x), t("adv.com.airLegend")) : "");
    }
    drawSites();

    // Roads and rail: the counts and rules (the map-art layers draw them; switches live in the Map menu).
    const nBody = section(el, { title: t("adv.com.roadsRails"), open: false });
    const nRoad = [0, 0], nRail = [0, 0];
    for (const r of infra.roads || []) nRoad[r[2]] = (nRoad[r[2]] || 0) + 1;
    for (const r of infra.rail || []) nRail[r[2]] = (nRail[r[2]] || 0) + 1;
    const toggles = (() => { try { return app.ui.mapToggles?.() || []; } catch { return []; } })();
    nBody.innerHTML = `<p class="adv-note">${(infra.road_classes || []).map((c, i) => t("adv.com.links", { name: esc(c.name), n: int(nRoad[i] || 0) })).join(" · ")}<br>${(infra.rail_tiers || []).map((c, i) => t("adv.com.links", { name: esc(c.name), n: int(nRail[i] || 0) })).join(" · ")}</p>
      <p class="adv-note">${esc(infra.rules?.roads || "")}</p><p class="adv-note">${esc(infra.rules?.rail || "")}</p>
      ${toggles.length ? `<p class="adv-note">${t("adv.com.toggles")}</p>` : ""}`;
  }
  function flyTo(p) {
    if (!p) return;
    focusPoint(app, p.x, p.y, Math.min(app.cam.maxScale, Math.max(app.cam.scale, (app.cam.fitScale || 1) * 3)));
  }

  el.insertAdjacentHTML("beforeend", sourcesHtml(data, [...(trade?.sources || []), ...(infra?.sources || [])], [
    // Each caveat only where its data is on this map (the US map has them all).
    ...(trade?.sources?.includes("faf5") ? [t("adv.com.c.faf1"), t("adv.com.c.faf2"), t("adv.com.c.faf3")] : []),
    ...(trade?.sources?.includes("eptmc") ? [t("adv.com.c.eptmc1"), t("adv.com.c.eptmc2"), t("adv.com.c.eptmc3"),
      t("adv.com.c.eptmc4", { vintage: esc(trade.vintage || ""), updated: esc(isoDay(trade.updated)) })] : []),
    ...(infra?.ports?.length || infra?.airports?.length ? [t("adv.com.c.ports")] : []),
    t("adv.com.c.ne"),
  ]));

  return {
    onMapHover(h) {
      if (!routes.length) return;
      const list = h.cell >= 0 ? (routeCells.get(h.cell) || []).filter((r) => (!st.mode || r.top_mode === st.mode) && (!st.zone || r.a === st.zone || r.b === st.zone)) : [];
      const fromLayer = h.item?.kind === "route" ? routes.find((x) => x.a === h.item.data?.route?.a && x.b === h.item.data?.route?.b) : null;
      const r = fromLayer || list[0] || null;
      if (h.item?.kind === "port") portBars?.setHot(`p${h.item.data?.id}`);
      if (h.item?.kind === "airport") airBars?.setHot(`a${h.item.data?.id}`);
      routeBars?.setHot(r ? r.key : null);
      // Only light the route up from the map when no circle is under the pointer (those have their own hover).
      api.setHotRoute?.(r);
      const z = h.cell >= 0 ? zoneOfCell(h.cell) : null;
      zTable?.setHot(z, false);
    },
    onMapClick(ev) {
      if (ev.item?.kind === "port" || ev.item?.kind === "airport") { flyTo(ev.item.data); return true; }
      const list = ev.item?.kind === "route" ? routes.filter((x) => x.a === ev.item.data?.route?.a && x.b === ev.item.data?.route?.b) : ev.cell >= 0 ? routeCells.get(ev.cell) || [] : [];
      const r = list.find((x) => (!st.mode || x.top_mode === st.mode) && (!st.zone || x.a === st.zone || x.b === st.zone));
      if (r && !ev.city) { api.selectRoute(r); return true; }
      return false;
    },
    onEscape() {
      if (st.route) { api.selectRoute(st.route); return true; }
      if (st.zone || st.mode) { st.zone = null; st.mode = null; link.base(null); api.drawRoutes?.(); zTable?.setSelected(null); return true; }
      return false;
    },
  };

  function zoneOfCell(cell) {
    if (tons) { const o = app.w.raw.owner[cell]; return o >= 0 ? zoneOfProvince.get(fips[o]) ?? null : null; }
    if (!zoneOfCity) { zoneOfCity = new Map(); for (const z of zoneById.values()) for (const id of z.cities || []) zoneOfCity.set(id, z.id); }
    const m = metros.rowAtCell(cell);
    return m ? zoneOfCity.get(m.key) ?? null : null;
  }
}

/** An ISO day ("2026-11-16") written out in the country's locale, or the text as it is when it is not one. */
function isoDay(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
  return m ? longDate(+m[1], +m[2], +m[3]) : iso || "";
}

/** The cells a straight segment [[x, y], [x, y]] crosses, sampled every half hex radius (routes without a path). */
function segmentCells(pts, grid) {
  if (pts.length !== 2) return [];
  const [[x0, y0], [x1, y1]] = pts, n = Math.max(1, Math.ceil(Math.hypot(x1 - x0, y1 - y0) / (grid.R / 2)));
  const out = new Set();
  for (let k = 0; k <= n; k++) {
    const c = grid.cellAt(x0 + ((x1 - x0) * k) / n, y0 + ((y1 - y0) * k) / n);
    if (c >= 0) out.add(c);
  }
  return [...out];
}

/** A smooth Path2D through hex-centre points (quadratic curves through the midpoints), in km. */
function smoothPath(pts) {
  const p = new Path2D();
  if (!pts.length) return p;
  p.moveTo(pts[0][0], pts[0][1]);
  if (pts.length === 2) { p.lineTo(pts[1][0], pts[1][1]); return p; }
  for (let i = 1; i < pts.length - 1; i++) {
    const mx = (pts[i][0] + pts[i + 1][0]) / 2, my = (pts[i][1] + pts[i + 1][1]) / 2;
    p.quadraticCurveTo(pts[i][0], pts[i][1], mx, my);
  }
  const l = pts[pts.length - 1];
  p.lineTo(l[0], l[1]);
  return p;
}
