"""Authoritative transient state for the manual-curve workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from curves.manual_curve import (
    CURVE_POINT_CORNER,
    CURVE_POINT_SMOOTH,
    CURVE_POINT_TANGENT_LOCKED,
    CURVE_POINT_SOURCE_AUTO,
    CURVE_POINT_SOURCE_IMPORTED,
    CURVE_POINT_SOURCE_LEGACY,
    CURVE_POINT_SOURCE_MANUAL,
    DEFAULT_CORNER_ANGLE_THRESHOLD_DEGREES,
    DEFAULT_MANUAL_CURVE_METHOD,
    DEFAULT_MANUAL_CURVE_SAMPLE_COUNT,
    DEFAULT_MANUAL_CURVE_SMOOTHNESS,
    ManualCurveControlDataV2,
    ManualCurvePoint,
)


_VALID_SUBMODES = {
    "inactive",
    "draw_add_points",
    "edit_select",
    "edit_move_point",
    "explicit_add_point",
    "explicit_insert_point",
}


@dataclass
class ManualCurveSessionState:
    """Own every piece of transient state used while drawing or editing a curve."""

    active: bool = False
    editing: bool = False
    edit_curve_id: str | None = None
    submode: str = "inactive"

    control_points: list[np.ndarray] = field(default_factory=list)
    point_types: list[str] = field(default_factory=list)
    point_type_sources: list[str] = field(default_factory=list)
    is_closed: bool = False
    curve_method: str = DEFAULT_MANUAL_CURVE_METHOD
    sample_count: int = DEFAULT_MANUAL_CURVE_SAMPLE_COUNT
    smoothness: int = DEFAULT_MANUAL_CURVE_SMOOTHNESS
    preserve_corners: bool = True
    corner_angle_threshold_degrees: float = DEFAULT_CORNER_ANGLE_THRESHOLD_DEGREES
    auto_detect_corners: bool = False

    plane_origin: np.ndarray = field(
        default_factory=lambda: np.asarray([0.0, 0.0, 0.0], dtype=float)
    )
    plane_normal: np.ndarray = field(
        default_factory=lambda: np.asarray([0.0, 0.0, 1.0], dtype=float)
    )
    plane_type: str = "world_xy"
    plane_label: str = "world XY plane"
    source_section_plane_id: str | None = None

    snap_to_mesh: bool = False
    keep_curve_on_mesh: bool = False
    snap_flags: list[bool] = field(default_factory=list)
    snap_triangle_indices: list[int | None] = field(default_factory=list)
    snap_normals: list[list[float] | None] = field(default_factory=list)
    projection_distances: list[float | None] = field(default_factory=list)
    snapped_point_count: int = 0

    selected_control_point_index: int | None = None
    hover_control_point_index: int | None = None
    drag_candidate_index: int | None = None
    drag_active: bool = False
    left_press_position: tuple[int, int] | None = None
    left_dragged: bool = False

    placing_enabled: bool = True
    add_point_active: bool = False
    insert_point_active: bool = False

    preview_point: np.ndarray | None = None
    preview_valid: bool = False
    preview_snaps_closed: bool = False
    preview_snaps_to_mesh: bool = False
    preview_triangle_index: int | None = None
    preview_normal: list[float] | None = None

    control_point_revision: int = 0
    corner_detection_revision: int = 0

    def reset(self) -> None:
        """Return the session to its inactive defaults."""

        self.active = False
        self.editing = False
        self.edit_curve_id = None
        self.submode = "inactive"
        self.control_points = []
        self.point_types = []
        self.point_type_sources = []
        self.is_closed = False
        self.curve_method = DEFAULT_MANUAL_CURVE_METHOD
        self.sample_count = DEFAULT_MANUAL_CURVE_SAMPLE_COUNT
        self.smoothness = DEFAULT_MANUAL_CURVE_SMOOTHNESS
        self.preserve_corners = True
        self.corner_angle_threshold_degrees = DEFAULT_CORNER_ANGLE_THRESHOLD_DEGREES
        self.auto_detect_corners = False
        self.plane_origin = np.asarray([0.0, 0.0, 0.0], dtype=float)
        self.plane_normal = np.asarray([0.0, 0.0, 1.0], dtype=float)
        self.plane_type = "world_xy"
        self.plane_label = "world XY plane"
        self.source_section_plane_id = None
        self.snap_to_mesh = False
        self.keep_curve_on_mesh = False
        self.snap_flags = []
        self.snap_triangle_indices = []
        self.snap_normals = []
        self.projection_distances = []
        self.snapped_point_count = 0
        self.selected_control_point_index = None
        self.hover_control_point_index = None
        self.drag_candidate_index = None
        self.drag_active = False
        self.left_press_position = None
        self.left_dragged = False
        self.placing_enabled = True
        self.add_point_active = False
        self.insert_point_active = False
        self.clear_preview()
        self.control_point_revision = 0
        self.corner_detection_revision = 0

    def begin_new_curve(
        self,
        *,
        plane_origin: object,
        plane_normal: object,
        plane_type: str = "world_xy",
        plane_label: str = "world XY plane",
        source_section_plane_id: str | None = None,
        snap_to_mesh: bool = False,
        keep_curve_on_mesh: bool = False,
        curve_method: str = DEFAULT_MANUAL_CURVE_METHOD,
        sample_count: int = DEFAULT_MANUAL_CURVE_SAMPLE_COUNT,
        smoothness: int = DEFAULT_MANUAL_CURVE_SMOOTHNESS,
        preserve_corners: bool = True,
        corner_angle_threshold_degrees: float = DEFAULT_CORNER_ANGLE_THRESHOLD_DEGREES,
        auto_detect_corners: bool = False,
    ) -> None:
        self.reset()
        self.active = True
        self.submode = "draw_add_points"
        self.placing_enabled = True
        self._set_plane(
            plane_origin,
            plane_normal,
            plane_type=plane_type,
            plane_label=plane_label,
            source_section_plane_id=source_section_plane_id,
        )
        self._set_options(
            snap_to_mesh=snap_to_mesh,
            keep_curve_on_mesh=keep_curve_on_mesh,
            curve_method=curve_method,
            sample_count=sample_count,
            smoothness=smoothness,
            preserve_corners=preserve_corners,
            corner_angle_threshold_degrees=corner_angle_threshold_degrees,
            auto_detect_corners=auto_detect_corners,
        )
        self.validate_invariants()

    def begin_edit_curve(
        self,
        control_data: ManualCurveControlDataV2,
        *,
        curve_id: str,
        metadata: dict[str, object] | None = None,
        plane_origin: object = (0.0, 0.0, 0.0),
        plane_normal: object = (0.0, 0.0, 1.0),
        plane_type: str = "world_xy",
        plane_label: str = "world XY plane",
        source_section_plane_id: str | None = None,
    ) -> None:
        self.reset()
        self.active = True
        self.editing = True
        self.edit_curve_id = str(curve_id)
        self.submode = "edit_select"
        self.placing_enabled = False
        self._set_plane(
            plane_origin,
            plane_normal,
            plane_type=plane_type,
            plane_label=plane_label,
            source_section_plane_id=source_section_plane_id,
        )
        self.load_control_data_v2(control_data, metadata=metadata)
        self.validate_invariants()

    def exit(self) -> None:
        self.reset()

    def clear_preview(self) -> None:
        self.preview_point = None
        self.preview_valid = False
        self.preview_snaps_closed = False
        self.preview_snaps_to_mesh = False
        self.preview_triangle_index = None
        self.preview_normal = None

    def set_preview(
        self,
        *,
        point: object | None = None,
        valid: bool,
        snaps_closed: bool = False,
        snaps_to_mesh: bool = False,
        triangle_index: int | None = None,
        normal: object | None = None,
    ) -> None:
        point_value = _finite_vector3(point, name="preview point") if valid else None
        self.preview_point = point_value
        self.preview_valid = bool(valid and point_value is not None)
        self.preview_snaps_closed = bool(self.preview_valid and snaps_closed)
        self.preview_snaps_to_mesh = bool(self.preview_valid and snaps_to_mesh)
        self.preview_triangle_index = (
            _optional_int(triangle_index) if self.preview_valid else None
        )
        self.preview_normal = (
            _optional_normal(normal) if self.preview_valid else None
        )

    def append_point(
        self,
        point: object,
        *,
        point_type: str = CURVE_POINT_SMOOTH,
        point_type_source: str = CURVE_POINT_SOURCE_AUTO,
        snapped: bool = False,
        triangle_index: int | None = None,
        normal: object | None = None,
        projection_distance: float | None = None,
    ) -> int:
        self.normalize_parallel_arrays()
        self.control_points.append(_finite_vector3(point, name="control point"))
        self.point_types.append(_point_type(point_type))
        self.point_type_sources.append(_point_source(point_type_source))
        self.snap_flags.append(bool(snapped))
        self.snap_triangle_indices.append(_optional_int(triangle_index))
        self.snap_normals.append(_optional_normal(normal))
        self.projection_distances.append(
            _projection_distance(projection_distance, snapped=bool(snapped))
        )
        self.mark_controls_changed()
        self.validate_invariants()
        return len(self.control_points) - 1

    def insert_point(
        self,
        index: int,
        point: object,
        *,
        point_type: str = CURVE_POINT_SMOOTH,
        point_type_source: str = CURVE_POINT_SOURCE_AUTO,
        snapped: bool = False,
        triangle_index: int | None = None,
        normal: object | None = None,
        projection_distance: float | None = None,
    ) -> int:
        self.normalize_parallel_arrays()
        insert_index = min(max(int(index), 0), len(self.control_points))
        values = (
            (self.control_points, _finite_vector3(point, name="control point")),
            (self.point_types, _point_type(point_type)),
            (self.point_type_sources, _point_source(point_type_source)),
            (self.snap_flags, bool(snapped)),
            (self.snap_triangle_indices, _optional_int(triangle_index)),
            (self.snap_normals, _optional_normal(normal)),
            (
                self.projection_distances,
                _projection_distance(projection_distance, snapped=bool(snapped)),
            ),
        )
        for values_list, value in values:
            values_list.insert(insert_index, value)
        self.mark_controls_changed()
        self.validate_invariants()
        return insert_index

    def remove_point(self, index: int) -> np.ndarray:
        self.normalize_parallel_arrays()
        remove_index = int(index)
        if not 0 <= remove_index < len(self.control_points):
            raise IndexError("Manual curve control-point index is out of range.")
        removed = self.control_points.pop(remove_index)
        for values in (
            self.point_types,
            self.point_type_sources,
            self.snap_flags,
            self.snap_triangle_indices,
            self.snap_normals,
            self.projection_distances,
        ):
            values.pop(remove_index)
        if len(self.control_points) < 3:
            self.is_closed = False
        self._repair_indices_after_remove(remove_index)
        self.mark_controls_changed()
        self.validate_invariants()
        return removed

    def move_point(
        self,
        index: int,
        point: object,
        *,
        snapped: bool | None = None,
        triangle_index: int | None = None,
        normal: object | None = None,
        projection_distance: float | None = None,
        mark_controls_changed: bool = True,
    ) -> None:
        self.normalize_parallel_arrays()
        move_index = int(index)
        if not 0 <= move_index < len(self.control_points):
            raise IndexError("Manual curve control-point index is out of range.")
        self.control_points[move_index] = _finite_vector3(point, name="control point")
        if snapped is not None:
            is_snapped = bool(snapped)
            self.snap_flags[move_index] = is_snapped
            self.snap_triangle_indices[move_index] = _optional_int(triangle_index)
            self.snap_normals[move_index] = _optional_normal(normal)
            self.projection_distances[move_index] = _projection_distance(
                projection_distance,
                snapped=is_snapped,
            )
        if mark_controls_changed:
            self.mark_controls_changed()
        else:
            self.snapped_point_count = sum(self.snap_flags)
        self.validate_invariants()

    def select_point(self, index: int | None) -> int | None:
        self.selected_control_point_index = self._valid_index(index)
        return self.selected_control_point_index

    def normalize_parallel_arrays(self) -> None:
        """Repair imported or compatibility-assigned arrays as one atomic operation."""

        self.control_points = [
            _finite_vector3(point, name="control point") for point in self.control_points
        ]
        count = len(self.control_points)
        self.point_types = _resize_values(
            [_point_type(value) for value in self.point_types],
            count,
            CURVE_POINT_SMOOTH,
        )
        self.point_type_sources = _resize_values(
            [_point_source(value) for value in self.point_type_sources],
            count,
            CURVE_POINT_SOURCE_AUTO,
        )
        self.snap_flags = _resize_values(
            [bool(value) for value in self.snap_flags], count, False
        )
        self.snap_triangle_indices = _resize_values(
            [_optional_int(value) for value in self.snap_triangle_indices], count, None
        )
        self.snap_normals = _resize_values(
            [_optional_normal(value) for value in self.snap_normals], count, None
        )
        self.projection_distances = _resize_values(
            [
                _projection_distance(value, snapped=self.snap_flags[index])
                for index, value in enumerate(self.projection_distances[:count])
            ],
            count,
            None,
        )
        self.snapped_point_count = sum(self.snap_flags)
        self.selected_control_point_index = self._valid_index(
            self.selected_control_point_index
        )
        self.hover_control_point_index = self._valid_index(
            self.hover_control_point_index
        )
        self.drag_candidate_index = self._valid_index(self.drag_candidate_index)
        if self.drag_active and self.drag_candidate_index is None:
            self.drag_active = False
        if self.is_closed and count < 3:
            self.is_closed = False
        self._normalize_plane()

    def mark_controls_changed(self) -> None:
        self.control_point_revision = max(int(self.control_point_revision), 0) + 1
        self.snapped_point_count = sum(bool(value) for value in self.snap_flags)

    def validate_invariants(self) -> None:
        count = len(self.control_points)
        arrays = {
            "point types": self.point_types,
            "point type sources": self.point_type_sources,
            "snap flags": self.snap_flags,
            "snap triangle indices": self.snap_triangle_indices,
            "snap normals": self.snap_normals,
            "projection distances": self.projection_distances,
        }
        for label, values in arrays.items():
            if len(values) != count:
                raise ValueError(
                    f"Manual curve {label} must match the control-point count."
                )
        if any(not np.all(np.isfinite(point)) for point in self.control_points):
            raise ValueError("Manual curve control points must be finite.")
        if self.is_closed and count < 3:
            raise ValueError("A closed manual curve requires at least three points.")
        for label, index in (
            ("selected", self.selected_control_point_index),
            ("hover", self.hover_control_point_index),
            ("drag", self.drag_candidate_index),
        ):
            if index is not None and not 0 <= index < count:
                raise ValueError(f"Manual curve {label} index is out of range.")
        if self.snapped_point_count != sum(bool(value) for value in self.snap_flags):
            raise ValueError("Manual curve snapped-point count is inconsistent.")
        if self.submode not in _VALID_SUBMODES:
            raise ValueError(f"Unknown manual curve submode: {self.submode}")
        self._normalize_plane()
        if not np.all(np.isfinite(self.plane_origin)):
            raise ValueError("Manual curve plane origin must be finite.")
        if not np.all(np.isfinite(self.plane_normal)):
            raise ValueError("Manual curve plane normal must be finite.")
        if not np.isclose(float(np.linalg.norm(self.plane_normal)), 1.0):
            raise ValueError("Manual curve plane normal must be normalized.")

    def to_control_data_v2(self) -> ManualCurveControlDataV2:
        self.normalize_parallel_arrays()
        self.validate_invariants()
        return ManualCurveControlDataV2(
            points=[
                ManualCurvePoint(
                    position=point.copy(),
                    point_type=self.point_types[index],
                    snap_triangle_index=self.snap_triangle_indices[index],
                    snap_normal=self.snap_normals[index],
                    metadata={
                        "point_type_source": self.point_type_sources[index]
                    },
                )
                for index, point in enumerate(self.control_points)
            ],
            is_closed=self.is_closed,
            curve_method=self.curve_method,
            sample_count=self.sample_count,
            corner_angle_threshold_degrees=self.corner_angle_threshold_degrees,
            preserve_corners=self.preserve_corners,
            metadata={
                "smoothness": self.smoothness,
                "control_point_revision": self.control_point_revision,
                "corner_detection_revision": self.corner_detection_revision,
            },
        )

    def load_control_data_v2(
        self,
        control_data: ManualCurveControlDataV2,
        *,
        metadata: dict[str, object] | None = None,
    ) -> None:
        if not isinstance(control_data, ManualCurveControlDataV2):
            raise TypeError("ManualCurveControlDataV2 is required.")
        values = dict(metadata) if isinstance(metadata, dict) else {}
        self.control_points = [point.position.copy() for point in control_data.points]
        self.point_types = [point.point_type for point in control_data.points]
        self.point_type_sources = [
            str(point.metadata.get("point_type_source", CURVE_POINT_SOURCE_AUTO))
            for point in control_data.points
        ]
        self.is_closed = bool(control_data.is_closed)
        self.curve_method = str(control_data.curve_method)
        self.sample_count = _sample_count(control_data.sample_count)
        self.smoothness = _smoothness(
            values.get(
                "smoothness",
                control_data.metadata.get(
                    "smoothness", DEFAULT_MANUAL_CURVE_SMOOTHNESS
                ),
            )
        )
        self.preserve_corners = bool(control_data.preserve_corners)
        self.corner_angle_threshold_degrees = _corner_threshold(
            control_data.corner_angle_threshold_degrees
        )
        self.control_point_revision = _revision(
            values.get(
                "control_point_revision",
                control_data.metadata.get("control_point_revision", 0),
            )
        )
        self.corner_detection_revision = _revision(
            values.get(
                "corner_detection_revision",
                control_data.metadata.get("corner_detection_revision", 0),
            )
        )
        self.snap_to_mesh = bool(
            values.get("snap_to_mesh")
            or str(values.get("snap_mode", "")).strip().lower() == "mesh"
        )
        self.keep_curve_on_mesh = bool(values.get("keep_curve_on_mesh", False))
        self.snap_flags = [self.snap_to_mesh for _point in self.control_points]
        self.snap_triangle_indices = [
            point.snap_triangle_index for point in control_data.points
        ]
        self.snap_normals = [point.snap_normal for point in control_data.points]
        self.projection_distances = list(
            _metadata_sequence(values, "snap_projection_distances")
        )
        self.normalize_parallel_arrays()
        self.validate_invariants()

    def set_closed(self, closed: bool) -> bool:
        value = bool(closed)
        if value and len(self.control_points) < 3:
            return False
        if self.is_closed == value:
            return True
        self.is_closed = value
        self.mark_controls_changed()
        self.validate_invariants()
        return True

    def _set_options(
        self,
        *,
        snap_to_mesh: bool,
        keep_curve_on_mesh: bool,
        curve_method: str,
        sample_count: int,
        smoothness: int,
        preserve_corners: bool,
        corner_angle_threshold_degrees: float,
        auto_detect_corners: bool,
    ) -> None:
        self.snap_to_mesh = bool(snap_to_mesh)
        self.keep_curve_on_mesh = bool(keep_curve_on_mesh)
        self.curve_method = str(curve_method)
        self.sample_count = _sample_count(sample_count)
        self.smoothness = _smoothness(smoothness)
        self.preserve_corners = bool(preserve_corners)
        self.corner_angle_threshold_degrees = _corner_threshold(
            corner_angle_threshold_degrees
        )
        self.auto_detect_corners = bool(auto_detect_corners)

    def _set_plane(
        self,
        origin: object,
        normal: object,
        *,
        plane_type: str,
        plane_label: str,
        source_section_plane_id: str | None,
    ) -> None:
        self.plane_origin = _finite_vector3(origin, name="plane origin")
        try:
            normal_value = np.asarray(normal, dtype=float).reshape(3)
        except (TypeError, ValueError):
            normal_value = np.asarray([0.0, 0.0, 1.0], dtype=float)
        if not np.all(np.isfinite(normal_value)):
            normal_value = np.asarray([0.0, 0.0, 1.0], dtype=float)
        length = float(np.linalg.norm(normal_value))
        self.plane_normal = (
            normal_value / length
            if np.isfinite(length) and length > 1e-12
            else np.asarray([0.0, 0.0, 1.0], dtype=float)
        )
        self.plane_type = str(plane_type)
        self.plane_label = str(plane_label)
        self.source_section_plane_id = (
            None
            if source_section_plane_id is None
            else str(source_section_plane_id)
        )

    def _normalize_plane(self) -> None:
        try:
            origin = np.asarray(self.plane_origin, dtype=float).reshape(3)
        except (TypeError, ValueError) as exc:
            raise ValueError("Manual curve plane origin must be a 3D point.") from exc
        if not np.all(np.isfinite(origin)):
            raise ValueError("Manual curve plane origin must be finite.")
        self.plane_origin = origin
        try:
            normal = np.asarray(self.plane_normal, dtype=float).reshape(3)
        except (TypeError, ValueError):
            normal = np.asarray([0.0, 0.0, 1.0], dtype=float)
        length = float(np.linalg.norm(normal)) if np.all(np.isfinite(normal)) else 0.0
        self.plane_normal = (
            normal / length
            if np.isfinite(length) and length > 1e-12
            else np.asarray([0.0, 0.0, 1.0], dtype=float)
        )

    def _valid_index(self, value: int | None) -> int | None:
        if value is None:
            return None
        try:
            index = int(value)
        except (TypeError, ValueError):
            return None
        return index if 0 <= index < len(self.control_points) else None

    def _repair_indices_after_remove(self, removed_index: int) -> None:
        for field_name in (
            "selected_control_point_index",
            "hover_control_point_index",
            "drag_candidate_index",
        ):
            value = getattr(self, field_name)
            if value is None:
                continue
            if value == removed_index:
                replacement = min(removed_index, len(self.control_points) - 1)
                setattr(self, field_name, replacement if replacement >= 0 else None)
            elif value > removed_index:
                setattr(self, field_name, value - 1)
        if self.drag_candidate_index is None:
            self.drag_active = False


def _finite_vector3(value: object, *, name: str) -> np.ndarray:
    try:
        result = np.asarray(value, dtype=float).reshape(3)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Manual curve {name} must be a 3D point.") from exc
    if not np.all(np.isfinite(result)):
        raise ValueError(f"Manual curve {name} must be finite.")
    return result.copy()


def _point_type(value: object) -> str:
    token = str(value).strip().lower()
    if token in {CURVE_POINT_CORNER, CURVE_POINT_TANGENT_LOCKED}:
        return token
    return CURVE_POINT_SMOOTH


def _point_source(value: object) -> str:
    token = str(value).strip().lower()
    if token in {
        CURVE_POINT_SOURCE_MANUAL,
        CURVE_POINT_SOURCE_LEGACY,
        CURVE_POINT_SOURCE_IMPORTED,
    }:
        return token
    return CURVE_POINT_SOURCE_AUTO


def _optional_int(value: object | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_normal(value: object | None) -> list[float] | None:
    if value is None:
        return None
    try:
        normal = np.asarray(value, dtype=float).reshape(3)
    except (TypeError, ValueError):
        return None
    if not np.all(np.isfinite(normal)):
        return None
    return [float(component) for component in normal]


def _projection_distance(value: object | None, *, snapped: bool) -> float | None:
    if value is None:
        return 0.0 if snapped else None
    try:
        distance = float(value)
    except (TypeError, ValueError):
        return 0.0 if snapped else None
    return distance if np.isfinite(distance) and distance >= 0.0 else (0.0 if snapped else None)


def _resize_values(values: list, count: int, default: object) -> list:
    return (values + [default for _index in range(count)])[:count]


def _sample_count(value: object) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = DEFAULT_MANUAL_CURVE_SAMPLE_COUNT
    return min(max(count, 16), 2048)


def _smoothness(value: object) -> int:
    try:
        result = int(round(float(value)))
    except (TypeError, ValueError):
        result = DEFAULT_MANUAL_CURVE_SMOOTHNESS
    return min(max(result, 1), 8)


def _corner_threshold(value: object) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = DEFAULT_CORNER_ANGLE_THRESHOLD_DEGREES
    if not np.isfinite(result):
        result = DEFAULT_CORNER_ANGLE_THRESHOLD_DEGREES
    return min(max(result, 1.0), 179.0)


def _revision(value: object) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def _metadata_sequence(metadata: dict[str, object], key: str) -> Sequence[object]:
    value = metadata.get(key)
    return value if isinstance(value, list) else ()
