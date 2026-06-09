"""Integrated Tk main window for openRetop."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from math import cos, radians, sin
from pathlib import Path
from tkinter import BooleanVar, Canvas, DoubleVar, Menu, StringVar, Tk, filedialog
from tkinter import messagebox, ttk

import numpy as np

from geometry.curves import CurveFitResult, fit_section_polylines
from geometry.sections import AXIS_TO_INDEX, SECTION_AXES, SectionResult, extract_section
from mesh.loader import load_mesh
from mesh.mesh_state import MeshState
from viewer.embedded_viewport import EmbeddedVTKViewport


MESH_FILE_TYPES = (
    ("Mesh files", "*.stl *.obj *.ply"),
    ("STL files", "*.stl"),
    ("OBJ files", "*.obj"),
    ("PLY files", "*.ply"),
    ("All files", "*.*"),
)
SELECT_MODEL = "model"
SELECT_SECTION_PLANE = "section_plane"


@dataclass
class MeshObjectState:
    """Selection-oriented state for the loaded mesh object."""

    raw_mesh: object
    file_path: Path | None
    name: str
    origin: np.ndarray
    location: np.ndarray
    rotation: np.ndarray
    scale: float = 1.0


class OpenRetopWindow:
    """One-window app with context-sensitive selection controls."""

    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("openRetop")
        self.root.geometry("1280x800")
        self.root.minsize(980, 620)

        self.mesh_state = MeshState()
        self.mesh_object: MeshObjectState | None = None
        self.selected_item: str | None = None
        self.active_transform_mode: str | None = None
        self.active_transform_axis: str | None = None
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

        self.location_x = StringVar(value="0.000")
        self.location_y = StringVar(value="0.000")
        self.location_z = StringVar(value="0.000")
        self.rotation_x = StringVar(value="0.000")
        self.rotation_y = StringVar(value="0.000")
        self.rotation_z = StringVar(value="0.000")
        self.scale_value = StringVar(value="1.000")

        self.status_text = StringVar(value="No selection")
        self.file_name_text = StringVar(value="(none)")
        self.vertex_count_text = StringVar(value="0")
        self.triangle_count_text = StringVar(value="0")
        self.bbox_size_text = StringVar(value="-")
        self.selected_object_text = StringVar(value="(none)")
        self.selected_vertex_count_text = StringVar(value="0")
        self.selected_triangle_count_text = StringVar(value="0")
        self.selected_bbox_size_text = StringVar(value="-")
        self.section_plane_text = StringVar(value="Section: Z = 0.000")
        self.section_result_text = StringVar(value="Section result: none")
        self.selection_buttons: list[ttk.Button] = []

        self._build_menu_bar()
        self._build_layout()
        self._set_selection_buttons_enabled(False)
        self._show_context(None)
        self._bind_keyboard_shortcuts()

        self.viewport = EmbeddedVTKViewport(self.viewport_frame)
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
        self.view_menu.add_command(label="Frame All", command=self.frame_all)
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

        self.sidebar = ttk.Frame(self.sidebar_canvas, padding=12)
        self.sidebar.columnconfigure(0, weight=1)
        sidebar_window = self.sidebar_canvas.create_window(
            (0, 0),
            window=self.sidebar,
            anchor="nw",
        )
        self.sidebar.bind(
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
        self.file_frame = ttk.Frame(self.sidebar)
        self.file_frame.grid(row=row, column=0, sticky="ew")
        self.file_frame.columnconfigure(1, weight=1)
        self._build_file_section(self.file_frame)
        row += 1

        self.no_selection_frame = ttk.Frame(self.sidebar)
        self.no_selection_frame.grid(row=row, column=0, sticky="ew")
        self.no_selection_frame.columnconfigure(0, weight=1)
        self._build_no_selection_context(self.no_selection_frame)

        self.model_context_frame = ttk.Frame(self.sidebar)
        self.model_context_frame.grid(row=row, column=0, sticky="ew")
        self.model_context_frame.columnconfigure(0, weight=1)
        self._build_model_context(self.model_context_frame)

        self.section_context_frame = ttk.Frame(self.sidebar)
        self.section_context_frame.grid(row=row, column=0, sticky="ew")
        self.section_context_frame.columnconfigure(0, weight=1)
        self._build_section_context(self.section_context_frame)

        self.viewport_frame = ttk.Frame(main)
        self.viewport_frame.grid(row=0, column=1, sticky="nsew")

        status_bar = ttk.Label(
            self.root,
            textvariable=self.status_text,
            anchor="w",
            padding=(8, 4),
        )
        status_bar.pack(fill="x", side="bottom")

    def _build_file_section(self, parent: ttk.Frame) -> None:
        row = self._add_heading(parent, 0, "File")
        self.open_model_button = ttk.Button(
            parent,
            text="Open Model",
            command=self.open_model,
        )
        self.open_model_button.grid(row=row, column=0, columnspan=2, sticky="ew")
        row += 1
        self._add_info_row(parent, row, "Loaded file", self.file_name_text)

    def _build_no_selection_context(self, parent: ttk.Frame) -> None:
        row = self._add_separator(parent, 0)
        row = self._add_heading(parent, row, "Scene/View")
        self.show_grid_check = ttk.Checkbutton(
            parent,
            text="Show Grid",
            variable=self.show_grid,
            command=self._on_view_option_changed,
        )
        self.show_grid_check.grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        self.show_axes_check = ttk.Checkbutton(
            parent,
            text="Show Axes",
            variable=self.show_axes,
            command=self._on_view_option_changed,
        )
        self.show_axes_check.grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        self.show_normals_check = ttk.Checkbutton(
            parent,
            text="Show Normals",
            variable=self.show_normals,
            command=self._on_view_option_changed,
        )
        self.show_normals_check.grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        ttk.Button(parent, text="Frame All", command=self.frame_all).grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        row += 1
        ttk.Button(parent, text="Reset View", command=self.reset_view).grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        row += 1
        self.select_model_button = ttk.Button(
            parent,
            text="Select Model",
            command=self.select_model,
        )
        self.select_model_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(8, 0),
        )
        self.selection_buttons.append(self.select_model_button)
        row += 1
        self.select_section_plane_button = ttk.Button(
            parent,
            text="Select Section Plane",
            command=self.select_section_plane,
        )
        self.select_section_plane_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        self.selection_buttons.append(self.select_section_plane_button)
        row += 1

        row = self._add_separator(parent, row)
        row = self._add_heading(parent, row, "Mesh Info")
        row = self._add_info_row(parent, row, "Vertices", self.vertex_count_text)
        row = self._add_info_row(parent, row, "Triangles", self.triangle_count_text)
        self._add_info_row(parent, row, "Bounding box", self.bbox_size_text)

    def _build_model_context(self, parent: ttk.Frame) -> None:
        row = self._add_separator(parent, 0)
        row = self._add_heading(parent, row, "Selected Object")
        row = self._add_info_row(parent, row, "Object", self.selected_object_text)
        row = self._add_info_row(parent, row, "Vertices", self.selected_vertex_count_text)
        row = self._add_info_row(parent, row, "Triangles", self.selected_triangle_count_text)
        row = self._add_info_row(parent, row, "Bounding box", self.selected_bbox_size_text)

        row = self._add_separator(parent, row)
        row = self._add_heading(parent, row, "Object Transform")
        self.object_transform_widgets: list[ttk.Widget] = []
        row = self._add_transform_entry(parent, row, "Location X", self.location_x)
        row = self._add_transform_entry(parent, row, "Location Y", self.location_y)
        row = self._add_transform_entry(parent, row, "Location Z", self.location_z)
        row = self._add_transform_entry(parent, row, "Rotation X", self.rotation_x)
        row = self._add_transform_entry(parent, row, "Rotation Y", self.rotation_y)
        row = self._add_transform_entry(parent, row, "Rotation Z", self.rotation_z)
        row = self._add_transform_entry(parent, row, "Scale", self.scale_value)

        row = self._add_separator(parent, row)
        row = self._add_heading(parent, row, "Origin/Pivot")
        self.set_origin_geometry_button = ttk.Button(
            parent,
            text="Set Origin to Geometry",
            command=self.set_origin_to_geometry,
        )
        self.set_origin_geometry_button.grid(row=row, column=0, columnspan=2, sticky="ew")
        row += 1
        self.origin_world_button = ttk.Button(
            parent,
            text="Move Object Origin to World Origin",
            command=self.move_origin_to_world_origin,
        )
        self.origin_world_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        row += 1
        self.center_geometry_button = ttk.Button(
            parent,
            text="Center Geometry on Origin",
            command=self.center_geometry_on_origin,
        )
        self.center_geometry_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        row += 1
        self.reset_object_button = ttk.Button(
            parent,
            text="Reset Object Transform",
            command=self.reset_object_transform,
        )
        self.reset_object_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        row += 1
        self.frame_selected_button = ttk.Button(
            parent,
            text="Frame Selected",
            command=self.frame_selected,
        )
        self.frame_selected_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        row += 1
        self.model_select_section_plane_button = ttk.Button(
            parent,
            text="Select Section Plane",
            command=self.select_section_plane,
        )
        self.model_select_section_plane_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(8, 0),
        )
        self.selection_buttons.append(self.model_select_section_plane_button)
        row += 1
        self.model_deselect_button = ttk.Button(
            parent,
            text="Deselect",
            command=self.clear_selection,
        )
        self.model_deselect_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.selection_buttons.append(self.model_deselect_button)

    def _build_section_context(self, parent: ttk.Frame) -> None:
        row = self._add_separator(parent, 0)
        row = self._add_heading(parent, row, "Section Plane")
        self.show_section_plane_check = ttk.Checkbutton(
            parent,
            text="Show Section Plane",
            variable=self.show_section_plane,
            command=self._on_section_plane_visibility_changed,
        )
        self.show_section_plane_check.grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        self.axis_label = ttk.Label(parent, text="Axis")
        self.axis_label.grid(row=row, column=0, sticky="w", pady=2)
        self.axis_dropdown = ttk.Combobox(
            parent,
            textvariable=self.section_axis,
            values=SECTION_AXES,
            width=8,
            state="readonly",
        )
        self.axis_dropdown.grid(row=row, column=1, sticky="ew", pady=2)
        self.axis_dropdown.bind("<<ComboboxSelected>>", self._on_section_axis_changed)
        row += 1

        self.offset_slider_label = ttk.Label(parent, text="Offset slider")
        self.offset_slider_label.grid(row=row, column=0, sticky="w", pady=2)
        self.offset_slider = ttk.Scale(
            parent,
            variable=self.section_offset,
            from_=-1.0,
            to=1.0,
            command=self._on_offset_slider_changed,
        )
        self.offset_slider.grid(row=row, column=1, sticky="ew", pady=2)
        row += 1

        self.offset_input_label = ttk.Label(parent, text="Offset")
        self.offset_input_label.grid(row=row, column=0, sticky="w", pady=2)
        self.offset_input = ttk.Entry(
            parent,
            textvariable=self.section_offset_text,
            width=10,
        )
        self.offset_input.grid(row=row, column=1, sticky="ew", pady=2)
        self.offset_input.bind("<KeyRelease>", self._on_offset_input_changed)
        self.offset_input.bind("<FocusOut>", self._on_offset_input_changed)
        row += 1

        self.section_plane_label = ttk.Label(parent, textvariable=self.section_plane_text)
        self.section_plane_label.grid(row=row, column=0, columnspan=2, sticky="w", pady=(4, 0))
        row += 1
        self.section_result_label = ttk.Label(parent, textvariable=self.section_result_text)
        self.section_result_label.grid(row=row, column=0, columnspan=2, sticky="w", pady=(2, 4))
        row += 1
        self.compute_section_button = ttk.Button(
            parent,
            text="Compute Section",
            command=self.compute_section,
        )
        self.compute_section_button.grid(row=row, column=0, columnspan=2, sticky="ew")
        row += 1
        self.clear_section_button = ttk.Button(
            parent,
            text="Clear Section",
            command=self.clear_section,
        )
        self.clear_section_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        row += 1
        self.section_select_model_button = ttk.Button(
            parent,
            text="Select Model",
            command=self.select_model,
        )
        self.section_select_model_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(8, 0),
        )
        self.selection_buttons.append(self.section_select_model_button)
        row += 1
        self.section_deselect_button = ttk.Button(
            parent,
            text="Deselect",
            command=self.clear_selection,
        )
        self.section_deselect_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.selection_buttons.append(self.section_deselect_button)

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

    def _add_transform_entry(
        self,
        parent: ttk.Frame,
        row: int,
        label_text: str,
        value: StringVar,
    ) -> int:
        label = ttk.Label(parent, text=label_text)
        label.grid(row=row, column=0, sticky="w", pady=2)
        entry = ttk.Entry(parent, textvariable=value, width=10)
        entry.grid(row=row, column=1, sticky="ew", pady=2)
        entry.bind("<KeyRelease>", self._on_object_transform_changed)
        entry.bind("<FocusOut>", self._on_object_transform_changed)
        self.object_transform_widgets.extend([label, entry])
        return row + 1

    def _show_context(self, selected_item: str | None) -> None:
        for frame in (
            self.no_selection_frame,
            self.model_context_frame,
            self.section_context_frame,
        ):
            frame.grid_remove()

        if selected_item == SELECT_MODEL and self.mesh_object is not None:
            self.model_context_frame.grid()
        elif selected_item == SELECT_SECTION_PLANE and self.mesh_object is not None:
            self.section_context_frame.grid()
        else:
            self.no_selection_frame.grid()

    def _on_sidebar_mousewheel(self, event: object) -> None:
        delta = getattr(event, "delta", 0)
        if delta:
            self.sidebar_canvas.yview_scroll(int(-1 * (delta / 120)), "units")

    def _bind_keyboard_shortcuts(self) -> None:
        self.root.bind_all("<KeyPress>", self._on_tk_keypress)

    def _on_tk_keypress(self, event: object) -> None:
        focused = self.root.focus_get()
        if isinstance(focused, (ttk.Entry, ttk.Combobox)):
            return

        key = getattr(event, "keysym", "")
        key_map = {
            "g": "G",
            "r": "R",
            "x": "X",
            "y": "Y",
            "z": "Z",
            "f": "F",
            "Escape": "Escape",
            "Return": "Enter",
            "Delete": "Delete",
        }
        if key in key_map:
            self._handle_shortcut(key_map[key])

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
            self.status_text.set("No selection")
            messagebox.showerror("Could not open model", str(exc))
            return

        raw_mesh = copy.deepcopy(loaded.mesh)
        bounds = raw_mesh.get_axis_aligned_bounding_box()
        origin = np.asarray(bounds.get_center(), dtype=float)
        self.mesh_object = MeshObjectState(
            raw_mesh=raw_mesh,
            file_path=loaded.metadata.file_path,
            name=loaded.metadata.file_name,
            origin=origin,
            location=origin.copy(),
            rotation=np.asarray([0.0, 0.0, 0.0], dtype=float),
            scale=1.0,
        )
        self.section_result = None
        self.curve_results = []
        self.section_result_text.set("Section result: none")
        self._set_transform_inputs_from_object()
        self._apply_object_transform(reset_camera=False)
        self._configure_offset_range(reset=True)
        self._update_section_plane_label(set_status=False)
        self._set_selection_buttons_enabled(True)
        self._set_selected_item(None, status="No selection")
        self._refresh_viewport(reset_camera=True)

    def select_model(self) -> None:
        if self.mesh_object is None:
            self._set_selected_item(None, status="No selection")
            return

        self._set_selected_item(SELECT_MODEL, status=f"Selected: {self.mesh_object.name}")

    def select_section_plane(self) -> None:
        if self.mesh_object is None:
            self._set_selected_item(None, status="No selection")
            return

        self._set_selected_item(SELECT_SECTION_PLANE, status="Selected: Section Plane")

    def clear_selection(self) -> None:
        self._set_selected_item(None, status="No selection")

    def _set_selected_item(self, selected_item: str | None, *, status: str | None = None) -> None:
        self.selected_item = selected_item
        self.active_transform_mode = None
        self.active_transform_axis = None
        self._show_context(selected_item)
        self._refresh_viewport(reset_camera=False)
        if status is not None:
            self.status_text.set(status)

    def _on_viewport_selection(self, selected_item: str | None) -> None:
        if selected_item == SELECT_MODEL:
            self.select_model()
        elif selected_item == SELECT_SECTION_PLANE:
            self.select_section_plane()
        else:
            self.clear_selection()

    def compute_section(self) -> None:
        if not self.mesh_state.is_loaded or self.mesh_state.mesh is None:
            self.status_text.set("No selection")
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

    def frame_all(self) -> None:
        self.viewport.frame_model()
        self.status_text.set("View framed")

    def frame_selected(self) -> None:
        if self.selected_item == SELECT_MODEL:
            self.viewport.frame_model()
            self.status_text.set(f"Selected: {self.mesh_object.name}")
        elif self.selected_item == SELECT_SECTION_PLANE:
            self.viewport.frame_model()
            self.status_text.set("Selected: Section Plane")
        else:
            self.status_text.set("No selection")

    def reset_view(self) -> None:
        self.viewport.reset_view()
        self.status_text.set("View reset")

    def reset_camera(self) -> None:
        self.reset_view()

    def _refresh_viewport(self, *, reset_camera: bool) -> None:
        origin = self.mesh_object.location if self.mesh_object is not None else None
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
            selected_item=self.selected_item,
            object_origin=origin,
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
        self.section_plane_text.set(f"Section: {axis} = {offset:.3f}")
        if set_status and self.selected_item == SELECT_SECTION_PLANE:
            self.status_text.set(f"Section plane: {axis} = {offset:.3f}")

    def _clear_section_for_plane_change(self) -> None:
        if self.section_result is None and not self.curve_results:
            return

        self.section_result = None
        self.curve_results = []
        self.section_result_text.set("Section result: none")

    def _on_object_transform_changed(self, _event: object | None = None) -> None:
        if self.selected_item != SELECT_MODEL or self.mesh_object is None:
            return

        values = self._parse_object_transform(show_error=False)
        if values is None:
            return

        location, rotation, scale = values
        self.mesh_object.location = location
        self.mesh_object.rotation = rotation
        self.mesh_object.scale = scale
        self._apply_object_transform(reset_camera=False)
        self.status_text.set("Transforms update live")

    def _parse_object_transform(
        self,
        *,
        show_error: bool,
    ) -> tuple[np.ndarray, np.ndarray, float] | None:
        try:
            location = np.asarray(
                [
                    float(self.location_x.get()),
                    float(self.location_y.get()),
                    float(self.location_z.get()),
                ],
                dtype=float,
            )
            rotation = np.asarray(
                [
                    float(self.rotation_x.get()),
                    float(self.rotation_y.get()),
                    float(self.rotation_z.get()),
                ],
                dtype=float,
            )
            scale = float(self.scale_value.get())
        except ValueError:
            if show_error:
                messagebox.showerror("Transform failed", "Transform values must be numbers.")
            return None

        if scale <= 0.0:
            if show_error:
                messagebox.showerror("Transform failed", "Scale must be greater than zero.")
            return None

        return (location, rotation, scale)

    def _apply_object_transform(self, *, reset_camera: bool) -> None:
        if self.mesh_object is None:
            self.mesh_state = MeshState()
            self._update_stats()
            self._refresh_viewport(reset_camera=reset_camera)
            return

        mesh = copy.deepcopy(self.mesh_object.raw_mesh)
        matrix = _build_object_transform_matrix(
            self.mesh_object.location,
            self.mesh_object.rotation,
            self.mesh_object.scale,
            self.mesh_object.origin,
        )
        mesh.transform(matrix)
        if hasattr(mesh, "compute_vertex_normals"):
            mesh.compute_vertex_normals()
        if hasattr(mesh, "compute_triangle_normals"):
            mesh.compute_triangle_normals()

        self.mesh_state = MeshState.from_mesh(mesh, file_path=self.mesh_object.file_path)
        self._update_stats()
        self._configure_offset_range(reset=False)
        self._clear_section_for_plane_change()
        self._refresh_viewport(reset_camera=reset_camera)

    def set_origin_to_geometry(self) -> None:
        if self.mesh_object is None or self.mesh_state.mesh is None:
            self.status_text.set("No selection")
            return

        current_center = np.asarray(
            self.mesh_state.mesh.get_axis_aligned_bounding_box().get_center(),
            dtype=float,
        )
        new_origin = _transform_point(
            np.linalg.inv(self._current_object_matrix()),
            current_center,
        )
        self._change_origin_keep_geometry(new_origin)
        self.status_text.set("Origin set to geometry")

    def move_origin_to_world_origin(self) -> None:
        if self.mesh_object is None:
            self.status_text.set("No selection")
            return

        rotation_scale = _rotation_matrix(self.mesh_object.rotation) * self.mesh_object.scale
        new_origin = self.mesh_object.origin + np.linalg.inv(rotation_scale) @ (
            np.asarray([0.0, 0.0, 0.0], dtype=float) - self.mesh_object.location
        )
        self.mesh_object.origin = new_origin
        self.mesh_object.location = np.asarray([0.0, 0.0, 0.0], dtype=float)
        self._set_transform_inputs_from_object()
        self._apply_object_transform(reset_camera=False)
        self.status_text.set("Origin moved to world origin")

    def center_geometry_on_origin(self) -> None:
        if self.mesh_object is None:
            self.status_text.set("No selection")
            return

        bounds = self.mesh_object.raw_mesh.get_axis_aligned_bounding_box()
        raw_center = np.asarray(bounds.get_center(), dtype=float)
        delta = self.mesh_object.origin - raw_center
        self.mesh_object.raw_mesh.translate(delta.tolist())
        self._apply_object_transform(reset_camera=False)
        self.status_text.set("Geometry centered on origin")

    def reset_object_transform(self) -> None:
        if self.mesh_object is None:
            self.status_text.set("No selection")
            return

        self.mesh_object.location = self.mesh_object.origin.copy()
        self.mesh_object.rotation = np.asarray([0.0, 0.0, 0.0], dtype=float)
        self.mesh_object.scale = 1.0
        self._set_transform_inputs_from_object()
        self._apply_object_transform(reset_camera=True)
        self.status_text.set("Selected: " + self.mesh_object.name)

    def _change_origin_keep_geometry(self, new_origin: np.ndarray) -> None:
        if self.mesh_object is None:
            return

        rotation_scale = _rotation_matrix(self.mesh_object.rotation) * self.mesh_object.scale
        old_origin = self.mesh_object.origin.copy()
        self.mesh_object.origin = np.asarray(new_origin, dtype=float)
        self.mesh_object.location = (
            self.mesh_object.location
            + rotation_scale @ (self.mesh_object.origin - old_origin)
        )
        self._set_transform_inputs_from_object()
        self._apply_object_transform(reset_camera=False)

    def _current_object_matrix(self) -> np.ndarray:
        if self.mesh_object is None:
            return np.identity(4)

        return _build_object_transform_matrix(
            self.mesh_object.location,
            self.mesh_object.rotation,
            self.mesh_object.scale,
            self.mesh_object.origin,
        )

    def _set_transform_inputs_from_object(self) -> None:
        if self.mesh_object is None:
            location = np.asarray([0.0, 0.0, 0.0], dtype=float)
            rotation = np.asarray([0.0, 0.0, 0.0], dtype=float)
            scale = 1.0
        else:
            location = self.mesh_object.location
            rotation = self.mesh_object.rotation
            scale = self.mesh_object.scale

        self.location_x.set(f"{location[0]:.3f}")
        self.location_y.set(f"{location[1]:.3f}")
        self.location_z.set(f"{location[2]:.3f}")
        self.rotation_x.set(f"{rotation[0]:.3f}")
        self.rotation_y.set(f"{rotation[1]:.3f}")
        self.rotation_z.set(f"{rotation[2]:.3f}")
        self.scale_value.set(f"{scale:.3f}")

    def _update_stats(self) -> None:
        self.file_name_text.set(self.mesh_state.file_name or "(none)")
        self.vertex_count_text.set(str(self.mesh_state.vertex_count))
        self.triangle_count_text.set(str(self.mesh_state.triangle_count))
        self.bbox_size_text.set(_format_vector(self.mesh_state.bounding_box_extent))
        self.selected_object_text.set(self.mesh_state.file_name or "(none)")
        self.selected_vertex_count_text.set(str(self.mesh_state.vertex_count))
        self.selected_triangle_count_text.set(str(self.mesh_state.triangle_count))
        self.selected_bbox_size_text.set(_format_vector(self.mesh_state.bounding_box_extent))

    def _handle_shortcut(self, key: str) -> None:
        if key == "F":
            self.frame_selected()
            return

        if key == "Delete":
            self._delete_selected_if_safe()
            return

        if key == "Escape":
            self.active_transform_mode = None
            self.active_transform_axis = None
            self.status_text.set("Transform canceled")
            return

        if key == "Enter":
            self.active_transform_mode = None
            self.active_transform_axis = None
            self.status_text.set("Transform confirmed")
            return

        if key in {"X", "Y", "Z"}:
            self.active_transform_axis = key
            if self.active_transform_mode is None:
                self.status_text.set(f"Axis constraint: {key}")
            else:
                self.status_text.set(f"{self.active_transform_mode.title()} axis: {key}")
            return

        if key == "G":
            if self.selected_item == SELECT_MODEL:
                self.active_transform_mode = "move"
                self.status_text.set("Move mode: selected model")
            elif self.selected_item == SELECT_SECTION_PLANE:
                self.active_transform_mode = "move"
                self.status_text.set("Move mode: section plane offset")
            else:
                self.status_text.set("No selection")
            return

        if key == "R":
            if self.selected_item == SELECT_MODEL:
                self.active_transform_mode = "rotate"
                self.status_text.set("Rotate mode: selected model")
            elif self.selected_item == SELECT_SECTION_PLANE:
                self.status_text.set("Section plane rotation is not implemented")
            else:
                self.status_text.set("No selection")

    def _delete_selected_if_safe(self) -> None:
        if self.selected_item != SELECT_MODEL or self.mesh_object is None:
            self.status_text.set("No selection")
            return

        self.mesh_object = None
        self.mesh_state = MeshState()
        self.section_result = None
        self.curve_results = []
        self.section_result_text.set("Section result: none")
        self._update_stats()
        self._set_selection_buttons_enabled(False)
        self._set_selected_item(None, status="Selected model removed")

    def _set_selection_buttons_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for button in self.selection_buttons:
            button.configure(state=state)

    def _on_exit(self) -> None:
        self.sidebar_canvas.unbind_all("<MouseWheel>")
        self.root.unbind_all("<KeyPress>")
        self.viewport.close()
        self.root.destroy()


def run_app() -> int:
    OpenRetopWindow().run()
    return 0


def _format_vector(values: object) -> str:
    return ", ".join(f"{float(value):.6g}" for value in values)


def _build_object_transform_matrix(
    location: np.ndarray,
    rotation: np.ndarray,
    scale: float,
    origin: np.ndarray,
) -> np.ndarray:
    matrix = np.identity(4)
    matrix[:3, :3] = _rotation_matrix(rotation) * float(scale)
    matrix[:3, 3] = np.asarray(location, dtype=float) - matrix[:3, :3] @ np.asarray(origin, dtype=float)
    return matrix


def _rotation_matrix(rotation: np.ndarray) -> np.ndarray:
    rx, ry, rz = rotation
    return _rotation_z(rz) @ _rotation_y(ry) @ _rotation_x(rx)


def _rotation_x(angle_degrees: float) -> np.ndarray:
    angle = radians(float(angle_degrees))
    c = cos(angle)
    s = sin(angle)
    return np.asarray(
        [
            [1.0, 0.0, 0.0],
            [0.0, c, -s],
            [0.0, s, c],
        ],
        dtype=float,
    )


def _rotation_y(angle_degrees: float) -> np.ndarray:
    angle = radians(float(angle_degrees))
    c = cos(angle)
    s = sin(angle)
    return np.asarray(
        [
            [c, 0.0, s],
            [0.0, 1.0, 0.0],
            [-s, 0.0, c],
        ],
        dtype=float,
    )


def _rotation_z(angle_degrees: float) -> np.ndarray:
    angle = radians(float(angle_degrees))
    c = cos(angle)
    s = sin(angle)
    return np.asarray(
        [
            [c, -s, 0.0],
            [s, c, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=float,
    )


def _transform_point(matrix: np.ndarray, point: np.ndarray) -> np.ndarray:
    homogeneous = np.append(np.asarray(point, dtype=float), 1.0)
    return (np.asarray(matrix, dtype=float) @ homogeneous)[:3]
