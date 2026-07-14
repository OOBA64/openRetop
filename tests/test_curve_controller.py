from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from application.curve_controller import CurveController
from application.events import ApplicationEvent, EventPublisher, SceneChangedEvent
from application.state import AppState
from curves.curve_state import StoredCurve, add_curve, set_selected_curves
from mesh.triangle_mesh import TriangleMeshData
from surfaces.brep_state import BrepSurfaceRecord
from surfaces.four_boundary_feature import FourBoundaryPatchFeatureRecord
from surfaces.loft_feature import LoftFeatureOptions, LoftFeatureRecord
from surfaces.surface_state import SurfacePatch


def _curve(curve_id: str, points: list[list[float]]) -> StoredCurve:
    values = np.asarray(points, dtype=float)
    return StoredCurve(
        id=curve_id,
        name=curve_id,
        section_result_id="section-1",
        plane_id="plane-1",
        original_points=values.copy(),
        fitted_points=values.copy(),
        mean_error=0.0,
        max_error=0.0,
        is_closed=False,
    )


class CurveControllerTests(unittest.TestCase):
    def test_join_returns_dirty_result_events_and_reversible_payload(self) -> None:
        state = AppState()
        add_curve(state.curve_collection, _curve("curve-a", [[0, 0, 0], [1, 0, 0]]))
        add_curve(state.curve_collection, _curve("curve-b", [[1, 0, 0], [2, 0, 0]]))
        set_selected_curves(
            state.curve_collection,
            ["curve-a", "curve-b"],
            active_curve_id="curve-a",
        )
        events = EventPublisher()
        received: list[ApplicationEvent] = []
        events.subscribe(ApplicationEvent, received.append)
        controller = CurveController(state, events=events)

        result = controller.join_selected(
            curve_id="curve-joined",
            name="Joined",
            tolerance=0.001,
        )

        self.assertTrue(result.success)
        self.assertTrue(result.changed)
        self.assertTrue(result.dirty)
        self.assertEqual(result.metadata["created_curve_id"], "curve-joined")
        joined = next(curve for curve in state.curve_collection.curves if curve.id == "curve-joined")
        self.assertEqual(joined.metadata["source_curve_ids"], ["curve-a", "curve-b"])
        self.assertTrue(any(isinstance(event, SceneChangedEvent) for event in received))
        self.assertIsNotNone(result.undo_payload)

        result.undo_payload.undo()  # type: ignore[union-attr]
        self.assertEqual(
            [curve.id for curve in state.curve_collection.curves],
            ["curve-a", "curve-b"],
        )
        result.undo_payload.redo()  # type: ignore[union-attr]
        self.assertIn("curve-joined", [curve.id for curve in state.curve_collection.curves])

    def test_failure_and_missing_mesh_query_dependency_do_not_mutate(self) -> None:
        state = AppState()
        controller = CurveController(state)
        join = controller.join_selected()

        self.assertFalse(join.success)
        self.assertFalse(join.changed)
        self.assertFalse(join.dirty)

        source = _curve("curve-a", [[0, 0, 1], [1, 0, 1]])
        add_curve(state.curve_collection, source)
        set_selected_curves(state.curve_collection, [source.id])
        mesh = TriangleMeshData(
            vertices=np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float),
            triangles=np.asarray([[0, 1, 2]], dtype=int),
        )

        projected = controller.project_selected_to_mesh(mesh, source_mesh_name="mesh")

        self.assertFalse(projected.success)
        self.assertIn("query service", projected.errors[0].lower())
        self.assertEqual([curve.id for curve in state.curve_collection.curves], ["curve-a"])

    def test_delete_prunes_all_dependent_feature_records_and_undo_restores(self) -> None:
        state = AppState()
        add_curve(state.curve_collection, _curve("curve-a", [[0, 0, 0], [1, 0, 0]]))
        set_selected_curves(state.curve_collection, ["curve-a"])
        state.surface_collection.surfaces.append(
            SurfacePatch("preview-1", "Preview", ["curve-a"], "loft")
        )
        state.brep_surface_collection.surfaces.append(
            BrepSurfaceRecord(
                "brep-1", "BREP", ["curve-a"], "loft_surface", "occt"
            )
        )
        state.loft_feature_collection.features.append(
            LoftFeatureRecord(
                "loft-1",
                "Loft",
                LoftFeatureOptions(["curve-a"]),
                brep_surface_id="brep-1",
                preview_surface_id="preview-1",
            )
        )
        state.four_boundary_feature_collection.features.append(
            FourBoundaryPatchFeatureRecord(
                "four-1",
                "Patch",
                ["curve-a"],
                brep_surface_id="brep-1",
                preview_surface_id="preview-1",
            )
        )

        result = CurveController(state).delete_selected()

        self.assertTrue(result.success)
        self.assertTrue(result.dirty)
        self.assertEqual(result.metadata["removed_curve_ids"], ("curve-a",))
        self.assertEqual(result.metadata["removed_preview_surface_ids"], ("preview-1",))
        self.assertEqual(result.metadata["removed_brep_surface_ids"], ("brep-1",))
        self.assertEqual(result.metadata["removed_loft_feature_ids"], ("loft-1",))
        self.assertEqual(
            result.metadata["removed_four_boundary_feature_ids"], ("four-1",)
        )
        self.assertFalse(state.curve_collection.curves)
        self.assertFalse(state.surface_collection.surfaces)
        self.assertFalse(state.brep_surface_collection.surfaces)
        self.assertFalse(state.loft_feature_collection.features)
        self.assertFalse(state.four_boundary_feature_collection.features)

        result.undo_payload.undo()  # type: ignore[union-attr]
        self.assertEqual(state.curve_collection.curves[0].id, "curve-a")
        self.assertEqual(state.surface_collection.surfaces[0].id, "preview-1")
        self.assertEqual(state.brep_surface_collection.surfaces[0].id, "brep-1")
        self.assertEqual(state.loft_feature_collection.features[0].id, "loft-1")
        self.assertEqual(state.four_boundary_feature_collection.features[0].id, "four-1")
        result.undo_payload.redo()  # type: ignore[union-attr]
        self.assertFalse(state.curve_collection.curves)

    def test_application_controller_imports_are_presentation_free(self) -> None:
        application_dir = Path(__file__).resolve().parents[1] / "src" / "application"
        for filename in (
            "curve_controller.py",
            "region_controller.py",
            "region_session.py",
            "analysis_controller.py",
        ):
            tree = ast.parse((application_dir / filename).read_text(encoding="utf-8"))
            imported_modules = {
                node.module or ""
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
            }
            imported_modules.update(
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            )
            self.assertFalse(
                any(
                    module == "tkinter"
                    or module.startswith("tkinter.")
                    or module == "app.main_window"
                    or module.startswith("vtk")
                    for module in imported_modules
                ),
                filename,
            )


if __name__ == "__main__":
    unittest.main()
