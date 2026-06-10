from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mesh.triangle_mesh import TriangleMeshData
from viewer.embedded_viewport import EmbeddedVTKViewport, _line_polydata, _mesh_polydata
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

        polydata = _mesh_polydata(mesh)

        self.assertEqual(polydata.GetNumberOfPoints(), 3)
        self.assertEqual(polydata.GetNumberOfPolys(), 1)

    def test_mesh_actor_is_reused_for_same_display_mesh(self) -> None:
        viewport = EmbeddedVTKViewport(parent=object())
        mesh = self._triangle_mesh()

        first_actor = viewport._ensure_mesh_actor(mesh)
        second_actor = viewport._ensure_mesh_actor(mesh)
        replacement_actor = viewport._ensure_mesh_actor(mesh.copy())

        self.assertIs(first_actor, second_actor)
        self.assertIsNot(first_actor, replacement_actor)

    def test_line_geometry_converts_to_vtk_polydata_with_cell_colors(self) -> None:
        lines = build_bounding_box_outline((0.0, 0.0, 0.0), (1.0, 2.0, 3.0))

        polydata = _line_polydata(lines)

        self.assertEqual(polydata.GetNumberOfPoints(), 8)
        self.assertEqual(polydata.GetNumberOfLines(), 12)
        self.assertIsNotNone(polydata.GetCellData().GetScalars())


if __name__ == "__main__":
    unittest.main()
