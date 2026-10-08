"""Kernel jobs: the modelling operations as plain-data functions for the worker process.

Inputs and outputs are picklable (NumPy arrays, BREP bytes, numbers, strings, dicts), so a job
runs the same in the worker (``cad_kernel.worker``) or inline. A surface result carries its
BREP plus everything the application needs to show and pick it without OpenCASCADE: a display
mesh, sampled edges and the fit statistics.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from openretop.cad_kernel import surfacing as S

AUTO_MIN_INLIERS = 0.75
SURFACE_KINDS = ("auto", "freeform", "plane", "cylinder", "cone", "sphere", "torus")


# -- results ----------------------------------------------------------------------------------


def surface_result(shape: Any, **info: Any) -> dict[str, Any]:
    """BREP, display mesh and edges of a shape, plus ``info``."""

    size = S.shape_size(shape)
    mesh = S.shape_mesh(shape, deflection=max(size * 6e-4, 1e-3), angle=0.3)
    return {
        "brep": S.to_brep(shape),
        "vertices": mesh.vertices,
        "triangles": mesh.triangles,
        "face_index": mesh.face_index,
        "edges": shape_edges(shape),
        "area": S.face_area(shape),
        "size": size,
        **info,
    }


def shape_edges(shape: Any, samples: int = 48) -> list[np.ndarray]:
    """Each edge of the shape as a polyline (for display and for picking fill boundaries)."""

    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedMapOfShape

    edges = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_EDGE, edges)
    polylines = []
    for index in range(1, edges.Size() + 1):
        edge = TopoDS.Edge_s(edges.FindKey(index))
        try:
            curve = BRepAdaptor_Curve(edge)
        except Exception:  # a degenerated edge (a cone apex) has no curve
            polylines.append(np.zeros((0, 3)))
            continue
        first, last = curve.FirstParameter(), curve.LastParameter()
        if not (math.isfinite(first) and math.isfinite(last)) or last <= first:
            polylines.append(np.zeros((0, 3)))
            continue
        points = [curve.Value(t).Coord() for t in np.linspace(first, last, samples)]
        polylines.append(np.asarray(points, dtype=float))
    return polylines


def edge_of(shape: Any, number: int) -> tuple[Any, Any]:
    """Edge ``number`` (``shape_edges`` order) and a face it bounds."""

    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape, TopTools_IndexedMapOfShape

    edges = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_EDGE, edges)
    if not 0 <= number < edges.Size():
        raise ValueError(f"the surface has no edge {number}")
    edge = TopoDS.Edge_s(edges.FindKey(number + 1))
    owners = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, owners)
    faces = list(owners.FindFromKey(edge))
    return edge, (TopoDS.Face_s(faces[0]) if faces else None)


# -- jobs -------------------------------------------------------------------------------------


def fit_surface(
    points: np.ndarray,
    triangles: np.ndarray | None = None,
    normals: np.ndarray | None = None,
    *,
    kind: str = "auto",
    control_u: int = 0,
    control_v: int = 0,
    smoothness: float = 0.25,
    expand: float = 0.15,
    tolerance: float = 0.05,
) -> dict[str, Any]:
    """ExModel's Fit Surface on a selected scan area.

    ``kind`` "auto" takes the simplest exact primitive that fits within ``tolerance`` and
    falls back to freeform. ``control_u``/``control_v`` 0 means "auto net" for freeform.
    """

    from openretop.fitting import fit_primitive
    from openretop.fitting.bspline_surface import auto_fit_bspline_surface, fit_bspline_surface

    points = np.asarray(points, dtype=float).reshape(-1, 3)
    if kind not in SURFACE_KINDS:
        raise ValueError(f"unknown surface type: {kind}")
    if len(points) < 12:
        raise ValueError("select a larger area of the scan first")
    chosen = kind
    if kind == "auto":
        chosen = auto_surface_kind(points, normals, tolerance)
    if chosen == "freeform":
        if control_u > 0 and control_v > 0:
            fit = fit_bspline_surface(
                points, triangles, control_u=control_u, control_v=control_v, smoothness=smoothness, expand=expand
            )
        else:
            fit = auto_fit_bspline_surface(points, triangles, tolerance=tolerance, smoothness=smoothness, expand=expand)
        if not fit.success:
            raise ValueError(fit.reason or "the freeform fit failed")
        face = S.bspline_face(fit)
        distances = fit.distances(points)
        info = {
            "kind": "freeform",
            "control_u": fit.control_counts[0],
            "control_v": fit.control_counts[1],
            "parameterization": fit.parameterization,
            "params": {},
        }
    else:
        primitive = fit_primitive(chosen, points, normals)
        if not primitive.success:
            raise ValueError(primitive.reason or f"no {chosen} fits this area")
        face = S.primitive_patch(primitive, points, expand=expand)
        distances = np.abs(_primitive_distances(primitive, points))
        info = {"kind": chosen, "params": _plain_params(primitive.params)}
    return surface_result(
        face,
        rms=float(np.sqrt(np.mean(distances**2))),
        max_error=float(np.max(distances)),
        point_distances=distances.astype(np.float32),
        **info,
    )


def auto_surface_kind(points: np.ndarray, normals: np.ndarray | None, tolerance: float) -> str:
    """The simplest exact type that fits within ``tolerance`` (RMS of its inliers), else freeform.

    A hand-made selection often catches a few triangles of the neighbours, so a primitive
    explaining three quarters of it is enough (the fit drops the outliers). Very narrow faces
    (a 2 mm chamfer on a 0.8 mm scan) are mostly scanner-rounded edge and may come out as
    freeform: choose the type explicitly for those. (A median-based spread was tried and
    misread two chamfers as torus and freeform.)
    """

    from openretop.fitting import classify_region

    found, _fit, _tried = classify_region(points, normals, tolerance=tolerance, min_inliers=AUTO_MIN_INLIERS)
    return found if found in ("plane", "cylinder", "cone", "sphere", "torus") else "freeform"


def _primitive_distances(fit: Any, points: np.ndarray) -> np.ndarray:
    from openretop.fitting import primitive_distance

    return np.asarray(primitive_distance(fit, points), dtype=float)


def _plain_params(params: dict[str, Any]) -> dict[str, Any]:
    plain: dict[str, Any] = {}
    for key, value in params.items():
        array = np.asarray(value)
        plain[key] = float(array) if array.ndim == 0 else [float(v) for v in array.ravel()]
    return plain


def loft(curves: list[np.ndarray], *, ruled: bool = False) -> dict[str, Any]:
    return surface_result(S.loft_surface([np.asarray(curve, dtype=float) for curve in curves], ruled=ruled), kind="loft")


def fill(boundaries: list[dict[str, Any]], *, scan_points: np.ndarray | None = None) -> dict[str, Any]:
    """Each boundary: {"points": array} or {"brep": bytes, "edge": n}, plus "continuity"."""

    sides = []
    for boundary in boundaries:
        continuity = str(boundary.get("continuity", "contact"))
        if boundary.get("points") is not None:
            sides.append(S.FillBoundary(points=np.asarray(boundary["points"], dtype=float), continuity=continuity))
        else:
            edge, face = edge_of(S.from_brep(boundary["brep"]), int(boundary["edge"]))
            sides.append(S.FillBoundary(edge=edge, support_face=face, continuity=continuity))
    face = S.fill_surface(sides, scan_points=scan_points)
    return surface_result(face, kind="fill")


def extend(brep: bytes, distance: float, sides: tuple[str, ...] = ("u0", "u1", "v0", "v1")) -> dict[str, Any]:
    shape = S.from_brep(brep)
    faces = S.faces_of(shape)
    if len(faces) != 1:
        raise ValueError("Extend works on a single surface")
    return surface_result(S.extend_face(faces[0], float(distance), tuple(sides)), kind="extend")


def trim(
    breps: list[bytes],
    scan_vertices: np.ndarray,
    scan_normals: np.ndarray,
    *,
    tolerance: float = 0.1,
    overlap: float = 0.3,
) -> dict[str, Any]:
    """Split every surface by every other and mark the pieces lying on the scan.

    ``overlap`` is the share of a piece that must lie on the scan to be kept. A piece at an
    open border of the model keeps the oversize margin of its patch (nothing trims it), so
    the default is well below one half.
    """

    faces = []
    for brep in breps:
        faces.extend(S.faces_of(S.from_brep(brep)))
    if len(faces) < 2:
        raise ValueError("trimming needs at least two surfaces")
    pieces = S.split_faces(faces)
    S.mark_pieces_on_scan(pieces, scan_vertices, scan_normals, tolerance=tolerance, overlap=overlap)
    return {
        "pieces": [
            {**surface_result(piece.face), "source": piece.source, "overlap": piece.overlap, "keep": piece.keep}
            for piece in pieces
        ]
    }


def sew(breps: list[bytes], *, tolerance: float = 0.05) -> dict[str, Any]:
    faces = []
    for brep in breps:
        faces.extend(S.faces_of(S.from_brep(brep)))
    result = S.sew(faces, tolerance=tolerance)
    return surface_result(
        result.shape,
        kind="solid" if result.solid else "shell",
        solid=result.solid,
        closed=result.closed,
        free_edges=result.free_edges,
        volume=result.volume,
        warnings=list(result.warnings),
    )


def deviation(breps: list[bytes], points: np.ndarray) -> np.ndarray:
    """Signed distance from each point to the nearest of the shapes."""

    shapes = [S.from_brep(brep) for brep in breps]
    if not shapes:
        raise ValueError("nothing to compare against")
    return S.signed_distances(S.compound(shapes), points).astype(np.float32)


def export(breps: list[bytes], path: str, *, file_format: str = "step") -> dict[str, Any]:
    """Write the shapes to STEP or IGES and read the file back to check it."""

    shapes = [S.from_brep(brep) for brep in breps]
    if not shapes:
        raise ValueError("nothing to export")
    shape = shapes[0] if len(shapes) == 1 else S.compound(shapes)
    if file_format == "step":
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer

        writer = STEPControl_Writer()
        writer.Transfer(shape, STEPControl_AsIs)
        if writer.Write(path) != IFSelect_RetDone:
            raise ValueError(f"could not write {path}")
        reader = STEPControl_Reader()
        if reader.ReadFile(path) != IFSelect_RetDone:
            raise ValueError("the written STEP file could not be read back")
        reader.TransferRoots()
        back = reader.OneShape()
    elif file_format == "iges":
        from OCP.IGESControl import IGESControl_Reader, IGESControl_Writer

        writer = IGESControl_Writer("MM", 1)
        writer.AddShape(shape)
        writer.ComputeModel()
        if not writer.Write(path):
            raise ValueError(f"could not write {path}")
        reader = IGESControl_Reader()
        reader.ReadFile(path)
        reader.TransferRoots()
        back = reader.OneShape()
    else:
        raise ValueError(f"unknown export format: {file_format}")
    return {
        "faces": len(S.faces_of(shape)),
        "faces_back": len(S.faces_of(back)),
        "area": S.face_area(shape),
        "area_back": S.face_area(back),
        "volume": S.shape_volume(shape),
        "volume_back": S.shape_volume(back),
    }


def selftest_sleep(seconds: float) -> float:
    """For tests of the worker's timeout."""

    import time

    time.sleep(seconds)
    return seconds


def selftest_crash() -> None:  # pragma: no cover - kills the worker process
    """For tests of the worker's crash isolation: an abrupt process death."""

    import os

    os._exit(3)


JOBS = frozenset(
    {
        "fit_surface",
        "loft",
        "fill",
        "extend",
        "trim",
        "sew",
        "deviation",
        "export",
        "selftest_sleep",
        "selftest_crash",
    }
)

__all__ = ("JOBS", "SURFACE_KINDS", "edge_of", "shape_edges", "surface_result", *sorted(JOBS))
