"""Milestone S end to end through the application actions: B1 bracket from scan to solid.

What a user does in the app: smart-select each face of the scan, Fit (auto type) and Create;
Trim keeps the pieces on the scan and sews them; Compare colours the deviation; Export writes
STEP. Every step goes through ``workflow.dispatch`` as the toolbar and panel do, with the
kernel worker inline.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

try:
    import cadquery  # noqa: F401
    import OCP  # noqa: F401

    HAVE_KERNEL = True
except ImportError:  # pragma: no cover
    HAVE_KERNEL = False

from openretop.application.state import MeshObjectState
from openretop.bootstrap import create_application
from openretop.cad_kernel.worker import KernelWorker
from openretop.infrastructure.settings_repository import InMemorySettingsRepository
from openretop.mesh.triangle_mesh import TriangleMeshData


def _composition():
    return create_application(settings_repository=InMemorySettingsRepository(), kernel_worker=KernelWorker(inline=True))


def _install(composition, vertices: np.ndarray, triangles: np.ndarray) -> None:
    mesh = TriangleMeshData(vertices=np.asarray(vertices, dtype=float), triangles=np.asarray(triangles, dtype=int))
    composition.state.mesh_object = MeshObjectState(
        source_mesh=mesh,
        display_mesh=mesh.copy(),
        file_path=None,
        name="scan",
        origin=np.zeros(3),
        location=np.zeros(3),
        rotation=np.zeros(3),
        transform_matrix=np.identity(4),
    )


class ScanSelectionTests(unittest.TestCase):
    def _plate_with_step(self):
        # two flat strips meeting at a 90 degree step: smart select stops at the crease
        x, y = np.meshgrid(np.linspace(0, 20, 21), np.linspace(0, 10, 11), indexing="ij")
        floor = np.c_[x.ravel(), y.ravel(), np.zeros(x.size)]
        wall = np.c_[np.full(x.size, 20.0), y.ravel(), x.ravel()]
        index = np.arange(21 * 11).reshape(21, 11)
        a, b, c, d = index[:-1, :-1].ravel(), index[:-1, 1:].ravel(), index[1:, :-1].ravel(), index[1:, 1:].ravel()
        quads = np.r_[np.c_[a, c, d], np.c_[a, d, b]]
        vertices = np.vstack([floor, wall])
        triangles = np.vstack([quads, quads + len(floor)])
        # stitch: the wall's first row coincides with the floor's last row
        wall_start = index[-1, :]  # floor x = 20
        remap = np.arange(len(vertices))
        remap[len(floor) + index[0, :]] = wall_start
        return vertices, remap[triangles], len(quads)

    def test_smart_select_stops_at_a_crease_and_brush_paints(self) -> None:
        from openretop.modeling import ScanSelection

        vertices, triangles, floor_count = self._plate_with_step()
        selection = ScanSelection(vertices, triangles)
        reached = selection.smart_select(5, 5.0)
        # the floor, less the ring of triangles touching the crease (their smoothed normals
        # lean towards the wall: on a scan that ring is the scanner-rounded edge)
        self.assertTrue(0.9 * floor_count <= reached <= floor_count, reached)
        self.assertFalse(np.any(selection.mask[floor_count:]))  # nothing of the wall
        selection.smart_select(5, 5.0, add=False)
        self.assertEqual(selection.count, 0)
        whole = selection.smart_select(5, 5.0, connected=True)
        self.assertEqual(whole, len(triangles))
        selection.clear()
        painted = selection.brush((10.0, 5.0, 0.0), 2.0)
        self.assertGreater(painted, 0)
        self.assertTrue(np.all(np.linalg.norm(selection.centroids()[selection.mask] - [10, 5, 0], axis=1) <= 2.0))
        selection.brush((10.0, 5.0, 0.0), 1.0, add=False)
        self.assertLess(selection.count, painted)


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class BracketInTheAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from openretop.benchmarks import make_part, scan_from_part

        cls.part = make_part("bracket")
        cls.scan = scan_from_part(cls.part, noise_sigma=0.02, seed=1, edge_length=1.0)

    def setUp(self) -> None:
        self.composition = _composition()
        _install(self.composition, self.scan.vertices, self.scan.triangles)
        self.workflow = self.composition.workflow
        self.modeling = self.composition.modeling_controller

    def _dispatch(self, action: str, payload: dict | None = None):
        result = self.workflow.dispatch(action, payload or {})
        self.assertTrue(result.success, (action, result.errors))
        return result

    def _seed_of(self, face: int) -> int:
        """The triangle of a true face farthest inside it (where a user would click)."""

        from scipy.spatial import cKDTree

        centers = self.scan.vertices[self.scan.triangles].mean(axis=1)
        inside = self.scan.face_labels == face
        # the middle of a ring (the boss top) is its hole: click farthest from every other face
        distance, _index = cKDTree(centers[~inside]).query(centers[inside])
        return int(np.nonzero(inside)[0][int(np.argmax(distance))])

    def test_fit_a_face_create_undo_redo(self) -> None:
        self._dispatch("model.fit_surface")
        biggest = int(np.argmax(np.bincount(self.scan.face_labels)))
        result = self.modeling.select_at(self._seed_of(biggest))
        self.assertTrue(result.success)
        selection = self.modeling.selection()
        truth = self.scan.face_labels[selection.mask]
        self.assertGreater(np.mean(truth == biggest), 0.97)  # one click took (mostly) the true face
        self._dispatch("model.fit_preview")
        preview = self.modeling.session.preview
        self.assertEqual(preview["kind"], "plane")
        self.assertLess(preview["rms"], 0.04)
        self._dispatch("model.fit_create")
        self.assertEqual(len(self.composition.state.model.entities), 1)
        self.assertEqual(self.modeling.selection().count, 0)
        self._dispatch("edit.undo")
        self.assertEqual(len(self.composition.state.model.entities), 0)
        self._dispatch("edit.redo")
        self.assertEqual(len(self.composition.state.model.entities), 1)

    def test_scan_to_solid_entirely_through_the_tools(self) -> None:
        self._dispatch("model.fit_surface")
        self._dispatch("model.configure", {"fit_expand": 0.3})
        made = 0
        for face in range(len(self.part.face_types)):
            narrow = int(np.sum(self.scan.face_labels == face)) < 300
            self.modeling.select_at(self._seed_of(face))
            if narrow or self.modeling.selection().count < 40:
                # a narrow face (a chamfer), or a click that landed on an edge: brush along
                # it and, for the chamfers, choose Plane, as the walkthrough tells a user to
                self.modeling.clear_selection()
                self._dispatch("model.configure", {"selection_mode": "brush", "brush_radius": 0.3})
                triangles = np.nonzero(self.scan.face_labels == face)[0]
                for center in self.scan.vertices[self.scan.triangles[triangles]].mean(axis=1):
                    self.modeling.brush_at(center)
                self._dispatch("model.configure", {"selection_mode": "smart"})
            kind = "plane" if narrow and self.part.face_types[face] == "PLANE" else "auto"
            self._dispatch("model.configure", {"fit_kind": kind})
            created = self.workflow.dispatch("model.fit_create", {})
            self.assertTrue(created.success, created.errors)
            made += 1
        self.assertGreaterEqual(made, 12)
        self._dispatch("model.trim")
        self._dispatch("model.trim_compute")
        pieces = self.modeling.session.trim_pieces
        self.assertGreater(len(pieces), made)
        self._dispatch("model.trim_apply", {"sew": True})
        bodies = [entity for entity in self.composition.state.model.entities if entity.is_body]
        self.assertEqual(len(bodies), 1)
        body = bodies[0]
        self.assertTrue(body.stats.get("solid"), body.stats)
        volume = self.part.truth["volume"]
        self.assertLess(abs(body.stats["volume"] - volume) / volume, 0.005)
        # the fitted surfaces are hidden, not deleted: trimming again stays possible
        self.assertTrue(all(not entity.visible for entity in self.composition.state.model.entities if not entity.is_body))

        self._dispatch("model.compare")
        self._dispatch("model.compare_apply")
        stats = self.modeling.deviation.statistics()
        self.assertGreater(stats["within"], 0.9)  # the scanner-rounded edges are the rest

        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "bracket.step")
            exported = self.modeling.export(path, entity_ids=(body.id,))
            self.assertTrue(exported.success, exported.errors)
            self.assertFalse(exported.warnings)
            self.assertTrue(Path(path).stat().st_size > 1000)

    def test_failures_come_back_as_messages(self) -> None:
        self._dispatch("model.fit_surface")
        result = self.workflow.dispatch("model.fit_preview", {})
        self.assertFalse(result.success)
        self.assertIn("Select an area", result.errors[0])
        trim = self.workflow.dispatch("model.trim_compute", {})
        self.assertFalse(trim.success)
        loft = self.workflow.dispatch("model.loft_apply", {})
        self.assertFalse(loft.success)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class SurfacingWindowTests(unittest.TestCase):
    """The tools in the main window: toolbar row, panel, tree group, Esc."""

    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_fit_surface_from_the_toolbar_to_the_tree(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QToolBar

        from openretop.presentation.qt.main_window import OpenRetopV3Window

        composition = _composition()
        x, y = np.meshgrid(np.linspace(0, 30, 31), np.linspace(0, 20, 21), indexing="ij")
        vertices = np.c_[x.ravel(), y.ravel(), np.random.default_rng(0).normal(0, 0.01, x.size)]
        index = np.arange(31 * 21).reshape(31, 21)
        a, b, c, d = index[:-1, :-1].ravel(), index[:-1, 1:].ravel(), index[1:, :-1].ravel(), index[1:, 1:].ravel()
        _install(composition, vertices, np.r_[np.c_[a, c, d], np.c_[a, d, b]])
        window = OpenRetopV3Window(composition)
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        window.refresh()
        surfacing = window.findChild(QToolBar, "toolbar_Surfacing")
        self.assertIn(window._qt_actions["model.fit_surface"], surfacing.actions())
        self.assertTrue(window._qt_actions["model.fit_surface"].isEnabled())
        self.assertFalse(window._qt_actions["model.trim"].isEnabled())  # nothing to trim yet

        window._qt_actions["model.fit_surface"].trigger()
        self.assertTrue(window.surfacing_panel.isVisibleTo(window))
        self.assertFalse(window.inspector.isVisibleTo(window))
        self.assertEqual(window.surfacing_panel.title.text(), "Fit Surface")
        self.assertEqual(window.viewport.left_capture_owner, None)  # smart select: drags still orbit
        window.surfacing_panel.mode_buttons["brush"].click()
        self.assertEqual(window.viewport.left_capture_owner, "modeling_brush")
        window.surfacing_panel.mode_buttons["smart"].click()

        composition.modeling_controller.select_at(5)
        window.refresh()
        self.assertIn("triangles selected", window.surfacing_panel.selection_info.text())
        window.surfacing_panel.create_button.click()  # inline executor: runs at once
        model = composition.state.model
        self.assertEqual(len(model.entities), 1)
        self.assertEqual(model.entities[0].kind, "plane")
        self.assertIn("model:" + model.entities[0].id, set(window._scene_model.nodes))
        snapshot = window.viewport.last_snapshot or window.viewport._pending_snapshot
        self.assertTrue(any(item.id.startswith("model-face:") for item in snapshot.model_faces))

        window._handle_tool_key(Qt.Key.Key_Escape)
        self.assertFalse(composition.modeling_controller.active)
        self.assertFalse(window.surfacing_panel.isVisibleTo(window))
        self.assertTrue(window._qt_actions["model.trim"].isEnabled())  # the model has a surface now


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class CurveToolTests(unittest.TestCase):
    """Loft and Fill from curves (curves drawn on the scan are stored curves)."""

    def setUp(self) -> None:
        self.composition = _composition()
        self.workflow = self.composition.workflow

    def _curve(self, name: str, points: np.ndarray) -> str:
        from openretop.curves.curve_state import StoredCurve, add_curve

        curve = StoredCurve(
            id=name, name=name, section_result_id="", plane_id="", original_points=points, fitted_points=points,
            mean_error=0.0, max_error=0.0, is_closed=False,
        )
        add_curve(self.composition.state.curve_collection, curve)
        return name

    def test_loft_between_two_selected_curves(self) -> None:
        angle = np.linspace(0, np.pi, 40)
        first = self._curve("c1", np.c_[20 * np.cos(angle), 20 * np.sin(angle), np.zeros(40)])
        second = self._curve("c2", np.c_[20 * np.cos(angle), 20 * np.sin(angle), np.full(40, 30.0)])
        self.composition.state.curve_collection.selected_curve_ids = {first, second}
        result = self.workflow.dispatch("model.loft_apply", {"curve_ids": [first, second]})
        self.assertTrue(result.success, result.errors)
        entity = self.composition.state.model.entities[-1]
        self.assertEqual(entity.kind, "loft")
        self.assertAlmostEqual(entity.stats["area"], np.pi * 20 * 30, delta=1.0)

    def test_fill_a_boundary_of_four_curves(self) -> None:
        s = np.linspace(-10, 10, 25)
        z = lambda x, y: (x**2 - y**2) / 40.0  # noqa: E731
        ids = [
            self._curve("s1", np.c_[s, np.full(25, -10.0), z(s, -10.0)]),
            self._curve("s2", np.c_[np.full(25, 10.0), s, z(10.0, s)]),
            self._curve("s3", np.c_[s, np.full(25, 10.0), z(s, 10.0)]),
            self._curve("s4", np.c_[np.full(25, -10.0), s, z(-10.0, s)]),
        ]
        self.assertTrue(self.workflow.dispatch("model.fill", {}).success)
        self.workflow.dispatch("model.configure", {"fill_on_scan": False})
        for curve_id in ids:
            self.assertTrue(self.composition.modeling_controller.fill_add_curve(curve_id).success)
        smooth = self.workflow.dispatch("model.fill_continuity", {"index": 0, "continuity": "smooth"})
        self.assertFalse(smooth.success)  # a curve has no tangent plane to follow
        result = self.workflow.dispatch("model.fill_apply", {})
        self.assertTrue(result.success, result.errors)
        entity = self.composition.state.model.entities[-1]
        self.assertEqual(entity.kind, "fill")
        self.assertGreater(entity.stats["area"], 400.0)
