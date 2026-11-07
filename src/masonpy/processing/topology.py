"""Sparse conforming boundaries, including T-junctions across periodic wall ends."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass
import math

from .models import WallDescription


@dataclass(frozen=True)
class SharedVertex:
    """A source junction in canonical coordinates and its local movement allowance."""

    x: int
    y: int
    allowance: float


@dataclass(frozen=True)
class VertexReference:
    """One stone's occurrence of a canonical vertex in an unwrapped horizontal period."""

    vertex: int
    period: int = 0


@dataclass(frozen=True)
class StoneBoundary:
    """Counter-clockwise references to the source junctions of one whole stone."""

    id: int
    vertices: tuple[VertexReference, ...]


@dataclass(frozen=True)
class BoundaryTopology:
    """Reusable topology for a particular logical description, independent of Shape settings."""

    signature: tuple
    width: int
    height: int
    wrap_x: bool
    vertices: tuple[SharedVertex, ...]
    stones: tuple[StoneBoundary, ...]
    inserted_vertices: int


def description_signature(source: WallDescription) -> tuple:
    """Identify geometry without relying on mutable traits or generator state."""
    return (
        source.width,
        source.height,
        source.wrap_x,
        tuple((s.id, s.x, s.y, s.width, s.height) for s in source.stones),
    )


def build_topology(source: WallDescription) -> BoundaryTopology:
    """Index source corners and insert every incident corner into each straight boundary.

    Modulo identity applies only to periodic descriptions. Vertex occurrences keep
    their period, so crossing stones remain whole and opposite ends share nodes.
    """
    rows, columns = defaultdict(set), defaultdict(set)
    width = source.width
    for stone in source.stones:
        for x in (stone.x, stone.x + stone.width):
            canonical = x % width if source.wrap_x else x
            for y in (stone.y, stone.y + stone.height):
                rows[y].add(canonical)
                columns[canonical].add(y)
    rows = {y: sorted(xs) for y, xs in rows.items()}
    columns = {x: sorted(ys) for x, ys in columns.items()}
    indices, coordinates, allowances, boundaries = {}, [], [], []

    def horizontal(y: int, left: int, right: int) -> list[tuple[int, int]]:
        """Find only indexed corners on the requested unwrapped horizontal span."""
        xs = rows[y]
        periods = (
            range(math.floor(left / width), math.floor(right / width) + 1)
            if source.wrap_x
            else (0,)
        )
        return [
            (x + period * width, y)
            for period in periods
            for x in xs[
                bisect_left(xs, left - period * width) : bisect_right(
                    xs, right - period * width
                )
            ]
        ]

    def vertical(x: int, bottom: int, top: int) -> list[tuple[int, int]]:
        """Find corners on a vertical edge, including those recorded in another period."""
        ys = columns[x % width if source.wrap_x else x]
        return [(x, y) for y in ys[bisect_left(ys, bottom) : bisect_right(ys, top)]]

    for stone in source.stones:
        x0, y0, x1, y1 = stone.x, stone.y, stone.x + stone.width, stone.y + stone.height
        sides = (
            horizontal(y0, x0, x1),
            vertical(x1, y0, y1),
            list(reversed(horizontal(y1, x0, x1))),
            list(reversed(vertical(x0, y0, y1))),
        )
        references = []
        for side in sides:
            for x, y in side[:-1]:
                canonical = x % width if source.wrap_x else x
                key = canonical, y
                if key not in indices:
                    indices[key] = len(coordinates)
                    coordinates.append(key)
                    allowances.append(float("inf"))
                index = indices[key]
                allowances[index] = min(
                    allowances[index], 0.25 * min(stone.width, stone.height)
                )
                references.append(
                    VertexReference(
                        index, (x - canonical) // width if source.wrap_x else 0
                    )
                )
        boundaries.append(StoneBoundary(stone.id, tuple(references)))
    return BoundaryTopology(
        description_signature(source),
        width,
        source.height,
        source.wrap_x,
        tuple(
            SharedVertex(x, y, allowance)
            for (x, y), allowance in zip(coordinates, allowances)
        ),
        tuple(boundaries),
        sum(len(s.vertices) - 4 for s in boundaries),
    )
