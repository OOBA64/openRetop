"""Plain geometry helpers for CAD-style viewport overlays."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, ceil, cos, floor, log10, pi, sin
from typing import Sequence

import numpy as np


AXIS_TO_INDEX = {"X": 0, "Y": 1, "Z": 2}
AXIS_COLORS = {
    "X": (0.95, 0.18, 0.18),
    "Y": (0.2, 0.85, 0.25),
    "Z": (0.22, 0.48, 1.0),
}
SELECTED_BOUNDING_BOX_COLOR = (0.44, 0.56, 0.62)


@dataclass(frozen=True)
class LineGeometry:
    points: np.ndarray
    lines: np.ndarray
    colors: np.ndarray


def build_xy_grid(
    min_bound: Sequence[float] | None,
    max_bound: Sequence[float] | None,
) -> LineGeometry:
    """Build a subtle XY grid centered on the world origin."""

    half_size, step = grid_size_and_step(min_bound, max_bound)
    divisions = max(int(ceil(half_size / step)), 1)
    coordinates = [index * step for index in range(-divisions, divisions + 1)]
    half_extent = divisions * step

    points: list[list[float]] = []
    lines: list[tuple[int, int]] = []
    colors: list[list[float]] = []

    def add_line(
        start: tuple[float, float, float],
        end: tuple[float, float, float],
        color: list[float],
    ) -> None:
        start_index = len(points)
        points.extend([list(start), list(end)])
        lines.append((start_index, start_index + 1))
        colors.append(color)

    for value in coordinates:
        is_origin_line = abs(value) <= step * 0.01
        color = [0.20, 0.23, 0.26] if is_origin_line else [0.10, 0.115, 0.13]
        add_line((-half_extent, value, 0.0), (half_extent, value, 0.0), color)
        add_line((value, -half_extent, 0.0), (value, half_extent, 0.0), color)

    return _line_geometry(points, lines, colors)


def build_world_axes(reference_extent: float) -> LineGeometry:
    size = max(float(reference_extent) * 0.24, 0.35)
    points = [
        [0.0, 0.0, 0.0],
        [size, 0.0, 0.0],
        [0.0, 0.0, 0.0],
        [0.0, size, 0.0],
        [0.0, 0.0, 0.0],
        [0.0, 0.0, size],
    ]
    lines = [(0, 1), (2, 3), (4, 5)]
    colors = [[0.95, 0.18, 0.18], [0.2, 0.85, 0.25], [0.22, 0.48, 1.0]]
    return _line_geometry(points, lines, colors)


def build_active_axis_indicator(
    origin: Sequence[float],
    axis: str,
    reference_extent: float,
) -> LineGeometry:
    axis_key = axis.upper()
    axis_index = AXIS_TO_INDEX.get(axis_key, AXIS_TO_INDEX["Z"])
    center = np.asarray(origin, dtype=float)
    size = max(float(reference_extent) * 0.34, 0.35)
    start = center.copy()
    end = center.copy()
    start[axis_index] -= size
    end[axis_index] += size
    color = list(AXIS_COLORS.get(axis_key, AXIS_COLORS["Z"]))
    return _line_geometry([start.tolist(), end.tolist()], [(0, 1)], [color])


def build_rotation_ring(
    origin: Sequence[float],
    axis: str,
    reference_extent: float,
    *,
    radius: float | None = None,
    segments: int = 96,
) -> LineGeometry:
    axis_key = axis.upper()
    center = np.asarray(origin, dtype=float)
    ring_radius = max(float(reference_extent) * 0.22, 0.25) if radius is None else max(float(radius), 1e-6)
    color = list(AXIS_COLORS.get(axis_key, AXIS_COLORS["Z"]))

    points: list[list[float]] = []
    lines: list[tuple[int, int]] = []
    colors: list[list[float]] = []
    for index in range(max(int(segments), 12)):
        angle = (2.0 * pi * index) / max(int(segments), 12)
        points.append(_rotation_plane_point(center, axis_key, angle, ring_radius).tolist())

    for index in range(len(points)):
        lines.append((index, (index + 1) % len(points)))
        colors.append(color)

    return _line_geometry(points, lines, colors)


def build_rotation_angle_indicator(
    origin: Sequence[float],
    axis: str,
    radius: float,
    angle_degrees: float,
    *,
    segments: int = 64,
) -> LineGeometry:
    """Build a line-based sector preview for the active rotation delta."""

    if abs(float(angle_degrees)) <= 1e-6:
        return _line_geometry([], [], [])

    axis_key = axis.upper()
    center = np.asarray(origin, dtype=float)
    indicator_radius = max(float(radius), 1e-6)
    angle_radians = (float(angle_degrees) * pi) / 180.0
    step_count = max(2, min(max(int(segments), 2), int(abs(float(angle_degrees)) / 7.5) + 2))
    color = list(AXIS_COLORS.get(axis_key, AXIS_COLORS["Z"]))
    start_color = [min(component + 0.25, 1.0) for component in color]
    fan_color = [component * 0.62 for component in color]

    points: list[list[float]] = [center.tolist()]
    lines: list[tuple[int, int]] = []
    colors: list[list[float]] = []
    arc_indices: list[int] = []
    for index in range(step_count + 1):
        ratio = index / step_count
        point = _rotation_plane_point(center, axis_key, angle_radians * ratio, indicator_radius)
        arc_indices.append(len(points))
        points.append(point.tolist())

    lines.append((0, arc_indices[0]))
    colors.append(start_color)
    lines.append((0, arc_indices[-1]))
    colors.append(color)

    for index in range(1, len(arc_indices)):
        lines.append((arc_indices[index - 1], arc_indices[index]))
        colors.append(color)

    for index in range(1, len(arc_indices) - 1):
        lines.append((0, arc_indices[index]))
        colors.append(fan_color)

    return _line_geometry(points, lines, colors)


def rotation_ring_radius_for_axis(
    min_bound: Sequence[float],
    max_bound: Sequence[float],
    axis: str,
) -> float:
    minimum = np.asarray(min_bound, dtype=float)
    maximum = np.asarray(max_bound, dtype=float)
    extents = np.maximum(maximum - minimum, 0.0)
    diagonal = float(np.linalg.norm(extents))
    minimum_radius = max(diagonal * 0.08, 0.25)
    axis_key = axis.upper()
    if axis_key == "X":
        axis_radius = 0.60 * max(float(extents[1]), float(extents[2]))
    elif axis_key == "Y":
        axis_radius = 0.60 * max(float(extents[0]), float(extents[2]))
    else:
        axis_radius = 0.60 * max(float(extents[0]), float(extents[1]))
    return max(axis_radius, minimum_radius)


def build_bounding_box_outline(
    min_bound: Sequence[float],
    max_bound: Sequence[float],
    *,
    color: Sequence[float] = SELECTED_BOUNDING_BOX_COLOR,
) -> LineGeometry:
    minimum = np.asarray(min_bound, dtype=float)
    maximum = np.asarray(max_bound, dtype=float)
    points = [
        [minimum[0], minimum[1], minimum[2]],
        [maximum[0], minimum[1], minimum[2]],
        [maximum[0], maximum[1], minimum[2]],
        [minimum[0], maximum[1], minimum[2]],
        [minimum[0], minimum[1], maximum[2]],
        [maximum[0], minimum[1], maximum[2]],
        [maximum[0], maximum[1], maximum[2]],
        [minimum[0], maximum[1], maximum[2]],
    ]
    lines = [
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 0),
        (4, 5),
        (5, 6),
        (6, 7),
        (7, 4),
        (0, 4),
        (1, 5),
        (2, 6),
        (3, 7),
    ]
    colors = [list(color) for _ in lines]
    return _line_geometry(points, lines, colors)


def build_origin_marker(origin: Sequence[float], reference_extent: float) -> LineGeometry:
    center = np.asarray(origin, dtype=float)
    size = max(float(reference_extent) * 0.035, 0.04)
    points = [
        (center + [-size, 0.0, 0.0]).tolist(),
        (center + [size, 0.0, 0.0]).tolist(),
        (center + [0.0, -size, 0.0]).tolist(),
        (center + [0.0, size, 0.0]).tolist(),
        (center + [0.0, 0.0, -size]).tolist(),
        (center + [0.0, 0.0, size]).tolist(),
    ]
    lines = [(0, 1), (2, 3), (4, 5)]
    colors = [[1.0, 0.74, 0.12] for _ in lines]
    return _line_geometry(points, lines, colors)


def build_section_plane_preview(
    axis: str,
    offset: float,
    min_bound: Sequence[float],
    max_bound: Sequence[float],
    *,
    selected: bool = False,
    origin: Sequence[float] | None = None,
    normal: Sequence[float] | None = None,
) -> LineGeometry:
    """Build a visible, non-occluding section plane preview."""

    minimum = np.asarray(min_bound, dtype=float)
    maximum = np.asarray(max_bound, dtype=float)
    extent = np.maximum(maximum - minimum, 1e-6)
    margin = max(float(np.max(extent)) * 0.08, 0.1)
    expanded_minimum = minimum - margin
    expanded_maximum = maximum + margin
    plane_origin, plane_normal = _plane_preview_origin_normal(
        axis,
        offset,
        origin=origin,
        normal=normal,
    )
    corners = _section_plane_polygon(
        expanded_minimum,
        expanded_maximum,
        plane_origin,
        plane_normal,
        fallback_size=max(float(np.max(extent)) + margin * 2.0, 1.0),
    )

    u_axis, v_axis = _plane_basis(plane_normal)
    center = np.mean(corners, axis=0)
    local = corners - center
    order = sorted(
        range(len(corners)),
        key=lambda index: atan2(
            float(np.dot(local[index], v_axis)),
            float(np.dot(local[index], u_axis)),
        ),
    )
    corners = corners[order]

    points: list[list[float]] = []
    lines: list[tuple[int, int]] = []
    colors: list[list[float]] = []

    def add_line(start: Sequence[float], end: Sequence[float], color: list[float]) -> None:
        start_index = len(points)
        points.extend([list(start), list(end)])
        lines.append((start_index, start_index + 1))
        colors.append(color)

    border_color = [1.0, 0.82, 0.1] if selected else [0.0, 0.92, 1.0]
    inner_color = [0.0, 0.42, 0.48]
    center_color = [1.0, 0.95, 0.35] if selected else [0.58, 1.0, 1.0]

    for index in range(len(corners)):
        add_line(corners[index], corners[(index + 1) % len(corners)], border_color)

    local_u = np.asarray([float(np.dot(point - center, u_axis)) for point in corners])
    local_v = np.asarray([float(np.dot(point - center, v_axis)) for point in corners])
    start_u, end_u = float(np.min(local_u)), float(np.max(local_u))
    start_v, end_v = float(np.min(local_v)), float(np.max(local_v))
    for fraction in (0.25, 0.5, 0.75):
        color = center_color if abs(fraction - 0.5) <= 1e-9 else inner_color
        value_u = start_u + (end_u - start_u) * fraction
        value_v = start_v + (end_v - start_v) * fraction
        add_line(
            center + u_axis * value_u + v_axis * start_v,
            center + u_axis * value_u + v_axis * end_v,
            color,
        )
        add_line(
            center + u_axis * start_u + v_axis * value_v,
            center + u_axis * end_u + v_axis * value_v,
            color,
        )

    return _line_geometry(points, lines, colors)


def _plane_preview_origin_normal(
    axis: str,
    offset: float,
    *,
    origin: Sequence[float] | None,
    normal: Sequence[float] | None,
) -> tuple[np.ndarray, np.ndarray]:
    axis_key = axis.upper()
    axis_index = AXIS_TO_INDEX.get(axis_key, AXIS_TO_INDEX["Z"])
    axis_normal = np.zeros(3, dtype=float)
    axis_normal[axis_index] = 1.0
    if normal is None:
        plane_normal = axis_normal
    else:
        plane_normal = _normalized_vector(normal, fallback=axis_normal)

    if origin is None:
        plane_origin = axis_normal * float(offset)
    else:
        plane_origin = np.asarray(origin, dtype=float).reshape(3)
    return (plane_origin, plane_normal)


def _section_plane_polygon(
    minimum: np.ndarray,
    maximum: np.ndarray,
    origin: np.ndarray,
    normal: np.ndarray,
    *,
    fallback_size: float,
) -> np.ndarray:
    corners = _box_corners(minimum, maximum)
    edges = (
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 0),
        (4, 5),
        (5, 6),
        (6, 7),
        (7, 4),
        (0, 4),
        (1, 5),
        (2, 6),
        (3, 7),
    )
    distances = (corners - origin) @ normal
    hits: list[np.ndarray] = []
    tolerance = max(float(fallback_size) * 1e-8, 1e-8)
    for start_index, end_index in edges:
        start_point = corners[start_index]
        end_point = corners[end_index]
        start_distance = float(distances[start_index])
        end_distance = float(distances[end_index])
        if abs(start_distance) <= tolerance:
            hits.append(start_point)
        if abs(end_distance) <= tolerance:
            hits.append(end_point)
        if start_distance * end_distance < 0.0:
            ratio = -start_distance / (end_distance - start_distance)
            hits.append(start_point + ratio * (end_point - start_point))

    unique_hits = _unique_plane_points(hits, tolerance)
    if len(unique_hits) >= 3:
        return np.asarray(unique_hits, dtype=float)

    u_axis, v_axis = _plane_basis(normal)
    half_size = max(float(fallback_size) * 0.5, 0.5)
    return np.asarray(
        [
            origin - u_axis * half_size - v_axis * half_size,
            origin + u_axis * half_size - v_axis * half_size,
            origin + u_axis * half_size + v_axis * half_size,
            origin - u_axis * half_size + v_axis * half_size,
        ],
        dtype=float,
    )


def _box_corners(minimum: np.ndarray, maximum: np.ndarray) -> np.ndarray:
    return np.asarray(
        [
            [minimum[0], minimum[1], minimum[2]],
            [maximum[0], minimum[1], minimum[2]],
            [maximum[0], maximum[1], minimum[2]],
            [minimum[0], maximum[1], minimum[2]],
            [minimum[0], minimum[1], maximum[2]],
            [maximum[0], minimum[1], maximum[2]],
            [maximum[0], maximum[1], maximum[2]],
            [minimum[0], maximum[1], maximum[2]],
        ],
        dtype=float,
    )


def _plane_basis(normal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    plane_normal = _normalized_vector(normal, fallback=np.asarray([0.0, 0.0, 1.0], dtype=float))
    reference = (
        np.asarray([0.0, 0.0, 1.0], dtype=float)
        if abs(float(plane_normal[2])) < 0.92
        else np.asarray([0.0, 1.0, 0.0], dtype=float)
    )
    u_axis = _normalized_vector(np.cross(reference, plane_normal), fallback=np.asarray([1.0, 0.0, 0.0], dtype=float))
    v_axis = _normalized_vector(np.cross(plane_normal, u_axis), fallback=np.asarray([0.0, 1.0, 0.0], dtype=float))
    return (u_axis, v_axis)


def _unique_plane_points(points: Sequence[np.ndarray], tolerance: float) -> list[np.ndarray]:
    unique: list[np.ndarray] = []
    for point in points:
        point_array = np.asarray(point, dtype=float)
        if not any(np.linalg.norm(point_array - existing) <= tolerance for existing in unique):
            unique.append(point_array)
    return unique


def _normalized_vector(
    vector: Sequence[float] | np.ndarray,
    *,
    fallback: np.ndarray,
) -> np.ndarray:
    values = np.asarray(vector, dtype=float)
    length = float(np.linalg.norm(values))
    if length <= 1e-12:
        return np.asarray(fallback, dtype=float).copy()
    return values / length


def grid_size_and_step(
    min_bound: Sequence[float] | None,
    max_bound: Sequence[float] | None,
) -> tuple[float, float]:
    """Return a grid half-size and visually useful spacing."""

    if min_bound is None or max_bound is None:
        half_size = 2.0
    else:
        minimum = np.asarray(min_bound, dtype=float)
        maximum = np.asarray(max_bound, dtype=float)
        extent = np.maximum(maximum - minimum, 1e-6)
        xy_radius = max(
            abs(float(minimum[0])),
            abs(float(maximum[0])),
            abs(float(minimum[1])),
            abs(float(maximum[1])),
        )
        half_size = max(float(np.max(extent)) * 1.25, xy_radius * 1.15, 1.0)

    step = _nice_step(half_size / 10.0)
    return half_size, step


def reference_extent(
    min_bound: Sequence[float] | None,
    max_bound: Sequence[float] | None,
) -> float:
    if min_bound is None or max_bound is None:
        return 2.0

    minimum = np.asarray(min_bound, dtype=float)
    maximum = np.asarray(max_bound, dtype=float)
    return max(float(np.max(maximum - minimum)), 1.0)


def _line_geometry(
    points: Sequence[Sequence[float]],
    lines: Sequence[tuple[int, int]],
    colors: Sequence[Sequence[float]],
) -> LineGeometry:
    return LineGeometry(
        points=np.asarray(points, dtype=float).reshape((-1, 3)),
        lines=np.asarray(lines, dtype=int).reshape((-1, 2)),
        colors=np.asarray(colors, dtype=float).reshape((-1, 3)),
    )


def _plane_point(
    axis_index: int,
    other_indices: list[int],
    offset: float,
    first_value: float,
    second_value: float,
) -> list[float]:
    point = [0.0, 0.0, 0.0]
    point[axis_index] = offset
    point[other_indices[0]] = first_value
    point[other_indices[1]] = second_value
    return point


def _rotation_plane_point(
    center: np.ndarray,
    axis_key: str,
    angle: float,
    radius: float,
) -> np.ndarray:
    point = center.copy()
    if axis_key == "X":
        point[1] += cos(angle) * radius
        point[2] += sin(angle) * radius
    elif axis_key == "Y":
        point[0] += cos(angle) * radius
        point[2] += sin(angle) * radius
    else:
        point[0] += cos(angle) * radius
        point[1] += sin(angle) * radius
    return point


def _nice_step(raw_step: float) -> float:
    if raw_step <= 0.0:
        return 1.0

    magnitude = 10 ** floor(log10(raw_step))
    normalized = raw_step / magnitude
    if normalized <= 1.0:
        nice = 1.0
    elif normalized <= 2.0:
        nice = 2.0
    elif normalized <= 5.0:
        nice = 5.0
    else:
        nice = 10.0

    return nice * magnitude
