from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np
from tests.mesh_query_reference import (
    ReferenceMeshSpatialIndex,
    reference_query_closest_points,
)

from openretop.mesh.query_service import MeshQueryService
from openretop.mesh.spatial_index import MeshSpatialIndex, vtk_available
from openretop.mesh.triangle_mesh import TriangleMeshData


def _query_mesh() -> TriangleMeshData:
    return TriangleMeshData(
        vertices=np.asarray(
            [
                [0.0, 0.0, 0.0],
                [2.0, 0.0, 0.0],
                [0.0, 2.0, 0.0],
                [5.0, 0.0, 0.0],
                [7.0, 0.0, 0.0],
                [5.0, 2.0, 0.0],
            ],
            dtype=float,
        ),
        triangles=np.asarray(
            [
                [0, 1, 2],
                [0, 0, 0],
                [0, 1, 99],
                [3, 4, 5],
            ],
            dtype=int,
        ),
    )


class MeshSpatialIndexInputTests(unittest.TestCase):
    def test_empty_and_invalid_meshes_fail_safely_without_building_vtk(self) -> None:
        empty = TriangleMeshData(
            vertices=np.zeros((0, 3), dtype=float),
            triangles=np.zeros((0, 3), dtype=int),
        )
        invalid = TriangleMeshData(
            vertices=np.asarray([[0.0, 0.0, 0.0]], dtype=float),
            triangles=np.asarray([[0, 0, 0], [0, 1, 2]], dtype=int),
        )

        for mesh in (empty, invalid):
            index = MeshSpatialIndex.from_mesh(mesh)
            result = index.query_closest_points([[1.0, 2.0, 3.0]])
            self.assertFalse(index.valid)
            self.assertEqual(result.hit_count, 0)
            self.assertEqual(result.missed_count, 1)
            self.assertTrue(np.all(np.isfinite(result.closest_points)))
            self.assertEqual(result.metadata["reason"], "no_valid_triangles")

    def test_empty_point_batch_has_stable_array_shapes(self) -> None:
        index = MeshSpatialIndex.from_mesh(
            TriangleMeshData(
                vertices=np.zeros((0, 3), dtype=float),
                triangles=np.zeros((0, 3), dtype=int),
            )
        )

        result = index.query_closest_points(np.zeros((0, 3), dtype=float))

        self.assertEqual(result.source_points.shape, (0, 3))
        self.assertEqual(result.closest_points.shape, (0, 3))
        self.assertEqual(result.normals.shape, (0, 3))
        self.assertEqual(result.triangle_indices.dtype, np.int64)


@unittest.skipUnless(vtk_available(), "VTK is unavailable in this local runtime")
class MeshSpatialIndexVtkTests(unittest.TestCase):
    def test_accelerated_results_match_reference_for_interior_edge_vertex_and_island(self) -> None:
        mesh = _query_mesh()
        points = np.asarray(
            [
                [0.5, 0.5, 1.0],
                [1.5, 1.5, 0.2],
                [-1.0, -1.0, 0.3],
                [5.25, 0.25, -0.4],
            ],
            dtype=float,
        )
        reference = reference_query_closest_points(mesh, points)

        index = MeshSpatialIndex.from_mesh(mesh)
        accelerated = index.query_closest_points(points)

        np.testing.assert_allclose(accelerated.closest_points, reference.closest_points, atol=1e-9)
        np.testing.assert_allclose(accelerated.distances, reference.distances, atol=1e-9)
        np.testing.assert_allclose(accelerated.normals, reference.normals, atol=1e-9)
        np.testing.assert_array_equal(accelerated.hit_mask, reference.hit_mask)
        np.testing.assert_array_equal(accelerated.triangle_indices, reference.triangle_indices)
        self.assertEqual(accelerated.triangle_indices.tolist(), [0, 0, 0, 3])
        np.testing.assert_allclose(
            accelerated.normals,
            np.tile(np.asarray([[0.0, 0.0, 1.0]]), (4, 1)),
        )
        self.assertEqual(accelerated.metadata["invalid_triangle_count"], 2)

    def test_duplicate_nonfinite_and_max_distance_queries_are_safe(self) -> None:
        mesh = _query_mesh()
        points = np.asarray(
            [[0.25, 0.25, 0.1], [0.25, 0.25, 0.1], [np.nan, 0.0, 0.0]],
            dtype=float,
        )

        result = MeshSpatialIndex.from_mesh(mesh).query_closest_points(
            points,
            max_distance=0.05,
            preserve_missed_points=False,
        )

        self.assertEqual(result.hit_mask.tolist(), [False, False, False])
        self.assertEqual(result.metadata["invalid_query_indices"], [2])
        self.assertEqual(result.metadata["threshold_rejected_indices"], [0, 1])
        self.assertTrue(np.all(np.isfinite(result.source_points)))
        self.assertTrue(np.all(np.isfinite(result.closest_points)))
        self.assertTrue(np.allclose(result.closest_points, 0.0))


class _FakeIndex(ReferenceMeshSpatialIndex):
    def __init__(self, mesh: TriangleMeshData, source_signature: object) -> None:
        super().__init__(mesh)
        self.source_signature = source_signature


class MeshQueryServiceTests(unittest.TestCase):
    def test_cache_builds_once_reuses_explicit_revision_and_invalidates(self) -> None:
        service = MeshQueryService()
        mesh = _query_mesh()

        with patch(
            "openretop.mesh.query_service.MeshSpatialIndex.from_mesh",
            side_effect=lambda candidate, source_signature=None: _FakeIndex(
                candidate, source_signature
            ),
        ) as build_index:
            service.query_closest_points(mesh, [[0.2, 0.2, 1.0]], mesh_revision=7)
            service.query_closest_points(mesh.copy(), [[0.3, 0.2, 1.0]], mesh_revision=7)
            self.assertEqual(build_index.call_count, 1)
            self.assertTrue(service.diagnostics["cache_hit"])

            # Display-only settings never touch the service or its revision token.
            display_color = "#FF00FF"
            self.assertEqual(display_color, "#FF00FF")
            service.query_closest_points(mesh, [[0.4, 0.2, 1.0]], mesh_revision=7)
            self.assertEqual(build_index.call_count, 1)

            service.query_closest_points(mesh, [[0.4, 0.2, 1.0]], mesh_revision=8)
            self.assertEqual(build_index.call_count, 2)

            service.invalidate()
            service.query_closest_points(mesh, [[0.2, 0.2, 1.0]], mesh_revision=7)
            self.assertEqual(build_index.call_count, 3)

        self.assertEqual(service.diagnostics["index_build_count"], 3)

    def test_mesh_replacement_changes_identity_cache_key(self) -> None:
        service = MeshQueryService()
        first = _query_mesh()
        second = _query_mesh().copy()

        with patch(
            "openretop.mesh.query_service.MeshSpatialIndex.from_mesh",
            side_effect=lambda candidate, source_signature=None: _FakeIndex(
                candidate, source_signature
            ),
        ) as build_index:
            service.get_index(first)
            service.get_index(second)

        self.assertEqual(build_index.call_count, 2)


if __name__ == "__main__":
    unittest.main()
