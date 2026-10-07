"""Stable-ID actor cache shared by incremental VTK scene synchronizers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ActorCacheEntry:
    actor: object
    geometry_revision: object
    style_revision: object
    transform_revision: object
    visible: bool


class ActorCache:
    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], ActorCacheEntry] = {}

    def get(self, category: str, item_id: str) -> ActorCacheEntry | None:
        return self._entries.get((str(category), str(item_id)))

    def put(self, category: str, item_id: str, entry: ActorCacheEntry) -> None:
        self._entries[(str(category), str(item_id))] = entry

    def pop(self, category: str, item_id: str) -> ActorCacheEntry | None:
        return self._entries.pop((str(category), str(item_id)), None)

    def keys(self) -> set[tuple[str, str]]:
        return set(self._entries)

    def clear(self) -> tuple[ActorCacheEntry, ...]:
        entries = tuple(self._entries.values())
        self._entries.clear()
        return entries


__all__ = ("ActorCache", "ActorCacheEntry")
