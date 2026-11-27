// The sun lens, "Sol y reloj" / "Sun and clock", for a country whose page settings say `sunset: true` (pipeline/countries
// Page.sunset, written by pipeline/site.py). Spain's clocks run on Central European Time though nearly all of it lies
// west of Greenwich, so the sun sets very late in the west.
//
//   lens "atardecer" in the lens picker (Territorio / Land): each land hex coloured by the clock time of its sunset,
//     sunrise or solar noon, or by its hours of daylight, on the chosen day; the legend and the tooltip name that
//     quantity (`heading`), the tooltip gives the rest of the hex's day (`tip`, worked out for the hex under the
//     pointer), and the legend the spread across the country (its first and last hexes, and on Central European Time
//     alone when the Canaries are one of them)
//   mode "sun" (opens and closes with the lens): the left dock with the day (Spain's today by default; 21 June,
//     21 December, today) and the switch between the four times; on phones, where the dock covers the legend, the
//     dock repeats the colour key and the spread
//   URL hash: #lens=atardecer&dia=2026-06-21&sol=puesta
// Nothing is worked out until the panel first opens. The sun and the clocks live in solar.js; each hex is its centre's
// longitude and latitude (geo.js mapProjection).
import { country } from "../../app/country.js";
import { lensPanel, panelHead, panelKey, updatePanelKey } from "../../app/lensPanel.js";
import { t } from "../../i18n.js";
import { clock, esc, longDate } from "../../format.js";
import { mapProjection } from "../../geo.js";
import { formatDuration } from "../../ui/lenses.js";
import * as S from "./solar.js";

const LENS = "atardecer";
const MODE = "sun";
const DAY_KEY = "dia";
const MODE_KEY = "sol";
const GROUP = "land";
const SOURCE = "noaa_solar";
const RAMP = ["#22285a", "#553a8a", "#a8467e", "#e5704f", "#ffcf6e"]; // night blue to evening gold, earliest to latest
const TIP_ORDER = ["sunrise", "noon", "sunset", "day"]; // the tooltip's day, in the order it happens

export function install(app) {
  if (!country().sunset) return;
  const { w } = app;
  const proj = mapProjection(app.data.world.country?.projection);
  if (!proj) return;
  const n = w.grid.size;
  const placeOf = (i) => w.raw.counties[w.raw.county[i]]?.name || w.raw.states[w.raw.owner[i]]?.name || "";

  const lens = {
    id: LENS, group: GROUP, name: t("sun.lens.name"), icon: "l-sunset", emoji: "🌇", format: "clock", scale: "linear",
    domain: [0, 1], higher_is: "neutral", unit: "", source: SOURCE, description: t("sun.lens.desc"),
    scale_text: t("sun.scale"), ramp: RAMP, values: new Array(n).fill(null),
  };
  app.addLens(lens, { after: app.data.lenses.lenses.filter((l) => l.group === GROUP).at(-1)?.id });

  let points = null; // the land hexes' centres, on first paint
  let layer = null; // the chosen day and mode, once painted
  let day = null; // null until chosen: the panel opens on Spain's today
  let mode = "sunset";

  // --- the lens --------------------------------------------------------------------------------------------------
  function landPoints() {
    const out = [];
    for (let i = 0; i < n; i++) {
      if (w.raw.owner[i] < 0) continue;
      const [lon, lat] = proj.inverse(w.grid.cx(i), w.grid.cy(i));
      out.push({ cell: i, lon, lat });
    }
    return out;
  }

  // The hex's day apart from the quantity the lens shows, and its clock: "Salida 06:53 · Mediodía solar 14:35 · CEST".
  const shown = (m, v) => (m === "day" ? formatDuration(v) : clock(v));
  function tip(i) {
    const s = layer?.days[i];
    if (!s) return "";
    const parts = TIP_ORDER.filter((m) => m !== mode).map((m) => t(`sun.tip.${m}`, { time: shown(m, s[m]) }));
    return [...parts, s.abbr].join(" · ");
  }

  // "Muxía (22:20 CEST)"; a duration has no zone.
  const at = (x) => `${placeOf(x.cell)} (${shown(mode, x.value)}${mode === "day" ? "" : ` ${x.abbr}`})`;
  const spread = (low, high) => ({ a: at(high), b: at(low), diff: formatDuration(high.value - low.value) });

  function paint() {
    points ??= landPoints();
    layer = S.sunLayer(points, n, day, mode);
    const { low, high, zones } = layer;
    // When the Canaries hold an extreme, the spread includes their hour of clock: give the one on CET too.
    const ce = zones.CE, mixed = mode !== "day" && low.zone !== high.zone;
    const note = [`${t(`sun.mode.${mode}`)}, ${longDate(day.y, day.m, day.d)}.`, t("sun.spread", spread(low, high)),
      mixed ? t("sun.spread.ce", spread(ce.low, ce.high)) : ""].filter(Boolean).join(" ");
    Object.assign(lens, {
      values: layer.values, tip, heading: t(`sun.mode.${mode}`), format: mode === "day" ? "duration" : "clock",
      domain: [low.value, Math.max(high.value, low.value + 1)], note,
    });
    if (app.state.lens === lens) app.refreshLens();
    update();
  }

  const panel = lensPanel(app, lens, {
    mode: MODE, width: 320, open: build,
    close: () => document.body.classList.remove("sn-open"),
  });

  // A new day or mode: painted at once while the panel is open, else when it opens.
  function set(next) {
    const d = next.day ?? day, m = next.mode ?? mode;
    if (d && day && S.sameDay(d, day) && m === mode) return;
    day = d;
    mode = m;
    if (panel.dock) paint();
    app.hash.update();
  }

  // Both keys are written while the panel is open; either one in a link opens it.
  const fromLink = (value) => {
    if (value == null) return; // without the key: today, or the day / mode already chosen
    set(value);
    if (app.mode !== MODE) app.setMode(MODE);
  };
  app.hash.register(DAY_KEY, {
    get: () => (app.mode === MODE && day ? S.isoDay(day) : null),
    set: (v) => {
      const d = S.parseDay(v);
      fromLink(d && { day: d });
    },
  });
  app.hash.register(MODE_KEY, {
    get: () => (app.mode === MODE ? S.MODE_SLUG[mode] : null),
    set: (v) => {
      const m = S.parseMode(v);
      fromLink(m && { mode: m });
    },
  });

  // --- the dock --------------------------------------------------------------------------------------------------
  // Built once when the panel opens; a new day or time only updates it, so the date field keeps its focus.
  function build(dock) {
    day ??= S.spainToday();
    document.body.classList.add("sn-open");
    const modes = S.MODES.map((m) => `<button type="button" class="sn-mode" role="radio" data-mode="${m}">${esc(t(`sun.mode.${m}`))}</button>`).join("");
    const quick = ["june", "december", "today"].map((k) => `<button type="button" class="chip" data-pick="${k}">${esc(t(`sun.${k}`))}</button>`).join("");
    dock.innerHTML = `
      ${panelHead(lens.name, t("sun.close"))}
      <div class="sn-modes" role="radiogroup" aria-label="${esc(t("sun.modes"))}">${modes}</div>
      <label class="sn-day">${esc(t("sun.day"))} <input type="date" min="${S.FIRST_YEAR}-01-01" max="${S.LAST_YEAR}-12-31" required></label>
      <div class="chips" role="group" aria-label="${esc(t("sun.picks"))}">${quick}</div>
      ${panelKey()}
      <p class="sn-note"></p>
      <p class="muted">${esc(t("sun.why"))}</p>`;
    const strip = dock.querySelector(".sn-modes");
    strip.onclick = (e) => {
      const b = e.target.closest("[data-mode]");
      if (b) set({ mode: b.dataset.mode });
    };
    strip.onkeydown = (e) => {
      const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
      if (!step) return;
      e.preventDefault();
      set({ mode: S.MODES[(S.MODES.indexOf(mode) + step + S.MODES.length) % S.MODES.length] });
      strip.querySelector(".on")?.focus();
    };
    // An emptied or impossible date puts the chosen day back in the field.
    dock.querySelector(".sn-day input").onchange = (e) => {
      const d = S.parseDay(e.target.value);
      if (d) set({ day: d });
      else update();
    };
    dock.querySelector(".chips").onclick = (e) => {
      const b = e.target.closest("[data-pick]");
      if (b) set({ day: pick(b.dataset.pick) });
    };
    paint();
  }

  // The quick picks: the solstices of the chosen day's year, and Spain's today (read when asked, so a tab left open
  // past midnight moves on).
  const pick = (k) => (k === "today" ? S.spainToday() : { y: day.y, m: k === "june" ? 6 : 12, d: 21 });

  function update() {
    const dock = panel.dock;
    if (!dock || !layer) return;
    dock.querySelectorAll(".sn-mode").forEach((b) => {
      const on = b.dataset.mode === mode;
      b.classList.toggle("on", on);
      b.setAttribute("aria-checked", String(on));
      b.tabIndex = on ? 0 : -1;
    });
    dock.querySelectorAll("[data-pick]").forEach((b) => {
      const on = S.sameDay(pick(b.dataset.pick), day);
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", String(on));
    });
    const input = dock.querySelector(".sn-day input");
    if (input.value !== S.isoDay(day)) input.value = S.isoDay(day);
    updatePanelKey(dock, lens, t("sun.key"));
    dock.querySelector(".sn-note").textContent = lens.note;
  }
}
