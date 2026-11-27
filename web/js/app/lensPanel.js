// A lens built in the browser that comes with a panel in the left dock (the fiesta calendar, the sun lens, the climate
// of the month): picking the lens opens the panel, and closing either closes both. The panel is an app mode, so Esc
// closes it too. A panel can serve several lenses (the climate's four variables): picking any of them opens it, moving
// between them keeps it open, and any other lens closes it.
//
//   const panel = lensPanel(app, lens | [lens, ...], {mode, width, open(dock), close(), pick()})
//     open(dock)    fill the dock (it is empty and on screen, one of the lenses already active)
//     close()       forget what the panel holds; the dock is emptied and hidden after it
//     pick()        the lens the panel opens on when none of its lenses is active (the first by default)
//   panel.dock      the dock element while open, else null
//   panelHead(title, closeLabel)   the panel's title row, with the close button
// A link that names one of the lenses (#lens=<id>) opens it: the hash's lens key was read before the extension added
// the lens. `leaving` keeps the mode's own lens change from re-entering it.
import { esc } from "../format.js";

const CLASS = "lens-panel";

export const panelHead = (title, closeLabel) => `<header class="${CLASS}-head"><h2>${esc(title)}</h2>
  <button type="button" class="icon-btn" data-close aria-label="${esc(closeLabel)}" title="${esc(closeLabel)}">✕</button></header>`;

export function lensPanel(app, lensOrLenses, { mode, width = 360, open, close, pick }) {
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
      dock = app.ui.dock("left", { width, label: lenses[0].name });
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
