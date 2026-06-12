"""Lightweight viewport preview geometry for surface patches."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from curves.curve_state import StoredCurve
from surfaces.surface_state import SurfacePatch


POINT_TOLERANCE = 1e-8


@dataclass(frozen=True)
class SurfacePreviewMesh:
    vertices: np.ndarray
    faces: np.ndarray
    source_surface_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "vertices",
            np.asarray(self.vertices, dtype=float).reshape((-1, 3)),
        )
        object.__setattr__(
            self,
            "faces",
            np.asarray(self.faces, dtype=int).reshape((-1, 3)),
        )


def build_surface_preview_mesh(
    surface: SurfacePatch,
    curves: Sequence[StoredCurve],
) -> SurfacePreviewMesh | None:
    """Build a coarse triangulated preview for the supported placeholder cases."""

    source_curves = _source_curves_for_surface(surface, curves)
    if source_curves is None:
        return None

    if len(source_curves) == 1:
        return _build_closed_curve_fan(surface, source_curves[0])

    if len(source_curves) == 2:
        return _build_two_curve_loft(surface, source_curves[0], source_curves[1])

    return None


def _source_curves_for_surface(
    surface: SurfacePatch,
    curves: Sequence[StoredCurve],
) -> list[StoredCurve] | None:
    if not surface.source_curve_ids:
        return None

    curves_by_id = {curve.id: curve for curve in curves}
    source_curves: list[StoredCurve] = []
    for curve_id in surface.source_curve_ids:
        curve = curves_by_id.get(curve_id)
        if curve is None:
            return None
        source_curves.append(curve)
    return source_curves


def _build_closed_curve_fan(
    surface: SurfacePatch,
    curve: StoredCurve,
) -> SurfacePreviewMesh | None:
    if not _is_curve_closed(curve):
        return None

    points = _clean_curve_points(curve)
    if points is None or len(points) < 3:
        return None

    center = np.mean(points, axis=0)
    vertices = np.vstack((center, points))
    faces = [
        (0, index + 1, ((index + 1) % len(points)) + 1)
        for index in range(len(points))
    ]
    return SurfacePreviewMesh(
        vertices=vertices,
        faces=np.asarray(faces, dtype=int),
        source_surface_id=surface.id,
    )


def _build_two_curve_loft(
    surface: SurfacePatch,
    first_curve: StoredCurve,
    second_curve: StoredCurve,
) -> SurfacePreviewMesh | None:
    first_points = _clean_curve_points(first_curve)
    second_points = _clean_curve_points(second_curve)
    if first_points is None or second_points is None:
        return None
    if len(first_points) < 2 or len(second_points) < 2:
        return None

    target_count = max(len(first_points), len(second_points))
    first_closed = _is_curve_closed(first_curve)
    second_closed = _is_curve_closed(second_curve)
    first_points = _resample_by_index(
        first_points,
        target_count=target_count,
        closed=first_closed,
    )
    second_points = _resample_by_index(
        second_points,
        target_count=target_count,
        closed=second_closed,
    )
    closed_loft = first_closed and second_closed
    segment_count = target_count if closed_loft else target_count - 1
    if segment_count < 1:
        return None

    vertices = np.vstack((first_points, second_points))
    faces: list[tuple[int, int, int]] = []
    for index in range(segment_count):
        next_index = (index + 1) % target_count
        first_start = index
        first_end = next_index
        second_start = target_count + index
        second_end = target_count + next_index
        faces.append((first_start, first_end, second_end))
        faces.append((first_start, second_end, second_start))

    return SurfacePreviewMesh(
        vertices=vertices,
        faces=np.asarray(faces, dtype=int),
        source_surface_id=surface.id,
    )


def _clean_curve_points(curve: StoredCurve) -> np.ndarray | None:
    try:
        points = np.asarray(curve.fitted_points, dtype=float)
    except (TypeError, ValueError):
        return None
    if points.ndim != 2 or points.shape[1] != 3:
        return None

    points = points[np.all(np.isfinite(points), axis=1)]
    if len(points) == 0:
        return None

    cleaned = [points[0]]
    for point in points[1:]:
        if np.linalg.norm(point - cleaned[-1]) > POINT_TOLERANCE:
            cleaned.append(point)

    if (
        len(cleaned) > 1
        and np.linalg.norm(cleaned[0] - cleaned[-1]) <= POINT_TOLERANCE
    ):
        cleaned.pop()

    if not cleaned:
        return None
    return np.asarray(cleaned, dtype=float).reshape((-1, 3))


def _is_curve_closed(curve: StoredCurve) -> bool:
    if bool(curve.is_closed):
        return True

    try:
        points = np.asarray(curve.fitted_points, dtype=float)
    except (TypeError, ValueError):
        return False
    if points.ndim != 2 or points.shape[1] != 3 or len(points) < 3:
        return False

    return bool(np.linalg.norm(points[0] - points[-1]) <= POINT_TOLERANCE)


def _resample_by_index(
    points: np.ndarray,
    *,
    target_count: int,
    closed: bool,
) -> np.ndarray:
    if len(points) == target_count:
        return points.copy()

    if closed:
        positions = np.linspace(0.0, float(len(points)), target_count, endpoint=False)
        lower_indices = np.floor(positions).astype(int) % len(points)
        upper_indices = (lower_indices + 1) % len(points)
    else:
        positions = np.linspace(0.0, float(len(points) - 1), target_count)
        lower_indices = np.floor(positions).astype(int)
        upper_indices = np.minimum(lower_indices + 1, len(points) - 1)

    fractions = (positions - np.floor(positions)).reshape((-1, 1))
    return (
        (points[lower_indices] * (1.0 - fractions))
        + (points[upper_indices] * fractions)
    )
