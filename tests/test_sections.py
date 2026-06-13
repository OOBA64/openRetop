from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from geometry.sections import extract_section


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


if __name__ == "__main__":
    unittest.main()
