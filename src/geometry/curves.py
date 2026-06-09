"""Lightweight curve fitting prototypes for extracted mesh sections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from geometry.sections import SectionPolyline


@dataclass(frozen=True)
class CurveFitResult:
    original_points: np.ndarray
    fitted_points: np.ndarray
    mean_error: float
    max_error: float
    is_closed: bool


def fit_section_polylines(
    polylines: Iterable[SectionPolyline],
    *,
    iterations: int = 2,
) -> list[CurveFitResult]:
    """Fit a smoothed polyline for every usable section polyline."""

    results: list[CurveFitResult] = []
    for polyline in polylines:
        if len(polyline.points) < 2:
            continue

        results.append(
            fit_smooth_polyline(polyline.points, iterations=max(int(iterations), 0))
        )

    return results


def fit_smooth_polyline(points: np.ndarray, *, iterations: int = 2) -> CurveFitResult:
    """Fit a simple smoothed polyline using Chaikin corner cutting."""

    original_points = np.asarray(points, dtype=float)
    if len(original_points) < 3 or iterations <= 0:
        fitted_points = original_points.copy()
    else:
        fitted_points = original_points.copy()
        is_closed = _is_closed(fitted_points)
        for _ in range(iterations):
            fitted_points = _chaikin_iteration(fitted_points, is_closed=is_closed)

    mean_error, max_error = _polyline_fit_error(original_points, fitted_points)
    return CurveFitResult(
        original_points=original_points,
        fitted_points=fitted_points,
        mean_error=mean_error,
        max_error=max_error,
        is_closed=_is_closed(original_points),
    )


def _is_closed(points: np.ndarray, tolerance: float = 1e-8) -> bool:
    if len(points) < 3:
        return False

    return bool(np.linalg.norm(points[0] - points[-1]) <= tolerance)


def _chaikin_iteration(points: np.ndarray, *, is_closed: bool) -> np.ndarray:
    if is_closed:
        working_points = points[:-1] if np.array_equal(points[0], points[-1]) else points
        smoothed: list[np.ndarray] = []
        point_count = len(working_points)
        for index in range(point_count):
            start = working_points[index]
            end = working_points[(index + 1) % point_count]
            smoothed.append((0.75 * start) + (0.25 * end))
            smoothed.append((0.25 * start) + (0.75 * end))

        smoothed.append(smoothed[0].copy())
        return np.asarray(smoothed)

    smoothed = [points[0]]
    for start, end in zip(points[:-1], points[1:]):
        smoothed.append((0.75 * start) + (0.25 * end))
        smoothed.append((0.25 * start) + (0.75 * end))
    smoothed.append(points[-1])

    return np.asarray(smoothed)


def _polyline_fit_error(
    original_points: np.ndarray,
    fitted_points: np.ndarray,
) -> tuple[float, float]:
    if len(original_points) == 0 or len(fitted_points) < 2:
        return (0.0, 0.0)

    distances = [
        _point_to_polyline_distance(point, fitted_points) for point in original_points
    ]
    if not distances:
        return (0.0, 0.0)

    return (float(np.mean(distances)), float(np.max(distances)))


def _point_to_polyline_distance(point: np.ndarray, polyline: np.ndarray) -> float:
    best_distance = float("inf")
    for start, end in zip(polyline[:-1], polyline[1:]):
        segment = end - start
        segment_length_squared = float(np.dot(segment, segment))
        if segment_length_squared == 0.0:
            distance = float(np.linalg.norm(point - start))
        else:
            ratio = float(np.dot(point - start, segment) / segment_length_squared)
            ratio = min(1.0, max(0.0, ratio))
            projection = start + (ratio * segment)
            distance = float(np.linalg.norm(point - projection))

        best_distance = min(best_distance, distance)

    return best_distance if best_distance != float("inf") else 0.0
