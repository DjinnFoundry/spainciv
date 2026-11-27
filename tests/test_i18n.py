"""The interface string tables (web/js/i18n.js, web/js/i18n/<lang>/*.js), the locale number formats (web/js/format.js),
and the texts of Spain's data files in both of its languages (sites/es/data, pipeline/core/lang.py).

Run with node; skipped without it. English is the original usaciv text, so the checks that matter most for the US
map are that every key the code uses has an English string, that index.html's static text still matches the English
table that replaces it, and that the en-US number formats are the original ones. Spain is published in Spanish and
English: every Spanish key has a Spain English string (web/js/i18n/en-ES over the US English) that speaks of Spain,
and every data text has its English version, without Spanish left in it.
"""

import json
import re
import shutil
import subprocess
import unittest

from pipeline.core.lang import Text
from pipeline.core.paths import ROOT
from pipeline.core.store import read_web
from pipeline.sources.es.fiestas_autonomicas import COMMUNITIES

NODE = shutil.which("node")
WEB_JS = ROOT / "web" / "js"
# t("key"), t('key') or t(`key`) with a literal key: the keys the code asks for.
KEY_USE = re.compile(r"""\bt\(\s*(["'`])([A-Za-z0-9_.@-]+)\1""")
# usOr("key"): "key.us" on the US map, "key" elsewhere (web/js/i18n.js).
US_OR_USE = re.compile(r"""\busOr\(\s*(["'`])([A-Za-z0-9_.@-]+)\1""")


def node(script: str) -> str:
    out = subprocess.run([NODE, "--input-type=module", "-e", script], cwd=ROOT, capture_output=True, text=True)
    if out.returncode:
        raise AssertionError(out.stderr)
    return out.stdout


def used_keys() -> dict[str, str]:
    """Every literal key passed to t() in web/js (both strings of a usOr() key), with the first file that uses it."""
    keys: dict[str, str] = {}
    for f in sorted(WEB_JS.rglob("*.js")):
        if "i18n" in f.relative_to(WEB_JS).parts[0]:
            continue
        text, where = f.read_text(encoding="utf-8"), str(f.relative_to(ROOT))
        for m in KEY_USE.finditer(text):
            keys.setdefault(m.group(2), where)
        for m in US_OR_USE.finditer(text):
            keys.setdefault(m.group(2), where)
            keys.setdefault(m.group(2) + ".us", where)
    return keys


@unittest.skipUnless(NODE, "node is not installed")
class TablesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = node("""
            import { readdirSync } from 'node:fs';
            const tables = {};
            for (const lang of ['en', 'es', 'en-ES']) {
                const merged = (await import(`./web/js/i18n/${lang}.js`)).default;
                const parts = {};
                for (const f of readdirSync(`web/js/i18n/${lang}`)) parts[f] = Object.keys((await import(`./web/js/i18n/${lang}/${f}`)).default);
                tables[lang] = { merged, parts };
            }
            console.log(JSON.stringify(tables));
        """)
        tables = json.loads(out)
        cls.en, cls.es, cls.en_es = tables["en"]["merged"], tables["es"]["merged"], tables["en-ES"]["merged"]
        cls.parts = {lang: tables[lang]["parts"] for lang in tables}

    def spain_english(self, key):
        """The English the map of Spain shows for `key` (i18n.js: en-ES over en)."""
        return self.en_es.get(key, self.en.get(key))

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
        for table in (self.en, self.es, self.en_es):
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

    def test_spain_english_covers_spanish(self):
        """Every string the map of Spain can show in Spanish has an English one with the same placeholders and plurals."""
        def holes(v):
            return {h for t in (v.values() if isinstance(v, dict) else [v]) for h in re.findall(r"\{(\w+)\}", t)}

        bad = {}
        for k, v in self.es.items():
            e = self.spain_english(k)
            if e is None or holes(e) != holes(v) or isinstance(e, dict) != isinstance(v, dict):
                bad[k] = (e, v)
        self.assertEqual(bad, {})

    def test_en_es_only_overrides_known_keys_in_their_part(self):
        self.assertEqual(sorted(k for k in self.en_es if k not in self.es or k.endswith(".us")), [])
        part_of = {k: f for f, keys in self.parts["en"].items() for k in keys}
        for f, keys in self.parts["en-ES"].items():
            for k in keys:
                self.assertEqual(part_of.get(k), f, k)
        self.assertEqual(sorted(k for k in self.en_es if self.en_es[k] == self.en.get(k)), [], "same as the US English")

    # English words about the United States, and the Spanish that allows each in a Spain English string: a key whose
    # Spanish speaks of the US too (the FEMA, the FAF's states and dollars) keeps them.
    US_TERMS = [
        (r"\bcount(y|ies)\b", r"condado"),
        (r"\bU\.S\.|\bUS\b|United States|\bAmerican", r"EE\. ?UU\.|Estados Unidos|estadounidense"),
        (r"\bdollars?\b|\$", r"dólar|\$"),
        (r"\bstates?\b|\bState\b", r"\bestados?\b"),
        (r"\bmetros?\b|\bmetropolitan\b|\bmicropolitan\b|\bmicros?\b", r"metropolitan|\bmicro"),
        (r"\bACS\b|\bCensus Bureau\b|\bCensus population estimates\b|\bB\d{5}\b", r"\bACS\b"),
        (r"\bBEA\b", r"\bBEA\b"), (r"\bBLS\b|\bQCEW\b", r"\bBLS\b|\bQCEW\b"), (r"\bOMB\b", r"\bOMB\b"),
        (r"\bFIPS\b", r"\bFIPS\b"), (r"\bFEMA\b|\bfederal\b", r"\bFEMA\b|federal"), (r"\bFAF\d?\b", r"\bFAF"),
        (r"\bUSACE\b|\bFAA\b|\bNPS\b|\bDoD\b|\bUSGS\b|\bEIA\b|\bMSHA\b", r"\bUSACE\b|\bFAA\b|\bNPS\b|\bDoD\b"),
        (r"lower 48|contiguous|\bAlbers\b|Alaska|Hawaii|Canada|Mexico", r"\b48\b|contiguos|Alaska|Hawái|Canadá|México"),
        (r"\bpounds\b|\blb\b|short tons", r"libras|toneladas cortas"),
    ]

    def test_spain_english_speaks_of_spain(self):
        # {placeholders} and file names (states.json, counties.json) are code, not words shown about the US.
        text = lambda v: re.sub(r"\{\w+\}|\b\w+\.json\b", " ", " ".join(v.values()) if isinstance(v, dict) else v)
        found = []
        for k, v in self.es.items():
            e = text(self.spain_english(k) or "")
            for us, es in self.US_TERMS:
                if re.search(us, e) and not re.search(es, text(v)):
                    found.append(f"{k}: {re.search(us, e).group(0)!r} in {e[:90]!r}")
        self.assertEqual(found, [], "\n".join(found))

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

    def test_spain_in_english_takes_its_own_strings(self):
        got = self.run_t({"id": "es", "lang": "en", "locale": "en-IE"}, "[t('page.search.placeholder'), t('page.loading')]")
        self.assertEqual(got, ["Search cities, provinces or people", "Surveying the land…"])
        self.assertEqual(self.run_t({}, "t('page.search.placeholder')"), "Search cities & states")

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

    def test_spain_english_formats(self):
        """Spain in English: en-IE, the English of a euro country, with the euro sign in front."""
        self.assertEqual(self.formats({"locale": "en-IE", "currency": "EUR", "lang": "en"}), [
            "950", "1.2K", "123.5K", "1.6M", "1.6B", "2.1T", "€2.1T", "€35,200", "1,234,567", "12.3%", "50%", "6.6M",
            "350K", "3.3"])
        tails = lambda country: json.loads(node(f"""
            import {{ setCountry }} from './web/js/app/country.js';
            import {{ withPct, withCurrency }} from './web/js/format.js';
            setCountry({{ country: {json.dumps(country)} }}, null);
            console.log(JSON.stringify([withPct("12"), withCurrency("5")]));
        """))
        self.assertEqual(tails({"locale": "en-IE", "currency": "EUR"}), ["12%", "€5"])
        self.assertEqual(tails({"locale": "es-ES", "currency": "EUR"}), ["12\u00a0%", "5\u00a0€"])
        self.assertEqual(tails({}), ["12%", "$5"])

    def test_spanish_formats(self):
        nb = " "
        self.assertEqual(self.formats({"locale": "es-ES", "currency": "EUR", "lang": "es"}), [
            "950", f"1,2{nb}mil", f"123,5{nb}mil", f"1,6{nb}M", f"1600{nb}M", f"2,1{nb}B", f"2,1{nb}B{nb}€", f"35.200{nb}€",
            "1.234.567", f"12,3{nb}%", f"50{nb}%", f"6,6{nb}M", f"350{nb}mil", "3,3"])


@unittest.skipUnless(NODE, "node is not installed")
class LanguageJsTest(unittest.TestCase):
    def test_overlay_lays_texts_over_lists_and_objects(self):
        got = json.loads(node("""
            import { overlay } from './web/js/app/data.js';
            const data = { vintage: "Padrón", lenses: [{ name: "Renta", values: [1, 2] }, { name: "Museos", names: ["Prado", "Catedral (+1)"] }] };
            overlay(data, { vintage: "INE Padrón", lenses: { "0": { name: "Income" }, "1": { names: { "1": "Cathedral (+1)" } } } });
            console.log(JSON.stringify(data));
        """))
        self.assertEqual(got, {"vintage": "INE Padrón", "lenses": [{"name": "Income", "values": [1, 2]},
                                                              {"name": "Museos", "names": ["Prado", "Cathedral (+1)"]}]})

    def test_load_data_fetches_the_overlay_of_the_chosen_language(self):
        got = json.loads(node("""
            import { setCountry } from './web/js/app/country.js';
            import { loadData } from './web/js/app/data.js';
            const files = { "data/x.json": { name: "Renta", n: 3 }, "data/x.en.json": { name: "Income" } };
            const asked = [];
            globalThis.fetch = async (path) => { asked.push(path); return { ok: path in files, status: 404, json: async () => structuredClone(files[path]) }; };
            const page = (text) => ({ getElementById: (id) => (id === "country-page" ? { textContent: JSON.stringify(text) } : null) });
            globalThis.location = new URL("https://spainciv.example/#lang=en");
            setCountry({ country: { id: "es" } }, page({ lang: "es", langs: { es: "es-ES", en: "en-IE" } }));
            const english = await loadData("x");
            globalThis.location = new URL("https://spainciv.example/#lang=es");
            setCountry({ country: { id: "es" } }, page({ lang: "es", langs: { es: "es-ES", en: "en-IE" } }));
            const spanish = await loadData("x");
            setCountry({ country: { id: "es" } }, page({ lang: "es", data: ["x"] }));
            const missing = await loadData("military").then(() => "loaded", (e) => e.message);
            console.log(JSON.stringify({ english, spanish, asked, missing }));
        """))
        self.assertEqual(got["english"], {"name": "Income", "n": 3})
        self.assertEqual(got["spanish"], {"name": "Renta", "n": 3})
        # A file the site does not list (page settings `data`) is never asked for: no 404 in the console.
        self.assertEqual(got["asked"], ["data/x.json", "data/x.en.json", "data/x.json"])
        self.assertIn("not in this map", got["missing"])

    def test_pick_lang_follows_url_then_saved_then_browser_then_first(self):
        got = json.loads(node("""
            import { pickLang } from './web/js/app/country.js';
            const langs = { es: "es-ES", en: "en-IE" };
            const at = (hash) => new URL(`https://spainciv.example/${hash}`);
            console.log(JSON.stringify([
                pickLang(langs, { loc: at("#lang=en&lens=income"), saved: "es", browser: ["es-ES"] }),
                pickLang(langs, { loc: at(""), saved: "es", browser: ["en-US"] }),
                pickLang(langs, { loc: at("#lang=xx"), saved: null, browser: ["fr-FR", "en-GB"] }),
                pickLang(langs, { loc: at(""), saved: null, browser: ["fr-FR"] }),
                pickLang(langs, { loc: at(""), saved: null, browser: [] }),
                pickLang(undefined, { loc: at("#lang=en"), saved: "en", browser: ["en"] }),
            ]));
        """))
        self.assertEqual(got, ["en", "es", "en", "es", "es", None])


class SpanishDataTest(unittest.TestCase):
    """Spain's data files (sites/es/data) are read by Spanish speakers: a text in them that carries common English
    words is a leftover of a US builder or of an English source (a vintage, a plant name, a unit).

    A small heuristic: words that are English and spelled like no Spanish (or Catalan, Galician, Basque) word, in every
    string that is not an id or a code. Proper names that hold one go in PROPER_NAMES, with the reason they stay."""

    DATA = ROOT / "sites" / "es" / "data"
    # Keys whose values are ids or codes, never shown as text.
    CODES = {"id", "type", "kind", "key", "icon", "motif", "rule", "group", "format", "scale", "higher_is", "color", "dark",
             "source", "sources", "file", "files", "sha256", "url", "cbsa", "county", "state", "naics", "via", "basis",
             "component", "tier", "status", "branch_from", "osm", "installation", "hex_state",  # military.json
             "district", "category", "unit_type", "qid", "ramp", "kinds", "industries", "site_url", "product", "lang",
             "locale", "currency",
             "map", "natural_wonders",  # unciv.json: the Unciv map and wonder, in the game's own (English) identifiers
             "bare", "start_bias", "resource", "seat"}  # the bare map like the map; a nation's Unciv terrain, resource, seat
    CODE_VALUES = {"workers", "usd", "eur"}  # nation.json yields[].unit
    # (file, key) whose values are people's names as Wikidata writes them: some have only an English label ("Mark of
    # Toledo") and some surnames are English words ("Eva Forest").
    PEOPLE = {("personajes.json", "name")}
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
                    if k not in self.CODES and (name, k) not in self.PEOPLE:
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
        found = [f for p in data_files() for f in self.leftovers(p.name)]
        self.assertEqual(found, [], "\n".join(found[:40]))

    def test_the_heuristic_catches_the_old_leftovers(self):
        for text in ("AENA 2025 (final) boardings", "Las Majas Wind Farm (+1)", "SIIU, students 2024-2025",
                     "OAPN, Red de Parques Nacionales; visitors 2025", "Naval Museum of Cartagena"):
            self.assertTrue(self.english_words(text), text)
        for text in ("Andén 0", "Museu de la Farmàcia Catalana", "Estación de Metro Ópera", "Areas Gordas (Sanxenxo)",
                     "CORINE Land Cover 2018", "MAPA: CC BY 4.0", "miles de toneladas"):
            self.assertFalse(self.english_words(text), text)


DATA = ROOT / "sites" / "es" / "data"
LANGS = ("es", "en")


def data_files() -> list:
    """Spain's data files: <name>.json, without the overlays (<name>.<lang>.json)."""
    return sorted(p for p in DATA.glob("*.json") if "." not in p.stem)


class EnglishDataTest(unittest.TestCase):
    """Spain's data files in English: each file with its English overlay (pipeline/core/lang.py), as the map shows them
    when English is picked. A plain string stays the same in both languages, so it must be a proper name, a code or a
    number; any generated text must have its English version, and that English must not carry Spanish.

    A small heuristic, the mirror of SpanishDataTest: words that are Spanish and spelled like no English word, in every
    string that is not an id or a code and not a proper name. Proper names keep their own language (DECISIONS): they
    are the keys in NAME_KEYS, whose strings are also taken out of the file's other texts before the check, with the
    names of the municipalities, provinces, rivers and cities of world.json."""

    CODES = SpanishDataTest.CODES
    # (file, path) of the strings that are names as their source writes them; a path is the keys from the file's root,
    # "[]" for any list item.
    NAME_KEYS = {
        ("personajes.json", ".people[].name"), ("personajes.json", ".people[].place"),
        ("world.json", ".counties[].name"), ("world.json", ".states[].name"), ("world.json", ".rivers[].name"),
        ("world.json", ".country.projection.insets[].name"),
        ("cities.json", "[].name"), ("states.json", "[].name"), ("states.json", "[].community.name"),
        ("infrastructure.json", ".airports[].name"), ("infrastructure.json", ".ports[].name"),
        ("resources.json", ".items[].name"),
        ("wonders.json", ".wonders[].name"), ("wonders.json", ".wonders[].short"), ("wonders.json", ".wonders[].metrics.municipality"),
        ("lenses.json", ".lenses[].names[]"),  # museums, castles, dishes, fiestas, beaches, denominations: see NAMED_SUFFIX
        # the fiesta calendar, each text as its official source writes it (a date included: "15 de agosto")
        *(("fiestas.json", f".fiestas[].{k}") for k in ("name", "community", "place", "declaration", "when")),
        ("unciv.json", ".summary.starts[].city"), ("unciv.json", ".summary.map_name"),
        ("unciv.json", ".summary.not_placed_designations[]"),  # denomination names; their kind is checked as a suffix
        ("unciv.json", ".summary.nations[].name"), ("unciv.json", ".summary.nations[].cities[]"),  # communities, municipalities
        ("sources.json", "[].publisher"),  # bodies by their own names (Instituto Nacional de Estadística, ADEAC…)
        # military installations and their parts as OpenStreetMap names them
        ("military.json", ".installations[].name"), ("military.json", ".installations[].parts[]"),
        ("military.json", ".ranges[].name"),
        # reservoirs and basins as the Boletín Hidrológico writes them ("Breña, La", "Miño - Sil")
        ("embalses.json", ".reservoirs[].name"), ("embalses.json", ".basins[].name"),
    }
    # (file, path) → the parts of its strings that are names: an urban area's AUDES name before "urban area"; in a
    # resource's detail, the plant it names ("including … (") and the company and municipality of a mine.
    NAME_PARTS = {
        ("cities.json", "[].full"): [re.compile(r"^.+(?= urban area$)")],
        ("resources.json", ".items[].detail"): [re.compile(r"(?<=including ).+?(?= \()"), re.compile(r"^[^;]+; [^;]+;")],
        ("military.json", ".components[].name"): [re.compile(r"\([^()]+\)$")],  # the branch's official Spanish name
        ("unciv.json", ".summary.nations[].leader"): [re.compile(r"Junta de Comunidades")],  # Castilla-La Mancha's institution
    }
    # An id made from a name ("base-aerea-de-zaragoza-ea", military.json), never shown.
    SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")
    # What a text quotes is cited as its source writes it (a deposit's name, INE's citation formula, a category title).
    QUOTED = re.compile(r"“[^”]*”|«[^»]*»|\"[^\"]*\"|(?<!\w)'[^']+'(?!\w)")
    # The lens whose categories are proper names: the ancient peoples, in Latin or Greek as Pleiades writes them.
    NAME_CATEGORIES = {"peoples"}
    # In a name the map writes a kind after (“Queso de la Serena (DOP · provincia)”), that kind is the map's own text.
    NAMED_SUFFIX = re.compile(r"\(([^()]*·[^()]*)\)\s*$")
    SPANISH = set("""de del los las con por para que una unos unas sus según más también desde hasta entre cada como
        municipio municipios provincia provincias hexágono hexágonos habitantes población ocupados datos año años mapa
        renta alquiler paro proporción mediana superficie visitantes matriculados toneladas pasajeros mercancías
        aeropuerto aeropuertos puerto puertos área áreas urbana urbanas lente fuente centrales planta yacimiento
        comunidad zona zonas cuenta cuentan muestra muestras tierra suelo costa ríos sitios sitio lugar lugares nacional
        nacidos personas incluye incluidos ninguna ninguno otros otras catedral catedrales museo museos castillo castillos
        playa playas platos cooficial municipales pueblo pueblos sección división sectores cifra cifras parque eólico
        mina minas dop igp""".split())  # DOP and IGP are PDO and PGI in English
    # Bodies and terms that keep their Spanish name in English text, as their publishers write them.
    KEEP = [
        # each community's name for its declaration (Fiesta de Interés Turístico de Andalucía…), before the State's
        # shorter "Fiesta de Interés Turístico" below takes their first words
        re.compile("|".join(re.escape(x) for x in sorted({c["declaration"] for c in COMMUNITIES.values()}, key=len,
                                                           reverse=True))),
        re.compile(r"\b(Atlas Digital de las Áreas Urbanas|Atlas Nacional de España|Instituto Geográfico Nacional|"
                   r"Instituto Nacional de Estadística|Puertos del Estado|Red de Parques Nacionales|Contabilidad Regional"
                   r"(?: de España)?|Censo Agrario|Estadística Minera de España|Panorama Minero|Ministerio [\w ,]+?(?=[),;.]|$)|"
                   r"Secretaría de Estado de Turismo|Fiestas? de Interés Turístico(?: Internacional(?: and Nacional)?| Nacional)?|"
                   r"Bienes? de Interés Cultural|Bandera Azul|Ley(?: Foral)? [\d/]+|Llei [\d/]+|Orden [A-Z]+/[\d/]+|"
                   r"Sistema Integrado de Información Universitaria|Atlas de Distribución de Renta de los Hogares|"
                   r"Indicadores Demográficos Básicos|Movimiento Natural de la Población|Censo anual de población|"
                   r"Censos de Población y Viviendas|calidad_diferenciada_zonas|vino de pago|Vinos? de la Tierra|"
                   r"Estadística sobre actividades de I\+D|Relación con la actividad|Grandes Áreas Urbanas|"
                   r"Calidad diferenciada|Estadística de Matrimonios|Balance de Criminalidad|Sistema Estadístico de Criminalidad|"
                   r"Portal Estadístico de Criminalidad|Policía (?:Nacional|Foral de Navarra)|Convenio de Cooperación para la Defensa|"
                   r"Sistema Estatal de Referencia del Precio del Alquiler de Vivienda|datos\.gob\.es|Sierra de Guadarrama|"
                   # the two names the Ministry maps that the EU register no longer has (DECISIONS E64)
                   r"Aceite de la Comunitat Valenciana|Carne Morucha de Salamanca)\b",
                   re.I),
        re.compile(r"\bMAPA\b"),  # the Ministry of Agriculture's acronym (and "mapa", the word, stays a Spanish word)
    ]

    @classmethod
    def setUpClass(cls):
        world = json.loads((DATA / "world.json").read_text(encoding="utf-8"))
        cities = json.loads((DATA / "cities.json").read_text(encoding="utf-8"))
        cls.places = {x["name"] for k in ("counties", "states", "rivers") for x in world.get(k, [])} | \
                     {c["name"] for c in cities} | {c.get("full", "") for c in cities}
        cls.places = {n for n in cls.places if isinstance(n, str) and n}

    @staticmethod
    def english(x):
        """The English view of a joined file: each Text's English, plain strings as they are."""
        if isinstance(x, Text):
            return x["en"]
        if isinstance(x, dict):
            return {k: EnglishDataTest.english(v) for k, v in x.items()}
        if isinstance(x, list):
            return [EnglishDataTest.english(v) for v in x]
        return x

    def words(self, text: str, names: list[str]) -> set[str]:
        tokens = lambda s: {w.lower() for w in re.findall(r"[^\W\d_]+", s)}
        if not tokens(text) & self.SPANISH:
            return set()
        for p in [self.QUOTED, *self.KEEP]:
            text = p.sub(" ", text)
        for n in names:
            if n in text:
                text = text.replace(n, " ")
        return tokens(text) & self.SPANISH

    def leftovers(self, name: str) -> list[str]:
        doc = self.english(read_web(DATA, name, LANGS))
        texts, names = [], set()

        def walk(x, path, lens=None):
            if isinstance(x, dict):
                lens = x.get("id", lens) if path.endswith("lenses[]") else lens
                for k, v in x.items():
                    if k not in self.CODES and (name, k) not in SpanishDataTest.PEOPLE:
                        walk(v, f"{path}.{k}", lens)
            elif isinstance(x, list):
                for v in x:
                    walk(v, f"{path}[]", lens)
            elif isinstance(x, str) and not x.startswith("http") and x not in SpanishDataTest.CODE_VALUES \
                    and not self.SLUG.match(x):
                proper = (name, path) in self.NAME_KEYS or (path.endswith("categories[].name") and lens in self.NAME_CATEGORIES)
                if proper:
                    names.add(x)
                    suffix = self.NAMED_SUFFIX.search(x)
                    if suffix:
                        texts.append((path, suffix.group(1)))
                else:
                    for part in self.NAME_PARTS.get((name, path), []):
                        x = part.sub(" ", x)
                    texts.append((path, x))

        walk(doc, "")
        ordered = sorted(names | self.places, key=len, reverse=True)
        return [f"{name}{path}: {x[:100]!r} ({', '.join(sorted(w))})" for path, x in texts if (w := self.words(x, ordered))]

    def test_no_spanish_in_english_texts(self):
        found = [f for p in data_files() for f in self.leftovers(p.name)]
        self.assertEqual(found, [], "\n".join(found[:60]) + f"\n… {len(found)} in all")

    def test_the_heuristic_catches_spanish(self):
        for text in ("Proporción de los matrimonios", "4 centrales, entre ellas Planta solar Perseo", "(IGP · provincia)",
                     "Área urbana de Murcia"):
            self.assertTrue(self.words(text, []), text)
        for text in ("Murcia urban area", "(PGI · province)", "INE Padrón, 1 January 2025", "Las Majas wind farm",
                     "Source: Atlas Digital de las Áreas Urbanas (Ministry of Housing)"):
            self.assertFalse(self.words(text, ["Las Majas"]), text)

    def test_every_file_has_an_english_overlay_of_texts(self):
        def check(base, over, path):
            if isinstance(over, str):
                self.assertIsInstance(base, str, f"{path}: the overlay replaces a {type(base).__name__}")
                return
            self.assertIsInstance(over, dict, f"{path}: an overlay holds strings in objects, not {type(over).__name__}")
            for k, v in over.items():
                if isinstance(base, list):
                    self.assertTrue(k.isdigit() and int(k) < len(base), f"{path}/{k}: no such item")
                    check(base[int(k)], v, f"{path}/{k}")
                else:
                    self.assertIn(k, base, f"{path}/{k}: no such key")
                    check(base[k], v, f"{path}/{k}")

        for p in data_files():
            overlay = DATA / f"{p.stem}.en.json"
            self.assertTrue(overlay.exists(), overlay.name)
            check(json.loads(p.read_text(encoding="utf-8")), json.loads(overlay.read_text(encoding="utf-8")), p.name)
        stray = sorted(o.name for o in DATA.glob("*.*.json") if not (DATA / f"{o.name.split('.')[0]}.json").exists())
        self.assertEqual(stray, [])


if __name__ == "__main__":
    unittest.main()
