"""Reference parts (B1-B5) and the scan simulator.

A reference part is a CadQuery solid plus its ground truth: the parameters of every analytic
feature (planes, cylinders, cones...) and the solid's volume. ``scan_from_part`` tessellates
the part face by face, refines it to scanner-like density, displaces every vertex along its
normal by Gaussian noise and punches holes, all from one seed. Each scan triangle keeps the
index of the reference face it came from, which is the ground truth for segmentation.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

Truth = dict[str, object]


@dataclass(frozen=True)
class ReferencePart:
    name: str
    title: str
    shape: object  # cadquery.Shape (a solid)
    truth: Truth
    face_types: tuple[str, ...]  # OCC geometry type of each face, e.g. "PLANE", "CYLINDER"


@dataclass
class ScanMesh:
    part: ReferencePart
    vertices: np.ndarray
    triangles: np.ndarray
    face_labels: np.ndarray  # reference face index of every triangle (ground-truth segmentation)
    noise_sigma: float
    seed: int
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def triangle_count(self) -> int:
        return int(len(self.triangles))

    def triangles_of_type(self, geom_type: str) -> np.ndarray:
        types = np.asarray(self.part.face_types, dtype=object)
        return np.nonzero(types[self.face_labels] == geom_type)[0]


# -- the parts -------------------------------------------------------------------------


def _cq():  # imported lazily: the app runs without CadQuery, the benchmarks do not
    import cadquery as cq

    return cq


def bracket() -> ReferencePart:
    """B1: plate 80 x 50 x 10, boss R12 x 15 with a R5 through hole, R4 hole, 2 mm chamfer."""

    cq = _cq()
    plate = cq.Workplane("XY").box(80.0, 50.0, 10.0)  # z from -5 to 5
    plate = plate.edges("|Z").chamfer(2.0)
    boss = cq.Workplane("XY").workplane(offset=5.0).center(20.0, 0.0).circle(12.0).extrude(15.0)
    part = plate.union(boss)
    part = part.cut(cq.Workplane("XY").workplane(offset=-10.0).center(20.0, 0.0).circle(5.0).extrude(40.0))
    part = part.cut(cq.Workplane("XY").workplane(offset=-10.0).center(-25.0, 0.0).circle(4.0).extrude(40.0))
    truth: Truth = {
        "cylinders": [
            {"name": "boss", "radius": 12.0, "axis": (0.0, 0.0, 1.0), "point": (20.0, 0.0, 0.0), "outward": True},
            {"name": "boss hole", "radius": 5.0, "axis": (0.0, 0.0, 1.0), "point": (20.0, 0.0, 0.0), "outward": False},
            {"name": "plate hole", "radius": 4.0, "axis": (0.0, 0.0, 1.0), "point": (-25.0, 0.0, 0.0), "outward": False},
        ],
        "planes": [
            {"name": "bottom", "normal": (0.0, 0.0, -1.0), "offset": 5.0},
            {"name": "top", "normal": (0.0, 0.0, 1.0), "offset": 5.0},
            {"name": "boss top", "normal": (0.0, 0.0, 1.0), "offset": 20.0},
            {"name": "+x side", "normal": (1.0, 0.0, 0.0), "offset": 40.0},
            {"name": "+y side", "normal": (0.0, 1.0, 0.0), "offset": 25.0},
        ],
        "chamfer": 2.0,
    }
    return _reference("bracket", "B1 bracket", part, truth)


def shaft() -> ReferencePart:
    """B2: turned shaft along Z: R10 x 40 with a 4 mm wide R8 groove, a cone to R6, R6 x 20."""

    cq = _cq()
    profile = [
        (0.0, 0.0),
        (10.0, 0.0),
        (10.0, 13.0),
        (8.0, 13.0),
        (8.0, 17.0),
        (10.0, 17.0),
        (10.0, 40.0),
        (6.0, 50.0),
        (6.0, 70.0),
        (0.0, 70.0),
    ]
    part = cq.Workplane("XZ").polyline(profile).close().revolve(360.0, (0, 0, 0), (0, 1, 0))
    half_angle = math.degrees(math.atan2(10.0 - 6.0, 50.0 - 40.0))
    truth: Truth = {
        "axis": (0.0, 0.0, 1.0),
        "cylinders": [
            {"name": "main", "radius": 10.0, "axis": (0.0, 0.0, 1.0), "point": (0.0, 0.0, 0.0), "outward": True},
            {"name": "groove", "radius": 8.0, "axis": (0.0, 0.0, 1.0), "point": (0.0, 0.0, 0.0), "outward": True},
            {"name": "end", "radius": 6.0, "axis": (0.0, 0.0, 1.0), "point": (0.0, 0.0, 0.0), "outward": True},
        ],
        "cones": [{"name": "taper", "half_angle_degrees": half_angle, "axis": (0.0, 0.0, 1.0), "apex_z": 40.0 + 10.0 * 10.0 / 4.0}],
        "profile": profile,
    }
    return _reference("shaft", "B2 shaft", part, truth)


def housing() -> ReferencePart:
    """B3: block 60 x 40 x 25 with R3 vertical fillets and a 40 x 24 x 15 pocket (R2 corners)."""

    cq = _cq()
    block = cq.Workplane("XY").box(60.0, 40.0, 25.0).edges("|Z").fillet(3.0)
    pocket = cq.Workplane("XY").workplane(offset=12.5 - 15.0).rect(40.0, 24.0).extrude(15.0).edges("|Z").fillet(2.0)
    part = block.cut(pocket)
    truth: Truth = {
        "outer_fillet": 3.0,
        "pocket_fillet": 2.0,
        "pocket": {"width": 40.0, "height": 24.0, "depth": 15.0},
        "box": (60.0, 40.0, 25.0),
    }
    return _reference("housing", "B3 housing", part, truth)


def knob() -> ReferencePart:
    """B4: R15 x 8 revolved base with a freeform lofted grip on top."""

    cq = _cq()
    base = cq.Workplane("XY").circle(15.0).extrude(8.0)
    grip = (
        cq.Workplane("XY")
        .workplane(offset=8.0)
        .ellipse(13.0, 6.0)
        .workplane(offset=10.0)
        .ellipse(10.0, 4.5)
        .workplane(offset=8.0)
        .ellipse(11.0, 3.5)
        .loft(ruled=False)
    )
    part = base.union(grip)
    truth: Truth = {"cylinders": [{"name": "base", "radius": 15.0, "axis": (0.0, 0.0, 1.0), "point": (0.0, 0.0, 0.0), "outward": True}]}
    return _reference("knob", "B4 knob", part, truth)


def casting() -> ReferencePart:
    """B5: a freeform body lofted through spline sections, with an R6 bore."""

    cq = _cq()

    def section(z: float, scale: float, bulge: float) -> list[tuple[float, float]]:
        points = []
        for index in range(10):
            angle = 2.0 * math.pi * index / 10.0
            radius = scale * (20.0 + bulge * math.cos(3.0 * angle))
            points.append((radius * math.cos(angle) * 1.3, radius * math.sin(angle)))
        return points

    body = cq.Workplane("XY")
    for z, scale, bulge in ((0.0, 1.0, 2.0), (12.0, 0.92, 3.0), (24.0, 0.8, 1.5)):
        body = body.workplane(offset=z if z == 0.0 else 12.0).spline(section(z, scale, bulge), periodic=True).close()
    part = body.loft(ruled=False)
    part = part.cut(cq.Workplane("XY").workplane(offset=-5.0).circle(6.0).extrude(40.0))
    truth: Truth = {"cylinders": [{"name": "bore", "radius": 6.0, "axis": (0.0, 0.0, 1.0), "point": (0.0, 0.0, 0.0), "outward": False}]}
    return _reference("casting", "B5 casting", part, truth)


BENCHMARKS: dict[str, Callable[[], ReferencePart]] = {
    "bracket": bracket,
    "shaft": shaft,
    "housing": housing,
    "knob": knob,
    "casting": casting,
}


def make_part(name: str) -> ReferencePart:
    try:
        return BENCHMARKS[name]()
    except KeyError as exc:
        raise ValueError(f"Unknown benchmark part: {name} (choose from {', '.join(BENCHMARKS)})") from exc


def _reference(name: str, title: str, workplane: object, truth: Truth) -> ReferencePart:
    solid = workplane.val()  # type: ignore[attr-defined]
    truth = dict(truth)
    truth["volume"] = float(solid.Volume())
    faces = solid.Faces()
    return ReferencePart(name=name, title=title, shape=solid, truth=truth, face_types=tuple(face.geomType() for face in faces))


# -- the scan simulator ----------------------------------------------------------------


def scan_from_part(
    part: ReferencePart,
    *,
    edge_length: float = 0.8,
    noise_sigma: float = 0.02,
    holes: int = 2,
    hole_radius: float = 2.5,
    seed: int = 0,
    tessellation_tolerance: float = 0.005,
) -> ScanMesh:
    """A scan-like mesh of ``part``: dense, noisy along the normals, with a few holes.

    ``edge_length`` is the scanner's point spacing (mm), ``noise_sigma`` the standard
    deviation of the normal noise (mm). Deterministic for a given ``seed``.
    """

    import trimesh

    vertices, triangles, labels = _tessellate_by_face(part.shape, tessellation_tolerance)
    vertices, triangles, labels = _refine(vertices, triangles, labels, edge_length)
    mesh = trimesh.Trimesh(vertices=vertices, faces=triangles, process=False)
    mesh.merge_vertices(digits_vertex=6)  # one surface: neighbouring faces share their edge points
    vertices = np.asarray(mesh.vertices, dtype=float)
    triangles = np.asarray(mesh.faces, dtype=np.int64)

    rng = np.random.default_rng(seed)
    clean_vertices = vertices.copy()
    if noise_sigma > 0.0:
        normals = _vertex_normals(vertices, triangles)
        vertices = vertices + normals * rng.normal(0.0, noise_sigma, size=(len(vertices), 1))
    keep = np.ones(len(triangles), dtype=bool)
    if holes > 0 and len(triangles):
        centroids = clean_vertices[triangles].mean(axis=1)
        for center_index in rng.choice(len(triangles), size=min(holes, len(triangles)), replace=False):
            keep &= np.linalg.norm(centroids - centroids[center_index], axis=1) > hole_radius
    triangles, labels = triangles[keep], labels[keep]
    used = np.unique(triangles)
    remap = np.full(len(vertices), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    return ScanMesh(
        part=part,
        vertices=vertices[used],
        triangles=remap[triangles],
        face_labels=labels,
        noise_sigma=float(noise_sigma),
        seed=int(seed),
        metadata={"edge_length": edge_length, "holes": holes, "hole_radius": hole_radius},
    )


def _tessellate_by_face(shape: object, tolerance: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    all_vertices: list[np.ndarray] = []
    all_triangles: list[np.ndarray] = []
    all_labels: list[np.ndarray] = []
    offset = 0
    for index, face in enumerate(shape.Faces()):  # type: ignore[attr-defined]
        points, faces = face.tessellate(tolerance, 0.1)
        if not faces:
            continue
        vertices = np.array([point.toTuple() for point in points], dtype=float)
        triangles = np.array(faces, dtype=np.int64)
        all_vertices.append(vertices)
        all_triangles.append(triangles + offset)
        all_labels.append(np.full(len(triangles), index, dtype=np.int64))
        offset += len(vertices)
    return np.vstack(all_vertices), np.vstack(all_triangles), np.concatenate(all_labels)


def _refine(vertices: np.ndarray, triangles: np.ndarray, labels: np.ndarray, edge_length: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Split triangles until no edge is longer than ``edge_length`` (scanner point spacing)."""

    import trimesh.remesh

    refined_vertices, refined_triangles, index = trimesh.remesh.subdivide_to_size(
        vertices, triangles, max_edge=edge_length, max_iter=30, return_index=True
    )
    return np.asarray(refined_vertices, dtype=float), np.asarray(refined_triangles, dtype=np.int64), labels[np.asarray(index)]


def _vertex_normals(vertices: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    corners = vertices[triangles]
    face_normals = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])  # area weighted
    normals = np.zeros_like(vertices)
    for column in range(3):
        np.add.at(normals, triangles[:, column], face_normals)
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    return normals / np.maximum(lengths, 1e-12)


def distance_to_reference(points: np.ndarray, part: ReferencePart, *, tolerance: float = 0.001) -> np.ndarray:
    """Unsigned distance from each point to the reference part's surface (mm)."""

    from openretop.mesh.spatial_index import MeshSpatialIndex
    from openretop.mesh.triangle_mesh import TriangleMeshData

    vertices, triangles, _labels = _tessellate_by_face(part.shape, tolerance)
    index = MeshSpatialIndex.from_mesh(TriangleMeshData(vertices=vertices, triangles=triangles))
    result = index.query_closest_points(np.asarray(points, dtype=float).reshape(-1, 3))
    return np.asarray(result.distances, dtype=float)


__all__ = (
    "BENCHMARKS",
    "ReferencePart",
    "ScanMesh",
    "bracket",
    "casting",
    "distance_to_reference",
    "housing",
    "knob",
    "make_part",
    "scan_from_part",
    "shaft",
)
