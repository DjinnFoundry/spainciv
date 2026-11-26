"""Helpers of Spain's count lenses that name what they count (museums, beaches, dishes, fiestas, castles…)."""

from __future__ import annotations

from ..core.hexgrid import HexGrid
from .cities import nearest_land


def named_counts(names: list[str], cells_of: list[list[int]], owner: list[int]) -> dict:
    """A count lens that also names what it counts: `values` (how many per land hex), `names`, and per hex the indices
    of the names in it (`labels`), which the tooltip lists."""
    labels: list[list[int] | None] = [[] if o >= 0 else None for o in owner]
    for k, cells in enumerate(cells_of):
        for c in cells:
            if c >= 0 and labels[c] is not None:
                labels[c].append(k)
    return {"values": [len(v) if v is not None else None for v in labels], "names": names, "labels": labels}


def shore_cell(grid: HexGrid, owner: list[int], x: float, y: float) -> int:
    """The land hex at x/y, or the nearest one next to it (a harbour museum sits in a sea hex); -1 if none."""
    cell = grid.cell_at(x, y)
    return -1 if cell < 0 else cell if owner[cell] >= 0 else nearest_land(grid, owner, cell, x, y, -1, max_rings=1)
