"""Host-independent triangle and joint-outline buffers in grid units, with Y up.

Vertices may repeat across faces. This is a surface representation, not a welded
editable mesh. Host adapters must establish connectivity within each stone while
keeping different stone IDs separate; outlines are display data, not mesh edges.
Face roles are assigned at construction and serialized only when requested.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SurfaceMesh:
    """Triangle vertices/indices plus line-segment endpoints, with no renderer dependency."""

    vertices: list[tuple[float, float, float]] = field(default_factory=list)
    triangles: list[tuple[int, int, int]] = field(default_factory=list)
    outlines: list[tuple[float, float, float]] = field(default_factory=list)
    face_roles: list[str] = field(default_factory=list)

    def quad(
        self,
        a: tuple[float, float, float],
        b: tuple[float, float, float],
        c: tuple[float, float, float],
        d: tuple[float, float, float],
        *,
        role: str = "side",
    ) -> None:
        """Counter-clockwise boundary viewed from the intended outside."""
        i = len(self.vertices)
        self.vertices.extend((a, b, c, d))
        self.triangles.extend(((i, i + 1, i + 2), (i, i + 2, i + 3)))
        self.face_roles.extend((role, role))

    def edge(
        self, a: tuple[float, float, float], b: tuple[float, float, float]
    ) -> None:
        """Append one visible outline segment as a pair of 3D endpoints."""
        self.outlines.extend((a, b))

    def to_dict(self, *, include_roles: bool = False) -> dict[str, Any]:
        """Return a JSON-ready representation of the current object or snapshot."""
        result = {
            "vertices": self.vertices,
            "triangles": self.triangles,
            "outlines": self.outlines,
        }

        if include_roles:
            if len(self.face_roles) != len(self.triangles):
                raise ValueError("Mesh face roles do not match triangles")
            result["face_roles"] = self.face_roles
        return result
