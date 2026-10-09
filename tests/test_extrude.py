"""S-14: Extrude a sketch into a solid, its depth from the scan.

The housing's one section sketch (outer wall + pocket) extrudes, with depths measured on the
scan, into the housing itself: the block over its full height and the pocket only down to its
floor. Typed depths cut holes through, as in any CAD; draft, cut and undo work; the window's
panel previews live and Enter creates.
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

from test_section_sketch import _composition_with

BLOCK_AREA = 60 * 40 - (4 - math.pi) * 9  # R3 corners
POCKET_AREA = 40 * 24 - (4 - math.pi) * 4  # R2 corners
HOUSING_VOLUME = BLOCK_AREA * 25 - POCKET_AREA * 15


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class ExtrudeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = _composition_with("housing")

    def setUp(self) -> None:
        self.composition = _composition_with("housing")
        self.modeling = self.composition.modeling_controller

    def dispatch(self, action: str, payload: dict | None = None):
        result = self.composition.workflow.dispatch(action, payload or {})
        self.assertTrue(result.success, (action, result.errors))
        return result

    def sketch(self) -> None:
        self.dispatch("model.section_sketch")
        self.dispatch("model.section_create")

    def test_one_extrude_from_the_scan_makes_the_housing_with_its_pocket_floor(self) -> None:
        self.sketch()
        self.dispatch("model.extrude")
        session = self.modeling.session
        self.assertEqual((session.tool, session.extrude_mode), ("extrude", "new"))
        self.assertAlmostEqual(session.extrude_front, 12.5, delta=0.05)
        self.assertAlmostEqual(session.extrude_back, 12.5, delta=0.05)
        ((hole, (low, high)),) = session.extrude_holes.items()
        self.assertAlmostEqual(low, -2.5, delta=0.05)  # the pocket's floor
        self.assertAlmostEqual(high, 12.5, delta=0.05)
        self.dispatch("model.extrude_preview")
        self.assertAlmostEqual(session.preview["volume"], HOUSING_VOLUME, delta=0.003 * HOUSING_VOLUME)
        self.dispatch("model.extrude_apply")
        model = self.composition.state.model
        sketch, body = model.entities
        self.assertEqual((body.kind, body.tool), ("solid", "extrude"))
        self.assertTrue(body.stats["solid"])
        self.assertAlmostEqual(body.stats["volume"], HOUSING_VOLUME, delta=0.003 * HOUSING_VOLUME)
        self.assertFalse(sketch.visible)  # used up, out of the way
        self.assertEqual(body.sources, (sketch.id,))

        self.composition.workflow.dispatch("edit.undo", {})
        self.assertEqual([entity.kind for entity in model.entities], ["profile"])
        self.assertTrue(model.entities[0].visible)

    def test_typed_depths_cut_holes_through_and_draft_tapers(self) -> None:
        self.sketch()
        self.dispatch("model.extrude")
        self.assertTrue(self.modeling.configure(extrude_auto=False, extrude_front=10.0, extrude_back=0.0).success)
        self.dispatch("model.extrude_preview")
        self.assertAlmostEqual(self.modeling.session.preview["volume"], (BLOCK_AREA - POCKET_AREA) * 10.0, delta=10.0)
        self.assertTrue(self.modeling.configure(extrude_draft=2.0).success)
        self.dispatch("model.extrude_preview")
        drafted = self.modeling.session.preview
        self.assertTrue(drafted["solid"])
        self.assertLess(drafted["volume"], (BLOCK_AREA - POCKET_AREA) * 10.0)  # outer walls lean in, the hole widens

    def test_a_second_extrude_cuts_from_the_body(self) -> None:
        self.sketch()
        self.dispatch("model.extrude")
        self.dispatch("model.extrude_apply")
        model = self.composition.state.model
        body = next(entity for entity in model.entities if entity.kind == "solid")
        before = body.stats["volume"]
        # the same sketch again, as a 2 mm cut just above its plane: a slot through the walls
        model.selected_ids = [model.entities[0].id]
        self.dispatch("model.extrude")
        self.assertEqual(self.modeling.session.extrude_target, body.id)
        self.assertTrue(self.modeling.configure(extrude_mode="cut", extrude_auto=False, extrude_front=2.0, extrude_back=0.0).success)
        self.dispatch("model.extrude_apply")
        solids = [entity for entity in model.entities if entity.kind == "solid"]
        self.assertEqual(len(solids), 1)  # the body was replaced, not duplicated
        self.assertEqual(solids[0].name, body.name)
        self.assertAlmostEqual(solids[0].stats["volume"], before - (BLOCK_AREA - POCKET_AREA) * 2.0, delta=10.0)

    def test_a_pocket_ending_a_hair_short_of_the_top_still_opens(self) -> None:
        # measured depths are rounded differently: a cut stopping 0.00004 below the top face
        # left a skin over the whole pocket (seen in the app as a lid)
        from openretop.cad_kernel import jobs
        from openretop.modeling.profile2d import fit_profile

        def rounded(width: float, height: float, radius: float) -> np.ndarray:
            sx, sy = width - radius, height - radius
            arcs = [
                np.c_[cx + radius * np.cos(a), cy + radius * np.sin(a)]
                for k, (cx, cy) in enumerate(((sx, -sy), (sx, sy), (-sx, sy), (-sx, -sy)))
                for a in [np.linspace(-math.pi / 2 + k * math.pi / 2, k * math.pi / 2, 30)]
            ]
            return np.vstack(arcs)

        loops = [fit_profile(rounded(*size), tolerance=0.01, closed=True).to_dict() for size in ((30, 20, 3), (20, 12, 2))]
        frame = {"origin": [0.0, 0.0, 0.0], "u": [1.0, 0.0, 0.0], "v": [0.0, 1.0, 0.0]}
        result = jobs.extrude(frame, loops, [(0.0, 12.4968), (3.0, 12.496756)])
        centers = result["vertices"][result["triangles"]].mean(axis=1)
        lid = (np.abs(centers[:, 0]) < 17) & (np.abs(centers[:, 1]) < 9) & (centers[:, 2] > 12.0)
        self.assertEqual(int(lid.sum()), 0)
        self.assertTrue(result["solid"])

    def test_without_a_sketch_extrude_says_what_to_do(self) -> None:
        result = self.composition.workflow.dispatch("model.extrude", {})
        self.assertFalse(result.success)
        self.assertIn("sketch", " ".join(result.errors).lower())


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class ExtrudeWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_toolbar_panel_live_preview_and_enter(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QToolBar

        from openretop.presentation.qt.main_window import OpenRetopV3Window

        composition = _composition_with("housing")
        window = OpenRetopV3Window(composition)
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        window.refresh()
        extrude = window._qt_actions["model.extrude"]
        self.assertIn(extrude, window.findChild(QToolBar, "toolbar_Solid_Modeling").actions())
        self.assertFalse(extrude.isEnabled())  # nothing to extrude yet
        window._qt_actions["model.section_sketch"].trigger()
        window._handle_tool_key(Qt.Key.Key_Return)  # creates the sketch
        window._handle_tool_key(Qt.Key.Key_Escape)
        window.refresh()
        self.assertTrue(extrude.isEnabled())
        extrude.trigger()
        panel = window.surfacing_panel
        self.assertEqual(panel.title.text(), "Extrude")
        self.assertAlmostEqual(panel.extrude_front.value(), 12.5, delta=0.05)
        self.assertIn("Hole 2", panel.extrude_info.text())
        session = composition.modeling_controller.session
        self.assertIsNotNone(session.preview)  # shown as the tool opens
        self.assertIn("Volume", panel.extrude_info.text())
        panel.extrude_draft.setValue(1.0)  # a change previews again at once
        self.assertIsNotNone(session.preview)
        snapshot = window.viewport.last_snapshot or window.viewport._pending_snapshot
        self.assertIn("model-preview", {item.id for item in snapshot.model_faces})
        self.assertIn("Volume", panel.extrude_info.text())
        window._handle_tool_key(Qt.Key.Key_Return)
        kinds = [entity.kind for entity in composition.state.model.entities]
        self.assertEqual(kinds, ["profile", "solid"])
        body = composition.state.model.entities[1]
        self.assertIn("model:" + body.id, set(window._scene_model.nodes))
        np.testing.assert_allclose(body.params["draft"], 1.0)


if __name__ == "__main__":
    unittest.main()
