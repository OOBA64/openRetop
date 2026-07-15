"""VTK actor factory for curve and section-result items."""

from __future__ import annotations

import numpy as np

from viewer.scene_types import CurveRenderItem, SectionResultRenderItem
from viewer.vtk_actor_utils import polydata_actor, polyline_cells, update_actor_polydata


def create_curve_actor(item: CurveRenderItem):
    return polydata_actor(
        item.points,
        polyline_cells(len(item.points), closed=item.closed),
        cell_kind="lines",
    )


def update_curve_actor(actor: object, item: CurveRenderItem) -> None:
    update_actor_polydata(
        actor,
        item.points,
        polyline_cells(len(item.points), closed=item.closed),
        cell_kind="lines",
    )


def create_section_result_actor(item: SectionResultRenderItem):
    points, cells = _combined_polylines(item)
    return polydata_actor(points, cells, cell_kind="lines")


def update_section_result_actor(actor: object, item: SectionResultRenderItem) -> None:
    points, cells = _combined_polylines(item)
    update_actor_polydata(actor, points, cells, cell_kind="lines")


def _combined_polylines(item: SectionResultRenderItem):
    points: list[np.ndarray] = []
    cells: list[np.ndarray] = []
    offset = 0
    for line in item.polylines:
        points.append(line)
        line_cells = polyline_cells(len(line))
        if len(line_cells):
            cells.append(line_cells + offset)
        offset += len(line)
    return (
        np.vstack(points) if points else np.zeros((0, 3), dtype=float),
        np.vstack(cells) if cells else np.zeros((0, 2), dtype=int),
    )


__all__ = (
    "create_curve_actor",
    "create_section_result_actor",
    "update_curve_actor",
    "update_section_result_actor",
)
