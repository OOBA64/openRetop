"""Integrated Tk main window for openRetop."""

from __future__ import annotations

from pathlib import Path
from tkinter import BooleanVar, Menu, StringVar, Tk, filedialog, messagebox
from tkinter import ttk

from geometry.curves import CurveFitResult, fit_section_polylines
from geometry.sections import SECTION_AXES, SectionResult, extract_section
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
    """One-window app with sidebar controls and an embedded Open3D viewport."""

    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("openRetop")
        self.root.geometry("1280x800")
        self.root.minsize(900, 560)

        self.mesh_state = MeshState()
        self.section_result: SectionResult | None = None
        self.curve_results: list[CurveFitResult] = []
        self.show_normals = BooleanVar(value=False)
        self.section_axis = StringVar(value="Z")
        self.section_offset = StringVar(value="0")
        self.status_text = StringVar(value="No model loaded")
        self.file_name_text = StringVar(value="(none)")
        self.vertex_count_text = StringVar(value="0")
        self.triangle_count_text = StringVar(value="0")
        self.bbox_size_text = StringVar(value="-")
        self.section_plane_text = StringVar(value="Section: Z = 0")

        self._build_menu_bar()
        self._build_layout()
        self._set_section_controls_enabled(False)

        self.viewport = EmbeddedOpen3DViewport(self.viewport_frame)
        self.root.after(100, self._start_viewport)
        self.root.protocol("WM_DELETE_WINDOW", self._on_exit)

    def run(self) -> None:
        self.root.mainloop()

    def _start_viewport(self) -> None:
        try:
            self.viewport.start()
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
        self.view_menu.add_command(label="Reset Camera", command=self.reset_camera)
        self.view_menu.add_checkbutton(
            label="Show Normals",
            variable=self.show_normals,
            command=self._on_show_normals_changed,
        )
        self.menu_bar.add_cascade(label="View", menu=self.view_menu)
        self.root.configure(menu=self.menu_bar)

    def _build_layout(self) -> None:
        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(main, padding=12)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.columnconfigure(1, weight=1)

        ttk.Button(sidebar, text="Open Model", command=self.open_model).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 12),
        )

        self._add_info_row(sidebar, 1, "Loaded file", self.file_name_text)
        self._add_info_row(sidebar, 2, "Vertices", self.vertex_count_text)
        self._add_info_row(sidebar, 3, "Triangles", self.triangle_count_text)
        self._add_info_row(sidebar, 4, "Bounding box", self.bbox_size_text)

        ttk.Separator(sidebar).grid(
            row=5,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=12,
        )
        self.section_header_label = ttk.Label(sidebar, text="Section controls")
        self.section_header_label.grid(
            row=6,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 6),
        )

        self.axis_label = ttk.Label(sidebar, text="Axis")
        self.axis_label.grid(row=7, column=0, sticky="w")
        self.axis_dropdown = ttk.Combobox(
            sidebar,
            textvariable=self.section_axis,
            values=SECTION_AXES,
            width=8,
            state="readonly",
        )
        self.axis_dropdown.grid(row=7, column=1, sticky="ew", pady=2)
        self.axis_dropdown.bind("<<ComboboxSelected>>", self._on_section_plane_changed)

        self.offset_label = ttk.Label(sidebar, text="Offset")
        self.offset_label.grid(row=8, column=0, sticky="w")
        self.offset_input = ttk.Entry(
            sidebar,
            textvariable=self.section_offset,
            width=10,
        )
        self.offset_input.grid(row=8, column=1, sticky="ew", pady=2)
        self.offset_input.bind("<KeyRelease>", self._on_section_plane_changed)
        self.offset_input.bind("<FocusOut>", self._on_section_plane_changed)

        self.section_plane_label = ttk.Label(
            sidebar,
            textvariable=self.section_plane_text,
        )
        self.section_plane_label.grid(
            row=9,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(6, 6),
        )

        self.compute_section_button = ttk.Button(
            sidebar,
            text="Compute Section",
            command=self.compute_section,
        )
        self.compute_section_button.grid(
            row=10,
            column=0,
            columnspan=2,
            sticky="ew",
        )
        self.section_controls = (
            self.section_header_label,
            self.axis_label,
            self.axis_dropdown,
            self.offset_label,
            self.offset_input,
            self.section_plane_label,
            self.compute_section_button,
        )

        sidebar.grid_rowconfigure(11, weight=1)

        self.viewport_frame = ttk.Frame(main)
        self.viewport_frame.grid(row=0, column=1, sticky="nsew")

        status_bar = ttk.Label(
            self.root,
            textvariable=self.status_text,
            anchor="w",
            padding=(8, 4),
        )
        status_bar.pack(fill="x", side="bottom")

    def _add_info_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        value: StringVar,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Label(parent, textvariable=value, wraplength=150).grid(
            row=row,
            column=1,
            sticky="w",
            pady=2,
            padx=(8, 0),
        )

    def open_model(self) -> None:
        selected_path = filedialog.askopenfilename(
            title="Open Model",
            filetypes=MESH_FILE_TYPES,
        )
        if not selected_path:
            return

        self.load_model(Path(selected_path))

    def load_model(self, file_path: Path) -> None:
        self.status_text.set(f"Loading model: {file_path.name}")
        self.root.update_idletasks()

        try:
            loaded = load_mesh(file_path)
        except (FileNotFoundError, ValueError, SystemExit) as exc:
            self.status_text.set("No model loaded")
            messagebox.showerror("Could not open model", str(exc))
            return

        self.mesh_state = MeshState.from_loaded_mesh(loaded)
        self.section_result = None
        self.curve_results = []
        self._set_section_controls_enabled(True)
        self._update_stats()
        self._refresh_viewport(reset_camera=True)
        self.status_text.set(f"Loaded model: {self.mesh_state.file_name}")

    def compute_section(self) -> None:
        if not self.mesh_state.is_loaded or self.mesh_state.mesh is None:
            self.status_text.set("No model loaded")
            return

        try:
            offset = float(self.section_offset.get())
        except ValueError as exc:
            messagebox.showerror("Section failed", str(exc))
            return

        self.section_result = extract_section(
            self.mesh_state.mesh,
            axis=self.section_axis.get(),
            offset=offset,
        )
        self.curve_results = fit_section_polylines(self.section_result.polylines)
        self._update_section_plane_label()
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(f"Section computed: {self.section_result.point_count} points")

    def reset_camera(self) -> None:
        self.viewport.reset_camera()

    def _refresh_viewport(self, *, reset_camera: bool) -> None:
        self.viewport.set_scene(
            self.mesh_state.mesh,
            show_normals=self.show_normals.get(),
            section_result=self.section_result,
            curve_results=self.curve_results,
            reset_camera=reset_camera,
        )

    def _on_show_normals_changed(self) -> None:
        if self.mesh_state.is_loaded:
            self._refresh_viewport(reset_camera=False)

    def _on_section_plane_changed(self, _event: object | None = None) -> None:
        self._update_section_plane_label()

    def _update_section_plane_label(self) -> None:
        try:
            offset = float(self.section_offset.get())
        except ValueError:
            offset_text = str(self.section_offset.get())
        else:
            offset_text = f"{offset:.6g}"

        self.section_plane_text.set(f"Section: {self.section_axis.get()} = {offset_text}")

    def _update_stats(self) -> None:
        self.file_name_text.set(self.mesh_state.file_name or "(unnamed)")
        self.vertex_count_text.set(str(self.mesh_state.vertex_count))
        self.triangle_count_text.set(str(self.mesh_state.triangle_count))
        self.bbox_size_text.set(_format_vector(self.mesh_state.bounding_box_extent))

    def _set_section_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        combo_state = "readonly" if enabled else "disabled"
        for widget in (
            self.section_header_label,
            self.axis_label,
            self.offset_label,
            self.section_plane_label,
        ):
            widget.configure(state=state)
        self.axis_dropdown.configure(state=combo_state)
        self.offset_input.configure(state=state)
        self.compute_section_button.configure(state=state)

    def _on_exit(self) -> None:
        self.viewport.close()
        self.root.destroy()


def run_app() -> int:
    OpenRetopWindow().run()
    return 0


def _format_vector(values: object) -> str:
    return ", ".join(f"{float(value):.6g}" for value in values)
