"""VTK actor factory for transient tool-preview polylines."""

from __future__ import annotations

from viewer.scene_types import ToolPreviewState
from viewer.vtk_actor_utils import polydata_actor, polyline_cells, update_actor_polydata


def create_tool_preview_actor(item: ToolPreviewState):
    return polydata_actor(
        item.fitted_points,
        polyline_cells(len(item.fitted_points), closed=item.closed),
        cell_kind="lines",
    )


def update_tool_preview_actor(actor: object, item: ToolPreviewState) -> None:
    update_actor_polydata(
        actor,
        item.fitted_points,
        polyline_cells(len(item.fitted_points), closed=item.closed),
        cell_kind="lines",
    )


__all__ = ("create_tool_preview_actor", "update_tool_preview_actor")
