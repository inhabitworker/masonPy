"""Compact, validated parameter recipes without geometry or placement evidence."""

from __future__ import annotations

import json
import math
from typing import Any

from masonpy.generators.catalog import get_generator_definition
from masonpy.geometry.settings import validate_details
from masonpy.processing import ShapeSettings
from masonpy.records import MAX_RECORD_CELLS


DEFAULT_WALL_SETTINGS = {"generator": "running_bond", "width": 104, "height": 60}


DEFAULT_SHAPE_SETTINGS = {
    "joint_width": 0.2,
    "distortion": 0,
    "seed": 1,
    "variation_scale": 6,
    "corner_softening": 0,
}

DEFAULT_BUILD_SETTINGS = {
    "mode": "projected",
    "roundness": 0.25,
    "resolution": 8,
    "depth": 0.25,
    "primitive": "tube",
    "tube_thickness": 1,
    "depth_variation": 0,
    "detail_seed": 1,
    "bevel": 0,
}


def configuration(
    data: Any,
    shape_defaults: dict[str, Any] | None = None,
    build_defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve a recipe or extract parameters from a legacy specimen, without generating."""
    shape_defaults = (
        DEFAULT_SHAPE_SETTINGS if shape_defaults is None else shape_defaults
    )
    build_defaults = (
        DEFAULT_BUILD_SETTINGS if build_defaults is None else build_defaults
    )
    if not isinstance(data, dict):
        raise ValueError("Config JSON must be an object")
    try:
        json.dumps(data, allow_nan=False)
    except (ValueError, TypeError, RecursionError) as error:
        raise ValueError("Config must contain finite JSON values") from error
    generator = data.get("generator")
    if isinstance(generator, dict):
        wall = data.get("wall", {})
        if not isinstance(wall, dict):
            raise ValueError("Wall must be an object")
        recipe = dict(
            generator=generator.get("id"),
            width=wall.get("width"),
            height=wall.get("height"),
            parameters=generator.get("parameters"),
        )
    else:
        recipe = {
            key: data.get(key) for key in ("generator", "width", "height", "parameters")
        }
    for key in ("width", "height"):
        value = recipe[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"Wall {key} must be a positive integer")
    if recipe["width"] * recipe["height"] > MAX_RECORD_CELLS:
        raise ValueError("Config exceeds the four-million-cell limit")
    if not isinstance(recipe["generator"], str):
        raise ValueError("Config must name a generator")
    definition = get_generator_definition(recipe["generator"])
    _, recipe["parameters"] = definition.create(recipe["parameters"])
    shape = data.get("shape", {})
    build = data.get("build", {})
    if not isinstance(shape, dict) or not isinstance(build, dict):
        raise ValueError("Shape and 3D parameters must be objects")
    shape = ShapeSettings(**{**shape_defaults, **shape}).to_dict()
    if set(build) - set(build_defaults):
        raise ValueError("Unknown 3D parameter")
    build = {**build_defaults, **build}
    validate_details(build["depth_variation"], build["detail_seed"], build["bevel"])
    if build["mode"] not in ("flat", "projected") or build["primitive"] not in (
        "none",
        "solid",
        "tube",
    ):
        raise ValueError("Unknown 3D mapping or core")
    for key in ("roundness", "depth", "tube_thickness"):
        value = build[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"{key} must be a finite number")
    resolution = build["resolution"]
    if (
        isinstance(resolution, bool)
        or not isinstance(resolution, int)
        or not 1 <= resolution <= 64
    ):
        raise ValueError("3D resolution must be an integer from 1 to 64")
    if (
        not 0 <= build["roundness"] <= 1
        or build["depth"] < 0
        or build["tube_thickness"] <= 0
    ):
        raise ValueError("Invalid 3D roundness, depth or tube thickness")
    return {**recipe, "shape": shape, "build": build}
