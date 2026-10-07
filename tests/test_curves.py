from __future__ import annotations

import unittest

import numpy as np

from openretop.geometry.curves import fit_section_polylines, fit_smooth_polyline


def _circle(radius: float, count: int, closed: bool = True, noise: float = 0.0) -> np.ndarray:
    angles = np.linspace(0.0, 2.0 * np.pi, count, endpoint=False)
    points = np.column_stack([radius * np.cos(angles), radius * np.sin(angles), np.zeros(count)])
    if noise:
        points += np.random.default_rng(1).normal(0.0, noise, points.shape)
    return np.vstack([points, points[:1]]) if closed else points


class CurveFitTests(unittest.TestCase):
    def test_open_curve_keeps_endpoints_and_reports_error_within_tolerance(self) -> None:
        parameter = np.linspace(0.0, 1.0, 200)
        points = np.column_stack([parameter * 30.0, np.sin(parameter * 5.0) * 4.0, parameter * 0.0])

        result = fit_smooth_polyline(points, tolerance=0.01)

        np.testing.assert_allclose(result.fitted_points[0], points[0], atol=1e-9)
        np.testing.assert_allclose(result.fitted_points[-1], points[-1], atol=1e-9)
        self.assertLessEqual(result.max_error, 0.01)
        self.assertGreaterEqual(result.max_error, result.mean_error)
        self.assertFalse(result.is_closed)
        self.assertFalse(np.shares_memory(result.original_points, result.fitted_points))

    def test_fit_does_not_multiply_points(self) -> None:
        points = _circle(10.0, 500)
        result = fit_smooth_polyline(points, tolerance=0.01)
        # Chaikin corner cutting used to double the point count per iteration.
        self.assertLess(len(result.fitted_points), len(points))
        self.assertLessEqual(result.max_error, 0.01)

    def test_closed_curve_stays_closed_and_has_no_seam_kink(self) -> None:
        result = fit_smooth_polyline(_circle(10.0, 200), tolerance=0.005)

        self.assertTrue(result.is_closed)
        np.testing.assert_allclose(result.fitted_points[0], result.fitted_points[-1], atol=1e-9)
        self.assertEqual(len(result.fitted_curve.segments), 1)
        self.assertTrue(result.fitted_curve.segments[0].periodic)
        radii = np.linalg.norm(result.fitted_points[:, :2], axis=1)
        self.assertLess(np.ptp(radii), 0.01)

    def test_tighter_tolerance_uses_more_control_points(self) -> None:
        points = _circle(10.0, 400)
        loose = fit_smooth_polyline(points, tolerance=0.1).fitted_curve.segments[0]
        tight = fit_smooth_polyline(points, tolerance=0.001).fitted_curve.segments[0]
        self.assertLess(len(loose.poles), len(tight.poles))
        self.assertLessEqual(loose.max_error, 0.1)
        self.assertLessEqual(tight.max_error, 0.001)

    def test_sharp_corners_are_preserved_as_separate_segments(self) -> None:
        square = np.array(
            [[0, 0, 0], [20, 0, 0], [20, 20, 0], [0, 20, 0], [0, 0, 0]], dtype=float
        )
        dense = np.vstack(
            [np.linspace(a, b, 40, endpoint=False) for a, b in zip(square[:-1], square[1:])]
            + [square[:1]]
        )

        result = fit_smooth_polyline(dense, tolerance=0.01)

        self.assertEqual(len(result.fitted_curve.segments), 4)
        self.assertLessEqual(result.max_error, 0.01)
        for corner in square[:-1]:
            self.assertLess(np.min(np.linalg.norm(result.fitted_points - corner, axis=1)), 1e-6)

    def test_scan_noise_on_a_smooth_curve_is_not_mistaken_for_corners(self) -> None:
        result = fit_smooth_polyline(_circle(10.0, 1500, noise=0.01), tolerance=0.05)
        self.assertEqual(len(result.fitted_curve.segments), 1)
        self.assertLess(len(result.fitted_curve.segments[0].poles), 80)

    def test_degenerate_inputs_do_not_raise(self) -> None:
        single = fit_smooth_polyline(np.array([[1.0, 2.0, 3.0]]))
        self.assertEqual(len(single.fitted_points), 1)
        pair = fit_smooth_polyline(np.array([[0.0, 0, 0], [5.0, 0, 0]]))
        np.testing.assert_allclose(pair.fitted_points[[0, -1]], [[0, 0, 0], [5, 0, 0]])
        repeated = fit_smooth_polyline(np.array([[1.0, 1, 1]] * 4))
        self.assertEqual(repeated.max_error, 0.0)

    def test_section_polyline_wrapper_skips_short_polylines(self) -> None:
        from types import SimpleNamespace

        results = fit_section_polylines(
            [SimpleNamespace(points=_circle(5.0, 60)), SimpleNamespace(points=np.zeros((1, 3)))],
            tolerance=0.01,
        )
        self.assertEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
