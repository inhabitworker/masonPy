"""Shared occupancy projection and maximal-run traversal; no placement policy."""

from __future__ import annotations

from masonpy.models import Wall


def _occupancy_cells(wall: Wall, wrap_x: bool) -> list[list[int | None]]:
    """A finite or projected grid shared by geometric analyses."""
    cells = [list(row) for row in wall.occupancy]
    if wrap_x:
        cells = [[None] * wall.width for _ in range(wall.height)]
        for stone in wall.stones:
            if stone.width > wall.width:
                raise ValueError("stone wider than the logical circumference")
            for y in range(stone.y, stone.y + stone.height):
                for dx in range(stone.width):
                    x = (stone.x + dx) % wall.width
                    if cells[y][x] is not None and cells[y][x] != stone.id:
                        raise ValueError(
                            f"logical wrapping overlaps stones at ({x}, {y})"
                        )
                    cells[y][x] = stone.id
    return cells


def _horizontal_runs(mask: list[bool], wrap_x: bool) -> list[tuple[int, int]]:
    """Return (start, length), merging a circular run exactly once."""
    width = len(mask)
    if all(mask):
        return [(0, width)]
    runs = []
    for x, active in enumerate(mask):
        if not active or (x > 0 and mask[x - 1]) or (x == 0 and wrap_x and mask[-1]):
            continue
        length = 1
        while length < width:
            column = x + length
            if not wrap_x and column >= width:
                break
            if not mask[column % width]:
                break
            length += 1
        runs.append((x, length))
    return runs
