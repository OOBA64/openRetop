"""VTK actor factory for mesh scene items."""

from __future__ import annotations

from viewer.scene_types import MeshRenderItem
from viewer.vtk_actor_utils import polydata_actor, update_actor_polydata, vtk_matrix


def create_mesh_actor(item: MeshRenderItem):
    actor = polydata_actor(item.mesh.vertices, item.mesh.triangles, cell_kind="polys")
    actor.SetUserMatrix(vtk_matrix(item.transform))
    return actor


def update_mesh_actor(actor: object, item: MeshRenderItem) -> None:
    update_actor_polydata(
        actor, item.mesh.vertices, item.mesh.triangles, cell_kind="polys"
    )
    actor.SetUserMatrix(vtk_matrix(item.transform))


__all__ = ("create_mesh_actor", "update_mesh_actor")
