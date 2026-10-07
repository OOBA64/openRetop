"""Reference per-triangle plane intersection (the pre-vectorisation implementation)."""

from __future__ import annotations

from typing import Iterable

import numpy as np


def _intersect_triangle_plane(
    triangle_points: np.ndarray,
    *,
    plane_origin: np.ndarray,
    plane_normal: np.ndarray,
    tolerance: float,
) -> np.ndarray | None:
    distances = (triangle_points - plane_origin) @ plane_normal

    if np.all(np.abs(distances) <= tolerance):
        return None

    hits: list[np.ndarray] = []
    for start_index, end_index in ((0, 1), (1, 2), (2, 0)):
        start_distance = float(distances[start_index])
        end_distance = float(distances[end_index])
        start_point = triangle_points[start_index]
        end_point = triangle_points[end_index]

        if abs(start_distance) <= tolerance:
            hits.append(start_point)

        crosses_plane = (
            start_distance < -tolerance
            and end_distance > tolerance
            or start_distance > tolerance
            and end_distance < -tolerance
        )
        if crosses_plane:
            ratio = -start_distance / (end_distance - start_distance)
            hits.append(start_point + ratio * (end_point - start_point))

        if abs(end_distance) <= tolerance:
            hits.append(end_point)

    unique_hits = _unique_points(hits, tolerance)
    if len(unique_hits) < 2:
        return None

    start_point, end_point = _farthest_pair(unique_hits)
    if np.linalg.norm(start_point - end_point) <= tolerance:
        return None

    return np.vstack((start_point, end_point))


def _unique_points(points: Iterable[np.ndarray], tolerance: float) -> list[np.ndarray]:
    unique: list[np.ndarray] = []
    for point in points:
        if not any(np.linalg.norm(point - existing) <= tolerance for existing in unique):
            unique.append(np.asarray(point, dtype=float))

    return unique


def _farthest_pair(points: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    best_pair = (points[0], points[1])
    best_distance = -1.0

    for start_index, start_point in enumerate(points):
        for end_point in points[start_index + 1 :]:
            distance = float(np.linalg.norm(start_point - end_point))
            if distance > best_distance:
                best_distance = distance
                best_pair = (start_point, end_point)

    return best_pair
