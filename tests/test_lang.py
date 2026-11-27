"""core.lang: texts in several languages, their overlays in the web data files, and numbers by language."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline import countries
from pipeline.core import store
from pipeline.core.lang import Num, Text, join, join_texts, num, pct, split, tr

LANGS = ("es", "en")


class TextTest(unittest.TestCase):
    def test_format_writes_numbers_in_each_language(self):
        t = tr("Los {n} museos ({mw} MW) de {place}", "The {n} museums ({mw} MW) of {place}")
        got = t.format(n=12345, mw=Num(148.25, 1), place=tr("España", "Spain"))
        self.assertEqual(got, {"es": "Los 12.345 museos (148,2 MW) de España", "en": "The 12,345 museums (148.2 MW) of Spain"})

    def test_concatenation_and_join(self):
        self.assertEqual(tr("a", "b") + " c", {"es": "a c", "en": "b c"})
        self.assertEqual("x " + tr("a", "b"), {"es": "x a", "en": "x b"})
        self.assertEqual(join_texts(["Toledo", tr("catedral", "cathedral")]), {"es": "Toledo, catedral", "en": "Toledo, cathedral"})
        self.assertEqual(join_texts(["a", "b"], "; "), "a; b")

    def test_a_text_needs_every_string(self):
        with self.assertRaises(ValueError):
            tr("Renta", "")

    def test_numbers(self):
        self.assertEqual([num(1234), num(12345), num(2.5), num(1234.5, 1)], ["1234", "12.345", "2,5", "1234,5"])
        self.assertEqual([num(1234, lang="en"), num(2.5, lang="en"), num(1234567.25, 2, "en")], ["1,234", "2.5", "1,234,567.25"])
        self.assertEqual([pct(0.125, 1), pct(0.125, 1, "en")], ["12,5 %", "12.5%"])


class SplitTest(unittest.TestCase):
    DATA = {"vintage": "INE Padrón", "lenses": [
        {"id": "income", "name": tr("Renta", "Income"), "values": [1, 2, 3]},
        {"id": "museums", "name": tr("Museos", "Museums"), "names": ["Museo del Prado", tr("Catedral (+1)", "Cathedral (+1)")]},
        {"id": "same", "name": tr("Patrimonio", "Patrimonio")}]}

    def test_split_keeps_values_and_only_differing_texts(self):
        base, overlays = split(self.DATA, LANGS)
        self.assertEqual(base["lenses"][1], {"id": "museums", "name": "Museos", "names": ["Museo del Prado", "Catedral (+1)"]})
        self.assertEqual(overlays, {"en": {"lenses": {"0": {"name": "Income"}, "1": {"name": "Museums", "names": {"1": "Cathedral (+1)"}}}}})

    def test_join_is_the_inverse(self):
        base, overlays = split(self.DATA, LANGS)
        joined = join(base, overlays, "es")
        self.assertEqual(split(joined, LANGS), (base, overlays))
        self.assertIsInstance(joined["lenses"][0]["name"], Text)
        self.assertEqual(joined["lenses"][2]["name"], "Patrimonio")  # the same in both: a plain string

    def test_a_text_must_have_the_country_languages(self):
        with self.assertRaisesRegex(ValueError, "/lenses/0/name"):
            split({"lenses": [{"name": Text(es="Renta")}]}, LANGS)

    def test_one_language_is_untouched(self):
        data = {"a": ["x", 1]}
        self.assertEqual(split(data, ("en",)), (data, {}))


class WriteWebTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.web = Path(tmp.name)

    def write(self, country_id, data):
        with countries.using(country_id, web_data_dir=self.web), mock.patch("builtins.print"):
            store.write_web("x.json", data)
            return store.load_web("x.json"), store.load_web("x.json", texts=True)

    def test_spain_writes_an_english_overlay(self):
        plain, texts = self.write("es", {"name": tr("Renta", "Income"), "n": 3})
        self.assertEqual(plain, {"name": "Renta", "n": 3})
        self.assertEqual(json.loads((self.web / "x.en.json").read_text()), {"name": "Income"})
        self.assertEqual(texts, {"name": {"es": "Renta", "en": "Income"}, "n": 3})

    def test_an_overlay_is_written_even_when_empty(self):
        self.write("es", {"name": "Madrid"})
        self.assertEqual((self.web / "x.en.json").read_text(), "{}")

    def test_the_us_has_no_overlay(self):
        plain, texts = self.write("us", {"name": "Texas"})
        self.assertEqual(plain, texts)
        self.assertEqual([p.name for p in self.web.iterdir()], ["x.json"])


if __name__ == "__main__":
    unittest.main()
