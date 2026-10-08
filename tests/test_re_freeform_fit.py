"""Freeform B-spline surface fitted to an area of the scan (ExModel "Fit Surface").

Acceptance: the fitted surface follows the true CAD surface to within scan-noise level, curved
areas that fold over any plane are flattened conformally, and the "expand" margin stays close
to the surface's natural continuation instead of swinging away.
"""

from __future__ import annotations

import unittest

import numpy as np

try:
    import cadquery  # noqa: F401

    HAVE_CADQUERY = True
except ImportError:  # pragma: no cover
    HAVE_CADQUERY = False

from openretop.fitting.bspline_surface import (
    auto_fit_bspline_surface,
    basis_functions,
    clamped_uniform_knots,
    fit_bspline_surface,
    fit_grid_surface,
)


def _grid_mesh(count_u: int, count_v: int) -> np.ndarray:
    index = np.arange(count_u * count_v).reshape(count_u, count_v)
    a, b = index[:-1, :-1].ravel(), index[:-1, 1:].ravel()
    c, d = index[1:, :-1].ravel(), index[1:, 1:].ravel()
    return np.r_[np.c_[a, c, d], np.c_[a, d, b]]


class BasisTests(unittest.TestCase):
    def test_basis_and_derivatives_match_scipy(self) -> None:
        from scipy.interpolate import BSpline

        knots = clamped_uniform_knots(9, 3, 0.0, 2.0)
        t = np.linspace(0.0, 2.0, 101)
        span, values, derivative = basis_functions(knots, 3, t, derivatives=True)
        for index in range(9):
            coefficients = np.zeros(9)
            coefficients[index] = 1.0
            reference = BSpline(knots, coefficients, 3)
            mine = np.zeros_like(t)
            mine_derivative = np.zeros_like(t)
            for r in range(4):
                hit = span - 3 + r == index
                mine[hit] = values[hit, r]
                mine_derivative[hit] = derivative[hit, r]
            np.testing.assert_allclose(mine, reference(t), atol=1e-12)
            np.testing.assert_allclose(mine_derivative, reference.derivative()(t), atol=1e-9)


class SyntheticFitTests(unittest.TestCase):
    def test_a_smooth_height_field_is_fitted_through_its_plane(self) -> None:
        x, y = np.meshgrid(np.linspace(-20, 20, 61), np.linspace(-15, 15, 46), indexing="ij")
        z = 3.0 * np.sin(x / 8.0) * np.cos(y / 10.0)
        points = np.c_[x.ravel(), y.ravel(), z.ravel()]
        fit = fit_bspline_surface(points, _grid_mesh(61, 46), control_u=12, control_v=12)
        self.assertTrue(fit.success)
        self.assertEqual(fit.parameterization, "plane")
        self.assertLess(fit.max_error, 0.01)

    def test_a_band_bent_through_150_degrees_is_flattened_conformally(self) -> None:
        # 150 degrees of an R20 cylinder, 30 long: its ends stand steeply on its best-fit
        # plane, so a projection would squeeze them
        angle, height = np.meshgrid(np.linspace(0, np.radians(150), 50), np.linspace(0, 30, 40), indexing="ij")
        points = np.c_[(20 * np.cos(angle)).ravel(), (20 * np.sin(angle)).ravel(), height.ravel()]
        noisy = points + np.random.default_rng(0).normal(0, 0.02, points.shape)
        fit = fit_bspline_surface(noisy, _grid_mesh(50, 40), control_u=8, control_v=6, expand=0.0)
        self.assertEqual(fit.parameterization, "conformal")
        self.assertLess(fit.rms, 0.025)  # the noise level
        clean = fit.distances(points)
        self.assertLess(float(np.sqrt(np.mean(clean**2))), 0.01)

    def test_degenerate_input_is_refused_with_a_reason(self) -> None:
        line = np.c_[np.linspace(0, 10, 200), np.zeros(200), np.zeros(200)]
        fit = fit_bspline_surface(line, control_u=6, control_v=6)
        self.assertFalse(fit.success)
        self.assertTrue(fit.reason)
        few = fit_bspline_surface(np.random.default_rng(0).random((5, 3)))
        self.assertFalse(few.success)

    def test_auto_picks_the_smallest_net_within_tolerance(self) -> None:
        x, y = np.meshgrid(np.linspace(-20, 20, 41), np.linspace(-20, 20, 41), indexing="ij")
        points = np.c_[x.ravel(), y.ravel(), (0.02 * x * y).ravel()]  # bilinear: a 4 x 4 net is exact
        fit = auto_fit_bspline_surface(points, _grid_mesh(41, 41), tolerance=0.01)
        self.assertEqual(fit.control_counts, (4, 4))
        wavy = np.c_[x.ravel(), y.ravel(), (2.0 * np.sin(x / 3.0)).ravel()]
        fit = auto_fit_bspline_surface(wavy, _grid_mesh(41, 41), tolerance=0.01)
        self.assertGreater(fit.control_counts[0], 4)
        self.assertLessEqual(fit.rms, 0.01)

    def test_resampling_a_grid_reproduces_it(self) -> None:
        u = np.linspace(0, 40, 30)
        v = np.linspace(0, 20, 20)
        uu, vv = np.meshgrid(u, v, indexing="ij")
        grid = np.dstack([uu, vv, np.sin(uu / 10.0) * 2.0])
        fit = fit_grid_surface(grid, u, v, control_u=14, control_v=8, smoothness=0.0)
        self.assertLess(fit.max_error, 0.005)


@unittest.skipUnless(HAVE_CADQUERY, "CadQuery is not installed")
class BenchmarkFreeformFitTests(unittest.TestCase):
    """A 100-degree sector of the B4 knob's lofted grip, fitted from a noisy scan."""

    @classmethod
    def setUpClass(cls) -> None:
        from openretop.benchmarks import distance_to_reference, make_part, scan_from_part

        cls.part = make_part("knob")
        scan = scan_from_part(cls.part, noise_sigma=0.02, seed=1, edge_length=1.0)
        grip = int(cls.part.face_types.index("BSPLINE"))
        triangles = np.nonzero(scan.face_labels == grip)[0]
        centers = scan.vertices[scan.triangles[triangles]].mean(axis=1)
        angle = np.degrees(np.arctan2(centers[:, 1], centers[:, 0]))
        chosen = triangles[(angle > -50) & (angle < 50)]
        vertices = np.unique(scan.triangles[chosen])
        local = -np.ones(len(scan.vertices), dtype=np.int64)
        local[vertices] = np.arange(len(vertices))
        cls.points = scan.vertices[vertices]
        cls.triangles = local[scan.triangles[chosen]]
        # vertices on the grip proper (the scanner rounds the grip's sharp top and bottom edges)
        cls.core = distance_to_reference(cls.points, cls.part) < 0.1
        cls.distance_to_reference = staticmethod(distance_to_reference)

    def test_the_fit_follows_the_true_surface(self) -> None:
        fit = fit_bspline_surface(self.points, self.triangles, control_u=16, control_v=16, expand=0.0)
        self.assertTrue(fit.success)
        self.assertEqual(fit.parameterization, "conformal")
        u, v = fit.closest_parameters(self.points[self.core])
        error = self.distance_to_reference(fit.evaluate(u, v), self.part)
        self.assertLess(float(np.sqrt(np.mean(error**2))), 0.02)
        self.assertLess(float(np.percentile(error, 99)), 0.06)

    def test_the_expanded_margin_continues_the_surface(self) -> None:
        fit = fit_bspline_surface(self.points, self.triangles, control_u=12, control_v=12, expand=0.1)
        grid = fit.grid(40, 40).reshape(-1, 3)
        away = self.distance_to_reference(grid, self.part)
        # a straight continuation of a curved grip parts from it slowly; it must not swing
        # away (before the unsupported-pole stiffening: 28 mm)
        self.assertLess(float(np.percentile(away, 90)), 2.5)
        self.assertLess(float(away.max()), 12.0)

    def test_fitting_is_quick(self) -> None:
        import time

        started = time.perf_counter()
        fit_bspline_surface(self.points, self.triangles, control_u=16, control_v=16)
        self.assertLess(time.perf_counter() - started, 2.0)


if __name__ == "__main__":
    unittest.main()
