"""Spanish capitalisation of names that a source writes in capitals or in English-style title case."""

from __future__ import annotations

import re

PARTICLES = {"de", "del", "y", "e", "o", "a", "en",  # lower case inside a name: 'Palma de Mallorca'
             "dels", "da", "do", "das", "dos"}  # and the Catalan and Galician contractions: 'Festa do Polbo'
ARTICLES = {"la", "las", "los", "el"}  # lower case only after 'de' or 'en' ('Jerez de la Frontera'), else part of the
# name ('Mina La Paz', 'Tenerife Norte-C. La Laguna')
ROMAN = {"I", "II", "III", "IV", "V", "VI"}
WORD = re.compile(r"[^\W\d_]+")
VOWEL = re.compile(r"[aeiouáéíóúü]", re.I)


def title_es(name: str) -> str:
    """'MINAS DE RIO TINTO' → 'Minas de Rio Tinto', 'Palma De Mallorca' → 'Palma de Mallorca'. A name in capitals gets
    its words capitalised, except Roman numerals and acronyms (three or more letters, no vowel: 'FGL'); then, in any
    name, particles between two spaces go to lower case ('S.A' keeps its A), and so does a lone I followed by a word
    that is not a particle, the Catalan 'and' ('Moros i Cristians'; 'Carlos I de España' keeps its numeral). Nothing
    else changes in a name that has lower-case letters ('PENOUTA Olga')."""
    if name.isupper():
        name = WORD.sub(lambda m: m.group(0) if m.group(0) in ROMAN or (len(m.group(0)) > 2 and not VOWEL.search(
            m.group(0))) else m.group(0).capitalize(), name)
    words = list(WORD.finditer(name))
    out, last = [], 0
    for k, m in enumerate(words):
        w, low = m.group(0), m.group(0).lower()
        prev = words[k - 1].group(0).lower() if k else None
        between_spaces = name[m.start() - 1:m.start()] == " " and name[m.end():m.end() + 1] == " "
        following = words[k + 1].group(0).lower() if k + 1 < len(words) else None
        galician_article = low in {"o", "a"} and prev in PARTICLES  # 'de O Carballiño', 'de A Coruña'
        if between_spaces and w.istitle() and not galician_article and (
                low in PARTICLES or (low in ARTICLES and prev in {"de", "en"})):
            w = low
        elif between_spaces and w == "I" and following not in PARTICLES | ARTICLES:  # Catalan 'i' (and), not Roman I
            w = "i"
        out += [name[last:m.start()], w]
        last = m.end()
    return "".join(out) + name[last:]
