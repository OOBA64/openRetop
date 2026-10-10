from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from openretop.application.actions import CORE_ACTIONS  # noqa: E402
from openretop.application.scene_ids import region_node_id  # noqa: E402
from openretop.application.state import MeshObjectState  # noqa: E402
from openretop.bootstrap import create_application  # noqa: E402
from openretop.infrastructure.settings_repository import InMemorySettingsRepository  # noqa: E402
from openretop.mesh.triangle_mesh import TriangleMeshData  # noqa: E402
from openretop.presentation.qt.main_window import OpenRetopV3Window  # noqa: E402
from openretop.project.project_data import ProjectCurve, ProjectSurface  # noqa: E402
from openretop.project.project_io import load_project, save_project  # noqa: E402
from openretop.regions.region_state import RegionSelection  # noqa: E402
from openretop.viewer.picking_service import MeshPickResult  # noqa: E402


def _composition():
    return create_application(settings_repository=InMemorySettingsRepository())


def _mesh_object() -> MeshObjectState:
    mesh = TriangleMeshData(
        vertices=np.asarray(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            dtype=float,
        ),
        triangles=np.asarray([[0, 1, 2]], dtype=int),
    )
    return MeshObjectState(
        source_mesh=mesh,
        display_mesh=mesh.copy(),
        file_path=None,
        name="Mesh",
        origin=np.zeros(3),
        location=np.zeros(3),
        rotation=np.zeros(3),
        transform_matrix=np.identity(4),
    )


class MainWindowWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_v3_shell_contains_scene_viewport_inspector_palette_and_actions(self) -> None:
        window = OpenRetopV3Window(_composition())
        try:
            self.assertEqual(window.windowTitle(), "openRetop V3")
            self.assertIn("view.frame_all", {item.id for item in window._framework_actions.definitions})
            self.assertIn("scene", window._docks)
            self.assertIn("properties", window._docks)
            self.assertIn("commands", window._docks)
            self.assertTrue(window.viewport.available)
            self.assertGreaterEqual(len(window._scene_model.nodes), 1)
            self.assertEqual(
                {definition.id for definition in CORE_ACTIONS},
                {definition.id for definition in window._application_actions.definitions},
            )
            self.assertTrue(
                {definition.id for definition in CORE_ACTIONS}.issubset(window._qt_actions)
            )
        finally:
            window.close()

    def test_central_actions_drive_frame_and_visibility_without_widget_handlers(self) -> None:
        window = OpenRetopV3Window(_composition())
        try:
            self.assertTrue(window._dispatch_framework_action("view.frame_all"))
            self.assertTrue(window._dispatch_application_action("scene.show_all"))
            self.assertEqual(window._camera_request.kind.value, "none")
        finally:
            window.close()

    def test_project_save_and_open_use_persistence_service(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v3.openretop"
            window = OpenRetopV3Window(_composition())
            try:
                with patch("openretop.presentation.qt.main_window.QFileDialog.getSaveFileName", return_value=(str(path), "")):
                    self.assertTrue(window.save_project(as_dialog=True))
                self.assertTrue(path.exists())
                self.assertIn("version", json.loads(path.read_text(encoding="utf-8")))
                with patch("openretop.presentation.qt.main_window.QFileDialog.getOpenFileName", return_value=(str(path), "")):
                    self.assertTrue(window.open_project())
            finally:
                window.close()

    def test_preferences_apply_shortcuts_without_dirtying_project(self) -> None:
        composition = _composition()
        candidate = copy.deepcopy(composition.settings)
        candidate.keybinds.undo = "Ctrl+U"
        window = OpenRetopV3Window(composition)
        try:
            with patch("openretop.presentation.qt.main_window.PreferencesDialog") as dialog_type:
                dialog = dialog_type.return_value
                dialog.exec.return_value = True
                dialog.settings = candidate
                self.assertTrue(window.show_preferences())
            self.assertEqual(
                window._framework_actions.require("edit.undo").shortcut,
                "Ctrl+U",
            )
            self.assertFalse(window.project_dirty)
        finally:
            window.close()

    def test_viewport_pointer_routes_the_region_tool(self) -> None:
        composition = _composition()
        composition.state.mesh_object = _mesh_object()
        window = OpenRetopV3Window(composition)
        try:
            self.assertTrue(window._dispatch_application_action("region.start"))
            pick = MeshPickResult(
                True,
                position=np.asarray([0.2, 0.2, 0.0]),
                normal=np.asarray([0.0, 0.0, 1.0]),
                triangle_index=0,
                mesh_id="mesh",
            )
            window._on_viewport_pointer("left_press", 10, 10, pick)
            window._on_viewport_pointer("left_release", 10, 10, pick)
            self.assertIsNotNone(composition.state.region_collection.active_region)
        finally:
            window.set_project_dirty(False)
            window.close()

    def test_viewport_focus_routes_tool_escape_to_the_window(self) -> None:
        composition = _composition()
        composition.state.mesh_object = _mesh_object()
        window = OpenRetopV3Window(composition)
        try:
            self.assertTrue(window._dispatch_application_action("region.start"))
            QTest.keyClick(window.viewport.interactor, Qt.Key_Escape)
            self.app.processEvents()
            self.assertFalse(composition.region_controller.session.active)
        finally:
            window.set_project_dirty(False)
            window.close()

    def test_project_open_restores_sketch_curves_region_and_selection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "complete.openretop"
            composition = _composition()
            curve = composition.state.model.sketch.add_polyline_curve(
                np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float), closed=True, name="Curve A"
            )
            composition.state.region_collection.active_region = RegionSelection(
                id="region-a",
                name="Region A",
                triangle_indices=(0,),
                selected=True,
            )
            composition.selection_controller.select_region("region-a")
            window = OpenRetopV3Window(composition)
            try:
                window.current_project_path = path
                self.assertTrue(window.save_project())
                composition.state.model.sketch.curves.clear()
                composition.state.region_collection.clear()

                self.assertTrue(window.open_project_path(path))
                curves = composition.state.model.sketch.curves
                self.assertEqual([item.name for item in curves], ["Curve A"])
                self.assertTrue(curves[0].closed)
                self.assertEqual(curves[0].id, curve.id)
                self.assertEqual(composition.state.region_collection.active_region.id, "region-a")
                self.assertEqual(composition.selection_controller.snapshot().ids, (region_node_id("region-a"),))
                self.assertIn(f"sketch:{curve.id}", window._scene_model.nodes)
            finally:
                window.set_project_dirty(False)
                window.close()

    def test_older_projects_bring_their_curves_into_the_3d_sketch(self) -> None:
        """Curves saved by the retired curve tools open as Surface Sketch curves; their old
        preview surfaces cannot be rebuilt and are reported instead of silently lost."""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "older.openretop"
            window = OpenRetopV3Window(_composition())
            try:
                window.current_project_path = path
                self.assertTrue(window.save_project())
                project = load_project(path)
                points = [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [2.0, 1.0, 0.0]]
                project.curves = [
                    ProjectCurve("c1", "Old Curve", "", "", points, points, 0.0, 0.0, False, True),
                    ProjectCurve("c2", "Empty", "", "", [], [], 0.0, 0.0, False, True),
                ]
                project.surfaces = [ProjectSurface("s1", "Old Fill", ["c1"], "preview_fill", True, {})]
                save_project(project, path)

                self.assertTrue(window.open_project_path(path))
                curves = window.composition.state.model.sketch.curves
                self.assertEqual([item.name for item in curves], ["Old Curve"])
                np.testing.assert_allclose(curves[0].polyline[[0, -1]], [points[0], points[-1]], atol=1e-9)
                self.assertTrue(any("older surface tools" in text for text in window._last_project_warnings))
            finally:
                window.set_project_dirty(False)
                window.close()

if __name__ == "__main__":
    unittest.main()
