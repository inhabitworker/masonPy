"""Small polygon operations shared by contour processing and mesh construction."""

from __future__ import annotations

import math

Point = tuple[float, float]
EPSILON = 1e-10


def cross(a: Point, b: Point, c: Point) -> float:
    """Return the signed double area of the triangle a, b, c."""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def clean(points: list[Point]) -> list[Point]:
    """Remove consecutive duplicate points without removing useful boundary vertices."""
    result = []
    for point in points:
        if not result or math.dist(point, result[-1]) > EPSILON:
            result.append(point)
    if len(result) > 1 and math.dist(result[0], result[-1]) <= EPSILON:
        result.pop()
    return result


def clip_x(points: list[Point], value: float, *, keep_right: bool) -> list[Point]:
    """Clip a convex polygon against one vertical half-plane."""
    output = []
    for a, b in zip(points, points[1:] + points[:1]):
        inside_a = a[0] >= value if keep_right else a[0] <= value
        inside_b = b[0] >= value if keep_right else b[0] <= value
        if inside_a:
            output.append(a)
        if inside_a != inside_b:
            t = (value - a[0]) / (b[0] - a[0])
            output.append((value, a[1] + t * (b[1] - a[1])))
    return clean(output)


def triangulate(points: tuple[Point, ...] | list[Point]) -> list[list[Point]]:
    """Ear-clip a simple counter-clockwise polygon, retaining boundary subdivisions."""
    remaining = clean(list(points))
    if len(remaining) < 3 or any(not math.isfinite(v) for p in remaining for v in p):
        raise ValueError("contour must contain at least three finite vertices")
    area = sum(
        a[0] * b[1] - b[0] * a[1]
        for a, b in zip(remaining, remaining[1:] + remaining[:1])
    )
    if area <= EPSILON:
        raise ValueError(
            "contour must have positive area and counter-clockwise winding"
        )
    triangles = []

    def quality(a: Point, b: Point, c: Point) -> float:
        """Prefer substantial ears rather than near-collinear junction triangles."""
        squared_edges = (
            math.dist(a, b) ** 2 + math.dist(b, c) ** 2 + math.dist(c, a) ** 2
        )
        return cross(a, b, c) / squared_edges if squared_edges else 0.0

    while len(remaining) > 3:
        ears = []
        for i, b in enumerate(remaining):
            a, c = remaining[i - 1], remaining[(i + 1) % len(remaining)]
            if cross(a, b, c) <= EPSILON:
                continue
            others = [
                p
                for j, p in enumerate(remaining)
                if j not in (i, (i - 1) % len(remaining), (i + 1) % len(remaining))
            ]
            if any(
                min(cross(a, b, p), cross(b, c, p), cross(c, a, p)) >= -EPSILON
                for p in others
            ):
                continue
            score = quality(a, b, c)
            if len(remaining) == 4:
                rest = remaining[:i] + remaining[i + 1 :]
                if cross(*rest) <= EPSILON:
                    continue
                score = min(score, quality(*rest))
            ears.append((score, i))
        if not ears:
            raise ValueError(
                "contour cannot be triangulated without crossing its boundary"
            )
        _, i = max(ears, key=lambda ear: (ear[0], -ear[1]))
        triangles.append(
            [remaining[i - 1], remaining[i], remaining[(i + 1) % len(remaining)]]
        )
        remaining.pop(i)
    if cross(*remaining) <= EPSILON:
        raise ValueError("contour contains a degenerate triangle")
    triangles.append(remaining)
    return triangles
