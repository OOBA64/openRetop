"""Analytic primitive fitting helpers for selected mesh regions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from mesh.triangle_mesh import TriangleMeshData
from regions.region_state import RegionSelection


@dataclass(frozen=True)
class RegionPlaneFitResult:
    success: bool
    reason: str
    origin: np.ndarray
    normal: np.ndarray
    u_axis: np.ndarray
    v_axis: np.ndarray
    rms_error: float
    max_error: float
    sample_count: int
    triangle_count: int
    region_id: str
    region_name: str
    metadata: dict[str, object] = field(default_factory=dict)


def fit_plane_to_region(
    mesh: TriangleMeshData,
    region: RegionSelection,
) -> RegionPlaneFitResult:
    """Fit a least-squares plane to the unique vertices of a mesh region."""

    region_id = str(getattr(region, "id", "") or "")
    region_name = str(getattr(region, "name", "") or "")
    if mesh is None:
        return _failure("No mesh is available for plane fitting.", region_id, region_name)
    if region is None:
        return _failure("No region is available for plane fitting.", "", "")

    try:
        vertices = np.asarray(mesh.vertices, dtype=float).reshape((-1, 3))
        triangles = np.asarray(mesh.triangles, dtype=int).reshape((-1, 3))
    except (AttributeError, TypeError, ValueError):
        return _failure("Region plane fit requires a valid triangle mesh.", region_id, region_name)
    if len(vertices) == 0 or len(triangles) == 0:
        return _failure("Region plane fit requires a non-empty mesh.", region_id, region_name)

    requested_indices = tuple(getattr(region, "triangle_indices", ()) or ())
    valid_triangle_indices: list[int] = []
    invalid_triangle_count = 0
    vertex_indices: set[int] = set()
    for raw_index in requested_indices:
        try:
            triangle_index = int(raw_index)
        except (TypeError, ValueError):
            invalid_triangle_count += 1
            continue
        if triangle_index < 0 or triangle_index >= len(triangles):
            invalid_triangle_count += 1
            continue
        triangle = triangles[triangle_index]
        if np.any(triangle < 0) or np.any(triangle >= len(vertices)):
            invalid_triangle_count += 1
            continue
        valid_triangle_indices.append(triangle_index)
        vertex_indices.update(int(vertex_index) for vertex_index in triangle)

    if not valid_triangle_indices:
        return _failure(
            "Region contains no valid triangles for plane fitting.",
            region_id,
            region_name,
            metadata={"invalid_triangle_count": invalid_triangle_count},
        )

    ordered_vertex_indices = sorted(vertex_indices)
    points = vertices[ordered_vertex_indices]
    finite_mask = np.all(np.isfinite(points), axis=1)
    finite_points = points[finite_mask]
    if len(finite_points) < 3:
        return _failure(
            "Region plane fit requires at least 3 usable non-collinear points.",
            region_id,
            region_name,
            sample_count=int(len(finite_points)),
            triangle_count=len(valid_triangle_indices),
            metadata={"invalid_triangle_count": invalid_triangle_count},
        )

    origin = np.mean(finite_points, axis=0)
    centered = finite_points - origin
    try:
        _left, singular_values, _right = np.linalg.svd(centered, full_matrices=False)
    except np.linalg.LinAlgError:
        return _failure(
            "Region plane fit failed during plane estimation.",
            region_id,
            region_name,
            sample_count=int(len(finite_points)),
            triangle_count=len(valid_triangle_indices),
        )

    extent = float(np.max(np.ptp(finite_points, axis=0)))
    rank_tolerance = max(extent * 1.0e-12, 1.0e-12)
    if len(singular_values) < 2 or float(singular_values[1]) <= rank_tolerance:
        return _failure(
            "Region is degenerate; usable points are collinear or coincident.",
            region_id,
            region_name,
            sample_count=int(len(finite_points)),
            triangle_count=len(valid_triangle_indices),
            metadata={"invalid_triangle_count": invalid_triangle_count},
        )

    covariance = centered.T @ centered
    try:
        eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    except np.linalg.LinAlgError:
        return _failure(
            "Region plane fit failed during plane estimation.",
            region_id,
            region_name,
            sample_count=int(len(finite_points)),
            triangle_count=len(valid_triangle_indices),
        )
    normal = _canonical_unit_vector(eigenvectors[:, int(np.argmin(eigenvalues))])
    if normal is None:
        return _failure(
            "Region plane fit produced an invalid plane normal.",
            region_id,
            region_name,
            sample_count=int(len(finite_points)),
            triangle_count=len(valid_triangle_indices),
        )

    u_axis, v_axis = _stable_plane_basis(normal)
    signed_distances = centered @ normal
    rms_error = float(np.sqrt(np.mean(np.square(signed_distances))))
    max_error = float(np.max(np.abs(signed_distances)))
    if not np.isfinite(rms_error) or not np.isfinite(max_error):
        return _failure(
            "Region plane fit produced non-finite error metrics.",
            region_id,
            region_name,
            sample_count=int(len(finite_points)),
            triangle_count=len(valid_triangle_indices),
        )

    return RegionPlaneFitResult(
        success=True,
        reason="Plane fit completed.",
        origin=origin.copy(),
        normal=normal,
        u_axis=u_axis,
        v_axis=v_axis,
        rms_error=rms_error,
        max_error=max_error,
        sample_count=int(len(finite_points)),
        triangle_count=len(valid_triangle_indices),
        region_id=region_id,
        region_name=region_name,
        metadata={
            "requested_triangle_count": len(requested_indices),
            "valid_triangle_count": len(valid_triangle_indices),
            "invalid_triangle_count": invalid_triangle_count,
            "discarded_non_finite_point_count": int(np.count_nonzero(~finite_mask)),
            "deduplicated_by_vertex_index": True,
        },
    )


def project_region_boundary_to_plane(
    boundary_points: Sequence[Sequence[float]] | np.ndarray,
    plane_fit: RegionPlaneFitResult,
    *,
    preserve_original_order: bool = True,
) -> np.ndarray:
    """Project ordered 3D boundary points onto a successful fitted plane."""

    del preserve_original_order  # Projection is point-wise and always preserves ordering.
    if not plane_fit.success:
        raise ValueError(f"Cannot project boundary: {plane_fit.reason}")
    try:
        points = np.asarray(boundary_points, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("Region boundary points must be numeric 3D points.") from exc
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("Region boundary points must be an Nx3 array.")
    if not np.all(np.isfinite(points)):
        raise ValueError("Region boundary points must contain only finite values.")

    origin = np.asarray(plane_fit.origin, dtype=float).reshape((3,))
    normal = _canonical_unit_vector(np.asarray(plane_fit.normal, dtype=float).reshape((3,)))
    if normal is None or not np.all(np.isfinite(origin)):
        raise ValueError("Region plane fit contains invalid projection geometry.")

    signed_distances = (points - origin) @ normal
    projected = points - signed_distances[:, None] * normal[None, :]
    if not np.all(np.isfinite(projected)):
        raise ValueError("Projected region boundary contains non-finite values.")
    return np.asarray(projected, dtype=float).reshape((-1, 3))


def region_plane_fit_error_summary(plane_fit: RegionPlaneFitResult) -> str:
    """Return a compact user-facing summary in generic model units."""

    if not plane_fit.success:
        return f"Plane fit failed: {plane_fit.reason}"
    return (
        f"Plane fit: RMS {plane_fit.rms_error:.3f}, "
        f"Max {plane_fit.max_error:.3f} model units"
    )


def _stable_plane_basis(normal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    reference_axes = np.eye(3, dtype=float)
    reference = reference_axes[int(np.argmin(np.abs(reference_axes @ normal)))]
    u_axis = _canonical_unit_vector(np.cross(reference, normal))
    if u_axis is None:
        raise ValueError("Could not construct a stable plane basis.")
    v_axis = np.cross(normal, u_axis)
    v_axis /= float(np.linalg.norm(v_axis))
    return u_axis, v_axis


def _canonical_unit_vector(vector: np.ndarray) -> np.ndarray | None:
    candidate = np.asarray(vector, dtype=float).reshape((3,))
    length = float(np.linalg.norm(candidate))
    if length <= 0.0 or not np.isfinite(length):
        return None
    candidate = candidate / length
    dominant_index = int(np.argmax(np.abs(candidate)))
    if candidate[dominant_index] < 0.0:
        candidate = -candidate
    return candidate


def _failure(
    reason: str,
    region_id: str,
    region_name: str,
    *,
    sample_count: int = 0,
    triangle_count: int = 0,
    metadata: dict[str, object] | None = None,
) -> RegionPlaneFitResult:
    zero = np.zeros(3, dtype=float)
    return RegionPlaneFitResult(
        success=False,
        reason=reason,
        origin=zero.copy(),
        normal=zero.copy(),
        u_axis=zero.copy(),
        v_axis=zero.copy(),
        rms_error=0.0,
        max_error=0.0,
        sample_count=int(sample_count),
        triangle_count=int(triangle_count),
        region_id=region_id,
        region_name=region_name,
        metadata={} if metadata is None else dict(metadata),
    )
