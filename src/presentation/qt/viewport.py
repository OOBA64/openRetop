"""Qt host for openRetop's snapshot-driven VTK viewport."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import math
from typing import Mapping

import numpy as np
from PySide6.QtCore import QEvent, QTimer, Qt, Signal
from PySide6.QtGui import QCloseEvent, QMouseEvent, QResizeEvent

from workbench_ui import VTKViewportWidget

from application.transform_controller import CameraVectors
from presentation.qt.orientation_gizmo import (
    GIZMO_CONTROL_GAP,
    OrientationGizmoController,
    OrientationGizmoDiagnosticState,
)
from presentation.qt.pointer_gestures import PointerGestureState
from presentation.qt.view_controls import ViewControlCluster
from settings.settings_data import DEFAULT_BACKGROUND_COLOR
from viewer.actor_factories import VTKActorAdapter
from viewer.camera_controller import CameraController
from viewer.picking_service import MeshPickResult, PickingService, SceneObjectPickResult
from viewer.scene_synchronizer import ActorUpdateDiagnostics, SceneSynchronizer
from viewer.scene_types import Bounds3, CameraRequest, CameraRequestKind, SceneSnapshot


_LOG = logging.getLogger(__name__)
@dataclass(frozen=True, slots=True)
class ViewportDiagnosticState:
    ready: bool
    render_window_class: str | None
    renderer_class: str | None
    interactor_style_class: str | None
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
    pointer_event_count: int
    pick_count: int
    left_capture_owner: str | None
    gesture_active: bool
    native_navigation_started: bool
    selection_eligible: bool
    gesture_distance: float
    gizmo_synchronization_count: int
    orientation_gizmo: OrientationGizmoDiagnosticState
    scene_actor_inventory: tuple[Mapping[str, object], ...]
    overlay_actor_inventory: tuple[Mapping[str, object], ...]
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
        self._synchronization_count = 0
        self._last_scene_error: str | None = None
        self._grid_actor: object | None = None
        self._transform_axes_actor: object | None = None
        self._rotation_ring_actor: object | None = None
        self._grid_signature: tuple[float, float, float] | None = None
        self._pointer_gesture = PointerGestureState()
        self._left_capture_owner: str | None = None
        self._last_pointer_release_was_click = True
        self._pointer_event_count = 0
        self._pick_count = 0
        self._qt_filter_installed = False
        self.orientation_gizmo = OrientationGizmoController(
            self.render_window,
            self.renderer,
            self.interactor,
            device_pixel_ratio=self.devicePixelRatioF,
        )
        self.view_controls = ViewControlCluster(self)
        if self.interactor is not None:
            self.interactor.installEventFilter(self)
            self._qt_filter_installed = True
        self.ready.connect(self._on_viewport_ready)

    @property
    def pending_snapshot(self) -> SceneSnapshot | None:
        return self._pending_snapshot

    @property
    def synchronization_count(self) -> int:
        return self._synchronization_count

    @property
    def observer_count(self) -> int:
        return self.orientation_gizmo.observer_count

    @property
    def _observer_ids(self) -> tuple[tuple[object, int], ...]:
        """Compatibility view of the gizmo controller's sole VTK observer."""

        return self.orientation_gizmo.observer_records

    @property
    def _axis_gizmo_renderer(self) -> object | None:
        return self.orientation_gizmo.renderer

    @property
    def _axis_gizmo_actor(self) -> object | None:
        return self.orientation_gizmo.actor

    @property
    def _axis_gizmo_visible(self) -> bool:
        return self.orientation_gizmo.enabled

    @property
    def _axis_gizmo_camera_signature(self) -> tuple[float, ...] | None:
        return self.orientation_gizmo.camera_signature

    @property
    def _axis_gizmo_synchronization_count(self) -> int:
        return self.orientation_gizmo.camera_update_count

    @property
    def last_pointer_release_was_click(self) -> bool:
        return self._last_pointer_release_was_click

    @property
    def left_capture_owner(self) -> str | None:
        return self._left_capture_owner

    def set_left_capture_owner(self, owner: str | None) -> None:
        """Set application tool ownership for future unmodified-left gestures."""

        value = str(owner or "").strip()
        self._left_capture_owner = value or None

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
        gizmo = self.orientation_gizmo.diagnostic_state()
        return ViewportDiagnosticState(
            ready=self.is_ready,
            render_window_class=_string_or_none(toolkit.get("render_window_class")),
            renderer_class=_string_or_none(toolkit.get("renderer_class")),
            interactor_style_class=_string_or_none(
                toolkit.get("interactor_style_class")
            ),
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
            observer_count=gizmo.observer_count,
            pointer_event_count=self._pointer_event_count,
            pick_count=self._pick_count,
            left_capture_owner=self._left_capture_owner,
            gesture_active=self._pointer_gesture.active,
            native_navigation_started=(
                self._pointer_gesture.native_navigation_started
            ),
            selection_eligible=self._pointer_gesture.selection_eligible,
            gesture_distance=self._pointer_gesture.accumulated_distance,
            gizmo_synchronization_count=gizmo.camera_update_count,
            orientation_gizmo=gizmo,
            scene_actor_inventory=self._scene_actor_inventory(),
            overlay_actor_inventory=self._overlay_actor_inventory(),
            last_synchronization=self.last_diagnostics,
            last_rendering_error=self._last_scene_error or self.last_error,
        )

    def pick_mesh(self, x_position: int, y_position: int) -> MeshPickResult:
        self._pick_count += 1
        if self.picking is None:
            return MeshPickResult(hit=False)
        return self.picking.pick_mesh(x_position, y_position)

    def pick_scene_object(
        self, x_position: int, y_position: int
    ) -> SceneObjectPickResult:
        self._pick_count += 1
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
        if self._qt_filter_installed and self.interactor is not None:
            self.interactor.removeEventFilter(self)
            self._qt_filter_installed = False
        self.view_controls.set_visible(False)
        self.orientation_gizmo.close()
        self._pointer_gesture.cancel()
        super().closeEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._position_axis_gizmo_renderer()
        self._position_view_controls()

    def event(self, event: QEvent) -> bool:
        handled = super().event(event)
        ratio_change = getattr(QEvent, "DevicePixelRatioChange", None)
        if ratio_change is not None and event.type() == ratio_change:
            # A monitor transition can change physical render-window pixels
            # without changing the desired 96-pixel logical presentation size.
            gizmo = getattr(self, "orientation_gizmo", None)
            if gizmo is not None:
                gizmo.update_layout()
        return handled

    def eventFilter(self, watched: object, event: object) -> bool:  # noqa: N802 - Qt API
        """Arbitrate unmodified-left between native orbit and active tools.

        QVTK remains the sole camera owner.  When no application tool captures
        left input, its existing press/move/release methods receive the event
        exactly once; selection is deferred until after a click release.
        """

        if watched is not self.interactor:
            return super().eventFilter(watched, event)
        if event.type() == QEvent.Leave and self._pointer_gesture.active:
            position = self._pointer_gesture.current_position or (0.0, 0.0)
            tool_owner = self._pointer_gesture.active_tool_owner
            self._pointer_gesture.cancel()
            self._last_pointer_release_was_click = False
            if tool_owner is not None:
                height = 0 if self.interactor is None else int(self.interactor.height())
                self._emit_pointer(
                    "leave",
                    int(round(position[0])),
                    max(height - int(round(position[1])) - 1, 0),
                )
            return False
        if not isinstance(event, QMouseEvent):
            return super().eventFilter(watched, event)
        event_type = event.type()
        x_position, y_position = self._vtk_pointer_position(event)
        if event_type == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            if event.modifiers() & (Qt.ShiftModifier | Qt.AltModifier):
                self._pointer_gesture.cancel()
                return False
            point = event.position()
            tool_owner = self._left_capture_owner
            self._pointer_gesture.press(
                point.x(),
                point.y(),
                button="left",
                active_tool_owner=tool_owner,
                native_navigation_started=tool_owner is None,
            )
            self._last_pointer_release_was_click = False
            if tool_owner is not None:
                self._emit_pointer("left_press", x_position, y_position)
                event.accept()
                return True
            return False
        if event_type == QEvent.MouseMove:
            if self._pointer_gesture.active:
                point = event.position()
                self._pointer_gesture.motion(point.x(), point.y())
                if self._pointer_gesture.active_tool_owner is not None:
                    self._emit_pointer("motion", x_position, y_position)
                    event.accept()
                    return True
                return False
            buttons = event.buttons()
            if buttons & (Qt.MiddleButton | Qt.RightButton) or (
                buttons & Qt.LeftButton
                and event.modifiers() & (Qt.ShiftModifier | Qt.AltModifier)
            ):
                # This is native TrackballCamera motion.  Emitting it as tool
                # hover/update would refresh the scene inside VTK's gesture,
                # which interrupted navigation whenever a tool was active.
                return False
            # Idle motion is sent only to a tool that explicitly owns left
            # input. Ordinary cursor motion stays out of application policy.
            if self._left_capture_owner is not None:
                self._emit_pointer("motion", x_position, y_position)
            return False
        if event_type == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            if not self._pointer_gesture.active:
                return False
            point = event.position()
            release = self._pointer_gesture.release(point.x(), point.y())
            self._last_pointer_release_was_click = release.is_click
            if release.active_tool_owner is not None:
                self._emit_pointer("left_release", x_position, y_position)
                event.accept()
                return True
            if release.is_click:
                # The event filter runs before QVTK's release handler. Defer
                # selection one event-loop turn so TrackballCamera always ends
                # its native interaction before scene policy may refresh.
                QTimer.singleShot(
                    0,
                    lambda x=x_position, y=y_position: self._emit_selection_click(
                        x, y
                    ),
                )
            return False
        return super().eventFilter(watched, event)

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
        self.orientation_gizmo.start()

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
            self.orientation_gizmo.sync_camera()
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
        assert self._transform_axes_actor is not None
        assert self._rotation_ring_actor is not None
        self._grid_actor.SetVisibility(bool(snapshot.display.get("show_grid", True)))
        bounds = snapshot.visible_bounds()
        extent = _overlay_extent(bounds)
        signature = (extent, 0.0, 0.0)
        if signature != self._grid_signature:
            _set_grid_geometry(self._grid_actor, extent)
            self._grid_signature = signature

        mode = str(snapshot.active_transform_mode or "").strip().lower()
        origin = _finite_origin(snapshot.object_origin)
        transform_visible = bool(
            snapshot.display.get("show_axes", True)
            and mode in {"move", "rotate"}
            and origin is not None
        )
        self._transform_axes_actor.SetVisibility(transform_visible)
        self._rotation_ring_actor.SetVisibility(
            transform_visible and mode == "rotate"
        )
        if transform_visible and origin is not None:
            self._transform_axes_actor.SetPosition(*origin)
            axes_size = max(extent * 0.34, 0.35)
            _style_transform_axes(
                self._transform_axes_actor,
                snapshot.active_transform_axis,
                axes_size,
            )
            if mode == "rotate":
                _set_rotation_ring_geometry(
                    self._rotation_ring_actor,
                    origin,
                    snapshot.active_transform_axis,
                    max(extent * 0.22, 0.25),
                    snapshot.active_transform_angle_delta,
                )

        self._set_axis_gizmo_visible(
            bool(snapshot.display.get("show_axis_gizmo", True))
        )
        self.view_controls.set_visible(
            bool(snapshot.display.get("show_viewcube", True))
        )
        self._position_axis_gizmo_renderer()
        self._position_view_controls()
        self.orientation_gizmo.sync_camera()

    def _ensure_display_overlays(self) -> None:
        if (
            self._grid_actor is not None
            and self._transform_axes_actor is not None
            and self._rotation_ring_actor is not None
        ):
            return
        from vtkmodules.vtkRenderingAnnotation import vtkAxesActor
        from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper, vtkRenderer

        grid_actor = vtkActor()
        grid_actor.SetMapper(vtkPolyDataMapper())
        grid_actor.GetProperty().SetColor(0.30, 0.34, 0.39)
        grid_actor.GetProperty().SetOpacity(0.42)
        grid_actor.GetProperty().SetLineWidth(1.0)
        grid_actor.PickableOff()

        transform_axes = vtkAxesActor()
        transform_axes.AxisLabelsOff()
        transform_axes.PickableOff()
        transform_axes.SetVisibility(False)

        rotation_ring = vtkActor()
        rotation_ring.SetMapper(vtkPolyDataMapper())
        rotation_ring.GetProperty().SetLineWidth(2.5)
        rotation_ring.PickableOff()
        rotation_ring.SetVisibility(False)

        self.renderer.AddActor(grid_actor)
        self.renderer.AddActor(transform_axes)
        self.renderer.AddActor(rotation_ring)
        self._grid_actor = grid_actor
        self._transform_axes_actor = transform_axes
        self._rotation_ring_actor = rotation_ring

    def _set_axis_gizmo_visible(self, visible: bool) -> None:
        self.orientation_gizmo.set_enabled(visible)

    def _position_axis_gizmo_renderer(self) -> None:
        self.orientation_gizmo.update_layout()

    def _position_view_controls(self) -> None:
        offset = (
            self.orientation_gizmo.logical_margin
            + self.orientation_gizmo.logical_size
            + GIZMO_CONTROL_GAP
            if self._axis_gizmo_visible
            else self.orientation_gizmo.logical_margin
        )
        self.view_controls.reposition(offset, self.orientation_gizmo.logical_margin)

    def _sync_axis_gizmo_camera(self) -> None:
        self.orientation_gizmo.sync_camera()

    def _on_camera_modified(self, _caller: object, _event: object) -> None:
        self.orientation_gizmo.sync_camera()

    def _record_scene_failure(self, context: str, exc: Exception) -> None:
        message = f"{context}: {type(exc).__name__}: {exc}"
        self._last_scene_error = message
        _LOG.exception(context)
        self.render_failed.emit(message)

    def _emit_pointer(self, event_name: str, x_position: int, y_position: int) -> None:
        self._pointer_event_count += 1
        self.pointer_event.emit(event_name, int(x_position), int(y_position), None)

    def _emit_selection_click(self, x_position: int, y_position: int) -> None:
        if self._closing:
            return
        self._last_pointer_release_was_click = True
        self._emit_pointer("left_release", x_position, y_position)

    def _vtk_pointer_position(self, event: QMouseEvent) -> tuple[int, int]:
        point = event.position()
        height = 0 if self.interactor is None else int(self.interactor.height())
        return (int(round(point.x())), max(height - int(round(point.y())) - 1, 0))

    def _scene_actor_inventory(self) -> tuple[Mapping[str, object], ...]:
        if self.synchronizer is None:
            return ()
        result: list[Mapping[str, object]] = []
        for category, item_id in sorted(self.synchronizer.cache.keys()):
            entry = self.synchronizer.cache.get(category, item_id)
            if entry is not None:
                result.append(
                    _actor_record(
                        f"{category}:{item_id}",
                        entry.actor,
                        0,
                        self.renderer,
                    )
                )
        return tuple(result)

    def _overlay_actor_inventory(self) -> tuple[Mapping[str, object], ...]:
        values = (
            ("grid", self._grid_actor, 0, self.renderer),
            ("transform_axes", self._transform_axes_actor, 0, self.renderer),
            ("rotation_ring", self._rotation_ring_actor, 0, self.renderer),
            (
                "orientation_gizmo",
                self._axis_gizmo_actor,
                self.orientation_gizmo.diagnostic_state().renderer_layer or 1,
                self._axis_gizmo_renderer,
            ),
        )
        return tuple(
            _actor_record(role, actor, layer, renderer)
            for role, actor, layer, renderer in values
            if actor is not None
        )

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


def _set_rotation_ring_geometry(
    actor: object,
    origin: tuple[float, float, float],
    axis: object,
    radius: float,
    angle_delta: object,
) -> None:
    from vtkmodules.vtkCommonCore import vtkPoints
    from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData

    axis_key = str(axis or "Z").strip().upper()
    points = vtkPoints()
    lines = vtkCellArray()
    segments = 96
    for index in range(segments):
        angle = (2.0 * math.pi * index) / segments
        cosine = math.cos(angle) * radius
        sine = math.sin(angle) * radius
        if axis_key == "X":
            point = (origin[0], origin[1] + cosine, origin[2] + sine)
        elif axis_key == "Y":
            point = (origin[0] + cosine, origin[1], origin[2] + sine)
        else:
            point = (origin[0] + cosine, origin[1] + sine, origin[2])
        points.InsertNextPoint(*point)
    for index in range(segments):
        lines.InsertNextCell(2)
        lines.InsertCellPoint(index)
        lines.InsertCellPoint((index + 1) % segments)
    try:
        angle = math.radians(float(angle_delta or 0.0))
    except (TypeError, ValueError):
        angle = 0.0
    if not math.isfinite(angle):
        angle = 0.0
    cosine = math.cos(angle) * radius
    sine = math.sin(angle) * radius
    if axis_key == "X":
        indicator = (origin[0], origin[1] + cosine, origin[2] + sine)
    elif axis_key == "Y":
        indicator = (origin[0] + cosine, origin[1], origin[2] + sine)
    else:
        indicator = (origin[0] + cosine, origin[1] + sine, origin[2])
    origin_id = points.InsertNextPoint(*origin)
    indicator_id = points.InsertNextPoint(*indicator)
    lines.InsertNextCell(2)
    lines.InsertCellPoint(origin_id)
    lines.InsertCellPoint(indicator_id)
    data = vtkPolyData()
    data.SetPoints(points)
    data.SetLines(lines)
    actor.GetMapper().SetInputData(data)
    color = {
        "X": (0.95, 0.18, 0.18),
        "Y": (0.2, 0.85, 0.25),
        "Z": (0.22, 0.48, 1.0),
    }.get(axis_key, (0.95, 0.74, 0.12))
    actor.GetProperty().SetColor(*color)


def _style_transform_axes(actor: object, axis: object, size: float) -> None:
    """Emphasize one constrained world axis without creating another prop."""

    axis_key = str(axis or "").strip().upper()
    colors = {
        "X": (0.95, 0.18, 0.18),
        "Y": (0.2, 0.85, 0.25),
        "Z": (0.22, 0.48, 1.0),
    }
    lengths = []
    for key in ("X", "Y", "Z"):
        emphasized = axis_key not in colors or key == axis_key
        opacity = 1.0 if emphasized else 0.28
        length = float(size) * (1.16 if key == axis_key else 1.0)
        lengths.append(length)
        for suffix in ("Shaft", "Tip"):
            prop = getattr(actor, f"Get{key}Axis{suffix}Property")()
            prop.SetColor(*colors[key])
            prop.SetOpacity(opacity)
    actor.SetTotalLength(*lengths)


def _finite_origin(value: object) -> tuple[float, float, float] | None:
    if value is None:
        return None
    try:
        values = np.asarray(value, dtype=float).reshape(3)
    except (TypeError, ValueError):
        return None
    if not np.all(np.isfinite(values)):
        return None
    return (float(values[0]), float(values[1]), float(values[2]))


def _actor_record(
    role: str,
    actor: object,
    layer: int,
    renderer: object | None,
) -> Mapping[str, object]:
    mapper = _safe_vtk_call(actor, "GetMapper")
    mapper_input = (
        None if mapper is None else _safe_vtk_call(mapper, "GetInput")
    )
    prop = _safe_vtk_call(actor, "GetProperty")
    return {
        "role": str(role),
        "layer": int(layer),
        "renderer_viewport": (
            None
            if renderer is None
            else _finite_tuple(_safe_vtk_call(renderer, "GetViewport"), 4)
        ),
        "class": _safe_vtk_call(actor, "GetClassName"),
        "mapper_class": (
            None if mapper is None else _safe_vtk_call(mapper, "GetClassName")
        ),
        "point_count": (
            None
            if mapper_input is None
            else _safe_vtk_call(mapper_input, "GetNumberOfPoints")
        ),
        "cell_count": (
            None
            if mapper_input is None
            else _safe_vtk_call(mapper_input, "GetNumberOfCells")
        ),
        "visible": bool(_safe_vtk_call(actor, "GetVisibility", default=False)),
        "pickable": bool(_safe_vtk_call(actor, "GetPickable", default=False)),
        "bounds": _finite_tuple(_safe_vtk_call(actor, "GetBounds"), 6),
        "color": (
            None
            if prop is None
            else _finite_tuple(_safe_vtk_call(prop, "GetColor"), 3)
        ),
        "opacity": (
            None if prop is None else _safe_vtk_call(prop, "GetOpacity")
        ),
    }


def _safe_vtk_call(
    owner: object,
    method_name: str,
    *,
    default: object = None,
) -> object:
    try:
        return getattr(owner, method_name)()
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return default


def _finite_tuple(value: object, length: int) -> tuple[float, ...] | None:
    try:
        values = tuple(float(item) for item in value)  # type: ignore[union-attr]
    except (TypeError, ValueError):
        return None
    return values if len(values) == length and all(np.isfinite(values)) else None


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
