"""Accelerated closest-point queries for immutable triangle meshes."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Sequence

import numpy as np

from mesh.triangle_mesh import TriangleMeshData


VTK_STATIC_CELL_LOCATOR_BACKEND = "vtkStaticCellLocator"
_AREA_TOLERANCE_SQUARED = 1e-24


@dataclass(frozen=True)
class MeshClosestPointResult:
    source_points: np.ndarray
    closest_points: np.ndarray
    distances: np.ndarray
    hit_mask: np.ndarray
    triangle_indices: np.ndarray
    normals: np.ndarray
    queried_point_count: int
    hit_count: int
    missed_count: int
    build_time_seconds: float
    query_time_seconds: float
    backend: str
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        source_points = _point_array(self.source_points)
        point_count = len(source_points)
        object.__setattr__(self, "source_points", source_points)
        object.__setattr__(
            self,
            "closest_points",
            _fixed_point_array(self.closest_points, point_count),
        )
        object.__setattr__(
            self,
            "distances",
            _fixed_vector(self.distances, point_count, dtype=float, default=0.0),
        )
        object.__setattr__(
            self,
            "hit_mask",
            _fixed_vector(self.hit_mask, point_count, dtype=bool, default=False),
        )
        object.__setattr__(
            self,
            "triangle_indices",
            _fixed_vector(self.triangle_indices, point_count, dtype=np.int64, default=-1),
        )
        object.__setattr__(
            self,
            "normals",
            _fixed_point_array(self.normals, point_count),
        )
        object.__setattr__(self, "queried_point_count", point_count)
        hit_count = int(np.count_nonzero(self.hit_mask))
        object.__setattr__(self, "hit_count", hit_count)
        object.__setattr__(self, "missed_count", point_count - hit_count)
        object.__setattr__(
            self,
            "build_time_seconds",
            _finite_non_negative_float(self.build_time_seconds),
        )
        object.__setattr__(
            self,
            "query_time_seconds",
            _finite_non_negative_float(self.query_time_seconds),
        )
        object.__setattr__(self, "backend", str(self.backend))
        object.__setattr__(self, "metadata", dict(self.metadata))


class MeshSpatialIndex:
    """A reusable VTK static-cell locator for one immutable mesh revision."""

    def __init__(
        self,
        *,
        mesh: TriangleMeshData,
        locator: object | None,
        polydata: object | None,
        valid_triangle_indices: np.ndarray,
        valid_triangle_normals: np.ndarray,
        build_time_seconds: float,
        source_signature: object,
        invalid_triangle_count: int,
    ) -> None:
        self._mesh = mesh
        self._locator = locator
        self._polydata = polydata
        self._valid_triangle_indices = np.asarray(
            valid_triangle_indices, dtype=np.int64
        ).reshape((-1,))
        self._valid_triangle_normals = np.asarray(
            valid_triangle_normals, dtype=float
        ).reshape((-1, 3))
        self._build_time_seconds = _finite_non_negative_float(build_time_seconds)
        self._source_signature = source_signature
        self._invalid_triangle_count = max(int(invalid_triangle_count), 0)

    @classmethod
    def from_mesh(
        cls,
        mesh: TriangleMeshData,
        *,
        source_signature: object | None = None,
    ) -> MeshSpatialIndex:
        if not isinstance(mesh, TriangleMeshData):
            raise TypeError("MeshSpatialIndex requires TriangleMeshData.")

        started = perf_counter()
        vertices = np.asarray(mesh.vertices, dtype=float).reshape((-1, 3))
        triangles = np.asarray(mesh.triangles, dtype=np.int64).reshape((-1, 3))
        valid_mask, normals = _valid_triangle_data(vertices, triangles)
        valid_indices = np.flatnonzero(valid_mask).astype(np.int64)
        valid_normals = normals[valid_mask]
        invalid_count = int(len(triangles) - len(valid_indices))
        signature = (
            (id(mesh), len(vertices), len(triangles))
            if source_signature is None
            else source_signature
        )

        locator: object | None = None
        polydata: object | None = None
        if len(valid_indices):
            dependencies = _vtk_dependencies()
            valid_triangles = triangles[valid_indices]
            used_vertex_indices, compact_connectivity = np.unique(
                valid_triangles.ravel(),
                return_inverse=True,
            )
            polydata = _mesh_polydata(
                vertices[used_vertex_indices],
                compact_connectivity.reshape((-1, 3)),
                dependencies=dependencies,
            )
            locator = dependencies["vtkStaticCellLocator"]()
            locator.SetDataSet(polydata)
            locator.BuildLocator()

        return cls(
            mesh=mesh,
            locator=locator,
            polydata=polydata,
            valid_triangle_indices=valid_indices,
            valid_triangle_normals=valid_normals,
            build_time_seconds=perf_counter() - started,
            source_signature=signature,
            invalid_triangle_count=invalid_count,
        )

    @property
    def triangle_count(self) -> int:
        return int(len(self._mesh.triangles))

    @property
    def vertex_count(self) -> int:
        return int(len(self._mesh.vertices))

    @property
    def build_time_seconds(self) -> float:
        return self._build_time_seconds

    @property
    def valid(self) -> bool:
        return self._locator is not None and len(self._valid_triangle_indices) > 0

    @property
    def source_signature(self) -> object:
        return self._source_signature

    def query_closest_points(
        self,
        points: object,
        *,
        max_distance: float | None = None,
        preserve_missed_points: bool = True,
    ) -> MeshClosestPointResult:
        source_points, invalid_point_indices = _query_point_array(points)
        point_count = len(source_points)
        closest_points = source_points.copy() if preserve_missed_points else np.zeros_like(source_points)
        distances = np.zeros(point_count, dtype=float)
        hit_mask = np.zeros(point_count, dtype=bool)
        triangle_indices = np.full(point_count, -1, dtype=np.int64)
        normals = np.zeros((point_count, 3), dtype=float)
        threshold = _optional_positive_float(max_distance)
        threshold_rejected_indices: list[int] = []
        started = perf_counter()

        if self.valid and point_count:
            dependencies = _vtk_dependencies()
            reference = dependencies["reference"]
            invalid_set = set(invalid_point_indices)
            for point_index, source_point in enumerate(source_points):
                if point_index in invalid_set:
                    continue
                closest = [0.0, 0.0, 0.0]
                cell_id = reference(-1)
                sub_id = reference(0)
                distance_squared = reference(0.0)
                self._locator.FindClosestPoint(
                    source_point.tolist(),
                    closest,
                    cell_id,
                    sub_id,
                    distance_squared,
                )
                local_triangle_index = int(cell_id)
                if not (0 <= local_triangle_index < len(self._valid_triangle_indices)):
                    continue
                distance = float(np.sqrt(max(float(distance_squared), 0.0)))
                if not np.isfinite(distance):
                    continue
                distances[point_index] = distance
                if threshold is not None and distance > threshold:
                    threshold_rejected_indices.append(point_index)
                    continue
                closest_points[point_index] = np.asarray(closest, dtype=float)
                hit_mask[point_index] = True
                triangle_indices[point_index] = self._valid_triangle_indices[
                    local_triangle_index
                ]
                normals[point_index] = self._valid_triangle_normals[
                    local_triangle_index
                ]

        query_time = perf_counter() - started
        reason = "ok" if self.valid else "no_valid_triangles"
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
            build_time_seconds=self.build_time_seconds,
            query_time_seconds=query_time,
            backend=VTK_STATIC_CELL_LOCATOR_BACKEND,
            metadata={
                "source_signature": self.source_signature,
                "valid_triangle_count": int(len(self._valid_triangle_indices)),
                "invalid_triangle_count": self._invalid_triangle_count,
                "invalid_query_indices": list(invalid_point_indices),
                "threshold_rejected_indices": threshold_rejected_indices,
                "max_distance": threshold,
                "preserve_missed_points": bool(preserve_missed_points),
                "reason": reason,
            },
        )


def vtk_available() -> bool:
    try:
        _vtk_dependencies()
    except RuntimeError:
        return False
    return True


def _vtk_dependencies() -> dict[str, object]:
    try:
        from vtkmodules.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray
        from vtkmodules.vtkCommonCore import reference, vtkPoints
        from vtkmodules.vtkCommonDataModel import (
            vtkCellArray,
            vtkPolyData,
            vtkStaticCellLocator,
        )
    except ImportError as exc:
        raise RuntimeError(
            "VTK is required for accelerated mesh closest-point queries."
        ) from exc
    return {
        "numpy_to_vtk": numpy_to_vtk,
        "numpy_to_vtkIdTypeArray": numpy_to_vtkIdTypeArray,
        "reference": reference,
        "vtkPoints": vtkPoints,
        "vtkCellArray": vtkCellArray,
        "vtkPolyData": vtkPolyData,
        "vtkStaticCellLocator": vtkStaticCellLocator,
    }


def _mesh_polydata(
    vertices: np.ndarray,
    triangles: np.ndarray,
    *,
    dependencies: dict[str, object],
) -> object:
    polydata = dependencies["vtkPolyData"]()
    vtk_points = dependencies["vtkPoints"]()
    vtk_points.SetData(dependencies["numpy_to_vtk"](vertices, deep=True))
    polydata.SetPoints(vtk_points)

    offsets = np.arange(0, len(triangles) * 3 + 1, 3, dtype=np.int64)
    cells = dependencies["vtkCellArray"]()
    cells.SetData(
        dependencies["numpy_to_vtkIdTypeArray"](offsets, deep=True),
        dependencies["numpy_to_vtkIdTypeArray"](triangles.ravel(), deep=True),
    )
    polydata.SetPolys(cells)
    return polydata


def _valid_triangle_data(
    vertices: np.ndarray,
    triangles: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    if len(triangles) == 0:
        return np.zeros(0, dtype=bool), np.zeros((0, 3), dtype=float)
    index_valid = np.all((triangles >= 0) & (triangles < len(vertices)), axis=1)
    normals = np.zeros((len(triangles), 3), dtype=float)
    if not np.any(index_valid):
        return index_valid, normals
    candidate_indices = np.flatnonzero(index_valid)
    candidate_points = vertices[triangles[candidate_indices]]
    finite = np.all(np.isfinite(candidate_points), axis=(1, 2))
    raw_normals = np.cross(
        candidate_points[:, 1] - candidate_points[:, 0],
        candidate_points[:, 2] - candidate_points[:, 0],
    )
    lengths_squared = np.einsum("ij,ij->i", raw_normals, raw_normals)
    geometry_valid = finite & np.isfinite(lengths_squared) & (
        lengths_squared > _AREA_TOLERANCE_SQUARED
    )
    valid_indices = candidate_indices[geometry_valid]
    if len(valid_indices):
        lengths = np.sqrt(lengths_squared[geometry_valid])
        normals[valid_indices] = raw_normals[geometry_valid] / lengths[:, None]
    valid_mask = np.zeros(len(triangles), dtype=bool)
    valid_mask[valid_indices] = True
    return valid_mask, normals


def _query_point_array(points: object) -> tuple[np.ndarray, list[int]]:
    try:
        values = np.asarray(points, dtype=float)
    except (TypeError, ValueError):
        return np.zeros((0, 3), dtype=float), []
    if values.size == 0:
        return np.zeros((0, 3), dtype=float), []
    try:
        values = values.reshape((-1, 3)).astype(float, copy=True)
    except ValueError:
        return np.zeros((0, 3), dtype=float), []
    finite_mask = np.all(np.isfinite(values), axis=1)
    invalid_indices = np.flatnonzero(~finite_mask).astype(int).tolist()
    values[~finite_mask] = 0.0
    return values, invalid_indices


def _point_array(points: object) -> np.ndarray:
    values, _invalid = _query_point_array(points)
    return values


def _fixed_point_array(values: object, count: int) -> np.ndarray:
    try:
        result = np.asarray(values, dtype=float).reshape((-1, 3))
    except (TypeError, ValueError):
        return np.zeros((count, 3), dtype=float)
    if len(result) != count:
        return np.zeros((count, 3), dtype=float)
    return np.nan_to_num(result, nan=0.0, posinf=0.0, neginf=0.0)


def _fixed_vector(
    values: object,
    count: int,
    *,
    dtype: object,
    default: object,
) -> np.ndarray:
    try:
        result = np.asarray(values, dtype=dtype).reshape((-1,))
    except (TypeError, ValueError):
        return np.full(count, default, dtype=dtype)
    if len(result) != count:
        return np.full(count, default, dtype=dtype)
    if dtype is float:
        result = np.nan_to_num(result, nan=0.0, posinf=0.0, neginf=0.0)
    return result


def _optional_positive_float(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number) or number <= 0.0:
        return None
    return number


def _finite_non_negative_float(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not np.isfinite(number):
        return 0.0
    return max(number, 0.0)
