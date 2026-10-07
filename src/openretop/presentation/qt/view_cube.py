"""Clickable orientation cube for the viewport.

The cube mirrors the main camera: each visible face is labelled (FRONT, BACK, LEFT,
RIGHT, TOP, BOTTOM) and every face, edge and corner is a click target that snaps the
camera to that direction.  Faces are split 3x3 like a conventional CAD view cube: the
centre is the face view, the border strips are edge views, and the corners are
three-face (isometric style) views.

Geometry and hit-testing are pure functions of the camera orientation so they can be
unit-tested without Qt; :class:`ViewCubeWidget` only paints them.

World convention matches ``viewer.camera_controller.named_view_vectors``: +Z is up,
FRONT is the face at -Y, RIGHT is the face at +X.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QMouseEvent,
    QPainter,
    QPen,
    QPolygonF,
    QTransform,
)
from PySide6.QtWidgets import QWidget

Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]

CUBE_WIDGET_SIZE = 160
CUBE_MARGIN = 10
CUBE_SCALE = 40.0  # pixels per cube half-edge
_BAND = 0.5  # |local coordinate| beyond this on a face is an edge/corner strip
_MIN_FACING = 0.02  # faces nearly edge-on are not drawn or clickable
_ROLL_DEGREES_TEXT = "15 degrees"

_NAMES: dict[Vec3, str] = {
    (0.0, -1.0, 0.0): "front",
    (0.0, 1.0, 0.0): "back",
    (-1.0, 0.0, 0.0): "left",
    (1.0, 0.0, 0.0): "right",
    (0.0, 0.0, 1.0): "top",
    (0.0, 0.0, -1.0): "bottom",
}
_ORDER = ("top", "bottom", "front", "back", "left", "right")
# name, outward normal, label "right" axis, label "up" axis (u x v == normal, so text
# reads upright and unmirrored whenever the face is visible).
_FACES: tuple[tuple[str, Vec3, Vec3, Vec3], ...] = (
    ("front", (0.0, -1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    ("back", (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    ("left", (-1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
    ("right", (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    ("top", (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    ("bottom", (0.0, 0.0, -1.0), (-1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
)
HOME_ACTION = "view.named.isometric"
ROLL_LEFT_ACTION = "view.roll_left"
ROLL_RIGHT_ACTION = "view.roll_right"


@dataclass(frozen=True, slots=True)
class ProjectedFace:
    """A visible cube face in view space (x right, y up, cube half-edge = 1)."""

    name: str
    normal: Vec3
    centre: Vec2
    u: Vec2
    v: Vec2
    facing: float  # cosine of the angle between the face normal and the viewer


def normalized_camera_orientation(
    direction: Iterable[object],
    view_up: Iterable[object],
) -> tuple[Vec3, Vec3] | None:
    """Finite unit forward vector and an up vector orthogonal to it, or None."""

    forward = _unit(direction)
    up = _unit(view_up)
    if forward is None or up is None:
        return None
    projection = _dot(up, forward)
    corrected = _unit(tuple(up[i] - projection * forward[i] for i in range(3)))
    if corrected is None:
        candidate = min(
            ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            key=lambda axis: abs(_dot(axis, forward)),
        )
        projection = _dot(candidate, forward)
        corrected = _unit(tuple(candidate[i] - projection * forward[i] for i in range(3)))
    if corrected is None:
        return None
    return forward, corrected


def project_faces(forward: Vec3, up: Vec3) -> tuple[ProjectedFace, ...]:
    """Visible faces, most camera-facing first."""

    right = _cross(forward, up)

    def screen(vector: Vec3) -> Vec2:
        return (_dot(vector, right), _dot(vector, up))

    faces = []
    for name, normal, u_axis, v_axis in _FACES:
        facing = -_dot(normal, forward)
        if facing <= _MIN_FACING:
            continue
        faces.append(ProjectedFace(name, normal, screen(normal), screen(u_axis), screen(v_axis), facing))
    return tuple(sorted(faces, key=lambda face: -face.facing))


def view_name(normals: Iterable[Vec3]) -> str:
    """Canonical name such as ``front``, ``top+right`` or ``top+front+right``."""

    names = {_NAMES[tuple(float(round(c)) for c in normal)] for normal in normals}  # type: ignore[index]
    return "+".join(name for name in _ORDER if name in names)


def view_title(name: str) -> str:
    parts = name.split("+")
    if len(parts) == 1:
        return f"{parts[0].capitalize()} view"
    kind = "edge" if len(parts) == 2 else "corner"
    return f"{'-'.join(part.capitalize() for part in parts)} {kind}"


def _cell(value: float) -> int:
    if value < -_BAND:
        return -1
    return 1 if value > _BAND else 0


def cell_view_name(face: ProjectedFace, i: int, j: int) -> str:
    """The view name for cell (i, j) of a face, with i along u and j along v."""

    face_def = next(item for item in _FACES if item[0] == face.name)
    normals = [face.normal]
    if i:
        normals.append(tuple(i * c for c in face_def[2]))  # type: ignore[arg-type]
    if j:
        normals.append(tuple(j * c for c in face_def[3]))  # type: ignore[arg-type]
    return view_name(normals)  # type: ignore[arg-type]


def locate(faces: Iterable[ProjectedFace], x: float, y: float) -> str | None:
    """View name under the view-space point (x, y), or None."""

    for face in faces:
        local = _local_coordinates(face, x, y)
        if local is None:
            continue
        a, b = local
        if abs(a) <= 1.0 and abs(b) <= 1.0:
            return cell_view_name(face, _cell(a), _cell(b))
    return None


def _local_coordinates(face: ProjectedFace, x: float, y: float) -> Vec2 | None:
    det = face.u[0] * face.v[1] - face.u[1] * face.v[0]
    if abs(det) < 1e-6:
        return None
    dx, dy = x - face.centre[0], y - face.centre[1]
    return ((dx * face.v[1] - dy * face.v[0]) / det, (face.u[0] * dy - face.u[1] * dx) / det)


@dataclass(frozen=True, slots=True)
class CubeHit:
    action_id: str
    title: str


class ViewCubeWidget(QWidget):
    """Paints the cube, its home/roll buttons and an axis triad, and hit-tests them.

    A Qt child widget cannot draw over QVTK's native OpenGL surface, so in the app this
    widget is never shown: the cluster renders it to an image (:meth:`render_image`),
    displays that inside the VTK frame, and forwards mouse events to :meth:`hit_at`.
    It also works as an ordinary widget (used directly in tests).
    """

    action_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("view_cube")
        self.setFixedSize(CUBE_WIDGET_SIZE, CUBE_WIDGET_SIZE)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._forward: Vec3 = (0.0, 1.0, 0.0)
        self._up: Vec3 = (0.0, 0.0, 1.0)
        self._faces = project_faces(self._forward, self._up)
        self._show_cube = True
        self._show_triad = True
        self._hover: str | None = None  # a view name, HOME_ACTION, or a roll action
        self._pressed: str | None = None

    # -- state --------------------------------------------------------------------

    @property
    def faces(self) -> tuple[ProjectedFace, ...]:
        return self._faces

    @property
    def hover(self) -> str | None:
        return self._hover

    @property
    def orientation(self) -> tuple[Vec3, Vec3]:
        return (self._forward, self._up)

    def set_parts(self, *, cube: bool, triad: bool) -> None:
        if (cube, triad) == (self._show_cube, self._show_triad):
            return
        self._show_cube, self._show_triad = bool(cube), bool(triad)
        self._hover = None
        self.update()

    def set_hover(self, key: str | None) -> bool:
        """Highlight a region (a hit's action id); returns True if it changed."""

        if key == self._hover:
            return False
        self._hover = key
        self.update()
        return True

    def render_image(self, device_pixel_ratio: float = 1.0) -> QImage:
        """The cube as a straight-alpha RGBA image (CUBE_WIDGET_SIZE logical pixels square)."""

        ratio = max(float(device_pixel_ratio), 1.0)
        size = round(CUBE_WIDGET_SIZE * ratio)
        image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(ratio)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        self._paint(painter)
        painter.end()
        return image.convertToFormat(QImage.Format.Format_RGBA8888)

    def set_orientation(self, forward: Vec3, up: Vec3) -> None:
        self._forward, self._up = forward, up
        self._faces = project_faces(forward, up)
        self.update()

    # -- geometry -----------------------------------------------------------------

    @property
    def _centre(self) -> QPointF:
        return QPointF(CUBE_WIDGET_SIZE / 2.0, CUBE_WIDGET_SIZE / 2.0)

    def _to_view(self, point: QPointF) -> Vec2:
        return ((point.x() - self._centre.x()) / CUBE_SCALE, (self._centre.y() - point.y()) / CUBE_SCALE)

    def _button_rect(self, action_id: str) -> QRectF:
        size = 24.0
        if action_id == HOME_ACTION:
            return QRectF(CUBE_MARGIN - 6, CUBE_MARGIN - 6, size, size)
        if action_id == ROLL_LEFT_ACTION:
            return QRectF(CUBE_WIDGET_SIZE - size - CUBE_MARGIN + 6, CUBE_MARGIN - 6, size, size)
        return QRectF(CUBE_WIDGET_SIZE - size - CUBE_MARGIN + 6, CUBE_WIDGET_SIZE - size - CUBE_MARGIN + 6, size, size)

    _BUTTONS = (HOME_ACTION, ROLL_LEFT_ACTION, ROLL_RIGHT_ACTION)

    def hit_at(self, point: QPointF) -> CubeHit | None:
        """What a click at ``point`` (widget pixels) would do, or None."""

        if not self._show_cube:
            return None
        for action_id in self._BUTTONS:
            if self._button_rect(action_id).contains(point):
                titles = {
                    HOME_ACTION: "Isometric view (Ctrl+7)",
                    ROLL_LEFT_ACTION: f"Roll view left {_ROLL_DEGREES_TEXT}",
                    ROLL_RIGHT_ACTION: f"Roll view right {_ROLL_DEGREES_TEXT}",
                }
                return CubeHit(action_id, titles[action_id])
        name = locate(self._faces, *self._to_view(point))
        if name is None:
            return None
        return CubeHit(f"view.named.{name}", view_title(name))

    # -- input --------------------------------------------------------------------

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        hit = self.hit_at(event.position())
        key = None if hit is None else hit.action_id
        if self.set_hover(key):
            self.setToolTip("" if hit is None else hit.title)
            self.setCursor(Qt.CursorShape.ArrowCursor if hit is None else Qt.CursorShape.PointingHandCursor)
        event.accept()

    def leaveEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        self.set_hover(None)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)  # type: ignore[arg-type]

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        hit = self.hit_at(event.position())
        self._pressed = None if hit is None or event.button() != Qt.MouseButton.LeftButton else hit.action_id
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        hit = self.hit_at(event.position())
        pressed, self._pressed = self._pressed, None
        if hit is not None and hit.action_id == pressed:
            self.action_requested.emit(hit.action_id)
        event.accept()

    def click_view(self, name: str) -> None:
        """Programmatic click on a named view (used by tests and accessibility)."""

        self.action_requested.emit(f"view.named.{name}")

    # -- painting -----------------------------------------------------------------

    def paintEvent(self, _event: object) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        self._paint(painter)

    def _paint(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        if self._show_cube:
            hover_name = (
                self._hover[len("view.named.") :]
                if self._hover is not None and self._hover.startswith("view.named.") and self._hover != HOME_ACTION
                else None
            )
            for face in reversed(self._faces):
                self._paint_face(painter, face, hover_name)
            for action_id in self._BUTTONS:
                self._paint_button(painter, action_id)
        if self._show_triad:
            self._paint_triad(painter)

    def _paint_face(self, painter: QPainter, face: ProjectedFace, hover_name: str | None) -> None:
        painter.save()
        s = CUBE_SCALE
        cx, cy = self._centre.x() + s * face.centre[0], self._centre.y() - s * face.centre[1]
        # local pixel coordinates (x right, y DOWN, front-on size) -> screen
        painter.setTransform(QTransform(face.u[0], -face.u[1], -face.v[0], face.v[1], cx, cy), False)
        shade = 0.62 + 0.38 * face.facing
        bevel = QColor.fromRgbF(0.22 * shade, 0.27 * shade, 0.33 * shade)
        centre_fill = QColor.fromRgbF(0.40 * shade, 0.47 * shade, 0.55 * shade)
        accent = QColor(0, 160, 205)
        outline = QPen(QColor(168, 200, 222, 235), 1.1)
        outline.setCosmetic(True)
        grid = QPen(QColor(10, 15, 20, 120), 1.0)
        grid.setCosmetic(True)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bevel)
        painter.drawRect(QRectF(-s, -s, 2 * s, 2 * s))
        painter.setBrush(centre_fill)
        painter.drawRect(QRectF(-s * _BAND, -s * _BAND, 2 * s * _BAND, 2 * s * _BAND))
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                if hover_name is not None and cell_view_name(face, i, j) == hover_name:
                    painter.setBrush(accent)
                    painter.drawRect(self._cell_rect(i, j))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(grid)
        painter.drawRect(QRectF(-s * _BAND, -s * _BAND, 2 * s * _BAND, 2 * s * _BAND))
        painter.setPen(outline)
        painter.drawRect(QRectF(-s, -s, 2 * s, 2 * s))

        font = QFont(self.font())
        font.setBold(True)
        font.setPixelSize(max(int(s * 0.28), 6))
        painter.setFont(font)
        painter.setPen(QColor(244, 249, 252) if hover_name != face.name else QColor(255, 255, 255))
        painter.drawText(
            QRectF(-s * _BAND, -s * _BAND, 2 * s * _BAND, 2 * s * _BAND),
            int(Qt.AlignmentFlag.AlignCenter),
            face.name.upper(),
        )
        painter.restore()

    @staticmethod
    def _cell_rect(i: int, j: int) -> QRectF:
        """Local pixel rect of cell (i along u, j along v); local y is down."""

        s = CUBE_SCALE

        def span(index: int) -> tuple[float, float]:
            return {-1: (-s, -s * _BAND), 0: (-s * _BAND, s * _BAND), 1: (s * _BAND, s)}[index]

        x0, x1 = span(i)
        y0, y1 = span(-j)
        return QRectF(x0, y0, x1 - x0, y1 - y0)

    def _paint_button(self, painter: QPainter, action_id: str) -> None:
        rect = self._button_rect(action_id)
        hovered = self._hover == action_id
        painter.save()
        painter.setPen(QPen(QColor(168, 200, 222, 220), 1.0))
        painter.setBrush(QColor(0, 160, 205, 230) if hovered else QColor(30, 40, 50, 205))
        painter.drawEllipse(rect.adjusted(1, 1, -1, -1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        pen = QPen(QColor(240, 247, 251), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        c = rect.center()
        if action_id == HOME_ACTION:
            roof = QPolygonF([QPointF(c.x() - 6, c.y()), QPointF(c.x(), c.y() - 6), QPointF(c.x() + 6, c.y())])
            painter.drawPolyline(roof)
            painter.drawPolyline(
                QPolygonF([QPointF(c.x() - 4, c.y()), QPointF(c.x() - 4, c.y() + 5), QPointF(c.x() + 4, c.y() + 5), QPointF(c.x() + 4, c.y())])
            )
        else:
            clockwise = action_id == ROLL_RIGHT_ACTION
            arc = rect.adjusted(6, 6, -6, -6)
            painter.drawArc(arc, (35 if clockwise else 145) * 16, (-255 if clockwise else 255) * 16)
            tip_x = c.x() + (5.5 if clockwise else -5.5)
            direction = 1 if clockwise else -1
            painter.setBrush(QColor(240, 247, 251))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(
                QPolygonF([QPointF(tip_x + 2.5 * direction, c.y() - 3), QPointF(tip_x - 2.5 * direction, c.y() - 4), QPointF(tip_x, c.y() + 1)])
            )
        painter.restore()

    def _paint_triad(self, painter: QPainter) -> None:
        """Small X/Y/Z axes in the corner, drawn from the camera orientation."""

        forward, up = self._forward, self._up
        right = _cross(forward, up)
        origin = QPointF(16.0, CUBE_WIDGET_SIZE - 16.0)
        length = 24.0
        painter.save()
        font = QFont(self.font())
        font.setBold(True)
        font.setPixelSize(10)
        painter.setFont(font)
        axes = (
            ("X", (1.0, 0.0, 0.0), QColor(255, 84, 72)),
            ("Y", (0.0, 1.0, 0.0), QColor(88, 226, 104)),
            ("Z", (0.0, 0.0, 1.0), QColor(92, 150, 255)),
        )
        # Draw the axes pointing away from the viewer first so nearer ones overlap them.
        for label, vector, colour in sorted(axes, key=lambda item: -_dot(item[1], forward)):
            end = QPointF(origin.x() + length * _dot(vector, right), origin.y() - length * _dot(vector, up))
            pen = QPen(colour, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(origin, end)
            direction = QPointF(end.x() - origin.x(), end.y() - origin.y())
            norm = math.hypot(direction.x(), direction.y())
            offset = QPointF(0.0, 0.0) if norm < 1e-6 else QPointF(direction.x() / norm * 7.0, direction.y() / norm * 7.0)
            painter.drawText(QRectF(end.x() + offset.x() - 6, end.y() + offset.y() - 6, 12, 12), int(Qt.AlignmentFlag.AlignCenter), label)
        painter.restore()


def _dot(first: Iterable[float], second: Iterable[float]) -> float:
    return sum(a * b for a, b in zip(first, second))


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(values: Iterable[object]) -> Vec3 | None:
    try:
        result = tuple(float(value) for value in values)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if len(result) != 3 or not all(math.isfinite(value) for value in result):
        return None
    length = math.sqrt(sum(value * value for value in result))
    if length <= 1e-12:
        return None
    return (result[0] / length, result[1] / length, result[2] / length)


__all__ = (
    "CUBE_SCALE",
    "CUBE_WIDGET_SIZE",
    "CubeHit",
    "HOME_ACTION",
    "ProjectedFace",
    "ROLL_LEFT_ACTION",
    "ROLL_RIGHT_ACTION",
    "ViewCubeWidget",
    "cell_view_name",
    "locate",
    "normalized_camera_orientation",
    "project_faces",
    "view_name",
    "view_title",
)
