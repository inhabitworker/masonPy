# ruff: noqa: E402
# SPDX-License-Identifier: GPL-3.0-or-later
"""MasonPy Add Masonry: saved recipes and labelled scene geometry."""

# Blender's Reload Scripts reloads this entry point; refresh dependencies in order.
_needs_reload = "bpy" in locals()

import bpy
from bpy.props import PointerProperty

from . import build, properties, mesh, ui, operators

if _needs_reload:
    import importlib

    for module in (build, properties, mesh, ui, operators):
        importlib.reload(module)

_CLASSES = (
    properties.MasonrySettings,
    operators.MESH_OT_add_masonry,
    operators.MESH_OT_regenerate_masonry,
    ui.VIEW3D_PT_masonry,
)


def menu_add(self, context):
    """Expose the extension through Blender's standard Add Mesh menu."""
    self.layout.operator("mesh.add_masonry", text="Masonry", icon="MESH_CUBE")


def register():
    """Register host classes and persistent object settings."""
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Object.masonry = PointerProperty(type=properties.MasonrySettings)
    bpy.types.Object.masonry_owner = PointerProperty(type=bpy.types.Object)
    bpy.types.VIEW3D_MT_mesh_add.append(menu_add)


def unregister():
    """Remove UI callbacks and RNA types without removing generated scene geometry."""
    bpy.types.VIEW3D_MT_mesh_add.remove(menu_add)
    del bpy.types.Object.masonry_owner
    del bpy.types.Object.masonry
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
