from __future__ import annotations

import unittest
from types import SimpleNamespace

import numpy as np
import trimesh
from tests.section_reference import _intersect_triangle_plane

from openretop.geometry.sections import (
    _plane_segments,
    extract_section,
    extract_section_by_plane,
)


def _reference_segments(vertices, triangles, origin, normal, tolerance) -> np.ndarray:
    segments = []
    for triangle in triangles:
        segment = _intersect_triangle_plane(
            vertices[triangle], plane_origin=origin, plane_normal=normal, tolerance=tolerance
        )
        if segment is not None:
            segments.append(segment)
    return np.asarray(segments).reshape((-1, 2, 3))


def _canonical(segments: np.ndarray, decimals: int = 9) -> list[tuple]:
    """Order-independent form: each segment's endpoints sorted, segments sorted."""

    rounded = np.round(segments, decimals) + 0.0
    pairs = []
    for first, second in rounded:
        a, b = tuple(first), tuple(second)
        pairs.append((a, b) if a <= b else (b, a))
    return sorted(pairs)


class VectorisedSectionTests(unittest.TestCase):
    meshes = {
        "box": trimesh.creation.box(extents=(2.0, 3.0, 4.0)),
        "sphere": trimesh.creation.icosphere(subdivisions=3, radius=5.0),
        "torus": trimesh.creation.torus(major_radius=6.0, minor_radius=2.0),
        "cylinder": trimesh.creation.cylinder(radius=3.0, height=8.0, sections=24),
    }

    def test_matches_the_per_triangle_reference_on_varied_planes(self) -> None:
        rng = np.random.default_rng(7)
        for name, mesh in self.meshes.items():
            vertices = np.asarray(mesh.vertices, dtype=float)
            triangles = np.asarray(mesh.faces, dtype=int)
            tolerance = 1e-9 * max(float(np.ptp(vertices, axis=0).max()), 1.0)
            planes = [
                (np.array([0.0, 0.0, offset]), np.array([0.0, 0.0, 1.0]))
                for offset in (-1.7, 0.0, 0.5, float(vertices[:, 2].max()))  # through vertices/faces
            ]
            for _ in range(6):
                normal = rng.normal(size=3)
                planes.append((rng.normal(size=3), normal / np.linalg.norm(normal)))
            for origin, normal in planes:
                expected = _reference_segments(vertices, triangles, origin, normal, tolerance)
                actual = _plane_segments(
                    vertices, triangles, plane_origin=origin, plane_normal=normal, tolerance=tolerance
                )
                self.assertEqual(
                    _canonical(actual), _canonical(expected), f"{name}: origin={origin} normal={normal}"
                )

    def test_plane_that_misses_the_mesh_gives_no_segments(self) -> None:
        mesh = self.meshes["box"]
        result = extract_section(SimpleNamespace(vertices=mesh.vertices, triangles=mesh.faces), axis="Z", offset=100.0)
        self.assertEqual(result.segment_count, 0)
        self.assertEqual(result.polylines, ())

    def test_cylinder_section_is_one_closed_ring_of_the_right_size(self) -> None:
        mesh = self.meshes["cylinder"]
        result = extract_section(SimpleNamespace(vertices=mesh.vertices, triangles=mesh.faces), axis="Z", offset=0.3)
        self.assertEqual(len(result.polylines), 1)
        ring = result.polylines[0]
        self.assertTrue(ring.is_closed)
        radii = np.linalg.norm(ring.points[:, :2], axis=1)
        self.assertGreater(radii.min(), 3.0 * np.cos(np.pi / 24) - 1e-6)
        self.assertLess(radii.max(), 3.0 + 1e-6)

    def test_oblique_plane_through_sphere_gives_a_circle(self) -> None:
        mesh = self.meshes["sphere"]
        normal = np.array([1.0, 1.0, 0.0]) / np.sqrt(2.0)
        result = extract_section_by_plane(
            SimpleNamespace(vertices=mesh.vertices, triangles=mesh.faces), np.zeros(3), normal
        )
        self.assertEqual(len(result.polylines), 1)
        radii = np.linalg.norm(result.polylines[0].points, axis=1)
        self.assertAlmostEqual(float(radii.mean()), 5.0, delta=0.15)

    def test_large_mesh_section_runs_without_a_python_loop_over_triangles(self) -> None:
        # ~82k triangles; the old loop needed ~1 s here. Checked for correctness
        # rather than speed so it is not flaky on slow machines.
        mesh = trimesh.creation.icosphere(subdivisions=6, radius=10.0)
        result = extract_section(SimpleNamespace(vertices=mesh.vertices, triangles=mesh.faces), axis="X", offset=0.0)
        self.assertEqual(len(result.polylines), 1)
        self.assertTrue(result.polylines[0].is_closed)
        self.assertGreater(result.segment_count, 400)


if __name__ == "__main__":
    unittest.main()
