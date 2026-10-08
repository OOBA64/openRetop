"""3D Sketch on the scan: points clicked on the mesh, curves through them lying on the surface.

The ExModel way of modelling organic parts: click points on the scan; each curve passes
through its points and is pulled onto the scan between them, so it never floats above the
surface or overshoots past its ends. Curves share points (snapping to a point reuses it), so
they join into a network: two or more open curves loft into a surface, a closed curve or a
loop of curves becomes a face fitted to the scan inside it.

Pure NumPy/SciPy; the mesh is given as arrays (world coordinates).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

import numpy as np

# -- projection onto the scan -----------------------------------------------------------------


class MeshProjector:
    """Closest points on a triangle mesh (nearest triangles by centroid, exact point-triangle)."""

    def __init__(self, vertices: object, triangles: object) -> None:
        from scipy.spatial import cKDTree

        self.vertices = np.asarray(vertices, dtype=float).reshape(-1, 3)
        self.triangles = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
        corners = self.vertices[self.triangles]
        self._a, self._b, self._c = corners[:, 0], corners[:, 1], corners[:, 2]
        self.centroids = corners.mean(axis=1)
        self._tree = cKDTree(self.centroids)
        edges = np.linalg.norm(corners[:, [1, 2, 0]] - corners, axis=2)
        self.spacing = float(np.median(edges)) if len(edges) else 1.0
        normals = np.cross(self._b - self._a, self._c - self._a)
        self.triangle_normals = normals / np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-15)

    def project(self, points: object, candidates: int = 12) -> tuple[np.ndarray, np.ndarray]:
        """(closest points, their triangles) for each point."""

        query = np.asarray(points, dtype=float).reshape(-1, 3)
        if len(query) == 0:
            return np.zeros((0, 3)), np.zeros(0, dtype=np.int64)
        k = min(candidates, len(self.centroids))
        _distance, nearest = self._tree.query(query, k=k)
        nearest = np.asarray(nearest).reshape(len(query), k)
        closest = closest_points_on_triangles(
            query[:, None, :], self._a[nearest], self._b[nearest], self._c[nearest]
        )
        distance = np.linalg.norm(closest - query[:, None, :], axis=2)
        best = np.argmin(distance, axis=1)
        rows = np.arange(len(query))
        return closest[rows, best], nearest[rows, best]

    def normals_at(self, points: object) -> np.ndarray:
        """Scan normal at each (on-scan) point, averaged over about a triangle's width."""

        query = np.asarray(points, dtype=float).reshape(-1, 3)
        _closest, triangle = self.project(query)
        result = np.empty_like(query)
        for index, (point, own) in enumerate(zip(query, triangle, strict=True)):
            near = np.asarray(self._tree.query_ball_point(point, 2.0 * self.spacing), dtype=np.int64)
            normals = self.triangle_normals[near] if len(near) else self.triangle_normals[[own]]
            reference = self.triangle_normals[own]
            normals = np.where((normals @ reference)[:, None] < 0, -normals, normals)
            mean = normals.sum(axis=0)
            result[index] = mean / max(float(np.linalg.norm(mean)), 1e-15)
        return result

    def project_along(self, points: object, directions: object, radius: float) -> np.ndarray:
        """Move each point to where a line along its direction meets the scan (the nearest
        crossing either way); the closest point when the line misses within ``radius``.

        A curve's straight run between two points on a curved face lies inside the part, and
        the plain closest point from there can be on another face entirely (a chord under a
        casting's side snapped to its top, 11 mm away). The line along the face normal comes
        out through the face the curve is drawn on.
        """

        query = np.asarray(points, dtype=float).reshape(-1, 3)
        rays = np.asarray(directions, dtype=float).reshape(-1, 3)
        result = np.empty_like(query)
        previous: np.ndarray | None = None
        for index, (origin, direction) in enumerate(zip(query, rays, strict=True)):
            hit = None
            if previous is not None:
                # guided: consecutive samples hit the scan close together, so look near the
                # last hit first (a few dozen triangles instead of a ball as wide as the
                # chord is deep: a curve preview went from 90-500 ms to a few ms)
                step = float(np.linalg.norm(origin - query[index - 1]))
                near = np.asarray(self._tree.query_ball_point(previous, max(3.0 * self.spacing, 3.0 * step)), dtype=np.int64)
                if len(near):
                    hit = _ray_hit(origin, direction, self._a[near], self._b[near], self._c[near])
            if hit is None:
                near = np.asarray(self._tree.query_ball_point(origin, radius), dtype=np.int64)
                hit = _ray_hit(origin, direction, self._a[near], self._b[near], self._c[near]) if len(near) else None
            if hit is None:
                closest, _triangle = self.project(origin.reshape(1, 3))
                hit = closest[0]
            result[index] = hit
            previous = hit
        return result


def _ray_hit(origin: np.ndarray, direction: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray | None:
    """Nearest crossing (either direction) of the line origin + t * direction with the
    triangles (Moller-Trumbore, vectorized over the triangles)."""

    edge1, edge2 = b - a, c - a
    pvec = np.cross(direction, edge2)
    determinant = np.einsum("ij,ij->i", edge1, pvec)
    usable = np.abs(determinant) > 1e-12
    inverse = np.where(usable, 1.0 / np.where(usable, determinant, 1.0), 0.0)
    tvec = origin - a
    u = np.einsum("ij,ij->i", tvec, pvec) * inverse
    qvec = np.cross(tvec, edge1)
    v = (qvec @ direction) * inverse
    t = np.einsum("ij,ij->i", edge2, qvec) * inverse
    inside = usable & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9)
    if not np.any(inside):
        return None
    candidates = np.nonzero(inside)[0]
    best = candidates[np.argmin(np.abs(t[candidates]))]
    return origin + t[best] * direction


def closest_points_on_triangles(p: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Closest point to ``p`` on triangle (a, b, c), vectorized (Ericson, Real-Time Collision
    Detection 5.1.5). Shapes broadcast; the last axis is xyz."""

    p, a, b, c = np.broadcast_arrays(p, a, b, c)
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = _dot(ab, ap), _dot(ac, ap)
    bp = p - b
    d3, d4 = _dot(ab, bp), _dot(ac, bp)
    cp = p - c
    d5, d6 = _dot(ab, cp), _dot(ac, cp)
    va = d3 * d6 - d5 * d4
    vb = d5 * d2 - d1 * d6
    vc = d1 * d4 - d3 * d2
    with np.errstate(divide="ignore", invalid="ignore"):
        denominator = va + vb + vc
        v = np.where(denominator != 0, vb / denominator, 0.0)
        w = np.where(denominator != 0, vc / denominator, 0.0)
        result = a + ab * v[..., None] + ac * w[..., None]  # inside the face
        # edge regions
        t_ab = np.where(d1 - d3 != 0, d1 / (d1 - d3), 0.0)
        on_ab = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
        result = np.where(on_ab[..., None], a + ab * t_ab[..., None], result)
        t_ac = np.where(d2 - d6 != 0, d2 / (d2 - d6), 0.0)
        on_ac = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
        result = np.where(on_ac[..., None], a + ac * t_ac[..., None], result)
        t_bc = np.where((d4 - d3) + (d5 - d6) != 0, (d4 - d3) / ((d4 - d3) + (d5 - d6)), 0.0)
        on_bc = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
        result = np.where(on_bc[..., None], b + (c - b) * t_bc[..., None], result)
    # vertex regions
    result = np.where(((d1 <= 0) & (d2 <= 0))[..., None], a, result)
    result = np.where(((d3 >= 0) & (d4 <= d3))[..., None], b, result)
    result = np.where(((d6 >= 0) & (d5 <= d6))[..., None], c, result)
    return result


def _dot(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.einsum("...i,...i->...", x, y)


# -- curves through points, on the scan -------------------------------------------------------


def catmull_rom(
    points: object, *, closed: bool = False, samples_per_unit: float = 2.0, minimum: int = 6
) -> tuple[np.ndarray, np.ndarray]:
    """A centripetal Catmull-Rom curve through the points: (samples, index of each point).

    Centripetal parameterization never loops or overshoots between unevenly spaced points
    (Yuksel et al. 2011), which is what made curves "curve weird" past their points.
    """

    control = np.asarray(points, dtype=float).reshape(-1, 3)
    if len(control) < 2:
        return control.copy(), np.arange(len(control))
    if closed:
        extended = np.vstack([control[-1:], control, control[:2]])
        spans = len(control)
    else:
        # phantom end points continue the end segments straight on
        extended = np.vstack([2 * control[0] - control[1], control, 2 * control[-1] - control[-2]])
        spans = len(control) - 1
    pieces, starts, offset = [], [], 0
    for span in range(spans):
        p0, p1, p2, p3 = extended[span : span + 4]
        count = max(minimum, int(np.ceil(np.linalg.norm(p2 - p1) * samples_per_unit)))
        t = np.linspace(0.0, 1.0, count, endpoint=False)
        pieces.append(_centripetal_segment(p0, p1, p2, p3, t))
        starts.append(offset)
        offset += count
    pieces.append(control[:1] if closed else control[-1:])
    if not closed:
        starts.append(offset)
    return np.vstack(pieces), np.asarray(starts, dtype=np.int64)


def _centripetal_segment(p0: np.ndarray, p1: np.ndarray, p2: np.ndarray, p3: np.ndarray, t: np.ndarray) -> np.ndarray:
    def knot(previous: float, a: np.ndarray, b: np.ndarray) -> float:
        return previous + max(float(np.linalg.norm(b - a)) ** 0.5, 1e-9)

    t0 = 0.0
    t1 = knot(t0, p0, p1)
    t2 = knot(t1, p1, p2)
    t3 = knot(t2, p2, p3)
    u = (t1 + (t2 - t1) * t)[:, None]
    a1 = (t1 - u) / (t1 - t0) * p0 + (u - t0) / (t1 - t0) * p1
    a2 = (t2 - u) / (t2 - t1) * p1 + (u - t1) / (t2 - t1) * p2
    a3 = (t3 - u) / (t3 - t2) * p2 + (u - t2) / (t3 - t2) * p3
    b1 = (t2 - u) / (t2 - t0) * a1 + (u - t0) / (t2 - t0) * a2
    b2 = (t3 - u) / (t3 - t1) * a2 + (u - t1) / (t3 - t1) * a3
    return (t2 - u) / (t2 - t1) * b1 + (u - t1) / (t2 - t1) * b2


def curve_on_mesh(points: object, projector: MeshProjector, *, closed: bool = False, smoothing: int = 1) -> np.ndarray:
    """A polyline through ``points`` that lies on the scan.

    The curve through the points (centripetal Catmull-Rom) is sampled about every half
    triangle; each sample is moved onto the scan along the surface normal, blended between
    its span's two points. That keeps the line on the face it is drawn on even where the
    straight run between two points dips deep inside the part. Light smoothing (the points
    held) then takes the scan's noise out of the line. The line passes exactly through the
    (projected) points, so curves that share a point meet there, and it ends at its end
    points: nothing extends past them.
    """

    control, _triangles = projector.project(points)
    if len(control) < 2:
        return control
    normals = projector.normals_at(control)
    line, held = catmull_rom(control, closed=closed, samples_per_unit=2.0 / max(projector.spacing, 1e-9))
    directions = np.empty_like(line)
    bounds = list(held) + ([len(line) - 1] if held[-1] != len(line) - 1 else [])
    radius = 2.0 * projector.spacing
    for span, (start, end) in enumerate(zip(bounds[:-1], bounds[1:], strict=True)):
        # no "fix" for normals more than 90 degrees apart: a face can turn that much between
        # two points (flipping one sent the middle of such a curve to the wrong side)
        n0, n1 = normals[span % len(normals)], normals[(span + 1) % len(normals)]
        t = np.linspace(0.0, 1.0, end - start + 1)[:, None]
        blend = n0 * (1 - t) + n1 * t
        directions[start : end + 1] = blend / np.maximum(np.linalg.norm(blend, axis=1, keepdims=True), 1e-15)
        chord = float(np.linalg.norm(line[end] - line[start]))
        radius = max(radius, 0.5 * chord + 2.0 * projector.spacing)
    line = projector.project_along(line, directions, radius)
    line[held] = control
    for _round in range(max(0, smoothing)):
        smoothed = line.copy()
        smoothed[1:-1] = 0.5 * line[1:-1] + 0.25 * (line[:-2] + line[2:])
        line = projector.project_along(smoothed, directions, 3.0 * projector.spacing)
        line[held] = control
    if closed:
        line[-1] = control[0]
    return line


# -- the sketch -------------------------------------------------------------------------------


@dataclass
class SketchCurve:
    id: str
    name: str
    nodes: list[str]  # control points in order; shared points join curves
    closed: bool = False
    polyline: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))
    visible: bool = True


@dataclass
class Sketch:
    nodes: dict[str, np.ndarray] = field(default_factory=dict)  # node id -> position on the scan
    curves: list[SketchCurve] = field(default_factory=list)
    counter: int = 0

    def copy(self) -> Sketch:
        return copy.deepcopy(self)

    def new_node(self, position: object) -> str:
        self.counter += 1
        node_id = f"p{self.counter}"
        self.nodes[node_id] = np.asarray(position, dtype=float).reshape(3).copy()
        return node_id

    def curve(self, curve_id: str) -> SketchCurve | None:
        return next((curve for curve in self.curves if curve.id == curve_id), None)

    def add_curve(self, nodes: list[str], projector: MeshProjector, *, closed: bool = False, name: str | None = None) -> SketchCurve:
        if len(nodes) < 2:
            raise ValueError("a curve needs at least two points")
        self.counter += 1
        curve = SketchCurve(f"c{self.counter}", name or self.next_name(), list(nodes), closed)
        self.rebuild(curve, projector)
        self.curves.append(curve)
        return curve

    def next_name(self) -> str:
        taken = {curve.name for curve in self.curves}
        number = 1
        while f"Curve {number}" in taken:
            number += 1
        return f"Curve {number}"

    def rebuild(self, curve: SketchCurve, projector: MeshProjector) -> None:
        points = np.array([self.nodes[node] for node in curve.nodes])
        curve.polyline = curve_on_mesh(points, projector, closed=curve.closed)

    def move_node(self, node_id: str, position: object, projector: MeshProjector) -> list[str]:
        """Move a point (projected onto the scan); every curve through it follows."""

        snapped, _triangle = projector.project(np.asarray(position, dtype=float).reshape(1, 3))
        self.nodes[node_id] = snapped[0]
        moved = [curve for curve in self.curves if node_id in curve.nodes]
        for curve in moved:
            self.rebuild(curve, projector)
        return [curve.id for curve in moved]

    def remove_curves(self, curve_ids: object) -> int:
        wanted = {str(value) for value in curve_ids}  # type: ignore[attr-defined]
        before = len(self.curves)
        self.curves = [curve for curve in self.curves if curve.id not in wanted]
        used = {node for curve in self.curves for node in curve.nodes}
        self.nodes = {node: position for node, position in self.nodes.items() if node in used}
        return before - len(self.curves)

    def remove_node(self, node_id: str, projector: MeshProjector) -> int:
        """Take a point out of every curve through it (a curve left with one point goes)."""

        changed = 0
        for curve in list(self.curves):
            if node_id not in curve.nodes:
                continue
            curve.nodes = [node for node in curve.nodes if node != node_id]
            changed += 1
            if len(curve.nodes) < 2 or (curve.closed and len(curve.nodes) < 3):
                self.curves.remove(curve)
            else:
                self.rebuild(curve, projector)
        self.nodes.pop(node_id, None)
        return changed

    def endpoints(self, curve: SketchCurve) -> tuple[str, str] | None:
        return None if curve.closed else (curve.nodes[0], curve.nodes[-1])


def boundary_loop(sketch: Sketch, curve_ids: list[str]) -> list[tuple[SketchCurve, bool]] | None:
    """Order open curves into a closed chain by their shared end points.

    Returns (curve, reversed) pairs around the loop, or None when they do not close. One
    closed curve is a loop by itself.
    """

    curves = [curve for curve in (sketch.curve(value) for value in curve_ids) if curve is not None]
    if len(curves) == 1 and curves[0].closed:
        return [(curves[0], False)]
    if len(curves) < 2 or any(curve.closed for curve in curves):
        return None
    remaining = curves[1:]
    chain = [(curves[0], False)]
    start, current = curves[0].nodes[0], curves[0].nodes[-1]
    while remaining:
        following = next((curve for curve in remaining if current in (curve.nodes[0], curve.nodes[-1])), None)
        if following is None:
            return None
        reverse = following.nodes[-1] == current
        chain.append((following, reverse))
        current = following.nodes[0] if reverse else following.nodes[-1]
        remaining.remove(following)
    return chain if current == start else None


def loop_polylines(chain: list[tuple[SketchCurve, bool]]) -> list[np.ndarray]:
    return [curve.polyline[::-1] if reverse else curve.polyline for curve, reverse in chain]


def region_inside(projector: MeshProjector, outline: np.ndarray, *, grow: int = 0) -> np.ndarray:
    """Triangles of the scan enclosed by a closed outline drawn on it.

    The outline's triangles are walls; a flood fill from the scan point nearest the outline's
    middle collects the inside. A fill that escapes (a gap in the wall) would reach far
    beyond the outline: then the inside is taken by projection onto the outline's plane.
    """

    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import breadth_first_order

    from openretop.segmentation import triangle_adjacency

    triangles = projector.triangles
    # the wall: every triangle within about a triangle's size of the outline, a solid band
    # (the triangles the outline passes through alone left gaps a fill slipped through)
    dense = _densify(outline, 0.25 * projector.spacing)
    hits = projector._tree.query_ball_point(dense, 0.9 * projector.spacing)
    walls = np.zeros(len(triangles), dtype=bool)
    walls[np.unique(np.concatenate([np.asarray(hit, dtype=np.int64) for hit in hits]))] = True
    offsets, neighbours = triangle_adjacency(triangles, len(projector.vertices))
    ring = np.repeat(np.arange(len(triangles)), np.diff(offsets))
    middle = outline.mean(axis=0)
    _closest, seed_triangle = projector.project(middle.reshape(1, 3))
    seed = int(seed_triangle[0])
    if walls[seed]:
        free = np.nonzero(~walls)[0]
        seed = int(free[np.argmin(np.linalg.norm(projector.centroids[free] - middle, axis=1))])
    keep = ~walls[ring] & ~walls[neighbours]
    graph = csr_matrix((np.ones(int(keep.sum())), (ring[keep], neighbours[keep])), shape=(len(triangles), len(triangles)))
    order = breadth_first_order(graph, seed, directed=False, return_predecessors=False)
    inside = np.zeros(len(triangles), dtype=bool)
    inside[order] = True
    distances = np.linalg.norm(projector.centroids[inside] - middle, axis=1)
    reach = float(np.max(distances)) if len(distances) else 0.0
    size = float(np.linalg.norm(outline.max(axis=0) - outline.min(axis=0)))
    if reach > 0.75 * size + 2 * projector.spacing:
        inside = _inside_by_projection(projector, outline)
    # ``grow`` rings past the outline: a surface fitted to the region then reaches the outline
    # with data on both sides of it
    for _ring in range(max(0, grow)):
        grown = inside.copy()
        grown[neighbours[inside[ring]]] = True
        inside = grown
    return inside


def _inside_by_projection(projector: MeshProjector, outline: np.ndarray) -> np.ndarray:
    center = outline.mean(axis=0)
    _s, _v, axes = np.linalg.svd(outline - center, full_matrices=False)
    flat = (outline - center) @ axes[:2].T
    centroids = (projector.centroids - center) @ axes[:2].T
    height = np.abs((projector.centroids - center) @ axes[2])
    size = float(np.linalg.norm(outline.max(axis=0) - outline.min(axis=0)))
    return _inside_polygon(centroids, flat) & (height < 0.5 * size)


def _inside_polygon(points: np.ndarray, polygon: np.ndarray) -> np.ndarray:
    """Even-odd rule: does a ray to +x cross the polygon an odd number of times."""

    x, y = points[:, 0][:, None], points[:, 1][:, None]
    x1, y1 = polygon[:, 0][None, :], polygon[:, 1][None, :]
    x2, y2 = np.roll(polygon[:, 0], -1)[None, :], np.roll(polygon[:, 1], -1)[None, :]
    straddles = (y1 > y) != (y2 > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        crossing_x = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
    return np.count_nonzero(straddles & (x < crossing_x), axis=1) % 2 == 1


def _densify(polyline: np.ndarray, step: float) -> np.ndarray:
    pieces = [polyline[:1]]
    for start, end in zip(polyline[:-1], polyline[1:], strict=True):
        count = max(1, int(np.ceil(np.linalg.norm(end - start) / max(step, 1e-9))))
        t = np.linspace(0.0, 1.0, count + 1)[1:, None]
        pieces.append(start + (end - start) * t)
    return np.vstack(pieces)


def nearest_on_polylines(polylines: dict[str, np.ndarray], point: object) -> tuple[str | None, float]:
    """The curve passing nearest a point (for picking curves)."""

    target = np.asarray(point, dtype=float)
    best: tuple[str | None, float] = (None, float("inf"))
    for key, line in polylines.items():
        if len(line) == 0:
            continue
        distance = float(np.min(np.linalg.norm(line - target, axis=1)))
        if distance < best[1]:
            best = (key, distance)
    return best


__all__ = (
    "MeshProjector",
    "Sketch",
    "SketchCurve",
    "boundary_loop",
    "catmull_rom",
    "closest_points_on_triangles",
    "curve_on_mesh",
    "loop_polylines",
    "nearest_on_polylines",
    "region_inside",
)
