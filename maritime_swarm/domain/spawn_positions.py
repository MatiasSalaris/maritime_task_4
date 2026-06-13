"""Spawn generation for repeatable or random demo runs."""

from __future__ import annotations

import random


def random_spawn_positions(seed: int | None = None) -> dict[str, tuple[float, float]]:
    """Return varied but demo-safe spawn positions for all three assets."""
    rng = random.Random(seed)
    return {
        "USV-1": (round(rng.uniform(6.0, 22.0), 1), round(rng.uniform(12.0, 32.0), 1)),
        "USV-2": (round(rng.uniform(36.0, 50.0), 1), round(rng.uniform(30.0, 46.0), 1)),
        "USV-3": (round(rng.uniform(82.0, 104.0), 1), round(rng.uniform(12.0, 30.0), 1)),
    }
