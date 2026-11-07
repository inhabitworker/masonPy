"""ExposedEdge: an immutable geometric analysis record in grid units."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ExposedEdge:
    """A maximal occupied/empty boundary; side names use logical wall orientation."""

    x: int
    y: int
    length: int
    side: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation of the current object or snapshot."""
        return asdict(self)
