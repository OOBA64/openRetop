"""The manual-curve tool while drawing: the fitted curve, the line to the cursor and the
control points as small shaded spheres, drawn over the whole scene.

The v3 viewport built this preview into every scene snapshot but never drew it, so points
placed with the curve tool were invisible.  Like the original app it is drawn in a layer
above the scan, so the points are never hidden inside or behind it.

Control points are real sphere geometry (VTK's "points as spheres" draws nothing on some
graphics drivers), resized before every frame to a constant size on screen.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np

from openretop.presentation.qt.overlay_layers import create_over_scene_layer
from openretop.viewer.scene_types import ToolPreviewState

POINT_RADIUS_PX = 5.0
SELECTED_RADIUS_PX = 7.0
PREVIEW_RADIUS_PX = 4.0
CURVE_LINE_WIDTH = 2.5
RUBBER_BAND_WIDTH = 1.5

DEFAULT_COLORS = {
    "manual_curve_color": "#FFFFFF",
    "smooth_point_color": "#F5FAFF",
    "corner_point_color": "#FF8C1F",
    "selected_point_color": "#59F2FF",
    "preview_point_color": "#FF7A14",
    "preview_line_color": "#FF7A14",
}


def _rgb(value: object, fallback: str) -> tuple[float, float, float]:
    text = value if isinstance(value, str) and len(value) == 7 and value.startswith("#") else fallback
    try:
        return tuple(int(text[index : index + 2], 16) / 255.0 for index in (1, 3, 5))  # type: ignore[return-value]
    except ValueError:
        return (1.0, 1.0, 1.0)


def world_per_pixel(renderer: object, point: np.ndarray, viewport_height: int) -> float:
    """World units covered by one screen pixel at ``point`` (orthographic or perspective)."""

    camera = renderer.GetActiveCamera()  # type: ignore[attr-defined]
    height = max(int(viewport_height), 1)
    if camera.GetParallelProjection():
        return 2.0 * float(camera.GetParallelScale()) / height
    position = np.asarray(camera.GetPosition(), dtype=float)
    direction = np.asarray(camera.GetDirectionOfProjection(), dtype=float)
    depth = max(float(np.dot(np.asarray(point, dtype=float) - position, direction)), 1e-9)
    return 2.0 * depth * math.tan(math.radians(float(camera.GetViewAngle()) / 2.0)) / height


class ToolPreviewOverlay:
    """Rebuilt when the preview changes; the sphere sizes follow the camera every frame."""

    def __init__(self, renderer: object | None) -> None:
        self.renderer = renderer
        self.layer_renderer: object | None = None
        self.overlay_layer: int | None = None
        self.curve_actor: object | None = None
        self.rubber_band_actor: object | None = None
        self.points_actor: object | None = None
        self._points_data: object | None = None
        self._positions = np.zeros((0, 3), dtype=float)
        self._pixel_radii = np.zeros(0, dtype=float)
        self._key: object | None = None
        self._observer: int | None = None
        self._closed = False
        self.rebuild_count = 0

    @property
    def actors(self) -> list[object]:
        return [actor for actor in (self.curve_actor, self.rubber_band_actor, self.points_actor) if actor is not None]

    @property
    def point_count(self) -> int:
        return int(len(self._positions)) if self.points_actor is not None and self.points_actor.GetVisibility() else 0  # type: ignore[attr-defined]

    def update(self, preview: ToolPreviewState, colors: Mapping[str, object] | None = None) -> bool:
        if self._closed or self.renderer is None:
            return False
        colors = dict(colors or {})
        key = (
            preview.active,
            preview.revision,
            preview.selected_control_point_index,
            preview.point_types,
            preview.preview_point if preview.preview_valid else None,
            preview.highlighted_node_index,
            tuple(sorted((name, str(colors.get(name))) for name in DEFAULT_COLORS)),
        )
        if key == self._key:
            return False
        self._key = key
        if not preview.active:
            for actor in self.actors:
                actor.SetVisibility(False)  # type: ignore[attr-defined]
            self._positions = np.zeros((0, 3), dtype=float)
            return True
        self._ensure_actors()
        color = lambda name: _rgb(colors.get(name), DEFAULT_COLORS[name])  # noqa: E731
        self._set_curve(preview, color("manual_curve_color"))
        self._set_rubber_band(preview, color("preview_line_color"))
        self._set_points(preview, color)
        self._resize_points()
        self.rebuild_count += 1
        return True

    # -- geometry ---------------------------------------------------------------------

    def _set_curve(self, preview: ToolPreviewState, rgb: tuple[float, float, float]) -> None:
        points = np.asarray(preview.fitted_points, dtype=float).reshape(-1, 3)
        if len(points) < 2:
            points = np.asarray(preview.control_points, dtype=float).reshape(-1, 3)
        _set_polyline(self.curve_actor, points, closed=bool(preview.closed) and len(points) > 2)
        self.curve_actor.GetProperty().SetColor(*rgb)  # type: ignore[union-attr]
        self.curve_actor.SetVisibility(len(points) >= 2)  # type: ignore[union-attr]

    def _set_rubber_band(self, preview: ToolPreviewState, rgb: tuple[float, float, float]) -> None:
        controls = np.asarray(preview.control_points, dtype=float).reshape(-1, 3)
        show = bool(preview.preview_valid and preview.preview_point is not None and len(controls))
        if show:
            _set_polyline(self.rubber_band_actor, np.vstack([controls[-1], np.asarray(preview.preview_point, dtype=float)]), closed=False)
            self.rubber_band_actor.GetProperty().SetColor(*rgb)  # type: ignore[union-attr]
        self.rubber_band_actor.SetVisibility(show)  # type: ignore[union-attr]

    def _set_points(self, preview: ToolPreviewState, color: object) -> None:
        from vtkmodules.util.numpy_support import numpy_to_vtk
        from vtkmodules.vtkCommonCore import VTK_UNSIGNED_CHAR, vtkPoints
        from vtkmodules.vtkCommonDataModel import vtkPolyData

        controls = np.asarray(preview.control_points, dtype=float).reshape(-1, 3)
        positions = [row for row in controls]
        radii: list[float] = []
        rgbs: list[tuple[float, float, float]] = []
        for index in range(len(controls)):
            kind = preview.point_types[index] if index < len(preview.point_types) else "smooth"
            if index == preview.selected_control_point_index:
                radii.append(SELECTED_RADIUS_PX)
                rgbs.append(color("selected_point_color"))  # type: ignore[operator]
            else:
                radii.append(POINT_RADIUS_PX)
                rgbs.append(color("corner_point_color" if kind == "corner" else "smooth_point_color"))  # type: ignore[operator]
        if preview.preview_valid and preview.preview_point is not None:
            positions.append(np.asarray(preview.preview_point, dtype=float))
            radii.append(PREVIEW_RADIUS_PX)
            rgbs.append(color("preview_point_color"))  # type: ignore[operator]
        nodes = np.asarray(preview.node_points, dtype=float).reshape(-1, 3)
        for index, node in enumerate(nodes):
            positions.append(node)
            if index == preview.highlighted_node_index:
                radii.append(SELECTED_RADIUS_PX)
                rgbs.append(color("selected_point_color"))  # type: ignore[operator]
            else:
                radii.append(POINT_RADIUS_PX - 1.0)
                rgbs.append(color("smooth_point_color"))  # type: ignore[operator]
        self._positions = np.asarray(positions, dtype=float).reshape(-1, 3)
        self._pixel_radii = np.asarray(radii, dtype=float)

        data = vtkPolyData()
        vtk_points = vtkPoints()
        vtk_points.SetData(numpy_to_vtk(self._positions.copy(), deep=True))
        data.SetPoints(vtk_points)
        scale = numpy_to_vtk(np.ones(len(self._positions), dtype=float), deep=True)
        scale.SetName("radius")
        data.GetPointData().AddArray(scale)
        colors = numpy_to_vtk(
            (np.asarray(rgbs, dtype=float).reshape(-1, 3) * 255.0).round().astype(np.uint8), deep=True, array_type=VTK_UNSIGNED_CHAR
        )
        colors.SetName("rgb")
        data.GetPointData().AddArray(colors)
        self._points_data = data
        self.points_actor.GetMapper().SetInputData(data)  # type: ignore[union-attr]
        self.points_actor.SetVisibility(len(self._positions) > 0)  # type: ignore[union-attr]

    def _resize_points(self) -> None:
        """Keep every sphere the same size on screen, whatever the zoom."""

        if self._points_data is None or not len(self._positions) or self.renderer is None:
            return
        window = self.renderer.GetRenderWindow()  # type: ignore[attr-defined]
        if window is None:
            return
        height = int(window.GetSize()[1]) or 1
        radii = np.array(
            [world_per_pixel(self.renderer, point, height) * pixels for point, pixels in zip(self._positions, self._pixel_radii)]
        )
        array = self._points_data.GetPointData().GetArray("radius")  # type: ignore[attr-defined]
        if array is None or array.GetNumberOfTuples() != len(radii):
            return
        changed = False
        for index, value in enumerate(radii):
            if abs(array.GetValue(index) - value) > 1e-12 * max(abs(value), 1.0):
                array.SetValue(index, float(value))
                changed = True
        if changed:
            array.Modified()
            self._points_data.Modified()  # type: ignore[attr-defined]

    # -- VTK ----------------------------------------------------------------------------

    def _ensure_actors(self) -> None:
        if self.curve_actor is not None:
            return
        from vtkmodules.vtkFiltersSources import vtkSphereSource
        from vtkmodules.vtkRenderingCore import vtkActor, vtkGlyph3DMapper, vtkPolyDataMapper

        created = create_over_scene_layer(self.renderer)
        target = self.renderer
        if created is not None:
            self.layer_renderer, self.overlay_layer = created
            target = self.layer_renderer

        def line_actor(width: float) -> object:
            actor = vtkActor()
            actor.SetMapper(vtkPolyDataMapper())
            actor.GetProperty().LightingOff()
            actor.GetProperty().SetLineWidth(width)
            actor.PickableOff()
            actor.UseBoundsOff()
            target.AddActor(actor)  # type: ignore[union-attr]
            return actor

        self.curve_actor = line_actor(CURVE_LINE_WIDTH)
        self.rubber_band_actor = line_actor(RUBBER_BAND_WIDTH)

        sphere = vtkSphereSource()
        sphere.SetRadius(1.0)
        sphere.SetThetaResolution(20)
        sphere.SetPhiResolution(14)
        mapper = vtkGlyph3DMapper()
        mapper.SetSourceConnection(sphere.GetOutputPort())
        mapper.SetScaleArray("radius")
        mapper.SetScaleModeToScaleByMagnitude()
        mapper.ScalingOn()
        mapper.SetScalarModeToUsePointFieldData()
        mapper.SelectColorArray("rgb")
        mapper.SetColorModeToDirectScalars()
        mapper.ScalarVisibilityOn()
        actor = vtkActor()
        actor.SetMapper(mapper)
        material = actor.GetProperty()
        material.SetInterpolationToPhong()
        material.SetAmbient(0.25)
        material.SetDiffuse(0.8)
        material.SetSpecular(0.45)
        material.SetSpecularPower(40.0)
        actor.PickableOff()
        actor.UseBoundsOff()
        target.AddActor(actor)  # type: ignore[union-attr]
        self.points_actor = actor

        window = self.renderer.GetRenderWindow()  # type: ignore[union-attr]
        if window is not None:
            self._observer = window.AddObserver("StartEvent", lambda *_: self._resize_points())

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        window = None if self.renderer is None else self.renderer.GetRenderWindow()  # type: ignore[attr-defined]
        if window is not None and self._observer is not None:
            window.RemoveObserver(self._observer)
        for actor in self.actors:
            actor.SetVisibility(False)  # type: ignore[attr-defined]
            for owner in (self.layer_renderer, self.renderer):
                if owner is not None:
                    owner.RemoveViewProp(actor)  # type: ignore[attr-defined]
        if window is not None and self.layer_renderer is not None:
            window.RemoveRenderer(self.layer_renderer)
        self.curve_actor = self.rubber_band_actor = self.points_actor = None
        self.layer_renderer = None
        self.renderer = None


def _set_polyline(actor: object, points: np.ndarray, *, closed: bool) -> None:
    from openretop.viewer.vtk_actor_utils import polydata, polyline_cells

    actor.GetMapper().SetInputData(polydata(points, polyline_cells(len(points), closed=closed), cell_kind="lines"))  # type: ignore[attr-defined]


__all__ = ("ToolPreviewOverlay", "world_per_pixel")
