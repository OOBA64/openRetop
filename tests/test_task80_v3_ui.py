from __future__ import annotations

import json
import copy
import numpy as np
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "workbench_ui"))

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from application.actions import CORE_ACTIONS  # noqa: E402
from application.scene_ids import curve_node_id, region_node_id, surface_node_id  # noqa: E402
from application.state import MeshObjectState  # noqa: E402
from bootstrap import create_application  # noqa: E402
from curves.curve_state import StoredCurve, add_curve  # noqa: E402
from infrastructure.settings_repository import InMemorySettingsRepository  # noqa: E402
from mesh.triangle_mesh import TriangleMeshData  # noqa: E402
from presentation.qt.main_window import OpenRetopV3Window  # noqa: E402
from regions.region_state import RegionSelection  # noqa: E402
from surfaces.surface_state import SurfacePatch, add_surface  # noqa: E402
from viewer.picking_service import MeshPickResult  # noqa: E402


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


class Task80V3UiTests(unittest.TestCase):
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
                with patch("presentation.qt.main_window.QFileDialog.getSaveFileName", return_value=(str(path), "")):
                    self.assertTrue(window.save_project(as_dialog=True))
                self.assertTrue(path.exists())
                self.assertIn("version", json.loads(path.read_text(encoding="utf-8")))
                with patch("presentation.qt.main_window.QFileDialog.getOpenFileName", return_value=(str(path), "")):
                    self.assertTrue(window.open_project())
            finally:
                window.close()

    def test_preferences_apply_shortcuts_without_dirtying_project(self) -> None:
        composition = _composition()
        candidate = copy.deepcopy(composition.settings)
        candidate.keybinds.undo = "Ctrl+U"
        window = OpenRetopV3Window(composition)
        try:
            with patch("presentation.qt.main_window.PreferencesDialog") as dialog_type:
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

    def test_viewport_pointer_routes_manual_curve_and_region_tools(self) -> None:
        composition = _composition()
        composition.state.mesh_object = _mesh_object()
        window = OpenRetopV3Window(composition)
        try:
            self.assertTrue(window._dispatch_application_action("manual_curve.create"))
            for index, point in enumerate(
                (np.asarray([0.0, 0.0, 0.0]), np.asarray([1.0, 0.0, 0.0]), np.asarray([0.0, 1.0, 0.0]))
            ):
                pick = MeshPickResult(
                    True,
                    position=point,
                    normal=np.asarray([0.0, 0.0, 1.0]),
                    triangle_index=0,
                    mesh_id="mesh",
                )
                window._on_viewport_pointer("left_press", index, index, pick)
                window._on_viewport_pointer("left_release", index, index, pick)
            self.assertEqual(
                len(composition.manual_curve_controller.session.control_points), 3
            )
            self.assertTrue(window._dispatch_application_action("manual_curve.finish"))

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
            self.assertTrue(window._dispatch_application_action("manual_curve.create"))
            QTest.keyClick(window.viewport.interactor, Qt.Key_Escape)
            self.app.processEvents()
            self.assertFalse(composition.manual_curve_controller.session.active)

            self.assertTrue(window._dispatch_application_action("region.start"))
            QTest.keyClick(window.viewport.interactor, Qt.Key_Escape)
            self.app.processEvents()
            self.assertFalse(composition.region_controller.session.active)
        finally:
            window.set_project_dirty(False)
            window.close()

    def test_project_open_restores_curves_surfaces_region_and_selection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "complete.openretop"
            composition = _composition()
            curve = StoredCurve(
                id="curve-a",
                name="Curve A",
                section_result_id="",
                plane_id="",
                original_points=np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float),
                fitted_points=np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float),
                mean_error=0.0,
                max_error=0.0,
                is_closed=True,
            )
            add_curve(composition.state.curve_collection, curve)
            add_surface(
                composition.state.surface_collection,
                SurfacePatch(
                    id="surface-a",
                    name="Surface A",
                    source_curve_ids=[curve.id],
                    surface_type="preview_fill",
                    metadata={"preview_mode": "closed_curve_fill"},
                ),
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
                composition.state.curve_collection.curves.clear()
                composition.state.surface_collection.surfaces.clear()
                composition.state.region_collection.clear()

                self.assertTrue(window.open_project_path(path))
                self.assertEqual(
                    [item.id for item in composition.state.curve_collection.curves],
                    ["curve-a"],
                )
                self.assertEqual(
                    [item.id for item in composition.state.surface_collection.surfaces],
                    ["surface-a"],
                )
                self.assertEqual(
                    composition.state.region_collection.active_region.id, "region-a"
                )
                self.assertEqual(
                    composition.selection_controller.snapshot().ids,
                    (region_node_id("region-a"),),
                )
                self.assertIn(curve_node_id("curve-a"), window._scene_model.nodes)
                self.assertIn(surface_node_id("surface-a"), window._scene_model.nodes)
            finally:
                window.set_project_dirty(False)
                window.close()


if __name__ == "__main__":
    unittest.main()
