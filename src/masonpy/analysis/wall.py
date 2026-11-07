"""Live wall inspection: statistics and local geometry, without cached policy."""

from __future__ import annotations

from collections import Counter
from fractions import Fraction
from typing import Any, Sequence

from masonpy.models import ExposedEdge, HorizontalJoint, Stone, VerticalSeam, Wall

from .grid import _horizontal_runs, _occupancy_cells
from .joints import horizontal_joints, vertical_seams
from .skyline import resulting_plateau


class WallAnalysis:
    """A live computed view. Each query reads current geometry, with no cache.

    Horizontal topology follows the wall unless explicitly overridden. Returned
    records/statistics are snapshots; query again after placement or undo.
    """

    def __init__(self, wall: Wall, *, wrap_x: bool | None = None) -> None:
        """Keep a live wall reference and an optional logical-topology override; queries recompute."""
        self.wall = wall
        self._wrap_override = wrap_x

    @property
    def wrap_x(self) -> bool:
        """Return the analysis topology override, or follow the wall when unset."""
        return self.wall.wrap_x if self._wrap_override is None else self._wrap_override

    def _cells(self) -> list[list[int | None]]:
        """Return validated finite or modulo occupancy for this analysis query."""
        return _occupancy_cells(self.wall, self.wrap_x)

    def _cell(
        self, cells: Sequence[Sequence[int | None]], x: int, y: int
    ) -> int | None:
        """Read one logical cell; outside finite or vertical bounds returns None."""
        if y < 0 or y >= self.wall.height:
            return None
        if self.wrap_x:
            x %= self.wall.width
        return cells[y][x] if 0 <= x < self.wall.width else None

    def surface(self) -> tuple[tuple[int, ...], tuple[int | None, ...]]:
        """Return skyline heights and the logical stone IDs at those tops."""
        cells = self._cells()
        heights, owners = [], []
        for x in range(self.wall.width):
            top = next(
                (
                    y + 1
                    for y in range(self.wall.height - 1, -1, -1)
                    if cells[y][x] is not None
                ),
                0,
            )
            heights.append(top)
            owners.append(cells[top - 1][x] if top else None)
        return tuple(heights), tuple(owners)

    def skyline(self) -> tuple[int, ...]:
        """Return the highest occupied elevation in each logical column."""
        return self.surface()[0]

    def stone_at(self, x: int, y: int) -> Stone | None:
        """Return the stone occupying a cell, or None for empty/outside space."""
        stone_id = self._cell(self._cells(), x, y)
        return next((s for s in self.wall.stones if s.id == stone_id), None)

    def neighbours(
        self, x: int, y: int, width: int, height: int = 1
    ) -> dict[str, tuple[Stone, ...]]:
        """Stones touching each side of a query rectangle, deduplicated by ID."""
        if width < 1 or height < 1 or (self.wrap_x and width > self.wall.width):
            raise ValueError(
                "query dimensions must be positive and fit the circumference"
            )
        cells = self._cells()
        sides = {
            "left": [(x - 1, row) for row in range(y, y + height)],
            "right": [(x + width, row) for row in range(y, y + height)],
            "below": [(column, y - 1) for column in range(x, x + width)],
            "above": [(column, y + height) for column in range(x, x + width)],
        }
        if self.wrap_x and width == self.wall.width:
            sides["left"] = sides["right"] = []
        by_id = {s.id: s for s in self.wall.stones}
        return {
            side: tuple(
                by_id[i]
                for i in sorted(
                    {self._cell(cells, cx, cy) for cx, cy in positions} - {None}
                )
            )
            for side, positions in sides.items()
        }

    def joints_below(self, x: int, y: int, width: int) -> tuple[int, ...]:
        """Joint x positions strictly inside a span, in traversal order."""
        if width < 1 or (self.wrap_x and width > self.wall.width):
            raise ValueError("query width must be positive and fit the circumference")
        cells = self._cells()
        positions = []
        for distance in range(1, width):
            column = x + distance
            left, right = (
                self._cell(cells, column - 1, y - 1),
                self._cell(cells, column, y - 1),
            )
            if left is not None and right is not None and left != right:
                positions.append(column % self.wall.width if self.wrap_x else column)
        return tuple(positions)

    def adjoining_ids_below(
        self, x: int, y: int
    ) -> tuple[frozenset[int], frozenset[int]]:
        """IDs on both sides of the uninterrupted completed joint below (x,y)."""
        cells = self._cells()
        left_ids, right_ids = set(), set()
        for row in range(min(y, self.wall.height) - 1, -1, -1):
            left, right = self._cell(cells, x - 1, row), self._cell(cells, x, row)
            if left is None or right is None or left == right:
                break
            left_ids.add(left)
            right_ids.add(right)
        return frozenset(left_ids), frozenset(right_ids)

    def plateau_after(self, stone: Stone) -> tuple[int, int]:
        """Describe a candidate's top run; occupancy validity is a separate concern."""
        if not self.wrap_x:
            raise ValueError(
                "hypothetical plateau query currently requires a periodic wall"
            )
        if not 0 < stone.width <= self.wall.width:
            raise ValueError("candidate must fit the circumference")
        return resulting_plateau(*self.surface(), stone)

    def vertical_seams(self) -> tuple[VerticalSeam, ...]:
        """Return maximal completed vertical joints using this view's topology."""
        return vertical_seams(self.wall, wrap_x=self.wrap_x)

    def alignment_after(
        self,
        stone: Stone,
        *,
        surface: tuple[Sequence[int], Sequence[int | None]] | None = None,
        joints: Sequence[HorizontalJoint] | None = None,
    ) -> dict[str, int]:
        """Separate connected skyline growth from remote same-elevation geometry.

        Optional snapshots let a caller compare many candidates against one wall
        state. Joint length describes completed joints, not hypothetical ones.
        """
        if not self.wrap_x:
            raise ValueError("alignment query currently requires a periodic wall")
        if not 0 < stone.width <= self.wall.width:
            raise ValueError("candidate must fit the circumference")
        heights, owners = self.surface() if surface is None else surface
        extent, count = resulting_plateau(heights, owners, stone)
        footprint = {(stone.x + dx) % self.wall.width for dx in range(stone.width)}
        top = stone.y + stone.height
        aligned = sum(h == top and x not in footprint for x, h in enumerate(heights))
        runs = self.horizontal_joints() if joints is None else joints
        same_height = [run for run in runs if run.y == top]
        connected_joint = sum(
            run.length
            for run in same_height
            if (run.x + run.length) % self.wall.width == stone.x % self.wall.width
            or run.x % self.wall.width == (stone.x + stone.width) % self.wall.width
        )
        joint_length = sum(run.length for run in same_height)
        return {
            "plateau_extent": extent,
            "plateau_stones": count,
            "connected_extension": extent - stone.width,
            "disconnected_skyline_length": aligned - (extent - stone.width),
            "existing_joint_length": joint_length,
            "connected_joint_length": connected_joint,
            "disconnected_joint_length": joint_length - connected_joint,
        }

    def horizontal_joints(
        self, elevation: int | None = None
    ) -> tuple[HorizontalJoint, ...]:
        """Return maximal completed horizontal runs, optionally at one elevation."""
        return tuple(
            run
            for run in horizontal_joints(self.wall, wrap_x=self.wrap_x)
            if elevation is None or run.y == elevation
        )

    def exposed_edges(self) -> tuple[ExposedEdge, ...]:
        """Maximal occupied/empty edges, including finite exterior boundaries."""
        cells = self._cells()
        edges = []
        for side, delta in (("bottom", -1), ("top", 1)):
            for y in range(self.wall.height):
                mask = [
                    cells[y][x] is not None and self._cell(cells, x, y + delta) is None
                    for x in range(self.wall.width)
                ]
                edges.extend(
                    ExposedEdge(x, y + (side == "top"), length, side)
                    for x, length in _horizontal_runs(mask, self.wrap_x)
                )
        for side, delta in (("left", -1), ("right", 1)):
            for x in range(self.wall.width):
                mask = [
                    cells[y][x] is not None and self._cell(cells, x + delta, y) is None
                    for y in range(self.wall.height)
                ]
                boundary = x + (side == "right")
                if self.wrap_x:
                    boundary %= self.wall.width
                edges.extend(
                    ExposedEdge(boundary, y, length, side)
                    for y, length in _horizontal_runs(mask, False)
                )
        return tuple(edges)

    def statistics(self) -> dict[str, Any]:
        """Describe whole-stone size frequencies, sneck usage and completed joint runs."""
        stones = self.wall.stones
        count = len(stones)
        widths = Counter(s.width for s in stones)
        heights = Counter(s.height for s in stones)
        dimensions = Counter((s.width, s.height) for s in stones)
        ratios = Counter(Fraction(s.width, s.height) for s in stones)
        snecks = sum(bool(s.traits.get("is_sneck")) for s in stones)
        vertical = self.vertical_seams()
        horizontal = self.horizontal_joints()
        length_counts = Counter(run.length for run in horizontal)
        elevations = sorted({run.y for run in horizontal})
        return {
            "stone_count": count,
            "average_width": sum(s.width for s in stones) / count if count else 0,
            "average_height": sum(s.height for s in stones) / count if count else 0,
            "average_aspect_ratio": sum(s.width / s.height for s in stones) / count
            if count
            else 0,
            "width_distribution": [
                {"width": w, "count": n} for w, n in sorted(widths.items())
            ],
            "height_distribution": [
                {"height": h, "count": n} for h, n in sorted(heights.items())
            ],
            "dimension_distribution": [
                {"width": w, "height": h, "count": n}
                for (w, h), n in sorted(dimensions.items())
            ],
            "aspect_ratio_distribution": [
                {"ratio": float(r), "exact_ratio": str(r), "count": n}
                for r, n in sorted(ratios.items())
            ],
            "sneck_count": snecks,
            "sneck_proportion": snecks / count if count else 0,
            "max_vertical_stack": max((s.stack_count for s in vertical), default=0),
            "max_vertical_joint_length": max((s.length for s in vertical), default=0),
            "horizontal_joint_count": len(horizontal),
            "max_horizontal_joint_length": max(
                (run.length for run in horizontal), default=0
            ),
            "horizontal_length_distribution": [
                {"length": length, "count": n}
                for length, n in sorted(length_counts.items())
            ],
            "horizontal_by_elevation": [
                {
                    "y": y,
                    "run_count": sum(run.y == y for run in horizontal),
                    "total_length": sum(run.length for run in horizontal if run.y == y),
                    "lengths": [run.length for run in horizontal if run.y == y],
                }
                for y in elevations
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation of the current object or snapshot."""
        return {
            "statistics": self.statistics(),
            "vertical_seams": [s.to_dict() for s in self.vertical_seams()],
            "horizontal_joints": [run.to_dict() for run in self.horizontal_joints()],
        }

    def stone_info(self, stone_id: int) -> dict[str, Any]:
        """Current local geometry, distinct from the original placement decision."""
        stone = next((s for s in self.wall.stones if s.id == stone_id), None)
        if stone is None:
            raise ValueError(f"unknown stone: {stone_id}")
        neighbours = self.neighbours(stone.x, stone.y, stone.width, stone.height)
        cells = self._cells()
        heights, owners = self.surface()
        columns = [
            (stone.x + dx) % self.wall.width if self.wrap_x else stone.x + dx
            for dx in range(stone.width)
        ]
        columns = [x for x in columns if 0 <= x < self.wall.width]
        footprint = set(columns)
        horizontal = []
        for joint in self.horizontal_joints():
            if joint.y not in (stone.y, stone.y + stone.height):
                continue
            span = {
                (joint.x + dx) % self.wall.width if self.wrap_x else joint.x + dx
                for dx in range(joint.length)
            }
            overlap = len(footprint & span)
            if overlap:
                horizontal.append({**joint.to_dict(), "overlap_with_stone": overlap})
        return {
            "stone": stone.to_dict(),
            "geometry": {
                "area": stone.width * stone.height,
                "aspect_ratio": stone.width / stone.height,
                "top": stone.y + stone.height,
                "right": stone.x + stone.width,
                "crosses_reference_boundary": stone.x < 0
                or stone.x + stone.width > self.wall.width,
                "occupied_reference_cells": sum(row.count(stone.id) for row in cells),
            },
            "neighbours": {
                side: [s.to_dict() for s in stones]
                for side, stones in neighbours.items()
            },
            "supporting_joints": self.joints_below(stone.x, stone.y, stone.width),
            "adjoining_horizontal_joints": horizontal,
            "surface_over_footprint": [
                {"x": x, "top": heights[x], "stone_id": owners[x]} for x in columns
            ],
            "adjoining_vertical_seams": [
                seam.to_dict()
                for seam in self.vertical_seams()
                if seam.y < stone.y + stone.height
                and seam.y + seam.length > stone.y
                and seam.x
                in (
                    (
                        stone.x % self.wall.width,
                        (stone.x + stone.width) % self.wall.width,
                    )
                    if self.wrap_x
                    else (stone.x, stone.x + stone.width)
                )
            ],
        }
