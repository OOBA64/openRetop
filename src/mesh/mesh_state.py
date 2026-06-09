"""Central state object for the currently loaded mesh."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from pathlib import Path
from typing import TYPE_CHECKING

from mesh.loader import LoadedMesh, MeshMetadata

if TYPE_CHECKING:
    import open3d as o3d


Vector3 = tuple[float, float, float]
ZERO_VECTOR: Vector3 = (0.0, 0.0, 0.0)


def _to_vector3(values: object) -> Vector3:
    sequence = list(values)  # Open3D vectors and numpy arrays are iterable.
    if len(sequence) < 3:
        return ZERO_VECTOR

    return (float(sequence[0]), float(sequence[1]), float(sequence[2]))


@dataclass
class MeshState:
    """The mesh currently loaded into the application."""

    mesh: o3d.geometry.TriangleMesh | None = None
    file_path: Path | None = None
    file_name: str = ""
    vertex_count: int = 0
    triangle_count: int = 0
    bounding_box_min: Vector3 = ZERO_VECTOR
    bounding_box_max: Vector3 = ZERO_VECTOR
    bounding_box_extent: Vector3 = ZERO_VECTOR
    has_vertex_normals: bool = False
    has_triangle_normals: bool = False
    computed_vertex_normals: bool = False
    computed_triangle_normals: bool = False

    @classmethod
    def from_loaded_mesh(cls, loaded: LoadedMesh) -> MeshState:
        """Build state from a loader result."""

        return cls.from_mesh(
            loaded.mesh,
            file_path=loaded.metadata.file_path,
            metadata=loaded.metadata,
        )

    @classmethod
    def from_mesh(
        cls,
        mesh: o3d.geometry.TriangleMesh,
        *,
        file_path: str | Path | None = None,
        metadata: MeshMetadata | None = None,
    ) -> MeshState:
        """Build state from a mesh object and optional load metadata."""

        bounding_box = mesh.get_axis_aligned_bounding_box()
        resolved_path = Path(file_path) if file_path is not None else None

        return cls(
            mesh=mesh,
            file_path=resolved_path,
            file_name=metadata.file_name
            if metadata is not None
            else (resolved_path.name if resolved_path is not None else ""),
            vertex_count=len(mesh.vertices),
            triangle_count=len(mesh.triangles),
            bounding_box_min=_to_vector3(bounding_box.get_min_bound()),
            bounding_box_max=_to_vector3(bounding_box.get_max_bound()),
            bounding_box_extent=_to_vector3(bounding_box.get_extent()),
            has_vertex_normals=bool(mesh.has_vertex_normals()),
            has_triangle_normals=bool(mesh.has_triangle_normals()),
            computed_vertex_normals=bool(
                metadata.computed_vertex_normals if metadata is not None else False
            ),
            computed_triangle_normals=bool(
                metadata.computed_triangle_normals if metadata is not None else False
            ),
        )

    @property
    def is_loaded(self) -> bool:
        return self.mesh is not None

    @property
    def face_count(self) -> int:
        return self.triangle_count

    @property
    def bounding_box(self) -> tuple[Vector3, Vector3]:
        return (self.bounding_box_min, self.bounding_box_max)

    @property
    def normals_available(self) -> bool:
        return self.has_vertex_normals or self.has_triangle_normals

    @property
    def normals_computed(self) -> bool:
        return self.computed_vertex_normals or self.computed_triangle_normals

    @property
    def approximate_size(self) -> float:
        x_size, y_size, z_size = self.bounding_box_extent
        return sqrt((x_size * x_size) + (y_size * y_size) + (z_size * z_size))
