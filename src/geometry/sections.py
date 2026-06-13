"""Extract polyline sections from triangle meshes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np


SECTION_AXES = ("X", "Y", "Z")
AXIS_TO_INDEX = {"X": 0, "Y": 1, "Z": 2}


@dataclass(frozen=True)
class SectionPolyline:
    points: np.ndarray

    @property
    def point_count(self) -> int:
        return int(len(self.points))

    @property
    def is_closed(self) -> bool:
        if len(self.points) < 3:
            return False

        return bool(np.linalg.norm(self.points[0] - self.points[-1]) <= 1e-8)


@dataclass(frozen=True)
class SectionResult:
    axis: str
    offset: float
    polylines: tuple[SectionPolyline, ...]
    segment_count: int
    plane_origin: np.ndarray | None = field(default=None, compare=False)
    plane_normal: np.ndarray | None = field(default=None, compare=False)
    is_arbitrary_plane: bool = False

    @property
    def point_count(self) -> int:
        return sum(polyline.point_count for polyline in self.polylines)


def normalize_axis(axis: str) -> str:
    axis_key = axis.upper()
    if axis_key not in AXIS_TO_INDEX:
        expected = ", ".join(SECTION_AXES)
        raise ValueError(f"Unsupported section axis '{axis}'. Expected one of: {expected}")

    return axis_key


def extract_section(
    mesh: object,
    *,
    axis: str = "Z",
    offset: float = 0.0,
    origin: object | None = None,
    normal: object | None = None,
    tolerance: float = 1e-8,
    weld_tolerance: float | None = None,
) -> SectionResult:
    """Intersect a triangle mesh with an axis-aligned or arbitrary plane."""

    axis_key = normalize_axis(axis)
    result_offset = float(offset)
    plane_origin, plane_normal = _plane_origin_normal(
        axis_key,
        result_offset,
        origin=origin,
        normal=normal,
    )
    is_arbitrary_plane = not _is_axis_aligned_plane(
        axis_key,
        result_offset,
        plane_origin,
        plane_normal,
    )

    return _extract_section_for_plane(
        mesh,
        axis=axis_key,
        offset=result_offset,
        plane_origin=plane_origin,
        plane_normal=plane_normal,
        is_arbitrary_plane=is_arbitrary_plane,
        tolerance=tolerance,
        weld_tolerance=weld_tolerance,
    )


def extract_section_by_plane(
    mesh: object,
    origin: object,
    normal: object,
    *,
    axis: str | None = None,
    offset: float | None = None,
    tolerance: float = 1e-8,
    weld_tolerance: float | None = None,
) -> SectionResult:
    """Intersect a triangle mesh with an arbitrary plane origin and normal."""

    plane_origin = _vector3(origin, "origin")
    fallback_axis = normalize_axis(axis) if axis is not None else "Z"
    plane_normal = _normalized_vector(
        normal,
        fallback=_axis_normal(fallback_axis),
    )
    axis_key = (
        normalize_axis(axis)
        if axis is not None
        else _axis_from_plane_normal(plane_normal, fallback=fallback_axis)
    )
    result_offset = (
        float(offset)
        if offset is not None
        else _offset_for_axis(axis_key, plane_origin)
    )
    is_arbitrary_plane = not _is_axis_aligned_plane(
        axis_key,
        result_offset,
        plane_origin,
        plane_normal,
    )

    return _extract_section_for_plane(
        mesh,
        axis=axis_key,
        offset=result_offset,
        plane_origin=plane_origin,
        plane_normal=plane_normal,
        is_arbitrary_plane=is_arbitrary_plane,
        tolerance=tolerance,
        weld_tolerance=weld_tolerance,
    )


def _extract_section_for_plane(
    mesh: object,
    *,
    axis: str,
    offset: float,
    plane_origin: np.ndarray,
    plane_normal: np.ndarray,
    is_arbitrary_plane: bool,
    tolerance: float,
    weld_tolerance: float | None,
) -> SectionResult:
    vertices = np.asarray(mesh.vertices, dtype=float)
    triangles = np.asarray(mesh.triangles, dtype=int)
    if vertices.size == 0 or triangles.size == 0:
        return SectionResult(
            axis,
            float(offset),
            tuple(),
            0,
            plane_origin=plane_origin.copy(),
            plane_normal=plane_normal.copy(),
            is_arbitrary_plane=bool(is_arbitrary_plane),
        )

    extents = np.ptp(vertices, axis=0)
    mesh_scale = max(float(np.max(extents)), 1.0)
    intersection_tolerance = max(float(tolerance), mesh_scale * 1e-10)
    point_weld_tolerance = (
        max(intersection_tolerance * 10.0, mesh_scale * 1e-8)
        if weld_tolerance is None
        else max(float(weld_tolerance), intersection_tolerance)
    )

    segments: list[np.ndarray] = []
    for triangle_indices in triangles:
        triangle_points = vertices[triangle_indices]
        segment = _intersect_triangle_plane(
            triangle_points,
            plane_origin=plane_origin,
            plane_normal=plane_normal,
            tolerance=intersection_tolerance,
        )
        if segment is not None:
            segments.append(segment)

    polylines = _segments_to_polylines(segments, point_weld_tolerance)
    return SectionResult(
        axis=axis,
        offset=float(offset),
        polylines=tuple(SectionPolyline(points=polyline) for polyline in polylines),
        segment_count=len(segments),
        plane_origin=plane_origin.copy(),
        plane_normal=plane_normal.copy(),
        is_arbitrary_plane=bool(is_arbitrary_plane),
    )


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


def _plane_origin_normal(
    axis: str,
    offset: float,
    *,
    origin: object | None,
    normal: object | None,
) -> tuple[np.ndarray, np.ndarray]:
    axis_normal = _axis_normal(axis)
    if normal is None:
        plane_normal = axis_normal
    else:
        plane_normal = _normalized_vector(normal, fallback=axis_normal)

    if origin is None:
        plane_origin = plane_normal * float(offset)
    else:
        plane_origin = _vector3(origin, "origin")
    return (plane_origin, plane_normal)


def _axis_normal(axis: str) -> np.ndarray:
    axis_index = AXIS_TO_INDEX[axis]
    normal = np.zeros(3, dtype=float)
    normal[axis_index] = 1.0
    return normal


def _axis_from_plane_normal(
    plane_normal: np.ndarray,
    *,
    fallback: str,
) -> str:
    normal = _normalized_vector(plane_normal, fallback=_axis_normal(fallback))
    for axis, axis_index in AXIS_TO_INDEX.items():
        if abs(float(normal[axis_index])) >= 1.0 - 1e-8:
            return axis
    return fallback


def _offset_for_axis(axis: str, plane_origin: np.ndarray) -> float:
    return float(np.dot(np.asarray(plane_origin, dtype=float), _axis_normal(axis)))


def _is_axis_aligned_plane(
    axis: str,
    offset: float,
    plane_origin: np.ndarray,
    plane_normal: np.ndarray,
) -> bool:
    axis_normal = _axis_normal(axis)
    normal = _normalized_vector(plane_normal, fallback=axis_normal)
    normal_is_axis = abs(float(np.dot(normal, axis_normal))) >= 1.0 - 1e-6
    origin_matches_offset = abs(_offset_for_axis(axis, plane_origin) - float(offset)) <= 1e-6
    return bool(normal_is_axis and origin_matches_offset)


def _vector3(value: object, field_name: str) -> np.ndarray:
    values = np.asarray(value, dtype=float).reshape(-1)
    if values.shape != (3,) or not np.all(np.isfinite(values)):
        raise ValueError(f"{field_name} must contain exactly three finite numbers.")
    return values.copy()


def _normalized_vector(value: object, *, fallback: np.ndarray) -> np.ndarray:
    vector = _vector3(value, "normal")
    length = float(np.linalg.norm(vector))
    if length <= 1e-12:
        return np.asarray(fallback, dtype=float).copy()
    return vector / length


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


def _segments_to_polylines(
    segments: list[np.ndarray],
    weld_tolerance: float,
) -> list[np.ndarray]:
    if not segments:
        return []

    points: list[np.ndarray] = []
    point_index_by_key: dict[tuple[int, int, int], int] = {}
    adjacency: dict[int, set[int]] = {}
    edges: set[tuple[int, int]] = set()

    def point_key(point: np.ndarray) -> tuple[int, int, int]:
        return tuple(int(round(float(value) / weld_tolerance)) for value in point)

    def point_index(point: np.ndarray) -> int:
        key = point_key(point)
        if key not in point_index_by_key:
            point_index_by_key[key] = len(points)
            points.append(np.asarray(point, dtype=float))

        return point_index_by_key[key]

    def edge_key(start_index: int, end_index: int) -> tuple[int, int]:
        return (
            (start_index, end_index)
            if start_index <= end_index
            else (end_index, start_index)
        )

    for segment in segments:
        start_index = point_index(segment[0])
        end_index = point_index(segment[1])
        if start_index == end_index:
            continue

        key = edge_key(start_index, end_index)
        if key in edges:
            continue

        edges.add(key)
        adjacency.setdefault(start_index, set()).add(end_index)
        adjacency.setdefault(end_index, set()).add(start_index)

    visited_edges: set[tuple[int, int]] = set()
    polylines: list[np.ndarray] = []

    def consume_path(start_index: int, next_index: int) -> list[int]:
        path = [start_index]
        previous_index = start_index
        current_index = next_index
        visited_edges.add(edge_key(start_index, next_index))

        while True:
            path.append(current_index)
            if current_index == start_index:
                break

            candidates = [
                candidate
                for candidate in adjacency.get(current_index, set())
                if edge_key(current_index, candidate) not in visited_edges
            ]
            if not candidates:
                break

            non_backtracking = [
                candidate for candidate in candidates if candidate != previous_index
            ]
            next_candidate = (
                non_backtracking[0] if non_backtracking else candidates[0]
            )
            visited_edges.add(edge_key(current_index, next_candidate))
            previous_index, current_index = current_index, next_candidate

        return path

    start_indices = [
        index for index, neighbors in adjacency.items() if len(neighbors) != 2
    ]
    start_indices.extend(
        index for index, neighbors in adjacency.items() if len(neighbors) == 2
    )

    for start_index in start_indices:
        for next_index in sorted(adjacency.get(start_index, set())):
            if edge_key(start_index, next_index) in visited_edges:
                continue

            path = consume_path(start_index, next_index)
            if len(path) >= 2:
                polylines.append(np.asarray([points[index] for index in path]))

    return sorted(polylines, key=len, reverse=True)
