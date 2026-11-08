"""Shared periodic distortion followed by mortar inset, independent of generation."""

from __future__ import annotations

from masonpy.models import Wall

from .field import distort_boundaries
from .inset import inset_stone
from .models import ShapeSettings, ShapedStone, ShapedWall, WallDescription
from .softening import soften_wall
from .topology import BoundaryTopology, build_topology, description_signature
from .validation import clipper, validate_arrangement


def shape_wall(
    wall: Wall | WallDescription,
    *,
    joint_width: float = 0.0,
    distortion: float = 0.0,
    seed: int = 1,
    variation_scale: float = 6.0,
    corner_softening: float = 0.0,
    topology: BoundaryTopology | None = None,
) -> ShapedWall:
    """Derive fractional contours from a logical source, committing nothing upstream.

    Distortion and softening zero retain the original rectangle arithmetic. Otherwise,
    shared T-junctions are displaced once, validated periodically, then inset.
    Consumed/split stones or overlaps reject the whole proposed result.
    """
    settings = ShapeSettings(
        joint_width, distortion, seed, variation_scale, corner_softening
    )
    source = WallDescription.from_wall(wall) if isinstance(wall, Wall) else wall
    if not source.stones:
        raise ValueError(
            "Generate or place at least one wall stone before applying Shape"
        )
    if settings.distortion == 0:
        stones = []
        inset = settings.joint_width / 2
        for stone in source.stones:
            limit = min(stone.width, stone.height)
            if settings.joint_width >= limit - 1e-10:
                raise ValueError(
                    f"Joint width consumes stone {stone.id}; use a value below {limit}"
                )
            x0, y0 = stone.x + inset, stone.y + inset
            x1, y1 = stone.x + stone.width - inset, stone.y + stone.height - inset
            stones.append(
                ShapedStone(stone.id, ((x0, y0), (x1, y0), (x1, y1), (x0, y1)))
            )
        return soften_wall(ShapedWall(source, stones=tuple(stones), settings=settings))
    if topology is None:
        topology = build_topology(source)
    elif topology.signature != description_signature(source):
        raise ValueError("Cached Shape topology does not match the source wall")
    boundaries, statistics = distort_boundaries(topology, settings)
    lib = clipper()
    try:
        validate_arrangement(boundaries, source.width, source.wrap_x)
        stones = tuple(inset_stone(stone, settings.joint_width) for stone in boundaries)
        if settings.joint_width:
            validate_arrangement(stones, source.width, source.wrap_x)
    except lib.ClipperException as error:
        raise ValueError(f"Polygon processing failed: {error}") from error
    return soften_wall(
        ShapedWall(source, stones=stones, settings=settings, statistics=statistics)
    )
