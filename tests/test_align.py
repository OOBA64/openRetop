"""H-01 Align to World: the plane-line-point solution (no kernel, no Qt)."""

from __future__ import annotations

import math
import unittest

import numpy as np

from openretop.application.transform_math import rotation_angles, rotation_matrix
from openretop.modeling.alignment import (
    AlignFeature,
    allowed_second_targets,
    apply_points,
    feature_from_fit,
    moved_frame,
    point_feature,
    solve_alignment,
    world_frame,
    world_plane_of,
)


def _tilt() -> np.ndarray:
    matrix = np.identity(4)
    matrix[:3, :3] = rotation_matrix(np.array([17.0, -23.0, 31.0]))
    matrix[:3, 3] = (12.0, -40.0, 7.5)
    return matrix


def _features(tilt: np.ndarray) -> tuple[AlignFeature, AlignFeature, AlignFeature]:
    """The bracket's top face (z = 5, out +Z), its front side (y = -25, out -Y) and the boss
    hole's axis (through (20, 0), along Z), tilted."""

    turn = tilt[:3, :3]
    top = AlignFeature("plane", apply_points(tilt, (3.0, 4.0, 5.0)), turn @ np.array([0.0, 0.0, 1.0]))
    side = AlignFeature("plane", apply_points(tilt, (-7.0, -25.0, 1.0)), turn @ np.array([0.0, -1.0, 0.0]))
    hole = AlignFeature("axis", apply_points(tilt, (20.0, 0.0, -3.0)), turn @ np.array([0.0, 0.0, 1.0]))
    return top, side, hole


class SolveTests(unittest.TestCase):
    def test_plane_plane_axis_squares_the_part_and_puts_the_origin_on_the_hole(self) -> None:
        tilt = _tilt()
        solution = solve_alignment(_features(tilt))
        assert solution is not None
        net = solution.matrix @ tilt  # the part's own frame -> aligned world
        np.testing.assert_allclose(net[:3, :3], np.identity(3), atol=1e-9)
        # origin: X, Y on the hole's axis (row 3), Z on the top face (row 1)
        np.testing.assert_allclose(net[:3, 3], (-20.0, 0.0, -5.0), atol=1e-9)
        self.assertEqual(solution.fixed_by, {"X": 3, "Y": 3, "Z": 1})
        self.assertEqual(solution.targets, ("XY", "XZ"))
        self.assertAlmostEqual(np.linalg.det(solution.matrix[:3, :3]), 1.0, places=12)

    def test_three_planes_put_the_origin_at_their_corner(self) -> None:
        tilt = _tilt()
        top, side, _hole = _features(tilt)
        end = AlignFeature("plane", apply_points(tilt, (40.0, 3.0, 0.0)), tilt[:3, :3] @ np.array([1.0, 0.0, 0.0]))
        solution = solve_alignment((top, side, end))
        assert solution is not None
        corner = apply_points(solution.matrix @ tilt, (40.0, -25.0, 5.0))
        np.testing.assert_allclose(corner, 0.0, atol=1e-9)

    def test_flip_turns_the_first_face_down(self) -> None:
        tilt = _tilt()
        top, side, hole = _features(tilt)
        solution = solve_alignment((top, side, hole), flips=(True, False, False))
        assert solution is not None
        normal = (solution.matrix @ tilt)[:3, :3] @ np.array([0.0, 0.0, 1.0])
        np.testing.assert_allclose(normal, (0.0, 0.0, -1.0), atol=1e-9)
        self.assertAlmostEqual(np.linalg.det(solution.matrix[:3, :3]), 1.0, places=12)

    def test_flip_on_the_second_row_turns_half_round(self) -> None:
        tilt = _tilt()
        top, side, hole = _features(tilt)
        solution = solve_alignment((top, side, hole), flips=(False, True, False))
        assert solution is not None
        side_normal = (solution.matrix @ tilt)[:3, :3] @ np.array([0.0, -1.0, 0.0])
        np.testing.assert_allclose(side_normal, (0.0, 1.0, 0.0), atol=1e-9)

    def test_a_chosen_target_for_each_row(self) -> None:
        tilt = _tilt()
        top, side, hole = _features(tilt)
        solution = solve_alignment((top, side, hole), targets=("XZ", "XY", ""))
        assert solution is not None
        net = (solution.matrix @ tilt)[:3, :3]
        np.testing.assert_allclose(net @ np.array([0.0, 0.0, 1.0]), (0.0, 1.0, 0.0), atol=1e-9)  # top -> +Y (XZ plane)
        self.assertEqual(abs(float((net @ np.array([0.0, -1.0, 0.0]))[2])), 1.0)  # side on XY
        self.assertEqual(allowed_second_targets("XZ", "plane"), ("XY", "YZ"))
        self.assertEqual(allowed_second_targets("XY", "axis"), ("X", "Y"))

    def test_a_parallel_second_pick_is_noted_and_only_turns_the_first(self) -> None:
        tilt = _tilt()
        top, _side, hole = _features(tilt)
        solution = solve_alignment((top, hole, None))
        assert solution is not None
        self.assertTrue(any("parallel" in note for note in solution.notes))
        np.testing.assert_allclose((solution.matrix @ tilt)[:3, :3] @ np.array([0.0, 0.0, 1.0]), (0.0, 0.0, 1.0), atol=1e-9)

    def test_a_shaft_axis_alone(self) -> None:
        tilt = _tilt()
        _top, _side, hole = _features(tilt)
        solution = solve_alignment((hole, None, None))
        assert solution is not None
        net = solution.matrix @ tilt
        np.testing.assert_allclose(net[:3, :3] @ np.array([0.0, 0.0, 1.0]), (0.0, 0.0, 1.0), atol=1e-9)
        # an axis on Z sets X and Y: the hole's axis is the Z axis
        np.testing.assert_allclose(apply_points(net, (20.0, 0.0, 11.0))[:2], 0.0, atol=1e-9)

    def test_a_point_alone_moves_without_turning(self) -> None:
        solution = solve_alignment((None, None, point_feature((3.0, -2.0, 9.0))))
        assert solution is not None
        np.testing.assert_allclose(solution.matrix[:3, :3], np.identity(3))
        np.testing.assert_allclose(apply_points(solution.matrix, (3.0, -2.0, 9.0)), 0.0, atol=1e-12)
        self.assertIsNone(solve_alignment((None, None, None)))

    def test_an_oblique_origin_face_is_not_used(self) -> None:
        tilt = _tilt()
        top, side, _hole = _features(tilt)
        oblique = AlignFeature("plane", apply_points(tilt, (0.0, 0.0, 0.0)), tilt[:3, :3] @ np.array([1.0, 1.0, 0.0]) / math.sqrt(2))
        solution = solve_alignment((top, side, oblique))
        assert solution is not None
        self.assertTrue(any("not square" in note for note in solution.notes))
        self.assertNotIn(3, solution.fixed_by.values())

    def test_the_rotation_is_always_proper(self) -> None:
        rng = np.random.default_rng(5)
        for _ in range(200):
            tilt = np.identity(4)
            tilt[:3, :3] = rotation_matrix(rng.uniform(-180, 180, 3))
            tilt[:3, 3] = rng.uniform(-50, 50, 3)
            flips = tuple(bool(value) for value in rng.integers(0, 2, 3))
            solution = solve_alignment(_features(tilt), flips=flips)
            assert solution is not None
            self.assertAlmostEqual(float(np.linalg.det(solution.matrix[:3, :3])), 1.0, places=9)


class FeatureTests(unittest.TestCase):
    def test_a_fitted_plane_points_out_of_the_part(self) -> None:
        from openretop.fitting import PrimitiveFit

        fit = PrimitiveFit("plane", True, {"normal": np.array([0.0, 0.0, -1.0]), "point": np.zeros(3)}, rms=0.02)
        feature = feature_from_fit(fit, np.tile([0.0, 0.1, 0.99], (10, 1)))
        assert feature is not None
        np.testing.assert_allclose(feature.direction, (0.0, 0.0, 1.0))
        cylinder = feature_from_fit(PrimitiveFit("cylinder", True, {"axis": np.array([0.0, 2.0, 0.0]), "point": np.ones(3), "radius": 5.0}))
        assert cylinder is not None
        self.assertEqual((cylinder.kind, cylinder.label), ("axis", "Cylinder R 5.00"))
        np.testing.assert_allclose(cylinder.direction, (0.0, 1.0, 0.0))
        sphere = feature_from_fit(PrimitiveFit("sphere", True, {"center": np.array([1.0, 2.0, 3.0]), "radius": 4.0}))
        assert sphere is not None
        self.assertEqual(sphere.kind, "point")


class FrameAndAngleTests(unittest.TestCase):
    def test_rotation_angles_round_trip(self) -> None:
        rng = np.random.default_rng(1)
        for angles in [*rng.uniform(-180, 180, (2000, 3)), (10.0, 90.0, 20.0), (10.0, -90.0, 20.0)]:
            matrix = rotation_matrix(np.asarray(angles))
            np.testing.assert_allclose(rotation_matrix(rotation_angles(matrix)), matrix, atol=1e-9)

    def test_a_world_frame_moved_and_recognised(self) -> None:
        frame = world_frame("XY", 5.0)
        self.assertEqual(world_plane_of(frame), ("XY", 5.0))
        shift = np.identity(4)
        shift[:3, 3] = (0.0, 0.0, 2.0)
        self.assertEqual(world_plane_of(moved_frame(frame, shift)), ("XY", 7.0))
        self.assertIsNone(world_plane_of(moved_frame(frame, _tilt())))


if __name__ == "__main__":
    unittest.main()
