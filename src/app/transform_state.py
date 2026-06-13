"""Interaction state captured when a viewport transform starts."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class ActiveTransformState:
    """Start values for one viewport hotkey transform."""

    selected_item: str
    mode: str
    mouse_start: tuple[int, int]
    axis_constraint: str | None
    location: np.ndarray
    rotation: np.ndarray
    section_axis: str
    section_offset: float
    section_origin: np.ndarray = field(
        default_factory=lambda: np.asarray([0.0, 0.0, 0.0], dtype=float)
    )
    section_normal: np.ndarray = field(
        default_factory=lambda: np.asarray([0.0, 0.0, 1.0], dtype=float)
    )
