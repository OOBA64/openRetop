"""Integrated Tk main window for openRetop."""

from __future__ import annotations

import copy
from math import cos, radians, sin
from pathlib import Path
from tkinter import BooleanVar, Canvas, DoubleVar, Menu, StringVar, Tk, filedialog
from tkinter import messagebox, ttk

import numpy as np

from geometry.curves import CurveFitResult, fit_section_polylines
from geometry.sections import AXIS_TO_INDEX, SECTION_AXES, SectionResult, extract_section
from mesh.loader import load_mesh
from mesh.mesh_state import MeshState
from viewer.embedded_viewport import EmbeddedOpen3DViewport


MESH_FILE_TYPES = (
    ("Mesh files", "*.stl *.obj *.ply"),
    ("STL files", "*.stl"),
    ("OBJ files", "*.obj"),
    ("PLY files", "*.ply"),
    ("All files", "*.*"),
)


class OpenRetopWindow:
    """One-window app with ordered controls and an embedded Open3D viewport."""

    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("openRetop")
        self.root.geometry("1280x800")
        self.root.minsize(980, 620)

        self.mesh_state = MeshState()
        self.original_mesh: object | None = None
        self.section_result: SectionResult | None = None
        self.curve_results: list[CurveFitResult] = []

        self.show_grid = BooleanVar(value=True)
        self.show_axes = BooleanVar(value=True)
        self.show_normals = BooleanVar(value=False)
        self.show_section_plane = BooleanVar(value=True)

        self.section_axis = StringVar(value="Z")
        self.section_offset = DoubleVar(value=0.0)
        self.section_offset_text = StringVar(value="0.000")
        self._section_offset_bounds = (-1.0, 1.0)
        self._updating_offset = False

        self.translate_x = StringVar(value="0.000")
        self.translate_y = StringVar(value="0.000")
        self.translate_z = StringVar(value="0.000")
        self.rotate_x = StringVar(value="0.000")
        self.rotate_y = StringVar(value="0.000")
        self.rotate_z = StringVar(value="0.000")
        self.scale_value = StringVar(value="1.000")

        self.status_text = StringVar(value="No model loaded")
        self.file_name_text = StringVar(value="(none)")
        self.vertex_count_text = StringVar(value="0")
        self.triangle_count_text = StringVar(value="0")
        self.bbox_size_text = StringVar(value="-")
        self.section_plane_text = StringVar(value="Section: Z = 0.000")
        self.section_result_text = StringVar(value="Section result: none")

        self._build_menu_bar()
        self._build_layout()
        self._set_mesh_controls_enabled(False)

        self.viewport = EmbeddedOpen3DViewport(self.viewport_frame)
        self.root.after(100, self._start_viewport)
        self.root.protocol("WM_DELETE_WINDOW", self._on_exit)

    def run(self) -> None:
        self.root.mainloop()

    def _start_viewport(self) -> None:
        try:
            self.viewport.start()
            self._refresh_viewport(reset_camera=True)
        except RuntimeError as exc:
            self.status_text.set("Viewport failed to start")
            messagebox.showerror("Viewport failed to start", str(exc))

    def _build_menu_bar(self) -> None:
        self.menu_bar = Menu(self.root, tearoff=False)

        self.file_menu = Menu(self.menu_bar, tearoff=False)
        self.file_menu.add_command(label="Open Model", command=self.open_model)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Exit", command=self._on_exit)
        self.menu_bar.add_cascade(label="File", menu=self.file_menu)

        self.view_menu = Menu(self.menu_bar, tearoff=False)
        self.view_menu.add_checkbutton(
            label="Show Grid",
            variable=self.show_grid,
            command=self._on_view_option_changed,
        )
        self.view_menu.add_checkbutton(
            label="Show Axes",
            variable=self.show_axes,
            command=self._on_view_option_changed,
        )
        self.view_menu.add_checkbutton(
            label="Show Normals",
            variable=self.show_normals,
            command=self._on_view_option_changed,
        )
        self.view_menu.add_separator()
        self.view_menu.add_command(label="Frame Model", command=self.frame_model)
        self.view_menu.add_command(label="Reset View", command=self.reset_view)
        self.menu_bar.add_cascade(label="View", menu=self.view_menu)
        self.root.configure(menu=self.menu_bar)

    def _build_layout(self) -> None:
        style = ttk.Style(self.root)
        style.configure("SidebarHeading.TLabel", font=("", 10, "bold"))

        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        sidebar_shell = ttk.Frame(main, width=320)
        sidebar_shell.grid(row=0, column=0, sticky="ns")
        sidebar_shell.grid_propagate(False)
        sidebar_shell.rowconfigure(0, weight=1)
        sidebar_shell.columnconfigure(0, weight=1)

        self.sidebar_canvas = Canvas(
            sidebar_shell,
            borderwidth=0,
            highlightthickness=0,
            width=318,
        )
        sidebar_scrollbar = ttk.Scrollbar(
            sidebar_shell,
            orient="vertical",
            command=self.sidebar_canvas.yview,
        )
        self.sidebar_canvas.configure(yscrollcommand=sidebar_scrollbar.set)
        self.sidebar_canvas.grid(row=0, column=0, sticky="nsew")
        sidebar_scrollbar.grid(row=0, column=1, sticky="ns")

        sidebar = ttk.Frame(self.sidebar_canvas, padding=12)
        sidebar.columnconfigure(1, weight=1)
        sidebar_window = self.sidebar_canvas.create_window(
            (0, 0),
            window=sidebar,
            anchor="nw",
        )
        sidebar.bind(
            "<Configure>",
            lambda _event: self.sidebar_canvas.configure(
                scrollregion=self.sidebar_canvas.bbox("all")
            ),
        )
        self.sidebar_canvas.bind(
            "<Configure>",
            lambda event: self.sidebar_canvas.itemconfigure(
                sidebar_window,
                width=event.width,
            ),
        )
        self.sidebar_canvas.bind_all("<MouseWheel>", self._on_sidebar_mousewheel)

        row = 0
        row = self._add_heading(sidebar, row, "File")
        self.open_model_button = ttk.Button(
            sidebar,
            text="Open Model",
            command=self.open_model,
        )
        self.open_model_button.grid(row=row, column=0, columnspan=2, sticky="ew")
        row += 1
        row = self._add_info_row(sidebar, row, "Loaded file", self.file_name_text)

        row = self._add_separator(sidebar, row)
        row = self._add_heading(sidebar, row, "Mesh Info")
        row = self._add_info_row(sidebar, row, "Vertices", self.vertex_count_text)
        row = self._add_info_row(sidebar, row, "Triangles", self.triangle_count_text)
        row = self._add_info_row(sidebar, row, "Bounding box", self.bbox_size_text)

        row = self._add_separator(sidebar, row)
        row = self._add_heading(sidebar, row, "View")
        self.show_grid_check = ttk.Checkbutton(
            sidebar,
            text="Show Grid",
            variable=self.show_grid,
            command=self._on_view_option_changed,
        )
        self.show_grid_check.grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        self.show_axes_check = ttk.Checkbutton(
            sidebar,
            text="Show Axes",
            variable=self.show_axes,
            command=self._on_view_option_changed,
        )
        self.show_axes_check.grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        self.show_normals_check = ttk.Checkbutton(
            sidebar,
            text="Show Normals",
            variable=self.show_normals,
            command=self._on_view_option_changed,
        )
        self.show_normals_check.grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        self.frame_model_button = ttk.Button(
            sidebar,
            text="Frame Model",
            command=self.frame_model,
        )
        self.frame_model_button.grid(row=row, column=0, columnspan=2, sticky="ew")
        row += 1
        self.reset_view_button = ttk.Button(
            sidebar,
            text="Reset View",
            command=self.reset_view,
        )
        self.reset_view_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        row += 1

        row = self._add_separator(sidebar, row)
        row = self._add_heading(sidebar, row, "Transform")
        self.transform_widgets: list[ttk.Widget] = []
        row = self._add_entry_row(sidebar, row, "Translate X", self.translate_x, self.transform_widgets)
        row = self._add_entry_row(sidebar, row, "Translate Y", self.translate_y, self.transform_widgets)
        row = self._add_entry_row(sidebar, row, "Translate Z", self.translate_z, self.transform_widgets)
        row = self._add_entry_row(sidebar, row, "Rotate X", self.rotate_x, self.transform_widgets)
        row = self._add_entry_row(sidebar, row, "Rotate Y", self.rotate_y, self.transform_widgets)
        row = self._add_entry_row(sidebar, row, "Rotate Z", self.rotate_z, self.transform_widgets)
        row = self._add_entry_row(sidebar, row, "Scale", self.scale_value, self.transform_widgets)
        self.apply_transform_button = ttk.Button(
            sidebar,
            text="Apply Transform",
            command=self.apply_transform,
        )
        self.apply_transform_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.transform_widgets.append(self.apply_transform_button)
        row += 1
        self.center_origin_button = ttk.Button(
            sidebar,
            text="Center Mesh at Origin",
            command=self.center_mesh_at_origin,
        )
        self.center_origin_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.transform_widgets.append(self.center_origin_button)
        row += 1
        self.reset_transform_button = ttk.Button(
            sidebar,
            text="Reset Transform",
            command=self.reset_transform,
        )
        self.reset_transform_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.transform_widgets.append(self.reset_transform_button)
        row += 1

        row = self._add_separator(sidebar, row)
        row = self._add_heading(sidebar, row, "Section Plane")
        self.section_widgets: list[ttk.Widget] = []
        self.show_section_plane_check = ttk.Checkbutton(
            sidebar,
            text="Show Section Plane",
            variable=self.show_section_plane,
            command=self._on_section_plane_visibility_changed,
        )
        self.show_section_plane_check.grid(row=row, column=0, columnspan=2, sticky="w")
        self.section_widgets.append(self.show_section_plane_check)
        row += 1
        self.axis_label = ttk.Label(sidebar, text="Axis")
        self.axis_label.grid(row=row, column=0, sticky="w", pady=2)
        self.axis_dropdown = ttk.Combobox(
            sidebar,
            textvariable=self.section_axis,
            values=SECTION_AXES,
            width=8,
            state="readonly",
        )
        self.axis_dropdown.grid(row=row, column=1, sticky="ew", pady=2)
        self.axis_dropdown.bind("<<ComboboxSelected>>", self._on_section_axis_changed)
        self.section_widgets.extend([self.axis_label, self.axis_dropdown])
        row += 1
        self.offset_slider_label = ttk.Label(sidebar, text="Offset slider")
        self.offset_slider_label.grid(row=row, column=0, sticky="w", pady=2)
        self.offset_slider = ttk.Scale(
            sidebar,
            variable=self.section_offset,
            from_=-1.0,
            to=1.0,
            command=self._on_offset_slider_changed,
        )
        self.offset_slider.grid(row=row, column=1, sticky="ew", pady=2)
        self.section_widgets.extend([self.offset_slider_label, self.offset_slider])
        row += 1
        self.offset_input_label = ttk.Label(sidebar, text="Offset")
        self.offset_input_label.grid(row=row, column=0, sticky="w", pady=2)
        self.offset_input = ttk.Entry(
            sidebar,
            textvariable=self.section_offset_text,
            width=10,
        )
        self.offset_input.grid(row=row, column=1, sticky="ew", pady=2)
        self.offset_input.bind("<KeyRelease>", self._on_offset_input_changed)
        self.offset_input.bind("<FocusOut>", self._on_offset_input_changed)
        self.section_widgets.extend([self.offset_input_label, self.offset_input])
        row += 1
        self.section_plane_label = ttk.Label(
            sidebar,
            textvariable=self.section_plane_text,
        )
        self.section_plane_label.grid(row=row, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.section_widgets.append(self.section_plane_label)
        row += 1
        self.section_result_label = ttk.Label(
            sidebar,
            textvariable=self.section_result_text,
        )
        self.section_result_label.grid(row=row, column=0, columnspan=2, sticky="w", pady=(2, 4))
        self.section_widgets.append(self.section_result_label)
        row += 1
        self.compute_section_button = ttk.Button(
            sidebar,
            text="Compute Section",
            command=self.compute_section,
        )
        self.compute_section_button.grid(row=row, column=0, columnspan=2, sticky="ew")
        self.section_widgets.append(self.compute_section_button)
        row += 1
        self.clear_section_button = ttk.Button(
            sidebar,
            text="Clear Section",
            command=self.clear_section,
        )
        self.clear_section_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.section_widgets.append(self.clear_section_button)
        row += 1

        self.viewport_frame = ttk.Frame(main)
        self.viewport_frame.grid(row=0, column=1, sticky="nsew")

        status_bar = ttk.Label(
            self.root,
            textvariable=self.status_text,
            anchor="w",
            padding=(8, 4),
        )
        status_bar.pack(fill="x", side="bottom")

    def _add_heading(self, parent: ttk.Frame, row: int, text: str) -> int:
        ttk.Label(parent, text=text, style="SidebarHeading.TLabel").grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 6),
        )
        return row + 1

    def _add_separator(self, parent: ttk.Frame, row: int) -> int:
        ttk.Separator(parent).grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=10,
        )
        return row + 1

    def _add_info_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        value: StringVar,
    ) -> int:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Label(parent, textvariable=value, wraplength=150).grid(
            row=row,
            column=1,
            sticky="w",
            pady=2,
            padx=(8, 0),
        )
        return row + 1

    def _add_entry_row(
        self,
        parent: ttk.Frame,
        row: int,
        label_text: str,
        value: StringVar,
        widget_list: list[ttk.Widget],
    ) -> int:
        label = ttk.Label(parent, text=label_text)
        label.grid(row=row, column=0, sticky="w", pady=2)
        entry = ttk.Entry(parent, textvariable=value, width=10)
        entry.grid(row=row, column=1, sticky="ew", pady=2)
        widget_list.extend([label, entry])
        return row + 1

    def _on_sidebar_mousewheel(self, event: object) -> None:
        delta = getattr(event, "delta", 0)
        if delta:
            self.sidebar_canvas.yview_scroll(int(-1 * (delta / 120)), "units")

    def open_model(self) -> None:
        selected_path = filedialog.askopenfilename(
            title="Open Model",
            filetypes=MESH_FILE_TYPES,
        )
        if not selected_path:
            return

        self.load_model(Path(selected_path))

    def load_model(self, file_path: Path) -> None:
        self.status_text.set(f"Loading: {file_path.name}")
        self.root.update_idletasks()

        try:
            loaded = load_mesh(file_path)
        except (FileNotFoundError, ValueError, SystemExit) as exc:
            self.status_text.set("No model loaded")
            messagebox.showerror("Could not open model", str(exc))
            return

        self.original_mesh = copy.deepcopy(loaded.mesh)
        current_mesh = copy.deepcopy(self.original_mesh)
        self.mesh_state = MeshState.from_mesh(
            current_mesh,
            file_path=loaded.metadata.file_path,
            metadata=loaded.metadata,
        )
        self.section_result = None
        self.curve_results = []
        self.section_result_text.set("Section result: none")
        self._reset_transform_inputs()
        self._set_mesh_controls_enabled(True)
        self._update_stats()
        self._configure_offset_range(reset=True)
        self._update_section_plane_label(set_status=False)
        self._refresh_viewport(reset_camera=True)
        self.status_text.set(f"Loaded: {self.mesh_state.file_name}")

    def compute_section(self) -> None:
        if not self.mesh_state.is_loaded or self.mesh_state.mesh is None:
            self.status_text.set("No model loaded")
            return

        offset = self._parse_offset()
        if offset is None:
            return

        self.section_result = extract_section(
            self.mesh_state.mesh,
            axis=self.section_axis.get(),
            offset=offset,
        )
        self.curve_results = fit_section_polylines(self.section_result.polylines)
        self.section_result_text.set(
            f"Section result: {self.section_result.segment_count} segments"
        )
        self._update_section_plane_label(set_status=False)
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(
            f"Section computed: {self.section_result.segment_count} segments"
        )

    def clear_section(self) -> None:
        self.section_result = None
        self.curve_results = []
        self.section_result_text.set("Section result: none")
        self._refresh_viewport(reset_camera=False)
        self.status_text.set("Section cleared")

    def apply_transform(self) -> None:
        transform_values = self._parse_transform_values()
        if transform_values is None:
            return

        self._apply_transform_values(transform_values)
        self.status_text.set("Transform applied")

    def center_mesh_at_origin(self) -> None:
        if not self.mesh_state.is_loaded or self.mesh_state.mesh is None:
            self.status_text.set("No model loaded")
            return

        transform_values = self._parse_transform_values()
        if transform_values is None:
            return

        center = np.asarray(
            self.mesh_state.mesh.get_axis_aligned_bounding_box().get_center(),
            dtype=float,
        )
        tx, ty, tz, rx, ry, rz, scale = transform_values
        centered_values = (tx - center[0], ty - center[1], tz - center[2], rx, ry, rz, scale)
        self._set_transform_inputs(centered_values)
        self._apply_transform_values(centered_values, reset_camera=True)
        self.status_text.set("Centered mesh at origin")

    def reset_transform(self) -> None:
        if self.original_mesh is None:
            self.status_text.set("No model loaded")
            return

        self._reset_transform_inputs()
        reset_values = self._parse_transform_values()
        if reset_values is None:
            return

        self._apply_transform_values(reset_values, reset_camera=True)
        self.status_text.set("Transform reset")

    def frame_model(self) -> None:
        self.viewport.frame_model()
        self.status_text.set("View framed")

    def reset_view(self) -> None:
        self.viewport.reset_view()
        self.status_text.set("View reset")

    def reset_camera(self) -> None:
        self.reset_view()

    def _refresh_viewport(self, *, reset_camera: bool) -> None:
        self.viewport.set_scene(
            self.mesh_state.mesh,
            show_grid=self.show_grid.get(),
            show_axes=self.show_axes.get(),
            show_normals=self.show_normals.get(),
            show_section_plane=(
                self.show_section_plane.get() and self.mesh_state.is_loaded
            ),
            section_axis=self.section_axis.get(),
            section_offset=self.section_offset.get(),
            section_result=self.section_result,
            curve_results=self.curve_results,
            reset_camera=reset_camera,
        )

    def _on_view_option_changed(self) -> None:
        self._refresh_viewport(reset_camera=False)

    def _on_section_plane_visibility_changed(self) -> None:
        self._refresh_viewport(reset_camera=False)

    def _on_section_axis_changed(self, _event: object | None = None) -> None:
        self._configure_offset_range(reset=False)
        self._update_section_plane_label(set_status=True)
        self._clear_section_for_plane_change()
        self._refresh_viewport(reset_camera=False)

    def _on_offset_slider_changed(self, value: object) -> None:
        if self._updating_offset:
            return

        self._set_section_offset(float(value), clamp=False, refresh=True)

    def _on_offset_input_changed(self, _event: object | None = None) -> None:
        if self._updating_offset:
            return

        offset = self._parse_offset(show_error=False)
        if offset is None:
            return

        self._set_section_offset(offset, clamp=True, refresh=True)

    def _parse_offset(self, *, show_error: bool = True) -> float | None:
        try:
            return float(self.section_offset_text.get())
        except ValueError:
            if show_error:
                messagebox.showerror("Section failed", "Offset must be a number.")
            return None

    def _set_section_offset(
        self,
        offset: float,
        *,
        clamp: bool,
        refresh: bool,
    ) -> None:
        minimum, maximum = self._section_offset_bounds
        next_offset = min(max(float(offset), minimum), maximum) if clamp else float(offset)
        self._updating_offset = True
        try:
            self.section_offset.set(next_offset)
            self.section_offset_text.set(f"{next_offset:.3f}")
        finally:
            self._updating_offset = False

        self._update_section_plane_label(set_status=True)
        self._clear_section_for_plane_change()
        if refresh:
            self._refresh_viewport(reset_camera=False)

    def _configure_offset_range(self, *, reset: bool) -> None:
        if not self.mesh_state.is_loaded or self.mesh_state.mesh is None:
            self._section_offset_bounds = (-1.0, 1.0)
            self.offset_slider.configure(from_=-1.0, to=1.0)
            self._set_section_offset(0.0, clamp=True, refresh=False)
            return

        axis_index = AXIS_TO_INDEX[self.section_axis.get()]
        bounds = self.mesh_state.mesh.get_axis_aligned_bounding_box()
        minimum = float(bounds.get_min_bound()[axis_index])
        maximum = float(bounds.get_max_bound()[axis_index])
        if abs(maximum - minimum) <= 1e-9:
            minimum -= 1.0
            maximum += 1.0

        self._section_offset_bounds = (minimum, maximum)
        self.offset_slider.configure(from_=minimum, to=maximum)

        current = self.section_offset.get()
        if reset:
            current = 0.0 if minimum <= 0.0 <= maximum else (minimum + maximum) * 0.5

        self._set_section_offset(current, clamp=True, refresh=False)

    def _update_section_plane_label(self, *, set_status: bool) -> None:
        axis = self.section_axis.get()
        offset = self.section_offset.get()
        plane_text = f"Section: {axis} = {offset:.3f}"
        self.section_plane_text.set(plane_text)
        if set_status and self.mesh_state.is_loaded:
            self.status_text.set(f"Section plane: {axis} = {offset:.3f}")

    def _clear_section_for_plane_change(self) -> None:
        if self.section_result is None and not self.curve_results:
            return

        self.section_result = None
        self.curve_results = []
        self.section_result_text.set("Section result: none")

    def _parse_transform_values(
        self,
    ) -> tuple[float, float, float, float, float, float, float] | None:
        try:
            tx = float(self.translate_x.get())
            ty = float(self.translate_y.get())
            tz = float(self.translate_z.get())
            rx = float(self.rotate_x.get())
            ry = float(self.rotate_y.get())
            rz = float(self.rotate_z.get())
            scale = float(self.scale_value.get())
        except ValueError:
            messagebox.showerror("Transform failed", "Transform values must be numbers.")
            return None

        if scale <= 0.0:
            messagebox.showerror("Transform failed", "Scale must be greater than zero.")
            return None

        return (tx, ty, tz, rx, ry, rz, scale)

    def _apply_transform_values(
        self,
        values: tuple[float, float, float, float, float, float, float],
        *,
        reset_camera: bool = False,
    ) -> None:
        if self.original_mesh is None:
            self.status_text.set("No model loaded")
            return

        mesh = copy.deepcopy(self.original_mesh)
        mesh.transform(_build_transform_matrix(values))
        if hasattr(mesh, "compute_vertex_normals"):
            mesh.compute_vertex_normals()
        if hasattr(mesh, "compute_triangle_normals"):
            mesh.compute_triangle_normals()

        self.mesh_state = MeshState.from_mesh(mesh, file_path=self.mesh_state.file_path)
        self.section_result = None
        self.curve_results = []
        self.section_result_text.set("Section result: none")
        self._update_stats()
        self._configure_offset_range(reset=False)
        self._refresh_viewport(reset_camera=reset_camera)

    def _set_transform_inputs(
        self,
        values: tuple[float, float, float, float, float, float, float],
    ) -> None:
        tx, ty, tz, rx, ry, rz, scale = values
        self.translate_x.set(f"{tx:.3f}")
        self.translate_y.set(f"{ty:.3f}")
        self.translate_z.set(f"{tz:.3f}")
        self.rotate_x.set(f"{rx:.3f}")
        self.rotate_y.set(f"{ry:.3f}")
        self.rotate_z.set(f"{rz:.3f}")
        self.scale_value.set(f"{scale:.3f}")

    def _reset_transform_inputs(self) -> None:
        self._set_transform_inputs((0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0))

    def _update_stats(self) -> None:
        self.file_name_text.set(self.mesh_state.file_name or "(unnamed)")
        self.vertex_count_text.set(str(self.mesh_state.vertex_count))
        self.triangle_count_text.set(str(self.mesh_state.triangle_count))
        self.bbox_size_text.set(_format_vector(self.mesh_state.bounding_box_extent))

    def _set_mesh_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        combo_state = "readonly" if enabled else "disabled"
        for widget in self.transform_widgets:
            widget.configure(state=state)
        for widget in self.section_widgets:
            widget.configure(state=state)
        self.axis_dropdown.configure(state=combo_state)

    def _on_exit(self) -> None:
        self.sidebar_canvas.unbind_all("<MouseWheel>")
        self.viewport.close()
        self.root.destroy()


def run_app() -> int:
    OpenRetopWindow().run()
    return 0


def _format_vector(values: object) -> str:
    return ", ".join(f"{float(value):.6g}" for value in values)


def _build_transform_matrix(
    values: tuple[float, float, float, float, float, float, float],
) -> np.ndarray:
    tx, ty, tz, rx, ry, rz, scale = values
    sx = sy = sz = scale
    matrix = np.identity(4)
    matrix[0, 0] = sx
    matrix[1, 1] = sy
    matrix[2, 2] = sz

    rotation = _rotation_z(rz) @ _rotation_y(ry) @ _rotation_x(rx)
    matrix = rotation @ matrix
    matrix[0, 3] = tx
    matrix[1, 3] = ty
    matrix[2, 3] = tz
    return matrix


def _rotation_x(angle_degrees: float) -> np.ndarray:
    angle = radians(angle_degrees)
    c = cos(angle)
    s = sin(angle)
    return np.asarray(
        [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, c, -s, 0.0],
            [0.0, s, c, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=float,
    )


def _rotation_y(angle_degrees: float) -> np.ndarray:
    angle = radians(angle_degrees)
    c = cos(angle)
    s = sin(angle)
    return np.asarray(
        [
            [c, 0.0, s, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [-s, 0.0, c, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=float,
    )


def _rotation_z(angle_degrees: float) -> np.ndarray:
    angle = radians(angle_degrees)
    c = cos(angle)
    s = sin(angle)
    return np.asarray(
        [
            [c, -s, 0.0, 0.0],
            [s, c, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=float,
    )
