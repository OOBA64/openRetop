from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from viewer.embedded_viewport import EmbeddedOpen3DViewport


class FakeBounds:
    def get_min_bound(self) -> tuple[float, float, float]:
        return (0.0, 0.0, 0.0)

    def get_max_bound(self) -> tuple[float, float, float]:
        return (1.0, 2.0, 3.0)

    def get_center(self) -> tuple[float, float, float]:
        return (0.5, 1.0, 1.5)

    def get_max_extent(self) -> float:
        return 3.0


class FakeMesh:
    vertices = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    triangles = [(0, 1, 2)]

    def get_axis_aligned_bounding_box(self) -> FakeBounds:
        return FakeBounds()

    def has_vertex_colors(self) -> bool:
        return True


class FakeViewControl:
    def set_front(self, _front: list[float]) -> None:
        return None

    def set_up(self, _up: list[float]) -> None:
        return None

    def set_lookat(self, _lookat: list[float]) -> None:
        return None

    def set_zoom(self, _zoom: float) -> None:
        return None


class FakeVisualizer:
    def __init__(self) -> None:
        self.added: list[tuple[object, bool]] = []

    def clear_geometries(self) -> None:
        self.added.clear()

    def add_geometry(self, geometry: object, *, reset_bounding_box: bool = True) -> bool:
        self.added.append((geometry, reset_bounding_box))
        return True

    def update_renderer(self) -> None:
        return None

    def get_view_control(self) -> FakeViewControl:
        return FakeViewControl()


def _make_viewport(visualizer: FakeVisualizer) -> EmbeddedOpen3DViewport:
    viewport = object.__new__(EmbeddedOpen3DViewport)
    viewport.visualizer = visualizer
    viewport._is_started = True
    viewport._geometry_names = []
    return viewport


class EmbeddedViewportSceneTests(unittest.TestCase):
    def test_mesh_resets_open3d_bounds_when_camera_is_reset(self) -> None:
        visualizer = FakeVisualizer()
        viewport = _make_viewport(visualizer)
        mesh = FakeMesh()

        viewport.set_scene(
            mesh,
            show_grid=True,
            show_axes=True,
            show_normals=False,
            show_section_plane=False,
            section_axis="Z",
            section_offset=0.0,
            reset_camera=True,
        )

        self.assertIs(visualizer.added[0][0], mesh)
        self.assertTrue(visualizer.added[0][1])
        self.assertTrue(any(geometry is not mesh for geometry, _ in visualizer.added))
        self.assertTrue(all(not reset for _, reset in visualizer.added[1:]))

    def test_mesh_keeps_existing_camera_when_camera_is_not_reset(self) -> None:
        visualizer = FakeVisualizer()
        viewport = _make_viewport(visualizer)
        mesh = FakeMesh()

        viewport.set_scene(
            mesh,
            show_grid=False,
            show_axes=False,
            show_normals=False,
            show_section_plane=False,
            section_axis="Z",
            section_offset=0.0,
            reset_camera=False,
        )

        self.assertIs(visualizer.added[0][0], mesh)
        self.assertFalse(visualizer.added[0][1])


if __name__ == "__main__":
    unittest.main()
