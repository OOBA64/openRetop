"""Small, toolkit-neutral state machine for viewport click/drag gestures."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class PointerRelease:
    """Classification of one completed primary-button gesture."""

    had_press: bool
    is_click: bool
    distance: float


class PointerGestureState:
    """Separate selection clicks from drags in Qt logical pixels.

    Qt 6 pointer positions are device-independent, so the default four-pixel
    threshold has the same physical intent at every display scale.  The class
    deliberately knows nothing about VTK, selection, or openRetop tools.
    """

    def __init__(self, drag_threshold: float = 4.0) -> None:
        threshold = float(drag_threshold)
        if not math.isfinite(threshold) or threshold < 0.0:
            raise ValueError("drag_threshold must be a finite non-negative value.")
        self.drag_threshold = threshold
        self.press_position: tuple[float, float] | None = None
        self.current_position: tuple[float, float] | None = None
        self.dragged = False

    @property
    def active(self) -> bool:
        return self.press_position is not None

    def press(self, x_position: float, y_position: float) -> None:
        position = _position(x_position, y_position)
        self.press_position = position
        self.current_position = position
        self.dragged = False

    def motion(self, x_position: float, y_position: float) -> bool:
        position = _position(x_position, y_position)
        self.current_position = position
        if self.press_position is not None:
            self.dragged = self.dragged or (
                _distance(self.press_position, position) > self.drag_threshold
            )
        return self.dragged

    def release(self, x_position: float, y_position: float) -> PointerRelease:
        position = _position(x_position, y_position)
        start = self.press_position
        distance = 0.0 if start is None else _distance(start, position)
        result = PointerRelease(
            had_press=start is not None,
            is_click=start is not None and not self.dragged and distance <= self.drag_threshold,
            distance=distance,
        )
        self.cancel()
        return result

    def cancel(self) -> None:
        self.press_position = None
        self.current_position = None
        self.dragged = False


def _position(x_position: float, y_position: float) -> tuple[float, float]:
    x_value = float(x_position)
    y_value = float(y_position)
    if not (math.isfinite(x_value) and math.isfinite(y_value)):
        raise ValueError("Pointer positions must be finite.")
    return (x_value, y_value)


def _distance(first: tuple[float, float], second: tuple[float, float]) -> float:
    return math.hypot(second[0] - first[0], second[1] - first[1])


__all__ = ("PointerGestureState", "PointerRelease")
