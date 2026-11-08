"""Host-independent validation of optional extrusion detail controls."""

from __future__ import annotations

import math


def validate_details(depth_variation: float, detail_seed: int, bevel: float) -> None:
    """Validate geometry-independent controls for both config import and mesh builds."""
    for name, value, upper in (
        ("depth variation", depth_variation, 0.9),
        ("bevel", bevel, math.inf),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 <= value <= upper
        ):
            raise ValueError(
                f"{name} must be finite, non-negative"
                + (" and at most 0.9" if name == "depth variation" else "")
            )
    if (
        isinstance(detail_seed, bool)
        or not isinstance(detail_seed, int)
        or not 0 <= detail_seed <= 2147483647
    ):
        raise ValueError("3D detail seed must be an integer from 0 to 2147483647")
