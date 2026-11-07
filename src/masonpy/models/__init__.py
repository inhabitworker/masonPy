"""Logical objects and immutable geometric records."""

from .errors import PlacementError
from .exposed_edge import ExposedEdge
from .horizontal_joint import HorizontalJoint
from .stone import Stone
from .vertical_seam import VerticalSeam
from .wall import Wall

__all__ = [
    "Stone",
    "Wall",
    "PlacementError",
    "VerticalSeam",
    "HorizontalJoint",
    "ExposedEdge",
]
