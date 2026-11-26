"""Spain's great people ("Grandes personajes"): famous people born in Spain, at their birthplace (Wikidata, see
pipeline/sources/es/personajes.py for the categories and the fame rule).

* **Where**: the first of a person's birthplaces (by QID) that falls in today's Spain: inside a municipal outline
  (SIANE), or, outside every outline (the 1:3M coast is simplified), on a hex with no foreign land within one ring.
  The hex is the one at the birthplace, or the nearest Spanish land hex next to it (a port on a sea hex). A birthplace
  without coordinates takes those of the place it is in (P131). A birthplace that is a country or a region (Spain, a
  province, al-Andalus) has only a centroid and does not count. Who is left out is counted, by reason.
* **Lenses**: people per hex (log scale) and each hex's main category (the one with most people; a tie goes to the
  category first in priority order). Both name the hex's people in the tooltip, most famous first, from
  `personajes.json`, which the map loads when one of them opens (`names_from`), so lenses.json stays small.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..core.geo import Shape, ShapeIndex
from ..core.hexgrid import HexGrid
from ..core.store import load_interim_payload
from ..sources.es.personajes import KIND_IDS, KINDS
from .cities import nearest_land, ring_search
from .spain_named import shore_cell
from .texts_es import num
from .world import FOREIGN

REQUIRES = ["wikidata_personajes"]
FILE = "personajes"  # web/data file with the people (names_from)

# Category → (name in the legend, colour). The largest categories (sport, writers, saints, film, painters) get the
# hues furthest apart; all are light enough to read on the dark map.
STYLE = {
    "nobel": ("Premios Nobel", "#ffd700"), "monarchs": ("Reyes y reinas", "#7b1fa2"),
    "conquistadors": ("Conquistadores", "#d84315"), "explorers": ("Navegantes y exploradores", "#80deea"),
    "military": ("Militares", "#556b2f"), "rebels": ("Rebeldes y guerrilleros", "#ff8a80"),
    "religious": ("Santos y religiosos", "#f2e6c9"), "philosophers": ("Filósofos", "#ce93d8"),
    "scientists": ("Científicos", "#00b8d4"), "physicians": ("Médicos", "#26a69a"),
    "engineers": ("Inventores e ingenieros", "#90a4ae"), "architects": ("Arquitectos", "#8d6e63"),
    "artists": ("Pintores y escultores", "#ff4fa3"), "writers": ("Escritores", "#3f6fd8"),
    "film": ("Cine", "#e53935"), "singers": ("Cantantes", "#ffb300"),
    "musicians": ("Músicos y compositores", "#9575cd"),
    "merchants": ("Empresarios y comerciantes", "#c0ca33"), "athletes": ("Deportistas", "#7cb342"),
}
# The class that names a person's role (the first rule of its primary category it meets) → (masculine, feminine).
NOUNS = {
    "Q7191": ("premio Nobel", "premio Nobel"), "Q47170": ("premio Nobel", "premio Nobel"),
    "Q116": ("monarca", "monarca"), "Q719039": ("reina consorte", "reina consorte"),
    "Q126236": ("conquistador", "conquistadora"),
    "Q11900058": ("explorador", "exploradora"), "Q10669499": ("marino", "marina"), "Q201559": ("corsario", "corsaria"),
    "Q10729326": ("pirata", "pirata"), "Q849424": ("capitán de barco", "capitana de barco"),
    "Q254651": ("navegante", "navegante"), "Q12038843": ("navegante", "navegante"), "Q45199": ("marino", "marina"),
    "Q7194435": ("piloto mayor", "piloto mayor"),
    "Q189290": ("militar", "militar"), "Q1402561": ("militar", "militar"),
    "Q1125062": ("rebelde", "rebelde"), "Q3242115": ("revolucionario", "revolucionaria"),
    "Q15962734": ("amotinado", "amotinada"), "Q212948": ("guerrillero", "guerrillera"),
    "Q1397808": ("resistente", "resistente"), "Q16144978": ("bandolero", "bandolera"),
    "Q254508": ("proscrito", "proscrita"), "Q11242506": ("salteador de caminos", "salteadora de caminos"),
    "Q43115": ("santo", "santa"), "Q3464126": ("santo", "santa"), "Q123110154": ("santo", "santa"),
    "Q2369287": ("beato", "beata"), "Q19546": ("papa", "papisa"), "Q45722": ("cardenal", "cardenal"),
    "Q1234713": ("teólogo", "teóloga"), "Q219477": ("misionero", "misionera"), "Q12328016": ("místico", "mística"),
    "Q133485": ("rabino", "rabina"), "Q1664338": ("inquisidor", "inquisidora"), "Q2566598": ("religioso", "religiosa"),
    "Q4964182": ("filósofo", "filósofa"),
    "Q170790": ("matemático", "matemática"), "Q169470": ("físico", "física"), "Q593644": ("químico", "química"),
    "Q11063": ("astrónomo", "astrónoma"), "Q864503": ("biólogo", "bióloga"), "Q2374149": ("botánico", "botánica"),
    "Q350979": ("zoólogo", "zoóloga"), "Q520549": ("geólogo", "geóloga"), "Q18805": ("naturalista", "naturalista"),
    "Q901402": ("geógrafo", "geógrafa"), "Q1734662": ("cartógrafo", "cartógrafa"), "Q901": ("científico", "científica"),
    "Q39631": ("médico", "médica"),
    "Q205375": ("inventor", "inventora"), "Q81096": ("ingeniero", "ingeniera"),
    "Q42973": ("arquitecto", "arquitecta"),
    "Q1028181": ("pintor", "pintora"), "Q1281618": ("escultor", "escultora"),
    "Q36180": ("escritor", "escritora"),
    "Q2526255": ("cineasta", "cineasta"), "Q33999": ("actor", "actriz"),
    "Q177220": ("cantante", "cantante"),
    "Q36834": ("compositor", "compositora"), "Q1278335": ("instrumentista", "instrumentista"),
    "Q158852": ("director de orquesta", "directora de orquesta"), "Q639669": ("músico", "música"),
    "Q43845": ("empresario", "empresaria"), "Q131524": ("emprendedor", "emprendedora"),
    "Q215536": ("comerciante", "comerciante"), "Q806798": ("banquero", "banquera"),
    "Q6606110": ("industrial", "industrial"), "Q500251": ("armador", "armadora"),
    "Q2066131": ("deportista", "deportista"),
}
ROMAN = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"),
         (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
REASONS = {"abroad": "nacieron fuera de la España actual", "area": "solo tienen un país o una región como lugar de "
           "nacimiento", "no_coordinates": "tienen un lugar de nacimiento sin coordenadas"}


def roman(n: int) -> str:
    out = ""
    for v, s in ROMAN:
        while n >= v:
            out, n = out + s, n - v
    return out


def date_text(d: dict | None) -> str | None:
    """A Wikidata date as the map prints it: the year (BC years in the SPARQL answer count a year 0: -3 is 4 a. C.),
    'h. 1550' for a decade, 's. XVI' for a century; None for anything vaguer or missing."""
    if not d or (d["precision"] or 0) < 7:
        return None
    y = d["year"]
    bc = y <= 0
    n = 1 - y if bc else y
    if d["precision"] == 7:
        text = f"s. {roman((n - 1) // 100 + 1)}"
    else:
        text = f"h. {n}" if d["precision"] == 8 else str(n)
    return text + (" a. C." if bc else "")


def years(born: dict | None, died: dict | None) -> str | None:
    """'1881–1973', 'n. 1986' (no death date), 'm. 1550' (no birth date), or None."""
    b, d = date_text(born), date_text(died)
    if b and d:
        return f"{b}–{d}"
    if b:
        return f"n. {b}"
    return f"m. {d}" if d else None


def noun(person: dict) -> str:
    """What a person was: the word of Wikidata's description for its primary category ('poeta', 'tenista'), a Nobel
    with the trade the description names first ('médico, premio Nobel'), or else the noun of its role, in the
    person's gender."""
    if person["word"]:
        return person["word"]
    if person["primary"] == "nobel" and person["trade"]:
        return f"{person['trade']}, premio Nobel"
    return NOUNS[person["role"]][1 if person["female"] else 0]


def note(person: dict) -> str:
    """What the tooltip prints after the name: 'pintor, 1881–1973'."""
    noun_ = noun(person)
    span = years(person["born"], person["died"])
    return f"{noun_}, {span}" if span else noun_


class Placer:
    """Where a birthplace falls on the map: its hex, or None when it is outside today's Spain (see the module
    docstring)."""

    def __init__(self, proj, grid: HexGrid, owner: list[int], municipalities: list[dict]):
        self.proj, self.grid, self.owner = proj, grid, owner
        shapes = [Shape([[proj(lon, lat) for lon, lat in ring] for ring in m["rings"]]) for m in municipalities]
        self.index = ShapeIndex(shapes, cell_km=20)

    def cell(self, lon: float, lat: float) -> int | None:
        x, y = self.proj(lon, lat)
        cell = self.grid.cell_at(x, y)
        if cell < 0:
            return None
        inside = self.index.locate(x, y) >= 0
        if not inside and any(self.owner[c] == FOREIGN for _, c in ring_search(self.grid, cell, 1)):
            return None
        near = shore_cell(self.grid, self.owner, x, y)
        if near < 0 and inside:  # inside Spain, in a hex that a neighbour country owns
            near = nearest_land(self.grid, self.owner, cell, x, y, -1)
        return near if near >= 0 else None


def place(person: dict, placer: Placer) -> tuple[int, dict] | str:
    """(hex, birthplace) of the first birthplace in today's Spain, or why there is none: 'abroad' (coordinates, none
    in Spain), 'area' (only a country or a region), 'no_coordinates'."""
    usable = [b for b in person["birthplaces"] if b["coord"] and not b["area"]]
    for b in usable:
        cell = placer.cell(*b["coord"])
        if cell is not None:
            return cell, b
    if usable:
        return "abroad"
    return "area" if any(b["area"] for b in person["birthplaces"]) else "no_coordinates"


def dominant(kinds_in_hex: list[str]) -> int:
    """Index (in KINDS) of the category with most people in a hex; a tie goes to the first in priority order."""
    return min(range(len(KIND_IDS)), key=lambda i: (-kinds_in_hex.count(KIND_IDS[i]), i))


def hex_values(owner: list[int], placed) -> dict[str, list]:
    """The values of the two lenses from (hex, category id) of each person placed: people per land hex, and the
    index of its main category (None where nobody was born)."""
    in_hex: list[list[str] | None] = [[] if o >= 0 else None for o in owner]
    for cell, kind in placed:
        in_hex[cell].append(kind)
    return {"great_people": [None if v is None else len(v) for v in in_hex],
            "great_people_kind": [None if not v else dominant(v) for v in in_hex]}


def great_people(world: dict, proj, grid: HexGrid, municipalities: list[dict]) -> tuple[list[dict], dict]:
    """The two lenses and the people file."""
    payload = load_interim_payload("wikidata_personajes")
    data = payload["data"]
    owner = world["owner"]
    placer = Placer(proj, grid, owner, municipalities)
    people, left_out = [], {r: 0 for r in REASONS}
    unnamed = 0
    for p in data["people"]:
        if not p["name"]:
            unnamed += 1
            continue
        where = place(p, placer)
        if isinstance(where, str):
            left_out[where] += 1
            continue
        cell, b = where
        people.append({"name": p["name"], "note": note(p), "place": b["name"], "cell": cell, "kind": p["primary"],
                       "kinds": p["kinds"], "qid": p["qid"], "sitelinks": p["sitelinks"],
                       "description": p["description"]})
    values = hex_values(owner, ((p["cell"], p["kind"]) for p in people))
    per_kind = {k.id: sum(p["kind"] == k.id for p in people) for k in KINDS}
    print(f"    {len(people)} great people placed; left out: {left_out}, {unnamed} without a name; "
          f"{data['conquistadors_without_birthplace']} conquistadors without a birthplace in Wikidata")
    print("    " + ", ".join(f"{k} {n}" for k, n in per_kind.items()))

    out_total = sum(left_out.values())
    rule = ("Fama = número de enlaces a Wikipedias y otros proyectos de Wikimedia (sitelinks); cada categoría guarda a "
            "quien llega a su umbral: " + ", ".join(f"{STYLE[k.id][0].lower()} {k.min_sitelinks}" for k in KINDS
                                                   if k.min_sitelinks) + "; los conquistadores, todos.")
    common = (f"{num(len(people))} personas famosas nacidas en la España actual según Wikidata, en el hexágono de su "
              "lugar de nacimiento: premios Nobel, reyes y reinas, conquistadores, navegantes, militares, rebeldes, "
              "santos, filósofos, científicos, médicos, ingenieros, arquitectos, pintores, escritores, cine, "
              "cantantes, músicos, empresarios y deportistas. " + rule + " Quien está en varias categorías va en la "
              f"primera de esta lista. Fuera quedan {num(out_total)}: {num(left_out['abroad'])} "
              f"{REASONS['abroad']}, {num(left_out['area'])} {REASONS['area']} y {num(left_out['no_coordinates'])} "
              f"{REASONS['no_coordinates']}. Pasa el ratón por un hexágono para ver quién nació allí, de más a menos "
              "famoso. Lo editan voluntarios: refleja lo que cuenta Wikipedia, no un censo.")
    categories = [{"id": k.id, "name": STYLE[k.id][0], "color": STYLE[k.id][1]} for k in KINDS]
    meta = {"group": "great_people", "higher_is": "neutral", "source": "wikidata_personajes", "names_from": FILE}
    lenses = [
        {"id": "great_people", "name": "Grandes personajes", "icon": "l-great-people", "emoji": "⭐",
         "unit": "personajes", "format": "int", "scale": "log",
         "ramp": ["#1c1530", "#3b2763", "#6a3d8f", "#a85a9e", "#e08a8a", "#ffd58a"], **meta,
         "description": "Cuántos grandes personajes nacieron en cada hexágono. " + common,
         "values": values["great_people"]},
        {"id": "great_people_kind", "name": "Personajes por oficio", "icon": "l-great-people-kind", "emoji": "🎭",
         "unit": "categoría con más personajes", "format": "category", "scale": "linear",
         "domain": [0, len(categories) - 1], "categories": categories, "ramp": [c["color"] for c in categories],
         "null_label": "Nadie", **meta,
         "description": "La categoría con más personajes nacidos en cada hexágono (un empate, para la primera de la "
         "lista); pulsa una para ver solo esa. " + common,
         "values": values["great_people_kind"]},
    ]
    doc = {
        "vintage": payload["vintage"],
        "categories": categories,
        "people": [{k: p[k] for k in ("name", "note", "place", "cell")}
                   | {"kind": KIND_IDS.index(p["kind"]), "qid": p["qid"]} for p in people],
    }
    return lenses, doc


def check(web_dir) -> list[tuple[str, str]]:
    """personajes.json against the lenses that name from it: every person on a land hex, and the lenses' counts and
    main categories those of the people file. Nothing to check on a map without those lenses."""
    web_dir = Path(web_dir)
    lenses = json.loads((web_dir / "lenses.json").read_text())["lenses"]
    named = {l["id"]: l for l in lenses if l.get("names_from") == FILE}
    if not named:
        return []
    path = web_dir / f"{FILE}.json"
    if not path.exists():
        return [("FAIL", f"{FILE}.json: missing, and {sorted(named)} name from it")]
    doc = json.loads(path.read_text())
    owner = json.loads((web_dir / "world.json").read_text())["owner"]
    people = doc["people"]
    off = [p["name"] for p in people if not (0 <= p["cell"] < len(owner) and owner[p["cell"]] >= 0)]
    if off:
        return [("FAIL", f"{FILE}.json: {len(off)} people off Spanish land ({', '.join(off[:5])})")]
    want = hex_values(owner, ((p["cell"], doc["categories"][p["kind"]]["id"]) for p in people))
    out = [("FAIL", f"lens {i}: values differ from {FILE}.json") for i, v in want.items() if named[i]["values"] != v]
    return out or [("PASS", f"{FILE}.json: {len(people)} people on land hexes, matching {sorted(named)}")]
