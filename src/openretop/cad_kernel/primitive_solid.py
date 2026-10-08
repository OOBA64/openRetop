"""A closed CAD solid from fitted primitives and the scan (RE-08).

QuickSurface-style "trim and extend", automated:

1. Every fitted primitive becomes a face large enough to pass right through the part.
2. OpenCASCADE's volume maker (``BOPAlgo_MakerVolume``) splits space into every closed cell
   those faces bound.
3. Each cell is classified as material or air by the scan: sample points inside the cell,
   and for each, the nearest scan point's outward normal says whether the sample is behind
   the surface (material) or in front of it (air). This works with holes in the scan.
4. The material cells are fused, and coplanar or co-cylindrical faces are unified.

Extended faces that slice through material only split it into cells that are fused back. A
drilled hole's cells contain no material, so the hole stays open. The result is one valid
B-rep solid ready for STEP.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from openretop.fitting import PrimitiveFit


@dataclass
class PrimitiveSolidResult:
    success: bool
    shape: object | None = None  # TopoDS_Shape (a solid, or a compound of solids)
    volume: float = 0.0
    face_count: int = 0
    solid_count: int = 0
    cell_count: int = 0
    material_cells: int = 0
    reason: str = ""
    warnings: list[str] = field(default_factory=list)

    def cadquery_shape(self) -> object | None:
        if self.shape is None:
            return None
        import cadquery as cq

        return cq.Shape.cast(self.shape)


def primitive_face(fit: PrimitiveFit, center: np.ndarray, extent: float) -> object:
    """An OCC face of the primitive, big enough to pass through a part of size ``extent``."""

    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.Geom import Geom_ConicalSurface, Geom_CylindricalSurface, Geom_SphericalSurface, Geom_ToroidalSurface
    from OCP.gp import gp_Ax3, gp_Dir, gp_Pln, gp_Pnt

    p = fit.params

    def pnt(value: object) -> object:
        x, y, z = (float(v) for v in np.asarray(value, dtype=float))
        return gp_Pnt(x, y, z)

    def direction(value: object) -> object:
        x, y, z = (float(v) for v in np.asarray(value, dtype=float))
        return gp_Dir(x, y, z)

    half = 1.5 * extent
    if fit.kind == "plane":
        normal = np.asarray(p["normal"], dtype=float)
        origin = center - normal * float((center - np.asarray(p["point"], dtype=float)) @ normal)
        return BRepBuilderAPI_MakeFace(gp_Pln(pnt(origin), direction(normal)), -half, half, -half, half).Face()
    if fit.kind == "cylinder":
        axis = np.asarray(p["axis"], dtype=float)
        base = np.asarray(p["point"], dtype=float)
        base = base + axis * float((center - base) @ axis)  # centre the face on the part
        surface = Geom_CylindricalSurface(gp_Ax3(pnt(base), direction(axis)), _scalar(p, "radius"))
        return BRepBuilderAPI_MakeFace(surface, 0.0, 2.0 * math.pi, -half, half, 1e-7).Face()
    if fit.kind == "cone":
        axis = np.asarray(p["axis"], dtype=float)
        half_angle = math.radians(_scalar(p, "half_angle_degrees"))
        surface = Geom_ConicalSurface(gp_Ax3(pnt(p["apex"]), direction(axis)), half_angle, 0.0)
        reach = (float(np.linalg.norm(center - np.asarray(p["apex"], dtype=float))) + half) / max(math.cos(half_angle), 1e-6)
        return BRepBuilderAPI_MakeFace(surface, 0.0, 2.0 * math.pi, 0.0, reach, 1e-7).Face()
    if fit.kind == "sphere":
        surface = Geom_SphericalSurface(gp_Ax3(pnt(p["center"]), gp_Dir(0.0, 0.0, 1.0)), _scalar(p, "radius"))
        return BRepBuilderAPI_MakeFace(surface, 1e-7).Face()
    if fit.kind == "torus":
        surface = Geom_ToroidalSurface(gp_Ax3(pnt(p["center"]), direction(p["axis"])), _scalar(p, "major_radius"), _scalar(p, "minor_radius"))
        return BRepBuilderAPI_MakeFace(surface, 1e-7).Face()
    raise ValueError(f"no face for {fit.kind}")


def solid_from_primitives(
    fits: list[PrimitiveFit],
    scan_vertices: object,
    scan_normals: object,
    *,
    fuzzy: float = 1e-5,
    samples_per_cell: int = 24,
) -> PrimitiveSolidResult:
    from OCP.BOPAlgo import BOPAlgo_MakerVolume
    from OCP.TopTools import TopTools_ListOfShape

    vertices = np.asarray(scan_vertices, dtype=float).reshape(-1, 3)
    normals = np.asarray(scan_normals, dtype=float).reshape(-1, 3)
    usable = [fit for fit in fits if fit.success and fit.kind in ("plane", "cylinder", "cone", "sphere", "torus")]
    if len(usable) < 2 or len(vertices) < 10:
        return PrimitiveSolidResult(False, reason="needs at least two fitted faces and a scan")
    lower, upper = vertices.min(axis=0), vertices.max(axis=0)
    center = 0.5 * (lower + upper)
    extent = float(np.linalg.norm(upper - lower))

    faces = TopTools_ListOfShape()
    warnings: list[str] = []
    for fit in usable:
        try:
            faces.Append(primitive_face(fit, center, extent))
        except Exception as exc:  # an OCC construction error for one face should not sink the rest
            warnings.append(f"skipped a {fit.kind}: {exc}")
    maker = BOPAlgo_MakerVolume()
    maker.SetArguments(faces)
    maker.SetIntersect(True)
    maker.SetRunParallel(True)
    maker.SetFuzzyValue(fuzzy)
    maker.Perform()
    if maker.HasErrors():
        return PrimitiveSolidResult(False, reason="OpenCASCADE could not split space by these faces", warnings=warnings)
    cells = _solids(maker.Shape())
    if not cells:
        return PrimitiveSolidResult(False, reason="the faces do not enclose any volume", warnings=warnings)

    from scipy.spatial import cKDTree

    tree = cKDTree(vertices)
    if _normals_point_inward(tree, vertices, normals, lower, upper):
        normals = -normals  # some exporters wind triangles inward; the vote needs outward normals
        warnings.append("the scan's normals point inwards; they were flipped for the material test")
    rng = np.random.default_rng(5)
    material = []
    for cell in cells:
        verdict = _is_material(cell, tree, vertices, normals, rng, samples_per_cell)
        if verdict:
            material.append(cell)
    if not material:
        return PrimitiveSolidResult(False, cell_count=len(cells), reason="no cell is inside the scan", warnings=warnings)

    shape = _fuse(material)
    shape = _unify(shape)
    solids = _solids(shape)
    return PrimitiveSolidResult(
        True,
        shape=shape,
        volume=_volume(shape),
        face_count=_count(shape, "face"),
        solid_count=len(solids),
        cell_count=len(cells),
        material_cells=len(material),
        warnings=warnings,
    )


# -- helpers ---------------------------------------------------------------------------


def _scalar(params: dict[str, object], key: str) -> float:
    return float(np.asarray(params[key], dtype=float))


def _solids(shape: object) -> list[object]:
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    found = []
    while explorer.More():
        found.append(TopoDS.Solid_s(explorer.Current()))
        explorer.Next()
    return found


def _count(shape: object, kind: str) -> int:
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer

    explorer = TopExp_Explorer(shape, {"face": TopAbs_FACE, "solid": TopAbs_SOLID}[kind])
    count = 0
    while explorer.More():
        count += 1
        explorer.Next()
    return count


def _volume(shape: object) -> float:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    properties = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, properties)
    return float(properties.Mass())


def _normals_point_inward(tree, vertices, normals, lower, upper) -> bool:
    """Probe from points certainly outside the scan: outward normals face them."""

    size = upper - lower
    probes = []
    for axis in range(3):
        for sign in (-1.0, 1.0):
            point = 0.5 * (lower + upper)
            point[axis] = (upper if sign > 0 else lower)[axis] + sign * 0.5 * size.max()
            probes.append(point)
    probes_array = np.asarray(probes)
    _distance, nearest = tree.query(probes_array)
    facing = np.einsum("ij,ij->i", probes_array - vertices[nearest], normals[nearest])
    return bool(np.mean(facing < 0.0) > 0.5)


def _is_material(cell, tree, vertices, normals, rng, samples) -> bool:
    """Most sample points inside the cell lie behind the scan surface (material side)."""

    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_IN

    box = Bnd_Box()
    BRepBndLib.Add_s(cell, box)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    classifier = BRepClass3d_SolidClassifier(cell)
    inside: list[tuple[float, float, float]] = []
    for _attempt in range(samples * 8):
        point = (rng.uniform(xmin, xmax), rng.uniform(ymin, ymax), rng.uniform(zmin, zmax))
        classifier.Perform(gp_Pnt(*point), 1e-7)
        if classifier.State() == TopAbs_IN:
            inside.append(point)
            if len(inside) >= samples:
                break
    if not inside:
        return False
    points = np.asarray(inside)
    _distance, nearest = tree.query(points)
    side = np.einsum("ij,ij->i", points - vertices[nearest], normals[nearest])
    return bool(np.mean(side < 0.0) > 0.5)


def _fuse(solids: list[object]) -> object:
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.TopTools import TopTools_ListOfShape

    if len(solids) == 1:
        return solids[0]
    arguments = TopTools_ListOfShape()
    arguments.Append(solids[0])
    tools = TopTools_ListOfShape()
    for solid in solids[1:]:
        tools.Append(solid)
    fuse = BRepAlgoAPI_Fuse()
    fuse.SetArguments(arguments)
    fuse.SetTools(tools)
    fuse.SetRunParallel(True)
    fuse.Build()
    return fuse.Shape()


def _unify(shape: object) -> object:
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain

    unify = ShapeUpgrade_UnifySameDomain(shape, True, True, True)
    unify.Build()
    return unify.Shape()


__all__ = ("PrimitiveSolidResult", "primitive_face", "solid_from_primitives")
