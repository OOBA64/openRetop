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


@dataclass
class SectionCollection:
    planes: list[SectionPlaneState] = field(default_factory=list)
    results: list[StoredSectionResult] = field(default_factory=list)
    active_plane_id: str | None = None


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
    for candidate in collection.planes:
        candidate.selected = candidate.id == plane.id
    return collection


def remove_plane(
    collection: SectionCollection,
    plane_id: str,
) -> SectionCollection:
    _require_collection(collection)
    removed_active = collection.active_plane_id == plane_id
    collection.planes = [plane for plane in collection.planes if plane.id != plane_id]
    clear_results_for_plane(collection, plane_id)

    if not removed_active:
        return collection

    collection.active_plane_id = None
    if collection.planes:
        set_active_plane(collection, collection.planes[0].id)
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
    collection.results.append(result)
    return collection


def clear_results_for_plane(
    collection: SectionCollection,
    plane_id: str,
) -> SectionCollection:
    _require_collection(collection)
    collection.results = [
        result for result in collection.results if result.plane_id != plane_id
    ]
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
