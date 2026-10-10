"""UX-02: the scene tree only shows groups that have content."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import trimesh
from PySide6.QtWidgets import QApplication

from openretop.bootstrap import create_application
from openretop.infrastructure.settings_repository import InMemorySettingsRepository
from openretop.presentation.qt.main_window import OpenRetopV3Window


def labels(window: OpenRetopV3Window) -> list[str]:
    return [node.label for node in window._scene_nodes()]


class SceneTreeContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _window(self) -> OpenRetopV3Window:
        window = OpenRetopV3Window(create_application(settings_repository=InMemorySettingsRepository()))
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        return window

    def test_empty_project_shows_one_hint_instead_of_empty_folders(self) -> None:
        window = self._window()
        names = labels(window)
        self.assertEqual(len(names), 2, names)
        self.assertEqual(names[0], "Untitled project")  # the root names the project; the dock says "Scene"
        self.assertIn("Open a scan", names[1])

    def test_rows_have_kind_icons_and_no_redundant_header(self) -> None:
        window = self._window()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ball.stl"
            trimesh.creation.icosphere(subdivisions=2, radius=10).export(path)
            self.assertTrue(window.open_model_path(path, units="mm"))
        tree = window.scene_tree.tree
        self.assertTrue(tree.isHeaderHidden())
        root = tree.topLevelItem(0)
        self.assertFalse(root.icon(0).isNull())
        scan_row = root.child(0)
        self.assertEqual(scan_row.text(0), "ball.stl")
        self.assertFalse(scan_row.icon(0).isNull())

    def test_the_root_row_follows_the_saved_project_name(self) -> None:
        window = self._window()
        window.current_project_path = Path("C:/work/bracket_scan.openretop")
        self.assertEqual(labels(window)[0], "bracket_scan")

    def test_groups_appear_only_when_they_hold_something(self) -> None:
        window = self._window()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ball.stl"
            trimesh.creation.icosphere(subdivisions=3, radius=10).export(path)
            self.assertTrue(window.open_model_path(path, units="mm"))

        names = labels(window)
        self.assertIn("ball.stl", names)
        self.assertNotIn("Section Planes", names)  # only once the Section tool is used
        for absent in ("Section Results", "Surface Sketch", "Model", "Regions"):
            self.assertNotIn(absent, names)

        self.assertTrue(window._dispatch_application_action("section.compute"))
        names = labels(window)
        self.assertIn("Section Planes", names)
        self.assertIn("Section Results", names)
        # the cut's one loop is a closed Surface Sketch curve; no empty Model or Regions folders
        self.assertIn("Surface Sketch", names)
        self.assertNotIn("Model", names)
        self.assertNotIn("Regions", names)
        self.assertEqual(sum(1 for name in names if name.endswith("(closed)")), 1)

    def test_reset_returns_to_the_hint(self) -> None:
        window = self._window()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ball.stl"
            trimesh.creation.icosphere(subdivisions=2, radius=10).export(path)
            window.open_model_path(path, units="mm")
        window._reset_state()
        self.assertIn("Open a scan", " ".join(labels(window)))


if __name__ == "__main__":
    unittest.main()
