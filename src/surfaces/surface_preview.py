"""Lightweight viewport preview geometry for surface patches."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from curves.curve_state import StoredCurve
from surfaces.surface_state import SurfacePatch


POINT_TOLERANCE = 1e-8
AREA_TOLERANCE = 1e-10
MAX_PREVIEW_POINTS = 256
FAN_FILL_WARNING = "Fan fill preview may be inaccurate for concave curves"

# TODO: add curve repair / auto-close gaps before preview generation.
# TODO: add fragment joining for section curves split by scan noise.
# TODO: expose point-count matching controls for loft previews.
# TODO: replace placeholder stitching with constrained loft/surface fitting.
# TODO: add eventual NURBS/BREP generation outside this preview-only module.


@dataclass(frozen=True)
class SurfacePreviewMesh:
    vertices: np.ndarray
    faces: np.ndarray
    source_surface_id: str
    selected: bool = False

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


@dataclass(frozen=True)
class SurfacePreviewBuildResult:
    mesh: SurfacePreviewMesh | None
    preview_available: bool
    reason: str
    warning: str | None = None


def build_surface_preview(
    surface: SurfacePatch,
    curves: Sequence[StoredCurve],
) -> SurfacePreviewBuildResult:
    """Build preview geometry and diagnostics for supported placeholder cases."""

    source_curves, reason = _source_curves_for_surface(surface, curves)
    if source_curves is None:
        return SurfacePreviewBuildResult(
            mesh=None,
            preview_available=False,
            reason=reason,
        )

    if len(source_curves) == 1:
        return _build_closed_curve_fan_result(surface, source_curves[0])

    if len(source_curves) == 2:
        return _build_two_curve_loft_result(surface, source_curves[0], source_curves[1])

    return SurfacePreviewBuildResult(
        mesh=None,
        preview_available=False,
        reason="preview unavailable: unsupported curve count",
    )


def build_surface_preview_mesh(
    surface: SurfacePatch,
    curves: Sequence[StoredCurve],
) -> SurfacePreviewMesh | None:
    """Build a coarse triangulated preview for the supported placeholder cases."""

    return build_surface_preview(surface, curves).mesh


def _source_curves_for_surface(
    surface: SurfacePatch,
    curves: Sequence[StoredCurve],
) -> tuple[list[StoredCurve] | None, str]:
    if not surface.source_curve_ids:
        return None, "preview unavailable: unsupported curve count"

    curves_by_id = {curve.id: curve for curve in curves}
    source_curves: list[StoredCurve] = []
    for curve_id in surface.source_curve_ids:
        curve = curves_by_id.get(curve_id)
        if curve is None:
            return None, "missing source curve"
        source_curves.append(curve)
    return source_curves, ""


def _build_closed_curve_fan_result(
    surface: SurfacePatch,
    curve: StoredCurve,
) -> SurfacePreviewBuildResult:
    if not _is_curve_closed(curve):
        return SurfacePreviewBuildResult(
            mesh=None,
            preview_available=False,
            reason="single curve is not closed",
        )

    points = _clean_curve_points(curve)
    if points is None:
        return SurfacePreviewBuildResult(
            mesh=None,
            preview_available=False,
            reason="curve has invalid point data",
        )
    if len(points) < 3:
        return SurfacePreviewBuildResult(
            mesh=None,
            preview_available=False,
            reason="curve has too few points",
        )
    if _closed_area_estimate(points) <= AREA_TOLERANCE:
        return SurfacePreviewBuildResult(
            mesh=None,
            preview_available=False,
            reason="curve is degenerate",
        )

    center = np.mean(points, axis=0)
    vertices = np.vstack((center, points))
    faces: list[tuple[int, int, int]] = []
    for index in range(len(points)):
        face = (0, index + 1, ((index + 1) % len(points)) + 1)
        if _triangle_area(vertices[face[0]], vertices[face[1]], vertices[face[2]]) > AREA_TOLERANCE:
            faces.append(face)

    if not faces:
        return SurfacePreviewBuildResult(
            mesh=None,
            preview_available=False,
            reason="curve is degenerate",
        )

    return SurfacePreviewBuildResult(
        mesh=SurfacePreviewMesh(
            vertices=vertices,
            faces=np.asarray(faces, dtype=int),
            source_surface_id=surface.id,
            selected=bool(surface.selected),
        ),
        preview_available=True,
        reason="fan fill preview generated",
        warning=FAN_FILL_WARNING,
    )


def _build_two_curve_loft_result(
    surface: SurfacePatch,
    first_curve: StoredCurve,
    second_curve: StoredCurve,
) -> SurfacePreviewBuildResult:
    first_points = _clean_curve_points(first_curve)
    second_points = _clean_curve_points(second_curve)
    if first_points is None or second_points is None:
        return SurfacePreviewBuildResult(
            mesh=None,
            preview_available=False,
            reason="curve has invalid point data",
        )

    first_closed = _is_curve_closed(first_curve)
    second_closed = _is_curve_closed(second_curve)
    if len(first_points) < _minimum_point_count(first_closed) or len(second_points) < _minimum_point_count(second_closed):
        return SurfacePreviewBuildResult(
            mesh=None,
            preview_available=False,
            reason="curve has too few points",
        )

    target_count = min(max(len(first_points), len(second_points)), MAX_PREVIEW_POINTS)
    target_count = max(target_count, 3 if first_closed and second_closed else 2)
    first_points = _resample_by_arc_length(
        first_points,
        target_count=target_count,
        closed=first_closed,
    )
    second_points = _resample_by_arc_length(
        second_points,
        target_count=target_count,
        closed=second_closed,
    )
    if first_points is None or second_points is None:
        return SurfacePreviewBuildResult(
            mesh=None,
            preview_available=False,
            reason="curve is degenerate",
        )

    closed_loft = first_closed and second_closed
    second_points, reversed_second, seam_shift = _align_second_curve_points(
        first_points,
        second_points,
        closed=closed_loft,
    )
    segment_count = target_count if closed_loft else target_count - 1
    if segment_count < 1:
        return SurfacePreviewBuildResult(
            mesh=None,
            preview_available=False,
            reason="curve has too few points",
        )

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

    faces = [
        face
        for face in faces
        if _triangle_area(vertices[face[0]], vertices[face[1]], vertices[face[2]]) > AREA_TOLERANCE
    ]
    if not faces:
        return SurfacePreviewBuildResult(
            mesh=None,
            preview_available=False,
            reason="curve is degenerate",
        )

    if reversed_second:
        reason = "loft generated with reversed second curve"
    elif closed_loft and seam_shift != 0:
        reason = "loft generated with seam-aligned second curve"
    else:
        reason = "loft generated"

    return SurfacePreviewBuildResult(
        mesh=SurfacePreviewMesh(
            vertices=vertices,
            faces=np.asarray(faces, dtype=int),
            source_surface_id=surface.id,
            selected=bool(surface.selected),
        ),
        preview_available=True,
        reason=reason,
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


def _minimum_point_count(closed: bool) -> int:
    return 3 if closed else 2


def _resample_by_arc_length(
    points: np.ndarray,
    *,
    target_count: int,
    closed: bool,
) -> np.ndarray | None:
    if len(points) == target_count:
        return points.copy()

    path_points = np.vstack((points, points[0])) if closed else points
    segment_vectors = np.diff(path_points, axis=0)
    segment_lengths = np.linalg.norm(segment_vectors, axis=1)
    total_length = float(np.sum(segment_lengths))
    if total_length <= POINT_TOLERANCE:
        return None

    cumulative = np.concatenate(([0.0], np.cumsum(segment_lengths)))
    if closed:
        distances = np.linspace(0.0, total_length, target_count, endpoint=False)
    else:
        distances = np.linspace(0.0, total_length, target_count)

    segment_indices = np.searchsorted(cumulative, distances, side="right") - 1
    segment_indices = np.clip(segment_indices, 0, len(segment_lengths) - 1)
    local_lengths = segment_lengths[segment_indices].reshape((-1, 1))
    fractions = np.divide(
        (distances - cumulative[segment_indices]).reshape((-1, 1)),
        local_lengths,
        out=np.zeros((len(distances), 1), dtype=float),
        where=local_lengths > POINT_TOLERANCE,
    )
    lower_indices = segment_indices % len(points)
    upper_indices = (segment_indices + 1) % len(points) if closed else np.minimum(segment_indices + 1, len(points) - 1)
    resampled = (
        points[lower_indices] * (1.0 - fractions)
        + points[upper_indices] * fractions
    )
    if not closed:
        resampled[0] = points[0]
        resampled[-1] = points[-1]
    return resampled


def _align_second_curve_points(
    first_points: np.ndarray,
    second_points: np.ndarray,
    *,
    closed: bool,
) -> tuple[np.ndarray, bool, int]:
    if closed:
        best_points = second_points
        best_reversed = False
        best_shift = 0
        best_score = float("inf")
        for reversed_candidate, candidate in (
            (False, second_points),
            (True, second_points[::-1]),
        ):
            for shift in range(len(candidate)):
                shifted = np.roll(candidate, -shift, axis=0)
                score = _mean_pairing_distance(first_points, shifted)
                if score < best_score:
                    best_score = score
                    best_points = shifted
                    best_reversed = reversed_candidate
                    best_shift = shift
        return best_points.copy(), best_reversed, best_shift

    direct_score = _mean_pairing_distance(first_points, second_points)
    reversed_points = second_points[::-1]
    reversed_score = _mean_pairing_distance(first_points, reversed_points)
    if reversed_score < direct_score:
        return reversed_points.copy(), True, 0
    return second_points.copy(), False, 0


def _mean_pairing_distance(first_points: np.ndarray, second_points: np.ndarray) -> float:
    return float(np.mean(np.linalg.norm(first_points - second_points, axis=1)))


def _closed_area_estimate(points: np.ndarray) -> float:
    center = np.mean(points, axis=0)
    area_vector = np.zeros(3, dtype=float)
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        area_vector += np.cross(point - center, next_point - center)
    return float(np.linalg.norm(area_vector) * 0.5)


def _triangle_area(first: np.ndarray, second: np.ndarray, third: np.ndarray) -> float:
    return float(np.linalg.norm(np.cross(second - first, third - first)) * 0.5)
