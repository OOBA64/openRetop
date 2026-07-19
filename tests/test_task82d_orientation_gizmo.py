from __future__ import annotations

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

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from application.scene_ids import NODE_MESH  # noqa: E402
from bootstrap import create_application  # noqa: E402
from infrastructure.settings_repository import InMemorySettingsRepository  # noqa: E402
from mesh.triangle_mesh import TriangleMeshData  # noqa: E402
from presentation.qt.orientation_gizmo import (  # noqa: E402
    GIZMO_LOGICAL_MARGIN,
    GIZMO_LOGICAL_SIZE,
    normalized_camera_orientation,
    normalized_gizmo_viewport,
)
from presentation.qt.main_window import OpenRetopV3Window  # noqa: E402
from presentation.qt.viewport import QtSceneViewport  # noqa: E402
from viewer.scene_types import CameraRequest, MeshRenderItem, SceneSnapshot  # noqa: E402


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
    show_axes: bool = True,
    mode: str | None = None,
    axis: str | None = None,
    origin: tuple[float, float, float] | None = None,
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
            "show_axes": show_axes,
            "show_axis_gizmo": show_axis_gizmo,
            "show_viewcube": show_viewcube,
            "display_colors": {"background_color": "#101316"},
        },
        camera_request=camera_request or CameraRequest(),
        object_origin=origin,
        active_transform_mode=mode,
        active_transform_axis=axis,
    )


def _ready_without_native_render(viewport: QtSceneViewport) -> None:
    with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
        viewport._is_ready = True
        viewport.ready.emit()


def _mouse_event(
    event_type: QEvent.Type,
    position: tuple[float, float],
    *,
    button: Qt.MouseButton,
    buttons: Qt.MouseButton,
) -> QMouseEvent:
    point = QPointF(*position)
    return QMouseEvent(
        event_type,
        point,
        point,
        button,
        buttons,
        Qt.NoModifier,
    )


def _renderers(render_window: object) -> tuple[object, ...]:
    collection = render_window.GetRenderers()
    collection.InitTraversal()
    result = []
    while True:
        renderer = collection.GetNextItem()
        if renderer is None:
            return tuple(result)
        result.append(renderer)


def _main_props(viewport: QtSceneViewport) -> tuple[object, ...]:
    collection = viewport.renderer.GetViewProps()
    collection.InitTraversal()
    result = []
    while True:
        prop = collection.GetNextProp()
        if prop is None:
            return tuple(result)
        result.append(prop)


def _logical_viewport_size(viewport: QtSceneViewport) -> tuple[float, float]:
    x0, y0, x1, y1 = viewport._axis_gizmo_renderer.GetViewport()
    width, height = viewport.render_window.GetSize()
    ratio = max(float(viewport.devicePixelRatioF()), 1.0)
    return ((x1 - x0) * width / ratio, (y1 - y0) * height / ratio)


class Task82DGizmoLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_controller_creates_attaches_and_reuses_one_renderer_and_actor(self) -> None:
        viewport = QtSceneViewport()
        try:
            self.assertEqual(viewport.render_window.GetRenderers().GetNumberOfItems(), 1)
            viewport.render_snapshot(_snapshot())
            _ready_without_native_render(viewport)
            controller = viewport.orientation_gizmo
            renderer = controller.renderer
            actor = controller.actor
            state = controller.diagnostic_state()
            self.assertTrue(state.renderer_attached)
            self.assertEqual(state.creation_count, 1)
            self.assertEqual(state.renderer_creation_count, 1)
            self.assertEqual(state.actor_creation_count, 1)
            self.assertEqual(viewport.render_window.GetRenderers().GetNumberOfItems(), 2)
            viewport.ready.emit()
            viewport.render_snapshot(_snapshot(revision=2))
            self.assertIs(controller.renderer, renderer)
            self.assertIs(controller.actor, actor)
            self.assertEqual(controller.diagnostic_state().creation_count, 1)
            self.assertEqual(viewport.render_window.GetRenderers().GetNumberOfItems(), 2)
        finally:
            viewport.close()

    def test_layers_are_nonconflicting_and_only_increased_when_needed(self) -> None:
        from vtkmodules.vtkRenderingCore import vtkRenderer

        viewport = QtSceneViewport()
        occupied = vtkRenderer()
        occupied.SetLayer(1)
        viewport.render_window.SetNumberOfLayers(3)
        viewport.render_window.AddRenderer(occupied)
        try:
            viewport.render_snapshot(_snapshot())
            _ready_without_native_render(viewport)
            self.assertEqual(viewport.renderer.GetLayer(), 0)
            self.assertEqual(viewport._axis_gizmo_renderer.GetLayer(), 2)
            self.assertEqual(viewport.render_window.GetNumberOfLayers(), 3)
            self.assertEqual(len(_renderers(viewport.render_window)), 3)
        finally:
            viewport.close()

    def test_renderer_is_transparent_noninteractive_and_actor_is_nonpickable(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.render_snapshot(_snapshot())
            _ready_without_native_render(viewport)
            state = viewport.orientation_gizmo.diagnostic_state()
            self.assertEqual(state.renderer_layer, 1)
            self.assertFalse(state.renderer_interactive)
            self.assertTrue(state.renderer_transparent)
            self.assertTrue(state.renderer_draw)
            self.assertTrue(state.actor_visible)
            self.assertFalse(state.actor_pickable)
            self.assertFalse(bool(viewport._axis_gizmo_renderer.GetErase()))
            self.assertEqual(
                viewport._axis_gizmo_renderer.GetViewProps().GetNumberOfItems(),
                1,
            )
            self.assertEqual(
                viewport._axis_gizmo_actor.GetClassName(),
                "vtkAxesActor",
            )
            self.assertIsNone(state.last_error)
        finally:
            viewport.close()

    def test_accepted_main_window_close_runs_viewport_shutdown_once(self) -> None:
        window = OpenRetopV3Window(
            create_application(settings_repository=InMemorySettingsRepository())
        )
        _ready_without_native_render(window.viewport)
        self.assertEqual(window.viewport.orientation_gizmo.observer_count, 1)

        window.set_project_dirty(False)
        self.assertTrue(window.close())
        self.assertEqual(window.viewport.orientation_gizmo.observer_count, 0)
        self.assertTrue(window.viewport._finalized)

    def test_visibility_view_controls_and_transform_overlays_are_independent(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.render_snapshot(
                _snapshot(show_axis_gizmo=False, show_viewcube=True)
            )
            _ready_without_native_render(viewport)
            renderer = viewport._axis_gizmo_renderer
            actor = viewport._axis_gizmo_actor
            self.assertFalse(viewport.orientation_gizmo.enabled)
            self.assertFalse(bool(renderer.GetDraw()))
            self.assertTrue(viewport.view_controls.visible)

            viewport.render_snapshot(
                _snapshot(
                    revision=2,
                    show_axis_gizmo=True,
                    show_viewcube=False,
                    mode="move",
                    axis="X",
                    origin=(4.0, 5.0, 6.0),
                )
            )
            self.assertTrue(viewport.orientation_gizmo.enabled)
            self.assertTrue(bool(renderer.GetDraw()))
            self.assertFalse(viewport.view_controls.visible)
            self.assertTrue(bool(viewport._transform_axes_actor.GetVisibility()))
            self.assertIs(viewport._axis_gizmo_renderer, renderer)
            self.assertIs(viewport._axis_gizmo_actor, actor)

            viewport.render_snapshot(
                _snapshot(revision=3, show_axis_gizmo=True, show_viewcube=False)
            )
            self.assertFalse(bool(viewport._transform_axes_actor.GetVisibility()))
            self.assertTrue(bool(viewport._axis_gizmo_actor.GetVisibility()))
        finally:
            viewport.close()

    def test_gizmo_is_excluded_from_main_props_bounds_and_picking(self) -> None:
        viewport = QtSceneViewport()
        snapshot = _snapshot()
        try:
            viewport.render_snapshot(snapshot)
            _ready_without_native_render(viewport)
            self.assertNotIn(viewport._axis_gizmo_actor, _main_props(viewport))
            self.assertEqual(snapshot.visible_bounds(), ((0.0, 0.0, 0.0), (2.0, 3.0, 0.0)))
            self.assertEqual(viewport.model_bounds(), snapshot.visible_bounds())
            self.assertFalse(bool(viewport._axis_gizmo_actor.GetPickable()))
            self.assertIs(viewport.picking.renderer, viewport.renderer)
            self.assertIsNot(
                viewport._axis_gizmo_renderer.GetActiveCamera(),
                viewport.renderer.GetActiveCamera(),
            )
        finally:
            viewport.close()

    def test_observer_is_installed_once_and_removed_with_renderer_on_close(self) -> None:
        viewport = QtSceneViewport()
        controller = viewport.orientation_gizmo
        try:
            viewport.render_snapshot(_snapshot())
            _ready_without_native_render(viewport)
            records = controller.observer_records
            self.assertEqual(controller.observer_count, 1)
            viewport.ready.emit()
            controller.start()
            self.assertEqual(controller.observer_records, records)
            self.assertEqual(controller.observer_count, 1)
            controller.close()
            self.assertEqual(controller.observer_count, 0)
            self.assertNotIn(controller.renderer, _renderers(viewport.render_window))
        finally:
            viewport.close()


class Task82DGizmoCameraAndLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_interaction_updates_orientation_but_pan_and_zoom_do_not(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.render_snapshot(_snapshot())
            _ready_without_native_render(viewport)
            controller = viewport.orientation_gizmo
            camera = viewport.renderer.GetActiveCamera()
            initial_signature = controller.camera_signature
            initial_count = controller.camera_update_count

            camera.SetPosition(4.0, -3.0, 6.0)
            camera.SetFocalPoint(0.0, 0.0, 0.0)
            camera.SetViewUp(0.2, 1.0, 0.1)
            viewport.interactor.InvokeEvent("InteractionEvent")
            self.assertNotEqual(controller.camera_signature, initial_signature)
            self.assertGreater(controller.camera_update_count, initial_count)
            oriented_signature = controller.camera_signature
            oriented_count = controller.camera_update_count

            delta = np.asarray((1.5, -2.0, 0.75), dtype=float)
            camera.SetPosition(*(np.asarray(camera.GetPosition()) + delta))
            camera.SetFocalPoint(*(np.asarray(camera.GetFocalPoint()) + delta))
            viewport.interactor.InvokeEvent("InteractionEvent")
            self.assertEqual(controller.camera_signature, oriented_signature)
            self.assertEqual(controller.camera_update_count, oriented_count)

            direction = np.asarray(camera.GetDirectionOfProjection(), dtype=float)
            camera.SetPosition(*(np.asarray(camera.GetPosition()) + direction))
            viewport.interactor.InvokeEvent("InteractionEvent")
            self.assertEqual(controller.camera_signature, oriented_signature)
            self.assertEqual(controller.camera_update_count, oriented_count)
        finally:
            viewport.close()

    def test_named_views_update_camera_without_recreating_gizmo(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.render_snapshot(_snapshot())
            _ready_without_native_render(viewport)
            actor = viewport._axis_gizmo_actor
            renderer = viewport._axis_gizmo_renderer
            signatures = []
            with patch.object(viewport, "_renderer_has_size", return_value=True):
                for revision, name in enumerate(
                    ("top", "front", "right", "isometric"),
                    start=2,
                ):
                    viewport.render_snapshot(
                        _snapshot(
                            revision=revision,
                            camera_request=CameraRequest.named_view(name),
                        )
                    )
                    signatures.append(viewport.orientation_gizmo.camera_signature)
                    self.assertIs(viewport._axis_gizmo_actor, actor)
                    self.assertIs(viewport._axis_gizmo_renderer, renderer)
            self.assertEqual(len(set(signatures)), len(signatures))
            self.assertEqual(viewport.orientation_gizmo.diagnostic_state().creation_count, 1)
        finally:
            viewport.close()

    def test_layout_is_fixed_logical_size_finite_and_in_bounds(self) -> None:
        for width, height, ratio in (
            (800, 600, 1.0),
            (2400, 1600, 1.0),
            (2400, 1600, 2.5),
        ):
            result = normalized_gizmo_viewport(width, height, ratio)
            self.assertIsNotNone(result)
            x0, y0, x1, y1 = result
            self.assertTrue(all(np.isfinite(result)))
            self.assertTrue(0.0 <= x0 < x1 <= 1.0)
            self.assertTrue(0.0 <= y0 < y1 <= 1.0)
            self.assertAlmostEqual((x1 - x0) * width / ratio, GIZMO_LOGICAL_SIZE)
            self.assertAlmostEqual((y1 - y0) * height / ratio, GIZMO_LOGICAL_SIZE)
            self.assertAlmostEqual(x0 * width / ratio, GIZMO_LOGICAL_MARGIN)
            self.assertAlmostEqual((1.0 - y1) * height / ratio, GIZMO_LOGICAL_MARGIN)
        self.assertIsNone(normalized_gizmo_viewport(0, 600, 1.0))
        self.assertIsNone(normalized_gizmo_viewport(800, 0, 1.0))
        self.assertIsNone(normalized_gizmo_viewport(800, 600, float("nan")))

    def test_camera_basis_is_finite_normalized_and_orthogonal(self) -> None:
        orientation = normalized_camera_orientation(
            (1.0, 2.0, -3.0),
            (0.1, 1.0, 0.2),
        )
        self.assertIsNotNone(orientation)
        forward, up = orientation
        self.assertAlmostEqual(float(np.linalg.norm(forward)), 1.0)
        self.assertAlmostEqual(float(np.linalg.norm(up)), 1.0)
        self.assertAlmostEqual(float(np.dot(forward, up)), 0.0)
        self.assertIsNone(normalized_camera_orientation((0, 0, 0), (0, 1, 0)))

    def test_gizmo_area_does_not_intercept_native_pointer_input(self) -> None:
        viewport = QtSceneViewport()
        events = []
        viewport.pointer_event.connect(
            lambda name, _x, _y, _pick: events.append(name)
        )
        try:
            viewport.render_snapshot(_snapshot(show_viewcube=True))
            _ready_without_native_render(viewport)
            for event in (
                _mouse_event(
                    QEvent.MouseButtonPress,
                    (35.0, 35.0),
                    button=Qt.LeftButton,
                    buttons=Qt.LeftButton,
                ),
                _mouse_event(
                    QEvent.MouseMove,
                    (60.0, 45.0),
                    button=Qt.NoButton,
                    buttons=Qt.LeftButton,
                ),
                _mouse_event(
                    QEvent.MouseButtonRelease,
                    (60.0, 45.0),
                    button=Qt.LeftButton,
                    buttons=Qt.NoButton,
                ),
            ):
                self.assertFalse(viewport.eventFilter(viewport.interactor, event))
            self.assertEqual(events, [])
            self.assertFalse(viewport.last_pointer_release_was_click)
            for control in viewport.view_controls.buttons.values():
                self.assertFalse(control.geometry().contains(QPoint(35, 35)))
        finally:
            viewport.close()


class Task82DVisibleWindowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @unittest.skipIf(
        os.environ.get("QT_QPA_PLATFORM", "").strip().lower() == "offscreen"
        or platform.system() != "Windows",
        "requires the visible Windows Qt/VTK path",
    )
    def test_real_win32_pixels_orbit_pan_zoom_resize_and_restore(self) -> None:
        from vtkmodules.util.numpy_support import vtk_to_numpy
        from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter

        viewport = QtSceneViewport()
        viewport.resize(760, 520)
        viewport.render_snapshot(
            _snapshot(
                show_viewcube=True,
                camera_request=CameraRequest.named_view("isometric"),
            )
        )
        viewport.show()
        try:
            self.assertTrue(viewport.start())
            QTest.qWait(180)
            self.assertEqual(
                viewport.render_window.GetClassName(),
                "vtkWin32OpenGLRenderWindow",
            )
            controller = viewport.orientation_gizmo
            state = controller.diagnostic_state()
            self.assertTrue(state.renderer_attached)
            self.assertTrue(state.renderer_transparent)
            self.assertEqual(state.renderer_layer, 1)
            self.assertEqual(state.creation_count, 1)

            capture = vtkWindowToImageFilter()
            capture.SetInput(viewport.render_window)
            capture.ReadFrontBufferOff()
            capture.SetInputBufferTypeToRGBA()
            capture.Update()
            image = capture.GetOutput()
            width, height, _depth = image.GetDimensions()
            pixels = vtk_to_numpy(image.GetPointData().GetScalars()).reshape(
                (height, width, 4)
            )
            x0, y0, x1, y1 = viewport._axis_gizmo_renderer.GetViewport()
            region = pixels[
                int(y0 * height) : max(int(y1 * height), int(y0 * height) + 1),
                int(x0 * width) : max(int(x1 * width), int(x0 * width) + 1),
                :3,
            ]
            red = (region[..., 0] > 140) & (region[..., 1] < 130) & (region[..., 2] < 130)
            green = (region[..., 1] > 140) & (region[..., 0] < 150) & (region[..., 2] < 150)
            blue = (region[..., 2] > 140) & (region[..., 0] < 150) & (region[..., 1] < 180)
            white = np.all(region > 235, axis=2)
            pixel_counts = tuple(
                int(np.count_nonzero(mask)) for mask in (red, green, blue, white)
            )
            # vtkWindowToImageFilter retains its input render window.  Break the
            # pipeline and release every output-backed NumPy view while the
            # native Win32 context is still alive so VTK cannot attempt a late
            # WGL cleanup after QApplication teardown.
            capture.SetInput(None)
            del region, pixels, image, capture
            self.assertGreater(pixel_counts[0], 12)
            self.assertGreater(pixel_counts[1], 12)
            self.assertGreater(pixel_counts[2], 12)
            self.assertEqual(pixel_counts[3], 0)

            actor = controller.actor
            renderer = controller.renderer
            camera = viewport.renderer.GetActiveCamera()
            direction_before = np.asarray(camera.GetDirectionOfProjection(), dtype=float)
            signature_before = controller.camera_signature
            start = QPoint(35, 35)
            QTest.mousePress(viewport.interactor, Qt.LeftButton, Qt.NoModifier, start)
            QTest.mouseMove(viewport.interactor, start + QPoint(55, 25), 40)
            QTest.mouseRelease(
                viewport.interactor,
                Qt.LeftButton,
                Qt.NoModifier,
                start + QPoint(55, 25),
            )
            self.assertFalse(
                np.allclose(direction_before, camera.GetDirectionOfProjection())
            )
            self.assertNotEqual(controller.camera_signature, signature_before)
            self.assertIs(controller.actor, actor)
            self.assertIs(controller.renderer, renderer)

            signature_before = controller.camera_signature
            target = viewport.interactor.rect().center()
            QTest.mousePress(viewport.interactor, Qt.MiddleButton, Qt.NoModifier, target)
            QTest.mouseMove(viewport.interactor, target + QPoint(40, 20), 35)
            QTest.mouseRelease(
                viewport.interactor,
                Qt.MiddleButton,
                Qt.NoModifier,
                target + QPoint(40, 20),
            )
            self.assertEqual(controller.camera_signature, signature_before)
            viewport.interactor.SetEventInformation(target.x(), target.y())
            viewport.interactor.MouseWheelForwardEvent()
            self.assertEqual(controller.camera_signature, signature_before)

            first_size = _logical_viewport_size(viewport)
            viewport.resize(1100, 760)
            QTest.qWait(100)
            second_size = _logical_viewport_size(viewport)
            for measured in (*first_size, *second_size):
                self.assertAlmostEqual(measured, GIZMO_LOGICAL_SIZE, delta=3.0)
            self.assertIs(controller.actor, actor)
            self.assertIs(controller.renderer, renderer)

            viewport.showMaximized()
            QTest.qWait(100)
            viewport.showNormal()
            QTest.qWait(100)
            viewport.showMinimized()
            QTest.qWait(75)
            viewport.showNormal()
            QTest.qWait(100)
            self.assertTrue(viewport.render())
            final = controller.diagnostic_state()
            self.assertTrue(final.renderer_attached)
            self.assertTrue(final.renderer_draw)
            self.assertEqual(final.creation_count, 1)
            self.assertEqual(final.observer_count, 1)
            self.assertIsNone(final.last_error)
            self.assertIsNone(viewport.diagnostic_state().last_rendering_error)
        finally:
            viewport.close()


if __name__ == "__main__":
    unittest.main()
