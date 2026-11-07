"""HorizontalJoint: an immutable geometric analysis record in grid units."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class HorizontalJoint:
    """A maximal occupied/occupied joint at y, over [x, x + length)."""

    x: int
    y: int
    length: int

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation of the current object or snapshot."""
        return asdict(self)
