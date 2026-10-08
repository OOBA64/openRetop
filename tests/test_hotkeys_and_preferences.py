"""Hotkeys reach model surfaces, the tool panel never traps them, and every shortcut is editable.

Reported 2026-10-08: Delete did nothing, undo misbehaved, "all hotkeys but the view ones were
gone", and the keybinding preferences could not be seen.
"""

from __future__ import annotations

import unittest

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QToolButton

try:
    import cadquery  # noqa: F401
    import OCP  # noqa: F401

    HAVE_KERNEL = True
except ImportError:  # pragma: no cover
    HAVE_KERNEL = False

from openretop.application.keybindings import (
    SHORTCUTS_SETTING,
    shortcut_conflicts,
    shortcut_overrides,
    store_shortcut_choices,
)
from openretop.application.state import MeshObjectState
from openretop.bootstrap import create_application
from openretop.cad_kernel.worker import KernelWorker
from openretop.infrastructure.settings_repository import InMemorySettingsRepository
from openretop.mesh.triangle_mesh import TriangleMeshData
from openretop.settings.settings_data import default_app_settings


def _plate_window():
    from openretop.presentation.qt.main_window import OpenRetopV3Window

    composition = create_application(settings_repository=InMemorySettingsRepository(), kernel_worker=KernelWorker(inline=True))
    x, y = np.meshgrid(np.linspace(0, 30, 31), np.linspace(0, 20, 21), indexing="ij")
    vertices = np.c_[x.ravel(), y.ravel(), np.random.default_rng(0).normal(0, 0.01, x.size)]
    index = np.arange(31 * 21).reshape(31, 21)
    a, b, c, d = index[:-1, :-1].ravel(), index[:-1, 1:].ravel(), index[1:, :-1].ravel(), index[1:, 1:].ravel()
    mesh = TriangleMeshData(vertices=vertices, triangles=np.r_[np.c_[a, c, d], np.c_[a, d, b]])
    composition.state.mesh_object = MeshObjectState(
        source_mesh=mesh,
        display_mesh=mesh.copy(),
        file_path=None,
        name="scan",
        origin=np.zeros(3),
        location=np.zeros(3),
        rotation=np.zeros(3),
        transform_matrix=np.identity(4),
    )
    window = OpenRetopV3Window(composition)
    window.refresh()
    return window


class ShortcutSettingsTests(unittest.TestCase):
    def test_every_command_can_be_rebound_and_cleared(self) -> None:
        settings = default_app_settings()
        defaults = {"edit.undo": "Ctrl+Z", "measure.distance": "M", "view.frame_all": "Home"}
        choices = {"edit.undo": "Ctrl+U", "measure.distance": "", "view.frame_all": "Home"}
        store_shortcut_choices(settings.keybinds, settings.future, choices, defaults)
        chosen = shortcut_overrides(settings.keybinds, settings.future)
        self.assertEqual(chosen["edit.undo"], "Ctrl+U")  # one of the classic twelve: in keybinds
        self.assertEqual(settings.keybinds.undo, "Ctrl+U")
        self.assertEqual(chosen["measure.distance"], "")  # removed: stored as "" in future
        self.assertEqual(settings.future[SHORTCUTS_SETTING], {"measure.distance": ""})
        self.assertNotIn("view.frame_all", chosen)  # unchanged defaults are not stored

    def test_conflicts_are_found(self) -> None:
        self.assertEqual(shortcut_conflicts({"a": "M", "b": "m", "c": ""}), {"m": ("a", "b")})


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class HotkeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = _plate_window()
        self.addCleanup(lambda: (self.window.set_project_dirty(False), self.window.close()))
        self.modeling = self.window.composition.modeling_controller
        self.model = self.window.composition.state.model
        self.window._qt_actions["model.fit_surface"].trigger()
        self.modeling.select_at(5)
        self.window._qt_actions["model.fit_create"].trigger()
        self.window._handle_tool_key(Qt.Key.Key_Escape)
        self.assertEqual(len(self.model.entities), 1)
        self.entity = self.model.entities[0]

    def _key(self, key, modifier=Qt.KeyboardModifier.NoModifier) -> None:
        QTest.keyClick(self.window.scene_tree, key, modifier)
        self.app.processEvents()

    def test_delete_hide_show_all_and_undo_act_on_a_selected_surface(self) -> None:
        self.window.show()  # shortcuts only reach a shown, active window
        self.window.activateWindow()
        self.app.processEvents()
        self.modeling.select_entities((self.entity.id,))
        self.window.refresh()
        self.assertTrue(self.window._qt_actions["scene.delete_selected"].isEnabled())
        self._key(Qt.Key.Key_H)
        self.assertFalse(self.model.get(self.entity.id).visible)
        self._key(Qt.Key.Key_H, Qt.KeyboardModifier.AltModifier)  # show all
        self.assertTrue(self.model.get(self.entity.id).visible)
        self.modeling.select_entities((self.entity.id,))
        self.window.refresh()
        self._key(Qt.Key.Key_Delete)
        self.assertEqual(self.model.entities, [])
        self._key(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(len(self.model.entities), 1)

    def test_undoing_a_fit_brings_its_selected_area_back(self) -> None:
        self.window._qt_actions["model.fit_surface"].trigger()
        selection = self.modeling.selection()
        self.assertEqual(selection.count, 0)
        self.window._dispatch_application_action("edit.undo")
        self.assertEqual(self.model.entities, [])
        self.assertGreater(selection.count, 0)  # adjust it and fit again
        self.window._dispatch_application_action("edit.redo")
        self.assertEqual(len(self.model.entities), 1)
        self.assertEqual(selection.count, 0)

    def test_the_tool_panel_never_takes_the_keyboard(self) -> None:
        self.window._qt_actions["model.fit_surface"].trigger()
        panel = self.window.surfacing_panel
        for button in panel.findChildren(QPushButton) + panel.findChildren(QToolButton):
            self.assertEqual(button.focusPolicy(), Qt.FocusPolicy.NoFocus, button.text())
        handed_back: list[bool] = []
        panel.editing_done.connect(lambda: handed_back.append(True))
        panel.angle.lineEdit().returnPressed.emit()  # Enter in a number field
        self.assertEqual(handed_back, [True])


class PreferencesKeyboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_the_keyboard_page_lists_every_command_and_applies_changes(self) -> None:
        from openretop.presentation.qt.main_window import OpenRetopV3Window
        from openretop.presentation.qt.preferences_dialog import CommandShortcut, PreferencesDialog

        window = OpenRetopV3Window(create_application(settings_repository=InMemorySettingsRepository()))
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        defaults = window._default_shortcuts()
        commands = tuple(CommandShortcut(d.id, d.label, d.category, defaults.get(d.id, "")) for d in window._framework_actions.definitions)
        dialog = PreferencesDialog(window.composition.settings, window, commands=commands)
        self.addCleanup(dialog.close)
        self.assertEqual([dialog.tabs.tabText(index) for index in range(3)], ["General", "Colours", "Keyboard"])
        self.assertEqual(dialog.table.rowCount(), len(commands))
        self.assertGreater(dialog.table.rowCount(), 100)
        self.assertLessEqual(dialog.height(), 700)  # fits the screen; the pages scroll
        dialog.set_shortcut("measure.distance", "Ctrl+Shift+M")
        self.assertEqual(dialog.conflicts(), {})
        dialog.set_shortcut("model.fit_surface", "Ctrl+Shift+M")
        self.assertIn("ctrl+shift+m", dialog.conflicts())
        dialog.set_shortcut("model.fit_surface", "")
        settings = dialog.settings
        self.assertEqual(shortcut_overrides(settings.keybinds, settings.future)["measure.distance"], "Ctrl+Shift+M")


if __name__ == "__main__":
    unittest.main()
