"""Mesh loading helpers for supported triangle mesh files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import open3d as o3d


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
    """A loaded Open3D mesh and its metadata."""

    mesh: o3d.geometry.TriangleMesh
    metadata: MeshMetadata


def _load_open3d():
    try:
        import open3d as o3d
    except ImportError as exc:
        raise SystemExit(
            "Open3D is required for mesh import. Install dependencies with: "
            "python -m pip install -r requirements.txt"
        ) from exc

    return o3d


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

    o3d = _load_open3d()
    mesh = o3d.io.read_triangle_mesh(str(mesh_path))
    if mesh.is_empty():
        raise ValueError(f"Open3D could not read any mesh data from: {mesh_path}")

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
