"""Manual control-point curve helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from curves.curve_state import StoredCurve


MANUAL_CURVE_METHOD_POLYLINE = "polyline"
MANUAL_CURVE_METHOD_CATMULL_ROM = "catmull_rom"
DEFAULT_MANUAL_CURVE_METHOD = MANUAL_CURVE_METHOD_CATMULL_ROM
DEFAULT_MANUAL_CURVE_SAMPLE_COUNT = 64
MANUAL_CURVE_CLOSE_THRESHOLD_RATIO = 0.01
MANUAL_CURVE_CLOSE_THRESHOLD_MIN = 1e-4


@dataclass(frozen=True)
class ManualCurveControlData:
    control_points: np.ndarray
    is_closed: bool
    curve_method: str = DEFAULT_MANUAL_CURVE_METHOD
    sample_count: int = DEFAULT_MANUAL_CURVE_SAMPLE_COUNT


def manual_curve_metadata(
    control_points: Sequence[Sequence[float]] | np.ndarray,
    *,
    is_closed: bool,
    creation_type: str,
    snap_to_mesh: bool,
    work_plane_type: str,
    source_section_plane_id: str | None = None,
    source_mesh_name: str | None = None,
    snap_triangle_indices: Sequence[int | None] | None = None,
    snap_normals: Sequence[Sequence[float] | None] | None = None,
    curve_method: str = DEFAULT_MANUAL_CURVE_METHOD,
    sample_count: int = DEFAULT_MANUAL_CURVE_SAMPLE_COUNT,
) -> dict[str, object]:
    points = _safe_points(control_points)
    method = _normalized_curve_method(curve_method)
    metadata: dict[str, object] = {
        "closed": bool(is_closed),
        "control_points": _json_safe_points(points),
        "curve_method": method,
        "sample_count": _normalized_sample_count(sample_count),
        "creation_type": str(creation_type),
        "snap_to_mesh": bool(snap_to_mesh),
        "work_plane_type": str(work_plane_type),
    }
    if bool(snap_to_mesh):
        metadata["snap_mode"] = "mesh"
    if source_section_plane_id is not None:
        metadata["source_section_plane_id"] = str(source_section_plane_id)
    if source_mesh_name:
        metadata["source_mesh_name"] = str(source_mesh_name)
    if snap_triangle_indices is not None:
        metadata["snap_triangle_indices"] = [
            None if index is None else int(index) for index in snap_triangle_indices
        ]
    if snap_normals is not None:
        metadata["snap_normals"] = [
            None if normal is None else _json_safe_point_or_none(normal)
            for normal in snap_normals
        ]
    return metadata


def parse_manual_curve_metadata(curve: object) -> ManualCurveControlData | None:
    metadata = getattr(curve, "metadata", {})
    if not isinstance(metadata, dict):
        return None

    control_points_value = metadata.get("control_points")
    if control_points_value is None:
        return None

    control_points = _safe_points(control_points_value)
    if len(control_points) == 0:
        return None
    sample_count = _normalized_sample_count(
        metadata.get("sample_count", DEFAULT_MANUAL_CURVE_SAMPLE_COUNT)
    )
    return ManualCurveControlData(
        control_points=control_points,
        is_closed=bool(metadata.get("closed", getattr(curve, "is_closed", False))),
        curve_method=_normalized_curve_method(
            metadata.get("curve_method", DEFAULT_MANUAL_CURVE_METHOD)
        ),
        sample_count=sample_count,
    )


def is_manual_curve_like(curve: object) -> bool:
    metadata = getattr(curve, "metadata", {})
    if not isinstance(metadata, dict):
        return False

    creation_type = str(metadata.get("creation_type", "")).strip().lower()
    return bool(
        creation_type in {"manual", "curve_on_mesh"}
        or "control_points" in metadata
        or str(metadata.get("snap_mode", "")).strip().lower() == "mesh"
        or str(metadata.get("source", "")).strip().lower() == "manual"
        or bool(metadata.get("manual"))
        or bool(metadata.get("snap_to_mesh"))
    )


def ensure_manual_curve_storage(curve: StoredCurve) -> StoredCurve:
    if not is_manual_curve_like(curve):
        return curve

    metadata = dict(curve.metadata if isinstance(curve.metadata, dict) else {})
    had_control_points = "control_points" in metadata
    control_points = _safe_points(metadata.get("control_points"))
    if len(control_points) == 0:
        control_points = _safe_points(getattr(curve, "original_points", []))
        had_control_points = False
    if len(control_points) == 0:
        control_points = _safe_points(getattr(curve, "fitted_points", []))
        had_control_points = False
    if len(control_points) == 0:
        return curve

    method = _normalized_curve_method(
        metadata.get(
            "curve_method",
            DEFAULT_MANUAL_CURVE_METHOD
            if had_control_points
            else MANUAL_CURVE_METHOD_POLYLINE,
        )
    )
    sample_count = _normalized_sample_count(
        metadata.get("sample_count", DEFAULT_MANUAL_CURVE_SAMPLE_COUNT)
    )
    is_closed = bool(metadata.get("closed", getattr(curve, "is_closed", False)))
    snap_to_mesh = bool(metadata.get("snap_to_mesh")) or str(
        metadata.get("snap_mode", "")
    ).strip().lower() == "mesh"

    metadata["closed"] = is_closed
    metadata["control_points"] = _json_safe_points(control_points)
    metadata["curve_method"] = method
    metadata["sample_count"] = sample_count
    metadata.setdefault(
        "creation_type",
        "curve_on_mesh" if snap_to_mesh else "manual",
    )
    metadata["snap_to_mesh"] = snap_to_mesh
    if snap_to_mesh:
        metadata["snap_mode"] = "mesh"
    metadata.setdefault("work_plane_type", "mesh" if snap_to_mesh else "manual")

    fitted_points = _safe_points(getattr(curve, "fitted_points", []))
    if len(fitted_points) < 2 and len(control_points) >= 2:
        fitted_points = sample_manual_curve(
            control_points,
            is_closed=is_closed,
            method=method,
            sample_count=sample_count,
        )

    curve.original_points = control_points.copy()
    curve.fitted_points = fitted_points
    curve.is_closed = is_closed
    curve.metadata = metadata
    return curve


def sample_manual_curve(
    control_points: Sequence[Sequence[float]] | np.ndarray,
    *,
    is_closed: bool,
    method: str,
    sample_count: int,
) -> np.ndarray:
    points = _safe_points(control_points)
    point_count = len(points)
    if point_count == 0:
        return np.zeros((0, 3), dtype=float)
    if point_count == 1:
        return points.copy()

    method = _normalized_curve_method(method)
    if method == MANUAL_CURVE_METHOD_POLYLINE:
        return _polyline_sample(points, is_closed=bool(is_closed))
    if point_count == 2:
        return _sample_line(points[0], points[1], _normalized_sample_count(sample_count))

    return _catmull_rom_sample(
        points,
        is_closed=bool(is_closed),
        sample_count=_normalized_sample_count(sample_count),
    )


def build_manual_stored_curve(
    *,
    curve_id: str,
    name: str,
    control_points: Sequence[Sequence[float]] | np.ndarray,
    is_closed: bool,
    creation_type: str,
    snap_to_mesh: bool,
    work_plane_type: str,
    source_section_plane_id: str | None = None,
    source_mesh_name: str | None = None,
    snap_triangle_indices: Sequence[int | None] | None = None,
    snap_normals: Sequence[Sequence[float] | None] | None = None,
    curve_method: str = DEFAULT_MANUAL_CURVE_METHOD,
    sample_count: int = DEFAULT_MANUAL_CURVE_SAMPLE_COUNT,
) -> StoredCurve:
    control_array = _safe_points(control_points)
    method = _normalized_curve_method(curve_method)
    count = _normalized_sample_count(sample_count)
    fitted_points = sample_manual_curve(
        control_array,
        is_closed=bool(is_closed),
        method=method,
        sample_count=count,
    )
    metadata = manual_curve_metadata(
        control_array,
        is_closed=bool(is_closed),
        creation_type=creation_type,
        snap_to_mesh=bool(snap_to_mesh),
        work_plane_type=work_plane_type,
        source_section_plane_id=source_section_plane_id,
        source_mesh_name=source_mesh_name,
        snap_triangle_indices=snap_triangle_indices,
        snap_normals=snap_normals,
        curve_method=method,
        sample_count=count,
    )
    return StoredCurve(
        id=str(curve_id),
        name=str(name),
        section_result_id="",
        plane_id=str(source_section_plane_id or ""),
        original_points=control_array.copy(),
        fitted_points=fitted_points,
        mean_error=0.0,
        max_error=0.0,
        is_closed=bool(is_closed),
        visible=True,
        selected=True,
        metadata=metadata,
    )


def manual_curve_close_threshold(model_extent: float | None) -> float:
    try:
        extent = float(model_extent)
    except (TypeError, ValueError):
        extent = 0.0
    if not np.isfinite(extent) or extent <= 0.0:
        extent = 0.0
    return max(extent * MANUAL_CURVE_CLOSE_THRESHOLD_RATIO, MANUAL_CURVE_CLOSE_THRESHOLD_MIN)


def should_snap_closed_to_first_point(
    control_points: Sequence[Sequence[float]] | np.ndarray,
    candidate_point: Sequence[float] | np.ndarray,
    *,
    model_extent: float | None,
) -> bool:
    points = _safe_points(control_points)
    if len(points) < 3:
        return False
    candidate = _safe_points([candidate_point])
    if len(candidate) != 1:
        return False
    distance = float(np.linalg.norm(candidate[0] - points[0]))
    return bool(distance <= manual_curve_close_threshold(model_extent))


def _catmull_rom_sample(
    points: np.ndarray,
    *,
    is_closed: bool,
    sample_count: int,
) -> np.ndarray:
    point_count = len(points)
    if point_count < 3:
        return _polyline_sample(points, is_closed=is_closed)

    segment_count = point_count if is_closed else point_count - 1
    samples_per_segment = max(int(np.ceil(sample_count / max(segment_count, 1))), 1)
    sampled: list[np.ndarray] = []
    for segment_index in range(segment_count):
        p0, p1, p2, p3 = _catmull_rom_segment_points(
            points,
            segment_index,
            is_closed=is_closed,
        )
        include_endpoint = segment_index == segment_count - 1 and not is_closed
        for step in range(samples_per_segment + (1 if include_endpoint else 0)):
            if step == samples_per_segment and not include_endpoint:
                continue
            t = step / float(samples_per_segment)
            if sampled and step == 0:
                continue
            sampled.append(_catmull_rom_point(p0, p1, p2, p3, t))

    if is_closed and sampled:
        sampled.append(sampled[0].copy())
    result = _safe_points(sampled)
    if not is_closed and len(result) >= 2:
        result[0] = points[0]
        result[-1] = points[-1]
    return result


def _catmull_rom_segment_points(
    points: np.ndarray,
    segment_index: int,
    *,
    is_closed: bool,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    count = len(points)
    if is_closed:
        return (
            points[(segment_index - 1) % count],
            points[segment_index % count],
            points[(segment_index + 1) % count],
            points[(segment_index + 2) % count],
        )

    start = segment_index
    return (
        points[max(start - 1, 0)],
        points[start],
        points[start + 1],
        points[min(start + 2, count - 1)],
    )


def _catmull_rom_point(
    p0: np.ndarray,
    p1: np.ndarray,
    p2: np.ndarray,
    p3: np.ndarray,
    t: float,
) -> np.ndarray:
    t2 = t * t
    t3 = t2 * t
    return 0.5 * (
        (2.0 * p1)
        + (-p0 + p2) * t
        + ((2.0 * p0) - (5.0 * p1) + (4.0 * p2) - p3) * t2
        + (-p0 + (3.0 * p1) - (3.0 * p2) + p3) * t3
    )


def _sample_line(start: np.ndarray, end: np.ndarray, sample_count: int) -> np.ndarray:
    steps = max(sample_count, 2)
    factors = np.linspace(0.0, 1.0, steps)
    return np.asarray(
        [(start * (1.0 - factor)) + (end * factor) for factor in factors],
        dtype=float,
    )


def _polyline_sample(points: np.ndarray, *, is_closed: bool) -> np.ndarray:
    if bool(is_closed) and len(points) >= 3 and not np.allclose(points[0], points[-1]):
        return np.vstack([points, points[0]])
    return points.copy()


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
    finite_mask = np.all(np.isfinite(values), axis=1)
    return values[finite_mask].astype(float, copy=True)


def _json_safe_points(points: Sequence[Sequence[float]] | np.ndarray) -> list[list[float]]:
    return [[float(value) for value in point] for point in _safe_points(points)]


def _json_safe_point_or_none(point: Sequence[float] | np.ndarray) -> list[float] | None:
    points = _json_safe_points([point])
    if not points:
        return None
    return points[0]


def _normalized_curve_method(method: object) -> str:
    value = str(method).strip().lower()
    if value == MANUAL_CURVE_METHOD_POLYLINE:
        return MANUAL_CURVE_METHOD_POLYLINE
    return MANUAL_CURVE_METHOD_CATMULL_ROM


def _normalized_sample_count(sample_count: object) -> int:
    try:
        value = int(sample_count)
    except (TypeError, ValueError):
        value = DEFAULT_MANUAL_CURVE_SAMPLE_COUNT
    return max(value, 2)
