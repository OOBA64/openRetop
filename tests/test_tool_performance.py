"""Per-mouse-move cost of the drawing tools.

Drawing a manual curve on a 180k-triangle scan cost 86 ms per mouse move: the whole scan was
copied and re-transformed for every preview (60 ms), every pick tested every triangle
(20 ms), the scan was re-hashed for every snapshot (10 ms) and the panels were rebuilt.
After the fixes it is 7.5 ms. These tests pin each cache.
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

from openretop.bootstrap import create_application
from openretop.infrastructure.settings_repository import InMemorySettingsRepository
from openretop.presentation.qt.main_window import OpenRetopV3Window
from openretop.viewer import scene_builder


def _window(test: unittest.TestCase) -> OpenRetopV3Window:
    window = OpenRetopV3Window(create_application(settings_repository=InMemorySettingsRepository()))
    test.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
    window.resize(900, 650)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "ball.stl"
        trimesh.creation.icosphere(subdivisions=4, radius=20).export(path)
        window.open_model_path(path, units="mm")
    with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
        window.viewport._is_ready = True
        window.viewport.ready.emit()
    return window


class TransformedMeshCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_the_world_space_scan_is_built_once_until_the_object_moves(self) -> None:
        window = _window(self)
        transform = window.composition.transform_controller
        first = transform.transformed_source_mesh()
        self.assertIs(transform.transformed_source_mesh(), first)
        window.composition.state.mesh_object.location = np.array([5.0, 0.0, 0.0])
        transform._apply_object_transform()
        moved = transform.transformed_source_mesh()
        self.assertIsNot(moved, first)
        np.testing.assert_allclose(moved.vertices.mean(axis=0), first.vertices.mean(axis=0) + [5.0, 0.0, 0.0], atol=1e-9)

    def test_the_shared_mesh_cannot_be_modified_by_a_caller(self) -> None:
        window = _window(self)
        mesh = window.composition.transform_controller.transformed_source_mesh()
        with self.assertRaises(ValueError):
            mesh.vertices[0, 0] = 99.0


class PickingIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_picks_reuse_one_spatial_index_and_still_hit_the_right_triangle(self) -> None:
        window = _window(self)
        viewport = window.viewport
        viewport.render_window.SetSize(900, 650)
        viewport.renderer.ResetCamera()
        picking = viewport.picking
        width, height = viewport.render_window.GetSize()
        hits = [picking.pick_mesh(width // 2 + dx, height // 2) for dx in (-20, 0, 20)]
        self.assertTrue(all(hit.hit for hit in hits))
        self.assertEqual(picking.locator_build_count, 1)
        # the triangle reported is the one under the hit point
        mesh = window.composition.transform_controller.transformed_source_mesh()
        for hit in hits:
            corners = mesh.vertices[mesh.triangles[hit.triangle_index]]
            self.assertLess(np.linalg.norm(corners.mean(axis=0) - hit.position), 3.0)


class MeshRevisionCacheTests(unittest.TestCase):
    def test_the_scan_is_hashed_once_per_geometry(self) -> None:
        vertices = np.random.default_rng(1).random((1000, 3))
        triangles = np.arange(999 * 3).reshape(-1, 3) % 1000
        with patch.object(scene_builder, "geometry_revision", wraps=scene_builder.geometry_revision) as hashed:
            first = scene_builder._mesh_revision(vertices, triangles)
            self.assertEqual(scene_builder._mesh_revision(vertices, triangles), first)
            self.assertEqual(hashed.call_count, 1)
            moved = vertices + 1.0  # translate assigns a new array
            self.assertNotEqual(scene_builder._mesh_revision(moved, triangles), first)
            self.assertEqual(hashed.call_count, 2)


if __name__ == "__main__":
    unittest.main()
