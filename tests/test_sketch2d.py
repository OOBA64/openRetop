"""P-02: the constrained 2D sketch solver."""

from __future__ import annotations

import math
import unittest

import numpy as np

from openretop.modeling.sketch2d import Sketch2D


def _rectangle(width: float = 10.0, height: float = 6.0) -> tuple[Sketch2D, tuple[str, str, str, str]]:
    sketch = Sketch2D()
    lines = sketch.add_rectangle((0.0, 0.0), (width, height))
    return sketch, lines


def _corners(sketch: Sketch2D, lines: tuple[str, ...]) -> list[str]:
    return [sketch.curves[line].p1 for line in lines]  # type: ignore[union-attr]


class DegreesOfFreedomTests(unittest.TestCase):
    """The plan asks for the DOF count to be right on 20 test sketches; here are 26."""

    def test_degrees_of_freedom_of_test_sketches(self) -> None:
        def point():
            s = Sketch2D()
            s.add_point(1, 2)
            return s

        def line(*constraints: str):
            s = Sketch2D()
            l1 = s.add_line((0, 0), (10, 1))
            for kind in constraints:
                if kind == "fix":
                    self.assertTrue(s.constrain("fix", s.curves[l1].p1).ok)  # type: ignore[union-attr]
                else:
                    self.assertTrue(s.constrain(kind, l1).ok, kind)
            return s

        def circle(*constraints: str):
            s = Sketch2D()
            c = s.add_circle((0, 0), 5)
            for kind in constraints:
                ref = s.curves[c].center if kind == "fix" else c  # type: ignore[union-attr]
                self.assertTrue(s.constrain(kind, ref).ok, kind)
            return s

        def arc(fixed: bool = False, radius: bool = False):
            s = Sketch2D()
            a = s.add_arc((0, 0), (5, 0), (0, 5))
            if fixed:
                self.assertTrue(s.constrain("fix", s.curves[a].center).ok)  # type: ignore[union-attr]
            if radius:
                self.assertTrue(s.constrain("radius", a, value=4.0).ok)
            return s

        def rectangle(*extra: str):
            s, lines = _rectangle()
            corners = _corners(s, lines)
            for kind in extra:
                if kind == "width":
                    self.assertTrue(s.constrain("distance", lines[0], value=12.0).ok)
                elif kind == "height":
                    self.assertTrue(s.constrain("distance", lines[1], value=7.0).ok)
                elif kind == "fix":
                    self.assertTrue(s.constrain("fix", corners[0]).ok)
                elif kind == "equal":
                    self.assertTrue(s.constrain("equal", lines[0], lines[1]).ok)
            return s

        def polyline(perpendicular: bool = False):
            s = Sketch2D()
            a = s.add_point(0, 0)
            b = s.add_point(10, 0)
            l1 = s.add_line(a, b)
            l2 = s.add_line(b, (12, 8))
            if perpendicular:
                self.assertTrue(s.constrain("perpendicular", l1, l2).ok)
            return s

        def pair(kind: str):
            s = Sketch2D()
            if kind == "tangent_line_circle":
                l1 = s.add_line((-10, 6), (10, 5))
                c = s.add_circle((0, 0), 5)
                self.assertTrue(s.constrain("tangent", l1, c).ok)
            elif kind == "concentric":
                c1, c2 = s.add_circle((0, 0), 5), s.add_circle((0.5, 0.2), 8)
                self.assertTrue(s.constrain("concentric", c1, c2).ok)
            elif kind == "midpoint":
                p = s.add_point(4, 1)
                l1 = s.add_line((0, 0), (10, 0))
                self.assertTrue(s.constrain("midpoint", p, l1).ok)
            elif kind == "symmetric":
                p, q = s.add_point(-3, 2), s.add_point(3, 2.5)
                axis = s.add_line((0, -5), (0, 5))
                self.assertTrue(s.constrain("symmetric", p, q, axis).ok)
            elif kind == "parallel_distance":
                l1, l2 = s.add_line((0, 0), (10, 0)), s.add_line((0, 4), (10, 4.5))
                self.assertTrue(s.constrain("distance", l1, l2, value=5.0).ok)
            elif kind == "collinear":
                l1, l2 = s.add_line((0, 0), (10, 0)), s.add_line((12, 0.5), (20, 0.2))
                self.assertTrue(s.constrain("collinear", l1, l2).ok)
            elif kind == "on_circle":
                p = s.add_point(6, 1)
                c = s.add_circle((0, 0), 5)
                self.assertTrue(s.constrain("coincident", p, c).ok)
            elif kind == "angle":
                l1, l2 = s.add_line((0, 0), (10, 0)), s.add_line((0, 0.5), (8, 6))
                self.assertTrue(s.constrain("angle", l1, l2, value=30.0).ok)
            elif kind == "vertical_distance":
                p, q = s.add_point(0, 0), s.add_point(3, 4)
                self.assertTrue(s.constrain("vertical_distance", p, q, value=5.0).ok)
            elif kind == "fillet":
                q = s.add_point(10, 0)
                s.add_line((0, 0), q)
                a = s.add_arc((10, 3), q, (13, 3))
                self.assertTrue(s.constrain("tangent", next(iter(s.curves)), a).ok)
            elif kind == "tangent_circles":
                c1, c2 = s.add_circle((0, 0), 5), s.add_circle((9, 0), 3)
                self.assertTrue(s.constrain("tangent", c1, c2).ok)
            elif kind == "equal_circles":
                c1, c2 = s.add_circle((0, 0), 5), s.add_circle((20, 0), 3)
                self.assertTrue(s.constrain("equal", c1, c2).ok)
            return s

        cases = {
            "point": (point, 2),
            "line": (line, 4),
            "horizontal line": (lambda: line("horizontal"), 3),
            "horizontal line with a length": (lambda: line("horizontal", "distance"), 2),
            "horizontal line, length, fixed end": (lambda: line("horizontal", "distance", "fix"), 0),
            "circle": (circle, 3),
            "circle with a radius": (lambda: circle("radius"), 2),
            "circle with a diameter and a fixed centre": (lambda: circle("diameter", "fix"), 0),
            "arc": (arc, 5),
            "arc with a fixed centre and a radius": (lambda: arc(True, True), 2),
            "rectangle": (rectangle, 4),
            "rectangle with width and height": (lambda: rectangle("width", "height"), 2),
            "rectangle fully defined": (lambda: rectangle("width", "height", "fix"), 0),
            "square fully defined": (lambda: rectangle("equal", "width", "fix"), 0),
            "two connected lines": (polyline, 6),
            "two perpendicular connected lines": (lambda: polyline(True), 5),
            "line tangent to a circle": (lambda: pair("tangent_line_circle"), 6),
            "concentric circles": (lambda: pair("concentric"), 4),
            "point at a line's midpoint": (lambda: pair("midpoint"), 4),
            "points symmetric about a line": (lambda: pair("symmetric"), 6),
            "parallel lines a distance apart": (lambda: pair("parallel_distance"), 6),
            "collinear lines": (lambda: pair("collinear"), 6),
            "point on a circle": (lambda: pair("on_circle"), 4),
            "lines at an angle": (lambda: pair("angle"), 7),
            "points a vertical distance apart": (lambda: pair("vertical_distance"), 3),
            "line and tangent arc (a fillet)": (lambda: pair("fillet"), 6),
            "tangent circles": (lambda: pair("tangent_circles"), 5),
            "equal circles": (lambda: pair("equal_circles"), 5),
        }
        for name, (build, expected) in cases.items():
            with self.subTest(name):
                self.assertEqual(build().dof(), expected)


class SolvingTests(unittest.TestCase):
    def test_a_constrained_rectangle_is_fully_defined_at_its_dimensions(self) -> None:
        sketch, lines = _rectangle()
        corners = _corners(sketch, lines)
        sketch.points[corners[2]].x += 0.3  # drawn a little off
        self.assertTrue(sketch.solve().ok)
        self.assertTrue(sketch.constrain("fix", corners[0]).ok)
        self.assertTrue(sketch.constrain("distance", lines[0], value=40.0).ok)
        self.assertTrue(sketch.constrain("distance", lines[1], value=25.0).ok)
        self.assertEqual(sketch.dof(), 0)
        np.testing.assert_allclose(sketch.position(corners[2]), (40.0, 25.0), atol=1e-8)
        defined = sketch.fully_defined()
        self.assertTrue(set(lines) | set(corners) <= defined)

    def test_changing_a_dimension_moves_only_what_it_drives(self) -> None:
        sketch, lines = _rectangle(10, 6)
        corners = _corners(sketch, lines)
        self.assertTrue(sketch.constrain("fix", corners[0]).ok)
        width = sketch.constrain("distance", lines[0], value=10.0)
        self.assertTrue(sketch.constrain("distance", lines[1], value=6.0).ok)
        report = sketch.set_value(width.constraint_id or "", 20.0)
        self.assertTrue(report.ok, report.message)
        np.testing.assert_allclose(sketch.position(corners[0]), (0, 0), atol=1e-9)
        np.testing.assert_allclose(sketch.position(corners[1]), (20, 0), atol=1e-8)
        np.testing.assert_allclose(sketch.position(corners[2]), (20, 6), atol=1e-8)
        np.testing.assert_allclose(sketch.position(corners[3]), (0, 6), atol=1e-8)

    def test_a_drag_moves_only_free_geometry(self) -> None:
        sketch, lines = _rectangle(10, 6)
        corners = _corners(sketch, lines)
        self.assertTrue(sketch.constrain("fix", corners[0]).ok)
        # width and height free: dragging the far corner resizes the rectangle around the fixed one
        self.assertTrue(sketch.drag(corners[2], (15.0, 9.0)).ok)
        np.testing.assert_allclose(sketch.position(corners[0]), (0, 0), atol=1e-9)
        np.testing.assert_allclose(sketch.position(corners[2]), (15, 9), atol=1e-8)
        np.testing.assert_allclose(sketch.position(corners[1]), (15, 0), atol=1e-8)
        np.testing.assert_allclose(sketch.position(corners[3]), (0, 9), atol=1e-8)
        # once fully defined, nothing moves however it is dragged
        self.assertTrue(sketch.constrain("distance", lines[0], value=15.0).ok)
        self.assertTrue(sketch.constrain("distance", lines[1], value=9.0).ok)
        before = {key: sketch.position(key) for key in sketch.points}
        sketch.drag(corners[2], (30.0, 30.0))
        for key, position in before.items():
            np.testing.assert_allclose(sketch.position(key), position, atol=1e-7)

    def test_a_drag_leaves_unconstrained_geometry_alone(self) -> None:
        sketch, lines = _rectangle(10, 6)
        corners = _corners(sketch, lines)
        loose = sketch.add_line((50, 50), (60, 55))
        loose_points = [sketch.position(key) for key in sketch.curve_points(loose)]
        sketch.drag(corners[2], (12.0, 8.0))
        for key, position in zip(sketch.curve_points(loose), loose_points, strict=True):
            np.testing.assert_allclose(sketch.position(key), position, atol=1e-12)

    def test_conflicting_constraints_are_refused_and_undone(self) -> None:
        sketch = Sketch2D()
        l1 = sketch.add_line((0, 0), (10, 0))
        self.assertTrue(sketch.constrain("horizontal", l1).ok)
        self.assertTrue(sketch.constrain("distance", l1, value=10.0).ok)
        a, b = sketch.curves[l1].p1, sketch.curves[l1].p2  # type: ignore[union-attr]
        count = len(sketch.constraints)
        report = sketch.constrain("horizontal_distance", a, b, value=20.0)
        self.assertFalse(report.ok)
        self.assertIn("conflicts", report.message)
        self.assertEqual(len(sketch.constraints), count)
        np.testing.assert_allclose(sketch.position(b) - sketch.position(a), (10, 0), atol=1e-9)

    def test_redundant_constraints_are_refused(self) -> None:
        sketch, lines = _rectangle()
        report = sketch.constrain("parallel", lines[0], lines[2])  # both are already horizontal
        self.assertFalse(report.ok)
        self.assertIn("redundant", report.message)
        self.assertEqual(sketch.dof(), 4)

    def test_a_dimension_the_sketch_cannot_take_is_refused(self) -> None:
        sketch = Sketch2D()
        c = sketch.add_circle((0, 0), 5)
        p = sketch.add_point(5, 0)
        self.assertTrue(sketch.constrain("coincident", p, c).ok)
        self.assertTrue(sketch.constrain("fix", sketch.curves[c].center).ok)  # type: ignore[union-attr]
        self.assertTrue(sketch.constrain("fix", p).ok)
        radius = sketch.constrain("radius", c, driving=False)  # reference only: measured, not held
        self.assertTrue(radius.ok)
        self.assertAlmostEqual(sketch.measure(sketch.constraint(radius.constraint_id or "")), 5.0)
        # a driving radius of 8 cannot hold with the centre and a point on the circle 5 apart
        sketch.remove_constraint(radius.constraint_id or "")
        self.assertFalse(sketch.constrain("radius", c, value=8.0).ok)
        self.assertAlmostEqual(sketch.radius(c), 5.0, places=9)
        diameter = sketch.constrain("diameter", c, driving=False)
        sketch.constraint(diameter.constraint_id or "").driving = True  # now it drives: try to change it
        refused = sketch.set_value(diameter.constraint_id or "", 16.0)
        self.assertFalse(refused.ok)
        self.assertAlmostEqual(sketch.radius(c), 5.0, places=9)
        self.assertAlmostEqual(sketch.constraint(diameter.constraint_id or "").value or 0.0, 10.0, places=9)

    def test_tangent_line_and_arc_meet_smoothly(self) -> None:
        sketch = Sketch2D()
        q = sketch.add_point(10, 0.4)
        line = sketch.add_line((0, 0), q)
        arc = sketch.add_arc((10.5, 3.2), q, (13, 3))
        self.assertTrue(sketch.constrain("horizontal", line).ok)
        self.assertTrue(sketch.constrain("tangent", line, arc).ok)
        self.assertTrue(sketch.constrain("radius", arc, value=3.0).ok)
        center = sketch.position(sketch.curves[arc].center)  # type: ignore[union-attr]
        joint = sketch.position(q)
        # tangent at the shared point: the radius there is perpendicular to the line
        self.assertAlmostEqual(abs(center[1] - joint[1]), 3.0, places=7)
        self.assertAlmostEqual(center[0], joint[0], places=7)

    def test_angle_dimension_in_degrees(self) -> None:
        sketch = Sketch2D()
        l1 = sketch.add_line((0, 0), (10, 0))
        l2 = sketch.add_line((0, 0), (8, 5))
        self.assertTrue(sketch.constrain("horizontal", l1).ok)
        report = sketch.constrain("angle", l1, l2, value=45.0)
        self.assertTrue(report.ok, report.message)
        u = np.subtract(*reversed([sketch.position(key) for key in sketch.curve_points(l2)]))
        self.assertAlmostEqual(math.degrees(math.atan2(u[1], u[0])), 45.0, places=6)

    def test_a_plate_with_four_holes_fully_defined_then_resized(self) -> None:
        """P-03's acceptance sketch, built through the API: the holes follow the plate."""

        sketch, lines = _rectangle(100, 60)
        corners = _corners(sketch, lines)
        self.assertTrue(sketch.constrain("fix", corners[0]).ok)
        width = sketch.constrain("distance", lines[0], value=100.0)
        self.assertTrue(sketch.constrain("distance", lines[1], value=60.0).ok)
        holes = []
        for corner, (dx, dy) in zip(corners, ((10, 10), (-10, 10), (-10, -10), (10, -10)), strict=True):
            x, y = sketch.position(corner) + (dx, dy)
            hole = sketch.add_circle((x + 0.7, y - 0.4), 3.5)
            centre = sketch.curves[hole].center  # type: ignore[union-attr]
            self.assertTrue(sketch.constrain("horizontal_distance", corner, centre, value=10.0).ok)
            self.assertTrue(sketch.constrain("vertical_distance", corner, centre, value=10.0).ok)
            holes.append(hole)
        self.assertTrue(sketch.constrain("diameter", holes[0], value=8.0).ok)
        for hole in holes[1:]:
            self.assertTrue(sketch.constrain("equal", holes[0], hole).ok)
        self.assertEqual(sketch.dof(), 0)
        self.assertTrue(set(holes) <= sketch.fully_defined())
        self.assertTrue(sketch.set_value(width.constraint_id or "", 140.0).ok)
        far_hole = sketch.position(sketch.curves[holes[2]].center)  # type: ignore[union-attr]
        np.testing.assert_allclose(far_hole, (130.0, 50.0), atol=1e-7)
        self.assertAlmostEqual(sketch.radius(holes[3]), 4.0, places=8)


class PersistenceAndEditingTests(unittest.TestCase):
    def test_round_trip_keeps_geometry_constraints_and_dof(self) -> None:
        sketch, lines = _rectangle()
        self.assertTrue(sketch.constrain("distance", lines[0], value=12.0).ok)
        sketch.add_arc((30, 0), (35, 0), (30, 5))
        copy = Sketch2D.from_dict(sketch.to_dict())
        self.assertEqual(copy.dof(), sketch.dof())
        self.assertEqual([item.kind for item in copy.constraints], [item.kind for item in sketch.constraints])
        new_point = copy.add_point(0, 0)
        self.assertNotIn(new_point, sketch.points)  # ids keep counting after a reload

    def test_deleting_a_line_takes_its_constraints_and_lonely_points(self) -> None:
        sketch, lines = _rectangle()
        before = len(sketch.points)
        sketch.delete(lines[0])
        self.assertEqual(len(sketch.points), before)  # its corners still belong to the sides
        self.assertNotIn(lines[0], {ref for item in sketch.constraints for ref in item.refs})
        lone = sketch.add_line((50, 50), (60, 50))
        sketch.delete(lone)
        self.assertEqual(len(sketch.points), before)

    def test_wrong_references_are_explained(self) -> None:
        sketch = Sketch2D()
        c = sketch.add_circle((0, 0), 5)
        with self.assertRaises(ValueError) as raised:
            sketch.constrain("parallel", c, c)
        self.assertIn("takes", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
