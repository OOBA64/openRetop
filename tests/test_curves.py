from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from geometry.curves import fit_smooth_polyline


class CurveFitTests(unittest.TestCase):
    def test_open_polyline_is_smoothed_and_keeps_endpoints(self) -> None:
        points = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
            ]
        )

        result = fit_smooth_polyline(points, iterations=2)

        self.assertGreater(len(result.fitted_points), len(points))
        self.assertTrue(np.allclose(result.fitted_points[0], points[0]))
        self.assertTrue(np.allclose(result.fitted_points[-1], points[-1]))
        self.assertGreaterEqual(result.mean_error, 0.0)
        self.assertGreaterEqual(result.max_error, result.mean_error)
        self.assertFalse(np.shares_memory(result.original_points, result.fitted_points))

    def test_closed_polyline_stays_closed(self) -> None:
        points = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
                [0.0, 0.0, 0.0],
            ]
        )

        result = fit_smooth_polyline(points, iterations=1)

        self.assertTrue(result.is_closed)
        self.assertTrue(np.allclose(result.fitted_points[0], result.fitted_points[-1]))


if __name__ == "__main__":
    unittest.main()
