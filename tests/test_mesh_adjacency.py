from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mesh.adjacency import (
    build_triangle_adjacency,
    cached_triangle_adjacency,
    grow_connected_region,
)
from mesh.triangle_mesh import TriangleMeshData
from regions.region_state import (
    DEFAULT_REGION_MAX_TRIANGLES,
    DEFAULT_REGION_THRESHOLD_DEGREES,
    RegionCollection,
    create_region_selection,
)


def _quad_mesh() -> TriangleMeshData:
    return TriangleMeshData(
        vertices=np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
                [0.0, 1.0, 0.0],
            ],
            dtype=float,
        ),
        triangles=np.asarray(
            [
                [0, 1, 2],
                [0, 2, 3],
            ],
            dtype=int,
        ),
    )


def _coplanar_strip_mesh() -> TriangleMeshData:
    return TriangleMeshData(
        vertices=np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [2.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [1.0, 1.0, 0.0],
                [2.0, 1.0, 0.0],
            ],
            dtype=float,
        ),
        triangles=np.asarray(
            [
                [0, 1, 4],
                [0, 4, 3],
                [1, 2, 5],
                [1, 5, 4],
            ],
            dtype=int,
        ),
    )


def _sharp_boundary_mesh() -> TriangleMeshData:
    return TriangleMeshData(
        vertices=np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=float,
        ),
        triangles=np.asarray(
            [
                [0, 1, 2],
                [0, 2, 3],
            ],
            dtype=int,
        ),
    )


def _cube_mesh() -> TriangleMeshData:
    return TriangleMeshData(
        vertices=np.asarray(
            [
                [-1.0, -1.0, -1.0],
                [1.0, -1.0, -1.0],
                [1.0, 1.0, -1.0],
                [-1.0, 1.0, -1.0],
                [-1.0, -1.0, 1.0],
                [1.0, -1.0, 1.0],
                [1.0, 1.0, 1.0],
                [-1.0, 1.0, 1.0],
            ],
            dtype=float,
        ),
        triangles=np.asarray(
            [
                [0, 2, 1],
                [0, 3, 2],
                [4, 5, 6],
                [4, 6, 7],
                [0, 1, 5],
                [0, 5, 4],
                [1, 2, 6],
                [1, 6, 5],
                [2, 3, 7],
                [2, 7, 6],
                [3, 0, 4],
                [3, 4, 7],
            ],
            dtype=int,
        ),
    )


class MeshAdjacencyTests(unittest.TestCase):
    def test_triangle_adjacency_on_simple_quad_mesh(self) -> None:
        adjacency = build_triangle_adjacency(_quad_mesh())

        self.assertEqual(adjacency, ((1,), (0,)))

    def test_cached_triangle_adjacency_reuses_same_mesh_identity_and_counts(self) -> None:
        mesh = _quad_mesh()
        first = cached_triangle_adjacency(mesh)
        second = cached_triangle_adjacency(mesh)

        self.assertIs(first, second)

    def test_triangle_adjacency_on_cube_mesh(self) -> None:
        adjacency = build_triangle_adjacency(_cube_mesh())

        self.assertEqual(len(adjacency), 12)
        self.assertTrue(all(len(neighbors) == 3 for neighbors in adjacency))

    def test_region_grow_selects_connected_coplanar_faces(self) -> None:
        result = grow_connected_region(_coplanar_strip_mesh(), 0)

        self.assertEqual(set(result.triangle_indices), {0, 1, 2, 3})
        self.assertEqual(result.threshold_degrees, DEFAULT_REGION_THRESHOLD_DEGREES)
        self.assertEqual(result.max_triangle_count, DEFAULT_REGION_MAX_TRIANGLES)

    def test_sharp_normal_boundary_stops_growth(self) -> None:
        result = grow_connected_region(_sharp_boundary_mesh(), 0, threshold_degrees=20.0)

        self.assertEqual(result.triangle_indices, (0,))

    def test_threshold_affects_region_size(self) -> None:
        mesh = _sharp_boundary_mesh()
        narrow = grow_connected_region(mesh, 0, threshold_degrees=20.0)
        wide = grow_connected_region(mesh, 0, threshold_degrees=95.0)

        self.assertEqual(narrow.triangle_indices, (0,))
        self.assertEqual(set(wide.triangle_indices), {0, 1})

    def test_max_triangle_cap_is_respected(self) -> None:
        result = grow_connected_region(
            _coplanar_strip_mesh(),
            0,
            threshold_degrees=20.0,
            max_triangle_count=2,
        )

        self.assertLessEqual(len(result.triangle_indices), 2)
        self.assertIn(0, result.triangle_indices)

    def test_empty_mesh_returns_no_region(self) -> None:
        mesh = TriangleMeshData(
            vertices=np.zeros((0, 3), dtype=float),
            triangles=np.zeros((0, 3), dtype=int),
        )

        result = grow_connected_region(mesh, 0)
        region = create_region_selection(mesh, 0)

        self.assertEqual(result.triangle_indices, tuple())
        self.assertIsNone(region)

    def test_invalid_seed_returns_empty_region(self) -> None:
        result = grow_connected_region(_quad_mesh(), 99)
        region = create_region_selection(_quad_mesh(), -1)

        self.assertEqual(result.triangle_indices, tuple())
        self.assertIsNone(region)

    def test_region_selection_does_not_alter_mesh_geometry(self) -> None:
        mesh = _coplanar_strip_mesh()
        vertices_before = mesh.vertices.copy()
        triangles_before = mesh.triangles.copy()

        region = create_region_selection(
            mesh,
            0,
            source_mesh_identifier="sample.stl",
            source_mesh_name="sample.stl",
        )

        self.assertIsNotNone(region)
        self.assertEqual(region.metadata["seed_triangle_index"], 0)
        self.assertEqual(region.metadata["triangle_count"], len(region.triangle_indices))
        self.assertEqual(region.source_mesh_identifier, "sample.stl")
        self.assertEqual(region.source_mesh_name, "sample.stl")
        np.testing.assert_allclose(mesh.vertices, vertices_before)
        np.testing.assert_array_equal(mesh.triangles, triangles_before)

    def test_region_collection_stores_one_active_region(self) -> None:
        region = create_region_selection(_quad_mesh(), 0)
        collection = RegionCollection()

        collection.set_active(region)
        self.assertIs(collection.active_region, region)
        collection.set_visible(False)
        self.assertFalse(collection.active_region.visible)
        collection.clear()
        self.assertIsNone(collection.active_region)


if __name__ == "__main__":
    unittest.main()
