"""Mutable state containers for fitted curves."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class TinyCurveThresholds:
    min_point_count: int = 2
    min_length: float = 0.01
    min_bounding_box_size: float = 0.01


@dataclass(frozen=True)
class CurveDiagnostics:
    point_count: int
    length: float
    endpoint_distance: float
    bounding_box_size: float
    is_tiny_fragment: bool
    source_section_result_id: str
    source_plane_id: str


DEFAULT_TINY_CURVE_THRESHOLDS = TinyCurveThresholds()


@dataclass
class StoredCurve:
    id: str
    name: str
    section_result_id: str
    plane_id: str
    original_points: np.ndarray
    fitted_points: np.ndarray
    mean_error: float
    max_error: float
    is_closed: bool
    visible: bool = True
    selected: bool = False
    diagnostics: CurveDiagnostics | None = field(default=None, compare=False)

    @property
    def point_count(self) -> int:
        return _curve_diagnostics(self).point_count

    @property
    def length(self) -> float:
        return _curve_diagnostics(self).length

    @property
    def endpoint_distance(self) -> float:
        return _curve_diagnostics(self).endpoint_distance

    @property
    def bounding_box_size(self) -> float:
        return _curve_diagnostics(self).bounding_box_size

    @property
    def is_tiny_fragment(self) -> bool:
        return _curve_diagnostics(self).is_tiny_fragment


@dataclass
class CurveCollection:
    curves: list[StoredCurve] = field(default_factory=list)
    active_curve_id: str | None = None
    selected_curve_ids: set[str] = field(default_factory=set)


def add_curve(collection: CurveCollection, curve: StoredCurve) -> CurveCollection:
    _require_collection(collection)
    _require_unique_curve_id(collection, curve.id)
    curve.original_points = np.asarray(curve.original_points, dtype=float)
    curve.fitted_points = np.asarray(curve.fitted_points, dtype=float)
    curve.mean_error = float(curve.mean_error)
    curve.max_error = float(curve.max_error)
    curve.is_closed = bool(curve.is_closed)
    refresh_curve_diagnostics(curve)
    collection.curves.append(curve)
    if collection.active_curve_id is None or curve.selected:
        set_active_curve(collection, curve.id)
    else:
        _sync_selected_flags(collection)
    return collection


def remove_curve(collection: CurveCollection, curve_id: str) -> CurveCollection:
    _require_collection(collection)
    removed_active = collection.active_curve_id == curve_id
    collection.curves = [curve for curve in collection.curves if curve.id != curve_id]
    collection.selected_curve_ids.discard(curve_id)
    _sync_selection_after_removal(collection, removed_active=removed_active)
    return collection


def clear_curves_for_section_result(
    collection: CurveCollection,
    section_result_id: str,
) -> CurveCollection:
    _require_collection(collection)
    removed_active = any(
        curve.id == collection.active_curve_id
        for curve in collection.curves
        if curve.section_result_id == section_result_id
    )
    removed_ids = {
        curve.id
        for curve in collection.curves
        if curve.section_result_id == section_result_id
    }
    collection.curves = [
        curve
        for curve in collection.curves
        if curve.section_result_id != section_result_id
    ]
    collection.selected_curve_ids.difference_update(removed_ids)
    _sync_selection_after_removal(collection, removed_active=removed_active)
    return collection


def clear_curves_for_plane(
    collection: CurveCollection,
    plane_id: str,
) -> CurveCollection:
    _require_collection(collection)
    removed_active = any(
        curve.id == collection.active_curve_id
        for curve in collection.curves
        if curve.plane_id == plane_id
    )
    removed_ids = {
        curve.id for curve in collection.curves if curve.plane_id == plane_id
    }
    collection.curves = [
        curve for curve in collection.curves if curve.plane_id != plane_id
    ]
    collection.selected_curve_ids.difference_update(removed_ids)
    _sync_selection_after_removal(collection, removed_active=removed_active)
    return collection


def get_visible_curves(collection: CurveCollection) -> list[StoredCurve]:
    _require_collection(collection)
    return [curve for curve in collection.curves if curve.visible]


def get_selected_curves(collection: CurveCollection) -> list[StoredCurve]:
    _require_collection(collection)
    return [
        curve for curve in collection.curves if curve.id in collection.selected_curve_ids
    ]


def get_tiny_curves(collection: CurveCollection) -> list[StoredCurve]:
    _require_collection(collection)
    return [
        curve
        for curve in collection.curves
        if _curve_diagnostics(curve).is_tiny_fragment
    ]


def refresh_curve_diagnostics(
    curve: StoredCurve,
    thresholds: TinyCurveThresholds = DEFAULT_TINY_CURVE_THRESHOLDS,
) -> StoredCurve:
    curve.diagnostics = compute_curve_diagnostics(curve, thresholds)
    return curve


def compute_curve_diagnostics(
    curve: StoredCurve,
    thresholds: TinyCurveThresholds = DEFAULT_TINY_CURVE_THRESHOLDS,
) -> CurveDiagnostics:
    points = np.asarray(curve.fitted_points, dtype=float).reshape((-1, 3))
    point_count = int(len(points))
    length = _polyline_length(points)
    endpoint_distance = _endpoint_distance(points)
    bounding_box_size = _bounding_box_size(points)
    is_tiny_fragment = (
        point_count < int(thresholds.min_point_count)
        or length < float(thresholds.min_length)
        or bounding_box_size < float(thresholds.min_bounding_box_size)
    )
    return CurveDiagnostics(
        point_count=point_count,
        length=length,
        endpoint_distance=endpoint_distance,
        bounding_box_size=bounding_box_size,
        is_tiny_fragment=bool(is_tiny_fragment),
        source_section_result_id=str(curve.section_result_id),
        source_plane_id=str(curve.plane_id),
    )


def set_active_curve(
    collection: CurveCollection,
    curve_id: str,
) -> CurveCollection:
    _require_collection(collection)
    curve = _find_curve(collection, curve_id)
    if curve is None:
        raise ValueError(f"Curve not found: {curve_id}")

    collection.active_curve_id = curve.id
    collection.selected_curve_ids = {curve.id}
    _sync_selected_flags(collection)
    return collection


def set_selected_curves(
    collection: CurveCollection,
    curve_ids: Iterable[str],
    *,
    active_curve_id: str | None = None,
) -> CurveCollection:
    _require_collection(collection)
    requested_ids = [str(curve_id) for curve_id in curve_ids]
    curve_by_id = {curve.id: curve for curve in collection.curves}
    missing_ids = [
        curve_id for curve_id in requested_ids if curve_id not in curve_by_id
    ]
    if missing_ids:
        raise ValueError(f"Curve not found: {missing_ids[0]}")

    selected_ids = set(requested_ids)
    if active_curve_id is not None:
        active_curve_id = str(active_curve_id)
        if active_curve_id not in selected_ids:
            raise ValueError(f"Active curve must be selected: {active_curve_id}")
    elif requested_ids:
        active_curve_id = requested_ids[0]

    collection.selected_curve_ids = selected_ids
    collection.active_curve_id = active_curve_id
    _sync_selected_flags(collection)
    return collection


def clear_curve_selection(collection: CurveCollection) -> CurveCollection:
    _require_collection(collection)
    collection.active_curve_id = None
    collection.selected_curve_ids.clear()
    _sync_selected_flags(collection)
    return collection


def _require_collection(collection: CurveCollection) -> None:
    if not isinstance(collection, CurveCollection):
        raise ValueError("Expected CurveCollection.")


def _require_unique_curve_id(collection: CurveCollection, curve_id: str) -> None:
    if _find_curve(collection, curve_id) is not None:
        raise ValueError(f"Curve already exists: {curve_id}")


def _find_curve(
    collection: CurveCollection,
    curve_id: str,
) -> StoredCurve | None:
    for curve in collection.curves:
        if curve.id == curve_id:
            return curve
    return None


def _curve_diagnostics(curve: StoredCurve) -> CurveDiagnostics:
    if curve.diagnostics is None:
        return compute_curve_diagnostics(curve)
    return curve.diagnostics


def _polyline_length(points: np.ndarray) -> float:
    if len(points) < 2:
        return 0.0

    deltas = np.diff(points, axis=0)
    return float(np.sum(np.linalg.norm(deltas, axis=1)))


def _endpoint_distance(points: np.ndarray) -> float:
    if len(points) < 2:
        return 0.0

    return float(np.linalg.norm(points[0] - points[-1]))


def _bounding_box_size(points: np.ndarray) -> float:
    if len(points) == 0:
        return 0.0

    extents = np.ptp(points, axis=0)
    return float(np.max(extents))


def _sync_selection_after_removal(
    collection: CurveCollection,
    *,
    removed_active: bool,
) -> None:
    existing_ids = {curve.id for curve in collection.curves}
    collection.selected_curve_ids.intersection_update(existing_ids)
    if collection.active_curve_id not in existing_ids:
        removed_active = True

    if removed_active:
        collection.active_curve_id = _first_curve_id(
            collection,
            collection.selected_curve_ids,
        )
        if collection.active_curve_id is None and collection.curves:
            set_active_curve(collection, collection.curves[0].id)
            return

    _sync_selected_flags(collection)


def _first_curve_id(
    collection: CurveCollection,
    curve_ids: set[str],
) -> str | None:
    for curve in collection.curves:
        if curve.id in curve_ids:
            return curve.id
    return None


def _sync_selected_flags(collection: CurveCollection) -> None:
    existing_ids = {curve.id for curve in collection.curves}
    collection.selected_curve_ids.intersection_update(existing_ids)
    if collection.active_curve_id not in existing_ids:
        collection.active_curve_id = None
    for curve in collection.curves:
        curve.selected = curve.id in collection.selected_curve_ids
