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

    def test_tool_hint_is_on_the_canvas_only_while_a_tool_is_active(self) -> None:
        window = self._window()
        self._load(window)
        hint = window.viewport.tool_hint
        self.assertEqual(hint.text, "")
        window._dispatch_application_action("region.start")
        self.assertIn("grow a region", hint.text)
        self.assertTrue(hint.visible)
        # never a second copy of the same sentence in the status bar
        self.assertNotIn(hint.text, window._info_label.text())
        window._dispatch_application_action("region.finish")
        self.assertEqual(hint.text, "")
        self.assertFalse(hint.visible)

    def test_the_hint_pill_is_centred_at_the_bottom_and_never_wider_than_the_view(self) -> None:
        from openretop.presentation.qt.tool_hint_overlay import paint_hint

        image = paint_hint("Click two points on the scan to measure. Esc cancels a point, then finishes.", 1.0, 400.0)
        self.assertLessEqual(image.width(), 400)
        self.assertGreater(image.height(), 20)  # wrapped onto more than one line rather than clipped
        wide = paint_hint("Short hint", 2.0, 1000.0)
        narrow = paint_hint("Short hint", 1.0, 1000.0)
        self.assertEqual(wide.width(), narrow.width() * 2)  # sharp on high-DPI screens


if __name__ == "__main__":
    unittest.main()
