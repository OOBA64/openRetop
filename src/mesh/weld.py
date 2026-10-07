"""Vertex welding for meshes that store each triangle's corners separately."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Relative to the bounding-box diagonal. STL stores float32 corners, so
# coincident corners are bit-identical; this only needs to absorb rounding noise.
DEFAULT_WELD_RELATIVE_TOLERANCE = 1e-6


@dataclass(frozen=True)
class WeldResult:
    vertices: np.ndarray
    triangles: np.ndarray
    tolerance: float
    merged_vertex_count: int
    removed_triangle_count: int


def weld_tolerance(vertices: np.ndarray, relative: float = DEFAULT_WELD_RELATIVE_TOLERANCE) -> float:
    """Return a weld distance scaled to the mesh's bounding-box diagonal."""

    if len(vertices) == 0:
        return 0.0
    diagonal = float(np.linalg.norm(vertices.max(axis=0) - vertices.min(axis=0)))
    return diagonal * float(relative)


def weld_vertices(
    vertices: np.ndarray,
    triangles: np.ndarray,
    tolerance: float | None = None,
) -> WeldResult:
    """Merge vertices closer than ``tolerance`` and drop triangles that collapse.

    Vertices keep first-appearance order and their original coordinates. Merging
    is grid-based, so two points straddling a cell boundary are not merged; for
    scan data that is duplicated bit-for-bit this does not matter.
    """

    vertices = np.asarray(vertices, dtype=float).reshape((-1, 3))
    triangles = np.asarray(triangles, dtype=np.int64).reshape((-1, 3))
    if tolerance is None:
        tolerance = weld_tolerance(vertices)
    if len(vertices) == 0 or tolerance <= 0.0:
        return WeldResult(vertices, triangles, float(tolerance), 0, 0)

    keys = np.round((vertices - vertices.min(axis=0)) / tolerance).astype(np.int64)
    _, first_index, inverse = np.unique(
        keys, axis=0, return_index=True, return_inverse=True
    )
    inverse = np.asarray(inverse).reshape(-1)
    order = np.argsort(first_index, kind="stable")
    rank = np.empty_like(order)
    rank[order] = np.arange(len(order))
    remap = rank[inverse]

    welded_vertices = vertices[first_index[order]]
    welded_triangles = remap[triangles]
    keep = (
        (welded_triangles[:, 0] != welded_triangles[:, 1])
        & (welded_triangles[:, 1] != welded_triangles[:, 2])
        & (welded_triangles[:, 2] != welded_triangles[:, 0])
    )
    removed = int(len(keep) - np.count_nonzero(keep))
    return WeldResult(
        vertices=welded_vertices,
        triangles=welded_triangles[keep],
        tolerance=float(tolerance),
        merged_vertex_count=int(len(vertices) - len(welded_vertices)),
        removed_triangle_count=removed,
    )
