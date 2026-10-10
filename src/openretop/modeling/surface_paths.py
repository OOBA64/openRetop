"""Paths along the scan's surface: the backbone of Surface Sketch curves.

A curve between two points on the scan runs along the surface itself: the shortest path over
the mesh's edges, found only in a capsule around the two points (fast on an 800k-triangle
scan). It cannot jump to another face or get lost over a hole the way a 3D line pushed onto
the scan can. With ``feature`` > 0 the path is drawn to the scan's creases (body lines,
character lines, the edge of a flare): edges where the surface bends sharply cost less, so the
path rides along them.

Crease strength: the angle between neighbouring vertex normals per unit length (curvature
across the edge), normalised so the scan's strongest few percent of bends count as 1.
"""

from __future__ import annotations

import numpy as np

CREASE_PERCENTILE = 97.0  # bends this strong or more count as a full crease
FEATURE_FLOOR = 0.04  # with feature 1, a full crease costs this fraction of its length
CREASE_RINGS = 4  # normals averaged over this many rings of neighbours
BORDER_RINGS = 3  # vertices this close to the scan's open edge never count as a crease


class SurfaceGraph:
    """The scan's vertex graph (edges weighted by length), for paths along the surface."""

    def __init__(self, vertices: object, triangles: object, normals: object | None = None) -> None:
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        from scipy.spatial import cKDTree

        self.vertices = np.asarray(vertices, dtype=float).reshape(-1, 3)
        triangles = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
        pairs = np.sort(np.vstack([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]]), axis=1)
        self.edges = np.unique(pairs, axis=0)
        self.lengths = np.linalg.norm(self.vertices[self.edges[:, 1]] - self.vertices[self.edges[:, 0]], axis=1)
        self.spacing = float(np.median(self.lengths)) if len(self.lengths) else 1.0
        count = len(self.vertices)
        graph = coo_matrix((np.ones(len(self.edges)), (self.edges[:, 0], self.edges[:, 1])), shape=(count, count))
        _pieces, self.piece = connected_components(graph, directed=False)
        self.tree = cKDTree(self.vertices)
        self._normals = None if normals is None else np.asarray(normals, dtype=float).reshape(-1, 3)
        self._triangles = triangles
        self._crease: np.ndarray | None = None

    # -- creases ---------------------------------------------------------------------------

    @property
    def crease(self) -> np.ndarray:
        """Per vertex, 0 (flat) to 1 (a crease as strong as the scan's strongest bends)."""

        if self._crease is None:
            self._crease = self._compute_crease()
        return self._crease

    def _compute_crease(self) -> np.ndarray:
        from scipy.sparse import coo_matrix

        normals = self._normals
        if normals is None or len(normals) != len(self.vertices):
            from openretop.modeling.scan_selection import vertex_normals

            normals = vertex_normals(self.vertices, self._triangles)
        count = len(self.vertices)
        rows = np.r_[self.edges[:, 0], self.edges[:, 1]]
        columns = np.r_[self.edges[:, 1], self.edges[:, 0]]
        neighbours = coo_matrix((np.ones(len(rows)), (rows, columns)), shape=(count, count)).tocsr()
        # averaging over a few rings takes the scan's noise out: a soft body line on a fender
        # then reads as one crease 560 mm long instead of fragments
        smoothed = normals.copy()
        for _round in range(CREASE_RINGS):
            smoothed = smoothed + neighbours @ smoothed
            smoothed /= np.maximum(np.linalg.norm(smoothed, axis=1, keepdims=True), 1e-15)
        cosine = np.einsum("ij,ij->i", smoothed[self.edges[:, 0]], smoothed[self.edges[:, 1]])
        bend = np.arccos(np.clip(cosine, -1.0, 1.0)) / np.maximum(self.lengths, 1e-12)
        strength = np.zeros(count)
        np.maximum.at(strength, self.edges[:, 0], bend)
        np.maximum.at(strength, self.edges[:, 1], bend)
        # the scan's own open edges bend sharply too, but they are not body lines
        pairs = np.sort(np.vstack([self._triangles[:, [0, 1]], self._triangles[:, [1, 2]], self._triangles[:, [2, 0]]]), axis=1)
        unique, uses = np.unique(pairs, axis=0, return_counts=True)
        border = np.zeros(count, dtype=bool)
        border[unique[uses == 1].ravel()] = True
        for _ring in range(BORDER_RINGS):
            border = border | (neighbours @ border.astype(float) > 0)
        strength[border] = 0.0
        reference = float(np.percentile(strength[~border], CREASE_PERCENTILE)) if np.any(~border) else 1.0
        return np.clip(strength / max(reference, 1e-12), 0.0, 1.0)

    # -- paths -----------------------------------------------------------------------------

    def nearest(self, point: object) -> int:
        _distance, index = self.tree.query(np.asarray(point, dtype=float).reshape(3))
        return int(index)

    def path(self, start: object, end: object, *, feature: float = 0.0) -> np.ndarray | None:
        """Vertices along the surface from ``start`` to ``end`` (exact end points), or None
        when they are on separate pieces of the scan or no path stays near them."""

        p0 = np.asarray(start, dtype=float).reshape(3)
        p1 = np.asarray(end, dtype=float).reshape(3)
        i0, i1 = self.nearest(p0), self.nearest(p1)
        if self.piece[i0] != self.piece[i1]:
            return None
        if i0 == i1:
            return np.vstack([p0, p1])
        chord = float(np.linalg.norm(p1 - p0))
        for widen in (0.6, 1.5):  # a capsule around the two points; wider if the way round is longer
            radius = widen * chord + 12.0 * self.spacing
            found = self._path_in_capsule(p0, p1, i0, i1, radius, feature)
            if found is not None:
                return np.vstack([p0, self.vertices[found[1:-1]], p1]) if len(found) > 2 else np.vstack([p0, p1])
        return None

    def _path_in_capsule(self, p0: np.ndarray, p1: np.ndarray, i0: int, i1: int, radius: float, feature: float) -> list[int] | None:
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import dijkstra

        low, high = np.minimum(p0, p1) - radius, np.maximum(p0, p1) + radius
        box = np.all((self.vertices >= low) & (self.vertices <= high), axis=1)
        candidates = np.nonzero(box)[0]
        axis = p1 - p0
        length2 = max(float(axis @ axis), 1e-24)
        offsets = self.vertices[candidates] - p0
        along = np.clip((offsets @ axis) / length2, 0.0, 1.0)
        distance = np.linalg.norm(offsets - along[:, None] * axis, axis=1)
        inside = np.zeros(len(self.vertices), dtype=bool)
        inside[candidates[distance <= radius]] = True
        inside[[i0, i1]] = True
        keep = inside[self.edges[:, 0]] & inside[self.edges[:, 1]]
        local = np.full(len(self.vertices), -1, dtype=np.int64)
        members = np.nonzero(inside)[0]
        local[members] = np.arange(len(members))
        edges = local[self.edges[keep]]
        weights = self.lengths[keep]
        if feature > 0.0:
            strength = 0.5 * (self.crease[self.edges[keep, 0]] + self.crease[self.edges[keep, 1]])
            weights = weights * (1.0 - min(feature, 1.0) * (1.0 - FEATURE_FLOOR) * strength)
        size = len(members)
        graph = coo_matrix((weights, (edges[:, 0], edges[:, 1])), shape=(size, size)).tocsr()
        source, target = int(local[i0]), int(local[i1])
        distances, previous = dijkstra(graph, directed=False, indices=source, return_predecessors=True)
        if not np.isfinite(distances[target]):
            return None
        route = [target]
        while route[-1] != source:
            route.append(int(previous[route[-1]]))
        return [int(members[index]) for index in reversed(route)]


__all__ = ("SurfaceGraph",)
