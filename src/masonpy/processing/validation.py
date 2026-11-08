"""Fixed-precision simple-polygon and periodic positive-area overlap checks."""

from __future__ import annotations

from functools import lru_cache
import importlib

from .field import PRECISION
from .models import ShapedStone


@lru_cache(maxsize=1)
def clipper():
    """Load the dedicated clipping engine only when non-rectangular processing needs it."""
    try:
        return importlib.import_module("pyclipper")
    except ImportError as error:
        raise ValueError(
            "Polygon shaping and 3D bevels require Pyclipper; install project dependencies with python3 -m pip install -e ."
        ) from error


def fixed_path(stone: ShapedStone) -> list[tuple[int, int]]:
    """Convert floats to clipping coordinates, rejecting unsupported coordinate ranges."""
    path = [(round(x * PRECISION), round(y * PRECISION)) for x, y in stone.vertices]
    if any(abs(value) >= (1 << 61) for point in path for value in point):
        raise ValueError(f"Stone {stone.id} exceeds polygon clipping coordinate range")
    return path


def area2(path: list[tuple[int, int]]) -> int:
    """Compute signed double area with exact integer arithmetic."""
    return sum(a[0] * b[1] - a[1] * b[0] for a, b in zip(path, path[1:] + path[:1]))


def orientation(a, b, c) -> int:
    """Return signed orientation for three fixed-precision points."""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segments_touch(a, b, c, d) -> bool:
    """Detect crossings, overlaps or contacts between two closed segments exactly."""
    if max(a[0], b[0]) < min(c[0], d[0]) or max(c[0], d[0]) < min(a[0], b[0]):
        return False
    if max(a[1], b[1]) < min(c[1], d[1]) or max(c[1], d[1]) < min(a[1], b[1]):
        return False
    ab_c, ab_d = orientation(a, b, c), orientation(a, b, d)
    cd_a, cd_b = orientation(c, d, a), orientation(c, d, b)
    return ab_c * ab_d <= 0 and cd_a * cd_b <= 0


def validate_path(path: list[tuple[int, int]], stone_id: int) -> None:
    """Require one positively oriented simple boundary; collinear subdivisions are valid."""
    if len(path) < 3 or len(set(path)) != len(path) or area2(path) <= 0:
        raise ValueError(f"Stone {stone_id} collapses or reverses during shaping")
    edges = list(zip(path, path[1:] + path[:1]))
    for i, (a, b) in enumerate(edges):
        c = path[(i + 2) % len(path)]
        if (
            orientation(a, b, c) == 0
            and (b[0] - a[0]) * (c[0] - b[0]) + (b[1] - a[1]) * (c[1] - b[1]) <= 0
        ):
            raise ValueError(f"Stone {stone_id} has a folded boundary after distortion")
        for j in range(i + 1, len(edges)):
            if j == i + 1 or (i == 0 and j == len(edges) - 1):
                continue
            if segments_touch(a, b, *edges[j]):
                raise ValueError(f"Stone {stone_id} self-intersects after distortion")


def polygon_operation(subject, other, operation) -> list:
    """Run one exact-grid clipping operation without modifying either input boundary."""
    lib = clipper()
    engine = lib.Pyclipper()
    engine.AddPath(subject, lib.PT_SUBJECT, True)
    engine.AddPath(other, lib.PT_CLIP, True)
    return engine.Execute(operation, lib.PFT_NONZERO, lib.PFT_NONZERO)


def validate_arrangement(
    stones: tuple[ShapedStone, ...], width: int, wrap_x: bool
) -> None:
    """Reject positive-area overlaps, including periodic copies and self-overlap.

    An X sweep culls distant polygons and a relative-period key avoids checking
    the same pair repeatedly. Coincident shared boundaries have no area and are
    permitted before mortar is opened. No vertices are repaired or moved here.
    """
    paths = [fixed_path(stone) for stone in stones]
    items = []
    period_width = width * PRECISION
    for index, (stone, path) in enumerate(zip(stones, paths)):
        validate_path(path, stone.id)
        left, right = min(p[0] for p in path), max(p[0] for p in path)
        bottom, top = min(p[1] for p in path), max(p[1] for p in path)
        periods = (
            range(-(right // period_width), (period_width - left) // period_width + 1)
            if wrap_x
            else (0,)
        )
        for period in periods:
            offset = period * period_width
            if wrap_x and (right + offset <= 0 or left + offset >= period_width):
                continue
            items.append((left + offset, right + offset, bottom, top, index, period))
    active, seen = [], set()
    lib = clipper()
    for item in sorted(items):
        left, right, bottom, top, index, period = item
        active = [other for other in active if other[1] > left]
        for other in active:
            if other[3] <= bottom or top <= other[2]:
                continue
            j, jp = other[4], other[5]
            key = (index, j, jp - period) if index < j else (j, index, period - jp)
            if index == j:
                key = index, index, abs(period - jp)
            if key in seen:
                continue
            seen.add(key)
            a = [(x + period * period_width, y) for x, y in paths[index]]
            b = [(x + jp * period_width, y) for x, y in paths[j]]
            overlap = polygon_operation(a, b, lib.CT_INTERSECTION)
            if any(area2(path) != 0 for path in overlap):
                suffix = " across the periodic boundary" if period != jp else ""
                raise ValueError(
                    f"Shaping overlaps stones {stones[index].id} and {stones[j].id}{suffix}; reduce distortion"
                )
        active.append(item)
