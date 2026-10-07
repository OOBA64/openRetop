"""UX-33: section planes are drawn and listed only while the Section tool is engaged."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import trimesh
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from openretop.application.scene_ids import NODE_MESH, section_plane_node_id
from openretop.bootstrap import create_application
from openretop.infrastructure.settings_repository import InMemorySettingsRepository
from openretop.presentation.qt.main_window import OpenRetopV3Window
from openretop.viewer.picking_service import SceneObjectPickResult


def _ready(window: OpenRetopV3Window) -> None:
    with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
        window.viewport._is_ready = True
        window.viewport.ready.emit()


class SectionToolGatingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _window(self) -> OpenRetopV3Window:
        window = OpenRetopV3Window(create_application(settings_repository=InMemorySettingsRepository()))
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ball.stl"
            trimesh.creation.icosphere(subdivisions=3, radius=10).export(path)
            window.open_model_path(path, units="mm")
        _ready(window)
        window.refresh()
        return window

    def _plane_items_visible(self, window: OpenRetopV3Window) -> list[bool]:
        snapshot = window.viewport.last_snapshot
        return [bool(item.visible) for item in snapshot.section_planes]

    def _tree(self, window: OpenRetopV3Window) -> list[str]:
        return [node.label for node in window._scene_nodes()]

    def test_a_fresh_scan_shows_no_section_plane(self) -> None:
        window = self._window()
        self.assertEqual(len(window.composition.state.section_collection.planes), 1)  # kept so Compute works
        self.assertFalse(any(self._plane_items_visible(window)))
        self.assertNotIn("Section Planes", self._tree(window))
        self.assertNotIn("Section Plane 1", self._tree(window))

    def test_compute_section_works_from_a_fresh_scan_and_shows_the_plane(self) -> None:
        window = self._window()
        with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
            self.assertTrue(window._dispatch_application_action("section.compute"))
        self.assertTrue(window.composition.state.section_collection.results)
        self.assertTrue(any(self._plane_items_visible(window)))
        self.assertIn("Section Plane 1", self._tree(window))

    def test_add_section_plane_engages_the_tool(self) -> None:
        window = self._window()
        window._dispatch_application_action("section.add_plane")
        self.assertTrue(all(self._plane_items_visible(window)))
        self.assertEqual(window.tool_modes.state.id, "section")

    def test_escape_leaves_the_tool_and_hides_the_planes_but_keeps_the_section(self) -> None:
        window = self._window()
        with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
            window._dispatch_application_action("section.compute")
        self.assertTrue(window._handle_tool_key(Qt.Key_Escape))
        self.assertFalse(any(self._plane_items_visible(window)))
        self.assertTrue(window.composition.state.section_collection.results)
        self.assertFalse(window.tool_modes.active)
        self.assertFalse(window._handle_tool_key(Qt.Key_Escape))  # nothing left to leave

    def test_selecting_a_plane_engages_the_tool_and_selecting_the_model_leaves_it(self) -> None:
        window = self._window()
        window._dispatch_application_action("section.add_plane")
        window._handle_tool_key(Qt.Key_Escape)
        plane = window.composition.state.section_collection.planes[0]
        self.assertFalse(any(self._plane_items_visible(window)))
        window._on_tree_selection(type("Sel", (), {"ids": (section_plane_node_id(plane.id),)})())
        self.assertTrue(all(self._plane_items_visible(window)))
        window._on_tree_selection(type("Sel", (), {"ids": (NODE_MESH,)})())
        self.assertFalse(any(self._plane_items_visible(window)))

    def test_a_click_on_empty_space_leaves_the_tool(self) -> None:
        window = self._window()
        window._dispatch_application_action("section.add_plane")
        window.viewport._last_pointer_release_was_click = True
        window._on_viewport_pointer("left_release", 5, 5, SceneObjectPickResult(hit=False))
        self.assertFalse(any(self._plane_items_visible(window)))

    def test_starting_another_tool_leaves_the_section_tool(self) -> None:
        window = self._window()
        window._dispatch_application_action("section.add_plane")
        self.assertTrue(window._section_tool)
        window._dispatch_application_action("region.start")
        self.assertFalse(window._section_tool)

    def test_a_new_scan_starts_without_the_tool(self) -> None:
        window = self._window()
        window._dispatch_application_action("section.add_plane")
        window._reset_state()
        self.assertFalse(window._section_tool)

    def test_extra_planes_made_by_the_user_stay_listed_after_leaving_the_tool(self) -> None:
        window = self._window()
        window._dispatch_application_action("section.add_plane")
        window._handle_tool_key(Qt.Key_Escape)
        self.assertGreater(len(window.composition.state.section_collection.planes), 1)
        self.assertIn("Section Planes", self._tree(window))  # their own planes are not hidden from the tree
        self.assertFalse(any(self._plane_items_visible(window)))  # but they are not drawn outside the tool


if __name__ == "__main__":
    unittest.main()
