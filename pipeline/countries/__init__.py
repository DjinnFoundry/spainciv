"""Country configurations: what makes a map the United States or Spain.

Everything country-specific that is not a data source lives in one `Country`: the projection and hex size, the
names of the administrative levels, the money and number formats, the regions left off the map, the product
name and address, and where the country's interim and web files go. The pipeline works on one *active* country,
chosen with `--country` (default `us`); `active()` returns it.

Sources and builders say which countries they serve: a module-level `COUNTRIES = ("us",)` limits a builder or a
source module to those countries (no attribute = every country).
"""

from __future__ import annotations

import contextlib
from dataclasses import replace

from .base import Country, Level, Page  # noqa: F401  (re-exported)


def _registry() -> dict[str, Country]:
    from . import es, us

    return {c.id: c for c in (us.COUNTRY, es.COUNTRY)}


COUNTRIES: dict[str, Country] = _registry()
_active: Country = COUNTRIES["us"]


def active() -> Country:
    return _active


def set_active(country_id: str) -> Country:
    global _active
    if country_id not in COUNTRIES:
        raise SystemExit(f"unknown country {country_id!r} (known: {', '.join(COUNTRIES)})")
    _active = COUNTRIES[country_id]
    return _active


def serves(module, country_id: str | None = None) -> bool:
    """True if a source or builder module serves the (active) country."""
    allowed = getattr(module, "COUNTRIES", None)
    return allowed is None or (country_id or _active.id) in allowed


@contextlib.contextmanager
def using(country_id: str | None = None, **changes):
    """Temporarily make a country active, optionally with fields replaced (tests point the dirs at a temp folder)."""
    global _active
    before = _active
    base = COUNTRIES[country_id] if country_id else _active
    _active = replace(base, **changes) if changes else base
    try:
        yield _active
    finally:
        _active = before
