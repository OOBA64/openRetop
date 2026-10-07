"""The viewport's look: smooth crease-aware shading, gradient background, studio lights."""

from __future__ import annotations

import unittest

import numpy as np
import trimesh
from vtkmodules.util.numpy_support import vtk_to_numpy

from openretop.presentation.qt.viewport import gradient_top_color, install_studio_lights
from openretop.viewer.mesh_actors import CREASE_ANGLE_DEGREES, shaded_polydata


def _triangle_points(data: object) -> np.ndarray:
    points = vtk_to_numpy(data.GetPoints().GetData())
    polys = data.GetPolys()
    connectivity = vtk_to_numpy(polys.GetConnectivityArray()).reshape(-1, 3)
    return points[connectivity]


class ShadingTests(unittest.TestCase):
    def test_every_triangle_keeps_its_index_so_picks_still_map_to_the_source(self) -> None:
        mesh = trimesh.creation.icosphere(subdivisions=3)
        data = shaded_polydata(mesh.vertices, mesh.faces)
        self.assertEqual(data.GetNumberOfPolys(), len(mesh.faces))
        np.testing.assert_allclose(_triangle_points(data), mesh.vertices[mesh.faces], atol=1e-12)

    def test_a_smooth_scan_gets_one_normal_per_vertex(self) -> None:
        mesh = trimesh.creation.icosphere(subdivisions=3)
        data = shaded_polydata(mesh.vertices, mesh.faces)
        normals = data.GetPointData().GetNormals()
        self.assertIsNotNone(normals)
        self.assertEqual(data.GetNumberOfPoints(), len(mesh.vertices))  # nothing split on a sphere
        # smooth: each vertex normal points outwards like the sphere's own normal
        outward = data.GetPoints()
        for index in range(0, data.GetNumberOfPoints(), 97):
            position = np.asarray(outward.GetPoint(index))
            self.assertGreater(float(np.dot(np.asarray(normals.GetTuple3(index)), position / np.linalg.norm(position))), 0.99)

    def test_machined_edges_stay_sharp(self) -> None:
        box = trimesh.creation.box((10, 10, 10))
        data = shaded_polydata(box.vertices, box.faces)
        normals = vtk_to_numpy(data.GetPointData().GetNormals())
        # every corner is split per face, so each normal is axis-aligned (a flat face), never a
        # diagonal blend that would make the cube look like a pillow
        self.assertGreater(data.GetNumberOfPoints(), len(box.vertices))
        np.testing.assert_allclose(np.sort(np.abs(normals), axis=1)[:, -1], 1.0, atol=1e-6)
        self.assertLess(CREASE_ANGLE_DEGREES, 90.0)

    def test_an_empty_mesh_is_fine(self) -> None:
        data = shaded_polydata(np.zeros((0, 3)), np.zeros((0, 3), dtype=int))
        self.assertEqual(data.GetNumberOfPolys(), 0)


class BackgroundAndLightTests(unittest.TestCase):
    def test_the_gradient_top_is_lighter_than_the_floor(self) -> None:
        bottom = (16 / 255, 19 / 255, 22 / 255)
        top = gradient_top_color(bottom)
        self.assertTrue(all(upper > lower for upper, lower in zip(top, bottom)))
        self.assertLess(max(top), 0.3)  # still a dark view

    def test_studio_lights_replace_the_headlight(self) -> None:
        from vtkmodules.vtkRenderingCore import vtkRenderer

        renderer = vtkRenderer()
        install_studio_lights(renderer)
        self.assertGreaterEqual(renderer.GetLights().GetNumberOfItems(), 3)
        install_studio_lights(renderer)  # idempotent: no doubled lights
        first = renderer.GetLights().GetNumberOfItems()
        install_studio_lights(renderer)
        self.assertEqual(renderer.GetLights().GetNumberOfItems(), first)

    def test_the_viewport_paints_a_gradient_from_the_background_setting(self) -> None:
        from PySide6.QtWidgets import QApplication

        from openretop.presentation.qt.viewport import QtSceneViewport

        QApplication.instance() or QApplication([])
        viewport = QtSceneViewport()
        self.addCleanup(viewport.close)
        color = viewport.set_background("#101316")
        self.assertTrue(bool(viewport.renderer.GetGradientBackground()))
        np.testing.assert_allclose(viewport.renderer.GetBackground(), color)
        np.testing.assert_allclose(viewport.renderer.GetBackground2(), gradient_top_color(color))


if __name__ == "__main__":
    unittest.main()
