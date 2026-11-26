"""Read the cell values of an .xlsx workbook (standard library only: an .xlsx is a zip of XML parts).

Values come back as strings (numbers as their XML text) or None for empty cells; formulas give their cached value.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _column(ref: str) -> int:
    """'C7' → 2."""
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def sheets(path: Path) -> dict[str, list[list[str | None]]]:
    """{sheet name: rows of cell values}, cells placed by their column letter."""
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
                shared.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
        rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        out = {}
        for sheet in ET.fromstring(z.read("xl/workbook.xml")).iter("{%s}sheet" % NS["m"]):
            target = rels[sheet.get(REL)].lstrip("/")
            part = target if target.startswith("xl/") else f"xl/{target}"
            rows = []
            for r in ET.fromstring(z.read(part)).iter("{%s}row" % NS["m"]):
                cells: dict[int, str | None] = {}
                for c in r.findall("m:c", NS):
                    v, kind = c.find("m:v", NS), c.get("t")
                    if kind == "s" and v is not None:
                        val = shared[int(v.text)]
                    elif kind == "inlineStr":
                        val = "".join(t.text or "" for t in c.iter("{%s}t" % NS["m"]))
                    else:
                        val = v.text if v is not None else None
                    cells[_column(c.get("r"))] = val
                rows.append([cells.get(i) for i in range(max(cells) + 1)] if cells else [])
            out[sheet.get("name")] = rows
        return out
