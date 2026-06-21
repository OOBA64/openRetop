"""Lightweight viewport preview geometry for surface patches."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from curves.curve_state import StoredCurve
from curves.projection import project_curve_points_to_mesh
from mesh.triangle_mesh import TriangleMeshData
from surfaces.surface_state import SurfacePatch


POINT_TOLERANCE = 1e-8
AREA_TOLERANCE = 1e-10
MAX_PREVIEW_POINTS = 256
MAX_PATCH_GRID_COUNT = 64
PLANARITY_WARNING_THRESHOLD = 0.02

CLOSED_CURVE_FILL = "closed_curve_fill"
TWO_CURVE_LOFT = "two_curve_loft"
BOUNDARY_PATCH = "boundary_patch"
FOUR_CURVE_PATCH = "four_curve_patch"
CURVE_NETWORK_PATCH = "curve_network_patch"
MESH_CONFORMING_LOFT = "mesh_conforming_loft"

FAN_FILL_WARNING = "Fan fill preview may be inaccurate for concave curves"
LOFT_PAIR_DISTANCE_WARNING = "Loft preview has high paired-curve distance; inspect for twisting"
BOUNDARY_PATCH_FALLBACK_WARNING = (
    "Boundary patch triangulation fell back to fan fill; inspect concave areas."
)
FOUR_CURVE_ORDER_WARNING = "Curve order inferred from scene order; inspect patch."
CURVE_NETWORK_SPACING_WARNING = "Curve network spacing varies heavily; inspect patch."
CURVE_NETWORK_POINT_COUNT_WARNING = (
    "Curve network source curves have very different point counts."
)

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
    opacity: float | None = None
    wireframe_overlay: bool = False
    display_role: str = "preview_surface"

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
    diagnostics: dict[str, object] = field(default_factory=dict)


def build_surface_preview(
    surface: SurfacePatch,
    curves: Sequence[StoredCurve],
    *,
    mesh: TriangleMeshData | None = None,
) -> SurfacePreviewBuildResult:
    """Build preview geometry and diagnostics for supported placeholder cases."""

    source_curves, reason = _source_curves_for_surface(surface, curves)
    if source_curves is None:
        return SurfacePreviewBuildResult(
            mesh=None,
            preview_available=False,
            reason=reason,
        )

    preview_mode = _preview_mode(surface)
    if preview_mode == MESH_CONFORMING_LOFT:
        return build_mesh_conforming_loft_preview(surface, source_curves, mesh)
    if preview_mode == BOUNDARY_PATCH:
        if len(source_curves) != 1:
            return _unavailable(
                "boundary patch requires exactly one curve",
                preview_mode=BOUNDARY_PATCH,
                source_curve_count=len(source_curves),
            )
        return build_boundary_patch_preview(surface, source_curves[0])

    if preview_mode == FOUR_CURVE_PATCH:
        return build_four_curve_patch_preview(surface, source_curves)

    if preview_mode == CURVE_NETWORK_PATCH:
        return build_curve_network_patch_preview(surface, source_curves)

    if preview_mode == CLOSED_CURVE_FILL and len(source_curves) != 1:
        return _unavailable(
            "closed-curve fill requires exactly one curve",
            preview_mode=CLOSED_CURVE_FILL,
            source_curve_count=len(source_curves),
        )

    if preview_mode == TWO_CURVE_LOFT and len(source_curves) != 2:
        return _unavailable(
            "two-curve loft requires exactly two curves",
            preview_mode=TWO_CURVE_LOFT,
            source_curve_count=len(source_curves),
        )

    if len(source_curves) == 1:
        return _build_closed_curve_fan_result(source=surface, curve=source_curves[0])

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
    *,
    mesh: TriangleMeshData | None = None,
) -> SurfacePreviewMesh | None:
    """Build a coarse triangulated preview for the supported placeholder cases."""

    return build_surface_preview(surface, curves, mesh=mesh).mesh


def build_boundary_patch_preview(
    surface: SurfacePatch,
    curve: StoredCurve,
) -> SurfacePreviewBuildResult:
    diagnostics: dict[str, object] = {
        "preview_mode": BOUNDARY_PATCH,
        "source_curve_count": 1,
        "boundary_curve_id": curve.id,
        "boundary_curve_name": curve.name,
    }
    if not _is_curve_closed(curve):
        return _unavailable(
            "boundary patch requires one closed curve",
            diagnostics=diagnostics,
        )

    points = _clean_curve_points(curve)
    if points is None:
        return _unavailable("curve has invalid point data", diagnostics=diagnostics)
    diagnostics["input_point_count"] = int(len(points))
    if len(points) < 3:
        return _unavailable("curve has too few points", diagnostics=diagnostics)
    if _closed_area_estimate(points) <= AREA_TOLERANCE:
        return _unavailable("curve is degenerate", diagnostics=diagnostics)

    plane = _best_fit_plane(points)
    if plane is None:
        return _unavailable("curve is degenerate", diagnostics=diagnostics)
    origin, u_axis, v_axis, _normal, planarity_error = plane
    diagnostics["planarity_error"] = float(planarity_error)

    projected_points = np.column_stack(
        ((points - origin) @ u_axis, (points - origin) @ v_axis)
    )
    faces = _triangulate_polygon(projected_points)
    warning = (
        "Boundary curve is not very planar; inspect patch."
        if planarity_error > PLANARITY_WARNING_THRESHOLD
        else None
    )
    if faces:
        diagnostics["triangulation_method"] = "ear_clipping"
        return SurfacePreviewBuildResult(
            mesh=SurfacePreviewMesh(
                vertices=points.copy(),
                faces=np.asarray(faces, dtype=int),
                source_surface_id=surface.id,
                selected=bool(surface.selected),
            ),
            preview_available=True,
            reason="boundary patch preview generated",
            warning=warning,
            diagnostics=diagnostics,
        )

    fallback = _build_closed_curve_fan_result(source=surface, curve=curve)
    if fallback.mesh is None:
        return SurfacePreviewBuildResult(
            mesh=None,
            preview_available=False,
            reason=fallback.reason,
            warning=fallback.warning,
            diagnostics=diagnostics,
        )
    diagnostics["triangulation_method"] = "fan_fallback"
    diagnostics["fallback_reason"] = "polygon triangulation failed"
    return SurfacePreviewBuildResult(
        mesh=fallback.mesh,
        preview_available=True,
        reason="boundary patch preview generated with fan fallback",
        warning=warning or BOUNDARY_PATCH_FALLBACK_WARNING,
        diagnostics=diagnostics,
    )


def build_four_curve_patch_preview(
    surface: SurfacePatch,
    curves: Sequence[StoredCurve],
) -> SurfacePreviewBuildResult:
    diagnostics: dict[str, object] = {
        "preview_mode": FOUR_CURVE_PATCH,
        "source_curve_count": len(curves),
        "curve_order": list(surface.source_curve_ids),
    }
    if len(curves) != 4:
        return _unavailable(
            "four-curve patch requires exactly four curves",
            diagnostics=diagnostics,
        )

    cleaned = _clean_patch_curves(curves, min_point_count=2)
    if isinstance(cleaned, str):
        return _unavailable(cleaned, diagnostics=diagnostics)

    bottom_source, right_source, top_source, left_source = cleaned
    grid_u_count = _patch_grid_count(bottom_source, top_source)
    grid_v_count = _patch_grid_count(left_source, right_source)
    bottom = _resample_by_arc_length(
        bottom_source,
        target_count=grid_u_count,
        closed=False,
    )
    right = _resample_by_arc_length(
        right_source,
        target_count=grid_v_count,
        closed=False,
    )
    top = _resample_by_arc_length(top_source, target_count=grid_u_count, closed=False)
    left = _resample_by_arc_length(left_source, target_count=grid_v_count, closed=False)
    if bottom is None or right is None or top is None or left is None:
        return _unavailable("curve is degenerate", diagnostics=diagnostics)

    right, right_reversed = _orient_curve_start_near(right, bottom[-1])
    left, left_reversed = _orient_curve_start_near(left, bottom[0])
    top, top_reversed = _orient_curve_between(top, left[-1], right[-1])
    corner_gaps = [
        float(np.linalg.norm(bottom[0] - left[0])),
        float(np.linalg.norm(bottom[-1] - right[0])),
        float(np.linalg.norm(top[0] - left[-1])),
        float(np.linalg.norm(top[-1] - right[-1])),
    ]
    diagnostics.update(
        {
            "grid_u_count": int(grid_u_count),
            "grid_v_count": int(grid_v_count),
            "average_corner_gap": float(np.mean(corner_gaps)),
            "max_corner_gap": float(np.max(corner_gaps)),
            "seam_reversal_applied": [
                False,
                bool(right_reversed),
                bool(top_reversed),
                bool(left_reversed),
            ],
        }
    )
    vertices = _coons_patch_grid(bottom, right, top, left)
    faces = _grid_faces(grid_u_count, grid_v_count)
    valid_faces = _valid_triangle_faces(vertices, faces)
    if not valid_faces:
        return _unavailable("grid generation failed", diagnostics=diagnostics)

    return SurfacePreviewBuildResult(
        mesh=SurfacePreviewMesh(
            vertices=vertices,
            faces=np.asarray(valid_faces, dtype=int),
            source_surface_id=surface.id,
            selected=bool(surface.selected),
        ),
        preview_available=True,
        reason="four-curve patch preview generated",
        warning=FOUR_CURVE_ORDER_WARNING,
        diagnostics=diagnostics,
    )


def build_curve_network_patch_preview(
    surface: SurfacePatch,
    curves: Sequence[StoredCurve],
) -> SurfacePreviewBuildResult:
    diagnostics: dict[str, object] = {
        "preview_mode": CURVE_NETWORK_PATCH,
        "source_curve_count": len(curves),
        "network_curve_count": len(curves),
    }
    if len(curves) < 3:
        return _unavailable(
            "curve network patch requires at least three curves",
            diagnostics=diagnostics,
        )

    cleaned = _clean_patch_curves(curves, min_point_count=2)
    if isinstance(cleaned, str):
        return _unavailable(cleaned, diagnostics=diagnostics)

    point_counts = [len(points) for points in cleaned]
    target_count = min(max(max(point_counts), 2), MAX_PATCH_GRID_COUNT)
    aligned_curves: list[np.ndarray] = []
    warnings: list[str] = []
    if _count_ratio(min(point_counts), max(point_counts)) > 3.0:
        warnings.append(CURVE_NETWORK_POINT_COUNT_WARNING)

    for index, points in enumerate(cleaned):
        resampled = _resample_by_arc_length(
            points,
            target_count=target_count,
            closed=False,
        )
        if resampled is None:
            return _unavailable("curve is degenerate", diagnostics=diagnostics)
        if index > 0:
            resampled, _reversed = _orient_curve_like_previous(
                aligned_curves[-1],
                resampled,
            )
        aligned_curves.append(resampled)

    pair_distances: list[np.ndarray] = []
    for first, second in zip(aligned_curves, aligned_curves[1:]):
        pair_distances.append(np.linalg.norm(first - second, axis=1))
    if not pair_distances:
        return _unavailable("curve network patch requires at least three curves", diagnostics=diagnostics)
    all_distances = np.concatenate(pair_distances)
    average_pair_distance = float(np.mean(all_distances))
    max_pair_distance = float(np.max(all_distances))
    strip_means = [float(np.mean(distances)) for distances in pair_distances]
    if _count_ratio(min(strip_means), max(strip_means)) > 3.0:
        warnings.append(CURVE_NETWORK_SPACING_WARNING)

    reference_length = max(
        np.mean([_polyline_length(points, closed=False) for points in aligned_curves]),
        POINT_TOLERANCE,
    )
    if max_pair_distance > reference_length * 10.0:
        return _unavailable(
            "curve network source curves are too far apart",
            diagnostics=diagnostics,
        )

    vertices = np.vstack(aligned_curves)
    faces = _network_strip_faces(len(aligned_curves), target_count)
    valid_faces = _valid_triangle_faces(vertices, faces)
    if not valid_faces:
        return _unavailable("grid generation failed", diagnostics=diagnostics)

    diagnostics.update(
        {
            "resampled_point_count": int(target_count),
            "strip_count": int(len(aligned_curves) - 1),
            "average_pair_distance": average_pair_distance,
            "max_pair_distance": max_pair_distance,
        }
    )
    if warnings:
        diagnostics["warnings"] = list(dict.fromkeys(warnings))

    return SurfacePreviewBuildResult(
        mesh=SurfacePreviewMesh(
            vertices=vertices,
            faces=np.asarray(valid_faces, dtype=int),
            source_surface_id=surface.id,
            selected=bool(surface.selected),
        ),
        preview_available=True,
        reason="curve network patch preview generated",
        warning=warnings[0] if warnings else None,
        diagnostics=diagnostics,
    )


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
    source: SurfacePatch,
    curve: StoredCurve,
) -> SurfacePreviewBuildResult:
    if not _is_curve_closed(curve):
        return SurfacePreviewBuildResult(
            mesh=None,
            preview_available=False,
            reason="single curve is not closed",
            diagnostics={"preview_mode": CLOSED_CURVE_FILL, "source_curve_count": 1},
        )

    points = _clean_curve_points(curve)
    if points is None:
        return SurfacePreviewBuildResult(
            mesh=None,
            preview_available=False,
            reason="curve has invalid point data",
            diagnostics={"preview_mode": CLOSED_CURVE_FILL, "source_curve_count": 1},
        )
    if len(points) < 3:
        return SurfacePreviewBuildResult(
            mesh=None,
            preview_available=False,
            reason="curve has too few points",
            diagnostics={
                "preview_mode": CLOSED_CURVE_FILL,
                "source_curve_count": 1,
                "input_point_count": int(len(points)),
            },
        )
    if _closed_area_estimate(points) <= AREA_TOLERANCE:
        return SurfacePreviewBuildResult(
            mesh=None,
            preview_available=False,
            reason="curve is degenerate",
            diagnostics={
                "preview_mode": CLOSED_CURVE_FILL,
                "source_curve_count": 1,
                "input_point_count": int(len(points)),
            },
        )

    center = np.mean(points, axis=0)
    vertices = np.vstack((center, points))
    faces: list[tuple[int, int, int]] = []
    for index in range(len(points)):
        faces.append((0, index + 1, ((index + 1) % len(points)) + 1))
    valid_faces = _valid_triangle_faces(vertices, faces)

    if not valid_faces:
        return SurfacePreviewBuildResult(
            mesh=None,
            preview_available=False,
            reason="curve is degenerate",
            diagnostics={
                "preview_mode": CLOSED_CURVE_FILL,
                "source_curve_count": 1,
                "input_point_count": int(len(points)),
            },
        )

    return SurfacePreviewBuildResult(
        mesh=SurfacePreviewMesh(
            vertices=vertices,
            faces=np.asarray(valid_faces, dtype=int),
            source_surface_id=source.id,
            selected=bool(source.selected),
        ),
        preview_available=True,
        reason="fan fill preview generated",
        warning=FAN_FILL_WARNING,
        diagnostics={
            "preview_mode": CLOSED_CURVE_FILL,
            "source_curve_count": 1,
            "input_point_count": int(len(points)),
        },
    )


def _build_two_curve_loft_result(
    surface: SurfacePatch,
    first_curve: StoredCurve,
    second_curve: StoredCurve,
) -> SurfacePreviewBuildResult:
    first_points = _clean_curve_points(first_curve)
    second_points = _clean_curve_points(second_curve)
    diagnostics: dict[str, object] = {
        "preview_mode": TWO_CURVE_LOFT,
        "source_curve_count": 2,
    }
    if first_points is None or second_points is None:
        return _unavailable("curve has invalid point data", diagnostics=diagnostics)

    first_closed = _is_curve_closed(first_curve)
    second_closed = _is_curve_closed(second_curve)
    if (
        len(first_points) < _minimum_point_count(first_closed)
        or len(second_points) < _minimum_point_count(second_closed)
    ):
        return _unavailable("curve has too few points", diagnostics=diagnostics)

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
        return _unavailable("curve is degenerate", diagnostics=diagnostics)

    closed_loft = first_closed and second_closed
    second_points, reversed_second, seam_shift = _align_second_curve_points(
        first_points,
        second_points,
        closed=closed_loft,
    )
    segment_count = target_count if closed_loft else target_count - 1
    if segment_count < 1:
        return _unavailable("curve has too few points", diagnostics=diagnostics)

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

    faces = _valid_triangle_faces(vertices, faces)
    if not faces:
        return _unavailable("curve is degenerate", diagnostics=diagnostics)

    if reversed_second:
        reason = "loft generated with reversed second curve"
    elif closed_loft and seam_shift != 0:
        reason = "loft generated with seam-aligned second curve"
    else:
        reason = "loft generated"
    average_pair_distance, max_pair_distance = _pairing_distance_stats(
        first_points,
        second_points,
    )
    warning = _loft_pair_distance_warning(
        first_points,
        second_points,
        max_pair_distance=max_pair_distance,
        closed=closed_loft,
    )
    diagnostics.update(
        {
            "reversed_second_curve": bool(reversed_second),
            "seam_shift_applied": bool(seam_shift != 0),
            "seam_shift_index": int(seam_shift),
            "resampled_point_count": int(target_count),
            "average_pair_distance": average_pair_distance,
            "max_pair_distance": max_pair_distance,
        }
    )

    return SurfacePreviewBuildResult(
        mesh=SurfacePreviewMesh(
            vertices=vertices,
            faces=np.asarray(faces, dtype=int),
            source_surface_id=surface.id,
            selected=bool(surface.selected),
        ),
        preview_available=True,
        reason=reason,
        warning=warning,
        diagnostics=diagnostics,
    )


def build_mesh_conforming_loft_preview(
    surface: SurfacePatch,
    source_curves: Sequence[StoredCurve],
    mesh: TriangleMeshData | None,
) -> SurfacePreviewBuildResult:
    """Project a loft sampling grid onto the scan without creating CAD geometry."""

    diagnostics: dict[str, object] = {
        "preview_mode": MESH_CONFORMING_LOFT,
        "conforming_preview": True,
        "source_curve_count": len(source_curves),
        "source_curve_ids": [curve.id for curve in source_curves],
        "source_mesh_name": str(surface.metadata.get("source_mesh_name", "")),
    }
    if len(source_curves) < 2:
        return _unavailable(
            "mesh-conforming loft requires at least two open curves",
            diagnostics=diagnostics,
        )
    if any(_is_curve_closed(curve) for curve in source_curves):
        return _unavailable(
            "mesh-conforming loft requires open source curves",
            diagnostics=diagnostics,
        )
    if mesh is None or mesh.is_empty():
        return _unavailable(
            "mesh-conforming loft requires a loaded mesh",
            diagnostics=diagnostics,
        )

    cleaned = _clean_patch_curves(source_curves, min_point_count=2)
    if isinstance(cleaned, str):
        return _unavailable(cleaned, diagnostics=diagnostics)
    grid_u_count = min(
        max(max(len(points) for points in cleaned), 8),
        MAX_PATCH_GRID_COUNT,
    )
    try:
        requested_v_count = int(surface.metadata.get("grid_v_count", 16))
    except (TypeError, ValueError):
        requested_v_count = 16
    grid_v_count = min(max(requested_v_count, len(cleaned)), MAX_PATCH_GRID_COUNT)
    rows: list[np.ndarray] = []
    for points in cleaned:
        row = _resample_by_arc_length(points, target_count=grid_u_count, closed=False)
        if row is None:
            return _unavailable("curve is degenerate", diagnostics=diagnostics)
        if rows:
            row, _reversed, _shift = _align_second_curve_points(
                rows[-1],
                row,
                closed=False,
            )
        rows.append(row)

    loft_rows: list[np.ndarray] = []
    for v_index in range(grid_v_count):
        source_position = (
            0.0
            if grid_v_count <= 1
            else v_index * (len(rows) - 1) / float(grid_v_count - 1)
        )
        lower_index = min(int(np.floor(source_position)), len(rows) - 1)
        upper_index = min(lower_index + 1, len(rows) - 1)
        factor = source_position - lower_index
        loft_rows.append(
            rows[lower_index] * (1.0 - factor) + rows[upper_index] * factor
        )
    unprojected_vertices = np.vstack(loft_rows)

    threshold = _optional_positive_metadata_float(
        surface.metadata.get("projection_distance_threshold")
    )
    projection = project_curve_points_to_mesh(
        unprojected_vertices,
        mesh,
        max_search_distance=threshold,
        preserve_missed_points=True,
    )
    attempted_distances = projection.distances[np.isfinite(projection.distances)]
    faces = _grid_faces(grid_u_count, grid_v_count)
    valid_faces = _valid_triangle_faces(projection.projected_points, faces)
    diagnostics.update(
        {
            "grid_u_count": int(grid_u_count),
            "grid_v_count": int(grid_v_count),
            "projection_mean_distance": (
                float(np.mean(attempted_distances)) if len(attempted_distances) else 0.0
            ),
            "projection_max_distance": (
                float(np.max(attempted_distances)) if len(attempted_distances) else 0.0
            ),
            "failed_projection_count": int(projection.missed_count),
            "projected_point_count": int(projection.projected_count),
            "projection_distance_threshold": threshold,
            "show_projection_error_heatmap": bool(
                surface.metadata.get("show_projection_error_heatmap", False)
            ),
            "wireframe_overlay": False,
            "is_brep": False,
        }
    )
    if not valid_faces:
        return _unavailable(
            "mesh-conforming loft projection produced no valid faces",
            diagnostics=diagnostics,
        )
    warning = None
    if projection.missed_count:
        warning = (
            f"{projection.missed_count} loft grid points exceeded the projection threshold."
        )
    return SurfacePreviewBuildResult(
        mesh=SurfacePreviewMesh(
            vertices=projection.projected_points,
            faces=np.asarray(valid_faces, dtype=int),
            source_surface_id=surface.id,
            selected=bool(surface.selected),
            wireframe_overlay=False,
            display_role="mesh_conforming_preview",
        ),
        preview_available=True,
        reason="mesh-conforming loft preview generated",
        warning=warning,
        diagnostics=diagnostics,
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


def _optional_positive_metadata_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) and number > 0.0 else None


def _clean_patch_curves(
    curves: Sequence[StoredCurve],
    *,
    min_point_count: int,
) -> list[np.ndarray] | str:
    cleaned: list[np.ndarray] = []
    for curve in curves:
        points = _clean_curve_points(curve)
        if points is None:
            return "curve has invalid point data"
        if len(points) < min_point_count:
            return "curve has too few points"
        if _polyline_length(points, closed=False) <= POINT_TOLERANCE:
            return "curve is degenerate"
        cleaned.append(points)
    return cleaned


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
    upper_indices = (
        (segment_indices + 1) % len(points)
        if closed
        else np.minimum(segment_indices + 1, len(points) - 1)
    )
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
        best_score = (float("inf"), float("inf"))
        for reversed_candidate, candidate in (
            (False, second_points),
            (True, second_points[::-1]),
        ):
            for shift in range(len(candidate)):
                shifted = np.roll(candidate, -shift, axis=0)
                score = _pairing_score(first_points, shifted)
                if score < best_score:
                    best_score = score
                    best_points = shifted
                    best_reversed = reversed_candidate
                    best_shift = shift
        return best_points.copy(), best_reversed, best_shift

    direct_score = _pairing_score(first_points, second_points)
    reversed_points = second_points[::-1]
    reversed_score = _pairing_score(first_points, reversed_points)
    if reversed_score < direct_score:
        return reversed_points.copy(), True, 0
    return second_points.copy(), False, 0


def _pairing_distance_stats(
    first_points: np.ndarray,
    second_points: np.ndarray,
) -> tuple[float, float]:
    distances = np.linalg.norm(first_points - second_points, axis=1)
    return (float(np.mean(distances)), float(np.max(distances)))


def _pairing_score(
    first_points: np.ndarray,
    second_points: np.ndarray,
) -> tuple[float, float]:
    return _pairing_distance_stats(first_points, second_points)


def _loft_pair_distance_warning(
    first_points: np.ndarray,
    second_points: np.ndarray,
    *,
    max_pair_distance: float,
    closed: bool,
) -> str | None:
    first_length = _polyline_length(first_points, closed=closed)
    second_length = _polyline_length(second_points, closed=closed)
    reference_length = max((first_length + second_length) * 0.5, POINT_TOLERANCE)
    if max_pair_distance > reference_length:
        return LOFT_PAIR_DISTANCE_WARNING
    return None


def _polyline_length(points: np.ndarray, *, closed: bool) -> float:
    if len(points) < 2:
        return 0.0

    path_points = np.vstack((points, points[0])) if closed else points
    return float(np.sum(np.linalg.norm(np.diff(path_points, axis=0), axis=1)))


def _best_fit_plane(
    points: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float] | None:
    if len(points) < 3:
        return None
    origin = np.mean(points, axis=0)
    centered = points - origin
    try:
        _u, _s, vh = np.linalg.svd(centered, full_matrices=False)
    except np.linalg.LinAlgError:
        return None
    if vh.shape[0] < 3:
        return None
    u_axis = vh[0]
    v_axis = vh[1]
    normal = vh[-1]
    normal_length = float(np.linalg.norm(normal))
    if normal_length <= POINT_TOLERANCE or not np.isfinite(normal_length):
        return None
    normal = normal / normal_length
    distances = np.abs(centered @ normal)
    planarity_error = float(np.max(distances)) if len(distances) else 0.0
    return origin, u_axis, v_axis, normal, planarity_error


def _triangulate_polygon(points_2d: np.ndarray) -> list[tuple[int, int, int]]:
    if len(points_2d) < 3:
        return []
    polygon_area = _signed_polygon_area(points_2d)
    if abs(polygon_area) <= AREA_TOLERANCE:
        return []
    orientation = 1.0 if polygon_area > 0.0 else -1.0
    remaining = list(range(len(points_2d)))
    faces: list[tuple[int, int, int]] = []
    guard = 0
    while len(remaining) > 3 and guard < len(points_2d) * len(points_2d):
        guard += 1
        clipped = False
        for local_index, current_index in enumerate(list(remaining)):
            previous_index = remaining[(local_index - 1) % len(remaining)]
            next_index = remaining[(local_index + 1) % len(remaining)]
            previous_point = points_2d[previous_index]
            current_point = points_2d[current_index]
            next_point = points_2d[next_index]
            if orientation * _cross_2d(previous_point, current_point, next_point) <= AREA_TOLERANCE:
                continue
            if _triangle_contains_polygon_point(
                points_2d,
                remaining,
                (previous_index, current_index, next_index),
            ):
                continue
            faces.append(
                (previous_index, current_index, next_index)
                if orientation > 0.0
                else (previous_index, next_index, current_index)
            )
            remaining.pop(local_index)
            clipped = True
            break
        if not clipped:
            return []
    if len(remaining) == 3:
        face = tuple(remaining)
        faces.append(face if orientation > 0.0 else (face[0], face[2], face[1]))
    return faces


def _triangle_contains_polygon_point(
    points_2d: np.ndarray,
    polygon_indices: Sequence[int],
    triangle_indices: tuple[int, int, int],
) -> bool:
    triangle_points = points_2d[list(triangle_indices)]
    triangle_index_set = set(triangle_indices)
    for point_index in polygon_indices:
        if point_index in triangle_index_set:
            continue
        if _point_in_triangle_2d(points_2d[point_index], triangle_points):
            return True
    return False


def _point_in_triangle_2d(point: np.ndarray, triangle: np.ndarray) -> bool:
    a, b, c = triangle
    first = _cross_2d(a, b, point)
    second = _cross_2d(b, c, point)
    third = _cross_2d(c, a, point)
    has_negative = first < -POINT_TOLERANCE or second < -POINT_TOLERANCE or third < -POINT_TOLERANCE
    has_positive = first > POINT_TOLERANCE or second > POINT_TOLERANCE or third > POINT_TOLERANCE
    return not (has_negative and has_positive)


def _cross_2d(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    ab = b - a
    ac = c - a
    return float(ab[0] * ac[1] - ab[1] * ac[0])


def _signed_polygon_area(points_2d: np.ndarray) -> float:
    x_values = points_2d[:, 0]
    y_values = points_2d[:, 1]
    return float(
        0.5
        * np.sum(
            x_values * np.roll(y_values, -1)
            - y_values * np.roll(x_values, -1)
        )
    )


def _patch_grid_count(first: np.ndarray, second: np.ndarray) -> int:
    return min(max(len(first), len(second), 2), MAX_PATCH_GRID_COUNT)


def _orient_curve_start_near(
    points: np.ndarray,
    target_start: np.ndarray,
) -> tuple[np.ndarray, bool]:
    direct_distance = float(np.linalg.norm(points[0] - target_start))
    reversed_distance = float(np.linalg.norm(points[-1] - target_start))
    if reversed_distance < direct_distance:
        return points[::-1].copy(), True
    return points.copy(), False


def _orient_curve_between(
    points: np.ndarray,
    target_start: np.ndarray,
    target_end: np.ndarray,
) -> tuple[np.ndarray, bool]:
    direct_distance = float(
        np.linalg.norm(points[0] - target_start)
        + np.linalg.norm(points[-1] - target_end)
    )
    reversed_distance = float(
        np.linalg.norm(points[-1] - target_start)
        + np.linalg.norm(points[0] - target_end)
    )
    if reversed_distance < direct_distance:
        return points[::-1].copy(), True
    return points.copy(), False


def _orient_curve_like_previous(
    previous_points: np.ndarray,
    points: np.ndarray,
) -> tuple[np.ndarray, bool]:
    direct_score = _pairing_score(previous_points, points)
    reversed_points = points[::-1]
    reversed_score = _pairing_score(previous_points, reversed_points)
    if reversed_score < direct_score:
        return reversed_points.copy(), True
    return points.copy(), False


def _coons_patch_grid(
    bottom: np.ndarray,
    right: np.ndarray,
    top: np.ndarray,
    left: np.ndarray,
) -> np.ndarray:
    grid_u_count = len(bottom)
    grid_v_count = len(left)
    p00 = (bottom[0] + left[0]) * 0.5
    p10 = (bottom[-1] + right[0]) * 0.5
    p01 = (top[0] + left[-1]) * 0.5
    p11 = (top[-1] + right[-1]) * 0.5
    vertices: list[np.ndarray] = []
    for v_index in range(grid_v_count):
        v = 0.0 if grid_v_count == 1 else v_index / float(grid_v_count - 1)
        for u_index in range(grid_u_count):
            u = 0.0 if grid_u_count == 1 else u_index / float(grid_u_count - 1)
            boundary_blend = (
                (1.0 - v) * bottom[u_index]
                + v * top[u_index]
                + (1.0 - u) * left[v_index]
                + u * right[v_index]
            )
            corner_blend = (
                (1.0 - u) * (1.0 - v) * p00
                + u * (1.0 - v) * p10
                + (1.0 - u) * v * p01
                + u * v * p11
            )
            vertices.append(boundary_blend - corner_blend)
    return np.asarray(vertices, dtype=float).reshape((-1, 3))


def _grid_faces(
    grid_u_count: int,
    grid_v_count: int,
) -> list[tuple[int, int, int]]:
    faces: list[tuple[int, int, int]] = []
    for v_index in range(grid_v_count - 1):
        for u_index in range(grid_u_count - 1):
            lower_left = v_index * grid_u_count + u_index
            lower_right = lower_left + 1
            upper_left = (v_index + 1) * grid_u_count + u_index
            upper_right = upper_left + 1
            faces.append((lower_left, lower_right, upper_right))
            faces.append((lower_left, upper_right, upper_left))
    return faces


def _network_strip_faces(
    curve_count: int,
    point_count: int,
) -> list[tuple[int, int, int]]:
    faces: list[tuple[int, int, int]] = []
    for curve_index in range(curve_count - 1):
        first_offset = curve_index * point_count
        second_offset = (curve_index + 1) * point_count
        for point_index in range(point_count - 1):
            first_start = first_offset + point_index
            first_end = first_start + 1
            second_start = second_offset + point_index
            second_end = second_start + 1
            faces.append((first_start, first_end, second_end))
            faces.append((first_start, second_end, second_start))
    return faces


def _valid_triangle_faces(
    vertices: np.ndarray,
    faces: Sequence[tuple[int, int, int]],
) -> list[tuple[int, int, int]]:
    valid_faces: list[tuple[int, int, int]] = []
    vertex_count = int(len(vertices))
    for raw_face in faces:
        if len(raw_face) != 3:
            continue
        face = tuple(int(index) for index in raw_face)
        if any(index < 0 or index >= vertex_count for index in face):
            continue
        if len(set(face)) != 3:
            continue
        first, second, third = (vertices[index] for index in face)
        if not (
            np.all(np.isfinite(first))
            and np.all(np.isfinite(second))
            and np.all(np.isfinite(third))
        ):
            continue
        if (
            np.linalg.norm(first - second) <= POINT_TOLERANCE
            or np.linalg.norm(second - third) <= POINT_TOLERANCE
            or np.linalg.norm(third - first) <= POINT_TOLERANCE
        ):
            continue
        if _triangle_area(first, second, third) <= AREA_TOLERANCE:
            continue
        valid_faces.append(face)
    return valid_faces


def _closed_area_estimate(points: np.ndarray) -> float:
    center = np.mean(points, axis=0)
    area_vector = np.zeros(3, dtype=float)
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        area_vector += np.cross(point - center, next_point - center)
    return float(np.linalg.norm(area_vector) * 0.5)


def _triangle_area(first: np.ndarray, second: np.ndarray, third: np.ndarray) -> float:
    return float(np.linalg.norm(np.cross(second - first, third - first)) * 0.5)


def _preview_mode(surface: SurfacePatch) -> str:
    metadata = surface.metadata if isinstance(surface.metadata, dict) else {}
    mode = str(metadata.get("preview_mode", "")).strip().lower()
    if mode:
        return mode
    surface_type = str(surface.surface_type).strip().lower()
    return {
        "preview_fill": CLOSED_CURVE_FILL,
        "preview_loft": TWO_CURVE_LOFT,
        "preview_boundary_patch": BOUNDARY_PATCH,
        "preview_four_curve_patch": FOUR_CURVE_PATCH,
        "preview_curve_network_patch": CURVE_NETWORK_PATCH,
        "mesh_conforming_loft_preview": MESH_CONFORMING_LOFT,
    }.get(surface_type, "")


def _unavailable(
    reason: str,
    *,
    preview_mode: str | None = None,
    source_curve_count: int | None = None,
    diagnostics: dict[str, object] | None = None,
) -> SurfacePreviewBuildResult:
    result_diagnostics = {} if diagnostics is None else dict(diagnostics)
    if preview_mode is not None:
        result_diagnostics.setdefault("preview_mode", preview_mode)
    if source_curve_count is not None:
        result_diagnostics.setdefault("source_curve_count", int(source_curve_count))
    return SurfacePreviewBuildResult(
        mesh=None,
        preview_available=False,
        reason=reason,
        diagnostics=result_diagnostics,
    )


def _count_ratio(first: float, second: float) -> float:
    smaller = max(min(float(first), float(second)), POINT_TOLERANCE)
    larger = max(float(first), float(second), POINT_TOLERANCE)
    return larger / smaller
