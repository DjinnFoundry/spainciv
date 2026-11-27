// The climate of the month, "Clima del mes" / "Climate this month", on a map whose data has clima.json (Spain).
//
//   lenses clima_temp, clima_lluvia, clima_heladas, clima_sol in the lens picker (Territorio / Land): each land hex
//     coloured by the month's mean temperature, rain or frost days (AEMET's ROCIO grid, averaged over 1991-2020 by
//     spainciv) or, on the hexes of the WMO stations that measure it, sunshine; one scale for the twelve months, and
//     the tooltip says where each value comes from (season.js)
//   mode "clima" (opens and closes with any of the four): the left dock with the month strip (bars: AEMET's normal for
//     peninsular Spain), the four variables, the Walter-Lieth diagram of the province under the pointer (a click pins
//     it; walter.js) with its twelve months, and the link to the fiestas of the same month
//   URL hash: #lens=clima_temp&mes=1; #lens=clima_lluvia alone opens this month (the month is ext/month.js)
// clima.json is loaded the first time the panel opens. A new month or variable repaints the lens once; nothing moves.
import { country } from "../../app/country.js";
import { lensPanel, panelHead } from "../../app/lensPanel.js";
import { t } from "../../i18n.js";
import { esc, fixed, int } from "../../format.js";
import { mapProjection } from "../../geo.js";
import { formatLensValue } from "../../ui/lenses.js";
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

export function install(app) {
  if (!country().data?.includes("clima")) return;
  const { w } = app;
  const n = w.grid.size;
  const proj = mapProjection(app.data.world.country?.projection);
  const locale = () => country().locale;
  const monthName = (m) => nameOf(m, locale());
  const provinceOf = (i) => (i >= 0 && w.raw.owner[i] >= 0 ? w.raw.states[w.raw.owner[i]].fips : null);
  const provinceName = new Map(w.raw.states.map((s) => [s.fips, s.name]));

  const lenses = new Map(S.VARIABLES.map((v) => [v, {
    id: S.LENS_ID[v], group: GROUP, name: t(`clima.lens.${v}`), icon: ICON[v], emoji: EMOJI[v], format: "float",
    scale: S.SCALE[v], domain: [1, 2], higher_is: "neutral", unit: t(`clima.unit.${v}`), source: SOURCE[v],
    description: t(`clima.desc.${v}`), scale_text: t("clima.scale"), ramp: S.RAMPS[v], values: new Array(n).fill(null),
  }]));
  let after = app.data.lenses.lenses.filter((l) => l.group === GROUP).at(-1)?.id;
  for (const lens of lenses.values()) {
    app.addLens(lens, { after });
    after = lens.id;
  }
  const variableOf = (l) => S.VARIABLES.find((v) => lenses.get(v) === l) ?? null;

  const ms = monthState(app);
  let variable = "temp";
  let model = null; // clima.json on this map, once loaded
  let shown = null, pinned = null; // the province of the diagram, and whether a click fixed it
  let mark = null; // the outline of the stations with sunshine, while the sunshine lens is on
  let token = 0;

  // --- the lenses ------------------------------------------------------------------------------------------------
  // All four take the month at once (a few ms), so moving between them paints the map once; only the one on screen
  // is repainted now.
  function paint() {
    const m = ms.month;
    for (const [v, lens] of lenses) {
      const L = S.layer(model, v, m);
      Object.assign(lens, {
        values: L.values, domain: L.domain, tip: (i) => tipLines(lens, L.facts(i)),
        heading: t("clima.heading", { what: lens.name, month: monthName(m) }), note: t("clima.note", { month: monthName(m) }),
        null_label: t(`clima.none.${v === "sun" || v === "frost" ? v : "any"}`),
      });
      if (app.state.lens === lens) app.refreshLens();
    }
  }

  // What the tooltip adds under the value: where it comes from, and the stations on the hex.
  function tipLines(lens, f) {
    if (!f) return [];
    const lines = [];
    const from = f.source && t(`clima.tip.${f.source}`);
    if (f.max != null && f.min != null) lines.push([t("clima.tip.range", { max: fixed(f.max, 1), min: fixed(f.min, 1) }), from].join(" · "));
    else if (from) lines.push(from);
    for (const s of f.stations) {
      // The WMO counts frost days below 0 °C, the grid at 0 °C or less: the station's line says which it is.
      const key = s.value == null ? "clima.tip.station.none" : lens === lenses.get("frost") ? "clima.tip.station.frost" : "clima.tip.station";
      lines.push(t(key, { name: s.name, alt: int(s.alt), value: s.value == null ? "" : formatLensValue(lens, s.value) }));
    }
    if (f.nearest) lines.push(t("clima.tip.nearest", { name: f.nearest.name, hours: int(f.nearest.annual) }));
    return lines;
  }

  const panel = lensPanel(app, [...lenses.values()], {
    mode: MODE, label: t("clima.mode"), pick: () => lenses.get(variable),
    open(dock) {
      dock.innerHTML = `<p class="muted">${esc(t("clima.loading"))}</p>`;
      load(++token);
    },
    close() {
      token++;
      pinned = shown = null;
      outlineStations(false);
    },
  });

  async function load(my) {
    const doc = await app.loadData("clima").catch(() => null);
    if (my !== token) return; // closed meanwhile
    const { dock } = panel;
    if (!doc?.cells || !proj) {
      dock.innerHTML = `<p class="muted">${esc(t("clima.loadError"))}</p>`;
      return;
    }
    model ??= S.climateModel(doc, { n, province: provinceOf, lonlat: (i) => proj.inverse(w.grid.cx(i), w.grid.cy(i)) });
    variable = variableOf(app.state.lens) ?? variable;
    build(dock);
    paint();
    update();
  }

  // Another of the four lenses (a tab, the lens picker, Back): the panel stays and shows it.
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
      if (model && panel.dock) {
        paint();
        update();
      }
    },
  });

  // --- the province's diagram ------------------------------------------------------------------------------------
  app.on("hover", (h) => {
    if (!panel.dock || !model || pinned) return;
    const code = provinceOf(h.cell);
    if (code && code !== shown) chart(code);
  });
  app.on("mapclick", (ev) => {
    if (app.mode !== MODE || !model || ev.city) return false;
    const code = provinceOf(ev.cell);
    if (!code) return false;
    pinned = code;
    chart(code);
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
      <p class="cl-sum"></p>
      <p class="cl-rule muted"></p>
      <section class="cl-chart" aria-live="polite"></section>
      <div class="cl-links"></div>
      <p class="cl-credit muted">${esc(t("clima.credit"))}</p>`;
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

  function update() {
    const dock = panel.dock;
    if (!dock || !model) return;
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
    dock.querySelector(".cl-sum").textContent = row
      ? t("clima.peninsular", { month: monthName(month), value: formatLensValue(lens, row[month - 1]) }) : "";
    dock.querySelector(".cl-rule").textContent = RULES[variable].map((k) => doc.rules[k]).join(" ");
    dock.querySelector(".cl-links").innerHTML = monthLinks(ms, MODE);
    outlineStations(variable === "sun");
  }

  // A station's hex is one among thousands, often under a city's banner: the sunshine lens outlines them.
  function outlineStations(on) {
    if (on && !mark) {
      mark = { cells: new Set(model.doc.stations.filter((s) => s.sun).map((s) => s.cell)) };
      app.setHighlight(mark);
    } else if (!on && mark) {
      if (app.state.highlight === mark) app.setHighlight(null);
      mark = null;
    }
  }

  function chart(code) {
    const host = panel.dock?.querySelector(".cl-chart");
    if (!host || !model) return;
    shown = code;
    const p = code && model.doc.provinces[code];
    if (!p) {
      host.innerHTML = `<h3>${esc(t("clima.chart.title"))}</h3><p class="muted">${esc(t("clima.chart.hint"))}</p>`;
      return;
    }
    const short = Array.from({ length: 12 }, (_, k) => nameOf(k + 1, locale(), "narrow"));
    const svg = walterSvg({
      tmed: p.tmed, prec: p.prec, tmin: p.tmin, place: provinceName.get(code) || code, period: model.doc.vintage,
      months: short, num: (v, d) => fixed(v, d), labels: { frost: t("clima.chart.frost") }, id: "cl-wl",
    });
    const rows = Array.from({ length: 12 }, (_, k) => `<tr><th scope="row">${esc(nameOf(k + 1, locale(), "short").replace(/\.$/, ""))}</th>${TABLE.map((v) => `<td>${esc(fixed(p[v][k], 1))}</td>`).join("")}</tr>`).join("");
    const head = TABLE.map((v) => `<th scope="col">${esc(t(`clima.table.${v}`))}</th>`).join("");
    host.innerHTML = `
      <h3>${esc(t("clima.chart.title"))}${pinned ? ` <button type="button" class="ms-link" data-unpin>${esc(t("clima.chart.unpin"))}</button>` : ""}</h3>
      <p class="muted cl-chart-how">${esc(t(pinned ? "clima.chart.pinned" : "clima.chart.hover"))}</p>
      ${svg}
      <p class="muted cl-cap">${esc(t("clima.chart.caption"))}</p>
      <table class="cl-table"><caption>${esc(t("clima.table.caption", { place: provinceName.get(code) || code, period: model.doc.vintage }))}</caption>
        <thead><tr><th></th>${head}</tr></thead><tbody>${rows}</tbody></table>`;
  }
}
