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
from mesh.display_proxy import DisplayMeshResult, build_display_mesh
from mesh.loader import load_mesh
from mesh.mesh_state import MeshState
from mesh.triangle_mesh import TriangleMeshData
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
MOVE_SENSITIVITY = 0.001
ROTATION_SENSITIVITY = 0.5
FINE_TRANSFORM_MULTIPLIER = 0.1


@dataclass
class MeshObjectState:
    """Selection-oriented state for the loaded mesh object."""

    source_mesh: TriangleMeshData
    display_mesh: TriangleMeshData
    file_path: Path | None
    name: str
    origin: np.ndarray
    location: np.ndarray
    rotation: np.ndarray
    scale: float = 1.0
    transform_matrix: np.ndarray | None = None
    source_triangle_count: int = 0
    display_triangle_count: int = 0
    display_proxy_enabled: bool = False
    source_bounds_min: np.ndarray | None = None
    source_bounds_max: np.ndarray | None = None


@dataclass
class ActiveTransformState:
    """Start values for one viewport hotkey transform."""

    selected_item: str
    mode: str
    mouse_start: tuple[int, int]
    axis_constraint: str | None
    location: np.ndarray
    rotation: np.ndarray
    section_axis: str
    section_offset: float


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
        self.transform_state: ActiveTransformState | None = None
        self._last_viewport_mouse = (0, 0)
        self._last_transform_readout: str | None = None
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
        self.display_triangle_count_text = StringVar(value="0")
        self.display_proxy_text = StringVar(value="Display proxy disabled")
        self.source_retained_text = StringVar(value="Full-resolution source retained")
        self.bbox_size_text = StringVar(value="-")
        self.selected_object_text = StringVar(value="(none)")
        self.selected_vertex_count_text = StringVar(value="0")
        self.selected_triangle_count_text = StringVar(value="0")
        self.selected_display_triangle_count_text = StringVar(value="0")
        self.selected_display_proxy_text = StringVar(value="Display proxy disabled")
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
        self.viewport.set_selection_callback(self._on_viewport_selection)
        self.viewport.set_pointer_callback(self._on_viewport_pointer_event)
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
        row = self._add_info_row(parent, row, "Source triangles", self.triangle_count_text)
        row = self._add_info_row(parent, row, "Display triangles", self.display_triangle_count_text)
        row = self._add_info_row(parent, row, "Display proxy", self.display_proxy_text)
        row = self._add_info_row(parent, row, "Source", self.source_retained_text)
        self._add_info_row(parent, row, "Bounding box", self.bbox_size_text)

    def _build_model_context(self, parent: ttk.Frame) -> None:
        row = self._add_separator(parent, 0)
        row = self._add_heading(parent, row, "Selected Object")
        row = self._add_info_row(parent, row, "Object", self.selected_object_text)
        row = self._add_info_row(parent, row, "Vertices", self.selected_vertex_count_text)
        row = self._add_info_row(parent, row, "Source triangles", self.selected_triangle_count_text)
        row = self._add_info_row(
            parent,
            row,
            "Display triangles",
            self.selected_display_triangle_count_text,
        )
        row = self._add_info_row(parent, row, "Display proxy", self.selected_display_proxy_text)
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

        display_result = build_display_mesh(loaded.mesh)
        bounds = display_result.source_mesh.get_axis_aligned_bounding_box()
        origin = np.asarray(bounds.get_center(), dtype=float)
        self.mesh_object = MeshObjectState(
            source_mesh=display_result.source_mesh,
            display_mesh=display_result.display_mesh,
            file_path=loaded.metadata.file_path,
            name=loaded.metadata.file_name,
            origin=origin,
            location=origin.copy(),
            rotation=np.asarray([0.0, 0.0, 0.0], dtype=float),
            scale=1.0,
            transform_matrix=np.identity(4),
            source_triangle_count=display_result.source_triangle_count,
            display_triangle_count=display_result.display_triangle_count,
            display_proxy_enabled=display_result.proxy_enabled,
            source_bounds_min=np.asarray(bounds.get_min_bound(), dtype=float),
            source_bounds_max=np.asarray(bounds.get_max_bound(), dtype=float),
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
        self.status_text.set(self._display_mesh_status(display_result))

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
        if self.transform_state is not None:
            self._end_active_transform(commit=False, status="Transform cancelled")

        self.selected_item = selected_item
        self.active_transform_mode = None
        self.active_transform_axis = None
        self.transform_state = None
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

    def _on_viewport_pointer_event(
        self,
        event_type: str,
        x_position: int,
        y_position: int,
        shift_pressed: bool = False,
        _ctrl_pressed: bool = False,
    ) -> bool:
        self._last_viewport_mouse = (int(x_position), int(y_position))
        if self.transform_state is None:
            return False

        if event_type == "motion":
            self._update_active_transform(
                (int(x_position), int(y_position)),
                fine=shift_pressed,
            )
            return True

        if event_type == "left_release":
            self._end_active_transform(commit=True, status="Transform confirmed")
            return True

        if event_type == "right_release":
            self._end_active_transform(commit=False, status="Transform cancelled")
            return True

        return True

    def compute_section(self) -> None:
        if self.mesh_object is None:
            self.status_text.set("No selection")
            return

        offset = self._parse_offset()
        if offset is None:
            return

        section_mesh = self._transformed_source_mesh()
        self.section_result = extract_section(
            section_mesh,
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
        display_mesh = self.mesh_object.display_mesh if self.mesh_object is not None else None
        transform_matrix = (
            self.mesh_object.transform_matrix
            if self.mesh_object is not None and self.mesh_object.transform_matrix is not None
            else None
        )
        hide_expensive_overlays = self.transform_state is not None
        self.viewport.set_scene(
            display_mesh,
            transform_matrix=transform_matrix,
            show_grid=self.show_grid.get(),
            show_axes=self.show_axes.get(),
            show_normals=self.show_normals.get()
            and not hide_expensive_overlays
            and not (
                self.mesh_object is not None and self.mesh_object.display_proxy_enabled
            ),
            show_section_plane=(
                self.show_section_plane.get() and self.mesh_state.is_loaded
            ),
            section_axis=self.section_axis.get(),
            section_offset=self.section_offset.get(),
            selected_item=self.selected_item,
            object_origin=origin,
            active_transform_mode=self.active_transform_mode,
            active_transform_axis=self.active_transform_axis,
            section_result=None if hide_expensive_overlays else self.section_result,
            curve_results=[] if hide_expensive_overlays else self.curve_results,
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
        if self.mesh_object is None:
            self._section_offset_bounds = (-1.0, 1.0)
            self.offset_slider.configure(from_=-1.0, to=1.0)
            self._set_section_offset(0.0, clamp=True, refresh=False)
            return

        axis_index = AXIS_TO_INDEX[self.section_axis.get()]
        minimum_bound, maximum_bound = self._transformed_source_bounds()
        minimum = float(minimum_bound[axis_index])
        maximum = float(maximum_bound[axis_index])
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

        self.mesh_object.transform_matrix = _build_object_transform_matrix(
            self.mesh_object.location,
            self.mesh_object.rotation,
            self.mesh_object.scale,
            self.mesh_object.origin,
        )
        self.mesh_state = MeshState.from_mesh(
            self.mesh_object.display_mesh,
            file_path=self.mesh_object.file_path,
        )
        self._update_stats()
        self._configure_offset_range(reset=False)
        self._clear_section_for_plane_change()
        self._refresh_viewport(reset_camera=reset_camera)

    def set_origin_to_geometry(self) -> None:
        if self.mesh_object is None:
            self.status_text.set("No selection")
            return

        minimum_bound, maximum_bound = self._transformed_source_bounds()
        current_center = (minimum_bound + maximum_bound) * 0.5
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

        bounds = self.mesh_object.source_mesh.get_axis_aligned_bounding_box()
        raw_center = np.asarray(bounds.get_center(), dtype=float)
        delta = self.mesh_object.origin - raw_center
        self.mesh_object.source_mesh.translate(delta.tolist())
        self.mesh_object.display_mesh.translate(delta.tolist())
        self.mesh_object.source_bounds_min = np.asarray(
            bounds.get_min_bound(),
            dtype=float,
        ) + delta
        self.mesh_object.source_bounds_max = np.asarray(
            bounds.get_max_bound(),
            dtype=float,
        ) + delta
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
        if self.mesh_object is None:
            file_name = "(none)"
            vertex_count = "0"
            source_triangles = "0"
            display_triangles = "0"
            display_proxy = "Display proxy disabled"
            source_retained = "(none)"
            bbox_extent = "-"
        else:
            minimum_bound, maximum_bound = self._transformed_source_bounds()
            file_name = self.mesh_object.name
            vertex_count = str(len(self.mesh_object.source_mesh.vertices))
            source_triangles = str(self.mesh_object.source_triangle_count)
            display_triangles = str(self.mesh_object.display_triangle_count)
            display_proxy = (
                "Display proxy enabled"
                if self.mesh_object.display_proxy_enabled
                else "Display proxy disabled"
            )
            source_retained = "Full-resolution source retained"
            bbox_extent = _format_vector(maximum_bound - minimum_bound)

        self.file_name_text.set(file_name)
        self.vertex_count_text.set(vertex_count)
        self.triangle_count_text.set(source_triangles)
        self.display_triangle_count_text.set(display_triangles)
        self.display_proxy_text.set(display_proxy)
        self.source_retained_text.set(source_retained)
        self.bbox_size_text.set(bbox_extent)
        self.selected_object_text.set(file_name)
        self.selected_vertex_count_text.set(vertex_count)
        self.selected_triangle_count_text.set(source_triangles)
        self.selected_display_triangle_count_text.set(display_triangles)
        self.selected_display_proxy_text.set(display_proxy)
        self.selected_bbox_size_text.set(bbox_extent)

    def _display_mesh_status(self, display_result: DisplayMeshResult) -> str:
        proxy_status = (
            "Display proxy enabled"
            if display_result.proxy_enabled
            else "Display proxy disabled"
        )
        return (
            f"Source triangles: {display_result.source_triangle_count} | "
            f"Display triangles: {display_result.display_triangle_count} | "
            f"{proxy_status} | Full-resolution source retained"
        )

    def _transformed_source_bounds(self) -> tuple[np.ndarray, np.ndarray]:
        if (
            self.mesh_object is None
            or self.mesh_object.source_bounds_min is None
            or self.mesh_object.source_bounds_max is None
        ):
            zero = np.asarray([0.0, 0.0, 0.0], dtype=float)
            return (zero, zero)

        return _transform_bounds(
            self.mesh_object.source_bounds_min,
            self.mesh_object.source_bounds_max,
            self._current_object_matrix(),
        )

    def _transformed_source_mesh(self) -> TriangleMeshData:
        if self.mesh_object is None:
            return TriangleMeshData(
                vertices=np.zeros((0, 3), dtype=float),
                triangles=np.zeros((0, 3), dtype=int),
            )

        mesh = self.mesh_object.source_mesh.copy()
        mesh.transform(self._current_object_matrix())
        return mesh

    def _start_active_transform(self, mode: str) -> None:
        if self.selected_item is None or self.mesh_object is None:
            self.status_text.set("No selection")
            return

        if self.selected_item == SELECT_SECTION_PLANE and mode == "rotate":
            self._cycle_section_axis_for_rotation()
            return

        self.transform_state = ActiveTransformState(
            selected_item=self.selected_item,
            mode=mode,
            mouse_start=self._last_viewport_mouse,
            axis_constraint=None,
            location=self.mesh_object.location.copy(),
            rotation=self.mesh_object.rotation.copy(),
            section_axis=self.section_axis.get(),
            section_offset=self.section_offset.get(),
        )
        self.active_transform_mode = mode
        self.active_transform_axis = self._display_transform_axis(self.transform_state)
        self._last_transform_readout = None
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(self._active_transform_status())

    def _set_transform_axis_constraint(self, axis: str) -> None:
        if self.transform_state is None:
            self.active_transform_axis = axis
            self.status_text.set(f"Axis constraint: {axis}")
            return

        next_axis = None if self.transform_state.axis_constraint == axis else axis
        self.transform_state.axis_constraint = next_axis
        self.active_transform_axis = self._display_transform_axis(self.transform_state)
        self._last_transform_readout = None
        if self.transform_state.selected_item == SELECT_SECTION_PLANE and next_axis is not None:
            self.section_axis.set(axis)
            self._configure_offset_range(reset=False)
            self.transform_state.section_axis = axis
            self.transform_state.section_offset = self.section_offset.get()
            self.transform_state.mouse_start = self._last_viewport_mouse
            self._update_section_plane_label(set_status=False)

        self._refresh_viewport(reset_camera=False)
        self.status_text.set(self._active_transform_status())

    def _update_active_transform(
        self,
        mouse_position: tuple[int, int],
        *,
        fine: bool,
    ) -> None:
        state = self.transform_state
        if state is None:
            return

        if state.selected_item == SELECT_MODEL:
            if state.mode == "move":
                self._update_mesh_move_transform(state, mouse_position, fine=fine)
            elif state.mode == "rotate":
                self._update_mesh_rotate_transform(state, mouse_position, fine=fine)
        elif state.selected_item == SELECT_SECTION_PLANE and state.mode == "move":
            self._update_section_plane_move_transform(state, mouse_position, fine=fine)

    def _update_mesh_move_transform(
        self,
        state: ActiveTransformState,
        mouse_position: tuple[int, int],
        *,
        fine: bool,
    ) -> None:
        if self.mesh_object is None:
            return

        delta = self._mouse_delta(state, mouse_position)
        scale = self._movement_scale(fine=fine)
        drag_amount = (delta[0] - delta[1]) * scale
        axis = state.axis_constraint
        if axis == "X":
            movement = np.asarray([drag_amount, 0.0, 0.0], dtype=float)
            self._last_transform_readout = f"Delta X: {movement[0]:.2f}"
        elif axis == "Y":
            movement = np.asarray([0.0, drag_amount, 0.0], dtype=float)
            self._last_transform_readout = f"Delta Y: {movement[1]:.2f}"
        elif axis == "Z":
            movement = np.asarray([0.0, 0.0, drag_amount], dtype=float)
            self._last_transform_readout = f"Delta Z: {movement[2]:.2f}"
        else:
            movement = np.asarray([delta[0] * scale, -delta[1] * scale, 0.0], dtype=float)
            self._last_transform_readout = (
                f"Delta X: {movement[0]:.2f}, Delta Y: {movement[1]:.2f}"
            )

        self.mesh_object.location = state.location + movement
        self._set_transform_inputs_from_object()
        self._apply_object_transform(reset_camera=False)
        self.status_text.set(self._active_transform_status())

    def _update_mesh_rotate_transform(
        self,
        state: ActiveTransformState,
        mouse_position: tuple[int, int],
        *,
        fine: bool,
    ) -> None:
        if self.mesh_object is None:
            return

        delta = self._mouse_delta(state, mouse_position)
        angle_delta = delta[0] * ROTATION_SENSITIVITY * self._fine_multiplier(fine)
        axis = self._display_transform_axis(state) or "Z"
        rotation = state.rotation.copy()
        rotation[AXIS_TO_INDEX[axis]] += angle_delta
        self.active_transform_axis = axis
        self._last_transform_readout = f"{angle_delta:.1f} deg"
        self.mesh_object.rotation = rotation
        self._set_transform_inputs_from_object()
        self._apply_object_transform(reset_camera=False)
        self.status_text.set(self._active_transform_status())

    def _update_section_plane_move_transform(
        self,
        state: ActiveTransformState,
        mouse_position: tuple[int, int],
        *,
        fine: bool,
    ) -> None:
        delta = self._mouse_delta(state, mouse_position)
        minimum, maximum = self._section_offset_bounds
        offset_scale = (max(abs(maximum - minimum), 1.0) / 300.0) * self._fine_multiplier(fine)
        offset_delta = (delta[0] - delta[1]) * offset_scale
        self._set_section_offset(
            state.section_offset + offset_delta,
            clamp=True,
            refresh=True,
        )
        self._last_transform_readout = (
            f"Offset {self.section_axis.get()}: {self.section_offset.get():.3f}"
        )
        self.status_text.set(self._active_transform_status())

    def _end_active_transform(self, *, commit: bool, status: str) -> None:
        state = self.transform_state
        if state is None:
            return

        if not commit:
            self._restore_transform_start_state(state)

        self.transform_state = None
        self.active_transform_mode = None
        self.active_transform_axis = None
        self._last_transform_readout = None
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(status)

    def _restore_transform_start_state(self, state: ActiveTransformState) -> None:
        if state.selected_item == SELECT_MODEL and self.mesh_object is not None:
            self.mesh_object.location = state.location.copy()
            self.mesh_object.rotation = state.rotation.copy()
            self._set_transform_inputs_from_object()
            self._apply_object_transform(reset_camera=False)
            return

        if state.selected_item == SELECT_SECTION_PLANE:
            self.section_axis.set(state.section_axis)
            self._configure_offset_range(reset=False)
            self._set_section_offset(state.section_offset, clamp=True, refresh=True)

    def _cycle_section_axis_for_rotation(self) -> None:
        current_index = SECTION_AXES.index(self.section_axis.get())
        next_axis = SECTION_AXES[(current_index + 1) % len(SECTION_AXES)]
        self.section_axis.set(next_axis)
        self._configure_offset_range(reset=False)
        self._update_section_plane_label(set_status=False)
        self._clear_section_for_plane_change()
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(f"Section plane axis cycled to {next_axis}")

    def _active_transform_status(self) -> str:
        if self.transform_state is None:
            return "No selection" if self.selected_item is None else "Transform"

        mode_label = "Move mode" if self.transform_state.mode == "move" else "Rotate mode"
        axis = self._display_transform_axis(self.transform_state)
        parts = [mode_label]
        if axis is not None:
            parts.append(f"{axis} axis")
        if self._last_transform_readout is not None:
            parts.append(self._last_transform_readout)
        elif self.transform_state.mode == "move" and axis is None:
            parts.append(
                "press X/Y/Z to constrain, Enter/Click to confirm, Esc/Right-click to cancel"
            )
        elif self.transform_state.mode == "rotate":
            parts.append("move mouse horizontally")
        return " - ".join(parts)

    def _display_transform_axis(self, state: ActiveTransformState) -> str | None:
        if state.mode == "rotate":
            return state.axis_constraint or "Z"
        if state.selected_item == SELECT_SECTION_PLANE:
            return state.axis_constraint or self.section_axis.get()
        return state.axis_constraint

    def _movement_scale(self, *, fine: bool) -> float:
        if self.mesh_object is None:
            model_diagonal = 1.0
        else:
            minimum_bound, maximum_bound = self._transformed_source_bounds()
            model_diagonal = float(np.linalg.norm(maximum_bound - minimum_bound))
        return max(model_diagonal, 1.0) * MOVE_SENSITIVITY * self._fine_multiplier(fine)

    def _fine_multiplier(self, fine: bool) -> float:
        return FINE_TRANSFORM_MULTIPLIER if fine else 1.0

    def _mouse_delta(
        self,
        state: ActiveTransformState,
        mouse_position: tuple[int, int],
    ) -> tuple[float, float]:
        return (
            float(mouse_position[0] - state.mouse_start[0]),
            float(mouse_position[1] - state.mouse_start[1]),
        )

    def _handle_shortcut(self, key: str) -> None:
        if key == "F":
            self.frame_selected()
            return

        if key == "Delete":
            self._delete_selected_if_safe()
            return

        if key == "Escape":
            if self.transform_state is None:
                self.active_transform_mode = None
                self.active_transform_axis = None
                self.status_text.set("Transform cancelled")
            else:
                self._end_active_transform(commit=False, status="Transform cancelled")
            return

        if key == "Enter":
            if self.transform_state is None:
                self.active_transform_mode = None
                self.active_transform_axis = None
                self.status_text.set("Transform confirmed")
            else:
                self._end_active_transform(commit=True, status="Transform confirmed")
            return

        if key in {"X", "Y", "Z"}:
            self._set_transform_axis_constraint(key)
            return

        if key == "G":
            self._start_active_transform("move")
            return

        if key == "R":
            self._start_active_transform("rotate")

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


def _transform_bounds(
    minimum: np.ndarray,
    maximum: np.ndarray,
    matrix: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    minimum = np.asarray(minimum, dtype=float)
    maximum = np.asarray(maximum, dtype=float)
    corners = np.asarray(
        [
            [minimum[0], minimum[1], minimum[2]],
            [maximum[0], minimum[1], minimum[2]],
            [maximum[0], maximum[1], minimum[2]],
            [minimum[0], maximum[1], minimum[2]],
            [minimum[0], minimum[1], maximum[2]],
            [maximum[0], minimum[1], maximum[2]],
            [maximum[0], maximum[1], maximum[2]],
            [minimum[0], maximum[1], maximum[2]],
        ],
        dtype=float,
    )
    homogeneous = np.column_stack((corners, np.ones(len(corners))))
    transformed = (np.asarray(matrix, dtype=float) @ homogeneous.T).T[:, :3]
    return (np.min(transformed, axis=0), np.max(transformed, axis=0))
