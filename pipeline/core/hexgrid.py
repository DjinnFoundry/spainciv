"""Pointy-top hex grid in "odd-r" offset layout (odd rows shifted right).

Cell (col, row) has its center at  x = W * (col + 0.5 * (row & 1)),  y = H * row
with W = sqrt(3) * radius and H = 1.5 * radius, in map km (y down).
web/js/hex.js mirrors this exactly — keep the two in sync.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass

SQRT3 = math.sqrt(3)

# Neighbour offsets in direction order E, SE, SW, W, NW, NE (y down).
_NEIGHBOURS = (
    ((1, 0), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1)),  # even rows
    ((1, 0), (1, 1), (0, 1), (-1, 0), (0, -1), (1, -1)),  # odd rows
)


@dataclass(frozen=True)
class HexGrid:
    radius: float
    cols: int
    rows: int

    @classmethod
    def covering(cls, width: float, height: float, radius: float) -> "HexGrid":
        return cls(radius, math.ceil(width / (SQRT3 * radius)) + 1, math.ceil(height / (1.5 * radius)) + 1)

    @property
    def size(self) -> int:
        return self.cols * self.rows

    def index(self, col: int, row: int) -> int:
        return row * self.cols + col

    def col_row(self, index: int) -> tuple[int, int]:
        return index % self.cols, index // self.cols

    def center(self, col: int, row: int) -> tuple[float, float]:
        return SQRT3 * self.radius * (col + 0.5 * (row & 1)), 1.5 * self.radius * row

    def cell_at(self, x: float, y: float) -> int:
        """Index of the cell containing (x, y), or -1 outside the grid."""
        q = (SQRT3 / 3 * x - y / 3) / self.radius
        r = (2 / 3 * y) / self.radius
        cx, cz = q, r
        cy = -cx - cz
        # floor(v + 0.5) is JS Math.round: Python's round() rounds half to even, which disagrees on ties.
        rx, ry, rz = math.floor(cx + 0.5), math.floor(cy + 0.5), math.floor(cz + 0.5)
        dx, dy, dz = abs(rx - cx), abs(ry - cy), abs(rz - cz)
        if dx > dy and dx > dz:
            rx = -ry - rz
        elif dy <= dz:
            rz = -rx - ry
        row = rz
        col = rx + (row - (row & 1)) // 2
        if 0 <= col < self.cols and 0 <= row < self.rows:
            return self.index(col, row)
        return -1

    def neighbour(self, index: int, direction: int) -> int:
        """The neighbour in `direction` (0 E, 1 SE, 2 SW, 3 W, 4 NW, 5 NE), or -1 outside the grid."""
        col, row = self.col_row(index)
        dc, dr = _NEIGHBOURS[row & 1][direction]
        c, r = col + dc, row + dr
        return self.index(c, r) if 0 <= c < self.cols and 0 <= r < self.rows else -1

    def neighbours(self, index: int) -> list[int]:
        return [j for d in range(6) if (j := self.neighbour(index, d)) >= 0]

    def to_dict(self) -> dict:
        return {"radius": self.radius, "cols": self.cols, "rows": self.rows}


def components(cells: list[int], neighbours: Callable[[int], Iterable[int]]) -> list[list[int]]:
    """Connected groups of `cells`, `neighbours` giving the cells next to one (HexGrid.neighbours, Grid.ring)."""
    todo, out = set(cells), []
    while todo:
        start = todo.pop()
        group, queue = [start], deque([start])
        while queue:
            for n in neighbours(queue.popleft()):
                if n in todo:
                    todo.remove(n)
                    group.append(n)
                    queue.append(n)
        out.append(sorted(group))
    return out
