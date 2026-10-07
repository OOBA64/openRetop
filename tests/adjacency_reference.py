"""Pure-Python reference for build_triangle_adjacency (pre-vectorisation)."""

from __future__ import annotations

from itertools import combinations

import numpy as np


def reference_triangle_adjacency(mesh) -> tuple:
    """Build edge-sharing triangle adjacency for a mesh."""

    triangles = np.asarray(mesh.triangles, dtype=int).reshape((-1, 3))
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
