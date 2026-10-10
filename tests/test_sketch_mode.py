"""P-03 / P-05: the 3D Sketch tool - draw on a plane, constrain, dimension, finish, extrude.

The plan's acceptance: draw a plate with four holes, fully define it, change a dimension,
the part follows.
"""

from __future__ import annotations

import math
import unittest

import numpy as np

try:
    import cadquery  # noqa: F401
    import OCP  # noqa: F401

    HAVE_KERNEL = True
except ImportError:  # pragma: no cover
    HAVE_KERNEL = False

from openretop.application.sketch_mode import PLANES, SketchMode

SNAP = 0.5


def corners_of(mode: SketchMode) -> list[str]:
    return [point for point in mode.sketch.points]


class DrawingTests(unittest.TestCase):
    def test_a_line_chain_closes_on_its_first_point_with_horizontal_and_vertical_kept(self) -> None:
        mode = SketchMode()
        for xy in ((0, 0), (10, 0.2), (10.1, 6), (0, 6)):
            mode.click(xy, SNAP)
        self.assertEqual(mode.click((0.1, 0.1), SNAP), "Shape closed")  # back on the first point
        self.assertEqual(len(mode.sketch.curves), 4)
        self.assertEqual(len(mode.sketch.points), 4)  # joined: no doubled corners
        kinds = sorted(constraint.kind for constraint in mode.sketch.constraints)
        self.assertEqual(kinds, ["horizontal", "horizontal", "vertical", "vertical"])  # drawn within 3 degrees
        self.assertEqual(mode.pending, [])

    def test_a_point_clicked_on_a_curve_stays_on_it(self) -> None:
        mode = SketchMode()
        mode.set_tool("circle")
        mode.click((0, 0), SNAP)
        mode.click((5, 0), SNAP)
        mode.set_tool("line")
        mode.click((0, 5.1), SNAP)  # on the circle (within the snap distance)
        mode.click((0, 12), SNAP)
        (on_circle,) = [item for item in mode.sketch.constraints if item.kind == "coincident"]
        circle = next(iter(mode.sketch.curves))
        self.assertEqual(on_circle.refs[1], circle)
        # on the circle (everything moved the least: the point, the circle's centre and size a little)
        center = mode.sketch.position(mode.sketch.curves[circle].center)  # type: ignore[union-attr]
        distance = float(np.linalg.norm(mode.sketch.position(on_circle.refs[0]) - center))
        self.assertAlmostEqual(distance, mode.sketch.radius(circle), places=8)
        self.assertLess(abs(mode.sketch.radius(circle) - 5.0), 0.1)

    def test_rectangle_circle_and_arc(self) -> None:
        mode = SketchMode()
        mode.set_tool("rectangle")
        mode.click((0, 0), SNAP)
        self.assertEqual(mode.click((20, 10), SNAP), "Rectangle drawn")
        mode.set_tool("circle")
        mode.click((5, 5), SNAP)
        mode.click((7, 5), SNAP)
        mode.set_tool("arc")
        mode.click((40, 0), SNAP)
        mode.click((45, 0), SNAP)
        mode.click((40, 7), SNAP)  # projected onto the arc's circle
        kinds = sorted(type(curve).__name__ for curve in mode.sketch.curves.values())
        self.assertEqual(kinds, ["Arc", "Circle", "Line", "Line", "Line", "Line"])
        arc = next(curve for curve in mode.sketch.curves.values() if type(curve).__name__ == "Arc")
        self.assertAlmostEqual(float(np.linalg.norm(mode.sketch.position(arc.end) - (40, 0))), 5.0, places=8)  # type: ignore[union-attr]

    def test_dimension_kind_follows_the_selection(self) -> None:
        mode = SketchMode()
        line = mode.sketch.add_line((0, 0), (10, 0))
        other = mode.sketch.add_line((0, 5), (10, 5))
        slanted = mode.sketch.add_line((0, 0), (8, 6))
        circle = mode.sketch.add_circle((20, 0), 3)
        arc = mode.sketch.add_arc((30, 0), (33, 0), (30, 3))
        p, q = mode.sketch.curve_points(line)
        cases = {
            (line,): "distance",
            (p, q): "distance",
            (line, other): "distance",  # parallel
            (line, slanted): "angle",
            (circle,): "diameter",
            (arc,): "radius",
            (p, other): "distance",
        }
        for selection, kind in cases.items():
            mode.select(list(selection))
            self.assertEqual(mode.dimension_kind(), kind, selection)
        mode.select([circle, arc])
        self.assertIsNone(mode.dimension_kind())
        self.assertIn("concentric", mode.available())
        self.assertIn("equal", mode.available())
        self.assertNotIn("dimension", mode.available())

    def test_a_click_anywhere_along_a_long_line_picks_it(self) -> None:
        mode = SketchMode()
        line = mode.sketch.add_line((0, 0), (300, 0))
        mode.set_tool("select")
        for x in (1.0, 77.7, 150.0, 299.0):
            mode.click((x, 0.3), SNAP)
            self.assertEqual(mode.selected, [line], x)

    def test_construction_curves_and_delete(self) -> None:
        mode = SketchMode()
        line = mode.sketch.add_line((0, 0), (10, 0))
        mode.select([line])
        self.assertEqual(mode.toggle_construction(), 1)
        self.assertTrue(mode.sketch.curves[line].construction)
        mode.select([line])
        self.assertEqual(mode.delete_selected(), 1)
        self.assertEqual(mode.sketch.curves, {})
        self.assertEqual(mode.sketch.points, {})

    def test_the_view_shows_defined_geometry_dimensions_and_glyphs(self) -> None:
        mode = SketchMode()
        line = mode.sketch.add_line((0, 0), (10, 0))
        mode.sketch.constrain("horizontal", line)
        mode.select([line])
        self.assertTrue(mode.dimension(12.0).ok)
        view = mode.view()
        texts = sorted(label["text"] for label in view["labels"])
        self.assertEqual(texts, ["12", "H"])
        self.assertEqual(view["dof"], 2)
        self.assertFalse(view["defined"])
        self.assertTrue(mode.sketch.constrain("fix", mode.sketch.curve_points(line)[0]).ok)
        view = mode.view()
        self.assertTrue(view["defined"])
        self.assertTrue(all(curve["defined"] for curve in view["curves"]))

    def test_planes_are_the_section_sketch_planes(self) -> None:
        from openretop.application.modeling_controller import SECTION_PLANES

        self.assertIs(PLANES, SECTION_PLANES)
        mode = SketchMode(plane="XZ", offset=4.0)
        world = mode.to_world((3.0, 2.0))[0]
        np.testing.assert_allclose(mode.to_plane(world), (3.0, 2.0))
        self.assertAlmostEqual(float(world @ np.array(PLANES["XZ"][2])), 4.0)


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class PlateAcceptanceTests(unittest.TestCase):
    """Draw a plate with four holes, fully define it, extrude, change a dimension: the part follows."""

    def setUp(self) -> None:
        from openretop.bootstrap import create_application
        from openretop.cad_kernel.worker import KernelWorker
        from openretop.infrastructure.settings_repository import InMemorySettingsRepository

        self.composition = create_application(settings_repository=InMemorySettingsRepository(), kernel_worker=KernelWorker(inline=True))
        self.modeling = self.composition.modeling_controller

    def dispatch(self, action: str, payload: dict | None = None):
        result = self.composition.workflow.dispatch(action, payload or {})
        self.assertTrue(result.success, (action, result.errors, result.status))
        return result

    def click(self, x: float, y: float) -> None:
        result = self.modeling.sketch2d_click((x, y, 0.0), snap=SNAP)
        self.assertTrue(result.success, result.errors)
        if result.undo_payload is not None:
            self.composition.undo.push(result.undo_payload)

    def mode(self) -> SketchMode:
        return self.modeling.session.sketch2d

    def draw_plate(self) -> tuple[str, list[str]]:
        self.dispatch("model.plane_sketch")
        self.dispatch("model.sketch2d_tool", {"tool": "rectangle"})
        self.click(0.4, -0.3)  # drawn by hand: a little off
        self.click(99.0, 61.0)
        self.dispatch("model.sketch2d_tool", {"tool": "circle"})
        for cx, cy in ((10, 10), (90, 10), (90, 50), (10, 50)):
            self.click(cx + 0.6, cy - 0.4)
            self.click(cx + 4.3, cy - 0.4)
        sketch = self.mode().sketch
        lines = [curve_id for curve_id, curve in sketch.curves.items() if type(curve).__name__ == "Line"]
        holes = [curve_id for curve_id, curve in sketch.curves.items() if type(curve).__name__ == "Circle"]
        corner = sketch.curves[lines[0]].p1  # type: ignore[union-attr]
        self.modeling.sketch2d_select([corner])
        self.dispatch("model.sketch2d_constrain", {"kind": "fix"})
        self.modeling.sketch2d_select([lines[0]])
        width = self.dispatch("model.sketch2d_dimension", {"value": 100.0})
        self.modeling.sketch2d_select([lines[1]])
        self.dispatch("model.sketch2d_dimension", {"value": 60.0})
        self.modeling.sketch2d_select([holes[0]])
        self.dispatch("model.sketch2d_dimension", {"value": 8.0})
        for hole in holes[1:]:
            self.modeling.sketch2d_select([holes[0], hole])
            self.dispatch("model.sketch2d_constrain", {"kind": "equal"})
        corners = [sketch.curves[line].p1 for line in lines]  # type: ignore[union-attr]
        for corner_id, hole in zip(corners, holes, strict=True):
            center = sketch.curves[hole].center  # type: ignore[union-attr]
            for kind in ("horizontal_distance", "vertical_distance"):
                self.modeling.sketch2d_select([corner_id, center])
                self.dispatch("model.sketch2d_dimension", {"value": 10.0, "kind": kind})
        self.assertEqual(sketch.dof(), 0)
        self.assertTrue(self.modeling.sketch2d_view_world()["defined"])
        width_id = next(item.id for item in sketch.constraints if item.kind == "distance" and item.refs == (lines[0],))
        self.assertIn("13 degree(s) of freedom", width.status)  # each step reports what is left
        return width_id, holes

    def test_draw_fully_define_extrude_and_the_part_follows_a_dimension(self) -> None:
        width_id, holes = self.draw_plate()
        self.dispatch("model.sketch2d_finish")
        self.assertFalse(self.modeling.active)
        model = self.composition.state.model
        (sketch_entity,) = model.entities
        self.assertEqual(sketch_entity.name, "3D Sketch 1")
        self.dispatch("model.extrude")
        self.assertTrue(self.modeling.configure(extrude_auto=False, extrude_front=10.0, extrude_back=0.0).success)
        self.dispatch("model.extrude_apply")
        self.dispatch("model.finish")
        hole_area = math.pi * 16.0
        body = next(entity for entity in model.entities if entity.kind == "solid")
        self.assertAlmostEqual(body.stats["volume"], (6000 - 4 * hole_area) * 10, delta=1.0)

        # change the width to 140: the holes keep 10 from their corners, the part follows
        self.dispatch("model.section_edit", {"entity": sketch_entity.id})
        self.assertEqual(self.modeling.tool, "plane_sketch")
        self.dispatch("model.sketch2d_set_dimension", {"constraint": width_id, "value": 140.0})
        self.dispatch("model.sketch2d_finish")
        body = next(entity for entity in model.entities if entity.kind == "solid")
        self.assertAlmostEqual(body.stats["volume"], (8400 - 4 * hole_area) * 10, delta=1.0)
        self.assertTrue(all(feature.status == "ok" for feature in model.timeline.features))
        # and undo puts the 100-wide plate back
        self.dispatch("edit.undo")
        body = next(entity for entity in model.entities if entity.kind == "solid")
        self.assertAlmostEqual(body.stats["volume"], (6000 - 4 * hole_area) * 10, delta=1.0)

    def test_extruding_picked_regions_only(self) -> None:
        _width, holes = self.draw_plate()
        self.dispatch("model.sketch2d_finish")
        self.dispatch("model.extrude")
        self.assertTrue(self.modeling.configure(extrude_auto=False, extrude_front=5.0, extrude_back=0.0).success)
        self.assertTrue(self.modeling.extrude_pick_region((10.0, 10.0, 0.0)).success)  # inside the first hole
        self.dispatch("model.extrude_apply")
        model = self.composition.state.model
        body = next(entity for entity in model.entities if entity.kind == "solid")
        self.assertAlmostEqual(body.stats["volume"], math.pi * 16.0 * 5.0, delta=0.05)  # one 8 mm pin
        (extrude,) = [feature for feature in model.timeline.features if feature.kind == "extrude"]
        self.assertEqual(extrude.inputs["regions"], [holes[0]])
        # replayed from the start, the picked region is found again
        self.assertTrue(self.modeling.rebuild().success)
        body = next(entity for entity in model.entities if entity.kind == "solid")
        self.assertAlmostEqual(body.stats["volume"], math.pi * 16.0 * 5.0, delta=0.05)

    def test_undo_inside_the_tool(self) -> None:
        self.dispatch("model.plane_sketch")
        self.dispatch("model.sketch2d_tool", {"tool": "circle"})
        self.click(0, 0)
        self.click(5, 0)
        self.assertEqual(len(self.mode().sketch.curves), 1)
        self.dispatch("edit.undo")
        self.assertEqual(len(self.mode().sketch.curves), 0)
        self.dispatch("edit.redo")
        self.assertEqual(len(self.mode().sketch.curves), 1)

    def test_finish_with_nothing_drawn_says_so(self) -> None:
        self.dispatch("model.plane_sketch")
        result = self.composition.workflow.dispatch("model.sketch2d_finish", {})
        self.assertFalse(result.success)
        self.assertIn("Draw something", result.status)


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class SketchInTheWindowTests(unittest.TestCase):
    """The tool through the window's own mouse and keyboard handling (the plane hit faked)."""

    def setUp(self) -> None:
        from PySide6.QtWidgets import QApplication

        from openretop.bootstrap import create_application
        from openretop.cad_kernel.worker import KernelWorker
        from openretop.infrastructure.settings_repository import InMemorySettingsRepository
        from openretop.presentation.qt.main_window import OpenRetopV3Window

        QApplication.instance() or QApplication([])
        self.composition = create_application(settings_repository=InMemorySettingsRepository(), kernel_worker=KernelWorker(inline=True))
        self.window = OpenRetopV3Window(self.composition)
        self.addCleanup(lambda: (self.window.set_project_dirty(False), self.window.close()))

    def click(self, x: float, y: float) -> None:
        from unittest.mock import patch

        window = self.window
        window.viewport._last_pointer_release_was_click = True
        with patch.object(window, "_plane_hit", return_value=np.array([x, y, 0.0])), patch.object(window, "_sketch2d_snap", return_value=SNAP):
            window._on_viewport_pointer("left_release", 0, 0, None)

    def key(self, key: object) -> None:
        self.assertTrue(self.window._handle_tool_key(key, ""))

    def test_draw_dimension_and_finish_with_the_mouse_keys_and_panel(self) -> None:
        from PySide6.QtCore import Qt

        window, modeling = self.window, self.composition.modeling_controller
        window._invoke_from_ui("model.plane_sketch")  # as the toolbar, menu or Ctrl+K palette start it
        self.assertEqual(window.active_workspace, "solid")
        self.assertTrue(modeling.active)
        self.assertEqual(window.surfacing_panel.title.text(), "3D Sketch")
        self.assertEqual(window.viewport.left_capture_owner, "plane_sketch")
        self.assertTrue(window._surfacing_claims_key(Qt.Key.Key_R))  # Rectangle here, not Rotate
        self.key(Qt.Key.Key_R)
        self.assertEqual(modeling.session.sketch2d.tool, "rectangle")
        self.click(0.0, 0.0)
        self.click(30.0, 20.0)
        sketch = modeling.session.sketch2d.sketch
        self.assertEqual(len(sketch.curves), 4)
        self.assertTrue(self.composition.undo.can_undo)  # each click is one undo step
        # select the bottom edge and dimension it from the panel
        self.key(Qt.Key.Key_S)
        self.click(15.0, 0.0)
        bottom = modeling.session.sketch2d.selected
        self.assertEqual(len(bottom), 1)
        window.refresh()
        panel = window.surfacing_panel
        self.assertTrue(panel.sketch2d_constraint_buttons["horizontal"].isEnabled())  # fits a line (it may turn out redundant)
        self.assertFalse(panel.sketch2d_constraint_buttons["concentric"].isEnabled())  # needs two circles
        self.assertTrue(panel.sketch2d_dimension.isEnabled())
        panel.sketch2d_dimension.click()
        labels = [item.text for item in window._surfacing_annotations()]
        self.assertIn("30", labels)
        self.assertGreater(window.viewport.annotation_overlay.visible_count, 0)
        # change it in the panel's list: the rectangle follows
        panel.sketch2d_constraints.setCurrentRow(panel.sketch2d_constraints.count() - 1)
        panel.sketch2d_value.setValue(45.0)
        panel._sketch2d_apply_value()
        line = sketch.curves[bottom[0]]
        self.assertAlmostEqual(float(np.linalg.norm(sketch.position(line.p2) - sketch.position(line.p1))), 45.0, places=6)  # type: ignore[union-attr]
        # Enter keeps the sketch; it shows in Model and History
        self.key(Qt.Key.Key_Return)
        self.assertFalse(modeling.active)
        names = [node.label for node in window._scene_nodes()]
        self.assertIn("3D Sketch 1", names)
        self.assertIn("Sketch 1", names)

    def test_enter_in_a_dimension_field_does_not_finish_the_sketch(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        window, modeling = self.window, self.composition.modeling_controller
        window.show()
        window._invoke_from_ui("model.plane_sketch")
        window._dispatch_application_action("model.sketch2d_tool", {"tool": "rectangle"})
        self.click(0.0, 0.0)
        self.click(30.0, 20.0)
        line = next(iter(modeling.session.sketch2d.sketch.curves))
        modeling.sketch2d_select([line])
        window._dispatch_application_action("model.sketch2d_dimension")
        window.refresh()
        panel = window.surfacing_panel
        panel.sketch2d_constraints.setCurrentRow(panel.sketch2d_constraints.count() - 1)
        field = panel.sketch2d_value.lineEdit()
        field.setFocus()
        field.selectAll()
        QTest.keyClicks(field, "42")
        QTest.keyClick(field, Qt.Key_Return)  # Qt passes this Enter on to the window as well
        QTest.qWait(20)
        self.assertEqual(modeling.tool, "plane_sketch")  # still sketching (it used to finish here)
        sketch = modeling.session.sketch2d.sketch
        self.assertAlmostEqual(float(np.linalg.norm(np.subtract(*[sketch.position(p) for p in sketch.curve_points(line)]))), 42.0, places=6)
        self.assertTrue(window._handle_tool_key(Qt.Key.Key_Return, ""))  # Enter in the view still finishes
        self.assertFalse(modeling.active)

    def test_extrude_picks_regions_by_click(self) -> None:
        window, modeling = self.window, self.composition.modeling_controller
        self.assertTrue(window._dispatch_framework_action("model.plane_sketch"))
        window._dispatch_application_action("model.sketch2d_tool", {"tool": "rectangle"})
        self.click(0.0, 0.0)
        self.click(40.0, 20.0)
        window._dispatch_application_action("model.sketch2d_tool", {"tool": "circle"})
        self.click(10.0, 10.0)
        self.click(14.0, 10.0)
        window._dispatch_application_action("model.sketch2d_finish")
        self.assertTrue(window._dispatch_framework_action("model.extrude"))
        self.assertEqual(window.viewport.left_capture_owner, "extrude_pick")
        self.click(30.0, 10.0)  # the plate, outside the hole
        self.assertEqual(len(modeling.session.extrude_regions), 1)
        self.assertTrue(window._sketch2d_lines())  # the picked region is outlined (over the scene)
        self.assertTrue(modeling.configure(extrude_auto=False, extrude_front=3.0, extrude_back=0.0).success)
        window._dispatch_application_action("model.extrude_apply")
        body = next(entity for entity in self.composition.state.model.entities if entity.kind == "solid")
        self.assertAlmostEqual(body.stats["volume"], (800 - math.pi * 16) * 3.0, delta=0.5)


if __name__ == "__main__":
    unittest.main()
