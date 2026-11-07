"""Successful placements and their original decision snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field

from masonpy.models import Stone


@dataclass(frozen=True, slots=True)
class GenerationEvent:
    """A successful placement plus human-readable decision context."""

    stone: Stone
    explanation: str
    decision: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready representation of the current object or snapshot."""
        return {
            "stone": self.stone.to_dict(),
            "explanation": self.explanation,
            "decision": self.decision,
        }
