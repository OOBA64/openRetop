from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tkinter import TclError, Tk
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.main_window import (
    LOAD_PROGRESS_STAGES,
    LoadProgressDialog,
    OPEN_MODEL_MENU_INDEX,
    OpenRetopWindow,
)
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
    if window._start_viewport_after_id is not None:
        window.root.after_cancel(window._start_viewport_after_id)
        window._start_viewport_after_id = None
    return window


def _widget_descendants(widget: object) -> list[object]:
    descendants: list[object] = []
    for child in widget.winfo_children():
        descendants.append(child)
        descendants.extend(_widget_descendants(child))
    return descendants


class MainWindowUiTests(unittest.TestCase):
    def test_menu_bar_and_initial_no_selection_context_match_instructions(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            self.assertEqual(window.menu_bar.entrycget(0, "label"), "File")
            self.assertEqual(window.menu_bar.entrycget(1, "label"), "View")
            self.assertEqual(window.file_menu.entrycget(0, "label"), "Open Model")
            self.assertEqual(window.file_menu.entrycget(2, "label"), "Exit")
            self.assertEqual(window.view_menu.entrycget(0, "label"), "Show Grid")
            self.assertEqual(window.view_menu.entrycget(1, "label"), "Show Axes")
            self.assertEqual(window.view_menu.entrycget(2, "label"), "Show Normals")
            self.assertEqual(window.view_menu.entrycget(4, "label"), "Frame All")
            self.assertEqual(window.view_menu.entrycget(5, "label"), "Reset View")
            self.assertEqual(window.view_menu.type(0), "checkbutton")
            self.assertEqual(window.view_menu.type(1), "checkbutton")
            self.assertEqual(window.view_menu.type(2), "checkbutton")

            self.assertTrue(window.show_grid.get())
            self.assertTrue(window.show_axes.get())
            self.assertFalse(window.show_normals.get())
            self.assertFalse(window.show_section_plane.get())
            self.assertEqual(window.proxy_quality.get(), "Medium")
            self.assertEqual(tuple(window.proxy_quality_dropdown.cget("values")), ("Low", "Medium", "High"))
            self.assertEqual(window.status_text.get(), "No selection")
            self.assertIsNone(window.app_state.selected_item)
            self.assertEqual(window.no_selection_frame.winfo_manager(), "grid")
            self.assertEqual(window.model_context_frame.winfo_manager(), "")
            self.assertEqual(window.section_context_frame.winfo_manager(), "")
            self.assertFalse(hasattr(window, "apply_transform_button"))
            self.assertEqual(str(window.select_model_button.cget("state")), "disabled")
            self.assertEqual(str(window.select_section_plane_button.cget("state")), "disabled")
            self.assertEqual(window.compute_section_button.cget("text"), "Compute Section")
            self.assertEqual(window.clear_section_button.cget("text"), "Clear Section")
            self.assertEqual(window.section_plane_text.get(), "Section: Z = 0.000")
            self.assertEqual(window.section_result_text.get(), "Section result: none")
            self.assertEqual(window.scale_value.get(), "1.000")
        finally:
            window.root.destroy()

    def test_loading_progress_dialog_contains_visible_indeterminate_progressbar(self) -> None:
        try:
            root = Tk()
        except TclError as exc:
            raise unittest.SkipTest(f"Tk is unavailable: {exc}") from exc

        dialog: LoadProgressDialog | None = None
        try:
            dialog = LoadProgressDialog(root, "sample.stl")
            progress_bars = [
                widget
                for widget in _widget_descendants(dialog.window)
                if widget.winfo_class() == "TProgressbar"
            ]

            self.assertEqual(len(progress_bars), 1)
            self.assertEqual(str(progress_bars[0].cget("mode")), "indeterminate")
            self.assertGreater(int(progress_bars[0].winfo_width()), 1)
            self.assertTrue(progress_bars[0].winfo_ismapped())

            initial_value = float(progress_bars[0].cget("value"))
            dialog.update_stage(LOAD_PROGRESS_STAGES[0])
            self.assertEqual(dialog.stage_text.get(), LOAD_PROGRESS_STAGES[0])
            self.assertNotEqual(float(progress_bars[0].cget("value")), initial_value)
        finally:
            if dialog is not None:
                dialog.close()
            root.destroy()

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
                window.load_model(Path("sample.stl"))

            self.assertEqual(window.file_name_text.get(), "sample.stl")
            self.assertEqual(window.vertex_count_text.get(), "3")
            self.assertEqual(window.triangle_count_text.get(), "1")
            self.assertEqual(window.bbox_size_text.get(), "1, 2, 3")
            self.assertEqual(
                window.status_text.get(),
                "Source: 1 tris | Display: 1 tris | Reduction: 0.0% | "
                "No proxy (Medium) | Full-resolution source preserved",
            )
            self.assertIsNone(window.app_state.selected_item)
            self.assertEqual(window.no_selection_frame.winfo_manager(), "grid")
            self.assertEqual(window.model_context_frame.winfo_manager(), "")
            self.assertEqual(window.section_context_frame.winfo_manager(), "")
            self.assertEqual(str(window.select_model_button.cget("state")), "normal")
            self.assertEqual(str(window.select_section_plane_button.cget("state")), "normal")
            self.assertTrue(window.show_grid.get())
            self.assertTrue(window.show_axes.get())
            self.assertFalse(window.show_section_plane.get())
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
            self.assertEqual(scene["show_section_plane"], False)
            self.assertEqual(scene["section_axis"], "Z")
            self.assertEqual(scene["section_offset"], 0.0)
            self.assertIsNone(scene["selected_item"])
            self.assertTrue(np.allclose(scene["scene_bounds_min"], [0.0, 0.0, 0.0]))
            self.assertTrue(np.allclose(scene["scene_bounds_max"], [1.0, 2.0, 3.0]))
        finally:
            window.root.destroy()

    def test_loading_mesh_shows_progress_stages_and_disables_open_model(self) -> None:
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

        observed_states: list[tuple[str, str, str]] = []
        progress_dialogs: list[object] = []

        class RecordingProgressDialog:
            def __init__(self, _parent: object, file_name: str) -> None:
                self.file_name = file_name
                self.stages: list[str] = []
                self.closed = False
                progress_dialogs.append(self)
                observed_states.append(
                    (
                        "created",
                        str(window.open_model_button.cget("state")),
                        window.file_menu.entrycget(OPEN_MODEL_MENU_INDEX, "state"),
                    )
                )

            def update_stage(self, stage: str) -> None:
                self.stages.append(stage)
                observed_states.append(
                    (
                        stage,
                        str(window.open_model_button.cget("state")),
                        window.file_menu.entrycget(OPEN_MODEL_MENU_INDEX, "state"),
                    )
                )

            def close(self) -> None:
                self.closed = True

        try:
            with (
                patch("app.main_window.LoadProgressDialog", RecordingProgressDialog),
                patch(
                    "app.main_window.load_mesh",
                    return_value=LoadedMesh(mesh=mesh, metadata=metadata),
                ),
            ):
                window.load_model(Path("sample.stl"))

            progress = progress_dialogs[0]
            self.assertEqual(progress.file_name, "sample.stl")
            self.assertEqual(progress.stages, list(LOAD_PROGRESS_STAGES))
            self.assertTrue(progress.closed)
            self.assertTrue(observed_states)
            self.assertTrue(
                all(
                    button_state == "disabled" and menu_state == "disabled"
                    for _stage, button_state, menu_state in observed_states
                )
            )
            self.assertEqual(str(window.open_model_button.cget("state")), "normal")
            self.assertEqual(
                window.file_menu.entrycget(OPEN_MODEL_MENU_INDEX, "state"),
                "normal",
            )
            self.assertEqual(
                window.status_text.get(),
                "Source: 1 tris | Display: 1 tris | Reduction: 0.0% | "
                "No proxy (Medium) | Full-resolution source preserved",
            )
        finally:
            window.root.destroy()

    def test_loading_mesh_failure_closes_progress_and_reenables_open_model(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        progress_dialogs: list[object] = []

        class RecordingProgressDialog:
            def __init__(self, _parent: object, file_name: str) -> None:
                self.file_name = file_name
                self.stages: list[str] = []
                self.closed = False
                progress_dialogs.append(self)

            def update_stage(self, stage: str) -> None:
                self.stages.append(stage)

            def close(self) -> None:
                self.closed = True

        try:
            with (
                patch("app.main_window.LoadProgressDialog", RecordingProgressDialog),
                patch("app.main_window.load_mesh", side_effect=ValueError("bad mesh")),
                patch("app.main_window.messagebox.showerror") as show_error,
            ):
                window.load_model(Path("broken.stl"))

            progress = progress_dialogs[0]
            self.assertEqual(progress.file_name, "broken.stl")
            self.assertEqual(progress.stages, [LOAD_PROGRESS_STAGES[0]])
            self.assertTrue(progress.closed)
            show_error.assert_called_once_with("Could not open model", "bad mesh")
            self.assertIsNone(window.app_state.mesh_object)
            self.assertEqual(window.status_text.get(), "No selection")
            self.assertEqual(str(window.open_model_button.cget("state")), "normal")
            self.assertEqual(
                window.file_menu.entrycget(OPEN_MODEL_MENU_INDEX, "state"),
                "normal",
            )
        finally:
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
                window.load_model(Path("sample.stl"))

            window.select_model()
            self.assertEqual(window.app_state.selected_item, "model")
            self.assertEqual(window.status_text.get(), "Selected: sample.stl")
            self.assertEqual(window.no_selection_frame.winfo_manager(), "")
            self.assertEqual(window.model_context_frame.winfo_manager(), "grid")
            self.assertEqual(window.section_context_frame.winfo_manager(), "")
            self.assertEqual(window.selected_object_text.get(), "sample.stl")
            self.assertEqual(window.viewport.scene_calls[-1]["selected_item"], "model")
            self.assertIsNotNone(window.viewport.scene_calls[-1]["object_origin"])

            window.location_x.set("1.500")
            window._on_object_transform_changed()
            self.assertEqual(window.status_text.get(), "Transforms update live")
            self.assertAlmostEqual(window.app_state.mesh_object.location[0], 1.5)
            self.assertIsNotNone(window.app_state.mesh_object.transform_matrix)
            self.assertEqual(window.viewport.scene_calls[-1]["mesh"], window.app_state.mesh_object.display_mesh)
            self.assertIsNotNone(window.viewport.scene_calls[-1]["transform_matrix"])

            window.rotation_z.set("90.000")
            window._on_object_transform_changed()
            mapped_origin = window._current_object_matrix() @ np.append(
                window.app_state.mesh_object.origin,
                1.0,
            )
            self.assertTrue(np.allclose(mapped_origin[:3], window.app_state.mesh_object.location))

            window.frame_selected()
            self.assertEqual(window.viewport.frame_count, 1)
            self.assertEqual(window.status_text.get(), "Selected: sample.stl")
        finally:
            window.root.destroy()

    def test_deleting_selected_model_refreshes_without_resetting_camera(self) -> None:
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
                window.load_model(Path("sample.stl"))

            window.select_model()
            reset_count = window.viewport.reset_count
            window._handle_shortcut("Delete")

            self.assertIsNone(window.app_state.mesh_object)
            self.assertEqual(window.status_text.get(), "Selected model removed")
            self.assertEqual(str(window.select_model_button.cget("state")), "disabled")
            self.assertEqual(str(window.select_section_plane_button.cget("state")), "disabled")
            self.assertEqual(window.viewport.reset_count, reset_count)
            self.assertIsNone(window.viewport.scene_calls[-1]["mesh"])
            self.assertEqual(window.viewport.scene_calls[-1]["reset_camera"], False)
            self.assertIsNone(window.viewport.scene_calls[-1]["selected_item"])
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
                window.load_model(Path("sample.stl"))

            window.select_model()
            start_location = window.app_state.mesh_object.location.copy()
            window._on_viewport_pointer_event("motion", 10, 10)
            window._handle_shortcut("G")
            self.assertTrue(window.status_text.get().startswith("Move mode - press X/Y/Z"))
            self.assertEqual(window.viewport.scene_calls[-1]["active_transform_mode"], "move")

            window._handle_shortcut("X")
            self.assertEqual(window.status_text.get(), "Move mode - X axis")
            self.assertEqual(window.viewport.scene_calls[-1]["active_transform_axis"], "X")
            window._handle_shortcut("X")
            self.assertTrue(window.status_text.get().startswith("Move mode - press X/Y/Z"))
            self.assertIsNone(window.viewport.scene_calls[-1]["active_transform_axis"])
            window._handle_shortcut("X")

            handled = window._on_viewport_pointer_event("motion", 80, 10)
            self.assertTrue(handled)
            moved_location = window.app_state.mesh_object.location.copy()
            self.assertGreater(moved_location[0], start_location[0])
            self.assertAlmostEqual(moved_location[1], start_location[1])
            self.assertAlmostEqual(moved_location[2], start_location[2])
            self.assertIn("Delta X:", window.status_text.get())
            self.assertEqual(window.location_x.get(), f"{moved_location[0]:.3f}")

            window._handle_shortcut("Escape")
            self.assertEqual(window.status_text.get(), "Transform cancelled")
            self.assertTrue(np.allclose(window.app_state.mesh_object.location, start_location))
            self.assertEqual(window.location_x.get(), f"{start_location[0]:.3f}")
            self.assertIsNone(window.viewport.scene_calls[-1]["active_transform_mode"])

            window._on_viewport_pointer_event("motion", 0, 0)
            window._handle_shortcut("G")
            window._handle_shortcut("X")
            window._on_viewport_pointer_event("motion", 100, 0)
            normal_location = window.app_state.mesh_object.location.copy()
            window._handle_shortcut("Escape")

            window._on_viewport_pointer_event("motion", 0, 0)
            window._handle_shortcut("G")
            window._handle_shortcut("X")
            window._on_viewport_pointer_event("motion", 100, 0, shift_pressed=True)
            fine_location = window.app_state.mesh_object.location.copy()
            normal_delta = normal_location[0] - start_location[0]
            fine_delta = fine_location[0] - start_location[0]
            self.assertAlmostEqual(fine_delta, normal_delta * 0.1, places=6)
            window._handle_shortcut("Escape")

            window._handle_shortcut("G")
            window._on_viewport_pointer_event("motion", 150, 10)
            confirmed_location = window.app_state.mesh_object.location.copy()
            window._handle_shortcut("Enter")
            self.assertEqual(window.status_text.get(), "Transform confirmed")
            self.assertTrue(np.allclose(window.app_state.mesh_object.location, confirmed_location))
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
                window.load_model(Path("sample.stl"))

            window.select_model()
            window._on_viewport_pointer_event("motion", 0, 0)
            window._handle_shortcut("R")
            self.assertEqual(
                window.status_text.get(),
                "Rotate mode - Z axis - move mouse horizontally",
            )
            self.assertEqual(window.viewport.scene_calls[-1]["active_transform_mode"], "rotate")
            self.assertEqual(window.viewport.scene_calls[-1]["active_transform_axis"], "Z")
            self.assertEqual(window.viewport.scene_calls[-1]["active_transform_angle_delta"], 0.0)
            window._handle_shortcut("X")
            self.assertEqual(window.status_text.get(), "Rotate mode - X axis - move mouse horizontally")
            self.assertEqual(window.viewport.scene_calls[-1]["active_transform_axis"], "X")
            self.assertEqual(window.viewport.scene_calls[-1]["active_transform_angle_delta"], 0.0)

            window._on_viewport_pointer_event("motion", 40, 0)
            self.assertGreater(window.app_state.mesh_object.rotation[0], 0.0)
            self.assertIn("20.0 deg", window.status_text.get())
            self.assertEqual(window.viewport.scene_calls[-1]["active_transform_angle_delta"], 20.0)
            self.assertEqual(window.rotation_x.get(), f"{window.app_state.mesh_object.rotation[0]:.3f}")
            self.assertEqual(window.rotation_y.get(), "0.000")
            self.assertEqual(window.rotation_z.get(), "0.000")

            mapped_origin = window._current_object_matrix() @ np.append(
                window.app_state.mesh_object.origin,
                1.0,
            )
            self.assertTrue(np.allclose(mapped_origin[:3], window.app_state.mesh_object.location))
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
                window.load_model(Path("sample.stl"))

            window.select_section_plane()
            self.assertEqual(window.app_state.selected_item, "section_plane")
            self.assertEqual(window.status_text.get(), "Selected: Section Plane")
            self.assertEqual(window.no_selection_frame.winfo_manager(), "")
            self.assertEqual(window.model_context_frame.winfo_manager(), "")
            self.assertEqual(window.section_context_frame.winfo_manager(), "grid")
            self.assertEqual(window.viewport.scene_calls[-1]["selected_item"], "section_plane")
            self.assertEqual(window.viewport.scene_calls[-1]["show_section_plane"], True)

            window._set_section_offset(0.5, clamp=True, refresh=True)
            self.assertEqual(window.section_plane_text.get(), "Section: Z = 0.500")
            self.assertEqual(window.status_text.get(), "Section plane: Z = 0.500")
            self.assertEqual(window.viewport.scene_calls[-1]["section_offset"], 0.5)

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

            window.clear_selection()
            self.assertIsNone(window.app_state.selected_item)
            self.assertEqual(window.viewport.scene_calls[-1]["show_section_plane"], False)

            window.show_section_plane.set(True)
            window._on_section_plane_visibility_changed()
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
                window.load_model(Path("sample.stl"))

            window.select_section_plane()
            start_offset = window.section_offset.get()
            window._on_viewport_pointer_event("motion", 0, 0)
            window._handle_shortcut("G")
            self.assertEqual(window.status_text.get(), "Move mode - Z axis")
            window._on_viewport_pointer_event("motion", 50, 0)
            moved_offset = window.section_offset.get()
            self.assertGreater(moved_offset, start_offset)
            self.assertEqual(window.section_offset_text.get(), f"{moved_offset:.3f}")
            self.assertIn("Offset Z:", window.status_text.get())

            handled = window._on_viewport_pointer_event("right_release", 50, 0)
            self.assertTrue(handled)
            self.assertEqual(window.status_text.get(), "Transform cancelled")
            self.assertAlmostEqual(window.section_offset.get(), start_offset)

            window._handle_shortcut("G")
            window._handle_shortcut("X")
            self.assertEqual(window.section_axis.get(), "X")
            self.assertEqual(window.status_text.get(), "Move mode - X axis")
            window._on_viewport_pointer_event("motion", 100, 0)
            confirmed_offset = window.section_offset.get()
            handled = window._on_viewport_pointer_event("left_release", 100, 0)
            self.assertTrue(handled)
            self.assertEqual(window.status_text.get(), "Transform confirmed")
            self.assertAlmostEqual(window.section_offset.get(), confirmed_offset)
            self.assertGreater(confirmed_offset, start_offset)

            self.assertEqual(window.section_axis.get(), "X")
            window._handle_shortcut("R")
            self.assertEqual(window.section_axis.get(), "Y")
            self.assertEqual(window.status_text.get(), "Section plane axis cycled to Y")
        finally:
            window.root.destroy()


if __name__ == "__main__":
    unittest.main()

