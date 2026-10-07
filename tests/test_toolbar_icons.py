"""The main toolbar: icons, short labels, groups, and fitting a 1280 px window."""

from __future__ import annotations

import unittest

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QToolBar, QToolButton

from openretop.bootstrap import create_application
from openretop.infrastructure.settings_repository import InMemorySettingsRepository
from openretop.presentation.qt.main_window import OpenRetopV3Window
from workbench_ui.icons import ICONS, svg_markup, themed_icon


class IconSetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_every_icon_renders_something(self) -> None:
        for name in ICONS:
            with self.subTest(icon=name):
                image = themed_icon(name, "#ffffff", "#555555").pixmap(20, 20).toImage()
                painted = sum(
                    1 for x in range(image.width()) for y in range(image.height()) if image.pixelColor(x, y).alpha() > 0
                )
                self.assertGreater(painted, 15)

    def test_the_colour_placeholder_is_always_filled_in(self) -> None:
        for name in ICONS:
            self.assertNotIn("{c}", svg_markup(name, "#123456"))

    def test_disabled_icons_are_drawn_in_the_disabled_colour(self) -> None:
        icon = themed_icon("move", "#ffffff", "#404040")
        normal = icon.pixmap(20, 20, QIcon.Mode.Normal).toImage()
        disabled = icon.pixmap(20, 20, QIcon.Mode.Disabled).toImage()
        brightest = max(normal.pixelColor(x, y).lightness() for x in range(20) for y in range(20))
        dimmest = max(disabled.pixelColor(x, y).lightness() for x in range(20) for y in range(20))
        self.assertGreater(brightest, dimmest)


class MainToolbarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _window(self) -> OpenRetopV3Window:
        window = OpenRetopV3Window(create_application(settings_repository=InMemorySettingsRepository()))
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        return window

    def test_every_toolbar_button_has_an_icon_a_short_label_and_a_tooltip(self) -> None:
        window = self._window()
        toolbar = window.findChild(QToolBar, "toolbar_Main")
        actions = [action for action in toolbar.actions() if not action.isSeparator()]
        self.assertGreaterEqual(len(actions), 12)
        for action in actions:
            with self.subTest(action=action.objectName()):
                self.assertFalse(action.icon().isNull())
                self.assertTrue(action.iconText())
                self.assertLessEqual(len(action.iconText()), 15)
                self.assertTrue(action.toolTip())
        # menus keep the full label: only the toolbar uses the short one
        open_scan = window._qt_actions["file.open_model"]
        self.assertEqual(open_scan.iconText(), "Open Scan")
        self.assertNotEqual(open_scan.text(), open_scan.iconText())

    def test_groups_are_separated_and_compute_section_is_on_the_toolbar(self) -> None:
        window = self._window()
        toolbar = window.findChild(QToolBar, "toolbar_Main")
        self.assertEqual(sum(1 for action in toolbar.actions() if action.isSeparator()), 4)
        self.assertIn(window._qt_actions["section.compute"], toolbar.actions())

    def test_the_toolbar_fits_a_1280_pixel_window(self) -> None:
        from PySide6.QtGui import QGuiApplication

        window = self._window()
        window.resize(1280, 800)
        toolbar = window.findChild(QToolBar, "toolbar_Main")
        if QGuiApplication.platformName() != "offscreen":
            self.assertLessEqual(toolbar.sizeHint().width(), 1280)  # 1151 px with Segoe UI 9 pt
        else:
            # the offscreen platform has no real fonts (its fallback is twice as wide), so
            # hold the labels to the character budget that measured 1151 px on Windows
            labels = [action.iconText() for action in toolbar.actions() if not action.isSeparator()]
            self.assertLessEqual(sum(len(label) for label in labels), 115)
        buttons = toolbar.findChildren(QToolButton)
        self.assertTrue(any(button.toolButtonStyle() == button.toolButtonStyle().ToolButtonTextUnderIcon for button in buttons))


if __name__ == "__main__":
    unittest.main()
