"""A bounded exposed-edge chamfer with corresponding outer and inset contours."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from masonpy.processing import ShapedStone
from masonpy.processing.contours import EPSILON, cross, triangulate
from masonpy.processing.validation import (
    clipper,
    fixed_path,
    polygon_operation,
    validate_path,
)

from .mesh import SurfaceMesh

if TYPE_CHECKING:
    from .projection import WallGeometry

MAX_BEVEL_VERTICES = 256
MAX_BEVEL_TRIANGLES = 12000
MAX_BUILD_TRIANGLES = 1_000_000


def inset_ring(stone: ShapedStone, width: float) -> ShapedStone:
    """Inset corresponding vertices, rejecting collapsed miters and folded bands."""
    outer = stone.vertices
    normals = []
    for a, b in zip(outer, outer[1:] + outer[:1]):
        length = math.dist(a, b)
        if length <= EPSILON:
            raise ValueError("Bevel encounters a zero-length edge")
        normals.append((-(b[1] - a[1]) / length, (b[0] - a[0]) / length))
    inner = []
    for i, point in enumerate(outer):
        a, b = normals[i - 1], normals[i]
        denominator = 1 + a[0] * b[0] + a[1] * b[1]
        if denominator <= 1e-8:
            raise ValueError("Bevel encounters a folded corner")
        delta = (
            width * (a[0] + b[0]) / denominator,
            width * (a[1] + b[1]) / denominator,
        )
        if math.hypot(*delta) > 4 * width:
            raise ValueError("Bevel miter exceeds its limit")
        inner.append((point[0] + delta[0], point[1] + delta[1]))
    result = ShapedStone(stone.id, tuple(inner))
    path = fixed_path(result)
    validate_path(path, stone.id)
    lib = clipper()
    try:
        outside = polygon_operation(path, fixed_path(stone), lib.CT_DIFFERENCE)
    except lib.ClipperException as error:
        raise ValueError(f"Bevel containment check failed: {error}") from error
    if outside:
        raise ValueError("Bevel inset leaves the stone footprint")
    for i, a in enumerate(outer):
        j = (i + 1) % len(outer)
        if (
            cross(a, outer[j], inner[j]) <= EPSILON
            or cross(a, inner[j], inner[i]) <= EPSILON
        ):
            raise ValueError("Bevel band collapses or folds")
    return result


def _clip(points: list, cut: float, keep_right: bool) -> list:
    """Clip a convex parameter-space face, interpolating height and extrusion depth."""
    output = []
    for a, b in zip(points, points[1:] + points[:1]):
        inside_a = a[0] >= cut if keep_right else a[0] <= cut
        inside_b = b[0] >= cut if keep_right else b[0] <= cut
        if inside_a:
            output.append(a)
        if inside_a != inside_b:
            t = (cut - a[0]) / (b[0] - a[0])
            output.append((cut, a[1] + t * (b[1] - a[1]), a[2] + t * (b[2] - a[2])))
    result = []
    for point in output:
        if not result or math.dist(point, result[-1]) > EPSILON:
            result.append(point)
    if len(result) > 1 and math.dist(result[0], result[-1]) <= EPSILON:
        result.pop()
    return result


def _face(mesh: SurfaceMesh, geometry: WallGeometry, triangle: list, role: str) -> None:
    """Score one parameter triangle at mapping facets before projecting it."""
    left, right = min(p[0] for p in triangle), max(p[0] for p in triangle)
    cuts = geometry.splits(left, right - left)
    for a, b in zip(cuts, cuts[1:]):
        piece = _clip(_clip(triangle, a, True), b, False)
        for i in range(1, len(piece) - 1):
            face = (piece[0], piece[i], piece[i + 1])
            u = tuple(face[1][j] - face[0][j] for j in range(3))
            v = tuple(face[2][j] - face[0][j] for j in range(3))
            normal = (
                u[1] * v[2] - u[2] * v[1],
                u[2] * v[0] - u[0] * v[2],
                u[0] * v[1] - u[1] * v[0],
            )
            if sum(n * n for n in normal) <= EPSILON**4:
                continue
            index = len(mesh.vertices)
            mesh.vertices.extend(geometry.point(*p) for p in face)
            mesh.triangles.append((index, index + 1, index + 2))
            mesh.face_roles.append(role)
            if len(mesh.triangles) > MAX_BEVEL_TRIANGLES:
                raise ValueError("Bevel exceeds the per-stone triangle limit")


def chamfer_mesh(
    geometry: WallGeometry, stone: ShapedStone, depth: float, width: float
) -> SurfaceMesh:
    """Build a closed rear, vertical skirt, one chamfer band and inset front face."""
    inner = inset_ring(stone, width)
    mesh = SurfaceMesh()
    for triangle in triangulate(stone.vertices):
        _face(mesh, geometry, [(x, y, 0) for x, y in reversed(triangle)], "back")
    for triangle in triangulate(inner.vertices):
        _face(mesh, geometry, [(x, y, depth) for x, y in triangle], "front")
    shoulder = depth - width
    for i, a in enumerate(stone.vertices):
        j = (i + 1) % len(stone.vertices)
        b, c, d = stone.vertices[j], inner.vertices[j], inner.vertices[i]
        low_a, low_b = (*a, 0), (*b, 0)
        top_a, top_b = (*a, shoulder), (*b, shoulder)
        front_a, front_b = (*d, depth), (*c, depth)
        for role, quad in (
            ("side", (low_a, low_b, top_b, top_a)),
            ("bevel", (top_a, top_b, front_b, front_a)),
        ):
            _face(mesh, geometry, [quad[0], quad[1], quad[2]], role)
            _face(mesh, geometry, [quad[0], quad[2], quad[3]], role)
        # Draw the silhouette shoulder, keeping triangulation and bevel diagonals hidden.
        cuts = geometry.splits(min(a[0], b[0]), abs(b[0] - a[0]))
        for left, right in zip(cuts, cuts[1:]):
            if abs(b[0] - a[0]) <= EPSILON:
                continue
            points = []
            for cut in (left, right):
                t = (cut - a[0]) / (b[0] - a[0])
                points.append(geometry.point(cut, a[1] + t * (b[1] - a[1]), shoulder))
            mesh.edge(*points)
        if abs(b[0] - a[0]) <= EPSILON:
            mesh.edge(geometry.point(*a, shoulder), geometry.point(*b, shoulder))
    return mesh
