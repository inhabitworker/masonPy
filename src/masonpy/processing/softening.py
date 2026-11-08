"""Bounded inward corner wear with short quadratic transition curves."""

from __future__ import annotations

from dataclasses import replace
import math

from .contours import triangulate
from .field import PRECISION
from .models import ShapedStone, ShapedWall
from .validation import (
    area2,
    clipper,
    fixed_path,
    polygon_operation,
    validate_arrangement,
    validate_path,
)


def _corner_path(path: list, radius: float) -> list[tuple[int, int]]:
    """Cut convex corners with short quadratic curves; retain concave/flat junctions.

    Trim lengths use a nominal fillet radius but cap at 40% of adjacent edges.
    Samples stop just inside the endpoints to keep quantized chords inside the
    original boundary. The maximum straight-edge retreat is 0.0001 * trim.
    """
    result = []
    for index, point in enumerate(path):
        before, after = path[index - 1], path[(index + 1) % len(path)]
        a = (before[0] - point[0], before[1] - point[1])
        b = (after[0] - point[0], after[1] - point[1])
        length_a, length_b = math.hypot(*a), math.hypot(*b)
        turn = -(a[0] * b[1] - a[1] * b[0]) / (length_a * length_b)
        if turn <= 0.05:
            result.append(tuple(point))
            continue
        cosine = max(-1, min(1, (a[0] * b[0] + a[1] * b[1]) / (length_a * length_b)))
        trim = min(
            radius * math.sqrt((1 + cosine) / max(1e-15, 1 - cosine)),
            length_a * 0.4,
            length_b * 0.4,
        )
        if trim < max(16, radius * 0.01):
            result.append(tuple(point))
            continue
        start = (a[0] * trim / length_a, a[1] * trim / length_a)
        end = (b[0] * trim / length_b, b[1] * trim / length_b)
        for t in (0.01, 0.25, 0.5, 0.75, 0.99):
            result.append(
                tuple(
                    round(point[i] + (1 - t) ** 2 * start[i] + t * t * end[i])
                    for i in (0, 1)
                )
            )
    return [point for index, point in enumerate(result) if point != result[index - 1]]


def soften_stone(
    stone: ShapedStone, strength: float
) -> tuple[ShapedStone, float, bool]:
    """Try a proportional corner radius, reducing it if containment/topology fails.

    Return the exact input on failure; no stone is fragmented, dropped or grown.
    The returned radius is nominal because quadratic curves approximate fillets.
    """
    lib = clipper()
    path = fixed_path(stone)
    span = min(max(p[i] for p in path) - min(p[i] for p in path) for i in (0, 1))
    requested = strength * span / 4
    for attempt in range(7):
        radius = round(requested / 2**attempt)
        if radius < 16:
            break
        try:
            result = _corner_path(path, radius)
            validate_path(result, stone.id)
            if abs(area2(path) - area2(result)) <= 2:
                return stone, 0, attempt > 0
            if any(
                area2(p) != 0
                for p in polygon_operation(result, path, lib.CT_DIFFERENCE)
            ):
                continue
            vertices = tuple((x / PRECISION, y / PRECISION) for x, y in result)
            triangulate(vertices)
            return ShapedStone(stone.id, vertices), radius / PRECISION, attempt > 0
        except (ValueError, lib.ClipperException):
            continue
    return stone, 0, True


def soften_wall(result: ShapedWall) -> ShapedWall:
    """Soften post-mortar contours, preserving every source ID and unsoftened profile."""
    strength = result.settings.corner_softening
    if not strength:
        return result
    full_rings = {
        stone.id
        for stone in result.source.stones
        if result.source.wrap_x and stone.width == result.source.width
    }
    stones = []
    softened = reduced = skipped = 0
    maximum = 0.0
    for stone in result.stones:
        # An unwrapped full ring has artificial end corners, not physical arrises.
        if stone.id in full_rings:
            shaped, radius, changed = stone, 0, False
        else:
            shaped, radius, changed = soften_stone(stone, strength)
        stones.append(shaped)
        if radius:
            softened += 1
            reduced += changed
            maximum = max(maximum, radius)
        else:
            skipped += 1
    stones = tuple(stones)
    validate_arrangement(stones, result.source.width, result.source.wrap_x)
    statistics = replace(
        result.statistics,
        softened_stones=softened,
        softening_reduced=reduced,
        softening_skipped=skipped,
        max_softening_radius=maximum,
    )
    return ShapedWall(
        result.source,
        stones=stones,
        settings=result.settings,
        statistics=statistics,
        unsoftened_stones=result.stones,
    )
