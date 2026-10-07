"""Align section curves with each other so a loft between them does not twist."""

from __future__ import annotations

import numpy as np


def polygon_normal(points: np.ndarray) -> np.ndarray:
    """Newell normal of a closed ring (its length is twice the area)."""

    ring = np.asarray(points, dtype=float).reshape((-1, 3))
    if len(ring) < 3:
        return np.zeros(3)
    following = np.roll(ring, -1, axis=0)
    return np.array(
        [
            np.sum((ring[:, 1] - following[:, 1]) * (ring[:, 2] + following[:, 2])),
            np.sum((ring[:, 2] - following[:, 2]) * (ring[:, 0] + following[:, 0])),
            np.sum((ring[:, 0] - following[:, 0]) * (ring[:, 1] + following[:, 1])),
        ]
    )


def align_open_points(points: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """Reverse ``points`` if that brings its ends closer to ``reference``'s ends."""

    points = np.asarray(points, dtype=float).reshape((-1, 3))
    reference = np.asarray(reference, dtype=float).reshape((-1, 3))
    if len(points) < 2 or len(reference) < 2:
        return points
    direct = np.linalg.norm(reference[0] - points[0]) + np.linalg.norm(reference[-1] - points[-1])
    flipped = np.linalg.norm(reference[0] - points[-1]) + np.linalg.norm(reference[-1] - points[0])
    return points[::-1].copy() if flipped < direct else points


def align_closed_points(points: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """Re-orient and re-seam a closed ring to match ``reference``.

    Both rings may or may not repeat their first point at the end; the result
    always repeats it. The ring is reversed when its winding about the
    reference's normal is opposite, then rolled so it starts at the vertex
    nearest the reference's start.
    """

    ring = _unique_ring(points)
    reference_ring = _unique_ring(reference)
    if len(ring) < 3 or len(reference_ring) < 3:
        return np.asarray(points, dtype=float).reshape((-1, 3))

    if float(np.dot(polygon_normal(ring), polygon_normal(reference_ring))) < 0.0:
        ring = ring[::-1]
    start = int(np.argmin(np.linalg.norm(ring - reference_ring[0], axis=1)))
    ring = np.roll(ring, -start, axis=0)
    return np.vstack([ring, ring[:1]])


def _unique_ring(points: np.ndarray) -> np.ndarray:
    ring = np.asarray(points, dtype=float).reshape((-1, 3))
    if len(ring) >= 2 and np.linalg.norm(ring[0] - ring[-1]) <= 1e-12:
        ring = ring[:-1]
    return ring
