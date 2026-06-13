"""Mutable state containers for multiple section planes and results."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from geometry.sections import SectionResult, normalize_axis


@dataclass
class SectionPlaneState:
    id: str
    name: str
    axis: str
    offset: float
    visible: bool = True
    selected: bool = False


@dataclass
class StoredSectionResult:
    id: str
    name: str
    plane_id: str
    axis: str
    offset: float
    result: SectionResult
    visible: bool = True
    selected: bool = False


@dataclass
class SectionCollection:
    planes: list[SectionPlaneState] = field(default_factory=list)
    results: list[StoredSectionResult] = field(default_factory=list)
    active_plane_id: str | None = None
    active_result_id: str | None = None
    selected_plane_ids: set[str] = field(default_factory=set)
    selected_result_ids: set[str] = field(default_factory=set)


def create_default_section_plane(axis: str = "Z", offset: float = 0.0) -> SectionPlaneState:
    return SectionPlaneState(
        id=_new_id("section-plane"),
        name="Section Plane 1",
        axis=normalize_axis(axis),
        offset=float(offset),
        visible=True,
        selected=False,
    )


def add_plane(
    collection: SectionCollection,
    plane: SectionPlaneState,
) -> SectionCollection:
    _require_collection(collection)
    _require_unique_plane_id(collection, plane.id)
    plane.axis = normalize_axis(plane.axis)
    plane.offset = float(plane.offset)
    collection.planes.append(plane)
    if collection.active_plane_id is None or plane.selected:
        set_active_plane(collection, plane.id)
    else:
        _sync_plane_selection_flags(collection)
    return collection


def get_active_plane(collection: SectionCollection) -> SectionPlaneState | None:
    _require_collection(collection)
    if collection.active_plane_id is None:
        return None

    return _find_plane(collection, collection.active_plane_id)


def set_active_plane(
    collection: SectionCollection,
    plane_id: str,
) -> SectionCollection:
    _require_collection(collection)
    plane = _find_plane(collection, plane_id)
    if plane is None:
        raise ValueError(f"Section plane not found: {plane_id}")

    collection.active_plane_id = plane.id
    collection.selected_plane_ids = {plane.id}
    _sync_plane_selection_flags(collection)
    return collection


def set_selected_planes(
    collection: SectionCollection,
    plane_ids: list[str],
    *,
    active_plane_id: str | None = None,
) -> SectionCollection:
    _require_collection(collection)
    requested_ids = [str(plane_id) for plane_id in plane_ids]
    plane_by_id = {plane.id: plane for plane in collection.planes}
    missing_ids = [
        plane_id for plane_id in requested_ids if plane_id not in plane_by_id
    ]
    if missing_ids:
        raise ValueError(f"Section plane not found: {missing_ids[0]}")

    selected_ids = set(requested_ids)
    if active_plane_id is not None:
        active_plane_id = str(active_plane_id)
        if active_plane_id not in selected_ids:
            raise ValueError(f"Active section plane must be selected: {active_plane_id}")
    elif requested_ids:
        active_plane_id = requested_ids[0]

    collection.selected_plane_ids = selected_ids
    collection.active_plane_id = active_plane_id
    _sync_plane_selection_flags(collection)
    return collection


def clear_plane_selection(collection: SectionCollection) -> SectionCollection:
    _require_collection(collection)
    collection.selected_plane_ids.clear()
    _sync_plane_selection_flags(collection)
    return collection


def remove_plane(
    collection: SectionCollection,
    plane_id: str,
) -> SectionCollection:
    _require_collection(collection)
    removed_active = collection.active_plane_id == plane_id
    collection.planes = [plane for plane in collection.planes if plane.id != plane_id]
    collection.selected_plane_ids.discard(plane_id)
    clear_results_for_plane(collection, plane_id)

    if not removed_active:
        _sync_plane_selection_flags(collection)
        return collection

    collection.active_plane_id = None
    if collection.planes:
        set_active_plane(collection, collection.planes[0].id)
    else:
        _sync_plane_selection_flags(collection)
    return collection


def add_result(
    collection: SectionCollection,
    result: StoredSectionResult,
) -> SectionCollection:
    _require_collection(collection)
    if _find_plane(collection, result.plane_id) is None:
        raise ValueError(f"Section plane not found: {result.plane_id}")

    result.axis = normalize_axis(result.axis)
    result.offset = float(result.offset)
    result.visible = bool(result.visible)
    collection.results.append(result)
    if collection.active_result_id is None or result.selected:
        set_active_result(collection, result.id)
    else:
        _sync_result_selection_flags(collection)
    return collection


def get_active_result(collection: SectionCollection) -> StoredSectionResult | None:
    _require_collection(collection)
    if collection.active_result_id is None:
        return None

    return _find_result(collection, collection.active_result_id)


def set_active_result(
    collection: SectionCollection,
    result_id: str,
) -> SectionCollection:
    _require_collection(collection)
    result = _find_result(collection, result_id)
    if result is None:
        raise ValueError(f"Section result not found: {result_id}")

    collection.active_result_id = result.id
    collection.selected_result_ids = {result.id}
    _sync_result_selection_flags(collection)
    return collection


def set_selected_results(
    collection: SectionCollection,
    result_ids: list[str],
    *,
    active_result_id: str | None = None,
) -> SectionCollection:
    _require_collection(collection)
    requested_ids = [str(result_id) for result_id in result_ids]
    result_by_id = {result.id: result for result in collection.results}
    missing_ids = [
        result_id for result_id in requested_ids if result_id not in result_by_id
    ]
    if missing_ids:
        raise ValueError(f"Section result not found: {missing_ids[0]}")

    selected_ids = set(requested_ids)
    if active_result_id is not None:
        active_result_id = str(active_result_id)
        if active_result_id not in selected_ids:
            raise ValueError(f"Active section result must be selected: {active_result_id}")
    elif requested_ids:
        active_result_id = requested_ids[0]

    collection.selected_result_ids = selected_ids
    collection.active_result_id = active_result_id
    _sync_result_selection_flags(collection)
    return collection


def clear_result_selection(collection: SectionCollection) -> SectionCollection:
    _require_collection(collection)
    collection.selected_result_ids.clear()
    _sync_result_selection_flags(collection)
    return collection


def clear_results_for_plane(
    collection: SectionCollection,
    plane_id: str,
) -> SectionCollection:
    _require_collection(collection)
    removed_active = any(
        result.id == collection.active_result_id
        for result in collection.results
        if result.plane_id == plane_id
    )
    removed_ids = {
        result.id
        for result in collection.results
        if result.plane_id == plane_id
    }
    collection.results = [
        result for result in collection.results if result.plane_id != plane_id
    ]
    collection.selected_result_ids.difference_update(removed_ids)
    if removed_active:
        collection.active_result_id = None
        if collection.results:
            set_active_result(collection, collection.results[-1].id)
        else:
            _sync_result_selection_flags(collection)
    else:
        _sync_result_selection_flags(collection)
    return collection


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _require_collection(collection: SectionCollection) -> None:
    if not isinstance(collection, SectionCollection):
        raise ValueError("Expected SectionCollection.")


def _require_unique_plane_id(collection: SectionCollection, plane_id: str) -> None:
    if _find_plane(collection, plane_id) is not None:
        raise ValueError(f"Section plane already exists: {plane_id}")


def _find_plane(
    collection: SectionCollection,
    plane_id: str,
) -> SectionPlaneState | None:
    for plane in collection.planes:
        if plane.id == plane_id:
            return plane
    return None


def _find_result(
    collection: SectionCollection,
    result_id: str,
) -> StoredSectionResult | None:
    for result in collection.results:
        if result.id == result_id:
            return result
    return None


def _sync_plane_selection_flags(collection: SectionCollection) -> None:
    existing_ids = {plane.id for plane in collection.planes}
    collection.selected_plane_ids.intersection_update(existing_ids)
    if collection.active_plane_id not in existing_ids:
        collection.active_plane_id = None
    for plane in collection.planes:
        plane.selected = plane.id in collection.selected_plane_ids


def _sync_result_selection_flags(collection: SectionCollection) -> None:
    existing_ids = {result.id for result in collection.results}
    collection.selected_result_ids.intersection_update(existing_ids)
    if collection.active_result_id not in existing_ids:
        collection.active_result_id = None
    for result in collection.results:
        result.selected = result.id in collection.selected_result_ids
