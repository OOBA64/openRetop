"""Mesh utilities for openRetop."""

from openretop.mesh.loader import LoadedMesh, MeshMetadata, load_mesh
from openretop.mesh.mesh_state import MeshState
from openretop.mesh.query_service import DEFAULT_MESH_QUERY_SERVICE, MeshQueryService
from openretop.mesh.spatial_index import MeshClosestPointResult, MeshSpatialIndex

__all__ = [
    "LoadedMesh",
    "DEFAULT_MESH_QUERY_SERVICE",
    "MeshClosestPointResult",
    "MeshMetadata",
    "MeshQueryService",
    "MeshSpatialIndex",
    "MeshState",
    "load_mesh",
]

