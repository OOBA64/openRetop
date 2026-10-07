"""UI-independent application selection contracts."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


class SelectionKind(str, Enum):
    MESH = "mesh"
    SECTION_PLANE = "section_plane"
    SECTION_RESULT = "section_result"
    CURVE = "curve"
    SURFACE = "surface"
    REGION = "region"
    SCENE_NODE = "scene_node"


@dataclass(frozen=True, slots=True)
class SelectionItem:
    id: str
    kind: SelectionKind

    def __post_init__(self) -> None:
        if not str(self.id).strip():
            raise ValueError("SelectionItem.id must not be empty.")


@dataclass(frozen=True, slots=True)
class SelectionSnapshot:
    """Immutable selection value passed between application boundaries."""

    items: tuple[SelectionItem, ...] = ()
    primary_id: str | None = None

    def __post_init__(self) -> None:
        ids = tuple(item.id for item in self.items)
        if len(ids) != len(set(ids)):
            raise ValueError("SelectionSnapshot items must have unique IDs.")
        if self.primary_id is not None and self.primary_id not in ids:
            raise ValueError("SelectionSnapshot.primary_id must identify a selected item.")

    @classmethod
    def from_ids(
        cls,
        item_ids: Iterable[str],
        *,
        kind: SelectionKind = SelectionKind.SCENE_NODE,
        primary_id: str | None = None,
    ) -> SelectionSnapshot:
        ordered_ids = tuple(dict.fromkeys(str(item_id) for item_id in item_ids))
        if primary_id is None and ordered_ids:
            primary_id = ordered_ids[0]
        return cls(
            items=tuple(SelectionItem(item_id, kind) for item_id in ordered_ids),
            primary_id=primary_id,
        )

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(item.id for item in self.items)

    @property
    def has_selection(self) -> bool:
        return bool(self.items)


@runtime_checkable
class SelectionProvider(Protocol):
    """Read-only selection port required by application command composition."""

    def snapshot(self) -> SelectionSnapshot:
        """Return the current immutable selection."""


@dataclass(frozen=True, slots=True)
class CallbackSelectionProvider:
    """Adapter for an existing authoritative selection owner."""

    reader: Callable[[], SelectionSnapshot]

    def snapshot(self) -> SelectionSnapshot:
        value = self.reader()
        if not isinstance(value, SelectionSnapshot):
            raise TypeError("Selection provider callback must return SelectionSnapshot.")
        return value
