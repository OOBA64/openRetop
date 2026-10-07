"""Measurement lines, end points and distance labels, drawn over the whole scene."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from openretop.application.measure_controller import format_length
from openretop.application.state import Measurement
from openretop.presentation.qt.overlay_layers import create_over_scene_layer

LINE_COLOR = (1.0, 0.78, 0.18)
PENDING_COLOR = (1.0, 1.0, 1.0)
LINE_WIDTH = 2.5
MARKER_FONT_SIZE = 44  # a bullet glyph: round at any zoom and drawn reliably (point sprites are not)
MARKER_GLYPH = "•"
LABEL_FONT_SIZE = 15

Point = tuple[float, float, float]


def label_text(measurement: Measurement, units: str) -> str:
    dx, dy, dz = (abs(value) for value in measurement.delta)
    return (
        f"{format_length(measurement.distance, units)}\n"
        f"dX {format_length(dx, units)}  dY {format_length(dy, units)}  dZ {format_length(dz, units)}"
    )


class MeasurementOverlay:
    """Rebuilt only when the measurements, the pending point or the units change."""

    def __init__(self, renderer: object | None) -> None:
        self.renderer = renderer
        self.layer_renderer: object | None = None
        self.overlay_layer: int | None = None
        self.lines_actor: object | None = None
        self.marker_actors: list[object] = []
        self.label_actors: list[object] = []
        self._key: object | None = None
        self.rebuild_count = 0
        self._closed = False

    @property
    def actors(self) -> list[object]:
        return [actor for actor in (self.lines_actor, *self.marker_actors, *self.label_actors) if actor is not None]

    @property
    def visible(self) -> bool:
        return self.lines_actor is not None and bool(self.lines_actor.GetVisibility())  # type: ignore[attr-defined]

    def update(self, measurements: Sequence[Measurement], pending: Point | None, units: str) -> bool:
        """Show the given measurements; True if anything was rebuilt."""

        if self._closed or self.renderer is None:
            return False
        key = (tuple((item.id, item.start, item.end) for item in measurements), pending, units)
        if key == self._key:
            return False
        self._key = key
        if not measurements and pending is None:
            for actor in self.actors:
                actor.SetVisibility(False)  # type: ignore[attr-defined]
            return True
        self._ensure_actors()
        assert self.lines_actor is not None
        self._set_lines(measurements)
        self._set_markers(measurements, pending)
        self._set_labels(measurements, units)
        self.lines_actor.SetVisibility(bool(measurements))  # type: ignore[attr-defined]
        self.rebuild_count += 1
        return True

    # -- VTK ----------------------------------------------------------------------------

    def _target(self) -> object:
        if self.layer_renderer is None:
            created = create_over_scene_layer(self.renderer)  # type: ignore[arg-type]
            if created is None:
                return self.renderer  # type: ignore[return-value]
            self.layer_renderer, self.overlay_layer = created
        return self.layer_renderer

    def _ensure_actors(self) -> None:
        if self.lines_actor is not None:
            return
        from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper

        target = self._target()

        actor = vtkActor()
        actor.SetMapper(vtkPolyDataMapper())
        actor.GetProperty().LightingOff()
        actor.GetProperty().SetColor(*LINE_COLOR)
        actor.GetProperty().SetLineWidth(LINE_WIDTH)
        actor.PickableOff()
        actor.DragableOff()
        actor.UseBoundsOff()
        target.AddActor(actor)  # type: ignore[attr-defined]
        self.lines_actor = actor

    def _set_lines(self, measurements: Sequence[Measurement]) -> None:
        from vtkmodules.vtkCommonCore import vtkPoints
        from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData

        points = vtkPoints()
        cells = vtkCellArray()
        for item in measurements:
            first = points.InsertNextPoint(*item.start)
            second = points.InsertNextPoint(*item.end)
            cells.InsertNextCell(2)
            cells.InsertCellPoint(first)
            cells.InsertCellPoint(second)
        data = vtkPolyData()
        data.SetPoints(points)
        data.SetLines(cells)
        self.lines_actor.GetMapper().SetInputData(data)  # type: ignore[union-attr, attr-defined]

    def _set_markers(self, measurements: Sequence[Measurement], pending: Point | None) -> None:
        from vtkmodules.vtkRenderingCore import vtkBillboardTextActor3D

        target = self._target()
        wanted: list[tuple[Point, tuple[float, float, float]]] = []
        for item in measurements:
            wanted.append((item.start, LINE_COLOR))
            wanted.append((item.end, LINE_COLOR))
        if pending is not None:
            wanted.append((pending, PENDING_COLOR))
        while len(self.marker_actors) < len(wanted):
            actor = vtkBillboardTextActor3D()
            actor.SetInput(MARKER_GLYPH)
            actor.PickableOff()
            actor.UseBoundsOff()
            prop = actor.GetTextProperty()
            prop.SetFontSize(MARKER_FONT_SIZE)
            prop.SetJustificationToCentered()
            prop.SetVerticalJustificationToCentered()
            target.AddActor(actor)  # type: ignore[attr-defined]
            self.marker_actors.append(actor)
        for index, marker in enumerate(self.marker_actors):
            if index < len(wanted):
                point, color = wanted[index]
                marker.SetPosition(*point)  # type: ignore[attr-defined]
                marker.GetTextProperty().SetColor(*color)  # type: ignore[attr-defined]
                marker.SetVisibility(True)  # type: ignore[attr-defined]
            else:
                marker.SetVisibility(False)  # type: ignore[attr-defined]

    def _set_labels(self, measurements: Sequence[Measurement], units: str) -> None:
        from vtkmodules.vtkRenderingCore import vtkBillboardTextActor3D

        target = self._target()
        while len(self.label_actors) < len(measurements):
            actor = vtkBillboardTextActor3D()
            actor.PickableOff()
            actor.UseBoundsOff()
            prop = actor.GetTextProperty()
            prop.SetFontSize(LABEL_FONT_SIZE)
            prop.SetColor(1.0, 1.0, 1.0)
            prop.SetBold(True)
            prop.SetBackgroundColor(0.05, 0.07, 0.09)
            prop.SetBackgroundOpacity(0.78)
            prop.SetFrame(False)
            prop.SetJustificationToCentered()
            prop.SetVerticalJustificationToBottom()
            actor.SetDisplayOffset(0, 10)
            target.AddActor(actor)  # type: ignore[attr-defined]
            self.label_actors.append(actor)
        for index, label in enumerate(self.label_actors):
            if index < len(measurements):
                item = measurements[index]
                middle = np.asarray(item.start, dtype=float) * 0.5 + np.asarray(item.end, dtype=float) * 0.5
                label.SetInput(label_text(item, units))  # type: ignore[attr-defined]
                label.SetPosition(float(middle[0]), float(middle[1]), float(middle[2]))  # type: ignore[attr-defined]
                label.SetVisibility(True)  # type: ignore[attr-defined]
            else:
                label.SetVisibility(False)  # type: ignore[attr-defined]

    def close(self) -> None:
        if self._closed:
            return
        owners = [self.layer_renderer, self.renderer]
        for actor in self.actors:
            actor.SetVisibility(False)  # type: ignore[attr-defined]
            for owner in owners:
                if owner is not None:
                    try:
                        owner.RemoveViewProp(actor)  # type: ignore[attr-defined]
                    except (AttributeError, RuntimeError, TypeError, ValueError):
                        pass
        if self.layer_renderer is not None and self.renderer is not None:
            window = self.renderer.GetRenderWindow()  # type: ignore[attr-defined]
            if window is not None:
                try:
                    window.RemoveRenderer(self.layer_renderer)
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    pass
        self.lines_actor = None
        self.marker_actors = []
        self.label_actors = []
        self.layer_renderer = None
        self.renderer = None
        self._closed = True


__all__ = ("MeasurementOverlay", "label_text")
