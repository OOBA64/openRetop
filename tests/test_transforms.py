from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.transforms import (
    build_object_transform_matrix,
    calculate_geometry_centering_delta,
    calculate_location_for_origin_change,
    calculate_origin_to_world_origin,
    mesh_move_delta,
    mesh_rotate_delta,
    section_offset_delta,
    transform_bounds,
    transform_point,
)


class TransformMathTests(unittest.TestCase):
    def test_object_transform_maps_origin_to_location(self) -> None:
        origin = np.asarray([1.0, 2.0, 3.0])
        location = np.asarray([4.0, 5.0, 6.0])
        matrix = build_object_transform_matrix(
            location=location,
            rotation=np.asarray([0.0, 0.0, 90.0]),
            scale=2.0,
            origin=origin,
        )

        self.assertTrue(np.allclose(transform_point(matrix, origin), location))

    def test_transform_bounds_uses_all_box_corners(self) -> None:
        matrix = build_object_transform_matrix(
            location=np.asarray([0.0, 0.0, 0.0]),
            rotation=np.asarray([0.0, 0.0, 90.0]),
            scale=1.0,
            origin=np.asarray([0.0, 0.0, 0.0]),
        )

        minimum, maximum = transform_bounds(
            np.asarray([0.0, 0.0, 0.0]),
            np.asarray([1.0, 2.0, 3.0]),
            matrix,
        )

        self.assertTrue(np.allclose(minimum, [-2.0, 0.0, 0.0]))
        self.assertTrue(np.allclose(maximum, [0.0, 1.0, 3.0]))

    def test_origin_to_world_origin_preserves_current_geometry_matrix(self) -> None:
        origin = np.asarray([1.0, 2.0, 3.0])
        location = np.asarray([4.0, 5.0, 6.0])
        rotation = np.asarray([10.0, 20.0, 30.0])
        scale = 1.5
        old_matrix = build_object_transform_matrix(location, rotation, scale, origin)

        new_origin, new_location = calculate_origin_to_world_origin(
            origin,
            location,
            rotation,
            scale,
        )
        new_matrix = build_object_transform_matrix(new_location, rotation, scale, new_origin)

        self.assertTrue(np.allclose(new_location, [0.0, 0.0, 0.0]))
        self.assertTrue(np.allclose(old_matrix, new_matrix))

    def test_origin_change_updates_location_to_keep_geometry_stable(self) -> None:
        old_origin = np.asarray([1.0, 2.0, 3.0])
        new_origin = np.asarray([2.0, 3.0, 4.0])
        location = np.asarray([4.0, 5.0, 6.0])
        rotation = np.asarray([0.0, 0.0, 90.0])
        scale = 2.0
        old_matrix = build_object_transform_matrix(location, rotation, scale, old_origin)

        new_location = calculate_location_for_origin_change(
            location,
            rotation,
            scale,
            old_origin,
            new_origin,
        )
        new_matrix = build_object_transform_matrix(new_location, rotation, scale, new_origin)

        self.assertTrue(np.allclose(old_matrix, new_matrix))

    def test_geometry_centering_delta_moves_raw_center_to_origin(self) -> None:
        delta = calculate_geometry_centering_delta(
            origin=np.asarray([1.0, 2.0, 3.0]),
            raw_center=np.asarray([4.0, 1.0, -1.0]),
        )

        self.assertTrue(np.allclose(delta, [-3.0, 1.0, 4.0]))

    def test_mesh_move_delta_matches_axis_and_fine_multiplier_behavior(self) -> None:
        movement, readout = mesh_move_delta(
            mouse_start=(0, 0),
            mouse_position=(100, 0),
            axis_constraint="X",
            model_diagonal=10.0,
            fine=False,
        )
        fine_movement, _fine_readout = mesh_move_delta(
            mouse_start=(0, 0),
            mouse_position=(100, 0),
            axis_constraint="X",
            model_diagonal=10.0,
            fine=True,
        )

        self.assertTrue(np.allclose(movement, [1.0, 0.0, 0.0]))
        self.assertTrue(np.allclose(fine_movement, [0.1, 0.0, 0.0]))
        self.assertEqual(readout, "Delta X: 1.00")

    def test_mesh_rotate_delta_updates_display_axis(self) -> None:
        rotation, angle_delta = mesh_rotate_delta(
            mouse_start=(0, 0),
            mouse_position=(40, 10),
            rotation=np.asarray([0.0, 0.0, 0.0]),
            axis="Z",
            fine=False,
        )

        self.assertEqual(angle_delta, 20.0)
        self.assertTrue(np.allclose(rotation, [0.0, 0.0, 20.0]))

    def test_section_offset_delta_uses_bounds_extent_and_fine_multiplier(self) -> None:
        offset_delta = section_offset_delta(
            mouse_start=(0, 0),
            mouse_position=(30, 0),
            offset_bounds=(-5.0, 5.0),
            fine=False,
        )
        fine_offset_delta = section_offset_delta(
            mouse_start=(0, 0),
            mouse_position=(30, 0),
            offset_bounds=(-5.0, 5.0),
            fine=True,
        )

        self.assertAlmostEqual(offset_delta, 1.0)
        self.assertAlmostEqual(fine_offset_delta, 0.1)


if __name__ == "__main__":
    unittest.main()
