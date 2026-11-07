"""Renderer-independent 2D processing; discrete wall models remain unchanged."""

from .models import (
    ShapeSettings,
    ShapeStatistics,
    ShapedStone,
    ShapedWall,
    WallDescription,
)
from .shape import shape_wall
from .topology import BoundaryTopology, build_topology

__all__ = [
    "ShapeSettings",
    "ShapeStatistics",
    "ShapedStone",
    "ShapedWall",
    "WallDescription",
    "BoundaryTopology",
    "build_topology",
    "shape_wall",
]
