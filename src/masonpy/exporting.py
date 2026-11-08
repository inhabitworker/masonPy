"""Clean stage SVG and validated binary STL, independent of the workbench UI."""

from __future__ import annotations

import json
import math
import struct
from typing import Any
from xml.etree import ElementTree as ET

# Preserve the existing import path for callers of the shell validator.
from masonpy.geometry.validation import shell_triangles as shell_triangles
from masonpy.models import Wall
from masonpy.processing import ShapedStone, ShapedWall, WallDescription


SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def export_scale(value: float) -> float:
    """Validate a physical millimetres-per-grid-unit conversion."""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError("Millimetres per unit must be a finite positive number")
    return float(value)


def wall_svg(
    source: Wall | ShapedWall,
    *,
    scale: float = 1,
    metadata: dict[str, Any] | None = None,
) -> bytes:
    """Export full applied contours without viewer overlays, selection or playback state.

    Periodic walls are repeated and clipped to one reference circumference;
    finite walls retain their whole overhanging contours. viewBox units remain
    logical, while document dimensions are physical millimetres.
    """
    scale = export_scale(scale)
    if isinstance(source, ShapedWall):
        wall = source.source
        contours = source.stones
    else:
        wall = WallDescription.from_wall(source)
        contours = tuple(
            ShapedStone(
                s.id,
                (
                    (s.x, s.y),
                    (s.x + s.width, s.y),
                    (s.x + s.width, s.y + s.height),
                    (s.x, s.y + s.height),
                ),
            )
            for s in wall.stones
        )
    if not contours:
        raise ValueError("There are no stones to export")
    left = 0 if wall.wrap_x else min(0, *(p[0] for s in contours for p in s.vertices))
    right = (
        wall.width
        if wall.wrap_x
        else max(wall.width, *(p[0] for s in contours for p in s.vertices))
    )
    if not all(
        math.isfinite(size * scale) and size * scale > 0
        for size in (right - left, wall.height)
    ):
        raise ValueError("Export scale exceeds SVG dimension precision")
    root = ET.Element(
        f"{{{SVG_NS}}}svg",
        {
            "viewBox": f"{left:g} 0 {right - left:g} {wall.height:g}",
            "width": f"{(right - left) * scale:g}mm",
            "height": f"{wall.height * scale:g}mm",
        },
    )
    ET.SubElement(root, "title").text = "MasonPy applied wall contours"
    ET.SubElement(root, "metadata").text = json.dumps(
        {
            "millimetres_per_unit": scale,
            "wall": {"width": wall.width, "height": wall.height, "wrap_x": wall.wrap_x},
            **(metadata or {}),
        }
    )
    if wall.wrap_x:
        clip = ET.SubElement(
            ET.SubElement(root, "defs"),
            "clipPath",
            {"id": "wall-bounds", "clipPathUnits": "userSpaceOnUse"},
        )
        ET.SubElement(
            clip,
            "rect",
            {"x": "0", "y": "0", "width": str(wall.width), "height": str(wall.height)},
        )
    drawing = ET.SubElement(
        root, "g", {"fill": "none", "stroke": "black", "stroke-width": "0.02"}
    )
    if wall.wrap_x:
        drawing.set("clip-path", "url(#wall-bounds)")
    for stone in contours:
        group = ET.SubElement(
            drawing, "g", {"id": f"stone-{stone.id}", "data-stone-id": str(stone.id)}
        )
        lo = min(p[0] for p in stone.vertices)
        hi = max(p[0] for p in stone.vertices)
        periods = (
            range(math.floor(lo / wall.width), math.ceil(hi / wall.width))
            if wall.wrap_x
            else (0,)
        )
        for period in periods:
            ET.SubElement(
                group,
                "polygon",
                {
                    "points": " ".join(
                        f"{x - period * wall.width:.12g},{wall.height - y:.12g}"
                        for x, y in stone.vertices
                    )
                },
            )
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def mesh_stl(geometry: dict[str, Any], *, scale: float = 1) -> bytes:
    """Serialize closed stone and optional core shells together, without boolean union."""
    scale = export_scale(scale)
    triangles = []
    for stone in geometry["stones"]:
        try:
            triangles.extend(shell_triangles(stone, scale))
        except ValueError as error:
            raise ValueError(f"Stone {stone['id']}: {error}") from error
    core = geometry.get("primitive", {})
    if core.get("triangles"):
        try:
            triangles.extend(shell_triangles(core, scale))
        except ValueError as error:
            raise ValueError(f"Core: {error}") from error
    if not triangles:
        raise ValueError("There are no solid shells to export")
    header = b"MasonPy | separate closed shells | coordinates in millimetres".ljust(
        80, b"\0"
    )
    output = bytearray(header + struct.pack("<I", len(triangles)))
    for normal, a, b, c in triangles:
        output.extend(struct.pack("<12fH", *normal, *a, *b, *c, 0))
    return bytes(output)
