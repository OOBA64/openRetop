"""Freeform B-spline surface fitted to a selected area of the scan (ExModel "Fit Surface").

The fit, in four steps:

1. **Parameterize.** Each point gets a (u, v). A height field over its best-fit plane is
   projected onto that plane. A curved area (a wheel-arch flange that turns through 90
   degrees) is flattened conformally instead, by least-squares conformal maps on the selected
   triangles. The (u, v) are then turned so the patch's rectangle hugs the selection.
2. **Least squares** for a U x V net of cubic control points, with a smoothing term on the
   net's second differences. The smoothing keeps the net sensible where there is no data:
   holes in the scan, and the margin added by "expand".
3. **Parameter correction.** Each point's (u, v) moves to its foot point on the surface and
   the net is solved again. This fits true distances rather than parametric ones.
4. **Report** RMS and maximum deviation of the points from the surface.

The result converts to an OpenCASCADE ``Geom_BSplineSurface`` (``cad_kernel.surfacing``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

MAX_FIT_POINTS = 60_000  # a random subset this size drives the solve; statistics use all points
DEFAULT_DEGREE = 3


@dataclass
class BSplineSurfaceFit:
    success: bool
    degree_u: int = DEFAULT_DEGREE
    degree_v: int = DEFAULT_DEGREE
    knots_u: np.ndarray = field(default_factory=lambda: np.zeros(0))  # full clamped knot vectors
    knots_v: np.ndarray = field(default_factory=lambda: np.zeros(0))
    poles: np.ndarray = field(default_factory=lambda: np.zeros((0, 0, 3)))  # (nu, nv, 3)
    rms: float = float("inf")
    max_error: float = float("inf")
    point_count: int = 0
    parameterization: str = ""
    reason: str = ""

    @property
    def control_counts(self) -> tuple[int, int]:
        return int(self.poles.shape[0]), int(self.poles.shape[1])

    @property
    def domain(self) -> tuple[float, float, float, float]:
        return (
            float(self.knots_u[self.degree_u]),
            float(self.knots_u[-self.degree_u - 1]),
            float(self.knots_v[self.degree_v]),
            float(self.knots_v[-self.degree_v - 1]),
        )

    def evaluate(self, u: object, v: object) -> np.ndarray:
        points, _du, _dv = self._evaluate(np.asarray(u, dtype=float), np.asarray(v, dtype=float), derivatives=False)
        return points

    def evaluate_derivatives(self, u: object, v: object) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return self._evaluate(np.asarray(u, dtype=float), np.asarray(v, dtype=float), derivatives=True)

    def grid(self, count_u: int = 40, count_v: int = 40) -> np.ndarray:
        u0, u1, v0, v1 = self.domain
        u, v = np.meshgrid(np.linspace(u0, u1, count_u), np.linspace(v0, v1, count_v), indexing="ij")
        return self.evaluate(u.ravel(), v.ravel()).reshape(count_u, count_v, 3)

    def closest_parameters(self, points: object, iterations: int = 8) -> tuple[np.ndarray, np.ndarray]:
        """Foot-point parameters of each point, from a dense sample and Gauss-Newton steps."""

        from scipy.spatial import cKDTree

        query = np.asarray(points, dtype=float).reshape(-1, 3)
        nu, nv = self.control_counts
        count_u, count_v = max(30, 6 * nu), max(30, 6 * nv)
        u0, u1, v0, v1 = self.domain
        grid_u, grid_v = np.meshgrid(np.linspace(u0, u1, count_u), np.linspace(v0, v1, count_v), indexing="ij")
        samples = self.evaluate(grid_u.ravel(), grid_v.ravel())
        _distance, nearest = cKDTree(samples).query(query)
        u = grid_u.ravel()[nearest]
        v = grid_v.ravel()[nearest]
        return self._project(query, u, v, iterations)

    def distances(self, points: object) -> np.ndarray:
        query = np.asarray(points, dtype=float).reshape(-1, 3)
        u, v = self.closest_parameters(query)
        return np.linalg.norm(self.evaluate(u, v) - query, axis=1)

    # -- internals ---------------------------------------------------------------------------

    def _project(self, points: np.ndarray, u: np.ndarray, v: np.ndarray, iterations: int) -> tuple[np.ndarray, np.ndarray]:
        u0, u1, v0, v1 = self.domain
        for _step in range(iterations):
            surface, du, dv = self._evaluate(u, v, derivatives=True)
            residual = surface - points
            a = np.einsum("ij,ij->i", du, du)
            b = np.einsum("ij,ij->i", du, dv)
            c = np.einsum("ij,ij->i", dv, dv)
            g_u = np.einsum("ij,ij->i", du, residual)
            g_v = np.einsum("ij,ij->i", dv, residual)
            determinant = a * c - b * b
            safe = np.abs(determinant) > 1e-18
            step_u = np.where(safe, (c * g_u - b * g_v) / np.where(safe, determinant, 1.0), 0.0)
            step_v = np.where(safe, (a * g_v - b * g_u) / np.where(safe, determinant, 1.0), 0.0)
            u = np.clip(u - step_u, u0, u1)
            v = np.clip(v - step_v, v0, v1)
            if float(np.max(np.abs(step_u), initial=0.0) + np.max(np.abs(step_v), initial=0.0)) < 1e-9:
                break
        return u, v

    def _evaluate(self, u: np.ndarray, v: np.ndarray, *, derivatives: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        shape = np.shape(u)
        u = np.ravel(u)
        v = np.ravel(v)
        span_u, basis_u, dbasis_u = basis_functions(self.knots_u, self.degree_u, u, derivatives=derivatives)
        span_v, basis_v, dbasis_v = basis_functions(self.knots_v, self.degree_v, v, derivatives=derivatives)
        index_u = span_u[:, None] - self.degree_u + np.arange(self.degree_u + 1)[None, :]
        index_v = span_v[:, None] - self.degree_v + np.arange(self.degree_v + 1)[None, :]
        local = self.poles[index_u[:, :, None], index_v[:, None, :]]  # (n, p+1, q+1, 3)
        points = np.einsum("ni,nj,nijk->nk", basis_u, basis_v, local)
        if not derivatives:
            return points.reshape((*shape, 3)), np.zeros(0), np.zeros(0)
        du = np.einsum("ni,nj,nijk->nk", dbasis_u, basis_v, local)
        dv = np.einsum("ni,nj,nijk->nk", basis_u, dbasis_v, local)
        return points.reshape((*shape, 3)), du.reshape((*shape, 3)), dv.reshape((*shape, 3))


# -- B-spline basis ---------------------------------------------------------------------------


def clamped_uniform_knots(count: int, degree: int, start: float, end: float) -> np.ndarray:
    """A clamped knot vector for ``count`` control points on [start, end]."""

    interior = count - degree - 1
    inner = np.linspace(start, end, interior + 2)[1:-1] if interior > 0 else np.zeros(0)
    return np.concatenate([np.full(degree + 1, start), inner, np.full(degree + 1, end)])


def basis_functions(
    knots: np.ndarray, degree: int, t: np.ndarray, *, derivatives: bool = False
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Knot span and the ``degree + 1`` non-zero basis functions (and derivatives) at each t.

    Vectorized Cox-de Boor (The NURBS Book, A2.2). Derivatives use the degree-1 basis on the
    same span (A2.3, first derivative).
    """

    t = np.asarray(t, dtype=float)
    count = len(knots) - degree - 1
    span = np.clip(np.searchsorted(knots, t, side="right") - 1, degree, count - 1)
    values = _cox_de_boor(knots, degree, span, t)
    if not derivatives:
        return span, values, np.zeros(0)
    if degree == 0:
        return span, values, np.zeros_like(values)
    lower = _cox_de_boor(knots, degree - 1, span, t)  # functions span-degree+1 .. span
    derivative = np.zeros_like(values)
    for r in range(degree + 1):
        i = span - degree + r
        if r >= 1:
            gap = knots[i + degree] - knots[i]
            derivative[:, r] += np.where(gap > 0, degree * lower[:, r - 1] / np.where(gap > 0, gap, 1.0), 0.0)
        if r <= degree - 1:
            gap = knots[i + degree + 1] - knots[i + 1]
            derivative[:, r] -= np.where(gap > 0, degree * lower[:, r] / np.where(gap > 0, gap, 1.0), 0.0)
    return span, values, derivative


def _cox_de_boor(knots: np.ndarray, degree: int, span: np.ndarray, t: np.ndarray) -> np.ndarray:
    n = len(t)
    values = np.zeros((n, degree + 1))
    values[:, 0] = 1.0
    left = np.zeros((n, degree + 1))
    right = np.zeros((n, degree + 1))
    for j in range(1, degree + 1):
        left[:, j] = t - knots[span + 1 - j]
        right[:, j] = knots[span + j] - t
        saved = np.zeros(n)
        for r in range(j):
            denominator = right[:, r + 1] + left[:, j - r]
            temp = np.where(denominator != 0.0, values[:, r] / np.where(denominator != 0.0, denominator, 1.0), 0.0)
            values[:, r] = saved + right[:, r + 1] * temp
            saved = left[:, j - r] * temp
        values[:, j] = saved
    return values


# -- parameterization -------------------------------------------------------------------------


@dataclass
class Parameterization:
    uv: np.ndarray  # (n, 2) for every input point
    method: str  # "plane" or "conformal"
    warnings: list[str] = field(default_factory=list)


def parameterize(
    points: np.ndarray,
    triangles: np.ndarray | None = None,
    *,
    method: str = "auto",
) -> Parameterization:
    """(u, v) for each point; ``triangles`` index into ``points`` (needed for "conformal")."""

    centroid = points.mean(axis=0)
    _s, _v, axes = np.linalg.svd(points - centroid, full_matrices=False)
    planar = (points - centroid) @ axes[:2].T
    warnings: list[str] = []
    if method == "plane" or triangles is None or len(triangles) == 0:
        if method == "conformal":
            warnings.append("a conformal flattening needs the selected triangles; projected onto a plane instead")
        return Parameterization(_aligned(planar), "plane", warnings)
    if method == "auto" and _is_height_field(points, triangles, axes[2]):
        return Parameterization(_aligned(planar), "plane", warnings)
    uv = conformal_map(points, triangles)
    if uv is None:
        warnings.append("the conformal flattening failed; projected onto a plane instead")
        return Parameterization(_aligned(planar), "plane", warnings)
    return Parameterization(_aligned(uv), "conformal", warnings)


def _is_height_field(points: np.ndarray, triangles: np.ndarray, normal: np.ndarray) -> bool:
    """No selected triangle folds over or stands steeply on the best-fit plane."""

    a, b, c = points[triangles[:, 0]], points[triangles[:, 1]], points[triangles[:, 2]]
    normals = np.cross(b - a, c - a)
    lengths = np.linalg.norm(normals, axis=1)
    valid = lengths > 0
    cosine = (normals[valid] @ normal) / lengths[valid]
    if len(cosine) == 0:
        return True
    if np.mean(cosine) < 0:
        cosine = -cosine
    # steeper than ~60 degrees squeezes the parameterization; any fold breaks it
    return bool(np.mean(cosine < 0.5) < 0.01 and np.mean(cosine < 0.0) < 0.001)


def _aligned(uv: np.ndarray) -> np.ndarray:
    """Turn the (u, v) so the patch rectangle follows the selection's principal directions."""

    center = uv.mean(axis=0)
    _s, _v, axes = np.linalg.svd(uv - center, full_matrices=False)
    return (uv - center) @ axes.T


def conformal_map(points: np.ndarray, triangles: np.ndarray) -> np.ndarray | None:
    """Least-squares conformal map (Levy et al. 2002) of the largest connected piece.

    Vertices outside that piece (a selection split by a scan hole) are placed by their nearest
    mapped vertex; parameter correction then moves them to their foot points.
    """

    from scipy.sparse import coo_matrix, csr_matrix
    from scipy.sparse.csgraph import connected_components
    from scipy.sparse.linalg import spsolve

    n = len(points)
    edges = np.vstack([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]])
    graph = csr_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(n, n))
    _count, labels = connected_components(graph, directed=False)
    used = np.zeros(n, dtype=bool)
    used[triangles.ravel()] = True
    largest = int(np.argmax(np.bincount(labels[used])))
    keep = labels[triangles[:, 0]] == largest
    tris = triangles[keep]
    vertices = np.unique(tris)
    if len(vertices) < 3 or len(tris) < 1:
        return None
    local = np.full(n, -1, dtype=np.int64)
    local[vertices] = np.arange(len(vertices))
    t = local[tris]
    p = points[vertices]

    p0, p1, p2 = p[t[:, 0]], p[t[:, 1]], p[t[:, 2]]
    x_axis = p1 - p0
    x_length = np.linalg.norm(x_axis, axis=1)
    normal = np.cross(p1 - p0, p2 - p0)
    double_area = np.linalg.norm(normal, axis=1)
    good = (x_length > 1e-12) & (double_area > 1e-12)
    t, p0, p1, p2, x_axis, x_length, normal, double_area = (
        t[good], p0[good], p1[good], p2[good], x_axis[good], x_length[good], normal[good], double_area[good]
    )
    if len(t) == 0:
        return None
    x_axis /= x_length[:, None]
    y_axis = np.cross(normal / double_area[:, None], x_axis)
    q = np.zeros((len(t), 3, 2))
    q[:, 1, 0] = x_length
    q[:, 2, 0] = np.einsum("ij,ij->i", p2 - p0, x_axis)
    q[:, 2, 1] = np.einsum("ij,ij->i", p2 - p0, y_axis)
    weight = 1.0 / np.sqrt(double_area)
    rows, cols, values = [], [], []
    m = len(vertices)
    for j in range(3):
        k, l_ = (j + 1) % 3, (j + 2) % 3
        a = (q[:, l_, 0] - q[:, k, 0]) * weight  # E_j = q_l - q_k, as a + ib
        b = (q[:, l_, 1] - q[:, k, 1]) * weight
        triangle_rows = np.arange(len(t))
        vertex = t[:, j]
        # real part: a*u - b*v ; imaginary part: b*u + a*v
        rows += [2 * triangle_rows, 2 * triangle_rows, 2 * triangle_rows + 1, 2 * triangle_rows + 1]
        cols += [vertex, vertex + m, vertex, vertex + m]
        values += [a, -b, b, a]
    matrix = coo_matrix(
        (np.concatenate(values), (np.concatenate(rows), np.concatenate(cols))), shape=(2 * len(t), 2 * m)
    ).tocsc()

    centroid = p.mean(axis=0)
    _s, _v, axes = np.linalg.svd(p - centroid, full_matrices=False)
    along = (p - centroid) @ axes[0]
    pin_a, pin_b = int(np.argmin(along)), int(np.argmax(along))
    if pin_a == pin_b:
        return None
    pinned = np.array([pin_a, pin_b, pin_a + m, pin_b + m])
    pinned_values = np.array([0.0, float(np.linalg.norm(p[pin_b] - p[pin_a])), 0.0, 0.0])
    free = np.setdiff1d(np.arange(2 * m), pinned)
    a_free = matrix[:, free]
    rhs = -(matrix[:, pinned] @ pinned_values)
    try:
        solution = spsolve((a_free.T @ a_free).tocsc(), a_free.T @ rhs)
    except Exception:  # a singular system (degenerate selection) falls back to the plane
        return None
    if not np.all(np.isfinite(solution)):
        return None
    full = np.zeros(2 * m)
    full[free] = solution
    full[pinned] = pinned_values
    uv_local = np.c_[full[:m], full[m:]]

    uv = np.zeros((n, 2))
    uv[vertices] = uv_local
    missing = np.setdiff1d(np.arange(n), vertices)
    if len(missing):
        from scipy.spatial import cKDTree

        _distance, nearest = cKDTree(p).query(points[missing])
        uv[missing] = uv_local[nearest]
    return uv


# -- the fit ----------------------------------------------------------------------------------


def smoothing_weight(smoothness: float) -> float:
    """Slider 0..1 to the relative weight of the smoothing term (log scale)."""

    smoothness = float(np.clip(smoothness, 0.0, 1.0))
    return float(10.0 ** (-6.0 + 5.0 * smoothness))


def fit_bspline_surface(
    points: object,
    triangles: object | None = None,
    *,
    control_u: int = 8,
    control_v: int = 8,
    degree: int = DEFAULT_DEGREE,
    smoothness: float = 0.25,
    expand: float = 0.1,
    parameterization: str = "auto",
    corrections: int = 3,
    seed: int = 0,
) -> BSplineSurfaceFit:
    """Fit a B-spline surface to ``points`` (an area of the scan).

    ``triangles`` (indices into ``points``) enable the conformal parameterization of curved
    areas. ``expand`` enlarges the patch beyond the selection on every side, as a fraction of
    its size, so it can be trimmed against neighbours later.
    """

    data = np.asarray(points, dtype=float).reshape(-1, 3)
    data_ok = np.all(np.isfinite(data), axis=1)
    tris = None if triangles is None else np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
    if not np.all(data_ok):
        if tris is not None:
            tris = tris[np.all(data_ok[tris], axis=1)]
    control_u = max(int(control_u), degree + 1)
    control_v = max(int(control_v), degree + 1)
    if int(np.sum(data_ok)) < max(16, control_u * control_v // 4):
        return BSplineSurfaceFit(False, reason="too few points for this control net; select a larger area or use fewer control points")

    params = parameterize(data, tris, method=parameterization)
    uv = params.uv
    usable = data_ok.copy()
    lower = uv[usable].min(axis=0)
    upper = uv[usable].max(axis=0)
    size = upper - lower
    if np.any(size <= 1e-9):
        return BSplineSurfaceFit(False, reason="the selected area is degenerate (a line or a point)")
    margin = max(0.0, float(expand)) * size
    knots_u = clamped_uniform_knots(control_u, degree, lower[0] - margin[0], upper[0] + margin[0])
    knots_v = clamped_uniform_knots(control_v, degree, lower[1] - margin[1], upper[1] + margin[1])

    index = np.nonzero(usable)[0]
    if len(index) > MAX_FIT_POINTS:
        index = np.sort(np.random.default_rng(seed).choice(index, MAX_FIT_POINTS, replace=False))
    fit_points = data[index]
    u, v = uv[index, 0].copy(), uv[index, 1].copy()

    fit = BSplineSurfaceFit(
        True,
        degree_u=degree,
        degree_v=degree,
        knots_u=knots_u,
        knots_v=knots_v,
        poles=np.zeros((control_u, control_v, 3)),
        parameterization=params.method,
    )
    rows = _smoothing_rows(control_u, control_v)
    weight = smoothing_weight(smoothness)
    for iteration in range(max(0, int(corrections)) + 1):
        fit.poles = _solve_poles(fit, u, v, fit_points, rows, weight)
        if iteration < corrections:
            u, v = fit._project(fit_points, u, v, iterations=3)

    distances = fit.distances(data[usable])
    fit.rms = float(np.sqrt(np.mean(distances**2)))
    fit.max_error = float(np.max(distances))
    fit.point_count = int(np.sum(usable))
    if params.warnings:
        fit.reason = "; ".join(params.warnings)
    return fit


def _design_matrix(fit: BSplineSurfaceFit, u: np.ndarray, v: np.ndarray) -> Any:
    from scipy.sparse import csr_matrix

    span_u, basis_u, _ = basis_functions(fit.knots_u, fit.degree_u, u)
    span_v, basis_v, _ = basis_functions(fit.knots_v, fit.degree_v, v)
    nu, nv = fit.poles.shape[:2]
    index_u = span_u[:, None] - fit.degree_u + np.arange(fit.degree_u + 1)[None, :]
    index_v = span_v[:, None] - fit.degree_v + np.arange(fit.degree_v + 1)[None, :]
    columns = (index_u[:, :, None] * nv + index_v[:, None, :]).reshape(len(u), -1)
    values = (basis_u[:, :, None] * basis_v[:, None, :]).reshape(len(u), -1)
    rows = np.repeat(np.arange(len(u)), columns.shape[1])
    return csr_matrix((values.ravel(), (rows, columns.ravel())), shape=(len(u), nu * nv))


def _difference(count: int, order: int) -> np.ndarray:
    matrix = np.eye(count)
    for _ in range(order):
        matrix = np.diff(matrix, axis=0)
    return matrix


def _smoothing_rows(nu: int, nv: int) -> np.ndarray:
    """Second differences along u and v and the mixed difference, on the control net."""

    return np.vstack(
        [
            np.kron(_difference(nu, 2), np.eye(nv)),
            np.kron(np.eye(nu), _difference(nv, 2)),
            np.sqrt(2.0) * np.kron(_difference(nu, 1), _difference(nv, 1)),
        ]
    )


UNSUPPORTED_STIFFNESS = 1e3  # how much harder the net is held straight where no data reaches it


def _supported_penalty(rows: np.ndarray, support: np.ndarray) -> np.ndarray:
    """The smoothing term, much stiffer on poles with little data under them.

    Poles in the "expand" margin, in empty corners of the patch rectangle and over scan holes
    are pinned only by smoothing. A light smoothing term lets them swing (an extended knob
    patch strayed 28 mm from the true surface 2 mm past its data; now 90% stays within 1.5 mm); a stiff one continues the surface straight on from its
    supported part, which is what extending a surface should do.
    """

    supported = support[support > 0]
    reference = 0.5 * float(np.median(supported)) if len(supported) else 1.0
    lack = np.clip(1.0 - support / reference, 0.0, 1.0)  # 0 well supported .. 1 no data
    involved = np.abs(rows) > 0
    # stiff only where every pole of the stencil lacks data: a stencil reaching into the data
    # keeps its normal weight, so the supported edge of the patch still fits the scan
    row_lack = np.min(np.where(involved, lack[None, :], 1.0), axis=1)
    weights = 1.0 + UNSUPPORTED_STIFFNESS * row_lack**2
    return rows.T @ (weights[:, None] * rows)


def _solve_poles(
    fit: BSplineSurfaceFit,
    u: np.ndarray,
    v: np.ndarray,
    points: np.ndarray,
    rows: np.ndarray,
    weight: float,
) -> np.ndarray:
    from scipy.linalg import solve

    design = _design_matrix(fit, u, v)
    normal = (design.T @ design).toarray()
    support = np.asarray(design.sum(axis=0)).ravel()
    scale = np.trace(normal) / max(float(np.sum(rows * rows)), 1e-12)
    system = normal + weight * scale * _supported_penalty(rows, support)
    rhs = design.T @ points
    try:
        solution = solve(system, rhs, assume_a="pos")
    except Exception:  # not positive definite (no data near some poles): least squares instead
        solution = np.linalg.lstsq(system, rhs, rcond=None)[0]
    nu, nv = fit.poles.shape[:2]
    return solution.reshape(nu, nv, 3)


def fit_grid_surface(
    grid: object,
    u_params: object,
    v_params: object,
    *,
    control_u: int,
    control_v: int,
    degree: int = DEFAULT_DEGREE,
    smoothness: float = 0.05,
) -> BSplineSurfaceFit:
    """A B-spline through a grid of points with known parameters (resampling a surface).

    Used to rebuild a surface over a larger range (Extend): the same smoothed least squares
    as the scan fit, but no parameterization or correction is needed.
    """

    points = np.asarray(grid, dtype=float)
    count_u, count_v = points.shape[:2]
    u = np.asarray(u_params, dtype=float)
    v = np.asarray(v_params, dtype=float)
    control_u = int(np.clip(control_u, degree + 1, count_u))
    control_v = int(np.clip(control_v, degree + 1, count_v))
    fit = BSplineSurfaceFit(
        True,
        degree_u=degree,
        degree_v=degree,
        knots_u=clamped_uniform_knots(control_u, degree, float(u[0]), float(u[-1])),
        knots_v=clamped_uniform_knots(control_v, degree, float(v[0]), float(v[-1])),
        poles=np.zeros((control_u, control_v, 3)),
        parameterization="grid",
    )
    uu, vv = np.meshgrid(u, v, indexing="ij")
    flat = points.reshape(-1, 3)
    fit.poles = _solve_poles(fit, uu.ravel(), vv.ravel(), flat, _smoothing_rows(control_u, control_v), smoothing_weight(smoothness))
    residual = np.linalg.norm(fit.evaluate(uu.ravel(), vv.ravel()) - flat, axis=1)
    fit.rms = float(np.sqrt(np.mean(residual**2)))
    fit.max_error = float(residual.max())
    fit.point_count = len(flat)
    return fit


def auto_fit_bspline_surface(
    points: object,
    triangles: object | None = None,
    *,
    tolerance: float,
    max_control: int = 24,
    **options: object,
) -> BSplineSurfaceFit:
    """The smallest square-ish net whose RMS deviation is within ``tolerance`` (the "Auto" button)."""

    best: BSplineSurfaceFit | None = None
    for count in (4, 6, 8, 10, 12, 16, 20, 24, 32):
        if count > max_control:
            break
        fit = fit_bspline_surface(points, triangles, control_u=count, control_v=count, **options)  # type: ignore[arg-type]
        if not fit.success:
            return best or fit
        best = fit
        if fit.rms <= tolerance:
            break
    assert best is not None
    return best


__all__ = (
    "BSplineSurfaceFit",
    "Parameterization",
    "auto_fit_bspline_surface",
    "basis_functions",
    "clamped_uniform_knots",
    "conformal_map",
    "fit_bspline_surface",
    "parameterize",
    "smoothing_weight",
)
