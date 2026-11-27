"""The Unciv downloads and the "Jugar en Unciv" page of a country whose build made an Unciv map (unciv.json, written by
pipeline/build/spain_unciv.py), as pipeline/site.py serves and packages them:

* unciv/<Mod>.zip: the mod, one folder with jsons/ModOptions.json, jsons/TileResources.json (its own resources),
  jsons/Events.json and jsons/GlobalUniques.json (the fire season, pipeline/build/spain_unciv_fire.py), its Spanish in
  jsons/translations/Spanish.properties, maps/<map name>, Images/ResourceIcons/ and the atlas of those icons
  (game.atlas, game.png, Atlases.json), preview.png, README.md and LICENSE; Unciv's "Download mod from URL" takes it as is, and its contents are what the
  mod's GitHub repository holds;
* unciv/<map file>: the bare map for the base ruleset alone (without the mod's resources), for the `maps` folder of a
  desktop Unciv;
* unciv/preview.png and the game screenshots (docs/images), for the page;
* jugar.html (Spanish) and play.html (English): how to play it, on desktop and Android, and what on the map is real
  data and what is game convention; each links to the other.

The texts live in pipeline/templates/: the page (jugar.<lang>.html), the mod's bilingual README (unciv-readme.md) and
the resources' names and sources in each language (unciv-resources.json), as string.Template files whose $fields come
from unciv.json's summary (its texts in each language, core/lang.py). Only Spain has an Unciv map.
"""

from __future__ import annotations

import json
import math
from fractions import Fraction
from html import escape
from string import Template
from typing import Callable

from .build import spain_unciv_fire as fire
from .build import unciv
from .core.archive import zip_bytes
from .core.paths import ROOT
from .core.store import read_web
from .core.lang import num, pct, pick
from .core.png import encode
from .core.raster import Canvas, circle
from .countries import Country

TEMPLATES = ROOT / "pipeline" / "templates"
PAGES = {"es": "jugar.html", "en": "play.html"}  # the page in each language
MOD_ZIP = "unciv/Spainciv-Unciv.zip"
MAP_FILE = "unciv/espana"  # saved as the map's own name (the link's `download`), which Unciv shows in its map list
PREVIEW = "unciv/preview.png"
SCREENSHOT = ("unciv/partida.jpg", ROOT / "docs" / "images" / "es-unciv-partida.jpg")
FIRE_SHOT = {lang: (f"unciv/incendio.{lang}.jpg", ROOT / "docs" / "images" / f"{lang}-unciv-incendio.jpg")
             for lang in PAGES}  # the fire season's popup in Unciv in each language
AUTHOR = "DjinnFoundry"
ICON = "ResourceIcons/{name}"  # a resource's region in the atlas, and its image in Images/ (.png)
ATLAS = "game"  # the atlas Atlases.json lists: game.atlas and its page game.png

LICENSE = """The map in maps/ and the icon in Images/ are published under the Creative Commons Attribution 4.0
International licence (CC BY 4.0, https://creativecommons.org/licenses/by/4.0/). Credit: spainciv
(https://spainciv.djinnfoundry.com), with data from IGN (CC BY 4.0), Copernicus CORINE Land Cover 2018 (EEA),
NOAA ETOPO1, Natural Earth, IGME-CSIC (Estadística Minera de España 2019, BDMIN), INE (Censo Agrario 2020, CC BY 4.0)
and the Ministerio de Agricultura, Pesca y Alimentación (CC BY 4.0). The fire season's rates come from the burnt areas
of EFFIS, the European Forest Fire Information System (European Commission JRC, Copernicus Emergency Management
Service, CC BY 4.0), counted per map tile by spainciv.
"""


def load(country: Country) -> dict | None:
    """unciv.json with its texts in every language of the country (core.lang.Text), or None without an Unciv map."""
    return read_web(country.web_data_dir, "unciv.json", country.langs, optional=True)


def files(country: Country) -> dict[str, Callable[[], bytes]]:
    """The site files of the country's Unciv map, by path in the site; none without one."""
    doc = load(country)
    if doc is None:
        return {}
    pages = {PAGES[lang]: (lambda lang=lang: page_html(country, doc["summary"], lang).encode("utf-8")) for lang in country.langs}
    return {
        **pages,
        MOD_ZIP: lambda: mod_zip(country, doc),
        MAP_FILE: lambda: unciv.encode(unciv.without_mod(doc["map"])),
        PREVIEW: lambda: preview(doc),
        **{path: source.read_bytes for path, source in (SCREENSHOT, *(FIRE_SHOT[lang] for lang in country.langs))},
    }


def preview(doc: dict) -> bytes:
    g = doc["summary"]["grid"]
    grid = unciv.Grid(g["spacing"], g["width"], g["height"], tuple(g["centre"]))
    return unciv.preview_png(grid, unciv.tiles_from_map(doc["map"]))


# --- the mod --------------------------------------------------------------------------------------------------------------


def mod_entries(country: Country, doc: dict) -> dict[str, bytes]:
    """The mod's files, by path inside its folder (what the GitHub repository holds)."""
    mod, fire_season = doc["summary"]["mod"], doc["summary"]["fire_season"]
    options = unciv.mod_options(AUTHOR, f"https://github.com/{mod['repo']}")
    icons = {name: pig_icon() for name in unciv.MOD_RESOURCES}  # RGBA pixels
    return {
        "jsons/ModOptions.json": json_bytes(options),
        "jsons/TileResources.json": json_bytes(unciv.tile_resources_json()),
        "jsons/Events.json": json_bytes(fire.events_json(fire_season)),
        "jsons/GlobalUniques.json": json_bytes(fire.global_uniques_json(fire_season)),
        "jsons/translations/Spanish.properties": unciv.properties(fire.translations(fire_season)).encode("utf-8"),
        f"maps/{doc['map']['mapParameters']['name']}": unciv.encode(doc["map"]),
        **{f"Images/{ICON.format(name=name)}.png": encode(unciv.ICON_PX, unciv.ICON_PX, px, channels=4)
           for name, px in icons.items()},
        **icon_atlas(icons),
        "preview.png": preview(doc),
        "README.md": readme(country, doc["summary"]).encode("utf-8"),
        "LICENSE": LICENSE.encode("utf-8"),
    }


def mod_zip(country: Country, doc: dict) -> bytes:
    folder = doc["summary"]["mod"]["name"]
    return zip_bytes({f"{folder}/{path}": data for path, data in mod_entries(country, doc).items()})


def json_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"


# --- the pig: the icon of the mod's own resource ----------------------------------------------------------------------------

ICON_PAGE = 128  # the atlas page: room for one ICON_PX icon
PIG = (58, 46, 52)  # the dark coat of the Iberian pig
OUTLINE = (243, 230, 196)  # the map's cream, so the dark pig reads on any background


def pig_shapes(grow: float = 0.0) -> list[list[tuple[float, float]]]:
    """A pig seen from the side, facing right, in a 100 px square; `grow` widens every part (for the outline)."""
    def box(x0, y0, x1, y1):
        return [(x0 - grow, y0 - grow), (x1 + grow, y0 - grow), (x1 + grow, y1 + grow), (x0 - grow, y1 + grow)]

    def oval(cx, cy, rx, ry, n=28):
        return [(cx + (rx + grow) * math.cos(2 * math.pi * k / n), cy + (ry + grow) * math.sin(2 * math.pi * k / n))
                for k in range(n)]

    return [oval(46, 52, 31, 20), oval(77, 47, 14, 13), box(85, 44, 96, 56),
            [(68 - grow, 40), (75, 25 - grow), (82 + grow, 39)],  # ear
            box(24, 62, 32, 84), box(36, 64, 44, 86), box(54, 64, 62, 86), box(66, 62, 74, 84),  # legs
            circle(15, 44, 4 + grow, 10)]  # tail


def pig_icon() -> bytes:
    """The ICON_PX square icon of the Iberian pig, RGBA pixels: the coat over a cream outline, transparent around it."""
    colour, mask = Canvas(unciv.ICON_PX, unciv.ICON_PX, OUTLINE), Canvas(unciv.ICON_PX, unciv.ICON_PX)
    colour.fill(pig_shapes(), PIG)
    colour.fill([circle(86, 44, 1.6, 8)], OUTLINE)  # eye
    mask.fill(pig_shapes(grow=3.0), (255, 255, 255))
    rgba = bytearray()
    for i in range(unciv.ICON_PX * unciv.ICON_PX):
        rgba += colour.px[3 * i:3 * i + 3] + mask.px[3 * i:3 * i + 1]
    return bytes(rgba)


def icon_atlas(icons: dict[str, bytes]) -> dict[str, bytes]:
    """The atlas of the icons' RGBA pixels, by path in the mod: its page (a PNG) with each icon as
    ResourceIcons/<name>, the atlas file and Atlases.json. One page of ICON_PAGE px holds one icon; a second resource
    would need a wider page."""
    if len(icons) != 1:
        raise ValueError("the atlas page holds one icon")
    (name, px), = icons.items()
    n, page = unciv.ICON_PX, bytearray(ICON_PAGE * ICON_PAGE * 4)
    for y in range(n):
        page[4 * ICON_PAGE * y:4 * ICON_PAGE * y + 4 * n] = px[4 * n * y:4 * n * (y + 1)]
    regions = {ICON.format(name=name): (0, 0)}
    return {f"{ATLAS}.png": encode(ICON_PAGE, ICON_PAGE, bytes(page), channels=4),
            f"{ATLAS}.atlas": unciv.atlas(f"{ATLAS}.png", (ICON_PAGE, ICON_PAGE), regions).encode("utf-8"),
            "Atlases.json": f"[{ATLAS}]\n".encode("utf-8")}


# --- texts ------------------------------------------------------------------------------------------------------------------


LANG_LINK = {"es": "En español", "en": "In English"}  # the link to the page in each language, in that language


def fill(template: str, **fields) -> str:
    """A file of pipeline/templates with its $fields filled in (a missing field fails)."""
    return Template((TEMPLATES / template).read_text(encoding="utf-8")).substitute(fields)


def resource_texts(summary: dict, lang: str) -> dict[str, tuple[str, str]]:
    """Resource → (its name in `lang`, where it comes from), with the summary's numbers filled in."""
    texts = json.loads((TEMPLATES / "unciv-resources.json").read_text(encoding="utf-8"))[lang]
    numbers = {"horse_density": f"{summary['horse_density']:g}", "horse_comarcas": summary["horse_comarcas"]}
    return {r: (name, Template(src).substitute(numbers)) for r, (name, src) in texts.items()}


def common_fields(country: Country, summary: dict, lang: str | None = None) -> dict:
    s = summary
    return {"product": country.product, "url": f"https://{country.site_url}", "page": PAGES[lang or country.lang],
            "width": s["grid"]["width"],
            "height": s["grid"]["height"], "tile_km": f"{s['tile_km']:g}", "land_tiles": s["land_tiles"],
            "national_land_tiles": s["national_land_tiles"], "release": s["unciv_release"],
            "n_starts": len(s["starts"]) - 1, "map_name": s["map_name"]}


FIRE_CLASSES = {  # the fire season's tile classes in each language (Unciv's Spanish: Montaña, Colina)
    "es": {"Mountain": "Montaña", "Hill": "Colina, también con bosque", "Land": "El resto de la tierra"},
    "en": {"Mountain": "Mountain", "Hill": "Hill, wooded or not", "Land": "Any other land"},
}
FIRE_EXAMPLES = {  # the rows of the chance table: fire.EXAMPLES, then all of Spain
    "es": ("Una ciudad nueva en llano", "Imperio pequeño", "Imperio mediano", "Toda España"),
    "en": ("A new city on flat land", "Small empire", "Mid-sized empire", "All of Spain"),
}


def fire_fields(summary: dict, lang: str) -> dict:
    """The fire season's numbers for the page and the README as `lang` writes them, and its two tables as rows of
    cells: `fire_rows` per class of tile, `fire_examples` the chance per check of some empires and of all of Spain."""
    f = summary["fire_season"]
    w = fire.weights(f)
    rows = [[FIRE_CLASSES[lang][c["class"]], str(c["tiles"]), num(c["per_tile_season"], 3, lang), str(c["weight"])]
            for c in f["classes"]]
    spain = {c["class"]: c["tiles"] for c in f["classes"]}
    examples = [[name, *(str(e[k]) for k in ("Land", "Hill", "Mountain")), pct(fire.chance(fire.owned(e, w)) / 100, 0, lang)]
                for name, e in zip(FIRE_EXAMPLES[lang], (*fire.EXAMPLES, spain), strict=True)]
    ai = Fraction(100 + fire.AI_PAY_WEIGHT_PCT, 200 + fire.AI_PAY_WEIGHT_PCT)  # Unciv: weight × (1 + pct / 100)
    (_, _, cost_1), (_, _, cost_2), (_, _, cost_3) = fire.COSTS
    return {
        "fire_n": f["great_fires"], "fire_ha": f["threshold_ha"], "fire_from": f["years"][0], "fire_to": f["years"][1],
        "fire_seasons": f["seasons"], "fire_min": min(f["per_season"]), "fire_max": max(f["per_season"]),
        "fire_per_season": num(f["fires_per_season"], 1, lang), "fire_on_spain": num(round(f["on_spanish_tiles"]), None, lang),
        "fire_summer": pct(f["summer_share"], 1, lang), "fire_unit": num(f["unit"], None, lang),
        "fire_check": fire.CHECK_TURNS, "fire_penalty": -fire.PENALTY_PCT, "fire_penalty_turns": fire.PENALTY_TURNS,
        "fire_cost_1": cost_1, "fire_cost_2": cost_2, "fire_cost_3": cost_3,
        "fire_ai": ai.numerator, "fire_ai_of": ai.denominator,
        "fire_bands": len(fire.bands()), "fire_times": fire.rough_times(f["classes"]),
        "fire_rows": rows, "fire_examples": examples,
    }


def markdown_rows(rows: list[list[str]]) -> str:
    return "\n".join("| " + " | ".join(row) + " |" for row in rows)


def html_rows(rows: list[list[str]]) -> str:
    """Table rows: the first cell as text, the rest as numbers."""
    return "".join("<tr>" + "".join(f"<td{' class=n' if k else ''}>{escape(c)}</td>" for k, c in enumerate(row))
                   + "</tr>" for row in rows)


def readme(country: Country, summary: dict) -> str:
    def rows(lang: str) -> str:
        texts = resource_texts(summary, lang)
        return "\n".join(f"| {texts[r][0]} | {n} | {texts[r][1]} |" for r, n in summary["resources"].items())

    def fires(lang: str) -> dict:
        f = fire_fields(summary, lang)
        del f["fire_examples"]  # the page's table only
        f["fire_rows"] = markdown_rows(f["fire_rows"])
        return {f"{k}_{lang}": v for k, v in f.items()}

    return fill("unciv-readme.md", rows_es=rows("es"), rows_en=rows("en"), **fires("es"), **fires("en"),
                page_en=PAGES["en"], **common_fields(country, summary))


def page_html(country: Country, summary: dict, lang: str | None = None) -> str:
    """The page in `lang` (the country's first by default), linking to its versions in the other languages."""
    s, lang = summary, lang or country.lang
    texts = resource_texts(s, lang)
    rows = "".join(f"<tr><td>{escape(texts[r][0])}</td><td class=n>{n}</td><td>{escape(texts[r][1])}</td></tr>"
                   for r, n in s["resources"].items())
    fields = {k: escape(str(v)) for k, v in common_fields(country, s, lang).items()} | {
        "zip_href": MOD_ZIP, "zip_name": MOD_ZIP.rsplit("/", 1)[1], "map_href": MAP_FILE, "shot": SCREENSHOT[0],
        "fire_shot": FIRE_SHOT[lang][0],
        "mod_name": escape(s["mod"]["name"]), "mod_repo": escape(s["mod"]["repo"]),
        "starts": escape(", ".join(x["city"] for x in s["starts"][1:])),
        "gap_km": f"{s['start_gap_tiles'] * s['tile_km']:g}", "fine_km": f"{country.hex_radius_km * math.sqrt(3):g}",
        "coast_m": -unciv.COAST_DEPTH_M, "mountain_pct": round(unciv.MOUNTAIN_SHARE * 100),
        "hill_pct": round(unciv.HILL_SHARE * 100), "forest_pct": unciv.FOREST_PCT, "marsh_pct": unciv.MARSH_PCT,
        "tundra_m": unciv.TUNDRA_ELEV_M, "river_edges": s["river_edges"], "resource_rows": rows,
        "not_placed": escape(", ".join(f"{texts[r][0].lower()} {n}" for r, n in s["not_placed"].items())),
        "designations": escape(", ".join(pick(d, lang) for d in s["not_placed_designations"])),
        "home": f"./#lang={lang}" if len(country.langs) > 1 else "./",
        "other_langs": "".join(f' · <a href="{PAGES[o]}" lang="{o}" hreflang="{o}">{LANG_LINK[o]}</a>'
                               for o in country.langs if o != lang),
    }
    fires = fire_fields(s, lang)
    rows, examples = fires.pop("fire_rows"), fires.pop("fire_examples")
    fields |= {k: escape(str(v)) for k, v in fires.items()} | {
        "fire_rows": html_rows(rows), "fire_examples": html_rows(examples)}
    return fill(f"jugar.{lang}.html", **fields)
