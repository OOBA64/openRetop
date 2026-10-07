"""VTK actor factory for mesh scene items."""

from __future__ import annotations

from openretop.viewer.scene_types import MeshRenderItem
from openretop.viewer.vtk_actor_utils import polydata, vtk_matrix

# Edges sharper than this keep a crisp crease; gentler ones are shaded smoothly, so a scan
# looks like a surface instead of a field of facets while a machined edge stays sharp.
CREASE_ANGLE_DEGREES = 40.0


def create_mesh_actor(item: MeshRenderItem):
    from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper

    mapper = vtkPolyDataMapper()
    mapper.SetInputData(shaded_polydata(item.mesh.vertices, item.mesh.triangles))
    mapper.ScalarVisibilityOff()
    actor = vtkActor()
    actor.SetMapper(mapper)
    apply_mesh_material(actor)
    actor.SetUserMatrix(vtk_matrix(item.transform))
    return actor


def update_mesh_actor(actor: object, item: MeshRenderItem) -> None:
    actor.GetMapper().SetInputData(shaded_polydata(item.mesh.vertices, item.mesh.triangles))  # type: ignore[attr-defined]
    actor.GetMapper().Modified()  # type: ignore[attr-defined]
    actor.SetUserMatrix(vtk_matrix(item.transform))  # type: ignore[attr-defined]


def shaded_polydata(vertices: object, triangles: object) -> object:
    """Triangles with point normals for smooth shading, split at creases.

    Splitting duplicates points along sharp edges but keeps every triangle in its original
    order, so a picked cell id is still the index of the source triangle.
    """

    from vtkmodules.vtkCommonDataModel import vtkPolyData
    from vtkmodules.vtkFiltersCore import vtkPolyDataNormals

    raw = polydata(vertices, triangles, cell_kind="polys")
    if raw.GetNumberOfPolys() == 0:
        return raw
    normals = vtkPolyDataNormals()
    normals.SetInputData(raw)
    normals.ComputePointNormalsOn()
    normals.ComputeCellNormalsOff()
    normals.SplittingOn()
    normals.SetFeatureAngle(CREASE_ANGLE_DEGREES)
    normals.ConsistencyOff()  # keep each triangle's vertex order as imported
    normals.AutoOrientNormalsOff()
    normals.NonManifoldTraversalOff()
    normals.Update()
    output = vtkPolyData()
    output.ShallowCopy(normals.GetOutput())
    return output


def apply_mesh_material(actor: object) -> None:
    """A soft satin finish: enough specular to read the shape, not enough to look like plastic."""

    prop = actor.GetProperty()  # type: ignore[attr-defined]
    prop.SetInterpolationToPhong()
    prop.SetAmbient(0.10)
    prop.SetDiffuse(0.85)
    prop.SetSpecular(0.22)
    prop.SetSpecularPower(28.0)
    prop.SetSpecularColor(1.0, 1.0, 1.0)


__all__ = ("CREASE_ANGLE_DEGREES", "apply_mesh_material", "create_mesh_actor", "shaded_polydata", "update_mesh_actor")
