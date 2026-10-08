"""RE-08: a closed CAD solid from fitted primitives and the scan.

Acceptance (RE_PLAN): B1 becomes one valid closed solid with its volume within 0.5% of the
reference.
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

from openretop.fitting import PrimitiveFit


def _plane(normal, point) -> PrimitiveFit:
    normal = np.asarray(normal, dtype=float)
    return PrimitiveFit("plane", True, {"normal": normal, "point": np.asarray(point, dtype=float), "offset": float(normal @ point)}, rms=0.0)


def _cylinder(axis, point, radius) -> PrimitiveFit:
    return PrimitiveFit("cylinder", True, {"axis": np.asarray(axis, dtype=float), "point": np.asarray(point, dtype=float), "radius": radius}, rms=0.0)


def _box_with_hole_scan():
    """Points and outward normals sampled on a 40 x 30 x 10 block with a R5 through hole."""

    rng = np.random.default_rng(0)
    points, normals = [], []
    for axis, extent in ((0, 20.0), (1, 15.0), (2, 5.0)):
        for sign in (-1.0, 1.0):
            sample = rng.uniform([-20, -15, -5], [20, 15, 5], size=(1500, 3))
            sample[:, axis] = sign * extent
            if axis == 2:
                sample = sample[np.hypot(sample[:, 0], sample[:, 1]) > 5.0]
            normal = np.zeros(3)
            normal[axis] = sign
            points.append(sample)
            normals.append(np.tile(normal, (len(sample), 1)))
    angle = rng.uniform(0, 2 * np.pi, 1500)
    hole = np.c_[5 * np.cos(angle), 5 * np.sin(angle), rng.uniform(-5, 5, 1500)]
    points.append(hole)
    normals.append(-np.c_[np.cos(angle), np.sin(angle), np.zeros(1500)])  # into the hole: away from material
    return np.vstack(points), np.vstack(normals)


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class PrimitiveSolidTests(unittest.TestCase):
    def setUp(self) -> None:
        from openretop.cad_kernel.primitive_solid import solid_from_primitives

        self.build = solid_from_primitives
        self.fits = [
            _plane((1, 0, 0), (20, 0, 0)),
            _plane((-1, 0, 0), (-20, 0, 0)),
            _plane((0, 1, 0), (0, 15, 0)),
            _plane((0, -1, 0), (0, -15, 0)),
            _plane((0, 0, 1), (0, 0, 5)),
            _plane((0, 0, -1), (0, 0, -5)),
            _cylinder((0, 0, 1), (0, 0, 0), 5.0),
        ]

    def test_exact_primitives_give_the_exact_solid(self) -> None:
        points, normals = _box_with_hole_scan()
        result = self.build(self.fits, points, normals)
        self.assertTrue(result.success, result.reason)
        self.assertEqual(result.solid_count, 1)
        self.assertAlmostEqual(result.volume, 40 * 30 * 10 - np.pi * 25 * 10, delta=0.01)
        self.assertEqual(result.face_count, 7)  # 6 sides + the hole, extended faces trimmed away
        from OCP.BRepCheck import BRepCheck_Analyzer

        self.assertTrue(BRepCheck_Analyzer(result.shape).IsValid())

    def test_inward_facing_scan_normals_are_detected(self) -> None:
        points, normals = _box_with_hole_scan()
        result = self.build(self.fits, points, -normals)
        self.assertTrue(result.success)
        self.assertAlmostEqual(result.volume, 40 * 30 * 10 - np.pi * 25 * 10, delta=0.01)
        self.assertTrue(any("inwards" in warning for warning in result.warnings))

    def test_too_little_input_is_refused_with_a_reason(self) -> None:
        points, normals = _box_with_hole_scan()
        result = self.build(self.fits[:1], points, normals)
        self.assertFalse(result.success)
        self.assertTrue(result.reason)

    def test_the_result_exports_to_step(self) -> None:
        import tempfile
        from pathlib import Path

        import cadquery as cq

        points, normals = _box_with_hole_scan()
        result = self.build(self.fits, points, normals)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "block.step"
            cq.exporters.export(cq.Workplane().add(result.cadquery_shape()), str(path))
            back = cq.importers.importStep(str(path)).val()
            self.assertAlmostEqual(back.Volume(), result.volume, delta=0.01)


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class BracketRoundTripTests(unittest.TestCase):
    """Scan of B1 -> segmentation -> primitives -> solid, compared with the original CAD."""

    def test_the_bracket_comes_back_as_one_valid_solid_of_the_right_volume(self) -> None:
        from OCP.BRepCheck import BRepCheck_Analyzer

        from openretop.benchmarks import distance_to_reference, make_part, scan_from_part
        from openretop.benchmarks.scoring import vertex_normals
        from openretop.cad_kernel.primitive_solid import solid_from_primitives
        from openretop.segmentation import segment_mesh

        part = make_part("bracket")
        scan = scan_from_part(part, noise_sigma=0.02, seed=1, edge_length=1.0)
        segments = segment_mesh(scan.vertices, scan.triangles).segments
        fits = [s.fit for s in segments if s.fit is not None and s.triangle_count >= 30 and not s.edge_band and s.kind != "torus"]
        result = solid_from_primitives(fits, scan.vertices, vertex_normals(scan.vertices, scan.triangles))
        self.assertTrue(result.success, result.reason)
        self.assertEqual(result.solid_count, 1)
        self.assertTrue(BRepCheck_Analyzer(result.shape).IsValid())
        self.assertLess(abs(result.volume - part.truth["volume"]) / part.truth["volume"], 0.005)
        surface_points, _faces = result.cadquery_shape().tessellate(0.01, 0.1)
        distance = distance_to_reference(np.array([p.toTuple() for p in surface_points]), part)
        self.assertLess(float(np.sqrt(np.mean(distance**2))), 0.1)


if __name__ == "__main__":
    unittest.main()
