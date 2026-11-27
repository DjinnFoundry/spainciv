// Fog of war, «España por descubrir» / "Spain to discover", for a country whose page settings have `explore`
// (pipeline/countries Page.explore, written by pipeline/site.py with the groups of regions its panel counts by).
//
//   map toggle "explore" in the Map menu, off by default (on in the URL as #layers=…,explore)
//   a small panel while it is on: the share explored, per group of regions, a copyable text and a reset
// A land hex becomes explored, with its neighbours, when its tooltip stays up for a moment, when it is clicked (a
// game guess too: the "tap" event sees every click), and when its city is selected (a search, a click, the City view).
// The set is kept in localStorage when the browser allows it; without it the fog still works, it just forgets.
import { country } from "../../app/country.js";
import { copyText } from "../../app/share.js";
import { t } from "../../i18n.js";
import { esc, pct } from "../../format.js";
import { createFog } from "./fog.js";
import * as M from "./model.js";

const TOGGLE = "explore";
const HOVER_MS = 650; // how long a tooltip stays on a hex before it counts as seen
const SAVE_MS = 400;
const Z = 95; // over the map and its highlights, under the city banners (overlays from z 100 draw after them)

const storage = () => {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
};

export function install(app) {
  const cfg = country().explore;
  if (!cfg) return;
  const { w } = app;
  const model = M.createExplored(w.grid, w.raw.owner);
  if (!model.total) return;
  const storeKey = `${country().product}.explore`;
  M.load(model, storage(), storeKey);
  const codes = w.raw.states.map((s) => s.fips);
  const groups = () => M.groupProgress(model, cfg.groups, codes);

  let on = false, fog = null, panel = null, offOverlay = null, offHover = null, hoverTimer = 0, saveTimer = 0, resetArmed = 0;

  function start() {
    if (on) return;
    on = true;
    if (!fog) {
      fog = createFog(w.grid, model);
      fog.paint();
    }
    offOverlay = app.registerOverlay({ id: "explore-fog", z: Z, draw: (ctx) => fog.draw(ctx) });
    offHover = app.on("hover", onHover);
    showPanel();
  }
  function stop() {
    if (!on) return;
    on = false;
    offOverlay?.();
    offHover?.();
    offOverlay = offHover = null;
    clearTimeout(hoverTimer);
    panel?.remove();
    panel = null;
  }

  // --- what explores ------------------------------------------------------------------------------------------------
  function onHover({ cell }) {
    clearTimeout(hoverTimer);
    if (cell >= 0 && !model.isExplored(cell)) hoverTimer = setTimeout(() => explore(cell), HOVER_MS);
  }
  app.on("tap", (ev) => { explore(ev.cell); });
  app.on("select", (sel) => { if (sel?.kind === "city") explore(sel.city.cell); });

  function explore(cell) {
    if (!on || !(cell >= 0)) return;
    const before = groups();
    const fresh = model.reveal(cell);
    if (!fresh.length) return;
    fog.paint(fresh);
    app.requestDraw();
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => M.save(model, storage(), storeKey), SAVE_MS);
    renderPanel();
    // A cheer when a group (or the whole country) is uncovered to the last hex.
    if (model.count === model.total) app.ui.toast(t("explore.allDone", { name: country().name }));
    else {
      const done = groups().find((g, k) => g.explored === g.total && before[k].explored < g.total);
      if (done) app.ui.toast(t("explore.groupDone", { name: done.name }));
    }
  }

  // --- the panel ----------------------------------------------------------------------------------------------------
  const shareLabel = (explored, total) => {
    const s = M.shownShare(explored, total);
    return pct(s.x, s.d);
  };

  function showPanel() {
    panel = document.createElement("section");
    panel.className = "panel explore-panel";
    panel.setAttribute("aria-label", t("explore.title", { name: country().name }));
    panel.innerHTML = `<h2>${esc(t("explore.title", { name: country().name }))}</h2>
      <p class="ex-line" aria-live="polite"></p>
      <div class="ex-bar" aria-hidden="true"><i></i></div>
      <p class="ex-hint muted">${esc(t("explore.hint"))}</p>
      ${cfg.groups?.length ? `<details class="ex-groups"><summary>${esc(t("explore.groups"))}</summary><ol></ol></details>` : ""}
      <div class="ex-actions">
        <button type="button" class="btn" data-act="share">${esc(t("explore.copy"))}</button>
        <button type="button" class="btn" data-act="reset"></button>
      </div>`;
    panel.addEventListener("click", onPanelClick);
    document.body.appendChild(panel);
    renderPanel();
  }

  function renderPanel() {
    if (!panel) return;
    const s = M.shownShare(model.count, model.total);
    panel.querySelector(".ex-line").innerHTML = t("explore.line", {
      pct: `<b>${esc(pct(s.x, s.d))}</b>`, name: esc(country().name),
    });
    panel.querySelector(".ex-bar i").style.width = `${(model.count / model.total) * 100}%`;
    const list = panel.querySelector(".ex-groups ol");
    if (list) {
      list.innerHTML = groups().map((g) => `<li${g.explored === g.total ? ' class="done"' : ""}><span>${esc(g.name)}</span>
        <span class="ex-mini" aria-hidden="true"><i style="width:${(g.explored / g.total) * 100}%"></i></span>
        <b>${esc(shareLabel(g.explored, g.total))}</b></li>`).join("");
    }
    panel.querySelector('[data-act="reset"]').textContent = t(resetArmed ? "explore.reset.confirm" : "explore.reset");
  }

  async function onPanelClick(e) {
    const act = e.target.closest("[data-act]")?.dataset.act;
    if (act === "share") app.ui.toast(t((await copyText(shareText())) ? "explore.copied" : "explore.copyFailed"));
    else if (act === "reset") {
      // Two clicks: the first arms the button for a few seconds.
      if (!resetArmed) {
        resetArmed = setTimeout(() => { resetArmed = 0; renderPanel(); }, 4000);
        return renderPanel();
      }
      clearTimeout(resetArmed);
      resetArmed = 0;
      model.reset();
      M.save(model, storage(), storeKey);
      fog.paint();
      app.requestDraw();
      renderPanel();
    }
  }

  function shareText() {
    const c = country();
    const tenths = Math.floor((model.count / model.total) * 10);
    const lang = c.data_lang && c.lang !== c.data_lang ? `&lang=${c.lang}` : "";
    const layers = app.ui.mapToggles().filter((x) => x.on).map((x) => x.id).join(",");
    return [
      t("explore.share", { pct: shareLabel(model.count, model.total), name: c.name, product: c.product }),
      "🟩".repeat(tenths) + "⬜".repeat(10 - tenths),
      `https://${c.site_url}/#layers=${layers}${lang}`,
    ].join("\n");
  }

  // Last: a link with the toggle on starts the fog right here, so everything above must exist.
  app.ui.addMapToggle({
    id: TOGGLE, label: t("explore.toggle"), title: t("explore.toggle.title"), icon: "🧭", default: false,
    get: () => on,
    set: (v) => (v ? start() : stop()),
  });
}
