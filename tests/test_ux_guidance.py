"""UX-01 / UX-03 / UX-11: Model & Next steps panel and drag-and-drop."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import trimesh
from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication

from openretop.application.guidance import Stage, build_guidance
from openretop.application.state import AppState, MeshObjectState
from openretop.bootstrap import create_application
from openretop.infrastructure.settings_repository import InMemorySettingsRepository
from openretop.mesh.triangle_mesh import TriangleMeshData
from openretop.presentation.qt.main_window import OpenRetopV3Window
from openretop.project.project_data import default_project_data


def _state_with_mesh() -> AppState:
    mesh = TriangleMeshData(
        np.array([[0.0, 0, 0], [10, 0, 0], [0, 20, 0], [0, 0, 30]]), np.array([[0, 1, 2], [0, 1, 3]])
    )
    state = AppState()
    state.units = "in"
    state.mesh_object = MeshObjectState(
        source_mesh=mesh,
        display_mesh=mesh,
        file_path=None,
        name="part.stl",
        origin=np.zeros(3),
        location=np.zeros(3),
        rotation=np.zeros(3),
        source_triangle_count=2,
        source_bounds_min=np.zeros(3),
        source_bounds_max=np.array([10.0, 20.0, 30.0]),
    )
    return state


class GuidanceLogicTests(unittest.TestCase):
    def test_no_scan_means_open_a_scan(self) -> None:
        guidance = build_guidance(AppState(), cad_available=True, has_runtime_brep=False)
        self.assertEqual(guidance.stage, Stage.START)
        self.assertEqual([step.action_id for step in guidance.steps if step.primary], ["file.open_model"])

    def test_scan_without_sections_suggests_computing_one(self) -> None:
        guidance = build_guidance(_state_with_mesh(), cad_available=True, has_runtime_brep=False)
        self.assertEqual(guidance.stage, Stage.SCAN)
        self.assertEqual([step.action_id for step in guidance.steps if step.primary], ["section.compute"])
        self.assertIn("Size: 10 x 20 x 30 in", guidance.summary)
        self.assertIn("2 triangles, units: in", guidance.summary)

    def test_missing_cad_kernel_is_called_out(self) -> None:
        guidance = build_guidance(_state_with_mesh(), cad_available=False, has_runtime_brep=False)
        self.assertIn("CadQuery", guidance.cad_note)

    def test_assumed_units_are_flagged(self) -> None:
        state = _state_with_mesh()
        state.units_assumed = True
        self.assertIn("(assumed)", build_guidance(state, cad_available=True, has_runtime_brep=False).summary[1])


class PanelAndDropTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _window(self) -> OpenRetopV3Window:
        window = OpenRetopV3Window(create_application(settings_repository=InMemorySettingsRepository()))
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        return window

    def _stl(self, directory: str, name: str = "ball.stl") -> Path:
        path = Path(directory) / name
        trimesh.creation.icosphere(subdivisions=3, radius=10).export(path)
        return path

    def test_empty_window_offers_open_a_scan(self) -> None:
        window = self._window()
        window.refresh()
        self.assertFalse(window.next_steps.isHidden())
        self.assertTrue(window.inspector.isHidden())
        self.assertEqual(window.next_steps.guidance.title, "Start with a scan")
        button = window.next_steps.step_buttons["file.open_model"]
        self.assertTrue(button.isEnabled())
        self.assertTrue(button.property("primary"))

    def test_after_loading_the_panel_moves_on_to_sections_and_buttons_run_actions(self) -> None:
        window = self._window()
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue(window.open_model_path(self._stl(directory), units="mm"))
        buttons = window.next_steps.step_buttons
        self.assertIn("section.compute", buttons)
        self.assertTrue(buttons["section.compute"].isEnabled())
        buttons["section.compute"].click()
        # sections now exist, so the advice advances to building a surface
        self.assertTrue(window.composition.state.curve_collection.curves)
        self.assertIn("surface.editable_brep_loft", window.next_steps.step_buttons)
        self.assertFalse(window.next_steps.step_buttons["surface.editable_brep_loft"].isEnabled())
        self.assertIn("needs", window.next_steps.step_buttons["surface.editable_brep_loft"].toolTip().lower())

    def test_selecting_something_swaps_in_the_inspector(self) -> None:
        window = self._window()
        with tempfile.TemporaryDirectory() as directory:
            window.open_model_path(self._stl(directory), units="mm")
        window.scene_tree.selection_changed.emit(("mesh",))
        window._scene_model.selected_ids = ("mesh",)
        window._refresh_next_steps()
        self.assertTrue(window.next_steps.isHidden())
        self.assertFalse(window.inspector.isHidden())

    def test_dropping_a_mesh_opens_it_and_other_files_are_rejected(self) -> None:
        window = self._window()
        window._ask_units = lambda *args, **kwargs: "cm"  # type: ignore[method-assign]
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue(window.open_dropped_file(self._stl(directory)))
            self.assertEqual(window.composition.state.units, "cm")
            junk = Path(directory) / "notes.txt"
            junk.write_text("x")
            self.assertFalse(window.open_dropped_file(junk))
            self.assertIn("supported files", window.statusBar().currentMessage())

    def test_real_drag_events_are_accepted_for_files_only(self) -> None:
        window = self._window()
        self.assertTrue(window.acceptDrops())
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(Path(tempfile.gettempdir()) / "a.stl"))])
        enter = QDragEnterEvent(QPoint(5, 5), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        window.dragEnterEvent(enter)
        self.assertTrue(enter.isAccepted())
        text_only = QMimeData()
        text_only.setText("hello")
        enter2 = QDragEnterEvent(QPoint(5, 5), Qt.CopyAction, text_only, Qt.LeftButton, Qt.NoModifier)
        window.dragEnterEvent(enter2)
        self.assertFalse(enter2.isAccepted())

    def test_dropping_a_project_opens_it(self) -> None:
        window = self._window()
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "p.openretop"
            window.composition.project_files.save_project(default_project_data(), project)
            drop_mime = QMimeData()
            drop_mime.setUrls([QUrl.fromLocalFile(str(project))])
            event = QDropEvent(QPoint(5, 5), Qt.CopyAction, drop_mime, Qt.LeftButton, Qt.NoModifier)
            window.dropEvent(event)
            self.assertEqual(window.current_project_path, project)


if __name__ == "__main__":
    unittest.main()
