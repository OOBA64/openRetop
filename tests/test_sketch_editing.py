"""Surface Sketch curves that follow the scan and stay editable (user feedback on a car fender scan).

- A curve runs along the surface between its points; on a large scan with a hole between two
  points it is still quick (the old line-pushed-onto-the-scan froze the app for ~10 s a click
  on an 800k-triangle fender).
- "Follow body lines": two clicks at the ends of a curved crease trace the crease; a plain
  curve cuts the corner.
- Every curve is editable, one undo step each: add a point on it, delete a point, split it,
  open / close it, reverse it, change its smoothness and crease following; the options are
  saved with the project. In the window a double click on a curve adds a point and a right
  click offers the edits.
"""

from __future__ import annotations

import time
import unittest

import numpy as np

from openretop.application.state import MeshObjectState
from openretop.bootstrap import create_application
from openretop.cad_kernel.worker import KernelWorker
from openretop.infrastructure.settings_repository import InMemorySettingsRepository
from openretop.mesh.triangle_mesh import TriangleMeshData
from openretop.modeling.persistence import model_from_dict, model_to_dict
from openretop.modeling.sketch import MeshProjector, Sketch, curve_on_mesh


def grid(count_x: int, count_y: int, size_x: float, size_y: float, height) -> tuple[np.ndarray, np.ndarray]:
    x, y = np.meshgrid(np.linspace(0, size_x, count_x), np.linspace(-size_y / 2, size_y / 2, count_y), indexing="ij")
    vertices = np.c_[x.ravel(), y.ravel(), height(x.ravel(), y.ravel())]
    index = np.arange(count_x * count_y).reshape(count_x, count_y)
    a, b, c, d = index[:-1, :-1].ravel(), index[:-1, 1:].ravel(), index[1:, :-1].ravel(), index[1:, 1:].ravel()
    return vertices, np.r_[np.c_[a, c, d], np.c_[a, d, b]]


def ridge_y(x: np.ndarray | float) -> np.ndarray | float:
    return 12.0 * np.sin(np.asarray(x) / 25.0)


class CurveEngineTests(unittest.TestCase):
    def test_a_big_scan_with_a_hole_between_the_points_stays_quick(self) -> None:
        vertices, triangles = grid(320, 320, 400.0, 400.0, lambda x, y: 0.002 * (x - 200) ** 2)
        centers = vertices[triangles].mean(axis=1)
        keep = np.hypot(centers[:, 0] - 200, centers[:, 1]) > 60  # a hole 120 across in the middle
        projector = MeshProjector(vertices, triangles[keep])
        projector.graph  # noqa: B018  # built once when the tool opens
        started = time.perf_counter()
        line = curve_on_mesh(np.array([[100.0, 0.0, 20.0], [300.0, 0.0, 20.0]]), projector)
        self.assertLess(time.perf_counter() - started, 1.5)
        closest, _ = projector.project(line)
        self.assertLess(float(np.max(np.linalg.norm(closest - line, axis=1))), 1e-6)  # on the scan, round the hole
        self.assertGreater(float(np.min(np.hypot(line[:, 0] - 200, line[:, 1]))), 55.0)

    def test_follow_body_lines_traces_a_curved_crease_from_two_clicks(self) -> None:
        vertices, triangles = grid(241, 121, 240.0, 120.0, lambda x, y: 20.0 - 0.6 * np.abs(y - ridge_y(x)))
        projector = MeshProjector(vertices, triangles)
        ends = np.array([[5.0, float(ridge_y(5.0)), 20.0], [235.0, float(ridge_y(235.0)), 20.0]])
        followed = curve_on_mesh(ends, projector, feature=True)
        plain = curve_on_mesh(ends, projector, feature=False)
        off_followed = np.abs(followed[:, 1] - ridge_y(followed[:, 0]))
        off_plain = np.abs(plain[:, 1] - ridge_y(plain[:, 0]))
        self.assertLess(float(np.median(off_followed)), 0.6)  # on the crease (grid spacing 1)
        self.assertLess(float(np.max(off_followed)), 2.0)
        self.assertGreater(float(np.max(off_plain)), 6.0)  # cuts the crease's bends

    def test_a_curve_through_points_has_no_corner_at_them(self) -> None:
        vertices, triangles = grid(161, 161, 160.0, 160.0, lambda x, y: 0.004 * ((x - 80) ** 2 + y**2))
        projector = MeshProjector(vertices, triangles)
        points = np.array([[20.0, -50.0, 0.0], [80.0, 10.0, 0.0], [140.0, -40.0, 0.0]])
        line = curve_on_mesh(points, projector, smoothness=0.6)
        steps = np.diff(line, axis=0)
        steps /= np.linalg.norm(steps, axis=1, keepdims=True)
        turn = np.degrees(np.arccos(np.clip(np.einsum("ij,ij->i", steps[:-1], steps[1:]), -1, 1)))
        self.assertLess(float(turn.max()), 12.0)


class SketchEditTests(unittest.TestCase):
    def setUp(self) -> None:
        vertices, triangles = grid(101, 101, 100.0, 100.0, lambda x, y: 0.003 * (x - 50) ** 2)
        self.projector = MeshProjector(vertices, triangles)
        self.sketch = Sketch()

    def on(self, x: float, y: float) -> np.ndarray:
        return np.array([x, y, 0.003 * (x - 50) ** 2])

    def curve(self, *points, closed=False):
        nodes = [self.sketch.new_node(self.on(*point)) for point in points]
        return self.sketch.add_curve(nodes, self.projector, closed=closed)

    def test_insert_split_close_reverse(self) -> None:
        curve = self.curve((10, 0), (50, 20), (90, 0))
        inserted = self.sketch.insert_node(curve.id, self.on(70, 12), self.projector)
        self.assertEqual(curve.nodes.index(inserted), 2)  # between the 2nd and 3rd points
        np.testing.assert_allclose(curve.polyline[0], self.sketch.nodes[curve.nodes[0]], atol=1e-9)
        made = self.sketch.split_curve(curve.id, inserted, self.projector)
        first, second = (self.sketch.curve(value) for value in made)
        self.assertEqual(first.nodes[-1], second.nodes[0])  # they share the split point
        self.assertEqual(len(first.nodes) + len(second.nodes), 5)
        self.sketch.set_closed(first.id, True, self.projector)
        self.assertTrue(first.closed)
        self.sketch.split_curve(first.id, first.nodes[1], self.projector)  # a closed curve opens there
        self.assertFalse(first.closed)
        self.assertEqual(first.nodes[0], first.nodes[-1])
        ends = (second.nodes[0], second.nodes[-1])
        self.sketch.reverse(second.id)
        self.assertEqual((second.nodes[-1], second.nodes[0]), ends)
        with self.assertRaises(ValueError):
            self.sketch.split_curve(second.id, second.nodes[0], self.projector)  # already an end

    def test_options_rebuild_and_are_saved(self) -> None:
        curve = self.curve((10, -30), (90, 30))
        before = curve.polyline.copy()
        self.sketch.set_options(curve.id, self.projector, smoothness=0.0, feature=True)
        self.assertEqual((curve.smoothness, curve.feature), (0.0, True))
        self.assertFalse(np.array_equal(before, curve.polyline) and len(before) == len(curve.polyline))

        from openretop.modeling.document import ModelDocument

        document = ModelDocument()
        document.sketch = self.sketch
        back, warnings = model_from_dict(model_to_dict(document))
        self.assertEqual(warnings, [])
        self.assertEqual((back.sketch.curves[0].smoothness, back.sketch.curves[0].feature), (0.0, True))


class SketchEditControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.composition = create_application(settings_repository=InMemorySettingsRepository(), kernel_worker=KernelWorker(inline=True))
        vertices, triangles = grid(81, 81, 80.0, 80.0, lambda x, y: 0.002 * (x - 40) ** 2)
        mesh = TriangleMeshData(vertices=vertices, triangles=triangles)
        self.composition.state.mesh_object = MeshObjectState(
            source_mesh=mesh,
            display_mesh=mesh.copy(),
            file_path=None,
            name="scan",
            origin=np.zeros(3),
            location=np.zeros(3),
            rotation=np.zeros(3),
            transform_matrix=np.identity(4),
        )
        self.modeling = self.composition.modeling_controller
        self.workflow = self.composition.workflow
        self.assertTrue(self.workflow.dispatch("model.sketch", {}).success)
        for x, y in ((10, 0), (40, 25), (70, 0)):
            self.modeling.sketch_click(np.array([x, y, 0.002 * (x - 40) ** 2]))
        self.modeling.sketch_finish()
        self.sketch = self.composition.state.model.sketch

    def dispatch(self, action: str, payload: dict | None = None):
        result = self.workflow.dispatch(action, payload or {})
        self.assertTrue(result.success, (action, result.errors))
        return result

    def test_edits_are_undoable_one_by_one(self) -> None:
        curve = self.sketch.curves[0]
        self.dispatch("model.sketch_insert_point", {"curve": curve.id, "position": [55.0, 14.0, 0.5]})
        self.assertEqual(len(self.sketch.curves[0].nodes), 4)
        self.dispatch("model.sketch_delete_point")  # the new point is selected
        self.assertEqual(len(self.composition.state.model.sketch.curves[0].nodes), 3)
        self.dispatch("edit.undo")
        self.assertEqual(len(self.composition.state.model.sketch.curves[0].nodes), 4)
        self.dispatch("edit.undo")
        self.assertEqual(len(self.composition.state.model.sketch.curves[0].nodes), 3)

    def test_split_close_reverse_and_options_on_the_selected_curve(self) -> None:
        middle = self.sketch.curves[0].nodes[1]
        self.assertTrue(self.modeling.sketch_select_node(middle).success)
        self.dispatch("model.sketch_split")
        sketch = self.composition.state.model.sketch
        self.assertEqual(len(sketch.curves), 2)
        self.modeling.sketch_select_curves((sketch.curves[0].id,))
        self.dispatch("model.sketch_reverse")
        self.dispatch("model.sketch_options", {"feature": True, "smoothness": 0.2})
        curve = self.composition.state.model.sketch.curves[0]
        self.assertEqual((curve.feature, curve.smoothness), (True, 0.2))
        self.assertTrue(self.modeling.session.sketch_feature)  # and new curves follow too
        refused = self.workflow.dispatch("model.sketch_toggle_closed", {"curves": [curve.id]})  # two points: cannot close
        self.assertFalse(refused.success)
        self.assertIn("three points", " ".join(refused.errors))
        self.assertFalse(self.composition.state.model.sketch.curves[0].closed)

    def test_show_body_lines_colours_the_scan(self) -> None:
        self.modeling.configure(show_creases=True)
        strength = self.modeling.sketch_crease_strength()
        self.assertEqual(len(strength), len(self.composition.state.mesh_object.display_mesh.vertices))
        self.assertTrue(np.all((strength >= 0) & (strength <= 1)))


class SketchEditWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_double_click_adds_a_point_and_right_click_offers_edits(self) -> None:
        from PySide6.QtCore import Qt

        from openretop.presentation.qt.main_window import OpenRetopV3Window

        composition = create_application(settings_repository=InMemorySettingsRepository(), kernel_worker=KernelWorker(inline=True))
        vertices, triangles = grid(61, 61, 60.0, 60.0, lambda x, y: np.zeros_like(x))
        mesh = TriangleMeshData(vertices=vertices, triangles=triangles)
        composition.state.mesh_object = MeshObjectState(
            source_mesh=mesh, display_mesh=mesh.copy(), file_path=None, name="scan", origin=np.zeros(3),
            location=np.zeros(3), rotation=np.zeros(3), transform_matrix=np.identity(4),
        )
        window = OpenRetopV3Window(composition)
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        window.refresh()
        window._qt_actions["model.sketch"].trigger()
        modeling = composition.modeling_controller
        for x in (10.0, 30.0, 50.0):
            modeling.sketch_click(np.array([x, 0.0, 0.0]))
        window._handle_tool_key(Qt.Key.Key_Return)
        curve = composition.state.model.sketch.curves[0]
        window._sketch_curve_at = lambda x, y: (curve.id, (20.0, 0.0, 0.0))
        window._sketch_node_at = lambda x, y: None
        window._surfacing_pointer("double_click", 5, 5, None)
        self.assertEqual(len(composition.state.model.sketch.curves[0].nodes), 4)
        selected = modeling.session.selected_node
        window._sketch_node_at = lambda x, y: selected
        window._surfacing_pointer("right_click", 5, 5, None)
        labels = [action.text() for action in window._sketch_last_menu.actions() if action.text()]
        for label in ("Delete Point", "Split Curve Here", "Open / Close Curve", "Reverse Curve", "Follow Body Lines"):
            self.assertIn(label, labels)
        window._sketch_last_menu.close()


if __name__ == "__main__":
    unittest.main()
