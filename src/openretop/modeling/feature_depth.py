"""How far a sketch's walls run in the scan (S-14 "auto depth" for Extrude).

For each closed loop of a profile: the scan's wall along the loop is the points close to the
loop (seen along the plane's normal) whose normals lie in the plane. Going away from the
sketch plane, the wall continues while at least half the loop still has wall at that height;
where it stops, the cap (the flat face that closes it: inside an outer loop, outside a hole)
gives the exact height, since the scan rounds the edge there and the wall alone stops short.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

COVERAGE = 0.5  # share of the loop that must still have wall
BINS_ALONG = 64  # the loop is cut into this many stretches for the coverage count


@dataclass(frozen=True)
class LoopDepth:
    low: float  # along the plane's normal, the sketch plane at 0
    high: float
    depth: int  # nesting: 0 outer, 1 a hole, ...
    found: bool  # False: no wall in the scan along this loop


def loop_depths(
    points: np.ndarray,
    normals: np.ndarray | None,
    frame: dict[str, Any],
    loops: list[dict[str, Any]],
    *,
    band: float,
    step: float,
) -> list[LoopDepth]:
    """The extent of each loop's wall (``band``: how near the loop a wall point lies;
    ``step``: the scan's point spacing; a wall goes on across gaps up to 3x that)."""

    from scipy.spatial import cKDTree

    origin = np.asarray(frame["origin"], dtype=float)
    u, v = np.asarray(frame["u"], dtype=float), np.asarray(frame["v"], dtype=float)
    normal = np.cross(u, v)
    normal /= np.linalg.norm(normal)
    local = np.asarray(points, dtype=float) - origin
    flat = np.c_[local @ u, local @ v]
    height = local @ normal
    facing = None if normals is None else np.abs(np.asarray(normals, dtype=float) @ normal)
    walls = np.ones(len(flat), dtype=bool) if facing is None else facing < 0.5
    caps = np.zeros(len(flat), dtype=bool) if facing is None else facing > 0.85
    spacing = min(step, band) / 2.0  # outline samples close enough that the band is a band
    outlines = [_dense(np.asarray(loop.get("outline", ()), dtype=float).reshape(-1, 2), spacing) for loop in loops]
    closed = [index for index, loop in enumerate(loops) if loop.get("closed", False) and len(outlines[index]) >= 3]
    results: list[LoopDepth] = []
    for index, outline in enumerate(outlines):
        if index not in closed:
            results.append(LoopDepth(0.0, 0.0, 0, False))
            continue
        depth = sum(_inside(outline[len(outline) // 2], outlines[other]) for other in closed if other != index)
        tree = cKDTree(outline)
        distance, nearest = tree.query(flat, distance_upper_bound=max(3.0 * band, 4.0 * step))
        near = np.isfinite(distance)
        on_wall = near & walls & (distance <= band)
        stretch = (nearest[on_wall] * BINS_ALONG) // len(outline)
        low, high, found = _walk(height[on_wall], stretch, 3.0 * step)
        if not found:
            results.append(LoopDepth(0.0, 0.0, depth, False))
            continue
        # the cap at each end: the flat scan beside the wall's end (inside an outer loop at
        # its top, inside a pocket at its floor, around it at its top: only a real end has one)
        cap_heights = height[near & caps]
        low = _cap(cap_heights, low, 2.0 * step + band)
        high = _cap(cap_heights, high, 2.0 * step + band)
        results.append(LoopDepth(low, high, depth, True))
    # a hole cannot run past the body around it
    for index, result in enumerate(results):
        if result.found and result.depth % 2:
            around = [other for other in results if other.found and other.depth == result.depth - 1]
            if around:
                low = max(result.low, min(item.low for item in around))
                high = min(result.high, max(item.high for item in around))
                results[index] = LoopDepth(low, high, result.depth, True)
    return results


def _walk(heights: np.ndarray, stretch: np.ndarray, gap: float) -> tuple[float, float, bool]:
    """Each stretch of the loop: its wall followed from the plane (0) up and down while the
    points are no further apart than ``gap``. The loop's ends: the median of the stretches'
    ends, so the wall goes on while half the loop still has it (low, high, found)."""

    lows, highs = [], []
    for value in range(BINS_ALONG):
        column = np.sort(heights[stretch == value])
        if len(column) == 0:
            continue
        start = int(np.argmin(np.abs(column)))
        if abs(column[start]) > gap:
            continue  # this stretch has no wall at the plane
        top = start
        while top + 1 < len(column) and column[top + 1] - column[top] <= gap:
            top += 1
        bottom = start
        while bottom > 0 and column[bottom] - column[bottom - 1] <= gap:
            bottom -= 1
        lows.append(column[bottom])
        highs.append(column[top])
    if len(lows) < COVERAGE * BINS_ALONG:
        return 0.0, 0.0, False
    return float(np.median(lows)), float(np.median(highs)), True


def _cap(heights: np.ndarray, end: float, reach: float) -> float:
    """The flat scan's height near a wall's end, if there is one (else the end itself)."""

    close = heights[np.abs(heights - end) <= reach]
    return float(np.median(close)) if len(close) >= 5 else end


def _dense(outline: np.ndarray, step: float) -> np.ndarray:
    if len(outline) < 2:
        return outline
    closed = np.vstack([outline, outline[:1]])
    length = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(closed, axis=0), axis=1))]
    count = max(int(length[-1] / max(step, 1e-9)), 16)
    at = np.linspace(0.0, length[-1], count, endpoint=False)
    return np.c_[np.interp(at, length, closed[:, 0]), np.interp(at, length, closed[:, 1])]


def _inside(point: np.ndarray, outline: np.ndarray) -> bool:
    x, y = float(point[0]), float(point[1])
    ax, ay = outline[:, 0], outline[:, 1]
    bx, by = np.roll(ax, -1), np.roll(ay, -1)
    crossing = (ay > y) != (by > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        at = ax + (y - ay) * (bx - ax) / (by - ay)
    return bool(np.count_nonzero(crossing & (x < at)) % 2)


__all__ = ("LoopDepth", "loop_depths")
