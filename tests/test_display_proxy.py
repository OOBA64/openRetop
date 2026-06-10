from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mesh.display_proxy import PROXY_QUALITY_LOW, build_display_mesh
from mesh.triangle_mesh import TriangleMeshData


class DisplayProxyTests(unittest.TestCase):
    def test_low_density_mesh_uses_full_display_copy(self) -> None:
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

        result = build_display_mesh(mesh)

        self.assertFalse(result.proxy_enabled)
        self.assertEqual(result.source_triangle_count, 1)
        self.assertEqual(result.display_triangle_count, 1)
        self.assertEqual(result.reduction_percent, 0.0)
        self.assertIs(result.source_mesh, mesh)
        self.assertIsNot(result.display_mesh, mesh)
        self.assertTrue(result.display_mesh.has_vertex_normals())
        self.assertTrue(result.display_mesh.has_triangle_normals())

    def test_dense_mesh_uses_decimated_display_proxy_without_mutating_source(self) -> None:
        mesh = self._grid_mesh(302)
        source_vertices = mesh.vertices.copy()
        source_triangles = mesh.triangles.copy()
        triangle_count = len(mesh.triangles)

        result = build_display_mesh(mesh, quality=PROXY_QUALITY_LOW)

        self.assertTrue(result.proxy_enabled)
        self.assertEqual(result.source_triangle_count, triangle_count)
        self.assertLess(result.display_triangle_count, result.source_triangle_count)
        self.assertGreater(result.display_triangle_count, 0)
        self.assertGreater(result.reduction_percent, 0.0)
        self.assertIs(result.source_mesh, mesh)
        self.assertTrue(result.display_mesh.has_vertex_normals())
        self.assertTrue(result.display_mesh.has_triangle_normals())
        self.assertTrue(np.array_equal(mesh.vertices, source_vertices))
        self.assertTrue(np.array_equal(mesh.triangles, source_triangles))

    def _grid_mesh(self, size: int) -> TriangleMeshData:
        xs, ys = np.meshgrid(
            np.arange(size, dtype=float),
            np.arange(size, dtype=float),
            indexing="xy",
        )
        vertices = np.column_stack(
            (
                xs.ravel(),
                ys.ravel(),
                np.sin(xs.ravel() * 0.04) * np.cos(ys.ravel() * 0.04),
            )
        )
        cells: list[tuple[int, int, int]] = []
        for y_index in range(size - 1):
            row = y_index * size
            next_row = (y_index + 1) * size
            for x_index in range(size - 1):
                lower_left = row + x_index
                lower_right = lower_left + 1
                upper_left = next_row + x_index
                upper_right = upper_left + 1
                cells.append((lower_left, lower_right, upper_right))
                cells.append((lower_left, upper_right, upper_left))
        triangles = np.asarray(cells, dtype=int)
        return TriangleMeshData(vertices=vertices, triangles=triangles)


if __name__ == "__main__":
    unittest.main()
