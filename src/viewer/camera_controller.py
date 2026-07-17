"""Camera math and VTK camera commands for viewport framing."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Sequence

import numpy as np

from viewer.scene_types import Bounds3, CameraRequest, CameraRequestKind, SceneSnapshot


@dataclass(frozen=True, slots=True)
class CameraPose:
    position: tuple[float, float, float]
    focal_point: tuple[float, float, float]
    view_up: tuple[float, float, float]
    clipping_range: tuple[float, float]
    parallel_scale: float


def named_view_vectors(name: str) -> tuple[np.ndarray, np.ndarray]:
    key = str(name).strip().lower()
    directions = {
        "front": ([0.0, -1.0, 0.0], [0.0, 0.0, 1.0]),
        "back": ([0.0, 1.0, 0.0], [0.0, 0.0, 1.0]),
        "left": ([-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]),
        "right": ([1.0, 0.0, 0.0], [0.0, 0.0, 1.0]),
        "top": ([0.0, 0.0, 1.0], [0.0, 1.0, 0.0]),
        "bottom": ([0.0, 0.0, -1.0], [0.0, 1.0, 0.0]),
        "iso": ([1.0, -1.0, 0.75], [0.0, 0.0, 1.0]),
        "isometric": ([1.0, -1.0, 0.75], [0.0, 0.0, 1.0]),
    }
    if key not in directions:
        raise ValueError(f"Unknown named view: {name}")
    direction, view_up = directions[key]
    normalized_direction = _normalized(direction, (1.0, -1.0, 0.75))
    return (normalized_direction, _orthogonal_up(normalized_direction, view_up))


def frame_pose(
    bounds: Bounds3,
    *,
    direction: Sequence[float] = (1.0, -1.0, 0.75),
    view_up: Sequence[float] = (0.0, 0.0, 1.0),
    view_angle_degrees: float = 30.0,
    aspect_ratio: float = 1.0,
    padding: float = 1.12,
) -> CameraPose:
    """Calculate a finite pose for ordinary and degenerate bounds."""

    minimum = np.asarray(bounds[0], dtype=float).reshape(3)
    maximum = np.asarray(bounds[1], dtype=float).reshape(3)
    if not (np.all(np.isfinite(minimum)) and np.all(np.isfinite(maximum))):
        raise ValueError("Camera bounds must be finite.")
    low = np.minimum(minimum, maximum)
    high = np.maximum(minimum, maximum)
    center = (low + high) * 0.5
    size = high - low
    radius = max(float(np.linalg.norm(size)) * 0.5, 1e-6)
    forward = _normalized(direction, (1.0, -1.0, 0.75))
    up = _orthogonal_up(forward, view_up)
    angle = min(max(float(view_angle_degrees), 1.0), 170.0)
    half_angle = math.radians(angle * 0.5)
    aspect = max(float(aspect_ratio), 1e-6)
    limiting_angle = math.atan(math.tan(half_angle) * min(aspect, 1.0))
    distance = max(radius * float(padding) / max(math.sin(limiting_angle), 1e-6), 1e-5)
    position = center + forward * distance
    near = max(distance - radius * 2.5, distance * 1e-5, 1e-7)
    far = max(distance + radius * 2.5, near * 10.0)
    parallel_scale = max(float(np.max(size)) * 0.5 * float(padding), 1e-6)
    return CameraPose(
        position=_tuple3(position),
        focal_point=_tuple3(center),
        view_up=_tuple3(up),
        clipping_range=(float(near), float(far)),
        parallel_scale=float(parallel_scale),
    )


class CameraController:
    """Apply tested camera math to a VTK-like renderer."""

    def __init__(self, renderer: object, request_render: Callable[..., object] | None = None) -> None:
        self.renderer = renderer
        self._request_render = request_render
        self.last_bounds: Bounds3 | None = None

    def apply(self, request: CameraRequest, snapshot: SceneSnapshot) -> bool:
        if request.kind is CameraRequestKind.NONE:
            return False
        if request.kind in {CameraRequestKind.FRAME_ALL, CameraRequestKind.RESET}:
            bounds = snapshot.visible_bounds()
            return False if bounds is None else self.frame_bounds(bounds)
        if request.kind is CameraRequestKind.FRAME_SELECTED:
            ids = request.selected_ids or snapshot.selection.selected_ids
            bounds = snapshot.bounds_for_ids(ids)
            return False if bounds is None else self.frame_bounds(bounds)
        if request.kind is CameraRequestKind.FRAME_BOUNDS:
            assert request.bounds is not None
            return self.frame_bounds(request.bounds)
        if request.kind is CameraRequestKind.NAMED_VIEW:
            assert request.view_name is not None
            # A named view changes orientation, but it must also preserve a
            # useful framing when switching from perspective to orthographic.
            # Re-frame the current visible scene because VTK's default
            # parallel scale is unrelated to the project's world dimensions.
            self.set_named_view(
                request.view_name,
                bounds=snapshot.visible_bounds(),
            )
            return True
        return False

    def frame_bounds(self, bounds: Bounds3) -> bool:
        camera = self.renderer.GetActiveCamera()
        position = np.asarray(camera.GetPosition(), dtype=float)
        focal = np.asarray(camera.GetFocalPoint(), dtype=float)
        direction = position - focal
        if not np.all(np.isfinite(direction)) or float(np.linalg.norm(direction)) <= 1e-12:
            direction = np.asarray([1.0, -1.0, 0.75], dtype=float)
        view_up = np.asarray(camera.GetViewUp(), dtype=float)
        aspect = self._aspect_ratio()
        pose = frame_pose(
            bounds,
            direction=direction,
            view_up=view_up,
            view_angle_degrees=float(camera.GetViewAngle()),
            aspect_ratio=aspect,
        )
        self._apply_pose(camera, pose)
        self.last_bounds = bounds
        self._reset_clipping(pose.clipping_range)
        self._render()
        return True

    def frame_all(self, snapshot: SceneSnapshot) -> bool:
        bounds = snapshot.visible_bounds()
        return False if bounds is None else self.frame_bounds(bounds)

    def frame_selected(self, snapshot: SceneSnapshot, selected_ids: Sequence[str] = ()) -> bool:
        bounds = snapshot.bounds_for_ids(selected_ids or snapshot.selection.selected_ids)
        return False if bounds is None else self.frame_bounds(bounds)

    def reset(self, snapshot: SceneSnapshot) -> bool:
        return self.frame_all(snapshot)

    def set_named_view(
        self,
        name: str,
        *,
        orthographic: bool = True,
        distance: float | None = None,
        bounds: Bounds3 | None = None,
    ) -> None:
        camera = self.renderer.GetActiveCamera()
        direction, view_up = named_view_vectors(name)
        if bounds is not None:
            if orthographic:
                try:
                    camera.ParallelProjectionOn()
                except AttributeError:
                    pass
            pose = frame_pose(
                bounds,
                direction=direction,
                view_up=view_up,
                view_angle_degrees=float(camera.GetViewAngle()),
                aspect_ratio=self._aspect_ratio(),
            )
            self._apply_pose(camera, pose)
            self.last_bounds = bounds
            self._reset_clipping(pose.clipping_range)
            self._render()
            return
        focal = np.asarray(camera.GetFocalPoint(), dtype=float)
        if not np.all(np.isfinite(focal)):
            focal = np.zeros(3, dtype=float)
        current_distance = float(
            np.linalg.norm(np.asarray(camera.GetPosition(), dtype=float) - focal)
        )
        requested_distance = current_distance if distance is None else float(distance)
        camera_distance = (
            requested_distance
            if np.isfinite(requested_distance) and requested_distance > 1e-6
            else current_distance
            if np.isfinite(current_distance) and current_distance > 1e-6
            else 2.8
        )
        position = focal + direction * camera_distance
        camera.SetFocalPoint(*_tuple3(focal))
        camera.SetPosition(*_tuple3(position))
        camera.SetViewUp(*_tuple3(_orthogonal_up(direction, view_up)))
        if orthographic:
            try:
                camera.ParallelProjectionOn()
            except AttributeError:
                pass
        self._reset_clipping(
            (max(camera_distance * 1e-4, 1e-7), max(camera_distance * 4.0, 1.0))
        )
        self._render()

    @staticmethod
    def _apply_pose(camera: object, pose: CameraPose) -> None:
        camera.SetFocalPoint(*pose.focal_point)
        camera.SetPosition(*pose.position)
        camera.SetViewUp(*pose.view_up)
        try:
            if int(camera.GetParallelProjection()):
                camera.SetParallelScale(pose.parallel_scale)
        except AttributeError:
            pass
        camera.SetClippingRange(*pose.clipping_range)

    def _reset_clipping(self, fallback: tuple[float, float]) -> None:
        try:
            self.renderer.ResetCameraClippingRange()
            clipping = self.renderer.GetActiveCamera().GetClippingRange()
            if (
                len(clipping) != 2
                or not all(np.isfinite(float(value)) for value in clipping)
                or float(clipping[0]) <= 0.0
                or float(clipping[1]) <= float(clipping[0])
            ):
                self.renderer.GetActiveCamera().SetClippingRange(*fallback)
        except (AttributeError, TypeError, ValueError):
            self.renderer.GetActiveCamera().SetClippingRange(*fallback)

    def _aspect_ratio(self) -> float:
        try:
            width, height = self.renderer.GetSize()
            return max(float(width), 1.0) / max(float(height), 1.0)
        except (AttributeError, TypeError, ValueError):
            return 1.0

    def _render(self) -> None:
        if self._request_render is not None:
            self._request_render(camera_dirty=True)


def _normalized(value: Sequence[float], fallback: Sequence[float]) -> np.ndarray:
    try:
        vector = np.asarray(value, dtype=float).reshape(3)
    except (TypeError, ValueError):
        vector = np.asarray(fallback, dtype=float).reshape(3)
    length = float(np.linalg.norm(vector))
    if not np.all(np.isfinite(vector)) or not np.isfinite(length) or length <= 1e-12:
        vector = np.asarray(fallback, dtype=float).reshape(3)
        length = float(np.linalg.norm(vector))
    return vector / max(length, 1e-12)


def _orthogonal_up(direction: Sequence[float], candidate: Sequence[float]) -> np.ndarray:
    forward = _normalized(direction, (1.0, -1.0, 0.75))
    up = _normalized(candidate, (0.0, 0.0, 1.0))
    up = up - forward * float(np.dot(up, forward))
    if float(np.linalg.norm(up)) <= 1e-8:
        fallback = np.asarray([0.0, 1.0, 0.0], dtype=float)
        if abs(float(np.dot(fallback, forward))) > 0.95:
            fallback = np.asarray([1.0, 0.0, 0.0], dtype=float)
        up = fallback - forward * float(np.dot(fallback, forward))
    return _normalized(up, (0.0, 0.0, 1.0))


def _tuple3(value: Sequence[float]) -> tuple[float, float, float]:
    array = np.asarray(value, dtype=float).reshape(3)
    return (float(array[0]), float(array[1]), float(array[2]))


__all__ = (
    "CameraController",
    "CameraPose",
    "frame_pose",
    "named_view_vectors",
)
