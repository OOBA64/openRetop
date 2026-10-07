"""Structured viewport picking results and focused VTK picking helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence

import numpy as np

try:
    from vtkmodules.vtkRenderingCore import vtkCellPicker
except ImportError:  # pragma: no cover - application dependency validation handles this.
    vtkCellPicker = None  # type: ignore[assignment,misc]


class PickKind(str, Enum):
    NONE = "none"
    MESH = "mesh"
    SCENE_OBJECT = "scene_object"
    MANUAL_CONTROL_POINT = "manual_control_point"
    CURVE_SEGMENT = "curve_segment"
    OVERBUILD_HANDLE = "overbuild_handle"


@dataclass(frozen=True, slots=True)
class MeshPickResult:
    hit: bool
    position: np.ndarray | None = None
    normal: np.ndarray | None = None
    triangle_index: int | None = None
    mesh_id: str | None = None
    kind: PickKind = PickKind.MESH


@dataclass(frozen=True, slots=True)
class SceneObjectPickResult:
    hit: bool
    object_id: str | None = None
    object_type: str | None = None
    position: np.ndarray | None = None
    kind: PickKind = PickKind.SCENE_OBJECT


@dataclass(frozen=True, slots=True)
class ManualControlPointPickResult:
    hit: bool
    control_point_index: int | None = None
    position: np.ndarray | None = None
    kind: PickKind = PickKind.MANUAL_CONTROL_POINT


@dataclass(frozen=True, slots=True)
class CurveSegmentPickResult:
    hit: bool
    curve_id: str | None = None
    segment_index: int | None = None
    position: np.ndarray | None = None
    parameter: float | None = None
    kind: PickKind = PickKind.CURVE_SEGMENT


@dataclass(frozen=True, slots=True)
class OverbuildHandlePickResult:
    hit: bool
    surface_id: str | None = None
    handle_index: int | None = None
    position: np.ndarray | None = None
    kind: PickKind = PickKind.OVERBUILD_HANDLE


StructuredPickResult = (
    MeshPickResult
    | SceneObjectPickResult
    | ManualControlPointPickResult
    | CurveSegmentPickResult
    | OverbuildHandlePickResult
)


class PickingService:
    """Own VTK picker configuration and actor-to-scene identity mapping."""

    def __init__(self, renderer: object) -> None:
        self.renderer = renderer
        self._actor_objects: dict[int, tuple[str, str]] = {}

    def register_actor(self, actor: object, *, object_id: str, object_type: str) -> None:
        self._actor_objects[id(actor)] = (str(object_id), str(object_type))

    def unregister_actor(self, actor: object) -> None:
        self._actor_objects.pop(id(actor), None)

    def pick_scene_object(self, x_position: int, y_position: int) -> SceneObjectPickResult:
        if vtkCellPicker is None:
            return SceneObjectPickResult(hit=False)
        picker = vtkCellPicker()
        picker.SetTolerance(0.0025)
        if not picker.Pick(float(x_position), float(y_position), 0.0, self.renderer):
            return SceneObjectPickResult(hit=False)
        actor = picker.GetActor()
        identity = self._actor_objects.get(id(actor))
        if identity is None:
            return SceneObjectPickResult(hit=False)
        position = _finite_position(picker.GetPickPosition())
        return SceneObjectPickResult(
            hit=position is not None,
            object_id=identity[0],
            object_type=identity[1],
            position=position,
        )

    def pick_mesh(self, x_position: int, y_position: int) -> MeshPickResult:
        """Return mesh-specific cell data without leaking a VTK picker object."""

        if vtkCellPicker is None:
            return MeshPickResult(hit=False)
        picker = vtkCellPicker()
        picker.SetTolerance(0.0025)
        if not picker.Pick(float(x_position), float(y_position), 0.0, self.renderer):
            return MeshPickResult(hit=False)
        identity = self._actor_objects.get(id(picker.GetActor()))
        cell_id = int(picker.GetCellId())
        if identity is None or identity[1] != "mesh" or cell_id < 0:
            return MeshPickResult(hit=False)
        position = _finite_position(picker.GetPickPosition())
        normal = _finite_position(picker.GetPickNormal())
        return MeshPickResult(
            hit=position is not None,
            position=position,
            normal=normal,
            triangle_index=cell_id,
            mesh_id=identity[0],
        )

    @staticmethod
    def pick_control_point(
        display_point: Sequence[float],
        projected_points: object,
        world_points: object,
        *,
        tolerance_pixels: float = 14.0,
    ) -> ManualControlPointPickResult:
        index = _nearest_projected_index(display_point, projected_points, tolerance_pixels)
        points = np.asarray(world_points, dtype=float).reshape((-1, 3))
        if index is None or index >= len(points):
            return ManualControlPointPickResult(hit=False)
        return ManualControlPointPickResult(True, index, points[index].copy())

    @staticmethod
    def pick_overbuild_handle(
        display_point: Sequence[float],
        projected_points: object,
        world_points: object,
        *,
        surface_id: str | None = None,
        tolerance_pixels: float = 16.0,
    ) -> OverbuildHandlePickResult:
        index = _nearest_projected_index(display_point, projected_points, tolerance_pixels)
        points = np.asarray(world_points, dtype=float).reshape((-1, 3))
        if index is None or index >= len(points):
            return OverbuildHandlePickResult(hit=False)
        return OverbuildHandlePickResult(True, surface_id, index, points[index].copy())

    @staticmethod
    def pick_curve_segment(
        display_point: Sequence[float],
        projected_curves: Mapping[str, object],
        world_curves: Mapping[str, object],
        *,
        tolerance_pixels: float = 12.0,
    ) -> CurveSegmentPickResult:
        target = np.asarray(display_point, dtype=float).reshape(2)
        best: tuple[float, str, int, float] | None = None
        for curve_id, projected in projected_curves.items():
            points = np.asarray(projected, dtype=float).reshape((-1, 2))
            for index in range(max(len(points) - 1, 0)):
                distance, parameter = _point_segment_distance(target, points[index], points[index + 1])
                if best is None or distance < best[0]:
                    best = (distance, str(curve_id), index, parameter)
        if best is None or best[0] > float(tolerance_pixels):
            return CurveSegmentPickResult(hit=False)
        world = np.asarray(world_curves.get(best[1], ()), dtype=float).reshape((-1, 3))
        if best[2] + 1 >= len(world):
            return CurveSegmentPickResult(hit=False)
        position = world[best[2]] + (world[best[2] + 1] - world[best[2]]) * best[3]
        return CurveSegmentPickResult(True, best[1], best[2], position, best[3])


def _nearest_projected_index(
    display_point: Sequence[float], projected_points: object, tolerance: float
) -> int | None:
    points = np.asarray(projected_points, dtype=float).reshape((-1, 2))
    if len(points) == 0:
        return None
    target = np.asarray(display_point, dtype=float).reshape(2)
    distances = np.linalg.norm(points - target, axis=1)
    index = int(np.argmin(distances))
    return index if float(distances[index]) <= float(tolerance) else None


def _point_segment_distance(
    point: np.ndarray, start: np.ndarray, end: np.ndarray
) -> tuple[float, float]:
    direction = end - start
    length_squared = float(np.dot(direction, direction))
    if length_squared <= 1e-12:
        return (float(np.linalg.norm(point - start)), 0.0)
    parameter = min(max(float(np.dot(point - start, direction) / length_squared), 0.0), 1.0)
    closest = start + direction * parameter
    return (float(np.linalg.norm(point - closest)), parameter)


def _finite_position(value: object) -> np.ndarray | None:
    try:
        position = np.asarray(value, dtype=float).reshape(3)
    except (TypeError, ValueError):
        return None
    return position if np.all(np.isfinite(position)) else None


__all__ = (
    "CurveSegmentPickResult",
    "ManualControlPointPickResult",
    "MeshPickResult",
    "OverbuildHandlePickResult",
    "PickKind",
    "PickingService",
    "SceneObjectPickResult",
    "StructuredPickResult",
)
