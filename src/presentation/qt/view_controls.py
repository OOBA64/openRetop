"""Unified Qt/VTK viewport navigation cluster."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygon, QRegion
from PySide6.QtWidgets import QAbstractButton, QWidget

from presentation.qt.orientation_gizmo import (
    GIZMO_LOGICAL_MARGIN,
    GIZMO_LOGICAL_SIZE,
    OrientationGizmoController,
    OrientationGizmoDiagnosticState,
)


TRIANGLE_BUTTON_SIZE = 20
ROLL_BUTTON_SIZE = 24
CENTRAL_BUTTON_SIZE = 28
NAVIGATION_CONTROL_GAP = 2
NAVIGATION_GIZMO_OFFSET = TRIANGLE_BUTTON_SIZE + NAVIGATION_CONTROL_GAP
NAVIGATION_CLUSTER_WIDTH = GIZMO_LOGICAL_SIZE + 2 * NAVIGATION_GIZMO_OFFSET
NAVIGATION_CLUSTER_HEIGHT = NAVIGATION_CLUSTER_WIDTH + 27


@dataclass(frozen=True, slots=True)
class NavigationClusterDiagnosticState:
    gizmo: OrientationGizmoDiagnosticState
    controls_visible: bool
    central_fallback_visible: bool
    directional_button_count: int
    roll_button_count: int
    creation_count: int
    logical_bounds: tuple[int, int, int, int]
    last_error: str | None


class _PaintedNavigationButton(QAbstractButton):
    """Small transparent control with deterministic hover/press diagnostics."""

    def __init__(self, action_id: str, tooltip: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.action_id = str(action_id)
        self._hovered = False
        self.setToolTip(str(tooltip))
        self.setAccessibleName(str(tooltip))
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAutoFillBackground(False)

    @property
    def visual_state(self) -> str:
        if self.isDown():
            return "pressed"
        return "hovered" if self._hovered else "normal"

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802 - Qt API
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802 - Qt API
        self._hovered = False
        self.update()
        super().leaveEvent(event)


class TriangularViewButton(_PaintedNavigationButton):
    """Unlettered masked button whose transparent corners pass through."""

    def __init__(
        self,
        action_id: str,
        direction: str,
        tooltip: str,
        parent: QWidget,
    ) -> None:
        super().__init__(action_id, tooltip, parent)
        self.direction = str(direction)
        self.setFixedSize(TRIANGLE_BUTTON_SIZE, TRIANGLE_BUTTON_SIZE)
        self._update_mask()

    def hitButton(self, position: QPoint) -> bool:  # noqa: N802 - Qt API
        return self._polygon().containsPoint(position, Qt.OddEvenFill)

    def resizeEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        self._update_mask()
        super().resizeEvent(event)

    def paintEvent(self, _event: object) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        fill = QColor(71, 151, 205, 235) if self.isDown() else QColor(37, 48, 58, 220)
        if self._hovered and not self.isDown():
            fill = QColor(50, 89, 116, 235)
        painter.setBrush(fill)
        painter.setPen(QPen(QColor(190, 218, 235, 235), 1.15))
        painter.drawPolygon(self._polygon())

    def _update_mask(self) -> None:
        self.setMask(QRegion(self._polygon()))

    def _polygon(self) -> QPolygon:
        width = max(self.width(), 4)
        height = max(self.height(), 4)
        left, top, right, bottom = 1, 1, width - 2, height - 2
        center_x, center_y = width // 2, height // 2
        points = {
            "up": ((center_x, top), (right, bottom), (left, bottom)),
            "down": ((left, top), (right, top), (center_x, bottom)),
            "left": ((left, center_y), (right, top), (right, bottom)),
            "right": ((left, top), (right, center_y), (left, bottom)),
        }[self.direction]
        return QPolygon([QPoint(x_value, y_value) for x_value, y_value in points])


class RollViewButton(_PaintedNavigationButton):
    """Circular button painted as a clockwise or counterclockwise arrow."""

    def __init__(
        self,
        action_id: str,
        *,
        clockwise: bool,
        tooltip: str,
        parent: QWidget,
    ) -> None:
        super().__init__(action_id, tooltip, parent)
        self.clockwise = bool(clockwise)
        self.setFixedSize(ROLL_BUTTON_SIZE, ROLL_BUTTON_SIZE)
        self.setMask(QRegion(self.rect(), QRegion.Ellipse))

    def hitButton(self, position: QPoint) -> bool:  # noqa: N802 - Qt API
        center = self.rect().center()
        radius = min(self.width(), self.height()) * 0.5 - 1.0
        return (position.x() - center.x()) ** 2 + (position.y() - center.y()) ** 2 <= radius**2

    def resizeEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        self.setMask(QRegion(self.rect(), QRegion.Ellipse))
        super().resizeEvent(event)

    def paintEvent(self, _event: object) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        fill = QColor(64, 132, 178, 235) if self.isDown() else QColor(32, 43, 52, 218)
        if self._hovered and not self.isDown():
            fill = QColor(45, 77, 99, 235)
        painter.setBrush(fill)
        painter.setPen(QPen(QColor(183, 215, 234, 235), 1.0))
        painter.drawEllipse(self.rect().adjusted(1, 1, -2, -2))

        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#F0F7FB"), 1.7, Qt.SolidLine, Qt.RoundCap))
        arc_rect = self.rect().adjusted(5, 5, -5, -5)
        start = 35 * 16 if self.clockwise else 145 * 16
        span = -255 * 16 if self.clockwise else 255 * 16
        painter.drawArc(arc_rect, start, span)
        if self.clockwise:
            arrow = QPolygon([QPoint(17, 15), QPoint(20, 18), QPoint(15, 19)])
        else:
            arrow = QPolygon([QPoint(7, 15), QPoint(4, 18), QPoint(9, 19)])
        painter.setBrush(QColor("#F0F7FB"))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(arrow)


class CentralGizmoButton(_PaintedNavigationButton):
    """Compact isometric hit target centered over the VTK axes."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__("view.named.isometric", "Isometric View", parent)
        self._fallback_visible = False
        self._end_on_axis: str | None = None
        self.setFixedSize(CENTRAL_BUTTON_SIZE, CENTRAL_BUTTON_SIZE)
        self._update_mask()

    @property
    def fallback_visible(self) -> bool:
        return self._fallback_visible

    def set_fallback_visible(self, visible: bool) -> None:
        if self._fallback_visible == bool(visible):
            return
        self._fallback_visible = bool(visible)
        self.update()

    def set_end_on_axis(self, axis: str | None) -> None:
        normalized = str(axis).upper() if axis in {"X", "Y", "Z"} else None
        if normalized == self._end_on_axis:
            return
        self._end_on_axis = normalized
        self.update()

    def hitButton(self, position: QPoint) -> bool:  # noqa: N802 - Qt API
        center = self.rect().center()
        radius = min(self.width(), self.height()) * 0.48
        return (position.x() - center.x()) ** 2 + (position.y() - center.y()) ** 2 <= radius**2

    def resizeEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        self._update_mask()
        super().resizeEvent(event)

    def paintEvent(self, _event: object) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        circle = self.rect().adjusted(1, 1, -2, -2)
        fill = QColor(38, 50, 59, 238) if self._fallback_visible else QColor(20, 27, 33, 230)
        if self._hovered:
            fill = QColor(48, 91, 118, 242)
        if self.isDown():
            fill = QColor(61, 139, 185, 245)
        painter.setBrush(fill)
        painter.setPen(QPen(QColor(164, 205, 229, 225), 1.1))
        painter.drawEllipse(circle)
        self._paint_isometric_cube(painter)
        if not self._fallback_visible and self._end_on_axis is not None:
            colors = {"X": "#FF3B30", "Y": "#39F05A", "Z": "#3D78FF"}
            font = painter.font()
            font.setBold(True)
            font.setPixelSize(9)
            painter.setFont(font)
            painter.setPen(QColor(colors[self._end_on_axis]))
            painter.drawText(QRect(2, 16, 10, 10), Qt.AlignCenter, self._end_on_axis)

    def _update_mask(self) -> None:
        margin = 1
        self.setMask(QRegion(self.rect().adjusted(margin, margin, -margin, -margin), QRegion.Ellipse))

    def _paint_isometric_cube(self, painter: QPainter) -> None:
        center = self.rect().center()
        x_value, y_value = center.x(), center.y()
        top = QPoint(x_value, y_value - 8)
        left = QPoint(x_value - 7, y_value - 4)
        right = QPoint(x_value + 7, y_value - 4)
        middle = QPoint(x_value, y_value)
        lower_left = QPoint(x_value - 7, y_value + 4)
        lower_right = QPoint(x_value + 7, y_value + 4)
        bottom = QPoint(x_value, y_value + 8)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#EAF5FB"), 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for first, second in (
            (top, left), (top, right), (left, middle), (right, middle),
            (left, lower_left), (right, lower_right), (middle, bottom),
            (lower_left, bottom), (lower_right, bottom),
        ):
            painter.drawLine(first, second)


class ViewportNavigationCluster(QObject):
    """Own one orientation renderer and its six surrounding Qt controls."""

    action_requested = Signal(str)

    _DIRECTION_SPECS = (
        ("view.named.top", "up", "Top View"),
        ("view.named.bottom", "down", "Bottom View"),
        ("view.named.left", "left", "Left View"),
        ("view.named.right", "right", "Right View"),
    )

    def __init__(
        self,
        render_window: object | None,
        main_renderer: object | None,
        interactor: object | None,
        parent: QWidget,
        *,
        device_pixel_ratio: Callable[[], float] | None = None,
    ) -> None:
        super().__init__(parent)
        self.parent_widget = parent
        self.orientation_gizmo = OrientationGizmoController(
            render_window,
            main_renderer,
            interactor,
            device_pixel_ratio=device_pixel_ratio,
        )
        self._controls_visible = False
        self._gizmo_visible = False
        self._closed = False
        self._creation_count = 1
        self._logical_bounds = (GIZMO_LOGICAL_MARGIN, GIZMO_LOGICAL_MARGIN, 0, 0)
        self._last_error: str | None = None

        self.direction_buttons: dict[str, TriangularViewButton] = {}
        for action_id, direction, tooltip in self._DIRECTION_SPECS:
            button = TriangularViewButton(action_id, direction, tooltip, parent)
            self._connect(button)
            self.direction_buttons[action_id] = button

        self.roll_buttons: dict[str, RollViewButton] = {
            "view.roll_left": RollViewButton(
                "view.roll_left",
                clockwise=False,
                tooltip="Roll View Left 15 degrees",
                parent=parent,
            ),
            "view.roll_right": RollViewButton(
                "view.roll_right",
                clockwise=True,
                tooltip="Roll View Right 15 degrees",
                parent=parent,
            ),
        }
        for button in self.roll_buttons.values():
            self._connect(button)

        self.central_button = CentralGizmoButton(parent)
        self._connect(self.central_button)
        self.buttons: dict[str, QAbstractButton] = {
            **self.direction_buttons,
            **self.roll_buttons,
            self.central_button.action_id: self.central_button,
        }
        for button in self.buttons.values():
            button.hide()

    @property
    def visible(self) -> bool:
        return self._controls_visible

    @property
    def logical_bounds(self) -> tuple[int, int, int, int]:
        return self._logical_bounds

    def start(self) -> bool:
        if self._closed:
            return False
        started = self.orientation_gizmo.start()
        self.update_layout()
        return started

    def set_visibility(self, *, gizmo: bool, controls: bool) -> None:
        self._gizmo_visible = bool(gizmo)
        self._controls_visible = bool(controls)
        self.orientation_gizmo.set_enabled(self._gizmo_visible)
        self.central_button.set_fallback_visible(
            self._controls_visible and not self._gizmo_visible
        )
        for button in self.buttons.values():
            button.setVisible(self._controls_visible)
            if self._controls_visible:
                button.raise_()
        self.update_layout()

    def set_visible(self, visible: bool) -> None:
        """Compatibility setter for the independent controls preference."""

        self.set_visibility(gizmo=self._gizmo_visible, controls=visible)

    def update_layout(self) -> bool:
        if self._closed:
            return False
        width = max(int(self.parent_widget.width()), 0)
        height = max(int(self.parent_widget.height()), 0)
        origin_x = min(
            GIZMO_LOGICAL_MARGIN,
            max(width - NAVIGATION_CLUSTER_WIDTH, 0),
        )
        origin_y = min(
            GIZMO_LOGICAL_MARGIN,
            max(height - NAVIGATION_CLUSTER_HEIGHT, 0),
        )
        center_x = origin_x + NAVIGATION_GIZMO_OFFSET
        center_y = origin_y + NAVIGATION_GIZMO_OFFSET
        triangle_center_offset = (GIZMO_LOGICAL_SIZE - TRIANGLE_BUTTON_SIZE) // 2

        positions = {
            "view.named.top": (center_x + triangle_center_offset, origin_y),
            "view.named.bottom": (
                center_x + triangle_center_offset,
                center_y + GIZMO_LOGICAL_SIZE + NAVIGATION_CONTROL_GAP,
            ),
            "view.named.left": (origin_x, center_y + triangle_center_offset),
            "view.named.right": (
                center_x + GIZMO_LOGICAL_SIZE + NAVIGATION_CONTROL_GAP,
                center_y + triangle_center_offset,
            ),
        }
        for action_id, position in positions.items():
            self.direction_buttons[action_id].move(*position)

        roll_y = (
            origin_y
            + NAVIGATION_GIZMO_OFFSET
            + GIZMO_LOGICAL_SIZE
            + TRIANGLE_BUTTON_SIZE
            + 5
        )
        roll_pair_width = 2 * ROLL_BUTTON_SIZE + 10
        roll_x = origin_x + (NAVIGATION_CLUSTER_WIDTH - roll_pair_width) // 2
        self.roll_buttons["view.roll_left"].move(roll_x, roll_y)
        self.roll_buttons["view.roll_right"].move(
            roll_x + ROLL_BUTTON_SIZE + 10,
            roll_y,
        )
        central_inset = (GIZMO_LOGICAL_SIZE - CENTRAL_BUTTON_SIZE) // 2
        self.central_button.move(center_x + central_inset, center_y + central_inset)
        for button in self.buttons.values():
            if button.isVisible():
                button.raise_()

        self._logical_bounds = (
            origin_x,
            origin_y,
            min(NAVIGATION_CLUSTER_WIDTH, width),
            min(NAVIGATION_CLUSTER_HEIGHT, height),
        )
        changed = self.orientation_gizmo.update_layout(
            logical_left=center_x,
            logical_top=center_y,
        )
        self._last_error = self.orientation_gizmo.diagnostic_state().last_error
        return changed

    def sync_camera(self, *, force: bool = False) -> bool:
        changed = self.orientation_gizmo.sync_camera(force=force)
        signature = self.orientation_gizmo.camera_signature
        end_on_axis = None
        if signature is not None:
            direction = signature[:3]
            index = max(range(3), key=lambda value: abs(direction[value]))
            if abs(direction[index]) >= 0.90:
                end_on_axis = ("X", "Y", "Z")[index]
        self.central_button.set_end_on_axis(end_on_axis)
        return changed

    def close(self) -> None:
        if self._closed:
            return
        for button in self.buttons.values():
            button.hide()
        self.orientation_gizmo.close()
        self._closed = True

    def diagnostic_state(self) -> NavigationClusterDiagnosticState:
        return NavigationClusterDiagnosticState(
            gizmo=self.orientation_gizmo.diagnostic_state(),
            controls_visible=self._controls_visible,
            central_fallback_visible=self.central_button.fallback_visible,
            directional_button_count=len(self.direction_buttons),
            roll_button_count=len(self.roll_buttons),
            creation_count=self._creation_count,
            logical_bounds=self._logical_bounds,
            last_error=self._last_error,
        )

    def _connect(self, button: _PaintedNavigationButton) -> None:
        button.clicked.connect(
            lambda _checked=False, value=button.action_id: self.action_requested.emit(value)
        )


__all__ = (
    "CentralGizmoButton",
    "CENTRAL_BUTTON_SIZE",
    "NAVIGATION_CLUSTER_HEIGHT",
    "NAVIGATION_CLUSTER_WIDTH",
    "NAVIGATION_CONTROL_GAP",
    "NAVIGATION_GIZMO_OFFSET",
    "NavigationClusterDiagnosticState",
    "ROLL_BUTTON_SIZE",
    "RollViewButton",
    "TRIANGLE_BUTTON_SIZE",
    "TriangularViewButton",
    "ViewportNavigationCluster",
)
