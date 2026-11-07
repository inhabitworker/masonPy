"""Hypothetical skyline queries: descriptive geometry, never a style score."""

from __future__ import annotations

from typing import Sequence

from masonpy.models import Stone


def resulting_plateau(
    skyline: Sequence[int], top_ids: Sequence[int | None], stone: Stone
) -> tuple[int, int]:
    """Circular skyline run containing a hypothetical stone; does not mutate."""
    circumference = len(skyline)
    extent = stone.width
    top = stone.y + stone.height
    adjoining = set()
    for column, direction in ((stone.x - 1, -1), (stone.x + stone.width, 1)):
        while extent < circumference and skyline[column % circumference] == top:
            adjoining.add(top_ids[column % circumference])
            extent += 1
            column += direction
    return extent, 1 + len(adjoining)
