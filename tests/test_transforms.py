from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from application.transform_math import (
    axis_constrained_camera_move_delta,
    build_object_transform_matrix,
    calculate_geometry_centering_delta,
    calculate_location_for_origin_change,
    calculate_origin_to_world_origin,
    camera_relative_move_delta,
    mesh_move_delta,
    mesh_rotate_delta,
    rotate_vector_around_axis,
    rotation_matrix,
    section_offset_delta,
    transform_bounds,
    transform_point,
    world_axis_vector,
)


class TransformMathTests(unittest.TestCase):
    def test_build_object_transform_matrix_identity_rotation_and_scale(self) -> None:
        matrix = build_object_transform_matrix(
            location=np.asarray([0.0, 0.0, 0.0]),
            rotation=np.asarray([0.0, 0.0, 0.0]),
            scale=1.0,
            origin=np.asarray([0.0, 0.0, 0.0]),
        )

        self.assertTrue(np.allclose(matrix, np.identity(4)))

    def test_build_object_transform_matrix_applies_location_translation(self) -> None:
        matrix = build_object_transform_matrix(
            location=np.asarray([4.0, 5.0, 6.0]),
            rotation=np.asarray([0.0, 0.0, 0.0]),
            scale=1.0,
            origin=np.asarray([0.0, 0.0, 0.0]),
        )

        self.assertTrue(np.allclose(transform_point(matrix, [1.0, 2.0, 3.0]), [5.0, 7.0, 9.0]))

    def test_build_object_transform_matrix_maps_pivot_origin_to_location(self) -> None:
        origin = np.asarray([1.0, 2.0, 3.0])
        location = np.asarray([4.0, 5.0, 6.0])
        matrix = build_object_transform_matrix(
            location=location,
            rotation=np.asarray([0.0, 0.0, 0.0]),
            scale=1.0,
            origin=origin,
        )

        self.assertTrue(np.allclose(transform_point(matrix, origin), location))
        self.assertTrue(np.allclose(transform_point(matrix, [2.0, 2.0, 3.0]), [5.0, 5.0, 6.0]))

    def test_rotation_matrix_rotates_90_degrees_around_x(self) -> None:
        matrix = rotation_matrix(np.asarray([90.0, 0.0, 0.0]))

        self.assertTrue(np.allclose(matrix @ np.asarray([0.0, 1.0, 0.0]), [0.0, 0.0, 1.0]))

    def test_rotation_matrix_rotates_90_degrees_around_y(self) -> None:
        matrix = rotation_matrix(np.asarray([0.0, 90.0, 0.0]))

        self.assertTrue(np.allclose(matrix @ np.asarray([0.0, 0.0, 1.0]), [1.0, 0.0, 0.0]))

    def test_rotation_matrix_rotates_90_degrees_around_z(self) -> None:
        matrix = rotation_matrix(np.asarray([0.0, 0.0, 90.0]))

        self.assertTrue(np.allclose(matrix @ np.asarray([1.0, 0.0, 0.0]), [0.0, 1.0, 0.0]))

    def test_rotate_vector_around_arbitrary_axis(self) -> None:
        rotated = rotate_vector_around_axis(
            np.asarray([0.0, 0.0, 1.0], dtype=float),
            np.asarray([1.0, 0.0, 0.0], dtype=float),
            90.0,
        )

        self.assertTrue(np.allclose(rotated, [0.0, -1.0, 0.0]))

    def test_transform_point_leaves_point_unchanged_with_identity(self) -> None:
        point = np.asarray([1.0, 2.0, 3.0])

        self.assertTrue(np.allclose(transform_point(np.identity(4), point), point))

    def test_transform_point_applies_translation_matrix(self) -> None:
        matrix = np.identity(4)
        matrix[:3, 3] = np.asarray([1.0, 2.0, 3.0])

        self.assertTrue(np.allclose(transform_point(matrix, [4.0, 5.0, 6.0]), [5.0, 7.0, 9.0]))

    def test_transform_bounds_preserves_simple_unit_cube_bounds(self) -> None:
        minimum, maximum = transform_bounds(
            np.asarray([0.0, 0.0, 0.0]),
            np.asarray([1.0, 1.0, 1.0]),
            np.identity(4),
        )

        self.assertTrue(np.allclose(minimum, [0.0, 0.0, 0.0]))
        self.assertTrue(np.allclose(maximum, [1.0, 1.0, 1.0]))

    def test_transform_bounds_applies_translation(self) -> None:
        matrix = np.identity(4)
        matrix[:3, 3] = np.asarray([2.0, -1.0, 3.0])

        minimum, maximum = transform_bounds(
            np.asarray([0.0, 0.0, 0.0]),
            np.asarray([1.0, 1.0, 1.0]),
            matrix,
        )

        self.assertTrue(np.allclose(minimum, [2.0, -1.0, 3.0]))
        self.assertTrue(np.allclose(maximum, [3.0, 0.0, 4.0]))

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

    def test_mesh_move_delta_returns_unconstrained_xy_movement(self) -> None:
        movement, readout = mesh_move_delta(
            mouse_start=(10, 20),
            mouse_position=(30, 5),
            axis_constraint=None,
            model_diagonal=10.0,
            fine=False,
        )

        self.assertTrue(np.allclose(movement, [0.2, 0.15, 0.0]))
        self.assertEqual(readout, "Delta X: 0.20, Delta Y: 0.15")

    def test_mesh_move_delta_constrains_x_axis(self) -> None:
        movement, readout = mesh_move_delta(
            mouse_start=(0, 0),
            mouse_position=(50, 20),
            axis_constraint="X",
            model_diagonal=10.0,
            fine=False,
        )

        self.assertTrue(np.allclose(movement, [0.3, 0.0, 0.0]))
        self.assertEqual(readout, "Delta X: 0.30")

    def test_mesh_move_delta_constrains_y_axis(self) -> None:
        movement, readout = mesh_move_delta(
            mouse_start=(0, 0),
            mouse_position=(50, 20),
            axis_constraint="Y",
            model_diagonal=10.0,
            fine=False,
        )

        self.assertTrue(np.allclose(movement, [0.0, 0.3, 0.0]))
        self.assertEqual(readout, "Delta Y: 0.30")

    def test_mesh_move_delta_constrains_z_axis(self) -> None:
        movement, readout = mesh_move_delta(
            mouse_start=(0, 0),
            mouse_position=(50, 20),
            axis_constraint="Z",
            model_diagonal=10.0,
            fine=False,
        )

        self.assertTrue(np.allclose(movement, [0.0, 0.0, 0.3]))
        self.assertEqual(readout, "Delta Z: 0.30")

    def test_mesh_move_delta_uses_fine_movement_multiplier(self) -> None:
        movement, _readout = mesh_move_delta(
            mouse_start=(0, 0),
            mouse_position=(100, 0),
            axis_constraint="X",
            model_diagonal=10.0,
            fine=True,
        )

        self.assertTrue(np.allclose(movement, [0.1, 0.0, 0.0]))

    def test_camera_relative_move_delta_uses_camera_right_and_up(self) -> None:
        movement, readout = camera_relative_move_delta(
            mouse_start=(0, 0),
            mouse_position=(20, -10),
            camera_right=np.asarray([1.0, 0.0, 0.0]),
            camera_up=np.asarray([0.0, 0.0, 1.0]),
            model_diagonal=10.0,
            fine=False,
        )

        self.assertTrue(np.allclose(movement, [0.2, 0.0, 0.1]))
        self.assertEqual(readout, "Delta X: 0.20, Delta Y: 0.00, Delta Z: 0.10")

    def test_camera_relative_move_delta_normalizes_camera_vectors_and_uses_fine_multiplier(self) -> None:
        movement, _readout = camera_relative_move_delta(
            mouse_start=(0, 0),
            mouse_position=(100, 0),
            camera_right=np.asarray([2.0, 0.0, 0.0]),
            camera_up=np.asarray([0.0, 3.0, 0.0]),
            model_diagonal=10.0,
            fine=True,
        )

        self.assertTrue(np.allclose(movement, [0.1, 0.0, 0.0]))

    def test_axis_constrained_camera_move_delta_projects_axis_to_screen_direction(self) -> None:
        movement, amount = axis_constrained_camera_move_delta(
            mouse_start=(0, 0),
            mouse_position=(100, 0),
            axis_vector=world_axis_vector("X"),
            camera_right=np.asarray([-1.0, 0.0, 0.0]),
            camera_up=np.asarray([0.0, 0.0, 1.0]),
            model_diagonal=10.0,
            fine=False,
        )

        self.assertAlmostEqual(amount, -1.0)
        self.assertTrue(np.allclose(movement, [-1.0, 0.0, 0.0]))

    def test_axis_constrained_camera_move_delta_uses_screen_up_sign(self) -> None:
        movement, amount = axis_constrained_camera_move_delta(
            mouse_start=(0, 0),
            mouse_position=(0, -100),
            axis_vector=world_axis_vector("Z"),
            camera_right=np.asarray([1.0, 0.0, 0.0]),
            camera_up=np.asarray([0.0, 0.0, 1.0]),
            model_diagonal=10.0,
            fine=False,
        )

        self.assertAlmostEqual(amount, 1.0)
        self.assertTrue(np.allclose(movement, [0.0, 0.0, 1.0]))

    def test_mesh_rotate_delta_changes_selected_axis_only(self) -> None:
        rotation, angle_delta = mesh_rotate_delta(
            mouse_start=(0, 0),
            mouse_position=(20, 10),
            rotation=np.asarray([1.0, 2.0, 3.0]),
            axis="Y",
            fine=False,
        )

        self.assertEqual(angle_delta, 10.0)
        self.assertTrue(np.allclose(rotation, [1.0, 12.0, 3.0]))

    def test_mesh_rotate_delta_uses_fine_movement_multiplier(self) -> None:
        rotation, angle_delta = mesh_rotate_delta(
            mouse_start=(0, 0),
            mouse_position=(20, 10),
            rotation=np.asarray([1.0, 2.0, 3.0]),
            axis="Y",
            fine=True,
        )

        self.assertEqual(angle_delta, 1.0)
        self.assertTrue(np.allclose(rotation, [1.0, 3.0, 3.0]))

    def test_section_offset_delta_uses_bounds_extent_for_normal_movement(self) -> None:
        offset_delta = section_offset_delta(
            mouse_start=(0, 0),
            mouse_position=(30, 0),
            offset_bounds=(-5.0, 5.0),
            fine=False,
        )

        self.assertAlmostEqual(offset_delta, 1.0)

    def test_section_offset_delta_uses_fine_movement_multiplier(self) -> None:
        offset_delta = section_offset_delta(
            mouse_start=(0, 0),
            mouse_position=(30, 0),
            offset_bounds=(-5.0, 5.0),
            fine=True,
        )

        self.assertAlmostEqual(offset_delta, 0.1)


if __name__ == "__main__":
    unittest.main()
