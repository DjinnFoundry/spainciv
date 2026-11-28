// Great people through time, "¿Quién vivía en {año}?" / "Who was alive in {year}?", on a map whose data has
// personajes.json with years of life (Spain; DECISIONS E105, A35).
//
//   lenses "great_people_year" (people alive per hex, the ramp and fixed domain of great_people, so a colour is the
//     same count in every year; a hex with nobody alive is grey, not the colour of one) and "great_people_year_kind"
//     (the trade with most people alive, the categories of great_people_kind, the legend showing only those with
//     someone alive), after great_people_kind in the picker; their names carry the year
//   mode "timeline" (app/lensPanel.js: opens and closes with either lens): the left dock with the year, a strip of
//     people alive per decade, a slider, steps by decade or century, play, the view switch and the most famous people
//     alive; on phones, where the dock is a sheet over the legend, the panel carries the colour key of the lens on
//     (lensPanel.panelKey: the count's ramp, or the swatches of the trades that lead some hex that year, the legend's
//     hide_empty rule)
//   URL hash: #lens=great_people_year&anio=1000, signed as people write years (anio=-201 = 201 BC, no year 0);
//     no anio (or one that is not a year) = the download year
//   overlay "timeline-dots": while the hexes are too small to read, a dot on each hex with someone alive, in its lens
//     colour and bigger with more people, so a year with a few dozen people still shows where they are
// personajes.json is loaded the first time the timeline opens; the year rules live in lifespan.js. A year change
// repaints with refreshLens() only (A18 and A26 stay intact); play adds no history entries.
import { country } from "../../app/country.js";
import { lensPanel, panelHead, panelKey } from "../../app/lensPanel.js";
import { lang, t } from "../../i18n.js";
import { esc, int } from "../../format.js";
import { namesFrom } from "../../ui/lenses.js";
import { flyToCells } from "../../app/flyToCells.js";
import * as L from "./lifespan.js";

const COUNT = "great_people_year";
const KIND = "great_people_year_kind";
const MODE = "timeline";
const HASH_KEY = "anio";
const FILE = "personajes";
const TICK_MS = { 10: 400, 100: 1000 }; // play: one step per tick
const PLAY_FROM = 10; // play from the end starts again at the first decade with this many people alive
const PAGE = 100; // PageUp / PageDown on the slider
const TOP = 10; // "the most famous" list
const FLY_SCALE = 2.4; // css px per km at most when a person's hex flies into view
const DOT = { min: 3, per: 1.2, max: 9 }; // dot radius in css px: min + per × log2(people), at most max

export function install(app) {
  const base = app.lensById.get("great_people"), baseKind = app.lensById.get("great_people_kind");
  if (!country().data?.includes(FILE) || !base || !baseKind) return;
  const owner = app.w.raw.owner;
  const empty = () => new Array(owner.length).fill(null);
  const shared = (b) => ({ group: b.group, icon: b.icon, emoji: b.emoji, source: b.source, higher_is: b.higher_is,
    scale: b.scale, domain: [...b.domain], ramp: b.ramp, format: b.format });
  // No names_from: main.js loadNames would put every person's names and labels on the lens, over the year's.
  const countLens = { ...shared(base), id: COUNT, name: t("timeline.lens.name"), unit: base.unit,
    description: t("timeline.lens.desc"), values: empty() };
  const kindLens = { ...shared(baseKind), id: KIND, name: t("timeline.kind.name"), unit: t("timeline.kindUnit"),
    description: t("timeline.kind.desc"), categories: baseKind.categories, hide_empty: true, values: empty() };
  app.addLens(countLens, { after: baseKind.id });
  app.addLens(kindLens, { after: COUNT });
  const ours = (l) => l === countLens || l === kindLens;

  let doc = null, P = null, names = null, span = null, decades = null, playStart = 0;
  let year = null; // the year on screen (null until the data is in)
  let committed = null; // the year in the URL: changed by a manual change, never by play (null = the download year)
  let step = 10;
  let playing = false, timer = 0, raf = 0;
  let el = {}, mark = null, token = 0;

  // --- words -----------------------------------------------------------------------------------------------------
  const yearText = (y) => { const h = L.historical(y); return h.bc ? t("timeline.bc", { n: h.n }) : String(h.n); };
  const centuryText = (y, full = false) => {
    const { c, bc } = L.century(y);
    const key = full ? (bc ? "timeline.centuryFullBc" : "timeline.centuryFull") : bc ? "timeline.centuryBc" : "timeline.century";
    return t(key, { c: lang() === "es" ? L.roman(c) : L.ordinal(c) });
  };

  // --- the lenses ------------------------------------------------------------------------------------------------
  let alive = 0, approx = 0, lived = []; // lived: [cell, people] of each hex with someone alive
  function paint(refresh = true) {
    const layer = L.yearLayer(P, owner.length, L.aliveIn(P, year));
    ({ alive, approx } = layer);
    lived = [];
    layer.count.forEach((n, c) => n && lived.push([c, n]));
    const y = yearText(year), none = t("timeline.none", { year: y });
    Object.assign(countLens, { values: layer.count, labels: layer.labels, names, null_label: none,
      name: t("timeline.lens.nameYear", { year: y }) });
    Object.assign(kindLens, { values: layer.kind, labels: layer.labels, names, null_label: none,
      name: t("timeline.kind.nameYear", { year: y }) });
    if (refresh && ours(app.state.lens)) app.refreshLens();
  }

  // Drawn every frame over the cached map (like the game's guesses), so a year change never repaints the static map
  // for it; a hex whose dot would be smaller than the hex itself is left to the lens colour.
  const dots = {
    id: "timeline-dots", z: 40,
    draw(ctx, cam) {
      const g = app.w.grid, s = cam.scale, colors = app.w.colors;
      if (!ours(app.state.lens) || !colors) return;
      if (DOT.max <= g.R * s) return; // zoomed in: every hex reads by itself
      const hw = cam.w / 2 / s + DOT.max / s, hh = cam.h / 2 / s + DOT.max / s;
      ctx.lineWidth = 1 / s;
      ctx.strokeStyle = "rgba(12,9,20,.9)";
      for (const [c, n] of lived) {
        const r = Math.min(DOT.max, DOT.min + DOT.per * Math.log2(n)), x = g.cx(c), y = g.cy(c);
        if (r <= g.R * s || Math.abs(x - cam.x) > hw || Math.abs(y - cam.y) > hh) continue;
        ctx.beginPath();
        ctx.arc(x, y, r / s, 0, 2 * Math.PI);
        ctx.fillStyle = colors[c];
        ctx.fill();
        ctx.stroke();
      }
    },
  };
  let offDots = null;

  const fromHash = () => { const l = app.lensById.get(app.hash.value("lens")); return ours(l) ? l : null; };

  // Before the year's panel is built: its head (so the ✕ is there in every state) and one line.
  const message = (dock, key) => {
    dock.innerHTML = `${panelHead(t("timeline.lens.name"), t("timeline.close"))}<p class="muted">${esc(t(key))}</p>`;
  };

  // An explicit label: paint() puts the year in the lenses' names, and lensPanel's default would read the first lens's.
  const panel = lensPanel(app, [countLens, kindLens], {
    mode: MODE, label: t("timeline.lens.name"),
    open(dock) {
      message(dock, "timeline.loading");
      document.addEventListener("visibilitychange", onVisibility);
      offDots = app.registerOverlay(dots);
      load(++token);
    },
    close() {
      token++;
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
      offDots?.();
      offDots = null;
      if (mark && app.state.highlight === mark) app.setHighlight(null);
      mark = null;
      el = {};
      committed = null; // opened again from the picker, the timeline starts at the download year
      if (doc && year !== span.max) {
        year = span.max;
        paint(false); // the picker names the lenses with the year they will open at; the lens is leaving, no repaint
      }
    },
  });
  app.on("lens", (l) => { if (ours(l)) updateView(); }); // Cuántos / Por oficio follow the lens

  async function load(my) {
    const data = doc || await app.loadData(FILE).catch(() => null);
    if (my !== token) return; // closed meanwhile
    const dock = panel.dock;
    if (!data?.people) return message(dock, "timeline.loadError");
    if (!data.timeline || !data.people.some((p) => p.life)) return message(dock, "timeline.noDates");
    if (!doc) {
      doc = data;
      P = L.pack(doc.people, doc.categories.length);
      names = namesFrom(doc, owner.length).names;
      span = L.range(P, doc.timeline.until);
      decades = L.perDecade(P, span.min, span.max);
      const i = decades.counts.findIndex((c) => c >= PLAY_FROM);
      playStart = i < 0 ? span.min : Math.max(span.min, decades.base + 10 * i);
    }
    year = committed == null ? span.max : clamp(committed);
    build();
    paint();
    render();
  }

  const clamp = (y) => Math.min(span.max, Math.max(span.min, y));

  /** Show year y; `commit` (a manual change) also puts it in the URL, which adds a history entry. */
  function setYear(y, commit = false) {
    if (doc) y = clamp(y);
    if (commit) {
      committed = y;
      app.hash.update();
    }
    if (y === year || !doc) return;
    year = y;
    if (mark && app.state.highlight === mark) app.setHighlight(null);
    mark = null;
    paint();
    render();
  }

  // Registered after the panel, so a link's lens (applied in lensPanel's microtask) is on before the year.
  // set() runs on load and on Back / Forward. A hash with one of the lenses and no year (or one that is not a year)
  // means the download year; with neither a year nor one of the lenses the lens key decides (no lens = no timeline).
  app.hash.register(HASH_KEY, {
    get: () => (app.mode === MODE && committed != null ? L.urlYear(committed) : null),
    set(v) {
      const y = L.parseYear(v, -Infinity, Infinity);
      if (y == null && !fromHash()) return;
      stop();
      committed = y == null ? null : doc ? clamp(y) : y;
      if (doc) setYear(committed ?? span.max);
      if (app.mode !== MODE) app.setMode(MODE);
    },
  });

  // --- play ------------------------------------------------------------------------------------------------------
  function play() {
    if (playing || !doc) return;
    playing = true;
    if (year >= span.max) setYear(playStart);
    afterFrames();
    render();
  }
  function stop() {
    if (!playing) return false;
    playing = false;
    clearTimeout(timer);
    cancelAnimationFrame(raf);
    render();
    return true;
  }
  function pause() {
    if (stop()) setYear(year, true);
  }
  // Never queue a tick before the last frame is on screen: two animation frames after the repaint, then the wait.
  function afterFrames() {
    raf = requestAnimationFrame(() => (raf = requestAnimationFrame(() => (timer = setTimeout(tick, TICK_MS[step])))));
  }
  function tick() {
    if (!playing) return;
    setYear(L.next(year, step, span.min, span.max));
    if (year >= span.max) pause();
    else afterFrames();
  }
  function onVisibility() {
    if (document.hidden) pause();
  }

  // --- a person on the map ---------------------------------------------------------------------------------------
  function show(k) {
    mark = flyToCells(app, [P.cell[k]], FLY_SCALE);
    panel.dock?.querySelectorAll(".dk-item[aria-current]").forEach((b) => b.removeAttribute("aria-current"));
    panel.dock?.querySelector(`.dk-item[data-k="${k}"]`)?.setAttribute("aria-current", "true");
  }

  // --- the dock: built once per opening, then updated in place (a slider being dragged keeps its focus) -----------
  function build() {
    const dock = panel.dock;
    const top = Math.max(...decades.counts);
    const h = (c) => (c ? Math.log1p(c) / Math.log1p(top) : 0);
    const bars = decades.counts.map((c, i) => c ? `<rect x="${i}" y="${(1 - h(c)) * 40}" width="1" height="${h(c) * 40}"/>` : "").join("");
    const meta = doc.timeline, cutoff = meta.until - meta.max_life;
    const left = meta.left_out, out = left.no_birth + left.no_death + left.inconsistent;
    const btn = (cls, label, text) => `<button type="button" class="tl-btn ${cls}" aria-label="${esc(label)}" title="${esc(label)}">${text}</button>`;
    dock.innerHTML = `
      ${panelHead("", t("timeline.close"))}
      <p class="tl-year"><b class="tl-y"></b> <span class="tl-c"></span></p>
      <div class="tl-strip">
        <svg viewBox="0 0 ${decades.counts.length} 40" preserveAspectRatio="none" role="img"
          aria-label="${esc(t("timeline.histogram", { from: yearText(span.min), to: yearText(span.max) }))}">${bars}<line class="tl-now" y1="0" y2="40"/></svg>
        <span class="tl-scale muted">${esc(t("timeline.logScale"))}</span>
      </div>
      <input type="range" class="tl-slider" min="${span.min}" max="${span.max}" step="1" aria-label="${esc(t("timeline.year"))}">
      <div class="tl-controls">
        ${btn("tl-prev", "", "‹")}
        <button type="button" class="tl-btn tl-play" aria-pressed="false"></button>
        ${btn("tl-next", "", "›")}
        <span class="tl-seg" role="group" aria-label="${esc(t("timeline.step"))}">
          <button type="button" class="tl-btn" data-step="10">${esc(t("timeline.step.decade"))}</button><button type="button" class="tl-btn" data-step="100">${esc(t("timeline.step.century"))}</button></span>
      </div>
      <div class="tl-seg tl-view" role="group" aria-label="${esc(t("timeline.view"))}">
        <button type="button" class="tl-btn" data-lens="${COUNT}">${esc(t("timeline.view.count"))}</button><button type="button" class="tl-btn" data-lens="${KIND}">${esc(t("timeline.view.kind"))}</button></div>
      ${panelKey()}
      <p class="tl-sum"></p>
      <h3 class="tl-h3">${esc(t("timeline.famous"))}</h3>
      <ol class="dk-list tl-famous"></ol>
      <p class="tl-note muted">${esc(t("timeline.caption"))}</p>
      <p class="tl-note muted">${esc(t("timeline.rules", { approx: int(meta.approximate), until: meta.until, cutoff, max: meta.max_life, next: meta.max_life + 1, longer: int(meta.longer) }))}</p>
      <p class="tl-note muted">${esc(t("timeline.leftOut", { n: out, count: int(out), birth: int(left.no_birth), death: int(left.no_death), bad: int(left.inconsistent) }))}</p>`;
    const q = (s) => dock.querySelector(s);
    el = { title: q(".lens-panel-head h2"), y: q(".tl-y"), c: q(".tl-c"), now: q(".tl-now"), svg: q(".tl-strip svg"), slider: q(".tl-slider"),
      prev: q(".tl-prev"), next: q(".tl-next"), play: q(".tl-play"), sum: q(".tl-sum"), famousHead: q(".tl-h3"), famous: q(".tl-famous") };
    el.slider.oninput = () => { stop(); setYear(+el.slider.value); };
    el.slider.onchange = () => setYear(+el.slider.value, true);
    el.slider.onkeydown = (e) => {
      const d = { PageUp: PAGE, PageDown: -PAGE }[e.key];
      if (!d) return;
      e.preventDefault();
      stop();
      setYear(year + d, true);
    };
    el.svg.onclick = (e) => {
      const r = el.svg.getBoundingClientRect();
      const i = Math.floor(((e.clientX - r.left) / r.width) * decades.counts.length);
      stop();
      setYear(decades.base + 10 * Math.max(0, Math.min(decades.counts.length - 1, i)), true);
    };
    el.prev.onclick = () => { stop(); setYear(L.prev(year, step, span.min, span.max), true); };
    el.next.onclick = () => { stop(); setYear(L.next(year, step, span.min, span.max), true); };
    el.play.onclick = () => (playing ? pause() : play());
    dock.querySelectorAll("[data-step]").forEach((b) => (b.onclick = () => { step = +b.dataset.step; render(); }));
    dock.querySelectorAll("[data-lens]").forEach((b) => (b.onclick = () => app.setLens(b.dataset.lens)));
    el.famous.onclick = (e) => {
      const b = e.target.closest("button[data-k]");
      if (b) show(+b.dataset.k);
    };
  }

  // The view switch and the phone key follow the lens (and render() calls this after each year's paint).
  function updateView() {
    const l = app.state.lens;
    panel.dock?.querySelectorAll("[data-lens]").forEach((b) => b.setAttribute("aria-pressed", String(l?.id === b.dataset.lens)));
    if (el.slider && ours(l)) panel.updateKey(l, l === kindLens ? kindLens.unit[0].toUpperCase() + kindLens.unit.slice(1) : t("timeline.key.count"));
  }

  function render() {
    const dock = panel.dock;
    if (!dock || !doc || !el.slider) return;
    const y = yearText(year);
    el.title.textContent = t("timeline.title", { year: y });
    el.y.textContent = y;
    el.c.textContent = `· ${centuryText(year)}`;
    el.slider.value = String(year);
    el.slider.setAttribute("aria-valuetext", t("timeline.valuetext", { year: y, century: centuryText(year, true), n: alive, count: int(alive) }));
    const x = (Math.floor(year / 10) * 10 - decades.base) / 10 + 0.5;
    el.now.setAttribute("x1", x);
    el.now.setAttribute("x2", x);
    const unit = step === 10 ? "decade" : "century";
    const prevLabel = unit === "decade" ? t("timeline.prev.decade") : t("timeline.prev.century");
    const nextLabel = unit === "decade" ? t("timeline.next.decade") : t("timeline.next.century");
    el.prev.setAttribute("aria-label", prevLabel);
    el.prev.title = prevLabel;
    el.next.setAttribute("aria-label", nextLabel);
    el.next.title = nextLabel;
    el.prev.disabled = year <= span.min;
    el.next.disabled = year >= span.max;
    el.play.setAttribute("aria-pressed", String(playing));
    el.play.innerHTML = `<span aria-hidden="true">${playing ? "❚❚" : "▶"}</span> ${esc(playing ? t("timeline.pause") : t("timeline.play"))}`;
    dock.querySelectorAll("[data-step]").forEach((b) => b.setAttribute("aria-pressed", String(+b.dataset.step === step)));
    updateView();
    el.sum.setAttribute("aria-live", playing ? "off" : "polite");
    el.sum.textContent = t("timeline.summary", { n: alive, count: int(alive), year: y, total: int(P.dated) })
      + (approx ? " " + t("timeline.approx", { n: approx, count: int(approx) }) : "");
    const famous = L.famous(P, year, TOP);
    el.famousHead.hidden = !famous.length; // a year with nobody alive: the summary says so, no heading over nothing
    el.famous.innerHTML = famous.map((k) => {
      const p = doc.people[k];
      return `<li><button type="button" class="dk-item" data-k="${k}" title="${esc(t("timeline.show"))}">
        <b class="dk-name">${esc(p.name)}</b><span class="dk-when">${esc(p.note || "")}</span><span class="dk-where">${esc(p.place)}</span></button></li>`;
    }).join("");
  }
}
