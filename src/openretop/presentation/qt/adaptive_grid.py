"""A ground grid that follows the camera instead of the scene.

* spacing snaps to 1-2-5 steps of the project unit and changes as you zoom, so there are
  always roughly ten to twenty lines across the view;
* it is centred under the view and recentres, in whole major steps, as you pan, and reaches
  well past the edges;
* minor lines, stronger major lines every tenth line, coloured X and Y axis lines through
  the origin, and a fade towards the edges so it never ends in a hard border;
* its geometry is rebuilt only when the spacing, the snapped centre or the extent changes.

The grid does not depend on the scene's bounds, so dragging an object can never rescale it.
The pure functions at the top are tested without VTK.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

TARGET_LINES_ACROSS_VIEW = 12.0
KEEP_RANGE = (6.0, 24.0)  # keep the current spacing while this many lines span the view
MAJOR_EVERY = 10
EXTENT_IN_VIEWS = 2.2  # half-size of the grid, in visible spans, before rounding up
MAX_LINES_PER_DIRECTION = 300
SEGMENTS_PER_LINE = 24  # each line is split so the fade can vary along it

MINOR_COLOR = (0.30, 0.34, 0.39)
MAJOR_COLOR = (0.44, 0.50, 0.58)
X_AXIS_COLOR = (0.90, 0.28, 0.28)
Y_AXIS_COLOR = (0.34, 0.80, 0.34)
MINOR_ALPHA = 0.50
MAJOR_ALPHA = 0.85
AXIS_ALPHA = 0.95


@dataclass(frozen=True, slots=True)
class GridSpec:
    spacing: float
    centre: tuple[float, float]  # in-plane centre, a multiple of the major step
    half_extent: float  # a multiple of the major step

    @property
    def major_step(self) -> float:
        return self.spacing * MAJOR_EVERY


def nice_step(value: float) -> float:
    """The 1-2-5 x 10^n step nearest ``value`` on a log scale (value > 0)."""

    if not math.isfinite(value) or value <= 0.0:
        return 1.0
    exponent = math.floor(math.log10(value))
    scale = 10.0**exponent
    mantissa = value / scale
    candidates = (1.0, 2.0, 5.0, 10.0)
    best = min(candidates, key=lambda candidate: abs(math.log(mantissa / candidate)))
    return best * scale


def choose_spacing(span: float, current: float | None = None) -> float:
    """Pick the grid spacing for a view ``span`` world units across.

    ``current`` adds hysteresis: the spacing only changes once the number of lines across the
    view leaves ``KEEP_RANGE``, so it does not flicker while zooming across a boundary.
    """

    if not math.isfinite(span) or span <= 0.0:
        return current if current is not None else 1.0
    if current is not None and current > 0.0:
        lines = span / current
        if KEEP_RANGE[0] <= lines <= KEEP_RANGE[1]:
            return current
    return nice_step(span / TARGET_LINES_ACROSS_VIEW)


def plan_grid(span: float, focal_xy: tuple[float, float], current_spacing: float | None = None) -> GridSpec:
    """Spacing, snapped centre and extent for a view ``span`` across, looking at ``focal_xy``."""

    spacing = choose_spacing(span, current_spacing)
    major = spacing * MAJOR_EVERY
    centre = (round(focal_xy[0] / major) * major, round(focal_xy[1] / major) * major)
    half = max(math.ceil(EXTENT_IN_VIEWS * max(span, spacing) / major), 1) * major
    cap = max(math.floor((MAX_LINES_PER_DIRECTION / 2) * spacing / major), 1) * major
    half = min(half, cap)
    return GridSpec(spacing=spacing, centre=(float(centre[0]), float(centre[1])), half_extent=float(half))


def visible_span(
    *,
    parallel: bool,
    parallel_scale: float,
    view_angle_degrees: float,
    distance: float,
    aspect: float,
) -> float:
    """The longer side of the visible rectangle, in world units at the focal distance."""

    if parallel:
        height = 2.0 * float(parallel_scale)
    else:
        height = 2.0 * float(distance) * math.tan(math.radians(float(view_angle_degrees)) / 2.0)
    aspect = float(aspect) if math.isfinite(aspect) and aspect > 0.0 else 1.0
    return max(height, height * aspect)


def grid_lines(spec: GridSpec) -> tuple[list[float], list[float]]:
    """Coordinates of the minor lines and of the major lines (as offsets from the centre)."""

    count = int(round(spec.half_extent / spec.spacing))
    minor: list[float] = []
    major: list[float] = []
    for index in range(-count, count + 1):
        (major if index % MAJOR_EVERY == 0 else minor).append(index * spec.spacing)
    return minor, major


def fade(radius: np.ndarray, half_extent: float) -> np.ndarray:
    """1 at the centre, 0 at ``half_extent``: smooth, so the grid never ends in a hard edge."""

    t = np.clip(np.asarray(radius, dtype=float) / max(half_extent, 1e-12), 0.0, 1.0)
    return (1.0 - t * t) ** 1.5


def build_line_geometry(spec: GridSpec) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Points, RGBA (uint8) and segment indices for ``lines`` (minor + major) and ``axes``.

    Lines are in the z=0 plane, running across the whole extent, centred on ``spec.centre``.
    The X and Y axes pass through the world origin when it lies inside the extent.
    """

    cx, cy = spec.centre
    half = spec.half_extent
    minor, major = grid_lines(spec)
    t = np.linspace(-half, half, SEGMENTS_PER_LINE + 1)

    def lines_for(offsets_world: Sequence[float], axis: str) -> tuple[np.ndarray, np.ndarray]:
        points = []
        for offset in offsets_world:
            if axis == "x":  # a line parallel to X at a given y
                y = cy + offset
                points.append(np.column_stack((cx + t, np.full_like(t, y), np.zeros_like(t))))
            else:  # parallel to Y at a given x
                x = cx + offset
                points.append(np.column_stack((np.full_like(t, x), cy + t, np.zeros_like(t))))
        if not points:
            return np.zeros((0, 3)), np.zeros(0, dtype=int)
        stacked = np.vstack(points)
        return stacked, np.arange(len(points)) * (SEGMENTS_PER_LINE + 1)

    def assemble(
        groups: list[tuple[Sequence[float], tuple[float, float, float], float]],
        *,
        extra_axes: bool = False,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        all_points: list[np.ndarray] = []
        all_colors: list[np.ndarray] = []
        all_segments: list[np.ndarray] = []
        base = 0
        for offsets, color, alpha in groups:
            for axis in ("x", "y"):
                points, starts = lines_for(offsets, axis)
                if len(points) == 0:
                    continue
                radius = np.hypot(points[:, 0] - cx, points[:, 1] - cy)
                strength = fade(radius, half) * alpha
                rgba = np.empty((len(points), 4), dtype=np.uint8)
                rgba[:, 0:3] = np.round(np.asarray(color) * 255.0)
                rgba[:, 3] = np.round(strength * 255.0)
                segments = np.concatenate(
                    [np.column_stack((s + np.arange(SEGMENTS_PER_LINE), s + np.arange(SEGMENTS_PER_LINE) + 1)) for s in starts]
                )
                all_points.append(points)
                all_colors.append(rgba)
                all_segments.append(segments + base)
                base += len(points)
        if not all_points:
            return np.zeros((0, 3)), np.zeros((0, 4), dtype=np.uint8), np.zeros((0, 2), dtype=int)
        return np.vstack(all_points), np.vstack(all_colors), np.vstack(all_segments)

    lines = assemble([(minor, MINOR_COLOR, MINOR_ALPHA), (major, MAJOR_COLOR, MAJOR_ALPHA)])

    # axis lines: X (red) along y = 0 and Y (green) along x = 0, if the origin is inside the grid
    axis_points: list[np.ndarray] = []
    axis_colors: list[np.ndarray] = []
    axis_segments: list[np.ndarray] = []
    base = 0
    for color, along_x in ((X_AXIS_COLOR, True), (Y_AXIS_COLOR, False)):
        inside = abs(cy) <= half if along_x else abs(cx) <= half
        if not inside:
            continue
        if along_x:
            points = np.column_stack((cx + t, np.zeros_like(t), np.zeros_like(t)))
        else:
            points = np.column_stack((np.zeros_like(t), cy + t, np.zeros_like(t)))
        radius = np.hypot(points[:, 0] - cx, points[:, 1] - cy)
        rgba = np.empty((len(points), 4), dtype=np.uint8)
        rgba[:, 0:3] = np.round(np.asarray(color) * 255.0)
        rgba[:, 3] = np.round(fade(radius, half) * AXIS_ALPHA * 255.0)
        axis_points.append(points)
        axis_colors.append(rgba)
        axis_segments.append(np.column_stack((np.arange(SEGMENTS_PER_LINE), np.arange(SEGMENTS_PER_LINE) + 1)) + base)
        base += len(points)
    if axis_points:
        axes = (np.vstack(axis_points), np.vstack(axis_colors), np.vstack(axis_segments))
    else:
        axes = (np.zeros((0, 3)), np.zeros((0, 4), dtype=np.uint8), np.zeros((0, 2), dtype=int))
    return {"lines": lines, "axes": axes}


def format_spacing(spacing: float, units: str) -> str:
    """``10 mm`` / ``0.5 in`` for the status bar."""

    text = f"{spacing:.6g}"
    return f"{text} {units}".strip()


class AdaptiveGrid:
    """The VTK side: two actors (grid lines, axis lines) rebuilt only when the plan changes."""

    def __init__(self, renderer: object | None, on_spacing_changed: Callable[[float], None] | None = None) -> None:
        self.renderer = renderer
        self._on_spacing_changed = on_spacing_changed
        self.lines_actor: object | None = None
        self.axes_actor: object | None = None
        self.spec: GridSpec | None = None
        self.rebuild_count = 0
        self.visible = True
        self._camera: object | None = None
        self._observer_id: int | None = None
        self._closed = False

    @property
    def spacing(self) -> float | None:
        return None if self.spec is None else self.spec.spacing

    def set_visible(self, visible: bool) -> None:
        self.visible = bool(visible)
        for actor in (self.lines_actor, self.axes_actor):
            if actor is not None:
                actor.SetVisibility(self.visible)  # type: ignore[attr-defined]
        if self.visible:
            self.sync()

    def sync(self) -> bool:
        """Re-plan from the camera; True if the geometry was rebuilt."""

        if self._closed or self.renderer is None or not self.visible:
            return False
        camera = self.renderer.GetActiveCamera()  # type: ignore[attr-defined]
        self._observe(camera)
        try:
            width, height = self.renderer.GetSize()  # type: ignore[attr-defined]
            aspect = float(width) / float(height) if height else 1.0
            position = np.asarray(camera.GetPosition(), dtype=float)
            focal = np.asarray(camera.GetFocalPoint(), dtype=float)
            span = visible_span(
                parallel=bool(camera.GetParallelProjection()),
                parallel_scale=float(camera.GetParallelScale()),
                view_angle_degrees=float(camera.GetViewAngle()),
                distance=float(np.linalg.norm(position - focal)),
                aspect=aspect,
            )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False
        if not (math.isfinite(span) and span > 0.0 and np.all(np.isfinite(focal))):
            return False
        spec = plan_grid(span, (float(focal[0]), float(focal[1])), self.spacing)
        if spec == self.spec:
            return False
        previous = self.spacing
        self._rebuild(spec)
        if previous != spec.spacing and self._on_spacing_changed is not None:
            self._on_spacing_changed(spec.spacing)
        return True

    def _observe(self, camera: object) -> None:
        if camera is self._camera:
            return
        if self._camera is not None and self._observer_id is not None:
            try:
                self._camera.RemoveObserver(self._observer_id)  # type: ignore[attr-defined]
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass
        self._camera = camera
        self._observer_id = int(camera.AddObserver("ModifiedEvent", self._on_camera_modified))  # type: ignore[attr-defined]

    def _on_camera_modified(self, _caller: object, _event: object) -> None:
        self.sync()

    def _rebuild(self, spec: GridSpec) -> None:
        geometry = build_line_geometry(spec)
        if self.lines_actor is None:
            self._create_actors()
        assert self.lines_actor is not None and self.axes_actor is not None
        _set_polydata(self.lines_actor, *geometry["lines"])
        _set_polydata(self.axes_actor, *geometry["axes"])
        self.spec = spec
        self.rebuild_count += 1

    def _create_actors(self) -> None:
        from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper

        def make(width: float) -> object:
            mapper = vtkPolyDataMapper()
            mapper.SetColorModeToDirectScalars()
            mapper.SetScalarModeToUsePointData()
            mapper.ScalarVisibilityOn()
            actor = vtkActor()
            actor.SetMapper(mapper)
            actor.GetProperty().SetLineWidth(width)
            actor.GetProperty().LightingOff()
            actor.PickableOff()
            actor.DragableOff()
            actor.SetVisibility(self.visible)
            self.renderer.AddActor(actor)  # type: ignore[union-attr, attr-defined]
            return actor

        self.lines_actor = make(1.0)
        self.axes_actor = make(2.0)

    def close(self) -> None:
        if self._closed:
            return
        if self._camera is not None and self._observer_id is not None:
            try:
                self._camera.RemoveObserver(self._observer_id)  # type: ignore[attr-defined]
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass
        for actor in (self.lines_actor, self.axes_actor):
            if actor is not None and self.renderer is not None:
                try:
                    self.renderer.RemoveActor(actor)  # type: ignore[attr-defined]
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    pass
        self.lines_actor = self.axes_actor = None
        self._camera = None
        self._observer_id = None
        self.renderer = None
        self._on_spacing_changed = None
        self._closed = True


def _set_polydata(actor: object, points: np.ndarray, rgba: np.ndarray, segments: np.ndarray) -> None:
    from vtkmodules import vtkCommonCore
    from vtkmodules.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray
    from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData

    data = vtkPolyData()
    vtk_points = vtkCommonCore.vtkPoints()
    if len(points):
        vtk_points.SetData(numpy_to_vtk(np.ascontiguousarray(points, dtype=np.float64), deep=True))
        colors = numpy_to_vtk(np.ascontiguousarray(rgba, dtype=np.uint8), deep=True, array_type=vtkCommonCore.VTK_UNSIGNED_CHAR)
        colors.SetName("grid_rgba")
        data.GetPointData().SetScalars(colors)
    data.SetPoints(vtk_points)
    cells = vtkCellArray()
    if len(segments):
        connectivity = np.ascontiguousarray(segments.reshape(-1), dtype=np.int64)
        offsets = np.arange(0, len(connectivity) + 1, 2, dtype=np.int64)
        cells.SetData(numpy_to_vtkIdTypeArray(offsets, deep=True), numpy_to_vtkIdTypeArray(connectivity, deep=True))
    data.SetLines(cells)
    actor.GetMapper().SetInputData(data)  # type: ignore[attr-defined]


__all__ = (
    "AdaptiveGrid",
    "GridSpec",
    "build_line_geometry",
    "choose_spacing",
    "fade",
    "format_spacing",
    "grid_lines",
    "nice_step",
    "plan_grid",
    "visible_span",
)
