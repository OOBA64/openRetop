"""Open3D geometry helpers for CAD-style viewport overlays."""

from __future__ import annotations

from math import ceil, floor, log10
from typing import Sequence

import numpy as np
import open3d as o3d


AXIS_TO_INDEX = {"X": 0, "Y": 1, "Z": 2}


def build_xy_grid(
    min_bound: Sequence[float] | None,
    max_bound: Sequence[float] | None,
) -> o3d.geometry.LineSet:
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
        color = [0.24, 0.26, 0.28] if is_origin_line else [0.14, 0.15, 0.16]
        add_line((-half_extent, value, 0.0), (half_extent, value, 0.0), color)
        add_line((value, -half_extent, 0.0), (value, half_extent, 0.0), color)

    line_set = o3d.geometry.LineSet()
    line_set.points = o3d.utility.Vector3dVector(np.asarray(points, dtype=float))
    line_set.lines = o3d.utility.Vector2iVector(np.asarray(lines, dtype=int))
    line_set.colors = o3d.utility.Vector3dVector(np.asarray(colors, dtype=float))
    return line_set


def build_world_axes(reference_extent: float) -> list[o3d.geometry.Geometry]:
    """Build colored axes and a visible marker at the world origin."""

    size = max(float(reference_extent) * 0.28, 0.4)
    frame = o3d.geometry.TriangleMesh.create_coordinate_frame(
        size=size,
        origin=(0.0, 0.0, 0.0),
    )

    origin = o3d.geometry.TriangleMesh.create_sphere(
        radius=max(size * 0.045, 0.025),
        resolution=12,
    )
    origin.paint_uniform_color([1.0, 0.95, 0.3])
    origin.compute_vertex_normals()
    return [frame, origin]


def build_bounding_box_outline(
    min_bound: Sequence[float],
    max_bound: Sequence[float],
    *,
    color: Sequence[float] = (1.0, 0.82, 0.1),
) -> o3d.geometry.LineSet:
    """Build a highlighted bounding box outline for the selected mesh."""

    box = o3d.geometry.AxisAlignedBoundingBox(
        min_bound=np.asarray(min_bound, dtype=float),
        max_bound=np.asarray(max_bound, dtype=float),
    )
    line_set = o3d.geometry.LineSet.create_from_axis_aligned_bounding_box(box)
    line_set.paint_uniform_color(list(color))
    return line_set


def build_origin_marker(
    origin: Sequence[float],
    reference_extent: float,
) -> list[o3d.geometry.Geometry]:
    """Build a small marker that shows the selected object's pivot/origin."""

    size = max(float(reference_extent) * 0.045, 0.04)
    marker = o3d.geometry.TriangleMesh.create_sphere(radius=size, resolution=14)
    marker.paint_uniform_color([1.0, 0.74, 0.12])
    marker.translate(np.asarray(origin, dtype=float).tolist())
    marker.compute_vertex_normals()

    axes = o3d.geometry.TriangleMesh.create_coordinate_frame(
        size=max(float(reference_extent) * 0.14, 0.18),
        origin=np.asarray(origin, dtype=float).tolist(),
    )
    return [marker, axes]


def build_section_plane_preview(
    axis: str,
    offset: float,
    min_bound: Sequence[float],
    max_bound: Sequence[float],
    *,
    selected: bool = False,
) -> o3d.geometry.LineSet:
    """Build a visible, non-occluding section plane preview."""

    axis_key = axis.upper()
    axis_index = AXIS_TO_INDEX.get(axis_key, AXIS_TO_INDEX["Z"])
    other_indices = [index for index in range(3) if index != axis_index]
    minimum = np.asarray(min_bound, dtype=float)
    maximum = np.asarray(max_bound, dtype=float)
    extent = np.maximum(maximum - minimum, 1e-6)
    margin = max(float(np.max(extent)) * 0.08, 0.1)

    ranges: list[tuple[float, float]] = []
    for index in other_indices:
        start = float(minimum[index] - margin)
        end = float(maximum[index] + margin)
        if abs(end - start) <= 1e-6:
            center = (start + end) * 0.5
            start = center - 0.5
            end = center + 0.5
        ranges.append((start, end))

    start_a, end_a = ranges[0]
    start_b, end_b = ranges[1]
    corners = [
        _plane_point(axis_index, other_indices, float(offset), start_a, start_b),
        _plane_point(axis_index, other_indices, float(offset), end_a, start_b),
        _plane_point(axis_index, other_indices, float(offset), end_a, end_b),
        _plane_point(axis_index, other_indices, float(offset), start_a, end_b),
    ]

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

    for index in range(4):
        add_line(corners[index], corners[(index + 1) % 4], border_color)

    for fraction in (0.25, 0.5, 0.75):
        value_a = start_a + (end_a - start_a) * fraction
        value_b = start_b + (end_b - start_b) * fraction
        color = center_color if abs(fraction - 0.5) <= 1e-9 else inner_color
        add_line(
            _plane_point(axis_index, other_indices, float(offset), value_a, start_b),
            _plane_point(axis_index, other_indices, float(offset), value_a, end_b),
            color,
        )
        add_line(
            _plane_point(axis_index, other_indices, float(offset), start_a, value_b),
            _plane_point(axis_index, other_indices, float(offset), end_a, value_b),
            color,
        )

    line_set = o3d.geometry.LineSet()
    line_set.points = o3d.utility.Vector3dVector(np.asarray(points, dtype=float))
    line_set.lines = o3d.utility.Vector2iVector(np.asarray(lines, dtype=int))
    line_set.colors = o3d.utility.Vector3dVector(np.asarray(colors, dtype=float))
    return line_set


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
