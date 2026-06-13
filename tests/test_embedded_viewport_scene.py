from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from curves.curve_state import StoredCurve
from geometry.sections import SectionPolyline, SectionResult
from mesh.triangle_mesh import TriangleMeshData
from sections.section_state import SectionPlaneState
from surfaces.surface_preview import SurfacePreviewMesh
from viewer.embedded_viewport import (
    EmbeddedVTKViewport,
    SELECTION_BOUNDING_BOX_LINE_WIDTH,
    SECTION_RESULT_LINE_WIDTH,
    SELECTED_CURVE_LINE_WIDTH,
    UNSELECTED_CURVE_LINE_WIDTH,
    _bounds_corners,
    _line_polydata,
    _mesh_actor,
    _mesh_polydata,
    _point_to_segment_distance,
)
from viewer.overlays import build_bounding_box_outline


class EmbeddedViewportSceneTests(unittest.TestCase):
    def _triangle_mesh(self) -> TriangleMeshData:
        return TriangleMeshData(
            vertices=np.asarray(
                [
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                ],
                dtype=float,
            ),
            triangles=np.asarray([[0, 1, 2]], dtype=int),
        )

    def _viewport(self) -> EmbeddedVTKViewport:
        viewport = EmbeddedVTKViewport(parent=object())
        viewport._is_started = True
        viewport._render = lambda: None  # type: ignore[method-assign]
        return viewport

    def _set_basic_scene(
        self,
        viewport: EmbeddedVTKViewport,
        mesh: TriangleMeshData | None,
        **kwargs: object,
    ) -> None:
        scene_kwargs = {
            "transform_matrix": np.identity(4),
            "show_grid": True,
            "show_axes": True,
            "show_normals": False,
            "show_section_plane": True,
            "section_axis": "Z",
            "section_offset": 0.0,
            "selected_item": None,
            "object_origin": None,
            "scene_bounds_min": None,
            "scene_bounds_max": None,
            "active_transform_mode": None,
            "active_transform_axis": None,
            "active_transform_angle_delta": None,
            "section_result": None,
            "curve_results": [],
            "surface_previews": [],
            "active_surface_id": None,
            "reset_camera": False,
        }
        scene_kwargs.update(kwargs)
        viewport.set_scene(mesh, **scene_kwargs)

    def _actor_count(self, viewport: EmbeddedVTKViewport) -> int:
        return int(viewport.renderer.GetActors().GetNumberOfItems())

    def _actor_points(self, actor: object) -> np.ndarray:
        polydata = actor.GetMapper().GetInput()
        return np.asarray(
            [polydata.GetPoint(index) for index in range(polydata.GetNumberOfPoints())],
            dtype=float,
        )

    def _ring_radius(self, actor: object, origin: tuple[float, float, float]) -> float:
        points = self._actor_points(actor)
        origin_array = np.asarray(origin, dtype=float)
        distances = np.linalg.norm(points - origin_array, axis=1)
        return float(np.mean(distances))

    def test_app_shortcut_keys_are_not_forwarded_to_vtk_interactor(self) -> None:
        class FakeInteractor:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def SetEventInformationFlipY(self, *_args: object) -> None:
                self.calls.append("event")

            def KeyPressEvent(self) -> None:
                self.calls.append("key")

            def CharEvent(self) -> None:
                self.calls.append("char")

        viewport = EmbeddedVTKViewport(parent=object())
        interactor = FakeInteractor()
        viewport.interactor = interactor  # type: ignore[assignment]
        render_calls: list[bool] = []
        viewport._render = lambda: render_calls.append(True)  # type: ignore[method-assign]

        viewport._on_key_press(SimpleNamespace(keysym="r", char="r", x=4, y=5, state=0))

        self.assertEqual(interactor.calls, [])
        self.assertEqual(render_calls, [])

    def test_non_app_shortcut_keys_still_forward_to_vtk_interactor(self) -> None:
        class FakeInteractor:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def SetEventInformationFlipY(self, *_args: object) -> None:
                self.calls.append("event")

            def KeyPressEvent(self) -> None:
                self.calls.append("key")

            def CharEvent(self) -> None:
                self.calls.append("char")

        viewport = EmbeddedVTKViewport(parent=object())
        interactor = FakeInteractor()
        viewport.interactor = interactor  # type: ignore[assignment]
        render_calls: list[bool] = []
        viewport._render = lambda: render_calls.append(True)  # type: ignore[method-assign]

        viewport._on_key_press(SimpleNamespace(keysym="a", char="a", x=4, y=5, state=0))

        self.assertEqual(interactor.calls, ["event", "key", "char"])
        self.assertEqual(render_calls, [True])

    def test_get_camera_vectors_returns_screen_basis_without_raw_camera(self) -> None:
        viewport = self._viewport()
        camera = viewport.renderer.GetActiveCamera()
        camera.SetPosition(0.0, 0.0, 10.0)
        camera.SetFocalPoint(0.0, 0.0, 0.0)
        camera.SetViewUp(0.0, 1.0, 0.0)

        vectors = viewport.get_camera_vectors()

        self.assertTrue(np.allclose(vectors.forward, [0.0, 0.0, -1.0]))
        self.assertTrue(np.allclose(vectors.right, [1.0, 0.0, 0.0]))
        self.assertTrue(np.allclose(vectors.up, [0.0, 1.0, 0.0]))
        self.assertTrue(np.allclose(vectors.position, [0.0, 0.0, 10.0]))
        self.assertTrue(np.allclose(vectors.focal_point, [0.0, 0.0, 0.0]))

    def test_triangle_mesh_converts_to_vtk_polydata(self) -> None:
        mesh = self._triangle_mesh()
        mesh.compute_vertex_normals()

        polydata = _mesh_polydata(mesh)

        self.assertEqual(polydata.GetNumberOfPoints(), 3)
        self.assertEqual(polydata.GetNumberOfPolys(), 1)
        self.assertIsNotNone(polydata.GetPointData().GetNormals())

    def test_mesh_actor_renders_as_smooth_surface(self) -> None:
        actor = _mesh_actor(self._triangle_mesh())
        prop = actor.GetProperty()

        self.assertEqual(prop.GetRepresentation(), 2)
        self.assertEqual(prop.GetEdgeVisibility(), 0)
        self.assertEqual(prop.GetInterpolation(), 2)

    def test_mesh_actor_is_reused_for_same_display_mesh(self) -> None:
        viewport = EmbeddedVTKViewport(parent=object())
        mesh = self._triangle_mesh()

        first_actor = viewport._ensure_mesh_actor(mesh)
        second_actor = viewport._ensure_mesh_actor(mesh)
        replacement_actor = viewport._ensure_mesh_actor(mesh.copy())

        self.assertIs(first_actor, second_actor)
        self.assertIsNot(first_actor, replacement_actor)

    def test_view_metrics_can_use_source_bounds_instead_of_display_bounds(self) -> None:
        viewport = EmbeddedVTKViewport(parent=object())
        mesh = self._triangle_mesh()
        matrix = np.identity(4)
        matrix[0, 3] = 3.0

        viewport._update_view_metrics(
            mesh,
            matrix,
            scene_bounds_min=(-2.0, -3.0, -4.0),
            scene_bounds_max=(2.0, 3.0, 4.0),
        )

        self.assertTrue(np.allclose(viewport._mesh_min_bound, [1.0, -3.0, -4.0]))
        self.assertTrue(np.allclose(viewport._mesh_max_bound, [5.0, 3.0, 4.0]))

    def test_interactive_transform_updates_existing_actor_matrix(self) -> None:
        viewport = EmbeddedVTKViewport(parent=object())
        mesh = self._triangle_mesh()
        actor = viewport._ensure_mesh_actor(mesh)
        transform_key = viewport._active_mesh_transform_key(mesh, "move", "X", "model")
        viewport._interactive_transform_key = transform_key
        render_calls: list[bool] = []
        viewport._render = lambda: render_calls.append(True)  # type: ignore[method-assign]
        matrix = np.identity(4)
        matrix[0, 3] = 4.0

        handled = viewport._try_update_interactive_mesh_transform(
            mesh,
            matrix,
            transform_key=transform_key,
            reset_camera=False,
            show_grid=False,
            show_axes=False,
            show_normals=False,
            show_section_plane=False,
            section_axis="Z",
            section_offset=0.0,
            section_planes=None,
            active_section_plane_id=None,
            selected_item="model",
            object_origin=(4.0, 0.0, 0.0),
            active_transform_mode="move",
            active_transform_axis="X",
            active_transform_angle_delta=None,
            section_result=None,
            curve_results=[],
        )

        self.assertTrue(handled)
        self.assertEqual(render_calls, [True])
        self.assertIs(actor, viewport._mesh_actor)
        self.assertAlmostEqual(actor.GetUserMatrix().GetElement(0, 3), 4.0)

    def test_interactive_move_updates_selection_overlays_without_duplicate_actors(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()
        self._set_basic_scene(
            viewport,
            mesh,
            selected_item="model",
            object_origin=(0.0, 0.0, 0.0),
            active_transform_mode="move",
            active_transform_axis="X",
        )
        first_actor = viewport._mesh_actor
        first_count = self._actor_count(viewport)
        first_selection_key = viewport._group_keys["selection_overlays"]
        first_gizmo_key = viewport._group_keys["active_transform_gizmo"]
        translated = np.identity(4)
        translated[0, 3] = 2.0

        self._set_basic_scene(
            viewport,
            mesh,
            transform_matrix=translated,
            selected_item="model",
            object_origin=(2.0, 0.0, 0.0),
            active_transform_mode="move",
            active_transform_axis="X",
        )

        self.assertIs(viewport._mesh_actor, first_actor)
        self.assertEqual(self._actor_count(viewport), first_count)
        self.assertNotEqual(viewport._group_keys["selection_overlays"], first_selection_key)
        self.assertNotEqual(viewport._group_keys["active_transform_gizmo"], first_gizmo_key)
        self.assertIn((2.0, 0.0, 0.0), viewport._group_keys["selection_overlays"])
        self.assertIn((2.0, 0.0, 0.0), viewport._group_keys["active_transform_gizmo"])

    def test_model_selection_bounding_box_is_thin_and_selection_only(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()

        self._set_basic_scene(
            viewport,
            mesh,
            selected_item="model",
            object_origin=(0.0, 0.0, 0.0),
        )

        selection_actors = viewport._actor_groups["selection_overlays"]
        self.assertGreaterEqual(len(selection_actors), 1)
        self.assertAlmostEqual(
            selection_actors[0].GetProperty().GetLineWidth(),
            SELECTION_BOUNDING_BOX_LINE_WIDTH,
        )

        self._set_basic_scene(viewport, mesh, selected_item=None, object_origin=None)

        self.assertNotIn("selection_overlays", viewport._actor_groups)
        self.assertNotIn("selection_overlays", viewport._group_keys)

    def test_interactive_rotate_updates_selection_bounds_without_duplicate_actors(self) -> None:
        viewport = self._viewport()
        mesh = TriangleMeshData(
            vertices=np.asarray(
                [
                    [0.0, 0.0, 0.0],
                    [2.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                ],
                dtype=float,
            ),
            triangles=np.asarray([[0, 1, 2]], dtype=int),
        )
        self._set_basic_scene(
            viewport,
            mesh,
            selected_item="model",
            object_origin=(0.0, 0.0, 0.0),
            active_transform_mode="rotate",
            active_transform_axis="Z",
        )
        first_actor = viewport._mesh_actor
        first_count = self._actor_count(viewport)
        first_selection_key = viewport._group_keys["selection_overlays"]
        rotation = np.asarray(
            [
                [0.0, -1.0, 0.0, 0.0],
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ],
            dtype=float,
        )

        self._set_basic_scene(
            viewport,
            mesh,
            transform_matrix=rotation,
            selected_item="model",
            object_origin=(0.0, 0.0, 0.0),
            active_transform_mode="rotate",
            active_transform_axis="Z",
        )

        self.assertIs(viewport._mesh_actor, first_actor)
        self.assertEqual(self._actor_count(viewport), first_count)
        self.assertNotEqual(viewport._group_keys["selection_overlays"], first_selection_key)
        self.assertTrue(np.allclose(viewport._mesh_min_bound, [-1.0, 0.0, 0.0]))
        self.assertTrue(np.allclose(viewport._mesh_max_bound, [0.0, 2.0, 0.0]))

    def test_rotation_ring_radius_uses_axis_specific_object_extents(self) -> None:
        viewport = self._viewport()
        mesh = TriangleMeshData(
            vertices=np.asarray(
                [
                    [0.0, 0.0, 0.0],
                    [2.0, 0.0, 0.0],
                    [0.0, 4.0, 0.0],
                    [0.0, 0.0, 6.0],
                ],
                dtype=float,
            ),
            triangles=np.asarray([[0, 1, 2], [0, 1, 3]], dtype=int),
        )

        expected_by_axis = {"X": 3.6, "Y": 3.6, "Z": 2.4}
        for axis, expected_radius in expected_by_axis.items():
            viewport._reset_rotation_overlay_bounds()
            self._set_basic_scene(
                viewport,
                mesh,
                selected_item="model",
                object_origin=(0.0, 0.0, 0.0),
                active_transform_mode="rotate",
                active_transform_axis=axis,
                active_transform_angle_delta=0.0,
            )

            ring_actor = viewport._actor_groups["active_transform_gizmo"][1]
            ring_points = self._actor_points(ring_actor)
            self.assertAlmostEqual(self._ring_radius(ring_actor, (0.0, 0.0, 0.0)), expected_radius)
            if axis == "X":
                self.assertTrue(np.allclose(ring_points[:, 0], 0.0))
            elif axis == "Y":
                self.assertTrue(np.allclose(ring_points[:, 1], 0.0))
            else:
                self.assertTrue(np.allclose(ring_points[:, 2], 0.0))

    def test_rotation_ring_radius_stays_stable_during_active_rotation(self) -> None:
        viewport = self._viewport()
        mesh = TriangleMeshData(
            vertices=np.asarray(
                [
                    [0.0, 0.0, 0.0],
                    [2.0, 0.0, 0.0],
                    [0.0, 4.0, 0.0],
                    [0.0, 0.0, 1.0],
                ],
                dtype=float,
            ),
            triangles=np.asarray([[0, 1, 2], [0, 1, 3]], dtype=int),
        )
        self._set_basic_scene(
            viewport,
            mesh,
            selected_item="model",
            object_origin=(0.0, 0.0, 0.0),
            active_transform_mode="rotate",
            active_transform_axis="Z",
            active_transform_angle_delta=0.0,
        )
        initial_radius = self._ring_radius(
            viewport._actor_groups["active_transform_gizmo"][1],
            (0.0, 0.0, 0.0),
        )
        rotation = np.asarray(
            [
                [0.0, -1.0, 0.0, 0.0],
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ],
            dtype=float,
        )

        self._set_basic_scene(
            viewport,
            mesh,
            transform_matrix=rotation,
            selected_item="model",
            object_origin=(0.0, 0.0, 0.0),
            active_transform_mode="rotate",
            active_transform_axis="Z",
            active_transform_angle_delta=25.0,
        )

        updated_radius = self._ring_radius(
            viewport._actor_groups["active_transform_gizmo"][1],
            (0.0, 0.0, 0.0),
        )
        self.assertAlmostEqual(updated_radius, initial_radius)

    def test_rotation_angle_indicator_updates_live_with_angle_delta(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()

        self._set_basic_scene(
            viewport,
            mesh,
            selected_item="model",
            object_origin=(0.0, 0.0, 0.0),
            active_transform_mode="rotate",
            active_transform_axis="Z",
            active_transform_angle_delta=0.0,
        )
        self.assertEqual(len(viewport._actor_groups["active_transform_gizmo"]), 2)

        self._set_basic_scene(
            viewport,
            mesh,
            selected_item="model",
            object_origin=(0.0, 0.0, 0.0),
            active_transform_mode="rotate",
            active_transform_axis="Z",
            active_transform_angle_delta=30.0,
        )

        gizmo_actors = viewport._actor_groups["active_transform_gizmo"]
        self.assertEqual(len(gizmo_actors), 3)
        angle_points = self._actor_points(gizmo_actors[2])
        self.assertGreater(len(angle_points), 3)
        self.assertTrue(np.allclose(angle_points[:, 2], 0.0))

    def test_repeated_set_scene_calls_do_not_duplicate_actors(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()

        self._set_basic_scene(viewport, mesh)
        first_count = self._actor_count(viewport)
        self._set_basic_scene(viewport, mesh)
        second_count = self._actor_count(viewport)
        self._set_basic_scene(viewport, mesh)
        third_count = self._actor_count(viewport)

        self.assertEqual(first_count, 4)
        self.assertEqual(second_count, first_count)
        self.assertEqual(third_count, first_count)
        self.assertEqual(
            set(viewport._actors_by_role),
            {"mesh", "grid", "axes"},
        )
        self.assertEqual(set(viewport._actor_groups), {"section_planes"})
        self.assertEqual(len(viewport._actor_groups["section_planes"]), 1)

    def test_multiple_section_planes_render_visible_planes_with_selected_styling(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()
        first_plane = SectionPlaneState(
            id="plane-1",
            name="Section Plane 1",
            axis="Z",
            offset=0.0,
            visible=True,
            selected=False,
        )
        second_plane = SectionPlaneState(
            id="plane-2",
            name="Section Plane 2",
            axis="X",
            offset=0.25,
            visible=True,
            selected=True,
        )
        hidden_plane = SectionPlaneState(
            id="plane-3",
            name="Section Plane 3",
            axis="Y",
            offset=0.5,
            visible=False,
            selected=False,
        )

        self._set_basic_scene(
            viewport,
            mesh,
            show_section_plane=False,
            section_planes=(first_plane, second_plane, hidden_plane),
            active_section_plane_id=second_plane.id,
        )

        self.assertEqual(self._actor_count(viewport), 5)
        self.assertEqual(len(viewport._section_plane_actors), 2)
        self.assertEqual(len(viewport._section_plane_pick_geometries), 2)
        self.assertEqual(len(viewport._actor_groups["section_planes"]), 2)
        self.assertEqual(
            [
                actor.GetProperty().GetLineWidth()
                for actor in viewport._section_plane_actors
            ],
            [2.0, 3.0],
        )
        first_points = self._actor_points(viewport._section_plane_actors[0])
        second_points = self._actor_points(viewport._section_plane_actors[1])
        self.assertTrue(np.allclose(first_points[:, 2], 0.0))
        self.assertTrue(np.allclose(second_points[:, 0], 0.25))

        first_plane.visible = False
        second_plane.visible = False
        self._set_basic_scene(
            viewport,
            mesh,
            show_section_plane=True,
            section_planes=(first_plane, second_plane, hidden_plane),
            active_section_plane_id=second_plane.id,
        )

        self.assertEqual(self._actor_count(viewport), 3)
        self.assertEqual(viewport._section_plane_actors, [])
        self.assertEqual(viewport._section_plane_pick_geometries, [])
        self.assertNotIn("section_planes", viewport._actor_groups)

    def test_selected_curve_renders_with_selected_overlay(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()
        points = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
            ],
            dtype=float,
        )
        first_curve = StoredCurve(
            id="curve-1",
            name="Section 1 Curve 1",
            section_result_id="section-result-1",
            plane_id="plane-1",
            original_points=points,
            fitted_points=points.copy(),
            mean_error=0.0,
            max_error=0.0,
            is_closed=False,
            selected=False,
        )
        second_curve = StoredCurve(
            id="curve-2",
            name="Section 2 Curve 1",
            section_result_id="section-result-2",
            plane_id="plane-2",
            original_points=points,
            fitted_points=points.copy(),
            mean_error=0.0,
            max_error=0.0,
            is_closed=False,
            selected=True,
        )

        self._set_basic_scene(
            viewport,
            mesh,
            curve_results=[first_curve, second_curve],
        )

        self.assertIn("curve_result", viewport._actors_by_role)
        self.assertIn("selected_curve_result", viewport._actor_groups)
        self.assertEqual(len(viewport._actor_groups["selected_curve_result"]), 1)
        self.assertAlmostEqual(
            viewport._actor_groups["selected_curve_result"][0].GetProperty().GetLineWidth(),
            SELECTED_CURVE_LINE_WIDTH,
            places=5,
        )
        self.assertAlmostEqual(
            viewport._actors_by_role["curve_result"].GetProperty().GetLineWidth(),
            UNSELECTED_CURVE_LINE_WIDTH,
            places=5,
        )

    def test_surface_previews_render_and_clear_with_selected_styling(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()
        first_preview = SurfacePreviewMesh(
            vertices=np.asarray(
                [
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                ],
                dtype=float,
            ),
            faces=np.asarray([[0, 1, 2]], dtype=int),
            source_surface_id="surface-1",
        )
        second_preview = SurfacePreviewMesh(
            vertices=np.asarray(
                [
                    [0.0, 0.0, 0.1],
                    [1.0, 0.0, 0.1],
                    [0.0, 1.0, 0.1],
                ],
                dtype=float,
            ),
            faces=np.asarray([[0, 1, 2]], dtype=int),
            source_surface_id="surface-2",
        )

        self._set_basic_scene(
            viewport,
            mesh,
            surface_previews=[first_preview, second_preview],
            active_surface_id="surface-2",
        )

        self.assertIn("surface_previews", viewport._actor_groups)
        surface_actors = viewport._actor_groups["surface_previews"]
        self.assertEqual(len(surface_actors), 2)
        self.assertLess(surface_actors[0].GetProperty().GetOpacity(), 1.0)
        self.assertGreater(
            surface_actors[1].GetProperty().GetOpacity(),
            surface_actors[0].GetProperty().GetOpacity(),
        )
        self.assertEqual(surface_actors[1].GetProperty().GetEdgeVisibility(), 1)
        count_with_previews = self._actor_count(viewport)

        self._set_basic_scene(
            viewport,
            mesh,
            surface_previews=[],
            active_surface_id=None,
        )

        self.assertNotIn("surface_previews", viewport._actor_groups)
        self.assertEqual(self._actor_count(viewport), count_with_previews - 2)

    def test_clearing_mesh_preserves_view_metrics_and_reference_actors(self) -> None:
        viewport = self._viewport()
        mesh = TriangleMeshData(
            vertices=np.asarray(
                [
                    [-2.0, -1.0, 0.0],
                    [4.0, -1.0, 0.0],
                    [-2.0, 3.0, 5.0],
                ],
                dtype=float,
            ),
            triangles=np.asarray([[0, 1, 2]], dtype=int),
        )
        self._set_basic_scene(viewport, mesh)
        view_center = viewport._view_center.copy()
        view_extent = viewport._view_extent
        grid_actor = viewport._actors_by_role["grid"]
        axes_actor = viewport._actors_by_role["axes"]

        self._set_basic_scene(viewport, None, reset_camera=False)

        self.assertTrue(np.allclose(viewport._view_center, view_center))
        self.assertEqual(viewport._view_extent, view_extent)
        self.assertNotIn("mesh", viewport._actors_by_role)
        self.assertIs(viewport._actors_by_role["grid"], grid_actor)
        self.assertIs(viewport._actors_by_role["axes"], axes_actor)

    def test_set_scene_reuses_mesh_actor_when_mesh_identity_is_unchanged(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()
        self._set_basic_scene(viewport, mesh)
        first_actor = viewport._mesh_actor
        translated = np.identity(4)
        translated[0, 3] = 2.5

        self._set_basic_scene(viewport, mesh, transform_matrix=translated)

        self.assertIs(viewport._mesh_actor, first_actor)
        self.assertIs(viewport._actors_by_role["mesh"], first_actor)
        self.assertAlmostEqual(first_actor.GetUserMatrix().GetElement(0, 3), 2.5)

    def test_set_scene_replaces_mesh_actor_when_mesh_identity_changes(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()
        self._set_basic_scene(viewport, mesh)
        first_actor = viewport._mesh_actor

        self._set_basic_scene(viewport, mesh.copy())

        self.assertIsNot(viewport._mesh_actor, first_actor)
        self.assertIs(viewport._actors_by_role["mesh"], viewport._mesh_actor)

    def test_clearing_section_result_removes_section_actor(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()
        section_result = SectionResult(
            axis="Z",
            offset=0.0,
            polylines=(
                SectionPolyline(
                    points=np.asarray(
                        [
                            [0.0, 0.0, 0.0],
                            [1.0, 0.0, 0.0],
                            [0.0, 1.0, 0.0],
                        ],
                        dtype=float,
                    )
                ),
            ),
            segment_count=2,
        )

        self._set_basic_scene(viewport, mesh, section_result=section_result)
        section_count = self._actor_count(viewport)
        section_actor = viewport._actors_by_role["section_result"]
        self.assertAlmostEqual(
            section_actor.GetProperty().GetLineWidth(),
            SECTION_RESULT_LINE_WIDTH,
            places=5,
        )
        self.assertLess(SECTION_RESULT_LINE_WIDTH, SELECTED_CURVE_LINE_WIDTH)

        self._set_basic_scene(viewport, mesh, section_result=None)

        self.assertNotIn("section_result", viewport._actors_by_role)
        self.assertEqual(self._actor_count(viewport), section_count - 1)
        self.assertIsNot(viewport._actors_by_role.get("section_result"), section_actor)

    def test_line_geometry_converts_to_vtk_polydata_with_cell_colors(self) -> None:
        lines = build_bounding_box_outline((0.0, 0.0, 0.0), (1.0, 2.0, 3.0))

        polydata = _line_polydata(lines)

        self.assertEqual(polydata.GetNumberOfPoints(), 8)
        self.assertEqual(polydata.GetNumberOfLines(), 12)
        self.assertIsNotNone(polydata.GetCellData().GetScalars())

    def test_screen_selection_helpers_are_constant_size(self) -> None:
        corners = _bounds_corners((-1.0, -2.0, -3.0), (4.0, 5.0, 6.0))

        self.assertEqual(corners.shape, (8, 3))
        self.assertAlmostEqual(
            _point_to_segment_distance((5.0, 5.0), (0.0, 0.0), (10.0, 0.0)),
            5.0,
        )
        self.assertAlmostEqual(
            _point_to_segment_distance((11.0, 0.0), (0.0, 0.0), (10.0, 0.0)),
            1.0,
        )


if __name__ == "__main__":
    unittest.main()
