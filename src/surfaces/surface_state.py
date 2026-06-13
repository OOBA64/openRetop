"""Mutable state containers for generated surface patches."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SurfacePatch:
    id: str
    name: str
    source_curve_ids: list[str]
    surface_type: str
    visible: bool = True
    selected: bool = False
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class SurfaceCollection:
    surfaces: list[SurfacePatch] = field(default_factory=list)
    active_surface_id: str | None = None
    selected_surface_ids: set[str] = field(default_factory=set)


def add_surface(
    collection: SurfaceCollection,
    surface: SurfacePatch,
) -> SurfaceCollection:
    _require_collection(collection)
    _require_unique_surface_id(collection, surface.id)
    surface.source_curve_ids = [str(curve_id) for curve_id in surface.source_curve_ids]
    surface.visible = bool(surface.visible)
    surface.selected = bool(surface.selected)
    collection.surfaces.append(surface)
    if collection.active_surface_id is None or surface.selected:
        set_active_surface(collection, surface.id)
    else:
        _sync_selected_flags(collection)
    return collection


def remove_surface(
    collection: SurfaceCollection,
    surface_id: str,
) -> SurfaceCollection:
    _require_collection(collection)
    removed_active = collection.active_surface_id == surface_id
    collection.surfaces = [
        surface for surface in collection.surfaces if surface.id != surface_id
    ]
    collection.selected_surface_ids.discard(surface_id)
    if not removed_active:
        _sync_selected_flags(collection)
        return collection

    collection.active_surface_id = None
    if collection.surfaces:
        set_active_surface(collection, collection.surfaces[0].id)
    else:
        _sync_selected_flags(collection)
    return collection


def get_active_surface(collection: SurfaceCollection) -> SurfacePatch | None:
    _require_collection(collection)
    if collection.active_surface_id is None:
        return None
    return _find_surface(collection, collection.active_surface_id)


def set_active_surface(
    collection: SurfaceCollection,
    surface_id: str,
) -> SurfaceCollection:
    _require_collection(collection)
    surface = _find_surface(collection, surface_id)
    if surface is None:
        raise ValueError(f"Surface not found: {surface_id}")

    collection.active_surface_id = surface.id
    collection.selected_surface_ids = {surface.id}
    _sync_selected_flags(collection)
    return collection


def set_selected_surfaces(
    collection: SurfaceCollection,
    surface_ids: list[str],
    *,
    active_surface_id: str | None = None,
) -> SurfaceCollection:
    _require_collection(collection)
    requested_ids = [str(surface_id) for surface_id in surface_ids]
    surface_by_id = {surface.id: surface for surface in collection.surfaces}
    missing_ids = [
        surface_id for surface_id in requested_ids if surface_id not in surface_by_id
    ]
    if missing_ids:
        raise ValueError(f"Surface not found: {missing_ids[0]}")

    selected_ids = set(requested_ids)
    if active_surface_id is not None:
        active_surface_id = str(active_surface_id)
        if active_surface_id not in selected_ids:
            raise ValueError(f"Active surface must be selected: {active_surface_id}")
    elif requested_ids:
        active_surface_id = requested_ids[0]

    collection.selected_surface_ids = selected_ids
    collection.active_surface_id = active_surface_id
    _sync_selected_flags(collection)
    return collection


def clear_surface_selection(collection: SurfaceCollection) -> SurfaceCollection:
    _require_collection(collection)
    collection.active_surface_id = None
    collection.selected_surface_ids.clear()
    _sync_selected_flags(collection)
    return collection


def get_visible_surfaces(collection: SurfaceCollection) -> list[SurfacePatch]:
    _require_collection(collection)
    return [surface for surface in collection.surfaces if surface.visible]


def clear_surfaces_for_curve(
    collection: SurfaceCollection,
    curve_id: str,
) -> SurfaceCollection:
    _require_collection(collection)
    removed_active = any(
        surface.id == collection.active_surface_id
        for surface in collection.surfaces
        if curve_id in surface.source_curve_ids
    )
    collection.surfaces = [
        surface
        for surface in collection.surfaces
        if curve_id not in surface.source_curve_ids
    ]
    collection.selected_surface_ids = {
        surface.id for surface in collection.surfaces if surface.selected
    }
    if removed_active:
        collection.active_surface_id = None
        if collection.surfaces:
            set_active_surface(collection, collection.surfaces[0].id)
        else:
            _sync_selected_flags(collection)
    else:
        _sync_selected_flags(collection)
    return collection


def _require_collection(collection: SurfaceCollection) -> None:
    if not isinstance(collection, SurfaceCollection):
        raise ValueError("Expected SurfaceCollection.")


def _require_unique_surface_id(
    collection: SurfaceCollection,
    surface_id: str,
) -> None:
    if _find_surface(collection, surface_id) is not None:
        raise ValueError(f"Surface already exists: {surface_id}")


def _find_surface(
    collection: SurfaceCollection,
    surface_id: str,
) -> SurfacePatch | None:
    for surface in collection.surfaces:
        if surface.id == surface_id:
            return surface
    return None


def _sync_selected_flags(collection: SurfaceCollection) -> None:
    existing_ids = {surface.id for surface in collection.surfaces}
    collection.selected_surface_ids.intersection_update(existing_ids)
    if collection.active_surface_id not in existing_ids:
        collection.active_surface_id = None
    for surface in collection.surfaces:
        surface.selected = surface.id in collection.selected_surface_ids
