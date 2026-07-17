"""Qt-only named-view controls layered beside the VTK orientation gizmo."""

from __future__ import annotations

from PySide6.QtCore import QObject, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygon, QRegion
from PySide6.QtWidgets import QAbstractButton, QWidget


_BUTTON_SIZE = 28
_BUTTON_GAP = 2


class TriangularViewButton(QAbstractButton):
    """A masked button whose non-triangular corners pass through to VTK."""

    def __init__(
        self,
        label: str,
        direction: str,
        tooltip: str,
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self._label = str(label)
        self._direction = str(direction)
        self.setFixedSize(_BUTTON_SIZE, _BUTTON_SIZE)
        self.setToolTip(str(tooltip))
        self.setAccessibleName(str(tooltip))
        self.setFocusPolicy(Qt.NoFocus)
        self._update_mask()

    def hitButton(self, position: QPoint) -> bool:  # noqa: N802 - Qt API
        return self._polygon().containsPoint(position, Qt.OddEvenFill)

    def resizeEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        self._update_mask()
        super().resizeEvent(event)

    def paintEvent(self, _event: object) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        fill = QColor("#4C9ED9") if self.isDown() else QColor("#303B45")
        if self.underMouse() and not self.isDown():
            fill = QColor("#3D596E")
        painter.setBrush(fill)
        painter.setPen(QPen(QColor("#AFC7D8"), 1.0))
        painter.drawPolygon(self._polygon())
        painter.setPen(QColor("#F1F6F9"))
        painter.drawText(self.rect(), Qt.AlignCenter, self._label)

    def _update_mask(self) -> None:
        self.setMask(QRegion(self._polygon()))

    def _polygon(self) -> QPolygon:
        width = max(self.width(), 4)
        height = max(self.height(), 4)
        left, top, right, bottom = 2, 2, width - 3, height - 3
        center_x, center_y = width // 2, height // 2
        points = {
            "up": ((center_x, top), (right, bottom), (left, bottom)),
            "down": ((left, top), (right, top), (center_x, bottom)),
            "left": ((left, center_y), (right, top), (right, bottom)),
            "right": ((left, top), (right, center_y), (left, bottom)),
            "up_right": ((left, bottom), (right, top), (right, bottom)),
        }.get(self._direction, ((center_x, top), (right, bottom), (left, bottom)))
        return QPolygon([QPoint(x_value, y_value) for x_value, y_value in points])


class ViewControlCluster(QObject):
    """Manage individually masked child buttons without a blocking container."""

    action_requested = Signal(str)

    _SPECS = (
        ("view.named.top", "T", "up", "Top view", 0, 0),
        ("view.named.bottom", "B", "down", "Bottom view", 0, 1),
        ("view.named.front", "F", "up", "Front view", 1, 0),
        ("view.named.back", "K", "down", "Back view", 1, 1),
        ("view.named.left", "L", "left", "Left view", 2, 0),
        ("view.named.right", "R", "right", "Right view", 2, 1),
        ("view.named.isometric", "I", "up_right", "Isometric view", 3, 0),
    )

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._visible = False
        self.buttons: dict[str, TriangularViewButton] = {}
        for action_id, label, direction, tooltip, _column, _row in self._SPECS:
            button = TriangularViewButton(label, direction, tooltip, parent)
            button.clicked.connect(
                lambda _checked=False, value=action_id: self.action_requested.emit(value)
            )
            button.hide()
            self.buttons[action_id] = button

    @property
    def visible(self) -> bool:
        return self._visible

    def set_visible(self, visible: bool) -> None:
        self._visible = bool(visible)
        for button in self.buttons.values():
            button.setVisible(self._visible)
            if visible:
                button.raise_()

    def reposition(self, x_position: int, y_position: int) -> None:
        for action_id, _label, _direction, _tooltip, column, row in self._SPECS:
            button = self.buttons[action_id]
            button.move(
                int(x_position) + column * (_BUTTON_SIZE + _BUTTON_GAP),
                int(y_position) + row * (_BUTTON_SIZE + _BUTTON_GAP),
            )
            if button.isVisible():
                button.raise_()


__all__ = ("TriangularViewButton", "ViewControlCluster")
