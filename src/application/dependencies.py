"""Explicit dependency ports and composition container for application commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from application.events import EventPublisher
from application.selection import SelectionProvider


@runtime_checkable
class UndoEntry(Protocol):
    name: str

    def undo(self) -> None:
        """Restore the state before the command."""

    def redo(self) -> None:
        """Reapply the state after the command."""


@runtime_checkable
class UndoPort(Protocol):
    @property
    def can_undo(self) -> bool:
        """Whether an undo command is available."""

    @property
    def can_redo(self) -> bool:
        """Whether a redo command is available."""

    def undo(self) -> UndoEntry | None:
        """Run and return the available undo entry."""

    def redo(self) -> UndoEntry | None:
        """Run and return the available redo entry."""


@dataclass(frozen=True, slots=True)
class ApplicationDependencies:
    """Typed composition root for shared application-level services.

    The container has named fields only and intentionally provides no string-key
    lookup API, so it cannot become an untyped global service locator.
    """

    events: EventPublisher
    selection: SelectionProvider
    undo: UndoPort

    def __post_init__(self) -> None:
        if not isinstance(self.events, EventPublisher):
            raise TypeError("events must be an EventPublisher.")
        if not isinstance(self.selection, SelectionProvider):
            raise TypeError("selection must implement SelectionProvider.")
        if not isinstance(self.undo, UndoPort):
            raise TypeError("undo must implement UndoPort.")
