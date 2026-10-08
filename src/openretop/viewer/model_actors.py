"""VTK actors for the model: surfaces and bodies, their edges, and overlays on the scan."""

from __future__ import annotations

import numpy as np

from openretop.viewer.curve_actors import _combined_polylines, on_surface_line
from openretop.viewer.mesh_actors import apply_mesh_material, shaded_polydata
from openretop.viewer.scene_types import ModelEdgesRenderItem, ModelFaceRenderItem, ScanOverlayRenderItem
from openretop.viewer.vtk_actor_utils import polydata, polydata_actor, update_actor_polydata, vtk_matrix

# Fitted surfaces lie on the scan within its noise: pull them in front of it in the depth test
# (between the scan overlays at (-1, -4) and curves at (-2, -8)).
MODEL_FACE_DEPTH_PULL = (-1.5, -6.0)
SCAN_OVERLAY_DEPTH_PULL = (-1.0, -4.0)
MODEL_EDGE_DEPTH_PULL = (-3.0, -12.0)


def create_model_face_actor(item: ModelFaceRenderItem):
    from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper

    mapper = vtkPolyDataMapper()
    mapper.SetInputData(shaded_polydata(item.vertices, item.triangles))
    mapper.ScalarVisibilityOff()
    mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(*MODEL_FACE_DEPTH_PULL)
    actor = vtkActor()
    actor.SetMapper(mapper)
    apply_mesh_material(actor)
    actor.GetProperty().BackfaceCullingOff()
    return actor


def update_model_face_actor(actor: object, item: ModelFaceRenderItem) -> None:
    actor.GetMapper().SetInputData(shaded_polydata(item.vertices, item.triangles))  # type: ignore[attr-defined]
    actor.GetMapper().Modified()  # type: ignore[attr-defined]


def create_model_edges_actor(item: ModelEdgesRenderItem):
    points, cells = _combined_polylines(item)  # type: ignore[arg-type]
    actor = on_surface_line(polydata_actor(points, cells, cell_kind="lines"))
    actor.GetMapper().SetRelativeCoincidentTopologyLineOffsetParameters(*MODEL_EDGE_DEPTH_PULL)
    return actor


def update_model_edges_actor(actor: object, item: ModelEdgesRenderItem) -> None:
    points, cells = _combined_polylines(item)  # type: ignore[arg-type]
    update_actor_polydata(actor, points, cells, cell_kind="lines")


def create_scan_overlay_actor(item: ScanOverlayRenderItem):
    from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper

    mapper = vtkPolyDataMapper()
    actor = vtkActor()
    actor.SetMapper(mapper)
    mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(*SCAN_OVERLAY_DEPTH_PULL)
    apply_mesh_material(actor)
    actor.PickableOff()  # picks go through to the scan under it
    update_scan_overlay_actor(actor, item)
    return actor


def update_scan_overlay_actor(actor: object, item: ScanOverlayRenderItem) -> None:
    mapper = actor.GetMapper()  # type: ignore[attr-defined]
    vertices = np.asarray(item.vertices, dtype=float).reshape(-1, 3)
    triangles = np.asarray(item.triangles, dtype=np.int64).reshape(-1, 3)
    colors = None if item.vertex_colors is None else np.asarray(item.vertex_colors, dtype=np.uint8).reshape(-1, 3)
    if item.triangle_mask is not None:
        mask = np.asarray(item.triangle_mask, dtype=bool)
        triangles = triangles[mask[: len(triangles)]] if len(mask) >= len(triangles) else triangles[:0]
        used, inverse = np.unique(triangles.ravel(), return_inverse=True)
        vertices = vertices[used]
        triangles = inverse.reshape(-1, 3)
        if colors is not None:
            colors = colors[used]
    data = shaded_polydata(vertices, triangles) if colors is None else polydata(vertices, triangles, cell_kind="polys")
    if colors is not None and len(colors) == len(vertices):
        from vtkmodules.util.numpy_support import numpy_to_vtk

        array = numpy_to_vtk(np.ascontiguousarray(colors), deep=True)
        array.SetName("deviation")
        data.GetPointData().SetScalars(array)  # type: ignore[attr-defined]
        mapper.ScalarVisibilityOn()
        mapper.SetColorModeToDirectScalars()
        mapper.SetScalarModeToUsePointData()
    else:
        mapper.ScalarVisibilityOff()
    mapper.SetInputData(data)
    mapper.Modified()
    actor.SetUserMatrix(vtk_matrix(item.transform))  # type: ignore[attr-defined]


__all__ = (
    "MODEL_EDGE_DEPTH_PULL",
    "MODEL_FACE_DEPTH_PULL",
    "SCAN_OVERLAY_DEPTH_PULL",
    "create_model_edges_actor",
    "create_model_face_actor",
    "create_scan_overlay_actor",
    "update_model_edges_actor",
    "update_model_face_actor",
    "update_scan_overlay_actor",
)
