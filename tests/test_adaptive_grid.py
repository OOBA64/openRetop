"""UX-31: the grid follows the camera - 1-2-5 spacing, recentring, fade, rebuilt only when needed."""

from __future__ import annotations

import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import trimesh
from PySide6.QtWidgets import QApplication

from openretop.bootstrap import create_application
from openretop.infrastructure.settings_repository import InMemorySettingsRepository
from openretop.presentation.qt.adaptive_grid import (
    MAJOR_EVERY,
    MAX_LINES_PER_DIRECTION,
    SEGMENTS_PER_LINE,
    build_line_geometry,
    choose_spacing,
    fade,
    format_spacing,
    grid_lines,
    nice_step,
    plan_grid,
    visible_span,
)
from openretop.presentation.qt.main_window import OpenRetopV3Window


def _is_125(value: float) -> bool:
    mantissa = value / 10.0 ** math.floor(math.log10(value))
    return any(math.isclose(mantissa, step, rel_tol=1e-9) for step in (1.0, 2.0, 5.0))


class SpacingTests(unittest.TestCase):
    def test_steps_are_always_one_two_or_five_times_a_power_of_ten(self) -> None:
        for exponent in range(-4, 6):
            for factor in np.linspace(1.0, 9.99, 40):
                value = float(factor) * 10.0**exponent
                self.assertTrue(_is_125(nice_step(value)), value)

    def test_steps_scale_with_powers_of_ten_and_never_decrease(self) -> None:
        values = np.geomspace(0.003, 4000.0, 400)
        steps = [nice_step(float(value)) for value in values]
        self.assertEqual(steps, sorted(steps))
        for value in (0.7, 1.3, 3.7, 8.2):
            self.assertAlmostEqual(nice_step(value * 10.0), nice_step(value) * 10.0)

    def test_bad_input_falls_back_to_one(self) -> None:
        for bad in (0.0, -3.0, float("nan"), float("inf")):
            self.assertEqual(nice_step(bad), 1.0)

    def test_there_are_always_a_sensible_number_of_lines_across_the_view(self) -> None:
        spacing = None
        for span in np.geomspace(0.5, 20000.0, 300):  # zoom out
            spacing = choose_spacing(float(span), spacing)
            self.assertTrue(_is_125(spacing))
            self.assertTrue(4.0 <= span / spacing <= 30.0, (span, spacing))
        for span in np.geomspace(20000.0, 0.5, 300):  # zoom back in
            spacing = choose_spacing(float(span), spacing)
            self.assertTrue(4.0 <= span / spacing <= 30.0, (span, spacing))

    def test_hysteresis_stops_the_spacing_flickering_at_a_boundary(self) -> None:
        boundary = 12.0 * math.sqrt(10.0 * 20.0)  # span at which the nearest 1-2-5 step flips from 10 to 20
        jitter = [boundary * (1.0 + 0.04 * math.sin(i)) for i in range(200)]
        self.assertGreater(len({nice_step(span / 12.0) for span in jitter}), 1)  # without hysteresis it would flip
        spacing = choose_spacing(jitter[0])
        changes = 0
        for span in jitter:
            new = choose_spacing(span, spacing)
            changes += new != spacing
            spacing = new
        self.assertEqual(changes, 0)

    def test_zooming_in_gives_finer_spacing_and_zooming_out_coarser(self) -> None:
        self.assertLess(choose_spacing(5.0), choose_spacing(50.0))
        self.assertLess(choose_spacing(50.0), choose_spacing(5000.0))


class PlanTests(unittest.TestCase):
    def test_centre_and_extent_are_whole_major_steps(self) -> None:
        for span in (3.0, 47.0, 800.0):
            for focal in ((0.0, 0.0), (13.7, -88.2), (-1234.5, 9876.5)):
                spec = plan_grid(span, focal)
                major = spec.spacing * MAJOR_EVERY
                self.assertAlmostEqual(spec.centre[0] / major, round(spec.centre[0] / major), places=9)
                self.assertAlmostEqual(spec.centre[1] / major, round(spec.centre[1] / major), places=9)
                self.assertAlmostEqual(spec.half_extent / major, round(spec.half_extent / major), places=9)

    def test_the_grid_reaches_well_past_the_edges_of_the_view(self) -> None:
        for span in (3.0, 47.0, 800.0):
            spec = plan_grid(span, (5.0, 5.0))
            self.assertGreaterEqual(spec.half_extent, span * 1.5)

    def test_line_count_is_capped(self) -> None:
        for span in (0.001, 1.0, 1e6):
            spec = plan_grid(span, (0.0, 0.0))
            self.assertLessEqual(2 * spec.half_extent / spec.spacing, MAX_LINES_PER_DIRECTION + 1e-9)

    def test_small_pans_do_not_change_the_plan_but_large_ones_do(self) -> None:
        span = 100.0
        base = plan_grid(span, (0.0, 0.0))
        self.assertEqual(plan_grid(span, (base.major_step * 0.4, 0.0), base.spacing), base)
        self.assertEqual(plan_grid(span, (0.0, -base.major_step * 0.4), base.spacing), base)
        moved = plan_grid(span, (base.major_step * 0.6, 0.0), base.spacing)
        self.assertNotEqual(moved, base)
        self.assertEqual(moved.spacing, base.spacing)  # same spacing, recentred by one major step
        self.assertAlmostEqual(moved.centre[0], base.major_step)

    def test_visible_span_for_both_projections(self) -> None:
        self.assertAlmostEqual(visible_span(parallel=True, parallel_scale=50.0, view_angle_degrees=30.0, distance=1.0, aspect=2.0), 200.0)
        perspective = visible_span(parallel=False, parallel_scale=1.0, view_angle_degrees=90.0, distance=100.0, aspect=1.0)
        self.assertAlmostEqual(perspective, 200.0)  # 2 * 100 * tan(45 deg)
        self.assertGreater(visible_span(parallel=False, parallel_scale=1.0, view_angle_degrees=30.0, distance=100.0, aspect=0.0), 0.0)

    def test_format_spacing(self) -> None:
        self.assertEqual(format_spacing(10.0, "mm"), "10 mm")
        self.assertEqual(format_spacing(0.5, "in"), "0.5 in")
        self.assertEqual(format_spacing(2000.0, "m"), "2000 m")


class GeometryTests(unittest.TestCase):
    def test_minor_and_major_lines_are_classified_by_every_tenth(self) -> None:
        spec = plan_grid(100.0, (0.0, 0.0))
        minor, major = grid_lines(spec)
        self.assertTrue(all(round(value / spec.spacing) % MAJOR_EVERY == 0 for value in major))
        self.assertTrue(all(round(value / spec.spacing) % MAJOR_EVERY != 0 for value in minor))
        count = int(round(spec.half_extent / spec.spacing))
        self.assertEqual(len(minor) + len(major), 2 * count + 1)

    def test_fade_is_one_at_the_centre_zero_at_the_edge_and_smooth(self) -> None:
        radius = np.linspace(0.0, 120.0, 50)
        values = fade(radius, 100.0)
        self.assertAlmostEqual(float(values[0]), 1.0)
        self.assertAlmostEqual(float(values[-1]), 0.0)
        self.assertTrue(np.all(np.diff(values) <= 1e-12))

    def test_geometry_lies_in_the_ground_plane_and_fades_towards_the_ends(self) -> None:
        spec = plan_grid(100.0, (0.0, 0.0))
        points, rgba, segments = build_line_geometry(spec)["lines"]
        self.assertTrue(np.all(points[:, 2] == 0.0))
        self.assertEqual(rgba.dtype, np.uint8)
        self.assertEqual(len(points), len(rgba))
        self.assertTrue(segments.min() >= 0 and segments.max() < len(points))
        radius = np.hypot(points[:, 0] - spec.centre[0], points[:, 1] - spec.centre[1])
        self.assertGreater(rgba[radius < spec.half_extent * 0.2][:, 3].mean(), rgba[radius > spec.half_extent * 0.9][:, 3].mean())
        self.assertEqual(len(segments) % SEGMENTS_PER_LINE, 0)

    def test_axis_lines_are_red_x_and_green_y_through_the_origin(self) -> None:
        spec = plan_grid(100.0, (0.0, 0.0))
        points, rgba, _segments = build_line_geometry(spec)["axes"]
        x_axis = points[(rgba[:, 0] > 200) & (rgba[:, 1] < 100)]
        y_axis = points[(rgba[:, 1] > 150) & (rgba[:, 0] < 120)]
        self.assertTrue(len(x_axis) and len(y_axis))
        self.assertTrue(np.all(x_axis[:, 1] == 0.0))
        self.assertTrue(np.all(y_axis[:, 0] == 0.0))

    def test_no_axis_lines_when_the_origin_is_far_outside_the_grid(self) -> None:
        spec = plan_grid(10.0, (50_000.0, 50_000.0))
        points, _rgba, _segments = build_line_geometry(spec)["axes"]
        self.assertEqual(len(points), 0)


def _ready(window: OpenRetopV3Window) -> None:
    with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
        window.viewport._is_ready = True
        window.viewport.ready.emit()


class ViewportGridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _window(self) -> OpenRetopV3Window:
        window = OpenRetopV3Window(create_application(settings_repository=InMemorySettingsRepository()))
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        window.resize(1000, 700)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ball.stl"
            trimesh.creation.icosphere(subdivisions=2, radius=10).export(path)
            window.open_model_path(path, units="mm")
        _ready(window)
        window.refresh()
        return window

    def _camera(self, window: OpenRetopV3Window):
        camera = window.viewport.renderer.GetActiveCamera()
        camera.ParallelProjectionOn()
        return camera

    def test_the_grid_exists_is_not_pickable_and_hides_with_the_setting(self) -> None:
        window = self._window()
        grid = window.viewport.grid
        self.assertIsNotNone(grid.lines_actor)
        self.assertTrue(bool(grid.lines_actor.GetVisibility()))
        self.assertFalse(bool(grid.lines_actor.GetPickable()))
        self.assertFalse(bool(grid.axes_actor.GetPickable()))
        grid.set_visible(False)
        self.assertFalse(bool(grid.lines_actor.GetVisibility()))
        self.assertFalse(bool(grid.axes_actor.GetVisibility()))

    def test_zooming_changes_the_spacing_in_one_two_five_steps_and_announces_it(self) -> None:
        window = self._window()
        camera = self._camera(window)
        announced: list[float] = []
        window.viewport.grid_spacing_changed.connect(announced.append)
        seen = []
        for scale in np.geomspace(5.0, 5000.0, 60):
            camera.SetParallelScale(float(scale))
            seen.append(window.viewport.grid.spacing)
        self.assertTrue(all(_is_125(value) for value in seen))
        self.assertEqual(seen, sorted(seen))
        self.assertGreater(len(set(seen)), 3)
        self.assertEqual(announced, [value for index, value in enumerate(seen) if index == 0 or value != seen[index - 1]][-len(announced):])

    def test_geometry_is_rebuilt_only_when_the_plan_changes(self) -> None:
        window = self._window()
        camera = self._camera(window)
        camera.SetParallelScale(50.0)
        grid = window.viewport.grid
        rebuilds = grid.rebuild_count
        for jitter in (0.0, 0.5, -0.5, 1.0, -1.0, 0.2):  # tiny zoom changes within one spacing band
            camera.SetParallelScale(50.0 + jitter)
        self.assertEqual(grid.rebuild_count, rebuilds)
        camera.SetParallelScale(5000.0)
        self.assertGreater(grid.rebuild_count, rebuilds)

    def test_the_grid_recentres_under_the_view_as_you_pan(self) -> None:
        window = self._window()
        camera = self._camera(window)
        camera.SetParallelScale(50.0)
        grid = window.viewport.grid
        before = grid.spec
        focal = np.asarray(camera.GetFocalPoint())
        position = np.asarray(camera.GetPosition())
        shift = np.array([before.major_step * 3.2, 0.0, 0.0])
        camera.SetFocalPoint(*(focal + shift))
        camera.SetPosition(*(position + shift))
        after = grid.spec
        self.assertNotEqual(after, before)
        self.assertAlmostEqual(after.centre[0], before.centre[0] + before.major_step * 3, places=6)
        self.assertEqual(after.spacing, before.spacing)

    def test_the_status_bar_names_the_current_grid_spacing(self) -> None:
        window = self._window()
        camera = self._camera(window)
        camera.SetParallelScale(40.0)
        near = window._info_label.text()
        camera.SetParallelScale(4000.0)
        far = window._info_label.text()
        self.assertIn("grid ", near)
        self.assertIn("mm", near)
        self.assertNotEqual(near, far)
        self.assertIn(format_spacing(window.viewport.grid.spacing, "mm"), far)

    def test_no_grid_text_without_a_model_or_with_the_grid_hidden(self) -> None:
        window = OpenRetopV3Window(create_application(settings_repository=InMemorySettingsRepository()))
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        self.assertEqual(window._model_info_text(), "No model")
        window = self._window()
        window.viewport.grid.set_visible(False)
        self.assertNotIn("grid", window._model_info_text())

    def test_closing_the_viewport_removes_the_camera_observer(self) -> None:
        window = self._window()
        camera = self._camera(window)
        grid = window.viewport.grid
        window.set_project_dirty(False)
        window.close()
        rebuilds = grid.rebuild_count
        camera.SetParallelScale(99999.0)
        self.assertEqual(grid.rebuild_count, rebuilds)


if __name__ == "__main__":
    unittest.main()
