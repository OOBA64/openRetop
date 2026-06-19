from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mesh.triangle_mesh import TriangleMeshData
from regions.boundary import extract_region_boundary_polylines
from regions.region_state import RegionSelection


def _region(*triangle_indices: int) -> RegionSelection:
    return RegionSelection(
        id="region-1",
        name="Region 1",
        triangle_indices=tuple(triangle_indices),
        threshold_degrees=20.0,
        max_triangle_count=50_000,
        source_mesh_identifier="sample.stl",
        source_mesh_name="sample.stl",
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
        triangles=np.asarray([[0, 1, 2], [0, 2, 3]], dtype=int),
    )


def _disconnected_triangles_mesh() -> TriangleMeshData:
    return TriangleMeshData(
        vertices=np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [3.0, 0.0, 0.0],
                [4.0, 0.0, 0.0],
                [3.0, 1.0, 0.0],
            ],
            dtype=float,
        ),
        triangles=np.asarray([[0, 1, 2], [3, 4, 5]], dtype=int),
    )


def _ring_mesh() -> TriangleMeshData:
    return TriangleMeshData(
        vertices=np.asarray(
            [
                [0.0, 0.0, 0.0],
                [3.0, 0.0, 0.0],
                [3.0, 3.0, 0.0],
                [0.0, 3.0, 0.0],
                [1.0, 1.0, 0.0],
                [2.0, 1.0, 0.0],
                [2.0, 2.0, 0.0],
                [1.0, 2.0, 0.0],
            ],
            dtype=float,
        ),
        triangles=np.asarray(
            [
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


def _non_manifold_boundary_mesh() -> TriangleMeshData:
    return TriangleMeshData(
        vertices=np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [2.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
                [1.0, -1.0, 0.0],
            ],
            dtype=float,
        ),
        triangles=np.asarray([[0, 1, 3], [1, 2, 3], [0, 1, 4]], dtype=int),
    )


class RegionBoundaryTests(unittest.TestCase):
    def test_single_triangle_extracts_one_closed_boundary(self) -> None:
        polylines = extract_region_boundary_polylines(_quad_mesh(), _region(0))

        self.assertEqual(len(polylines), 1)
        self.assertTrue(polylines[0].is_closed)
        self.assertEqual(polylines[0].points.shape, (3, 3))
        self.assertEqual(polylines[0].metadata["boundary_point_count"], 3)
        self.assertTrue(polylines[0].metadata["boundary_closed"])
        self.assertGreater(polylines[0].metadata["boundary_perimeter"], 0.0)

    def test_quad_region_extracts_one_closed_boundary_loop(self) -> None:
        polylines = extract_region_boundary_polylines(_quad_mesh(), _region(0, 1))

        self.assertEqual(len(polylines), 1)
        boundary = polylines[0]
        self.assertTrue(boundary.is_closed)
        self.assertEqual(boundary.points.shape, (4, 3))
        self.assertEqual(boundary.source_region_id, "region-1")
        self.assertEqual(boundary.source_mesh_name, "sample.stl")
        self.assertEqual(boundary.metadata["region_triangle_count"], 2)
        self.assertEqual(boundary.metadata["source_region_triangle_count"], 2)
        self.assertFalse(np.allclose(boundary.points[0], boundary.points[-1]))

    def test_adjacent_triangles_omit_internal_edge(self) -> None:
        polylines = extract_region_boundary_polylines(_quad_mesh(), _region(0, 1))

        self.assertEqual(len(polylines), 1)
        self.assertEqual(len(polylines[0].points), 4)

    def test_region_with_hole_extracts_inner_and_outer_loops(self) -> None:
        polylines = extract_region_boundary_polylines(_ring_mesh(), _region(*range(8)))

        self.assertEqual(len(polylines), 2)
        self.assertTrue(all(polyline.is_closed for polyline in polylines))
        self.assertEqual(sorted(len(polyline.points) for polyline in polylines), [4, 4])

    def test_invalid_indices_are_ignored_safely(self) -> None:
        polylines = extract_region_boundary_polylines(_quad_mesh(), _region(-1, 99, 0))

        self.assertEqual(len(polylines), 1)
        self.assertTrue(polylines[0].is_closed)
        self.assertEqual(polylines[0].points.shape, (3, 3))

    def test_empty_region_returns_no_boundaries(self) -> None:
        self.assertEqual(extract_region_boundary_polylines(_quad_mesh(), _region()), [])

    def test_disconnected_region_returns_multiple_polylines(self) -> None:
        polylines = extract_region_boundary_polylines(
            _disconnected_triangles_mesh(),
            _region(0, 1),
        )

        self.assertEqual(len(polylines), 2)
        self.assertTrue(all(polyline.is_closed for polyline in polylines))
        self.assertEqual(sorted(len(polyline.points) for polyline in polylines), [3, 3])

    def test_extracted_boundary_point_order_is_continuous(self) -> None:
        boundary = extract_region_boundary_polylines(_quad_mesh(), _region(0, 1))[0]
        distances = np.linalg.norm(
            np.diff(np.vstack((boundary.points, boundary.points[0])), axis=0),
            axis=1,
        )

        self.assertTrue(np.all(distances > 0.0))
        self.assertLessEqual(np.max(distances), np.sqrt(2.0))

    def test_non_manifold_boundary_does_not_crash(self) -> None:
        polylines = extract_region_boundary_polylines(
            _non_manifold_boundary_mesh(),
            _region(0, 1, 2),
        )

        self.assertTrue(polylines)
        self.assertTrue(all(len(polyline.points) >= 2 for polyline in polylines))


if __name__ == "__main__":
    unittest.main()
