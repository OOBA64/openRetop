"""Toolkit-neutral scene descriptions consumed by viewport presentation adapters.

The objects in this module intentionally contain no Tk or VTK types.  Geometry
is represented by NumPy arrays and existing domain mesh objects; presentation
adapters are responsible for converting those values into actors.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import hashlib
import math
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence

import numpy as np


Vector3 = tuple[float, float, float]
Bounds3 = tuple[Vector3, Vector3]


def geometry_revision(*values: object) -> int:
    """Return a deterministic revision token for geometry-like values."""

    digest = hashlib.blake2b(digest_size=8)
    for value in values:
        if value is None:
            digest.update(b"none")
            continue
        if isinstance(value, np.ndarray):
            array = np.ascontiguousarray(value)
            digest.update(str(array.dtype).encode("ascii"))
            digest.update(str(array.shape).encode("ascii"))
            digest.update(array.tobytes())
            continue
        if isinstance(value, (list, tuple)):
            try:
                array = np.ascontiguousarray(value)
            except (TypeError, ValueError):
                digest.update(repr(value).encode("utf-8", "replace"))
            else:
                digest.update(str(array.dtype).encode("ascii"))
                digest.update(str(array.shape).encode("ascii"))
                digest.update(array.tobytes())
            continue
        digest.update(repr(value).encode("utf-8", "replace"))
    return int.from_bytes(digest.digest(), "big", signed=False)


def _points(value: object | None) -> np.ndarray:
    if value is None:
        return np.zeros((0, 3), dtype=float)
    try:
        points = np.asarray(value, dtype=float).reshape((-1, 3))
    except (TypeError, ValueError):
        return np.zeros((0, 3), dtype=float)
    return points


def finite_bounds(points: object | None) -> Bounds3 | None:
    values = _points(points)
    if len(values) == 0:
        return None
    values = values[np.all(np.isfinite(values), axis=1)]
    if len(values) == 0:
        return None
    minimum = np.min(values, axis=0)
    maximum = np.max(values, axis=0)
    return (_vector3_tuple(minimum), _vector3_tuple(maximum))


def transformed_bounds(bounds: Bounds3 | None, matrix: object | None) -> Bounds3 | None:
    if bounds is None:
        return None
    minimum = np.asarray(bounds[0], dtype=float)
    maximum = np.asarray(bounds[1], dtype=float)
    if matrix is None:
        return bounds
    try:
        transform = np.asarray(matrix, dtype=float).reshape((4, 4))
    except (TypeError, ValueError):
        return None
    if not np.all(np.isfinite(transform)):
        return None
    corners = np.asarray(
        [
            [x, y, z]
            for x in (minimum[0], maximum[0])
            for y in (minimum[1], maximum[1])
            for z in (minimum[2], maximum[2])
        ],
        dtype=float,
    )
    homogeneous = np.column_stack((corners, np.ones(len(corners), dtype=float)))
    world = (transform @ homogeneous.T).T[:, :3]
    return finite_bounds(world)


def merge_bounds(bounds: Iterable[Bounds3 | None]) -> Bounds3 | None:
    valid = [item for item in bounds if item is not None]
    if not valid:
        return None
    minimum = np.min(np.asarray([item[0] for item in valid], dtype=float), axis=0)
    maximum = np.max(np.asarray([item[1] for item in valid], dtype=float), axis=0)
    return (_vector3_tuple(minimum), _vector3_tuple(maximum))


@dataclass(frozen=True, slots=True)
class DisplayStyleSnapshot:
    """Display options and palette independent of a concrete toolkit."""

    color: Vector3 = (1.0, 1.0, 1.0)
    edge_color: Vector3 | None = None
    opacity: float = 1.0
    line_width: float = 1.0
    point_size: float = 1.0
    representation: str = "surface"
    edge_visibility: bool = False
    extras: Mapping[str, object] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "color", _color3(self.color, (1.0, 1.0, 1.0)))
        if self.edge_color is not None:
            object.__setattr__(self, "edge_color", _color3(self.edge_color, self.color))
        object.__setattr__(self, "opacity", _finite_clamped(self.opacity, 1.0, 0.0, 1.0))
        object.__setattr__(self, "line_width", max(_finite_float(self.line_width, 1.0), 0.0))
        object.__setattr__(self, "point_size", max(_finite_float(self.point_size, 1.0), 0.0))
        object.__setattr__(self, "extras", MappingProxyType(dict(self.extras)))


@dataclass(frozen=True, slots=True)
class MeshRenderItem:
    id: str
    revision: int
    mesh: object = field(compare=False, repr=False)
    transform: np.ndarray = field(
        default_factory=lambda: np.identity(4, dtype=float), compare=False, repr=False
    )
    visible: bool = True
    selected: bool = False
    style: DisplayStyleSnapshot = field(default_factory=DisplayStyleSnapshot)
    local_bounds: Bounds3 | None = None
    selection_keys: tuple[str, ...] = ()

    @property
    def world_bounds(self) -> Bounds3 | None:
        bounds = self.local_bounds
        if bounds is None and self.mesh is not None:
            try:
                mesh_bounds = self.mesh.get_axis_aligned_bounding_box()
                bounds = (
                    _vector3_tuple(mesh_bounds.get_min_bound()),
                    _vector3_tuple(mesh_bounds.get_max_bound()),
                )
            except (AttributeError, TypeError, ValueError):
                bounds = finite_bounds(getattr(self.mesh, "vertices", None))
        return transformed_bounds(bounds, self.transform)


@dataclass(frozen=True, slots=True)
class CurveRenderItem:
    id: str
    revision: int
    points: np.ndarray = field(compare=False, repr=False)
    visible: bool = True
    closed: bool = False
    style: DisplayStyleSnapshot = field(default_factory=DisplayStyleSnapshot)
    category: str = "normal"
    selected: bool = False
    active: bool = False
    metadata: Mapping[str, object] = field(default_factory=dict, compare=False)
    selection_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "points", _points(self.points))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def fitted_points(self) -> np.ndarray:
        """Compatibility attribute used by the Task 74 actor factories."""

        return self.points

    @property
    def is_closed(self) -> bool:
        return self.closed

    @property
    def world_bounds(self) -> Bounds3 | None:
        return finite_bounds(self.points)


@dataclass(frozen=True, slots=True)
class SurfaceRenderItem:
    id: str
    revision: int
    vertices: np.ndarray = field(compare=False, repr=False)
    faces: np.ndarray = field(compare=False, repr=False)
    visible: bool = True
    style: DisplayStyleSnapshot = field(default_factory=DisplayStyleSnapshot)
    selected: bool = False
    active: bool = False
    display_role: str = "preview_surface"
    wireframe_overlay: bool = False
    overbuild_handle_points: np.ndarray = field(
        default_factory=lambda: np.zeros((0, 3), dtype=float), compare=False, repr=False
    )
    show_overbuild_handles: bool = False
    selection_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "vertices", _points(self.vertices))
        object.__setattr__(
            self,
            "faces",
            np.asarray(self.faces, dtype=int).reshape((-1, 3)),
        )
        object.__setattr__(
            self, "overbuild_handle_points", _points(self.overbuild_handle_points)
        )

    @property
    def world_bounds(self) -> Bounds3 | None:
        return merge_bounds(
            (
                finite_bounds(self.vertices),
                finite_bounds(self.overbuild_handle_points)
                if self.show_overbuild_handles
                else None,
            )
        )


@dataclass(frozen=True, slots=True)
class RegionRenderItem:
    id: str
    revision: int
    mesh: object = field(compare=False, repr=False)
    triangle_indices: tuple[int, ...] = ()
    transform: np.ndarray = field(
        default_factory=lambda: np.identity(4, dtype=float), compare=False, repr=False
    )
    visible: bool = True
    selected: bool = False
    style: DisplayStyleSnapshot = field(default_factory=DisplayStyleSnapshot)
    selection_keys: tuple[str, ...] = ()

    @property
    def world_bounds(self) -> Bounds3 | None:
        vertices = _points(getattr(self.mesh, "vertices", None))
        try:
            faces = np.asarray(getattr(self.mesh, "triangles"), dtype=int).reshape((-1, 3))
        except (AttributeError, TypeError, ValueError):
            return None
        indices = [index for index in self.triangle_indices if 0 <= index < len(faces)]
        if not indices:
            return None
        points = vertices[np.unique(faces[np.asarray(indices, dtype=int)].ravel())]
        bounds = finite_bounds(points)
        return transformed_bounds(bounds, self.transform)


@dataclass(frozen=True, slots=True)
class SectionPlaneRenderItem:
    id: str
    revision: int
    origin: Vector3
    normal: Vector3
    axis: str = "Z"
    offset: float = 0.0
    visible: bool = True
    selected: bool = False
    frame_bounds: Bounds3 | None = None
    style: DisplayStyleSnapshot = field(default_factory=DisplayStyleSnapshot)
    selection_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "origin", _vector3_tuple(self.origin))
        normal = np.asarray(self.normal, dtype=float)
        magnitude = float(np.linalg.norm(normal))
        if not np.isfinite(magnitude) or magnitude <= 1e-12:
            normal = np.asarray([0.0, 0.0, 1.0], dtype=float)
        else:
            normal = normal / magnitude
        object.__setattr__(self, "normal", _vector3_tuple(normal))

    @property
    def world_bounds(self) -> Bounds3 | None:
        return self.frame_bounds


@dataclass(frozen=True, slots=True)
class SectionResultRenderItem:
    id: str
    revision: int
    polylines: tuple[np.ndarray, ...] = field(compare=False, repr=False)
    visible: bool = True
    selected: bool = False
    active: bool = False
    style: DisplayStyleSnapshot = field(default_factory=DisplayStyleSnapshot)
    selection_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "polylines", tuple(_points(line) for line in self.polylines))

    @property
    def world_bounds(self) -> Bounds3 | None:
        return merge_bounds(finite_bounds(line) for line in self.polylines)


@dataclass(frozen=True, slots=True)
class ToolPreviewState:
    revision: int = 0
    active: bool = False
    control_points: np.ndarray = field(
        default_factory=lambda: np.zeros((0, 3), dtype=float), compare=False, repr=False
    )
    point_types: tuple[str, ...] = ()
    fitted_points: np.ndarray = field(
        default_factory=lambda: np.zeros((0, 3), dtype=float), compare=False, repr=False
    )
    closed: bool = False
    plane_normal: Vector3 = (0.0, 0.0, 1.0)
    snap_to_mesh: bool = False
    selected_control_point_index: int | None = None
    curve_method: str = "smooth_guide"
    sample_count: int = 100
    preview_point: Vector3 | None = None
    preview_valid: bool = False
    preview_snaps_closed: bool = False
    preview_snaps_to_mesh: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "control_points", _points(self.control_points))
        object.__setattr__(self, "fitted_points", _points(self.fitted_points))
        object.__setattr__(self, "point_types", tuple(str(value) for value in self.point_types))
        object.__setattr__(self, "plane_normal", _vector3_tuple(self.plane_normal))
        if self.preview_point is not None:
            object.__setattr__(self, "preview_point", _vector3_tuple(self.preview_point))

    @property
    def world_bounds(self) -> Bounds3 | None:
        return merge_bounds(
            (
                finite_bounds(self.control_points),
                finite_bounds(self.fitted_points),
                finite_bounds([self.preview_point]) if self.preview_valid else None,
            )
        )


@dataclass(frozen=True, slots=True)
class SelectionRenderState:
    selected_ids: frozenset[str] = frozenset()
    active_id: str | None = None
    selected_item: str | None = None
    active_curve_id: str | None = None
    active_surface_id: str | None = None
    surface_source_curve_ids: tuple[str, ...] = ()


class CameraRequestKind(str, Enum):
    NONE = "none"
    FRAME_ALL = "frame_all"
    FRAME_SELECTED = "frame_selected"
    FRAME_BOUNDS = "frame_bounds"
    RESET = "reset"
    NAMED_VIEW = "named_view"
    ROLL = "roll"


@dataclass(frozen=True, slots=True)
class CameraRequest:
    kind: CameraRequestKind = CameraRequestKind.NONE
    bounds: Bounds3 | None = None
    selected_ids: frozenset[str] = frozenset()
    view_name: str | None = None
    roll_degrees: float | None = None

    def __post_init__(self) -> None:
        if self.kind is CameraRequestKind.FRAME_BOUNDS and self.bounds is None:
            raise ValueError("Frame-bounds camera requests require bounds.")
        if self.kind is CameraRequestKind.NAMED_VIEW and not self.view_name:
            raise ValueError("Named-view camera requests require a view name.")
        if self.kind is CameraRequestKind.ROLL:
            if self.roll_degrees is None or not math.isfinite(float(self.roll_degrees)):
                raise ValueError("Roll camera requests require a finite angle.")

    @classmethod
    def frame_all(cls) -> "CameraRequest":
        return cls(CameraRequestKind.FRAME_ALL)

    @classmethod
    def frame_selected(cls, selected_ids: Iterable[str]) -> "CameraRequest":
        return cls(
            CameraRequestKind.FRAME_SELECTED,
            selected_ids=frozenset(str(value) for value in selected_ids),
        )

    @classmethod
    def frame_bounds(cls, bounds: Bounds3) -> "CameraRequest":
        return cls(CameraRequestKind.FRAME_BOUNDS, bounds=bounds)

    @classmethod
    def named_view(cls, name: str) -> "CameraRequest":
        return cls(CameraRequestKind.NAMED_VIEW, view_name=str(name))

    @classmethod
    def roll(cls, degrees: float) -> "CameraRequest":
        return cls(CameraRequestKind.ROLL, roll_degrees=float(degrees))


@dataclass(frozen=True, slots=True)
class SceneSnapshot:
    revision: int
    meshes: tuple[MeshRenderItem, ...] = ()
    curves: tuple[CurveRenderItem, ...] = ()
    surfaces: tuple[SurfaceRenderItem, ...] = ()
    regions: tuple[RegionRenderItem, ...] = ()
    section_planes: tuple[SectionPlaneRenderItem, ...] = ()
    section_results: tuple[SectionResultRenderItem, ...] = ()
    tool_preview: ToolPreviewState = field(default_factory=ToolPreviewState)
    selection: SelectionRenderState = field(default_factory=SelectionRenderState)
    display: Mapping[str, object] = field(default_factory=dict, compare=False)
    camera_request: CameraRequest = field(default_factory=CameraRequest)
    object_origin: Vector3 | None = None
    active_transform_mode: str | None = None
    active_transform_axis: str | None = None
    active_transform_angle_delta: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "display", MappingProxyType(dict(self.display)))
        if self.object_origin is not None:
            object.__setattr__(self, "object_origin", _vector3_tuple(self.object_origin))

    def render_items(self) -> tuple[object, ...]:
        return (
            *self.meshes,
            *self.curves,
            *self.surfaces,
            *self.regions,
            *self.section_planes,
            *self.section_results,
        )

    def visible_bounds(self) -> Bounds3 | None:
        item_bounds = [
            getattr(item, "world_bounds", None)
            for item in self.render_items()
            if bool(getattr(item, "visible", True))
        ]
        if self.tool_preview.active:
            item_bounds.append(self.tool_preview.world_bounds)
        return merge_bounds(item_bounds)

    def bounds_for_ids(self, ids: Iterable[str]) -> Bounds3 | None:
        requested = {str(value) for value in ids}
        if not requested:
            return None
        return merge_bounds(
            getattr(item, "world_bounds", None)
            for item in self.render_items()
            if str(getattr(item, "id", "")) in requested
            or requested.intersection(getattr(item, "selection_keys", ()))
        )

    def with_camera_request(self, request: CameraRequest) -> "SceneSnapshot":
        return replace(self, camera_request=request)


def _vector3_tuple(value: Sequence[float] | np.ndarray) -> Vector3:
    array = np.asarray(value, dtype=float).reshape(3)
    if not np.all(np.isfinite(array)):
        raise ValueError("Vector values must be finite.")
    return (float(array[0]), float(array[1]), float(array[2]))


def _color3(value: object, fallback: Vector3) -> Vector3:
    try:
        array = np.asarray(value, dtype=float).reshape(3)
    except (TypeError, ValueError):
        return fallback
    if not np.all(np.isfinite(array)):
        return fallback
    array = np.clip(array, 0.0, 1.0)
    return (float(array[0]), float(array[1]), float(array[2]))


def _finite_float(value: object, fallback: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return fallback
    return result if math.isfinite(result) else fallback


def _finite_clamped(value: object, fallback: float, minimum: float, maximum: float) -> float:
    return min(max(_finite_float(value, fallback), minimum), maximum)


__all__ = (
    "Bounds3",
    "CameraRequest",
    "CameraRequestKind",
    "CurveRenderItem",
    "DisplayStyleSnapshot",
    "MeshRenderItem",
    "RegionRenderItem",
    "SceneSnapshot",
    "SectionPlaneRenderItem",
    "SectionResultRenderItem",
    "SelectionRenderState",
    "SurfaceRenderItem",
    "ToolPreviewState",
    "finite_bounds",
    "geometry_revision",
    "merge_bounds",
    "transformed_bounds",
)
