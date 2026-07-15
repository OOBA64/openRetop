"""Incrementally synchronize scene render items with presentation actors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from viewer.actor_cache import ActorCache, ActorCacheEntry
from viewer.scene_types import SceneSnapshot


class ActorAdapter(Protocol):
    def create_actor(self, category: str, item: object) -> object: ...
    def update_geometry(self, actor: object, category: str, item: object) -> None: ...
    def update_style(self, actor: object, category: str, item: object) -> None: ...
    def update_transform(self, actor: object, category: str, item: object) -> None: ...
    def set_visibility(self, actor: object, visible: bool) -> None: ...
    def remove_actor(self, actor: object) -> None: ...


@dataclass(frozen=True, slots=True)
class ActorUpdateDiagnostics:
    created: int = 0
    geometry_updated: int = 0
    style_updated: int = 0
    transform_updated: int = 0
    visibility_updated: int = 0
    removed: int = 0
    reused: int = 0

    @property
    def changed(self) -> int:
        return (
            self.created
            + self.geometry_updated
            + self.style_updated
            + self.transform_updated
            + self.visibility_updated
            + self.removed
        )


class SceneSynchronizer:
    """Generic stable-ID/revision synchronizer, directly headless-testable."""

    def __init__(self, adapter: ActorAdapter, cache: ActorCache | None = None) -> None:
        self.adapter = adapter
        self.cache = cache or ActorCache()
        self.last_snapshot: SceneSnapshot | None = None
        self.last_diagnostics = ActorUpdateDiagnostics()

    def synchronize(self, snapshot: SceneSnapshot) -> ActorUpdateDiagnostics:
        counts = {
            "created": 0,
            "geometry_updated": 0,
            "style_updated": 0,
            "transform_updated": 0,
            "visibility_updated": 0,
            "removed": 0,
            "reused": 0,
        }
        desired: set[tuple[str, str]] = set()
        for category, item in _snapshot_items(snapshot):
            item_id = str(getattr(item, "id"))
            key = (category, item_id)
            desired.add(key)
            geometry_revision = getattr(item, "revision", 0)
            style_revision = (
                getattr(item, "style", None),
                bool(getattr(item, "selected", False)),
                bool(getattr(item, "active", False)),
                getattr(item, "category", None),
            )
            visible = bool(getattr(item, "visible", True))
            transform_revision = _transform_revision(item)
            entry = self.cache.get(category, item_id)
            if entry is None:
                actor = self.adapter.create_actor(category, item)
                self.adapter.update_style(actor, category, item)
                self.adapter.set_visibility(actor, visible)
                self.cache.put(
                    category,
                    item_id,
                    ActorCacheEntry(
                        actor,
                        geometry_revision,
                        style_revision,
                        transform_revision,
                        visible,
                    ),
                )
                counts["created"] += 1
                continue
            changed = False
            if entry.geometry_revision != geometry_revision:
                self.adapter.update_geometry(entry.actor, category, item)
                entry.geometry_revision = geometry_revision
                counts["geometry_updated"] += 1
                changed = True
            if entry.style_revision != style_revision:
                self.adapter.update_style(entry.actor, category, item)
                entry.style_revision = style_revision
                counts["style_updated"] += 1
                changed = True
            if entry.transform_revision != transform_revision:
                update_transform = getattr(self.adapter, "update_transform", None)
                if callable(update_transform):
                    update_transform(entry.actor, category, item)
                entry.transform_revision = transform_revision
                counts["transform_updated"] += 1
                changed = True
            if entry.visible != visible:
                self.adapter.set_visibility(entry.actor, visible)
                entry.visible = visible
                counts["visibility_updated"] += 1
                changed = True
            if not changed:
                counts["reused"] += 1

        for category, item_id in self.cache.keys() - desired:
            entry = self.cache.pop(category, item_id)
            if entry is not None:
                self.adapter.remove_actor(entry.actor)
                counts["removed"] += 1

        self.last_snapshot = snapshot
        self.last_diagnostics = ActorUpdateDiagnostics(**counts)
        return self.last_diagnostics


def _snapshot_items(snapshot: SceneSnapshot):
    collections = (
        ("mesh", snapshot.meshes),
        ("curve", snapshot.curves),
        ("surface", snapshot.surfaces),
        ("region", snapshot.regions),
        ("section_plane", snapshot.section_planes),
        ("section_result", snapshot.section_results),
    )
    for category, items in collections:
        for item in items:
            yield category, item


def _transform_revision(item: object) -> object:
    transform = getattr(item, "transform", None)
    if transform is None:
        return None
    try:
        import numpy as np

        values = np.asarray(transform, dtype=float).reshape((4, 4))
        return tuple(float(value) for value in values.ravel())
    except (TypeError, ValueError):
        return repr(transform)


__all__ = ("ActorAdapter", "ActorUpdateDiagnostics", "SceneSynchronizer")
