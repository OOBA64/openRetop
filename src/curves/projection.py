"""Curve-to-mesh projection helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from curves.curve_state import StoredCurve, refresh_curve_diagnostics
from curves.manual_curve import (
    DEFAULT_MANUAL_CURVE_METHOD,
    DEFAULT_MANUAL_CURVE_SAMPLE_COUNT,
    build_manual_stored_curve,
    parse_manual_curve_metadata,
)
from mesh.triangle_mesh import TriangleMeshData


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


def project_curve_points_to_mesh(
    points: object,
    mesh: TriangleMeshData | None,
    *,
    max_search_distance: float | None = None,
    preserve_missed_points: bool = True,
) -> CurveProjectionResult:
    source_points = _safe_points(points)
    if len(source_points) == 0:
        return _empty_projection_result(source_points, warning="No curve points to project.")
    if mesh is None or mesh.is_empty():
        projected = source_points.copy() if preserve_missed_points else np.zeros((len(source_points), 3), dtype=float)
        return _projection_result(
            source_points,
            projected,
            np.zeros(len(source_points), dtype=bool),
            np.zeros(len(source_points), dtype=float),
            [None for _point in source_points],
            [None for _point in source_points],
            ["No mesh available for projection."],
        )

    vertices = np.asarray(mesh.vertices, dtype=float).reshape((-1, 3))
    triangles = np.asarray(mesh.triangles, dtype=int).reshape((-1, 3))
    valid_triangle_mask = np.all((triangles >= 0) & (triangles < len(vertices)), axis=1)
    valid_triangle_indices = np.nonzero(valid_triangle_mask)[0]
    if len(valid_triangle_indices) == 0:
        projected = source_points.copy() if preserve_missed_points else np.zeros((len(source_points), 3), dtype=float)
        return _projection_result(
            source_points,
            projected,
            np.zeros(len(source_points), dtype=bool),
            np.zeros(len(source_points), dtype=float),
            [None for _point in source_points],
            [None for _point in source_points],
            ["Mesh has no valid projection triangles."],
        )

    triangle_points = vertices[triangles[valid_triangle_indices]]
    max_distance = _optional_positive_float(max_search_distance)
    projected_points: list[np.ndarray] = []
    hit_mask: list[bool] = []
    distances: list[float] = []
    triangle_indices: list[int | None] = []
    normals: list[list[float] | None] = []
    warnings: list[str] = []

    for point_index, source_point in enumerate(source_points):
        closest_point, source_triangle_index, distance, normal = _closest_mesh_point(
            source_point,
            triangle_points,
            valid_triangle_indices,
        )
        hit = bool(source_triangle_index is not None)
        if hit and max_distance is not None and distance > max_distance:
            hit = False
            warnings.append(
                f"Point {point_index + 1} missed projection distance limit "
                f"({distance:.6g} > {max_distance:.6g})."
            )
        elif not hit:
            warnings.append(f"Point {point_index + 1} could not be projected.")

        if hit:
            projected_points.append(closest_point)
            hit_mask.append(True)
            distances.append(float(distance))
            triangle_indices.append(source_triangle_index)
            normals.append(None if normal is None else [float(value) for value in normal])
        else:
            projected_points.append(source_point.copy() if preserve_missed_points else np.zeros(3, dtype=float))
            hit_mask.append(False)
            distances.append(0.0)
            triangle_indices.append(None)
            normals.append(None)

    return _projection_result(
        source_points,
        np.asarray(projected_points, dtype=float).reshape((-1, 3)),
        np.asarray(hit_mask, dtype=bool),
        np.asarray(distances, dtype=float),
        triangle_indices,
        normals,
        warnings,
    )


def project_stored_curve_to_mesh(
    curve: StoredCurve,
    mesh: TriangleMeshData | None,
    *,
    curve_id: str,
    name: str,
    source_mesh_name: str,
    max_search_distance: float | None = None,
) -> StoredCurve:
    source_points = _source_points_for_curve(curve)
    projection = project_curve_points_to_mesh(
        source_points,
        mesh,
        max_search_distance=max_search_distance,
        preserve_missed_points=True,
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


def _projection_result(
    source_points: np.ndarray,
    projected_points: np.ndarray,
    hit_mask: np.ndarray,
    distances: np.ndarray,
    triangle_indices: list[int | None],
    normals: list[list[float] | None],
    warnings: list[str],
) -> CurveProjectionResult:
    safe_distances = np.nan_to_num(
        np.asarray(distances, dtype=float).reshape((-1,)),
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )
    hit_distances = distances[hit_mask & np.isfinite(distances)]
    projected_count = int(np.count_nonzero(hit_mask))
    missed_count = int(len(source_points) - projected_count)
    return CurveProjectionResult(
        projected_points=_safe_points(projected_points),
        source_points=source_points.copy(),
        hit_mask=np.asarray(hit_mask, dtype=bool).reshape((-1,)),
        distances=safe_distances,
        triangle_indices=list(triangle_indices),
        normals=list(normals),
        projected_count=projected_count,
        missed_count=missed_count,
        max_distance=float(np.max(hit_distances)) if len(hit_distances) else 0.0,
        mean_distance=float(np.mean(hit_distances)) if len(hit_distances) else 0.0,
        warnings=list(warnings),
    )


def _empty_projection_result(source_points: np.ndarray, *, warning: str) -> CurveProjectionResult:
    return _projection_result(
        source_points,
        source_points.copy(),
        np.zeros(len(source_points), dtype=bool),
        np.zeros(len(source_points), dtype=float),
        [None for _point in source_points],
        [None for _point in source_points],
        [warning],
    )


def _closest_mesh_point(
    point: np.ndarray,
    triangle_points: np.ndarray,
    triangle_indices: np.ndarray,
) -> tuple[np.ndarray, int | None, float, list[float] | None]:
    best_point: np.ndarray | None = None
    best_triangle_index: int | None = None
    best_distance_squared = float("inf")
    best_normal: list[float] | None = None
    for local_index, triangle in enumerate(triangle_points):
        candidate = _closest_point_on_triangle(point, triangle[0], triangle[1], triangle[2])
        distance_squared = float(np.dot(candidate - point, candidate - point))
        if distance_squared >= best_distance_squared:
            continue
        normal = _triangle_normal(triangle[0], triangle[1], triangle[2])
        best_point = candidate
        best_triangle_index = int(triangle_indices[local_index])
        best_distance_squared = distance_squared
        best_normal = normal

    if best_point is None:
        return (point.copy(), None, 0.0, None)
    return (best_point, best_triangle_index, float(np.sqrt(best_distance_squared)), best_normal)


def _closest_point_on_triangle(
    point: np.ndarray,
    a: np.ndarray,
    b: np.ndarray,
    c: np.ndarray,
) -> np.ndarray:
    ab = b - a
    ac = c - a
    ap = point - a
    d1 = float(np.dot(ab, ap))
    d2 = float(np.dot(ac, ap))
    if d1 <= 0.0 and d2 <= 0.0:
        return a.copy()

    bp = point - b
    d3 = float(np.dot(ab, bp))
    d4 = float(np.dot(ac, bp))
    if d3 >= 0.0 and d4 <= d3:
        return b.copy()

    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        v = d1 / (d1 - d3)
        return a + v * ab

    cp = point - c
    d5 = float(np.dot(ab, cp))
    d6 = float(np.dot(ac, cp))
    if d6 >= 0.0 and d5 <= d6:
        return c.copy()

    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        w = d2 / (d2 - d6)
        return a + w * ac

    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return b + w * (c - b)

    denominator = va + vb + vc
    if abs(denominator) <= 1e-12:
        return a.copy()
    v = vb / denominator
    w = vc / denominator
    return a + ab * v + ac * w


def _triangle_normal(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> list[float] | None:
    normal = np.cross(b - a, c - a)
    length = float(np.linalg.norm(normal))
    if length <= 1e-12 or not np.isfinite(length):
        return None
    return [float(value) for value in normal / length]


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
