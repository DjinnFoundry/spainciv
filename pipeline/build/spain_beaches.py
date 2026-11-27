"""The Blue Flag beaches lens: each beach ADEAC lists, at the beach itself when Wikidata or OpenStreetMap has it by
name in its municipality, else on its municipality's coast (DECISIONS E24, E74, E75).

Matching (`match`): an ADEAC beach and a record are the same beach when one of the beach's name forms (`forms`: the
whole name, without its bracket, the bracket alone, each part of a name joined with '-', '/' or 'y') has the same key
(`name_key`) as one of the record's names, and the record is in one of the beach's municipalities. A record is in a municipality
when its point is within MATCH_KM of the outline and, for a Wikidata item that gives INE codes (P131), one of them is
that municipality's (the SIANE 1:3M outline leaves many beaches just offshore).
Wikidata is tried first, then OSM, form by form. Several records with the key: those inside the outline if any; they
must lie within SPREAD_KM of each other (a beach mapped in pieces, or twice), and the beach goes at their mean, else
that source has no answer.
"""

from __future__ import annotations

import math
import re
from functools import partial

from ..core import names
from ..core.geo import Shape, lonlat_scale, spread_mean
from ..core.hexgrid import HexGrid
from ..core.lang import tr
from .cities import nearest_land
from .spain_named import named_counts, shore_cell
from .spain_wonders import place_key

REQUIRES = ["bandera_azul", "wikidata_playas", "osm_playas"]

# ADEAC's municipality names that are not INE's: (province, ADEAC name) → INE codes (the first holds a shared beach).
BEACH_TOWNS = {("03", "Vila Joiosa"): ["03139"], ("07", "Palma de Mallorca"): ["07040"],
               ("08", "Pineda del Mar"): ["08163"], ("15", "Riveira"): ["15073"],
               ("33", "Castropol- Tapia de Casariego"): ["33017", "33070"], ("35", "Villa de Agüimes"): ["35002"],
               ("38", "Pinar del Hierro"): ["38901"], ("51", "Ciudad Autónoma de Ceuta"): ["51001"],
               ("52", "Ciudad Autónoma de Melilla"): ["52001"]}
BEACH_REACH_KM = 15  # an unplaced beach of a municipality that owns no coastal hex: coastal hexes this close
MATCH_KM = 2.0  # a record this close to a municipality's outline is in it
SPREAD_KM = 2.0  # records of one beach lie this close to each other

# Words a beach name may carry or drop without naming another beach: the word for beach in the languages of Spain
# and the articles, prepositions and conjunctions of Spanish, Catalan, Galician, Asturian and Basque spelling.
BEACH_WORDS = {"playa", "playas", "platja", "platges", "praia", "praias", "praya", "hondartza", "hondartzak", "fluvial"}
GLUE = {"de", "del", "dels", "des", "d", "da", "do", "das", "dos", "la", "las", "los", "el", "lo", "l", "les", "els",
        "sa", "ses", "s", "es", "so", "o", "a", "os", "as", "en", "na", "y", "i", "e"}
DROPPED = frozenset(BEACH_WORDS | GLUE)

# A beach name without accents, case, punctuation, the word for beach and articles: 'Playa de la Concha', 'La Concha'
# and 'Praia da Concha' all give 'concha'; 'Platja de l'Arenal' and "L´Arenal" give 'arenal'.
name_key = partial(names.name_key, dropped=DROPPED)


def forms(name: str) -> list[str]:
    """The keys an ADEAC beach name may go by, in order: the whole name, the name without its bracket, the bracket,
    then each part of a name joined with '-', '/' or 'y'/'i'/'e' ('Venus-Bajadilla': Venus, Bajadilla)."""
    out: list[str] = []
    bare = re.sub(r"\s*\(.*?\)", "", name).strip()
    candidates = [name, bare, *re.findall(r"\((.*?)\)", name), *re.split(r"\s*[-–/]\s*|\s+[yie]\s+", bare)]
    for c in candidates:
        if (k := name_key(c)) and k not in out:
            out.append(k)
    return out


def beach_towns(beach: dict, by_key: dict) -> list[str]:
    """The INE codes of the municipalities a Blue Flag beach belongs to (two for a beach they share)."""
    key = (beach["province"], beach["municipality"])
    if key in BEACH_TOWNS:
        return BEACH_TOWNS[key]
    codes = []
    for part in beach["municipality"].split("/"):
        code = by_key.get((beach["province"], place_key(part)))
        if not code:
            raise RuntimeError(f"Blue Flag: no municipality {beach['municipality']!r} in province {beach['province']}")
        codes.append(code)
    return codes


class Outline:
    """A municipality's SIANE outline: whether a point is inside, and how far outside."""

    def __init__(self, rings: list[list[tuple[float, float]]]):
        self.shape = Shape(rings)
        x0, y0, x1, y1 = self.shape.bbox
        pad = MATCH_KM / 80  # degrees, generous at Spain's latitudes
        self.near_box = (x0 - pad, y0 - pad, x1 + pad, y1 + pad)

    def distance(self, p: tuple[float, float]) -> float:
        x0, y0, x1, y1 = self.near_box
        if not (x0 <= p[0] <= x1 and y0 <= p[1] <= y1):
            return math.inf
        return self.shape.distance(*p, *lonlat_scale(p[1]))  # km, flat around p


def pick(found: list[tuple[float, dict]]) -> tuple[float, float] | None:
    """One position from the records that match (distance to the outline, record): those inside if any; their mean if
    they lie within SPREAD_KM of each other, else none (two beaches of the same name)."""
    inside = [r for d, r in found if d == 0] or [r for _, r in found]
    return spread_mean([r["lonlat"] for r in inside], SPREAD_KM)


def index(records: list[dict]) -> dict[str, list[dict]]:
    """name key → records with a name of that key."""
    out: dict[str, list[dict]] = {}
    for r in records:
        for k in {name_key(n) for n in r["names"]} - {""}:
            out.setdefault(k, []).append(r)
    return out


def match(beach_forms: list[str], towns: list[str], outlines: dict[str, Outline],
          wikidata: dict[str, list[dict]], osm: dict[str, list[dict]]) -> tuple[str, str, tuple[float, float]] | None:
    """(source, record id, lon/lat) of the first source and name form with an answer (module docstring), or None."""
    town_set = set(towns)
    for source, by_key in (("wikidata_playas", wikidata), ("osm_playas", osm)):
        for key in beach_forms:
            found = []
            for r in by_key.get(key, []):
                if source == "wikidata_playas" and r["ine"] and not town_set.intersection(r["ine"]):
                    continue
                d = min(outlines[t].distance(r["lonlat"]) for t in towns)
                if d <= MATCH_KM:
                    found.append((d, r))
            if found and (where := pick(found)):
                return source, "+".join(r["id"] for _, r in found), where
    return None


def place(beaches: list[dict], municipalities: list[dict], wikidata: list[dict], osm: list[dict]) -> list[dict]:
    """Each ADEAC beach with `towns` (INE codes) and, when matched, `lonlat`, `source` and `record`."""
    by_key = {(m["state_fips"], place_key(part)): m["geoid"] for m in municipalities for part in m["name"].split("/")}
    rings = {m["geoid"]: m["rings"] for m in municipalities}
    outlines: dict[str, Outline] = {}
    wd, om = index(wikidata), index(osm)
    out = []
    for b in beaches:
        towns = beach_towns(b, by_key)
        for t in towns:
            outlines.setdefault(t, Outline(rings[t]))
        beach = {**b, "towns": towns}
        if found := match(forms(b["beach"]), towns, outlines, wd, om):
            beach["source"], beach["record"], beach["lonlat"] = found
        out.append(beach)
    return out


def beaches_lens(placed: list[dict], municipalities: list[dict], world: dict, grid: HexGrid, proj) -> dict:
    """Blue Flag beaches per hex. A matched beach sits on the land hex at its point (or the nearest one next to it).
    An unmatched one stays where ADEAC puts it, in its municipality: its municipality's beaches without a point take its
    coastal hexes in turn, nearest its centre first; a municipality too small to own a hex uses the coastal hexes within
    BEACH_REACH_KM of its centre; a lake or river beach (no coast near) its nearest land hex."""
    owner, county, geoids = world["owner"], world["county"], world["counties"]
    centre = {m["geoid"]: m["centre"] for m in municipalities}
    hexes: dict[str, list[int]] = {}
    for c, (o, ci) in enumerate(zip(owner, county)):
        if o >= 0 and ci >= 0:
            hexes.setdefault(geoids[ci], []).append(c)
    coastal = {c for c, o in enumerate(owner) if o >= 0 and any(owner[n] == -1 for n in grid.neighbours(c))}
    used: dict[str, int] = {}
    cells_of = []
    for b in placed:
        if "lonlat" in b and (cell := shore_cell(grid, owner, *proj(*b["lonlat"]))) >= 0:
            cells_of.append([cell])
            continue
        town = b["towns"][0]
        x, y = proj(*centre[town])
        dist = lambda c: math.dist(grid.center(*grid.col_row(c)), (x, y))
        own = hexes.get(town, [])
        options = ([c for c in own if c in coastal] or [c for c in coastal if dist(c) <= BEACH_REACH_KM] or own
                   or [nearest_land(grid, owner, max(grid.cell_at(x, y), 0), x, y, -1)])
        options.sort(key=dist)
        turn = used.get(town, 0)
        cells_of.append([options[turn % len(options)]])
        used[town] = turn + 1
    n, matched = len(placed), sum("lonlat" in b for b in placed)
    return {
        "id": "beaches", "group": "heritage", "name": tr("Bandera Azul", "Blue Flag"), "icon": "l-beaches",
        "emoji": "🏖️", "unit": tr("playas con Bandera Azul", "Blue Flag beaches"), "format": "int", "scale": "linear",
        "higher_is": "good", "domain": [0, 6],
        "ramp": ["#0d2b45", "#134f74", "#1a77a3", "#2ea3c9", "#7fd1e3", "#e6f8fb"],
        "source": "bandera_azul",
        "description": tr(
            "Las {n} playas con Bandera Azul en 2026-27, con su nombre y municipio al pasar el ratón. ADEAC da el "
            "municipio de cada playa, no su posición: {matched} están en su sitio porque Wikidata u OpenStreetMap "
            "tienen una playa con ese nombre en ese municipio; las otras {rest} se reparten por la costa de su "
            "municipio.",
            "The {n} Blue Flag beaches of 2026-27, with name and municipality on hover. ADEAC gives each beach's "
            "municipality, not its position: {matched} are in place because Wikidata or OpenStreetMap has a beach of "
            "that name in that municipality; the other {rest} are shared among their municipality's coastal hexes."
        ).format(n=n, matched=matched, rest=n - matched),
        **named_counts([f"{b['beach']} ({b['municipality']})" for b in placed], cells_of, owner),
    }
