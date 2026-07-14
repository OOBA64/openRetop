from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from application.events import EventPublisher, SceneChangedEvent, StateChangedEvent
from application.section_controller import SectionController
from application.state import AppState, MeshObjectState
from application.transform_math import build_object_transform_matrix
from mesh.triangle_mesh import TriangleMeshData
from surfaces.surface_state import SurfacePatch, add_surface


def _cube_mesh() -> TriangleMeshData:
    vertices = np.asarray(
        [
            (-1.0, -1.0, -1.0),
            (1.0, -1.0, -1.0),
            (1.0, 1.0, -1.0),
            (-1.0, 1.0, -1.0),
            (-1.0, -1.0, 1.0),
            (1.0, -1.0, 1.0),
            (1.0, 1.0, 1.0),
            (-1.0, 1.0, 1.0),
        ],
        dtype=float,
    )
    triangles = np.asarray(
        [
            (0, 1, 2),
            (0, 2, 3),
            (4, 6, 5),
            (4, 7, 6),
            (0, 4, 5),
            (0, 5, 1),
            (1, 5, 6),
            (1, 6, 2),
            (2, 6, 7),
            (2, 7, 3),
            (3, 7, 4),
            (3, 4, 0),
        ],
        dtype=int,
    )
    return TriangleMeshData(vertices=vertices, triangles=triangles)


def _state_with_mesh() -> AppState:
    source = _cube_mesh()
    mesh_object = MeshObjectState(
        source_mesh=source,
        display_mesh=source.copy(),
        file_path=None,
        name="Cube",
        origin=np.zeros(3, dtype=float),
        location=np.zeros(3, dtype=float),
        rotation=np.zeros(3, dtype=float),
        transform_matrix=build_object_transform_matrix(
            np.zeros(3), np.zeros(3), 1.0, np.zeros(3)
        ),
        source_triangle_count=len(source.triangles),
        display_triangle_count=len(source.triangles),
        source_bounds_min=np.min(source.vertices, axis=0),
        source_bounds_max=np.max(source.vertices, axis=0),
    )
    return AppState(mesh_object=mesh_object)


class SectionControllerTests(unittest.TestCase):
    def test_compute_returns_undo_dirty_state_and_typed_events(self) -> None:
        state = _state_with_mesh()
        events = EventPublisher()
        scene_events: list[SceneChangedEvent] = []
        state_events: list[StateChangedEvent] = []
        events.subscribe(SceneChangedEvent, scene_events.append)
        events.subscribe(StateChangedEvent, state_events.append)
        controller = SectionController(state, events)

        result = controller.compute(state.mesh_object.source_mesh.copy())

        self.assertTrue(result.success)
        self.assertTrue(result.changed)
        self.assertTrue(result.dirty)
        self.assertIsNotNone(result.undo_payload)
        self.assertEqual(len(state.section_collection.results), 1)
        self.assertGreater(len(state.curve_collection.curves), 0)
        self.assertIsNotNone(state.section_result)
        self.assertEqual(scene_events[-1].reason, "section_computed")
        self.assertIn("curve_collection", state_events[-1].changed_fields)

        result.undo_payload.undo()
        self.assertEqual(state.section_collection.results, [])
        self.assertEqual(state.curve_collection.curves, [])
        result.undo_payload.redo()
        self.assertEqual(len(state.section_collection.results), 1)
        self.assertGreater(len(state.curve_collection.curves), 0)

    def test_compute_fails_without_mesh_and_does_not_mutate(self) -> None:
        state = AppState()
        controller = SectionController(state)

        result = controller.compute(_cube_mesh())

        self.assertFalse(result.success)
        self.assertFalse(result.changed)
        self.assertFalse(result.dirty)
        self.assertEqual(state.section_collection.results, [])

    def test_axis_change_invalidates_results_curves_and_dependent_surface(self) -> None:
        state = _state_with_mesh()
        controller = SectionController(state)
        computed = controller.compute(state.mesh_object.source_mesh.copy())
        curve_id = state.curve_collection.curves[0].id
        add_surface(
            state.surface_collection,
            SurfacePatch(
                id="preview-1",
                name="Dependent",
                source_curve_ids=[curve_id],
                surface_type="fill",
            ),
        )

        result = controller.set_axis_offset(axis="X", offset=0.25)

        self.assertTrue(result.success)
        self.assertTrue(result.dirty)
        self.assertEqual(state.section_collection.results, [])
        self.assertEqual(state.curve_collection.curves, [])
        self.assertEqual(state.surface_collection.surfaces, [])
        self.assertIn("preview-1", result.metadata["removed_preview_surface_ids"])
        result.undo_payload.undo()
        self.assertEqual(len(state.section_collection.results), 1)
        self.assertGreater(len(state.curve_collection.curves), 0)
        self.assertEqual(state.surface_collection.surfaces[0].id, "preview-1")
        computed.undo_payload.undo()

    def test_delete_plane_cascades_and_undo_restores_original_plane(self) -> None:
        state = _state_with_mesh()
        controller = SectionController(state)
        controller.compute(state.mesh_object.source_mesh.copy())
        original_id = state.section_collection.active_plane_id

        result = controller.delete_plane()

        self.assertTrue(result.success)
        self.assertTrue(result.dirty)
        self.assertNotEqual(state.section_collection.active_plane_id, original_id)
        self.assertEqual(len(state.section_collection.planes), 1)
        self.assertEqual(state.section_collection.results, [])
        result.undo_payload.undo()
        self.assertEqual(state.section_collection.active_plane_id, original_id)
        self.assertEqual(len(state.section_collection.results), 1)

    def test_invalid_offset_is_a_structured_failure(self) -> None:
        state = _state_with_mesh()
        controller = SectionController(state)
        before = state.section_collection.planes[0].offset

        result = controller.set_offset(float("nan"))

        self.assertFalse(result.success)
        self.assertEqual(state.section_collection.planes[0].offset, before)

    def test_controller_has_no_ui_or_main_window_imports(self) -> None:
        source = inspect.getsource(sys.modules[SectionController.__module__])
        self.assertNotIn("tkinter", source)
        self.assertNotIn("main_window", source)
        self.assertNotIn("from app.", source)
        self.assertNotIn("vtk", source.lower())


if __name__ == "__main__":
    unittest.main()
