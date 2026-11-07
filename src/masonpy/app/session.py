"""Workbench state and incremental/undo lifecycle; core generators stay GUI-free."""

from __future__ import annotations

import threading
from typing import Any, Iterator

from masonpy.analysis import WallAnalysis
from masonpy.generators import (
    GENERATOR_DEFINITIONS,
    ConstructionFailure,
    GenerationEvent,
)
from masonpy.generators.catalog import get_generator_definition
from masonpy.models import Wall


class GenerationSession:
    """Own the wall and current incremental generator for the web UI."""

    def __init__(
        self,
        *,
        width: int = 104,
        height: int = 60,
        generator_id: str = "running_bond",
        generator_parameters: dict[str, Any] | None = None,
    ) -> None:
        """Create the default or supplied workbench configuration and its re-entrant session lock."""
        self._lock = threading.RLock()
        self.reset(
            width=width,
            height=height,
            generator_id=generator_id,
            generator_parameters=generator_parameters,
        )

    def reset(
        self,
        *,
        width: int,
        height: int,
        generator_id: str = "running_bond",
        generator_parameters: dict[str, Any] | None = None,
    ) -> None:
        """Create a fresh wall, generator and iterator, clearing history and terminal failure."""
        with self._lock:
            wall = Wall(width, height)
            definition = get_generator_definition(generator_id)
            generator, parameters = definition.create(generator_parameters)
            # Commit only after configuration validation succeeds.
            self.wall = wall
            self.generator_definition = definition
            self.generator = generator
            self.generator_parameters = parameters
            self._steps: Iterator[GenerationEvent] = (
                self.generator.generate_incrementally(self.wall)
            )
            self.events: list[GenerationEvent] = []
            self.complete = False
            self.failure: ConstructionFailure | None = None

    def step(self) -> GenerationEvent | None:
        """Accept one incremental event, or retain terminal completion/failure and return None."""
        with self._lock:
            if self.complete or self.failure is not None:
                return None
            try:
                event = next(self._steps)
            except StopIteration:
                self.complete = True
                return None
            except ConstructionFailure as failure:
                self.failure = failure
                return None
            self.events.append(event)
            return event

    def generate_all(self) -> None:
        """Consume the same step mechanism until completion or strict construction failure."""
        with self._lock:
            while self.step() is not None:
                pass

    def undo(self) -> GenerationEvent | None:
        """Undo one logical placement and re-evaluate it on the next step."""

        with self._lock:
            self.failure = None
            if not self.events:
                self._steps = self.generator.generate_incrementally(self.wall)
                return None
            event = self.events.pop()
            removed = self.wall.remove_last_stone()
            if removed != event.stone:
                raise RuntimeError("wall and generation event history are out of sync")
            self.complete = False
            self._steps = self.generator.generate_incrementally(self.wall)
            return event

    def inspect(
        self, *, stone_id: int | None = None, visible_count: int | None = None
    ) -> dict[str, Any]:
        """Inspect the visible prefix; display wrapping never changes topology."""
        with self._lock:
            count = len(self.wall.stones) if visible_count is None else visible_count
            if (
                isinstance(count, bool)
                or not isinstance(count, int)
                or not 0 <= count <= len(self.wall.stones)
            ):
                raise ValueError("visible_count must identify a valid wall prefix")
            wall = Wall(
                self.wall.width,
                self.wall.height,
                resolution=self.wall.resolution,
                wrap_x=self.wall.wrap_x,
            )
            for stone in self.wall.stones[:count]:
                wall.add_stone(stone)
            analysis = WallAnalysis(wall)
            context = {
                "generator": self.generator_definition.id,
                "parameters": dict(self.generator_parameters),
                "logical_wrap_x": wall.wrap_x,
                "visible_stones": count,
                "generated_stones": len(self.wall.stones),
            }
            if stone_id is not None:
                if isinstance(stone_id, bool) or not isinstance(stone_id, int):
                    raise ValueError("stone_id must be an integer")
                result = analysis.stone_info(stone_id)
                result["placement"] = next(
                    (
                        event.to_dict()
                        for event in self.events
                        if event.stone.id == stone_id
                    ),
                    None,
                )
                result["context"] = context
                return result
            return {
                "context": context,
                "wall": wall.to_dict(),
                "analysis": analysis.to_dict(),
                "skyline": analysis.skyline(),
                "exposed_edges": [edge.to_dict() for edge in analysis.exposed_edges()],
                "occupancy": wall.occupancy,
                "construction": {
                    "complete": self.complete,
                    "failure": self.failure.to_dict() if self.failure else None,
                    "visible_prefix_complete": count == len(self.wall.stones),
                },
                "placements": [event.to_dict() for event in self.events[:count]],
            }

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation of the current object or snapshot."""
        with self._lock:
            return {
                "wall": self.wall.to_dict(),
                "analysis": WallAnalysis(self.wall).to_dict(),
                "generator": {
                    "id": self.generator_definition.id,
                    "label": self.generator_definition.label,
                    "category": self.generator_definition.category,
                    "parameters": dict(self.generator_parameters),
                },
                "generators": [
                    definition.to_dict() for definition in GENERATOR_DEFINITIONS
                ],
                "events": [event.to_dict() for event in self.events],
                "complete": self.complete,
                "failure": self.failure.to_dict() if self.failure else None,
                "last_stone_id": self.events[-1].stone.id if self.events else None,
            }
