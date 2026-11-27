// The Almanac: what every number means and exactly where it comes from.
import { resolveTables } from "../terrain.js";
import { esc, fixed, localeNum, plain } from "../format.js";
import { t } from "../i18n.js";
import { country } from "../app/country.js";
import { parseHex, luminance } from "../color.js";
import { icon, glyph } from "./icon.js";
import { formatLensValue, isTimeLens } from "./lenses.js";

const COVER_ICON = { forest_deciduous: "l-forest", forest_evergreen: "l-forest", forest_mixed: "l-forest", cropland: "l-farmland", pasture: "l-farmland", urban: "l-developed" };
// Glyph colour that reads on a resource medallion (dark on light faces such as nuclear yellow or silver).
const inkOn = (hex) => {
  try { return /^#[0-9a-f]{6}$/i.test(hex || "") && luminance(parseHex(hex)) > 0.4 ? "#1c1710" : "#f8f0d8"; } catch { return "#f8f0d8"; }
};
const CATEGORY = { energy: "core.pedia.cat.energy", mineral: "core.pedia.cat.mineral", agri: "core.pedia.cat.agri" };
// A lens's scale ends: as numbers, or as the times of day / durations a time lens holds.
const bound = (l, v) => (isTimeLens(l) ? formatLensValue(l, v) : localeNum(v));
const PAGE_LABEL = { "About this map": "core.pedia.about", Yields: "core.pedia.yields", Terrain: "core.pedia.terrain", Lenses: "core.lens.lenses",
  Resources: "core.pedia.resources", Sources: "core.pedia.sources" };

export function initPedia(data) {
  const modal = document.getElementById("pedia");
  const card = modal.querySelector(".modal-card");
  const nav = document.getElementById("pedia-nav");
  const body = document.getElementById("pedia-body");
  const srcName = (id) => data.sources?.find((s) => s.id === id)?.title || id || "";
  let restoreFocus = null;

  const h2 = (ic, fb, text) => `<h2>${icon(ic, fb, { size: 24 })}<span>${esc(text)}</span></h2>`;

  // Page ids are stable (pedia.open("Yields"), data-pedia="Sources"); the labels and texts are in the tables.
  const g = data.world.grid;
  const pages = {
    "About this map": () => `
      ${h2("pedia", "📖", t("core.pedia.about"))}
      ${t("core.pedia.about.body", { cols: g.cols, rows: g.rows, km: plain(Math.round(g.radius * 20) / 10) })}`,
    Yields: () => `
      ${h2("y-production", "⚙️", t("core.pedia.yields"))}
      ${t("core.pedia.yields.intro")}
      <table>${data.nation.yields.map((y) => `<tr><td class="ic" style="color:${esc(y.color)}">${glyph(y, 26)}</td><td><b style="color:${esc(y.color)}">${esc(y.label)}${y.key === "gold" ? ` (${t("core.panel.gdpLabel")})` : ""}</b><br>${esc(y.description)}</td></tr>`).join("")}</table>
      ${t("core.pedia.yields.amenities")}`,
    States: () => `
      ${h2("terrain", "🗺️", country().levels.region.many)}
      ${t("core.pedia.states.body", { vintage: esc(data.nation.vintage), gdp: data.nation.gdp_vintage ? t("core.pedia.states.gdp", { vintage: esc(data.nation.gdp_vintage) }) : "", count: data.world.states.length })}
      ${data.states ? "" : `<p class="muted">${t("core.pedia.states.none")}</p>`}`,
    Terrain: () => {
      const tb = data.w?.tables || resolveTables(data.world.tables);
      const hasCover = Array.isArray(data.world.cover);
      const row = (x) => `<tr><td class="nm">${x.color ? `<span class="swatch" style="background:${esc(x.color)}"></span>` : ""}${
        COVER_ICON[x.key] ? icon(COVER_ICON[x.key], "", { size: 15 }) + " " : ""}<b>${esc(x.name)}</b></td><td>${esc(x.rule || "")}</td></tr>`;
      return `
      ${h2("terrain", "🗺️", t("core.pedia.terrain"))}
      ${t("core.pedia.terrain.intro")}
      <h4>${icon("l-forest", "🌲", { size: 16 })} ${t("core.pedia.terrain.cover")}</h4>
      ${hasCover
        ? `${t("core.pedia.terrain.coverBody")}
           <table>${tb.cover.filter((x) => x.id > 0).map(row).join("")}</table>`
        : `<p class="muted">${t("core.pedia.terrain.noCover")}</p>`}
      <h4>${t("core.pedia.terrain.relief")}</h4>
      <table>${tb.relief.map(row).join("")}</table>
      <h4>${icon("r-hydro", "💧", { size: 16 })} ${t("core.pedia.terrain.water")}</h4>
      <table>${tb.water.filter((x) => x.id > 0).map(row).join("")}</table>
      <h4>${t("core.pedia.terrain.beyond")}</h4>
      <p class="muted">${t("core.pedia.terrain.beyondBody")}</p>`;
    },
    Lenses: () => `
      ${h2("layers", "▤", t("core.lens.lenses"))}
      ${t("core.pedia.lenses.intro", { vintage: esc(data.lenses.vintage) })}
      ${(data.lenses.groups || [{ id: null, name: "" }]).map((grp) => {
        const ls = data.lenses.lenses.filter((l) => !grp.id || l.group === grp.id);
        if (!ls.length) return "";
        return `${grp.name ? `<h3 class="grp">${icon(`g-${grp.id}`, "", { size: 16 })} ${esc(grp.name)}</h3>` : ""}${ls.map((l) => `
          <div class="lens-entry"><div class="le-ic">${glyph(l, 26)}</div><div>
          <h4>${esc(l.name)}</h4><p>${esc(l.description)}<br>
          <i class="le-ramp" style="background:linear-gradient(90deg, ${(l.ramp || []).map(esc).join(",")})"></i>
          <span class="muted">${l.scale_text ? esc(l.scale_text) : t("core.pedia.lenses.scale", { scale: esc(l.scale === "log" ? t("core.pedia.scale.log") : l.scale === "linear" ? t("core.pedia.scale.linear") : l.scale), from: bound(l, l.domain[0]), to: bound(l, l.domain[1]), unit: esc(l.unit) })}${
            l.higher_is === "good" ? t("core.pedia.lenses.better") : l.higher_is === "bad" ? t("core.pedia.lenses.worse") : ""}${l.source ? " · " + esc(srcName(l.source)) : ""}</span></p></div></div>`).join("")}`;
      }).join("")}`,
    Resources: () => {
      const r = data.resources;
      if (!r?.types?.length) return `${h2("resources", "⛏️", t("core.pedia.resources"))}<p class="muted">${t("core.pedia.resources.none")}</p>`;
      const count = new Map();
      for (const it of r.items || []) count.set(it.type, (count.get(it.type) || 0) + 1);
      const cats = [...new Set(r.types.map((x) => x.category || "other"))];
      return `
      ${h2("resources", "⛏️", t("core.pedia.resources"))}
      ${t("core.pedia.resources.intro")}
      ${cats.map((c) => `<h4>${esc(CATEGORY[c] ? t(CATEGORY[c]) : c)}</h4><table class="res-table">
        <tr><th></th><th>${t("core.pedia.resources.type")}</th><th>${t("core.pedia.resources.counts")}</th><th>${t("core.pedia.resources.sites")}</th></tr>
        ${r.types.filter((x) => (x.category || "other") === c).map((x) => `<tr>
          <td class="ic"><span class="res-ic" style="background:${esc(x.color || "#24384f")};color:${inkOn(x.color)}">${glyph(x, 20)}</span></td>
          <td class="nm"><b>${esc(x.name)}</b>${x.unit ? `<br><span class="muted">${t("core.pedia.resources.unit", { unit: esc(x.unit) })}</span>` : ""}</td>
          <td>${esc(x.description || "")}<br><span class="muted">${t("core.pedia.source", { name: esc(srcName(x.source)) })}</span></td>
          <td class="num">${count.get(x.id) || 0}</td></tr>`).join("")}</table>`).join("")}`;
    },
    Sources: () => `
      ${h2("pedia", "📖", t("core.pedia.sources"))}
      ${data.sources.map((s) => `
        <h4>${esc(s.title)}</h4>
        <p>${esc(s.description)}<br>
        <span class="muted">${esc(s.publisher)} · ${esc(s.license)}${s.vintage ? " · " + esc(s.vintage) : ""} ·
        <a href="${esc(s.homepage)}" target="_blank" rel="noopener">${t("core.pedia.homepage")}</a></span></p>
        <table>${(s.files || []).map((f) => `<tr><td><code>${esc(f.url)}</code></td><td class="muted" style="white-space:nowrap">${esc((f.retrieved || "").slice(0, 10))}<br>${fixed((f.bytes || 0) / 1e6, 1)} MB</td></tr>`).join("")}</table>`).join("")}`,
  };
  const label = (id) => (id === "States" ? country().levels.region.many : t(PAGE_LABEL[id]));

  const show = (name) => {
    if (!pages[name]) name = "About this map";
    body.innerHTML = pages[name]();
    body.scrollTop = 0;
    nav.querySelectorAll("button").forEach((b) => {
      const on = b.dataset.page === name;
      b.classList.toggle("active", on);
      b.setAttribute("aria-current", on ? "page" : "false");
    });
  };
  nav.innerHTML = `<div class="hd">${t("page.pedia")}</div>` + Object.keys(pages).map((p) => `<button data-page="${esc(p)}">${esc(label(p))}</button>`).join("");
  nav.onclick = (e) => {
    const b = e.target.closest("button[data-page]");
    if (b) show(b.dataset.page);
  };
  const close = () => {
    if (modal.hidden) return;
    modal.hidden = true;
    if (restoreFocus && document.contains(restoreFocus)) restoreFocus.focus();
    restoreFocus = null;
  };
  modal.onclick = (e) => {
    if (e.target === modal || e.target.closest("[data-close]")) close();
  };
  // Keep Tab inside the dialog.
  modal.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    const f = [...card.querySelectorAll("button, a[href], [tabindex]:not([tabindex='-1'])")].filter((x) => x.offsetParent);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  return {
    open(page = "About this map") {
      if (modal.hidden) restoreFocus = document.activeElement;
      show(page);
      modal.hidden = false;
      (nav.querySelector("button.active") || card.querySelector("[data-close]"))?.focus();
    },
    close,
    get isOpen() {
      return !modal.hidden;
    },
  };
}
