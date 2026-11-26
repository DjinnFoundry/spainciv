"""pipeline/site.py and the package: the US page is published as written; Spain gets its own head, credits and files."""

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

from pipeline import countries, package, site
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
        es = countries.COUNTRIES["es"]
        self.assertEqual(es.site_url, "spainciv.djinnfoundry.com")
        h = Head(site.render_index(TEMPLATE, es))
        url = "https://spainciv.djinnfoundry.com/"
        self.assertEqual(h.lang, "es")
        self.assertEqual(h.title, es.page.title)
        self.assertEqual(h.links["canonical"], url)
        self.assertEqual(h.meta["description"], es.page.description)
        self.assertEqual(h.meta["og:site_name"], "spainciv")
        self.assertEqual(h.meta["og:url"], url)
        for k in ("og:image", "twitter:image"):
            self.assertEqual(h.meta[k], url + "og-image.png")
        for k in ("og:title", "twitter:title"):
            self.assertEqual(h.meta[k], es.page.card_title)
        for k in ("og:description", "twitter:description"):
            self.assertEqual(h.meta[k], es.page.description)
        for k in ("og:image:alt", "twitter:image:alt"):
            self.assertEqual(h.meta[k], es.page.image_alt)
        # The image size and card type are the template's, still right for the 1200x630 card.
        self.assertEqual((h.meta["og:image:width"], h.meta["og:image:height"], h.meta["twitter:card"]), ("1200", "630", "summary_large_image"))
        self.assertNotIn("karpathy.ai", " ".join([*h.meta.values(), *h.links.values()]))

    def test_spain_credits_and_settings(self):
        es = countries.COUNTRIES["es"]
        html = site.render_index(TEMPLATE, es)
        h = Head(html)
        self.assertIn("Límites: Atlas Nacional de España (ANE), CC BY 4.0, ign.es", h.credits)
        self.assertIn(es.page.data_credit, h.credits)
        self.assertNotIn("EuroGeographics", html)  # GISCO boundaries were replaced by the IGN's SIANE
        self.assertIn("Basado en usaciv, de Andrej Karpathy (MIT)", h.credits)
        self.assertIn('<a href="https://karpathy.ai/usaciv/"', html)
        self.assertEqual(h.config, {"lang": "es", "site_url": es.site_url, "data_credit": es.page.data_credit, "notices": list(es.page.notices)})
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

    def test_a_changed_template_fails_loudly(self):
        with self.assertRaises(ValueError):
            site.render_index(TEMPLATE.replace('<meta property="og:url"', '<meta property="og:URL"'), countries.COUNTRIES["es"])


class OverlayTest(unittest.TestCase):
    def test_us_has_none(self):
        self.assertIsNone(site.overlay_dir(countries.COUNTRIES["us"]))
        self.assertEqual(site.overlay_files(countries.COUNTRIES["us"]), [])

    def test_spain_og_image(self):
        files = dict((rel.as_posix(), f) for f, rel in site.overlay_files(countries.COUNTRIES["es"]))
        self.assertIn("og-image.png", files)
        self.assertNotIn("data", {Path(k).parts[0] for k in files})
        png = files["og-image.png"].read_bytes()
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual((int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")), (1200, 630))
        self.assertNotEqual(png, (WEB / "og-image.png").read_bytes())


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
        out = self.build("es")
        self.assertEqual((out / "index.html").read_bytes(), site.index_bytes(es))
        self.assertEqual((out / "og-image.png").read_bytes(), (ROOT / "sites" / "es" / "og-image.png").read_bytes())
        self.assertEqual((out / "data" / "world.json").read_bytes(), (es.web_data_dir / "world.json").read_bytes())
        self.assertFalse((out / "data" / "military.json").exists())  # US data never leaks into Spain's site
        for name in ("LICENSE", "NOTICE"):
            self.assertTrue((out / name).is_file())


@unittest.skipUnless(NODE, "node is not installed")
class CountryJsTest(unittest.TestCase):
    def country(self, world, page_json):
        doc = "null" if page_json is None else "{getElementById: (id) => id === 'country-page' ? {textContent: %s} : null}" % json.dumps(page_json)
        script = (
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
        self.assertEqual(c["data_credit"], es.page.data_credit)
        self.assertEqual(c["product"], "spainciv")

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
