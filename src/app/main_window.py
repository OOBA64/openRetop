"""Integrated Tk main window for openRetop."""

from __future__ import annotations

import copy
from pathlib import Path
from tkinter import BooleanVar, Canvas, DoubleVar, Menu, StringVar, Tk, Toplevel, filedialog
from tkinter import messagebox, ttk
from uuid import uuid4

import numpy as np

from app.app_state import AppState
from app.object_state import MeshObjectState
from app.scene_browser import (
    NODE_CURVES,
    NODE_CURVE_GROUP_UNASSIGNED,
    NODE_MESH,
    NODE_SECTION_PLANES,
    NODE_SECTION_RESULTS,
    NODE_SURFACES,
    SceneBrowser,
    curve_group_id_from_node,
    curve_group_node_id,
    curve_id_from_node,
    curve_node_id,
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
    section_offset_delta,
    transform_bounds,
    transform_point,
    world_axis_vector,
)
from curves.curve_state import (
    CurveCollection,
    StoredCurve,
    add_curve,
    clear_curve_selection,
    clear_curves_for_plane,
    clear_curves_for_section_result,
    get_selected_curves,
    get_visible_curves,
    remove_curve,
    set_active_curve,
    set_selected_curves,
)
from geometry.curves import fit_section_polylines
from geometry.sections import (
    AXIS_TO_INDEX,
    SECTION_AXES,
    SectionPolyline,
    SectionResult,
    extract_section,
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
from settings.settings_data import (
    SETTINGS_VERSION,
    AppDisplaySettings,
    AppImportSettings,
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
    clear_results_for_plane,
    create_default_section_plane,
    get_active_plane,
    get_active_result,
    remove_plane,
    set_active_plane,
    set_active_result,
)
from surfaces.surface_state import (
    SurfaceCollection,
    SurfacePatch,
    add_surface,
    clear_surfaces_for_curve,
    get_active_surface,
    remove_surface,
    set_active_surface,
)
from surfaces.surface_preview import SurfacePreviewMesh, build_surface_preview_mesh
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
OPEN_MODEL_MENU_INDEX = 1
LOAD_PROGRESS_STAGES = (
    "Loading mesh",
    "Computing bounds",
    "Building display proxy",
    "Creating viewport actors",
    "Finalizing scene",
)
GENERATED_GEOMETRY_TRANSFORM_WARNING = (
    "Generated sections/curves/surfaces will not follow mesh transform. "
    "Recompute after moving."
)


class LoadProgressDialog:
    """Small stage-based progress window for synchronous mesh loading."""

    def __init__(self, parent: Tk, file_name: str) -> None:
        self.window = Toplevel(parent)
        self.window.title("Opening Model")
        self.window.resizable(False, False)
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", lambda: None)
        self.window.columnconfigure(0, weight=1)

        self.stage_text = StringVar(master=self.window, value="Preparing")
        frame = ttk.Frame(self.window, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=f"Opening {file_name}").grid(row=0, column=0, sticky="w")
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

        self.render_now()
        self.window.lift()

    def update_stage(self, stage: str) -> None:
        self.stage_text.set(stage)
        self.progress_bar.step(8.0)
        self.render_now()
        self.window.lift()

    def render_now(self) -> None:
        self.window.update_idletasks()
        self.window.update()

    def close(self) -> None:
        self.progress_bar.stop()
        self.window.destroy()


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

        self.mesh_state = MeshState()
        self.app_state = AppState()
        self._last_viewport_mouse = (0, 0)
        self._last_transform_readout: str | None = None
        self._active_transform_angle_delta: float | None = None
        self._is_loading_model = False
        self._start_viewport_after_id: str | None = None
        self.current_project_path: Path | None = None
        self.project_dirty = False
        self.preferences_dialog: Toplevel | None = None
        self.preferences_vars: dict[str, BooleanVar | StringVar] = {}
        self._update_window_title()

        self.show_grid = BooleanVar(value=self.settings.display.show_grid)
        self.show_axes = BooleanVar(value=self.settings.display.show_axes)
        self.show_normals = BooleanVar(value=self.settings.display.show_normals)
        self.show_section_plane = BooleanVar(value=False)
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

        self.status_text = StringVar(value="No selection")
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
        self.curve_mean_error_text = StringVar(value="0.000")
        self.curve_max_error_text = StringVar(value="0.000")
        self.curve_closed_text = StringVar(value="Open")
        self.surface_visible = BooleanVar(value=True)
        self.surface_name_text = StringVar(value="(none)")
        self.surface_type_text = StringVar(value="(none)")
        self.surface_source_curve_count_text = StringVar(value="0")
        self.surface_metadata_text = StringVar(value="(none)")
        self.selection_buttons: list[ttk.Button] = []
        self._sync_active_section_plane_from_controls()

        self._build_menu_bar()
        self._build_layout()
        self._set_selection_buttons_enabled(False)
        self._show_context(None)
        self._refresh_scene_browser()
        self._bind_keyboard_shortcuts()

        self.viewport = EmbeddedVTKViewport(self.viewport_frame)
        self.viewport.set_selection_callback(self._on_viewport_selection)
        self.viewport.set_pointer_callback(self._on_viewport_pointer_event)
        self._start_viewport_after_id = self.root.after(100, self._start_viewport)
        self.root.protocol("WM_DELETE_WINDOW", self._on_exit)

    def run(self) -> None:
        self.root.mainloop()

    def _start_viewport(self) -> None:
        self._start_viewport_after_id = None
        try:
            self.viewport.start()
            self._refresh_viewport(reset_camera=True)
        except RuntimeError as exc:
            self.status_text.set("Viewport failed to start")
            messagebox.showerror("Viewport failed to start", str(exc))

    def _build_menu_bar(self) -> None:
        self.menu_bar = Menu(self.root, tearoff=False)

        self.file_menu = Menu(self.menu_bar, tearoff=False)
        self.file_menu.add_command(label="New Project", command=self.new_project)
        self.file_menu.add_command(label="Open Model", command=self.open_model)
        self.file_menu.add_command(label="Open Project", command=self.open_project)
        self.file_menu.add_command(label="Save Project", command=self.save_project)
        self.file_menu.add_command(label="Save Project As", command=self.save_project_as)
        self.file_menu.add_command(label="Exit", command=self._on_exit)
        self.menu_bar.add_cascade(label="File", menu=self.file_menu)

        self.edit_menu = Menu(self.menu_bar, tearoff=False)
        self.edit_menu.add_command(label="Undo", command=self._undo_placeholder)
        self.edit_menu.add_command(label="Redo", command=self._redo_placeholder)
        self.edit_menu.add_command(label="Preferences", command=self.open_preferences)
        self.menu_bar.add_cascade(label="Edit", menu=self.edit_menu)

        self.view_menu = Menu(self.menu_bar, tearoff=False)
        self.view_menu.add_command(label="Frame All", command=self.frame_all)
        self.view_menu.add_command(label="Frame Selected", command=self.frame_selected)
        self.view_menu.add_command(label="Reset View", command=self.reset_view)
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
        self.menu_bar.add_cascade(label="View", menu=self.view_menu)

        self.tools_menu = Menu(self.menu_bar, tearoff=False)
        self.tools_menu.add_command(label="Select Model", command=self.select_model)
        self.tools_menu.add_command(label="Select Section Plane", command=self.select_section_plane)
        self.tools_menu.add_command(label="Add Section Plane", command=self.add_section_plane)
        self.tools_menu.add_command(label="Compute Section", command=self.compute_section)
        self.tools_menu.add_command(
            label="Clear Active Section Result",
            command=self.clear_active_section_result,
        )
        self.tools_menu.add_command(
            label="Clear All Section Results",
            command=self.clear_all_section_results,
        )
        self.tools_menu.add_command(
            label="Delete Active Section Plane",
            command=self.delete_active_section_plane,
        )
        self.tools_menu.add_command(
            label="Delete Selected Curve",
            command=self.delete_selected_curve,
        )
        self.tools_menu.add_command(
            label="Hide Selected Curves",
            command=self.hide_selected_curves,
        )
        self.tools_menu.add_command(
            label="Hide Unselected Curves",
            command=self.hide_unselected_curves,
        )
        self.tools_menu.add_command(
            label="Show All Curves",
            command=self.show_all_curves,
        )
        self.tools_menu.add_command(
            label="Create Surface From Curves",
            command=self.create_surface_from_curves,
        )
        self.tools_menu.add_command(
            label="Rename Selected",
            command=self.rename_selected,
        )
        self.tools_menu.add_command(
            label="Hide Selected",
            command=self.hide_selected_scene_objects,
        )
        self.tools_menu.add_command(
            label="Hide Unselected",
            command=self.hide_unselected_scene_objects,
        )
        self.tools_menu.add_command(
            label="Show All",
            command=self.show_all_scene_objects,
        )
        self.menu_bar.add_cascade(label="Tools", menu=self.tools_menu)

        self.help_menu = Menu(self.menu_bar, tearoff=False)
        self.help_menu.add_command(label="About", command=self._about_placeholder)
        self.menu_bar.add_cascade(label="Help", menu=self.help_menu)
        self.root.configure(menu=self.menu_bar)

    def _not_implemented(self, feature_name: str) -> None:
        self.status_text.set(f"{feature_name}: Not implemented yet")

    def new_project(self) -> None:
        if not self._confirm_unsaved_project_changes("starting a new project"):
            return

        self.current_project_path = None
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
        self._set_project_dirty(False)
        self.status_text.set(f"Project loaded: {project.name} ({project_path})")

    def _project_display_name(self) -> str:
        if self.current_project_path is None:
            return "Untitled Project"
        return self.current_project_path.name

    def _update_window_title(self) -> None:
        marker = " *" if self.project_dirty else ""
        self.root.title(f"openRetop - {self._project_display_name()}{marker}")

    def _set_project_dirty(self, dirty: bool = True) -> None:
        self.project_dirty = bool(dirty)
        self._update_window_title()

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
        self.show_normals.set(project.display.show_normals)
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
            )
            for project_curve in project.curves
        ]
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
                show_normals=self.show_normals.get(),
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

    def _undo_placeholder(self) -> None:
        self._not_implemented("Undo")

    def _redo_placeholder(self) -> None:
        self._not_implemented("Redo")

    def open_preferences(self) -> None:
        if self.preferences_dialog is not None and self.preferences_dialog.winfo_exists():
            self.preferences_dialog.lift()
            self.preferences_dialog.focus_set()
            return

        dialog = Toplevel(self.root)
        dialog.title("Preferences")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.protocol("WM_DELETE_WINDOW", self._close_preferences_dialog)
        dialog.columnconfigure(0, weight=1)
        self.preferences_dialog = dialog
        self.preferences_vars = {
            "show_grid": BooleanVar(
                master=dialog,
                value=self.settings.display.show_grid,
            ),
            "show_axes": BooleanVar(
                master=dialog,
                value=self.settings.display.show_axes,
            ),
            "show_normals": BooleanVar(
                master=dialog,
                value=self.settings.display.show_normals,
            ),
            "default_proxy_quality": StringVar(
                master=dialog,
                value=normalize_proxy_quality(
                    self.settings.import_settings.default_proxy_quality
                ),
            ),
        }

        content = ttk.Frame(dialog, padding=12)
        content.grid(row=0, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)

        display_frame = ttk.LabelFrame(content, text="Display", padding=8)
        display_frame.grid(row=0, column=0, sticky="ew")
        display_frame.columnconfigure(0, weight=1)
        ttk.Checkbutton(
            display_frame,
            text="Startup Show Grid",
            variable=self.preferences_vars["show_grid"],
        ).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(
            display_frame,
            text="Startup Show Axes",
            variable=self.preferences_vars["show_axes"],
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Checkbutton(
            display_frame,
            text="Startup Show Normals",
            variable=self.preferences_vars["show_normals"],
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))

        import_frame = ttk.LabelFrame(content, text="Import", padding=8)
        import_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        import_frame.columnconfigure(1, weight=1)
        ttk.Label(import_frame, text="Default Proxy Quality").grid(
            row=0,
            column=0,
            sticky="w",
        )
        ttk.Combobox(
            import_frame,
            textvariable=self.preferences_vars["default_proxy_quality"],
            values=PROXY_QUALITY_LABELS,
            width=10,
            state="readonly",
        ).grid(row=0, column=1, sticky="ew", padx=(8, 0))

        buttons = ttk.Frame(content)
        buttons.grid(row=2, column=0, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="OK", command=self._confirm_preferences_dialog).grid(
            row=0,
            column=0,
        )
        ttk.Button(buttons, text="Cancel", command=self._close_preferences_dialog).grid(
            row=0,
            column=1,
            padx=(6, 0),
        )
        ttk.Button(buttons, text="Apply", command=self._apply_preferences_dialog).grid(
            row=0,
            column=2,
            padx=(6, 0),
        )

    def _confirm_preferences_dialog(self) -> None:
        self._apply_preferences_dialog()
        self._close_preferences_dialog()

    def _apply_preferences_dialog(self) -> None:
        if not self.preferences_vars:
            return

        show_grid = bool(self.preferences_vars["show_grid"].get())
        show_axes = bool(self.preferences_vars["show_axes"].get())
        show_normals = bool(self.preferences_vars["show_normals"].get())
        proxy_quality = normalize_proxy_quality(
            str(self.preferences_vars["default_proxy_quality"].get())
        )

        width, height = self._current_window_size()
        self.settings = AppSettings(
            version=SETTINGS_VERSION,
            display=AppDisplaySettings(
                show_grid=show_grid,
                show_axes=show_axes,
                show_normals=show_normals,
            ),
            import_settings=AppImportSettings(
                default_proxy_quality=proxy_quality,
            ),
            ui=AppUiSettings(
                window_width=width,
                window_height=height,
            ),
            future=dict(self.settings.future),
        )
        self._save_app_settings()
        self.status_text.set("Preferences applied")

    def _close_preferences_dialog(self) -> None:
        dialog = self.preferences_dialog
        self.preferences_dialog = None
        self.preferences_vars = {}
        if dialog is not None and dialog.winfo_exists():
            dialog.destroy()

    def _about_placeholder(self) -> None:
        self._not_implemented("About")

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

        self.section_result_context_frame = ttk.Frame(self.sidebar)
        self.section_result_context_frame.grid(row=row, column=0, sticky="ew")
        self.section_result_context_frame.columnconfigure(0, weight=1)
        self._build_section_result_context(self.section_result_context_frame)

        self.curve_context_frame = ttk.Frame(self.sidebar)
        self.curve_context_frame.grid(row=row, column=0, sticky="ew")
        self.curve_context_frame.columnconfigure(0, weight=1)
        self._build_curve_context(self.curve_context_frame)

        self.surface_context_frame = ttk.Frame(self.sidebar)
        self.surface_context_frame.grid(row=row, column=0, sticky="ew")
        self.surface_context_frame.columnconfigure(0, weight=1)
        self._build_surface_context(self.surface_context_frame)

        self.viewport_frame = ttk.Frame(main)
        self.viewport_frame.grid(row=0, column=1, sticky="nsew")

        self.scene_browser = SceneBrowser(
            main,
            selection_callback=self._on_scene_browser_selection,
            visibility_callback=self._on_scene_browser_visibility,
        )
        self.scene_browser.frame.grid(row=0, column=2, sticky="ns")

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
        row = self._add_info_row(parent, row, "Reduction", self.display_reduction_text)
        row = self._add_info_row(parent, row, "Display proxy", self.display_proxy_text)
        row = self._add_info_row(parent, row, "Source", self.source_retained_text)
        self._add_info_row(parent, row, "Bounding box", self.bbox_size_text)

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
        row = self._add_info_row(parent, row, "Mean error", self.curve_mean_error_text)
        row = self._add_info_row(parent, row, "Max error", self.curve_max_error_text)
        row = self._add_info_row(parent, row, "Shape", self.curve_closed_text)
        self.delete_curve_button = ttk.Button(
            parent,
            text="Delete Selected Curve",
            command=self.delete_selected_curve,
        )
        self.delete_curve_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.selection_buttons.append(self.delete_curve_button)
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
        row = self._add_info_row(
            parent,
            row,
            "Source curves",
            self.surface_source_curve_count_text,
        )
        row = self._add_info_row(parent, row, "Metadata", self.surface_metadata_text)
        self.delete_surface_button = ttk.Button(
            parent,
            text="Delete Surface",
            command=self.delete_selected_surface,
        )
        self.delete_surface_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.selection_buttons.append(self.delete_surface_button)
        row += 1
        self.surface_deselect_button = ttk.Button(
            parent,
            text="Deselect",
            command=self.clear_selection,
        )
        self.surface_deselect_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.selection_buttons.append(self.surface_deselect_button)

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
        for frame in (
            self.no_selection_frame,
            self.model_context_frame,
            self.section_context_frame,
            self.section_result_context_frame,
            self.curve_context_frame,
            self.surface_context_frame,
        ):
            frame.grid_remove()

        if selected_item == SELECT_MODEL and self.app_state.mesh_object is not None:
            self.model_context_frame.grid()
        elif selected_item == SELECT_SECTION_PLANE and self.app_state.mesh_object is not None:
            self.section_context_frame.grid()
        elif selected_item == SELECT_SECTION_RESULT and self.app_state.mesh_object is not None:
            self.section_result_context_frame.grid()
        elif selected_item == SELECT_CURVE and self.app_state.mesh_object is not None:
            self.curve_context_frame.grid()
        elif selected_item == SELECT_SURFACE and self.app_state.mesh_object is not None:
            self.surface_context_frame.grid()
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
        state = int(getattr(event, "state", 0) or 0)
        if key in {"h", "H"}:
            if state & 0x0008:
                self._handle_shortcut("Alt+H")
            elif state & 0x0001:
                self._handle_shortcut("Shift+H")
            else:
                self._handle_shortcut("H")
            return

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
            "F2": "F2",
        }
        if key in key_map:
            self._handle_shortcut(key_map[key])

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
            self.app_state.section_result = None
            self.app_state.section_collection.results = []
            self.app_state.section_collection.active_result_id = None
            self.app_state.curve_results = []
            self.app_state.curve_collection.curves = []
            self.app_state.curve_collection.active_curve_id = None
            self.app_state.curve_collection.selected_curve_ids.clear()
            self.app_state.surface_collection.surfaces = []
            self.app_state.surface_collection.active_surface_id = None
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
        self.open_model_button.configure(state=state)
        self.file_menu.entryconfigure(OPEN_MODEL_MENU_INDEX, state=state)

    def _set_load_progress_stage(
        self,
        progress: LoadProgressDialog,
        stage: str,
    ) -> None:
        self.status_text.set(stage)
        progress.update_stage(stage)

    def select_model(self) -> None:
        if self.app_state.mesh_object is None:
            self._set_selected_item(None, status="No selection")
            return

        clear_curve_selection(self.app_state.curve_collection)
        self._set_selected_item(SELECT_MODEL, status=f"Selected: {self.app_state.mesh_object.name}")

    def select_section_plane(self, plane_id: str | None = None) -> None:
        if self.app_state.mesh_object is None:
            self._set_selected_item(None, status="No selection")
            return

        clear_curve_selection(self.app_state.curve_collection)
        if plane_id is not None:
            try:
                set_active_plane(self.app_state.section_collection, plane_id)
            except ValueError:
                self._refresh_scene_browser()
                self.status_text.set("Section plane not found")
                return
            self._sync_section_controls_from_active_plane()

        self._set_selected_item(SELECT_SECTION_PLANE, status="Selected: Section Plane")

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

        clear_curve_selection(self.app_state.curve_collection)
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
        clear_curve_selection(self.app_state.curve_collection)
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

        if selected_item != SELECT_CURVE and not preserve_curve_selection:
            clear_curve_selection(self.app_state.curve_collection)
        self.app_state.selected_item = selected_item
        self.app_state.active_transform_mode = None
        self.app_state.active_transform_axis = None
        self.app_state.transform_state = None
        self._active_transform_angle_delta = None
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

    def _on_scene_browser_selection(
        self,
        selected_item: str | None,
        selected_items: tuple[str, ...] = (),
    ) -> None:
        section_plane_id = section_plane_id_from_node(selected_item)
        section_result_id = section_result_id_from_node(selected_item)
        curve_group_id = curve_group_id_from_node(selected_item)
        curve_id = curve_id_from_node(selected_item)
        surface_id = surface_id_from_node(selected_item)
        if selected_item == SELECT_MODEL:
            self.select_model()
        elif selected_item == NODE_CURVES:
            curve_ids = [curve.id for curve in self.app_state.curve_collection.curves]
            if curve_ids:
                self.select_curves(curve_ids, active_curve_id=curve_ids[0])
            else:
                self.status_text.set("No curves available")
        elif selected_item == NODE_SURFACES:
            self.status_text.set("Select an individual surface.")
        elif selected_item == NODE_SECTION_PLANES:
            self.status_text.set("Select an individual section plane.")
        elif selected_item == NODE_SECTION_RESULTS:
            self.status_text.set("Select a section result.")
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
            curve_ids = [
                selected_curve_id
                for selected_curve_id in (
                    curve_id_from_node(item) for item in selected_items
                )
                if selected_curve_id is not None
            ]
            if not curve_ids:
                curve_ids = [curve_id]
            self.select_curves(curve_ids, active_curve_id=curve_id)
        elif surface_id is not None:
            self.select_surface(surface_id)
        elif selected_item == SELECT_SECTION_PLANE:
            self.select_section_plane()
        elif selected_item == SELECT_SECTION_RESULT:
            self.select_section_result()
        elif selected_item == SELECT_CURVE:
            self.select_curve()
        elif selected_item == SELECT_SURFACE:
            self.select_surface()
        else:
            self.clear_selection()

    def _curve_ids_for_group(self, section_result_id: str) -> list[str]:
        result_ids = {
            result.id for result in self.app_state.section_collection.results
        }
        if section_result_id == "":
            return [
                curve.id
                for curve in self.app_state.curve_collection.curves
                if curve.section_result_id not in result_ids
            ]

        return [
            curve.id
            for curve in self.app_state.curve_collection.curves
            if curve.section_result_id == section_result_id
        ]

    def _on_viewport_pointer_event(
        self,
        event_type: str,
        x_position: int,
        y_position: int,
        shift_pressed: bool = False,
        _ctrl_pressed: bool = False,
    ) -> bool:
        self._last_viewport_mouse = (int(x_position), int(y_position))
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

    def compute_section(self) -> None:
        if self.app_state.mesh_object is None:
            self.status_text.set("No selection")
            return

        offset = self._parse_offset()
        if offset is None:
            return
        self._set_section_offset(offset, clamp=True, refresh=False, clear_section=False)

        active_plane = get_active_plane(self.app_state.section_collection)
        if active_plane is None:
            self.status_text.set("No section plane")
            return

        section_mesh = self._transformed_source_mesh()
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
        )
        add_result(self.app_state.section_collection, stored_result)
        self._store_curves_for_section_result(stored_result)
        self._set_display_section_result(stored_result)
        self._update_section_plane_label(set_status=False)
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(self._section_result_status(stored_result))

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
            self.curve_mean_error_text.set("0.000")
            self.curve_max_error_text.set("0.000")
            self.curve_closed_text.set("Open")
            return

        self.curve_visible.set(bool(active_curve.visible))
        self.curve_name_text.set(active_curve.name)
        self.curve_section_text.set(self._section_result_name_for_curve(active_curve))
        self.curve_plane_text.set(self._section_plane_summary_for_curve(active_curve))
        self.curve_point_count_text.set(str(len(active_curve.fitted_points)))
        self.curve_mean_error_text.set(f"{active_curve.mean_error:.3f}")
        self.curve_max_error_text.set(f"{active_curve.max_error:.3f}")
        self.curve_closed_text.set("Closed" if active_curve.is_closed else "Open")

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

        active_curve.name = candidate
        self._refresh_scene_browser()
        self.status_text.set(f"Selected: {active_curve.name}")
        self._set_project_dirty(True)

    def _on_curve_visibility_changed(self) -> None:
        active_curve = self._active_curve()
        if active_curve is None:
            self.status_text.set("No selection")
            return

        active_curve.visible = bool(self.curve_visible.get())
        self._sync_visible_curve_results()
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(f"Selected: {active_curve.name}")
        self._set_project_dirty(True)

    def create_surface_from_curves(self) -> None:
        if not self.app_state.curve_collection.curves:
            self.status_text.set("No curves available")
            return

        source_curves = self._surface_source_curves_from_selection()
        if not source_curves:
            self.status_text.set("Select one closed curve for fill or two curves for loft.")
            return
        if len(source_curves) > 2:
            self.status_text.set("Select one closed curve for fill or exactly two curves for loft.")
            return

        if len(source_curves) == 1:
            if not self._curve_is_closed(source_curves[0]):
                self.status_text.set("Single-curve surface requires a closed curve.")
                return
            surface_type = "preview_fill"
            metadata: dict[str, object] = {
                "curve_count": 1,
                "source": "selected_curve",
                "preview_mode": "closed_curve_fill",
            }
        else:
            surface_type = "preview_loft"
            metadata = {
                "curve_count": 2,
                "source": "selected_curves",
                "preview_mode": "two_curve_loft",
            }
            if any(
                not self._curve_has_min_fitted_points(curve, 2)
                for curve in source_curves
            ):
                metadata["preview_reason"] = "Each selected curve needs at least 2 fitted points."

        surface = SurfacePatch(
            id=f"surface-{uuid4().hex}",
            name=self._next_surface_name(),
            source_curve_ids=[curve.id for curve in source_curves],
            surface_type=surface_type,
            metadata=metadata,
        )
        preview = build_surface_preview_mesh(
            surface,
            self.app_state.curve_collection.curves,
        )
        surface.metadata["preview_available"] = preview is not None
        if preview is None:
            surface.metadata.setdefault(
                "preview_reason",
                self._surface_preview_unavailable_reason(source_curves),
            )
        add_surface(self.app_state.surface_collection, surface)
        self._sync_surface_context_from_active_surface()
        curve_label = "curve" if len(source_curves) == 1 else "curves"
        status = (
            f"Created {surface.name} preview from {len(source_curves)} {curve_label}"
            if surface.metadata["preview_available"]
            else "Surface created, but preview unavailable for selected curves"
        )
        self._set_selected_item(SELECT_SURFACE, status=status)
        self._set_project_dirty(True)

    def _surface_source_curves_from_selection(self) -> list[StoredCurve]:
        selected_curves = get_selected_curves(self.app_state.curve_collection)
        if selected_curves:
            return selected_curves

        active_curve = self._active_curve()
        return [] if active_curve is None else [active_curve]

    @staticmethod
    def _curve_is_closed(curve: StoredCurve) -> bool:
        if bool(curve.is_closed):
            return True

        points = np.asarray(curve.fitted_points, dtype=float)
        if points.ndim != 2 or points.shape[1] != 3 or len(points) < 3:
            return False

        return bool(np.linalg.norm(points[0] - points[-1]) <= 1e-8)

    @staticmethod
    def _curve_has_min_fitted_points(curve: StoredCurve, minimum_count: int) -> bool:
        try:
            points = np.asarray(curve.fitted_points, dtype=float)
        except (TypeError, ValueError):
            return False
        return bool(
            points.ndim == 2
            and points.shape[1] == 3
            and len(points) >= minimum_count
        )

    def _surface_preview_unavailable_reason(self, curves: list[StoredCurve]) -> str:
        if len(curves) == 1:
            return "Closed curve needs at least 3 fitted points."
        if len(curves) == 2 and any(
            not self._curve_has_min_fitted_points(curve, 2)
            for curve in curves
        ):
            return "Each selected curve needs at least 2 fitted points."
        return "Preview unavailable for selected curves."

    def _next_surface_name(self) -> str:
        existing_names = {
            surface.name for surface in self.app_state.surface_collection.surfaces
        }
        index = 1
        while f"Surface {index}" in existing_names:
            index += 1
        return f"Surface {index}"

    def delete_selected_curve(self) -> None:
        active_curve = self._active_curve()
        if active_curve is None:
            self.status_text.set("No selection")
            return

        removed_name = active_curve.name or "Curve"
        self._clear_surfaces_for_curve_ids([active_curve.id])
        remove_curve(self.app_state.curve_collection, active_curve.id)
        self._sync_visible_curve_results()
        if self._active_curve() is not None:
            self._sync_curve_context_from_active_curve()
            self._set_selected_item(SELECT_CURVE, status=f"Deleted: {removed_name}")
        else:
            self._sync_curve_context_from_active_curve()
            self._set_selected_item(None, status=f"Deleted: {removed_name}")
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
                previews.append(preview)
        return previews

    def _clear_surfaces_for_curve_ids(self, curve_ids: list[str]) -> None:
        for curve_id in curve_ids:
            clear_surfaces_for_curve(self.app_state.surface_collection, curve_id)

    def hide_selected_curves(self) -> None:
        selected_ids = set(self.app_state.curve_collection.selected_curve_ids)
        if not selected_ids:
            self.status_text.set("No selected curves")
            return

        for curve in self.app_state.curve_collection.curves:
            if curve.id in selected_ids:
                curve.visible = False
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

        hidden_count = 0
        for curve in self.app_state.curve_collection.curves:
            if curve.id not in selected_ids and curve.visible:
                hidden_count += 1
                curve.visible = False
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

        for curve in self.app_state.curve_collection.curves:
            curve.visible = True
        self._sync_curve_context_from_active_curve()
        self._sync_visible_curve_results()
        self._refresh_viewport(reset_camera=False)
        self.status_text.set("All curves visible")
        self._set_project_dirty(True)

    def _sync_surface_context_from_active_surface(self) -> None:
        active_surface = self._active_surface()
        if active_surface is None:
            self.surface_visible.set(False)
            self.surface_name_text.set("(none)")
            self.surface_type_text.set("(none)")
            self.surface_source_curve_count_text.set("0")
            self.surface_metadata_text.set("(none)")
            return

        self.surface_visible.set(bool(active_surface.visible))
        self.surface_name_text.set(active_surface.name)
        self.surface_type_text.set(active_surface.surface_type)
        self.surface_source_curve_count_text.set(str(len(active_surface.source_curve_ids)))
        self.surface_metadata_text.set(self._surface_metadata_summary(active_surface.metadata))

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

        active_surface.name = candidate
        self._refresh_scene_browser()
        self.status_text.set(f"Selected: {active_surface.name}")
        self._set_project_dirty(True)

    @staticmethod
    def _surface_metadata_summary(metadata: dict[str, object]) -> str:
        if not metadata:
            return "(none)"

        parts = [
            f"{key}={metadata[key]}"
            for key in sorted(metadata)
        ]
        return ", ".join(parts)

    def _on_surface_visibility_changed(self) -> None:
        active_surface = self._active_surface()
        if active_surface is None:
            self.status_text.set("No selection")
            return

        active_surface.visible = bool(self.surface_visible.get())
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(f"Selected: {active_surface.name}")
        self._set_project_dirty(True)

    def delete_selected_surface(self) -> None:
        active_surface = self._active_surface()
        if active_surface is None:
            self.status_text.set("No selection")
            return

        removed_name = active_surface.name or "Surface"
        remove_surface(self.app_state.surface_collection, active_surface.id)
        if self._active_surface() is not None:
            self._sync_surface_context_from_active_surface()
            self._set_selected_item(SELECT_SURFACE, status=f"Deleted: {removed_name}")
        else:
            self._sync_surface_context_from_active_surface()
            self._set_selected_item(None, status=f"Deleted: {removed_name}")
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
        if self.app_state.selected_item == SELECT_MODEL:
            self.viewport.frame_model()
            self.status_text.set(f"Selected: {self.app_state.mesh_object.name}")
        elif self.app_state.selected_item == SELECT_SECTION_PLANE:
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
        surface_previews = [] if hide_expensive_overlays else self._build_visible_surface_previews()
        self.viewport.set_scene(
            display_mesh,
            transform_matrix=transform_matrix,
            show_grid=self.show_grid.get(),
            show_axes=self.show_axes.get(),
            show_normals=self.show_normals.get()
            and not hide_expensive_overlays
            and not (
                self.app_state.mesh_object is not None and self.app_state.mesh_object.display_proxy_enabled
            ),
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
            surface_previews=surface_previews,
            active_surface_id=self.app_state.surface_collection.active_surface_id,
            reset_camera=reset_camera,
        )
        self._refresh_scene_browser()

    def _refresh_scene_browser(self) -> None:
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
            section_results=self.app_state.section_collection.results,
            active_section_result_id=self.app_state.section_collection.active_result_id,
            curves=self.app_state.curve_collection.curves,
            active_curve_id=self.app_state.curve_collection.active_curve_id,
            selected_curve_ids=self.app_state.curve_collection.selected_curve_ids,
            surfaces=self.app_state.surface_collection.surfaces,
            active_surface_id=self.app_state.surface_collection.active_surface_id,
            has_section_result=bool(self.app_state.section_collection.results)
            or self.app_state.section_result is not None,
            has_curves=bool(self.app_state.curve_collection.curves),
            has_surfaces=bool(self.app_state.surface_collection.surfaces),
            selected_item=self.app_state.selected_item,
        )

    def _should_show_section_plane(self) -> bool:
        if not self.mesh_state.is_loaded:
            return False

        return any(plane.visible for plane in self.app_state.section_collection.planes)

    def _sync_active_section_plane_from_controls(self) -> None:
        active_plane = get_active_plane(self.app_state.section_collection)
        if active_plane is None:
            return

        active_plane.axis = normalize_axis(self.section_axis.get())
        active_plane.offset = float(self.section_offset.get())
        active_plane.visible = bool(self.show_section_plane.get())

    def _sync_section_controls_from_active_plane(self, *, clamp_offset: bool = True) -> None:
        active_plane = get_active_plane(self.app_state.section_collection)
        if active_plane is None:
            return

        desired_offset = float(active_plane.offset)
        self.section_plane_name_text.set(active_plane.name)
        self.section_axis.set(normalize_axis(active_plane.axis))
        self.show_section_plane.set(bool(active_plane.visible))
        self._update_section_offset_range()
        self._set_section_offset(
            desired_offset,
            clamp=clamp_offset,
            refresh=False,
            clear_section=False,
        )
        self._update_section_plane_label(set_status=False)

    def _on_view_option_changed(self) -> None:
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
        self._sync_active_section_plane_from_controls()
        self._refresh_viewport(reset_camera=False)
        self._set_project_dirty(True)

    def _on_mesh_visibility_changed(self) -> None:
        if self.app_state.mesh_object is None:
            self.status_text.set("No selection")
            return

        self.app_state.mesh_object.visible = bool(self.mesh_visible.get())
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

        mesh_object.name = candidate
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

        active_plane.name = candidate
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

        active_result.visible = bool(self.section_result_visible.get())
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

        active_result.name = candidate
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
        expanded_node_ids = self._expanded_visibility_node_ids(node_ids)
        if action == "show_all":
            changed_count = self._set_scene_visibility(
                self._all_visibility_object_node_ids(),
                True,
            )
            status = "All scene items visible"
        elif action == "hide_selected":
            changed_count = self._set_scene_visibility(expanded_node_ids, False)
            status = self._visibility_status("Hidden", changed_count, "selected item")
        elif action == "show_selected":
            changed_count = self._set_scene_visibility(expanded_node_ids, True)
            status = self._visibility_status("Shown", changed_count, "selected item")
        elif action == "hide_unselected":
            unselected_node_ids = self._all_visibility_object_node_ids() - expanded_node_ids
            changed_count = self._set_scene_visibility(unselected_node_ids, False)
            status = self._visibility_status("Hidden", changed_count, "unselected item")
        else:
            self.status_text.set("Unknown visibility command")
            return

        self._sync_after_scene_visibility_change()
        self.status_text.set(status)
        if changed_count:
            self._set_project_dirty(True)

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
            elif node_id == NODE_CURVE_GROUP_UNASSIGNED:
                expanded_node_ids.update(
                    curve_node_id(curve.id)
                    for curve in self.app_state.curve_collection.curves
                    if curve.section_result_id not in section_result_ids
                )
            else:
                for result in self.app_state.section_collection.results:
                    if node_id != curve_group_node_id(result.id):
                        continue
                    expanded_node_ids.update(
                        curve_node_id(curve.id)
                        for curve in self.app_state.curve_collection.curves
                        if curve.section_result_id == result.id
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
        return node_ids

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

    def show_all_scene_objects(self) -> None:
        self._on_scene_browser_visibility("show_all", ())

    def _scene_visibility_target_node_ids(self) -> tuple[str, ...]:
        browser_selection = self.scene_browser.selected_node_ids()
        if browser_selection:
            return browser_selection

        return tuple(self._node_ids_for_active_selection())

    def _node_ids_for_active_selection(self) -> set[str]:
        selected_item = self.app_state.selected_item
        if selected_item == SELECT_MODEL and self.app_state.mesh_object is not None:
            return {NODE_MESH}
        if selected_item == SELECT_SECTION_PLANE:
            active_plane = get_active_plane(self.app_state.section_collection)
            return (
                {section_plane_node_id(active_plane.id)}
                if active_plane is not None
                else set()
            )
        if selected_item == SELECT_SECTION_RESULT:
            active_result = self._active_section_result()
            return (
                {section_result_node_id(active_result.id)}
                if active_result is not None
                else set()
            )
        if selected_item == SELECT_CURVE:
            return {
                curve_node_id(curve_id)
                for curve_id in self.app_state.curve_collection.selected_curve_ids
            }
        if selected_item == SELECT_SURFACE:
            active_surface = self._active_surface()
            return (
                {surface_node_id(active_surface.id)}
                if active_surface is not None
                else set()
            )
        return set()

    def _on_section_axis_changed(self, _event: object | None = None) -> None:
        self._sync_active_section_plane_from_controls()
        self._configure_offset_range(reset=False)
        self._update_section_plane_label(set_status=True)
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
    ) -> None:
        minimum, maximum = self._section_offset_bounds
        next_offset = min(max(float(offset), minimum), maximum) if clamp else float(offset)
        self._updating_offset = True
        try:
            self.section_offset.set(next_offset)
            self.section_offset_text.set(f"{next_offset:.3f}")
        finally:
            self._updating_offset = False

        self._sync_active_section_plane_from_controls()
        self._update_section_plane_label(set_status=True)
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
        self.section_plane_text.set(f"Section: {axis} = {offset:.3f}")
        if set_status and self.app_state.selected_item == SELECT_SECTION_PLANE:
            self.status_text.set(f"Section plane: {axis} = {offset:.3f}")

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

        if self.app_state.selected_item == SELECT_SECTION_PLANE and mode == "rotate":
            self._cycle_section_axis_for_rotation()
            return

        self.app_state.transform_state = ActiveTransformState(
            selected_item=self.app_state.selected_item,
            mode=mode,
            mouse_start=self._last_viewport_mouse,
            axis_constraint=None,
            location=self.app_state.mesh_object.location.copy(),
            rotation=self.app_state.mesh_object.rotation.copy(),
            section_axis=self.section_axis.get(),
            section_offset=self.section_offset.get(),
        )
        self.app_state.active_transform_mode = mode
        self.app_state.active_transform_axis = self._display_transform_axis(self.app_state.transform_state)
        self._last_transform_readout = None
        self._active_transform_angle_delta = 0.0 if mode == "rotate" else None
        self._refresh_viewport(reset_camera=False)
        self.status_text.set(self._active_transform_status())

    def _set_transform_axis_constraint(self, axis: str) -> None:
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
        if self.app_state.transform_state.selected_item == SELECT_SECTION_PLANE and next_axis is not None:
            self.section_axis.set(axis)
            self._configure_offset_range(reset=False)
            self.app_state.transform_state.section_axis = axis
            self.app_state.transform_state.section_offset = self.section_offset.get()
            self.app_state.transform_state.mouse_start = self._last_viewport_mouse
            self._update_section_plane_label(set_status=False)

        self._refresh_viewport(reset_camera=False)
        self.status_text.set(self._active_transform_status())

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
        elif state.selected_item == SELECT_SECTION_PLANE and state.mode == "move":
            self._update_section_plane_move_transform(state, mouse_position, fine=fine)

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
        offset_delta = section_offset_delta(
            state.mouse_start,
            mouse_position,
            self._section_offset_bounds,
            fine=fine,
        )
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
        self._refresh_viewport(reset_camera=False)
        if commit and state.selected_item == SELECT_MODEL:
            status = self._model_transform_status(status)
        self.status_text.set(status)
        if commit:
            self._set_project_dirty(True)

    def _restore_transform_start_state(self, state: ActiveTransformState) -> None:
        if state.selected_item == SELECT_MODEL and self.app_state.mesh_object is not None:
            self.app_state.mesh_object.location = state.location.copy()
            self.app_state.mesh_object.rotation = state.rotation.copy()
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
        self._set_project_dirty(True)

    def _active_transform_status(self) -> str:
        if self.app_state.transform_state is None:
            return "No selection" if self.app_state.selected_item is None else "Transform"

        mode_label = "Move mode" if self.app_state.transform_state.mode == "move" else "Rotate mode"
        axis = self._display_transform_axis(self.app_state.transform_state)
        parts = [mode_label]
        if axis is not None:
            parts.append(f"{axis} axis")
        if self._last_transform_readout is not None:
            parts.append(self._last_transform_readout)
        elif self.app_state.transform_state.mode == "move" and axis is None:
            parts.append(
                "press X/Y/Z to constrain, Enter/Click to confirm, Esc/Right-click to cancel"
            )
        elif self.app_state.transform_state.mode == "rotate":
            parts.append("move mouse horizontally")
        return " - ".join(parts)

    def _display_transform_axis(self, state: ActiveTransformState) -> str | None:
        if state.mode == "rotate":
            return state.axis_constraint or "Z"
        if state.selected_item == SELECT_SECTION_PLANE:
            return state.axis_constraint or self.section_axis.get()
        return state.axis_constraint

    def rename_selected(self) -> None:
        entry = self._rename_entry_for_selection()
        if entry is None:
            self.status_text.set("No renameable selection")
            return

        entry.focus_set()
        entry.selection_range(0, "end")
        self.status_text.set("Rename selected object")

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
        return None

    def _handle_shortcut(self, key: str) -> None:
        if key == "F":
            self.frame_selected()
            return

        if key == "F2":
            self.rename_selected()
            return

        if key == "H":
            self.hide_selected_scene_objects()
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

        if key == "Escape":
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

        if key in {"X", "Y", "Z"}:
            self._set_transform_axis_constraint(key)
            return

        if key == "G":
            self._start_active_transform("move")
            return

        if key == "R":
            self._start_active_transform("rotate")

    def _delete_selected_if_safe(self) -> None:
        if self.app_state.selected_item == SELECT_SURFACE:
            self.delete_selected_surface()
            return

        if self.app_state.selected_item == SELECT_CURVE:
            self.delete_selected_curve()
            return

        if self.app_state.selected_item == SELECT_SECTION_PLANE:
            self.delete_active_section_plane()
            return

        if self.app_state.selected_item != SELECT_MODEL or self.app_state.mesh_object is None:
            self.status_text.set("No selection")
            return

        self.app_state.mesh_object = None
        self.mesh_state = MeshState()
        self.app_state.section_result = None
        self.app_state.curve_results = []
        self.app_state.curve_collection.curves = []
        self.app_state.curve_collection.active_curve_id = None
        self.app_state.curve_collection.selected_curve_ids.clear()
        self.app_state.surface_collection.surfaces = []
        self.app_state.surface_collection.active_surface_id = None
        self.app_state.section_collection.results = []
        self.app_state.section_collection.active_result_id = None
        self.section_result_text.set("Section result: none")
        self._update_stats()
        self._set_selection_buttons_enabled(False)
        self._set_selected_item(None, status="Selected model removed")
        self._set_project_dirty(True)

    def _set_selection_buttons_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for button in self.selection_buttons:
            button.configure(state=state)

    def _settings_from_ui(self) -> AppSettings:
        width, height = self._current_window_size()
        return AppSettings(
            version=SETTINGS_VERSION,
            display=AppDisplaySettings(
                show_grid=self.settings.display.show_grid,
                show_axes=self.settings.display.show_axes,
                show_normals=self.settings.display.show_normals,
            ),
            import_settings=AppImportSettings(
                default_proxy_quality=normalize_proxy_quality(
                    self.settings.import_settings.default_proxy_quality
                ),
            ),
            ui=AppUiSettings(
                window_width=width,
                window_height=height,
            ),
            future=dict(self.settings.future),
        )

    def _current_window_size(self) -> tuple[int, int]:
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


def _format_percent(value: float) -> str:
    return f"{float(value):.1f}%"
