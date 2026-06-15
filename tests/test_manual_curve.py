from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from curves.curve_state import StoredCurve
from curves.manual_curve import (
    DEFAULT_MANUAL_CURVE_METHOD,
    DEFAULT_MANUAL_CURVE_SAMPLE_COUNT,
    MANUAL_CURVE_METHOD_CATMULL_ROM,
    MANUAL_CURVE_METHOD_POLYLINE,
    build_manual_stored_curve,
    ensure_manual_curve_storage,
    is_manual_curve_like,
    manual_curve_metadata,
    sample_manual_curve,
    should_snap_closed_to_first_point,
)


class ManualCurveHelperTests(unittest.TestCase):
    def test_polyline_sampling_preserves_control_points_and_optional_closure(self) -> None:
        points = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
            ],
            dtype=float,
        )

        open_points = sample_manual_curve(
            points,
            is_closed=False,
            method=MANUAL_CURVE_METHOD_POLYLINE,
            sample_count=8,
        )
        closed_points = sample_manual_curve(
            points,
            is_closed=True,
            method=MANUAL_CURVE_METHOD_POLYLINE,
            sample_count=8,
        )

        self.assertTrue(np.allclose(open_points, points))
        self.assertEqual(len(closed_points), 4)
        self.assertTrue(np.allclose(closed_points[:3], points))
        self.assertTrue(np.allclose(closed_points[0], closed_points[-1]))

    def test_catmull_rom_sampling_creates_smooth_curve_and_preserves_endpoints(self) -> None:
        points = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
                [2.0, 1.0, 0.0],
            ],
            dtype=float,
        )

        sampled = sample_manual_curve(
            points,
            is_closed=False,
            method=MANUAL_CURVE_METHOD_CATMULL_ROM,
            sample_count=32,
        )

        self.assertGreater(len(sampled), len(points))
        self.assertTrue(np.allclose(sampled[0], points[0]))
        self.assertTrue(np.allclose(sampled[-1], points[-1]))
        self.assertFalse(np.allclose(sampled[: len(points)], points))

    def test_catmull_rom_closed_sampling_wraps_back_to_first_point(self) -> None:
        points = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
            ],
            dtype=float,
        )

        sampled = sample_manual_curve(
            points,
            is_closed=True,
            method=DEFAULT_MANUAL_CURVE_METHOD,
            sample_count=24,
        )

        self.assertGreater(len(sampled), len(points))
        self.assertTrue(np.allclose(sampled[0], sampled[-1]))

    def test_build_manual_curve_keeps_controls_and_stores_smooth_result(self) -> None:
        points = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
            ],
            dtype=float,
        )

        curve = build_manual_stored_curve(
            curve_id="curve-1",
            name="Manual Curve 1",
            control_points=points,
            is_closed=True,
            creation_type="manual",
            snap_to_mesh=False,
            work_plane_type="section_plane",
            source_section_plane_id="plane-1",
        )

        self.assertTrue(np.allclose(curve.original_points, points))
        self.assertGreater(len(curve.fitted_points), len(points))
        self.assertTrue(np.allclose(curve.fitted_points[0], curve.fitted_points[-1]))
        self.assertEqual(curve.metadata["control_points"], points.tolist())
        self.assertEqual(curve.metadata["curve_method"], DEFAULT_MANUAL_CURVE_METHOD)
        self.assertEqual(curve.metadata["sample_count"], DEFAULT_MANUAL_CURVE_SAMPLE_COUNT)

    def test_snap_close_helper_uses_model_relative_threshold(self) -> None:
        points = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
            ],
            dtype=float,
        )

        self.assertTrue(
            should_snap_closed_to_first_point(
                points,
                [0.05, 0.0, 0.0],
                model_extent=10.0,
            )
        )
        self.assertFalse(
            should_snap_closed_to_first_point(
                points,
                [0.2, 0.0, 0.0],
                model_extent=10.0,
            )
        )
        self.assertFalse(
            should_snap_closed_to_first_point(
                points[:2],
                [0.0, 0.0, 0.0],
                model_extent=10.0,
            )
        )

    def test_manual_metadata_tolerates_missing_or_invalid_snap_normals(self) -> None:
        metadata = manual_curve_metadata(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            is_closed=False,
            creation_type="curve_on_mesh",
            snap_to_mesh=True,
            work_plane_type="mesh",
            snap_normals=[None, [float("nan"), 0.0, 1.0]],
        )

        self.assertEqual(metadata["snap_normals"], [None, None])

    def test_sampling_filters_invalid_points_before_fitting(self) -> None:
        sampled = sample_manual_curve(
            [
                [0.0, 0.0, 0.0],
                [float("nan"), 0.0, 0.0],
                [1.0, 0.0, 0.0],
            ],
            is_closed=False,
            method=MANUAL_CURVE_METHOD_CATMULL_ROM,
            sample_count=8,
        )

        self.assertEqual(sampled.shape, (8, 3))
        self.assertTrue(np.all(np.isfinite(sampled)))
        self.assertTrue(np.allclose(sampled[0], [0.0, 0.0, 0.0]))
        self.assertTrue(np.allclose(sampled[-1], [1.0, 0.0, 0.0]))

    def test_ensure_manual_curve_storage_upgrades_legacy_manual_curve(self) -> None:
        points = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
            ],
            dtype=float,
        )
        curve = StoredCurve(
            id="curve-legacy",
            name="Manual Curve 1",
            section_result_id="",
            plane_id="",
            original_points=points.copy(),
            fitted_points=np.zeros((0, 3), dtype=float),
            mean_error=0.0,
            max_error=0.0,
            is_closed=False,
            metadata={"creation_type": "manual", "closed": False},
        )

        self.assertTrue(is_manual_curve_like(curve))
        upgraded = ensure_manual_curve_storage(curve)

        self.assertIs(upgraded, curve)
        self.assertEqual(curve.metadata["control_points"], points.tolist())
        self.assertEqual(curve.metadata["curve_method"], MANUAL_CURVE_METHOD_POLYLINE)
        self.assertEqual(curve.metadata["sample_count"], DEFAULT_MANUAL_CURVE_SAMPLE_COUNT)
        self.assertFalse(curve.metadata["snap_to_mesh"])
        self.assertEqual(curve.metadata["work_plane_type"], "manual")
        self.assertTrue(np.allclose(curve.original_points, points))
        self.assertTrue(np.allclose(curve.fitted_points, points))


if __name__ == "__main__":
    unittest.main()
