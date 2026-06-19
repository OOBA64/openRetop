"""Surface-readiness checks for curves."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from curves.curve_state import StoredCurve, refresh_curve_diagnostics
from curves.manual_curve import is_manual_curve_like, parse_manual_curve_metadata


HIGH_POINT_COUNT_WARNING = 256
POINT_TOLERANCE = 1e-8


@dataclass(frozen=True)
class CurveSurfaceReadiness:
    curve_id: str
    curve_name: str
    point_count: int
    control_point_count: int | None
    is_closed: bool
    is_manual_like: bool
    is_projected: bool
    is_region_boundary: bool
    bounding_box_size: float
    perimeter_or_length: float
    endpoint_gap: float
    planarity_error: float | None
    mesh_projection_mean_distance: float | None
    mesh_projection_max_distance: float | None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def validate_curve_for_fill(curve: StoredCurve) -> CurveSurfaceReadiness:
    readiness = _base_readiness(curve)
    warnings = list(readiness.warnings)
    errors = list(readiness.errors)
    if not readiness.is_closed:
        errors.append("Fill Closed Curve requires one closed curve.")
    if readiness.point_count < 3:
        errors.append("Fill Closed Curve requires at least 3 curve points.")
    if readiness.bounding_box_size <= POINT_TOLERANCE or readiness.perimeter_or_length <= POINT_TOLERANCE:
        errors.append("Selected curve is degenerate.")
    elif _closed_area_estimate(_clean_points(curve.fitted_points)) <= POINT_TOLERANCE:
        errors.append("Selected curve is degenerate.")
    if readiness.point_count > HIGH_POINT_COUNT_WARNING:
        warnings.append("Curve has many points; rebuild it for cleaner surface inputs.")
    if readiness.is_closed and readiness.endpoint_gap > POINT_TOLERANCE:
        warnings.append("Closed curve has a small endpoint gap.")
    return _with_messages(readiness, warnings=warnings, errors=errors)


def validate_curves_for_loft(curves: Sequence[StoredCurve]) -> list[CurveSurfaceReadiness]:
    readiness = [_base_readiness(curve) for curve in curves]
    if len(readiness) != 2:
        return [
            CurveSurfaceReadiness(
                curve_id="",
                curve_name="Loft Selection",
                point_count=0,
                control_point_count=None,
                is_closed=False,
                is_manual_like=False,
                is_projected=False,
                is_region_boundary=False,
                bounding_box_size=0.0,
                perimeter_or_length=0.0,
                endpoint_gap=0.0,
                planarity_error=None,
                mesh_projection_mean_distance=None,
                mesh_projection_max_distance=None,
                errors=["Select exactly two curves to loft."],
            )
        ]

    updated: list[CurveSurfaceReadiness] = []
    for item in readiness:
        errors = list(item.errors)
        warnings = list(item.warnings)
        if item.point_count < 2:
            errors.append("Loft Between Two Curves requires curves with at least two points.")
        if item.bounding_box_size <= POINT_TOLERANCE or item.perimeter_or_length <= POINT_TOLERANCE:
            errors.append("Selected curve is degenerate.")
        if item.point_count > HIGH_POINT_COUNT_WARNING:
            warnings.append("Curve has many points; rebuild it for cleaner surface inputs.")
        updated.append(_with_messages(item, warnings=warnings, errors=errors))

    first, second = updated
    shared_warnings: list[str] = []
    if first.is_closed != second.is_closed:
        shared_warnings.append("Loft uses one open curve and one closed curve.")
    if _count_ratio(first.point_count, second.point_count) > 3.0:
        shared_warnings.append("Loft source curves have very different point counts.")
    if _count_ratio(first.bounding_box_size, second.bounding_box_size) > 10.0:
        shared_warnings.append("Loft source curves have very different bounding boxes.")
    source_warning = _source_mismatch_warning(curves[0], curves[1])
    if source_warning:
        shared_warnings.append(source_warning)
    if shared_warnings:
        updated = [
            _with_messages(item, warnings=[*item.warnings, *shared_warnings], errors=item.errors)
            for item in updated
        ]
    return updated


def estimate_curve_planarity_error(points: object) -> float:
    safe_points = _clean_points(points)
    if len(safe_points) < 4:
        return 0.0
    centered = safe_points - np.mean(safe_points, axis=0)
    try:
        _u, _s, vh = np.linalg.svd(centered, full_matrices=False)
    except np.linalg.LinAlgError:
        return 0.0
    normal = vh[-1]
    normal_length = float(np.linalg.norm(normal))
    if normal_length <= POINT_TOLERANCE or not np.isfinite(normal_length):
        return 0.0
    normal = normal / normal_length
    distances = np.abs(centered @ normal)
    return float(np.max(distances)) if len(distances) else 0.0


def _base_readiness(curve: StoredCurve) -> CurveSurfaceReadiness:
    refresh_curve_diagnostics(curve)
    points = _clean_points(curve.fitted_points)
    metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
    control_data = parse_manual_curve_metadata(curve)
    control_point_count = None if control_data is None else int(len(control_data.control_points))
    endpoint_gap = _endpoint_gap(points)
    is_closed = bool(curve.is_closed or (len(points) >= 3 and endpoint_gap <= POINT_TOLERANCE))
    warnings: list[str] = []
    errors: list[str] = []
    if len(points) == 0:
        errors.append("Curve has no usable points.")
    return CurveSurfaceReadiness(
        curve_id=curve.id,
        curve_name=curve.name,
        point_count=int(len(points)),
        control_point_count=control_point_count,
        is_closed=is_closed,
        is_manual_like=bool(is_manual_curve_like(curve)),
        is_projected=str(metadata.get("creation_type", "")).strip().lower() == "projected_curve",
        is_region_boundary=(
            str(metadata.get("creation_type", "")).strip().lower() == "region_boundary"
            or "source_region_id" in metadata
        ),
        bounding_box_size=_bounding_box_size(points),
        perimeter_or_length=_polyline_length(points, closed=is_closed),
        endpoint_gap=endpoint_gap,
        planarity_error=estimate_curve_planarity_error(points),
        mesh_projection_mean_distance=_optional_float(metadata.get("projection_mean_distance")),
        mesh_projection_max_distance=_optional_float(metadata.get("projection_max_distance")),
        warnings=warnings,
        errors=errors,
    )


def _with_messages(
    readiness: CurveSurfaceReadiness,
    *,
    warnings: Sequence[str],
    errors: Sequence[str],
) -> CurveSurfaceReadiness:
    return CurveSurfaceReadiness(
        curve_id=readiness.curve_id,
        curve_name=readiness.curve_name,
        point_count=readiness.point_count,
        control_point_count=readiness.control_point_count,
        is_closed=readiness.is_closed,
        is_manual_like=readiness.is_manual_like,
        is_projected=readiness.is_projected,
        is_region_boundary=readiness.is_region_boundary,
        bounding_box_size=readiness.bounding_box_size,
        perimeter_or_length=readiness.perimeter_or_length,
        endpoint_gap=readiness.endpoint_gap,
        planarity_error=readiness.planarity_error,
        mesh_projection_mean_distance=readiness.mesh_projection_mean_distance,
        mesh_projection_max_distance=readiness.mesh_projection_max_distance,
        warnings=list(dict.fromkeys(str(warning) for warning in warnings if warning)),
        errors=list(dict.fromkeys(str(error) for error in errors if error)),
    )


def _source_mismatch_warning(first: StoredCurve, second: StoredCurve) -> str | None:
    first_metadata = first.metadata if isinstance(first.metadata, dict) else {}
    second_metadata = second.metadata if isinstance(second.metadata, dict) else {}
    for key, label in (
        ("source_mesh_name", "source meshes"),
        ("source_region_id", "source regions"),
    ):
        first_value = first_metadata.get(key)
        second_value = second_metadata.get(key)
        if first_value and second_value and first_value != second_value:
            return f"Loft source curves come from different {label}."
    return None


def _count_ratio(first: float, second: float) -> float:
    smaller = max(min(float(first), float(second)), POINT_TOLERANCE)
    larger = max(float(first), float(second), POINT_TOLERANCE)
    return larger / smaller


def _polyline_length(points: np.ndarray, *, closed: bool) -> float:
    if len(points) < 2:
        return 0.0
    path = np.vstack((points, points[0])) if closed and not np.allclose(points[0], points[-1]) else points
    return float(np.linalg.norm(np.diff(path, axis=0), axis=1).sum())


def _closed_area_estimate(points: np.ndarray) -> float:
    if len(points) < 3:
        return 0.0
    center = np.mean(points, axis=0)
    area_vector = np.zeros(3, dtype=float)
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        area_vector += np.cross(point - center, next_point - center)
    return float(np.linalg.norm(area_vector) * 0.5)


def _endpoint_gap(points: np.ndarray) -> float:
    if len(points) < 2:
        return 0.0
    return float(np.linalg.norm(points[0] - points[-1]))


def _bounding_box_size(points: np.ndarray) -> float:
    if len(points) == 0:
        return 0.0
    return float(np.max(np.max(points, axis=0) - np.min(points, axis=0)))


def _optional_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _clean_points(points: object) -> np.ndarray:
    try:
        values = np.asarray(points, dtype=float)
    except (TypeError, ValueError):
        return np.zeros((0, 3), dtype=float)
    if values.size == 0:
        return np.zeros((0, 3), dtype=float)
    try:
        values = values.reshape((-1, 3))
    except ValueError:
        return np.zeros((0, 3), dtype=float)
    values = values[np.all(np.isfinite(values), axis=1)]
    if len(values) <= 1:
        return values.astype(float, copy=True)
    cleaned = [values[0]]
    for point in values[1:]:
        if np.linalg.norm(point - cleaned[-1]) > POINT_TOLERANCE:
            cleaned.append(point)
    if len(cleaned) > 1 and np.linalg.norm(cleaned[0] - cleaned[-1]) <= POINT_TOLERANCE:
        cleaned.pop()
    return np.asarray(cleaned, dtype=float).reshape((-1, 3))
