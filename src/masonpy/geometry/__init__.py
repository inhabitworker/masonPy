"""Visual geometry only: no mutation of logical stones or occupancy."""

from .mesh import SurfaceMesh
from .projection import WallGeometry

__all__ = ["SurfaceMesh", "WallGeometry"]
