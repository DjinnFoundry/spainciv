"""pipeline/site.py and the package: the US page is published as written; Spain gets its own head, credits and files."""

import http.server
import json
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

import pipeline.__main__ as cli
from pipeline import countries, package, play, site
from pipeline.core.paths import ROOT, WEB

TEMPLATE = (WEB / "index.html").read_text(encoding="utf-8")
COUNTRY_JS = WEB / "js" / "app" / "country.js"
NODE = shutil.which("node")


class Head(HTMLParser):
    """The <head> facts a crawler reads, plus the map credits and the page settings."""

    def __init__(self, html):
        super().__init__()
        self.meta, self.links, self.lang, self.title, self.credits, self.config = {}, {}, None, "", "", None
        self._in = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "meta" and "content" in a:
            self.meta[a.get("property") or a.get("name")] = a["content"]
        elif tag == "link":
            self.links[a["rel"]] = a["href"]
        elif tag == "title" or (tag == "p" and a.get("id") == "map-credits") or (tag == "script" and a.get("id") == "country-page"):
            self._in = a.get("id") or tag

    def handle_endtag(self, tag):
        if tag in ("title", "p", "script"):
            self._in = None

    def handle_data(self, data):
        if self._in == "title":
            self.title += data
        elif self._in == "map-credits":
            self.credits += data
        elif self._in == "country-page":
            self.config = json.loads(data)


class RenderTest(unittest.TestCase):
    def test_us_page_is_the_template(self):
        self.assertIsNone(countries.COUNTRIES["us"].page)
        self.assertEqual(site.render_index(TEMPLATE, countries.COUNTRIES["us"]), TEMPLATE)
        with countries.using("us"):
            self.assertEqual(site.index_bytes(), (WEB / "index.html").read_bytes())

    def test_spain_head(self):
        """The head is in Spanish, the language of the data: link previews never see the language a visitor picks."""
        es = countries.COUNTRIES["es"]
        page = es.page.in_lang("es")
        self.assertEqual(es.site_url, "spainciv.djinnfoundry.com")
        h = Head(site.render_index(TEMPLATE, es))
        url = "https://spainciv.djinnfoundry.com/"
        self.assertEqual(h.lang, "es")
        self.assertEqual(h.title, page.title)
        self.assertEqual(h.links["canonical"], url)
        self.assertEqual(h.meta["description"], page.description)
        self.assertEqual(h.meta["og:site_name"], "spainciv")
        self.assertEqual(h.meta["og:url"], url)
        for k in ("og:image", "twitter:image"):
            self.assertEqual(h.meta[k], url + "og-image.png")
        for k in ("og:title", "twitter:title"):
            self.assertEqual(h.meta[k], page.card_title)
        for k in ("og:description", "twitter:description"):
            self.assertEqual(h.meta[k], page.description)
        for k in ("og:image:alt", "twitter:image:alt"):
            self.assertEqual(h.meta[k], page.image_alt)
        # The image size and card type are the template's, still right for the 1200x630 card.
        self.assertEqual((h.meta["og:image:width"], h.meta["og:image:height"], h.meta["twitter:card"]), ("1200", "630", "summary_large_image"))
        self.assertNotIn("karpathy.ai", " ".join([*h.meta.values(), *h.links.values()]))

    def test_spain_credits_and_settings(self):
        es = countries.COUNTRIES["es"]
        page, en = es.page.in_lang("es"), es.page.in_lang("en")
        html = site.render_index(TEMPLATE, es)
        h = Head(html)
        self.assertIn("Límites: Atlas Nacional de España (ANE), CC BY 4.0, ign.es", h.credits)
        self.assertIn(page.data_credit, h.credits)
        self.assertNotIn("EuroGeographics", html)  # GISCO boundaries were replaced by the IGN's SIANE
        self.assertIn("Basado en usaciv, de Andrej Karpathy (MIT)", h.credits)
        self.assertIn('<a href="https://karpathy.ai/usaciv/"', html)

        def groups(p):  # the fog of war's groups of regions (Page.explore) in that page's language
            return {"groups": [{"name": name, "regions": list(regions)} for name, regions in p.explore]}

        english = {"data_credit": en.data_credit, "notices": list(en.notices), "explore": groups(en), "play": "play.html",
                   "description": en.description, "credits": site.credits_inner(es, "en")}
        self.assertEqual(h.config, {"lang": "es", "site_url": es.site_url, "data_credit": page.data_credit, "notices": list(page.notices),
                                    "explore": groups(page), "play": "jugar.html", "langs": {"es": "es-ES", "en": "en-IE"}, "texts": {"en": english},
                                    "data": sorted(p.stem for p in es.web_data_dir.glob("*.json") if "." not in p.stem),
                                    "game": True, "sunset": True})
        self.assertIn("lenses", h.config["data"])
        self.assertNotIn("lenses.en", h.config["data"])
        self.assertNotIn("trade", h.config["data"])  # a US-only file Spain does not have
        self.assertIn("Based on <a href=", english["credits"])
        self.assertIn("Boundaries: Atlas Nacional de España (ANE)", english["credits"])
        # The credits come before the lens dock: the CSS lifts the dock with `.map-credits ~ #lens-area`.
        self.assertLess(html.index('id="map-credits"'), html.index('id="lens-area"'))

    def test_values_are_escaped(self):
        page = countries.Page(title="A <b> & \"c\"", card_title="t", description='d "q"', image_alt="a", data_credit="</script>x", notices=("n<",))
        with countries.using("es", page=page) as c:
            html = site.render_index(TEMPLATE, c)
        self.assertIn("<title>A &lt;b&gt; &amp; &quot;c&quot;</title>", html)
        self.assertIn('content="d &quot;q&quot;"', html)
        self.assertIn("n&lt;", html)
        self.assertEqual(html.count("</script>"), TEMPLATE.count("</script>") + 1)
        self.assertEqual(Head(html).config["data_credit"], "</script>x")
        self.assertNotIn("game", Head(html).config)  # the daily game, the sun lens and the fog of war are the page's choice
        self.assertNotIn("sunset", Head(html).config)
        self.assertNotIn("explore", Head(html).config)

    def test_a_changed_template_fails_loudly(self):
        with self.assertRaises(ValueError):
            site.render_index(TEMPLATE.replace('<meta property="og:url"', '<meta property="og:URL"'), countries.COUNTRIES["es"])


class GeneratedFilesTest(unittest.TestCase):
    def test_us_only_renders_its_index(self):
        files = site.generated_files(countries.COUNTRIES["us"])
        self.assertEqual(set(files), {"index.html"})
        self.assertEqual(files["index.html"](), (WEB / "index.html").read_bytes())

    def test_spain_draws_its_card_and_ships_its_unciv_map(self):
        es = countries.COUNTRIES["es"]
        files = site.generated_files(es)
        self.assertEqual(set(files), {"index.html", "og-image.png", "_headers"} | set(play.files(es)))
        self.assertIn("/js/*\n  Cache-Control: public, max-age=0, must-revalidate", files["_headers"]().decode())
        self.assertTrue(set(play.PAGES.values()) <= set(files))
        self.assertEqual(files["index.html"](), site.index_bytes(es))
        with mock.patch.object(site, "card_png", return_value=b"card") as card:
            self.assertEqual(files["og-image.png"](), b"card")
        card.assert_called_once_with(es)

    def test_no_card_is_committed(self):
        # The card is drawn from the data when the site is served or packaged; a stale copy must not shadow it.
        self.assertEqual(sorted(p.name for p in (ROOT / "sites" / "es").iterdir() if p.name != ".DS_Store"), ["data"])


class ServeTest(unittest.TestCase):
    """`pipeline serve` answers the generated files as `package` writes them, and web/'s files as they are."""

    def get(self, country_id, path):
        with countries.using(country_id), mock.patch.object(site, "card_png", return_value=b"\x89PNG card"), \
                mock.patch.object(cli._SiteHandler, "log_message"):
            srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), cli.site_handler())
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{srv.server_port}{path}") as r:
                    return r.headers["Content-Type"], r.read()
            finally:
                srv.shutdown()
                srv.server_close()

    def test_spain(self):
        es = countries.COUNTRIES["es"]
        self.assertEqual(self.get("es", "/og-image.png"), ("image/png", b"\x89PNG card"))
        self.assertEqual(self.get("es", "/"), ("text/html; charset=utf-8", site.index_bytes(es)))
        self.assertEqual(self.get("es", "/index.html?x=1")[1], site.index_bytes(es))
        self.assertEqual(self.get("es", "/data/world.json")[1], (es.web_data_dir / "world.json").read_bytes())

    def test_us(self):
        self.assertEqual(self.get("us", "/og-image.png")[1], (WEB / "og-image.png").read_bytes())
        self.assertEqual(self.get("us", "/")[1], (WEB / "index.html").read_bytes())

    def test_restarts_when_the_pipeline_code_changes(self):
        """A server started before an edit to site.py or a country's page would keep serving the old index.html
        (an English credit line under a Spanish interface): serve runs the server in a child it restarts."""
        children = [mock.Mock(**{"poll.return_value": None}), mock.Mock(returncode=0, **{"poll.side_effect": [None, 0, 0]})]
        stamps = iter([1.0, 1.0, 2.0, 2.0, 2.0, 2.0])
        with mock.patch.dict(cli.os.environ, {cli.SERVE_CHILD: ""}), \
                mock.patch.object(cli.subprocess, "Popen", side_effect=children) as popen, \
                mock.patch.object(cli, "code_stamp", lambda: next(stamps)), mock.patch.object(cli.time, "sleep"), \
                mock.patch("builtins.print"), self.assertRaises(SystemExit) as done:
            cli.cmd_serve(8772, ["serve", "--country", "es", "--port", "8772"])
        self.assertEqual(done.exception.code, 0)
        self.assertEqual(popen.call_count, 2)
        children[0].terminate.assert_called_once_with()
        args, kw = popen.call_args
        self.assertEqual(args[0][1:], ["-m", "pipeline", "serve", "--country", "es", "--port", "8772"])
        self.assertEqual(kw["env"][cli.SERVE_CHILD], "1")

    def test_code_stamp_follows_the_newest_module(self):
        self.assertEqual(cli.code_stamp(), max(p.stat().st_mtime for p in (ROOT / "pipeline").rglob("*.py")))


class PackageTest(unittest.TestCase):
    """cmd_package into a temporary dist/ (the source zip and site zip are written there too)."""

    def build(self, country_id):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        with countries.using(country_id), mock.patch.object(package, "DIST", tmp), mock.patch.object(package, "ROOT", tmp), \
                mock.patch.object(package, "_files", self._files_from_repo), mock.patch("builtins.print"):
            for name in ("LICENSE", "NOTICE"):
                shutil.copy2(ROOT / name, tmp / name)
            package.cmd_package()
        return tmp / countries.COUNTRIES[country_id].product

    @staticmethod
    def _files_from_repo(base, items, _orig=package._files):
        # The source zip reads from the temporary ROOT, which only holds LICENSE and NOTICE: keep it small.
        if items == package.SOURCE_ITEMS:
            return _orig(base, ["LICENSE", "NOTICE"])
        return _orig(base, items)

    def test_us_site_index_and_image_are_web_files(self):
        out = self.build("us")
        self.assertEqual((out / "index.html").read_bytes(), (WEB / "index.html").read_bytes())
        self.assertEqual((out / "og-image.png").read_bytes(), (WEB / "og-image.png").read_bytes())

    def test_spain_site(self):
        es = countries.COUNTRIES["es"]
        with mock.patch.object(site, "card_png", return_value=b"\x89PNG card") as card:
            out = self.build("es")
        card.assert_called_once_with(es)
        self.assertEqual((out / "index.html").read_bytes(), site.index_bytes(es))
        self.assertEqual((out / "og-image.png").read_bytes(), b"\x89PNG card")
        self.assertEqual((out / "data" / "world.json").read_bytes(), (es.web_data_dir / "world.json").read_bytes())
        # US data never leaks into Spain's site: its military.json is Spain's own
        self.assertEqual((out / "data" / "military.json").read_bytes(), (es.web_data_dir / "military.json").read_bytes())
        self.assertNotEqual((out / "data" / "military.json").read_bytes(), (WEB / "data" / "military.json").read_bytes())
        for path in play.files(es):
            self.assertTrue((out / path).is_file(), path)
        for name in ("LICENSE", "NOTICE"):
            self.assertTrue((out / name).is_file())


@unittest.skipUnless(NODE, "node is not installed")
class CountryJsTest(unittest.TestCase):
    def country(self, world, page_json, browser=()):
        """setCountry in node, with the page settings `page_json` and the browser's languages `browser`. Node has its own
        `navigator`, whose languages follow the machine's locale: replaced so the result does not depend on it."""
        doc = "null" if page_json is None else "{getElementById: (id) => id === 'country-page' ? {textContent: %s} : null}" % json.dumps(page_json)
        script = (
            f"Object.defineProperty(globalThis, 'navigator', {{value: {{languages: {json.dumps(list(browser))}}}}});"
            f"import({json.dumps(COUNTRY_JS.as_uri())}).then(({{setCountry}}) => "
            f"console.log(JSON.stringify(setCountry({json.dumps(world)}, {doc}))));"
        )
        out = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
        return json.loads(out.stdout)

    def test_page_settings_override_world(self):
        es = countries.COUNTRIES["es"]
        world = {"country": {"id": "es", "site_url": "spainciv", "product": "spainciv"}}
        c = self.country(world, json.dumps(site.page_config(es)))
        self.assertEqual(c["site_url"], "spainciv.djinnfoundry.com")
        self.assertEqual(c["notices"], ["Límites: Atlas Nacional de España (ANE), CC BY 4.0, ign.es"])
        self.assertEqual(c["data_credit"], es.page.in_lang("es").data_credit)
        self.assertEqual(c["product"], "spainciv")

    def test_browser_language_picks_its_texts(self):
        es = countries.COUNTRIES["es"]
        c = self.country({"country": {"id": "es"}}, json.dumps(site.page_config(es)), browser=["en-GB"])
        self.assertEqual((c["lang"], c["locale"]), ("en", dict(es.locales)["en"]))
        self.assertEqual(c["notices"], ["Boundaries: Atlas Nacional de España (ANE), CC BY 4.0, ign.es"])
        self.assertEqual(c["data_credit"], es.page.in_lang("en").data_credit)

    def test_us_without_page_settings(self):
        c = self.country({}, None)
        self.assertEqual((c["site_url"], c["notices"]), ("karpathy.ai/usaciv", []))
        self.assertTrue(re.match(r"Data: Census ACS", c["data_credit"]))
        self.assertEqual(self.country({}, "not json")["site_url"], "karpathy.ai/usaciv")


@unittest.skipUnless(NODE, "node is not installed")
class ShareLinkJsTest(unittest.TestCase):
    def test_camera_updates_keep_city_view_until_it_loads(self):
        result = subprocess.run([NODE, "--input-type=module", "-e", """
            import assert from 'node:assert/strict';
            import { createHashState } from './web/js/app/api.js';

            globalThis.window = { addEventListener() {} };
            globalThis.location = new URL('https://example.com/#city=12040&view=city');
            const navigation = [];
            const write = (kind, href) => {
                navigation.push(kind);
                location.href = new URL(href, location.href);
            };
            globalThis.history = {
                pushState: (_state, _title, href) => write('push', href),
                replaceState: (_state, _title, href) => write('replace', href),
            };
            const url = createHashState({ read: () => ({ city: '12040', at: [1, 2, 3] }) });
            url.flush();
            assert.equal(url.value('view'), 'city');
            assert.deepEqual(navigation, ['replace']);

            let active = null;
            url.register('view', { get: () => active, set: (value) => { active = value; } });
            await Promise.resolve();
            assert.equal(active, 'city');

            active = null;
            url.flush();
            assert.equal(url.value('view'), null);
            assert.deepEqual(navigation, ['replace', 'push']);
        """], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
