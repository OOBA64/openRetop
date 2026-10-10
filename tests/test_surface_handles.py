"""Drag arrows on a surface's sides (QuickSurface-style): grow or cut back fitted planes,
cylinders and freeform surfaces by hand."""

from __future__ import annotations

import math
import unittest
from unittest.mock import patch

import numpy as np

try:
    import cadquery  # noqa: F401
    import OCP  # noqa: F401

    HAVE_KERNEL = True
except ImportError:  # pragma: no cover
    HAVE_KERNEL = False


def _plane(half_u: float = 10.0, half_v: float = 5.0):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

    return BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), -half_u, half_u, -half_v, half_v).Face()


def _cylinder(sweep: float = 2 * math.pi):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.Geom import Geom_CylindricalSurface
    from OCP.gp import gp_Ax3, gp_Dir, gp_Pnt

    surface = Geom_CylindricalSurface(gp_Ax3(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 4.0)
    return BRepBuilderAPI_MakeFace(surface, 0.0, sweep, -5.0, 5.0, 1e-7).Face()


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class KernelTests(unittest.TestCase):
    def test_a_plane_has_an_arrow_on_each_side_pointing_out(self) -> None:
        from openretop.cad_kernel import surfacing as S

        handles = {handle["side"]: handle for handle in S.face_handles(_plane())["handles"]}
        self.assertEqual(sorted(handles), ["u0", "u1", "v0", "v1"])
        np.testing.assert_allclose(handles["u1"]["point"], (10, 0, 0), atol=1e-9)
        np.testing.assert_allclose(handles["u1"]["direction"], (1, 0, 0), atol=1e-9)
        np.testing.assert_allclose(handles["v0"]["direction"], (0, -1, 0), atol=1e-9)
        self.assertEqual(len(handles["u1"]["edge"]), 33)

    def test_sides_move_independently_both_ways(self) -> None:
        from openretop.cad_kernel import surfacing as S

        grown = S.resize_face(_plane(), {"u1": 7.0, "v0": -2.0})  # 20 x 10 -> 27 x 8
        self.assertAlmostEqual(S.face_area(grown), 27 * 8, places=6)

    def test_a_full_cylinder_extends_along_its_axis(self) -> None:
        from openretop.cad_kernel import surfacing as S

        handles = S.face_handles(_cylinder())["handles"]
        self.assertEqual([handle["side"] for handle in handles], ["v0", "v1"])  # a full turn: only its ends
        np.testing.assert_allclose([abs(handle["direction"][2]) for handle in handles], [1, 1], atol=1e-9)
        longer = S.resize_face(_cylinder(), {"v1": 6.0, "v0": -3.0})  # 10 tall -> 13
        self.assertAlmostEqual(S.face_area(longer), 2 * math.pi * 4 * 13, places=6)

    def test_a_part_cylinder_opens_round_its_axis_and_stops_at_a_full_turn(self) -> None:
        from openretop.cad_kernel import surfacing as S

        half = _cylinder(math.pi)
        self.assertEqual([handle["side"] for handle in S.face_handles(half)["handles"]], ["u0", "u1"] + ["v0", "v1"])
        wider = S.resize_face(half, {"u1": 4.0 * math.pi / 2})  # a quarter turn more along the arc
        self.assertAlmostEqual(S.face_area(wider), 4 * 1.5 * math.pi * 10, places=6)
        full = S.resize_face(half, {"u1": 100.0})
        self.assertAlmostEqual(S.face_area(full), 2 * math.pi * 4 * 10, places=6)

    def test_freeform_grows_and_cuts_back(self) -> None:
        from openretop.cad_kernel import surfacing as S
        from openretop.fitting.bspline_surface import fit_grid_surface

        u, v = np.linspace(0, 20, 15), np.linspace(0, 10, 10)
        grid = np.array([[[a, b, 0.02 * a * a] for b in v] for a in u])
        face = S.bspline_face(fit_grid_surface(grid, u, v, control_u=8, control_v=6, smoothness=0.0))
        area = S.face_area(face)
        self.assertEqual(len(S.face_handles(face)["handles"]), 4)
        self.assertAlmostEqual(S.face_area(S.resize_face(face, {"v1": 5.0})) / area, 1.5, places=2)
        self.assertLess(S.face_area(S.resize_face(face, {"u0": -5.0})), 0.8 * area)

    def test_a_trimmed_surface_has_no_arrows(self) -> None:
        from openretop.cad_kernel import surfacing as S

        pieces = S.split_faces([_plane(), _cylinder()])
        plane_piece = next(piece for piece in pieces if piece.source == 0)
        result = S.face_handles(plane_piece.face)
        self.assertFalse(result["rectangular"])
        self.assertEqual(result["handles"], [])

    def test_shrinking_to_nothing_is_refused(self) -> None:
        from openretop.cad_kernel import surfacing as S

        with self.assertRaises(ValueError):
            S.resize_face(_plane(), {"u1": -25.0})


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class InTheAppTests(unittest.TestCase):
    def setUp(self) -> None:
        from openretop.bootstrap import create_application
        from openretop.cad_kernel import jobs
        from openretop.cad_kernel.worker import KernelWorker
        from openretop.infrastructure.settings_repository import InMemorySettingsRepository
        from openretop.modeling.document import entity_from_result

        self.composition = create_application(settings_repository=InMemorySettingsRepository(), kernel_worker=KernelWorker(inline=True))
        model = self.composition.state.model
        result = jobs.surface_result(_plane(), kind="plane", rms=0.01, max_error=0.03)
        self.plane = model.add(entity_from_result(model, result, tool="fit_surface"))
        model.selected_ids = [self.plane.id]

    def test_resize_command_with_undo(self) -> None:
        modeling = self.composition.modeling_controller
        self.assertIs(modeling.handle_entity(), self.plane)
        self.assertEqual(len(modeling.surface_handles(self.plane.id)["handles"]), 4)
        result = self.composition.workflow.dispatch("model.resize", {"entity": self.plane.id, "changes": {"u1": 7.0}})
        self.assertTrue(result.success, result.errors)
        resized = self.composition.state.model.get(self.plane.id)
        assert resized is not None
        self.assertAlmostEqual(resized.stats["area"], 27 * 10, places=4)
        self.assertEqual((resized.name, resized.kind, resized.stats["rms"]), (self.plane.name, "plane", 0.01))  # still the fitted plane
        handles = {handle["side"]: handle for handle in modeling.surface_handles(self.plane.id)["handles"]}
        np.testing.assert_allclose(handles["u1"]["point"], (17, 0, 0), atol=1e-9)  # the arrows follow
        self.composition.workflow.dispatch("edit.undo", {})
        self.assertAlmostEqual(self.composition.state.model.get(self.plane.id).stats["area"], 200.0, places=4)  # type: ignore[union-attr]

    def test_no_arrows_while_another_tool_is_open(self) -> None:
        modeling = self.composition.modeling_controller
        self.assertTrue(modeling.start("loft").success)
        self.assertIsNone(modeling.handle_entity())
        modeling.finish()
        self.assertTrue(modeling.start("extend").success)
        self.assertIs(modeling.handle_entity(), self.plane)

    def test_dragging_an_arrow_in_the_window(self) -> None:
        from PySide6.QtWidgets import QApplication

        from openretop.presentation.qt.main_window import OpenRetopV3Window

        QApplication.instance() or QApplication([])
        window = OpenRetopV3Window(self.composition)
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        window.refresh()
        self.assertEqual(window.viewport.left_capture_owner, "surface_handles")
        lines = window._sketch2d_lines()
        self.assertEqual(len(lines), 16)  # a shaft and a head per side (4) and corner (4)
        handle = next(item for item in window._handle_items() if item.get("side") == "v1")
        with patch.object(window, "_handle_at", return_value=handle), patch.object(
            window.viewport, "pointer_ray", return_value=(np.array([0.0, 5.0, 50.0]), np.array([0.0, 0.0, -1.0]))
        ):
            self.assertTrue(window._surfacing_press_claim(0, 0))  # grabbed on the side
        # the pointer's line of sight passes 3 past the side (looking straight down)
        with patch.object(window.viewport, "pointer_ray", return_value=(np.array([0.0, 8.0, 50.0]), np.array([0.0, 0.0, -1.0]))):
            window._on_viewport_pointer("motion", 0, 0, None)
        self.assertAlmostEqual(window._handle_distance, 3.0, places=9)
        self.assertIn("+3.000", window.statusBar().currentMessage())
        self.assertEqual(len(window._sketch2d_lines()), 17)  # and the side where it will go
        window.viewport._last_pointer_release_was_click = False  # it was a drag
        window._on_viewport_pointer("left_release", 0, 0, None)
        self.assertIsNone(window._handle_drag)
        self.assertAlmostEqual(self.composition.state.model.get(self.plane.id).stats["area"], 20 * 13, places=4)  # type: ignore[union-attr]
        self.assertTrue(self.composition.undo.can_undo)
        # a press away from the arrows is not claimed: it orbits the view
        with patch.object(window, "_handle_at", return_value=None):
            self.assertFalse(window._surfacing_press_claim(0, 0))

    def _window(self):
        from PySide6.QtWidgets import QApplication

        from openretop.presentation.qt.main_window import OpenRetopV3Window

        QApplication.instance() or QApplication([])
        window = OpenRetopV3Window(self.composition)
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        window.refresh()
        return window

    def test_a_corner_drags_both_sides(self) -> None:
        window = self._window()
        corner = next(item for item in window._handle_items() if item.get("sides") == ("u1", "v1"))
        np.testing.assert_allclose(corner["point"], (10, 5, 0), atol=1e-9)
        with patch.object(window, "_handle_at", return_value=corner), patch.object(
            window.viewport, "pointer_ray", return_value=(np.array([11.0, 6.0, 30.0]), np.array([0.0, 0.0, -1.0]))
        ):
            self.assertTrue(window._surfacing_press_claim(0, 0))  # grabbed a little outside the corner
        # then moved to (15, 8): 4 further past the u1 side, 2 past the v1 side
        with patch.object(window.viewport, "pointer_ray", return_value=(np.array([15.0, 8.0, 30.0]), np.array([0.0, 0.0, -1.0]))):
            window._on_viewport_pointer("motion", 0, 0, None)
        self.assertEqual({side: round(value, 9) for side, value in (window._handle_moves or {}).items()}, {"u1": 4.0, "v1": 2.0})
        window.viewport._last_pointer_release_was_click = False
        window._on_viewport_pointer("left_release", 0, 0, None)
        self.assertAlmostEqual(self.composition.state.model.get(self.plane.id).stats["area"], 24 * 12, places=4)  # type: ignore[union-attr]

    def test_click_an_arrow_then_type_the_distance(self) -> None:
        from PySide6.QtCore import Qt

        window = self._window()
        handle = next(item for item in window._handle_items() if item.get("side") == "u0")
        with patch.object(window, "_handle_at", return_value=handle):
            self.assertTrue(window._surfacing_press_claim(0, 0))
        window.viewport._last_pointer_release_was_click = True
        window._on_viewport_pointer("left_release", 0, 0, None)
        self.assertIsNotNone(window._handle_picked)
        self.assertIn("Type how far", window.statusBar().currentMessage())
        self.assertTrue(window._surfacing_claims_key(Qt.Key.Key_1))  # digits are the distance, not view shortcuts
        for key, text in ((Qt.Key.Key_1, "1"), (Qt.Key.Key_2, "2"), (Qt.Key.Key_Period, "."), (Qt.Key.Key_5, "5")):
            self.assertTrue(window._handle_tool_key(key, text))
        self.assertEqual(window._handle_typed, "12.5")
        self.assertIn("12.5", [item.text.split()[0] for item in window._surfacing_annotations()])
        self.assertTrue(window._handle_tool_key(Qt.Key.Key_Return, ""))
        self.assertIsNone(window._handle_picked)
        self.assertAlmostEqual(self.composition.state.model.get(self.plane.id).stats["area"], 32.5 * 10, places=4)  # type: ignore[union-attr]
        # Esc lets go without changing anything
        with patch.object(window, "_handle_at", return_value=handle):
            window._surfacing_press_claim(0, 0)
        window._on_viewport_pointer("left_release", 0, 0, None)
        self.assertTrue(window._handle_tool_key(Qt.Key.Key_Escape, ""))
        self.assertIsNone(window._handle_picked)

    def test_an_arrow_off_screen_moves_to_the_visible_part_of_its_side(self) -> None:
        window = self._window()
        side = next(item for item in self.composition.modeling_controller.surface_handles(self.plane.id)["handles"] if item["side"] == "u1")
        visible = {tuple(np.round(point, 6)) for point in side["edge"][:5]}
        with patch.object(window, "_on_screen", side_effect=lambda point: tuple(np.round(point, 6)) in visible):
            moved = window._visible_handle(side)
        self.assertIn(tuple(np.round(moved["point"], 6)), visible)
        np.testing.assert_allclose(moved["direction"], side["direction"])

    def test_other_tools_keep_the_mouse(self) -> None:
        from PySide6.QtWidgets import QApplication

        from openretop.presentation.qt.main_window import OpenRetopV3Window

        QApplication.instance() or QApplication([])
        window = OpenRetopV3Window(self.composition)
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        from openretop.application.state import MeshObjectState
        from openretop.mesh.triangle_mesh import TriangleMeshData

        mesh = TriangleMeshData(vertices=np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0]]), triangles=np.array([[0, 1, 2]]))
        self.composition.state.mesh_object = MeshObjectState(
            source_mesh=mesh, display_mesh=mesh.copy(), file_path=None, name="scan",
            origin=np.zeros(3), location=np.zeros(3), rotation=np.zeros(3), transform_matrix=np.identity(4),
        )
        self.assertTrue(self.composition.region_controller.start().success)
        window.refresh()
        self.assertEqual(window.viewport.left_capture_owner, "region")
        self.assertEqual(window._handle_items(), [])  # no arrows to grab while selecting a region
        self.assertTrue(window._surfacing_press_claim(5, 5))  # the region tool gets its presses


class AlongLineTests(unittest.TestCase):
    def test_the_closest_point_on_the_arrow_line_to_the_line_of_sight(self) -> None:
        from openretop.presentation.qt.surfacing_workbench import _along_line

        point, direction = np.zeros(3), np.array([1.0, 0.0, 0.0])
        self.assertAlmostEqual(_along_line(point, direction, np.array([4.0, 3.0, 10.0]), np.array([0.0, 0.0, -2.0])), 4.0)  # type: ignore[arg-type]
        self.assertIsNone(_along_line(point, direction, np.array([-5.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0])))


if __name__ == "__main__":
    unittest.main()
