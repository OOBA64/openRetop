"""S-12: model surfaces, bodies and the Surface Sketch are saved in the project and come back."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

try:
    import cadquery  # noqa: F401
    import OCP  # noqa: F401
    import trimesh

    HAVE_KERNEL = True
except ImportError:  # pragma: no cover
    HAVE_KERNEL = False

from openretop.modeling.document import ModelDocument, ModelEntity
from openretop.modeling.persistence import model_from_dict, model_to_dict
from openretop.modeling.sketch import Sketch, SketchCurve


class ModelDictTests(unittest.TestCase):
    def test_round_trip_keeps_geometry_and_sketch(self) -> None:
        document = ModelDocument()
        document.entities.append(
            ModelEntity(
                id="model-1",
                name="Plane 1",
                kind="plane",
                tool="fit_surface",
                brep=b"BREP bytes \x00\x01",
                vertices=np.random.default_rng(0).random((10, 3)),
                triangles=np.array([[0, 1, 2], [2, 3, 4]]),
                edges=[np.zeros((3, 3)), np.ones((5, 3))],
                color=(0.1, 0.2, 0.3),
                visible=False,
                params={"triangles": np.arange(4), "kind": "auto"},
                stats={"rms": np.float64(0.02)},
                sources=("model-0",),
            )
        )
        document.counter = 7
        sketch = Sketch()
        sketch.nodes = {"p1": np.array([1.0, 2.0, 3.0]), "p2": np.array([4.0, 5.0, 6.0])}
        sketch.curves.append(SketchCurve("c3", "Curve 1", ["p1", "p2"], False, np.linspace(0, 1, 30).reshape(10, 3)))
        sketch.counter = 3
        document.sketch = sketch

        data = json.loads(json.dumps(model_to_dict(document)))  # must be plain JSON
        back, warnings = model_from_dict(data)
        self.assertEqual(warnings, [])
        entity = back.entities[0]
        self.assertEqual((entity.id, entity.name, entity.kind, entity.visible), ("model-1", "Plane 1", "plane", False))
        self.assertEqual(entity.brep, b"BREP bytes \x00\x01")
        np.testing.assert_allclose(entity.vertices, document.entities[0].vertices, atol=1e-6)  # stored as float32
        np.testing.assert_array_equal(entity.triangles, [[0, 1, 2], [2, 3, 4]])
        self.assertEqual([len(edge) for edge in entity.edges], [3, 5])
        self.assertEqual(entity.params["triangles"], [0, 1, 2, 3])
        self.assertAlmostEqual(entity.stats["rms"], 0.02)
        self.assertEqual(back.counter, 7)
        self.assertEqual(back.sketch.curves[0].nodes, ["p1", "p2"])
        np.testing.assert_allclose(back.sketch.curves[0].polyline, sketch.curves[0].polyline)
        self.assertEqual(back.sketch.counter, 3)

    def test_an_empty_model_is_not_written_and_bad_data_warns(self) -> None:
        self.assertIsNone(model_to_dict(ModelDocument()))
        back, warnings = model_from_dict({"format": 1, "entities": [{"id": "x"}], "sketch": {}})
        self.assertEqual(back.entities, [])
        self.assertEqual(len(warnings), 1)


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery / trimesh not installed")
class SaveAndReopenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def _window(self):
        from openretop.bootstrap import create_application
        from openretop.cad_kernel.worker import KernelWorker
        from openretop.infrastructure.settings_repository import InMemorySettingsRepository
        from openretop.presentation.qt.main_window import OpenRetopV3Window

        window = OpenRetopV3Window(
            create_application(settings_repository=InMemorySettingsRepository(), kernel_worker=KernelWorker(inline=True))
        )
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        return window

    def test_surfaces_and_sketch_survive_save_and_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mesh_path = Path(directory) / "plate.stl"
            project_path = Path(directory) / "job.openretop"
            trimesh.creation.box(extents=(40.0, 30.0, 10.0)).subdivide().subdivide().export(mesh_path)
            window = self._window()
            self.assertTrue(window.open_model_path(mesh_path, units="mm"))
            modeling = window.composition.modeling_controller
            window._qt_actions["model.fit_surface"].trigger()
            top = int(np.argmax(window.composition.state.mesh_object.display_mesh.vertices[window.composition.state.mesh_object.display_mesh.triangles].mean(axis=1)[:, 2]))
            modeling.select_at(top)
            window._qt_actions["model.fit_create"].trigger()
            window._dispatch_application_action("model.sketch")
            modeling.sketch_click(np.array([-10.0, -5.0, 5.0]))
            modeling.sketch_click(np.array([10.0, 5.0, 5.0]))
            window._handle_tool_key(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.Key.Key_Return)
            saved = window.composition.state.model
            self.assertEqual(len(saved.entities), 1)
            self.assertEqual(len(saved.sketch.curves), 1)
            with patch(
                "openretop.presentation.qt.main_window.QFileDialog.getSaveFileName",
                return_value=(str(project_path), ""),
            ):
                self.assertTrue(window.save_project(as_dialog=True))

            reopened = self._window()
            self.assertTrue(reopened.open_project_path(project_path))
            model = reopened.composition.state.model
            self.assertEqual([entity.name for entity in model.entities], [entity.name for entity in saved.entities])
            self.assertEqual(model.entities[0].brep, saved.entities[0].brep)
            self.assertEqual(len(model.sketch.curves), 1)
            np.testing.assert_allclose(model.sketch.curves[0].polyline, saved.sketch.curves[0].polyline)
            reopened.refresh()
            self.assertIn("model:" + model.entities[0].id, set(reopened._scene_model.nodes))
            # the reopened surface still works with the kernel (export)
            exported = reopened.composition.modeling_controller.export(str(Path(directory) / "out.step"))
            self.assertTrue(exported.success, exported.errors)


if __name__ == "__main__":
    unittest.main()
