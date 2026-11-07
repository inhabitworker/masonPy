"""VerticalSeam: an immutable geometric analysis record in grid units."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class VerticalSeam:
    """Maximal continuous joint at x, spanning [y, y + length)."""

    x: int
    y: int
    length: int
    left_count: int = 0
    right_count: int = 0

    @property
    def stack_count(self) -> int:
        """Return the greater count of distinct stones adjoining either side of this joint."""
        return max(self.left_count, self.right_count)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation of the current object or snapshot."""
        return {**asdict(self), "stack_count": self.stack_count}
