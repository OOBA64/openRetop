"""Section-curve fitting: tolerance-driven B-splines instead of corner cutting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from geometry.bspline import FittedCurve, fit_curve
from geometry.sections import SectionPolyline
from geometry.tolerances import curve_fit_tolerance


@dataclass(frozen=True)
class CurveFitResult:
    original_points: np.ndarray
    fitted_points: np.ndarray
    mean_error: float
    max_error: float
    is_closed: bool
    fitted_curve: FittedCurve | None = None
    tolerance: float = 0.0


def fit_section_polylines(
    polylines: Iterable[SectionPolyline],
    *,
    tolerance: float | None = None,
) -> list[CurveFitResult]:
    """Fit a B-spline curve to every usable section polyline.

    ``tolerance`` is the allowed deviation from the section points; when omitted
    it is derived from the size of the polyline's bounding box.
    """

    results: list[CurveFitResult] = []
    for polyline in polylines:
        if len(polyline.points) < 2:
            continue
        results.append(fit_smooth_polyline(polyline.points, tolerance=tolerance))
    return results


def fit_smooth_polyline(
    points: np.ndarray,
    *,
    tolerance: float | None = None,
) -> CurveFitResult:
    """Fit ``points`` with B-splines within ``tolerance``.

    Closed input (first point equals last) yields a closed curve whose sampled
    points start and end on the same point. Fewer than two distinct points are
    returned unchanged with zero error.
    """

    original_points = np.asarray(points, dtype=float).reshape((-1, 3))
    extent = (
        float(np.max(original_points.max(axis=0) - original_points.min(axis=0)))
        if len(original_points)
        else 0.0
    )
    resolved = float(tolerance) if tolerance is not None else curve_fit_tolerance(extent)
    is_closed = _is_closed(original_points)
    try:
        fitted = fit_curve(original_points, tolerance=resolved, closed=is_closed)
    except ValueError:
        return CurveFitResult(
            original_points=original_points,
            fitted_points=original_points.copy(),
            mean_error=0.0,
            max_error=0.0,
            is_closed=is_closed,
            tolerance=resolved,
        )
    return CurveFitResult(
        original_points=original_points,
        fitted_points=fitted.sample(),
        mean_error=fitted.mean_error,
        max_error=fitted.max_error,
        is_closed=is_closed,
        fitted_curve=fitted,
        tolerance=resolved,
    )


def _is_closed(points: np.ndarray, tolerance: float = 1e-8) -> bool:
    if len(points) < 3:
        return False
    return bool(np.linalg.norm(points[0] - points[-1]) <= tolerance)
