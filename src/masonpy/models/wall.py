"""Finite or periodic occupancy with atomic placement and undo."""

from __future__ import annotations

from typing import Any, Iterator

from .errors import PlacementError
from .stone import Stone


class Wall:
    """A rectangular grid and the stones occupying it.

    Coordinates start at the bottom-left. The occupancy grid is indexed as
    ``occupancy[y][x]`` and contains stone IDs or ``None``.
    """

    def __init__(
        self, width: int, height: int, *, resolution: int = 1, wrap_x: bool = False
    ) -> None:
        """Create an empty integer grid. Horizontal wrapping affects occupancy, not stone identity."""
        if not isinstance(width, int) or not isinstance(height, int):
            raise TypeError("wall dimensions must be integers")
        if width <= 0 or height <= 0:
            raise ValueError("wall dimensions must be positive")
        if not isinstance(resolution, int) or resolution <= 0:
            raise ValueError("resolution must be a positive integer")
        if not isinstance(wrap_x, bool):
            raise TypeError("wrap_x must be a boolean")

        self.width = width
        self.height = height
        self.resolution = resolution
        self.wrap_x = wrap_x
        self._stones: list[Stone] = []
        self._stone_ids: set[int] = set()
        self._occupancy: list[list[int | None]] = [
            [None for _ in range(width)] for _ in range(height)
        ]

    @property
    def stones(self) -> tuple[Stone, ...]:
        """Return stones in placement order as an immutable tuple."""
        return tuple(self._stones)

    @property
    def occupancy(self) -> tuple[tuple[int | None, ...], ...]:
        """Return row-major occupancy as tuples; cells contain stone IDs or None."""
        return tuple(tuple(row) for row in self._occupancy)

    @property
    def next_stone_id(self) -> int:
        """Return the next available non-negative identity after the current prefix."""
        return max(self._stone_ids, default=-1) + 1

    def add_stone(self, stone: Stone) -> None:
        """Validate and add ``stone``, updating occupancy atomically."""

        self._validate_stone(stone)
        for row, column in self._stone_cells(stone):
            self._occupancy[row][column] = stone.id
        self._stones.append(stone)
        self._stone_ids.add(stone.id)

    def remove_last_stone(self) -> Stone | None:
        """Remove and return the most recently added stone, if one exists."""

        if not self._stones:
            return None

        stone = self._stones.pop()
        for row, column in self._stone_cells(stone):
            self._occupancy[row][column] = None
        self._stone_ids.remove(stone.id)
        return stone

    def _validate_stone(self, stone: Stone) -> None:
        """Reject invalid dimensions, duplicate IDs, boundary violations or overlaps before mutation."""
        values = (stone.id, stone.x, stone.y, stone.width, stone.height)
        if any(not isinstance(value, int) for value in values):
            raise PlacementError("stone ID, position, and dimensions must be integers")
        if stone.id < 0:
            raise PlacementError("stone ID must be non-negative")
        if stone.id in self._stone_ids:
            raise PlacementError(f"stone ID {stone.id} is already in use")
        if stone.width <= 0 or stone.height <= 0:
            raise PlacementError("stone dimensions must be positive")
        if stone.y < 0:
            raise PlacementError("stone vertical position must be non-negative")
        if stone.y + stone.height > self.height:
            raise PlacementError("stone extends outside the wall")
        if stone.x >= self.width or stone.x + stone.width <= 0:
            raise PlacementError("stone does not intersect the wall")
        if self.wrap_x and stone.width > self.width:
            raise PlacementError("stone wider than the logical circumference")

        for row, column in self._stone_cells(stone):
            occupant = self._occupancy[row][column]
            if occupant is not None:
                raise PlacementError(
                    f"stone overlaps stone {occupant} at ({column}, {row})"
                )

    def _stone_cells(self, stone: Stone) -> Iterator[tuple[int, int]]:
        """Yield (row, column) cells, clipping finite walls or folding periodic ones once."""
        for row in range(stone.y, stone.y + stone.height):
            columns = (
                ((stone.x + dx) % self.width for dx in range(stone.width))
                if self.wrap_x
                else range(max(0, stone.x), min(self.width, stone.x + stone.width))
            )
            for column in columns:
                yield row, column

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation of the current object or snapshot."""
        return {
            "width": self.width,
            "height": self.height,
            "resolution": self.resolution,
            "wrap_x": self.wrap_x,
            "stones": [stone.to_dict() for stone in self._stones],
        }
