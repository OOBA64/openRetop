"""Helpers that turn a benchmark scan into the inputs the tools see, and score their output."""

from __future__ import annotations

import math

import numpy as np

from openretop.benchmarks.parts import ScanMesh


def vertex_normals(vertices: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    """Area-weighted vertex normals, as the app computes them for a loaded scan."""

    corners = vertices[triangles]
    face_normals = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    flat = triangles.ravel()
    repeated = np.repeat(face_normals, 3, axis=0)
    normals = np.column_stack([np.bincount(flat, weights=repeated[:, axis], minlength=len(vertices)) for axis in range(3)])
    return normals / np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)


def face_points(scan: ScanMesh, face_index: int, *, shrink: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """Points and normals of one true face, without the vertices it shares with neighbours.

    ``shrink`` rings of vertices next to other faces are dropped: a user's region (or the
    segmentation) stops a little short of an edge too, and the normals there are blended.
    """

    cached = scan.metadata.get("vertex_normals")
    if isinstance(cached, np.ndarray):
        normals = cached
    else:
        normals = vertex_normals(scan.vertices, scan.triangles)
        scan.metadata["vertex_normals"] = normals
    inside = scan.face_labels == face_index
    vertex_faces_other = np.zeros(len(scan.vertices), dtype=bool)
    vertex_faces_other[np.unique(scan.triangles[~inside])] = True
    keep = np.zeros(len(scan.vertices), dtype=bool)
    keep[np.unique(scan.triangles[inside])] = True
    blocked = vertex_faces_other.copy()
    for _ring in range(max(shrink, 0)):
        touching = np.any(blocked[scan.triangles], axis=1)
        blocked[np.unique(scan.triangles[touching])] = True
    keep &= ~blocked
    return scan.vertices[keep], normals[keep]


def axis_angle_degrees(first: object, second: object) -> float:
    a = np.asarray(first, dtype=float) / np.linalg.norm(first)
    b = np.asarray(second, dtype=float) / np.linalg.norm(second)
    return math.degrees(math.acos(min(1.0, abs(float(a @ b)))))


def axis_offset(point: object, axis: object, true_point: object, true_axis: object) -> float:
    """Distance between two (nearly parallel) axes, measured at the true axis point."""

    axis_unit = np.asarray(axis, dtype=float) / np.linalg.norm(axis)
    offset = np.asarray(true_point, dtype=float) - np.asarray(point, dtype=float)
    return float(np.linalg.norm(offset - axis_unit * (offset @ axis_unit)))


__all__ = ("axis_angle_degrees", "axis_offset", "face_points", "vertex_normals")
