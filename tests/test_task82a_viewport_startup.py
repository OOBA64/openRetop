from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import platform
import sys
import unittest
from unittest.mock import patch

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "packages" / "workbench_ui"))

from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from bootstrap import create_application  # noqa: E402
from infrastructure.settings_repository import InMemorySettingsRepository  # noqa: E402
from mesh.triangle_mesh import TriangleMeshData  # noqa: E402
from presentation.qt.main_window import OpenRetopV3Window  # noqa: E402
from presentation.qt.viewport import (  # noqa: E402
    QtSceneViewport,
    normalized_background_color,
)
from scripts.diagnose_vtk_viewport import add_diagnostic_sphere  # noqa: E402
from viewer.scene_types import (  # noqa: E402
    CameraRequest,
    DisplayStyleSnapshot,
    MeshRenderItem,
    SceneSnapshot,
)
from workbench_ui.viewport import VTKViewportWidget  # noqa: E402


def _mesh_snapshot(
    *,
    revision: int = 1,
    background: object = "#204060",
    camera_request: CameraRequest | None = None,
) -> SceneSnapshot:
    mesh = TriangleMeshData(
        vertices=np.asarray(
            [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 3.0, 0.0]],
            dtype=float,
        ),
        triangles=np.asarray([[0, 1, 2]], dtype=int),
    )
    return SceneSnapshot(
        revision=revision,
        meshes=(
            MeshRenderItem(
                id="mesh",
                revision=revision,
                mesh=mesh,
                style=DisplayStyleSnapshot(color=(0.8, 0.8, 0.8)),
                local_bounds=((0.0, 0.0, 0.0), (2.0, 3.0, 0.0)),
            ),
        ),
        display={
            "show_grid": False,
            "show_axes": False,
            "display_colors": {"background_color": background},
        },
        camera_request=camera_request or CameraRequest(),
    )


def _emit_ready_without_native_render(viewport: QtSceneViewport) -> None:
    # Unit tests exercise scene readiness independently from a real display.
    # The visible integration test below covers the actual Initialize/Render path.
    with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
        viewport._is_ready = True
        viewport.ready.emit()


class _FakeInteractor:
    def __init__(self, *, fail_initialize: bool = False) -> None:
        self.initialize_calls = 0
        self.start_calls = 0
        self.initialized = False
        self.fail_initialize = fail_initialize

    def isVisible(self) -> bool:
        return True

    def Initialize(self) -> None:
        self.initialize_calls += 1
        if self.fail_initialize:
            raise RuntimeError("synthetic initialization failure")
        self.initialized = True

    def Start(self) -> None:
        self.start_calls += 1

    def GetInitialized(self) -> int:
        return int(self.initialized)


class Task82AVTKViewportStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_concrete_vtk_modules_are_imported_before_renderer_use(self) -> None:
        for module_name in (
            "vtkmodules.vtkRenderingOpenGL2",
            "vtkmodules.vtkInteractionStyle",
            "vtkmodules.vtkRenderingFreeType",
        ):
            self.assertIn(module_name, sys.modules)
        viewport = VTKViewportWidget()
        try:
            self.assertTrue(viewport.available)
            self.assertNotEqual(
                viewport.render_window.GetClassName(),
                "vtkRenderWindow",
            )
        finally:
            viewport.close()

    def test_start_is_idempotent_and_initializes_once(self) -> None:
        viewport = VTKViewportWidget()
        original = viewport.interactor
        fake = _FakeInteractor()
        viewport.interactor = fake
        try:
            with patch.dict(os.environ, {"QT_QPA_PLATFORM": "windows"}):
                self.assertTrue(viewport.start())
                self.assertTrue(viewport.start())
            self.assertEqual(fake.initialize_calls, 1)
            self.assertEqual(fake.start_calls, 1)
            self.assertEqual(viewport.initialization_count, 1)
        finally:
            viewport.interactor = original
            viewport.close()

    def test_starting_twice_does_not_duplicate_renderers(self) -> None:
        viewport = VTKViewportWidget()
        original = viewport.interactor
        viewport.interactor = _FakeInteractor()
        try:
            before = viewport.render_window.GetRenderers().GetNumberOfItems()
            with patch.dict(os.environ, {"QT_QPA_PLATFORM": "windows"}):
                viewport.start()
                viewport.start()
            after = viewport.render_window.GetRenderers().GetNumberOfItems()
            self.assertEqual((before, after), (1, 1))
        finally:
            viewport.interactor = original
            viewport.close()

    def test_render_before_readiness_is_safe(self) -> None:
        viewport = VTKViewportWidget()
        try:
            self.assertFalse(viewport.is_ready)
            self.assertFalse(viewport.render())
            self.assertIsNone(viewport.last_error)
        finally:
            viewport.close()

    def test_offscreen_start_and_render_suppress_native_opengl_work(self) -> None:
        viewport = VTKViewportWidget()
        try:
            with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
                self.assertFalse(viewport.start())
                viewport._is_ready = True
                self.assertFalse(viewport.render())
                state = viewport.diagnostic_state()
            self.assertTrue(state["offscreen_start_suppressed"])
            self.assertEqual(viewport.initialization_count, 0)
        finally:
            viewport.close()

    def test_snapshot_submitted_before_readiness_is_retained(self) -> None:
        viewport = QtSceneViewport()
        snapshot = _mesh_snapshot()
        try:
            self.assertIsNone(viewport.render_snapshot(snapshot))
            self.assertIs(viewport.pending_snapshot, snapshot)
            self.assertEqual(viewport.synchronization_count, 0)
        finally:
            viewport.close()

    def test_retained_snapshot_synchronizes_once_after_readiness(self) -> None:
        viewport = QtSceneViewport()
        snapshot = _mesh_snapshot(camera_request=CameraRequest.frame_all())
        try:
            viewport.render_snapshot(snapshot)
            _emit_ready_without_native_render(viewport)
            self.assertIsNone(viewport.pending_snapshot)
            self.assertIs(viewport.last_snapshot, snapshot)
            self.assertEqual(viewport.synchronization_count, 1)
            self.assertEqual(viewport.last_diagnostics.created, 1)
            viewport.ready.emit()
            self.assertEqual(viewport.synchronization_count, 1)
        finally:
            viewport.close()

    def test_repeated_refresh_reuses_cached_actors(self) -> None:
        viewport = QtSceneViewport()
        snapshot = _mesh_snapshot()
        try:
            viewport.render_snapshot(snapshot)
            _emit_ready_without_native_render(viewport)
            actor = viewport.synchronizer.cache.get("mesh", "mesh").actor
            with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
                diagnostics = viewport.render_snapshot(replace(snapshot, revision=2))
            self.assertEqual(diagnostics.reused, 1)
            self.assertIs(viewport.synchronizer.cache.get("mesh", "mesh").actor, actor)
        finally:
            viewport.close()

    def test_readiness_does_not_duplicate_vtk_event_observers(self) -> None:
        viewport = QtSceneViewport()
        try:
            _emit_ready_without_native_render(viewport)
            first_ids = tuple(viewport._observer_ids)
            viewport.ready.emit()
            self.assertEqual(viewport.observer_count, 5)
            self.assertEqual(tuple(viewport._observer_ids), first_ids)
        finally:
            viewport.close()

    def test_renderer_background_receives_configured_color(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.render_snapshot(_mesh_snapshot(background="#204060"))
            _emit_ready_without_native_render(viewport)
            self.assertTrue(
                np.allclose(
                    viewport.renderer.GetBackground(),
                    (32 / 255.0, 64 / 255.0, 96 / 255.0),
                )
            )
        finally:
            viewport.close()

    def test_invalid_background_falls_back_to_application_default(self) -> None:
        self.assertTrue(
            np.allclose(
                normalized_background_color("not-a-color"),
                (16 / 255.0, 19 / 255.0, 22 / 255.0),
            )
        )

    def test_diagnostic_path_adds_visible_synthetic_actor(self) -> None:
        from vtkmodules.vtkRenderingCore import vtkRenderer

        renderer = vtkRenderer()
        actor = add_diagnostic_sphere(renderer)
        actor.GetMapper().Update()
        self.assertEqual(renderer.GetActors().GetNumberOfItems(), 1)
        self.assertEqual(actor.GetVisibility(), 1)
        self.assertGreater(actor.GetMapper().GetInput().GetNumberOfPoints(), 0)

    def test_camera_framing_runs_after_valid_renderer_dimensions(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.render_snapshot(
                _mesh_snapshot(camera_request=CameraRequest.frame_all())
            )
            with patch.object(viewport, "_renderer_has_size", return_value=True):
                _emit_ready_without_native_render(viewport)
            camera = viewport.renderer.GetActiveCamera()
            self.assertTrue(np.allclose(camera.GetFocalPoint(), (1.0, 1.5, 0.0)))
            self.assertGreater(camera.GetClippingRange()[0], 0.0)
            self.assertIsNone(viewport._pending_camera_request)
        finally:
            viewport.close()

    def test_initialization_exception_is_logged_and_emitted(self) -> None:
        viewport = VTKViewportWidget()
        original = viewport.interactor
        viewport.interactor = _FakeInteractor(fail_initialize=True)
        failures: list[str] = []
        viewport.initialization_failed.connect(failures.append)
        try:
            with self.assertLogs("workbench_ui.viewport", level="ERROR"):
                with patch.dict(os.environ, {"QT_QPA_PLATFORM": "windows"}):
                    self.assertFalse(viewport.start())
            self.assertEqual(len(failures), 1)
            self.assertIn("synthetic initialization failure", failures[0])
            self.assertIn("synthetic initialization failure", viewport.last_error)
        finally:
            viewport.interactor = original
            viewport.close()

    def test_main_window_constructor_defers_first_native_scene_sync(self) -> None:
        composition = create_application(
            settings_repository=InMemorySettingsRepository()
        )
        window = OpenRetopV3Window(composition)
        try:
            self.assertEqual(window.viewport.synchronization_count, 0)
            self.assertIsNotNone(window.viewport.pending_snapshot)
            self.assertFalse(window.viewport.is_ready)
        finally:
            window.close()

    def test_main_window_does_not_rely_on_deleted_tk_shell(self) -> None:
        legacy_source = ROOT / "src" / "app"
        self.assertFalse(legacy_source.exists() and any(legacy_source.glob("*.py")))
        source = (ROOT / "src" / "presentation" / "qt" / "main_window.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("tkinter", source)
        self.assertNotIn("src.app", source)

    def test_no_production_startup_path_contains_diagnostic_geometry(self) -> None:
        production_files = tuple((ROOT / "src").rglob("*.py")) + tuple(
            (ROOT / "packages" / "workbench_ui" / "workbench_ui").rglob("*.py")
        )
        for path in production_files:
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("vtkSphereSource", source, path)
            self.assertNotIn("add_test_geometry", source, path)

    @unittest.skipIf(
        os.environ.get("QT_QPA_PLATFORM", "").strip().lower() == "offscreen"
        or platform.system() != "Windows",
        "requires a visible Windows Qt platform",
    )
    def test_real_visible_windows_qt_vtk_render_smoke(self) -> None:
        viewport = VTKViewportWidget()
        viewport.resize(720, 480)
        viewport.show()
        try:
            self.assertTrue(viewport.start())
            actor = add_diagnostic_sphere(viewport.renderer)
            viewport.renderer.ResetCamera()
            self.assertTrue(viewport.render())
            QTest.qWait(150)
            self.assertIn("OpenGL", viewport.render_window.GetClassName())
            self.assertEqual(actor.GetVisibility(), 1)
            self.assertIsNone(viewport.last_error)
        finally:
            viewport.close()


if __name__ == "__main__":
    unittest.main()
