"""Lines and arcs fitted to a section of the scan (S-13): the sketch profile.

A section polyline is noisy and has thousands of points; CAD wants a handful of exact lines and
arcs meeting at exact points. ``fit_profile`` does what ExModel's "fit primitives" does over a
whole section at once:

1. resample evenly; grow pieces greedily: from each point the line or the arc that stays
   within the tolerance furthest, the line when about as far. A sharp corner the scan has
   rounded is recognised and skipped (the two lines will meet exactly);
2. merge neighbours that fit as one, fold slivers into a neighbour, drop arcs below the
   sharp radius between two lines;
3. lines: least squares through their own samples (not the biased end samples), exactly
   horizontal/vertical when that still fits; collinear neighbours become one line, and the
   lines at sharp corners are refitted without the rounded-off samples;
4. exact shared end points: a corner is where two pieces intersect; an arc between two lines
   it can meet tangentially is refitted as a tangent fillet (or slot end).

Measured on simulated scans (0.02 noise): walls land within 0.01 of their true position,
R2/R3 fillets within 0.08, sharp corners within 0.03. Lines and arcs suit prismatic profiles;
on a smooth freeform curve the chain of arcs, joined end to end, deviates up to about twice
the tolerance (a spline fits those). Each profile reports its true deviation from the samples
it was fitted to.

Coordinates are 2D, in the sketch plane.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Segment2D:
    kind: str  # "line" or "arc"
    start: np.ndarray
    end: np.ndarray
    center: np.ndarray | None = None
    radius: float = 0.0
    ccw: bool = True  # arc direction from start to end
    max_error: float = 0.0

    def sample(self, count: int = 24) -> np.ndarray:
        if self.kind == "line":
            t = np.linspace(0.0, 1.0, max(2, count))[:, None]
            return self.start + (self.end - self.start) * t
        assert self.center is not None
        a0, sweep = self.angles()
        t = np.linspace(0.0, 1.0, max(3, count))
        angle = a0 + sweep * t
        return self.center + self.radius * np.c_[np.cos(angle), np.sin(angle)]

    def angles(self) -> tuple[float, float]:
        """Start angle and signed sweep (counter-clockwise positive)."""

        assert self.center is not None
        a0 = math.atan2(*(self.start - self.center)[::-1])
        a1 = math.atan2(*(self.end - self.center)[::-1])
        sweep = (a1 - a0) % (2 * math.pi)
        if not self.ccw:
            sweep -= 2 * math.pi
        if abs(sweep) < 1e-12:
            sweep = 2 * math.pi if self.ccw else -2 * math.pi
        return a0, sweep

    @property
    def length(self) -> float:
        if self.kind == "line":
            return float(np.linalg.norm(self.end - self.start))
        return abs(self.angles()[1]) * self.radius

    def midpoint(self) -> np.ndarray:
        return self.sample(3)[1]

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {"kind": self.kind, "start": self.start.tolist(), "end": self.end.tolist()}
        if self.kind == "arc" and self.center is not None:
            data.update(center=self.center.tolist(), radius=float(self.radius), ccw=bool(self.ccw))
        return data

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Segment2D:
        center = data.get("center")
        return cls(
            str(data["kind"]),
            np.asarray(data["start"], dtype=float),
            np.asarray(data["end"], dtype=float),
            center=None if center is None else np.asarray(center, dtype=float),
            radius=float(data.get("radius", 0.0)),  # type: ignore[arg-type]
            ccw=bool(data.get("ccw", True)),
        )


@dataclass
class Profile2D:
    segments: list[Segment2D] = field(default_factory=list)
    closed: bool = False
    deviation: float = 0.0  # largest distance of the fitted samples from the profile
    rms: float = 0.0
    gap: float = 0.0  # a closed profile's ends may span a hole in the scan this long

    @property
    def max_error(self) -> float:
        return max((segment.max_error for segment in self.segments), default=0.0)

    def distances(self, points: object) -> np.ndarray:
        """Distance of each 2D point to the nearest segment of the profile."""

        points = np.asarray(points, dtype=float).reshape(-1, 2)
        if not self.segments:
            return np.full(len(points), np.inf)
        return np.min([segment_distances(segment, points) for segment in self.segments], axis=0)

    def to_dict(self) -> dict[str, object]:
        """Plain data, for the kernel job and the project file."""

        return {
            "segments": [segment.to_dict() for segment in self.segments],
            "closed": self.closed,
            "outline": self.polyline(8).tolist(),
            "deviation": self.deviation,
            "rms": self.rms,
            "gap": self.gap,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Profile2D:
        segments = [Segment2D.from_dict(item) for item in data.get("segments", [])]  # type: ignore[attr-defined]
        return cls(
            segments,
            bool(data.get("closed", False)),
            float(data.get("deviation", 0.0)),  # type: ignore[arg-type]
            float(data.get("rms", 0.0)),  # type: ignore[arg-type]
            float(data.get("gap", 0.0)),  # type: ignore[arg-type]
        )

    def polyline(self, per_segment: int = 24) -> np.ndarray:
        pieces = [segment.sample(per_segment)[:-1] for segment in self.segments]
        if not pieces:
            return np.zeros((0, 2))
        last = self.segments[-1].end[None, :]
        return np.vstack(pieces + [last])


def segment_distances(segment: Segment2D, points: np.ndarray) -> np.ndarray:
    """Distance of each point to a line segment or an arc (its swept part only)."""

    if segment.kind == "line":
        chord = segment.end - segment.start
        length2 = float(chord @ chord)
        t = np.clip(((points - segment.start) @ chord) / max(length2, 1e-30), 0.0, 1.0)
        return np.linalg.norm(points - (segment.start + t[:, None] * chord), axis=1)
    assert segment.center is not None
    a0, sweep = segment.angles()
    offset = points - segment.center
    angle = np.arctan2(offset[:, 1], offset[:, 0])
    along = ((angle - a0) * (1.0 if sweep >= 0 else -1.0)) % (2 * math.pi)
    inside = along <= abs(sweep) + 1e-12
    on_circle = np.abs(np.linalg.norm(offset, axis=1) - segment.radius)
    to_ends = np.minimum(np.linalg.norm(points - segment.start, axis=1), np.linalg.norm(points - segment.end, axis=1))
    return np.where(inside, on_circle, to_ends)


def estimate_noise(loops: object, *, window: int = 31, stride: int = 4) -> float:
    """The spread of section samples about the true outline (a standard deviation).

    A circle (or line) is fitted to each run of ``window`` samples; the lower quartile of
    their residual RMS is the noise: runs on plain lines and arcs give it, runs across a
    corner are larger and fall above. Runs must be long: neighbouring section samples come
    from the same scan triangles, so a short run sees too little of the noise. The samples
    are interpolated between scan vertices, so their spread is about 0.7x the scan's.
    """

    values = []
    for loop in loops:  # type: ignore[attr-defined]
        points = np.asarray(loop, dtype=float).reshape(-1, 2)
        for start in range(0, len(points) - window + 1, stride):
            run = points[start : start + window]
            point, direction, _error = fit_line_2d(run)
            residual = (run - point) @ np.array([-direction[1], direction[0]])
            center, radius, _error = fit_circle_2d(run)
            on_circle = np.linalg.norm(run - center, axis=1) - radius
            if np.sum(on_circle**2) < np.sum(residual**2):
                residual = on_circle
            values.append(math.sqrt(float(np.sum(residual**2)) / (window - 3)))
    return float(np.percentile(values, 25)) if values else 0.0


def auto_tolerance(loops: object, *, floor: float = 0.005) -> float:
    """A fit tolerance for these outlines: 6x their sample noise (about 4 standard
    deviations of the scan's own noise), so noise alone never breaks a line."""

    return max(6.0 * estimate_noise(loops), floor)


# -- primitive fits ---------------------------------------------------------------------------


def fit_line_2d(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """(point on line, unit direction, largest distance) by total least squares."""

    center = points.mean(axis=0)
    _s, _v, axes = np.linalg.svd(points - center, full_matrices=False)
    direction = axes[0]
    normal = np.array([-direction[1], direction[0]])
    error = float(np.max(np.abs((points - center) @ normal))) if len(points) else 0.0
    return center, direction, error


def fit_circle_2d(points: np.ndarray) -> tuple[np.ndarray, float, float]:
    """(center, radius, largest distance): algebraic fit refined by Gauss-Newton."""

    x, y = points[:, 0], points[:, 1]
    design = np.c_[2 * x, 2 * y, np.ones(len(x))]
    solution, *_ = np.linalg.lstsq(design, x * x + y * y, rcond=None)
    center = solution[:2]
    radius = math.sqrt(max(solution[2] + center @ center, 1e-18))
    for _step in range(10):
        offsets = points - center
        distance = np.linalg.norm(offsets, axis=1)
        distance = np.maximum(distance, 1e-12)
        residual = distance - radius
        jacobian = np.c_[-offsets / distance[:, None], -np.ones(len(points))]
        delta, *_ = np.linalg.lstsq(jacobian, -residual, rcond=None)
        center = center + delta[:2]
        radius = radius + delta[2]
        if np.abs(delta).max() < 1e-12:
            break
    error = float(np.max(np.abs(np.linalg.norm(points - center, axis=1) - radius)))
    return center, float(abs(radius)), error


# -- the profile ------------------------------------------------------------------------------


def fit_profile(
    points: object,
    *,
    tolerance: float = 0.05,
    closed: bool | None = None,
    corner_degrees: float = 35.0,
    snap_degrees: float = 5.0,
    max_radius_factor: float = 20.0,
    sharp_radius: float | None = None,
) -> Profile2D:
    """Lines and arcs within ``tolerance`` of a (noisy) section polyline.

    ``snap_degrees``: a line within this of horizontal/vertical is made exact when it then
    still fits its samples within the tolerance (so a short step snaps, a long drafted wall
    does not).

    ``sharp_radius``: an arc smaller than this between two lines is a sharp corner the scan
    has rounded (a scanner rounds every edge by about its point spacing), so the lines meet
    exactly instead. Default: 5x the section's point spacing.
    """

    raw = np.asarray(points, dtype=float).reshape(-1, 2)
    if closed is None:
        # a section broken by a hole in the scan is still a loop: its ends nearly meet
        span = float(np.linalg.norm(raw.max(axis=0) - raw.min(axis=0))) if len(raw) else 0.0
        closed = len(raw) > 3 and float(np.linalg.norm(raw[0] - raw[-1])) <= max(1e-6, 0.15 * span)
    if closed and np.linalg.norm(raw[0] - raw[-1]) <= 1e-6:
        raw = raw[:-1]
    if len(raw) < 3:
        return Profile2D([], bool(closed))
    size = float(np.linalg.norm(raw.max(axis=0) - raw.min(axis=0)))
    step = max(float(np.median(np.linalg.norm(np.diff(raw, axis=0), axis=1))), size / 4000.0, 1e-9)
    gap = float(np.linalg.norm(raw[-1] - raw[0])) if closed else 0.0
    # a loop broken by a hole in the scan: fit what was scanned as an open profile, then close
    # it where its end pieces meet (a fillet seen in part is rebuilt tangent to its walls);
    # bridging the hole with a straight chord would invent a piece the scan never showed
    bridged = bool(closed) and gap > 3.0 * step
    growing_closed = bool(closed) and not bridged
    path = _resample(raw, step, growing_closed)
    max_radius = max_radius_factor * size
    sharp = 5.0 * step if sharp_radius is None else sharp_radius

    def grow(path: np.ndarray) -> list[Segment2D]:
        return _grow(
            path, tolerance=tolerance, max_radius=max_radius, closed=growing_closed, sharp=sharp, corner_degrees=corner_degrees
        )

    segments = grow(path)
    if growing_closed and len(segments) > 1:
        # start the loop at the beginning of its longest piece, so the seam is not in the
        # middle of a feature, and grow again from there
        longest = max(segments, key=lambda segment: _indices(segment)[1] - _indices(segment)[0])
        shift = _indices(longest)[0] % len(path)
        path = np.roll(path, -shift, axis=0)
        segments = grow(path)
    segments = _merge(path, segments, tolerance, max_radius, growing_closed)
    segments = _absorb_slivers(path, segments, step, tolerance, max_radius, growing_closed)
    segments = _sharpen(path, segments, sharp, growing_closed)
    if bridged:  # the two pieces either side of the hole may be one (a wall, a fillet)
        segments = _merge(path, segments, tolerance, max_radius, True)
        segments = _seam_arc(path, segments, tolerance, max_radius)
    profile = Profile2D([_finish(path, s, snap_degrees, tolerance) for s in segments], bool(closed), gap=gap if bridged else 0.0)
    _join(profile, path, corner_degrees)
    _merge_collinear(profile, path, snap_degrees, tolerance, sharp)
    _join(profile, path, corner_degrees)
    for _round in range(2):
        if not _trim_corners(profile, path, snap_degrees, tolerance, sharp, corner_degrees):
            break
        _join(profile, path, corner_degrees)
    _refit_fillets(profile, path, tolerance)
    distances = profile.distances(raw)
    profile.deviation = float(np.max(distances)) if len(distances) else 0.0
    profile.rms = float(np.sqrt(np.mean(distances**2))) if len(distances) else 0.0
    return profile


def _resample(points: np.ndarray, step: float, closed: bool) -> np.ndarray:
    loop = np.vstack([points, points[:1]]) if closed else points
    length = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(loop, axis=0), axis=1))]
    count = max(int(length[-1] / step), 8)
    targets = np.linspace(0.0, length[-1], count + (0 if closed else 1), endpoint=not closed)
    return np.c_[np.interp(targets, length, loop[:, 0]), np.interp(targets, length, loop[:, 1])]


def _points(path: np.ndarray, start: int, end: int, closed: bool) -> np.ndarray:
    n = len(path)
    if closed:
        return path[np.arange(start, end + 1) % n]
    return path[start : end + 1]


def _best_fit(points: np.ndarray, tolerance: float, max_radius: float) -> Segment2D | None:
    point, direction, line_error = fit_line_2d(points)
    if line_error <= tolerance:
        return Segment2D("line", points[0], points[-1], max_error=line_error)
    if len(points) >= 5:
        center, radius, arc_error = fit_circle_2d(points)
        if arc_error <= tolerance and radius < max_radius:
            cross = _cross(points[len(points) // 2] - points[0], points[-1] - points[len(points) // 2])
            return Segment2D("arc", points[0], points[-1], center=center, radius=radius, ccw=bool(cross > 0), max_error=arc_error)
    return None


def _grow(
    path: np.ndarray, *, tolerance: float, max_radius: float, closed: bool, sharp: float, corner_degrees: float
) -> list[Segment2D]:
    """Greedy: from each point, grow a line and an arc as far as they stay within the
    tolerance; keep the one that reaches further (the line when about as far), go on from its
    end. A fillet becomes one arc between two lines.

    A sharp corner the scan has rounded is not an arc: when a line, a short skipped rounding
    and a second line reach as far as the arc would, that wins, and the skipped samples belong
    to neither line (the lines meet exactly at the corner later).
    """

    n = len(path)
    last = n if closed else n - 1  # a closed loop ends back at its first point
    segments: list[Segment2D] = []
    i = 0
    while i < last:
        line_end = _reach(path, i, last, tolerance, max_radius, "line", closed)
        arc_end = _reach(path, i, last, tolerance, max_radius, "arc", closed)
        slack = max(2, (line_end - i) // 20)
        kind, j, following = ("line", line_end, line_end) if line_end + slack >= arc_end else ("arc", arc_end, arc_end)
        if kind == "arc":
            arc_points = _points(path, i, j, closed)
            center, radius, _error = fit_circle_2d(arc_points)
            length = float(np.sum(np.linalg.norm(np.diff(arc_points, axis=0), axis=1)))
            sag = radius * (1.0 - math.cos(min(length / max(radius, 1e-12), math.pi) / 2.0))
            if sag <= 1.5 * tolerance:
                # barely curved: an arc this flat only "fits" by bending round the next corner
                kind, j, following = "line", line_end, line_end
            elif segments and segments[-1].kind == "line":
                corner = _corner_jump(path, segments[-1], i, arc_end, last, tolerance, max_radius, closed, sharp, corner_degrees)
                if corner is not None:
                    i = corner  # the rounding belongs to neither line
                    continue
        j = max(j, i + 1)
        points = _points(path, i, j, closed)
        fitted = _best_fit(points, tolerance, max_radius) if len(points) >= 3 else None
        if fitted is None or fitted.kind != kind:
            point, direction, error = fit_line_2d(points)
            fitted = Segment2D("line", points[0], points[-1], max_error=error)
        fitted.start_index, fitted.end_index = i, j  # type: ignore[attr-defined]
        segments.append(fitted)
        i = max(following, j)
    return segments


def _corner_jump(
    path: np.ndarray, previous: Segment2D, start: int, arc_end: int, last: int, tolerance: float, max_radius: float,
    closed: bool, sharp: float, corner_degrees: float,
) -> int | None:
    """Where the next line starts, if the outline from ``start`` is a sharp corner the scan
    rounded (after the line ``previous``) rather than the arc that would grow there.

    The test: past a short skipped stretch (at most 2x ``sharp``), a line reaches about as
    far as the arc, turns at least ``corner_degrees`` from the previous line, and the
    skipped samples hug the two lines' corner closely enough for a rounding no bigger than
    ``sharp``: a round of radius R passes R (sec(turn/2) - 1) from the corner (a scanned
    sharp 90 degree edge implies about R0.5, a real R2 fillet R2, a smooth crest its own
    radius).
    """

    n = len(path)
    step = float(np.linalg.norm(path[1] - path[0])) or 1e-9
    p_start, p_end = _indices(previous)
    first = _points(path, p_start, p_end, closed)
    point0, d0, _e = fit_line_2d(first)
    d0 = d0 if d0 @ (first[-1] - first[0]) >= 0 else -d0
    skip_max = max(1, int(round(2.0 * sharp / step)))
    for skip in range(1, skip_max + 1):
        begin = start + skip
        if begin >= last - 2:
            return None
        end = _reach(path, begin, last, tolerance, max_radius, "line", closed)
        if end - begin < 3 or end < arc_end - sharp / step:
            continue
        second = _points(path, begin, end, closed)
        point1, d1, _e = fit_line_2d(second)
        d1 = d1 if d1 @ (second[-1] - second[0]) >= 0 else -d1
        turn = math.degrees(math.acos(float(np.clip(d0 @ d1, -1.0, 1.0))))
        if turn < corner_degrees:
            continue
        corner = _line_line(point0, d0, point1, d1)
        if corner is None:
            continue
        distance = np.linalg.norm(path[np.arange(start, begin + 1) % n] - corner, axis=1)
        implied = float(np.min(distance)) / max(1.0 / math.cos(math.radians(turn) / 2.0) - 1.0, 1e-9)
        if float(np.max(distance)) <= max(2.0 * sharp, 2.0 * step) and implied <= sharp:
            return begin
    return None


def _sharpen(path: np.ndarray, segments: list[Segment2D], sharp_radius: float, closed: bool) -> list[Segment2D]:
    """Drop arcs below ``sharp_radius`` between two lines: the lines meet at a sharp corner."""

    count = len(segments)
    keep: list[Segment2D] = []
    for k, segment in enumerate(segments):
        if segment.kind == "arc" and segment.radius < sharp_radius and count > 2 and (closed or 0 < k < count - 1):
            before, after = segments[(k - 1) % count], segments[(k + 1) % count]
            if before.kind == "line" and after.kind == "line":
                corner = _line_line(before.start, before.end - before.start, after.start, after.end - after.start)
                if corner is not None and float(np.linalg.norm(corner - segment.midpoint())) <= 3.0 * sharp_radius:
                    continue
        keep.append(segment)
    return keep


def _reach(path: np.ndarray, start: int, last: int, tolerance: float, max_radius: float, kind: str, closed: bool) -> int:
    """The furthest index a single line (or arc) from ``start`` fits to, within tolerance."""

    def fits(end: int) -> bool:
        points = _points(path, start, end, closed)
        if kind == "line":
            return fit_line_2d(points)[2] <= tolerance
        if len(points) < 5:
            return True
        center, radius, error = fit_circle_2d(points)
        if error <= tolerance and radius < max_radius:
            return True
        # nearly straight so far: a line is an arc of endless radius, so the arc grows on
        # (else a fillet entered tangentially dies at its first samples and a chord takes it)
        return not radius < max_radius and fit_line_2d(points)[2] <= tolerance

    low = min(start + (2 if kind == "line" else 4), last)
    if not fits(low):
        return low
    stride = 4
    high = low
    while high < last:  # expand until it stops fitting
        candidate = min(high + stride, last)
        if not fits(candidate):
            break
        high = candidate
        stride *= 2
    else:
        return last
    upper = min(high + stride, last)
    while upper - high > 1:  # then bisect the boundary
        middle = (high + upper) // 2
        if fits(middle):
            high = middle
        else:
            upper = middle
    return high


def _merge(path: np.ndarray, segments: list[Segment2D], tolerance: float, max_radius: float, closed: bool) -> list[Segment2D]:
    """One piece for two neighbours of a kind whose samples fit as one."""

    changed = True
    while changed and len(segments) > 1:
        changed = False
        count = len(segments)
        for k in range(count if closed else count - 1):
            first, second = segments[k], segments[(k + 1) % count]
            if first.kind != second.kind:
                continue
            start = first.start_index  # type: ignore[attr-defined]
            end = second.end_index  # type: ignore[attr-defined]
            if closed and end <= start:
                end += len(path)
            merged = _best_fit(_points(path, start, end, closed), tolerance, max_radius)
            if merged is None or merged.kind != first.kind:
                continue
            merged.start_index, merged.end_index = start, end  # type: ignore[attr-defined]
            if closed and k == count - 1:
                segments = [merged] + segments[1:-1]
            else:
                segments = segments[:k] + [merged] + segments[k + 2 :]
            changed = True
            break
    return segments


def _seam_arc(path: np.ndarray, segments: list[Segment2D], tolerance: float, max_radius: float) -> list[Segment2D]:
    """Across a hole in the scan: the pieces either side of it, between two walls, that
    together are one fillet tangent to both walls (seen in part) become that fillet.

    At the end of a run a fillet's fragment often grows as a short line (a line and an arc
    both reach the end, and the line wins the tie), and an arc fragment can run on a little
    into the wall; measured against the whole wall-fillet-wall corner, neither matters.
    """

    from scipy.optimize import minimize_scalar

    if len(segments) < 4:
        return segments
    last, first = segments[-1], segments[0]
    before, after = segments[-2], segments[1]  # the walls around the hole's pieces
    if "arc" not in (last.kind, first.kind) or before.kind != "line" or after.kind != "line":
        return segments
    n = len(path)
    walls = []
    for wall in (before, after):
        start, end = _indices(wall)
        samples = _points(path, start, end, True)
        point, direction, _error = fit_line_2d(samples)
        walls.append((point, direction if direction @ (samples[-1] - samples[0]) >= 0 else -direction))
    (p0, d0), (p1, d1) = walls
    corner = _line_line(p0, d0, p1, d1)
    turn = math.degrees(math.acos(float(np.clip(d0 @ d1, -1.0, 1.0))))
    if corner is None or not 5.0 < turn < 175.0:
        return segments
    start, end = _indices(last)[0], _indices(first)[1] + n
    points = _points(path, start, end, True)
    shape = _corner_fillet(corner, d0, d1, turn)
    arc = last if last.kind == "arc" else first

    def distances(radius: float) -> np.ndarray:
        center, value, tangent0, tangent1 = shape(radius)
        return _corner_distances(points, center, value, tangent0, tangent1, d0, d1)

    guess = max(arc.radius, 1e-6)
    result = minimize_scalar(lambda radius: float(np.sum(distances(radius) ** 2)), bounds=(0.2 * guess, 3.0 * guess), method="bounded")
    error = float(np.max(distances(float(result.x))))
    if error > 1.5 * tolerance:
        return segments
    center, radius, tangent0, tangent1 = shape(float(result.x))
    merged = Segment2D("arc", tangent0, tangent1, center=center, radius=radius, ccw=_cross(d0, d1) > 0, max_error=error)
    merged.start_index, merged.end_index = start, end  # type: ignore[attr-defined]
    return [merged] + segments[1:-1]


def _indices(segment: Segment2D) -> tuple[int, int]:
    return segment.start_index, segment.end_index  # type: ignore[attr-defined]


def _absorb_slivers(
    path: np.ndarray, segments: list[Segment2D], step: float, tolerance: float, max_radius: float, closed: bool
) -> list[Segment2D]:
    """Fold the tiny pieces splitting leaves where a line runs into a fillet into a neighbour.

    A piece a few samples long between a line and an arc is the noise at their tangent
    point, not a feature: the neighbour that fits it (with a little slack) takes it over.
    """

    shortest = max(10.0 * tolerance, 5.0 * step)  # outline length below which a piece is noise
    changed = True
    while changed and len(segments) > 2:
        changed = False
        count = len(segments)
        for k, piece in enumerate(segments):
            start, end = _indices(piece)
            if (end - start) * step >= shortest:
                continue
            options = []
            for side in (-1, 1):
                if not closed and not 0 <= k + side < count:
                    continue
                other_index = (k + side) % count
                other = segments[other_index]
                o_start, o_end = _indices(other)
                if side < 0:
                    span = (o_start, end if end >= o_start else end + len(path))
                else:
                    span = (start, o_end if o_end >= start else o_end + len(path))
                fitted = _best_fit(_points(path, span[0], span[1], closed), 1.5 * tolerance, max_radius)
                if fitted is not None and fitted.kind == other.kind:
                    options.append((fitted.max_error, other_index, fitted, span))
            if not options:
                # nobody takes it: drop it, and its neighbours meet at their exact junction
                segments = segments[:k] + segments[k + 1 :]
                changed = True
                break
            _error, other_index, fitted, span = min(options, key=lambda item: item[0])
            fitted.start_index, fitted.end_index = span  # type: ignore[attr-defined]
            keep = [segment for index, segment in enumerate(segments) if index not in (k, other_index)]
            position = min(k, other_index)
            if closed and {k, other_index} == {0, count - 1}:
                keep.append(fitted)  # the merged piece wraps the loop's seam
            else:
                keep.insert(position, fitted)
            segments = keep
            changed = True
            break
    return segments


def _refit_fillets(profile: Profile2D, path: np.ndarray, tolerance: float) -> None:
    """An arc between two lines that it can meet tangentially is a fillet: refit it so.

    Only one number is free: the radius for a corner fillet (its center sits on the corner's
    bisector), or the position along the lines for a semicircle between parallel lines (a
    slot end; the radius is half their distance). The fit runs over the arc's points and a
    margin of each line, measured against the whole line-arc-line shape, so which side of
    the tangent point a sample was given to does not matter. A free circle through a short,
    noisy arc is far less steady (R2.9-3.2 for a true R3). The tangent arc is kept only when
    it fits the outline as well (within 1.5x the tolerance).
    """

    from scipy.optimize import minimize_scalar

    segments = profile.segments
    count = len(segments)
    for k, arc in enumerate(segments):
        if arc.kind != "arc" or arc.center is None or count < 3 or (not profile.closed and (k == 0 or k == count - 1)):
            continue
        before, after = segments[(k - 1) % count], segments[(k + 1) % count]
        if before.kind != "line" or after.kind != "line":
            continue
        d0 = _unit(before.end - before.start)
        d1 = _unit(after.end - after.start)
        turn = math.degrees(math.acos(float(np.clip(d0 @ d1, -1.0, 1.0))))
        if turn < 5.0:
            continue
        points = _fillet_points(path, before, arc, after, profile.closed)
        if turn > 175.0:  # a slot end: parallel lines, opposite directions
            d = _unit(d0 - d1)
            normal = np.array([-d[1], d[0]])
            o0, o1 = float(before.start @ normal), float(after.start @ normal)
            shape = _slot_end(d, normal, o0, o1)
            s0 = float(arc.center @ d)
            bounds = (s0 - abs(o1 - o0) / 2.0, s0 + abs(o1 - o0) / 2.0)
        else:
            corner = _line_line(before.start, d0, after.start, d1)
            if corner is None:
                continue
            shape = _corner_fillet(corner, d0, d1, turn)
            bounds = (0.2 * arc.radius, 3.0 * arc.radius)

        def distances(value: float, shape: _Shape = shape, points: np.ndarray = points, d0: np.ndarray = d0, d1: np.ndarray = d1) -> np.ndarray:
            center, radius, tangent0, tangent1 = shape(value)
            return _corner_distances(points, center, radius, tangent0, tangent1, d0, d1)

        result = minimize_scalar(lambda value: float(np.sum(distances(value) ** 2)), bounds=bounds, method="bounded")
        error = float(np.max(distances(float(result.x))))
        if error > 1.5 * tolerance:
            continue  # not tangent (an arc beside a sharp corner): keep the free arc
        center, radius, _t0, _t1 = shape(float(result.x))
        # the tangent points from each line's own far end, so a snapped line stays exact
        tangent0 = before.start + d0 * ((center - before.start) @ d0)
        tangent1 = after.end + d1 * ((center - after.end) @ d1)
        arc.center, arc.radius, arc.max_error = center, radius, error
        before.end, arc.start = tangent0.copy(), tangent0.copy()
        arc.end, after.start = tangent1.copy(), tangent1.copy()
        arc.ccw = _cross(d0, d1) > 0 if turn <= 175.0 else _cross(d0, center - tangent0) > 0


_Shape = Callable[[float], tuple[np.ndarray, float, np.ndarray, np.ndarray]]  # -> center, radius, tangent points


def _slot_end(d: np.ndarray, normal: np.ndarray, o0: float, o1: float) -> _Shape:
    """The semicircle between two parallel lines (offsets o0, o1 along ``normal``), by its
    position along them."""

    radius = abs(o1 - o0) / 2.0
    middle = normal * (o0 + o1) / 2.0

    def shape(position: float) -> tuple[np.ndarray, float, np.ndarray, np.ndarray]:
        return middle + d * position, radius, normal * o0 + d * position, normal * o1 + d * position

    return shape


def _corner_fillet(corner: np.ndarray, d0: np.ndarray, d1: np.ndarray, turn: float) -> _Shape:
    """The fillet tangent to both lines of a corner, by its radius."""

    bisector = _unit(d1 - d0)  # points into the fillet's side
    reach = 1.0 / max(math.sin(math.radians(180.0 - turn) / 2.0), 1e-9)

    def shape(radius: float) -> tuple[np.ndarray, float, np.ndarray, np.ndarray]:
        center = corner + bisector * (radius * reach)
        return center, radius, corner + d0 * ((center - corner) @ d0), corner + d1 * ((center - corner) @ d1)

    return shape


def _fillet_points(path: np.ndarray, before: Segment2D, arc: Segment2D, after: Segment2D, closed: bool) -> np.ndarray:
    """The arc's samples and a margin of each neighbouring line (up to half its length)."""

    n = len(path)
    start, end = _indices(arc)
    if end < start:
        end += n
    margin = max(3, end - start)
    b_start, b_end = _indices(before)
    a_start, a_end = _indices(after)
    lo = start - min(margin, max(0, ((b_end - b_start) % n if closed else b_end - b_start) // 2))
    hi = end + min(margin, max(0, ((a_end - a_start) % n if closed else a_end - a_start) // 2))
    if closed:
        return path[np.arange(lo, hi + 1) % n]
    return path[max(lo, 0) : min(hi, n - 1) + 1]


def _corner_distances(
    points: np.ndarray, center: np.ndarray, radius: float, tangent0: np.ndarray, tangent1: np.ndarray, d0: np.ndarray, d1: np.ndarray
) -> np.ndarray:
    """Distance of each point to the line - arc - line shape (lines end at the tangent points)."""

    def ray(origin: np.ndarray, direction: np.ndarray) -> np.ndarray:  # the half line from origin
        along = np.maximum((points - origin) @ direction, 0.0)
        return np.linalg.norm(points - (origin + along[:, None] * direction), axis=1)

    on_arc = np.abs(np.linalg.norm(points - center, axis=1) - radius)
    return np.minimum(np.minimum(ray(tangent0, -d0), ray(tangent1, d1)), on_arc)


def _unit(vector: np.ndarray) -> np.ndarray:
    return vector / max(float(np.linalg.norm(vector)), 1e-15)


def _merge_collinear(profile: Profile2D, path: np.ndarray, snap_degrees: float, tolerance: float, sharp: float) -> None:
    """One line for neighbouring lines that are one wall (split where a line started inside
    a corner's rounding and so stopped early)."""

    segments = profile.segments
    n = len(path)
    k = 0
    while len(segments) > 1 and k < (len(segments) if profile.closed else len(segments) - 1):
        count = len(segments)
        first, second = segments[k], segments[(k + 1) % count]
        if first.kind == second.kind == "line":
            d0, d1 = _unit(first.end - first.start), _unit(second.end - second.start)
            if float(d0 @ d1) >= math.cos(math.radians(15.0)):  # the fit below decides
                start, end = _indices(first)[0], _indices(second)[1]
                if end <= start:
                    end += n
                merged = Segment2D("line", first.start.copy(), second.end.copy())
                merged.start_index, merged.end_index = start, end  # type: ignore[attr-defined]
                _finish(path, merged, snap_degrees, tolerance, exclude=[first.start, second.end], radius=0.6 * sharp)
                if _line_error(path, merged, [first.start, second.end], 0.6 * sharp) <= tolerance:
                    if profile.closed and k == count - 1:
                        segments[:] = [merged] + segments[1:-1]
                    else:
                        segments[k : k + 2] = [merged]
                    continue
        k += 1


def _line_error(path: np.ndarray, segment: Segment2D, exclude: list[np.ndarray], radius: float) -> float:
    points = _line_points(path, segment, exclude, radius)
    direction = _unit(segment.end - segment.start)
    normal = np.array([-direction[1], direction[0]])
    return float(np.max(np.abs((points - segment.start) @ normal)))


def _line_points(path: np.ndarray, segment: Segment2D, exclude: list[np.ndarray] | None, radius: float) -> np.ndarray:
    """A line's samples, without those within ``radius`` of the given corners (if 3 remain)."""

    start, end = _indices(segment)
    points = _points(path, start, end, True) if end >= len(path) else path[start : end + 1]
    if exclude:
        near = np.zeros(len(points), dtype=bool)
        for corner in exclude:
            near |= np.linalg.norm(points - corner, axis=1) <= radius
        if int((~near).sum()) >= 3:
            points = points[~near]
    return points


def _trim_corners(
    profile: Profile2D, path: np.ndarray, snap_degrees: float, tolerance: float, sharp: float, corner_degrees: float
) -> bool:
    """Refit the lines at sharp corners without the samples the scan rounded off there.

    Within about ``sharp`` of a sharp corner the samples cut the corner; a short line
    (a 2 mm step) fitted through them tilts. Returns whether anything changed.
    """

    segments = profile.segments
    count = len(segments)
    corners: dict[int, list[np.ndarray]] = {}
    for k in range(count if profile.closed else count - 1):
        first, second = segments[k], segments[(k + 1) % count]
        if first.kind != "line" or second.kind != "line":
            continue
        d0, d1 = _unit(first.end - first.start), _unit(second.end - second.start)
        if math.degrees(math.acos(float(np.clip(d0 @ d1, -1.0, 1.0)))) >= corner_degrees:
            corners.setdefault(k, []).append(first.end)
            corners.setdefault((k + 1) % count, []).append(second.start)
    changed = False
    for k, points in corners.items():
        before = (segments[k].start.copy(), segments[k].end.copy())
        _finish(path, segments[k], snap_degrees, tolerance, exclude=points, radius=0.6 * sharp)
        changed = changed or not (np.allclose(before[0], segments[k].start) and np.allclose(before[1], segments[k].end))
    return changed


def _finish(
    path: np.ndarray,
    segment: Segment2D,
    snap_degrees: float,
    tolerance: float,
    exclude: list[np.ndarray] | None = None,
    radius: float = 0.0,
) -> Segment2D:
    """A line through its own samples (optionally without those near given corners):
    exactly horizontal/vertical when within ``snap_degrees`` and that still fits within the
    tolerance, else a least-squares line with the stray samples trimmed.

    Growth lets a line run a little into the rounding beyond it (while within the
    tolerance), so its end samples are biased inward: a snapped line's offset is the median
    of its samples, never the end samples.
    """

    if segment.kind != "line":
        return segment
    start, end = _indices(segment)
    every = _points(path, start, end, True) if end >= len(path) else path[start : end + 1]
    span = (every[0].copy(), every[-1].copy())  # the line's extent
    points = _line_points(path, segment, exclude, radius)
    point, direction, _error = fit_line_2d(points)
    if direction @ (span[1] - span[0]) < 0:
        direction = -direction
    normal = np.array([-direction[1], direction[0]])
    residual = np.abs((points - point) @ normal)
    spread = 1.4826 * float(np.median(residual))
    keep = residual <= max(3.0 * spread, 1e-12)
    if 2 <= int(keep.sum()) < len(points):
        points = points[keep]
        point, refit, _error = fit_line_2d(points)
        direction = refit if refit @ direction >= 0 else -refit
    angle = math.degrees(math.atan2(direction[1], direction[0])) % 180.0
    for target in (0.0, 90.0, 180.0):
        if abs(angle - target) <= snap_degrees:
            exact = np.array([1.0, 0.0]) if target != 90.0 else np.array([0.0, 1.0])
            exact = exact if exact @ direction >= 0 else -exact
            exact_normal = np.array([-exact[1], exact[0]])
            offset = float(np.median(points @ exact_normal))
            if float(np.max(np.abs(points @ exact_normal - offset))) <= tolerance:
                direction = exact
                point = exact_normal * offset + exact * float(np.median(points @ exact))
            break
    segment.start = point + direction * ((span[0] - point) @ direction)
    segment.end = point + direction * ((span[1] - point) @ direction)
    return segment


def _join(profile: Profile2D, path: np.ndarray, corner_degrees: float) -> None:
    """Exact shared end points between neighbouring segments.

    At a corner (the pieces' directions differ by ``corner_degrees`` or more) the point is
    where they intersect. Where an arc runs smoothly on into the next piece the intersection
    of the two (nearly tangent) curves can lie far along; there the point is the sample where
    one piece hands over to the other (on the line, if one is a line), and arcs are refitted
    through it.
    """

    segments = profile.segments
    count = len(segments)
    if count == 1 and profile.closed and segments[0].kind == "arc" and segments[0].center is not None:
        circle = segments[0]  # a full circle: start = end, on the circle
        assert circle.center is not None
        point = circle.center + _unit(path[0] - circle.center) * circle.radius
        circle.start, circle.end = point.copy(), point.copy()
        return
    pairs = range(count if profile.closed else count - 1)
    for k in pairs:
        first, second = segments[k], segments[(k + 1) % count]
        guess = 0.5 * (first.end + second.start)
        across_gap = profile.gap > 0.0 and k == count - 1
        if across_gap:
            point = _junction(first, second, guess, reach=0.5)
        elif "arc" in (first.kind, second.kind) and _turn(first, second) < corner_degrees:
            point = _handover(path, first, profile.closed)
            if first.kind == "line" or second.kind == "line":
                line = first if first.kind == "line" else second
                direction = _unit(line.end - line.start)
                point = line.start + direction * ((point - line.start) @ direction)
        else:
            point = _junction(first, second, guess)
        first.end = point.copy()
        second.start = point.copy()
    for segment in segments:  # arcs: through their (shared, exact) end points
        if segment.kind == "arc" and segment.center is not None:
            _arc_through_ends(segment, path, profile.closed)


def _tangent(segment: Segment2D, at_end: bool) -> np.ndarray:
    """Unit direction of travel at the start or end of a segment."""

    if segment.kind == "line" or segment.center is None:
        return _unit(segment.end - segment.start)
    radial = _unit((segment.end if at_end else segment.start) - segment.center)
    across = np.array([-radial[1], radial[0]])  # counter-clockwise travel
    return across if segment.ccw else -across


def _turn(first: Segment2D, second: Segment2D) -> float:
    """Degrees between the direction leaving ``first`` and the one entering ``second``."""

    cosine = float(np.clip(_tangent(first, True) @ _tangent(second, False), -1.0, 1.0))
    return math.degrees(math.acos(cosine))


def _handover(path: np.ndarray, first: Segment2D, closed: bool) -> np.ndarray:
    """The sample where ``first`` ends (averaged with its neighbours against noise)."""

    n = len(path)
    index = _indices(first)[1]
    around = np.arange(index - 1, index + 2)
    around = around % n if closed else np.clip(around, 0, n - 1)
    return path[around].mean(axis=0)


def _arc_through_ends(arc: Segment2D, path: np.ndarray, closed: bool) -> None:
    """Refit an arc whose end points are off its circle as the best circle through them.

    Where two circles do not meet (or a line misses a circle), the shared point cannot be on
    both; moving each end onto its own circle would open a gap. Instead the center slides
    along the chord's perpendicular bisector to fit the arc's samples best.
    """

    assert arc.center is not None
    off = max(abs(float(np.linalg.norm(end - arc.center)) - arc.radius) for end in (arc.start, arc.end))
    chord = arc.end - arc.start
    length = float(np.linalg.norm(chord))
    if off <= 1e-9 * max(arc.radius, 1.0) or length < 1e-12:
        return
    from scipy.optimize import minimize_scalar

    middle = 0.5 * (arc.start + arc.end)
    across = np.array([-chord[1], chord[0]]) / length
    start, end = _indices(arc)
    points = _points(path, start, end if end >= start else end + len(path), closed)

    def cost(t: float) -> float:
        center = middle + across * t
        return float(np.sum((np.linalg.norm(points - center, axis=1) - np.linalg.norm(arc.start - center)) ** 2))

    t0 = float((arc.center - middle) @ across)
    result = minimize_scalar(cost, bracket=(t0 - 0.1 * arc.radius, t0 + 0.1 * arc.radius))
    arc.center = middle + across * float(result.x)
    arc.radius = float(np.linalg.norm(arc.start - arc.center))


def _junction(first: Segment2D, second: Segment2D, guess: np.ndarray, reach: float = 0.25) -> np.ndarray:
    candidates: list[np.ndarray] = []
    if first.kind == "line" and second.kind == "line":
        hit = _line_line(first.start, first.end - first.start, second.start, second.end - second.start)
        if hit is not None:
            candidates.append(hit)
    elif first.kind == "line" or second.kind == "line":
        line, arc = (first, second) if first.kind == "line" else (second, first)
        assert arc.center is not None
        candidates.extend(_line_circle(line.start, line.end - line.start, arc.center, arc.radius))
        if not candidates:  # tangent (or just missing): the foot of the center on the line
            direction = (line.end - line.start) / max(float(np.linalg.norm(line.end - line.start)), 1e-15)
            candidates.append(line.start + direction * ((arc.center - line.start) @ direction))
    else:
        assert first.center is not None and second.center is not None
        candidates.extend(_circle_circle(first.center, first.radius, second.center, second.radius))
        if not candidates:  # the circles miss: halfway between their closest points
            unit = _unit(second.center - first.center)
            pairs = [
                (first.center + a * unit * first.radius, second.center + b * unit * second.radius)
                for a in (-1.0, 1.0)
                for b in (-1.0, 1.0)
            ]
            near, far = min(pairs, key=lambda pair: float(np.linalg.norm(pair[0] - pair[1])))
            candidates.append(0.5 * (near + far))
    if not candidates:  # parallel lines: no intersection
        return guess
    best = min(candidates, key=lambda point: float(np.linalg.norm(point - guess)))
    # an intersection far from where the outline actually turns is spurious (nearly parallel)
    limit = reach * max(first.length, second.length, 1e-9)
    return best if float(np.linalg.norm(best - guess)) <= limit else guess


def _cross(a: np.ndarray, b: np.ndarray) -> float:
    return float(a[0] * b[1] - a[1] * b[0])


def _line_line(p: np.ndarray, r: np.ndarray, q: np.ndarray, s: np.ndarray) -> np.ndarray | None:
    denominator = r[0] * s[1] - r[1] * s[0]
    if abs(denominator) < 1e-12 * max(float(np.linalg.norm(r) * np.linalg.norm(s)), 1e-30):
        return None
    t = ((q - p)[0] * s[1] - (q - p)[1] * s[0]) / denominator
    return p + t * r


def _line_circle(p: np.ndarray, r: np.ndarray, center: np.ndarray, radius: float) -> list[np.ndarray]:
    a = float(r @ r)
    b = 2.0 * float(r @ (p - center))
    c = float((p - center) @ (p - center)) - radius * radius
    disc = b * b - 4 * a * c
    if a < 1e-30 or disc < -1e-9 * max(b * b, 1e-30):
        return []
    root = math.sqrt(max(disc, 0.0))
    return [p + r * ((-b - root) / (2 * a)), p + r * ((-b + root) / (2 * a))]


def _circle_circle(c0: np.ndarray, r0: float, c1: np.ndarray, r1: float) -> list[np.ndarray]:
    gap = c1 - c0
    d = float(np.linalg.norm(gap))
    if d < 1e-12 or d > r0 + r1 or d < abs(r0 - r1):
        return []
    a = (r0 * r0 - r1 * r1 + d * d) / (2 * d)
    h = math.sqrt(max(r0 * r0 - a * a, 0.0))
    base = c0 + gap * (a / d)
    perpendicular = np.array([-gap[1], gap[0]]) / d
    return [base + perpendicular * h, base - perpendicular * h]


__all__ = (
    "Profile2D",
    "Segment2D",
    "auto_tolerance",
    "estimate_noise",
    "fit_circle_2d",
    "fit_line_2d",
    "fit_profile",
    "segment_distances",
)
