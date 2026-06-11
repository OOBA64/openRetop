"""Interaction state captured when a viewport transform starts."""

from __future__ import annotations

from dataclasses import dataclass

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
