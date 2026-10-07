"""Extract polyline sections from triangle meshes."""

from __future__ import annotations

from dataclasses import dataclass, field

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

    segments = _plane_segments(
        vertices,
        triangles,
        plane_origin=plane_origin,
        plane_normal=plane_normal,
        tolerance=intersection_tolerance,
    )
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


def _plane_segments(
    vertices: np.ndarray,
    triangles: np.ndarray,
    *,
    plane_origin: np.ndarray,
    plane_normal: np.ndarray,
    tolerance: float,
) -> np.ndarray:
    """Plane/triangle intersection segments as an (n, 2, 3) array.

    One signed-distance pass over the vertices, then only triangles that touch
    the plane are examined. A triangle contributes the farthest pair of its
    on-plane corners and edge crossings; triangles lying in the plane add none.
    """

    signed = (vertices - plane_origin) @ plane_normal
    corner_distance = signed[triangles]
    touching = (corner_distance.min(axis=1) <= tolerance) & (corner_distance.max(axis=1) >= -tolerance)
    on_plane = np.abs(corner_distance) <= tolerance
    touching &= ~on_plane.all(axis=1)
    touched = np.flatnonzero(touching)
    if len(touched) == 0:
        return np.zeros((0, 2, 3))

    distance = corner_distance[touched]
    corners = vertices[triangles[touched]]
    on = on_plane[touched]

    candidates: list[np.ndarray] = []
    valid: list[np.ndarray] = []
    # Same visiting order as the original edge loop: start corner, crossing, end corner.
    for start, end in ((0, 1), (1, 2), (2, 0)):
        d_start, d_end = distance[:, start], distance[:, end]
        crossing = ((d_start < -tolerance) & (d_end > tolerance)) | (
            (d_start > tolerance) & (d_end < -tolerance)
        )
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(crossing, -d_start / (d_end - d_start), 0.0)
        point = corners[:, start] + ratio[:, None] * (corners[:, end] - corners[:, start])
        candidates.extend([corners[:, start], point, corners[:, end]])
        valid.extend([on[:, start], crossing, on[:, end]])

    points = np.stack(candidates, axis=1)  # (m, 9, 3)
    mask = np.stack(valid, axis=1)  # (m, 9)
    gaps = np.linalg.norm(points[:, :, None, :] - points[:, None, :, :], axis=3)
    usable = mask[:, :, None] & mask[:, None, :]
    usable &= np.triu(np.ones((9, 9), dtype=bool), k=1)[None]
    gaps = np.where(usable, gaps, -1.0)
    flat_best = gaps.reshape(len(touched), -1).argmax(axis=1)
    best = gaps.reshape(len(touched), -1)[np.arange(len(touched)), flat_best]
    keep = best > tolerance
    first, second = np.divmod(flat_best[keep], 9)
    rows = np.arange(len(touched))[keep]
    return np.stack([points[rows, first], points[rows, second]], axis=1)


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


def _segments_to_polylines(
    segments: np.ndarray,
    weld_tolerance: float,
) -> list[np.ndarray]:
    segments = np.asarray(segments, dtype=float).reshape((-1, 2, 3))
    if len(segments) == 0:
        return []

    # Weld endpoints on a grid. Indices follow first appearance, so output order
    # matches a sequential walk over the segments.
    endpoints = segments.reshape((-1, 3))
    keys = np.round(endpoints / weld_tolerance).astype(np.int64)
    _, first_seen, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    appearance_order = np.argsort(first_seen, kind="stable")
    rank = np.empty_like(appearance_order)
    rank[appearance_order] = np.arange(len(appearance_order))
    points = endpoints[first_seen[appearance_order]]
    index_pairs = rank[np.asarray(inverse).reshape(-1)].reshape((-1, 2))

    # Drop zero-length and repeated edges, keeping first-appearance order.
    index_pairs = index_pairs[index_pairs[:, 0] != index_pairs[:, 1]]
    undirected = np.sort(index_pairs, axis=1)
    _, first_edge = np.unique(undirected, axis=0, return_index=True)
    index_pairs = index_pairs[np.sort(first_edge)]

    adjacency: dict[int, set[int]] = {}
    for start_index, end_index in index_pairs.tolist():
        adjacency.setdefault(start_index, set()).add(end_index)
        adjacency.setdefault(end_index, set()).add(start_index)

    def edge_key(start_index: int, end_index: int) -> tuple[int, int]:
        return (
            (start_index, end_index)
            if start_index <= end_index
            else (end_index, start_index)
        )

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
