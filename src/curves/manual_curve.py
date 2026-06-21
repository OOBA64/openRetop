"""Manual control-point curve helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from curves.curve_state import StoredCurve


MANUAL_CURVE_METHOD_POLYLINE = "polyline"
MANUAL_CURVE_METHOD_CATMULL_ROM = "catmull_rom"
MANUAL_CURVE_METHOD_HYBRID = "hybrid"
MANUAL_CURVE_METHOD_CAD_SPLINE = "cad_spline"
MANUAL_CURVE_METHOD_SMOOTH_GUIDE = "smooth_guide"
CURVE_POINT_SMOOTH = "smooth"
CURVE_POINT_CORNER = "corner"
CURVE_POINT_TANGENT_LOCKED = "tangent_locked"
CURVE_POINT_SOURCE_MANUAL = "manual"
CURVE_POINT_SOURCE_AUTO = "auto"
CURVE_POINT_SOURCE_LEGACY = "legacy"
CURVE_POINT_SOURCE_IMPORTED = "imported"
CURVE_POINT_TYPES = {
    CURVE_POINT_SMOOTH,
    CURVE_POINT_CORNER,
    CURVE_POINT_TANGENT_LOCKED,
}
DEFAULT_CORNER_ANGLE_THRESHOLD_DEGREES = 135.0
DEFAULT_MANUAL_CURVE_METHOD = MANUAL_CURVE_METHOD_SMOOTH_GUIDE
DEFAULT_MANUAL_CURVE_SAMPLE_COUNT = 128
DEFAULT_MANUAL_CURVE_SMOOTHNESS = 4
MANUAL_CURVE_CLOSE_THRESHOLD_RATIO = 0.01
MANUAL_CURVE_CLOSE_THRESHOLD_MIN = 1e-4


@dataclass(frozen=True)
class ManualCurveControlData:
    control_points: np.ndarray
    is_closed: bool
    curve_method: str = DEFAULT_MANUAL_CURVE_METHOD
    sample_count: int = DEFAULT_MANUAL_CURVE_SAMPLE_COUNT


@dataclass
class ManualCurvePoint:
    position: np.ndarray
    point_type: str = CURVE_POINT_SMOOTH
    tangent_in: np.ndarray | None = None
    tangent_out: np.ndarray | None = None
    weight: float = 1.0
    snap_triangle_index: int | None = None
    snap_normal: list[float] | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.position = _safe_vector3(self.position, fallback=np.zeros(3, dtype=float))
        self.point_type = _normalized_point_type(self.point_type)
        self.tangent_in = _optional_vector3(self.tangent_in)
        self.tangent_out = _optional_vector3(self.tangent_out)
        try:
            weight = float(self.weight)
        except (TypeError, ValueError):
            weight = 1.0
        self.weight = weight if np.isfinite(weight) and weight > 0.0 else 1.0
        if self.snap_triangle_index is not None:
            try:
                self.snap_triangle_index = int(self.snap_triangle_index)
            except (TypeError, ValueError):
                self.snap_triangle_index = None
        self.snap_normal = _json_safe_point_or_none(self.snap_normal)
        self.metadata = dict(self.metadata) if isinstance(self.metadata, dict) else {}
        self.metadata["point_type_source"] = _normalized_point_type_source(
            self.metadata.get("point_type_source", CURVE_POINT_SOURCE_IMPORTED)
        )


@dataclass
class ManualCurveControlDataV2:
    points: list[ManualCurvePoint]
    is_closed: bool
    curve_method: str = MANUAL_CURVE_METHOD_HYBRID
    sample_count: int = DEFAULT_MANUAL_CURVE_SAMPLE_COUNT
    corner_angle_threshold_degrees: float = DEFAULT_CORNER_ANGLE_THRESHOLD_DEGREES
    preserve_corners: bool = True
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.points = [
            point if isinstance(point, ManualCurvePoint) else _manual_curve_point_from_value(point)
            for point in self.points
        ]
        self.is_closed = bool(self.is_closed)
        self.curve_method = _normalized_curve_method(self.curve_method)
        self.sample_count = _normalized_sample_count(self.sample_count)
        self.corner_angle_threshold_degrees = _normalized_corner_threshold(
            self.corner_angle_threshold_degrees
        )
        self.preserve_corners = bool(self.preserve_corners)
        self.metadata = dict(self.metadata) if isinstance(self.metadata, dict) else {}

    @property
    def control_points(self) -> np.ndarray:
        if not self.points:
            return np.zeros((0, 3), dtype=float)
        return np.asarray([point.position for point in self.points], dtype=float).reshape((-1, 3))


def manual_curve_metadata(
    control_points: Sequence[Sequence[float]] | np.ndarray,
    *,
    is_closed: bool,
    creation_type: str,
    snap_to_mesh: bool,
    work_plane_type: str,
    source_section_plane_id: str | None = None,
    source_mesh_name: str | None = None,
    snap_triangle_indices: Sequence[int | None] | None = None,
    snap_normals: Sequence[Sequence[float] | None] | None = None,
    curve_method: str = DEFAULT_MANUAL_CURVE_METHOD,
    sample_count: int = DEFAULT_MANUAL_CURVE_SAMPLE_COUNT,
    point_types: Sequence[str] | None = None,
    point_type_sources: Sequence[str] | None = None,
    corner_angle_threshold_degrees: float = DEFAULT_CORNER_ANGLE_THRESHOLD_DEGREES,
    preserve_corners: bool = True,
    smoothness: int = DEFAULT_MANUAL_CURVE_SMOOTHNESS,
    keep_curve_on_mesh: bool = False,
) -> dict[str, object]:
    points = _safe_points(control_points)
    method = _normalized_curve_method(curve_method)
    metadata: dict[str, object] = {
        "closed": bool(is_closed),
        "control_points": _json_safe_points(points),
        "curve_method": method,
        "sample_count": _normalized_sample_count(sample_count),
        "creation_type": str(creation_type),
        "snap_to_mesh": bool(snap_to_mesh),
        "work_plane_type": str(work_plane_type),
    }
    if bool(snap_to_mesh):
        metadata["snap_mode"] = "mesh"
    if source_section_plane_id is not None:
        metadata["source_section_plane_id"] = str(source_section_plane_id)
    if source_mesh_name:
        metadata["source_mesh_name"] = str(source_mesh_name)
    if snap_triangle_indices is not None:
        metadata["snap_triangle_indices"] = [
            None if index is None else int(index) for index in snap_triangle_indices
        ]
    if snap_normals is not None:
        metadata["snap_normals"] = [
            None if normal is None else _json_safe_point_or_none(normal)
            for normal in snap_normals
        ]
    control_data = manual_curve_control_data_v2(
        points,
        is_closed=bool(is_closed),
        curve_method=method,
        sample_count=sample_count,
        point_types=point_types,
        point_type_sources=point_type_sources,
        corner_angle_threshold_degrees=corner_angle_threshold_degrees,
        preserve_corners=preserve_corners,
        smoothness=smoothness,
        snap_triangle_indices=snap_triangle_indices,
        snap_normals=snap_normals,
    )
    metadata.update(manual_curve_v2_metadata(control_data))
    metadata["smoothness"] = _normalized_smoothness(smoothness)
    metadata["keep_curve_on_mesh"] = bool(keep_curve_on_mesh)
    return metadata


def parse_manual_curve_metadata(curve: object) -> ManualCurveControlData | None:
    metadata = getattr(curve, "metadata", {})
    if not isinstance(metadata, dict):
        return None

    control_points_value = metadata.get("control_points")
    if control_points_value is None:
        return None

    control_points = _safe_points(control_points_value)
    if len(control_points) == 0:
        return None
    sample_count = _normalized_sample_count(
        metadata.get("sample_count", DEFAULT_MANUAL_CURVE_SAMPLE_COUNT)
    )
    return ManualCurveControlData(
        control_points=control_points,
        is_closed=bool(metadata.get("closed", getattr(curve, "is_closed", False))),
        curve_method=_normalized_curve_method(
            metadata.get("curve_method", DEFAULT_MANUAL_CURVE_METHOD)
        ),
        sample_count=sample_count,
    )


def parse_manual_curve_metadata_v2(curve: object) -> ManualCurveControlDataV2 | None:
    """Parse V2 metadata or losslessly upgrade legacy control-point metadata."""

    metadata = getattr(curve, "metadata", {})
    if not isinstance(metadata, dict):
        return None
    control_points = _safe_points(metadata.get("control_points"))
    point_values = metadata.get("control_points_v2")
    points: list[ManualCurvePoint] = []
    if isinstance(point_values, list):
        points = [_manual_curve_point_from_value(value) for value in point_values]
        points = [point for point in points if np.all(np.isfinite(point.position))]
    if not points and len(control_points):
        threshold = _normalized_corner_threshold(
            metadata.get(
                "corner_angle_threshold_degrees",
                DEFAULT_CORNER_ANGLE_THRESHOLD_DEGREES,
            )
        )
        point_types = metadata.get("point_types")
        if not isinstance(point_types, list) or len(point_types) != len(control_points):
            point_types = detect_corner_point_types(
                control_points,
                is_closed=bool(metadata.get("closed", getattr(curve, "is_closed", False))),
                threshold_degrees=threshold,
            )
        triangle_indices = metadata.get("snap_triangle_indices")
        normals = metadata.get("snap_normals")
        point_type_sources = metadata.get("point_type_sources")
        for index, position in enumerate(control_points):
            points.append(
                ManualCurvePoint(
                    position=position,
                    point_type=(
                        point_types[index]
                        if index < len(point_types)
                        else CURVE_POINT_SMOOTH
                    ),
                    snap_triangle_index=_sequence_item(triangle_indices, index),
                    snap_normal=_sequence_item(normals, index),
                    metadata={
                        "point_type_source": (
                            _sequence_item(point_type_sources, index)
                            or CURVE_POINT_SOURCE_LEGACY
                        )
                    },
                )
            )
    if not points:
        return None
    return ManualCurveControlDataV2(
        points=points,
        is_closed=bool(metadata.get("closed", getattr(curve, "is_closed", False))),
        curve_method=_normalized_curve_method(
            metadata.get("curve_method", DEFAULT_MANUAL_CURVE_METHOD)
        ),
        sample_count=_normalized_sample_count(
            metadata.get("sample_count", DEFAULT_MANUAL_CURVE_SAMPLE_COUNT)
        ),
        corner_angle_threshold_degrees=_normalized_corner_threshold(
            metadata.get(
                "corner_angle_threshold_degrees",
                DEFAULT_CORNER_ANGLE_THRESHOLD_DEGREES,
            )
        ),
        preserve_corners=bool(metadata.get("preserve_corners", True)),
        metadata={
            **(
                dict(metadata.get("manual_curve_v2_metadata", {}))
                if isinstance(metadata.get("manual_curve_v2_metadata"), dict)
                else {}
            ),
            "smoothness": _normalized_smoothness(
                metadata.get("smoothness", DEFAULT_MANUAL_CURVE_SMOOTHNESS)
            ),
        },
    )


def is_manual_curve_like(curve: object) -> bool:
    metadata = getattr(curve, "metadata", {})
    if not isinstance(metadata, dict):
        return False

    creation_type = str(metadata.get("creation_type", "")).strip().lower()
    return bool(
        creation_type in {"manual", "curve_on_mesh"}
        or "control_points" in metadata
        or str(metadata.get("snap_mode", "")).strip().lower() == "mesh"
        or str(metadata.get("source", "")).strip().lower() == "manual"
        or bool(metadata.get("manual"))
        or bool(metadata.get("snap_to_mesh"))
    )


def ensure_manual_curve_storage(curve: StoredCurve) -> StoredCurve:
    if not is_manual_curve_like(curve):
        return curve

    metadata = dict(curve.metadata if isinstance(curve.metadata, dict) else {})
    had_control_points = "control_points" in metadata
    control_points = _safe_points(metadata.get("control_points"))
    if len(control_points) == 0:
        control_points = _safe_points(getattr(curve, "original_points", []))
        had_control_points = False
    if len(control_points) == 0:
        control_points = _safe_points(getattr(curve, "fitted_points", []))
        had_control_points = False
    if len(control_points) == 0:
        return curve

    method = _normalized_curve_method(
        metadata.get(
            "curve_method",
            DEFAULT_MANUAL_CURVE_METHOD
            if had_control_points
            else MANUAL_CURVE_METHOD_POLYLINE,
        )
    )
    sample_count = _normalized_sample_count(
        metadata.get("sample_count", DEFAULT_MANUAL_CURVE_SAMPLE_COUNT)
    )
    is_closed = bool(metadata.get("closed", getattr(curve, "is_closed", False)))
    snap_to_mesh = bool(metadata.get("snap_to_mesh")) or str(
        metadata.get("snap_mode", "")
    ).strip().lower() == "mesh"

    metadata["closed"] = is_closed
    metadata["control_points"] = _json_safe_points(control_points)
    metadata["curve_method"] = method
    metadata["sample_count"] = sample_count
    metadata.setdefault(
        "creation_type",
        "curve_on_mesh" if snap_to_mesh else "manual",
    )
    metadata["snap_to_mesh"] = snap_to_mesh
    if snap_to_mesh:
        metadata["snap_mode"] = "mesh"
    metadata.setdefault("work_plane_type", "mesh" if snap_to_mesh else "manual")

    control_data_v2 = parse_manual_curve_metadata_v2(
        type("CurveMetadataView", (), {"metadata": metadata, "is_closed": is_closed})()
    )
    if control_data_v2 is not None and (
        metadata.get("manual_curve_version") == 2
        or "control_points_v2" in metadata
        or "point_types" in metadata
    ):
        metadata.update(manual_curve_v2_metadata(control_data_v2))

    fitted_points = _safe_points(getattr(curve, "fitted_points", []))
    if len(fitted_points) < 2 and len(control_points) >= 2:
        fitted_points = (
            sample_hybrid_manual_curve(control_data_v2)
            if control_data_v2 is not None
            and control_data_v2.curve_method in {
                MANUAL_CURVE_METHOD_HYBRID,
                MANUAL_CURVE_METHOD_CAD_SPLINE,
                MANUAL_CURVE_METHOD_SMOOTH_GUIDE,
            }
            else sample_manual_curve(
                control_points,
                is_closed=is_closed,
                method=method,
                sample_count=sample_count,
            )
        )

    curve.original_points = control_points.copy()
    curve.fitted_points = fitted_points
    curve.is_closed = is_closed
    curve.metadata = metadata
    return curve


def sample_manual_curve(
    control_points: Sequence[Sequence[float]] | np.ndarray,
    *,
    is_closed: bool,
    method: str,
    sample_count: int,
) -> np.ndarray:
    points = _safe_points(control_points)
    point_count = len(points)
    if point_count == 0:
        return np.zeros((0, 3), dtype=float)
    if point_count == 1:
        return points.copy()

    method = _normalized_curve_method(method)
    if method in {
        MANUAL_CURVE_METHOD_HYBRID,
        MANUAL_CURVE_METHOD_CAD_SPLINE,
        MANUAL_CURVE_METHOD_SMOOTH_GUIDE,
    }:
        control_data = manual_curve_control_data_v2(
            points,
            is_closed=bool(is_closed),
            curve_method=method,
            sample_count=sample_count,
        )
        return sample_hybrid_manual_curve(control_data)
    if method == MANUAL_CURVE_METHOD_POLYLINE:
        return _polyline_sample(points, is_closed=bool(is_closed))
    if point_count == 2:
        return _sample_line(points[0], points[1], _normalized_sample_count(sample_count))

    return _catmull_rom_sample(
        points,
        is_closed=bool(is_closed),
        sample_count=_normalized_sample_count(sample_count),
    )


def build_manual_stored_curve(
    *,
    curve_id: str,
    name: str,
    control_points: Sequence[Sequence[float]] | np.ndarray,
    is_closed: bool,
    creation_type: str,
    snap_to_mesh: bool,
    work_plane_type: str,
    source_section_plane_id: str | None = None,
    source_mesh_name: str | None = None,
    snap_triangle_indices: Sequence[int | None] | None = None,
    snap_normals: Sequence[Sequence[float] | None] | None = None,
    curve_method: str = DEFAULT_MANUAL_CURVE_METHOD,
    sample_count: int = DEFAULT_MANUAL_CURVE_SAMPLE_COUNT,
    point_types: Sequence[str] | None = None,
    point_type_sources: Sequence[str] | None = None,
    corner_angle_threshold_degrees: float = DEFAULT_CORNER_ANGLE_THRESHOLD_DEGREES,
    preserve_corners: bool = True,
    smoothness: int = DEFAULT_MANUAL_CURVE_SMOOTHNESS,
    keep_curve_on_mesh: bool = False,
) -> StoredCurve:
    control_array = _safe_points(control_points)
    method = _normalized_curve_method(curve_method)
    count = _normalized_sample_count(sample_count)
    control_data_v2 = manual_curve_control_data_v2(
        control_array,
        is_closed=bool(is_closed),
        curve_method=method,
        sample_count=count,
        point_types=point_types,
        point_type_sources=point_type_sources,
        corner_angle_threshold_degrees=corner_angle_threshold_degrees,
        preserve_corners=preserve_corners,
        smoothness=smoothness,
        snap_triangle_indices=snap_triangle_indices,
        snap_normals=snap_normals,
    )
    fitted_points = (
        sample_hybrid_manual_curve(control_data_v2)
        if method in {
            MANUAL_CURVE_METHOD_HYBRID,
            MANUAL_CURVE_METHOD_CAD_SPLINE,
            MANUAL_CURVE_METHOD_SMOOTH_GUIDE,
        }
        else sample_manual_curve(
            control_array,
            is_closed=bool(is_closed),
            method=method,
            sample_count=count,
        )
    )
    metadata = manual_curve_metadata(
        control_array,
        is_closed=bool(is_closed),
        creation_type=creation_type,
        snap_to_mesh=bool(snap_to_mesh),
        work_plane_type=work_plane_type,
        source_section_plane_id=source_section_plane_id,
        source_mesh_name=source_mesh_name,
        snap_triangle_indices=snap_triangle_indices,
        snap_normals=snap_normals,
        curve_method=method,
        sample_count=count,
        point_types=[point.point_type for point in control_data_v2.points],
        point_type_sources=[
            manual_curve_point_type_source(point)
            for point in control_data_v2.points
        ],
        corner_angle_threshold_degrees=control_data_v2.corner_angle_threshold_degrees,
        preserve_corners=control_data_v2.preserve_corners,
        smoothness=smoothness,
        keep_curve_on_mesh=keep_curve_on_mesh,
    )
    metadata.update(hybrid_curve_diagnostics(control_data_v2, fitted_points))
    return StoredCurve(
        id=str(curve_id),
        name=str(name),
        section_result_id="",
        plane_id=str(source_section_plane_id or ""),
        original_points=control_array.copy(),
        fitted_points=fitted_points,
        mean_error=0.0,
        max_error=0.0,
        is_closed=bool(is_closed),
        visible=True,
        selected=True,
        metadata=metadata,
    )


def manual_curve_control_data_v2(
    control_points: Sequence[Sequence[float]] | np.ndarray,
    *,
    is_closed: bool,
    curve_method: str = MANUAL_CURVE_METHOD_HYBRID,
    sample_count: int = DEFAULT_MANUAL_CURVE_SAMPLE_COUNT,
    point_types: Sequence[str] | None = None,
    point_type_sources: Sequence[str] | None = None,
    corner_angle_threshold_degrees: float = DEFAULT_CORNER_ANGLE_THRESHOLD_DEGREES,
    preserve_corners: bool = True,
    smoothness: int = DEFAULT_MANUAL_CURVE_SMOOTHNESS,
    snap_triangle_indices: Sequence[int | None] | None = None,
    snap_normals: Sequence[Sequence[float] | None] | None = None,
) -> ManualCurveControlDataV2:
    positions = _safe_points(control_points)
    threshold = _normalized_corner_threshold(corner_angle_threshold_degrees)
    has_explicit_point_types = bool(
        point_types is not None and len(point_types) == len(positions)
    )
    if has_explicit_point_types:
        assert point_types is not None
        resolved_types = [_normalized_point_type(value) for value in point_types]
    elif _normalized_curve_method(curve_method) == MANUAL_CURVE_METHOD_SMOOTH_GUIDE:
        resolved_types = [CURVE_POINT_SMOOTH for _point in positions]
    else:
        resolved_types = detect_corner_point_types(
            positions,
            is_closed=bool(is_closed),
            threshold_degrees=threshold,
        )
    points = [
        ManualCurvePoint(
            position=position,
            point_type=resolved_types[index],
            snap_triangle_index=_sequence_item(snap_triangle_indices, index),
            snap_normal=_sequence_item(snap_normals, index),
            metadata={
                "point_type_source": (
                    _sequence_item(point_type_sources, index)
                    or (
                        CURVE_POINT_SOURCE_IMPORTED
                        if has_explicit_point_types
                        or _normalized_curve_method(curve_method)
                        == MANUAL_CURVE_METHOD_SMOOTH_GUIDE
                        else CURVE_POINT_SOURCE_AUTO
                    )
                )
            },
        )
        for index, position in enumerate(positions)
    ]
    return ManualCurveControlDataV2(
        points=points,
        is_closed=bool(is_closed),
        curve_method=curve_method,
        sample_count=sample_count,
        corner_angle_threshold_degrees=threshold,
        preserve_corners=bool(preserve_corners),
        metadata={"smoothness": _normalized_smoothness(smoothness)},
    )


def manual_curve_v2_metadata(
    control_data: ManualCurveControlDataV2,
) -> dict[str, object]:
    return {
        "manual_curve_version": 2,
        "control_points": _json_safe_points(control_data.control_points),
        "control_points_v2": [
            {
                "position": _json_safe_point_or_none(point.position),
                "point_type": point.point_type,
                "tangent_in": _json_safe_point_or_none(point.tangent_in),
                "tangent_out": _json_safe_point_or_none(point.tangent_out),
                "weight": float(point.weight),
                "snap_triangle_index": point.snap_triangle_index,
                "snap_normal": point.snap_normal,
                "metadata": _json_safe_metadata(point.metadata),
            }
            for point in control_data.points
        ],
        "point_types": [point.point_type for point in control_data.points],
        "point_type_sources": [
            manual_curve_point_type_source(point) for point in control_data.points
        ],
        "corner_angle_threshold_degrees": float(
            control_data.corner_angle_threshold_degrees
        ),
        "preserve_corners": bool(control_data.preserve_corners),
        "manual_curve_v2_metadata": _json_safe_metadata(control_data.metadata),
    }


def detect_corner_point_types(
    control_points: Sequence[Sequence[float]] | np.ndarray,
    *,
    is_closed: bool,
    threshold_degrees: float = DEFAULT_CORNER_ANGLE_THRESHOLD_DEGREES,
) -> list[str]:
    points = _safe_points(control_points)
    threshold = _normalized_corner_threshold(threshold_degrees)
    point_types = [CURVE_POINT_SMOOTH for _point in points]
    if len(points) < 3:
        return point_types
    candidates = range(len(points)) if is_closed else range(1, len(points) - 1)
    for index in candidates:
        previous = points[(index - 1) % len(points)]
        current = points[index]
        following = points[(index + 1) % len(points)]
        angle = _interior_angle_degrees(previous, current, following)
        if angle is not None and angle < threshold:
            point_types[index] = CURVE_POINT_CORNER
    return point_types


def auto_detect_manual_curve_corners(
    control_data: ManualCurveControlDataV2,
    *,
    threshold_degrees: float | None = None,
) -> ManualCurveControlDataV2:
    threshold = _normalized_corner_threshold(
        control_data.corner_angle_threshold_degrees
        if threshold_degrees is None
        else threshold_degrees
    )
    point_types = detect_corner_point_types(
        control_data.control_points,
        is_closed=control_data.is_closed,
        threshold_degrees=threshold,
    )
    points: list[ManualCurvePoint] = []
    for index, point in enumerate(control_data.points):
        source = manual_curve_point_type_source(point)
        preserve_manual_corner = bool(
            point.point_type == CURVE_POINT_CORNER
            and source == CURVE_POINT_SOURCE_MANUAL
        )
        detected_type = point.point_type if preserve_manual_corner else point_types[index]
        metadata = dict(point.metadata)
        if not preserve_manual_corner and detected_type == CURVE_POINT_CORNER:
            metadata["point_type_source"] = CURVE_POINT_SOURCE_AUTO
        points.append(
            ManualCurvePoint(
                position=point.position.copy(),
                point_type=detected_type,
                tangent_in=None if point.tangent_in is None else point.tangent_in.copy(),
                tangent_out=None if point.tangent_out is None else point.tangent_out.copy(),
                weight=point.weight,
                snap_triangle_index=point.snap_triangle_index,
                snap_normal=point.snap_normal,
                metadata=metadata,
            )
        )
    return ManualCurveControlDataV2(
        points=points,
        is_closed=control_data.is_closed,
        curve_method=control_data.curve_method,
        sample_count=control_data.sample_count,
        corner_angle_threshold_degrees=threshold,
        preserve_corners=control_data.preserve_corners,
        metadata=dict(control_data.metadata),
    )


def clear_auto_detected_manual_curve_corners(
    control_data: ManualCurveControlDataV2,
) -> ManualCurveControlDataV2:
    """Clear only corner classifications produced by auto detection."""

    points: list[ManualCurvePoint] = []
    for point in control_data.points:
        metadata = dict(point.metadata)
        point_type = point.point_type
        if (
            point_type == CURVE_POINT_CORNER
            and manual_curve_point_type_source(point) == CURVE_POINT_SOURCE_AUTO
        ):
            point_type = CURVE_POINT_SMOOTH
        points.append(
            ManualCurvePoint(
                position=point.position.copy(),
                point_type=point_type,
                tangent_in=None if point.tangent_in is None else point.tangent_in.copy(),
                tangent_out=None if point.tangent_out is None else point.tangent_out.copy(),
                weight=point.weight,
                snap_triangle_index=point.snap_triangle_index,
                snap_normal=point.snap_normal,
                metadata=metadata,
            )
        )
    return ManualCurveControlDataV2(
        points=points,
        is_closed=control_data.is_closed,
        curve_method=control_data.curve_method,
        sample_count=control_data.sample_count,
        corner_angle_threshold_degrees=control_data.corner_angle_threshold_degrees,
        preserve_corners=control_data.preserve_corners,
        metadata=dict(control_data.metadata),
    )


def manual_curve_point_type_source(point: ManualCurvePoint) -> str:
    return _normalized_point_type_source(
        point.metadata.get("point_type_source", CURVE_POINT_SOURCE_IMPORTED)
    )


def simplify_manual_curve_control_data(
    control_data: ManualCurveControlDataV2,
    *,
    tolerance: float,
) -> ManualCurveControlDataV2:
    """Reduce controls while preserving endpoints and manually marked corners."""

    points = control_data.control_points
    if len(points) <= (3 if control_data.is_closed else 2):
        return control_data
    try:
        tolerance_value = float(tolerance)
    except (TypeError, ValueError) as exc:
        raise ValueError("Guide simplification tolerance must be finite and non-negative.") from exc
    if not np.isfinite(tolerance_value) or tolerance_value < 0.0:
        raise ValueError("Guide simplification tolerance must be finite and non-negative.")

    manual_corners = [
        index
        for index, point in enumerate(control_data.points)
        if point.point_type == CURVE_POINT_CORNER
        and manual_curve_point_type_source(point) == CURVE_POINT_SOURCE_MANUAL
    ]
    kept_indices: list[int] = []
    if control_data.is_closed:
        anchors = list(manual_corners)
        if len(anchors) < 2:
            first_anchor = anchors[0] if anchors else 0
            distances = np.linalg.norm(points - points[first_anchor], axis=1)
            second_anchor = int(np.argmax(distances))
            if second_anchor == first_anchor:
                second_anchor = (first_anchor + max(len(points) // 2, 1)) % len(points)
            anchors = [first_anchor, second_anchor]
        for anchor_index, start in enumerate(anchors):
            end = anchors[(anchor_index + 1) % len(anchors)]
            span_indices = [start]
            cursor = start
            while cursor != end or len(span_indices) == 1:
                cursor = (cursor + 1) % len(points)
                span_indices.append(cursor)
                if len(span_indices) > len(points) + 1:
                    break
            local_kept = _rdp_keep_indices(points[span_indices], tolerance_value)
            kept_indices.extend(span_indices[index] for index in local_kept[:-1])
        kept_indices = list(dict.fromkeys(kept_indices))
        if len(kept_indices) < 3:
            kept_indices = list(range(min(3, len(points))))
    else:
        anchors = sorted(set([0, *manual_corners, len(points) - 1]))
        for start, end in zip(anchors[:-1], anchors[1:]):
            span_indices = list(range(start, end + 1))
            local_kept = _rdp_keep_indices(points[span_indices], tolerance_value)
            mapped = [span_indices[index] for index in local_kept]
            if kept_indices and mapped and kept_indices[-1] == mapped[0]:
                mapped = mapped[1:]
            kept_indices.extend(mapped)

    reduced_points = [
        _copy_manual_curve_point(control_data.points[index]) for index in kept_indices
    ]
    return ManualCurveControlDataV2(
        points=reduced_points,
        is_closed=control_data.is_closed,
        curve_method=control_data.curve_method,
        sample_count=control_data.sample_count,
        corner_angle_threshold_degrees=control_data.corner_angle_threshold_degrees,
        preserve_corners=control_data.preserve_corners,
        metadata={
            **control_data.metadata,
            "simplification_tolerance": tolerance_value,
            "source_control_point_count": len(points),
            "result_control_point_count": len(reduced_points),
        },
    )


def _copy_manual_curve_point(point: ManualCurvePoint) -> ManualCurvePoint:
    return ManualCurvePoint(
        position=point.position.copy(),
        point_type=point.point_type,
        tangent_in=None if point.tangent_in is None else point.tangent_in.copy(),
        tangent_out=None if point.tangent_out is None else point.tangent_out.copy(),
        weight=point.weight,
        snap_triangle_index=point.snap_triangle_index,
        snap_normal=point.snap_normal,
        metadata=dict(point.metadata),
    )


def sample_hybrid_manual_curve(
    control_data: ManualCurveControlDataV2,
) -> np.ndarray:
    points = control_data.control_points
    if len(points) <= 1:
        return points.copy()
    if not control_data.preserve_corners:
        return _smooth_span_sample(control_data, points, closed=control_data.is_closed)

    spans = manual_curve_segment_definitions(control_data)
    if not spans:
        return _polyline_sample(points, is_closed=control_data.is_closed)
    if len(spans) == 1 and spans[0]["kind"] == "spline" and spans[0].get("closed"):
        return _smooth_span_sample(control_data, points, closed=True)

    total_segments = max(
        sum(max(len(np.asarray(span["points"])) - 1, 1) for span in spans),
        1,
    )
    sampled_parts: list[np.ndarray] = []
    for span in spans:
        span_points = _safe_points(span["points"])
        if len(span_points) < 2:
            continue
        if span["kind"] == "line":
            sampled = span_points[[0, -1]].copy()
        else:
            span_segments = max(len(span_points) - 1, 1)
            span_sample_count = max(
                3,
                int(np.ceil(control_data.sample_count * span_segments / total_segments)),
            )
            sampled = _smooth_span_sample(
                control_data,
                span_points,
                closed=False,
                sample_count=span_sample_count,
            )
        if sampled_parts and np.allclose(sampled_parts[-1][-1], sampled[0]):
            sampled = sampled[1:]
        if len(sampled):
            sampled_parts.append(sampled)
    if not sampled_parts:
        return np.zeros((0, 3), dtype=float)
    result = np.vstack(sampled_parts)
    if control_data.is_closed and len(result) and not np.allclose(result[0], result[-1]):
        result = np.vstack((result, result[0]))
    if not control_data.is_closed and len(result):
        result[0] = points[0]
        result[-1] = points[-1]
    if not np.all(np.isfinite(result)):
        return _polyline_sample(points, is_closed=control_data.is_closed)
    return result


def sample_smooth_guide_manual_curve(
    control_data: ManualCurveControlDataV2,
) -> np.ndarray:
    """Sample a fair, sparse guide while preserving explicit corner constraints."""

    smooth_data = ManualCurveControlDataV2(
        points=control_data.points,
        is_closed=control_data.is_closed,
        curve_method=MANUAL_CURVE_METHOD_SMOOTH_GUIDE,
        sample_count=control_data.sample_count,
        corner_angle_threshold_degrees=control_data.corner_angle_threshold_degrees,
        preserve_corners=control_data.preserve_corners,
        metadata=dict(control_data.metadata),
    )
    return sample_hybrid_manual_curve(smooth_data)


def _smooth_span_sample(
    control_data: ManualCurveControlDataV2,
    points: np.ndarray,
    *,
    closed: bool,
    sample_count: int | None = None,
) -> np.ndarray:
    count = control_data.sample_count if sample_count is None else sample_count
    if control_data.curve_method == MANUAL_CURVE_METHOD_SMOOTH_GUIDE:
        return _centripetal_catmull_rom_sample(
            points,
            is_closed=closed,
            sample_count=count,
            smoothness=_normalized_smoothness(
                control_data.metadata.get(
                    "smoothness", DEFAULT_MANUAL_CURVE_SMOOTHNESS
                )
            ),
        )
    return _catmull_rom_sample(points, is_closed=closed, sample_count=count)


def manual_curve_segment_definitions(
    control_data: ManualCurveControlDataV2,
) -> list[dict[str, object]]:
    """Return ordered line/spline spans suitable for preview and CAD topology."""

    points = control_data.control_points
    count = len(points)
    if count < 2:
        return []
    if control_data.curve_method == MANUAL_CURVE_METHOD_POLYLINE:
        segment_count = count if control_data.is_closed else count - 1
        return [
            {
                "kind": "line",
                "points": np.asarray(
                    [points[index], points[(index + 1) % count]],
                    dtype=float,
                ),
                "closed": False,
            }
            for index in range(segment_count)
        ]

    hard_indices = [
        index
        for index, point in enumerate(control_data.points)
        if point.point_type in {CURVE_POINT_CORNER, CURVE_POINT_TANGENT_LOCKED}
    ]
    if not control_data.preserve_corners or not hard_indices:
        return [{"kind": "spline", "points": points.copy(), "closed": control_data.is_closed}]

    index_spans: list[list[int]] = []
    if control_data.is_closed:
        if len(hard_indices) == 1:
            start = hard_indices[0]
            index_spans.append(
                [start, *[(start + offset) % count for offset in range(1, count + 1)]]
            )
        for anchor_index, start in enumerate(hard_indices):
            if len(hard_indices) == 1:
                break
            end = hard_indices[(anchor_index + 1) % len(hard_indices)]
            span = [start]
            cursor = start
            while cursor != end:
                cursor = (cursor + 1) % count
                span.append(cursor)
                if len(span) > count + 1:
                    break
            index_spans.append(span)
    else:
        anchors = sorted(set([0, *hard_indices, count - 1]))
        index_spans = [
            list(range(start, end + 1))
            for start, end in zip(anchors[:-1], anchors[1:])
            if end > start
        ]

    spans: list[dict[str, object]] = []
    for indices in index_spans:
        span_points = points[indices]
        has_smooth_interior = any(
            control_data.points[index].point_type == CURVE_POINT_SMOOTH
            for index in indices[1:-1]
        )
        kind = "spline" if len(indices) > 2 and has_smooth_interior else "line"
        spans.append({"kind": kind, "points": span_points, "closed": False})
    return spans


def hybrid_curve_diagnostics(
    control_data: ManualCurveControlDataV2,
    sampled_points: Sequence[Sequence[float]] | np.ndarray | None = None,
) -> dict[str, object]:
    controls = control_data.control_points
    sampled = (
        sample_hybrid_manual_curve(control_data)
        if sampled_points is None
        else _safe_points(sampled_points)
    )
    spans = manual_curve_segment_definitions(control_data)
    corner_angles = [
        angle
        for index, point in enumerate(control_data.points)
        if point.point_type == CURVE_POINT_CORNER
        for angle in [
            _point_angle_for_index(controls, index, closed=control_data.is_closed)
        ]
        if angle is not None
    ]
    segment_lengths = (
        np.linalg.norm(np.diff(sampled, axis=0), axis=1)
        if len(sampled) >= 2
        else np.asarray([], dtype=float)
    )
    endpoint_gap = (
        float(np.linalg.norm(sampled[0] - sampled[-1])) if len(sampled) >= 2 else 0.0
    )
    return {
        "point_count": int(len(sampled)),
        "control_point_count": int(len(controls)),
        "corner_count": sum(
            point.point_type == CURVE_POINT_CORNER for point in control_data.points
        ),
        "smooth_span_count": sum(span["kind"] == "spline" for span in spans),
        "max_corner_angle": max(corner_angles) if corner_angles else 0.0,
        "min_segment_length": float(np.min(segment_lengths)) if len(segment_lengths) else 0.0,
        "endpoint_gap": endpoint_gap,
        "closed": bool(control_data.is_closed),
        "curve_topology": "closed" if control_data.is_closed else "open",
        "overshoot_warning": _hybrid_overshoot_warning(controls, sampled),
    }


def manual_curve_close_threshold(model_extent: float | None) -> float:
    try:
        extent = float(model_extent)
    except (TypeError, ValueError):
        extent = 0.0
    if not np.isfinite(extent) or extent <= 0.0:
        extent = 0.0
    return max(extent * MANUAL_CURVE_CLOSE_THRESHOLD_RATIO, MANUAL_CURVE_CLOSE_THRESHOLD_MIN)


def should_snap_closed_to_first_point(
    control_points: Sequence[Sequence[float]] | np.ndarray,
    candidate_point: Sequence[float] | np.ndarray,
    *,
    model_extent: float | None,
) -> bool:
    points = _safe_points(control_points)
    if len(points) < 3:
        return False
    candidate = _safe_points([candidate_point])
    if len(candidate) != 1:
        return False
    distance = float(np.linalg.norm(candidate[0] - points[0]))
    return bool(distance <= manual_curve_close_threshold(model_extent))


def _catmull_rom_sample(
    points: np.ndarray,
    *,
    is_closed: bool,
    sample_count: int,
) -> np.ndarray:
    point_count = len(points)
    if point_count < 3:
        return _polyline_sample(points, is_closed=is_closed)

    segment_count = point_count if is_closed else point_count - 1
    samples_per_segment = max(int(np.ceil(sample_count / max(segment_count, 1))), 1)
    sampled: list[np.ndarray] = []
    for segment_index in range(segment_count):
        p0, p1, p2, p3 = _catmull_rom_segment_points(
            points,
            segment_index,
            is_closed=is_closed,
        )
        include_endpoint = segment_index == segment_count - 1 and not is_closed
        for step in range(samples_per_segment + (1 if include_endpoint else 0)):
            if step == samples_per_segment and not include_endpoint:
                continue
            t = step / float(samples_per_segment)
            if sampled and step == 0:
                continue
            sampled.append(_catmull_rom_point(p0, p1, p2, p3, t))

    if is_closed and sampled:
        sampled.append(sampled[0].copy())
    result = _safe_points(sampled)
    if not is_closed and len(result) >= 2:
        result[0] = points[0]
        result[-1] = points[-1]
    return result


def _centripetal_catmull_rom_sample(
    points: np.ndarray,
    *,
    is_closed: bool,
    sample_count: int,
    smoothness: int = DEFAULT_MANUAL_CURVE_SMOOTHNESS,
) -> np.ndarray:
    point_count = len(points)
    if point_count < 3:
        return _polyline_sample(points, is_closed=is_closed)

    segment_count = point_count if is_closed else point_count - 1
    samples_per_segment = max(int(np.ceil(sample_count / max(segment_count, 1))), 1)
    sampled: list[np.ndarray] = []
    for segment_index in range(segment_count):
        p1 = points[segment_index % point_count]
        p2 = points[(segment_index + 1) % point_count]
        if is_closed:
            p0 = points[(segment_index - 1) % point_count]
            p3 = points[(segment_index + 2) % point_count]
        else:
            p0 = (
                points[segment_index - 1]
                if segment_index > 0
                else (2.0 * p1) - p2
            )
            p3 = (
                points[segment_index + 2]
                if segment_index + 2 < point_count
                else (2.0 * p2) - p1
            )
        include_endpoint = segment_index == segment_count - 1 and not is_closed
        step_count = samples_per_segment + (1 if include_endpoint else 0)
        for step in range(step_count):
            if sampled and step == 0:
                continue
            factor = step / float(samples_per_segment)
            curve_point = _centripetal_catmull_rom_point(p0, p1, p2, p3, factor)
            linear_point = p1 * (1.0 - factor) + p2 * factor
            smooth_factor = min(max(float(smoothness) / 4.0, 0.25), 1.25)
            sampled.append(
                linear_point + smooth_factor * (curve_point - linear_point)
            )

    if is_closed and sampled:
        sampled.append(sampled[0].copy())
    result = _safe_points(sampled)
    if not is_closed and len(result) >= 2:
        result[0] = points[0]
        result[-1] = points[-1]
    if not np.all(np.isfinite(result)):
        return _catmull_rom_sample(
            points,
            is_closed=is_closed,
            sample_count=sample_count,
        )
    return result


def _centripetal_catmull_rom_point(
    p0: np.ndarray,
    p1: np.ndarray,
    p2: np.ndarray,
    p3: np.ndarray,
    factor: float,
) -> np.ndarray:
    alpha = 0.5

    def knot(previous: float, start: np.ndarray, end: np.ndarray) -> float:
        distance = max(float(np.linalg.norm(end - start)), 1e-9)
        return previous + distance**alpha

    def blend(
        start: np.ndarray,
        end: np.ndarray,
        start_t: float,
        end_t: float,
        value_t: float,
    ) -> np.ndarray:
        span = max(end_t - start_t, 1e-12)
        return ((end_t - value_t) / span) * start + ((value_t - start_t) / span) * end

    t0 = 0.0
    t1 = knot(t0, p0, p1)
    t2 = knot(t1, p1, p2)
    t3 = knot(t2, p2, p3)
    value_t = t1 + min(max(float(factor), 0.0), 1.0) * (t2 - t1)
    a1 = blend(p0, p1, t0, t1, value_t)
    a2 = blend(p1, p2, t1, t2, value_t)
    a3 = blend(p2, p3, t2, t3, value_t)
    b1 = blend(a1, a2, t0, t2, value_t)
    b2 = blend(a2, a3, t1, t3, value_t)
    return blend(b1, b2, t1, t2, value_t)


def _catmull_rom_segment_points(
    points: np.ndarray,
    segment_index: int,
    *,
    is_closed: bool,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    count = len(points)
    if is_closed:
        return (
            points[(segment_index - 1) % count],
            points[segment_index % count],
            points[(segment_index + 1) % count],
            points[(segment_index + 2) % count],
        )

    start = segment_index
    return (
        points[max(start - 1, 0)],
        points[start],
        points[start + 1],
        points[min(start + 2, count - 1)],
    )


def _catmull_rom_point(
    p0: np.ndarray,
    p1: np.ndarray,
    p2: np.ndarray,
    p3: np.ndarray,
    t: float,
) -> np.ndarray:
    t2 = t * t
    t3 = t2 * t
    return 0.5 * (
        (2.0 * p1)
        + (-p0 + p2) * t
        + ((2.0 * p0) - (5.0 * p1) + (4.0 * p2) - p3) * t2
        + (-p0 + (3.0 * p1) - (3.0 * p2) + p3) * t3
    )


def _sample_line(start: np.ndarray, end: np.ndarray, sample_count: int) -> np.ndarray:
    steps = max(sample_count, 2)
    factors = np.linspace(0.0, 1.0, steps)
    return np.asarray(
        [(start * (1.0 - factor)) + (end * factor) for factor in factors],
        dtype=float,
    )


def _polyline_sample(points: np.ndarray, *, is_closed: bool) -> np.ndarray:
    if bool(is_closed) and len(points) >= 3 and not np.allclose(points[0], points[-1]):
        return np.vstack([points, points[0]])
    return points.copy()


def _rdp_keep_indices(points: np.ndarray, tolerance: float) -> list[int]:
    if len(points) <= 2:
        return list(range(len(points)))
    start = points[0]
    end = points[-1]
    segment = end - start
    segment_length = float(np.linalg.norm(segment))
    if segment_length <= 1e-12:
        distances = np.linalg.norm(points[1:-1] - start, axis=1)
    else:
        distances = (
            np.linalg.norm(np.cross(points[1:-1] - start, segment), axis=1)
            / segment_length
        )
    if len(distances) == 0 or float(np.max(distances)) <= tolerance:
        return [0, len(points) - 1]
    split = int(np.argmax(distances)) + 1
    left = _rdp_keep_indices(points[: split + 1], tolerance)
    right = _rdp_keep_indices(points[split:], tolerance)
    return [*left[:-1], *[split + index for index in right]]


def _safe_points(points: object) -> np.ndarray:
    try:
        values = np.asarray(points, dtype=float)
    except (TypeError, ValueError):
        return np.zeros((0, 3), dtype=float)
    if values.size == 0:
        return np.zeros((0, 3), dtype=float)
    try:
        values = values.reshape((-1, 3))
    except ValueError:
        return np.zeros((0, 3), dtype=float)
    finite_mask = np.all(np.isfinite(values), axis=1)
    return values[finite_mask].astype(float, copy=True)


def _json_safe_points(points: Sequence[Sequence[float]] | np.ndarray) -> list[list[float]]:
    return [[float(value) for value in point] for point in _safe_points(points)]


def _json_safe_point_or_none(point: Sequence[float] | np.ndarray) -> list[float] | None:
    points = _json_safe_points([point])
    if not points:
        return None
    return points[0]


def _normalized_curve_method(method: object) -> str:
    value = str(method).strip().lower()
    if value in {
        MANUAL_CURVE_METHOD_POLYLINE,
        MANUAL_CURVE_METHOD_CATMULL_ROM,
        MANUAL_CURVE_METHOD_HYBRID,
        MANUAL_CURVE_METHOD_CAD_SPLINE,
        MANUAL_CURVE_METHOD_SMOOTH_GUIDE,
    }:
        return value
    return DEFAULT_MANUAL_CURVE_METHOD


def _normalized_sample_count(sample_count: object) -> int:
    try:
        value = int(sample_count)
    except (TypeError, ValueError):
        value = DEFAULT_MANUAL_CURVE_SAMPLE_COUNT
    return max(value, 2)


def _normalized_point_type(value: object) -> str:
    token = str(value).strip().lower()
    return token if token in CURVE_POINT_TYPES else CURVE_POINT_SMOOTH


def _normalized_point_type_source(value: object) -> str:
    token = str(value).strip().lower()
    if token in {
        CURVE_POINT_SOURCE_MANUAL,
        CURVE_POINT_SOURCE_AUTO,
        CURVE_POINT_SOURCE_LEGACY,
        CURVE_POINT_SOURCE_IMPORTED,
    }:
        return token
    return CURVE_POINT_SOURCE_IMPORTED


def _normalized_smoothness(value: object) -> int:
    try:
        smoothness = int(round(float(value)))
    except (TypeError, ValueError):
        smoothness = DEFAULT_MANUAL_CURVE_SMOOTHNESS
    return min(max(smoothness, 1), 8)


def _normalized_corner_threshold(value: object) -> float:
    try:
        threshold = float(value)
    except (TypeError, ValueError):
        threshold = DEFAULT_CORNER_ANGLE_THRESHOLD_DEGREES
    if not np.isfinite(threshold):
        threshold = DEFAULT_CORNER_ANGLE_THRESHOLD_DEGREES
    return min(max(threshold, 1.0), 179.0)


def _safe_vector3(value: object, *, fallback: np.ndarray) -> np.ndarray:
    try:
        vector = np.asarray(value, dtype=float).reshape((3,))
    except (TypeError, ValueError):
        return np.asarray(fallback, dtype=float).reshape((3,)).copy()
    if not np.all(np.isfinite(vector)):
        return np.asarray(fallback, dtype=float).reshape((3,)).copy()
    return vector.copy()


def _optional_vector3(value: object) -> np.ndarray | None:
    if value is None:
        return None
    vector = _safe_vector3(value, fallback=np.asarray([np.nan, np.nan, np.nan]))
    return vector if np.all(np.isfinite(vector)) else None


def _manual_curve_point_from_value(value: object) -> ManualCurvePoint:
    if isinstance(value, ManualCurvePoint):
        return value
    if not isinstance(value, dict):
        return ManualCurvePoint(position=value)
    data = value
    return ManualCurvePoint(
        position=data.get("position", [0.0, 0.0, 0.0]),
        point_type=data.get("point_type", CURVE_POINT_SMOOTH),
        tangent_in=data.get("tangent_in"),
        tangent_out=data.get("tangent_out"),
        weight=data.get("weight", 1.0),
        snap_triangle_index=data.get("snap_triangle_index"),
        snap_normal=data.get("snap_normal"),
        metadata=data.get("metadata", {}),
    )


def _sequence_item(values: object, index: int) -> object:
    if isinstance(values, Sequence) and not isinstance(values, str):
        return values[index] if index < len(values) else None
    return None


def _json_safe_metadata(metadata: object) -> dict[str, object]:
    if not isinstance(metadata, dict):
        return {}
    result: dict[str, object] = {}
    for key, value in metadata.items():
        if not isinstance(key, str):
            continue
        if value is None or isinstance(value, str | int | float | bool):
            result[key] = value
        elif isinstance(value, list):
            result[key] = [
                item
                for item in value
                if item is None or isinstance(item, str | int | float | bool)
            ]
    return result


def _interior_angle_degrees(
    previous: np.ndarray,
    current: np.ndarray,
    following: np.ndarray,
) -> float | None:
    incoming = np.asarray(previous, dtype=float) - np.asarray(current, dtype=float)
    outgoing = np.asarray(following, dtype=float) - np.asarray(current, dtype=float)
    incoming_length = float(np.linalg.norm(incoming))
    outgoing_length = float(np.linalg.norm(outgoing))
    if incoming_length <= 1e-12 or outgoing_length <= 1e-12:
        return None
    cosine = float(
        np.clip(
            np.dot(incoming, outgoing) / (incoming_length * outgoing_length),
            -1.0,
            1.0,
        )
    )
    return float(np.degrees(np.arccos(cosine)))


def _point_angle_for_index(
    points: np.ndarray,
    index: int,
    *,
    closed: bool,
) -> float | None:
    if len(points) < 3 or (not closed and index in {0, len(points) - 1}):
        return None
    return _interior_angle_degrees(
        points[(index - 1) % len(points)],
        points[index],
        points[(index + 1) % len(points)],
    )


def _hybrid_overshoot_warning(
    controls: np.ndarray,
    sampled: np.ndarray,
) -> str:
    if len(controls) == 0 or len(sampled) == 0:
        return ""
    minimum = np.min(controls, axis=0)
    maximum = np.max(controls, axis=0)
    extent = max(float(np.max(maximum - minimum)), 1e-9)
    tolerance = extent * 0.10
    if np.any(sampled < minimum - tolerance) or np.any(sampled > maximum + tolerance):
        return "Sampled curve leaves the local control polygon; inspect overshoot."
    return ""
