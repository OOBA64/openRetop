"""Selecting an area of the scan for Fit Surface (S-05): smart select, brush, connected.

The selection is a mask over the triangles of the mesh the user sees and picks (the display
mesh, which may be a decimated copy of a dense scan). ``SourceMapping`` carries it over to the
full-resolution scan for fitting.
"""

from __future__ import annotations

from typing import Any

import numpy as np

DEFAULT_SMART_ANGLE = 5.0  # degrees between neighbouring (smoothed) triangle normals


class ScanSelection:
    """A triangle mask on one mesh, with the lookups the tools need built on first use."""

    def __init__(self, vertices: object, triangles: object) -> None:
        self._source_vertices = vertices  # the caller's arrays, to recognise the same mesh
        self._source_triangles = triangles
        self.vertices = np.asarray(vertices, dtype=float).reshape(-1, 3)
        self.triangles = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
        self.mask = np.zeros(len(self.triangles), dtype=bool)
        self._adjacency: tuple[np.ndarray, np.ndarray] | None = None
        self._centroids: np.ndarray | None = None
        self._normals: np.ndarray | None = None
        self._raw_normals: np.ndarray | None = None
        self._tree: Any = None
        self.revision = 0

    # -- queries -----------------------------------------------------------------------------

    @property
    def count(self) -> int:
        return int(np.count_nonzero(self.mask))

    def triangle_indices(self) -> np.ndarray:
        return np.nonzero(self.mask)[0]

    def matches(self, vertices: object, triangles: object) -> bool:
        """Still the same mesh (identity of the arrays, as the scene caches do)."""

        return vertices is self._source_vertices and triangles is self._source_triangles

    # -- edits -------------------------------------------------------------------------------

    def clear(self) -> None:
        self.mask[:] = False
        self.revision += 1

    def invert(self) -> None:
        self.mask = ~self.mask
        self.revision += 1

    def set_mask(self, mask: object) -> None:
        values = np.asarray(mask, dtype=bool).ravel()
        if len(values) != len(self.triangles):
            raise ValueError("the selection does not match this mesh")
        self.mask = values.copy()
        self.revision += 1

    def smart_select(self, seed: int, angle_degrees: float = DEFAULT_SMART_ANGLE, *, add: bool = True, connected: bool = False) -> int:
        """Grow from ``seed`` across neighbours whose normals turn less than the angle.

        It stops at creases and sharp edges, so one click picks one smooth face of the scan.
        ``connected`` ignores the angle and takes the whole connected piece of the mesh.
        Returns the number of triangles reached.
        """

        if not 0 <= seed < len(self.triangles):
            return 0
        offsets, neighbours = self._adjacency_arrays()
        normals = self._smooth_normals()
        raw = self._face_normals()
        limit = np.cos(np.radians(max(float(angle_degrees), 0.0)))
        reached = np.zeros(len(self.triangles), dtype=bool)
        reached[seed] = True
        frontier = np.array([seed], dtype=np.int64)
        while len(frontier):
            starts, ends = offsets[frontier], offsets[frontier + 1]
            lengths = ends - starts
            origin = np.repeat(frontier, lengths)
            index = np.repeat(starts - np.concatenate([[0], np.cumsum(lengths)[:-1]]), lengths) + np.arange(int(lengths.sum()))
            candidate = neighbours[index]
            fresh = ~reached[candidate]
            origin, candidate = origin[fresh], candidate[fresh]
            if not connected:
                # smoothed normals ride over a scan's noise; raw ones keep a coarse CAD mesh
                # flat (there every triangle touches an edge and its smoothed normal leans)
                smooth = np.einsum("ij,ij->i", normals[origin], normals[candidate]) >= limit
                flat = np.einsum("ij,ij->i", raw[origin], raw[candidate]) >= limit
                candidate = candidate[smooth | flat]
            candidate = np.unique(candidate)
            reached[candidate] = True
            frontier = candidate
        if add:
            self.mask |= reached
        else:
            self.mask &= ~reached
        self.revision += 1
        return int(np.count_nonzero(reached))

    def brush(self, center: object, radius: float, *, add: bool = True, view_direction: object | None = None) -> int:
        """Paint the triangles within ``radius`` of ``center`` (facing the viewer, if given)."""

        tree = self._centroid_tree()
        hits = np.asarray(tree.query_ball_point(np.asarray(center, dtype=float), float(radius)), dtype=np.int64)
        if len(hits) and view_direction is not None:
            towards_viewer = -np.asarray(view_direction, dtype=float)
            hits = hits[self._smooth_normals()[hits] @ towards_viewer > -0.1]
        if add:
            self.mask[hits] = True
        else:
            self.mask[hits] = False
        if len(hits):
            self.revision += 1
        return int(len(hits))

    # -- lookups -----------------------------------------------------------------------------

    def _adjacency_arrays(self) -> tuple[np.ndarray, np.ndarray]:
        if self._adjacency is None:
            from openretop.segmentation import triangle_adjacency

            self._adjacency = triangle_adjacency(self.triangles, len(self.vertices))
        return self._adjacency

    def centroids(self) -> np.ndarray:
        if self._centroids is None:
            self._centroids = self.vertices[self.triangles].mean(axis=1)
        return self._centroids

    def _centroid_tree(self) -> Any:
        if self._tree is None:
            from scipy.spatial import cKDTree

            self._tree = cKDTree(self.centroids())
        return self._tree

    def _face_normals(self) -> np.ndarray:
        if self._raw_normals is None:
            corners = self.vertices[self.triangles]
            face = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
            self._raw_normals = face / np.maximum(np.linalg.norm(face, axis=1, keepdims=True), 1e-15)
        return self._raw_normals

    def _smooth_normals(self) -> np.ndarray:
        """Triangle normals averaged from their vertices: steady on a noisy scan."""

        if self._normals is None:
            vertex = vertex_normals(self.vertices, self.triangles)
            smooth = vertex[self.triangles].mean(axis=1)
            self._normals = smooth / np.maximum(np.linalg.norm(smooth, axis=1, keepdims=True), 1e-15)
        return self._normals



def vertex_normals(vertices: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    """Area-weighted unit vertex normals."""

    corners = vertices[triangles]
    face = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    flat = triangles.ravel()
    repeated = np.repeat(face, 3, axis=0)
    summed = np.column_stack([np.bincount(flat, weights=repeated[:, axis], minlength=len(vertices)) for axis in range(3)])
    return summed / np.maximum(np.linalg.norm(summed, axis=1, keepdims=True), 1e-15)


class SourceMapping:
    """Carries a display-mesh selection over to the full-resolution scan.

    Each source triangle belongs to the display triangle whose centroid is nearest; without a
    decimated proxy the two meshes are the same and the mapping is the identity.
    """

    def __init__(self, display_centroids: np.ndarray, source_vertices: np.ndarray, source_triangles: np.ndarray) -> None:
        self.source_vertices = source_vertices
        self.source_triangles = source_triangles
        if len(display_centroids) == len(source_triangles):
            self.owner: np.ndarray | None = None
        else:
            from scipy.spatial import cKDTree

            centroids = source_vertices[source_triangles].mean(axis=1)
            _distance, self.owner = cKDTree(display_centroids).query(centroids)

    def source_triangles_for(self, display_mask: np.ndarray) -> np.ndarray:
        if self.owner is None:
            return np.nonzero(display_mask)[0]
        return np.nonzero(display_mask[self.owner])[0]


def selected_patch(vertices: np.ndarray, triangles: np.ndarray, chosen: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The chosen triangles as a compact mesh: (points, local triangles, original vertex ids)."""

    picked = triangles[chosen]
    used, inverse = np.unique(picked.ravel(), return_inverse=True)
    return vertices[used], inverse.reshape(-1, 3), used


__all__ = ("DEFAULT_SMART_ANGLE", "ScanSelection", "SourceMapping", "selected_patch", "vertex_normals")
