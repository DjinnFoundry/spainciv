"""The Unciv downloads and the "Jugar en Unciv" page of a country whose build made an Unciv map (unciv.json, written by
pipeline/build/spain_unciv.py), as pipeline/site.py serves and packages them:

* unciv/<Mod>.zip: the mod, one folder with jsons/ModOptions.json, maps/<map name>, preview.png, README.md and LICENSE;
  Unciv's "Download mod from URL" takes it as is, and its contents are what the mod's GitHub repository holds;
* unciv/<map file>: the bare map, for the `maps` folder of a desktop Unciv;
* unciv/preview.png and the game screenshot (docs/images), for the page;
* jugar.html: how to play it, on desktop and Android, and what on the map is real data and what is game convention.

Every number on the page and in the README comes from unciv.json's summary. The page is in Spanish: only Spain has an
Unciv map.
"""

from __future__ import annotations

import json
import math
from html import escape
from typing import Callable

from .build import unciv
from .core.archive import zip_bytes
from .core.paths import ROOT
from .countries import Country

PAGE = "jugar.html"
MOD_REPO = "DjinnFoundry/Spainciv-Unciv"
MOD_FOLDER = "Spainciv Unciv"  # the folder Unciv makes from the repository's name (Github.kt: repoNameToFolderName)
MOD_ZIP = "unciv/Spainciv-Unciv.zip"
MAP_FILE = "unciv/espana"  # saved as the map's own name (the link's `download`), which Unciv shows in its map list
PREVIEW = "unciv/preview.png"
SCREENSHOT = ("unciv/partida.jpg", ROOT / "docs" / "images" / "es-unciv-partida.jpg")
AUTHOR = "DjinnFoundry"

# Unciv's English resource names → the Spanish names the game itself shows (android/assets/jsons/translations/Spanish.properties).
RESOURCE_ES = {"Iron": "Hierro", "Oil": "Petróleo", "Gold Ore": "Oro", "Copper": "Cobre", "Marble": "Mármol",
               "Salt": "Sal", "Wine": "Vino", "Citrus": "Cítricos", "Spices": "Especias", "Cattle": "Ganado",
               "Sheep": "Ovejas", "Fish": "Peces", "Stone": "Piedra", "Bananas": "Plátanos"}
# Where each resource comes from, for the page.
RESOURCE_SOURCE = {
    "Iron": "las explotaciones de óxidos de hierro (IGME, 2019), las únicas de hierro de la lista",
    "Oil": "las concesiones de hidrocarburos en explotación (IGME, 2019); Unciv no tiene gas, así que cuentan como petróleo",
    "Gold Ore": "la mina de oro y plata activa (IGME, 2019)",
    "Copper": "las minas de cobre activas (IGME, 2019)",
    "Marble": "las canteras de mármol (IGME, 2019)",
    "Salt": "las minas de sal gema, salinas marinas y de manantial (IGME, 2019)",
    "Wine": "las denominaciones de origen de vino (Ministerio de Agricultura)",
    "Citrus": "las IGP Cítricos Valencianos y Clementinas de las Tierras del Ebro",
    "Spices": "las DOP Azafrán de La Mancha, Pimentón de la Vera y Pimentón de Murcia",
    "Cattle": "las IGP de carne de vacuno (Ternera Gallega, Ternera Asturiana, Carne de Ávila y otras)",
    "Sheep": "las IGP de cordero (Cordero Manchego, Lechazo de Castilla y León, Ternasco de Aragón y otras)",
    "Fish": "las IGP y DOP de pescado y marisco (Mejillón de Galicia, Caballa de Andalucía, Mojama de Barbate y otras)",
    "Stone": "las canteras de roca ornamental: granito, caliza, pizarra, arenisca y cuarcita (IGME, 2019)",
    "Bananas": "la IGP Plátano de Canarias",
}

LICENSE = """The map in maps/ is derived from open data and is published under the Creative Commons Attribution 4.0
International licence (CC BY 4.0, https://creativecommons.org/licenses/by/4.0/). Credit: spainciv
(https://spainciv.djinnfoundry.com), with data from IGN (CC BY 4.0), Copernicus CORINE Land Cover 2018 (EEA),
NOAA ETOPO1, Natural Earth, IGME-CSIC (Estadística Minera de España 2019) and the Ministerio de Agricultura, Pesca y
Alimentación (CC BY 4.0).
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
        MAP_FILE: lambda: unciv.encode(doc["map"]),
        PREVIEW: lambda: preview(doc),
        shot_path: shot_file.read_bytes,
    }


def preview(doc: dict) -> bytes:
    g = doc["summary"]["grid"]
    grid = unciv.Grid(g["spacing"], g["width"], g["height"], tuple(g["centre"]))
    return unciv.preview_png(grid, unciv.tiles_from_map(doc["map"]))


def mod_entries(country: Country, doc: dict) -> dict[str, bytes]:
    """The mod's files, by path inside its folder (what the GitHub repository holds)."""
    options = unciv.mod_options(AUTHOR, f"https://github.com/{MOD_REPO}")
    return {
        "jsons/ModOptions.json": json.dumps(options, ensure_ascii=False, indent=2).encode("utf-8") + b"\n",
        f"maps/{doc['map']['mapParameters']['name']}": unciv.encode(doc["map"]),
        "preview.png": preview(doc),
        "README.md": readme(country, doc["summary"]).encode("utf-8"),
        "LICENSE": LICENSE.encode("utf-8"),
    }


def mod_zip(country: Country, doc: dict) -> bytes:
    return zip_bytes({f"{MOD_FOLDER}/{path}": data for path, data in mod_entries(country, doc).items()})


def resource_lines(summary: dict) -> list[tuple[str, int, str]]:
    """(Spanish name, tiles, where it comes from) of every placed resource."""
    return [(RESOURCE_ES[r], n, RESOURCE_SOURCE[r]) for r, n in summary["resources"].items()]


def readme(country: Country, summary: dict) -> str:
    rows = "\n".join(f"| {name} | {n} | {src} |" for name, n, src in resource_lines(summary))
    return f"""# Spainciv Unciv

España como mapa de [Unciv](https://github.com/yairm210/Unciv), sacado del mapa de
[spainciv](https://{country.site_url}): costa, relieve, ríos, cubierta del suelo y recursos de datos abiertos.
Spain as an Unciv map, built from open data by spainciv.

- {summary['grid']['width']} × {summary['grid']['height']} casillas de {summary['tile_km']:g} km
  ({summary['land_tiles']} de tierra, {summary['national_land_tiles']} de ellas españolas).
- Reglas: Civ V - Gods & Kings, el conjunto de reglas por defecto. Probado en Unciv {summary['unciv_release']}.
- España empieza en Madrid; los demás jugadores, en {len(summary['starts']) - 1} grandes áreas urbanas.

| Recurso | Casillas | De dónde sale |
|---|---|---|
{rows}

Cómo jugarlo y qué es dato real y qué es convención del juego: https://{country.site_url}/{PAGE}
"""


# --- the page -----------------------------------------------------------------------------------------------------------

STYLE = """
html, body { height: auto; overflow: auto; background: #0d2a47; }
main { max-width: 760px; margin: 0 auto; padding: 24px 16px 48px; line-height: 1.55; font-size: 16px; }
h1 { font: normal 30px var(--serif); letter-spacing: .08em; text-transform: uppercase; color: var(--gold-bright); margin: 8px 0 4px; }
h2 { font: normal 15px var(--serif); letter-spacing: .18em; text-transform: uppercase; color: var(--gold); border-bottom: 1px solid var(--line); padding-bottom: 4px; margin: 32px 0 12px; }
a { color: var(--gold-bright); }
.back { font-size: 14px; }
.panel.box { padding: 14px 18px; margin: 16px 0; }
.downloads { display: flex; flex-wrap: wrap; gap: 10px; }
.downloads a { display: inline-block; padding: 8px 14px; border: 1px solid var(--line); border-radius: 6px; text-decoration: none; background: var(--panel-2); }
figure { margin: 18px 0; }
figure img { width: 100%; height: auto; border: 1px solid var(--line); border-radius: 6px; display: block; }
figcaption { font-size: 13px; color: var(--ink-dim); margin-top: 6px; }
ol li, ul li { margin: 4px 0; }
code { background: rgba(0,0,0,.35); padding: 1px 5px; border-radius: 4px; font-size: 14px; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { text-align: left; vertical-align: top; padding: 6px 8px; border-bottom: 1px solid rgba(201,164,92,.25); }
th { color: var(--gold); font-weight: normal; }
td.n { text-align: right; white-space: nowrap; }
"""


def page_html(country: Country, summary: dict) -> str:
    s = summary
    map_name = s["map_name"]
    fine_km = country.hex_radius_km * math.sqrt(3)
    gap_km = s["start_gap_tiles"] * s["tile_km"]
    starts = [x["city"] for x in s["starts"][1:]]
    resources = "".join(f"<tr><td>{escape(name)}</td><td class=n>{n}</td><td>{escape(src)}</td></tr>"
                        for name, n, src in resource_lines(s))
    not_placed = ", ".join(f"{RESOURCE_ES[r].lower()} {n}" for r, n in s["not_placed"].items())
    designations = ", ".join(s["not_placed_designations"])
    zip_name = MOD_ZIP.rsplit("/", 1)[1]
    url = f"https://{country.site_url}"
    return f"""<!doctype html>
<html lang="{country.lang}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Jugar en Unciv — {escape(country.product)}</title>
  <meta name="description" content="Cómo jugar el mapa de España de {escape(country.product)} en Unciv, la versión libre de Civilization V, en el ordenador y en Android.">
  <link rel="canonical" href="{url}/{PAGE}">
  <meta name="theme-color" content="#131e2a">
  <link rel="stylesheet" href="css/style.css">
  <style>{STYLE}</style>
</head>
<body>
<main>
  <p class="back"><a href="./">Volver al mapa</a></p>
  <h1>Jugar en Unciv</h1>
  <p>El mapa de España de {escape(country.product)} se puede jugar en <a href="https://github.com/yairm210/Unciv">Unciv</a>,
  la versión libre y gratuita de Civilization V para Windows, macOS, Linux y Android. Son {s['grid']['width']} × {s['grid']['height']}
  casillas de {s['tile_km']:g} km: la península, Baleares, Canarias (en su recuadro, como en el mapa), Ceuta, Melilla
  y la tierra vecina de Portugal, Francia y el norte de África. España empieza en Madrid.</p>

  <div class="panel box downloads">
    <a href="{MOD_ZIP}" download>Mod para Unciv ({zip_name})</a>
    <a href="{MAP_FILE}" download="{escape(map_name)}">Solo el mapa</a>
  </div>

  <figure>
    <img src="{SCREENSHOT[0]}" alt="Una partida en Unciv sobre el mapa de España" loading="lazy">
    <figcaption>Una partida en Unciv {s['unciv_release']} sobre este mapa, en el turno 40, con el mapa descubierto: España
    en Madrid y otras siete civilizaciones en las grandes ciudades.</figcaption>
  </figure>

  <h2>En el ordenador (Windows, macOS, Linux)</h2>
  <ol>
    <li>Instala Unciv como dice <a href="https://github.com/yairm210/Unciv#how-do-i-install">su página</a>: en Windows,
      el instalador <a href="https://github.com/yairm210/Unciv/releases/latest/download/Unciv.msi">Unciv.msi</a>; en
      Linux, Flathub o itch.io; en macOS, <code>brew install unciv</code>.</li>
    <li>Abre Unciv y entra en <b>Mods</b>. Pulsa <b>Descargar mod con Enlace</b>, pega
      <code>{url}/{MOD_ZIP}</code> y pulsa <b>Descargar</b>.</li>
    <li>Vuelve al menú y pulsa <b>Nueva partida</b>. En <b>Mapa</b> elige <b>Personalizado</b> y, en <b>Escoger mapa</b>,
      <b>{escape(map_name)}</b>.</li>
    <li>Pulsa <b>Seleccionar jugadores según las posiciones iniciales</b>: juegas con España. Añade rivales con el
      <b>+</b> de la lista de jugadores; cada uno empieza en una gran ciudad: {escape(', '.join(starts))}.</li>
    <li>Pulsa <b>¡Empezar partida!</b>.</li>
  </ol>
  <p>Sin el mod: descarga <a href="{MAP_FILE}" download="{escape(map_name)}">solo el mapa</a> y guárdalo, con el nombre
  <code>{escape(map_name)}</code> y sin extensión, en la carpeta <code>maps</code> de los datos de Unciv (si lo abres con
  <code>java -jar Unciv.jar</code>, es la carpeta del .jar). Aparece en <b>Escoger mapa</b> y en el editor de mapas.</p>

  <h2>En Android</h2>
  <ol>
    <li>Instala Unciv desde Google Play o F-Droid.</li>
    <li>Abre Unciv, entra en <b>Mods</b>, pulsa <b>Descargar mod con Enlace</b>, pega
      <code>{url}/{MOD_ZIP}</code> y pulsa <b>Descargar</b>.</li>
    <li>Sigue desde el paso 3 de arriba. En Android no hace falta el mapa suelto: el mod lo lleva dentro.</li>
  </ol>

  <h2>Desde el buscador de mods de Unciv</h2>
  <p>El mod también está en GitHub (<a href="https://github.com/{MOD_REPO}">{MOD_REPO}</a>), así que aparece en la
  lista de mods del juego: entra en <b>Mods</b>, busca <b>Spainciv</b> en <b>Mods Descargables</b> (o en la categoría
  <b>Maps</b>), elígelo y pulsa <b>Descargar</b>. Por ahí también llegan las actualizaciones.</p>

  <h2>Qué es real y qué es del juego</h2>
  <table>
    <tr><th>En el mapa</th><th>De dónde sale</th></tr>
    <tr><td>Tierra, mar, lagos e islas</td><td>Real: el mapa de {escape(country.product)} (IGN, Natural Earth, ETOPO1).
      Una casilla es tierra si lo es al menos la mitad de los hexágonos de {fine_km:g} km que cubre; ninguna isla del mapa
      desaparece. El mar junto a la costa o con menos de {-unciv.COAST_DEPTH_M} m de fondo es Costa; el resto, Océano.</td></tr>
    <tr><td>Montañas y colinas</td><td>Real: el relieve de ETOPO1. Montaña si el {round(unciv.MOUNTAIN_SHARE * 100)} % de la casilla es
      montaña en el mapa de {escape(country.product)} o tiene algún hexágono de cumbres; colina si lo es el
      {round(unciv.HILL_SHARE * 100)} %. En Unciv las montañas no se pueden cruzar.</td></tr>
    <tr><td>Bosque, pradera, llanura, marisma</td><td>Real: CORINE Land Cover 2018. Bosque donde el bosque cubre el
      {unciv.FOREST_PCT} % o más; pradera donde prados, pastos y humedales pesan más que cultivos y matorral; marisma donde los
      humedales pasan del {unciv.MARSH_PCT} %. El resto es llanura.</td></tr>
    <tr><td>Tundra</td><td>Convención: sin datos de clima, la altitud hace de frío: la tierra a {unciv.TUNDRA_ELEV_M} m o más de
      altitud media es tundra.</td></tr>
    <tr><td>Portugal, Francia y el norte de África</td><td>Su relieve es real; su cubierta del suelo no está en los
      datos, así que son llanura, sin bosques ni recursos.</td></tr>
    <tr><td>Ríos</td><td>Real: los ríos del mapa de {escape(country.product)} (Natural Earth), llevados a los bordes de las casillas,
      como los dibuja Unciv ({s['river_edges']} tramos).</td></tr>
    <tr><td>Peñón de Gibraltar</td><td>La única maravilla natural de Unciv que está de verdad en este mapa, en la casilla
      de Gibraltar.</td></tr>
    <tr><td>Puntos de partida</td><td>España en Madrid y {len(starts)} puntos más en las mayores áreas urbanas del AUDES,
      a {gap_km:g} km o más unos de otros. Los rivales los ocupan al azar y las ciudades-estado se quedan con los que
      sobran; si no hay bastantes, el juego les busca sitio.</td></tr>
  </table>

  <h2>Recursos</h2>
  <p>Cada recurso sale de un dato y va a la casilla de su mina o su municipio, o a la que más superficie tiene de su
  denominación de origen. Unciv solo deja cada recurso sobre ciertos terrenos (el vino en pradera o llanura, el ganado
  en pradera, las ovejas en colinas); si su casilla no vale, va a la vecina que valga, y si ninguna vale no se pone.
  Hay uno por casilla, y varias minas de lo mismo juntas dan uno. Las cantidades de hierro y petróleo son las de un
  yacimiento grande de Unciv.</p>
  <table>
    <tr><th>Recurso</th><th>Casillas</th><th>De dónde sale</th></tr>
    {resources}
  </table>
  <p>Sin casilla se quedaron: {escape(not_placed)}. Casi todas las canteras de piedra caen en llanura, donde Unciv no
  pone piedra; y estas denominaciones no encontraron sitio libre que las admita: {escape(designations)}.</p>
  <p>No hay caballos, carbón, aluminio ni uranio: la Estadística Minera de 2019 no registra minas activas de carbón,
  uranio ni bauxita, y ningún dato del mapa dice dónde se crían caballos.</p>

  <h2>Créditos</h2>
  <p>Mapa: <a href="{url}/">{escape(country.product)}</a>, con datos del IGN, Copernicus (CORINE Land Cover 2018), NOAA (ETOPO1),
  Natural Earth, el IGME y el Ministerio de Agricultura. El mod se publica con licencia CC BY 4.0.
  Unciv es de Yair Morgenstern y sus colaboradores (MPL 2.0).</p>
</main>
</body>
</html>
"""

