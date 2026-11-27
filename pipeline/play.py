"""The Unciv downloads and the "Jugar en Unciv" page of a country whose build made an Unciv map (unciv.json, written by
pipeline/build/spain_unciv.py), as pipeline/site.py serves and packages them:

* unciv/<Mod>.zip: the mod, one folder with jsons/ModOptions.json, jsons/TileResources.json (its own resources),
  jsons/Nations.json (the autonomous communities and cities), jsons/Events.json and jsons/GlobalUniques.json (the fire
  season, pipeline/build/spain_unciv_fire.py), jsons/translations/Spanish.properties (the Spanish of both),
  maps/<map name>, Images/ (the resource's icon, each nation's flag in NationPortraits/ and each major nation's
  city-banner icon in NationIcons/) and the atlas of those images (game.atlas, game.png, Atlases.json), preview.png,
  README.md and LICENSE; Unciv's "Download mod from URL" takes it as is, and its contents are what the mod's GitHub
  repository holds;
* unciv/<map file>: the bare map for the base ruleset alone (without the mod's resources), for the `maps` folder of a
  desktop Unciv;
* unciv/preview.png and the game screenshots (docs/images), for the page;
* jugar.html (Spanish) and play.html (English): how to play it, on desktop and Android, and what on the map is real
  data and what is game convention; each links to the other.

The texts live in pipeline/templates/: the page (jugar.<lang>.html), the mod's bilingual README (unciv-readme.md), the
resources' names and sources in each language (unciv-resources.json) and the nations' texts (unciv-nations.json), as
string.Template files whose $fields come from unciv.json's summary (its texts in each language, core/lang.py). Only
Spain has an Unciv map.
"""

from __future__ import annotations

import json
import math
from fractions import Fraction
from html import escape
from string import Template
from typing import Callable

from .build import spain_unciv, unciv
from .build import spain_unciv_fire as fire
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
PORTRAIT, NATION_ICON = "NationPortraits/{name}", "NationIcons/{name}"  # a nation's emblem and its city-banner icon
ATLAS = "game"  # the atlas Atlases.json lists: game.atlas and its page game.png
ATLAS_COLUMNS = 10  # images per row of the atlas page
TEXT_LANG = "en"  # the language of the mod's own texts: Unciv's, whose translations are keyed by the English
UNCIV_LANGUAGES = {"es": "Spanish"}  # the other languages of the country → Unciv's name for its translation file

LICENSE = """The map in maps/, the nations in jsons/ and the images in Images/ are published under the Creative Commons
Attribution 4.0 International licence (CC BY 4.0, https://creativecommons.org/licenses/by/4.0/). Credit: spainciv
(https://spainciv.djinnfoundry.com), with data from IGN (CC BY 4.0), Copernicus CORINE Land Cover 2018 (EEA),
NOAA ETOPO1, Natural Earth, IGME-CSIC (Estadística Minera de España 2019, BDMIN), INE (Padrón, Censo Agrario 2020,
CC BY 4.0), the Ministerio de Agricultura, Pesca y Alimentación (CC BY 4.0) and the Statutes of Autonomy (BOE). The
fire season's rates come from the burnt areas of EFFIS, the European Forest Fire Information System (European
Commission JRC, Copernicus Emergency Management Service, CC BY 4.0), counted per map tile by spainciv.
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
        MAP_FILE: lambda: unciv.encode(unciv.without_mod(doc["map"], doc["bare"])),
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
    summary = doc["summary"]
    options = unciv.mod_options(AUTHOR, f"https://github.com/{summary['mod']['repo']}")
    images = {ICON.format(name=name): pig_icon() for name in unciv.MOD_RESOURCES}  # region → RGBA pixels
    for n in summary["nations"]:
        portrait, icon = flag_images(n)
        images[PORTRAIT.format(name=n["name"])] = portrait
        if not n["city_state"]:  # a city-state's banner shows its type's icon (pipeline/build/unciv.py)
            images[NATION_ICON.format(name=n["name"])] = icon
    return {
        "jsons/ModOptions.json": json_bytes(options),
        "jsons/TileResources.json": json_bytes(unciv.tile_resources_json()),
        "jsons/Nations.json": json_bytes([nation_json(summary, n) for n in summary["nations"]]),
        "jsons/Events.json": json_bytes(fire.events_json(summary["fire_season"])),
        "jsons/GlobalUniques.json": json_bytes(fire.global_uniques_json(summary["fire_season"])),
        **{f"jsons/translations/{name}.properties": unciv.properties(translations(summary, lang)).encode("utf-8")
           for lang, name in UNCIV_LANGUAGES.items() if lang in country.langs},
        f"maps/{doc['map']['mapParameters']['name']}": unciv.encode(doc["map"]),
        **{f"Images/{name}.png": encode(unciv.ICON_PX, unciv.ICON_PX, px, channels=4) for name, px in images.items()},
        **icon_atlas(images),
        "preview.png": preview(doc),
        "README.md": readme(country, summary).encode("utf-8"),
        "LICENSE": LICENSE.encode("utf-8"),
    }


def mod_zip(country: Country, doc: dict) -> bytes:
    folder = doc["summary"]["mod"]["name"]
    return zip_bytes({f"{folder}/{path}": data for path, data in mod_entries(country, doc).items()})


def json_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"


# --- the pig: the icon of the mod's own resource ----------------------------------------------------------------------------

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


def icon_atlas(images: dict[str, bytes]) -> dict[str, bytes]:
    """The atlas of the mod's images (region → ICON_PX square RGBA pixels), by path in the mod: one page (a PNG) with
    the images in rows of ATLAS_COLUMNS, a pixel of space around each, the atlas file and Atlases.json."""
    n, pitch = unciv.ICON_PX, unciv.ICON_PX + 2
    width = power_of_two(ATLAS_COLUMNS * pitch)
    height = power_of_two(math.ceil(len(images) / ATLAS_COLUMNS) * pitch)
    page, regions = bytearray(width * height * 4), {}
    for k, (name, px) in enumerate(images.items()):
        x0, y0 = 1 + pitch * (k % ATLAS_COLUMNS), 1 + pitch * (k // ATLAS_COLUMNS)
        for y in range(n):
            row = 4 * (width * (y0 + y) + x0)
            page[row:row + 4 * n] = px[4 * n * y:4 * n * (y + 1)]
        regions[name] = (x0, y0)
    return {f"{ATLAS}.png": encode(width, height, bytes(page), channels=4),
            f"{ATLAS}.atlas": unciv.atlas(f"{ATLAS}.png", (width, height), regions).encode("utf-8"),
            "Atlases.json": f"[{ATLAS}]\n".encode("utf-8")}


def power_of_two(n: int) -> int:
    return 1 << max(0, n - 1).bit_length()


# --- the nations: their flags and their texts -------------------------------------------------------------------------------


def flag_images(nation: dict) -> tuple[bytes, bytes]:
    """A nation's flag (its layers in unciv.json, spain_flags) as its two ICON_PX square RGBA images: the emblem, the
    flag in full colour on a disc, transparent around it; and the city-banner icon, white wherever the flag shows the
    nation's inner colour (Unciv tints it with that colour), on the same disc."""
    n, inner = unciv.ICON_PX, tuple(nation["inner"])
    colour, mask, disc = Canvas(n, n), Canvas(n, n), Canvas(n, n)
    for rgb, polygons in nation["flag"]:
        polys = [[(x * n, y * n) for x, y in p] for p in polygons]
        rgb = tuple(rgb)
        colour.fill(polys, rgb)
        mask.fill(polys, (255, 255, 255) if rgb == inner else (0, 0, 0))
    disc.fill([circle(n / 2, n / 2, n / 2 - 0.5, 96)], (255, 255, 255))
    portrait, icon = bytearray(), bytearray()
    for i in range(n * n):
        alpha = disc.px[3 * i]
        portrait += colour.px[3 * i:3 * i + 3] + bytes([alpha])
        icon += bytes([255, 255, 255, mask.px[3 * i] * alpha // 255])
    return bytes(portrait), bytes(icon)


def nation_templates(lang: str) -> dict:
    return template_json("unciv-nations.json", lang)


def nation_texts(summary: dict, nation: dict, lang: str) -> dict[str, str]:
    """A major nation's leader title, unique's name, start text, advantage and starting city in `lang`
    (unciv-nations.json), with its numbers as the language writes them. A nation that starts off its seat's tile says
    how far; a strategic resource says the technology that reveals it (unciv.REVEALED_BY), before which its tiles
    give nothing."""
    t = nation_templates(lang)
    sub = lambda key, **fields: Template(t[key]).substitute(fields)
    name, _, word = resource_texts(summary, lang)[nation["resource"]]
    capital, off = nation["cities"][0], nation["start_off_seat"]
    distance = Template(t["tiles"][off != 1]).substitute(n=off)  # "1 casilla", "2 casillas"
    tech = unciv.REVEALED_BY.get(nation["resource"])
    fields = {"name": nation["name"], "capital": capital, "year": summary["padron_year"],
              "population": num(nation["population"], lang=lang), "municipalities": num(nation["municipalities"], lang=lang),
              "start": sub("start_near", distance=distance, capital=capital) if off else sub("start", capital=capital),
              "land_tiles": nation["land_tiles"], "resource": name, "resource_word": word,
              "resource_tiles": nation["resource_tiles"], "resource_map_tiles": nation["resource_map_tiles"],
              "hidden": sub("hidden", tech=t["techs"][tech]) if tech else "",
              "hidden_short": sub("hidden_short", tech=t["techs"][tech]) if tech else ""}
    return {"leader": pick(nation["leader"], lang), "unique_name": sub("unique_name", **fields),
            "intro": sub("intro", **fields), "advantage": sub("advantage", **fields),
            "starts_in": sub("start_cell_near", capital=capital, distance=distance) if off else capital}


def nation_json(summary: dict, nation: dict) -> dict:
    """The Nations.json entry of a nation in unciv.json's summary, its texts in TEXT_LANG."""
    if nation["city_state"]:
        return unciv.nation_json(nation["name"], nation["outer"], nation["inner"], nation["cities"],
                                 city_state_type=nation["type"])
    t = nation_texts(summary, nation, TEXT_LANG)
    return unciv.nation_json(nation["name"], nation["outer"], nation["inner"], nation["cities"], leader=t["leader"],
                             start_bias=nation["start_bias"], unique_name=t["unique_name"], resource=nation["resource"],
                             intro=t["intro"])


def translations(summary: dict, lang: str) -> dict[str, str]:
    """The mod's texts (TEXT_LANG) → their `lang` version: what jsons/translations/<Language>.properties holds."""
    out = {}
    for n in summary["nations"]:
        if not n["city_state"]:
            source, target = nation_texts(summary, n, TEXT_LANG), nation_texts(summary, n, lang)
            out |= {source[k]: target[k] for k in ("leader", "unique_name", "intro") if source[k] != target[k]}
    for text in summary["fire_season"]["texts"].values():  # the event's texts, keyed by Events.json's English
        source, target = text[TEXT_LANG], text[lang]
        if out.get(source, target) != target:
            raise ValueError(f"two translations of {source!r}")
        out[source] = target
    return out


def nation_rows(summary: dict, lang: str) -> list[tuple[str, str, str, str]]:
    """(name, where it starts, advantage, start bias) of each nation, in `lang`: the README shows the four, the page
    the first three (the start bias only counts on other maps)."""
    templates, rows = nation_templates(lang), []
    for n in summary["nations"]:
        if n["city_state"]:
            rows.append((n["name"], n["cities"][0], templates["city_state"], ""))
        else:
            bias = templates["terrains"][n["start_bias"]] if n["start_bias"] else templates["no_bias"]
            t = nation_texts(summary, n, lang)
            rows.append((n["name"], t["starts_in"], t["advantage"], bias))
    return rows


PAGE_COLUMNS = 3  # the columns of nation_rows the page shows


def unique_fallback(summary: dict, lang: str) -> str:
    """What the page adds to the unique's rule for the nations that hold no resource on UNIQUE_MIN_TILES tiles (their
    resource is chosen among all they hold): "; si no llega a 2 en ninguno, entre todos: Madrid", or nothing."""
    names = [n["name"] for n in summary["nations"]
             if not n["city_state"] and n["resource_tiles"] < spain_unciv.UNIQUE_MIN_TILES]
    return Template(nation_templates(lang)["fallback"]).substitute(
        unique_min=spain_unciv.UNIQUE_MIN_TILES, names=", ".join(names)) if names else ""


def n_nations(summary: dict) -> int:
    """How many major nations (not city-states) the mod has."""
    return sum(not n["city_state"] for n in summary["nations"])


def moved_starts(summary: dict) -> str:
    """The nations that start off their seat's tile, with how many tiles: "Castilla-La Mancha 1, La Rioja 2"."""
    return ", ".join(f"{n['name']} {n['start_off_seat']}" for n in summary["nations"] if n["start_off_seat"])


# --- texts ------------------------------------------------------------------------------------------------------------------


LANG_LINK = {"es": "En español", "en": "In English"}  # the link to the page in each language, in that language


def fill(template: str, **fields) -> str:
    """A file of pipeline/templates with its $fields filled in (a missing field fails)."""
    return Template((TEMPLATES / template).read_text(encoding="utf-8")).substitute(fields)


def template_json(template: str, lang: str) -> dict:
    """The `lang` part of a JSON file of texts in pipeline/templates/."""
    return json.loads((TEMPLATES / template).read_text(encoding="utf-8"))[lang]


def resource_texts(summary: dict, lang: str) -> dict[str, tuple[str, str, str]]:
    """Resource → (its name in `lang`, where it comes from, its word inside a sentence), with the summary's numbers
    filled in."""
    texts = template_json("unciv-resources.json", lang)
    numbers = {"horse_density": f"{summary['horse_density']:g}", "horse_comarcas": summary["horse_comarcas"]}
    return {r: (name, Template(src).substitute(numbers), word) for r, (name, src, word) in texts.items()}


def common_fields(country: Country, summary: dict, lang: str | None = None) -> dict:
    s = summary
    return {"product": country.product, "url": f"https://{country.site_url}", "page": PAGES[lang or country.lang],
            "width": s["grid"]["width"],
            "height": s["grid"]["height"], "tile_km": f"{s['tile_km']:g}", "land_tiles": s["land_tiles"],
            "national_land_tiles": s["national_land_tiles"], "release": s["unciv_release"],
            "n_starts": len(s["starts"]) - 1, "map_name": s["map_name"], "padron_year": s["padron_year"],
            "n_nations": n_nations(s), "moved": moved_starts(s)}


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

    def nations(lang: str) -> str:
        return "\n".join(f"| {' | '.join(row)} |" for row in nation_rows(summary, lang))

    def fires(lang: str) -> dict:
        f = fire_fields(summary, lang)
        del f["fire_examples"]  # the page's table only
        f["fire_rows"] = markdown_rows(f["fire_rows"])
        return {f"{k}_{lang}": v for k, v in f.items()}

    return fill("unciv-readme.md", rows_es=rows("es"), rows_en=rows("en"), nations_es=nations("es"),
                nations_en=nations("en"), **fires("es"), **fires("en"), page_en=PAGES["en"],
                **common_fields(country, summary))


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
        "nation_rows": "".join("<tr>" + "".join(f"<td>{escape(c)}</td>" for c in row[:PAGE_COLUMNS]) + "</tr>"
                               for row in nation_rows(s, lang)),
        "unique_fallback": escape(unique_fallback(s, lang)),
        "bias_pct": round(spain_unciv.BIAS_SHARE * 100), "unique_min": spain_unciv.UNIQUE_MIN_TILES,
        "city_gap": spain_unciv.MIN_SEAT_GAP - 1, "city_names": spain_unciv.CITY_NAMES,
        "rivals": n_nations(s) - 1,
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
