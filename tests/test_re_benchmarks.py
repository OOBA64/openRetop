"""RE-01: reference parts and the scan simulator that every reverse-engineering tool is scored on."""

from __future__ import annotations

import unittest

import numpy as np

try:
    import cadquery  # noqa: F401

    HAVE_CADQUERY = True
except ImportError:  # pragma: no cover - the CAD workflows need it; CI installs it
    HAVE_CADQUERY = False

from openretop.benchmarks import BENCHMARKS, distance_to_reference, make_part, scan_from_part

FAST = {"edge_length": 2.0}  # coarse point spacing keeps the suite quick; the maths is the same


@unittest.skipUnless(HAVE_CADQUERY, "CadQuery is not installed")
class ReferencePartTests(unittest.TestCase):
    def test_every_benchmark_builds_a_valid_solid_with_truth(self) -> None:
        for name in BENCHMARKS:
            with self.subTest(part=name):
                part = make_part(name)
                self.assertTrue(part.shape.isValid())
                self.assertGreater(part.truth["volume"], 0.0)
                self.assertEqual(len(part.face_types), len(part.shape.Faces()))

    def test_the_parts_cover_the_feature_types_the_tools_must_handle(self) -> None:
        types = {name: set(make_part(name).face_types) for name in BENCHMARKS}
        self.assertEqual(types["bracket"], {"PLANE", "CYLINDER"})
        self.assertIn("CONE", types["shaft"])
        self.assertIn("BSPLINE", types["knob"])
        self.assertIn("BSPLINE", types["casting"])

    def test_bracket_truth_matches_the_geometry(self) -> None:
        part = make_part("bracket")
        radii = sorted(cylinder["radius"] for cylinder in part.truth["cylinders"])
        self.assertEqual(radii, [4.0, 5.0, 12.0])
        # 80 x 50 x 10 plate (2 mm chamfers) + R12 x 15 boss - R5 and R4 through holes
        plate = 80 * 50 * 10 - 4 * (2.0 * 2.0 / 2.0) * 10
        expected = plate + math_pi() * 12.0**2 * 15.0 - math_pi() * 5.0**2 * 25.0 - math_pi() * 4.0**2 * 10.0
        self.assertAlmostEqual(part.truth["volume"], expected, delta=0.5)

    def test_unknown_parts_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            make_part("teapot")


@unittest.skipUnless(HAVE_CADQUERY, "CadQuery is not installed")
class ScanSimulatorTests(unittest.TestCase):
    def test_the_same_seed_gives_the_same_scan(self) -> None:
        part = make_part("shaft")
        first = scan_from_part(part, seed=7, **FAST)
        second = scan_from_part(part, seed=7, **FAST)
        np.testing.assert_array_equal(first.vertices, second.vertices)
        np.testing.assert_array_equal(first.triangles, second.triangles)
        other = scan_from_part(part, seed=8, **FAST)
        self.assertFalse(np.array_equal(first.vertices, other.vertices[: len(first.vertices)]) and len(first.vertices) == len(other.vertices))

    def test_noise_has_the_requested_size(self) -> None:
        part = make_part("shaft")
        for sigma in (0.0, 0.02, 0.05):
            with self.subTest(sigma=sigma):
                scan = scan_from_part(part, noise_sigma=sigma, holes=0, seed=1, **FAST)
                distance = distance_to_reference(scan.vertices, part)
                rms = float(np.sqrt(np.mean(distance**2)))
                self.assertAlmostEqual(rms, sigma, delta=0.003 + 0.08 * sigma)

    def test_every_triangle_knows_its_reference_face(self) -> None:
        part = make_part("bracket")
        scan = scan_from_part(part, seed=2, **FAST)
        self.assertEqual(len(scan.face_labels), scan.triangle_count)
        self.assertEqual(set(np.unique(scan.face_labels)), set(range(len(part.face_types))))
        # triangles labelled CYLINDER lie on one of the three cylinders
        cylinder_triangles = scan.triangles_of_type("CYLINDER")
        centroids = scan.vertices[scan.triangles[cylinder_triangles]].mean(axis=1)
        radial = np.minimum.reduce(
            [np.abs(np.hypot(centroids[:, 0] - c["point"][0], centroids[:, 1] - c["point"][1]) - c["radius"]) for c in part.truth["cylinders"]]
        )
        self.assertLess(float(np.percentile(radial, 99)), 0.15)

    def test_holes_are_punched_and_the_mesh_stays_a_single_surface(self) -> None:
        part = make_part("housing")
        closed = scan_from_part(part, holes=0, noise_sigma=0.0, seed=3, **FAST)
        holed = scan_from_part(part, holes=3, noise_sigma=0.0, seed=3, **FAST)
        self.assertLess(holed.triangle_count, closed.triangle_count)
        self.assertEqual(_boundary_edge_count(closed.triangles), 0)  # welded and watertight
        self.assertGreater(_boundary_edge_count(holed.triangles), 0)

    def test_point_spacing_follows_the_scanner_resolution(self) -> None:
        scan = scan_from_part(make_part("shaft"), edge_length=1.0, noise_sigma=0.0, holes=0)
        corners = scan.vertices[scan.triangles]
        edges = np.linalg.norm(corners - np.roll(corners, 1, axis=1), axis=2)
        self.assertLessEqual(float(edges.max()), 1.0 + 1e-6)


def _boundary_edge_count(triangles: np.ndarray) -> int:
    edges = np.sort(triangles[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), axis=1)
    _unique, counts = np.unique(edges, axis=0, return_counts=True)
    return int(np.sum(counts == 1))


def math_pi() -> float:
    import math

    return math.pi


if __name__ == "__main__":
    unittest.main()
