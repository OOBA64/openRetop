from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tkinter import TclError
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.main_window import OpenRetopWindow
from mesh.loader import LoadedMesh, MeshMetadata


class FakeBounds:
    def get_min_bound(self) -> tuple[float, float, float]:
        return (0.0, 0.0, 0.0)

    def get_max_bound(self) -> tuple[float, float, float]:
        return (1.0, 2.0, 3.0)

    def get_extent(self) -> tuple[float, float, float]:
        return (1.0, 2.0, 3.0)

    def get_max_extent(self) -> float:
        return 3.0


class FakeMesh:
    vertices = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    triangles = [(0, 1, 2)]

    def get_axis_aligned_bounding_box(self) -> FakeBounds:
        return FakeBounds()

    def has_vertex_normals(self) -> bool:
        return True

    def has_triangle_normals(self) -> bool:
        return True

    def has_vertex_colors(self) -> bool:
        return False

    def paint_uniform_color(self, _color: list[float]) -> None:
        return None


class FakeViewport:
    def __init__(self, _parent: object) -> None:
        self.scene_calls: list[dict[str, object]] = []
        self.reset_count = 0
        self.closed = False

    def start(self) -> None:
        return None

    def set_scene(self, mesh: object, **kwargs: object) -> None:
        self.scene_calls.append({"mesh": mesh, **kwargs})

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
    def test_native_menu_bar_and_initial_sidebar_state_match_instructions(self) -> None:
        with patch("app.main_window.EmbeddedOpen3DViewport", FakeViewport):
            window = _create_window()

        try:
            self.assertEqual(window.menu_bar.entrycget(0, "label"), "File")
            self.assertEqual(window.menu_bar.entrycget(1, "label"), "View")
            self.assertEqual(window.file_menu.entrycget(0, "label"), "Open Model")
            self.assertEqual(window.file_menu.entrycget(2, "label"), "Exit")
            self.assertEqual(window.view_menu.entrycget(0, "label"), "Reset Camera")
            self.assertEqual(window.view_menu.entrycget(1, "label"), "Show Normals")
            self.assertEqual(window.view_menu.type(1), "checkbutton")

            self.assertFalse(window.show_normals.get())
            self.assertEqual(window.status_text.get(), "No model loaded")
            self.assertEqual(str(window.axis_dropdown.cget("state")), "disabled")
            self.assertEqual(str(window.offset_input.cget("state")), "disabled")
            self.assertEqual(str(window.compute_section_button.cget("state")), "disabled")
            self.assertEqual(window.compute_section_button.cget("text"), "Compute Section")
            self.assertEqual(window.section_plane_text.get(), "Section: Z = 0")
        finally:
            window.root.destroy()

    def test_loading_mesh_updates_sidebar_enables_section_and_keeps_normals_off(self) -> None:
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
            self.assertEqual(window.status_text.get(), "Loaded model: sample.stl")
            self.assertEqual(str(window.axis_dropdown.cget("state")), "readonly")
            self.assertEqual(str(window.offset_input.cget("state")), "normal")
            self.assertEqual(str(window.compute_section_button.cget("state")), "normal")
            self.assertFalse(window.show_normals.get())
            self.assertEqual(window.viewport.scene_calls[-1]["show_normals"], False)
        finally:
            window.root.destroy()


if __name__ == "__main__":
    unittest.main()
