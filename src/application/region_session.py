"""Authoritative transient state for the region-selection workflow."""

from __future__ import annotations

from dataclasses import dataclass
import math

from regions.region_state import (
    DEFAULT_REGION_MAX_TRIANGLES,
    DEFAULT_REGION_THRESHOLD_DEGREES,
)


@dataclass
class RegionSessionState:
    """Own pointer-routing and configuration state for Region Select.

    Screen-space picking remains a presentation concern.  The session only
    remembers enough resolved input to distinguish a click from a camera drag
    and to repeat a region grow from its last seed.
    """

    active: bool = False
    threshold_degrees: float = DEFAULT_REGION_THRESHOLD_DEGREES
    max_triangle_count: int = DEFAULT_REGION_MAX_TRIANGLES
    left_press_position: tuple[int, int] | None = None
    left_dragged: bool = False
    current_seed_triangle_index: int | None = None
    last_hit_triangle_index: int | None = None
    drag_threshold_pixels: int = 4

    def reset(self) -> None:
        self.active = False
        self.threshold_degrees = DEFAULT_REGION_THRESHOLD_DEGREES
        self.max_triangle_count = DEFAULT_REGION_MAX_TRIANGLES
        self.clear_pointer()
        self.current_seed_triangle_index = None
        self.last_hit_triangle_index = None

    def begin(self) -> None:
        self.active = True
        self.clear_pointer()
        self.last_hit_triangle_index = None

    def exit(self) -> None:
        self.active = False
        self.clear_pointer()
        self.current_seed_triangle_index = None
        self.last_hit_triangle_index = None

    def clear_pointer(self) -> None:
        self.left_press_position = None
        self.left_dragged = False

    def configure(
        self,
        *,
        threshold_degrees: float | None = None,
        max_triangle_count: int | None = None,
    ) -> bool:
        changed = False
        if threshold_degrees is not None:
            threshold = float(threshold_degrees)
            if not math.isfinite(threshold) or threshold < 0.0 or threshold > 90.0:
                raise ValueError("Region threshold must be between 0 and 90 degrees.")
            if threshold != self.threshold_degrees:
                self.threshold_degrees = threshold
                changed = True
        if max_triangle_count is not None:
            maximum = int(max_triangle_count)
            if maximum < 1 or maximum > 10_000_000:
                raise ValueError(
                    "Region maximum triangle count must be between 1 and 10,000,000."
                )
            if maximum != self.max_triangle_count:
                self.max_triangle_count = maximum
                changed = True
        return changed

    def press(self, x_position: int, y_position: int) -> None:
        self.left_press_position = (int(x_position), int(y_position))
        self.left_dragged = False

    def motion(self, x_position: int, y_position: int) -> bool:
        start = self.left_press_position
        if start is None:
            return False
        distance = abs(int(x_position) - start[0]) + abs(int(y_position) - start[1])
        if distance > int(self.drag_threshold_pixels):
            self.left_dragged = True
        return self.left_dragged

    def release_is_click(self, x_position: int, y_position: int) -> bool:
        if self.left_press_position is None:
            return False
        self.motion(x_position, y_position)
        is_click = not self.left_dragged
        self.clear_pointer()
        return is_click

    def set_seed(self, triangle_index: int | None) -> None:
        if triangle_index is None:
            self.current_seed_triangle_index = None
            self.last_hit_triangle_index = None
            return
        seed = int(triangle_index)
        if seed < 0:
            raise ValueError("Region seed triangle index must be non-negative.")
        self.current_seed_triangle_index = seed
        self.last_hit_triangle_index = seed


__all__ = ("RegionSessionState",)
