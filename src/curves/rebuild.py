"""Curve rebuild helpers for surface-preparation workflows."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from curves.curve_state import StoredCurve, refresh_curve_diagnostics
from curves.manual_curve import (
    DEFAULT_MANUAL_CURVE_METHOD,
    DEFAULT_MANUAL_CURVE_SAMPLE_COUNT,
    build_manual_stored_curve,
    parse_manual_curve_metadata,
    sample_manual_curve,
)


@dataclass(frozen=True)
class CurveRebuildResult:
    control_points: np.ndarray
    fitted_points: np.ndarray
    source_point_count: int
    target_control_point_count: int
    method: str
    is_closed: bool
    warnings: list[str] = field(default_factory=list)


def rebuild_curve_by_arc_length(
    points: object,
    *,
    target_control_point_count: int,
    is_closed: bool,
    curve_method: str = DEFAULT_MANUAL_CURVE_METHOD,
    sample_count: int = 128,
) -> CurveRebuildResult:
    source_points = _clean_points(points, closed=bool(is_closed))
    closed = bool(is_closed)
    target_count = _clamped_target_count(target_control_point_count, closed=closed)
    method = _normalized_method(curve_method)
    samples = _normalized_sample_count(sample_count)
    warnings: list[str] = []
    if len(source_points) == 0:
        warnings.append("No source points to rebuild.")
        control_points = np.zeros((0, 3), dtype=float)
    elif len(source_points) == 1:
        warnings.append("Curve has too few points to rebuild.")
        control_points = source_points.copy()
    else:
        control_points = _resample_by_arc_length(
            source_points,
            target_count=target_count,
            closed=closed,
        )
        if len(control_points) == 0:
            warnings.append("Curve is degenerate; original points were preserved.")
            control_points = source_points.copy()

    fitted_points = sample_manual_curve(
        control_points,
        is_closed=closed,
        method=method,
        sample_count=samples,
    )
    return CurveRebuildResult(
        control_points=control_points,
        fitted_points=fitted_points,
        source_point_count=int(len(source_points)),
        target_control_point_count=int(len(control_points)),
        method=method,
        is_closed=closed,
        warnings=warnings,
    )


def rebuild_stored_curve(
    curve: StoredCurve,
    *,
    curve_id: str,
    name: str,
    target_control_point_count: int,
    curve_method: str,
    sample_count: int,
) -> StoredCurve:
    source_metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
    source_points = _source_points_for_curve(curve)
    result = rebuild_curve_by_arc_length(
        source_points,
        target_control_point_count=target_control_point_count,
        is_closed=bool(curve.is_closed),
        curve_method=curve_method,
        sample_count=sample_count,
    )
    rebuilt_curve = build_manual_stored_curve(
        curve_id=curve_id,
        name=name,
        control_points=result.control_points,
        is_closed=bool(result.is_closed),
        creation_type="rebuilt_curve",
        snap_to_mesh=bool(source_metadata.get("snap_to_mesh")),
        work_plane_type=str(source_metadata.get("work_plane_type", "manual")),
        source_mesh_name=(
            str(source_metadata.get("source_mesh_name"))
            if source_metadata.get("source_mesh_name")
            else None
        ),
        curve_method=result.method,
        sample_count=sample_count,
    )
    metadata = dict(rebuilt_curve.metadata)
    metadata.update(_preserved_source_metadata(source_metadata))
    metadata.update(
        {
            "creation_type": "rebuilt_curve",
            "source_curve_id": curve.id,
            "source_curve_name": curve.name,
            "source_curve_creation_type": str(source_metadata.get("creation_type", "")),
            "rebuild_source_point_count": int(result.source_point_count),
            "rebuild_target_control_point_count": int(result.target_control_point_count),
            "rebuild_method": result.method,
            "rebuild_warnings": list(result.warnings),
            "control_points": result.control_points.tolist(),
            "curve_method": result.method,
            "sample_count": int(sample_count),
            "closed": bool(result.is_closed),
        }
    )
    rebuilt_curve.metadata = metadata
    rebuilt_curve.original_points = result.control_points.copy()
    rebuilt_curve.fitted_points = result.fitted_points.copy()
    refresh_curve_diagnostics(rebuilt_curve)
    return rebuilt_curve


def _source_points_for_curve(curve: StoredCurve) -> np.ndarray:
    control_data = parse_manual_curve_metadata(curve)
    if control_data is not None:
        return control_data.control_points.copy()
    fitted = _safe_points(curve.fitted_points)
    if len(fitted):
        return fitted
    return _safe_points(curve.original_points)


def _resample_by_arc_length(
    points: np.ndarray,
    *,
    target_count: int,
    closed: bool,
) -> np.ndarray:
    if len(points) == 0:
        return np.zeros((0, 3), dtype=float)
    if len(points) == 1:
        return points.copy()
    if closed and len(points) < 3:
        closed = False
    path_points = np.vstack((points, points[0])) if closed else points
    segment_lengths = np.linalg.norm(np.diff(path_points, axis=0), axis=1)
    total_length = float(np.sum(segment_lengths))
    if total_length <= 1e-12 or not np.isfinite(total_length):
        return np.zeros((0, 3), dtype=float)
    cumulative = np.concatenate(([0.0], np.cumsum(segment_lengths)))
    distances = (
        np.linspace(0.0, total_length, target_count, endpoint=False)
        if closed
        else np.linspace(0.0, total_length, target_count)
    )
    segment_indices = np.searchsorted(cumulative, distances, side="right") - 1
    segment_indices = np.clip(segment_indices, 0, len(segment_lengths) - 1)
    local_lengths = segment_lengths[segment_indices].reshape((-1, 1))
    fractions = np.divide(
        (distances - cumulative[segment_indices]).reshape((-1, 1)),
        local_lengths,
        out=np.zeros((len(distances), 1), dtype=float),
        where=local_lengths > 1e-12,
    )
    lower_indices = segment_indices % len(points)
    upper_indices = (
        (segment_indices + 1) % len(points)
        if closed
        else np.minimum(segment_indices + 1, len(points) - 1)
    )
    resampled = points[lower_indices] * (1.0 - fractions) + points[upper_indices] * fractions
    if not closed and len(resampled) >= 2:
        resampled[0] = points[0]
        resampled[-1] = points[-1]
    return _safe_points(resampled)


def _clean_points(points: object, *, closed: bool) -> np.ndarray:
    safe_points = _safe_points(points)
    if len(safe_points) <= 1:
        return safe_points
    cleaned = [safe_points[0]]
    for point in safe_points[1:]:
        if np.linalg.norm(point - cleaned[-1]) > 1e-12:
            cleaned.append(point)
    if closed and len(cleaned) > 1 and np.linalg.norm(cleaned[0] - cleaned[-1]) <= 1e-12:
        cleaned.pop()
    return np.asarray(cleaned, dtype=float).reshape((-1, 3))


def _preserved_source_metadata(metadata: dict[str, object]) -> dict[str, object]:
    preserved: dict[str, object] = {}
    for key in (
        "source_mesh_name",
        "source_region_id",
        "source_region_name",
        "source_region_triangle_count",
        "region_triangle_count",
        "projection_projected_count",
        "projection_missed_count",
        "projection_mean_distance",
        "projection_max_distance",
        "projection_warnings",
    ):
        if key in metadata:
            preserved[key] = metadata[key]
    return preserved


def _clamped_target_count(value: int, *, closed: bool) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = 16
    return min(max(count, 3 if closed else 2), 256)


def _normalized_method(method: object) -> str:
    return "polyline" if str(method).strip().lower() == "polyline" else DEFAULT_MANUAL_CURVE_METHOD


def _normalized_sample_count(value: object) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = DEFAULT_MANUAL_CURVE_SAMPLE_COUNT
    return max(count, 2)


def _safe_points(points: object) -> np.ndarray:
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
    return values[np.all(np.isfinite(values), axis=1)].astype(float, copy=True)
