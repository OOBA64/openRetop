"""Surface modelling operations: fit, loft, fill, extend, trim, sew, deviation.

The ExModel workflow end to end on known geometry: oversize patches are split by each other,
the pieces lying on the scan are kept, and they sew into a closed solid of the right volume.
"""

from __future__ import annotations

import unittest

import numpy as np

try:
    import cadquery  # noqa: F401
    import OCP  # noqa: F401

    HAVE_KERNEL = True
except ImportError:  # pragma: no cover
    HAVE_KERNEL = False


def _saddle(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    return (x**2 - y**2) / 40.0


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class FaceConstructionTests(unittest.TestCase):
    def setUp(self) -> None:
        from openretop.cad_kernel import surfacing

        self.s = surfacing

    def test_a_fitted_surface_becomes_an_identical_occ_face(self) -> None:
        from openretop.fitting.bspline_surface import fit_bspline_surface

        x, y = np.meshgrid(np.linspace(-20, 20, 41), np.linspace(-15, 15, 31), indexing="ij")
        points = np.c_[x.ravel(), y.ravel(), (3 * np.sin(x / 8) * np.cos(y / 10)).ravel()]
        fit = fit_bspline_surface(points, control_u=10, control_v=10)
        face = self.s.bspline_face(fit)
        samples = fit.grid(12, 12).reshape(-1, 3)
        self.assertLess(float(np.abs(self.s.signed_distances(face, samples, deflection=0.001)).max()), 0.002)
        back = self.s.from_brep(self.s.to_brep(face))
        self.assertAlmostEqual(self.s.face_area(back), self.s.face_area(face), places=6)

    def test_loft_through_two_arcs_is_the_cylinder_band(self) -> None:
        angle = np.linspace(0, np.pi, 40)
        bottom = np.c_[20 * np.cos(angle), 20 * np.sin(angle), np.zeros(40)]
        top = np.c_[20 * np.cos(angle), 20 * np.sin(angle), np.full(40, 30.0)][::-1]  # drawn the other way
        face = self.s.loft_surface([bottom, top])
        self.assertAlmostEqual(self.s.face_area(face), np.pi * 20 * 30, delta=0.5)

    def test_fill_four_curves_on_scan_data(self) -> None:
        s = np.linspace(-10, 10, 30)
        sides = [
            np.c_[s, np.full(30, -10.0), _saddle(s, -10.0)],
            np.c_[np.full(30, 10.0), s, _saddle(10.0, s)],
            np.c_[s, np.full(30, 10.0), _saddle(s, 10.0)],  # head-to-tail order is not required
            np.c_[np.full(30, -10.0), s, _saddle(-10.0, s)],
        ]
        inside = np.random.default_rng(0).uniform(-9, 9, (300, 2))
        scan = np.c_[inside, _saddle(inside[:, 0], inside[:, 1])]
        face = self.s.fill_surface([self.s.FillBoundary(points=side) for side in sides], scan_points=scan)
        self.assertLess(float(np.abs(self.s.signed_distances(face, scan, deflection=0.002)).max()), 0.01)

    def test_fill_is_tangent_to_a_smooth_neighbour(self) -> None:
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace
        from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

        # neighbour: the plane z = 0 for x < 0; the fill spans x 0..20, its x = 0 side smooth
        neighbour = BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), -20.0, 0.0, -10.0, 10.0).Face()
        shared = BRepBuilderAPI_MakeEdge(gp_Pnt(0, -10, 0), gp_Pnt(0, 10, 0)).Edge()
        t = np.linspace(-10, 10, 20)
        x = np.linspace(0, 20, 20)
        far = np.c_[np.full(20, 20.0), t, np.full(20, 6.0)]
        rise = 6.0 * (x / 20.0) ** 2
        sides = [
            self.s.FillBoundary(edge=shared, support_face=neighbour, continuity="smooth"),
            self.s.FillBoundary(points=np.c_[x, np.full(20, 10.0), rise]),
            self.s.FillBoundary(points=far),
            self.s.FillBoundary(points=np.c_[x, np.full(20, -10.0), rise]),
        ]
        face = self.s.fill_surface(sides)
        adaptor = BRepAdaptor_Surface(face)
        from OCP.BRep import BRep_Tool
        from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf

        projector = GeomAPI_ProjectPointOnSurf(gp_Pnt(0.01, 0.0, 0.0), BRep_Tool.Surface_s(face))
        u, v = projector.LowerDistanceParameters()
        from OCP.BRepLProp import BRepLProp_SLProps

        normal = BRepLProp_SLProps(adaptor, u, v, 1, 1e-6).Normal()
        self.assertGreater(abs(normal.Z()), np.cos(np.radians(1.0)))  # tangent to the plane

    def test_extend_grows_a_face_straight_on(self) -> None:
        angle = np.linspace(0, np.pi / 2, 40)
        face = self.s.loft_surface(
            [np.c_[20 * np.cos(angle), 20 * np.sin(angle), np.zeros(40)], np.c_[20 * np.cos(angle), 20 * np.sin(angle), np.full(40, 30.0)]]
        )
        grown = self.s.extend_face(face, 5.0)
        # quarter band 31.4 x 30 grows by 5 on each side, flat beyond the arc ends
        self.assertAlmostEqual(self.s.face_area(grown), (np.pi / 2 * 20 + 10) * 40, delta=2.0)
        plane = self.s.primitive_patch(_plane_fit(), np.array([[0, 0, 0], [10, 10, 0]]))
        self.assertGreater(self.s.face_area(self.s.extend_face(plane, 3.0)), self.s.face_area(plane))


def _plane_fit():
    from openretop.fitting import PrimitiveFit

    return PrimitiveFit("plane", True, {"normal": np.array([0.0, 0.0, 1.0]), "point": np.zeros(3), "offset": 0.0}, rms=0.0)


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class TrimAndSewTests(unittest.TestCase):
    """B1 bracket: a primitive per true face, oversized, split by each other, trimmed to the
    scan and sewn: one closed solid of the CAD's volume."""

    def test_the_bracket_trims_and_sews_into_its_solid(self) -> None:
        from OCP.BRepCheck import BRepCheck_Analyzer

        from openretop.benchmarks import make_part, scan_from_part
        from openretop.benchmarks.scoring import vertex_normals
        from openretop.cad_kernel import surfacing
        from openretop.fitting import fit_primitive

        part = make_part("bracket")
        scan = scan_from_part(part, noise_sigma=0.02, seed=1, edge_length=1.0)
        normals = vertex_normals(scan.vertices, scan.triangles)
        kinds = {"PLANE": "plane", "CYLINDER": "cylinder", "CONE": "cone"}
        patches = []
        for face, geom_type in enumerate(part.face_types):
            vertices = np.unique(scan.triangles[scan.face_labels == face])
            fit = fit_primitive(kinds[geom_type], scan.vertices[vertices], normals[vertices])
            self.assertTrue(fit.success, fit.reason)
            patches.append(surfacing.primitive_patch(fit, scan.vertices[vertices], expand=0.3))
        pieces = surfacing.split_faces(patches)
        self.assertGreater(len(pieces), len(patches))
        surfacing.mark_pieces_on_scan(pieces, scan.vertices, normals, tolerance=0.1)
        result = surfacing.sew([piece.face for piece in pieces if piece.keep], tolerance=0.05)
        self.assertTrue(result.solid, result.warnings)
        self.assertTrue(BRepCheck_Analyzer(result.shape).IsValid())
        self.assertLess(abs(result.volume - part.truth["volume"]) / part.truth["volume"], 0.002)

    def test_open_surfaces_sew_into_a_shell_and_report_open_edges(self) -> None:
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
        from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

        from openretop.cad_kernel import surfacing

        a = BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 0.0, 10.0, 0.0, 10.0).Face()
        b = BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(10, 0, 0), gp_Dir(1, 0, 0)), 0.0, 10.0, 0.0, 10.0).Face()
        result = surfacing.sew([a, b])
        self.assertFalse(result.solid)
        self.assertGreater(result.free_edges, 0)
        self.assertTrue(result.warnings)


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class PlanePatchTests(unittest.TestCase):
    """H-03: a fitted plane is a rectangle along the face's outline, not a big square."""

    def _corners(self, face: object) -> np.ndarray:
        from OCP.BRep import BRep_Tool
        from OCP.TopAbs import TopAbs_VERTEX
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS

        corners = []
        explorer = TopExp_Explorer(face, TopAbs_VERTEX)
        while explorer.More():
            point = BRep_Tool.Pnt_s(TopoDS.Vertex_s(explorer.Current()))
            corners.append((point.X(), point.Y(), point.Z()))
            explorer.Next()
        corners = np.unique(np.round(corners, 6), axis=0)
        # in order around the rectangle (angle about the centre, in the plane)
        centred = corners - corners.mean(axis=0)
        _, _, axes = np.linalg.svd(centred)
        angles = np.arctan2(centred @ axes[1], centred @ axes[0])
        return corners[np.argsort(angles)]

    def test_a_long_narrow_face_gets_a_rectangle_along_its_edges(self) -> None:
        from openretop.cad_kernel import surfacing

        # a 100 x 10 face turned 30 degrees in a tilted plane, sampled like a scan
        rng = np.random.default_rng(3)
        turn = np.radians(30.0)
        u = np.array([np.cos(turn), np.sin(turn), 0.0])
        v = np.array([-np.sin(turn), np.cos(turn), 0.0])
        tilt = np.radians(20.0)
        rotation = np.array([[1, 0, 0], [0, np.cos(tilt), -np.sin(tilt)], [0, np.sin(tilt), np.cos(tilt)]])
        uv = rng.uniform([0.0, 0.0], [100.0, 10.0], size=(2000, 2))
        points = (uv[:, :1] * u + uv[:, 1:] * v) @ rotation.T + np.array([5.0, -7.0, 12.0])
        normal = rotation @ np.array([0.0, 0.0, 1.0])
        face = surfacing.primitive_patch(
            _plane_fit_through(normal, points[0]), points, expand=0.15
        )
        corners = self._corners(face)
        self.assertEqual(len(corners), 4)
        sides = np.linalg.norm(np.roll(corners, -1, axis=0) - corners, axis=1)
        edges = sorted({round(float(side), 0) for side in sides})
        # 100 x 10 plus 15 (15% of the long side) on every side
        self.assertAlmostEqual(surfacing.face_area(face), 130.0 * 40.0, delta=130.0 * 40.0 * 0.01)
        self.assertTrue(any(abs(edge - 130.0) < 1.0 for edge in edges), edges)
        # the long sides run along the face's long edges
        long_direction = rotation @ u
        directions = [step / np.linalg.norm(step) for step in np.roll(corners, -1, axis=0) - corners]
        best = max(abs(float(direction @ long_direction)) for direction in directions)
        self.assertGreater(best, np.cos(np.radians(1.0)))
        # on the plane, through the data
        np.testing.assert_allclose((corners - points[0]) @ normal, 0.0, atol=1e-6)

    def test_the_old_size_was_far_larger(self) -> None:
        from openretop.cad_kernel import surfacing

        points = np.array([[x, y, 0.0] for x in np.linspace(0, 100, 21) for y in np.linspace(0, 10, 5)])
        face = surfacing.primitive_patch(_plane_fit(), points, expand=0.15)
        self.assertLess(surfacing.face_area(face), 0.35 * (1.3 * float(np.hypot(100, 10))) ** 2)


def _plane_fit_through(normal: np.ndarray, point: np.ndarray):
    from openretop.fitting import PrimitiveFit

    normal = np.asarray(normal, dtype=float) / np.linalg.norm(normal)
    return PrimitiveFit("plane", True, {"normal": normal, "point": np.asarray(point, dtype=float), "offset": float(normal @ point)}, rms=0.0)


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class DeviationTests(unittest.TestCase):
    def test_signed_distance_to_a_plane_face(self) -> None:
        from openretop.cad_kernel import surfacing

        face = surfacing.primitive_patch(_plane_fit(), np.array([[-10, -10, 0], [10, -10, 0], [10, 10, 0], [-10, 10, 0]]))
        points = np.array([[0.0, 0.0, 0.5], [1.0, 2.0, -0.25], [3.0, -4.0, 0.0]])
        np.testing.assert_allclose(surfacing.signed_distances(face, points), [0.5, -0.25, 0.0], atol=1e-6)


if __name__ == "__main__":
    unittest.main()
