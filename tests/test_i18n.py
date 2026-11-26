"""The interface string tables (web/js/i18n.js, web/js/i18n/<lang>/*.js) and the locale number formats (web/js/format.js).

Run with node; skipped without it. English is the original usaciv text, so the checks that matter most for the US
map are that every key the code uses has an English string, that index.html's static text still matches the English
table that replaces it, and that the en-US number formats are the original ones.
"""

import json
import re
import shutil
import subprocess
import unittest

from pipeline.core.paths import ROOT

NODE = shutil.which("node")
WEB_JS = ROOT / "web" / "js"
# t("key"), t('key') or t(`key`) with a literal key: the keys the code asks for.
KEY_USE = re.compile(r"""\bt\(\s*(["'`])([A-Za-z0-9_.@-]+)\1""")


def node(script: str) -> str:
    out = subprocess.run([NODE, "--input-type=module", "-e", script], cwd=ROOT, capture_output=True, text=True)
    if out.returncode:
        raise AssertionError(out.stderr)
    return out.stdout


def used_keys() -> dict[str, str]:
    """Every literal key passed to t() in web/js, with the first file that uses it."""
    keys: dict[str, str] = {}
    for f in sorted(WEB_JS.rglob("*.js")):
        if "i18n" in f.relative_to(WEB_JS).parts[0]:
            continue
        for m in KEY_USE.finditer(f.read_text(encoding="utf-8")):
            keys.setdefault(m.group(2), str(f.relative_to(ROOT)))
    return keys


@unittest.skipUnless(NODE, "node is not installed")
class TablesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = node("""
            import { readdirSync } from 'node:fs';
            const tables = {};
            for (const lang of ['en', 'es']) {
                const merged = (await import(`./web/js/i18n/${lang}.js`)).default;
                const parts = {};
                for (const f of readdirSync(`web/js/i18n/${lang}`)) parts[f] = Object.keys((await import(`./web/js/i18n/${lang}/${f}`)).default);
                tables[lang] = { merged, parts };
            }
            console.log(JSON.stringify(tables));
        """)
        tables = json.loads(out)
        cls.en, cls.es = tables["en"]["merged"], tables["es"]["merged"]
        cls.parts = {lang: tables[lang]["parts"] for lang in tables}

    def test_every_used_key_has_an_english_string(self):
        missing = {k: f for k, f in used_keys().items() if k not in self.en}
        self.assertEqual(missing, {})

    def test_spanish_covers_english(self):
        # Keys ending in ".us" are United States content that only the English (US) site shows.
        self.assertEqual(sorted(k for k in self.en if k not in self.es and not k.endswith(".us")), [])
        self.assertEqual(sorted(k for k in self.es if k not in self.en), [])

    def test_same_placeholders(self):
        def holes(v):
            texts = v.values() if isinstance(v, dict) else [v]
            return {h for s in texts for h in re.findall(r"\{(\w+)\}", s)}

        diff = {k: (holes(self.en[k]), holes(v)) for k, v in self.es.items() if k in self.en and holes(v) != holes(self.en[k])}
        self.assertEqual(diff, {})

    def test_plural_entries_have_one_and_other(self):
        for table in (self.en, self.es):
            for k, v in table.items():
                if isinstance(v, dict):
                    self.assertEqual(sorted(v), ["one", "other"], k)

    def test_no_key_in_two_parts(self):
        for lang, parts in self.parts.items():
            seen: dict[str, str] = {}
            for f, keys in parts.items():
                for k in keys:
                    self.assertNotIn(k, seen, f"{lang}: {k} in {seen.get(k)} and {f}")
                    seen[k] = f

    def test_page_strings_match_index_html(self):
        """index.html is written in English for the US: the English table must say exactly what it says."""
        out = node("""
            import { PAGE_STRINGS } from './web/js/i18n.js';
            console.log(JSON.stringify(PAGE_STRINGS));
        """)
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        unescape = lambda s: s.replace("&amp;", "&")
        for sel, attr, key in json.loads(out):
            ident = sel.split()[-1].lstrip("#")
            if sel.startswith("#pedia ") or sel == "#loading":
                found = {"#pedia .modal-card": r'class="modal-card panel"[^>]*aria-label="([^"]*)"',
                         "#pedia [data-close]": r'data-close aria-label="([^"]*)"',
                         "#loading": r'<div id="loading">([^<]*)</div>'}[sel]
            else:
                found = rf'id="{re.escape(ident)}"[^>]*?{attr}="([^"]*)"'
            m = re.search(found, html)
            self.assertIsNotNone(m, sel)
            self.assertEqual(unescape(m.group(1)), self.en[key], key)


@unittest.skipUnless(NODE, "node is not installed")
class TranslateTest(unittest.TestCase):
    def run_t(self, world_country: dict, expr: str):
        return json.loads(node(f"""
            import {{ setCountry }} from './web/js/app/country.js';
            import {{ t, lang }} from './web/js/i18n.js';
            setCountry({{ country: {json.dumps(world_country)} }}, null);
            console.log(JSON.stringify({expr}));
        """))

    def test_language_follows_the_country(self):
        self.assertEqual(self.run_t({}, "[lang(), t('page.loading')]"), ["en", "Surveying the land…"])
        self.assertEqual(self.run_t({"lang": "es", "locale": "es-ES"}, "lang()"), "es")
        self.assertEqual(self.run_t({"lang": "xx"}, "[lang(), t('page.loading')]"), ["en", "Surveying the land…"])

    def test_placeholders_plurals_and_fallback(self):
        es = {"lang": "es", "locale": "es-ES"}
        got = self.run_t(es, "[t('nope.missing'), t('core.hexes', {n: 1}), t('core.hexes', {n: 3})]")
        self.assertEqual(got[0], "nope.missing")
        self.assertNotEqual(got[1], got[2])
        self.assertIn("3", got[2])


@unittest.skipUnless(NODE, "node is not installed")
class FormatTest(unittest.TestCase):
    CASES = "[compact(950), compact(1234), compact(123456), compact(1.6e6), compact(1.6e9), compact(2.1e12), money(2.1e12), " \
            "dollars(35200), int(1234567), pct(0.1234), pct(0.5, 0), popShort(6.6e6), popShort(350000), fixed(3.25, 1)]"

    def formats(self, country: dict):
        return json.loads(node(f"""
            import {{ setCountry }} from './web/js/app/country.js';
            import {{ compact, money, dollars, int, pct, popShort, fixed }} from './web/js/format.js';
            setCountry({{ country: {json.dumps(country)} }}, null);
            console.log(JSON.stringify({self.CASES}));
        """))

    def test_us_formats_are_the_original(self):
        self.assertEqual(self.formats({}), ["950", "1.2K", "123K", "1.6M", "1.6B", "2.10T", "$2.10T", "$35,200", "1,234,567",
                                            "12.3%", "50%", "6.6M", "350K", "3.3"])

    def test_spanish_formats(self):
        nb = " "
        self.assertEqual(self.formats({"locale": "es-ES", "currency": "EUR", "lang": "es"}), [
            "950", f"1,2{nb}mil", f"123,5{nb}mil", f"1,6{nb}M", f"1600{nb}M", f"2,1{nb}B", f"2,1{nb}B{nb}€", f"35.200{nb}€",
            "1.234.567", f"12,3{nb}%", f"50{nb}%", f"6,6{nb}M", f"350{nb}mil", "3,3"])


if __name__ == "__main__":
    unittest.main()
