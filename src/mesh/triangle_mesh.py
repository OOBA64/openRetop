"""Small numpy-backed triangle mesh types used by the app runtime."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class AxisAlignedBounds:
    minimum: np.ndarray
    maximum: np.ndarray

    def get_min_bound(self) -> np.ndarray:
        return self.minimum.copy()

    def get_max_bound(self) -> np.ndarray:
        return self.maximum.copy()

    def get_extent(self) -> np.ndarray:
        return self.maximum - self.minimum

    def get_center(self) -> np.ndarray:
        return (self.minimum + self.maximum) * 0.5

    def get_max_extent(self) -> float:
        extent = self.get_extent()
        return float(np.max(extent)) if len(extent) else 0.0


@dataclass
class TriangleMeshData:
    """Triangle mesh data plus the small API surface the app needs."""

    vertices: np.ndarray
    triangles: np.ndarray
    vertex_normals: np.ndarray | None = None
    triangle_normals: np.ndarray | None = None

    def __post_init__(self) -> None:
        self.vertices = np.asarray(self.vertices, dtype=float).reshape((-1, 3))
        self.triangles = np.asarray(self.triangles, dtype=int).reshape((-1, 3))
        if self.vertex_normals is not None:
            self.vertex_normals = np.asarray(self.vertex_normals, dtype=float).reshape((-1, 3))
        if self.triangle_normals is not None:
            self.triangle_normals = np.asarray(self.triangle_normals, dtype=float).reshape((-1, 3))

    def copy(self) -> TriangleMeshData:
        return TriangleMeshData(
            vertices=self.vertices.copy(),
            triangles=self.triangles.copy(),
            vertex_normals=None if self.vertex_normals is None else self.vertex_normals.copy(),
            triangle_normals=None if self.triangle_normals is None else self.triangle_normals.copy(),
        )

    def is_empty(self) -> bool:
        return len(self.vertices) == 0 or len(self.triangles) == 0

    def is_watertight(self) -> bool:
        return False

    def has_vertex_normals(self) -> bool:
        return self.vertex_normals is not None and len(self.vertex_normals) == len(self.vertices)

    def has_triangle_normals(self) -> bool:
        return self.triangle_normals is not None and len(self.triangle_normals) == len(self.triangles)

    def has_vertex_colors(self) -> bool:
        return False

    def paint_uniform_color(self, _color: list[float]) -> None:
        return None

    def get_axis_aligned_bounding_box(self) -> AxisAlignedBounds:
        if len(self.vertices) == 0:
            zero = np.asarray([0.0, 0.0, 0.0], dtype=float)
            return AxisAlignedBounds(zero, zero)

        return AxisAlignedBounds(
            minimum=np.min(self.vertices, axis=0),
            maximum=np.max(self.vertices, axis=0),
        )

    def compute_vertex_normals(self) -> None:
        self.compute_triangle_normals()
        normals = np.zeros_like(self.vertices, dtype=float)
        if self.triangle_normals is None:
            self.vertex_normals = normals
            return

        for face_index, triangle in enumerate(self.triangles):
            normals[triangle] += self.triangle_normals[face_index]

        lengths = np.linalg.norm(normals, axis=1)
        valid = lengths > 1e-12
        normals[valid] /= lengths[valid, None]
        self.vertex_normals = normals

    def compute_triangle_normals(self) -> None:
        if len(self.triangles) == 0:
            self.triangle_normals = np.zeros((0, 3), dtype=float)
            return

        triangle_points = self.vertices[self.triangles]
        normals = np.cross(
            triangle_points[:, 1] - triangle_points[:, 0],
            triangle_points[:, 2] - triangle_points[:, 0],
        )
        lengths = np.linalg.norm(normals, axis=1)
        valid = lengths > 1e-12
        normals[valid] /= lengths[valid, None]
        normals[~valid] = 0.0
        self.triangle_normals = normals

    def transform(self, matrix: np.ndarray) -> None:
        transform_matrix = np.asarray(matrix, dtype=float).reshape((4, 4))
        points = np.column_stack((self.vertices, np.ones(len(self.vertices))))
        self.vertices = (transform_matrix @ points.T).T[:, :3]

        normal_matrix = transform_matrix[:3, :3]
        if self.vertex_normals is not None:
            self.vertex_normals = _transform_normals(self.vertex_normals, normal_matrix)
        if self.triangle_normals is not None:
            self.triangle_normals = _transform_normals(self.triangle_normals, normal_matrix)

    def translate(self, offset: list[float] | tuple[float, float, float] | np.ndarray) -> None:
        self.vertices = self.vertices + np.asarray(offset, dtype=float)


def _transform_normals(normals: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    transformed = (np.asarray(matrix, dtype=float) @ normals.T).T
    lengths = np.linalg.norm(transformed, axis=1)
    valid = lengths > 1e-12
    transformed[valid] /= lengths[valid, None]
    transformed[~valid] = 0.0
    return transformed
