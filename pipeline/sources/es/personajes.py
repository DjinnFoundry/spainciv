"""Great people born in Spain, from Wikidata (CC0): the map's take on Civilization's Great People.

A person (Q5) counts when Wikidata gives a place of birth (P19) whose country (P17) is Spain or one of the polities
that Wikidata names as the only country of a historical place in the peninsula (Calagurris in Ancient Rome, a town in
the Crown of Castile…); the builder keeps those whose birthplace falls in today's Spain. Fame is the item's sitelink
count (how many Wikipedias and other Wikimedia projects have a page on the person).

Each person gets every category (KINDS, in priority order) whose classes it matches: occupations (P106), positions
held (P39), awards (P166) or canonization status (P411), each class with or without its subclasses (P279*). A
category keeps the people with at least its `min_sitelinks`; the person's primary category is chosen among those
(primary(): an office, a prize, a conquest or a sainthood first, then the first trade Wikidata's description of the
person names, then the category that counts most of its occupations), and the others stay listed.
Conquistadors count whatever their fame.

The answers are cached like any download, in three steps that keep every query small enough for the endpoint's
60-second limit: the people born in Spain (split by sitelink count) with their occupations and their positions,
awards and canonization status; the class trees; and the labels, descriptions, dates and birthplaces of the people
the rules keep, in batches.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.parse
from dataclasses import dataclass

from ...core.fetch import read_manifest
from ...core.source import Source, SourceInfo
from .wikidata import ENDPOINT, HEADERS, LANGUAGES, point, qid, value

SPAIN = "Q29"
# The only country (P17) Wikidata gives some historical birthplaces in the peninsula: Ancient Rome, Roman Empire and
# Republic, Western Roman Empire, Hispania, al-Andalus, the Emirate and the Caliphate of Córdoba, the Visigothic
# Kingdom and its Kingdom of Toledo, the Crowns of Castile and Aragon, the kingdoms of Castile, Aragon, León, Navarre,
# Pamplona, Asturias, Galicia, Majorca and Valencia, the Principality of Catalonia, the Emirate of Granada, the
# Spanish Empire, the Almohads and the Almoravids, Francoist Spain and the Second Republic (QIDs checked with the
# Wikidata API). Places abroad with these countries (Rome, Lisbon) are dropped by the builder's land check.
POLITIES = ("Q1747689", "Q2277", "Q17167", "Q42834", "Q186513", "Q123559", "Q1337854", "Q171740", "Q126936",
            "Q2940142", "Q217196", "Q204920", "Q179293", "Q199442", "Q175276", "Q200262", "Q3446210", "Q231392",
            "Q303421", "Q836676", "Q142417", "Q15581", "Q238445", "Q80702", "Q199688", "Q75613", "Q13474305",
            "Q178038")
FLOOR = 5  # sitelinks: below this, a person is fetched only as a conquistador
CONQUISTADOR = "Q126236"  # (Q201559, sometimes given for it, is "privateer")
FEMALE = {"Q6581072", "Q1052281"}  # female, trans woman (P21): the category noun goes in the feminine
# A birthplace of these types is a country or a region, not a place: its coordinates are a centroid.
AREAS = {"Q6256", "Q3624078", "Q3024240", "Q10742", "Q162620", "Q1620908", "Q82794"}
BATCH = 250  # items per VALUES query
PAUSE = 10  # seconds before each new query (see WikidataPersonajes._query)


def qid_number(q: str) -> int:
    """The number of a QID ('Q29' → 29): the sort key for QID order."""
    return int(q[1:])


def _items(qids) -> str:
    """QIDs as SPARQL items: 'wd:Q1 wd:Q2'."""
    return " ".join("wd:" + q for q in qids)


@dataclass(frozen=True)
class Rule:
    """A class that puts a person in a category: a value of `prop` (P106 occupation, P39 position, P166 award, P411
    canonization status), with all its subclasses (P279*) when `deep`. A `decisive` class (an office, a prize, a
    sainthood, a conquest) makes its category the primary one, before any trade (see classify)."""
    prop: str
    cls: str
    deep: bool = True
    decisive: bool = False


@dataclass(frozen=True)
class Kind:
    """A category of great people: its rules, in the order that names a person's role (the first rule a person meets:
    Picasso is a painter before a sculptor), its fame threshold, and the classes of its trees that do not belong."""
    id: str
    min_sitelinks: int
    rules: tuple[Rule, ...]
    exclude: frozenset[str] = frozenset()


def occ(*qids: str, deep: bool = True, decisive: bool = False) -> tuple[Rule, ...]:
    return tuple(Rule("P106", q, deep, decisive) for q in qids)


# Priority order (see classify: it orders the offices and breaks ties): offices and status (a Nobel, a crown, a
# conquest, a sainthood) before trades, the rarer trades before the common ones, and sport last.
KINDS = (
    # The Nobel Prizes (Q7191 and its five prizes) and the economics prize in memory of Nobel.
    Kind("nobel", FLOOR, (Rule("P166", "Q7191", decisive=True), Rule("P166", "Q47170", False, True))),
    # Monarchs (Q116) with every crown below it, and queens consort (Q719039). Out: the bishops of Urgell and the
    # co-princes of Andorra, popes, the judges of Sardinia, the Lord of Biscay, Fürsten, prince-electors and the bishop
    # of Sion, which Wikidata files under monarch.
    Kind("monarchs", FLOOR, (Rule("P39", "Q116", decisive=True), Rule("P39", "Q719039", decisive=True)),
         frozenset({"Q19808790", "Q19808845", "Q49967564", "Q19546", "Q3769128", "Q2279624", "Q17077113", "Q18244",
                    "Q22722", "Q23034734"})),
    Kind("conquistadors", 0, occ(CONQUISTADOR, decisive=True)),
    # Explorers, naval officers, privateers, pirates, sea captains; navigators, seafarers, sailors and the pilot major
    # without their subclasses (those of sailor are sport sailors, rowers and canoeists).
    Kind("explorers", 8, occ("Q11900058", "Q10669499", "Q201559", "Q10729326", "Q849424")
         + occ("Q254651", "Q12038843", "Q45199", "Q7194435", deep=False)),
    Kind("military", 10, occ("Q189290", "Q1402561")),  # military officers and military leaders
    # Rebels, revolutionaries, mutineers, guerrilla fighters, resistance fighters, bandits, outlaws, highwaymen.
    Kind("rebels", FLOOR, occ("Q1125062", "Q3242115", "Q15962734", "Q212948", "Q1397808", "Q16144978", "Q254508",
                              "Q11242506")),
    # Saints and blessed (P411: saint, Catholic saint, canonized saint, blessed), popes and cardinals (P39),
    # theologians, missionaries, mystics, rabbis, inquisitors and members of religious orders. Priests and bishops as
    # such are not in: there are thousands.
    Kind("religious", 8, tuple(Rule("P411", q, False, True) for q in ("Q43115", "Q3464126", "Q123110154", "Q2369287"))
         + (Rule("P39", "Q19546", decisive=True), Rule("P39", "Q45722", decisive=True))
         + occ("Q1234713", "Q219477", "Q12328016", "Q133485", "Q1664338", "Q2566598")),
    Kind("philosophers", 8, occ("Q4964182")),
    # Mathematicians, physicists, chemists, astronomers, biologists, botanists, zoologists, geologists, naturalists,
    # geographers and cartographers; "scientist" (Q901) without its tree, which takes in every historian and university
    # teacher.
    Kind("scientists", 8, occ("Q170790", "Q169470", "Q593644", "Q11063", "Q864503", "Q2374149", "Q350979", "Q520549",
                              "Q18805", "Q901402", "Q1734662") + occ("Q901", deep=False)),
    Kind("physicians", FLOOR, occ("Q39631")),
    Kind("engineers", FLOOR, occ("Q205375", "Q81096")),  # inventors and engineers
    Kind("architects", FLOOR, occ("Q42973")),
    Kind("artists", 8, occ("Q1028181", "Q1281618")),  # painters and sculptors
    Kind("writers", 10, occ("Q36180")),
    Kind("film", 15, occ("Q2526255", "Q33999")),  # film directors and actors
    Kind("singers", 10, occ("Q177220")),
    # Composers, instrumentalists and conductors; "musician" without its tree, which holds every singer.
    Kind("musicians", 10, occ("Q36834", "Q1278335", "Q158852") + occ("Q639669", deep=False)),
    # Businesspeople, entrepreneurs, merchants, bankers, industrialists and ship-owners, without their trees: that of
    # businessperson takes in film producers, editors and football referees.
    Kind("merchants", 8, occ("Q43845", "Q131524", "Q215536", "Q806798", "Q6606110", "Q500251", deep=False)),
    Kind("athletes", 20, occ("Q2066131")),
)
KIND_IDS = [k.id for k in KINDS]
BY_ID = {k.id: k for k in KINDS}

_HUMAN = "?p wdt:P31 wd:Q5."
# The people of each fetch step: born in Spain, split by sitelink count; born where Wikidata gives only a historical
# country; and the conquistadors, whatever their fame and birthplace's country.
SHARDS = {
    "spain_5": f"?b wdt:P17 wd:{SPAIN}. ?p wdt:P19 ?b; wikibase:sitelinks ?s. FILTER(?s >= 5 && ?s < 8) {_HUMAN}",
    "spain_8": f"?b wdt:P17 wd:{SPAIN}. ?p wdt:P19 ?b; wikibase:sitelinks ?s. FILTER(?s >= 8 && ?s < 15) {_HUMAN}",
    "spain_15": f"?b wdt:P17 wd:{SPAIN}. ?p wdt:P19 ?b; wikibase:sitelinks ?s. FILTER(?s >= 15) {_HUMAN}",
    "historic": "VALUES ?c { %s } ?b wdt:P17 ?c. FILTER NOT EXISTS { ?b wdt:P17 wd:%s } ?p wdt:P19 ?b; "
    "wikibase:sitelinks ?s. FILTER(?s >= %d) %s" % (_items(POLITIES), SPAIN, FLOOR, _HUMAN),
    "conquistadors": 'hint:Query hint:optimizer "None". ?o wdt:P279* wd:%s. ?p wdt:P106 ?o; wdt:P19 ?b; '
    "wikibase:sitelinks ?s. VALUES ?c { %s } ?b wdt:P17 ?c. %s" % (
        CONQUISTADOR, _items((SPAIN, *POLITIES)), _HUMAN),
}
# Occupations; and positions, awards and canonization status (one row per value; a person without any still has its
# sitelinks row in the first).
OCCUPATIONS = "SELECT DISTINCT ?p ?s ?x WHERE { %s OPTIONAL { ?p wdt:P106 ?x. } }"
HONOURS = ("SELECT DISTINCT ?p ?k ?x WHERE { %s { ?p wdt:P39 ?x. BIND('P39' AS ?k) } UNION { ?p wdt:P166 ?x. "
           "BIND('P166' AS ?k) } UNION { ?p wdt:P411 ?x. BIND('P411' AS ?k) } }")
TREE = "SELECT DISTINCT ?x WHERE { ?x wdt:P279* wd:%s. }"  # a class and all its subclasses
# Conquistadors Wikidata knows without a place of birth: counted, not mapped.
UNBORN = (f"SELECT (COUNT(DISTINCT ?p) AS ?n) WHERE {{ ?o wdt:P279* wd:{CONQUISTADOR}. ?p wdt:P106 ?o. {_HUMAN} "
          "FILTER NOT EXISTS { ?p wdt:P19 ?b. } }")
# Labels, descriptions, sex and dates (with their precision and rank) of a batch of people, and their birthplaces:
# label, coordinates, types and, for one without coordinates, the place it is in (P131) with its coordinates and
# types.
DETAILS = """SELECT ?p ?pLabel ?pDescription ?g ?born ?bp ?br ?died ?dp ?dr
  ?b ?bLabel ?coord ?t ?up ?upcoord ?ut WHERE {
  VALUES ?p { %s }
  OPTIONAL { ?p wdt:P21 ?g. }
  OPTIONAL { ?p p:P569 ?bs. ?bs wikibase:rank ?br; psv:P569 [ wikibase:timeValue ?born; wikibase:timePrecision ?bp ].
             FILTER(?br != wikibase:DeprecatedRank) }
  OPTIONAL { ?p p:P570 ?ds. ?ds wikibase:rank ?dr; psv:P570 [ wikibase:timeValue ?died; wikibase:timePrecision ?dp ].
             FILTER(?dr != wikibase:DeprecatedRank) }
  OPTIONAL { ?p wdt:P19 ?b.
             OPTIONAL { ?b wdt:P625 ?coord. }
             OPTIONAL { ?b wdt:P31 ?t. }
             OPTIONAL { FILTER NOT EXISTS { ?b wdt:P625 ?any. } ?b wdt:P131 ?up. ?up wdt:P625 ?upcoord.
                        OPTIONAL { ?up wdt:P31 ?ut. } } }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "%s". }
}"""


def tree_file(cls: str) -> str:
    return f"classes/{cls}.json"


DEEP = sorted({r.cls for k in KINDS for r in k.rules if r.deep}, key=qid_number)  # one tree query each


def hits(kind: Kind, values: dict[str, set[str]], trees: dict[str, set[str]]) -> dict[Rule, set[str]]:
    """The rules of `kind` that a person's property values meet, each with the values it counts (`trees`: class → it
    and its subclasses), in rule order."""
    out = {}
    for r in kind.rules:
        found = values.get(r.prop, set()) & ((trees[r.cls] if r.deep else {r.cls}) - kind.exclude)
        if found:
            out[r] = found
    return out


def classify(values: dict[str, set[str]], sitelinks: int, trees: dict[str, set[str]]) -> dict | None:
    """What the rules say of a person: every category it meets (`kinds`, in priority order); those whose fame
    threshold its sitelinks meet (`kept`), each with its role (the class of the first rule met in it, which names it:
    Picasso is a painter before a sculptor) and how many of the person's values it counts; and which of them it meets
    through a decisive rule. None when no category keeps the person."""
    met = {k.id: h for k in KINDS if (h := hits(k, values, trees))}
    kept = [k for k in met if sitelinks >= BY_ID[k].min_sitelinks]
    if not kept:
        return None
    return {"sitelinks": sitelinks, "kinds": list(met), "kept": kept,
            "roles": {k: next(iter(met[k])).cls for k in kept},
            "counts": {k: len(set().union(*met[k].values())) for k in kept},
            "decisive": [k for k in kept if any(r.decisive for r in met[k])]}


# Words of a Wikidata description (in Spanish; Galician and Catalan share most of them) that name a category's trade.
# Phrases of several words go after a |, and are matched before their first word.
WORDS = {
    "monarchs": "rey reina monarca emperador emperatriz califa emir sultán",
    "conquistadors": "conquistador conquistadora",
    "explorers": "explorador exploradora navegante navegador navegadora marino marina corsario corsaria pirata "
    "almirante",
    "military": "militar caudillo guerrero guerrera soldado",
    "rebels": "rebelde revolucionario revolucionaria guerrillero guerrillera bandolero bandolera amotinado maqui",
    "religious": "santo santa beato beata papa cardenal teólogo teóloga misionero misionera místico mística religioso "
    "religiosa monja fraile sacerdote presbítero obispo arzobispo rabino jesuita franciscano franciscana dominico "
    "inquisidor abad abadesa monje eclesiástico predicador",
    "philosophers": "filósofo filósofa pensador pensadora",
    "scientists": "científico científica matemático matemática físico física químico química astrónomo astrónoma "
    "biólogo bióloga botánico botánica zoólogo zoóloga geólogo geóloga naturalista geógrafo geógrafa cartógrafo "
    "cartógrafa bioquímico bioquímica investigador investigadora",
    "physicians": "médico médica cirujano cirujana psiquiatra neurólogo neuróloga",
    "engineers": "ingeniero ingeniera inventor inventora",
    "architects": "arquitecto arquitecta",
    "artists": "pintor pintora escultor escultora",  # not "artista", which singers and actors also get
    "writers": "escritor escritora poeta poetisa novelista dramaturgo dramaturga ensayista cuentista",
    "film": "actor actriz cineasta|director de cine|directora de cine",
    "singers": "cantante cantaor cantaora cantautor cantautora soprano tenor barítono mezzosoprano tonadillera "
    "cupletista rapero rapera",
    "musicians": "compositor compositora músico música pianista guitarrista violinista violonchelista organista "
    "arpista|director de orquesta|directora de orquesta",
    "merchants": "empresario empresaria comerciante banquero banquera mercader emprendedor emprendedora armador "
    "financiero",
    "athletes": "deportista futbolista ciclista tenista baloncestista atleta nadador nadadora jugador jugadora "
    "torero boxeador golfista balonmanista alpinista esquiador esquiadora regatista waterpolista piragüista "
    "entrenador",
}
TERMS = {tuple(t.split()): k for k, spec in WORDS.items()
         for t in spec.split("|")[0].split() + spec.split("|")[1:]}  # words, then the phrases after a |
LONGEST = max(len(t) for t in TERMS)


def described(description: str | None, kinds: list[str]) -> list[tuple[str, str]]:
    """(category, words) for each trade the description names, in order, among `kinds`."""
    tokens = re.findall(r"[^\W\d_]+", (description or "").lower())
    out, i = [], 0
    while i < len(tokens):
        for n in range(LONGEST, 0, -1):
            k = TERMS.get(tuple(tokens[i:i + n]))
            if k:
                if k in kinds:
                    out.append((k, " ".join(tokens[i:i + n])))
                i += n - 1
                break
        i += 1
    return out


def primary(c: dict, description: str | None) -> dict:
    """A person's primary category, among those that keep it (classify): the first one met through a decisive rule
    (a Nobel, a crown, a conquest, a sainthood, the papacy); otherwise the first trade the description names
    (Dalí: "artista, pintor, escultor… y escritor"; Julio Iglesias: "cantante"); otherwise the one that counts most of
    the person's values (a tie goes to the first in priority order). With it, its role, the description's word for
    it (`word`, or None), and the first trade the description names at all (`trade`: a Nobel's trade)."""
    found = described(description, c["kept"])
    if c["decisive"]:
        k = c["decisive"][0]
    elif found:
        k = found[0][0]
    else:
        k = max(c["kept"], key=lambda k: (c["counts"][k], -KIND_IDS.index(k)))
    return {"kinds": c["kinds"], "primary": k, "role": c["roles"][k],
            "word": next((w for x, w in found if x == k), None), "trade": found[0][1] if found else None,
            "sitelinks": c["sitelinks"]}


DATE = re.compile(r"^([+-]?)(\d+)-")


def year(timestamp: str | None) -> int | None:
    """The astronomical year of an xsd:dateTime: '-0003-01-01T00:00:00Z' → -3 (4 BC). Unknown values ('somevalue'
    blank nodes, which reach SPARQL as genid IRIs) give None."""
    m = DATE.match(timestamp or "")
    if not m:
        return None
    return -int(m.group(2)) if m.group(1) == "-" else int(m.group(2))


RANK = {"PreferredRank": 0, "NormalRank": 1}


def best_date(options: list[tuple[str, int | None, int | None]]) -> dict | None:
    """Of a property's statements (rank, year, precision), the preferred one, then the most precise, then the earliest:
    {"year", "precision"} (precision: 9 = year, 8 = decade, 7 = century, as Wikidata), or None."""
    known = [(RANK.get(r, 2), -(p or 0), y, p) for r, y, p in options if y is not None]
    if not known:
        return None
    _, _, y, p = min(known)
    return {"year": y, "precision": p}


def batches(qids: list[str], prefix: str) -> dict[str, list[str]]:
    """Batches of BATCH items in QID order, each named after its contents (a new candidate set refetches only the
    batches it changes)."""
    ordered = sorted(set(qids), key=qid_number)
    out = {}
    for i in range(0, len(ordered), BATCH):
        chunk = ordered[i:i + BATCH]
        out[f"{prefix}/{hashlib.sha1(' '.join(chunk).encode()).hexdigest()[:12]}.json"] = chunk
    return out


class WikidataPersonajes(Source):
    info = SourceInfo(
        id="wikidata_personajes",
        title="Wikidata: famous people born in Spain (occupations, offices, awards, birthplaces and dates)",
        publisher="Wikidata (Wikimedia Foundation and volunteer editors)",
        homepage="https://www.wikidata.org/",
        license="CC0 1.0 (public domain dedication)",
        description="People whose place of birth Wikidata puts in Spain (or, for historical places, in a polity of "
        "the peninsula), with their occupations, positions held (monarchs, popes, cardinals), Nobel Prizes, "
        "canonization status, sitelink count, dates of birth and death and birthplace coordinates, from Wikidata's "
        "SPARQL service. Volunteer-edited: who has an item, and which occupations it lists, follows Wikipedia's "
        "coverage, not a register.",
        used_for=["Great people lens"],
    )

    def fetch(self, force=False):
        for name, base in SHARDS.items():
            self._query(f"occupations/{name}.json", OCCUPATIONS % base, force)
            self._query(f"honours/{name}.json", HONOURS % base, force)
        self._query("conquistadors_unborn.json", UNBORN, force)
        for cls in DEEP:
            self._query(tree_file(cls), TREE % cls, force)
        for rel, chunk in batches(list(self._candidates()), "details").items():
            self._query(rel, DETAILS % (_items(chunk), LANGUAGES), force)

    def _query(self, rel: str, sparql: str, force: bool) -> None:
        """Download one SPARQL answer. The endpoint can cut an answer short at its time limit and still send 200, so
        an answer that is not valid JSON is discarded and asked for again (twice), then reported. Each new query waits
        PAUSE seconds first: the endpoint answers 429 to a client that spends more than a minute of query time in a
        minute."""
        url = ENDPOINT + urllib.parse.quote_plus(" ".join(sparql.split()), safe=":")  # short: the Almanac cites it
        for attempt in range(3):
            if force or attempt or not (self.raw_dir / rel).exists():
                time.sleep(PAUSE)
            path = self.download(url, rel, force=force or attempt > 0, headers=HEADERS)
            try:
                json.loads(path.read_text())
                return
            except json.JSONDecodeError:
                self.discard(rel)
        raise RuntimeError(f"wikidata_personajes: {rel} came back cut short three times; try again later")

    def _rows(self, rel: str) -> list[dict]:
        return json.loads((self.raw_dir / rel).read_text())["results"]["bindings"]

    def _trees(self) -> dict[str, set[str]]:
        """Class → it and all its subclasses, for the classes that count with their trees."""
        return {cls: {qid(b["x"]["value"]) for b in self._rows(tree_file(cls))} for cls in DEEP}

    def _candidates(self) -> dict[str, dict]:
        """QID → classify() of every person a category keeps."""
        sitelinks: dict[str, int] = {}
        values: dict[str, dict[str, set[str]]] = {}
        for name in SHARDS:
            for b in self._rows(f"occupations/{name}.json"):
                p = qid(b["p"]["value"])
                sitelinks[p] = int(value(b, "s"))
                if "x" in b:
                    values.setdefault(p, {}).setdefault("P106", set()).add(qid(b["x"]["value"]))
            for b in self._rows(f"honours/{name}.json"):
                values.setdefault(qid(b["p"]["value"]), {}).setdefault(value(b, "k"), set()).add(qid(b["x"]["value"]))
        trees = self._trees()
        return {p: c for p, s in sitelinks.items() if (c := classify(values.get(p, {}), s, trees))}

    def process(self):
        people = self._candidates()
        detail_files = list(batches(list(people), "details"))
        details: dict[str, dict] = {}
        places: dict[str, dict] = {}
        for rel in detail_files:
            for b in self._rows(rel):
                d = details.setdefault(qid(b["p"]["value"]), {"name": None, "description": None, "female": False,
                                                              "places": set(), "born": [], "died": []})
                d["name"] = _label(value(b, "pLabel"))
                d["description"] = value(b, "pDescription")
                d["female"] |= qid(value(b, "g") or "") in FEMALE
                for key, prec, rank in (("born", "bp", "br"), ("died", "dp", "dr")):
                    if key in b:
                        d[key].append((value(b, rank).rsplit("#", 1)[-1], year(value(b, key)),
                                       int(value(b, prec))))
                if "b" in b and _is_item(b["b"]["value"]):
                    d["places"].add(qid(b["b"]["value"]))
                    _add_place(places, b)
        unborn = int(self._rows("conquistadors_unborn.json")[0]["n"]["value"])
        out = []
        for p, c in people.items():
            d = details[p]
            out.append({
                "qid": p, "name": d["name"], "description": d["description"], "female": d["female"],
                "born": best_date(d["born"]), "died": best_date(d["died"]), **primary(c, d["description"]),
                "birthplaces": [birthplace(places[b]) for b in sorted(d["places"], key=qid_number)],
            })
        out.sort(key=lambda r: (-r["sitelinks"], qid_number(r["qid"])))
        files = [f"{k}/{n}.json" for n in SHARDS for k in ("occupations", "honours")] + ["conquistadors_unborn.json"]
        files += [tree_file(cls) for cls in DEEP] + detail_files
        return {
            "vintage": f"Wikidata, {read_manifest(self.id)['occupations/spain_15.json']['retrieved'][:10]}",
            "_files": files,
            "kinds": KIND_IDS,
            "conquistadors_without_birthplace": unborn,
            "people": out,
        }


def _label(v: str | None) -> str | None:
    """A label, or None where the label service has none in our languages (it returns the bare QID)."""
    return None if v is None or re.fullmatch(r"Q\d+", v) else v


def _add_place(places: dict[str, dict], b: dict) -> None:
    """Gather one answer row's facts about a birthplace."""
    q = qid(b["b"]["value"])
    r = places.setdefault(q, {"qid": q, "name": None, "coord": None, "types": set(), "up": {}})
    r["name"] = _label(value(b, "bLabel"))
    r["coord"] = r["coord"] or point(value(b, "coord"))
    if "t" in b:
        r["types"].add(qid(b["t"]["value"]))
    if "up" in b and point(value(b, "upcoord")):
        up = r["up"].setdefault(qid(b["up"]["value"]), {"coord": point(value(b, "upcoord")), "types": set()})
        if "ut" in b:
            up["types"].add(qid(b["ut"]["value"]))


def birthplace(r: dict) -> dict:
    """{qid, name, coord, via, area} of a birthplace: `via` "P625" (its own coordinates), "P131" (none of its own:
    those of the place it is in, the first by QID) or None; `area` True when it, or the place it is in, is a country
    or a region."""
    if r["coord"]:
        coord, via, types = r["coord"], "P625", r["types"]
    elif r["up"]:
        first = min(r["up"], key=qid_number)
        coord, via, types = r["up"][first]["coord"], "P131", r["types"] | r["up"][first]["types"]
    else:
        coord, via, types = None, None, r["types"]
    return {"qid": r["qid"], "name": r["name"], "coord": coord, "via": via, "area": bool(types & AREAS)}


def _is_item(uri: str) -> bool:
    """An entity IRI, not an unknown value ('somevalue' comes as a genid blank node)."""
    return "/entity/Q" in uri
