"""Perimeter-preserving planar and rounded-column projection; Y is up."""

from __future__ import annotations

import math
from collections import Counter
from bisect import bisect_right
from typing import Any

from masonpy.models import Stone, Wall
from masonpy.processing import ShapedStone, ShapedWall
from masonpy.processing.contours import EPSILON, clip_x, cross, triangulate

from .mesh import SurfaceMesh


class WallGeometry:
    """A configurable visual projection of a live wall, independent of its topology.

    Projected stones fold once, retaining their whole logical width and ID.
    A finite source may only be projected if its modulo coverage is compatible.
    """

    def __init__(
        self,
        wall: Wall | ShapedWall,
        *,
        mode: str = "flat",
        roundness: float = 0.0,
        resolution: int = 8,
        depth: float = 0.0,
    ) -> None:
        """Configure visual mapping only.

        Args:
            wall: Live logical source; all coordinates remain in grid units.
            mode: "flat" or "projected"; projection never changes occupancy.
            roundness: Square (0) through sampled cylinder (1).
            resolution: Facets per rounded corner, from 1 to 64.
            depth: Optional outward visual thickness; zero emits surfaces only."""
        self.shape = wall if isinstance(wall, ShapedWall) else None
        wall = wall.source.to_wall() if self.shape else wall
        if mode not in ("flat", "projected"):
            raise ValueError("mode must be flat or projected")
        for name, value in (("roundness", roundness), ("depth", depth)):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(f"{name} must be a finite number")
        if not 0 <= roundness <= 1 or not 0 <= depth <= wall.width:
            raise ValueError("roundness must be 0–1 and depth 0–wall width")
        if (
            isinstance(resolution, bool)
            or not isinstance(resolution, int)
            or not 1 <= resolution <= 64
        ):
            raise ValueError("resolution must be an integer from 1 to 64")
        self.wall, self.mode = wall, mode
        self.roundness, self.resolution, self.depth = roundness, resolution, depth
        points = []
        for quarter in range(4):
            angle = -quarter * math.pi / 2
            samples = range(resolution + 1) if roundness else (0,)
            for step in samples:
                theta = math.pi / 2 * (1 - step / resolution)
                x = 1 - roundness + roundness * math.cos(theta)
                z = 1 - roundness + roundness * math.sin(theta)
                point = (
                    x * math.cos(angle) - z * math.sin(angle),
                    x * math.sin(angle) + z * math.cos(angle),
                )
                if not points or math.dist(points[-1], point) > 1e-12:
                    points.append(point)
        if math.dist(points[-1], points[0]) < 1e-12:
            points.pop()
        perimeter = sum(
            math.dist(p, points[(i + 1) % len(points)]) for i, p in enumerate(points)
        )
        self.section = [
            (x * wall.width / perimeter, z * wall.width / perimeter) for x, z in points
        ]
        self.distances = [0.0]
        for i, point in enumerate(self.section):
            self.distances.append(
                self.distances[-1]
                + math.dist(point, self.section[(i + 1) % len(self.section)])
            )
        self.distances[-1] = float(wall.width)
        self._offsets = {0: self.section}

    def _offset_section(self, offset: float) -> list[tuple[float, float]]:
        """Return/cache a mitered parallel section for visual stone depth."""
        if offset in self._offsets:
            return self._offsets[offset]
        result = []
        for i, point in enumerate(self.section):
            previous, following = (
                self.section[i - 1],
                self.section[(i + 1) % len(self.section)],
            )
            normals = []
            for a, b in ((previous, point), (point, following)):
                length = math.dist(a, b)
                normals.append((-(b[1] - a[1]) / length, (b[0] - a[0]) / length))
            a, b = normals
            denominator = 1 + a[0] * b[0] + a[1] * b[1]
            result.append(
                (
                    point[0] + offset * (a[0] + b[0]) / denominator,
                    point[1] + offset * (a[1] + b[1]) / denominator,
                )
            )
        self._offsets[offset] = result
        return result

    @property
    def inradius(self) -> float:
        """Return the smallest centre-to-face distance of the sampled polygon."""
        return min(
            abs(a[0] * b[1] - a[1] * b[0]) / math.dist(a, b)
            for a, b in zip(self.section, self.section[1:] + self.section[:1])
        )

    def point(
        self, x: float, y: float, offset: float = 0.0
    ) -> tuple[float, float, float]:
        """Map a logical coordinate; offset is a mitered visual face offset."""
        if self.mode == "flat":
            return (x - self.wall.width / 2, y, offset)
        s = x % self.wall.width
        i = min(bisect_right(self.distances, s) - 1, len(self.section) - 1)
        t = (s - self.distances[i]) / (self.distances[i + 1] - self.distances[i])
        points = self.section if offset == 0 else self._offset_section(offset)
        a, b = points[i], points[(i + 1) % len(points)]
        return (a[0] + (b[0] - a[0]) * t, y, a[1] + (b[1] - a[1]) * t)

    def splits(self, start: float, width: float) -> list[float]:
        """Unwrapped distances: endpoints plus every intervening face/period cut."""
        end = start + width
        if self.mode == "flat":
            return [start, end]
        if width > self.wall.width and self.shape is None:
            raise ValueError("projected stones cannot exceed the perimeter")
        # A valid periodic contour can have a wider bounding box after shared
        # distortion (e.g. a full ring with a sloping cut). Coverage belongs to
        # the validated source/Shape, not to this temporary X extent.
        cuts = [start, end]
        for period in range(
            math.floor(start / self.wall.width), math.floor(end / self.wall.width) + 1
        ):
            for distance in self.distances[:-1]:
                value = distance + period * self.wall.width
                if start + 1e-10 < value < end - 1e-10:
                    cuts.append(value)
        return sorted(cuts)

    def stone_mesh(self, stone: Stone) -> SurfaceMesh:
        """Fold one whole stone at face/period cuts; positive depth adds a closed visual shell."""
        start, width = stone.x, stone.width
        cuts = self.splits(start, width)
        mesh = SurfaceMesh()
        y0, y1 = stone.y, stone.y + stone.height
        for left, right in zip(cuts, cuts[1:]):
            a, b = self.point(left, y0, self.depth), self.point(right, y0, self.depth)
            c, d = self.point(right, y1, self.depth), self.point(left, y1, self.depth)
            mesh.quad(a, b, c, d)
            mesh.edge(a, b)
            mesh.edge(d, c)
            if self.depth:
                e, f = self.point(left, y0), self.point(right, y0)
                g, h = self.point(right, y1), self.point(left, y1)
                mesh.quad(h, g, f, e)  # back
                mesh.quad(e, f, b, a)  # bottom
                mesh.quad(d, c, g, h)  # top
        # A full ring has no end faces or artificial seam outline.
        closed = self.mode == "projected" and math.isclose(
            width, self.wall.width, abs_tol=1e-10
        )
        if not closed:
            for distance, reverse in ((cuts[0], False), (cuts[-1], True)):
                a, b = (
                    self.point(distance, y0, self.depth),
                    self.point(distance, y1, self.depth),
                )
                mesh.edge(a, b)
                if self.depth:
                    c, d = self.point(distance, y1), self.point(distance, y0)
                    mesh.quad(*((d, c, b, a) if reverse else (a, b, c, d)))
        return mesh

    def contour_mesh(self, stone: ShapedStone) -> SurfaceMesh:
        """Triangulate arbitrary simple contours, cutting faces only at mapping facets.

        Front/back faces share strip intersections. Side walls follow only the
        original boundary, never internal triangulation or projection cuts.
        """
        mesh = SurfaceMesh()
        points = list(stone.vertices)
        triangles = triangulate(points)
        lo, hi = min(p[0] for p in points), max(p[0] for p in points)
        cuts = self.splits(lo, hi - lo)
        for triangle in triangles:
            for left, right in zip(cuts, cuts[1:]):
                piece = clip_x(
                    clip_x(triangle, left, keep_right=True), right, keep_right=False
                )
                if len(piece) < 3:
                    continue
                for i in range(1, len(piece) - 1):
                    face = (piece[0], piece[i], piece[i + 1])
                    # Scoring can create genuine microscopic corner pieces.
                    # Dropping these by a linear-coordinate epsilon leaves holes.
                    if cross(*face) <= EPSILON * EPSILON:
                        continue
                    index = len(mesh.vertices)
                    mesh.vertices.extend(self.point(x, y, self.depth) for x, y in face)
                    mesh.triangles.append((index, index + 1, index + 2))
                    if self.depth:
                        index = len(mesh.vertices)
                        mesh.vertices.extend(
                            self.point(x, y) for x, y in reversed(face)
                        )
                        mesh.triangles.append((index, index + 1, index + 2))
        boundaries = []
        for a, b in zip(points, points[1:] + points[:1]):
            ts = [0.0, 1.0]
            if abs(b[0] - a[0]) > EPSILON:
                ts += [
                    (cut - a[0]) / (b[0] - a[0])
                    for cut in cuts
                    if EPSILON < (cut - a[0]) / (b[0] - a[0]) < 1 - EPSILON
                ]
            ts.sort()
            for t0, t1 in zip(ts, ts[1:]):
                segment = tuple(
                    (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
                    for t in (t0, t1)
                )
                boundaries.append(segment)
        # Opposite periodic end edges of a full-ring contour are one joined seam.
        keys = []
        for a, b in boundaries:
            key = tuple(
                sorted(
                    (
                        tuple(round(v, 9) for v in self.point(*a)),
                        tuple(round(v, 9) for v in self.point(*b)),
                    )
                )
            )
            keys.append(key)
        counts = Counter(keys)
        for (a, b), key in zip(boundaries, keys):
            if self.mode == "projected" and counts[key] == 2:
                continue
            front_a, front_b = self.point(*a, self.depth), self.point(*b, self.depth)
            mesh.edge(front_a, front_b)
            if self.depth:
                back_a, back_b = self.point(*a), self.point(*b)
                # Sloping extruded edges can form nonplanar quads after mapping.
                # Choose the same diagonal for reversed/shared boundary segments,
                # so zero-mortar neighbours have coincident side surfaces.
                if a <= b:
                    mesh.quad(back_a, back_b, front_b, front_a)
                else:
                    mesh.quad(front_a, back_a, back_b, front_b)
        return mesh

    def primitive_mesh(
        self, kind: str = "solid", thickness: float = 0.5
    ) -> SurfaceMesh:
        """An independent capped core or open-ended tube; flat mode has no core."""
        if kind not in ("none", "solid", "tube"):
            raise ValueError("primitive must be none, solid or tube")
        mesh = SurfaceMesh()
        if kind == "none" or self.mode == "flat":
            return mesh
        if kind == "tube" and (
            isinstance(thickness, bool)
            or not isinstance(thickness, (int, float))
            or not math.isfinite(thickness)
            or not 0 < thickness < self.inradius
        ):
            raise ValueError(
                "tube thickness must be positive and smaller than the cross-section inradius"
            )
        for left, right in zip(self.distances, self.distances[1:]):
            a, b = self.point(left, 0), self.point(right, 0)
            c, d = (
                self.point(right, self.wall.height),
                self.point(left, self.wall.height),
            )
            mesh.quad(a, b, c, d)
            if kind == "solid":
                for triangle in ((a, (0, 0, 0), b), (d, c, (0, self.wall.height, 0))):
                    i = len(mesh.vertices)
                    mesh.vertices.extend(triangle)
                    mesh.triangles.append((i, i + 1, i + 2))
            else:
                # A similar inner section cannot invert small fillets when the
                # requested tube wall is thicker than their corner radius.
                scale = 1 - thickness / self.inradius
                e, f = (a[0] * scale, 0, a[2] * scale), (b[0] * scale, 0, b[2] * scale)
                g, h = (
                    (c[0] * scale, c[1], c[2] * scale),
                    (d[0] * scale, d[1], d[2] * scale),
                )
                mesh.quad(h, g, f, e)
                mesh.quad(e, f, b, a)
                mesh.quad(d, c, g, h)
        return mesh

    def to_dict(
        self, *, primitive: str = "none", tube_thickness: float = 0.5
    ) -> dict[str, Any]:
        """Return a JSON-ready representation of the current object or snapshot."""
        if self.mode == "projected":
            # Never disguise incompatible source coverage by clipping stones.
            from masonpy.analysis.grid import _occupancy_cells

            _occupancy_cells(self.wall, True)
        return {
            "mode": self.mode,
            "perimeter": self.wall.width,
            "coverage": "whole stones, perimeter modulo"
            if self.mode == "projected"
            else "whole stones, planar",
            "section": self.section if self.mode == "projected" else [],
            "stones": [
                {"id": s.id, **self.contour_mesh(s).to_dict()}
                for s in self.shape.stones
            ]
            if self.shape
            else [
                {"id": s.id, **self.stone_mesh(s).to_dict()} for s in self.wall.stones
            ],
            "primitive": self.primitive_mesh(primitive, tube_thickness).to_dict(),
        }
