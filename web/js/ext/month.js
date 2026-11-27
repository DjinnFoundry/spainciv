// The month that the fiesta calendar and the climate of the month share: one month per app, kept in the URL as `mes`,
// and the strip of twelve month buttons each of them draws in its panel. Not an extension (it is not in ext/index.js):
// the extensions that show a month import it. Nothing touches the DOM until monthStrip runs, so
// tests/test_month_js.py runs the rest in node.
//
//   const ms = monthState(app)   the app's month state (one per app)
//   ms.month                     the month, 1–12 (this month until a link or a click picks another)
//   ms.set(m)                    pick a month: every page's onMonth(m) runs, then the URL is written
//   ms.page({id, lensIds, fallback, active(), open(), onMonth(m), linkLabel(m)})   a page that shows the month
//   monthLinks(ms, id)           the links from page `id` to the others on the same month ("Clima de enero →"); a
//                                click on one goes through ms.follow(event)
//
// The `mes` key is written while one of the pages is open. A link with `mes` opens the page whose lenses include the
// link's lens (#lens=clima_temp&mes=1), else the fallback page (#mes=8 alone is the fiesta calendar, as it always was);
// a link with a page's lens and no month opens that page on this month (lensPanel does that). When the last open page
// closes, the month goes back to this month: the URL has lost `mes` by then, and a page opened again shows what that
// URL would open.

import { esc } from "../format.js";

const HASH_KEY = "mes";

/** The month (1–12) of a local date. */
export const currentMonth = (date = new Date()) => date.getMonth() + 1;

/** A month from the URL ("8") or null. */
export const parseMonth = (v) => (/^(?:[1-9]|1[0-2])$/.test(String(v)) ? Number(v) : null);

/** A month's name in `locale` ("enero", "ene"). */
export const monthName = (m, locale, month = "long") =>
  new Intl.DateTimeFormat(locale, { month }).format(new Date(2026, m - 1, 1));

/** The page a link with `mes` opens: the one whose lenses include the link's lens, else the fallback page. */
export function pickPage(pages, lens) {
  return pages.find((p) => lens != null && p.lensIds.includes(lens)) ?? pages.find((p) => p.fallback) ?? null;
}

const states = new WeakMap();

export function monthState(app) {
  if (states.has(app)) return states.get(app);
  let month = currentMonth();
  const pages = [];
  const ms = {
    get month() {
      return month;
    },
    set(m) {
      if (m === month) return;
      month = m;
      for (const p of pages) p.onMonth?.(m);
      app.hash.update();
    },
    page(p) {
      pages.push(p);
    },
    others: (id) => pages.filter((p) => p.id !== id),
    /** A click handler for monthLinks: opens the page of the link clicked. */
    follow(e) {
      const id = e.target.closest?.("[data-month-page]")?.dataset.monthPage;
      pages.find((p) => p.id === id)?.open();
    },
  };
  states.set(app, ms);

  // Moving from one page to another (the links) keeps the month; closing the last one forgets it.
  let open = false;
  app.on?.("mode", () => {
    const now = pages.some((p) => p.active());
    if (open && !now) month = currentMonth();
    open = now;
  });

  // The link's lens may belong to a page whose extension is not installed yet: the page is chosen once they all are.
  const whenInstalled = (fn) => {
    if (app.extensions) return fn();
    const off = app.on("extensions", () => {
      off();
      fn();
    });
  };
  app.hash.register(HASH_KEY, {
    get: () => (pages.some((p) => p.active()) ? String(month) : null),
    set(v) {
      const m = parseMonth(v);
      if (m == null) return; // without the key the lens key decides
      ms.set(m);
      whenInstalled(() => {
        const p = pickPage(pages, app.hash.value("lens"));
        if (p && !p.active()) p.open();
      });
    },
  });
  return ms;
}

/**
 * The twelve month buttons in `host` (a radio group; the arrow keys move the month).
 *   month       the month shown as picked
 *   locale      for the month names
 *   label(m)    each button's accessible name and title (the month's name by default)
 *   bar(m)      the height of the month's bar, 0..1, or null for none
 *   onPick(m)   a month was picked
 * A page that re-renders its panel on onPick may replace `host`: the focus then goes to the new strip in host's parent.
 */
export function monthStrip(host, { month, locale, label = (m) => monthName(m, locale), bar = () => null, onPick }) {
  const scope = host.parentElement;
  host.classList.add("ms-strip");
  host.setAttribute("role", "radiogroup");
  host.classList.toggle("ms-bare", Array.from({ length: 12 }, (_, k) => bar(k + 1)).every((h) => h == null)); // no bars: short buttons
  host.innerHTML = Array.from({ length: 12 }, (_, k) => {
    const m = k + 1, on = m === month, h = bar(m), name = esc(label(m));
    return `<button type="button" class="ms-month${on ? " on" : ""}" role="radio" aria-checked="${on}" tabindex="${on ? 0 : -1}"
      data-m="${m}" aria-label="${name}" title="${name}">${h == null ? "" : `<i style="height:${Math.round(Math.max(0, Math.min(1, h)) * 100)}%"></i>`}<span>${esc(monthName(m, locale, "short").replace(/\.$/, ""))}</span></button>`;
  }).join("");
  host.onclick = (e) => {
    const b = e.target.closest("[data-m]");
    if (b) onPick(+b.dataset.m);
  };
  host.onkeydown = (e) => {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
    if (!step) return;
    e.preventDefault();
    const next = ((month - 1 + step + 12) % 12) + 1;
    onPick(next);
    (host.isConnected ? host : scope)?.querySelector(`.ms-month[data-m="${next}"]`)?.focus();
  };
}

/** The links from page `id` to the other pages, on the same month (empty when there are none). */
export function monthLinks(ms, id) {
  const others = ms.others(id);
  if (!others.length) return "";
  return `<p class="ms-links">${others.map((p) => `<button type="button" class="ms-link" data-month-page="${esc(p.id)}">${esc(p.linkLabel(ms.month))} →</button>`).join("")}</p>`;
}
