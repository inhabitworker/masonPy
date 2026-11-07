"""Renderer-independent triangle and joint-outline buffers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SurfaceMesh:
    """Triangle vertices/indices plus line-segment endpoints, with no renderer dependency."""

    vertices: list[tuple[float, float, float]] = field(default_factory=list)
    triangles: list[tuple[int, int, int]] = field(default_factory=list)
    outlines: list[tuple[float, float, float]] = field(default_factory=list)

    def quad(
        self,
        a: tuple[float, float, float],
        b: tuple[float, float, float],
        c: tuple[float, float, float],
        d: tuple[float, float, float],
    ) -> None:
        """Counter-clockwise boundary viewed from the intended outside."""
        i = len(self.vertices)
        self.vertices.extend((a, b, c, d))
        self.triangles.extend(((i, i + 1, i + 2), (i, i + 2, i + 3)))

    def edge(
        self, a: tuple[float, float, float], b: tuple[float, float, float]
    ) -> None:
        """Append one visible outline segment as a pair of 3D endpoints."""
        self.outlines.extend((a, b))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation of the current object or snapshot."""
        return {
            "vertices": self.vertices,
            "triangles": self.triangles,
            "outlines": self.outlines,
        }
