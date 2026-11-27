"""Spain's wildlife lenses (group "Fauna"): where the Iberian lynx, the brown bear, the wolf, the Spanish imperial eagle
and the bearded vulture were reported in 2013-2018 (pipeline/sources/es/especies.py), with the latest lynx and wolf
censuses as text (censos_fauna.py).

* **Value**: the share of each land hex inside the species' 10 km squares, from 0 to 1 on a fixed scale. The squares
  are cells of the EEA reference grid in ETRS89-LAEA (EPSG:3035), named by their south-west corner in units of 10 km
  ("10kmE316N182"), so a point's square is its LAEA coordinates divided by 10 km: each hex looks up the squares of
  the points of `hex_lattice` at 1 km (84 per hex), once for all species.
* **Reported presence, not suitability**: an empty square may be one nobody surveyed or reported, and the legend's
  note says so. Nothing here models where a species could live, and the 2013-2018 squares are not where it is today.
* **Census sentence**: the communities a census names that the 2013-2018 squares do not reach. Each lattice point is
  given the community of the municipality it falls in (not the hex's majority owner), so a border hex whose reported
  half lies in the neighbouring community counts for that community; a point in no Spanish municipality counts for
  none.

The builder is spain.py, which calls `lenses()`; SOURCES go into its REQUIRES. Rules: DECISIONS.md E90, F37, F38.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from ..core.geo import LambertAzimuthalEllipsoid, Shape, ShapeIndex
from ..core.hexgrid import HexGrid
from ..core.lang import Text, and_list, nor_list, tr
from ..core.store import load_interim
from ..countries import active
from ..sources.es.especies import SPECIES
from ..sources.es.provinces import COMMUNITY_NAMES, COMMUNITY_OF
from .world import hex_lattice

SOURCES = ["bdn_especies", "miteco_censos_fauna"]
GROUP = "fauna"
MIN_HEXES = 50  # check(): a lens with fewer hexes > 0 than this means the squares and the hexes did not meet
MAX_UNMATCHED = 0.05  # share of a species' squares that may touch no land hex (border squares abroad) before it fails

# Scientific name (especies.SPECIES) → the lens. The icons fall back to the emoji; the emoji are a game convention
# (there is no lynx or vulture emoji).
LENSES = {
    "Lynx pardinus": {"id": "lynx", "name": tr("Lince ibérico", "Iberian lynx"), "emoji": "🐈", "icon": "l-lynx",
                      "ramp": ["#1a1408", "#463c22", "#72643c", "#9e8c56", "#cab470", "#f6dc8a"]},
    "Ursus arctos": {"id": "bear", "name": tr("Oso pardo", "Brown bear"), "emoji": "🐻", "icon": "l-bear",
                     "ramp": ["#160f0a", "#403124", "#6a533d", "#937557", "#bd9770", "#e7b98a"]},
    "Canis lupus": {"id": "wolf", "name": tr("Lobo", "Wolf"), "emoji": "🐺", "icon": "l-wolf",
                    "ramp": ["#0f141c", "#353d47", "#5c6672", "#828e9c", "#a9b7c7", "#cfe0f2"]},
    "Aquila adalberti": {"id": "imperial_eagle", "name": tr("Águila imperial ibérica", "Spanish imperial eagle"),
                         "emoji": "🦅", "icon": "l-imperial-eagle",
                         "ramp": ["#15120a", "#443c27", "#736644", "#a18f60", "#d0b97d", "#ffe39a"]},
    "Gypaetus barbatus": {"id": "bearded_vulture", "name": tr("Quebrantahuesos", "Bearded vulture"), "emoji": "🦴",
                          "icon": "l-bearded-vulture",
                          "ramp": ["#170c0a", "#432a21", "#6f4838", "#9b664e", "#c78465", "#f3a27c"]},
}
DIRECTIVES = {
    "art17": tr("el informe del artículo 17 de la Directiva de Hábitats",
                "the report under Article 17 of the Habitats Directive"),
    "art12": tr("el informe del artículo 12 de la Directiva de Aves, que recoge el área de cría",
                "the report under Article 12 of the Birds Directive, which gives the breeding range"),
}
ARTICLES = {"art17": tr("art. 17 de la Directiva de Hábitats", "Habitats Directive, Art. 17"),
            "art12": tr("art. 12 de la Directiva de Aves, área de cría", "Birds Directive, Art. 12, breeding range")}
CENSUS_UNITS = {"individuals": tr("ejemplares", "individuals"), "packs": tr("manadas", "packs")}
UNIT = tr("del hexágono en cuadrículas con la especie", "of the hex in squares where it was reported")
SCALE_TEXT = tr("Escala fija de 0 a 100 %", "Fixed scale from 0 to 100%")
NOTE = tr("Cuadrículas de 10 km notificadas a la UE para {first}-{last} ({article}).{census} Una cuadrícula vacía no "
          "prueba que la especie no esté.",
          "10 km squares reported to the EU for {first}-{last} ({article}).{census} An empty square does not prove the "
          "species is absent.")


def same_species(lenses: dict, species: dict) -> None:
    """LENSES and especies.SPECIES must name the same species: one list decides what is read, the other what is shown."""
    if set(lenses) != set(species):
        raise RuntimeError(f"spain_fauna.LENSES and especies.SPECIES differ: only in LENSES "
                           f"{sorted(set(lenses) - set(species))}, only in SPECIES {sorted(set(species) - set(lenses))}")


def cell_code(x: float, y: float) -> str:
    """The EEA 10 km square of an ETRS89-LAEA point in metres."""
    return f"10kmE{int(x // 10000)}N{int(y // 10000)}"


def cell_codes(owner: list[int], proj, grid: HexGrid, municipalities: list[dict], laea=None
               ) -> tuple[dict[int, Counter], int]:
    """For each land hex, how many of its lattice points (1 km apart) fall in each (EEA 10 km square, community of the
    municipality the point is in, None outside every municipality); and the number of points per hex."""
    laea = laea or LambertAzimuthalEllipsoid()
    index = ShapeIndex([Shape([[proj(lon, lat) for lon, lat in r] for r in m["rings"]]) for m in municipalities],
                       cell_km=20)
    community = [COMMUNITY_OF.get(m["state_fips"]) for m in municipalities]
    lattice = hex_lattice(grid.radius, 1.0)
    out = {}
    for i, o in enumerate(owner):
        if o < 0:
            continue
        cx, cy = grid.center(*grid.col_row(i))
        counts: Counter = Counter()
        for ox, oy in lattice:
            x, y = cx + ox, cy + oy
            k = index.locate(x, y)
            counts[cell_code(*laea(*proj.inverse(x, y))), community[k] if k >= 0 else None] += 1
        out[i] = counts
    return out, len(lattice)


def shares(codes: dict[int, Counter], points: int, cells: set[str], size: int) -> list[float | None]:
    """Share of each land hex in `cells`, rounded to 0.01; None off land."""
    values: list[float | None] = [None] * size
    for i, counts in codes.items():
        values[i] = round(sum(n for (code, _), n in counts.items() if code in cells) / points, 2)
    return values


def reached(codes: dict[int, Counter], cells: set[str]) -> set[str]:
    """The communities with at least one lattice point inside `cells`."""
    return {comm for counts in codes.values() for code, comm in counts if comm and code in cells}


def census_text(census: dict, reached_communities: set[str], period: list[int]) -> Text:
    """The census figure and the communities it names that the squares do not reach; for the wolf, also the census's
    own distribution and why it is not comparable with the squares."""
    first, last = (str(y) for y in period)
    names = [COMMUNITY_NAMES[c] for c in census["communities"]]
    missing = [COMMUNITY_NAMES[c] for c in census["communities"] if c not in reached_communities]
    text = tr("El censo de {period} cuenta {figure} {unit} en {k} comunidades",
              "The {period} census counts {figure} {unit} in {k} communities").format(
        period=census["period"], figure=census["figure"], unit=CENSUS_UNITS[census["unit"]], k=len(names))
    if missing:
        text += tr("; las cuadrículas de {first}-{last} no llegan a {missing}.",
                   "; the {first}-{last} squares do not reach {missing}.").format(
            first=first, last=last, missing=nor_list(missing))
    else:
        text += tr("; las cuadrículas de {first}-{last} llegan a todas.",
                   "; the {first}-{last} squares reach all of them.").format(first=first, last=last)
    text += tr(" Son {communities}.", " They are {communities}.").format(communities=and_list(names))
    if "stable_cells" in census:
        text += tr(" La distribución de {cells_period} del censo tiene {stable} cuadrículas de presencia estable y "
                   "{sporadic} de presencia esporádica; su mapa (Figura 1) es solo una imagen. Esas cuadrículas y las "
                   "{n} de {first}-{last} salen de dos trabajos distintos, el censo y el informe a la UE, y el mapa no "
                   "dice qué parte de la diferencia es crecimiento.",
                   " The census's {cells_period} distribution has {stable} squares of stable presence and {sporadic} "
                   "of sporadic presence; its map (Figure 1) is only a picture. Those squares and the {n} of "
                   "{first}-{last} come from two different pieces of work, the census and the report to the EU, and "
                   "the map does not say how much of the difference is growth.").format(
            cells_period=census["cells_period"], stable=census["stable_cells"], sporadic=census["sporadic_cells"],
            n=census["map_cells"], first=first, last=last)
    return text


def note(sp: dict, census: dict | None, period: list[int]) -> Text:
    """The legend's note, shown on desktop and phone: the squares' age and article, the latest census figure, and that
    an empty square proves nothing."""
    said: Text | str = ""
    if census and "stable_cells" in census:
        said = tr(" Para {p}, el censo da {n} cuadrículas de presencia estable.",
                  " For {p} the census gives {n} squares of stable presence.").format(
            p=census["cells_period"], n=census["stable_cells"])
    elif census:
        said = tr(" El censo de {p} cuenta {n} {unit}.", " The {p} census counts {n} {unit}.").format(
            p=census["period"], n=census["figure"], unit=CENSUS_UNITS[census["unit"]])
    first, last = (str(y) for y in period)
    return NOTE.format(first=first, last=last, article=ARTICLES[sp["directive"]], census=said)


def in_sentence(name: Text) -> Text:
    """A lens name inside a sentence, with its article: "el lince ibérico", "the Iberian lynx", "the wolf" (English
    keeps the capital of a people's adjective)."""
    def one(s: str, lang: str) -> str:
        keep = lang == "en" and s.split()[0] in ("Iberian", "Spanish")
        return ("the " if lang == "en" else "el ") + (s if keep else s[0].lower() + s[1:])
    return name.map(one)


def fauna_lens(name: str, sp: dict, period: list[int], values: list, census: dict | None,
               reached_communities: set[str]) -> dict:
    meta = LENSES[name]
    first, last = (str(y) for y in period)
    # The legend shows three lines of this on desktop: the census and the communities the squares miss come first.
    description = census_text({**census, "map_cells": len(sp["cells"])}, reached_communities, period) + " " \
        if census else ""
    description += tr(
        "Cada hexágono muestra qué parte de su superficie cae en las {n} cuadrículas de 10 km donde España notificó "
        "{common} ({name}) a la Unión Europea para {first}-{last}, según {directive}. Son cuadrículas de la red de referencia "
        "europea (ETRS89-LAEA), del Banco de Datos de la Naturaleza del Ministerio para la Transición Ecológica y el "
        "Reto Demográfico; la parte se mide en {points} puntos por hexágono, a 1 km unos de otros. Una cuadrícula sitúa "
        "la especie en algún lugar de sus 100 km², no localiza madrigueras ni nidos; los ficheros del ministerio no "
        "marcan ninguno de estos registros como sensible. Una cuadrícula vacía puede no haberse muestreado o no haberla "
        "notificado su comunidad.",
        "Each hex shows how much of it lies inside the {n} squares of 10 km where Spain reported {common} ({name}) "
        "to the European Union for {first}-{last}, in {directive}. The squares are those of the European reference grid "
        "(ETRS89-LAEA), from the Banco de Datos de la Naturaleza of the Ministerio para la Transición Ecológica y el "
        "Reto Demográfico; the part is measured at {points} points per hex, 1 km apart. A square places the species "
        "somewhere in its 100 km² and does not locate dens or nests; the ministry's files mark none of these records "
        "as sensitive. An empty square may not have been surveyed, or its community may not have reported it.",
    ).format(common=in_sentence(meta["name"]), name=name,
             n=len(sp["cells"]), first=first, last=last, directive=DIRECTIVES[sp["directive"]], points=sp["points"])
    return {
        "id": meta["id"], "group": GROUP, "name": meta["name"], "icon": meta["icon"], "emoji": meta["emoji"],
        "ramp": meta["ramp"], "unit": UNIT, "format": "pct", "decimals": 0, "unit_in_value": True, "scale": "linear",
        "domain": [0, 1], "bounded": True, "scale_text": SCALE_TEXT, "higher_is": "neutral", "source": "bdn_especies",
        "note": note(sp, census, period), "description": description, "values": values,
    }


def lenses(world: dict, proj, grid: HexGrid, municipalities: list[dict], laea=None) -> list[dict]:
    """One lens per species, in the order of LENSES. Fails if a species has more than MAX_UNMATCHED of its squares on
    no land hex (a projection or grid mismatch, not border squares abroad). `municipalities` (siane) give each point
    its community; `laea` replaces EPSG:3035 in tests."""
    same_species(LENSES, SPECIES)
    data, censuses = load_interim("bdn_especies"), load_interim("miteco_censos_fauna")["censuses"]
    owner = world["owner"]
    codes, points = cell_codes(owner, proj, grid, municipalities, laea)
    seen = {code for counts in codes.values() for code, _ in counts}
    out = []
    for name in LENSES:
        sp = data["species"][name]
        cells = set(sp["cells"])
        unmatched = sorted(cells - seen)
        hexes = sum(any(code in cells for code, _ in counts) for counts in codes.values())
        print(f"    {name}: {len(cells)} squares, {hexes} hexes > 0; {len(unmatched)} squares on no Spanish land hex"
              + (f" ({', '.join(unmatched[:8])})" if unmatched else ""))
        if len(unmatched) > MAX_UNMATCHED * len(cells):
            raise RuntimeError(f"{name}: {len(unmatched)} of {len(cells)} squares touch no land hex: is the cell lookup "
                               f"still EPSG:3035?")
        values = shares(codes, points, cells, len(owner))
        out.append(fauna_lens(name, {**sp, "points": points}, data["period"], values, censuses.get(name),
                              reached(codes, cells)))
    return out


def check(web_dir) -> list[tuple[str, str]]:
    """Spain's map has the five wildlife lenses, each a share 0..1 on land with a legend note, and at least MIN_HEXES
    hexes > 0. Nothing to check on another country's map."""
    if active().id != "es":
        return []
    lenses_by_id = {l["id"]: l for l in json.loads((Path(web_dir) / "lenses.json").read_text())["lenses"]}
    bad, counts = [], {}
    for meta in LENSES.values():
        lens = lenses_by_id.get(meta["id"])
        if lens is None:
            bad.append(f"lens {meta['id']} missing")
            continue
        vals = [v for v in lens["values"] if v is not None]
        counts[meta["id"]] = sum(v > 0 for v in vals)
        if lens.get("group") != GROUP or lens.get("format") != "pct" or not lens.get("note"):
            bad.append(f"lens {meta['id']}: group {lens.get('group')!r}, format {lens.get('format')!r}, "
                       f"note {'present' if lens.get('note') else 'missing'}")
        if any(not 0 <= v <= 1 for v in vals):
            bad.append(f"lens {meta['id']}: values outside 0..1")
        if counts[meta["id"]] < MIN_HEXES:
            bad.append(f"lens {meta['id']}: only {counts[meta['id']]} hexes > 0")
    if bad:
        return [("FAIL", f"wildlife lenses: {m}") for m in bad]
    return [("PASS", "wildlife lenses: " + ", ".join(f"{k} {n} hexes > 0" for k, n in counts.items()))]
