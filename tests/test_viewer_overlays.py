from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from viewer.overlays import (
    build_active_axis_indicator,
    build_rotation_angle_indicator,
    build_rotation_ring,
    build_section_plane_preview,
    build_world_axes,
    build_xy_grid,
    rotation_ring_radius_for_axis,
)


class ViewerOverlayTests(unittest.TestCase):
    def test_xy_grid_scales_from_bounds_and_crosses_origin(self) -> None:
        grid = build_xy_grid((-2.0, -3.0, -1.0), (2.0, 3.0, 1.0))

        points = np.asarray(grid.points)
        lines = np.asarray(grid.lines)

        self.assertGreater(len(points), 0)
        self.assertGreater(len(lines), 0)
        self.assertTrue(np.any(np.isclose(points[:, 0], 0.0)))
        self.assertTrue(np.any(np.isclose(points[:, 1], 0.0)))
        self.assertTrue(np.allclose(points[:, 2], 0.0))

    def test_world_axes_include_axis_frame_and_origin_marker(self) -> None:
        axes = build_world_axes(4.0)

        self.assertEqual(len(axes.lines), 3)
        self.assertEqual(len(axes.points), 6)
        self.assertTrue(np.allclose(axes.points[0], [0.0, 0.0, 0.0]))

    def test_active_axis_indicator_crosses_pivot_on_selected_axis(self) -> None:
        axis = build_active_axis_indicator((1.0, 2.0, 3.0), "Z", 4.0)

        self.assertEqual(len(axis.lines), 1)
        self.assertTrue(np.allclose(axis.points[:, 0], 1.0))
        self.assertTrue(np.allclose(axis.points[:, 1], 2.0))
        self.assertLess(axis.points[0, 2], 3.0)
        self.assertGreater(axis.points[1, 2], 3.0)

    def test_rotation_ring_aligns_to_active_axis(self) -> None:
        ring = build_rotation_ring((1.0, 2.0, 3.0), "X", 4.0, segments=16)

        self.assertEqual(len(ring.points), 16)
        self.assertEqual(len(ring.lines), 16)
        self.assertTrue(np.allclose(ring.points[:, 0], 1.0))

    def test_rotation_ring_radius_uses_axis_specific_bounds(self) -> None:
        minimum = (0.0, 0.0, 0.0)
        maximum = (2.0, 4.0, 6.0)

        self.assertAlmostEqual(rotation_ring_radius_for_axis(minimum, maximum, "X"), 3.6)
        self.assertAlmostEqual(rotation_ring_radius_for_axis(minimum, maximum, "Y"), 3.6)
        self.assertAlmostEqual(rotation_ring_radius_for_axis(minimum, maximum, "Z"), 2.4)

    def test_rotation_angle_indicator_matches_active_axis_plane(self) -> None:
        indicator = build_rotation_angle_indicator(
            (1.0, 2.0, 3.0),
            "Y",
            2.0,
            45.0,
            segments=8,
        )

        self.assertGreater(len(indicator.lines), 3)
        self.assertTrue(np.allclose(indicator.points[:, 1], 2.0))

    def test_section_plane_preview_uses_selected_axis_and_offset(self) -> None:
        plane = build_section_plane_preview(
            "X",
            0.5,
            (-1.0, -2.0, -3.0),
            (1.0, 2.0, 3.0),
        )

        points = np.asarray(plane.points)

        self.assertGreater(len(points), 0)
        self.assertTrue(np.allclose(points[:, 0], 0.5))


if __name__ == "__main__":
    unittest.main()
