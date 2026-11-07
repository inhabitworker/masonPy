"""Shared face-layout measurements for the workbench, saved specimens and battery."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from masonpy.models import Wall
from .joints import vertical_seams

ANALYSIS_COLOURS = {
    "ordinary": "#b6b1a7",
    "fallback": "#5d9cbd",
    "deliberate": "#a486bc",
}


def wall_report(
    wall: Wall,
    generator: str,
    parameters: Mapping[str, Any],
    *,
    complete: bool = False,
    failure: Mapping[str, Any] | None = None,
    events: Sequence[Any] = (),
    unexpected: str | None = None,
) -> dict[str, Any]:
    """Measure actual occupancy and bounded stock without changing the specimen.

    Area shares describe placed stone area, including accepted failed prefixes.
    Historical geometry may violate today's stock policy; report that explicitly.
    """
    stones = wall.stones
    ashlar = generator == "ashlar"
    snecks = (
        [
            s
            for s in stones
            if (
                s.width < parameters.get("min_stone_width", 0)
                or s.height < parameters.get("min_stone_height", 0)
            )
        ]
        if ashlar
        else [s for s in stones if s.traits.get("is_sneck")]
    )
    sneck_ids = {s.id for s in snecks}
    area = sum(s.width * s.height for s in stones)
    occupied = sum(cell is not None for row in wall.occupancy for cell in row)
    expected_area = sum(
        s.height
        * (
            s.width
            if wall.wrap_x
            else max(0, min(wall.width, s.x + s.width) - max(0, s.x))
        )
        for s in stones
    )
    seams = vertical_seams(wall)
    max_stack = max((s.stack_count for s in seams), default=0)
    limit = (
        parameters.get("max_joint_stack") if parameters.get("enforce_stack") else None
    )
    errors = [unexpected] if unexpected else []
    if expected_area != occupied:
        errors.append("Stone area and occupied cell count disagree")
    if complete and occupied != wall.width * wall.height:
        errors.append("Generator ended without filling the wall or reporting failure")
    if limit is not None and max_stack > limit:
        errors.append("Accepted prefix exceeds the joint-stack limit")
    if ashlar:
        for stone in stones:
            if (
                stone.width > parameters["max_stone_width"]
                or stone.height > parameters["max_stone_height"]
            ):
                errors.append(f"Stone {stone.id} exceeds maximum dimensions")
            if stone.id in sneck_ids and (
                not parameters.get("allow_snecks", 1)
                or min(stone.width, stone.height) < parameters.get("min_sneck_size", 1)
            ):
                errors.append(f"Stone {stone.id} violates sneck permission/minimum")
    rejections: dict[str, int] = {}
    max_examined = 0
    for event in events:
        decision = (
            event.decision if hasattr(event, "decision") else event.get("decision", {})
        )
        selection = decision.get("selection", {})
        if not isinstance(selection, dict):
            continue
        counts = selection.get("rejection_counts", {})
        for key, count in counts.items() if isinstance(counts, dict) else ():
            if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
                rejections[key] = rejections.get(key, 0) + count
        examined = selection.get("examined", 0)
        if isinstance(examined, int) and not isinstance(examined, bool):
            max_examined = max(max_examined, examined)
    if failure:
        counts = failure.get("details", {}).get("rejection_counts", {})
        for key, count in counts.items() if isinstance(counts, dict) else ():
            if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
                rejections[key] = rejections.get(key, 0) + count
    aspects = sorted(max(s.width / s.height, s.height / s.width) for s in snecks)
    result = {
        "complete": complete
        and occupied == wall.width * wall.height
        and not failure
        and not unexpected,
        "fill": occupied / (wall.width * wall.height),
        "stone_count": len(stones),
        "sneck_count": len(snecks),
        "sneck_share": len(snecks) / max(1, len(stones)),
        "sneck_area_share": sum(s.width * s.height for s in snecks) / max(1, area),
        "deliberate_snecks": sum(
            bool(s.traits.get("sneck_deliberate")) for s in snecks
        ),
        "both_small_snecks": sum(
            s.width < parameters.get("min_stone_width", 0)
            and s.height < parameters.get("min_stone_height", 0)
            for s in snecks
        ),
        "sneck_ids": sorted(sneck_ids),
        "deliberate_sneck_ids": [
            s.id for s in snecks if s.traits.get("sneck_deliberate")
        ],
        "max_sneck_aspect": max(aspects, default=0),
        "p95_sneck_aspect": aspects[min(len(aspects) - 1, int(0.95 * len(aspects)))]
        if aspects
        else 0,
        "max_joint_stack": max_stack,
        "joint_stack_limit": limit,
        "longest_joint": max((s.length for s in seams), default=0),
        "rejection_counts": rejections,
        "max_examined_per_step": max_examined,
        "invariant_errors": errors,
        "colours": dict(ANALYSIS_COLOURS),
    }
    result["summary"] = report_summary(result, failure)
    return result


def report_summary(
    report: Mapping[str, Any], failure: Mapping[str, Any] | None = None
) -> str:
    """Describe completion, closing stock and face-layout checks in plain English."""
    count, snecks = report["stone_count"], report["sneck_count"]
    if report["complete"]:
        opening = f"Completed {count} stones."
    elif failure:
        opening = f"Construction stopped with {count} stones, covering {report['fill']:.1%} of the wall."
    else:
        opening = (
            f"Partial wall: {count} stones, covering {report['fill']:.1%} of the wall."
        )
    area = "wall" if report["complete"] else "placed stone"
    stock = (
        (
            f" {snecks} are snecks ({report['sneck_share']:.1%} of stones), covering "
            f"{report['sneck_area_share']:.1%} of the {area} area; "
            f"{report['deliberate_snecks']} were chosen deliberately."
        )
        if snecks
        else " No snecks are present."
    )
    limit = report["joint_stack_limit"]
    joints = f" Maximum vertical joint stack is {report['max_joint_stack']}"
    joints += (
        f" (configured limit {limit})."
        if limit is not None
        else "; no joint-stack limit is enabled."
    )
    checks = (
        (" Layout checks: " + "; ".join(report["invariant_errors"]) + ".")
        if report["invariant_errors"]
        else " No size, occupancy or joint-limit violations were found."
    )
    ending = " Stopping reason: " + failure["reason"] if failure else ""
    return opening + stock + joints + checks + ending
