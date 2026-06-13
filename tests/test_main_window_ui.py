from __future__ import annotations

import json
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
    COMPUTE_SECTION_PROGRESS_STAGES,
    GENERATED_GEOMETRY_TRANSFORM_WARNING,
    LOAD_PROGRESS_STAGES,
    SURFACE_PREVIEW_PROGRESS_STAGES,
    LoadProgressDialog,
    OPEN_MODEL_MENU_INDEX,
    OpenRetopWindow,
)
from app.scene_browser import (
    NODE_CURVES,
    NODE_CURVE_GROUP_UNASSIGNED,
    NODE_MESH,
    NODE_SCENE,
    NODE_SECTION_PLANES,
    NODE_SECTION_RESULTS,
    NODE_SURFACES,
    curve_group_node_id,
    curve_id_from_node,
    curve_node_id,
    section_result_id_from_node,
    section_plane_node_id,
    section_result_node_id,
    surface_id_from_node,
    surface_node_id,
)
from curves.curve_state import StoredCurve, add_curve
from mesh.loader import LoadedMesh, MeshMetadata
from project.project_data import (
    ProjectCurve,
    ProjectSectionPlane,
    ProjectSurface,
    default_project_data,
)
from project.project_io import load_project, save_project
from settings.settings_data import default_app_settings
from settings.settings_io import load_settings, save_settings
from sections.section_state import SectionPlaneState, add_plane, set_active_plane
from surfaces.surface_state import SurfacePatch, add_surface


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


def _window_is_zoomed(window: OpenRetopWindow) -> bool:
    try:
        return str(window.root.state()) == "zoomed"
    except TclError:
        return False


def _assert_startup_size_or_zoomed(
    test_case: unittest.TestCase,
    window: OpenRetopWindow,
    expected_size: str,
) -> None:
    if _window_is_zoomed(window):
        return
    test_case.assertTrue(window.root.geometry().startswith(expected_size))


def _make_curve_closed(curve: StoredCurve) -> None:
    closed_points = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0],
        ],
        dtype=float,
    )
    curve.original_points = closed_points.copy()
    curve.fitted_points = closed_points.copy()
    curve.is_closed = True


class MainWindowUiTests(unittest.TestCase):
    def test_menu_bar_and_initial_no_selection_context_match_instructions(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            self.assertEqual(window.menu_bar.entrycget(0, "label"), "File")
            self.assertEqual(window.menu_bar.entrycget(1, "label"), "Edit")
            self.assertEqual(window.menu_bar.entrycget(2, "label"), "View")
            self.assertEqual(window.menu_bar.entrycget(3, "label"), "Scene")
            self.assertEqual(window.menu_bar.entrycget(4, "label"), "Sections")
            self.assertEqual(window.menu_bar.entrycget(5, "label"), "Curves")
            self.assertEqual(window.menu_bar.entrycget(6, "label"), "Surfaces")
            self.assertEqual(window.menu_bar.entrycget(7, "label"), "Tools")
            self.assertEqual(window.menu_bar.entrycget(8, "label"), "Help")
            self.assertEqual(window.file_menu.entrycget(0, "label"), "New Project")
            self.assertEqual(window.file_menu.entrycget(1, "label"), "Open Project")
            self.assertEqual(window.file_menu.entrycget(2, "label"), "Save Project")
            self.assertEqual(window.file_menu.entrycget(3, "label"), "Save Project As")
            self.assertEqual(window.file_menu.entrycget(4, "label"), "Open Model")
            self.assertEqual(window.file_menu.entrycget(5, "label"), "Recent Files")
            self.assertEqual(window.file_menu.entrycget(6, "label"), "Exit")
            self.assertEqual(window.edit_menu.entrycget(0, "label"), "Undo")
            self.assertEqual(window.edit_menu.entrycget(1, "label"), "Redo")
            self.assertEqual(window.edit_menu.entrycget(2, "label"), "Rename Selected")
            self.assertEqual(window.edit_menu.entrycget(3, "label"), "Delete Selected")
            self.assertEqual(window.edit_menu.entrycget(4, "label"), "Preferences")
            self.assertEqual(window.view_menu.entrycget(0, "label"), "Frame All")
            self.assertEqual(window.view_menu.entrycget(1, "label"), "Frame Selected")
            self.assertEqual(window.view_menu.entrycget(2, "label"), "Reset View")
            self.assertEqual(window.view_menu.entrycget(3, "label"), "Show Grid")
            self.assertEqual(window.view_menu.entrycget(4, "label"), "Show Axes")
            self.assertEqual(window.view_menu.entrycget(5, "label"), "Show All Objects")
            self.assertEqual(window.view_menu.entrycget(6, "label"), "Isolate Selected")
            self.assertEqual(window.view_menu.entrycget(7, "label"), "Toggle Selected Visibility")
            self.assertEqual(window.view_menu.index("end"), 7)
            self.assertEqual(window.view_menu.type(3), "checkbutton")
            self.assertEqual(window.view_menu.type(4), "checkbutton")
            self.assertEqual(window.scene_menu.entrycget(0, "label"), "Rename Selected")
            self.assertEqual(window.scene_menu.entrycget(1, "label"), "Delete Selected")
            self.assertEqual(window.scene_menu.entrycget(2, "label"), "Toggle Visibility")
            self.assertEqual(window.sections_menu.entrycget(0, "label"), "Add Section Plane")
            self.assertEqual(window.sections_menu.entrycget(2, "label"), "Compute Section")
            self.assertEqual(window.curves_menu.entrycget(0, "label"), "Create Surface From Selected Curves")
            self.assertEqual(window.surfaces_menu.entrycget(0, "label"), "Create Surface From Selected Curves")
            self.assertEqual(window.tools_menu.entrycget(0, "label"), "Select Model")
            self.assertEqual(window.tools_menu.entrycget(1, "label"), "Select Section Plane")
            self.assertEqual(window.tools_menu.entrycget(2, "label"), "Move")
            self.assertEqual(window.tools_menu.entrycget(3, "label"), "Rotate")
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
            self.assertEqual(
                [window.sidebar_notebook.tab(index, "text") for index in range(window.sidebar_notebook.index("end"))],
                ["Object", "Transform", "Sections", "Curves", "Surfaces", "Info"],
            )
            self.assertEqual(window.no_selection_frame.winfo_manager(), "grid")
            self.assertEqual(window.model_context_frame.winfo_manager(), "")
            self.assertEqual(window.section_context_frame.winfo_manager(), "")
            self.assertEqual(window.curve_context_frame.winfo_manager(), "")
            self.assertEqual(window.surface_context_frame.winfo_manager(), "")
            self.assertFalse(hasattr(window, "apply_transform_button"))
            self.assertEqual(str(window.select_model_button.cget("state")), "disabled")
            self.assertEqual(str(window.select_section_plane_button.cget("state")), "disabled")
            self.assertEqual(window.compute_section_button.cget("text"), "Compute Section")
            self.assertEqual(window.clear_section_button.cget("text"), "Clear Active Section Result")
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

            window.edit_menu.invoke(4)
            window.root.update()
            dialog = window.preferences_dialog
            self.assertIsNotNone(dialog)
            assert dialog is not None

            self.assertEqual(dialog.title(), "Preferences")
            self.assertIsNotNone(window.preferences_notebook)
            assert window.preferences_notebook is not None
            self.assertEqual(
                [
                    window.preferences_notebook.tab(index, "text")
                    for index in range(window.preferences_notebook.index("end"))
                ],
                ["General", "Viewport", "Keybinds", "Advanced"],
            )
            self.assertEqual(window.preferences_vars["window_mode"].get(), "maximized")
            self.assertTrue(window.preferences_vars["remember_window_size"].get())
            self.assertFalse(window.preferences_vars["show_grid"].get())
            self.assertFalse(window.preferences_vars["show_axes"].get())
            self.assertNotIn("show_normals", window.preferences_vars)
            self.assertEqual(window.preferences_vars["default_proxy_quality"].get(), "High")
            self.assertTrue(_widgets_with_text(dialog, "Startup window mode"))
            self.assertTrue(_widgets_with_text(dialog, "Remember last window size"))
            self.assertTrue(_widgets_with_text(dialog, "Startup Show Grid"))
            self.assertTrue(_widgets_with_text(dialog, "Startup Show Axes"))
            self.assertTrue(_widgets_with_text(dialog, "Surface preview opacity"))
            self.assertTrue(_widgets_with_text(dialog, "Curve display thickness"))
            self.assertTrue(_widgets_with_text(dialog, "Rename Selected"))
            self.assertTrue(_widgets_with_text(dialog, "Toggle Visibility"))
            self.assertTrue(_widgets_with_text(dialog, "Delete Selected"))
            self.assertEqual(window.preferences_vars["keybind.rename_selected"].get(), "F2")
            self.assertEqual(window.preferences_vars["keybind.toggle_visibility"].get(), "H")
            self.assertEqual(window.preferences_vars["keybind.isolate_selected"].get(), "Shift+H")
            self.assertFalse(_widgets_with_text(dialog, "Startup Show Normals"))
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
            self.assertEqual(len(comboboxes), 2)
            self.assertIn(("Low", "Medium", "High"), [tuple(box.cget("values")) for box in comboboxes])

            existing_dialog = window.preferences_dialog
            window.edit_menu.invoke(4)
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
                window.edit_menu.invoke(4)
                dialog = window.preferences_dialog
                self.assertIsNotNone(dialog)
                assert dialog is not None

                scene_call_count = len(window.viewport.scene_calls)
                window.preferences_vars["show_grid"].set(False)
                window.preferences_vars["show_axes"].set(False)
                window.preferences_vars["window_mode"].set("remembered_size")
                window.preferences_vars["remember_window_size"].set(False)
                window.preferences_vars["keybind.toggle_visibility"].set("V")
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
                self.assertFalse(window.settings.display.show_normals)
                self.assertEqual(
                    window.settings.import_settings.default_proxy_quality,
                    "Low",
                )
                self.assertEqual(window.settings.ui.window_mode, "remembered_size")
                self.assertFalse(window.settings.ui.remember_window_size)
                self.assertEqual(window.settings.keybinds.toggle_visibility, "V")

                saved_settings = load_settings(settings_path)
                self.assertFalse(saved_settings.display.show_grid)
                self.assertFalse(saved_settings.display.show_axes)
                self.assertFalse(saved_settings.display.show_normals)
                self.assertEqual(
                    saved_settings.import_settings.default_proxy_quality,
                    "Low",
                )
                self.assertEqual(saved_settings.ui.window_mode, "remembered_size")
                self.assertFalse(saved_settings.ui.remember_window_size)
                self.assertEqual(saved_settings.keybinds.toggle_visibility, "V")
            finally:
                if window.preferences_dialog is not None:
                    window._close_preferences_dialog()
                window.root.destroy()

            with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
                restored_window = _create_window(settings_path=settings_path)

            try:
                self.assertFalse(restored_window.show_grid.get())
                self.assertFalse(restored_window.show_axes.get())
                self.assertFalse(restored_window.show_normals.get())
                self.assertEqual(restored_window.proxy_quality.get(), "Low")
            finally:
                restored_window.root.destroy()

    def test_preferences_rejects_empty_keybinds(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"
            with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
                window = _create_window(settings_path=settings_path)

            try:
                window.edit_menu.invoke(4)
                dialog = window.preferences_dialog
                self.assertIsNotNone(dialog)
                assert dialog is not None

                window.preferences_vars["keybind.toggle_visibility"].set(" ")
                _button_by_text(dialog, "Apply").invoke()

                self.assertEqual(
                    window.status_text.get(),
                    "Toggle Visibility keybind cannot be empty",
                )
                self.assertEqual(window.settings.keybinds.toggle_visibility, "H")
                self.assertEqual(load_settings(settings_path).keybinds.toggle_visibility, "H")

                _button_by_text(dialog, "OK").invoke()
                self.assertIsNotNone(window.preferences_dialog)
            finally:
                if window.preferences_dialog is not None:
                    window._close_preferences_dialog()
                window.root.destroy()

    def test_preferences_ok_applies_and_closes_dialog(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"
            with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
                window = _create_window(settings_path=settings_path)

            try:
                window.edit_menu.invoke(4)
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
                window.edit_menu.invoke(4)
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
                self.assertFalse(window.show_normals.get())
                self.assertEqual(window.proxy_quality.get(), "High")
                _assert_startup_size_or_zoomed(self, window, "1120x720")
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
                _assert_startup_size_or_zoomed(self, window, "1280x800")
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
            if _window_is_zoomed(window):
                window.root.state("normal")
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
                _assert_startup_size_or_zoomed(self, restored_window, "1180x740")
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
                    window.file_menu.invoke(1)

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
                self.assertFalse(window.show_normals.get())
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
                    window.file_menu.invoke(1)

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
                self.assertFalse(window.show_normals.get())
                self.assertTrue(window.show_section_plane.get())
                self.assertEqual(window.section_axis.get(), "X")
                self.assertEqual(window.section_offset.get(), 0.5)
                self.assertEqual(window.section_offset_text.get(), "0.500")
                self.assertEqual(window.section_plane_text.get(), "Section: X = 0.500")
                scene = window.viewport.scene_calls[-1]
                self.assertEqual(scene["show_grid"], False)
                self.assertEqual(scene["show_axes"], False)
                self.assertEqual(scene["show_normals"], False)
                self.assertEqual(scene["show_section_plane"], True)
                self.assertEqual(scene["section_axis"], "X")
                self.assertEqual(scene["section_offset"], 0.5)
                self.assertEqual(scene["mesh"], window.app_state.mesh_object.display_mesh)
                self.assertIsNotNone(scene["transform_matrix"])
        finally:
            window.root.destroy()

    def test_open_legacy_project_without_section_planes_restores_single_plane(self) -> None:
        mesh = FakeMesh()

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        class RecordingProgressDialog:
            def __init__(self, _parent: object, _file_name: str) -> None:
                self.closed = False

            def update_stage(self, _stage: str) -> None:
                return None

            def close(self) -> None:
                self.closed = True

        try:
            with TemporaryDirectory() as tmpdir:
                mesh_path = Path(tmpdir) / "sample.stl"
                project_path = Path(tmpdir) / "legacy.openretop"
                project_path.write_text(
                    json.dumps(
                        {
                            "version": 1,
                            "name": "Legacy Section",
                            "mesh_path": str(mesh_path),
                            "section": {
                                "axis": "Y",
                                "offset": 1.25,
                                "show_plane": True,
                            },
                        }
                    ),
                    encoding="utf-8",
                )
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

                with (
                    patch("app.main_window.LoadProgressDialog", RecordingProgressDialog),
                    patch(
                        "app.main_window.filedialog.askopenfilename",
                        return_value=str(project_path),
                    ),
                    patch(
                        "app.main_window.load_mesh",
                        return_value=LoadedMesh(mesh=mesh, metadata=metadata),
                    ),
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(1)

                show_error.assert_not_called()
                planes = window.app_state.section_collection.planes
                self.assertEqual(len(planes), 1)
                legacy_plane = planes[0]
                self.assertEqual(legacy_plane.name, "Section Plane 1")
                self.assertEqual(legacy_plane.axis, "Y")
                self.assertEqual(legacy_plane.offset, 1.25)
                self.assertTrue(legacy_plane.visible)
                self.assertTrue(legacy_plane.selected)
                self.assertEqual(window.app_state.section_collection.active_plane_id, legacy_plane.id)
                self.assertEqual(window.section_axis.get(), "Y")
                self.assertEqual(window.section_offset.get(), 1.25)
                self.assertTrue(window.show_section_plane.get())

                tree = window.scene_browser.tree
                legacy_node = section_plane_node_id(legacy_plane.id)
                self.assertEqual(tree.get_children(NODE_SECTION_PLANES), (legacy_node,))
                self.assertEqual(tree.item(legacy_node, "text"), "[V] Section Plane 1")
                self.assertEqual(window.viewport.scene_calls[-1]["section_planes"], planes)
                self.assertEqual(
                    window.viewport.scene_calls[-1]["active_section_plane_id"],
                    legacy_plane.id,
                )
        finally:
            window.root.destroy()

    def test_open_project_with_empty_section_planes_uses_legacy_section_fallback(self) -> None:
        mesh = FakeMesh()

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        class RecordingProgressDialog:
            def __init__(self, _parent: object, _file_name: str) -> None:
                return None

            def update_stage(self, _stage: str) -> None:
                return None

            def close(self) -> None:
                return None

        try:
            with TemporaryDirectory() as tmpdir:
                mesh_path = Path(tmpdir) / "sample.stl"
                project_path = Path(tmpdir) / "empty-planes.openretop"
                project = default_project_data()
                project.name = "Empty Planes"
                project.mesh_path = str(mesh_path)
                project.section.axis = "X"
                project.section.offset = 0.75
                project.section.show_plane = True
                project.section_planes = []
                project.active_section_plane_id = "missing-plane"
                save_project(project, project_path)
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

                with (
                    patch("app.main_window.LoadProgressDialog", RecordingProgressDialog),
                    patch(
                        "app.main_window.filedialog.askopenfilename",
                        return_value=str(project_path),
                    ),
                    patch(
                        "app.main_window.load_mesh",
                        return_value=LoadedMesh(mesh=mesh, metadata=metadata),
                    ),
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(1)

                show_error.assert_not_called()
                planes = window.app_state.section_collection.planes
                self.assertEqual(len(planes), 1)
                fallback_plane = planes[0]
                self.assertEqual(fallback_plane.name, "Section Plane 1")
                self.assertEqual(fallback_plane.axis, "X")
                self.assertEqual(fallback_plane.offset, 0.75)
                self.assertTrue(fallback_plane.visible)
                self.assertTrue(fallback_plane.selected)
                self.assertEqual(window.app_state.section_collection.active_plane_id, fallback_plane.id)
                self.assertEqual(window.section_axis.get(), "X")
                self.assertEqual(window.section_offset.get(), 0.75)
                self.assertTrue(window.show_section_plane.get())
        finally:
            window.root.destroy()

    def test_open_project_with_invalid_active_section_plane_selects_first_plane(self) -> None:
        mesh = FakeMesh()

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        class RecordingProgressDialog:
            def __init__(self, _parent: object, _file_name: str) -> None:
                return None

            def update_stage(self, _stage: str) -> None:
                return None

            def close(self) -> None:
                return None

        try:
            with TemporaryDirectory() as tmpdir:
                mesh_path = Path(tmpdir) / "sample.stl"
                project_path = Path(tmpdir) / "invalid-active.openretop"
                project = default_project_data()
                project.name = "Invalid Active"
                project.mesh_path = str(mesh_path)
                project.section_planes = [
                    ProjectSectionPlane(
                        id="plane-a",
                        name="",
                        axis="Z",
                        offset=0.25,
                        visible=True,
                    ),
                    ProjectSectionPlane(
                        id="plane-b",
                        name="Section Plane 1",
                        axis="X",
                        offset=0.5,
                        visible=False,
                    ),
                    ProjectSectionPlane(
                        id="plane-c",
                        name="Custom",
                        axis="Y",
                        offset=0.75,
                        visible=True,
                    ),
                    ProjectSectionPlane(
                        id="plane-d",
                        name="Custom",
                        axis="Y",
                        offset=1.0,
                        visible=True,
                    ),
                ]
                project.active_section_plane_id = "missing-plane"
                save_project(project, project_path)
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

                with (
                    patch("app.main_window.LoadProgressDialog", RecordingProgressDialog),
                    patch(
                        "app.main_window.filedialog.askopenfilename",
                        return_value=str(project_path),
                    ),
                    patch(
                        "app.main_window.load_mesh",
                        return_value=LoadedMesh(mesh=mesh, metadata=metadata),
                    ),
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(1)

                show_error.assert_not_called()
                planes = window.app_state.section_collection.planes
                self.assertEqual([plane.id for plane in planes], ["plane-a", "plane-b", "plane-c", "plane-d"])
                self.assertEqual(
                    [plane.name for plane in planes],
                    ["Section Plane 1", "Section Plane 2", "Custom", "Custom 2"],
                )
                self.assertEqual(window.app_state.section_collection.active_plane_id, "plane-a")
                self.assertTrue(planes[0].selected)
                self.assertFalse(planes[1].selected)
                self.assertEqual(window.section_axis.get(), "Z")
                self.assertEqual(window.section_offset.get(), 0.25)
                self.assertTrue(window.show_section_plane.get())

                tree = window.scene_browser.tree
                nodes = tuple(section_plane_node_id(plane.id) for plane in planes)
                self.assertEqual(tree.get_children(NODE_SECTION_PLANES), nodes)
                self.assertEqual(tree.item(nodes[0], "text"), "[V] Section Plane 1")
                self.assertEqual(tree.item(nodes[1], "text"), "[H] Section Plane 2")
                self.assertEqual(tree.item(nodes[2], "text"), "[V] Custom")
                self.assertEqual(tree.item(nodes[3], "text"), "[V] Custom 2")
                self.assertEqual(window.viewport.scene_calls[-1]["active_section_plane_id"], "plane-a")

                window.select_section_plane()
                self.assertEqual(tree.selection(), (nodes[0],))
        finally:
            window.root.destroy()

    def test_open_project_restores_saved_section_planes(self) -> None:
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
                project_path = Path(tmpdir) / "planes.openretop"
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
                project.name = "Restored Section Planes"
                project.mesh_path = str(mesh_path)
                project.section.axis = "Y"
                project.section.offset = 1.25
                project.section.show_plane = True
                project.section_planes = [
                    ProjectSectionPlane(
                        id="plane-a",
                        name="Base Section",
                        axis="Z",
                        offset=0.25,
                        visible=True,
                    ),
                    ProjectSectionPlane(
                        id="plane-b",
                        name="Side Section",
                        axis="X",
                        offset=0.5,
                        visible=False,
                    ),
                ]
                project.active_section_plane_id = "plane-b"
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
                    ),
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(1)

                show_error.assert_not_called()
                planes = window.app_state.section_collection.planes
                self.assertEqual(len(planes), 2)
                self.assertEqual([plane.id for plane in planes], ["plane-a", "plane-b"])
                self.assertEqual([plane.name for plane in planes], ["Base Section", "Side Section"])
                self.assertEqual([plane.axis for plane in planes], ["Z", "X"])
                self.assertEqual([plane.offset for plane in planes], [0.25, 0.5])
                self.assertEqual([plane.visible for plane in planes], [True, False])
                self.assertFalse(planes[0].selected)
                self.assertTrue(planes[1].selected)
                self.assertEqual(window.app_state.section_collection.active_plane_id, "plane-b")
                self.assertEqual(window.app_state.section_collection.results, [])
                self.assertIsNone(window.app_state.section_result)
                self.assertEqual(window.section_axis.get(), "X")
                self.assertEqual(window.section_offset.get(), 0.5)
                self.assertEqual(window.section_offset_text.get(), "0.500")
                self.assertFalse(window.show_section_plane.get())
                self.assertEqual(window.section_plane_text.get(), "Section: X = 0.500")

                tree = window.scene_browser.tree
                first_node = section_plane_node_id("plane-a")
                second_node = section_plane_node_id("plane-b")
                self.assertEqual(tree.get_children(NODE_SECTION_PLANES), (first_node, second_node))
                self.assertEqual(tree.item(first_node, "text"), "[V] Base Section")
                self.assertEqual(tree.item(second_node, "text"), "[H] Side Section")

                scene = window.viewport.scene_calls[-1]
                self.assertEqual(scene["section_planes"], planes)
                self.assertEqual(scene["active_section_plane_id"], "plane-b")
                self.assertTrue(scene["show_section_plane"])
                self.assertEqual(scene["section_axis"], "X")
                self.assertEqual(scene["section_offset"], 0.5)
        finally:
            window.root.destroy()

    def test_open_project_restores_saved_curves_and_visibility(self) -> None:
        mesh = FakeMesh()

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        class RecordingProgressDialog:
            def __init__(self, _parent: object, _file_name: str) -> None:
                return None

            def update_stage(self, _stage: str) -> None:
                return None

            def close(self) -> None:
                return None

        try:
            with TemporaryDirectory() as tmpdir:
                mesh_path = Path(tmpdir) / "sample.stl"
                project_path = Path(tmpdir) / "curves.openretop"
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
                project.name = "Restored Curves"
                project.mesh_path = str(mesh_path)
                project.section_planes = [
                    ProjectSectionPlane(
                        id="plane-a",
                        name="Base Section",
                        axis="Z",
                        offset=0.0,
                        visible=True,
                    ),
                    ProjectSectionPlane(
                        id="plane-b",
                        name="Side Section",
                        axis="X",
                        offset=0.5,
                        visible=True,
                    ),
                ]
                project.active_section_plane_id = "plane-a"
                project.curves = [
                    ProjectCurve(
                        id="curve-a",
                        name="Section 1 Curve 1",
                        section_result_id="section-a",
                        plane_id="plane-a",
                        original_points=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                        fitted_points=[
                            [0.0, 0.0, 0.0],
                            [0.5, 0.25, 0.0],
                            [1.0, 0.0, 0.0],
                        ],
                        mean_error=0.05,
                        max_error=0.1,
                        is_closed=False,
                        visible=True,
                    ),
                    ProjectCurve(
                        id="curve-b",
                        name="Section 2 Curve 1",
                        section_result_id="section-b",
                        plane_id="plane-b",
                        original_points=[[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]],
                        fitted_points=[[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]],
                        mean_error=0.0,
                        max_error=0.0,
                        is_closed=False,
                        visible=False,
                    ),
                ]
                project.surfaces = [
                    ProjectSurface(
                        id="surface-a",
                        name="Surface 1",
                        source_curve_ids=["curve-a", "curve-b"],
                        surface_type="placeholder",
                        visible=True,
                        metadata={"curve_count": 2, "source": "visible_curves"},
                    ),
                    ProjectSurface(
                        id="surface-b",
                        name="Missing Curve Surface",
                        source_curve_ids=["missing-curve"],
                        surface_type="placeholder",
                        visible=False,
                        metadata={"curve_count": 1, "source": "selected_curve"},
                    ),
                ]
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
                    ),
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(1)

                show_error.assert_not_called()
                curves = window.app_state.curve_collection.curves
                self.assertEqual([curve.id for curve in curves], ["curve-a", "curve-b"])
                self.assertEqual([curve.visible for curve in curves], [True, False])
                self.assertIsNone(window.app_state.curve_collection.active_curve_id)
                self.assertEqual(window.app_state.curve_results, [curves[0]])
                self.assertEqual(window.viewport.scene_calls[-1]["curve_results"], [curves[0]])
                surfaces = window.app_state.surface_collection.surfaces
                self.assertEqual([surface.id for surface in surfaces], ["surface-a", "surface-b"])
                self.assertEqual([surface.visible for surface in surfaces], [True, False])
                self.assertIsNone(window.app_state.surface_collection.active_surface_id)
                self.assertEqual(surfaces[0].metadata["curve_count"], 2)
                self.assertEqual(surfaces[1].metadata["missing_curve_ids"], ["missing-curve"])

                tree = window.scene_browser.tree
                first_curve_node = curve_node_id("curve-a")
                second_curve_node = curve_node_id("curve-b")
                self.assertEqual(
                    tree.get_children(NODE_CURVES),
                    (NODE_CURVE_GROUP_UNASSIGNED,),
                )
                self.assertEqual(
                    tree.get_children(NODE_CURVE_GROUP_UNASSIGNED),
                    (first_curve_node, second_curve_node),
                )
                self.assertEqual(tree.item(first_curve_node, "text"), "[V] Section 1 Curve 1")
                self.assertEqual(tree.item(second_curve_node, "text"), "[H] Section 2 Curve 1")
                self.assertEqual(tree.selection(), ())
                first_surface_node = surface_node_id("surface-a")
                second_surface_node = surface_node_id("surface-b")
                self.assertEqual(
                    tree.get_children(NODE_SURFACES),
                    (first_surface_node, second_surface_node),
                )
                self.assertEqual(tree.item(first_surface_node, "text"), "[V] Surface 1")
                self.assertEqual(tree.item(second_surface_node, "text"), "[H] Missing Curve Surface")

                tree.selection_set(second_curve_node)
                tree.event_generate("<<TreeviewSelect>>")
                window.root.update()
                window.curve_visible.set(True)
                window._on_curve_visibility_changed()

                self.assertTrue(curves[1].visible)
                self.assertEqual(window.app_state.curve_results, curves)
                self.assertEqual(window.viewport.scene_calls[-1]["curve_results"], curves)

                tree.selection_set(second_surface_node)
                tree.event_generate("<<TreeviewSelect>>")
                window.root.update()
                self.assertEqual(window.app_state.selected_item, "surface")
                self.assertEqual(window.surface_name_text.get(), "Missing Curve Surface")
                self.assertEqual(window.surface_type_text.get(), "placeholder")
                self.assertEqual(window.surface_source_curve_count_text.get(), "1")
                self.assertFalse(window.surface_visible.get())
                self.assertIn("missing_curve_ids=['missing-curve']", window.surface_metadata_text.get())
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
                    window.file_menu.invoke(1)

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
                    window.file_menu.invoke(1)

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
                    window.file_menu.invoke(2)

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
                self.assertEqual(len(project.section_planes), 1)
                section_plane = project.section_planes[0]
                self.assertEqual(section_plane.name, "Section Plane 1")
                self.assertEqual(section_plane.axis, "Z")
                self.assertEqual(section_plane.offset, 0.0)
                self.assertFalse(section_plane.visible)
                self.assertEqual(project.active_section_plane_id, section_plane.id)
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
                    window.file_menu.invoke(2)

                ask_save.assert_not_called()
                show_error.assert_not_called()
                self.assertEqual(window.current_project_path, project_path)
                self.assertFalse(window.project_dirty)
                self.assertEqual(window.root.title(), "openRetop - current.openretop")
                self.assertEqual(window.status_text.get(), f"Project saved: {project_path}")
                self.assertFalse(load_project(project_path).display.show_grid)
        finally:
            window.root.destroy()

    def test_save_project_writes_multiple_section_planes_from_collection(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            first_plane = window.app_state.section_collection.planes[0]
            first_plane.name = "Base Section"
            first_plane.axis = "Z"
            first_plane.offset = 0.25
            first_plane.visible = True
            second_plane = SectionPlaneState(
                id="plane-b",
                name="Side Section",
                axis="X",
                offset=-0.5,
                visible=False,
            )
            add_plane(window.app_state.section_collection, second_plane)
            set_active_plane(window.app_state.section_collection, second_plane.id)
            window._sync_section_controls_from_active_plane()

            with TemporaryDirectory() as tmpdir:
                project_path = Path(tmpdir) / "planes.openretop"

                with (
                    patch(
                        "app.main_window.filedialog.asksaveasfilename",
                        return_value=str(project_path),
                    ),
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(2)

                show_error.assert_not_called()
                project = load_project(project_path)
                self.assertEqual(len(project.section_planes), 2)
                self.assertEqual(project.section_planes[0].id, first_plane.id)
                self.assertEqual(project.section_planes[0].name, "Base Section")
                self.assertEqual(project.section_planes[0].axis, "Z")
                self.assertEqual(project.section_planes[0].offset, 0.25)
                self.assertTrue(project.section_planes[0].visible)
                self.assertEqual(project.section_planes[1].id, "plane-b")
                self.assertEqual(project.section_planes[1].name, "Side Section")
                self.assertEqual(project.section_planes[1].axis, "X")
                self.assertEqual(project.section_planes[1].offset, -0.5)
                self.assertFalse(project.section_planes[1].visible)
                self.assertEqual(project.active_section_plane_id, "plane-b")
        finally:
            window.root.destroy()

    def test_save_project_preserves_curve_names_and_visibility(self) -> None:
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

            window.compute_section()
            first_curve = window.app_state.curve_collection.curves[0]
            window.add_section_plane()
            window.section_axis.set("X")
            window._on_section_axis_changed()
            window._set_section_offset(0.5, clamp=True, refresh=True)
            window.compute_section()
            second_curve = window.app_state.curve_collection.curves[1]

            window.select_curve(first_curve.id)
            window.curve_name_text.set("Rim Curve")
            window._on_curve_name_changed()
            window.select_curve(second_curve.id)
            window.curve_visible.set(False)
            window._on_curve_visibility_changed()

            with TemporaryDirectory() as tmpdir:
                project_path = Path(tmpdir) / "curves.openretop"

                with (
                    patch(
                        "app.main_window.filedialog.asksaveasfilename",
                        return_value=str(project_path),
                    ),
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(2)

                show_error.assert_not_called()
                project = load_project(project_path)
                self.assertEqual([curve.id for curve in project.curves], [first_curve.id, second_curve.id])
                self.assertEqual([curve.name for curve in project.curves], ["Rim Curve", "Section 2 Curve 1"])
                self.assertEqual([curve.visible for curve in project.curves], [True, False])
                self.assertEqual(project.curves[0].section_result_id, first_curve.section_result_id)
                self.assertEqual(project.curves[1].plane_id, second_curve.plane_id)
        finally:
            window.root.destroy()

    def test_save_project_preserves_surface_records(self) -> None:
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

            window.compute_section()
            source_curve = window.app_state.curve_collection.curves[0]
            _make_curve_closed(source_curve)
            window.select_curve(source_curve.id)
            window.create_surface_from_curves()
            surface = window.app_state.surface_collection.surfaces[0]
            window.surface_visible.set(False)
            window._on_surface_visibility_changed()

            with TemporaryDirectory() as tmpdir:
                project_path = Path(tmpdir) / "surfaces.openretop"

                with (
                    patch(
                        "app.main_window.filedialog.asksaveasfilename",
                        return_value=str(project_path),
                    ),
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(2)

                show_error.assert_not_called()
                project = load_project(project_path)
                self.assertEqual(len(project.surfaces), 1)
                project_surface = project.surfaces[0]
                self.assertEqual(project_surface.id, surface.id)
                self.assertEqual(project_surface.name, "Surface 1")
                self.assertEqual(project_surface.source_curve_ids, [source_curve.id])
                self.assertEqual(project_surface.surface_type, "preview_fill")
                self.assertFalse(project_surface.visible)
                self.assertEqual(project_surface.metadata["curve_count"], 1)
                self.assertEqual(project_surface.metadata["source_curve_count"], 1)
                self.assertEqual(project_surface.metadata["source"], "selected_curve")
                self.assertEqual(
                    project_surface.metadata["preview_mode"],
                    "closed_curve_fill",
                )
                self.assertTrue(project_surface.metadata["preview_available"])
                self.assertEqual(
                    project_surface.metadata["preview_reason"],
                    "fan fill preview generated",
                )
                self.assertEqual(
                    project_surface.metadata["preview_warning"],
                    "Fan fill preview may be inaccurate for concave curves",
                )
        finally:
            window.root.destroy()

    def test_save_project_preserves_global_renames_and_mesh_visibility(self) -> None:
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
            window.mesh_name_text.set("Scan Body")
            window._on_mesh_name_changed()
            window.mesh_visible.set(False)
            window._on_mesh_visibility_changed()
            active_plane = window.app_state.section_collection.planes[0]
            window.select_section_plane(active_plane.id)
            window.section_plane_name_text.set("Cut Plane")
            window._on_section_plane_name_changed()
            window.compute_section()
            stored_result = window.app_state.section_collection.results[0]
            source_curve = window.app_state.curve_collection.curves[0]
            window.select_section_result(stored_result.id)
            window.section_result_name_text.set("Rim Section")
            window._on_section_result_name_changed()
            window.select_curve(source_curve.id)
            window.curve_name_text.set("Rim Curve")
            window._on_curve_name_changed()
            _make_curve_closed(source_curve)
            window.create_surface_from_curves()
            surface = window.app_state.surface_collection.surfaces[0]
            window.surface_name_text.set("Preview Surface")
            window._on_surface_name_changed()

            with TemporaryDirectory() as tmpdir:
                project_path = Path(tmpdir) / "renamed.openretop"

                with (
                    patch(
                        "app.main_window.filedialog.asksaveasfilename",
                        return_value=str(project_path),
                    ),
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(2)

                show_error.assert_not_called()
                project = load_project(project_path)
                self.assertEqual(project.mesh_path, str(metadata.file_path))
                self.assertEqual(project.mesh_name, "Scan Body")
                self.assertFalse(project.mesh_visible)
                self.assertEqual(project.section_planes[0].name, "Cut Plane")
                self.assertEqual(project.section_results[0].name, "Rim Section")
                self.assertEqual(project.section_results[0].id, stored_result.id)
                self.assertEqual(project.curves[0].name, "Rim Curve")
                self.assertEqual(project.surfaces[0].name, "Preview Surface")
                self.assertEqual(project.surfaces[0].id, surface.id)
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
                    window.file_menu.invoke(3)

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
                self.assertFalse(project.display.show_normals)
                self.assertEqual(project.section.axis, "X")
                self.assertEqual(project.section.offset, 0.5)
                self.assertTrue(project.section.show_plane)
                self.assertEqual(len(project.section_planes), 1)
                section_plane = project.section_planes[0]
                self.assertEqual(section_plane.name, "Section Plane 1")
                self.assertEqual(section_plane.axis, "X")
                self.assertEqual(section_plane.offset, 0.5)
                self.assertTrue(section_plane.visible)
                self.assertEqual(project.active_section_plane_id, section_plane.id)
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
                window.file_menu.invoke(2)

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
            self.assertEqual(window.status_text.get(), "No selection")
            window.sections_menu.invoke(0)
            self.assertEqual(window.status_text.get(), "No selection")
            window.sections_menu.invoke(2)
            self.assertEqual(window.status_text.get(), "No selection")
            window.sections_menu.invoke(3)
            self.assertEqual(window.status_text.get(), "Section cleared")
            window.sections_menu.invoke(4)
            self.assertEqual(window.status_text.get(), "All section results cleared")
            window.sections_menu.invoke(1)
            self.assertEqual(window.status_text.get(), "No selection")
            window.curves_menu.invoke(1)
            self.assertEqual(window.status_text.get(), "No selected curves")
            window.curves_menu.invoke(2)
            self.assertEqual(window.status_text.get(), "No selected curves")
            window.curves_menu.invoke(3)
            self.assertEqual(window.status_text.get(), "No curves available")
            window.curves_menu.invoke(0)
            self.assertEqual(window.status_text.get(), "No curves available")
            window.surfaces_menu.invoke(0)
            self.assertEqual(window.status_text.get(), "No curves available")
        finally:
            window.root.destroy()

    def test_loading_progress_dialog_contains_visible_indeterminate_progressbar(self) -> None:
        try:
            root = Tk()
        except TclError as exc:
            raise unittest.SkipTest(f"Tk is unavailable: {exc}") from exc

        dialog: LoadProgressDialog | None = None
        try:
            root.geometry("800x600+120+80")
            root.update_idletasks()
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
            expected_x = root.winfo_rootx() + (root.winfo_width() - dialog.window.winfo_width()) // 2
            expected_y = root.winfo_rooty() + (root.winfo_height() - dialog.window.winfo_height()) // 2
            self.assertLessEqual(abs(dialog.window.winfo_rootx() - expected_x), 32)
            self.assertLessEqual(abs(dialog.window.winfo_rooty() - expected_y), 32)
        finally:
            if dialog is not None:
                dialog.close()
            root.destroy()

    def test_compute_section_shows_progress_dialog_stages(self) -> None:
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

        progress_dialogs: list[object] = []

        class RecordingProgressDialog:
            def __init__(self, _parent: object, title: str, summary: str | None = None) -> None:
                self.title = title
                self.summary = summary
                self.stages: list[str] = []
                self.closed = False
                progress_dialogs.append(self)

            def update_stage(self, stage: str) -> None:
                self.stages.append(stage)

            def close(self) -> None:
                self.closed = True

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            with patch("app.main_window.ComputationProgressDialog", RecordingProgressDialog):
                window.compute_section()

            self.assertEqual(len(progress_dialogs), 1)
            progress = progress_dialogs[0]
            self.assertEqual(progress.title, "Computing Section")
            self.assertEqual(progress.stages, list(COMPUTE_SECTION_PROGRESS_STAGES))
            self.assertTrue(progress.closed)
            self.assertTrue(window.app_state.section_collection.results)
            self.assertEqual(window.status_text.get(), "Section computed: Section 1 - 1 segments")
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
            self.assertEqual(scene["section_planes"], window.app_state.section_collection.planes)
            self.assertEqual(
                scene["active_section_plane_id"],
                window.app_state.section_collection.active_plane_id,
            )
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
            self.assertEqual(tree.item(NODE_MESH, "text"), "[V] sample.stl")
            self.assertEqual(tree.item(NODE_SECTION_PLANES, "text"), "Section Planes")
            self.assertEqual(tree.get_children(NODE_SECTION_PLANES), (section_plane_node,))
            self.assertEqual(tree.item(section_plane_node, "text"), "[H] Section Plane 1")
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
            stored_result = window.app_state.section_collection.results[0]
            stored_curve = window.app_state.curve_collection.curves[0]
            section_result_node = section_result_node_id(stored_result.id)
            section_curve_group = curve_group_node_id(stored_result.id)
            curve_node = curve_node_id(stored_curve.id)
            self.assertEqual(section_result_id_from_node(section_result_node), stored_result.id)
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
            self.assertEqual(tree.get_children(NODE_SECTION_RESULTS), (section_result_node,))
            self.assertEqual(tree.item(section_result_node, "text"), "[V] Section 1")
            self.assertEqual(tree.get_children(NODE_CURVES), (section_curve_group,))
            self.assertEqual(tree.item(section_curve_group, "text"), "Section 1")
            self.assertEqual(tree.get_children(section_curve_group), (curve_node,))
            self.assertEqual(tree.item(curve_node, "text"), "[V] Section 1 Curve 1")

            tree.selection_set(section_result_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()
            self.assertEqual(window.app_state.selected_item, "section_result")
            self.assertEqual(window.app_state.section_collection.active_result_id, stored_result.id)
            self.assertEqual(window.section_result_context_frame.winfo_manager(), "grid")
            self.assertEqual(window.section_result_name_text.get(), "Section 1")
            self.assertEqual(window.section_result_axis_text.get(), "Z")
            self.assertEqual(window.section_result_offset_text.get(), "0.000")
            self.assertEqual(window.section_result_segment_count_text.get(), "1")
            self.assertEqual(window.section_result_curve_count_text.get(), "1")
            self.assertTrue(window.section_result_visible.get())

            window.section_result_visible.set(False)
            window._on_section_result_visibility_changed()
            self.assertFalse(stored_result.visible)
            self.assertIsNone(window.viewport.scene_calls[-1]["section_result"])
            self.assertEqual(tree.item(section_result_node, "text"), "[H] Section 1")

            window.section_result_visible.set(True)
            window._on_section_result_visibility_changed()
            self.assertTrue(stored_result.visible)
            self.assertIs(window.viewport.scene_calls[-1]["section_result"], stored_result.result)
            self.assertEqual(tree.item(section_result_node, "text"), "[V] Section 1")

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

    def test_surface_scene_browser_selection_visibility_and_delete(self) -> None:
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

            window.compute_section()
            source_curve = window.app_state.curve_collection.curves[0]
            first_surface = SurfacePatch(
                id="surface-1",
                name="Patch A",
                source_curve_ids=[source_curve.id],
                surface_type="loft",
                metadata={"degree": 3, "quality": "draft"},
            )
            second_surface = SurfacePatch(
                id="surface-2",
                name="Patch B",
                source_curve_ids=[source_curve.id, "curve-extra"],
                surface_type="patch",
                visible=False,
            )
            add_surface(window.app_state.surface_collection, first_surface)
            add_surface(window.app_state.surface_collection, second_surface)
            window._refresh_scene_browser()

            tree = window.scene_browser.tree
            first_surface_node = surface_node_id(first_surface.id)
            second_surface_node = surface_node_id(second_surface.id)
            self.assertEqual(surface_id_from_node(second_surface_node), second_surface.id)
            self.assertEqual(
                tree.get_children(NODE_SCENE),
                (
                    NODE_MESH,
                    NODE_SECTION_PLANES,
                    NODE_SECTION_RESULTS,
                    NODE_CURVES,
                    NODE_SURFACES,
                ),
            )
            self.assertEqual(tree.item(NODE_SURFACES, "text"), "Surfaces")
            self.assertEqual(
                tree.get_children(NODE_SURFACES),
                (first_surface_node, second_surface_node),
            )
            self.assertEqual(tree.item(first_surface_node, "text"), "[V] Patch A")
            self.assertEqual(tree.item(second_surface_node, "text"), "[H] Patch B")

            tree.selection_set(first_surface_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()

            self.assertEqual(window.app_state.selected_item, "surface")
            self.assertEqual(window.app_state.surface_collection.active_surface_id, first_surface.id)
            self.assertTrue(first_surface.selected)
            self.assertFalse(second_surface.selected)
            self.assertEqual(tree.selection(), (first_surface_node,))
            self.assertEqual(window.surface_context_frame.winfo_manager(), "grid")
            self.assertEqual(window.no_selection_frame.winfo_manager(), "")
            self.assertEqual(window.surface_name_text.get(), "Patch A")
            self.assertEqual(window.surface_type_text.get(), "loft")
            self.assertEqual(window.surface_source_curve_count_text.get(), "1")
            self.assertEqual(window.surface_preview_available_text.get(), "(unknown)")
            self.assertEqual(window.surface_preview_reason_text.get(), "(none)")
            self.assertEqual(window.surface_preview_warning_text.get(), "(none)")
            self.assertEqual(window.surface_metadata_text.get(), "degree=3, quality=draft")
            self.assertTrue(window.surface_visible.get())

            window._set_project_dirty(False)
            window.surface_visible.set(False)
            window._on_surface_visibility_changed()

            self.assertFalse(first_surface.visible)
            self.assertTrue(window.project_dirty)
            self.assertEqual(window.status_text.get(), "Selected: Patch A")
            self.assertEqual(tree.get_children(NODE_SURFACES), (first_surface_node, second_surface_node))
            self.assertEqual(tree.item(first_surface_node, "text"), "[H] Patch A")

            tree.selection_set(second_surface_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()
            self.assertEqual(window.app_state.surface_collection.active_surface_id, second_surface.id)
            self.assertFalse(first_surface.selected)
            self.assertTrue(second_surface.selected)
            self.assertFalse(window.surface_visible.get())
            self.assertEqual(window.surface_source_curve_count_text.get(), "2")
            self.assertEqual(window.surface_preview_available_text.get(), "(unknown)")
            self.assertEqual(window.surface_preview_reason_text.get(), "(none)")
            self.assertEqual(window.surface_preview_warning_text.get(), "(none)")
            self.assertEqual(window.surface_metadata_text.get(), "(none)")

            window.delete_selected_surface()

            self.assertEqual(window.app_state.curve_collection.curves, [source_curve])
            self.assertEqual(window.app_state.surface_collection.surfaces, [first_surface])
            self.assertEqual(window.app_state.surface_collection.active_surface_id, first_surface.id)
            self.assertEqual(tree.get_children(NODE_SURFACES), (first_surface_node,))
            self.assertEqual(tree.selection(), (first_surface_node,))
            self.assertEqual(window.status_text.get(), "Deleted: Patch B")
            self.assertEqual(window.app_state.selected_item, "surface")

            window.delete_selected_surface()

            self.assertEqual(window.app_state.curve_collection.curves, [source_curve])
            self.assertEqual(window.app_state.surface_collection.surfaces, [])
            self.assertIsNone(window.app_state.surface_collection.active_surface_id)
            self.assertFalse(tree.exists(NODE_SURFACES))
            self.assertEqual(window.app_state.selected_item, None)
            self.assertEqual(window.status_text.get(), "Deleted: Patch A")
        finally:
            window.root.destroy()

    def test_scene_browser_visibility_commands_hide_show_curves_and_surfaces(self) -> None:
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

            window.compute_section()
            stored_result = window.app_state.section_collection.results[0]
            source_curve = window.app_state.curve_collection.curves[0]
            surface = SurfacePatch(
                id="surface-1",
                name="Surface 1",
                source_curve_ids=[source_curve.id],
                surface_type="preview_fill",
            )
            add_surface(window.app_state.surface_collection, surface)
            window._refresh_scene_browser()

            tree = window.scene_browser.tree
            curve_node = curve_node_id(source_curve.id)
            surface_node = surface_node_id(surface.id)
            section_result_node = section_result_node_id(stored_result.id)

            window._set_project_dirty(False)
            window._on_scene_browser_visibility(
                "hide_selected",
                (curve_node, surface_node),
            )

            self.assertFalse(source_curve.visible)
            self.assertFalse(surface.visible)
            self.assertTrue(stored_result.visible)
            self.assertEqual(tree.item(curve_node, "text"), "[H] Section 1 Curve 1")
            self.assertEqual(tree.item(surface_node, "text"), "[H] Surface 1")
            self.assertEqual(window.app_state.curve_results, [])
            self.assertEqual(window.viewport.scene_calls[-1]["surface_previews"], [])
            self.assertTrue(window.project_dirty)

            window._on_scene_browser_visibility(
                "show_selected",
                (curve_node, surface_node),
            )

            self.assertTrue(source_curve.visible)
            self.assertTrue(surface.visible)
            self.assertEqual(tree.item(curve_node, "text"), "[V] Section 1 Curve 1")
            self.assertEqual(tree.item(surface_node, "text"), "[V] Surface 1")

            window._on_scene_browser_visibility("hide_unselected", (curve_node,))

            self.assertTrue(source_curve.visible)
            self.assertFalse(stored_result.visible)
            self.assertFalse(surface.visible)
            self.assertIsNone(window.viewport.scene_calls[-1]["section_result"])
            self.assertEqual(tree.item(section_result_node, "text"), "[H] Section 1")

            window._on_scene_browser_visibility("show_all", ())

            self.assertTrue(source_curve.visible)
            self.assertTrue(stored_result.visible)
            self.assertTrue(surface.visible)
            self.assertIs(window.viewport.scene_calls[-1]["section_result"], stored_result.result)
            self.assertEqual(tree.item(section_result_node, "text"), "[V] Section 1")
            self.assertEqual(tree.item(surface_node, "text"), "[V] Surface 1")
        finally:
            window.root.destroy()

    def test_global_rename_updates_scene_browser_and_contexts(self) -> None:
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
            window.select_model()
            window._set_project_dirty(False)
            window.mesh_name_text.set("Scan Body")
            window._on_mesh_name_changed()

            self.assertEqual(window.app_state.mesh_object.name, "Scan Body")
            self.assertEqual(window.file_name_text.get(), "sample.stl")
            self.assertEqual(window.selected_object_text.get(), "Scan Body")
            self.assertEqual(tree.item(NODE_MESH, "text"), "[V] Scan Body")
            self.assertTrue(window.project_dirty)

            active_plane = window.app_state.section_collection.planes[0]
            window.select_section_plane(active_plane.id)
            window.section_plane_name_text.set("Cut Plane")
            window._on_section_plane_name_changed()

            plane_node = section_plane_node_id(active_plane.id)
            self.assertEqual(active_plane.name, "Cut Plane")
            self.assertEqual(tree.item(plane_node, "text"), "[H] Cut Plane")

            window.compute_section()
            stored_result = window.app_state.section_collection.results[0]
            stored_curve = window.app_state.curve_collection.curves[0]
            result_node = section_result_node_id(stored_result.id)
            curve_group = curve_group_node_id(stored_result.id)
            window.select_section_result(stored_result.id)
            window.section_result_name_text.set("Rim Section")
            window._on_section_result_name_changed()

            self.assertEqual(stored_result.name, "Rim Section")
            self.assertEqual(tree.item(result_node, "text"), "[V] Rim Section")
            self.assertEqual(tree.item(curve_group, "text"), "Rim Section")

            window.select_curve(stored_curve.id)
            self.assertEqual(window.curve_section_text.get(), "Rim Section")
            self.assertEqual(window.curve_plane_text.get(), "Cut Plane (Z = 0.000)")
            window.curve_name_text.set("Rim Curve")
            window._on_curve_name_changed()

            curve_node = curve_node_id(stored_curve.id)
            self.assertEqual(stored_curve.name, "Rim Curve")
            self.assertEqual(tree.item(curve_node, "text"), "[V] Rim Curve")

            _make_curve_closed(stored_curve)
            window.create_surface_from_curves()
            surface = window.app_state.surface_collection.surfaces[0]
            surface_node = surface_node_id(surface.id)
            window.surface_name_text.set("Preview Surface")
            window._on_surface_name_changed()

            self.assertEqual(surface.name, "Preview Surface")
            self.assertEqual(tree.item(surface_node, "text"), "[V] Preview Surface")
        finally:
            window.root.destroy()

    def test_f2_focuses_selected_object_name_field(self) -> None:
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
            window._handle_shortcut("F2")

            self.assertEqual(window.status_text.get(), "Rename selected object")
            self.assertTrue(window.mesh_name_entry.selection_present())
        finally:
            window.root.destroy()

    def test_section_result_and_curve_group_selection_select_child_curves(self) -> None:
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

            window.compute_section()
            first_result = window.app_state.section_collection.results[0]
            first_curve = window.app_state.curve_collection.curves[0]
            window.add_section_plane()
            window.section_axis.set("X")
            window._on_section_axis_changed()
            window._set_section_offset(0.5, clamp=True, refresh=True)
            window.compute_section()
            second_result = window.app_state.section_collection.results[1]
            second_curve = window.app_state.curve_collection.curves[1]

            tree = window.scene_browser.tree
            first_result_node = section_result_node_id(first_result.id)
            tree.selection_set(first_result_node)
            tree.focus(first_result_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()

            self.assertEqual(window.app_state.selected_item, "section_result")
            self.assertEqual(
                window.app_state.curve_collection.selected_curve_ids,
                {first_curve.id},
            )
            self.assertTrue(first_curve.selected)
            self.assertFalse(second_curve.selected)
            self.assertTrue(window.viewport.scene_calls[-1]["curve_results"][0].selected)

            second_group = curve_group_node_id(second_result.id)
            tree.selection_set(second_group)
            tree.focus(second_group)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()

            self.assertEqual(window.app_state.selected_item, "curve")
            self.assertEqual(
                window.app_state.curve_collection.selected_curve_ids,
                {second_curve.id},
            )
            self.assertFalse(first_curve.selected)
            self.assertTrue(second_curve.selected)
        finally:
            window.root.destroy()

    def test_mesh_visibility_hotkeys_toggle_isolate_and_show_all(self) -> None:
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
            window._handle_shortcut("H")

            self.assertFalse(window.app_state.mesh_object.visible)
            self.assertFalse(window.mesh_visible.get())
            self.assertIsNone(window.viewport.scene_calls[-1]["mesh"])
            self.assertEqual(window.scene_browser.tree.item(NODE_MESH, "text"), "[H] sample.stl")

            window._handle_shortcut("H")

            self.assertTrue(window.app_state.mesh_object.visible)
            self.assertTrue(window.mesh_visible.get())
            self.assertIs(window.viewport.scene_calls[-1]["mesh"], window.app_state.mesh_object.display_mesh)
            self.assertEqual(window.scene_browser.tree.item(NODE_MESH, "text"), "[V] sample.stl")

            active_plane = window.app_state.section_collection.planes[0]
            active_plane.visible = True
            window.show_section_plane.set(True)
            window.select_model()
            window._handle_shortcut("Shift+H")

            self.assertTrue(window.app_state.mesh_object.visible)
            self.assertFalse(active_plane.visible)

            window._handle_shortcut("Alt+H")

            self.assertTrue(window.app_state.mesh_object.visible)
            self.assertTrue(active_plane.visible)
        finally:
            window.root.destroy()

    def test_visibility_keybind_uses_settings_and_ignores_text_entry_focus(self) -> None:
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
            window.settings.keybinds.toggle_visibility = "V"
            window._on_tk_keypress(SimpleNamespace(keysym="h", state=0))
            self.assertTrue(window.app_state.mesh_object.visible)

            window._on_tk_keypress(SimpleNamespace(keysym="v", state=0))
            self.assertFalse(window.app_state.mesh_object.visible)

            window.mesh_name_entry.focus_set()
            window.root.update()
            window._on_tk_keypress(SimpleNamespace(keysym="v", state=0))
            self.assertFalse(window.app_state.mesh_object.visible)
        finally:
            window.root.destroy()

    def test_create_surface_from_selected_curve_adds_placeholder_surface(self) -> None:
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

            window.compute_section()
            source_curve = window.app_state.curve_collection.curves[0]
            _make_curve_closed(source_curve)
            window.select_curve(source_curve.id)
            window._set_project_dirty(False)

            progress_dialogs: list[object] = []

            class RecordingProgressDialog:
                def __init__(self, _parent: object, title: str, summary: str | None = None) -> None:
                    self.title = title
                    self.summary = summary
                    self.stages: list[str] = []
                    self.closed = False
                    progress_dialogs.append(self)

                def update_stage(self, stage: str) -> None:
                    self.stages.append(stage)

                def close(self) -> None:
                    self.closed = True

            with patch("app.main_window.ComputationProgressDialog", RecordingProgressDialog):
                window.curves_menu.invoke(0)

            surfaces = window.app_state.surface_collection.surfaces
            self.assertEqual(len(surfaces), 1)
            surface = surfaces[0]
            self.assertEqual(surface.name, "Surface 1")
            self.assertEqual(surface.surface_type, "preview_fill")
            self.assertEqual(surface.source_curve_ids, [source_curve.id])
            self.assertTrue(surface.visible)
            self.assertTrue(surface.selected)
            self.assertEqual(surface.metadata["curve_count"], 1)
            self.assertEqual(surface.metadata["source_curve_count"], 1)
            self.assertEqual(surface.metadata["source"], "selected_curve")
            self.assertEqual(
                surface.metadata["preview_mode"],
                "closed_curve_fill",
            )
            self.assertTrue(surface.metadata["preview_available"])
            self.assertEqual(surface.metadata["preview_reason"], "fan fill preview generated")
            self.assertEqual(
                surface.metadata["preview_warning"],
                "Fan fill preview may be inaccurate for concave curves",
            )
            self.assertEqual(window.app_state.selected_item, "surface")
            self.assertEqual(window.app_state.surface_collection.active_surface_id, surface.id)
            self.assertEqual(window.status_text.get(), "Created Surface 1 preview from 1 curve")
            self.assertEqual(len(progress_dialogs), 1)
            self.assertEqual(progress_dialogs[0].title, "Building Surface Preview")
            self.assertEqual(progress_dialogs[0].stages, list(SURFACE_PREVIEW_PROGRESS_STAGES))
            self.assertTrue(progress_dialogs[0].closed)
            self.assertTrue(window.project_dirty)
            self.assertEqual(window.surface_context_frame.winfo_manager(), "grid")
            self.assertEqual(window.surface_name_text.get(), "Surface 1")
            self.assertEqual(window.surface_type_text.get(), "preview_fill")
            self.assertEqual(window.surface_source_curve_count_text.get(), "1")
            self.assertEqual(window.surface_preview_available_text.get(), "Yes")
            self.assertEqual(window.surface_preview_reason_text.get(), "fan fill preview generated")
            self.assertEqual(
                window.surface_preview_warning_text.get(),
                "Fan fill preview may be inaccurate for concave curves",
            )
            self.assertIn("curve_count=1", window.surface_metadata_text.get())
            self.assertIn("source=selected_curve", window.surface_metadata_text.get())

            tree = window.scene_browser.tree
            surface_node = surface_node_id(surface.id)
            self.assertEqual(tree.get_children(NODE_SURFACES), (surface_node,))
            self.assertEqual(tree.item(surface_node, "text"), "[V] Surface 1")
            self.assertEqual(tree.selection(), (surface_node,))
        finally:
            window.root.destroy()

    def test_create_surface_from_two_selected_curves_creates_loft_with_unique_names(self) -> None:
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

            window.compute_section()
            first_curve = window.app_state.curve_collection.curves[0]
            window.add_section_plane()
            window.section_axis.set("X")
            window._on_section_axis_changed()
            window._set_section_offset(0.5, clamp=True, refresh=True)
            window.compute_section()
            second_curve = window.app_state.curve_collection.curves[1]

            window.select_curves(
                [first_curve.id, second_curve.id],
                active_curve_id=second_curve.id,
            )
            window.curves_menu.invoke(0)
            first_surface = window.app_state.surface_collection.surfaces[0]
            self.assertEqual(first_surface.name, "Surface 1")
            self.assertEqual(
                first_surface.source_curve_ids,
                [first_curve.id, second_curve.id],
            )
            self.assertEqual(first_surface.surface_type, "preview_loft")
            self.assertEqual(first_surface.metadata["curve_count"], 2)
            self.assertEqual(first_surface.metadata["source_curve_count"], 2)
            self.assertEqual(first_surface.metadata["source"], "selected_curves")
            self.assertEqual(first_surface.metadata["preview_mode"], "two_curve_loft")
            self.assertTrue(first_surface.metadata["preview_available"])
            self.assertIn("loft generated", str(first_surface.metadata["preview_reason"]))
            self.assertEqual(
                window.status_text.get(),
                "Created Surface 1 preview from 2 curves",
            )

            window.select_curves(
                [first_curve.id, second_curve.id],
                active_curve_id=first_curve.id,
            )
            window.curves_menu.invoke(0)

            surfaces = window.app_state.surface_collection.surfaces
            self.assertEqual([surface.name for surface in surfaces], ["Surface 1", "Surface 2"])
            second_surface = surfaces[1]
            self.assertEqual(second_surface.source_curve_ids, [first_curve.id, second_curve.id])
            self.assertEqual(second_surface.surface_type, "preview_loft")

            window.clear_selection()
            window.curves_menu.invoke(0)
            self.assertEqual(
                window.status_text.get(),
                "Select one closed curve for fill or two curves for loft.",
            )
            self.assertEqual(len(window.app_state.surface_collection.surfaces), 2)
        finally:
            window.root.destroy()

    def test_create_surface_from_short_two_curve_selection_marks_preview_unavailable(self) -> None:
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

            window.compute_section()
            first_curve = window.app_state.curve_collection.curves[0]
            short_points = np.asarray([[0.0, 0.0, 0.0]], dtype=float)
            short_curve = StoredCurve(
                id="curve-short",
                name="Short Curve",
                section_result_id=first_curve.section_result_id,
                plane_id=first_curve.plane_id,
                original_points=short_points.copy(),
                fitted_points=short_points.copy(),
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
            )
            add_curve(window.app_state.curve_collection, short_curve)

            window.select_curves(
                [first_curve.id, short_curve.id],
                active_curve_id=short_curve.id,
            )
            progress_dialogs: list[object] = []

            class RecordingProgressDialog:
                def __init__(self, _parent: object, title: str, summary: str | None = None) -> None:
                    self.title = title
                    self.summary = summary
                    self.stages: list[str] = []
                    self.closed = False
                    progress_dialogs.append(self)

                def update_stage(self, stage: str) -> None:
                    self.stages.append(stage)

                def close(self) -> None:
                    self.closed = True

            with patch("app.main_window.ComputationProgressDialog", RecordingProgressDialog):
                window.create_surface_from_curves()

            surfaces = window.app_state.surface_collection.surfaces
            self.assertEqual(surfaces, [])
            self.assertEqual(
                window.status_text.get(),
                "Surface preview unavailable: curve has too few points",
            )
            self.assertEqual(progress_dialogs[0].stages, list(SURFACE_PREVIEW_PROGRESS_STAGES))
            self.assertTrue(progress_dialogs[0].closed)
            self.assertEqual(window.viewport.scene_calls[-1]["surface_previews"], [])
        finally:
            window.root.destroy()

    def test_scene_browser_multi_selects_curves_and_viewport_marks_each_selected(self) -> None:
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

            window.compute_section()
            first_curve = window.app_state.curve_collection.curves[0]
            window.add_section_plane()
            window.section_axis.set("X")
            window._on_section_axis_changed()
            window._set_section_offset(0.5, clamp=True, refresh=True)
            window.compute_section()
            second_curve = window.app_state.curve_collection.curves[1]

            tree = window.scene_browser.tree
            first_curve_node = curve_node_id(first_curve.id)
            second_curve_node = curve_node_id(second_curve.id)
            tree.selection_set((first_curve_node, second_curve_node))
            tree.focus(second_curve_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()

            self.assertEqual(window.app_state.selected_item, "curve")
            self.assertEqual(window.app_state.curve_collection.active_curve_id, second_curve.id)
            self.assertEqual(
                window.app_state.curve_collection.selected_curve_ids,
                {first_curve.id, second_curve.id},
            )
            self.assertTrue(first_curve.selected)
            self.assertTrue(second_curve.selected)
            self.assertEqual(tree.selection(), (first_curve_node, second_curve_node))
            self.assertEqual(window.status_text.get(), "Selected: 2 curves")
            self.assertTrue(all(curve.selected for curve in window.viewport.scene_calls[-1]["curve_results"]))
        finally:
            window.root.destroy()

    def test_curve_visibility_commands_hide_selected_unselected_and_show_all(self) -> None:
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

            window.compute_section()
            first_curve = window.app_state.curve_collection.curves[0]
            window.add_section_plane()
            window.section_axis.set("X")
            window._on_section_axis_changed()
            window._set_section_offset(0.5, clamp=True, refresh=True)
            window.compute_section()
            second_curve = window.app_state.curve_collection.curves[1]

            window.select_curve(first_curve.id)
            window._set_project_dirty(False)
            window.hide_selected_curves()

            self.assertFalse(first_curve.visible)
            self.assertTrue(second_curve.visible)
            self.assertEqual(window.app_state.curve_results, [second_curve])
            self.assertEqual(window.status_text.get(), "Hidden selected curve")
            self.assertTrue(window.project_dirty)

            window.show_all_curves()
            self.assertTrue(first_curve.visible)
            self.assertTrue(second_curve.visible)
            self.assertEqual(window.app_state.curve_results, [first_curve, second_curve])

            window.select_curve(first_curve.id)
            window.hide_unselected_curves()

            self.assertTrue(first_curve.visible)
            self.assertFalse(second_curve.visible)
            self.assertEqual(window.app_state.curve_results, [first_curve])
            self.assertEqual(window.status_text.get(), "Hidden 1 unselected curves")

            window.curves_menu.invoke(3)
            self.assertTrue(first_curve.visible)
            self.assertTrue(second_curve.visible)
            self.assertEqual(window.status_text.get(), "All curves visible")
        finally:
            window.root.destroy()

    def test_create_surface_rejects_open_single_curve_and_more_than_two_curves(self) -> None:
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

            window.compute_section()
            first_curve = window.app_state.curve_collection.curves[0]
            window.select_curve(first_curve.id)
            window.curves_menu.invoke(0)

            self.assertEqual(
                window.status_text.get(),
                "Surface preview unavailable: single curve is not closed",
            )
            self.assertEqual(window.app_state.surface_collection.surfaces, [])

            points = np.asarray(
                [
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                ],
                dtype=float,
            )
            second_curve = StoredCurve(
                id="curve-2",
                name="Curve 2",
                section_result_id="section-result-2",
                plane_id="plane-2",
                original_points=points.copy(),
                fitted_points=points.copy(),
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
            )
            third_curve = StoredCurve(
                id="curve-3",
                name="Curve 3",
                section_result_id="section-result-3",
                plane_id="plane-3",
                original_points=points.copy(),
                fitted_points=points.copy(),
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
            )
            add_curve(window.app_state.curve_collection, second_curve)
            add_curve(window.app_state.curve_collection, third_curve)
            window.select_curves(
                [first_curve.id, second_curve.id, third_curve.id],
                active_curve_id=third_curve.id,
            )
            window.curves_menu.invoke(0)

            self.assertEqual(
                window.status_text.get(),
                "Surface preview unavailable: unsupported curve count",
            )
            self.assertEqual(window.app_state.surface_collection.surfaces, [])
        finally:
            window.root.destroy()

    def test_visible_surface_preview_ignores_source_curve_visibility(self) -> None:
        closed_points = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0],
            ],
            dtype=float,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            curve = StoredCurve(
                id="curve-1",
                name="Curve 1",
                section_result_id="section-result-1",
                plane_id="plane-1",
                original_points=closed_points.copy(),
                fitted_points=closed_points.copy(),
                mean_error=0.0,
                max_error=0.0,
                is_closed=True,
                visible=False,
            )
            add_curve(window.app_state.curve_collection, curve)
            surface = SurfacePatch(
                id="surface-1",
                name="Surface 1",
                source_curve_ids=[curve.id],
                surface_type="placeholder",
                visible=True,
            )
            add_surface(window.app_state.surface_collection, surface)

            window._refresh_viewport(reset_camera=False)

            previews = window.viewport.scene_calls[-1]["surface_previews"]
            self.assertEqual(len(previews), 1)
            self.assertEqual(previews[0].source_surface_id, surface.id)

            surface.visible = False
            window._refresh_viewport(reset_camera=False)

            self.assertEqual(window.viewport.scene_calls[-1]["surface_previews"], [])
        finally:
            window.root.destroy()

    def test_model_transform_preserves_generated_surfaces_and_restores_preview(self) -> None:
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

            window.compute_section()
            source_curve = window.app_state.curve_collection.curves[0]
            _make_curve_closed(source_curve)
            window.select_curve(source_curve.id)
            window.create_surface_from_curves()
            surface = window.app_state.surface_collection.surfaces[0]
            surface_node = surface_node_id(surface.id)

            self.assertEqual(len(window.viewport.scene_calls[-1]["surface_previews"]), 1)
            self.assertTrue(window.scene_browser.tree.exists(surface_node))

            window.select_model()
            window._start_active_transform("move")

            self.assertEqual(window.app_state.surface_collection.surfaces, [surface])
            self.assertTrue(window.scene_browser.tree.exists(surface_node))
            self.assertEqual(window.viewport.scene_calls[-1]["surface_previews"], [])
            self.assertEqual(window.viewport.scene_calls[-1]["curve_results"], [])
            self.assertIsNone(window.viewport.scene_calls[-1]["section_result"])

            window._end_active_transform(commit=True, status="Transform confirmed")

            self.assertEqual(window.app_state.surface_collection.surfaces, [surface])
            self.assertTrue(window.scene_browser.tree.exists(surface_node))
            self.assertEqual(len(window.viewport.scene_calls[-1]["surface_previews"]), 1)
            self.assertEqual(
                window.viewport.scene_calls[-1]["surface_previews"][0].source_surface_id,
                surface.id,
            )
            self.assertEqual(window.status_text.get(), GENERATED_GEOMETRY_TRANSFORM_WARNING)
        finally:
            window.root.destroy()

    def test_deleting_source_curve_removes_dependent_placeholder_surface(self) -> None:
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

            window.compute_section()
            stored_result = window.app_state.section_collection.results[0]
            source_curve = window.app_state.curve_collection.curves[0]
            source_plane = window.app_state.section_collection.planes[0]
            _make_curve_closed(source_curve)
            window.select_curve(source_curve.id)
            window.curves_menu.invoke(0)
            self.assertEqual(len(window.app_state.surface_collection.surfaces), 1)

            window.select_curve(source_curve.id)
            window.delete_selected_curve()

            self.assertEqual(window.app_state.curve_collection.curves, [])
            self.assertEqual(window.app_state.surface_collection.surfaces, [])
            self.assertIsNone(window.app_state.surface_collection.active_surface_id)
            self.assertEqual(window.app_state.section_collection.results, [stored_result])
            self.assertEqual(window.app_state.section_collection.planes, [source_plane])
            self.assertFalse(window.scene_browser.tree.exists(NODE_SURFACES))
            self.assertEqual(window.status_text.get(), "Deleted: Section 1 Curve 1")
        finally:
            window.root.destroy()

    def test_add_section_plane_command_creates_active_plane_and_updates_browser(self) -> None:
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

            first_plane = window.app_state.section_collection.planes[0]
            window._set_section_offset(0.5, clamp=True, refresh=True)
            window.section_axis.set("X")
            window._on_section_axis_changed()

            window.sections_menu.invoke(0)

            planes = window.app_state.section_collection.planes
            self.assertEqual(len(planes), 2)
            self.assertIs(planes[0], first_plane)
            second_plane = planes[1]
            self.assertEqual(first_plane.name, "Section Plane 1")
            self.assertEqual(second_plane.name, "Section Plane 2")
            self.assertEqual(second_plane.axis, "X")
            self.assertEqual(second_plane.offset, 0.5)
            self.assertFalse(second_plane.visible)
            self.assertEqual(window.app_state.section_collection.active_plane_id, second_plane.id)
            self.assertFalse(first_plane.selected)
            self.assertTrue(second_plane.selected)
            self.assertEqual(window.section_axis.get(), "X")
            self.assertEqual(window.section_offset.get(), 0.5)
            self.assertEqual(window.section_offset_text.get(), "0.500")
            self.assertEqual(window.status_text.get(), "Added: Section Plane 2")
            self.assertIsNone(window.app_state.section_result)
            self.assertEqual(window.section_result_text.get(), "Section result: none")

            tree = window.scene_browser.tree
            first_node = section_plane_node_id(first_plane.id)
            second_node = section_plane_node_id(second_plane.id)
            self.assertEqual(tree.get_children(NODE_SECTION_PLANES), (first_node, second_node))
            self.assertEqual(tree.item(first_node, "text"), "[H] Section Plane 1")
            self.assertEqual(tree.item(second_node, "text"), "[H] Section Plane 2")
            self.assertEqual(tree.selection(), (second_node,))
            self.assertEqual(window.viewport.scene_calls[-1]["selected_item"], "section_plane")
            self.assertEqual(window.viewport.scene_calls[-1]["section_axis"], "X")
            self.assertEqual(window.viewport.scene_calls[-1]["section_offset"], 0.5)
            self.assertEqual(
                window.viewport.scene_calls[-1]["section_planes"],
                window.app_state.section_collection.planes,
            )
            self.assertEqual(
                window.viewport.scene_calls[-1]["active_section_plane_id"],
                second_plane.id,
            )

            window.section_axis.set("Y")
            window._on_section_axis_changed()
            window._set_section_offset(1.0, clamp=True, refresh=True)
            self.assertEqual(second_plane.axis, "Y")
            self.assertEqual(second_plane.offset, 1.0)

            tree.selection_set(first_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()
            self.assertEqual(window.app_state.section_collection.active_plane_id, first_plane.id)
            self.assertTrue(first_plane.selected)
            self.assertFalse(second_plane.selected)
            self.assertEqual(window.section_axis.get(), "X")
            self.assertEqual(window.section_offset.get(), 0.5)
            self.assertEqual(tree.selection(), (first_node,))

            tree.selection_set(second_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()
            self.assertEqual(window.app_state.section_collection.active_plane_id, second_plane.id)
            self.assertFalse(first_plane.selected)
            self.assertTrue(second_plane.selected)
            self.assertEqual(window.section_axis.get(), "Y")
            self.assertEqual(window.section_offset.get(), 1.0)
            self.assertEqual(tree.selection(), (second_node,))
        finally:
            window.root.destroy()

    def test_compute_section_stores_independent_results_for_active_planes(self) -> None:
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

            first_plane = window.app_state.section_collection.planes[0]
            window.compute_section()
            first_result = window.app_state.section_collection.results[0]
            self.assertEqual(first_result.name, "Section 1")
            self.assertEqual(first_result.plane_id, first_plane.id)
            self.assertEqual(first_result.axis, "Z")
            self.assertEqual(first_result.offset, 0.0)
            self.assertIs(window.app_state.section_result, first_result.result)
            self.assertEqual(window.section_result_text.get(), "Section result: Section 1 - 1 segments")
            first_curve = window.app_state.curve_collection.curves[0]
            self.assertEqual(first_curve.name, "Section 1 Curve 1")
            self.assertEqual(first_curve.section_result_id, first_result.id)
            self.assertEqual(first_curve.plane_id, first_plane.id)
            self.assertEqual(window.app_state.curve_results, [first_curve])

            window.add_section_plane()
            second_plane = window.app_state.section_collection.planes[1]
            window.section_axis.set("X")
            window._on_section_axis_changed()
            window._set_section_offset(0.5, clamp=True, refresh=True)
            window.compute_section()

            results = window.app_state.section_collection.results
            self.assertEqual(len(results), 2)
            second_result = results[1]
            self.assertEqual(second_result.name, "Section 2")
            self.assertEqual(second_result.plane_id, second_plane.id)
            self.assertEqual(second_result.axis, "X")
            self.assertEqual(second_result.offset, 0.5)
            self.assertIs(window.app_state.section_result, second_result.result)
            self.assertEqual(window.section_result_text.get(), "Section result: Section 2 - 1 segments")
            self.assertEqual(window.status_text.get(), "Section computed: Section 2 - 1 segments")
            second_curve = window.app_state.curve_collection.curves[1]
            self.assertEqual(second_curve.name, "Section 2 Curve 1")
            self.assertEqual(second_curve.section_result_id, second_result.id)
            self.assertEqual(second_curve.plane_id, second_plane.id)
            self.assertEqual(window.app_state.curve_results, [first_curve, second_curve])
            self.assertEqual(
                window.viewport.scene_calls[-1]["curve_results"],
                [first_curve, second_curve],
            )

            tree = window.scene_browser.tree
            first_result_node = section_result_node_id(first_result.id)
            second_result_node = section_result_node_id(second_result.id)
            first_curve_group = curve_group_node_id(first_result.id)
            second_curve_group = curve_group_node_id(second_result.id)
            first_curve_node = curve_node_id(first_curve.id)
            second_curve_node = curve_node_id(second_curve.id)
            self.assertEqual(
                tree.get_children(NODE_SECTION_RESULTS),
                (first_result_node, second_result_node),
            )
            self.assertEqual(tree.item(first_result_node, "text"), "[V] Section 1")
            self.assertEqual(tree.item(second_result_node, "text"), "[V] Section 2")
            self.assertEqual(
                tree.get_children(NODE_CURVES),
                (first_curve_group, second_curve_group),
            )
            self.assertEqual(tree.get_children(first_curve_group), (first_curve_node,))
            self.assertEqual(tree.get_children(second_curve_group), (second_curve_node,))
            self.assertEqual(tree.item(first_curve_node, "text"), "[V] Section 1 Curve 1")
            self.assertEqual(tree.item(second_curve_node, "text"), "[V] Section 2 Curve 1")

            first_plane_node = section_plane_node_id(first_plane.id)
            tree.selection_set(first_plane_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()
            self.assertEqual(window.app_state.section_collection.active_plane_id, first_plane.id)
            self.assertEqual(window.app_state.section_collection.results, [first_result, second_result])

            window.clear_section()
            self.assertEqual(window.app_state.section_collection.results, [second_result])
            self.assertIs(window.app_state.section_result, second_result.result)
            self.assertEqual(window.section_result_text.get(), "Section result: Section 2 - 1 segments")
            self.assertEqual(tree.get_children(NODE_SECTION_RESULTS), (second_result_node,))
            self.assertEqual(window.app_state.curve_collection.curves, [second_curve])
            self.assertEqual(window.app_state.curve_results, [second_curve])
            self.assertEqual(tree.get_children(NODE_CURVES), (second_curve_group,))
            self.assertEqual(tree.get_children(second_curve_group), (second_curve_node,))
        finally:
            window.root.destroy()

    def test_curve_selection_visibility_and_delete_preserve_section_results(self) -> None:
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

            first_plane = window.app_state.section_collection.planes[0]
            window.compute_section()
            first_result = window.app_state.section_collection.results[0]
            first_curve = window.app_state.curve_collection.curves[0]
            window.add_section_plane()
            second_plane = window.app_state.section_collection.planes[1]
            window.section_axis.set("X")
            window._on_section_axis_changed()
            window._set_section_offset(0.5, clamp=True, refresh=True)
            window.compute_section()
            second_result = window.app_state.section_collection.results[1]
            second_curve = window.app_state.curve_collection.curves[1]

            tree = window.scene_browser.tree
            first_curve_node = curve_node_id(first_curve.id)
            second_curve_node = curve_node_id(second_curve.id)
            self.assertEqual(curve_id_from_node(first_curve_node), first_curve.id)

            tree.selection_set(first_curve_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()

            self.assertEqual(window.app_state.selected_item, "curve")
            self.assertEqual(window.app_state.curve_collection.active_curve_id, first_curve.id)
            self.assertEqual(window.app_state.curve_collection.selected_curve_ids, {first_curve.id})
            self.assertTrue(first_curve.selected)
            self.assertFalse(second_curve.selected)
            self.assertEqual(tree.selection(), (first_curve_node,))
            self.assertEqual(window.curve_context_frame.winfo_manager(), "grid")
            self.assertEqual(window.no_selection_frame.winfo_manager(), "")
            self.assertEqual(window.curve_name_text.get(), "Section 1 Curve 1")
            self.assertEqual(window.curve_section_text.get(), "Section 1")
            self.assertEqual(window.curve_plane_text.get(), f"{first_plane.name} (Z = 0.000)")
            self.assertEqual(window.curve_point_count_text.get(), "2")
            self.assertEqual(window.curve_closed_text.get(), "Open")
            self.assertTrue(window.curve_visible.get())
            self.assertEqual(window.viewport.scene_calls[-1]["curve_results"], [first_curve, second_curve])
            self.assertTrue(window.viewport.scene_calls[-1]["curve_results"][0].selected)
            self.assertFalse(window.viewport.scene_calls[-1]["curve_results"][1].selected)

            window._set_project_dirty(False)
            window.curve_name_text.set("Rim Curve")
            window._on_curve_name_changed()

            self.assertEqual(first_curve.name, "Rim Curve")
            self.assertEqual(tree.item(first_curve_node, "text"), "[V] Rim Curve")
            self.assertEqual(window.status_text.get(), "Selected: Rim Curve")
            self.assertTrue(window.project_dirty)

            window.curve_visible.set(False)
            window._on_curve_visibility_changed()

            self.assertFalse(first_curve.visible)
            self.assertTrue(second_curve.visible)
            self.assertEqual(window.app_state.curve_results, [second_curve])
            self.assertEqual(window.viewport.scene_calls[-1]["curve_results"], [second_curve])
            first_curve_group = curve_group_node_id(first_result.id)
            second_curve_group = curve_group_node_id(second_result.id)
            self.assertEqual(tree.get_children(NODE_CURVES), (first_curve_group, second_curve_group))
            self.assertEqual(tree.get_children(first_curve_group), (first_curve_node,))
            self.assertEqual(tree.get_children(second_curve_group), (second_curve_node,))
            self.assertEqual(tree.selection(), (first_curve_node,))

            window.curve_visible.set(True)
            window._on_curve_visibility_changed()

            self.assertTrue(first_curve.visible)
            self.assertEqual(window.app_state.curve_results, [first_curve, second_curve])
            self.assertEqual(window.viewport.scene_calls[-1]["curve_results"], [first_curve, second_curve])

            window.curve_visible.set(False)
            window._on_curve_visibility_changed()

            window.curves_menu.invoke(4)

            self.assertEqual(window.app_state.section_collection.results, [first_result, second_result])
            self.assertEqual(window.app_state.section_collection.planes, [first_plane, second_plane])
            self.assertEqual(window.app_state.curve_collection.curves, [second_curve])
            self.assertEqual(window.app_state.curve_collection.active_curve_id, second_curve.id)
            self.assertEqual(window.app_state.curve_collection.selected_curve_ids, {second_curve.id})
            self.assertEqual(window.app_state.curve_results, [second_curve])
            self.assertEqual(tree.get_children(NODE_CURVES), (second_curve_group,))
            self.assertEqual(tree.get_children(second_curve_group), (second_curve_node,))
            self.assertEqual(tree.selection(), (second_curve_node,))
            self.assertEqual(window.status_text.get(), "Deleted: Rim Curve")
            self.assertEqual(window.curve_section_text.get(), "Section 2")
            self.assertEqual(window.curve_plane_text.get(), f"{second_plane.name} (X = 0.500)")
        finally:
            window.root.destroy()

    def test_clear_all_section_results_removes_all_result_nodes(self) -> None:
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

            window.compute_section()
            window.add_section_plane()
            window.section_axis.set("X")
            window._on_section_axis_changed()
            window._set_section_offset(0.5, clamp=True, refresh=True)
            window.compute_section()

            self.assertEqual(len(window.app_state.section_collection.results), 2)
            self.assertEqual(len(window.app_state.curve_collection.curves), 2)
            self.assertTrue(window.scene_browser.tree.exists(NODE_SECTION_RESULTS))
            self.assertTrue(window.scene_browser.tree.exists(NODE_CURVES))

            window.sections_menu.invoke(4)

            self.assertEqual(window.app_state.section_collection.results, [])
            self.assertIsNone(window.app_state.section_result)
            self.assertEqual(window.app_state.curve_collection.curves, [])
            self.assertIsNone(window.app_state.curve_collection.active_curve_id)
            self.assertEqual(window.app_state.curve_results, [])
            self.assertEqual(window.section_result_text.get(), "Section result: none")
            self.assertEqual(window.status_text.get(), "All section results cleared")
            self.assertFalse(window.scene_browser.tree.exists(NODE_SECTION_RESULTS))
            self.assertFalse(window.scene_browser.tree.exists(NODE_CURVES))
            self.assertEqual(len(window.app_state.section_collection.planes), 2)
            self.assertEqual(window.viewport.scene_calls[-1]["section_result"], None)
            self.assertEqual(window.viewport.scene_calls[-1]["curve_results"], [])
        finally:
            window.root.destroy()

    def test_delete_active_section_plane_removes_results_and_restores_default(self) -> None:
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

            first_plane = window.app_state.section_collection.planes[0]
            window.compute_section()
            first_result = window.app_state.section_collection.results[0]
            first_curve = window.app_state.curve_collection.curves[0]
            window.add_section_plane()
            second_plane = window.app_state.section_collection.planes[1]
            window.section_axis.set("X")
            window._on_section_axis_changed()
            window._set_section_offset(0.5, clamp=True, refresh=True)
            window.compute_section()
            second_result = window.app_state.section_collection.results[1]
            second_curve = window.app_state.curve_collection.curves[1]

            window.sections_menu.invoke(1)

            self.assertEqual(window.app_state.section_collection.planes, [first_plane])
            self.assertEqual(window.app_state.section_collection.active_plane_id, first_plane.id)
            self.assertTrue(first_plane.selected)
            self.assertEqual(window.app_state.section_collection.results, [first_result])
            self.assertNotIn(second_result, window.app_state.section_collection.results)
            self.assertEqual(window.app_state.curve_collection.curves, [first_curve])
            self.assertNotIn(second_curve, window.app_state.curve_collection.curves)
            self.assertEqual(window.app_state.curve_results, [first_curve])
            self.assertIs(window.app_state.section_result, first_result.result)
            self.assertEqual(window.section_result_text.get(), "Section result: Section 1 - 1 segments")
            self.assertEqual(window.section_axis.get(), "Z")
            self.assertEqual(window.section_offset.get(), 0.0)
            self.assertEqual(window.app_state.selected_item, "section_plane")
            self.assertEqual(window.status_text.get(), "Deleted: Section Plane 2")

            tree = window.scene_browser.tree
            first_plane_node = section_plane_node_id(first_plane.id)
            first_result_node = section_result_node_id(first_result.id)
            first_curve_group = curve_group_node_id(first_result.id)
            first_curve_node = curve_node_id(first_curve.id)
            self.assertEqual(tree.get_children(NODE_SECTION_PLANES), (first_plane_node,))
            self.assertEqual(tree.get_children(NODE_SECTION_RESULTS), (first_result_node,))
            self.assertEqual(tree.get_children(NODE_CURVES), (first_curve_group,))
            self.assertEqual(tree.get_children(first_curve_group), (first_curve_node,))
            self.assertEqual(tree.selection(), (first_plane_node,))

            window.sections_menu.invoke(1)

            restored_plane = window.app_state.section_collection.planes[0]
            restored_node = section_plane_node_id(restored_plane.id)
            self.assertEqual(len(window.app_state.section_collection.planes), 1)
            self.assertIsNot(restored_plane, first_plane)
            self.assertEqual(restored_plane.name, "Section Plane 1")
            self.assertEqual(restored_plane.axis, "Z")
            self.assertEqual(restored_plane.offset, 0.0)
            self.assertTrue(restored_plane.selected)
            self.assertEqual(window.app_state.section_collection.active_plane_id, restored_plane.id)
            self.assertEqual(window.app_state.section_collection.results, [])
            self.assertEqual(window.app_state.curve_collection.curves, [])
            self.assertEqual(window.app_state.curve_results, [])
            self.assertIsNone(window.app_state.section_result)
            self.assertEqual(window.section_result_text.get(), "Section result: none")
            self.assertFalse(tree.exists(NODE_SECTION_RESULTS))
            self.assertFalse(tree.exists(NODE_CURVES))
            self.assertEqual(tree.get_children(NODE_SECTION_PLANES), (restored_node,))
            self.assertEqual(tree.selection(), (restored_node,))

            window.clear_selection()
            window.sections_menu.invoke(1)

            next_restored_plane = window.app_state.section_collection.planes[0]
            self.assertEqual(len(window.app_state.section_collection.planes), 1)
            self.assertIsNot(next_restored_plane, restored_plane)
            self.assertEqual(window.app_state.selected_item, "section_plane")
            self.assertIn("Deleted: Section Plane 1", window.status_text.get())
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
            self.assertEqual(window.viewport.scene_calls[-1]["show_section_plane"], False)

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
            self.assertEqual(window.status_text.get(), "Section computed: Section 1 - 1 segments")
            self.assertEqual(window.section_result_text.get(), "Section result: Section 1 - 1 segments")

            window.clear_section()
            self.assertEqual(window.status_text.get(), "Section cleared")
            self.assertEqual(window.section_result_text.get(), "Section result: none")
            self.assertIsNone(window.viewport.scene_calls[-1]["section_result"])
            self.assertEqual(window.viewport.scene_calls[-1]["show_section_plane"], False)

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

