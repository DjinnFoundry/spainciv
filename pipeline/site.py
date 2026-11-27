"""The published page of the active country: web/index.html, and the country's own site files.

web/index.html is written for the United States and is published as is for it. A country with a `page`
(countries.base.Page) gets, when the site is served (`serve`) or packaged (`package`):

- its language, title, description and social cards (canonical, og:*, twitter:*), with absolute URLs built from
  `site_url`; the card image is `https://<site_url>/og-image.png`, drawn from the country's data (pipeline/card.py);
- a credit line on the map: its data sources, the licence notices its sources require, and usaciv's credit;
- `<script id="country-page">`: lang, site_url, data_credit and notices as JSON, which web/js/app/country.js lays over
  the world.json `country` block (so a new address or credit needs no data rebuild), and `play` when the country has
  an Unciv map, and `data`, the names of its data files; a country in several languages adds `langs` (each language's
  number locale) and `texts`, the page's texts in every language but the first; `game: true` when the country
  has the daily game (web/js/ext/game), `sunset: true` when it has the sun lens (web/js/ext/sun), and `explore`, the
  groups of regions of the fog of war (web/js/ext/explore), in each language like the other texts;
- the Unciv page and downloads (pipeline/play.py) when its build made an Unciv map.

generated_files() lists what is written from code rather than copied from web/, for `serve` and `package` alike.

The head and the credits are written in the country's first language, the language of the data files: link previews
never run the page, so they cannot follow the language a visitor picks. The page switches its own texts when another
language is chosen (web/js/app/country.js).
"""

from __future__ import annotations

import json
import re
from html import escape
from typing import Callable

from . import play
from .card import card_png
from .core.paths import WEB
from .countries import Country, active

USACIV_URL = "https://karpathy.ai/usaciv/"


def _attr(value: str) -> str:
    return escape(value, quote=True)


def _set(html: str, pattern: str, replacement) -> str:
    """Replace the one match of `pattern` (with a string, or a function of the match); index.html must have exactly
    one, so a changed template fails loudly instead of publishing the US cards."""
    new, n = re.subn(pattern, replacement if callable(replacement) else (lambda _m: replacement), html)
    if n != 1:
        raise ValueError(f"web/index.html: expected one match of {pattern!r}, found {n}")
    return new


def _meta(html: str, attr: str, name: str, value: str) -> str:
    return _set(html, rf'<meta {attr}="{re.escape(name)}" content="[^"]*">', f'<meta {attr}="{name}" content="{_attr(value)}">')


def credits_inner(country: Country, lang: str) -> str:
    """The map's credit line in `lang`, as HTML: data sources, licence notices, usaciv's credit."""
    page = country.page.in_lang(lang)
    link = f'<a href="{USACIV_URL}" target="_blank" rel="noopener">usaciv</a>'
    text = " · ".join([escape(page.data_credit), *map(escape, page.notices)])
    for label, url in page.links:
        text = text.replace(escape(label), f'<a href="{_attr(url)}" target="_blank" rel="noopener">{escape(label)}</a>', 1)
    return f'{text} · {escape(page.based_on).replace("{usaciv}", link)}'


def credits_html(country: Country) -> str:
    return f'<p id="map-credits" class="map-credits">{credits_inner(country, country.lang)}</p>'


def page_config(country: Country) -> dict:
    """What the browser takes from the page rather than from world.json (see web/js/app/country.js); `play` is the
    "Jugar en Unciv" page of a country with an Unciv map (pipeline/play.py), which the help dialog links to. A country
    in several languages adds `langs` and, for each language but the first, `texts`: what changes with the language."""
    has_play = play.load(country) is not None

    def texts(lang: str) -> dict:
        page = country.page.in_lang(lang)
        out = {"data_credit": page.data_credit, "notices": list(page.notices)}
        if page.explore is not None:
            out["explore"] = {"groups": [{"name": name, "regions": list(regions)} for name, regions in page.explore]}
        return out | {"play": play.PAGES[lang]} if has_play else out

    # The data files the site has, so the browser does not ask for the US-only ones (and log a 404 for each).
    data = sorted(p.stem for p in country.web_data_dir.glob("*.json") if "." not in p.stem)
    config = {"lang": country.lang, "site_url": country.site_url, **texts(country.lang), "data": data}
    config |= {flag: True for flag in ("game", "sunset") if getattr(country.page, flag)}
    if len(country.langs) > 1:
        config["langs"] = dict(country.locales)
        config["texts"] = {lang: texts(lang) | {"description": country.page.in_lang(lang).description,
                                                "credits": credits_inner(country, lang)} for lang in country.langs[1:]}
    return config


def render_index(html: str, country: Country | None = None) -> str:
    """web/index.html for a country: unchanged without a `page`, else with the country's head and map credits."""
    c = country or active()
    if c.page is None:
        return html
    page = c.page.in_lang(c.lang)
    url = f"https://{c.site_url}/"
    image = url + "og-image.png"
    html = _set(html, r'<html lang="[^"]*">', f'<html lang="{_attr(c.lang)}">')
    html = _set(html, r"<title>[^<]*</title>", f"<title>{escape(page.title)}</title>")
    html = _meta(html, "name", "description", page.description)
    html = _set(html, r'<link rel="canonical" href="[^"]*">', f'<link rel="canonical" href="{_attr(url)}">')
    for prop, value in (
        ("og:site_name", c.product),
        ("og:title", page.card_title),
        ("og:description", page.description),
        ("og:url", url),
        ("og:image", image),
        ("og:image:alt", page.image_alt),
    ):
        html = _meta(html, "property", prop, value)
    for name, value in (
        ("twitter:title", page.card_title),
        ("twitter:description", page.description),
        ("twitter:image", image),
        ("twitter:image:alt", page.image_alt),
    ):
        html = _meta(html, "name", name, value)
    config = json.dumps(page_config(c), ensure_ascii=False).replace("</", "<\\/")
    script = f'<script type="application/json" id="country-page">{config}</script>'
    html = _set(html, r'<link rel="stylesheet" href="css/style.css">', lambda m: f"{script}\n  {m.group(0)}")
    return _set(html, r'<canvas id="map"[^>]*></canvas>', lambda m: m.group(0) + "\n  " + credits_html(c))


def index_bytes(country: Country | None = None) -> bytes:
    """The country's index.html, ready to serve or package."""
    return render_index((WEB / "index.html").read_text(encoding="utf-8"), country).encode("utf-8")


# Cloudflare Pages headers for a country we publish: scripts and styles revalidate on every visit, like the page and
# the data already do. Pages' default lets a browser keep them 4 hours, so after a deploy a returning visitor ran the
# old scripts against the new data (the fiesta calendar link opened the plain map).
HEADERS = """/js/*
  Cache-Control: public, max-age=0, must-revalidate
/css/*
  Cache-Control: public, max-age=0, must-revalidate
"""


def generated_files(country: Country | None = None) -> dict[str, Callable[[], bytes]]:
    """Site files made from code, by path in the site: index.html, og-image.png and the Pages `_headers` for a country
    with a `page` (the US keeps web/og-image.png), and the Unciv page and downloads of a country with an Unciv map
    (pipeline/play.py)."""
    c = country or active()
    files = {"index.html": lambda: index_bytes(c)}
    if c.page is not None:
        files["og-image.png"] = lambda: card_png(c)
        files["_headers"] = lambda: HEADERS.encode("utf-8")
        files |= play.files(c)
    return files
