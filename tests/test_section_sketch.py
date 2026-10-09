"""S-13: the Section Sketch tool in the app: plane, the scan's section, Fit Profile, Create.

Through the application actions (as the toolbar and panel use them) with the kernel inline:
the housing's section becomes one planar face with the pocket as its hole, of the true area;
the shaft's becomes its exact 16-line profile; clicking the scan moves the plane; undo, the
project file and the window all keep up.
"""

from __future__ import annotations

import json
import math
import unittest

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

HOUSING_AREA_Z0 = 60 * 40 - (4 - math.pi) * 9 - (40 * 24 - (4 - math.pi) * 4)  # wall ring with R3 / R2 corners
HOUSING_AREA_LOW = 60 * 40 - (4 - math.pi) * 9  # below the pocket: the full block section
SHAFT_HALF = [(0, 0), (10, 0), (10, 13), (8, 13), (8, 17), (10, 17), (10, 40), (6, 50), (6, 70), (0, 70)]


def _shoelace(points) -> float:
    values = np.asarray(points, dtype=float)
    x, y = values[:, 0], values[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def _composition_with(part_name: str):
    from openretop.benchmarks import make_part, scan_from_part

    scan = scan_from_part(make_part(part_name), noise_sigma=0.02, seed=1, edge_length=0.8)
    composition = create_application(settings_repository=InMemorySettingsRepository(), kernel_worker=KernelWorker(inline=True))
    mesh = TriangleMeshData(vertices=np.asarray(scan.vertices, dtype=float), triangles=np.asarray(scan.triangles, dtype=int))
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
    return composition


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class SectionSketchTests(unittest.TestCase):
    def dispatch(self, composition, action: str, payload: dict | None = None):
        result = composition.workflow.dispatch(action, payload or {})
        self.assertTrue(result.success, (action, result.errors))
        return result

    def test_housing_section_becomes_one_face_with_the_pocket_as_its_hole(self) -> None:
        composition = _composition_with("housing")
        modeling = composition.modeling_controller
        self.dispatch(composition, "model.section_sketch")
        session = modeling.session
        self.assertEqual((session.tool, session.section_plane), ("section", "XY"))
        self.assertAlmostEqual(session.section_offset, 0.0, delta=0.05)  # the scan's middle
        self.dispatch(composition, "model.section_fit")
        self.assertEqual(len(session.section_loops), 2)
        self.assertEqual([len(profile.segments) for profile in session.section_profiles], [8, 8])
        self.dispatch(composition, "model.section_create")
        (entity,) = composition.state.model.entities
        self.assertEqual((entity.kind, entity.label, entity.tool), ("profile", "Sketch", "section"))
        self.assertAlmostEqual(entity.stats["area"], HOUSING_AREA_Z0, delta=1.0)
        self.assertEqual(len(entity.edges), 16)
        self.assertLessEqual(entity.stats["max_error"], 0.1)
        self.assertEqual(entity.params["plane"], "XY")
        json.dumps(entity.params)  # plain data: goes into the project file as it is

        composition.workflow.dispatch("edit.undo", {})
        self.assertEqual(composition.state.model.entities, [])
        composition.workflow.dispatch("edit.redo", {})
        self.assertEqual(len(composition.state.model.entities), 1)

    def test_clicking_the_scan_moves_the_plane_and_recuts(self) -> None:
        composition = _composition_with("housing")
        modeling = composition.modeling_controller
        self.dispatch(composition, "model.section_sketch")
        result = modeling.section_place(np.array([5.0, 3.0, -6.0]))  # below the pocket's floor
        self.assertTrue(result.success)
        self.assertAlmostEqual(modeling.session.section_offset, -6.0)
        self.assertEqual(len(modeling.session.section_loops), 1)
        self.dispatch(composition, "model.section_create")
        self.assertAlmostEqual(composition.state.model.entities[0].stats["area"], HOUSING_AREA_LOW, delta=1.0)
        # a plane past the part cuts nothing, and says so
        modeling.section_set_plane("XY", offset=40.0)
        self.assertEqual(modeling.session.section_loops, [])
        self.assertFalse(composition.workflow.dispatch("model.section_fit", {}).success)

    def test_shaft_side_section_is_its_exact_profile(self) -> None:
        composition = _composition_with("shaft")
        modeling = composition.modeling_controller
        self.dispatch(composition, "model.section_sketch")
        self.dispatch(composition, "model.section_plane", {"plane": "XZ", "offset": 0.0})
        self.dispatch(composition, "model.section_fit")
        (profile,) = modeling.session.section_profiles
        self.assertEqual([segment.kind for segment in profile.segments], ["line"] * 16)
        self.dispatch(composition, "model.section_create")
        entity = composition.state.model.entities[0]
        self.assertAlmostEqual(entity.stats["area"], 2 * _shoelace(SHAFT_HALF), delta=1.5)
        # the sketch lies in the XZ plane at y = 0
        points = np.vstack(entity.edges)
        self.assertLess(float(np.abs(points[:, 1]).max()), 1e-9)

    def test_tolerance_change_drops_the_fitted_profile(self) -> None:
        composition = _composition_with("housing")
        modeling = composition.modeling_controller
        self.dispatch(composition, "model.section_sketch")
        self.dispatch(composition, "model.section_fit")
        self.assertIsNotNone(modeling.session.section_profiles)
        self.assertTrue(modeling.configure(section_tolerance=0.1).success)
        self.assertIsNone(modeling.session.section_profiles)


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class SectionSketchWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_from_the_toolbar_to_a_sketch_in_the_tree(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QToolBar

        from openretop.presentation.qt.main_window import OpenRetopV3Window

        composition = _composition_with("housing")
        window = OpenRetopV3Window(composition)
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        window.refresh()
        surfacing = window.findChild(QToolBar, "toolbar_Surfacing")
        action = window._qt_actions["model.section_sketch"]
        self.assertIn(action, surfacing.actions())
        action.trigger()
        panel = window.surfacing_panel
        self.assertEqual(panel.title.text(), "Section Sketch")
        self.assertTrue(panel.plane_buttons["XY"].isChecked())
        self.assertIn("2 section loop(s)", panel.section_info.text())
        snapshot = window.viewport.last_snapshot or window.viewport._pending_snapshot
        ids = {item.id for item in snapshot.model_edges}
        self.assertIn("section-scan", ids)
        self.assertIn("section-plane", ids)

        panel.section_fit.click()
        self.assertIn("4 lines, 4 arcs", panel.section_info.text())
        snapshot = window.viewport.last_snapshot or window.viewport._pending_snapshot
        self.assertIn("section-profile", {item.id for item in snapshot.model_edges})

        panel.plane_buttons["YZ"].click()  # another plane: recut through the middle
        self.assertEqual(composition.modeling_controller.session.section_plane, "YZ")
        self.assertIsNone(composition.modeling_controller.session.section_profiles)
        panel.plane_buttons["XY"].click()

        window._handle_tool_key(Qt.Key.Key_Return)  # Enter creates
        model = composition.state.model
        self.assertEqual([entity.kind for entity in model.entities], ["profile"])
        self.assertIn("model:" + model.entities[0].id, set(window._scene_model.nodes))


if __name__ == "__main__":
    unittest.main()
