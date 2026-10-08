"""Surface modelling operations on OpenCASCADE shapes (the ExModel / QuickSurface toolset).

Fit Surface, Loft, Fill, Extend, Trim (split everything by everything, keep the pieces that
lie on the scan) and Sew (into a shell, or a solid when it closes). Also tessellation for
display and scan-to-shape deviation.

Every function takes and returns plain data (NumPy arrays, BREP bytes via ``to_brep`` /
``from_brep``) or OCC shapes, so the risky ones can run in the kernel worker process
(``cad_kernel.worker``) where a kernel crash cannot take the application down.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from openretop.fitting import PrimitiveFit
from openretop.fitting.bspline_surface import BSplineSurfaceFit

# -- conversion -------------------------------------------------------------------------------


def to_brep(shape: Any) -> bytes:
    import cadquery as cq

    stream = io.BytesIO()
    cq.Shape.cast(shape).exportBrep(stream)
    return stream.getvalue()


def from_brep(data: bytes) -> object:
    import cadquery as cq

    return cq.Shape.importBrep(io.BytesIO(data)).wrapped


def bspline_face(fit: BSplineSurfaceFit) -> object:
    """An untrimmed OCC face of the fitted B-spline surface."""

    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.Geom import Geom_BSplineSurface
    from OCP.gp import gp_Pnt
    from OCP.TColgp import TColgp_Array2OfPnt
    from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal

    nu, nv = fit.control_counts
    poles = TColgp_Array2OfPnt(1, nu, 1, nv)
    for i in range(nu):
        for j in range(nv):
            x, y, z = (float(value) for value in fit.poles[i, j])
            poles.SetValue(i + 1, j + 1, gp_Pnt(x, y, z))

    def knots(vector: np.ndarray) -> tuple[object, object]:
        distinct, counts = np.unique(np.round(vector, 12), return_counts=True)
        values = TColStd_Array1OfReal(1, len(distinct))
        multiplicities = TColStd_Array1OfInteger(1, len(distinct))
        for index, (value, count) in enumerate(zip(distinct, counts, strict=True), start=1):
            values.SetValue(index, float(value))
            multiplicities.SetValue(index, int(count))
        return values, multiplicities

    u_knots, u_mults = knots(fit.knots_u)
    v_knots, v_mults = knots(fit.knots_v)
    surface = Geom_BSplineSurface(poles, u_knots, v_knots, u_mults, v_mults, fit.degree_u, fit.degree_v)
    return BRepBuilderAPI_MakeFace(surface, 1e-6).Face()


def trimmed_bspline_face(fit: BSplineSurfaceFit, boundaries: list[np.ndarray]) -> object:
    """The fitted surface cut to a closed chain of curves drawn on the scan.

    Each curve is mapped onto the surface (foot-point parameters) and becomes an edge lying
    on it; consecutive edges share their corner vertex, so the wire closes exactly. The
    curves are on the scan and the surface fits the scan, so they differ by about the scan
    noise: two patches built on a shared curve meet within it and sew together.
    """

    from OCP.BRep import BRep_Tool
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakeEdge,
        BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_MakeVertex,
        BRepBuilderAPI_MakeWire,
    )
    from OCP.BRepLib import BRepLib
    from OCP.ShapeFix import ShapeFix_Face

    surface = BRep_Tool.Surface_s(bspline_face(fit))
    lines = [np.asarray(line, dtype=float).reshape(-1, 3) for line in boundaries]
    uv_lines = [np.column_stack(fit.closest_parameters(line)) for line in lines]
    count = len(uv_lines)
    corners = []  # the corner between line i and line i+1, in (u, v)
    for index in range(count):
        following = uv_lines[(index + 1) % count]
        corners.append(0.5 * (uv_lines[index][-1] + following[0]))
    vertices = [BRepBuilderAPI_MakeVertex(surface.Value(float(u), float(v))).Vertex() for u, v in corners]
    wire = BRepBuilderAPI_MakeWire()
    for index, uv in enumerate(uv_lines):
        uv = uv.copy()
        uv[0] = corners[index - 1]
        uv[-1] = corners[index]
        curve2d = _uv_curve(uv, closed=count == 1)
        start, end = vertices[index - 1], vertices[index]
        edge = BRepBuilderAPI_MakeEdge(curve2d, surface, start, end)
        if not edge.IsDone():
            raise ValueError("a boundary curve could not be made into an edge")
        wire.Add(edge.Edge())
    if not wire.IsDone():
        raise ValueError("the boundary curves do not close a loop on the surface")
    face_maker = BRepBuilderAPI_MakeFace(surface, wire.Wire(), True)
    if not face_maker.IsDone():
        raise ValueError("the surface could not be cut to the boundary")
    face = face_maker.Face()
    BRepLib.BuildCurves3d_s(face)
    fixer = ShapeFix_Face(face)
    fixer.FixOrientation()
    fixer.Perform()
    return fixer.Face()


def _uv_curve(uv: np.ndarray, *, closed: bool) -> object:
    """A smooth 2D B-spline through a curve's (u, v) on the surface, ends exact.

    Approximation, not interpolation: the foot-point parameters carry the scan's noise, and
    an exact interpolant through them wiggled up to 0.46 mm off the curve between samples.
    """

    from OCP.Geom2dAPI import Geom2dAPI_PointsToBSpline
    from OCP.GeomAbs import GeomAbs_C2
    from OCP.gp import gp_Pnt2d
    from OCP.TColgp import TColgp_Array1OfPnt2d

    samples = _resample(uv, max(16, min(200, len(uv))))
    if closed:
        samples[-1] = samples[0]
    scale = float(np.linalg.norm(samples.max(axis=0) - samples.min(axis=0))) or 1.0
    points = TColgp_Array1OfPnt2d(1, len(samples))
    for position, (u, v) in enumerate(samples, start=1):
        points.SetValue(position, gp_Pnt2d(float(u), float(v)))
    approximation = Geom2dAPI_PointsToBSpline(points, 3, 8, GeomAbs_C2, 2e-4 * scale)
    if not approximation.IsDone():
        raise ValueError("a boundary curve could not be laid on the surface")
    return approximation.Curve()


def _resample(polyline: np.ndarray, count: int) -> np.ndarray:
    """``count`` points evenly spaced along a polyline (any dimension), ends kept."""

    steps = np.linalg.norm(np.diff(polyline, axis=0), axis=1)
    length = np.r_[0.0, np.cumsum(steps)]
    if length[-1] <= 0:
        return polyline[[0, -1]]
    targets = np.linspace(0.0, length[-1], max(count, 2))
    return np.column_stack([np.interp(targets, length, polyline[:, axis]) for axis in range(polyline.shape[1])])


def primitive_patch(fit: PrimitiveFit, points: object, expand: float = 0.15) -> object:
    """A primitive face sized to the selected points plus a margin (Fit Surface, exact types)."""

    from openretop.cad_kernel.primitive_solid import primitive_face

    data = np.asarray(points, dtype=float).reshape(-1, 3)
    lower, upper = data.min(axis=0), data.max(axis=0)
    center = 0.5 * (lower + upper)
    extent = float(np.linalg.norm(upper - lower)) * (0.5 + max(0.0, expand)) / 1.5
    return primitive_face(fit, center, max(extent, 1e-3))


# -- curves -----------------------------------------------------------------------------------


def bspline_edge(points: object, *, closed: bool = False, tolerance: float = 1e-3) -> object:
    """A smooth edge through a polyline's points (sketch curves, section curves, boundaries)."""

    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.GeomAbs import GeomAbs_C2
    from OCP.GeomAPI import GeomAPI_PointsToBSpline
    from OCP.gp import gp_Pnt
    from OCP.TColgp import TColgp_Array1OfPnt

    data = np.asarray(points, dtype=float).reshape(-1, 3)
    if closed and len(data) > 2 and np.linalg.norm(data[0] - data[-1]) > 1e-9:
        data = np.vstack([data, data[:1]])
    keep = np.r_[True, np.linalg.norm(np.diff(data, axis=0), axis=1) > 1e-9]
    data = data[keep]
    if len(data) < 2:
        raise ValueError("a curve needs at least two distinct points")
    array = TColgp_Array1OfPnt(1, len(data))
    for index, point in enumerate(data, start=1):
        array.SetValue(index, gp_Pnt(*(float(value) for value in point)))
    approximation = GeomAPI_PointsToBSpline(array, 3, 8, GeomAbs_C2, tolerance)
    return BRepBuilderAPI_MakeEdge(approximation.Curve()).Edge()


def loft_surface(curves: list[object], *, ruled: bool = False) -> object:
    """A surface through two or more section curves (polylines), as in ExModel's Loft."""

    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeWire
    from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections

    if len(curves) < 2:
        raise ValueError("a loft needs at least two curves")
    loft = BRepOffsetAPI_ThruSections(False, ruled, 1e-6)
    loft.CheckCompatibility(False)
    previous: np.ndarray | None = None
    for curve in curves:
        data = np.asarray(curve, dtype=float).reshape(-1, 3)
        if previous is not None and _reversed_relative_to(previous, data):
            data = data[::-1]  # sections drawn in opposite directions would twist the loft
        previous = data
        loft.AddWire(BRepBuilderAPI_MakeWire(bspline_edge(data)).Wire())
    loft.Build()
    if not loft.IsDone():
        raise ValueError("the curves could not be lofted")
    faces = faces_of(loft.Shape())
    if len(faces) != 1:
        return loft.Shape()
    return faces[0]


def _reversed_relative_to(first: np.ndarray, second: np.ndarray) -> bool:
    same = np.linalg.norm(first[0] - second[0]) + np.linalg.norm(first[-1] - second[-1])
    swapped = np.linalg.norm(first[0] - second[-1]) + np.linalg.norm(first[-1] - second[0])
    return bool(swapped < same)


# -- fill -------------------------------------------------------------------------------------


@dataclass
class FillBoundary:
    """One side of a fill: a curve (points) or an existing face's edge, with its continuity."""

    points: np.ndarray | None = None
    edge: object | None = None
    support_face: object | None = None  # the neighbour, for "smooth" (G1) sides
    continuity: str = "contact"  # "contact" (G0) or "smooth" (G1)


def fill_surface(
    boundaries: list[FillBoundary],
    *,
    scan_points: object | None = None,
    degree: int = 3,
    max_scan_points: int = 400,
) -> object:
    """A face bounded by a closed chain of curves/edges (ExModel's Fill Surface).

    "smooth" sides are tangent to their support face. ``scan_points`` ("on scan data") pull
    the inside of the patch onto the scan.
    """

    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeFilling
    from OCP.GeomAbs import GeomAbs_C0, GeomAbs_G1
    from OCP.gp import gp_Pnt

    if len(boundaries) < 2:
        raise ValueError("a fill needs a closed chain of at least two boundary curves")
    filling = BRepOffsetAPI_MakeFilling(degree, 15, 2, False, 1e-5, 1e-4, 0.01, 0.1, 8, 9)
    edges = _chain_edges(boundaries)
    for boundary, edge in zip(boundaries, edges, strict=True):
        if boundary.continuity == "smooth" and boundary.support_face is not None:
            filling.Add(edge, boundary.support_face, GeomAbs_G1, True)
        else:
            filling.Add(edge, GeomAbs_C0, True)
    if scan_points is not None:
        data = np.asarray(scan_points, dtype=float).reshape(-1, 3)
        if len(data) > max_scan_points:
            data = data[np.random.default_rng(0).choice(len(data), max_scan_points, replace=False)]
        for point in data:
            filling.Add(gp_Pnt(*(float(value) for value in point)))
    filling.Build()
    if not filling.IsDone():
        raise ValueError("the boundary could not be filled (is the chain closed?)")
    faces = faces_of(filling.Shape())
    if not faces:
        raise ValueError("the fill produced no face")
    return faces[0]


def _chain_edges(boundaries: list[FillBoundary]) -> list[object]:
    """Edges of the chain, with polyline ends snapped to their neighbours so the loop closes."""

    point_sets: list[np.ndarray | None] = []
    for boundary in boundaries:
        point_sets.append(None if boundary.points is None else np.asarray(boundary.points, dtype=float).reshape(-1, 3).copy())
    # orient consecutive polylines head-to-tail and average the shared corners
    for index, current in enumerate(point_sets):
        if current is None:
            continue
        following = point_sets[(index + 1) % len(point_sets)]
        if following is None:
            continue
        if index == 0:
            ends = [(np.linalg.norm(current[a] - following[b]), a, b) for a in (0, -1) for b in (0, -1)]
            _gap, a, _b = min(ends)
            if a == 0:
                current[:] = current[::-1]
        if np.linalg.norm(current[-1] - following[-1]) < np.linalg.norm(current[-1] - following[0]):
            following[:] = following[::-1]
        corner = 0.5 * (current[-1] + following[0])
        current[-1] = corner
        following[0] = corner
    edges = []
    for boundary, points in zip(boundaries, point_sets, strict=True):
        if points is not None:
            edges.append(bspline_edge(points))
        elif boundary.edge is not None:
            edges.append(boundary.edge)
        else:
            raise ValueError("every boundary needs a curve or an edge")
    return edges


# -- extend -----------------------------------------------------------------------------------


def extend_face(face: Any, distance: float, sides: tuple[str, ...] = ("u0", "u1", "v0", "v1")) -> object:
    """The face's surface grown by ``distance`` past the chosen sides (ExModel's Extend Surface).

    Analytic faces (plane, cylinder, cone, sphere) get a larger parameter range. Freeform
    faces continue their end spans' polynomials (curvature-continuous, the B-spline's natural
    extrapolation), resampled into a new B-spline surface over the larger range.
    """

    from OCP.BRep import BRep_Tool
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepTools import BRepTools
    from OCP.Geom import (
        Geom_ConicalSurface,
        Geom_CylindricalSurface,
        Geom_Plane,
        Geom_RectangularTrimmedSurface,
        Geom_SphericalSurface,
        Geom_ToroidalSurface,
    )

    surface = BRep_Tool.Surface_s(face)
    u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
    basis = surface
    if isinstance(basis, Geom_RectangularTrimmedSurface):
        basis = basis.BasisSurface()
    analytic = (Geom_Plane, Geom_CylindricalSurface, Geom_ConicalSurface, Geom_SphericalSurface, Geom_ToroidalSurface)
    if not isinstance(basis, analytic):
        return _extend_freeform(basis, (u0, u1, v0, v1), distance, sides)
    # analytic: grow the parameter box; angular parameters grow by distance / radius
    scale_u, scale_v = _parameter_scales(basis, face)
    du, dv = distance / scale_u, distance / scale_v
    if "u0" in sides:
        u0 -= du
    if "u1" in sides:
        u1 += du
    if "v0" in sides:
        v0 -= dv
    if "v1" in sides:
        v1 += dv
    if basis.IsUPeriodic() and u1 - u0 > 2.0 * math.pi:
        u0, u1 = 0.0, 2.0 * math.pi
    if basis.IsVPeriodic() and v1 - v0 > 2.0 * math.pi:
        v0, v1 = -0.5 * math.pi, 0.5 * math.pi
    return BRepBuilderAPI_MakeFace(basis, u0, u1, v0, v1, 1e-6).Face()


def _extend_freeform(surface: Any, bounds: tuple[float, float, float, float], distance: float, sides: tuple[str, ...]) -> object:
    from OCP.gp import gp_Pnt, gp_Vec

    from openretop.fitting.bspline_surface import fit_grid_surface

    u0, u1, v0, v1 = bounds
    point, du_vec, dv_vec = gp_Pnt(), gp_Vec(), gp_Vec()
    um, vm = 0.5 * (u0 + u1), 0.5 * (v0 + v1)
    surface.D1(um, vm, point, du_vec, dv_vec)
    length_u = max(du_vec.Magnitude() * (u1 - u0), 1e-9)
    length_v = max(dv_vec.Magnitude() * (v1 - v0), 1e-9)

    def steps(length: float, before: bool, after: bool) -> tuple[np.ndarray, np.ndarray]:
        """Fractions (0..1 across the face, beyond it per unit of ``distance``) and their
        approximate world positions, sampled about evenly in world units."""

        inside = 36
        outside = max(3, int(round(inside * distance / length)))
        fractions = [np.linspace(0.0, 1.0, inside)]
        world = [fractions[0] * length]
        if before:
            extra = np.linspace(-1.0, 0.0, outside + 1)[:-1]
            fractions.insert(0, extra)
            world.insert(0, extra * distance)
        if after:
            extra = np.linspace(1.0, 2.0, outside + 1)[1:]
            fractions.append(extra)
            world.append(length + (extra - 1.0) * distance)
        return np.concatenate(fractions), np.concatenate(world)

    steps_u, world_u = steps(length_u, "u0" in sides, "u1" in sides)
    steps_v, world_v = steps(length_v, "v0" in sides, "v1" in sides)
    grid = np.zeros((len(steps_u), len(steps_v), 3))
    for i, su in enumerate(steps_u):
        for j, sv in enumerate(steps_v):
            # inside: the surface itself; outside: straight on along its unit tangents (G1).
            # A cubic end span continued past its edge curls away within a few millimetres,
            # and a fixed parameter step overshoots where the surface is parameterized fast.
            cu = u0 + min(max(float(su), 0.0), 1.0) * (u1 - u0)
            cv = v0 + min(max(float(sv), 0.0), 1.0) * (v1 - v0)
            past_u = (su - 1.0 if su > 1.0 else su if su < 0.0 else 0.0) * distance
            past_v = (sv - 1.0 if sv > 1.0 else sv if sv < 0.0 else 0.0) * distance
            surface.D1(cu, cv, point, du_vec, dv_vec)
            tu = np.array(du_vec.Coord()) / max(du_vec.Magnitude(), 1e-12)
            tv = np.array(dv_vec.Coord()) / max(dv_vec.Magnitude(), 1e-12)
            grid[i, j] = np.array(point.Coord()) + past_u * tu + past_v * tv
    poles_u, poles_v = _pole_counts(surface)
    grown_u = int(1.5 * poles_u) + int(np.ceil(poles_u * distance / length_u)) * (("u0" in sides) + ("u1" in sides))
    grown_v = int(1.5 * poles_v) + int(np.ceil(poles_v * distance / length_v)) * (("v0" in sides) + ("v1" in sides))
    fit = fit_grid_surface(grid, world_u, world_v, control_u=min(grown_u, 48), control_v=min(grown_v, 48), smoothness=0.0)
    return bspline_face(fit)


def _pole_counts(surface: Any) -> tuple[int, int]:
    try:
        return max(int(surface.NbUPoles()), 8), max(int(surface.NbVPoles()), 8)
    except AttributeError:  # not a B-spline (an offset or swept surface): a moderate net
        return 12, 12


def _parameter_scales(surface: Any, face: Any) -> tuple[float, float]:
    """World length per unit of u and v at the face's middle."""

    from OCP.BRepTools import BRepTools
    from OCP.gp import gp_Pnt, gp_Vec

    u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
    point, du, dv = gp_Pnt(), gp_Vec(), gp_Vec()
    surface.D1(0.5 * (u0 + u1), 0.5 * (v0 + v1), point, du, dv)
    return max(du.Magnitude(), 1e-9), max(dv.Magnitude(), 1e-9)


# -- trim -------------------------------------------------------------------------------------


@dataclass
class TrimPiece:
    face: Any
    source: int  # index of the input face it came from
    overlap: float = 0.0  # share of the piece lying on the scan
    area: float = 0.0
    keep: bool = False


def split_faces(faces: list[object], *, fuzzy: float = 1e-4) -> list[TrimPiece]:
    """Split every face by every other (OCC general fuse); each piece remembers its source."""

    from OCP.BOPAlgo import BOPAlgo_Builder

    builder = BOPAlgo_Builder()
    for face in faces:
        builder.AddArgument(face)
    builder.SetFuzzyValue(fuzzy)
    builder.SetRunParallel(True)
    builder.SetNonDestructive(True)
    builder.Perform()
    if builder.HasErrors():
        raise ValueError("the surfaces could not be intersected with each other")
    pieces: list[TrimPiece] = []
    for index, face in enumerate(faces):
        images = list(builder.Modified(face))
        if not images and not builder.IsDeleted(face):
            images = [face]
        for image in images:
            for piece in faces_of(image):
                pieces.append(TrimPiece(piece, index, area=face_area(piece)))
    return pieces


def mark_pieces_on_scan(
    pieces: list[TrimPiece],
    scan_vertices: object,
    scan_normals: object,
    *,
    tolerance: float,
    overlap: float = 0.5,
    samples: int = 200,
) -> list[TrimPiece]:
    """Keep the pieces mostly lying on the scan (ExModel's automatic trimming)."""

    from scipy.spatial import cKDTree

    vertices = np.asarray(scan_vertices, dtype=float).reshape(-1, 3)
    normals = np.asarray(scan_normals, dtype=float).reshape(-1, 3)
    tree = cKDTree(vertices)
    spacing = _scan_spacing(tree, vertices)
    for piece in pieces:
        points = sample_face(piece.face, samples)
        if len(points) == 0:
            piece.overlap, piece.keep = 0.0, False
            continue
        distance = scan_distance(points, tree, vertices, normals, spacing)
        piece.overlap = float(np.mean(distance <= tolerance))
        piece.keep = piece.overlap >= overlap
    return pieces


def _scan_spacing(tree: Any, vertices: np.ndarray) -> float:
    """Typical distance between neighbouring scan vertices.

    Coincident vertices (an STL stores every triangle's corners separately) are skipped:
    counting them made the spacing zero, and then nothing counted as lying on the scan.
    """

    sample = vertices[:: max(1, len(vertices) // 2000)]
    distance, _index = tree.query(sample, k=8)
    apart = np.where(distance > 1e-9, distance, np.inf).min(axis=1)
    apart = apart[np.isfinite(apart)]
    return float(np.median(apart)) if len(apart) else 0.0


def scan_distance(points: np.ndarray, tree: Any, vertices: np.ndarray, normals: np.ndarray, spacing: float) -> np.ndarray:
    """Distance to the scan surface: along the nearest vertex's normal when close beside it."""

    distance, nearest = tree.query(points)
    offset = points - vertices[nearest]
    along = np.einsum("ij,ij->i", offset, normals[nearest])
    lateral = np.linalg.norm(offset - along[:, None] * normals[nearest], axis=1)
    return np.where(lateral <= 1.5 * spacing, np.abs(along), distance)


def sample_face(face: Any, count: int) -> np.ndarray:
    """Points spread over a (trimmed) face, from its tessellation."""

    mesh = shape_mesh(face, deflection=None)
    if len(mesh.triangles) == 0:
        return np.zeros((0, 3))
    a, b, c = (mesh.vertices[mesh.triangles[:, k]] for k in range(3))
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    if area.sum() <= 0:
        return np.zeros((0, 3))
    rng = np.random.default_rng(1)
    chosen = rng.choice(len(area), size=count, p=area / area.sum())
    r1, r2 = rng.random(count), rng.random(count)
    flip = r1 + r2 > 1
    r1[flip], r2[flip] = 1 - r1[flip], 1 - r2[flip]
    return a[chosen] + r1[:, None] * (b[chosen] - a[chosen]) + r2[:, None] * (c[chosen] - a[chosen])


# -- sew --------------------------------------------------------------------------------------


@dataclass
class SewResult:
    shape: Any
    closed: bool
    solid: bool
    free_edges: int
    volume: float = 0.0
    warnings: list[str] = field(default_factory=list)


def sew(faces: list[object], *, tolerance: float = 0.01, make_solid: bool = True) -> SewResult:
    """Sew faces into a shell; a closed shell becomes a solid."""

    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid, BRepBuilderAPI_Sewing
    from OCP.ShapeFix import ShapeFix_Solid
    from OCP.TopAbs import TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    if not faces:
        raise ValueError("nothing to sew")
    sewing = BRepBuilderAPI_Sewing(tolerance)
    for face in faces:
        sewing.Add(face)
    sewing.Perform()
    shape = sewing.SewedShape()
    free = int(sewing.NbFreeEdges())
    warnings: list[str] = []
    if sewing.NbMultipleEdges():
        warnings.append(f"{sewing.NbMultipleEdges()} edges are shared by more than two faces")
    shells = []
    explorer = TopExp_Explorer(shape, TopAbs_SHELL)
    while explorer.More():
        shells.append(TopoDS.Shell_s(explorer.Current()))
        explorer.Next()
    closed = free == 0 and len(shells) == 1
    if closed and make_solid:
        solid = BRepBuilderAPI_MakeSolid(shells[0]).Solid()
        fixer = ShapeFix_Solid(solid)
        fixer.Perform()
        solid = fixer.Solid()
        volume = shape_volume(solid)
        if volume < 0:
            solid.Reverse()
            volume = -volume
        return SewResult(solid, True, True, 0, volume, warnings)
    if free:
        warnings.append(f"{free} open edges: the surfaces do not close a volume yet")
    return SewResult(shape, closed, False, free, 0.0, warnings)


# -- display and measurement ------------------------------------------------------------------


@dataclass
class ShapeMesh:
    vertices: np.ndarray
    triangles: np.ndarray
    face_index: np.ndarray  # face number (TopExp order) of each triangle


def shape_mesh(shape: Any, deflection: float | None = 0.05, angle: float = 0.35) -> ShapeMesh:
    """Triangles of every face, for display and sampling."""

    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_REVERSED
    from OCP.TopLoc import TopLoc_Location

    if deflection is None:
        size = shape_size(shape)
        deflection = max(size * 0.002, 1e-4)
    BRepMesh_IncrementalMesh(shape, float(deflection), False, float(angle), True)
    vertex_blocks, triangle_blocks, face_blocks = [], [], []
    offset = 0
    for number, face in enumerate(faces_of(shape)):
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        if triangulation is None:
            continue
        node = triangulation.Node
        nodes = np.array([node(index).Coord() for index in range(1, triangulation.NbNodes() + 1)], dtype=float).reshape(-1, 3)
        if not location.IsIdentity():
            nodes = _transformed(nodes, location.Transformation())
        triangles = np.array(
            [triangulation.Triangle(index).Get() for index in range(1, triangulation.NbTriangles() + 1)],
            dtype=np.int64,
        ).reshape(-1, 3) - 1
        if face.Orientation() == TopAbs_REVERSED:
            triangles = triangles[:, [0, 2, 1]]
        vertex_blocks.append(nodes)
        triangle_blocks.append(triangles + offset)
        face_blocks.append(np.full(len(triangles), number, dtype=np.int64))
        offset += len(nodes)
    if not vertex_blocks:
        return ShapeMesh(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), np.zeros(0, dtype=np.int64))
    return ShapeMesh(np.vstack(vertex_blocks), np.vstack(triangle_blocks), np.concatenate(face_blocks))


def _transformed(points: np.ndarray, transform: Any) -> np.ndarray:
    matrix = np.array([[transform.Value(row, column) for column in range(1, 5)] for row in range(1, 4)])
    return points @ matrix[:, :3].T + matrix[:, 3]


def signed_distances(shape: Any, points: object, *, deflection: float | None = None) -> np.ndarray:
    """Distance from each point to the shape (positive on the side its face normals point to)."""

    from vtkmodules.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray, vtk_to_numpy
    from vtkmodules.vtkCommonCore import vtkPoints
    from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
    from vtkmodules.vtkFiltersCore import vtkImplicitPolyDataDistance

    if deflection is None:  # the chord error stays well under scan noise
        deflection = max(shape_size(shape) * 1e-4, 0.005)
    mesh = shape_mesh(shape, deflection=deflection)
    query = np.ascontiguousarray(np.asarray(points, dtype=float).reshape(-1, 3))
    if len(mesh.triangles) == 0 or len(query) == 0:
        return np.full(len(query), np.inf)
    polydata = vtkPolyData()
    vtk_points = vtkPoints()
    vtk_points.SetData(numpy_to_vtk(np.ascontiguousarray(mesh.vertices), deep=True))
    polydata.SetPoints(vtk_points)
    cells = vtkCellArray()
    offsets = np.arange(0, 3 * len(mesh.triangles) + 1, 3, dtype=np.int64)
    cells.SetData(numpy_to_vtkIdTypeArray(offsets, deep=True), numpy_to_vtkIdTypeArray(mesh.triangles.astype(np.int64).ravel(), deep=True))
    polydata.SetPolys(cells)
    distance = vtkImplicitPolyDataDistance()
    distance.SetInput(polydata)
    values = numpy_to_vtk(np.zeros(len(query)), deep=True)
    distance.FunctionValue(numpy_to_vtk(query, deep=True), values)
    return vtk_to_numpy(values).astype(float)


def faces_of(shape: Any) -> list[Any]:
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    found = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        found.append(TopoDS.Face_s(explorer.Current()))
        explorer.Next()
    return found


def face_area(shape: Any) -> float:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    properties = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, properties)
    return float(properties.Mass())


def shape_volume(shape: Any) -> float:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    properties = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, properties)
    return float(properties.Mass())


def shape_size(shape: Any) -> float:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    if box.IsVoid():
        return 0.0
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return float(math.dist((xmin, ymin, zmin), (xmax, ymax, zmax)))


def compound(shapes: list[object]) -> object:
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound

    result = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(result)
    for shape in shapes:
        builder.Add(result, shape)
    return result


__all__ = (
    "FillBoundary",
    "SewResult",
    "ShapeMesh",
    "TrimPiece",
    "bspline_edge",
    "bspline_face",
    "compound",
    "extend_face",
    "face_area",
    "faces_of",
    "fill_surface",
    "from_brep",
    "loft_surface",
    "mark_pieces_on_scan",
    "primitive_patch",
    "sample_face",
    "scan_distance",
    "sew",
    "shape_mesh",
    "shape_size",
    "shape_volume",
    "signed_distances",
    "split_faces",
    "to_brep",
)
