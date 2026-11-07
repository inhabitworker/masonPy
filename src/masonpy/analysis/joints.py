"""Completed horizontal/vertical joints and explicit diagnostic logging."""

from __future__ import annotations

import logging

from masonpy.models import HorizontalJoint, VerticalSeam, Wall

from .grid import _horizontal_runs, _occupancy_cells


def horizontal_joints(
    wall: Wall, *, wrap_x: bool | None = None
) -> tuple[HorizontalJoint, ...]:
    """Return maximal completed horizontal runs, optionally at one elevation."""
    wrap_x = wall.wrap_x if wrap_x is None else wrap_x
    cells = _occupancy_cells(wall, wrap_x)
    joints = []
    for y in range(1, wall.height):
        mask = [
            below is not None and above is not None and below != above
            for below, above in zip(cells[y - 1], cells[y])
        ]
        joints.extend(
            HorizontalJoint(x, y, length)
            for x, length in _horizontal_runs(mask, wrap_x)
        )
    return tuple(joints)


def vertical_seams(
    wall: Wall, *, wrap_x: bool | None = None
) -> tuple[VerticalSeam, ...]:
    """Measure joints with occupied, distinct stones on both sides.

    Stone identities may change along a continuous joint. Empty cells and cells
    belonging to the same stone interrupt it. With wrap_x, project whole stones
    modulo width and compare the last and first column at x=0. Conflicting
    projections are rejected rather than choosing an arbitrary stone.
    """
    if wrap_x is None:
        wrap_x = wall.wrap_x
    cells = _occupancy_cells(wall, wrap_x)

    seams = []
    for x in range(0 if wrap_x else 1, wall.width):
        start = None
        left_ids, right_ids = set(), set()
        for y in range(wall.height + 1):
            joint = False
            if y < wall.height:
                left, right = cells[y][x - 1], cells[y][x]
                joint = left is not None and right is not None and left != right
            if joint and start is None:
                start = y
            if joint:
                left_ids.add(left)
                right_ids.add(right)
            elif not joint and start is not None:
                seams.append(
                    VerticalSeam(x, start, y - start, len(left_ids), len(right_ids))
                )
                start = None
                left_ids.clear()
                right_ids.clear()
    return tuple(seams)


def report_vertical_seams(
    wall: Wall, *, wrap_x: bool | None = None, logger: logging.Logger | None = None
) -> str:
    """Explicit snapshot report; callers control when logging occurs."""
    if wrap_x is None:
        wrap_x = wall.wrap_x
    seams = vertical_seams(wall, wrap_x=wrap_x)
    message = (
        f"Vertical seams ({'logical wrap' if wrap_x else 'finite wall'}): "
        f"{len(seams)} runs; longest {max((s.length for s in seams), default=0)} units; "
        f"maximum stack {max((s.stack_count for s in seams), default=0)}."
    )
    (logger or logging.getLogger(__name__)).info(message)
    return message
