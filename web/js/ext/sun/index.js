// The sunset lens, "Atardecer" / "Sunset", for a country whose page settings say `sunset: true` (pipeline/countries
// Page.sunset, written by pipeline/site.py). Spain's clocks run on Central European Time though nearly all of it lies
// west of Greenwich, so the sun sets very late in the west.
//
//   lens "atardecer" in the lens picker (Territorio / Land): each land hex coloured by the clock time of its sunset,
//     sunrise or solar noon, or by its hours of daylight, on the chosen day; its whole day in the tooltip, and the
//     spread across the country (its first and last hexes) in the legend
//   mode "sun" (opens and closes with the lens): the left dock with the day (today by default; 21 June, 21 December,
//     today) and the switch between the four times
//   URL hash: #lens=atardecer&dia=2026-06-21&sol=puesta
// The sun and the clocks live in solar.js; each hex is its centre's longitude and latitude (geo.js mapProjection).
import { country } from "../../app/country.js";
import { lensPanel, panelHead } from "../../app/lensPanel.js";
import { t } from "../../i18n.js";
import { clock, esc } from "../../format.js";
import { mapProjection } from "../../geo.js";
import { formatDuration } from "../../ui/lenses.js";
import * as S from "./solar.js";

const LENS = "atardecer";
const MODE = "sun";
const DAY_KEY = "dia";
const MODE_KEY = "sol";
const GROUP = "land";
const RAMP = ["#22285a", "#553a8a", "#a8467e", "#e5704f", "#ffcf6e"]; // night blue to evening gold, earliest to latest
const SLUG_MODE = Object.fromEntries(Object.entries(S.MODE_SLUG).map(([m, s]) => [s, m]));

export function install(app) {
  if (!country().sunset) return;
  const { w } = app;
  const proj = mapProjection(app.data.world.country?.projection);
  if (!proj) return;
  const n = w.grid.size;
  const points = [];
  for (let i = 0; i < n; i++) {
    if (w.raw.owner[i] < 0) continue;
    const [lon, lat] = proj.inverse(w.grid.cx(i), w.grid.cy(i));
    points.push({ cell: i, lon, lat });
  }
  const placeOf = (i) => w.raw.counties[w.raw.county[i]]?.name || w.raw.states[w.raw.owner[i]]?.name || "";
  const longDate = (d) => new Intl.DateTimeFormat(country().locale, { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })
    .format(new Date(Date.UTC(d.y, d.m - 1, d.d)));
  const shown = (mode, v) => (mode === "day" ? formatDuration(v) : clock(v));

  const lens = {
    id: LENS, group: GROUP, name: t("sun.lens.name"), emoji: "🌇", format: "clock", scale: "linear", domain: [0, 1],
    higher_is: "neutral", unit: "", source: t("sun.source"), description: t("sun.lens.desc"), ramp: RAMP,
    values: new Array(n).fill(null),
  };
  app.addLens(lens, { after: app.data.lenses.lenses.filter((l) => l.group === GROUP).at(-1)?.id });

  let day = S.localDay();
  let mode = "sunset";

  // --- the lens --------------------------------------------------------------------------------------------------
  function paint() {
    const layer = S.sunLayer(points, n, day, mode);
    const names = [], labels = new Array(n).fill(null);
    for (const { cell } of points) {
      const s = layer.days[cell];
      const rise = mode === "sunrise";
      const lead = t(rise ? "sun.tip.sunrise" : "sun.tip.sunset", { time: clock(rise ? s.sunrise : s.sunset), zone: s.abbr });
      labels[cell] = [names.length];
      names.push(t("sun.tip", { lead, noon: clock(s.noon), day: formatDuration(s.day) }));
    }
    const { low, high } = layer;
    const at = (x) => `${placeOf(x.cell)} (${shown(mode, x.value)})`;
    const spread = t("sun.spread", { a: at(high), b: at(low), diff: formatDuration(high.value - low.value) });
    Object.assign(lens, {
      values: layer.values, names, labels, format: mode === "day" ? "duration" : "clock",
      domain: [low.value, Math.max(high.value, low.value + 1)],
      note: `${t(`sun.mode.${mode}`)}, ${longDate(day)}. ${spread}`,
    });
    if (app.state.lens === lens) app.refreshLens();
    update();
  }

  const panel = lensPanel(app, lens, { mode: MODE, width: 320, open: build });

  function set(next) {
    const d = next.day ?? day, m = next.mode ?? mode;
    if (S.sameDay(d, day) && m === mode) return;
    day = d;
    mode = m;
    paint();
    app.hash.update();
  }

  // Both keys are written while the panel is open; either one in a link opens it.
  app.hash.register(DAY_KEY, {
    get: () => (app.mode === MODE ? S.isoDay(day) : null),
    set(v) {
      const d = S.parseDay(v);
      if (!d) return; // without the key: today, or the day already chosen
      set({ day: d });
      if (app.mode !== MODE) app.setMode(MODE);
    },
  });
  app.hash.register(MODE_KEY, {
    get: () => (app.mode === MODE ? S.MODE_SLUG[mode] : null),
    set(v) {
      const m = SLUG_MODE[v];
      if (!m) return;
      set({ mode: m });
      if (app.mode !== MODE) app.setMode(MODE);
    },
  });

  // --- the dock --------------------------------------------------------------------------------------------------
  // Built once when the panel opens; a new day or time only updates it, so the date field keeps its focus.
  function build(dock) {
    const modes = S.MODES.map((m) => `<button type="button" class="sn-mode" role="radio" data-mode="${m}">${esc(t(`sun.mode.${m}`))}</button>`).join("");
    const quick = ["june", "december", "today"].map((k) => `<button type="button" class="chip" data-pick="${k}">${esc(t(`sun.${k}`))}</button>`).join("");
    dock.innerHTML = `
      ${panelHead(lens.name, t("sun.close"))}
      <div class="sn-modes" role="radiogroup" aria-label="${esc(t("sun.modes"))}">${modes}</div>
      <label class="sn-day">${esc(t("sun.day"))} <input type="date" min="1901-01-01" max="2099-12-31" required></label>
      <div class="chips" role="group" aria-label="${esc(t("sun.picks"))}">${quick}</div>
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
    dock.querySelector(".sn-day input").onchange = (e) => {
      const d = S.parseDay(e.target.value);
      if (d) set({ day: d });
    };
    dock.querySelector(".chips").onclick = (e) => {
      const b = e.target.closest("[data-pick]");
      if (b) set({ day: pick(b.dataset.pick) });
    };
    update();
  }

  // The quick picks: the solstices of the chosen day's year, and today.
  const pick = (k) => (k === "today" ? S.localDay() : { y: day.y, m: k === "june" ? 6 : 12, d: 21 });

  function update() {
    const dock = panel.dock;
    if (!dock) return;
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
    dock.querySelector(".sn-note").textContent = lens.note;
  }

  paint();
}
