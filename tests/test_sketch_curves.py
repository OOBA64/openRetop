"""3D Sketch: curves through points that lie on the scan, joined into networks, made into faces.

Owner report (2026-10-08): curves "never follow the face of a mesh, always extending beyond or
curving weird", and points could not be connected to make a face. Acceptance: curves pass
exactly through their points, end there, stay on the scan even where the straight run between
two points dips inside the part, and a loop of connected curves becomes a face fitted to the
scan inside it.
"""

from __future__ import annotations

import unittest

import numpy as np

try:
    import cadquery  # noqa: F401
    import OCP  # noqa: F401

    HAVE_KERNEL = True
except ImportError:  # pragma: no cover
    HAVE_KERNEL = False

from openretop.modeling.sketch import (
    MeshProjector,
    Sketch,
    boundary_loop,
    catmull_rom,
    closest_points_on_triangles,
    curve_on_mesh,
    loop_polylines,
    region_inside,
)


def _cylinder_mesh(radius: float = 20.0, height: float = 30.0, around: int = 120, up: int = 40):
    """A closed-around open cylinder wall (axis Z), outward-wound."""

    angle, z = np.meshgrid(np.linspace(0, 2 * np.pi, around, endpoint=False), np.linspace(0, height, up), indexing="ij")
    vertices = np.c_[(radius * np.cos(angle)).ravel(), (radius * np.sin(angle)).ravel(), z.ravel()]
    index = np.arange(around * up).reshape(around, up)
    nxt = np.roll(index, -1, axis=0)
    a, b, c, d = index[:, :-1].ravel(), index[:, 1:].ravel(), nxt[:, :-1].ravel(), nxt[:, 1:].ravel()
    return vertices, np.r_[np.c_[a, c, d], np.c_[a, d, b]]


class GeometryTests(unittest.TestCase):
    def test_closest_point_on_a_triangle_in_every_region(self) -> None:
        a, b, c = np.array([0.0, 0, 0]), np.array([4.0, 0, 0]), np.array([0.0, 4, 0])
        cases = {
            (1.0, 1.0, 3.0): (1.0, 1.0, 0.0),  # above the face
            (-2.0, -2.0, 0.0): (0.0, 0.0, 0.0),  # vertex a
            (6.0, -1.0, 0.0): (4.0, 0.0, 0.0),  # vertex b
            (2.0, -3.0, 1.0): (2.0, 0.0, 0.0),  # edge ab
            (-3.0, 2.0, 0.0): (0.0, 2.0, 0.0),  # edge ac
            (3.0, 3.0, 0.0): (2.0, 2.0, 0.0),  # edge bc
        }
        for point, expected in cases.items():
            with self.subTest(point=point):
                result = closest_points_on_triangles(np.array(point), a, b, c)
                np.testing.assert_allclose(result, expected, atol=1e-12)

    def test_centripetal_curve_does_not_overshoot_uneven_points(self) -> None:
        points = np.array([[0.0, 0, 0], [1.0, 0, 0], [10.0, 0, 0], [10.5, 0, 0]])
        line, held = catmull_rom(points, samples_per_unit=10)
        np.testing.assert_allclose(line[held], points)
        self.assertTrue(np.all(np.diff(line[:, 0]) >= -1e-9))  # never runs backwards past a point
        self.assertAlmostEqual(float(np.abs(line[:, 1:]).max()), 0.0)


class CurveOnScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.vertices, self.triangles = _cylinder_mesh()
        self.projector = MeshProjector(self.vertices, self.triangles)

    def _on(self, degrees: float, z: float) -> np.ndarray:
        angle = np.radians(degrees)
        return np.array([20 * np.cos(angle), 20 * np.sin(angle), z])

    def test_a_curve_across_a_curved_face_stays_on_it(self) -> None:
        # 120 degrees apart: the straight run between the points is 10 mm inside the wall,
        # and its middle is closer to the far side of the cylinder than the plain closest
        # point would like
        points = np.array([self._on(-60, 5), self._on(0, 15), self._on(60, 25)])
        line = curve_on_mesh(points, self.projector)
        radius = np.hypot(line[:, 0], line[:, 1])
        self.assertLess(float(np.abs(radius - 20.0).max()), 0.05)  # on the wall (facets: < 0.04)
        self.assertGreater(float(line[:, 0].min()), 9.0)  # on the near side of the cylinder only
        steps = np.linalg.norm(np.diff(line, axis=0), axis=1)
        self.assertLess(float(steps.max()), 2.0 * self.projector.spacing)  # no jumps
        np.testing.assert_allclose(line[0], self.projector.project(points[:1])[0][0], atol=1e-9)
        np.testing.assert_allclose(line[-1], self.projector.project(points[-1:])[0][0], atol=1e-9)

    def test_a_network_of_curves_makes_a_closed_loop_and_follows_moved_points(self) -> None:
        sketch = Sketch()
        corners = [sketch.new_node(self._on(a, z)) for a, z in ((-30, 5), (30, 5), (30, 25), (-30, 25))]
        curves = [sketch.add_curve([corners[k], corners[(k + 1) % 4]], self.projector) for k in range(4)]
        chain = boundary_loop(sketch, [curves[2].id, curves[0].id, curves[3].id, curves[1].id])
        self.assertIsNotNone(chain)
        outline = loop_polylines(chain)
        for first, second in zip(outline, outline[1:] + outline[:1], strict=True):
            np.testing.assert_allclose(first[-1], second[0], atol=1e-9)  # the loop is closed
        self.assertIsNone(boundary_loop(sketch, [curves[0].id, curves[1].id]))  # not closed

        moved = sketch.move_node(corners[1], self._on(35, 4), self.projector)
        self.assertEqual(set(moved), {curves[0].id, curves[1].id})
        np.testing.assert_allclose(curves[0].polyline[-1], sketch.nodes[corners[1]], atol=1e-9)
        np.testing.assert_allclose(curves[1].polyline[0], sketch.nodes[corners[1]], atol=1e-9)

        sketch.remove_curves([curves[0].id])
        self.assertEqual(len(sketch.curves), 3)
        self.assertEqual(len(sketch.nodes), 4)  # every point is still used by a curve

    def test_the_region_inside_a_loop(self) -> None:
        sketch = Sketch()
        corners = [sketch.new_node(self._on(a, z)) for a, z in ((-30, 5), (30, 5), (30, 25), (-30, 25))]
        curves = [sketch.add_curve([corners[k], corners[(k + 1) % 4]], self.projector) for k in range(4)]
        outline = np.vstack(loop_polylines(boundary_loop(sketch, [curve.id for curve in curves])))
        inside = region_inside(self.projector, outline)
        centers = self.projector.centroids[inside]
        angle = np.degrees(np.arctan2(centers[:, 1], centers[:, 0]))
        self.assertTrue(np.all(np.abs(angle) < 31) and np.all((centers[:, 2] > 4.5) & (centers[:, 2] < 25.5)))
        self.assertGreater(int(inside.sum()), 0.6 * 2 * (60 / 3) * (20 / (30 / 39)))  # most of the inside


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class SketchWorkflowTests(unittest.TestCase):
    """The casting's freeform side through the app's actions: draw four connected curves by
    clicking, make a face from them, loft two of them; undo."""

    @classmethod
    def setUpClass(cls) -> None:
        from openretop.benchmarks import make_part, scan_from_part

        cls.part = make_part("casting")
        cls.scan = scan_from_part(cls.part, noise_sigma=0.02, seed=1, edge_length=1.0)

    def setUp(self) -> None:
        from openretop.application.state import MeshObjectState
        from openretop.bootstrap import create_application
        from openretop.cad_kernel.worker import KernelWorker
        from openretop.infrastructure.settings_repository import InMemorySettingsRepository
        from openretop.mesh.triangle_mesh import TriangleMeshData

        self.composition = create_application(settings_repository=InMemorySettingsRepository(), kernel_worker=KernelWorker(inline=True))
        mesh = TriangleMeshData(vertices=self.scan.vertices.copy(), triangles=self.scan.triangles.copy())
        self.composition.state.mesh_object = MeshObjectState(
            source_mesh=mesh, display_mesh=mesh.copy(), file_path=None, name="casting",
            origin=np.zeros(3), location=np.zeros(3), rotation=np.zeros(3), transform_matrix=np.identity(4),
        )
        self.modeling = self.composition.modeling_controller
        self.workflow = self.composition.workflow
        self.projector = MeshProjector(self.scan.vertices, self.scan.triangles)

    def _outside_point(self, degrees: float, z: float) -> np.ndarray:
        direction = np.array([np.cos(np.radians(degrees)) * 1.3, np.sin(np.radians(degrees)), 0.0])
        direction /= np.linalg.norm(direction)
        ray = np.array([0.0, 0.0, z]) + np.outer(np.linspace(0, 40, 4000), direction)
        closest, _ = self.projector.project(ray)
        on = np.nonzero(np.linalg.norm(closest - ray, axis=1) < 0.2)[0]
        return closest[on[-1]]  # the outside of the casting, not its bore

    def _ok(self, result) -> None:
        self.assertTrue(result.success, result.errors)
        if result.undo_payload is not None and result.changed:
            self.composition.undo.push(result.undo_payload)

    def test_click_connected_curves_make_a_face_on_the_scan(self) -> None:
        from openretop.benchmarks import distance_to_reference
        from openretop.cad_kernel import surfacing

        self.assertTrue(self.workflow.dispatch("model.sketch", {}).success)
        corners = [self._outside_point(a, z) for a, z in ((-40, 5), (40, 5), (40, 19), (-40, 19))]
        # curve 1: bottom, three clicks, Enter
        self._ok(self.modeling.sketch_click(corners[0]))
        self._ok(self.modeling.sketch_click(self._outside_point(0, 4)))
        self._ok(self.modeling.sketch_click(corners[1]))
        self._ok(self.modeling.sketch_finish())
        sketch = self.composition.state.model.sketch
        first, last = sketch.curves[0].nodes[0], sketch.curves[0].nodes[-1]
        # curve 2: start ON the bottom curve's end point, click the top corner, Enter
        self._ok(self.modeling.sketch_click(None, last))
        self._ok(self.modeling.sketch_click(corners[2]))
        self._ok(self.modeling.sketch_finish())
        top_right = sketch.curves[1].nodes[-1]
        # curve 3 (top) and curve 4 (left side): snapping to the start point connects and ends
        self._ok(self.modeling.sketch_click(None, top_right))
        self._ok(self.modeling.sketch_click(corners[3]))
        self._ok(self.modeling.sketch_finish())
        top_left = sketch.curves[2].nodes[-1]
        self._ok(self.modeling.sketch_click(None, top_left))
        self._ok(self.modeling.sketch_click(None, first))  # snapping to a point finishes the curve
        self.assertEqual(len(sketch.curves), 4)
        self.assertEqual(len(sketch.nodes), 5)  # four corners (shared) and the bottom middle

        for curve in sketch.curves:
            self.assertLess(float(distance_to_reference(curve.polyline, self.part).max()), 0.1)

        result = self.workflow.dispatch("model.sketch_face", {"fit_to_scan": True})
        self.assertFalse(result.success)  # nothing selected yet
        self.modeling.sketch_select_curves(tuple(curve.id for curve in sketch.curves))
        result = self.workflow.dispatch("model.sketch_face", {"fit_to_scan": True})
        self.assertTrue(result.success, result.errors)
        face = self.composition.state.model.entities[-1]
        self.assertEqual(face.kind, "patch")
        self.assertLess(face.stats["rms"], 0.04)  # the scan's noise is 0.02
        shape = surfacing.from_brep(face.brep)
        error = distance_to_reference(surfacing.sample_face(shape, 3000), self.part)
        self.assertLess(float(np.sqrt(np.mean(error**2))), 0.05)
        self.assertEqual(len(surfacing.faces_of(shape)), 1)

        self.modeling.sketch_select_curves((sketch.curves[0].id, sketch.curves[2].id))
        loft = self.workflow.dispatch("model.sketch_loft", {})
        self.assertTrue(loft.success, loft.errors)

        # undo: the loft, the face, then curve 4 goes but the others and their points stay
        for _ in range(3):
            self.workflow.dispatch("edit.undo", {})
        self.assertEqual(len(self.composition.state.model.entities), 0)
        self.assertEqual(len(self.composition.state.model.sketch.curves), 3)

    def test_moving_a_shared_point_moves_both_curves_with_one_undo(self) -> None:
        self.workflow.dispatch("model.sketch", {})
        a, b, c = (self._outside_point(x, 10) for x in (-30, 0, 30))
        self._ok(self.modeling.sketch_click(a))
        self._ok(self.modeling.sketch_click(b))
        self._ok(self.modeling.sketch_finish())
        sketch = self.composition.state.model.sketch
        shared = sketch.curves[0].nodes[-1]
        self._ok(self.modeling.sketch_click(None, shared))
        self._ok(self.modeling.sketch_click(c))
        self._ok(self.modeling.sketch_finish())
        before = sketch.nodes[shared].copy()
        target = self._outside_point(0, 15)
        self.modeling.sketch_move_node(shared, self._outside_point(0, 12))
        self._ok(self.modeling.sketch_move_node(shared, target, final=True))
        sketch = self.composition.state.model.sketch
        np.testing.assert_allclose(sketch.curves[0].polyline[-1], sketch.nodes[shared], atol=1e-9)
        np.testing.assert_allclose(sketch.curves[1].polyline[0], sketch.nodes[shared], atol=1e-9)
        self.workflow.dispatch("edit.undo", {})
        np.testing.assert_allclose(self.composition.state.model.sketch.nodes[shared], before, atol=1e-9)

    def test_drawing_keys_finish_close_and_undo_points(self) -> None:
        self.workflow.dispatch("model.sketch", {})
        points = [self._outside_point(x, 12) for x in (-30, -10, 10)]
        for point in points:
            self._ok(self.modeling.sketch_click(point))
        self._ok(self.modeling.sketch_undo_point())
        self.assertEqual(len(self.modeling.session.sketch_points), 2)
        self.assertFalse(self.modeling.sketch_finish(close=True).success)  # a loop needs three
        self._ok(self.modeling.sketch_click(points[2]))
        self._ok(self.modeling.sketch_click(self._outside_point(0, 18)))
        first = self.modeling.session.sketch_points[0][1]
        closed = self.modeling.sketch_finish(close=True)
        self._ok(closed)
        curve = self.composition.state.model.sketch.curves[0]
        self.assertTrue(curve.closed)
        np.testing.assert_allclose(curve.polyline[0], curve.polyline[-1], atol=1e-9)
        np.testing.assert_allclose(curve.polyline[0], first, atol=1e-9)


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class SketchWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_the_tool_in_the_window(self) -> None:
        from PySide6.QtWidgets import QToolBar

        from openretop.application.state import MeshObjectState
        from openretop.bootstrap import create_application
        from openretop.cad_kernel.worker import KernelWorker
        from openretop.infrastructure.settings_repository import InMemorySettingsRepository
        from openretop.mesh.triangle_mesh import TriangleMeshData
        from openretop.presentation.qt.main_window import OpenRetopV3Window

        composition = create_application(settings_repository=InMemorySettingsRepository(), kernel_worker=KernelWorker(inline=True))
        vertices, triangles = _cylinder_mesh()
        mesh = TriangleMeshData(vertices=vertices, triangles=triangles)
        composition.state.mesh_object = MeshObjectState(
            source_mesh=mesh, display_mesh=mesh.copy(), file_path=None, name="cylinder",
            origin=np.zeros(3), location=np.zeros(3), rotation=np.zeros(3), transform_matrix=np.identity(4),
        )
        window = OpenRetopV3Window(composition)
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        window.refresh()
        toolbar = window.findChild(QToolBar, "toolbar_Surfacing")
        self.assertIn(window._qt_actions["model.sketch"], toolbar.actions())
        window._qt_actions["model.sketch"].trigger()
        self.assertEqual(window.surfacing_panel.title.text(), "3D Sketch")
        self.assertEqual(window.viewport.left_capture_owner, "sketch")
        self.assertTrue(window._surfacing_press_claim(5, 5) is False)  # no point there: the drag orbits

        modeling = composition.modeling_controller
        modeling.sketch_click(np.array([20.0, 0.0, 10.0]))
        modeling.sketch_click(np.array([0.0, 20.0, 10.0]))
        preview = window._tool_preview()
        self.assertTrue(preview.active)
        self.assertEqual(len(preview.control_points), 2)
        self.assertGreater(len(preview.fitted_points), 10)  # the live curve on the scan
        window._handle_tool_key(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.Key.Key_Return)
        self.assertEqual(len(composition.state.model.sketch.curves), 1)
        window.refresh()
        self.assertIn("sketch:" + composition.state.model.sketch.curves[0].id, set(window._scene_model.nodes))
        self.assertEqual(len(window._tool_preview().node_points), 2)
        snapshot = window.viewport.last_snapshot or window.viewport._pending_snapshot
        self.assertTrue(any(item.id.startswith("sketch-curve:") for item in snapshot.model_edges))


if __name__ == "__main__":
    unittest.main()
