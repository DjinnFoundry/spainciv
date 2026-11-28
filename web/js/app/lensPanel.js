// A lens built in the browser that comes with a panel in the left dock (the fiesta calendar, the sun lens, the
// reservoirs, the climate of the month, the timeline): picking the lens opens the panel, and closing either closes
// both. The panel is an app mode, so Esc closes it too. A panel can serve several lenses (the climate's four variables,
// the timeline's two views): picking any of them opens it, moving between them keeps it open, and any other lens
// closes it.
//
//   const panel = lensPanel(app, lens | [lens, ...], {mode, width, label, open(dock), close(), pick()})
//     label         the dock's accessible name (the first lens's name by default)
//     open(dock)    fill the dock (it is empty and on screen, one of the lenses already active)
//     close()       forget what the panel holds; the dock is emptied and hidden after it
//     pick()        the lens the panel opens on when none of its lenses is active (the first by default)
//   panel.dock      the dock element while open, else null
//   panelHead(title, closeLabel)   the panel's title row, with the close button
//   panelKey()                     a colour key for the panel, shown on phones only: there the dock is a bottom
//                                  sheet that covers the lens legend
//   updatePanelKey(dock, lens, label, owner)   draw the lens into that key: its ramp and three of its legend ticks, or
//                                  for a categorical lens the swatches its legend shows (owner: the hexes' owners,
//                                  which the legend's hide_empty rule counts on)
// A link that names one of the lenses (#lens=<id>) opens it: the hash's lens key was read before the extension added
// the lens. `leaving` keeps the mode's own lens change from re-entering it.
import { esc } from "../format.js";
import { categoryColor, categoryCounts, formatLensTick, shownCategories } from "../ui/lenses.js";

const CLASS = "lens-panel";
const KEY_TICKS = [[0, 0], [0.5, 2], [1, 4]]; // [position on the ramp, legend tick index] of the key's labels

export const panelHead = (title, closeLabel) => `<header class="${CLASS}-head"><h2>${esc(title)}</h2>
  <button type="button" class="icon-btn" data-close aria-label="${esc(closeLabel)}" title="${esc(closeLabel)}">✕</button></header>`;

export const panelKey = () => `<div class="pk-key" role="img"><i class="pk-ramp"></i><div class="pk-ticks"></div></div>`;

export function updatePanelKey(dock, lens, label, owner) {
  const key = dock.querySelector(".pk-key");
  if (!key) return;
  const ramp = key.querySelector(".pk-ramp");
  if (lens.format === "category" && lens.categories?.length) {
    const shown = shownCategories(lens, categoryCounts(lens, owner)), names = shown.map((k) => lens.categories[k].name);
    key.classList.add("pk-swatches");
    ramp.hidden = true;
    key.querySelector(".pk-ticks").innerHTML = shown.map((k, i) =>
      `<span class="pk-cat"><i style="background:${esc(categoryColor(lens, k))}"></i>${esc(names[i])}</span>`).join("");
    key.setAttribute("aria-label", `${label}: ${names.join(", ")}`);
    return;
  }
  key.classList.remove("pk-swatches");
  ramp.hidden = false;
  if (!lens.domain) return;
  const ticks = KEY_TICKS.map(([p, k]) => formatLensTick(lens, p, k));
  ramp.style.background = `linear-gradient(90deg, ${lens.ramp.join(",")})`;
  key.querySelector(".pk-ticks").innerHTML = ticks.map((s) => `<span>${esc(s)}</span>`).join("");
  key.setAttribute("aria-label", `${label}: ${ticks.join(", ")}`);
}

export function lensPanel(app, lensOrLenses, { mode, width = 360, label, open, close, pick }) {
  const lenses = [].concat(lensOrLenses);
  const mine = (l) => lenses.includes(l);
  let dock = null, leaving = false;
  const onClick = (e) => e.target.closest?.("[data-close]") && app.setMode(null);

  app.on("lens", (l) => {
    if (mine(l)) {
      if (app.mode !== mode) app.setMode(mode);
    } else if (app.mode === mode && !leaving) app.setMode(null);
  });

  app.registerMode(mode, {
    enter() {
      dock = app.ui.dock("left", { width, label: label ?? lenses[0].name });
      dock.classList.add(CLASS);
      dock.addEventListener("click", onClick);
      if (!mine(app.state.lens)) app.setLens(pick?.() ?? lenses[0]);
      open(dock);
    },
    exit() {
      leaving = true;
      try {
        close?.();
        dock?.classList.remove(CLASS);
        dock?.removeEventListener("click", onClick);
        app.ui.undock("left");
        dock = null;
        if (mine(app.state.lens)) app.setLens(null);
      } finally {
        leaving = false;
      }
    },
  });

  // In a microtask, so the caller has its panel (and its own hash keys registered) before the panel opens.
  queueMicrotask(() => {
    const linked = lenses.find((l) => l.id === app.hash.value("lens"));
    if (linked) app.setLens(linked);
  });

  return {
    get dock() {
      return dock;
    },
  };
}
