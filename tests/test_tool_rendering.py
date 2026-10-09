"""Tools that drew nothing or did the wrong thing.

- Manual-curve points and the curve being drawn were never rendered: the v3 viewport built the
  preview into every snapshot but no code drew it.
- Curves on the scan were mostly hidden by the facets they lie on (no depth offset).
- Pressing R when Rotate was unavailable reached VTK's built-in "r" key, which reset the camera.
- In the Section tool, G/R did nothing unless the plane was also selected.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import trimesh
from PySide6.QtWidgets import QApplication

from openretop.application.scene_ids import NODE_MESH
from openretop.bootstrap import create_application
from openretop.infrastructure.settings_repository import InMemorySettingsRepository
from openretop.presentation.qt.main_window import OpenRetopV3Window
from openretop.presentation.qt.tool_preview_overlay import POINT_RADIUS_PX, ToolPreviewOverlay, world_per_pixel
from openretop.viewer.curve_actors import CURVE_DEPTH_PULL, create_curve_actor
from openretop.viewer.scene_types import CurveRenderItem, ToolPreviewState


def _ready(window: OpenRetopV3Window) -> None:
    with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
        window.viewport._is_ready = True
        window.viewport.ready.emit()


def _window(test: unittest.TestCase) -> OpenRetopV3Window:
    window = OpenRetopV3Window(create_application(settings_repository=InMemorySettingsRepository()))
    test.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
    window.resize(1000, 700)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "capsule.stl"
        trimesh.creation.capsule(height=40, radius=10).export(path)
        window.open_model_path(path, units="mm")
    _ready(window)
    return window


def _preview(**values: object) -> ToolPreviewState:
    defaults: dict[str, object] = {
        "revision": 1,
        "active": True,
        "control_points": np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [10.0, 10.0, 0.0]]),
        "point_types": ("smooth", "corner", "smooth"),
        "fitted_points": np.array([[0.0, 0.0, 0.0], [5.0, -1.0, 0.0], [10.0, 0.0, 0.0], [10.0, 10.0, 0.0]]),
    }
    defaults.update(values)
    return ToolPreviewState(**defaults)  # type: ignore[arg-type]


class ToolPreviewOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _overlay(self) -> tuple[OpenRetopV3Window, ToolPreviewOverlay]:
        window = _window(self)
        return window, window.viewport.tool_preview_overlay

    def test_points_and_curve_are_drawn_over_the_scene(self) -> None:
        _window_, overlay = self._overlay()
        overlay.update(_preview())
        self.assertEqual(overlay.point_count, 3)
        self.assertTrue(bool(overlay.curve_actor.GetVisibility()))
        self.assertEqual(overlay.curve_actor.GetMapper().GetInput().GetNumberOfPoints(), 4)
        # in their own layer above the scan, so the scan never hides them
        self.assertIsNotNone(overlay.layer_renderer)
        self.assertTrue(overlay.layer_renderer.HasViewProp(overlay.points_actor))
        self.assertGreater(overlay.layer_renderer.GetLayer(), 0)

    def test_control_points_are_spheres_not_point_sprites(self) -> None:
        from vtkmodules.vtkRenderingCore import vtkGlyph3DMapper

        _window_, overlay = self._overlay()
        overlay.update(_preview())
        mapper = overlay.points_actor.GetMapper()
        self.assertIsInstance(mapper, vtkGlyph3DMapper)
        source = mapper.GetInputConnection(1, 0).GetProducer()
        self.assertEqual(source.GetClassName(), "vtkSphereSource")
        self.assertFalse(bool(overlay.points_actor.GetProperty().GetRenderPointsAsSpheres()))

    def test_corner_selected_and_cursor_points_have_their_own_colours(self) -> None:
        _window_, overlay = self._overlay()
        colors = {"smooth_point_color": "#FFFFFF", "corner_point_color": "#FF0000", "selected_point_color": "#00FF00", "preview_point_color": "#0000FF"}
        overlay.update(_preview(selected_control_point_index=2, preview_point=(20.0, 0.0, 0.0), preview_valid=True), colors)
        rgb = overlay._points_data.GetPointData().GetArray("rgb")
        self.assertEqual([tuple(int(v) for v in rgb.GetTuple3(i)) for i in range(4)], [(255, 255, 255), (255, 0, 0), (0, 255, 0), (0, 0, 255)])
        self.assertTrue(bool(overlay.rubber_band_actor.GetVisibility()))  # a line from the last point to the cursor

    def test_spheres_keep_their_size_on_screen_when_zooming(self) -> None:
        window, overlay = self._overlay()
        overlay.update(_preview())
        camera = window.viewport.renderer.GetActiveCamera()
        camera.ParallelProjectionOn()
        height = int(window.viewport.render_window.GetSize()[1]) or 1
        for scale in (10.0, 100.0):
            camera.SetParallelScale(scale)
            overlay._resize_points()
            radius = overlay._points_data.GetPointData().GetArray("radius").GetValue(0)
            self.assertAlmostEqual(radius, POINT_RADIUS_PX * 2.0 * scale / height, places=9)
        self.assertAlmostEqual(world_per_pixel(window.viewport.renderer, np.zeros(3), height), 200.0 / height)

    def test_nothing_is_drawn_when_the_tool_ends(self) -> None:
        _window_, overlay = self._overlay()
        overlay.update(_preview())
        overlay.update(ToolPreviewState())
        self.assertEqual(overlay.point_count, 0)
        self.assertFalse(bool(overlay.curve_actor.GetVisibility()))

    def test_the_window_feeds_the_3d_sketch_into_the_overlay(self) -> None:
        window = _window(self)
        modeling = window.composition.modeling_controller
        with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
            self.assertTrue(window._dispatch_framework_action("model.sketch"))
            for angle in (0.0, 45.0, 90.0):
                radians = np.radians(angle)
                self.assertTrue(modeling.sketch_click((10.0 * np.cos(radians), 10.0 * np.sin(radians), 0.0)).success)
            window.refresh()
        overlay = window.viewport.tool_preview_overlay
        self.assertEqual(len(modeling.session.sketch_points), 3)
        self.assertGreaterEqual(overlay.point_count, 3)
        self.assertTrue(bool(overlay.curve_actor.GetVisibility()))


class CurveOnScanTests(unittest.TestCase):
    """A curve drawn on a curved scan used to cut through its inside (measured: up to 1.4 mm)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_a_3d_sketch_curve_follows_the_surface_of_the_scan(self) -> None:
        from vtkmodules.vtkFiltersCore import vtkImplicitPolyDataDistance

        from openretop.viewer.vtk_actor_utils import polydata

        window = _window(self)
        modeling = window.composition.modeling_controller
        with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
            self.assertTrue(window._dispatch_framework_action("model.sketch"))
            # three points on the capsule side (radius 10), a quarter turn apart
            for angle in (0.0, 45.0, 90.0):
                radians = np.radians(angle)
                modeling.sketch_click((10.0 * np.cos(radians), 10.0 * np.sin(radians), 0.0))
            self.assertTrue(modeling.sketch_finish().success)
        points = np.asarray(window.composition.state.model.sketch.curves[-1].polyline, dtype=float)
        mesh = window.composition.transform_controller.transformed_source_mesh()
        distance = vtkImplicitPolyDataDistance()
        distance.SetInput(polydata(mesh.vertices, mesh.triangles, cell_kind="polys"))
        depth_inside = -min(distance.EvaluateFunction(list(point)) for point in points)
        self.assertLess(depth_inside, 1e-3)


class CurveDepthTests(unittest.TestCase):
    def test_curves_are_pulled_in_front_of_the_surface_they_lie_on(self) -> None:
        actor = create_curve_actor(CurveRenderItem(id="c", revision=1, points=np.array([[0.0, 0, 0], [1.0, 0, 0]]), closed=False))
        from vtkmodules.vtkCommonCore import reference

        factor, units = reference(0.0), reference(0.0)
        actor.GetMapper().GetRelativeCoincidentTopologyLineOffsetParameters(factor, units)
        factor, units = float(factor), float(units)
        self.assertEqual((factor, units), CURVE_DEPTH_PULL)
        self.assertLess(units, 0.0)

    def test_the_viewport_turns_on_coincident_topology_offsets(self) -> None:
        from vtkmodules.vtkRenderingCore import vtkMapper

        QApplication.instance() or QApplication([])
        from openretop.presentation.qt.viewport import QtSceneViewport

        viewport = QtSceneViewport()
        self.addCleanup(viewport.close)
        self.assertEqual(vtkMapper.GetResolveCoincidentTopology(), 1)  # VTK_RESOLVE_POLYGON_OFFSET


class KeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_vtk_single_letter_keys_do_nothing(self) -> None:
        window = _window(self)
        interactor = window.viewport.interactor
        camera = window.viewport.renderer.GetActiveCamera()
        camera.SetPosition(123.0, 45.0, 67.0)
        before = camera.GetPosition()
        for key in "rwsf3":
            interactor.SetKeyCode(key)
            interactor.InvokeEvent("CharEvent")
        np.testing.assert_allclose(camera.GetPosition(), before)

    def test_g_and_r_act_on_the_active_plane_in_the_section_tool(self) -> None:
        for action, mode in (("transform.move", "move"), ("transform.rotate", "rotate")):
            with self.subTest(action=action):
                window = _window(self)
                with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
                    window._dispatch_framework_action("section.compute")
                window.composition.selection_controller.select_nodes(())
                window.refresh()
                self.assertTrue(window._section_tool)
                self.assertTrue(window._framework_actions.require(action).enabled)
                with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
                    self.assertTrue(window._dispatch_framework_action(action))
                session = window.composition.state.transform_state
                self.assertEqual(session.selected_item, "section_plane")
                self.assertEqual(session.mode, mode)

    def test_outside_the_section_tool_g_and_r_still_need_a_selection(self) -> None:
        window = _window(self)
        window.composition.selection_controller.select_nodes(())
        window.refresh()
        self.assertFalse(window._section_tool)
        self.assertFalse(window._framework_actions.require("transform.rotate").enabled)
        window.composition.selection_controller.select_nodes((NODE_MESH,))
        window.refresh()
        self.assertTrue(window._framework_actions.require("transform.rotate").enabled)


if __name__ == "__main__":
    unittest.main()
