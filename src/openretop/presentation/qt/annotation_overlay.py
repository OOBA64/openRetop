"""Lines and text labels drawn over the scene: the 3D Sketch's curves, plane and the scan's
cut, with its dimension values and constraint marks (H, V, = ...).

Over the scene, not in it: a sketch plane usually runs through the middle of the scan, whose
surface would hide the sketch (Fusion draws sketches on top too)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from openretop.presentation.qt.overlay_layers import create_over_scene_layer

DIMENSION_COLOR = (1.0, 1.0, 1.0)
REFERENCE_COLOR = (0.70, 0.72, 0.76)  # a driven (reference) dimension
GLYPH_COLOR = (0.55, 0.85, 1.0)
DIMENSION_FONT_SIZE = 14
GLYPH_FONT_SIZE = 11


@dataclass(frozen=True)
class Annotation:
    position: tuple[float, float, float]
    text: str
    kind: str = "dimension"  # "dimension", "reference" or "glyph"


class AnnotationOverlay:
    """Billboard text actors, reused between updates; rebuilt only when the labels change."""

    def __init__(self, renderer: object | None) -> None:
        self.renderer = renderer
        self.layer_renderer: object | None = None
        self.actors: list[object] = []
        self.line_actors: list[object] = []
        self._key: object | None = None
        self._lines_key: object | None = None
        self._closed = False

    @property
    def visible_count(self) -> int:
        return sum(1 for actor in self.actors if actor.GetVisibility())  # type: ignore[attr-defined, misc]

    def update_lines(self, lines: Sequence[tuple[object, tuple[float, float, float], float]]) -> bool:
        """Polylines (world points, colour, width), one actor per colour and width."""

        if self._closed or self.renderer is None:
            return False
        key = tuple((id(points), tuple(color), float(width)) for points, color, width in lines)
        if key == self._lines_key:
            return False
        self._lines_key = key
        import numpy as np
        from vtkmodules.vtkCommonCore import vtkPoints
        from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
        from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper

        groups: dict[tuple[tuple[float, float, float], float], list[object]] = {}
        for points, color, width in lines:
            groups.setdefault((tuple(color), float(width)), []).append(points)  # type: ignore[arg-type]
        target = self._target()
        while len(self.line_actors) < len(groups):
            actor: object = vtkActor()
            actor.SetMapper(vtkPolyDataMapper())  # type: ignore[attr-defined]
            actor.GetProperty().LightingOff()  # type: ignore[attr-defined]
            actor.PickableOff()  # type: ignore[attr-defined]
            actor.DragableOff()  # type: ignore[attr-defined]
            actor.UseBoundsOff()  # type: ignore[attr-defined]
            target.AddActor(actor)  # type: ignore[attr-defined]
            self.line_actors.append(actor)
        items = list(groups.items())
        for index, actor in enumerate(self.line_actors):
            if index >= len(items):
                actor.SetVisibility(False)  # type: ignore[attr-defined]
                continue
            (color, width), polylines = items[index]
            points = vtkPoints()
            cells = vtkCellArray()
            for polyline in polylines:
                values = np.asarray(polyline, dtype=float).reshape(-1, 3)
                if len(values) < 2:
                    continue
                cells.InsertNextCell(len(values))
                for value in values:
                    cells.InsertCellPoint(points.InsertNextPoint(*value.tolist()))
            data = vtkPolyData()
            data.SetPoints(points)
            data.SetLines(cells)
            actor.GetMapper().SetInputData(data)  # type: ignore[attr-defined]
            actor.GetProperty().SetColor(*color)  # type: ignore[attr-defined]
            actor.GetProperty().SetLineWidth(width)  # type: ignore[attr-defined]
            actor.SetVisibility(True)  # type: ignore[attr-defined]
        return True

    def update(self, annotations: Sequence[Annotation]) -> bool:
        if self._closed or self.renderer is None:
            return False
        key = tuple(annotations)
        if key == self._key:
            return False
        self._key = key
        from vtkmodules.vtkRenderingCore import vtkBillboardTextActor3D

        target = self._target()
        while len(self.actors) < len(annotations):
            actor: object = vtkBillboardTextActor3D()
            actor.PickableOff()  # type: ignore[attr-defined]
            actor.UseBoundsOff()  # type: ignore[attr-defined]
            prop = actor.GetTextProperty()  # type: ignore[attr-defined]
            prop.SetJustificationToCentered()
            prop.SetVerticalJustificationToCentered()
            prop.SetBackgroundColor(0.05, 0.07, 0.09)
            prop.SetFrame(False)
            target.AddActor(actor)  # type: ignore[attr-defined]
            self.actors.append(actor)
        for index, actor in enumerate(self.actors):
            if index >= len(annotations):
                actor.SetVisibility(False)  # type: ignore[attr-defined]
                continue
            item = annotations[index]
            prop = actor.GetTextProperty()  # type: ignore[attr-defined]
            glyph = item.kind == "glyph"
            prop.SetFontSize(GLYPH_FONT_SIZE if glyph else DIMENSION_FONT_SIZE)
            prop.SetBold(not glyph)
            prop.SetColor(*(GLYPH_COLOR if glyph else REFERENCE_COLOR if item.kind == "reference" else DIMENSION_COLOR))
            prop.SetBackgroundOpacity(0.55 if glyph else 0.8)
            actor.SetDisplayOffset(0, 12 if glyph else -14)  # type: ignore[attr-defined]  # marks above their geometry, values below
            actor.SetInput(item.text)  # type: ignore[attr-defined]
            actor.SetPosition(*item.position)  # type: ignore[attr-defined]
            actor.SetVisibility(True)  # type: ignore[attr-defined]
        return True

    def _target(self) -> object:
        if self.layer_renderer is None:
            created = create_over_scene_layer(self.renderer)  # type: ignore[arg-type]
            if created is None:
                return self.renderer  # type: ignore[return-value]
            self.layer_renderer, _layer = created
        return self.layer_renderer

    def close(self) -> None:
        if self._closed:
            return
        for actor in [*self.actors, *self.line_actors]:
            actor.SetVisibility(False)  # type: ignore[attr-defined]
            for owner in (self.layer_renderer, self.renderer):
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
        self.actors = []
        self.line_actors = []
        self._closed = True


__all__ = ("Annotation", "AnnotationOverlay")
