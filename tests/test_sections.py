from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from geometry.sections import extract_section, extract_section_by_plane


class SimpleMesh:
    def __init__(self, vertices: list[tuple[float, float, float]], triangles: list[tuple[int, int, int]]) -> None:
        self.vertices = np.asarray(vertices, dtype=float)
        self.triangles = np.asarray(triangles, dtype=int)


def build_cube_mesh() -> SimpleMesh:
    vertices = [
        (-1.0, -1.0, -1.0),
        (1.0, -1.0, -1.0),
        (1.0, 1.0, -1.0),
        (-1.0, 1.0, -1.0),
        (-1.0, -1.0, 1.0),
        (1.0, -1.0, 1.0),
        (1.0, 1.0, 1.0),
        (-1.0, 1.0, 1.0),
    ]
    triangles = [
        (0, 1, 2),
        (0, 2, 3),
        (4, 6, 5),
        (4, 7, 6),
        (0, 4, 5),
        (0, 5, 1),
        (1, 5, 6),
        (1, 6, 2),
        (2, 6, 7),
        (2, 7, 3),
        (3, 7, 4),
        (3, 4, 0),
    ]
    return SimpleMesh(vertices, triangles)


class SectionExtractionTests(unittest.TestCase):
    def test_z_section_extracts_closed_cube_loop(self) -> None:
        result = extract_section(build_cube_mesh(), axis="Z", offset=0.0)

        self.assertEqual(result.axis, "Z")
        self.assertGreaterEqual(result.segment_count, 4)
        self.assertEqual(len(result.polylines), 1)
        self.assertGreaterEqual(result.point_count, 4)
        self.assertTrue(result.polylines[0].is_closed)

    def test_section_outside_mesh_returns_no_polylines(self) -> None:
        result = extract_section(build_cube_mesh(), axis="Z", offset=2.0)

        self.assertEqual(result.segment_count, 0)
        self.assertEqual(result.point_count, 0)
        self.assertEqual(result.polylines, tuple())

    def test_arbitrary_plane_section_uses_origin_and_normal(self) -> None:
        normal = np.asarray([1.0, 1.0, 0.0], dtype=float)
        normal = normal / np.linalg.norm(normal)

        result = extract_section(
            build_cube_mesh(),
            axis="Z",
            offset=0.0,
            origin=[0.0, 0.0, 0.0],
            normal=normal,
        )

        self.assertGreater(result.segment_count, 0)
        for polyline in result.polylines:
            distances = polyline.points @ normal
            self.assertTrue(np.allclose(distances, 0.0, atol=1e-7))

    def test_invalid_axis_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            extract_section(build_cube_mesh(), axis="A", offset=0.0)

    def test_extract_section_by_plane_through_cube_creates_closed_loop(self) -> None:
        result = extract_section_by_plane(
            build_cube_mesh(),
            origin=[0.0, 0.0, 0.0],
            normal=[1.0, 0.0, 0.0],
        )

        self.assertEqual(result.axis, "X")
        self.assertFalse(result.is_arbitrary_plane)
        self.assertGreaterEqual(result.segment_count, 4)
        self.assertEqual(len(result.polylines), 1)
        self.assertTrue(result.polylines[0].is_closed)
        self.assertTrue(np.allclose(result.polylines[0].points[:, 0], 0.0))

    def test_axis_aligned_plane_api_matches_axis_section(self) -> None:
        axis_result = extract_section(build_cube_mesh(), axis="Z", offset=0.0)
        plane_result = extract_section_by_plane(
            build_cube_mesh(),
            origin=[0.0, 0.0, 0.0],
            normal=[0.0, 0.0, 1.0],
        )

        self.assertEqual(plane_result.axis, "Z")
        self.assertEqual(plane_result.segment_count, axis_result.segment_count)
        self.assertEqual(len(plane_result.polylines), len(axis_result.polylines))
        self.assertEqual(plane_result.point_count, axis_result.point_count)
        self.assertFalse(plane_result.is_arbitrary_plane)

    def test_rotated_plane_api_produces_non_empty_arbitrary_result(self) -> None:
        normal = np.asarray([1.0, 0.0, 1.0], dtype=float)
        normal = normal / np.linalg.norm(normal)

        result = extract_section_by_plane(
            build_cube_mesh(),
            origin=[0.0, 0.0, 0.0],
            normal=normal,
        )

        self.assertTrue(result.is_arbitrary_plane)
        self.assertGreater(result.segment_count, 0)
        for polyline in result.polylines:
            distances = polyline.points @ normal
            self.assertTrue(np.allclose(distances, 0.0, atol=1e-7))

    def test_arbitrary_plane_missing_mesh_returns_empty_result(self) -> None:
        result = extract_section_by_plane(
            build_cube_mesh(),
            origin=[0.0, 0.0, 3.0],
            normal=[0.0, 0.0, 1.0],
        )

        self.assertEqual(result.segment_count, 0)
        self.assertEqual(result.polylines, tuple())
        self.assertTrue(np.allclose(result.plane_origin, [0.0, 0.0, 3.0]))
        self.assertTrue(np.allclose(result.plane_normal, [0.0, 0.0, 1.0]))


if __name__ == "__main__":
    unittest.main()
