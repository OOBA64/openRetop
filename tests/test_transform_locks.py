"""Locking a grab to an axis (X/Y/Z) or a plane (Shift+X/Y/Z), as in Blender.

The controller has always supported axis constraints, but no key was wired to them, so a grab
could not be locked at all.  These tests drive the window the way a user does.
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
from openretop.application.transform_math import (
    camera_relative_move_delta,
    plane_constrained_camera_move_delta,
    plane_constraint_normal,
    world_axis_vector,
)
from openretop.bootstrap import create_application
from openretop.infrastructure.settings_repository import InMemorySettingsRepository
from openretop.presentation.qt.main_window import OpenRetopV3Window


def _ready(window: OpenRetopV3Window) -> None:
    with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
        window.viewport._is_ready = True
        window.viewport.ready.emit()


class PlaneMoveMathTests(unittest.TestCase):
    RIGHT = np.array([1.0, 0.0, 0.0])
    UP = np.array([0.0, 1.0, 0.0])

    def test_a_plane_facing_the_camera_moves_exactly_like_a_free_move(self) -> None:
        free, _ = camera_relative_move_delta((0, 0), (37, -12), self.RIGHT, self.UP, 100.0, fine=False)
        locked, _ = plane_constrained_camera_move_delta(
            (0, 0), (37, -12), (world_axis_vector("X"), world_axis_vector("Y")), self.RIGHT, self.UP, 100.0, fine=False
        )
        np.testing.assert_allclose(locked, free, atol=1e-12)

    def test_a_tilted_plane_follows_the_drag_on_screen(self) -> None:
        # looking down at 45 degrees: the XY floor is foreshortened vertically, so a vertical
        # drag needs a longer Y move to cover the same screen distance
        right = np.array([1.0, 0.0, 0.0])
        up = np.array([0.0, 1.0, 1.0]) / np.sqrt(2.0)
        movement, _ = plane_constrained_camera_move_delta(
            (0, 0), (0, -10), (world_axis_vector("X"), world_axis_vector("Y")), right, up, 1000.0, fine=False
        )
        self.assertAlmostEqual(float(movement[2]), 0.0)
        screen = np.array([movement @ right, -(movement @ up)])
        free, _ = camera_relative_move_delta((0, 0), (0, -10), right, up, 1000.0, fine=False)
        np.testing.assert_allclose(screen, [free @ right, -(free @ up)], atol=1e-12)

    def test_an_edge_on_plane_never_jumps(self) -> None:
        # looking along Y at the XY plane: only X can be seen to move; a vertical drag does nothing
        right = np.array([1.0, 0.0, 0.0])
        up = np.array([0.0, 0.0, 1.0])
        movement, _ = plane_constrained_camera_move_delta(
            (0, 0), (5, -40), (world_axis_vector("X"), world_axis_vector("Y")), right, up, 1000.0, fine=False
        )
        free, _ = camera_relative_move_delta((0, 0), (5, -40), right, up, 1000.0, fine=False)
        self.assertAlmostEqual(float(movement[0]), float(free[0]))
        self.assertAlmostEqual(float(movement[2]), 0.0)
        self.assertLessEqual(abs(float(movement[1])), 1e-9)

    def test_plane_names(self) -> None:
        self.assertEqual(plane_constraint_normal("YZ"), "X")
        self.assertEqual(plane_constraint_normal("XZ"), "Y")
        self.assertEqual(plane_constraint_normal("XY"), "Z")
        self.assertIsNone(plane_constraint_normal("X"))


class TransformLockWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _window(self) -> OpenRetopV3Window:
        window = OpenRetopV3Window(create_application(settings_repository=InMemorySettingsRepository()))
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        window.resize(1000, 700)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "box.stl"
            trimesh.creation.box((30, 20, 10)).export(path)
            window.open_model_path(path, units="mm")
        _ready(window)
        window.composition.selection_controller.select_nodes((NODE_MESH,))
        window.refresh()
        return window

    def _hover(self, window: OpenRetopV3Window, x: float, y: float) -> None:
        point = QPointF(x, y)
        event = QMouseEvent(QEvent.Type.MouseMove, point, point, Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        window.viewport.eventFilter(window.viewport.interactor, event)

    def _motion(self, window: OpenRetopV3Window, x: float, y: float) -> None:
        self._hover(window, x, y)
        height = int(window.viewport.interactor.height())
        window._on_viewport_pointer("motion", int(x), height - 1 - int(y), None)

    def _act(self, window: OpenRetopV3Window, action: str) -> bool:
        with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
            return window._dispatch_framework_action(action)

    def _grab(self, window: OpenRetopV3Window, mode: str = "transform.move") -> tuple[int, int]:
        height = int(window.viewport.interactor.height())
        start = (200, max(height // 2, 1))
        self._hover(window, *start)
        self.assertTrue(self._act(window, mode))
        self._motion(window, *start)
        return start

    def _location(self, window: OpenRetopV3Window) -> np.ndarray:
        return np.asarray(window.composition.state.mesh_object.location, dtype=float).copy()

    # -- keys -------------------------------------------------------------------------

    def test_lock_keys_are_bound_to_the_actions(self) -> None:
        window = self._window()
        registry = window._framework_actions
        for axis in ("X", "Y", "Z"):
            self.assertEqual(registry.require(f"transform.constrain_{axis.lower()}").shortcut, axis)
            self.assertEqual(registry.require(f"transform.constrain_plane_{axis.lower()}").shortcut, f"Shift+{axis}")

    def test_lock_keys_only_work_during_a_grab(self) -> None:
        window = self._window()
        ids = ("transform.constrain_x", "transform.constrain_plane_z")
        for action_id in ids:
            action = window._qt_actions[action_id]
            self.assertFalse(action.isEnabled() and action.isVisible(), "X must stay free outside a grab")
        self._grab(window)
        for action_id in ids:
            action = window._qt_actions[action_id]
            self.assertTrue(action.isEnabled() and action.isVisible(), action_id)
        self._act(window, "transform.confirm")
        self.assertFalse(window._qt_actions["transform.constrain_x"].isEnabled())

    # -- axis lock --------------------------------------------------------------------

    def test_an_axis_lock_moves_the_object_only_along_that_axis(self) -> None:
        for axis, index in (("x", 0), ("y", 1), ("z", 2)):
            with self.subTest(axis=axis):
                window = self._window()
                start = self._grab(window)
                self.assertTrue(self._act(window, f"transform.constrain_{axis}"))
                self._motion(window, start[0] + 60, start[1] - 45)
                moved = self._location(window)
                self.assertGreater(abs(float(moved[index])), 1e-6)
                others = [value for position, value in enumerate(moved) if position != index]
                np.testing.assert_allclose(others, 0.0, atol=1e-12)

    def test_pressing_the_same_axis_again_unlocks(self) -> None:
        window = self._window()
        self._grab(window)
        self._act(window, "transform.constrain_x")
        self._act(window, "transform.constrain_x")
        self.assertIsNone(window.composition.state.transform_state.axis_constraint)

    def test_changing_the_lock_mid_grab_moves_the_object_at_once(self) -> None:
        window = self._window()
        start = self._grab(window)
        self._motion(window, start[0] + 80, start[1] - 30)
        free = self._location(window)
        self.assertGreater(np.count_nonzero(np.abs(free) > 1e-9), 1)
        self._act(window, "transform.constrain_x")  # no mouse move after this
        locked = self._location(window)
        np.testing.assert_allclose(locked[1:], 0.0, atol=1e-12)
        self.assertGreater(abs(float(locked[0])), 1e-6)

    def test_cancel_puts_a_locked_move_back(self) -> None:
        window = self._window()
        start = self._grab(window)
        self._act(window, "transform.constrain_y")
        self._motion(window, start[0] + 40, start[1] - 70)
        self._act(window, "transform.cancel")
        np.testing.assert_allclose(self._location(window), 0.0, atol=1e-12)

    # -- plane lock -------------------------------------------------------------------

    def test_a_plane_lock_keeps_the_excluded_axis_fixed(self) -> None:
        for axis, index in (("x", 0), ("y", 1), ("z", 2)):
            with self.subTest(axis=axis):
                window = self._window()
                start = self._grab(window)
                self.assertTrue(self._act(window, f"transform.constrain_plane_{axis}"))
                self._motion(window, start[0] + 70, start[1] - 50)
                moved = self._location(window)
                self.assertAlmostEqual(float(moved[index]), 0.0, places=12)
                self.assertGreater(float(np.linalg.norm(moved)), 1e-6)

    def test_a_floor_lock_seen_from_above_follows_the_pointer_exactly(self) -> None:
        window = self._window()
        self._act(window, "view.named.top")
        start = self._grab(window)
        self._act(window, "transform.constrain_plane_z")
        self._motion(window, start[0] + 50, start[1] + 20)
        locked = self._location(window)
        self._act(window, "transform.constrain_plane_z")  # unlock: a free move from the same drag
        free = self._location(window)
        np.testing.assert_allclose(locked, free, atol=1e-9)

    def test_the_status_bar_names_the_lock(self) -> None:
        window = self._window()
        self._grab(window)
        self._act(window, "transform.constrain_plane_x")
        self.assertIn("YZ plane", window.statusBar().currentMessage())
        self._act(window, "transform.constrain_z")
        self.assertIn("Z axis", window.statusBar().currentMessage())

    def test_a_plane_lock_while_rotating_rotates_around_the_excluded_axis(self) -> None:
        window = self._window()
        start = self._grab(window, "transform.rotate")
        self._act(window, "transform.constrain_plane_x")
        self.assertEqual(window.composition.state.transform_state.axis_constraint, "X")
        self._motion(window, start[0] + 40, start[1])
        rotation = np.asarray(window.composition.state.mesh_object.rotation, dtype=float)
        self.assertAlmostEqual(float(rotation[0]), 20.0, places=6)
        np.testing.assert_allclose(rotation[1:], 0.0, atol=1e-12)

    # -- what the user sees -----------------------------------------------------------

    def test_a_lock_draws_guide_lines_and_dims_the_free_axes(self) -> None:
        window = self._window()
        overlays = window.viewport.transform_overlays
        self._grab(window)
        self.assertFalse(overlays.diagnostics().guide_visible)

        self._act(window, "transform.constrain_x")
        self.assertTrue(overlays.diagnostics().guide_visible)
        self.assertEqual(overlays.guide_actor.GetMapper().GetInput().GetNumberOfLines(), 1)

        self._act(window, "transform.constrain_plane_z")
        self.assertEqual(overlays.guide_actor.GetMapper().GetInput().GetNumberOfLines(), 2)
        axes = overlays.move_actor
        self.assertAlmostEqual(axes.GetZAxisShaftProperty().GetOpacity(), 0.22)
        self.assertAlmostEqual(axes.GetXAxisShaftProperty().GetOpacity(), 1.0)

        self._act(window, "transform.confirm")
        self.assertFalse(overlays.diagnostics().guide_visible)

    def test_the_guide_is_drawn_in_the_transform_layer_and_never_picked(self) -> None:
        window = self._window()
        self._grab(window)
        self._act(window, "transform.constrain_y")
        overlays = window.viewport.transform_overlays
        self.assertFalse(bool(overlays.guide_actor.GetPickable()))
        self.assertFalse(bool(overlays.guide_actor.GetUseBounds()))
        self.assertTrue(overlays.layer_renderer.HasViewProp(overlays.guide_actor))
        roles = {item["role"] for item in window.viewport.diagnostic_state().overlay_actor_inventory}
        self.assertIn("transform_guide", roles)


if __name__ == "__main__":
    unittest.main()
