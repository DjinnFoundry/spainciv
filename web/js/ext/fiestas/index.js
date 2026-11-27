// The fiesta calendar, "¿Dónde hay fiesta este mes?" / "Where's the party this month?", on a map whose data has
// fiestas.json (Spain).
//
//   lens "fiestas_mes" in the lens picker, after the fiestas lens: the hexes with a fiesta in the month, coloured by
//     its highest category, its fiestas and their dates (as the source writes them) in the tooltip
//   mode "fiestas" (opens and closes with the lens): the left dock with the month, the month's fiestas by category
//     and name (a click flies to its hexes) and how many have no month
//   URL hash: #lens=fiestas_mes&mes=8
// fiestas.json is loaded the first time the calendar opens; the month rules live in calendar.js.
import { country } from "../../app/country.js";
import { lensPanel, panelHead } from "../../app/lensPanel.js";
import { t } from "../../i18n.js";
import { esc, int } from "../../format.js";
import * as C from "./calendar.js";

const LENS = "fiestas_mes";
const MODE = "fiestas";
const HASH_KEY = "mes";
const FLY_SCALE = 2.4; // css px per km at most when a fiesta's hexes fly into view

export function install(app) {
  const fiestasLens = app.lensById.get("fiestas");
  if (!country().data?.includes("fiestas") || !fiestasLens) return;
  const n = app.w.grid.size;
  const monthName = (m, month = "long") => new Intl.DateTimeFormat(country().locale, { month }).format(new Date(2026, m - 1, 1));
  const catName = (c) => t(`fiestas.cat.${c}`);

  const lens = {
    id: LENS, group: fiestasLens.group, name: t("fiestas.lens.name"), icon: fiestasLens.icon, emoji: "📅",
    format: "category", scale: "linear", domain: [0, C.CATEGORIES.length - 1], higher_is: "neutral", unit: "",
    source: "fiestas_autonomicas", description: t("fiestas.lens.desc"),
    categories: C.CATEGORIES.map((id) => ({ id, name: catName(id), color: C.COLORS[id] })),
    ramp: C.CATEGORIES.map((id) => C.COLORS[id]),
    values: new Array(n).fill(null),
  };
  app.addLens(lens, { after: fiestasLens.id });

  let month = C.currentMonth();
  let doc = null; // fiestas.json once loaded
  let list = []; // the month's fiestas, in order
  let mark = null, token = 0;

  // --- the lens --------------------------------------------------------------------------------------------------
  function paint() {
    list = C.monthFiestas(doc.fiestas, month, country().locale);
    const layer = C.monthLayer(list, n, (f) => t("fiestas.tip", { name: f.name, category: catName(f.category), when: f.when }));
    Object.assign(lens, layer, { null_label: t("fiestas.lens.none", { month: monthName(month) }) });
    if (app.state.lens === lens) app.refreshLens();
  }

  const panel = lensPanel(app, lens, {
    mode: MODE,
    open(dock) {
      dock.innerHTML = `<p class="muted">${esc(t("fiestas.loading"))}</p>`;
      load(++token);
    },
    close() {
      token++;
      if (mark && app.state.highlight === mark) app.setHighlight(null);
      mark = null;
    },
  });

  async function load(my) {
    const data = await app.loadData("fiestas").catch(() => null);
    if (my !== token) return; // closed meanwhile
    const { dock } = panel;
    if (!data?.fiestas) {
      dock.innerHTML = `<p class="muted">${esc(t("fiestas.loadError"))}</p>`;
      return;
    }
    doc = data;
    paint();
    render();
  }

  function setMonth(m) {
    if (m === month) return;
    month = m;
    if (mark && app.state.highlight === mark) app.setHighlight(null);
    mark = null;
    if (doc) {
      paint();
      render();
    }
    app.hash.update();
  }

  app.hash.register(HASH_KEY, {
    get: () => (app.mode === MODE ? String(month) : null),
    set(v) {
      const m = C.parseMonth(v);
      if (m == null) return; // without the key the lens key decides (#lens=fiestas_mes: this month's calendar)
      setMonth(m);
      if (app.mode !== MODE) app.setMode(MODE);
    },
  });

  // --- a fiesta on the map ---------------------------------------------------------------------------------------
  function show(f) {
    const { dock } = panel;
    mark = { cells: new Set(f.cells) };
    app.setHighlight(mark);
    const b = app.highlightBounds(mark);
    if (b) app.fitBounds(b.x0, b.y0, b.x1, b.y1, { maxScale: Math.max(app.cam.scale, FLY_SCALE) });
    dock?.querySelectorAll(".fc-item[aria-current]").forEach((el) => el.removeAttribute("aria-current"));
    dock?.querySelector(`.fc-item[data-k="${list.indexOf(f)}"]`)?.setAttribute("aria-current", "true");
  }

  // --- the dock --------------------------------------------------------------------------------------------------
  function render() {
    const { dock } = panel;
    if (!dock || !doc) return;
    const per = C.perMonth(doc.fiestas);
    const top = Math.max(1, ...per);
    const months = per.map((count, k) => {
      const m = k + 1, on = m === month;
      return `<button type="button" class="fc-month${on ? " on" : ""}" role="radio" aria-checked="${on}" tabindex="${on ? 0 : -1}"
        data-m="${m}" aria-label="${esc(t("fiestas.month", { month: monthName(m), n: count }))}" title="${esc(t("fiestas.month", { month: monthName(m), n: count }))}">
        <i style="height:${Math.round((count / top) * 100)}%"></i><span>${esc(monthName(m, "short").replace(/\.$/, ""))}</span></button>`;
    }).join("");
    const groups = C.CATEGORIES.map((c) => {
      const items = list.map((f, k) => [f, k]).filter(([f]) => f.category === c);
      if (!items.length) return "";
      return `<section class="fc-group"><h3><i style="background:${C.COLORS[c]}"></i>${esc(catName(c))} <span class="muted">${int(items.length)}</span></h3>
        <ol class="fc-list">${items.map(([f, k]) => item(f, k)).join("")}</ol></section>`;
    }).join("");
    const title = month === C.currentMonth() ? t("fiestas.title.now") : t("fiestas.title", { month: monthName(month) });
    dock.innerHTML = `
      ${panelHead(title, t("fiestas.close"))}
      <div class="fc-months" role="radiogroup" aria-label="${esc(t("fiestas.months"))}">${months}</div>
      <p class="fc-sum">${esc(t("fiestas.summary", { n: list.length, month: monthName(month) }))}</p>
      ${groups}
      <p class="fc-undated muted">${esc(t("fiestas.undated", { n: C.undated(doc.fiestas) }))}</p>`;
    const strip = dock.querySelector(".fc-months");
    strip.onclick = (e) => {
      const b = e.target.closest("[data-m]");
      if (b) setMonth(+b.dataset.m);
    };
    strip.onkeydown = (e) => {
      const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
      if (!step) return;
      e.preventDefault();
      setMonth(((month - 1 + step + 12) % 12) + 1);
      dock?.querySelector(".fc-month.on")?.focus();
    };
    dock.querySelectorAll("button.fc-item").forEach((b) => (b.onclick = () => show(list[+b.dataset.k])));
  }

  function item(f, k) {
    const where = [f.place, f.community].filter(Boolean).join(" · ");
    const body = `<b class="fc-name">${esc(f.name)}</b>${where ? `<span class="fc-where">${esc(where)}</span>` : ""}
      <span class="fc-when">${esc(f.when)}</span>`;
    return f.cells.length
      ? `<li><button type="button" class="fc-item" data-k="${k}" title="${esc(t("fiestas.show"))}">${body}</button></li>`
      : `<li><div class="fc-item">${body}<span class="fc-where muted">${esc(t("fiestas.nowhere"))}</span></div></li>`;
  }
}
