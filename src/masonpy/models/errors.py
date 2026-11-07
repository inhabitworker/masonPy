"""Placement validation errors for logical wall operations."""

from __future__ import annotations


class PlacementError(ValueError):
    """Raised when a stone cannot be placed on a wall."""
