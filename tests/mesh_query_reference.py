"""Test-only brute-force oracle for accelerated mesh-query correctness tests."""

from __future__ import annotations

import numpy as np

from mesh.spatial_index import MeshClosestPointResult
from mesh.triangle_mesh import TriangleMeshData


REFERENCE_BACKEND = "test-brute-force-reference"


class ReferenceMeshSpatialIndex:
    def __init__(self, mesh: TriangleMeshData) -> None:
        self.mesh = mesh
        self.build_time_seconds = 0.0
        self.triangle_count = len(mesh.triangles)
        self.vertex_count = len(mesh.vertices)
        self.valid = bool(_valid_triangles(mesh)[0].size)
        self.source_signature = ("reference", id(mesh))

    def query_closest_points(
        self,
        points: object,
        *,
        max_distance: float | None = None,
        preserve_missed_points: bool = True,
    ) -> MeshClosestPointResult:
        return reference_query_closest_points(
            self.mesh,
            points,
            max_distance=max_distance,
            preserve_missed_points=preserve_missed_points,
        )


class ReferenceMeshQueryService:
    def __init__(self) -> None:
        self._index: ReferenceMeshSpatialIndex | None = None
        self._cache_key: object | None = None
        self.index_build_count = 0
        self.query_count = 0

    def invalidate(self) -> None:
        self._index = None
        self._cache_key = None

    def get_index(
        self,
        mesh: TriangleMeshData,
        *,
        mesh_revision: object | None = None,
    ) -> ReferenceMeshSpatialIndex:
        key = ("revision", mesh_revision) if mesh_revision is not None else ("mesh", id(mesh))
        if self._index is None or self._cache_key != key:
            self._index = ReferenceMeshSpatialIndex(mesh)
            self._cache_key = key
            self.index_build_count += 1
        return self._index

    def query_closest_points(
        self,
        mesh: TriangleMeshData,
        points: object,
        *,
        mesh_revision: object | None = None,
        max_distance: float | None = None,
        preserve_missed_points: bool = True,
    ) -> MeshClosestPointResult:
        self.query_count += 1
        return self.get_index(mesh, mesh_revision=mesh_revision).query_closest_points(
            points,
            max_distance=max_distance,
            preserve_missed_points=preserve_missed_points,
        )

    @property
    def diagnostics(self) -> dict[str, object]:
        return {
            "index_build_count": self.index_build_count,
            "queried_point_count": 0,
            "backend": REFERENCE_BACKEND,
        }


def reference_query_closest_points(
    mesh: TriangleMeshData,
    points: object,
    *,
    max_distance: float | None = None,
    preserve_missed_points: bool = True,
) -> MeshClosestPointResult:
    source_points, invalid_query_indices = _points(points)
    valid_triangle_indices, triangle_points, triangle_normals = _valid_triangles(mesh)
    point_count = len(source_points)
    closest_points = source_points.copy() if preserve_missed_points else np.zeros_like(source_points)
    distances = np.zeros(point_count, dtype=float)
    hit_mask = np.zeros(point_count, dtype=bool)
    triangle_indices = np.full(point_count, -1, dtype=np.int64)
    normals = np.zeros((point_count, 3), dtype=float)
    threshold = _positive_float(max_distance)
    threshold_rejected_indices: list[int] = []
    invalid_set = set(invalid_query_indices)

    for point_index, point in enumerate(source_points):
        if point_index in invalid_set:
            continue
        best_distance_squared = float("inf")
        best_local_index = -1
        best_point = point.copy()
        for local_index, triangle in enumerate(triangle_points):
            candidate = _closest_point_on_triangle(
                point,
                triangle[0],
                triangle[1],
                triangle[2],
            )
            distance_squared = float(np.dot(candidate - point, candidate - point))
            if distance_squared < best_distance_squared:
                best_distance_squared = distance_squared
                best_local_index = local_index
                best_point = candidate
        if best_local_index < 0:
            continue
        distance = float(np.sqrt(max(best_distance_squared, 0.0)))
        distances[point_index] = distance
        if threshold is not None and distance > threshold:
            threshold_rejected_indices.append(point_index)
            continue
        closest_points[point_index] = best_point
        hit_mask[point_index] = True
        triangle_indices[point_index] = valid_triangle_indices[best_local_index]
        normals[point_index] = triangle_normals[best_local_index]

    return MeshClosestPointResult(
        source_points=source_points,
        closest_points=closest_points,
        distances=distances,
        hit_mask=hit_mask,
        triangle_indices=triangle_indices,
        normals=normals,
        queried_point_count=point_count,
        hit_count=int(np.count_nonzero(hit_mask)),
        missed_count=int(point_count - np.count_nonzero(hit_mask)),
        build_time_seconds=0.0,
        query_time_seconds=0.0,
        backend=REFERENCE_BACKEND,
        metadata={
            "reason": "ok" if len(valid_triangle_indices) else "no_valid_triangles",
            "valid_triangle_count": len(valid_triangle_indices),
            "invalid_triangle_count": len(mesh.triangles) - len(valid_triangle_indices),
            "invalid_query_indices": invalid_query_indices,
            "threshold_rejected_indices": threshold_rejected_indices,
            "max_distance": threshold,
        },
    )


def _valid_triangles(
    mesh: TriangleMeshData,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    vertices = np.asarray(mesh.vertices, dtype=float).reshape((-1, 3))
    triangles = np.asarray(mesh.triangles, dtype=np.int64).reshape((-1, 3))
    valid_indices: list[int] = []
    points: list[np.ndarray] = []
    normals: list[np.ndarray] = []
    for index, triangle in enumerate(triangles):
        if not np.all((triangle >= 0) & (triangle < len(vertices))):
            continue
        triangle_points = vertices[triangle]
        if not np.all(np.isfinite(triangle_points)):
            continue
        normal = np.cross(
            triangle_points[1] - triangle_points[0],
            triangle_points[2] - triangle_points[0],
        )
        length = float(np.linalg.norm(normal))
        if not np.isfinite(length) or length <= 1e-12:
            continue
        valid_indices.append(index)
        points.append(triangle_points)
        normals.append(normal / length)
    return (
        np.asarray(valid_indices, dtype=np.int64),
        np.asarray(points, dtype=float).reshape((-1, 3, 3)),
        np.asarray(normals, dtype=float).reshape((-1, 3)),
    )


def _points(points: object) -> tuple[np.ndarray, list[int]]:
    try:
        values = np.asarray(points, dtype=float)
    except (TypeError, ValueError):
        return np.zeros((0, 3), dtype=float), []
    if values.size == 0:
        return np.zeros((0, 3), dtype=float), []
    try:
        values = values.reshape((-1, 3)).copy()
    except ValueError:
        return np.zeros((0, 3), dtype=float), []
    finite = np.all(np.isfinite(values), axis=1)
    invalid_indices = np.flatnonzero(~finite).astype(int).tolist()
    values[~finite] = 0.0
    return values, invalid_indices


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
        return a + (d1 / (d1 - d3)) * ab
    cp = point - c
    d5 = float(np.dot(ab, cp))
    d6 = float(np.dot(ac, cp))
    if d6 >= 0.0 and d5 <= d6:
        return c.copy()
    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        return a + (d2 / (d2 - d6)) * ac
    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        return b + ((d4 - d3) / ((d4 - d3) + (d5 - d6))) * (c - b)
    denominator = va + vb + vc
    if abs(denominator) <= 1e-12:
        return a.copy()
    return a + ab * (vb / denominator) + ac * (vc / denominator)


def _positive_float(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) and number > 0.0 else None
