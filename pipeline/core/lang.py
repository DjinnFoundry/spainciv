"""Texts in several languages in the web data files, and numbers as each language writes them.

A country published in more than one language (countries.base.Country.locales, Spain: Spanish and English) has its
builders write every generated text as a `Text`, {lang: string}. A plain string is the same in every language: a
proper name as its source writes it (a place, a person, a dish, a museum), a code, a number. `write_web` splits the
data in two kinds of file (`split`):

- `<name>.json`, the file the browser always loads, with every text in the country's first language;
- `<name>.<lang>.json` for each other language, an overlay with only the texts that differ, at the same path (a list
  index is an object key, `{"lenses": {"3": {"name": "Income"}}}`), which web/js/app/data.js lays over the file.

The numeric arrays are never repeated, so an overlay holds texts only. `load_web(..., texts=True)` puts the overlays
back (`join`) for a builder that rewrites another builder's file. The US has one language: no Text, no overlay, its
files byte for byte as before.
"""

from __future__ import annotations

import re
from typing import Any


class Text(dict):
    """A text in each language of the country: Text(es="Renta", en="Income")."""

    def __init__(self, **by_lang: str):
        missing = [lang for lang, s in by_lang.items() if not isinstance(s, str) or not s]
        if missing:
            raise ValueError(f"Text without a string for {', '.join(missing)}: {by_lang!r}")
        super().__init__(by_lang)

    def format(self, **values) -> "Text":
        """Fill {placeholders} in each language: a number goes in as that language writes it (`num`; Num(x, d) for d
        decimals), a Text with its own language's string, anything else as it is."""
        def one(lang: str, v):
            if isinstance(v, Text):
                return v[lang]
            if isinstance(v, Num):
                return num(v.x, v.decimals, lang)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return num(v, None, lang)
            return v

        return Text(**{lang: s.format(**{k: one(lang, v) for k, v in values.items()}) for lang, s in self.items()})

    def map(self, fn) -> "Text":
        """The same function applied to the text of each language: fn(text, lang)."""
        return Text(**{lang: fn(s, lang) for lang, s in self.items()})

    def __add__(self, other):
        if isinstance(other, Text):
            return Text(**{lang: s + other[lang] for lang, s in self.items()})
        return Text(**{lang: s + other for lang, s in self.items()})

    def __radd__(self, other):
        return Text(**{lang: other + s for lang, s in self.items()})


class Num:
    """A number for Text.format with a fixed number of decimals."""

    def __init__(self, x: float, decimals: int | None = None):
        self.x, self.decimals = x, decimals


def tr(es: str, en: str) -> Text:
    """A Spanish text and its English version."""
    return Text(es=es, en=en)


def pick(value, lang: str):
    """The string of a Text in `lang`; anything else as it is."""
    return value[lang] if isinstance(value, Text) else value


def pick_all(x, lang: str):
    """`x` (a Text, or a dict, list or tuple holding some) with every Text in `lang`."""
    if isinstance(x, Text):
        return x[lang]
    if isinstance(x, dict):
        return {k: pick_all(v, lang) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return type(x)(pick_all(v, lang) for v in x)
    return x


def num(x: float, decimals: int | None = None, lang: str = "es") -> str:
    """A number as the language writes it. Spanish: decimal comma and a thousands point from five digits on ("1000",
    "12.000", "2,5", as the RAE asks); English: decimal point and a thousands comma ("1,000", "12,000", "2.5")."""
    if decimals is None and float(x).is_integer():
        x = int(x)
    whole, _, frac = (f"{x:,.{decimals}f}" if decimals is not None else f"{x:,}").partition(".")
    if lang == "en":
        return whole + ("." + frac if frac else "")
    if len(whole.lstrip("-").replace(",", "")) <= 4:
        whole = whole.replace(",", "")
    return whole.replace(",", ".") + ("," + frac if frac else "")


def pct(x: float, decimals: int = 0, lang: str = "es") -> str:
    """A share as a percentage: "12,5 %" (Spanish, with a space), "12.5%" (English)."""
    return f"{num(x * 100, decimals, lang)}{'%' if lang == 'en' else ' %'}"


def join_texts(parts: list, sep: str = ", ") -> Any:
    """Parts (strings or Texts) joined with `sep`: a Text if any part is one."""
    langs = next((list(p) for p in parts if isinstance(p, Text)), None)
    if langs is None:
        return sep.join(parts)
    return Text(**{lang: sep.join(pick(p, lang) for p in parts) for lang in langs})


def and_list(items: list) -> Text:
    """Items (Texts, or strings that are the same in both languages) joined as a list in each language from its own
    strings: "A, B y C" / "A, B and C", with the Spanish "e" before an i- sound ("Andalucía e Illes Balears")."""
    return _series(items, "y", "and")


def nor_list(items: list) -> Text:
    """The list after a negative: "no llega a A, B ni C" / "does not reach A, B or C"."""
    return _series(items, "ni", "or")


def _series(items: list, es: str, en: str) -> Text:
    if not items:
        raise ValueError("a list of no items")
    words = {"es": es, "en": en}

    def one(lang: str) -> str:
        names = [pick(x, lang) for x in items]
        if len(names) == 1:
            return names[0]
        word = "e" if lang == "es" and es == "y" and re.match(r"(?i)h?i(?![aeiouáéíóú])", names[-1]) else words[lang]
        return f"{', '.join(names[:-1])} {word} {names[-1]}"

    return tr(one("es"), one("en"))


def split(data: Any, langs: tuple[str, ...]) -> tuple[Any, dict[str, Any]]:
    """(data with every Text in langs[0], {other lang: overlay of the texts that differ}). A Text must have exactly the
    country's languages."""
    base_lang, others = langs[0], langs[1:]

    def walk(x, path):
        if isinstance(x, Text):
            if set(x) != set(langs):
                raise ValueError(f"{path or '/'}: a Text needs {', '.join(langs)}, has {', '.join(x)}")
            return x[base_lang], {lang: x[lang] for lang in others if x[lang] != x[base_lang]}
        if not isinstance(x, (dict, list)):
            return x, {}
        walked = [(k, *walk(v, f"{path}/{k}")) for k, v in (x.items() if isinstance(x, dict) else enumerate(x))]
        patches: dict[str, dict] = {}
        for k, _, p in walked:
            for lang, sub in p.items():
                patches.setdefault(lang, {})[str(k)] = sub
        base = {k: b for k, b, _ in walked} if isinstance(x, dict) else [b for _, b, _ in walked]
        return base, patches

    base, patches = walk(data, "")
    return base, {lang: patches.get(lang, {}) for lang in others}


def join(base: Any, overlays: dict[str, Any], base_lang: str) -> Any:
    """The inverse of split: base with a Text wherever an overlay has a string."""
    langs = [base_lang, *overlays]

    def walk(x, over: dict[str, Any]):
        if not over:
            return x
        if isinstance(x, str):
            return Text(**(dict.fromkeys(langs, x) | over))
        if isinstance(x, dict):
            return {k: walk(v, {lang: o[k] for lang, o in over.items() if k in o}) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v, {lang: o[str(i)] for lang, o in over.items() if str(i) in o}) for i, v in enumerate(x)]
        raise ValueError(f"an overlay text over a {type(x).__name__}")

    return walk(base, {lang: o for lang, o in overlays.items() if o})


def overlay_name(name: str, lang: str) -> str:
    """lenses.json → lenses.en.json"""
    return re.sub(r"\.json$", f".{lang}.json", name)
