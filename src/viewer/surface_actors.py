"""VTK actor factory for triangulated surface items."""

from __future__ import annotations

from viewer.scene_types import SurfaceRenderItem
from viewer.vtk_actor_utils import polydata_actor, update_actor_polydata


def create_surface_actor(item: SurfaceRenderItem):
    return polydata_actor(item.vertices, item.faces, cell_kind="polys")


def update_surface_actor(actor: object, item: SurfaceRenderItem) -> None:
    update_actor_polydata(actor, item.vertices, item.faces, cell_kind="polys")


__all__ = ("create_surface_actor", "update_surface_actor")
