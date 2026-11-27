// Fog of war, «España por descubrir» / "Spain to discover", for a country whose page settings have `explore`
// (pipeline/countries Page.explore, written by pipeline/site.py with the groups of regions its panel counts by).
//
//   map toggle "explore" in the Map menu, off by default (on in the URL as #layers=…,explore)
//   a small panel while it is on: the share explored, per group of regions, a copyable text and a reset; it folds
//   down to its first line
// While the toggle is on, land becomes explored around a land hex when its tooltip stays up for a moment, when it is
// clicked or tapped (a game guess too: the "tap" event sees every click), and when its city is selected (a search, a
// click, the City view). A reveal clears about HOVER_PX or TAP_PX css px around the hex at the map's zoom
// (model.revealRadius), so a map zoomed out clears more at once. The fog draws under the selection, the hover outline
// and the highlights (overlay z < 0), lets a lens show through, and covers the minimap too.
// The set is kept in localStorage when the browser allows it, merged with what other tabs saved; without storage the
// fog still works, it just forgets.
import { country } from "../../app/country.js";
import { copyText } from "../../app/share.js";
import { t } from "../../i18n.js";
import { esc, pct } from "../../format.js";
import { createFog } from "./fog.js";
import * as M from "./model.js";

const TOGGLE = "explore";
const HOVER_MS = 650; // how long a tooltip stays on a hex before it counts as seen
const HOVER_PX = 28; // what a reveal clears around the hex, in css px: a resting pointer…
const TAP_PX = 40; // …and a click, a tap or a selected city
const SAVE_MS = 400;
const RESET_MS = 4000; // how long the reset button stays armed after its first click
const Z = -10; // over the map, under the selection, the hover outline, the highlights and every other overlay
const LENS_ALPHA = 0.55; // the fog over an active lens: thinner, so the lens still reads under it

const storage = () => {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
};
const media = (q) => globalThis.matchMedia?.(q).matches ?? false;

export function install(app) {
  const cfg = country().explore;
  if (!cfg) return;
  const { w } = app;
  const model = M.createExplored(w.grid, w.raw.owner);
  if (!model.total) return;
  const storeKey = `${country().product}.explore`;
  const foldKey = `${storeKey}.folded`;
  M.load(model, storage(), storeKey);
  const codes = w.raw.states.map((s) => s.fips);
  const groups = () => M.groupProgress(model, cfg.groups, codes);
  const isLand = (cell) => cell >= 0 && w.raw.owner[cell] >= 0;
  const fogAlpha = () => (app.state?.lens ? LENS_ALPHA : 1);
  const cover = (ctx) => fog.draw(ctx, fogAlpha());

  let on = false, fog = null, panel = null, offOverlay = null, offHover = null;
  let hoverTimer = 0, saveTimer = 0, resetArmed = 0;

  function start() {
    if (on) return;
    on = true;
    if (!fog) {
      fog = createFog(w.grid, model);
      fog.paint();
    }
    offOverlay = app.registerOverlay({ id: "explore-fog", z: Z, draw: cover });
    offHover = app.on("hover", onHover);
    app.minimap?.setCover(cover);
    showPanel();
  }
  function stop() {
    if (!on) return;
    on = false;
    offOverlay?.();
    offHover?.();
    offOverlay = offHover = null;
    clearTimeout(hoverTimer);
    clearTimeout(resetArmed);
    resetArmed = 0;
    app.minimap?.setCover(null);
    panel?.remove();
    panel = null;
  }

  // --- what explores ------------------------------------------------------------------------------------------------
  function onHover({ cell }) {
    clearTimeout(hoverTimer);
    if (isLand(cell)) hoverTimer = setTimeout(() => explore(cell, HOVER_PX), HOVER_MS);
  }
  app.on("tap", (ev) => { explore(ev.cell, TAP_PX); });
  app.on("select", (sel) => { if (sel?.kind === "city") explore(sel.city.cell, TAP_PX); });

  function explore(cell, px) {
    if (!on || !isLand(cell)) return;
    const before = groups();
    const fresh = model.reveal(cell, M.revealRadius(w.grid.R * app.cam.scale, px));
    if (!fresh.length) return;
    fog.paint(fresh);
    shown();
    schedule();
    // A cheer when a group (or the whole country) is uncovered to the last hex.
    if (model.count === model.total) app.ui.toast(t("explore.allDone", { name: country().name }));
    else {
      const done = groups().find((g, k) => g.explored === g.total && before[k].explored < g.total);
      if (done) app.ui.toast(t("explore.groupDone", { name: done.name }));
    }
  }

  // The set changed: the map, the minimap and the panel show it.
  function shown() {
    app.requestDraw();
    if (on) app.minimap?.setCover(cover);
    renderPanel();
  }

  // --- keeping it ---------------------------------------------------------------------------------------------------
  // Saved a moment after the last reveal, and at once when the page is hidden or closed. Before writing, what another
  // tab saved is added in (M.pull), so two tabs do not wipe each other's progress; a "storage" event from one brings
  // its progress into the other straight away.
  function schedule() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(persist, SAVE_MS);
  }
  function persist() {
    clearTimeout(saveTimer);
    saveTimer = 0;
    if (M.pull(model, storage(), storeKey)) repaint();
    M.save(model, storage(), storeKey);
  }
  function repaint() {
    fog?.paint();
    shown();
  }
  const flush = () => saveTimer && persist();
  globalThis.addEventListener?.("pagehide", flush);
  globalThis.document?.addEventListener("visibilitychange", () => document.visibilityState === "hidden" && flush());
  globalThis.addEventListener?.("storage", (e) => {
    if (e.key === storeKey && e.newValue && model.merge(e.newValue)) repaint();
  });

  // --- the panel ----------------------------------------------------------------------------------------------------
  const shareLabel = (explored, total) => {
    const s = M.shownShare(explored, total);
    return pct(s.x, s.d);
  };
  const folded = () => {
    try {
      const v = storage()?.getItem(foldKey);
      if (v != null) return v === "1";
    } catch { /* not remembered */ }
    return media("(max-width: 700px)"); // a phone starts with the panel folded: it would cover the north of the map
  };
  function setFolded(v) {
    try {
      storage()?.setItem(foldKey, v ? "1" : "0");
    } catch { /* not remembered */ }
    panel.classList.toggle("folded", v);
    const btn = panel.querySelector(".ex-fold");
    btn.setAttribute("aria-expanded", String(!v));
    btn.setAttribute("aria-label", t(v ? "explore.expand" : "explore.collapse"));
    btn.textContent = v ? "▾" : "▴";
  }

  function showPanel() {
    panel = document.createElement("section");
    panel.className = "panel explore-panel";
    panel.setAttribute("aria-label", t("explore.title", { name: country().name }));
    panel.innerHTML = `<div class="ex-head"><h2>${esc(t("explore.title", { name: country().name }))}</h2>
        <button type="button" class="ex-fold" data-act="fold"></button></div>
      <p class="ex-line" aria-live="polite"></p>
      <div class="ex-bar" aria-hidden="true"><i></i></div>
      <div class="ex-more">
        <p class="ex-hint muted">${esc(t(media("(hover: none)") ? "explore.hint.touch" : "explore.hint"))}</p>
        ${cfg.groups?.length ? `<details class="ex-groups"><summary>${esc(t("explore.groups"))}</summary><ol></ol></details>` : ""}
        <div class="ex-actions">
          <button type="button" class="btn" data-act="share">${esc(t("explore.copy"))}</button>
          <button type="button" class="btn" data-act="reset"></button>
        </div>
      </div>`;
    panel.addEventListener("click", onPanelClick);
    document.body.appendChild(panel);
    setFolded(folded());
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
    if (act === "fold") setFolded(!panel.classList.contains("folded"));
    else if (act === "share") app.ui.toast(t((await copyText(shareText())) ? "explore.copied" : "explore.copyFailed"));
    else if (act === "reset") {
      // Two clicks: the first arms the button for a few seconds.
      if (!resetArmed) {
        resetArmed = setTimeout(() => { resetArmed = 0; renderPanel(); }, RESET_MS);
        return renderPanel();
      }
      clearTimeout(resetArmed);
      resetArmed = 0;
      model.reset();
      persist();
      repaint();
    }
  }

  function shareText() {
    const c = country();
    const lang = c.data_lang && c.lang !== c.data_lang ? `&lang=${c.lang}` : "";
    const layers = app.ui.mapToggles().filter((x) => x.on).map((x) => x.id).join(",");
    return [
      t("explore.share", { pct: shareLabel(model.count, model.total), name: c.name, product: c.product }),
      M.progressSquares(model, groups()),
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
