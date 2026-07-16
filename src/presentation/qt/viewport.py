"""Qt host for openRetop's snapshot-driven VTK viewport."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Mapping

import numpy as np
from PySide6.QtCore import Signal
from PySide6.QtGui import QCloseEvent

from workbench_ui import VTKViewportWidget

from application.transform_controller import CameraVectors
from settings.settings_data import DEFAULT_BACKGROUND_COLOR
from viewer.actor_factories import VTKActorAdapter
from viewer.camera_controller import CameraController
from viewer.picking_service import MeshPickResult, PickingService, SceneObjectPickResult
from viewer.scene_synchronizer import ActorUpdateDiagnostics, SceneSynchronizer
from viewer.scene_types import Bounds3, CameraRequest, CameraRequestKind, SceneSnapshot


_LOG = logging.getLogger(__name__)
_POINTER_EVENTS = (
    ("LeftButtonPressEvent", "left_press"),
    ("LeftButtonReleaseEvent", "left_release"),
    ("MouseMoveEvent", "motion"),
    ("RightButtonPressEvent", "right_press"),
    ("RightButtonReleaseEvent", "right_release"),
)


@dataclass(frozen=True, slots=True)
class ViewportDiagnosticState:
    ready: bool
    render_window_class: str | None
    renderer_class: str | None
    interactor_initialized: bool | None
    actor_count: int
    view_prop_count: int
    snapshot_counts: Mapping[str, int]
    visible_bounds: Bounds3 | None
    renderer_size: tuple[int, int] | None
    render_window_size: tuple[int, int] | None
    camera_position: tuple[float, float, float] | None
    camera_focal_point: tuple[float, float, float] | None
    camera_clipping_range: tuple[float, float] | None
    camera_view_angle: float | None
    background: tuple[float, float, float] | None
    synchronization_count: int
    observer_count: int
    last_synchronization: ActorUpdateDiagnostics | None
    last_rendering_error: str | None


class QtSceneViewport(VTKViewportWidget):
    """Apply openRetop scene snapshots after the generic host becomes ready."""

    pointer_event = Signal(str, int, int, object)
    scene_synchronized = Signal(object)

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self.synchronizer: SceneSynchronizer | None = None
        self.camera_controller: CameraController | None = None
        self.last_snapshot: SceneSnapshot | None = None
        self.last_diagnostics: ActorUpdateDiagnostics | None = None
        self.picking: PickingService | None = None
        self._pending_snapshot: SceneSnapshot | None = None
        self._pending_camera_request: CameraRequest | None = None
        self._observer_ids: list[int] = []
        self._observers_registered = False
        self._synchronization_count = 0
        self._last_scene_error: str | None = None
        self._grid_actor: object | None = None
        self._axes_actor: object | None = None
        self._grid_signature: tuple[float, float, float] | None = None
        self.ready.connect(self._on_viewport_ready)

    @property
    def pending_snapshot(self) -> SceneSnapshot | None:
        return self._pending_snapshot

    @property
    def synchronization_count(self) -> int:
        return self._synchronization_count

    @property
    def observer_count(self) -> int:
        return len(self._observer_ids)

    def render_snapshot(self, snapshot: SceneSnapshot) -> ActorUpdateDiagnostics | None:
        """Retain and eventually synchronize the newest submitted snapshot."""

        self._pending_snapshot = snapshot
        if snapshot.camera_request.kind is not CameraRequestKind.NONE:
            self._pending_camera_request = snapshot.camera_request
        if not self.is_ready:
            return None
        return self._flush_pending_snapshot()

    def set_background(self, value: object) -> tuple[float, float, float]:
        color = normalized_background_color(value)
        if self.renderer is not None:
            self.renderer.SetBackground(*color)
        return color

    def diagnostic_state(self) -> ViewportDiagnosticState:
        snapshot = self.last_snapshot or self._pending_snapshot
        camera = None if self.renderer is None else self.renderer.GetActiveCamera()
        toolkit = super().diagnostic_state()
        return ViewportDiagnosticState(
            ready=self.is_ready,
            render_window_class=_string_or_none(toolkit.get("render_window_class")),
            renderer_class=_string_or_none(toolkit.get("renderer_class")),
            interactor_initialized=_bool_or_none(toolkit.get("interactor_initialized")),
            actor_count=_collection_count(self.renderer, "GetActors"),
            view_prop_count=_collection_count(self.renderer, "GetViewProps"),
            snapshot_counts=_snapshot_counts(snapshot),
            visible_bounds=None if snapshot is None else snapshot.visible_bounds(),
            renderer_size=_size_or_none(toolkit.get("renderer_size")),
            render_window_size=_size_or_none(toolkit.get("render_window_size")),
            camera_position=_camera_tuple(camera, "GetPosition", 3),
            camera_focal_point=_camera_tuple(camera, "GetFocalPoint", 3),
            camera_clipping_range=_camera_tuple(camera, "GetClippingRange", 2),
            camera_view_angle=_camera_scalar(camera, "GetViewAngle"),
            background=_camera_tuple(self.renderer, "GetBackground", 3),
            synchronization_count=self._synchronization_count,
            observer_count=len(self._observer_ids),
            last_synchronization=self.last_diagnostics,
            last_rendering_error=self._last_scene_error or self.last_error,
        )

    def pick_mesh(self, x_position: int, y_position: int) -> MeshPickResult:
        if self.picking is None:
            return MeshPickResult(hit=False)
        return self.picking.pick_mesh(x_position, y_position)

    def pick_scene_object(
        self, x_position: int, y_position: int
    ) -> SceneObjectPickResult:
        if self.picking is None:
            return SceneObjectPickResult(hit=False)
        return self.picking.pick_scene_object(x_position, y_position)

    def camera_vectors(self) -> CameraVectors | None:
        if not self.is_ready or self.renderer is None:
            return None
        camera = self.renderer.GetActiveCamera()
        forward = np.asarray(camera.GetFocalPoint(), dtype=float) - np.asarray(
            camera.GetPosition(), dtype=float
        )
        up = np.asarray(camera.GetViewUp(), dtype=float)
        forward = _unit(forward)
        if forward is None:
            return None
        right = _unit(np.cross(forward, up))
        if right is None:
            return None
        corrected_up = _unit(np.cross(right, forward))
        if corrected_up is None:
            return None
        return CameraVectors(right, corrected_up, forward)

    def model_bounds(self) -> Bounds3 | None:
        snapshot = self.last_snapshot or self._pending_snapshot
        return None if snapshot is None else snapshot.visible_bounds()

    def project_points(self, world_points: object) -> np.ndarray:
        if not self.is_ready or self.renderer is None:
            return np.zeros((0, 2), dtype=float)
        try:
            points = np.asarray(world_points, dtype=float).reshape((-1, 3))
        except (TypeError, ValueError):
            return np.zeros((0, 2), dtype=float)
        projected: list[tuple[float, float]] = []
        for point in points:
            self.renderer.SetWorldPoint(float(point[0]), float(point[1]), float(point[2]), 1.0)
            self.renderer.WorldToDisplay()
            display = self.renderer.GetDisplayPoint()
            projected.append((float(display[0]), float(display[1])))
        return np.asarray(projected, dtype=float).reshape((-1, 2))

    def point_on_plane(
        self,
        x_position: int,
        y_position: int,
        *,
        plane_origin: object,
        plane_normal: object,
    ) -> np.ndarray | None:
        """Intersect a display ray with a toolkit-neutral work plane."""

        if not self.is_ready or self.renderer is None:
            return None
        near = self._display_to_world(x_position, y_position, 0.0)
        far = self._display_to_world(x_position, y_position, 1.0)
        if near is None or far is None:
            return None
        direction = far - near
        normal = _unit(plane_normal)
        if normal is None:
            return None
        origin = np.asarray(plane_origin, dtype=float).reshape(3)
        denominator = float(np.dot(normal, direction))
        if abs(denominator) <= 1e-12:
            return None
        distance = float(np.dot(normal, origin - near) / denominator)
        point = near + distance * direction
        return point if np.all(np.isfinite(point)) else None

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        if self.interactor is not None:
            for observer_id in self._observer_ids:
                try:
                    self.interactor.RemoveObserver(observer_id)
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    _LOG.warning("Could not remove VTK observer %s", observer_id)
        self._observer_ids.clear()
        self._observers_registered = False
        super().closeEvent(event)

    def _on_viewport_ready(self) -> None:
        try:
            self._ensure_scene_services()
            self._flush_pending_snapshot()
        except Exception as exc:  # presentation boundary: log and expose full context
            self._record_scene_failure("Viewport readiness failed", exc)

    def _ensure_scene_services(self) -> None:
        if self.renderer is None or self.interactor is None:
            raise RuntimeError("VTK renderer and interactor are unavailable.")
        if self.picking is None:
            self.picking = PickingService(self.renderer)
        if self.synchronizer is None:
            self.synchronizer = SceneSynchronizer(
                VTKActorAdapter(self.renderer, self.picking)
            )
        if self.camera_controller is None:
            self.camera_controller = CameraController(self.renderer)
        if self._observers_registered:
            return

        added: list[int] = []
        try:
            for vtk_name, event_name in _POINTER_EVENTS:
                observer_id = self.interactor.AddObserver(
                    vtk_name,
                    lambda caller, _event, name=event_name: self._emit_pointer(name, caller),
                )
                added.append(int(observer_id))
        except (AttributeError, RuntimeError, TypeError, ValueError):
            for observer_id in added:
                try:
                    self.interactor.RemoveObserver(observer_id)
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    pass
            raise
        self._observer_ids.extend(added)
        self._observers_registered = True

    def _flush_pending_snapshot(self) -> ActorUpdateDiagnostics | None:
        snapshot = self._pending_snapshot
        if snapshot is None:
            return self.last_diagnostics
        try:
            self._ensure_scene_services()
            assert self.synchronizer is not None
            assert self.camera_controller is not None
            display_colors = snapshot.display.get("display_colors", {})
            background = (
                display_colors.get("background_color", DEFAULT_BACKGROUND_COLOR)
                if isinstance(display_colors, Mapping)
                else DEFAULT_BACKGROUND_COLOR
            )
            self.set_background(background)
            self._update_display_overlays(snapshot)
            diagnostics = self.synchronizer.synchronize(snapshot)
            self.last_snapshot = snapshot
            self.last_diagnostics = diagnostics
            self._synchronization_count += 1

            if self._pending_camera_request is not None and self._renderer_has_size():
                request = self._pending_camera_request
                if (
                    request.kind in {CameraRequestKind.FRAME_ALL, CameraRequestKind.RESET}
                    and snapshot.visible_bounds() is None
                    and bool(snapshot.display.get("show_grid", True))
                ):
                    extent = _overlay_extent(None)
                    request = CameraRequest.frame_bounds(
                        ((-extent, -extent, 0.0), (extent, extent, 0.0))
                    )
                self.camera_controller.apply(request, snapshot)
                self._pending_camera_request = None
            rendered = self.render()
            if not rendered and self.last_error:
                raise RuntimeError(self.last_error)
        except Exception as exc:  # scene boundary: preserve pending state and expose it
            self._record_scene_failure("Scene synchronization failed", exc)
            return None

        self._pending_snapshot = None
        self._last_scene_error = None
        self.scene_synchronized.emit(diagnostics)
        return diagnostics

    def _renderer_has_size(self) -> bool:
        if self.renderer is None:
            return False
        try:
            width, height = self.renderer.GetSize()
            return int(width) > 0 and int(height) > 0
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False

    def _update_display_overlays(self, snapshot: SceneSnapshot) -> None:
        if self.renderer is None:
            return
        self._ensure_display_overlays()
        assert self._grid_actor is not None
        assert self._axes_actor is not None
        self._grid_actor.SetVisibility(bool(snapshot.display.get("show_grid", True)))
        self._axes_actor.SetVisibility(bool(snapshot.display.get("show_axes", True)))
        bounds = snapshot.visible_bounds()
        extent = _overlay_extent(bounds)
        signature = (extent, 0.0, 0.0)
        if signature != self._grid_signature:
            _set_grid_geometry(self._grid_actor, extent)
            self._axes_actor.SetTotalLength(extent * 0.25, extent * 0.25, extent * 0.25)
            self._grid_signature = signature

    def _ensure_display_overlays(self) -> None:
        if self._grid_actor is not None and self._axes_actor is not None:
            return
        from vtkmodules.vtkRenderingAnnotation import vtkAxesActor
        from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper

        grid_actor = vtkActor()
        grid_actor.SetMapper(vtkPolyDataMapper())
        grid_actor.GetProperty().SetColor(0.30, 0.34, 0.39)
        grid_actor.GetProperty().SetOpacity(0.42)
        grid_actor.GetProperty().SetLineWidth(1.0)
        grid_actor.PickableOff()

        axes_actor = vtkAxesActor()
        axes_actor.AxisLabelsOff()
        axes_actor.PickableOff()

        self.renderer.AddActor(grid_actor)
        self.renderer.AddActor(axes_actor)
        self._grid_actor = grid_actor
        self._axes_actor = axes_actor

    def _record_scene_failure(self, context: str, exc: Exception) -> None:
        message = f"{context}: {type(exc).__name__}: {exc}"
        self._last_scene_error = message
        _LOG.exception(context)
        self.render_failed.emit(message)

    def _emit_pointer(self, event_name: str, caller: object) -> None:
        try:
            x_position, y_position = caller.GetEventPosition()
        except (AttributeError, TypeError, ValueError):
            return
        pick: object | None = None
        if event_name in {"left_press", "left_release", "motion"}:
            pick = self.pick_mesh(int(x_position), int(y_position))
            if not pick.hit:
                pick = self.pick_scene_object(int(x_position), int(y_position))
        self.pointer_event.emit(event_name, int(x_position), int(y_position), pick)

    def _display_to_world(
        self, x_position: int, y_position: int, depth: float
    ) -> np.ndarray | None:
        assert self.renderer is not None
        self.renderer.SetDisplayPoint(float(x_position), float(y_position), float(depth))
        self.renderer.DisplayToWorld()
        value = np.asarray(self.renderer.GetWorldPoint(), dtype=float).reshape(4)
        if not np.all(np.isfinite(value)) or abs(float(value[3])) <= 1e-12:
            return None
        return value[:3] / value[3]


def normalized_background_color(
    value: object,
    fallback: str = DEFAULT_BACKGROUND_COLOR,
) -> tuple[float, float, float]:
    """Convert a display setting to finite normalized VTK RGB values."""

    parsed = _hex_color(value)
    if parsed is not None:
        return parsed
    parsed_fallback = _hex_color(fallback)
    return parsed_fallback if parsed_fallback is not None else (0.0, 0.0, 0.0)


def _hex_color(value: object) -> tuple[float, float, float] | None:
    if not isinstance(value, str) or len(value) != 7 or not value.startswith("#"):
        return None
    try:
        return tuple(int(value[index : index + 2], 16) / 255.0 for index in (1, 3, 5))
    except ValueError:
        return None


def _set_grid_geometry(actor: object, extent: float) -> None:
    from vtkmodules.vtkCommonCore import vtkPoints
    from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData

    points = vtkPoints()
    lines = vtkCellArray()
    subdivisions = 10
    step = (extent * 2.0) / subdivisions
    for index in range(subdivisions + 1):
        coordinate = -extent + index * step
        for first, second in (
            ((-extent, coordinate, 0.0), (extent, coordinate, 0.0)),
            ((coordinate, -extent, 0.0), (coordinate, extent, 0.0)),
        ):
            first_id = points.InsertNextPoint(*first)
            second_id = points.InsertNextPoint(*second)
            lines.InsertNextCell(2)
            lines.InsertCellPoint(first_id)
            lines.InsertCellPoint(second_id)
    data = vtkPolyData()
    data.SetPoints(points)
    data.SetLines(lines)
    actor.GetMapper().SetInputData(data)


def _overlay_extent(bounds: Bounds3 | None) -> float:
    if bounds is None:
        return 10.0
    values = np.asarray(bounds, dtype=float).reshape((2, 3))
    if not np.all(np.isfinite(values)):
        return 10.0
    return max(float(np.max(np.abs(values[:, :2]))), float(np.max(values[1] - values[0])), 1.0)


def _snapshot_counts(snapshot: SceneSnapshot | None) -> dict[str, int]:
    if snapshot is None:
        return {
            "meshes": 0,
            "curves": 0,
            "surfaces": 0,
            "regions": 0,
            "section_planes": 0,
            "section_results": 0,
        }
    return {
        "meshes": len(snapshot.meshes),
        "curves": len(snapshot.curves),
        "surfaces": len(snapshot.surfaces),
        "regions": len(snapshot.regions),
        "section_planes": len(snapshot.section_planes),
        "section_results": len(snapshot.section_results),
    }


def _collection_count(owner: object | None, getter_name: str) -> int:
    if owner is None:
        return 0
    try:
        return int(getattr(owner, getter_name)().GetNumberOfItems())
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return 0


def _camera_tuple(
    owner: object | None,
    getter_name: str,
    length: int,
) -> tuple | None:
    if owner is None:
        return None
    try:
        values = tuple(float(value) for value in getattr(owner, getter_name)())
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return None
    return values if len(values) == length and all(np.isfinite(values)) else None


def _camera_scalar(owner: object | None, getter_name: str) -> float | None:
    if owner is None:
        return None
    try:
        value = float(getattr(owner, getter_name)())
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def _string_or_none(value: object) -> str | None:
    return None if value is None else str(value)


def _bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _size_or_none(value: object) -> tuple[int, int] | None:
    try:
        width, height = value  # type: ignore[misc]
        return (int(width), int(height))
    except (TypeError, ValueError):
        return None


def _unit(value: object) -> np.ndarray | None:
    vector = np.asarray(value, dtype=float).reshape(3)
    length = float(np.linalg.norm(vector))
    if not np.isfinite(length) or length <= 1e-12:
        return None
    return vector / length


__all__ = (
    "QtSceneViewport",
    "ViewportDiagnosticState",
    "normalized_background_color",
)
