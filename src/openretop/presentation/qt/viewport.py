"""Qt host for openRetop's snapshot-driven VTK viewport."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Mapping

import numpy as np
from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QMouseEvent, QResizeEvent

from openretop.application.transform_controller import CameraVectors
from openretop.presentation.qt.adaptive_grid import AdaptiveGrid
from openretop.presentation.qt.measurement_overlay import MeasurementOverlay
from openretop.presentation.qt.pointer_gestures import PointerGestureState
from openretop.presentation.qt.selection_overlay import SelectionBoxOverlay
from openretop.presentation.qt.tool_hint_overlay import ToolHintOverlay
from openretop.presentation.qt.transform_overlays import (
    TransformOverlayController,
    TransformOverlayDiagnosticState,
)
from openretop.presentation.qt.view_controls import (
    NavigationClusterDiagnosticState,
    ViewportNavigationCluster,
)
from openretop.settings.settings_data import DEFAULT_BACKGROUND_COLOR
from openretop.viewer.actor_factories import VTKActorAdapter
from openretop.viewer.camera_controller import CameraController
from openretop.viewer.picking_service import MeshPickResult, PickingService, SceneObjectPickResult
from openretop.viewer.scene_synchronizer import ActorUpdateDiagnostics, SceneSynchronizer
from openretop.viewer.scene_types import Bounds3, CameraRequest, CameraRequestKind, SceneSnapshot
from workbench_ui import VTKViewportWidget

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
    navigation: NavigationClusterDiagnosticState
    transform_overlay: TransformOverlayDiagnosticState
    scene_actor_inventory: tuple[Mapping[str, object], ...]
    overlay_actor_inventory: tuple[Mapping[str, object], ...]
    renderer_prop_inventory: tuple[Mapping[str, object], ...]
    last_synchronization: ActorUpdateDiagnostics | None
    last_rendering_error: str | None


class QtSceneViewport(VTKViewportWidget):
    """Apply openRetop scene snapshots after the generic host becomes ready."""

    pointer_event = Signal(str, int, int, object)
    grid_spacing_changed = Signal(float)
    scene_synchronized = Signal(object)

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self.synchronizer: SceneSynchronizer | None = None
        self.camera_controller: CameraController | None = None
        self._studio_lights = False
        self.last_snapshot: SceneSnapshot | None = None
        self.last_diagnostics: ActorUpdateDiagnostics | None = None
        self.picking: PickingService | None = None
        self._pending_snapshot: SceneSnapshot | None = None
        self._pending_camera_request: CameraRequest | None = None
        self._synchronization_count = 0
        self._last_scene_error: str | None = None
        self.grid = AdaptiveGrid(self.renderer, on_spacing_changed=self.grid_spacing_changed.emit)
        self.transform_overlays = TransformOverlayController(self.renderer)
        self.selection_box = SelectionBoxOverlay(self.renderer)
        self.measurement_overlay = MeasurementOverlay(self.renderer)
        self._pointer_gesture = PointerGestureState()
        self._left_capture_owner: str | None = None
        self._last_pointer_release_was_click = True
        self._pointer_event_count = 0
        self._last_pointer: tuple[int, int] | None = None  # Qt widget coordinates (y down)
        self._pick_count = 0
        self._qt_filter_installed = False
        self.navigation_cluster = ViewportNavigationCluster(
            self.render_window,
            self.renderer,
            self.interactor,
            self,
            device_pixel_ratio=self.devicePixelRatioF,
            request_render=self._render_navigation,
        )
        self.view_controls = self.navigation_cluster
        self.tool_hint = ToolHintOverlay(self.render_window, self.renderer, device_pixel_ratio=self.devicePixelRatioF)
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
        return self.navigation_cluster.observer_count

    @property
    def _observer_ids(self) -> tuple[tuple[object, int], ...]:
        """The navigation cluster's sole VTK observer."""

        return self.navigation_cluster.observer_records

    @property
    def _transform_axes_actor(self) -> object | None:
        """Compatibility view; the focused controller owns this actor."""

        return self.transform_overlays.move_actor

    @property
    def _rotation_ring_actor(self) -> object | None:
        """Compatibility view; the focused controller owns this actor."""

        return self.transform_overlays.ring_actor

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
        """The background setting is the floor colour of a soft vertical gradient."""

        color = normalized_background_color(value)
        if self.renderer is not None:
            self.renderer.SetBackground(*color)
            self.renderer.SetBackground2(*gradient_top_color(color))
            self.renderer.GradientBackgroundOn()
        return color

    def diagnostic_state(self) -> ViewportDiagnosticState:
        snapshot = self.last_snapshot or self._pending_snapshot
        camera = None if self.renderer is None else self.renderer.GetActiveCamera()
        toolkit = super().diagnostic_state()
        navigation = self.navigation_cluster.diagnostic_state()
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
            observer_count=navigation.observer_count,
            pointer_event_count=self._pointer_event_count,
            pick_count=self._pick_count,
            left_capture_owner=self._left_capture_owner,
            gesture_active=self._pointer_gesture.active,
            native_navigation_started=(
                self._pointer_gesture.native_navigation_started
            ),
            selection_eligible=self._pointer_gesture.selection_eligible,
            gesture_distance=self._pointer_gesture.accumulated_distance,
            gizmo_synchronization_count=navigation.camera_update_count,
            navigation=navigation,
            transform_overlay=self.transform_overlays.diagnostics(),
            scene_actor_inventory=self._scene_actor_inventory(),
            overlay_actor_inventory=self._overlay_actor_inventory(),
            renderer_prop_inventory=self.renderer_prop_inventory(),
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

    @property
    def last_pointer_position(self) -> tuple[int, int]:
        """The last pointer position seen over the viewport, in widget coordinates (y down).

        Falls back to the viewport centre before the pointer has ever been over it. This is
        the reference a Move/Rotate transform starts from, so the object does not jump on the
        first mouse movement.
        """

        if self._last_pointer is not None:
            return self._last_pointer
        width = 0 if self.interactor is None else int(self.interactor.width())
        height = 0 if self.interactor is None else int(self.interactor.height())
        return (width // 2, height // 2)

    def to_widget_position(self, x_position: int, y_position: int) -> tuple[int, int]:
        """Convert VTK display coordinates (y up) to widget coordinates (y down)."""

        height = 0 if self.interactor is None else int(self.interactor.height())
        return (int(x_position), max(height - int(y_position) - 1, 0))

    def set_tool_hint(self, text: str) -> None:
        """Show the active tool's instructions on the canvas ('' hides them)."""

        if text == self.tool_hint.text:
            return
        self.tool_hint.set_text(text)
        if self.is_ready:
            self._render_navigation()

    def set_measurements(self, measurements: object, pending: object, units: str) -> None:
        """Show the measure tool's lines, points and distance labels over the scene."""

        if self.renderer is None:
            return
        self.measurement_overlay.update(measurements, pending, units)  # type: ignore[arg-type]

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
        self.transform_overlays.close()
        self.selection_box.close()
        self.measurement_overlay.close()
        self.grid.close()
        self.navigation_cluster.close()
        self.tool_hint.close()
        self._pointer_gesture.cancel()
        super().closeEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self.navigation_cluster.update_layout()

    def event(self, event: QEvent) -> bool:
        handled = super().event(event)
        ratio_change = getattr(QEvent, "DevicePixelRatioChange", None)
        if ratio_change is not None and event.type() == ratio_change:
            # A monitor transition can change physical render-window pixels
            # without changing the desired 96-pixel logical presentation size.
            cluster = getattr(self, "navigation_cluster", None)
            if cluster is not None:
                cluster.update_layout()
        return handled

    def eventFilter(self, watched: object, event: object) -> bool:  # noqa: N802 - Qt API
        """Arbitrate unmodified-left between native orbit and active tools.

        QVTK remains the sole camera owner.  When no application tool captures
        left input, its existing press/move/release methods receive the event
        exactly once; selection is deferred until after a click release.
        """

        if watched is not self.interactor:
            return super().eventFilter(watched, event)
        if isinstance(event, QMouseEvent):
            point = event.position()
            self._last_pointer = (int(round(point.x())), int(round(point.y())))
        if event.type() == QEvent.Leave:
            self.navigation_cluster.leave()
        elif isinstance(event, QMouseEvent) and self.navigation_cluster.handle_mouse_event(event):
            # A click on the view cube must not start an orbit or a selection pick.
            event.accept()
            return True
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
        if not self._studio_lights:
            install_studio_lights(self.renderer)
            self._studio_lights = True
        self.navigation_cluster.start()

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
                self.grid.sync()
            self.navigation_cluster.sync_camera()
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
        # The grid follows the camera, not the scene, so moving an object never rescales it.
        self.grid.set_visible(bool(snapshot.display.get("show_grid", True)))

        self.selection_box.update(snapshot)
        if not self.transform_overlays.update(snapshot):
            diagnostics = self.transform_overlays.diagnostics()
            if diagnostics.last_error:
                raise RuntimeError(diagnostics.last_error)

        self.navigation_cluster.set_visibility(
            gizmo=bool(snapshot.display.get("show_axis_gizmo", True)),
            controls=bool(snapshot.display.get("show_viewcube", True)),
        )
        self.navigation_cluster.sync_camera()

    def _render_navigation(self) -> None:
        if self.is_ready and not self._closing:
            self.render()

    def _position_view_controls(self) -> None:
        self.navigation_cluster.update_layout()

    def _on_camera_modified(self, _caller: object, _event: object) -> None:
        self.navigation_cluster.sync_camera()

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
            ("grid", self.grid.lines_actor, 0, self.renderer),
            ("grid_axes", self.grid.axes_actor, 0, self.renderer),
            ("transform_axes", self._transform_axes_actor, self.transform_overlays.overlay_layer or 0, self.transform_overlays.layer_renderer or self.renderer),
            ("rotation_ring", self._rotation_ring_actor, self.transform_overlays.overlay_layer or 0, self.transform_overlays.layer_renderer or self.renderer),
            ("transform_guide", self.transform_overlays.guide_actor, self.transform_overlays.overlay_layer or 0, self.transform_overlays.layer_renderer or self.renderer),
            ("selection_box", self.selection_box.actor, 0, self.renderer),
            (
                "view_cube",
                self.navigation_cluster.overlay_actor,
                _safe_vtk_call(self.navigation_cluster.overlay_renderer, "GetLayer", default=1),
                self.navigation_cluster.overlay_renderer,
            ),
        )
        return tuple(
            _actor_record(role, actor, layer, renderer)
            for role, actor, layer, renderer in values
            if actor is not None
        )

    def renderer_prop_inventory(self) -> tuple[Mapping[str, object], ...]:
        """Return a complete, on-demand inventory without startup logging."""

        roles: dict[int, str] = {}
        if self.synchronizer is not None:
            for category, item_id in sorted(self.synchronizer.cache.keys()):
                entry = self.synchronizer.cache.get(category, item_id)
                if entry is not None:
                    roles[id(entry.actor)] = f"{category}:{item_id}"
        for measurement_actor in self.measurement_overlay.actors:
            roles[id(measurement_actor)] = "measurement"
        for role, actor in (
            ("grid", self.grid.lines_actor),
            ("grid_axes", self.grid.axes_actor),
            ("transform_axes", self._transform_axes_actor),
            ("rotation_ring", self._rotation_ring_actor),
            ("transform_guide", self.transform_overlays.guide_actor),
            ("tool_hint", self.tool_hint.actor),
            ("selection_box", self.selection_box.actor),
            ("view_cube", self.navigation_cluster.overlay_actor),
        ):
            if actor is not None:
                roles[id(actor)] = role

        result: list[Mapping[str, object]] = []
        renderers = _collection_items(self.render_window, "GetRenderers", "GetNextItem")
        for renderer in renderers:
            layer_value = _safe_vtk_call(renderer, "GetLayer", default=0)
            try:
                layer = int(layer_value)
            except (TypeError, ValueError):
                layer = 0
            props = _collection_items(renderer, "GetViewProps", "GetNextProp")
            for index, actor in enumerate(props):
                role = roles.get(id(actor), f"unidentified:{layer}:{index}")
                result.append(_actor_record(role, actor, layer, renderer))
        return tuple(result)

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


GRADIENT_TOP_TINT = (0.23, 0.255, 0.30)  # a cool slate the top of the view fades towards
GRADIENT_TOP_MIX = 0.55


def gradient_top_color(bottom: tuple[float, float, float]) -> tuple[float, float, float]:
    """The top of the background gradient: the floor colour lifted towards a cool slate."""

    return tuple(  # type: ignore[return-value]
        float(base + (tint - base) * GRADIENT_TOP_MIX) for base, tint in zip(bottom, GRADIENT_TOP_TINT)
    )


def install_studio_lights(renderer: object) -> None:
    """Key, fill, back and head lights instead of VTK's single headlight.

    Fixed to the camera, so the model is lit the same way from every view: the key light
    from the upper left gives shape, the fill keeps shadows readable, the back light picks
    out the silhouette.
    """

    from vtkmodules.vtkRenderingCore import vtkLightKit

    renderer.RemoveAllLights()  # type: ignore[attr-defined]
    kit = vtkLightKit()
    kit.SetKeyLightIntensity(0.85)
    kit.SetKeyLightElevation(50.0)
    kit.SetKeyLightAzimuth(-25.0)
    kit.SetKeyToFillRatio(2.6)
    kit.SetKeyToHeadRatio(3.2)
    kit.SetKeyToBackRatio(3.0)
    kit.MaintainLuminanceOff()
    kit.AddLightsToRenderer(renderer)


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
    visible = bool(_safe_vtk_call(actor, "GetVisibility", default=False))
    use_bounds = bool(_safe_vtk_call(actor, "GetUseBounds", default=False))
    main_renderer_member = bool(
        renderer is not None
        and int(_safe_vtk_call(renderer, "GetLayer", default=0) or 0) == 0
        and _renderer_has_prop(renderer, actor)
    )
    return {
        "role": str(role),
        "semantic_category": _semantic_category(role),
        "layer": int(layer),
        "renderer_class": (
            None if renderer is None else _safe_vtk_call(renderer, "GetClassName")
        ),
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
        "visible": visible,
        "pickable": bool(_safe_vtk_call(actor, "GetPickable", default=False)),
        "draggable": bool(_safe_vtk_call(actor, "GetDragable", default=False)),
        "use_bounds": use_bounds,
        "bounds": _finite_tuple(_safe_vtk_call(actor, "GetBounds"), 6),
        "position": _finite_tuple(_safe_vtk_call(actor, "GetPosition"), 3),
        "user_matrix": _matrix_tuple(_safe_vtk_call(actor, "GetUserMatrix")),
        "main_renderer_member": main_renderer_member,
        "contributes_to_main_visible_bounds": bool(
            main_renderer_member and visible and use_bounds
        ),
        "color": (
            None
            if prop is None
            else _finite_tuple(_safe_vtk_call(prop, "GetColor"), 3)
        ),
        "opacity": (
            None if prop is None else _safe_vtk_call(prop, "GetOpacity")
        ),
        "representation": (
            None if prop is None else _safe_vtk_call(prop, "GetRepresentation")
        ),
        "line_width": (
            None if prop is None else _safe_vtk_call(prop, "GetLineWidth")
        ),
    }


def _semantic_category(role: str) -> str:
    prefix = str(role).split(":", 1)[0]
    return {
        "mesh": "imported_scene_geometry",
        "curve": "scene_geometry",
        "surface": "scene_geometry",
        "region": "selection_overlay",
        "section_plane": "section_plane",
        "section_result": "scene_geometry",
        "tool_preview": "selection_overlay",
        "grid": "grid",
        "grid_axes": "grid",
        "transform_axes": "transform_axes",
        "rotation_ring": "rotation_ring",
        "view_cube": "view_cube",
        "measurement": "measurement",
        "selection_box": "selection_overlay",
        "transform_guide": "transform_axes",
        "tool_hint": "tool_hint",
    }.get(prefix, "unidentified")


def _renderer_has_prop(renderer: object, actor: object) -> bool:
    try:
        return bool(renderer.HasViewProp(actor))
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return False


def _collection_items(
    owner: object | None,
    getter_name: str,
    next_name: str,
) -> tuple[object, ...]:
    if owner is None:
        return ()
    try:
        collection = getattr(owner, getter_name)()
        collection.InitTraversal()
        count = int(collection.GetNumberOfItems())
        return tuple(getattr(collection, next_name)() for _ in range(count))
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return ()


def _matrix_tuple(value: object) -> tuple[float, ...] | None:
    if value is None:
        return None
    try:
        values = tuple(
            float(value.GetElement(row, column))
            for row in range(4)
            for column in range(4)
        )
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return None
    return values if all(np.isfinite(values)) else None


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
