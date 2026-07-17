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

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent, QWheelEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from application.scene_ids import NODE_MESH, section_plane_node_id  # noqa: E402
from application.state import MeshObjectState  # noqa: E402
from bootstrap import create_application  # noqa: E402
from infrastructure.settings_repository import InMemorySettingsRepository  # noqa: E402
from mesh.triangle_mesh import TriangleMeshData  # noqa: E402
from presentation.qt.main_window import OpenRetopV3Window  # noqa: E402
from presentation.qt.pointer_gestures import PointerGestureState  # noqa: E402
from presentation.qt.viewport import QtSceneViewport  # noqa: E402
from viewer.picking_service import SceneObjectPickResult  # noqa: E402
from viewer.scene_types import CameraRequest  # noqa: E402
from workbench_ui.viewport import VTKViewportWidget  # noqa: E402


def _mesh() -> TriangleMeshData:
    return TriangleMeshData(
        vertices=np.asarray(
            [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 3.0, 0.0]],
            dtype=float,
        ),
        triangles=np.asarray([[0, 1, 2]], dtype=int),
    )


def _mesh_object() -> MeshObjectState:
    mesh = _mesh()
    return MeshObjectState(
        source_mesh=mesh,
        display_mesh=mesh.copy(),
        file_path=None,
        name="Mesh",
        origin=np.zeros(3),
        location=np.zeros(3),
        rotation=np.zeros(3),
        transform_matrix=np.identity(4),
    )


def _window() -> OpenRetopV3Window:
    composition = create_application(
        settings_repository=InMemorySettingsRepository()
    )
    composition.state.mesh_object = _mesh_object()
    window = OpenRetopV3Window(composition)
    window.refresh()
    return window


def _mouse_event(
    event_type: QEvent.Type,
    position: tuple[float, float],
    *,
    button: Qt.MouseButton,
    buttons: Qt.MouseButton,
    modifiers: Qt.KeyboardModifier = Qt.NoModifier,
) -> QMouseEvent:
    point = QPointF(*position)
    return QMouseEvent(
        event_type,
        point,
        point,
        button,
        buttons,
        modifiers,
    )


def _camera_state(camera: object) -> tuple[float, ...]:
    position = tuple(float(value) for value in camera.GetPosition())
    focal = tuple(float(value) for value in camera.GetFocalPoint())
    view_up = tuple(float(value) for value in camera.GetViewUp())
    direction = tuple(float(value) for value in camera.GetDirectionOfProjection())
    distance = float(np.linalg.norm(np.asarray(position) - np.asarray(focal)))
    return (*position, *focal, *view_up, *direction, distance, float(camera.GetParallelScale()))


def _project_to_qt(viewport: QtSceneViewport, point: tuple[float, float, float]) -> QPoint:
    renderer = viewport.renderer
    renderer.SetWorldPoint(*point, 1.0)
    renderer.WorldToDisplay()
    x_position, y_position, _depth = renderer.GetDisplayPoint()
    return QPoint(
        int(round(x_position)),
        max(viewport.interactor.height() - int(round(y_position)) - 1, 0),
    )


class Task82CGestureStateTests(unittest.TestCase):
    def test_state_records_button_distance_native_owner_and_selection_eligibility(self) -> None:
        gesture = PointerGestureState(4.0)
        gesture.press(
            10.0,
            10.0,
            button="left",
            native_navigation_started=True,
        )
        self.assertEqual(gesture.press_button, "left")
        self.assertTrue(gesture.native_navigation_started)
        self.assertTrue(gesture.selection_eligible)
        gesture.motion(12.0, 10.0)
        gesture.motion(15.0, 10.0)
        self.assertEqual(gesture.accumulated_distance, 5.0)
        self.assertTrue(gesture.dragged)
        self.assertFalse(gesture.selection_eligible)
        release = gesture.release(15.0, 10.0)
        self.assertFalse(release.is_click)
        self.assertTrue(release.native_navigation_started)
        self.assertEqual(release.distance, 5.0)

    def test_tool_owned_left_gesture_is_never_selection_eligible(self) -> None:
        gesture = PointerGestureState(4.0)
        gesture.press(2.0, 3.0, active_tool_owner="manual_curve")
        release = gesture.release(2.0, 3.0)
        self.assertEqual(release.active_tool_owner, "manual_curve")
        self.assertFalse(release.native_navigation_started)
        self.assertFalse(release.selection_eligible)
        self.assertFalse(release.is_click)

    def test_four_logical_pixel_click_threshold_remains_inclusive(self) -> None:
        gesture = PointerGestureState(4.0)
        gesture.press(0.0, 0.0)
        self.assertTrue(gesture.release(4.0, 0.0).is_click)
        gesture.press(0.0, 0.0)
        self.assertFalse(gesture.release(4.01, 0.0).is_click)


class Task82CRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_trackball_camera_style_remains_installed_once(self) -> None:
        viewport = VTKViewportWidget()
        try:
            style = viewport.interactor.GetInteractorStyle()
            self.assertEqual(style.GetClassName(), "vtkInteractorStyleTrackballCamera")
            with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
                viewport.start()
                viewport.start()
            self.assertIs(viewport.interactor.GetInteractorStyle(), style)
        finally:
            viewport.close()

    def test_native_left_drag_is_not_consumed_emitted_or_picked(self) -> None:
        viewport = QtSceneViewport()
        events: list[str] = []
        viewport.pointer_event.connect(
            lambda name, _x, _y, _pick: events.append(name)
        )
        try:
            press = _mouse_event(
                QEvent.MouseButtonPress,
                (10.0, 10.0),
                button=Qt.LeftButton,
                buttons=Qt.LeftButton,
            )
            motion = _mouse_event(
                QEvent.MouseMove,
                (30.0, 20.0),
                button=Qt.NoButton,
                buttons=Qt.LeftButton,
            )
            release = _mouse_event(
                QEvent.MouseButtonRelease,
                (30.0, 20.0),
                button=Qt.LeftButton,
                buttons=Qt.NoButton,
            )
            self.assertFalse(viewport.eventFilter(viewport.interactor, press))
            during = viewport.diagnostic_state()
            self.assertTrue(during.native_navigation_started)
            self.assertTrue(during.selection_eligible)
            self.assertFalse(viewport.eventFilter(viewport.interactor, motion))
            self.assertFalse(viewport.diagnostic_state().selection_eligible)
            self.assertFalse(viewport.eventFilter(viewport.interactor, release))
            self.app.processEvents()
            self.assertEqual(events, [])
            self.assertEqual(viewport.diagnostic_state().pick_count, 0)
            self.assertFalse(viewport.last_pointer_release_was_click)
        finally:
            viewport.close()

    def test_true_click_is_deferred_until_after_native_release(self) -> None:
        viewport = QtSceneViewport()
        events: list[str] = []
        viewport.pointer_event.connect(
            lambda name, _x, _y, _pick: events.append(name)
        )
        try:
            self.assertFalse(
                viewport.eventFilter(
                    viewport.interactor,
                    _mouse_event(
                        QEvent.MouseButtonPress,
                        (15.0, 15.0),
                        button=Qt.LeftButton,
                        buttons=Qt.LeftButton,
                    ),
                )
            )
            self.assertFalse(
                viewport.eventFilter(
                    viewport.interactor,
                    _mouse_event(
                        QEvent.MouseButtonRelease,
                        (15.0, 15.0),
                        button=Qt.LeftButton,
                        buttons=Qt.NoButton,
                    ),
                )
            )
            self.assertEqual(events, [])
            self.app.processEvents()
            self.assertEqual(events, ["left_release"])
            self.assertTrue(viewport.last_pointer_release_was_click)
        finally:
            viewport.close()

    def test_one_click_performs_only_one_final_scene_pick_and_selects(self) -> None:
        window = _window()
        try:
            pick = SceneObjectPickResult(
                hit=True,
                object_id="mesh",
                object_type="mesh",
            )
            with patch.object(
                window.viewport,
                "pick_scene_object",
                return_value=pick,
            ) as scene_pick, patch.dict(
                os.environ,
                {"QT_QPA_PLATFORM": "offscreen"},
            ):
                window.viewport.eventFilter(
                    window.viewport.interactor,
                    _mouse_event(
                        QEvent.MouseButtonPress,
                        (20.0, 20.0),
                        button=Qt.LeftButton,
                        buttons=Qt.LeftButton,
                    ),
                )
                window.viewport.eventFilter(
                    window.viewport.interactor,
                    _mouse_event(
                        QEvent.MouseButtonRelease,
                        (20.0, 20.0),
                        button=Qt.LeftButton,
                        buttons=Qt.NoButton,
                    ),
                )
                self.app.processEvents()
            scene_pick.assert_called_once_with(20, window.viewport.interactor.height() - 21)
            self.assertEqual(
                window.composition.selection_controller.snapshot().ids,
                (NODE_MESH,),
            )
        finally:
            window.set_project_dirty(False)
            window.close()

    def test_release_after_drag_never_picks_or_selects(self) -> None:
        window = _window()
        try:
            plane = window.composition.state.section_collection.planes[0]
            plane_node = section_plane_node_id(plane.id)
            window.composition.selection_controller.select_nodes((plane_node,))
            with patch.object(window.viewport, "pick_scene_object") as scene_pick:
                for event in (
                    _mouse_event(
                        QEvent.MouseButtonPress,
                        (20.0, 20.0),
                        button=Qt.LeftButton,
                        buttons=Qt.LeftButton,
                    ),
                    _mouse_event(
                        QEvent.MouseMove,
                        (40.0, 30.0),
                        button=Qt.NoButton,
                        buttons=Qt.LeftButton,
                    ),
                    _mouse_event(
                        QEvent.MouseButtonRelease,
                        (40.0, 30.0),
                        button=Qt.LeftButton,
                        buttons=Qt.NoButton,
                    ),
                ):
                    self.assertFalse(
                        window.viewport.eventFilter(window.viewport.interactor, event)
                    )
                self.app.processEvents()
            scene_pick.assert_not_called()
            self.assertEqual(
                window.composition.selection_controller.snapshot().ids,
                (plane_node,),
            )
        finally:
            window.set_project_dirty(False)
            window.close()

    def test_idle_motion_has_no_application_event_or_pick(self) -> None:
        viewport = QtSceneViewport()
        events: list[str] = []
        viewport.pointer_event.connect(
            lambda name, _x, _y, _pick: events.append(name)
        )
        try:
            for offset in range(8):
                self.assertFalse(
                    viewport.eventFilter(
                        viewport.interactor,
                        _mouse_event(
                            QEvent.MouseMove,
                            (30.0 + offset, 30.0),
                            button=Qt.NoButton,
                            buttons=Qt.NoButton,
                        ),
                    )
                )
            self.assertEqual(events, [])
            self.assertEqual(viewport.diagnostic_state().pick_count, 0)
        finally:
            viewport.close()

    def test_each_active_tool_owner_captures_the_complete_left_gesture(self) -> None:
        for owner in ("manual_curve", "region", "transform"):
            viewport = QtSceneViewport()
            events: list[str] = []
            viewport.pointer_event.connect(
                lambda name, _x, _y, _pick: events.append(name)
            )
            viewport.set_left_capture_owner(owner)
            try:
                for event in (
                    _mouse_event(
                        QEvent.MouseButtonPress,
                        (10.0, 10.0),
                        button=Qt.LeftButton,
                        buttons=Qt.LeftButton,
                    ),
                    _mouse_event(
                        QEvent.MouseMove,
                        (25.0, 20.0),
                        button=Qt.NoButton,
                        buttons=Qt.LeftButton,
                    ),
                    _mouse_event(
                        QEvent.MouseButtonRelease,
                        (25.0, 20.0),
                        button=Qt.LeftButton,
                        buttons=Qt.NoButton,
                    ),
                ):
                    self.assertTrue(viewport.eventFilter(viewport.interactor, event))
                self.assertEqual(events, ["left_press", "motion", "left_release"])
                self.assertFalse(viewport.last_pointer_release_was_click)
            finally:
                viewport.close()

    def test_middle_right_modified_left_and_wheel_remain_native_during_tools(self) -> None:
        viewport = QtSceneViewport()
        events: list[str] = []
        viewport.pointer_event.connect(
            lambda name, _x, _y, _pick: events.append(name)
        )
        viewport.set_left_capture_owner("manual_curve")
        try:
            for button, modifier in (
                (Qt.MiddleButton, Qt.NoModifier),
                (Qt.RightButton, Qt.NoModifier),
                (Qt.LeftButton, Qt.AltModifier),
                (Qt.LeftButton, Qt.ShiftModifier),
            ):
                self.assertFalse(
                    viewport.eventFilter(
                        viewport.interactor,
                        _mouse_event(
                            QEvent.MouseButtonPress,
                            (20.0, 20.0),
                            button=button,
                            buttons=button,
                            modifiers=modifier,
                        ),
                    )
                )
                self.assertFalse(
                    viewport.eventFilter(
                        viewport.interactor,
                        _mouse_event(
                            QEvent.MouseMove,
                            (30.0, 25.0),
                            button=Qt.NoButton,
                            buttons=button,
                            modifiers=modifier,
                        ),
                    )
                )
            self.assertEqual(events, [])
        finally:
            viewport.close()

    def test_main_window_assigns_only_the_current_left_capture_tool(self) -> None:
        window = _window()
        try:
            self.assertIsNone(window.viewport.left_capture_owner)
            window.composition.manual_curve_controller.begin_new_curve(
                plane_origin=(0.0, 0.0, 0.0),
                plane_normal=(0.0, 0.0, 1.0),
            )
            window.refresh()
            self.assertEqual(window.viewport.left_capture_owner, "manual_curve")
            window.composition.manual_curve_controller.cancel()
            window.composition.region_controller.start()
            window.refresh()
            self.assertEqual(window.viewport.left_capture_owner, "region")
            window.composition.region_controller.exit(status="Region Select finished")
            window.composition.selection_controller.select_nodes((NODE_MESH,))
            window.composition.transform_controller.start_move(mouse_start=(0.0, 0.0))
            window.refresh()
            self.assertEqual(window.viewport.left_capture_owner, "transform")
        finally:
            window.set_project_dirty(False)
            window.close()

    def test_region_tool_receives_the_complete_captured_left_sequence(self) -> None:
        window = _window()
        try:
            controller = window.composition.region_controller
            self.assertTrue(controller.start().success)
            window.refresh()
            self.assertEqual(window.viewport.left_capture_owner, "region")
            with patch.object(
                controller,
                "handle_pointer_event",
                wraps=controller.handle_pointer_event,
            ) as route:
                for event in (
                    _mouse_event(
                        QEvent.MouseButtonPress,
                        (20.0, 20.0),
                        button=Qt.LeftButton,
                        buttons=Qt.LeftButton,
                    ),
                    _mouse_event(
                        QEvent.MouseMove,
                        (35.0, 25.0),
                        button=Qt.NoButton,
                        buttons=Qt.LeftButton,
                    ),
                    _mouse_event(
                        QEvent.MouseButtonRelease,
                        (35.0, 25.0),
                        button=Qt.LeftButton,
                        buttons=Qt.NoButton,
                    ),
                ):
                    self.assertTrue(
                        window.viewport.eventFilter(window.viewport.interactor, event)
                    )
            self.assertEqual(
                [args[0] for args, _kwargs in route.call_args_list],
                ["left_press", "motion", "left_release"],
            )
        finally:
            window.set_project_dirty(False)
            window.close()

    def test_task82b_checkbox_visibility_still_preserves_selection(self) -> None:
        window = _window()
        try:
            plane = window.composition.state.section_collection.planes[0]
            plane_node = section_plane_node_id(plane.id)
            window.composition.selection_controller.select_nodes((plane_node,))
            before = window.composition.selection_controller.snapshot().ids
            with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
                window._on_tree_visibility(NODE_MESH, False)
            self.assertFalse(window.composition.state.mesh_object.visible)
            self.assertEqual(
                window.composition.selection_controller.snapshot().ids,
                before,
            )
        finally:
            window.set_project_dirty(False)
            window.close()


class Task82CVisibleWindowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @unittest.skipIf(
        os.environ.get("QT_QPA_PLATFORM", "").strip().lower() == "offscreen"
        or platform.system() != "Windows",
        "requires the visible Windows Qt/VTK path",
    )
    def test_real_win32_orbit_selection_pan_zoom_tools_and_repetition(self) -> None:
        window = _window()
        window.resize(900, 650)
        window.show()
        try:
            self.assertTrue(window.viewport.start())
            QTest.qWait(180)
            viewport = window.viewport
            interactor = viewport.interactor
            camera = viewport.renderer.GetActiveCamera()
            self.assertEqual(
                viewport.render_window.GetClassName(),
                "vtkWin32OpenGLRenderWindow",
            )
            self.assertEqual(
                interactor.GetInteractorStyle().GetClassName(),
                "vtkInteractorStyleTrackballCamera",
            )

            mesh_target = _project_to_qt(viewport, (0.65, 0.8, 0.0))
            vtk_y = interactor.height() - mesh_target.y() - 1
            self.assertTrue(
                viewport.pick_scene_object(mesh_target.x(), vtk_y).hit,
                "projected test point must begin over the mesh actor",
            )
            window.composition.selection_controller.clear()
            window.refresh()
            QTest.qWait(30)

            # Interactor styles may abort VTK observer propagation after they
            # handle an event. Count the public QVTK-to-interactor calls
            # instead; these are the actual native forwarding boundary.
            vtk_interactor = interactor._Iren
            counts = {"press": 0, "move": 0, "release": 0}
            original_press = vtk_interactor.LeftButtonPressEvent
            original_move = vtk_interactor.MouseMoveEvent
            original_release = vtk_interactor.LeftButtonReleaseEvent

            def forward_press() -> None:
                counts["press"] += 1
                original_press()

            def forward_move() -> None:
                counts["move"] += 1
                original_move()

            def forward_release() -> None:
                counts["release"] += 1
                original_release()

            vtk_interactor.LeftButtonPressEvent = forward_press
            vtk_interactor.MouseMoveEvent = forward_move
            vtk_interactor.LeftButtonReleaseEvent = forward_release
            before = _camera_state(camera)
            direction_before = np.asarray(camera.GetDirectionOfProjection(), dtype=float)
            selection_before = window.composition.selection_controller.snapshot().ids
            picks_before = viewport.diagnostic_state().pick_count
            sync_before = viewport.diagnostic_state().synchronization_count
            request_before = window._camera_request.kind
            try:
                with patch.object(window, "refresh", wraps=window.refresh) as refresh:
                    QTest.mousePress(
                        interactor,
                        Qt.LeftButton,
                        Qt.NoModifier,
                        mesh_target,
                    )
                    QTest.mouseMove(interactor, mesh_target + QPoint(72, 0), 45)
                    state_before_release = _camera_state(camera)
                    QTest.mouseRelease(
                        interactor,
                        Qt.LeftButton,
                        Qt.NoModifier,
                        mesh_target + QPoint(72, 0),
                    )
                    QTest.qWait(40)
                    refresh.assert_not_called()
            finally:
                vtk_interactor.LeftButtonPressEvent = original_press
                vtk_interactor.MouseMoveEvent = original_move
                vtk_interactor.LeftButtonReleaseEvent = original_release
            self.assertNotEqual(before, _camera_state(camera))
            self.assertFalse(
                np.allclose(direction_before, camera.GetDirectionOfProjection())
            )
            self.assertEqual(state_before_release, _camera_state(camera))
            self.assertEqual(
                window.composition.selection_controller.snapshot().ids,
                selection_before,
            )
            self.assertEqual(viewport.diagnostic_state().pick_count, picks_before)
            self.assertEqual(
                viewport.diagnostic_state().synchronization_count,
                sync_before,
            )
            self.assertEqual(window._camera_request.kind, request_before)
            self.assertEqual(request_before, CameraRequest().kind)
            self.assertEqual(counts, {"press": 1, "move": 1, "release": 1})

            vertical_start = interactor.rect().center()
            direction_before = np.asarray(camera.GetDirectionOfProjection(), dtype=float)
            QTest.mousePress(interactor, Qt.LeftButton, Qt.NoModifier, vertical_start)
            QTest.mouseMove(interactor, vertical_start + QPoint(0, 65), 45)
            QTest.mouseRelease(
                interactor,
                Qt.LeftButton,
                Qt.NoModifier,
                vertical_start + QPoint(0, 65),
            )
            self.assertFalse(
                np.allclose(direction_before, camera.GetDirectionOfProjection())
            )

            click_target = _project_to_qt(viewport, (0.65, 0.8, 0.0))
            vtk_y = interactor.height() - click_target.y() - 1
            self.assertTrue(viewport.pick_scene_object(click_target.x(), vtk_y).hit)
            window.composition.selection_controller.clear()
            window.refresh()
            picks_before = viewport.diagnostic_state().pick_count
            QTest.mouseClick(
                interactor,
                Qt.LeftButton,
                Qt.NoModifier,
                click_target,
            )
            QTest.qWait(60)
            self.assertEqual(
                window.composition.selection_controller.snapshot().ids,
                (NODE_MESH,),
            )
            self.assertEqual(viewport.diagnostic_state().pick_count, picks_before + 1)

            before = _camera_state(camera)
            target = interactor.rect().center()
            QTest.mousePress(interactor, Qt.MiddleButton, Qt.NoModifier, target)
            QTest.mouseMove(interactor, target + QPoint(45, 25), 35)
            QTest.mouseRelease(
                interactor,
                Qt.MiddleButton,
                Qt.NoModifier,
                target + QPoint(45, 25),
            )
            self.assertNotEqual(before, _camera_state(camera))

            distance_before = _camera_state(camera)[-2]
            global_target = interactor.mapToGlobal(target)
            wheel = QWheelEvent(
                QPointF(target),
                QPointF(global_target),
                QPoint(),
                QPoint(0, 120),
                Qt.NoButton,
                Qt.NoModifier,
                Qt.ScrollUpdate,
                False,
            )
            QApplication.sendEvent(interactor, wheel)
            QTest.qWait(30)
            self.assertNotEqual(distance_before, _camera_state(camera)[-2])

            self.assertTrue(window._dispatch_framework_action("manual_curve.create"))
            self.assertEqual(viewport.left_capture_owner, "manual_curve")
            direction_before = tuple(camera.GetDirectionOfProjection())
            QTest.mousePress(interactor, Qt.LeftButton, Qt.NoModifier, target)
            QTest.mouseMove(interactor, target + QPoint(35, 15), 30)
            QTest.mouseRelease(
                interactor,
                Qt.LeftButton,
                Qt.NoModifier,
                target + QPoint(35, 15),
            )
            self.assertTrue(
                np.allclose(direction_before, camera.GetDirectionOfProjection())
            )
            before = _camera_state(camera)
            QTest.mousePress(interactor, Qt.MiddleButton, Qt.NoModifier, target)
            QTest.mouseMove(interactor, target + QPoint(35, 20), 30)
            QTest.mouseRelease(
                interactor,
                Qt.MiddleButton,
                Qt.NoModifier,
                target + QPoint(35, 20),
            )
            self.assertNotEqual(before, _camera_state(camera))
            distance_before = _camera_state(camera)[-2]
            global_target = interactor.mapToGlobal(target)
            tool_wheel = QWheelEvent(
                QPointF(target),
                QPointF(global_target),
                QPoint(),
                QPoint(0, 120),
                Qt.NoButton,
                Qt.NoModifier,
                Qt.ScrollUpdate,
                False,
            )
            QApplication.sendEvent(interactor, tool_wheel)
            QTest.qWait(30)
            self.assertNotEqual(distance_before, _camera_state(camera)[-2])
            self.assertTrue(window._dispatch_framework_action("manual_curve.cancel"))

            self.assertTrue(window._dispatch_framework_action("region.start"))
            self.assertEqual(viewport.left_capture_owner, "region")
            before = _camera_state(camera)
            QTest.mousePress(interactor, Qt.MiddleButton, Qt.NoModifier, target)
            QTest.mouseMove(interactor, target + QPoint(30, 20), 30)
            QTest.mouseRelease(
                interactor,
                Qt.MiddleButton,
                Qt.NoModifier,
                target + QPoint(30, 20),
            )
            self.assertNotEqual(before, _camera_state(camera))
            self.assertTrue(window._dispatch_framework_action("region.finish"))

            for index in range(10):
                start = interactor.rect().center()
                before_direction = np.asarray(
                    camera.GetDirectionOfProjection(), dtype=float
                )
                delta = QPoint(24 if index % 2 == 0 else -24, 12 + index)
                QTest.mousePress(interactor, Qt.LeftButton, Qt.NoModifier, start)
                QTest.mouseMove(interactor, start + delta, 20)
                QTest.mouseRelease(
                    interactor,
                    Qt.LeftButton,
                    Qt.NoModifier,
                    start + delta,
                )
                state = np.asarray(_camera_state(camera), dtype=float)
                self.assertTrue(np.all(np.isfinite(state)))
                self.assertFalse(
                    np.allclose(before_direction, camera.GetDirectionOfProjection())
                )

            self.assertIsNone(viewport.diagnostic_state().last_rendering_error)
        finally:
            window.set_project_dirty(False)
            window.close()


if __name__ == "__main__":
    unittest.main()
