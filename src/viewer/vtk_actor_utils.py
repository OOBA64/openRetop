"""Low-level public-VTK geometry conversion used by focused actor factories."""

from __future__ import annotations

import numpy as np

from vtkmodules.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper


def polydata_actor(points: object, cells: object, *, cell_kind: str) -> vtkActor:
    actor = vtkActor()
    mapper = vtkPolyDataMapper()
    mapper.SetInputData(polydata(points, cells, cell_kind=cell_kind))
    mapper.ScalarVisibilityOff()
    actor.SetMapper(mapper)
    return actor


def update_actor_polydata(actor: object, points: object, cells: object, *, cell_kind: str) -> None:
    actor.GetMapper().SetInputData(polydata(points, cells, cell_kind=cell_kind))
    actor.GetMapper().Modified()


def polydata(points: object, cells: object, *, cell_kind: str) -> vtkPolyData:
    point_array = np.asarray(points, dtype=float).reshape((-1, 3))
    width = 3 if cell_kind == "polys" else 2
    cell_array = np.asarray(cells, dtype=np.int64).reshape((-1, width))
    result = vtkPolyData()
    vtk_points = numpy_to_vtk(point_array, deep=True)
    from vtkmodules.vtkCommonCore import vtkPoints

    points_object = vtkPoints()
    points_object.SetData(vtk_points)
    result.SetPoints(points_object)
    vtk_cells = vtkCellArray()
    if len(cell_array):
        offsets = np.arange(
            0,
            (len(cell_array) + 1) * width,
            width,
            dtype=np.int64,
        )
        vtk_cells.SetData(
            numpy_to_vtkIdTypeArray(offsets, deep=True),
            numpy_to_vtkIdTypeArray(cell_array.ravel(), deep=True),
        )
    if cell_kind == "polys":
        result.SetPolys(vtk_cells)
    else:
        result.SetLines(vtk_cells)
    return result


def polyline_cells(point_count: int, *, closed: bool = False) -> np.ndarray:
    cells = [[index, index + 1] for index in range(max(point_count - 1, 0))]
    if closed and point_count >= 3:
        cells.append([point_count - 1, 0])
    return np.asarray(cells, dtype=np.int64).reshape((-1, 2))


def vtk_matrix(matrix: object):
    from vtkmodules.vtkCommonMath import vtkMatrix4x4

    values = np.asarray(matrix, dtype=float).reshape((4, 4))
    result = vtkMatrix4x4()
    for row in range(4):
        for column in range(4):
            result.SetElement(row, column, float(values[row, column]))
    return result


__all__ = (
    "polydata",
    "polydata_actor",
    "polyline_cells",
    "update_actor_polydata",
    "vtk_matrix",
)
