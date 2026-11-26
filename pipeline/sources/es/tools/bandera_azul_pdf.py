"""Blue Flag beach list (ADEAC's PDF) → pipeline/sources/es/data/bandera_azul_2026.csv.

Not part of the pipeline (it needs poppler's pdftotext); run it by hand when ADEAC publishes a new list:

    curl -o list.pdf "https://www.banderaazul.org/sites/default/files/2026/Rueda-de-prensa-2026/Relaci%C3%B3n%20Playas%20Galardonadas%202026.pdf"
    pdftotext -bbox list.pdf list.html
    python3 -I pipeline/sources/es/tools/bandera_azul_pdf.py list.html pipeline/sources/es/data/bandera_azul_2026.csv

The PDF sets three columns per page. Font size tells the levels apart: a community header is 16.8 pt ("ANDALUCÍA (143
playas en 48 municipios)"), a province header 14.4 pt in capitals, a municipality 14.4 pt, a beach 12–13.2 pt, and
the NUEVA / RECUPERA tags 8.4 pt. A beach line indented further than its column's beaches continues the line above;
a municipality line straight after another continues its name. A header starting at a column's left edge belongs to
that column only ("TERRES DE L'EBRE" beside Tarragona's columns); any other, centred one spans the page. The script
fails unless its count per community equals the PDF's own header.
"""

from __future__ import annotations

import collections
import csv
import html
import re
import sys

WORD = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>')
FOOTER_Y = 780  # page numbers and ADEAC's address
SAME_LINE, WORD_GAP = 1.5, 12  # pt: words on one line share a top within SAME_LINE and are at most WORD_GAP apart
COLUMN_GAP = 40  # pt: column starts are further apart than this; a wrapped municipality name starts closer
BEACH_INDENT = 18  # pt: beaches start under 18 pt right of their column, continuation lines further


def page_words(page: str) -> list[tuple[float, float, float, float, str]]:
    """(x0, y0, x1, height, text) of a page's words, without tags, the legend at the end and the footer."""
    words = [(float(a), float(b), float(c), float(d) - float(b), html.unescape(w)) for a, b, c, d, w in WORD.findall(page)]
    legend = min((w[1] for w, v in zip(words, words[1:]) if (w[4], v[4]) == ("primera", "vez")), default=FOOTER_Y)
    return [w for w in words if w[3] >= 9 and w[1] < min(legend - 5, FOOTER_Y)]


def is_header(w, words) -> bool:
    """A 14.4 pt word in capitals is a header, except a municipality's one-letter article ('A Coruña')."""
    if w[3] > 15:
        return True
    if w[3] < 14 or not w[4].isupper():
        return False
    after = next((v for v in words if abs(v[1] - w[1]) < SAME_LINE and 0 < v[0] - w[2] < WORD_GAP), None)
    return len(w[4]) > 1 or bool(after and after[4].isupper() and len(after[4]) > 1)


def columns(words) -> list[float]:
    """Left edges of the page's columns: where municipality lines start."""
    starts = sorted({round(w[0]) for w in words if w[3] >= 14 and not is_header(w, words)
                     and not any(abs(v[1] - w[1]) < SAME_LINE and 0 < w[0] - v[2] < WORD_GAP for v in words)})
    cols: list[float] = []
    for x in starts:
        if not cols or x - cols[-1] > COLUMN_GAP:
            cols.append(x)
    return cols


def page_lines(words, cols) -> list[dict]:
    """Words joined into lines: headers across the page, everything else within its column."""
    col_of = lambda x: max([k for k, c in enumerate(cols) if x >= c - 5], default=0)
    lines: list[dict] = []
    key = lambda w: (is_header(w, words), -1 if is_header(w, words) else col_of(w[0]), round(w[1]), w[0])
    for w in sorted(words, key=key):
        x0, y0, x1, h, text = w
        hd, last = is_header(w, words), lines[-1] if lines else None
        if (last and abs(last["y"] - y0) < SAME_LINE and x0 - last["x1"] < WORD_GAP and last["header"] == hd
                and (hd or last["col"] == col_of(x0))):
            last["x1"], last["text"] = x1, f"{last['text']} {text}"
        else:
            lines.append({"y": y0, "x0": x0, "x1": x1, "h": h, "text": text, "header": hd, "col": col_of(x0)})
    return lines


class Reader:
    """Walks the pages in reading order, keeping the current community, province and municipality."""

    def __init__(self):
        self.rows: list[list[str]] = []
        self.totals: dict[str, int] = {}
        self.community = self.province = self.muni = None

    def header(self, text: str) -> None:
        if m := re.match(r"(.+?)\s*\((\d+) playas? en", text):
            self.community, self.province = m.group(1).strip(), None
            self.totals[self.community] = int(m.group(2))
        elif "BANDERA" not in text and "RELACIÓN" not in text:
            self.province = text.strip()

    def column(self, lines: list[dict], left: float) -> None:
        after_muni = False
        for line in sorted(lines, key=lambda l: l["y"]):
            text = line["text"].strip()
            if line["header"]:
                self.header(text)
                after_muni = False
            elif line["h"] >= 14:
                self.muni = f"{self.muni} {text}" if after_muni else text
                after_muni = True
            else:
                after_muni = False
                if line["x0"] - left < BEACH_INDENT:
                    self.rows.append([self.community, self.province or "", self.muni, text])
                elif self.rows:
                    self.rows[-1][3] += ("" if self.rows[-1][3].endswith("-") else " ") + text

    def page(self, page: str) -> None:
        words = page_words(page)
        cols = columns(words)
        lines = page_lines(words, cols)
        local = lambda l: any(abs(l["x0"] - c) < 3 for c in cols)
        wide = [l for l in lines if l["header"] and not local(l)]
        bounds = [-1.0] + [l["y"] for l in wide] + [float("inf")]
        for b in range(len(bounds) - 1):
            if b:
                self.header(wide[b - 1]["text"])
            for c, left in enumerate(cols):
                self.column([l for l in lines if l["col"] == c and bounds[b] < l["y"] < bounds[b + 1]
                             and (not l["header"] or local(l))], left)


def main(src: str, out: str) -> None:
    reader = Reader()
    for page in re.split(r"<page ", open(src, encoding="utf-8").read())[1:]:
        reader.page(page)
    got = collections.Counter(r[0] for r in reader.rows)
    bad = {k: (v, got.get(k)) for k, v in reader.totals.items() if v != got.get(k)}
    if bad:
        sys.exit(f"beaches per community differ from the PDF's headers (expected, read): {bad}")
    with open(out, "w", newline="", encoding="utf-8") as f:
        f.write("# Blue Flag beaches 2026-2027 (ADEAC, Bandera Azul), read from its PDF by tools/bandera_azul_pdf.py.\n")
        writer = csv.writer(f)
        writer.writerow(["community", "province", "municipality", "beach"])
        writer.writerows(reader.rows)
    print(f"{len(reader.rows)} beaches in {len(reader.totals)} communities, all matching the PDF's counts")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
