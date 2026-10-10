"""3D Sketch (P-03): drawing a constrained sketch on a plane through the scan.

The Solid workspace's sketch tool. Geometry is drawn on a plane (XY, XZ or YZ at an offset,
the scan's cut there shown for reference), held by constraints and dimensions, and solved by
``modeling.sketch2d`` as it is edited. This module is the tool's state and logic, free of Qt
and of the kernel; ``ModelingController`` wraps it with undo and makes the finished sketch
a history feature.

Drawing works as in Fusion 360:

- Line: click, click, ... (a chain); click its first point to close it; Enter or Esc ends it.
  A line drawn within 3 degrees of horizontal or vertical is constrained so.
- Rectangle: two corners. Circle: centre, then a point on it. Arc: centre, start, end
  (counter-clockwise).
- A click near an existing point uses that point (the curves are joined); near a curve, the
  new point is constrained onto it.

Constraints and dimensions apply to the selection (points and curves, picked in Select);
the dimension's kind follows from what is picked (a line: its length; two points: their
distance; a point and a line: the distance between them; two lines: their angle, or their
distance when parallel; a circle: its diameter; an arc: its radius).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from openretop.modeling.sketch2d import DIMENSIONS, GEOMETRIC, Arc, Circle, Constraint, Line, Sketch2D, SolveReport

DRAW_TOOLS = ("select", "line", "rectangle", "circle", "arc")
# the sketch planes (Section Sketch uses the same): name -> (in-plane u, in-plane v, the world
# axis the offset runs along)
PLANES = {
    "XY": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    "YZ": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
    "XZ": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
}
AXIS_SNAP_DEGREES = 3.0
# short marks for the constraints drawn beside the geometry
GLYPHS = {
    "horizontal": "H",
    "vertical": "V",
    "parallel": "//",
    "perpendicular": "90°",
    "tangent": "T",
    "equal": "=",
    "concentric": "O",
    "midpoint": "M",
    "symmetric": "S",
    "collinear": "C",
    "fix": "F",
}
_SHAPE_ORDER = {"P": 0, "L": 1, "C": 2}


@dataclass
class SketchMode:
    sketch: Sketch2D = field(default_factory=Sketch2D)
    plane: str = "XY"
    offset: float = 0.0
    tool: str = "line"
    pending: list[str] = field(default_factory=list)  # points placed for the shape being drawn
    chain_start: str | None = None  # the first point of the line chain being drawn
    hover: np.ndarray | None = None  # the pointer on the plane (2D), for the rubber band
    selected: list[str] = field(default_factory=list)  # points and curves
    editing: str = ""  # the sketch entity being edited: Finish updates it

    # -- the plane ----------------------------------------------------------------------------

    def frame(self) -> dict[str, list[float]]:
        u, v, axis = (np.asarray(value, dtype=float) for value in PLANES[self.plane])
        return {"origin": (axis * self.offset).tolist(), "u": u.tolist(), "v": v.tolist()}

    def to_plane(self, world: object) -> np.ndarray:
        frame = self.frame()
        local = np.asarray(world, dtype=float).reshape(3) - np.asarray(frame["origin"])
        return np.array([float(local @ np.asarray(frame["u"])), float(local @ np.asarray(frame["v"]))])

    def to_world(self, points: object) -> np.ndarray:
        frame = self.frame()
        values = np.asarray(points, dtype=float).reshape(-1, 2)
        return np.asarray(frame["origin"]) + values[:, :1] * np.asarray(frame["u"]) + values[:, 1:2] * np.asarray(frame["v"])

    # -- picking ------------------------------------------------------------------------------

    def nearest_point(self, xy: object, radius: float) -> str | None:
        target = np.asarray(xy, dtype=float)
        best, distance = None, radius
        for point_id in self.sketch.points:
            gap = float(np.linalg.norm(self.sketch.position(point_id) - target))
            if gap <= distance:
                best, distance = point_id, gap
        return best

    def nearest_curve(self, xy: object, radius: float) -> str | None:
        target = np.asarray(xy, dtype=float)
        best, distance = None, radius
        for curve_id in self.sketch.curves:
            gap = _distance_to_polyline(self.curve_polyline(curve_id), target)
            if gap <= distance:
                best, distance = curve_id, gap
        return best

    def curve_polyline(self, curve_id: str, samples: int = 64) -> np.ndarray:
        sketch = self.sketch
        curve = sketch.curves[curve_id]
        if isinstance(curve, Line):
            a, b = sketch.position(curve.p1), sketch.position(curve.p2)
            t = np.linspace(0.0, 1.0, max(2, samples // 8))[:, None]
            return a + (b - a) * t
        center = sketch.position(curve.center)
        radius = sketch.radius(curve_id)
        if isinstance(curve, Circle):
            angles = np.linspace(0.0, 2 * math.pi, samples + 1)
        else:
            assert isinstance(curve, Arc)
            start, end = sketch.position(curve.start) - center, sketch.position(curve.end) - center
            a0, a1 = math.atan2(start[1], start[0]), math.atan2(end[1], end[0])
            sweep = (a1 - a0) % (2 * math.pi) or 2 * math.pi
            angles = a0 + np.linspace(0.0, sweep, max(4, int(samples * sweep / (2 * math.pi)) + 2))
        return center + radius * np.c_[np.cos(angles), np.sin(angles)]

    # -- drawing ------------------------------------------------------------------------------

    def set_tool(self, tool: str) -> None:
        if tool not in DRAW_TOOLS:
            raise ValueError(f"unknown sketch tool: {tool}")
        self.end_shape()
        self.tool = tool

    def end_shape(self) -> None:
        """Stop the shape being drawn (a line chain stays as drawn)."""

        self.pending.clear()
        self.chain_start = None

    def click(self, xy: object, radius: float, *, add: bool = False) -> str:
        """A click on the plane at ``xy``; ``radius`` is the snapping distance. Returns what
        happened, for the status line."""

        xy = np.asarray(xy, dtype=float).reshape(2)
        if self.tool == "select":
            return self._select(xy, radius, add=add)
        snapped = self.nearest_point(xy, radius)
        if self.tool == "line":
            return self._line_click(xy, snapped, radius)
        if self.tool == "rectangle":
            if not self.pending:
                self.pending.append(self._place(xy, snapped, radius))
                return "Rectangle: click the opposite corner"
            corner = self.sketch.position(self.pending[0])
            if np.allclose(corner, xy):
                return "Rectangle: click a corner away from the first"
            first = self.pending[0]
            lines = self.sketch.add_rectangle(tuple(corner), tuple(xy))  # type: ignore[arg-type]
            # the first corner the user clicked (possibly an existing point) is the rectangle's
            self._merge_point(self.sketch.curves[lines[0]].p1, first)  # type: ignore[union-attr]
            self.end_shape()
            self.sketch.solve()
            return "Rectangle drawn"
        if self.tool == "circle":
            if not self.pending:
                self.pending.append(self._place(xy, snapped, radius))
                return "Circle: click a point on it"
            center = self.pending[0]
            size = float(np.linalg.norm(xy - self.sketch.position(center)))
            if size <= 1e-9:
                return "Circle: click away from the centre"
            self.sketch.add_circle(center, size)
            self.end_shape()
            return "Circle drawn"
        if self.tool == "arc":
            if len(self.pending) < 2:
                if self.pending and np.allclose(self.sketch.position(self.pending[0]), xy):
                    return "Arc: click away from the centre"
                self.pending.append(self._place(xy, snapped, radius))
                return "Arc: click its start" if len(self.pending) == 1 else "Arc: click its end (counter-clockwise)"
            center, start = self.pending
            end = snapped if snapped not in (None, center, start) else self.sketch.add_point(*xy)
            self.sketch.add_arc(center, start, end)
            self.end_shape()
            self.sketch.solve()
            return "Arc drawn"
        raise ValueError(self.tool)

    def _line_click(self, xy: np.ndarray, snapped: str | None, radius: float) -> str:
        if not self.pending:
            point = self._place(xy, snapped, radius)
            self.pending.append(point)
            self.chain_start = point
            return "Line: click the next point (its first point closes the shape; Enter ends)"
        last = self.pending[-1]
        if snapped == last:
            return "Line: click away from the last point"
        end = self._place(xy, snapped, radius)
        line = self.sketch.add_line(last, end)
        direction = self.sketch.position(end) - self.sketch.position(last)
        angle = math.degrees(math.atan2(abs(direction[1]), abs(direction[0])))
        if angle <= AXIS_SNAP_DEGREES:
            self.sketch.constrain("horizontal", line)
        elif angle >= 90.0 - AXIS_SNAP_DEGREES:
            self.sketch.constrain("vertical", line)
        if end == self.chain_start:
            self.end_shape()
            return "Shape closed"
        self.pending.append(end)
        return "Line drawn: click the next point"

    def _place(self, xy: np.ndarray, snapped: str | None, radius: float) -> str:
        """The point a click places: an existing one if it was clicked, else a new point,
        held on the curve it was clicked on (if any)."""

        if snapped is not None:
            return snapped
        point = self.sketch.add_point(*xy)
        curve = self.nearest_curve(xy, radius)
        if curve is not None and curve not in self._curves_at(point):
            self.sketch.constrain("coincident", point, curve)
        return point

    def _curves_at(self, point_id: str) -> set[str]:
        return {curve_id for curve_id in self.sketch.curves if point_id in self.sketch.curve_points(curve_id)}

    def _merge_point(self, keep: str, into: str) -> None:
        """Replace point ``keep`` by ``into`` in the curves and constraints (``into`` takes its place)."""

        if keep == into:
            return
        for curve in self.sketch.curves.values():
            for attribute in ("p1", "p2", "center", "start", "end"):
                if getattr(curve, attribute, None) == keep:
                    setattr(curve, attribute, into)
        for constraint in self.sketch.constraints:
            constraint.refs = tuple(into if ref == keep else ref for ref in constraint.refs)
        del self.sketch.points[keep]

    # -- selection ----------------------------------------------------------------------------

    def _select(self, xy: np.ndarray, radius: float, *, add: bool) -> str:
        hit = self.nearest_point(xy, radius) or self.nearest_curve(xy, radius)
        if hit is None:
            if not add:
                self.selected.clear()
            return "Nothing there" if add else "Selection cleared"
        if add:
            if hit in self.selected:
                self.selected.remove(hit)
            else:
                self.selected.append(hit)
        else:
            self.selected = [hit]
        return f"{len(self.selected)} selected"

    def select(self, ids: list[str]) -> None:
        self.selected = [value for value in ids if value in self.sketch.points or value in self.sketch.curves]

    # -- constraints and dimensions -----------------------------------------------------------

    def ordered_selection(self) -> tuple[str, ...]:
        """The selection as a constraint takes it: points, then lines, then circles and arcs."""

        return tuple(sorted(self.selected, key=lambda ref: _SHAPE_ORDER[self.sketch._shape(ref)]))

    def available(self) -> list[str]:
        """The constraints that fit the selection (for enabling the panel's buttons)."""

        refs = self.ordered_selection()
        result = []
        for kind in GEOMETRIC:
            try:
                self.sketch._check_refs(Constraint("check", kind, refs))
            except (ValueError, KeyError):
                continue
            result.append(kind)
        if self.dimension_kind(refs) is not None:
            result.append("dimension")
        return result

    def constrain(self, kind: str) -> SolveReport:
        refs = self.ordered_selection()
        try:
            return self.sketch.constrain(kind, *refs)
        except (ValueError, KeyError) as error:
            return SolveReport(False, str(error))

    def dimension_kind(self, refs: tuple[str, ...] | None = None) -> str | None:
        refs = self.ordered_selection() if refs is None else refs
        shapes = tuple(self.sketch._shape(ref) for ref in refs)
        if shapes in (("L",), ("P", "P"), ("P", "L")):
            return "distance"
        if shapes == ("L", "L"):
            u = [np.subtract(*reversed([self.sketch.position(p) for p in self.sketch.curve_points(ref)])) for ref in refs]
            cross = abs(u[0][0] * u[1][1] - u[0][1] * u[1][0]) / max(float(np.linalg.norm(u[0]) * np.linalg.norm(u[1])), 1e-15)
            return "distance" if cross < 1e-6 else "angle"
        if shapes == ("C",):
            return "diameter" if isinstance(self.sketch.curves[refs[0]], Circle) else "radius"
        return None

    def dimension(self, value: float | None = None, kind: str | None = None) -> SolveReport:
        """Dimension the selection; ``kind`` overrides the one it implies (two points:
        "horizontal_distance" or "vertical_distance")."""

        refs = self.ordered_selection()
        implied = self.dimension_kind(refs)
        if kind is not None and implied is not None and kind in ("horizontal_distance", "vertical_distance"):
            if tuple(self.sketch._shape(ref) for ref in refs) != ("P", "P"):
                return SolveReport(False, "Horizontal and vertical distances are between two points")
            implied = kind
        kind = implied
        if kind is None:
            return SolveReport(False, "Select a line, two points, a point and a line, two lines, or a circle or arc to dimension")
        return self.sketch.constrain(kind, *refs, value=value)

    def set_dimension(self, constraint_id: str, value: float) -> SolveReport:
        try:
            return self.sketch.set_value(constraint_id, value)
        except (KeyError, ValueError) as error:
            return SolveReport(False, str(error).strip("'\""))

    def delete_constraint(self, constraint_id: str) -> None:
        self.sketch.remove_constraint(constraint_id)

    def delete_selected(self) -> int:
        count = 0
        for item in list(self.selected):
            if item in self.sketch.curves or item in self.sketch.points:
                self.sketch.delete(item)
                count += 1
        self.selected.clear()
        self.pending = [point for point in self.pending if point in self.sketch.points]
        return count

    def toggle_construction(self) -> int:
        curves = [self.sketch.curves[item] for item in self.selected if item in self.sketch.curves]
        for curve in curves:
            curve.construction = not curve.construction
        return len(curves)

    def drag(self, point_id: str, xy: object) -> SolveReport:
        return self.sketch.drag(point_id, (float(np.asarray(xy)[0]), float(np.asarray(xy)[1])))

    # -- what to draw -------------------------------------------------------------------------

    def view(self) -> dict[str, Any]:
        """Everything the viewport shows of the sketch, in plane coordinates."""

        sketch = self.sketch
        defined = sketch.fully_defined()
        curves = [
            {
                "id": curve_id,
                "points": self.curve_polyline(curve_id),
                "construction": curve.construction,
                "selected": curve_id in self.selected,
                "defined": curve_id in defined,
            }
            for curve_id, curve in sketch.curves.items()
        ]
        points = [
            {"id": point_id, "xy": sketch.position(point_id), "selected": point_id in self.selected, "defined": point_id in defined}
            for point_id in sketch.points
        ]
        labels = []
        for constraint in sketch.constraints:
            anchor = self._anchor(constraint)
            if anchor is None:
                continue
            if constraint.kind in DIMENSIONS:
                labels.append({"id": constraint.id, "xy": anchor, "text": self.dimension_text(constraint), "dimension": True, "driving": constraint.driving})
            elif constraint.kind in GLYPHS:
                labels.append({"id": constraint.id, "xy": anchor, "text": GLYPHS[constraint.kind], "dimension": False, "driving": True})
        dof = sketch.dof()
        return {
            "curves": curves,
            "points": points,
            "labels": labels,
            "preview": self.rubber_band(),
            "dof": dof,
            "defined": dof == 0 and bool(sketch.points),
        }

    def dimension_text(self, constraint: Constraint) -> str:
        value = self.sketch.measure(constraint) if not constraint.driving else float(constraint.value or 0.0)
        if constraint.kind == "angle":
            return f"{abs(value):.1f}°"
        prefix = {"radius": "R", "diameter": "Ø"}.get(constraint.kind, "")
        text = f"{prefix}{value:.3f}".rstrip("0").rstrip(".")
        return text if constraint.driving else f"({text})"

    def _anchor(self, constraint: Constraint) -> np.ndarray | None:
        sketch = self.sketch
        refs = [ref for ref in constraint.refs if ref in sketch.points or ref in sketch.curves]
        if not refs:
            return None
        anchors = []
        for ref in refs:
            if ref in sketch.points:
                anchors.append(sketch.position(ref))
                continue
            curve = sketch.curves[ref]
            if isinstance(curve, Line):
                anchors.append(0.5 * (sketch.position(curve.p1) + sketch.position(curve.p2)))
            elif isinstance(curve, Circle):  # on the circle, up and to the right
                anchors.append(sketch.position(curve.center) + curve.radius * np.array([math.sqrt(0.5), math.sqrt(0.5)]))
            else:
                polyline = self.curve_polyline(ref, 16)
                anchors.append(polyline[len(polyline) // 2])
        return np.mean(anchors, axis=0)

    def rubber_band(self) -> np.ndarray | None:
        """The shape being drawn, from the points placed to the pointer."""

        if self.hover is None or not self.pending:
            return None
        sketch = self.sketch
        first = sketch.position(self.pending[0])
        hover = self.hover
        if self.tool == "line":
            return np.vstack([sketch.position(self.pending[-1]), hover])
        if self.tool == "rectangle":
            return np.array([first, [hover[0], first[1]], hover, [first[0], hover[1]], first])
        if self.tool in ("circle", "arc"):
            radius = float(np.linalg.norm((sketch.position(self.pending[1]) if len(self.pending) > 1 else hover) - first))
            angles = np.linspace(0.0, 2 * math.pi, 65)
            return first + radius * np.c_[np.cos(angles), np.sin(angles)]
        return None

    # -- persistence --------------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {"plane": self.plane, "offset": self.offset, "sketch": self.sketch.to_dict()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SketchMode:
        return cls(Sketch2D.from_dict(data.get("sketch", {})), str(data.get("plane", "XY")), float(data.get("offset", 0.0)))


def _distance_to_polyline(points: np.ndarray, target: np.ndarray) -> float:
    """Distance from ``target`` to the polyline's segments (not just its sample points)."""

    starts, ends = points[:-1], points[1:]
    if not len(starts):
        return float(np.linalg.norm(points[0] - target)) if len(points) else float("inf")
    along = ends - starts
    length2 = np.maximum(np.einsum("ij,ij->i", along, along), 1e-30)
    t = np.clip(np.einsum("ij,ij->i", target - starts, along) / length2, 0.0, 1.0)
    nearest = starts + along * t[:, None]
    return float(np.min(np.linalg.norm(nearest - target, axis=1)))


__all__ = ("DRAW_TOOLS", "GLYPHS", "PLANES", "SketchMode")
