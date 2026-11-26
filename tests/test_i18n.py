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

    def test_weights_in_the_country_units(self):
        """The data keep short tons and pounds; the US map shows them as they are, Spain's in tonnes."""
        def weights(country):
            return json.loads(node(f"""
                import {{ setCountry }} from './web/js/app/country.js';
                import {{ shownTons, shownWeight }} from './web/js/format.js';
                setCountry({{ country: {json.dumps(country)} }}, null);
                console.log(JSON.stringify([shownTons(1102311), shownWeight(2204623), shownTons(null), shownWeight(null)]));
            """))
        self.assertEqual(weights({}), [1102311, 2204623, None, None])
        tonnes, cargo, *nulls = weights({"locale": "es-ES", "lang": "es"})
        self.assertAlmostEqual(tonnes, 1e6, delta=1)
        self.assertAlmostEqual(cargo, 1000, delta=0.01)
        self.assertEqual(nulls, [None, None])

    def test_spanish_formats(self):
        nb = " "
        self.assertEqual(self.formats({"locale": "es-ES", "currency": "EUR", "lang": "es"}), [
            "950", f"1,2{nb}mil", f"123,5{nb}mil", f"1,6{nb}M", f"1600{nb}M", f"2,1{nb}B", f"2,1{nb}B{nb}€", f"35.200{nb}€",
            "1.234.567", f"12,3{nb}%", f"50{nb}%", f"6,6{nb}M", f"350{nb}mil", "3,3"])


class SpanishDataTest(unittest.TestCase):
    """Spain's data files (sites/es/data) are read by Spanish speakers: a text in them that carries common English
    words is a leftover of a US builder or of an English source (a vintage, a plant name, a unit).

    A small heuristic: words that are English and spelled like no Spanish (or Catalan, Galician, Basque) word, in every
    string that is not an id or a code. Proper names that hold one go in PROPER_NAMES, with the reason they stay."""

    DATA = ROOT / "sites" / "es" / "data"
    # Keys whose values are ids or codes, never shown as text.
    CODES = {"id", "type", "kind", "key", "icon", "motif", "rule", "group", "format", "scale", "higher_is", "color", "dark",
             "source", "sources", "file", "files", "sha256", "url", "cbsa", "county", "state", "naics", "via", "basis",
             "district", "category", "unit_type", "qid", "ramp", "kinds", "industries", "site_url", "product", "lang",
             "locale", "currency"}
    CODE_VALUES = {"workers", "usd", "eur"}  # nation.json yields[].unit
    ENGLISH = set("""the of and with from for by is are was not this that its which who people residents workers jobs
        county counties state states share median average farm wind plant plants power station airport airports
        students visitors island islands short tons pounds lb million billion year years unknown phase landmark
        landmarks wonder wonders university universities river lake coast coastal mountain mountains hills north south
        east west population income land forest desert urban edition none other boardings enplanements cargo nonhub
        museum gallery""".split())
    # Licence codes and the names of products and bodies, kept as they are written.
    PROPER_NAMES = [
        re.compile(r"\bCC BY(?:-[A-Z]{2})*"),  # Creative Commons licences
        "CORINE Land Cover",  # the Copernicus product
        "National Centers for Environmental Information",  # the NOAA office that publishes ETOPO
        "Institute for the Study of the Ancient World",  # Pleiades' publisher (NYU)
        "power=plant",  # the OpenStreetMap tag
        "Alma Mater Museum",  # the museum of the Archdiocese of Zaragoza is called so
        # Museums that Wikidata names only in English (or in English before Catalan, Galician or Basque, the label
        # order of pipeline/sources/es/wikidata.py). A new label order needs a fresh fetch of the Wikidata queries.
        "Chinijo Museum", "Culleredo Ethnographic Museum", "Hash Marihuana & Hemp Museum", "Liedtke Museum",
        "Military Museum of Valencia", "Modern Art Museum of Barcelona", "Museum Cemento Rezola", "Museum Jorge Rando",
        "Museum Juan Évora", "Museum of Contemporary Tapestry", "The House of Magic. The Xevi Collection",
        "The Sherry Gallery", "Truffles Museum of Metauten",
    ]

    @classmethod
    def english_words(cls, text: str) -> set[str]:
        for p in cls.PROPER_NAMES:
            text = p.sub("", text) if isinstance(p, re.Pattern) else text.replace(p, "")
        return {w.lower() for w in re.findall(r"[^\W\d_]+", text)} & cls.ENGLISH

    def leftovers(self, name):
        found = []

        def walk(x, path):
            if isinstance(x, dict):
                for k, v in x.items():
                    if k not in self.CODES:
                        walk(v, f"{path}.{k}")
            elif isinstance(x, list):
                for i, v in enumerate(x):
                    walk(v, f"{path}[{i}]")
            elif isinstance(x, str) and not x.startswith("http") and x not in self.CODE_VALUES:
                if words := self.english_words(x):
                    found.append(f"{name}{path}: {x[:100]!r} ({', '.join(sorted(words))})")

        walk(json.loads((self.DATA / name).read_text(encoding="utf-8")), "")
        return found

    def test_no_english_in_spanish_texts(self):
        found = [f for p in sorted(self.DATA.glob("*.json")) for f in self.leftovers(p.name)]
        self.assertEqual(found, [], "\n".join(found[:40]))

    def test_the_heuristic_catches_the_old_leftovers(self):
        for text in ("AENA 2025 (final) boardings", "Las Majas Wind Farm (+1)", "SIIU, students 2024-2025",
                     "OAPN, Red de Parques Nacionales; visitors 2025", "Naval Museum of Cartagena"):
            self.assertTrue(self.english_words(text), text)
        for text in ("Andén 0", "Museu de la Farmàcia Catalana", "Estación de Metro Ópera", "Areas Gordas (Sanxenxo)",
                     "CORINE Land Cover 2018", "MAPA: CC BY 4.0", "miles de toneladas"):
            self.assertFalse(self.english_words(text), text)


if __name__ == "__main__":
    unittest.main()
