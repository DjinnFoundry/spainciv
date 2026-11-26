"""The Unciv downloads and the "Jugar en Unciv" page of a country whose build made an Unciv map (unciv.json, written by
pipeline/build/spain_unciv.py), as pipeline/site.py serves and packages them:

* unciv/<Mod>.zip: the mod, one folder with jsons/ModOptions.json, jsons/TileResources.json (its own resources),
  maps/<map name>, Images/ResourceIcons/ and the atlas of those icons (game.atlas, game.png, Atlases.json),
  preview.png, README.md and LICENSE; Unciv's "Download mod from URL" takes it as is, and its contents are what the
  mod's GitHub repository holds;
* unciv/<map file>: the bare map for the base ruleset alone (without the mod's resources), for the `maps` folder of a
  desktop Unciv;
* unciv/preview.png and the game screenshot (docs/images), for the page;
* jugar.html: how to play it, on desktop and Android, and what on the map is real data and what is game convention.

The texts live in pipeline/templates/: the page (jugar.<lang>.html), the mod's bilingual README (unciv-readme.md) and
the resources' names and sources in each language (unciv-resources.json), as string.Template files whose $fields come
from unciv.json's summary. Only Spain has an Unciv map, and its page is in Spanish for now.
"""

from __future__ import annotations

import json
import math
from html import escape
from string import Template
from typing import Callable

from .build import unciv
from .core.archive import zip_bytes
from .core.paths import ROOT
from .core.png import encode
from .core.raster import Canvas, circle
from .countries import Country

TEMPLATES = ROOT / "pipeline" / "templates"
PAGE = "jugar.html"
MOD_ZIP = "unciv/Spainciv-Unciv.zip"
MAP_FILE = "unciv/espana"  # saved as the map's own name (the link's `download`), which Unciv shows in its map list
PREVIEW = "unciv/preview.png"
SCREENSHOT = ("unciv/partida.jpg", ROOT / "docs" / "images" / "es-unciv-partida.jpg")
AUTHOR = "DjinnFoundry"
ICON = "ResourceIcons/{name}"  # a resource's region in the atlas, and its image in Images/ (.png)
ATLAS = "game"  # the atlas Atlases.json lists: game.atlas and its page game.png

LICENSE = """The map in maps/ and the icon in Images/ are published under the Creative Commons Attribution 4.0
International licence (CC BY 4.0, https://creativecommons.org/licenses/by/4.0/). Credit: spainciv
(https://spainciv.djinnfoundry.com), with data from IGN (CC BY 4.0), Copernicus CORINE Land Cover 2018 (EEA),
NOAA ETOPO1, Natural Earth, IGME-CSIC (Estadística Minera de España 2019, BDMIN), INE (Censo Agrario 2020, CC BY 4.0)
and the Ministerio de Agricultura, Pesca y Alimentación (CC BY 4.0).
"""


def load(country: Country) -> dict | None:
    path = country.web_data_dir / "unciv.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def files(country: Country) -> dict[str, Callable[[], bytes]]:
    """The site files of the country's Unciv map, by path in the site; none without one."""
    doc = load(country)
    if doc is None:
        return {}
    shot_path, shot_file = SCREENSHOT
    return {
        PAGE: lambda: page_html(country, doc["summary"]).encode("utf-8"),
        MOD_ZIP: lambda: mod_zip(country, doc),
        MAP_FILE: lambda: unciv.encode(unciv.without_mod(doc["map"])),
        PREVIEW: lambda: preview(doc),
        shot_path: shot_file.read_bytes,
    }


def preview(doc: dict) -> bytes:
    g = doc["summary"]["grid"]
    grid = unciv.Grid(g["spacing"], g["width"], g["height"], tuple(g["centre"]))
    return unciv.preview_png(grid, unciv.tiles_from_map(doc["map"]))


# --- the mod --------------------------------------------------------------------------------------------------------------


def mod_entries(country: Country, doc: dict) -> dict[str, bytes]:
    """The mod's files, by path inside its folder (what the GitHub repository holds)."""
    mod = doc["summary"]["mod"]
    options = unciv.mod_options(AUTHOR, f"https://github.com/{mod['repo']}")
    icons = {name: pig_icon() for name in unciv.MOD_RESOURCES}  # RGBA pixels
    return {
        "jsons/ModOptions.json": json_bytes(options),
        "jsons/TileResources.json": json_bytes(unciv.tile_resources_json()),
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


def fill(template: str, **fields) -> str:
    """A file of pipeline/templates with its $fields filled in (a missing field fails)."""
    return Template((TEMPLATES / template).read_text(encoding="utf-8")).substitute(fields)


def resource_texts(summary: dict, lang: str) -> dict[str, tuple[str, str]]:
    """Resource → (its name in `lang`, where it comes from), with the summary's numbers filled in."""
    texts = json.loads((TEMPLATES / "unciv-resources.json").read_text(encoding="utf-8"))[lang]
    numbers = {"horse_density": f"{summary['horse_density']:g}", "horse_comarcas": summary["horse_comarcas"]}
    return {r: (name, Template(src).substitute(numbers)) for r, (name, src) in texts.items()}


def common_fields(country: Country, summary: dict) -> dict:
    s = summary
    return {"product": country.product, "url": f"https://{country.site_url}", "page": PAGE, "width": s["grid"]["width"],
            "height": s["grid"]["height"], "tile_km": f"{s['tile_km']:g}", "land_tiles": s["land_tiles"],
            "national_land_tiles": s["national_land_tiles"], "release": s["unciv_release"],
            "n_starts": len(s["starts"]) - 1, "map_name": s["map_name"]}


def readme(country: Country, summary: dict) -> str:
    def rows(lang: str) -> str:
        texts = resource_texts(summary, lang)
        return "\n".join(f"| {texts[r][0]} | {n} | {texts[r][1]} |" for r, n in summary["resources"].items())

    return fill("unciv-readme.md", rows_es=rows("es"), rows_en=rows("en"), **common_fields(country, summary))


def page_html(country: Country, summary: dict) -> str:
    s = summary
    texts = resource_texts(s, country.lang)
    rows = "".join(f"<tr><td>{escape(texts[r][0])}</td><td class=n>{n}</td><td>{escape(texts[r][1])}</td></tr>"
                   for r, n in s["resources"].items())
    fields = {k: escape(str(v)) for k, v in common_fields(country, s).items()} | {
        "zip_href": MOD_ZIP, "zip_name": MOD_ZIP.rsplit("/", 1)[1], "map_href": MAP_FILE, "shot": SCREENSHOT[0],
        "mod_name": escape(s["mod"]["name"]), "mod_repo": escape(s["mod"]["repo"]),
        "starts": escape(", ".join(x["city"] for x in s["starts"][1:])),
        "gap_km": f"{s['start_gap_tiles'] * s['tile_km']:g}", "fine_km": f"{country.hex_radius_km * math.sqrt(3):g}",
        "coast_m": -unciv.COAST_DEPTH_M, "mountain_pct": round(unciv.MOUNTAIN_SHARE * 100),
        "hill_pct": round(unciv.HILL_SHARE * 100), "forest_pct": unciv.FOREST_PCT, "marsh_pct": unciv.MARSH_PCT,
        "tundra_m": unciv.TUNDRA_ELEV_M, "river_edges": s["river_edges"], "resource_rows": rows,
        "not_placed": escape(", ".join(f"{texts[r][0].lower()} {n}" for r, n in s["not_placed"].items())),
        "designations": escape(", ".join(s["not_placed_designations"])),
    }
    return fill(f"jugar.{country.lang}.html", **fields)
