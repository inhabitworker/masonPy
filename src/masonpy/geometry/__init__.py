"""Host-independent surfaces without mutation of logical stones or occupancy.

Projection, extrusion, detail controls and shell validation belong here. File
serialization and host mesh creation consume these results from outside this
package. Neither Blender APIs nor application sessions belong in this layer.
"""

from .mesh import SurfaceMesh
from .projection import WallGeometry

__all__ = ["SurfaceMesh", "WallGeometry"]
