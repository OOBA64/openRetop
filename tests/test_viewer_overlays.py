from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from viewer.overlays import build_section_plane_preview, build_world_axes, build_xy_grid


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
