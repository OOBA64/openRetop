"""3D Sketch on the scan: points clicked on the mesh, curves through them lying on the surface.

The ExModel way of modelling organic parts: click points on the scan; each curve passes
through its points and runs along the scan between them (a path over the surface, smoothed),
so it never floats above the surface, cuts across a gap or overshoots past its ends. Curves
share points (snapping to a point reuses it), so they join into a network: two or more open
curves loft into a surface, a closed curve or a loop of curves becomes a face fitted to the
scan inside it. Every curve stays editable: its points move, come and go, it splits, opens,
closes, reverses; its smoothness and whether it follows the scan's creases are its own.

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
        self._graph: object | None = None

    @property
    def graph(self):  # -> SurfaceGraph (built once, about 2 s on an 800k-triangle scan)
        if self._graph is None:
            from openretop.modeling.surface_paths import SurfaceGraph

            self._graph = SurfaceGraph(self.vertices, self.triangles)
        return self._graph

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


def curve_on_mesh(
    points: object,
    projector: MeshProjector,
    *,
    closed: bool = False,
    smoothness: float = 0.5,
    feature: bool = False,
    smoothing: int | None = None,
) -> np.ndarray:
    """A polyline through ``points`` that lies on the scan.

    Each span runs along the surface (the shortest path over the scan between its two
    points, or with ``feature`` the path along the scan's creases), resampled evenly and
    smoothed (``smoothness`` 0 to 1) while it is kept on the scan. Across interior points the
    curve bends smoothly the way a spline through the points does (not in ``feature`` mode:
    there the crease decides). It passes exactly through the points, so curves sharing a
    point meet there, and ends at its end points. A span whose points are on separate pieces
    of the scan (or across a gap no path goes round) is bridged straight.

    ``smoothing`` 0 (the live preview while drawing) means: as little smoothing as reads well.
    """

    if smoothing is not None and smoothing <= 0:
        smoothness = min(smoothness, 0.15)
    control, _triangles = projector.project(points)
    count = len(control)
    if count < 2:
        return control
    graph = projector.graph
    step = 0.75 * projector.spacing
    spans = count if closed else count - 1
    pieces: list[np.ndarray] = []
    bridged: list[bool] = []
    for span in range(spans):
        start, end = control[span], control[(span + 1) % count]
        chord = float(np.linalg.norm(end - start))
        path = graph.path(start, end, feature=1.0 if feature else 0.0)
        length = float(np.sum(np.linalg.norm(np.diff(path, axis=0), axis=1))) if path is not None else np.inf
        gap = path is None or length > 2.5 * chord + 20.0 * projector.spacing  # the way round is no way
        segment = _even(np.vstack([start, end]) if gap else path, step)
        if feature and not gap:
            # the crease shapes the curve: centred on it, only the zigzag smoothed out, centred again
            segment = _onto_crest(segment, projector)
            segment = _smoothed(segment, projector, smoothness, on_scan=True, feature=True)
            segment = _onto_crest(segment, projector, rounds=2)
            for _round in range(int(round(2 + 14 * float(np.clip(smoothness, 0.0, 1.0))))):  # evened out, as asked
                segment[1:-1] = 0.5 * segment[1:-1] + 0.25 * (segment[:-2] + segment[2:])
        else:
            segment = _smoothed(segment, projector, smoothness, on_scan=not gap)
        pieces.append(segment)
        bridged.append(gap)
    if not feature and count >= 3:
        pieces = _bend_through_points(control, pieces, closed=closed)
    line, held = _joined(pieces, closed=closed)
    line = _ease_through_points(line, held, closed=closed)
    on_scan = np.concatenate([np.full(len(piece) - 1, not gap) for piece, gap in zip(pieces, bridged, strict=True)] + [[True]])
    projected, _triangles = projector.project(line)
    near = np.linalg.norm(projected - line, axis=1) <= 3.0 * projector.spacing
    line = np.where((on_scan | near)[:, None], projected, line)
    line[held] = control if not closed else np.vstack([control, control[:1]])
    return line


def _even(path: np.ndarray, step: float) -> np.ndarray:
    """The polyline resampled every ``step`` (ends kept)."""

    lengths = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
    total = float(lengths[-1])
    count = max(2, int(np.ceil(total / max(step, 1e-12))) + 1)
    at = np.linspace(0.0, total, count)
    return np.c_[np.interp(at, lengths, path[:, 0]), np.interp(at, lengths, path[:, 1]), np.interp(at, lengths, path[:, 2])]


def _onto_crest(segment: np.ndarray, projector: MeshProjector, rounds: int = 4) -> np.ndarray:
    """Centre a span on its crease: a crease reads a few triangles wide, and the path along
    it cuts the inside of each bend within that band (1 mm off the crest on a test ridge).
    Each sample moves to the crease-weighted middle of the scan around it (the strongest bend
    dominates), a few rounds, then back onto the scan; the ends stay."""

    graph = projector.graph
    strength = graph.crease
    radius = 3.0 * projector.spacing
    line = segment.copy()
    for _round in range(rounds):
        neighbourhoods = graph.tree.query_ball_point(line[1:-1], radius)
        for row, members in enumerate(neighbourhoods, start=1):
            if not members:
                continue
            weight = strength[members] ** 4
            total = float(weight.sum())
            if total > 1e-12:
                line[row] = weight @ graph.vertices[members] / total
        line[1:-1] = projector.project(line[1:-1])[0]
    return line


def _smoothed(segment: np.ndarray, projector: MeshProjector, smoothness: float, *, on_scan: bool, feature: bool = False) -> np.ndarray:
    """Relax a span (its ends held) and keep it on the scan.

    A path over the scan's edges zigzags, in long runs along the triangles' directions as
    well as by single triangles (a fender curve wobbled every 10-30 mm). Relaxing coarse to
    fine takes both out: a few points along the span are pulled straight and put back on the
    scan, round after round, then finer; the result is the smooth, straightest line over the
    scan between the ends. ``smoothness`` sets how far the curve goes towards it; a curve
    following a crease (``feature``) only loses its zigzag: relaxing pulled it 1 mm off the
    crest of a test ridge.
    """

    if len(segment) < 3 or not on_scan:
        return segment
    strength = 0.0 if feature else float(np.clip(smoothness, 0.0, 1.0))
    fine = segment
    total = float(np.sum(np.linalg.norm(np.diff(fine, axis=0), axis=1)))
    fine_step = total / max(len(fine) - 1, 1)
    relaxed = fine
    for divisions in (6, 24, 96) if strength > 0.0 else ():
        step = total / divisions
        if step < 3.0 * fine_step:
            break
        coarse = _even(relaxed, step)
        for _round in range(30):
            coarse[1:-1] = 0.5 * coarse[1:-1] + 0.25 * (coarse[:-2] + coarse[2:])
            coarse[1:-1] = projector.project(coarse[1:-1])[0]
        relaxed = _even(coarse, fine_step)
    relaxed = _matched(relaxed, len(fine))
    line = fine * (1.0 - strength) + relaxed * strength
    for round_number in range(8):  # the last zigzag of single triangles
        line[1:-1] = 0.5 * line[1:-1] + 0.25 * (line[:-2] + line[2:])
        if round_number % 4 == 3:
            line[1:-1] = projector.project(line[1:-1])[0]
    return line


def _matched(line: np.ndarray, count: int) -> np.ndarray:
    """The polyline resampled to ``count`` evenly spaced points."""

    lengths = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(line, axis=0), axis=1))]
    at = np.linspace(0.0, float(lengths[-1]), count)
    return np.c_[np.interp(at, lengths, line[:, 0]), np.interp(at, lengths, line[:, 1]), np.interp(at, lengths, line[:, 2])]


def _bend_through_points(control: np.ndarray, pieces: list[np.ndarray], *, closed: bool) -> list[np.ndarray]:
    """Add to each span how a spline through all the points bows away from the straight run
    between the span's points: the surface paths meet at a point with a kink, the spline
    passes through it smoothly. The offsets are small and lie mostly along the surface."""

    count = len(control)
    bent = []
    for span, piece in enumerate(pieces):
        lengths = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(piece, axis=0), axis=1))]
        t = lengths / max(float(lengths[-1]), 1e-12)
        indices = [(span + offset) % count if closed else min(max(span + offset, 0), count - 1) for offset in (-1, 0, 1, 2)]
        p0, p1, p2, p3 = (control[index] for index in indices)
        if not closed and span == 0:
            p0 = 2 * p1 - p2
        if not closed and span == len(pieces) - 1:
            p3 = 2 * p2 - p1
        spline = _centripetal_segment(p0, p1, p2, p3, t)
        straight = p1 + (p2 - p1) * t[:, None]
        bent.append(piece + (spline - straight))
    return bent


def _ease_through_points(line: np.ndarray, held: np.ndarray, *, closed: bool) -> np.ndarray:
    """No corner at an interior point: the spans either side arrive along their own paths
    over the scan, in different directions (69 degrees on a fender). Near each point the
    samples are eased onto the point's mean direction (in and out), fading out over a quarter
    of the shorter span either side; the caller puts them back on the scan."""

    eased = line.copy()
    lengths = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(line, axis=0), axis=1))]
    total = float(lengths[-1])
    interior = list(held[1:-1]) + ([int(held[0])] if closed else [])
    for index in interior:
        index = int(index)
        position = list(held).index(index)
        before_start = int(held[position - 1]) if position > 0 else int(held[-2])
        after_end = int(held[position + 1]) if position + 1 < len(held) else int(held[1])
        here = lengths[index] if index < len(line) - 1 or not closed else 0.0
        span_in = (lengths[index] - lengths[before_start]) if index > 0 else (total - lengths[before_start])
        span_out = lengths[after_end] - here
        reach = 0.25 * max(min(span_in, span_out), 1e-9)
        signed = _signed_arc(lengths, index, total, closed)
        window = np.nonzero(np.abs(signed) <= reach)[0]
        if len(window) < 3:
            continue
        incoming = line[index] - line[window[signed[window] < 0]].mean(axis=0) if np.any(signed[window] < 0) else None
        outgoing = line[window[signed[window] > 0]].mean(axis=0) - line[index] if np.any(signed[window] > 0) else None
        if incoming is None or outgoing is None:
            continue
        direction = _unit(_unit(incoming) + _unit(outgoing))
        weight = (1.0 - np.abs(signed[window]) / reach) ** 2
        target = line[index] + signed[window][:, None] * direction
        eased[window] = line[window] * (1.0 - weight[:, None]) + target * weight[:, None]
    return eased


def _signed_arc(lengths: np.ndarray, index: int, total: float, closed: bool) -> np.ndarray:
    """Arc length of every sample from sample ``index`` (negative before it; wrapping on a loop)."""

    signed = lengths - lengths[index]
    if closed and total > 0:
        signed = (signed + 0.5 * total) % total - 0.5 * total
    return signed


def _unit(vector: np.ndarray) -> np.ndarray:
    return vector / max(float(np.linalg.norm(vector)), 1e-15)


def _joined(pieces: list[np.ndarray], *, closed: bool) -> tuple[np.ndarray, np.ndarray]:
    """One polyline from the spans, and where each point (span start) sits in it."""

    held, rows, offset = [], [], 0
    for piece in pieces:
        held.append(offset)
        rows.append(piece[:-1])
        offset += len(piece) - 1
    rows.append(pieces[-1][-1:])
    held.append(offset)
    return np.vstack(rows), np.asarray(held, dtype=np.int64)


# -- the sketch -------------------------------------------------------------------------------


@dataclass
class SketchCurve:
    id: str
    name: str
    nodes: list[str]  # control points in order; shared points join curves
    closed: bool = False
    polyline: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))
    visible: bool = True
    smoothness: float = 0.5  # 0: hugs the path over the scan's triangles, 1: evened out
    feature: bool = False  # follows the scan's creases (body lines) between its points


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

    def add_curve(
        self,
        nodes: list[str],
        projector: MeshProjector,
        *,
        closed: bool = False,
        name: str | None = None,
        smoothness: float = 0.5,
        feature: bool = False,
    ) -> SketchCurve:
        if len(nodes) < 2:
            raise ValueError("a curve needs at least two points")
        self.counter += 1
        curve = SketchCurve(f"c{self.counter}", name or self.next_name(), list(nodes), closed, smoothness=smoothness, feature=feature)
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
        curve.polyline = curve_on_mesh(points, projector, closed=curve.closed, smoothness=curve.smoothness, feature=curve.feature)

    # -- editing ---------------------------------------------------------------------------

    def span_at(self, curve: SketchCurve, position: object) -> int:
        """The span (between point k and k+1) passing nearest ``position``."""

        line = curve.polyline
        target = np.asarray(position, dtype=float).reshape(3)
        nearest = int(np.argmin(np.linalg.norm(line - target, axis=1)))
        # where each point sits on the line, in order
        held = [int(np.argmin(np.linalg.norm(line - self.nodes[node], axis=1))) for node in curve.nodes]
        if curve.closed:
            held.append(len(line) - 1)
        for span in range(len(held) - 1):
            if held[span] <= nearest <= held[span + 1]:
                return span
        return len(held) - 2

    def insert_node(self, curve_id: str, position: object, projector: MeshProjector) -> str:
        """A new point on the curve where it passes ``position`` (between the points either side)."""

        curve = self.curve(curve_id)
        if curve is None:
            raise ValueError("no such curve")
        snapped, _triangle = projector.project(np.asarray(position, dtype=float).reshape(1, 3))
        span = self.span_at(curve, snapped[0])
        node = self.new_node(snapped[0])
        curve.nodes.insert(span + 1, node)
        self.rebuild(curve, projector)
        return node

    def split_curve(self, curve_id: str, node_id: str, projector: MeshProjector) -> list[str]:
        """Cut the curve at one of its points: an open curve into two sharing the point, a
        closed one opened there."""

        curve = self.curve(curve_id)
        if curve is None or node_id not in curve.nodes:
            raise ValueError("the point is not on that curve")
        index = curve.nodes.index(node_id)
        if curve.closed:
            curve.nodes = curve.nodes[index:] + curve.nodes[: index + 1]
            curve.closed = False
            self.rebuild(curve, projector)
            return [curve.id]
        if index in (0, len(curve.nodes) - 1):
            raise ValueError("that is an end of the curve already")
        tail = curve.nodes[index:]
        curve.nodes = curve.nodes[: index + 1]
        self.rebuild(curve, projector)
        other = self.add_curve(tail, projector, smoothness=curve.smoothness, feature=curve.feature)
        position = self.curves.index(curve)
        self.curves.remove(other)
        self.curves.insert(position + 1, other)
        return [curve.id, other.id]

    def set_closed(self, curve_id: str, closed: bool, projector: MeshProjector) -> None:
        curve = self.curve(curve_id)
        if curve is None:
            raise ValueError("no such curve")
        if closed and len(curve.nodes) < 3:
            raise ValueError("a closed curve needs at least three points")
        curve.closed = bool(closed)
        self.rebuild(curve, projector)

    def reverse(self, curve_id: str) -> None:
        curve = self.curve(curve_id)
        if curve is None:
            raise ValueError("no such curve")
        curve.nodes.reverse()
        curve.polyline = curve.polyline[::-1].copy()

    def set_options(self, curve_id: str, projector: MeshProjector, *, smoothness: float | None = None, feature: bool | None = None) -> None:
        curve = self.curve(curve_id)
        if curve is None:
            raise ValueError("no such curve")
        if smoothness is not None:
            curve.smoothness = float(np.clip(smoothness, 0.0, 1.0))
        if feature is not None:
            curve.feature = bool(feature)
        self.rebuild(curve, projector)

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
