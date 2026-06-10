from __future__ import annotations

import sys
import threading
import time
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

    def copy(self) -> FakeMesh:
        copied = FakeMesh()
        copied.vertices = list(self.vertices)
        copied.triangles = list(self.triangles)
        return copied

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

    def translate(self, offset: list[float]) -> None:
        points = np.asarray(self.vertices, dtype=float) + np.asarray(offset, dtype=float)
        self.vertices = [tuple(point) for point in points]

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
        self.selection_callback = None
        self.pointer_callback = None

    def start(self) -> None:
        return None

    def set_selection_callback(self, callback: object) -> None:
        self.selection_callback = callback

    def set_pointer_callback(self, callback: object) -> None:
        self.pointer_callback = callback

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


def _active_workspace(window: OpenRetopWindow) -> str:
    return window.active_workspace.get()


class MainWindowUiTests(unittest.TestCase):
    def test_menu_bar_and_initial_no_selection_context_match_instructions(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            self.assertEqual(window.menu_bar.entrycget(0, "label"), "File")
            self.assertEqual(window.menu_bar.entrycget(1, "label"), "Edit")
            self.assertEqual(window.menu_bar.entrycget(2, "label"), "View")
            self.assertEqual(window.menu_bar.entrycget(3, "label"), "Help")
            self.assertEqual(window.file_menu.entrycget(0, "label"), "New Project")
            self.assertEqual(window.file_menu.entrycget(1, "label"), "Open Model")
            self.assertEqual(window.file_menu.entrycget(3, "label"), "Open Project")
            self.assertEqual(window.file_menu.entrycget(4, "label"), "Save Project")
            self.assertEqual(window.file_menu.entrycget(5, "label"), "Save Project As")
            self.assertEqual(window.file_menu.entrycget(7, "label"), "Exit")
            self.assertEqual(window.edit_menu.entrycget(0, "label"), "Undo")
            self.assertEqual(window.edit_menu.entrycget(1, "label"), "Redo")
            self.assertEqual(window.edit_menu.entrycget(3, "label"), "Preferences")
            self.assertEqual(window.view_menu.entrycget(0, "label"), "Frame All")
            self.assertEqual(window.view_menu.entrycget(1, "label"), "Frame Selected")
            self.assertEqual(window.view_menu.entrycget(2, "label"), "Reset View")
            self.assertEqual(window.view_menu.entrycget(4, "label"), "Show Grid")
            self.assertEqual(window.view_menu.entrycget(5, "label"), "Show Axes")
            self.assertEqual(window.view_menu.type(4), "checkbutton")
            self.assertEqual(window.view_menu.type(5), "checkbutton")
            self.assertEqual(window.help_menu.entrycget(0, "label"), "About")
            self.assertEqual(window.toolbar_select_button.cget("text"), "Select")
            self.assertEqual(window.toolbar_move_button.cget("text"), "Move")
            self.assertEqual(window.toolbar_rotate_button.cget("text"), "Rotate")
            self.assertEqual(window.toolbar_frame_button.cget("text"), "Frame")
            self.assertEqual(window.toolbar_section_button.cget("text"), "Section Plane")
            self.assertFalse(hasattr(window, "toolbar_compute_section_button"))
            self.assertEqual(
                [window.inspector_tabs.tab(index, "text") for index in range(2)],
                ["Scene", "Properties"],
            )
            self.assertEqual(
                tuple(window.workspace_buttons),
                ("View", "Align", "Section", "Curve", "Surface", "Export"),
            )

            self.assertTrue(window.show_grid.get())
            self.assertTrue(window.show_axes.get())
            self.assertFalse(window.show_normals.get())
            self.assertTrue(window.show_section_plane.get())
            self.assertEqual(window.proxy_quality.get(), "Medium")
            self.assertEqual(tuple(window.proxy_quality_dropdown.cget("values")), ("Low", "Medium", "High"))
            self.assertEqual(_active_workspace(window), "View")
            self.assertEqual(window.active_workspace.get(), "View")
            self.assertIn("Selected: None", window.status_text.get())
            self.assertIn("Workspace: View", window.status_text.get())
            self.assertIn("Tool: Select", window.status_text.get())
            self.assertIsNone(window.selected_item)
            self.assertEqual(str(window.workspace_buttons["Curve"].cget("state")), "disabled")
            self.assertEqual(str(window.workspace_buttons["Surface"].cget("state")), "disabled")
            self.assertEqual(str(window.workspace_buttons["Export"].cget("state")), "disabled")
            self.assertEqual(window.active_properties_context.get(), "global")
            self.assertFalse(hasattr(window, "apply_transform_button"))
            self.assertEqual(str(window.select_section_plane_button.cget("state")), "disabled")
            self.assertEqual(str(window.toolbar_move_button.cget("state")), "disabled")
            self.assertEqual(str(window.toolbar_rotate_button.cget("state")), "disabled")
            self.assertEqual(str(window.toolbar_section_button.cget("state")), "disabled")
            self.assertEqual(str(window.compute_section_button.cget("state")), "disabled")
            self.assertEqual(window.compute_section_button.cget("text"), "Compute Section")
            self.assertEqual(window.clear_section_button.cget("text"), "Clear Section")
            self.assertEqual(window.section_plane_text.get(), "Section: Z = 0.000")
            self.assertEqual(window.section_result_text.get(), "Section result: none")
            self.assertEqual(window.scale_value.get(), "1.000")
        finally:
            window.root.destroy()

    def test_loading_mesh_starts_with_scene_context_and_keeps_normals_off(self) -> None:
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

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"), background=False)

            self.assertEqual(window.file_name_text.get(), "sample.stl")
            self.assertEqual(window.vertex_count_text.get(), "3")
            self.assertEqual(window.triangle_count_text.get(), "1")
            self.assertEqual(window.bbox_size_text.get(), "1, 2, 3")
            self.assertIn("Selected: None", window.status_text.get())
            self.assertIn("Workspace: View", window.status_text.get())
            self.assertIn("Proxy: 1 / 1 tris", window.status_text.get())
            self.assertIn("Source: 1 tris", window.status_text.get())
            self.assertIsNone(window.selected_item)
            self.assertEqual(_active_workspace(window), "View")
            self.assertEqual(str(window.select_section_plane_button.cget("state")), "normal")
            self.assertEqual(str(window.toolbar_move_button.cget("state")), "normal")
            self.assertEqual(str(window.toolbar_rotate_button.cget("state")), "normal")
            self.assertEqual(str(window.toolbar_section_button.cget("state")), "normal")
            self.assertEqual(str(window.compute_section_button.cget("state")), "normal")
            self.assertIsNone(window.loading_window)
            self.assertEqual(str(window.open_model_button.cget("state")), "normal")
            self.assertTrue(window.show_grid.get())
            self.assertTrue(window.show_axes.get())
            self.assertTrue(window.show_section_plane.get())
            self.assertFalse(window.show_normals.get())
            self.assertEqual(window.triangle_count_text.get(), "1")
            self.assertEqual(window.display_triangle_count_text.get(), "1")
            self.assertEqual(window.display_reduction_text.get(), "0.0%")
            self.assertEqual(window.display_proxy_text.get(), "Disabled (Medium)")
            self.assertEqual(window.source_retained_text.get(), "Full-resolution source preserved")
            scene = window.viewport.scene_calls[-1]
            self.assertEqual(scene["show_grid"], True)
            self.assertEqual(scene["show_axes"], True)
            self.assertEqual(scene["show_normals"], False)
            self.assertEqual(scene["show_section_plane"], True)
            self.assertEqual(scene["section_axis"], "Z")
            self.assertEqual(scene["section_offset"], 0.0)
            self.assertIsNone(scene["selected_item"])
            self.assertEqual(window.active_properties_context.get(), "global")
            self.assertTrue(np.allclose(scene["scene_bounds_min"], [0.0, 0.0, 0.0]))
            self.assertTrue(np.allclose(scene["scene_bounds_max"], [1.0, 2.0, 3.0]))
            self.assertTrue(window.scene_tree.exists("tree_loaded_mesh"))
            self.assertEqual(window.scene_tree.item("tree_loaded_mesh", "text"), "sample.stl")
            self.assertTrue(window.scene_tree.exists("tree_section_plane"))
        finally:
            window.root.destroy()

    def test_background_loading_shows_progress_and_disables_open_model(self) -> None:
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
        release_load = threading.Event()

        def slow_load(_path: Path) -> LoadedMesh:
            release_load.wait(timeout=2.0)
            return LoadedMesh(mesh=mesh, metadata=metadata)

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch("app.main_window.load_mesh", side_effect=slow_load):
                window.load_model(Path("sample.stl"))
                window.root.update()

                self.assertTrue(window.is_loading)
                self.assertIsNotNone(window.loading_window)
                self.assertEqual(window.loading_file_text.get(), "sample.stl")
                self.assertIn("Loading mesh file", window.status_text.get())
                self.assertEqual(str(window.open_model_button.cget("state")), "disabled")

                release_load.set()
                for _index in range(100):
                    window.root.update()
                    if not window.is_loading:
                        break
                    time.sleep(0.01)

            self.assertFalse(window.is_loading)
            self.assertIsNone(window.loading_window)
            self.assertEqual(str(window.open_model_button.cget("state")), "normal")
            self.assertEqual(window.file_name_text.get(), "sample.stl")
        finally:
            release_load.set()
            window.root.destroy()

    def test_selecting_model_shows_object_context_and_live_transform(self) -> None:
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

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"), background=False)

            window.select_model()
            self.assertEqual(window.selected_item, "model")
            self.assertIn("Selected: sample.stl", window.status_text.get())
            self.assertEqual(_active_workspace(window), "View")
            self.assertEqual(window.active_properties_context.get(), "mesh")
            self.assertEqual(window.selected_object_text.get(), "sample.stl")
            self.assertEqual(window.viewport.scene_calls[-1]["selected_item"], "model")
            self.assertIsNotNone(window.viewport.scene_calls[-1]["object_origin"])
            self.assertEqual(window.scene_tree.selection(), ("tree_loaded_mesh",))

            window._set_workspace("Section")
            window.activate_move_tool()
            self.assertEqual(_active_workspace(window), "Section")
            self.assertEqual(window.active_tool.get(), "Move")
            window._handle_shortcut("Escape")
            window.activate_rotate_tool()
            self.assertEqual(_active_workspace(window), "Section")
            self.assertEqual(window.active_tool.get(), "Rotate")
            window._handle_shortcut("Escape")

            window.location_x.set("1.500")
            window._on_object_transform_changed()
            self.assertIn("Transforms update live", window.status_text.get())
            self.assertAlmostEqual(window.mesh_object.location[0], 1.5)
            self.assertIsNotNone(window.mesh_object.transform_matrix)
            self.assertEqual(window.viewport.scene_calls[-1]["mesh"], window.mesh_object.display_mesh)
            self.assertIsNotNone(window.viewport.scene_calls[-1]["transform_matrix"])

            window.rotation_z.set("90.000")
            window._on_object_transform_changed()
            mapped_origin = window._current_object_matrix() @ np.append(
                window.mesh_object.origin,
                1.0,
            )
            self.assertTrue(np.allclose(mapped_origin[:3], window.mesh_object.location))

            window.frame_selected()
            self.assertEqual(window.viewport.frame_count, 1)
            self.assertIn("Selected: sample.stl", window.status_text.get())
        finally:
            window.root.destroy()

    def test_hotkey_move_cancel_and_confirm_update_mesh_location(self) -> None:
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

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            self.assertIsNotNone(window.viewport.selection_callback)
            self.assertIsNotNone(window.viewport.pointer_callback)
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"), background=False)

            window.select_model()
            start_location = window.mesh_object.location.copy()
            window._on_viewport_pointer_event("motion", 10, 10)
            window._handle_shortcut("G")
            self.assertIn("Move mode - press X/Y/Z", window.status_text.get())
            self.assertEqual(window.viewport.scene_calls[-1]["active_transform_mode"], "move")
            self.assertIn("Transform: Move free", window.status_text.get())

            window._handle_shortcut("X")
            self.assertIn("Move mode - X axis", window.status_text.get())
            self.assertEqual(window.viewport.scene_calls[-1]["active_transform_axis"], "X")
            window._handle_shortcut("X")
            self.assertIn("Move mode - press X/Y/Z", window.status_text.get())
            self.assertIsNone(window.viewport.scene_calls[-1]["active_transform_axis"])
            window._handle_shortcut("X")

            with patch("app.main_window.MeshState.from_mesh") as from_mesh:
                handled = window._on_viewport_pointer_event("motion", 80, 10)
                from_mesh.assert_not_called()
            self.assertTrue(handled)
            moved_location = window.mesh_object.location.copy()
            self.assertGreater(moved_location[0], start_location[0])
            self.assertAlmostEqual(moved_location[1], start_location[1])
            self.assertAlmostEqual(moved_location[2], start_location[2])
            self.assertIn("Delta X:", window.status_text.get())
            self.assertEqual(window.location_x.get(), f"{moved_location[0]:.3f}")

            window._handle_shortcut("Escape")
            self.assertIn("Transform cancelled", window.status_text.get())
            self.assertTrue(np.allclose(window.mesh_object.location, start_location))
            self.assertEqual(window.location_x.get(), f"{start_location[0]:.3f}")
            self.assertIsNone(window.viewport.scene_calls[-1]["active_transform_mode"])

            window._on_viewport_pointer_event("motion", 0, 0)
            window._handle_shortcut("G")
            window._handle_shortcut("X")
            window._on_viewport_pointer_event("motion", 100, 0)
            normal_location = window.mesh_object.location.copy()
            window._handle_shortcut("Escape")

            window._on_viewport_pointer_event("motion", 0, 0)
            window._handle_shortcut("G")
            window._handle_shortcut("X")
            window._on_viewport_pointer_event("motion", 100, 0, shift_pressed=True)
            fine_location = window.mesh_object.location.copy()
            normal_delta = normal_location[0] - start_location[0]
            fine_delta = fine_location[0] - start_location[0]
            self.assertAlmostEqual(fine_delta, normal_delta * 0.1, places=6)
            window._handle_shortcut("Escape")

            window._handle_shortcut("G")
            window._on_viewport_pointer_event("motion", 150, 10)
            confirmed_location = window.mesh_object.location.copy()
            window._handle_shortcut("Enter")
            self.assertIn("Transform confirmed", window.status_text.get())
            self.assertTrue(np.allclose(window.mesh_object.location, confirmed_location))
            self.assertGreater(confirmed_location[0], start_location[0])
        finally:
            window.root.destroy()

    def test_hotkey_rotate_axis_constraint_updates_mesh_rotation_about_pivot(self) -> None:
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

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"), background=False)

            window.select_model()
            window._on_viewport_pointer_event("motion", 0, 0)
            window._handle_shortcut("R")
            self.assertIn("Rotate mode - Z axis - move mouse horizontally", window.status_text.get())
            self.assertEqual(window.viewport.scene_calls[-1]["active_transform_mode"], "rotate")
            self.assertEqual(window.viewport.scene_calls[-1]["active_transform_axis"], "Z")
            window._handle_shortcut("X")
            self.assertIn("Rotate mode - X axis - move mouse horizontally", window.status_text.get())
            self.assertEqual(window.viewport.scene_calls[-1]["active_transform_axis"], "X")

            window._on_viewport_pointer_event("motion", 40, 0)
            self.assertGreater(window.mesh_object.rotation[0], 0.0)
            self.assertIn("20.0 deg", window.status_text.get())
            self.assertEqual(window.rotation_x.get(), f"{window.mesh_object.rotation[0]:.3f}")
            self.assertEqual(window.rotation_y.get(), "0.000")
            self.assertEqual(window.rotation_z.get(), "0.000")

            mapped_origin = window._current_object_matrix() @ np.append(
                window.mesh_object.origin,
                1.0,
            )
            self.assertTrue(np.allclose(mapped_origin[:3], window.mesh_object.location))
        finally:
            window.root.destroy()

    def test_selecting_section_plane_shows_section_context_and_compute_clear(self) -> None:
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

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"), background=False)

            window.select_section_plane()
            self.assertEqual(window.selected_item, "section_plane")
            self.assertIn("Selected: Section Plane", window.status_text.get())
            self.assertEqual(_active_workspace(window), "View")
            self.assertEqual(window.active_properties_context.get(), "section")
            self.assertEqual(window.viewport.scene_calls[-1]["selected_item"], "section_plane")
            self.assertEqual(window.scene_tree.selection(), ("tree_section_plane",))

            window._set_section_offset(0.5, clamp=True, refresh=True)
            self.assertEqual(window.section_plane_text.get(), "Section: Z = 0.500")
            self.assertIn("Section plane: Z = 0.500", window.status_text.get())
            self.assertEqual(window.viewport.scene_calls[-1]["section_offset"], 0.5)

            window.reset_view()
            self.assertEqual(window.viewport.reset_count, 1)
            self.assertIn("View reset", window.status_text.get())

            window.compute_section()
            self.assertIn("Section computed: 1 segments", window.status_text.get())
            self.assertEqual(window.section_result_text.get(), "Section result: 1 segments")
            self.assertTrue(window.scene_tree.exists("tree_section_result"))

            window.clear_section()
            self.assertIn("Section cleared", window.status_text.get())
            self.assertEqual(window.section_result_text.get(), "Section result: none")
            self.assertFalse(window.scene_tree.exists("tree_section_result"))
            self.assertIsNone(window.viewport.scene_calls[-1]["section_result"])
            self.assertEqual(window.viewport.scene_calls[-1]["show_section_plane"], True)
        finally:
            window.root.destroy()

    def test_section_plane_hotkey_move_cancel_confirm_and_rotate_cycle(self) -> None:
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

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"), background=False)

            window.select_section_plane()
            start_offset = window.section_offset.get()
            window._on_viewport_pointer_event("motion", 0, 0)
            window._handle_shortcut("G")
            self.assertIn("Move mode - Z axis", window.status_text.get())
            window._on_viewport_pointer_event("motion", 50, 0)
            moved_offset = window.section_offset.get()
            self.assertGreater(moved_offset, start_offset)
            self.assertEqual(window.section_offset_text.get(), f"{moved_offset:.3f}")
            self.assertIn("Offset Z:", window.status_text.get())

            handled = window._on_viewport_pointer_event("right_release", 50, 0)
            self.assertTrue(handled)
            self.assertIn("Transform cancelled", window.status_text.get())
            self.assertAlmostEqual(window.section_offset.get(), start_offset)

            window._handle_shortcut("G")
            window._handle_shortcut("X")
            self.assertEqual(window.section_axis.get(), "X")
            self.assertIn("Move mode - X axis", window.status_text.get())
            window._on_viewport_pointer_event("motion", 100, 0)
            confirmed_offset = window.section_offset.get()
            handled = window._on_viewport_pointer_event("left_release", 100, 0)
            self.assertTrue(handled)
            self.assertIn("Transform confirmed", window.status_text.get())
            self.assertAlmostEqual(window.section_offset.get(), confirmed_offset)
            self.assertGreater(confirmed_offset, start_offset)

            self.assertEqual(window.section_axis.get(), "X")
            window._handle_shortcut("R")
            self.assertEqual(window.section_axis.get(), "Y")
            self.assertIn("Section plane axis cycled to Y", window.status_text.get())
        finally:
            window.root.destroy()


if __name__ == "__main__":
    unittest.main()

