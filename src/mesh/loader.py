"""Mesh loading helpers for supported triangle mesh files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from mesh.triangle_mesh import TriangleMeshData

if TYPE_CHECKING:
    import trimesh

SUPPORTED_EXTENSIONS = {".obj", ".ply", ".stl"}


@dataclass(frozen=True)
class MeshMetadata:
    """Basic facts captured at load time."""

    file_path: Path
    file_name: str
    extension: str
    vertex_count: int
    triangle_count: int
    had_vertex_normals: bool
    had_triangle_normals: bool
    computed_vertex_normals: bool
    computed_triangle_normals: bool


@dataclass(frozen=True)
class LoadedMesh:
    """A loaded triangle mesh and its metadata."""

    mesh: TriangleMeshData
    metadata: MeshMetadata


def _load_trimesh():
    try:
        import trimesh
    except ImportError as exc:
        raise SystemExit(
            "trimesh is required for mesh import. Install dependencies with: "
            "python -m pip install -r requirements.txt"
        ) from exc

    return trimesh


def _resolve_mesh_path(path: str | Path) -> Path:
    mesh_path = Path(path).expanduser()
    try:
        mesh_path = mesh_path.resolve()
    except OSError as exc:
        raise ValueError(f"Could not resolve mesh path: {path}") from exc

    if not mesh_path.exists():
        raise FileNotFoundError(f"Mesh file does not exist: {mesh_path}")

    if not mesh_path.is_file():
        raise ValueError(f"Mesh path is not a file: {mesh_path}")

    return mesh_path


def load_mesh(path: str | Path) -> LoadedMesh:
    """Load a supported triangle mesh file and return it with metadata."""

    mesh_path = _resolve_mesh_path(path)
    extension = mesh_path.suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(
            f"Unsupported mesh format '{mesh_path.suffix}'. Expected one of: {supported}"
        )

    trimesh = _load_trimesh()
    imported = trimesh.load_mesh(str(mesh_path), process=False)
    raw_mesh = _coerce_trimesh(imported, trimesh)
    mesh = _to_triangle_mesh_data(raw_mesh)
    if mesh.is_empty():
        raise ValueError(f"Could not read any mesh data from: {mesh_path}")

    had_vertex_normals = mesh.has_vertex_normals()
    had_triangle_normals = mesh.has_triangle_normals()

    if not had_vertex_normals:
        mesh.compute_vertex_normals()

    if not had_triangle_normals:
        mesh.compute_triangle_normals()

    metadata = MeshMetadata(
        file_path=mesh_path,
        file_name=mesh_path.name,
        extension=extension,
        vertex_count=len(mesh.vertices),
        triangle_count=len(mesh.triangles),
        had_vertex_normals=had_vertex_normals,
        had_triangle_normals=had_triangle_normals,
        computed_vertex_normals=(not had_vertex_normals and mesh.has_vertex_normals()),
        computed_triangle_normals=(
            not had_triangle_normals and mesh.has_triangle_normals()
        ),
    )

    return LoadedMesh(mesh=mesh, metadata=metadata)


def _coerce_trimesh(imported: object, trimesh_module: object) -> trimesh.Trimesh:
    trimesh_type = trimesh_module.Trimesh
    scene_type = trimesh_module.Scene

    if isinstance(imported, trimesh_type):
        return imported

    if isinstance(imported, scene_type):
        geometries = [
            geometry
            for geometry in imported.geometry.values()
            if isinstance(geometry, trimesh_type) and len(geometry.faces) > 0
        ]
        if geometries:
            return trimesh_module.util.concatenate(geometries)

    raise ValueError("Loaded file did not contain a triangle mesh.")


def _to_triangle_mesh_data(raw_mesh: trimesh.Trimesh) -> TriangleMeshData:
    vertices = np.asarray(raw_mesh.vertices, dtype=float)
    faces = np.asarray(raw_mesh.faces, dtype=int)
    if faces.ndim != 2 or faces.shape[1] != 3:
        raise ValueError("Loaded mesh is not triangulated.")

    triangle_normals = None
    try:
        face_normals = np.asarray(raw_mesh.face_normals, dtype=float)
    except (AttributeError, ValueError):
        face_normals = np.zeros((0, 3), dtype=float)
    if face_normals.shape == faces.shape:
        triangle_normals = face_normals.copy()

    return TriangleMeshData(
        vertices=vertices,
        triangles=faces,
        vertex_normals=None,
        triangle_normals=triangle_normals,
    )
