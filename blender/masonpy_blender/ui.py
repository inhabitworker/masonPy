"""Add operator controls and persistent selected-object settings."""

import bpy
from masonpy.generators.catalog import get_generator_definition

from .properties import masonry_object, snapshot


def draw_options(layout, options):
    """Use the same core-backed fields in the redo region and the object panel."""
    layout.use_property_split = True
    layout.use_property_decorate = False
    layout.prop(options, "generator")
    layout.prop(options, "width")
    layout.prop(options, "height")
    layout.prop(options, "unit_scale")
    layout.prop(options, "output")
    definition = get_generator_definition(options.generator)
    box = layout.box()
    box.label(text="Wall pattern")
    for parameter in definition.parameters:
        if not parameter.advanced or options.show_advanced:
            box.prop(options, "gen_" + parameter.id)
    box = layout.box()
    box.prop(options, "use_shape")
    column = box.column()
    column.enabled = options.use_shape
    for name in ("joint_width", "distortion", "corner_softening"):
        column.prop(options, name)
    if options.show_advanced:
        column.prop(options, "shape_seed")
        column.prop(options, "variation_scale")
    box = layout.box()
    box.label(text="Mapping")
    box.prop(options, "mode")
    column = box.column()
    column.enabled = options.mode == "projected"
    column.prop(options, "roundness")
    column.prop(options, "resolution")
    box = layout.box()
    box.label(text="Extrusion / backing")
    box.enabled = options.output == "SOLID"
    for name in ("depth", "depth_variation", "bevel"):
        box.prop(options, name)
    if options.show_advanced:
        box.prop(options, "detail_seed")
    column = box.column()
    column.enabled = options.mode == "projected"
    column.prop(options, "primitive")
    row = column.row()
    row.enabled = options.primitive == "tube"
    row.prop(options, "tube_thickness")
    layout.prop(options, "show_advanced")


class VIEW3D_PT_masonry(bpy.types.Panel):
    """Keep object recipes available after the Add operator's redo panel disappears."""

    bl_label = "Masonry"
    bl_idname = "VIEW3D_PT_masonry"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Masonry"

    def draw(self, context):
        layout = self.layout
        obj = masonry_object(context)
        if obj is None:
            layout.operator("mesh.add_masonry", icon="MESH_CUBE")
            layout.label(text="Select masonry to edit its recipe")
            return
        options = obj.masonry
        column = layout.column()
        column.enabled = context.mode == "OBJECT" and obj.library is None
        column.label(text=f"{obj.name}: {obj.get('masonry_stone_count', 0)} stones")
        draw_options(column, options)
        dirty = snapshot(options) != options.applied_recipe
        column.label(
            text="Settings changed — rebuild to apply"
            if dirty
            else "Generated geometry is current",
            icon="INFO",
        )
        column.operator("mesh.regenerate_masonry", icon="FILE_REFRESH")
        column.label(text="Rebuild replaces mesh edits and weights", icon="INFO")
