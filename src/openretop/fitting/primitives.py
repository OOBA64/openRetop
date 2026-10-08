"""Exact primitives fitted to scan points: plane, sphere, cylinder, cone, torus (RE-05).

Each fit runs in three stages:

1. **Initial guess** from the points and their normals, using a closed-form property of
   the shape:
   - a cylinder's normals are all perpendicular to its axis;
   - a cone's normals make a constant angle with its axis, and every tangent plane passes
     through the apex;
   - a torus's points, moved inwards by the tube radius, trace the spine circle.
2. **Geometric least squares** (Levenberg-Marquardt) on the true point-to-surface distance,
   so the result is the best fit in millimetres, not an algebraic approximation.
3. **Outlier trimming**: points further than 3 robust standard deviations (or a tolerance)
   are dropped and the fit is repeated. This handles a region that slightly overlaps the
   next face, or scanner spikes.

Every fit returns a :class:`PrimitiveFit` with its parameters, RMS and maximum error and inlier
share. On impossible input (too few points, degenerate geometry) it returns a reason; it
never raises.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

PRIMITIVE_KINDS = ("plane", "sphere", "cylinder", "cone", "torus")
MAX_FIT_POINTS = 3_000  # the refinement uses a random subset (error ~ noise / sqrt(N): 0.0004 mm at 0.02 mm noise); final errors use every point
FINAL_FIT_POINTS = 20_000
CLASSIFY_POINTS = 3_000
MIN_INLIER_FRACTION = 0.9  # a shape that leaves more than 10% of the region unexplained does not fit it
_RNG_SEED = 12345


@dataclass(frozen=True)
class PrimitiveFit:
    kind: str
    success: bool
    params: dict[str, object] = field(default_factory=dict)
    rms: float = math.inf
    max_error: float = math.inf
    inlier_fraction: float = 0.0
    point_count: int = 0
    reason: str = ""

    def describe(self, units: str = "mm") -> str:
        if not self.success:
            return f"{self.kind}: {self.reason}"
        p = self.params
        if self.kind == "plane":
            core = f"normal {_vec(p['normal'])}"
        elif self.kind == "sphere":
            core = f"radius {p['radius']:.4f} {units}"
        elif self.kind == "cylinder":
            core = f"radius {p['radius']:.4f} {units}, axis {_vec(p['axis'])}"
        elif self.kind == "cone":
            core = f"half-angle {p['half_angle_degrees']:.3f} deg, axis {_vec(p['axis'])}"
        else:
            core = f"radii {p['major_radius']:.4f} / {p['minor_radius']:.4f} {units}"
        return f"{self.kind}: {core}; RMS {self.rms:.4f} {units}, max {self.max_error:.4f} {units}"


def _vec(value: object) -> str:
    return "(" + ", ".join(f"{float(v):.4f}" for v in np.asarray(value, dtype=float)) + ")"


# -- public API ------------------------------------------------------------------------


def fit_primitive(kind: str, points: object, normals: object | None = None, *, outlier_tolerance: float | None = None) -> PrimitiveFit:
    fitter = {"plane": fit_plane, "sphere": fit_sphere, "cylinder": fit_cylinder, "cone": fit_cone, "torus": fit_torus}.get(kind)
    if fitter is None:
        return PrimitiveFit(kind, False, reason=f"unknown primitive '{kind}'")
    return fitter(points, normals, outlier_tolerance=outlier_tolerance)


def fit_plane(points: object, normals: object | None = None, *, outlier_tolerance: float | None = None) -> PrimitiveFit:
    del normals
    return _robust("plane", points, None, 3, _plane_from, _plane_distance, outlier_tolerance)


def fit_sphere(points: object, normals: object | None = None, *, outlier_tolerance: float | None = None) -> PrimitiveFit:
    return _robust("sphere", points, normals, 4, _sphere_from, _sphere_distance, outlier_tolerance)


def fit_cylinder(points: object, normals: object | None = None, *, outlier_tolerance: float | None = None) -> PrimitiveFit:
    return _robust("cylinder", points, normals, 6, _cylinder_from, _cylinder_distance, outlier_tolerance)


def fit_cone(points: object, normals: object | None = None, *, outlier_tolerance: float | None = None) -> PrimitiveFit:
    return _robust("cone", points, normals, 6, _cone_from, _cone_distance, outlier_tolerance)


def fit_torus(points: object, normals: object | None = None, *, outlier_tolerance: float | None = None) -> PrimitiveFit:
    return _robust("torus", points, normals, 8, _torus_from, _torus_distance, outlier_tolerance)


def classify_region(points: object, normals: object | None, *, tolerance: float) -> tuple[str, PrimitiveFit | None, dict[str, PrimitiveFit]]:
    """The simplest primitive that fits within ``tolerance`` (RMS), or 'freeform'.

    Tries plane, then cylinder, sphere, cone and torus on a subsample and stops at the first
    that fits, so a region is never described with more parameters than it needs.
    Returns (kind, fit or None, every fit tried).
    """

    xyz = np.asarray(points, dtype=float).reshape(-1, 3)
    nrm = None if normals is None else np.asarray(normals, dtype=float).reshape(-1, 3)
    if len(xyz) > CLASSIFY_POINTS:  # deciding the type needs far fewer points than the final fit
        pick = np.random.default_rng(_RNG_SEED).choice(len(xyz), size=CLASSIFY_POINTS, replace=False)
        xyz = xyz[pick]
        nrm = None if nrm is None else nrm[pick]
    fits: dict[str, PrimitiveFit] = {}
    # simplest first, and stop at the first that fits: a plane is never "a huge cylinder", a
    # cylinder never "a cone of tiny angle" (Occam: extra parameters only fit the noise)
    for kind in ("plane", "cylinder", "sphere", "cone", "torus"):
        fit = fit_primitive(kind, xyz, nrm)
        fits[kind] = fit
        if fit.success and fit.rms <= tolerance and fit.inlier_fraction >= MIN_INLIER_FRACTION:
            return kind, fit, fits
    return "freeform", None, fits


def primitive_distance(fit: PrimitiveFit, points: object) -> np.ndarray:
    """Signed distance from each point to the fitted surface (mm)."""

    xyz = np.asarray(points, dtype=float).reshape(-1, 3)
    return _DISTANCES[fit.kind](fit.params, xyz)


def primitive_normal(fit: PrimitiveFit, points: object) -> np.ndarray:
    """Unit surface normal of the fitted primitive at the foot of each point (sign arbitrary)."""

    xyz = np.asarray(points, dtype=float).reshape(-1, 3)
    p = fit.params
    if fit.kind == "plane":
        return np.tile(np.asarray(p["normal"], dtype=float), (len(xyz), 1))
    if fit.kind == "sphere":
        return _unit_rows(xyz - np.asarray(p["center"]))
    if fit.kind == "cylinder":
        axis = np.asarray(p["axis"])
        offset = xyz - np.asarray(p["point"])
        return _unit_rows(offset - np.outer(offset @ axis, axis))
    if fit.kind == "cone":
        axis = np.asarray(p["axis"])
        half = math.radians(float(p["half_angle_degrees"]))  # type: ignore[arg-type]
        offset = xyz - np.asarray(p["apex"])
        radial = _unit_rows(offset - np.outer(offset @ axis, axis))
        return _unit_rows(radial * math.cos(half) - axis * math.sin(half))
    if fit.kind == "torus":
        axis = np.asarray(p["axis"])
        offset = xyz - np.asarray(p["center"])
        radial = _unit_rows(offset - np.outer(offset @ axis, axis))
        spine = np.asarray(p["center"]) + radial * float(p["major_radius"])  # type: ignore[arg-type]
        return _unit_rows(xyz - spine)
    raise ValueError(f"no normal for {fit.kind}")


# -- the robust loop -------------------------------------------------------------------


def _robust(kind, points, normals, min_points, initial_and_refine, distance, outlier_tolerance) -> PrimitiveFit:
    try:
        xyz = np.asarray(points, dtype=float).reshape(-1, 3)
        nrm = None if normals is None else np.asarray(normals, dtype=float).reshape(-1, 3)
    except (TypeError, ValueError):
        return PrimitiveFit(kind, False, reason="points must be an (N, 3) array")
    finite = np.all(np.isfinite(xyz), axis=1)
    if nrm is not None:
        if len(nrm) != len(xyz):
            nrm = None
        else:
            finite &= np.all(np.isfinite(nrm), axis=1)
    xyz = xyz[finite]
    nrm = None if nrm is None else _unit_rows(nrm[finite])
    if len(xyz) < max(min_points, 3):
        return PrimitiveFit(kind, False, point_count=len(xyz), reason=f"needs at least {max(min_points, 3)} points")

    rng = np.random.default_rng(_RNG_SEED)
    inliers = np.ones(len(xyz), dtype=bool)
    params: dict[str, object] | None = None
    for _round in range(3):
        index = np.nonzero(inliers)[0]
        if len(index) > MAX_FIT_POINTS:
            index = rng.choice(index, size=MAX_FIT_POINTS, replace=False)
        try:
            params = initial_and_refine(xyz[index], None if nrm is None else nrm[index], params)
        except (np.linalg.LinAlgError, ValueError, FloatingPointError) as exc:
            return PrimitiveFit(kind, False, point_count=len(xyz), reason=f"degenerate data ({exc})")
        if params is None:
            return PrimitiveFit(kind, False, point_count=len(xyz), reason="the points do not determine this shape")
        residual = np.abs(distance(params, xyz))
        sigma = 1.4826 * float(np.median(residual[inliers])) + 1e-12  # robust standard deviation
        limit = outlier_tolerance if outlier_tolerance is not None else max(3.0 * sigma, 1e-9)
        next_inliers = residual <= limit
        if next_inliers.sum() < max(min_points, 3) or np.array_equal(next_inliers, inliers):
            break
        inliers = next_inliers
    assert params is not None
    # one last refinement from the converged answer on many more inliers: an axis is pinned
    # by the length of the face and the point count, so short cylinders need the extra points
    final_index = np.nonzero(inliers)[0]
    if len(final_index) > MAX_FIT_POINTS:
        if len(final_index) > FINAL_FIT_POINTS:
            final_index = rng.choice(final_index, size=FINAL_FIT_POINTS, replace=False)
        try:
            refined = initial_and_refine(xyz[final_index], None if nrm is None else nrm[final_index], params)
        except (np.linalg.LinAlgError, ValueError, FloatingPointError):
            refined = None
        if refined is not None:
            params = refined
    residual = np.abs(distance(params, xyz))
    used = residual[inliers]
    return PrimitiveFit(
        kind,
        True,
        params=params,
        rms=float(np.sqrt(np.mean(used**2))),
        max_error=float(used.max()),
        inlier_fraction=float(inliers.mean()),
        point_count=int(len(xyz)),
    )


def _least_squares(fun, x0, jac=None):
    from scipy.optimize import least_squares

    # Analytic Jacobians: a finite-difference Jacobian costs one residual evaluation per
    # parameter and dominated segmentation time. A fit that has not converged in this many
    # evaluations is not this shape (e.g. a torus tried on freeform): give up quickly.
    result = least_squares(fun, x0, jac="2-point" if jac is None else jac, method="lm", x_scale="jac", max_nfev=40 * (len(x0) + 1))
    return result.x


def _axis_derivatives(theta: float, phi: float) -> tuple[np.ndarray, np.ndarray]:
    """d(axis)/d(theta) and d(axis)/d(phi) for the spherical-angle axis parameterisation."""

    return (
        np.array([math.cos(theta) * math.cos(phi), math.cos(theta) * math.sin(phi), -math.sin(theta)]),
        np.array([-math.sin(theta) * math.sin(phi), math.sin(theta) * math.cos(phi), 0.0]),
    )


# -- geometry helpers ------------------------------------------------------------------


def _unit_rows(vectors: np.ndarray) -> np.ndarray:
    lengths = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.maximum(lengths, 1e-15)


def _unit(vector: np.ndarray) -> np.ndarray:
    return vector / max(float(np.linalg.norm(vector)), 1e-15)


def _angles_to_axis(theta: float, phi: float) -> np.ndarray:
    return np.array([math.sin(theta) * math.cos(phi), math.sin(theta) * math.sin(phi), math.cos(theta)])


def _axis_to_angles(axis: np.ndarray) -> tuple[float, float]:
    axis = _unit(axis)
    return math.acos(max(-1.0, min(1.0, float(axis[2])))), math.atan2(float(axis[1]), float(axis[0]))


def _canonical_axis(axis: np.ndarray) -> np.ndarray:
    """An axis has no direction: report the one pointing into the positive half-space."""

    axis = _unit(np.asarray(axis, dtype=float))
    for component in axis[::-1]:
        if abs(component) > 1e-9:
            return axis if component > 0 else -axis
    return axis


def _basis(axis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    helper = np.array([1.0, 0.0, 0.0]) if abs(axis[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = _unit(np.cross(axis, helper))
    return u, np.cross(axis, u)


def _circle_2d(xy: np.ndarray) -> tuple[np.ndarray, float]:
    """Kasa algebraic circle fit (a good start for the geometric refinement)."""

    a = np.column_stack([2.0 * xy, np.ones(len(xy))])
    b = np.sum(xy**2, axis=1)
    solution, *_ = np.linalg.lstsq(a, b, rcond=None)
    center = solution[:2]
    radius = math.sqrt(max(float(solution[2] + center @ center), 0.0))
    return center, radius


def _closest_to_axis(point: np.ndarray, origin: np.ndarray, axis: np.ndarray) -> np.ndarray:
    return origin + axis * float((point - origin) @ axis)


# -- plane -----------------------------------------------------------------------------


def _plane_from(points, _normals, _previous):
    centroid = points.mean(axis=0)
    _u, _s, vt = np.linalg.svd(points - centroid, full_matrices=False)
    normal = _canonical_axis(vt[-1])
    return {"normal": normal, "point": centroid, "offset": float(normal @ centroid)}


def _plane_distance(params, points):
    return (points - params["point"]) @ params["normal"]


# -- sphere ----------------------------------------------------------------------------


def _sphere_from(points, _normals, previous):
    if previous is None:
        a = np.column_stack([2.0 * points, np.ones(len(points))])
        b = np.sum(points**2, axis=1)
        solution, *_ = np.linalg.lstsq(a, b, rcond=None)
        center = solution[:3]
        radius = math.sqrt(max(float(solution[3] + center @ center), 1e-12))
    else:
        center, radius = np.asarray(previous["center"]), float(previous["radius"])
    def sphere_jacobian(v):
        offset = points - v[:3]
        length = np.maximum(np.linalg.norm(offset, axis=1, keepdims=True), 1e-15)
        return np.column_stack([-offset / length, -np.ones(len(points))])

    x = _least_squares(lambda v: np.linalg.norm(points - v[:3], axis=1) - v[3], np.r_[center, radius], sphere_jacobian)
    if not np.all(np.isfinite(x)) or x[3] <= 0:
        return None
    return {"center": x[:3], "radius": float(abs(x[3]))}


def _sphere_distance(params, points):
    return np.linalg.norm(points - params["center"], axis=1) - params["radius"]


# -- cylinder --------------------------------------------------------------------------


def _cylinder_axis_guess(points: np.ndarray, normals: np.ndarray | None) -> np.ndarray:
    if normals is not None and len(normals) >= 3:
        # every normal is perpendicular to the axis: the axis is the normals' null direction
        _u, _s, vt = np.linalg.svd(normals, full_matrices=False)
        return _unit(vt[-1])
    # without normals: the longest spread of the points is usually along the axis
    _u, _s, vt = np.linalg.svd(points - points.mean(axis=0), full_matrices=False)
    return _unit(vt[0])


def _cylinder_from(points, normals, previous):
    if previous is None:
        axis = _cylinder_axis_guess(points, normals)
        u, v = _basis(axis)
        local = np.column_stack([(points - points.mean(axis=0)) @ u, (points - points.mean(axis=0)) @ v])
        center_2d, radius = _circle_2d(local)
        origin = points.mean(axis=0) + u * center_2d[0] + v * center_2d[1]
    else:
        axis, origin, radius = np.asarray(previous["axis"]), np.asarray(previous["point"]), float(previous["radius"])
    if not math.isfinite(radius) or radius <= 0:
        return None
    # parameters: axis angles (2), the axis point in the plane through the start point
    # perpendicular to the axis (2 offsets along a fixed basis), radius
    theta0, phi0 = _axis_to_angles(axis)
    u0, v0 = _basis(axis)
    base = origin.copy()

    def residual(x):
        axis_now = _angles_to_axis(x[0], x[1])
        origin_now = base + u0 * x[2] + v0 * x[3]
        offset = points - origin_now
        radial = offset - np.outer(offset @ axis_now, axis_now)
        return np.linalg.norm(radial, axis=1) - x[4]

    def jacobian(x):
        axis_now = _angles_to_axis(x[0], x[1])
        d_theta, d_phi = _axis_derivatives(x[0], x[1])
        offset = points - (base + u0 * x[2] + v0 * x[3])
        height = offset @ axis_now
        radial = offset - np.outer(height, axis_now)
        direction = radial / np.maximum(np.linalg.norm(radial, axis=1, keepdims=True), 1e-15)
        d_axis = -height[:, None] * direction  # d(rho)/d(axis)
        return np.column_stack([d_axis @ d_theta, d_axis @ d_phi, -(direction @ u0), -(direction @ v0), -np.ones(len(points))])

    x = _least_squares(residual, np.array([theta0, phi0, 0.0, 0.0, radius]), jacobian)
    axis_fit = _angles_to_axis(x[0], x[1])
    origin_fit = base + u0 * x[2] + v0 * x[3]
    if not np.all(np.isfinite(x)) or x[4] <= 0:
        return None
    axis_fit = _canonical_axis(axis_fit)
    origin_fit = _closest_to_axis(points.mean(axis=0), origin_fit, axis_fit)  # the axis point nearest the data
    return {"axis": axis_fit, "point": origin_fit, "radius": float(x[4])}


def _cylinder_distance(params, points):
    offset = points - params["point"]
    axis = params["axis"]
    radial = offset - np.outer(offset @ axis, axis)
    return np.linalg.norm(radial, axis=1) - params["radius"]


# -- cone ------------------------------------------------------------------------------


def _cone_from(points, normals, previous):
    if previous is None:
        if normals is None or len(normals) < 6:
            return None  # a cone cannot be told from a cylinder or plane without normals
        # the normals lie on a cone around the axis: their tips lie on a plane whose normal is the axis
        tips_center = normals.mean(axis=0)
        _u, _s, vt = np.linalg.svd(normals - tips_center, full_matrices=False)
        axis = _unit(vt[-1])
        cosine = float(np.mean(normals @ axis))  # = +-sin(half angle)
        half_angle = math.asin(min(abs(cosine), 0.999))
        if half_angle < math.radians(0.2):
            return None  # really a cylinder
        # every tangent plane passes through the apex: n . apex = n . p
        apex, *_ = np.linalg.lstsq(normals, np.sum(normals * points, axis=1), rcond=None)
        # point the axis from the apex into the data
        if float(np.mean((points - apex) @ axis)) < 0:
            axis = -axis
    else:
        apex, axis, half_angle = np.asarray(previous["apex"]), np.asarray(previous["axis"]), math.radians(float(previous["half_angle_degrees"]))
    theta0, phi0 = _axis_to_angles(axis)

    def residual(x):
        axis_now = _angles_to_axis(x[3], x[4])
        offset = points - x[:3]
        height = offset @ axis_now
        radial = np.linalg.norm(offset - np.outer(height, axis_now), axis=1)
        return radial * math.cos(x[5]) - height * math.sin(x[5])

    def jacobian(x):
        axis_now = _angles_to_axis(x[3], x[4])
        d_theta, d_phi = _axis_derivatives(x[3], x[4])
        cos_half, sin_half = math.cos(x[5]), math.sin(x[5])
        offset = points - x[:3]
        height = offset @ axis_now
        radial = offset - np.outer(height, axis_now)
        rho = np.maximum(np.linalg.norm(radial, axis=1), 1e-15)
        direction = radial / rho[:, None]
        d_apex = -(cos_half * direction - sin_half * axis_now)
        d_axis = cos_half * (-height[:, None] * direction) - sin_half * offset
        d_half = -rho * sin_half - height * cos_half
        return np.column_stack([d_apex, d_axis @ d_theta, d_axis @ d_phi, d_half])

    x = _least_squares(residual, np.r_[apex, theta0, phi0, half_angle], jacobian)
    if not np.all(np.isfinite(x)):
        return None
    half = float(x[5])
    axis_fit = _angles_to_axis(x[3], x[4])
    if half < 0:
        half, axis_fit = -half, -axis_fit
    if not (math.radians(0.2) < half < math.radians(89.0)):
        return None
    return {"apex": x[:3], "axis": axis_fit, "half_angle_degrees": math.degrees(half)}


def _cone_distance(params, points):
    axis = params["axis"]
    half = math.radians(float(params["half_angle_degrees"]))
    offset = points - params["apex"]
    height = offset @ axis
    radial = np.linalg.norm(offset - np.outer(height, axis), axis=1)
    return radial * math.cos(half) - height * math.sin(half)


# -- torus -----------------------------------------------------------------------------


def _torus_from(points, normals, previous):
    if previous is None:
        if normals is None or len(normals) < 8:
            return None
        from scipy.optimize import minimize_scalar

        extent = float(np.linalg.norm(points.max(axis=0) - points.min(axis=0)))

        def spine_error(minor: float) -> float:
            spine = points - normals * minor
            return _circle_3d(spine)[3]

        # the tube radius is where stepping inwards along the normals gives the best circle
        candidates: list[tuple[float, float]] = []
        for sign in (1.0, -1.0):  # normals may point out of or into the tube
            result = minimize_scalar(
                lambda r, s=sign: spine_error(s * r), bounds=(1e-3 * extent, extent), method="bounded"
            )
            candidates.append((sign * float(result.x), float(result.fun)))
        minor = min(candidates, key=lambda item: item[1])[0]
        center, axis, major, _error = _circle_3d(points - normals * minor)
        minor = abs(minor)
    else:
        center, axis = np.asarray(previous["center"]), np.asarray(previous["axis"])
        major, minor = float(previous["major_radius"]), float(previous["minor_radius"])
    theta0, phi0 = _axis_to_angles(axis)

    def residual(x):
        axis_now = _angles_to_axis(x[3], x[4])
        offset = points - x[:3]
        height = offset @ axis_now
        radial = np.linalg.norm(offset - np.outer(height, axis_now), axis=1)
        return np.hypot(radial - x[5], height) - x[6]

    def jacobian(x):
        axis_now = _angles_to_axis(x[3], x[4])
        d_theta, d_phi = _axis_derivatives(x[3], x[4])
        offset = points - x[:3]
        height = offset @ axis_now
        radial = offset - np.outer(height, axis_now)
        rho = np.maximum(np.linalg.norm(radial, axis=1), 1e-15)
        direction = radial / rho[:, None]
        tube = np.maximum(np.hypot(rho - x[5], height), 1e-15)
        along_rho, along_height = (rho - x[5]) / tube, height / tube
        d_center = -(along_rho[:, None] * direction + along_height[:, None] * axis_now)
        d_axis = along_rho[:, None] * (-height[:, None] * direction) + along_height[:, None] * offset
        return np.column_stack([d_center, d_axis @ d_theta, d_axis @ d_phi, -along_rho, -np.ones(len(points))])

    x = _least_squares(residual, np.r_[center, theta0, phi0, major, minor], jacobian)
    if not np.all(np.isfinite(x)) or x[5] <= 0 or x[6] <= 0:
        return None
    return {"center": x[:3], "axis": _canonical_axis(_angles_to_axis(x[3], x[4])), "major_radius": float(x[5]), "minor_radius": float(x[6])}


def _circle_3d(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Best circle through 3D points: (center, plane normal, radius, RMS error)."""

    centroid = points.mean(axis=0)
    _u, _s, vt = np.linalg.svd(points - centroid, full_matrices=False)
    normal = _unit(vt[-1])
    u, v = _basis(normal)
    local = np.column_stack([(points - centroid) @ u, (points - centroid) @ v])
    center_2d, radius = _circle_2d(local)
    center = centroid + u * center_2d[0] + v * center_2d[1]
    in_plane = np.linalg.norm(local - center_2d, axis=1) - radius
    off_plane = (points - centroid) @ normal
    return center, normal, radius, float(np.sqrt(np.mean(in_plane**2 + off_plane**2)))


def _torus_distance(params, points):
    axis = params["axis"]
    offset = points - params["center"]
    height = offset @ axis
    radial = np.linalg.norm(offset - np.outer(height, axis), axis=1)
    return np.hypot(radial - params["major_radius"], height) - params["minor_radius"]


_DISTANCES = {
    "plane": _plane_distance,
    "sphere": _sphere_distance,
    "cylinder": _cylinder_distance,
    "cone": _cone_distance,
    "torus": _torus_distance,
}


__all__ = (
    "PRIMITIVE_KINDS",
    "PrimitiveFit",
    "classify_region",
    "primitive_distance",
    "primitive_normal",
    "fit_cone",
    "fit_cylinder",
    "fit_plane",
    "fit_primitive",
    "fit_sphere",
    "fit_torus",
)
