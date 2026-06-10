"""Display mesh proxy creation for dense source meshes."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from mesh.triangle_mesh import TriangleMeshData


LOW_DENSITY_TRIANGLE_LIMIT = 150_000
MEDIUM_DENSITY_TRIANGLE_LIMIT = 500_000
MEDIUM_DISPLAY_TARGET = 100_000
HIGH_DISPLAY_TARGET = 180_000


@dataclass(frozen=True)
class DisplayMeshResult:
    source_mesh: TriangleMeshData
    display_mesh: TriangleMeshData
    source_triangle_count: int
    display_triangle_count: int
    proxy_enabled: bool


def build_display_mesh(source_mesh: TriangleMeshData) -> DisplayMeshResult:
    """Return an interaction/display mesh while preserving the source mesh."""

    source_triangle_count = len(source_mesh.triangles)
    target_triangle_count = _target_triangle_count(source_triangle_count)
    if target_triangle_count >= source_triangle_count:
        display_mesh = source_mesh.copy()
        proxy_enabled = False
    else:
        display_mesh = _sample_display_mesh(source_mesh, target_triangle_count)
        proxy_enabled = True

    return DisplayMeshResult(
        source_mesh=source_mesh,
        display_mesh=display_mesh,
        source_triangle_count=source_triangle_count,
        display_triangle_count=len(display_mesh.triangles),
        proxy_enabled=proxy_enabled,
    )


def _target_triangle_count(source_triangle_count: int) -> int:
    if source_triangle_count <= LOW_DENSITY_TRIANGLE_LIMIT:
        return source_triangle_count
    if source_triangle_count <= MEDIUM_DENSITY_TRIANGLE_LIMIT:
        return min(MEDIUM_DISPLAY_TARGET, source_triangle_count)
    return min(HIGH_DISPLAY_TARGET, source_triangle_count)


def _sample_display_mesh(
    source_mesh: TriangleMeshData,
    target_triangle_count: int,
) -> TriangleMeshData:
    triangles = np.asarray(source_mesh.triangles, dtype=int)
    if target_triangle_count <= 0 or len(triangles) == 0:
        return TriangleMeshData(
            vertices=np.zeros((0, 3), dtype=float),
            triangles=np.zeros((0, 3), dtype=int),
        )

    face_indices = np.linspace(
        0,
        len(triangles) - 1,
        num=min(int(target_triangle_count), len(triangles)),
        dtype=int,
    )
    face_indices = np.unique(face_indices)
    sampled_faces = triangles[face_indices]
    used_vertices, remapped_faces = np.unique(sampled_faces.ravel(), return_inverse=True)
    remapped_faces = remapped_faces.reshape((-1, 3))
    vertices = np.asarray(source_mesh.vertices, dtype=float)[used_vertices]

    vertex_normals = None
    if source_mesh.has_vertex_normals():
        vertex_normals = np.asarray(source_mesh.vertex_normals, dtype=float)[used_vertices]

    triangle_normals = None
    if source_mesh.has_triangle_normals():
        triangle_normals = np.asarray(source_mesh.triangle_normals, dtype=float)[face_indices]

    return TriangleMeshData(
        vertices=vertices,
        triangles=remapped_faces,
        vertex_normals=vertex_normals,
        triangle_normals=triangle_normals,
    )
