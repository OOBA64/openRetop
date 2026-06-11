from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from tkinter import TclError, Tk
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.main_window import (
    LOAD_PROGRESS_STAGES,
    LoadProgressDialog,
    OPEN_MODEL_MENU_INDEX,
    OpenRetopWindow,
)
from app.scene_browser import (
    NODE_CURVES,
    NODE_MESH,
    NODE_SCENE,
    NODE_SECTION_PLANES,
    NODE_SECTION_RESULTS,
    section_plane_node_id,
)
from mesh.loader import LoadedMesh, MeshMetadata
from project.project_data import default_project_data
from project.project_io import load_project, save_project
from settings.settings_data import default_app_settings
from settings.settings_io import load_settings, save_settings


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
        self.camera_right = np.asarray([1.0, 0.0, 0.0], dtype=float)
        self.camera_up = np.asarray([0.0, 1.0, 0.0], dtype=float)

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

    def get_camera_vectors(self) -> object:
        return SimpleNamespace(
            right=self.camera_right,
            up=self.camera_up,
            forward=np.asarray([0.0, 0.0, -1.0], dtype=float),
            position=np.asarray([0.0, 0.0, 1.0], dtype=float),
            focal_point=np.asarray([0.0, 0.0, 0.0], dtype=float),
        )

    def close(self) -> None:
        self.closed = True


def _create_window(*, settings_path: Path | None = None) -> OpenRetopWindow:
    settings_tmpdir: TemporaryDirectory[str] | None = None
    if settings_path is None:
        settings_tmpdir = TemporaryDirectory()
        settings_path = Path(settings_tmpdir.name) / "settings.json"

    try:
        window = OpenRetopWindow(settings_path=settings_path)
    except TclError as exc:
        if settings_tmpdir is not None:
            settings_tmpdir.cleanup()
        raise unittest.SkipTest(f"Tk is unavailable: {exc}") from exc

    if settings_tmpdir is not None:
        original_destroy = window.root.destroy

        def destroy_with_settings_cleanup() -> None:
            try:
                original_destroy()
            finally:
                settings_tmpdir.cleanup()

        window.root.destroy = destroy_with_settings_cleanup  # type: ignore[method-assign]

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


def _button_by_text(widget: object, text: str) -> object:
    for child in _widget_descendants(widget):
        if child.winfo_class() == "TButton" and child.cget("text") == text:
            return child
    raise AssertionError(f"Button not found: {text}")


def _widgets_with_text(widget: object, text: str) -> list[object]:
    matches: list[object] = []
    for child in _widget_descendants(widget):
        try:
            if child.cget("text") == text:
                matches.append(child)
        except TclError:
            continue
    return matches


class MainWindowUiTests(unittest.TestCase):
    def test_menu_bar_and_initial_no_selection_context_match_instructions(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            self.assertEqual(window.menu_bar.entrycget(0, "label"), "File")
            self.assertEqual(window.menu_bar.entrycget(1, "label"), "Edit")
            self.assertEqual(window.menu_bar.entrycget(2, "label"), "View")
            self.assertEqual(window.menu_bar.entrycget(3, "label"), "Tools")
            self.assertEqual(window.menu_bar.entrycget(4, "label"), "Help")
            self.assertEqual(window.file_menu.entrycget(0, "label"), "New Project")
            self.assertEqual(window.file_menu.entrycget(1, "label"), "Open Model")
            self.assertEqual(window.file_menu.entrycget(2, "label"), "Open Project")
            self.assertEqual(window.file_menu.entrycget(3, "label"), "Save Project")
            self.assertEqual(window.file_menu.entrycget(4, "label"), "Save Project As")
            self.assertEqual(window.file_menu.entrycget(5, "label"), "Exit")
            self.assertEqual(window.edit_menu.entrycget(0, "label"), "Undo")
            self.assertEqual(window.edit_menu.entrycget(1, "label"), "Redo")
            self.assertEqual(window.edit_menu.entrycget(2, "label"), "Preferences")
            self.assertEqual(window.view_menu.entrycget(0, "label"), "Frame All")
            self.assertEqual(window.view_menu.entrycget(1, "label"), "Frame Selected")
            self.assertEqual(window.view_menu.entrycget(2, "label"), "Reset View")
            self.assertEqual(window.view_menu.entrycget(3, "label"), "Show Grid")
            self.assertEqual(window.view_menu.entrycget(4, "label"), "Show Axes")
            self.assertEqual(window.view_menu.entrycget(5, "label"), "Show Normals")
            self.assertEqual(window.view_menu.type(3), "checkbutton")
            self.assertEqual(window.view_menu.type(4), "checkbutton")
            self.assertEqual(window.view_menu.type(5), "checkbutton")
            self.assertEqual(window.tools_menu.entrycget(0, "label"), "Select Model")
            self.assertEqual(window.tools_menu.entrycget(1, "label"), "Select Section Plane")
            self.assertEqual(window.tools_menu.entrycget(2, "label"), "Compute Section")
            self.assertEqual(window.tools_menu.entrycget(3, "label"), "Clear Section")
            self.assertEqual(window.help_menu.entrycget(0, "label"), "About")

            self.assertTrue(window.show_grid.get())
            self.assertTrue(window.show_axes.get())
            self.assertFalse(window.show_normals.get())
            self.assertFalse(window.show_section_plane.get())
            self.assertEqual(window.proxy_quality.get(), "Medium")
            self.assertEqual(tuple(window.proxy_quality_dropdown.cget("values")), ("Low", "Medium", "High"))
            self.assertEqual(window.status_text.get(), "No selection")
            self.assertIsNone(window.current_project_path)
            self.assertFalse(window.project_dirty)
            self.assertEqual(window.root.title(), "openRetop - Untitled Project")
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
            self.assertEqual(window.scene_browser.frame.winfo_manager(), "grid")
            self.assertEqual(window.scene_browser.tree.item(NODE_SCENE, "text"), "Scene")
            self.assertEqual(window.scene_browser.tree.get_children(NODE_SCENE), ())
        finally:
            window.root.destroy()

    def test_remaining_menu_placeholders_report_not_implemented_without_crashing(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            placeholder_invocations = (
                (window.edit_menu, 0, "Undo"),
                (window.edit_menu, 1, "Redo"),
                (window.help_menu, 0, "About"),
            )

            for menu, index, label in placeholder_invocations:
                menu.invoke(index)
                self.assertEqual(window.status_text.get(), f"{label}: Not implemented yet")
        finally:
            window.root.destroy()

    def test_preferences_dialog_opens_with_startup_values_and_controls(self) -> None:
        settings = default_app_settings()
        settings.display.show_grid = False
        settings.display.show_axes = False
        settings.display.show_normals = True
        settings.import_settings.default_proxy_quality = "High"

        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"
            save_settings(settings, settings_path)

            with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
                window = _create_window(settings_path=settings_path)

        try:
            window.show_grid.set(True)
            window.show_axes.set(True)
            window.show_normals.set(False)
            window.proxy_quality.set("Medium")

            window.edit_menu.invoke(2)
            window.root.update()
            dialog = window.preferences_dialog
            self.assertIsNotNone(dialog)
            assert dialog is not None

            self.assertEqual(dialog.title(), "Preferences")
            self.assertFalse(window.preferences_vars["show_grid"].get())
            self.assertFalse(window.preferences_vars["show_axes"].get())
            self.assertTrue(window.preferences_vars["show_normals"].get())
            self.assertEqual(window.preferences_vars["default_proxy_quality"].get(), "High")
            self.assertTrue(_widgets_with_text(dialog, "Display"))
            self.assertTrue(_widgets_with_text(dialog, "Import"))
            self.assertTrue(_widgets_with_text(dialog, "Startup Show Grid"))
            self.assertTrue(_widgets_with_text(dialog, "Startup Show Axes"))
            self.assertTrue(_widgets_with_text(dialog, "Startup Show Normals"))
            self.assertFalse(_widgets_with_text(dialog, "Show Grid"))
            self.assertFalse(_widgets_with_text(dialog, "Show Axes"))
            self.assertFalse(_widgets_with_text(dialog, "Show Normals"))
            self.assertTrue(_widgets_with_text(dialog, "Default Proxy Quality"))
            for button_text in ("OK", "Cancel", "Apply"):
                self.assertIsNotNone(_button_by_text(dialog, button_text))

            comboboxes = [
                widget
                for widget in _widget_descendants(dialog)
                if widget.winfo_class() == "TCombobox"
            ]
            self.assertEqual(len(comboboxes), 1)
            self.assertEqual(tuple(comboboxes[0].cget("values")), ("Low", "Medium", "High"))

            existing_dialog = window.preferences_dialog
            window.edit_menu.invoke(2)
            self.assertIs(window.preferences_dialog, existing_dialog)
        finally:
            if window.preferences_dialog is not None:
                window._close_preferences_dialog()
            window.root.destroy()

    def test_preferences_apply_updates_startup_defaults_without_changing_current_scene(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"
            with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
                window = _create_window(settings_path=settings_path)

            try:
                window.edit_menu.invoke(2)
                dialog = window.preferences_dialog
                self.assertIsNotNone(dialog)
                assert dialog is not None

                scene_call_count = len(window.viewport.scene_calls)
                window.preferences_vars["show_grid"].set(False)
                window.preferences_vars["show_axes"].set(False)
                window.preferences_vars["show_normals"].set(True)
                window.preferences_vars["default_proxy_quality"].set("Low")
                _button_by_text(dialog, "Apply").invoke()

                self.assertIsNotNone(window.preferences_dialog)
                self.assertTrue(window.show_grid.get())
                self.assertTrue(window.show_axes.get())
                self.assertFalse(window.show_normals.get())
                self.assertEqual(window.proxy_quality.get(), "Medium")
                self.assertEqual(window.status_text.get(), "Preferences applied")
                self.assertEqual(len(window.viewport.scene_calls), scene_call_count)
                self.assertFalse(window.settings.display.show_grid)
                self.assertFalse(window.settings.display.show_axes)
                self.assertTrue(window.settings.display.show_normals)
                self.assertEqual(
                    window.settings.import_settings.default_proxy_quality,
                    "Low",
                )

                saved_settings = load_settings(settings_path)
                self.assertFalse(saved_settings.display.show_grid)
                self.assertFalse(saved_settings.display.show_axes)
                self.assertTrue(saved_settings.display.show_normals)
                self.assertEqual(
                    saved_settings.import_settings.default_proxy_quality,
                    "Low",
                )
            finally:
                if window.preferences_dialog is not None:
                    window._close_preferences_dialog()
                window.root.destroy()

            with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
                restored_window = _create_window(settings_path=settings_path)

            try:
                self.assertFalse(restored_window.show_grid.get())
                self.assertFalse(restored_window.show_axes.get())
                self.assertTrue(restored_window.show_normals.get())
                self.assertEqual(restored_window.proxy_quality.get(), "Low")
            finally:
                restored_window.root.destroy()

    def test_preferences_ok_applies_and_closes_dialog(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"
            with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
                window = _create_window(settings_path=settings_path)

            try:
                window.edit_menu.invoke(2)
                dialog = window.preferences_dialog
                self.assertIsNotNone(dialog)
                assert dialog is not None

                window.preferences_vars["show_grid"].set(False)
                _button_by_text(dialog, "OK").invoke()

                self.assertIsNone(window.preferences_dialog)
                self.assertEqual(window.preferences_vars, {})
                self.assertTrue(window.show_grid.get())
                self.assertFalse(window.settings.display.show_grid)
                self.assertFalse(load_settings(settings_path).display.show_grid)
                self.assertEqual(window.status_text.get(), "Preferences applied")
            finally:
                window.root.destroy()

    def test_preferences_cancel_closes_without_applying(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"
            with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
                window = _create_window(settings_path=settings_path)

            try:
                window.edit_menu.invoke(2)
                dialog = window.preferences_dialog
                self.assertIsNotNone(dialog)
                assert dialog is not None

                window.preferences_vars["show_grid"].set(False)
                window.preferences_vars["default_proxy_quality"].set("High")
                _button_by_text(dialog, "Cancel").invoke()

                self.assertIsNone(window.preferences_dialog)
                self.assertEqual(window.preferences_vars, {})
                self.assertTrue(window.show_grid.get())
                self.assertEqual(window.proxy_quality.get(), "Medium")
                self.assertFalse(settings_path.exists())
            finally:
                window.root.destroy()

    def test_startup_loads_preferences_from_settings_file(self) -> None:
        settings = default_app_settings()
        settings.display.show_grid = False
        settings.display.show_axes = False
        settings.display.show_normals = True
        settings.import_settings.default_proxy_quality = "High"
        settings.ui.window_width = 1120
        settings.ui.window_height = 720

        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"
            save_settings(settings, settings_path)

            with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
                window = _create_window(settings_path=settings_path)

            try:
                self.assertFalse(window.show_grid.get())
                self.assertFalse(window.show_axes.get())
                self.assertTrue(window.show_normals.get())
                self.assertEqual(window.proxy_quality.get(), "High")
                self.assertTrue(window.root.geometry().startswith("1120x720"))
                self.assertEqual(window.display_proxy_text.get(), "Disabled (High)")
            finally:
                window.root.destroy()

    def test_invalid_startup_preferences_recover_to_defaults(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"
            settings_path.write_text("{broken json", encoding="utf-8")

            with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
                window = _create_window(settings_path=settings_path)

            try:
                self.assertTrue(window.show_grid.get())
                self.assertTrue(window.show_axes.get())
                self.assertFalse(window.show_normals.get())
                self.assertEqual(window.proxy_quality.get(), "Medium")
                self.assertTrue(window.root.geometry().startswith("1280x800"))
            finally:
                window.root.destroy()

    def test_exit_saves_window_size_without_overwriting_startup_preferences(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"

            with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
                window = _create_window(settings_path=settings_path)

            window.show_grid.set(False)
            window.show_axes.set(False)
            window.show_normals.set(True)
            window.proxy_quality.set("Low")
            window.root.geometry("1180x740")
            window.root.update_idletasks()
            window._on_exit()

            self.assertTrue(settings_path.exists())
            saved_settings = load_settings(settings_path)
            self.assertTrue(saved_settings.display.show_grid)
            self.assertTrue(saved_settings.display.show_axes)
            self.assertFalse(saved_settings.display.show_normals)
            self.assertEqual(saved_settings.import_settings.default_proxy_quality, "Medium")
            self.assertEqual(saved_settings.ui.window_width, 1180)
            self.assertEqual(saved_settings.ui.window_height, 740)

            with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
                restored_window = _create_window(settings_path=settings_path)

            try:
                self.assertTrue(restored_window.show_grid.get())
                self.assertTrue(restored_window.show_axes.get())
                self.assertFalse(restored_window.show_normals.get())
                self.assertEqual(restored_window.proxy_quality.get(), "Medium")
                self.assertTrue(restored_window.root.geometry().startswith("1180x740"))
            finally:
                restored_window.root.destroy()

    def test_new_project_resets_project_path_without_touching_loaded_mesh(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            mesh_object = SimpleNamespace(name="sample.stl")
            project_path = Path("saved.openretop")
            window.current_project_path = project_path
            window.app_state.mesh_object = mesh_object
            window.app_state.selected_item = "model"
            window.status_text.set(f"Project opened: Saved Metadata ({project_path})")
            scene_call_count = len(window.viewport.scene_calls)

            window.file_menu.invoke(0)

            self.assertIsNone(window.current_project_path)
            self.assertFalse(window.project_dirty)
            self.assertEqual(window.root.title(), "openRetop - Untitled Project")
            self.assertEqual(window.status_text.get(), "Project ready: Untitled Project")
            self.assertIs(window.app_state.mesh_object, mesh_object)
            self.assertEqual(window.app_state.selected_item, "model")
            self.assertEqual(len(window.viewport.scene_calls), scene_call_count)
        finally:
            window.root.destroy()

    def test_new_project_dirty_prompt_cancel_keeps_project_metadata(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            project_path = Path("saved.openretop")
            window.current_project_path = project_path
            window._set_project_dirty(True)
            window.status_text.set("Working")

            with patch("app.main_window.messagebox.askyesnocancel", return_value=None) as prompt:
                window.file_menu.invoke(0)

            prompt.assert_called_once()
            self.assertEqual(window.current_project_path, project_path)
            self.assertTrue(window.project_dirty)
            self.assertEqual(window.root.title(), "openRetop - saved.openretop *")
            self.assertEqual(window.status_text.get(), "Working")
        finally:
            window.root.destroy()

    def test_new_project_dirty_prompt_dont_save_resets_metadata(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            window.current_project_path = Path("saved.openretop")
            window._set_project_dirty(True)

            with patch("app.main_window.messagebox.askyesnocancel", return_value=False) as prompt:
                window.file_menu.invoke(0)

            prompt.assert_called_once()
            self.assertIsNone(window.current_project_path)
            self.assertFalse(window.project_dirty)
            self.assertEqual(window.root.title(), "openRetop - Untitled Project")
            self.assertEqual(window.status_text.get(), "Project ready: Untitled Project")
        finally:
            window.root.destroy()

    def test_open_project_without_mesh_path_reads_metadata_only(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with TemporaryDirectory() as tmpdir:
                project_path = Path(tmpdir) / "saved.openretop"
                project = default_project_data()
                project.name = "Saved Metadata"
                project.mesh_path = None
                project.display.show_grid = False
                project.display.show_axes = False
                project.display.show_normals = True
                project.section.axis = "X"
                project.section.offset = 2.0
                project.section.show_plane = True
                save_project(project, project_path)

                scene_call_count = len(window.viewport.scene_calls)
                mesh_object = window.app_state.mesh_object

                with (
                    patch(
                        "app.main_window.filedialog.askopenfilename",
                        return_value=str(project_path),
                    ) as ask_open,
                    patch("app.main_window.load_mesh") as load_mesh,
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(2)

                ask_open.assert_called_once()
                load_mesh.assert_not_called()
                show_error.assert_not_called()
                self.assertEqual(window.current_project_path, project_path)
                self.assertEqual(
                    window.status_text.get(),
                    f"Project loaded: Saved Metadata ({project_path})",
                )
                self.assertFalse(window.project_dirty)
                self.assertEqual(window.root.title(), "openRetop - saved.openretop")
                self.assertIs(window.app_state.mesh_object, mesh_object)
                self.assertEqual(len(window.viewport.scene_calls), scene_call_count)
                self.assertFalse(window.show_grid.get())
                self.assertFalse(window.show_axes.get())
                self.assertTrue(window.show_normals.get())
                self.assertTrue(window.show_section_plane.get())
                self.assertEqual(window.section_axis.get(), "X")
                self.assertEqual(window.section_offset.get(), 2.0)
                self.assertEqual(window.section_offset_text.get(), "2.000")
                self.assertEqual(window.section_plane_text.get(), "Section: X = 2.000")
        finally:
            window.root.destroy()

    def test_open_project_reloads_mesh_and_restores_saved_state(self) -> None:
        mesh = FakeMesh()

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
            with TemporaryDirectory() as tmpdir:
                mesh_path = Path(tmpdir) / "sample.stl"
                project_path = Path(tmpdir) / "saved.openretop"
                metadata = MeshMetadata(
                    file_path=mesh_path,
                    file_name="sample.stl",
                    extension=".stl",
                    vertex_count=3,
                    triangle_count=1,
                    had_vertex_normals=True,
                    had_triangle_normals=True,
                    computed_vertex_normals=False,
                    computed_triangle_normals=False,
                )
                project = default_project_data()
                project.name = "Restored Project"
                project.mesh_path = str(mesh_path)
                project.transform.location = [4.0, 5.0, 6.0]
                project.transform.rotation = [10.0, 20.0, 30.0]
                project.transform.scale = 1.5
                project.transform.origin = [0.25, 0.5, 0.75]
                project.display.proxy_quality = "High"
                project.display.show_grid = False
                project.display.show_axes = False
                project.display.show_normals = True
                project.section.axis = "X"
                project.section.offset = 0.5
                project.section.show_plane = True
                save_project(project, project_path)

                with (
                    patch("app.main_window.LoadProgressDialog", RecordingProgressDialog),
                    patch(
                        "app.main_window.filedialog.askopenfilename",
                        return_value=str(project_path),
                    ),
                    patch(
                        "app.main_window.load_mesh",
                        return_value=LoadedMesh(mesh=mesh, metadata=metadata),
                    ) as load_mesh,
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(2)

                load_mesh.assert_called_once_with(mesh_path)
                show_error.assert_not_called()
                self.assertEqual(window.current_project_path, project_path)
                self.assertEqual(progress_dialogs[0].file_name, "sample.stl")
                self.assertEqual(progress_dialogs[0].stages, list(LOAD_PROGRESS_STAGES))
                self.assertTrue(progress_dialogs[0].closed)
                self.assertEqual(
                    window.status_text.get(),
                    f"Project loaded: Restored Project ({project_path})",
                )
                self.assertFalse(window.project_dirty)
                self.assertEqual(window.root.title(), "openRetop - saved.openretop")
                self.assertIsNotNone(window.app_state.mesh_object)
                self.assertTrue(np.allclose(window.app_state.mesh_object.location, [4.0, 5.0, 6.0]))
                self.assertTrue(np.allclose(window.app_state.mesh_object.rotation, [10.0, 20.0, 30.0]))
                self.assertAlmostEqual(window.app_state.mesh_object.scale, 1.5)
                self.assertTrue(np.allclose(window.app_state.mesh_object.origin, [0.25, 0.5, 0.75]))
                self.assertEqual(window.location_x.get(), "4.000")
                self.assertEqual(window.location_y.get(), "5.000")
                self.assertEqual(window.location_z.get(), "6.000")
                self.assertEqual(window.rotation_x.get(), "10.000")
                self.assertEqual(window.rotation_y.get(), "20.000")
                self.assertEqual(window.rotation_z.get(), "30.000")
                self.assertEqual(window.scale_value.get(), "1.500")
                self.assertEqual(window.proxy_quality.get(), "High")
                self.assertFalse(window.show_grid.get())
                self.assertFalse(window.show_axes.get())
                self.assertTrue(window.show_normals.get())
                self.assertTrue(window.show_section_plane.get())
                self.assertEqual(window.section_axis.get(), "X")
                self.assertEqual(window.section_offset.get(), 0.5)
                self.assertEqual(window.section_offset_text.get(), "0.500")
                self.assertEqual(window.section_plane_text.get(), "Section: X = 0.500")
                scene = window.viewport.scene_calls[-1]
                self.assertEqual(scene["show_grid"], False)
                self.assertEqual(scene["show_axes"], False)
                self.assertEqual(scene["show_normals"], True)
                self.assertEqual(scene["show_section_plane"], True)
                self.assertEqual(scene["section_axis"], "X")
                self.assertEqual(scene["section_offset"], 0.5)
                self.assertEqual(scene["mesh"], window.app_state.mesh_object.display_mesh)
                self.assertIsNotNone(scene["transform_matrix"])
        finally:
            window.root.destroy()

    def test_open_project_missing_mesh_path_reports_error_and_keeps_app_usable(self) -> None:
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
            with TemporaryDirectory() as tmpdir:
                project_path = Path(tmpdir) / "missing-mesh.openretop"
                previous_mesh = SimpleNamespace(name="previous.stl")
                window.app_state.mesh_object = previous_mesh
                project = default_project_data()
                project.name = "Missing Mesh Project"
                project.mesh_path = "missing.stl"
                save_project(project, project_path)

                with (
                    patch("app.main_window.LoadProgressDialog", RecordingProgressDialog),
                    patch(
                        "app.main_window.filedialog.askopenfilename",
                        return_value=str(project_path),
                    ),
                    patch(
                        "app.main_window.load_mesh",
                        side_effect=FileNotFoundError("Mesh file does not exist: missing.stl"),
                    ),
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(2)

                show_error.assert_called_once_with(
                    "Could not open project",
                    "Mesh file does not exist: missing.stl",
                )
                self.assertEqual(window.current_project_path, project_path)
                self.assertIs(window.app_state.mesh_object, previous_mesh)
                self.assertEqual(window.status_text.get(), "Project open failed")
                self.assertEqual(str(window.open_model_button.cget("state")), "normal")
                self.assertEqual(
                    window.file_menu.entrycget(OPEN_MODEL_MENU_INDEX, "state"),
                    "normal",
                )
                self.assertEqual(progress_dialogs[0].stages, [LOAD_PROGRESS_STAGES[0]])
                self.assertTrue(progress_dialogs[0].closed)
        finally:
            window.root.destroy()

    def test_open_project_invalid_file_reports_error_without_changing_project_path(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with TemporaryDirectory() as tmpdir:
                project_path = Path(tmpdir) / "broken.openretop"
                previous_path = Path(tmpdir) / "previous.openretop"
                project_path.write_text("{broken json", encoding="utf-8")
                window.current_project_path = previous_path
                scene_call_count = len(window.viewport.scene_calls)

                with (
                    patch(
                        "app.main_window.filedialog.askopenfilename",
                        return_value=str(project_path),
                    ),
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(2)

                show_error.assert_called_once()
                self.assertEqual(show_error.call_args.args[0], "Could not open project")
                self.assertIn("Invalid project JSON", show_error.call_args.args[1])
                self.assertEqual(window.current_project_path, previous_path)
                self.assertEqual(window.status_text.get(), "Project open failed")
                self.assertEqual(len(window.viewport.scene_calls), scene_call_count)
        finally:
            window.root.destroy()

    def test_save_project_prompts_for_path_and_writes_project_without_mesh(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with TemporaryDirectory() as tmpdir:
                project_path = Path(tmpdir) / "empty.openretop"

                with (
                    patch(
                        "app.main_window.filedialog.asksaveasfilename",
                        return_value=str(project_path),
                    ) as ask_save,
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(3)

                ask_save.assert_called_once()
                show_error.assert_not_called()
                self.assertEqual(window.current_project_path, project_path)
                self.assertFalse(window.project_dirty)
                self.assertEqual(window.root.title(), "openRetop - empty.openretop")
                self.assertEqual(window.status_text.get(), f"Project saved: {project_path}")

                project = load_project(project_path)
                self.assertEqual(project.name, "Untitled Project")
                self.assertIsNone(project.mesh_path)
                self.assertEqual(project.transform.location, [0.0, 0.0, 0.0])
                self.assertEqual(project.transform.rotation, [0.0, 0.0, 0.0])
                self.assertEqual(project.transform.scale, 1.0)
                self.assertEqual(project.transform.origin, [0.0, 0.0, 0.0])
                self.assertEqual(project.display.proxy_quality, "Medium")
                self.assertTrue(project.display.show_grid)
                self.assertTrue(project.display.show_axes)
                self.assertFalse(project.display.show_normals)
                self.assertEqual(project.section.axis, "Z")
                self.assertEqual(project.section.offset, 0.0)
                self.assertFalse(project.section.show_plane)
        finally:
            window.root.destroy()

    def test_save_project_overwrites_current_project_path_without_prompting(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with TemporaryDirectory() as tmpdir:
                project_path = Path(tmpdir) / "current.openretop"
                project_path.write_text("old contents", encoding="utf-8")
                window.current_project_path = project_path
                window._set_project_dirty(True)
                window.show_grid.set(False)

                with (
                    patch("app.main_window.filedialog.asksaveasfilename") as ask_save,
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(3)

                ask_save.assert_not_called()
                show_error.assert_not_called()
                self.assertEqual(window.current_project_path, project_path)
                self.assertFalse(window.project_dirty)
                self.assertEqual(window.root.title(), "openRetop - current.openretop")
                self.assertEqual(window.status_text.get(), f"Project saved: {project_path}")
                self.assertFalse(load_project(project_path).display.show_grid)
        finally:
            window.root.destroy()

    def test_save_project_as_writes_loaded_mesh_transform_and_settings(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            mesh_path = Path("sample.stl")
            window.app_state.mesh_object = SimpleNamespace(
                file_path=mesh_path,
                location=np.asarray([1.0, 2.0, 3.0], dtype=float),
                rotation=np.asarray([10.0, 20.0, 30.0], dtype=float),
                scale=1.75,
                origin=np.asarray([0.5, 0.25, 0.0], dtype=float),
            )
            window.proxy_quality.set("High")
            window.show_grid.set(False)
            window.show_axes.set(False)
            window.show_normals.set(True)
            window.section_axis.set("X")
            window.section_offset.set(0.5)
            window.show_section_plane.set(True)

            with TemporaryDirectory() as tmpdir:
                project_path = Path(tmpdir) / "mesh.openretop"

                with (
                    patch(
                        "app.main_window.filedialog.asksaveasfilename",
                        return_value=str(project_path),
                    ) as ask_save,
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(4)

                ask_save.assert_called_once()
                show_error.assert_not_called()
                self.assertEqual(window.current_project_path, project_path)
                self.assertFalse(window.project_dirty)
                self.assertEqual(window.root.title(), "openRetop - mesh.openretop")
                self.assertEqual(window.status_text.get(), f"Project saved: {project_path}")

                project = load_project(project_path)
                self.assertEqual(project.mesh_path, str(mesh_path))
                self.assertEqual(project.transform.location, [1.0, 2.0, 3.0])
                self.assertEqual(project.transform.rotation, [10.0, 20.0, 30.0])
                self.assertEqual(project.transform.scale, 1.75)
                self.assertEqual(project.transform.origin, [0.5, 0.25, 0.0])
                self.assertEqual(project.display.proxy_quality, "High")
                self.assertFalse(project.display.show_grid)
                self.assertFalse(project.display.show_axes)
                self.assertTrue(project.display.show_normals)
                self.assertEqual(project.section.axis, "X")
                self.assertEqual(project.section.offset, 0.5)
                self.assertTrue(project.section.show_plane)
        finally:
            window.root.destroy()

    def test_save_project_failure_reports_error(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            window.current_project_path = Path("broken.openretop")

            with (
                patch("app.main_window.save_project", side_effect=OSError("disk full")),
                patch("app.main_window.messagebox.showerror") as show_error,
            ):
                window.file_menu.invoke(3)

            show_error.assert_called_once_with("Could not save project", "disk full")
            self.assertEqual(window.status_text.get(), "Project save failed")
        finally:
            window.root.destroy()

    def test_dirty_close_cancel_keeps_window_open(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            window._set_project_dirty(True)

            with (
                patch("app.main_window.messagebox.askyesnocancel", return_value=None) as prompt,
                patch.object(window.root, "destroy") as destroy,
            ):
                window._on_exit()

            prompt.assert_called_once()
            destroy.assert_not_called()
            self.assertFalse(window.viewport.closed)
            self.assertTrue(window.project_dirty)
            self.assertEqual(window.root.title(), "openRetop - Untitled Project *")
        finally:
            window.root.destroy()

    def test_dirty_close_dont_save_closes_without_saving(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            window._set_project_dirty(True)

            with (
                patch("app.main_window.messagebox.askyesnocancel", return_value=False) as prompt,
                patch.object(window.root, "destroy") as destroy,
                patch("app.main_window.save_project") as save_project_fn,
            ):
                window._on_exit()

            prompt.assert_called_once()
            save_project_fn.assert_not_called()
            destroy.assert_called_once()
            self.assertTrue(window.viewport.closed)
        finally:
            window.root.destroy()

    def test_dirty_close_save_writes_project_then_closes(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with TemporaryDirectory() as tmpdir:
                project_path = Path(tmpdir) / "closing.openretop"
                window.current_project_path = project_path
                window._set_project_dirty(True)

                with (
                    patch("app.main_window.messagebox.askyesnocancel", return_value=True) as prompt,
                    patch.object(window.root, "destroy") as destroy,
                ):
                    window._on_exit()

                prompt.assert_called_once()
                destroy.assert_called_once()
                self.assertTrue(window.viewport.closed)
                self.assertFalse(window.project_dirty)
                self.assertEqual(window.root.title(), "openRetop - closing.openretop")
                self.assertTrue(project_path.exists())
                self.assertEqual(load_project(project_path).name, "Untitled Project")
        finally:
            window.root.destroy()

    def test_tools_menu_commands_keep_existing_no_selection_behavior(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            window.tools_menu.invoke(0)
            self.assertEqual(window.status_text.get(), "No selection")
            window.tools_menu.invoke(1)
            self.assertEqual(window.status_text.get(), "No selection")
            window.tools_menu.invoke(2)
            self.assertEqual(window.status_text.get(), "No selection")
            window.tools_menu.invoke(3)
            self.assertEqual(window.status_text.get(), "Section cleared")
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
            self.assertTrue(window.project_dirty)
            self.assertEqual(window.root.title(), "openRetop - Untitled Project *")
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

    def test_scene_browser_syncs_mesh_section_nodes_and_selection(self) -> None:
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

            tree = window.scene_browser.tree
            active_plane = window.app_state.section_collection.planes[0]
            section_plane_node = section_plane_node_id(active_plane.id)
            self.assertEqual(
                tree.get_children(NODE_SCENE),
                (NODE_MESH, NODE_SECTION_PLANES),
            )
            self.assertEqual(tree.item(NODE_MESH, "text"), "Mesh")
            self.assertEqual(tree.item(NODE_SECTION_PLANES, "text"), "Section Planes")
            self.assertEqual(tree.get_children(NODE_SECTION_PLANES), (section_plane_node,))
            self.assertEqual(tree.item(section_plane_node, "text"), "Section Plane 1")
            self.assertFalse(tree.exists(NODE_SECTION_RESULTS))
            self.assertFalse(tree.exists(NODE_CURVES))

            tree.selection_set(NODE_MESH)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()
            self.assertEqual(window.app_state.selected_item, "model")
            self.assertEqual(window.status_text.get(), "Selected: sample.stl")
            self.assertEqual(tree.selection(), (NODE_MESH,))

            tree.selection_set(section_plane_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()
            self.assertEqual(window.app_state.selected_item, "section_plane")
            self.assertEqual(window.status_text.get(), "Selected: Section Plane")
            self.assertEqual(tree.selection(), (section_plane_node,))

            window._on_viewport_selection("model")
            self.assertEqual(window.app_state.selected_item, "model")
            self.assertEqual(tree.selection(), (NODE_MESH,))

            window._on_viewport_selection("section_plane")
            self.assertEqual(window.app_state.selected_item, "section_plane")
            self.assertEqual(tree.selection(), (section_plane_node,))

            window.compute_section()
            self.assertEqual(
                tree.get_children(NODE_SCENE),
                (
                    NODE_MESH,
                    NODE_SECTION_PLANES,
                    NODE_SECTION_RESULTS,
                    NODE_CURVES,
                ),
            )
            self.assertEqual(tree.get_children(NODE_SECTION_PLANES), (section_plane_node,))

            window.clear_section()
            self.assertEqual(
                tree.get_children(NODE_SCENE),
                (NODE_MESH, NODE_SECTION_PLANES),
            )
            self.assertEqual(tree.get_children(NODE_SECTION_PLANES), (section_plane_node,))
            self.assertFalse(tree.exists(NODE_SECTION_RESULTS))
            self.assertFalse(tree.exists(NODE_CURVES))
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
            window._set_project_dirty(False)
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
            self.assertTrue(window.project_dirty)
            self.assertEqual(window.root.title(), "openRetop - Untitled Project *")
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
            window._set_project_dirty(False)
            reset_count = window.viewport.reset_count
            window._handle_shortcut("Delete")

            self.assertIsNone(window.app_state.mesh_object)
            self.assertEqual(window.status_text.get(), "Selected model removed")
            self.assertTrue(window.project_dirty)
            self.assertEqual(window.root.title(), "openRetop - Untitled Project *")
            self.assertEqual(str(window.select_model_button.cget("state")), "disabled")
            self.assertEqual(str(window.select_section_plane_button.cget("state")), "disabled")
            self.assertEqual(window.viewport.reset_count, reset_count)
            self.assertIsNone(window.viewport.scene_calls[-1]["mesh"])
            self.assertEqual(window.viewport.scene_calls[-1]["reset_camera"], False)
            self.assertIsNone(window.viewport.scene_calls[-1]["selected_item"])
            self.assertEqual(window.scene_browser.tree.get_children(NODE_SCENE), ())
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

    def test_unconstrained_grab_uses_viewport_camera_vectors(self) -> None:
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

            window.viewport.camera_right = np.asarray([0.0, 1.0, 0.0], dtype=float)
            window.viewport.camera_up = np.asarray([0.0, 0.0, 1.0], dtype=float)
            window.select_model()
            start_location = window.app_state.mesh_object.location.copy()
            window._on_viewport_pointer_event("motion", 0, 0)
            window._handle_shortcut("G")

            handled = window._on_viewport_pointer_event("motion", 100, -50)
            moved_location = window.app_state.mesh_object.location.copy()
            delta = moved_location - start_location

            self.assertTrue(handled)
            self.assertAlmostEqual(delta[0], 0.0)
            self.assertGreater(delta[1], 0.0)
            self.assertGreater(delta[2], 0.0)
            self.assertIn("Delta Z:", window.status_text.get())
            window._handle_shortcut("Escape")
            self.assertTrue(np.allclose(window.app_state.mesh_object.location, start_location))
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

            active_plane = window.app_state.section_collection.planes[0]
            self.assertEqual(active_plane.axis, "Z")
            self.assertEqual(active_plane.offset, 0.0)
            self.assertFalse(active_plane.visible)

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
            self.assertEqual(active_plane.offset, 0.5)

            window.section_axis.set("X")
            window._on_section_axis_changed()
            self.assertEqual(active_plane.axis, "X")
            self.assertEqual(active_plane.offset, window.section_offset.get())

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
            self.assertTrue(active_plane.visible)
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
            active_plane = window.app_state.section_collection.planes[0]
            self.assertGreater(moved_offset, start_offset)
            self.assertEqual(window.section_offset_text.get(), f"{moved_offset:.3f}")
            self.assertAlmostEqual(active_plane.offset, moved_offset)
            self.assertIn("Offset Z:", window.status_text.get())

            handled = window._on_viewport_pointer_event("right_release", 50, 0)
            self.assertTrue(handled)
            self.assertEqual(window.status_text.get(), "Transform cancelled")
            self.assertAlmostEqual(window.section_offset.get(), start_offset)
            self.assertAlmostEqual(active_plane.offset, start_offset)

            window._handle_shortcut("G")
            window._handle_shortcut("X")
            self.assertEqual(window.section_axis.get(), "X")
            self.assertEqual(active_plane.axis, "X")
            self.assertEqual(window.status_text.get(), "Move mode - X axis")
            window._on_viewport_pointer_event("motion", 100, 0)
            confirmed_offset = window.section_offset.get()
            handled = window._on_viewport_pointer_event("left_release", 100, 0)
            self.assertTrue(handled)
            self.assertEqual(window.status_text.get(), "Transform confirmed")
            self.assertAlmostEqual(window.section_offset.get(), confirmed_offset)
            self.assertAlmostEqual(active_plane.offset, confirmed_offset)
            self.assertGreater(confirmed_offset, start_offset)

            self.assertEqual(window.section_axis.get(), "X")
            window._handle_shortcut("R")
            self.assertEqual(window.section_axis.get(), "Y")
            self.assertEqual(active_plane.axis, "Y")
            self.assertEqual(window.status_text.get(), "Section plane axis cycled to Y")
        finally:
            window.root.destroy()


if __name__ == "__main__":
    unittest.main()

