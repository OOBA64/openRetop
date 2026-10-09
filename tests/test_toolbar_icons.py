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


TOOLBARS = ("toolbar_Main", "toolbar_Scan", "toolbar_Surface_Modeling", "toolbar_Solid_Modeling")


class MainToolbarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _window(self, **future) -> OpenRetopV3Window:
        composition = create_application(settings_repository=InMemorySettingsRepository())
        composition.settings.future.update(future)
        window = OpenRetopV3Window(composition)
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        return window

    def test_every_toolbar_button_has_an_icon_a_short_label_and_a_tooltip(self) -> None:
        window = self._window()
        for name in TOOLBARS:
            toolbar = window.findChild(QToolBar, name)
            actions = [action for action in toolbar.actions() if not action.isSeparator()]
            self.assertGreaterEqual(len(actions), 4, name)
            for action in actions:
                with self.subTest(toolbar=name, action=action.objectName()):
                    self.assertFalse(action.icon().isNull())
                    self.assertTrue(action.iconText())
                    self.assertLessEqual(len(action.iconText()), 15)
                    self.assertTrue(action.toolTip())
        # menus keep the full label: only the toolbar uses the short one
        open_scan = window._qt_actions["file.open_model"]
        self.assertEqual(open_scan.iconText(), "Open Scan")
        self.assertNotEqual(open_scan.text(), open_scan.iconText())

    def test_groups_are_separated_and_compute_section_is_on_the_scan_toolbar(self) -> None:
        window = self._window()
        main = window.findChild(QToolBar, "toolbar_Main")
        self.assertEqual(sum(1 for action in main.actions() if action.isSeparator()), 2)  # file | history | view
        self.assertIn(window._qt_actions["section.compute"], window.findChild(QToolBar, "toolbar_Scan").actions())

    def test_each_toolbar_row_fits_a_1280_pixel_window(self) -> None:
        from PySide6.QtGui import QGuiApplication

        window = self._window()
        window.resize(1280, 800)
        tabs = window.findChild(QToolBar, "toolbar_Workspaces")
        for name in TOOLBARS:
            toolbar = window.findChild(QToolBar, name)
            labels = [action.iconText() for action in toolbar.actions() if not action.isSeparator()]
            if QGuiApplication.platformName() != "offscreen":
                extra = tabs.sizeHint().width() if name == "toolbar_Main" else 0  # the tabs share the first row
                self.assertLessEqual(toolbar.sizeHint().width() + extra, 1280, name)
            else:
                # the offscreen platform has no real fonts (its fallback is twice as wide), so
                # hold the labels to the character budget that measured 1151 px on Windows
                self.assertLessEqual(sum(len(label) for label in labels), 115 - (40 if name == "toolbar_Main" else 0), name)
            buttons = toolbar.findChildren(QToolButton)
            self.assertTrue(any(button.toolButtonStyle() == button.toolButtonStyle().ToolButtonTextUnderIcon for button in buttons))


class WorkspaceTests(unittest.TestCase):
    """Workspaces: Scan, Surface Modeling, Solid Modeling, each with its own toolbar."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _window(self, **future) -> OpenRetopV3Window:
        composition = create_application(settings_repository=InMemorySettingsRepository())
        composition.settings.future.update(future)
        window = OpenRetopV3Window(composition)
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        return window

    def visible(self, window: OpenRetopV3Window) -> list[str]:
        return [name for name in TOOLBARS[1:] if window.findChild(QToolBar, name).isVisibleTo(window)]

    def test_the_tabs_switch_the_tools(self) -> None:
        window = self._window()
        tabs = window.workspace_tabs
        self.assertEqual([tabs.tabText(index) for index in range(tabs.count())], ["Scan", "Surface", "Solid"])
        self.assertEqual(window.active_workspace, "surface")
        self.assertEqual(self.visible(window), ["toolbar_Surface_Modeling"])
        self.assertTrue(window.findChild(QToolBar, "toolbar_Main").isVisibleTo(window))  # common: always
        tabs.setCurrentIndex(0)
        self.assertEqual(window.active_workspace, "scan")
        self.assertEqual(self.visible(window), ["toolbar_Scan"])
        self.assertEqual(window.composition.settings.future["workspace"], "scan")  # remembered

    def test_a_tool_from_another_workspace_switches_to_it(self) -> None:
        window = self._window(workspace="scan")
        self.assertEqual(window.active_workspace, "scan")
        window._invoke_from_ui("model.section_sketch")  # a menu item or shortcut (no scan: it just says so)
        self.assertEqual(window.active_workspace, "solid")
        window._invoke_from_ui("model.compare")  # in Solid Modeling too: stays
        self.assertEqual(window.active_workspace, "solid")
        window._invoke_from_ui("view.frame_all")  # common: never switches
        self.assertEqual(window.active_workspace, "solid")
        window._invoke_from_ui("model.sketch")
        self.assertEqual(window.active_workspace, "surface")

    def test_an_unknown_remembered_workspace_falls_back(self) -> None:
        window = self._window(workspace="nonsense")
        self.assertEqual(window.active_workspace, "surface")


if __name__ == "__main__":
    unittest.main()
