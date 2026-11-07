"""Strict terminal failures, distinct from invalid individual placements."""

from __future__ import annotations

from typing import Any


class ConstructionFailure(RuntimeError):
    """A bounded construction attempt has no accepted continuation."""

    def __init__(
        self,
        x: int,
        y: int,
        reason: str,
        rejected: int = 0,
        *,
        retry_possible: bool = True,
        kind: str = "no_continuation",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialise configuration and local state; no generation is performed here."""
        self.x, self.y, self.reason, self.rejected = x, y, reason, rejected
        self.retry_possible = retry_possible
        self.kind = kind
        self.details = dict(details or {})
        advice = (
            "This attempt failed; another earlier sequence may succeed."
            if retry_possible
            else "Change the configuration before retrying."
        )
        super().__init__(f"Construction stopped at ({x}, {y}): {reason} {advice}")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation of the current object or snapshot."""
        return {
            "x": self.x,
            "y": self.y,
            "reason": self.reason,
            "rejected": self.rejected,
            "message": str(self),
            "retry_possible": self.retry_possible,
            "kind": self.kind,
            "details": self.details,
        }
