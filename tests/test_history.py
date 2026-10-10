"""P-01: the design history - features recorded, replayed after an edit, saved and reopened.

The housing scan's section sketch is extruded (depths from the scan), and a 2 mm slot is cut
from the body by a second extrude of the same sketch. Editing the first extrude, or the
sketch itself, replays what comes after; the history survives save and reopen and replays
to the same volume.
"""

from __future__ import annotations

import json
import unittest

import numpy as np

try:
    import cadquery  # noqa: F401
    import OCP  # noqa: F401

    HAVE_KERNEL = True
except ImportError:  # pragma: no cover
    HAVE_KERNEL = False

from openretop.application.regeneration import extrude_ranges
from openretop.modeling.persistence import model_from_dict, model_to_dict
from test_extrude import BLOCK_AREA, HOUSING_VOLUME, POCKET_AREA
from test_section_sketch import _composition_with

WALL_AREA = BLOCK_AREA - POCKET_AREA  # the housing's cross-section where the pocket goes through


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class HistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.composition = _composition_with("housing")
        self.modeling = self.composition.modeling_controller
        self.model = self.composition.state.model

    def dispatch(self, action: str, payload: dict | None = None):
        result = self.composition.workflow.dispatch(action, payload or {})
        self.assertTrue(result.success, (action, result.errors))
        return result

    def body(self):
        (body,) = [entity for entity in self.model.entities if entity.kind == "solid"]
        return body

    def sketch_and_extrude(self, *, front: float | None = None) -> None:
        self.dispatch("model.section_sketch")
        self.dispatch("model.section_create")
        self.dispatch("model.extrude")
        if front is not None:
            self.assertTrue(self.modeling.configure(extrude_auto=False, extrude_front=front, extrude_back=0.0).success)
        self.dispatch("model.extrude_apply")

    def cut_slot(self) -> None:
        profile = next(entity for entity in self.model.entities if entity.kind == "profile")
        self.model.selected_ids = [profile.id]
        self.dispatch("model.extrude")
        self.assertTrue(self.modeling.configure(extrude_mode="cut", extrude_auto=False, extrude_front=2.0, extrude_back=0.0).success)
        self.dispatch("model.extrude_apply")

    def test_features_are_recorded_and_the_body_keeps_its_id(self) -> None:
        self.sketch_and_extrude(front=10.0)
        body_id = self.body().id
        self.cut_slot()
        kinds = [(feature.kind, feature.inputs.get("mode")) for feature in self.model.timeline.features]
        self.assertEqual(kinds, [("sketch", None), ("extrude", "new"), ("extrude", "cut")])
        self.assertEqual(self.body().id, body_id)  # the cut changed Body 1, it did not make another
        self.assertEqual([feature.entity for feature in self.model.timeline.features[1:]], [body_id, body_id])
        self.assertAlmostEqual(self.body().stats["volume"], WALL_AREA * 8.0, delta=10.0)

    def test_editing_an_early_feature_regenerates_the_rest(self) -> None:
        self.sketch_and_extrude(front=10.0)
        self.cut_slot()
        first_extrude = self.model.timeline.features[1]
        self.dispatch("model.edit_feature", {"feature": first_extrude.id, "front": 20.0})
        # 20 mm tall now, and the 2 mm slot is cut from the taller body
        self.assertAlmostEqual(self.body().stats["volume"], WALL_AREA * 18.0, delta=20.0)
        self.assertTrue(all(feature.status == "ok" for feature in self.model.timeline.features))
        self.dispatch("edit.undo")
        self.assertAlmostEqual(self.body().stats["volume"], WALL_AREA * 8.0, delta=10.0)
        self.assertEqual(self.model.timeline.features[1].inputs["front"], 10.0)

    def test_editing_the_sketch_rebuilds_the_extrude_from_it(self) -> None:
        self.sketch_and_extrude(front=10.0)
        profile = next(entity for entity in self.model.entities if entity.kind == "profile")
        before = self.body().stats["volume"]
        self.assertTrue(self.modeling.section_edit_entity(profile.id).success)
        loop, index, position = self.modeling.section_vertices_world()[0]
        frame = self.modeling.section_frame()
        moved = np.asarray(position) + 3.0 * np.asarray(frame["u"]) + 2.0 * np.asarray(frame["v"])
        self.assertTrue(self.modeling.section_move_vertex(loop, index, moved, final=True).success)
        self.dispatch("model.section_create")
        sketch, extrude = self.model.timeline.features
        self.assertEqual((sketch.status, extrude.status), ("ok", "ok"))
        self.assertEqual(self.model.get(profile.id).name, profile.name)  # the same sketch, edited
        # the body is what a fresh extrude of the edited sketch gives
        from openretop.cad_kernel import jobs

        loops = sketch.inputs["loops"]
        expected = jobs.extrude(sketch.inputs["frame"], loops, extrude_ranges(extrude.inputs, len(loops)))["volume"]
        self.assertAlmostEqual(self.body().stats["volume"], expected, delta=1e-6 * expected)
        self.assertNotAlmostEqual(self.body().stats["volume"], before, delta=1.0)

    def test_the_history_replays_from_the_saved_file_to_the_same_volume(self) -> None:
        self.sketch_and_extrude()  # depths measured on the scan, the pocket stopping at its floor
        self.cut_slot()
        volume = self.body().stats["volume"]
        self.assertAlmostEqual(volume, HOUSING_VOLUME - WALL_AREA * 2.0, delta=0.005 * HOUSING_VOLUME)
        saved = json.loads(json.dumps(model_to_dict(self.model)))

        reopened = _composition_with("housing")
        model, warnings = model_from_dict(saved)
        self.assertEqual(warnings, [])
        reopened.state.model = model
        self.assertTrue(all(feature.result is None for feature in model.timeline.features))  # nothing cached
        result = reopened.modeling_controller.rebuild()
        self.assertTrue(result.success, result.errors)
        (body,) = [entity for entity in model.entities if entity.kind == "solid"]
        self.assertEqual(body.id, self.body().id)
        self.assertAlmostEqual(body.stats["volume"], volume, delta=1e-6 * volume)
        self.assertTrue(all(feature.status == "ok" for feature in model.timeline.features))

    def test_a_failed_feature_is_reported_and_the_ones_after_it_skipped(self) -> None:
        self.sketch_and_extrude(front=10.0)
        self.cut_slot()
        first_extrude, cut = self.model.timeline.features[1:]
        result = self.modeling.edit_feature(first_extrude.id, mode="add")  # nothing to add to
        self.assertTrue(result.success)
        self.assertEqual((first_extrude.status, cut.status), ("failed", "skipped"))
        self.assertIn("no body", first_extrude.message)
        self.assertIn("failed", result.status)
        self.assertTrue(self.modeling.edit_feature(first_extrude.id, mode="new").success)
        self.assertEqual((first_extrude.status, cut.status), ("ok", "ok"))
        self.assertAlmostEqual(self.body().stats["volume"], WALL_AREA * 8.0, delta=10.0)

    def test_deleting_the_sketch_keeps_the_body_as_a_base_feature(self) -> None:
        self.sketch_and_extrude(front=10.0)
        volume = self.body().stats["volume"]
        profile = next(entity for entity in self.model.entities if entity.kind == "profile")
        self.assertTrue(self.modeling.delete((profile.id,)).success)
        (base,) = self.model.timeline.features
        self.assertEqual((base.kind, base.entity), ("base", self.body().id))
        self.assertTrue(self.modeling.rebuild().success)
        self.assertAlmostEqual(self.body().stats["volume"], volume, delta=1e-6 * volume)
        saved = model_from_dict(json.loads(json.dumps(model_to_dict(self.model))))[0]
        self.assertEqual(saved.timeline.features[0].inputs["brep"], base.inputs["brep"])

    def test_deleting_the_body_drops_its_features(self) -> None:
        self.sketch_and_extrude(front=10.0)
        self.assertTrue(self.modeling.delete((self.body().id,)).success)
        self.assertEqual([feature.kind for feature in self.model.timeline.features], ["sketch"])


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class HistoryInTheWindowTests(unittest.TestCase):
    def test_history_rows_and_editing_an_extrude_in_properties(self) -> None:
        from PySide6.QtWidgets import QApplication

        from openretop.presentation.qt.main_window import OpenRetopV3Window

        QApplication.instance() or QApplication([])
        composition = _composition_with("housing")
        window = OpenRetopV3Window(composition)
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        for action in ("model.section_sketch", "model.section_create", "model.extrude"):
            self.assertTrue(window._dispatch_application_action(action))
        self.assertTrue(composition.modeling_controller.configure(extrude_auto=False, extrude_front=10.0, extrude_back=0.0).success)
        self.assertTrue(window._dispatch_application_action("model.extrude_apply"))
        self.assertTrue(window._dispatch_application_action("model.finish"))
        labels = {node.id: node.label for node in window._scene_nodes()}
        self.assertEqual(labels["history"], "History")
        sketch, extrude = composition.state.model.timeline.features
        self.assertEqual(labels[f"feature:{extrude.id}"], "Extrude 1")

        window._on_tree_selection(type("Selection", (), {"ids": (f"feature:{extrude.id}",)})())
        self.assertEqual(window._scene_model.selected_ids, (f"feature:{extrude.id}",))
        fields = {field.id: field for field in window._inspector_fields()}
        self.assertEqual(fields["feature_front"].value, 10.0)
        self.assertEqual(fields["feature_mode"].value, "new")

        window._on_inspector_value("feature_front", 20.0)
        (body,) = [entity for entity in composition.state.model.entities if entity.kind == "solid"]
        self.assertAlmostEqual(body.stats["volume"], WALL_AREA * 20.0, delta=20.0)
        self.assertTrue(composition.undo.can_undo)
        self.assertEqual({field.id: field for field in window._inspector_fields()}["feature_front"].value, 20.0)


if __name__ == "__main__":
    unittest.main()
