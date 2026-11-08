"""Inherited source descriptions, applied contour settings and immutable results."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, asdict
import math
from typing import Any

from masonpy.models import Stone, Wall
from .contours import Point


@dataclass(frozen=True)
class ShapeSettings:
    """One reproducible configuration for shared distortion followed by mortar inset."""

    joint_width: float = 0.0
    distortion: float = 0.0
    seed: int = 1
    variation_scale: float = 6.0
    corner_softening: float = 0.0

    def __post_init__(self) -> None:
        """Reject invalid drafts before constructing topology or changing any applied result."""
        for name in (
            "joint_width",
            "distortion",
            "variation_scale",
            "corner_softening",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(f"{name.replace('_', ' ')} must be a finite number")
            object.__setattr__(self, name, float(value))
        if self.joint_width < 0:
            raise ValueError("joint width must be non-negative")
        if not 0 <= self.distortion <= 1:
            raise ValueError("distortion must be between 0 and 1")
        if not 0 <= self.corner_softening <= 1:
            raise ValueError("corner softening must be between 0 and 1")
        if self.variation_scale < 0.25:
            raise ValueError("variation scale must be at least 0.25 grid units")
        if (
            isinstance(self.seed, bool)
            or not isinstance(self.seed, int)
            or not 0 <= self.seed <= 2147483647
        ):
            raise ValueError("shape seed must be an integer from 0 to 2147483647")

    def to_dict(self) -> dict[str, Any]:
        """Serialize only processing parameters, suitable for an explicit apply request."""
        return asdict(self)


@dataclass(frozen=True)
class ShapeStatistics:
    """Deterministic processing diagnostics, never a source of placement decisions."""

    shared_vertices: int = 0
    inserted_vertices: int = 0
    max_displacement: float = 0.0
    coordinate_precision: float = 1e-7
    softened_stones: int = 0
    softening_reduced: int = 0
    softening_skipped: int = 0
    max_softening_radius: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Expose vertex counts and maximum pre-inset shared movement in grid units."""
        return asdict(self)


@dataclass(frozen=True)
class WallDescription:
    """Capture whole source stones independently of a live generation session."""

    width: int
    height: int
    resolution: int
    wrap_x: bool
    stones: tuple[Stone, ...]

    @classmethod
    def from_wall(cls, wall: Wall) -> WallDescription:
        """Copy the accepted logical description without changing occupancy or RNG state."""
        return cls(
            wall.width, wall.height, wall.resolution, wall.wrap_x, deepcopy(wall.stones)
        )

    def to_wall(self) -> Wall:
        """Reconstruct an independent wall for source analysis and projection validation."""
        wall = Wall(
            self.width, self.height, resolution=self.resolution, wrap_x=self.wrap_x
        )
        for stone in self.stones:
            wall.add_stone(deepcopy(stone))
        return wall

    def to_dict(self) -> dict[str, Any]:
        """Serialize the inherited discrete description without exposing internal traits."""
        return {
            "width": self.width,
            "height": self.height,
            "resolution": self.resolution,
            "wrap_x": self.wrap_x,
            "stones": [deepcopy(s.to_dict()) for s in self.stones],
        }


@dataclass(frozen=True)
class ShapedStone:
    """A whole stone's counter-clockwise boundary in unwrapped wall coordinates."""

    id: int
    vertices: tuple[Point, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialize contour coordinates while retaining the source identity."""
        return {"id": self.id, "vertices": self.vertices}


@dataclass(frozen=True, init=False)
class ShapedWall:
    """Applied contours with one settings object, source provenance and diagnostics.

    The original (source, joint_width, stones) constructor remains supported;
    new processing code passes settings explicitly as the single configuration.
    """

    source: WallDescription
    stones: tuple[ShapedStone, ...]
    settings: ShapeSettings
    statistics: ShapeStatistics
    unsoftened_stones: tuple[ShapedStone, ...] | None

    def __init__(
        self,
        source: WallDescription,
        joint_width: float | None = None,
        stones: tuple[ShapedStone, ...] = (),
        *,
        settings: ShapeSettings | None = None,
        statistics: ShapeStatistics | None = None,
        unsoftened_stones: tuple[ShapedStone, ...] | None = None,
    ) -> None:
        """Capture an applied result while preserving the original constructor contract."""
        if settings is None:
            settings = ShapeSettings(
                joint_width=0 if joint_width is None else joint_width
            )
        elif joint_width is not None and joint_width != settings.joint_width:
            raise ValueError("joint width disagrees with Shape settings")
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "stones", tuple(stones))
        object.__setattr__(self, "settings", settings)
        object.__setattr__(self, "statistics", statistics or ShapeStatistics())
        object.__setattr__(self, "unsoftened_stones", unsoftened_stones)

    @property
    def joint_width(self) -> float:
        """Retain the original joint-width accessor without duplicating applied settings."""
        return self.settings.joint_width

    def to_dict(self) -> dict[str, Any]:
        """Expose inherited source, reproducible settings and renderer-independent contours."""
        result = {
            "source": self.source.to_dict(),
            "joint_width": self.joint_width,
            "method": "shared-warp-v1",
            "settings": self.settings.to_dict(),
            "statistics": self.statistics.to_dict(),
            "stones": [stone.to_dict() for stone in self.stones],
        }
        if self.unsoftened_stones is not None:
            result["unsoftened_stones"] = [
                stone.to_dict() for stone in self.unsoftened_stones
            ]
        return result
