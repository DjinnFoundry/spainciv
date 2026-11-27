"""Names of one place as different sources write them, reduced to a key that matches exactly (no fuzzy matching)."""

from __future__ import annotations

import re
import unicodedata


def name_key(name: str, dropped: frozenset[str] | set[str] = frozenset()) -> str:
    """A name without case, accents and punctuation, and without the words in `dropped` (articles, prepositions, the
    kind of place): with a beach's words, 'Playa de la Concha' and 'Praia da Concha' both give 'concha'."""
    t = unicodedata.normalize("NFD", name.lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return " ".join(w for w in re.split(r"[^a-z0-9]+", t) if w and w not in dropped)
