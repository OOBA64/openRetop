"""Selections made outside the tree (viewport picks) must reach the inspector; UX-16 stale widgets."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import trimesh
from PySide6.QtWidgets import QApplication, QGroupBox

from openretop.application.scene_ids import section_result_node_id
from openretop.bootstrap import create_application
from openretop.infrastructure.settings_repository import InMemorySettingsRepository
from openretop.presentation.qt.main_window import OpenRetopV3Window
from openretop.viewer.picking_service import SceneObjectPickResult
from workbench_ui import FieldDefinition, PropertyInspectorModel


class SelectionSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _window_with_section(self) -> OpenRetopV3Window:
        window = OpenRetopV3Window(create_application(settings_repository=InMemorySettingsRepository()))
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ball.stl"
            trimesh.creation.icosphere(subdivisions=3, radius=10).export(path)
            window.open_model_path(path, units="mm")
        window._dispatch_application_action("section.compute")
        return window

    @staticmethod
    def _click(window: OpenRetopV3Window, pick: SceneObjectPickResult) -> None:
        window.viewport._last_pointer_release_was_click = True
        window._on_viewport_pointer("left_release", 10, 10, pick)

    def test_a_pick_made_outside_the_tree_shows_in_the_tree_and_inspector(self) -> None:
        window = self._window_with_section()
        result = window.composition.state.section_collection.results[0]
        node_id = section_result_node_id(result.id)

        self.assertTrue(window.composition.state.model.selected_curve_ids)  # the new section curves
        self._click(window, SceneObjectPickResult(hit=True, object_id=result.id, object_type="section_result"))

        self.assertEqual(window._scene_model.selected_ids, (node_id,))
        self.assertFalse(window.inspector.isHidden())
        self.assertTrue(window.next_steps.isHidden())
        labels = [field.label for field in window._inspector_fields()]
        self.assertIn("Name", labels)
        self.assertIn(result.name, [field.value for field in window._inspector_fields()])

    def test_clearing_the_selection_returns_to_next_steps(self) -> None:
        window = self._window_with_section()
        result = window.composition.state.section_collection.results[0]
        self._click(window, SceneObjectPickResult(hit=True, object_id=result.id, object_type="section_result"))
        self.assertEqual(window._scene_model.selected_ids, (section_result_node_id(result.id),))
        self._click(window, SceneObjectPickResult(hit=False))  # empty space
        self.assertTrue(window.inspector.isHidden())
        self.assertFalse(window.next_steps.isHidden())

    def test_inspector_refresh_leaves_no_stale_group_boxes(self) -> None:
        window = self._window_with_section()
        inspector = window.inspector
        inspector.set_model(
            PropertyInspectorModel(
                (
                    FieldDefinition("a", "A", "x", "readonly", read_only=True, group="General"),
                    FieldDefinition("b", "B", "y", "readonly", read_only=True, group="Diagnostics"),
                )
            )
        )
        inspector.set_model(
            PropertyInspectorModel((FieldDefinition("c", "C", "z", "readonly", read_only=True, group="General"),))
        )
        titles = [box.title() for box in inspector.findChildren(QGroupBox)]
        self.assertEqual(titles, ["General"])


if __name__ == "__main__":
    unittest.main()
