"""Display mesh proxy creation for dense source meshes."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from mesh.triangle_mesh import TriangleMeshData


LOW_DENSITY_TRIANGLE_LIMIT = 150_000
MEDIUM_DENSITY_TRIANGLE_LIMIT = 500_000
PROXY_QUALITY_LOW = "Low"
PROXY_QUALITY_MEDIUM = "Medium"
PROXY_QUALITY_HIGH = "High"
PROXY_QUALITY_LABELS = (
    PROXY_QUALITY_LOW,
    PROXY_QUALITY_MEDIUM,
    PROXY_QUALITY_HIGH,
)
DEFAULT_PROXY_QUALITY = PROXY_QUALITY_MEDIUM

_MEDIUM_DENSITY_TARGETS = {
    PROXY_QUALITY_LOW: 150_000,
    PROXY_QUALITY_MEDIUM: 180_000,
    PROXY_QUALITY_HIGH: 240_000,
}
_HIGH_DENSITY_TARGETS = {
    PROXY_QUALITY_LOW: 150_000,
    PROXY_QUALITY_MEDIUM: 220_000,
    PROXY_QUALITY_HIGH: 300_000,
}


@dataclass(frozen=True)
class DisplayMeshResult:
    source_mesh: TriangleMeshData
    display_mesh: TriangleMeshData
    source_triangle_count: int
    display_triangle_count: int
    proxy_enabled: bool
    reduction_percent: float
    quality: str


def build_display_mesh(
    source_mesh: TriangleMeshData,
    *,
    quality: str = DEFAULT_PROXY_QUALITY,
) -> DisplayMeshResult:
    """Return an interaction/display mesh while preserving the source mesh."""

    quality = normalize_proxy_quality(quality)
    source_triangle_count = len(source_mesh.triangles)
    target_triangle_count = _target_triangle_count(source_triangle_count, quality)
    if target_triangle_count >= source_triangle_count:
        display_mesh = source_mesh.copy()
        proxy_enabled = False
    else:
        display_mesh = _decimated_display_mesh(source_mesh, target_triangle_count)
        proxy_enabled = True

    _ensure_display_normals(display_mesh)
    display_triangle_count = len(display_mesh.triangles)
    return DisplayMeshResult(
        source_mesh=source_mesh,
        display_mesh=display_mesh,
        source_triangle_count=source_triangle_count,
        display_triangle_count=display_triangle_count,
        proxy_enabled=proxy_enabled,
        reduction_percent=_reduction_percent(source_triangle_count, display_triangle_count),
        quality=quality,
    )


def normalize_proxy_quality(quality: str) -> str:
    if quality in PROXY_QUALITY_LABELS:
        return quality
    return DEFAULT_PROXY_QUALITY


def _target_triangle_count(source_triangle_count: int, quality: str) -> int:
    if source_triangle_count <= LOW_DENSITY_TRIANGLE_LIMIT:
        return source_triangle_count

    quality = normalize_proxy_quality(quality)
    if source_triangle_count <= MEDIUM_DENSITY_TRIANGLE_LIMIT:
        return min(_MEDIUM_DENSITY_TARGETS[quality], source_triangle_count)
    return min(_HIGH_DENSITY_TARGETS[quality], source_triangle_count)


def _decimated_display_mesh(
    source_mesh: TriangleMeshData,
    target_triangle_count: int,
) -> TriangleMeshData:
    try:
        mesh = _decimated_display_mesh_with_vtk(source_mesh, target_triangle_count)
    except (AttributeError, ImportError, RuntimeError, ValueError):
        mesh = _sample_display_mesh(source_mesh, target_triangle_count)

    if len(mesh.triangles) == 0:
        return _sample_display_mesh(source_mesh, target_triangle_count)
    return mesh


def _decimated_display_mesh_with_vtk(
    source_mesh: TriangleMeshData,
    target_triangle_count: int,
) -> TriangleMeshData:
    from vtkmodules.util.numpy_support import (
        numpy_to_vtk,
        numpy_to_vtkIdTypeArray,
        vtk_to_numpy,
    )
    from vtkmodules.vtkCommonCore import vtkPoints
    from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
    from vtkmodules.vtkFiltersCore import (
        vtkDecimatePro,
        vtkStaticCleanPolyData,
    )

    triangles = np.asarray(source_mesh.triangles, dtype=np.int64)
    vertices = np.asarray(source_mesh.vertices, dtype=float)
    if target_triangle_count <= 0 or len(triangles) == 0 or len(vertices) == 0:
        return TriangleMeshData(
            vertices=np.zeros((0, 3), dtype=float),
            triangles=np.zeros((0, 3), dtype=int),
        )

    polydata = vtkPolyData()
    points = vtkPoints()
    points.SetData(numpy_to_vtk(vertices, deep=True))
    polydata.SetPoints(points)

    offsets = np.arange(0, (len(triangles) * 3) + 1, 3, dtype=np.int64)
    cells = vtkCellArray()
    cells.SetData(
        numpy_to_vtkIdTypeArray(offsets, deep=True),
        numpy_to_vtkIdTypeArray(triangles.ravel(), deep=True),
    )
    polydata.SetPolys(cells)
    clean_input = vtkStaticCleanPolyData()
    clean_input.SetInputData(polydata)
    clean_input.Update()
    decimation_input = clean_input.GetOutput()

    reduction = 1.0 - (float(target_triangle_count) / float(len(triangles)))
    if len(triangles) > MEDIUM_DENSITY_TRIANGLE_LIMIT:
        output = _quadric_decimated_output(decimation_input, reduction)
    else:
        decimator = vtkDecimatePro()
        decimator.SetInputData(decimation_input)
        decimator.SetTargetReduction(float(np.clip(reduction, 0.0, 0.95)))
        decimator.PreserveTopologyOn()
        decimator.BoundaryVertexDeletionOff()
        decimator.SplittingOff()
        decimator.PreSplitMeshOff()
        decimator.SetFeatureAngle(30.0)

        output = _normal_output_from_vtk_port(decimator.GetOutputPort())
        if output.GetNumberOfPolys() > max(
            int(target_triangle_count * 1.25),
            target_triangle_count + 1,
        ):
            output = _quadric_decimated_output(decimation_input, reduction)

    if output is None or output.GetNumberOfPoints() == 0 or output.GetNumberOfPolys() == 0:
        raise RuntimeError("VTK decimation produced an empty mesh.")

    output_points = output.GetPoints()
    if output_points is None:
        raise RuntimeError("VTK decimation produced no points.")

    decimated_vertices = vtk_to_numpy(output_points.GetData()).astype(float, copy=True)
    decimated_triangles = _vtk_polys_to_numpy(output).astype(int, copy=False)
    decimated_vertices, decimated_triangles = _remove_degenerate_faces(
        decimated_vertices,
        decimated_triangles,
    )
    if len(decimated_triangles) == 0:
        raise RuntimeError("VTK decimation produced only degenerate faces.")

    mesh = TriangleMeshData(vertices=decimated_vertices, triangles=decimated_triangles)
    _ensure_display_normals(mesh)
    return mesh


def _quadric_decimated_output(polydata: object, reduction: float) -> object:
    from vtkmodules.vtkCommonCore import vtkObject
    from vtkmodules.vtkFiltersCore import vtkQuadricDecimation

    quadric = vtkQuadricDecimation()
    quadric.SetInputData(polydata)
    quadric.SetTargetReduction(float(np.clip(reduction, 0.0, 0.95)))
    quadric.VolumePreservationOn()
    previous_warning_state = vtkObject.GetGlobalWarningDisplay()
    vtkObject.GlobalWarningDisplayOff()
    try:
        return _normal_output_from_vtk_port(quadric.GetOutputPort())
    finally:
        if previous_warning_state:
            vtkObject.GlobalWarningDisplayOn()
        else:
            vtkObject.GlobalWarningDisplayOff()


def _normal_output_from_vtk_port(output_port: object) -> object:
    from vtkmodules.vtkCommonDataModel import vtkPolyData
    from vtkmodules.vtkFiltersCore import vtkCleanPolyData, vtkPolyDataNormals

    cleaner = vtkCleanPolyData()
    cleaner.SetInputConnection(output_port)
    cleaner.PointMergingOn()

    normals = vtkPolyDataNormals()
    normals.SetInputConnection(cleaner.GetOutputPort())
    normals.ComputePointNormalsOn()
    normals.ComputeCellNormalsOn()
    normals.ConsistencyOn()
    normals.SplittingOff()
    normals.Update()
    output = vtkPolyData()
    output.DeepCopy(normals.GetOutput())
    return output


def _vtk_polys_to_numpy(polydata: object) -> np.ndarray:
    from vtkmodules.util.numpy_support import vtk_to_numpy

    polys = polydata.GetPolys()
    offsets_array = polys.GetOffsetsArray()
    connectivity_array = polys.GetConnectivityArray()
    if offsets_array is not None and connectivity_array is not None:
        offsets = vtk_to_numpy(offsets_array).astype(np.int64, copy=False)
        connectivity = vtk_to_numpy(connectivity_array).astype(np.int64, copy=False)
        if len(offsets) < 2:
            return np.zeros((0, 3), dtype=int)

        faces: list[np.ndarray] = []
        for start, end in zip(offsets[:-1], offsets[1:]):
            face = connectivity[int(start) : int(end)]
            if len(face) == 3:
                faces.append(face)
        if not faces:
            return np.zeros((0, 3), dtype=int)
        return np.asarray(faces, dtype=int)

    packed = vtk_to_numpy(polys.GetData()).astype(np.int64, copy=False)
    faces = []
    index = 0
    while index < len(packed):
        face_size = int(packed[index])
        face = packed[index + 1 : index + 1 + face_size]
        if face_size == 3:
            faces.append(face)
        index += face_size + 1

    if not faces:
        return np.zeros((0, 3), dtype=int)
    return np.asarray(faces, dtype=int)


def _sample_display_mesh(
    source_mesh: TriangleMeshData,
    target_triangle_count: int,
) -> TriangleMeshData:
    triangles = np.asarray(source_mesh.triangles, dtype=int)
    if target_triangle_count <= 0 or len(triangles) == 0:
        return TriangleMeshData(
            vertices=np.zeros((0, 3), dtype=float),
            triangles=np.zeros((0, 3), dtype=int),
        )

    face_indices = np.linspace(
        0,
        len(triangles) - 1,
        num=min(int(target_triangle_count), len(triangles)),
        dtype=int,
    )
    face_indices = np.unique(face_indices)
    sampled_faces = triangles[face_indices]
    used_vertices, remapped_faces = np.unique(sampled_faces.ravel(), return_inverse=True)
    remapped_faces = remapped_faces.reshape((-1, 3))
    vertices = np.asarray(source_mesh.vertices, dtype=float)[used_vertices]

    vertex_normals = None
    if source_mesh.has_vertex_normals():
        vertex_normals = np.asarray(source_mesh.vertex_normals, dtype=float)[used_vertices]

    triangle_normals = None
    if source_mesh.has_triangle_normals():
        triangle_normals = np.asarray(source_mesh.triangle_normals, dtype=float)[face_indices]

    return TriangleMeshData(
        vertices=vertices,
        triangles=remapped_faces,
        vertex_normals=vertex_normals,
        triangle_normals=triangle_normals,
    )


def _remove_degenerate_faces(
    vertices: np.ndarray,
    triangles: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    if len(triangles) == 0:
        return vertices, triangles.reshape((0, 3))

    triangles = np.asarray(triangles, dtype=int).reshape((-1, 3))
    valid_indices = (
        (triangles[:, 0] != triangles[:, 1])
        & (triangles[:, 1] != triangles[:, 2])
        & (triangles[:, 0] != triangles[:, 2])
    )
    triangles = triangles[valid_indices]
    if len(triangles) == 0:
        return vertices[:0].copy(), triangles.reshape((0, 3))

    face_vertices = vertices[triangles]
    face_normals = np.cross(
        face_vertices[:, 1] - face_vertices[:, 0],
        face_vertices[:, 2] - face_vertices[:, 0],
    )
    valid_area = np.linalg.norm(face_normals, axis=1) > 1e-12
    triangles = triangles[valid_area]
    if len(triangles) == 0:
        return vertices[:0].copy(), triangles.reshape((0, 3))

    used_vertices, remapped = np.unique(triangles.ravel(), return_inverse=True)
    return vertices[used_vertices].copy(), remapped.reshape((-1, 3)).astype(int, copy=False)


def _ensure_display_normals(mesh: object) -> None:
    if not isinstance(mesh, TriangleMeshData):
        if hasattr(mesh, "compute_triangle_normals"):
            mesh.compute_triangle_normals()
        if hasattr(mesh, "compute_vertex_normals"):
            mesh.compute_vertex_normals()
        return

    if len(mesh.triangles) == 0:
        mesh.triangle_normals = np.zeros((0, 3), dtype=float)
        mesh.vertex_normals = np.zeros_like(mesh.vertices, dtype=float)
        return

    triangle_points = mesh.vertices[mesh.triangles]
    triangle_normals = np.cross(
        triangle_points[:, 1] - triangle_points[:, 0],
        triangle_points[:, 2] - triangle_points[:, 0],
    )
    lengths = np.linalg.norm(triangle_normals, axis=1)
    valid = lengths > 1e-12
    triangle_normals[valid] /= lengths[valid, None]
    triangle_normals[~valid] = 0.0

    vertex_normals = np.zeros_like(mesh.vertices, dtype=float)
    repeated_normals = np.repeat(triangle_normals, 3, axis=0)
    np.add.at(vertex_normals, mesh.triangles.ravel(), repeated_normals)
    vertex_lengths = np.linalg.norm(vertex_normals, axis=1)
    valid_vertices = vertex_lengths > 1e-12
    vertex_normals[valid_vertices] /= vertex_lengths[valid_vertices, None]
    vertex_normals[~valid_vertices] = 0.0

    mesh.triangle_normals = triangle_normals
    mesh.vertex_normals = vertex_normals


def _reduction_percent(source_triangle_count: int, display_triangle_count: int) -> float:
    if source_triangle_count <= 0:
        return 0.0
    reduction = 1.0 - (float(display_triangle_count) / float(source_triangle_count))
    return max(reduction, 0.0) * 100.0
