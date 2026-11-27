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
from ..core.lang import Text, tr
from ..core.store import load_interim_payload
from ..sources.es.personajes import GUANARTEME, KIND_IDS, KINDS, MENCEY
from .cities import nearest_land, ring_search
from .spain_named import shore_cell
from .world import FOREIGN

REQUIRES = ["wikidata_personajes"]
FILE = "personajes"  # web/data file with the people (names_from)

# Category → (name in the legend, colour). The largest categories (sport, writers, saints, film, painters) get the
# hues furthest apart; all are light enough to read on the dark map.
STYLE = {
    "nobel": (tr("Premios Nobel", "Nobel laureates"), "#ffd700"),
    "monarchs": (tr("Reyes y reinas", "Kings and queens"), "#7b1fa2"),
    "conquistadors": (tr("Conquistadores", "Conquistadors"), "#d84315"),
    "explorers": (tr("Navegantes y exploradores", "Navigators and explorers"), "#80deea"),
    "military": (tr("Militares", "Soldiers"), "#556b2f"),
    "rebels": (tr("Rebeldes y guerrilleros", "Rebels and guerrillas"), "#ff8a80"),
    "religious": (tr("Santos y religiosos", "Saints and clergy"), "#f2e6c9"),
    "philosophers": (tr("Filósofos", "Philosophers"), "#ce93d8"),
    "scientists": (tr("Científicos", "Scientists"), "#00b8d4"), "physicians": (tr("Médicos", "Physicians"), "#26a69a"),
    "engineers": (tr("Inventores e ingenieros", "Inventors and engineers"), "#90a4ae"),
    "architects": (tr("Arquitectos", "Architects"), "#8d6e63"),
    "artists": (tr("Pintores y escultores", "Painters and sculptors"), "#ff4fa3"),
    "writers": (tr("Escritores", "Writers"), "#3f6fd8"), "film": (tr("Cine", "Film"), "#e53935"),
    "singers": (tr("Cantantes", "Singers"), "#ffb300"),
    "musicians": (tr("Músicos y compositores", "Musicians and composers"), "#9575cd"),
    "merchants": (tr("Empresarios y comerciantes", "Business people and merchants"), "#c0ca33"),
    "athletes": (tr("Deportistas", "Athletes"), "#7cb342"),
}
# The class that names a person's role (the first rule of its primary category it meets) → (masculine, feminine).
NOUNS = {
    "Q7191": ("premio Nobel", "premio Nobel"), "Q47170": ("premio Nobel", "premio Nobel"),
    "Q2724892": ("mencey", "mencey"), "Q3323725": ("guanarteme", "guanarteme"), "Q116": ("monarca", "monarca"), "Q719039": ("reina consorte", "reina consorte"),
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
# The English of every Spanish noun a note can hold: the nouns above and the trade words of Wikidata's descriptions
# (sources/es/personajes.py WORDS), masculine and feminine alike.
NOUN_EN = {
    "premio Nobel": "Nobel laureate", "mencey": "mencey", "guanarteme": "guanarteme", "monarca": "monarch",
    "reina consorte": "queen consort", "conquistador": "conquistador", "conquistadora": "conquistador",
    "explorador": "explorer", "exploradora": "explorer", "marino": "sailor", "marina": "sailor",
    "corsario": "privateer", "corsaria": "privateer", "pirata": "pirate", "capitán de barco": "ship's captain",
    "capitana de barco": "ship's captain", "navegante": "navigator", "navegador": "navigator", "navegadora": "navigator",
    "piloto mayor": "pilot major", "almirante": "admiral", "militar": "soldier", "caudillo": "warlord",
    "guerrero": "warrior", "guerrera": "warrior", "soldado": "soldier", "rebelde": "rebel",
    "revolucionario": "revolutionary", "revolucionaria": "revolutionary", "amotinado": "mutineer", "amotinada": "mutineer",
    "guerrillero": "guerrilla", "guerrillera": "guerrilla", "maqui": "maquis guerrilla", "resistente": "resistance fighter",
    "bandolero": "bandit", "bandolera": "bandit", "proscrito": "outlaw", "proscrita": "outlaw",
    "salteador de caminos": "highwayman", "salteadora de caminos": "highwaywoman", "santo": "saint", "santa": "saint",
    "beato": "blessed", "beata": "blessed", "papa": "pope", "papisa": "pope", "cardenal": "cardinal",
    "teólogo": "theologian", "teóloga": "theologian", "misionero": "missionary", "misionera": "missionary",
    "místico": "mystic", "mística": "mystic", "religioso": "member of a religious order",
    "religiosa": "member of a religious order", "monja": "nun", "fraile": "friar", "sacerdote": "priest",
    "presbítero": "priest", "obispo": "bishop", "arzobispo": "archbishop", "rabino": "rabbi", "rabina": "rabbi",
    "jesuita": "Jesuit", "franciscano": "Franciscan", "franciscana": "Franciscan", "dominico": "Dominican",
    "inquisidor": "inquisitor", "inquisidora": "inquisitor", "abad": "abbot", "abadesa": "abbess", "monje": "monk",
    "eclesiástico": "churchman", "predicador": "preacher", "filósofo": "philosopher", "filósofa": "philosopher",
    "pensador": "thinker", "pensadora": "thinker", "científico": "scientist", "científica": "scientist",
    "matemático": "mathematician", "matemática": "mathematician", "físico": "physicist", "física": "physicist",
    "químico": "chemist", "química": "chemist", "astrónomo": "astronomer", "astrónoma": "astronomer",
    "biólogo": "biologist", "bióloga": "biologist", "botánico": "botanist", "botánica": "botanist",
    "zoólogo": "zoologist", "zoóloga": "zoologist", "geólogo": "geologist", "geóloga": "geologist",
    "naturalista": "naturalist", "geógrafo": "geographer", "geógrafa": "geographer", "cartógrafo": "cartographer",
    "cartógrafa": "cartographer", "bioquímico": "biochemist", "bioquímica": "biochemist", "investigador": "researcher",
    "investigadora": "researcher", "médico": "physician", "médica": "physician", "cirujano": "surgeon",
    "cirujana": "surgeon", "psiquiatra": "psychiatrist", "neurólogo": "neurologist", "neuróloga": "neurologist",
    "ingeniero": "engineer", "ingeniera": "engineer", "inventor": "inventor", "inventora": "inventor",
    "arquitecto": "architect", "arquitecta": "architect", "pintor": "painter", "pintora": "painter",
    "escultor": "sculptor", "escultora": "sculptor", "escritor": "writer", "escritora": "writer", "poeta": "poet",
    "poetisa": "poet", "novelista": "novelist", "dramaturgo": "playwright", "dramaturga": "playwright",
    "ensayista": "essayist", "cuentista": "short-story writer", "actor": "actor", "actriz": "actress",
    "cineasta": "filmmaker", "director de cine": "film director", "directora de cine": "film director",
    "cantante": "singer", "cantaor": "flamenco singer", "cantaora": "flamenco singer", "cantautor": "singer-songwriter",
    "cantautora": "singer-songwriter", "soprano": "soprano", "tenor": "tenor", "barítono": "baritone",
    "mezzosoprano": "mezzo-soprano", "tonadillera": "tonadilla singer", "cupletista": "cuplé singer", "rapero": "rapper",
    "rapera": "rapper", "compositor": "composer", "compositora": "composer", "instrumentista": "instrumentalist",
    "director de orquesta": "conductor", "directora de orquesta": "conductor", "músico": "musician",
    "música": "musician", "pianista": "pianist", "guitarrista": "guitarist", "violinista": "violinist",
    "violonchelista": "cellist", "organista": "organist", "arpista": "harpist", "empresario": "businessman",
    "empresaria": "businesswoman", "emprendedor": "entrepreneur", "emprendedora": "entrepreneur",
    "comerciante": "merchant", "banquero": "banker", "banquera": "banker", "mercader": "merchant",
    "industrial": "industrialist", "armador": "shipowner", "armadora": "shipowner", "financiero": "financier",
    "deportista": "athlete", "futbolista": "footballer", "ciclista": "cyclist", "tenista": "tennis player",
    "baloncestista": "basketball player", "atleta": "athlete", "nadador": "swimmer", "nadadora": "swimmer",
    "jugador": "player", "jugadora": "player", "torero": "bullfighter", "boxeador": "boxer", "golfista": "golfer",
    "balonmanista": "handball player", "alpinista": "mountaineer", "esquiador": "skier", "esquiadora": "skier",
    "regatista": "sailor", "waterpolista": "water polo player", "piragüista": "canoeist", "entrenador": "coach",
    "rey": "king", "reina": "queen", "emperador": "emperor", "emperatriz": "empress", "califa": "caliph",
    "emir": "emir", "sultán": "sultan",
}
ROMAN = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"),
         (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
REASONS = {"abroad": tr("nacieron fuera de la España actual", "were born outside today's Spain"),
           "area": tr("solo tienen un país o una región como lugar de nacimiento",
                      "have only a country or a region as their birthplace"),
           "no_coordinates": tr("tienen un lugar de nacimiento sin coordenadas", "have a birthplace without coordinates")}
# Date words of a note: Spanish, English.
DATE_WORDS = {"century": ("s. {}", "{} century"), "circa": ("h. {}", "c. {}"), "bc": (" a. C.", " BC"),
              "born": ("n. {}", "b. {}"), "died": ("m. {}", "d. {}")}


def roman(n: int) -> str:
    out = ""
    for v, s in ROMAN:
        while n >= v:
            out, n = out + s, n - v
    return out


def ordinal(n: int) -> str:
    """1st, 2nd, 3rd, 4th… 11th, 12th, 13th, 21st."""
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def date_text(d: dict | None, lang: str = "es") -> str | None:
    """A Wikidata date as the map prints it: the year (BC years in the SPARQL answer count a year 0: -3 is 4 a. C.),
    'h. 1550' for a decade, 's. XVI' for a century ('c. 1550', '16th century' in English); None for anything vaguer or
    missing."""
    if not d or (d["precision"] or 0) < 7:
        return None
    k = lang == "en"
    y = d["year"]
    bc = y <= 0
    n = 1 - y if bc else y
    if d["precision"] == 7:
        c = (n - 1) // 100 + 1
        text = DATE_WORDS["century"][k].format(ordinal(c) if k else roman(c))
    else:
        text = DATE_WORDS["circa"][k].format(n) if d["precision"] == 8 else str(n)
    return text + (DATE_WORDS["bc"][k] if bc else "")


def years(born: dict | None, died: dict | None, lang: str = "es") -> str | None:
    """'1881–1973', 'n. 1986' (no death date), 'm. 1550' (no birth date), or None; 'b. 1986', 'd. 1550' in English."""
    k = lang == "en"
    b, d = date_text(born, lang), date_text(died, lang)
    if b and d:
        return f"{b}–{d}"
    if b:
        return DATE_WORDS["born"][k].format(b)
    return DATE_WORDS["died"][k].format(d) if d else None


OWN_TITLES = {MENCEY, GUANARTEME}  # titles that name the role better than a description's 'rey'


def noun(person: dict, lang: str = "es") -> str:
    """What a person was: the word of Wikidata's description for its primary category ('poeta', 'tenista'), a Nobel
    with the trade the description names first ('médico, premio Nobel'), or else the noun of its role, in the
    person's gender; in English, the English of that word (NOUN_EN)."""
    en = (lambda w: NOUN_EN[w]) if lang == "en" else (lambda w: w)
    if person["word"] and person["role"] not in OWN_TITLES:
        return en(person["word"])
    if person["primary"] == "nobel" and person["trade"]:
        return f"{en(person['trade'])}, {en('premio Nobel')}"
    return en(NOUNS[person["role"]][1 if person["female"] else 0])


def note(person: dict) -> Text:
    """What the tooltip prints after the name: 'pintor, 1881–1973' ('painter, 1881–1973')."""
    def one(lang: str) -> str:
        noun_, span = noun(person, lang), years(person["born"], person["died"], lang)
        return f"{noun_}, {span}" if span else noun_

    return tr(one("es"), one("en"))


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
    thresholds = {lang: ", ".join(f"{STYLE[k.id][0][lang].lower()} {k.min_sitelinks}" for k in KINDS if k.min_sitelinks)
                  for lang in ("es", "en")}
    common = tr(
        "{people} personas famosas nacidas en la España actual según Wikidata, en el hexágono de su lugar de nacimiento: "
        "premios Nobel, reyes y reinas, conquistadores, navegantes, militares, rebeldes, santos, filósofos, científicos, "
        "médicos, ingenieros, arquitectos, pintores, escritores, cine, cantantes, músicos, empresarios y deportistas. "
        "Fama = número de enlaces a Wikipedias y otros proyectos de Wikimedia (sitelinks); cada categoría guarda a "
        "quien llega a su umbral: {thresholds}; los conquistadores, todos. Quien está en varias categorías va en la "
        "primera de esta lista. Fuera quedan {out}: {abroad} {r_abroad}, {area} {r_area} y {nocoord} {r_nocoord}. Pasa "
        "el ratón por un hexágono para ver quién nació allí, de más a menos famoso. Lo editan voluntarios: refleja lo "
        "que cuenta Wikipedia, no un censo.",
        "{people} famous people born in today's Spain according to Wikidata, on the hex of their birthplace: Nobel "
        "laureates, kings and queens, conquistadors, navigators, soldiers, rebels, saints, philosophers, scientists, "
        "physicians, engineers, architects, painters, writers, film, singers, musicians, business people and athletes. "
        "Fame = the number of links to Wikipedias and other Wikimedia projects (sitelinks); each category keeps those "
        "who reach its threshold: {thresholds}; conquistadors, all of them. Someone in several categories goes in the "
        "first of this list. Left out: {out}, of whom {abroad} {r_abroad}, {area} {r_area} and {nocoord} {r_nocoord}. "
        "Hover a hex to see who was born there, most famous first. Volunteer-edited: it reflects what Wikipedia covers, "
        "not a census.",
    ).format(people=len(people), thresholds=Text(**thresholds), out=out_total, abroad=left_out["abroad"],
             r_abroad=REASONS["abroad"], area=left_out["area"], r_area=REASONS["area"],
             nocoord=left_out["no_coordinates"], r_nocoord=REASONS["no_coordinates"])
    categories = [{"id": k.id, "name": STYLE[k.id][0], "color": STYLE[k.id][1]} for k in KINDS]
    meta = {"group": "great_people", "higher_is": "neutral", "source": "wikidata_personajes", "names_from": FILE}
    lenses = [
        {"id": "great_people", "name": tr("Grandes personajes", "Great people"), "icon": "l-great-people", "emoji": "⭐",
         "unit": tr("personajes", "people"), "format": "int", "scale": "log",
         "ramp": ["#1c1530", "#3b2763", "#6a3d8f", "#a85a9e", "#e08a8a", "#ffd58a"], **meta,
         "description": tr("Cuántos grandes personajes nacieron en cada hexágono. ",
                           "How many great people were born in each hex. ") + common,
         "values": values["great_people"]},
        {"id": "great_people_kind", "name": tr("Personajes por oficio", "Great people by trade"),
         "icon": "l-great-people-kind", "emoji": "🎭",
         "unit": tr("categoría con más personajes", "category with the most people"), "format": "category",
         "scale": "linear", "domain": [0, len(categories) - 1], "categories": categories,
         "ramp": [c["color"] for c in categories], "null_label": tr("Nadie", "Nobody"), **meta,
         "description": tr("La categoría con más personajes nacidos en cada hexágono (un empate, para la primera de la "
                           "lista); pulsa una para ver solo esa. ",
                           "The category with the most people born in each hex (a tie goes to the first in the list); "
                           "click one to show only that one. ") + common,
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
