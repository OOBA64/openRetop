"""Pure transform math helpers for object and viewport interaction state."""

from __future__ import annotations

from math import cos, radians, sin

import numpy as np


MOVE_SENSITIVITY = 0.001
ROTATION_SENSITIVITY = 0.5
FINE_TRANSFORM_MULTIPLIER = 0.1

_AXIS_TO_INDEX = {"X": 0, "Y": 1, "Z": 2}


def build_object_transform_matrix(
    location: np.ndarray,
    rotation: np.ndarray,
    scale: float,
    origin: np.ndarray,
) -> np.ndarray:
    matrix = np.identity(4)
    matrix[:3, :3] = rotation_matrix(rotation) * float(scale)
    matrix[:3, 3] = np.asarray(location, dtype=float) - matrix[:3, :3] @ np.asarray(origin, dtype=float)
    return matrix


def rotation_matrix(rotation: np.ndarray) -> np.ndarray:
    rx, ry, rz = rotation
    return _rotation_z(rz) @ _rotation_y(ry) @ _rotation_x(rx)


def rotate_vector_around_axis(
    vector: np.ndarray,
    axis_vector: np.ndarray,
    angle_degrees: float,
) -> np.ndarray:
    values = np.asarray(vector, dtype=float)
    axis = normalized_vector(axis_vector, fallback=np.asarray([0.0, 0.0, 1.0], dtype=float))
    angle = radians(float(angle_degrees))
    cosine = cos(angle)
    sine = sin(angle)
    return (
        values * cosine
        + np.cross(axis, values) * sine
        + axis * float(np.dot(axis, values)) * (1.0 - cosine)
    )


def transform_point(matrix: np.ndarray, point: np.ndarray) -> np.ndarray:
    homogeneous = np.append(np.asarray(point, dtype=float), 1.0)
    return (np.asarray(matrix, dtype=float) @ homogeneous)[:3]


def transform_bounds(
    minimum: np.ndarray,
    maximum: np.ndarray,
    matrix: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    minimum = np.asarray(minimum, dtype=float)
    maximum = np.asarray(maximum, dtype=float)
    corners = np.asarray(
        [
            [minimum[0], minimum[1], minimum[2]],
            [maximum[0], minimum[1], minimum[2]],
            [maximum[0], maximum[1], minimum[2]],
            [minimum[0], maximum[1], minimum[2]],
            [minimum[0], minimum[1], maximum[2]],
            [maximum[0], minimum[1], maximum[2]],
            [maximum[0], maximum[1], maximum[2]],
            [minimum[0], maximum[1], maximum[2]],
        ],
        dtype=float,
    )
    homogeneous = np.column_stack((corners, np.ones(len(corners))))
    transformed = (np.asarray(matrix, dtype=float) @ homogeneous.T).T[:, :3]
    return (np.min(transformed, axis=0), np.max(transformed, axis=0))


def calculate_origin_to_world_origin(
    origin: np.ndarray,
    location: np.ndarray,
    rotation: np.ndarray,
    scale: float,
    world_origin: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    target_location = (
        np.asarray([0.0, 0.0, 0.0], dtype=float)
        if world_origin is None
        else np.asarray(world_origin, dtype=float)
    )
    rotation_scale = rotation_matrix(rotation) * float(scale)
    new_origin = np.asarray(origin, dtype=float) + np.linalg.inv(rotation_scale) @ (
        target_location - np.asarray(location, dtype=float)
    )
    return (new_origin, target_location)


def calculate_location_for_origin_change(
    location: np.ndarray,
    rotation: np.ndarray,
    scale: float,
    old_origin: np.ndarray,
    new_origin: np.ndarray,
) -> np.ndarray:
    rotation_scale = rotation_matrix(rotation) * float(scale)
    return np.asarray(location, dtype=float) + rotation_scale @ (
        np.asarray(new_origin, dtype=float) - np.asarray(old_origin, dtype=float)
    )


def calculate_geometry_centering_delta(origin: np.ndarray, raw_center: np.ndarray) -> np.ndarray:
    return np.asarray(origin, dtype=float) - np.asarray(raw_center, dtype=float)


def mesh_move_delta(
    mouse_start: tuple[int, int],
    mouse_position: tuple[int, int],
    axis_constraint: str | None,
    model_diagonal: float,
    *,
    fine: bool,
) -> tuple[np.ndarray, str]:
    delta = mouse_delta(mouse_start, mouse_position)
    scale = movement_scale(model_diagonal, fine=fine)
    drag_amount = (delta[0] - delta[1]) * scale
    if axis_constraint == "X":
        movement = np.asarray([drag_amount, 0.0, 0.0], dtype=float)
        readout = f"Delta X: {movement[0]:.2f}"
    elif axis_constraint == "Y":
        movement = np.asarray([0.0, drag_amount, 0.0], dtype=float)
        readout = f"Delta Y: {movement[1]:.2f}"
    elif axis_constraint == "Z":
        movement = np.asarray([0.0, 0.0, drag_amount], dtype=float)
        readout = f"Delta Z: {movement[2]:.2f}"
    else:
        movement = np.asarray([delta[0] * scale, -delta[1] * scale, 0.0], dtype=float)
        readout = f"Delta X: {movement[0]:.2f}, Delta Y: {movement[1]:.2f}"

    return (movement, readout)


def camera_relative_move_delta(
    mouse_start: tuple[int, int],
    mouse_position: tuple[int, int],
    camera_right: np.ndarray,
    camera_up: np.ndarray,
    model_diagonal: float,
    *,
    fine: bool,
) -> tuple[np.ndarray, str]:
    delta = mouse_delta(mouse_start, mouse_position)
    scale = movement_scale(model_diagonal, fine=fine)
    right = normalized_vector(camera_right, fallback=np.asarray([1.0, 0.0, 0.0], dtype=float))
    up = normalized_vector(camera_up, fallback=np.asarray([0.0, 1.0, 0.0], dtype=float))
    movement = (right * delta[0] + up * -delta[1]) * scale
    return (movement, movement_readout(movement))


def axis_constrained_camera_move_delta(
    mouse_start: tuple[int, int],
    mouse_position: tuple[int, int],
    axis_vector: np.ndarray,
    camera_right: np.ndarray,
    camera_up: np.ndarray,
    model_diagonal: float,
    *,
    fine: bool,
) -> tuple[np.ndarray, float]:
    delta = mouse_delta(mouse_start, mouse_position)
    scale = movement_scale(model_diagonal, fine=fine)
    axis = normalized_vector(axis_vector, fallback=np.asarray([1.0, 0.0, 0.0], dtype=float))
    right = normalized_vector(camera_right, fallback=np.asarray([1.0, 0.0, 0.0], dtype=float))
    up = normalized_vector(camera_up, fallback=np.asarray([0.0, 1.0, 0.0], dtype=float))
    screen_axis = np.asarray(
        [
            float(np.dot(axis, right)),
            -float(np.dot(axis, up)),
        ],
        dtype=float,
    )
    screen_length = float(np.linalg.norm(screen_axis))
    if screen_length <= 1e-9:
        pixel_amount = delta[0] - delta[1]
    else:
        pixel_amount = float(np.dot(np.asarray(delta, dtype=float), screen_axis / screen_length))

    amount = pixel_amount * scale
    return (axis * amount, amount)


def world_axis_vector(axis: str) -> np.ndarray:
    vector = np.zeros(3, dtype=float)
    vector[_AXIS_TO_INDEX[axis]] = 1.0
    return vector


def movement_readout(movement: np.ndarray) -> str:
    values = np.asarray(movement, dtype=float)
    return f"Delta X: {values[0]:.2f}, Delta Y: {values[1]:.2f}, Delta Z: {values[2]:.2f}"


def mesh_rotate_delta(
    mouse_start: tuple[int, int],
    mouse_position: tuple[int, int],
    rotation: np.ndarray,
    axis: str,
    *,
    fine: bool,
) -> tuple[np.ndarray, float]:
    delta = mouse_delta(mouse_start, mouse_position)
    angle_delta = delta[0] * ROTATION_SENSITIVITY * fine_multiplier(fine)
    next_rotation = np.asarray(rotation, dtype=float).copy()
    next_rotation[_AXIS_TO_INDEX[axis]] += angle_delta
    return (next_rotation, angle_delta)


def section_offset_delta(
    mouse_start: tuple[int, int],
    mouse_position: tuple[int, int],
    offset_bounds: tuple[float, float],
    *,
    fine: bool,
) -> float:
    delta = mouse_delta(mouse_start, mouse_position)
    minimum, maximum = offset_bounds
    offset_scale = (max(abs(maximum - minimum), 1.0) / 300.0) * fine_multiplier(fine)
    return (delta[0] - delta[1]) * offset_scale


def movement_scale(model_diagonal: float, *, fine: bool) -> float:
    return max(float(model_diagonal), 1.0) * MOVE_SENSITIVITY * fine_multiplier(fine)


def fine_multiplier(fine: bool) -> float:
    return FINE_TRANSFORM_MULTIPLIER if fine else 1.0


def normalized_vector(vector: np.ndarray, *, fallback: np.ndarray) -> np.ndarray:
    values = np.asarray(vector, dtype=float)
    length = float(np.linalg.norm(values))
    if length <= 1e-12:
        return np.asarray(fallback, dtype=float).copy()
    return values / length


def mouse_delta(
    mouse_start: tuple[int, int],
    mouse_position: tuple[int, int],
) -> tuple[float, float]:
    return (
        float(mouse_position[0] - mouse_start[0]),
        float(mouse_position[1] - mouse_start[1]),
    )


def _rotation_x(angle_degrees: float) -> np.ndarray:
    angle = radians(float(angle_degrees))
    c = cos(angle)
    s = sin(angle)
    return np.asarray(
        [
            [1.0, 0.0, 0.0],
            [0.0, c, -s],
            [0.0, s, c],
        ],
        dtype=float,
    )


def _rotation_y(angle_degrees: float) -> np.ndarray:
    angle = radians(float(angle_degrees))
    c = cos(angle)
    s = sin(angle)
    return np.asarray(
        [
            [c, 0.0, s],
            [0.0, 1.0, 0.0],
            [-s, 0.0, c],
        ],
        dtype=float,
    )


def _rotation_z(angle_degrees: float) -> np.ndarray:
    angle = radians(float(angle_degrees))
    c = cos(angle)
    s = sin(angle)
    return np.asarray(
        [
            [c, -s, 0.0],
            [s, c, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=float,
    )
