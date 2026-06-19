"""Integrated Tk main window for openRetop."""

from __future__ import annotations

import copy
from pathlib import Path
from tkinter import BooleanVar, Canvas, DoubleVar, Menu, StringVar, TclError, Tk, Toplevel, filedialog
from tkinter import messagebox, simpledialog, ttk
from typing import Sequence
from uuid import uuid4

import numpy as np

from app.app_state import AppState
from app.keybinds import KEYBIND_DISPLAY_ORDER, action_for_shortcut, shortcut_from_tk_event
from app.menus import build_menu_bar
from app.object_state import MeshObjectState
from app.preferences_dialog import build_preferences_dialog
from app.scene_browser import (
    CURVE_GROUP_REGION_BOUNDARIES_ID,
    CURVE_GROUP_PROJECTED_ID,
    CURVE_GROUP_REBUILT_ID,
    CURVE_GROUP_REPAIRED_ID,
    CURVE_GROUP_MANUAL_ID,
    NODE_CURVES,
    NODE_CURVE_GROUP_PROJECTED,
    NODE_CURVE_GROUP_REBUILT,
    NODE_CURVE_GROUP_REGION_BOUNDARIES,
    NODE_CURVE_GROUP_UNASSIGNED,
    NODE_CURVE_GROUP_MANUAL,
    NODE_CURVE_GROUP_REPAIRED,
    NODE_MESH,
    NODE_REGIONS,
    NODE_SECTION_PLANES,
    NODE_SECTION_RESULTS,
    NODE_SURFACES,
    SceneBrowser,
    curve_group_id_from_node,
    curve_group_node_id,
    curve_id_from_node,
    curve_node_id,
    region_id_from_node,
    region_node_id,
    section_result_id_from_node,
    section_result_node_id,
    section_plane_id_from_node,
    section_plane_node_id,
    surface_id_from_node,
    surface_node_id,
)
from app.selection_types import (
    SELECT_CURVE,
    SELECT_MODEL,
    SELECT_REGION,
    SELECT_SECTION_PLANE,
    SELECT_SECTION_RESULT,
    SELECT_SURFACE,
)
from app.transform_state import ActiveTransformState
from app.transforms import (
    axis_constrained_camera_move_delta,
    build_object_transform_matrix,
    calculate_geometry_centering_delta,
    calculate_location_for_origin_change,
    calculate_origin_to_world_origin,
    camera_relative_move_delta,
    mesh_rotate_delta,
    normalized_vector,
    rotate_vector_around_axis,
    rotation_matrix,
    transform_bounds,
    transform_point,
    world_axis_vector,
)
from app.undo import CallbackUndoCommand, UndoStack
from curves.curve_state import (
    CurveCollection,
    CurveProcessingError,
    CurveRepairError,
    DEFAULT_CURVE_REPAIR_TOLERANCE,
    DEFAULT_CURVE_SIMPLIFY_TOLERANCE,
    DEFAULT_CURVE_SMOOTH_ITERATIONS,
    StoredCurve,
    add_curve,
    auto_close_curve,
    clear_curve_selection,
    clear_curves_for_plane,
    clear_curves_for_section_result,
    get_selected_curves,
    get_tiny_curves,
    get_visible_curves,
    is_repaired_curve,
    join_curves,
    refresh_curve_diagnostics,
    remove_curve,
    set_active_curve,
    set_selected_curves,
    simplify_curve,
    smooth_curve,
)
from curves.manual_curve import (
    DEFAULT_MANUAL_CURVE_METHOD,
    DEFAULT_MANUAL_CURVE_SAMPLE_COUNT,
    ManualCurveControlData,
    build_manual_stored_curve,
    ensure_manual_curve_storage,
    is_manual_curve_like,
    manual_curve_close_threshold,
    parse_manual_curve_metadata,
    should_snap_closed_to_first_point,
)
from curves.projection import project_stored_curve_to_mesh
from curves.rebuild import rebuild_stored_curve
from curves.validation import (
    CurveSurfaceReadiness,
    validate_curve_for_fill,
    validate_curves_for_loft,
)
from geometry.curves import fit_section_polylines
from geometry.sections import (
    AXIS_TO_INDEX,
    SECTION_AXES,
    SectionPolyline,
    SectionResult,
    extract_section,
    extract_section_by_plane,
    normalize_axis,
)
from mesh.display_proxy import (
    PROXY_QUALITY_LABELS,
    DisplayMeshResult,
    build_display_mesh,
    normalize_proxy_quality,
)
from mesh.loader import load_mesh
from mesh.mesh_state import MeshState
from mesh.triangle_mesh import TriangleMeshData
from project.project_data import ProjectData
from project.project_io import load_project, save_project
from project.project_state import project_from_app_state
from regions.region_state import (
    DEFAULT_REGION_MAX_TRIANGLES,
    DEFAULT_REGION_THRESHOLD_DEGREES,
    RegionSelection,
    create_region_selection,
)
from regions.boundary import RegionBoundaryPolyline, extract_region_boundary_polylines
from settings.settings_data import (
    DEFAULT_REGION_SELECTION_EDGE_COLOR,
    DEFAULT_REGION_SELECTION_COLOR,
    DEFAULT_REGION_SELECTION_OPACITY,
    SETTINGS_VERSION,
    AppDisplaySettings,
    AppImportSettings,
    AppKeybindSettings,
    AppSettings,
    AppUiSettings,
)
from settings.settings_io import load_settings, save_settings
from sections.section_state import (
    SectionCollection,
    SectionPlaneState,
    StoredSectionResult,
    add_plane,
    add_result,
    clear_plane_selection,
    clear_results_for_plane,
    clear_result_selection,
    create_default_section_plane,
    get_active_plane,
    get_active_result,
    plane_normal,
    plane_origin,
    remove_plane,
    set_active_plane,
    set_plane_axis_offset,
    set_plane_origin_normal,
    set_active_result,
    set_selected_planes,
    set_selected_results,
)
from surfaces.surface_state import (
    SurfaceCollection,
    SurfacePatch,
    add_surface,
    clear_surface_selection,
    clear_surfaces_for_curve,
    get_active_surface,
    remove_surface,
    set_active_surface,
    set_selected_surfaces,
)
from surfaces.surface_preview import (
    BOUNDARY_PATCH,
    CURVE_NETWORK_PATCH,
    FOUR_CURVE_PATCH,
    SurfacePreviewMesh,
    TWO_CURVE_LOFT,
    CLOSED_CURVE_FILL,
    build_surface_preview,
    build_surface_preview_mesh,
)
from viewer.embedded_viewport import EmbeddedVTKViewport


MESH_FILE_TYPES = (
    ("Mesh files", "*.stl *.obj *.ply"),
    ("STL files", "*.stl"),
    ("OBJ files", "*.obj"),
    ("PLY files", "*.ply"),
    ("All files", "*.*"),
)
PROJECT_FILE_TYPES = (
    ("openRetop project files", "*.openretop"),
    ("JSON files", "*.json"),
    ("All files", "*.*"),
)
OPEN_MODEL_MENU_INDEX = 4
WORKBENCH_NAMES = (
    "Scene",
    "Transform",
    "Sections",
    "Curves",
    "Surfaces",
    "Manual RE",
    "Analysis",
)
WORKBENCH_PROMPTS = {
    "Scene": "Open a model, adjust viewport visibility, or frame the scene.",
    "Transform": "Select an object, then use Move, Rotate, or numeric transform fields.",
    "Sections": "Create or select a section plane, then compute section curves.",
    "Curves": "Select curves, repair fragments, simplify, smooth, or show tiny curves.",
    "Surfaces": "Select one closed curve to fill or two curves to loft.",
    "Manual RE": "Create manual curves, toggle Snap to Mesh, then finish or cancel.",
    "Analysis": "Inspect mesh, selection, curve, surface, and project diagnostics.",
}
LOAD_PROGRESS_STAGES = (
    "Loading mesh",
    "Computing bounds",
    "Building display proxy",
    "Creating viewport actors",
    "Finalizing scene",
)
COMPUTE_SECTION_PROGRESS_STAGES = (
    "Preparing section",
    "Extracting section geometry",
    "Fitting section curves",
    "Updating viewport",
)
SURFACE_PREVIEW_PROGRESS_STAGES = (
    "Preparing surface preview",
    "Building preview geometry",
    "Updating viewport",
)
SURFACE_PREVIEW_DEFAULT_OPACITY = 0.22
GENERATED_GEOMETRY_TRANSFORM_WARNING = (
    "Generated sections/curves/surfaces will not follow mesh transform. "
    "Recompute after moving."
)


class StageProgressDialog:
    """Small stage-based progress window for synchronous operations."""

    def __init__(self, parent: Tk, *, title: str, summary: str) -> None:
        self.window = Toplevel(parent)
        self.window.title(title)
        self.window.resizable(False, False)
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", lambda: None)
        self.window.columnconfigure(0, weight=1)

        self.stage_text = StringVar(master=self.window, value="Preparing")
        frame = ttk.Frame(self.window, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=summary).grid(row=0, column=0, sticky="w")
        ttk.Label(frame, textvariable=self.stage_text).grid(
            row=1,
            column=0,
            sticky="w",
            pady=(8, 0),
        )
        self.progress_bar = ttk.Progressbar(
            frame,
            mode="indeterminate",
            length=260,
        )
        self.progress_bar.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self.progress_bar.start(12)

        _center_toplevel_over_parent(self.window, parent)
        self.render_now()
        self.window.lift()

    def update_stage(self, stage: str) -> None:
        self.stage_text.set(stage)
        self.progress_bar.step(8.0)
        self.render_now()
        self.window.lift()

    def render_now(self) -> None:
        try:
            self.window.update_idletasks()
            self.window.update()
        except TclError:
            return

    def close(self) -> None:
        self.progress_bar.stop()
        self.window.destroy()


class LoadProgressDialog(StageProgressDialog):
    def __init__(self, parent: Tk, file_name: str) -> None:
        self.file_name = file_name
        super().__init__(
            parent,
            title="Opening Model",
            summary=f"Opening {file_name}",
        )


class ComputationProgressDialog(StageProgressDialog):
    def __init__(self, parent: Tk, title: str, summary: str | None = None) -> None:
        self.title_text = title
        super().__init__(
            parent,
            title=title,
            summary=summary or title,
        )


def _center_toplevel_over_parent(window: Toplevel, parent: Tk) -> None:
    try:
        window.update_idletasks()
        parent.update_idletasks()
        width = max(int(window.winfo_width()), int(window.winfo_reqwidth()))
        height = max(int(window.winfo_height()), int(window.winfo_reqheight()))
        parent_width = int(parent.winfo_width())
        parent_height = int(parent.winfo_height())
        parent_x = int(parent.winfo_rootx())
        parent_y = int(parent.winfo_rooty())
        if parent_width <= 1 or parent_height <= 1:
            parent_width = int(parent.winfo_screenwidth())
            parent_height = int(parent.winfo_screenheight())
            parent_x = 0
            parent_y = 0
        x = max(parent_x + (parent_width - width) // 2, 0)
        y = max(parent_y + (parent_height - height) // 2, 0)
        window.geometry(f"+{x}+{y}")
    except TclError:
        return


class OpenRetopWindow:
    """One-window app with context-sensitive selection controls."""

    def __init__(self, *, settings_path: Path | None = None) -> None:
        self.root = Tk()
        self.settings_path = settings_path
        self.settings = load_settings(settings_path)
        self.root.title("openRetop")
        self.root.geometry(
            f"{self.settings.ui.window_width}x{self.settings.ui.window_height}"
        )
        self.root.minsize(980, 620)
        self._maximize_startup_window()

        self.mesh_state = MeshState()
        self.app_state = AppState()
        self.undo_stack = UndoStack()
        self._last_viewport_mouse = (0, 0)
        self._last_transform_readout: str | None = None
        self._active_transform_angle_delta: float | None = None
        self._manual_curve_active = False
        self._manual_curve_points: list[np.ndarray] = []
        self._manual_curve_closed = False
        self._manual_curve_plane_origin = np.asarray([0.0, 0.0, 0.0], dtype=float)
        self._manual_curve_plane_normal = np.asarray([0.0, 0.0, 1.0], dtype=float)
        self._manual_curve_plane_type = "world_xy"
        self._manual_curve_plane_label = "world XY plane"
        self._manual_curve_source_section_plane_id: str | None = None
        self._manual_curve_snap_point_count = 0
        self._manual_curve_snap_flags: list[bool] = []
        self._manual_curve_snap_triangle_indices: list[int | None] = []
        self._manual_curve_snap_normals: list[list[float] | None] = []
        self._manual_curve_edit_active = False
        self._manual_curve_edit_curve_id: str | None = None
        self._manual_curve_selected_control_point_index: int | None = None
        self._manual_curve_hover_control_point_index: int | None = None
        self._manual_curve_drag_active = False
        self._manual_curve_placing_enabled = True
        self._manual_curve_add_point_active = False
        self._manual_curve_insert_point_active = False
        self._manual_curve_curve_method = DEFAULT_MANUAL_CURVE_METHOD
        self._manual_curve_sample_count = DEFAULT_MANUAL_CURVE_SAMPLE_COUNT
        self._manual_curve_left_press_position: tuple[int, int] | None = None
        self._manual_curve_left_dragged = False
        self._manual_curve_context_menu: Menu | None = None
        self._manual_curve_last_context_actions: tuple[str, ...] = ()
        self._manual_curve_preview_point: np.ndarray | None = None
        self._manual_curve_preview_valid = False
        self._manual_curve_preview_snaps_closed = False
        self._manual_curve_preview_snaps_to_mesh = False
        self._manual_curve_preview_triangle_index: int | None = None
        self._manual_curve_preview_normal: list[float] | None = None
        self._region_select_active = False
        self._region_select_left_press_position: tuple[int, int] | None = None
        self._region_select_left_dragged = False
        self._region_select_current_seed_triangle_index: int | None = None
        self._region_select_last_hit_triangle_index: int | None = None
        self._region_select_context_menu: Menu | None = None
        self._is_loading_model = False
        self._start_viewport_after_id: str | None = None
        self.current_project_path: Path | None = None
        self.project_dirty = False
        self.preferences_dialog: Toplevel | None = None
        self.preferences_notebook: ttk.Notebook | None = None
        self.preferences_vars: dict[str, BooleanVar | StringVar] = {}
        self._update_window_title()

        self.show_grid = BooleanVar(value=self.settings.display.show_grid)
        self.show_axes = BooleanVar(value=self.settings.display.show_axes)
        self.show_axis_gizmo = BooleanVar(value=self.settings.display.show_axis_gizmo)
        self.show_viewcube = BooleanVar(value=self.settings.display.show_viewcube)
        self.show_view_controls = self.show_viewcube
        self.show_normals = BooleanVar(value=False)
        self.show_section_plane = BooleanVar(value=False)
        self.manual_curve_snap_to_mesh = BooleanVar(value=False)
        self.region_threshold_degrees = DoubleVar(value=DEFAULT_REGION_THRESHOLD_DEGREES)
        self.region_threshold_text = StringVar(value=f"{DEFAULT_REGION_THRESHOLD_DEGREES:.1f}")
        self.region_max_triangle_count = StringVar(value=str(DEFAULT_REGION_MAX_TRIANGLES))
        self._last_valid_region_threshold = DEFAULT_REGION_THRESHOLD_DEGREES
        self._last_valid_region_max_triangle_count = DEFAULT_REGION_MAX_TRIANGLES
        self.proxy_quality = StringVar(
            value=normalize_proxy_quality(
                self.settings.import_settings.default_proxy_quality
            )
        )

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

        self.status_text = StringVar(value="Open Model to begin")
        self.current_mode_text = StringVar(value="No Mode")
        self.current_workbench = StringVar(value="Scene")
        self.command_prompt_text = StringVar(value=WORKBENCH_PROMPTS["Scene"])
        self.hotkey_hint_text = StringVar(value="Hotkeys: G move, R rotate, F frame, Esc cancel")
        self.empty_scene_prompt_text = StringVar(value="Load a mesh to begin reverse engineering.")
        self.manual_curve_mode_title = StringVar(value="Manual Curve")
        self.manual_curve_mode_details = StringVar(value="Inactive")
        self.manual_curve_snap_help_text = StringVar(
            value="Load a mesh to enable Snap to Mesh."
        )
        self.manual_curve_type_text = StringVar(value="Smooth Curve")
        self.region_name_text = StringVar(value="(none)")
        self.region_triangle_count_text = StringVar(value="0")
        self.region_threshold_display_text = StringVar(value="20.0 deg")
        self.region_max_triangle_cap_text = StringVar(value=f"{DEFAULT_REGION_MAX_TRIANGLES:,}")
        self.region_seed_triangle_text = StringVar(value="-")
        self.region_source_mesh_text = StringVar(value="(none)")
        self.region_visible_text = StringVar(value="No")
        self.region_status_text = StringVar(value="No active region")
        self.region_boundary_curve_count_text = StringVar(value="0")
        self.project_path_text = StringVar(value="Project: Untitled Project")
        self.selected_object_type_text = StringVar(value="(none)")
        self.file_name_text = StringVar(value="(none)")
        self.vertex_count_text = StringVar(value="0")
        self.triangle_count_text = StringVar(value="0")
        self.display_triangle_count_text = StringVar(value="0")
        self.display_reduction_text = StringVar(value="0.0%")
        self.display_proxy_text = StringVar(
            value=f"Disabled ({self.proxy_quality.get()})"
        )
        self.source_retained_text = StringVar(value="Full-resolution source preserved")
        self.bbox_size_text = StringVar(value="-")
        self.selected_object_text = StringVar(value="(none)")
        self.selected_vertex_count_text = StringVar(value="0")
        self.selected_triangle_count_text = StringVar(value="0")
        self.selected_display_triangle_count_text = StringVar(value="0")
        self.selected_display_reduction_text = StringVar(value="0.0%")
        self.selected_display_proxy_text = StringVar(
            value=f"Disabled ({self.proxy_quality.get()})"
        )
        self.selected_bbox_size_text = StringVar(value="-")
        self.mesh_visible = BooleanVar(value=True)
        self.mesh_name_text = StringVar(value="(none)")
        self.section_plane_text = StringVar(value="Section: Z = 0.000")
        self.section_plane_name_text = StringVar(value="Section Plane 1")
        self.section_result_text = StringVar(value="Section result: none")
        self.section_result_visible = BooleanVar(value=True)
        self.section_result_name_text = StringVar(value="(none)")
        self.section_result_source_plane_text = StringVar(value="(none)")
        self.section_result_axis_text = StringVar(value="(none)")
        self.section_result_offset_text = StringVar(value="0.000")
        self.section_result_segment_count_text = StringVar(value="0")
        self.section_result_curve_count_text = StringVar(value="0")
        self.curve_visible = BooleanVar(value=True)
        self.curve_name_text = StringVar(value="(none)")
        self.curve_section_text = StringVar(value="(none)")
        self.curve_plane_text = StringVar(value="(none)")
        self.curve_point_count_text = StringVar(value="0")
        self.curve_length_text = StringVar(value="0.000")
        self.curve_endpoint_gap_text = StringVar(value="0.000")
        self.curve_mean_error_text = StringVar(value="0.000")
        self.curve_max_error_text = StringVar(value="0.000")
        self.curve_closed_text = StringVar(value="Open")
        self.curve_tiny_text = StringVar(value="No")
        self.curve_type_text = StringVar(value="(none)")
        self.curve_source_text = StringVar(value="(none)")
        self.curve_control_point_count_text = StringVar(value="0")
        self.curve_planarity_error_text = StringVar(value="(none)")
        self.curve_projection_mean_distance_text = StringVar(value="(none)")
        self.curve_projection_max_distance_text = StringVar(value="(none)")
        self.curve_surface_readiness_text = StringVar(value="Select curve(s) to validate.")
        self.curve_surface_warnings_text = StringVar(value="(none)")
        self.curve_surface_errors_text = StringVar(value="(none)")
        self.rebuild_target_control_points = StringVar(value="16")
        self.rebuild_curve_type_text = StringVar(value="Smooth Curve")
        self.rebuild_sample_count = StringVar(value="128")
        self.surface_visible = BooleanVar(value=True)
        self.surface_name_text = StringVar(value="(none)")
        self.surface_type_text = StringVar(value="(none)")
        self.surface_preview_mode_text = StringVar(value="(none)")
        self.surface_source_curve_count_text = StringVar(value="0")
        self.surface_source_curve_names_text = StringVar(value="(none)")
        self.surface_preview_available_text = StringVar(value="(none)")
        self.surface_preview_reason_text = StringVar(value="(none)")
        self.surface_preview_warning_text = StringVar(value="(none)")
        self.surface_grid_size_text = StringVar(value="(none)")
        self.surface_planarity_error_text = StringVar(value="(none)")
        self.surface_resampled_point_count_text = StringVar(value="(none)")
        self.surface_reversed_second_curve_text = StringVar(value="(none)")
        self.surface_seam_shift_applied_text = StringVar(value="(none)")
        self.surface_average_pair_distance_text = StringVar(value="(none)")
        self.surface_max_pair_distance_text = StringVar(value="(none)")
        self.surface_validation_warnings_text = StringVar(value="(none)")
        self.surface_validation_errors_text = StringVar(value="(none)")
        self.surface_opacity = DoubleVar(value=0.22)
        self.surface_opacity_text = StringVar(value="0.22")
        self.surface_wireframe_overlay = BooleanVar(value=True)
        self.surface_metadata_text = StringVar(value="(none)")
        self.selection_buttons: list[ttk.Button] = []
        self._syncing_surface_display_controls = False
        self._sync_active_section_plane_from_controls()

        self._build_menu_bar()
        self._update_undo_redo_menu()
        self._build_layout()
        self._set_selection_buttons_enabled(False)
        self._show_context(None)
        self._sync_workflow_ui()
        self._refresh_scene_browser()
        self._bind_keyboard_shortcuts()

        self.viewport = EmbeddedVTKViewport(self.viewport_frame)
        self.viewport.set_selection_callback(self._on_viewport_selection)
        self.viewport.set_pointer_callback(self._on_viewport_pointer_event)
        self._sync_viewcube_shell_visibility()
        self._start_viewport_after_id = self.root.after(100, self._start_viewport)
        self.root.protocol("WM_DELETE_WINDOW", self._on_exit)

    def run(self) -> None:
        self.root.mainloop()

    def _maximize_startup_window(self) -> None:
        if self.settings.ui.window_mode != "maximized":
            return
        try:
            self.root.state("zoomed")
        except TclError:
            return

    def _start_viewport(self) -> None:
        self._start_viewport_after_id = None
        try:
            self.viewport.start()
            self._sync_viewcube_shell_visibility()
            self._refresh_viewport(reset_camera=True)
        except RuntimeError as exc:
            self.status_text.set("Viewport failed to start")
            messagebox.showerror("Viewport failed to start", str(exc))

    def _build_menu_bar(self) -> None:
        self.menu_bar = build_menu_bar(self)

    def _not_implemented(self, feature_name: str) -> None:
        self.status_text.set(f"{feature_name}: Not implemented yet")

    def new_project(self) -> None:
        if not self._confirm_unsaved_project_changes("starting a new project"):
            return

        self._clear_scene_data(reset_camera=False)
        self.current_project_path = None
        self._clear_undo_stack()
        self._set_project_dirty(False)
        self.status_text.set("Project ready: Untitled Project")

    def open_project(self) -> None:
        selected_path = filedialog.askopenfilename(
            title="Open Project",
            filetypes=PROJECT_FILE_TYPES,
        )
        if not selected_path:
            return

        project_path = Path(selected_path)
        try:
            project = load_project(project_path)
        except (OSError, ValueError, RuntimeError) as exc:
            self.status_text.set("Project open failed")
            messagebox.showerror("Could not open project", str(exc))
            return

        self.current_project_path = project_path
        self._update_window_title()
        if project.mesh_path is None:
            self._restore_project_controls(project)
            self._clear_undo_stack()
            self._set_project_dirty(False)
            self.status_text.set(f"Project loaded: {project.name} ({project_path})")
            return

        mesh_path = self._project_mesh_path(project_path, project.mesh_path)
        self.proxy_quality.set(normalize_proxy_quality(project.display.proxy_quality))
        if not self.load_model(mesh_path, error_title="Could not open project"):
            self.status_text.set("Project open failed")
            return

        self._restore_project_transform(project)
        self._restore_project_controls(project)
        self._refresh_viewport(reset_camera=False)
        self._clear_undo_stack()
        self._set_project_dirty(False)
        self.status_text.set(f"Project loaded: {project.name} ({project_path})")

    def _project_display_name(self) -> str:
        if self.current_project_path is None:
            return "Untitled Project"
        return self.current_project_path.name

    def _update_window_title(self) -> None:
        marker = " *" if self.project_dirty else ""
        self.root.title(f"openRetop - {self._project_display_name()}{marker}")
        if hasattr(self, "project_path_text"):
            self.project_path_text.set(
                f"Project: {self.current_project_path}"
                if self.current_project_path is not None
                else "Project: Untitled Project"
            )

    def _set_project_dirty(self, dirty: bool = True) -> None:
        self.project_dirty = bool(dirty)
        self._update_window_title()

    def _clear_scene_data(self, *, reset_camera: bool) -> None:
        self.mesh_state = MeshState()
        self.app_state = AppState(
            section_collection=SectionCollection(),
            curve_collection=CurveCollection(),
            surface_collection=SurfaceCollection(),
        )
        self._last_transform_readout = None
        self._active_transform_angle_delta = None
        self._clear_manual_curve_state(reset_snap=True)
        self._clear_region_selection_state()

        self.show_section_plane.set(False)
        self.section_axis.set("Z")
        self._updating_offset = True
        try:
            self.section_offset.set(0.0)
            self.section_offset_text.set("0.000")
        finally:
            self._updating_offset = False
        self._section_offset_bounds = (-1.0, 1.0)
        self.offset_slider.configure(from_=-1.0, to=1.0)
        self.section_plane_name_text.set("Section Plane 1")
        self._update_section_plane_label(set_status=False)

        self._set_transform_inputs_from_object()
        self._set_display_section_result(None)
        self._sync_section_result_context_from_active_result()
        self._sync_curve_context_from_active_curve()
        self._sync_surface_context_from_active_surface()
        self._update_stats()
        self._set_selection_buttons_enabled(False)
        self._show_context(None)
        self._clear_undo_stack()
        self._refresh_viewport(reset_camera=reset_camera)
        self._refresh_scene_browser()

    def delete_mesh(self) -> None:
        if self.app_state.mesh_object is None:
            self.status_text.set("No selection")
            return

        if not messagebox.askyesno("Delete Mesh", self._delete_mesh_confirmation_text()):
            self.status_text.set("Mesh deletion cancelled")
            return

        self._clear_scene_data(reset_camera=False)
        if deleted_count != 1 or not delete_targets["regions"]:
            self._set_project_dirty(True)
        self.status_text.set("Mesh deleted")

    def _delete_mesh_confirmation_text(self) -> str:
        section_plane_count = len(self.app_state.section_collection.planes)
        section_result_count = len(self.app_state.section_collection.results)
        curve_count = len(self.app_state.curve_collection.curves)
        surface_count = len(self.app_state.surface_collection.surfaces)
        return (
            "Delete mesh and all generated data?\n"
            "This will remove:\n"
            f"- {section_plane_count} {_plural_label(section_plane_count, 'section plane')}\n"
            f"- {section_result_count} {_plural_label(section_result_count, 'section result')}\n"
            f"- {curve_count} {_plural_label(curve_count, 'curve')}\n"
            f"- {surface_count} {_plural_label(surface_count, 'surface')}"
        )

    def _confirm_unsaved_project_changes(self, action: str) -> bool:
        if not self.project_dirty:
            return True

        response = messagebox.askyesnocancel(
            "Unsaved Project",
            f"Save changes to {self._project_display_name()} before {action}?",
        )
        if response is None:
            return False
        if response:
            return self.save_project()
        return True

    def _project_mesh_path(self, project_path: Path, mesh_path: str) -> Path:
        restored_mesh_path = Path(mesh_path).expanduser()
        if not restored_mesh_path.is_absolute():
            restored_mesh_path = project_path.parent / restored_mesh_path
        return restored_mesh_path

    def _restore_project_controls(self, project: ProjectData) -> None:
        self.proxy_quality.set(normalize_proxy_quality(project.display.proxy_quality))
        self.show_grid.set(project.display.show_grid)
        self.show_axes.set(project.display.show_axes)
        self.show_normals.set(False)
        self._restore_project_mesh_display(project)
        self._restore_project_section_collection(project)
        self._restore_project_curve_collection(project)
        self._restore_project_surface_collection(project)
        self._refresh_scene_browser()

    def _restore_project_mesh_display(self, project: ProjectData) -> None:
        if self.app_state.mesh_object is None:
            return

        if project.mesh_name is not None and project.mesh_name.strip():
            self.app_state.mesh_object.name = project.mesh_name.strip()
        self.app_state.mesh_object.visible = bool(project.mesh_visible)
        self._update_stats()

    def _restore_project_transform(self, project: ProjectData) -> None:
        if self.app_state.mesh_object is None:
            return

        self.app_state.mesh_object.location = np.asarray(project.transform.location, dtype=float)
        self.app_state.mesh_object.rotation = np.asarray(project.transform.rotation, dtype=float)
        self.app_state.mesh_object.scale = float(project.transform.scale)
        self.app_state.mesh_object.origin = np.asarray(project.transform.origin, dtype=float)
        self._set_transform_inputs_from_object()
        self._apply_object_transform(reset_camera=False)

    def _restore_project_section_collection(self, project: ProjectData) -> None:
        collection = SectionCollection()
        restored_names: set[str] = set()
        if project.section_planes:
            for index, project_plane in enumerate(project.section_planes, start=1):
                add_plane(
                    collection,
                    SectionPlaneState(
                        id=project_plane.id,
                        name=self._unique_restored_section_plane_name(
                            project_plane.name,
                            index,
                            restored_names,
                        ),
                        axis=project_plane.axis,
                        offset=project_plane.offset,
                        visible=project_plane.visible,
                        origin=np.asarray(project_plane.origin, dtype=float)
                        if project_plane.origin is not None
                        else None,
                        normal=np.asarray(project_plane.normal, dtype=float)
                        if project_plane.normal is not None
                        else None,
                    ),
                )

            self._set_restored_active_section_plane(
                collection,
                project.active_section_plane_id,
            )
        else:
            plane = create_default_section_plane(
                axis=project.section.axis,
                offset=project.section.offset,
            )
            plane.name = self._unique_restored_section_plane_name(
                plane.name,
                1,
                restored_names,
            )
            plane.visible = bool(project.section.show_plane)
            add_plane(collection, plane)

        if not collection.planes:
            add_plane(collection, create_default_section_plane())

        self._restore_project_section_results(collection, project)
        self.app_state.section_collection = collection
        self._set_display_section_result(collection.results[-1] if collection.results else None)
        self._sync_section_controls_from_active_plane(clamp_offset=False)

    def _restore_project_section_results(
        self,
        collection: SectionCollection,
        project: ProjectData,
    ) -> None:
        plane_ids = {plane.id for plane in collection.planes}
        for project_result in project.section_results:
            if project_result.plane_id not in plane_ids:
                continue

            polylines = tuple(
                SectionPolyline(points=np.asarray(points, dtype=float))
                for points in project_result.polylines
            )
            result = SectionResult(
                axis=normalize_axis(project_result.axis),
                offset=float(project_result.offset),
                polylines=polylines,
                segment_count=int(project_result.segment_count),
                plane_origin=np.asarray(project_result.plane_origin, dtype=float),
                plane_normal=np.asarray(project_result.plane_normal, dtype=float),
                is_arbitrary_plane=bool(project_result.is_arbitrary_plane),
            )
            try:
                add_result(
                    collection,
                    StoredSectionResult(
                        id=project_result.id,
                        name=project_result.name.strip()
                        or f"Section {len(collection.results) + 1}",
                        plane_id=project_result.plane_id,
                        axis=project_result.axis,
                        offset=project_result.offset,
                        result=result,
                        visible=project_result.visible,
                        plane_origin=np.asarray(project_result.plane_origin, dtype=float),
                        plane_normal=np.asarray(project_result.plane_normal, dtype=float),
                        is_arbitrary_plane=bool(project_result.is_arbitrary_plane),
                    ),
                )
            except ValueError:
                continue

    def _restore_project_curve_collection(self, project: ProjectData) -> None:
        curves = [
            StoredCurve(
                id=project_curve.id,
                name=project_curve.name,
                section_result_id=project_curve.section_result_id,
                plane_id=project_curve.plane_id,
                original_points=np.asarray(project_curve.original_points, dtype=float),
                fitted_points=np.asarray(project_curve.fitted_points, dtype=float),
                mean_error=project_curve.mean_error,
                max_error=project_curve.max_error,
                is_closed=project_curve.is_closed,
                visible=project_curve.visible,
                selected=False,
                metadata=dict(project_curve.metadata),
            )
            for project_curve in project.curves
        ]
        for curve in curves:
            ensure_manual_curve_storage(curve)
            refresh_curve_diagnostics(curve)
        self.app_state.curve_collection = CurveCollection(
            curves=curves,
            active_curve_id=None,
        )
        self._sync_visible_curve_results()
        self._sync_curve_context_from_active_curve()

    def _restore_project_surface_collection(self, project: ProjectData) -> None:
        curve_ids = {curve.id for curve in self.app_state.curve_collection.curves}
        surfaces: list[SurfacePatch] = []
        for project_surface in project.surfaces:
            metadata = dict(project_surface.metadata)
            missing_curve_ids = [
                curve_id
                for curve_id in project_surface.source_curve_ids
                if curve_id not in curve_ids
            ]
            if missing_curve_ids:
                metadata["missing_curve_ids"] = missing_curve_ids
            surfaces.append(
                SurfacePatch(
                    id=project_surface.id,
                    name=project_surface.name,
                    source_curve_ids=list(project_surface.source_curve_ids),
                    surface_type=project_surface.surface_type,
                    visible=project_surface.visible,
                    selected=False,
                    metadata=metadata,
                )
            )

        self.app_state.surface_collection = SurfaceCollection(
            surfaces=surfaces,
            active_surface_id=None,
        )
        self._sync_surface_context_from_active_surface()

    def _set_restored_active_section_plane(
        self,
        collection: SectionCollection,
        active_plane_id: str | None,
    ) -> None:
        if not collection.planes:
            return

        if active_plane_id is not None:
            try:
                set_active_plane(collection, active_plane_id)
                return
            except ValueError:
                pass

        set_active_plane(collection, collection.planes[0].id)

    @staticmethod
    def _unique_restored_section_plane_name(
        name: str,
        index: int,
        existing_names: set[str],
    ) -> str:
        candidate = name.strip() or f"Section Plane {index}"
        if candidate not in existing_names:
            existing_names.add(candidate)
            return candidate

        if candidate.startswith("Section Plane "):
            suffix = 1
            while f"Section Plane {suffix}" in existing_names:
                suffix += 1
            candidate = f"Section Plane {suffix}"
        else:
            base_name = candidate
            suffix = 2
            while f"{base_name} {suffix}" in existing_names:
                suffix += 1
            candidate = f"{base_name} {suffix}"

        existing_names.add(candidate)
        return candidate

    def save_project(self) -> bool:
        if self.current_project_path is None:
            return self.save_project_as()

        return self._write_project(self.current_project_path)

    def save_project_as(self) -> bool:
        selected_path = filedialog.asksaveasfilename(
            title="Save Project",
            defaultextension=".openretop",
            filetypes=PROJECT_FILE_TYPES,
        )
        if not selected_path:
            return False

        project_path = Path(selected_path)
        return self._write_project(project_path)

    def _write_project(self, project_path: Path) -> bool:
        try:
            self._sync_active_section_plane_from_controls()
            project = project_from_app_state(
                mesh_object=self.app_state.mesh_object,
                proxy_quality=self.proxy_quality.get(),
                show_grid=self.show_grid.get(),
                show_axes=self.show_axes.get(),
                show_normals=False,
                section_axis=self.section_axis.get(),
                section_offset=self.section_offset.get(),
                show_section_plane=self.show_section_plane.get(),
                section_collection=self.app_state.section_collection,
                curve_collection=self.app_state.curve_collection,
                surface_collection=self.app_state.surface_collection,
            )
            save_project(project, project_path)
        except (OSError, ValueError, RuntimeError) as exc:
            self.status_text.set("Project save failed")
            messagebox.showerror("Could not save project", str(exc))
            return False

        self.current_project_path = project_path
        self._set_project_dirty(False)
        self.status_text.set(f"Project saved: {project_path}")
        return True

    def undo(self) -> None:
        command = self.undo_stack.undo()
        self._update_undo_redo_menu()
        if command is None:
            self.status_text.set("Nothing to undo")
            return

        self._sync_after_undoable_scene_change()
        self.status_text.set(f"Undid {command.name}")
        self._set_project_dirty(True)

    def redo(self) -> None:
        command = self.undo_stack.redo()
        self._update_undo_redo_menu()
        if command is None:
            self.status_text.set("Nothing to redo")
            return

        self._sync_after_undoable_scene_change()
        self.status_text.set(f"Redid {command.name}")
        self._set_project_dirty(True)

    def _push_undo_command(self, command: CallbackUndoCommand) -> None:
        self.undo_stack.push(command)
        self._update_undo_redo_menu()

    def _clear_undo_stack(self) -> None:
        self.undo_stack.clear()
        self._update_undo_redo_menu()

    def _update_undo_redo_menu(self) -> None:
        edit_menu = getattr(self, "edit_menu", None)
        if edit_menu is None:
            return

        try:
            edit_menu.entryconfigure(
                0,
                state="normal" if self.undo_stack.can_undo else "disabled",
            )
            edit_menu.entryconfigure(
                1,
                state="normal" if self.undo_stack.can_redo else "disabled",
            )
        except TclError:
            return

    def _push_rename_command(
        self,
        node_id: str,
        command_name: str,
        old_name: str,
        new_name: str,
    ) -> None:
        if old_name == new_name:
            return

        self._push_undo_command(
            CallbackUndoCommand(
                command_name,
                undo_action=lambda: self._set_object_name_by_node_id(node_id, old_name),
                redo_action=lambda: self._set_object_name_by_node_id(node_id, new_name),
            )
        )

    def _set_object_name_by_node_id(self, node_id: str, name: str) -> None:
        mesh_object = self.app_state.mesh_object
        if node_id == NODE_MESH:
            if mesh_object is not None:
                mesh_object.name = name
            return

        plane_id = section_plane_id_from_node(node_id)
        if plane_id is not None:
            for plane in self.app_state.section_collection.planes:
                if plane.id == plane_id:
                    plane.name = name
                    return

        result_id = section_result_id_from_node(node_id)
        if result_id is not None:
            for result in self.app_state.section_collection.results:
                if result.id == result_id:
                    result.name = name
                    return

        curve_id = curve_id_from_node(node_id)
        if curve_id is not None:
            for curve in self.app_state.curve_collection.curves:
                if curve.id == curve_id:
                    curve.name = name
                    return

        surface_id = surface_id_from_node(node_id)
        if surface_id is not None:
            for surface in self.app_state.surface_collection.surfaces:
                if surface.id == surface_id:
                    surface.name = name
                    return

        region_id = region_id_from_node(node_id)
        active_region = self.app_state.region_collection.active_region
        if (
            region_id is not None
            and active_region is not None
            and active_region.id == region_id
        ):
            active_region.name = name
            return

    def _push_visibility_command(
        self,
        command_name: str,
        before: dict[str, bool],
        after: dict[str, bool],
    ) -> None:
        changed_node_ids = {
            node_id
            for node_id, before_visible in before.items()
            if node_id in after and before_visible != after[node_id]
        }
        if not changed_node_ids:
            return

        before_changed = {
            node_id: before[node_id]
            for node_id in changed_node_ids
        }
        after_changed = {
            node_id: after[node_id]
            for node_id in changed_node_ids
        }
        self._push_undo_command(
            CallbackUndoCommand(
                command_name,
                undo_action=lambda: self._apply_visibility_snapshot(before_changed),
                redo_action=lambda: self._apply_visibility_snapshot(after_changed),
            )
        )

    def _visibility_snapshot(self, node_ids: set[str]) -> dict[str, bool]:
        snapshot: dict[str, bool] = {}
        if self.app_state.mesh_object is not None and NODE_MESH in node_ids:
            snapshot[NODE_MESH] = bool(self.app_state.mesh_object.visible)
        for plane in self.app_state.section_collection.planes:
            node_id = section_plane_node_id(plane.id)
            if node_id in node_ids:
                snapshot[node_id] = bool(plane.visible)
        for result in self.app_state.section_collection.results:
            node_id = section_result_node_id(result.id)
            if node_id in node_ids:
                snapshot[node_id] = bool(result.visible)
        for curve in self.app_state.curve_collection.curves:
            node_id = curve_node_id(curve.id)
            if node_id in node_ids:
                snapshot[node_id] = bool(curve.visible)
        for surface in self.app_state.surface_collection.surfaces:
            node_id = surface_node_id(surface.id)
            if node_id in node_ids:
                snapshot[node_id] = bool(surface.visible)
        active_region = self.app_state.region_collection.active_region
        if active_region is not None:
            node_id = region_node_id(active_region.id)
            if node_id in node_ids:
                snapshot[node_id] = bool(active_region.visible)
        return snapshot

    def _apply_visibility_snapshot(self, snapshot: dict[str, bool]) -> None:
        if self.app_state.mesh_object is not None and NODE_MESH in snapshot:
            self.app_state.mesh_object.visible = bool(snapshot[NODE_MESH])
        for plane in self.app_state.section_collection.planes:
            node_id = section_plane_node_id(plane.id)
            if node_id in snapshot:
                plane.visible = bool(snapshot[node_id])
        for result in self.app_state.section_collection.results:
            node_id = section_result_node_id(result.id)
            if node_id in snapshot:
                result.visible = bool(snapshot[node_id])
        for curve in self.app_state.curve_collection.curves:
            node_id = curve_node_id(curve.id)
            if node_id in snapshot:
                curve.visible = bool(snapshot[node_id])
        for surface in self.app_state.surface_collection.surfaces:
            node_id = surface_node_id(surface.id)
            if node_id in snapshot:
                surface.visible = bool(snapshot[node_id])
        active_region = self.app_state.region_collection.active_region
        if active_region is not None:
            node_id = region_node_id(active_region.id)
            if node_id in snapshot:
                active_region.visible = bool(snapshot[node_id])

    def _delete_undo_command_for_targets(
        self,
        targets: dict[str, set[str]],
    ) -> CallbackUndoCommand | None:
        if targets["section_planes"] or targets["section_results"]:
            # TODO: Add section plane/result undo when cascading section state can be restored atomically.
            return None

        deleted_curves = [
            (index, copy.deepcopy(curve))
            for index, curve in enumerate(self.app_state.curve_collection.curves)
            if curve.id in targets["curves"]
        ]
        deleted_surfaces = [
            (index, copy.deepcopy(surface))
            for index, surface in enumerate(self.app_state.surface_collection.surfaces)
            if surface.id in targets["surfaces"]
        ]
        if not deleted_curves and not deleted_surfaces:
            return None

        curve_ids = {curve.id for _index, curve in deleted_curves}
        surface_ids = {surface.id for _index, surface in deleted_surfaces}
        command_name = self._delete_command_name(
            curve_count=len(deleted_curves),
            surface_count=len(deleted_surfaces),
        )
        return CallbackUndoCommand(
            command_name,
            undo_action=lambda: self._restore_deleted_curves_and_surfaces(
                deleted_curves,
                deleted_surfaces,
            ),
            redo_action=lambda: self._remove_curves_and_surfaces_for_undo(
                curve_ids,
                surface_ids,
            ),
        )

    @staticmethod
    def _delete_command_name(*, curve_count: int, surface_count: int) -> str:
        if curve_count == 1:
            return "Delete Curve"
        if surface_count == 1 and curve_count == 0:
            return "Delete Surface"
        if curve_count > 1 and surface_count == 0:
            return "Delete Curves"
        if surface_count > 1 and curve_count == 0:
            return "Delete Surfaces"
        return "Delete Objects"

    def _restore_deleted_curves_and_surfaces(
        self,
        curves: list[tuple[int, StoredCurve]],
        surfaces: list[tuple[int, SurfacePatch]],
    ) -> None:
        for index, curve in curves:
            self._restore_curve_at_index(copy.deepcopy(curve), index)
        for index, surface in surfaces:
            self._restore_surface_at_index(copy.deepcopy(surface), index)

    def _restore_curve_at_index(self, curve: StoredCurve, index: int) -> None:
        if any(existing.id == curve.id for existing in self.app_state.curve_collection.curves):
            return

        add_curve(self.app_state.curve_collection, curve)
        restored = self.app_state.curve_collection.curves.pop()
        insert_index = max(0, min(index, len(self.app_state.curve_collection.curves)))
        self.app_state.curve_collection.curves.insert(insert_index, restored)

    def _restore_surface_at_index(self, surface: SurfacePatch, index: int) -> None:
        if any(existing.id == surface.id for existing in self.app_state.surface_collection.surfaces):
            return

        add_surface(self.app_state.surface_collection, surface)
        restored = self.app_state.surface_collection.surfaces.pop()
        insert_index = max(0, min(index, len(self.app_state.surface_collection.surfaces)))
        self.app_state.surface_collection.surfaces.insert(insert_index, restored)

    def _remove_curves_and_surfaces_for_undo(
        self,
        curve_ids: set[str],
        surface_ids: set[str],
    ) -> None:
        for surface_id in surface_ids:
            remove_surface(self.app_state.surface_collection, surface_id)
        for curve_id in curve_ids:
            remove_curve(self.app_state.curve_collection, curve_id)

    def _push_created_curve_command(
        self,
        curve: StoredCurve,
        *,
        command_name: str = "Create Repaired Curve",
    ) -> None:
        curve_index = next(
            (
                index
                for index, existing in enumerate(self.app_state.curve_collection.curves)
                if existing.id == curve.id
            ),
            len(self.app_state.curve_collection.curves),
        )
        captured_curve = copy.deepcopy(curve)
        self._push_undo_command(
            CallbackUndoCommand(
                command_name,
                undo_action=lambda: remove_curve(self.app_state.curve_collection, captured_curve.id),
                redo_action=lambda: self._restore_curve_at_index(
                    copy.deepcopy(captured_curve),
                    curve_index,
                ),
            )
        )

    def _push_created_curves_command(
        self,
        curves: Sequence[StoredCurve],
        *,
        command_name: str,
    ) -> None:
        captured_curves = [copy.deepcopy(curve) for curve in curves]
        curve_indices = [
            next(
                (
                    index
                    for index, existing in enumerate(self.app_state.curve_collection.curves)
                    if existing.id == curve.id
                ),
                len(self.app_state.curve_collection.curves),
            )
            for curve in captured_curves
        ]
        captured_ids = [curve.id for curve in captured_curves]
        self._push_undo_command(
            CallbackUndoCommand(
                command_name,
                undo_action=lambda: self._remove_created_curves_for_undo(captured_ids),
                redo_action=lambda: self._restore_created_curves_for_undo(
                    captured_curves,
                    curve_indices,
                ),
            )
        )

    def _remove_created_curves_for_undo(self, curve_ids: Sequence[str]) -> None:
        for curve_id in curve_ids:
            remove_curve(self.app_state.curve_collection, curve_id)

    def _restore_created_curves_for_undo(
        self,
        curves: Sequence[StoredCurve],
        curve_indices: Sequence[int],
    ) -> None:
        restored_ids: list[str] = []
        for curve, curve_index in zip(curves, curve_indices):
            restored_curve = copy.deepcopy(curve)
            self._restore_curve_at_index(restored_curve, curve_index)
            restored_ids.append(restored_curve.id)
        if restored_ids:
            try:
                set_selected_curves(
                    self.app_state.curve_collection,
                    restored_ids,
                    active_curve_id=restored_ids[0],
                )
            except ValueError:
                return

    def _push_created_surface_command(self, surface: SurfacePatch) -> None:
        surface_index = next(
            (
                index
                for index, existing in enumerate(self.app_state.surface_collection.surfaces)
                if existing.id == surface.id
            ),
            len(self.app_state.surface_collection.surfaces),
        )
        captured_surface = copy.deepcopy(surface)
        self._push_undo_command(
            CallbackUndoCommand(
                "Create Surface",
                undo_action=lambda: remove_surface(
                    self.app_state.surface_collection,
                    captured_surface.id,
                ),
                redo_action=lambda: self._restore_surface_at_index(
                    copy.deepcopy(captured_surface),
                    surface_index,
                ),
            )
        )

    def _sync_after_undoable_scene_change(self) -> None:
        if (
            self._manual_curve_edit_active
            and self._active_manual_edit_curve() is None
        ):
            self._clear_manual_curve_state()
        elif self._manual_curve_edit_active:
            active_curve = self._active_manual_edit_curve()
            if active_curve is not None:
                self._load_manual_curve_edit_working_copy(active_curve)
        self._set_display_section_result(self._latest_stored_section_result())
        self._sync_visible_curve_results()
        self._sync_section_controls_from_active_plane()
        self._sync_section_result_context_from_active_result()
        self._sync_curve_context_from_active_curve()
        self._sync_surface_context_from_active_surface()
        self._refresh_scene_browser()
        self._refresh_viewport(reset_camera=False)

    def open_preferences(self) -> None:
        if self.preferences_dialog is not None and self.preferences_dialog.winfo_exists():
            self.preferences_dialog.lift()
            self.preferences_dialog.focus_set()
            return

        handle = build_preferences_dialog(
            self.root,
            settings=self.settings,
            proxy_quality_labels=PROXY_QUALITY_LABELS,
            apply_callback=self._apply_preferences_dialog,
            ok_callback=self._confirm_preferences_dialog,
            close_callback=self._close_preferences_dialog,
            placeholder_callback=self._not_implemented,
        )
        self.preferences_dialog = handle.dialog
        self.preferences_notebook = handle.notebook
        self.preferences_vars = handle.variables

    def _confirm_preferences_dialog(self) -> None:
        if self._apply_preferences_dialog():
            self._close_preferences_dialog()

    def _apply_preferences_dialog(self) -> bool:
        if not self.preferences_vars:
            return False

        show_grid = bool(self.preferences_vars["show_grid"].get())
        show_axes = bool(self.preferences_vars["show_axes"].get())
        show_axis_gizmo = bool(self.preferences_vars["show_axis_gizmo"].get())
        show_viewcube = bool(self.preferences_vars["show_viewcube"].get())
        window_mode = str(self.preferences_vars["window_mode"].get())
        remember_window_size = bool(self.preferences_vars["remember_window_size"].get())
        proxy_quality = normalize_proxy_quality(
            str(self.preferences_vars["default_proxy_quality"].get())
        )
        try:
            keybinds = self._keybind_settings_from_preferences()
            region_display_settings = self._region_display_settings_from_preferences()
        except ValueError as exc:
            self.status_text.set(str(exc))
            return False
        region_selection_color, region_selection_edge_color, region_selection_opacity = (
            region_display_settings
        )
        old_region_display_settings = (
            self.settings.display.region_selection_color,
            self.settings.display.region_selection_edge_color,
            float(self.settings.display.region_selection_opacity),
        )

        width, height = (
            self._current_window_size()
            if remember_window_size
            else (self.settings.ui.window_width, self.settings.ui.window_height)
        )
        self.settings = AppSettings(
            version=SETTINGS_VERSION,
            display=AppDisplaySettings(
                show_grid=show_grid,
                show_axes=show_axes,
                show_normals=False,
                show_axis_gizmo=show_axis_gizmo,
                show_viewcube=show_viewcube,
                region_selection_color=region_selection_color,
                region_selection_edge_color=region_selection_edge_color,
                region_selection_opacity=region_selection_opacity,
            ),
            import_settings=AppImportSettings(
                default_proxy_quality=proxy_quality,
            ),
            ui=AppUiSettings(
                window_width=width,
                window_height=height,
                window_mode=window_mode,
                remember_window_size=remember_window_size,
            ),
            keybinds=keybinds,
            future=dict(self.settings.future),
        )
        self._save_app_settings()
        if (
            old_region_display_settings != region_display_settings
            and self._active_visible_region_selection() is not None
        ):
            self._refresh_viewport(reset_camera=False)
        self.status_text.set("Preferences applied")
        return True

    def _keybind_settings_from_preferences(self) -> AppKeybindSettings:
        values: dict[str, str] = {}
        for field_name, label in KEYBIND_DISPLAY_ORDER:
            value = str(self.preferences_vars[f"keybind.{field_name}"].get()).strip()
            if not value:
                raise ValueError(f"{label} keybind cannot be empty")
            values[field_name] = value

        return AppKeybindSettings(**values)

    def _region_display_settings_from_preferences(self) -> tuple[str, str, float]:
        fill_color = self._hex_color_from_preferences(
            "region_selection_color",
            "Region Fill Color",
            DEFAULT_REGION_SELECTION_COLOR,
        )
        edge_color = self._hex_color_from_preferences(
            "region_selection_edge_color",
            "Region Edge Color",
            DEFAULT_REGION_SELECTION_EDGE_COLOR,
        )
        opacity = self._opacity_from_preferences(
            "region_selection_opacity",
            DEFAULT_REGION_SELECTION_OPACITY,
        )
        return (fill_color, edge_color, opacity)

    def _hex_color_from_preferences(
        self,
        variable_name: str,
        label: str,
        default: str,
    ) -> str:
        variable = self.preferences_vars.get(variable_name)
        raw_value = default if variable is None else str(variable.get())
        value = raw_value.strip().upper()
        if len(value) != 7 or not value.startswith("#"):
            raise ValueError(f"{label} must be #RRGGBB.")
        try:
            int(value[1:], 16)
        except ValueError as exc:
            raise ValueError(f"{label} must be #RRGGBB.") from exc
        if variable is not None:
            variable.set(value)
        return value

    def _opacity_from_preferences(self, variable_name: str, default: float) -> float:
        variable = self.preferences_vars.get(variable_name)
        raw_value = default if variable is None else str(variable.get()).strip()
        try:
            opacity = float(raw_value)
        except (TypeError, ValueError):
            raise ValueError("Region Opacity must be a number.") from None
        if not np.isfinite(opacity):
            raise ValueError("Region Opacity must be a number.")
        opacity = min(max(opacity, 0.05), 1.0)
        if variable is not None:
            variable.set(f"{opacity:.2f}")
        return opacity

    def _close_preferences_dialog(self) -> None:
        dialog = self.preferences_dialog
        self.preferences_dialog = None
        self.preferences_notebook = None
        self.preferences_vars = {}
        if dialog is not None and dialog.winfo_exists():
            dialog.destroy()

    def _about_placeholder(self) -> None:
        self._not_implemented("About")

    def _build_layout(self) -> None:
        style = ttk.Style(self.root)
        self._configure_workbench_theme(style)
        style.configure("SidebarHeading.TLabel", font=("", 10, "bold"))
        style.configure(
            "ViewControls.TFrame",
            background="#171b20",
            relief="solid",
            borderwidth=1,
        )
        style.configure(
            "ViewControlsHeading.TLabel",
            background="#171b20",
            foreground="#e7edf5",
            font=("", 9, "bold"),
        )

        workbench_bar = ttk.Frame(self.root, style="WorkbenchBar.TFrame", padding=(8, 6))
        workbench_bar.pack(fill="x", side="top")
        self._build_workbench_selector(workbench_bar)

        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        sidebar_shell = ttk.Frame(main, width=276, style="Sidebar.TFrame")
        sidebar_shell.grid(row=0, column=0, sticky="ns")
        sidebar_shell.grid_propagate(False)
        sidebar_shell.rowconfigure(0, weight=1)
        sidebar_shell.columnconfigure(0, weight=1)

        self.sidebar_canvas = Canvas(
            sidebar_shell,
            borderwidth=0,
            highlightthickness=0,
            width=272,
            background="#20242a",
        )
        self.sidebar_scrollbar = ttk.Scrollbar(
            sidebar_shell,
            orient="vertical",
            command=self.sidebar_canvas.yview,
        )
        self.sidebar_canvas.configure(yscrollcommand=self.sidebar_scrollbar.set)
        self.sidebar_canvas.grid(row=0, column=0, sticky="nsew")

        self.sidebar = ttk.Frame(self.sidebar_canvas, padding=8, style="Sidebar.TFrame")
        self.sidebar.columnconfigure(0, weight=1)
        self.sidebar_window = self.sidebar_canvas.create_window(
            (0, 0),
            window=self.sidebar,
            anchor="nw",
        )
        self.sidebar.bind("<Configure>", self._on_sidebar_content_configure)
        self.sidebar_canvas.bind("<Configure>", self._on_sidebar_canvas_configure)
        self.sidebar_canvas.bind_all("<MouseWheel>", self._on_sidebar_mousewheel)

        self.workbench_content = ttk.Frame(self.sidebar, style="Sidebar.TFrame")
        self.workbench_content.grid(row=0, column=0, sticky="nsew")
        self.workbench_content.columnconfigure(0, weight=1)
        self.sidebar.rowconfigure(0, weight=1)

        self.scene_tab = ttk.Frame(self.workbench_content, padding=6, style="Sidebar.TFrame")
        self.object_tab = self.scene_tab
        self.transform_tab = ttk.Frame(self.workbench_content, padding=6, style="Sidebar.TFrame")
        self.sections_tab = ttk.Frame(self.workbench_content, padding=6, style="Sidebar.TFrame")
        self.curves_tab = ttk.Frame(self.workbench_content, padding=6, style="Sidebar.TFrame")
        self.surfaces_tab = ttk.Frame(self.workbench_content, padding=6, style="Sidebar.TFrame")
        self.manual_re_tab = ttk.Frame(self.workbench_content, padding=6, style="Sidebar.TFrame")
        self.analysis_tab = ttk.Frame(self.workbench_content, padding=6, style="Sidebar.TFrame")
        self.info_tab = self.analysis_tab
        for tab in (
            self.scene_tab,
            self.transform_tab,
            self.sections_tab,
            self.curves_tab,
            self.surfaces_tab,
            self.manual_re_tab,
            self.analysis_tab,
        ):
            tab.columnconfigure(0, weight=1)

        self.workbench_panels = {
            "Scene": self.scene_tab,
            "Transform": self.transform_tab,
            "Sections": self.sections_tab,
            "Curves": self.curves_tab,
            "Surfaces": self.surfaces_tab,
            "Manual RE": self.manual_re_tab,
            "Analysis": self.analysis_tab,
        }
        for panel in self.workbench_panels.values():
            panel.grid(row=0, column=0, sticky="new")
            panel.grid_remove()

        self.file_frame = ttk.Frame(self.scene_tab)
        self.file_frame.grid(row=0, column=0, sticky="ew")
        self.file_frame.columnconfigure(1, weight=1)
        self._build_file_section(self.file_frame)

        self.no_selection_frame = ttk.Frame(self.scene_tab)
        self.no_selection_frame.grid(row=1, column=0, sticky="ew")
        self.no_selection_frame.columnconfigure(0, weight=1)
        self._build_no_selection_context(self.no_selection_frame)

        self.model_context_frame = ttk.Frame(self.transform_tab)
        self.model_context_frame.grid(row=0, column=0, sticky="ew")
        self.model_context_frame.columnconfigure(0, weight=1)
        self._build_model_context(self.model_context_frame)

        self.transform_empty_frame = ttk.Frame(self.transform_tab)
        self.transform_empty_frame.grid(row=1, column=0, sticky="ew")
        ttk.Label(
            self.transform_empty_frame,
            text="Select the model to edit transforms.",
            wraplength=250,
        ).grid(row=0, column=0, sticky="ew")

        self.section_context_frame = ttk.Frame(self.sections_tab)
        self.section_context_frame.grid(row=0, column=0, sticky="ew")
        self.section_context_frame.columnconfigure(0, weight=1)
        self._build_section_context(self.section_context_frame)

        self.section_result_context_frame = ttk.Frame(self.sections_tab)
        self.section_result_context_frame.grid(row=1, column=0, sticky="ew")
        self.section_result_context_frame.columnconfigure(0, weight=1)
        self._build_section_result_context(self.section_result_context_frame)

        self.curve_context_frame = ttk.Frame(self.curves_tab)
        self.curve_context_frame.grid(row=0, column=0, sticky="ew")
        self.curve_context_frame.columnconfigure(0, weight=1)
        self._build_curve_context(self.curve_context_frame)

        self.surface_context_frame = ttk.Frame(self.surfaces_tab)
        self.surface_context_frame.grid(row=0, column=0, sticky="ew")
        self.surface_context_frame.columnconfigure(0, weight=1)
        self._build_surface_context(self.surface_context_frame)

        self.manual_re_frame = ttk.Frame(self.manual_re_tab)
        self.manual_re_frame.grid(row=0, column=0, sticky="ew")
        self.manual_re_frame.columnconfigure(0, weight=1)
        self._build_manual_re_context(self.manual_re_frame)

        self.info_frame = ttk.Frame(self.info_tab)
        self.info_frame.grid(row=0, column=0, sticky="ew")
        self.info_frame.columnconfigure(1, weight=1)
        self._build_info_context(self.info_frame)

        self.viewport_frame = ttk.Frame(main)
        self.viewport_frame.grid(row=0, column=1, sticky="nsew")
        self._build_view_controls_shell(self.viewport_frame)

        self.scene_browser = SceneBrowser(
            main,
            selection_callback=self._on_scene_browser_selection,
            visibility_callback=self._on_scene_browser_visibility,
        )
        self.scene_browser.frame.grid(row=0, column=2, sticky="ns")

        self._build_status_strip()
        self._set_active_workbench("Scene", set_status=False)

    def _configure_workbench_theme(self, style: ttk.Style) -> None:
        try:
            style.theme_use("clam")
        except TclError:
            pass
        self.root.configure(background="#20242a")
        style.configure("TFrame", background="#20242a")
        style.configure("Sidebar.TFrame", background="#20242a")
        style.configure("WorkbenchBar.TFrame", background="#181c21")
        style.configure("Status.TFrame", background="#181c21")
        style.configure("TLabel", background="#20242a", foreground="#d9dee8")
        style.configure("SidebarHeading.TLabel", background="#20242a", foreground="#f2f5fa")
        style.configure("Status.TLabel", background="#181c21", foreground="#d9dee8")
        style.configure("StatusMode.TLabel", background="#181c21", foreground="#8fd3ff")
        style.configure("StatusPrompt.TLabel", background="#181c21", foreground="#f0f4fa")
        style.configure("TCheckbutton", background="#20242a", foreground="#d9dee8")
        style.configure("TButton", padding=(6, 4))
        style.configure("Workbench.TButton", padding=(10, 5))
        style.configure("ActiveWorkbench.TButton", padding=(10, 5))
        style.configure("ViewControls.TButton", padding=(4, 2))
        style.configure(
            "Treeview",
            background="#181c21",
            fieldbackground="#181c21",
            foreground="#d9dee8",
            bordercolor="#303640",
        )
        style.configure(
            "Treeview.Heading",
            background="#20242a",
            foreground="#f2f5fa",
        )
        style.map(
            "Treeview",
            background=[("selected", "#32506a")],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "TCombobox",
            fieldbackground="#181c21",
            background="#20242a",
            foreground="#d9dee8",
            arrowcolor="#d9dee8",
        )
        style.map(
            "ActiveWorkbench.TButton",
            foreground=[("!disabled", "#ffffff")],
            background=[("!disabled", "#32506a")],
        )

    def _build_workbench_selector(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(len(WORKBENCH_NAMES), weight=1)
        ttk.Label(
            parent,
            text="Workbench",
            style="Status.TLabel",
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.workbench_buttons: dict[str, ttk.Button] = {}
        for column, name in enumerate(WORKBENCH_NAMES, start=1):
            button = ttk.Button(
                parent,
                text=name,
                style="Workbench.TButton",
                command=lambda workbench=name: self._set_active_workbench(
                    workbench,
                    set_status=True,
                ),
            )
            button.grid(row=0, column=column, sticky="w", padx=(0, 4))
            self.workbench_buttons[name] = button

    def _build_status_strip(self) -> None:
        status_strip = ttk.Frame(self.root, style="Status.TFrame", padding=(8, 4))
        status_strip.pack(fill="x", side="bottom")
        status_strip.columnconfigure(1, weight=2)
        status_strip.columnconfigure(2, weight=1)
        status_strip.columnconfigure(3, weight=2)
        ttk.Label(status_strip, textvariable=self.current_mode_text, style="StatusMode.TLabel").grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 12),
        )
        ttk.Label(
            status_strip,
            textvariable=self.command_prompt_text,
            style="StatusPrompt.TLabel",
            anchor="w",
        ).grid(row=0, column=1, sticky="ew", padx=(0, 12))
        ttk.Label(
            status_strip,
            textvariable=self.hotkey_hint_text,
            style="Status.TLabel",
            anchor="w",
        ).grid(row=0, column=2, sticky="ew", padx=(0, 12))
        ttk.Label(
            status_strip,
            textvariable=self.status_text,
            style="Status.TLabel",
            anchor="w",
        ).grid(row=0, column=3, sticky="ew")

    def _set_active_workbench(self, workbench: str, *, set_status: bool) -> None:
        if workbench not in WORKBENCH_NAMES:
            return
        previous_workbench = self.current_workbench.get()
        if previous_workbench != workbench:
            self._clear_manual_curve_preview_state()
        self.current_workbench.set(workbench)
        for name, panel in getattr(self, "workbench_panels", {}).items():
            if name == workbench:
                panel.grid()
            else:
                panel.grid_remove()
        for name, button in getattr(self, "workbench_buttons", {}).items():
            button.configure(
                style="ActiveWorkbench.TButton" if name == workbench else "Workbench.TButton"
            )
        self._update_command_strip()
        self._sync_sidebar_scrollbar()
        if set_status:
            self.status_text.set(f"{workbench} workbench")

    def _on_sidebar_content_configure(self, _event: object | None = None) -> None:
        self.sidebar_canvas.configure(scrollregion=self.sidebar_canvas.bbox("all"))
        self._sync_sidebar_scrollbar()

    def _on_sidebar_canvas_configure(self, event: object) -> None:
        self.sidebar_canvas.itemconfigure(self.sidebar_window, width=getattr(event, "width", 0))
        self._sync_sidebar_scrollbar()

    def _sync_sidebar_scrollbar(self) -> None:
        if not hasattr(self, "sidebar_scrollbar"):
            return
        bbox = self.sidebar_canvas.bbox("all")
        if bbox is None:
            self.sidebar_scrollbar.grid_remove()
            return
        content_height = max(int(bbox[3] - bbox[1]), 0)
        canvas_height = max(int(self.sidebar_canvas.winfo_height()), 1)
        if content_height > canvas_height + 2:
            self.sidebar_scrollbar.grid(row=0, column=1, sticky="ns")
        else:
            self.sidebar_scrollbar.grid_remove()
            self.sidebar_canvas.yview_moveto(0.0)

    def _build_file_section(self, parent: ttk.Frame) -> None:
        row = self._add_heading(parent, 0, "Project")
        ttk.Button(parent, text="New Project", command=self.new_project).grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
        )
        row += 1
        self.open_model_button = ttk.Button(
            parent,
            text="Open Model",
            command=self.open_model,
        )
        self.open_model_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        row += 1
        ttk.Button(parent, text="Save Project", command=self.save_project).grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        row += 1
        ttk.Button(parent, text="Save Project As", command=self.save_project_as).grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        row += 1
        row = self._add_info_row(parent, row, "Loaded file", self.file_name_text)
        ttk.Label(parent, text="Proxy quality").grid(row=row, column=0, sticky="w", pady=2)
        self.proxy_quality_dropdown = ttk.Combobox(
            parent,
            textvariable=self.proxy_quality,
            values=PROXY_QUALITY_LABELS,
            width=10,
            state="readonly",
        )
        self.proxy_quality_dropdown.grid(row=row, column=1, sticky="ew", pady=2, padx=(8, 0))
        self.proxy_quality_dropdown.bind("<<ComboboxSelected>>", self._on_proxy_quality_changed)

    def _build_view_controls_shell(self, parent: ttk.Frame) -> None:
        self.view_controls_frame = ttk.Frame(parent, padding=(5, 4), style="ViewControls.TFrame")
        self.viewcube_frame = self.view_controls_frame
        ttk.Label(
            self.view_controls_frame,
            text="View",
            style="ViewControlsHeading.TLabel",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 2))
        for column in range(2):
            self.view_controls_frame.columnconfigure(column, weight=1)

        button_specs = (
            ("Top", "top", 1, 0),
            ("Front", "front", 1, 1),
            ("Right", "right", 2, 0),
            ("Iso", "isometric", 2, 1),
        )
        self.view_controls_buttons: list[ttk.Button] = []
        self.viewcube_buttons = self.view_controls_buttons
        for label, view_name, row, column in button_specs:
            button = ttk.Button(
                self.view_controls_frame,
                text=label,
                width=5,
                style="ViewControls.TButton",
                takefocus=False,
                command=lambda name=view_name: self.set_named_view(name),
            )
            button.grid(
                row=row,
                column=column,
                sticky="ew",
                padx=(0 if column == 0 else 2, 0),
                pady=(0 if row == 1 else 2, 0),
            )
            self.view_controls_buttons.append(button)

    def _build_viewcube_shell(self, parent: ttk.Frame) -> None:
        self._build_view_controls_shell(parent)

    def _sync_viewcube_shell_visibility(self) -> None:
        frame = getattr(self, "view_controls_frame", None)
        if frame is None:
            return

        if bool(self.show_view_controls.get()):
            frame.place(relx=1.0, x=-10, y=10, anchor="ne")
            frame.lift()
        else:
            frame.place_forget()

    def _build_no_selection_context(self, parent: ttk.Frame) -> None:
        row = self._add_separator(parent, 0)
        row = self._add_heading(parent, row, "Start")
        ttk.Label(
            parent,
            textvariable=self.empty_scene_prompt_text,
            wraplength=250,
        ).grid(row=row, column=0, columnspan=2, sticky="ew")
        row += 1
        self.empty_open_model_button = ttk.Button(
            parent,
            text="Open Model",
            command=self.open_model,
        )
        self.empty_open_model_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(6, 0),
        )
        row += 1

        row = self._add_separator(parent, row)
        row = self._add_heading(parent, row, "View")
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
        self.show_axis_gizmo_check = ttk.Checkbutton(
            parent,
            text="Show Axis Gizmo",
            variable=self.show_axis_gizmo,
            command=self._on_view_option_changed,
        )
        self.show_axis_gizmo_check.grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        self.show_view_controls_check = ttk.Checkbutton(
            parent,
            text="Show View Controls",
            variable=self.show_view_controls,
            command=self._on_view_option_changed,
        )
        self.show_view_controls_check.grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        self.scene_mesh_visible_check = ttk.Checkbutton(
            parent,
            text="Mesh Visible",
            variable=self.mesh_visible,
            command=self._on_mesh_visibility_changed,
        )
        self.scene_mesh_visible_check.grid(row=row, column=0, columnspan=2, sticky="w")
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
        self.scene_delete_mesh_button = ttk.Button(
            parent,
            text="Delete Mesh",
            command=self.delete_mesh,
        )
        self.scene_delete_mesh_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(8, 0),
        )

    def _build_model_context(self, parent: ttk.Frame) -> None:
        row = self._add_separator(parent, 0)
        row = self._add_heading(parent, row, "Selected Object")
        self.mesh_visible_check = ttk.Checkbutton(
            parent,
            text="Visible",
            variable=self.mesh_visible,
            command=self._on_mesh_visibility_changed,
        )
        self.mesh_visible_check.grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        row, self.mesh_name_entry = self._add_editable_name_row(
            parent,
            row,
            self.mesh_name_text,
            self._on_mesh_name_changed,
        )
        row = self._add_info_row(parent, row, "Type", self.selected_object_type_text)
        row = self._add_info_row(parent, row, "Vertices", self.selected_vertex_count_text)
        row = self._add_info_row(parent, row, "Source triangles", self.selected_triangle_count_text)
        row = self._add_info_row(
            parent,
            row,
            "Display triangles",
            self.selected_display_triangle_count_text,
        )
        row = self._add_info_row(parent, row, "Reduction", self.selected_display_reduction_text)
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
        self.move_transform_button = ttk.Button(
            parent,
            text="Move",
            command=self.start_move_transform,
        )
        self.move_transform_button.grid(row=row, column=0, sticky="ew", pady=(8, 0))
        self.selection_buttons.append(self.move_transform_button)
        self.rotate_transform_button = ttk.Button(
            parent,
            text="Rotate",
            command=self.start_rotate_transform,
        )
        self.rotate_transform_button.grid(row=row, column=1, sticky="ew", pady=(8, 0), padx=(6, 0))
        self.selection_buttons.append(self.rotate_transform_button)
        row += 1
        ttk.Label(
            parent,
            text="Generated curves and surfaces may not follow mesh transforms.",
            wraplength=240,
        ).grid(row=row, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        row += 1

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
        self.section_add_plane_button = ttk.Button(
            parent,
            text="Add Section Plane",
            command=self.add_section_plane,
        )
        self.section_add_plane_button.grid(row=row, column=0, columnspan=2, sticky="ew")
        row += 1
        self.section_delete_plane_button = ttk.Button(
            parent,
            text="Delete Selected Section Plane",
            command=self.delete_active_section_plane,
        )
        self.section_delete_plane_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        row += 1
        row, self.section_plane_name_entry = self._add_editable_name_row(
            parent,
            row,
            self.section_plane_name_text,
            self._on_section_plane_name_changed,
        )
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
            text="Clear Active Section Result",
            command=self.clear_active_section_result,
        )
        self.clear_section_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        row += 1
        self.clear_all_sections_button = ttk.Button(
            parent,
            text="Clear All Section Results",
            command=self.clear_all_section_results,
        )
        self.clear_all_sections_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        row += 1
        ttk.Label(
            parent,
            text="Use Move/Rotate on a selected section plane for arbitrary plane placement.",
            wraplength=240,
        ).grid(row=row, column=0, columnspan=2, sticky="ew", pady=(6, 0))
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

    def _build_section_result_context(self, parent: ttk.Frame) -> None:
        row = self._add_separator(parent, 0)
        row = self._add_heading(parent, row, "Section Result")
        self.section_result_visible_check = ttk.Checkbutton(
            parent,
            text="Visible",
            variable=self.section_result_visible,
            command=self._on_section_result_visibility_changed,
        )
        self.section_result_visible_check.grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        row, self.section_result_name_entry = self._add_editable_name_row(
            parent,
            row,
            self.section_result_name_text,
            self._on_section_result_name_changed,
        )
        row = self._add_info_row(parent, row, "Source plane", self.section_result_source_plane_text)
        row = self._add_info_row(parent, row, "Axis", self.section_result_axis_text)
        row = self._add_info_row(parent, row, "Offset", self.section_result_offset_text)
        row = self._add_info_row(parent, row, "Segments", self.section_result_segment_count_text)
        row = self._add_info_row(parent, row, "Curves", self.section_result_curve_count_text)
        self.section_result_deselect_button = ttk.Button(
            parent,
            text="Deselect",
            command=self.clear_selection,
        )
        self.section_result_deselect_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(8, 0),
        )
        self.selection_buttons.append(self.section_result_deselect_button)

    def _build_curve_context(self, parent: ttk.Frame) -> None:
        row = self._add_separator(parent, 0)
        row = self._add_heading(parent, row, "Curve")
        self.curve_visible_check = ttk.Checkbutton(
            parent,
            text="Visible",
            variable=self.curve_visible,
            command=self._on_curve_visibility_changed,
        )
        self.curve_visible_check.grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        row = self._add_curve_name_row(parent, row)
        row = self._add_info_row(parent, row, "Section", self.curve_section_text)
        row = self._add_info_row(parent, row, "Plane", self.curve_plane_text)
        row = self._add_info_row(parent, row, "Points", self.curve_point_count_text)
        row = self._add_info_row(parent, row, "Length", self.curve_length_text)
        row = self._add_info_row(parent, row, "Endpoint gap", self.curve_endpoint_gap_text)
        row = self._add_info_row(parent, row, "Shape", self.curve_closed_text)
        row = self._add_info_row(parent, row, "Mean error", self.curve_mean_error_text)
        row = self._add_info_row(parent, row, "Max error", self.curve_max_error_text)
        row = self._add_info_row(parent, row, "Tiny fragment", self.curve_tiny_text)
        row = self._add_info_row(parent, row, "Type", self.curve_type_text)
        row = self._add_info_row(parent, row, "Source", self.curve_source_text)
        row = self._add_info_row(parent, row, "Control points", self.curve_control_point_count_text)
        row = self._add_info_row(parent, row, "Planarity error", self.curve_planarity_error_text)
        row = self._add_info_row(parent, row, "Projection mean", self.curve_projection_mean_distance_text)
        row = self._add_info_row(parent, row, "Projection max", self.curve_projection_max_distance_text)
        row = self._add_info_row(parent, row, "Surface readiness", self.curve_surface_readiness_text)
        row = self._add_info_row(parent, row, "Warnings", self.curve_surface_warnings_text)
        row = self._add_info_row(parent, row, "Errors", self.curve_surface_errors_text)
        self.project_curve_to_mesh_button = ttk.Button(
            parent,
            text="Project Selected Curve to Mesh",
            command=self.project_selected_curve_to_mesh,
        )
        self.project_curve_to_mesh_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.selection_buttons.append(self.project_curve_to_mesh_button)
        row += 1
        ttk.Label(parent, text="Target Control Points").grid(row=row, column=0, sticky="w", pady=(6, 0))
        self.rebuild_target_control_points_entry = ttk.Entry(
            parent,
            textvariable=self.rebuild_target_control_points,
            width=8,
        )
        self.rebuild_target_control_points_entry.grid(row=row, column=1, sticky="ew", pady=(6, 0), padx=(8, 0))
        row += 1
        ttk.Label(parent, text="Rebuild Type").grid(row=row, column=0, sticky="w", pady=(6, 0))
        self.rebuild_curve_type_combo = ttk.Combobox(
            parent,
            textvariable=self.rebuild_curve_type_text,
            values=("Smooth Curve", "Polyline"),
            state="readonly",
            width=14,
        )
        self.rebuild_curve_type_combo.grid(row=row, column=1, sticky="ew", pady=(6, 0), padx=(8, 0))
        row += 1
        ttk.Label(parent, text="Sample Count").grid(row=row, column=0, sticky="w", pady=(6, 0))
        self.rebuild_sample_count_entry = ttk.Entry(
            parent,
            textvariable=self.rebuild_sample_count,
            width=8,
        )
        self.rebuild_sample_count_entry.grid(row=row, column=1, sticky="ew", pady=(6, 0), padx=(8, 0))
        row += 1
        self.rebuild_curve_button = ttk.Button(
            parent,
            text="Rebuild Selected Curve",
            command=self.rebuild_selected_curve,
        )
        self.rebuild_curve_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.selection_buttons.append(self.rebuild_curve_button)
        row += 1
        self.validate_curve_button = ttk.Button(
            parent,
            text="Validate Selected Curve",
            command=self.validate_selected_curve,
        )
        self.validate_curve_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.selection_buttons.append(self.validate_curve_button)
        row += 1
        self.validate_loft_curves_button = ttk.Button(
            parent,
            text="Validate Selected Curves for Loft",
            command=self.validate_selected_curves_for_loft,
        )
        self.validate_loft_curves_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.selection_buttons.append(self.validate_loft_curves_button)
        row += 1
        self.delete_curve_button = ttk.Button(
            parent,
            text="Delete Selected Curve",
            command=self.delete_selected_curve,
        )
        self.delete_curve_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.selection_buttons.append(self.delete_curve_button)
        row += 1
        self.edit_selected_curve_button = ttk.Button(
            parent,
            text="Edit Selected Curve",
            command=self.start_manual_curve_edit_mode,
        )
        self.edit_selected_curve_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.selection_buttons.append(self.edit_selected_curve_button)
        row += 1
        self.join_curves_button = ttk.Button(
            parent,
            text="Join Selected Curves",
            command=self.join_selected_curves,
        )
        self.join_curves_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.selection_buttons.append(self.join_curves_button)
        row += 1
        self.auto_close_curve_button = ttk.Button(
            parent,
            text="Auto-Close Selected Curve",
            command=self.auto_close_selected_curve,
        )
        self.auto_close_curve_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        self.selection_buttons.append(self.auto_close_curve_button)
        row += 1
        self.simplify_curve_button = ttk.Button(
            parent,
            text="Simplify Selected Curve",
            command=self.simplify_selected_curve,
        )
        self.simplify_curve_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        self.selection_buttons.append(self.simplify_curve_button)
        row += 1
        self.smooth_curve_button = ttk.Button(
            parent,
            text="Smooth Selected Curve",
            command=self.smooth_selected_curve,
        )
        self.smooth_curve_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        self.selection_buttons.append(self.smooth_curve_button)
        row += 1
        self.hide_selected_curves_button = ttk.Button(
            parent,
            text="Hide Selected Curves",
            command=self.hide_selected_curves,
        )
        self.hide_selected_curves_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        self.selection_buttons.append(self.hide_selected_curves_button)
        row += 1
        self.hide_unselected_curves_button = ttk.Button(
            parent,
            text="Hide Unselected Curves",
            command=self.hide_unselected_curves,
        )
        self.hide_unselected_curves_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        self.selection_buttons.append(self.hide_unselected_curves_button)
        row += 1
        self.show_all_curves_button = ttk.Button(
            parent,
            text="Show All Curves",
            command=self.show_all_curves,
        )
        self.show_all_curves_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        self.selection_buttons.append(self.show_all_curves_button)
        row += 1
        self.select_tiny_curves_button = ttk.Button(
            parent,
            text="Select Tiny Curves",
            command=self.select_tiny_curves,
        )
        self.select_tiny_curves_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        self.selection_buttons.append(self.select_tiny_curves_button)
        row += 1
        self.hide_tiny_curves_button = ttk.Button(
            parent,
            text="Hide Tiny Curves",
            command=self.hide_tiny_curves,
        )
        self.hide_tiny_curves_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        self.selection_buttons.append(self.hide_tiny_curves_button)
        row += 1
        self.delete_tiny_curves_button = ttk.Button(
            parent,
            text="Delete Tiny Curves",
            command=self.delete_tiny_curves,
        )
        self.delete_tiny_curves_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        self.selection_buttons.append(self.delete_tiny_curves_button)
        row += 1
        self.curve_deselect_button = ttk.Button(
            parent,
            text="Deselect",
            command=self.clear_selection,
        )
        self.curve_deselect_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.selection_buttons.append(self.curve_deselect_button)

    def _build_surface_context(self, parent: ttk.Frame) -> None:
        row = self._add_separator(parent, 0)
        row = self._add_heading(parent, row, "Surface")
        self.fill_closed_curve_button = ttk.Button(
            parent,
            text="Fill Closed Curve",
            command=self.fill_closed_curve,
        )
        self.fill_closed_curve_button.grid(row=row, column=0, columnspan=2, sticky="ew")
        row += 1
        self.loft_curves_button = ttk.Button(
            parent,
            text="Loft Between Two Curves",
            command=self.loft_between_two_curves,
        )
        self.loft_curves_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        row += 1
        self.boundary_patch_button = ttk.Button(
            parent,
            text="Create Boundary Patch",
            command=self.create_boundary_patch_from_curve,
        )
        self.boundary_patch_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        row += 1
        self.four_curve_patch_button = ttk.Button(
            parent,
            text="Create Four-Curve Patch",
            command=self.create_four_curve_patch,
        )
        self.four_curve_patch_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        row += 1
        self.curve_network_patch_button = ttk.Button(
            parent,
            text="Create Curve Network Patch",
            command=self.create_curve_network_patch,
        )
        self.curve_network_patch_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        row += 1
        self.surface_visible_check = ttk.Checkbutton(
            parent,
            text="Visible",
            variable=self.surface_visible,
            command=self._on_surface_visibility_changed,
        )
        self.surface_visible_check.grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        row, self.surface_name_entry = self._add_editable_name_row(
            parent,
            row,
            self.surface_name_text,
            self._on_surface_name_changed,
        )
        row = self._add_info_row(parent, row, "Type", self.surface_type_text)
        row = self._add_info_row(parent, row, "Preview mode", self.surface_preview_mode_text)
        row = self._add_info_row(
            parent,
            row,
            "Source curves",
            self.surface_source_curve_count_text,
        )
        row = self._add_info_row(
            parent,
            row,
            "Source names",
            self.surface_source_curve_names_text,
        )
        row = self._add_info_row(
            parent,
            row,
            "Preview available",
            self.surface_preview_available_text,
        )
        row = self._add_info_row(parent, row, "Preview reason", self.surface_preview_reason_text)
        row = self._add_info_row(
            parent,
            row,
            "Preview warning",
            self.surface_preview_warning_text,
        )
        row = self._add_info_row(parent, row, "Grid size", self.surface_grid_size_text)
        row = self._add_info_row(
            parent,
            row,
            "Planarity error",
            self.surface_planarity_error_text,
        )
        row = self._add_info_row(
            parent,
            row,
            "Resampled points",
            self.surface_resampled_point_count_text,
        )
        row = self._add_info_row(
            parent,
            row,
            "Reversed second",
            self.surface_reversed_second_curve_text,
        )
        row = self._add_info_row(
            parent,
            row,
            "Seam shifted",
            self.surface_seam_shift_applied_text,
        )
        row = self._add_info_row(
            parent,
            row,
            "Average pair distance",
            self.surface_average_pair_distance_text,
        )
        row = self._add_info_row(
            parent,
            row,
            "Max pair distance",
            self.surface_max_pair_distance_text,
        )
        row = self._add_info_row(
            parent,
            row,
            "Validation warnings",
            self.surface_validation_warnings_text,
        )
        row = self._add_info_row(
            parent,
            row,
            "Validation errors",
            self.surface_validation_errors_text,
        )
        row = self._add_info_row(parent, row, "Opacity", self.surface_opacity_text)
        self.surface_opacity_slider = ttk.Scale(
            parent,
            from_=0.05,
            to=1.0,
            variable=self.surface_opacity,
            command=self._on_surface_opacity_changed,
        )
        self.surface_opacity_slider.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(2, 6),
        )
        row += 1
        self.surface_wireframe_check = ttk.Checkbutton(
            parent,
            text="Wireframe overlay",
            variable=self.surface_wireframe_overlay,
            command=self._on_surface_wireframe_changed,
        )
        self.surface_wireframe_check.grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        row = self._add_info_row(parent, row, "Raw metadata", self.surface_metadata_text)
        self.select_source_curves_button = ttk.Button(
            parent,
            text="Select Source Curves",
            command=self.select_source_curves_for_active_surface,
        )
        self.select_source_curves_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(8, 0),
        )
        self.selection_buttons.append(self.select_source_curves_button)
        row += 1
        self.isolate_source_curves_button = ttk.Button(
            parent,
            text="Isolate Source Curves",
            command=self.isolate_source_curves_for_active_surface,
        )
        self.isolate_source_curves_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        self.selection_buttons.append(self.isolate_source_curves_button)
        row += 1
        self.show_source_curves_button = ttk.Button(
            parent,
            text="Show Source Curves",
            command=self.show_source_curves_for_active_surface,
        )
        self.show_source_curves_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        self.selection_buttons.append(self.show_source_curves_button)
        row += 1
        self.frame_source_curves_button = ttk.Button(
            parent,
            text="Frame Source Curves",
            command=self.frame_source_curves_for_active_surface,
        )
        self.frame_source_curves_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        self.selection_buttons.append(self.frame_source_curves_button)
        row += 1
        self.delete_surface_button = ttk.Button(
            parent,
            text="Delete Surface",
            command=self.delete_selected_surface,
        )
        self.delete_surface_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.selection_buttons.append(self.delete_surface_button)
        row += 1
        self.surface_deselect_button = ttk.Button(
            parent,
            text="Deselect",
            command=self.clear_selection,
        )
        self.surface_deselect_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.selection_buttons.append(self.surface_deselect_button)

    def _build_manual_re_context(self, parent: ttk.Frame) -> None:
        row = self._add_heading(parent, 0, "Manual Curve")
        ttk.Label(
            parent,
            textvariable=self.manual_curve_mode_title,
            style="SidebarHeading.TLabel",
        ).grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        ttk.Label(
            parent,
            textvariable=self.manual_curve_mode_details,
            wraplength=250,
        ).grid(row=row, column=0, columnspan=2, sticky="ew", pady=(2, 6))
        row += 1
        self.start_manual_curve_button = ttk.Button(
            parent,
            text="Create Manual Curve",
            command=self.start_manual_curve_mode,
        )
        self.start_manual_curve_button.grid(row=row, column=0, columnspan=2, sticky="ew")
        row += 1
        self.edit_manual_curve_button = ttk.Button(
            parent,
            text="Edit Selected Curve",
            command=self.start_manual_curve_edit_mode,
        )
        self.edit_manual_curve_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        row += 1
        self.manual_project_curve_to_mesh_button = ttk.Button(
            parent,
            text="Project Selected Curve to Mesh",
            command=self.project_selected_curve_to_mesh,
        )
        self.manual_project_curve_to_mesh_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        row += 1
        self.manual_rebuild_curve_button = ttk.Button(
            parent,
            text="Rebuild Selected Curve",
            command=self.rebuild_selected_curve,
        )
        self.manual_rebuild_curve_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        row += 1
        self.finish_manual_curve_button = ttk.Button(
            parent,
            text="Finish Curve",
            command=self._confirm_manual_curve,
        )
        self.finish_manual_curve_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        row += 1
        self.cancel_manual_curve_button = ttk.Button(
            parent,
            text="Cancel",
            command=lambda: self._cancel_manual_curve_mode(status="Manual curve cancelled"),
        )
        self.cancel_manual_curve_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        row += 1
        self.done_manual_curve_edit_button = ttk.Button(
            parent,
            text="Done Editing",
            command=self.done_manual_curve_editing,
        )
        self.done_manual_curve_edit_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        row += 1
        self.remove_manual_point_button = ttk.Button(
            parent,
            text="Remove Last Point",
            command=self._remove_last_manual_curve_point,
        )
        self.remove_manual_point_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        row += 1
        self.toggle_manual_closed_button = ttk.Button(
            parent,
            text="Toggle Closed",
            command=self._toggle_manual_curve_closed,
        )
        self.toggle_manual_closed_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        row += 1
        self.add_manual_point_button = ttk.Button(
            parent,
            text="Add Point",
            command=self.activate_manual_curve_add_point,
        )
        self.add_manual_point_button.grid(
            row=row,
            column=0,
            sticky="ew",
            pady=(4, 0),
        )
        self.insert_manual_point_button = ttk.Button(
            parent,
            text="Insert Point",
            command=self.activate_manual_curve_insert_point,
        )
        self.insert_manual_point_button.grid(
            row=row,
            column=1,
            sticky="ew",
            pady=(4, 0),
            padx=(8, 0),
        )
        row += 1
        self.delete_manual_point_button = ttk.Button(
            parent,
            text="Delete Selected Point",
            command=self.delete_selected_manual_curve_point,
        )
        self.delete_manual_point_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        row += 1
        ttk.Label(parent, text="Curve Type").grid(row=row, column=0, sticky="w", pady=(6, 0))
        self.manual_curve_type_combo = ttk.Combobox(
            parent,
            textvariable=self.manual_curve_type_text,
            values=("Smooth Curve", "Polyline"),
            state="readonly",
        )
        self.manual_curve_type_combo.grid(row=row, column=1, sticky="ew", pady=(6, 0), padx=(8, 0))
        self.manual_curve_type_combo.bind("<<ComboboxSelected>>", self._on_manual_curve_type_changed)
        row += 1
        self.manual_curve_snap_check = ttk.Checkbutton(
            parent,
            text="Snap to Mesh",
            variable=self.manual_curve_snap_to_mesh,
            command=self._on_manual_curve_snap_to_mesh_changed,
        )
        self.manual_curve_snap_check.grid(row=row, column=0, columnspan=2, sticky="w", pady=(6, 0))
        row += 1
        ttk.Label(
            parent,
            textvariable=self.manual_curve_snap_help_text,
            wraplength=250,
        ).grid(row=row, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        row += 1
        row = self._add_separator(parent, row)
        row = self._add_heading(parent, row, "Region Selection")
        self.region_select_button = ttk.Button(
            parent,
            text="Region Select",
            command=self.start_region_select_mode,
        )
        self.region_select_button.grid(row=row, column=0, columnspan=2, sticky="ew")
        row += 1
        ttk.Label(parent, text="Region Name").grid(row=row, column=0, sticky="w", pady=(6, 0))
        self.region_name_entry = ttk.Entry(
            parent,
            textvariable=self.region_name_text,
        )
        self.region_name_entry.grid(row=row, column=1, sticky="ew", pady=(6, 0), padx=(8, 0))
        self.region_name_entry.bind("<KeyRelease>", self._on_region_name_changed)
        self.region_name_entry.bind("<FocusOut>", self._on_region_name_changed)
        self.region_name_entry.bind("<Return>", self._on_region_name_changed)
        row += 1
        self.recompute_region_button = ttk.Button(
            parent,
            text="Recompute Region",
            command=self.recompute_region_selection,
        )
        self.recompute_region_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        row += 1
        self.clear_region_button = ttk.Button(
            parent,
            text="Clear Region",
            command=self.clear_region_selection,
        )
        self.clear_region_button.grid(row=row, column=0, sticky="ew", pady=(4, 0))
        self.hide_region_button = ttk.Button(
            parent,
            text="Hide Region",
            command=self.hide_region_selection,
        )
        self.hide_region_button.grid(row=row, column=1, sticky="ew", pady=(4, 0), padx=(8, 0))
        row += 1
        self.show_region_button = ttk.Button(
            parent,
            text="Show Region",
            command=self.show_region_selection,
        )
        self.show_region_button.grid(row=row, column=0, sticky="ew", pady=(4, 0))
        self.delete_region_button = ttk.Button(
            parent,
            text="Delete Region",
            command=self.delete_region_selection,
        )
        self.delete_region_button.grid(row=row, column=1, sticky="ew", pady=(4, 0), padx=(8, 0))
        row += 1
        self.done_region_select_button = ttk.Button(
            parent,
            text="Done Selecting",
            command=lambda: self._exit_region_select_mode(status="Region Select finished"),
        )
        self.done_region_select_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        row += 1
        ttk.Label(parent, text="Threshold").grid(row=row, column=0, sticky="w", pady=(6, 0))
        self.region_threshold_entry = ttk.Entry(
            parent,
            textvariable=self.region_threshold_text,
            width=8,
        )
        self.region_threshold_entry.grid(row=row, column=1, sticky="ew", pady=(6, 0), padx=(8, 0))
        self.region_threshold_entry.bind("<FocusOut>", self._on_region_threshold_entry_changed)
        self.region_threshold_entry.bind("<Return>", self._on_region_threshold_entry_changed)
        row += 1
        self.region_threshold_slider = ttk.Scale(
            parent,
            from_=0.0,
            to=90.0,
            variable=self.region_threshold_degrees,
            command=self._on_region_threshold_slider_changed,
        )
        self.region_threshold_slider.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        row += 1
        ttk.Label(parent, text="Max Triangles").grid(row=row, column=0, sticky="w", pady=(6, 0))
        self.region_max_triangle_entry = ttk.Entry(
            parent,
            textvariable=self.region_max_triangle_count,
            width=12,
        )
        self.region_max_triangle_entry.grid(row=row, column=1, sticky="ew", pady=(6, 0), padx=(8, 0))
        self.region_max_triangle_entry.bind("<FocusOut>", self._on_region_max_triangle_entry_changed)
        self.region_max_triangle_entry.bind("<Return>", self._on_region_max_triangle_entry_changed)
        row += 1
        row = self._add_info_row(parent, row, "Triangles", self.region_triangle_count_text)
        row = self._add_info_row(parent, row, "Seed triangle", self.region_seed_triangle_text)
        row = self._add_info_row(parent, row, "Region status", self.region_status_text)
        self.extract_region_boundary_button = ttk.Button(
            parent,
            text="Extract Region Boundary",
            command=self.extract_region_boundary,
        )
        self.extract_region_boundary_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        row += 1
        self.select_region_boundary_curves_button = ttk.Button(
            parent,
            text="Select Boundary Curves",
            command=self.select_boundary_curves_for_active_region,
        )
        self.select_region_boundary_curves_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )
        row += 1
        row = self._add_separator(parent, row)
        row = self._add_heading(parent, row, "Coming Later")
        self.fit_patch_from_region_placeholder_button = ttk.Button(
            parent,
            text="Fit Patch From Region",
            command=lambda: self._not_implemented("Fit Patch From Region"),
        )
        self.fit_patch_from_region_placeholder_button.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 0),
        )

    def _build_info_context(self, parent: ttk.Frame) -> None:
        row = self._add_heading(parent, 0, "Project")
        row = self._add_info_row(parent, row, "Loaded file", self.file_name_text)
        row = self._add_info_row(parent, row, "Project", self.project_path_text)
        row = self._add_info_row(parent, row, "Mode", self.current_mode_text)
        row = self._add_info_row(parent, row, "Status", self.status_text)
        row = self._add_separator(parent, row)
        row = self._add_heading(parent, row, "Mesh Stats")
        row = self._add_info_row(parent, row, "Vertices", self.vertex_count_text)
        row = self._add_info_row(parent, row, "Source triangles", self.triangle_count_text)
        row = self._add_info_row(parent, row, "Display triangles", self.display_triangle_count_text)
        row = self._add_info_row(parent, row, "Reduction", self.display_reduction_text)
        row = self._add_info_row(parent, row, "Display proxy", self.display_proxy_text)
        row = self._add_info_row(parent, row, "Source", self.source_retained_text)
        row = self._add_info_row(parent, row, "Bounding box", self.bbox_size_text)
        row = self._add_separator(parent, row)
        row = self._add_heading(parent, row, "Selection Stats")
        row = self._add_info_row(parent, row, "Selected", self.selected_object_text)
        row = self._add_info_row(parent, row, "Vertices", self.selected_vertex_count_text)
        row = self._add_info_row(parent, row, "Source triangles", self.selected_triangle_count_text)
        row = self._add_info_row(parent, row, "Display triangles", self.selected_display_triangle_count_text)
        row = self._add_info_row(parent, row, "Bounding box", self.selected_bbox_size_text)
        row = self._add_separator(parent, row)
        row = self._add_heading(parent, row, "Active Region")
        row = self._add_info_row(parent, row, "Region", self.region_name_text)
        row = self._add_info_row(parent, row, "Triangle count", self.region_triangle_count_text)
        row = self._add_info_row(parent, row, "Threshold", self.region_threshold_display_text)
        row = self._add_info_row(parent, row, "Max cap", self.region_max_triangle_cap_text)
        row = self._add_info_row(parent, row, "Seed triangle", self.region_seed_triangle_text)
        row = self._add_info_row(parent, row, "Source mesh", self.region_source_mesh_text)
        row = self._add_info_row(parent, row, "Visible", self.region_visible_text)
        row = self._add_info_row(parent, row, "Boundary curves", self.region_boundary_curve_count_text)
        row = self._add_separator(parent, row)
        row = self._add_heading(parent, row, "Hotkeys")
        ttk.Label(
            parent,
            text="Enter finish, Esc cancel, Backspace remove point, C toggle closed, G move, R rotate, F frame.",
            wraplength=250,
        ).grid(row=row, column=0, columnspan=2, sticky="ew")

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

    def _add_editable_name_row(
        self,
        parent: ttk.Frame,
        row: int,
        value: StringVar,
        callback: object,
    ) -> tuple[int, ttk.Entry]:
        ttk.Label(parent, text="Name").grid(row=row, column=0, sticky="w", pady=2)
        entry = ttk.Entry(parent, textvariable=value)
        entry.grid(row=row, column=1, sticky="ew", pady=2, padx=(8, 0))
        entry.bind("<KeyRelease>", callback)
        entry.bind("<FocusOut>", callback)
        entry.bind("<Return>", callback)
        return (row + 1, entry)

    def _add_curve_name_row(self, parent: ttk.Frame, row: int) -> int:
        row, self.curve_name_entry = self._add_editable_name_row(
            parent,
            row,
            self.curve_name_text,
            self._on_curve_name_changed,
        )
        return row

    def _show_context(self, selected_item: str | None) -> None:
        if selected_item == SELECT_MODEL and self.app_state.mesh_object is not None:
            self.model_context_frame.grid()
            self.transform_empty_frame.grid_remove()
            self._set_active_workbench("Transform", set_status=False)
        elif selected_item == SELECT_SECTION_PLANE and self.app_state.mesh_object is not None:
            self.model_context_frame.grid_remove()
            self.transform_empty_frame.grid()
            self._set_active_workbench("Sections", set_status=False)
        elif selected_item == SELECT_SECTION_RESULT and self.app_state.mesh_object is not None:
            self.model_context_frame.grid_remove()
            self.transform_empty_frame.grid()
            self._set_active_workbench("Sections", set_status=False)
        elif selected_item == SELECT_CURVE and self.app_state.mesh_object is not None:
            self.model_context_frame.grid_remove()
            self.transform_empty_frame.grid()
            self._set_active_workbench("Curves", set_status=False)
        elif selected_item == SELECT_SURFACE and self.app_state.mesh_object is not None:
            self.model_context_frame.grid_remove()
            self.transform_empty_frame.grid()
            self._set_active_workbench("Surfaces", set_status=False)
        elif selected_item == SELECT_REGION and self.app_state.mesh_object is not None:
            self.model_context_frame.grid_remove()
            self.transform_empty_frame.grid()
            self._set_active_workbench("Manual RE", set_status=False)
        else:
            self.model_context_frame.grid_remove()
            self.transform_empty_frame.grid()
            self._set_active_workbench("Scene", set_status=False)

    def _on_sidebar_mousewheel(self, event: object) -> None:
        delta = getattr(event, "delta", 0)
        if delta and getattr(self, "sidebar_scrollbar", None) is not None and self.sidebar_scrollbar.winfo_ismapped():
            self.sidebar_canvas.yview_scroll(int(-1 * (delta / 120)), "units")

    def _bind_keyboard_shortcuts(self) -> None:
        self.root.bind_all("<KeyPress>", self._on_tk_keypress)

    def _on_tk_keypress(self, event: object) -> None:
        focused = self.root.focus_get()
        if isinstance(focused, (ttk.Entry, ttk.Combobox)):
            return

        shortcut = shortcut_from_tk_event(event)
        if shortcut is None:
            return

        if self._manual_curve_active and shortcut in {"Backspace", "C", "Enter", "Esc"}:
            self._handle_shortcut(shortcut)
            return

        action = action_for_shortcut(self.settings.keybinds, shortcut)
        if action is not None:
            self._handle_keybind_action(action)
            return

        if shortcut in {"X", "Y", "Z", "N"}:
            self._handle_shortcut(shortcut)

    def open_model(self) -> None:
        if self._is_loading_model:
            return

        selected_path = filedialog.askopenfilename(
            title="Open Model",
            filetypes=MESH_FILE_TYPES,
        )
        if not selected_path:
            return

        self.load_model(Path(selected_path))

    def load_model(self, file_path: Path, *, error_title: str = "Could not open model") -> bool:
        if self._is_loading_model:
            return False

        self._is_loading_model = True
        self._set_open_model_enabled(False)
        progress: LoadProgressDialog | None = None
        try:
            progress = LoadProgressDialog(self.root, file_path.name)
            try:
                self._set_load_progress_stage(progress, LOAD_PROGRESS_STAGES[0])
                loaded = load_mesh(file_path)

                self._set_load_progress_stage(progress, LOAD_PROGRESS_STAGES[1])
                bounds = loaded.mesh.get_axis_aligned_bounding_box()

                self._set_load_progress_stage(progress, LOAD_PROGRESS_STAGES[2])
                display_result = build_display_mesh(loaded.mesh, quality=self.proxy_quality.get())
            except (FileNotFoundError, ValueError, RuntimeError, SystemExit) as exc:
                self.status_text.set("No selection")
                progress.close()
                progress = None
                messagebox.showerror(error_title, str(exc))
                return False

            origin = np.asarray(bounds.get_center(), dtype=float)
            self.app_state.mesh_object = MeshObjectState(
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
                display_reduction_percent=display_result.reduction_percent,
                proxy_quality=display_result.quality,
                source_bounds_min=np.asarray(bounds.get_min_bound(), dtype=float),
                source_bounds_max=np.asarray(bounds.get_max_bound(), dtype=float),
            )
            self._clear_manual_curve_state()
            self._clear_region_selection_state()
            self.app_state.section_result = None
            self.app_state.section_collection.results = []
            self.app_state.section_collection.active_result_id = None
            self.app_state.curve_results = []
            self.app_state.curve_collection.curves = []
            self.app_state.curve_collection.active_curve_id = None
            self.app_state.curve_collection.selected_curve_ids.clear()
            self.app_state.surface_collection.surfaces = []
            self.app_state.surface_collection.active_surface_id = None
            self.app_state.surface_collection.selected_surface_ids.clear()
            self._ensure_default_section_plane()
            self._sync_active_section_plane_from_controls()
            self.section_result_text.set("Section result: none")
            self._set_load_progress_stage(progress, LOAD_PROGRESS_STAGES[3])
            self._set_transform_inputs_from_object()
            self._apply_object_transform(reset_camera=False)
            self._configure_offset_range(reset=True)
            self._update_section_plane_label(set_status=False)
            self._set_selection_buttons_enabled(True)
            self._set_load_progress_stage(progress, LOAD_PROGRESS_STAGES[4])
            self._set_selected_item(None, status="No selection")
            self._refresh_viewport(reset_camera=True)
            self._clear_undo_stack()
            self.status_text.set(self._display_mesh_status(display_result))
            self._set_project_dirty(True)
            return True
        finally:
            if progress is not None:
                progress.close()
            self._is_loading_model = False
            self._set_open_model_enabled(True)

    def _set_open_model_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for name in ("open_model_button", "empty_open_model_button"):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.configure(state=state)
        if hasattr(self, "file_menu"):
            self.file_menu.entryconfigure(OPEN_MODEL_MENU_INDEX, state=state)

    def _set_load_progress_stage(
        self,
        progress: LoadProgressDialog,
        stage: str,
    ) -> None:
        self._set_progress_stage(progress, stage)

    def _set_progress_stage(
        self,
        progress: StageProgressDialog,
        stage: str,
    ) -> None:
        self.status_text.set(stage)
        progress.update_stage(stage)

    def select_model(self) -> None:
        if self.app_state.mesh_object is None:
            self._set_selected_item(None, status="No selection")
            return

        self._set_selected_item(SELECT_MODEL, status=f"Selected: {self.app_state.mesh_object.name}")

    def select_section_plane(self, plane_id: str | None = None) -> None:
        if self.app_state.mesh_object is None:
            self._set_selected_item(None, status="No selection")
            return

        if plane_id is not None:
            try:
                set_active_plane(self.app_state.section_collection, plane_id)
            except ValueError:
                self._refresh_scene_browser()
                self.status_text.set("Section plane not found")
                return
        else:
            active_plane = get_active_plane(self.app_state.section_collection)
            if active_plane is None:
                self._set_selected_item(None, status="No selection")
                return
            set_active_plane(self.app_state.section_collection, active_plane.id)

        self._sync_section_controls_from_active_plane()
        self._set_selected_item(SELECT_SECTION_PLANE, status="Selected: Section Plane")

    def select_section_planes(
        self,
        plane_ids: list[str],
        *,
        active_plane_id: str | None = None,
    ) -> None:
        if self.app_state.mesh_object is None:
            self._set_selected_item(None, status="No selection")
            return
        if not plane_ids:
            self.status_text.set("No section planes available")
            return

        try:
            set_selected_planes(
                self.app_state.section_collection,
                plane_ids,
                active_plane_id=active_plane_id,
            )
        except ValueError:
            self._refresh_scene_browser()
            self.status_text.set("Section plane not found")
            return

        self._sync_section_controls_from_active_plane()
        count = len(self.app_state.section_collection.selected_plane_ids)
        status = "Selected: Section Plane" if count == 1 else f"Selected: {count} section planes"
        self._set_selected_item(SELECT_SECTION_PLANE, status=status)

    def select_section_result(self, result_id: str | None = None) -> None:
        if self.app_state.mesh_object is None:
            self._set_selected_item(None, status="No selection")
            return

        if result_id is not None:
            try:
                set_active_result(self.app_state.section_collection, result_id)
            except ValueError:
                self._refresh_scene_browser()
                self.status_text.set("Section result not found")
                return

        active_result = self._active_section_result()
        if active_result is None:
            self._set_selected_item(None, status="No selection")
            return

        self._set_display_section_result(active_result)
        child_curve_ids = [
            curve.id
            for curve in self.app_state.curve_collection.curves
            if curve.section_result_id == active_result.id
        ]
        if child_curve_ids:
            set_selected_curves(
                self.app_state.curve_collection,
                child_curve_ids,
                active_curve_id=child_curve_ids[0],
            )
        else:
            clear_curve_selection(self.app_state.curve_collection)
        self._sync_section_result_context_from_active_result()
        self._set_selected_item(
            SELECT_SECTION_RESULT,
            status=f"Selected: {active_result.name}",
            preserve_curve_selection=True,
        )

    def select_section_results(
        self,
        result_ids: list[str],
        *,
        active_result_id: str | None = None,
    ) -> None:
        if self.app_state.mesh_object is None:
            self._set_selected_item(None, status="No selection")
            return
        if not result_ids:
            self.status_text.set("No section results available")
            return

        try:
            set_selected_results(
                self.app_state.section_collection,
                result_ids,
                active_result_id=active_result_id,
            )
        except ValueError:
            self._refresh_scene_browser()
            self.status_text.set("Section result not found")
            return

        active_result = self._active_section_result()
        self.app_state.section_result = (
            active_result.result
            if active_result is not None and active_result.visible
            else None
        )
        if active_result is not None:
            self.section_result_text.set(self._section_result_summary(active_result))
        else:
            self.section_result_text.set("Section result: none")
        self._sync_visible_curve_results()
        child_curve_ids = [
            curve.id
            for curve in self.app_state.curve_collection.curves
            if curve.section_result_id in self.app_state.section_collection.selected_result_ids
        ]
        if child_curve_ids:
            set_selected_curves(
                self.app_state.curve_collection,
                child_curve_ids,
                active_curve_id=child_curve_ids[0],
            )
        else:
            clear_curve_selection(self.app_state.curve_collection)
        self._sync_section_result_context_from_active_result()
        count = len(self.app_state.section_collection.selected_result_ids)
        status = "Selected: Section Result" if count == 1 else f"Selected: {count} section results"
        self._set_selected_item(
            SELECT_SECTION_RESULT,
            status=status,
            preserve_curve_selection=True,
        )

    def select_curve(self, curve_id: str | None = None) -> None:
        if self.app_state.mesh_object is None:
            self._set_selected_item(None, status="No selection")
            return

        if curve_id is not None:
            try:
                set_active_curve(self.app_state.curve_collection, curve_id)
            except ValueError:
                self._refresh_scene_browser()
                self.status_text.set("Curve not found")
                return

        active_curve = self._active_curve()
        if active_curve is None:
            self._set_selected_item(None, status="No selection")
            return

        self._sync_curve_context_from_active_curve()
        self._set_selected_item(SELECT_CURVE, status=f"Selected: {active_curve.name}")

    def select_curves(
        self,
        curve_ids: list[str],
        *,
        active_curve_id: str | None = None,
    ) -> None:
        if self.app_state.mesh_object is None:
            self._set_selected_item(None, status="No selection")
            return

        if not curve_ids:
            self._set_selected_item(None, status="No selection")
            return

        try:
            set_selected_curves(
                self.app_state.curve_collection,
                curve_ids,
                active_curve_id=active_curve_id,
            )
        except ValueError:
            self._refresh_scene_browser()
            self.status_text.set("Curve not found")
            return

        active_curve = self._active_curve()
        if active_curve is None:
            self._set_selected_item(None, status="No selection")
            return

        self._sync_curve_context_from_active_curve()
        selected_count = len(self.app_state.curve_collection.selected_curve_ids)
        status = (
            f"Selected: {active_curve.name}"
            if selected_count == 1
            else f"Selected: {selected_count} curves"
        )
        self._set_selected_item(SELECT_CURVE, status=status)

    def select_surface(self, surface_id: str | None = None) -> None:
        if self.app_state.mesh_object is None:
            self._set_selected_item(None, status="No selection")
            return

        if surface_id is not None:
            try:
                set_active_surface(self.app_state.surface_collection, surface_id)
            except ValueError:
                self._refresh_scene_browser()
                self.status_text.set("Surface not found")
                return

        active_surface = self._active_surface()
        if active_surface is None:
            self._set_selected_item(None, status="No selection")
            return

        self._sync_surface_context_from_active_surface()
        self._set_selected_item(SELECT_SURFACE, status=f"Selected: {active_surface.name}")

    def select_region(self, region_id: str | None = None) -> None:
        if self.app_state.mesh_object is None:
            self._set_selected_item(None, status="No selection")
            return

        region = self.app_state.region_collection.active_region
        if region is None:
            self._set_selected_item(None, status="No selection")
            return
        if region_id is not None and region.id != region_id:
            self._refresh_scene_browser()
            self.status_text.set("Region not found")
            return

        region.selected = True
        self._set_selected_item(SELECT_REGION, status=f"Selected: {region.name or 'Region 1'}")
        self._sync_region_panel()

    def select_surfaces(
        self,
        surface_ids: list[str],
        *,
        active_surface_id: str | None = None,
    ) -> None:
        if self.app_state.mesh_object is None:
            self._set_selected_item(None, status="No selection")
            return
        if not surface_ids:
            self.status_text.set("No surfaces available")
            return

        try:
            set_selected_surfaces(
                self.app_state.surface_collection,
                surface_ids,
                active_surface_id=active_surface_id,
            )
        except ValueError:
            self._refresh_scene_browser()
            self.status_text.set("Surface not found")
            return

        active_surface = self._active_surface()
        if active_surface is None:
            self._set_selected_item(None, status="No selection")
            return

        self._sync_surface_context_from_active_surface()
        count = len(self.app_state.surface_collection.selected_surface_ids)
        status = (
            f"Selected: {active_surface.name}"
            if count == 1
            else f"Selected: {count} surfaces"
        )
        self._set_selected_item(SELECT_SURFACE, status=status)

    def select_source_curves_for_active_surface(
        self,
        node_ids: tuple[str, ...] = (),
    ) -> None:
        surface = self._surface_for_source_curve_selection(node_ids)
        if surface is None:
            self.status_text.set("Select a surface first.")
            return

        source_curves, missing_curve_ids = self._source_curves_for_surface(surface)
        source_curve_ids = [curve.id for curve in source_curves]
        if not source_curve_ids:
            self.status_text.set(self._source_curve_missing_status(surface, missing_curve_ids))
            return

        self.select_curves(source_curve_ids, active_curve_id=source_curve_ids[0])
        self.status_text.set(
            f"Selected source curves for {surface.name}"
            f"{self._missing_source_curve_suffix(missing_curve_ids)}"
        )

    def isolate_source_curves_for_active_surface(
        self,
        node_ids: tuple[str, ...] = (),
    ) -> None:
        surface = self._surface_for_source_curve_selection(node_ids)
        if surface is None:
            self.status_text.set("Select a surface first.")
            return

        source_curves, missing_curve_ids = self._source_curves_for_surface(surface)
        if not source_curves:
            self.status_text.set(self._source_curve_missing_status(surface, missing_curve_ids))
            return

        source_curve_ids = {curve.id for curve in source_curves}
        node_id_set = {
            curve_node_id(curve.id)
            for curve in self.app_state.curve_collection.curves
        }
        before = self._visibility_snapshot(node_id_set)
        for curve in self.app_state.curve_collection.curves:
            curve.visible = curve.id in source_curve_ids
        after = self._visibility_snapshot(node_id_set)
        self._push_visibility_command("Isolate Source Curves", before, after)
        self._sync_after_scene_visibility_change()
        self.status_text.set(
            f"Isolated source curves for {surface.name}"
            f"{self._missing_source_curve_suffix(missing_curve_ids)}"
        )
        self._set_project_dirty(True)

    def show_source_curves_for_active_surface(
        self,
        node_ids: tuple[str, ...] = (),
    ) -> None:
        surface = self._surface_for_source_curve_selection(node_ids)
        if surface is None:
            self.status_text.set("Select a surface first.")
            return

        source_curves, missing_curve_ids = self._source_curves_for_surface(surface)
        if not source_curves:
            self.status_text.set(self._source_curve_missing_status(surface, missing_curve_ids))
            return

        node_id_set = {curve_node_id(curve.id) for curve in source_curves}
        before = self._visibility_snapshot(node_id_set)
        for curve in source_curves:
            curve.visible = True
        after = self._visibility_snapshot(node_id_set)
        self._push_visibility_command("Show Source Curves", before, after)
        self._sync_after_scene_visibility_change()
        self.status_text.set(
            f"Shown source curves for {surface.name}"
            f"{self._missing_source_curve_suffix(missing_curve_ids)}"
        )
        if before != after:
            self._set_project_dirty(True)

    def frame_source_curves_for_active_surface(
        self,
        node_ids: tuple[str, ...] = (),
    ) -> None:
        surface = self._surface_for_source_curve_selection(node_ids)
        if surface is None:
            self.status_text.set("Select a surface first.")
            return

        source_curves, missing_curve_ids = self._source_curves_for_surface(surface)
        if not source_curves:
            self.status_text.set(self._source_curve_missing_status(surface, missing_curve_ids))
            return

        bounds = self._bounds_for_node_ids(
            {curve_node_id(curve.id) for curve in source_curves}
        )
        if bounds is None:
            self.status_text.set(self._source_curve_missing_status(surface, missing_curve_ids))
            return

        minimum_bound, maximum_bound = bounds
        if hasattr(self.viewport, "frame_bounds"):
            self.viewport.frame_bounds(minimum_bound, maximum_bound)
        else:
            self.viewport.frame_model()
        self.status_text.set(
            f"Framed source curves for {surface.name}"
            f"{self._missing_source_curve_suffix(missing_curve_ids)}"
        )

    def _surface_for_source_curve_selection(
        self,
        node_ids: tuple[str, ...],
    ) -> SurfacePatch | None:
        surface_by_id = {
            surface.id: surface
            for surface in self.app_state.surface_collection.surfaces
        }
        selected_surface_ids = {
            surface_id
            for surface_id in (surface_id_from_node(node_id) for node_id in node_ids)
            if surface_id is not None
        }
        if len(selected_surface_ids) == 1:
            return surface_by_id.get(next(iter(selected_surface_ids)))
        if len(selected_surface_ids) > 1:
            return None

        for node_id in node_ids:
            surface_id = surface_id_from_node(node_id)
            if surface_id is not None and surface_id in surface_by_id:
                return surface_by_id[surface_id]

        active_surface = self._active_surface()
        if (
            self.app_state.selected_item == SELECT_SURFACE
            and active_surface is not None
            and self.app_state.surface_collection.selected_surface_ids == {active_surface.id}
        ):
            return active_surface
        return None

    def _source_curves_for_surface(
        self,
        surface: SurfacePatch,
    ) -> tuple[list[StoredCurve], list[str]]:
        curve_by_id = {
            curve.id: curve
            for curve in self.app_state.curve_collection.curves
        }
        source_curves: list[StoredCurve] = []
        missing_curve_ids: list[str] = []
        seen_curve_ids: set[str] = set()
        for curve_id in surface.source_curve_ids:
            curve_id = str(curve_id)
            if curve_id in seen_curve_ids:
                continue
            seen_curve_ids.add(curve_id)
            curve = curve_by_id.get(curve_id)
            if curve is None:
                missing_curve_ids.append(curve_id)
                continue
            source_curves.append(curve)
        return source_curves, missing_curve_ids

    @staticmethod
    def _missing_source_curve_suffix(missing_curve_ids: list[str]) -> str:
        missing_count = len(missing_curve_ids)
        if missing_count == 0:
            return ""
        noun = "curve" if missing_count == 1 else "curves"
        return f" ({missing_count} missing source {noun})"

    def _source_curve_missing_status(
        self,
        surface: SurfacePatch,
        missing_curve_ids: list[str],
    ) -> str:
        suffix = self._missing_source_curve_suffix(missing_curve_ids)
        return f"No source curves found for {surface.name}{suffix}"

    def add_section_plane(self) -> None:
        if self.app_state.mesh_object is None:
            self._set_selected_item(None, status="No selection")
            return

        plane = create_default_section_plane(
            axis=self.section_axis.get(),
            offset=self.section_offset.get(),
        )
        plane.name = self._next_section_plane_name()
        plane.visible = bool(self.show_section_plane.get())
        add_plane(self.app_state.section_collection, plane)
        set_active_plane(self.app_state.section_collection, plane.id)
        self._sync_section_controls_from_active_plane()
        self._set_selected_item(SELECT_SECTION_PLANE, status=f"Added: {plane.name}")
        self._set_project_dirty(True)

    def _next_section_plane_name(self) -> str:
        existing_names = {
            plane.name for plane in self.app_state.section_collection.planes
        }
        index = 1
        while f"Section Plane {index}" in existing_names:
            index += 1
        return f"Section Plane {index}"

    def clear_selection(self) -> None:
        self._set_selected_item(None, status="No selection")

    def _set_selected_item(
        self,
        selected_item: str | None,
        *,
        status: str | None = None,
        preserve_curve_selection: bool = False,
    ) -> None:
        if self.app_state.transform_state is not None:
            self._end_active_transform(commit=False, status="Transform cancelled")
        if self._manual_curve_active:
            self._clear_manual_curve_state()
        if self._region_select_active:
            self._exit_region_select_mode()

        keep_selection_families: set[str] = set()
        if selected_item == SELECT_SECTION_PLANE:
            keep_selection_families.add("section_planes")
        if selected_item == SELECT_SECTION_RESULT:
            keep_selection_families.add("section_results")
        if selected_item == SELECT_CURVE or preserve_curve_selection:
            keep_selection_families.add("curves")
        if selected_item == SELECT_SURFACE:
            keep_selection_families.add("surfaces")
        if selected_item == SELECT_REGION:
            keep_selection_families.add("regions")
        self._clear_selection_families(keep=keep_selection_families)
        self.app_state.selected_item = selected_item
        self.app_state.active_transform_mode = None
        self.app_state.active_transform_axis = None
        self.app_state.transform_state = None
        self._active_transform_angle_delta = None
        self._show_context(selected_item)
        self._refresh_viewport(reset_camera=False)
        if status is not None:
            self.status_text.set(status)

    def _clear_selection_families(self, *, keep: set[str]) -> None:
        if "section_planes" not in keep:
            clear_plane_selection(self.app_state.section_collection)
        if "section_results" not in keep:
            clear_result_selection(self.app_state.section_collection)
        if "curves" not in keep:
            clear_curve_selection(self.app_state.curve_collection)
        if "surfaces" not in keep:
            clear_surface_selection(self.app_state.surface_collection)
        if "regions" not in keep:
            active_region = self.app_state.region_collection.active_region
            if active_region is not None:
                active_region.selected = False

    def _on_viewport_selection(self, selected_item: str | None) -> None:
        if self._region_select_active:
            return
        if selected_item == SELECT_MODEL:
            self.select_model()
        elif selected_item == SELECT_SECTION_PLANE:
            self.select_section_plane()
        else:
            self.clear_selection()

    def _on_scene_browser_selection(
        self,
        selected_item: str | None,
        selected_items: tuple[str, ...] = (),
    ) -> None:
        selected_node_ids = tuple(selected_items or (() if selected_item is None else (selected_item,)))
        section_plane_id = section_plane_id_from_node(selected_item)
        section_result_id = section_result_id_from_node(selected_item)
        curve_group_id = curve_group_id_from_node(selected_item)
        curve_id = curve_id_from_node(selected_item)
        surface_id = surface_id_from_node(selected_item)
        region_id = region_id_from_node(selected_item)
        selected_plane_ids = [
            selected_plane_id
            for selected_plane_id in (
                section_plane_id_from_node(item) for item in selected_node_ids
            )
            if selected_plane_id is not None
        ]
        selected_result_ids = [
            selected_result_id
            for selected_result_id in (
                section_result_id_from_node(item) for item in selected_node_ids
            )
            if selected_result_id is not None
        ]
        selected_curve_ids = [
            selected_curve_id
            for selected_curve_id in (
                curve_id_from_node(item) for item in selected_node_ids
            )
            if selected_curve_id is not None
        ]
        selected_surface_ids = [
            selected_surface_id
            for selected_surface_id in (
                surface_id_from_node(item) for item in selected_node_ids
            )
            if selected_surface_id is not None
        ]
        selected_region_ids = [
            selected_region_id
            for selected_region_id in (
                region_id_from_node(item) for item in selected_node_ids
            )
            if selected_region_id is not None
        ]
        if selected_item == SELECT_MODEL:
            self.select_model()
        elif selected_item == NODE_REGIONS:
            region = self.app_state.region_collection.active_region
            if region is not None:
                self.select_region(region.id)
            else:
                self.status_text.set("No region selection")
        elif selected_item == NODE_CURVES:
            curve_ids = [curve.id for curve in self.app_state.curve_collection.curves]
            if curve_ids:
                self.select_curves(curve_ids, active_curve_id=curve_ids[0])
            else:
                self.status_text.set("No curves available")
        elif selected_item == NODE_SURFACES:
            surface_ids = [surface.id for surface in self.app_state.surface_collection.surfaces]
            if surface_ids:
                self.select_surfaces(surface_ids, active_surface_id=surface_ids[0])
            else:
                self.status_text.set("No surfaces available")
        elif selected_item == NODE_SECTION_PLANES:
            plane_ids = [plane.id for plane in self.app_state.section_collection.planes]
            if plane_ids:
                self.select_section_planes(plane_ids, active_plane_id=plane_ids[0])
            else:
                self.status_text.set("No section planes available")
        elif selected_item == NODE_SECTION_RESULTS:
            result_ids = [result.id for result in self.app_state.section_collection.results]
            if result_ids:
                self.select_section_results(result_ids, active_result_id=result_ids[0])
            else:
                self.status_text.set("No section results available")
        elif selected_plane_ids and len(selected_plane_ids) == len(selected_node_ids):
            active_id = section_plane_id if section_plane_id in selected_plane_ids else selected_plane_ids[0]
            self.select_section_planes(selected_plane_ids, active_plane_id=active_id)
        elif selected_result_ids and len(selected_result_ids) == len(selected_node_ids):
            active_id = section_result_id if section_result_id in selected_result_ids else selected_result_ids[0]
            self.select_section_results(selected_result_ids, active_result_id=active_id)
        elif selected_surface_ids and len(selected_surface_ids) == len(selected_node_ids):
            active_id = surface_id if surface_id in selected_surface_ids else selected_surface_ids[0]
            self.select_surfaces(selected_surface_ids, active_surface_id=active_id)
        elif selected_region_ids and len(selected_region_ids) == len(selected_node_ids):
            active_id = region_id if region_id in selected_region_ids else selected_region_ids[0]
            self.select_region(active_id)
        elif selected_curve_ids and len(selected_curve_ids) == len(selected_node_ids):
            active_id = curve_id if curve_id in selected_curve_ids else selected_curve_ids[0]
            self.select_curves(selected_curve_ids, active_curve_id=active_id)
        elif len(selected_node_ids) > 1:
            self.status_text.set("Mixed selection is not supported yet.")
        elif section_plane_id is not None:
            self.select_section_plane(section_plane_id)
        elif section_result_id is not None:
            self.select_section_result(section_result_id)
        elif curve_group_id is not None:
            curve_ids = self._curve_ids_for_group(curve_group_id)
            if curve_ids:
                self.select_curves(curve_ids, active_curve_id=curve_ids[0])
            else:
                self.status_text.set("No curves in group")
        elif curve_id is not None:
            self.select_curves([curve_id], active_curve_id=curve_id)
        elif surface_id is not None:
            self.select_surface(surface_id)
        elif region_id is not None:
            self.select_region(region_id)
        elif selected_item == SELECT_SECTION_PLANE:
            self.select_section_plane()
        elif selected_item == SELECT_SECTION_RESULT:
            self.select_section_result()
        elif selected_item == SELECT_CURVE:
            self.select_curve()
        elif selected_item == SELECT_SURFACE:
            self.select_surface()
        elif selected_item == SELECT_REGION:
            self.select_region()
        else:
            self.clear_selection()

    def _curve_ids_for_group(self, section_result_id: str) -> list[str]:
        result_ids = {
            result.id for result in self.app_state.section_collection.results
        }
        if section_result_id == CURVE_GROUP_REPAIRED_ID:
            return [
                curve.id
                for curve in self.app_state.curve_collection.curves
                if is_repaired_curve(curve)
            ]
        if section_result_id == CURVE_GROUP_PROJECTED_ID:
            return [
                curve.id
                for curve in self.app_state.curve_collection.curves
                if self._is_projected_curve(curve)
            ]
        if section_result_id == CURVE_GROUP_REBUILT_ID:
            return [
                curve.id
                for curve in self.app_state.curve_collection.curves
                if self._is_rebuilt_curve(curve)
            ]
        if section_result_id == CURVE_GROUP_REGION_BOUNDARIES_ID:
            return [
                curve.id
                for curve in self.app_state.curve_collection.curves
                if self._is_region_boundary_curve(curve)
            ]
        if section_result_id == CURVE_GROUP_MANUAL_ID:
            return [
                curve.id
                for curve in self.app_state.curve_collection.curves
                if self._is_manual_or_mesh_curve(curve)
            ]
        if section_result_id == "":
            return [
                curve.id
                for curve in self.app_state.curve_collection.curves
                if curve.section_result_id not in result_ids
                and not is_repaired_curve(curve)
                and not self._is_projected_curve(curve)
                and not self._is_rebuilt_curve(curve)
                and not self._is_region_boundary_curve(curve)
                and not self._is_manual_or_mesh_curve(curve)
            ]

        return [
            curve.id
            for curve in self.app_state.curve_collection.curves
            if curve.section_result_id == section_result_id
            and not self._is_projected_curve(curve)
            and not self._is_rebuilt_curve(curve)
            and not self._is_region_boundary_curve(curve)
            and not self._is_manual_or_mesh_curve(curve)
        ]

    @staticmethod
    def _is_manual_or_mesh_curve(curve: StoredCurve) -> bool:
        return is_manual_curve_like(curve)

    @staticmethod
    def _is_projected_curve(curve: StoredCurve) -> bool:
        metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
        return str(metadata.get("creation_type", "")).strip().lower() == "projected_curve"

    @staticmethod
    def _is_rebuilt_curve(curve: StoredCurve) -> bool:
        metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
        return str(metadata.get("creation_type", "")).strip().lower() == "rebuilt_curve"

    @staticmethod
    def _is_region_boundary_curve(curve: StoredCurve) -> bool:
        metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
        return (
            str(metadata.get("creation_type", "")).strip().lower() == "region_boundary"
            or "source_region_id" in metadata
        )

    def _on_viewport_pointer_event(
        self,
        event_type: str,
        x_position: int,
        y_position: int,
        shift_pressed: bool = False,
        ctrl_pressed: bool = False,
    ) -> bool:
        self._last_viewport_mouse = (int(x_position), int(y_position))
        if self._manual_curve_active:
            return self._handle_manual_curve_pointer_event(
                event_type,
                int(x_position),
                int(y_position),
                shift_pressed=shift_pressed,
                ctrl_pressed=ctrl_pressed,
            )

        if self._region_select_active:
            return self._handle_region_select_pointer_event(
                event_type,
                int(x_position),
                int(y_position),
            )

        if self.app_state.transform_state is None:
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

    def start_region_select_mode(self) -> None:
        if self.app_state.mesh_object is None:
            self.status_text.set("Region selection requires a loaded mesh.")
            self._sync_workflow_ui()
            return

        if self.app_state.transform_state is not None:
            self._end_active_transform(commit=False, status="Transform cancelled")
        if self._manual_curve_active:
            self._clear_manual_curve_state()
        self.app_state.active_transform_mode = None
        self.app_state.active_transform_axis = None
        self._active_transform_angle_delta = None
        self._region_select_active = True
        self._region_select_left_press_position = None
        self._region_select_left_dragged = False
        self._region_select_last_hit_triangle_index = None
        self._set_active_workbench("Manual RE", set_status=False)
        self._refresh_viewport(reset_camera=False)
        self.status_text.set("Region Select: click a mesh area.")
        self._sync_workflow_ui()

    def configure_region_threshold(self) -> None:
        value = simpledialog.askfloat(
            "Region Threshold",
            "Normal angle threshold in degrees",
            parent=self.root,
            initialvalue=self._region_threshold_value(),
            minvalue=0.0,
            maxvalue=90.0,
        )
        if value is None:
            self.status_text.set("Region threshold unchanged")
            return

        self._set_region_threshold_value(value, set_status=False)
        self.status_text.set(
            f"Region threshold: {self._region_threshold_value():.1f} degrees"
        )
        self._sync_workflow_ui()

    def configure_region_max_triangle_count(self) -> None:
        value = simpledialog.askinteger(
            "Region Max Triangles",
            "Maximum triangles selected by Region Select",
            parent=self.root,
            initialvalue=self._region_max_triangle_value(),
            minvalue=1,
            maxvalue=10_000_000,
        )
        if value is None:
            self.status_text.set("Region max triangles unchanged")
            return

        self._set_region_max_triangle_value(value, set_status=False)
        self.status_text.set(
            f"Region max triangles: {self._region_max_triangle_value():,}"
        )
        self._sync_workflow_ui()

    def clear_region_selection(self) -> None:
        had_region = self.app_state.region_collection.active_region is not None
        self.app_state.region_collection.clear()
        self._region_select_current_seed_triangle_index = None
        self._region_select_last_hit_triangle_index = None
        if self.app_state.selected_item == SELECT_REGION:
            self.app_state.selected_item = None
        self._refresh_viewport(reset_camera=False)
        self._refresh_scene_browser()
        self.status_text.set(
            "Region selection cleared." if had_region else "No region selection"
        )
        self._sync_workflow_ui()

    def hide_region_selection(self) -> None:
        region = self.app_state.region_collection.active_region
        if region is None:
            self.status_text.set("No region selection")
            self._sync_workflow_ui()
            return

        region.visible = False
        self._refresh_viewport(reset_camera=False)
        self._refresh_scene_browser()
        self.status_text.set("Region hidden.")
        self._sync_workflow_ui()

    def show_region_selection(self) -> None:
        region = self.app_state.region_collection.active_region
        if region is None:
            self.status_text.set("No region selection")
            self._sync_workflow_ui()
            return

        region.visible = True
        self._refresh_viewport(reset_camera=False)
        self._refresh_scene_browser()
        self.status_text.set("Region shown.")
        self._sync_workflow_ui()

    def delete_region_selection(self) -> None:
        had_region = self.app_state.region_collection.active_region is not None
        self.app_state.region_collection.clear()
        self._region_select_current_seed_triangle_index = None
        self._region_select_last_hit_triangle_index = None
        if self.app_state.selected_item == SELECT_REGION:
            self.app_state.selected_item = None
        self._refresh_viewport(reset_camera=False)
        self._refresh_scene_browser()
        self.status_text.set("Region deleted." if had_region else "No region selection")
        self._sync_workflow_ui()

    def frame_selected_region(self) -> None:
        region = self.app_state.region_collection.active_region
        mesh_object = self.app_state.mesh_object
        if region is None:
            self.status_text.set("No region selection")
            return

        bounds = None
        if mesh_object is not None:
            bounds = self._bounds_for_node_ids({region_node_id(region.id)})
        if bounds is None:
            if mesh_object is not None:
                self.viewport.frame_model()
                self.status_text.set("Region framing fallback: framed mesh.")
            else:
                self.status_text.set("Region geometry is unavailable")
            return

        minimum_bound, maximum_bound = bounds
        if hasattr(self.viewport, "frame_bounds"):
            self.viewport.frame_bounds(minimum_bound, maximum_bound)
        else:
            self.viewport.frame_model()
        self.status_text.set(f"Framed: {region.name or 'Region 1'}")

    def recompute_region_selection(self) -> None:
        active_region = self.app_state.region_collection.active_region
        mesh_object = self.app_state.mesh_object
        if active_region is None or mesh_object is None:
            self.status_text.set("No region selection")
            self._sync_workflow_ui()
            return

        seed_triangle_index = active_region.seed_triangle_index
        if seed_triangle_index is None:
            self.status_text.set("Active region has no seed triangle")
            self._sync_workflow_ui()
            return

        controls = self._validated_region_controls()
        if controls is None:
            self._sync_workflow_ui()
            return
        threshold_degrees, max_triangle_count = controls

        region = create_region_selection(
            mesh_object.display_mesh,
            seed_triangle_index,
            source_mesh_identifier=active_region.source_mesh_identifier
            or self._region_source_mesh_identifier(),
            source_mesh_name=active_region.source_mesh_name or mesh_object.name,
            threshold_degrees=threshold_degrees,
            max_triangle_count=max_triangle_count,
            name=active_region.name or "Region 1",
        )
        if region is None:
            self.status_text.set("Region Select: no region found")
            self._sync_workflow_ui()
            return

        region.id = active_region.id
        region.visible = bool(active_region.visible)
        region.selected = True
        self.app_state.region_collection.set_active(region)
        self._region_select_current_seed_triangle_index = seed_triangle_index
        self._region_select_last_hit_triangle_index = seed_triangle_index
        self._refresh_viewport(reset_camera=False)
        self._refresh_scene_browser()
        self.status_text.set(self._region_result_status("Recomputed region", region))
        self._sync_workflow_ui()

    def extract_region_boundary(self) -> None:
        mesh_object = self.app_state.mesh_object
        region = self.app_state.region_collection.active_region
        if mesh_object is None:
            self.status_text.set("Region boundary extraction requires a loaded mesh.")
            self._sync_workflow_ui()
            return
        if region is None:
            self.status_text.set("No active region to extract.")
            self._sync_workflow_ui()
            return

        boundary_mesh = mesh_object.display_mesh.copy()
        boundary_mesh.transform(self._current_object_matrix())
        boundaries = extract_region_boundary_polylines(boundary_mesh, region)
        if not boundaries:
            self.status_text.set("No boundary edges found.")
            self._sync_workflow_ui()
            return

        names = self._region_boundary_curve_names(len(boundaries))
        created_curves = [
            self._stored_curve_from_region_boundary(boundary, index, name)
            for index, (boundary, name) in enumerate(zip(boundaries, names), start=1)
        ]
        clear_curve_selection(self.app_state.curve_collection)
        for curve in created_curves:
            add_curve(self.app_state.curve_collection, curve)

        created_curve_ids = [curve.id for curve in created_curves]
        self._sync_visible_curve_results()
        self.select_curves(created_curve_ids, active_curve_id=created_curve_ids[0])
        self._push_created_curves_command(
            created_curves,
            command_name="Extract Region Boundary",
        )
        self._set_project_dirty(True)
        self.status_text.set(self._region_boundary_extraction_status(created_curves))
        self._sync_workflow_ui()

    def select_boundary_curves_for_active_region(self) -> None:
        region = self.app_state.region_collection.active_region
        if region is None:
            self.status_text.set("No active region to extract.")
            self._sync_workflow_ui()
            return

        curve_ids = [curve.id for curve in self._boundary_curves_for_region(region.id)]
        if not curve_ids:
            self.status_text.set("No boundary curves linked to active region.")
            self._sync_workflow_ui()
            return

        self.select_curves(curve_ids, active_curve_id=curve_ids[0])
        self.status_text.set(
            "Selected 1 boundary curve."
            if len(curve_ids) == 1
            else f"Selected {len(curve_ids)} boundary curves."
        )
        self._sync_workflow_ui()

    def _boundary_curves_for_region(self, region_id: str) -> list[StoredCurve]:
        return [
            curve
            for curve in self.app_state.curve_collection.curves
            if self._is_region_boundary_curve(curve)
            and str(
                (curve.metadata if isinstance(curve.metadata, dict) else {}).get(
                    "source_region_id",
                    "",
                )
            )
            == region_id
        ]

    def _stored_curve_from_region_boundary(
        self,
        boundary: RegionBoundaryPolyline,
        index: int,
        name: str,
    ) -> StoredCurve:
        region = self.app_state.region_collection.active_region
        region_name = "" if region is None else region.name
        points = np.asarray(boundary.points, dtype=float).reshape((-1, 3))
        curve = build_manual_stored_curve(
            curve_id=f"curve-{uuid4().hex}",
            name=name,
            control_points=points,
            is_closed=bool(boundary.is_closed),
            creation_type="region_boundary",
            snap_to_mesh=False,
            work_plane_type="mesh",
            source_mesh_name=boundary.source_mesh_name,
            curve_method="polyline",
            sample_count=max(len(points), 2),
        )
        metadata = dict(curve.metadata)
        metadata.update(boundary.metadata)
        metadata.update(
            {
                "creation_type": "region_boundary",
                "source_region_id": boundary.source_region_id,
                "source_region_name": region_name,
                "source_mesh_name": boundary.source_mesh_name,
                "curve_method": "polyline",
                "boundary_point_count": int(len(points)),
                "boundary_closed": bool(boundary.is_closed),
                "boundary_perimeter": _polyline_perimeter(
                    points,
                    closed=bool(boundary.is_closed),
                ),
                "region_triangle_count": 0
                if region is None
                else len(region.triangle_indices),
                "source_region_triangle_count": 0
                if region is None
                else len(region.triangle_indices),
                "boundary_index": int(index),
            }
        )
        curve.metadata = metadata
        curve.original_points = points.copy()
        curve.fitted_points = points.copy()
        curve.is_closed = bool(boundary.is_closed)
        refresh_curve_diagnostics(curve)
        return curve

    def _region_boundary_curve_names(self, count: int) -> list[str]:
        existing_names = {curve.name for curve in self.app_state.curve_collection.curves}
        names: list[str] = []
        index = 1
        while len(names) < count:
            candidate = f"Region Boundary {index}"
            index += 1
            if candidate in existing_names:
                continue
            existing_names.add(candidate)
            names.append(candidate)
        return names

    @staticmethod
    def _region_boundary_extraction_status(curves: Sequence[StoredCurve]) -> str:
        count = len(curves)
        if count == 1:
            shape = "closed" if bool(curves[0].is_closed) else "open"
            return f"Extracted 1 {shape} boundary curve."
        return f"Extracted {count} boundary curves."

    def hide_region_highlight(self) -> None:
        self.hide_region_selection()

    def show_region_highlight(self) -> None:
        self.show_region_selection()

    def _on_region_name_changed(self, event: object | None = None) -> None:
        region = self.app_state.region_collection.active_region
        if region is None:
            return

        candidate = self._validated_name_candidate(
            self.region_name_text,
            region.name or "Region 1",
            self.region_name_entry,
            event,
        )
        if candidate is None or candidate == region.name:
            return

        old_name = region.name
        region.name = candidate
        self._push_rename_command(
            region_node_id(region.id),
            "Rename Region",
            old_name,
            candidate,
        )
        self._refresh_scene_browser()
        self.status_text.set(f"Selected: {region.name}")

    def _select_region_at_screen_point(self, x_position: int, y_position: int) -> None:
        mesh_object = self.app_state.mesh_object
        if mesh_object is None:
            self.status_text.set("No selection")
            self._sync_workflow_ui()
            return

        controls = self._validated_region_controls()
        if controls is None:
            self._sync_workflow_ui()
            return
        threshold_degrees, max_triangle_count = controls

        pick_result = self.viewport.pick_mesh_at_screen_point(int(x_position), int(y_position))
        if not bool(getattr(pick_result, "hit", False)):
            self.status_text.set("No mesh under cursor.")
            self._sync_workflow_ui()
            return

        triangle_index = getattr(pick_result, "triangle_index", None)
        seed_triangle_index = self._valid_region_seed_triangle_index(
            mesh_object.display_mesh,
            triangle_index,
        )
        if seed_triangle_index is None:
            self.status_text.set("No mesh under cursor.")
            self._sync_workflow_ui()
            return
        self._region_select_last_hit_triangle_index = seed_triangle_index

        active_region = self.app_state.region_collection.active_region
        name = active_region.name if active_region is not None and active_region.name else "Region 1"

        region = create_region_selection(
            mesh_object.display_mesh,
            seed_triangle_index,
            source_mesh_identifier=self._region_source_mesh_identifier(),
            source_mesh_name=mesh_object.name,
            threshold_degrees=threshold_degrees,
            max_triangle_count=max_triangle_count,
            name=name,
        )
        if region is None:
            self.status_text.set("Region Select: no region found")
            self._sync_workflow_ui()
            return

        region.visible = True
        region.selected = True
        self.app_state.region_collection.set_active(region)
        self._region_select_current_seed_triangle_index = seed_triangle_index
        self.app_state.selected_item = SELECT_REGION
        self._clear_selection_families(keep={"regions"})
        self._show_context(SELECT_REGION)
        self._refresh_viewport(reset_camera=False)
        self._refresh_scene_browser()
        self.status_text.set(self._region_result_status("Selected region", region))
        self._sync_workflow_ui()

    def _handle_region_select_pointer_event(
        self,
        event_type: str,
        x_position: int,
        y_position: int,
    ) -> bool:
        if event_type == "left_press":
            self._region_select_left_press_position = (int(x_position), int(y_position))
            self._region_select_left_dragged = False
            return True

        if event_type == "motion":
            if self._region_select_left_press_position is None:
                return False
            self._update_region_select_drag_state(int(x_position), int(y_position))
            return True

        if event_type == "left_release":
            if not self._region_select_release_is_click(int(x_position), int(y_position)):
                self.status_text.set(self._region_select_status())
                self._sync_workflow_ui()
                return True
            self._select_region_at_screen_point(int(x_position), int(y_position))
            return True

        if event_type == "right_press":
            return True

        if event_type == "right_release":
            self._show_region_select_context_menu(int(x_position), int(y_position))
            return True

        if event_type == "leave":
            self._region_select_left_press_position = None
            self._region_select_left_dragged = False
            return False

        return False

    def _update_region_select_drag_state(self, x_position: int, y_position: int) -> None:
        if self._region_select_left_press_position is None:
            return
        start_x, start_y = self._region_select_left_press_position
        distance = abs(int(x_position) - start_x) + abs(int(y_position) - start_y)
        if distance > 4:
            self._region_select_left_dragged = True

    def _region_select_release_is_click(self, x_position: int, y_position: int) -> bool:
        if self._region_select_left_press_position is None:
            return False
        self._update_region_select_drag_state(x_position, y_position)
        is_click = not self._region_select_left_dragged
        self._region_select_left_press_position = None
        self._region_select_left_dragged = False
        return is_click

    def _show_region_select_context_menu(self, x_position: int, y_position: int) -> None:
        menu = self._build_region_select_context_menu()
        self._region_select_context_menu = menu
        try:
            root_x = int(self.root.winfo_pointerx())
            root_y = int(self.root.winfo_pointery())
        except TclError:
            root_x = int(x_position)
            root_y = int(y_position)
        try:
            menu.tk_popup(root_x, root_y)
        except TclError:
            return
        finally:
            try:
                menu.grab_release()
            except TclError:
                pass

    def _build_region_select_context_menu(self) -> Menu:
        menu = Menu(self.root, tearoff=False)
        menu.add_command(label="Clear Region", command=self.clear_region_selection)
        menu.add_command(label="Hide Region", command=self.hide_region_selection)
        menu.add_command(label="Show Region", command=self.show_region_selection)
        menu.add_command(label="Delete Region", command=self.delete_region_selection)
        menu.add_separator()
        menu.add_command(
            label="Cancel Region Select",
            command=lambda: self._exit_region_select_mode(status="Region Select cancelled"),
        )
        active_region = self.app_state.region_collection.active_region
        region_state = "normal" if active_region is not None else "disabled"
        for index in range(4):
            menu.entryconfigure(index, state=region_state)
        return menu

    def _active_visible_region_selection(self) -> RegionSelection | None:
        region = self.app_state.region_collection.active_region
        if region is None or not bool(region.visible):
            return None
        return region

    def _exit_region_select_mode(self, *, status: str | None = None) -> None:
        self._region_select_active = False
        self._region_select_left_press_position = None
        self._region_select_left_dragged = False
        self._region_select_current_seed_triangle_index = None
        self._region_select_last_hit_triangle_index = None
        if status is not None:
            self.status_text.set(status)
        self._sync_workflow_ui()

    def _clear_region_selection_state(self) -> None:
        self._region_select_active = False
        self._region_select_left_press_position = None
        self._region_select_left_dragged = False
        self._region_select_current_seed_triangle_index = None
        self._region_select_last_hit_triangle_index = None
        self.app_state.region_collection.clear()

    def _region_select_status(self) -> str:
        return "Region Select: click a mesh area."

    def _region_result_status(self, prefix: str, region: RegionSelection) -> str:
        triangle_count = len(region.triangle_indices)
        return (
            f"{prefix}: {triangle_count:,} "
            f"{_plural_label(triangle_count, 'triangle')} "
            f"at {float(region.threshold_degrees):.1f}\u00b0."
        )

    def _region_source_mesh_identifier(self) -> str:
        mesh_object = self.app_state.mesh_object
        if mesh_object is None:
            return ""
        if mesh_object.file_path is not None:
            return str(mesh_object.file_path)
        return mesh_object.name or str(id(mesh_object.display_mesh))

    def _region_threshold_value(self) -> float:
        try:
            raw_value = self.region_threshold_degrees.get()
        except (TclError, ValueError):
            raw_value = self._last_valid_region_threshold
        value = self._clamped_region_threshold(raw_value)
        if value != self._last_valid_region_threshold or value != raw_value:
            self._set_region_threshold_value(value, set_status=False)
        return value

    @staticmethod
    def _clamped_region_threshold(value: object) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return DEFAULT_REGION_THRESHOLD_DEGREES
        if not np.isfinite(number):
            return DEFAULT_REGION_THRESHOLD_DEGREES
        return min(max(number, 0.0), 90.0)

    def _region_max_triangle_value(self) -> int:
        value = self._parse_region_max_triangle_input(show_error=False)
        if value is None:
            value = self._last_valid_region_max_triangle_count
            self.region_max_triangle_count.set(str(value))
        return value

    def _set_region_threshold_value(self, value: object, *, set_status: bool) -> None:
        threshold = self._clamped_region_threshold(value)
        self._last_valid_region_threshold = threshold
        self.region_threshold_degrees.set(threshold)
        self.region_threshold_text.set(f"{threshold:.1f}")
        self.region_threshold_display_text.set(f"{threshold:.1f} deg")
        if set_status:
            self.status_text.set(self._region_control_status("Region threshold", f"{threshold:.1f} degrees"))

    def _set_region_max_triangle_value(self, value: object, *, set_status: bool) -> None:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = DEFAULT_REGION_MAX_TRIANGLES
        number = max(1, number)
        self._last_valid_region_max_triangle_count = number
        self.region_max_triangle_count.set(str(number))
        self.region_max_triangle_cap_text.set(f"{number:,}")
        if set_status:
            self.status_text.set(self._region_control_status("Region max triangles", f"{number:,}"))

    def _region_control_status(self, label: str, value: str) -> str:
        if self.app_state.region_collection.active_region is not None:
            return f"{label}: {value}. Use Recompute Region to update the active region."
        return f"{label}: {value}"

    def _on_region_threshold_slider_changed(self, value: object) -> None:
        self._set_region_threshold_value(value, set_status=True)
        self._sync_workflow_ui()

    def _on_region_threshold_entry_changed(self, _event: object | None = None) -> None:
        value = self._parse_region_threshold_input(show_error=True)
        if value is not None:
            self._set_region_threshold_value(value, set_status=True)
        self._sync_workflow_ui()

    def _on_region_max_triangle_entry_changed(self, _event: object | None = None) -> None:
        value = self._parse_region_max_triangle_input(show_error=True)
        if value is not None:
            self._set_region_max_triangle_value(value, set_status=True)
        self._sync_workflow_ui()

    def _validated_region_controls(self) -> tuple[float, int] | None:
        threshold = self._parse_region_threshold_input(show_error=True)
        if threshold is None:
            return None
        max_triangle_count = self._parse_region_max_triangle_input(show_error=True)
        if max_triangle_count is None:
            return None
        self._set_region_threshold_value(threshold, set_status=False)
        self._set_region_max_triangle_value(max_triangle_count, set_status=False)
        return (threshold, max_triangle_count)

    def _parse_region_threshold_input(self, *, show_error: bool) -> float | None:
        try:
            raw_value = self.region_threshold_text.get().strip()
        except TclError:
            raw_value = ""
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            value = float("nan")
        if not np.isfinite(value) or value < 0.0 or value > 90.0:
            self._set_region_threshold_value(self._last_valid_region_threshold, set_status=False)
            if show_error:
                self.status_text.set("Region threshold must be between 0 and 90 degrees.")
            return None
        return value

    def _parse_region_max_triangle_input(self, *, show_error: bool) -> int | None:
        try:
            raw_value = self.region_max_triangle_count.get().strip().replace(",", "")
        except TclError:
            raw_value = ""
        try:
            numeric_value = float(raw_value)
        except (TypeError, ValueError):
            numeric_value = float("nan")
        if (
            not np.isfinite(numeric_value)
            or numeric_value < 1.0
            or not numeric_value.is_integer()
        ):
            self.region_max_triangle_count.set(str(self._last_valid_region_max_triangle_count))
            if show_error:
                self.status_text.set("Max triangles must be a whole number >= 1.")
            return None
        return int(numeric_value)

    @staticmethod
    def _valid_region_seed_triangle_index(
        mesh: TriangleMeshData,
        triangle_index: object,
    ) -> int | None:
        try:
            seed_triangle_index = int(triangle_index)
        except (TypeError, ValueError):
            return None
        triangles = np.asarray(mesh.triangles, dtype=int).reshape((-1, 3))
        if seed_triangle_index < 0 or seed_triangle_index >= len(triangles):
            return None
        return seed_triangle_index

    def compute_section(self) -> None:
        if self.app_state.mesh_object is None:
            self.status_text.set("No selection")
            return

        offset = self._parse_offset()
        if offset is None:
            return
        active_plane = get_active_plane(self.app_state.section_collection)
        sync_plane_from_controls = (
            active_plane is not None
            and active_plane.axis == normalize_axis(self.section_axis.get())
            and np.allclose(
                plane_normal(active_plane),
                world_axis_vector(self.section_axis.get()),
                atol=1e-6,
            )
        )
        self._set_section_offset(
            offset,
            clamp=True,
            refresh=False,
            clear_section=False,
            sync_plane=sync_plane_from_controls,
        )

        active_plane = get_active_plane(self.app_state.section_collection)
        if active_plane is None:
            self.status_text.set("No section plane")
            return

        progress: ComputationProgressDialog | None = None
        try:
            progress = ComputationProgressDialog(
                self.root,
                "Computing Section",
                "Computing section geometry",
            )
            self._set_progress_stage(progress, COMPUTE_SECTION_PROGRESS_STAGES[0])
            section_mesh = self._transformed_source_mesh()
            self._set_progress_stage(progress, COMPUTE_SECTION_PROGRESS_STAGES[1])
            active_plane_origin = plane_origin(active_plane)
            active_plane_normal = plane_normal(active_plane)
            is_arbitrary_plane = not self._section_plane_is_axis_aligned(active_plane)
            if is_arbitrary_plane:
                section_result = extract_section_by_plane(
                    section_mesh,
                    active_plane_origin,
                    active_plane_normal,
                    axis=active_plane.axis,
                    offset=active_plane.offset,
                )
            else:
                section_result = extract_section(
                    section_mesh,
                    axis=active_plane.axis,
                    offset=active_plane.offset,
                )
            stored_result = StoredSectionResult(
                id=f"section-result-{uuid4().hex}",
                name=self._next_section_result_name(),
                plane_id=active_plane.id,
                axis=active_plane.axis,
                offset=active_plane.offset,
                result=section_result,
                plane_origin=active_plane_origin,
                plane_normal=active_plane_normal,
                is_arbitrary_plane=is_arbitrary_plane,
            )
            add_result(self.app_state.section_collection, stored_result)
            self._set_progress_stage(progress, COMPUTE_SECTION_PROGRESS_STAGES[2])
            self._store_curves_for_section_result(stored_result)
            self._set_display_section_result(stored_result)
            self._update_section_plane_label(set_status=False)
            self._set_progress_stage(progress, COMPUTE_SECTION_PROGRESS_STAGES[3])
            self._refresh_viewport(reset_camera=False)
            self.status_text.set(
                self._arbitrary_section_status(active_plane)
                if stored_result.is_arbitrary_plane
                else self._section_result_status(stored_result)
            )
        finally:
            if progress is not None:
                progress.close()

    def clear_section(self) -> None:
        self.clear_active_section_result()

    def clear_active_section_result(self) -> None:
        self._clear_active_section_results()
        self._refresh_viewport(reset_camera=False)
        self.status_text.set("Section cleared")

    def clear_all_section_results(self) -> None:
        self.app_state.section_collection.results = []
        self.app_state.section_collection.active_result_id = None
        self.app_state.curve_collection.curves = []
        self.app_state.curve_collection.active_curve_id = None
        self.app_state.curve_collection.selected_curve_ids.clear()
        self.app_state.surface_collection.surfaces = []
        self.app_state.surface_collection.active_surface_id = None
        self._set_display_section_result(None)
        self._refresh_viewport(reset_camera=False)
        self.status_text.set("All section results cleared")

    def delete_active_section_plane(self) -> None:
        if self.app_state.mesh_object is None:
            self.status_text.set("No selection")
            return

        active_plane = get_active_plane(self.app_state.section_collection)
        if active_plane is None:
            self._ensure_default_section_plane()
            self._sync_section_controls_from_active_plane()
            self._set_selected_item(SELECT_SECTION_PLANE, status="Selected: Section Plane")
            return

        removed_name = active_plane.name or "Section Plane"
        curve_ids = [
            curve.id
            for curve in self.app_state.curve_collection.curves
            if curve.plane_id == active_plane.id
        ]
        self._clear_surfaces_for_curve_ids(curve_ids)
        clear_curves_for_plane(self.app_state.curve_collection, active_plane.id)
        remove_plane(self.app_state.section_collection, active_plane.id)
        self._ensure_default_section_plane()
        self._set_display_section_result(self._latest_stored_section_result())
        self._sync_section_controls_from_active_plane()
        self._set_selected_item(SELECT_SECTION_PLANE, status=f"Deleted: {removed_name}")
        self._set_project_dirty(True)

    def _ensure_default_section_plane(self) -> None:
        if self.app_state.section_collection.planes:
            if self.app_state.section_collection.active_plane_id is None:
                set_active_plane(
                    self.app_state.section_collection,
                    self.app_state.section_collection.planes[0].id,
                )
            return

        add_plane(
            self.app_state.section_collection,
            create_default_section_plane(),
        )

    def _next_section_result_name(self) -> str:
        existing_names = {
            result.name for result in self.app_state.section_collection.results
        }
        index = 1
        prefix = "Section "
        for name in existing_names:
            if not name.startswith(prefix):
                continue

            suffix = name[len(prefix) :]
            if suffix.isdigit():
                index = max(index, int(suffix) + 1)

        while f"Section {index}" in existing_names:
            index += 1
        return f"Section {index}"

    def _latest_stored_section_result(self) -> StoredSectionResult | None:
        if not self.app_state.section_collection.results:
            return None

        return self.app_state.section_collection.results[-1]

    def _set_display_section_result(
        self,
        stored_result: StoredSectionResult | None,
    ) -> None:
        if stored_result is None:
            self.app_state.section_result = None
            self.app_state.section_collection.active_result_id = None
            self.section_result_text.set("Section result: none")
            self._sync_section_result_context_from_active_result()
            self._sync_visible_curve_results()
            return

        try:
            set_active_result(self.app_state.section_collection, stored_result.id)
        except ValueError:
            pass
        self.app_state.section_result = stored_result.result if stored_result.visible else None
        self.section_result_text.set(self._section_result_summary(stored_result))
        self._sync_section_result_context_from_active_result()
        self._sync_visible_curve_results()

    def _store_curves_for_section_result(
        self,
        stored_result: StoredSectionResult,
    ) -> None:
        for index, curve_fit in enumerate(
            fit_section_polylines(stored_result.result.polylines),
            start=1,
        ):
            add_curve(
                self.app_state.curve_collection,
                StoredCurve(
                    id=f"curve-{uuid4().hex}",
                    name=f"{stored_result.name} Curve {index}",
                    section_result_id=stored_result.id,
                    plane_id=stored_result.plane_id,
                    original_points=curve_fit.original_points,
                    fitted_points=curve_fit.fitted_points,
                    mean_error=curve_fit.mean_error,
                    max_error=curve_fit.max_error,
                    is_closed=curve_fit.is_closed,
                ),
            )

    def _sync_visible_curve_results(self) -> None:
        for curve in self.app_state.curve_collection.curves:
            refresh_curve_diagnostics(curve)
        self.app_state.curve_results = list(
            get_visible_curves(self.app_state.curve_collection)
        )

    def _active_section_result(self) -> StoredSectionResult | None:
        return get_active_result(self.app_state.section_collection)

    def _sync_section_result_context_from_active_result(self) -> None:
        active_result = self._active_section_result()
        if active_result is None:
            self.section_result_visible.set(False)
            self.section_result_name_text.set("(none)")
            self.section_result_source_plane_text.set("(none)")
            self.section_result_axis_text.set("(none)")
            self.section_result_offset_text.set("0.000")
            self.section_result_segment_count_text.set("0")
            self.section_result_curve_count_text.set("0")
            return

        self.section_result_visible.set(bool(active_result.visible))
        self.section_result_name_text.set(active_result.name)
        self.section_result_source_plane_text.set(
            self._section_plane_summary_for_result(active_result)
        )
        self.section_result_axis_text.set(active_result.axis)
        self.section_result_offset_text.set(f"{active_result.offset:.3f}")
        self.section_result_segment_count_text.set(str(active_result.result.segment_count))
        self.section_result_curve_count_text.set(
            str(self._curve_count_for_section_result(active_result.id))
        )

    def _section_plane_summary_for_result(self, result: StoredSectionResult) -> str:
        for plane in self.app_state.section_collection.planes:
            if plane.id == result.plane_id:
                return f"{plane.name} ({plane.axis} = {plane.offset:.3f})"
        return "(missing)"

    def _curve_count_for_section_result(self, result_id: str) -> int:
        return sum(
            1
            for curve in self.app_state.curve_collection.curves
            if curve.section_result_id == result_id
        )

    def _active_curve(self) -> StoredCurve | None:
        active_curve_id = self.app_state.curve_collection.active_curve_id
        if active_curve_id is None:
            return None

        for curve in self.app_state.curve_collection.curves:
            if curve.id == active_curve_id:
                return curve
        return None

    def _sync_curve_context_from_active_curve(self) -> None:
        active_curve = self._active_curve()
        if active_curve is None:
            self.curve_visible.set(False)
            self.curve_name_text.set("(none)")
            self.curve_section_text.set("(none)")
            self.curve_plane_text.set("(none)")
            self.curve_point_count_text.set("0")
            self.curve_length_text.set("0.000")
            self.curve_endpoint_gap_text.set("0.000")
            self.curve_mean_error_text.set("0.000")
            self.curve_max_error_text.set("0.000")
            self.curve_closed_text.set("Open")
            self.curve_tiny_text.set("No")
            self.curve_type_text.set("(none)")
            self.curve_source_text.set("(none)")
            self.curve_control_point_count_text.set("0")
            self.curve_planarity_error_text.set("(none)")
            self.curve_projection_mean_distance_text.set("(none)")
            self.curve_projection_max_distance_text.set("(none)")
            self.curve_surface_readiness_text.set("Select curve(s) to validate.")
            self.curve_surface_warnings_text.set("(none)")
            self.curve_surface_errors_text.set("(none)")
            return

        refresh_curve_diagnostics(active_curve)
        self.curve_visible.set(bool(active_curve.visible))
        self.curve_name_text.set(active_curve.name)
        self.curve_section_text.set(self._section_result_name_for_curve(active_curve))
        self.curve_plane_text.set(self._section_plane_summary_for_curve(active_curve))
        self.curve_point_count_text.set(str(active_curve.point_count))
        self.curve_length_text.set(f"{active_curve.length:.3f}")
        self.curve_endpoint_gap_text.set(f"{active_curve.endpoint_distance:.3f}")
        self.curve_mean_error_text.set(f"{active_curve.mean_error:.3f}")
        self.curve_max_error_text.set(f"{active_curve.max_error:.3f}")
        self.curve_closed_text.set("Closed" if active_curve.is_closed else "Open")
        self.curve_tiny_text.set("Yes" if active_curve.is_tiny_fragment else "No")
        self.curve_type_text.set(self._curve_type_label(active_curve))
        self.curve_source_text.set(self._curve_source_label(active_curve))
        selected_curves = get_selected_curves(self.app_state.curve_collection)
        if len(selected_curves) == 2:
            self._set_curve_readiness_display(
                validate_curves_for_loft(selected_curves),
                mode="loft",
            )
        else:
            self._set_curve_readiness_display(
                [validate_curve_for_fill(active_curve)],
                mode="fill",
            )

    def _section_result_name_for_curve(self, curve: StoredCurve) -> str:
        for result in self.app_state.section_collection.results:
            if result.id == curve.section_result_id:
                return result.name
        return "(missing)"

    def _section_plane_summary_for_curve(self, curve: StoredCurve) -> str:
        for plane in self.app_state.section_collection.planes:
            if plane.id == curve.plane_id:
                return f"{plane.name} ({plane.axis} = {plane.offset:.3f})"
        return "(missing)"

    def _set_curve_readiness_display(
        self,
        readiness_items: Sequence[CurveSurfaceReadiness],
        *,
        mode: str,
    ) -> None:
        if not readiness_items:
            self.curve_control_point_count_text.set("0")
            self.curve_planarity_error_text.set("(none)")
            self.curve_projection_mean_distance_text.set("(none)")
            self.curve_projection_max_distance_text.set("(none)")
            self.curve_surface_readiness_text.set("Select curve(s) to validate.")
            self.curve_surface_warnings_text.set("(none)")
            self.curve_surface_errors_text.set("(none)")
            return

        first = readiness_items[0]
        self.curve_control_point_count_text.set(
            "(none)"
            if first.control_point_count is None
            else str(int(first.control_point_count))
        )
        self.curve_planarity_error_text.set(self._optional_float_text(first.planarity_error))
        self.curve_projection_mean_distance_text.set(
            self._optional_float_text(first.mesh_projection_mean_distance)
        )
        self.curve_projection_max_distance_text.set(
            self._optional_float_text(first.mesh_projection_max_distance)
        )
        errors = self._readiness_errors(readiness_items)
        warnings = self._readiness_warnings(readiness_items)
        if errors:
            status = "Not Ready"
        elif mode == "loft":
            status = "Ready for Loft"
        else:
            status = "Ready for Fill"
        self.curve_surface_readiness_text.set(status)
        self.curve_surface_warnings_text.set("; ".join(warnings) if warnings else "(none)")
        self.curve_surface_errors_text.set("; ".join(errors) if errors else "(none)")

    @staticmethod
    def _readiness_warnings(readiness_items: Sequence[CurveSurfaceReadiness]) -> list[str]:
        warnings: list[str] = []
        for readiness in readiness_items:
            warnings.extend(readiness.warnings)
        return list(dict.fromkeys(warnings))

    @staticmethod
    def _readiness_errors(readiness_items: Sequence[CurveSurfaceReadiness]) -> list[str]:
        errors: list[str] = []
        for readiness in readiness_items:
            errors.extend(readiness.errors)
        return list(dict.fromkeys(errors))

    def _first_readiness_warning(
        self,
        readiness_items: Sequence[CurveSurfaceReadiness],
    ) -> str | None:
        warnings = self._readiness_warnings(readiness_items)
        return warnings[0] if warnings else None

    def _first_readiness_error(
        self,
        readiness_items: Sequence[CurveSurfaceReadiness],
    ) -> str | None:
        errors = self._readiness_errors(readiness_items)
        return errors[0] if errors else None

    @staticmethod
    def _optional_float_text(value: float | None) -> str:
        if value is None:
            return "(none)"
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "(none)"
        if not np.isfinite(number):
            return "(none)"
        return f"{number:.3f}"

    def _curve_type_label(self, curve: StoredCurve) -> str:
        metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
        creation_type = str(metadata.get("creation_type", "")).strip().lower()
        labels = {
            "projected_curve": "Projected",
            "rebuilt_curve": "Rebuilt",
            "region_boundary": "Region Boundary",
            "manual": "Manual",
            "curve_on_mesh": "Curve on Mesh",
        }
        if creation_type in labels:
            return labels[creation_type]
        if is_repaired_curve(curve):
            return "Repaired/Processed"
        if curve.section_result_id:
            return "Section Curve"
        return "Curve"

    @staticmethod
    def _curve_source_label(curve: StoredCurve) -> str:
        metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
        for key in ("source_curve_name", "source_region_name", "source_mesh_name"):
            value = metadata.get(key)
            if value:
                return str(value)
        return "(none)"

    def _validated_name_candidate(
        self,
        value: StringVar,
        current_name: str,
        entry: ttk.Entry,
        event: object | None,
    ) -> str | None:
        candidate = value.get().strip()
        if candidate:
            return candidate

        keysym = getattr(event, "keysym", "")
        if self.root.focus_get() is not entry or keysym == "Return":
            value.set(current_name)
            self.status_text.set("Name cannot be empty")
        return None

    def _on_curve_name_changed(self, _event: object | None = None) -> None:
        active_curve = self._active_curve()
        if active_curve is None:
            return

        candidate = self._validated_name_candidate(
            self.curve_name_text,
            active_curve.name,
            self.curve_name_entry,
            _event,
        )
        if candidate == active_curve.name:
            return
        if candidate is None:
            return

        old_name = active_curve.name
        active_curve.name = candidate
        self._push_rename_command(
            curve_node_id(active_curve.id),
            "Rename Curve",
            old_name,
            candidate,
        )
        self._refresh_scene_browser()
        self.status_text.set(f"Selected: {active_curve.name}")
        self._set_project_dirty(True)

    def _on_curve_visibility_changed(self) -> None:
        active_curve = self._active_curve()
        if active_curve is None:
            self.status_text.set("No selection")
            return

        node_ids = {curve_node_id(active_curve.id)}
        before = self._visibility_snapshot(node_ids)
        active_curve.visible = bool(self.curve_visible.get())
        after = self._visibility_snapshot(node_ids)
        self._push_visibility_command("Toggle Visibility", before, after)
        self._sync_visible_curve_results()
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(f"Selected: {active_curve.name}")
        self._set_project_dirty(True)

    def join_selected_curves(self) -> None:
        selected_curves = get_selected_curves(self.app_state.curve_collection)
        if len(selected_curves) < 2:
            self.status_text.set("Select at least two curves to join")
            return

        tolerance = self._curve_repair_tolerance()
        try:
            repaired_curve = join_curves(
                selected_curves,
                curve_id=f"curve-{uuid4().hex}",
                name=self._next_repaired_curve_name("Joined Curve"),
                tolerance=tolerance,
            )
        except CurveRepairError as exc:
            self.status_text.set(f"{exc} Tolerance: {tolerance:.3f}")
            return

        add_curve(self.app_state.curve_collection, repaired_curve)
        self._sync_visible_curve_results()
        self.select_curve(repaired_curve.id)
        self._push_created_curve_command(repaired_curve)
        source_count = len(selected_curves)
        self.status_text.set(
            f"Created joined curve from {source_count} curves "
            f"(tolerance {tolerance:.3f})"
        )
        self._set_project_dirty(True)

    def auto_close_selected_curve(self) -> None:
        selected_curves = get_selected_curves(self.app_state.curve_collection)
        if len(selected_curves) != 1:
            self.status_text.set("Select exactly one open curve to auto-close")
            return

        selected_curve = selected_curves[0]
        refresh_curve_diagnostics(selected_curve)
        tolerance = self._curve_repair_tolerance()
        endpoint_gap = selected_curve.endpoint_distance
        if selected_curve.is_closed:
            self.status_text.set("Selected curve is already closed")
            return
        if endpoint_gap > tolerance:
            self.status_text.set(
                f"Endpoint gap {endpoint_gap:.3f} exceeds tolerance {tolerance:.3f}"
            )
            return

        try:
            repaired_curve = auto_close_curve(
                selected_curve,
                curve_id=f"curve-{uuid4().hex}",
                name=self._next_repaired_curve_name("Auto-Closed Curve"),
                tolerance=tolerance,
            )
        except CurveRepairError as exc:
            self.status_text.set(f"{exc} Tolerance: {tolerance:.3f}")
            return

        add_curve(self.app_state.curve_collection, repaired_curve)
        self._sync_visible_curve_results()
        self.select_curve(repaired_curve.id)
        self._push_created_curve_command(repaired_curve)
        self.status_text.set(
            f"Created auto-closed curve "
            f"(gap {endpoint_gap:.3f}, tolerance {tolerance:.3f})"
        )
        self._set_project_dirty(True)

    def simplify_selected_curve(self) -> None:
        selected_curves = get_selected_curves(self.app_state.curve_collection)
        if len(selected_curves) != 1:
            self.status_text.set("Select exactly one curve to simplify")
            return

        selected_curve = selected_curves[0]
        refresh_curve_diagnostics(selected_curve)
        tolerance = self._curve_simplify_tolerance(selected_curve)
        source_point_count = selected_curve.point_count
        try:
            generated_curve = simplify_curve(
                selected_curve,
                curve_id=f"curve-{uuid4().hex}",
                name=self._next_repaired_curve_name("Simplified Curve"),
                tolerance=tolerance,
            )
        except CurveProcessingError as exc:
            self.status_text.set(f"{exc} Tolerance: {tolerance:.3f}")
            return

        add_curve(self.app_state.curve_collection, generated_curve)
        self._sync_visible_curve_results()
        self.select_curve(generated_curve.id)
        self._push_created_curve_command(generated_curve)
        self.status_text.set(
            f"Created simplified curve "
            f"({source_point_count} -> {generated_curve.point_count} points, "
            f"tolerance {tolerance:.3f})"
        )
        self._set_project_dirty(True)

    def smooth_selected_curve(self) -> None:
        selected_curves = get_selected_curves(self.app_state.curve_collection)
        if len(selected_curves) != 1:
            self.status_text.set("Select exactly one curve to smooth")
            return

        selected_curve = selected_curves[0]
        try:
            generated_curve = smooth_curve(
                selected_curve,
                curve_id=f"curve-{uuid4().hex}",
                name=self._next_repaired_curve_name("Smoothed Curve"),
                iterations=DEFAULT_CURVE_SMOOTH_ITERATIONS,
            )
        except CurveProcessingError as exc:
            self.status_text.set(str(exc))
            return

        add_curve(self.app_state.curve_collection, generated_curve)
        self._sync_visible_curve_results()
        self.select_curve(generated_curve.id)
        self._push_created_curve_command(generated_curve)
        self.status_text.set(
            f"Created smoothed curve "
            f"({generated_curve.point_count} points, "
            f"{DEFAULT_CURVE_SMOOTH_ITERATIONS} iterations)"
        )
        self._set_project_dirty(True)

    def project_selected_curve_to_mesh(self) -> None:
        mesh_object = self.app_state.mesh_object
        if mesh_object is None:
            self.status_text.set("Load a mesh before projecting curves.")
            self._sync_workflow_ui()
            return

        source_curve = self._single_curve_for_surface_prep("Select one curve to project.")
        if source_curve is None:
            return

        boundary_mesh = mesh_object.display_mesh.copy()
        boundary_mesh.transform(self._current_object_matrix())
        projected_curve = project_stored_curve_to_mesh(
            source_curve,
            boundary_mesh,
            curve_id=f"curve-{uuid4().hex}",
            name=self._next_derived_curve_name("Projected Curve"),
            source_mesh_name=mesh_object.name,
        )
        add_curve(self.app_state.curve_collection, projected_curve)
        self._sync_visible_curve_results()
        self.select_curve(projected_curve.id)
        self._push_created_curve_command(
            projected_curve,
            command_name="Project Curve to Mesh",
        )
        self.status_text.set(
            "Projected "
            f"{projected_curve.metadata.get('projection_projected_count', 0)} points "
            f"to {projected_curve.name}."
        )
        self._set_project_dirty(True)
        self._sync_workflow_ui()

    def rebuild_selected_curve(self) -> None:
        source_curve = self._single_curve_for_surface_prep("Select one curve to rebuild.")
        if source_curve is None:
            return

        target_count = self._rebuild_target_control_point_count()
        sample_count = self._rebuild_sample_count_value()
        curve_method = self._rebuild_curve_method()
        rebuilt_curve = rebuild_stored_curve(
            source_curve,
            curve_id=f"curve-{uuid4().hex}",
            name=self._next_derived_curve_name("Rebuilt Curve"),
            target_control_point_count=target_count,
            curve_method=curve_method,
            sample_count=sample_count,
        )
        add_curve(self.app_state.curve_collection, rebuilt_curve)
        self._sync_visible_curve_results()
        self.select_curve(rebuilt_curve.id)
        self._push_created_curve_command(
            rebuilt_curve,
            command_name="Rebuild Curve",
        )
        self.status_text.set(
            f"Rebuilt {source_curve.name} into {rebuilt_curve.name} "
            f"({rebuilt_curve.metadata.get('rebuild_target_control_point_count', 0)} controls)."
        )
        self._set_project_dirty(True)
        self._sync_workflow_ui()

    def validate_selected_curve(self) -> None:
        source_curve = self._single_curve_for_surface_prep("Select curve(s) to validate.")
        if source_curve is None:
            return

        readiness = validate_curve_for_fill(source_curve)
        self._set_curve_readiness_display([readiness], mode="fill")
        if readiness.errors:
            self.status_text.set(readiness.errors[0])
        elif readiness.warnings:
            self.status_text.set(readiness.warnings[0])
        else:
            self.status_text.set("Ready for Fill")
        self._sync_workflow_ui()

    def validate_selected_curves_for_loft(self) -> None:
        curves = self._surface_source_curves_from_selection()
        if not curves:
            self.status_text.set("Select curve(s) to validate.")
            self._sync_workflow_ui()
            return

        readiness = validate_curves_for_loft(curves)
        self._set_curve_readiness_display(readiness, mode="loft")
        first_error = self._first_readiness_error(readiness)
        first_warning = self._first_readiness_warning(readiness)
        if first_error:
            self.status_text.set(first_error)
        elif first_warning:
            self.status_text.set(first_warning)
        else:
            self.status_text.set("Ready for Loft")
        self._sync_workflow_ui()

    def _single_curve_for_surface_prep(self, message: str) -> StoredCurve | None:
        selected_curves = get_selected_curves(self.app_state.curve_collection)
        if not selected_curves:
            active_curve = self._active_curve()
            selected_curves = [] if active_curve is None else [active_curve]
        if len(selected_curves) != 1:
            self.status_text.set(message)
            self._sync_workflow_ui()
            return None
        return selected_curves[0]

    def _rebuild_target_control_point_count(self) -> int:
        try:
            value = int(str(self.rebuild_target_control_points.get()).strip())
        except (TypeError, ValueError):
            value = 16
        value = min(max(value, 2), 256)
        self.rebuild_target_control_points.set(str(value))
        return value

    def _rebuild_sample_count_value(self) -> int:
        try:
            value = int(str(self.rebuild_sample_count.get()).strip())
        except (TypeError, ValueError):
            value = 128
        value = max(value, 2)
        self.rebuild_sample_count.set(str(value))
        return value

    def _rebuild_curve_method(self) -> str:
        return "polyline" if self.rebuild_curve_type_text.get().strip().lower() == "polyline" else DEFAULT_MANUAL_CURVE_METHOD

    def _next_derived_curve_name(self, prefix: str) -> str:
        existing_names = {
            curve.name for curve in self.app_state.curve_collection.curves
        }
        index = 1
        while f"{prefix} {index}" in existing_names:
            index += 1
        return f"{prefix} {index}"

    def create_surface_from_curves(self) -> None:
        source_curves = self._surface_source_curves_from_selection()
        if len(source_curves) == 1:
            self.fill_closed_curve()
            return
        if len(source_curves) == 2:
            self.loft_between_two_curves()
            return
        if not self.app_state.curve_collection.curves:
            self.status_text.set("No curves available")
            return
        self.status_text.set("Select one closed curve to fill or exactly two curves to loft")

    def fill_closed_curve(self) -> None:
        source_curves = self._surface_source_curves_from_selection()
        if not self.app_state.curve_collection.curves:
            self.status_text.set("No curves available")
            return
        if len(source_curves) != 1:
            self.status_text.set("Select exactly one closed curve to fill")
            return

        source_curve = source_curves[0]
        refresh_curve_diagnostics(source_curve)
        readiness = validate_curve_for_fill(source_curve)
        if readiness.errors:
            self._set_curve_readiness_display([readiness], mode="fill")
            self.status_text.set(readiness.errors[0])
            return

        self._create_surface_preview(
            source_curves,
            surface_type="preview_fill",
            preview_mode=CLOSED_CURVE_FILL,
            source_label="selected_curve",
            name_prefix="Fill Surface",
            success_action="Filled",
            validation_readiness=[readiness],
        )

    def loft_between_two_curves(self) -> None:
        source_curves = self._surface_source_curves_from_selection()
        if not self.app_state.curve_collection.curves:
            self.status_text.set("No curves available")
            return
        if len(source_curves) != 2:
            self.status_text.set("Select exactly two curves to loft")
            return
        readiness = validate_curves_for_loft(source_curves)
        first_error = self._first_readiness_error(readiness)
        if first_error:
            self._set_curve_readiness_display(readiness, mode="loft")
            self.status_text.set(first_error)
            return

        self._create_surface_preview(
            source_curves,
            surface_type="preview_loft",
            preview_mode=TWO_CURVE_LOFT,
            source_label="selected_curves",
            name_prefix="Loft Surface",
            success_action="Lofted",
            validation_readiness=readiness,
        )

    def create_boundary_patch_from_curve(self) -> None:
        source_curves = self._surface_source_curves_from_selection()
        if not self.app_state.curve_collection.curves:
            self.status_text.set("No curves available")
            return
        if len(source_curves) != 1:
            self.status_text.set("Create Boundary Patch requires one closed curve.")
            return

        readiness = validate_curve_for_fill(source_curves[0])
        if readiness.errors:
            self._set_curve_readiness_display([readiness], mode="fill")
            if not readiness.is_closed:
                self.status_text.set("Create Boundary Patch requires one closed curve.")
            else:
                self.status_text.set(readiness.errors[0])
            return

        source_curve = source_curves[0]
        self._create_surface_preview(
            source_curves,
            surface_type="preview_boundary_patch",
            preview_mode=BOUNDARY_PATCH,
            source_label="selected_curve",
            name_prefix="Boundary Patch",
            success_action="Created",
            validation_readiness=[readiness],
            extra_metadata={
                "boundary_curve_id": source_curve.id,
                "boundary_curve_name": source_curve.name,
            },
        )

    def create_four_curve_patch(self) -> None:
        source_curves = self._surface_source_curves_from_selection()
        if not self.app_state.curve_collection.curves:
            self.status_text.set("No curves available")
            return
        warnings, errors = self._surface_patch_validation_messages(
            source_curves,
            preview_mode=FOUR_CURVE_PATCH,
        )
        if errors:
            self.status_text.set(errors[0])
            return

        self._create_surface_preview(
            source_curves,
            surface_type="preview_four_curve_patch",
            preview_mode=FOUR_CURVE_PATCH,
            source_label="selected_curves",
            name_prefix="Four-Curve Patch",
            success_action="Created",
            validation_warnings=warnings,
            validation_errors=errors,
            extra_metadata={"curve_order": [curve.id for curve in source_curves]},
        )

    def create_curve_network_patch(self) -> None:
        source_curves = self._surface_source_curves_from_selection()
        if not self.app_state.curve_collection.curves:
            self.status_text.set("No curves available")
            return
        warnings, errors = self._surface_patch_validation_messages(
            source_curves,
            preview_mode=CURVE_NETWORK_PATCH,
        )
        if errors:
            self.status_text.set(errors[0])
            return

        self._create_surface_preview(
            source_curves,
            surface_type="preview_curve_network_patch",
            preview_mode=CURVE_NETWORK_PATCH,
            source_label="selected_curves",
            name_prefix="Network Patch",
            success_action="Created",
            validation_warnings=warnings,
            validation_errors=errors,
        )

    def _create_surface_preview(
        self,
        source_curves: list[StoredCurve],
        *,
        surface_type: str,
        preview_mode: str,
        source_label: str,
        name_prefix: str,
        success_action: str,
        validation_readiness: Sequence[CurveSurfaceReadiness] | None = None,
        validation_warnings: Sequence[str] | None = None,
        validation_errors: Sequence[str] | None = None,
        extra_metadata: dict[str, object] | None = None,
    ) -> None:
        source_curve_names = [curve.name for curve in source_curves]
        metadata: dict[str, object] = {
            "curve_count": len(source_curves),
            "source_curve_count": len(source_curves),
            "source_curve_ids": [curve.id for curve in source_curves],
            "source_curve_names": source_curve_names,
            "source": source_label,
            "preview_mode": preview_mode,
            "source_curve_validation_warnings": [],
            "source_curve_validation_errors": [],
        }
        metadata.update(self._surface_source_lineage_metadata(source_curves))
        if validation_readiness is not None:
            metadata.update(self._surface_validation_metadata(validation_readiness))
        if validation_warnings:
            metadata["source_curve_validation_warnings"] = self._merged_metadata_strings(
                metadata.get("source_curve_validation_warnings"),
                validation_warnings,
            )
        if validation_errors:
            metadata["source_curve_validation_errors"] = self._merged_metadata_strings(
                metadata.get("source_curve_validation_errors"),
                validation_errors,
            )
        if extra_metadata:
            metadata.update(extra_metadata)
        surface = SurfacePatch(
            id=f"surface-{uuid4().hex}",
            name=self._next_surface_name(name_prefix),
            source_curve_ids=[curve.id for curve in source_curves],
            surface_type=surface_type,
            metadata=metadata,
        )
        progress: ComputationProgressDialog | None = None
        try:
            progress = ComputationProgressDialog(
                self.root,
                "Building Surface Preview",
                "Building surface preview",
            )
            self._set_progress_stage(progress, SURFACE_PREVIEW_PROGRESS_STAGES[0])
            self._set_progress_stage(progress, SURFACE_PREVIEW_PROGRESS_STAGES[1])
            preview_result = build_surface_preview(
                surface,
                self.app_state.curve_collection.curves,
            )
            self._set_progress_stage(progress, SURFACE_PREVIEW_PROGRESS_STAGES[2])
        finally:
            if progress is not None:
                progress.close()

        surface.metadata["preview_available"] = bool(preview_result.preview_available)
        surface.metadata["preview_reason"] = preview_result.reason
        surface.metadata.update(preview_result.diagnostics)
        surface.metadata["preview_warning"] = preview_result.warning or ""
        backend_warnings = preview_result.diagnostics.get("warnings")
        if isinstance(backend_warnings, list):
            surface.metadata["source_curve_validation_warnings"] = self._merged_metadata_strings(
                surface.metadata.get("source_curve_validation_warnings"),
                backend_warnings,
            )
        if preview_result.mesh is None:
            self.status_text.set(f"Surface preview unavailable: {preview_result.reason}")
            return

        add_surface(self.app_state.surface_collection, surface)
        self._push_created_surface_command(surface)
        self._sync_surface_context_from_active_surface()
        curve_label = "curve" if len(source_curves) == 1 else "curves"
        status = f"{success_action} {surface.name} from {len(source_curves)} {curve_label}"
        self._set_selected_item(SELECT_SURFACE, status=status)
        self._set_project_dirty(True)

    def _surface_source_curves_from_selection(self) -> list[StoredCurve]:
        selected_curves = get_selected_curves(self.app_state.curve_collection)
        if selected_curves:
            return selected_curves

        active_curve = self._active_curve()
        return [] if active_curve is None else [active_curve]

    def _surface_patch_validation_messages(
        self,
        curves: Sequence[StoredCurve],
        *,
        preview_mode: str,
    ) -> tuple[list[str], list[str]]:
        warnings: list[str] = []
        errors: list[str] = []
        if preview_mode == FOUR_CURVE_PATCH and len(curves) != 4:
            errors.append("Select exactly four curves for a four-curve patch.")
        if preview_mode == CURVE_NETWORK_PATCH and len(curves) < 3:
            errors.append("Select at least three curves for a curve network patch.")
        if errors:
            return warnings, errors

        curve_points: list[np.ndarray] = []
        for curve in curves:
            points = self._surface_patch_curve_points(curve)
            if len(points) < 2:
                errors.append(f"{curve.name} has too few usable points.")
                continue
            if self._surface_patch_curve_length(points) <= 1e-8:
                errors.append(f"{curve.name} is degenerate.")
                continue
            curve_points.append(points)
        if errors:
            return warnings, errors

        warnings.extend(self._surface_source_mismatch_warnings(curves))
        closed_values = [self._curve_is_closed_for_fill(curve) for curve in curves]
        if any(closed_values) and not all(closed_values):
            warnings.append("Surface patch mixes open and closed curves.")

        point_counts = [len(points) for points in curve_points]
        if point_counts and self._surface_count_ratio(min(point_counts), max(point_counts)) > 3.0:
            warnings.append("Surface patch source curves have very different point counts.")

        if preview_mode == FOUR_CURVE_PATCH:
            warnings.append("Curve order inferred from scene order; inspect patch.")
            corner_gaps = self._four_curve_corner_gaps(curve_points)
            if corner_gaps:
                average_length = max(
                    float(
                        np.mean(
                            [
                                self._surface_patch_curve_length(points)
                                for points in curve_points
                            ]
                        )
                    ),
                    1e-8,
                )
                if max(corner_gaps) > average_length * 0.25:
                    warnings.append("Four-curve patch endpoint gaps are large.")

        if preview_mode == CURVE_NETWORK_PATCH:
            spacing_ratio = self._curve_network_spacing_ratio(curve_points)
            if spacing_ratio > 3.0:
                warnings.append("Curve network spacing varies heavily; inspect patch.")

        return list(dict.fromkeys(warnings)), []

    @staticmethod
    def _surface_patch_curve_points(curve: StoredCurve) -> np.ndarray:
        try:
            points = np.asarray(curve.fitted_points, dtype=float)
        except (TypeError, ValueError):
            return np.zeros((0, 3), dtype=float)
        if points.size == 0:
            return np.zeros((0, 3), dtype=float)
        try:
            points = points.reshape((-1, 3))
        except ValueError:
            return np.zeros((0, 3), dtype=float)
        points = points[np.all(np.isfinite(points), axis=1)]
        if len(points) <= 1:
            return points.astype(float, copy=True)
        cleaned = [points[0]]
        for point in points[1:]:
            if np.linalg.norm(point - cleaned[-1]) > 1e-8:
                cleaned.append(point)
        if len(cleaned) > 1 and np.linalg.norm(cleaned[0] - cleaned[-1]) <= 1e-8:
            cleaned.pop()
        return np.asarray(cleaned, dtype=float).reshape((-1, 3))

    @staticmethod
    def _surface_patch_curve_length(points: np.ndarray) -> float:
        if len(points) < 2:
            return 0.0
        return float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())

    @staticmethod
    def _surface_count_ratio(first: int | float, second: int | float) -> float:
        smaller = max(min(float(first), float(second)), 1e-8)
        larger = max(float(first), float(second), 1e-8)
        return larger / smaller

    @staticmethod
    def _four_curve_corner_gaps(curve_points: Sequence[np.ndarray]) -> list[float]:
        if len(curve_points) != 4:
            return []
        bottom, right, top, left = curve_points
        return [
            float(np.linalg.norm(bottom[0] - left[0])),
            float(np.linalg.norm(bottom[-1] - right[0])),
            float(min(np.linalg.norm(top[0] - left[-1]), np.linalg.norm(top[-1] - left[-1]))),
            float(min(np.linalg.norm(top[-1] - right[-1]), np.linalg.norm(top[0] - right[-1]))),
        ]

    def _curve_network_spacing_ratio(self, curve_points: Sequence[np.ndarray]) -> float:
        if len(curve_points) < 2:
            return 1.0
        target_count = min(max(max(len(points) for points in curve_points), 2), 64)
        resampled: list[np.ndarray] = []
        for points in curve_points:
            candidate = self._resample_surface_patch_points(points, target_count)
            if candidate is None:
                return 1.0
            if resampled:
                direct = float(np.mean(np.linalg.norm(resampled[-1] - candidate, axis=1)))
                reversed_candidate = candidate[::-1]
                reversed_distance = float(
                    np.mean(np.linalg.norm(resampled[-1] - reversed_candidate, axis=1))
                )
                if reversed_distance < direct:
                    candidate = reversed_candidate
            resampled.append(candidate)
        strip_distances = [
            float(np.mean(np.linalg.norm(first - second, axis=1)))
            for first, second in zip(resampled, resampled[1:])
        ]
        if not strip_distances:
            return 1.0
        return self._surface_count_ratio(min(strip_distances), max(strip_distances))

    @staticmethod
    def _resample_surface_patch_points(
        points: np.ndarray,
        target_count: int,
    ) -> np.ndarray | None:
        if len(points) == target_count:
            return points.copy()
        segment_lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
        total_length = float(np.sum(segment_lengths))
        if total_length <= 1e-8:
            return None
        cumulative = np.concatenate(([0.0], np.cumsum(segment_lengths)))
        distances = np.linspace(0.0, total_length, target_count)
        segment_indices = np.searchsorted(cumulative, distances, side="right") - 1
        segment_indices = np.clip(segment_indices, 0, len(segment_lengths) - 1)
        local_lengths = segment_lengths[segment_indices].reshape((-1, 1))
        fractions = np.divide(
            (distances - cumulative[segment_indices]).reshape((-1, 1)),
            local_lengths,
            out=np.zeros((len(distances), 1), dtype=float),
            where=local_lengths > 1e-8,
        )
        lower = segment_indices
        upper = np.minimum(segment_indices + 1, len(points) - 1)
        resampled = points[lower] * (1.0 - fractions) + points[upper] * fractions
        resampled[0] = points[0]
        resampled[-1] = points[-1]
        return resampled

    @staticmethod
    def _surface_source_mismatch_warnings(curves: Sequence[StoredCurve]) -> list[str]:
        warnings: list[str] = []
        mesh_names: set[str] = set()
        region_ids: set[str] = set()
        for curve in curves:
            metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
            mesh_name = metadata.get("source_mesh_name")
            region_id = metadata.get("source_region_id")
            if mesh_name:
                mesh_names.add(str(mesh_name))
            if region_id:
                region_ids.add(str(region_id))
        if len(mesh_names) > 1:
            warnings.append("Surface source curves come from different source meshes.")
        if len(region_ids) > 1:
            warnings.append("Surface source curves come from different source regions.")
        return warnings

    def _surface_source_lineage_metadata(
        self,
        source_curves: Sequence[StoredCurve],
    ) -> dict[str, object]:
        creation_types: list[str] = []
        tags: list[str] = []
        region_ids: list[str] = []
        mesh_names: list[str] = []
        for curve in source_curves:
            metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
            creation_type = str(metadata.get("creation_type", "")).strip()
            creation_types.append(creation_type)
            tags.extend(self._surface_source_curve_tags(curve))
            region_id = metadata.get("source_region_id")
            mesh_name = metadata.get("source_mesh_name")
            if region_id:
                region_ids.append(str(region_id))
            if mesh_name:
                mesh_names.append(str(mesh_name))
        lineage: dict[str, object] = {
            "source_curve_creation_types": creation_types,
            "source_curve_tags": list(dict.fromkeys(tags)),
        }
        if region_ids:
            lineage["source_region_ids"] = list(dict.fromkeys(region_ids))
        if mesh_names:
            lineage["source_mesh_names"] = list(dict.fromkeys(mesh_names))
        return lineage

    @staticmethod
    def _surface_source_curve_tags(curve: StoredCurve) -> list[str]:
        metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
        explicit_tags = metadata.get("source_curve_tags", metadata.get("tags"))
        tags: list[str] = []
        if isinstance(explicit_tags, list):
            tags.extend(str(tag) for tag in explicit_tags if str(tag))
        creation_type = str(metadata.get("creation_type", "")).strip().lower()
        if creation_type == "projected_curve":
            tags.append("projected")
        elif creation_type == "rebuilt_curve":
            tags.append("rebuilt")
        elif creation_type == "region_boundary" or "source_region_id" in metadata:
            tags.append("boundary")
        elif creation_type in {"manual", "curve_on_mesh"}:
            tags.append("manual")
        if str(metadata.get("snap_mode", "")).strip().lower() == "mesh" or metadata.get("snap_to_mesh"):
            tags.append("mesh")
        curve_method = str(metadata.get("curve_method", "")).strip().lower()
        if curve_method == "polyline":
            tags.append("polyline")
        elif curve_method:
            tags.append("smooth")
        return list(dict.fromkeys(tags))

    @staticmethod
    def _merged_metadata_strings(
        existing: object,
        additions: Sequence[object],
    ) -> list[str]:
        values: list[str] = []
        if isinstance(existing, list):
            values.extend(str(value) for value in existing if str(value))
        elif existing:
            values.append(str(existing))
        values.extend(str(value) for value in additions if str(value))
        return list(dict.fromkeys(values))

    def _surface_validation_metadata(
        self,
        readiness_items: Sequence[CurveSurfaceReadiness],
    ) -> dict[str, object]:
        warnings = self._readiness_warnings(readiness_items)
        errors = self._readiness_errors(readiness_items)
        planarity_values = [
            readiness.planarity_error
            for readiness in readiness_items
            if readiness.planarity_error is not None
        ]
        projection_values = [
            readiness.mesh_projection_max_distance
            for readiness in readiness_items
            if readiness.mesh_projection_max_distance is not None
        ]
        metadata: dict[str, object] = {
            "source_curve_validation_warnings": warnings,
            "source_curve_validation_errors": errors,
        }
        if planarity_values:
            metadata["source_curve_planarity_error"] = max(float(value) for value in planarity_values)
        if projection_values:
            metadata["source_curve_projection_distance"] = max(
                float(value) for value in projection_values
            )
        return metadata

    def _next_surface_name(self, prefix: str) -> str:
        existing_names = {
            surface.name for surface in self.app_state.surface_collection.surfaces
        }
        index = 1
        while f"{prefix} {index}" in existing_names:
            index += 1
        return f"{prefix} {index}"

    @staticmethod
    def _curve_is_closed_for_fill(curve: StoredCurve) -> bool:
        refresh_curve_diagnostics(curve)
        return bool(curve.is_closed or curve.endpoint_distance <= 1e-8)

    def _next_repaired_curve_name(self, prefix: str) -> str:
        existing_names = {
            curve.name for curve in self.app_state.curve_collection.curves
        }
        index = 1
        while f"{prefix} {index}" in existing_names:
            index += 1
        return f"{prefix} {index}"

    def _handle_manual_curve_pointer_event(
        self,
        event_type: str,
        x_position: int,
        y_position: int,
        *,
        shift_pressed: bool,
        ctrl_pressed: bool,
    ) -> bool:
        if event_type == "left_press":
            self._manual_curve_left_press_position = (int(x_position), int(y_position))
            self._manual_curve_left_dragged = False
            return True

        if event_type == "motion":
            self._update_manual_curve_drag_state(int(x_position), int(y_position))
            if self._should_drag_manual_curve_selected_point():
                self._clear_manual_curve_preview_state()
                self._drag_manual_curve_selected_point(int(x_position), int(y_position))
            else:
                self._update_manual_curve_preview_from_screen(
                    int(x_position),
                    int(y_position),
                )
            return True

        if event_type == "left_release":
            if self._manual_curve_edit_active and self._manual_curve_drag_active:
                self._finish_manual_curve_point_drag()
                return True
            if not self._manual_curve_release_is_click(int(x_position), int(y_position)):
                self.status_text.set(self._manual_curve_status())
                self._sync_workflow_ui()
                return True
            if self._manual_curve_edit_active:
                self._handle_manual_curve_edit_click(
                    int(x_position),
                    int(y_position),
                    ctrl_pressed=ctrl_pressed,
                )
                return True
            if self._manual_curve_placing_enabled:
                self._place_manual_curve_point(int(x_position), int(y_position))
            return True

        if event_type == "right_press":
            return True

        if event_type == "right_release":
            self._show_manual_curve_context_menu(int(x_position), int(y_position))
            return True

        if event_type == "leave":
            if self._clear_manual_curve_preview_state():
                self._refresh_viewport(reset_camera=False)
            return True

        return False

    def _update_manual_curve_drag_state(self, x_position: int, y_position: int) -> None:
        if self._manual_curve_left_press_position is None:
            return

        start_x, start_y = self._manual_curve_left_press_position
        distance = abs(int(x_position) - start_x) + abs(int(y_position) - start_y)
        if distance > 4:
            self._manual_curve_left_dragged = True

    def _should_drag_manual_curve_selected_point(self) -> bool:
        return bool(
            self._manual_curve_edit_active
            and self._manual_curve_left_dragged
            and self._manual_curve_selected_control_point_index is not None
            and not self._manual_curve_add_point_active
            and not self._manual_curve_insert_point_active
        )

    def _drag_manual_curve_selected_point(self, x_position: int, y_position: int) -> None:
        selected_index = self._manual_curve_selected_control_point_index
        if selected_index is None or not (0 <= selected_index < len(self._manual_curve_points)):
            return

        point = self._manual_curve_point_from_screen(
            x_position,
            y_position,
            snap_to_mesh=bool(self.manual_curve_snap_to_mesh.get()),
        )
        if point is None:
            return

        self._manual_curve_drag_active = True
        self._manual_curve_points[selected_index] = point
        if selected_index != 0:
            self._snap_manual_curve_closed_to_first_point(point, edit_status=True)
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(f"Moving control point {selected_index + 1}")
        self._sync_workflow_ui()

    def _finish_manual_curve_point_drag(self) -> None:
        selected_index = self._manual_curve_selected_control_point_index
        self._manual_curve_drag_active = False
        self._manual_curve_left_press_position = None
        self._manual_curve_left_dragged = False
        if selected_index is None:
            self.status_text.set("Moved control point")
        else:
            self.status_text.set(f"Moved control point {selected_index + 1}")
        self._sync_workflow_ui()

    def _manual_curve_release_is_click(self, x_position: int, y_position: int) -> bool:
        if self._manual_curve_left_press_position is None:
            return False

        self._update_manual_curve_drag_state(x_position, y_position)
        is_click = not self._manual_curve_left_dragged
        self._manual_curve_left_press_position = None
        self._manual_curve_left_dragged = False
        return is_click

    def _update_manual_curve_preview_from_screen(
        self,
        x_position: int,
        y_position: int,
    ) -> None:
        status_signature = self._manual_curve_preview_status_signature()
        if not self._manual_curve_preview_enabled():
            if self._clear_manual_curve_preview_state():
                self._refresh_viewport(reset_camera=False)
            self._sync_manual_curve_preview_status(status_signature)
            return

        (
            point,
            valid,
            snaps_to_mesh,
            triangle_index,
            normal,
        ) = self._manual_curve_preview_candidate_from_screen(x_position, y_position)
        if not valid or point is None:
            if self._set_manual_curve_preview_state(
                valid=False,
                snaps_to_mesh=snaps_to_mesh,
            ):
                self._refresh_viewport(reset_camera=False)
            self._sync_manual_curve_preview_status(status_signature)
            return

        snaps_closed = should_snap_closed_to_first_point(
            self._manual_curve_points,
            point,
            model_extent=self._manual_curve_model_extent(),
        )
        if self._set_manual_curve_preview_state(
            point=point,
            valid=True,
            snaps_closed=snaps_closed,
            snaps_to_mesh=snaps_to_mesh,
            triangle_index=triangle_index,
            normal=normal,
        ):
            self._refresh_viewport(reset_camera=False)
        self._sync_manual_curve_preview_status(status_signature)

    def _manual_curve_preview_enabled(self) -> bool:
        if not self._manual_curve_active:
            return False
        if self.current_workbench.get() != "Manual RE":
            return False
        if self._manual_curve_edit_active:
            return bool(
                (self._manual_curve_add_point_active or self._manual_curve_insert_point_active)
                and not self._manual_curve_drag_active
            )
        return bool(self._manual_curve_placing_enabled)

    def _manual_curve_preview_status_signature(self) -> tuple[object, ...]:
        return (
            bool(self._manual_curve_preview_enabled()),
            bool(self._manual_curve_preview_valid),
            bool(self._manual_curve_preview_snaps_closed),
            bool(self.manual_curve_snap_to_mesh.get()),
            bool(self._manual_curve_edit_active),
            bool(self._manual_curve_add_point_active),
            bool(self._manual_curve_insert_point_active),
        )

    def _sync_manual_curve_preview_status(
        self,
        previous_signature: tuple[object, ...],
    ) -> None:
        status = self._manual_curve_preview_status()
        if (
            previous_signature == self._manual_curve_preview_status_signature()
            and self.status_text.get() == status
        ):
            return
        self.status_text.set(status)

    def _manual_curve_preview_status(self) -> str:
        if not self._manual_curve_preview_enabled():
            return self._manual_curve_status()
        if self._manual_curve_preview_snaps_closed:
            return "Manual Curve: click near first point to close."
        if self._manual_curve_edit_active:
            if self._manual_curve_add_point_active:
                return "Edit Curve: Add Point active. Click to place next point."
            if self._manual_curve_insert_point_active:
                return "Edit Curve: Insert Point active. Click segment location."
            return "Manual Curve Edit: click a control point to select it."
        if bool(self.manual_curve_snap_to_mesh.get()):
            if self._manual_curve_preview_valid:
                return "Manual Curve: Snap to Mesh On. Click scan surface to place."
            return "Manual Curve: no mesh under cursor."
        if self._manual_curve_preview_valid:
            return "Manual Curve: previewing next point. Click to place."
        return "Manual Curve: could not place point on work plane"

    def _manual_curve_preview_candidate_from_screen(
        self,
        x_position: int,
        y_position: int,
    ) -> tuple[np.ndarray | None, bool, bool, int | None, list[float] | None]:
        if bool(self.manual_curve_snap_to_mesh.get()):
            pick_result = self.viewport.pick_mesh_at_screen_point(
                int(x_position),
                int(y_position),
            )
            if not bool(getattr(pick_result, "hit", False)):
                return (None, False, True, None, None)
            position = getattr(pick_result, "position", None)
            point = self._finite_manual_curve_point(position)
            if point is None:
                return (None, False, True, None, None)
            triangle_index = self._manual_curve_triangle_index_value(
                getattr(pick_result, "triangle_index", None)
            )
            normal = self._manual_curve_pick_normal_value(
                getattr(pick_result, "normal", None)
            )
            return (point, True, True, triangle_index, normal)

        point = self.viewport.screen_point_to_plane(
            int(x_position),
            int(y_position),
            self._manual_curve_plane_origin,
            self._manual_curve_plane_normal,
        )
        point_array = self._finite_manual_curve_point(point)
        if point_array is None:
            return (None, False, False, None, None)
        return (point_array, True, False, None, None)

    @staticmethod
    def _finite_manual_curve_point(point: object) -> np.ndarray | None:
        if point is None:
            return None
        try:
            point_array = np.asarray(point, dtype=float).reshape(3)
        except (TypeError, ValueError):
            return None
        if not np.all(np.isfinite(point_array)):
            return None
        return point_array

    @staticmethod
    def _manual_curve_triangle_index_value(index: object) -> int | None:
        if index is None:
            return None
        try:
            return int(index)
        except (TypeError, ValueError):
            return None

    def _set_manual_curve_preview_state(
        self,
        *,
        point: np.ndarray | None = None,
        valid: bool,
        snaps_closed: bool = False,
        snaps_to_mesh: bool = False,
        triangle_index: int | None = None,
        normal: list[float] | None = None,
    ) -> bool:
        point_array = None if point is None else np.asarray(point, dtype=float).reshape(3)
        changed = self._manual_curve_preview_state_changed(
            point_array,
            valid=valid,
            snaps_closed=snaps_closed,
            snaps_to_mesh=snaps_to_mesh,
            triangle_index=triangle_index,
            normal=normal,
        )
        self._manual_curve_preview_point = point_array if valid else None
        self._manual_curve_preview_valid = bool(valid)
        self._manual_curve_preview_snaps_closed = bool(snaps_closed and valid)
        self._manual_curve_preview_snaps_to_mesh = bool(snaps_to_mesh and valid)
        self._manual_curve_preview_triangle_index = triangle_index if valid else None
        self._manual_curve_preview_normal = list(normal) if valid and normal is not None else None
        return changed

    def _manual_curve_preview_state_changed(
        self,
        point: np.ndarray | None,
        *,
        valid: bool,
        snaps_closed: bool,
        snaps_to_mesh: bool,
        triangle_index: int | None,
        normal: list[float] | None,
    ) -> bool:
        if self._manual_curve_preview_valid != bool(valid):
            return True
        if self._manual_curve_preview_snaps_closed != bool(snaps_closed and valid):
            return True
        if self._manual_curve_preview_snaps_to_mesh != bool(snaps_to_mesh and valid):
            return True
        if self._manual_curve_preview_triangle_index != (triangle_index if valid else None):
            return True
        current_normal = self._manual_curve_preview_normal
        next_normal = list(normal) if valid and normal is not None else None
        if current_normal != next_normal:
            return True
        if not valid:
            return self._manual_curve_preview_point is not None
        if point is None or self._manual_curve_preview_point is None:
            return True
        return not bool(np.allclose(self._manual_curve_preview_point, point))

    def _clear_manual_curve_preview_state(self) -> bool:
        return self._set_manual_curve_preview_state(valid=False)

    def start_manual_curve_mode(self) -> None:
        if self.app_state.mesh_object is None:
            self.status_text.set("Load a mesh to use Manual Curve")
            self._sync_workflow_ui()
            return

        if self.app_state.transform_state is not None:
            self._end_active_transform(commit=False, status="Transform cancelled")
        self.app_state.active_transform_mode = None
        self.app_state.active_transform_axis = None
        self._active_transform_angle_delta = None
        if self._region_select_active:
            self._exit_region_select_mode()

        (
            self._manual_curve_plane_origin,
            self._manual_curve_plane_normal,
            self._manual_curve_plane_type,
            self._manual_curve_plane_label,
            self._manual_curve_source_section_plane_id,
        ) = self._manual_curve_work_plane()
        self._manual_curve_active = True
        self._manual_curve_edit_active = False
        self._manual_curve_edit_curve_id = None
        self._manual_curve_selected_control_point_index = None
        self._manual_curve_hover_control_point_index = None
        self._manual_curve_drag_active = False
        self._manual_curve_placing_enabled = True
        self._manual_curve_add_point_active = False
        self._manual_curve_insert_point_active = False
        self._manual_curve_curve_method = self._manual_curve_method_from_label()
        self._manual_curve_sample_count = DEFAULT_MANUAL_CURVE_SAMPLE_COUNT
        self._manual_curve_left_press_position = None
        self._manual_curve_left_dragged = False
        self._clear_manual_curve_preview_state()
        self._manual_curve_points = []
        self._manual_curve_closed = False
        self._manual_curve_snap_point_count = 0
        self._manual_curve_snap_flags = []
        self._manual_curve_snap_triangle_indices = []
        self._manual_curve_snap_normals = []
        self._set_active_workbench("Manual RE", set_status=False)
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(self._manual_curve_status())
        self._sync_workflow_ui()

    def _on_manual_curve_snap_to_mesh_changed(self) -> None:
        if self.app_state.mesh_object is None:
            self.manual_curve_snap_to_mesh.set(False)
            self.status_text.set("Load a mesh to use Snap to Mesh")
            self._sync_workflow_ui()
            return

        if self._manual_curve_active:
            self._clear_manual_curve_preview_state()
            self._refresh_viewport(reset_camera=False)
            self.status_text.set(self._manual_curve_status())
            self._sync_workflow_ui()
            return

        self.status_text.set(
            "Snap to Mesh: On"
            if bool(self.manual_curve_snap_to_mesh.get())
            else "Snap to Mesh: Off"
        )
        self._sync_workflow_ui()

    def _manual_curve_work_plane(
        self,
    ) -> tuple[np.ndarray, np.ndarray, str, str, str | None]:
        active_plane = get_active_plane(self.app_state.section_collection)
        if active_plane is not None:
            return (
                np.asarray(plane_origin(active_plane), dtype=float).reshape(3),
                normalized_vector(
                    np.asarray(plane_normal(active_plane), dtype=float).reshape(3),
                    fallback=np.asarray([0.0, 0.0, 1.0], dtype=float),
                ),
                "section_plane",
                active_plane.name or "Section Plane",
                active_plane.id,
            )

        return (
            np.asarray([0.0, 0.0, 0.0], dtype=float),
            np.asarray([0.0, 0.0, 1.0], dtype=float),
            "world_xy",
            "world XY plane",
            None,
        )

    def start_manual_curve_edit_mode(self) -> None:
        if self.app_state.mesh_object is None:
            self.status_text.set("Load a mesh to use Manual Curve")
            self._sync_workflow_ui()
            return

        active_curve = self._active_curve()
        if active_curve is None:
            self.status_text.set("Select a manual curve to edit.")
            self._sync_workflow_ui()
            return
        if not self._is_editable_manual_curve(active_curve):
            self.status_text.set("Only manual curves can be edited in this mode.")
            self._sync_workflow_ui()
            return

        self._begin_manual_curve_edit_mode(
            active_curve,
            status=f"Editing {active_curve.name}",
        )

    def _begin_manual_curve_edit_mode(self, curve: StoredCurve, *, status: str) -> None:
        control_data = self._manual_curve_control_data_for_curve(curve)
        if control_data is None:
            self.status_text.set("Manual curve has no editable control points.")
            self._sync_workflow_ui()
            return

        if self.app_state.transform_state is not None:
            self._end_active_transform(commit=False, status="Transform cancelled")
        if self._region_select_active:
            self._exit_region_select_mode()
        self.app_state.active_transform_mode = None
        self.app_state.active_transform_axis = None
        self._active_transform_angle_delta = None

        (
            self._manual_curve_plane_origin,
            self._manual_curve_plane_normal,
            self._manual_curve_plane_type,
            self._manual_curve_plane_label,
            self._manual_curve_source_section_plane_id,
        ) = self._manual_curve_work_plane_for_curve(curve)
        self._manual_curve_active = True
        self._manual_curve_edit_active = True
        self._manual_curve_edit_curve_id = curve.id
        self._manual_curve_selected_control_point_index = None
        self._manual_curve_hover_control_point_index = None
        self._manual_curve_drag_active = False
        self._manual_curve_placing_enabled = False
        self._manual_curve_add_point_active = False
        self._manual_curve_insert_point_active = False
        self._manual_curve_left_press_position = None
        self._manual_curve_left_dragged = False
        self._clear_manual_curve_preview_state()
        self._load_manual_curve_edit_working_copy(curve, control_data=control_data)
        self._set_active_workbench("Manual RE", set_status=False)
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(status)
        self._sync_workflow_ui()

    def _load_manual_curve_edit_working_copy(
        self,
        curve: StoredCurve,
        *,
        control_data: ManualCurveControlData | None = None,
    ) -> bool:
        control_data = control_data or self._manual_curve_control_data_for_curve(curve)
        if control_data is None:
            return False

        self._manual_curve_points = [
            np.asarray(point, dtype=float).reshape(3)
            for point in np.asarray(control_data.control_points, dtype=float).reshape((-1, 3))
        ]
        self._manual_curve_closed = bool(control_data.is_closed)
        self._manual_curve_curve_method = str(control_data.curve_method)
        self._manual_curve_sample_count = int(control_data.sample_count)
        self._set_manual_curve_type_label(self._manual_curve_curve_method)
        metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
        snap_to_mesh = (
            bool(metadata.get("snap_to_mesh"))
            or str(metadata.get("snap_mode", "")).strip().lower() == "mesh"
        )
        self.manual_curve_snap_to_mesh.set(snap_to_mesh)
        self._manual_curve_snap_point_count = len(self._manual_curve_points) if snap_to_mesh else 0
        self._manual_curve_snap_flags = [snap_to_mesh for _point in self._manual_curve_points]
        self._manual_curve_snap_triangle_indices = self._manual_curve_metadata_list(
            metadata,
            "snap_triangle_indices",
            default=None,
        )
        self._manual_curve_snap_normals = self._manual_curve_metadata_list(
            metadata,
            "snap_normals",
            default=None,
        )
        return True

    def _manual_curve_control_data_for_curve(
        self,
        curve: StoredCurve,
    ) -> ManualCurveControlData | None:
        control_data = parse_manual_curve_metadata(curve)
        if control_data is not None:
            return control_data

        points = self._finite_points(curve.original_points)
        if points is None:
            points = self._finite_points(curve.fitted_points)
        if points is None:
            return None

        return ManualCurveControlData(
            control_points=points,
            is_closed=bool(curve.is_closed),
            curve_method="polyline",
            sample_count=DEFAULT_MANUAL_CURVE_SAMPLE_COUNT,
        )

    @staticmethod
    def _manual_curve_metadata_list(
        metadata: dict[str, object],
        key: str,
        *,
        default: object,
    ) -> list[object]:
        value = metadata.get(key)
        if not isinstance(value, list):
            return []
        return list(value)

    def _manual_curve_work_plane_for_curve(
        self,
        curve: StoredCurve,
    ) -> tuple[np.ndarray, np.ndarray, str, str, str | None]:
        metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
        source_plane_id = metadata.get("source_section_plane_id") or curve.plane_id
        if source_plane_id:
            for plane in self.app_state.section_collection.planes:
                if plane.id == str(source_plane_id):
                    return (
                        np.asarray(plane_origin(plane), dtype=float).reshape(3),
                        np.asarray(plane_normal(plane), dtype=float).reshape(3),
                        "section_plane",
                        plane.name or "Section Plane",
                        plane.id,
                    )
        return self._manual_curve_work_plane()

    @staticmethod
    def _is_editable_manual_curve(curve: StoredCurve) -> bool:
        metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
        creation_type = str(metadata.get("creation_type", "")).strip().lower()
        return bool(
            creation_type in {
                "manual",
                "curve_on_mesh",
                "region_boundary",
                "projected_curve",
                "rebuilt_curve",
            }
            or "control_points" in metadata
            or is_manual_curve_like(curve)
        )

    def _handle_manual_curve_shortcut(self, key: str) -> None:
        if self._manual_curve_edit_active:
            if key in {"Escape", "Esc"}:
                if self._cancel_manual_curve_subaction(status="Manual Curve: action cancelled"):
                    return
                self.done_manual_curve_editing()
                return
            if key == "Enter":
                self.apply_manual_curve_edits()
                return
            if key == "Backspace":
                self.delete_selected_manual_curve_point()
                return
            if key == "C":
                self._toggle_manual_curve_closed()
                return

        if key in {"Escape", "Esc"}:
            self._cancel_manual_curve_mode(status="Manual curve cancelled")
            return
        if key == "Enter":
            self._confirm_manual_curve()
            return
        if key == "Backspace":
            self._remove_last_manual_curve_point()
            return
        if key == "C":
            self._toggle_manual_curve_closed()

    def _prepare_manual_curve_preview_for_click(
        self,
        x_position: int,
        y_position: int,
    ) -> bool:
        if not self._manual_curve_preview_enabled():
            return False
        point, valid, snaps_to_mesh, triangle_index, normal = (
            self._manual_curve_preview_candidate_from_screen(x_position, y_position)
        )
        if not valid or point is None:
            self._set_manual_curve_preview_state(
                valid=False,
                snaps_to_mesh=snaps_to_mesh,
            )
            return False
        self._set_manual_curve_preview_state(
            point=point,
            valid=True,
            snaps_closed=should_snap_closed_to_first_point(
                self._manual_curve_points,
                point,
                model_extent=self._manual_curve_model_extent(),
            ),
            snaps_to_mesh=snaps_to_mesh,
            triangle_index=triangle_index,
            normal=normal,
        )
        return True

    def _manual_curve_click_miss_status(self) -> str:
        if bool(self.manual_curve_snap_to_mesh.get()):
            return "Manual Curve: no mesh under cursor."
        return "Manual Curve: could not place point on work plane"

    def _place_manual_curve_point(self, x_position: int, y_position: int) -> None:
        if not self._prepare_manual_curve_preview_for_click(x_position, y_position):
            self.status_text.set(self._manual_curve_click_miss_status())
            self._sync_workflow_ui()
            return

        point_array = self._manual_curve_preview_point
        if point_array is None:
            self.status_text.set(self._manual_curve_click_miss_status())
            self._sync_workflow_ui()
            return
        if self._manual_curve_preview_snaps_closed:
            self._snap_manual_curve_closed_to_first_point(point_array)
            self._clear_manual_curve_preview_state()
            return

        snapped = bool(self._manual_curve_preview_snaps_to_mesh)
        triangle_index = self._manual_curve_preview_triangle_index
        normal = self._manual_curve_preview_normal
        self._clear_manual_curve_preview_state()
        self._append_manual_curve_point(
            point_array,
            snapped=snapped,
            triangle_index=triangle_index,
            normal=normal,
        )
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(self._manual_curve_status())
        self._sync_workflow_ui()

    def _place_manual_curve_mesh_point(self, x_position: int, y_position: int) -> None:
        pick_result = self.viewport.pick_mesh_at_screen_point(int(x_position), int(y_position))
        if not bool(getattr(pick_result, "hit", False)):
            self.status_text.set("No mesh under cursor.")
            self._sync_workflow_ui()
            return

        position = getattr(pick_result, "position", None)
        if position is None:
            self.status_text.set("No mesh under cursor.")
            self._sync_workflow_ui()
            return

        try:
            point_array = np.asarray(position, dtype=float).reshape(3)
        except (TypeError, ValueError):
            self.status_text.set("No mesh under cursor.")
            self._sync_workflow_ui()
            return
        if not np.all(np.isfinite(point_array)):
            self.status_text.set("No mesh under cursor.")
            self._sync_workflow_ui()
            return

        if self._snap_manual_curve_closed_to_first_point(point_array):
            self._clear_manual_curve_preview_state()
            return

        triangle_index = getattr(pick_result, "triangle_index", None)
        try:
            triangle_value = None if triangle_index is None else int(triangle_index)
        except (TypeError, ValueError):
            triangle_value = None
        normal_value = self._manual_curve_pick_normal_value(
            getattr(pick_result, "normal", None)
        )
        self._clear_manual_curve_preview_state()
        self._append_manual_curve_point(
            point_array,
            snapped=True,
            triangle_index=triangle_value,
            normal=normal_value,
        )
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(self._manual_curve_status())
        self._sync_workflow_ui()

    def _handle_manual_curve_edit_click(
        self,
        x_position: int,
        y_position: int,
        *,
        ctrl_pressed: bool,
    ) -> None:
        if self._manual_curve_add_point_active:
            self._add_manual_curve_edit_point(int(x_position), int(y_position))
            return
        if self._manual_curve_insert_point_active:
            self._insert_manual_curve_edit_point(int(x_position), int(y_position))
            return
        self._select_manual_curve_control_point(int(x_position), int(y_position))

    def _manual_curve_point_from_screen(
        self,
        x_position: int,
        y_position: int,
        *,
        snap_to_mesh: bool,
    ) -> np.ndarray | None:
        if bool(snap_to_mesh):
            pick_result = self.viewport.pick_mesh_at_screen_point(int(x_position), int(y_position))
            if not bool(getattr(pick_result, "hit", False)):
                self.status_text.set("No mesh under cursor.")
                self._sync_workflow_ui()
                return None
            position = getattr(pick_result, "position", None)
            if position is None:
                self.status_text.set("No mesh under cursor.")
                self._sync_workflow_ui()
                return None
            try:
                point_array = np.asarray(position, dtype=float).reshape(3)
            except (TypeError, ValueError):
                self.status_text.set("No mesh under cursor.")
                self._sync_workflow_ui()
                return None
        else:
            point = self.viewport.screen_point_to_plane(
                int(x_position),
                int(y_position),
                self._manual_curve_plane_origin,
                self._manual_curve_plane_normal,
            )
            if point is None:
                self.status_text.set("Manual Curve: could not place point on work plane")
                self._sync_workflow_ui()
                return None
            try:
                point_array = np.asarray(point, dtype=float).reshape(3)
            except (TypeError, ValueError):
                self.status_text.set("Manual Curve: could not place point on work plane")
                self._sync_workflow_ui()
                return None

        if not np.all(np.isfinite(point_array)):
            self.status_text.set("Manual Curve: could not place point on work plane")
            self._sync_workflow_ui()
            return None
        return point_array

    def _add_manual_curve_edit_point(self, x_position: int, y_position: int) -> None:
        if not self._prepare_manual_curve_preview_for_click(x_position, y_position):
            self.status_text.set(self._manual_curve_click_miss_status())
            self._sync_workflow_ui()
            return

        point = self._manual_curve_preview_point
        if point is None:
            self.status_text.set(self._manual_curve_click_miss_status())
            self._sync_workflow_ui()
            return
        if self._manual_curve_preview_snaps_closed:
            self._snap_manual_curve_closed_to_first_point(point, edit_status=True)
            self._manual_curve_add_point_active = False
            self._manual_curve_placing_enabled = False
            self._clear_manual_curve_preview_state()
            return

        snapped = bool(self._manual_curve_preview_snaps_to_mesh)
        triangle_index = self._manual_curve_preview_triangle_index
        normal = self._manual_curve_preview_normal
        self._clear_manual_curve_preview_state()
        self._append_manual_curve_point(
            point,
            snapped=snapped,
            triangle_index=triangle_index,
            normal=normal,
        )
        self._manual_curve_selected_control_point_index = len(self._manual_curve_points) - 1
        self._manual_curve_add_point_active = False
        self._manual_curve_placing_enabled = False
        self._refresh_viewport(reset_camera=False)
        self.status_text.set("Point added. Add Point mode off.")
        self._sync_workflow_ui()

    def _insert_manual_curve_edit_point(self, x_position: int, y_position: int) -> None:
        if not self._prepare_manual_curve_preview_for_click(x_position, y_position):
            self.status_text.set(self._manual_curve_click_miss_status())
            self._sync_workflow_ui()
            return

        point = self._manual_curve_preview_point
        if point is None:
            self.status_text.set(self._manual_curve_click_miss_status())
            self._sync_workflow_ui()
            return
        if self._manual_curve_preview_snaps_closed:
            self._snap_manual_curve_closed_to_first_point(point, edit_status=True)
            self._manual_curve_insert_point_active = False
            self._manual_curve_placing_enabled = False
            self._clear_manual_curve_preview_state()
            return

        snapped = bool(self._manual_curve_preview_snaps_to_mesh)
        triangle_index = self._manual_curve_preview_triangle_index
        normal = self._manual_curve_preview_normal
        self._clear_manual_curve_preview_state()
        insert_index = self._manual_curve_insert_index_for_point(point)
        self._insert_manual_curve_point(
            insert_index,
            point,
            snapped=snapped,
            triangle_index=triangle_index,
            normal=normal,
        )
        self._manual_curve_selected_control_point_index = insert_index
        self._manual_curve_insert_point_active = False
        self._manual_curve_placing_enabled = False
        self._refresh_viewport(reset_camera=False)
        self.status_text.set("Point inserted. Insert mode off.")
        self._sync_workflow_ui()

    def _manual_curve_insert_index_for_point(self, point: np.ndarray) -> int:
        points = np.asarray(self._manual_curve_points, dtype=float).reshape((-1, 3))
        if len(points) < 2:
            return len(points)

        segment_count = len(points) if self._manual_curve_closed and len(points) >= 3 else len(points) - 1
        best_index = 1
        best_distance = float("inf")
        for segment_index in range(segment_count):
            start = points[segment_index]
            end = points[(segment_index + 1) % len(points)]
            distance = self._distance_to_segment(point, start, end)
            if distance < best_distance:
                best_distance = distance
                best_index = segment_index + 1
        return min(best_index, len(points))

    @staticmethod
    def _distance_to_segment(point: np.ndarray, start: np.ndarray, end: np.ndarray) -> float:
        segment = end - start
        length_squared = float(np.dot(segment, segment))
        if length_squared <= 1e-12:
            return float(np.linalg.norm(point - start))
        projection = float(np.dot(point - start, segment) / length_squared)
        projection = min(max(projection, 0.0), 1.0)
        closest = start + projection * segment
        return float(np.linalg.norm(point - closest))

    def _select_manual_curve_control_point(self, x_position: int, y_position: int) -> None:
        point = self._manual_curve_point_from_screen(
            x_position,
            y_position,
            snap_to_mesh=False,
        )
        if point is None:
            return

        selected_index = self._nearest_manual_curve_control_point_index(point)
        if selected_index is None:
            self._manual_curve_selected_control_point_index = None
            self._refresh_viewport(reset_camera=False)
            self.status_text.set("No control point selected")
            self._sync_workflow_ui()
            return

        self._manual_curve_selected_control_point_index = selected_index
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(f"Selected control point {selected_index + 1}")
        self._sync_workflow_ui()

    def _nearest_manual_curve_control_point_index(self, point: np.ndarray) -> int | None:
        if not self._manual_curve_points:
            return None

        points = np.asarray(self._manual_curve_points, dtype=float).reshape((-1, 3))
        distances = np.linalg.norm(points - np.asarray(point, dtype=float).reshape(3), axis=1)
        nearest_index = int(np.argmin(distances))
        threshold = max(manual_curve_close_threshold(self._manual_curve_model_extent()) * 2.5, 0.025)
        if float(distances[nearest_index]) <= threshold:
            return nearest_index
        return None

    def activate_manual_curve_add_point(self) -> None:
        if not self._manual_curve_edit_active:
            self.status_text.set("Edit a manual curve before adding points.")
            self._sync_workflow_ui()
            return

        self._manual_curve_add_point_active = True
        self._manual_curve_insert_point_active = False
        self._manual_curve_placing_enabled = True
        self.status_text.set("Edit Curve: Add Point active. Click to place next point.")
        self._sync_workflow_ui()

    def activate_manual_curve_insert_point(self) -> None:
        if not self._manual_curve_edit_active:
            self.status_text.set("Edit a manual curve before inserting points.")
            self._sync_workflow_ui()
            return

        self._manual_curve_insert_point_active = True
        self._manual_curve_add_point_active = False
        self._manual_curve_placing_enabled = True
        self.status_text.set("Edit Curve: Insert Point active. Click segment location.")
        self._sync_workflow_ui()

    def delete_selected_manual_curve_point(self) -> None:
        if not self._manual_curve_edit_active:
            self.status_text.set("Edit a manual curve before deleting control points.")
            self._sync_workflow_ui()
            return
        if self._manual_curve_selected_control_point_index is None:
            self.status_text.set("No control point selected")
            self._sync_workflow_ui()
            return

        minimum = 3 if self._manual_curve_closed else 2
        if len(self._manual_curve_points) <= minimum:
            self.status_text.set("Cannot delete point: curve needs more control points")
            self._sync_workflow_ui()
            return

        removed_index = self._manual_curve_selected_control_point_index
        self._manual_curve_points.pop(removed_index)
        if removed_index < len(self._manual_curve_snap_flags):
            was_snapped = self._manual_curve_snap_flags.pop(removed_index)
            if was_snapped:
                self._manual_curve_snap_point_count = max(
                    0,
                    self._manual_curve_snap_point_count - 1,
                )
        if removed_index < len(self._manual_curve_snap_triangle_indices):
            self._manual_curve_snap_triangle_indices.pop(removed_index)
        if removed_index < len(self._manual_curve_snap_normals):
            self._manual_curve_snap_normals.pop(removed_index)
        if removed_index >= len(self._manual_curve_points):
            removed_index = len(self._manual_curve_points) - 1
        self._manual_curve_selected_control_point_index = removed_index
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(f"Deleted control point {removed_index + 1}")
        self._sync_workflow_ui()

    def _snap_manual_curve_closed_to_first_point(
        self,
        point: np.ndarray,
        *,
        edit_status: bool = False,
    ) -> bool:
        if len(self._manual_curve_points) < 3:
            return False

        if not should_snap_closed_to_first_point(
            self._manual_curve_points,
            point,
            model_extent=self._manual_curve_model_extent(),
        ):
            return False

        if self._manual_curve_closed:
            self.status_text.set("Manual Curve: already closed")
        else:
            self._manual_curve_closed = True
            self.status_text.set("Curve closed to first point")
        self._manual_curve_selected_control_point_index = 0 if edit_status else None
        self._clear_manual_curve_preview_state()
        self._refresh_viewport(reset_camera=False)
        self._sync_workflow_ui()
        return True

    def _manual_curve_model_extent(self) -> float | None:
        mesh_object = self.app_state.mesh_object
        if (
            mesh_object is None
            or mesh_object.source_bounds_min is None
            or mesh_object.source_bounds_max is None
        ):
            return None

        minimum_bound, maximum_bound = self._transformed_source_bounds()
        extent = float(
            np.max(
                np.asarray(maximum_bound, dtype=float)
                - np.asarray(minimum_bound, dtype=float)
            )
        )
        return extent if np.isfinite(extent) and extent > 0.0 else None

    def _append_manual_curve_point(
        self,
        point: np.ndarray,
        *,
        snapped: bool,
        triangle_index: int | None = None,
        normal: list[float] | None = None,
    ) -> None:
        self._manual_curve_points.append(np.asarray(point, dtype=float).reshape(3))
        snapped = bool(snapped)
        self._manual_curve_snap_flags.append(snapped)
        self._manual_curve_snap_triangle_indices.append(triangle_index)
        self._manual_curve_snap_normals.append(normal)
        if snapped:
            self._manual_curve_snap_point_count += 1

    def _insert_manual_curve_point(
        self,
        index: int,
        point: np.ndarray,
        *,
        snapped: bool,
        triangle_index: int | None = None,
        normal: list[float] | None = None,
    ) -> None:
        insert_index = min(max(int(index), 0), len(self._manual_curve_points))
        self._manual_curve_points.insert(
            insert_index,
            np.asarray(point, dtype=float).reshape(3),
        )
        snapped = bool(snapped)
        self._manual_curve_snap_flags.insert(insert_index, snapped)
        self._manual_curve_snap_triangle_indices.insert(insert_index, triangle_index)
        self._manual_curve_snap_normals.insert(insert_index, normal)
        if snapped:
            self._manual_curve_snap_point_count += 1

    @staticmethod
    def _manual_curve_pick_normal_value(normal: object) -> list[float] | None:
        if normal is None:
            return None

        try:
            normal_array = np.asarray(normal, dtype=float).reshape(3)
        except (TypeError, ValueError):
            return None
        if not np.all(np.isfinite(normal_array)):
            return None
        return [float(value) for value in normal_array]

    def _remove_last_manual_curve_point(self) -> None:
        if not self._manual_curve_points:
            self.status_text.set("Manual Curve: no pending points")
            self._sync_workflow_ui()
            return

        self._manual_curve_points.pop()
        if self._manual_curve_snap_flags:
            was_snapped = self._manual_curve_snap_flags.pop()
            if was_snapped:
                self._manual_curve_snap_point_count = max(
                    0,
                    self._manual_curve_snap_point_count - 1,
                )
        if self._manual_curve_snap_triangle_indices:
            self._manual_curve_snap_triangle_indices.pop()
        if self._manual_curve_snap_normals:
            self._manual_curve_snap_normals.pop()
        if len(self._manual_curve_points) < 3:
            self._manual_curve_closed = False
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(self._manual_curve_status())
        self._sync_workflow_ui()

    def _toggle_manual_curve_closed(self) -> None:
        if len(self._manual_curve_points) < 3:
            self.status_text.set("Manual Curve: need at least 3 points to close")
            self._sync_workflow_ui()
            return

        self._manual_curve_closed = not self._manual_curve_closed
        self._refresh_viewport(reset_camera=False)
        if self._manual_curve_edit_active:
            self.status_text.set("Curve closed" if self._manual_curve_closed else "Curve opened")
        else:
            self.status_text.set(self._manual_curve_status())
        self._sync_workflow_ui()

    def _confirm_manual_curve(self) -> None:
        if self._manual_curve_edit_active:
            self.apply_manual_curve_edits()
            return

        point_count = len(self._manual_curve_points)
        if self._manual_curve_closed:
            if point_count < 3:
                self.status_text.set("Manual Curve: closed curve needs at least 3 points")
                self._sync_workflow_ui()
                return
        elif point_count < 2:
            self.status_text.set("Manual Curve: open curve needs at least 2 points")
            self._sync_workflow_ui()
            return

        points = np.asarray(self._manual_curve_points, dtype=float).reshape((-1, 3))
        snap_to_mesh = self._manual_curve_snap_point_count > 0
        mesh_object = self.app_state.mesh_object
        curve = build_manual_stored_curve(
            curve_id=f"curve-{uuid4().hex}",
            name=self._next_manual_curve_name(),
            control_points=points,
            is_closed=bool(self._manual_curve_closed),
            creation_type="curve_on_mesh" if snap_to_mesh else "manual",
            snap_to_mesh=snap_to_mesh,
            work_plane_type="mesh" if snap_to_mesh else self._manual_curve_plane_type,
            source_section_plane_id=(
                None if snap_to_mesh else self._manual_curve_source_section_plane_id
            ),
            source_mesh_name=(
                mesh_object.name
                if snap_to_mesh and mesh_object is not None and mesh_object.name
                else None
            ),
            snap_triangle_indices=(
                list(self._manual_curve_snap_triangle_indices)
                if snap_to_mesh
                and any(index is not None for index in self._manual_curve_snap_triangle_indices)
                else None
            ),
            snap_normals=(
                list(self._manual_curve_snap_normals)
                if snap_to_mesh
                and any(normal is not None for normal in self._manual_curve_snap_normals)
                else None
            ),
            curve_method=self._manual_curve_curve_method,
            sample_count=self._manual_curve_sample_count,
        )
        add_curve(self.app_state.curve_collection, curve)
        self._sync_visible_curve_results()
        self.select_curve(curve.id)
        self._push_created_curve_command(curve, command_name="Create Manual Curve")
        self._begin_manual_curve_edit_mode(
            curve,
            status=f"Created {curve.name}. Editing curve.",
        )
        self._set_project_dirty(True)
        self._sync_workflow_ui()

    def apply_manual_curve_edits(self) -> None:
        active_curve = self._active_manual_edit_curve()
        if active_curve is None:
            self.status_text.set("No manual curve is being edited")
            self._sync_workflow_ui()
            return

        point_count = len(self._manual_curve_points)
        if self._manual_curve_closed and point_count < 3:
            self.status_text.set("Manual Curve: closed curve needs at least 3 points")
            self._sync_workflow_ui()
            return
        if not self._manual_curve_closed and point_count < 2:
            self.status_text.set("Manual Curve: open curve needs at least 2 points")
            self._sync_workflow_ui()
            return

        metadata = active_curve.metadata if isinstance(active_curve.metadata, dict) else {}
        snap_to_mesh = bool(self.manual_curve_snap_to_mesh.get())
        before_curve = copy.deepcopy(active_curve)
        updated_curve = build_manual_stored_curve(
            curve_id=active_curve.id,
            name=active_curve.name,
            control_points=np.asarray(self._manual_curve_points, dtype=float).reshape((-1, 3)),
            is_closed=bool(self._manual_curve_closed),
            creation_type=str(
                metadata.get(
                    "creation_type",
                    "curve_on_mesh" if snap_to_mesh else "manual",
                )
            ),
            snap_to_mesh=snap_to_mesh,
            work_plane_type=str(
                metadata.get(
                    "work_plane_type",
                    "mesh" if snap_to_mesh else self._manual_curve_plane_type,
                )
            ),
            source_section_plane_id=(
                None
                if snap_to_mesh
                else metadata.get("source_section_plane_id")
                or self._manual_curve_source_section_plane_id
            ),
            source_mesh_name=metadata.get("source_mesh_name"),
            snap_triangle_indices=metadata.get("snap_triangle_indices"),
            snap_normals=metadata.get("snap_normals"),
            curve_method=self._manual_curve_curve_method,
            sample_count=self._manual_curve_sample_count,
        )
        active_curve.original_points = updated_curve.original_points
        active_curve.fitted_points = updated_curve.fitted_points
        active_curve.mean_error = updated_curve.mean_error
        active_curve.max_error = updated_curve.max_error
        active_curve.is_closed = updated_curve.is_closed
        active_curve.metadata = self._merged_manual_curve_edit_metadata(
            original_metadata=metadata,
            updated_metadata=updated_curve.metadata,
            updated_points=updated_curve.fitted_points,
            is_closed=bool(updated_curve.is_closed),
        )
        refresh_curve_diagnostics(active_curve)
        after_curve = copy.deepcopy(active_curve)
        self._push_undo_command(
            CallbackUndoCommand(
                "Edit Manual Curve",
                undo_action=lambda: self._restore_manual_curve_snapshot(
                    copy.deepcopy(before_curve)
                ),
                redo_action=lambda: self._restore_manual_curve_snapshot(
                    copy.deepcopy(after_curve)
                ),
            )
        )
        self._sync_visible_curve_results()
        self._sync_curve_context_from_active_curve()
        self._refresh_viewport(reset_camera=False)
        self.status_text.set("Curve edits saved")
        self._set_project_dirty(True)
        self._sync_workflow_ui()

    def _merged_manual_curve_edit_metadata(
        self,
        *,
        original_metadata: dict[str, object],
        updated_metadata: dict[str, object],
        updated_points: np.ndarray,
        is_closed: bool,
    ) -> dict[str, object]:
        metadata = dict(updated_metadata)
        creation_type = str(original_metadata.get("creation_type", "")).strip().lower()
        if creation_type not in {"region_boundary", "projected_curve", "rebuilt_curve"}:
            return metadata

        preserve_keys = (
            "creation_type",
            "source_curve_id",
            "source_curve_name",
            "source_curve_creation_type",
            "source_region_id",
            "source_region_name",
            "source_mesh_name",
            "region_triangle_count",
            "source_region_triangle_count",
            "boundary_index",
            "projection_projected_count",
            "projection_missed_count",
            "projection_mean_distance",
            "projection_max_distance",
            "projection_warnings",
            "rebuild_source_point_count",
            "rebuild_target_control_point_count",
            "rebuild_method",
            "rebuild_warnings",
        )
        for key in preserve_keys:
            if key in original_metadata:
                metadata[key] = original_metadata[key]
        metadata["creation_type"] = creation_type
        if creation_type == "region_boundary":
            metadata["boundary_point_count"] = int(len(np.asarray(updated_points).reshape((-1, 3))))
            metadata["boundary_closed"] = bool(is_closed)
            metadata["boundary_perimeter"] = _polyline_perimeter(updated_points, closed=is_closed)
        return metadata

    def _active_manual_edit_curve(self) -> StoredCurve | None:
        if self._manual_curve_edit_curve_id is None:
            return None
        for curve in self.app_state.curve_collection.curves:
            if curve.id == self._manual_curve_edit_curve_id:
                return curve
        return None

    def _restore_manual_curve_snapshot(self, snapshot: StoredCurve) -> None:
        for index, curve in enumerate(self.app_state.curve_collection.curves):
            if curve.id != snapshot.id:
                continue
            restored = copy.deepcopy(snapshot)
            self.app_state.curve_collection.curves[index] = restored
            set_active_curve(self.app_state.curve_collection, restored.id)
            refresh_curve_diagnostics(restored)
            if (
                self._manual_curve_edit_active
                and self._manual_curve_edit_curve_id == restored.id
            ):
                self._load_manual_curve_edit_working_copy(restored)
            return

    def cancel_manual_curve_edit(self) -> None:
        active_curve = self._active_manual_edit_curve()
        if active_curve is None:
            self.done_manual_curve_editing(status="Manual curve editing cancelled")
            return
        self._begin_manual_curve_edit_mode(active_curve, status="Curve edit cancelled")

    def done_manual_curve_editing(self, *, status: str = "Manual curve editing finished") -> None:
        selected_curve_id = self._manual_curve_edit_curve_id
        self._clear_manual_curve_state()
        if selected_curve_id is not None:
            try:
                set_active_curve(self.app_state.curve_collection, selected_curve_id)
            except ValueError:
                pass
        self._sync_curve_context_from_active_curve()
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(status)
        self._sync_workflow_ui()

    def _next_manual_curve_name(self) -> str:
        existing_names = {
            curve.name for curve in self.app_state.curve_collection.curves
        }
        index = 1
        while f"Manual Curve {index}" in existing_names:
            index += 1
        return f"Manual Curve {index}"

    def _cancel_manual_curve_mode(self, *, status: str | None = None) -> None:
        if self._manual_curve_edit_active:
            self.cancel_manual_curve_edit()
            return

        self._clear_manual_curve_state()
        self._refresh_viewport(reset_camera=False)
        if status is not None:
            self.status_text.set(status)
        self._sync_workflow_ui()

    def _cancel_manual_curve_subaction(self, *, status: str) -> bool:
        if self._manual_curve_drag_active:
            self._manual_curve_drag_active = False
            self._clear_manual_curve_preview_state()
            self.status_text.set(status)
            self._sync_workflow_ui()
            return True
        if self._manual_curve_add_point_active or self._manual_curve_insert_point_active:
            self._manual_curve_add_point_active = False
            self._manual_curve_insert_point_active = False
            self._manual_curve_placing_enabled = False
            self._clear_manual_curve_preview_state()
            self.status_text.set(status)
            self._sync_workflow_ui()
            return True
        return False

    def _on_manual_curve_type_changed(self, _event: object | None = None) -> None:
        self._manual_curve_curve_method = self._manual_curve_method_from_label()
        if self._manual_curve_active:
            self._refresh_viewport(reset_camera=False)
            self.status_text.set(f"Curve type: {self.manual_curve_type_text.get()}")
        self._sync_workflow_ui()

    def _manual_curve_method_from_label(self) -> str:
        value = self.manual_curve_type_text.get().strip().lower()
        if value == "polyline":
            return "polyline"
        return DEFAULT_MANUAL_CURVE_METHOD

    def _set_manual_curve_type_label(self, method: str) -> None:
        label = "Polyline" if str(method).strip().lower() == "polyline" else "Smooth Curve"
        self.manual_curve_type_text.set(label)

    def _show_manual_curve_context_menu(self, x_position: int, y_position: int) -> None:
        menu = self._build_manual_curve_context_menu()
        self._manual_curve_context_menu = menu
        try:
            root_x = int(self.root.winfo_pointerx())
            root_y = int(self.root.winfo_pointery())
        except TclError:
            root_x = int(x_position)
            root_y = int(y_position)
        try:
            menu.tk_popup(root_x, root_y)
        except TclError:
            return
        finally:
            try:
                menu.grab_release()
            except TclError:
                pass

    def _build_manual_curve_context_menu(self) -> Menu:
        menu = Menu(self.root, tearoff=False)
        actions: list[str] = []

        def add_action(label: str, command: object) -> None:
            actions.append(label)
            menu.add_command(label=label, command=command)

        add_action("Apply / Finish Current Curve", self._apply_or_finish_manual_curve_context_action)
        add_action("Cancel Current Action", self._cancel_manual_curve_context_action)
        add_action("Restart Current Curve", self._restart_manual_curve_context_action)
        add_action("Done Editing", self.done_manual_curve_editing)
        add_action("Toggle Closed", self._toggle_manual_curve_closed)
        if self._manual_curve_selected_control_point_index is not None:
            add_action("Delete Selected Point", self.delete_selected_manual_curve_point)
        self._manual_curve_last_context_actions = tuple(actions)
        return menu

    def _apply_or_finish_manual_curve_context_action(self) -> None:
        if self._manual_curve_edit_active:
            self.apply_manual_curve_edits()
        else:
            self._confirm_manual_curve()

    def _cancel_manual_curve_context_action(self) -> None:
        if self._cancel_manual_curve_subaction(status="Manual Curve: action cancelled"):
            return
        if self._manual_curve_edit_active:
            self.cancel_manual_curve_edit()
            return
        if self._manual_curve_points and not self._confirm_discard_manual_curve_work(
            "Discard current manual curve?"
        ):
            return
        self._cancel_manual_curve_mode(status="Manual curve cancelled")

    def _restart_manual_curve_context_action(self) -> None:
        if not self._confirm_discard_manual_curve_work("Restart current manual curve?"):
            return
        self.start_manual_curve_mode()
        self.status_text.set("Manual curve restarted")
        self._sync_workflow_ui()

    def _confirm_discard_manual_curve_work(self, message: str) -> bool:
        if not self._manual_curve_points and not self._manual_curve_edit_active:
            return True
        return bool(
            messagebox.askyesno(
                "Manual Curve",
                message,
                parent=self.root,
            )
        )

    def _clear_manual_curve_state(self, *, reset_snap: bool = False) -> None:
        self._manual_curve_active = False
        self._manual_curve_edit_active = False
        self._manual_curve_edit_curve_id = None
        self._manual_curve_selected_control_point_index = None
        self._manual_curve_hover_control_point_index = None
        self._manual_curve_drag_active = False
        self._manual_curve_placing_enabled = True
        self._manual_curve_add_point_active = False
        self._manual_curve_insert_point_active = False
        self._manual_curve_curve_method = DEFAULT_MANUAL_CURVE_METHOD
        self._manual_curve_sample_count = DEFAULT_MANUAL_CURVE_SAMPLE_COUNT
        self._manual_curve_left_press_position = None
        self._manual_curve_left_dragged = False
        self._manual_curve_points = []
        self._manual_curve_closed = False
        self._manual_curve_plane_origin = np.asarray([0.0, 0.0, 0.0], dtype=float)
        self._manual_curve_plane_normal = np.asarray([0.0, 0.0, 1.0], dtype=float)
        self._manual_curve_plane_type = "world_xy"
        self._manual_curve_plane_label = "world XY plane"
        self._manual_curve_source_section_plane_id = None
        self._manual_curve_snap_point_count = 0
        self._manual_curve_snap_flags = []
        self._manual_curve_snap_triangle_indices = []
        self._manual_curve_snap_normals = []
        self._clear_manual_curve_preview_state()
        if reset_snap:
            self.manual_curve_snap_to_mesh.set(False)

    def _manual_curve_status(self) -> str:
        point_count = len(self._manual_curve_points)
        point_label = "point" if point_count == 1 else "points"
        closed_label = "closed" if self._manual_curve_closed else "open"
        snap_label = (
            "Snap to Mesh: On"
            if bool(self.manual_curve_snap_to_mesh.get())
            else "Snap to Mesh: Off"
        )
        if self._manual_curve_edit_active:
            if self._manual_curve_add_point_active:
                action_label = "Add Point"
            elif self._manual_curve_insert_point_active:
                action_label = "Insert Point"
            else:
                action_label = "Select Point"
            return (
                "Manual Curve Edit: "
                f"{point_count} {point_label}, {closed_label}; "
                f"{snap_label}; action: {action_label}"
            )
        return (
            "Manual Curve: click to place points; "
            f"Manual Curve: using {self._manual_curve_plane_label} "
            f"({point_count} {point_label}, {closed_label}; {snap_label})"
        )

    def _curve_repair_tolerance(self) -> float:
        mesh_object = self.app_state.mesh_object
        if (
            mesh_object is None
            or mesh_object.source_bounds_min is None
            or mesh_object.source_bounds_max is None
        ):
            return DEFAULT_CURVE_REPAIR_TOLERANCE

        bounds_min = np.asarray(mesh_object.source_bounds_min, dtype=float)
        bounds_max = np.asarray(mesh_object.source_bounds_max, dtype=float)
        extent = float(np.max(bounds_max - bounds_min))
        if extent <= 0.0 or not np.isfinite(extent):
            return DEFAULT_CURVE_REPAIR_TOLERANCE
        return max(DEFAULT_CURVE_REPAIR_TOLERANCE, extent * 0.002)

    def _curve_simplify_tolerance(self, curve: StoredCurve) -> float:
        refresh_curve_diagnostics(curve)
        extent = float(curve.bounding_box_size)
        if extent <= 0.0 or not np.isfinite(extent):
            return DEFAULT_CURVE_SIMPLIFY_TOLERANCE
        return max(DEFAULT_CURVE_SIMPLIFY_TOLERANCE, extent * 0.002)

    def delete_selected_curve(self) -> None:
        active_curve = self._active_curve()
        if active_curve is None:
            self.status_text.set("No selection")
            return

        removed_name = active_curve.name or "Curve"
        delete_targets = self._delete_targets_for_node_ids((curve_node_id(active_curve.id),))
        undo_command = self._delete_undo_command_for_targets(delete_targets)
        self._apply_delete_targets(delete_targets)
        if undo_command is not None:
            self._push_undo_command(undo_command)
        self._sync_visible_curve_results()
        self._sync_surface_context_from_active_surface()
        self._select_delete_fallback(delete_targets)
        self.status_text.set(f"Deleted: {removed_name}")
        self._set_project_dirty(True)

    def _active_surface(self) -> SurfacePatch | None:
        return get_active_surface(self.app_state.surface_collection)

    def _build_visible_surface_previews(self) -> list[SurfacePreviewMesh]:
        previews: list[SurfacePreviewMesh] = []
        curves = self.app_state.curve_collection.curves
        for surface in self.app_state.surface_collection.surfaces:
            if not surface.visible:
                continue

            preview = build_surface_preview_mesh(surface, curves)
            if preview is not None:
                previews.append(
                    SurfacePreviewMesh(
                        vertices=preview.vertices,
                        faces=preview.faces,
                        source_surface_id=preview.source_surface_id,
                        selected=bool(preview.selected),
                        opacity=self._surface_display_opacity(surface),
                        wireframe_overlay=self._surface_wireframe_overlay(surface),
                    )
                )
        return previews

    def _clear_surfaces_for_curve_ids(self, curve_ids: list[str]) -> None:
        for curve_id in curve_ids:
            clear_surfaces_for_curve(self.app_state.surface_collection, curve_id)

    def hide_selected_curves(self) -> None:
        selected_ids = set(self.app_state.curve_collection.selected_curve_ids)
        if not selected_ids:
            self.status_text.set("No selected curves")
            return

        node_ids = {curve_node_id(curve_id) for curve_id in selected_ids}
        before = self._visibility_snapshot(node_ids)
        for curve in self.app_state.curve_collection.curves:
            if curve.id in selected_ids:
                curve.visible = False
        after = self._visibility_snapshot(node_ids)
        self._push_visibility_command("Hide Visibility", before, after)
        self._sync_curve_context_from_active_curve()
        self._sync_visible_curve_results()
        self._refresh_viewport(reset_camera=False)
        count = len(selected_ids)
        self.status_text.set(
            "Hidden selected curve" if count == 1 else f"Hidden {count} selected curves"
        )
        self._set_project_dirty(True)

    def hide_unselected_curves(self) -> None:
        selected_ids = set(self.app_state.curve_collection.selected_curve_ids)
        if not selected_ids:
            self.status_text.set("No selected curves")
            return

        node_ids = {
            curve_node_id(curve.id)
            for curve in self.app_state.curve_collection.curves
            if curve.id not in selected_ids
        }
        before = self._visibility_snapshot(node_ids)
        hidden_count = 0
        for curve in self.app_state.curve_collection.curves:
            if curve.id not in selected_ids and curve.visible:
                hidden_count += 1
                curve.visible = False
        after = self._visibility_snapshot(node_ids)
        self._push_visibility_command("Hide Visibility", before, after)
        self._sync_curve_context_from_active_curve()
        self._sync_visible_curve_results()
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(
            "No unselected visible curves"
            if hidden_count == 0
            else f"Hidden {hidden_count} unselected curves"
        )
        self._set_project_dirty(True)

    def show_all_curves(self) -> None:
        if not self.app_state.curve_collection.curves:
            self.status_text.set("No curves available")
            return

        node_ids = {
            curve_node_id(curve.id)
            for curve in self.app_state.curve_collection.curves
        }
        before = self._visibility_snapshot(node_ids)
        for curve in self.app_state.curve_collection.curves:
            curve.visible = True
        after = self._visibility_snapshot(node_ids)
        self._push_visibility_command("Show Visibility", before, after)
        self._sync_curve_context_from_active_curve()
        self._sync_visible_curve_results()
        self._refresh_viewport(reset_camera=False)
        self.status_text.set("All curves visible")
        self._set_project_dirty(True)

    def select_tiny_curves(self) -> None:
        tiny_curves = self._tiny_curves()
        if not self.app_state.curve_collection.curves:
            self.status_text.set("No curves available")
            return
        if not tiny_curves:
            self.status_text.set("No tiny curves found")
            return

        tiny_curve_ids = [curve.id for curve in tiny_curves]
        self.select_curves(tiny_curve_ids, active_curve_id=tiny_curve_ids[0])
        count = len(tiny_curve_ids)
        self.status_text.set(
            "Selected tiny curve" if count == 1 else f"Selected {count} tiny curves"
        )

    def hide_tiny_curves(self) -> None:
        tiny_curves = self._tiny_curves()
        if not self.app_state.curve_collection.curves:
            self.status_text.set("No curves available")
            return
        if not tiny_curves:
            self.status_text.set("No tiny curves found")
            return

        node_ids = {curve_node_id(curve.id) for curve in tiny_curves}
        before = self._visibility_snapshot(node_ids)
        hidden_count = 0
        for curve in tiny_curves:
            if curve.visible:
                curve.visible = False
                hidden_count += 1
        after = self._visibility_snapshot(node_ids)
        self._push_visibility_command("Hide Visibility", before, after)
        self._sync_curve_context_from_active_curve()
        self._sync_visible_curve_results()
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(
            "No visible tiny curves"
            if hidden_count == 0
            else (
                "Hidden tiny curve"
                if hidden_count == 1
                else f"Hidden {hidden_count} tiny curves"
            )
        )
        if hidden_count:
            self._set_project_dirty(True)

    def delete_tiny_curves(self) -> None:
        tiny_curves = self._tiny_curves()
        if not self.app_state.curve_collection.curves:
            self.status_text.set("No curves available")
            return
        if not tiny_curves:
            self.status_text.set("No tiny curves found")
            return

        tiny_curve_ids = [curve.id for curve in tiny_curves]
        delete_targets = self._delete_targets_for_node_ids(
            tuple(curve_node_id(curve_id) for curve_id in tiny_curve_ids)
        )
        undo_command = self._delete_undo_command_for_targets(delete_targets)
        self._apply_delete_targets(delete_targets)
        if undo_command is not None:
            self._push_undo_command(undo_command)

        self._sync_visible_curve_results()
        self._sync_surface_context_from_active_surface()
        count = len(tiny_curve_ids)
        status = (
            "Deleted tiny curve" if count == 1 else f"Deleted {count} tiny curves"
        )
        self._select_delete_fallback(delete_targets)
        self.status_text.set(status)
        self._set_project_dirty(True)

    def _tiny_curves(self) -> list[StoredCurve]:
        for curve in self.app_state.curve_collection.curves:
            refresh_curve_diagnostics(curve)
        return get_tiny_curves(self.app_state.curve_collection)

    def _sync_surface_context_from_active_surface(self) -> None:
        active_surface = self._active_surface()
        if active_surface is None:
            self._syncing_surface_display_controls = True
            try:
                self.surface_visible.set(False)
                self.surface_name_text.set("(none)")
                self.surface_type_text.set("(none)")
                self.surface_preview_mode_text.set("(none)")
                self.surface_source_curve_count_text.set("0")
                self.surface_source_curve_names_text.set("(none)")
                self.surface_preview_available_text.set("(none)")
                self.surface_preview_reason_text.set("(none)")
                self.surface_preview_warning_text.set("(none)")
                self.surface_grid_size_text.set("(none)")
                self.surface_planarity_error_text.set("(none)")
                self.surface_resampled_point_count_text.set("(none)")
                self.surface_reversed_second_curve_text.set("(none)")
                self.surface_seam_shift_applied_text.set("(none)")
                self.surface_average_pair_distance_text.set("(none)")
                self.surface_max_pair_distance_text.set("(none)")
                self.surface_validation_warnings_text.set("(none)")
                self.surface_validation_errors_text.set("(none)")
                self.surface_opacity.set(SURFACE_PREVIEW_DEFAULT_OPACITY)
                self.surface_opacity_text.set(f"{SURFACE_PREVIEW_DEFAULT_OPACITY:.2f}")
                self.surface_wireframe_overlay.set(True)
                self.surface_metadata_text.set("(none)")
            finally:
                self._syncing_surface_display_controls = False
            return

        metadata = active_surface.metadata
        opacity = self._surface_display_opacity(active_surface)
        self._syncing_surface_display_controls = True
        try:
            self.surface_visible.set(bool(active_surface.visible))
            self.surface_name_text.set(active_surface.name)
            self.surface_type_text.set(active_surface.surface_type)
            self.surface_preview_mode_text.set(
                str(metadata.get("preview_mode") or "(none)")
            )
            self.surface_source_curve_count_text.set(str(len(active_surface.source_curve_ids)))
            self.surface_source_curve_names_text.set(
                self._surface_source_curve_names_summary(active_surface)
            )
            self.surface_preview_available_text.set(
                self._surface_preview_available_summary(metadata)
            )
            self.surface_preview_reason_text.set(
                str(metadata.get("preview_reason") or "(none)")
            )
            self.surface_preview_warning_text.set(
                str(metadata.get("preview_warning") or "(none)")
            )
            self.surface_grid_size_text.set(self._surface_grid_size_text(metadata))
            self.surface_planarity_error_text.set(
                self._surface_metadata_float_text(
                    metadata,
                    "planarity_error"
                    if "planarity_error" in metadata
                    else "source_curve_planarity_error",
                )
            )
            self.surface_resampled_point_count_text.set(
                self._surface_metadata_int_text(metadata, "resampled_point_count")
            )
            self.surface_reversed_second_curve_text.set(
                self._surface_metadata_bool_text(metadata, "reversed_second_curve")
            )
            self.surface_seam_shift_applied_text.set(
                self._surface_metadata_bool_text(metadata, "seam_shift_applied")
            )
            self.surface_average_pair_distance_text.set(
                self._surface_metadata_float_text(metadata, "average_pair_distance")
            )
            self.surface_max_pair_distance_text.set(
                self._surface_metadata_float_text(metadata, "max_pair_distance")
            )
            self.surface_validation_warnings_text.set(
                self._surface_metadata_list_text(
                    metadata.get("source_curve_validation_warnings")
                )
            )
            self.surface_validation_errors_text.set(
                self._surface_metadata_list_text(
                    metadata.get("source_curve_validation_errors")
                )
            )
            self.surface_opacity.set(opacity)
            self.surface_opacity_text.set(f"{opacity:.2f}")
            self.surface_wireframe_overlay.set(self._surface_wireframe_overlay(active_surface))
            self.surface_metadata_text.set(self._surface_metadata_summary(metadata))
        finally:
            self._syncing_surface_display_controls = False

    def _on_surface_name_changed(self, event: object | None = None) -> None:
        active_surface = self._active_surface()
        if active_surface is None:
            return

        candidate = self._validated_name_candidate(
            self.surface_name_text,
            active_surface.name,
            self.surface_name_entry,
            event,
        )
        if candidate is None or candidate == active_surface.name:
            return

        old_name = active_surface.name
        active_surface.name = candidate
        self._push_rename_command(
            surface_node_id(active_surface.id),
            "Rename Surface",
            old_name,
            candidate,
        )
        self._refresh_scene_browser()
        self.status_text.set(f"Selected: {active_surface.name}")
        self._set_project_dirty(True)

    @staticmethod
    def _surface_preview_available_summary(metadata: dict[str, object]) -> str:
        if "preview_available" not in metadata:
            return "(unknown)"
        return "Yes" if bool(metadata["preview_available"]) else "No"

    @staticmethod
    def _surface_grid_size_text(metadata: dict[str, object]) -> str:
        u_count = metadata.get("grid_u_count")
        v_count = metadata.get("grid_v_count")
        if u_count is None or v_count is None:
            return "(none)"
        try:
            return f"{int(u_count)} x {int(v_count)}"
        except (TypeError, ValueError):
            return f"{u_count} x {v_count}"

    @staticmethod
    def _surface_metadata_list_text(value: object) -> str:
        if isinstance(value, list):
            items = [str(item) for item in value if str(item)]
            return "; ".join(items) if items else "(none)"
        if value:
            return str(value)
        return "(none)"

    @staticmethod
    def _surface_metadata_int_text(metadata: dict[str, object], key: str) -> str:
        value = metadata.get(key)
        if value is None:
            return "(none)"
        try:
            return str(int(value))
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _surface_metadata_bool_text(metadata: dict[str, object], key: str) -> str:
        if key not in metadata:
            return "(none)"
        return "Yes" if bool(metadata[key]) else "No"

    @staticmethod
    def _surface_metadata_float_text(metadata: dict[str, object], key: str) -> str:
        value = metadata.get(key)
        if value is None:
            return "(none)"
        try:
            return f"{float(value):.3f}"
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _surface_display_opacity(surface: SurfacePatch) -> float:
        metadata = surface.metadata if isinstance(surface.metadata, dict) else {}
        value = metadata.get("display_opacity", metadata.get("opacity", SURFACE_PREVIEW_DEFAULT_OPACITY))
        try:
            opacity = float(value)
        except (TypeError, ValueError):
            opacity = SURFACE_PREVIEW_DEFAULT_OPACITY
        if not np.isfinite(opacity):
            opacity = SURFACE_PREVIEW_DEFAULT_OPACITY
        return min(max(opacity, 0.05), 1.0)

    @staticmethod
    def _surface_wireframe_overlay(surface: SurfacePatch) -> bool:
        metadata = surface.metadata if isinstance(surface.metadata, dict) else {}
        return bool(metadata.get("wireframe_overlay", True))

    def _surface_source_curve_names_summary(self, surface: SurfacePatch) -> str:
        curves_by_id = {
            curve.id: curve for curve in self.app_state.curve_collection.curves
        }
        names = [
            curves_by_id[curve_id].name
            for curve_id in surface.source_curve_ids
            if curve_id in curves_by_id
        ]
        if not names:
            metadata_names = surface.metadata.get("source_curve_names")
            if isinstance(metadata_names, list):
                names = [str(name) for name in metadata_names if str(name)]
        return ", ".join(names) if names else "(missing)"

    @staticmethod
    def _surface_metadata_summary(metadata: dict[str, object]) -> str:
        if not metadata:
            return "(none)"

        parts = [
            f"{key}={metadata[key]}"
            for key in sorted(metadata)
        ]
        return ", ".join(parts)

    def _on_surface_opacity_changed(self, value: object) -> None:
        if self._syncing_surface_display_controls:
            return

        active_surface = self._active_surface()
        if active_surface is None:
            return

        try:
            opacity = float(value)
        except (TypeError, ValueError):
            opacity = SURFACE_PREVIEW_DEFAULT_OPACITY
        if not np.isfinite(opacity):
            opacity = SURFACE_PREVIEW_DEFAULT_OPACITY
        opacity = min(max(opacity, 0.05), 1.0)
        active_surface.metadata["display_opacity"] = opacity
        self.surface_opacity_text.set(f"{opacity:.2f}")
        self.surface_metadata_text.set(self._surface_metadata_summary(active_surface.metadata))
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(f"Selected: {active_surface.name}")
        self._set_project_dirty(True)

    def _on_surface_wireframe_changed(self) -> None:
        if self._syncing_surface_display_controls:
            return

        active_surface = self._active_surface()
        if active_surface is None:
            return

        active_surface.metadata["wireframe_overlay"] = bool(self.surface_wireframe_overlay.get())
        self.surface_metadata_text.set(self._surface_metadata_summary(active_surface.metadata))
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(f"Selected: {active_surface.name}")
        self._set_project_dirty(True)

    def _on_surface_visibility_changed(self) -> None:
        active_surface = self._active_surface()
        if active_surface is None:
            self.status_text.set("No selection")
            return

        node_ids = {surface_node_id(active_surface.id)}
        before = self._visibility_snapshot(node_ids)
        active_surface.visible = bool(self.surface_visible.get())
        after = self._visibility_snapshot(node_ids)
        self._push_visibility_command("Toggle Visibility", before, after)
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(f"Selected: {active_surface.name}")
        self._set_project_dirty(True)

    def delete_selected_surface(self) -> None:
        active_surface = self._active_surface()
        if active_surface is None:
            self.status_text.set("No selection")
            return

        removed_name = active_surface.name or "Surface"
        delete_targets = self._delete_targets_for_node_ids((surface_node_id(active_surface.id),))
        undo_command = self._delete_undo_command_for_targets(delete_targets)
        self._apply_delete_targets(delete_targets)
        if undo_command is not None:
            self._push_undo_command(undo_command)
        self._sync_surface_context_from_active_surface()
        self._select_delete_fallback(delete_targets)
        self.status_text.set(f"Deleted: {removed_name}")
        self._set_project_dirty(True)

    @staticmethod
    def _section_result_summary(stored_result: StoredSectionResult) -> str:
        return (
            f"Section result: {stored_result.name} - "
            f"{stored_result.result.segment_count} segments"
        )

    @staticmethod
    def _section_result_status(stored_result: StoredSectionResult) -> str:
        return (
            f"Section computed: {stored_result.name} - "
            f"{stored_result.result.segment_count} segments"
        )

    @staticmethod
    def _arbitrary_section_status(active_plane: SectionPlaneState) -> str:
        return f"Computed arbitrary section from {active_plane.name}"

    def _section_plane_is_axis_aligned(
        self,
        active_plane: SectionPlaneState,
    ) -> bool:
        axis = normalize_axis(active_plane.axis)
        axis_vector = world_axis_vector(axis)
        origin_offset = float(np.dot(plane_origin(active_plane), axis_vector))
        return bool(
            np.allclose(plane_normal(active_plane), axis_vector, atol=1e-6)
            and abs(origin_offset - active_plane.offset) <= 1e-6
        )

    def _clear_active_section_results(self) -> None:
        active_plane = get_active_plane(self.app_state.section_collection)
        if active_plane is not None:
            result_ids = [
                result.id
                for result in self.app_state.section_collection.results
                if result.plane_id == active_plane.id
            ]
            curve_ids = [
                curve.id
                for curve in self.app_state.curve_collection.curves
                if curve.section_result_id in result_ids
            ]
            self._clear_surfaces_for_curve_ids(curve_ids)
            for result_id in result_ids:
                clear_curves_for_section_result(
                    self.app_state.curve_collection,
                    result_id,
                )
            clear_results_for_plane(self.app_state.section_collection, active_plane.id)

        self._set_display_section_result(self._latest_stored_section_result())

    def frame_all(self) -> None:
        self.viewport.frame_model()
        self.status_text.set("View framed")

    def frame_selected(self) -> None:
        node_ids = self._scene_visibility_target_node_ids()
        if not node_ids:
            self.status_text.set("No selection")
            return

        expanded_node_ids = self._expanded_visibility_node_ids(node_ids)
        if any(region_id_from_node(node_id) is not None for node_id in expanded_node_ids):
            self.frame_selected_region()
            return

        bounds = self._bounds_for_node_ids(expanded_node_ids)
        if bounds is None:
            self.status_text.set("Selected geometry is unavailable")
            return

        minimum_bound, maximum_bound = bounds
        if NODE_MESH in expanded_node_ids:
            self.viewport.frame_model()
        elif hasattr(self.viewport, "frame_bounds"):
            self.viewport.frame_bounds(minimum_bound, maximum_bound)
        else:
            self.viewport.frame_model()
        self.status_text.set("View framed to selection")

    def _bounds_for_node_ids(
        self,
        node_ids: set[str],
    ) -> tuple[np.ndarray, np.ndarray] | None:
        point_sets: list[np.ndarray] = []

        if self.app_state.mesh_object is not None and NODE_MESH in node_ids:
            minimum_bound, maximum_bound = self._transformed_source_bounds()
            point_sets.append(np.vstack((minimum_bound, maximum_bound)))

        plane_points = self._section_plane_frame_points(node_ids)
        if plane_points is not None:
            point_sets.append(plane_points)

        for result in self.app_state.section_collection.results:
            if section_result_node_id(result.id) not in node_ids:
                continue
            for polyline in result.result.polylines:
                points = self._finite_points(polyline.points)
                if points is not None:
                    point_sets.append(points)

        for curve in self.app_state.curve_collection.curves:
            if curve_node_id(curve.id) not in node_ids:
                continue
            points = self._finite_points(curve.fitted_points)
            if points is not None:
                point_sets.append(points)

        curves = self.app_state.curve_collection.curves
        for surface in self.app_state.surface_collection.surfaces:
            if surface_node_id(surface.id) not in node_ids:
                continue
            preview = build_surface_preview_mesh(surface, curves)
            if preview is None:
                continue
            points = self._finite_points(preview.vertices)
            if points is not None:
                point_sets.append(points)

        region_points = self._region_frame_points(node_ids)
        if region_points is not None:
            point_sets.append(region_points)

        if not point_sets:
            return None

        points = np.vstack(point_sets)
        return (points.min(axis=0), points.max(axis=0))

    def _region_frame_points(self, node_ids: set[str]) -> np.ndarray | None:
        region = self.app_state.region_collection.active_region
        mesh_object = self.app_state.mesh_object
        if region is None or mesh_object is None:
            return None
        if region_node_id(region.id) not in node_ids:
            return None

        triangles = np.asarray(mesh_object.display_mesh.triangles, dtype=int).reshape((-1, 3))
        vertices = np.asarray(mesh_object.display_mesh.vertices, dtype=float).reshape((-1, 3))
        selected_indices = np.asarray(
            [
                int(index)
                for index in region.triangle_indices
                if 0 <= int(index) < len(triangles)
            ],
            dtype=int,
        )
        if len(selected_indices) == 0:
            return None

        selected_vertex_indices = np.unique(triangles[selected_indices].ravel())
        points = vertices[selected_vertex_indices]
        matrix = self._current_object_matrix()
        homogeneous = np.column_stack((points, np.ones(len(points))))
        transformed = (matrix @ homogeneous.T).T[:, :3]
        return self._finite_points(transformed)

    def _section_plane_frame_points(self, node_ids: set[str]) -> np.ndarray | None:
        planes = [
            plane
            for plane in self.app_state.section_collection.planes
            if section_plane_node_id(plane.id) in node_ids
        ]
        if not planes:
            return None

        minimum_bound, maximum_bound = self._transformed_source_bounds()
        extent = max(float(np.max(maximum_bound - minimum_bound)), 1.0)
        half_extent = extent * 0.5
        points = []
        for plane in planes:
            origin = plane_origin(plane)
            points.append(origin - half_extent)
            points.append(origin + half_extent)
        return self._finite_points(np.asarray(points, dtype=float))

    @staticmethod
    def _finite_points(points: object) -> np.ndarray | None:
        try:
            values = np.asarray(points, dtype=float)
        except (TypeError, ValueError):
            return None
        if values.ndim != 2 or values.shape[1] != 3:
            return None
        values = values[np.all(np.isfinite(values), axis=1)]
        return values if len(values) else None

    def reset_view(self) -> None:
        self.viewport.reset_view()
        self.status_text.set("View reset")

    def reset_camera(self) -> None:
        self.reset_view()

    def set_named_view(self, name: str) -> None:
        view_name = str(name).strip().lower()
        try:
            self.viewport.set_named_view(view_name)
        except ValueError:
            self.status_text.set(f"Unknown view: {name}")
            return

        label = "Isometric" if view_name in {"iso", "isometric"} else view_name.title()
        self.status_text.set(f"View: {label}")

    def _refresh_viewport(self, *, reset_camera: bool) -> None:
        origin = self.app_state.mesh_object.location if self.app_state.mesh_object is not None else None
        mesh_is_visible = (
            self.app_state.mesh_object is not None
            and bool(self.app_state.mesh_object.visible)
        )
        display_mesh = (
            self.app_state.mesh_object.display_mesh
            if mesh_is_visible
            else None
        )
        transform_matrix = (
            self.app_state.mesh_object.transform_matrix
            if self.app_state.mesh_object is not None and self.app_state.mesh_object.transform_matrix is not None
            else None
        )
        hide_expensive_overlays = self.app_state.transform_state is not None
        visible_curves = [] if hide_expensive_overlays else get_visible_curves(
            self.app_state.curve_collection
        )
        if self._manual_curve_edit_active and self._manual_curve_edit_curve_id is not None:
            visible_curves = [
                curve
                for curve in visible_curves
                if curve.id != self._manual_curve_edit_curve_id
            ]
        surface_previews = [] if hide_expensive_overlays else self._build_visible_surface_previews()
        surface_source_curve_ids = (
            ()
            if hide_expensive_overlays
            else self._active_surface_source_curve_ids()
        )
        region_selection = (
            None
            if hide_expensive_overlays
            else self._active_visible_region_selection()
        )
        self.viewport.set_scene(
            display_mesh,
            transform_matrix=transform_matrix,
            show_grid=self.show_grid.get(),
            show_axes=self.show_axes.get(),
            show_axis_gizmo=self.show_axis_gizmo.get(),
            show_normals=False,
            show_section_plane=self._should_show_section_plane(),
            section_axis=self.section_axis.get(),
            section_offset=self.section_offset.get(),
            section_planes=self.app_state.section_collection.planes,
            active_section_plane_id=self.app_state.section_collection.active_plane_id,
            selected_item=self.app_state.selected_item,
            object_origin=origin,
            scene_bounds_min=(
                self.app_state.mesh_object.source_bounds_min if self.app_state.mesh_object is not None else None
            ),
            scene_bounds_max=(
                self.app_state.mesh_object.source_bounds_max if self.app_state.mesh_object is not None else None
            ),
            active_transform_mode=self.app_state.active_transform_mode,
            active_transform_axis=self.app_state.active_transform_axis,
            active_transform_angle_delta=self._active_transform_angle_delta,
            section_result=None if hide_expensive_overlays else self.app_state.section_result,
            curve_results=visible_curves,
            active_curve_id=self.app_state.curve_collection.active_curve_id,
            surface_source_curve_ids=surface_source_curve_ids,
            surface_previews=surface_previews,
            active_surface_id=self.app_state.surface_collection.active_surface_id,
            region_selection=region_selection,
            region_selection_color=self.settings.display.region_selection_color,
            region_selection_edge_color=self.settings.display.region_selection_edge_color,
            region_selection_opacity=self.settings.display.region_selection_opacity,
            manual_curve_points=(
                self._manual_curve_points
                if self._manual_curve_active
                else None
            ),
            manual_curve_closed=self._manual_curve_closed,
            manual_curve_plane_normal=(
                self._manual_curve_plane_normal
                if self._manual_curve_active
                else None
            ),
            manual_curve_snap_to_mesh=bool(self.manual_curve_snap_to_mesh.get()),
            manual_curve_selected_control_point_index=(
                self._manual_curve_selected_control_point_index
                if self._manual_curve_edit_active
                else None
            ),
            manual_curve_method=self._manual_curve_curve_method,
            manual_curve_sample_count=self._manual_curve_sample_count,
            manual_curve_preview_point=(
                self._manual_curve_preview_point
                if self._manual_curve_active and self._manual_curve_preview_valid
                else None
            ),
            manual_curve_preview_valid=(
                self._manual_curve_preview_valid
                if self._manual_curve_active
                else False
            ),
            manual_curve_preview_snaps_closed=self._manual_curve_preview_snaps_closed,
            manual_curve_preview_snaps_to_mesh=self._manual_curve_preview_snaps_to_mesh,
            reset_camera=reset_camera,
        )
        self._refresh_scene_browser()

    def _active_surface_source_curve_ids(self) -> tuple[str, ...]:
        if self.app_state.selected_item != SELECT_SURFACE:
            return ()

        active_surface = self._active_surface()
        if active_surface is None:
            return ()

        return tuple(str(curve_id) for curve_id in active_surface.source_curve_ids)

    def _refresh_scene_browser(self) -> None:
        for curve in self.app_state.curve_collection.curves:
            refresh_curve_diagnostics(curve)
        active_region = self.app_state.region_collection.active_region
        self.scene_browser.update_scene(
            has_mesh=self.app_state.mesh_object is not None,
            mesh_name=(
                self.app_state.mesh_object.name
                if self.app_state.mesh_object is not None
                else None
            ),
            mesh_visible=(
                bool(self.app_state.mesh_object.visible)
                if self.app_state.mesh_object is not None
                else True
            ),
            section_planes=self.app_state.section_collection.planes,
            active_section_plane_id=self.app_state.section_collection.active_plane_id,
            selected_section_plane_ids=self.app_state.section_collection.selected_plane_ids,
            section_results=self.app_state.section_collection.results,
            active_section_result_id=self.app_state.section_collection.active_result_id,
            selected_section_result_ids=self.app_state.section_collection.selected_result_ids,
            curves=self.app_state.curve_collection.curves,
            active_curve_id=self.app_state.curve_collection.active_curve_id,
            selected_curve_ids=self.app_state.curve_collection.selected_curve_ids,
            surfaces=self.app_state.surface_collection.surfaces,
            active_surface_id=self.app_state.surface_collection.active_surface_id,
            selected_surface_ids=self.app_state.surface_collection.selected_surface_ids,
            has_section_result=bool(self.app_state.section_collection.results)
            or self.app_state.section_result is not None,
            has_curves=bool(self.app_state.curve_collection.curves),
            has_surfaces=bool(self.app_state.surface_collection.surfaces),
            selected_item=self.app_state.selected_item,
            regions=() if active_region is None else (active_region,),
            active_region_id=None if active_region is None else active_region.id,
            selected_region_ids=(
                set()
                if active_region is None or not bool(active_region.selected)
                else {active_region.id}
            ),
        )
        self._sync_workflow_ui()

    def _sync_workflow_ui(self) -> None:
        if not hasattr(self, "root"):
            return

        has_mesh = self.app_state.mesh_object is not None
        self.empty_scene_prompt_text.set(
            "Mesh loaded. Select an object or choose a workflow."
            if has_mesh
            else "Load a mesh to begin reverse engineering."
        )
        self.project_path_text.set(
            f"Project: {self.current_project_path}"
            if self.current_project_path is not None
            else "Project: Untitled Project"
        )
        self.current_mode_text.set(self._current_mode_label())
        self.selected_object_type_text.set(self._selected_object_type_label())
        self._sync_mesh_required_sidebar_controls(has_mesh)
        self._sync_manual_curve_panel()
        self._sync_region_panel()
        self._update_command_strip()
        self._update_menu_availability()

    def _update_command_strip(self) -> None:
        mode = self._current_mode_label()
        self.current_mode_text.set(mode)
        if self._manual_curve_edit_active:
            if self._manual_curve_add_point_active:
                prompt = "Edit Curve: Add Point active. Click to place next point."
            elif self._manual_curve_insert_point_active:
                prompt = "Edit Curve: Insert Point active. Click segment location."
            else:
                prompt = "Manual Curve Edit: click a control point to select it."
            hints = "Enter=apply, Esc=done/cancel action, Backspace=delete point, C=closed"
        elif self._manual_curve_active:
            if bool(self.manual_curve_snap_to_mesh.get()):
                prompt = "Manual Curve: Snap to Mesh On. Click scan surface to place."
            else:
                prompt = "Manual Curve: previewing next point. Click to place."
            hints = "Enter=finish, Esc=cancel, Backspace=remove, C=closed"
        elif self.app_state.transform_state is not None:
            prompt = self._active_transform_status()
            hints = "Drag mouse, X/Y/Z constrain, Enter/click confirm, Esc cancel"
        elif self._region_select_active:
            prompt = "Region Select: click a mesh area to grow a connected region."
            hints = "Esc cancel, click mesh to select region."
        else:
            prompt = WORKBENCH_PROMPTS.get(self.current_workbench.get(), "Ready")
            hints = "G=move, R=rotate, F=frame, H=visibility, Del=delete"
        self.command_prompt_text.set(prompt)
        self.hotkey_hint_text.set(hints)

    def _sync_mesh_required_sidebar_controls(self, has_mesh: bool) -> None:
        mesh_state = "normal" if has_mesh else "disabled"
        selected_curve_count = len(self.app_state.curve_collection.selected_curve_ids)
        has_curves = bool(self.app_state.curve_collection.curves)
        has_selected_curve = selected_curve_count > 0 and has_mesh
        has_active_surface = self._active_surface() is not None and has_mesh
        has_section_results = bool(self.app_state.section_collection.results)
        selected_model = self.app_state.selected_item == SELECT_MODEL and has_mesh
        has_section_planes = bool(self.app_state.section_collection.planes)
        for name in (
            "scene_mesh_visible_check",
            "scene_delete_mesh_button",
            "select_model_button",
            "select_section_plane_button",
            "section_add_plane_button",
            "section_plane_name_entry",
            "show_section_plane_check",
            "axis_dropdown",
            "offset_slider",
            "offset_input",
            "compute_section_button",
            "section_select_model_button",
        ):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.configure(state=mesh_state)
        for name in ("section_delete_plane_button",):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.configure(state="normal" if has_mesh and has_section_planes else "disabled")
        for name in ("clear_section_button", "clear_all_sections_button"):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.configure(state="normal" if has_mesh and has_section_results else "disabled")
        for widget in getattr(self, "object_transform_widgets", []):
            widget.configure(state="normal" if selected_model else "disabled")
        for name in (
            "mesh_visible_check",
            "mesh_name_entry",
            "move_transform_button",
            "rotate_transform_button",
            "set_origin_geometry_button",
            "origin_world_button",
            "center_geometry_button",
            "reset_object_button",
            "frame_selected_button",
            "model_select_section_plane_button",
            "model_deselect_button",
        ):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.configure(state="normal" if selected_model else "disabled")
        curve_state = "normal" if has_selected_curve else "disabled"
        active_curve = self._active_curve()
        editable_curve_state = (
            "normal"
            if has_mesh
            and selected_curve_count == 1
            and active_curve is not None
            and self._is_editable_manual_curve(active_curve)
            and not self._manual_curve_active
            else "disabled"
        )
        for name in (
            "curve_visible_check",
            "curve_name_entry",
            "delete_curve_button",
            "hide_selected_curves_button",
            "hide_unselected_curves_button",
            "auto_close_curve_button",
            "simplify_curve_button",
            "smooth_curve_button",
        ):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.configure(state=curve_state)
        widget = getattr(self, "edit_selected_curve_button", None)
        if widget is not None:
            widget.configure(state=editable_curve_state)
        surface_prep_curve_state = (
            "normal"
            if has_mesh
            and selected_curve_count == 1
            and active_curve is not None
            and not self._manual_curve_active
            else "disabled"
        )
        for name in (
            "project_curve_to_mesh_button",
            "manual_project_curve_to_mesh_button",
            "rebuild_curve_button",
            "manual_rebuild_curve_button",
            "rebuild_target_control_points_entry",
            "rebuild_curve_type_combo",
            "rebuild_sample_count_entry",
            "validate_curve_button",
        ):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.configure(state=surface_prep_curve_state)
        widget = getattr(self, "validate_loft_curves_button", None)
        if widget is not None:
            widget.configure(
                state="normal" if has_mesh and selected_curve_count == 2 else "disabled"
            )
        for name in ("join_curves_button", "loft_curves_button"):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.configure(state="normal" if has_mesh and selected_curve_count >= 2 else "disabled")
        for name in ("fill_closed_curve_button", "boundary_patch_button"):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.configure(state="normal" if has_mesh and selected_curve_count == 1 else "disabled")
        widget = getattr(self, "four_curve_patch_button", None)
        if widget is not None:
            widget.configure(
                state="normal" if has_mesh and selected_curve_count == 4 else "disabled"
            )
        widget = getattr(self, "curve_network_patch_button", None)
        if widget is not None:
            widget.configure(
                state="normal" if has_mesh and selected_curve_count >= 3 else "disabled"
            )
        for name in (
            "show_all_curves_button",
            "select_tiny_curves_button",
            "hide_tiny_curves_button",
            "delete_tiny_curves_button",
        ):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.configure(state="normal" if has_mesh and has_curves else "disabled")
        for name in (
            "surface_visible_check",
            "surface_name_entry",
            "surface_opacity_slider",
            "surface_wireframe_check",
            "select_source_curves_button",
            "isolate_source_curves_button",
            "show_source_curves_button",
            "frame_source_curves_button",
            "delete_surface_button",
        ):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.configure(state="normal" if has_active_surface else "disabled")

    def _current_mode_label(self) -> str:
        if self._manual_curve_edit_active:
            return "Manual Curve Edit"
        if self._manual_curve_active:
            return "Manual Curve"
        if self._region_select_active:
            return "Region Select"
        if self.app_state.transform_state is not None:
            mode = self.app_state.transform_state.mode.title()
            return f"Transform: {mode}"
        return "No Mode"

    def _selected_object_type_label(self) -> str:
        selected_item = self.app_state.selected_item
        if selected_item == SELECT_MODEL and self.app_state.mesh_object is not None:
            return "Mesh"
        if selected_item == SELECT_SECTION_PLANE:
            return "Section Plane"
        if selected_item == SELECT_SECTION_RESULT:
            return "Section Result"
        if selected_item == SELECT_CURVE:
            return "Curve"
        if selected_item == SELECT_SURFACE:
            return "Surface"
        if selected_item == SELECT_REGION:
            return "Region"
        return "(none)"

    def _sync_manual_curve_panel(self) -> None:
        has_mesh = self.app_state.mesh_object is not None
        active = bool(self._manual_curve_active)
        edit_active = bool(self._manual_curve_edit_active)
        point_count = len(self._manual_curve_points)
        point_label = "point" if point_count == 1 else "points"
        active_curve = self._active_curve()
        can_edit_selected = bool(
            has_mesh
            and active_curve is not None
            and self._is_editable_manual_curve(active_curve)
            and not active
        )
        if edit_active:
            selected_label = (
                str(self._manual_curve_selected_control_point_index + 1)
                if self._manual_curve_selected_control_point_index is not None
                else "(none)"
            )
            sub_action = "Add Point" if self._manual_curve_add_point_active else (
                "Insert Point" if self._manual_curve_insert_point_active else "Select Point"
            )
            snap_label = "On" if bool(self.manual_curve_snap_to_mesh.get()) else "Off"
            closed_label = "Yes" if self._manual_curve_closed else "No"
            self.manual_curve_mode_title.set("MANUAL CURVE EDIT MODE")
            self.manual_curve_mode_details.set(
                "MANUAL CURVE EDIT MODE\n"
                f"Control points: {point_count}\n"
                f"Selected point: {selected_label}\n"
                f"Snap edited points: {snap_label}\n"
                f"Curve type: {self.manual_curve_type_text.get()}\n"
                f"Closed: {closed_label}\n"
                f"Action: {sub_action}"
            )
        elif active:
            self.manual_curve_mode_title.set("MANUAL CURVE MODE")
            snap_label = "On" if bool(self.manual_curve_snap_to_mesh.get()) else "Off"
            closed_label = "Yes" if self._manual_curve_closed else "No"
            self.manual_curve_mode_details.set(
                "MANUAL CURVE MODE\n"
                f"Point count: {point_count}\n"
                f"Snap mode: {snap_label}\n"
                f"Drawing plane: {self._manual_curve_plane_label}\n"
                f"Closed: {closed_label}\n"
                "Enter: Finish, Esc: Cancel, Backspace: Remove last point, C: Toggle closed"
            )
        elif has_mesh:
            self.manual_curve_mode_title.set("Manual Curve")
            self.manual_curve_mode_details.set("Create a manual curve by placing points.")
        else:
            self.manual_curve_mode_title.set("Manual Curve")
            self.manual_curve_mode_details.set("Create a manual curve by placing points.")
        self.manual_curve_snap_help_text.set(
            "Snap to Mesh places manual curve points on the scan surface."
            if has_mesh
            else "Load a mesh to enable Snap to Mesh."
        )

        create_active = active and not edit_active
        active_state = "normal" if active else "disabled"
        create_active_state = "normal" if create_active else "disabled"
        edit_active_state = "normal" if edit_active else "disabled"
        start_state = "normal" if has_mesh and not active else "disabled"
        edit_state = "normal" if can_edit_selected else "disabled"
        snap_state = "normal" if has_mesh else "disabled"
        if hasattr(self, "finish_manual_curve_button"):
            self.finish_manual_curve_button.configure(
                text="Apply Edits" if edit_active else "Finish Curve"
            )
        if hasattr(self, "cancel_manual_curve_button"):
            self.cancel_manual_curve_button.configure(
                text="Cancel Edit" if edit_active else "Cancel"
            )
        for name, state in (
            ("start_manual_curve_button", start_state),
            ("edit_manual_curve_button", edit_state),
            ("finish_manual_curve_button", active_state),
            ("cancel_manual_curve_button", active_state),
            ("done_manual_curve_edit_button", edit_active_state),
            ("remove_manual_point_button", create_active_state),
            ("toggle_manual_closed_button", active_state),
            ("add_manual_point_button", edit_active_state),
            ("insert_manual_point_button", edit_active_state),
            (
                "delete_manual_point_button",
                "normal"
                if edit_active and self._manual_curve_selected_control_point_index is not None
                else "disabled",
            ),
            ("manual_curve_snap_check", snap_state),
            ("manual_curve_type_combo", "readonly" if active else "disabled"),
        ):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.configure(state=state)
        for name in ("fit_patch_from_region_placeholder_button",):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.configure(state="disabled")
        if not has_mesh and bool(self.manual_curve_snap_to_mesh.get()):
            self.manual_curve_snap_to_mesh.set(False)

    def _sync_region_panel(self) -> None:
        has_mesh = self.app_state.mesh_object is not None
        region = self.app_state.region_collection.active_region
        has_region = region is not None
        mesh_state = "normal" if has_mesh else "disabled"
        region_state = "normal" if has_region else "disabled"
        boundary_curve_count = (
            0 if region is None else len(self._boundary_curves_for_region(region.id))
        )

        for name in (
            "region_select_button",
            "region_threshold_entry",
            "region_threshold_slider",
            "region_max_triangle_entry",
        ):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.configure(state=mesh_state)

        for name in (
            "recompute_region_button",
            "clear_region_button",
            "hide_region_button",
            "show_region_button",
            "delete_region_button",
            "region_name_entry",
        ):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.configure(state=region_state)
        extract_button = getattr(self, "extract_region_boundary_button", None)
        if extract_button is not None:
            extract_button.configure(state="normal" if has_mesh and has_region else "disabled")
        select_boundary_button = getattr(self, "select_region_boundary_curves_button", None)
        if select_boundary_button is not None:
            select_boundary_button.configure(
                state="normal" if has_mesh and has_region and boundary_curve_count > 0 else "disabled"
            )
        done_button = getattr(self, "done_region_select_button", None)
        if done_button is not None:
            done_button.configure(state="normal" if self._region_select_active else "disabled")

        if has_region:
            triangle_count = len(region.triangle_indices)
            self.region_name_text.set(region.name or "Region 1")
            self.region_triangle_count_text.set(f"{triangle_count:,}")
            self.region_threshold_display_text.set(
                f"{float(region.threshold_degrees):.1f} deg"
            )
            self.region_max_triangle_cap_text.set(f"{int(region.max_triangle_count):,}")
            self.region_seed_triangle_text.set(
                "-"
                if region.seed_triangle_index is None
                else str(int(region.seed_triangle_index))
            )
            self.region_source_mesh_text.set(region.source_mesh_name or "(none)")
            self.region_visible_text.set("Yes" if bool(region.visible) else "No")
            self.region_boundary_curve_count_text.set(f"{boundary_curve_count:,}")
            if self._region_select_active:
                state_text = "Region Select active"
            else:
                state_text = "Region visible" if bool(region.visible) else "Region hidden"
            self.region_status_text.set(state_text)
        else:
            self.region_name_text.set("(none)")
            self.region_triangle_count_text.set("0")
            self.region_threshold_display_text.set(
                f"{self._region_threshold_value():.1f} deg"
            )
            self.region_max_triangle_cap_text.set(f"{self._region_max_triangle_value():,}")
            self.region_seed_triangle_text.set("-")
            self.region_source_mesh_text.set(
                self.app_state.mesh_object.name
                if self.app_state.mesh_object is not None
                else "(none)"
            )
            self.region_visible_text.set("No")
            self.region_boundary_curve_count_text.set("0")
            if not has_mesh:
                self.region_status_text.set("Load a mesh to use Region Select.")
            elif self._region_select_active:
                self.region_status_text.set("Region Select active")
            else:
                self.region_status_text.set("No active region")

        if self._region_select_active:
            triangle_count = "0" if not has_region else self.region_triangle_count_text.get()
            self.manual_curve_mode_title.set("REGION SELECT MODE")
            self.manual_curve_mode_details.set(
                "Click a mesh area to grow a connected region by normal angle.\n"
                f"Threshold: {self._region_threshold_value():.1f} deg\n"
                f"Max triangles: {self._region_max_triangle_value():,}\n"
                f"Current triangles: {triangle_count}"
            )

    def _update_menu_availability(self) -> None:
        scene_node_ids = self._scene_visibility_target_node_ids()
        has_scene_selection = bool(
            self._expanded_visibility_node_ids(scene_node_ids)
            & self._all_visibility_object_node_ids()
        )
        can_rename_scene_selection = (
            len(scene_node_ids) == 1
            and self.scene_browser._is_renameable_node(scene_node_ids[0])
        )

        self._set_menu_labels_state(self.edit_menu, ("Rename Selected",), can_rename_scene_selection)
        self._set_menu_labels_state(self.edit_menu, ("Delete Selected",), has_scene_selection)
        self._set_menu_labels_state(self.view_menu, ("Frame Selected",), has_scene_selection)

    @staticmethod
    def _set_menu_labels_state(menu: object, labels: tuple[str, ...], enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for label in labels:
            _set_menu_entry_state_by_label(menu, label, state)

    def _should_show_section_plane(self) -> bool:
        if not self.mesh_state.is_loaded:
            return False

        return any(plane.visible for plane in self.app_state.section_collection.planes)

    def _sync_active_section_plane_from_controls(self) -> bool:
        active_plane = get_active_plane(self.app_state.section_collection)
        if active_plane is None:
            return False

        axis = normalize_axis(self.section_axis.get())
        offset = float(self.section_offset.get())
        reset_to_axis_aligned = not np.allclose(
            plane_normal(active_plane),
            world_axis_vector(axis),
            atol=1e-6,
        )
        active_plane.axis = axis
        set_plane_axis_offset(
            active_plane,
            axis,
            offset,
        )
        active_plane.visible = bool(self.show_section_plane.get())
        return reset_to_axis_aligned

    def _sync_section_controls_from_active_plane(self, *, clamp_offset: bool = True) -> None:
        active_plane = get_active_plane(self.app_state.section_collection)
        if active_plane is None:
            return

        desired_offset = float(active_plane.offset)
        self.section_plane_name_text.set(active_plane.name)
        self.section_axis.set(normalize_axis(active_plane.axis))
        self.show_section_plane.set(bool(active_plane.visible))
        self._update_section_offset_range()
        clamp_display_offset = clamp_offset and np.allclose(
            plane_normal(active_plane),
            world_axis_vector(self.section_axis.get()),
            atol=1e-6,
        )
        self._set_section_offset(
            desired_offset,
            clamp=clamp_display_offset,
            refresh=False,
            clear_section=False,
            sync_plane=False,
        )
        self._update_section_plane_label(set_status=False)

    def _sync_section_controls_from_plane_orientation(
        self,
        active_plane: SectionPlaneState,
    ) -> None:
        offset = float(active_plane.offset)
        minimum, maximum = self._section_offset_bounds
        if offset < minimum or offset > maximum:
            minimum = min(minimum, offset)
            maximum = max(maximum, offset)
            self._section_offset_bounds = (minimum, maximum)
            self.offset_slider.configure(from_=minimum, to=maximum)

        self.section_axis.set(normalize_axis(active_plane.axis))
        self._updating_offset = True
        try:
            self.section_offset.set(offset)
            self.section_offset_text.set(f"{offset:.3f}")
        finally:
            self._updating_offset = False
        self._update_section_plane_label(set_status=False)

    def _on_view_option_changed(self) -> None:
        self._sync_viewcube_shell_visibility()
        self._refresh_viewport(reset_camera=False)
        self._set_project_dirty(True)

    def _on_proxy_quality_changed(self, _event: object | None = None) -> None:
        quality = normalize_proxy_quality(self.proxy_quality.get())
        if quality != self.proxy_quality.get():
            self.proxy_quality.set(quality)

        if self.app_state.mesh_object is None:
            self._update_stats()
            self.status_text.set(f"Proxy quality: {quality}")
            self._set_project_dirty(True)
            return

        self.status_text.set(f"Rebuilding {quality} display proxy")
        self.root.update_idletasks()
        display_result = build_display_mesh(self.app_state.mesh_object.source_mesh, quality=quality)
        self._apply_display_mesh_result(display_result)
        self._update_stats()
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(self._display_mesh_status(display_result))
        self._set_project_dirty(True)

    def _on_section_plane_visibility_changed(self) -> None:
        active_plane = get_active_plane(self.app_state.section_collection)
        if active_plane is not None:
            node_ids = {section_plane_node_id(active_plane.id)}
            before = self._visibility_snapshot(node_ids)
            active_plane.visible = bool(self.show_section_plane.get())
            after = self._visibility_snapshot(node_ids)
            self._push_visibility_command("Toggle Visibility", before, after)
        self._refresh_viewport(reset_camera=False)
        self._set_project_dirty(True)

    def _on_mesh_visibility_changed(self) -> None:
        if self.app_state.mesh_object is None:
            self.status_text.set("No selection")
            return

        node_ids = {NODE_MESH}
        before = self._visibility_snapshot(node_ids)
        self.app_state.mesh_object.visible = bool(self.mesh_visible.get())
        after = self._visibility_snapshot(node_ids)
        self._push_visibility_command("Toggle Visibility", before, after)
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(f"Selected: {self.app_state.mesh_object.name}")
        self._set_project_dirty(True)

    def _on_mesh_name_changed(self, event: object | None = None) -> None:
        mesh_object = self.app_state.mesh_object
        if mesh_object is None:
            return

        candidate = self._validated_name_candidate(
            self.mesh_name_text,
            mesh_object.name,
            self.mesh_name_entry,
            event,
        )
        if candidate is None or candidate == mesh_object.name:
            return

        old_name = mesh_object.name
        mesh_object.name = candidate
        self._push_rename_command(
            NODE_MESH,
            "Rename Mesh",
            old_name,
            candidate,
        )
        self._update_stats()
        self._refresh_scene_browser()
        self.status_text.set(f"Selected: {mesh_object.name}")
        self._set_project_dirty(True)

    def _on_section_plane_name_changed(self, event: object | None = None) -> None:
        active_plane = get_active_plane(self.app_state.section_collection)
        if active_plane is None:
            return

        candidate = self._validated_name_candidate(
            self.section_plane_name_text,
            active_plane.name,
            self.section_plane_name_entry,
            event,
        )
        if candidate is None or candidate == active_plane.name:
            return

        old_name = active_plane.name
        active_plane.name = candidate
        self._push_rename_command(
            section_plane_node_id(active_plane.id),
            "Rename Section Plane",
            old_name,
            candidate,
        )
        self._refresh_scene_browser()
        self._sync_curve_context_from_active_curve()
        self._sync_section_result_context_from_active_result()
        self.status_text.set(f"Selected: {active_plane.name}")
        self._set_project_dirty(True)

    def _on_section_result_visibility_changed(self) -> None:
        active_result = self._active_section_result()
        if active_result is None:
            self.status_text.set("No selection")
            return

        node_ids = {section_result_node_id(active_result.id)}
        before = self._visibility_snapshot(node_ids)
        active_result.visible = bool(self.section_result_visible.get())
        after = self._visibility_snapshot(node_ids)
        self._push_visibility_command("Toggle Visibility", before, after)
        self._set_display_section_result(active_result)
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(f"Selected: {active_result.name}")
        self._set_project_dirty(True)

    def _on_section_result_name_changed(self, event: object | None = None) -> None:
        active_result = self._active_section_result()
        if active_result is None:
            return

        candidate = self._validated_name_candidate(
            self.section_result_name_text,
            active_result.name,
            self.section_result_name_entry,
            event,
        )
        if candidate is None or candidate == active_result.name:
            return

        old_name = active_result.name
        active_result.name = candidate
        self._push_rename_command(
            section_result_node_id(active_result.id),
            "Rename Section Result",
            old_name,
            candidate,
        )
        self.section_result_text.set(self._section_result_summary(active_result))
        self._refresh_scene_browser()
        self._sync_curve_context_from_active_curve()
        self.status_text.set(f"Selected: {active_result.name}")
        self._set_project_dirty(True)

    def _on_scene_browser_visibility(
        self,
        action: str,
        node_ids: tuple[str, ...],
    ) -> None:
        if action == "select":
            self._select_scene_browser_nodes(node_ids)
            return
        if action == "rename":
            self.rename_selected()
            return
        if action == "delete_selected":
            self._delete_selected_if_safe()
            return
        if action == "frame_selected":
            self.frame_selected()
            return
        if action == "extract_region_boundary":
            self.extract_region_boundary()
            return
        if action == "project_curve_to_mesh":
            self.project_selected_curve_to_mesh()
            return
        if action == "rebuild_curve":
            self.rebuild_selected_curve()
            return
        if action == "select_source_curves":
            self.select_source_curves_for_active_surface(node_ids)
            return
        if action == "isolate_source_curves":
            self.isolate_source_curves_for_active_surface(node_ids)
            return
        if action == "show_source_curves":
            self.show_source_curves_for_active_surface(node_ids)
            return
        if action == "frame_source_curves":
            self.frame_source_curves_for_active_surface(node_ids)
            return
        if action == "toggle_visibility":
            self.toggle_selected_scene_objects()
            return

        expanded_node_ids = self._expanded_visibility_node_ids(node_ids)
        dirty_node_ids = expanded_node_ids
        if action == "show_all":
            target_node_ids = self._all_visibility_object_node_ids()
            dirty_node_ids = target_node_ids
            before = self._visibility_snapshot(target_node_ids)
            changed_count = self._set_scene_visibility(target_node_ids, True)
            after = self._visibility_snapshot(target_node_ids)
            self._push_visibility_command("Show Visibility", before, after)
            status = "All scene items visible"
        elif action == "hide_selected":
            before = self._visibility_snapshot(expanded_node_ids)
            changed_count = self._set_scene_visibility(expanded_node_ids, False)
            after = self._visibility_snapshot(expanded_node_ids)
            self._push_visibility_command("Hide Visibility", before, after)
            status = self._visibility_status("Hidden", changed_count, "selected item")
        elif action == "show_selected":
            before = self._visibility_snapshot(expanded_node_ids)
            changed_count = self._set_scene_visibility(expanded_node_ids, True)
            after = self._visibility_snapshot(expanded_node_ids)
            self._push_visibility_command("Show Visibility", before, after)
            status = self._visibility_status("Shown", changed_count, "selected item")
        elif action == "hide_unselected":
            target_node_ids = self._all_visibility_object_node_ids()
            dirty_node_ids = target_node_ids
            unselected_node_ids = target_node_ids - expanded_node_ids
            before = self._visibility_snapshot(target_node_ids)
            hidden_count = self._set_scene_visibility(unselected_node_ids, False)
            shown_count = self._set_scene_visibility(expanded_node_ids, True)
            changed_count = hidden_count + shown_count
            after = self._visibility_snapshot(target_node_ids)
            self._push_visibility_command("Hide Visibility", before, after)
            status = self._visibility_status("Hidden", hidden_count, "unselected item")
        else:
            self.status_text.set("Unknown visibility command")
            return

        self._sync_after_scene_visibility_change()
        self.status_text.set(status)
        if changed_count and self._has_persistent_visibility_target(dirty_node_ids):
            self._set_project_dirty(True)

    def _select_scene_browser_nodes(self, node_ids: tuple[str, ...]) -> None:
        if not node_ids:
            self.status_text.set("No selection")
            return

        focused_node_id = self.scene_browser.tree.focus()
        selected_item = (
            focused_node_id
            if focused_node_id in node_ids
            else node_ids[0]
        )
        self._on_scene_browser_selection(selected_item, node_ids)

    @staticmethod
    def _has_persistent_visibility_target(node_ids: set[str]) -> bool:
        return any(
            node_id != NODE_REGIONS and region_id_from_node(node_id) is None
            for node_id in node_ids
        )

    @staticmethod
    def _visibility_status(prefix: str, changed_count: int, noun: str) -> str:
        if changed_count == 0:
            return "No visibility changes"
        if changed_count == 1:
            return f"{prefix} 1 {noun}"
        return f"{prefix} {changed_count} {noun}s"

    def _expanded_visibility_node_ids(self, node_ids: tuple[str, ...]) -> set[str]:
        expanded_node_ids = set(node_ids)
        section_result_ids = {
            result.id for result in self.app_state.section_collection.results
        }
        for node_id in node_ids:
            if node_id == NODE_MESH:
                expanded_node_ids.add(NODE_MESH)
            elif node_id == NODE_SECTION_PLANES:
                expanded_node_ids.update(
                    section_plane_node_id(plane.id)
                    for plane in self.app_state.section_collection.planes
                )
            elif node_id == NODE_SECTION_RESULTS:
                expanded_node_ids.update(
                    section_result_node_id(result.id)
                    for result in self.app_state.section_collection.results
                )
            elif node_id == NODE_CURVES:
                expanded_node_ids.update(
                    curve_node_id(curve.id)
                    for curve in self.app_state.curve_collection.curves
                )
            elif node_id == NODE_SURFACES:
                expanded_node_ids.update(
                    surface_node_id(surface.id)
                    for surface in self.app_state.surface_collection.surfaces
                )
            elif node_id == NODE_REGIONS:
                region = self.app_state.region_collection.active_region
                if region is not None:
                    expanded_node_ids.add(region_node_id(region.id))
            elif node_id == NODE_CURVE_GROUP_UNASSIGNED:
                expanded_node_ids.update(
                    curve_node_id(curve.id)
                    for curve in self.app_state.curve_collection.curves
                    if curve.section_result_id not in section_result_ids
                    and not is_repaired_curve(curve)
                    and not self._is_projected_curve(curve)
                    and not self._is_rebuilt_curve(curve)
                    and not self._is_region_boundary_curve(curve)
                    and not self._is_manual_or_mesh_curve(curve)
                )
            elif node_id == NODE_CURVE_GROUP_PROJECTED:
                expanded_node_ids.update(
                    curve_node_id(curve.id)
                    for curve in self.app_state.curve_collection.curves
                    if self._is_projected_curve(curve)
                )
            elif node_id == NODE_CURVE_GROUP_REBUILT:
                expanded_node_ids.update(
                    curve_node_id(curve.id)
                    for curve in self.app_state.curve_collection.curves
                    if self._is_rebuilt_curve(curve)
                )
            elif node_id == NODE_CURVE_GROUP_REGION_BOUNDARIES:
                expanded_node_ids.update(
                    curve_node_id(curve.id)
                    for curve in self.app_state.curve_collection.curves
                    if self._is_region_boundary_curve(curve)
                )
            elif node_id == NODE_CURVE_GROUP_REPAIRED:
                expanded_node_ids.update(
                    curve_node_id(curve.id)
                    for curve in self.app_state.curve_collection.curves
                    if is_repaired_curve(curve)
                )
            elif node_id == NODE_CURVE_GROUP_MANUAL:
                expanded_node_ids.update(
                    curve_node_id(curve.id)
                    for curve in self.app_state.curve_collection.curves
                    if self._is_manual_or_mesh_curve(curve)
                )
            else:
                for result in self.app_state.section_collection.results:
                    if node_id != curve_group_node_id(result.id):
                        continue
                    expanded_node_ids.update(
                        curve_node_id(curve.id)
                        for curve in self.app_state.curve_collection.curves
                        if curve.section_result_id == result.id
                        and not self._is_projected_curve(curve)
                        and not self._is_rebuilt_curve(curve)
                        and not self._is_region_boundary_curve(curve)
                        and not self._is_manual_or_mesh_curve(curve)
                    )
                    break
        return expanded_node_ids

    def _all_visibility_object_node_ids(self) -> set[str]:
        node_ids = {
            *(
                section_plane_node_id(plane.id)
                for plane in self.app_state.section_collection.planes
            ),
            *(
                section_result_node_id(result.id)
                for result in self.app_state.section_collection.results
            ),
            *(curve_node_id(curve.id) for curve in self.app_state.curve_collection.curves),
            *(
                surface_node_id(surface.id)
                for surface in self.app_state.surface_collection.surfaces
            ),
        }
        if self.app_state.mesh_object is not None:
            node_ids.add(NODE_MESH)
        active_region = self.app_state.region_collection.active_region
        if active_region is not None:
            node_ids.add(region_node_id(active_region.id))
        return node_ids

    def _toggle_scene_visibility(self, node_ids: set[str]) -> int:
        changed_count = 0
        if self.app_state.mesh_object is not None and NODE_MESH in node_ids:
            self.app_state.mesh_object.visible = not self.app_state.mesh_object.visible
            changed_count += 1
        for plane in self.app_state.section_collection.planes:
            if section_plane_node_id(plane.id) in node_ids:
                plane.visible = not plane.visible
                changed_count += 1
        for result in self.app_state.section_collection.results:
            if section_result_node_id(result.id) in node_ids:
                result.visible = not result.visible
                changed_count += 1
        for curve in self.app_state.curve_collection.curves:
            if curve_node_id(curve.id) in node_ids:
                curve.visible = not curve.visible
                changed_count += 1
        for surface in self.app_state.surface_collection.surfaces:
            if surface_node_id(surface.id) in node_ids:
                surface.visible = not surface.visible
                changed_count += 1
        active_region = self.app_state.region_collection.active_region
        if active_region is not None and region_node_id(active_region.id) in node_ids:
            active_region.visible = not active_region.visible
            changed_count += 1
        return changed_count

    def _set_scene_visibility(self, node_ids: set[str], visible: bool) -> int:
        changed_count = 0
        if (
            self.app_state.mesh_object is not None
            and NODE_MESH in node_ids
            and self.app_state.mesh_object.visible != visible
        ):
            self.app_state.mesh_object.visible = visible
            changed_count += 1
        for plane in self.app_state.section_collection.planes:
            if section_plane_node_id(plane.id) in node_ids and plane.visible != visible:
                plane.visible = visible
                changed_count += 1
        for result in self.app_state.section_collection.results:
            if section_result_node_id(result.id) in node_ids and result.visible != visible:
                result.visible = visible
                changed_count += 1
        for curve in self.app_state.curve_collection.curves:
            if curve_node_id(curve.id) in node_ids and curve.visible != visible:
                curve.visible = visible
                changed_count += 1
        for surface in self.app_state.surface_collection.surfaces:
            if surface_node_id(surface.id) in node_ids and surface.visible != visible:
                surface.visible = visible
                changed_count += 1
        active_region = self.app_state.region_collection.active_region
        if (
            active_region is not None
            and region_node_id(active_region.id) in node_ids
            and active_region.visible != visible
        ):
            active_region.visible = visible
            changed_count += 1
        return changed_count

    def _sync_after_scene_visibility_change(self) -> None:
        active_result = self._active_section_result()
        self.app_state.section_result = (
            active_result.result
            if active_result is not None and active_result.visible
            else None
        )
        active_plane = get_active_plane(self.app_state.section_collection)
        if active_plane is not None:
            self.show_section_plane.set(bool(active_plane.visible))
        if self.app_state.mesh_object is not None:
            self.mesh_visible.set(bool(self.app_state.mesh_object.visible))
        self._sync_visible_curve_results()
        self._sync_section_result_context_from_active_result()
        self._sync_curve_context_from_active_curve()
        self._sync_surface_context_from_active_surface()
        self._refresh_viewport(reset_camera=False)

    def hide_selected_scene_objects(self) -> None:
        node_ids = self._scene_visibility_target_node_ids()
        if not node_ids:
            self.status_text.set("No selection")
            return

        self._on_scene_browser_visibility("hide_selected", tuple(node_ids))

    def hide_unselected_scene_objects(self) -> None:
        node_ids = self._scene_visibility_target_node_ids()
        if not node_ids:
            self.status_text.set("No selection")
            return

        self._on_scene_browser_visibility("hide_unselected", tuple(node_ids))

    def show_selected_scene_objects(self) -> None:
        node_ids = self._scene_visibility_target_node_ids()
        if not node_ids:
            self.status_text.set("No selection")
            return

        self._on_scene_browser_visibility("show_selected", tuple(node_ids))

    def show_all_scene_objects(self) -> None:
        self._on_scene_browser_visibility("show_all", ())

    def toggle_selected_scene_objects(self) -> None:
        node_ids = self._scene_visibility_target_node_ids()
        if not node_ids:
            self.status_text.set("No selection")
            return

        expanded_node_ids = self._expanded_visibility_node_ids(node_ids)
        before = self._visibility_snapshot(expanded_node_ids)
        changed_count = self._toggle_scene_visibility(expanded_node_ids)
        after = self._visibility_snapshot(expanded_node_ids)
        self._push_visibility_command("Toggle Visibility", before, after)
        self._sync_after_scene_visibility_change()
        self.status_text.set(
            self._visibility_status("Toggled", changed_count, "selected item")
        )
        if changed_count and self._has_persistent_visibility_target(expanded_node_ids):
            self._set_project_dirty(True)

    def toggle_active_surface_visibility(self) -> None:
        active_surface = self._active_surface()
        if active_surface is None:
            self.status_text.set("No selection")
            return

        node_ids = {surface_node_id(active_surface.id)}
        before = self._visibility_snapshot(node_ids)
        active_surface.visible = not active_surface.visible
        after = self._visibility_snapshot(node_ids)
        self._push_visibility_command("Toggle Visibility", before, after)
        self.surface_visible.set(active_surface.visible)
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(f"Selected: {active_surface.name}")
        self._set_project_dirty(True)

    def start_move_transform(self) -> None:
        self._start_active_transform("move")

    def start_rotate_transform(self) -> None:
        self._start_active_transform("rotate")

    def _scene_visibility_target_node_ids(self) -> tuple[str, ...]:
        browser_selection = self.scene_browser.selected_node_ids()
        if browser_selection:
            node_ids = set(browser_selection)
            node_ids.update(self._node_ids_for_active_selection())
            return tuple(node_ids)

        return tuple(self._node_ids_for_active_selection())

    def _node_ids_for_active_selection(self) -> set[str]:
        selected_item = self.app_state.selected_item
        if selected_item == SELECT_MODEL and self.app_state.mesh_object is not None:
            return {NODE_MESH}
        if selected_item == SELECT_SECTION_PLANE:
            selected_ids = set(self.app_state.section_collection.selected_plane_ids)
            if selected_ids:
                return {section_plane_node_id(plane_id) for plane_id in selected_ids}
            active_plane = get_active_plane(self.app_state.section_collection)
            return {section_plane_node_id(active_plane.id)} if active_plane is not None else set()
        if selected_item == SELECT_SECTION_RESULT:
            selected_ids = set(self.app_state.section_collection.selected_result_ids)
            node_ids = (
                {section_result_node_id(result_id) for result_id in selected_ids}
                if selected_ids
                else set()
            )
            node_ids.update(
                curve_node_id(curve_id)
                for curve_id in self.app_state.curve_collection.selected_curve_ids
            )
            if node_ids:
                return node_ids
            active_result = self._active_section_result()
            return {section_result_node_id(active_result.id)} if active_result is not None else set()
        if selected_item == SELECT_CURVE:
            return {
                curve_node_id(curve_id)
                for curve_id in self.app_state.curve_collection.selected_curve_ids
            }
        if selected_item == SELECT_SURFACE:
            selected_ids = set(self.app_state.surface_collection.selected_surface_ids)
            if selected_ids:
                return {surface_node_id(surface_id) for surface_id in selected_ids}
            active_surface = self._active_surface()
            return {surface_node_id(active_surface.id)} if active_surface is not None else set()
        if selected_item == SELECT_REGION:
            region = self.app_state.region_collection.active_region
            return {region_node_id(region.id)} if region is not None else set()
        return set()

    def _on_section_axis_changed(self, _event: object | None = None) -> None:
        reset_to_axis_aligned = self._sync_active_section_plane_from_controls()
        self._configure_offset_range(reset=False)
        self._update_section_plane_label(set_status=True)
        if reset_to_axis_aligned:
            self.status_text.set(
                f"Section plane reset to axis-aligned {self.section_axis.get()} mode"
            )
        self._clear_section_for_plane_change()
        self._refresh_viewport(reset_camera=False)
        self._set_project_dirty(True)

    def _on_offset_slider_changed(self, value: object) -> None:
        if self._updating_offset:
            return

        self._set_section_offset(float(value), clamp=False, refresh=True, mark_dirty=True)

    def _on_offset_input_changed(self, _event: object | None = None) -> None:
        if self._updating_offset:
            return

        offset = self._parse_offset(show_error=False)
        if offset is None:
            return

        self._set_section_offset(offset, clamp=True, refresh=True, mark_dirty=True)

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
        mark_dirty: bool = False,
        clear_section: bool = True,
        sync_plane: bool = True,
    ) -> None:
        minimum, maximum = self._section_offset_bounds
        next_offset = min(max(float(offset), minimum), maximum) if clamp else float(offset)
        self._updating_offset = True
        try:
            self.section_offset.set(next_offset)
            self.section_offset_text.set(f"{next_offset:.3f}")
        finally:
            self._updating_offset = False

        reset_to_axis_aligned = False
        if sync_plane:
            reset_to_axis_aligned = self._sync_active_section_plane_from_controls()
        self._update_section_plane_label(set_status=True)
        if reset_to_axis_aligned:
            self.status_text.set(
                f"Section plane reset to axis-aligned {self.section_axis.get()} mode"
            )
        if clear_section:
            self._clear_section_for_plane_change()
        if refresh:
            self._refresh_viewport(reset_camera=False)
        if mark_dirty:
            self._set_project_dirty(True)

    def _configure_offset_range(
        self,
        *,
        reset: bool,
        clear_section: bool = True,
    ) -> None:
        minimum, maximum = self._update_section_offset_range()

        current = self.section_offset.get()
        if reset:
            current = 0.0 if minimum <= 0.0 <= maximum else (minimum + maximum) * 0.5

        self._set_section_offset(
            current,
            clamp=True,
            refresh=False,
            clear_section=clear_section,
        )

    def _update_section_offset_range(self) -> tuple[float, float]:
        if self.app_state.mesh_object is None:
            self._section_offset_bounds = (-1.0, 1.0)
            self.offset_slider.configure(from_=-1.0, to=1.0)
            return self._section_offset_bounds

        axis_index = AXIS_TO_INDEX[self.section_axis.get()]
        minimum_bound, maximum_bound = self._transformed_source_bounds()
        minimum = float(minimum_bound[axis_index])
        maximum = float(maximum_bound[axis_index])
        if abs(maximum - minimum) <= 1e-9:
            minimum -= 1.0
            maximum += 1.0

        self._section_offset_bounds = (minimum, maximum)
        self.offset_slider.configure(from_=minimum, to=maximum)
        return self._section_offset_bounds

    def _update_section_plane_label(self, *, set_status: bool) -> None:
        axis = self.section_axis.get()
        offset = self.section_offset.get()
        active_plane = get_active_plane(self.app_state.section_collection)
        label = f"Section: {axis} = {offset:.3f}"
        if active_plane is not None:
            normal = plane_normal(active_plane)
            axis_vector = world_axis_vector(axis)
            if not np.allclose(normal, axis_vector, atol=1e-6):
                label = (
                    "Section: "
                    f"n=({normal[0]:.2f}, {normal[1]:.2f}, {normal[2]:.2f}) "
                    f"d={active_plane.offset:.3f}"
                )
        self.section_plane_text.set(label)
        if set_status and self.app_state.selected_item == SELECT_SECTION_PLANE:
            self.status_text.set(label.replace("Section:", "Section plane:", 1))

    def _clear_section_for_plane_change(self) -> None:
        active_plane = get_active_plane(self.app_state.section_collection)
        had_active_results = (
            active_plane is not None
            and any(
                result.plane_id == active_plane.id
                for result in self.app_state.section_collection.results
            )
        )
        if (
            not had_active_results
            and self.app_state.section_result is None
            and not self.app_state.curve_results
        ):
            return

        if active_plane is not None:
            curve_ids = [
                curve.id
                for curve in self.app_state.curve_collection.curves
                if curve.plane_id == active_plane.id
            ]
            self._clear_surfaces_for_curve_ids(curve_ids)
            clear_curves_for_plane(self.app_state.curve_collection, active_plane.id)
            clear_results_for_plane(self.app_state.section_collection, active_plane.id)
        self._set_display_section_result(self._latest_stored_section_result())

    def _has_generated_geometry(self) -> bool:
        return bool(
            self.app_state.section_collection.results
            or self.app_state.curve_collection.curves
            or self.app_state.surface_collection.surfaces
        )

    def _model_transform_status(self, default_status: str) -> str:
        if self._has_generated_geometry():
            return GENERATED_GEOMETRY_TRANSFORM_WARNING
        return default_status

    def _on_object_transform_changed(self, _event: object | None = None) -> None:
        if self.app_state.selected_item != SELECT_MODEL or self.app_state.mesh_object is None:
            return

        values = self._parse_object_transform(show_error=False)
        if values is None:
            return

        location, rotation, scale = values
        self.app_state.mesh_object.location = location
        self.app_state.mesh_object.rotation = rotation
        self.app_state.mesh_object.scale = scale
        self._apply_object_transform(reset_camera=False)
        self.status_text.set(self._model_transform_status("Transforms update live"))
        self._set_project_dirty(True)

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
        if self.app_state.mesh_object is None:
            self.mesh_state = MeshState()
            self._update_stats()
            self._refresh_viewport(reset_camera=reset_camera)
            return

        self.app_state.mesh_object.transform_matrix = build_object_transform_matrix(
            self.app_state.mesh_object.location,
            self.app_state.mesh_object.rotation,
            self.app_state.mesh_object.scale,
            self.app_state.mesh_object.origin,
        )
        self.mesh_state = MeshState.from_mesh(
            self.app_state.mesh_object.display_mesh,
            file_path=self.app_state.mesh_object.file_path,
        )
        self._update_stats()
        self._configure_offset_range(reset=False, clear_section=False)
        self._refresh_viewport(reset_camera=reset_camera)

    def _apply_display_mesh_result(self, display_result: DisplayMeshResult) -> None:
        if self.app_state.mesh_object is None:
            return

        self.app_state.mesh_object.display_mesh = display_result.display_mesh
        self.app_state.mesh_object.source_triangle_count = display_result.source_triangle_count
        self.app_state.mesh_object.display_triangle_count = display_result.display_triangle_count
        self.app_state.mesh_object.display_proxy_enabled = display_result.proxy_enabled
        self.app_state.mesh_object.display_reduction_percent = display_result.reduction_percent
        self.app_state.mesh_object.proxy_quality = display_result.quality
        self.mesh_state = MeshState.from_mesh(
            self.app_state.mesh_object.display_mesh,
            file_path=self.app_state.mesh_object.file_path,
        )

    def set_origin_to_geometry(self) -> None:
        if self.app_state.mesh_object is None:
            self.status_text.set("No selection")
            return

        minimum_bound, maximum_bound = self._transformed_source_bounds()
        current_center = (minimum_bound + maximum_bound) * 0.5
        new_origin = transform_point(
            np.linalg.inv(self._current_object_matrix()),
            current_center,
        )
        self._change_origin_keep_geometry(new_origin)
        self.status_text.set(self._model_transform_status("Origin set to geometry"))
        self._set_project_dirty(True)

    def move_origin_to_world_origin(self) -> None:
        if self.app_state.mesh_object is None:
            self.status_text.set("No selection")
            return

        new_origin, new_location = calculate_origin_to_world_origin(
            self.app_state.mesh_object.origin,
            self.app_state.mesh_object.location,
            self.app_state.mesh_object.rotation,
            self.app_state.mesh_object.scale,
        )
        self.app_state.mesh_object.origin = new_origin
        self.app_state.mesh_object.location = new_location
        self._set_transform_inputs_from_object()
        self._apply_object_transform(reset_camera=False)
        self.status_text.set(self._model_transform_status("Origin moved to world origin"))
        self._set_project_dirty(True)

    def center_geometry_on_origin(self) -> None:
        if self.app_state.mesh_object is None:
            self.status_text.set("No selection")
            return

        bounds = self.app_state.mesh_object.source_mesh.get_axis_aligned_bounding_box()
        raw_center = np.asarray(bounds.get_center(), dtype=float)
        delta = calculate_geometry_centering_delta(self.app_state.mesh_object.origin, raw_center)
        self.app_state.mesh_object.source_mesh.translate(delta.tolist())
        self.app_state.mesh_object.display_mesh.translate(delta.tolist())
        self.app_state.mesh_object.source_bounds_min = np.asarray(
            bounds.get_min_bound(),
            dtype=float,
        ) + delta
        self.app_state.mesh_object.source_bounds_max = np.asarray(
            bounds.get_max_bound(),
            dtype=float,
        ) + delta
        self._apply_object_transform(reset_camera=False)
        self.status_text.set(self._model_transform_status("Geometry centered on origin"))
        self._set_project_dirty(True)

    def reset_object_transform(self) -> None:
        if self.app_state.mesh_object is None:
            self.status_text.set("No selection")
            return

        self.app_state.mesh_object.location = self.app_state.mesh_object.origin.copy()
        self.app_state.mesh_object.rotation = np.asarray([0.0, 0.0, 0.0], dtype=float)
        self.app_state.mesh_object.scale = 1.0
        self._set_transform_inputs_from_object()
        self._apply_object_transform(reset_camera=True)
        self.status_text.set(
            self._model_transform_status("Selected: " + self.app_state.mesh_object.name)
        )
        self._set_project_dirty(True)

    def _change_origin_keep_geometry(self, new_origin: np.ndarray) -> None:
        if self.app_state.mesh_object is None:
            return

        old_origin = self.app_state.mesh_object.origin.copy()
        self.app_state.mesh_object.origin = np.asarray(new_origin, dtype=float)
        self.app_state.mesh_object.location = calculate_location_for_origin_change(
            self.app_state.mesh_object.location,
            self.app_state.mesh_object.rotation,
            self.app_state.mesh_object.scale,
            old_origin,
            self.app_state.mesh_object.origin,
        )
        self._set_transform_inputs_from_object()
        self._apply_object_transform(reset_camera=False)

    def _current_object_matrix(self) -> np.ndarray:
        if self.app_state.mesh_object is None:
            return np.identity(4)

        return build_object_transform_matrix(
            self.app_state.mesh_object.location,
            self.app_state.mesh_object.rotation,
            self.app_state.mesh_object.scale,
            self.app_state.mesh_object.origin,
        )

    def _set_transform_inputs_from_object(self) -> None:
        if self.app_state.mesh_object is None:
            location = np.asarray([0.0, 0.0, 0.0], dtype=float)
            rotation = np.asarray([0.0, 0.0, 0.0], dtype=float)
            scale = 1.0
        else:
            location = self.app_state.mesh_object.location
            rotation = self.app_state.mesh_object.rotation
            scale = self.app_state.mesh_object.scale

        self.location_x.set(f"{location[0]:.3f}")
        self.location_y.set(f"{location[1]:.3f}")
        self.location_z.set(f"{location[2]:.3f}")
        self.rotation_x.set(f"{rotation[0]:.3f}")
        self.rotation_y.set(f"{rotation[1]:.3f}")
        self.rotation_z.set(f"{rotation[2]:.3f}")
        self.scale_value.set(f"{scale:.3f}")

    def _update_stats(self) -> None:
        if self.app_state.mesh_object is None:
            loaded_file_name = "(none)"
            object_name = "(none)"
            mesh_visible = True
            vertex_count = "0"
            source_triangles = "0"
            display_triangles = "0"
            reduction = "0.0%"
            display_proxy = f"Disabled ({self.proxy_quality.get()})"
            source_retained = "(none)"
            bbox_extent = "-"
        else:
            minimum_bound, maximum_bound = self._transformed_source_bounds()
            loaded_file_name = (
                self.app_state.mesh_object.file_path.name
                if self.app_state.mesh_object.file_path is not None
                else "(unsaved mesh)"
            )
            object_name = self.app_state.mesh_object.name
            mesh_visible = bool(self.app_state.mesh_object.visible)
            vertex_count = _format_count(len(self.app_state.mesh_object.source_mesh.vertices))
            source_triangles = _format_count(self.app_state.mesh_object.source_triangle_count)
            display_triangles = _format_count(self.app_state.mesh_object.display_triangle_count)
            reduction = _format_percent(self.app_state.mesh_object.display_reduction_percent)
            display_proxy = (
                f"Enabled ({self.app_state.mesh_object.proxy_quality})"
                if self.app_state.mesh_object.display_proxy_enabled
                else f"Disabled ({self.app_state.mesh_object.proxy_quality})"
            )
            source_retained = "Full-resolution source preserved"
            bbox_extent = _format_vector(maximum_bound - minimum_bound)

        self.file_name_text.set(loaded_file_name)
        self.vertex_count_text.set(vertex_count)
        self.triangle_count_text.set(source_triangles)
        self.display_triangle_count_text.set(display_triangles)
        self.display_reduction_text.set(reduction)
        self.display_proxy_text.set(display_proxy)
        self.source_retained_text.set(source_retained)
        self.bbox_size_text.set(bbox_extent)
        self.mesh_name_text.set(object_name)
        self.mesh_visible.set(mesh_visible)
        self.selected_object_text.set(object_name)
        self.selected_vertex_count_text.set(vertex_count)
        self.selected_triangle_count_text.set(source_triangles)
        self.selected_display_triangle_count_text.set(display_triangles)
        self.selected_display_reduction_text.set(reduction)
        self.selected_display_proxy_text.set(display_proxy)
        self.selected_bbox_size_text.set(bbox_extent)

    def _display_mesh_status(self, display_result: DisplayMeshResult) -> str:
        proxy_status = (
            f"Proxy {display_result.quality}"
            if display_result.proxy_enabled
            else f"No proxy ({display_result.quality})"
        )
        return (
            f"Source: {_format_count(display_result.source_triangle_count)} tris | "
            f"Display: {_format_count(display_result.display_triangle_count)} tris | "
            f"Reduction: {_format_percent(display_result.reduction_percent)} | "
            f"{proxy_status} | Full-resolution source preserved"
        )

    def _transformed_source_bounds(self) -> tuple[np.ndarray, np.ndarray]:
        if (
            self.app_state.mesh_object is None
            or self.app_state.mesh_object.source_bounds_min is None
            or self.app_state.mesh_object.source_bounds_max is None
        ):
            zero = np.asarray([0.0, 0.0, 0.0], dtype=float)
            return (zero, zero)

        return transform_bounds(
            self.app_state.mesh_object.source_bounds_min,
            self.app_state.mesh_object.source_bounds_max,
            self._current_object_matrix(),
        )

    def _transformed_source_mesh(self) -> TriangleMeshData:
        if self.app_state.mesh_object is None:
            return TriangleMeshData(
                vertices=np.zeros((0, 3), dtype=float),
                triangles=np.zeros((0, 3), dtype=int),
            )

        mesh = self.app_state.mesh_object.source_mesh.copy()
        mesh.transform(self._current_object_matrix())
        return mesh

    def _start_active_transform(self, mode: str) -> None:
        if self.app_state.selected_item is None or self.app_state.mesh_object is None:
            self.status_text.set("No selection")
            return

        section_origin = np.asarray([0.0, 0.0, 0.0], dtype=float)
        section_normal = np.asarray([0.0, 0.0, 1.0], dtype=float)
        section_axis = self.section_axis.get()
        section_offset = float(self.section_offset.get())
        section_plane_id: str | None = None
        section_plane_name: str | None = None
        if self.app_state.selected_item == SELECT_SECTION_PLANE:
            if len(self.app_state.section_collection.selected_plane_ids) != 1:
                self.status_text.set("Select one section plane to transform.")
                return

            active_plane = get_active_plane(self.app_state.section_collection)
            if active_plane is None:
                self.status_text.set("No section plane")
                return
            if active_plane.id not in self.app_state.section_collection.selected_plane_ids:
                self.status_text.set("Select one section plane to transform.")
                return
            section_origin = plane_origin(active_plane)
            section_normal = plane_normal(active_plane)
            section_axis = active_plane.axis
            section_offset = active_plane.offset
            section_plane_id = active_plane.id
            section_plane_name = active_plane.name

        if self._region_select_active:
            self._exit_region_select_mode()

        self.app_state.transform_state = ActiveTransformState(
            selected_item=self.app_state.selected_item,
            mode=mode,
            mouse_start=self._last_viewport_mouse,
            axis_constraint=None,
            location=self.app_state.mesh_object.location.copy(),
            rotation=self.app_state.mesh_object.rotation.copy(),
            section_axis=section_axis,
            section_offset=section_offset,
            section_origin=section_origin,
            section_normal=section_normal,
            section_plane_id=section_plane_id,
            section_plane_name=section_plane_name,
        )
        self.app_state.active_transform_mode = mode
        self.app_state.active_transform_axis = self._display_transform_axis(self.app_state.transform_state)
        self._last_transform_readout = None
        self._active_transform_angle_delta = 0.0 if mode == "rotate" else None
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(self._active_transform_status())
        self._sync_workflow_ui()

    def _set_transform_axis_constraint(self, axis: str) -> None:
        axis = axis.upper()
        if axis == "N":
            state = self.app_state.transform_state
            if (
                state is None
                or state.selected_item != SELECT_SECTION_PLANE
                or state.mode != "move"
            ):
                self.status_text.set(
                    "Move Along Plane Normal is available while moving a section plane"
                )
                return
        elif axis not in {"X", "Y", "Z"}:
            return

        if self.app_state.transform_state is None:
            self.app_state.active_transform_axis = axis
            self.status_text.set(f"Axis constraint: {axis}")
            return

        next_axis = None if self.app_state.transform_state.axis_constraint == axis else axis
        self.app_state.transform_state.axis_constraint = next_axis
        self.app_state.active_transform_axis = self._display_transform_axis(self.app_state.transform_state)
        self._last_transform_readout = None
        self._active_transform_angle_delta = (
            0.0 if self.app_state.transform_state.mode == "rotate" else None
        )
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(self._active_transform_status())
        self._update_command_strip()

    def _update_active_transform(
        self,
        mouse_position: tuple[int, int],
        *,
        fine: bool,
    ) -> None:
        state = self.app_state.transform_state
        if state is None:
            return

        if state.selected_item == SELECT_MODEL:
            if state.mode == "move":
                self._update_mesh_move_transform(state, mouse_position, fine=fine)
            elif state.mode == "rotate":
                self._update_mesh_rotate_transform(state, mouse_position, fine=fine)
        elif state.selected_item == SELECT_SECTION_PLANE:
            if state.mode == "move":
                self._update_section_plane_move_transform(state, mouse_position, fine=fine)
            elif state.mode == "rotate":
                self._update_section_plane_rotate_transform(state, mouse_position, fine=fine)

    def _update_mesh_move_transform(
        self,
        state: ActiveTransformState,
        mouse_position: tuple[int, int],
        *,
        fine: bool,
    ) -> None:
        if self.app_state.mesh_object is None:
            return

        minimum_bound, maximum_bound = self._transformed_source_bounds()
        model_diagonal = float(np.linalg.norm(maximum_bound - minimum_bound))
        camera_vectors = self.viewport.get_camera_vectors()
        if state.axis_constraint is None:
            movement, readout = camera_relative_move_delta(
                state.mouse_start,
                mouse_position,
                camera_vectors.right,
                camera_vectors.up,
                model_diagonal,
                fine=fine,
            )
        else:
            movement, amount = axis_constrained_camera_move_delta(
                state.mouse_start,
                mouse_position,
                world_axis_vector(state.axis_constraint),
                camera_vectors.right,
                camera_vectors.up,
                model_diagonal,
                fine=fine,
            )
            readout = f"Delta {state.axis_constraint}: {amount:.2f}"

        self._last_transform_readout = readout
        self._active_transform_angle_delta = None
        self.app_state.mesh_object.location = state.location + movement
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
        if self.app_state.mesh_object is None:
            return

        # Rotation remains screen-horizontal for now; camera-relative rotation needs a dedicated pass.
        axis = self._display_transform_axis(state) or "Z"
        rotation, angle_delta = mesh_rotate_delta(
            state.mouse_start,
            mouse_position,
            state.rotation,
            axis,
            fine=fine,
        )
        self.app_state.active_transform_axis = axis
        self._last_transform_readout = f"{angle_delta:.1f} deg"
        self._active_transform_angle_delta = angle_delta
        self.app_state.mesh_object.rotation = rotation
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
        active_plane = self._section_plane_for_transform_state(state)
        if active_plane is None:
            return

        minimum_bound, maximum_bound = self._transformed_source_bounds()
        model_diagonal = float(np.linalg.norm(maximum_bound - minimum_bound))
        camera_vectors = self.viewport.get_camera_vectors()
        if state.axis_constraint is None:
            movement, readout = camera_relative_move_delta(
                state.mouse_start,
                mouse_position,
                camera_vectors.right,
                camera_vectors.up,
                model_diagonal,
                fine=fine,
            )
            readout = self._section_movement_readout(movement)
        elif state.axis_constraint == "N":
            movement, amount = axis_constrained_camera_move_delta(
                state.mouse_start,
                mouse_position,
                state.section_normal,
                camera_vectors.right,
                camera_vectors.up,
                model_diagonal,
                fine=fine,
            )
            readout = f"{amount:.3f}"
        else:
            movement, amount = axis_constrained_camera_move_delta(
                state.mouse_start,
                mouse_position,
                world_axis_vector(state.axis_constraint),
                camera_vectors.right,
                camera_vectors.up,
                model_diagonal,
                fine=fine,
            )
            readout = f"Delta {state.axis_constraint} {amount:.3f}"

        set_plane_origin_normal(
            active_plane,
            state.section_origin + movement,
            state.section_normal,
        )
        self._sync_section_controls_from_plane_orientation(active_plane)
        self._last_transform_readout = readout
        self._active_transform_angle_delta = None
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(self._active_transform_status())

    def _update_section_plane_rotate_transform(
        self,
        state: ActiveTransformState,
        mouse_position: tuple[int, int],
        *,
        fine: bool,
    ) -> None:
        active_plane = self._section_plane_for_transform_state(state)
        if active_plane is None:
            return

        axis = self._display_transform_axis(state)
        _rotation_delta, angle_delta = mesh_rotate_delta(
            state.mouse_start,
            mouse_position,
            np.asarray([0.0, 0.0, 0.0], dtype=float),
            axis or "Z",
            fine=fine,
        )
        rotation_axis = (
            world_axis_vector(axis)
            if axis in {"X", "Y", "Z"}
            else self._section_view_rotation_axis(state)
        )
        normal = rotate_vector_around_axis(
            state.section_normal,
            rotation_axis,
            angle_delta,
        )
        set_plane_origin_normal(active_plane, state.section_origin, normal)
        self._sync_section_controls_from_plane_orientation(active_plane)
        self.app_state.active_transform_axis = axis
        self._last_transform_readout = f"{angle_delta:.1f} deg"
        self._active_transform_angle_delta = angle_delta
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(self._active_transform_status())

    def _end_active_transform(self, *, commit: bool, status: str) -> None:
        state = self.app_state.transform_state
        if state is None:
            return

        if not commit:
            self._restore_transform_start_state(state)

        self.app_state.transform_state = None
        self.app_state.active_transform_mode = None
        self.app_state.active_transform_axis = None
        self._last_transform_readout = None
        self._active_transform_angle_delta = None
        if commit and state.selected_item == SELECT_SECTION_PLANE:
            if self._section_transform_changed(state):
                self._clear_section_for_plane_change()
            active_plane = self._section_plane_for_transform_state(state)
            if active_plane is not None:
                self._sync_section_controls_from_plane_orientation(active_plane)
        self._refresh_viewport(reset_camera=False)
        if commit and state.selected_item == SELECT_MODEL:
            status = self._model_transform_status(status)
        self.status_text.set(status)
        if commit:
            self._set_project_dirty(True)
        self._sync_workflow_ui()

    def _restore_transform_start_state(self, state: ActiveTransformState) -> None:
        if state.selected_item == SELECT_MODEL and self.app_state.mesh_object is not None:
            self.app_state.mesh_object.location = state.location.copy()
            self.app_state.mesh_object.rotation = state.rotation.copy()
            self._set_transform_inputs_from_object()
            self._apply_object_transform(reset_camera=False)
            return

        if state.selected_item == SELECT_SECTION_PLANE:
            active_plane = self._section_plane_for_transform_state(state)
            if active_plane is None:
                return
            active_plane.axis = normalize_axis(state.section_axis)
            set_plane_origin_normal(
                active_plane,
                state.section_origin.copy(),
                state.section_normal.copy(),
            )
            active_plane.offset = float(state.section_offset)
            self._sync_section_controls_from_plane_orientation(active_plane)

    def _section_transform_changed(self, state: ActiveTransformState) -> bool:
        active_plane = self._section_plane_for_transform_state(state)
        if active_plane is None:
            return False

        return not (
            np.allclose(plane_origin(active_plane), state.section_origin, atol=1e-8)
            and np.allclose(plane_normal(active_plane), state.section_normal, atol=1e-8)
        )

    def _section_plane_for_transform_state(
        self,
        state: ActiveTransformState,
    ) -> SectionPlaneState | None:
        if state.section_plane_id is not None:
            for plane in self.app_state.section_collection.planes:
                if plane.id == state.section_plane_id:
                    return plane

        return get_active_plane(self.app_state.section_collection)

    def _section_view_rotation_axis(self, state: ActiveTransformState) -> np.ndarray:
        camera_vectors = self.viewport.get_camera_vectors()
        plane_normal_vector = normalized_vector(
            state.section_normal,
            fallback=np.asarray([0.0, 0.0, 1.0], dtype=float),
        )
        for candidate in (camera_vectors.up, camera_vectors.right, camera_vectors.forward):
            candidate_axis = normalized_vector(
                np.asarray(candidate, dtype=float),
                fallback=np.asarray([1.0, 0.0, 0.0], dtype=float),
            )
            if abs(float(np.dot(candidate_axis, plane_normal_vector))) < 0.92:
                return candidate_axis

        return world_axis_vector("X")

    def _cycle_section_axis_for_rotation(self) -> None:
        current_index = SECTION_AXES.index(self.section_axis.get())
        next_axis = SECTION_AXES[(current_index + 1) % len(SECTION_AXES)]
        self.section_axis.set(next_axis)
        self._configure_offset_range(reset=False)
        self._update_section_plane_label(set_status=False)
        self._clear_section_for_plane_change()
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(f"Section plane axis cycled to {next_axis}")
        self._set_project_dirty(True)

    def _active_transform_status(self) -> str:
        if self.app_state.transform_state is None:
            return "No selection" if self.app_state.selected_item is None else "Transform"

        state = self.app_state.transform_state
        if state.selected_item == SELECT_SECTION_PLANE:
            return self._section_plane_transform_status(state)

        mode_label = "Move mode" if state.mode == "move" else "Rotate mode"
        axis = self._display_transform_axis(state)
        parts = [mode_label]
        if axis is not None:
            parts.append(f"{axis} axis")
        if self._last_transform_readout is not None:
            parts.append(self._last_transform_readout)
        elif state.mode == "move" and axis is None:
            parts.append(
                "press X/Y/Z to constrain, Enter/Click to confirm, Esc/Right-click to cancel"
            )
        elif state.mode == "rotate":
            parts.append("move mouse horizontally")
        return " - ".join(parts)

    def _display_transform_axis(self, state: ActiveTransformState) -> str | None:
        if state.mode == "rotate":
            if state.selected_item == SELECT_SECTION_PLANE:
                return state.axis_constraint
            return state.axis_constraint or "Z"
        if state.selected_item == SELECT_SECTION_PLANE:
            return state.axis_constraint
        return state.axis_constraint

    def _section_plane_transform_status(self, state: ActiveTransformState) -> str:
        plane_name = state.section_plane_name or "Section Plane"
        axis = self._display_transform_axis(state)
        if state.mode == "move":
            if self._last_transform_readout is None:
                if axis == "N":
                    return f"Moving {plane_name} along normal: drag mouse"
                if axis in {"X", "Y", "Z"}:
                    return f"Moving {plane_name} along {axis}: drag mouse"
                return (
                    f"Moving {plane_name}: camera-relative grab "
                    "(X/Y/Z constrain, N normal, Enter/click confirm, Esc cancel)"
                )
            if axis == "N":
                return f"Moving {plane_name} along normal: {self._last_transform_readout}"
            return f"Moving {plane_name}: {self._last_transform_readout}"

        axis_label = axis if axis in {"X", "Y", "Z"} else "view"
        if self._last_transform_readout is None:
            return f"Rotating {plane_name} around {axis_label}: move mouse horizontally"
        return f"Rotating {plane_name} around {axis_label}: {self._last_transform_readout}"

    @staticmethod
    def _section_movement_readout(movement: np.ndarray) -> str:
        values = np.asarray(movement, dtype=float)
        return (
            f"Delta X {values[0]:.3f}, "
            f"Delta Y {values[1]:.3f}, "
            f"Delta Z {values[2]:.3f}"
        )

    def rename_selected(self) -> None:
        renameable_node_ids = self._renameable_selected_node_ids()
        if len(renameable_node_ids) > 1:
            self.status_text.set("Select one object to rename.")
            return

        entry = self._rename_entry_for_selection()
        if entry is None:
            self.status_text.set(
                "Select one object to rename."
                if len(renameable_node_ids) != 1
                else "No renameable selection"
            )
            return

        entry.focus_set()
        entry.selection_range(0, "end")
        self.status_text.set("Rename selected object")

    def _renameable_selected_node_ids(self) -> set[str]:
        node_ids = set(self.scene_browser.selected_node_ids())
        if not node_ids:
            node_ids = self._node_ids_for_active_selection()
        return {
            node_id
            for node_id in node_ids
            if self._is_renameable_scene_node_id(node_id)
        }

    def _is_renameable_scene_node_id(self, node_id: str) -> bool:
        return (
            node_id == NODE_MESH
            or section_plane_id_from_node(node_id) is not None
            or section_result_id_from_node(node_id) is not None
            or curve_id_from_node(node_id) is not None
            or surface_id_from_node(node_id) is not None
            or region_id_from_node(node_id) is not None
        )

    def _rename_entry_for_selection(self) -> ttk.Entry | None:
        selected_item = self.app_state.selected_item
        if selected_item == SELECT_MODEL and self.app_state.mesh_object is not None:
            return self.mesh_name_entry
        if selected_item == SELECT_SECTION_PLANE and get_active_plane(self.app_state.section_collection) is not None:
            return self.section_plane_name_entry
        if selected_item == SELECT_SECTION_RESULT and self._active_section_result() is not None:
            return self.section_result_name_entry
        if selected_item == SELECT_CURVE and self._active_curve() is not None:
            return self.curve_name_entry
        if selected_item == SELECT_SURFACE and self._active_surface() is not None:
            return self.surface_name_entry
        if (
            selected_item == SELECT_REGION
            and self.app_state.region_collection.active_region is not None
        ):
            return self.region_name_entry
        return None

    def _handle_keybind_action(self, action: str) -> None:
        action_map = {
            "undo": self.undo,
            "redo": self.redo,
            "rename_selected": lambda: self._handle_shortcut("F2"),
            "toggle_visibility": lambda: self._handle_shortcut("H"),
            "isolate_selected": lambda: self._handle_shortcut("Shift+H"),
            "show_all": lambda: self._handle_shortcut("Alt+H"),
            "frame_selected": lambda: self._handle_shortcut("F"),
            "move": lambda: self._handle_shortcut("G"),
            "rotate": lambda: self._handle_shortcut("R"),
            "confirm_transform": lambda: self._handle_shortcut("Enter"),
            "cancel_transform": lambda: self._handle_shortcut("Esc"),
            "delete_selected": lambda: self._handle_shortcut("Delete"),
        }
        handler = action_map.get(action)
        if handler is not None:
            handler()

    def _handle_shortcut(self, key: str) -> None:
        if self._manual_curve_active:
            if key in {"Backspace", "C", "Enter", "Escape", "Esc"}:
                self._handle_manual_curve_shortcut(key)
            else:
                self.status_text.set(self._manual_curve_status())
            return

        if self._region_select_active and key in {"Escape", "Esc"}:
            self._exit_region_select_mode(status="Region Select cancelled")
            return

        if key == "F":
            self.frame_selected()
            return

        if key == "F2":
            self.rename_selected()
            return

        if key == "H":
            self.toggle_selected_scene_objects()
            return

        if key == "Shift+H":
            self.hide_unselected_scene_objects()
            return

        if key == "Alt+H":
            self.show_all_scene_objects()
            return

        if key == "Delete":
            self._delete_selected_if_safe()
            return

        if key in {"Escape", "Esc"}:
            if self.app_state.transform_state is None:
                self.app_state.active_transform_mode = None
                self.app_state.active_transform_axis = None
                self._active_transform_angle_delta = None
                self.status_text.set("Transform cancelled")
            else:
                self._end_active_transform(commit=False, status="Transform cancelled")
            return

        if key == "Enter":
            if self.app_state.transform_state is None:
                self.app_state.active_transform_mode = None
                self.app_state.active_transform_axis = None
                self._active_transform_angle_delta = None
                self.status_text.set("Transform confirmed")
            else:
                self._end_active_transform(commit=True, status="Transform confirmed")
            return

        if key in {"X", "Y", "Z", "N"}:
            self._set_transform_axis_constraint(key)
            return

        if key == "G":
            self._start_active_transform("move")
            return

        if key == "R":
            self._start_active_transform("rotate")

    def _delete_selected_if_safe(self) -> None:
        self.delete_selected_scene_objects()

    def delete_selected_scene_objects(self) -> None:
        node_ids = self._scene_visibility_target_node_ids()
        if not node_ids:
            self.status_text.set("No selection")
            return

        expanded_node_ids = self._expanded_visibility_node_ids(node_ids)
        if self.app_state.mesh_object is not None and NODE_MESH in expanded_node_ids:
            self.delete_mesh()
            return

        delete_targets = self._delete_targets_for_node_ids(node_ids)
        deleted_count = (
            len(delete_targets["section_planes"])
            + len(delete_targets["section_results"])
            + len(delete_targets["curves"])
            + len(delete_targets["surfaces"])
            + len(delete_targets["regions"])
        )
        if deleted_count == 0:
            if NODE_MESH in expanded_node_ids:
                self.status_text.set("Mesh deletion is not implemented yet.")
            else:
                self.status_text.set("No deletable selection")
            return

        undo_command = self._delete_undo_command_for_targets(delete_targets)
        self._apply_delete_targets(delete_targets)
        if undo_command is not None:
            self._push_undo_command(undo_command)
        self._set_display_section_result(self._latest_stored_section_result())
        self._sync_visible_curve_results()
        self._sync_section_controls_from_active_plane()
        self._sync_section_result_context_from_active_result()
        self._sync_curve_context_from_active_curve()
        self._sync_surface_context_from_active_surface()
        self._select_delete_fallback(delete_targets)
        self.status_text.set(
            "Region deleted."
            if deleted_count == 1 and delete_targets["regions"]
            else "Deleted selected object"
            if deleted_count == 1
            else f"Deleted {deleted_count} selected objects"
        )
        if deleted_count != 1 or not delete_targets["regions"]:
            self._set_project_dirty(True)

    def _delete_targets_for_node_ids(
        self,
        node_ids: tuple[str, ...],
    ) -> dict[str, set[str]]:
        section_plane_ids: set[str] = set()
        section_result_ids: set[str] = set()
        curve_ids: set[str] = set()
        surface_ids: set[str] = set()
        region_ids: set[str] = set()

        for node_id in node_ids:
            plane_id = section_plane_id_from_node(node_id)
            result_id = section_result_id_from_node(node_id)
            curve_group_id = curve_group_id_from_node(node_id)
            curve_id = curve_id_from_node(node_id)
            surface_id = surface_id_from_node(node_id)
            region_id = region_id_from_node(node_id)
            if node_id == NODE_SECTION_PLANES:
                section_plane_ids.update(
                    plane.id for plane in self.app_state.section_collection.planes
                )
            elif plane_id is not None:
                section_plane_ids.add(plane_id)
            elif node_id == NODE_SECTION_RESULTS:
                section_result_ids.update(
                    result.id for result in self.app_state.section_collection.results
                )
            elif result_id is not None:
                section_result_ids.add(result_id)
            elif node_id == NODE_CURVES:
                curve_ids.update(curve.id for curve in self.app_state.curve_collection.curves)
            elif curve_group_id is not None:
                curve_ids.update(self._curve_ids_for_group(curve_group_id))
            elif curve_id is not None:
                curve_ids.add(curve_id)
            elif node_id == NODE_SURFACES:
                surface_ids.update(
                    surface.id for surface in self.app_state.surface_collection.surfaces
                )
            elif surface_id is not None:
                surface_ids.add(surface_id)
            elif node_id == NODE_REGIONS:
                region = self.app_state.region_collection.active_region
                if region is not None:
                    region_ids.add(region.id)
            elif region_id is not None:
                region_ids.add(region_id)

        section_result_ids.update(
            result.id
            for result in self.app_state.section_collection.results
            if result.plane_id in section_plane_ids
        )
        curve_ids.update(
            curve.id
            for curve in self.app_state.curve_collection.curves
            if curve.section_result_id in section_result_ids or curve.plane_id in section_plane_ids
        )
        surface_ids.update(
            surface.id
            for surface in self.app_state.surface_collection.surfaces
            if any(curve_id in curve_ids for curve_id in surface.source_curve_ids)
        )

        existing_plane_ids = {plane.id for plane in self.app_state.section_collection.planes}
        existing_result_ids = {result.id for result in self.app_state.section_collection.results}
        existing_curve_ids = {curve.id for curve in self.app_state.curve_collection.curves}
        existing_surface_ids = {surface.id for surface in self.app_state.surface_collection.surfaces}
        active_region = self.app_state.region_collection.active_region
        existing_region_ids = {active_region.id} if active_region is not None else set()
        return {
            "section_planes": section_plane_ids & existing_plane_ids,
            "section_results": section_result_ids & existing_result_ids,
            "curves": curve_ids & existing_curve_ids,
            "surfaces": surface_ids & existing_surface_ids,
            "regions": region_ids & existing_region_ids,
        }

    def _apply_delete_targets(self, targets: dict[str, set[str]]) -> None:
        plane_ids = targets["section_planes"]
        result_ids = targets["section_results"]
        curve_ids = targets["curves"]
        surface_ids = targets["surfaces"]
        region_ids = targets["regions"]

        active_region = self.app_state.region_collection.active_region
        if active_region is not None and active_region.id in region_ids:
            self.app_state.region_collection.clear()
            self._region_select_current_seed_triangle_index = None
            self._region_select_last_hit_triangle_index = None

        self.app_state.surface_collection.surfaces = [
            surface
            for surface in self.app_state.surface_collection.surfaces
            if surface.id not in surface_ids
        ]
        self.app_state.surface_collection.selected_surface_ids.difference_update(surface_ids)
        if self.app_state.surface_collection.active_surface_id in surface_ids:
            self.app_state.surface_collection.active_surface_id = None

        self.app_state.curve_collection.curves = [
            curve
            for curve in self.app_state.curve_collection.curves
            if curve.id not in curve_ids
        ]
        self.app_state.curve_collection.selected_curve_ids.difference_update(curve_ids)
        if self.app_state.curve_collection.active_curve_id in curve_ids:
            self.app_state.curve_collection.active_curve_id = None

        self.app_state.section_collection.results = [
            result
            for result in self.app_state.section_collection.results
            if result.id not in result_ids and result.plane_id not in plane_ids
        ]
        self.app_state.section_collection.selected_result_ids.difference_update(result_ids)
        if self.app_state.section_collection.active_result_id in result_ids:
            self.app_state.section_collection.active_result_id = None

        self.app_state.section_collection.planes = [
            plane
            for plane in self.app_state.section_collection.planes
            if plane.id not in plane_ids
        ]
        self.app_state.section_collection.selected_plane_ids.difference_update(plane_ids)
        if self.app_state.section_collection.active_plane_id in plane_ids:
            self.app_state.section_collection.active_plane_id = None
        self._ensure_default_section_plane()

    def _select_delete_fallback(self, targets: dict[str, set[str]]) -> None:
        if targets["surfaces"] and self.app_state.surface_collection.surfaces:
            self.select_surface(self.app_state.surface_collection.surfaces[0].id)
            return
        if targets["curves"] and self.app_state.curve_collection.curves:
            curve_id = self.app_state.curve_collection.curves[0].id
            self.select_curves([curve_id], active_curve_id=curve_id)
            return
        if targets["section_results"] and self.app_state.section_collection.results:
            self.select_section_result(self.app_state.section_collection.results[-1].id)
            return
        if targets["section_planes"] and self.app_state.section_collection.planes:
            plane_id = self.app_state.section_collection.planes[0].id
            self.select_section_plane(plane_id)
            return
        self._set_selected_item(None)

    def _set_selection_buttons_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for button in self.selection_buttons:
            button.configure(state=state)

    def _settings_from_ui(self) -> AppSettings:
        if self.settings.ui.remember_window_size:
            width, height = self._current_window_size()
        else:
            width = int(self.settings.ui.window_width)
            height = int(self.settings.ui.window_height)
        return AppSettings(
            version=SETTINGS_VERSION,
            display=AppDisplaySettings(
                show_grid=self.settings.display.show_grid,
                show_axes=self.settings.display.show_axes,
                show_normals=False,
                show_axis_gizmo=self.settings.display.show_axis_gizmo,
                show_viewcube=self.settings.display.show_viewcube,
                region_selection_color=self.settings.display.region_selection_color,
                region_selection_edge_color=self.settings.display.region_selection_edge_color,
                region_selection_opacity=self.settings.display.region_selection_opacity,
            ),
            import_settings=AppImportSettings(
                default_proxy_quality=normalize_proxy_quality(
                    self.settings.import_settings.default_proxy_quality
                ),
            ),
            ui=AppUiSettings(
                window_width=width,
                window_height=height,
                window_mode=self.settings.ui.window_mode,
                remember_window_size=self.settings.ui.remember_window_size,
            ),
            keybinds=copy.deepcopy(self.settings.keybinds),
            future=dict(self.settings.future),
        )

    def _current_window_size(self) -> tuple[int, int]:
        try:
            if str(self.root.state()) == "zoomed":
                return (
                    int(self.settings.ui.window_width),
                    int(self.settings.ui.window_height),
                )
        except TclError:
            pass

        width = int(self.root.winfo_width())
        height = int(self.root.winfo_height())
        if width > 1 and height > 1:
            return (width, height)

        geometry = self.root.geometry().split("+", maxsplit=1)[0]
        try:
            width_text, height_text = geometry.split("x", maxsplit=1)
            width = int(width_text)
            height = int(height_text)
        except ValueError:
            width = self.settings.ui.window_width
            height = self.settings.ui.window_height

        return (max(width, 1), max(height, 1))

    def _save_app_settings(self) -> None:
        self.settings = self._settings_from_ui()
        try:
            save_settings(self.settings, self.settings_path)
        except (OSError, ValueError, RuntimeError):
            self.status_text.set("Settings save failed")

    def _on_exit(self) -> None:
        if not self._confirm_unsaved_project_changes("closing openRetop"):
            return

        self._save_app_settings()
        if self._start_viewport_after_id is not None:
            self.root.after_cancel(self._start_viewport_after_id)
            self._start_viewport_after_id = None
        self.sidebar_canvas.unbind_all("<MouseWheel>")
        self.root.unbind_all("<KeyPress>")
        self.viewport.close()
        self.root.destroy()


def run_app() -> int:
    OpenRetopWindow().run()
    return 0


def _format_vector(values: object) -> str:
    return ", ".join(f"{float(value):.6g}" for value in values)


def _format_count(value: int) -> str:
    return f"{int(value):,}"


def _plural_label(count: int, singular: str) -> str:
    return singular if int(count) == 1 else f"{singular}s"


def _polyline_perimeter(points: object, *, closed: bool) -> float:
    try:
        point_array = np.asarray(points, dtype=float).reshape((-1, 3))
    except (TypeError, ValueError):
        return 0.0
    if len(point_array) < 2:
        return 0.0

    length = float(np.linalg.norm(np.diff(point_array, axis=0), axis=1).sum())
    if closed and len(point_array) >= 3:
        length += float(np.linalg.norm(point_array[0] - point_array[-1]))
    return length


def _format_percent(value: float) -> str:
    return f"{float(value):.1f}%"


def _set_menu_entry_state_by_label(menu: object, label: str, state: str) -> None:
    if menu is None:
        return
    try:
        end_index = menu.index("end")
    except TclError:
        return
    if end_index is None:
        return
    for index in range(int(end_index) + 1):
        try:
            if menu.entrycget(index, "label") == label:
                menu.entryconfigure(index, state=state)
                return
        except TclError:
            continue
