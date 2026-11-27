// The climate of the month, "Clima del mes" / "Climate this month", on a map whose data has clima.json (Spain).
//
//   lenses clima_temp, clima_lluvia, clima_heladas, clima_sol in the lens picker (Territorio / Land): each land hex
//     coloured by the month's mean temperature, rain or frost days (AEMET's ROCIO grid, averaged over 1991-2020 by
//     spainciv) or, on the hexes of the WMO stations that measure it, sunshine; one scale for the twelve months, and
//     the tooltip says where each value comes from (season.js)
//   static layer "clima-sun" (sunshine lens only): a disc DISC_PX across on each station's hex at any zoom, in the
//     lens's colours, with the station's own tooltip (it wins over the sites under it)
//   mode "clima" (opens and closes with any of the four): the left dock with the month strip (bars: AEMET's normal for
//     peninsular Spain), the four variables, the colour key on phones (where the sheet covers the legend), the
//     Walter-Lieth diagram of the province under the pointer (a click or a tap pins it; walter.js) with its twelve
//     months, and the link to the fiestas of the same month
//   URL hash: #lens=clima_temp&mes=1; #lens=clima_lluvia alone opens this month (the month is ext/month.js)
// clima.json is loaded the first time the panel opens; until then the lenses have no domain and the legend shows only
// their name. A new month or variable repaints the lens once; nothing moves.
import { country } from "../../app/country.js";
import { lensPanel, panelHead, panelKey, updatePanelKey } from "../../app/lensPanel.js";
import { t } from "../../i18n.js";
import { css, parseHex, rampColor } from "../../color.js";
import { esc, fixed, int } from "../../format.js";
import { mapProjection } from "../../geo.js";
import { glyph } from "../../ui/icon.js";
import { formatLensValue } from "../../ui/lenses.js";
import { lensScale } from "../../world.js";
import { currentMonth, monthLinks, monthName as nameOf, monthState, monthStrip } from "../month.js";
import * as S from "./season.js";
import { walterSvg } from "./walter.js";

const MODE = "clima";
const GROUP = "land";
const ICON = { temp: "l-temperature", prec: "l-rain", frost: "l-frost", sun: "l-sunshine" };
const EMOJI = { temp: "🌡️", prec: "🌧️", frost: "❄️", sun: "☀️" };
const SOURCE = { temp: "aemet_rocio", prec: "aemet_rocio", frost: "aemet_rocio", sun: "omm_normales_es" };
const RULES = { temp: ["grid", "province"], prec: ["grid", "rain", "province"], frost: ["grid", "frost"], sun: ["sun", "station"] };
const TABLE = ["tmed", "tmax", "tmin", "prec"];
const SUN_Z = 88; // above the sites (65-67) and the resources (80), under the state names (90)
// A sunshine station's disc, in css px across: several hexes at the country view, a dot inside its own (coloured) hex
// close up, where a bigger disc would hide the names of the sites around it.
const DISC_PX = 14;

export function install(app) {
  if (!country().data?.includes("clima")) return;
  const { w } = app;
  const n = w.grid.size;
  const proj = mapProjection(app.data.world.country?.projection);
  const locale = () => country().locale;
  const monthName = (m) => nameOf(m, locale());
  const provinceOf = (i) => (i >= 0 && w.raw.owner[i] >= 0 ? w.raw.states[w.raw.owner[i]].fips : null);
  const provinceName = new Map(w.raw.states.map((s) => [s.fips, s.name]));
  const touch = () => !!app.isMobile?.();

  const lenses = new Map(S.VARIABLES.map((v) => [v, {
    id: S.LENS_ID[v], group: GROUP, name: t(`clima.lens.${v}`), icon: ICON[v], emoji: EMOJI[v], format: "float", decimals: 1,
    scale: S.SCALE[v], domain: null, higher_is: "neutral", unit: t(`clima.unit.${v}`), source: SOURCE[v],
    description: t(`clima.desc.${v}`), scale_text: t("clima.scale"), ramp: S.RAMPS[v], values: new Array(n).fill(null),
    heading: t("clima.loading"), click_hint: t("clima.tip.click"),
  }]));
  let after = app.data.lenses.lenses.filter((l) => l.group === GROUP).at(-1)?.id;
  for (const lens of lenses.values()) {
    app.addLens(lens, { after });
    after = lens.id;
  }
  const variableOf = (l) => S.VARIABLES.find((v) => lenses.get(v) === l) ?? null;
  const sunLens = lenses.get("sun");

  const ms = monthState(app);
  let variable = "temp";
  let model = null; // clima.json on this map, once loaded
  let built = false; // the dock holds the panel (build() ran since it opened), not the loading line
  let shown = null, pinned = null; // the province of the diagram, and whether a click fixed it
  let token = 0;

  // --- the lenses ------------------------------------------------------------------------------------------------
  // All four take the month at once (a few ms), so moving between them paints the map once; only the one on screen
  // is repainted now.
  function paint() {
    const m = ms.month;
    for (const [v, lens] of lenses) {
      const L = S.layer(model, v, m);
      const value = { temp: (x) => fixed(x, 1), int, lens: (x) => formatLensValue(lens, x) };
      Object.assign(lens, {
        values: L.values, domain: L.domain,
        tip: (i) => S.tipLines(L.facts(i), { say: t, value, frost: v === "frost", month: monthName(m) }),
        heading: t("clima.heading", { what: lens.name, month: monthName(m) }),
        note: t(v === "sun" ? "clima.note.station" : "clima.note.grid", { month: monthName(m) }),
        null_label: t(`clima.none.${v === "sun" || v === "frost" ? v : "any"}`),
      });
      if (app.state.lens === lens) app.refreshLens();
    }
  }

  const panel = lensPanel(app, [...lenses.values()], {
    mode: MODE, label: t("clima.mode"), pick: () => lenses.get(variable),
    open(dock) {
      built = false;
      dock.innerHTML = `<p class="muted">${esc(t("clima.loading"))}</p>`;
      load(++token);
    },
    close() {
      token++;
      built = false;
      pinned = shown = null;
    },
  });

  async function load(my) {
    const doc = await app.loadData("clima").catch(() => null);
    if (my !== token) return; // closed meanwhile
    const { dock } = panel;
    if (!doc?.cells || !proj) {
      dock.innerHTML = `<p class="muted">${esc(t("clima.loadError"))}</p>`;
      for (const lens of lenses.values()) lens.heading = t("clima.loadError");
      app.refreshLens();
      return;
    }
    model ??= S.climateModel(doc, { n, province: provinceOf, lonlat: (i) => proj.inverse(w.grid.cx(i), w.grid.cy(i)) });
    variable = variableOf(app.state.lens) ?? variable;
    build(dock);
    paint();
    update();
  }

  // Another of the four lenses (a tab, the lens picker, Back): the panel stays and shows it once it is built.
  app.on("lens", (l) => {
    const v = variableOf(l);
    if (!v || v === variable) return;
    variable = v;
    update();
  });

  ms.page({
    id: MODE, lensIds: [...lenses.values()].map((l) => l.id), active: () => app.mode === MODE, open: () => app.setMode(MODE),
    linkLabel: (m) => t("clima.link", { month: monthName(m) }),
    onMonth() {
      if (model && built) {
        paint();
        update();
      }
    },
  });

  // --- the sunshine stations -------------------------------------------------------------------------------------
  // 76 hexes among thousands: a disc of DISC_PX on each, in the lens's colour, so the lens reads at the country view
  // too. Drawn into the cached map (it changes with the lens and the month, which repaint it anyway).
  const sunStations = () => model.doc.stations.filter((s) => s.sun);
  const discKm = (Rpx) => (DISC_PX / 2) * (w.grid.R / Rpx);
  app.registerStaticLayer({
    id: "clima-sun", z: SUN_Z,
    visible: () => !!model && app.state.lens === sunLens && !!sunLens.domain,
    sig: () => String(ms.month),
    draw(ctx, vp, _w, o) {
      const scale = lensScale(sunLens), stops = sunLens.ramp.map(parseHex);
      const r = discKm(o.Rpx), px = w.grid.R / o.Rpx; // km per css px
      for (const s of sunStations()) {
        const x = w.grid.cx(s.cell), y = w.grid.cy(s.cell);
        if (x + r < vp.x0 || x - r > vp.x1 || y + r < vp.y0 || y - r > vp.y1) continue;
        ctx.beginPath();
        ctx.arc(x, y, r, 0, 2 * Math.PI);
        ctx.fillStyle = css(rampColor(stops, scale(s.sun[ms.month - 1])));
        ctx.fill();
        ctx.lineWidth = 2 * px;
        ctx.strokeStyle = "rgba(20,16,10,.85)";
        ctx.stroke();
        ctx.lineWidth = px;
        ctx.strokeStyle = "rgba(255,240,200,.9)";
        ctx.stroke();
      }
    },
    hit(x, y, Rpx) {
      const r = discKm(Rpx);
      let best = null, bd = r;
      for (const s of sunStations()) {
        const d = Math.hypot(w.grid.cx(s.cell) - x, w.grid.cy(s.cell) - y);
        if (d <= bd) [best, bd] = [s, d];
      }
      return best;
    },
    tooltip(s) {
      const m = ms.month;
      return `<b>${esc(t("clima.tip.stationName", { name: s.name }))}</b> <span class="muted">· ${int(s.alt)} m</span><br>`
        + `${esc(provinceName.get(s.province) || s.province)}<br>`
        + `${glyph(sunLens, 13)} ${esc(sunLens.heading)}: <b>${esc(formatLensValue(sunLens, s.sun[m - 1]))}</b><br>`
        + `<span class="muted">${esc(t("clima.tip.sunStation", { hours: int(S.annualSun(s)) }))}</span><br>`
        + `<span class="muted">${esc(t("clima.tip.click"))}</span>`;
    },
  });

  // --- the province's diagram ------------------------------------------------------------------------------------
  app.on("hover", (h) => {
    if (!built || !model || pinned) return;
    const code = provinceOf(h.cell);
    if (code && code !== shown) chart(code);
  });
  app.on("mapclick", (ev) => {
    if (app.mode !== MODE || !model || ev.city) return false;
    const code = provinceOf(ev.cell);
    if (!code) return false;
    pinned = code;
    chart(code);
    // On a phone the diagram is below the fold of the sheet: bring it up.
    if (touch()) panel.dock?.querySelector(".cl-chart")?.scrollIntoView?.({ block: "start", behavior: "smooth" });
    return true;
  });

  // --- the dock --------------------------------------------------------------------------------------------------
  // Built once when the data is in; a new month or variable only updates it.
  function build(dock) {
    const tabs = S.VARIABLES.map((v) => `<button type="button" class="cl-tab" role="tab" data-v="${v}">${esc(lenses.get(v).name)}</button>`).join("");
    dock.innerHTML = `
      ${panelHead("", t("clima.close"))}
      <div class="ms-strip" aria-label="${esc(t("clima.months"))}"></div>
      <div class="cl-tabs" role="tablist" aria-label="${esc(t("clima.variables"))}">${tabs}</div>
      ${panelKey()}
      <p class="cl-sum"></p>
      <p class="cl-rule muted"></p>
      <section class="cl-chart" aria-live="polite"></section>
      <div class="cl-links"></div>
      <p class="cl-credit muted">${esc(t("clima.credit"))}</p>`;
    built = true;
    dock.querySelector(".cl-tabs").onclick = (e) => {
      const b = e.target.closest("[data-v]");
      if (b) app.setLens(lenses.get(b.dataset.v));
    };
    dock.querySelector(".cl-tabs").onkeydown = (e) => {
      const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
      if (!step) return;
      e.preventDefault();
      const next = S.VARIABLES[(S.VARIABLES.indexOf(variable) + step + S.VARIABLES.length) % S.VARIABLES.length];
      app.setLens(lenses.get(next));
      dock.querySelector(`.cl-tab[data-v="${next}"]`)?.focus();
    };
    dock.querySelector(".cl-links").onclick = ms.follow;
    dock.querySelector(".cl-chart").onclick = (e) => {
      if (!e.target.closest("[data-unpin]")) return;
      pinned = null;
      chart(shown);
    };
    chart(shown);
  }

  // The summary under the tabs: AEMET's normal for peninsular Spain (temperature, rain), else the stations with the
  // most and the least of it (frost, sunshine).
  function summary(lens, month) {
    const doc = model.doc;
    const row = { temp: doc.peninsular.tmed, prec: doc.peninsular.prec }[variable];
    if (row) return t("clima.peninsular", { month: monthName(month), value: formatLensValue(lens, row[month - 1]) });
    const ex = S.stationExtremes(doc, variable, month);
    if (!ex) return t(`clima.extremes.${variable}.none`, { month: monthName(month) });
    return t(`clima.extremes.${variable}`, {
      month: monthName(month), top: ex.top.name, max: formatLensValue(lens, ex.top.value),
      bottom: ex.bottom.name, min: formatLensValue(lens, ex.bottom.value),
    });
  }

  function update() {
    const dock = panel.dock;
    if (!dock || !model || !built) return;
    const { month } = ms, doc = model.doc, lens = lenses.get(variable);
    dock.querySelector(".lens-panel-head h2").textContent = month === currentMonth() ? t("clima.title.now") : t("clima.title", { month: monthName(month) });
    const bars = S.stripBars(doc, variable);
    const row = { temp: doc.peninsular.tmed, prec: doc.peninsular.prec }[variable];
    monthStrip(dock.querySelector(".ms-strip"), {
      month, locale: locale(), bar: bars ? (m) => bars[m - 1] : undefined, onPick: (m) => ms.set(m),
      label: row ? (m) => t("clima.month.bar", { month: monthName(m), value: formatLensValue(lens, row[m - 1]) }) : undefined,
    });
    dock.querySelectorAll(".cl-tab").forEach((b) => {
      const on = b.dataset.v === variable;
      b.classList.toggle("on", on);
      b.setAttribute("aria-selected", String(on));
      b.tabIndex = on ? 0 : -1;
    });
    updatePanelKey(dock, lens, t("clima.key", { what: lens.heading }));
    dock.querySelector(".cl-sum").textContent = summary(lens, month);
    dock.querySelector(".cl-rule").textContent = RULES[variable].map((k) => doc.rules[k]).join(" ");
    dock.querySelector(".cl-links").innerHTML = monthLinks(ms, MODE);
  }

  function chart(code) {
    const host = built && panel.dock?.querySelector(".cl-chart");
    if (!host || !model) return;
    shown = code;
    const p = code && model.doc.provinces[code];
    const how = (k) => t(touch() ? `${k}.touch` : k);
    if (!p) {
      host.innerHTML = `<h3>${esc(t("clima.chart.title"))}</h3><p class="muted">${esc(how("clima.chart.hint"))}</p>`;
      return;
    }
    const period = model.doc.provinces_period;
    const short = Array.from({ length: 12 }, (_, k) => nameOf(k + 1, locale(), "narrow"));
    const svg = walterSvg({
      tmed: p.tmed, prec: p.prec, tmin: p.tmin, place: provinceName.get(code) || code, period,
      months: short, num: (v, d) => fixed(v, d), labels: { frost: t("clima.chart.frost") }, id: "cl-wl",
    });
    const rows = Array.from({ length: 12 }, (_, k) => `<tr><th scope="row">${esc(nameOf(k + 1, locale(), "short").replace(/\.$/, ""))}</th>${TABLE.map((v) => `<td>${esc(fixed(p[v][k], 1))}</td>`).join("")}</tr>`).join("");
    const head = TABLE.map((v) => `<th scope="col">${esc(t(`clima.table.${v}`))}</th>`).join("");
    host.innerHTML = `
      <h3>${esc(t("clima.chart.title"))}${pinned ? ` <button type="button" class="ms-link" data-unpin>${esc(t("clima.chart.unpin"))}</button>` : ""}</h3>
      <p class="muted cl-chart-how">${esc(how(pinned ? "clima.chart.pinned" : "clima.chart.hover"))}</p>
      ${svg}
      <p class="muted cl-cap">${esc(t("clima.chart.caption"))}</p>
      <table class="cl-table"><caption>${esc(t("clima.table.caption", { place: provinceName.get(code) || code, period }))}</caption>
        <thead><tr><th></th>${head}</tr></thead><tbody>${rows}</tbody></table>`;
  }
}
