"""Core public API for MasonPy."""

from .analysis import (
    ExposedEdge,
    HorizontalJoint,
    VerticalSeam,
    WallAnalysis,
    horizontal_joints,
    report_vertical_seams,
    vertical_seams,
)
from .generators import (
    AshlarGenerator,
    EnglishBondGenerator,
    FlemishBondGenerator,
    GenerationEvent,
    RunningBondGenerator,
    StackBondGenerator,
    WallGenerator,
)
from .generators.errors import ConstructionFailure
from .geometry import SurfaceMesh, WallGeometry
from .models import PlacementError, Stone, Wall
from .processing import (
    ShapeSettings,
    ShapeStatistics,
    ShapedStone,
    ShapedWall,
    WallDescription,
    shape_wall,
)

__all__ = [
    "ShapeSettings",
    "ShapeStatistics",
    "ShapedStone",
    "ShapedWall",
    "WallDescription",
    "shape_wall",
    "WallGeometry",
    "SurfaceMesh",
    "WallAnalysis",
    "ExposedEdge",
    "HorizontalJoint",
    "horizontal_joints",
    "ConstructionFailure",
    "VerticalSeam",
    "vertical_seams",
    "report_vertical_seams",
    "GenerationEvent",
    "AshlarGenerator",
    "EnglishBondGenerator",
    "FlemishBondGenerator",
    "PlacementError",
    "RunningBondGenerator",
    "StackBondGenerator",
    "Stone",
    "Wall",
    "WallGenerator",
]
