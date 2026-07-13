"""Cached ownership for accelerated mesh closest-point queries.

Meshes and query points must be expressed in the same coordinate space. Callers
that transform geometry outside ``TriangleMeshData`` should pass an explicit,
stable revision token representing both mesh identity and that transform.
"""

from __future__ import annotations

from mesh.spatial_index import MeshClosestPointResult, MeshSpatialIndex
from mesh.triangle_mesh import TriangleMeshData


class MeshQueryService:
    def __init__(self) -> None:
        self._index: MeshSpatialIndex | None = None
        self._cache_key: object | None = None
        self._cache_hit = False
        self._index_build_count = 0
        self._last_query_time = 0.0
        self._queried_point_count = 0

    def get_index(
        self,
        mesh: TriangleMeshData,
        *,
        mesh_revision: object | None = None,
    ) -> MeshSpatialIndex:
        cache_key = _mesh_cache_key(mesh, mesh_revision)
        if self._index is not None and self._cache_key == cache_key:
            self._cache_hit = True
            return self._index

        self._cache_hit = False
        self._index = MeshSpatialIndex.from_mesh(
            mesh,
            source_signature=cache_key,
        )
        self._cache_key = cache_key
        self._index_build_count += 1
        return self._index

    def invalidate(self) -> None:
        self._index = None
        self._cache_key = None
        self._cache_hit = False

    def query_closest_points(
        self,
        mesh: TriangleMeshData,
        points: object,
        *,
        mesh_revision: object | None = None,
        max_distance: float | None = None,
        preserve_missed_points: bool = True,
    ) -> MeshClosestPointResult:
        index = self.get_index(mesh, mesh_revision=mesh_revision)
        result = index.query_closest_points(
            points,
            max_distance=max_distance,
            preserve_missed_points=preserve_missed_points,
        )
        self._last_query_time = result.query_time_seconds
        self._queried_point_count = result.queried_point_count
        return result

    @property
    def diagnostics(self) -> dict[str, object]:
        index = self._index
        return {
            "cache_hit": bool(self._cache_hit),
            "index_build_count": int(self._index_build_count),
            "last_build_time": 0.0 if index is None else index.build_time_seconds,
            "last_query_time": float(self._last_query_time),
            "triangle_count": 0 if index is None else index.triangle_count,
            "queried_point_count": int(self._queried_point_count),
            "backend": "" if index is None else "vtkStaticCellLocator",
            "source_signature": None if index is None else index.source_signature,
        }


def _mesh_cache_key(mesh: TriangleMeshData, mesh_revision: object | None) -> object:
    if mesh_revision is None:
        return ("mesh_identity", id(mesh))
    return ("mesh_revision", _stable_revision_value(mesh_revision))


def _stable_revision_value(value: object) -> object:
    try:
        hash(value)
    except TypeError:
        return ("revision_identity", id(value))
    return value


DEFAULT_MESH_QUERY_SERVICE = MeshQueryService()
