"""RE-03: automatic segmentation of a scan into its faces, scored on the benchmark parts.

Acceptance (RE_PLAN): B1 splits into its true faces with at least 90% of triangles correct,
and every region carries its primitive type and fit.
"""

from __future__ import annotations

import time
import unittest

import numpy as np

try:
    import cadquery  # noqa: F401

    HAVE_CADQUERY = True
except ImportError:  # pragma: no cover
    HAVE_CADQUERY = False

from openretop.segmentation import segment_mesh, triangle_adjacency
from openretop.segmentation.segment import UNASSIGNED


def _score(scan, result) -> tuple[float, dict[int, set[int]]]:
    """Share of triangles in a region whose majority true face is their own, and the regions of each face."""

    correct = 0
    regions_of_face: dict[int, set[int]] = {}
    for segment in result.segments:
        true = scan.face_labels[segment.triangles]
        majority = int(np.bincount(true).argmax())
        correct += int(np.sum(true == majority))
        regions_of_face.setdefault(majority, set()).add(segment.id)
    return correct / len(scan.face_labels), regions_of_face


@unittest.skipUnless(HAVE_CADQUERY, "CadQuery is not installed")
class BenchmarkSegmentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from openretop.benchmarks import make_part, scan_from_part

        cls.results = {}
        for name in ("bracket", "shaft", "housing"):
            part = make_part(name)
            scan = scan_from_part(part, noise_sigma=0.02, seed=1, edge_length=1.5)
            started = time.perf_counter()
            result = segment_mesh(scan.vertices, scan.triangles)
            cls.results[name] = (part, scan, result, time.perf_counter() - started)

    def test_most_triangles_land_in_their_true_face(self) -> None:
        for name, (_part, scan, result, _seconds) in self.results.items():
            with self.subTest(part=name):
                accuracy, _regions = _score(scan, result)
                self.assertGreaterEqual(accuracy, 0.9)
                self.assertGreaterEqual(result.assigned_fraction, 0.95)

    def test_every_true_face_is_found(self) -> None:
        for name, (part, scan, result, _seconds) in self.results.items():
            with self.subTest(part=name):
                _accuracy, regions = _score(scan, result)
                self.assertEqual(set(regions), set(range(len(part.face_types))))

    def test_the_main_faces_get_their_true_primitive(self) -> None:
        kind_of = {"PLANE": "plane", "CYLINDER": "cylinder", "CONE": "cone"}
        for name, (part, scan, result, _seconds) in self.results.items():
            with self.subTest(part=name):
                checked = 0
                for face, geom_type in enumerate(part.face_types):
                    size = int(np.sum(scan.face_labels == face))
                    if size < 400 or geom_type not in kind_of:
                        continue  # small faces (chamfers, groove walls) may be transitions
                    largest = max(result.segments, key=lambda s: int(np.sum(scan.face_labels[s.triangles] == face)))
                    self.assertEqual(largest.kind, kind_of[geom_type], f"face {face}")
                    checked += 1
                self.assertGreater(checked, 2)

    def test_region_fits_reproduce_the_cad(self) -> None:
        part, _scan, result, _seconds = self.results["bracket"]
        # the R4 hole is only ~480 triangles at this spacing and a simulated scan hole may split it
        radii = sorted(round(s.fit.params["radius"], 2) for s in result.segments if s.kind == "cylinder" and s.triangle_count > 200)
        for truth in (4.0, 5.0, 12.0):
            self.assertTrue(any(abs(radius - truth) < 0.02 for radius in radii), (truth, radii))

    def test_the_noise_level_is_measured_from_the_scan(self) -> None:
        for name, (_part, _scan, result, _seconds) in self.results.items():
            with self.subTest(part=name):
                self.assertAlmostEqual(result.noise_sigma, 0.02, delta=0.004)

    def test_segmentation_is_quick(self) -> None:
        for name, (_part, scan, _result, seconds) in self.results.items():
            with self.subTest(part=name):
                self.assertLess(seconds, max(10.0, scan.triangle_count / 2000.0))


class TopologyTests(unittest.TestCase):
    def test_triangle_adjacency_on_a_tetrahedron(self) -> None:
        triangles = np.array([[0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0]])
        offsets, neighbours = triangle_adjacency(triangles, 4)
        for triangle in range(4):
            found = set(neighbours[offsets[triangle] : offsets[triangle + 1]].tolist())
            self.assertEqual(found, set(range(4)) - {triangle})

    def test_a_flat_square_is_one_plane(self) -> None:
        x, y = np.meshgrid(np.linspace(0, 40, 41), np.linspace(0, 40, 41))
        vertices = np.c_[x.ravel(), y.ravel(), np.random.default_rng(0).normal(0, 0.01, x.size)]
        index = np.arange(41 * 41).reshape(41, 41)
        a, b, c, d = index[:-1, :-1].ravel(), index[:-1, 1:].ravel(), index[1:, :-1].ravel(), index[1:, 1:].ravel()
        triangles = np.r_[np.c_[a, b, d], np.c_[a, d, c]]
        result = segment_mesh(vertices, triangles)
        self.assertEqual([segment.kind for segment in result.segments], ["plane"])
        self.assertEqual(int(np.sum(result.labels == UNASSIGNED)), 0)

    def test_empty_and_tiny_meshes_do_not_crash(self) -> None:
        result = segment_mesh(np.zeros((3, 3)), np.array([[0, 1, 2]]))
        self.assertEqual(len(result.labels), 1)


if __name__ == "__main__":
    unittest.main()
