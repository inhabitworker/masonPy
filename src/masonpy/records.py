"""Plain JSON wall specimens: geometry, applied recipe and original evidence."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import math
from typing import Any

from masonpy.generators import ConstructionFailure, GenerationEvent
from masonpy.generators.catalog import get_generator_definition
from masonpy.models import Stone, Wall

MAX_RECORD_BYTES = 32 * 1024 * 1024
MAX_RECORD_CELLS = 4_000_000


def _integer(value: Any, name: str, minimum: int = 0) -> int:
    """Require actual integers rather than bools, floats or numeric strings."""
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer of at least {minimum}")
    return value


def _wall(data: Any) -> Wall:
    """Hydrate occupancy atomically through the normal model placement checks."""
    if not isinstance(data, dict):
        raise ValueError("wall must be an object")
    width = _integer(data.get("width"), "Wall width", 1)
    height = _integer(data.get("height"), "Wall height", 1)
    if width * height > MAX_RECORD_CELLS:
        raise ValueError("Imported wall exceeds the four-million-cell limit")
    wrap = data.get("wrap_x", False)
    if not isinstance(wrap, bool):
        raise ValueError("wrap_x must be boolean")
    wall = Wall(
        width,
        height,
        resolution=_integer(data.get("resolution", 1), "Resolution", 1),
        wrap_x=wrap,
    )
    stones = data.get("stones", [])
    if not isinstance(stones, list):
        raise ValueError("stones must be an array")
    for data in stones:
        if not isinstance(data, dict) or not isinstance(data.get("traits", {}), dict):
            raise ValueError("Each stone must be an object with object traits")
        values = {
            key: _integer(
                data.get(key), f"Stone {key}", 1 if key in ("width", "height") else 0
            )
            for key in ("id", "y", "width", "height")
        }
        x = data.get("x")
        if isinstance(x, bool) or not isinstance(x, int):
            raise ValueError("Stone x must be an integer")
        for key in ("is_sneck", "sneck_deliberate"):
            if key in data.get("traits", {}) and not isinstance(
                data["traits"][key], bool
            ):
                raise ValueError(f"Stone trait {key} must be boolean")
        wall.add_stone(Stone(**values, x=x, traits=deepcopy(data.get("traits", {}))))
    return wall


def _tuples(value: Any) -> Any:
    """Restore the standard-library random state from JSON arrays, never executable data."""
    return (
        tuple(_tuples(v) for v in value) if isinstance(value, (tuple, list)) else value
    )


def _failure(data: Any) -> ConstructionFailure | None:
    """Restore a terminal outcome while preserving the recorded original wording."""
    if data is None:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("reason"), str):
        raise ValueError("failure must contain a textual reason")
    if not isinstance(data.get("retry_possible", True), bool) or not isinstance(
        data.get("details", {}), dict
    ):
        raise ValueError("Invalid failure details")
    if not isinstance(data.get("kind", "no_continuation"), str):
        raise ValueError("Failure kind must be text")
    error = ConstructionFailure(
        _integer(data.get("x"), "Failure x"),
        _integer(data.get("y"), "Failure y"),
        data["reason"],
        _integer(data.get("rejected", 0), "Rejected count"),
        retry_possible=data.get("retry_possible", True),
        kind=data.get("kind", "no_continuation"),
        details=deepcopy(data.get("details", {})),
    )
    if "message" in data:
        if not isinstance(data["message"], str):
            raise ValueError("Failure message must be text")
        error.args = (data["message"],)
    return error


@dataclass(frozen=True)
class WallRecord:
    """An isolated snapshot; callers receive copies rather than mutable stored data."""

    _data: dict[str, Any]

    @classmethod
    def capture(
        cls,
        wall: Wall,
        generator: dict[str, Any],
        events: list[GenerationEvent],
        *,
        complete: bool,
        failure: ConstructionFailure | None,
        random_state: Any = None,
        generation_seconds: float = 0,
        analysis: dict[str, Any] | None = None,
    ) -> WallRecord:
        """Capture trusted runtime state once, without replaying the generator."""
        data = dict(
            wall=wall.to_dict(),
            generator=generator,
            construction=dict(
                complete=complete, failure=failure.to_dict() if failure else None
            ),
            events=[e.to_dict() for e in events],
            random_state=random_state,
            generation_seconds=generation_seconds,
        )
        if analysis is not None:
            data["analysis"] = analysis
        return cls(deepcopy(data))

    @classmethod
    def from_dict(cls, data: Any) -> WallRecord:
        """Validate a full specimen or a simple workbench reset recipe before committing it."""
        try:
            json.dumps(data, allow_nan=False)
        except (TypeError, ValueError, RecursionError) as error:
            raise ValueError(
                "Wall JSON must contain finite, serializable data"
            ) from error
        if not isinstance(data, dict):
            raise ValueError("Wall JSON must be an object")
        data = deepcopy(data)
        if isinstance(data.get("generator"), str) and "wall" not in data:
            data = {
                "generator": {
                    "id": data["generator"],
                    "parameters": data.get("parameters", {}),
                },
                "wall": {"width": data.get("width"), "height": data.get("height")},
            }
        config = data.get("generator")
        if not isinstance(config, dict) or not isinstance(config.get("id"), str):
            raise ValueError("generator must contain an id and parameter object")
        definition = get_generator_definition(config["id"])
        generator, parameters = definition.create(config.get("parameters"))
        wall = _wall(data.get("wall"))
        construction = data.get("construction", {})
        if not isinstance(construction, dict):
            raise ValueError("construction must be an object")
        failure = _failure(construction.get("failure"))
        filled = all(cell is not None for row in wall.occupancy for cell in row)
        complete = construction.get("complete", filled and failure is None)
        if not isinstance(complete, bool) or (complete and (not filled or failure)):
            raise ValueError(
                "A completed wall must be fully occupied and have no failure"
            )
        evidence = data.get("events", [])
        if not isinstance(evidence, list) or (
            evidence and len(evidence) != len(wall.stones)
        ):
            raise ValueError(
                "Placement events must match the saved stones in order, or be omitted"
            )
        events = []
        for index, stone in enumerate(wall.stones):
            if not evidence:
                events.append(
                    GenerationEvent(
                        stone,
                        "Loaded stone; original placement evidence was not supplied.",
                        {"restored": True, "original_evidence": False},
                    )
                )
                continue
            item = evidence[index]
            if not isinstance(item, dict) or item.get("stone") != stone.to_dict():
                raise ValueError("Placement evidence does not match the saved geometry")
            if not isinstance(item.get("explanation"), str) or not isinstance(
                item.get("decision", {}), dict
            ):
                raise ValueError("Invalid placement explanation or decision")
            events.append(
                GenerationEvent(
                    stone, item["explanation"], deepcopy(item.get("decision", {}))
                )
            )
        seconds = data.get("generation_seconds", 0)
        if (
            isinstance(seconds, bool)
            or not isinstance(seconds, (float, int))
            or not math.isfinite(seconds)
            or seconds < 0
        ):
            raise ValueError("generation_seconds must be a finite non-negative number")
        random_state = data.get("random_state")
        if random_state is not None:
            random = getattr(generator, "_random", None)
            if random is None:
                raise ValueError("This generator does not accept a saved random state")
            try:
                random.setstate(_tuples(random_state))
            except (TypeError, ValueError, OverflowError) as error:
                raise ValueError("Invalid saved random state") from error
        return cls.capture(
            wall,
            {"id": definition.id, "parameters": parameters},
            events,
            complete=complete,
            failure=failure,
            random_state=random_state,
            generation_seconds=seconds,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a detached, JSON-compatible specimen without session-local IDs or meshes."""
        return deepcopy(self._data)

    def hydrate(self) -> dict[str, Any]:
        """Restore the exact geometry and available continuation state into fresh objects."""
        data = self._data
        definition = get_generator_definition(data["generator"]["id"])
        generator, parameters = definition.create(data["generator"]["parameters"])
        wall = _wall(data["wall"])
        if data.get("random_state") is not None:
            generator._random.setstate(_tuples(data["random_state"]))
        return dict(
            wall=wall,
            generator=generator,
            generator_definition=definition,
            generator_parameters=parameters,
            events=[
                GenerationEvent(stone, item["explanation"], deepcopy(item["decision"]))
                for stone, item in zip(wall.stones, data["events"])
            ],
            complete=data["construction"]["complete"],
            failure=_failure(data["construction"]["failure"]),
            generation_seconds=data.get("generation_seconds", 0),
        )

    def label(self, number: str) -> str:
        """Describe a history entry compactly without computing analysis or copying its wall."""
        data = self._data
        config, wall, outcome = data["generator"], data["wall"], data["construction"]
        seed = config["parameters"].get("seed")
        status = (
            "stopped"
            if outcome["failure"]
            else "complete"
            if outcome["complete"]
            else "partial"
        )
        name = get_generator_definition(config["id"]).label
        count = len(wall["stones"])
        return (
            f"{number} · {name} · {wall['width']}×{wall['height']}"
            + (f" · seed {seed}" if seed is not None else "")
            + f" · {count} stone{'s' if count != 1 else ''} · {status}"
        )
