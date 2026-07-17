from __future__ import annotations

from dataclasses import replace
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

from application.commands import CommandRequest  # noqa: E402
from application.results import CommandResult  # noqa: E402
from application.scene_ids import (  # noqa: E402
    NODE_MESH,
    curve_node_id,
    region_node_id,
    section_plane_node_id,
    section_result_node_id,
    surface_node_id,
)
from application.state import MeshObjectState  # noqa: E402
from bootstrap import create_application  # noqa: E402
from curves.curve_state import StoredCurve, add_curve  # noqa: E402
from geometry.sections import SectionResult  # noqa: E402
from infrastructure.settings_repository import InMemorySettingsRepository  # noqa: E402
from mesh.triangle_mesh import TriangleMeshData  # noqa: E402
from presentation.qt.main_window import OpenRetopV3Window  # noqa: E402
from presentation.qt.pointer_gestures import PointerGestureState  # noqa: E402
from presentation.qt.view_controls import TriangularViewButton  # noqa: E402
from presentation.qt.viewport import QtSceneViewport  # noqa: E402
from regions.region_state import RegionSelection  # noqa: E402
from sections.section_state import StoredSectionResult  # noqa: E402
from surfaces.brep_state import BrepSurfaceRecord, add_brep_surface  # noqa: E402
from surfaces.surface_state import SurfacePatch, add_surface  # noqa: E402
from viewer.scene_builder import SceneBuildOptions, SceneBuilder  # noqa: E402
from viewer.picking_service import (  # noqa: E402
    MeshPickResult,
    SceneObjectPickResult,
)
from viewer.scene_types import (  # noqa: E402
    CameraRequest,
    MeshRenderItem,
    SceneSnapshot,
)
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


def _snapshot(
    *,
    revision: int = 1,
    show_axes: bool = True,
    show_axis_gizmo: bool = True,
    show_viewcube: bool = True,
    mode: str | None = None,
    axis: str | None = None,
    origin: tuple[float, float, float] | None = None,
    angle_delta: float | None = None,
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
        active_transform_angle_delta=angle_delta,
    )


def _ready_without_native_render(viewport: QtSceneViewport) -> None:
    with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
        viewport._is_ready = True
        viewport.ready.emit()


def _camera_state(camera: object) -> tuple[float, ...]:
    vectors = tuple(
        float(value)
        for values in (
            camera.GetPosition(),
            camera.GetFocalPoint(),
            camera.GetViewUp(),
        )
        for value in values
    )
    return (*vectors, float(camera.GetParallelScale()))


def _find_tree_item(tree: object, node_id: str) -> object | None:
    pending = [tree.topLevelItem(index) for index in range(tree.topLevelItemCount())]
    while pending:
        item = pending.pop(0)
        if str(item.data(0, Qt.UserRole)) == node_id:
            return item
        pending.extend(item.child(index) for index in range(item.childCount()))
    return None


class Task82BPointerRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_generic_viewport_uses_concrete_trackball_camera_style(self) -> None:
        viewport = VTKViewportWidget()
        try:
            self.assertEqual(
                viewport.interactor.GetInteractorStyle().GetClassName(),
                "vtkInteractorStyleTrackballCamera",
            )
            self.assertEqual(
                viewport.diagnostic_state()["interactor_style_class"],
                "vtkInteractorStyleTrackballCamera",
            )
        finally:
            viewport.close()

    def test_repeated_start_preserves_the_one_style_and_renderer(self) -> None:
        viewport = VTKViewportWidget()
        try:
            style = viewport.interactor.GetInteractorStyle()
            with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
                self.assertFalse(viewport.start())
                self.assertFalse(viewport.start())
            self.assertIs(viewport.interactor.GetInteractorStyle(), style)
            self.assertEqual(
                viewport.render_window.GetRenderers().GetNumberOfItems(),
                1,
            )
        finally:
            viewport.close()

    def test_pointer_gesture_distinguishes_click_and_drag_at_four_pixels(self) -> None:
        gesture = PointerGestureState(4.0)
        gesture.press(10.0, 10.0)
        gesture.motion(12.0, 12.0)
        self.assertTrue(gesture.release(12.0, 12.0).is_click)
        gesture.press(10.0, 10.0)
        gesture.motion(15.0, 10.0)
        release = gesture.release(15.0, 10.0)
        self.assertFalse(release.is_click)
        self.assertEqual(release.distance, 5.0)

    def test_unmodified_left_drag_is_not_camera_navigation_or_a_pick(self) -> None:
        viewport = QtSceneViewport()
        events: list[str] = []
        viewport.pointer_event.connect(
            lambda name, _x, _y, _pick: events.append(name)
        )
        try:
            camera_before = _camera_state(viewport.renderer.GetActiveCamera())
            press = QMouseEvent(
                QEvent.MouseButtonPress,
                QPointF(10.0, 10.0),
                QPointF(10.0, 10.0),
                Qt.LeftButton,
                Qt.LeftButton,
                Qt.NoModifier,
            )
            motion = QMouseEvent(
                QEvent.MouseMove,
                QPointF(30.0, 10.0),
                QPointF(30.0, 10.0),
                Qt.NoButton,
                Qt.LeftButton,
                Qt.NoModifier,
            )
            release = QMouseEvent(
                QEvent.MouseButtonRelease,
                QPointF(30.0, 10.0),
                QPointF(30.0, 10.0),
                Qt.LeftButton,
                Qt.NoButton,
                Qt.NoModifier,
            )
            self.assertTrue(viewport.eventFilter(viewport.interactor, press))
            self.assertTrue(viewport.eventFilter(viewport.interactor, motion))
            self.assertTrue(viewport.eventFilter(viewport.interactor, release))
            self.assertEqual(events[0], "left_press")
            self.assertEqual(events[-1], "left_release")
            self.assertIn("motion", events)
            self.assertFalse(viewport.last_pointer_release_was_click)
            self.assertEqual(viewport.diagnostic_state().pick_count, 0)
            self.assertEqual(camera_before, _camera_state(viewport.renderer.GetActiveCamera()))
        finally:
            viewport.close()

    def test_modified_left_and_secondary_buttons_bypass_application_router(self) -> None:
        viewport = QtSceneViewport()
        events: list[str] = []
        viewport.pointer_event.connect(
            lambda name, _x, _y, _pick: events.append(name)
        )
        try:
            for button, modifier in (
                (Qt.LeftButton, Qt.AltModifier),
                (Qt.LeftButton, Qt.ShiftModifier),
                (Qt.MiddleButton, Qt.NoModifier),
                (Qt.RightButton, Qt.NoModifier),
            ):
                event = QMouseEvent(
                    QEvent.MouseButtonPress,
                    QPointF(20.0, 20.0),
                    QPointF(20.0, 20.0),
                    button,
                    button,
                    modifier,
                )
                self.assertFalse(viewport.eventFilter(viewport.interactor, event))
                motion = QMouseEvent(
                    QEvent.MouseMove,
                    QPointF(35.0, 30.0),
                    QPointF(35.0, 30.0),
                    Qt.NoButton,
                    button,
                    modifier,
                )
                self.assertFalse(viewport.eventFilter(viewport.interactor, motion))
            self.assertEqual(events, [])
            self.assertEqual(viewport.diagnostic_state().pick_count, 0)
        finally:
            viewport.close()

    def test_idle_motion_never_picks(self) -> None:
        viewport = QtSceneViewport()
        try:
            for offset in range(5):
                event = QMouseEvent(
                    QEvent.MouseMove,
                    QPointF(20.0 + offset, 20.0),
                    QPointF(20.0 + offset, 20.0),
                    Qt.NoButton,
                    Qt.NoButton,
                    Qt.NoModifier,
                )
                self.assertFalse(viewport.eventFilter(viewport.interactor, event))
            state = viewport.diagnostic_state()
            self.assertGreaterEqual(state.pointer_event_count, 1)
            self.assertEqual(state.pick_count, 0)
        finally:
            viewport.close()

    def test_scene_refresh_without_camera_request_preserves_pose(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.render_snapshot(_snapshot())
            _ready_without_native_render(viewport)
            viewport.render_window.SetSize(800, 600)
            viewport._position_axis_gizmo_renderer()
            camera = viewport.renderer.GetActiveCamera()
            camera.SetPosition(8.0, 7.0, 6.0)
            camera.SetFocalPoint(1.0, 2.0, 3.0)
            before = _camera_state(camera)
            with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
                viewport.render_snapshot(_snapshot(revision=2))
            self.assertEqual(before, _camera_state(camera))
        finally:
            viewport.close()

    def test_click_selects_but_drag_release_preserves_the_existing_selection(self) -> None:
        composition = create_application(
            settings_repository=InMemorySettingsRepository()
        )
        composition.state.mesh_object = _mesh_object()
        window = OpenRetopV3Window(composition)
        try:
            plane = composition.state.section_collection.planes[0]
            plane_node = section_plane_node_id(plane.id)
            composition.selection_controller.select_nodes((plane_node,))
            mesh_pick = SceneObjectPickResult(
                hit=True,
                object_id="mesh",
                object_type="mesh",
            )

            window.viewport._last_pointer_release_was_click = False
            window._on_viewport_pointer("left_release", 10, 10, mesh_pick)
            self.assertEqual(
                composition.selection_controller.snapshot().ids,
                (plane_node,),
            )

            window.viewport._last_pointer_release_was_click = True
            with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
                window._on_viewport_pointer("left_release", 10, 10, mesh_pick)
            self.assertEqual(
                composition.selection_controller.snapshot().ids,
                (NODE_MESH,),
            )
        finally:
            window.set_project_dirty(False)
            window.close()

    def test_manual_hover_picks_once_but_native_navigation_never_enters_tool_router(self) -> None:
        composition = create_application(
            settings_repository=InMemorySettingsRepository()
        )
        composition.state.mesh_object = _mesh_object()
        window = OpenRetopV3Window(composition)
        try:
            composition.manual_curve_controller.begin_new_curve(
                plane_origin=(0.0, 0.0, 0.0),
                plane_normal=(0.0, 0.0, 1.0),
            )
            with patch.object(
                window.viewport,
                "pick_mesh",
                return_value=MeshPickResult(hit=False),
            ) as pick:
                window._on_viewport_pointer("motion", 10, 10, None)
                pick.assert_called_once_with(10, 10)
                event = QMouseEvent(
                    QEvent.MouseButtonPress,
                    QPointF(20.0, 20.0),
                    QPointF(20.0, 20.0),
                    Qt.RightButton,
                    Qt.RightButton,
                    Qt.NoModifier,
                )
                self.assertFalse(
                    window.viewport.eventFilter(window.viewport.interactor, event)
                )
                pick.assert_called_once()
        finally:
            window.set_project_dirty(False)
            window.close()


class Task82BSceneTreeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _window(self) -> OpenRetopV3Window:
        composition = create_application(
            settings_repository=InMemorySettingsRepository()
        )
        composition.state.mesh_object = _mesh_object()
        return OpenRetopV3Window(composition)

    def test_roots_and_groups_are_not_checkable_but_visibility_leaves_are(self) -> None:
        window = self._window()
        try:
            nodes = window._scene_nodes()
            hierarchy = [node for node in nodes if node.kind in {"root", "group", "curve_group"}]
            self.assertTrue(hierarchy)
            self.assertTrue(all(not node.checkable for node in hierarchy))
            self.assertTrue(all(not node.selectable for node in hierarchy))
            self.assertTrue(next(node for node in nodes if node.id == NODE_MESH).checkable)
            for node in nodes:
                item = _find_tree_item(window.scene_tree.tree, node.id)
                self.assertIsNotNone(item)
                self.assertEqual(
                    bool(item.flags() & Qt.ItemIsUserCheckable),
                    node.checkable,
                    node.id,
                )
                self.assertEqual(
                    bool(item.flags() & Qt.ItemIsSelectable),
                    node.selectable,
                    node.id,
                )
            emitted: list[tuple[str, bool]] = []
            window.scene_tree.visibility_changed.connect(
                lambda node_id, visible: emitted.append((node_id, visible))
            )
            window.scene_tree.refresh()
            self.assertEqual(emitted, [])
        finally:
            window.set_project_dirty(False)
            window.close()

    def test_checkbox_command_preserves_selection_camera_and_records_one_undo(self) -> None:
        window = self._window()
        try:
            _ready_without_native_render(window.viewport)
            plane = window.composition.state.section_collection.planes[0]
            plane_node = section_plane_node_id(plane.id)
            window.composition.selection_controller.select_nodes((plane_node,))
            camera = window.viewport.renderer.GetActiveCamera()
            camera.SetPosition(9.0, 8.0, 7.0)
            camera.SetFocalPoint(1.0, 1.0, 1.0)
            camera_before = _camera_state(camera)
            selection_before = window.composition.selection_controller.snapshot().ids

            with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
                window._on_tree_visibility(NODE_MESH, False)
                self.assertFalse(window.composition.state.mesh_object.visible)
                self.assertEqual(
                    window.composition.selection_controller.snapshot().ids,
                    selection_before,
                )
                self.assertEqual(_camera_state(camera), camera_before)
                self.assertEqual(len(window.composition.undo._undo_commands), 1)
                self.assertEqual(window.composition.undo.undo_name, "Hide Visibility")

                window._on_tree_visibility(NODE_MESH, False)
            self.assertEqual(len(window.composition.undo._undo_commands), 1)
        finally:
            window.set_project_dirty(False)
            window.close()

    def test_queued_checkbox_refresh_does_not_delete_item_during_signal(self) -> None:
        window = self._window()
        try:
            plane = window.composition.state.section_collection.planes[0]
            plane_node = section_plane_node_id(plane.id)
            window.composition.selection_controller.select_nodes((plane_node,))
            window._scene_model.select((plane_node,))
            window.scene_tree.refresh()
            selection_before = window.composition.selection_controller.snapshot().ids
            item = _find_tree_item(window.scene_tree.tree, NODE_MESH)
            self.assertIsNotNone(item)
            item.setCheckState(0, Qt.Unchecked)
            self.app.processEvents()
            self.assertFalse(window.composition.state.mesh_object.visible)
            self.assertEqual(
                window.composition.selection_controller.snapshot().ids,
                selection_before,
            )
        finally:
            window.set_project_dirty(False)
            window.close()

    def test_stale_or_failed_visibility_target_rolls_back_to_domain_state(self) -> None:
        window = self._window()
        try:
            window._on_tree_visibility("curve:already-deleted", False)
            self.assertTrue(window.composition.state.mesh_object.visible)
            self.assertEqual(len(window.composition.undo._undo_commands), 0)
            self.assertEqual(window.statusBar().currentMessage(), "No selection")

            window._scene_model.set_visible(NODE_MESH, False)
            with patch.object(
                window,
                "_command_result",
                return_value=CommandResult.failure("Forced visibility failure"),
            ):
                window._on_tree_visibility(NODE_MESH, False)
            self.assertTrue(window.composition.state.mesh_object.visible)
            item = _find_tree_item(window.scene_tree.tree, NODE_MESH)
            self.assertEqual(item.checkState(0), Qt.Checked)
            self.assertIn("Forced visibility failure", window.statusBar().currentMessage())
        finally:
            window.set_project_dirty(False)
            window.close()

    def test_scene_builder_propagates_viewcube_independently(self) -> None:
        state = create_application(
            settings_repository=InMemorySettingsRepository()
        ).state
        snapshot = SceneBuilder().build(
            state,
            options=SceneBuildOptions(show_axis_gizmo=False, show_viewcube=True),
        )
        self.assertFalse(snapshot.display["show_axis_gizmo"])
        self.assertTrue(snapshot.display["show_viewcube"])

    def test_explicit_visibility_command_covers_every_scene_leaf_category(self) -> None:
        composition = create_application(
            settings_repository=InMemorySettingsRepository()
        )
        state = composition.state
        state.mesh_object = _mesh_object()
        plane = state.section_collection.planes[0]
        section_result = StoredSectionResult(
            id="result-a",
            name="Result A",
            plane_id=plane.id,
            axis="Z",
            offset=0.0,
            result=SectionResult("Z", 0.0, (), 0),
        )
        state.section_collection.results.append(section_result)
        points = np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
        curve = StoredCurve(
            id="curve-a",
            name="Curve A",
            section_result_id="result-a",
            plane_id=plane.id,
            original_points=points.copy(),
            fitted_points=points.copy(),
            mean_error=0.0,
            max_error=0.0,
            is_closed=False,
        )
        add_curve(state.curve_collection, curve)
        manual_curve = replace(
            curve,
            id="curve-manual",
            name="Manual Curve",
            metadata={"creation_type": "manual"},
        )
        region_boundary = replace(
            curve,
            id="curve-region-boundary",
            name="Region Boundary",
            metadata={
                "creation_type": "region_boundary",
                "source_region_id": "region-a",
            },
        )
        add_curve(state.curve_collection, manual_curve)
        add_curve(state.curve_collection, region_boundary)
        preview = SurfacePatch("preview-a", "Preview", [curve.id], "loft")
        brep = BrepSurfaceRecord(
            "brep-a", "BREP", [curve.id], "loft_surface", "test"
        )
        add_surface(state.surface_collection, preview)
        add_brep_surface(state.brep_surface_collection, brep)
        region = RegionSelection(id="region-a", name="Region", triangle_indices=(0,))
        state.region_collection.set_active(region)
        selection = composition.selection_controller.select_nodes(
            (section_plane_node_id(plane.id),)
        )
        self.assertTrue(selection.success)
        selection_before = composition.selection_controller.snapshot().ids
        targets = (
            (NODE_MESH, state.mesh_object),
            (section_plane_node_id(plane.id), plane),
            (section_result_node_id(section_result.id), section_result),
            (curve_node_id(curve.id), curve),
            (curve_node_id(manual_curve.id), manual_curve),
            (curve_node_id(region_boundary.id), region_boundary),
            (surface_node_id(preview.id), preview),
            (surface_node_id(brep.id), brep),
            (region_node_id(region.id), region),
        )
        action = composition.actions.require("scene.set_visibility")
        for index, (node_id, owner) in enumerate(targets, start=1):
            result = composition.commands.dispatch(
                CommandRequest(
                    command_id=action.command_id,
                    action_id=action.id,
                    payload={"node_ids": (node_id,), "visible": False},
                )
            )
            self.assertTrue(result.success, node_id)
            self.assertFalse(owner.visible, node_id)
            self.assertEqual(len(composition.undo._undo_commands), index)
            self.assertEqual(
                composition.selection_controller.snapshot().ids,
                selection_before,
            )


class Task82BOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_idle_scene_has_layered_gizmo_and_no_world_axes(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.render_snapshot(_snapshot())
            _ready_without_native_render(viewport)
            viewport._position_axis_gizmo_renderer()
            state = viewport.diagnostic_state()
            inventory = {item["role"]: item for item in state.overlay_actor_inventory}
            self.assertEqual(viewport.render_window.GetRenderers().GetNumberOfItems(), 2)
            self.assertEqual(inventory["orientation_gizmo"]["layer"], 1)
            self.assertTrue(inventory["orientation_gizmo"]["visible"])
            self.assertFalse(inventory["transform_axes"]["visible"])
            self.assertFalse(inventory["rotation_ring"]["visible"])
            self.assertEqual(viewport._axis_gizmo_renderer.GetBackgroundAlpha(), 0.0)
            self.assertFalse(bool(viewport._axis_gizmo_renderer.GetInteractive()))
            x0, y0, x1, y1 = viewport._axis_gizmo_renderer.GetViewport()
            # Qt's offscreen QVTK child reports a synthetic 120x30 surface, so
            # exact pixel stability is asserted by the visible Win32 test.
            self.assertLessEqual(x0, 0.1)
            self.assertGreaterEqual(y0, 0.1)
            self.assertGreater(x1, x0)
            self.assertGreater(y1, y0)
        finally:
            viewport.close()

    def test_transform_axes_and_rotation_ring_follow_active_origin_only(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.render_snapshot(
                _snapshot(mode="move", axis="X", origin=(4.0, 5.0, 6.0))
            )
            _ready_without_native_render(viewport)
            self.assertTrue(bool(viewport._transform_axes_actor.GetVisibility()))
            self.assertEqual(viewport._transform_axes_actor.GetPosition(), (4.0, 5.0, 6.0))
            self.assertFalse(bool(viewport._rotation_ring_actor.GetVisibility()))
            self.assertGreater(
                viewport._transform_axes_actor.GetTotalLength()[0],
                viewport._transform_axes_actor.GetTotalLength()[1],
            )
            self.assertEqual(
                viewport._transform_axes_actor.GetXAxisShaftProperty().GetOpacity(),
                1.0,
            )
            self.assertAlmostEqual(
                viewport._transform_axes_actor.GetYAxisShaftProperty().GetOpacity(),
                0.28,
            )

            with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
                viewport.render_snapshot(
                    _snapshot(
                        revision=2,
                        mode="rotate",
                        axis="Y",
                        origin=(4.0, 5.0, 6.0),
                        angle_delta=32.0,
                    )
                )
            self.assertTrue(bool(viewport._rotation_ring_actor.GetVisibility()))
            self.assertGreater(
                viewport._rotation_ring_actor.GetMapper().GetInput().GetNumberOfPoints(),
                0,
            )
            self.assertEqual(
                viewport._rotation_ring_actor.GetMapper().GetInput().GetNumberOfCells(),
                97,
            )
            self.assertTrue(
                np.allclose(
                    viewport._rotation_ring_actor.GetProperty().GetColor(),
                    (0.2, 0.85, 0.25),
                )
            )

            with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
                viewport.render_snapshot(
                    _snapshot(
                        revision=3,
                        show_axes=False,
                        mode="move",
                        axis="X",
                        origin=(4.0, 5.0, 6.0),
                    )
                )
            self.assertFalse(bool(viewport._transform_axes_actor.GetVisibility()))

            with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
                viewport.render_snapshot(_snapshot(revision=4))
            self.assertFalse(bool(viewport._transform_axes_actor.GetVisibility()))
            self.assertFalse(bool(viewport._rotation_ring_actor.GetVisibility()))
        finally:
            viewport.close()

    def test_axis_and_view_controls_settings_are_independent(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.render_snapshot(
                _snapshot(show_axis_gizmo=False, show_viewcube=True)
            )
            _ready_without_native_render(viewport)
            self.assertFalse(viewport._axis_gizmo_visible)
            self.assertTrue(viewport.view_controls.visible)
            with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
                viewport.render_snapshot(
                    _snapshot(
                        revision=2,
                        show_axis_gizmo=True,
                        show_viewcube=False,
                    )
                )
            self.assertTrue(viewport._axis_gizmo_visible)
            self.assertFalse(viewport.view_controls.visible)
        finally:
            viewport.close()

    def test_orientation_gizmo_camera_tracks_the_scene_camera(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.render_snapshot(_snapshot())
            _ready_without_native_render(viewport)
            camera = viewport.renderer.GetActiveCamera()
            camera.SetFocalPoint(1.0, 2.0, 3.0)
            camera.SetPosition(7.0, -4.0, 11.0)
            camera.SetViewUp(0.2, 0.9, 0.3)
            viewport._sync_axis_gizmo_camera()
            self.assertTrue(
                np.allclose(
                    viewport._axis_gizmo_renderer.GetActiveCamera().GetDirectionOfProjection(),
                    camera.GetDirectionOfProjection(),
                )
            )
            actor = viewport._axis_gizmo_actor
            renderer = viewport._axis_gizmo_renderer
            synchronization_count = viewport.diagnostic_state().gizmo_synchronization_count
            with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
                viewport.render_snapshot(_snapshot(revision=2))
            self.assertIs(viewport._axis_gizmo_actor, actor)
            self.assertIs(viewport._axis_gizmo_renderer, renderer)
            self.assertEqual(
                viewport.diagnostic_state().gizmo_synchronization_count,
                synchronization_count,
            )
        finally:
            viewport.close()

    def test_view_control_buttons_are_triangular_and_emit_existing_action_ids(self) -> None:
        viewport = QtSceneViewport()
        actions: list[str] = []
        viewport.view_controls.action_requested.connect(actions.append)
        try:
            button = viewport.view_controls.buttons["view.named.top"]
            self.assertIsInstance(button, TriangularViewButton)
            self.assertTrue(button.hitButton(QPoint(button.width() // 2, 4)))
            self.assertFalse(button.hitButton(QPoint(0, 0)))
            for action_id, control in viewport.view_controls.buttons.items():
                control.click()
                self.assertEqual(actions[-1], action_id)
        finally:
            viewport.close()

    def test_actor_inventory_identifies_scene_mesh_and_every_overlay_role(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.render_snapshot(_snapshot())
            _ready_without_native_render(viewport)
            state = viewport.diagnostic_state()
            self.assertEqual(
                {item["role"] for item in state.scene_actor_inventory},
                {"mesh:mesh"},
            )
            self.assertEqual(
                {item["role"] for item in state.overlay_actor_inventory},
                {"grid", "transform_axes", "rotation_ring", "orientation_gizmo"},
            )
            self.assertTrue(
                all(not item["pickable"] for item in state.overlay_actor_inventory)
            )
            mesh = state.scene_actor_inventory[0]
            self.assertEqual(mesh["mapper_class"], "vtkOpenGLPolyDataMapper")
            self.assertEqual(mesh["point_count"], 3)
            self.assertEqual(mesh["cell_count"], 1)
            self.assertEqual(
                viewport.renderer.GetViewProps().GetNumberOfItems(),
                4,
                "main renderer must contain only mesh, grid, and hidden transform props",
            )
            self.assertEqual(
                viewport._axis_gizmo_renderer.GetViewProps().GetNumberOfItems(),
                1,
            )
        finally:
            viewport.close()

    def test_main_window_view_controls_dispatch_central_named_view_actions(self) -> None:
        composition = create_application(
            settings_repository=InMemorySettingsRepository()
        )
        window = OpenRetopV3Window(composition)
        try:
            with patch.object(
                window,
                "_dispatch_framework_action",
                wraps=window._dispatch_framework_action,
            ) as dispatch, patch.object(
                window.viewport,
                "pick_scene_object",
            ) as pick:
                with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
                    window.viewport.view_controls.buttons["view.named.top"].click()
                dispatch.assert_called_once_with("view.named.top")
                pick.assert_not_called()
        finally:
            window.set_project_dirty(False)
            window.close()

    def test_view_setting_actions_toggle_controls_and_gizmo_independently(self) -> None:
        composition = create_application(
            settings_repository=InMemorySettingsRepository()
        )
        window = OpenRetopV3Window(composition)
        try:
            _ready_without_native_render(window.viewport)
            self.assertTrue(window.viewport.view_controls.visible)
            self.assertTrue(window.viewport._axis_gizmo_visible)
            with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
                self.assertTrue(
                    window._dispatch_framework_action("view.toggle_view_controls")
                )
            self.assertFalse(window.viewport.view_controls.visible)
            self.assertTrue(window.viewport._axis_gizmo_visible)
            with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
                self.assertTrue(
                    window._dispatch_framework_action("view.toggle_axis_gizmo")
                )
            self.assertFalse(window.viewport._axis_gizmo_visible)
        finally:
            window.set_project_dirty(False)
            window.close()

    def test_view_controls_reposition_within_the_viewport(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.resize(640, 400)
            viewport.render_snapshot(_snapshot())
            _ready_without_native_render(viewport)
            viewport._position_view_controls()
            for button in viewport.view_controls.buttons.values():
                self.assertTrue(viewport.rect().contains(button.geometry()))
                self.assertTrue(button.accessibleName())
                self.assertTrue(button.toolTip())
        finally:
            viewport.close()

    def test_named_view_refits_visible_bounds_for_orthographic_projection(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.render_window.SetSize(640, 480)
            viewport.render_snapshot(
                _snapshot(camera_request=CameraRequest.named_view("top"))
            )
            with patch.object(viewport, "_renderer_has_size", return_value=True):
                _ready_without_native_render(viewport)
            camera = viewport.renderer.GetActiveCamera()
            self.assertTrue(bool(camera.GetParallelProjection()))
            self.assertAlmostEqual(camera.GetParallelScale(), 1.68, places=6)
            self.assertTrue(
                np.allclose(camera.GetDirectionOfProjection(), (0.0, 0.0, -1.0))
            )
            self.assertEqual(
                viewport.camera_controller.last_bounds,
                ((0.0, 0.0, 0.0), (2.0, 3.0, 0.0)),
            )
        finally:
            viewport.close()

    @unittest.skipIf(
        os.environ.get("QT_QPA_PLATFORM", "").strip().lower() == "offscreen"
        or platform.system() != "Windows",
        "requires the visible Windows Qt/VTK path",
    )
    def test_real_win32_camera_gestures_gizmo_and_resize(self) -> None:
        viewport = QtSceneViewport()
        viewport.resize(760, 520)
        viewport.render_snapshot(
            _snapshot(camera_request=CameraRequest.frame_all())
        )
        viewport.show()
        try:
            self.assertTrue(viewport.start())
            QTest.qWait(150)
            self.assertIn("OpenGL", viewport.render_window.GetClassName())
            self.assertEqual(
                viewport.interactor.GetInteractorStyle().GetClassName(),
                "vtkInteractorStyleTrackballCamera",
            )
            camera = viewport.renderer.GetActiveCamera()
            target = viewport.interactor.rect().center()

            before = _camera_state(camera)
            QTest.mousePress(viewport.interactor, Qt.MiddleButton, Qt.NoModifier, target)
            QTest.mouseMove(viewport.interactor, target + QPoint(45, 20), 30)
            QTest.mouseRelease(
                viewport.interactor,
                Qt.MiddleButton,
                Qt.NoModifier,
                target + QPoint(45, 20),
            )
            self.assertNotEqual(before, _camera_state(camera))

            before = _camera_state(camera)
            QTest.mousePress(viewport.interactor, Qt.LeftButton, Qt.NoModifier, target)
            QTest.mouseMove(viewport.interactor, target + QPoint(45, 20), 30)
            QTest.mouseRelease(
                viewport.interactor,
                Qt.LeftButton,
                Qt.NoModifier,
                target + QPoint(45, 20),
            )
            self.assertEqual(before, _camera_state(camera))
            self.assertFalse(viewport.last_pointer_release_was_click)

            before = _camera_state(camera)
            QTest.mousePress(viewport.interactor, Qt.LeftButton, Qt.AltModifier, target)
            QTest.mouseMove(viewport.interactor, target + QPoint(45, 20), 30)
            QTest.mouseRelease(
                viewport.interactor,
                Qt.LeftButton,
                Qt.AltModifier,
                target + QPoint(45, 20),
            )
            self.assertNotEqual(before, _camera_state(camera))

            before = _camera_state(camera)
            QTest.mousePress(viewport.interactor, Qt.LeftButton, Qt.ShiftModifier, target)
            QTest.mouseMove(viewport.interactor, target + QPoint(35, 15), 30)
            QTest.mouseRelease(
                viewport.interactor,
                Qt.LeftButton,
                Qt.ShiftModifier,
                target + QPoint(35, 15),
            )
            self.assertNotEqual(before, _camera_state(camera))

            before = _camera_state(camera)
            QTest.mousePress(viewport.interactor, Qt.RightButton, Qt.NoModifier, target)
            QTest.mouseMove(viewport.interactor, target + QPoint(0, 35), 30)
            QTest.mouseRelease(
                viewport.interactor,
                Qt.RightButton,
                Qt.NoModifier,
                target + QPoint(0, 35),
            )
            self.assertNotEqual(before, _camera_state(camera))

            before = _camera_state(camera)
            viewport.interactor.SetEventInformation(target.x(), target.y())
            viewport.interactor.MouseWheelForwardEvent()
            self.assertNotEqual(before, _camera_state(camera))

            before = _camera_state(camera)
            viewport.interactor.MouseWheelBackwardEvent()
            self.assertNotEqual(before, _camera_state(camera))

            for revision, name in enumerate(
                ("top", "bottom", "front", "back", "left", "right", "isometric"),
                start=10,
            ):
                viewport.render_snapshot(
                    _snapshot(
                        revision=revision,
                        camera_request=CameraRequest.named_view(name),
                    )
                )
                self.assertTrue(
                    np.all(np.isfinite(camera.GetPosition())),
                    name,
                )
                self.assertTrue(np.all(np.isfinite(camera.GetFocalPoint())), name)
                self.assertGreater(camera.GetClippingRange()[0], 0.0, name)
                self.assertGreater(
                    camera.GetClippingRange()[1],
                    camera.GetClippingRange()[0],
                    name,
                )
            viewport.render_snapshot(
                _snapshot(
                    revision=20,
                    camera_request=CameraRequest.frame_selected((NODE_MESH,)),
                )
            )
            self.assertEqual(
                viewport.camera_controller.last_bounds,
                ((0.0, 0.0, 0.0), (2.0, 3.0, 0.0)),
            )

            viewport.resize(1000, 700)
            QTest.qWait(100)
            x0, y0, x1, y1 = viewport._axis_gizmo_renderer.GetViewport()
            width, height = viewport.render_window.GetSize()
            expected = 96.0 * max(float(viewport.devicePixelRatioF()), 1.0)
            self.assertAlmostEqual((x1 - x0) * width, expected, delta=3.0)
            self.assertAlmostEqual((y1 - y0) * height, expected, delta=3.0)
            for button in viewport.view_controls.buttons.values():
                self.assertTrue(viewport.rect().contains(button.geometry()))
            viewport.showMinimized()
            QTest.qWait(75)
            viewport.showNormal()
            QTest.qWait(100)
            self.assertTrue(viewport.render())
            self.assertIsNone(viewport.diagnostic_state().last_rendering_error)
        finally:
            viewport.close()


if __name__ == "__main__":
    unittest.main()
