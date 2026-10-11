"""Align to World (H-01): square a scan to the world axes from features picked on it.

Design X's plane-line-point (3-2-1) alignment: the first feature (a plane or an axis) is
turned onto a world plane or axis, the second sets the turn about it, the third (a hole's
axis, a ball's centre, a picked point or a third face) the origin. Pure NumPy: the
application moves the scan and everything built on it by the matrix solved here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

PLANE_TARGETS = ("XY", "XZ", "YZ")
AXIS_TARGETS = ("X", "Y", "Z")
TARGET_AXIS = {"XY": 2, "XZ": 1, "YZ": 0, "X": 0, "Y": 1, "Z": 2}  # the world axis a target's normal / direction runs along
PARALLEL_DEGREES = 5.0  # a second feature this close to parallel to the first cannot set the turn
SQUARE_DEGREES = 2.0  # an origin plane this close to square to a world axis sets that coordinate
_E = np.identity(3)


@dataclass(frozen=True)
class AlignFeature:
    """A plane (outward normal), an axis (direction) or a point, in world coordinates."""

    kind: str  # "plane" | "axis" | "point"
    point: np.ndarray
    direction: np.ndarray | None = None
    label: str = ""
    source: str = "scan"  # "scan", "point", or the model entity it was read from
    triangles: np.ndarray | None = field(default=None, compare=False)  # display triangles picked
    rms: float = float("nan")


@dataclass(frozen=True)
class AlignSolution:
    matrix: np.ndarray  # 4 x 4 rigid: current world -> aligned world
    targets: tuple[str, str]  # where rows 1 and 2 went ("" if unused)
    angle: float  # degrees turned
    shift: float  # how far row 1's point moves
    fixed_by: dict[str, int]  # "X" / "Y" / "Z" -> the row (1..3) that set it
    notes: tuple[str, ...] = ()


def _unit(vector: object) -> np.ndarray:
    values = np.asarray(vector, dtype=float).reshape(3)
    length = float(np.linalg.norm(values))
    if length < 1e-12:
        raise ValueError("a direction of zero length")
    return values / length


def feature_from_fit(
    fit: Any, normals: object | None = None, *, source: str = "scan", triangles: np.ndarray | None = None, units: str = "mm"
) -> AlignFeature | None:
    """A feature from a fitted primitive: a plane (its normal turned outward, the way the
    scan's normals point), a cylinder / cone / torus's axis, a sphere's centre."""

    params = getattr(fit, "params", {}) or {}
    kind = getattr(fit, "kind", "")
    rms = float(getattr(fit, "rms", float("nan")))
    if kind == "plane":
        normal = _unit(params["normal"])
        if normals is not None:
            mean = np.asarray(normals, dtype=float).reshape(-1, 3).mean(axis=0)
            if float(mean @ normal) < 0:
                normal = -normal
        return AlignFeature("plane", np.asarray(params["point"], dtype=float).reshape(3), normal, f"Plane (RMS {rms:.3f} {units})", source, triangles, rms)
    if kind in ("cylinder", "cone", "torus"):
        point = params.get("point", params.get("apex", params.get("center")))
        radius = params.get("radius", params.get("major_radius"))
        name = kind.title() + (f" R {float(radius):.2f}" if radius is not None else "")
        return AlignFeature("axis", np.asarray(point, dtype=float).reshape(3), _unit(params["axis"]), name, source, triangles, rms)
    if kind == "sphere":
        return AlignFeature("point", np.asarray(params["center"], dtype=float).reshape(3), None, f"Sphere R {float(params['radius']):.2f}", source, triangles, rms)
    return None


def point_feature(point: object) -> AlignFeature:
    return AlignFeature("point", np.asarray(point, dtype=float).reshape(3), None, "Point", "point")


def _rotation_between(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """The smallest rotation taking unit vector ``a`` to unit vector ``b`` (Rodrigues)."""

    axis = np.cross(a, b)
    sine, cosine = float(np.linalg.norm(axis)), float(a @ b)
    if sine < 1e-12:
        if cosine > 0:
            return np.identity(3)
        # half a turn about any axis square to a
        other = _E[int(np.argmin(np.abs(a)))]
        axis = _unit(np.cross(a, other))
        return 2.0 * np.outer(axis, axis) - np.identity(3)
    axis = axis / sine
    k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.identity(3) + sine * k + (1.0 - cosine) * (k @ k)


def targets_for(kind: str) -> tuple[str, ...]:
    return PLANE_TARGETS if kind == "plane" else AXIS_TARGETS if kind == "axis" else ()


def allowed_second_targets(first_target: str, second_kind: str) -> tuple[str, ...]:
    """The targets row 2 can take: those square to row 1's."""

    return tuple(name for name in targets_for(second_kind) if not first_target or TARGET_AXIS[name] != TARGET_AXIS[first_target])


def default_first_target(feature: AlignFeature) -> str:
    return "XY" if feature.kind == "plane" else "Z"


def solve_alignment(
    features: Sequence[AlignFeature | None], targets: Sequence[str] = ("", "", ""), flips: Sequence[bool] = (False, False, False)
) -> AlignSolution | None:
    """The rigid motion putting row 1 on its target, row 2's direction on its target (the
    turn about row 1), and the origin at row 3 (else rows 1 and 2 where they set it).

    Row 1 is a plane (its outward normal goes to + the target's axis: the clicked face
    becomes the top) or an axis. Row 2 is a plane or an axis not parallel to row 1; only its
    part square to row 1 counts. Row 3 is anything: a point sets X, Y and Z, an axis the
    two coordinates across it, a plane square to a world axis that coordinate."""

    rows = list(features) + [None] * (3 - len(features))
    targets = list(targets) + [""] * (3 - len(targets))
    flips = list(flips) + [False] * (3 - len(flips))
    first, second, third = rows[:3]
    notes: list[str] = []
    if first is None or first.direction is None:  # nothing to turn by: an origin only moves it
        origin = third or first
        return _translation_only(origin, notes) if origin is not None else None
    d1 = _unit(first.direction) * (-1.0 if flips[0] else 1.0)
    t1 = targets[0] or default_first_target(first)
    k1 = TARGET_AXIS[t1]
    sign1 = 1.0 if first.kind == "plane" else (1.0 if float(d1 @ _E[k1]) >= 0 else -1.0)
    e1 = _E[k1] * sign1
    rotation = _rotation_between(d1, e1)
    t2 = ""
    if second is not None and second.direction is not None:
        d2 = _unit(second.direction)
        across = d2 - float(d2 @ d1) * d1
        if float(np.linalg.norm(across)) < math.sin(math.radians(PARALLEL_DEGREES)):
            notes.append("The second pick is parallel to the first, so it cannot set the turn.")
        else:
            angle = math.degrees(math.acos(min(1.0, abs(float(_unit(d2) @ d1)))))
            if abs(90.0 - angle) > 1.0:
                notes.append(f"The second face is {angle:.1f} deg from the first; only its turn about the first counts.")
            across = _unit(across)
            turned = rotation @ across
            choices = [axis for axis in range(3) if axis != k1]
            wanted = [name for name in (targets[1],) if name and TARGET_AXIS[name] in choices]
            k2 = TARGET_AXIS[wanted[0]] if wanted else max(choices, key=lambda axis: abs(float(turned @ _E[axis])))
            t2 = wanted[0] if wanted else _target_name(second.kind, k2)
            sign2 = 1.0 if float(turned @ _E[k2]) >= 0 else -1.0  # the face keeps pointing the way it does
            if flips[1]:
                sign2 = -sign2
            e2 = _E[k2] * sign2
            source = np.column_stack([d1, across, np.cross(d1, across)])
            target = np.column_stack([e1, e2, np.cross(e1, e2)])
            rotation = target @ source.T
    pivot = first.point
    moved = pivot.astype(float).copy()  # where the pivot ends up: it stays put along an axis no row sets
    fixed: dict[str, int] = {}
    for row in (3, 1, 2):
        feature = rows[row - 1]
        if feature is None:
            continue
        for axis in _axes_set_by(feature, rotation, notes if row == 3 else None):
            name = "XYZ"[axis]
            if name in fixed:
                continue
            fixed[name] = row
            moved[axis] = float((rotation @ (pivot - feature.point))[axis])
    matrix = np.identity(4)
    matrix[:3, :3] = rotation
    matrix[:3, 3] = moved - rotation @ pivot
    turn = math.degrees(math.acos(max(-1.0, min(1.0, (float(np.trace(rotation)) - 1.0) / 2.0))))
    shift = float(np.linalg.norm(matrix[:3, :3] @ pivot + matrix[:3, 3] - pivot))
    return AlignSolution(matrix, (t1, t2), turn, shift, fixed, tuple(notes))


def _target_name(kind: str, axis: int) -> str:
    if kind == "plane":
        return {2: "XY", 1: "XZ", 0: "YZ"}[axis]
    return "XYZ"[axis]


def _axes_set_by(feature: AlignFeature, rotation: np.ndarray, notes: list[str] | None) -> list[int]:
    if feature.kind == "point" or feature.direction is None:
        return [0, 1, 2]
    direction = rotation @ _unit(feature.direction)
    if feature.kind == "axis":
        along = int(np.argmax(np.abs(direction)))
        if abs(float(direction[along])) < math.cos(math.radians(SQUARE_DEGREES)):
            if notes is not None:
                notes.append("The origin axis is not square to a world axis: it is not used.")
            return []
        return [axis for axis in range(3) if axis != along]
    along = int(np.argmax(np.abs(direction)))
    if abs(float(direction[along])) < math.cos(math.radians(SQUARE_DEGREES)):
        if notes is not None:
            notes.append("The origin face is not square to a world axis: it is not used.")
        return []
    return [along]


def _translation_only(feature: AlignFeature, notes: list[str]) -> AlignSolution | None:
    axes = _axes_set_by(feature, np.identity(3), notes)
    if not axes:
        return None
    matrix = np.identity(4)
    for axis in axes:
        matrix[axis, 3] = -float(feature.point[axis])
    fixed = {"XYZ"[axis]: 3 for axis in axes}
    return AlignSolution(matrix, ("", ""), 0.0, float(np.linalg.norm(matrix[:3, 3])), fixed, tuple(notes))


def apply_points(matrix: np.ndarray, points: object) -> np.ndarray:
    values = np.asarray(points, dtype=float)
    flat = values.reshape(-1, 3)
    moved = flat @ np.asarray(matrix, dtype=float)[:3, :3].T + np.asarray(matrix, dtype=float)[:3, 3]
    return moved.reshape(values.shape)


def apply_directions(matrix: np.ndarray, directions: object) -> np.ndarray:
    values = np.asarray(directions, dtype=float)
    return (values.reshape(-1, 3) @ np.asarray(matrix, dtype=float)[:3, :3].T).reshape(values.shape)


def moved_frame(frame: dict[str, Any], matrix: np.ndarray) -> dict[str, list[float]]:
    """A sketch frame (origin, u, v) moved with the scan."""

    return {
        **frame,
        "origin": apply_points(matrix, frame["origin"]).reshape(3).tolist(),
        "u": apply_directions(matrix, frame["u"]).reshape(3).tolist(),
        "v": apply_directions(matrix, frame["v"]).reshape(3).tolist(),
    }


WORLD_PLANES = {
    "XY": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    "YZ": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
    "XZ": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
}  # == sketch_mode.PLANES: (u, v, axis)


def world_frame(plane: str, offset: float) -> dict[str, list[float]]:
    u, v, axis = (np.asarray(value, dtype=float) for value in WORLD_PLANES[plane])
    return {"origin": (axis * float(offset)).tolist(), "u": u.tolist(), "v": v.tolist()}


def same_frame(a: dict[str, Any], b: dict[str, Any], tolerance: float = 1e-9) -> bool:
    return all(np.allclose(np.asarray(a[key], dtype=float), np.asarray(b[key], dtype=float), atol=tolerance) for key in ("origin", "u", "v"))


def world_plane_of(frame: dict[str, Any], tolerance: float = 1e-9) -> tuple[str, float] | None:
    """The world plane and offset a frame is, if it is one (after Align it usually is not)."""

    origin = np.asarray(frame["origin"], dtype=float)
    for name, (_u, _v, axis) in WORLD_PLANES.items():
        offset = float(origin @ np.asarray(axis))
        if same_frame(frame, world_frame(name, offset), tolerance):
            return name, offset
    return None


__all__ = (
    "AXIS_TARGETS",
    "PLANE_TARGETS",
    "TARGET_AXIS",
    "AlignFeature",
    "AlignSolution",
    "allowed_second_targets",
    "targets_for",
    "apply_directions",
    "apply_points",
    "default_first_target",
    "feature_from_fit",
    "moved_frame",
    "point_feature",
    "same_frame",
    "solve_alignment",
    "world_frame",
    "world_plane_of",
)
