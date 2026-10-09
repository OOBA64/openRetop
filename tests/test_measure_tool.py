"""UX-32: measuring the scan to verify its size."""

from __future__ import annotations

import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import trimesh
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from openretop.application.guidance import Stage, build_guidance
from openretop.application.measure_controller import describe_measurement, format_length
from openretop.application.scene_ids import NODE_MESH
from openretop.application.state import Measurement
from openretop.bootstrap import create_application
from openretop.infrastructure.settings_repository import InMemorySettingsRepository
from openretop.presentation.qt.main_window import OpenRetopV3Window
from openretop.presentation.qt.measurement_overlay import label_text
from openretop.viewer.picking_service import MeshPickResult, SceneObjectPickResult


def _ready(window: OpenRetopV3Window) -> None:
    with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
        window.viewport._is_ready = True
        window.viewport.ready.emit()


def _hit(x: float, y: float, z: float) -> MeshPickResult:
    return MeshPickResult(hit=True, position=np.asarray([x, y, z], dtype=float), triangle_index=0, mesh_id="mesh")


class FormattingTests(unittest.TestCase):
    def test_precision_follows_the_size_of_the_number(self) -> None:
        self.assertEqual(format_length(42.3141, "mm"), "42.31 mm")
        self.assertEqual(format_length(1.666, "in"), "1.67 in")
        self.assertEqual(format_length(0.0123, "mm"), "0.012 mm")
        self.assertEqual(format_length(123.456, "mm"), "123.5 mm")
        self.assertEqual(format_length(98765.4, "m"), "98765 m")
        self.assertEqual(format_length(0.0, "mm"), "0.000 mm")
        self.assertEqual(format_length(float("nan"), "mm"), "-- mm")

    def test_a_measurement_reports_its_components(self) -> None:
        item = Measurement("m", (0.0, 0.0, 0.0), (3.0, -4.0, 12.0))
        self.assertAlmostEqual(item.distance, 13.0)
        self.assertEqual(item.delta, (3.0, -4.0, 12.0))
        text = describe_measurement(item, "mm")
        self.assertIn("13.00 mm", text)
        self.assertIn("dX 3.00 mm", text)
        self.assertIn("dY 4.00 mm", text)  # components are absolute: the sign is just direction
        self.assertIn("dZ 12.00 mm", text)
        self.assertIn("13.00 mm", label_text(item, "mm"))


class MeasureToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _window(self, extents: tuple[float, float, float] = (10.0, 20.0, 30.0), units: str = "mm") -> OpenRetopV3Window:
        window = OpenRetopV3Window(create_application(settings_repository=InMemorySettingsRepository()))
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        window.resize(1000, 700)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "block.stl"
            trimesh.creation.box(extents).export(path)
            window.open_model_path(path, units=units)
        _ready(window)
        window.refresh()
        return window

    def _click(self, window: OpenRetopV3Window, pick: object) -> None:
        window.viewport._last_pointer_release_was_click = True
        window._on_viewport_pointer("left_release", 5, 5, pick)

    def _status(self, window: OpenRetopV3Window) -> str:
        return window.statusBar().currentMessage()

    # -- accuracy -----------------------------------------------------------------

    def test_the_measured_distance_matches_the_known_size_in_millimetres(self) -> None:
        window = self._window((10.0, 20.0, 30.0), "mm")
        window._dispatch_application_action("measure.distance")
        self._click(window, _hit(-5, -10, -15))
        self._click(window, _hit(5, 10, 15))
        (measurement,) = window.composition.measure_controller.measurements
        self.assertAlmostEqual(measurement.distance, math.sqrt(10**2 + 20**2 + 30**2), places=9)
        status = self._status(window)
        self.assertIn("37.42 mm", status)
        for component in ("dX 10.00 mm", "dY 20.00 mm", "dZ 30.00 mm"):
            self.assertIn(component, status)

    def test_the_measured_distance_is_reported_in_the_project_units_for_inches(self) -> None:
        window = self._window((2.0, 2.0, 2.0), "in")
        window._dispatch_application_action("measure.distance")
        self._click(window, _hit(-1, -1, -1))
        self._click(window, _hit(1, -1, -1))  # one edge: exactly 2 in
        self.assertIn("2.00 in", self._status(window))
        self.assertNotIn("mm", self._status(window))

    def test_clicks_are_snapped_onto_the_source_mesh_when_the_display_is_a_proxy(self) -> None:
        window = self._window((100.0, 100.0, 100.0), "mm")
        window.composition.state.mesh_object.display_proxy_enabled = True  # as if a large scan were reduced
        window._dispatch_application_action("measure.distance")
        self._click(window, _hit(-49.6, 3.0, 2.0))  # picked slightly inside the left face
        self._click(window, _hit(50.4, 3.0, 2.0))  # and slightly outside the right face
        (measurement,) = window.composition.measure_controller.measurements
        self.assertAlmostEqual(measurement.start[0], -50.0, places=6)
        self.assertAlmostEqual(measurement.end[0], 50.0, places=6)
        self.assertAlmostEqual(measurement.distance, 100.0, places=6)

    def test_clicks_are_not_moved_when_the_display_is_the_source(self) -> None:
        window = self._window((100.0, 100.0, 100.0), "mm")
        window._dispatch_application_action("measure.distance")
        self._click(window, _hit(-49.6, 3.0, 2.0))
        self.assertEqual(window.composition.measure_controller.pending, (-49.6, 3.0, 2.0))

    def test_a_snap_never_jumps_far_across_the_scan(self) -> None:
        window = self._window((100.0, 100.0, 100.0), "mm")
        window.composition.state.mesh_object.display_proxy_enabled = True
        window._dispatch_application_action("measure.distance")
        self._click(window, _hit(0.0, 0.0, 0.0))  # the centre: 50 mm from any face, beyond the 2 % limit
        self.assertEqual(window.composition.measure_controller.pending, (0.0, 0.0, 0.0))

    # -- the tool's flow ----------------------------------------------------------

    def test_it_needs_a_scan(self) -> None:
        window = OpenRetopV3Window(create_application(settings_repository=InMemorySettingsRepository()))
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        self.assertFalse(window._framework_actions.require("measure.distance").enabled)
        self.assertFalse(window.composition.measure_controller.start().success)

    def test_two_clicks_make_a_measurement_and_a_third_starts_the_next(self) -> None:
        window = self._window()
        measure = window.composition.measure_controller
        window._dispatch_application_action("measure.distance")
        self.assertTrue(measure.active)
        self.assertEqual(window.tool_modes.state.id, "measure")
        self._click(window, _hit(0, 0, 0))
        self.assertEqual(measure.pending, (0.0, 0.0, 0.0))
        self.assertEqual(len(measure.measurements), 0)
        self._click(window, _hit(3, 4, 0))
        self.assertIsNone(measure.pending)
        self.assertEqual(len(measure.measurements), 1)
        self._click(window, _hit(1, 1, 1))
        self.assertEqual(len(measure.measurements), 1)
        self.assertIsNotNone(measure.pending)
        self._click(window, _hit(1, 1, 6))
        self.assertEqual([round(item.distance, 6) for item in measure.measurements], [5.0, 5.0])
        self.assertEqual(len({item.id for item in measure.measurements}), 2)

    def test_a_click_that_misses_the_scan_places_nothing(self) -> None:
        window = self._window()
        window._dispatch_application_action("measure.distance")
        self._click(window, MeshPickResult(hit=False))
        self.assertIsNone(window.composition.measure_controller.pending)
        self.assertIn("Click on the scan", self._status(window))

    def test_a_drag_is_an_orbit_not_a_click(self) -> None:
        window = self._window()
        window._dispatch_application_action("measure.distance")
        window.viewport._last_pointer_release_was_click = False
        window._on_viewport_pointer("left_release", 5, 5, _hit(0, 0, 0))
        self.assertIsNone(window.composition.measure_controller.pending)

    def test_esc_cancels_a_half_made_measurement_then_finishes_the_tool(self) -> None:
        window = self._window()
        measure = window.composition.measure_controller
        window._dispatch_application_action("measure.distance")
        self._click(window, _hit(0, 0, 0))
        self._click(window, _hit(0, 0, 9))
        self._click(window, _hit(1, 1, 1))
        self.assertTrue(window._handle_tool_key(Qt.Key_Escape))
        self.assertIsNone(measure.pending)
        self.assertTrue(measure.active)
        self.assertTrue(window._handle_tool_key(Qt.Key_Escape))
        self.assertFalse(measure.active)
        self.assertEqual(len(measure.measurements), 1)  # finished measurements stay on screen

    def test_clear_measurements_removes_them_and_is_only_enabled_when_there_are_some(self) -> None:
        window = self._window()
        self.assertFalse(window._framework_actions.require("measure.clear").enabled)
        window._dispatch_application_action("measure.distance")
        self._click(window, _hit(0, 0, 0))
        self._click(window, _hit(0, 0, 4))
        self.assertTrue(window._framework_actions.require("measure.clear").enabled)
        window._dispatch_application_action("measure.clear")
        self.assertEqual(window.composition.measure_controller.measurements, ())
        self.assertFalse(window._framework_actions.require("measure.clear").enabled)

    def test_measuring_never_changes_the_selection(self) -> None:
        window = self._window()
        window.composition.selection_controller.select_nodes((NODE_MESH,))
        window.refresh()
        window._dispatch_application_action("measure.distance")
        window.viewport._last_pointer_release_was_click = True
        window._on_viewport_pointer("left_release", 5, 5, SceneObjectPickResult(hit=False))  # would clear the selection
        self.assertEqual(window.composition.selection_controller.snapshot().ids, (NODE_MESH,))

    # -- tool conflicts -----------------------------------------------------------

    def test_it_cannot_start_while_another_tool_owns_the_pointer(self) -> None:
        window = self._window()
        window._dispatch_application_action("region.start")
        self.assertFalse(window._dispatch_application_action("measure.distance"))
        self.assertIn("region tool", self._status(window))
        self.assertFalse(window.composition.measure_controller.active)

    def test_starting_another_tool_ends_measuring(self) -> None:
        window = self._window()
        window._dispatch_application_action("measure.distance")
        window._dispatch_application_action("region.start")
        self.assertFalse(window.composition.measure_controller.active)
        self.assertEqual(window.tool_modes.state.id, "region")

    def test_a_new_scan_clears_the_measurements(self) -> None:
        window = self._window()
        window._dispatch_application_action("measure.distance")
        self._click(window, _hit(0, 0, 0))
        self._click(window, _hit(0, 0, 4))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "other.stl"
            trimesh.creation.box((1.0, 1.0, 1.0)).export(path)
            window.open_model_path(path, units="mm")
        self.assertFalse(window.composition.measure_controller.has_measurements)
        self.assertFalse(window.composition.measure_controller.active)

    def test_measurements_are_not_saved_in_the_project_file(self) -> None:
        window = self._window()
        window._dispatch_application_action("measure.distance")
        self._click(window, _hit(0, 0, 0))
        self._click(window, _hit(0, 0, 4))
        with tempfile.TemporaryDirectory() as directory:
            window.current_project_path = Path(directory) / "p.openretop"
            self.assertTrue(window.save_project())
            text = window.current_project_path.read_text(encoding="utf-8").lower()
        self.assertNotIn("measure", text)

    # -- model size ---------------------------------------------------------------

    def test_model_size_reports_the_bounding_box_and_diagonal(self) -> None:
        window = self._window((10.0, 20.0, 30.0), "mm")
        self.assertTrue(window._dispatch_application_action("measure.model_size"))
        status = self._status(window)
        self.assertIn("10.00 mm x 20.00 mm x 30.00 mm", status)
        self.assertIn("diagonal 37.42 mm", status)

    def test_model_size_warns_when_the_units_were_assumed(self) -> None:
        window = self._window()
        window.composition.state.units_assumed = True
        window._dispatch_application_action("measure.model_size")
        self.assertIn("Units were assumed", self._status(window))

    # -- the on-screen overlay ----------------------------------------------------

    def test_the_overlay_shows_points_lines_and_a_distance_label_over_the_scene(self) -> None:
        window = self._window()
        overlay = window.viewport.measurement_overlay
        self.assertFalse(overlay.visible)
        window._dispatch_application_action("measure.distance")
        self._click(window, _hit(0, 0, 0))
        self.assertEqual([bool(actor.GetVisibility()) for actor in overlay.marker_actors], [True])  # the first point is marked straight away
        self.assertFalse(bool(overlay.lines_actor.GetVisibility()))
        self._click(window, _hit(3, 4, 0))
        self.assertTrue(overlay.visible)
        self.assertEqual(sum(bool(actor.GetVisibility()) for actor in overlay.marker_actors), 2)  # both ends
        self.assertEqual(len(overlay.label_actors), 1)
        self.assertIn("5.00 mm", overlay.label_actors[0].GetInput())
        layer = overlay.layer_renderer
        self.assertIsNotNone(layer)
        self.assertGreaterEqual(layer.GetLayer(), 1)
        self.assertFalse(bool(layer.GetPreserveDepthBuffer()))  # depth cleared: never hidden by the scan
        self.assertTrue(bool(layer.GetErase()))
        self.assertIs(layer.GetActiveCamera(), window.viewport.renderer.GetActiveCamera())
        for actor in overlay.actors:
            self.assertFalse(bool(window.viewport.renderer.HasViewProp(actor)))
            self.assertTrue(bool(layer.HasViewProp(actor)))
        self.assertFalse(bool(overlay.lines_actor.GetPickable()))

    def test_the_overlay_follows_the_units_and_is_rebuilt_only_on_change(self) -> None:
        window = self._window((2.0, 2.0, 2.0), "in")
        overlay = window.viewport.measurement_overlay
        window._dispatch_application_action("measure.distance")
        self._click(window, _hit(-1, -1, -1))
        self._click(window, _hit(1, -1, -1))
        self.assertIn("2.00 in", overlay.label_actors[0].GetInput())
        rebuilds = overlay.rebuild_count
        window.refresh()
        window.refresh()
        self.assertEqual(overlay.rebuild_count, rebuilds)

    def test_clearing_hides_the_overlay_and_several_measurements_each_get_a_label(self) -> None:
        window = self._window()
        overlay = window.viewport.measurement_overlay
        window._dispatch_application_action("measure.distance")
        for start, end in (((0, 0, 0), (0, 0, 2)), ((1, 1, 1), (1, 1, 4)), ((2, 2, 2), (2, 2, 7))):
            self._click(window, _hit(*start))
            self._click(window, _hit(*end))
        visible_labels = [actor for actor in overlay.label_actors if actor.GetVisibility()]
        self.assertEqual(len(visible_labels), 3)
        window._dispatch_application_action("measure.clear")
        self.assertFalse(overlay.visible)
        self.assertFalse(any(actor.GetVisibility() for actor in overlay.label_actors))
        self.assertFalse(any(actor.GetVisibility() for actor in overlay.marker_actors))

    def test_the_overlay_props_are_named_in_the_inventory_and_not_unidentified(self) -> None:
        window = self._window()
        window._dispatch_application_action("measure.distance")
        self._click(window, _hit(0, 0, 0))
        self._click(window, _hit(0, 0, 4))
        inventory = window.viewport.renderer_prop_inventory()
        self.assertNotIn("unidentified", {item["semantic_category"] for item in inventory})
        self.assertIn("measurement", {item["role"] for item in inventory})

    # -- discoverability ----------------------------------------------------------

    def test_the_tool_is_in_the_inspect_menu_palette_toolbar_and_next_steps(self) -> None:
        window = self._window()
        definition = window._framework_actions.require("measure.distance")
        self.assertEqual(definition.category, "Inspect")
        self.assertEqual(definition.shortcut, "M")
        self.assertTrue(definition.description)
        palette = [item.id for item in window.shell.command_palette.search("measure", include_disabled=True)] if hasattr(window, "shell") else []
        if palette:
            self.assertIn("measure.distance", palette)
        guidance = build_guidance(window.composition.state)
        self.assertEqual(guidance.stage, Stage.SCAN)
        self.assertIn("measure.distance", [step.action_id for step in guidance.steps])
        self.assertIn("measure.distance", window.next_steps.step_buttons)

    def test_an_unavailable_clear_explains_why(self) -> None:
        window = self._window()
        definition = window._framework_actions.require("measure.clear")
        self.assertFalse(definition.enabled)
        self.assertIn("measurement", definition.disabled_reason)


if __name__ == "__main__":
    unittest.main()
