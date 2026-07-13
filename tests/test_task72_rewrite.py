from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from curves.manual_curve import (
    CURVE_POINT_CORNER,
    CURVE_POINT_SMOOTH,
    CURVE_POINT_SOURCE_AUTO,
    CURVE_POINT_SOURCE_IMPORTED,
    CURVE_POINT_SOURCE_MANUAL,
    DEFAULT_MANUAL_CURVE_SAMPLE_COUNT,
    MANUAL_CURVE_METHOD_SMOOTH_GUIDE,
    ManualCurveControlDataV2,
    ManualCurvePoint,
    auto_detect_manual_curve_corners,
    build_manual_stored_curve,
    clear_auto_detected_manual_curve_corners,
    manual_curve_point_type_source,
    parse_manual_curve_metadata_v2,
    sample_smooth_guide_manual_curve,
    simplify_manual_curve_control_data,
)
from mesh.triangle_mesh import TriangleMeshData
from surfaces.surface_preview import (
    MESH_CONFORMING_LOFT,
    SurfacePreviewMesh,
    build_surface_preview,
)
from surfaces.surface_state import SurfacePatch
from mesh_query_reference import ReferenceMeshQueryService


def _plane_mesh() -> TriangleMeshData:
    return TriangleMeshData(
        vertices=np.asarray(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
            dtype=float,
        ),
        triangles=np.asarray([[0, 1, 2], [0, 2, 3]], dtype=int),
    )


def _open_curve(curve_id: str, y_value: float, z_value: float):
    return build_manual_stored_curve(
        curve_id=curve_id,
        name=curve_id,
        control_points=np.asarray(
            [[0.1, y_value, z_value], [0.5, y_value, z_value], [0.9, y_value, z_value]],
            dtype=float,
        ),
        is_closed=False,
        creation_type="manual",
        snap_to_mesh=False,
        work_plane_type="world_xy",
        curve_method=MANUAL_CURVE_METHOD_SMOOTH_GUIDE,
    )


class Task72SmoothGuideTests(unittest.TestCase):
    def test_smooth_guide_defaults_to_smooth_points_and_128_samples(self) -> None:
        points = np.asarray(
            [[0.0, 0.0, 0.0], [0.2, 0.5, 0.0], [0.5, 0.8, 0.0], [0.8, 0.5, 0.0], [1.0, 0.0, 0.0]],
            dtype=float,
        )
        curve = build_manual_stored_curve(
            curve_id="arch",
            name="Arch",
            control_points=points,
            is_closed=False,
            creation_type="manual",
            snap_to_mesh=False,
            work_plane_type="world_xy",
        )
        control_data = parse_manual_curve_metadata_v2(curve)

        self.assertIsNotNone(control_data)
        assert control_data is not None
        self.assertEqual(control_data.curve_method, MANUAL_CURVE_METHOD_SMOOTH_GUIDE)
        self.assertEqual(control_data.sample_count, DEFAULT_MANUAL_CURVE_SAMPLE_COUNT)
        self.assertEqual(
            [point.point_type for point in control_data.points],
            [CURVE_POINT_SMOOTH] * len(points),
        )
        self.assertGreater(len(curve.fitted_points), len(points))
        np.testing.assert_allclose(curve.fitted_points[[0, -1]], points[[0, -1]])

    def test_explicit_corner_is_an_exact_constraint(self) -> None:
        points = np.asarray(
            [[0.0, 0.0, 0.0], [0.4, 0.4, 0.0], [0.6, 0.0, 0.0], [1.0, 0.4, 0.0]],
            dtype=float,
        )
        control_data = ManualCurveControlDataV2(
            points=[
                ManualCurvePoint(position=point, point_type=point_type)
                for point, point_type in zip(
                    points,
                    [CURVE_POINT_SMOOTH, CURVE_POINT_SMOOTH, CURVE_POINT_CORNER, CURVE_POINT_SMOOTH],
                )
            ],
            is_closed=False,
            curve_method=MANUAL_CURVE_METHOD_SMOOTH_GUIDE,
        )

        sampled = sample_smooth_guide_manual_curve(control_data)

        self.assertTrue(np.any(np.all(np.isclose(sampled, points[2]), axis=1)))
        self.assertTrue(np.all(np.isfinite(sampled)))

    def test_auto_corners_can_be_cleared_without_removing_manual_corner(self) -> None:
        square = np.asarray(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
            dtype=float,
        )
        points = [
            ManualCurvePoint(
                position=point,
                point_type=CURVE_POINT_CORNER if index == 0 else CURVE_POINT_SMOOTH,
                metadata={
                    "point_type_source": (
                        CURVE_POINT_SOURCE_MANUAL if index == 0 else CURVE_POINT_SOURCE_AUTO
                    )
                },
            )
            for index, point in enumerate(square)
        ]
        detected = auto_detect_manual_curve_corners(
            ManualCurveControlDataV2(
                points=points,
                is_closed=True,
                curve_method=MANUAL_CURVE_METHOD_SMOOTH_GUIDE,
            )
        )

        cleared = clear_auto_detected_manual_curve_corners(detected)

        self.assertEqual(cleared.points[0].point_type, CURVE_POINT_CORNER)
        self.assertTrue(
            all(point.point_type == CURVE_POINT_SMOOTH for point in cleared.points[1:])
        )

    def test_explicit_imported_corner_is_not_labeled_auto(self) -> None:
        curve = build_manual_stored_curve(
            curve_id="imported",
            name="Imported Guide",
            control_points=np.asarray(
                [[0.0, 0.0, 0.0], [0.5, 0.5, 0.0], [1.0, 0.0, 0.0]],
                dtype=float,
            ),
            is_closed=False,
            creation_type="manual",
            snap_to_mesh=False,
            work_plane_type="world_xy",
            point_types=[CURVE_POINT_SMOOTH, CURVE_POINT_CORNER, CURVE_POINT_SMOOTH],
        )
        control_data = parse_manual_curve_metadata_v2(curve)

        self.assertIsNotNone(control_data)
        assert control_data is not None
        self.assertEqual(
            manual_curve_point_type_source(control_data.points[1]),
            CURVE_POINT_SOURCE_IMPORTED,
        )
        cleared = clear_auto_detected_manual_curve_corners(control_data)
        self.assertEqual(cleared.points[1].point_type, CURVE_POINT_CORNER)

    def test_simplification_preserves_endpoints_and_manual_corner(self) -> None:
        points = np.column_stack(
            (np.linspace(0.0, 1.0, 21), np.zeros(21), np.zeros(21))
        )
        points[10, 1] = 0.2
        control_data = ManualCurveControlDataV2(
            points=[
                ManualCurvePoint(
                    position=point,
                    point_type=CURVE_POINT_CORNER if index == 10 else CURVE_POINT_SMOOTH,
                    metadata={
                        "point_type_source": (
                            CURVE_POINT_SOURCE_MANUAL if index == 10 else CURVE_POINT_SOURCE_AUTO
                        )
                    },
                )
                for index, point in enumerate(points)
            ],
            is_closed=False,
            curve_method=MANUAL_CURVE_METHOD_SMOOTH_GUIDE,
        )

        reduced = simplify_manual_curve_control_data(control_data, tolerance=0.05)

        self.assertLess(len(reduced.points), len(control_data.points))
        np.testing.assert_allclose(reduced.points[0].position, points[0])
        np.testing.assert_allclose(reduced.points[-1].position, points[-1])
        self.assertTrue(
            any(
                point.point_type == CURVE_POINT_CORNER
                and np.allclose(point.position, points[10])
                for point in reduced.points
            )
        )


class Task72ConformingLoftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.query_service = ReferenceMeshQueryService()

    def _surface(self, *, threshold: float) -> SurfacePatch:
        return SurfacePatch(
            id="conforming",
            name="Conforming Loft Preview",
            source_curve_ids=["lower", "upper"],
            surface_type="mesh_conforming_loft_preview",
            metadata={
                "preview_mode": MESH_CONFORMING_LOFT,
                "source_mesh_name": "scan.stl",
                "projection_distance_threshold": threshold,
                "grid_v_count": 8,
            },
        )

    def test_open_curves_project_loft_grid_to_mesh_with_metrics(self) -> None:
        curves = [_open_curve("lower", 0.2, 0.2), _open_curve("upper", 0.8, 0.2)]

        result = build_surface_preview(
            self._surface(threshold=1.0),
            curves,
            mesh=_plane_mesh(),
            mesh_query_service=self.query_service,
        )

        self.assertTrue(result.preview_available)
        assert result.mesh is not None
        self.assertTrue(np.allclose(result.mesh.vertices[:, 2], 0.0))
        self.assertEqual(result.diagnostics["failed_projection_count"], 0)
        self.assertGreater(result.diagnostics["projection_mean_distance"], 0.0)
        self.assertTrue(result.diagnostics["conforming_preview"])
        self.assertFalse(result.diagnostics["is_brep"])
        self.assertFalse(result.mesh.wireframe_overlay)

    def test_projection_threshold_reports_failed_points_and_attempted_distance(self) -> None:
        curves = [_open_curve("lower", 0.2, 1.0), _open_curve("upper", 0.8, 1.0)]

        result = build_surface_preview(
            self._surface(threshold=0.1),
            curves,
            mesh=_plane_mesh(),
            mesh_query_service=self.query_service,
        )

        self.assertTrue(result.preview_available)
        self.assertGreater(result.diagnostics["failed_projection_count"], 0)
        self.assertAlmostEqual(result.diagnostics["projection_max_distance"], 1.0)
        self.assertIsNotNone(result.warning)

    def test_preview_mesh_hides_internal_tessellation_by_default(self) -> None:
        preview = SurfacePreviewMesh(
            vertices=np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
            faces=np.asarray([[0, 1, 2]]),
            source_surface_id="surface",
        )

        self.assertFalse(preview.wireframe_overlay)


if __name__ == "__main__":
    unittest.main()
