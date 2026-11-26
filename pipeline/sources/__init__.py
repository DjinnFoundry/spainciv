"""Registry of data sources, discovered automatically, per country.

To add a source, drop a module in the country's package containing a Source subclass with an
`info = SourceInfo(...)` class attribute. Nothing else to register. The United States' sources are the modules
of this package; every other country has a subpackage named after its id (pipeline/sources/es/ for Spain).
"""

from __future__ import annotations

import importlib
import pkgutil

from ..core.source import Source

PACKAGES = {"us": __name__, "es": f"{__name__}.es"}


def _discover(package: str) -> list[Source]:
    pkg = importlib.import_module(package)
    found: dict[str, Source] = {}
    for m in pkgutil.iter_modules(pkg.__path__):
        if m.ispkg:
            continue
        mod = importlib.import_module(f"{package}.{m.name}")
        for obj in vars(mod).values():
            if (
                isinstance(obj, type)
                and issubclass(obj, Source)
                and obj.__module__ == mod.__name__
                and getattr(obj, "info", None) is not None
            ):
                inst = obj()
                if inst.id in found:
                    raise RuntimeError(f"duplicate source id {inst.id!r}")
                found[inst.id] = inst
    return sorted(found.values(), key=lambda s: s.id)


_CACHE: dict[str, list[Source]] = {}


def sources_for(country_id: str) -> list[Source]:
    if country_id not in _CACHE:
        _CACHE[country_id] = _discover(PACKAGES[country_id])
    return _CACHE[country_id]


SOURCES = sources_for("us")
BY_ID = {s.id: s for s in SOURCES}
