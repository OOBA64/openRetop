from __future__ import annotations

import math
import os
from pathlib import Path
import platform
import sys
import unittest
from unittest.mock import patch

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "packages" / "workbench_ui"))

from PySide6.QtCore import QEvent, QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from application.actions import create_core_action_registry  # noqa: E402
from application.scene_ids import NODE_MESH  # noqa: E402
from bootstrap import create_application  # noqa: E402
from infrastructure.settings_repository import InMemorySettingsRepository  # noqa: E402
from mesh.triangle_mesh import TriangleMeshData  # noqa: E402
from presentation.qt.main_window import OpenRetopV3Window  # noqa: E402
from presentation.qt.orientation_gizmo import (  # noqa: E402
    GIZMO_LOGICAL_MARGIN,
    GIZMO_LOGICAL_SIZE,
    normalized_gizmo_viewport,
)
from presentation.qt.view_controls import (  # noqa: E402
    CENTRAL_BUTTON_SIZE,
    NAVIGATION_CLUSTER_HEIGHT,
    NAVIGATION_CLUSTER_WIDTH,
    NAVIGATION_GIZMO_OFFSET,
    ROLL_BUTTON_SIZE,
    TRIANGLE_BUTTON_SIZE,
    CentralGizmoButton,
    RollViewButton,
    TriangularViewButton,
)
from presentation.qt.viewport import QtSceneViewport  # noqa: E402
from settings.settings_data import default_app_settings  # noqa: E402
from viewer.camera_controller import CameraController  # noqa: E402
from viewer.scene_types import (  # noqa: E402
    CameraRequest,
    MeshRenderItem,
    SceneSnapshot,
)


DIRECTION_ACTIONS = {
    "view.named.top",
    "view.named.bottom",
    "view.named.left",
    "view.named.right",
}
ROLL_ACTIONS = {"view.roll_left", "view.roll_right"}


def _mesh() -> TriangleMeshData:
    return TriangleMeshData(
        vertices=np.asarray(
            [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 3.0, 0.0]],
            dtype=float,
        ),
        triangles=np.asarray([[0, 1, 2]], dtype=int),
    )


def _snapshot(
    *,
    revision: int = 1,
    show_axis_gizmo: bool = True,
    show_viewcube: bool = True,
    mode: str | None = None,
    camera_request: CameraRequest | None = None,
) -> SceneSnapshot:
    return SceneSnapshot(
        revision=revision,
        meshes=(
            MeshRenderItem(
                id="mesh",
                revision=1,
                mesh=_mesh(),
                local_bounds=((0.0, 0.0, 0.0), (2.0, 3.0, 0.0)),
                selection_keys=(NODE_MESH,),
            ),
        ),
        display={
            "show_grid": True,
            "show_axes": True,
            "show_axis_gizmo": show_axis_gizmo,
            "show_viewcube": show_viewcube,
            "display_colors": {"background_color": "#101316"},
        },
        camera_request=camera_request or CameraRequest(),
        active_transform_mode=mode,
        object_origin=(1.0, 1.0, 0.0) if mode else None,
    )


def _ready_without_native_render(viewport: QtSceneViewport) -> None:
    with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
        viewport._is_ready = True
        viewport.ready.emit()


def _camera_state(camera: object) -> dict[str, object]:
    position = np.asarray(camera.GetPosition(), dtype=float)
    focal = np.asarray(camera.GetFocalPoint(), dtype=float)
    return {
        "position": position,
        "focal": focal,
        "view_up": np.asarray(camera.GetViewUp(), dtype=float),
        "direction": np.asarray(camera.GetDirectionOfProjection(), dtype=float),
        "distance": float(np.linalg.norm(position - focal)),
        "parallel": int(camera.GetParallelProjection()),
        "parallel_scale": float(camera.GetParallelScale()),
    }


class Task82ENavigationControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_defaults_create_one_visible_gizmo_and_one_cluster(self) -> None:
        defaults = default_app_settings().display
        self.assertTrue(defaults.show_axis_gizmo)
        self.assertTrue(defaults.show_viewcube)
        viewport = QtSceneViewport()
        viewport.resize(700, 480)
        try:
            viewport.render_snapshot(_snapshot())
            _ready_without_native_render(viewport)
            cluster = viewport.navigation_cluster
            state = cluster.diagnostic_state()
            renderer = viewport._axis_gizmo_renderer
            actor = viewport._axis_gizmo_actor
            self.assertTrue(state.gizmo.renderer_attached)
            self.assertTrue(state.gizmo.actor_visible)
            self.assertFalse(state.gizmo.actor_pickable)
            self.assertEqual(state.gizmo.creation_count, 1)
            self.assertEqual(state.creation_count, 1)
            self.assertEqual(viewport.render_window.GetRenderers().GetNumberOfItems(), 2)

            viewport.ready.emit()
            viewport.render_snapshot(_snapshot(revision=2))
            self.assertIs(viewport._axis_gizmo_renderer, renderer)
            self.assertIs(viewport._axis_gizmo_actor, actor)
            self.assertEqual(cluster.diagnostic_state().creation_count, 1)
            self.assertEqual(cluster.diagnostic_state().gizmo.observer_count, 1)
        finally:
            viewport.close()

    def test_exact_new_control_structure_has_no_lettered_triangles(self) -> None:
        viewport = QtSceneViewport()
        try:
            cluster = viewport.navigation_cluster
            self.assertEqual(set(cluster.direction_buttons), DIRECTION_ACTIONS)
            self.assertEqual(set(cluster.roll_buttons), ROLL_ACTIONS)
            self.assertEqual(len(cluster.direction_buttons), 4)
            self.assertEqual(len(cluster.roll_buttons), 2)
            self.assertIsInstance(cluster.central_button, CentralGizmoButton)
            self.assertNotIn("view.named.front", cluster.buttons)
            self.assertNotIn("view.named.back", cluster.buttons)
            for button in cluster.direction_buttons.values():
                self.assertIsInstance(button, TriangularViewButton)
                self.assertEqual(button.text(), "")
                self.assertFalse(hasattr(button, "_label"))
                self.assertEqual(button.size().width(), TRIANGLE_BUTTON_SIZE)
            for button in cluster.roll_buttons.values():
                self.assertIsInstance(button, RollViewButton)
                self.assertEqual(button.size().width(), ROLL_BUTTON_SIZE)
            self.assertEqual(cluster.central_button.width(), CENTRAL_BUTTON_SIZE)
        finally:
            viewport.close()

    def test_control_actions_mapping_hit_regions_and_accessibility(self) -> None:
        viewport = QtSceneViewport()
        actions: list[str] = []
        viewport.view_controls.action_requested.connect(actions.append)
        try:
            cluster = viewport.navigation_cluster
            for action_id, button in cluster.direction_buttons.items():
                self.assertFalse(button.hitButton(QPoint(0, 0)))
                interior = {
                    "view.named.top": QPoint(button.width() // 2, 4),
                    "view.named.bottom": QPoint(button.width() // 2, button.height() - 4),
                    "view.named.left": QPoint(4, button.height() // 2),
                    "view.named.right": QPoint(button.width() - 4, button.height() // 2),
                }[action_id]
                self.assertTrue(button.hitButton(interior))
                button.click()
                self.assertEqual(actions[-1], action_id)
                self.assertTrue(button.toolTip())
                self.assertTrue(button.accessibleName())

            cluster.roll_buttons["view.roll_left"].click()
            cluster.roll_buttons["view.roll_right"].click()
            cluster.central_button.click()
            self.assertEqual(
                actions[-3:],
                ["view.roll_left", "view.roll_right", "view.named.isometric"],
            )
            self.assertEqual(cluster.central_button.toolTip(), "Isometric View")
            self.assertEqual(cluster.central_button.accessibleName(), "Isometric View")
        finally:
            viewport.close()

    def test_hover_pressed_paint_and_control_clicks_do_not_pick(self) -> None:
        viewport = QtSceneViewport()
        viewport.resize(700, 480)
        picks = []
        viewport.pointer_event.connect(lambda *values: picks.append(values))
        try:
            viewport.render_snapshot(_snapshot())
            _ready_without_native_render(viewport)
            button = viewport.view_controls.direction_buttons["view.named.top"]
            QApplication.sendEvent(button, QEvent(QEvent.Enter))
            self.assertEqual(button.visual_state, "hovered")
            button.setDown(True)
            self.assertEqual(button.visual_state, "pressed")
            button.setDown(False)
            QApplication.sendEvent(button, QEvent(QEvent.Leave))
            self.assertEqual(button.visual_state, "normal")
            with patch.object(viewport, "pick_scene_object") as pick:
                for control in viewport.view_controls.buttons.values():
                    control.click()
                pick.assert_not_called()
            self.assertEqual(picks, [])

            image = button.grab().toImage()
            nontransparent = sum(
                1
                for y_value in range(image.height())
                for x_value in range(image.width())
                if image.pixelColor(x_value, y_value).alpha() > 0
            )
            self.assertGreater(nontransparent, 40)
        finally:
            viewport.close()

    def test_independent_visibility_combinations_and_transform_separation(self) -> None:
        viewport = QtSceneViewport()
        viewport.resize(700, 480)
        try:
            _ready_without_native_render(viewport)
            combinations = (
                (True, True, True, True, False),
                (True, False, True, False, False),
                (False, True, False, True, True),
                (False, False, False, False, False),
            )
            for revision, values in enumerate(combinations, start=1):
                gizmo, controls, actor_visible, controls_visible, fallback = values
                viewport.render_snapshot(
                    _snapshot(
                        revision=revision,
                        show_axis_gizmo=gizmo,
                        show_viewcube=controls,
                        mode="move" if revision == 1 else None,
                    )
                )
                state = viewport.navigation_cluster.diagnostic_state()
                self.assertEqual(state.gizmo.actor_visible, actor_visible)
                self.assertEqual(state.controls_visible, controls_visible)
                self.assertEqual(state.central_fallback_visible, fallback)
                self.assertEqual(
                    bool(viewport._transform_axes_actor.GetVisibility()),
                    revision == 1,
                )
            self.assertFalse(bool(viewport._rotation_ring_actor.GetVisibility()))
        finally:
            viewport.close()

    def test_layout_is_compact_in_bounds_nonoverlapping_and_dpi_safe(self) -> None:
        viewport = QtSceneViewport()
        try:
            for width, height in ((640, 400), (1100, 760)):
                viewport.resize(width, height)
                viewport.render_snapshot(_snapshot(revision=width))
                if not viewport.is_ready:
                    _ready_without_native_render(viewport)
                viewport.navigation_cluster.update_layout()
                x_value, y_value, cluster_width, cluster_height = (
                    viewport.navigation_cluster.logical_bounds
                )
                self.assertEqual((x_value, y_value), (GIZMO_LOGICAL_MARGIN,) * 2)
                self.assertEqual(cluster_width, NAVIGATION_CLUSTER_WIDTH)
                self.assertEqual(cluster_height, NAVIGATION_CLUSTER_HEIGHT)
                for button in viewport.view_controls.buttons.values():
                    self.assertTrue(viewport.rect().contains(button.geometry()))
                controls = list(viewport.view_controls.buttons.values())
                for index, first in enumerate(controls):
                    for second in controls[index + 1 :]:
                        self.assertFalse(first.geometry().intersects(second.geometry()))

            for ratio in (1.0, 1.25, 1.5):
                result = normalized_gizmo_viewport(
                    1200 * ratio,
                    800 * ratio,
                    ratio,
                    logical_left=GIZMO_LOGICAL_MARGIN + NAVIGATION_GIZMO_OFFSET,
                    logical_top=GIZMO_LOGICAL_MARGIN + NAVIGATION_GIZMO_OFFSET,
                )
                self.assertIsNotNone(result)
                x0, y0, x1, y1 = result
                self.assertTrue(0.0 <= x0 < x1 <= 1.0)
                self.assertTrue(0.0 <= y0 < y1 <= 1.0)
                self.assertAlmostEqual((x1 - x0) * 1200, GIZMO_LOGICAL_SIZE)
                self.assertAlmostEqual((y1 - y0) * 800, GIZMO_LOGICAL_SIZE)
        finally:
            viewport.close()

    def test_navigation_props_never_enter_primary_scene_or_world_bounds(self) -> None:
        viewport = QtSceneViewport()
        viewport.resize(700, 480)
        try:
            viewport.render_snapshot(_snapshot())
            _ready_without_native_render(viewport)
            main_props = viewport.renderer.GetViewProps()
            self.assertFalse(main_props.IsItemPresent(viewport._axis_gizmo_actor))
            self.assertEqual(
                viewport._axis_gizmo_renderer.GetViewProps().GetNumberOfItems(),
                1,
            )
            self.assertFalse(bool(viewport._axis_gizmo_actor.GetPickable()))
            self.assertIsNot(
                viewport.renderer.GetActiveCamera(),
                viewport._axis_gizmo_renderer.GetActiveCamera(),
            )
            bounds_before = viewport.last_snapshot.visible_bounds()
            viewport.view_controls.central_button.click()
            self.assertEqual(viewport.last_snapshot.visible_bounds(), bounds_before)
        finally:
            viewport.close()


class Task82ECameraRollTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _controller(self) -> tuple[CameraController, object]:
        from vtkmodules.vtkRenderingCore import vtkRenderer

        renderer = vtkRenderer()
        camera = renderer.GetActiveCamera()
        camera.SetPosition(3.0, -4.0, 5.0)
        camera.SetFocalPoint(0.5, 0.25, -0.75)
        camera.SetViewUp(0.2, 0.9, 0.3)
        camera.OrthogonalizeViewUp()
        camera.ParallelProjectionOn()
        camera.SetParallelScale(7.25)
        return CameraController(renderer), camera

    def test_roll_preserves_pose_distance_projection_and_changes_only_view_up(self) -> None:
        for parallel_projection in (True, False):
            with self.subTest(parallel_projection=parallel_projection):
                controller, camera = self._controller()
                if not parallel_projection:
                    camera.ParallelProjectionOff()
                before = _camera_state(camera)
                self.assertTrue(controller.roll(15.0))
                after = _camera_state(camera)
                np.testing.assert_allclose(after["position"], before["position"])
                np.testing.assert_allclose(after["focal"], before["focal"])
                self.assertAlmostEqual(after["distance"], before["distance"])
                self.assertEqual(after["parallel"], before["parallel"])
                self.assertAlmostEqual(after["parallel_scale"], before["parallel_scale"])
                self.assertFalse(np.allclose(after["view_up"], before["view_up"]))
                self.assertTrue(np.all(np.isfinite(after["view_up"])))
                self.assertAlmostEqual(float(np.linalg.norm(after["view_up"])), 1.0)
                self.assertAlmostEqual(
                    float(np.dot(after["view_up"], after["direction"])),
                    0.0,
                )

    def test_equal_left_right_and_repeated_rolls_are_stable(self) -> None:
        controller, camera = self._controller()
        original = _camera_state(camera)["view_up"]
        self.assertTrue(controller.roll(-15.0))
        self.assertTrue(controller.roll(15.0))
        np.testing.assert_allclose(camera.GetViewUp(), original, atol=1e-12)
        for _index in range(48):
            self.assertTrue(controller.roll(15.0))
        final = _camera_state(camera)
        self.assertTrue(np.all(np.isfinite(final["view_up"])))
        self.assertAlmostEqual(float(np.dot(final["view_up"], final["direction"])), 0.0)

    def test_camera_request_and_registered_actions_dispatch_through_application(self) -> None:
        registry = create_core_action_registry()
        self.assertIsNotNone(registry.get("view.roll_left"))
        self.assertIsNotNone(registry.get("view.roll_right"))
        request = CameraRequest.roll(15.0)
        self.assertEqual(request.roll_degrees, 15.0)

        window = OpenRetopV3Window(
            create_application(settings_repository=InMemorySettingsRepository())
        )
        try:
            window.viewport.resize(700, 480)
            _ready_without_native_render(window.viewport)
            camera = window.viewport.renderer.GetActiveCamera()
            before = _camera_state(camera)
            signature_before = window.viewport.orientation_gizmo.camera_signature
            with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}), patch.object(
                window.viewport,
                "_renderer_has_size",
                return_value=True,
            ):
                self.assertTrue(window._dispatch_framework_action("view.roll_right"))
            after = _camera_state(camera)
            np.testing.assert_allclose(after["position"], before["position"])
            np.testing.assert_allclose(after["focal"], before["focal"])
            self.assertFalse(np.allclose(after["view_up"], before["view_up"]))
            self.assertNotEqual(
                window.viewport.orientation_gizmo.camera_signature,
                signature_before,
            )
            with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}), patch.object(
                window.viewport,
                "_renderer_has_size",
                return_value=True,
            ):
                self.assertTrue(window._dispatch_framework_action("view.roll_left"))
            np.testing.assert_allclose(camera.GetViewUp(), before["view_up"], atol=1e-12)
        finally:
            window.set_project_dirty(False)
            window.close()


class Task82EVisibleWindowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @unittest.skipIf(
        os.environ.get("QT_QPA_PLATFORM", "").strip().lower() == "offscreen"
        or platform.system() != "Windows",
        "requires the visible Windows Qt/VTK path",
    )
    def test_real_win32_pixels_controls_roll_and_window_states(self) -> None:
        from vtkmodules.util.numpy_support import vtk_to_numpy
        from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter

        viewport = QtSceneViewport()
        viewport.resize(820, 580)
        viewport.render_snapshot(
            _snapshot(camera_request=CameraRequest.named_view("isometric"))
        )
        viewport.show()
        try:
            self.assertTrue(viewport.start())
            QTest.qWait(180)
            self.assertEqual(
                viewport.render_window.GetClassName(),
                "vtkWin32OpenGLRenderWindow",
            )
            state = viewport.navigation_cluster.diagnostic_state()
            self.assertTrue(state.gizmo.renderer_attached)
            self.assertTrue(state.gizmo.renderer_transparent)
            self.assertEqual(state.directional_button_count, 4)
            self.assertEqual(state.roll_button_count, 2)

            capture = vtkWindowToImageFilter()
            capture.SetInput(viewport.render_window)
            capture.ReadFrontBufferOff()
            capture.SetInputBufferTypeToRGBA()
            capture.Update()
            image = capture.GetOutput()
            width, height, _depth = image.GetDimensions()
            pixels = vtk_to_numpy(image.GetPointData().GetScalars()).reshape(
                height, width, 4
            )
            x0, y0, x1, y1 = viewport._axis_gizmo_renderer.GetViewport()
            region = pixels[
                int(y0 * height) : max(int(y1 * height), int(y0 * height) + 1),
                int(x0 * width) : max(int(x1 * width), int(x0 * width) + 1),
                :3,
            ]
            red = (region[..., 0] > 140) & (region[..., 1] < 140) & (region[..., 2] < 140)
            green = (region[..., 1] > 140) & (region[..., 0] < 160) & (region[..., 2] < 160)
            blue = (region[..., 2] > 140) & (region[..., 0] < 160) & (region[..., 1] < 190)
            white = np.all(region > 235, axis=2)
            combined = red | green | blue
            rows, columns = np.nonzero(combined)
            counts = tuple(int(np.count_nonzero(mask)) for mask in (red, green, blue, white))
            bounds = (
                int(columns.min()),
                int(rows.min()),
                int(columns.max()),
                int(rows.max()),
            )
            capture.SetInput(None)
            del pixels, image, capture
            self.assertGreater(counts[0], 20)
            self.assertGreater(counts[1], 20)
            self.assertGreater(counts[2], 20)
            self.assertEqual(counts[3], 0)
            self.assertGreaterEqual(bounds[2] - bounds[0] + 1, 55)
            self.assertGreaterEqual(bounds[3] - bounds[1] + 1, 55)

            actions: list[str] = []
            viewport.view_controls.action_requested.connect(actions.append)
            viewport.view_controls.central_button.click()
            viewport.view_controls.direction_buttons["view.named.top"].click()
            viewport.view_controls.roll_buttons["view.roll_left"].click()
            self.assertEqual(
                actions,
                ["view.named.isometric", "view.named.top", "view.roll_left"],
            )

            actor = viewport._axis_gizmo_actor
            renderer = viewport._axis_gizmo_renderer
            viewport.resize(1100, 760)
            QTest.qWait(80)
            viewport.showMaximized()
            QTest.qWait(80)
            viewport.showNormal()
            QTest.qWait(80)
            viewport.showMinimized()
            QTest.qWait(60)
            viewport.showNormal()
            QTest.qWait(80)
            self.assertTrue(viewport.render())
            final = viewport.navigation_cluster.diagnostic_state()
            self.assertIs(viewport._axis_gizmo_actor, actor)
            self.assertIs(viewport._axis_gizmo_renderer, renderer)
            self.assertEqual(final.gizmo.creation_count, 1)
            self.assertEqual(final.gizmo.observer_count, 1)
            self.assertIsNone(final.last_error)
            self.assertIsNone(viewport.diagnostic_state().last_rendering_error)
        finally:
            viewport.close()


if __name__ == "__main__":
    unittest.main()
