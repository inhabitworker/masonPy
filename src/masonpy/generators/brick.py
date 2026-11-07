"""Periodic brick patterns built on one shared course planner."""

from __future__ import annotations

import logging
from abc import abstractmethod
from collections.abc import Iterator

from masonpy.generators.errors import ConstructionFailure
from masonpy.generators.events import GenerationEvent
from masonpy.generators.interface import WallGenerator
from masonpy.models import Stone, Wall

Face = tuple[int, str]
logger = logging.getLogger(__name__)


class BrickBondGenerator(WallGenerator):
    """Base class for bonds described by a repeating pattern in each course."""

    def __init__(self, *, brick_height: int = 2, course_offset: int = 0) -> None:
        """Initialise configuration and local state; no generation is performed here."""
        if (
            not isinstance(brick_height, int)
            or isinstance(brick_height, bool)
            or brick_height <= 0
        ):
            raise ValueError("brick_height must be a positive integer")
        self.brick_height = brick_height
        if not isinstance(course_offset, int) or isinstance(course_offset, bool):
            raise ValueError("course_offset must be an integer")
        self.course_offset = course_offset

    @abstractmethod
    def _course_pattern(self, course: int) -> tuple[int, tuple[Face, ...]]:
        """Return the left offset and repeating ``(width, face)`` sequence."""

    def generate_incrementally(self, wall: Wall) -> Iterator[GenerationEvent]:
        # Check the whole course plan before constructing an invalid ring. A
        # phase shift cannot make an incompatible repeating pattern close.
        """Resume from a valid prefix and yield each accepted whole stone with its decision record."""
        for course, y in enumerate(range(0, wall.height, self.brick_height)):
            _, pattern = self._course_pattern(course)
            period = sum(width for width, _ in pattern)
            if wall.width % period:
                failure = ConstructionFailure(
                    0,
                    y,
                    f"Course {course} cannot close around circumference {wall.width}: "
                    f"the repeating {self.name} pattern is {period} units wide "
                    f"(remainder {wall.width % period}). Choose a wall width divisible by {period}; "
                    "bricks will not be shortened or clipped to fit the row.",
                    retry_possible=False,
                )
                logger.warning(str(failure))
                raise failure
        if not wall.stones:
            wall.wrap_x = True
        elif not wall.wrap_x:
            raise ValueError("brick generation requires logical horizontal wrapping")
        existing = wall.stones
        planned_count = 0

        for course, y in enumerate(range(0, wall.height, self.brick_height)):
            height = min(self.brick_height, wall.height - y)
            offset, pattern = self._course_pattern(course)
            period = sum(width for width, _ in pattern)
            offset = (offset + course * self.course_offset) % period
            cursor = -offset
            pattern_index = 0
            limit = wall.width - offset
            while cursor < limit:
                nominal_width, face = pattern[pattern_index % len(pattern)]
                pattern_index += 1
                x = cursor
                width = nominal_width
                if x + width <= 0:
                    cursor += nominal_width
                    limit += nominal_width
                    continue
                overhangs_wall = x < 0 or x + width > wall.width

                traits = {
                    "generator": self.name,
                    "course": course,
                    "face": face,
                    "overhangs_wall": overhangs_wall,
                }
                stone = Stone(
                    id=planned_count,
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                    traits=traits,
                )

                if planned_count < len(existing):
                    if existing[planned_count] != stone:
                        raise ValueError(
                            "wall stones are not a valid prefix for this generator"
                        )
                else:
                    wall.add_stone(stone)
                    details = [f"course {course}", face]
                    if offset:
                        details.append(f"offset {offset}")
                    if overhangs_wall:
                        details.append("crosses the periodic seam as one whole brick")
                    decision = {
                        "target": {
                            "reason": "next face in course, left to right; courses bottom to top",
                            "course": course,
                            "pattern_index": pattern_index - 1,
                        },
                        "width": {
                            "chosen": width,
                            "face": face,
                            "pattern": pattern,
                            "period": period,
                            "course_phase": offset,
                            "additional_phase": course * self.course_offset,
                        },
                        "height": {
                            "chosen": height,
                            "nominal": self.brick_height,
                            "remaining_wall_height": wall.height - y,
                        },
                        "boundary": {
                            "overhangs": overhangs_wall,
                            "logical_wrap_x": wall.wrap_x,
                        },
                        "selection": "deterministic bond pattern; no random choice",
                    }
                    yield GenerationEvent(
                        stone,
                        f"Added at [{x}, {y}]:\n"
                        f"Target: next face from left to right in course {course}, courses bottom to top.\n"
                        f"Width: {width}; {face} from repeating pattern {pattern}; "
                        f"phase {offset} modulo {period}, cumulative nudge {course * self.course_offset}.\n"
                        f"Height: {height}; nominal {self.brick_height}, "
                        f"remaining wall height {wall.height - y}.\n"
                        f"Selection: deterministic pattern, one prescribed size; no randomness.\n"
                        f"Boundary: {'one whole brick; occupancy wraps modulo the circumference' if overhangs_wall else 'inside reference grid; course closes periodically'}.\n"
                        + "; ".join(details)
                        + ".",
                        decision,
                    )

                planned_count += 1
                cursor += nominal_width

        if len(existing) > planned_count:
            raise ValueError("wall has more stones than this generator would place")


class StackBondGenerator(BrickBondGenerator):
    """Courses of stretchers whose vertical joints remain aligned."""

    name = "stack_bond"

    def __init__(
        self, *, stretcher_width: int = 4, brick_height: int = 2, course_offset: int = 0
    ) -> None:
        """Initialise configuration and local state; no generation is performed here."""
        _validate_stretcher_width(stretcher_width)
        super().__init__(brick_height=brick_height, course_offset=course_offset)
        self.stretcher_width = stretcher_width

    def _course_pattern(self, course: int) -> tuple[int, tuple[Face, ...]]:
        """Return the conventional phase and repeating (width, face) sequence for this course."""
        return 0, ((self.stretcher_width, "stretcher"),)


class RunningBondGenerator(StackBondGenerator):
    """Stretcher courses offset by half a brick on alternating courses."""

    name = "running_bond"

    def _course_pattern(self, course: int) -> tuple[int, tuple[Face, ...]]:
        """Return the conventional phase and repeating (width, face) sequence for this course."""
        offset = self.stretcher_width // 2 if course % 2 else 0
        return offset, ((self.stretcher_width, "stretcher"),)


class EnglishBondGenerator(BrickBondGenerator):
    """Alternating courses made entirely of stretchers or headers."""

    name = "english_bond"

    def __init__(
        self,
        *,
        stretcher_width: int = 4,
        header_width: int = 2,
        brick_height: int = 2,
        course_offset: int = 0,
    ) -> None:
        """Initialise configuration and local state; no generation is performed here."""
        _validate_face_widths(stretcher_width, header_width)
        super().__init__(brick_height=brick_height, course_offset=course_offset)
        self.stretcher_width = stretcher_width
        self.header_width = header_width

    def _course_pattern(self, course: int) -> tuple[int, tuple[Face, ...]]:
        """Return the conventional phase and repeating (width, face) sequence for this course."""
        if course % 2:
            return self.header_width // 2, ((self.header_width, "header"),)
        return 0, ((self.stretcher_width, "stretcher"),)


class FlemishBondGenerator(EnglishBondGenerator):
    """Alternating stretchers and headers, shifted half a repeat each course."""

    name = "flemish_bond"

    def _course_pattern(self, course: int) -> tuple[int, tuple[Face, ...]]:
        """Return the conventional phase and repeating (width, face) sequence for this course."""
        pattern = (
            (self.stretcher_width, "stretcher"),
            (self.header_width, "header"),
        )
        return (
            self.stretcher_width + self.header_width
        ) // 2 if course % 2 else 0, pattern


def _validate_stretcher_width(width: int) -> None:
    """Require an even stretcher width of at least two grid units."""
    if not isinstance(width, int) or isinstance(width, bool) or width < 2 or width % 2:
        raise ValueError("stretcher_width must be an even integer of at least 2")


def _validate_face_widths(stretcher_width: int, header_width: int) -> None:
    """Require valid even face lengths with stretchers longer than headers."""
    _validate_stretcher_width(stretcher_width)
    if (
        not isinstance(header_width, int)
        or isinstance(header_width, bool)
        or header_width < 2
        or header_width % 2
    ):
        raise ValueError("header_width must be an even integer of at least 2")
    if stretcher_width <= header_width:
        raise ValueError("stretcher_width must be greater than header_width")
