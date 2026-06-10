from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mesh.triangle_mesh import TriangleMeshData
from viewer.embedded_viewport import _line_polydata, _mesh_polydata
from viewer.overlays import build_bounding_box_outline


class EmbeddedViewportSceneTests(unittest.TestCase):
    def test_triangle_mesh_converts_to_vtk_polydata(self) -> None:
        mesh = TriangleMeshData(
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

        polydata = _mesh_polydata(mesh)

        self.assertEqual(polydata.GetNumberOfPoints(), 3)
        self.assertEqual(polydata.GetNumberOfPolys(), 1)

    def test_line_geometry_converts_to_vtk_polydata_with_cell_colors(self) -> None:
        lines = build_bounding_box_outline((0.0, 0.0, 0.0), (1.0, 2.0, 3.0))

        polydata = _line_polydata(lines)

        self.assertEqual(polydata.GetNumberOfPoints(), 8)
        self.assertEqual(polydata.GetNumberOfLines(), 12)
        self.assertIsNotNone(polydata.GetCellData().GetScalars())


if __name__ == "__main__":
    unittest.main()
