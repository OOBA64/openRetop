from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from curves.curve_state import StoredCurve
from cad_kernel.types import (
    CadBuildResult,
    CadCurveInput,
    StepExportResult,
    clean_cad_curve_points,
    curve_points_from_stored_curve,
)


def _stored_curve(
    *,
    curve_id: str = "curve-1",
    fitted_points: object | None = None,
    is_closed: bool = False,
    metadata: dict[str, object] | None = None,
) -> StoredCurve:
    points = (
        np.asarray(fitted_points, dtype=float)
        if fitted_points is not None
        else np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=float)
    )
    return StoredCurve(
        id=curve_id,
        name=f"Curve {curve_id}",
        section_result_id="section-1",
        plane_id="plane-1",
        original_points=points.copy(),
        fitted_points=points.copy(),
        mean_error=0.0,
        max_error=0.0,
        is_closed=is_closed,
        metadata=dict(metadata or {}),
    )


class CadKernelTypesTests(unittest.TestCase):
    def test_result_dataclasses_use_fresh_mutable_defaults(self) -> None:
        build_result = CadBuildResult(success=False, cad_object=None, reason="failed")
        other_build_result = CadBuildResult(
            success=False,
            cad_object=None,
            reason="also failed",
        )
        export_result = StepExportResult(success=False, path=None, reason="failed")

        build_result.warnings.append("warning")
        build_result.metadata["key"] = "value"
        export_result.warnings.append("export warning")

        self.assertEqual(other_build_result.warnings, [])
        self.assertEqual(other_build_result.metadata, {})
        self.assertEqual(export_result.warnings, ["export warning"])

    def test_clean_cad_curve_points_removes_duplicate_points(self) -> None:
        points = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
                [0.0, 0.0, 0.0],
            ]
        )

        cleaned = clean_cad_curve_points(points, closed=True)

        self.assertTrue(
            np.allclose(
                cleaned,
                [
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                    [1.0, 1.0, 0.0],
                ],
            )
        )

    def test_clean_cad_curve_points_rejects_non_finite_points(self) -> None:
        points = np.asarray([[0.0, 0.0, 0.0], [np.nan, 0.0, 0.0]])

        with self.assertRaises(ValueError) as context:
            clean_cad_curve_points(points, closed=False)

        self.assertIn("must be finite", str(context.exception))
        self.assertIn("point 1", str(context.exception))

    def test_clean_cad_curve_points_rejects_bad_shape(self) -> None:
        with self.assertRaises(ValueError) as context:
            clean_cad_curve_points([0.0, 1.0, 2.0], closed=False)

        self.assertIn("Nx3 array", str(context.exception))

    def test_clean_cad_curve_points_rejects_short_curves_after_cleanup(self) -> None:
        with self.assertRaises(ValueError) as context:
            clean_cad_curve_points(
                [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
                closed=False,
            )

        self.assertIn("at least 2", str(context.exception))

    def test_curve_points_from_stored_curve_uses_fitted_points_by_default(self) -> None:
        fitted_points = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
                [0.0, 0.0, 0.0],
            ]
        )
        curve = _stored_curve(
            fitted_points=fitted_points,
            is_closed=True,
            metadata={
                "control_points": [
                    [9.0, 9.0, 9.0],
                    [8.0, 8.0, 8.0],
                    [7.0, 7.0, 7.0],
                ]
            },
        )

        curve_input = curve_points_from_stored_curve(curve)

        self.assertIsInstance(curve_input, CadCurveInput)
        self.assertEqual(curve_input.curve_id, curve.id)
        self.assertTrue(curve_input.is_closed)
        self.assertEqual(curve_input.metadata["point_source"], "fitted_points")
        self.assertEqual(curve_input.metadata["source_point_count"], 4)
        self.assertEqual(curve_input.metadata["clean_point_count"], 3)
        self.assertTrue(np.allclose(curve_input.points, fitted_points[:-1]))

    def test_curve_points_from_stored_curve_can_use_control_points(self) -> None:
        curve = _stored_curve(
            fitted_points=[
                [0.0, 0.0, 0.0],
                [5.0, 0.0, 0.0],
                [5.0, 5.0, 0.0],
                [0.0, 0.0, 0.0],
            ],
            is_closed=True,
            metadata={
                "cad_point_source": "control_points",
                "control_points": [
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                    [1.0, 1.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [0.0, 0.0, 0.0],
                ],
            },
        )

        curve_input = curve_points_from_stored_curve(curve)

        self.assertEqual(curve_input.metadata["point_source"], "control_points")
        self.assertEqual(len(curve_input.points), 4)
        self.assertTrue(np.allclose(curve_input.points[-1], [0.0, 1.0, 0.0]))

    def test_curve_points_from_stored_curve_reports_invalid_curve_context(self) -> None:
        curve = _stored_curve(
            curve_id="bad-curve",
            fitted_points=[[0.0, 0.0, 0.0], [float("inf"), 0.0, 0.0]],
        )

        with self.assertRaises(ValueError) as context:
            curve_points_from_stored_curve(curve)

        message = str(context.exception)
        self.assertIn("Curve bad-curve cannot be used for CAD", message)
        self.assertIn("must be finite", message)

    def test_curve_points_from_stored_curve_reports_missing_control_points(self) -> None:
        curve = _stored_curve(
            curve_id="missing-controls",
            metadata={"cad_point_source": "control_points"},
        )

        with self.assertRaises(ValueError) as context:
            curve_points_from_stored_curve(curve)

        message = str(context.exception)
        self.assertIn("Curve missing-controls cannot be used for CAD", message)
        self.assertIn("no control_points metadata", message)


if __name__ == "__main__":
    unittest.main()
