from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from curves.curve_state import CurveCollection, StoredCurve
from curves.manual_curve import (
    CURVE_POINT_CORNER,
    CURVE_POINT_SMOOTH,
    MANUAL_CURVE_METHOD_HYBRID,
    ManualCurveControlDataV2,
    ManualCurvePoint,
    auto_detect_manual_curve_corners,
    build_manual_stored_curve,
    detect_corner_point_types,
    hybrid_curve_diagnostics,
    parse_manual_curve_metadata_v2,
    sample_hybrid_manual_curve,
)
from project.project_io import load_project, save_project
from project.project_state import project_from_app_state


def _square() -> np.ndarray:
    return np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
        dtype=float,
    )


class ManualCurveV2Tests(unittest.TestCase):
    def test_legacy_control_points_upgrade_with_inferred_types(self) -> None:
        curve = StoredCurve(
            id="legacy",
            name="Legacy Square",
            section_result_id="",
            plane_id="",
            original_points=_square(),
            fitted_points=_square(),
            mean_error=0.0,
            max_error=0.0,
            is_closed=True,
            metadata={
                "control_points": _square().tolist(),
                "closed": True,
                "curve_method": "polyline",
            },
        )

        control_data = parse_manual_curve_metadata_v2(curve)

        self.assertIsNotNone(control_data)
        self.assertEqual(
            [point.point_type for point in control_data.points],
            [CURVE_POINT_CORNER] * 4,
        )
        np.testing.assert_allclose(control_data.control_points, _square())

    def test_new_curve_stores_v2_point_types(self) -> None:
        curve = build_manual_stored_curve(
            curve_id="hybrid",
            name="Hybrid",
            control_points=_square(),
            is_closed=True,
            creation_type="manual",
            snap_to_mesh=False,
            work_plane_type="world_xy",
            curve_method=MANUAL_CURVE_METHOD_HYBRID,
            point_types=[CURVE_POINT_CORNER] * 4,
        )

        self.assertEqual(curve.metadata["manual_curve_version"], 2)
        self.assertEqual(curve.metadata["point_types"], [CURVE_POINT_CORNER] * 4)
        self.assertEqual(len(curve.metadata["control_points_v2"]), 4)

    def test_v2_point_types_survive_project_round_trip(self) -> None:
        point_types = [
            CURVE_POINT_CORNER,
            CURVE_POINT_SMOOTH,
            CURVE_POINT_SMOOTH,
            CURVE_POINT_CORNER,
        ]
        curve = build_manual_stored_curve(
            curve_id="hybrid",
            name="Hybrid",
            control_points=_square(),
            is_closed=False,
            creation_type="manual",
            snap_to_mesh=False,
            work_plane_type="world_xy",
            curve_method=MANUAL_CURVE_METHOD_HYBRID,
            point_types=point_types,
        )
        project = project_from_app_state(
            mesh_object=None,
            proxy_quality="Medium",
            show_grid=True,
            show_axes=True,
            show_normals=False,
            section_axis="Z",
            section_offset=0.0,
            show_section_plane=False,
            curve_collection=CurveCollection(curves=[curve]),
        )

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manual-v2.openretop"
            save_project(project, path)
            loaded = load_project(path)

        self.assertEqual(loaded.curves[0].metadata["point_types"], point_types)
        self.assertEqual(loaded.curves[0].metadata["manual_curve_version"], 2)

    def test_corner_only_square_samples_as_exact_lines(self) -> None:
        control_data = ManualCurveControlDataV2(
            points=[
                ManualCurvePoint(position=point, point_type=CURVE_POINT_CORNER)
                for point in _square()
            ],
            is_closed=True,
            curve_method=MANUAL_CURVE_METHOD_HYBRID,
            sample_count=64,
        )

        sampled = sample_hybrid_manual_curve(control_data)

        self.assertEqual(sampled.shape, (5, 3))
        np.testing.assert_allclose(sampled[:-1], _square())
        np.testing.assert_allclose(sampled[0], sampled[-1])

    def test_mixed_curve_preserves_corners_and_smooths_only_span(self) -> None:
        points = np.asarray(
            [[0.0, 0.0, 0.0], [1.0, 0.4, 0.0], [2.0, 0.4, 0.0], [3.0, 0.0, 0.0]],
            dtype=float,
        )
        control_data = ManualCurveControlDataV2(
            points=[
                ManualCurvePoint(position=points[0], point_type=CURVE_POINT_CORNER),
                ManualCurvePoint(position=points[1], point_type=CURVE_POINT_SMOOTH),
                ManualCurvePoint(position=points[2], point_type=CURVE_POINT_SMOOTH),
                ManualCurvePoint(position=points[3], point_type=CURVE_POINT_CORNER),
            ],
            is_closed=False,
            curve_method=MANUAL_CURVE_METHOD_HYBRID,
            sample_count=32,
        )

        sampled = sample_hybrid_manual_curve(control_data)

        self.assertGreater(len(sampled), len(points))
        np.testing.assert_allclose(sampled[0], points[0])
        np.testing.assert_allclose(sampled[-1], points[-1])
        self.assertTrue(np.all(np.isfinite(sampled)))

    def test_smooth_only_open_curve_preserves_endpoints(self) -> None:
        points = np.asarray(
            [[0.0, 0.0, 0.0], [1.0, 0.5, 0.0], [2.0, 0.0, 0.0]],
            dtype=float,
        )
        control_data = ManualCurveControlDataV2(
            points=[ManualCurvePoint(position=point) for point in points],
            is_closed=False,
            curve_method=MANUAL_CURVE_METHOD_HYBRID,
            sample_count=24,
        )

        sampled = sample_hybrid_manual_curve(control_data)

        np.testing.assert_allclose(sampled[0], points[0])
        np.testing.assert_allclose(sampled[-1], points[-1])

    def test_corner_detection_finds_square_and_ignores_smooth_arc(self) -> None:
        self.assertEqual(
            detect_corner_point_types(_square(), is_closed=True),
            [CURVE_POINT_CORNER] * 4,
        )
        angles = np.linspace(0.0, np.pi / 2.0, 9)
        arc = np.column_stack((np.cos(angles), np.sin(angles), np.zeros(len(angles))))
        detected = detect_corner_point_types(arc, is_closed=False)
        self.assertNotIn(CURVE_POINT_CORNER, detected)

    def test_noisy_line_does_not_create_excessive_corners(self) -> None:
        x_values = np.linspace(0.0, 10.0, 41)
        noisy_line = np.column_stack(
            (x_values, 0.002 * np.sin(x_values * 3.0), np.zeros(len(x_values)))
        )

        detected = detect_corner_point_types(noisy_line, is_closed=False)

        self.assertEqual(detected.count(CURVE_POINT_CORNER), 0)

    def test_threshold_changes_corner_detection_predictably(self) -> None:
        points = np.asarray(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.5, 0.866, 0.0]],
            dtype=float,
        )
        low = detect_corner_point_types(points, is_closed=False, threshold_degrees=100.0)
        high = detect_corner_point_types(points, is_closed=False, threshold_degrees=130.0)
        self.assertEqual(low[1], CURVE_POINT_SMOOTH)
        self.assertEqual(high[1], CURVE_POINT_CORNER)

    def test_auto_detection_and_diagnostics_do_not_move_controls(self) -> None:
        control_data = ManualCurveControlDataV2(
            points=[ManualCurvePoint(position=point) for point in _square()],
            is_closed=True,
            curve_method=MANUAL_CURVE_METHOD_HYBRID,
        )
        before = control_data.control_points.copy()

        detected = auto_detect_manual_curve_corners(control_data)
        sampled = sample_hybrid_manual_curve(detected)
        diagnostics = hybrid_curve_diagnostics(detected, sampled)

        np.testing.assert_allclose(detected.control_points, before)
        self.assertEqual(diagnostics["corner_count"], 4)
        self.assertEqual(diagnostics["curve_topology"], "closed")
        self.assertIn("overshoot_warning", diagnostics)


if __name__ == "__main__":
    unittest.main()
