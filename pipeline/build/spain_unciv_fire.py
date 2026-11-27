"""The fire season of the Unciv mod: an event that can put a great fire on a major civilization's land, where EFFIS
saw great fires burn in Spain, and the files that make it (Events.json, GlobalUniques.json and their Spanish).
spain_unciv.py measures it (season) into unciv.json's summary; pipeline/play.py writes the files from that summary.
No build(): it is a helper of spain_unciv, not a builder.

What is data and what is convention (DECISIONS E90):
* Data (EFFIS 2016-2025, CC BY 4.0): each fire of GREAT_FIRE_HA or more is shared among the 25 km tiles its perimeter
  covers (spain_daily.burnt_cells on the map's fine hexes, each hex in the tile that holds its centre). Over Spain's
  land tiles that gives each class of tile, as Unciv's tile filters count them (CLASSES), its great fires per tile per
  season, λ, and its share of Spain's great fires, s = λ / Σ λ·N; the weight is s in UNIT parts.
* Conventions: a turn is one fire season; each season Spain's great fire lands on a civilization with the share of
  Spain it owns, P = Σ s·owned (all of Spain: one a season, against EFFIS's fires_per_season); the check runs every
  CHECK_TURNS turns with 1 - (1 - P)^CHECK_TURNS; brigades cost COSTS gold by era; letting it burn costs PENALTY_PCT %
  production for PENALTY_TURNS turns. Land outside Spain has no EFFIS data and counts with Spain's rates for its class.

Unciv 5.0.1 (core/src/com/unciv): the event fires from Global uniques with <upon turn start> (TurnManager.startTurn);
<with [N]% chance> takes an integer, so the chance comes in bands of the countable expression, one Global unique per
percent (bands); <every [N] turns> is turns % N == 0 (Conditionals.kt); "is between" includes both ends.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from ..core.lang import tr
from . import unciv
from .spain_daily import burnt_cells

EVENT = "Fire season"  # the event's name in Events.json, the key the Global uniques trigger
GREAT_FIRE_HA = 500  # MITECO's threshold for a gran incendio forestal (of forest land; EFFIS counts all land)
CHECK_TURNS = 5  # turns between checks
PENALTY_PCT = -25  # production in every city while the fire burns
PENALTY_TURNS = CHECK_TURNS  # as long as the gap between checks, so two penalties never add up
UNIT = 100_000  # Spain as a whole in the weights: the countable expression is P × UNIT
SUMMER = (6, 7, 8, 9)  # June to September
CLASSES = ("Mountain", "Hill", "Land")  # Unciv's tile filters: Mountain base terrain, Hill feature, any land
# (from era, before era, gold) of the brigades, all three times the game speed's gold cost modifier (Speeds.json).
COSTS = ((None, "Medieval era", 60), ("Medieval era", "Industrial era", 150), ("Industrial era", None, 400))
AI_PAY_WEIGHT_PCT = 100  # AI civs pick paying twice as often as letting it burn, when they can pay
# Empires to show the chance with, tiles by class: a new city on flat land, a small and a middling empire.
EXAMPLES = ({"Land": 7, "Hill": 0, "Mountain": 0}, {"Land": 24, "Hill": 6, "Mountain": 2},
            {"Land": 100, "Hill": 22, "Mountain": 8})


def tile_class(tile: unciv.Tile) -> str:
    """The class a land tile counts in: Mountain (base terrain), Hill (feature, wooded hills too) or plain Land."""
    return "Mountain" if tile.base == "Mountain" else "Hill" if "Hill" in tile.features else "Land"


def season(effis: dict, tiles: list[unciv.Tile], fine, proj) -> dict:
    """unciv.json's summary.fire_season from EFFIS's fires (load_interim("effis_incendios")) and the map's tiles
    (`fine` is world.json's HexGrid, `proj` the lon/lat → km projection)."""
    spanish = [t for t, tile in enumerate(tiles) if tile.is_land and tile.national]
    tiles_in = Counter(tile_class(tiles[t]) for t in spanish)
    if set(tiles_in) != set(CLASSES):
        raise RuntimeError(f"Spain's land tiles lack a class: {dict(tiles_in)}")
    class_of = {c: tile_class(tiles[t]) for t in spanish for c in tiles[t].cells}
    fires = effis["fires"]
    great = [f for f in fires if f["area_ha"] >= GREAT_FIRE_HA]
    shares = Counter()
    for fire in great:
        cells = burnt_cells([fire], proj, fine)
        total = sum(cells.values())
        for c, ha in cells.items():
            if c in class_of:
                shares[class_of[c]] += ha / total
    first, last = effis["years"]
    seasons = last - first + 1
    rate = {k: shares[k] / (seasons * tiles_in[k]) for k in CLASSES}  # great fires per tile per season
    per_season = sum(shares.values()) / seasons
    classes = [{"class": k, "tiles": tiles_in[k], "per_tile_season": round(rate[k], 4),
                "weight": round(UNIT * rate[k] / per_season)} for k in CLASSES]
    summer = sum(f["area_ha"] for f in fires if f["month"] in SUMMER) / sum(f["area_ha"] for f in fires)
    by_season = Counter(f["year"] for f in great)
    numbers = {"n": len(great), "ha": GREAT_FIRE_HA, "seasons": seasons, "per": round(len(great) / seasons),
               "times": rough_times(classes), "k": CHECK_TURNS}
    return {
        "threshold_ha": GREAT_FIRE_HA, "years": [first, last], "great_fires": len(great),
        "per_season": [by_season[y] for y in range(first, last + 1)],
        "on_spanish_tiles": round(sum(shares.values()), 1), "summer_share": round(summer, 3), "seasons": seasons,
        "fires_per_season": round(per_season, 1), "classes": classes, "unit": UNIT,
        "texts": {key: text.format(**numbers) for key, text in TEXTS.items()},
    }


def rough_times(classes: list[dict]) -> int:
    """How many times as many great fires a hill or mountain tile has as any other land tile, rounded."""
    by = {c["class"]: c for c in classes}
    rough = [by[k] for k in ("Hill", "Mountain")]
    per_tile = sum(c["per_tile_season"] * c["tiles"] for c in rough) / sum(c["tiles"] for c in rough)
    return round(per_tile / by["Land"]["per_tile_season"])


# The game's texts: English is Events.json's text and the key of its Spanish line (translations). Unciv writes the
# numbers in them as the player's language does, so they carry plain integers and no years.
TEXTS = {
    "name": tr("Temporada de incendios", EVENT),
    "event": tr("Arde un gran incendio en tu territorio. En España el EFFIS cartografió {n} incendios de {ha} "
                "ha o más en {seasons} temporadas, unos {per} por temporada, y en colinas y montañas arden {times} "
                "veces más por casilla que en el llano.",
                "A great fire is burning on your land. In Spain EFFIS mapped {n} fires of {ha} ha or more in "
                "{seasons} seasons, about {per} a season, and hills and mountains burn {times} times as often per tile "
                "as flat land."),
    "pay": tr("Enviar brigadas", "Send fire brigades"),
    "burn": tr("Dejar que se apague solo", "Let it burn out"),
    "pedia": tr("Temporada de incendios: cada {k} turnos puede declararse un gran incendio en tu territorio, con más "
                "probabilidad cuanto más territorio tienes, y más en colinas y montañas, según los incendios que el "
                "EFFIS cartografió en España.",
                "Fire season: every {k} turns a great fire can break out on your land, more likely the more land you "
                "own, and more in hills and mountains, from the fires EFFIS mapped in Spain."),
}


def weights(summary: dict) -> dict[str, int]:
    """Class → weight, from unciv.json's summary.fire_season."""
    return {c["class"]: c["weight"] for c in summary["classes"]}


def owned(tiles_by_class: dict[str, int], w: dict[str, int]) -> int:
    """The countable expression's value for an empire with these land tiles by class."""
    return sum(w[k] * tiles_by_class.get(k, 0) for k in CLASSES)


def chance(x: int) -> int:
    """The check's chance in whole percent for a civilization whose land adds up to x (UNIT is all of Spain)."""
    p_season = min(x, UNIT) / UNIT
    return round(100 * (1 - (1 - p_season) ** CHECK_TURNS))


def bands(top: int = UNIT) -> list[tuple[int, int, int | None]]:
    """(chance %, lowest x, highest x) of each whole percent from 1 to 100, x being the countable expression (the
    last band has no top). x = 0 to the first band's start gives no chance and no line."""
    out: list[list] = []
    for x in range(top + 1):
        p = chance(x)
        if p == 0:
            continue
        if out and out[-1][0] == p:
            out[-1][2] = x
        else:
            out.append([p, x, x])
    out[-1][2] = None
    return [tuple(b) for b in out]


def expression(w: dict[str, int]) -> str:
    """Unciv's countable for Σ weight × owned tiles: Land counts every land tile, so Hill and Mountain add the rest."""
    land = w["Land"]
    return (f"[Owned [Land] Tiles] * {land} + [Owned [Hill] Tiles] * {w['Hill'] - land}"
            f" + [Owned [Mountain] Tiles] * {w['Mountain'] - land}")


def global_uniques_json(summary: dict) -> dict:
    """jsons/GlobalUniques.json: one hidden line per percent of chance, and the rule in a line of Civilopedia text."""
    expr = expression(weights(summary))
    lines = []
    for p, lo, hi in bands():
        when = f"is between [{lo}] and [{hi}]" if hi is not None else f"is more than [{lo - 1}]"
        lines.append(f"Triggers a [{EVENT}] event <upon turn start> <every [{CHECK_TURNS}] turns> "
                     f"<for [Major] Civilizations> <with [{p}]% chance> <when number of [{expr}] {when}> "
                     f"<hidden from users>")
    return {"name": "Global Uniques", "uniques": lines, "civilopediaText": [{"text": summary["texts"]["pedia"]["en"]}]}


def era_conditions(start: str | None, end: str | None) -> str:
    return (f" <starting from the [{start}]>" if start else "") + (f" <before the [{end}]>" if end else "")


def events_json(summary: dict) -> list[dict]:
    """jsons/Events.json: the fire season, with one brigades choice per era span and letting it burn.

    A choice is offered only while its conditions hold, so a civilization with too little gold only sees "let it
    burn". The gold bound is the cost itself, both times the game speed (Conditionals.checkResourceOrStatAmount and
    OneTimeGainStat use the same gold cost modifier): "more than cost" never lets the treasury go below zero."""
    costs_by_era()  # every era has one price
    texts = {k: t["en"] for k, t in summary["texts"].items()}
    speed = "<(modified by game speed)>"
    pay = [{"text": texts["pay"], "uniques": [
        f"Gain [-{gold}] [Gold] {speed}",
        f"Only available <when above [{gold}] [Gold]>{era_conditions(start, end)} {speed}",
        f"[+{AI_PAY_WEIGHT_PCT}]% weight to this choice for AI decisions"]} for start, end, gold in COSTS]
    burn = {"text": texts["burn"], "uniques": [f"[{PENALTY_PCT}]% [Production] [in all cities] <for [{PENALTY_TURNS}] turns>"]}
    return [{"name": EVENT, "presentation": "Alert", "text": texts["event"], "choices": [*pay, burn]}]


def costs_by_era() -> dict[str, int]:
    """Era → brigades gold at standard speed (each era in exactly one span, or it fails)."""
    out = {}
    for start, end, gold in COSTS:
        lo = unciv.ERAS.index(start) if start else 0
        hi = unciv.ERAS.index(end) if end else len(unciv.ERAS)
        for era in unciv.ERAS[lo:hi]:
            if era in out:
                raise ValueError(f"{era}: two brigade costs")
            out[era] = gold
    if len(out) != len(unciv.ERAS):
        raise ValueError(f"eras without brigades: {set(unciv.ERAS) - set(out)}")
    return out


def check(web_dir) -> list[tuple[str, str]]:
    """unciv.json's fire season: the class weights over Spain add up to UNIT within 1 %. Nothing without an Unciv map."""
    path = Path(web_dir) / "unciv.json"
    if not path.exists():
        return []
    fire = json.loads(path.read_text())["summary"].get("fire_season")
    if fire is None:
        return [("FAIL", "unciv.json: no summary.fire_season")]
    total = sum(c["weight"] * c["tiles"] for c in fire["classes"])
    w = ", ".join(f"{c['class']} {c['weight']}" for c in fire["classes"])
    off = 1 - fire["on_spanish_tiles"] / fire["great_fires"]  # islands without a land tile, coastal hexes at sea
    if abs(total - fire["unit"]) > fire["unit"] / 100:
        return [("FAIL", f"unciv.json fire season: weights over Spain add up to {total}, not {fire['unit']} ({w})")]
    return [("PASS", f"unciv.json fire season: {fire['great_fires']} fires of {fire['threshold_ha']} ha or more, "
                     f"{fire['fires_per_season']} a season on Spanish tiles ({off:.1%} off them); weights {w} "
                     f"(Spain {total}); {len(bands())} chance bands")]
