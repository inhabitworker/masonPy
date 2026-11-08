"""Closed-shell checks at float32 precision, shared by geometry and STL export.

These checks canonicalize coincident coordinates for validation only. They do
not produce a connected editable mesh or establish subdivision suitability.
"""

from __future__ import annotations

from collections import Counter
import math
import struct
from typing import Any


def shell_triangles(mesh: dict[str, Any], scale: float) -> list[tuple]:
    """Weld numeric seam noise and validate the actual float32 STL shell topology."""
    raw = mesh["vertices"]
    if not raw or not mesh["triangles"]:
        raise ValueError("Cannot export an empty shell")
    if any(not math.isfinite(v) for p in raw for v in p):
        raise ValueError("STL vertices must be finite")
    extent = max(max(p[i] for p in raw) - min(p[i] for p in raw) for i in range(3))
    tolerance = max(extent * 1e-9, 1e-12)
    canonical = {}
    vertices = []
    for point in raw:
        key = tuple(round(v / tolerance) for v in point)
        if key not in canonical:
            try:
                packed = struct.pack("<3f", *(v * scale for v in point))
            except (OverflowError, struct.error) as error:
                raise ValueError(
                    "Export scale exceeds STL coordinate precision"
                ) from error
            canonical[key] = struct.unpack("<3f", packed)
        vertices.append(canonical[key])
    edges = Counter()
    triangles = []
    signed_volume = 0
    origin = vertices[0]
    for indices in mesh["triangles"]:
        a, b, c = (vertices[i] for i in indices)
        # A clipping/offset edge below float32 precision can collapse to one
        # stored point. Its zero-area faces carry no surface in the STL. Omit
        # only these faces, then validate the entire resulting closed shell.
        if len({a, b, c}) < 3:
            continue
        u, v = (
            tuple(b[i] - a[i] for i in range(3)),
            tuple(c[i] - a[i] for i in range(3)),
        )
        normal = (
            u[1] * v[2] - u[2] * v[1],
            u[2] * v[0] - u[0] * v[2],
            u[0] * v[1] - u[1] * v[0],
        )
        length = math.sqrt(sum(n * n for n in normal))
        if not math.isfinite(length) or length == 0:
            raise ValueError(
                "A triangle collapses at STL precision; adjust depth or scale"
            )
        for p, q in ((a, b), (b, c), (c, a)):
            edges[(p, q)] += 1
        signed_volume += sum((a[i] - origin[i]) * normal[i] for i in range(3)) / 6
        triangles.append((tuple(n / length for n in normal), a, b, c))
    if not triangles:
        raise ValueError("Shell collapses at STL precision; adjust depth or scale")
    if any(count != 1 or edges[(b, a)] != 1 for (a, b), count in edges.items()):
        raise ValueError("STL requires closed shells with consistently oriented edges")
    if signed_volume <= 0:
        raise ValueError("STL shell must enclose positive volume")
    return triangles
