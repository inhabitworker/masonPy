"""Shared operator/object properties populated from the core parameter catalogue."""

import json

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from masonpy.configuration import (
    DEFAULT_BUILD_SETTINGS,
    DEFAULT_SHAPE_SETTINGS,
    DEFAULT_WALL_SETTINGS,
)
from masonpy.generators.catalog import GENERATOR_DEFINITIONS, get_generator_definition


def option_properties():
    """Create fresh RNA definitions for both Add's redo panel and persistent settings."""
    shape, build, wall = (
        DEFAULT_SHAPE_SETTINGS,
        DEFAULT_BUILD_SETTINGS,
        DEFAULT_WALL_SETTINGS,
    )
    props = {
        "generator": EnumProperty(
            name="Pattern",
            items=[(g.id, g.label, g.category) for g in GENERATOR_DEFINITIONS],
            default=wall["generator"],
        ),
        "width": IntProperty(
            name="Width / perimeter", default=wall["width"], min=1, max=4_000_000
        ),
        "height": IntProperty(
            name="Height", default=wall["height"], min=1, max=4_000_000
        ),
        "output": EnumProperty(
            name="Geometry",
            items=[
                (
                    "SURFACE",
                    "2D surfaces",
                    "Mapped stone faces without thickness or backing",
                ),
                (
                    "SOLID",
                    "Extruded stones",
                    "Closed stone shells with optional backing",
                ),
            ],
            default="SOLID",
        ),
        "use_shape": BoolProperty(
            name="Apply Shape styling",
            default=True,
            description="Apply shared distortion, mortar inset and corner softening",
        ),
        "unit_scale": FloatProperty(
            name="Grid unit",
            default=0.1,
            min=0.000001,
            soft_max=1,
            subtype="DISTANCE",
            description="Size of one grid unit in Blender units; with metric scale 1 this is metres",
        ),
        "joint_width": FloatProperty(
            name="Mortar gap", default=shape["joint_width"], min=0, soft_max=1
        ),
        "distortion": FloatProperty(
            name="Distortion", default=shape["distortion"], min=0, max=1
        ),
        "corner_softening": FloatProperty(
            name="Corner softening", default=shape["corner_softening"], min=0, max=1
        ),
        "shape_seed": IntProperty(name="Shape seed", default=shape["seed"], min=0),
        "variation_scale": FloatProperty(
            name="Variation scale",
            default=shape["variation_scale"],
            min=0.25,
            soft_max=24,
        ),
        "mode": EnumProperty(
            name="Mapping",
            items=[
                ("flat", "Flat", "Planar masonry"),
                (
                    "projected",
                    "Column",
                    "Perimeter-preserving square to cylinder mapping",
                ),
            ],
            default=build["mode"],
        ),
        "roundness": FloatProperty(
            name="Roundness", default=build["roundness"], min=0, max=1
        ),
        "resolution": IntProperty(
            name="Corner resolution", default=build["resolution"], min=1, max=64
        ),
        "depth": FloatProperty(
            name="Stone depth", default=build["depth"], min=0, soft_max=2
        ),
        "depth_variation": FloatProperty(
            name="Depth variation", default=build["depth_variation"], min=0, max=0.9
        ),
        "detail_seed": IntProperty(
            name="Detail seed", default=build["detail_seed"], min=0
        ),
        "bevel": FloatProperty(
            name="Front chamfer", default=build["bevel"], min=0, soft_max=0.2
        ),
        "primitive": EnumProperty(
            name="Backing",
            items=[
                ("none", "None", "Stone geometry only"),
                ("solid", "Solid core", "Separate solid column core"),
                ("tube", "Tube core", "Separate hollow column core"),
            ],
            default=build["primitive"],
        ),
        "tube_thickness": FloatProperty(
            name="Core thickness",
            default=build["tube_thickness"],
            min=0.000001,
            soft_max=4,
        ),
        "show_advanced": BoolProperty(name="Advanced", default=False),
    }
    for definition in GENERATOR_DEFINITIONS:
        for parameter in definition.parameters:
            name = "gen_" + parameter.id
            if name in props:
                continue
            common = dict(name=parameter.label, description=parameter.description)
            if parameter.toggle:
                props[name] = BoolProperty(default=bool(parameter.default), **common)
            elif parameter.numeric_type == "number":
                props[name] = FloatProperty(
                    default=parameter.default,
                    min=parameter.minimum,
                    max=parameter.maximum if parameter.maximum is not None else 1e6,
                    **common,
                )
            else:
                props[name] = IntProperty(
                    default=parameter.default,
                    min=parameter.minimum,
                    max=parameter.maximum
                    if parameter.maximum is not None
                    else 1_000_000,
                    **common,
                )
    return props


OPTION_NAMES = tuple(option_properties())


def recipe_from(options):
    """Read only the selected generator's parameters, keeping inactive pattern drafts separate."""
    definition = get_generator_definition(options.generator)
    return dict(
        generator=options.generator,
        width=options.width,
        height=options.height,
        parameters={
            p.id: int(getattr(options, "gen_" + p.id))
            if p.toggle
            else getattr(options, "gen_" + p.id)
            for p in definition.parameters
        },
        shape={
            key: getattr(options, "shape_seed" if key == "seed" else key)
            for key in DEFAULT_SHAPE_SETTINGS
        },
        build={key: getattr(options, key) for key in DEFAULT_BUILD_SETTINGS},
    )


def snapshot(options):
    """Serialize the applied recipe and host choices for persistence and draft comparison."""
    return json.dumps(
        dict(
            recipe=recipe_from(options),
            output=options.output,
            use_shape=options.use_shape,
            unit_scale=options.unit_scale,
        ),
        sort_keys=True,
    )


def copy_options(source, target):
    """Copy values rather than RNA property definitions between independent owners."""
    for name in OPTION_NAMES:
        setattr(target, name, getattr(source, name))


class MasonrySettings(bpy.types.PropertyGroup):
    """Saved per-object drafts and the last successfully applied recipe."""

    is_masonry: BoolProperty(default=False, options={"HIDDEN"})
    applied_recipe: StringProperty(options={"HIDDEN"})
    core_object: PointerProperty(type=bpy.types.Object, options={"HIDDEN"})


MasonrySettings.__annotations__.update(option_properties())


def masonry_object(context):
    """Resolve either the selected masonry mesh or its owned backing to the editable root."""
    obj = context.object
    if obj and obj.type == "MESH" and obj.masonry.is_masonry:
        return obj
    if obj and obj.masonry_owner and obj.masonry_owner.masonry.is_masonry:
        return obj.masonry_owner
    return None
