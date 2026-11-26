"""The published page of the active country: web/index.html, and the country's own site files.

web/index.html is written for the United States and is published as is for it. A country with a `page`
(countries.base.Page) gets, when the site is served (`serve`) or packaged (`package`):

- its language, title, description and social cards (canonical, og:*, twitter:*), with absolute URLs built from
  `site_url`; the card image is `https://<site_url>/og-image.png`;
- a credit line on the map: its data sources, the licence notices its sources require, and usaciv's credit;
- `<script id="country-page">`: site_url, data_credit and notices as JSON, which web/js/app/country.js lays over
  the world.json `country` block (so a new address or credit needs no data rebuild).

A country whose web data lives in sites/<id>/data can put more site files next to it (sites/<id>/og-image.png):
they replace web/'s files of the same name.
"""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path

from .core.paths import WEB
from .countries import Country, active

USACIV_URL = "https://karpathy.ai/usaciv/"


def overlay_dir(country: Country | None = None) -> Path | None:
    """sites/<id>/: the country's own site files (its data/ excluded), or None when the country's data is web/data."""
    folder = (country or active()).web_data_dir.parent
    return None if folder == WEB else folder


def overlay_files(country: Country | None = None) -> list[tuple[Path, Path]]:
    """(file, path in the site) for every overlay file of the country."""
    folder = overlay_dir(country)
    if folder is None or not folder.is_dir():
        return []
    return [(f, f.relative_to(folder)) for f in sorted(folder.rglob("*")) if f.is_file() and f.relative_to(folder).parts[0] != "data" and f.name != ".DS_Store"]


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
    parts = [escape(page.data_credit), *map(escape, page.notices), f'Based on <a href="{USACIV_URL}" target="_blank" rel="noopener">usaciv</a> by Andrej Karpathy (MIT)']
    return f'<p id="map-credits" class="map-credits">{" · ".join(parts)}</p>'


def page_config(country: Country) -> dict:
    """What the browser takes from the page rather than from world.json (see web/js/app/country.js)."""
    return {"site_url": country.site_url, "data_credit": country.page.data_credit, "notices": list(country.page.notices)}


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
