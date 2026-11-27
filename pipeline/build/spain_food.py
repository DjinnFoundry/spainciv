"""The food and drink lens: every Spanish name in the EU register (eAmbrosia) on the hexes of its area.

An area is the Ministry's polygon (calidad_diferenciada, 2017) or, for a name the Ministry has not mapped, the
administrative units its specification delimits (communities, provinces, islands, municipalities), built from the
map's own municipalities: a hex is in a unit when its municipality is. A vino de pago is an estate: one hex, at its
municipality's centre.
"""

from __future__ import annotations

import re
from collections import Counter

from ..core.geo import Shape, ring_area, ring_centroid
from ..core.hexgrid import HexGrid
from ..core.lang import Text, join_texts, tr
from ..sources.es.food import ISLANDS
from ..sources.es.provinces import COMMUNITIES
from .cities import nearest_land
from .spain_named import named_counts


# The words the map adds after a name ('Torrezno de Soria (IGP · provincia)', sources/es/food.py) in English: the EU's
# English abbreviations (PDO, PGI, GI) and the Spanish wine categories that have none, kept as their legal names.
KIND_EN = {"DOP": "PDO", "IGP": "PGI", "IG": "GI", "Vino de pago": "Vino de Pago", "Vino de calidad": "Vino de Calidad"}
HOW_EN = {"comunidad": "community", "provincia": "province", "isla": "island", "municipios": "municipalities",
          "finca": "estate", "sin zona": "no area"}
SUFFIX = re.compile(r"^(?P<name>.*) \((?P<kind>[^()·]+?)(?: · (?P<how>[^()]+))?\)$")


def label(name: str) -> str | Text:
    """A designation as the tooltip lists it: the registered name as it is, and the kind and area the map adds after
    it in each language ('Torrezno de Soria (IGP · provincia)' → '… (PGI · province)')."""
    m = SUFFIX.match(name)
    if not m or m["kind"] not in KIND_EN:
        return name
    how = f" · {', '.join(HOW_EN[h] for h in m['how'].split(', '))}" if m["how"] else ""
    return tr(name, f"{m['name']} ({KIND_EN[m['kind']]}{how})")


def island(municipalities: list[dict], seed: str) -> set[str]:
    """INE codes of the municipalities on the island of `seed`: those linked to it through shared boundary points
    (SIANE outlines of neighbouring municipalities share their vertices)."""
    owners: dict[tuple, set[str]] = {}
    prov = seed[:2]
    for m in municipalities:
        if m["state_fips"] == prov:
            for ring in m["rings"]:
                for point in ring:
                    owners.setdefault(tuple(point), set()).add(m["geoid"])
    links: dict[str, set[str]] = {}
    for shared in owners.values():
        for g in shared:
            links.setdefault(g, set()).update(shared)
    found, todo = {seed}, [seed]
    while todo:
        for g in links.get(todo.pop(), ()):
            if g not in found:
                found.add(g)
                todo.append(g)
    return found


def unit_municipalities(units: list[str], municipalities: list[dict]) -> set[str]:
    """INE codes of the municipalities that make up an area's units ('provincia:42', 'municipio:05057*'…)."""
    out: set[str] = set()
    for unit in units:
        kind, _, value = unit.partition(":")
        if kind == "comunidad":
            provinces = set(COMMUNITIES[value][1])
            out |= {m["geoid"] for m in municipalities if m["state_fips"] in provinces}
        elif kind == "provincia":
            out |= {m["geoid"] for m in municipalities if m["state_fips"] == value}
        elif kind == "isla":
            out |= island(municipalities, ISLANDS[value.replace("_", " ")])
        else:
            out.add(value.rstrip("*"))
    return out


def food_lens(names: list[dict], proj, grid: HexGrid, world: dict, municipalities: list[dict],
              not_registered: list[str]) -> dict:
    """Protected food and drink names whose area holds each land hex's centre. A Ministry polygon that holds no hex
    centre (a small vino de pago) goes to the land hex nearest its centre; an area of units, to the hexes of its
    municipalities (a municipality too small to own one, to the land hex nearest its centre); an estate, to the land
    hex nearest its municipality's centre. Each hex lists its smallest areas first."""
    owner, county, geoids = world["owner"], world["county"], world["counties"]
    centres = {c: grid.center(*grid.col_row(c)) for c in range(grid.size) if owner[c] >= 0}
    centre_of = {m["geoid"]: m["centre"] for m in municipalities}
    hexes_of: dict[str, list[int]] = {}
    for c, k in enumerate(county):
        if owner[c] >= 0 and k >= 0:
            hexes_of.setdefault(geoids[k], []).append(c)

    def nearest(lon: float, lat: float) -> int:
        x, y = proj(lon, lat)
        return nearest_land(grid, owner, max(grid.cell_at(x, y), 0), x, y, -1)

    mapped = [n for n in names if n["area"] != "ninguna"]
    cells_of = []
    for n in mapped:
        if n["area"] == "mapa":
            shape = Shape([[proj(lon, lat) for lon, lat in ring] for ring in n["rings"] if len(ring) >= 3])
            x0, y0, x1, y1 = shape.bbox
            cells = [c for c, (x, y) in centres.items() if x0 <= x <= x1 and y0 <= y <= y1 and shape.contains(x, y)]
            cells = cells or [nearest(*ring_centroid(max(n["rings"], key=lambda r: abs(ring_area(r)))))]
        else:
            codes = sorted(unit_municipalities(n["units"], municipalities))
            if n["area"] == "finca":
                cells = sorted({nearest(*centre_of[g]) for g in codes})
            else:
                cells = sorted({c for g in codes for c in hexes_of.get(g) or [nearest(*centre_of[g])]})
        cells_of.append(cells)
    lens = named_counts([label(n["name"]) for n in mapped], cells_of, owner)
    size = [len(cells) for cells in cells_of]
    lens["labels"] = [None if ks is None else sorted(ks, key=lambda k: (size[k], k)) for ks in lens["labels"]]
    missing = [n for n in names if n["area"] == "ninguna"]
    return {
        "id": "food", "group": "food", "name": tr("Denominaciones de origen", "Designations of origin"),
        "icon": "l-food", "emoji": "🍷",
        "unit": tr("denominaciones (DOP, IGP, vinos)", "designations (PDO, PGI, wines)"), "format": "int", "scale": "linear", "higher_is": "neutral",
        "ramp": ["#2b1320", "#5c1f3a", "#8e3049", "#c25a4a", "#e89a5a", "#ffe0a0"], "source": "calidad_diferenciada",
        "description": description(len(names), Counter(n["area"] for n in mapped), missing, not_registered),
        **lens,
    }


def description(total: int, counts: Counter, missing: list[dict], not_registered: list[str]) -> Text:
    """The lens description: how many names, how each kind of area was obtained (`counts` by area), the names with
    no area and the Ministry's designations left out for no longer being registered."""
    text = tr(
        "Cuántos de los {total} nombres que España tiene en el registro de la UE (eAmbrosia: DOP, IGP, vinos y bebidas "
        "espirituosas) incluyen cada hexágono en su zona. {mapa} zonas son las del Ministerio de Agricultura (revisión "
        "de 2017). Para {unidades} que el Ministerio no ha cartografiado (casi todos los vinos de la tierra y los "
        "registrados desde 2017) la zona es la que delimita su pliego o el documento único de la UE, levantada sobre "
        "los límites municipales del IGN; el tooltip lo dice tras el tipo: «comunidad», «provincia», «isla» o "
        "«municipios» (un municipio que solo entra en parte cuenta entero). Los {finca} vinos de pago sin zona del "
        "Ministerio son una finca: van en un hexágono, el del centro de su municipio («finca»). Cada hexágono lista "
        "primero las zonas más pequeñas.",
        "How many of the {total} names Spain has in the EU register (eAmbrosia: PDO, PGI, wines and spirit drinks) "
        "include each hex in their area. {mapa} areas are those of the Ministry of Agriculture (2017 revision). For "
        "{unidades} the Ministry has not mapped (nearly all the PGI wines and the names registered since 2017) the "
        "area is the one their specification or EU single document delimits, drawn on the IGN's municipal boundaries; "
        "the tooltip says so after the kind: “community”, “province”, “island” or “municipalities” (a municipality "
        "only partly inside counts whole). The {finca} single-estate wines without a Ministry area are an estate: they go on "
        "one hex, that of their municipality's centre (“estate”). Each hex lists the smallest areas first.",
    ).format(total=total, mapa=counts["mapa"], unidades=counts["unidades"], finca=counts["finca"])
    if missing:
        text += tr(" Sin zona: ", " No area: ") + join_texts([label(n["name"]) + ", " + n["note"] for n in missing], "; ") + "."
    if not_registered:
        text += tr(" Fuera del mapa por no estar ya registrados: ", " Left off the map as no longer registered: ") + \
            join_texts([label(n) for n in not_registered]) + "."
    return text
