from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tkinter import TclError
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.main_window import OpenRetopWindow
from mesh.loader import LoadedMesh, MeshMetadata


class FakeBounds:
    def __init__(
        self,
        minimum: tuple[float, float, float],
        maximum: tuple[float, float, float],
    ) -> None:
        self.minimum = minimum
        self.maximum = maximum

    def get_min_bound(self) -> tuple[float, float, float]:
        return self.minimum

    def get_max_bound(self) -> tuple[float, float, float]:
        return self.maximum

    def get_extent(self) -> tuple[float, float, float]:
        return tuple(maximum - minimum for minimum, maximum in zip(self.minimum, self.maximum))

    def get_max_extent(self) -> float:
        return max(self.get_extent())

    def get_center(self) -> tuple[float, float, float]:
        return tuple((minimum + maximum) * 0.5 for minimum, maximum in zip(self.minimum, self.maximum))


class FakeMesh:
    def __init__(self) -> None:
        self.vertices = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 2.0, 3.0)]
        self.triangles = [(0, 1, 2)]

    def get_axis_aligned_bounding_box(self) -> FakeBounds:
        points = np.asarray(self.vertices, dtype=float)
        return FakeBounds(tuple(points.min(axis=0)), tuple(points.max(axis=0)))

    def has_vertex_normals(self) -> bool:
        return True

    def has_triangle_normals(self) -> bool:
        return True

    def has_vertex_colors(self) -> bool:
        return False

    def paint_uniform_color(self, _color: list[float]) -> None:
        return None

    def transform(self, matrix: np.ndarray) -> None:
        points = np.asarray(self.vertices, dtype=float)
        homogeneous = np.column_stack((points, np.ones(len(points))))
        transformed = (np.asarray(matrix, dtype=float) @ homogeneous.T).T[:, :3]
        self.vertices = [tuple(point) for point in transformed]

    def compute_vertex_normals(self) -> None:
        return None

    def compute_triangle_normals(self) -> None:
        return None


class FakeViewport:
    def __init__(self, _parent: object) -> None:
        self.scene_calls: list[dict[str, object]] = []
        self.frame_count = 0
        self.reset_count = 0
        self.closed = False

    def start(self) -> None:
        return None

    def set_scene(self, mesh: object, **kwargs: object) -> None:
        self.scene_calls.append({"mesh": mesh, **kwargs})

    def frame_model(self) -> None:
        self.frame_count += 1

    def reset_view(self) -> None:
        self.reset_count += 1

    def reset_camera(self) -> None:
        self.reset_count += 1

    def close(self) -> None:
        self.closed = True


def _create_window() -> OpenRetopWindow:
    try:
        window = OpenRetopWindow()
    except TclError as exc:
        raise unittest.SkipTest(f"Tk is unavailable: {exc}") from exc

    window.root.update_idletasks()
    return window


class MainWindowUiTests(unittest.TestCase):
    def test_menu_bar_and_initial_sidebar_state_match_instructions(self) -> None:
        with patch("app.main_window.EmbeddedOpen3DViewport", FakeViewport):
            window = _create_window()

        try:
            self.assertEqual(window.menu_bar.entrycget(0, "label"), "File")
            self.assertEqual(window.menu_bar.entrycget(1, "label"), "View")
            self.assertEqual(window.file_menu.entrycget(0, "label"), "Open Model")
            self.assertEqual(window.file_menu.entrycget(2, "label"), "Exit")
            self.assertEqual(window.view_menu.entrycget(0, "label"), "Show Grid")
            self.assertEqual(window.view_menu.entrycget(1, "label"), "Show Axes")
            self.assertEqual(window.view_menu.entrycget(2, "label"), "Show Normals")
            self.assertEqual(window.view_menu.entrycget(4, "label"), "Frame Model")
            self.assertEqual(window.view_menu.entrycget(5, "label"), "Reset View")
            self.assertEqual(window.view_menu.type(0), "checkbutton")
            self.assertEqual(window.view_menu.type(1), "checkbutton")
            self.assertEqual(window.view_menu.type(2), "checkbutton")

            self.assertTrue(window.show_grid.get())
            self.assertTrue(window.show_axes.get())
            self.assertFalse(window.show_normals.get())
            self.assertTrue(window.show_section_plane.get())
            self.assertEqual(window.status_text.get(), "No model loaded")
            self.assertEqual(str(window.axis_dropdown.cget("state")), "disabled")
            self.assertEqual(str(window.offset_input.cget("state")), "disabled")
            self.assertEqual(str(window.compute_section_button.cget("state")), "disabled")
            self.assertEqual(str(window.clear_section_button.cget("state")), "disabled")
            self.assertEqual(str(window.apply_transform_button.cget("state")), "disabled")
            self.assertEqual(window.compute_section_button.cget("text"), "Compute Section")
            self.assertEqual(window.clear_section_button.cget("text"), "Clear Section")
            self.assertEqual(window.section_plane_text.get(), "Section: Z = 0.000")
            self.assertEqual(window.section_result_text.get(), "Section result: none")
            self.assertEqual(window.scale_value.get(), "1.000")
        finally:
            window.root.destroy()

    def test_loading_mesh_updates_workspace_controls_and_keeps_normals_off(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedOpen3DViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            self.assertEqual(window.file_name_text.get(), "sample.stl")
            self.assertEqual(window.vertex_count_text.get(), "3")
            self.assertEqual(window.triangle_count_text.get(), "1")
            self.assertEqual(window.bbox_size_text.get(), "1, 2, 3")
            self.assertEqual(window.status_text.get(), "Loaded: sample.stl")
            self.assertEqual(str(window.axis_dropdown.cget("state")), "readonly")
            self.assertEqual(str(window.offset_input.cget("state")), "normal")
            self.assertEqual(str(window.compute_section_button.cget("state")), "normal")
            self.assertEqual(str(window.clear_section_button.cget("state")), "normal")
            self.assertEqual(str(window.apply_transform_button.cget("state")), "normal")
            self.assertTrue(window.show_grid.get())
            self.assertTrue(window.show_axes.get())
            self.assertTrue(window.show_section_plane.get())
            self.assertFalse(window.show_normals.get())
            scene = window.viewport.scene_calls[-1]
            self.assertEqual(scene["show_grid"], True)
            self.assertEqual(scene["show_axes"], True)
            self.assertEqual(scene["show_normals"], False)
            self.assertEqual(scene["show_section_plane"], True)
            self.assertEqual(scene["section_axis"], "Z")
            self.assertEqual(scene["section_offset"], 0.0)
        finally:
            window.root.destroy()

    def test_frame_reset_compute_and_clear_use_new_workspace_controls(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedOpen3DViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            window.frame_model()
            self.assertEqual(window.viewport.frame_count, 1)
            self.assertEqual(window.status_text.get(), "View framed")

            window.reset_view()
            self.assertEqual(window.viewport.reset_count, 1)
            self.assertEqual(window.status_text.get(), "View reset")

            window.compute_section()
            self.assertEqual(window.status_text.get(), "Section computed: 1 segments")
            self.assertEqual(window.section_result_text.get(), "Section result: 1 segments")

            window.clear_section()
            self.assertEqual(window.status_text.get(), "Section cleared")
            self.assertEqual(window.section_result_text.get(), "Section result: none")
            self.assertIsNone(window.viewport.scene_calls[-1]["section_result"])
            self.assertEqual(window.viewport.scene_calls[-1]["show_section_plane"], True)
        finally:
            window.root.destroy()


if __name__ == "__main__":
    unittest.main()
