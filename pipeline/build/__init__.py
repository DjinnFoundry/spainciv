"""Builders, discovered automatically and run in dependency order.

A builder is any module in this package that defines:

    REQUIRES: list[str]   # interim names it reads (sources, or "_name" interims made by other builders)
                          # or {country id: list[str]} when each country feeds it from its own sources
    PRODUCES: list[str]   # "_name" interims and/or web/data file names it writes
    def build() -> None

Optionally RUN_LAST = True (e.g. the catalog, which describes everything else), and COUNTRIES = ("us",) for a
builder that only makes sense for some countries (see pipeline/countries).
Modules without a `build` function (e.g. yields.py) are helpers, not builders.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

from ..countries import active, serves


def requires(mod: ModuleType, country_id: str | None = None) -> list[str]:
    """A builder's REQUIRES for the (active) country."""
    req = getattr(mod, "REQUIRES", [])
    if isinstance(req, dict):
        return list(req.get(country_id or active().id, []))
    return list(req)


def _discover() -> dict[str, ModuleType]:
    mods = {}
    for m in pkgutil.iter_modules(__path__):
        mod = importlib.import_module(f"{__name__}.{m.name}")
        if callable(getattr(mod, "build", None)) and hasattr(mod, "PRODUCES"):
            mods[m.name] = mod
    return mods


def _order(mods: dict[str, ModuleType], country_id: str = "us") -> list[str]:
    producer = {out: name for name, mod in mods.items() for out in mod.PRODUCES}
    deps = {name: {producer[r] for r in requires(mod, country_id) if r in producer and producer[r] != name} for name, mod in mods.items()}
    ordered, seen, active_ = [], set(), set()

    def visit(n):
        if n in seen:
            return
        if n in active_:
            raise RuntimeError(f"builder dependency cycle at {n}")
        active_.add(n)
        for d in sorted(deps[n]):
            visit(d)
        active_.discard(n)
        seen.add(n)
        ordered.append(n)

    for n in sorted(mods, key=lambda n: (getattr(mods[n], "RUN_LAST", False), n)):
        visit(n)
    last = [n for n in ordered if getattr(mods[n], "RUN_LAST", False)]
    return [n for n in ordered if n not in last] + last


_MODS = _discover()


def builders_for(country_id: str) -> dict[str, ModuleType]:
    """The builders serving a country, in dependency order."""
    mods = {n: m for n, m in _MODS.items() if serves(m, country_id)}
    return {name: mods[name] for name in _order(mods, country_id)}


BUILDERS = builders_for("us")


def producers_of(outputs) -> list[str]:
    """Builder names producing any of the given interim/web names."""
    return [n for n, m in BUILDERS.items() if set(m.PRODUCES) & set(outputs)]
