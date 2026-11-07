"""Explicit applied stages and revision provenance around the generation session."""

from __future__ import annotations

from copy import deepcopy
import json
from time import perf_counter
from typing import Any

from masonpy.exporting import mesh_stl, wall_svg
from masonpy.geometry import WallGeometry
from masonpy.generators import GenerationEvent
from masonpy.analysis import wall_report
from masonpy.records import WallRecord
from masonpy.processing import (
    ShapeSettings,
    WallDescription,
    build_topology,
    shape_wall,
)

from .session import GenerationSession

DEFAULT_SHAPE_SETTINGS = {
    "joint_width": 0.2,
    "distortion": 0,
    "seed": 1,
    "variation_scale": 6,
}

DEFAULT_BUILD_SETTINGS = {
    "mode": "projected",
    "roundness": 0.25,
    "resolution": 8,
    "depth": 0.25,
    "primitive": "tube",
    "tube_thickness": 1,
}


class WorkbenchSession(GenerationSession):
    """Keep downstream results stable until explicitly applied, retaining stale previews."""

    def __init__(self, **kwargs: Any) -> None:
        """Initialize independent source revisions, stage histories and applied results."""
        self.wall_revision = 0
        self.shape_revision = 0
        self.shape_result = None
        self._shape_topology = None
        self._shape_topology_revision = None
        self.shape_source_revision = None
        self.shape_source_configuration = None
        self.shape_events: list[str] = []
        self.build_revision = 0
        self.build_result = None
        self.build_source_revision = None
        self.build_settings = None
        self.build_events: list[str] = []
        self._records: dict[str, WallRecord | None] = {}
        self.active_record: str | None = None
        self._next_record = 1
        self.generation_seconds = 0.0
        self._report_key = None
        self._report = None
        super().__init__(**kwargs)

    def reset(self, **kwargs: Any) -> None:
        """Replace the logical source atomically; failed configuration preserves all stages."""
        with self._lock:
            previous_id = self.active_record
            previous = self._capture_record() if previous_id else None
            super().reset(**kwargs)
            if previous_id:
                self._records[previous_id] = previous
            self.active_record = None
            self.generation_seconds = 0.0
            self.wall_revision += 1

    def step(self) -> GenerationEvent | None:
        """Advance the shared generator and invalidate downstream only on placement."""
        with self._lock:
            if self.complete or self.failure is not None:
                return None
            self._ensure_record()
            started = perf_counter()
            try:
                event = super().step()
            finally:
                self.generation_seconds += perf_counter() - started
            if event is not None:
                self.wall_revision += 1
            return event

    def wall_report(self) -> dict[str, Any]:
        """Cache the same measurements used by the diagnostic battery per accepted state."""
        key = (self.wall_revision, self.complete, id(self.failure), len(self.events))
        if key != self._report_key:
            self._report = wall_report(
                self.wall,
                self.generator_definition.id,
                self.generator_parameters,
                complete=self.complete,
                failure=self.failure.to_dict() if self.failure else None,
                events=self.events,
            )
            self._report_key = key
        return deepcopy(self._report)

    def _ensure_record(self) -> None:
        """Create one session entry when a generation attempt first starts."""
        if self.active_record is None:
            self.active_record = str(self._next_record)
            self._next_record += 1
            self._records[self.active_record] = None

    def _capture_record(self) -> WallRecord:
        """Freeze the current specimen only on save or departure, not on every placement."""
        random = getattr(self.generator, "_random", None)
        return WallRecord.capture(
            self.wall,
            {
                "id": self.generator_definition.id,
                "parameters": self.generator_parameters,
            },
            self.events,
            complete=self.complete,
            failure=self.failure,
            random_state=random.getstate() if random else None,
            generation_seconds=self.generation_seconds,
            analysis=self.wall_report(),
        )

    def _activate_record(
        self, record_id: str, record: WallRecord, restored: dict[str, Any]
    ) -> None:
        """Commit a validated specimen and invalidate downstream by a new Wall revision."""
        if self.active_record is not None:
            self._records[self.active_record] = self._capture_record()
        for key, value in restored.items():
            setattr(self, key, value)
        self._steps = self.generator.generate_incrementally(self.wall)
        self._records[record_id] = record
        self.active_record = record_id
        self.wall_revision += 1
        self._shape_topology = None
        self._shape_topology_revision = None

    def load_record(self, data: Any, *, source_revision: int | None = None) -> None:
        """Validate all input before replacing the active wall or changing history."""
        record = WallRecord.from_dict(data)
        restored = record.hydrate()
        with self._lock:
            self._check_source_revision(source_revision, self.wall_revision, "Wall")
            record_id = str(self._next_record)
            self._activate_record(record_id, record, restored)
            self._next_record += 1

    def select_record(
        self, record_id: str, *, source_revision: int | None = None
    ) -> None:
        """Restore a session specimen, preserving the current wall's continuation state."""
        with self._lock:
            self._check_source_revision(source_revision, self.wall_revision, "Wall")
            if not isinstance(record_id, str) or record_id not in self._records:
                raise ValueError("Unknown wall history entry")
            if record_id == self.active_record:
                return
            record = self._records[record_id]
            self._activate_record(record_id, record, record.hydrate())

    def save_record(self, *, revision: int | None = None) -> tuple[bytes, str]:
        """Export applied geometry and evidence; drafts and downstream meshes are excluded."""
        with self._lock:
            self._check_source_revision(revision, self.wall_revision, "Wall")
            content = json.dumps(
                self._capture_record().to_dict(), indent=2, allow_nan=False
            ).encode()
            return content, f"masonpy-wall-r{self.wall_revision}.json"

    def _history_entries(self) -> list[dict[str, str]]:
        """Return lightweight labels without serializing every stored wall on each request."""
        entries = []
        for record_id, record in self._records.items():
            if record_id == self.active_record:
                seed = self.generator_parameters.get("seed")
                status = (
                    "stopped"
                    if self.failure
                    else "complete"
                    if self.complete
                    else "partial"
                )
                label = f"{record_id} · {self.generator_definition.label} · {self.wall.width}×{self.wall.height}"
                label += f" · seed {seed}" if seed is not None else ""
                count = len(self.wall.stones)
                label += f" · {count} stone{'s' if count != 1 else ''} · {status}"
            else:
                label = record.label(record_id)
            entries.append({"id": record_id, "label": label})
        return entries

    def undo(self) -> GenerationEvent | None:
        """Remove a placement while preserving downstream snapshots for stale inspection."""
        with self._lock:
            event = super().undo()
            if event is not None:
                self.wall_revision += 1
            return event

    @property
    def shape_current(self) -> bool:
        """Whether the applied contours still describe the accepted wall revision."""
        return (
            self.shape_result is not None
            and self.shape_source_revision == self.wall_revision
        )

    @property
    def build_current(self) -> bool:
        """Whether the built mesh inherits the current applied Shape result."""
        return (
            self.build_result is not None
            and self.shape_current
            and self.build_source_revision == self.shape_revision
        )

    def apply_shape(
        self,
        joint_width: float = 0,
        distortion: float = 0,
        seed: int = 1,
        variation_scale: float = 6,
        *,
        source_revision: int | None = None,
    ) -> None:
        """Apply shared distortion and mortar atomically, reusing source topology by revision."""
        with self._lock:
            self._check_source_revision(source_revision, self.wall_revision, "Wall")
            try:
                settings = ShapeSettings(joint_width, distortion, seed, variation_scale)
                if self.shape_current and self.shape_result.settings == settings:
                    self.shape_events.append(
                        "Shape already current; no new processing needed."
                    )
                    return
                source = WallDescription.from_wall(self.wall)
                if (
                    settings.distortion
                    and self._shape_topology_revision != self.wall_revision
                ):
                    self._shape_topology = build_topology(source)
                    self._shape_topology_revision = self.wall_revision
                result = shape_wall(
                    source,
                    **settings.to_dict(),
                    topology=self._shape_topology if settings.distortion else None,
                )
            except (TypeError, ValueError) as error:
                self.shape_events.append(f"Apply failed: {error}")
                raise
            self.shape_result = result
            self.shape_revision += 1
            self.shape_source_revision = self.wall_revision
            self.shape_source_configuration = deepcopy(
                {
                    "id": self.generator_definition.id,
                    "label": self.generator_definition.label,
                    "category": self.generator_definition.category,
                    "parameters": self.generator_parameters,
                }
            )
            self.shape_events.append(
                f"Applied Shape to {len(result.stones)} stones: distortion {settings.distortion:g}, "
                f"joint width {settings.joint_width:g}, max movement {result.statistics.max_displacement:.3g} units "
                f"(Wall revision {self.wall_revision})."
            )

    def build_3d(
        self, settings: dict[str, Any], *, source_revision: int | None = None
    ) -> None:
        """Build only from a current applied Shape, keeping the previous mesh on failure."""
        with self._lock:
            self._check_source_revision(source_revision, self.shape_revision, "Shape")
            try:
                if not self.shape_current:
                    raise ValueError(
                        "Apply Shape to the current wall before building 3D"
                    )
                allowed = {
                    "mode",
                    "roundness",
                    "resolution",
                    "depth",
                    "primitive",
                    "tube_thickness",
                }
                if set(settings) - allowed:
                    raise ValueError("unknown 3D setting")
                config = {
                    **DEFAULT_BUILD_SETTINGS,
                    **settings,
                }
                if self.build_current and config == self.build_settings:
                    self.build_events.append(
                        "3D already current; reused the existing build."
                    )
                    return
                geometry = WallGeometry(
                    self.shape_result,
                    **{
                        k: config[k]
                        for k in ("mode", "roundness", "resolution", "depth")
                    },
                )
                result = geometry.to_dict(
                    primitive=config["primitive"],
                    tube_thickness=config["tube_thickness"],
                )
            except (TypeError, ValueError) as error:
                self.build_events.append(f"Build failed: {error}")
                raise
            self.build_result = result
            self.build_revision += 1
            self.build_shape_snapshot = deepcopy(self.shape_result.to_dict())
            self.build_shape_snapshot["source_configuration"] = deepcopy(
                self.shape_source_configuration
            )
            self.build_shape_snapshot["source_revision"] = self.shape_source_revision
            self.build_source_revision = self.shape_revision
            self.build_settings = config
            self.build_events.append(
                f"Built {len(result['stones'])} stones from Shape revision {self.shape_revision} "
                f"({config['mode']}, depth {config['depth']:g})."
            )

    @staticmethod
    def _check_source_revision(expected: int | None, actual: int, stage: str) -> None:
        """Reject a queued request for another source without modifying any stage."""
        if expected is None:
            return
        if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
            raise ValueError("source_revision must be a non-negative integer")
        if expected != actual:
            raise ValueError(
                f"{stage} changed before processing; refresh the current source and retry"
            )

    def export_stage(
        self, stage: str, *, scale: float = 1, revision: int | None = None
    ) -> tuple[bytes, str, str]:
        """Export a full applied revision, rejecting stale sources or changed requests."""
        with self._lock:
            revisions = {
                "wall": self.wall_revision,
                "shape": self.shape_revision,
                "3d": self.build_revision,
            }
            if stage not in revisions:
                raise ValueError("Unknown export stage")
            if revision is not None and revision != revisions[stage]:
                raise ValueError(
                    "The result changed; retry export from the current stage"
                )
            metadata = {"stage": stage, "revision": revisions[stage]}
            if stage == "wall":
                metadata["generator"] = super().to_dict()["generator"]
                content = wall_svg(self.wall, scale=scale, metadata=metadata)
            elif stage == "shape":
                if not self.shape_current:
                    raise ValueError(
                        "Apply Shape to the current wall before exporting SVG"
                    )
                metadata.update(
                    source_revision=self.shape_source_revision,
                    joint_width=self.shape_result.joint_width,
                    settings=self.shape_result.settings.to_dict(),
                    statistics=self.shape_result.statistics.to_dict(),
                    method="shared-warp-v1",
                    generator=self.shape_source_configuration,
                )
                content = wall_svg(self.shape_result, scale=scale, metadata=metadata)
            else:
                if not self.build_current:
                    raise ValueError(
                        "Build 3D from the current Shape before exporting STL"
                    )
                if self.build_settings["depth"] <= 0:
                    raise ValueError(
                        "Build with positive stone depth before exporting STL"
                    )
                content = mesh_stl(self.build_result, scale=scale)
            suffix = "stl" if stage == "3d" else "svg"
            mime = "model/stl" if stage == "3d" else "image/svg+xml"
            return content, mime, f"masonpy-{stage}-r{revisions[stage]}.{suffix}"

    def geometry_snapshot(self) -> dict[str, Any]:
        """Return the stored mesh and its inherited Shape for display without rebuilding."""
        with self._lock:
            return deepcopy(
                {
                    "revision": self.build_revision,
                    "source_revision": self.build_source_revision,
                    "wall_revision": self.build_shape_snapshot["source_revision"]
                    if self.build_result
                    else None,
                    "geometry": self.build_result,
                    "shape": self.build_shape_snapshot if self.build_result else None,
                }
            )

    def to_dict(self) -> dict[str, Any]:
        """Expose applied stage metadata and source snapshots without resending mesh buffers."""
        with self._lock:
            data = super().to_dict()
            data["wall_revision"] = self.wall_revision
            data["wall_report"] = self.wall_report()
            data["history"] = {
                "active": self.active_record,
                "entries": self._history_entries(),
            }
            data["shape"] = {
                "defaults": deepcopy(DEFAULT_SHAPE_SETTINGS),
                "revision": self.shape_revision,
                "source_revision": self.shape_source_revision,
                "current": self.shape_current,
                "result": self.shape_result.to_dict() if self.shape_result else None,
                "source_configuration": deepcopy(self.shape_source_configuration),
                "events": list(self.shape_events),
            }
            data["build"] = {
                "defaults": deepcopy(DEFAULT_BUILD_SETTINGS),
                "revision": self.build_revision,
                "source_revision": self.build_source_revision,
                "current": self.build_current,
                "present": self.build_result is not None,
                "settings": deepcopy(self.build_settings),
                "events": list(self.build_events),
            }
            return data
