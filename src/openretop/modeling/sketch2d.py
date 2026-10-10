"""Constrained 2D sketches (P-02): points, lines, arcs and circles held by geometric
constraints and dimensions, solved numerically.

Model
-----
The unknowns are the points' x and y and the circles' radii. Lines and arcs refer to
points, so sharing a point is how geometry connects. An arc is a centre, a start and an end,
counter-clockwise; an implicit constraint keeps its two radii equal. Construction geometry
takes part in solving but not in profiles.

Solver
------
Damped Gauss-Newton with minimum-norm steps: every step changes the unknowns as little as
possible while reducing the residuals, so geometry the constraints do not hold stays where
it is, and a drag moves only what has to move (as in Fusion 360). Each constraint touches
at most eight unknowns; its Jacobian rows are central differences over those alone.

Degrees of freedom are the unknowns minus the rank of the Jacobian at the solution. A point
or curve is *fully defined* when no direction of the Jacobian's null space moves it.

Adding a constraint that cannot be met (it conflicts) or that adds nothing (it is
redundant) is refused, with the reason, and the sketch is left as it was.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

import numpy as np

# constraint kinds, by what they take (P = point, L = line, C = circle or arc)
GEOMETRIC = (
    "coincident",  # P P | P L (point on the line) | P C (point on the circle)
    "horizontal",  # L | P P
    "vertical",  # L | P P
    "parallel",  # L L
    "perpendicular",  # L L
    "tangent",  # L C | C C
    "equal",  # L L (length) | C C (radius)
    "concentric",  # C C
    "midpoint",  # P L
    "symmetric",  # P P L
    "collinear",  # L L
    "fix",  # P (held where it is)
)
DIMENSIONS = (
    "distance",  # P P | P L | L (its length) | L L (parallel lines)
    "horizontal_distance",  # P P
    "vertical_distance",  # P P
    "angle",  # L L, degrees, measured from the first to the second counter-clockwise
    "radius",  # C
    "diameter",  # C
)
KINDS = GEOMETRIC + DIMENSIONS

_EPS = 1e-12


@dataclass
class Point:
    id: str
    x: float
    y: float
    construction: bool = False


@dataclass
class Line:
    id: str
    p1: str
    p2: str
    construction: bool = False


@dataclass
class Circle:
    id: str
    center: str
    radius: float
    construction: bool = False


@dataclass
class Arc:
    """Counter-clockwise from ``start`` to ``end`` around ``center``."""

    id: str
    center: str
    start: str
    end: str
    construction: bool = False


Curve = Line | Circle | Arc


@dataclass
class Constraint:
    id: str
    kind: str
    refs: tuple[str, ...]
    value: float | None = None  # dimensions; a "fix" keeps its (x, y) in ``target``
    driving: bool = True  # a driven (reference) dimension only reports its value
    target: tuple[float, float] | None = None
    option: str = ""  # tangent circles: "outside" or "inside"


@dataclass(frozen=True)
class SolveReport:
    ok: bool
    message: str = ""
    residual: float = 0.0
    iterations: int = 0
    dof: int = 0
    constraint_id: str | None = None  # the constraint that was added or changed


@dataclass
class Sketch2D:
    """A plane sketch: geometry, constraints, and the solver that keeps them consistent."""

    points: dict[str, Point] = field(default_factory=dict)
    curves: dict[str, Curve] = field(default_factory=dict)
    constraints: list[Constraint] = field(default_factory=list)
    _counter: int = 0

    # -- geometry -----------------------------------------------------------------------------

    def _new_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}{self._counter}"

    def add_point(self, x: float, y: float, *, construction: bool = False) -> str:
        point = Point(self._new_id("p"), float(x), float(y), construction)
        self.points[point.id] = point
        return point.id

    def _point_ref(self, value: str | tuple[float, float] | Iterable[float]) -> str:
        if isinstance(value, str):
            if value not in self.points:
                raise KeyError(f"no point {value}")
            return value
        x, y = (float(component) for component in value)
        return self.add_point(x, y)

    def add_line(self, start: Any, end: Any, *, construction: bool = False) -> str:
        line = Line(self._new_id("l"), self._point_ref(start), self._point_ref(end), construction)
        self.curves[line.id] = line
        return line.id

    def add_circle(self, center: Any, radius: float, *, construction: bool = False) -> str:
        circle = Circle(self._new_id("c"), self._point_ref(center), float(radius), construction)
        self.curves[circle.id] = circle
        return circle.id

    def add_arc(self, center: Any, start: Any, end: Any, *, construction: bool = False) -> str:
        arc = Arc(self._new_id("a"), self._point_ref(center), self._point_ref(start), self._point_ref(end), construction)
        self.curves[arc.id] = arc
        # the end lies on the start's circle: snap it there so the implicit constraint holds
        c, s, e = (self.position(arc.center), self.position(arc.start), self.position(arc.end))
        radius, direction = float(np.linalg.norm(s - c)), e - c
        length = float(np.linalg.norm(direction))
        if radius > _EPS and length > _EPS:
            self.points[arc.end].x, self.points[arc.end].y = (c + direction * (radius / length)).tolist()
        return arc.id

    def add_rectangle(self, corner: tuple[float, float], opposite: tuple[float, float]) -> tuple[str, str, str, str]:
        """Four lines through shared corners, horizontal and vertical (as Fusion draws it)."""

        (x0, y0), (x1, y1) = corner, opposite
        a, b, c, d = (self.add_point(x0, y0), self.add_point(x1, y0), self.add_point(x1, y1), self.add_point(x0, y1))
        lines = (self.add_line(a, b), self.add_line(b, c), self.add_line(c, d), self.add_line(d, a))
        for line, kind in zip(lines, ("horizontal", "vertical", "horizontal", "vertical"), strict=True):
            self.constraints.append(Constraint(self._new_id("k"), kind, (line,)))
        return lines

    def position(self, point_id: str) -> np.ndarray:
        point = self.points[point_id]
        return np.array([point.x, point.y], dtype=float)

    def radius(self, curve_id: str) -> float:
        curve = self.curves[curve_id]
        if isinstance(curve, Circle):
            return float(curve.radius)
        if isinstance(curve, Arc):
            return float(np.linalg.norm(self.position(curve.start) - self.position(curve.center)))
        raise TypeError(f"{curve_id} is not a circle or an arc")

    def curve_points(self, curve_id: str) -> tuple[str, ...]:
        curve = self.curves[curve_id]
        if isinstance(curve, Line):
            return (curve.p1, curve.p2)
        if isinstance(curve, Circle):
            return (curve.center,)
        return (curve.center, curve.start, curve.end)

    def delete(self, item_id: str) -> None:
        """Delete a point or curve with the constraints on it (and points nothing else uses)."""

        doomed = {item_id}
        if item_id in self.curves:
            for point_id in self.curve_points(item_id):
                users = [other for other in self.curves if other != item_id and point_id in self.curve_points(other)]
                if not users:
                    doomed.add(point_id)
            del self.curves[item_id]
        if item_id in self.points:
            for curve_id in [key for key in self.curves if item_id in self.curve_points(key)]:
                doomed.add(curve_id)
                del self.curves[curve_id]
        for point_id in doomed & set(self.points):
            del self.points[point_id]
        self.constraints = [item for item in self.constraints if not doomed & set(item.refs)]

    # -- constraints --------------------------------------------------------------------------

    def constrain(self, kind: str, *refs: str, value: float | None = None, driving: bool = True) -> SolveReport:
        """Add a constraint or dimension and solve; refused (and undone) if it conflicts or is
        redundant. A dimension without a value takes the current measurement."""

        if kind not in KINDS:
            raise ValueError(f"unknown constraint: {kind}")
        constraint = Constraint(self._new_id("k"), kind, tuple(refs), driving=driving)
        self._check_refs(constraint)
        if kind == "fix":
            constraint.target = tuple(self.position(refs[0]).tolist())  # type: ignore[assignment]
        if kind == "tangent" and all(self._is_round(ref) for ref in refs):
            centre_distance = float(np.linalg.norm(self._center(refs[0]) - self._center(refs[1])))
            outside = abs(centre_distance - (self.radius(refs[0]) + self.radius(refs[1])))
            inside = abs(centre_distance - abs(self.radius(refs[0]) - self.radius(refs[1])))
            constraint.option = "outside" if outside <= inside else "inside"
        if kind in DIMENSIONS:
            measured = self.measure(constraint)
            constraint.value = measured if value is None else float(value)
            if kind == "angle" and value is not None and np.sign(measured) < 0 < float(value):
                constraint.value = -float(value)  # the angle keeps the turn the lines already have
        if not driving:
            self.constraints.append(constraint)
            return SolveReport(True, "Reference dimension added", dof=self.dof(), constraint_id=constraint.id)
        saved = self._state()
        rank_before = self._rank()
        self.constraints.append(constraint)
        report = self.solve()
        if not report.ok:
            self._restore(saved)
            return SolveReport(False, f"{_label(kind)} conflicts with the existing constraints", report.residual, constraint_id=constraint.id)
        if self._rank() <= rank_before:
            self._restore(saved)
            return SolveReport(False, f"{_label(kind)} is redundant: the sketch already holds it", constraint_id=constraint.id)
        return SolveReport(True, f"{_label(kind)} added", report.residual, report.iterations, report.dof, constraint.id)

    def set_value(self, constraint_id: str, value: float) -> SolveReport:
        """Change a dimension; refused (and undone) if the sketch cannot take it."""

        constraint = self.constraint(constraint_id)
        if constraint.kind not in DIMENSIONS:
            raise ValueError(f"{constraint_id} is not a dimension")
        saved = self._state()
        constraint.value = float(value) if constraint.kind != "angle" else math.copysign(float(value), constraint.value or 1.0)
        report = self.solve()
        if not report.ok:
            self._restore(saved)
            return SolveReport(False, f"The sketch cannot take {value:g}", report.residual, constraint_id=constraint_id)
        return SolveReport(True, "Dimension changed", report.residual, report.iterations, report.dof, constraint_id)

    def remove_constraint(self, constraint_id: str) -> None:
        self.constraints = [item for item in self.constraints if item.id != constraint_id]

    def constraint(self, constraint_id: str) -> Constraint:
        return next(item for item in self.constraints if item.id == constraint_id)

    def measure(self, constraint: Constraint) -> float:
        """The current value of a dimension (degrees for angles)."""

        x, index = self._vector()
        value = _dimension_value(self, constraint, x, index)
        return math.degrees(value) if constraint.kind == "angle" else value

    # -- solving ------------------------------------------------------------------------------

    def solve(self, *, frozen: Iterable[str] = (), max_iterations: int = 60) -> SolveReport:
        """Move the geometry the least to satisfy every driving constraint.

        ``frozen`` points keep their position (a drag holds the dragged point)."""

        x, index = self._vector()
        free = self._free_columns(index, frozen)
        rows = self._rows(index)
        scale = self._scale(x, index)
        tolerance = 1e-10 * scale
        residual = _residuals(rows, x, scale)
        iterations = 0
        damping = 0.0
        while iterations < max_iterations and residual.size and float(np.max(np.abs(residual))) > tolerance:
            iterations += 1
            jacobian = _jacobian(rows, x, scale)[:, free]
            if damping:
                # Levenberg-Marquardt, still minimum-norm: dx = -J^T (J J^T + damping I)^-1 r
                gram = jacobian @ jacobian.T + damping * np.eye(len(residual))
                step = -jacobian.T @ np.linalg.solve(gram, residual)
            else:
                step = -np.linalg.lstsq(jacobian, residual, rcond=None)[0]
            current = float(residual @ residual)
            accepted = False
            alpha = 1.0
            for _ in range(12):
                trial = x.copy()
                trial[free] += alpha * step
                trial_residual = _residuals(rows, trial, scale)
                if float(trial_residual @ trial_residual) < current:
                    x, residual, accepted = trial, trial_residual, True
                    break
                alpha *= 0.5
            if accepted:
                damping = damping * 0.3 if damping > 1e-12 else 0.0
            else:
                damping = max(damping * 10.0, 1e-6 * scale * scale)
                if damping > 1e8 * scale * scale:
                    break
        worst = float(np.max(np.abs(residual))) if residual.size else 0.0
        ok = worst <= max(tolerance, 1e-9 * scale) * 10.0
        if ok:
            self._write(x, index)
        dof = self.dof() if ok else 0
        return SolveReport(ok, "Solved" if ok else "No solution", worst, iterations, dof)

    def drag(self, point_id: str, target: tuple[float, float]) -> SolveReport:
        """Move a point toward ``target``; the rest of the sketch follows its constraints.

        The point goes to the target if the sketch allows it, else as near as it can (a fully
        defined point does not move)."""

        saved = self._state()
        self.points[point_id].x, self.points[point_id].y = float(target[0]), float(target[1])
        report = self.solve(frozen=(point_id,))
        if report.ok:
            return report
        self._restore(saved)
        # held elsewhere: start from the target and let the solver pull it back into place
        self.points[point_id].x, self.points[point_id].y = float(target[0]), float(target[1])
        report = self.solve()
        if not report.ok:
            self._restore(saved)
        return report

    # -- degrees of freedom -------------------------------------------------------------------

    def dof(self) -> int:
        x, index = self._vector()
        return len(x) - self._rank(x, index)

    def fully_defined(self) -> set[str]:
        """Ids of the points and curves no remaining freedom can move (Fusion draws them black)."""

        x, index = self._vector()
        if not len(x):
            return set()
        rows = self._rows(index)
        jacobian = _jacobian(rows, x, self._scale(x, index)) if rows else np.zeros((0, len(x)))
        null = _null_space(jacobian, len(x))
        moves = np.linalg.norm(null, axis=1) if null.size else np.zeros(len(x))
        defined_points = {
            point_id for point_id, (ix, iy) in index.points.items() if moves[ix] < 1e-7 and moves[iy] < 1e-7
        }
        result = set(defined_points)
        for curve_id, curve in self.curves.items():
            points_defined = all(point in defined_points for point in self.curve_points(curve_id))
            radius_defined = not isinstance(curve, Circle) or moves[index.radii[curve_id]] < 1e-7
            if points_defined and radius_defined:
                result.add(curve_id)
        return result

    # -- internals ----------------------------------------------------------------------------

    def _state(self) -> tuple[Any, ...]:
        return (
            {key: (point.x, point.y) for key, point in self.points.items()},
            {key: curve.radius for key, curve in self.curves.items() if isinstance(curve, Circle)},
            copy.deepcopy(self.constraints),
        )

    def _restore(self, state: tuple[Any, ...]) -> None:
        positions, radii, constraints = state
        for key, (x, y) in positions.items():
            self.points[key].x, self.points[key].y = x, y
        for key, radius in radii.items():
            self.curves[key].radius = radius  # type: ignore[union-attr]
        self.constraints = constraints

    def _vector(self) -> tuple[np.ndarray, _Index]:
        index = _Index()
        values: list[float] = []
        for point_id, point in self.points.items():
            index.points[point_id] = (len(values), len(values) + 1)
            values.extend((point.x, point.y))
        for curve_id, curve in self.curves.items():
            if isinstance(curve, Circle):
                index.radii[curve_id] = len(values)
                values.append(curve.radius)
        return np.asarray(values, dtype=float), index

    def _write(self, x: np.ndarray, index: _Index) -> None:
        for point_id, (ix, iy) in index.points.items():
            self.points[point_id].x, self.points[point_id].y = float(x[ix]), float(x[iy])
        for curve_id, ir in index.radii.items():
            self.curves[curve_id].radius = float(x[ir])  # type: ignore[union-attr]

    @staticmethod
    def _free_columns(index: _Index, frozen: Iterable[str]) -> np.ndarray:
        held = {column for point_id in frozen for column in index.points[point_id]}
        total = 2 * len(index.points) + len(index.radii)
        return np.asarray([column for column in range(total) if column not in held], dtype=int)

    def _scale(self, x: np.ndarray, index: _Index) -> float:
        """A typical length of the sketch: dimensionless residuals are multiplied by it."""

        if not index.points:
            return 1.0
        xy = np.asarray([[x[ix], x[iy]] for ix, iy in index.points.values()])
        extent = float(np.max(np.ptp(xy, axis=0))) if len(xy) > 1 else 0.0
        radii = [abs(float(x[ir])) for ir in index.radii.values()]
        return max(extent, max(radii, default=0.0), 1e-3)

    def _rows(self, index: _Index) -> list[_Row]:
        rows = [_arc_row(self, curve, index) for curve in self.curves.values() if isinstance(curve, Arc)]
        rows.extend(_constraint_row(self, constraint, index) for constraint in self.constraints if constraint.driving)
        return rows

    def _rank(self, x: np.ndarray | None = None, index: _Index | None = None) -> int:
        if x is None or index is None:
            x, index = self._vector()
        rows = self._rows(index)
        if not rows or not len(x):
            return 0
        jacobian = _jacobian(rows, x, self._scale(x, index))
        singular = np.linalg.svd(jacobian, compute_uv=False)
        if not singular.size or singular[0] <= 0:
            return 0
        return int(np.sum(singular > singular[0] * 1e-9))

    def _check_refs(self, constraint: Constraint) -> None:
        shapes = [self._shape(ref) for ref in constraint.refs]
        allowed = _ALLOWED[constraint.kind]
        if tuple(shapes) not in allowed:
            wanted = " or ".join("+".join(shape) for shape in allowed)
            raise ValueError(f"{_label(constraint.kind)} takes {wanted}, not {'+'.join(shapes) or 'nothing'}")

    def _shape(self, ref: str) -> str:
        if ref in self.points:
            return "P"
        curve = self.curves.get(ref)
        if curve is None:
            raise KeyError(f"no point or curve {ref}")
        return "L" if isinstance(curve, Line) else "C"

    def _is_round(self, ref: str) -> bool:
        return isinstance(self.curves.get(ref), Circle | Arc)

    def _center(self, ref: str) -> np.ndarray:
        curve = self.curves[ref]
        assert isinstance(curve, Circle | Arc)
        return self.position(curve.center)

    # -- persistence --------------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        def curve_dict(curve: Curve) -> dict[str, Any]:
            if isinstance(curve, Line):
                return {"type": "line", "p1": curve.p1, "p2": curve.p2, "construction": curve.construction}
            if isinstance(curve, Circle):
                return {"type": "circle", "center": curve.center, "radius": curve.radius, "construction": curve.construction}
            return {"type": "arc", "center": curve.center, "start": curve.start, "end": curve.end, "construction": curve.construction}

        return {
            "points": {key: [point.x, point.y, point.construction] for key, point in self.points.items()},
            "curves": {key: curve_dict(curve) for key, curve in self.curves.items()},
            "constraints": [
                {
                    "id": item.id,
                    "kind": item.kind,
                    "refs": list(item.refs),
                    "value": item.value,
                    "driving": item.driving,
                    "target": None if item.target is None else list(item.target),
                    "option": item.option,
                }
                for item in self.constraints
            ],
            "counter": self._counter,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Sketch2D:
        sketch = cls()
        for key, (x, y, construction) in data.get("points", {}).items():
            sketch.points[key] = Point(key, float(x), float(y), bool(construction))
        for key, item in data.get("curves", {}).items():
            kind, construction = item["type"], bool(item.get("construction", False))
            if kind == "line":
                sketch.curves[key] = Line(key, item["p1"], item["p2"], construction)
            elif kind == "circle":
                sketch.curves[key] = Circle(key, item["center"], float(item["radius"]), construction)
            else:
                sketch.curves[key] = Arc(key, item["center"], item["start"], item["end"], construction)
        for item in data.get("constraints", []):
            target = item.get("target")
            sketch.constraints.append(
                Constraint(
                    item["id"],
                    item["kind"],
                    tuple(item["refs"]),
                    None if item.get("value") is None else float(item["value"]),
                    bool(item.get("driving", True)),
                    None if target is None else (float(target[0]), float(target[1])),
                    str(item.get("option", "")),
                )
            )
        sketch._counter = int(data.get("counter", len(sketch.points) + len(sketch.curves) + len(sketch.constraints)))
        return sketch


# -- residuals ---------------------------------------------------------------------------------


@dataclass
class _Index:
    points: dict[str, tuple[int, int]] = field(default_factory=dict)
    radii: dict[str, int] = field(default_factory=dict)


@dataclass
class _Row:
    """One constraint's residuals: ``function(x, scale)`` reads only ``columns`` of ``x``."""

    function: Callable[[np.ndarray, float], np.ndarray]
    columns: tuple[int, ...]


def _residuals(rows: list[_Row], x: np.ndarray, scale: float) -> np.ndarray:
    if not rows:
        return np.zeros(0)
    return np.concatenate([np.atleast_1d(row.function(x, scale)) for row in rows])


def _jacobian(rows: list[_Row], x: np.ndarray, scale: float) -> np.ndarray:
    blocks = []
    step = 1e-6 * scale
    for row in rows:
        base = np.atleast_1d(row.function(x, scale))
        block = np.zeros((len(base), len(x)))
        for column in row.columns:
            plus, minus = x.copy(), x.copy()
            plus[column] += step
            minus[column] -= step
            block[:, column] = (np.atleast_1d(row.function(plus, scale)) - np.atleast_1d(row.function(minus, scale))) / (2 * step)
        blocks.append(block)
    return np.vstack(blocks) if blocks else np.zeros((0, len(x)))


def _null_space(jacobian: np.ndarray, columns: int) -> np.ndarray:
    if not jacobian.size:
        return np.eye(columns)
    _u, singular, vt = np.linalg.svd(jacobian, full_matrices=True)
    rank = int(np.sum(singular > (singular[0] if singular.size else 0.0) * 1e-9)) if singular.size else 0
    return vt[rank:].T


def _arc_row(sketch: Sketch2D, arc: Arc, index: _Index) -> _Row:
    c, s, e = index.points[arc.center], index.points[arc.start], index.points[arc.end]

    def residual(x: np.ndarray, _scale: float) -> np.ndarray:
        center = x[list(c)]
        return np.array([np.linalg.norm(x[list(s)] - center) - np.linalg.norm(x[list(e)] - center)])

    return _Row(residual, (*c, *s, *e))


class _Reader:
    """Positions, directions and radii read from the unknowns vector."""

    def __init__(self, sketch: Sketch2D, index: _Index) -> None:
        self.sketch = sketch
        self.index = index

    def point_columns(self, point_id: str) -> tuple[int, int]:
        return self.index.points[point_id]

    def columns(self, ref: str) -> tuple[int, ...]:
        if ref in self.sketch.points:
            return self.point_columns(ref)
        curve = self.sketch.curves[ref]
        columns = [column for point_id in self.sketch.curve_points(ref) for column in self.point_columns(point_id)]
        if isinstance(curve, Circle):
            columns.append(self.index.radii[ref])
        return tuple(columns)

    def p(self, x: np.ndarray, point_id: str) -> np.ndarray:
        ix, iy = self.index.points[point_id]
        return np.array([x[ix], x[iy]])

    def ends(self, x: np.ndarray, line_id: str) -> tuple[np.ndarray, np.ndarray]:
        line = self.sketch.curves[line_id]
        assert isinstance(line, Line)
        return self.p(x, line.p1), self.p(x, line.p2)

    def direction(self, x: np.ndarray, line_id: str) -> np.ndarray:
        a, b = self.ends(x, line_id)
        d = b - a
        return d / max(float(np.linalg.norm(d)), _EPS)

    def center(self, x: np.ndarray, curve_id: str) -> np.ndarray:
        curve = self.sketch.curves[curve_id]
        assert isinstance(curve, Circle | Arc)
        return self.p(x, curve.center)

    def radius(self, x: np.ndarray, curve_id: str) -> float:
        curve = self.sketch.curves[curve_id]
        if isinstance(curve, Circle):
            return float(x[self.index.radii[curve_id]])
        assert isinstance(curve, Arc)
        return float(np.linalg.norm(self.p(x, curve.start) - self.p(x, curve.center)))

    def point_line_distance(self, x: np.ndarray, point_id: str, line_id: str, *, signed: bool = False) -> float:
        a, _b = self.ends(x, line_id)
        u = self.direction(x, line_id)
        value = float(_cross(u, self.p(x, point_id) - a))
        return value if signed else abs(value)


def _cross(a: np.ndarray, b: np.ndarray) -> float:
    return float(a[0] * b[1] - a[1] * b[0])


def _dimension_value(sketch: Sketch2D, constraint: Constraint, x: np.ndarray, index: _Index) -> float:
    read = _Reader(sketch, index)
    kind, refs = constraint.kind, constraint.refs
    shapes = tuple(sketch._shape(ref) for ref in refs)
    if kind == "distance":
        if shapes == ("P", "P"):
            return float(np.linalg.norm(read.p(x, refs[1]) - read.p(x, refs[0])))
        if shapes == ("P", "L"):
            return read.point_line_distance(x, refs[0], refs[1])
        if shapes == ("L",):
            a, b = read.ends(x, refs[0])
            return float(np.linalg.norm(b - a))
        line = sketch.curves[refs[1]]
        assert isinstance(line, Line)
        return read.point_line_distance(x, line.p1, refs[0])
    if kind == "horizontal_distance":
        return abs(float(read.p(x, refs[1])[0] - read.p(x, refs[0])[0]))
    if kind == "vertical_distance":
        return abs(float(read.p(x, refs[1])[1] - read.p(x, refs[0])[1]))
    if kind == "angle":
        u, v = read.direction(x, refs[0]), read.direction(x, refs[1])
        return math.atan2(_cross(u, v), float(u @ v))
    if kind == "radius":
        return read.radius(x, refs[0])
    if kind == "diameter":
        return 2.0 * read.radius(x, refs[0])
    raise ValueError(kind)


def _constraint_row(sketch: Sketch2D, constraint: Constraint, index: _Index) -> _Row:
    read = _Reader(sketch, index)
    kind, refs = constraint.kind, constraint.refs
    shapes = tuple(sketch._shape(ref) for ref in refs)
    columns = tuple(dict.fromkeys(column for ref in refs for column in read.columns(ref)))

    def row(function: Callable[[np.ndarray, float], Any]) -> _Row:
        return _Row(lambda x, scale: np.atleast_1d(np.asarray(function(x, scale), dtype=float)), columns)

    if kind == "coincident":
        if shapes == ("P", "P"):
            return row(lambda x, s: read.p(x, refs[0]) - read.p(x, refs[1]))
        if shapes == ("P", "L"):
            return row(lambda x, s: read.point_line_distance(x, refs[0], refs[1], signed=True))
        return row(lambda x, s: np.linalg.norm(read.p(x, refs[0]) - read.center(x, refs[1])) - read.radius(x, refs[1]))
    if kind in ("horizontal", "vertical"):
        axis = 1 if kind == "horizontal" else 0
        if shapes == ("L",):
            return row(lambda x, s: read.ends(x, refs[0])[1][axis] - read.ends(x, refs[0])[0][axis])
        return row(lambda x, s: read.p(x, refs[1])[axis] - read.p(x, refs[0])[axis])
    if kind == "parallel":
        return row(lambda x, s: s * _cross(read.direction(x, refs[0]), read.direction(x, refs[1])))
    if kind == "perpendicular":
        return row(lambda x, s: s * float(read.direction(x, refs[0]) @ read.direction(x, refs[1])))
    if kind == "tangent":
        joint = _shared_end(sketch, refs[0], refs[1])
        if joint is not None:
            # meeting at a point (a fillet): "centre-to-line distance = radius" has a zero
            # gradient there (it never exceeds the radius), so hold the joint's direction instead
            if shapes == ("L", "C"):
                return row(lambda x, s: float(read.direction(x, refs[0]) @ (read.center(x, refs[1]) - read.p(x, joint))))

            def centres_in_line(x: np.ndarray, s: float) -> float:
                q = read.p(x, joint)
                a, b = read.center(x, refs[0]) - q, read.center(x, refs[1]) - q
                return s * _cross(a / max(float(np.linalg.norm(a)), _EPS), b / max(float(np.linalg.norm(b)), _EPS))

            return row(centres_in_line)
        if shapes == ("L", "C"):
            return row(lambda x, s: read.point_line_distance(x, sketch.curves[refs[1]].center, refs[0]) - read.radius(x, refs[1]))  # type: ignore[union-attr]
        if constraint.option == "inside":
            return row(
                lambda x, s: np.linalg.norm(read.center(x, refs[0]) - read.center(x, refs[1]))
                - abs(read.radius(x, refs[0]) - read.radius(x, refs[1]))
            )
        return row(
            lambda x, s: np.linalg.norm(read.center(x, refs[0]) - read.center(x, refs[1]))
            - (read.radius(x, refs[0]) + read.radius(x, refs[1]))
        )
    if kind == "equal":
        if shapes == ("L", "L"):
            return row(
                lambda x, s: np.linalg.norm(np.subtract(*read.ends(x, refs[0])))
                - np.linalg.norm(np.subtract(*read.ends(x, refs[1])))
            )
        return row(lambda x, s: read.radius(x, refs[0]) - read.radius(x, refs[1]))
    if kind == "concentric":
        return row(lambda x, s: read.center(x, refs[0]) - read.center(x, refs[1]))
    if kind == "midpoint":
        return row(lambda x, s: read.p(x, refs[0]) - 0.5 * np.add(*read.ends(x, refs[1])))
    if kind == "symmetric":

        def symmetric(x: np.ndarray, s: float) -> np.ndarray:
            p, q = read.p(x, refs[0]), read.p(x, refs[1])
            a, _b = read.ends(x, refs[2])
            u = read.direction(x, refs[2])
            return np.array([_cross(u, 0.5 * (p + q) - a), float((q - p) @ u)])

        return row(symmetric)
    if kind == "collinear":

        def collinear(x: np.ndarray, s: float) -> np.ndarray:
            u = read.direction(x, refs[0])
            a, _b = read.ends(x, refs[0])
            c, d = read.ends(x, refs[1])
            return np.array([_cross(u, c - a), _cross(u, d - a)])

        return row(collinear)
    if kind == "fix":
        target = np.asarray(constraint.target, dtype=float)
        return row(lambda x, s: read.p(x, refs[0]) - target)
    if kind in DIMENSIONS:
        goal = float(constraint.value or 0.0)
        if kind == "angle":
            goal = math.radians(goal)

            def angle(x: np.ndarray, s: float) -> float:
                difference = _dimension_value(sketch, constraint, x, index) - goal
                return s * math.atan2(math.sin(difference), math.cos(difference))

            return row(angle)
        if kind == "distance" and shapes == ("L", "L"):
            # parallel lines a set distance apart: keep them parallel too
            def between(x: np.ndarray, s: float) -> np.ndarray:
                return np.array(
                    [
                        _dimension_value(sketch, constraint, x, index) - goal,
                        s * _cross(read.direction(x, refs[0]), read.direction(x, refs[1])),
                    ]
                )

            return row(between)
        return row(lambda x, s: _dimension_value(sketch, constraint, x, index) - goal)
    raise ValueError(kind)


def _shared_end(sketch: Sketch2D, first: str, second: str) -> str | None:
    """The point where a line or arc ends and an arc begins or ends, if they meet."""

    def ends(ref: str) -> set[str]:
        curve = sketch.curves[ref]
        if isinstance(curve, Line):
            return {curve.p1, curve.p2}
        if isinstance(curve, Arc):
            return {curve.start, curve.end}
        return set()

    shared = ends(first) & ends(second)
    return next(iter(sorted(shared)), None)


_ALLOWED: dict[str, tuple[tuple[str, ...], ...]] = {
    "coincident": (("P", "P"), ("P", "L"), ("P", "C")),
    "horizontal": (("L",), ("P", "P")),
    "vertical": (("L",), ("P", "P")),
    "parallel": (("L", "L"),),
    "perpendicular": (("L", "L"),),
    "tangent": (("L", "C"), ("C", "C")),
    "equal": (("L", "L"), ("C", "C")),
    "concentric": (("C", "C"),),
    "midpoint": (("P", "L"),),
    "symmetric": (("P", "P", "L"),),
    "collinear": (("L", "L"),),
    "fix": (("P",),),
    "distance": (("P", "P"), ("P", "L"), ("L",), ("L", "L")),
    "horizontal_distance": (("P", "P"),),
    "vertical_distance": (("P", "P"),),
    "angle": (("L", "L"),),
    "radius": (("C",),),
    "diameter": (("C",),),
}


def _label(kind: str) -> str:
    return kind.replace("_", " ").capitalize()


__all__ = (
    "DIMENSIONS",
    "GEOMETRIC",
    "KINDS",
    "Arc",
    "Circle",
    "Constraint",
    "Line",
    "Point",
    "Sketch2D",
    "SolveReport",
)
