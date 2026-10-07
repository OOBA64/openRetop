from __future__ import annotations

import os
import platform
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]

from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from openretop.application.scene_ids import NODE_MESH  # noqa: E402
from openretop.mesh.triangle_mesh import TriangleMeshData  # noqa: E402
from openretop.presentation.qt.transform_overlays import (  # noqa: E402
    AXIS_COLORS,
    RING_SEGMENTS,
    overlay_reference_extent,
    transformed_object_origin,
)
from openretop.presentation.qt.viewport import QtSceneViewport  # noqa: E402
from openretop.viewer.scene_types import (  # noqa: E402
    CameraRequest,
    MeshRenderItem,
    SceneSnapshot,
    SelectionRenderState,
)


def _mesh() -> TriangleMeshData:
    return TriangleMeshData(
        vertices=np.asarray(
            [
                [-2.0, -3.0, -1.0],
                [8.0, -3.0, -1.0],
                [-2.0, 17.0, -1.0],
                [-2.0, -3.0, 4.0],
            ],
            dtype=float,
        ),
        triangles=np.asarray([[0, 1, 2], [0, 1, 3]], dtype=int),
    )


def _snapshot(
    *,
    revision: int = 1,
    mode: str | None = None,
    axis: str | None = None,
    constraint: str | None = None,
    origin: object = (11.0, 13.0, 17.0),
    angle: float | None = None,
    show_axes: bool = True,
    show_grid: bool = True,
    selected: bool = True,
    bounds: tuple[tuple[float, float, float], tuple[float, float, float]] = (
        (-2.0, -3.0, -1.0),
        (8.0, 17.0, 4.0),
    ),
    camera_request: CameraRequest | None = None,
) -> SceneSnapshot:
    return SceneSnapshot(
        revision=revision,
        meshes=(
            MeshRenderItem(
                id="mesh",
                revision=1,
                mesh=_mesh(),
                local_bounds=bounds,
                selection_keys=(NODE_MESH,),
            ),
        ),
        selection=SelectionRenderState(
            selected_ids=frozenset({NODE_MESH}) if selected else frozenset(),
            selected_item="model" if selected else None,
        ),
        display={
            "show_grid": show_grid,
            "show_axes": show_axes,
            "show_axis_gizmo": True,
            "show_viewcube": True,
            "display_colors": {"background_color": "#101316"},
        },
        camera_request=camera_request or CameraRequest(),
        object_origin=origin,
        active_transform_mode=mode,
        active_transform_axis=axis,
        active_transform_constraint=constraint,
        active_transform_angle_delta=angle,
    )


def _ready_without_native_render(viewport: QtSceneViewport) -> None:
    with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
        viewport._is_ready = True
        viewport.ready.emit()


def _submit(viewport: QtSceneViewport, snapshot: SceneSnapshot) -> None:
    with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
        viewport.render_snapshot(snapshot)


def _camera_state(viewport: QtSceneViewport) -> tuple[float, ...]:
    camera = viewport.renderer.GetActiveCamera()
    return tuple(
        float(value)
        for values in (
            camera.GetPosition(),
            camera.GetFocalPoint(),
            camera.GetViewUp(),
            camera.GetClippingRange(),
        )
        for value in values
    )


def _axis_opacity(actor: object, axis: str) -> float:
    return float(getattr(actor, f"Get{axis}AxisShaftProperty")().GetOpacity())


def _axis_color(actor: object, axis: str) -> tuple[float, float, float]:
    return tuple(
        float(value)
        for value in getattr(actor, f"Get{axis}AxisShaftProperty")().GetColor()
    )


def _ring_colors(actor: object) -> tuple[tuple[float, float, float, float], ...]:
    scalars = actor.GetMapper().GetInput().GetCellData().GetScalars()
    return tuple(tuple(float(value) for value in scalars.GetTuple4(index)) for index in range(4))


class TransformOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_idle_selection_and_project_load_never_show_transform_props(self) -> None:
        viewport = QtSceneViewport()
        try:
            pending = _snapshot(mode=None, selected=True)
            viewport.render_snapshot(pending)
            self.assertIsNone(viewport._transform_axes_actor)
            self.assertIsNone(viewport._rotation_ring_actor)

            _ready_without_native_render(viewport)
            diagnostics = viewport.diagnostic_state().transform_overlay
            self.assertEqual(diagnostics.hidden_reason, "inactive")
            self.assertFalse(diagnostics.move_axis_visible)
            self.assertFalse(diagnostics.rotation_ring_visible)
            self.assertFalse(diagnostics.move_actor_contributes_to_bounds)
            self.assertFalse(diagnostics.ring_actor_contributes_to_bounds)

            _submit(viewport, replace(pending, revision=2, object_origin=(1.0, 2.0, 3.0)))
            self.assertIsNone(viewport._transform_axes_actor)
            self.assertIsNone(viewport._rotation_ring_actor)
        finally:
            viewport.close()

    def test_invalid_origin_hides_without_falling_back_to_world_zero(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.render_snapshot(_snapshot(mode="move", origin=(5.0, 6.0, 7.0)))
            _ready_without_native_render(viewport)
            self.assertEqual(viewport._transform_axes_actor.GetPosition(), (5.0, 6.0, 7.0))

            _submit(
                viewport,
                _snapshot(revision=2, mode="move", origin=None),
            )
            state = viewport.diagnostic_state().transform_overlay
            self.assertEqual(state.hidden_reason, "invalid_origin")
            self.assertIsNone(state.world_origin)
            self.assertFalse(state.move_axis_visible)
            self.assertFalse(state.rotation_ring_visible)
            self.assertEqual(
                viewport._transform_axes_actor.GetPosition(),
                (5.0, 6.0, 7.0),
                "invalid input must not reposition a retained prop to world zero",
            )
            self.assertEqual(viewport._rotation_ring_actor.GetPosition(), (5.0, 6.0, 7.0))
        finally:
            viewport.close()

    def test_world_origin_conversion_uses_finite_homogeneous_math(self) -> None:
        matrix = np.asarray(
            [
                [2.0, 0.0, 0.0, 10.0],
                [0.0, 3.0, 0.0, -5.0],
                [0.0, 0.0, 4.0, 7.0],
                [0.0, 0.0, 0.0, 2.0],
            ],
            dtype=float,
        )
        self.assertTrue(
            np.allclose(
                transformed_object_origin((1.0, 2.0, 3.0), matrix),
                (6.0, 0.5, 9.5),
            )
        )
        self.assertEqual(
            transformed_object_origin((1.0, 2.0, 3.0), None, location=(9.0, 8.0, 7.0)),
            (9.0, 8.0, 7.0),
        )
        self.assertIsNone(transformed_object_origin(None, matrix))
        self.assertIsNone(transformed_object_origin((1.0, 2.0, 3.0), np.zeros((4, 4))))
        invalid = matrix.copy()
        invalid[0, 0] = np.inf
        self.assertIsNone(transformed_object_origin((1.0, 2.0, 3.0), invalid))

    def test_move_overlay_world_axes_colors_constraints_and_setting(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.render_snapshot(_snapshot(mode="move", constraint=None))
            _ready_without_native_render(viewport)
            actor = viewport._transform_axes_actor
            self.assertTrue(bool(actor.GetVisibility()))
            self.assertEqual(actor.GetPosition(), (11.0, 13.0, 17.0))
            self.assertFalse(bool(viewport._rotation_ring_actor.GetVisibility()))
            for axis in ("X", "Y", "Z"):
                self.assertTrue(np.allclose(_axis_color(actor, axis), AXIS_COLORS[axis]))
                self.assertEqual(_axis_opacity(actor, axis), 1.0)
            self.assertTrue(np.allclose(actor.GetTotalLength(), (5.6, 5.6, 5.6)))

            for revision, constraint in enumerate(("X", "Y", "Z"), start=2):
                _submit(
                    viewport,
                    _snapshot(
                        revision=revision,
                        mode="move",
                        axis=constraint,
                        constraint=constraint,
                    ),
                )
                for axis in ("X", "Y", "Z"):
                    expected = 1.0 if axis == constraint else 0.22
                    self.assertAlmostEqual(_axis_opacity(actor, axis), expected)
                lengths = actor.GetTotalLength()
                constrained_index = ("X", "Y", "Z").index(constraint)
                self.assertGreater(lengths[constrained_index], min(lengths))

            _submit(
                viewport,
                _snapshot(revision=5, mode="move", constraint="X", show_axes=False),
            )
            self.assertFalse(bool(actor.GetVisibility()))
            self.assertEqual(
                viewport.diagnostic_state().transform_overlay.hidden_reason,
                "setting_disabled",
            )
        finally:
            viewport.close()

    def test_move_actor_is_reused_noninteractive_and_excluded_from_bounds(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.render_snapshot(_snapshot(mode="move"))
            _ready_without_native_render(viewport)
            actor = viewport._transform_axes_actor
            state = viewport.diagnostic_state().transform_overlay
            geometry_updates = state.geometry_update_count
            self.assertEqual(state.actor_creation_count, 2)
            self.assertFalse(state.move_actor_pickable)
            self.assertFalse(state.move_actor_draggable)
            self.assertFalse(bool(actor.GetUseBounds()))
            self.assertFalse(state.move_actor_contributes_to_bounds)

            _submit(viewport, _snapshot(revision=2, mode="move"))
            repeated = viewport.diagnostic_state().transform_overlay
            self.assertIs(viewport._transform_axes_actor, actor)
            self.assertEqual(repeated.actor_creation_count, 2)
            self.assertEqual(repeated.geometry_update_count, geometry_updates)
        finally:
            viewport.close()

    def test_move_confirm_cancel_and_camera_motion_do_not_move_or_reset_actor(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.render_snapshot(_snapshot(mode="move"))
            _ready_without_native_render(viewport)
            actor = viewport._transform_axes_actor
            camera = viewport.renderer.GetActiveCamera()
            camera.SetPosition(45.0, -31.0, 29.0)
            camera.SetFocalPoint(2.0, 3.0, 4.0)
            before = _camera_state(viewport)
            camera.Azimuth(19.0)
            orbit_state = _camera_state(viewport)
            self.assertNotEqual(orbit_state, before)

            _submit(viewport, _snapshot(revision=2, mode="move", constraint="X"))
            self.assertEqual(actor.GetPosition(), (11.0, 13.0, 17.0))
            self.assertEqual(_camera_state(viewport), orbit_state)

            _submit(viewport, _snapshot(revision=3, mode=None))
            self.assertFalse(bool(actor.GetVisibility()))
            self.assertEqual(_camera_state(viewport), orbit_state)
            _submit(viewport, _snapshot(revision=4, mode="move"))
            _submit(viewport, _snapshot(revision=5, mode=None))
            self.assertFalse(bool(actor.GetVisibility()))
            self.assertEqual(_camera_state(viewport), orbit_state)
        finally:
            viewport.close()

    def test_rotate_shows_three_smooth_colored_rings_and_constraint_highlight(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.render_snapshot(
                _snapshot(mode="rotate", axis="Z", constraint=None, angle=15.0)
            )
            _ready_without_native_render(viewport)
            actor = viewport._rotation_ring_actor
            data = actor.GetMapper().GetInput()
            self.assertTrue(bool(actor.GetVisibility()))
            self.assertFalse(bool(viewport._transform_axes_actor.GetVisibility()))
            self.assertEqual(actor.GetPosition(), (11.0, 13.0, 17.0))
            self.assertEqual(data.GetNumberOfPoints(), RING_SEGMENTS * 3 + 2)
            self.assertEqual(data.GetNumberOfCells(), 4)
            colors = _ring_colors(actor)
            for index, axis in enumerate(("X", "Y", "Z")):
                expected = tuple(round(value * 255.0) for value in AXIS_COLORS[axis])
                self.assertEqual(colors[index][:3], expected)
                self.assertEqual(colors[index][3], 255.0)

            for revision, constraint in enumerate(("X", "Y", "Z"), start=2):
                _submit(
                    viewport,
                    _snapshot(
                        revision=revision,
                        mode="rotate",
                        axis=constraint,
                        constraint=constraint,
                        angle=22.0,
                    ),
                )
                colors = _ring_colors(actor)
                active_index = ("X", "Y", "Z").index(constraint)
                for index in range(3):
                    expected_alpha = 255.0 if index == active_index else 58.0
                    self.assertEqual(colors[index][3], expected_alpha)
        finally:
            viewport.close()

    def test_rotation_radius_is_finite_clamped_and_angle_reuses_actor(self) -> None:
        viewport = QtSceneViewport()
        huge_bounds = ((-1.0e9, -1.0e9, -1.0e9), (1.0e9, 1.0e9, 1.0e9))
        try:
            viewport.render_snapshot(
                _snapshot(mode="rotate", axis="Z", angle=0.0, bounds=huge_bounds)
            )
            _ready_without_native_render(viewport)
            actor = viewport._rotation_ring_actor
            first_state = viewport.diagnostic_state().transform_overlay
            first_actor = actor
            local_half_extent = (actor.GetBounds()[1] - actor.GetBounds()[0]) * 0.5
            self.assertAlmostEqual(local_half_extent, 600.0, places=3)
            self.assertEqual(first_state.reference_extent, 4_000.0)
            self.assertTrue(np.all(np.isfinite(actor.GetBounds())))

            _submit(
                viewport,
                _snapshot(
                    revision=2,
                    mode="rotate",
                    axis="Z",
                    angle=37.5,
                    bounds=huge_bounds,
                ),
            )
            second_state = viewport.diagnostic_state().transform_overlay
            self.assertIs(viewport._rotation_ring_actor, first_actor)
            self.assertEqual(second_state.actor_creation_count, 2)
            self.assertEqual(
                second_state.geometry_update_count,
                first_state.geometry_update_count + 1,
            )
            self.assertFalse(second_state.ring_actor_pickable)
            self.assertFalse(second_state.ring_actor_draggable)
            self.assertFalse(bool(actor.GetUseBounds()))
            self.assertFalse(second_state.ring_actor_contributes_to_bounds)
            self.assertEqual(overlay_reference_extent(((0, 0, 0), (1e-9, 0, 0))), 1.0)
        finally:
            viewport.close()

    def test_move_rotate_transition_settings_confirm_and_cancel_clear_stale_visuals(self) -> None:
        viewport = QtSceneViewport()
        try:
            viewport.render_snapshot(_snapshot(mode="move"))
            _ready_without_native_render(viewport)
            self.assertTrue(bool(viewport._transform_axes_actor.GetVisibility()))
            _submit(viewport, _snapshot(revision=2, mode="rotate", axis="Z", angle=4.0))
            self.assertFalse(bool(viewport._transform_axes_actor.GetVisibility()))
            self.assertTrue(bool(viewport._rotation_ring_actor.GetVisibility()))
            _submit(
                viewport,
                _snapshot(revision=3, mode="rotate", show_axes=False, angle=4.0),
            )
            self.assertFalse(bool(viewport._rotation_ring_actor.GetVisibility()))
            _submit(viewport, _snapshot(revision=4, mode=None))
            self.assertFalse(bool(viewport._transform_axes_actor.GetVisibility()))
            self.assertFalse(bool(viewport._rotation_ring_actor.GetVisibility()))
            _submit(viewport, _snapshot(revision=5, mode="rotate", angle=4.0))
            _submit(viewport, _snapshot(revision=6, mode=None))
            self.assertFalse(bool(viewport._rotation_ring_actor.GetVisibility()))
        finally:
            viewport.close()

    def test_callable_inventory_classifies_all_props_and_mesh_is_unchanged(self) -> None:
        snapshot = _snapshot(mode=None)
        mesh = snapshot.meshes[0].mesh
        vertices_before = mesh.vertices.copy()
        triangles_before = mesh.triangles.copy()
        viewport = QtSceneViewport()
        try:
            viewport.render_snapshot(snapshot)
            _ready_without_native_render(viewport)
            inventory = viewport.renderer_prop_inventory()
            roles = {item["role"]: item for item in inventory}
            self.assertNotIn("unidentified", {item["semantic_category"] for item in inventory})
            self.assertEqual(roles["mesh:mesh"]["semantic_category"], "imported_scene_geometry")
            self.assertNotIn("orientation_gizmo", roles)
            self.assertNotIn("transform_axes", roles)
            self.assertNotIn("rotation_ring", roles)
            self.assertFalse(any(item["role"].startswith("navigation") for item in inventory))
            self.assertTrue(roles["grid"]["visible"])

            _submit(
                viewport,
                replace(
                    snapshot,
                    revision=2,
                    active_transform_mode="move",
                    object_origin=(11.0, 13.0, 17.0),
                    display={**snapshot.display, "show_grid": False},
                ),
            )
            updated = {item["role"]: item for item in viewport.renderer_prop_inventory()}
            self.assertFalse(updated["grid"]["visible"])
            self.assertTrue(updated["transform_axes"]["visible"])
            self.assertFalse(updated["rotation_ring"]["visible"])
            self.assertIsNone(updated["rotation_ring"]["point_count"])
            self.assertFalse(
                updated["rotation_ring"]["contributes_to_main_visible_bounds"]
            )
            np.testing.assert_array_equal(mesh.vertices, vertices_before)
            np.testing.assert_array_equal(mesh.triangles, triangles_before)
        finally:
            viewport.close()

    def test_frame_all_and_selected_use_only_snapshot_bounds(self) -> None:
        viewport = QtSceneViewport()
        bounds = ((-2.0, -3.0, -1.0), (8.0, 17.0, 4.0))
        try:
            viewport.render_snapshot(
                _snapshot(
                    mode="move",
                    camera_request=CameraRequest.frame_all(),
                )
            )
            with patch.object(viewport, "_renderer_has_size", return_value=True):
                _ready_without_native_render(viewport)
            self.assertEqual(viewport.camera_controller.last_bounds, bounds)
            camera_after_all = _camera_state(viewport)

            _submit(viewport, _snapshot(revision=2, mode="rotate", axis="Z", angle=9.0))
            self.assertEqual(_camera_state(viewport), camera_after_all)
            selected_request = CameraRequest.frame_selected((NODE_MESH,))
            with patch.object(viewport, "_renderer_has_size", return_value=True):
                _submit(
                    viewport,
                    _snapshot(
                        revision=3,
                        mode="rotate",
                        axis="Z",
                        angle=9.0,
                        camera_request=selected_request,
                    ),
                )
            self.assertEqual(viewport.camera_controller.last_bounds, bounds)
        finally:
            viewport.close()

    @unittest.skipIf(
        os.environ.get("QT_QPA_PLATFORM", "").strip().lower() == "offscreen"
        or platform.system() != "Windows",
        "requires a visible Windows Qt platform",
    )
    def test_real_visible_windows_vtk_transform_overlay(self) -> None:
        viewport = QtSceneViewport()
        viewport.resize(720, 480)
        viewport.render_snapshot(_snapshot(mode="rotate", axis="Z", angle=12.0))
        viewport.show()
        try:
            QTest.qWait(100)
            self.assertTrue(viewport.start())
            self.assertTrue(viewport.render())
            QTest.qWait(150)
            self.assertIn("OpenGL", viewport.render_window.GetClassName())
            self.assertEqual(viewport.render_window.GetClassName(), "vtkWin32OpenGLRenderWindow")
            self.assertTrue(bool(viewport._rotation_ring_actor.GetVisibility()))
            self.assertFalse(bool(viewport._transform_axes_actor.GetVisibility()))
            move_actor = viewport._transform_axes_actor
            ring_actor = viewport._rotation_ring_actor
            viewport.resize(920, 620)
            QTest.qWait(60)
            viewport.showMaximized()
            QTest.qWait(60)
            viewport.showNormal()
            QTest.qWait(60)
            viewport.showMinimized()
            QTest.qWait(60)
            viewport.showNormal()
            QTest.qWait(80)
            self.assertTrue(viewport.render())
            self.assertIs(viewport._transform_axes_actor, move_actor)
            self.assertIs(viewport._rotation_ring_actor, ring_actor)
            self.assertEqual(
                viewport.diagnostic_state().transform_overlay.actor_creation_count,
                2,
            )
            self.assertTrue(bool(viewport._rotation_ring_actor.GetVisibility()))
            self.assertIsNone(viewport.diagnostic_state().last_rendering_error)
        finally:
            viewport.close()


if __name__ == "__main__":
    unittest.main()
