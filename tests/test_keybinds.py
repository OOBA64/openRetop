from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.keybinds import action_for_shortcut, shortcut_from_tk_event
from settings.settings_data import default_app_settings


class KeybindTests(unittest.TestCase):
    def test_ctrl_undo_and_redo_shortcuts_resolve_to_actions(self) -> None:
        keybinds = default_app_settings().keybinds

        self.assertEqual(action_for_shortcut(keybinds, "Ctrl+Z"), "undo")
        self.assertEqual(action_for_shortcut(keybinds, "Ctrl+Y"), "redo")
        self.assertEqual(action_for_shortcut(keybinds, "Ctrl+Shift+Z"), "redo")

    def test_shortcut_from_tk_event_includes_ctrl_modifier(self) -> None:
        self.assertEqual(
            shortcut_from_tk_event(SimpleNamespace(keysym="z", state=0x0004)),
            "Ctrl+Z",
        )
        self.assertEqual(
            shortcut_from_tk_event(SimpleNamespace(keysym="Z", state=0x0005)),
            "Ctrl+Shift+Z",
        )


if __name__ == "__main__":
    unittest.main()
