"""Profiles of a constrained sketch (P-04): the closed regions its curves enclose.

The sketch's lines and arcs (not construction geometry) form a network joined at their end
points; points held together by a coincident constraint count as one. Each region of the
plane the network encloses is a profile, found by walking the network with the region on
the left. Circles are regions of their own. A region inside another is an island: the outer
region is the plate minus the island, and the island is a region too.

Regions are named by the curves around them (``Region.key``), which survive a dimension
change, so an extrude keeps the region it was made from when the sketch is edited.

Loops come out in the profile format of ``modeling.profile2d`` (exact lines and arcs, with
an outline for nesting), the same that Section Sketch makes, so the kernel's profile and
extrude jobs take them as they are.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from openretop.cad_kernel.profiles import interior_point, point_in_outline
from openretop.modeling.profile2d import Profile2D, Segment2D
from openretop.modeling.sketch2d import Arc, Circle, Line, Sketch2D


@dataclass
class Region:
    key: str  # the ids of the curves around it, sorted: stable through dimension changes
    outer: Profile2D
    holes: list[Profile2D] = field(default_factory=list)
    area: float = 0.0  # the outer loop's area (islands not taken off)
    parent: str | None = None  # the key of the region it is an island in
    children: list[str] = field(default_factory=list)

    def contains(self, point: object) -> bool:
        if not point_in_outline(point, self.outer.polyline(16)):
            return False
        return not any(point_in_outline(point, hole.polyline(16)) for hole in self.holes)


@dataclass
class SketchProfiles:
    regions: list[Region]
    open_chains: list[Profile2D]  # curves that enclose nothing (shown as wires)

    def region(self, key: str) -> Region | None:
        return next((region for region in self.regions if region.key == key), None)

    def region_at(self, point: object) -> Region | None:
        """The region a click on the plane at ``point`` (2D) picks: the innermost one."""

        hits = [region for region in self.regions if region.contains(point)]
        return min(hits, key=lambda region: region.area) if hits else None

    def all_loops(self) -> list[dict[str, object]]:
        """Every loop (closed ones nest by containment: outer, hole, island ...) and the open
        chains: the sketch as the profile entity shows it and extrudes it all."""

        return [region.outer.to_dict() for region in self.regions] + [chain.to_dict() for chain in self.open_chains]

    def loops_for(self, keys: list[str]) -> list[dict[str, object]] | None:
        """Loops that extrude just the picked regions (None if a picked region is gone).

        A picked region whose island is picked too is filled there; an island not picked
        stays a hole."""

        picked = set(keys)
        if not picked or any(self.region(key) is None for key in picked):
            return None
        loops: list[dict[str, object]] = []

        def holes_of(region: Region) -> None:
            for child_key in region.children:
                child = self.region(child_key)
                assert child is not None
                if child.key in picked:
                    holes_of(child)  # filled: its own unpicked islands are holes
                else:
                    loops.append(child.outer.to_dict())

        for region in self.regions:
            if region.key in picked and region.parent not in picked:
                loops.append(region.outer.to_dict())
                holes_of(region)
        return loops


def find_profiles(sketch: Sketch2D) -> SketchProfiles:
    """The sketch's regions and open chains."""

    node = _merged_points(sketch)
    position = {key: sketch.position(key) for key in sketch.points}
    edges: list[tuple[str, str, str]] = []  # (curve, from node, to node)
    circles: list[Circle] = []
    for curve_id, curve in sketch.curves.items():
        if curve.construction:
            continue
        if isinstance(curve, Circle):
            circles.append(curve)
        elif isinstance(curve, Line):
            if node[curve.p1] != node[curve.p2]:
                edges.append((curve_id, node[curve.p1], node[curve.p2]))
        elif isinstance(curve, Arc):
            if node[curve.start] != node[curve.end]:
                edges.append((curve_id, node[curve.start], node[curve.end]))
    # dangling curves (an end that meets nothing) enclose nothing: peel them off
    hanging: list[tuple[str, str, str]] = []
    while True:
        degree: dict[str, int] = {}
        for _curve, a, b in edges:
            degree[a] = degree.get(a, 0) + 1
            degree[b] = degree.get(b, 0) + 1
        loose = [edge for edge in edges if degree[edge[1]] == 1 or degree[edge[2]] == 1]
        if not loose:
            break
        hanging.extend(loose)
        edges = [edge for edge in edges if edge not in loose]
    node_position = {node[key]: position[key] for key in sketch.points}
    cycles = _faces(sketch, edges, node, node_position)
    loops: list[tuple[str, Profile2D, float]] = []
    for cycle in cycles:
        profile = _profile(sketch, cycle, node, node_position)
        area = _area(profile.polyline(16))
        if area > 1e-12:  # the region on the left of a counter-clockwise walk
            loops.append(("|".join(sorted({curve for curve, _forward in cycle})), profile, area))
    for circle in circles:
        center = sketch.position(circle.center)
        start = center + np.array([circle.radius, 0.0])
        segment = Segment2D("arc", start.copy(), start.copy(), center=center, radius=float(circle.radius), ccw=True)
        loops.append((circle.id, Profile2D([segment], closed=True), math.pi * circle.radius**2))
    regions = [Region(key, profile, area=area) for key, profile, area in loops]
    _nest(regions)
    open_chains = [_profile(sketch, [(curve, True)], node, node_position, closed=False) for curve, _a, _b in hanging]
    return SketchProfiles(regions, open_chains)


def _merged_points(sketch: Sketch2D) -> dict[str, str]:
    """Each point's representative: points joined by a coincident constraint, or lying on
    each other, are one node of the network."""

    parent = {key: key for key in sketch.points}

    def find(key: str) -> str:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for constraint in sketch.constraints:
        if constraint.kind == "coincident" and len(constraint.refs) == 2 and all(ref in sketch.points for ref in constraint.refs):
            union(*constraint.refs)
    keys = list(sketch.points)
    if keys:
        xy = np.asarray([sketch.position(key) for key in keys])
        size = max(float(np.max(np.ptp(xy, axis=0))), 1e-9) if len(xy) > 1 else 1.0
        tolerance = 1e-9 * size
        order = np.argsort(xy[:, 0])
        for i, first in enumerate(order):
            for second in order[i + 1 :]:
                if xy[second, 0] - xy[first, 0] > tolerance:
                    break
                if abs(xy[second, 1] - xy[first, 1]) <= tolerance:
                    union(keys[first], keys[second])
    return {key: find(key) for key in keys}


def _leaving(sketch: Sketch2D, curve_id: str, forward: bool) -> np.ndarray:
    """A point a little way along the curve from the end it is walked from: its direction
    there orders the curves around a node (and tells tangent ones apart by their bend)."""

    segment = _segment(sketch, curve_id, forward)
    if segment.kind == "line":
        return segment.start + (segment.end - segment.start) * 1e-3
    a0, sweep = segment.angles()
    angle = a0 + sweep * 1e-3
    assert segment.center is not None
    return segment.center + segment.radius * np.array([math.cos(angle), math.sin(angle)])


def _faces(sketch: Sketch2D, edges: list[tuple[str, str, str]], node: dict[str, str], position: dict[str, np.ndarray]) -> list[list[tuple[str, bool]]]:
    """Walk the network: each walk keeps one face on its left (the next curve at a node is
    the first one clockwise from the curve just arrived by)."""

    outgoing: dict[str, list[tuple[float, str, bool]]] = {}
    for curve, a, b in edges:
        for start, forward in ((a, True), (b, False)):
            direction = _leaving(sketch, curve, forward) - position[start]
            outgoing.setdefault(start, []).append((math.atan2(direction[1], direction[0]), curve, forward))
    for items in outgoing.values():
        items.sort()
    ends = {curve: (a, b) for curve, a, b in edges}
    used: set[tuple[str, bool]] = set()
    cycles = []
    for curve, _a, _b in edges:
        for forward in (True, False):
            if (curve, forward) in used:
                continue
            cycle = []
            current = (curve, forward)
            while current not in used:
                used.add(current)
                cycle.append(current)
                name, way = current
                arrive = ends[name][1] if way else ends[name][0]
                around = outgoing[arrive]
                back = next(index for index, (_angle, other, other_way) in enumerate(around) if other == name and other_way != way)
                _angle, next_curve, next_way = around[(back - 1) % len(around)]
                current = (next_curve, next_way)
            cycles.append(cycle)
    return cycles


def _segment(sketch: Sketch2D, curve_id: str, forward: bool) -> Segment2D:
    curve = sketch.curves[curve_id]
    if isinstance(curve, Line):
        a, b = sketch.position(curve.p1), sketch.position(curve.p2)
        return Segment2D("line", a, b) if forward else Segment2D("line", b, a)
    assert isinstance(curve, Arc)
    center = sketch.position(curve.center)
    start, end = sketch.position(curve.start), sketch.position(curve.end)
    radius = float(np.linalg.norm(start - center))
    end = center + (end - center) * (radius / max(float(np.linalg.norm(end - center)), 1e-15))
    if forward:
        return Segment2D("arc", start, end, center=center, radius=radius, ccw=True)
    return Segment2D("arc", end, start, center=center, radius=radius, ccw=False)


def _profile(sketch: Sketch2D, cycle: list[tuple[str, bool]], node: dict[str, str], position: dict[str, np.ndarray], *, closed: bool = True) -> Profile2D:
    segments = [_segment(sketch, curve, forward) for curve, forward in cycle]
    if closed:
        # consecutive segments meet exactly (merged points may differ by a hair)
        for index, segment in enumerate(segments):
            following = segments[(index + 1) % len(segments)]
            segment.end = following.start.copy()
    return Profile2D(segments, closed=closed)


def _area(outline: np.ndarray) -> float:
    if len(outline) < 3:
        return 0.0
    following = np.roll(outline, -1, axis=0)
    return 0.5 * float(np.sum(outline[:, 0] * following[:, 1] - following[:, 0] * outline[:, 1]))


def _nest(regions: list[Region]) -> None:
    """Each region's parent is the smallest region it lies inside; its children are holes."""

    outlines = {region.key: region.outer.polyline(16) for region in regions}
    probes = {region.key: interior_point(outlines[region.key]) for region in regions}
    for region in regions:
        containers = [
            other
            for other in regions
            if other is not region and other.area > region.area and point_in_outline(probes[region.key], outlines[other.key])
        ]
        if containers:
            parent = min(containers, key=lambda other: other.area)
            region.parent = parent.key
            parent.children.append(region.key)
            parent.holes.append(region.outer)


__all__ = ("Region", "SketchProfiles", "find_profiles")
