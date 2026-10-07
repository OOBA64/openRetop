"""Moving, rotating and selecting objects in the viewport.

Regression tests for: a transform starting from pointer (0, 0) so the object jumped on the
first mouse move; the vertical axis being inverted (VTK coordinates are y-up, the transform
maths is y-down); every drag event rebuilding the whole UI; the grid rescaling while an
object is dragged; and the missing selection bounding box.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import trimesh
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from openretop.application.scene_ids import NODE_MESH
from openretop.bootstrap import create_application
from openretop.infrastructure.settings_repository import InMemorySettingsRepository
from openretop.presentation.qt.main_window import OpenRetopV3Window
from openretop.presentation.qt.selection_overlay import box_corners, selected_mesh_bounds


def _ready(window: OpenRetopV3Window) -> None:
    with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
        window.viewport._is_ready = True
        window.viewport.ready.emit()


class ObjectMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _window(self) -> OpenRetopV3Window:
        window = OpenRetopV3Window(create_application(settings_repository=InMemorySettingsRepository()))
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        window.resize(1000, 700)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capsule.stl"
            trimesh.creation.capsule(height=40, radius=10).export(path)
            window.open_model_path(path, units="mm")
        _ready(window)
        window.composition.selection_controller.select_nodes((NODE_MESH,))
        window.refresh()
        return window

    def _hover(self, window: OpenRetopV3Window, x: float, y: float) -> None:
        """A real mouse move over the viewport (Qt widget coordinates, y down)."""

        point = QPointF(x, y)
        event = QMouseEvent(QEvent.Type.MouseMove, point, point, Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        window.viewport.eventFilter(window.viewport.interactor, event)

    def _motion(self, window: OpenRetopV3Window, x: float, y: float) -> None:
        """What the viewport emits while a tool owns the pointer: VTK coordinates, y up."""

        height = int(window.viewport.interactor.height())
        window._on_viewport_pointer("motion", int(x), height - 1 - int(y), None)

    def _start(self, window: OpenRetopV3Window, action: str, at: tuple[int, int]) -> None:
        self._hover(window, *at)
        with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
            self.assertTrue(window._dispatch_framework_action(action))

    def _location(self, window: OpenRetopV3Window) -> np.ndarray:
        return np.asarray(window.composition.state.mesh_object.location, dtype=float).copy()

    # -- the first-move jump ----------------------------------------------------------

    def test_transform_starts_from_the_last_pointer_position_not_from_zero(self) -> None:
        window = self._window()
        height = int(window.viewport.interactor.height())
        at = (60, max(height // 2, 1))
        self._start(window, "transform.move", at)
        self.assertEqual(window.composition.state.transform_state.mouse_start, at)

    def test_the_first_pointer_event_does_not_move_the_object(self) -> None:
        for action, attribute in (("transform.move", "location"), ("transform.rotate", "rotation")):
            with self.subTest(action=action):
                window = self._window()
                height = int(window.viewport.interactor.height())
                at = (80, max(height // 2, 1))
                before = np.asarray(getattr(window.composition.state.mesh_object, attribute), dtype=float).copy()
                self._start(window, action, at)
                self._motion(window, *at)
                after = np.asarray(getattr(window.composition.state.mesh_object, attribute), dtype=float)
                np.testing.assert_allclose(after, before, atol=1e-9)

    def test_a_pointer_that_never_entered_the_viewport_starts_from_its_centre(self) -> None:
        window = self._window()
        viewport = window.viewport
        viewport._last_pointer = None
        self.assertEqual(viewport.last_pointer_position, (viewport.interactor.width() // 2, viewport.interactor.height() // 2))

    # -- direction relative to the camera ---------------------------------------------

    def test_dragging_right_and_down_moves_the_object_right_and_down_on_screen(self) -> None:
        window = self._window()
        height = int(window.viewport.interactor.height())
        start = (40, max(height // 2 - 5, 1))
        vectors = window.viewport.camera_vectors()
        before = self._location(window)
        self._start(window, "transform.move", start)
        self._motion(window, *start)
        self._motion(window, start[0] + 30, start[1] + 3)  # 30 px right, 3 px down
        delta = self._location(window) - before
        self.assertGreater(float(delta @ vectors.right), 0.0)
        self.assertLess(float(delta @ vectors.up), 0.0, "dragging down must move the object down")
        # the same 10:1 ratio as the pointer, so the object follows the direction of the drag
        self.assertAlmostEqual(float(delta @ vectors.right) / float(-(delta @ vectors.up)), 10.0, places=3)

    def test_rotation_follows_horizontal_drag_at_half_a_degree_per_pixel(self) -> None:
        window = self._window()
        height = int(window.viewport.interactor.height())
        start = (20, max(height // 2, 1))
        self._start(window, "transform.rotate", start)
        self._motion(window, *start)
        self._motion(window, start[0] + 100, start[1])
        self.assertAlmostEqual(float(window.composition.state.mesh_object.rotation[2]), 50.0, places=6)

    def test_drag_speed_does_not_accelerate_as_the_object_moves_away(self) -> None:
        window = self._window()
        height = int(window.viewport.interactor.height())
        start = (10, max(height // 2, 1))
        before = self._location(window)
        self._start(window, "transform.move", start)
        self._motion(window, *start)
        self._motion(window, start[0] + 50, start[1])
        first = float(np.linalg.norm(self._location(window) - before))
        for step in range(10):  # wander off and come back to the same pointer position
            self._motion(window, start[0] + 50 + step * 40, start[1])
        self._motion(window, start[0] + 50, start[1])
        np.testing.assert_allclose(np.linalg.norm(self._location(window) - before), first, rtol=1e-9)

    # -- cost of a drag ---------------------------------------------------------------

    def test_a_drag_re_renders_the_scene_but_does_not_rebuild_the_panels(self) -> None:
        window = self._window()
        height = int(window.viewport.interactor.height())
        start = (30, max(height // 2, 1))
        self._start(window, "transform.move", start)
        self._motion(window, *start)
        with patch.object(window.inspector, "set_model") as inspector, patch.object(window.scene_tree, "refresh") as tree, patch.object(
            window.next_steps, "set_guidance"
        ) as guidance, patch.object(window.viewport, "render_snapshot", wraps=window.viewport.render_snapshot) as render:
            for step in range(1, 6):
                self._motion(window, start[0] + step * 4, start[1])
            self.assertEqual(render.call_count, 5)
            inspector.assert_not_called()
            tree.assert_not_called()
            guidance.assert_not_called()

    def test_panels_catch_up_when_the_transform_is_confirmed(self) -> None:
        window = self._window()
        height = int(window.viewport.interactor.height())
        start = (30, max(height // 2, 1))
        self._start(window, "transform.move", start)
        self._motion(window, *start)
        self._motion(window, start[0] + 20, start[1])
        with patch.object(window.inspector, "set_model") as inspector, patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
            self.assertTrue(window._dispatch_framework_action("transform.confirm"))
        inspector.assert_called()

    # -- the grid must not rescale during a drag --------------------------------------

    def test_the_grid_keeps_its_size_while_an_object_is_dragged_far_away(self) -> None:
        window = self._window()
        viewport = window.viewport
        height = int(viewport.interactor.height())
        start = (10, max(height // 2, 1))
        self._start(window, "transform.move", start)
        self._motion(window, *start)
        before, rebuilds = viewport.grid.spec, viewport.grid.rebuild_count
        self.assertIsNotNone(before)
        for step in range(1, 30):
            self._motion(window, start[0] + step * 60, start[1])
        # the grid follows the camera, not the scene: dragging an object far away changes nothing
        self.assertEqual(viewport.grid.spec, before)
        self.assertEqual(viewport.grid.rebuild_count, rebuilds)

    # -- click selection ---------------------------------------------------------------

    def test_a_click_on_empty_space_clears_the_selection_and_the_box(self) -> None:
        from openretop.viewer.picking_service import SceneObjectPickResult

        window = self._window()
        self.assertEqual(window.composition.selection_controller.snapshot().ids, (NODE_MESH,))
        window.viewport._last_pointer_release_was_click = True
        window._on_viewport_pointer("left_release", 5, 5, SceneObjectPickResult(hit=False))
        self.assertEqual(window.composition.selection_controller.snapshot().ids, ())
        self.assertFalse(window.viewport.selection_box.visible)

    def test_a_drag_release_over_empty_space_keeps_the_selection(self) -> None:
        from openretop.viewer.picking_service import SceneObjectPickResult

        window = self._window()
        window.viewport._last_pointer_release_was_click = False  # an orbit, not a click
        window._on_viewport_pointer("left_release", 5, 5, SceneObjectPickResult(hit=False))
        self.assertEqual(window.composition.selection_controller.snapshot().ids, (NODE_MESH,))

    # -- selection bounding box -------------------------------------------------------

    def test_selecting_the_scan_draws_a_bounding_box_that_follows_it(self) -> None:
        window = self._window()
        box = window.viewport.selection_box
        self.assertTrue(box.visible)
        first = box.bounds
        self.assertIsNotNone(first)
        height = int(window.viewport.interactor.height())
        start = (10, max(height // 2, 1))
        self._start(window, "transform.move", start)
        self._motion(window, *start)
        self._motion(window, start[0] + 40, start[1])
        self.assertNotEqual(box.bounds, first)
        moved = np.asarray(box.bounds[0]) - np.asarray(first[0])
        np.testing.assert_allclose(moved, self._location(window) - np.zeros(3), atol=1e-6)  # the box moved with the object
        extents_before = np.asarray(first[1]) - np.asarray(first[0])
        extents_after = np.asarray(box.bounds[1]) - np.asarray(box.bounds[0])
        np.testing.assert_allclose(extents_after, extents_before, atol=1e-9)

    def test_the_bounding_box_is_hidden_when_nothing_is_selected(self) -> None:
        window = self._window()
        window.composition.selection_controller.select_nodes(())
        window.refresh()
        self.assertFalse(window.viewport.selection_box.visible)

    def test_the_bounding_box_is_twelve_unpickable_edges_outside_scene_bounds(self) -> None:
        window = self._window()
        box = window.viewport.selection_box
        data = box.actor.GetMapper().GetInput()
        self.assertEqual(data.GetNumberOfPoints(), 8)
        self.assertEqual(data.GetNumberOfLines(), 12)
        self.assertFalse(bool(box.actor.GetPickable()))
        snapshot = window.viewport.last_snapshot
        self.assertEqual(len(snapshot.meshes), 1)  # the box is not scene geometry, so it never affects framing
        role_names = {item["role"] for item in window.viewport.diagnostic_state().overlay_actor_inventory}
        self.assertIn("selection_box", role_names)

    def test_box_corners_cover_the_bounds(self) -> None:
        corners = np.asarray(box_corners(((0.0, 1.0, 2.0), (3.0, 5.0, 8.0))))
        np.testing.assert_allclose(corners.min(axis=0), (0.0, 1.0, 2.0))
        np.testing.assert_allclose(corners.max(axis=0), (3.0, 5.0, 8.0))
        self.assertEqual(len({tuple(row) for row in corners}), 8)

    def test_selected_mesh_bounds_needs_a_selected_visible_mesh(self) -> None:
        window = self._window()
        snapshot = window.viewport.last_snapshot
        self.assertIsNotNone(selected_mesh_bounds(snapshot))
        window.composition.selection_controller.select_nodes(())
        window.refresh()
        self.assertIsNone(selected_mesh_bounds(window.viewport.last_snapshot))


if __name__ == "__main__":
    unittest.main()
