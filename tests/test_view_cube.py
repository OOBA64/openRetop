"""The viewport view cube: geometry, hit-testing, widget behaviour and camera integration."""

from __future__ import annotations

import itertools
import os
import unittest
from unittest.mock import patch

import numpy as np
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from openretop.application.scene_ids import NODE_MESH
from openretop.bootstrap import create_application
from openretop.infrastructure.settings_repository import InMemorySettingsRepository
from openretop.mesh.triangle_mesh import TriangleMeshData
from openretop.presentation.qt.main_window import OpenRetopV3Window
from openretop.presentation.qt.view_cube import (
    AXIS_DISTANCE,
    CUBE_SCALE,
    CUBE_WIDGET_SIZE,
    ViewCubeWidget,
    axis_title,
    cell_view_name,
    locate,
    normalized_camera_orientation,
    project_axes,
    project_faces,
    view_name,
    view_title,
)
from openretop.presentation.qt.viewport import QtSceneViewport
from openretop.viewer.camera_controller import CameraController, named_view_vectors
from openretop.viewer.scene_types import CameraRequest, MeshRenderItem, SceneSnapshot

FACE_NAMES = ("front", "back", "left", "right", "top", "bottom")


def _orientation(name: str) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Camera forward/up vectors for a named view (the camera sits at +direction)."""

    direction, up = named_view_vectors(name)
    forward = tuple(float(-value) for value in direction)
    return forward, tuple(float(value) for value in up)  # type: ignore[return-value]


def _snapshot(*, show_cube: bool = True, show_axes_gizmo: bool = True, camera_request: CameraRequest | None = None) -> SceneSnapshot:
    mesh = TriangleMeshData(
        vertices=np.asarray([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 3.0, 0.0]], dtype=float),
        triangles=np.asarray([[0, 1, 2]], dtype=int),
    )
    return SceneSnapshot(
        revision=1,
        meshes=(
            MeshRenderItem(
                id="mesh",
                revision=1,
                mesh=mesh,
                local_bounds=((0.0, 0.0, 0.0), (2.0, 3.0, 0.0)),
                selection_keys=(NODE_MESH,),
            ),
        ),
        display={
            "show_grid": True,
            "show_axes": True,
            "show_axis_gizmo": show_axes_gizmo,
            "show_viewcube": show_cube,
            "display_colors": {"background_color": "#101316"},
        },
        camera_request=camera_request or CameraRequest(),
    )


def _ready_without_native_render(viewport: QtSceneViewport) -> None:
    with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
        viewport._is_ready = True
        viewport.ready.emit()


class CubeGeometryTests(unittest.TestCase):
    def test_every_named_view_shows_its_own_face_head_on(self) -> None:
        for name in FACE_NAMES:
            with self.subTest(view=name):
                faces = project_faces(*_orientation(name))
                self.assertEqual(faces[0].name, name)
                self.assertAlmostEqual(faces[0].facing, 1.0)
                self.assertEqual(len(faces), 1)

    def test_clicking_the_centre_of_a_head_on_view_returns_that_face(self) -> None:
        for name in FACE_NAMES:
            with self.subTest(view=name):
                self.assertEqual(locate(project_faces(*_orientation(name)), 0.0, 0.0), name)

    def test_isometric_view_shows_three_faces_and_the_corner_in_the_middle(self) -> None:
        faces = project_faces(*_orientation("isometric"))
        self.assertEqual({face.name for face in faces}, {"front", "right", "top"})
        self.assertEqual(locate(faces, 0.0, 0.0), "top+front+right")

    def test_all_26_regions_can_be_reached_from_some_view(self) -> None:
        """Faces, edges and corners are each clickable (6 + 12 + 8 = 26 views)."""

        reachable: set[str] = set()
        for forward in itertools.product((-1.0, 0.0, 1.0), repeat=3):
            if forward == (0.0, 0.0, 0.0):
                continue
            oriented = normalized_camera_orientation(forward, (0.0, 0.0, 1.0)) or normalized_camera_orientation(forward, (0.0, 1.0, 0.0))
            assert oriented is not None
            for face in project_faces(*oriented):
                for i, j in itertools.product((-1, 0, 1), repeat=2):
                    reachable.add(cell_view_name(face, i, j))
        self.assertEqual(len(reachable), 26)
        self.assertEqual(len([name for name in reachable if "+" not in name]), 6)
        self.assertEqual(len([name for name in reachable if name.count("+") == 1]), 12)
        self.assertEqual(len([name for name in reachable if name.count("+") == 2]), 8)

    def test_every_region_name_is_a_valid_camera_view(self) -> None:
        names = {
            view_name([(0.0, -1.0, 0.0)]),
            "top+front",
            "front+left",
            "bottom+back+right",
        }
        for name in names:
            with self.subTest(view=name):
                direction, up = named_view_vectors(name)
                self.assertAlmostEqual(float(np.linalg.norm(direction)), 1.0)
                self.assertAlmostEqual(float(np.dot(direction, up)), 0.0)

    def test_clicking_an_edge_strip_returns_the_edge_view(self) -> None:
        faces = project_faces(*_orientation("front"))
        # Front face, x/z in [-1, 1]; the strip beyond |0.5| is an edge or corner.
        self.assertEqual(locate(faces, 0.9, 0.0), "front+right")
        self.assertEqual(locate(faces, -0.9, 0.0), "front+left")
        self.assertEqual(locate(faces, 0.0, 0.9), "top+front")
        self.assertEqual(locate(faces, 0.0, -0.9), "bottom+front")
        self.assertEqual(locate(faces, 0.9, 0.9), "top+front+right")
        self.assertEqual(locate(faces, -0.9, -0.9), "bottom+front+left")
        self.assertIsNone(locate(faces, 1.5, 0.0))

    def test_labels_are_not_mirrored_from_any_visible_side(self) -> None:
        """u x v must equal the outward normal so text is readable, never mirrored."""

        for name in FACE_NAMES:
            with self.subTest(view=name):
                face = project_faces(*_orientation(name))[0]
                determinant = face.u[0] * face.v[1] - face.u[1] * face.v[0]
                self.assertGreater(determinant, 0.0)

    def test_view_names_are_canonical_and_titled(self) -> None:
        self.assertEqual(view_name([(1.0, 0.0, 0.0), (0.0, 0.0, 1.0)]), "top+right")
        self.assertEqual(view_title("front"), "Front view")
        self.assertEqual(view_title("top+front"), "Top-Front edge")
        self.assertEqual(view_title("top+front+right"), "Top-Front-Right corner")

    def test_invalid_combinations_are_rejected(self) -> None:
        for bad in ("front+back", "left+left", "top+nonsense", "front+isometric"):
            with self.subTest(view=bad), self.assertRaises(ValueError):
                named_view_vectors(bad)

    def test_degenerate_camera_vectors_are_handled(self) -> None:
        self.assertIsNone(normalized_camera_orientation((0.0, 0.0, 0.0), (0.0, 0.0, 1.0)))
        self.assertIsNone(normalized_camera_orientation((float("nan"), 0.0, 1.0), (0.0, 1.0, 0.0)))
        forward, up = normalized_camera_orientation((0.0, 0.0, -1.0), (0.0, 0.0, 1.0))  # up parallel to forward
        self.assertAlmostEqual(abs(float(np.dot(forward, up))), 0.0)


class AxisBallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _widget(self, view: str) -> ViewCubeWidget:
        widget = ViewCubeWidget()
        widget.set_orientation(*_orientation(view))
        return widget

    def _pixel(self, ball) -> QPointF:
        return QPointF(CUBE_WIDGET_SIZE / 2 + ball.centre[0] * CUBE_SCALE, CUBE_WIDGET_SIZE / 2 - ball.centre[1] * CUBE_SCALE)

    def test_head_on_views_hide_the_end_on_axis_and_show_the_other_four_ends(self) -> None:
        for view in FACE_NAMES:
            with self.subTest(view=view):
                balls = project_axes(*_orientation(view))
                self.assertEqual(len(balls), 4)
                self.assertNotIn(view, {ball.name for ball in balls})

    def test_isometric_view_shows_all_six_ends(self) -> None:
        balls = project_axes(*_orientation("isometric"))
        self.assertEqual({ball.name for ball in balls}, set(FACE_NAMES))
        near = [ball for ball in balls if ball.depth < 0]
        self.assertEqual({ball.name for ball in near}, {"front", "right", "top"})

    def test_ball_positions_follow_the_axes_and_stay_inside_the_widget(self) -> None:
        for view in ("front", "isometric", "top+front+right", "bottom+back+left"):
            for ball in project_axes(*_orientation(view)):
                with self.subTest(view=view, ball=ball.name):
                    self.assertLessEqual(abs(ball.centre[0]), AXIS_DISTANCE + 1e-9)
                    self.assertLessEqual(abs(ball.centre[1]), AXIS_DISTANCE + 1e-9)
                    pixel_radius = (AXIS_DISTANCE * CUBE_SCALE) + 9.0
                    self.assertLess(pixel_radius, CUBE_WIDGET_SIZE / 2)

    def test_x_points_right_and_z_points_up_in_the_front_view(self) -> None:
        balls = {ball.name: ball for ball in project_axes(*_orientation("front"))}
        self.assertGreater(balls["right"].centre[0], 1.0)
        self.assertLess(balls["left"].centre[0], -1.0)
        self.assertGreater(balls["top"].centre[1], 1.0)
        self.assertLess(balls["bottom"].centre[1], -1.0)

    def test_clicking_a_ball_selects_the_view_along_that_axis(self) -> None:
        widget = ViewCubeWidget()
        widget.set_orientation(*normalized_camera_orientation((-0.6, 0.7, -0.3), (0.0, 0.0, 1.0)))  # generic: no ends overlap
        for ball in widget.axes:
            if ball.depth > 0 and locate(widget.faces, *ball.centre) is not None:
                continue  # hidden behind the cube
            with self.subTest(ball=ball.name):
                hit = widget.hit_at(self._pixel(ball))
                self.assertIsNotNone(hit)
                self.assertEqual(hit.action_id, f"view.named.{ball.name}")
                self.assertEqual(hit.hover_key, f"view.named.{ball.name}#axis")
                self.assertEqual(hit.title, axis_title(ball))

    def test_a_ball_hidden_behind_the_cube_cannot_be_clicked_through_it(self) -> None:
        widget = self._widget("isometric")
        behind = [ball for ball in widget.axes if ball.depth > 0]
        self.assertTrue(behind)
        for ball in behind:
            with self.subTest(ball=ball.name):
                from openretop.presentation.qt.view_cube import locate

                covered = locate(widget.faces, *ball.centre) is not None
                hit = widget.hit_at(self._pixel(ball))
                if covered:
                    self.assertNotEqual(hit and hit.hover_key, f"view.named.{ball.name}#axis")

    def test_axes_work_without_the_cube_and_cube_without_the_axes(self) -> None:
        widget = self._widget("isometric")
        ball = next(item for item in widget.axes if item.depth < 0)
        widget.set_parts(cube=False, axes=True)
        self.assertEqual(widget.hit_at(self._pixel(ball)).action_id, f"view.named.{ball.name}")
        self.assertIsNone(widget.hit_at(QPointF(CUBE_WIDGET_SIZE / 2, CUBE_WIDGET_SIZE / 2)))
        widget.set_parts(cube=True, axes=False)
        hit = widget.hit_at(self._pixel(ball))
        self.assertTrue(hit is None or not hit.hover_key.endswith("#axis"))

    def test_ball_hover_is_distinct_from_the_matching_face(self) -> None:
        widget = self._widget("isometric")
        ball = next(item for item in widget.axes if item.depth < 0)
        self.assertTrue(widget.set_hover(widget.hit_at(self._pixel(ball)).hover_key))
        image_ball = widget.render_image()
        widget.set_hover(f"view.named.{ball.name}")
        image_face = widget.render_image()
        self.assertNotEqual(image_ball.constBits().tobytes(), image_face.constBits().tobytes())


class CubeWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _point(self, widget: ViewCubeWidget, x: float, y: float) -> QPointF:
        """Widget pixel for a view-space point (cube half-edge = 1)."""

        return QPointF(CUBE_WIDGET_SIZE / 2 + x * CUBE_SCALE, CUBE_WIDGET_SIZE / 2 - y * CUBE_SCALE)

    def test_click_on_a_face_emits_the_named_view_action(self) -> None:
        widget = ViewCubeWidget()
        widget.set_orientation(*_orientation("front"))
        for point, expected in (
            ((0.0, 0.0), "view.named.front"),
            ((0.9, 0.0), "view.named.front+right"),
            ((0.0, 0.9), "view.named.top+front"),
        ):
            with self.subTest(expected=expected):
                hit = widget.hit_at(self._point(widget, *point))
                self.assertIsNotNone(hit)
                self.assertEqual(hit.action_id, expected)

    def test_clicks_outside_the_cube_hit_nothing(self) -> None:
        widget = ViewCubeWidget()
        widget.set_orientation(*_orientation("front"))
        self.assertIsNone(widget.hit_at(self._point(widget, 1.3, 1.3)))
        self.assertIsNone(widget.hit_at(QPointF(CUBE_WIDGET_SIZE / 2, 2.0)))

    def test_there_are_no_buttons_only_cube_regions_and_axis_balls(self) -> None:
        widget = ViewCubeWidget()
        widget.set_orientation(*_orientation("front"))
        corners = [QPointF(4, 4), QPointF(CUBE_WIDGET_SIZE - 4, 4), QPointF(4, CUBE_WIDGET_SIZE - 4), QPointF(CUBE_WIDGET_SIZE - 4, CUBE_WIDGET_SIZE - 4)]
        for corner in corners:
            with self.subTest(corner=(corner.x(), corner.y())):
                self.assertIsNone(widget.hit_at(corner))

    def test_orientation_follows_the_camera_and_back_faces_are_not_clickable(self) -> None:
        widget = ViewCubeWidget()
        widget.set_orientation(*_orientation("back"))
        self.assertEqual(widget.faces[0].name, "back")
        self.assertEqual(widget.hit_at(self._point(widget, 0.0, 0.0)).action_id, "view.named.back")
        widget.set_orientation(*_orientation("bottom"))
        self.assertEqual(widget.hit_at(self._point(widget, 0.0, 0.0)).action_id, "view.named.bottom")

    def test_real_mouse_press_and_release_emits_once(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        widget = ViewCubeWidget()
        widget.set_orientation(*_orientation("front"))
        widget.show()
        actions: list[str] = []
        widget.action_requested.connect(actions.append)
        try:
            QTest.mouseClick(widget, Qt.LeftButton, Qt.NoModifier, self._point(widget, 0.9, 0.0).toPoint())
            self.assertEqual(actions, ["view.named.front+right"])
            QTest.mouseClick(widget, Qt.LeftButton, Qt.NoModifier, self._point(widget, 1.3, 1.3).toPoint())
            self.assertEqual(len(actions), 1)
        finally:
            widget.close()

    def test_hover_tracks_the_region_and_sets_a_tooltip(self) -> None:
        from PySide6.QtTest import QTest

        widget = ViewCubeWidget()
        widget.set_orientation(*_orientation("front"))
        widget.show()
        try:
            QTest.mouseMove(widget, self._point(widget, 0.0, 0.9).toPoint())
            self.assertEqual(widget.hover, "view.named.top+front")
            self.assertEqual(widget.toolTip(), "Top-Front edge")
            QTest.mouseMove(widget, self._point(widget, 1.3, 1.3).toPoint())
            self.assertIsNone(widget.hover)
        finally:
            widget.close()

    def test_rendered_image_is_transparent_outside_the_cube_and_opaque_on_it(self) -> None:
        widget = ViewCubeWidget()
        widget.set_orientation(*_orientation("front"))
        for ratio in (1.0, 2.0):
            with self.subTest(ratio=ratio):
                image = widget.render_image(ratio)
                self.assertEqual(image.width(), round(CUBE_WIDGET_SIZE * ratio))
                centre = round(CUBE_WIDGET_SIZE * ratio / 2)
                self.assertGreater(image.pixelColor(centre, centre).alpha(), 200)
                self.assertEqual(image.pixelColor(centre, 2).alpha(), 0)  # above the cube, between the buttons
        widget.set_parts(cube=False, axes=False)
        self.assertEqual(widget.render_image().pixelColor(CUBE_WIDGET_SIZE // 2, CUBE_WIDGET_SIZE // 2).alpha(), 0)
        self.assertIsNone(widget.hit_at(self._point(widget, 0.0, 0.0)))

    def test_painting_every_orientation_never_raises(self) -> None:
        from PySide6.QtGui import QPixmap

        widget = ViewCubeWidget()
        pixmap = QPixmap(CUBE_WIDGET_SIZE, CUBE_WIDGET_SIZE)
        for forward in itertools.product((-1.0, 0.0, 0.4, 1.0), repeat=3):
            oriented = normalized_camera_orientation(forward, (0.0, 0.0, 1.0))
            if oriented is None:
                continue
            widget.set_orientation(*oriented)
            widget.render(pixmap)


class ViewportCubeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_cube_and_axes_visibility_are_independent(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.resize(600, 400)
            for cube, triad in ((True, True), (True, False), (False, True), (False, False)):
                with self.subTest(cube=cube, axes=triad):
                    viewport.render_snapshot(_snapshot(show_cube=cube, show_axes_gizmo=triad))
                    _ready_without_native_render(viewport)
                    state = viewport.navigation_cluster.diagnostic_state()
                    self.assertEqual((state.cube_visible, state.axes_visible), (cube, triad))
                    self.assertEqual(bool(viewport.navigation_cluster.overlay_renderer.GetDraw()), cube or triad)
        finally:
            viewport.close()

    def test_cube_sits_in_the_top_right_corner_and_stays_inside_the_viewport(self) -> None:
        viewport = QtSceneViewport()
        try:
            for width, height in ((800, 500), (300, 200)):
                viewport.resize(width, height)
                viewport.navigation_cluster.update_layout()
                x, y, w, h = viewport.navigation_cluster.logical_bounds
                self.assertGreaterEqual(x, 0)
                self.assertGreaterEqual(y, 0)
                self.assertLessEqual(x + w, width)
        finally:
            viewport.close()

    def test_one_observer_is_installed_and_removed_on_close(self) -> None:
        viewport = QtSceneViewport()
        viewport.render_snapshot(_snapshot())
        _ready_without_native_render(viewport)
        self.assertEqual(viewport.observer_count, 1)
        _ready_without_native_render(viewport)
        self.assertEqual(viewport.observer_count, 1)
        viewport.close()
        self.assertEqual(viewport.navigation_cluster.observer_count, 0)

    def test_cube_follows_the_camera_but_not_pan_or_zoom(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.render_snapshot(_snapshot())
            _ready_without_native_render(viewport)
            cluster = viewport.navigation_cluster
            camera = viewport.renderer.GetActiveCamera()
            camera.SetPosition(0.0, -10.0, 0.0)
            camera.SetFocalPoint(0.0, 0.0, 0.0)
            camera.SetViewUp(0.0, 0.0, 1.0)
            self.assertTrue(cluster.sync_camera())
            self.assertEqual(cluster.widget.faces[0].name, "front")
            updates = cluster.camera_update_count
            camera.SetPosition(5.0, -20.0, 0.0)  # pan + zoom: same orientation
            camera.SetFocalPoint(5.0, 0.0, 0.0)
            self.assertFalse(cluster.sync_camera())
            self.assertEqual(cluster.camera_update_count, updates)
            camera.SetPosition(0.0, 0.0, 10.0)
            camera.SetFocalPoint(0.0, 0.0, 0.0)
            camera.SetViewUp(0.0, 1.0, 0.0)
            self.assertTrue(cluster.sync_camera())
            self.assertEqual(cluster.widget.faces[0].name, "top")
        finally:
            viewport.close()


    def test_overlay_is_a_transparent_noninteractive_layer_with_one_unpickable_image_actor(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.resize(640, 400)
            viewport.render_snapshot(_snapshot())
            _ready_without_native_render(viewport)
            cluster = viewport.navigation_cluster
            state = cluster.diagnostic_state()
            renderer = cluster.overlay_renderer
            self.assertTrue(state.overlay_attached)
            self.assertEqual(viewport.render_window.GetRenderers().GetNumberOfItems(), 2)
            self.assertGreaterEqual(renderer.GetLayer(), 1)
            self.assertFalse(bool(renderer.GetInteractive()))
            self.assertEqual(renderer.GetBackgroundAlpha(), 0.0)
            self.assertEqual(renderer.GetViewProps().GetNumberOfItems(), 1)
            self.assertFalse(bool(cluster.overlay_actor.GetPickable()))
            self.assertEqual(viewport.renderer.GetViewProps().GetNumberOfItems(), 2)  # mesh + grid only
            x0, y0, x1, y1 = state.overlay_viewport
            self.assertGreater(x1, x0)
            self.assertGreater(y1, y0)
            self.assertLessEqual(x1, 1.0)
            image = cluster.overlay_actor.GetInput()
            self.assertEqual(image.GetDimensions()[:2], (CUBE_WIDGET_SIZE, CUBE_WIDGET_SIZE))
            self.assertEqual(image.GetNumberOfScalarComponents(), 4)
        finally:
            viewport.close()

    def test_image_is_repainted_only_when_something_changes(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.render_snapshot(_snapshot())
            _ready_without_native_render(viewport)
            cluster = viewport.navigation_cluster
            updates = cluster.image_update_count
            self.assertGreater(updates, 0)
            cluster.sync_camera()
            cluster.update_layout()
            self.assertEqual(cluster.image_update_count, updates)
            camera = viewport.renderer.GetActiveCamera()
            camera.SetPosition(0.0, -10.0, 0.0)
            camera.SetFocalPoint(0.0, 0.0, 0.0)
            camera.SetViewUp(0.0, 0.0, 1.0)
            cluster.sync_camera()
            self.assertEqual(cluster.image_update_count, updates + 1)
        finally:
            viewport.close()

    def _mouse(self, kind: QEvent.Type, point: QPointF, *, buttons: Qt.MouseButton = Qt.MouseButton.NoButton) -> QMouseEvent:
        button = Qt.MouseButton.LeftButton if kind != QEvent.Type.MouseMove else Qt.MouseButton.NoButton
        return QMouseEvent(kind, point, point, button, buttons, Qt.KeyboardModifier.NoModifier)

    def test_clicks_on_the_cube_are_consumed_and_emit_actions_but_others_pass_through(self) -> None:
        viewport = QtSceneViewport()
        actions: list[str] = []
        try:
            viewport.resize(700, 500)
            viewport.render_snapshot(_snapshot())
            _ready_without_native_render(viewport)
            cluster = viewport.navigation_cluster
            cluster.action_requested.connect(actions.append)
            cluster.widget.set_orientation(*_orientation("front"))
            x, y, _w, _h = cluster.logical_bounds
            on_cube = QPointF(x + CUBE_WIDGET_SIZE / 2, y + CUBE_WIDGET_SIZE / 2 - 0.9 * CUBE_SCALE)  # top-front edge strip
            left = Qt.MouseButton.LeftButton
            press, release = QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease
            self.assertTrue(viewport.eventFilter(viewport.interactor, self._mouse(press, on_cube, buttons=left)))
            self.assertTrue(viewport.eventFilter(viewport.interactor, self._mouse(release, on_cube)))
            self.assertEqual(actions, ["view.named.top+front"])
            self.assertEqual(viewport.diagnostic_state().pointer_event_count, 0)
            self.assertEqual(viewport.diagnostic_state().pick_count, 0)
            # press on the cube but release elsewhere: no action
            elsewhere = QPointF(40.0, 300.0)
            viewport.eventFilter(viewport.interactor, self._mouse(press, on_cube, buttons=left))
            viewport.eventFilter(viewport.interactor, self._mouse(release, elsewhere))
            self.assertEqual(len(actions), 1)
            # a click away from the cube is not consumed
            self.assertFalse(viewport.eventFilter(viewport.interactor, self._mouse(press, elsewhere, buttons=left)))
            viewport.eventFilter(viewport.interactor, self._mouse(release, elsewhere))
            self.assertEqual(len(actions), 1)
        finally:
            viewport.close()

    def test_hover_highlights_the_region_and_a_drag_over_the_cube_is_not_hijacked(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.resize(700, 500)
            viewport.render_snapshot(_snapshot())
            _ready_without_native_render(viewport)
            cluster = viewport.navigation_cluster
            cluster.widget.set_orientation(*_orientation("front"))
            x, y, _w, _h = cluster.logical_bounds
            on_cube = QPointF(x + CUBE_WIDGET_SIZE / 2 + 0.9 * CUBE_SCALE, y + CUBE_WIDGET_SIZE / 2)
            before = cluster.image_update_count
            viewport.eventFilter(viewport.interactor, self._mouse(QEvent.Type.MouseMove, on_cube))
            self.assertEqual(cluster.widget.hover, "view.named.front+right")
            self.assertGreater(cluster.image_update_count, before)
            viewport.eventFilter(viewport.interactor, self._mouse(QEvent.Type.MouseMove, QPointF(5.0, 5.0)))
            self.assertIsNone(cluster.widget.hover)
            # a middle-button drag across the cube (an orbit/pan) is left to VTK
            dragging = self._mouse(QEvent.Type.MouseMove, on_cube, buttons=Qt.MouseButton.MiddleButton)
            self.assertFalse(viewport.eventFilter(viewport.interactor, dragging))
            self.assertIsNone(cluster.widget.hover)
        finally:
            viewport.close()

    def test_hover_follows_the_region_under_a_stationary_cursor_when_the_camera_turns(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.resize(700, 500)
            viewport.render_snapshot(_snapshot())
            _ready_without_native_render(viewport)
            cluster = viewport.navigation_cluster
            cluster.widget.set_orientation(*_orientation("front"))
            x, y, _w, _h = cluster.logical_bounds
            local = QPointF(CUBE_WIDGET_SIZE / 2 + 0.9 * CUBE_SCALE, CUBE_WIDGET_SIZE / 2)
            viewport.eventFilter(viewport.interactor, self._mouse(QEvent.Type.MouseMove, QPointF(x + local.x(), y + local.y())))
            self.assertEqual(cluster.widget.hover, "view.named.front+right")
            camera = viewport.renderer.GetActiveCamera()
            camera.SetPosition(10.0, 0.0, 0.0)  # now looking at the right face from +X
            camera.SetFocalPoint(0.0, 0.0, 0.0)
            camera.SetViewUp(0.0, 0.0, 1.0)
            self.assertTrue(cluster.sync_camera())
            expected = cluster.widget.hit_at(local)
            self.assertIsNotNone(expected)
            self.assertEqual(cluster.widget.hover, expected.action_id)
            self.assertNotEqual(cluster.widget.hover, "view.named.front+right")
            cluster.leave()
            self.assertIsNone(cluster.widget.hover)
        finally:
            viewport.close()

    def test_hidden_cube_ignores_the_mouse(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.resize(700, 500)
            viewport.render_snapshot(_snapshot(show_cube=False))
            _ready_without_native_render(viewport)
            cluster = viewport.navigation_cluster
            x, y, _w, _h = cluster.logical_bounds
            centre = QPointF(x + CUBE_WIDGET_SIZE / 2, y + CUBE_WIDGET_SIZE / 2)
            press = self._mouse(QEvent.Type.MouseButtonPress, centre, buttons=Qt.MouseButton.LeftButton)
            self.assertFalse(cluster.handle_mouse_event(press))
        finally:
            viewport.close()


class CameraViewActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _window(self) -> OpenRetopV3Window:
        window = OpenRetopV3Window(create_application(settings_repository=InMemorySettingsRepository()))
        window.viewport.resize(700, 480)
        _ready_without_native_render(window.viewport)
        return window

    def _dispatch(self, window: OpenRetopV3Window, action_id: str) -> bool:
        with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}), patch.object(
            window.viewport, "_renderer_has_size", return_value=True
        ):
            return window._dispatch_framework_action(action_id)

    def test_cube_clicks_move_the_camera_and_update_the_cube(self) -> None:
        window = self._window()
        try:
            camera = window.viewport.renderer.GetActiveCamera()
            for name in ("front", "left", "top", "front+right", "top+front+right", "bottom+back+left"):
                with self.subTest(view=name):
                    with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}), patch.object(
                        window.viewport, "_renderer_has_size", return_value=True
                    ):
                        window.viewport.navigation_cluster.action_requested.emit(f"view.named.{name}")
                    direction, _up = named_view_vectors(name)
                    position = np.asarray(camera.GetPosition()) - np.asarray(camera.GetFocalPoint())
                    position /= np.linalg.norm(position)
                    np.testing.assert_allclose(position, direction, atol=1e-6)
                    self.assertTrue(np.all(np.isfinite(camera.GetViewUp())))
                    expected_faces = {part for part in name.split("+")}
                    self.assertEqual({face.name for face in window.viewport.navigation_cluster.widget.faces}, expected_faces)
        finally:
            window.set_project_dirty(False)
            window.close()

    def test_roll_actions_rotate_only_the_view_up_vector(self) -> None:
        window = self._window()
        try:
            camera = window.viewport.renderer.GetActiveCamera()
            position, focal, up = (np.asarray(value) for value in (camera.GetPosition(), camera.GetFocalPoint(), camera.GetViewUp()))
            self.assertTrue(self._dispatch(window, "view.roll_right"))
            np.testing.assert_allclose(camera.GetPosition(), position)
            np.testing.assert_allclose(camera.GetFocalPoint(), focal)
            self.assertFalse(np.allclose(camera.GetViewUp(), up))
            self.assertTrue(self._dispatch(window, "view.roll_left"))
            np.testing.assert_allclose(camera.GetViewUp(), up, atol=1e-12)
        finally:
            window.set_project_dirty(False)
            window.close()


class CameraRollMathTests(unittest.TestCase):
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

    def test_roll_preserves_pose_and_changes_only_view_up(self) -> None:
        for parallel in (True, False):
            with self.subTest(parallel=parallel):
                controller, camera = self._controller()
                if not parallel:
                    camera.ParallelProjectionOff()
                position, focal, scale = np.asarray(camera.GetPosition()), np.asarray(camera.GetFocalPoint()), camera.GetParallelScale()
                up = np.asarray(camera.GetViewUp())
                self.assertTrue(controller.roll(15.0))
                np.testing.assert_allclose(camera.GetPosition(), position)
                np.testing.assert_allclose(camera.GetFocalPoint(), focal)
                self.assertAlmostEqual(camera.GetParallelScale(), scale)
                self.assertFalse(np.allclose(camera.GetViewUp(), up))
                self.assertAlmostEqual(float(np.linalg.norm(camera.GetViewUp())), 1.0)
                self.assertAlmostEqual(float(np.dot(camera.GetViewUp(), camera.GetDirectionOfProjection())), 0.0)

    def test_repeated_rolls_are_stable(self) -> None:
        controller, camera = self._controller()
        original = np.asarray(camera.GetViewUp())
        controller.roll(-15.0)
        controller.roll(15.0)
        np.testing.assert_allclose(camera.GetViewUp(), original, atol=1e-12)
        for _ in range(48):
            controller.roll(15.0)
        self.assertTrue(np.all(np.isfinite(camera.GetViewUp())))
        self.assertAlmostEqual(float(np.dot(camera.GetViewUp(), camera.GetDirectionOfProjection())), 0.0)


if __name__ == "__main__":
    unittest.main()
