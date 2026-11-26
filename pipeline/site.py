"""The published page of the active country: web/index.html, and the country's own site files.

web/index.html is written for the United States and is published as is for it. A country with a `page`
(countries.base.Page) gets, when the site is served (`serve`) or packaged (`package`):

- its language, title, description and social cards (canonical, og:*, twitter:*), with absolute URLs built from
  `site_url`; the card image is `https://<site_url>/og-image.png`, drawn from the country's data (pipeline/card.py);
- a credit line on the map: its data sources, the licence notices its sources require, and usaciv's credit;
- `<script id="country-page">`: lang, site_url, data_credit and notices as JSON, which web/js/app/country.js lays over
  the world.json `country` block (so a new address or credit needs no data rebuild), and `play` when the country has
  an Unciv map;
- the Unciv page and downloads (pipeline/play.py) when its build made an Unciv map.

generated_files() lists what is written from code rather than copied from web/, for `serve` and `package` alike.
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


def credits_html(country: Country) -> str:
    page = country.page
    link = f'<a href="{USACIV_URL}" target="_blank" rel="noopener">usaciv</a>'
    parts = [escape(page.data_credit), *map(escape, page.notices), escape(page.based_on).replace("{usaciv}", link)]
    return f'<p id="map-credits" class="map-credits">{" · ".join(parts)}</p>'


def page_config(country: Country) -> dict:
    """What the browser takes from the page rather than from world.json (see web/js/app/country.js); `play` is the
    "Jugar en Unciv" page of a country with an Unciv map (pipeline/play.py), which the help dialog links to."""
    config = {"lang": country.lang, "site_url": country.site_url, "data_credit": country.page.data_credit, "notices": list(country.page.notices)}
    if play.load(country) is not None:
        config["play"] = play.PAGE
    return config


def render_index(html: str, country: Country | None = None) -> str:
    """web/index.html for a country: unchanged without a `page`, else with the country's head and map credits."""
    c = country or active()
    page = c.page
    if page is None:
        return html
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


def generated_files(country: Country | None = None) -> dict[str, Callable[[], bytes]]:
    """Site files made from code, by path in the site: index.html, og-image.png for a country with a `page` (the US
    keeps web/og-image.png), and the Unciv page and downloads of a country with an Unciv map (pipeline/play.py)."""
    c = country or active()
    files = {"index.html": lambda: index_bytes(c)}
    if c.page is not None:
        files["og-image.png"] = lambda: card_png(c)
        files |= play.files(c)
    return files
