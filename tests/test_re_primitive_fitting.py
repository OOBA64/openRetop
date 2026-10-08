"""RE-05: primitives fitted to scan data, scored against the benchmark parts' exact geometry.

Acceptance (RE_PLAN): at 0.02 mm scanner noise, radii within 0.01 mm and axes within
0.05 degrees; never raise on degenerate input.
"""

from __future__ import annotations

import math
import time
import unittest

import numpy as np

try:
    import cadquery  # noqa: F401

    HAVE_CADQUERY = True
except ImportError:  # pragma: no cover
    HAVE_CADQUERY = False

from openretop.fitting import classify_region, fit_cone, fit_cylinder, fit_plane, fit_primitive, fit_sphere, fit_torus

KIND_OF = {"PLANE": "plane", "CYLINDER": "cylinder", "CONE": "cone"}


def _scan(name: str):
    from openretop.benchmarks import make_part, scan_from_part

    part = make_part(name)
    return part, scan_from_part(part, noise_sigma=0.02, seed=1, edge_length=1.0)


@unittest.skipUnless(HAVE_CADQUERY, "CadQuery is not installed")
class BenchmarkFitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bracket = _scan("bracket")
        cls.shaft = _scan("shaft")

    def _faces(self, scan_pair, geom_type):
        from openretop.benchmarks.scoring import face_points

        part, scan = scan_pair
        for index, face_type in enumerate(part.face_types):
            if face_type == geom_type:
                points, normals = face_points(scan, index)
                if len(points) >= 50:
                    yield index, points, normals

    def test_bracket_cylinders_match_the_cad_within_a_hundredth(self) -> None:
        from openretop.benchmarks.scoring import axis_angle_degrees, axis_offset

        part, _scan_ = self.bracket
        found = []
        for _index, points, normals in self._faces(self.bracket, "CYLINDER"):
            fit = fit_cylinder(points, normals)
            self.assertTrue(fit.success, fit.reason)
            truth = min(part.truth["cylinders"], key=lambda c: abs(c["radius"] - fit.params["radius"]))
            self.assertAlmostEqual(fit.params["radius"], truth["radius"], delta=0.01)
            self.assertLess(axis_angle_degrees(fit.params["axis"], truth["axis"]), 0.05)
            self.assertLess(axis_offset(fit.params["point"], fit.params["axis"], truth["point"], truth["axis"]), 0.01)
            self.assertAlmostEqual(fit.rms, 0.02, delta=0.003)  # nothing left but the scanner noise
            found.append(truth["name"])
        self.assertEqual(sorted(found), ["boss", "boss hole", "plate hole"])

    def test_bracket_planes_match_the_cad(self) -> None:
        from openretop.benchmarks.scoring import axis_angle_degrees

        part, _scan_ = self.bracket
        matched = 0
        for _index, points, normals in self._faces(self.bracket, "PLANE"):
            fit = fit_plane(points, normals)
            self.assertTrue(fit.success)
            for truth in part.truth["planes"]:
                if axis_angle_degrees(fit.params["normal"], truth["normal"]) < 0.05:
                    signed = float(np.asarray(truth["normal"]) @ fit.params["point"])
                    if abs(signed - truth["offset"]) < 0.01:
                        matched += 1
        self.assertEqual(matched, len(part.truth["planes"]))

    def test_shaft_cone_and_cylinders(self) -> None:
        from openretop.benchmarks.scoring import axis_angle_degrees

        part, _scan_ = self.shaft
        (_index, points, normals), = list(self._faces(self.shaft, "CONE"))
        cone = fit_cone(points, normals)
        self.assertTrue(cone.success, cone.reason)
        truth = part.truth["cones"][0]
        self.assertAlmostEqual(cone.params["half_angle_degrees"], truth["half_angle_degrees"], delta=0.05)
        self.assertLess(axis_angle_degrees(cone.params["axis"], truth["axis"]), 0.05)
        self.assertAlmostEqual(float(cone.params["apex"][2]), truth["apex_z"], delta=0.05)
        radii = sorted(round(fit_cylinder(p, n).params["radius"], 2) for _i, p, n in self._faces(self.shaft, "CYLINDER"))
        self.assertEqual(radii, [6.0, 8.0, 10.0, 10.0])

    def test_every_benchmark_face_is_classified_as_its_true_type(self) -> None:
        for pair in (self.bracket, self.shaft):
            part, _scan_ = pair
            for geom_type in ("PLANE", "CYLINDER", "CONE"):
                for index, points, normals in self._faces(pair, geom_type):
                    with self.subTest(part=part.name, face=index):
                        kind, fit, _fits = classify_region(points, normals, tolerance=0.05)
                        self.assertEqual(kind, KIND_OF[geom_type])
                        self.assertIsNotNone(fit)


class SyntheticFitTests(unittest.TestCase):
    """Spheres and tori are not in the prismatic benchmarks: noisy partial patches instead."""

    def setUp(self) -> None:
        self.rng = np.random.default_rng(3)

    def _sphere_cap(self, count=8000, radius=25.0, center=(3.0, -2.0, 7.0), cap_degrees=60.0):
        theta = self.rng.uniform(0, math.radians(cap_degrees), count)
        phi = self.rng.uniform(0, 2 * math.pi, count)
        normals = np.c_[np.sin(theta) * np.cos(phi), np.sin(theta) * np.sin(phi), np.cos(theta)]
        points = np.asarray(center) + radius * normals + normals * self.rng.normal(0, 0.02, (count, 1))
        return points, normals

    def _torus_quarter(self, count=8000, major=20.0, minor=4.0):
        u = self.rng.uniform(0, math.pi / 2, count)
        v = self.rng.uniform(0, 2 * math.pi, count)
        normals = np.c_[np.cos(v) * np.cos(u), np.cos(v) * np.sin(u), np.sin(v)]
        points = np.c_[(major + minor * np.cos(v)) * np.cos(u), (major + minor * np.cos(v)) * np.sin(u), minor * np.sin(v)]
        return points + normals * self.rng.normal(0, 0.02, (count, 1)), normals

    def test_a_60_degree_sphere_cap(self) -> None:
        points, normals = self._sphere_cap()
        fit = fit_sphere(points, normals)
        self.assertTrue(fit.success)
        self.assertAlmostEqual(fit.params["radius"], 25.0, delta=0.01)
        np.testing.assert_allclose(fit.params["center"], (3.0, -2.0, 7.0), atol=0.02)

    def test_a_quarter_torus(self) -> None:
        points, normals = self._torus_quarter()
        fit = fit_torus(points, normals)
        self.assertTrue(fit.success, fit.reason)
        self.assertAlmostEqual(fit.params["major_radius"], 20.0, delta=0.01)
        self.assertAlmostEqual(fit.params["minor_radius"], 4.0, delta=0.01)

    def test_classification_of_sphere_and_torus(self) -> None:
        self.assertEqual(classify_region(*self._sphere_cap(), tolerance=0.05)[0], "sphere")
        self.assertEqual(classify_region(*self._torus_quarter(), tolerance=0.05)[0], "torus")

    def test_a_bumpy_patch_is_freeform(self) -> None:
        x, y = np.meshgrid(np.linspace(-20, 20, 60), np.linspace(-20, 20, 60))
        z = 3.0 * np.sin(x / 6.0) * np.cos(y / 5.0)
        points = np.c_[x.ravel(), y.ravel(), z.ravel()]
        self.assertEqual(classify_region(points, None, tolerance=0.05)[0], "freeform")

    def test_outliers_are_ignored(self) -> None:
        points, normals = self._sphere_cap(count=5000)
        spikes = self.rng.choice(len(points), 100, replace=False)
        points[spikes] += normals[spikes] * 3.0  # 2% of the points are 3 mm spikes
        fit = fit_sphere(points, normals)
        self.assertAlmostEqual(fit.params["radius"], 25.0, delta=0.01)
        self.assertLess(fit.inlier_fraction, 0.99)

    def test_degenerate_input_returns_a_reason_instead_of_raising(self) -> None:
        line = np.c_[np.linspace(0, 10, 50), np.zeros(50), np.zeros(50)]
        for kind in ("plane", "sphere", "cylinder", "cone", "torus"):
            with self.subTest(kind=kind):
                for data in (np.zeros((2, 3)), line, np.full((20, 3), np.nan), "nonsense"):
                    fit = fit_primitive(kind, data)
                    self.assertIsInstance(fit.success, bool)
                    if not fit.success:
                        self.assertTrue(fit.reason)
        self.assertFalse(fit_primitive("blob", line).success)

    def test_fits_are_fast_enough_to_feel_instant(self) -> None:
        points, normals = self._sphere_cap(count=40_000)
        started = time.perf_counter()
        fit_sphere(points, normals)
        self.assertLess(time.perf_counter() - started, 1.5)


if __name__ == "__main__":
    unittest.main()
