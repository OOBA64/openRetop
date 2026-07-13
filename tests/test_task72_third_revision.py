from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from analysis.deviation import DeviationResult, DeviationSample
from curves.curve_state import StoredCurve
from curves.manual_curve import (
    CURVE_POINT_CORNER,
    CURVE_POINT_SMOOTH,
    CURVE_POINT_SOURCE_MANUAL,
    MANUAL_CURVE_METHOD_SMOOTH_GUIDE,
    ManualCurveControlDataV2,
    ManualCurvePoint,
    auto_detect_manual_curve_corners,
    detect_corner_point_types_by_angle,
    sample_hybrid_manual_curve,
)
from surfaces.loft_feature import LoftFeatureOptions
from surfaces.surface_preview import TWO_CURVE_LOFT, build_surface_preview
from surfaces.surface_state import SurfacePatch


def _curve(curve_id: str, y_value: float) -> StoredCurve:
    points = np.asarray(
        [[0.0, y_value, 0.0], [0.5, y_value, 0.0], [1.0, y_value, 0.0]],
        dtype=float,
    )
    return StoredCurve(
        id=curve_id,
        name=curve_id,
        section_result_id="",
        plane_id="",
        original_points=points.copy(),
        fitted_points=points.copy(),
        mean_error=0.0,
        max_error=0.0,
        is_closed=False,
    )


class AngleCornerDetectionTests(unittest.TestCase):
    def test_angle_detector_marks_sharp_point_and_keeps_open_endpoints_smooth(self) -> None:
        points = np.asarray(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0]],
            dtype=float,
        )

        point_types = detect_corner_point_types_by_angle(
            points,
            is_closed=False,
            threshold_degrees=135.0,
        )

        self.assertEqual(
            point_types,
            [CURVE_POINT_SMOOTH, CURVE_POINT_CORNER, CURVE_POINT_SMOOTH],
        )

    def test_manual_smooth_override_survives_auto_detection(self) -> None:
        points = np.asarray(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0]],
            dtype=float,
        )
        control_data = ManualCurveControlDataV2(
            points=[
                ManualCurvePoint(position=point)
                for point in points
            ],
            is_closed=False,
            curve_method=MANUAL_CURVE_METHOD_SMOOTH_GUIDE,
            metadata={"control_point_revision": 7},
        )
        control_data.points[1].point_type = CURVE_POINT_SMOOTH
        control_data.points[1].metadata["point_type_source"] = CURVE_POINT_SOURCE_MANUAL

        detected = auto_detect_manual_curve_corners(control_data)

        self.assertEqual(detected.points[1].point_type, CURVE_POINT_SMOOTH)
        self.assertEqual(detected.metadata["corner_detection_revision"], 7)

    def test_sampling_does_not_rerun_corner_detection(self) -> None:
        points = [
            ManualCurvePoint(position=[0.0, 0.0, 0.0]),
            ManualCurvePoint(position=[0.5, 0.7, 0.0]),
            ManualCurvePoint(position=[1.0, 0.0, 0.0]),
        ]
        control_data = ManualCurveControlDataV2(
            points=points,
            is_closed=False,
            curve_method=MANUAL_CURVE_METHOD_SMOOTH_GUIDE,
        )

        with patch(
            "curves.manual_curve.detect_corner_point_types_by_angle"
        ) as detector:
            sampled = sample_hybrid_manual_curve(control_data)

        detector.assert_not_called()
        self.assertGreater(len(sampled), len(points))

    def test_angle_detector_handles_more_than_one_hundred_points(self) -> None:
        x_values = np.linspace(0.0, 10.0, 201)
        points = np.column_stack((x_values, np.sin(x_values) * 0.05, np.zeros(201)))

        point_types = detect_corner_point_types_by_angle(
            points,
            is_closed=False,
            threshold_degrees=135.0,
        )

        self.assertEqual(len(point_types), 201)
        self.assertEqual(point_types[0], CURVE_POINT_SMOOTH)
        self.assertEqual(point_types[-1], CURVE_POINT_SMOOTH)


class LoftOverbuildTests(unittest.TestCase):
    def test_explicit_overbuild_extends_preview_and_exposes_four_handles(self) -> None:
        surface = SurfacePatch(
            id="loft",
            name="Loft",
            source_curve_ids=["a", "b"],
            surface_type="preview_loft",
            selected=True,
            metadata={
                "preview_mode": TWO_CURVE_LOFT,
                "overbuild_enabled": True,
                "overbuild_u_start": 0.2,
                "overbuild_u_end": 0.2,
                "overbuild_v_start": 0.3,
                "overbuild_v_end": 0.3,
                "show_overbuild_handles": True,
            },
        )

        result = build_surface_preview(surface, [_curve("a", 0.0), _curve("b", 1.0)])

        self.assertTrue(result.preview_available)
        assert result.mesh is not None
        self.assertLess(float(np.min(result.mesh.vertices[:, 0])), 0.0)
        self.assertGreater(float(np.max(result.mesh.vertices[:, 0])), 1.0)
        self.assertLess(float(np.min(result.mesh.vertices[:, 1])), 0.0)
        self.assertGreater(float(np.max(result.mesh.vertices[:, 1])), 1.0)
        self.assertEqual(result.mesh.overbuild_handle_points.shape, (4, 3))
        self.assertTrue(result.mesh.show_overbuild_handles)
        self.assertTrue(result.diagnostics["overbuild_preview_only"])

    def test_legacy_loft_without_overbuild_metadata_keeps_original_grid(self) -> None:
        surface = SurfacePatch(
            id="legacy",
            name="Legacy Loft",
            source_curve_ids=["a", "b"],
            surface_type="preview_loft",
            metadata={"preview_mode": TWO_CURVE_LOFT},
        )

        result = build_surface_preview(surface, [_curve("a", 0.0), _curve("b", 1.0)])

        assert result.mesh is not None
        self.assertEqual(result.mesh.vertices.shape, (6, 3))
        self.assertFalse(result.diagnostics["overbuild_enabled"])

    def test_loft_feature_defaults_store_preview_only_overbuild_options(self) -> None:
        options = LoftFeatureOptions(source_curve_ids=["a", "b"])

        self.assertTrue(options.overbuild_enabled)
        self.assertAlmostEqual(options.overbuild_amount, 0.10)
        self.assertAlmostEqual(options.overbuild_u_start, 0.10)
        self.assertTrue(options.show_overbuild_handles)


class DeviationContractTests(unittest.TestCase):
    def test_deviation_records_are_computation_free_data_contracts(self) -> None:
        sample = DeviationSample(
            source_point=(0.0, 0.0, 0.0),
            nearest_point=(0.0, 0.0, 0.1),
            distance=0.1,
        )
        result = DeviationResult(
            samples=(sample,),
            mean_distance=0.1,
            max_distance=0.1,
            rms_distance=0.1,
        )

        self.assertEqual(result.samples, (sample,))
        self.assertEqual(result.failed_sample_count, 0)


if __name__ == "__main__":
    unittest.main()
