"""Qt host for the Task 77 snapshot viewport infrastructure."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Signal

from workbench_ui import VTKViewportWidget

from application.transform_controller import CameraVectors
from viewer.actor_factories import VTKActorAdapter
from viewer.camera_controller import CameraController
from viewer.picking_service import MeshPickResult, PickingService, SceneObjectPickResult
from viewer.scene_synchronizer import ActorUpdateDiagnostics, SceneSynchronizer
from viewer.scene_types import SceneSnapshot


class QtSceneViewport(VTKViewportWidget):
    """Apply scene snapshots through the shared VTK synchronizer and camera."""

    pointer_event = Signal(str, int, int, object)

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self.synchronizer: SceneSynchronizer | None = None
        self.camera_controller: CameraController | None = None
        self.last_snapshot: SceneSnapshot | None = None
        self.last_diagnostics: ActorUpdateDiagnostics | None = None
        self.picking: PickingService | None = None
        self._observer_ids: list[int] = []
        if self.renderer is not None:
            self.picking = PickingService(self.renderer)
            self.synchronizer = SceneSynchronizer(
                VTKActorAdapter(self.renderer, self.picking)
            )
            self.camera_controller = CameraController(self.renderer)
        if self.interactor is not None:
            for vtk_name, event_name in (
                ("LeftButtonPressEvent", "left_press"),
                ("LeftButtonReleaseEvent", "left_release"),
                ("MouseMoveEvent", "motion"),
                ("RightButtonPressEvent", "right_press"),
                ("RightButtonReleaseEvent", "right_release"),
            ):
                observer_id = self.interactor.AddObserver(
                    vtk_name,
                    lambda caller, _event, name=event_name: self._emit_pointer(name, caller),
                )
                self._observer_ids.append(int(observer_id))

    def render_snapshot(self, snapshot: SceneSnapshot) -> ActorUpdateDiagnostics | None:
        if self.synchronizer is None or self.camera_controller is None:
            return None
        self.last_diagnostics = self.synchronizer.synchronize(snapshot)
        self.last_snapshot = snapshot
        if snapshot.camera_request.kind.value != "none":
            self.camera_controller.apply(snapshot.camera_request, snapshot)
        self.render()
        return self.last_diagnostics

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
        if self.renderer is None:
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

    def model_bounds(self):
        return None if self.last_snapshot is None else self.last_snapshot.visible_bounds()

    def project_points(self, world_points: object) -> np.ndarray:
        if self.renderer is None:
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

        if self.renderer is None:
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
        self.renderer.SetDisplayPoint(float(x_position), float(y_position), float(depth))
        self.renderer.DisplayToWorld()
        value = np.asarray(self.renderer.GetWorldPoint(), dtype=float).reshape(4)
        if not np.all(np.isfinite(value)) or abs(float(value[3])) <= 1e-12:
            return None
        return value[:3] / value[3]


def _unit(value: object) -> np.ndarray | None:
    vector = np.asarray(value, dtype=float).reshape(3)
    length = float(np.linalg.norm(vector))
    if not np.isfinite(length) or length <= 1e-12:
        return None
    return vector / length
