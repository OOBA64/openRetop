"""Qt host for the Task 77 snapshot viewport infrastructure."""

from __future__ import annotations

from workbench_ui import VTKViewportWidget

from viewer.actor_factories import VTKActorAdapter
from viewer.camera_controller import CameraController
from viewer.scene_synchronizer import ActorUpdateDiagnostics, SceneSynchronizer
from viewer.scene_types import SceneSnapshot


class QtSceneViewport(VTKViewportWidget):
    """Apply scene snapshots through the shared VTK synchronizer and camera."""

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self.synchronizer: SceneSynchronizer | None = None
        self.camera_controller: CameraController | None = None
        self.last_snapshot: SceneSnapshot | None = None
        self.last_diagnostics: ActorUpdateDiagnostics | None = None
        if self.renderer is not None:
            self.synchronizer = SceneSynchronizer(VTKActorAdapter(self.renderer))
            self.camera_controller = CameraController(self.renderer)

    def render_snapshot(self, snapshot: SceneSnapshot) -> ActorUpdateDiagnostics | None:
        if self.synchronizer is None or self.camera_controller is None:
            return None
        self.last_diagnostics = self.synchronizer.synchronize(snapshot)
        self.last_snapshot = snapshot
        if snapshot.camera_request.kind.value != "none":
            self.camera_controller.apply(snapshot.camera_request, snapshot)
        self.render()
        return self.last_diagnostics
