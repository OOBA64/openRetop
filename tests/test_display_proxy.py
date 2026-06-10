from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mesh.display_proxy import build_display_mesh
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
        self.assertIs(result.source_mesh, mesh)
        self.assertIsNot(result.display_mesh, mesh)

    def test_dense_mesh_uses_sampled_display_proxy(self) -> None:
        triangle_count = 150_001
        vertices = np.column_stack(
            (
                np.arange(triangle_count + 2, dtype=float),
                np.zeros(triangle_count + 2, dtype=float),
                np.zeros(triangle_count + 2, dtype=float),
            )
        )
        triangles = np.column_stack(
            (
                np.arange(triangle_count, dtype=int),
                np.arange(1, triangle_count + 1, dtype=int),
                np.arange(2, triangle_count + 2, dtype=int),
            )
        )
        mesh = TriangleMeshData(vertices=vertices, triangles=triangles)

        result = build_display_mesh(mesh)

        self.assertTrue(result.proxy_enabled)
        self.assertEqual(result.source_triangle_count, triangle_count)
        self.assertLess(result.display_triangle_count, result.source_triangle_count)
        self.assertLessEqual(result.display_triangle_count, 100_000)
        self.assertIs(result.source_mesh, mesh)


if __name__ == "__main__":
    unittest.main()
