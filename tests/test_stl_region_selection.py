"""End-to-end check of the original bug: region selection on an STL picked one triangle."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import trimesh
from PySide6.QtWidgets import QApplication

from openretop.bootstrap import create_application
from openretop.infrastructure.settings_repository import InMemorySettingsRepository
from openretop.presentation.qt.main_window import OpenRetopV3Window


class StlRegionSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _window(self) -> OpenRetopV3Window:
        window = OpenRetopV3Window(create_application(settings_repository=InMemorySettingsRepository()))
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        return window

    def test_every_face_of_an_stl_box_selects_exactly_its_two_triangles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "box.stl"
            trimesh.creation.box(extents=(20.0, 30.0, 40.0)).export(path)
            window = self._window()
            self.assertTrue(window.open_model_path(path, units="mm"))

        state = window.composition.state
        regions = window.composition.region_controller
        mesh = state.mesh_object.display_mesh
        self.assertEqual(len(mesh.triangles), 12)
        self.assertEqual(len(mesh.vertices), 8, "STL corners must be welded or faces cannot connect")

        regions.start()
        covered: set[int] = set()
        for seed in range(12):
            result = regions.select_seed(seed)
            self.assertTrue(result.success, result.status)
            region = state.region_collection.active_region
            self.assertEqual(len(region.triangle_indices), 2, f"seed {seed}: {region.triangle_indices}")
            covered.update(region.triangle_indices)
        self.assertEqual(covered, set(range(12)))

    def test_region_survives_save_and_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mesh_path = Path(directory) / "box.stl"
            project_path = Path(directory) / "job.openretop"
            trimesh.creation.box(extents=(20.0, 30.0, 40.0)).export(mesh_path)

            window = self._window()
            self.assertTrue(window.open_model_path(mesh_path, units="in"))
            window.composition.region_controller.start()
            window.composition.region_controller.select_seed(3)
            selected = tuple(window.composition.state.region_collection.active_region.triangle_indices)
            with patch(
                "openretop.presentation.qt.main_window.QFileDialog.getSaveFileName",
                return_value=(str(project_path), ""),
            ):
                self.assertTrue(window.save_project(as_dialog=True))

            reopened = self._window()
            self.assertTrue(reopened.open_project_path(project_path))

        restored = reopened.composition.state.region_collection.active_region
        self.assertIsNotNone(restored)
        self.assertEqual(tuple(restored.triangle_indices), selected)
        self.assertEqual(len(selected), 2)
        self.assertEqual(reopened.composition.state.units, "in")


if __name__ == "__main__":
    unittest.main()
