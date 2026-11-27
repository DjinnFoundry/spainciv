"""Spain's wildlife lenses (group "Fauna"): where the Iberian lynx, the brown bear, the wolf, the Spanish imperial eagle
and the bearded vulture were reported in 2013-2018 (pipeline/sources/es/especies.py), with the latest lynx and wolf
censuses as text (censos_fauna.py).

* **Value**: the share of each land hex inside the species' 10 km squares, from 0 to 1 on a fixed scale. The squares
  are cells of the EEA reference grid in ETRS89-LAEA (EPSG:3035), named by their south-west corner in units of 10 km
  ("10kmE316N182"), so a point's square is its LAEA coordinates divided by 10 km: each hex looks up the squares of
  the points of `hex_lattice` at 1 km (84 per hex), once for all species.
* **Reported presence, not suitability**: an empty square may be one nobody surveyed or reported, and the lens says so
  in its legend. Nothing here models where a species could live.
* **Census sentence**: the communities a census names that the 2013-2018 squares do not reach, worked out from the
  hexes (hex → province → community), so it changes when the data do.

The builder is spain.py, which calls `lenses()`; SOURCES go into its REQUIRES. Rules: DECISIONS.md E84, F35, F36.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from ..core.geo import LambertAzimuthalEllipsoid
from ..core.hexgrid import HexGrid
from ..core.lang import Text, and_list, tr
from ..core.store import load_interim
from ..countries import active
from ..sources.es.especies import SPECIES
from ..sources.es.provinces import COMMUNITY_OF, community_name
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
CENSUS_UNITS = {"individuals": tr("ejemplares", "individuals"), "packs": tr("manadas", "packs")}
UNIT = tr("del hexágono en cuadrículas con la especie", "of the hex in squares where it was reported")
NOTE = tr("Cuadrículas de 10 km con la especie en {first}-{last}; una vacía no prueba que no esté.",
          "10 km squares where it was reported in {first}-{last}; an empty one does not prove it is absent.")


def same_species(lenses: dict, species: dict) -> None:
    """LENSES and especies.SPECIES must name the same species: one list decides what is read, the other what is shown."""
    if set(lenses) != set(species):
        raise RuntimeError(f"spain_fauna.LENSES and especies.SPECIES differ: only in LENSES "
                           f"{sorted(set(lenses) - set(species))}, only in SPECIES {sorted(set(species) - set(lenses))}")


def cell_code(x: float, y: float) -> str:
    """The EEA 10 km square of an ETRS89-LAEA point in metres."""
    return f"10kmE{int(x // 10000)}N{int(y // 10000)}"


def cell_codes(owner: list[int], proj, grid: HexGrid, laea=None) -> tuple[dict[int, Counter], int]:
    """For each land hex, how many of its lattice points (1 km apart) fall in each EEA 10 km square; and the number of
    points per hex."""
    laea = laea or LambertAzimuthalEllipsoid()
    lattice = hex_lattice(grid.radius, 1.0)
    out = {}
    for i, o in enumerate(owner):
        if o < 0:
            continue
        cx, cy = grid.center(*grid.col_row(i))
        out[i] = Counter(cell_code(*laea(*proj.inverse(cx + ox, cy + oy))) for ox, oy in lattice)
    return out, len(lattice)


def shares(codes: dict[int, Counter], points: int, cells: set[str], size: int) -> list[float | None]:
    """Share of each land hex in `cells`, rounded to 0.01; None off land."""
    values: list[float | None] = [None] * size
    for i, counts in codes.items():
        values[i] = round(sum(n for code, n in counts.items() if code in cells) / points, 2)
    return values


def census_text(census: dict, values: list, owner: list[int], states: list[str], period: list[int]) -> Text:
    """The census figure and the communities it names that the map's squares do not reach (no hex > 0 there)."""
    reached = {COMMUNITY_OF.get(states[owner[i]]) for i, v in enumerate(values) if v}
    names = [community_name(c) for c in census["communities"]]
    missing = [community_name(c) for c in census["communities"] if c not in reached]
    text = tr("El censo de {period} cuenta {figure} {unit} en {communities}; ",
              "The {period} census counts {figure} {unit} in {communities}; ").format(
        period=census["period"], figure=census["figure"], unit=CENSUS_UNITS[census["unit"]],
        communities=and_list(names))
    first, last = period
    if missing:
        text += tr("el mapa de {first}-{last} no llega a {missing}.",
                   "the {first}-{last} map does not reach {missing}.").format(
            first=str(first), last=str(last), missing=and_list(missing))
    else:
        text += tr("el mapa de {first}-{last} llega a todas.", "the {first}-{last} map reaches all of them.").format(
            first=str(first), last=str(last))
    if "stable_cells" in census:
        text += tr(" El mapa oficial de {first}-{last} tiene {n} cuadrículas; el censo {period} da {stable} de "
                   "presencia estable y {sporadic} esporádica, que el ministerio publica solo como figura.",
                   " The official {first}-{last} map has {n} squares; the {period} census gives {stable} of stable "
                   "presence and {sporadic} of sporadic presence, which the ministry publishes only as a picture.").format(
            first=str(first), last=str(last), n=census["map_cells"], period=census["period"],
            stable=census["stable_cells"], sporadic=census["sporadic_cells"])
    return text


def fauna_lens(name: str, sp: dict, period: list[int], values: list, census: dict | None, world: dict) -> dict:
    meta = LENSES[name]
    first, last = period
    description = tr(
        "{common} ({name}): parte de cada hexágono que cae en las cuadrículas de 10 km (red de referencia europea, "
        "ETRS89-LAEA) donde España notificó la especie a la Unión Europea en {first}-{last}, según {directive} "
        "(Ministerio para la Transición Ecológica y el Reto Demográfico, Banco de Datos de la Naturaleza; {n} "
        "cuadrículas). La parte se mide en {points} puntos por hexágono, a 1 km unos de otros. Una cuadrícula sitúa la "
        "especie en algún lugar de sus 100 km², no localiza madrigueras ni nidos; los ficheros del ministerio no marcan "
        "ninguno de estos registros como sensible. Una cuadrícula vacía puede no haberse muestreado o no haberla "
        "notificado su comunidad. En Canarias no vive ninguna de estas cinco especies.",
        "{common} ({name}): the part of each hex inside the 10 km squares (European reference grid, ETRS89-LAEA) where "
        "Spain reported the species to the European Union for {first}-{last}, in {directive} (Ministerio para la "
        "Transición Ecológica y el Reto Demográfico, Banco de Datos de la Naturaleza; {n} squares). The part is "
        "measured at {points} points per hex, 1 km apart. A square places the species somewhere in its 100 km² and "
        "does not locate dens or nests; the ministry's files mark none of these records as sensitive. An empty square "
        "may not have been surveyed, or its community may not have reported it. None of these five species lives in "
        "the Canary Islands.",
    ).format(common=meta["name"], name=name, first=str(first), last=str(last), directive=DIRECTIVES[sp["directive"]],
             n=len(sp["cells"]), points=sp["points"])
    if census:
        description += " " + census_text({**census, "map_cells": len(sp["cells"])}, values, world["owner"],
                                         world["states"], period)
    return {
        "id": meta["id"], "group": GROUP, "name": meta["name"], "icon": meta["icon"], "emoji": meta["emoji"],
        "ramp": meta["ramp"], "unit": UNIT, "format": "pct", "scale": "linear", "domain": [0, 1],
        "higher_is": "neutral", "source": "bdn_especies",
        "note": NOTE.format(first=str(first), last=str(last)), "description": description, "values": values,
    }


def lenses(world: dict, proj, grid: HexGrid, laea=None) -> list[dict]:
    """One lens per species, in the order of LENSES. Fails if a species has more than MAX_UNMATCHED of its squares on
    no land hex (a projection or grid mismatch, not border squares abroad). `laea` replaces EPSG:3035 in tests."""
    same_species(LENSES, SPECIES)
    data, censuses = load_interim("bdn_especies"), load_interim("miteco_censos_fauna")["censuses"]
    owner = world["owner"]
    codes, points = cell_codes(owner, proj, grid, laea)
    seen = set().union(*codes.values())
    out = []
    for name in LENSES:
        sp = data["species"][name]
        cells = set(sp["cells"])
        unmatched = sorted(cells - seen)
        hexes = sum(any(c in cells for c in counts) for counts in codes.values())
        print(f"    {name}: {len(cells)} squares, {hexes} hexes > 0; {len(unmatched)} squares on no Spanish land hex"
              + (f" ({', '.join(unmatched[:8])})" if unmatched else ""))
        if len(unmatched) > MAX_UNMATCHED * len(cells):
            raise RuntimeError(f"{name}: {len(unmatched)} of {len(cells)} squares touch no land hex: is the cell lookup "
                               f"still EPSG:3035?")
        values = shares(codes, points, cells, len(owner))
        out.append(fauna_lens(name, {**sp, "points": points}, data["period"], values, censuses.get(name), world))
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
