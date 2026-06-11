from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from geometry.sections import SectionPolyline, SectionResult
from mesh.triangle_mesh import TriangleMeshData
from viewer.embedded_viewport import (
    EmbeddedVTKViewport,
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
            "section_result": None,
            "curve_results": [],
            "reset_camera": False,
        }
        scene_kwargs.update(kwargs)
        viewport.set_scene(mesh, **scene_kwargs)

    def _actor_count(self, viewport: EmbeddedVTKViewport) -> int:
        return int(viewport.renderer.GetActors().GetNumberOfItems())

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
            selected_item="model",
            object_origin=(4.0, 0.0, 0.0),
            active_transform_mode="move",
            active_transform_axis="X",
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
            {"mesh", "grid", "axes", "section_plane"},
        )

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
