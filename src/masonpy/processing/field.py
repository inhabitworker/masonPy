"""Seeded periodic value noise evaluated once per shared boundary vertex."""

from __future__ import annotations

from functools import lru_cache
import math

from .models import ShapeSettings, ShapedStone, ShapeStatistics
from .topology import BoundaryTopology

# Fixed precision is a clipping detail, not a quantization to occupancy units.
PRECISION = 10_000_000
MASK = (1 << 64) - 1


def lattice_value(x: int, y: int, seed: int, channel: int) -> float:
    """Hash lattice coordinates into a stable signed value without any RNG state."""
    value = (
        (x * 0x9E3779B185EBCA87)
        ^ (y * 0xC2B2AE3D27D4EB4F)
        ^ (seed * 0x165667B19E3779F9)
        ^ (channel * 0x85EBCA77C2B2AE63)
    ) & MASK
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & MASK
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & MASK
    value ^= value >> 31
    return ((value >> 11) / ((1 << 53) - 1)) * 2 - 1


def distort_boundaries(
    topology: BoundaryTopology, settings: ShapeSettings
) -> tuple[tuple[ShapedStone, ...], ShapeStatistics]:
    """Move canonical nodes once, then restore each occurrence's unwrapped period.

    Movement is at most distortion * one quarter of the thinnest incident stone.
    Vertical movement tapers to zero at the wall's base/top; horizontal movement
    remains periodic at the seam. All stored coordinates are fractional floats.
    """
    cells = max(1, round(topology.width / settings.variation_scale))
    pitch = topology.width / cells if topology.wrap_x else settings.variation_scale

    @lru_cache(maxsize=None)
    def sample(x: int, y: int, channel: int) -> float:
        """Reuse lattice samples locally; wrapping is exact at the integer lattice index."""
        return lattice_value(
            x % cells if topology.wrap_x else x, y, settings.seed, channel
        )

    def noise(x: float, y: float, channel: int) -> float:
        """Smoothly interpolate a scalar channel in wall coordinates."""
        gx, gy = x / pitch, y / settings.variation_scale
        ix, iy = math.floor(gx), math.floor(gy)
        tx, ty = gx - ix, gy - iy
        tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
        a = sample(ix, iy, channel) * (1 - tx) + sample(ix + 1, iy, channel) * tx
        b = (
            sample(ix, iy + 1, channel) * (1 - tx)
            + sample(ix + 1, iy + 1, channel) * tx
        )
        return a * (1 - ty) + b * ty

    moved, maximum = [], 0.0
    for vertex in topology.vertices:
        amplitude = settings.distortion * vertex.allowance / math.sqrt(2)
        dx = amplitude * noise(vertex.x, vertex.y, 1)
        taper = (
            0
            if vertex.y in (0, topology.height)
            else math.sin(math.pi * vertex.y / topology.height)
        )
        dy = amplitude * noise(vertex.x, vertex.y, 2) * taper
        x, y = round((vertex.x + dx) * PRECISION), round((vertex.y + dy) * PRECISION)
        moved.append((x, y))
        maximum = max(
            maximum, math.hypot(x / PRECISION - vertex.x, y / PRECISION - vertex.y)
        )
    stones = tuple(
        ShapedStone(
            stone.id,
            tuple(
                (
                    (moved[ref.vertex][0] + ref.period * topology.width * PRECISION)
                    / PRECISION,
                    moved[ref.vertex][1] / PRECISION,
                )
                for ref in stone.vertices
            ),
        )
        for stone in topology.stones
    )
    return stones, ShapeStatistics(
        len(topology.vertices), topology.inserted_vertices, maximum
    )
