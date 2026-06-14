"""Triangle adjacency and normal-angle region growing utilities."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from itertools import combinations
from typing import Sequence

import numpy as np

from mesh.triangle_mesh import TriangleMeshData


MeshAdjacency = tuple[tuple[int, ...], ...]
_ADJACENCY_CACHE: dict[tuple[int, int, int], MeshAdjacency] = {}


@dataclass(frozen=True)
class RegionGrowResult:
    triangle_indices: tuple[int, ...]
    threshold_degrees: float
    max_triangle_count: int


def build_triangle_adjacency(mesh: TriangleMeshData) -> MeshAdjacency:
    """Build edge-sharing triangle adjacency for a mesh."""

    triangles = _triangle_array(mesh)
    triangle_count = int(len(triangles))
    if triangle_count == 0:
        return tuple()

    neighbors: list[set[int]] = [set() for _ in range(triangle_count)]
    edge_to_triangles: dict[tuple[int, int], list[int]] = {}
    for triangle_index, triangle in enumerate(triangles):
        for edge in (
            (int(triangle[0]), int(triangle[1])),
            (int(triangle[1]), int(triangle[2])),
            (int(triangle[2]), int(triangle[0])),
        ):
            edge_to_triangles.setdefault(tuple(sorted(edge)), []).append(triangle_index)

    for shared_triangles in edge_to_triangles.values():
        if len(shared_triangles) < 2:
            continue
        for first, second in combinations(shared_triangles, 2):
            neighbors[first].add(second)
            neighbors[second].add(first)

    return tuple(tuple(sorted(triangle_neighbors)) for triangle_neighbors in neighbors)


def cached_triangle_adjacency(mesh: TriangleMeshData) -> MeshAdjacency:
    """Return cached adjacency for the current mesh object."""

    triangles = _triangle_array(mesh)
    vertices = _vertex_array(mesh)
    key = (id(mesh), int(len(vertices)), int(len(triangles)))
    adjacency = _ADJACENCY_CACHE.get(key)
    if adjacency is None:
        adjacency = build_triangle_adjacency(mesh)
        _ADJACENCY_CACHE[key] = adjacency
    return adjacency


def triangle_normals(mesh: TriangleMeshData) -> np.ndarray:
    """Return per-triangle unit normals without mutating the mesh."""

    triangles = _triangle_array(mesh)
    if len(triangles) == 0:
        return np.zeros((0, 3), dtype=float)

    stored_normals = getattr(mesh, "triangle_normals", None)
    if stored_normals is not None:
        normals = np.asarray(stored_normals, dtype=float)
        if normals.shape == (len(triangles), 3):
            return _normalized_rows(normals)

    vertices = _vertex_array(mesh)
    if len(vertices) == 0:
        return np.zeros((len(triangles), 3), dtype=float)

    try:
        triangle_points = vertices[triangles]
    except IndexError:
        return np.zeros((len(triangles), 3), dtype=float)

    normals = np.cross(
        triangle_points[:, 1] - triangle_points[:, 0],
        triangle_points[:, 2] - triangle_points[:, 0],
    )
    return _normalized_rows(normals)


def grow_connected_region(
    mesh: TriangleMeshData,
    seed_triangle_index: int | None,
    *,
    threshold_degrees: float = 20.0,
    max_triangle_count: int = 50_000,
    adjacency: MeshAdjacency | None = None,
    normals: np.ndarray | None = None,
) -> RegionGrowResult:
    """Grow a connected triangle region from a seed triangle."""

    triangles = _triangle_array(mesh)
    triangle_count = int(len(triangles))
    if triangle_count == 0 or seed_triangle_index is None:
        return RegionGrowResult(tuple(), float(threshold_degrees), int(max_triangle_count))

    try:
        seed_index = int(seed_triangle_index)
    except (TypeError, ValueError):
        return RegionGrowResult(tuple(), float(threshold_degrees), int(max_triangle_count))
    if seed_index < 0 or seed_index >= triangle_count:
        return RegionGrowResult(tuple(), float(threshold_degrees), int(max_triangle_count))

    cap = max(1, int(max_triangle_count))
    threshold = _finite_float(threshold_degrees, fallback=20.0)
    threshold = max(0.0, min(180.0, threshold))
    normal_array = triangle_normals(mesh) if normals is None else _normalized_rows(normals)
    if len(normal_array) != triangle_count:
        normal_array = triangle_normals(mesh)

    seed_normal = normal_array[seed_index]
    if float(np.linalg.norm(seed_normal)) <= 1e-12:
        return RegionGrowResult((seed_index,), threshold, cap)

    neighbor_map = cached_triangle_adjacency(mesh) if adjacency is None else adjacency
    cos_threshold = float(np.cos(np.deg2rad(threshold)))
    selected: set[int] = {seed_index}
    queue: deque[int] = deque([seed_index])

    while queue and len(selected) < cap:
        current_index = queue.popleft()
        if current_index >= len(neighbor_map):
            continue
        for neighbor_index in neighbor_map[current_index]:
            if neighbor_index in selected or len(selected) >= cap:
                continue
            if neighbor_index < 0 or neighbor_index >= triangle_count:
                continue
            neighbor_normal = normal_array[neighbor_index]
            if float(np.linalg.norm(neighbor_normal)) <= 1e-12:
                continue
            if float(np.dot(seed_normal, neighbor_normal)) < cos_threshold:
                continue
            selected.add(int(neighbor_index))
            queue.append(int(neighbor_index))

    return RegionGrowResult(tuple(sorted(selected)), threshold, cap)


def _triangle_array(mesh: TriangleMeshData) -> np.ndarray:
    triangles = getattr(mesh, "triangles", None)
    if triangles is None:
        return np.zeros((0, 3), dtype=int)
    try:
        return np.asarray(triangles, dtype=int).reshape((-1, 3))
    except ValueError:
        return np.zeros((0, 3), dtype=int)


def _vertex_array(mesh: TriangleMeshData) -> np.ndarray:
    vertices = getattr(mesh, "vertices", None)
    if vertices is None:
        return np.zeros((0, 3), dtype=float)
    try:
        return np.asarray(vertices, dtype=float).reshape((-1, 3))
    except ValueError:
        return np.zeros((0, 3), dtype=float)


def _normalized_rows(values: Sequence[Sequence[float]] | np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        return np.zeros((0, 3), dtype=float)
    try:
        array = array.reshape((-1, 3))
    except ValueError:
        return np.zeros((0, 3), dtype=float)
    lengths = np.linalg.norm(array, axis=1)
    normalized = np.zeros_like(array, dtype=float)
    valid = lengths > 1e-12
    normalized[valid] = array[valid] / lengths[valid, None]
    return normalized


def _finite_float(value: object, *, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    return number if np.isfinite(number) else float(fallback)
