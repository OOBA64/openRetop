"""Editing a sketch profile by hand: the fitted lines and arcs are a start, not the last word.

Corners (vertices) are the points where neighbouring segments meet; segment k runs from
vertex k to vertex k + 1 (wrapping on a closed profile). Every edit keeps the profile joined:

- move a vertex: the lines meeting there follow, the arcs keep their angle (a fillet stays a
  quarter circle, its radius changing with the move);
- set an arc's radius: between two lines it stays a fillet tangent to both, else it keeps its
  ends;
- make a fillet a sharp corner, or round a sharp corner with a fillet;
- turn a line exactly horizontal or vertical (in the sketch plane);
- delete a segment: its neighbours run on until they meet.
"""

from __future__ import annotations

import math

import numpy as np

from openretop.modeling.profile2d import Profile2D, Segment2D, _corner_fillet, _cross, _junction, _line_line, _unit


def vertex_count(profile: Profile2D) -> int:
    count = len(profile.segments)
    return count if profile.closed else count + 1


def vertex(profile: Profile2D, index: int) -> np.ndarray:
    segments = profile.segments
    if not profile.closed and index == len(segments):
        return segments[-1].end.copy()
    return segments[index % len(segments)].start.copy()


def vertices(profile: Profile2D) -> np.ndarray:
    return np.array([vertex(profile, index) for index in range(vertex_count(profile))]).reshape(-1, 2)


def _before(profile: Profile2D, index: int) -> int | None:
    """The segment ending at vertex ``index``."""

    if profile.closed:
        return (index - 1) % len(profile.segments)
    return index - 1 if index > 0 else None


def _after(profile: Profile2D, index: int) -> int | None:
    """The segment starting at vertex ``index``."""

    if profile.closed:
        return index % len(profile.segments)
    return index if index < len(profile.segments) else None


def _sweep(arc: Segment2D) -> float:
    return arc.angles()[1]


def _arc_with_sweep(arc: Segment2D, start: np.ndarray, end: np.ndarray, sweep: float) -> None:
    """Reshape ``arc`` to run from ``start`` to ``end`` turning through ``sweep`` (radians)."""

    chord = end - start
    length = float(np.linalg.norm(chord))
    if length < 1e-12 or abs(sweep) < 1e-9:
        arc.start, arc.end = start.copy(), end.copy()
        return
    half = abs(sweep) / 2.0
    radius = length / (2.0 * math.sin(half))
    left = np.array([-chord[1], chord[0]]) / length
    arc.center = 0.5 * (start + end) + left * (radius * math.cos(half)) * (1.0 if sweep > 0 else -1.0)
    arc.radius = radius
    arc.ccw = sweep > 0
    arc.start, arc.end = start.copy(), end.copy()


def move_vertex(profile: Profile2D, index: int, position: object) -> None:
    """Move a corner; the segments meeting there follow (arcs keep their angle)."""

    point = np.asarray(position, dtype=float).reshape(2)
    first, second = _before(profile, index), _after(profile, index)
    for number, at_end in ((first, True), (second, False)):
        if number is None:
            continue
        segment = profile.segments[number]
        start = segment.start if at_end else point
        end = point if at_end else segment.end
        if segment.kind == "arc" and segment.center is not None:
            _arc_with_sweep(segment, start.copy(), end.copy(), _sweep(segment))
        else:
            segment.start, segment.end = start.copy(), end.copy()


def set_arc_radius(profile: Profile2D, index: int, radius: float) -> None:
    """A new radius for arc ``index``: tangent to the lines either side when it sits
    between two lines (a fillet), else through its own ends."""

    arc = profile.segments[index]
    if arc.kind != "arc" or arc.center is None:
        raise ValueError("that segment is not an arc")
    if radius <= 0:
        raise ValueError("a radius must be more than 0")
    neighbours = _line_neighbours(profile, index)
    if neighbours is not None:
        before, after = neighbours
        corner, d0, d1, turn = _corner(before, after)
        center, value, tangent0, tangent1 = _corner_fillet(corner, d0, d1, turn)(radius)
        if not (_on_span(before.start, corner, tangent0) and _on_span(corner, after.end, tangent1)):
            raise ValueError(f"R{radius:g} does not fit between the lines either side")
        arc.center, arc.radius = center, value
        arc.ccw = _cross(d0, d1) > 0
        before.end, arc.start = tangent0.copy(), tangent0.copy()
        arc.end, after.start = tangent1.copy(), tangent1.copy()
        return
    length = float(np.linalg.norm(arc.end - arc.start))
    if radius < length / 2.0:
        raise ValueError(f"an arc between these ends needs a radius of at least {length / 2.0:.4g}")
    sweep = 2.0 * math.asin(min(1.0, length / (2.0 * radius)))
    _arc_with_sweep(arc, arc.start.copy(), arc.end.copy(), math.copysign(sweep, _sweep(arc)))


def make_sharp(profile: Profile2D, index: int) -> None:
    """Take out the fillet ``index``: the lines either side meet at their corner."""

    neighbours = _line_neighbours(profile, index)
    if profile.segments[index].kind != "arc" or neighbours is None:
        raise ValueError("only an arc between two lines can become a sharp corner")
    before, after = neighbours
    corner, _d0, _d1, _turn = _corner(before, after)
    before.end, after.start = corner.copy(), corner.copy()
    del profile.segments[index]


def add_fillet(profile: Profile2D, vertex_index: int, radius: float) -> int:
    """Round the sharp corner at a vertex between two lines; returns the new arc's index."""

    first, second = _before(profile, vertex_index), _after(profile, vertex_index)
    if first is None or second is None:
        raise ValueError("an end of an open profile has no corner to round")
    before, after = profile.segments[first], profile.segments[second]
    if before.kind != "line" or after.kind != "line":
        raise ValueError("a fillet rounds a corner between two lines")
    if radius <= 0:
        raise ValueError("a radius must be more than 0")
    corner, d0, d1, turn = _corner(before, after)
    if turn < 1.0 or turn > 179.0:
        raise ValueError("the lines there run straight on: no corner to round")
    center, value, tangent0, tangent1 = _corner_fillet(corner, d0, d1, turn)(radius)
    if not (_on_span(before.start, corner, tangent0) and _on_span(corner, after.end, tangent1)):
        raise ValueError(f"R{radius:g} does not fit between these lines")
    arc = Segment2D("arc", tangent0.copy(), tangent1.copy(), center=center, radius=value, ccw=_cross(d0, d1) > 0)
    before.end, after.start = tangent0.copy(), tangent1.copy()
    position = second if second > first else len(profile.segments)
    profile.segments.insert(position, arc)
    return position


def make_axis_line(profile: Profile2D, index: int) -> str:
    """Turn line ``index`` exactly horizontal or vertical (whichever is nearer) about its middle."""

    line = profile.segments[index]
    if line.kind != "line":
        raise ValueError("that segment is not a line")
    direction = line.end - line.start
    middle = 0.5 * (line.start + line.end)
    if abs(direction[0]) >= abs(direction[1]):
        axis, name = np.array([math.copysign(1.0, direction[0]), 0.0]), "horizontal"
    else:
        axis, name = np.array([0.0, math.copysign(1.0, direction[1])]), "vertical"
    start = middle + axis * float((line.start - middle) @ axis)
    end = middle + axis * float((line.end - middle) @ axis)
    vertex_index = index
    following = (index + 1) % len(profile.segments) if profile.closed else index + 1
    move_vertex(profile, vertex_index, start)
    move_vertex(profile, following, end)
    return name


def delete_segment(profile: Profile2D, index: int) -> None:
    """Remove segment ``index``; its neighbours run on until they meet."""

    count = len(profile.segments)
    if count <= (3 if profile.closed else 1):
        raise ValueError("the profile would be left with too little")
    gone = profile.segments[index]
    if not profile.closed and index in (0, count - 1):
        del profile.segments[index]
        return
    before = profile.segments[(index - 1) % count]
    after = profile.segments[(index + 1) % count]
    point = _junction(before, after, 0.5 * (gone.start + gone.end), reach=2.0)
    del profile.segments[index]
    for segment, at_end in ((before, True), (after, False)):
        start = segment.start if at_end else point
        end = point if at_end else segment.end
        if segment.kind == "arc" and segment.center is not None:
            _arc_with_sweep(segment, start.copy(), end.copy(), _sweep(segment))
        else:
            segment.start, segment.end = start.copy(), end.copy()


def close_profile(profile: Profile2D) -> str:
    """Close an open profile (a section broken by a hole too wide to bridge on its own):
    end lines running on in one direction become one line, else a line joins the ends."""

    if profile.closed:
        raise ValueError("the profile is closed already")
    if len(profile.segments) < 2:
        raise ValueError("a closed profile needs more than one segment")
    first, last = profile.segments[0], profile.segments[-1]
    profile.closed = True
    if first.kind == last.kind == "line":
        d0, d1 = _unit(last.end - last.start), _unit(first.end - first.start)
        offset = float(abs(_cross(d0, first.start - last.start)))
        if float(d0 @ d1) > math.cos(math.radians(3.0)) and offset <= 0.02 * max(last.length, first.length, 1e-9):
            first.start = last.start.copy()  # one wall, across the hole
            del profile.segments[-1]
            return "closed: the two pieces of the wall are one line"
    profile.segments.append(Segment2D("line", last.end.copy(), first.start.copy()))
    return "closed with a line across the gap"


def describe(segment: Segment2D) -> str:
    if segment.kind == "line":
        direction = segment.end - segment.start
        angle = math.degrees(math.atan2(direction[1], direction[0])) % 180.0
        return f"Line, length {segment.length:.3f}, at {angle:.1f} deg"
    return f"Arc R{segment.radius:.3f}, {abs(math.degrees(_sweep(segment))):.1f} deg"


def _line_neighbours(profile: Profile2D, index: int) -> tuple[Segment2D, Segment2D] | None:
    count = len(profile.segments)
    if not profile.closed and (index == 0 or index == count - 1):
        return None
    before, after = profile.segments[(index - 1) % count], profile.segments[(index + 1) % count]
    if before.kind != "line" or after.kind != "line":
        return None
    return before, after


def _corner(before: Segment2D, after: Segment2D) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    d0, d1 = _unit(before.end - before.start), _unit(after.end - after.start)
    corner = _line_line(before.start, d0, after.end, d1)
    if corner is None:
        raise ValueError("the lines either side are parallel")
    turn = math.degrees(math.acos(float(np.clip(d0 @ d1, -1.0, 1.0))))
    return corner, d0, d1, turn


def _on_span(start: np.ndarray, end: np.ndarray, point: np.ndarray) -> bool:
    """Whether ``point`` (on the line through start and end) lies between them."""

    direction = end - start
    length2 = float(direction @ direction)
    t = float((point - start) @ direction) / max(length2, 1e-24)
    return -1e-6 <= t <= 1.0 + 1e-6


__all__ = (
    "add_fillet",
    "close_profile",
    "delete_segment",
    "describe",
    "make_axis_line",
    "make_sharp",
    "move_vertex",
    "set_arc_radius",
    "vertex",
    "vertex_count",
    "vertices",
)
