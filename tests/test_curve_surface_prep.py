from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from curves.curve_state import StoredCurve
from curves.projection import project_curve_points_to_mesh, project_stored_curve_to_mesh
from curves.rebuild import rebuild_curve_by_arc_length, rebuild_stored_curve
from curves.validation import (
    estimate_curve_planarity_error,
    validate_curve_for_fill,
    validate_curves_for_loft,
)
from application.scene_labels import curve_display_label
from mesh.triangle_mesh import TriangleMeshData
from mesh_query_reference import ReferenceMeshQueryService


def _mesh() -> TriangleMeshData:
    return TriangleMeshData(
        vertices=np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
                [0.0, 1.0, 0.0],
            ],
            dtype=float,
        ),
        triangles=np.asarray([[0, 1, 2], [0, 2, 3]], dtype=int),
    )


def _curve(
    *,
    curve_id: str = "curve-a",
    name: str = "Curve A",
    points: np.ndarray | None = None,
    is_closed: bool = False,
    metadata: dict[str, object] | None = None,
) -> StoredCurve:
    if points is None:
        points = np.asarray([[0.0, 0.0, 0.5], [1.0, 0.0, 0.5]], dtype=float)
    return StoredCurve(
        id=curve_id,
        name=name,
        section_result_id="",
        plane_id="",
        original_points=points.copy(),
        fitted_points=points.copy(),
        mean_error=0.0,
        max_error=0.0,
        is_closed=is_closed,
        metadata={} if metadata is None else dict(metadata),
    )


class CurveProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.query_service = ReferenceMeshQueryService()

    def test_projection_empty_curve_returns_safe_result(self) -> None:
        result = project_curve_points_to_mesh(
            np.zeros((0, 3), dtype=float),
            _mesh(),
            mesh_query_service=self.query_service,
        )

        self.assertEqual(result.projected_points.shape, (0, 3))
        self.assertEqual(result.projected_count, 0)
        self.assertEqual(result.missed_count, 0)
        self.assertTrue(result.warnings)

    def test_projection_preserves_order_and_reports_stats(self) -> None:
        points = np.asarray(
            [[0.1, 0.1, 0.5], [0.9, 0.1, -0.25], [0.8, 0.8, 0.2]],
            dtype=float,
        )

        result = project_curve_points_to_mesh(
            points,
            _mesh(),
            mesh_query_service=self.query_service,
        )

        self.assertEqual(result.projected_points.shape, points.shape)
        self.assertTrue(np.allclose(result.projected_points[:, 2], 0.0))
        self.assertEqual(result.hit_mask.tolist(), [True, True, True])
        self.assertEqual(result.triangle_indices[0], 0)
        self.assertEqual(result.projected_count, 3)
        self.assertEqual(result.missed_count, 0)
        self.assertGreater(result.max_distance, 0.0)

    def test_projection_handles_missing_mesh_safely(self) -> None:
        points = np.asarray([[0.0, 0.0, 1.0]], dtype=float)

        result = project_curve_points_to_mesh(
            points,
            None,
            mesh_query_service=self.query_service,
        )

        self.assertEqual(result.projected_count, 0)
        self.assertEqual(result.missed_count, 1)
        self.assertTrue(np.allclose(result.projected_points, points))
        self.assertTrue(result.warnings)

    def test_projection_preserves_missed_points_when_limited(self) -> None:
        points = np.asarray([[0.25, 0.25, 5.0], [0.75, 0.75, 4.0]], dtype=float)

        result = project_curve_points_to_mesh(
            points,
            _mesh(),
            max_search_distance=0.01,
            mesh_query_service=self.query_service,
        )

        self.assertEqual(result.hit_mask.tolist(), [False, False])
        self.assertEqual(result.projected_count, 0)
        self.assertEqual(result.missed_count, 2)
        self.assertTrue(np.allclose(result.projected_points, points))
        self.assertEqual(len(result.warnings), 2)

    def test_projection_handles_invalid_mesh_safely(self) -> None:
        points = np.asarray([[0.25, 0.25, 1.0]], dtype=float)
        invalid_mesh = TriangleMeshData(
            vertices=np.asarray([[0.0, 0.0, 0.0]], dtype=float),
            triangles=np.asarray([[0, 1, 2]], dtype=int),
        )

        result = project_curve_points_to_mesh(
            points,
            invalid_mesh,
            mesh_query_service=self.query_service,
        )

        self.assertEqual(result.projected_count, 0)
        self.assertEqual(result.missed_count, 1)
        self.assertTrue(np.allclose(result.projected_points, points))
        self.assertIn("Mesh has no valid projection triangles.", result.warnings)

    def test_project_stored_curve_creates_editable_metadata(self) -> None:
        curve = _curve(
            is_closed=True,
            metadata={
                "creation_type": "region_boundary",
                "source_region_id": "region-a",
                "source_region_name": "Region 1",
                "source_region_triangle_count": 2,
                "curve_method": "polyline",
                "control_points": [[0.0, 0.0, 0.5], [1.0, 0.0, 0.5]],
            }
        )

        projected = project_stored_curve_to_mesh(
            curve,
            _mesh(),
            curve_id="curve-projected",
            name="Projected Curve 1",
            source_mesh_name="scan.stl",
            mesh_query_service=self.query_service,
        )

        self.assertEqual(projected.metadata["creation_type"], "projected_curve")
        self.assertEqual(projected.metadata["source_curve_id"], curve.id)
        self.assertEqual(projected.metadata["source_region_id"], "region-a")
        self.assertEqual(projected.metadata["source_region_name"], "Region 1")
        self.assertEqual(projected.metadata["source_region_triangle_count"], 2)
        self.assertEqual(projected.metadata["projection_projected_count"], 2)
        self.assertEqual(projected.metadata["snap_mode"], "mesh")
        self.assertEqual(len(projected.metadata["control_points"]), 2)
        self.assertTrue(projected.is_closed)


class CurveRebuildTests(unittest.TestCase):
    def test_rebuild_open_curve_preserves_endpoints(self) -> None:
        points = np.asarray([[float(index), 0.0, 0.0] for index in range(10)], dtype=float)

        result = rebuild_curve_by_arc_length(
            points,
            target_control_point_count=4,
            is_closed=False,
            curve_method="polyline",
            sample_count=16,
        )

        self.assertEqual(result.control_points.shape, (4, 3))
        self.assertTrue(np.allclose(result.control_points[0], points[0]))
        self.assertTrue(np.allclose(result.control_points[-1], points[-1]))

    def test_rebuild_closed_curve_does_not_duplicate_first_control(self) -> None:
        points = np.asarray(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
            dtype=float,
        )

        result = rebuild_curve_by_arc_length(
            points,
            target_control_point_count=4,
            is_closed=True,
            curve_method="polyline",
            sample_count=16,
        )

        self.assertEqual(result.control_points.shape, (4, 3))
        self.assertFalse(np.allclose(result.control_points[0], result.control_points[-1]))
        self.assertTrue(np.allclose(result.fitted_points[0], result.fitted_points[-1]))

    def test_rebuild_stored_curve_preserves_projection_lineage(self) -> None:
        source = _curve(
            metadata={
                "creation_type": "projected_curve",
                "source_mesh_name": "scan.stl",
                "projection_mean_distance": 0.25,
            }
        )

        rebuilt = rebuild_stored_curve(
            source,
            curve_id="curve-rebuilt",
            name="Rebuilt Curve 1",
            target_control_point_count=2,
            curve_method="polyline",
            sample_count=8,
        )

        self.assertEqual(rebuilt.metadata["creation_type"], "rebuilt_curve")
        self.assertEqual(rebuilt.metadata["source_curve_id"], source.id)
        self.assertEqual(rebuilt.metadata["source_mesh_name"], "scan.stl")
        self.assertEqual(rebuilt.metadata["projection_mean_distance"], 0.25)
        self.assertEqual(rebuilt.metadata["rebuild_target_control_point_count"], 2)

    def test_rebuild_target_count_clamps_and_outputs_finite_points(self) -> None:
        points = np.asarray([[float(index), 0.0, 0.0] for index in range(20)], dtype=float)

        result = rebuild_curve_by_arc_length(
            points,
            target_control_point_count=999,
            is_closed=False,
            curve_method="polyline",
            sample_count=8,
        )

        self.assertEqual(result.target_control_point_count, 256)
        self.assertEqual(result.control_points.shape, (256, 3))
        self.assertTrue(np.all(np.isfinite(result.control_points)))
        self.assertTrue(np.all(np.isfinite(result.fitted_points)))


class CurveValidationTests(unittest.TestCase):
    def test_validate_fill_reports_open_curve_error(self) -> None:
        readiness = validate_curve_for_fill(_curve(is_closed=False))

        self.assertIn("Fill Closed Curve requires one closed curve.", readiness.errors)
        self.assertEqual(readiness.point_count, 2)

    def test_validate_fill_accepts_closed_planar_curve(self) -> None:
        points = np.asarray(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
            dtype=float,
        )

        readiness = validate_curve_for_fill(_curve(points=points, is_closed=True))

        self.assertEqual(readiness.errors, [])
        self.assertEqual(readiness.planarity_error, 0.0)

    def test_validate_fill_rejects_collinear_closed_curve(self) -> None:
        points = np.asarray(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
            dtype=float,
        )

        readiness = validate_curve_for_fill(_curve(points=points, is_closed=True))

        self.assertIn("Selected curve is degenerate.", readiness.errors)

    def test_validate_loft_warns_for_mismatched_curve_types(self) -> None:
        first = _curve(curve_id="first", is_closed=True)
        second = _curve(curve_id="second", is_closed=False)

        readiness = validate_curves_for_loft([first, second])

        warnings = {warning for item in readiness for warning in item.warnings}
        self.assertIn("Loft uses one open curve and one closed curve.", warnings)

    def test_validate_warns_on_high_point_count(self) -> None:
        angles = np.linspace(0.0, np.pi * 2.0, 300, endpoint=False)
        points = np.column_stack((np.cos(angles), np.sin(angles), np.zeros(len(angles))))

        readiness = validate_curve_for_fill(_curve(points=points, is_closed=True))

        self.assertIn(
            "Curve has many points; rebuild it for cleaner surface inputs.",
            readiness.warnings,
        )

    def test_validate_loft_warns_on_point_count_mismatch(self) -> None:
        first = _curve(
            curve_id="first",
            points=np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=float),
        )
        second = _curve(
            curve_id="second",
            points=np.asarray([[float(index), 1.0, 0.0] for index in range(10)], dtype=float),
        )

        readiness = validate_curves_for_loft([first, second])

        warnings = {warning for item in readiness for warning in item.warnings}
        self.assertIn("Loft source curves have very different point counts.", warnings)

    def test_validate_empty_curve_does_not_crash(self) -> None:
        readiness = validate_curve_for_fill(_curve(points=np.zeros((0, 3), dtype=float)))

        self.assertIn("Curve has no usable points.", readiness.errors)

    def test_planarity_error_handles_nonplanar_points(self) -> None:
        points = np.asarray(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.5], [0.0, 1.0, 0.0]],
            dtype=float,
        )

        self.assertGreater(estimate_curve_planarity_error(points), 0.0)


class CurveSceneBrowserLabelTests(unittest.TestCase):
    def test_projected_rebuilt_and_boundary_labels_use_two_priority_tags(self) -> None:
        self.assertEqual(
            curve_display_label(
                _curve(
                    name="Projected Curve 1",
                    metadata={"creation_type": "projected_curve"},
                ),
                "Curve 1",
            ),
            "Projected Curve 1 (projected)",
        )
        self.assertEqual(
            curve_display_label(
                _curve(
                    name="Projected Curve 2",
                    metadata={
                        "creation_type": "projected_curve",
                        "snap_mode": "mesh",
                        "is_tiny_fragment": True,
                    },
                ),
                "Curve 2",
            ),
            "Projected Curve 2 (projected, mesh)",
        )
        self.assertEqual(
            curve_display_label(
                _curve(
                    name="Rebuilt Curve 2",
                    metadata={
                        "creation_type": "rebuilt_curve",
                        "curve_method": "catmull_rom",
                        "source_mesh_name": "scan.stl",
                        "snap_to_mesh": True,
                    },
                ),
                "Curve 3",
            ),
            "Rebuilt Curve 2 (rebuilt, smooth)",
        )
        self.assertEqual(
            curve_display_label(
                _curve(
                    name="Region Boundary 1",
                    is_closed=True,
                    metadata={
                        "creation_type": "region_boundary",
                        "source_region_id": "region-a",
                    },
                ),
                "Curve 4",
            ),
            "Region Boundary 1 (boundary, closed)",
        )


if __name__ == "__main__":
    unittest.main()
