"""UI-independent undo/redo primitives for application commands."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


class UndoCommand(Protocol):
    name: str

    def undo(self) -> None: ...

    def redo(self) -> None: ...


@dataclass
class CallbackUndoCommand:
    name: str
    undo_action: Callable[[], None]
    redo_action: Callable[[], None]

    def undo(self) -> None:
        self.undo_action()

    def redo(self) -> None:
        self.redo_action()


class UndoStack:
    def __init__(self) -> None:
        self._undo_commands: list[UndoCommand] = []
        self._redo_commands: list[UndoCommand] = []

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_commands)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_commands)

    @property
    def undo_name(self) -> str | None:
        return self._undo_commands[-1].name if self._undo_commands else None

    @property
    def redo_name(self) -> str | None:
        return self._redo_commands[-1].name if self._redo_commands else None

    def push(self, command: UndoCommand) -> None:
        self._undo_commands.append(command)
        self._redo_commands.clear()

    def undo(self) -> UndoCommand | None:
        if not self._undo_commands:
            return None
        command = self._undo_commands.pop()
        command.undo()
        self._redo_commands.append(command)
        return command

    def redo(self) -> UndoCommand | None:
        if not self._redo_commands:
            return None
        command = self._redo_commands.pop()
        command.redo()
        self._undo_commands.append(command)
        return command

    def clear(self) -> None:
        self._undo_commands.clear()
        self._redo_commands.clear()


__all__ = ("CallbackUndoCommand", "UndoCommand", "UndoStack")
