"""Mesh loading helpers for supported triangle mesh files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from openretop.mesh.triangle_mesh import TriangleMeshData
from openretop.mesh.weld import weld_vertices

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
    welded_vertex_count: int = 0
    removed_degenerate_triangle_count: int = 0


class MeshDependencyError(RuntimeError):
    """A library needed to read meshes is not installed."""


@dataclass(frozen=True)
class LoadedMesh:
    """A loaded triangle mesh and its metadata."""

    mesh: TriangleMeshData
    metadata: MeshMetadata


def _load_trimesh():
    try:
        import trimesh
    except ImportError as exc:
        raise MeshDependencyError(
            "trimesh is required for mesh import. Install dependencies with: "
            "python -m pip install -e ."
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
    try:
        # process=False keeps the file's own triangle order; welding is done
        # explicitly below so it is tolerance-scaled and reported.
        imported = trimesh.load_mesh(str(mesh_path), process=False)
    except (ValueError, OSError, IndexError, KeyError, TypeError) as exc:
        raise ValueError(f"Could not read mesh file {mesh_path.name}: {exc}") from exc
    raw_mesh = _coerce_trimesh(imported, trimesh)
    file_had_triangle_normals = _file_supplied_triangle_normals(mesh_path, extension)
    mesh, weld = _to_triangle_mesh_data(raw_mesh)
    if mesh.is_empty():
        raise ValueError(f"Could not read any mesh data from: {mesh_path}")

    had_vertex_normals = mesh.has_vertex_normals()
    had_triangle_normals = file_had_triangle_normals

    if not had_vertex_normals:
        mesh.compute_vertex_normals()

    if not mesh.has_triangle_normals():
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
        welded_vertex_count=weld.merged_vertex_count,
        removed_degenerate_triangle_count=weld.removed_triangle_count,
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


def _file_supplied_triangle_normals(path: Path, extension: str) -> bool:
    """Whether the file itself carries usable facet normals.

    Only STL stores them. trimesh computes ``face_normals`` lazily on first
    access and discards loader-provided ones after ``load_mesh``, so asking it
    cannot tell the difference; peek at the file instead. The loader always
    recomputes normals from the welded geometry either way.
    """

    if extension != ".stl":
        return False
    try:
        with open(path, "rb") as handle:
            head = handle.read(84)
            binary_count = int.from_bytes(head[80:84], "little") if len(head) == 84 else 0
            size = path.stat().st_size
            if len(head) == 84 and size == 84 + 50 * binary_count and binary_count > 0:
                handle.seek(84)
                record = handle.read(12)
                normal = np.frombuffer(record, dtype="<f4")
                return bool(np.any(normal != 0.0))
            handle.seek(0)
            text = handle.read(4096).decode("ascii", errors="ignore")
    except OSError:
        return False
    marker = "facet normal"
    index = text.find(marker)
    if index < 0:
        return False
    try:
        values = [float(v) for v in text[index + len(marker):].split()[:3]]
    except ValueError:
        return False
    return any(v != 0.0 for v in values)


def _to_triangle_mesh_data(raw_mesh: trimesh.Trimesh):
    vertices = np.asarray(raw_mesh.vertices, dtype=float)
    faces = np.asarray(raw_mesh.faces, dtype=int)
    if faces.ndim != 2 or faces.shape[1] != 3:
        raise ValueError("Loaded mesh is not triangulated.")

    weld = weld_vertices(vertices, faces)
    # Normals are recomputed from the welded geometry by the caller so they
    # always match the triangles that survive welding.
    mesh = TriangleMeshData(
        vertices=weld.vertices,
        triangles=weld.triangles,
        vertex_normals=None,
        triangle_normals=None,
    )
    return mesh, weld
