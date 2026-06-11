"""Mutable state containers for fitted curves."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


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


@dataclass
class CurveCollection:
    curves: list[StoredCurve] = field(default_factory=list)
    active_curve_id: str | None = None


def add_curve(collection: CurveCollection, curve: StoredCurve) -> CurveCollection:
    _require_collection(collection)
    _require_unique_curve_id(collection, curve.id)
    curve.original_points = np.asarray(curve.original_points, dtype=float)
    curve.fitted_points = np.asarray(curve.fitted_points, dtype=float)
    curve.mean_error = float(curve.mean_error)
    curve.max_error = float(curve.max_error)
    curve.is_closed = bool(curve.is_closed)
    collection.curves.append(curve)
    if collection.active_curve_id is None or curve.selected:
        set_active_curve(collection, curve.id)
    return collection


def remove_curve(collection: CurveCollection, curve_id: str) -> CurveCollection:
    _require_collection(collection)
    removed_active = collection.active_curve_id == curve_id
    collection.curves = [curve for curve in collection.curves if curve.id != curve_id]
    if not removed_active:
        return collection

    collection.active_curve_id = None
    if collection.curves:
        set_active_curve(collection, collection.curves[0].id)
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
    collection.curves = [
        curve
        for curve in collection.curves
        if curve.section_result_id != section_result_id
    ]
    if removed_active:
        collection.active_curve_id = None
        if collection.curves:
            set_active_curve(collection, collection.curves[0].id)
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
    collection.curves = [
        curve for curve in collection.curves if curve.plane_id != plane_id
    ]
    if removed_active:
        collection.active_curve_id = None
        if collection.curves:
            set_active_curve(collection, collection.curves[0].id)
    return collection


def get_visible_curves(collection: CurveCollection) -> list[StoredCurve]:
    _require_collection(collection)
    return [curve for curve in collection.curves if curve.visible]


def set_active_curve(
    collection: CurveCollection,
    curve_id: str,
) -> CurveCollection:
    _require_collection(collection)
    curve = _find_curve(collection, curve_id)
    if curve is None:
        raise ValueError(f"Curve not found: {curve_id}")

    collection.active_curve_id = curve.id
    for candidate in collection.curves:
        candidate.selected = candidate.id == curve.id
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
