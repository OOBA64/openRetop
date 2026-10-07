"""Tolerance-driven B-spline approximation of 3D point sequences.

Open data is fitted with a clamped B-spline that passes through its end points.
Closed data is fitted with a periodic B-spline (uniform knots, wrapped control
points), so a closed curve has no seam kink. The number of control points is the
smallest that keeps every data point within ``tolerance`` of the curve.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DEFAULT_DEGREE = 3
MAX_CONTROL_POINTS = 600
DEFAULT_CORNER_ANGLE_DEGREES = 50.0
_DISTANCE_CHUNK_ELEMENTS = 2_000_000


@dataclass(frozen=True)
class BSplineFit:
    """A fitted spline plus how well it matches the data it was fitted to."""

    poles: np.ndarray  # (n, 3) control points; for periodic curves, one period only
    knots: np.ndarray  # full knot vector (clamped) or uniform period knots
    degree: int
    periodic: bool
    max_error: float
    mean_error: float
    source_point_count: int

    @property
    def domain(self) -> tuple[float, float]:
        if self.periodic:
            return (0.0, 1.0)
        return (float(self.knots[self.degree]), float(self.knots[len(self.poles)]))

    def evaluate(self, parameters: np.ndarray) -> np.ndarray:
        """Evaluate at parameters in ``domain`` (periodic ones wrap)."""

        u = np.asarray(parameters, dtype=float).reshape(-1)
        if self.periodic:
            return _periodic_basis(u, len(self.poles), self.degree) @ self.poles
        basis = _basis_matrix(u, self.knots, self.degree, len(self.poles))
        return basis @ self.poles

    def sample(self, count: int) -> np.ndarray:
        """Return ``count`` points along the curve; closed curves repeat the first point."""

        count = max(int(count), 2)
        start, end = self.domain
        if self.periodic:
            params = np.linspace(start, end, count, endpoint=True)
            points = self.evaluate(params[:-1] % 1.0)
            return np.vstack([points, points[:1]])
        return self.evaluate(np.linspace(start, end, count))

    def occ_knots_and_multiplicities(self) -> tuple[list[float], list[int]]:
        """Knots in OpenCascade's (distinct value, multiplicity) form."""

        distinct: list[float] = []
        mults: list[int] = []
        for value in self.knots:
            if distinct and abs(value - distinct[-1]) < 1e-12:
                mults[-1] += 1
            else:
                distinct.append(float(value))
                mults.append(1)
        return distinct, mults


def fit_bspline(
    points: np.ndarray,
    *,
    tolerance: float,
    closed: bool | None = None,
    degree: int = DEFAULT_DEGREE,
    max_control_points: int = MAX_CONTROL_POINTS,
) -> BSplineFit:
    """Fit a B-spline that stays within ``tolerance`` of ``points``.

    ``closed`` defaults to whether the first and last point coincide. For closed
    data the repeated end point is dropped. Raises ValueError if fewer than two
    distinct points remain.
    """

    if not tolerance > 0.0:
        raise ValueError("tolerance must be positive.")
    data = np.asarray(points, dtype=float).reshape((-1, 3))
    if not np.all(np.isfinite(data)):
        raise ValueError("Curve points must be finite.")
    data = _drop_consecutive_duplicates(data)
    if closed is None:
        closed = len(data) >= 3 and bool(np.linalg.norm(data[0] - data[-1]) <= 1e-8)
    if closed and len(data) >= 2 and np.linalg.norm(data[0] - data[-1]) <= 1e-8:
        data = data[:-1]
    minimum = 3 if closed else 2
    if len(data) < minimum:
        raise ValueError(f"Need at least {minimum} distinct points to fit a curve.")

    count = len(data)
    degree = max(1, min(int(degree), count - 1))
    cap = max(degree + 1, min(int(max_control_points), count))
    params = _chord_parameters(data, closed=closed)

    def attempt(control_count: int) -> BSplineFit:
        if closed:
            return _fit_periodic(data, params, control_count, degree)
        return _fit_clamped(data, params, control_count, degree)

    low = degree + 1  # smallest curve we will try
    best: BSplineFit | None = None
    candidate = min(max(low, 6), cap)
    infeasible = low - 1
    previous_error = float("inf")
    while True:
        fit = attempt(candidate)
        if fit.max_error <= tolerance or candidate >= cap:
            best = fit
            break
        if fit.max_error > 0.85 * previous_error and candidate >= 24:
            # More control points no longer help: the tolerance is below the
            # data's noise floor. Keep this fit and report its actual error.
            return fit
        previous_error = fit.max_error
        infeasible = candidate
        candidate = min(cap, max(candidate + 1, int(candidate * 1.5)))

    # Tighten: bisect between the last failing and first passing control count.
    high = len(best.poles)
    while high - infeasible > 1:
        middle = (high + infeasible) // 2
        trial = attempt(middle)
        if trial.max_error <= tolerance:
            best, high = trial, middle
        else:
            infeasible = middle
    return best


@dataclass(frozen=True)
class FittedCurve:
    """One or more joined B-splines approximating a point sequence.

    A smooth closed curve is one periodic spline; a curve with sharp corners is
    split at the corners so each piece is smooth and the corners stay sharp.
    """

    segments: tuple[BSplineFit, ...]
    closed: bool
    max_error: float
    mean_error: float
    source_point_count: int

    def sample(self, points_per_segment_hint: int | None = None) -> np.ndarray:
        """Polyline through the curve; closed curves repeat the first point."""

        pieces: list[np.ndarray] = []
        for segment in self.segments:
            if segment.degree == 1 and len(segment.poles) == 2:
                count = 2  # a straight line needs no interior samples
            else:
                count = points_per_segment_hint or min(
                    max(4 * len(segment.poles), 16), max(segment.source_point_count, 16)
                )
            samples = segment.sample(count)
            pieces.append(samples if not pieces else samples[1:])
        return np.vstack(pieces)


def fit_curve(
    points: np.ndarray,
    *,
    tolerance: float,
    closed: bool | None = None,
    degree: int = DEFAULT_DEGREE,
    corner_angle_degrees: float | None = DEFAULT_CORNER_ANGLE_DEGREES,
    max_control_points: int = MAX_CONTROL_POINTS,
) -> FittedCurve:
    """Fit ``points`` with B-splines within ``tolerance``, splitting at sharp corners.

    Pass ``corner_angle_degrees=None`` to force a single spline.
    """

    data = _drop_consecutive_duplicates(np.asarray(points, dtype=float).reshape((-1, 3)))
    if not np.all(np.isfinite(data)):
        raise ValueError("Curve points must be finite.")
    if closed is None:
        closed = len(data) >= 3 and bool(np.linalg.norm(data[0] - data[-1]) <= 1e-8)
    if closed and len(data) >= 2 and np.linalg.norm(data[0] - data[-1]) <= 1e-8:
        data = data[:-1]

    corners = (
        _corner_indices(data, closed, corner_angle_degrees, tolerance)
        if corner_angle_degrees is not None
        else []
    )
    if not corners:
        fit = fit_bspline(
            data, tolerance=tolerance, closed=closed, degree=degree,
            max_control_points=max_control_points,
        )
        return FittedCurve((fit,), closed, fit.max_error, fit.mean_error, len(data))

    if closed:
        data = np.roll(data, -corners[0], axis=0)
        corners = [(index - corners[0]) % len(data) for index in corners]
        boundaries = corners + [len(data)]
        pieces = [
            np.vstack([data[a : b + 1]]) if b < len(data) else np.vstack([data[a:], data[:1]])
            for a, b in zip(boundaries[:-1], boundaries[1:])
        ]
    else:
        boundaries = [0, *corners, len(data) - 1]
        pieces = [data[a : b + 1] for a, b in zip(boundaries[:-1], boundaries[1:])]

    fits: list[BSplineFit] = []
    for piece in pieces:
        piece = _drop_consecutive_duplicates(piece)
        if len(piece) < 2:
            continue
        fits.append(
            fit_bspline(
                piece, tolerance=tolerance, closed=False, degree=degree,
                max_control_points=max_control_points,
            )
        )
    if not fits:
        raise ValueError("Need at least two distinct points to fit a curve.")
    total = sum(item.source_point_count for item in fits)
    mean = sum(item.mean_error * item.source_point_count for item in fits) / max(total, 1)
    return FittedCurve(
        tuple(fits), closed, max(item.max_error for item in fits), mean, len(data)
    )


def _corner_indices(
    data: np.ndarray, closed: bool, threshold_degrees: float, tolerance: float
) -> list[int]:
    """Vertices where the path turns by at least ``threshold_degrees``.

    The turn is measured between the directions over an arc-length window, so
    scan noise on densely sampled smooth curves does not register as corners.
    Only the strongest turn within one window is kept.
    """

    count = len(data)
    if count < 3:
        return []
    steps = np.linalg.norm(np.diff(data, axis=0), axis=1)
    if len(steps) == 0 or not np.any(steps > 0.0):
        return []
    window = max(20.0 * tolerance, 3.0 * float(np.median(steps[steps > 0.0])))

    if closed:
        ring = np.vstack([data, data[:1]])
        ring_steps = np.linalg.norm(np.diff(ring, axis=0), axis=1)
        perimeter = float(ring_steps.sum())
        if window * 2.0 >= perimeter:
            window = perimeter / 4.0
        tiled = np.vstack([data, data, data])
        arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(tiled, axis=0), axis=1))])
        centre = np.arange(count) + count
        positions = arc[centre]
    else:
        tiled = data
        arc = np.concatenate([[0.0], np.cumsum(steps)])
        centre = np.arange(count)
        positions = arc
    before = np.column_stack([np.interp(positions - window, arc, tiled[:, k]) for k in range(3)])
    after = np.column_stack([np.interp(positions + window, arc, tiled[:, k]) for k in range(3)])
    incoming = tiled[centre] - before
    outgoing = after - tiled[centre]
    norms = np.linalg.norm(incoming, axis=1) * np.linalg.norm(outgoing, axis=1)
    safe = np.where(norms > 0.0, norms, 1.0)
    cosine = np.clip(np.einsum("ij,ij->i", incoming, outgoing) / safe, -1.0, 1.0)
    turn = np.degrees(np.arccos(cosine))
    turn[norms <= 0.0] = 0.0

    base = arc[count : 2 * count] - arc[count] if closed else arc
    perimeter = float(ring_steps.sum()) if closed else 0.0
    accepted: list[int] = []
    for index in np.argsort(-turn):
        if turn[index] < threshold_degrees:
            break
        if not closed and (index == 0 or index == count - 1):
            continue
        too_close = False
        for other in accepted:
            gap = abs(base[index] - base[other])
            if closed:
                gap = min(gap, perimeter - gap)
            if gap < window:
                too_close = True
                break
        if not too_close:
            accepted.append(int(index))
    return sorted(accepted)


def point_to_polyline_distances(points: np.ndarray, polyline: np.ndarray) -> np.ndarray:
    """Distance from each point to the nearest segment of ``polyline`` (vectorised)."""

    points = np.asarray(points, dtype=float).reshape((-1, 3))
    polyline = np.asarray(polyline, dtype=float).reshape((-1, 3))
    if len(polyline) < 2:
        if len(polyline) == 1:
            return np.linalg.norm(points - polyline[0], axis=1)
        return np.zeros(len(points))
    starts = polyline[:-1]
    deltas = polyline[1:] - starts
    lengths_sq = np.einsum("ij,ij->i", deltas, deltas)
    safe = np.where(lengths_sq > 0.0, lengths_sq, 1.0)
    chunk = max(1, _DISTANCE_CHUNK_ELEMENTS // len(starts))
    result = np.empty(len(points))
    for begin in range(0, len(points), chunk):
        block = points[begin : begin + chunk]
        offsets = block[:, None, :] - starts[None, :, :]
        ratio = np.clip(np.einsum("bsk,sk->bs", offsets, deltas) / safe, 0.0, 1.0)
        ratio = np.where(lengths_sq > 0.0, ratio, 0.0)
        nearest = starts[None, :, :] + ratio[:, :, None] * deltas[None, :, :]
        distance_sq = np.einsum("bsk,bsk->bs", block[:, None, :] - nearest, block[:, None, :] - nearest)
        result[begin : begin + chunk] = np.sqrt(distance_sq.min(axis=1))
    return result


# --------------------------------------------------------------------------- fitting


def _drop_consecutive_duplicates(points: np.ndarray) -> np.ndarray:
    if len(points) < 2:
        return points
    keep = np.concatenate([[True], np.linalg.norm(np.diff(points, axis=0), axis=1) > 0.0])
    return points[keep]


def _chord_parameters(points: np.ndarray, *, closed: bool) -> np.ndarray:
    """Centripetal parameters in [0, 1] (closed: [0, 1) with the wrap gap implied)."""

    path = points if not closed else np.vstack([points, points[:1]])
    steps = np.sqrt(np.linalg.norm(np.diff(path, axis=0), axis=1))
    cumulative = np.concatenate([[0.0], np.cumsum(steps)])
    total = cumulative[-1]
    if total <= 0.0:
        return np.linspace(0.0, 1.0, len(path))[: len(points)]
    parameters = cumulative / total
    return parameters[:-1] if closed else parameters


def _fit_clamped(
    data: np.ndarray, params: np.ndarray, control_count: int, degree: int
) -> BSplineFit:
    count = len(data)
    control_count = max(degree + 1, min(control_count, count))
    knots = _approximation_knots(params, control_count, degree)
    basis = _basis_matrix(params, knots, degree, control_count)
    poles = np.zeros((control_count, 3))
    poles[0], poles[-1] = data[0], data[-1]
    if control_count > 2:
        residual = data - np.outer(basis[:, 0], data[0]) - np.outer(basis[:, -1], data[-1])
        solution, *_ = np.linalg.lstsq(basis[1:-1, 1:-1], residual[1:-1], rcond=None)
        poles[1:-1] = solution
    fit = BSplineFit(poles, knots, degree, False, 0.0, 0.0, count)
    return _with_error(fit, data)


def _fit_periodic(
    data: np.ndarray, params: np.ndarray, control_count: int, degree: int
) -> BSplineFit:
    count = len(data)
    control_count = max(degree + 1, min(control_count, count))
    basis = _periodic_basis(params, control_count, degree)
    poles, *_ = np.linalg.lstsq(basis, data, rcond=None)
    knots = np.arange(control_count + 1, dtype=float) / control_count
    fit = BSplineFit(poles, knots, degree, True, 0.0, 0.0, count)
    return _with_error(fit, data)


def _with_error(fit: BSplineFit, data: np.ndarray) -> BSplineFit:
    samples = fit.sample(max(64, 12 * len(fit.poles)))
    distances = point_to_polyline_distances(data, samples)
    return BSplineFit(
        fit.poles,
        fit.knots,
        fit.degree,
        fit.periodic,
        float(distances.max()) if len(distances) else 0.0,
        float(distances.mean()) if len(distances) else 0.0,
        fit.source_point_count,
    )


def _approximation_knots(params: np.ndarray, control_count: int, degree: int) -> np.ndarray:
    """Clamped knot vector from averaging data parameters (Piegl & Tiller 9.69)."""

    interior_count = control_count - degree - 1
    knots = np.concatenate([np.zeros(degree + 1), np.ones(degree + 1)])
    if interior_count <= 0:
        return knots
    spacing = len(params) / (interior_count + 1)
    interior = np.empty(interior_count)
    for j in range(1, interior_count + 1):
        position = j * spacing
        index = int(position)
        alpha = position - index
        interior[j - 1] = (1.0 - alpha) * params[index - 1] + alpha * params[index]
    return np.concatenate([np.zeros(degree + 1), interior, np.ones(degree + 1)])


# ------------------------------------------------------------------------- basis


def _basis_matrix(u: np.ndarray, knots: np.ndarray, degree: int, control_count: int) -> np.ndarray:
    """Dense (len(u), control_count) matrix of B-spline basis values."""

    u = np.asarray(u, dtype=float).reshape(-1)
    count = len(u)
    low, high = knots[degree], knots[control_count]
    clipped = np.clip(u, low, high)
    span = np.searchsorted(knots, clipped, side="right") - 1
    span = np.clip(span, degree, control_count - 1)

    local = np.zeros((count, degree + 1))
    local[:, 0] = 1.0
    left = np.zeros((count, degree + 1))
    right = np.zeros((count, degree + 1))
    for j in range(1, degree + 1):
        left[:, j] = clipped - knots[span + 1 - j]
        right[:, j] = knots[span + j] - clipped
        saved = np.zeros(count)
        for r in range(j):
            denominator = right[:, r + 1] + left[:, j - r]
            safe = np.where(denominator != 0.0, denominator, 1.0)
            ratio = np.where(denominator != 0.0, local[:, r] / safe, 0.0)
            local[:, r] = saved + right[:, r + 1] * ratio
            saved = left[:, j - r] * ratio
        local[:, j] = saved

    matrix = np.zeros((count, control_count))
    rows = np.arange(count)
    for offset in range(degree + 1):
        matrix[rows, span - degree + offset] = local[:, offset]
    return matrix


def _periodic_basis(u: np.ndarray, control_count: int, degree: int) -> np.ndarray:
    """Basis matrix of a uniform periodic B-spline over [0, 1) with wrapped poles."""

    u = np.asarray(u, dtype=float).reshape(-1) % 1.0
    extended = control_count + degree
    knots = (np.arange(extended + degree + 1, dtype=float) - degree) / control_count
    unfolded = _basis_matrix(u, knots, degree, extended)
    folded = unfolded[:, :control_count].copy()
    folded[:, :degree] += unfolded[:, control_count:extended]
    return folded
