"""World-space presentation for active Move and Rotate operations."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

import numpy as np

from viewer.scene_types import Bounds3, SceneSnapshot


AXIS_COLORS: Mapping[str, tuple[float, float, float]] = {
    "X": (0.95, 0.18, 0.18),
    "Y": (0.20, 0.85, 0.25),
    "Z": (0.22, 0.48, 1.00),
}
RING_SEGMENTS = 128
MIN_REFERENCE_EXTENT = 1.0
MAX_REFERENCE_EXTENT = 4_000.0
MIN_MOVE_SIZE = 0.25
MAX_MOVE_SIZE = 750.0
MIN_RING_RADIUS = 0.25
MAX_RING_RADIUS = 600.0


@dataclass(frozen=True, slots=True)
class TransformOverlayDiagnosticState:
    active_mode: str | None
    active_axis: str | None
    active_constraint: str | None
    requested_visibility: bool
    move_axis_visible: bool
    rotation_ring_visible: bool
    world_origin: tuple[float, float, float] | None
    reference_extent: float | None
    actor_creation_count: int
    move_actor_creation_count: int
    ring_actor_creation_count: int
    geometry_update_count: int
    last_geometry_signature: tuple[object, ...] | None
    move_actor_bounds: tuple[float, ...] | None
    ring_actor_bounds: tuple[float, ...] | None
    move_actor_in_main_renderer: bool
    ring_actor_in_main_renderer: bool
    move_actor_pickable: bool
    ring_actor_pickable: bool
    move_actor_draggable: bool
    ring_actor_draggable: bool
    move_actor_contributes_to_bounds: bool
    ring_actor_contributes_to_bounds: bool
    hidden_reason: str | None
    last_error: str | None


class TransformOverlayController:
    """Own and reuse the two props that present authoritative transform state."""

    def __init__(self, renderer: object | None) -> None:
        self.renderer = renderer
        self.move_actor: object | None = None
        self.ring_actor: object | None = None
        self._closed = False
        self._move_actor_creation_count = 0
        self._ring_actor_creation_count = 0
        self._geometry_update_count = 0
        self._move_geometry_signature: tuple[object, ...] | None = None
        self._ring_geometry_signature: tuple[object, ...] | None = None
        self._last_geometry_signature: tuple[object, ...] | None = None
        self._active_mode: str | None = None
        self._active_axis: str | None = None
        self._active_constraint: str | None = None
        self._requested_visibility = False
        self._world_origin: tuple[float, float, float] | None = None
        self._reference_extent: float | None = None
        self._hidden_reason: str | None = "inactive"
        self._last_error: str | None = None

    @property
    def actor_creation_count(self) -> int:
        return self._move_actor_creation_count + self._ring_actor_creation_count

    @property
    def geometry_update_count(self) -> int:
        return self._geometry_update_count

    def update(self, snapshot: SceneSnapshot) -> bool:
        """Present the snapshot's transform state without touching camera or scene."""

        if self._closed or self.renderer is None:
            return False

        mode = _mode(snapshot.active_transform_mode)
        axis = _axis(snapshot.active_transform_axis)
        constraint = _axis(snapshot.active_transform_constraint)
        show_axes = bool(snapshot.display.get("show_axes", True))
        origin = finite_world_origin(snapshot.object_origin)
        reference_bounds = snapshot.bounds_for_ids(snapshot.selection.selected_ids)
        if reference_bounds is None:
            reference_bounds = snapshot.visible_bounds()
        reference_extent = overlay_reference_extent(reference_bounds)

        self._active_mode = mode
        self._active_axis = axis
        self._active_constraint = constraint
        self._requested_visibility = bool(show_axes and mode in {"move", "rotate"})
        self._world_origin = origin
        self._reference_extent = reference_extent
        self._last_error = None

        self._hide_actors()
        if mode is None:
            self._hidden_reason = "inactive"
            self._last_geometry_signature = ("inactive", show_axes)
            return True
        if mode not in {"move", "rotate"}:
            self._hidden_reason = "unsupported_transform_target"
            self._last_geometry_signature = ("unsupported", mode, show_axes)
            return True
        if not show_axes:
            self._hidden_reason = "setting_disabled"
            self._last_geometry_signature = ("setting_disabled", mode)
            return True
        if origin is None:
            self._hidden_reason = "invalid_origin"
            self._last_geometry_signature = ("invalid_origin", mode, constraint)
            return True
        if reference_extent is None:
            self._hidden_reason = "invalid_reference_extent"
            self._last_geometry_signature = ("invalid_extent", mode, constraint, origin)
            return True

        self._hidden_reason = None
        try:
            self._create_actors()
            if self.move_actor is None or self.ring_actor is None:
                raise RuntimeError("VTK transform overlay actors are unavailable.")
            # Both retained props follow the authoritative origin, including
            # the currently hidden one.  No inactive mapper is parked at an
            # invented world-zero fallback.
            self.move_actor.SetPosition(*origin)
            self.ring_actor.SetPosition(*origin)
            if mode == "move":
                size = float(np.clip(reference_extent * 0.28, MIN_MOVE_SIZE, MAX_MOVE_SIZE))
                move_signature = (round(size, 9), constraint)
                if move_signature != self._move_geometry_signature:
                    _style_move_axes(self.move_actor, constraint, size)
                    self._move_geometry_signature = move_signature
                    self._geometry_update_count += 1
                self.move_actor.SetVisibility(True)
                geometry_signature: tuple[object, ...] = (
                    "move",
                    constraint,
                    origin,
                    round(reference_extent, 9),
                    show_axes,
                )
            else:
                radius = float(
                    np.clip(reference_extent * 0.22, MIN_RING_RADIUS, MAX_RING_RADIUS)
                )
                angle = _finite_angle(snapshot.active_transform_angle_delta)
                indicator_axis = axis or constraint or "Z"
                ring_signature = (
                    round(radius, 9),
                    constraint,
                    indicator_axis,
                    round(angle, 9),
                )
                if ring_signature != self._ring_geometry_signature:
                    _set_rotation_ring_geometry(
                        self.ring_actor,
                        radius=radius,
                        constraint=constraint,
                        indicator_axis=indicator_axis,
                        angle_degrees=angle,
                    )
                    self._ring_geometry_signature = ring_signature
                    self._geometry_update_count += 1
                self.ring_actor.SetVisibility(True)
                geometry_signature = (
                    "rotate",
                    axis,
                    constraint,
                    origin,
                    round(reference_extent, 9),
                    round(angle, 9),
                    show_axes,
                )
            self._last_geometry_signature = geometry_signature
            return True
        except Exception as exc:
            self._hide_actors()
            self._hidden_reason = "geometry_error"
            self._last_error = f"{type(exc).__name__}: {exc}"
            return False

    def _hide_actors(self) -> None:
        for actor in (self.move_actor, self.ring_actor):
            if actor is not None:
                actor.SetVisibility(False)

    def diagnostics(self) -> TransformOverlayDiagnosticState:
        move_visible = _bool_call(self.move_actor, "GetVisibility")
        ring_visible = _bool_call(self.ring_actor, "GetVisibility")
        move_member = _renderer_has_prop(self.renderer, self.move_actor)
        ring_member = _renderer_has_prop(self.renderer, self.ring_actor)
        return TransformOverlayDiagnosticState(
            active_mode=self._active_mode,
            active_axis=self._active_axis,
            active_constraint=self._active_constraint,
            requested_visibility=self._requested_visibility,
            move_axis_visible=move_visible,
            rotation_ring_visible=ring_visible,
            world_origin=self._world_origin,
            reference_extent=self._reference_extent,
            actor_creation_count=self.actor_creation_count,
            move_actor_creation_count=self._move_actor_creation_count,
            ring_actor_creation_count=self._ring_actor_creation_count,
            geometry_update_count=self._geometry_update_count,
            last_geometry_signature=self._last_geometry_signature,
            move_actor_bounds=_finite_tuple(_call(self.move_actor, "GetBounds"), 6),
            ring_actor_bounds=_finite_tuple(_call(self.ring_actor, "GetBounds"), 6),
            move_actor_in_main_renderer=move_member,
            ring_actor_in_main_renderer=ring_member,
            move_actor_pickable=_bool_call(self.move_actor, "GetPickable"),
            ring_actor_pickable=_bool_call(self.ring_actor, "GetPickable"),
            move_actor_draggable=_bool_call(self.move_actor, "GetDragable"),
            ring_actor_draggable=_bool_call(self.ring_actor, "GetDragable"),
            move_actor_contributes_to_bounds=bool(
                move_member and move_visible and _bool_call(self.move_actor, "GetUseBounds")
            ),
            ring_actor_contributes_to_bounds=bool(
                ring_member and ring_visible and _bool_call(self.ring_actor, "GetUseBounds")
            ),
            hidden_reason=self._hidden_reason,
            last_error=self._last_error,
        )

    def close(self) -> None:
        if self._closed:
            return
        for actor in (self.move_actor, self.ring_actor):
            if actor is None:
                continue
            actor.SetVisibility(False)
            if self.renderer is not None and _renderer_has_prop(self.renderer, actor):
                self.renderer.RemoveViewProp(actor)
        self.move_actor = None
        self.ring_actor = None
        self.renderer = None
        self._closed = True

    def _create_actors(self) -> None:
        if self._closed or self.renderer is None:
            return
        from vtkmodules.vtkRenderingAnnotation import vtkAxesActor
        from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper

        if self.move_actor is None:
            actor = vtkAxesActor()
            actor.AxisLabelsOff()
            actor.PickableOff()
            actor.DragableOff()
            actor.UseBoundsOff()
            actor.SetVisibility(False)
            actor.SetShaftTypeToCylinder()
            actor.SetTipTypeToCone()
            actor.SetNormalizedShaftLength(0.78, 0.78, 0.78)
            actor.SetNormalizedTipLength(0.22, 0.22, 0.22)
            actor.SetCylinderRadius(0.025)
            actor.SetConeRadius(0.10)
            actor.SetCylinderResolution(20)
            actor.SetConeResolution(24)
            self.renderer.AddActor(actor)
            self.move_actor = actor
            self._move_actor_creation_count += 1
        if self.ring_actor is None:
            mapper = vtkPolyDataMapper()
            mapper.SetScalarModeToUseCellData()
            mapper.SetColorModeToDirectScalars()
            mapper.ScalarVisibilityOn()
            actor = vtkActor()
            actor.SetMapper(mapper)
            actor.GetProperty().SetLineWidth(2.5)
            actor.GetProperty().LightingOff()
            actor.PickableOff()
            actor.DragableOff()
            actor.UseBoundsOff()
            actor.SetVisibility(False)
            self.renderer.AddActor(actor)
            self.ring_actor = actor
            self._ring_actor_creation_count += 1


def transformed_object_origin(
    local_origin: object,
    transform_matrix: object | None,
    *,
    location: object | None = None,
) -> tuple[float, float, float] | None:
    """Resolve an explicit local object origin to finite world coordinates."""

    origin = finite_world_origin(local_origin)
    if origin is None:
        return None
    if transform_matrix is None:
        return finite_world_origin(location)
    try:
        matrix = np.asarray(transform_matrix, dtype=float).reshape((4, 4))
    except (TypeError, ValueError):
        return None
    if not np.all(np.isfinite(matrix)):
        return None
    homogeneous = matrix @ np.asarray((*origin, 1.0), dtype=float)
    weight = float(homogeneous[3])
    if not np.all(np.isfinite(homogeneous)) or abs(weight) <= 1e-12:
        return None
    return finite_world_origin(homogeneous[:3] / weight)


def finite_world_origin(value: object) -> tuple[float, float, float] | None:
    if value is None:
        return None
    try:
        values = np.asarray(value, dtype=float).reshape(3)
    except (TypeError, ValueError):
        return None
    if not np.all(np.isfinite(values)):
        return None
    return (float(values[0]), float(values[1]), float(values[2]))


def overlay_reference_extent(bounds: Bounds3 | None) -> float | None:
    if bounds is None:
        return None
    try:
        values = np.asarray(bounds, dtype=float).reshape((2, 3))
    except (TypeError, ValueError):
        return None
    if not np.all(np.isfinite(values)):
        return None
    extent = float(np.max(np.abs(values[1] - values[0])))
    if not math.isfinite(extent) or extent <= 1e-12:
        return None
    return float(np.clip(extent, MIN_REFERENCE_EXTENT, MAX_REFERENCE_EXTENT))


def _style_move_axes(actor: object, constraint: str | None, size: float) -> None:
    lengths: list[float] = []
    for axis in ("X", "Y", "Z"):
        emphasized = constraint is None or constraint == axis
        opacity = 1.0 if emphasized else 0.22
        lengths.append(float(size) * (1.12 if constraint == axis else 1.0))
        for suffix in ("Shaft", "Tip"):
            material = getattr(actor, f"Get{axis}Axis{suffix}Property")()
            material.SetColor(*AXIS_COLORS[axis])
            material.SetOpacity(opacity)
            material.SetAmbient(0.55)
            material.SetDiffuse(0.65)
    actor.SetTotalLength(*lengths)


def _set_rotation_ring_geometry(
    actor: object,
    *,
    radius: float,
    constraint: str | None,
    indicator_axis: str,
    angle_degrees: float,
) -> None:
    from vtkmodules.vtkCommonCore import vtkPoints, vtkUnsignedCharArray
    from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData

    points = vtkPoints()
    lines = vtkCellArray()
    colors = vtkUnsignedCharArray()
    colors.SetName("TransformOverlayRGBA")
    colors.SetNumberOfComponents(4)

    for axis in ("X", "Y", "Z"):
        point_ids: list[int] = []
        for index in range(RING_SEGMENTS):
            angle = (2.0 * math.pi * index) / RING_SEGMENTS
            point_ids.append(points.InsertNextPoint(*_ring_point(axis, radius, angle)))
        lines.InsertNextCell(RING_SEGMENTS + 1)
        for point_id in point_ids:
            lines.InsertCellPoint(point_id)
        lines.InsertCellPoint(point_ids[0])
        colors.InsertNextTypedTuple(_ring_color(axis, constraint, indicator=False))

    indicator = _axis(indicator_axis) or "Z"
    origin_id = points.InsertNextPoint(0.0, 0.0, 0.0)
    end_id = points.InsertNextPoint(
        *_ring_point(indicator, radius, math.radians(angle_degrees))
    )
    lines.InsertNextCell(2)
    lines.InsertCellPoint(origin_id)
    lines.InsertCellPoint(end_id)
    colors.InsertNextTypedTuple(_ring_color(indicator, constraint, indicator=True))

    data = vtkPolyData()
    data.SetPoints(points)
    data.SetLines(lines)
    data.GetCellData().SetScalars(colors)
    actor.GetMapper().SetInputData(data)


def _ring_point(axis: str, radius: float, angle: float) -> tuple[float, float, float]:
    cosine = math.cos(angle) * radius
    sine = math.sin(angle) * radius
    if axis == "X":
        return (0.0, cosine, sine)
    if axis == "Y":
        return (cosine, 0.0, sine)
    return (cosine, sine, 0.0)


def _ring_color(
    axis: str,
    constraint: str | None,
    *,
    indicator: bool,
) -> tuple[int, int, int, int]:
    values = AXIS_COLORS[axis]
    alpha = 255 if constraint is None or constraint == axis else 58
    if indicator:
        alpha = 255 if constraint is None or constraint == axis else 90
    return (
        int(round(values[0] * 255.0)),
        int(round(values[1] * 255.0)),
        int(round(values[2] * 255.0)),
        alpha,
    )


def _mode(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized or None


def _axis(value: object) -> str | None:
    normalized = str(value or "").strip().upper()
    return normalized if normalized in AXIS_COLORS else None


def _finite_angle(value: object) -> float:
    try:
        angle = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return angle if math.isfinite(angle) else 0.0


def _renderer_has_prop(renderer: object | None, prop: object | None) -> bool:
    if renderer is None or prop is None:
        return False
    try:
        return bool(renderer.HasViewProp(prop))
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return False


def _call(owner: object | None, method: str, default: object = None) -> object:
    if owner is None:
        return default
    try:
        return getattr(owner, method)()
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return default


def _bool_call(owner: object | None, method: str) -> bool:
    return bool(_call(owner, method, False))


def _finite_tuple(value: object, length: int) -> tuple[float, ...] | None:
    try:
        values = tuple(float(item) for item in value)  # type: ignore[union-attr]
    except (TypeError, ValueError):
        return None
    return (
        values
        if len(values) == length and all(math.isfinite(item) for item in values)
        else None
    )


__all__ = (
    "AXIS_COLORS",
    "RING_SEGMENTS",
    "TransformOverlayController",
    "TransformOverlayDiagnosticState",
    "finite_world_origin",
    "overlay_reference_extent",
    "transformed_object_origin",
)
