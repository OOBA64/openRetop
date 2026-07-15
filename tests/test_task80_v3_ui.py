from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "workbench_ui"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from presentation.qt.main_window import OpenRetopV3Window  # noqa: E402


class Task80V3UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_v3_shell_contains_scene_viewport_inspector_palette_and_actions(self) -> None:
        window = OpenRetopV3Window()
        try:
            self.assertEqual(window.windowTitle(), "openRetop V3")
            self.assertIn("view.frame_all", {item.id for item in window._framework_actions.definitions})
            self.assertIn("scene", window._docks)
            self.assertIn("properties", window._docks)
            self.assertIn("commands", window._docks)
            self.assertTrue(window.viewport.available)
            self.assertGreaterEqual(len(window._scene_model.nodes), 1)
        finally:
            window.close()

    def test_central_actions_drive_frame_and_visibility_without_widget_handlers(self) -> None:
        window = OpenRetopV3Window()
        try:
            self.assertTrue(window._dispatch_framework_action("view.frame_all"))
            self.assertTrue(window._dispatch_application_action("scene.show_all"))
            self.assertEqual(window._camera_request.kind.value, "none")
        finally:
            window.close()

    def test_project_save_and_open_use_persistence_service(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v3.openretop"
            window = OpenRetopV3Window()
            try:
                with patch("presentation.qt.main_window.QFileDialog.getSaveFileName", return_value=(str(path), "")):
                    self.assertTrue(window.save_project(as_dialog=True))
                self.assertTrue(path.exists())
                self.assertIn("version", json.loads(path.read_text(encoding="utf-8")))
                with patch("presentation.qt.main_window.QFileDialog.getOpenFileName", return_value=(str(path), "")):
                    self.assertTrue(window.open_project())
            finally:
                window.close()


if __name__ == "__main__":
    unittest.main()
