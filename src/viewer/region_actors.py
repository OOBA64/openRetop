"""VTK actor factory for selected mesh regions."""

from __future__ import annotations

import numpy as np

from viewer.scene_types import RegionRenderItem
from viewer.vtk_actor_utils import polydata_actor, update_actor_polydata, vtk_matrix


def create_region_actor(item: RegionRenderItem):
    points, faces = _region_geometry(item)
    actor = polydata_actor(points, faces, cell_kind="polys")
    actor.SetUserMatrix(vtk_matrix(item.transform))
    return actor


def update_region_actor(actor: object, item: RegionRenderItem) -> None:
    points, faces = _region_geometry(item)
    update_actor_polydata(actor, points, faces, cell_kind="polys")
    actor.SetUserMatrix(vtk_matrix(item.transform))


def _region_geometry(item: RegionRenderItem):
    vertices = np.asarray(item.mesh.vertices, dtype=float).reshape((-1, 3))
    triangles = np.asarray(item.mesh.triangles, dtype=int).reshape((-1, 3))
    indices = [value for value in item.triangle_indices if 0 <= value < len(triangles)]
    if not indices:
        return vertices[:0], np.zeros((0, 3), dtype=int)
    selected = triangles[np.asarray(indices, dtype=int)]
    unique, inverse = np.unique(selected.ravel(), return_inverse=True)
    return vertices[unique], inverse.reshape((-1, 3))


__all__ = ("create_region_actor", "update_region_actor")
