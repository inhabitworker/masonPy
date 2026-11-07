"""Data-driven catalogue shared by applications that configure generators."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from masonpy.generators.ashlar import AshlarGenerator
from masonpy.generators.brick import (
    EnglishBondGenerator,
    FlemishBondGenerator,
    RunningBondGenerator,
    StackBondGenerator,
)
from masonpy.generators.interface import WallGenerator


@dataclass(frozen=True, slots=True)
class GeneratorParameter:
    """One generator-specific form field: label, numeric bounds, default and advanced/toggle hints."""

    id: str
    label: str
    default: int | float
    minimum: int = 1
    step: int | float = 1
    description: str = ""
    advanced: bool = False
    toggle: bool = False
    maximum: int | float | None = None
    numeric_type: str = "integer"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation of the current object or snapshot."""
        return {
            "id": self.id,
            "label": self.label,
            "type": self.numeric_type,
            "maximum": self.maximum,
            "default": self.default,
            "minimum": self.minimum,
            "step": self.step,
            "description": self.description,
            "advanced": self.advanced,
            "toggle": self.toggle,
        }


@dataclass(frozen=True, slots=True)
class GeneratorDefinition:
    """Associate a generator implementation with its category and parameter schema."""

    id: str
    label: str
    category: str
    generator_type: type[WallGenerator]
    parameters: tuple[GeneratorParameter, ...]

    def resolve_parameters(
        self, values: dict[str, Any] | None = None
    ) -> dict[str, int | float]:
        """Apply schema defaults and validate supplied numeric values; unknown fields raise ValueError."""
        if values is not None and not isinstance(values, dict):
            raise ValueError("generator parameters must be an object")
        supplied = values or {}
        expected = {parameter.id for parameter in self.parameters}
        unknown = set(supplied) - expected
        if unknown:
            raise ValueError(
                f"unknown parameters for {self.id}: {', '.join(sorted(unknown))}"
            )

        resolved: dict[str, int | float] = {}
        for parameter in self.parameters:
            value = supplied.get(parameter.id, parameter.default)
            allowed = (int,) if parameter.numeric_type == "integer" else (int, float)
            if (
                not isinstance(value, allowed)
                or isinstance(value, bool)
                or not math.isfinite(value)
            ):
                raise ValueError(
                    f"{parameter.id} must be a finite {parameter.numeric_type}"
                )
            if value < parameter.minimum or (
                parameter.maximum is not None and value > parameter.maximum
            ):
                raise ValueError(f"{parameter.id} is outside its allowed range")
            resolved[parameter.id] = value
        return resolved

    def create(
        self, values: dict[str, Any] | None = None
    ) -> tuple[WallGenerator, dict[str, int | float]]:
        """Return a configured generator and the resolved parameter values used to construct it."""
        parameters = self.resolve_parameters(values)
        return self.generator_type(**parameters), parameters

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation of the current object or snapshot."""
        return {
            "id": self.id,
            "label": self.label,
            "category": self.category,
            "parameters": [parameter.to_dict() for parameter in self.parameters],
        }


BRICK_HEIGHT = GeneratorParameter(
    "brick_height", "Brick height", 2, description="Course height in grid units."
)
COURSE_OFFSET = GeneratorParameter(
    "course_offset",
    "Cumulative course offset",
    0,
    minimum=-1000000,
    description="Additional phase per course in grid units, modulo its pattern width.",
    advanced=True,
)
STRETCHER_WIDTH = GeneratorParameter(
    "stretcher_width",
    "Stretcher width",
    4,
    description="Long-face width in grid units.",
)
HEADER_WIDTH = GeneratorParameter(
    "header_width",
    "Header width",
    2,
    minimum=2,
    step=2,
    description="Short-face width; even values permit half-header offsets.",
)

GENERATOR_DEFINITIONS = (
    GeneratorDefinition(
        id="running_bond",
        label="Running bond",
        category="Brick",
        generator_type=RunningBondGenerator,
        parameters=(STRETCHER_WIDTH, BRICK_HEIGHT, COURSE_OFFSET),
    ),
    GeneratorDefinition(
        id="stack_bond",
        label="Stack bond",
        category="Brick",
        generator_type=StackBondGenerator,
        parameters=(STRETCHER_WIDTH, BRICK_HEIGHT, COURSE_OFFSET),
    ),
    GeneratorDefinition(
        id="english_bond",
        label="English bond",
        category="Brick",
        generator_type=EnglishBondGenerator,
        parameters=(STRETCHER_WIDTH, HEADER_WIDTH, BRICK_HEIGHT, COURSE_OFFSET),
    ),
    GeneratorDefinition(
        id="flemish_bond",
        label="Flemish bond",
        category="Brick",
        generator_type=FlemishBondGenerator,
        parameters=(STRETCHER_WIDTH, HEADER_WIDTH, BRICK_HEIGHT, COURSE_OFFSET),
    ),
    GeneratorDefinition(
        id="ashlar",
        label="Ashlar",
        category="Stone",
        generator_type=AshlarGenerator,
        parameters=(
            GeneratorParameter(
                "coursing_factor",
                "Coursing factor",
                0.5,
                minimum=0,
                maximum=1,
                step=0.1,
                description="0 discourages horizontal continuity/alignment; 1 encourages it. Bonding retains priority.",
                advanced=True,
                numeric_type="number",
            ),
            GeneratorParameter(
                "enforce_stack",
                "Limit vertical joint stacks",
                1,
                minimum=0,
                advanced=True,
                toggle=True,
            ),
            GeneratorParameter(
                "max_joint_stack",
                "Maximum vertical joint stack",
                2,
                advanced=True,
            ),
            GeneratorParameter(
                "allow_snecks",
                "Allow snecks",
                1,
                minimum=0,
                maximum=1,
                description="Permit bounded closing stones below the ordinary minima, including small corner closers.",
                toggle=True,
            ),
            GeneratorParameter(
                "snecking_factor",
                "Sneck preference",
                0.2,
                minimum=0,
                maximum=1,
                step=0.1,
                description="0 uses snecks only when needed; higher values encourage useful deliberate snecks. Allow snecks controls permission.",
                numeric_type="number",
            ),
            GeneratorParameter(
                "min_sneck_size",
                "Minimum sneck size",
                1,
                description="Smallest closing width or height in grid units; no larger than either ordinary minimum.",
                advanced=True,
            ),
            GeneratorParameter(
                "jitter_start",
                "Jitter first stone",
                1,
                minimum=0,
                description="Randomize the first stone's horizontal position on the circular skyline.",
                advanced=True,
                toggle=True,
            ),
            GeneratorParameter(
                "min_stone_width",
                "Minimum stone width",
                3,
                description="Smallest preferred stone width in grid units.",
            ),
            GeneratorParameter(
                "max_stone_width",
                "Maximum stone width",
                8,
                description="Hard maximum width for ordinary stones and snecks, in grid units.",
            ),
            GeneratorParameter(
                "min_stone_height",
                "Minimum stone height",
                2,
                description="Smallest preferred stone height in grid units.",
            ),
            GeneratorParameter(
                "max_stone_height",
                "Maximum stone height",
                5,
                description="Hard maximum height for ordinary stones and snecks, in grid units.",
            ),
            GeneratorParameter(
                "seed",
                "Random seed",
                1,
                minimum=0,
                description="Change this value to produce another repeatable pattern.",
                advanced=True,
            ),
        ),
    ),
)

_DEFINITIONS_BY_ID = {definition.id: definition for definition in GENERATOR_DEFINITIONS}


def get_generator_definition(generator_id: str) -> GeneratorDefinition:
    """Look up a generator ID; unknown IDs raise ValueError."""
    try:
        return _DEFINITIONS_BY_ID[generator_id]
    except KeyError as error:
        raise ValueError(f"unknown generator: {generator_id}") from error
