// The fiesta calendar, "¿Dónde hay fiesta este mes?" / "Where's the party this month?", on a map whose data has
// fiestas.json (Spain).
//
//   lens "fiestas_mes" in the lens picker, after the fiestas lens: the hexes with a fiesta in the month, coloured by
//     its highest category, its fiestas and their dates (as the source writes them) in the tooltip
//   mode "fiestas" (opens and closes with the lens): the left dock with the month, the month's fiestas by category
//     and name (a click flies to its hexes) and how many have no month
//   URL hash: #lens=fiestas_mes&mes=8; #mes=8 alone opens it too (ext/month.js, shared with the climate of the month)
// fiestas.json is loaded the first time the calendar opens; the month rules live in calendar.js.
import { country } from "../../app/country.js";
import { lensPanel, panelHead } from "../../app/lensPanel.js";
import { t } from "../../i18n.js";
import { esc, int } from "../../format.js";
import { flyToCells } from "../flyToCells.js";
import * as C from "./calendar.js";
import { currentMonth, monthLinks, monthName as nameOf, monthState, monthStrip } from "../month.js";

const LENS = "fiestas_mes";
const MODE = "fiestas";
const FLY_SCALE = 2.4; // css px per km at most when a fiesta's hexes fly into view

export function install(app) {
  const fiestasLens = app.lensById.get("fiestas");
  if (!country().data?.includes("fiestas") || !fiestasLens) return;
  const n = app.w.grid.size;
  const monthName = (m) => nameOf(m, country().locale);
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

  const ms = monthState(app);
  let doc = null; // fiestas.json once loaded
  let list = []; // the month's fiestas, in order
  let mark = null, token = 0;

  // --- the lens --------------------------------------------------------------------------------------------------
  function paint() {
    list = C.monthFiestas(doc.fiestas, ms.month, country().locale);
    const layer = C.monthLayer(list, n, (f) => t("fiestas.tip", { name: f.name, category: catName(f.category), when: f.when }));
    Object.assign(lens, layer, { null_label: t("fiestas.lens.none", { month: monthName(ms.month) }) });
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

  // A new month: drawn at once while the calendar is open, else when it opens.
  ms.page({
    id: MODE, lensIds: [LENS], fallback: true, active: () => app.mode === MODE, open: () => app.setMode(MODE),
    linkLabel: (m) => t("fiestas.link", { month: monthName(m) }),
    onMonth() {
      if (mark && app.state.highlight === mark) app.setHighlight(null);
      mark = null;
      if (doc && panel.dock) {
        paint();
        render();
      }
    },
  });

  // --- a fiesta on the map ---------------------------------------------------------------------------------------
  function show(f) {
    const { dock } = panel;
    mark = flyToCells(app, f.cells, FLY_SCALE);
    dock?.querySelectorAll(".dk-item[aria-current]").forEach((el) => el.removeAttribute("aria-current"));
    dock?.querySelector(`.dk-item[data-k="${list.indexOf(f)}"]`)?.setAttribute("aria-current", "true");
  }

  // --- the dock --------------------------------------------------------------------------------------------------
  function render() {
    const { dock } = panel;
    if (!dock || !doc) return;
    const { month } = ms;
    const per = C.perMonth(doc.fiestas);
    const top = Math.max(1, ...per);
    const groups = C.CATEGORIES.map((c) => {
      const items = list.map((f, k) => [f, k]).filter(([f]) => f.category === c);
      if (!items.length) return "";
      return `<section class="fc-group"><h3><i style="background:${C.COLORS[c]}"></i>${esc(catName(c))} <span class="muted">${int(items.length)}</span></h3>
        <ol class="dk-list">${items.map(([f, k]) => item(f, k)).join("")}</ol></section>`;
    }).join("");
    const title = month === currentMonth() ? t("fiestas.title.now") : t("fiestas.title", { month: monthName(month) });
    dock.innerHTML = `
      ${panelHead(title, t("fiestas.close"))}
      <div class="ms-strip" aria-label="${esc(t("fiestas.months"))}"></div>
      <p class="fc-sum">${esc(t("fiestas.summary", { n: list.length, month: monthName(month) }))}</p>
      ${groups}
      <p class="fc-undated muted">${esc(t("fiestas.undated", { n: C.undated(doc.fiestas) }))}</p>
      ${monthLinks(ms, MODE)}`;
    monthStrip(dock.querySelector(".ms-strip"), {
      month, locale: country().locale, label: (m) => t("fiestas.month", { month: monthName(m), n: per[m - 1] }),
      bar: (m) => per[m - 1] / top, onPick: (m) => ms.set(m),
    });
    const links = dock.querySelector(".ms-links");
    if (links) links.onclick = ms.follow;
    dock.querySelectorAll("button.dk-item").forEach((b) => (b.onclick = () => show(list[+b.dataset.k])));
  }

  function item(f, k) {
    const where = [f.place, f.community].filter(Boolean).join(" · ");
    const body = `<b class="dk-name">${esc(f.name)}</b>${where ? `<span class="dk-where">${esc(where)}</span>` : ""}
      <span class="dk-when">${esc(f.when)}</span>`;
    return f.cells.length
      ? `<li><button type="button" class="dk-item" data-k="${k}" title="${esc(t("fiestas.show"))}">${body}</button></li>`
      : `<li><div class="dk-item">${body}<span class="dk-where muted">${esc(t("fiestas.nowhere"))}</span></div></li>`;
  }
}
