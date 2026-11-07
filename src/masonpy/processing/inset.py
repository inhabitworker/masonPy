"""Dedicated polygon erosion with explicit rejection of consumed or split stones."""

from __future__ import annotations

from .field import PRECISION
from .models import ShapedStone
from .validation import area2, clipper, fixed_path, polygon_operation, validate_path


def inset_stone(stone: ShapedStone, joint_width: float) -> ShapedStone:
    """Inset one valid simple polygon by half a joint; never discard fragments silently."""
    if joint_width == 0:
        return stone
    lib = clipper()
    path = fixed_path(stone)
    narrow_span = (
        min(max(p[i] for p in path) - min(p[i] for p in path) for i in (0, 1))
        / PRECISION
    )
    if joint_width >= narrow_span:
        raise ValueError(
            f"Joint width consumes stone {stone.id} after distortion; reduce joint width or distortion"
        )
    offset = lib.PyclipperOffset(miter_limit=2.0)
    offset.AddPath(path, lib.JT_MITER, lib.ET_CLOSEDPOLYGON)
    tree = offset.Execute2(-joint_width * PRECISION / 2)
    if not tree.Childs:
        raise ValueError(
            f"Joint width consumes stone {stone.id} after distortion; reduce joint width or distortion"
        )
    if len(tree.Childs) != 1 or tree.Childs[0].Childs:
        raise ValueError(
            f"Joint width splits stone {stone.id} after distortion; reduce joint width or distortion"
        )
    # Remove only clipping-grid noise (two steps = 0.0000002 grid units),
    # such as a one-step edge generated at an almost straight junction.
    result = [tuple(point) for point in lib.CleanPolygon(tree.Childs[0].Contour, 2)]
    if area2(result) < 0:
        result.reverse()
    validate_path(result, stone.id)
    outside = polygon_operation(result, path, lib.CT_DIFFERENCE)
    if any(area2(piece) != 0 for piece in outside):
        raise ValueError(
            f"Inset of stone {stone.id} extends outside its distorted boundary"
        )
    return ShapedStone(
        stone.id, tuple((x / PRECISION, y / PRECISION) for x, y in result)
    )
