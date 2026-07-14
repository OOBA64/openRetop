from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from application.events import EventPublisher, SceneChangedEvent
from application.section_controller import SectionController
from application.state import AppState, MeshObjectState
from application.transform_controller import CameraVectors, TransformController
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
    zero = np.zeros(3, dtype=float)
    return AppState(
        mesh_object=MeshObjectState(
            source_mesh=source,
            display_mesh=source.copy(),
            file_path=None,
            name="Cube",
            origin=zero.copy(),
            location=zero.copy(),
            rotation=zero.copy(),
            transform_matrix=build_object_transform_matrix(zero, zero, 1.0, zero),
            source_triangle_count=len(source.triangles),
            display_triangle_count=len(source.triangles),
            source_bounds_min=np.min(source.vertices, axis=0),
            source_bounds_max=np.max(source.vertices, axis=0),
        )
    )


CAMERA = CameraVectors(
    right=np.asarray([1.0, 0.0, 0.0]),
    up=np.asarray([0.0, 1.0, 0.0]),
    forward=np.asarray([0.0, 0.0, -1.0]),
)


class TransformControllerTests(unittest.TestCase):
    def test_numeric_transform_returns_undo_and_invalidates_shared_query(self) -> None:
        state = _state_with_mesh()
        invalidations: list[bool] = []
        events = EventPublisher()
        scene_events: list[SceneChangedEvent] = []
        events.subscribe(SceneChangedEvent, scene_events.append)
        controller = TransformController(
            state,
            events,
            mesh_query_invalidator=lambda: invalidations.append(True),
        )

        result = controller.set_object_transform(
            location=(2.0, 3.0, 4.0),
            rotation=(0.0, 0.0, 90.0),
            scale=2.0,
        )

        self.assertTrue(result.success)
        self.assertTrue(result.dirty)
        self.assertIsNotNone(result.undo_payload)
        self.assertTrue(np.allclose(state.mesh_object.location, [2.0, 3.0, 4.0]))
        self.assertEqual(len(invalidations), 1)
        self.assertEqual(scene_events[-1].reason, "object_transform_changed")
        result.undo_payload.undo()
        self.assertTrue(np.allclose(state.mesh_object.location, [0.0, 0.0, 0.0]))
        result.undo_payload.redo()
        self.assertTrue(np.allclose(state.mesh_object.location, [2.0, 3.0, 4.0]))

    def test_invalid_scale_is_a_structured_failure(self) -> None:
        state = _state_with_mesh()
        controller = TransformController(state)

        result = controller.set_object_transform(
            location=(1.0, 2.0, 3.0),
            rotation=(0.0, 0.0, 0.0),
            scale=0.0,
        )

        self.assertFalse(result.success)
        self.assertFalse(result.changed)
        self.assertTrue(np.allclose(state.mesh_object.location, [0.0, 0.0, 0.0]))

    def test_modal_model_move_commits_one_undo_payload(self) -> None:
        state = _state_with_mesh()
        state.selected_item = "model"
        controller = TransformController(state)
        started = controller.start_move(mouse_start=(0, 0))
        self.assertTrue(started.success)
        controller.set_axis_constraint("X")

        preview = controller.update(
            (100, 0),
            camera=CAMERA,
            model_bounds=((-1.0, -1.0, -1.0), (1.0, 1.0, 1.0)),
        )
        moved = state.mesh_object.location.copy()
        committed = controller.commit()

        self.assertTrue(preview.changed)
        self.assertTrue(committed.changed)
        self.assertTrue(committed.dirty)
        self.assertIsNotNone(committed.undo_payload)
        self.assertIsNone(state.transform_state)
        self.assertGreater(float(moved[0]), 0.0)
        committed.undo_payload.undo()
        self.assertTrue(np.allclose(state.mesh_object.location, [0.0, 0.0, 0.0]))
        committed.undo_payload.redo()
        self.assertTrue(np.allclose(state.mesh_object.location, moved))

    def test_modal_cancel_restores_start_state_without_dirtying(self) -> None:
        state = _state_with_mesh()
        state.selected_item = "model"
        controller = TransformController(state)
        controller.start_rotate(mouse_start=(0, 0))
        controller.update((40, 0), camera=CAMERA)
        self.assertFalse(np.allclose(state.mesh_object.rotation, [0.0, 0.0, 0.0]))

        result = controller.cancel()

        self.assertTrue(result.changed)
        self.assertFalse(result.dirty)
        self.assertIsNone(result.undo_payload)
        self.assertTrue(np.allclose(state.mesh_object.rotation, [0.0, 0.0, 0.0]))

    def test_section_transform_commit_invalidates_dependents_and_undo_restores(self) -> None:
        state = _state_with_mesh()
        sections = SectionController(state)
        sections.compute(state.mesh_object.source_mesh.copy())
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
        state.selected_item = "section_plane"
        controller = TransformController(state)
        controller.start_move(mouse_start=(0, 0))
        controller.set_axis_constraint("N")
        controller.update(
            (50, 0),
            camera=CAMERA,
            model_bounds=((-1.0, -1.0, -1.0), (1.0, 1.0, 1.0)),
        )

        result = controller.commit()

        self.assertTrue(result.changed)
        self.assertTrue(result.dirty)
        self.assertEqual(state.section_collection.results, [])
        self.assertEqual(state.curve_collection.curves, [])
        self.assertEqual(state.surface_collection.surfaces, [])
        self.assertIn("preview-1", result.metadata["removed_preview_surface_ids"])
        result.undo_payload.undo()
        self.assertEqual(len(state.section_collection.results), 1)
        self.assertGreater(len(state.curve_collection.curves), 0)
        self.assertEqual(state.surface_collection.surfaces[0].id, "preview-1")

    def test_controller_has_no_ui_or_main_window_imports(self) -> None:
        source = inspect.getsource(sys.modules[TransformController.__module__])
        self.assertNotIn("tkinter", source)
        self.assertNotIn("main_window", source)
        self.assertNotIn("from app.", source)
        self.assertNotIn("vtk", source.lower())


if __name__ == "__main__":
    unittest.main()
