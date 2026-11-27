// The daily game "Adivina el hexágono" / "Guess the hex", for a country whose page settings say `game: true`
// (pipeline/countries Page.game, written by pipeline/site.py).
//
//   app mode "game"; URL hash #juego (the link a finished game shares opens the game)
//   top-bar button "Juego" / "Game"
// The rules, clues and points live in puzzle.js; this module docks the game beside the map, takes map clicks as
// guesses, marks them on the map and flies to the answer at the end. Today's progress and the stats are kept in
// localStorage when the browser allows it; without it the game still plays, it just forgets.
import { country } from "../../app/country.js";
import { copyText } from "../../app/share.js";
import { t } from "../../i18n.js";
import { esc, int } from "../../format.js";
import { mapProjection } from "../../geo.js";
import { hexPath } from "../../render/map.js";
import { showCellTooltip } from "../../ui/tooltip.js";
import * as P from "./puzzle.js";

const MODE = "game";
const HASH_KEY = "juego";
const ANSWER_SCALE = 2.4; // css px per km when the answer flies into view (a hex about 14 px across)
const FONT = '-apple-system, "Segoe UI", system-ui, sans-serif';
const SQUARE_COLOR = { "🟩": "#4fa85a", "🟨": "#e0bf45", "🟧": "#e0873a", "🟥": "#c8483a" };
const ICON = `<svg class="icon" width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 2 20.7 7v10L12 22l-8.7-5V7z" fill="none" stroke="currentColor" stroke-width="2"/><path d="M9.6 9.4a2.5 2.5 0 1 1 3.6 2.3c-.8.4-1.2.9-1.2 1.8v.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="17" r="1.2" fill="currentColor"/></svg>`;

const storeKey = () => `${country().product}.game`;
function loadSaved() {
  try {
    const s = JSON.parse(globalThis.localStorage?.getItem(storeKey()) || "null");
    return s && typeof s === "object" ? s : {};
  } catch {
    return {}; // storage blocked or unreadable: a fresh game
  }
}
function save(s) {
  try {
    globalThis.localStorage?.setItem(storeKey(), JSON.stringify(s));
  } catch {
    /* not remembered */
  }
}

export function install(app) {
  if (!country().game) return;
  const { w } = app;
  const proj = mapProjection(app.data.world.country?.projection);
  const density = app.lensById.get("density");
  if (!proj || !density) return;
  const pool = P.puzzlePool(w.raw, density);
  if (!pool.length) return;
  const names = [...w.raw.counties, ...w.raw.states, ...app.data.cities].map((x) => x.name);
  const isLand = (i) => Number.isInteger(i) && i >= 0 && i < w.grid.size && w.raw.owner[i] >= 0;
  const placeOf = (i) => {
    const unit = w.raw.counties[w.raw.county[i]]?.name, region = w.raw.states[w.raw.owner[i]]?.name;
    return unit && region ? `${unit} (${region})` : region || unit || "";
  };

  let saved = loadSaved();
  let game = null; // {day, cell, guesses: [cell], clues: n, list: buildClues()}
  let dock = null, mark = null, offOverlay = null, token = 0;
  const now = () => P.standing({ grid: w.grid, proj, cell: game.cell, guesses: game.guesses, clues: game.clues });

  // --- top-bar button and URL ---------------------------------------------------------------------------------
  const btn = app.ui.addTopButton({
    id: "btn-game", label: t("game.button"), title: t("game.button.title"),
    onClick: () => app.setMode(app.mode === MODE ? null : MODE),
  });
  if (btn) btn.innerHTML = `${ICON}<span class="lbl">${esc(t("game.button"))}</span>`;
  app.on("mode", ({ name }) => btn?.setAttribute("aria-pressed", String(name === MODE)));
  btn?.setAttribute("aria-pressed", "false");
  app.hash.register(HASH_KEY, {
    get: () => (app.mode === MODE ? "1" : null),
    set: (v) => {
      if (v != null && app.mode !== MODE) app.setMode(MODE);
      else if (v == null && app.mode === MODE) app.setMode(null);
    },
  });

  // --- the map: guesses are hexes coloured like their share squares -------------------------------------------
  const overlay = {
    id: "game-guesses", z: 40,
    draw(ctx, cam) {
      if (!game) return;
      const s = cam.scale;
      const { kms } = now();
      const px = Math.min(w.grid.R * 1.1, 13 / s);
      ctx.font = `bold ${px}px ${FONT}`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      game.guesses.forEach((g, k) => {
        hexPath(ctx, w.grid, g, 0.92);
        ctx.fillStyle = SQUARE_COLOR[P.square(kms[k])];
        ctx.globalAlpha = 0.85;
        ctx.fill();
        ctx.globalAlpha = 1;
        ctx.lineWidth = 1.5 / s;
        ctx.strokeStyle = "rgba(20,14,4,.9)";
        ctx.stroke();
        ctx.fillStyle = "#14100a";
        ctx.fillText(String(k + 1), w.grid.cx(g), w.grid.cy(g) + px * 0.05);
      });
    },
  };

  // --- the mode -------------------------------------------------------------------------------------------------
  app.registerMode(MODE, {
    enter() {
      app.clearSelection();
      dock = app.ui.dock("left", { width: 360, label: t("game.title") });
      dock.classList.add("game-dock");
      dock.innerHTML = `<p class="gm-loading muted">${esc(t("game.loading"))}</p>`;
      offOverlay = app.registerOverlay(overlay);
      start(++token);
    },
    exit() {
      token++;
      offOverlay?.();
      offOverlay = null;
      if (mark && app.state.highlight === mark) app.setHighlight(null);
      mark = null;
      game = null;
      dock?.classList.remove("game-dock");
      app.ui.undock("left");
      dock = null;
    },
  });

  async function start(my) {
    const day = P.dayNumber();
    const cell = P.dailyCell(pool, day);
    const people = country().data?.includes("personajes") ? (await app.loadData("personajes"))?.people : null;
    if (my !== token) return; // the game was closed meanwhile
    const today = saved.today?.day === day ? saved.today : null;
    game = {
      day, cell,
      guesses: (today?.guesses || []).filter(isLand).slice(0, P.MAX_GUESSES),
      clues: Math.max(1, Math.min(P.CLUES.length, today?.clues | 0)),
      list: P.buildClues({ w, lenses: app.lensById, people, names }, cell),
    };
    render();
    if (now().over) reveal();
    app.requestDraw();
  }

  app.on("mapclick", (ev) => {
    if (app.mode !== MODE || (game && now().over)) return false; // a finished game lets the map open its panels
    if (game) guess(ev.cell);
    return true;
  });

  function persist() {
    saved = { ...loadSaved(), today: { day: game.day, guesses: game.guesses, clues: game.clues } };
    save(saved);
  }

  function guess(cell) {
    if (!isLand(cell)) return app.ui.toast(t("game.notLand"));
    if (game.guesses.includes(cell)) return app.ui.toast(t("game.again"));
    game.guesses.push(cell);
    const s = now();
    if (!s.won) game.clues = Math.min(P.CLUES.length, Math.max(game.clues, game.guesses.length + 1));
    persist();
    if (s.over) {
      saved = { ...saved, stats: P.recordResult(saved.stats, game.day, s.won) };
      save(saved);
      reveal();
    }
    render();
    app.requestDraw();
  }

  function moreClue() {
    if (!game || now().over || game.clues >= P.CLUES.length) return;
    game.clues++;
    persist();
    render();
    dock?.querySelector(`[data-clue="${game.clues - 1}"]`)?.scrollIntoView({ block: "nearest" });
  }

  // The answer flies into view with its outline and its map tooltip.
  function reveal() {
    const x = w.grid.cx(game.cell), y = w.grid.cy(game.cell);
    mark = { cells: new Set([game.cell]) };
    app.setHighlight(mark);
    app.flyTo(x, y, Math.max(app.cam.scale, ANSWER_SCALE), 900);
    const my = token, until = performance.now() + 4000;
    const tip = () => {
      if (my !== token) return;
      if (app.cam.moving) return performance.now() < until && setTimeout(tip, 150); // once the flight lands
      const [sx, sy] = app.cam.toScreen(x, y);
      showCellTooltip(sx, sy, w, game.cell, app.state.lens, app.state.showResources);
    };
    setTimeout(tip, 950);
  }

  // --- the dock ---------------------------------------------------------------------------------------------------
  function shareUrl() {
    const c = country();
    const lang = c.data_lang && c.lang !== c.data_lang ? `&lang=${c.lang}` : "";
    return `https://${c.site_url}/#${HASH_KEY}${lang}`;
  }

  function render() {
    if (!dock || !game) return;
    const s = now();
    const shown = s.over ? P.CLUES.length : game.clues;
    const clues = game.list.map((c, k) => {
      const n = `<span class="gm-n">${esc(t("game.clue", { n: k + 1 }))}</span>`;
      return k < shown ? `
      <li class="gm-clue" data-clue="${k}"><h3>${n} ${esc(c.title)}</h3>
        <dl>${c.facts.map((f) => `<div><dt>${esc(f.label)}</dt><dd>${esc(f.value)}</dd></div>`).join("")}</dl></li>`
      : `<li class="gm-clue locked" aria-hidden="true"><h3>${n}</h3></li>`;
    }).join("");
    const guesses = game.guesses.map((g, k) => {
      const km = s.kms[k], prev = s.kms[k - 1];
      const trend = k && km > P.HIT_KM ? ` · ${esc(t(km < prev ? "game.warmer" : "game.colder"))}` : "";
      return `<li><span class="gm-sq" aria-hidden="true">${P.square(km)}</span>${esc(t("game.guess", {
        place: placeOf(g), km: t("game.km", { n: int(km) }), arrow: P.arrow(w.grid, g, game.cell) }))}${trend}</li>`;
    }).join("");
    dock.innerHTML = `
      <header class="gm-head"><h2>${esc(t("game.title"))} <span class="gm-day">${esc(t("game.day", { n: game.day }))}</span></h2>
        <button type="button" class="icon-btn gm-close" data-close aria-label="${esc(t("game.close"))}">✕</button></header>
      ${game.guesses.length ? "" : `<p class="gm-rules muted">${esc(t("game.rules", { max: P.MAX_GUESSES }))}</p>`}
      ${s.over ? end(s) : ""}
      ${guesses ? `<h3 class="gm-sub">${esc(t("game.guesses"))} <span class="muted">${game.guesses.length}/${P.MAX_GUESSES}</span></h3><ol class="gm-guesses">${guesses}</ol>` : ""}
      ${s.over ? "" : `<div class="gm-actions">
        <button type="button" class="btn gm-more"${game.clues >= P.CLUES.length ? " disabled" : ""}>${esc(t("game.moreClue", { cost: P.CLUE_COST }))}</button>
        <p class="gm-prompt">${esc(t("game.prompt"))}</p></div>`}
      <ol class="gm-clues">${clues}</ol>`;
    dock.querySelector("[data-close]").onclick = () => app.setMode(null);
    const more = dock.querySelector(".gm-more");
    if (more) more.onclick = moreClue;
    const copy = dock.querySelector(".gm-copy");
    if (copy) copy.onclick = async () => app.ui.toast(t((await copyText(text(s))) ? "game.copied" : "game.copyFailed"));
    const native = dock.querySelector(".gm-native");
    if (native) native.onclick = () => navigator.share({ text: text(s) }).catch(() => {});
  }

  const text = (s) => P.shareText({ day: game.day, kms: s.kms, won: s.won, clues: s.clues, url: shareUrl() });

  function end(s) {
    const st = saved.stats || P.NO_STATS;
    const points = t("game.points", { n: P.score(s.best, s.clues) });
    return `<section class="gm-end">
      <p class="gm-verdict">${esc(s.won ? t("game.won", { km: t("game.km", { n: int(s.best) }) }) : t("game.lost"))}</p>
      <p class="gm-answer">${esc(t("game.answer", { place: placeOf(game.cell) }))}</p>
      <p>${esc(t("game.result", { points, tries: s.kms.length, max: P.MAX_GUESSES, clues: s.clues, cluesMax: P.CLUES.length }))}</p>
      <p class="muted">${esc(t("game.stats", { played: st.played, won: st.won, streak: P.currentStreak(st, game.day), best: st.best }))}</p>
      <pre class="gm-share">${esc(text(s))}</pre>
      <div class="gm-buttons"><button type="button" class="btn gm-copy">${esc(t("game.copy"))}</button>
        ${typeof navigator.share === "function" ? `<button type="button" class="btn gm-native">${esc(t("game.share"))}</button>` : ""}</div>
      <p class="muted">${esc(t("game.next"))}</p></section>`;
  }
}
