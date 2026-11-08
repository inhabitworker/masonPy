"""Undoable Add Masonry and explicit regeneration without modifier management."""

import bpy
from bpy_extras.object_utils import AddObjectHelper, add_object_align_init

from .build import build_masonry
from .mesh import apply_result
from .properties import masonry_object, option_properties, recipe_from
from .ui import draw_options


def prepare(options):
    """Generate and validate all islands before any scene datablocks are replaced."""
    return build_masonry(
        recipe_from(options),
        output=options.output,
        use_shape=options.use_shape,
        unit_scale=options.unit_scale,
    )


class MESH_OT_add_masonry(bpy.types.Operator, AddObjectHelper):
    """Add labelled masonry at the cursor with an editable, saved generation recipe."""

    bl_idname = "mesh.add_masonry"
    bl_label = "Add Masonry"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and context.scene.library is None

    def draw(self, context):
        draw_options(self.layout, self)
        self.layout.prop(self, "align")
        self.layout.prop(self, "location")
        self.layout.prop(self, "rotation")

    def execute(self, context):
        try:
            result = prepare(self)
            obj = apply_result(
                context, self, result, matrix=add_object_align_init(context, self)
            )
        except (ValueError, TypeError, RuntimeError, OverflowError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        for selected in context.selected_objects:
            selected.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        self.report({"INFO"}, f"Added {result[3]['stone_count']} masonry stones")
        return {"FINISHED"}


MESH_OT_add_masonry.__annotations__ = option_properties()


class MESH_OT_regenerate_masonry(bpy.types.Operator):
    """Replace generated mesh and groups using saved settings; retain object placement."""

    bl_idname = "mesh.regenerate_masonry"
    bl_label = "Rebuild Masonry"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = masonry_object(context)
        return context.mode == "OBJECT" and obj is not None and obj.library is None

    def execute(self, context):
        obj = masonry_object(context)
        try:
            result = prepare(obj.masonry)
            apply_result(context, obj.masonry, result, obj=obj)
        except (ValueError, TypeError, RuntimeError, OverflowError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Rebuilt {result[3]['stone_count']} masonry stones")
        return {"FINISHED"}
