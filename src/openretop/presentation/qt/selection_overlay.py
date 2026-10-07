"""Bounding box drawn around the selected scan, as the original app did."""

from __future__ import annotations

import numpy as np

from openretop.viewer.scene_types import Bounds3, SceneSnapshot

SELECTION_BOX_COLOR = (0.55, 0.72, 0.82)
SELECTION_BOX_LINE_WIDTH = 1.5
# Corner order matches _EDGES: bottom face counter-clockwise, then the top face.
_EDGES = (
    (0, 1), (1, 2), (2, 3), (3, 0),
    (4, 5), (5, 6), (6, 7), (7, 4),
    (0, 4), (1, 5), (2, 6), (3, 7),
)  # fmt: skip


def selected_mesh_bounds(snapshot: SceneSnapshot) -> Bounds3 | None:
    """World bounds of the selected scan (it follows the object while it is moved)."""

    chosen = snapshot.selection.selected_ids
    boxes: list[Bounds3] = []
    for item in snapshot.meshes:
        if item.visible and (item.selected or chosen.intersection(item.selection_keys)):
            bounds = item.world_bounds
            if bounds is not None:
                boxes.append(bounds)
    if not boxes:
        return None
    lows = np.min([np.asarray(box[0], dtype=float) for box in boxes], axis=0)
    highs = np.max([np.asarray(box[1], dtype=float) for box in boxes], axis=0)
    if not (np.all(np.isfinite(lows)) and np.all(np.isfinite(highs))):
        return None
    return (tuple(float(value) for value in lows), tuple(float(value) for value in highs))  # type: ignore[return-value]


def box_corners(bounds: Bounds3) -> list[tuple[float, float, float]]:
    (x0, y0, z0), (x1, y1, z1) = bounds
    return [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ]  # fmt: skip


class SelectionBoxOverlay:
    """One line actor, created on first use, updated in place and hidden when nothing is selected."""

    def __init__(self, renderer: object | None) -> None:
        self.renderer = renderer
        self.actor: object | None = None
        self._points: object | None = None
        self._data: object | None = None
        self.bounds: Bounds3 | None = None
        self.update_count = 0

    @property
    def visible(self) -> bool:
        return self.actor is not None and bool(self.actor.GetVisibility())  # type: ignore[attr-defined, union-attr]

    def update(self, snapshot: SceneSnapshot) -> bool:
        bounds = selected_mesh_bounds(snapshot)
        if bounds is None:
            if self.actor is not None:
                self.actor.SetVisibility(False)  # type: ignore[attr-defined, union-attr]
            self.bounds = None
            return False
        if self.renderer is None:
            return False
        if self.actor is None:
            self._create()
        assert self.actor is not None and self._points is not None and self._data is not None
        if bounds != self.bounds:
            for index, corner in enumerate(box_corners(bounds)):
                self._points.SetPoint(index, *corner)  # type: ignore[attr-defined, union-attr]
            self._points.Modified()  # type: ignore[attr-defined, union-attr]
            self._data.Modified()  # type: ignore[attr-defined, union-attr]
            self.bounds = bounds
            self.update_count += 1
        self.actor.SetVisibility(True)  # type: ignore[attr-defined, union-attr]
        return True

    def _create(self) -> None:
        from vtkmodules.vtkCommonCore import vtkPoints
        from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
        from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper

        points = vtkPoints()
        points.SetNumberOfPoints(8)
        for index in range(8):
            points.SetPoint(index, 0.0, 0.0, 0.0)
        lines = vtkCellArray()
        for first, second in _EDGES:
            lines.InsertNextCell(2)
            lines.InsertCellPoint(first)
            lines.InsertCellPoint(second)
        data = vtkPolyData()
        data.SetPoints(points)
        data.SetLines(lines)
        mapper = vtkPolyDataMapper()
        mapper.SetInputData(data)
        actor = vtkActor()
        actor.SetMapper(mapper)
        prop = actor.GetProperty()
        prop.SetColor(*SELECTION_BOX_COLOR)
        prop.SetLineWidth(SELECTION_BOX_LINE_WIDTH)
        prop.LightingOff()
        actor.PickableOff()
        actor.DragableOff()
        self.renderer.AddActor(actor)  # type: ignore[attr-defined, union-attr]
        self.actor, self._points, self._data = actor, points, data

    def close(self) -> None:
        if self.actor is not None and self.renderer is not None:
            try:
                self.renderer.RemoveActor(self.actor)  # type: ignore[attr-defined, union-attr]
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass
        self.actor = None
        self._points = None
        self._data = None
        self.renderer = None


__all__ = ("SELECTION_BOX_COLOR", "SelectionBoxOverlay", "box_corners", "selected_mesh_bounds")
