from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from application.manual_curve_controller import ManualCurveController
from curves.curve_state import StoredCurve
from curves.manual_curve import (
    CURVE_POINT_CORNER,
    CURVE_POINT_SMOOTH,
    CURVE_POINT_SOURCE_MANUAL,
    MANUAL_CURVE_METHOD_POLYLINE,
    MANUAL_CURVE_METHOD_SMOOTH_GUIDE,
)
from mesh.spatial_index import MeshClosestPointResult
from mesh.triangle_mesh import TriangleMeshData


class _FakeMeshQueryService:
    def __init__(self) -> None:
        self.query_count = 0

    def query_closest_points(
        self,
        _mesh: TriangleMeshData,
        points: object,
        **_kwargs: object,
    ) -> MeshClosestPointResult:
        self.query_count += 1
        source = np.asarray(points, dtype=float).reshape((-1, 3))
        closest = source.copy()
        closest[:, 2] = 0.0
        distances = np.abs(source[:, 2])
        count = len(source)
        return MeshClosestPointResult(
            source_points=source,
            closest_points=closest,
            distances=distances,
            hit_mask=np.ones(count, dtype=bool),
            triangle_indices=np.zeros(count, dtype=int),
            normals=np.tile([0.0, 0.0, 1.0], (count, 1)),
            queried_point_count=count,
            hit_count=count,
            missed_count=0,
            build_time_seconds=0.01,
            query_time_seconds=0.02,
            backend="fake-index",
        )


class ManualCurveControllerTests(unittest.TestCase):
    def test_creates_open_closed_and_polyline_curves(self) -> None:
        controller = self._controller_with_points()

        open_result = controller.finish_new_curve(curve_id="open", name="Open")

        self.assertTrue(open_result.success)
        self.assertFalse(open_result.created_curve.is_closed)
        self.assertEqual(
            open_result.created_curve.metadata["curve_method"],
            MANUAL_CURVE_METHOD_SMOOTH_GUIDE,
        )

        controller.toggle_closed()
        closed_result = controller.finish_new_curve(curve_id="closed", name="Closed")
        self.assertTrue(closed_result.created_curve.is_closed)

        controller.configure(curve_method=MANUAL_CURVE_METHOD_POLYLINE)
        polyline_result = controller.finish_new_curve(
            curve_id="polyline", name="Polyline"
        )
        self.assertEqual(
            polyline_result.created_curve.metadata["curve_method"],
            MANUAL_CURVE_METHOD_POLYLINE,
        )

    def test_edit_select_move_append_insert_delete_apply_and_cancel(self) -> None:
        source = self._controller_with_points().finish_new_curve(
            curve_id="source", name="Source"
        ).created_curve
        controller = ManualCurveController()

        loaded = controller.load_curve_for_editing(source)
        controller.select_point(1)
        controller.move_point(1, [2.0, 0.0, 0.0])
        controller.append_point([2.0, 2.0, 0.0])
        controller.insert_point(1, [0.5, 0.0, 0.0])
        controller.select_point(2)
        deleted = controller.delete_selected_point()
        applied = controller.apply_curve_edits(source)

        self.assertTrue(loaded.success)
        self.assertTrue(deleted.success)
        self.assertTrue(applied.success)
        self.assertIsNotNone(applied.updated_curve)
        self.assertEqual(applied.updated_curve.id, source.id)
        self.assertEqual(applied.updated_curve.metadata["source_curve_revision"], 1)
        cancelled = controller.cancel_workflow()
        self.assertTrue(cancelled.success)
        self.assertFalse(controller.session.active)

    def test_angle_detection_manual_override_and_clear_auto_corners(self) -> None:
        controller = ManualCurveController()
        controller.begin_new_curve(
            plane_origin=[0.0, 0.0, 0.0],
            plane_normal=[0.0, 0.0, 1.0],
        )
        for point in ([0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0]):
            controller.append_point(point)

        detected = controller.auto_detect_corners()

        self.assertTrue(detected.success)
        self.assertEqual(controller.session.point_types[1], CURVE_POINT_CORNER)
        self.assertGreater(controller.session.corner_detection_revision, 0)
        controller.select_point(1)
        controller.set_selected_point_type(CURVE_POINT_CORNER)
        controller.move_point(1, [0.5, 0.0, 0.0])
        controller.auto_detect_corners()
        cleared = controller.clear_auto_corners()
        self.assertTrue(cleared.success)
        self.assertEqual(controller.session.point_types[1], CURVE_POINT_CORNER)
        self.assertEqual(
            controller.session.point_type_sources[1], CURVE_POINT_SOURCE_MANUAL
        )

    def test_configuration_changes_sample_count_and_smoothness(self) -> None:
        controller = self._controller_with_points()

        result = controller.configure(sample_count=256, smoothness=7)
        display = controller.display_state()

        self.assertTrue(result.changed)
        self.assertEqual(controller.session.sample_count, 256)
        self.assertEqual(controller.session.smoothness, 7)
        self.assertEqual(display.sample_count, 256)

    def test_simplify_and_convert_use_existing_curve_helpers(self) -> None:
        controller = ManualCurveController()
        controller.begin_new_curve(
            plane_origin=[0.0, 0.0, 0.0],
            plane_normal=[0.0, 0.0, 1.0],
        )
        for point in (
            [0.0, 0.0, 0.0],
            [0.25, 0.01, 0.0],
            [0.5, -0.01, 0.0],
            [0.75, 0.01, 0.0],
            [1.0, 0.0, 0.0],
        ):
            controller.append_point(point)
        source = controller.finish_new_curve(curve_id="source", name="Source").created_curve

        generic = controller.simplify_stored_curve(
            source,
            curve_id="simple",
            name="Simple",
            tolerance=0.05,
        )
        guide = controller.simplify_guide_curve(
            source,
            curve_id="guide",
            name="Guide",
            tolerance=0.05,
        )
        converted = controller.convert_curve_to_smooth(source)

        self.assertTrue(generic.success)
        self.assertTrue(guide.success)
        self.assertLess(
            len(guide.created_curve.metadata["control_points"]),
            len(source.metadata["control_points"]),
        )
        self.assertTrue(converted.success)
        self.assertEqual(
            converted.updated_curve.metadata["curve_method"],
            MANUAL_CURVE_METHOD_SMOOTH_GUIDE,
        )

    def test_snap_metadata_and_keep_on_mesh_projection_are_preserved(self) -> None:
        service = _FakeMeshQueryService()
        controller = ManualCurveController(mesh_query_service=service)
        controller.begin_new_curve(
            plane_origin=[0.0, 0.0, 0.0],
            plane_normal=[0.0, 0.0, 1.0],
            snap_to_mesh=True,
            keep_curve_on_mesh=True,
        )
        controller.append_point(
            [0.0, 0.0, 1.0],
            snapped=True,
            triangle_index=4,
            normal=[0.0, 0.0, 1.0],
            projection_distance=0.25,
        )
        controller.append_point(
            [1.0, 0.0, 1.0],
            snapped=True,
            triangle_index=5,
            normal=[0.0, 0.0, 1.0],
            projection_distance=0.5,
        )

        result = controller.finish_new_curve(
            curve_id="mesh-curve",
            name="Mesh Curve",
            source_mesh_name="scan",
            projection_mesh=self._mesh(),
            mesh_revision=("mesh", 1),
        )
        metadata = result.created_curve.metadata

        self.assertEqual(metadata["creation_type"], "curve_on_mesh")
        self.assertEqual(metadata["snap_triangle_indices"], [4, 5])
        self.assertEqual(metadata["snap_projection_distances"], [0.25, 0.5])
        self.assertEqual(metadata["projection_distance"], 0.5)
        self.assertEqual(metadata["projection_backend"], "fake-index")
        self.assertEqual(metadata["projection_index_build_time_seconds"], 0.01)
        self.assertEqual(metadata["projection_query_time_seconds"], 0.02)
        self.assertEqual(metadata["source_mesh_name"], "scan")
        self.assertTrue(np.allclose(result.created_curve.fitted_points[:, 2], 0.0))

    def test_editing_derived_curve_preserves_source_lineage(self) -> None:
        source = self._controller_with_points().finish_new_curve(
            curve_id="projected", name="Projected"
        ).created_curve
        source.metadata.update(
            {
                "creation_type": "projected_curve",
                "source_curve_id": "original",
                "source_curve_name": "Original",
                "source_region_id": "region-a",
                "source_curve_ids": ["original", "support"],
                "source_lineage": {"operation": "project"},
                "projection_backend": "vtkStaticCellLocator",
                "projection_failed_indices": [2],
                "projection_query_time_seconds": 0.25,
            }
        )
        controller = ManualCurveController()
        controller.begin_edit_curve(source)
        controller.move_point(1, [1.5, 0.0, 0.0])

        result = controller.build_updated_curve(source)
        metadata = result.updated_curve.metadata

        self.assertEqual(metadata["creation_type"], "projected_curve")
        self.assertEqual(metadata["source_curve_id"], "original")
        self.assertEqual(metadata["source_curve_name"], "Original")
        self.assertEqual(metadata["source_region_id"], "region-a")
        self.assertEqual(metadata["source_curve_ids"], ["original", "support"])
        self.assertEqual(metadata["source_lineage"], {"operation": "project"})
        self.assertEqual(metadata["projection_backend"], "vtkStaticCellLocator")
        self.assertEqual(metadata["projection_failed_indices"], [2])
        self.assertEqual(metadata["projection_query_time_seconds"], 0.25)

    def test_display_cache_reuses_projection_until_controls_or_mesh_change(self) -> None:
        service = _FakeMeshQueryService()
        controller = ManualCurveController(mesh_query_service=service)
        controller.begin_new_curve(
            plane_origin=[0.0, 0.0, 0.0],
            plane_normal=[0.0, 0.0, 1.0],
            keep_curve_on_mesh=True,
        )
        controller.append_point([0.0, 0.0, 1.0])
        controller.append_point([1.0, 0.0, 1.0])
        mesh = self._mesh()

        first = controller.display_state(
            projection_mesh=mesh, mesh_revision=("mesh", 1)
        )
        second = controller.display_state(
            projection_mesh=mesh, mesh_revision=("mesh", 1)
        )
        self.assertEqual(service.query_count, 1)
        self.assertIs(first.fitted_points, second.fitted_points)

        controller.move_point(1, [2.0, 0.0, 1.0])
        controller.display_state(projection_mesh=mesh, mesh_revision=("mesh", 1))
        self.assertEqual(service.query_count, 2)
        controller.display_state(projection_mesh=mesh, mesh_revision=("mesh", 2))
        self.assertEqual(service.query_count, 3)

    def test_pointer_routing_and_escape_order(self) -> None:
        controller = self._controller_with_points()
        self.assertEqual(
            controller.route_pointer_event("left_release", button="left").action,
            "add_point",
        )
        for event, button in (
            ("right_press", "right"),
            ("middle_press", "middle"),
            ("wheel", "wheel"),
        ):
            self.assertFalse(
                controller.route_pointer_event(event, button=button).consumed
            )
        draw_escape = controller.handle_escape()
        self.assertTrue(draw_escape.metadata["exited_submode"])
        self.assertTrue(controller.session.active)
        self.assertEqual(controller.session.submode, "inactive")
        controller.resume_add_points()

        source = controller.finish_new_curve(curve_id="source", name="Source").created_curve
        controller.begin_edit_curve(source)
        empty = controller.route_pointer_event(
            "left_release", button="left", control_point_index=None
        )
        self.assertEqual(empty.action, "select_point")
        self.assertIsNone(empty.control_point_index)
        no_drag = controller.route_pointer_event(
            "left_press", button="left", control_point_index=None
        )
        begin_drag = controller.route_pointer_event(
            "left_press", button="left", control_point_index=1
        )
        self.assertEqual(no_drag.action, "none")
        self.assertEqual(begin_drag.action, "begin_drag")

        drag_escape = controller.handle_escape()
        self.assertTrue(drag_escape.metadata["exited_submode"])
        self.assertTrue(controller.session.active)
        self.assertEqual(controller.session.submode, "edit_select")
        self.assertIsNone(controller.session.drag_candidate_index)
        controller.activate_add_point()
        self.assertEqual(
            controller.route_pointer_event("left_release", button="left").action,
            "add_point",
        )
        first_escape = controller.handle_escape()
        self.assertTrue(first_escape.metadata["exited_submode"])
        self.assertTrue(controller.session.active)
        self.assertEqual(controller.session.submode, "edit_select")
        controller.activate_insert_point()
        self.assertEqual(
            controller.route_pointer_event("left_release", button="left").action,
            "insert_point",
        )
        controller.handle_escape()
        second_escape = controller.handle_escape()
        self.assertTrue(second_escape.metadata["exited_workflow"])
        self.assertFalse(controller.session.active)

    def test_architecture_has_no_window_shadow_arrays_or_ui_imports(self) -> None:
        root = Path(__file__).resolve().parents[1]
        controller_source = (root / "src/application/manual_curve_controller.py").read_text(
            encoding="utf-8"
        )
        lowered = controller_source.lower()
        self.assertNotIn("import tkinter", lowered)
        self.assertNotIn("from tkinter", lowered)
        self.assertNotIn("vtk", lowered)
        self.assertNotIn("openretopwindow", lowered)

        tree = ast.parse(
            (root / "src/presentation/qt/main_window.py").read_text(encoding="utf-8")
        )
        window_class = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "OpenRetopV3Window"
        )
        initializer = next(
            node
            for node in window_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "__init__"
        )
        forbidden = {
            "_manual_curve_points",
            "_manual_curve_point_types",
            "_manual_curve_point_type_sources",
            "_manual_curve_snap_flags",
            "_manual_curve_snap_triangle_indices",
            "_manual_curve_snap_normals",
            "_manual_curve_projection_distances",
        }
        assigned = {
            target.attr
            for node in ast.walk(initializer)
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            for target in (
                node.targets if isinstance(node, ast.Assign) else [node.target]
            )
            if isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
        }
        self.assertTrue(forbidden.isdisjoint(assigned))

    def test_controller_session_is_the_only_manual_control_state_owner(self) -> None:
        controller = ManualCurveController()
        controller.begin_new_curve(
            plane_origin=[0.0, 0.0, 0.0],
            plane_normal=[0.0, 0.0, 1.0],
        )
        controller.append_point([0.0, 0.0, 0.0])

        self.assertEqual(len(controller.session.control_points), 1)
        self.assertNotIn("control_points", controller.__dict__)

    @staticmethod
    def _controller_with_points() -> ManualCurveController:
        controller = ManualCurveController()
        controller.begin_new_curve(
            plane_origin=[0.0, 0.0, 0.0],
            plane_normal=[0.0, 0.0, 1.0],
        )
        controller.append_point([0.0, 0.0, 0.0])
        controller.append_point([1.0, 0.0, 0.0])
        controller.append_point([1.0, 1.0, 0.0])
        return controller

    @staticmethod
    def _mesh() -> TriangleMeshData:
        return TriangleMeshData(
            vertices=np.asarray(
                [[-2.0, -2.0, 0.0], [3.0, -2.0, 0.0], [-2.0, 3.0, 0.0]],
                dtype=float,
            ),
            triangles=np.asarray([[0, 1, 2]], dtype=int),
        )


if __name__ == "__main__":
    unittest.main()
