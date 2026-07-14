from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from application.events import (
    ActiveToolChangedEvent,
    ApplicationEvent,
    EventPublisher,
    SceneChangedEvent,
    SelectionChangedEvent,
)
from application.region_controller import RegionController
from application.region_session import RegionSessionState
from application.state import AppState, MeshObjectState
from mesh.triangle_mesh import TriangleMeshData


def _quad_mesh() -> TriangleMeshData:
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


def _state_with_mesh() -> AppState:
    mesh = _quad_mesh()
    return AppState(
        mesh_object=MeshObjectState(
            source_mesh=mesh,
            display_mesh=mesh,
            file_path=Path("sample.stl"),
            name="sample.stl",
            origin=np.zeros(3),
            location=np.zeros(3),
            rotation=np.zeros(3),
            source_triangle_count=2,
            display_triangle_count=2,
        )
    )


class RegionSessionStateTests(unittest.TestCase):
    def test_validates_controls_and_distinguishes_click_from_drag(self) -> None:
        session = RegionSessionState()
        session.begin()
        self.assertTrue(
            session.configure(threshold_degrees=30.0, max_triangle_count=200)
        )
        with self.assertRaises(ValueError):
            session.configure(threshold_degrees=91.0)
        with self.assertRaises(ValueError):
            session.configure(max_triangle_count=0)

        session.press(10, 10)
        self.assertTrue(session.release_is_click(12, 11))
        session.press(10, 10)
        self.assertTrue(session.motion(20, 10))
        self.assertFalse(session.release_is_click(20, 10))


class RegionControllerTests(unittest.TestCase):
    def test_start_failure_start_exit_and_pointer_routing_publish_typed_events(self) -> None:
        missing = RegionController(AppState()).start()
        self.assertFalse(missing.success)

        state = _state_with_mesh()
        events = EventPublisher()
        received: list[ApplicationEvent] = []
        events.subscribe(ApplicationEvent, received.append)
        controller = RegionController(state, events=events)

        started = controller.start()
        press = controller.handle_pointer_event("left_press", 10, 10)
        release = controller.handle_pointer_event("left_release", 12, 11)
        exited = controller.exit()

        self.assertTrue(started.success)
        self.assertFalse(started.dirty)
        self.assertTrue(press.metadata["consumed"])
        self.assertTrue(release.metadata["is_click"])
        self.assertTrue(exited.success)
        self.assertFalse(controller.session.active)
        self.assertEqual(
            len([event for event in received if isinstance(event, ActiveToolChangedEvent)]),
            2,
        )

    def test_select_recompute_visibility_rename_and_clear_are_transient(self) -> None:
        state = _state_with_mesh()
        events = EventPublisher()
        received: list[ApplicationEvent] = []
        events.subscribe(ApplicationEvent, received.append)
        controller = RegionController(state, events=events)
        controller.start()

        selected = controller.select_seed(0)
        region = state.region_collection.active_region

        self.assertTrue(selected.success)
        self.assertTrue(selected.changed)
        self.assertFalse(selected.dirty)
        self.assertIsNotNone(region)
        self.assertEqual(state.selected_item, "region")
        self.assertEqual(region.source_mesh_identifier, "sample.stl")  # type: ignore[union-attr]
        self.assertTrue(any(isinstance(event, SceneChangedEvent) for event in received))
        self.assertTrue(any(isinstance(event, SelectionChangedEvent) for event in received))

        original_id = region.id  # type: ignore[union-attr]
        controller.configure(threshold_degrees=25.0, max_triangle_count=1)
        recomputed = controller.recompute()
        self.assertTrue(recomputed.success)
        self.assertEqual(state.region_collection.active_region.id, original_id)  # type: ignore[union-attr]
        self.assertEqual(len(state.region_collection.active_region.triangle_indices), 1)  # type: ignore[union-attr]

        hidden = controller.hide()
        shown = controller.show()
        self.assertFalse(hidden.dirty)
        self.assertFalse(shown.dirty)
        self.assertTrue(state.region_collection.active_region.visible)  # type: ignore[union-attr]

        renamed = controller.rename("Panel")
        self.assertTrue(renamed.success)
        self.assertFalse(renamed.dirty)
        self.assertEqual(state.region_collection.active_region.name, "Panel")  # type: ignore[union-attr]
        renamed.undo_payload.undo()  # type: ignore[union-attr]
        self.assertEqual(state.region_collection.active_region.name, "Region 1")  # type: ignore[union-attr]
        renamed.undo_payload.redo()  # type: ignore[union-attr]
        self.assertEqual(state.region_collection.active_region.name, "Panel")  # type: ignore[union-attr]

        cleared = controller.clear()
        self.assertTrue(cleared.success)
        self.assertFalse(cleared.dirty)
        self.assertIsNone(state.region_collection.active_region)
        self.assertIsNone(state.selected_item)

    def test_boundary_extraction_preserves_lineage_and_is_reversible(self) -> None:
        state = _state_with_mesh()
        events = EventPublisher()
        received: list[ApplicationEvent] = []
        events.subscribe(ApplicationEvent, received.append)
        controller = RegionController(state, events=events)
        controller.start()
        controller.select_seed(0)
        region_id = state.region_collection.active_region.id  # type: ignore[union-attr]

        result = controller.extract_boundary(_quad_mesh())

        self.assertTrue(result.success)
        self.assertTrue(result.changed)
        self.assertTrue(result.dirty)
        self.assertEqual(result.metadata["source_region_id"], region_id)
        self.assertEqual(len(result.metadata["created_curve_ids"]), 1)
        curve = state.curve_collection.curves[0]
        self.assertEqual(curve.metadata["creation_type"], "region_boundary")
        self.assertEqual(curve.metadata["source_region_id"], region_id)
        self.assertEqual(curve.metadata["source_region_name"], "Region 1")
        self.assertEqual(curve.metadata["source_mesh_name"], "sample.stl")
        self.assertEqual(curve.metadata["source_curve_tags"], ["region_boundary"])
        self.assertEqual(curve.metadata["boundary_index"], 1)
        self.assertTrue(curve.is_closed)
        self.assertEqual(state.selected_item, "curve")
        self.assertTrue(any(isinstance(event, SceneChangedEvent) for event in received))

        result.undo_payload.undo()  # type: ignore[union-attr]
        self.assertFalse(state.curve_collection.curves)
        self.assertEqual(state.selected_item, "region")
        self.assertTrue(state.region_collection.active_region.selected)  # type: ignore[union-attr]
        result.undo_payload.redo()  # type: ignore[union-attr]
        self.assertEqual(len(state.curve_collection.curves), 1)
        self.assertEqual(state.selected_item, "curve")

        selected = controller.select_boundary_curves()
        self.assertTrue(selected.success)
        self.assertFalse(selected.dirty)

        converted = controller.convert_boundary_to_hybrid_guide()
        self.assertTrue(converted.success)
        self.assertTrue(converted.dirty)
        guide = next(
            curve
            for curve in state.curve_collection.curves
            if curve.id == converted.metadata["created_curve_id"]
        )
        self.assertEqual(guide.metadata["creation_type"], "hybrid_region_guide")
        self.assertEqual(guide.metadata["source_curve_id"], curve.id)
        self.assertEqual(guide.metadata["source_region_id"], region_id)


if __name__ == "__main__":
    unittest.main()
