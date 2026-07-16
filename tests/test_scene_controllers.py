from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from application.events import (
    EventPublisher,
    SceneChangedEvent,
    SelectionChangedEvent,
)
from application.feature_dependencies import (
    plan_feature_dependency_removal,
    prune_feature_dependencies,
)
from application.scene_controller import SceneController
from application.scene_ids import (
    NODE_MESH,
    curve_node_id,
    region_node_id,
)
from application.selection_controller import SelectionController
from application.state import ActiveTransformState, AppState, MeshObjectState
from application.visibility_controller import VisibilityController
from curves.curve_state import StoredCurve, add_curve
from mesh.triangle_mesh import TriangleMeshData
from regions.region_state import RegionSelection
from surfaces.brep_state import BrepSurfaceRecord, add_brep_surface
from surfaces.four_boundary_feature import (
    FourBoundaryPatchFeatureRecord,
    add_four_boundary_feature,
)
from surfaces.loft_feature import (
    LoftFeatureOptions,
    LoftFeatureRecord,
    add_loft_feature,
)
from surfaces.surface_state import SurfacePatch, add_surface


def _mesh_object() -> MeshObjectState:
    mesh = TriangleMeshData(
        vertices=np.asarray(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        ),
        triangles=np.asarray([[0, 1, 2]]),
    )
    return MeshObjectState(
        source_mesh=mesh,
        display_mesh=mesh.copy(),
        file_path=None,
        name="Mesh",
        origin=np.zeros(3),
        location=np.zeros(3),
        rotation=np.zeros(3),
    )


def _curve(curve_id: str, name: str | None = None) -> StoredCurve:
    points = np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    return StoredCurve(
        id=curve_id,
        name=name or curve_id,
        section_result_id="",
        plane_id="",
        original_points=points.copy(),
        fitted_points=points.copy(),
        mean_error=0.0,
        max_error=0.0,
        is_closed=False,
    )


def _state_with_curve() -> AppState:
    state = AppState(mesh_object=_mesh_object())
    add_curve(state.curve_collection, _curve("curve-a", "Curve A"))
    return state


class ApplicationStateMoveTests(unittest.TestCase):
    def test_controllers_rebind_explicit_state(self) -> None:
        first = AppState()
        second = AppState(mesh_object=_mesh_object())
        controller = SelectionController(first)

        controller.rebind_state(second)

        self.assertIs(controller.state, second)
        self.assertTrue(controller.select_model().success)


class SelectionControllerTests(unittest.TestCase):
    def test_select_curve_returns_clean_result_and_typed_event(self) -> None:
        state = _state_with_curve()
        events = EventPublisher()
        received: list[SelectionChangedEvent] = []
        events.subscribe(SelectionChangedEvent, received.append)
        controller = SelectionController(state, events)

        result = controller.select_curve("curve-a")

        self.assertTrue(result.success)
        self.assertTrue(result.changed)
        self.assertFalse(result.dirty)
        self.assertIsNone(result.undo_payload)
        self.assertEqual(controller.snapshot().ids, (curve_node_id("curve-a"),))
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].selection, controller.snapshot())

    def test_missing_selection_dependency_is_failure_without_mutation(self) -> None:
        state = _state_with_curve()
        controller = SelectionController(state)
        controller.select_curve("curve-a")
        before = controller.snapshot()

        result = controller.select_curve("missing")

        self.assertFalse(result.success)
        self.assertEqual(controller.snapshot(), before)


class VisibilityControllerTests(unittest.TestCase):
    def test_persistent_visibility_returns_undo_and_scene_events(self) -> None:
        state = _state_with_curve()
        events = EventPublisher()
        received: list[SceneChangedEvent] = []
        events.subscribe(SceneChangedEvent, received.append)
        controller = VisibilityController(state, events)

        result = controller.toggle((curve_node_id("curve-a"),))

        self.assertTrue(result.success)
        self.assertTrue(result.changed)
        self.assertTrue(result.dirty)
        self.assertFalse(state.curve_collection.curves[0].visible)
        self.assertIsNotNone(result.undo_payload)
        result.undo_payload.undo()  # type: ignore[union-attr]
        self.assertTrue(state.curve_collection.curves[0].visible)
        result.undo_payload.redo()  # type: ignore[union-attr]
        self.assertFalse(state.curve_collection.curves[0].visible)
        self.assertGreaterEqual(len(received), 3)

    def test_region_visibility_is_transient_not_dirty(self) -> None:
        state = AppState(mesh_object=_mesh_object())
        state.region_collection.set_active(
            RegionSelection(id="region-a", name="Region", triangle_indices=(0,))
        )
        controller = VisibilityController(state)

        result = controller.hide((region_node_id("region-a"),))

        self.assertTrue(result.changed)
        self.assertFalse(result.dirty)
        self.assertFalse(state.region_collection.active_region.visible)  # type: ignore[union-attr]


class FeatureDependencyTests(unittest.TestCase):
    def test_source_curve_plan_prunes_linked_surfaces_and_features(self) -> None:
        state = _state_with_curve()
        add_surface(
            state.surface_collection,
            SurfacePatch("preview-a", "Preview", ["curve-a"], "loft"),
        )
        add_brep_surface(
            state.brep_surface_collection,
            BrepSurfaceRecord(
                "brep-a", "BREP", ["curve-a"], "loft_surface", "test"
            ),
        )
        add_loft_feature(
            state.loft_feature_collection,
            LoftFeatureRecord(
                "loft-a",
                "Loft",
                LoftFeatureOptions(["curve-a"]),
                brep_surface_id="brep-a",
                preview_surface_id="preview-a",
            ),
        )
        add_four_boundary_feature(
            state.four_boundary_feature_collection,
            FourBoundaryPatchFeatureRecord(
                "four-a",
                "Four",
                ["curve-a", "b", "c", "d"],
                preview_surface_id="preview-a",
            ),
        )

        change = plan_feature_dependency_removal(state, curve_ids=("curve-a",))
        prune_feature_dependencies(state, change)

        self.assertEqual(change.removed_preview_surface_ids, ("preview-a",))
        self.assertEqual(change.removed_brep_surface_ids, ("brep-a",))
        self.assertEqual(change.removed_loft_feature_ids, ("loft-a",))
        self.assertEqual(change.removed_four_boundary_feature_ids, ("four-a",))
        self.assertEqual(state.surface_collection.surfaces, [])
        self.assertEqual(state.brep_surface_collection.surfaces, [])


class SceneControllerTests(unittest.TestCase):
    def test_rename_returns_dirty_undo_payload(self) -> None:
        state = _state_with_curve()
        controller = SceneController(state)

        result = controller.rename(curve_node_id("curve-a"), "Renamed")

        self.assertTrue(result.success)
        self.assertTrue(result.dirty)
        self.assertEqual(state.curve_collection.curves[0].name, "Renamed")
        result.undo_payload.undo()  # type: ignore[union-attr]
        self.assertEqual(state.curve_collection.curves[0].name, "Curve A")
        result.undo_payload.redo()  # type: ignore[union-attr]
        self.assertEqual(state.curve_collection.curves[0].name, "Renamed")

    def test_curve_delete_cascades_and_undo_restores_dependencies_selection(self) -> None:
        state = _state_with_curve()
        add_surface(
            state.surface_collection,
            SurfacePatch("preview-a", "Preview", ["curve-a"], "loft"),
        )
        add_brep_surface(
            state.brep_surface_collection,
            BrepSurfaceRecord(
                "brep-a", "BREP", ["curve-a"], "loft_surface", "test"
            ),
        )
        add_loft_feature(
            state.loft_feature_collection,
            LoftFeatureRecord(
                "loft-a",
                "Loft",
                LoftFeatureOptions(["curve-a"]),
                brep_surface_id="brep-a",
                preview_surface_id="preview-a",
            ),
        )
        selection = SelectionController(state)
        selection.select_curve("curve-a")
        before_selection = selection.snapshot()
        controller = SceneController(state)

        result = controller.delete((curve_node_id("curve-a"),))

        self.assertTrue(result.success)
        self.assertTrue(result.dirty)
        self.assertEqual(state.curve_collection.curves, [])
        self.assertEqual(state.surface_collection.surfaces, [])
        self.assertEqual(state.brep_surface_collection.surfaces, [])
        self.assertEqual(state.loft_feature_collection.features, [])
        self.assertEqual(result.metadata["removed_brep_surface_ids"], ("brep-a",))
        result.undo_payload.undo()  # type: ignore[union-attr]
        self.assertEqual([curve.id for curve in state.curve_collection.curves], ["curve-a"])
        self.assertEqual(SelectionController(state).snapshot(), before_selection)
        result.undo_payload.redo()  # type: ignore[union-attr]
        self.assertEqual(state.curve_collection.curves, [])

    def test_mesh_delete_is_explicit_presentation_boundary(self) -> None:
        result = SceneController(_state_with_curve()).delete((NODE_MESH,))

        self.assertFalse(result.success)
        self.assertTrue(result.metadata["requires_mesh_confirmation"])


class ControllerArchitectureTests(unittest.TestCase):
    def test_application_controllers_do_not_import_ui_or_legacy_app(self) -> None:
        root = Path(__file__).resolve().parents[1] / "src" / "application"
        for filename in (
            "state.py",
            "controller_support.py",
            "feature_dependencies.py",
            "selection_controller.py",
            "visibility_controller.py",
            "scene_controller.py",
        ):
            tree = ast.parse((root / filename).read_text(encoding="utf-8"))
            imports = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            }
            imports.update(
                node.module or ""
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
            )
            self.assertFalse(any(name == "tkinter" for name in imports), filename)
            self.assertFalse(any(name.startswith("app.") for name in imports), filename)


if __name__ == "__main__":
    unittest.main()
