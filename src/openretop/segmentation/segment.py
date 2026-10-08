"""Split a scan into the faces of the part it came from (RE-03).

Fit-guided region growing, the way reverse-engineering packages do it:

1. Estimate the scanner noise from small local quadric fits, which sets the tolerance.
2. Take seeds in the smoothest unclaimed areas first.
3. Classify each seed patch with the primitive fitter (plane, cylinder, sphere, cone, torus).
4. Grow the region one ring of triangles at a time, accepting a triangle only if it lies on
   *that exact primitive* within the tolerance and its normal agrees. Refit as the region
   grows.

So a plane stops exactly where its fillet starts. Plain normal-angle growing (the old region
tool) cannot do that, because the angle between neighbouring triangles is small everywhere
on a blend.

Whatever no primitive claims is split into connected "freeform" regions. Small leftovers
along edges stay unassigned as transitions.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from openretop.fitting import PrimitiveFit, fit_primitive, primitive_distance, primitive_normal

UNASSIGNED = -1


@dataclass(frozen=True)
class Segment:
    id: int
    kind: str  # plane, cylinder, sphere, cone, torus or freeform
    triangles: np.ndarray
    fit: PrimitiveFit | None
    area: float = 0.0
    width: float = 0.0  # area / length: how wide the region is across its long direction
    edge_band: bool = False  # a strip a couple of triangles wide along a sharp edge, not a face

    @property
    def triangle_count(self) -> int:
        return int(len(self.triangles))


@dataclass
class SegmentationResult:
    segments: list[Segment]
    labels: np.ndarray  # segment id of every triangle, UNASSIGNED for transitions
    noise_sigma: float
    tolerance: float
    angle_tolerance_degrees: float
    seconds: float
    metadata: dict[str, object] = field(default_factory=dict)

    def segment(self, segment_id: int) -> Segment:
        return self.segments[segment_id]

    @property
    def assigned_fraction(self) -> float:
        return float(np.mean(self.labels != UNASSIGNED)) if len(self.labels) else 0.0


# -- mesh topology -----------------------------------------------------------------------


def triangle_adjacency(triangles: np.ndarray, vertex_count: int) -> tuple[np.ndarray, np.ndarray]:
    """Edge-neighbours of every triangle as CSR arrays (offsets, neighbours)."""

    triangle_count = len(triangles)
    edges = np.sort(triangles[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), axis=1)
    owner = np.repeat(np.arange(triangle_count), 3)
    keys = edges[:, 0].astype(np.int64) * int(vertex_count) + edges[:, 1]
    order = np.argsort(keys, kind="stable")
    keys, owner = keys[order], owner[order]
    same = keys[1:] == keys[:-1]
    first, second = owner[:-1][same], owner[1:][same]  # consecutive owners of a shared edge
    pairs = np.concatenate([np.c_[first, second], np.c_[second, first]])
    pairs = pairs[pairs[:, 0] != pairs[:, 1]]
    order = np.argsort(pairs[:, 0], kind="stable")
    pairs = pairs[order]
    counts = np.bincount(pairs[:, 0], minlength=triangle_count)
    offsets = np.concatenate([[0], np.cumsum(counts)])
    return offsets, pairs[:, 1]


def _neighbours_of(offsets: np.ndarray, neighbours: np.ndarray, items: np.ndarray) -> np.ndarray:
    if len(items) == 0:
        return items
    starts, ends = offsets[items], offsets[items + 1]
    lengths = ends - starts
    index = np.repeat(starts - np.concatenate([[0], np.cumsum(lengths)[:-1]]), lengths) + np.arange(int(lengths.sum()))
    return np.unique(neighbours[index])


# -- the algorithm ---------------------------------------------------------------------


def segment_mesh(
    vertices: object,
    triangles: object,
    *,
    tolerance: float | None = None,
    angle_tolerance_degrees: float | None = None,
    min_region_triangles: int = 30,
    seed_radius: float | None = None,
    progress: Callable[[float], None] | None = None,
) -> SegmentationResult:
    started = time.perf_counter()
    xyz = np.asarray(vertices, dtype=float).reshape(-1, 3)
    tri = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
    corners = xyz[tri]
    centroids = corners.mean(axis=1)
    # Triangle normals of thin sliver triangles (common in decimated or CAD-tessellated scans)
    # are dominated by noise. Area-weighted vertex normals average over each vertex's whole
    # fan, so a triangle's normal is the mean of its three vertex normals.
    vertex_normals = _vertex_normals(xyz, tri)
    normals = _unit_rows(vertex_normals[tri].sum(axis=1))
    offsets, neighbours = triangle_adjacency(tri, len(xyz))
    count = len(tri)

    noise_sigma, normal_noise = _estimate_noise(xyz, tri, vertex_normals, offsets, neighbours)
    tol = float(tolerance) if tolerance is not None else max(3.5 * noise_sigma, 1e-6)
    angle_tol = float(angle_tolerance_degrees) if angle_tolerance_degrees is not None else max(12.0, 4.0 * normal_noise)
    cos_angle = math.cos(math.radians(angle_tol))

    diagonal = float(np.linalg.norm(xyz.max(axis=0) - xyz.min(axis=0))) if len(xyz) else 0.0
    radius = seed_radius if seed_radius is not None else max(0.06 * diagonal, 40.0 * noise_sigma)

    labels = np.full(count, UNASSIGNED, dtype=np.int64)
    tried = np.zeros(count, dtype=bool)
    regions: list[tuple[str, np.ndarray, PrimitiveFit]] = []
    for seed in _seed_order(normals, offsets, neighbours):
        if labels[seed] != UNASSIGNED or tried[seed]:
            continue
        patch = _seed_patch(seed, labels, centroids, normals, offsets, neighbours, radius)
        tried[patch] = True
        if len(patch) < 10:
            continue
        grown, explored = _grow_best(patch, labels, centroids, normals, offsets, neighbours, tol, cos_angle)
        if grown is None:
            # no exact shape explains it: left for the freeform pass, and the area the
            # attempts covered is not seeded again (freeform would otherwise be retried
            # from every one of its triangles)
            tried[explored] = True
            continue
        kind, region, fit = grown
        if len(region) < min_region_triangles:
            continue
        labels[region] = len(regions)
        regions.append((kind, region, fit))
        if progress is not None:
            progress(float(np.mean(labels != UNASSIGNED)))

    regions, labels = _merge_regions(regions, labels, centroids, normals, offsets, neighbours, tol)
    corner_edges = np.linalg.norm(corners - np.roll(corners, 1, axis=1), axis=2)
    spacing = float(np.median(corner_edges)) if len(corner_edges) else 0.0
    triangle_areas = 0.5 * np.linalg.norm(np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1)
    segments = []
    for index, (kind, region, fit) in enumerate(regions):
        final_kind, final_fit = _vertex_fit(kind, region, fit, xyz, tri, vertex_normals, tol)
        area, width = _area_and_width(region, centroids, triangle_areas)
        segments.append(
            Segment(index, final_kind, np.sort(region), final_fit, area=area, width=width, edge_band=_is_edge_band(final_kind, final_fit, width, spacing))
        )
    for component in _components(labels == UNASSIGNED, offsets, neighbours):
        if len(component) >= max(min_region_triangles * 4, 100):
            labels[component] = len(segments)
            segments.append(Segment(len(segments), "freeform", np.sort(component), None))

    return SegmentationResult(
        segments=segments,
        labels=labels,
        noise_sigma=noise_sigma,
        tolerance=tol,
        angle_tolerance_degrees=angle_tol,
        seconds=time.perf_counter() - started,
        metadata={"triangle_count": count},
    )


def _vertex_normals(vertices: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    corners = vertices[triangles]
    face = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])  # area weighted
    flat = triangles.ravel()
    repeated = np.repeat(face, 3, axis=0)
    summed = np.column_stack([np.bincount(flat, weights=repeated[:, axis], minlength=len(vertices)) for axis in range(3)])
    return _unit_rows(summed)


def _unit_rows(vectors: np.ndarray) -> np.ndarray:
    return vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-15)


def _estimate_noise(vertices, triangles, vertex_normals, offsets, neighbours, samples: int = 300) -> tuple[float, float]:
    """Scanner noise (mm) and normal jitter (degrees) from local quadric fits on vertices."""

    rng = np.random.default_rng(7)
    picks = rng.choice(len(triangles), size=min(samples, len(triangles)), replace=False)
    residuals: list[float] = []
    angles: list[float] = []
    for seed in picks:
        patch = np.array([seed])
        while len(patch) < 60:
            grown = np.union1d(patch, _neighbours_of(offsets, neighbours, patch))
            if len(grown) == len(patch):
                break
            patch = grown
        ids = np.unique(triangles[patch])
        if len(ids) < 20:
            continue
        points = vertices[ids] - vertices[ids].mean(axis=0)
        _u, _s, vt = np.linalg.svd(points, full_matrices=False)
        local = points @ vt.T  # x, y in the tangent plane, z along the normal
        x, y, z = local[:, 0], local[:, 1], local[:, 2]
        design = np.c_[x * x, x * y, y * y, x, y, np.ones_like(x)]
        coefficients, *_ = np.linalg.lstsq(design, z, rcond=None)
        rest = z - design @ coefficients
        dof = max(len(ids) - design.shape[1], 1)
        residuals.append(float(np.sqrt(np.sum(rest**2) / dof)))  # unbiased: the quadric absorbs 6 dof
        # jitter of the vertex normals around the quadric's own normal at each vertex
        a, b, c, d, e, _f = coefficients
        surface = np.c_[-(2 * a * x + b * y + d), -(b * x + 2 * c * y + e), np.ones_like(x)] @ vt
        surface = _unit_rows(surface)
        cosines = np.clip(np.abs(np.einsum("ij,ij->i", vertex_normals[ids], surface)), 0.0, 1.0)
        angles.append(math.degrees(math.acos(float(np.median(cosines)))))
    if not residuals:
        return 0.0, 0.0
    # Edges and strongly curved areas inflate many patches on a small part, so take the low
    # end of the distribution (the smooth areas). A patch RMS from ~40 points scatters by
    # ~12%, so its 25th percentile sits at ~0.91 sigma.
    return float(np.percentile(residuals, 25)) / 0.91, float(np.percentile(angles, 25))


def _seed_order(normals, offsets, neighbours) -> np.ndarray:
    """Triangles ordered from the smoothest (normal agrees with all neighbours) to the roughest."""

    counts = np.diff(offsets)
    owner = np.repeat(np.arange(len(normals)), counts)
    agreement = np.einsum("ij,ij->i", normals[owner], normals[neighbours])
    worst = np.full(len(normals), 1.0)
    np.minimum.at(worst, owner, agreement)
    return np.argsort(-worst, kind="stable")


def _seed_patch(seed, labels, centroids, normals, offsets, neighbours, radius, max_triangles=6000) -> np.ndarray:
    """Unclaimed triangles within ``radius`` of the seed whose normals stay within 25 degrees.

    A physical radius, not a triangle count: the patch must be wide enough for curvature to
    show above the noise (a few long sliver triangles would otherwise look flat).
    """

    patch = np.array([seed])
    cos_limit = math.cos(math.radians(25.0))
    while len(patch) < max_triangles:
        ring = _neighbours_of(offsets, neighbours, patch)
        ring = ring[
            (labels[ring] == UNASSIGNED)
            & (normals[ring] @ normals[seed] > cos_limit)
            & (np.linalg.norm(centroids[ring] - centroids[seed], axis=1) <= radius)
        ]
        grown = np.union1d(patch, ring)
        if len(grown) == len(patch):
            break
        patch = grown
    return patch


SATURATION_RATIO = 1.3  # growth when the tolerance is doubled: a bounded face barely grows
BAND_ROWS = 1.2  # ...or gains at most about one row of triangles along its boundary


_SIMPLER = {"cylinder": ("plane",), "sphere": ("plane",), "cone": ("plane", "cylinder"), "torus": ("plane", "cylinder", "sphere"), "plane": ()}


def _simplest_for(kind, region, fit, centroids, normals, tol):
    for simpler in _SIMPLER[kind]:
        candidate = fit_primitive(simpler, centroids[region], normals[region], outlier_tolerance=tol)
        if candidate.success and candidate.rms <= tol and candidate.inlier_fraction >= 0.9:
            return simpler, region, candidate
    return kind, region, fit


def _boundary_count(region: np.ndarray, labels: np.ndarray, offsets: np.ndarray, neighbours: np.ndarray) -> int:
    """Triangles of the region that have a neighbour outside it (its perimeter, in triangles)."""

    inside = np.zeros(len(labels), dtype=bool)
    inside[region] = True
    starts, ends = offsets[region], offsets[region + 1]
    lengths = ends - starts
    index = np.repeat(starts - np.concatenate([[0], np.cumsum(lengths)[:-1]]), lengths) + np.arange(int(lengths.sum()))
    owners = np.repeat(region, lengths)
    outside = ~inside[neighbours[index]]
    open_edges = lengths < 3  # a triangle on the scan's own border also bounds the region
    return int(len(np.unique(owners[outside])) + np.sum(open_edges))


def _grow_best(patch, labels, centroids, normals, offsets, neighbours, tol, cos_angle):
    """The simplest primitive whose grown region is *saturated*, or None (freeform).

    Grow a candidate with the tolerance, then again with twice the tolerance. A real face is
    bounded by real edges, so the second growth adds only a thin band along them (5 to 10%).
    A wrong guess has no edges of its own; it stops wherever its systematic error reaches the
    tolerance, so doubling the tolerance grows it markedly. Examples: a plane on freeform
    (area roughly doubles), or a tilted cylinder on a cone (the strip widens by about 40%).
    The test needs no knowledge of the noise and no shape-specific thresholds. Candidates are
    tried simplest first and the first that saturates wins.
    """

    xyz, nrm = centroids[patch], normals[patch]
    if len(patch) > 2000:
        pick = np.random.default_rng(11).choice(len(patch), size=2000, replace=False)
        xyz, nrm = xyz[pick], nrm[pick]
    loose_cos = math.cos(min(math.acos(cos_angle) * 1.5, math.pi / 2))
    explored = patch
    weak: tuple[str, np.ndarray, PrimitiveFit] | None = None
    for kind in ("plane", "cylinder", "sphere", "cone", "torus"):
        fit = fit_primitive(kind, xyz, nrm)
        if not fit.success or fit.rms > tol or fit.inlier_fraction < 0.9:
            continue
        region, grown_fit = _grow(patch, fit, kind, labels, centroids, normals, offsets, neighbours, tol, cos_angle)
        if len(region) < 3:
            continue
        loose, _loose_fit = _grow(region, grown_fit, kind, labels, centroids, normals, offsets, neighbours, 2.0 * tol, loose_cos, refit=False)
        added = len(loose) - len(region)
        if len(loose) <= SATURATION_RATIO * len(region):
            # clearly bounded by real edges. Occam: a huge sphere hugging a flat ring passes
            # too, so a simpler primitive that explains the same region wins
            return _simplest_for(kind, region, grown_fit, centroids, normals, tol), explored
        # A narrow face (a 2 mm groove wall) gains a large share of its area from the one row
        # of triangles along its edges, so it is judged per unit of boundary instead. That is a
        # weak pass: a thin strip of a fillet passes it as a plane too, so a later primitive
        # that passes outright (the fillet's cylinder) wins over it.
        if added <= BAND_ROWS * _boundary_count(region, labels, offsets, neighbours):
            if weak is None or len(region) > len(weak[1]):
                weak = (kind, region, grown_fit)
        if len(region) > len(explored):
            explored = region
    return weak, explored


def _grow(patch, fit, kind, labels, centroids, normals, offsets, neighbours, tol, cos_angle, *, refit=True):
    in_region = np.zeros(len(labels), dtype=bool)
    rejected = np.zeros(len(labels), dtype=bool)

    def accepts(candidates: np.ndarray) -> np.ndarray:
        distance = np.abs(primitive_distance(fit, centroids[candidates]))
        agreement = np.abs(np.einsum("ij,ij->i", normals[candidates], primitive_normal(fit, centroids[candidates])))
        return (distance <= tol) & (agreement >= cos_angle)

    seed_ok = patch[accepts(patch)]
    if len(seed_ok) < 3:
        return seed_ok, fit
    in_region[seed_ok] = True
    frontier = seed_ok
    fitted_at = len(seed_ok)
    while len(frontier):
        candidates = _neighbours_of(offsets, neighbours, frontier)
        candidates = candidates[~in_region[candidates] & ~rejected[candidates] & (labels[candidates] == UNASSIGNED)]
        if len(candidates) == 0:
            break
        ok = accepts(candidates)
        rejected[candidates[~ok]] = True
        frontier = candidates[ok]
        in_region[frontier] = True
        size = int(in_region.sum())
        if refit and size >= 2 * fitted_at:  # refit on the larger region: the shape gets more exact
            region = np.nonzero(in_region)[0]
            refit = fit_primitive(kind, centroids[region], normals[region], outlier_tolerance=tol)
            if refit.success:
                fit = refit
                rejected[:] = False  # the better fit may accept what the first one refused
                frontier = region
            fitted_at = size
    region = np.nonzero(in_region)[0]
    if not refit:
        return region, fit
    final = fit_primitive(kind, centroids[region], normals[region], outlier_tolerance=tol)
    return region, final if final.success else fit


def _vertex_fit(kind, region, fit, vertices, triangles, vertex_normals, tol):
    """The region's final (kind, fit), on its vertices.

    Growing works on triangle centroids, but a centroid lies on the chord, slightly inside
    a curved surface (a R4 hole fitted 3.97 at 1.5 mm spacing). The vertices lie on the
    surface, so the reported primitive is refitted to them.

    A cylinder or cone that covers only a sliver of its arc is nearly flat. A 2.8 mm chamfer
    strip fitted as an R11 cylinder, almost tangent to its neighbours, crashed the CAD kernel.
    If a plane explains such a region within tolerance, it is a plane.
    """

    ids = np.unique(triangles[region])
    points, normals = vertices[ids], vertex_normals[ids]
    if kind in ("cylinder", "cone") and _arc_span_degrees(kind, fit, points) < FLAT_ARC_DEGREES:
        plane = fit_primitive("plane", points, normals, outlier_tolerance=tol)
        # edge bevels make up much of a narrow strip, so only three quarters need to fit
        if plane.success and plane.rms <= tol and plane.inlier_fraction >= 0.75:
            return "plane", plane
    refit = fit_primitive(kind, points, normals, outlier_tolerance=tol)
    return kind, (refit if refit.success else fit)


FLAT_ARC_DEGREES = 25.0


def _is_edge_band(kind: str, fit: PrimitiveFit, width: float, spacing: float) -> bool:
    """A strip of triangles along a sharp edge, not a face of the part.

    A scanned sharp edge comes out as a rounded band whose radius is about the scanner's point
    spacing: a "fillet" the scanner itself made. Real faces can be just as narrow (a 2 mm
    groove wall measured narrower than an edge band), so width alone cannot tell them apart;
    the radius can. Anything less than one point spacing wide is a band too.
    """

    if spacing <= 0.0:
        return False
    if width < 1.0 * spacing:
        return True
    params = fit.params if fit is not None else {}
    radius = params.get("radius", params.get("minor_radius"))
    if kind in ("cylinder", "sphere", "torus") and radius is not None:
        return float(radius) < 2.0 * spacing and width < 3.0 * spacing  # type: ignore[arg-type]
    return False


def _area_and_width(region: np.ndarray, centroids: np.ndarray, areas: np.ndarray) -> tuple[float, float]:
    area = float(areas[region].sum())
    points = centroids[region]
    if len(points) < 3:
        return area, 0.0
    centred = points - points.mean(axis=0)
    _u, _s, vt = np.linalg.svd(centred, full_matrices=False)
    along = centred @ vt[0]
    length = float(along.max() - along.min())
    return area, (area / length if length > 1e-12 else 0.0)


def _arc_span_degrees(kind: str, fit: PrimitiveFit, points: np.ndarray) -> float:
    """How much of the way around its axis a cylinder or cone region reaches (degrees)."""

    axis = np.asarray(fit.params["axis"], dtype=float)
    origin = np.asarray(fit.params["point" if kind == "cylinder" else "apex"], dtype=float)
    offset = points - origin
    radial = offset - np.outer(offset @ axis, axis)
    helper = np.array([1.0, 0.0, 0.0]) if abs(axis[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(axis, helper)
    u /= np.linalg.norm(u)
    v = np.cross(axis, u)
    angles = np.sort(np.arctan2(radial @ v, radial @ u))
    if len(angles) < 2:
        return 0.0
    gaps = np.diff(np.r_[angles, angles[0] + 2.0 * math.pi])
    return math.degrees(2.0 * math.pi - float(gaps.max()))


def _merge_regions(regions, labels, centroids, normals, offsets, neighbours, tol):
    """Join neighbouring regions of the same kind when one primitive fits both.

    A face that was seeded twice (from both ends) or split by a hole grows as two regions;
    if a single fit of their union stays within the tolerance they are one face.
    """

    regions = list(regions)
    merged_any = True
    while merged_any:
        merged_any = False
        owner = np.repeat(np.arange(len(labels)), np.diff(offsets))
        a, b = labels[owner], labels[neighbours]
        touching = (a != b) & (a != UNASSIGNED) & (b != UNASSIGNED)
        pairs = np.unique(np.sort(np.c_[a[touching], b[touching]], axis=1), axis=0)
        alive = [True] * len(regions)
        for first, second in pairs:
            if not (alive[first] and alive[second]) or regions[first][0] != regions[second][0]:
                continue
            kind = regions[first][0]
            union = np.concatenate([regions[first][1], regions[second][1]])
            fit = fit_primitive(kind, centroids[union], normals[union], outlier_tolerance=tol)
            if fit.success and fit.rms <= 0.5 * tol and fit.inlier_fraction >= 0.97:
                regions[first] = (kind, union, fit)
                alive[second] = False
                labels[regions[second][1]] = first
                merged_any = True
        if merged_any:
            keep = [index for index, flag in enumerate(alive) if flag]
            renumber = np.full(len(regions), UNASSIGNED, dtype=np.int64)
            renumber[keep] = np.arange(len(keep))
            assigned = labels != UNASSIGNED
            labels[assigned] = renumber[labels[assigned]]
            regions = [regions[index] for index in keep]
    return regions, labels


def _components(mask: np.ndarray, offsets: np.ndarray, neighbours: np.ndarray) -> list[np.ndarray]:
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import connected_components

    owner = np.repeat(np.arange(len(mask)), np.diff(offsets))
    keep = mask[owner] & mask[neighbours]
    graph = csr_matrix((np.ones(int(keep.sum())), (owner[keep], neighbours[keep])), shape=(len(mask), len(mask)))
    _count, component = connected_components(graph, directed=False)
    result = []
    for value in np.unique(component[mask]):
        members = np.nonzero((component == value) & mask)[0]
        result.append(members)
    return result


__all__ = ("UNASSIGNED", "Segment", "SegmentationResult", "segment_mesh", "triangle_adjacency")
