"""Editing a sketch profile by hand (user feedback: "too automatic", sketches hard to edit).

The fitted lines and arcs are a start: corners drag in the sketch plane, an arc takes a typed
radius (a fillet stays tangent to its lines), fillets come out to a sharp corner and go in at
one, a line turns exactly horizontal / vertical, a segment goes (its neighbours meet), an open
profile closes. Edits are undoable in the tool, and a created sketch reopens for editing:
Create then replaces it.
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

import test_profile_fit
from openretop.modeling import profile_edit as edit
from openretop.modeling.profile2d import Profile2D, Segment2D, fit_profile
from test_section_sketch import HOUSING_AREA_Z0, _composition_with


def joined(profile: Profile2D) -> bool:
    count = len(profile.segments)
    pairs = range(count if profile.closed else count - 1)
    return all(np.allclose(profile.segments[k].end, profile.segments[(k + 1) % count].start, atol=1e-9) for k in pairs)


class ProfileEditTests(unittest.TestCase):
    def setUp(self) -> None:
        shapes = test_profile_fit.SyntheticProfileTests()  # its outlines, not its tests
        shapes.setUp()
        self.profile = fit_profile(shapes.noisy(shapes.rounded_rectangle(30.0, 20.0, 3.0)), tolerance=0.08)
        self.assertEqual(sorted(segment.kind for segment in self.profile.segments), ["arc"] * 4 + ["line"] * 4)

    def first(self, kind: str) -> int:
        return next(index for index, segment in enumerate(self.profile.segments) if segment.kind == kind)

    def test_radius_sharp_and_fillet(self) -> None:
        arc = self.first("arc")
        for radius in (5.0, 1.0):
            edit.set_arc_radius(self.profile, arc, radius)
            self.assertAlmostEqual(self.profile.segments[arc].radius, radius)
            self.assertAlmostEqual(abs(math.degrees(self.profile.segments[arc].angles()[1])), 90.0, places=6)  # still tangent
            self.assertTrue(joined(self.profile))
        with self.assertRaises(ValueError):
            edit.set_arc_radius(self.profile, arc, 40.0)  # bigger than the lines allow
        edit.make_sharp(self.profile, arc)
        self.assertEqual(len(self.profile.segments), 7)
        self.assertTrue(joined(self.profile))
        sharp_corner = next(
            index
            for index in range(edit.vertex_count(self.profile))
            if self.profile.segments[index - 1].kind == "line" and self.profile.segments[index % 7].kind == "line"
        )
        new_arc = edit.add_fillet(self.profile, sharp_corner, 6.0)
        self.assertAlmostEqual(self.profile.segments[new_arc].radius, 6.0)
        self.assertEqual(len(self.profile.segments), 8)
        self.assertTrue(joined(self.profile))

    def test_moving_a_corner_keeps_arcs_their_angle(self) -> None:
        corner = self.first("arc")  # the arc starts at this corner (a line ends there)
        before = abs(self.profile.segments[corner].angles()[1])
        edit.move_vertex(self.profile, corner, edit.vertex(self.profile, corner) + np.array([0.4, -0.3]))
        np.testing.assert_allclose(self.profile.segments[corner].start, edit.vertex(self.profile, corner))
        self.assertAlmostEqual(abs(self.profile.segments[corner].angles()[1]), before, places=9)
        self.assertTrue(joined(self.profile))

    def test_axis_line_and_delete_segment(self) -> None:
        line = self.first("line")
        self.profile.segments[line].end = self.profile.segments[line].end + np.array([0.0, 0.6])  # knock it off level
        edit.move_vertex(self.profile, (line + 1) % len(self.profile.segments), self.profile.segments[line].end)
        name = edit.make_axis_line(self.profile, line)
        segment = self.profile.segments[line]
        direction = segment.end - segment.start
        self.assertIn(name, ("horizontal", "vertical"))
        self.assertAlmostEqual(min(abs(direction[0]), abs(direction[1])), 0.0, places=9)
        self.assertTrue(joined(self.profile))
        edit.delete_segment(self.profile, self.first("arc"))  # a fillet goes: its lines meet
        self.assertEqual(len(self.profile.segments), 7)
        self.assertTrue(joined(self.profile))

    def test_close_an_open_profile(self) -> None:
        wall = Profile2D(
            [
                Segment2D("line", np.array([5.0, 0.0]), np.array([20.0, 0.0])),
                Segment2D("line", np.array([20.0, 0.0]), np.array([20.0, 10.0])),
                Segment2D("line", np.array([20.0, 10.0]), np.array([0.0, 10.0])),
                Segment2D("line", np.array([0.0, 10.0]), np.array([0.0, 0.0])),
                Segment2D("line", np.array([0.0, 0.0]), np.array([2.0, 0.0])),
            ],
            closed=False,
        )
        self.assertIn("one line", edit.close_profile(wall))  # the two halves of the bottom wall
        self.assertEqual(len(wall.segments), 4)
        self.assertTrue(wall.closed and joined(wall))
        bend = Profile2D(
            [Segment2D("line", np.array([0.0, 0.0]), np.array([10.0, 0.0])), Segment2D("line", np.array([10.0, 0.0]), np.array([10.0, 8.0]))]
        )
        self.assertIn("a line", edit.close_profile(bend))
        self.assertEqual(len(bend.segments), 3)
        self.assertTrue(joined(bend))


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class ProfileEditInTheToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.composition = _composition_with("housing")
        self.modeling = self.composition.modeling_controller
        self.workflow = self.composition.workflow

    def dispatch(self, action: str, payload: dict | None = None):
        result = self.workflow.dispatch(action, payload or {})
        self.assertTrue(result.success, (action, result.errors))
        return result

    def outer_arc(self) -> tuple[int, int]:
        profiles = self.modeling.session.section_profiles
        loop = max(range(len(profiles)), key=lambda index: max(abs(np.asarray(profiles[index].polyline())[:, 0])))
        return loop, next(index for index, segment in enumerate(profiles[loop].segments) if segment.kind == "arc")

    def test_a_radius_edit_is_undoable_and_reported(self) -> None:
        self.dispatch("model.section_sketch")
        self.dispatch("model.section_fit")
        loop, arc = self.outer_arc()
        self.modeling.section_select("segment", loop, arc)
        result = self.dispatch("model.section_profile_edit", {"operation": "radius", "value": 6.0})
        self.assertIn("deviation max", result.status)
        profile = self.modeling.session.section_profiles[loop]
        self.assertAlmostEqual(profile.segments[arc].radius, 6.0)
        self.assertGreater(profile.deviation, 0.5)  # R6 where the scan has R3: the deviation shows it
        self.dispatch("edit.undo")
        self.assertAlmostEqual(self.modeling.session.section_profiles[loop].segments[arc].radius, 3.0, delta=0.1)
        refused = self.workflow.dispatch("model.section_profile_edit", {"operation": "sharp"})
        self.assertFalse(refused.success)  # nothing picked after the undo

    def test_dragging_a_corner_moves_it_in_the_plane(self) -> None:
        self.dispatch("model.section_sketch")
        self.dispatch("model.section_fit")
        corners = self.modeling.section_vertices_world()
        loop, index, position = corners[0]
        target = position + np.array([1.0, 0.5, 0.0])
        self.modeling.section_move_vertex(loop, index, target)
        result = self.modeling.section_move_vertex(loop, index, target, final=True)
        self.assertTrue(result.success)
        self.assertIsNotNone(result.undo_payload)
        moved = [item for item in self.modeling.section_vertices_world() if item[:2] == (loop, index)][0][2]
        np.testing.assert_allclose(moved, target, atol=1e-9)

    def test_edit_sketch_replaces_the_sketch(self) -> None:
        self.dispatch("model.section_sketch")
        self.dispatch("model.section_create")
        model = self.composition.state.model
        original = model.entities[0]
        self.dispatch("model.finish")
        self.dispatch("model.section_edit", {"entity": original.id})
        self.assertEqual(self.modeling.session.section_editing, original.id)
        loop, arc = self.outer_arc()
        self.modeling.section_select("segment", loop, arc)
        self.dispatch("model.section_profile_edit", {"operation": "sharp"})
        self.dispatch("model.section_create")
        (updated,) = model.entities
        self.assertEqual(updated.name, original.name)
        self.assertNotEqual(updated.id, original.id)
        self.assertAlmostEqual(updated.stats["area"], HOUSING_AREA_Z0 + (4 - math.pi) * 9 / 4, delta=1.0)  # one R3 corner filled in
        self.dispatch("edit.undo")
        self.assertEqual([entity.id for entity in model.entities], [original.id])


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class ProfileEditWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_the_menu_offers_what_fits_the_pick(self) -> None:
        from openretop.presentation.qt.main_window import OpenRetopV3Window

        composition = _composition_with("housing")
        window = OpenRetopV3Window(composition)
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        window.refresh()
        window._qt_actions["model.section_sketch"].trigger()
        window.surfacing_panel.section_fit.click()
        profiles = composition.modeling_controller.session.section_profiles
        arc = next(index for index, segment in enumerate(profiles[0].segments) if segment.kind == "arc")
        window._section_vertex_at = lambda x, y: None
        window._section_segment_at = lambda x, y: (0, arc)
        window._surfacing_pointer("right_click", 5, 5, None)
        labels = [action.text() for action in window._sketch_last_menu.actions() if action.text()]
        self.assertIn("Set Radius...", labels)
        self.assertIn("Sharp Corner", labels)
        self.assertNotIn("Make Horizontal / Vertical", labels)
        window._sketch_last_menu.close()
        panel = window.surfacing_panel
        self.assertTrue(panel.section_edit_buttons["radius"].isEnabled())
        self.assertFalse(panel.section_edit_buttons["fillet"].isEnabled())
        self.assertIn("Arc R", panel.section_selection.text())


if __name__ == "__main__":
    unittest.main()
