"""The month shared by the fiesta calendar and the climate of the month (web/js/ext/month.js): the month from the date
and from the URL, which page a link with `mes` opens, and the month state on a stub app whose URL hash applies a key
the way createHashState does for a key registered after the page loaded (once, in a microtask). Run with node; skipped
without it."""

import json
import shutil
import subprocess
import unittest

from pipeline.core.paths import ROOT

NODE = shutil.which("node")

PRELUDE = """
const M = await import('./web/js/ext/month.js');
const { createEmitter } = await import('./web/js/app/api.js');
const out = (x) => console.log(JSON.stringify(x));
const tick = () => new Promise((r) => setTimeout(r, 0));

// An app with a URL hash, the pages' lenses and an `extensions` event the test fires when it says so.
function makeApp(link) {
  const hash = new URLSearchParams(link.replace(/^#/, ''));
  const app = { ...createEmitter(), keys: new Map(), writes: 0, extensions: undefined };
  app.hash = {
    value: (k) => hash.get(k),
    update: () => app.writes++,
    register(key, h) {
      app.keys.set(key, h);
      if (hash.has(key)) queueMicrotask(() => h.set(hash.get(key)));
    },
  };
  app.installed = () => { app.extensions = []; app.emit('extensions', []); };
  return app;
}
function page(ms, id, lensIds, extra = {}) {
  const p = { id, lensIds, on: false, opened: 0, months: [], active: () => p.on, open() { p.on = true; p.opened++; },
              onMonth: (m) => p.months.push(m), linkLabel: (m) => `${id} ${m}`, ...extra };
  ms.page(p);
  return p;
}
"""


def run(body: str):
    res = subprocess.run([NODE, "--input-type=module", "-e", PRELUDE + body], cwd=ROOT, capture_output=True, text=True)
    if res.returncode:
        raise AssertionError(res.stderr)
    return json.loads(res.stdout)


@unittest.skipUnless(NODE, "node is not installed")
class MonthTest(unittest.TestCase):
    def test_month_from_the_local_date_and_from_the_url(self):
        got = run("out([M.currentMonth(new Date(2026, 7, 31, 23, 59)), M.currentMonth(new Date(2027, 0, 1, 0, 0)), "
                  "['8', '12', '1', '0', '13', '8.5', 'agosto', '', null, ' 8', '08'].map(M.parseMonth)]);")
        self.assertEqual(got, [8, 1, [8, 12, 1, None, None, None, None, None, None, None, None]])

    def test_month_names_follow_the_locale(self):
        got = run("out([M.monthName(1, 'es-ES'), M.monthName(8, 'en-IE'), M.monthName(9, 'es-ES', 'short')]);")
        self.assertEqual(got[:2], ["enero", "August"])
        self.assertTrue(got[2].startswith("sept"))


@unittest.skipUnless(NODE, "node is not installed")
class HashRuleTest(unittest.TestCase):
    def test_the_lens_picks_the_page_and_the_month_alone_the_fallback(self):
        got = run("""
            const pages = [{ id: 'fiestas', lensIds: ['fiestas_mes'], fallback: true },
                           { id: 'clima', lensIds: ['clima_temp', 'clima_lluvia', 'clima_heladas', 'clima_sol'] }];
            const pick = (lens) => M.pickPage(pages, lens)?.id ?? null;
            out([pick('clima_temp'), pick('clima_sol'), pick(null), pick('fiestas_mes'), pick('density'),
                 M.pickPage(pages.slice(1), null)]);
        """)
        self.assertEqual(got, ["clima", "clima", "fiestas", "fiestas", "fiestas", None])

    def test_a_link_with_a_climate_lens_and_a_month_opens_the_climate_once_every_extension_is_in(self):
        got = run("""
            const app = makeApp('#lens=clima_temp&mes=1');
            const ms = M.monthState(app);
            const fiestas = page(ms, 'fiestas', ['fiestas_mes'], { fallback: true });
            await tick(); // the key is applied before the climate's extension has installed
            const before = [ms.month, fiestas.opened];
            const clima = page(ms, 'clima', ['clima_temp', 'clima_lluvia']);
            app.installed();
            out({ before, fiestas: fiestas.opened, clima: clima.opened, month: ms.month, key: app.keys.get('mes').get(),
                  same: M.monthState(app) === ms });
        """)
        self.assertEqual(got, {"before": [1, 0], "fiestas": 0, "clima": 1, "month": 1, "key": "1", "same": True})

    def test_a_month_alone_opens_the_fiesta_calendar_as_it_always_did(self):
        got = run("""
            const app = makeApp('#mes=8');
            const ms = M.monthState(app);
            const fiestas = page(ms, 'fiestas', ['fiestas_mes'], { fallback: true });
            const clima = page(ms, 'clima', ['clima_temp']);
            app.installed();
            await tick();
            out([fiestas.opened, clima.opened, ms.month]);
        """)
        self.assertEqual(got, [1, 0, 8])

    def test_an_open_page_is_not_opened_again_and_a_bad_month_does_nothing(self):
        got = run("""
            const app = makeApp('');
            app.installed();
            const ms = M.monthState(app);
            const fiestas = page(ms, 'fiestas', ['fiestas_mes'], { fallback: true });
            const key = app.keys.get('mes');
            const closed = key.get();
            key.set('13'); key.set(null);
            const untouched = [fiestas.opened, ms.month === M.currentMonth()];
            fiestas.on = true;
            key.set('3');
            out({ closed, untouched, opened: fiestas.opened, key: key.get() });
        """)
        self.assertEqual(got, {"closed": None, "untouched": [0, True], "opened": 0, "key": "3"})


@unittest.skipUnless(NODE, "node is not installed")
class MonthStateTest(unittest.TestCase):
    def test_a_new_month_reaches_every_page_once_and_writes_the_url(self):
        got = run("""
            const app = makeApp('');
            const ms = M.monthState(app);
            const a = page(ms, 'a', ['la']), b = page(ms, 'b', ['lb']);
            const now = ms.month, next = now % 12 + 1;
            ms.set(now); // the same month: nothing
            ms.set(next);
            out({ a: a.months, b: b.months, writes: app.writes, next, others: ms.others('a').map((p) => p.id) });
        """)
        self.assertEqual(got["a"], [got["next"]])
        self.assertEqual(got["b"], [got["next"]])
        self.assertEqual((got["writes"], got["others"]), (1, ["b"]))

    def test_links_name_the_other_pages_on_the_same_month_and_open_them(self):
        got = run("""
            const app = makeApp('');
            const ms = M.monthState(app);
            const a = page(ms, 'a', ['la']);
            const alone = M.monthLinks(ms, 'a');
            const b = page(ms, 'b', ['lb']);
            ms.set(5);
            const html = M.monthLinks(ms, 'a');
            ms.follow({ target: { closest: () => ({ dataset: { monthPage: 'b' } }) } });
            ms.follow({ target: { closest: () => null } });
            out({ alone, html, b: b.opened, a: a.opened });
        """)
        self.assertEqual(got["alone"], "")
        self.assertIn('data-month-page="b"', got["html"])
        self.assertIn("b 5 →", got["html"])
        self.assertNotIn('data-month-page="a"', got["html"])
        self.assertEqual((got["b"], got["a"]), (1, 0))

    def test_moving_between_pages_keeps_the_month_and_closing_the_last_one_forgets_it(self):
        got = run("""
            const app = makeApp('');
            const ms = M.monthState(app);
            const a = page(ms, 'a', ['la']), b = page(ms, 'b', ['lb']);
            const other = ms.month % 12 + 1;
            const mode = () => app.emit('mode', {});
            a.on = true; mode();
            ms.set(other);
            a.on = false; b.on = true; mode(); // a link from a to b
            const moved = ms.month;
            app.emit('mode', {}); // another mode event with b still open
            const still = ms.month;
            b.on = false; mode(); // Esc
            out({ other, moved, still, after: ms.month, now: M.currentMonth(), key: app.keys.get('mes').get() });
        """)
        self.assertEqual((got["moved"], got["still"]), (got["other"], got["other"]))
        self.assertEqual((got["after"], got["key"]), (got["now"], None))


if __name__ == "__main__":
    unittest.main()
