from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from application.undo import CallbackUndoCommand, UndoStack


class UndoStackTests(unittest.TestCase):
    def test_empty_undo_and_redo_do_not_crash(self) -> None:
        stack = UndoStack()

        self.assertIsNone(stack.undo())
        self.assertIsNone(stack.redo())
        self.assertFalse(stack.can_undo)
        self.assertFalse(stack.can_redo)

    def test_undo_and_redo_run_command_callbacks(self) -> None:
        events: list[str] = []
        stack = UndoStack()
        stack.push(
            CallbackUndoCommand(
                "Rename Curve",
                undo_action=lambda: events.append("undo"),
                redo_action=lambda: events.append("redo"),
            )
        )

        undone = stack.undo()
        redone = stack.redo()

        self.assertEqual(events, ["undo", "redo"])
        self.assertIsNotNone(undone)
        self.assertIsNotNone(redone)
        assert undone is not None
        assert redone is not None
        self.assertEqual(undone.name, "Rename Curve")
        self.assertEqual(redone.name, "Rename Curve")

    def test_push_clears_redo_stack(self) -> None:
        events: list[str] = []
        stack = UndoStack()
        stack.push(
            CallbackUndoCommand(
                "First",
                undo_action=lambda: events.append("undo-first"),
                redo_action=lambda: events.append("redo-first"),
            )
        )
        stack.undo()

        stack.push(
            CallbackUndoCommand(
                "Second",
                undo_action=lambda: events.append("undo-second"),
                redo_action=lambda: events.append("redo-second"),
            )
        )

        self.assertFalse(stack.can_redo)
        self.assertIsNone(stack.redo())
        self.assertEqual(events, ["undo-first"])

    def test_clear_removes_undo_and_redo_commands(self) -> None:
        stack = UndoStack()
        stack.push(
            CallbackUndoCommand(
                "Rename Curve",
                undo_action=lambda: None,
                redo_action=lambda: None,
            )
        )
        stack.undo()

        stack.clear()

        self.assertFalse(stack.can_undo)
        self.assertFalse(stack.can_redo)
        self.assertIsNone(stack.undo_name)
        self.assertIsNone(stack.redo_name)


if __name__ == "__main__":
    unittest.main()
