"""Perimeter-preserving planar and rounded-column projection; Y is up."""

from __future__ import annotations

import math
import hashlib
from collections import Counter
from bisect import bisect_right
from typing import Any

from masonpy.models import Stone, Wall
from masonpy.processing import ShapedStone, ShapedWall
from masonpy.processing.contours import EPSILON, clip_x, cross, triangulate

from .mesh import SurfaceMesh
from .bevel import MAX_BEVEL_VERTICES, MAX_BUILD_TRIANGLES, validate_details


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
        depth_variation: float = 0.0,
        detail_seed: int = 1,
        bevel: float = 0.0,
    ) -> None:
        """Configure visual mapping only.

        Args:
            wall: Live logical source; all coordinates remain in grid units.
            mode: "flat" or "projected"; projection never changes occupancy.
            roundness: Square (0) through sampled cylinder (1).
            resolution: Facets per rounded corner, from 1 to 64.
            depth: Base outward thickness; zero emits surfaces only.
            depth_variation: Per-stone relative range, from zero through 0.9.
            detail_seed: Independent stable seed for depth samples keyed by stone ID.
            bevel: Exposed-front chamfer width; zero disables, unsafe widths reduce
                or retain an explicitly reported unbeveled base shell."""
        validate_details(depth_variation, detail_seed, bevel)
        self.depth_variation, self.detail_seed, self.bevel = (
            depth_variation,
            detail_seed,
            bevel,
        )
        self._treatments = {}
        self._offset_vectors = None
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
        self._source_widths = {s.id: s.width for s in wall.stones} if self.shape else {}
        self.roundness, self.resolution, self.depth = roundness, resolution, depth
        if self.bevel and self.depth:
            from masonpy.processing.validation import clipper

            clipper()  # Dependency errors are build errors, not per-stone fallbacks.
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
        if offset and (self.depth_variation or self.bevel):
            if self._offset_vectors is None:
                unit = self._offset_section(1)
                self._offset_vectors = [
                    (q[0] - p[0], q[1] - p[1]) for p, q in zip(self.section, unit)
                ]
            a, b = self.section[i], self.section[(i + 1) % len(self.section)]
            u, v = (
                self._offset_vectors[i],
                self._offset_vectors[(i + 1) % len(self.section)],
            )
            return (
                a[0] + (b[0] - a[0]) * t + offset * (u[0] + (v[0] - u[0]) * t),
                y,
                a[1] + (b[1] - a[1]) * t + offset * (u[1] + (v[1] - u[1]) * t),
            )
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

    def depth_for(self, stone_id: int) -> float:
        """Choose one bounded depth from logical identity, without consuming any RNG."""
        if not self.depth or not self.depth_variation:
            return self.depth
        digest = hashlib.blake2b(
            f"masonpy-depth:{self.detail_seed}:{stone_id}".encode(), digest_size=8
        ).digest()
        value = int.from_bytes(digest, "little") / ((1 << 64) - 1)
        return self.depth * (1 + self.depth_variation * (2 * value - 1))

    def stone_mesh(self, stone: Stone) -> SurfaceMesh:
        """Build one whole logical stone with deterministic depth and optional front bevel."""
        if not self.depth_variation and not self.bevel:
            return self._rectangular_mesh(stone, self.depth)
        contour = ShapedStone(
            stone.id,
            (
                (stone.x, stone.y),
                (stone.x + stone.width, stone.y),
                (stone.x + stone.width, stone.y + stone.height),
                (stone.x, stone.y + stone.height),
            ),
        )
        return self._treated_mesh(contour, stone)

    def contour_mesh(self, stone: ShapedStone) -> SurfaceMesh:
        """Preserve a shaped outline while independently treating its exposed extrusion."""
        if not self.depth_variation and not self.bevel:
            return self._contour_mesh(stone, self.depth)
        return self._treated_mesh(stone)

    def _treated_mesh(
        self, stone: ShapedStone, rectangle: Stone | None = None
    ) -> SurfaceMesh:
        """Validate optional treatments, reducing the bevel or retaining the base shell."""
        from masonpy.exporting import shell_triangles
        from .bevel import chamfer_mesh

        depth = self.depth_for(stone.id)
        record = dict(
            depth=depth,
            bevel=0.0,
            bevel_reduced=False,
            bevel_skipped=False,
            depth_fallback=False,
            bevel_note="",
        )
        self._treatments[stone.id] = record
        if self.bevel and depth:
            source_width = (
                rectangle.width if rectangle else self._source_widths.get(stone.id)
            )
            ring = self.mode == "projected" and source_width == self.wall.width
            span = min(
                max(p[i] for p in stone.vertices) - min(p[i] for p in stone.vertices)
                for i in (0, 1)
            )
            cap = min(self.bevel, depth * 0.45, span * 0.2)
            if not ring and len(stone.vertices) <= MAX_BEVEL_VERTICES:
                for attempt in range(6):
                    width = cap / 2**attempt
                    if width <= 1e-6:
                        break
                    try:
                        mesh = chamfer_mesh(self, stone, depth, width)
                        shell_triangles(mesh.to_dict(), 1)
                        record.update(
                            bevel=width,
                            bevel_reduced=width < self.bevel * (1 - 1e-9),
                            bevel_note=(
                                "Reduced after validation"
                                if attempt
                                else "Limited by depth/contour span"
                            )
                            if width < self.bevel * (1 - 1e-9)
                            else "",
                        )
                        return mesh
                    except ValueError:
                        continue
            record["bevel_skipped"] = True
            record["bevel_note"] = (
                "Full-ring seam"
                if ring
                else "Contour complexity limit"
                if len(stone.vertices) > MAX_BEVEL_VERTICES
                else "No valid chamfer within six attempts"
            )
        elif self.bevel:
            record["bevel_skipped"] = True
            record["bevel_note"] = "Zero extrusion depth"
        try:
            mesh = (
                self._rectangular_mesh(rectangle, depth)
                if rectangle
                else self._contour_mesh(stone, depth)
            )
        except ValueError as error:
            raise ValueError(
                f"Stone {stone.id}: invalid base geometry: {error}"
            ) from error
        if depth and (self.depth_variation or self.bevel):
            try:
                shell_triangles(mesh.to_dict(), 1)
            except ValueError as error:
                if depth == self.depth:
                    raise ValueError(
                        f"Stone {stone.id}: invalid base shell: {error}"
                    ) from error
                mesh = (
                    self._rectangular_mesh(rectangle, self.depth)
                    if rectangle
                    else self._contour_mesh(stone, self.depth)
                )
                try:
                    shell_triangles(mesh.to_dict(), 1)
                except ValueError as fallback_error:
                    raise ValueError(
                        f"Stone {stone.id}: invalid base shell: {fallback_error}"
                    ) from fallback_error
                record.update(depth=self.depth, depth_fallback=True)
        return mesh

    def _rectangular_mesh(self, stone: Stone, depth: float) -> SurfaceMesh:
        """Fold one whole stone at face/period cuts; positive depth adds a closed visual shell."""
        start, width = stone.x, stone.width
        cuts = self.splits(start, width)
        mesh = SurfaceMesh()
        y0, y1 = stone.y, stone.y + stone.height
        for left, right in zip(cuts, cuts[1:]):
            a, b = self.point(left, y0, depth), self.point(right, y0, depth)
            c, d = self.point(right, y1, depth), self.point(left, y1, depth)
            mesh.quad(a, b, c, d)
            mesh.edge(a, b)
            mesh.edge(d, c)
            if depth:
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
                    self.point(distance, y0, depth),
                    self.point(distance, y1, depth),
                )
                mesh.edge(a, b)
                if depth:
                    c, d = self.point(distance, y1), self.point(distance, y0)
                    mesh.quad(*((d, c, b, a) if reverse else (a, b, c, d)))
        return mesh

    def _contour_mesh(self, stone: ShapedStone, depth: float) -> SurfaceMesh:
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
                    mesh.vertices.extend(self.point(x, y, depth) for x, y in face)
                    mesh.triangles.append((index, index + 1, index + 2))
                    if depth:
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
            front_a, front_b = self.point(*a, depth), self.point(*b, depth)
            mesh.edge(front_a, front_b)
            if depth:
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
        self._treatments.clear()
        stones = []
        triangle_count = 0
        sources = self.shape.stones if self.shape else self.wall.stones
        for source in sources:
            mesh = self.contour_mesh(source) if self.shape else self.stone_mesh(source)
            triangle_count += len(mesh.triangles)
            if (
                self.depth_variation or self.bevel
            ) and triangle_count > MAX_BUILD_TRIANGLES:
                raise ValueError(
                    "3D detail build exceeds one million triangles; reduce mapping resolution or bevel"
                )
            stones.append({"id": source.id, **mesh.to_dict()})
        result = {
            "mode": self.mode,
            "perimeter": self.wall.width,
            "coverage": "whole stones, perimeter modulo"
            if self.mode == "projected"
            else "whole stones, planar",
            "section": self.section if self.mode == "projected" else [],
            "stones": stones,
            "primitive": self.primitive_mesh(primitive, tube_thickness).to_dict(),
        }
        if self.depth_variation or self.bevel:
            records = list(self._treatments.values())
            result["statistics"] = dict(
                depth_min=min((r["depth"] for r in records), default=0),
                depth_max=max((r["depth"] for r in records), default=0),
                beveled_stones=sum(r["bevel"] > 0 for r in records),
                reduced_bevel_ids=[
                    i for i, r in self._treatments.items() if r["bevel_reduced"]
                ],
                skipped_bevel_ids=[
                    i for i, r in self._treatments.items() if r["bevel_skipped"]
                ],
                depth_fallback_ids=[
                    i for i, r in self._treatments.items() if r["depth_fallback"]
                ],
                omitted_stones=0,
            )
            for stone in result["stones"]:
                stone["treatment"] = dict(self._treatments[stone["id"]])
        return result
