"""Boundary extraction helpers for selected mesh regions."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from mesh.triangle_mesh import TriangleMeshData
from regions.region_state import RegionSelection


@dataclass(frozen=True)
class RegionBoundaryPolyline:
    points: np.ndarray
    is_closed: bool
    source_region_id: str
    source_mesh_name: str
    metadata: dict[str, object] = field(default_factory=dict)


def extract_region_boundary_polylines(
    mesh: TriangleMeshData,
    region: RegionSelection,
    *,
    weld_tolerance: float | None = None,
) -> list[RegionBoundaryPolyline]:
    vertices = np.asarray(mesh.vertices, dtype=float).reshape((-1, 3))
    triangles = np.asarray(mesh.triangles, dtype=int).reshape((-1, 3))
    selected_indices = _valid_region_triangle_indices(region.triangle_indices, len(triangles))
    if len(vertices) == 0 or not selected_indices:
        return []

    vertex_ids, vertex_points = _welded_vertex_ids(vertices, weld_tolerance)
    edge_counts: dict[tuple[int, int], int] = defaultdict(int)
    for triangle_index in selected_indices:
        triangle = triangles[triangle_index]
        if np.any(triangle < 0) or np.any(triangle >= len(vertices)):
            continue
        welded_triangle = [vertex_ids[int(index)] for index in triangle]
        for edge in (
            (welded_triangle[0], welded_triangle[1]),
            (welded_triangle[1], welded_triangle[2]),
            (welded_triangle[2], welded_triangle[0]),
        ):
            if edge[0] == edge[1]:
                continue
            edge_counts[tuple(sorted(edge))] += 1

    boundary_edges = sorted(edge for edge, count in edge_counts.items() if count == 1)
    if not boundary_edges:
        return []

    polylines: list[RegionBoundaryPolyline] = []
    for path, is_closed in _ordered_boundary_paths(boundary_edges):
        points = _clean_path_points(
            np.asarray([vertex_points[vertex_id] for vertex_id in path], dtype=float),
            is_closed=is_closed,
        )
        if len(points) < (3 if is_closed else 2):
            continue
        polylines.append(
            RegionBoundaryPolyline(
                points=points,
                is_closed=bool(is_closed),
                source_region_id=region.id,
                source_mesh_name=region.source_mesh_name,
                metadata={
                    "source_region_id": region.id,
                    "source_region_name": region.name,
                    "source_mesh_name": region.source_mesh_name,
                    "region_triangle_count": len(selected_indices),
                    "source_region_triangle_count": len(selected_indices),
                    "boundary_vertex_count": int(len(points)),
                    "boundary_point_count": int(len(points)),
                    "boundary_closed": bool(is_closed),
                    "boundary_perimeter": _polyline_perimeter(points, closed=is_closed),
                    "weld_tolerance": weld_tolerance,
                },
            )
        )
    return polylines


def _valid_region_triangle_indices(
    triangle_indices: Sequence[int],
    triangle_count: int,
) -> tuple[int, ...]:
    valid_indices: set[int] = set()
    for index in triangle_indices:
        try:
            triangle_index = int(index)
        except (TypeError, ValueError):
            continue
        if 0 <= triangle_index < triangle_count:
            valid_indices.add(triangle_index)
    return tuple(sorted(valid_indices))


def _welded_vertex_ids(
    vertices: np.ndarray,
    weld_tolerance: float | None,
) -> tuple[dict[int, int], dict[int, np.ndarray]]:
    tolerance = _valid_weld_tolerance(weld_tolerance)
    if tolerance is None:
        return (
            {index: index for index in range(len(vertices))},
            {index: vertices[index].copy() for index in range(len(vertices))},
        )

    ids_by_key: dict[tuple[int, int, int], int] = {}
    vertex_ids: dict[int, int] = {}
    point_sums: dict[int, np.ndarray] = {}
    point_counts: dict[int, int] = {}
    for index, point in enumerate(vertices):
        key = tuple(int(value) for value in np.round(point / tolerance))
        welded_id = ids_by_key.setdefault(key, len(ids_by_key))
        vertex_ids[index] = welded_id
        point_sums[welded_id] = point_sums.get(welded_id, np.zeros(3, dtype=float)) + point
        point_counts[welded_id] = point_counts.get(welded_id, 0) + 1
    return (
        vertex_ids,
        {
            welded_id: point_sums[welded_id] / float(point_counts[welded_id])
            for welded_id in point_sums
        },
    )


def _valid_weld_tolerance(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        tolerance = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(tolerance) or tolerance <= 0.0:
        return None
    return tolerance


def _ordered_boundary_paths(
    boundary_edges: Sequence[tuple[int, int]],
) -> list[tuple[list[int], bool]]:
    unused_edges = {tuple(sorted(edge)) for edge in boundary_edges if edge[0] != edge[1]}
    paths: list[tuple[list[int], bool]] = []
    while unused_edges:
        component_edges = _connected_edge_component(min(unused_edges), unused_edges)
        paths.extend(_trace_component_paths(component_edges))
        unused_edges.difference_update(component_edges)
    return paths


def _connected_edge_component(
    start_edge: tuple[int, int],
    edges: set[tuple[int, int]],
) -> set[tuple[int, int]]:
    adjacency = _edge_adjacency(edges)
    component_edges: set[tuple[int, int]] = set()
    visited_vertices: set[int] = set()
    queue: deque[int] = deque(start_edge)
    while queue:
        vertex_id = queue.popleft()
        if vertex_id in visited_vertices:
            continue
        visited_vertices.add(vertex_id)
        for neighbor_id in adjacency.get(vertex_id, ()):
            edge = tuple(sorted((vertex_id, neighbor_id)))
            if edge not in edges:
                continue
            component_edges.add(edge)
            if neighbor_id not in visited_vertices:
                queue.append(neighbor_id)
    return component_edges


def _trace_component_paths(
    component_edges: set[tuple[int, int]],
) -> list[tuple[list[int], bool]]:
    unused_edges = set(component_edges)
    paths: list[tuple[list[int], bool]] = []
    while unused_edges:
        adjacency = _edge_adjacency(unused_edges)
        degrees = {vertex_id: len(neighbors) for vertex_id, neighbors in adjacency.items()}
        endpoints = sorted(vertex_id for vertex_id, degree in degrees.items() if degree == 1)
        start_vertex = endpoints[0] if endpoints else min(adjacency)
        path, is_closed = _trace_path(start_vertex, unused_edges)
        if len(path) >= 2:
            paths.append((path, is_closed))
    return paths


def _trace_path(
    start_vertex: int,
    unused_edges: set[tuple[int, int]],
) -> tuple[list[int], bool]:
    path = [start_vertex]
    current_vertex = start_vertex
    previous_vertex: int | None = None
    is_closed = False
    while True:
        adjacency = _edge_adjacency(unused_edges)
        candidates = [
            neighbor
            for neighbor in sorted(adjacency.get(current_vertex, ()))
            if previous_vertex is None or neighbor != previous_vertex or len(adjacency[current_vertex]) == 1
        ]
        if not candidates:
            break
        next_vertex = candidates[0]
        edge = tuple(sorted((current_vertex, next_vertex)))
        if edge not in unused_edges:
            break
        unused_edges.remove(edge)
        if next_vertex == start_vertex:
            is_closed = True
            break
        if next_vertex in path:
            path.append(next_vertex)
            break
        path.append(next_vertex)
        previous_vertex, current_vertex = current_vertex, next_vertex
    return path, is_closed


def _edge_adjacency(edges: set[tuple[int, int]]) -> dict[int, list[int]]:
    adjacency: dict[int, set[int]] = defaultdict(set)
    for first, second in edges:
        adjacency[first].add(second)
        adjacency[second].add(first)
    return {
        vertex_id: sorted(neighbor_ids)
        for vertex_id, neighbor_ids in adjacency.items()
    }


def _clean_path_points(points: np.ndarray, *, is_closed: bool) -> np.ndarray:
    if len(points) == 0:
        return points.reshape((0, 3))

    cleaned = [points[0]]
    for point in points[1:]:
        if np.linalg.norm(point - cleaned[-1]) > 1e-12:
            cleaned.append(point)
    if is_closed and len(cleaned) > 1 and np.linalg.norm(cleaned[0] - cleaned[-1]) <= 1e-12:
        cleaned.pop()
    return np.asarray(cleaned, dtype=float).reshape((-1, 3))


def _polyline_perimeter(points: np.ndarray, *, closed: bool) -> float:
    if len(points) < 2:
        return 0.0
    length = float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())
    if closed and len(points) >= 3:
        length += float(np.linalg.norm(points[0] - points[-1]))
    return length
