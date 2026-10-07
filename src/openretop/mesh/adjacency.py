"""Triangle adjacency and normal-angle region growing utilities."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from itertools import combinations
from typing import Sequence

import numpy as np

from openretop.mesh.triangle_mesh import TriangleMeshData

MeshAdjacency = tuple[tuple[int, ...], ...]
_CACHE_ATTRIBUTE = "_triangle_adjacency_cache"


@dataclass(frozen=True)
class RegionGrowResult:
    triangle_indices: tuple[int, ...]
    threshold_degrees: float
    max_triangle_count: int


def build_triangle_adjacency(mesh: TriangleMeshData) -> MeshAdjacency:
    """Build edge-sharing triangle adjacency for a mesh.

    Triangles sharing an edge are neighbours; an edge shared by more than two
    triangles (non-manifold) connects all of them. Neighbour tuples are sorted.
    """

    triangles = _triangle_array(mesh)
    triangle_count = int(len(triangles))
    if triangle_count == 0:
        return tuple()

    vertex_span = int(triangles.max()) + 1
    edge_ends = triangles[:, [0, 1, 1, 2, 2, 0]].reshape((-1, 2))
    low = edge_ends.min(axis=1).astype(np.int64)
    high = edge_ends.max(axis=1).astype(np.int64)
    edge_key = low * vertex_span + high
    owner = np.repeat(np.arange(triangle_count), 3)

    order = np.argsort(edge_key, kind="stable")
    key_sorted = edge_key[order]
    owner_sorted = owner[order]
    same_as_next = key_sorted[:-1] == key_sorted[1:]

    first = owner_sorted[:-1][same_as_next]
    second = owner_sorted[1:][same_as_next]
    # Edges shared by 3+ triangles also pair non-adjacent entries of a run.
    run_start = np.flatnonzero(np.concatenate([[True], ~same_as_next]))
    run_length = np.diff(np.concatenate([run_start, [len(key_sorted)]]))
    extra_first: list[int] = []
    extra_second: list[int] = []
    for start, length in zip(run_start[run_length > 2], run_length[run_length > 2]):
        members = owner_sorted[start : start + length].tolist()
        for a, b in combinations(members, 2):
            extra_first.append(a)
            extra_second.append(b)
    if extra_first:
        first = np.concatenate([first, extra_first])
        second = np.concatenate([second, extra_second])

    keep = first != second
    pair_a = np.concatenate([first[keep], second[keep]])
    pair_b = np.concatenate([second[keep], first[keep]])
    if len(pair_a) == 0:
        return tuple(() for _ in range(triangle_count))
    pair_order = np.lexsort((pair_b, pair_a))
    pair_a, pair_b = pair_a[pair_order], pair_b[pair_order]
    distinct = np.concatenate([[True], (pair_a[1:] != pair_a[:-1]) | (pair_b[1:] != pair_b[:-1])])
    pair_a, pair_b = pair_a[distinct], pair_b[distinct]

    offsets = np.searchsorted(pair_a, np.arange(triangle_count + 1)).tolist()
    flat = pair_b.tolist()
    return tuple(tuple(flat[offsets[i] : offsets[i + 1]]) for i in range(triangle_count))


def cached_triangle_adjacency(mesh: TriangleMeshData) -> MeshAdjacency:
    """Return adjacency for ``mesh``, cached on the mesh object itself.

    The entry holds a reference to the triangle array it was built from, so it
    is dropped with the mesh and is rebuilt whenever ``mesh.triangles`` is
    replaced. In-place edits of the triangle array are not detected; call
    ``invalidate_triangle_adjacency`` after making them.
    """

    triangles = getattr(mesh, "triangles", None)
    entry = getattr(mesh, _CACHE_ATTRIBUTE, None)
    if entry is not None and entry[0] is triangles:
        return entry[1]

    adjacency = build_triangle_adjacency(mesh)
    try:
        setattr(mesh, _CACHE_ATTRIBUTE, (triangles, adjacency))
    except AttributeError:
        pass  # mesh type without a writable __dict__: just don't cache
    return adjacency


def invalidate_triangle_adjacency(mesh: TriangleMeshData) -> None:
    """Drop any adjacency cached on ``mesh``."""

    try:
        setattr(mesh, _CACHE_ATTRIBUTE, None)
    except AttributeError:
        pass


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
