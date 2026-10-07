"""UX-04: Ctrl+K command palette."""

from __future__ import annotations

import unittest

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from workbench_ui import ActionDefinition, ActionRegistry, CommandPalette, CommandPaletteDialog

from openretop.bootstrap import create_application
from openretop.infrastructure.settings_repository import InMemorySettingsRepository
from openretop.presentation.qt.main_window import OpenRetopV3Window


def _registry(calls: list[str]) -> ActionRegistry:
    def make(action_id: str, label: str, description: str, enabled: bool = True, reason: str = "") -> ActionDefinition:
        return ActionDefinition(
            action_id,
            label,
            category="Create",
            description=description,
            enabled=enabled,
            disabled_reason=reason,
            dispatch=lambda _p, a=action_id: calls.append(a),
        )

    return ActionRegistry(
        [
            make("a.loft", "Loft Between Curves", "Skin a surface between two curves", False, "two curves selected"),
            make("a.section", "Compute Section", "Slice the scan with the active plane"),
            make("a.export", "Export STEP", "Write the loft to a STEP file"),
            make("a.curve", "Create Manual Curve", "Draw a curve on the scan"),
        ]
    )


class PaletteSearchTests(unittest.TestCase):
    def test_label_matches_rank_above_description_matches(self) -> None:
        palette = CommandPalette(_registry([]))
        ids = [item.id for item in palette.search("loft", include_disabled=True)]
        self.assertEqual(ids[0], "a.loft")  # label match
        self.assertIn("a.export", ids)  # only the description mentions loft
        self.assertLess(ids.index("a.loft"), ids.index("a.export"))

    def test_all_words_must_match_in_any_order(self) -> None:
        palette = CommandPalette(_registry([]))
        self.assertEqual([i.id for i in palette.search("curve manual")], ["a.curve"])
        self.assertEqual(palette.search("curve zebra"), ())

    def test_disabled_actions_only_appear_when_requested(self) -> None:
        palette = CommandPalette(_registry([]))
        self.assertNotIn("a.loft", [i.id for i in palette.search("")])
        self.assertIn("a.loft", [i.id for i in palette.search("", include_disabled=True)])


class PaletteDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_disabled_command_is_listed_greyed_with_its_reason_and_cannot_run(self) -> None:
        calls: list[str] = []
        dialog = CommandPaletteDialog(_registry(calls))
        dialog.open_palette()
        dialog.widget.search.setText("loft")
        item = dialog.widget.results.item(0)
        self.assertIn("needs two curves selected", item.text())
        self.assertFalse(item.flags() & Qt.ItemIsEnabled)
        dialog.widget._trigger(item)
        self.assertEqual(calls, [])

    def test_enter_runs_the_first_available_match_and_closes(self) -> None:
        calls: list[str] = []
        registry = _registry(calls)
        dialog = CommandPaletteDialog(registry)
        dialog.action_triggered.connect(lambda action_id: registry.invoke(action_id))
        dialog.open_palette()
        dialog.widget.search.setText("loft")  # first hit is disabled, so Enter must skip to export
        QTest.keyClick(dialog.widget.search, Qt.Key_Return)
        self.assertEqual(calls, ["a.export"])
        self.assertFalse(dialog.isVisible())

    def test_arrow_keys_skip_disabled_rows_and_escape_closes(self) -> None:
        dialog = CommandPaletteDialog(_registry([]))
        dialog.open_palette()
        results = dialog.widget.results
        first = results.currentRow()
        QTest.keyClick(dialog.widget.search, Qt.Key_Down)
        self.assertGreater(results.currentRow(), first)
        self.assertTrue(results.currentItem().flags() & Qt.ItemIsEnabled)
        QTest.keyClick(dialog, Qt.Key_Escape)
        self.assertFalse(dialog.isVisible())


class MainWindowPaletteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_ctrl_k_action_exists_in_the_view_menu_and_opens_the_palette(self) -> None:
        window = OpenRetopV3Window(create_application(settings_repository=InMemorySettingsRepository()))
        self.addCleanup(window.close)
        definition = window._framework_actions.require("view.command_palette")
        self.assertEqual(definition.shortcut, "Ctrl+K")
        view_menu = next(a.menu() for a in window.menuBar().actions() if a.text().replace("&", "") == "View")
        self.assertIn("Command Palette...", [a.text() for a in view_menu.actions()])
        self.assertTrue(window._framework_actions.invoke("view.command_palette"))
        self.assertTrue(window._palette_dialog.isVisible())
        window._palette_dialog.close()

    def test_palette_lists_disabled_commands_with_requirements_before_a_scan_is_loaded(self) -> None:
        window = OpenRetopV3Window(create_application(settings_repository=InMemorySettingsRepository()))
        self.addCleanup(window.close)
        window._palette_dialog.open_palette()
        window._palette_dialog.widget.search.setText("compute section")
        text = window._palette_dialog.widget.results.item(0).text()
        self.assertIn("Compute Section", text)
        self.assertIn("loaded scan", text)
        window._palette_dialog.close()

    def test_choosing_a_palette_command_runs_it(self) -> None:
        window = OpenRetopV3Window(create_application(settings_repository=InMemorySettingsRepository()))
        self.addCleanup(window.close)
        ran: list[str] = []
        window._framework_actions.require("view.frame_all").dispatch = lambda _p: ran.append("frame") or True
        window._run_palette_action("view.frame_all")
        QApplication.processEvents()
        self.assertEqual(ran, ["frame"])


if __name__ == "__main__":
    unittest.main()
