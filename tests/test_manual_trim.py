"""Manual trimming: cut a surface along a line drawn across it, click the overhang away."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

try:
    import cadquery  # noqa: F401
    import OCP  # noqa: F401

    HAVE_KERNEL = True
except ImportError:  # pragma: no cover
    HAVE_KERNEL = False

DOWN = np.array([0.0, 0.0, -1.0])  # looking straight down at the plane


def _plane():
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

    return BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), -10, 10, -5, 5).Face()  # 20 x 10


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class KernelTests(unittest.TestCase):
    def brep(self) -> bytes:
        from openretop.cad_kernel import surfacing as S

        return S.to_brep(_plane())

    def test_a_line_clicked_inside_the_edges_still_cuts_right_across(self) -> None:
        from openretop.cad_kernel import jobs

        cut = {"points": np.array([[5.0, -3.0, 0.0], [5.0, 3.0, 0.0]]), "direction": DOWN}
        pieces = jobs.trim([self.brep()], np.zeros((0, 3)), np.zeros((0, 3)), cuts=[cut], manual=True)["pieces"]
        self.assertEqual(sorted(round(piece["area"], 6) for piece in pieces), [50.0, 150.0])
        self.assertTrue(all(piece["keep"] for piece in pieces))  # manual: you choose what goes

    def test_a_bent_line_cuts_a_corner_off(self) -> None:
        from openretop.cad_kernel import jobs

        cut = {"points": np.array([[4.0, -4.0, 0.0], [4.0, 2.0, 0.0], [9.0, 2.0, 0.0]]), "direction": DOWN}
        pieces = jobs.trim([self.brep()], np.zeros((0, 3)), np.zeros((0, 3)), cuts=[cut], manual=True)["pieces"]
        # up x = 4 from the bottom edge, then right along y = 2 to the right edge: the
        # 6 x 7 block below the bend comes away (the line runs on to both edges)
        self.assertEqual(sorted(round(piece["area"], 6) for piece in pieces), [42.0, 158.0])

    def test_one_surface_without_a_cut_line_is_explained(self) -> None:
        from openretop.cad_kernel import jobs

        with self.assertRaises(ValueError) as raised:
            jobs.trim([self.brep()], np.zeros((0, 3)), np.zeros((0, 3)))
        self.assertIn("cut line", str(raised.exception))


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class ToolTests(unittest.TestCase):
    def setUp(self) -> None:
        from openretop.bootstrap import create_application
        from openretop.cad_kernel import jobs
        from openretop.cad_kernel.worker import KernelWorker
        from openretop.infrastructure.settings_repository import InMemorySettingsRepository
        from openretop.modeling.document import entity_from_result

        self.composition = create_application(settings_repository=InMemorySettingsRepository(), kernel_worker=KernelWorker(inline=True))
        model = self.composition.state.model
        self.plane = model.add(entity_from_result(model, jobs.surface_result(_plane(), kind="plane"), tool="fit_surface"))
        model.selected_ids = [self.plane.id]
        self.modeling = self.composition.modeling_controller

    def dispatch(self, action: str, payload: dict | None = None):
        result = self.composition.workflow.dispatch(action, payload or {})
        self.assertTrue(result.success, (action, result.errors, result.status))
        return result

    def test_cut_the_overhang_off_one_surface(self) -> None:
        self.dispatch("model.trim")
        self.assertEqual(self.modeling.session.trim_selected, (self.plane.id,))
        self.dispatch("model.trim_cut")
        for point in ((5.0, -3.0, 0.0), (5.0, 3.0, 0.0)):
            self.assertTrue(self.modeling.trim_cut_point(point, DOWN).success)
        self.dispatch("model.trim_cut_finish")
        pieces = self.modeling.session.trim_pieces
        self.assertEqual(len(pieces), 2)
        overhang = min(range(2), key=lambda index: pieces[index]["area"])
        self.assertTrue(self.modeling.trim_toggle(overhang).success)  # click the overhang away
        self.dispatch("model.trim_apply", {"sew": False})
        model = self.composition.state.model
        visible = [entity for entity in model.entities if entity.visible]
        self.assertEqual(len(visible), 1)
        self.assertAlmostEqual(visible[0].stats["area"], 150.0, places=4)
        self.assertFalse(model.get(self.plane.id).visible)  # type: ignore[union-attr]  # kept, hidden: trim again later
        self.dispatch("edit.undo")
        self.assertEqual([entity.id for entity in model.entities], [self.plane.id])

    def test_a_cut_line_on_the_selected_surface_leaves_the_others_alone(self) -> None:
        from openretop.cad_kernel import jobs
        from openretop.modeling.document import entity_from_result

        model = self.composition.state.model
        other = model.add(entity_from_result(model, jobs.surface_result(_plane(), kind="plane"), tool="fit_surface"))
        model.selected_ids = [self.plane.id]
        self.dispatch("model.trim")
        self.dispatch("model.trim_cut")
        self.modeling.trim_cut_point((5.0, -3.0, 0.0), DOWN)
        self.modeling.trim_cut_point((5.0, 3.0, 0.0), DOWN)
        self.dispatch("model.trim_cut_finish")
        self.assertEqual(self.modeling.session.trim_used, (self.plane.id,))
        self.assertEqual({piece["source_id"] for piece in self.modeling.session.trim_pieces}, {self.plane.id})
        self.dispatch("model.trim_apply", {"sew": False})
        self.assertTrue(model.get(other.id).visible)  # type: ignore[union-attr]

    def test_manual_mode_keeps_every_piece_even_with_a_scan(self) -> None:
        from openretop.application.state import MeshObjectState
        from openretop.mesh.triangle_mesh import TriangleMeshData

        # a scan under the left half of the plane only: automatic trimming would drop the right
        xs, ys = np.meshgrid(np.linspace(-10, -1, 10), np.linspace(-5, 5, 11))
        vertices = np.c_[xs.ravel(), ys.ravel(), np.zeros(xs.size)]
        rows, cols = xs.shape
        triangles = [
            tri
            for i in range(rows - 1)
            for j in range(cols - 1)
            for tri in ([i * cols + j, i * cols + j + 1, (i + 1) * cols + j], [i * cols + j + 1, (i + 1) * cols + j + 1, (i + 1) * cols + j])
        ]
        mesh = TriangleMeshData(vertices=vertices, triangles=np.asarray(triangles))
        self.composition.state.mesh_object = MeshObjectState(
            source_mesh=mesh, display_mesh=mesh.copy(), file_path=None, name="scan",
            origin=np.zeros(3), location=np.zeros(3), rotation=np.zeros(3), transform_matrix=np.identity(4),
        )
        self.dispatch("model.trim")
        self.dispatch("model.trim_cut")
        self.modeling.trim_cut_point((0.0, -2.0, 0.0), DOWN)
        self.modeling.trim_cut_point((0.0, 2.0, 0.0), DOWN)
        self.dispatch("model.trim_cut_finish")
        automatic = [piece["keep"] for piece in self.modeling.session.trim_pieces]
        self.assertEqual(sorted(automatic), [False, True])  # automatic: only the half on the scan
        self.dispatch("model.trim_cut_clear")
        self.dispatch("model.trim")
        self.assertTrue(self.modeling.configure(trim_manual=True).success)
        self.dispatch("model.trim_cut")
        self.modeling.trim_cut_point((0.0, -2.0, 0.0), DOWN)
        self.modeling.trim_cut_point((0.0, 2.0, 0.0), DOWN)
        self.dispatch("model.trim_cut_finish")
        self.assertTrue(all(piece["keep"] for piece in self.modeling.session.trim_pieces))

    def test_a_one_point_line_is_cancelled_and_clear_forgets_cuts(self) -> None:
        self.dispatch("model.trim")
        self.dispatch("model.trim_cut")
        self.modeling.trim_cut_point((0.0, 0.0, 0.0), DOWN)
        result = self.dispatch("model.trim_cut_finish")
        self.assertIn("cancelled", result.status)
        self.assertFalse(self.modeling.session.trim_drawing)
        self.assertEqual(self.modeling.session.trim_cuts, [])

    def test_drawing_with_the_mouse_and_enter(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        from openretop.presentation.qt.main_window import OpenRetopV3Window
        from openretop.viewer.picking_service import SceneObjectPickResult

        QApplication.instance() or QApplication([])
        window = OpenRetopV3Window(self.composition)
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        window._invoke_from_ui("model.trim")
        window._dispatch_application_action("model.trim_cut")
        self.assertEqual(window.viewport.left_capture_owner, "trim_cut")
        for x, y in ((5.0, -3.0), (5.0, 3.0)):
            pick = SceneObjectPickResult(hit=True, object_id=f"model-face:{self.plane.id}", object_type="model_face", position=np.array([x, y, 0.0]))
            window.viewport._last_pointer_release_was_click = True
            with patch.object(window, "_view_direction", return_value=DOWN):
                window._on_viewport_pointer("left_release", 0, 0, pick)
        self.assertEqual(len(self.modeling.session.trim_cut), 2)
        self.assertTrue(window._sketch2d_lines())  # the line is drawn over the scene
        self.assertTrue(window._handle_tool_key(Qt.Key.Key_Return, ""))
        self.assertEqual(len(self.modeling.session.trim_pieces), 2)
        self.assertIn("2 pieces", window.surfacing_panel.trim_info.text())

    def test_real_mouse_clicks_place_cut_points(self) -> None:
        """Through the view's own press / release handling: a click in Cut Line used to be
        taken for a drag (the tool owned the press), so no point was ever placed."""

        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QApplication

        from openretop.presentation.qt.main_window import OpenRetopV3Window
        from openretop.viewer.picking_service import SceneObjectPickResult

        QApplication.instance() or QApplication([])
        window = OpenRetopV3Window(self.composition)
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        window._invoke_from_ui("model.trim")
        window._dispatch_application_action("model.trim_cut")
        viewport = window.viewport
        spots = iter((np.array([5.0, -3.0, 0.0]), np.array([5.0, 3.0, 0.0])))

        def pick(_x: int, _y: int) -> SceneObjectPickResult:
            return SceneObjectPickResult(hit=True, object_id=f"model-face:{self.plane.id}", object_type="model_face", position=next(spots))

        def mouse(kind: QEvent.Type, buttons: Qt.MouseButton) -> QMouseEvent:
            point = QPointF(40.0, 40.0)
            return QMouseEvent(kind, point, point, Qt.LeftButton, buttons, Qt.NoModifier)

        with patch.object(viewport, "pick_scene_object", side_effect=pick), patch.object(window, "_view_direction", return_value=DOWN):
            for _ in range(2):
                viewport.eventFilter(viewport.interactor, mouse(QEvent.MouseButtonPress, Qt.LeftButton))
                viewport.eventFilter(viewport.interactor, mouse(QEvent.MouseButtonRelease, Qt.NoButton))
                self.app_events()
        self.assertEqual(len(self.modeling.session.trim_cut), 2)

    def app_events(self) -> None:
        from PySide6.QtTest import QTest

        QTest.qWait(20)  # an unclaimed click is delivered on the next event-loop turn


if __name__ == "__main__":
    unittest.main()
