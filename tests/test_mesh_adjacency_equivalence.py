from __future__ import annotations

import unittest

import numpy as np
import trimesh
from tests.adjacency_reference import reference_triangle_adjacency

from openretop.mesh.adjacency import build_triangle_adjacency
from openretop.mesh.triangle_mesh import TriangleMeshData


def _mesh(vertices, triangles) -> TriangleMeshData:
    return TriangleMeshData(np.asarray(vertices, float), np.asarray(triangles, int))


class VectorisedAdjacencyTests(unittest.TestCase):
    def test_matches_reference_on_real_meshes(self) -> None:
        for source in (
            trimesh.creation.box(),
            trimesh.creation.icosphere(subdivisions=3),
            trimesh.creation.torus(6.0, 2.0),
        ):
            mesh = _mesh(source.vertices, source.faces)
            self.assertEqual(build_triangle_adjacency(mesh), reference_triangle_adjacency(mesh))

    def test_matches_reference_on_random_soup_with_non_manifold_edges(self) -> None:
        rng = np.random.default_rng(3)
        for _ in range(20):
            vertex_count = int(rng.integers(5, 30))
            triangles = rng.integers(0, vertex_count, size=(int(rng.integers(1, 60)), 3))
            mesh = _mesh(rng.normal(size=(vertex_count, 3)), triangles)  # includes degenerate faces
            # The old implementation listed a degenerate triangle as its own
            # neighbour (it shares an edge with itself); that is dropped now.
            expected = tuple(
                tuple(n for n in neighbours if n != index)
                for index, neighbours in enumerate(reference_triangle_adjacency(mesh))
            )
            self.assertEqual(build_triangle_adjacency(mesh), expected)

    def test_three_triangles_on_one_edge_are_all_neighbours(self) -> None:
        mesh = _mesh(np.zeros((5, 3)), [[0, 1, 2], [0, 1, 3], [0, 1, 4]])
        self.assertEqual(build_triangle_adjacency(mesh), ((1, 2), (0, 2), (0, 1)))

    def test_empty_and_isolated_triangles(self) -> None:
        self.assertEqual(build_triangle_adjacency(_mesh(np.zeros((0, 3)), np.zeros((0, 3)))), ())
        mesh = _mesh(np.zeros((6, 3)), [[0, 1, 2], [3, 4, 5]])
        self.assertEqual(build_triangle_adjacency(mesh), ((), ()))


class WatertightTests(unittest.TestCase):
    def test_closed_meshes_are_watertight_and_open_ones_are_not(self) -> None:
        sphere = trimesh.creation.icosphere(subdivisions=2)
        self.assertTrue(_mesh(sphere.vertices, sphere.faces).is_watertight())
        open_box = _mesh(trimesh.creation.box().vertices, trimesh.creation.box().faces[:-2])
        self.assertFalse(open_box.is_watertight())
        self.assertFalse(_mesh(np.zeros((0, 3)), np.zeros((0, 3))).is_watertight())

    def test_unwelded_triangle_soup_is_not_watertight(self) -> None:
        soup = _mesh(np.arange(36, dtype=float).reshape(12, 3), np.arange(12).reshape(4, 3))
        self.assertFalse(soup.is_watertight())


class VertexNormalTests(unittest.TestCase):
    def test_vertex_normals_are_unit_and_point_outward_on_a_sphere(self) -> None:
        source = trimesh.creation.icosphere(subdivisions=2, radius=3.0)
        mesh = _mesh(source.vertices, source.faces)
        mesh.compute_vertex_normals()
        np.testing.assert_allclose(np.linalg.norm(mesh.vertex_normals, axis=1), 1.0, atol=1e-9)
        radial = mesh.vertices / np.linalg.norm(mesh.vertices, axis=1)[:, None]
        self.assertGreater(float(np.min(np.sum(mesh.vertex_normals * radial, axis=1))), 0.99)


if __name__ == "__main__":
    unittest.main()
