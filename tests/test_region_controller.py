from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from openretop.application.events import (
    ActiveToolChangedEvent,
    ApplicationEvent,
    EventPublisher,
    SceneChangedEvent,
    SelectionChangedEvent,
)
from openretop.application.region_controller import RegionController
from openretop.application.region_session import RegionSessionState
from openretop.application.state import AppState, MeshObjectState
from openretop.mesh.triangle_mesh import TriangleMeshData


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

    def test_boundary_extraction_adds_world_space_sketch_curves_and_is_reversible(self) -> None:
        state = _state_with_mesh()
        # the scan was moved: its boundary must come out where the scan is shown
        matrix = np.identity(4)
        matrix[:3, 3] = (10.0, 0.0, 5.0)
        state.mesh_object.transform_matrix = matrix  # type: ignore[union-attr]
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
        curves = state.model.sketch.curves
        self.assertEqual(len(curves), 1)
        curve = curves[0]
        self.assertTrue(curve.closed)
        self.assertIn("Boundary", curve.name)
        self.assertEqual(state.model.selected_curve_ids, [curve.id])
        polyline = np.asarray(curve.polyline)
        np.testing.assert_allclose(polyline.min(axis=0), (10.0, 0.0, 5.0), atol=1e-9)
        np.testing.assert_allclose(polyline.max(axis=0), (11.0, 1.0, 5.0), atol=1e-9)
        self.assertTrue(any(isinstance(event, SceneChangedEvent) for event in received))

        result.undo_payload.undo()  # type: ignore[union-attr]
        self.assertEqual(state.model.sketch.curves, [])
        result.undo_payload.redo()  # type: ignore[union-attr]
        self.assertEqual([item.id for item in state.model.sketch.curves], [curve.id])

if __name__ == "__main__":
    unittest.main()
