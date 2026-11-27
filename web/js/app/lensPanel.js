// A lens built in the browser that comes with a panel in the left dock (the fiesta calendar, the sunset lens): picking
// the lens opens the panel, and closing either closes both. The panel is an app mode, so Esc closes it too.
//
//   const panel = lensPanel(app, lens, {mode, width, open(dock), close()})
//     open(dock)    fill the dock (it is empty and on screen, the lens already active)
//     close()       forget what the panel holds; the dock is emptied and hidden after it
//   panel.dock      the dock element while open, else null
//   panelHead(title, closeLabel)   the panel's title row, with the close button
// A link that names the lens (#lens=<id>) opens it: the hash's lens key was read before the extension added the lens.
// `leaving` keeps the mode's own lens change from re-entering it.
import { esc } from "../format.js";

const CLASS = "lens-panel";

export const panelHead = (title, closeLabel) => `<header class="${CLASS}-head"><h2>${esc(title)}</h2>
  <button type="button" class="icon-btn" data-close aria-label="${esc(closeLabel)}" title="${esc(closeLabel)}">✕</button></header>`;

export function lensPanel(app, lens, { mode, width = 360, open, close }) {
  let dock = null, leaving = false;
  const onClick = (e) => e.target.closest?.("[data-close]") && app.setMode(null);

  app.on("lens", (l) => {
    if (l === lens) {
      if (app.mode !== mode) app.setMode(mode);
    } else if (app.mode === mode && !leaving) app.setMode(null);
  });

  app.registerMode(mode, {
    enter() {
      dock = app.ui.dock("left", { width, label: lens.name });
      dock.classList.add(CLASS);
      dock.addEventListener("click", onClick);
      if (app.state.lens !== lens) app.setLens(lens);
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
        if (app.state.lens === lens) app.setLens(null);
      } finally {
        leaving = false;
      }
    },
  });

  // In a microtask, so the caller has its panel (and its own hash keys registered) before the panel opens.
  queueMicrotask(() => app.hash.value("lens") === lens.id && app.setLens(lens));

  return {
    get dock() {
      return dock;
    },
  };
}
