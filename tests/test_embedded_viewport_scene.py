from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

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
            show_normals=False,
            section_result=None,
            curve_results=[],
        )

        self.assertTrue(handled)
        self.assertEqual(render_calls, [True])
        self.assertIs(actor, viewport._mesh_actor)
        self.assertAlmostEqual(actor.GetUserMatrix().GetElement(0, 3), 4.0)

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
