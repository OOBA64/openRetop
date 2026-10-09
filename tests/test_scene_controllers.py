from __future__ import annotations

import ast
import unittest
from pathlib import Path

import numpy as np

from openretop.application.events import (
    EventPublisher,
    SceneChangedEvent,
    SelectionChangedEvent,
)
from openretop.application.scene_controller import SceneController
from openretop.application.scene_ids import (
    NODE_MESH,
    region_node_id,
    section_plane_node_id,
    section_result_node_id,
)
from openretop.application.selection_controller import SelectionController
from openretop.application.state import AppState, MeshObjectState
from openretop.application.visibility_controller import VisibilityController
from openretop.geometry.sections import SectionResult
from openretop.mesh.triangle_mesh import TriangleMeshData
from openretop.regions.region_state import RegionSelection
from openretop.sections.section_state import SectionPlaneState, StoredSectionResult, add_plane, add_result


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


def _state_with_plane() -> AppState:
    """A scan with a second section plane "plane-a" and one result cut by it."""

    state = AppState(mesh_object=_mesh_object())
    add_plane(state.section_collection, SectionPlaneState(id="plane-a", name="Plane A", axis="X", offset=0.5))
    add_result(
        state.section_collection,
        StoredSectionResult(
            id="result-a",
            name="Section A",
            plane_id="plane-a",
            axis="X",
            offset=0.5,
            result=SectionResult(axis="X", offset=0.5, polylines=(), segment_count=0),
        ),
    )
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
    def test_select_plane_returns_clean_result_and_typed_event(self) -> None:
        state = _state_with_plane()
        events = EventPublisher()
        received: list[SelectionChangedEvent] = []
        events.subscribe(SelectionChangedEvent, received.append)
        controller = SelectionController(state, events)

        result = controller.select_section_plane("plane-a")

        self.assertTrue(result.success)
        self.assertTrue(result.changed)
        self.assertFalse(result.dirty)
        self.assertIsNone(result.undo_payload)
        self.assertEqual(controller.snapshot().ids, (section_plane_node_id("plane-a"),))
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].selection, controller.snapshot())

    def test_missing_selection_dependency_is_failure_without_mutation(self) -> None:
        state = _state_with_plane()
        controller = SelectionController(state)
        controller.select_section_plane("plane-a")
        before = controller.snapshot()

        result = controller.select_section_plane("missing")

        self.assertFalse(result.success)
        self.assertEqual(controller.snapshot(), before)


class VisibilityControllerTests(unittest.TestCase):
    def test_persistent_visibility_returns_undo_and_scene_events(self) -> None:
        state = _state_with_plane()
        events = EventPublisher()
        received: list[SceneChangedEvent] = []
        events.subscribe(SceneChangedEvent, received.append)
        controller = VisibilityController(state, events)

        result = controller.toggle((section_result_node_id("result-a"),))

        self.assertTrue(result.success)
        self.assertTrue(result.changed)
        self.assertTrue(result.dirty)
        self.assertFalse(state.section_collection.results[0].visible)
        self.assertIsNotNone(result.undo_payload)
        result.undo_payload.undo()  # type: ignore[union-attr]
        self.assertTrue(state.section_collection.results[0].visible)
        result.undo_payload.redo()  # type: ignore[union-attr]
        self.assertFalse(state.section_collection.results[0].visible)
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


class SceneControllerTests(unittest.TestCase):
    def test_rename_returns_dirty_undo_payload(self) -> None:
        state = _state_with_plane()
        controller = SceneController(state)

        result = controller.rename(section_plane_node_id("plane-a"), "Renamed")

        def name() -> str:
            return next(plane.name for plane in state.section_collection.planes if plane.id == "plane-a")

        self.assertTrue(result.success)
        self.assertTrue(result.dirty)
        self.assertEqual(name(), "Renamed")
        result.undo_payload.undo()  # type: ignore[union-attr]
        self.assertEqual(name(), "Plane A")
        result.undo_payload.redo()  # type: ignore[union-attr]
        self.assertEqual(name(), "Renamed")

    def test_plane_delete_takes_its_results_and_undo_restores_them_and_the_selection(self) -> None:
        state = _state_with_plane()
        selection = SelectionController(state)
        selection.select_section_plane("plane-a")
        before_selection = selection.snapshot()
        controller = SceneController(state)

        result = controller.delete((section_plane_node_id("plane-a"),))

        self.assertTrue(result.success)
        self.assertTrue(result.dirty)
        self.assertNotIn("plane-a", [plane.id for plane in state.section_collection.planes])
        self.assertEqual(state.section_collection.results, [])
        self.assertEqual(result.metadata["removed_section_result_ids"], ("result-a",))
        result.undo_payload.undo()  # type: ignore[union-attr]
        self.assertIn("plane-a", [plane.id for plane in state.section_collection.planes])
        self.assertEqual([item.id for item in state.section_collection.results], ["result-a"])
        self.assertEqual(SelectionController(state).snapshot(), before_selection)
        result.undo_payload.redo()  # type: ignore[union-attr]
        self.assertEqual(state.section_collection.results, [])

    def test_mesh_delete_is_explicit_presentation_boundary(self) -> None:
        result = SceneController(_state_with_plane()).delete((NODE_MESH,))

        self.assertFalse(result.success)
        self.assertTrue(result.metadata["requires_mesh_confirmation"])


class ControllerArchitectureTests(unittest.TestCase):
    def test_application_controllers_do_not_import_ui_or_legacy_app(self) -> None:
        root = Path(__file__).resolve().parents[1] / "src" / "openretop" / "application"
        for filename in (
            "state.py",
            "controller_support.py",
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
