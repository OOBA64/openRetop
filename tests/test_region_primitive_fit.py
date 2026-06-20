from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mesh.triangle_mesh import TriangleMeshData
from regions.primitive_fit import (
    fit_plane_to_region,
    project_region_boundary_to_plane,
    region_plane_fit_error_summary,
)
from regions.region_state import RegionSelection


def _region(*triangle_indices: int) -> RegionSelection:
    return RegionSelection(
        id="region-fit",
        name="Plane Patch",
        triangle_indices=tuple(triangle_indices),
        source_mesh_name="scan.stl",
    )


def _quad_mesh(*, noise: float = 0.0) -> TriangleMeshData:
    return TriangleMeshData(
        vertices=np.asarray(
            [
                [0.0, 0.0, 0.0],
                [2.0, 0.0, noise],
                [2.0, 1.0, 0.0],
                [0.0, 1.0, -noise],
            ],
            dtype=float,
        ),
        triangles=np.asarray([[0, 1, 2], [0, 2, 3]], dtype=int),
    )


class RegionPlaneFitTests(unittest.TestCase):
    def test_planar_region_fits_successfully(self) -> None:
        fit = fit_plane_to_region(_quad_mesh(), _region(0, 1))

        self.assertTrue(fit.success)
        np.testing.assert_allclose(fit.origin, [1.0, 0.5, 0.0])
        self.assertAlmostEqual(fit.rms_error, 0.0)
        self.assertAlmostEqual(fit.max_error, 0.0)
        self.assertEqual(fit.sample_count, 4)
        self.assertEqual(fit.triangle_count, 2)
        self.assertEqual(fit.region_id, "region-fit")

    def test_noisy_planar_region_reports_error_without_failing(self) -> None:
        fit = fit_plane_to_region(_quad_mesh(noise=0.08), _region(0, 1))

        self.assertTrue(fit.success)
        self.assertGreater(fit.rms_error, 0.0)
        self.assertGreaterEqual(fit.max_error, fit.rms_error)

    def test_invalid_triangle_indices_are_ignored(self) -> None:
        fit = fit_plane_to_region(_quad_mesh(), _region(-1, 0, 99, 1))

        self.assertTrue(fit.success)
        self.assertEqual(fit.triangle_count, 2)
        self.assertEqual(fit.metadata["invalid_triangle_count"], 2)

    def test_empty_region_fails_clearly(self) -> None:
        fit = fit_plane_to_region(_quad_mesh(), _region())

        self.assertFalse(fit.success)
        self.assertIn("no valid triangles", fit.reason.lower())

    def test_collinear_region_fails_as_degenerate(self) -> None:
        mesh = TriangleMeshData(
            vertices=np.asarray(
                [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
                dtype=float,
            ),
            triangles=np.asarray([[0, 1, 2]], dtype=int),
        )

        fit = fit_plane_to_region(mesh, _region(0))

        self.assertFalse(fit.success)
        self.assertIn("degenerate", fit.reason.lower())

    def test_plane_basis_is_orthonormal(self) -> None:
        fit = fit_plane_to_region(_quad_mesh(noise=0.02), _region(0, 1))

        self.assertTrue(fit.success)
        self.assertAlmostEqual(float(np.linalg.norm(fit.normal)), 1.0)
        self.assertAlmostEqual(float(np.linalg.norm(fit.u_axis)), 1.0)
        self.assertAlmostEqual(float(np.linalg.norm(fit.v_axis)), 1.0)
        self.assertAlmostEqual(float(np.dot(fit.normal, fit.u_axis)), 0.0)
        self.assertAlmostEqual(float(np.dot(fit.normal, fit.v_axis)), 0.0)
        self.assertAlmostEqual(float(np.dot(fit.u_axis, fit.v_axis)), 0.0)

    def test_boundary_projection_preserves_order_and_flattens_points(self) -> None:
        fit = fit_plane_to_region(_quad_mesh(), _region(0, 1))
        points = np.asarray(
            [
                [0.0, 0.0, 0.5],
                [2.0, 0.0, -0.25],
                [2.0, 1.0, 0.75],
                [0.0, 1.0, -1.0],
            ],
            dtype=float,
        )

        projected = project_region_boundary_to_plane(points, fit)

        self.assertEqual(projected.shape, points.shape)
        np.testing.assert_allclose(projected[:, :2], points[:, :2])
        self.assertTrue(np.all(np.isfinite(projected)))
        distances = (projected - fit.origin) @ fit.normal
        np.testing.assert_allclose(distances, 0.0, atol=1e-12)

    def test_error_summary_is_specific(self) -> None:
        fit = fit_plane_to_region(_quad_mesh(noise=0.08), _region(0, 1))

        summary = region_plane_fit_error_summary(fit)

        self.assertIn("Plane fit: RMS", summary)
        self.assertIn("Max", summary)
        self.assertIn("model units", summary)


if __name__ == "__main__":
    unittest.main()
