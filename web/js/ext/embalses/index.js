// Spain's reservoirs week by week since 1988, on a map whose data has embalses.json (Spain).
//
//   lens "embalses" in the lens picker, after the wildfires lens: each peninsular hex takes its basin's fill in the
//     chosen week (Σ water stored ÷ Σ capacity of the reservoirs the Boletín Hidrológico reported that week)
//   static layer "reservoirs" (z 65, only with the lens): a ring per reservoir placed that week, its arc the share
//     of its capacity it holds, larger reservoirs drawn first so the small ones stay on top
//   mode "embalses" (opens and closes with the lens): the left dock with the week control, Spain's line since 1988,
//     the basins from the driest and a clicked reservoir's own line
//   URL hash: #lens=embalses&semana=1995-11-07
// embalses.json loads the first time the lens opens; the weekly matrix (embalses_semanas.json) the first time the
// week leaves the latest one or a reservoir is clicked. The series rules live in series.js.
import { country } from "../../app/country.js";
import { t } from "../../i18n.js";
import { esc, int, pct } from "../../format.js";
import * as S from "./series.js";

const LENS = "embalses";
const MODE = "embalses";
const LAYER = "reservoirs";
const HASH_KEY = "semana";
const FILE = "embalses", WEEKS_FILE = "embalses_semanas";
const PLAY_MS = 800; // a year a step while "year by year" plays
const PAINT_GAP_MS = 120; // while the slider drags, the map repaints at most this often
const FLY_SCALE = 1.2; // css px per km at most when a basin flies into view
// Empty to full: dry earth to water, lightness rising all the way (DECISIONS E85).
const RAMP = ["#593215", "#774e23", "#82734b", "#689693", "#6ab0ca", "#8ac7ea", "#bbe0fc"];
const CHART = { w: 328, h: 120, top: 8, bottom: 18, left: 28, right: 6 };

export function install(app) {
  if (!country().data?.includes(FILE)) return;
  const fires = app.lensById.get("wildfires");
  const n = app.w.grid.size;
  const fmtDate = (iso, opts = { day: "numeric", month: "long", year: "numeric" }) =>
    new Intl.DateTimeFormat(country().locale, { ...opts, timeZone: "UTC" }).format(new Date(iso + "T00:00:00Z"));
  const weekText = (i) => t("embalses.week", { date: fmtDate(doc.dates[i]) });
  const hm3 = (v) => (v == null ? "–" : int(v));

  const lens = {
    id: LENS, group: fires?.group ?? "hazards", name: t("embalses.lens.name"), icon: "r-hydro", emoji: "💧",
    format: "pct", scale: "linear", domain: [0, 1], higher_is: "good", unit: "", source: "boletin_hidrologico",
    description: t("embalses.lens.desc"), ramp: RAMP, values: new Array(n).fill(null),
    null_label: t("embalses.lens.none"),
  };
  app.addLens(lens, { after: fires?.id });

  let doc = null; // embalses.json once loaded
  let weeks = null, weeksLoad = null; // embalses_semanas.json, its load
  let week = null, wanted = null; // the week shown; a week the URL asked for before the data arrived
  let picked = null; // the clicked reservoir's index
  let dock = null, mark = null, token = 0, leaving = false;
  let order = []; // reservoirs drawn largest first
  let rings = []; // the week's rings: [{k, x, y, r, arc}], in drawing order
  let paintTimer = 0, paintRaf = 0, lastPaint = 0, play = null;

  const latest = () => doc.dates.length - 1;

  // --- the lens and the rings --------------------------------------------------------------------------------------
  function paint() {
    lastPaint = performance.now();
    const names = doc.basins.map((b) => t("embalses.hexTip", {
      basin: b.name, actual: hm3(b.actual[week]), capacity: hm3(b.capacity[week]), week: weekText(week),
    }));
    const labels = new Array(n).fill(null);
    doc.basins.forEach((b, k) => b.cells.forEach((c) => (labels[c] = [k])));
    Object.assign(lens, { values: S.hexValues(doc.basins, week, n), labels, names });
    const now = S.reporting(doc.reservoirs, weeks, week, latest());
    const byK = new Map((now || []).map((r) => [r.k, r]));
    rings = [];
    for (const k of order) {
      const r = doc.reservoirs[k], at = byK.get(k);
      if (!at || r.x == null) continue;
      rings.push({ k, x: r.x, y: r.y, r: S.ringRadius(at.capacity), arc: S.ringArc(at.actual, at.capacity), at });
    }
    if (app.state.lens === lens) app.refreshLens();
    else app.requestDraw();
  }

  // Dock text and chart cursor follow the slider at once; the map at most every PAINT_GAP_MS, once a frame.
  function schedulePaint(final = false) {
    clearTimeout(paintTimer);
    cancelAnimationFrame(paintRaf);
    if (final) return paint();
    const wait = Math.max(0, PAINT_GAP_MS - (performance.now() - lastPaint));
    paintTimer = setTimeout(() => (paintRaf = requestAnimationFrame(paint)), wait);
  }

  const ringLayer = {
    id: LAYER, z: 65,
    visible: () => app.state.lens === lens && !!doc && rings.length > 0,
    sig: () => `${week}:${picked ?? ""}:${weeks ? 1 : 0}`,
    draw(ctx, vp, w, o) {
      const s = vp.s, R = w.grid.R, pad = 16 / s;
      const { r0, r1, c0, c1 } = o.range;
      const x0 = (c0 - 1) * Math.sqrt(3) * R - pad, x1 = (c1 + 2) * Math.sqrt(3) * R + pad;
      const y0 = (r0 - 1) * 1.5 * R - pad, y1 = (r1 + 1) * 1.5 * R + pad;
      ctx.lineCap = "butt";
      for (const g of rings) {
        if (g.x < x0 || g.x > x1 || g.y < y0 || g.y > y1) continue;
        const rr = g.r / s;
        ctx.beginPath();
        ctx.arc(g.x, g.y, rr, 0, Math.PI * 2);
        ctx.lineWidth = 3.2 / s;
        ctx.strokeStyle = "rgba(8,12,18,0.7)";
        ctx.stroke();
        if (g.arc && g.arc.frac > 0) {
          ctx.beginPath();
          ctx.arc(g.x, g.y, rr, -Math.PI / 2, -Math.PI / 2 + g.arc.frac * Math.PI * 2);
          ctx.lineWidth = 1.8 / s;
          ctx.strokeStyle = "#e9f5ff";
          ctx.stroke();
        }
        if (g.arc?.over) { // a small outer tick at the top: more than the capacity
          ctx.beginPath();
          ctx.moveTo(g.x, g.y - rr - 1.4 / s);
          ctx.lineTo(g.x, g.y - rr - 4.4 / s);
          ctx.lineWidth = 1.6 / s;
          ctx.strokeStyle = "#e9f5ff";
          ctx.stroke();
        }
        if (g.k === picked) {
          ctx.beginPath();
          ctx.arc(g.x, g.y, rr + 3 / s, 0, Math.PI * 2);
          ctx.lineWidth = 1.5 / s;
          ctx.strokeStyle = "#ecd08e";
          ctx.stroke();
        }
      }
    },
    hit(x, y, Rpx) {
      const s = Rpx / app.w.grid.R;
      for (let j = rings.length - 1; j >= 0; j--) { // the small ones are on top
        const g = rings[j];
        if (Math.hypot(x - g.x, y - g.y) <= (g.r + 3) / s) return g;
      }
      return null;
    },
    tooltip(g) {
      const r = doc.reservoirs[g.k], { actual, capacity } = g.at;
      const amount = g.arc?.over
        ? t("embalses.tip.over", { actual: hm3(actual), capacity: hm3(capacity) })
        : t("embalses.tip.amount", { actual: hm3(actual), capacity: hm3(capacity), pct: pct(actual / capacity, 0) });
      const lines = [`<b>${esc(r.name)}</b> <span class="muted">· ${esc(doc.basins[r.basin].name)}</span>`, esc(amount),
        `<span class="muted">${esc(t(`embalses.use.${r.use}`))} · ${esc(weekText(week))}</span>`];
      if (r.placed === "wikidata") lines.push(`<span class="muted">${esc(t("embalses.tip.wikidata"))}</span>`);
      lines.push(`<span class="muted">${esc(t("embalses.tip.click"))}</span>`);
      return lines.join("<br>");
    },
  };
  app.registerStaticLayer(ringLayer);

  app.on("mapclick", (ev) => {
    if (app.mode !== MODE || ev.layer !== LAYER || !ev.item) return false;
    pick(ev.item.k);
    return true;
  });

  // --- the lens and the mode come and go together -------------------------------------------------------------
  app.on("lens", (l) => {
    if (l === lens) {
      if (app.mode !== MODE) app.setMode(MODE);
    } else if (app.mode === MODE && !leaving) app.setMode(null);
  });

  app.registerMode(MODE, {
    enter() {
      dock = app.ui.dock("left", { width: 360, label: t("embalses.lens.name") });
      dock.classList.add("embalses-dock");
      dock.innerHTML = `<p class="muted">${esc(t("embalses.loading"))}</p>`;
      if (app.state.lens !== lens) app.setLens(lens);
      open(++token);
    },
    exit() {
      leaving = true;
      try {
        token++;
        stop();
        clearTimeout(paintTimer);
        cancelAnimationFrame(paintRaf);
        if (mark && app.state.highlight === mark) app.setHighlight(null);
        mark = null;
        picked = null;
        dock?.classList.remove("embalses-dock");
        app.ui.undock("left");
        dock = null;
        if (app.state.lens === lens) app.setLens(null);
      } finally {
        leaving = false;
      }
    },
  });

  async function open(my) {
    const data = await app.loadData(FILE).catch(() => null);
    if (my !== token) return; // closed meanwhile
    if (!data?.dates?.length) {
      dock.innerHTML = `<p class="muted">${esc(t("embalses.loadError"))}</p>`;
      return;
    }
    if (!doc) {
      doc = data;
      order = doc.reservoirs.map((r, k) => k).sort((a, b) => (doc.reservoirs[b].capacity ?? 0) - (doc.reservoirs[a].capacity ?? 0));
      doc.extremes = S.extremes(doc.basins);
      doc.line = doc.dates.map((d, i) => S.national(doc.basins, i).pct);
    }
    const w = wanted != null ? S.parseWeek(wanted, doc.dates) : null;
    wanted = null;
    week = w ?? week ?? latest();
    if (week !== latest()) needWeeks();
    build();
    update();
    paint();
    app.hash.update();
  }

  /** Load the weekly matrix once, then repaint what needs it (rings off the latest week, a reservoir's line). */
  function needWeeks() {
    if (weeksLoad) return weeksLoad;
    weeksLoad = app.loadData(WEEKS_FILE).then((d) => {
      if (!d?.actual?.length) {
        weeksLoad = null; // a later step may try again
        return null;
      }
      weeks = d;
      if (doc && app.mode === MODE) {
        paint();
        update();
      }
      return d;
    }, () => (weeksLoad = null));
    return weeksLoad;
  }

  function setWeek(i, { final = true, keepPlay = false } = {}) {
    if (!doc || i == null || i < 0 || i >= doc.dates.length) return;
    if (!keepPlay) stop();
    if (i !== week) {
      week = i;
      if (week !== latest()) needWeeks();
      update();
      app.hash.update();
    }
    schedulePaint(final);
  }

  app.hash.register(HASH_KEY, {
    get: () => (app.mode === MODE && doc && week != null ? doc.dates[week] : null),
    set(v) {
      if (v == null) return; // without the key the lens key decides (no lens = no reservoirs)
      if (doc) {
        const i = S.parseWeek(v, doc.dates);
        if (i == null) return; // anything invalid is ignored
        setWeek(i);
      } else wanted = v;
      if (app.mode !== MODE) app.setMode(MODE);
    },
  });
  // A link with the lens and no week (#lens=embalses) opens the latest week.
  if (app.hash.value("lens") === LENS && app.hash.value(HASH_KEY) == null) app.setLens(lens);

  // --- year by year ---------------------------------------------------------------------------------------------
  // The same week of each year from 1988 to the latest, PLAY_MS a step; any input stops it, and it never starts alone.
  const stopOnInput = (e) => {
    if (e.target?.closest?.("[data-play]")) return;
    stop();
  };
  function start() {
    if (!doc) return;
    const anchor = week, first = +doc.dates[0].slice(0, 4), last = +doc.dates[latest()].slice(0, 4);
    let year = first;
    const step = () => {
      let i = null;
      while (i == null && year <= last) i = S.sameWeekIn(doc.dates, anchor, year++);
      if (i == null) return stop();
      setWeek(i, { keepPlay: true });
      if (year > last) return stop();
      play.timer = setTimeout(step, PLAY_MS);
    };
    play = { timer: 0 };
    for (const ev of ["pointerdown", "keydown", "wheel"]) addEventListener(ev, stopOnInput, { capture: true });
    needWeeks().then(() => play && step());
    syncPlay();
  }
  function stop() {
    if (!play) return;
    clearTimeout(play.timer);
    play = null;
    for (const ev of ["pointerdown", "keydown", "wheel"]) removeEventListener(ev, stopOnInput, { capture: true });
    syncPlay();
  }
  function syncPlay() {
    const b = dock?.querySelector("[data-play]");
    if (!b) return;
    b.setAttribute("aria-pressed", String(!!play));
    b.textContent = play ? `■ ${t("embalses.stop")}` : `▶ ${t("embalses.play")}`;
  }

  // --- a basin, a reservoir -------------------------------------------------------------------------------------
  function highlightBasin(k, fly = false) {
    mark = k == null ? null : { cells: new Set(doc.basins[k].cells) };
    app.setHighlight(mark);
    if (!fly || !mark) return;
    const b = app.highlightBounds(mark);
    if (b) app.fitBounds(b.x0, b.y0, b.x1, b.y1, { maxScale: Math.max(app.cam.scale, FLY_SCALE) });
  }

  function pick(k) {
    picked = k;
    needWeeks();
    update();
    app.requestDraw();
  }

  // --- the dock --------------------------------------------------------------------------------------------------
  function build() {
    if (!dock) return;
    const first = +doc.dates[0].slice(0, 4), last = +doc.dates[latest()].slice(0, 4);
    const years = Array.from({ length: last - first + 1 }, (_, k) => first + k)
      .map((y) => `<option value="${y}">${y}</option>`).join("");
    dock.innerHTML = `
      <header class="em-head"><h2 data-title></h2>
        <button type="button" class="icon-btn em-close" data-close aria-label="${esc(t("embalses.close"))}">✕</button></header>
      <p class="em-prov muted">${esc(t("embalses.provisional"))}</p>
      <div class="em-time">
        <input type="range" class="em-slider" min="0" max="${latest()}" step="1" aria-label="${esc(t("embalses.slider"))}">
        <div class="em-steps">
          <button type="button" class="icon-btn" data-step="-1" aria-label="${esc(t("embalses.prev"))}" title="${esc(t("embalses.prev"))}">◀</button>
          <button type="button" class="icon-btn" data-step="1" aria-label="${esc(t("embalses.next"))}" title="${esc(t("embalses.next"))}">▶</button>
          <label class="em-year"><span class="sr-only">${esc(t("embalses.year"))}</span><select data-year aria-label="${esc(t("embalses.year"))}">${years}</select></label>
          <button type="button" class="em-btn" data-play aria-pressed="false" title="${esc(t("embalses.playTitle", { first, last }))}"></button>
        </div>
        <div class="em-jumps">
          <button type="button" class="em-btn" data-jump="min">${esc(t("embalses.min"))}</button>
          <button type="button" class="em-btn" data-jump="max">${esc(t("embalses.max"))}</button>
          <button type="button" class="em-btn" data-jump="latest">${esc(t("embalses.latest"))}</button>
        </div>
      </div>
      <p class="em-big"><b data-pct></b> <span data-amount></span></p>
      <figure class="em-chart">${chartSvg()}<figcaption class="muted">${esc(t("embalses.chart"))}</figcaption></figure>
      <p class="em-count" data-count></p>
      <h3 class="em-h3">${esc(t("embalses.basins"))}</h3>
      <ol class="em-basins" data-basins></ol>
      <section class="em-res" data-res hidden></section>
      <p class="em-note muted" data-note></p>`;
    dock.querySelector("[data-close]").onclick = () => app.setMode(null);
    const slider = dock.querySelector(".em-slider");
    slider.oninput = () => setWeek(+slider.value, { final: false });
    slider.onchange = () => setWeek(+slider.value);
    slider.onkeydown = (e) => {
      const step = { ArrowRight: 1, ArrowUp: 1, ArrowLeft: -1, ArrowDown: -1 }[e.key];
      let i = null;
      if (step) i = week + step;
      else if (e.key === "PageUp" || e.key === "PageDown") {
        const y = +doc.dates[week].slice(0, 4) + (e.key === "PageUp" ? 1 : -1);
        i = S.sameWeekIn(doc.dates, week, y) ?? (e.key === "PageUp" ? latest() : 0);
      } else if (e.key === "Home") i = 0;
      else if (e.key === "End") i = latest();
      else return;
      e.preventDefault();
      setWeek(Math.max(0, Math.min(latest(), i)));
    };
    dock.querySelectorAll("[data-step]").forEach((b) => (b.onclick = () => setWeek(Math.max(0, Math.min(latest(), week + +b.dataset.step)))));
    dock.querySelector("[data-year]").onchange = (e) => {
      const y = +e.target.value;
      setWeek(S.sameWeekIn(doc.dates, week, y) ?? (y <= first ? 0 : latest()));
    };
    dock.querySelectorAll("[data-jump]").forEach((b) => (b.onclick = () => {
      const j = b.dataset.jump;
      setWeek(j === "latest" ? latest() : doc.extremes[j]);
    }));
    dock.querySelector("[data-play]").onclick = () => (play ? stop() : start());
    syncPlay();
    const svg = dock.querySelector(".em-chart svg");
    svg.onclick = (e) => {
      const box = svg.getBoundingClientRect();
      const x = ((e.clientX - box.left) / box.width) * CHART.w;
      const k = Math.round(((x - CHART.left) / (CHART.w - CHART.left - CHART.right)) * latest());
      setWeek(Math.max(0, Math.min(latest(), k)));
    };
    const list = dock.querySelector("[data-basins]");
    list.onpointerover = (e) => {
      const b = e.target.closest("[data-k]");
      if (b) highlightBasin(+b.dataset.k);
    };
    list.onpointerleave = () => highlightBasin(null);
    list.onclick = (e) => {
      const b = e.target.closest("[data-k]");
      if (b) highlightBasin(+b.dataset.k, true);
    };
    list.onfocusin = (e) => {
      const b = e.target.closest("[data-k]");
      if (b) highlightBasin(+b.dataset.k);
    };
  }

  const cx = (i) => CHART.left + (i / Math.max(1, latest())) * (CHART.w - CHART.left - CHART.right);
  const cy = (p) => CHART.top + (1 - p) * (CHART.h - CHART.top - CHART.bottom);
  function chartSvg() {
    const grid = [0.25, 0.5, 0.75].map((p) => `<line class="em-grid" x1="${CHART.left}" x2="${CHART.w - CHART.right}" y1="${cy(p)}" y2="${cy(p)}"/>
      <text class="em-axis" x="${CHART.left - 4}" y="${cy(p) + 3}" text-anchor="end">${esc(pct(p, 0))}</text>`).join("");
    const d = doc.line.map((p, i) => (p == null ? "" : `${i && doc.line[i - 1] != null ? "L" : "M"}${cx(i).toFixed(1)},${cy(p).toFixed(1)}`)).join("");
    const decades = [];
    for (let i = 0; i < doc.dates.length; i++) {
      const y = +doc.dates[i].slice(0, 4);
      if (y % 10 === 0 && (i === 0 || +doc.dates[i - 1].slice(0, 4) !== y)) decades.push([i, y]);
    }
    const ticks = decades.map(([i, y]) => `<text class="em-axis" x="${cx(i)}" y="${CHART.h - 4}" text-anchor="middle">${y}</text>`).join("");
    return `<svg viewBox="0 0 ${CHART.w} ${CHART.h}" role="img" aria-label="${esc(t("embalses.chart"))}">${grid}${ticks}
      <path class="em-line" d="${d}"/><line class="em-cursor" data-cursor y1="${CHART.top}" y2="${CHART.h - CHART.bottom}"/>
      <circle class="em-dot" data-dot r="3.5"/><path class="em-res-line" data-res-line d=""/></svg>`;
  }

  function update() {
    if (!dock || !doc || !dock.querySelector("[data-title]")) return;
    const q = (sel) => dock.querySelector(sel);
    const date = fmtDate(doc.dates[week]);
    q("[data-title]").textContent = t("embalses.title", { date });
    const slider = q(".em-slider");
    slider.value = String(week);
    slider.setAttribute("aria-valuetext", weekText(week));
    q("[data-year]").value = doc.dates[week].slice(0, 4);
    const nat = S.national(doc.basins, week);
    q("[data-pct]").textContent = nat.pct == null ? "–" : pct(nat.pct, 1);
    q("[data-amount]").textContent = t("embalses.amount", { actual: hm3(nat.actual), capacity: hm3(nat.capacity) });
    const cur = q("[data-cursor]");
    cur.setAttribute("x1", cx(week));
    cur.setAttribute("x2", cx(week));
    const dot = q("[data-dot]");
    dot.setAttribute("cx", cx(week));
    dot.setAttribute("cy", nat.pct == null ? -10 : cy(nat.pct));
    const now = S.reporting(doc.reservoirs, weeks, week, latest());
    q("[data-count]").textContent = now
      ? t("embalses.count", { n: now.length, capacity: hm3(nat.capacity) })
      : t("embalses.loadingWeeks");
    q("[data-basins]").innerHTML = S.basinsByDryness(doc.basins, week).map((k) => {
      const b = doc.basins[k], p = S.basinPct(b, week);
      const label = t("embalses.basin", { actual: hm3(b.actual[week]), capacity: hm3(b.capacity[week]) });
      return `<li><button type="button" class="em-basin" data-k="${k}" title="${esc(t("embalses.basinShow"))}">
        <span class="em-bname">${esc(b.name)}</span><span class="em-bpct">${p == null ? "–" : esc(pct(p, 0))}</span>
        <span class="em-bar"><i style="width:${p == null ? 0 : Math.round(Math.min(1, p) * 100)}%"></i></span>
        <span class="em-bamt muted">${esc(label)}</span></button></li>`;
    }).join("");
    renderNote(now);
    renderReservoir();
  }

  function renderNote(now) {
    const el = dock.querySelector("[data-note]");
    if (!now) {
      el.textContent = "";
      return;
    }
    const off = now.filter((r) => doc.reservoirs[r.k].x == null);
    const wd = now.filter((r) => doc.reservoirs[r.k].placed === "wikidata").map((r) => doc.reservoirs[r.k].name);
    el.textContent = [
      off.length ? t("embalses.unplaced", { n: off.length, hm3: hm3(off.reduce((a, r) => a + r.actual, 0)) }) : "",
      wd.length ? t("embalses.wikidata", { n: wd.length, names: wd.join(", ") }) : "",
    ].filter(Boolean).join(" ");
  }

  function renderReservoir() {
    const el = dock.querySelector("[data-res]"), line = dock.querySelector("[data-res-line]");
    if (picked == null) {
      el.hidden = true;
      line.setAttribute("d", "");
      return;
    }
    const r = doc.reservoirs[picked];
    el.hidden = false;
    const since = r.first == null ? "" : t("embalses.res.span", { first: fmtDate(doc.dates[r.first]), last: fmtDate(doc.dates[r.last]) });
    let now = "";
    if (weeks) {
      const a = weeks.actual[week][picked], c = S.capacityAt(weeks.capacity[picked], week);
      now = a == null ? t("embalses.res.absent") : S.ringArc(a, c)?.over
        ? t("embalses.tip.over", { actual: hm3(a), capacity: hm3(c) })
        : t("embalses.tip.amount", { actual: hm3(a), capacity: hm3(c), pct: pct(a / c, 0) });
      const d = weeks.actual.map((row, i) => {
        const a2 = row[picked], c2 = a2 == null ? null : S.capacityAt(weeks.capacity[picked], i);
        const p = a2 == null || !c2 ? null : Math.min(1.05, a2 / c2);
        return p == null ? "" : `${i && weeks.actual[i - 1][picked] != null ? "L" : "M"}${cx(i).toFixed(1)},${cy(p).toFixed(1)}`;
      }).join("");
      line.setAttribute("d", d);
    } else {
      now = t("embalses.loadingWeeks");
    }
    el.innerHTML = `<h3 class="em-h3">${esc(r.name)} <span class="muted">· ${esc(doc.basins[r.basin].name)}</span>
        <button type="button" class="icon-btn em-res-close" data-unpick aria-label="${esc(t("embalses.res.close"))}">✕</button></h3>
      <p>${esc(now)}</p>
      <p class="muted">${esc(t(`embalses.use.${r.use}`))}${r.placed === "wikidata" ? ` · ${esc(t("embalses.tip.wikidata"))}` : ""}</p>
      <p class="muted">${esc(since)}</p>
      <p class="muted em-legend"><i class="em-key em-key-res"></i>${esc(t("embalses.res.line"))}</p>`;
    el.querySelector("[data-unpick]").onclick = () => {
      picked = null;
      renderReservoir();
      app.requestDraw();
    };
  }
}
