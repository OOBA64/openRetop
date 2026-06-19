"""Mutable state containers for CAD/BREP surface records."""

from __future__ import annotations

from dataclasses import dataclass, field


BREP_TYPE_PLANAR_FACE = "planar_face"
BREP_TYPE_LOFT_SURFACE = "loft_surface"
BREP_TYPE_UNKNOWN = "unknown"
BREP_TYPES = {
    BREP_TYPE_PLANAR_FACE,
    BREP_TYPE_LOFT_SURFACE,
    BREP_TYPE_UNKNOWN,
}


@dataclass
class BrepSurfaceRecord:
    id: str
    name: str
    source_curve_ids: list[str]
    brep_type: str
    backend: str
    visible: bool = True
    selected: bool = False
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class BrepSurfaceCollection:
    surfaces: list[BrepSurfaceRecord] = field(default_factory=list)
    active_surface_id: str | None = None
    selected_surface_ids: set[str] = field(default_factory=set)


def add_brep_surface(
    collection: BrepSurfaceCollection,
    surface: BrepSurfaceRecord,
) -> BrepSurfaceCollection:
    _require_collection(collection)
    _normalize_surface(surface)
    _require_unique_surface_id(collection, surface.id)
    collection.surfaces.append(surface)
    if collection.active_surface_id is None or surface.selected:
        set_active_brep_surface(collection, surface.id)
    else:
        _sync_selected_flags(collection)
    return collection


def remove_brep_surface(
    collection: BrepSurfaceCollection,
    surface_id: str,
) -> BrepSurfaceCollection:
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
        set_active_brep_surface(collection, collection.surfaces[0].id)
    else:
        _sync_selected_flags(collection)
    return collection


def get_active_brep_surface(
    collection: BrepSurfaceCollection,
) -> BrepSurfaceRecord | None:
    _require_collection(collection)
    if collection.active_surface_id is None:
        return None
    return _find_surface(collection, collection.active_surface_id)


def set_active_brep_surface(
    collection: BrepSurfaceCollection,
    surface_id: str,
) -> BrepSurfaceCollection:
    _require_collection(collection)
    surface = _find_surface(collection, surface_id)
    if surface is None:
        raise ValueError(f"BREP surface not found: {surface_id}")

    collection.active_surface_id = surface.id
    collection.selected_surface_ids = {surface.id}
    _sync_selected_flags(collection)
    return collection


def set_selected_brep_surfaces(
    collection: BrepSurfaceCollection,
    surface_ids: list[str],
    *,
    active_surface_id: str | None = None,
) -> BrepSurfaceCollection:
    _require_collection(collection)
    requested_ids = [str(surface_id) for surface_id in surface_ids]
    surface_by_id = {surface.id: surface for surface in collection.surfaces}
    missing_ids = [
        surface_id for surface_id in requested_ids if surface_id not in surface_by_id
    ]
    if missing_ids:
        raise ValueError(f"BREP surface not found: {missing_ids[0]}")

    selected_ids = set(requested_ids)
    if active_surface_id is not None:
        active_surface_id = str(active_surface_id)
        if active_surface_id not in selected_ids:
            raise ValueError(f"Active BREP surface must be selected: {active_surface_id}")
    elif requested_ids:
        active_surface_id = requested_ids[0]

    collection.selected_surface_ids = selected_ids
    collection.active_surface_id = active_surface_id
    _sync_selected_flags(collection)
    return collection


def clear_brep_surface_selection(
    collection: BrepSurfaceCollection,
) -> BrepSurfaceCollection:
    _require_collection(collection)
    collection.active_surface_id = None
    collection.selected_surface_ids.clear()
    _sync_selected_flags(collection)
    return collection


def get_visible_brep_surfaces(
    collection: BrepSurfaceCollection,
) -> list[BrepSurfaceRecord]:
    _require_collection(collection)
    return [surface for surface in collection.surfaces if surface.visible]


def _normalize_surface(surface: BrepSurfaceRecord) -> None:
    surface.id = str(surface.id)
    surface.name = str(surface.name)
    surface.source_curve_ids = [
        str(curve_id) for curve_id in surface.source_curve_ids
    ]
    surface.brep_type = _normalized_brep_type(surface.brep_type)
    surface.backend = str(surface.backend)
    surface.visible = bool(surface.visible)
    surface.selected = bool(surface.selected)
    if not isinstance(surface.metadata, dict):
        raise ValueError("brep surface metadata must be a dictionary.")
    surface.metadata = dict(surface.metadata)


def _normalized_brep_type(value: object) -> str:
    candidate = str(value).strip().lower()
    return candidate if candidate in BREP_TYPES else BREP_TYPE_UNKNOWN


def _require_collection(collection: BrepSurfaceCollection) -> None:
    if not isinstance(collection, BrepSurfaceCollection):
        raise ValueError("Expected BrepSurfaceCollection.")


def _require_unique_surface_id(
    collection: BrepSurfaceCollection,
    surface_id: str,
) -> None:
    if _find_surface(collection, surface_id) is not None:
        raise ValueError(f"BREP surface already exists: {surface_id}")


def _find_surface(
    collection: BrepSurfaceCollection,
    surface_id: str,
) -> BrepSurfaceRecord | None:
    for surface in collection.surfaces:
        if surface.id == surface_id:
            return surface
    return None


def _sync_selected_flags(collection: BrepSurfaceCollection) -> None:
    existing_ids = {surface.id for surface in collection.surfaces}
    collection.selected_surface_ids.intersection_update(existing_ids)
    if collection.active_surface_id not in existing_ids:
        collection.active_surface_id = None
    for surface in collection.surfaces:
        surface.selected = surface.id in collection.selected_surface_ids
