"""Integrated Open3D main window for openRetop."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import open3d as o3d
import open3d.visualization.gui as gui
import open3d.visualization.rendering as rendering

from geometry.curves import CurveFitResult, fit_section_polylines
from geometry.sections import SECTION_AXES, SectionResult, extract_section
from mesh.import_mesh import (
    build_normal_lines,
    build_polyline_lines,
    build_polyline_tubes,
)
from mesh.loader import load_mesh
from mesh.mesh_state import MeshState


class OpenRetopWindow:
    """One-window mesh viewer with embedded controls and viewport."""

    MENU_OPEN = 1
    MENU_EXIT = 2
    MENU_RESET_CAMERA = 3
    MENU_SHOW_NORMALS = 4

    MESH_GEOMETRY_NAME = "loaded_mesh"
    NORMALS_GEOMETRY_NAME = "mesh_normals"
    FITTED_CURVE_GEOMETRY_NAME = "fitted_curve"
    SECTION_GEOMETRY_PREFIX = "section_curve_"

    def __init__(self, width: int = 1280, height: int = 800) -> None:
        self.window = gui.Application.instance.create_window("openRetop", width, height)
        self.mesh_state = MeshState()
        self.section_result: SectionResult | None = None
        self.curve_results: list[CurveFitResult] = []
        self.show_normals = False

        self._scene = gui.SceneWidget()
        self._scene.scene = rendering.Open3DScene(self.window.renderer)
        self._scene.scene.set_background([0.08, 0.09, 0.1, 1.0])
        self._scene.scene.show_axes(True)

        self._sidebar = self._build_sidebar()
        self._status = gui.Label("No model loaded")

        self.window.add_child(self._scene)
        self.window.add_child(self._sidebar)
        self.window.add_child(self._status)
        self.window.set_on_layout(self._on_layout)

        self._setup_menu()
        self._set_section_controls_enabled(False)
        self._reset_stats()
        self._reset_camera()

    def _build_sidebar(self) -> gui.Vert:
        em = self.window.theme.font_size
        sidebar = gui.Vert(0.45 * em, gui.Margins(em, em, em, em))

        self._open_button = gui.Button("Open Model")
        self._open_button.set_on_clicked(self._on_open_model)
        sidebar.add_child(self._open_button)
        sidebar.add_fixed(0.25 * em)

        sidebar.add_child(gui.Label("Loaded file"))
        self._file_name_label = gui.Label("(none)")
        sidebar.add_child(self._file_name_label)

        sidebar.add_fixed(0.25 * em)
        self._vertex_count_label = self._add_stat_row(sidebar, "Vertices", "0")
        self._triangle_count_label = self._add_stat_row(sidebar, "Triangles", "0")
        self._bbox_size_label = self._add_stat_row(sidebar, "Bounding box", "-")

        sidebar.add_fixed(0.75 * em)
        sidebar.add_child(gui.Label("Section controls"))

        axis_row = gui.Horiz(0.5 * em)
        axis_row.add_child(gui.Label("Axis"))
        self._axis_dropdown = gui.Combobox()
        for axis in SECTION_AXES:
            self._axis_dropdown.add_item(axis)
        self._axis_dropdown.selected_index = SECTION_AXES.index("Z")
        axis_row.add_child(self._axis_dropdown)
        sidebar.add_child(axis_row)

        offset_row = gui.Horiz(0.5 * em)
        offset_row.add_child(gui.Label("Offset"))
        self._offset_input = gui.NumberEdit(gui.NumberEdit.DOUBLE)
        self._offset_input.double_value = 0.0
        self._offset_input.decimal_precision = 4
        self._offset_input.set_preferred_width(7 * em)
        offset_row.add_child(self._offset_input)
        sidebar.add_child(offset_row)

        self._section_plane_label = gui.Label("Section: Z = 0")
        sidebar.add_child(self._section_plane_label)

        self._compute_section_button = gui.Button("Compute Section")
        self._compute_section_button.set_on_clicked(self._on_compute_section)
        sidebar.add_child(self._compute_section_button)

        self._axis_dropdown.set_on_selection_changed(self._on_section_axis_changed)
        self._offset_input.set_on_value_changed(self._on_section_offset_changed)

        sidebar.add_fixed(0.75 * em)
        self._show_normals_checkbox = gui.Checkbox("Show Normals")
        self._show_normals_checkbox.checked = False
        self._show_normals_checkbox.set_on_checked(self._set_show_normals)
        sidebar.add_child(self._show_normals_checkbox)
        sidebar.add_stretch()

        return sidebar

    def _add_stat_row(self, sidebar: gui.Vert, label: str, initial: str) -> gui.Label:
        row = gui.Horiz(0.5 * self.window.theme.font_size)
        row.add_child(gui.Label(label))
        value_label = gui.Label(initial)
        row.add_stretch()
        row.add_child(value_label)
        sidebar.add_child(row)
        return value_label

    def _setup_menu(self) -> None:
        menu = gui.Menu()

        file_menu = gui.Menu()
        file_menu.add_item("Open Model", self.MENU_OPEN)
        file_menu.add_separator()
        file_menu.add_item("Exit", self.MENU_EXIT)

        view_menu = gui.Menu()
        view_menu.add_item("Reset Camera", self.MENU_RESET_CAMERA)
        view_menu.add_item("Show Normals", self.MENU_SHOW_NORMALS)
        view_menu.set_checked(self.MENU_SHOW_NORMALS, False)

        menu.add_menu("File", file_menu)
        menu.add_menu("View", view_menu)
        gui.Application.instance.menubar = menu

        self.window.set_on_menu_item_activated(self.MENU_OPEN, self._on_open_model)
        self.window.set_on_menu_item_activated(self.MENU_EXIT, self._on_exit)
        self.window.set_on_menu_item_activated(
            self.MENU_RESET_CAMERA,
            self._reset_camera,
        )
        self.window.set_on_menu_item_activated(
            self.MENU_SHOW_NORMALS,
            self._toggle_show_normals,
        )

    def _on_layout(self, layout_context: gui.LayoutContext) -> None:
        content = self.window.content_rect
        em = layout_context.theme.font_size
        sidebar_width = int(19 * em)
        status_height = int(1.7 * em)
        viewport_height = max(0, content.height - status_height)

        self._sidebar.frame = gui.Rect(
            content.x,
            content.y,
            sidebar_width,
            viewport_height,
        )
        self._scene.frame = gui.Rect(
            content.x + sidebar_width,
            content.y,
            max(0, content.width - sidebar_width),
            viewport_height,
        )
        self._status.frame = gui.Rect(
            content.x + int(0.5 * em),
            content.y + viewport_height,
            content.width - int(em),
            status_height,
        )

    def _on_open_model(self) -> None:
        dialog = gui.FileDialog(
            gui.FileDialog.OPEN,
            "Open Model",
            self.window.theme,
        )
        dialog.add_filter(".stl .obj .ply", "Mesh files (.stl, .obj, .ply)")
        dialog.add_filter(".stl", "STL files (.stl)")
        dialog.add_filter(".obj", "OBJ files (.obj)")
        dialog.add_filter(".ply", "PLY files (.ply)")
        dialog.add_filter("", "All files")
        dialog.set_on_cancel(self._on_file_dialog_cancel)
        dialog.set_on_done(self._on_file_dialog_done)
        self.window.show_dialog(dialog)

    def _on_file_dialog_cancel(self) -> None:
        self.window.close_dialog()

    def _on_file_dialog_done(self, file_path: str) -> None:
        self.window.close_dialog()
        self.load_model(Path(file_path))

    def load_model(self, file_path: Path) -> None:
        self._set_status(f"Loading model: {file_path.name}")
        try:
            loaded = load_mesh(file_path)
        except (FileNotFoundError, ValueError, SystemExit) as exc:
            self._set_status("No model loaded")
            self.window.show_message_box("Could not open model", str(exc))
            return

        self.mesh_state = MeshState.from_loaded_mesh(loaded)
        self.section_result = None
        self.curve_results = []
        self._set_section_controls_enabled(True)
        self._update_stats()
        self._refresh_scene(reset_camera=True)
        self._set_status(f"Loaded model: {self.mesh_state.file_name}")

    def _on_compute_section(self) -> None:
        if not self.mesh_state.is_loaded or self.mesh_state.mesh is None:
            self._set_status("No model loaded")
            return

        axis = self._axis_dropdown.selected_text
        offset = float(self._offset_input.double_value)
        try:
            self.section_result = extract_section(
                self.mesh_state.mesh,
                axis=axis,
                offset=offset,
            )
            self.curve_results = fit_section_polylines(self.section_result.polylines)
        except ValueError as exc:
            self.window.show_message_box("Section failed", str(exc))
            return

        self._update_section_plane_label()
        self._refresh_scene(reset_camera=False)
        self._set_status(f"Section computed: {self.section_result.point_count} points")

    def _on_section_axis_changed(self, _text: str, _index: int) -> None:
        self._update_section_plane_label()

    def _on_section_offset_changed(self, _value: float) -> None:
        self._update_section_plane_label()

    def _toggle_show_normals(self) -> None:
        menubar = gui.Application.instance.menubar
        checked = not menubar.is_checked(self.MENU_SHOW_NORMALS)
        self._set_show_normals(checked)

    def _set_show_normals(self, checked: bool) -> None:
        self.show_normals = bool(checked)
        self._show_normals_checkbox.checked = self.show_normals
        gui.Application.instance.menubar.set_checked(
            self.MENU_SHOW_NORMALS,
            self.show_normals,
        )
        self._refresh_scene(reset_camera=False)

    def _on_exit(self) -> None:
        gui.Application.instance.quit()

    def _set_section_controls_enabled(self, enabled: bool) -> None:
        self._axis_dropdown.enabled = enabled
        self._offset_input.enabled = enabled
        self._compute_section_button.enabled = enabled

    def _reset_stats(self) -> None:
        self._file_name_label.text = "(none)"
        self._vertex_count_label.text = "0"
        self._triangle_count_label.text = "0"
        self._bbox_size_label.text = "-"

    def _update_stats(self) -> None:
        self._file_name_label.text = self.mesh_state.file_name or "(unnamed)"
        self._vertex_count_label.text = str(self.mesh_state.vertex_count)
        self._triangle_count_label.text = str(self.mesh_state.triangle_count)
        self._bbox_size_label.text = _format_vector(self.mesh_state.bounding_box_extent)

    def _update_section_plane_label(self) -> None:
        axis = self._axis_dropdown.selected_text or "Z"
        offset = float(self._offset_input.double_value)
        self._section_plane_label.text = f"Section: {axis} = {offset:.6g}"

    def _refresh_scene(self, *, reset_camera: bool) -> None:
        self._scene.scene.clear_geometry()

        if self.mesh_state.mesh is None:
            if reset_camera:
                self._reset_camera()
            self.window.post_redraw()
            return

        mesh = self.mesh_state.mesh
        if not mesh.has_vertex_colors():
            mesh.paint_uniform_color([0.72, 0.74, 0.78])

        self._scene.scene.add_geometry(
            self.MESH_GEOMETRY_NAME,
            mesh,
            _mesh_material(),
        )

        if self.show_normals:
            normal_lines = build_normal_lines(mesh, normal_scale=0.02)
            if normal_lines is not None:
                self._scene.scene.add_geometry(
                    self.NORMALS_GEOMETRY_NAME,
                    normal_lines,
                    _line_material([0.1, 0.45, 1.0, 1.0], line_width=1.0),
                )

        self._add_section_geometry()

        if reset_camera:
            self._reset_camera()

        self.window.post_redraw()

    def _add_section_geometry(self) -> None:
        if self.mesh_state.mesh is None or self.section_result is None:
            return

        mesh_extent = max(
            float(self.mesh_state.mesh.get_axis_aligned_bounding_box().get_max_extent()),
            1.0,
        )
        section_tubes = build_polyline_tubes(
            self.section_result.polylines,
            color=[1.0, 0.88, 0.05],
            radius=mesh_extent * 0.003,
        )
        for index, tube in enumerate(section_tubes):
            self._scene.scene.add_geometry(
                f"{self.SECTION_GEOMETRY_PREFIX}{index}",
                tube,
                _section_material(),
            )

        fitted_lines = build_polyline_lines(
            [result.fitted_points for result in self.curve_results],
            color=[0.1, 0.78, 0.28],
        )
        if fitted_lines is not None:
            self._scene.scene.add_geometry(
                self.FITTED_CURVE_GEOMETRY_NAME,
                fitted_lines,
                _line_material([0.1, 0.78, 0.28, 1.0], line_width=4.0),
            )

    def _reset_camera(self) -> None:
        if self.mesh_state.mesh is None:
            bounds = o3d.geometry.AxisAlignedBoundingBox(
                [-1.0, -1.0, -1.0],
                [1.0, 1.0, 1.0],
            )
        else:
            bounds = self.mesh_state.mesh.get_axis_aligned_bounding_box()

        self._scene.setup_camera(60.0, bounds, bounds.get_center())
        self.window.post_redraw()

    def _set_status(self, message: str) -> None:
        self._status.text = message


def run_app() -> int:
    app = gui.Application.instance
    app.initialize()
    OpenRetopWindow()
    app.run()
    return 0


def _mesh_material() -> rendering.MaterialRecord:
    material = rendering.MaterialRecord()
    material.shader = "defaultLit"
    material.base_color = [0.72, 0.74, 0.78, 1.0]
    material.base_roughness = 0.55
    return material


def _section_material() -> rendering.MaterialRecord:
    material = rendering.MaterialRecord()
    material.shader = "defaultLit"
    material.base_color = [1.0, 0.88, 0.05, 1.0]
    material.base_roughness = 0.35
    return material


def _line_material(
    color: Sequence[float],
    *,
    line_width: float,
) -> rendering.MaterialRecord:
    material = rendering.MaterialRecord()
    material.shader = "unlitLine"
    material.base_color = list(color)
    material.line_width = line_width
    return material


def _format_vector(values: Sequence[float]) -> str:
    return ", ".join(f"{value:.6g}" for value in values)
