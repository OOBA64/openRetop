"""Clickable orientation gizmo for the viewport: a view cube with XYZ axis balls.

The gizmo mirrors the main camera.  Each visible cube face is labelled (FRONT, BACK,
LEFT, RIGHT, TOP, BOTTOM) and every face, edge and corner is a click target that snaps
the camera to that direction.  Faces are split 3x3 like a conventional CAD view cube:
the centre is the face view, the border strips are edge views, and the corners are
three-face (isometric style) views.  Around the cube, coloured balls mark the axes
(solid for +X/+Y/+Z with a letter, muted for the negative ends); clicking one looks
along that axis, as in Blender's navigation gizmo.  There are deliberately no extra
buttons: the isometric view and view roll are in the View menu and the command palette.

Geometry and hit-testing are pure functions of the camera orientation so they can be
unit-tested without Qt; :class:`ViewCubeWidget` only paints them.

World convention matches ``viewer.camera_controller.named_view_vectors``: +Z is up,
FRONT is the face at -Y, RIGHT is the face at +X.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import partial
from typing import Callable, Iterable

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
    QTransform,
)
from PySide6.QtWidgets import QWidget

Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]

CUBE_WIDGET_SIZE = 160
CUBE_MARGIN = 8
CUBE_SCALE = 32.0  # pixels per cube half-edge
_BAND = 0.5  # |local coordinate| beyond this on a face is an edge/corner strip
_MIN_FACING = 0.02  # faces nearly edge-on are not drawn or clickable
AXIS_DISTANCE = 2.05  # axis balls sit this many half-edges from the centre
_AXIS_HIDE_OFFSET = 1.0  # a ball nearly end-on to the viewer would cover the cube face
_BALL_RADIUS = (9.0, 6.5)  # positive, negative
_ACCENT = QColor(0, 170, 215)

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


def project_faces(forward: Vec3, up: Vec3, *, include_hidden: bool = False) -> tuple[ProjectedFace, ...]:
    """Visible faces, most camera-facing first (plus the far faces when asked)."""

    right = _cross(forward, up)

    def screen(vector: Vec3) -> Vec2:
        return (_dot(vector, right), _dot(vector, up))

    faces = []
    for name, normal, u_axis, v_axis in _FACES:
        facing = -_dot(normal, forward)
        if facing <= _MIN_FACING and not include_hidden:
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


# name of the view looking along the axis end, letter, positive?, colour
_AXES: tuple[tuple[str, str, bool, Vec3, tuple[int, int, int]], ...] = (
    ("right", "X", True, (1.0, 0.0, 0.0), (236, 72, 88)),
    ("left", "X", False, (-1.0, 0.0, 0.0), (236, 72, 88)),
    ("back", "Y", True, (0.0, 1.0, 0.0), (126, 200, 40)),
    ("front", "Y", False, (0.0, -1.0, 0.0), (126, 200, 40)),
    ("top", "Z", True, (0.0, 0.0, 1.0), (56, 142, 245)),
    ("bottom", "Z", False, (0.0, 0.0, -1.0), (56, 142, 245)),
)


@dataclass(frozen=True, slots=True)
class AxisBall:
    """One end of an axis in view space (x right, y up, cube half-edge = 1)."""

    name: str  # the named view it selects: "right", "front", ...
    label: str
    positive: bool
    colour: tuple[int, int, int]
    centre: Vec2
    depth: float  # larger = farther from the viewer


def project_axes(forward: Vec3, up: Vec3) -> tuple[AxisBall, ...]:
    """Axis balls that are not hidden end-on behind/in front of the cube centre."""

    right = _cross(forward, up)
    balls = []
    for name, label, positive, direction, colour in _AXES:
        position = tuple(AXIS_DISTANCE * c for c in direction)
        centre = (_dot(position, right), _dot(position, up))
        if math.hypot(*centre) < _AXIS_HIDE_OFFSET:
            continue
        balls.append(AxisBall(name, label, positive, colour, centre, _dot(position, forward)))
    return tuple(balls)


def axis_title(ball: AxisBall) -> str:
    return f"{view_title(ball.name)} ({'+' if ball.positive else '-'}{ball.label})"


@dataclass(frozen=True, slots=True)
class CubeHit:
    action_id: str
    title: str
    key: str | None = None  # distinguishes a ball from the face that selects the same view

    @property
    def hover_key(self) -> str:
        return self.action_id if self.key is None else self.key


class ViewCubeWidget(QWidget):
    """Paints the cube and XYZ axis balls, and hit-tests them.

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
        self._axes = project_axes(self._forward, self._up)
        self._show_cube = True
        self._show_axes = True
        self._hover: str | None = None  # a hit's hover_key
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

    def set_parts(self, *, cube: bool, axes: bool) -> None:
        if (cube, axes) == (self._show_cube, self._show_axes):
            return
        self._show_cube, self._show_axes = bool(cube), bool(axes)
        self._hover = None
        self.update()

    def set_hover(self, key: str | None) -> bool:
        """Highlight a region (a hit's hover_key); returns True if it changed."""

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
        self._axes = project_axes(forward, up)
        self.update()

    # -- geometry -----------------------------------------------------------------

    @property
    def _centre(self) -> QPointF:
        return QPointF(CUBE_WIDGET_SIZE / 2.0, CUBE_WIDGET_SIZE / 2.0)

    def _to_view(self, point: QPointF) -> Vec2:
        return ((point.x() - self._centre.x()) / CUBE_SCALE, (self._centre.y() - point.y()) / CUBE_SCALE)

    @property
    def axes(self) -> tuple[AxisBall, ...]:
        return self._axes

    def _ball_pixel(self, ball: AxisBall) -> QPointF:
        return QPointF(self._centre.x() + CUBE_SCALE * ball.centre[0], self._centre.y() - CUBE_SCALE * ball.centre[1])

    def hit_at(self, point: QPointF) -> CubeHit | None:
        """What a click at ``point`` (widget pixels) would do, or None."""

        view_point = self._to_view(point)
        if self._show_axes:
            for ball in sorted(self._axes, key=lambda item: item.depth):  # nearest first
                centre = self._ball_pixel(ball)
                radius = _BALL_RADIUS[0 if ball.positive else 1] + 2.0
                if math.hypot(point.x() - centre.x(), point.y() - centre.y()) > radius:
                    continue
                if self._show_cube and ball.depth > 0.0 and locate(self._faces, *view_point) is not None:
                    continue  # behind the cube
                return CubeHit(f"view.named.{ball.name}", axis_title(ball), f"view.named.{ball.name}#axis")
        if not self._show_cube:
            return None
        name = locate(self._faces, *view_point)
        if name is None:
            return None
        return CubeHit(f"view.named.{name}", view_title(name))

    # -- input --------------------------------------------------------------------

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        hit = self.hit_at(event.position())
        key = None if hit is None else hit.hover_key
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
        hover = self._hover
        if hover is not None:
            # A faint disc behind the gizmo while the pointer is over it.
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 24))
            painter.drawEllipse(self._centre, 80.0, 80.0)
        hover_axis = hover[len("view.named.") : -len("#axis")] if hover is not None and hover.endswith("#axis") else None
        hover_name = (
            hover[len("view.named.") :]
            if hover is not None and hover.startswith("view.named.") and not hover.endswith("#axis")
            else None
        )
        # Painter's algorithm: far to near, so balls pass behind and in front of the cube.
        items: list[tuple[float, Callable[[], None]]] = []
        if self._show_cube:
            for face in project_faces(self._forward, self._up, include_hidden=True):
                if face.facing <= _MIN_FACING:
                    self._paint_hidden_face(painter, face)
                else:
                    items.append((-face.facing, partial(self._paint_face, painter, face, hover_name)))
        if self._show_axes:
            for ball in self._axes:
                # The axis line runs from the centre, so the cube covers its inner part.
                items.append((max(ball.depth, 0.0), partial(self._paint_axis_line, painter, ball)))
                items.append((ball.depth, partial(self._paint_ball, painter, ball, ball.name == hover_axis)))
        for _depth, draw in sorted(items, key=lambda item: -item[0]):
            draw()

    def _face_path(self) -> QPainterPath:
        s = CUBE_SCALE
        path = QPainterPath()
        path.addRoundedRect(QRectF(-s, -s, 2 * s, 2 * s), 0.2 * s, 0.2 * s)
        return path

    def _face_transform(self, face: ProjectedFace) -> QTransform:
        """Local pixel coordinates (x right, y DOWN, front-on size) -> widget pixels."""

        cx = self._centre.x() + CUBE_SCALE * face.centre[0]
        cy = self._centre.y() - CUBE_SCALE * face.centre[1]
        return QTransform(face.u[0], -face.u[1], -face.v[0], face.v[1], cx, cy)

    def _paint_hidden_face(self, painter: QPainter, face: ProjectedFace) -> None:
        painter.save()
        painter.setTransform(self._face_transform(face), False)
        pen = QPen(QColor(190, 210, 228, 58), 1.0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._face_path())
        painter.restore()

    def _paint_face(self, painter: QPainter, face: ProjectedFace, hover_name: str | None) -> None:
        painter.save()
        s = CUBE_SCALE
        painter.setTransform(self._face_transform(face), False)
        shade = 0.70 + 0.30 * face.facing
        gradient = QLinearGradient(0.0, -s, 0.0, s)
        gradient.setColorAt(0.0, QColor.fromRgbF(0.46 * shade, 0.52 * shade, 0.61 * shade))
        gradient.setColorAt(1.0, QColor.fromRgbF(0.28 * shade, 0.33 * shade, 0.41 * shade))
        path = self._face_path()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawPath(path)
        if hover_name is not None:
            painter.save()
            painter.setClipPath(path)
            painter.setBrush(_ACCENT)
            for i in (-1, 0, 1):
                for j in (-1, 0, 1):
                    if cell_view_name(face, i, j) == hover_name:
                        painter.drawRect(self._cell_rect(i, j))
            painter.restore()
        rim = QPen(QColor(222, 235, 246, 165), 1.0)
        rim.setCosmetic(True)
        painter.setPen(rim)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # Drawn as a vector path: skewed text stays smooth and free of colour fringes.
        font = QFont(self.font())
        font.setBold(True)
        font.setPixelSize(max(int(s * 0.29), 6))
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.NoSubpixelAntialias)
        label = face.name.upper()
        text = QPainterPath()
        text.addText(0.0, 0.0, font, label)
        bounds = text.boundingRect()
        text.translate(-bounds.center().x(), -bounds.center().y())
        painter.setPen(Qt.PenStyle.NoPen)
        # Labels on faces turned steeply away would only be a smear: fade them out.
        legibility = min(max((face.facing - 0.2) / 0.35, 0.0), 1.0)
        painter.setBrush(QColor(248, 251, 253, round(240 * legibility)))
        painter.drawPath(text)
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

    def _paint_axis_line(self, painter: QPainter, ball: AxisBall) -> None:
        painter.save()
        painter.setPen(QPen(QColor(*ball.colour, 225), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(self._centre, self._ball_pixel(ball))
        painter.restore()

    def _paint_ball(self, painter: QPainter, ball: AxisBall, hovered: bool) -> None:
        painter.save()
        radius = _BALL_RADIUS[0 if ball.positive else 1]
        centre = self._ball_pixel(ball)
        colour = QColor(*ball.colour)
        fill = colour if ball.positive else colour.darker(260)
        if hovered:
            fill = colour.lighter(125)
        gradient = QRadialGradient(QPointF(centre.x() - radius * 0.35, centre.y() - radius * 0.4), radius * 1.5)
        gradient.setColorAt(0.0, fill.lighter(140))
        gradient.setColorAt(0.55, fill)
        gradient.setColorAt(1.0, fill.darker(135))
        painter.setBrush(gradient)
        painter.setPen(QPen(colour if not ball.positive else colour.darker(150), 1.4))
        painter.drawEllipse(centre, radius, radius)
        if ball.positive:
            font = QFont(self.font())
            font.setBold(True)
            font.setPixelSize(11)
            font.setStyleStrategy(QFont.StyleStrategy.NoSubpixelAntialias)
            painter.setFont(font)
            painter.setPen(QColor(18, 22, 28))
            painter.drawText(QRectF(centre.x() - radius, centre.y() - radius, 2 * radius, 2 * radius), int(Qt.AlignmentFlag.AlignCenter), ball.label)
        if hovered:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(255, 255, 255, 235), 1.8))
            painter.drawEllipse(centre, radius + 2.2, radius + 2.2)
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
    "AXIS_DISTANCE",
    "AxisBall",
    "CubeHit",
    "ProjectedFace",
    "ViewCubeWidget",
    "axis_title",
    "cell_view_name",
    "locate",
    "normalized_camera_orientation",
    "project_axes",
    "project_faces",
    "view_name",
    "view_title",
)
