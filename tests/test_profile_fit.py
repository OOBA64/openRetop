"""S-13: lines and arcs fitted to a section of the scan (ExModel "fit primitives" on a sketch).

Acceptance: on simulated scans the fitted profile has the true number of lines and arcs, walls
land within scan-noise of their true position, fillets come back at their radius and tangent,
sharp corners the scan rounded come back sharp, and the reported deviation is the real one.
"""

from __future__ import annotations

import math
import unittest

import numpy as np

try:
    import cadquery  # noqa: F401

    HAVE_CADQUERY = True
except ImportError:  # pragma: no cover
    HAVE_CADQUERY = False

from openretop.modeling.profile2d import Segment2D, auto_tolerance, estimate_noise, fit_profile, segment_distances


def _section(part_name: str, origin, normal, columns):
    from openretop.benchmarks import make_part, scan_from_part
    from openretop.geometry.sections import extract_section_by_plane
    from openretop.mesh.triangle_mesh import TriangleMeshData

    scan = scan_from_part(make_part(part_name), noise_sigma=0.02, seed=1, edge_length=0.8)
    mesh = TriangleMeshData(vertices=scan.vertices, triangles=scan.triangles)
    return [poly.points[:, columns] for poly in extract_section_by_plane(mesh, origin, normal).polylines]


def _assert_connected(test: unittest.TestCase, profile) -> None:
    count = len(profile.segments)
    for k in range(count if profile.closed else count - 1):
        np.testing.assert_allclose(profile.segments[k].end, profile.segments[(k + 1) % count].start, atol=1e-9)


@unittest.skipUnless(HAVE_CADQUERY, "CadQuery not installed")
class ScanSectionTests(unittest.TestCase):
    def test_housing_section_gives_four_walls_and_four_tangent_fillets_per_loop(self) -> None:
        loops = _section("housing", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), [0, 1])
        self.assertEqual(len(loops), 2)
        found = {}
        for points in loops:
            profile = fit_profile(points, tolerance=0.08)
            self.assertTrue(profile.closed)
            kinds = [segment.kind for segment in profile.segments]
            self.assertEqual(sorted(kinds), ["arc"] * 4 + ["line"] * 4, kinds)
            self.assertEqual(kinds[::2] if kinds[0] == "line" else kinds[1::2], ["line"] * 4)  # alternating
            _assert_connected(self, profile)
            half_width = max(abs(segment.start[0]) for segment in profile.segments if segment.kind == "line")
            found[round(half_width)] = profile
            self.assertLessEqual(profile.deviation, 0.1)
        outer, pocket = found[30], found[20]
        for profile, (wx, wy), radius in ((outer, (30.0, 20.0), 3.0), (pocket, (20.0, 12.0), 2.0)):
            for segment in profile.segments:
                if segment.kind == "line":
                    direction = segment.end - segment.start
                    if abs(direction[0]) > abs(direction[1]):
                        self.assertEqual(segment.start[1], segment.end[1])  # snapped exactly horizontal
                        self.assertAlmostEqual(abs(segment.start[1]), wy, delta=0.02)
                    else:
                        self.assertEqual(segment.start[0], segment.end[0])
                        self.assertAlmostEqual(abs(segment.start[0]), wx, delta=0.02)
                else:
                    self.assertAlmostEqual(segment.radius, radius, delta=0.1)
            # tangent: each fillet's radius at its ends is perpendicular to the line it meets
            for k, segment in enumerate(profile.segments):
                if segment.kind == "arc":
                    following = profile.segments[(k + 1) % len(profile.segments)]
                    radial = segment.end - segment.center
                    self.assertAlmostEqual(float(radial @ (following.end - following.start)), 0.0, delta=1e-6)

    def test_shaft_profile_comes_back_as_its_sixteen_exact_lines(self) -> None:
        (points,) = _section("shaft", (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), [0, 2])
        profile = fit_profile(points, tolerance=0.08)
        self.assertTrue(profile.closed)
        self.assertEqual([segment.kind for segment in profile.segments], ["line"] * 16)
        _assert_connected(self, profile)
        # every sharp corner of the true profile (both sides of the axis) is a vertex within 0.03
        half = [(10, 0), (10, 13), (8, 13), (8, 17), (10, 17), (10, 40), (6, 50), (6, 70)]
        truth = np.array(half + [(-x, z) for x, z in half], dtype=float)
        vertices = np.array([segment.start for segment in profile.segments])
        nearest = np.min(np.linalg.norm(vertices[:, None, :] - truth[None, :, :], axis=2), axis=0)
        self.assertLess(float(nearest.max()), 0.03, nearest)
        # the deviation reported is the scan's own rounding of those sharp edges, measured
        self.assertAlmostEqual(profile.deviation, float(profile.distances(points).max()), places=9)
        self.assertLess(profile.rms, 0.03)


class SyntheticProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rng = np.random.default_rng(0)

    def noisy(self, points: np.ndarray) -> np.ndarray:
        return points + self.rng.normal(0.0, 0.02, points.shape)

    def test_a_circle_is_one_full_arc(self) -> None:
        t = np.linspace(0.0, 2 * math.pi, 400, endpoint=False)
        profile = fit_profile(self.noisy(np.c_[5 + 7 * np.cos(t), 2 + 7 * np.sin(t)]), tolerance=0.08)
        self.assertEqual([segment.kind for segment in profile.segments], ["arc"])
        circle = profile.segments[0]
        self.assertAlmostEqual(circle.radius, 7.0, delta=0.01)
        np.testing.assert_allclose(circle.center, [5.0, 2.0], atol=0.01)
        self.assertAlmostEqual(circle.length, 2 * math.pi * circle.radius, places=6)

    def rounded_rectangle(self, width: float, height: float, radius: float, count: int = 1200) -> np.ndarray:
        """An outline 2*width x 2*height with corner radius ``radius``, evenly sampled, ccw."""

        straight_x, straight_y = width - radius, height - radius
        pieces = []
        for k, (cx, cy) in enumerate(((straight_x, -straight_y), (straight_x, straight_y), (-straight_x, straight_y), (-straight_x, -straight_y))):
            angle = np.linspace(-math.pi / 2 + k * math.pi / 2, k * math.pi / 2, 40)
            pieces.append(np.c_[cx + radius * np.cos(angle), cy + radius * np.sin(angle)])
        loop = np.vstack(pieces)
        closed = np.vstack([loop, loop[:1]])
        length = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(closed, axis=0), axis=1))]
        at = np.linspace(0.0, length[-1], count, endpoint=False)
        return np.c_[np.interp(at, length, closed[:, 0]), np.interp(at, length, closed[:, 1])]

    def test_a_hole_in_the_scan_across_a_fillet_is_closed_through_it(self) -> None:
        outline = self.noisy(self.rounded_rectangle(30.0, 20.0, 3.0))
        # the scan misses the middle of one fillet (2 of its 4.7): the section stops either side
        corner = np.array([27.0, 17.0]) + 3.0 * np.array([math.cos(math.pi / 4), math.sin(math.pi / 4)])
        missing = np.linalg.norm(outline - corner, axis=1) < 1.0
        start = int(np.nonzero(missing)[0].max()) + 1
        section = np.roll(outline, -start, axis=0)[: int((~missing).sum())]
        profile = fit_profile(section, tolerance=0.08)
        self.assertTrue(profile.closed)
        self.assertGreater(profile.gap, 1.5)
        self.assertEqual(sorted(segment.kind for segment in profile.segments), ["arc"] * 4 + ["line"] * 4)
        _assert_connected(self, profile)
        for segment in profile.segments:
            if segment.kind == "arc":
                self.assertAlmostEqual(segment.radius, 3.0, delta=0.15)  # the half-seen one too

    def test_auto_tolerance_follows_the_noise(self) -> None:
        clean = self.rounded_rectangle(30.0, 20.0, 3.0)
        for sigma in (0.01, 0.03):
            noisy = clean + np.random.default_rng(1).normal(0.0, sigma, clean.shape)
            self.assertAlmostEqual(estimate_noise([noisy]), sigma, delta=0.25 * sigma)
            self.assertGreater(auto_tolerance([noisy]), 4.0 * sigma)
        self.assertEqual(auto_tolerance([clean]), 0.005)  # a perfect outline: the floor

    def test_a_slot_has_tangent_semicircle_ends(self) -> None:
        a = np.linspace(-math.pi / 2, math.pi / 2, 80)
        b = np.linspace(math.pi / 2, 3 * math.pi / 2, 80)
        outline = np.vstack(
            [
                np.c_[np.linspace(0, 20, 100), np.full(100, -4.0)],
                np.c_[20 + 4 * np.cos(a), 4 * np.sin(a)],
                np.c_[np.linspace(20, 0, 100), np.full(100, 4.0)],
                np.c_[4 * np.cos(b), 4 * np.sin(b)],
            ]
        )
        profile = fit_profile(self.noisy(outline), tolerance=0.08)
        self.assertEqual(sorted(segment.kind for segment in profile.segments), ["arc", "arc", "line", "line"])
        _assert_connected(self, profile)
        for segment in profile.segments:
            if segment.kind == "arc":
                self.assertAlmostEqual(segment.radius, 4.0, delta=0.02)
                self.assertAlmostEqual(abs(segment.angles()[1]), math.pi, delta=1e-6)  # a half circle
            else:
                self.assertAlmostEqual(segment.length, 20.0, delta=0.05)

    def test_snapping_takes_a_short_step_but_not_a_long_drafted_wall(self) -> None:
        # a 50 long wall at 2 degrees, then a 2 long step at 3 degrees, back down, along the floor
        tilt, step_tilt = math.radians(2.0), math.radians(3.0)
        corners = [
            np.array([0.0, 0.0]),
            np.array([50 * math.sin(tilt), 50 * math.cos(tilt)]),
        ]
        corners.append(corners[-1] + 2.0 * np.array([math.cos(step_tilt), math.sin(step_tilt)]))
        corners.append(np.array([corners[-1][0], 0.0]))
        outline = np.vstack([np.linspace(corners[k], corners[(k + 1) % 4], 200, endpoint=False) for k in range(4)])
        profile = fit_profile(self.noisy(outline), tolerance=0.08)
        self.assertEqual([segment.kind for segment in profile.segments], ["line"] * 4)
        angles = sorted(
            round(math.degrees(math.atan2(*(segment.end - segment.start)[::-1])) % 180.0, 1) for segment in profile.segments
        )
        self.assertIn(0.0, angles)  # the short step (and the floor) are exactly horizontal
        self.assertIn(90.0, angles)  # the right side
        drafted = [angle for angle in angles if 80.0 < angle < 89.5]
        self.assertEqual(len(drafted), 1)  # the long wall keeps its draft
        self.assertAlmostEqual(drafted[0], 88.0, delta=0.2)

    def test_an_open_curve_stays_open_and_reports_its_true_deviation(self) -> None:
        x = np.linspace(0.0, 30.0, 300)
        points = self.noisy(np.c_[x, 3.0 * np.sin(x / 5.0)])
        profile = fit_profile(points, tolerance=0.08)
        self.assertFalse(profile.closed)
        self.assertGreaterEqual(len(profile.segments), 2)
        _assert_connected(self, profile)
        np.testing.assert_allclose(profile.segments[0].start, points[0], atol=0.1)
        np.testing.assert_allclose(profile.segments[-1].end, points[-1], atol=0.1)
        self.assertAlmostEqual(profile.deviation, float(profile.distances(points).max()), places=9)
        self.assertLess(profile.deviation, 2.0 * 0.08)  # arcs joined end to end on a freeform curve
        self.assertLess(profile.rms, 0.06)

    def test_segment_distances(self) -> None:
        line = Segment2D("line", np.array([0.0, 0.0]), np.array([10.0, 0.0]))
        np.testing.assert_allclose(segment_distances(line, np.array([[5.0, 2.0], [-3.0, 4.0], [12.0, 0.0]])), [2.0, 5.0, 2.0])
        # a quarter arc from (1, 0) to (0, 1) around the origin, counter-clockwise
        arc = Segment2D("arc", np.array([1.0, 0.0]), np.array([0.0, 1.0]), center=np.zeros(2), radius=1.0, ccw=True)
        np.testing.assert_allclose(segment_distances(arc, np.array([[2.0, 2.0], [0.5, 0.0], [-1.0, 0.0]])), [math.sqrt(8) - 1.0, 0.5, math.sqrt(2)])
        clockwise = Segment2D("arc", np.array([1.0, 0.0]), np.array([0.0, 1.0]), center=np.zeros(2), radius=1.0, ccw=False)
        self.assertAlmostEqual(float(segment_distances(clockwise, np.array([[-1.0, 0.0]]))[0]), 0.0)  # the long way round


if __name__ == "__main__":
    unittest.main()
