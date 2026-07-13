"""Curve-to-mesh projection helpers backed by the shared mesh query service."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter

import numpy as np

from curves.curve_state import StoredCurve, refresh_curve_diagnostics
from curves.manual_curve import (
    DEFAULT_MANUAL_CURVE_METHOD,
    DEFAULT_MANUAL_CURVE_SAMPLE_COUNT,
    build_manual_stored_curve,
    parse_manual_curve_metadata,
)
from mesh.query_service import DEFAULT_MESH_QUERY_SERVICE, MeshQueryService
from mesh.spatial_index import MeshClosestPointResult
from mesh.triangle_mesh import TriangleMeshData


_DETAILED_WARNING_POINT_LIMIT = 32


@dataclass(frozen=True)
class CurveProjectionResult:
    projected_points: np.ndarray
    source_points: np.ndarray
    hit_mask: np.ndarray
    distances: np.ndarray
    triangle_indices: list[int | None]
    normals: list[list[float] | None]
    projected_count: int
    missed_count: int
    max_distance: float
    mean_distance: float
    warnings: list[str] = field(default_factory=list)
    failed_indices: list[int] = field(default_factory=list)
    build_time_seconds: float = 0.0
    query_time_seconds: float = 0.0
    backend: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


def project_curve_points_to_mesh(
    points: object,
    mesh: TriangleMeshData | None,
    *,
    max_search_distance: float | None = None,
    preserve_missed_points: bool = True,
    mesh_query_service: MeshQueryService | None = None,
    mesh_revision: object | None = None,
) -> CurveProjectionResult:
    started = perf_counter()
    source_points = _safe_points(points)
    if len(source_points) == 0:
        return _empty_projection_result(
            source_points,
            warning="No curve points to project.",
            projection_time_seconds=perf_counter() - started,
        )
    if mesh is None or mesh.is_empty():
        projected = (
            source_points.copy()
            if preserve_missed_points
            else np.zeros((len(source_points), 3), dtype=float)
        )
        return _projection_result(
            source_points,
            projected,
            np.zeros(len(source_points), dtype=bool),
            np.zeros(len(source_points), dtype=float),
            [None for _point in source_points],
            [None for _point in source_points],
            ["No mesh available for projection."],
            failed_indices=list(range(len(source_points))),
            metadata={"reason": "no_mesh"},
            projection_time_seconds=perf_counter() - started,
        )

    service = mesh_query_service or DEFAULT_MESH_QUERY_SERVICE
    try:
        query = service.query_closest_points(
            mesh,
            source_points,
            mesh_revision=mesh_revision,
            max_distance=max_search_distance,
            preserve_missed_points=preserve_missed_points,
        )
    except RuntimeError as exc:
        projected = (
            source_points.copy()
            if preserve_missed_points
            else np.zeros((len(source_points), 3), dtype=float)
        )
        return _projection_result(
            source_points,
            projected,
            np.zeros(len(source_points), dtype=bool),
            np.zeros(len(source_points), dtype=float),
            [None for _point in source_points],
            [None for _point in source_points],
            [f"Mesh query backend unavailable: {exc}"],
            failed_indices=list(range(len(source_points))),
            metadata={"reason": "backend_unavailable"},
            projection_time_seconds=perf_counter() - started,
        )

    triangle_indices = [
        int(query.triangle_indices[index]) if query.hit_mask[index] else None
        for index in range(len(source_points))
    ]
    normals = [
        [float(value) for value in query.normals[index]]
        if query.hit_mask[index]
        else None
        for index in range(len(source_points))
    ]
    failed_indices = np.flatnonzero(~query.hit_mask).astype(int).tolist()
    warnings = _query_warnings(query, max_search_distance=max_search_distance)
    metadata = {
        **query.metadata,
        "query_backend": query.backend,
        "index_build_time_seconds": query.build_time_seconds,
        "query_time_seconds": query.query_time_seconds,
        "failed_indices": failed_indices,
        "projection_time_seconds": perf_counter() - started,
    }
    return _projection_result(
        source_points,
        query.closest_points,
        query.hit_mask,
        query.distances,
        triangle_indices,
        normals,
        warnings,
        failed_indices=failed_indices,
        build_time_seconds=query.build_time_seconds,
        query_time_seconds=query.query_time_seconds,
        backend=query.backend,
        metadata=metadata,
        projection_time_seconds=metadata["projection_time_seconds"],
    )


def project_stored_curve_to_mesh(
    curve: StoredCurve,
    mesh: TriangleMeshData | None,
    *,
    curve_id: str,
    name: str,
    source_mesh_name: str,
    max_search_distance: float | None = None,
    mesh_query_service: MeshQueryService | None = None,
    mesh_revision: object | None = None,
) -> StoredCurve:
    source_points = _source_points_for_curve(curve)
    projection = project_curve_points_to_mesh(
        source_points,
        mesh,
        max_search_distance=max_search_distance,
        preserve_missed_points=True,
        mesh_query_service=mesh_query_service,
        mesh_revision=mesh_revision,
    )
    source_metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
    control_data = parse_manual_curve_metadata(curve)
    curve_method = str(
        source_metadata.get(
            "curve_method",
            DEFAULT_MANUAL_CURVE_METHOD if control_data is not None else "polyline",
        )
    )
    sample_count = int(
        source_metadata.get(
            "sample_count",
            DEFAULT_MANUAL_CURVE_SAMPLE_COUNT,
        )
    )
    projected_curve = build_manual_stored_curve(
        curve_id=curve_id,
        name=name,
        control_points=projection.projected_points,
        is_closed=bool(curve.is_closed),
        creation_type="projected_curve",
        snap_to_mesh=True,
        work_plane_type="mesh",
        source_mesh_name=source_mesh_name,
        snap_triangle_indices=projection.triangle_indices,
        snap_normals=projection.normals,
        curve_method=curve_method,
        sample_count=sample_count,
    )
    metadata = dict(projected_curve.metadata)
    metadata.update(_lineage_metadata(source_metadata))
    metadata.update(
        {
            "creation_type": "projected_curve",
            "source_curve_id": curve.id,
            "source_curve_name": curve.name,
            "source_curve_creation_type": str(source_metadata.get("creation_type", "")),
            "source_mesh_name": str(source_mesh_name),
            "projection_projected_count": int(projection.projected_count),
            "projection_missed_count": int(projection.missed_count),
            "projection_mean_distance": float(projection.mean_distance),
            "projection_max_distance": float(projection.max_distance),
            "projection_warnings": list(projection.warnings),
            "projection_failed_indices": list(projection.failed_indices),
            "projection_index_build_time_seconds": projection.build_time_seconds,
            "projection_query_time_seconds": projection.query_time_seconds,
            "projection_backend": projection.backend,
            "control_points": projection.projected_points.tolist(),
            "curve_method": curve_method,
            "sample_count": sample_count,
            "snap_to_mesh": True,
            "snap_mode": "mesh",
        }
    )
    projected_curve.metadata = metadata
    refresh_curve_diagnostics(projected_curve)
    return projected_curve


def _query_warnings(
    query: MeshClosestPointResult,
    *,
    max_search_distance: float | None,
) -> list[str]:
    if query.metadata.get("reason") == "no_valid_triangles":
        return ["Mesh has no valid projection triangles."]
    failed_indices = np.flatnonzero(~query.hit_mask).astype(int).tolist()
    if not failed_indices:
        return []

    threshold_indices = {
        int(index)
        for index in query.metadata.get("threshold_rejected_indices", [])
    }
    if len(query.source_points) > _DETAILED_WARNING_POINT_LIMIT:
        warnings: list[str] = []
        threshold_count = sum(index in threshold_indices for index in failed_indices)
        if threshold_count:
            warnings.append(
                f"{threshold_count} of {len(query.source_points)} points exceeded "
                "the projection threshold."
            )
        other_count = len(failed_indices) - threshold_count
        if other_count:
            warnings.append(
                f"{other_count} of {len(query.source_points)} points could not be projected."
            )
        return warnings

    threshold = _optional_positive_float(max_search_distance)
    warnings = []
    for index in failed_indices:
        if index in threshold_indices and threshold is not None:
            warnings.append(
                f"Point {index + 1} missed projection distance limit "
                f"({query.distances[index]:.6g} > {threshold:.6g})."
            )
        else:
            warnings.append(f"Point {index + 1} could not be projected.")
    return warnings


def _projection_result(
    source_points: np.ndarray,
    projected_points: np.ndarray,
    hit_mask: np.ndarray,
    distances: np.ndarray,
    triangle_indices: list[int | None],
    normals: list[list[float] | None],
    warnings: list[str],
    *,
    failed_indices: list[int] | None = None,
    build_time_seconds: float = 0.0,
    query_time_seconds: float = 0.0,
    backend: str = "",
    metadata: dict[str, object] | None = None,
    projection_time_seconds: float = 0.0,
) -> CurveProjectionResult:
    safe_distances = np.nan_to_num(
        np.asarray(distances, dtype=float).reshape((-1,)),
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )
    safe_hit_mask = np.asarray(hit_mask, dtype=bool).reshape((-1,))
    hit_distances = safe_distances[safe_hit_mask]
    projected_count = int(np.count_nonzero(safe_hit_mask))
    missed_count = int(len(source_points) - projected_count)
    result_metadata = dict(metadata or {})
    result_metadata.setdefault(
        "projection_time_seconds", max(float(projection_time_seconds), 0.0)
    )
    return CurveProjectionResult(
        projected_points=_safe_points(projected_points),
        source_points=source_points.copy(),
        hit_mask=safe_hit_mask,
        distances=safe_distances,
        triangle_indices=list(triangle_indices),
        normals=list(normals),
        projected_count=projected_count,
        missed_count=missed_count,
        max_distance=float(np.max(hit_distances)) if len(hit_distances) else 0.0,
        mean_distance=float(np.mean(hit_distances)) if len(hit_distances) else 0.0,
        warnings=list(warnings),
        failed_indices=list(failed_indices or []),
        build_time_seconds=max(float(build_time_seconds), 0.0),
        query_time_seconds=max(float(query_time_seconds), 0.0),
        backend=str(backend),
        metadata=result_metadata,
    )


def _empty_projection_result(
    source_points: np.ndarray,
    *,
    warning: str,
    projection_time_seconds: float = 0.0,
) -> CurveProjectionResult:
    return _projection_result(
        source_points,
        source_points.copy(),
        np.zeros(len(source_points), dtype=bool),
        np.zeros(len(source_points), dtype=float),
        [None for _point in source_points],
        [None for _point in source_points],
        [warning],
        projection_time_seconds=projection_time_seconds,
    )


def _source_points_for_curve(curve: StoredCurve) -> np.ndarray:
    control_data = parse_manual_curve_metadata(curve)
    if control_data is not None:
        return control_data.control_points.copy()
    fitted = _safe_points(curve.fitted_points)
    if len(fitted):
        return fitted
    return _safe_points(curve.original_points)


def _lineage_metadata(metadata: dict[str, object]) -> dict[str, object]:
    preserved: dict[str, object] = {}
    for key in (
        "source_region_id",
        "source_region_name",
        "source_region_triangle_count",
        "region_triangle_count",
        "boundary_point_count",
        "boundary_closed",
        "boundary_perimeter",
    ):
        if key in metadata:
            preserved[key] = metadata[key]
    return preserved


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


def _optional_positive_float(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number) or number <= 0.0:
        return None
    return number
