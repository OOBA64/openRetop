from __future__ import annotations

import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from application.keybindings import action_for_shortcut, shortcut_overrides
from settings.settings_data import default_app_settings


class KeybindTests(unittest.TestCase):
    def test_ctrl_undo_and_redo_shortcuts_resolve_to_actions(self) -> None:
        keybinds = default_app_settings().keybinds

        self.assertEqual(action_for_shortcut(keybinds, "Ctrl+Z"), "edit.undo")
        self.assertEqual(action_for_shortcut(keybinds, "Ctrl+Y"), "edit.redo")
        self.assertEqual(action_for_shortcut(keybinds, "Ctrl+Shift+Z"), "edit.redo")

    def test_persisted_fields_map_to_stable_v3_actions(self) -> None:
        overrides = shortcut_overrides(default_app_settings().keybinds)
        self.assertEqual(overrides["edit.undo"], "Ctrl+Z")
        self.assertEqual(overrides["scene.delete_selected"], "Delete")
        self.assertEqual(len(overrides), 12)


if __name__ == "__main__":
    unittest.main()
