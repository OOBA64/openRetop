"""UX-12: one message area, a tool-hint strip only while a tool is active, idle model info."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import trimesh
from PySide6.QtWidgets import QApplication

from openretop.bootstrap import create_application
from openretop.infrastructure.settings_repository import InMemorySettingsRepository
from openretop.presentation.qt.main_window import OpenRetopV3Window


class StatusBarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _window(self) -> OpenRetopV3Window:
        window = OpenRetopV3Window(create_application(settings_repository=InMemorySettingsRepository()))
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        return window

    def _load(self, window: OpenRetopV3Window, units: str = "mm") -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ball.stl"
            trimesh.creation.icosphere(subdivisions=3, radius=10).export(path)
            self.assertTrue(window.open_model_path(path, units=units))

    def test_message_is_shown_once_and_idle_info_is_separate(self) -> None:
        window = self._window()
        window.set_status_message("Section computed")
        self.assertEqual(window.statusBar().currentMessage(), "Section computed")
        self.assertNotEqual(window._info_label.text(), "Section computed")
        self.assertNotEqual(window._info_label.text(), window.statusBar().currentMessage())

    def test_idle_info_describes_the_model(self) -> None:
        window = self._window()
        window.refresh()
        self.assertEqual(window._info_label.text(), "No model")
        self._load(window, units="in")
        info = window._info_label.text()
        self.assertIn("ball.stl", info)
        self.assertIn("in", info)
        self.assertIn("triangles", info)
        self.assertIn("1,280", info)  # icosphere(subdivisions=3) has 1280 triangles

    def test_tool_hint_strip_is_hidden_when_idle_and_follows_the_active_tool(self) -> None:
        window = self._window()
        self._load(window)
        self.assertTrue(window.instructions.isHidden())
        window._dispatch_application_action("region.start")
        self.assertFalse(window.instructions.isHidden())
        self.assertIn("grow a region", window.instructions.label.text())
        window._dispatch_application_action("region.finish")
        self.assertTrue(window.instructions.isHidden())


if __name__ == "__main__":
    unittest.main()
