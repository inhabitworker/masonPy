"""Whole logical stones; rendering never splits their identity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Stone:
    """An axis-aligned stone measured in abstract integer grid units."""

    id: int
    x: int
    y: int
    width: int
    height: int
    traits: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation of the current object or snapshot."""
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "traits": dict(self.traits),
        }
