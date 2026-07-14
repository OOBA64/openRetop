from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from application.brep_controller import BrepController, FunctionCadBackend
from application.events import EventPublisher, SceneChangedEvent, SelectionChangedEvent
from application.state import AppState
from application.surface_controller import SurfaceController
from curves.curve_state import StoredCurve, add_curve, set_selected_curves
from surfaces.four_boundary_feature import FourBoundaryPatchFeatureRecord
from surfaces.brep_state import BrepSurfaceRecord, add_brep_surface
from surfaces.loft_feature import LoftFeatureOptions, LoftFeatureRecord, add_loft_feature
from surfaces.surface_state import SurfacePatch, add_surface


def _curve(
    curve_id: str,
    points: list[list[float]],
    *,
    closed: bool = False,
    metadata: dict[str, object] | None = None,
) -> StoredCurve:
    values = np.asarray(points, dtype=float)
    return StoredCurve(
        id=curve_id,
        name=curve_id,
        section_result_id="result-a",
        plane_id="plane-a",
        original_points=values.copy(),
        fitted_points=values.copy(),
        mean_error=0.0,
        max_error=0.0,
        is_closed=closed,
        metadata=dict(metadata or {}),
    )


@dataclass
class _Build:
    success: bool = True
    cad_object: object | None = field(default_factory=object)
    reason: str = "built"
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(
        default_factory=lambda: {
            "backend": "test-cad",
            "build_method": "test-build",
        }
    )


@dataclass
class _Export:
    success: bool = True
    path: str | None = "part.step"
    reason: str = "exported"
    warnings: list[str] = field(default_factory=list)


def _backend(build: _Build | None = None) -> FunctionCadBackend:
    outcome = build or _Build()
    return FunctionCadBackend(
        planar_face_builder=lambda _curve: outcome,
        loft_builder=lambda _curves, _options: outcome,
        step_exporter=lambda _obj, _path: _Export(path=str(_path)),
    )


class SurfaceControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = AppState()
        self.events = EventPublisher()
        self.scene_events: list[SceneChangedEvent] = []
        self.events.subscribe(SceneChangedEvent, self.scene_events.append)
        self.controller = SurfaceController(self.state, self.events)

    def test_fill_returns_task75_result_events_and_atomic_undo(self) -> None:
        source = _curve(
            "curve-a",
            [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 0]],
            closed=True,
            metadata={"creation_type": "region_boundary", "source_region_id": "r1"},
        )
        add_curve(self.state.curve_collection, source)
        set_selected_curves(self.state.curve_collection, [source.id])

        result = self.controller.create_fill(surface_id="surface-a")

        self.assertTrue(result.success)
        self.assertTrue(result.changed)
        self.assertTrue(result.dirty)
        self.assertIsNotNone(result.undo_payload)
        self.assertEqual(self.state.surface_collection.surfaces[0].id, "surface-a")
        self.assertEqual(
            self.state.surface_collection.surfaces[0].metadata["source_region_ids"],
            ["r1"],
        )
        self.assertEqual(self.scene_events[-1].reason, "surface_created")

        result.undo_payload.undo()
        self.assertEqual(self.state.surface_collection.surfaces, [])
        result.undo_payload.redo()
        self.assertEqual(self.state.surface_collection.surfaces[0].id, "surface-a")

    def test_fill_failure_does_not_dirty_or_mutate(self) -> None:
        result = self.controller.create_fill()

        self.assertFalse(result.success)
        self.assertFalse(result.changed)
        self.assertFalse(result.dirty)
        self.assertEqual(self.state.surface_collection.surfaces, [])

    def test_four_curve_feature_is_restored_with_surface_on_redo(self) -> None:
        curves = [
            _curve("bottom", [[0, 0, 0], [1, 0, 0]]),
            _curve("right", [[1, 0, 0], [1, 1, 0]]),
            _curve("top", [[0, 1, 0], [1, 1, 0]]),
            _curve("left", [[0, 0, 0], [0, 1, 0]]),
        ]
        for curve in curves:
            add_curve(self.state.curve_collection, curve)
        set_selected_curves(self.state.curve_collection, [curve.id for curve in curves])

        result = self.controller.create_four_curve_patch(
            surface_id="surface-four", feature_id="feature-four"
        )

        self.assertTrue(result.success, result.errors)
        self.assertEqual(
            self.state.four_boundary_feature_collection.features[0].id,
            "feature-four",
        )
        result.undo_payload.undo()
        self.assertEqual(self.state.surface_collection.surfaces, [])
        self.assertEqual(self.state.four_boundary_feature_collection.features, [])
        result.undo_payload.redo()
        self.assertEqual(self.state.surface_collection.surfaces[0].id, "surface-four")
        self.assertEqual(
            self.state.four_boundary_feature_collection.features[0].id,
            "feature-four",
        )

    def test_create_selection_and_undo_are_exclusive_across_families(self) -> None:
        source = _curve(
            "selected-source",
            [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 0, 0]],
            closed=True,
        )
        add_curve(self.state.curve_collection, source)
        set_selected_curves(self.state.curve_collection, [source.id])
        self.state.selected_item = "curve"
        received: list[SelectionChangedEvent] = []
        self.events.subscribe(SelectionChangedEvent, received.append)

        result = self.controller.create_fill(surface_id="exclusive-surface")

        self.assertTrue(result.success, result.errors)
        self.assertEqual(self.state.curve_collection.selected_curve_ids, set())
        self.assertEqual(
            self.state.surface_collection.selected_surface_ids,
            {"exclusive-surface"},
        )
        self.assertEqual(received[-1].selection.ids, ("surface:exclusive-surface",))
        result.undo_payload.undo()
        self.assertEqual(
            self.state.curve_collection.selected_curve_ids,
            {source.id},
        )
        result.undo_payload.redo()
        self.assertEqual(self.state.curve_collection.selected_curve_ids, set())

    def test_missing_and_duplicate_ids_are_structured_failures(self) -> None:
        first = _curve("first", [[0, 0, 0], [1, 0, 0]])
        second = _curve("second", [[0, 1, 0], [1, 1, 0]])
        for curve in (first, second):
            add_curve(self.state.curve_collection, curve)
        missing = self.controller.create_loft(
            curve_ids=(first.id, second.id, "missing")
        )
        self.assertFalse(missing.success)
        self.assertEqual(missing.metadata["missing_curve_ids"], ("missing",))

        set_selected_curves(self.state.curve_collection, [first.id, second.id])
        created = self.controller.create_loft(surface_id="duplicate")
        self.assertTrue(created.success, created.errors)
        duplicate = self.controller.create_loft(
            curve_ids=(first.id, second.id),
            surface_id="duplicate",
        )
        self.assertFalse(duplicate.success)
        self.assertEqual(duplicate.metadata["duplicate_surface_id"], "duplicate")

    def test_delete_preview_prunes_linked_features_and_undo_restores_brep_selection(self) -> None:
        preview = SurfacePatch("preview", "Preview", [], "preview")
        brep = BrepSurfaceRecord("brep", "BREP", [], "loft_surface", "test")
        add_surface(self.state.surface_collection, preview)
        add_brep_surface(self.state.brep_surface_collection, brep)
        feature = LoftFeatureRecord(
            id="linked",
            name="Linked",
            options=LoftFeatureOptions(source_curve_ids=[]),
            preview_surface_id=preview.id,
            brep_surface_id=brep.id,
        )
        add_loft_feature(self.state.loft_feature_collection, feature)

        result = self.controller.delete_surface(preview.id)

        self.assertTrue(result.success)
        self.assertEqual(self.state.surface_collection.surfaces, [])
        self.assertEqual(self.state.brep_surface_collection.surfaces, [])
        self.assertEqual(self.state.loft_feature_collection.features, [])
        result.undo_payload.undo()
        self.assertEqual(
            [item.id for item in self.state.surface_collection.surfaces],
            [preview.id],
        )
        self.assertEqual(
            [item.id for item in self.state.brep_surface_collection.surfaces],
            [brep.id],
        )

    def test_surface_opacity_rejects_nonfinite_and_clamps_legacy_minimum(self) -> None:
        surface = SurfacePatch("preview", "Preview", [], "preview")
        add_surface(self.state.surface_collection, surface)

        invalid = self.controller.update_surface(
            surface.id,
            name="Must Not Apply",
            visible=False,
            opacity=float("nan"),
        )
        clamped = self.controller.update_surface(surface.id, opacity=0.0)

        self.assertFalse(invalid.success)
        self.assertEqual(surface.name, "Preview")
        self.assertTrue(surface.visible)
        self.assertTrue(clamped.success)
        self.assertEqual(surface.metadata["display_opacity"], 0.05)
        clamped.undo_payload.undo()
        restored = self.state.surface_collection.surfaces[0]
        self.assertNotIn("display_opacity", restored.metadata)
        clamped.undo_payload.redo()
        self.assertEqual(
            self.state.surface_collection.surfaces[0].metadata["display_opacity"],
            0.05,
        )


class BrepControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = AppState()
        self.events = EventPublisher()
        self.runtime: dict[str, object] = {}
        self.controller = BrepController(
            self.state,
            self.events,
            cad_backend=_backend(),
            runtime_objects=self.runtime,
        )

    def _closed_curve(self) -> StoredCurve:
        curve = _curve(
            "closed",
            [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 0, 0]],
            closed=True,
        )
        add_curve(self.state.curve_collection, curve)
        set_selected_curves(self.state.curve_collection, [curve.id])
        return curve

    def test_face_runtime_and_record_share_atomic_undo(self) -> None:
        self._closed_curve()

        result = self.controller.create_face(surface_id="brep-a")

        self.assertTrue(result.success, result.errors)
        self.assertTrue(result.dirty)
        self.assertEqual(self.state.brep_surface_collection.surfaces[0].id, "brep-a")
        self.assertIn("brep-a", self.runtime)
        result.undo_payload.undo()
        self.assertEqual(self.state.brep_surface_collection.surfaces, [])
        self.assertNotIn("brep-a", self.runtime)
        result.undo_payload.redo()
        self.assertIn("brep-a", self.runtime)

    def test_missing_backend_and_missing_rebuild_source_are_structured_failures(self) -> None:
        self._closed_curve()
        missing_backend = BrepController(self.state)
        result = missing_backend.create_face()
        self.assertFalse(result.success)
        self.assertFalse(result.dirty)

        created = self.controller.create_face(surface_id="brep-a")
        self.assertTrue(created.success)
        self.state.curve_collection.curves.clear()
        rebuilt = self.controller.rebuild_surface("brep-a")
        self.assertFalse(rebuilt.success)
        self.assertEqual(rebuilt.metadata["missing_curve_ids"], ("closed",))
        self.assertIn("brep-a", self.runtime)

    def test_editable_loft_reorder_reverse_and_undo_invalidate_dependents(self) -> None:
        first = _curve("a", [[0, 0, 0], [1, 0, 0]])
        second = _curve("b", [[0, 1, 0], [1, 1, 0]])
        for curve in (first, second):
            add_curve(self.state.curve_collection, curve)
        set_selected_curves(self.state.curve_collection, [first.id, second.id])
        self.state.four_boundary_feature_collection.features.append(
            FourBoundaryPatchFeatureRecord(
                id="patch",
                name="patch",
                source_curve_ids=[first.id, second.id, "c", "d"],
            )
        )

        created = self.controller.create_editable_loft(
            surface_id="loft-surface", feature_id="loft-feature"
        )
        self.assertTrue(created.success, created.errors)
        reordered = self.controller.reorder_source_curve(
            "loft-feature", first.id, 1
        )
        self.assertEqual(
            reordered.metadata["source_curve_ids"], (second.id, first.id)
        )
        before_points = first.fitted_points.copy()
        reversed_result = self.controller.reverse_source_curve(
            first.id, feature_id="loft-feature"
        )
        self.assertTrue(reversed_result.success)
        self.assertTrue(np.allclose(first.fitted_points, before_points[::-1]))
        self.assertTrue(
            self.state.four_boundary_feature_collection.features[0].metadata[
                "four_boundary_feature_dirty"
            ]
        )
        reversed_result.undo_payload.undo()
        restored = next(
            curve for curve in self.state.curve_collection.curves if curve.id == first.id
        )
        self.assertTrue(np.allclose(restored.fitted_points, before_points))

    def test_missing_sources_feature_and_duplicate_ids_fail_without_mutation(self) -> None:
        first = _curve("first", [[0, 0, 0], [1, 0, 0]])
        second = _curve("second", [[0, 1, 0], [1, 1, 0]])
        for curve in (first, second):
            add_curve(self.state.curve_collection, curve)
        missing = self.controller.create_loft(
            curve_ids=(first.id, second.id, "missing")
        )
        self.assertFalse(missing.success)
        self.assertEqual(missing.metadata["missing_curve_ids"], ("missing",))

        before = first.fitted_points.copy()
        reversed_result = self.controller.reverse_source_curve(
            first.id,
            feature_id="missing-feature",
        )
        self.assertFalse(reversed_result.success)
        np.testing.assert_allclose(first.fitted_points, before)

        set_selected_curves(self.state.curve_collection, [first.id, second.id])
        created = self.controller.create_loft(surface_id="duplicate")
        self.assertTrue(created.success, created.errors)
        duplicate = self.controller.create_loft(surface_id="duplicate")
        self.assertFalse(duplicate.success)
        self.assertEqual(duplicate.metadata["duplicate_surface_id"], "duplicate")

    def test_face_selection_export_metadata_and_undo_restore_source_selection(self) -> None:
        source = self._closed_curve()
        self.state.selected_item = "curve"
        result = self.controller.create_face(surface_id="brep-selection")

        self.assertTrue(result.success, result.errors)
        self.assertEqual(self.state.curve_collection.selected_curve_ids, set())
        self.assertEqual(
            self.state.brep_surface_collection.selected_surface_ids,
            {"brep-selection"},
        )
        exported = self.controller.export_surface(
            Path("selection.step"), "brep-selection"
        )
        self.assertTrue(exported.success)
        surface = self.state.brep_surface_collection.surfaces[0]
        self.assertEqual(surface.metadata["last_export_reason"], "exported")
        result.undo_payload.undo()
        self.assertEqual(self.state.curve_collection.selected_curve_ids, {source.id})

    def test_source_edit_invalidation_and_runtime_rebuild_share_atomic_undo(self) -> None:
        first = _curve("source-a", [[0, 0, 0], [1, 0, 0]])
        second = _curve("source-b", [[0, 1, 0], [1, 1, 0]])
        for curve in (first, second):
            add_curve(self.state.curve_collection, curve)
        set_selected_curves(self.state.curve_collection, [first.id, second.id])
        created = self.controller.create_editable_loft(
            surface_id="editable-surface",
            feature_id="editable-feature",
        )
        self.assertTrue(created.success, created.errors)
        original_runtime = self.runtime["editable-surface"]
        before_curve = _curve(first.id, first.fitted_points.tolist())
        first.fitted_points = first.fitted_points + np.asarray([0.0, 0.0, 2.0])

        changed = self.controller.source_curve_changed(
            first.id,
            before_curve=before_curve,
        )

        self.assertTrue(changed.success)
        self.assertEqual(changed.metadata["rebuilt_feature_ids"], ("editable-feature",))
        changed.undo_payload.undo()
        restored = next(
            item for item in self.state.curve_collection.curves if item.id == first.id
        )
        np.testing.assert_allclose(restored.fitted_points, before_curve.fitted_points)
        self.assertIs(self.runtime["editable-surface"], original_runtime)


if __name__ == "__main__":
    unittest.main()
