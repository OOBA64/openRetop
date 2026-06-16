"""Embed a VTK viewport inside a Tk frame."""

from __future__ import annotations

from dataclasses import dataclass
import time
from tkinter import Canvas, Event, TclError
from typing import Callable, Sequence

import numpy as np

from curves.curve_state import is_repaired_curve
from curves.manual_curve import (
    DEFAULT_MANUAL_CURVE_SAMPLE_COUNT,
    sample_manual_curve,
)
from geometry.curves import CurveFitResult
from geometry.sections import SectionResult
from mesh.triangle_mesh import TriangleMeshData
from regions.region_state import RegionSelection
from sections.section_state import SectionPlaneState
from sections.section_state import plane_normal, plane_origin
from surfaces.surface_preview import SurfacePreviewMesh
from viewer.overlays import (
    LineGeometry,
    build_active_axis_indicator,
    build_bounding_box_outline,
    build_origin_marker,
    build_rotation_angle_indicator,
    build_rotation_ring,
    build_section_plane_preview,
    build_world_axes,
    build_xy_grid,
    reference_extent,
    rotation_ring_radius_for_axis,
)

try:
    from vtkmodules.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray
    from vtkmodules.vtkCommonCore import VTK_UNSIGNED_CHAR
    from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
    from vtkmodules.vtkCommonMath import vtkMatrix4x4
    from vtkmodules.vtkFiltersCore import vtkPolyDataNormals, vtkTubeFilter
    from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera
    from vtkmodules.vtkRenderingAnnotation import vtkAxesActor
    from vtkmodules.vtkRenderingCore import (
        vtkActor,
        vtkCellPicker,
        vtkPolyDataMapper,
        vtkRenderer,
        vtkRenderWindow,
        vtkRenderWindowInteractor,
    )
    import vtkmodules.vtkRenderingOpenGL2  # noqa: F401
except ImportError as exc:  # pragma: no cover - exercised only when deps are absent.
    raise SystemExit(
        "VTK is required for the openRetop viewport. Install dependencies with: "
        "python -m pip install -r requirements.txt"
    ) from exc


APP_SHORTCUT_KEYSYMS = {
    "backspace",
    "c",
    "delete",
    "escape",
    "f",
    "g",
    "n",
    "r",
    "return",
    "x",
    "y",
    "z",
}
SELECTION_BOUNDING_BOX_LINE_WIDTH = 1.0
SECTION_RESULT_COLOR = (0.58, 0.50, 0.40)
SECTION_RESULT_LINE_WIDTH = 1.25
UNSELECTED_CURVE_COLOR = (0.08, 0.72, 0.38)
UNSELECTED_CURVE_LINE_WIDTH = 2.2
TINY_CURVE_COLOR = (0.58, 0.33, 0.36)
TINY_CURVE_LINE_WIDTH = 2.4
REPAIRED_CURVE_COLOR = (1.0, 0.48, 0.12)
REPAIRED_CURVE_LINE_WIDTH = 3.0
SURFACE_SOURCE_CURVE_COLOR = (0.66, 0.38, 1.0)
SURFACE_SOURCE_CURVE_LINE_WIDTH = 3.6
SELECTED_CURVE_COLOR = (0.0, 0.95, 1.0)
SELECTED_CURVE_LINE_WIDTH = 4.6
ACTIVE_CURVE_COLOR = (1.0, 0.92, 0.12)
ACTIVE_CURVE_LINE_WIDTH = 5.4
MANUAL_CURVE_POINT_COLOR = (1.0, 1.0, 1.0)
MANUAL_CURVE_FIRST_POINT_COLOR = (0.96, 0.98, 1.0)
MANUAL_CURVE_SELECTED_POINT_COLOR = (0.35, 0.95, 1.0)
MANUAL_CURVE_POLYLINE_COLOR = (1.0, 1.0, 1.0)
MANUAL_CURVE_CONTROL_POLYGON_COLOR = (0.65, 0.68, 0.70)
MANUAL_CURVE_PREVIEW_POINT_COLOR = (1.0, 0.48, 0.08)
MANUAL_CURVE_PREVIEW_LINE_COLOR = (1.0, 0.48, 0.08)
MANUAL_CURVE_CLOSING_COLOR = (1.0, 0.48, 0.08)
MANUAL_CURVE_SNAP_POINT_COLOR = MANUAL_CURVE_POINT_COLOR
MANUAL_CURVE_SNAP_POLYLINE_COLOR = MANUAL_CURVE_POLYLINE_COLOR
MANUAL_CURVE_POINT_LINE_WIDTH = 1.15
MANUAL_CURVE_PREVIEW_LINE_WIDTH = 2.6
MANUAL_CURVE_GHOST_LINE_WIDTH = 1.9
MANUAL_CURVE_ACTIVE_LINE_WIDTH = 3.2
MANUAL_CURVE_CONTROL_POINT_RADIUS_RATIO = 0.0045
MANUAL_CURVE_FIRST_POINT_RADIUS_RATIO = 0.0055
MANUAL_CURVE_SELECTED_POINT_RADIUS_RATIO = 0.0065
MANUAL_CURVE_PREVIEW_POINT_RADIUS_RATIO = 0.0055
MANUAL_CURVE_MIN_POINT_RADIUS = 0.003
REGION_SELECTION_COLOR = (0.0, 0.82, 1.0)
REGION_SELECTION_EDGE_COLOR = (0.88, 1.0, 1.0)
REGION_SELECTION_OPACITY = 0.34
REGION_SELECTION_LINE_WIDTH = 2.4

CURVE_DISPLAY_CATEGORY_ORDER = (
    "normal",
    "tiny",
    "repaired",
    "surface_source",
    "active_surface_source",
    "selected",
    "active",
)


@dataclass(frozen=True)
class CurveDisplayStyle:
    color: tuple[float, float, float]
    line_width: float


CURVE_DISPLAY_STYLES = {
    "normal": CurveDisplayStyle(UNSELECTED_CURVE_COLOR, UNSELECTED_CURVE_LINE_WIDTH),
    "tiny": CurveDisplayStyle(TINY_CURVE_COLOR, TINY_CURVE_LINE_WIDTH),
    "repaired": CurveDisplayStyle(REPAIRED_CURVE_COLOR, REPAIRED_CURVE_LINE_WIDTH),
    "surface_source": CurveDisplayStyle(
        SURFACE_SOURCE_CURVE_COLOR,
        SURFACE_SOURCE_CURVE_LINE_WIDTH,
    ),
    "active_surface_source": CurveDisplayStyle(
        SURFACE_SOURCE_CURVE_COLOR,
        SURFACE_SOURCE_CURVE_LINE_WIDTH,
    ),
    "selected": CurveDisplayStyle(SELECTED_CURVE_COLOR, SELECTED_CURVE_LINE_WIDTH),
    "active": CurveDisplayStyle(ACTIVE_CURVE_COLOR, ACTIVE_CURVE_LINE_WIDTH),
}


@dataclass(frozen=True)
class CameraVectors:
    right: np.ndarray
    up: np.ndarray
    forward: np.ndarray
    position: np.ndarray
    focal_point: np.ndarray


@dataclass(frozen=True)
class ViewportSectionPlane:
    id: str
    axis: str
    offset: float
    visible: bool
    selected: bool
    origin: np.ndarray
    normal: np.ndarray


@dataclass(frozen=True)
class MeshPickResult:
    hit: bool
    position: np.ndarray | None = None
    normal: np.ndarray | None = None
    triangle_index: int | None = None


class EmbeddedVTKViewport:
    """VTK viewport hosted inside a Tk frame."""

    def __init__(self, parent: object) -> None:
        self.parent = parent
        self.renderer = vtkRenderer()
        self.renderer.SetBackground(0.055, 0.06, 0.068)
        self.widget: Canvas | None = None
        self.render_window: vtkRenderWindow | None = None
        self.interactor: vtkRenderWindowInteractor | None = None
        self._is_started = False
        self._is_closed = False
        self._view_center = np.asarray([0.0, 0.0, 0.0], dtype=float)
        self._view_extent = 2.0
        self._mesh_min_bound: np.ndarray | None = None
        self._mesh_max_bound: np.ndarray | None = None
        self._mesh_actor: vtkActor | None = None
        self._mesh_actor_mesh_id: int | None = None
        self._actors_by_role: dict[str, vtkActor] = {}
        self._actor_groups: dict[str, list[vtkActor]] = {}
        self._actor_keys: dict[str, object] = {}
        self._group_keys: dict[str, object] = {}
        self._mesh_bounds_mesh_id: int | None = None
        self._mesh_local_min_bound: np.ndarray | None = None
        self._mesh_local_max_bound: np.ndarray | None = None
        self._interactive_transform_key: tuple[int, str, str | None, str | None] | None = None
        self._rotation_overlay_mesh_id: int | None = None
        self._rotation_overlay_min_bound: np.ndarray | None = None
        self._rotation_overlay_max_bound: np.ndarray | None = None
        self._section_plane_actors: list[vtkActor] = []
        self._section_plane_pick_geometry: LineGeometry | None = None
        self._section_plane_pick_geometries: list[LineGeometry] = []
        self._axis_gizmo_renderer: vtkRenderer | None = None
        self._axis_gizmo_actor: vtkAxesActor | None = None
        self._axis_gizmo_visible = False
        self._axis_gizmo_requested_visible: bool | None = None
        self._axis_gizmo_camera_key: tuple[float, ...] | None = None
        self._manual_overlay_renderer: vtkRenderer | None = None
        self._selection_callback: Callable[[str | None], None] | None = None
        self._pointer_callback: Callable[[str, int, int, bool, bool], bool] | None = None
        self._left_press_position: tuple[int, int] | None = None
        self._last_mouse_position = (0, 0)
        self._left_button_pressed = False
        self._middle_button_pressed = False
        self._right_button_pressed = False
        self._active_interaction = False
        self._render_after_id: str | None = None
        self.scene_dirty = False
        self.camera_dirty = False
        self.overlay_dirty = False
        self.gizmo_dirty = False
        self._render_counters_enabled = False
        self.render_count = 0
        self.skipped_render_count = 0
        self.last_render_time: float | None = None

    def start(self) -> None:
        if self._is_started:
            return

        self.widget = Canvas(
            self.parent,
            background="#101316",
            borderwidth=0,
            highlightthickness=0,
        )
        self.widget.pack(fill="both", expand=True)
        self.widget.update_idletasks()

        self.render_window = vtkRenderWindow()
        self.render_window.AddRenderer(self.renderer)
        self._attach_render_window_to_widget()

        self.interactor = vtkRenderWindowInteractor()
        self.interactor.SetRenderWindow(self.render_window)
        self.interactor.SetInteractorStyle(vtkInteractorStyleTrackballCamera())
        self.interactor.Initialize()
        self.interactor.Enable()
        self._bind_widget_events()
        self._is_started = True
        self._render()

    def close(self) -> None:
        self._is_closed = True
        self._cancel_pending_render()
        if self.render_window is not None and self._axis_gizmo_renderer is not None:
            self.render_window.RemoveRenderer(self._axis_gizmo_renderer)
        if self.render_window is not None and self._manual_overlay_renderer is not None:
            self.render_window.RemoveRenderer(self._manual_overlay_renderer)
        self._axis_gizmo_renderer = None
        self._axis_gizmo_actor = None
        self._axis_gizmo_camera_key = None
        self._manual_overlay_renderer = None
        if self.interactor is not None:
            self.interactor.Disable()
            self.interactor.TerminateApp()
            self.interactor = None
        if self.render_window is not None:
            self.render_window.Finalize()
            self.render_window = None
        if self.widget is not None:
            self.widget.destroy()
            self.widget = None

    def set_selection_callback(
        self,
        callback: Callable[[str | None], None] | None,
    ) -> None:
        self._selection_callback = callback

    def set_pointer_callback(
        self,
        callback: Callable[[str, int, int, bool, bool], bool] | None,
    ) -> None:
        self._pointer_callback = callback

    def get_camera_vectors(self) -> CameraVectors:
        camera = self.renderer.GetActiveCamera()
        forward = _normalized_vector(
            np.asarray(camera.GetDirectionOfProjection(), dtype=float),
            fallback=np.asarray([0.0, 0.0, -1.0], dtype=float),
        )
        view_up = _normalized_vector(
            np.asarray(camera.GetViewUp(), dtype=float),
            fallback=np.asarray([0.0, 1.0, 0.0], dtype=float),
        )
        right = _normalized_vector(
            np.cross(forward, view_up),
            fallback=np.asarray([1.0, 0.0, 0.0], dtype=float),
        )
        up = _normalized_vector(
            np.cross(right, forward),
            fallback=view_up,
        )
        return CameraVectors(
            right=right,
            up=up,
            forward=forward,
            position=np.asarray(camera.GetPosition(), dtype=float),
            focal_point=np.asarray(camera.GetFocalPoint(), dtype=float),
        )

    def screen_point_to_plane(
        self,
        x_position: int,
        y_position: int,
        plane_origin: Sequence[float],
        plane_normal: Sequence[float],
    ) -> np.ndarray | None:
        if self.widget is None:
            return None

        origin = np.asarray(plane_origin, dtype=float).reshape(3)
        normal = _normalized_vector(
            np.asarray(plane_normal, dtype=float).reshape(3),
            fallback=np.asarray([0.0, 0.0, 1.0], dtype=float),
        )
        if not (np.all(np.isfinite(origin)) and np.all(np.isfinite(normal))):
            return None

        height = max(int(self.widget.winfo_height()), 1)
        display_x = float(x_position)
        display_y = float(height - int(y_position))
        near = self._display_to_world(display_x, display_y, 0.0)
        far = self._display_to_world(display_x, display_y, 1.0)
        if near is None or far is None:
            return None

        direction = far - near
        denominator = float(np.dot(direction, normal))
        if abs(denominator) <= 1e-9:
            return None

        distance = float(np.dot(origin - near, normal) / denominator)
        if not np.isfinite(distance):
            return None

        point = near + direction * distance
        if not np.all(np.isfinite(point)):
            return None
        return point

    def _display_to_world(
        self,
        display_x: float,
        display_y: float,
        display_z: float,
    ) -> np.ndarray | None:
        self.renderer.SetDisplayPoint(float(display_x), float(display_y), float(display_z))
        self.renderer.DisplayToWorld()
        world_point = np.asarray(self.renderer.GetWorldPoint(), dtype=float)
        if len(world_point) < 4 or abs(float(world_point[3])) <= 1e-12:
            return None

        point = world_point[:3] / float(world_point[3])
        if not np.all(np.isfinite(point)):
            return None
        return point

    def pick_mesh_at_screen_point(
        self,
        x_position: int,
        y_position: int,
    ) -> MeshPickResult:
        if (
            self.widget is None
            or self._mesh_actor is None
            or not bool(self._mesh_actor.GetVisibility())
        ):
            return MeshPickResult(hit=False)

        height = max(int(self.widget.winfo_height()), 1)
        display_x = float(x_position)
        display_y = float(height - int(y_position))
        picker = vtkCellPicker()
        picker.SetTolerance(0.0008)
        picker.PickFromListOn()
        picker.AddPickList(self._mesh_actor)
        if picker.Pick(display_x, display_y, 0.0, self.renderer) <= 0:
            return MeshPickResult(hit=False)
        if picker.GetActor() is not self._mesh_actor:
            return MeshPickResult(hit=False)

        position = np.asarray(picker.GetPickPosition(), dtype=float).reshape(3)
        if not np.all(np.isfinite(position)):
            return MeshPickResult(hit=False)

        cell_id = int(picker.GetCellId())
        triangle_index = cell_id if cell_id >= 0 else None
        normal = _mesh_pick_normal(self._mesh_actor, triangle_index)
        return MeshPickResult(
            hit=True,
            position=position,
            normal=normal,
            triangle_index=triangle_index,
        )

    def set_scene(
        self,
        mesh: TriangleMeshData | None,
        *,
        transform_matrix: Sequence[Sequence[float]] | np.ndarray | None = None,
        show_grid: bool,
        show_axes: bool,
        show_normals: bool,
        show_section_plane: bool,
        section_axis: str,
        section_offset: float,
        section_planes: Sequence[SectionPlaneState] | None = None,
        active_section_plane_id: str | None = None,
        selected_item: str | None = None,
        object_origin: Sequence[float] | None = None,
        scene_bounds_min: Sequence[float] | None = None,
        scene_bounds_max: Sequence[float] | None = None,
        active_transform_mode: str | None = None,
        active_transform_axis: str | None = None,
        active_transform_angle_delta: float | None = None,
        section_result: SectionResult | None = None,
        curve_results: Sequence[CurveFitResult] | None = None,
        active_curve_id: str | None = None,
        surface_source_curve_ids: Sequence[str] | None = None,
        surface_previews: Sequence[SurfacePreviewMesh] | None = None,
        active_surface_id: str | None = None,
        region_selection: RegionSelection | None = None,
        manual_curve_points: Sequence[Sequence[float]] | np.ndarray | None = None,
        manual_curve_closed: bool = False,
        manual_curve_plane_normal: Sequence[float] | None = None,
        manual_curve_snap_to_mesh: bool = False,
        manual_curve_selected_control_point_index: int | None = None,
        manual_curve_method: str = "catmull_rom",
        manual_curve_sample_count: int = DEFAULT_MANUAL_CURVE_SAMPLE_COUNT,
        manual_curve_preview_point: Sequence[float] | None = None,
        manual_curve_preview_valid: bool = False,
        manual_curve_preview_snaps_closed: bool = False,
        manual_curve_preview_snaps_to_mesh: bool = False,
        show_axis_gizmo: bool = True,
        reset_camera: bool = False,
    ) -> None:
        if not self._is_started:
            self.start()

        show_normals = False
        matrix = (
            np.identity(4, dtype=float)
            if transform_matrix is None
            else np.asarray(transform_matrix, dtype=float).reshape((4, 4))
        )
        transform_key = self._active_mesh_transform_key(
            mesh,
            active_transform_mode,
            active_transform_axis,
            selected_item,
        )
        self._update_view_metrics(mesh, matrix, scene_bounds_min, scene_bounds_max)
        if self._try_update_interactive_mesh_transform(
            mesh,
            matrix,
            transform_key=transform_key,
            reset_camera=reset_camera,
            show_grid=show_grid,
            show_axes=show_axes,
            show_normals=show_normals,
            show_section_plane=show_section_plane,
            section_axis=section_axis,
            section_offset=section_offset,
            section_planes=section_planes,
            active_section_plane_id=active_section_plane_id,
            selected_item=selected_item,
            object_origin=object_origin,
            active_transform_mode=active_transform_mode,
            active_transform_axis=active_transform_axis,
            active_transform_angle_delta=active_transform_angle_delta,
            section_result=section_result,
            curve_results=curve_results,
            active_curve_id=active_curve_id,
            surface_source_curve_ids=surface_source_curve_ids,
            surface_previews=surface_previews,
            region_selection=region_selection,
            manual_curve_points=manual_curve_points,
            manual_curve_preview_valid=manual_curve_preview_valid,
            show_axis_gizmo=show_axis_gizmo,
        ):
            return

        self._update_mesh_actor(mesh, matrix)
        self._update_selection_overlay_actors(
            mesh,
            selected_item=selected_item,
            object_origin=object_origin,
            active_transform_mode=active_transform_mode,
            active_transform_axis=active_transform_axis,
            active_transform_angle_delta=active_transform_angle_delta,
        )
        self._update_grid_actor(show_grid)
        self._update_axes_actor(show_axes)
        self._update_axis_gizmo(show_axis_gizmo)
        self._update_normal_actor(mesh, matrix, show_normals)
        self._update_region_selection_actor(mesh, matrix, region_selection)
        self._update_section_plane_actors(
            mesh,
            show_section_plane=show_section_plane,
            section_axis=section_axis,
            section_offset=section_offset,
            section_planes=section_planes,
            active_section_plane_id=active_section_plane_id,
            selected_item=selected_item,
        )
        self._update_section_transform_overlay(
            section_axis=section_axis,
            section_offset=section_offset,
            section_planes=section_planes,
            active_section_plane_id=active_section_plane_id,
            selected_item=selected_item,
            active_transform_mode=active_transform_mode,
            active_transform_axis=active_transform_axis,
            active_transform_angle_delta=active_transform_angle_delta,
        )
        self._update_section_result_actor(section_result)
        self._update_surface_preview_actors(
            surface_previews,
            active_surface_id=active_surface_id,
        )
        self._update_curve_result_actor(
            curve_results,
            active_curve_id=active_curve_id,
            surface_source_curve_ids=surface_source_curve_ids,
        )
        self._update_manual_curve_preview_actor(
            manual_curve_points,
            closed=manual_curve_closed,
            plane_normal=manual_curve_plane_normal,
            snap_to_mesh=manual_curve_snap_to_mesh,
            selected_control_point_index=manual_curve_selected_control_point_index,
            curve_method=manual_curve_method,
            sample_count=manual_curve_sample_count,
            preview_point=manual_curve_preview_point,
            preview_valid=manual_curve_preview_valid,
            preview_snaps_closed=manual_curve_preview_snaps_closed,
            preview_snaps_to_mesh=manual_curve_preview_snaps_to_mesh,
        )

        if reset_camera:
            self.reset_view()
        else:
            self.request_render(scene_dirty=True, overlay_dirty=True)
        self._interactive_transform_key = transform_key

    def _active_mesh_transform_key(
        self,
        mesh: TriangleMeshData | None,
        active_transform_mode: str | None,
        active_transform_axis: str | None,
        selected_item: str | None,
    ) -> tuple[int, str, str | None, str | None] | None:
        if (
            mesh is None
            or selected_item != "model"
            or active_transform_mode not in {"move", "rotate"}
        ):
            return None

        return (id(mesh), active_transform_mode, active_transform_axis, selected_item)

    def _try_update_interactive_mesh_transform(
        self,
        mesh: TriangleMeshData | None,
        matrix: np.ndarray,
        *,
        transform_key: tuple[int, str, str | None, str | None] | None,
        reset_camera: bool,
        show_grid: bool,
        show_axes: bool,
        show_normals: bool,
        show_section_plane: bool,
        section_axis: str,
        section_offset: float,
        section_planes: Sequence[SectionPlaneState] | None,
        active_section_plane_id: str | None,
        selected_item: str | None,
        object_origin: Sequence[float] | None,
        active_transform_mode: str | None,
        active_transform_axis: str | None,
        active_transform_angle_delta: float | None,
        section_result: SectionResult | None,
        curve_results: Sequence[CurveFitResult] | None,
        active_curve_id: str | None = None,
        surface_source_curve_ids: Sequence[str] | None = None,
        show_axis_gizmo: bool = True,
        surface_previews: Sequence[SurfacePreviewMesh] | None = None,
        region_selection: RegionSelection | None = None,
        manual_curve_points: Sequence[Sequence[float]] | np.ndarray | None = None,
        manual_curve_preview_valid: bool = False,
    ) -> bool:
        if (
            transform_key is None
            or transform_key != self._interactive_transform_key
            or reset_camera
            or show_normals
            or section_result is not None
            or curve_results
            or surface_previews
            or region_selection is not None
            or "region_selection" in self._actors_by_role
            or _has_manual_curve_preview(
                manual_curve_points,
                preview_valid=manual_curve_preview_valid,
            )
            or mesh is None
            or self._mesh_actor is None
            or self._mesh_actor_mesh_id != id(mesh)
        ):
            return False

        self._mesh_actor.SetUserMatrix(_vtk_matrix(matrix))
        self._update_selection_overlay_actors(
            mesh,
            selected_item=selected_item,
            object_origin=object_origin,
            active_transform_mode=active_transform_mode,
            active_transform_axis=active_transform_axis,
            active_transform_angle_delta=active_transform_angle_delta,
        )
        self._update_grid_actor(show_grid)
        self._update_axes_actor(show_axes)
        if self._axis_gizmo_requested_visible != bool(show_axis_gizmo):
            self._update_axis_gizmo(show_axis_gizmo)
        self._update_section_plane_actors(
            mesh,
            show_section_plane=show_section_plane,
            section_axis=section_axis,
            section_offset=section_offset,
            section_planes=section_planes,
            active_section_plane_id=active_section_plane_id,
            selected_item=selected_item,
        )
        self.request_render(scene_dirty=True, overlay_dirty=True)
        return True

    def _update_mesh_actor(
        self,
        mesh: TriangleMeshData | None,
        matrix: np.ndarray,
    ) -> None:
        if mesh is None:
            self._remove_actor("mesh")
            self._mesh_actor = None
            self._mesh_actor_mesh_id = None
            return

        mesh_actor = self._ensure_mesh_actor(mesh)
        mesh_actor.SetUserMatrix(_vtk_matrix(matrix))
        self._replace_actor("mesh", mesh_actor, key=id(mesh))

    def _update_selection_overlay_actors(
        self,
        mesh: TriangleMeshData | None,
        *,
        selected_item: str | None,
        object_origin: Sequence[float] | None,
        active_transform_mode: str | None,
        active_transform_axis: str | None,
        active_transform_angle_delta: float | None,
    ) -> None:
        if (
            mesh is None
            or selected_item != "model"
            or self._mesh_min_bound is None
            or self._mesh_max_bound is None
        ):
            self._reset_rotation_overlay_bounds()
            self._clear_overlay_group("selection_overlays")
            self._clear_overlay_group("active_transform_gizmo")
            return

        bounds_key = self._bounds_key()
        origin_key = _array_key(object_origin) if object_origin is not None else None
        selection_key = ("selection", bounds_key, origin_key, round(float(self._view_extent), 9))
        if self._group_keys.get("selection_overlays") != selection_key:
            selection_geometries = [
                build_bounding_box_outline(self._mesh_min_bound, self._mesh_max_bound)
            ]
            selection_line_widths = [SELECTION_BOUNDING_BOX_LINE_WIDTH]
            if object_origin is not None:
                selection_geometries.append(build_origin_marker(object_origin, self._view_extent))
                selection_line_widths.append(2.2)
            if not self._try_update_line_overlay_group(
                "selection_overlays",
                selection_geometries,
                selection_line_widths,
                key=selection_key,
            ):
                self._replace_overlay_group(
                    "selection_overlays",
                    [
                        _line_actor(geometry, line_width=line_width)
                        for geometry, line_width in zip(
                            selection_geometries,
                            selection_line_widths,
                        )
                    ],
                    key=selection_key,
                )

        active_axis = _active_axis_for_gizmo(active_transform_mode, active_transform_axis)
        if active_transform_mode != "rotate":
            self._reset_rotation_overlay_bounds()
        gizmo_key = (
            "gizmo",
            origin_key,
            active_transform_mode,
            active_axis,
            None if active_transform_angle_delta is None else round(float(active_transform_angle_delta), 6),
            self._rotation_overlay_key(mesh, active_transform_mode, active_axis),
            round(float(self._view_extent), 9),
        )
        if object_origin is None or active_transform_mode not in {"move", "rotate"}:
            if active_transform_mode != "rotate" or object_origin is None:
                self._reset_rotation_overlay_bounds()
            self._clear_overlay_group("active_transform_gizmo")
            return

        if self._group_keys.get("active_transform_gizmo") == gizmo_key:
            return

        gizmo_geometries: list[LineGeometry] = []
        gizmo_line_widths: list[float] = []
        if active_axis is not None:
            gizmo_geometries.append(
                build_active_axis_indicator(
                    object_origin,
                    active_axis,
                    self._view_extent,
                )
            )
            gizmo_line_widths.append(2.8)
        if active_transform_mode == "rotate":
            rotation_bounds = self._rotation_overlay_bounds(mesh)
            assert rotation_bounds is not None
            ring_min_bound, ring_max_bound = rotation_bounds
            ring_radius = rotation_ring_radius_for_axis(
                ring_min_bound,
                ring_max_bound,
                active_axis or "Z",
            )
            gizmo_geometries.append(
                build_rotation_ring(
                    object_origin,
                    active_axis or "Z",
                    self._view_extent,
                    radius=ring_radius,
                )
            )
            gizmo_line_widths.append(2.4)
            if active_transform_angle_delta is not None:
                angle_indicator = build_rotation_angle_indicator(
                    object_origin,
                    active_axis or "Z",
                    ring_radius,
                    active_transform_angle_delta,
                )
                if len(angle_indicator.lines) > 0:
                    gizmo_geometries.append(angle_indicator)
                    gizmo_line_widths.append(2.0)
        if self._try_update_line_overlay_group(
            "active_transform_gizmo",
            gizmo_geometries,
            gizmo_line_widths,
            key=gizmo_key,
        ):
            return
        self._replace_overlay_group(
            "active_transform_gizmo",
            [
                _line_actor(geometry, line_width=line_width)
                for geometry, line_width in zip(gizmo_geometries, gizmo_line_widths)
            ],
            key=gizmo_key,
        )

    def _update_grid_actor(self, show_grid: bool) -> None:
        if not show_grid:
            self._remove_actor("grid")
            return

        key = ("grid", self._bounds_key())
        if self._actor_keys.get("grid") == key and "grid" in self._actors_by_role:
            return

        self._replace_actor(
            "grid",
            _line_actor(
                build_xy_grid(self._mesh_min_bound, self._mesh_max_bound),
                line_width=1.0,
            ),
            key=key,
        )

    def _update_axes_actor(self, show_axes: bool) -> None:
        if not show_axes:
            self._remove_actor("axes")
            return

        key = ("axes", self._bounds_key())
        if self._actor_keys.get("axes") == key and "axes" in self._actors_by_role:
            return

        self._replace_actor(
            "axes",
            _line_actor(
                build_world_axes(reference_extent(self._mesh_min_bound, self._mesh_max_bound)),
                line_width=3.0,
            ),
            key=key,
        )

    def _update_axis_gizmo(self, show_axis_gizmo: bool) -> None:
        requested_visible = bool(show_axis_gizmo)
        if (
            self._axis_gizmo_requested_visible == requested_visible
            and self._axis_gizmo_visible == requested_visible
            and (not requested_visible or self._axis_gizmo_renderer is not None)
        ):
            return

        self._axis_gizmo_requested_visible = requested_visible
        if self.render_window is None:
            self.gizmo_dirty = self.gizmo_dirty or self._axis_gizmo_visible != requested_visible
            self._axis_gizmo_visible = requested_visible
            return

        if not requested_visible:
            self._set_axis_gizmo_draw(False)
            return

        self._ensure_axis_gizmo_renderer()
        self._set_axis_gizmo_draw(True)
        self._sync_axis_gizmo_camera(force=True)

    def _ensure_axis_gizmo_renderer(self) -> None:
        if self.render_window is None or self._axis_gizmo_renderer is not None:
            return

        self._axis_gizmo_actor = vtkAxesActor()
        self._axis_gizmo_actor.SetTotalLength(0.72, 0.72, 0.72)
        self._axis_gizmo_actor.SetShaftTypeToCylinder()
        self._axis_gizmo_actor.SetCylinderRadius(0.035)
        self._axis_gizmo_actor.SetConeRadius(0.13)
        self._axis_gizmo_actor.SetSphereRadius(0.065)

        self._axis_gizmo_renderer = vtkRenderer()
        self._axis_gizmo_renderer.SetLayer(1)
        self._axis_gizmo_renderer.SetViewport(0.84, 0.58, 0.98, 0.74)
        self._axis_gizmo_renderer.InteractiveOff()
        try:
            self._axis_gizmo_renderer.SetBackgroundAlpha(0.0)
        except AttributeError:
            pass
        self._axis_gizmo_renderer.AddActor(self._axis_gizmo_actor)

        try:
            current_layers = int(self.render_window.GetNumberOfLayers())
        except AttributeError:
            current_layers = 1
        if current_layers < 2:
            self.render_window.SetNumberOfLayers(2)
        self.render_window.AddRenderer(self._axis_gizmo_renderer)

    def _set_axis_gizmo_draw(self, visible: bool) -> None:
        desired_visibility = bool(visible)
        changed = self._axis_gizmo_visible != desired_visibility
        self._axis_gizmo_visible = desired_visibility
        target_value = 1 if desired_visibility else 0
        if self._axis_gizmo_actor is not None:
            if int(self._axis_gizmo_actor.GetVisibility()) != target_value:
                self._axis_gizmo_actor.SetVisibility(target_value)
                changed = True
        if self._axis_gizmo_renderer is not None:
            try:
                draw_state = int(self._axis_gizmo_renderer.GetDraw())
            except AttributeError:
                draw_state = None
            try:
                if draw_state is None or draw_state != target_value:
                    self._axis_gizmo_renderer.SetDraw(target_value)
                    changed = True
            except AttributeError:
                pass
        if changed:
            self.gizmo_dirty = True
        if not desired_visibility:
            self._axis_gizmo_camera_key = None

    def _sync_axis_gizmo_camera(self, *, force: bool = False) -> None:
        if (
            not self._axis_gizmo_visible
            or self._axis_gizmo_renderer is None
            or self._axis_gizmo_actor is None
        ):
            return

        source_camera = self.renderer.GetActiveCamera()
        forward = _normalized_vector(
            np.asarray(source_camera.GetDirectionOfProjection(), dtype=float),
            fallback=np.asarray([0.0, 0.0, -1.0], dtype=float),
        )
        view_up = _normalized_vector(
            np.asarray(source_camera.GetViewUp(), dtype=float),
            fallback=np.asarray([0.0, 1.0, 0.0], dtype=float),
        )
        key = _axis_gizmo_camera_key(forward, view_up)
        if not force and self._axis_gizmo_camera_key == key:
            return

        self._axis_gizmo_camera_key = key
        camera = self._axis_gizmo_renderer.GetActiveCamera()
        distance = 4.0
        camera.SetFocalPoint(0.0, 0.0, 0.0)
        camera.SetPosition(
            float(-forward[0] * distance),
            float(-forward[1] * distance),
            float(-forward[2] * distance),
        )
        camera.SetViewUp(float(view_up[0]), float(view_up[1]), float(view_up[2]))
        camera.ParallelProjectionOn()
        camera.SetParallelScale(1.15)
        self._axis_gizmo_renderer.ResetCameraClippingRange()

    def _update_normal_actor(
        self,
        mesh: TriangleMeshData | None,
        matrix: np.ndarray,
        show_normals: bool,
    ) -> None:
        if mesh is None or not show_normals or not mesh.has_vertex_normals():
            self._remove_actor("normal")
            return

        key = ("normal", id(mesh))
        if self._actor_keys.get("normal") != key or "normal" not in self._actors_by_role:
            self._replace_actor(
                "normal",
                _line_actor(
                    _normal_lines(mesh, normal_scale=0.012),
                    line_width=1.0,
                ),
                key=key,
            )

        self._actors_by_role["normal"].SetUserMatrix(_vtk_matrix(matrix))

    def _update_section_plane_actors(
        self,
        mesh: TriangleMeshData | None,
        *,
        show_section_plane: bool,
        section_axis: str,
        section_offset: float,
        section_planes: Sequence[SectionPlaneState] | None,
        active_section_plane_id: str | None,
        selected_item: str | None,
    ) -> None:
        if (
            mesh is None
            or self._mesh_min_bound is None
            or self._mesh_max_bound is None
        ):
            self._clear_section_plane_actors()
            return

        planes_to_render = self._section_planes_for_viewport(
            show_section_plane=show_section_plane,
            section_axis=section_axis,
            section_offset=section_offset,
            section_planes=section_planes,
            active_section_plane_id=active_section_plane_id,
            selected_item=selected_item,
        )
        if not planes_to_render:
            self._clear_section_plane_actors()
            return

        key = (
            "section_planes",
            tuple(
                (
                    plane.id,
                    plane.axis,
                    round(float(plane.offset), 9),
                    bool(plane.visible),
                    bool(plane.selected),
                    _array_key(plane.origin),
                    _array_key(plane.normal),
                )
                for plane in planes_to_render
            ),
            self._bounds_key(),
        )
        if (
            self._group_keys.get("section_planes") == key
            and "section_planes" in self._actor_groups
            and self._section_plane_pick_geometries
        ):
            self._section_plane_actors = self._actor_groups["section_planes"]
            return

        section_geometries: list[LineGeometry] = []
        section_line_widths: list[float] = []
        for plane in planes_to_render:
            section_geometry = build_section_plane_preview(
                plane.axis,
                plane.offset,
                self._mesh_min_bound,
                self._mesh_max_bound,
                selected=plane.selected,
                origin=plane.origin,
                normal=plane.normal,
            )
            section_geometries.append(section_geometry)
            section_line_widths.append(3.0 if plane.selected else 2.0)

        self._remove_actor("section_plane")
        if self._try_update_line_overlay_group(
            "section_planes",
            section_geometries,
            section_line_widths,
            key=key,
        ):
            self._section_plane_actors = self._actor_groups["section_planes"]
            self._section_plane_pick_geometries = section_geometries
            self._section_plane_pick_geometry = section_geometries[0]
            return

        section_actors = [
            _line_actor(geometry, line_width=line_width)
            for geometry, line_width in zip(section_geometries, section_line_widths)
        ]

        self._section_plane_actors = section_actors
        self._section_plane_pick_geometries = section_geometries
        self._section_plane_pick_geometry = section_geometries[0]
        self._replace_overlay_group("section_planes", section_actors, key=key)

    def _section_planes_for_viewport(
        self,
        *,
        show_section_plane: bool,
        section_axis: str,
        section_offset: float,
        section_planes: Sequence[SectionPlaneState] | None,
        active_section_plane_id: str | None,
        selected_item: str | None,
    ) -> tuple[ViewportSectionPlane, ...]:
        if section_planes is None:
            if not show_section_plane:
                return ()

            return (
                ViewportSectionPlane(
                    id="section_plane",
                    axis=section_axis,
                    offset=float(section_offset),
                    visible=True,
                    selected=(selected_item == "section_plane"),
                    origin=_axis_plane_origin(section_axis, section_offset),
                    normal=_axis_plane_normal(section_axis),
                ),
            )

        planes: list[ViewportSectionPlane] = []
        for plane in section_planes:
            if not plane.visible:
                continue

            selected = bool(plane.selected) or (
                selected_item == "section_plane" and plane.id == active_section_plane_id
            )
            planes.append(
                ViewportSectionPlane(
                    id=plane.id,
                    axis=plane.axis,
                    offset=float(plane.offset),
                    visible=True,
                    selected=selected,
                    origin=plane_origin(plane),
                    normal=plane_normal(plane),
                )
            )
        return tuple(planes)

    def _clear_section_plane_actors(self) -> None:
        self._remove_actor("section_plane")
        self._clear_overlay_group("section_planes")
        self._section_plane_actors = []
        self._section_plane_pick_geometry = None
        self._section_plane_pick_geometries = []

    def _update_section_transform_overlay(
        self,
        *,
        section_axis: str,
        section_offset: float,
        section_planes: Sequence[SectionPlaneState] | None,
        active_section_plane_id: str | None,
        selected_item: str | None,
        active_transform_mode: str | None,
        active_transform_axis: str | None,
        active_transform_angle_delta: float | None,
    ) -> None:
        if (
            selected_item != "section_plane"
            or active_transform_mode not in {"move", "rotate"}
        ):
            return

        origin = self._active_section_plane_origin(
            section_axis=section_axis,
            section_offset=section_offset,
            section_planes=section_planes,
            active_section_plane_id=active_section_plane_id,
        )
        active_axis = _active_axis_for_gizmo(active_transform_mode, active_transform_axis)
        if origin is None or (active_axis is None and active_transform_mode != "rotate"):
            self._clear_overlay_group("active_transform_gizmo")
            return

        key = (
            "section_transform_gizmo",
            _array_key(origin),
            active_transform_mode,
            active_axis,
            None if active_transform_angle_delta is None else round(float(active_transform_angle_delta), 6),
            round(float(self._view_extent), 9),
            self._bounds_key(),
        )
        if self._group_keys.get("active_transform_gizmo") == key:
            return

        gizmo_geometries: list[LineGeometry] = []
        gizmo_line_widths: list[float] = []
        if active_axis is not None:
            gizmo_geometries.append(
                build_active_axis_indicator(
                    origin,
                    active_axis,
                    self._view_extent,
                )
            )
            gizmo_line_widths.append(2.8)
        if active_transform_mode == "rotate" and active_axis is not None:
            axis = active_axis or "Z"
            ring_radius = rotation_ring_radius_for_axis(
                self._mesh_min_bound if self._mesh_min_bound is not None else origin - 1.0,
                self._mesh_max_bound if self._mesh_max_bound is not None else origin + 1.0,
                axis,
            )
            gizmo_geometries.append(
                build_rotation_ring(
                    origin,
                    axis,
                    self._view_extent,
                    radius=ring_radius,
                )
            )
            gizmo_line_widths.append(2.4)
            if active_transform_angle_delta is not None:
                angle_indicator = build_rotation_angle_indicator(
                    origin,
                    axis,
                    ring_radius,
                    active_transform_angle_delta,
                )
                if len(angle_indicator.lines) > 0:
                    gizmo_geometries.append(angle_indicator)
                    gizmo_line_widths.append(2.0)

        if not gizmo_geometries:
            self._clear_overlay_group("active_transform_gizmo")
            return

        if self._try_update_line_overlay_group(
            "active_transform_gizmo",
            gizmo_geometries,
            gizmo_line_widths,
            key=key,
        ):
            return
        self._replace_overlay_group(
            "active_transform_gizmo",
            [
                _line_actor(geometry, line_width=line_width)
                for geometry, line_width in zip(gizmo_geometries, gizmo_line_widths)
            ],
            key=key,
        )

    def _active_section_plane_origin(
        self,
        *,
        section_axis: str,
        section_offset: float,
        section_planes: Sequence[SectionPlaneState] | None,
        active_section_plane_id: str | None,
    ) -> np.ndarray | None:
        if section_planes is None:
            return _axis_plane_origin(section_axis, section_offset)

        for plane in section_planes:
            if plane.id == active_section_plane_id:
                return plane_origin(plane)
        return None

    def _update_section_result_actor(self, section_result: SectionResult | None) -> None:
        if section_result is None:
            self._remove_actor("section_result")
            return

        key = (
            "section_result",
            id(section_result),
            section_result.segment_count,
            section_result.point_count,
        )
        if self._actor_keys.get("section_result") == key and "section_result" in self._actors_by_role:
            return

        section_lines = _polyline_geometry(
            [polyline.points for polyline in section_result.polylines],
            color=SECTION_RESULT_COLOR,
        )
        self._replace_actor(
            "section_result",
            _line_actor(section_lines, line_width=SECTION_RESULT_LINE_WIDTH),
            key=key,
        )

    def _update_manual_curve_preview_actor(
        self,
        manual_curve_points: Sequence[Sequence[float]] | np.ndarray | None,
        *,
        closed: bool,
        plane_normal: Sequence[float] | None,
        snap_to_mesh: bool,
        selected_control_point_index: int | None,
        curve_method: str,
        sample_count: int,
        preview_point: Sequence[float] | None,
        preview_valid: bool,
        preview_snaps_closed: bool,
        preview_snaps_to_mesh: bool,
    ) -> None:
        control_points = _manual_curve_points_array(manual_curve_points)
        preview = _manual_curve_preview_point_array(
            preview_point,
            preview_valid=preview_valid,
        )
        geometries, line_widths, key = _manual_curve_preview_geometries(
            control_points,
            closed=closed,
            plane_normal=plane_normal,
            snap_to_mesh=snap_to_mesh,
            reference_extent=self._view_extent,
            curve_method=curve_method,
            sample_count=sample_count,
            preview_point=preview,
            preview_valid=preview_valid,
            preview_snaps_closed=preview_snaps_closed,
        )
        has_preview = len(preview) == 1
        if len(control_points) == 0 and not has_preview:
            self._clear_overlay_group("manual_curve_preview")
            self._clear_overlay_group("manual_curve_control_points")
            return

        if not geometries:
            self._clear_overlay_group("manual_curve_preview")
        else:
            lines_updated = self._try_update_line_overlay_group(
                "manual_curve_preview",
                geometries,
                line_widths,
                key=key,
            )
            if not lines_updated:
                self._replace_overlay_group(
                    "manual_curve_preview",
                    [
                        _line_actor(geometry, line_width=line_width)
                        for geometry, line_width in zip(geometries, line_widths)
                    ],
                    key=key,
                )
        point_key = (
            "manual_curve_control_points",
            _array_key(control_points),
            bool(snap_to_mesh),
            None if selected_control_point_index is None else int(selected_control_point_index),
            _array_key(preview) if has_preview else None,
            bool(preview_valid),
            bool(preview_snaps_closed),
            bool(preview_snaps_to_mesh),
            round(float(self._view_extent), 9),
        )
        if self._group_keys.get("manual_curve_control_points") != point_key:
            point_actors = _manual_curve_control_point_actors(
                control_points,
                reference_extent=self._view_extent,
                snap_to_mesh=snap_to_mesh,
                selected_index=selected_control_point_index,
                preview_point=preview,
                preview_valid=preview_valid,
                preview_snaps_closed=preview_snaps_closed,
            )
            self._replace_overlay_group(
                "manual_curve_control_points",
                point_actors,
                key=point_key,
            )

    def _update_region_selection_actor(
        self,
        mesh: TriangleMeshData | None,
        matrix: np.ndarray,
        region_selection: RegionSelection | None,
    ) -> None:
        if (
            mesh is None
            or region_selection is None
            or not bool(region_selection.visible)
            or not region_selection.triangle_indices
        ):
            self._remove_actor("region_selection")
            return

        key = _region_selection_key(mesh, region_selection)
        actor = self._actors_by_role.get("region_selection")
        if self._actor_keys.get("region_selection") != key or actor is None:
            actor = _region_selection_actor(mesh, region_selection)
            self._replace_actor("region_selection", actor, key=key)

        actor.SetUserMatrix(_vtk_matrix(matrix))

    def _update_surface_preview_actors(
        self,
        surface_previews: Sequence[SurfacePreviewMesh] | None,
        *,
        active_surface_id: str | None,
    ) -> None:
        if not surface_previews:
            self._clear_overlay_group("surface_previews")
            return

        renderable_previews = [
            preview
            for preview in surface_previews
            if len(preview.vertices) > 0 and len(preview.faces) > 0
        ]
        if not renderable_previews:
            self._clear_overlay_group("surface_previews")
            return

        key = (
            "surface_previews",
            tuple(
                (
                    preview.source_surface_id,
                    preview.vertices.shape,
                    preview.faces.shape,
                    _array_key(np.min(preview.vertices, axis=0)),
                    _array_key(np.max(preview.vertices, axis=0)),
                    bool(preview.selected or preview.source_surface_id == active_surface_id),
                    None if preview.opacity is None else round(float(preview.opacity), 4),
                    bool(preview.wireframe_overlay),
                )
                for preview in renderable_previews
            ),
        )
        if (
            self._group_keys.get("surface_previews") == key
            and "surface_previews" in self._actor_groups
        ):
            return

        actors = [
            _surface_preview_actor(
                preview,
                selected=bool(preview.selected or preview.source_surface_id == active_surface_id),
            )
            for preview in renderable_previews
        ]
        self._replace_overlay_group("surface_previews", actors, key=key)

    def _update_curve_result_actor(
        self,
        curve_results: Sequence[CurveFitResult] | None,
        *,
        active_curve_id: str | None = None,
        surface_source_curve_ids: Sequence[str] | None = None,
    ) -> None:
        if not curve_results:
            self._remove_actor("curve_result")
            self._clear_overlay_group("selected_curve_result")
            self._clear_overlay_group("curve_results")
            self._clear_overlay_group("selected_manual_curve_result")
            return

        self._remove_actor("curve_result")
        self._clear_overlay_group("selected_curve_result")
        source_ids = {str(curve_id) for curve_id in (surface_source_curve_ids or ())}
        display_groups = _curve_display_groups(
            curve_results,
            active_curve_id=active_curve_id,
            surface_source_curve_ids=source_ids,
        )
        if not display_groups:
            self._clear_overlay_group("curve_results")
            self._clear_overlay_group("selected_manual_curve_result")
            return

        selected_manual_results = [
            result
            for category, results in display_groups
            if category in {"selected", "active"}
            for result in results
            if _is_manual_curve_result(result)
        ]
        self._update_selected_manual_curve_overlay(selected_manual_results)

        key = (
            "curve_results",
            tuple(
                (
                    category,
                    tuple(_curve_display_key(result, category) for result in results),
                )
                for category, results in display_groups
            ),
        )
        if (
            self._group_keys.get("curve_results") == key
            and "curve_results" in self._actor_groups
        ):
            return

        geometries: list[LineGeometry] = []
        line_widths: list[float] = []
        for category, results in display_groups:
            style = CURVE_DISPLAY_STYLES[category]
            geometries.append(
                _polyline_geometry(
                    [result.fitted_points for result in results],
                    color=style.color,
                )
            )
            line_widths.append(style.line_width)

        if self._try_update_line_overlay_group(
            "curve_results",
            geometries,
            line_widths,
            key=key,
        ):
            return

        self._replace_overlay_group(
            "curve_results",
            [
                _line_actor(geometry, line_width=line_width)
                for geometry, line_width in zip(geometries, line_widths)
            ],
            key=key,
        )

    def _update_selected_manual_curve_overlay(self, curve_results: Sequence[CurveFitResult]) -> None:
        if not curve_results:
            self._clear_overlay_group("selected_manual_curve_result")
            return

        key = (
            "selected_manual_curve_result",
            tuple(_curve_display_key(result, "manual_overlay") for result in curve_results),
        )
        geometries = [
            _polyline_geometry(
                [result.fitted_points for result in curve_results],
                color=ACTIVE_CURVE_COLOR,
            )
        ]
        line_widths = [MANUAL_CURVE_ACTIVE_LINE_WIDTH]
        if self._try_update_line_overlay_group(
            "selected_manual_curve_result",
            geometries,
            line_widths,
            key=key,
        ):
            return
        self._replace_overlay_group(
            "selected_manual_curve_result",
            [_line_actor(geometries[0], line_width=line_widths[0])],
            key=key,
        )

    def _replace_actor(self, role: str, actor: vtkActor, *, key: object | None = None) -> None:
        current_actor = self._actors_by_role.get(role)
        if current_actor is actor:
            self._actor_keys[role] = key
            return

        if current_actor is not None:
            self.renderer.RemoveActor(current_actor)

        self._actors_by_role[role] = actor
        self._actor_keys[role] = key
        self.renderer.AddActor(actor)

    def _remove_actor(self, role: str) -> None:
        actor = self._actors_by_role.pop(role, None)
        self._actor_keys.pop(role, None)
        if actor is not None:
            self.renderer.RemoveActor(actor)

    def _try_update_line_overlay_group(
        self,
        group_name: str,
        geometries: Sequence[LineGeometry],
        line_widths: Sequence[float],
        *,
        key: object | None = None,
    ) -> bool:
        actors = self._actor_groups.get(group_name)
        if (
            actors is None
            or len(actors) != len(geometries)
            or len(line_widths) != len(geometries)
        ):
            return False

        updates: list[tuple[vtkActor, vtkPolyDataMapper, LineGeometry, float]] = []
        for actor, geometry, line_width in zip(actors, geometries, line_widths):
            mapper = actor.GetMapper()
            if mapper is None or not hasattr(mapper, "SetInputData"):
                return False
            updates.append((actor, mapper, geometry, float(line_width)))

        for actor, mapper, geometry, line_width in updates:
            mapper.SetInputData(_line_polydata(geometry))
            mapper.Update()
            actor.GetProperty().SetLineWidth(line_width)

        self._group_keys[group_name] = key
        return True

    def _replace_overlay_group(
        self,
        group_name: str,
        actors: Sequence[vtkActor],
        *,
        key: object | None = None,
    ) -> None:
        self._clear_overlay_group(group_name)
        actor_list = list(actors)
        self._actor_groups[group_name] = actor_list
        self._group_keys[group_name] = key
        renderer = self._renderer_for_overlay_group(group_name)
        for actor in actor_list:
            renderer.AddActor(actor)

    def _clear_overlay_group(self, group_name: str) -> None:
        actors = self._actor_groups.pop(group_name, [])
        self._group_keys.pop(group_name, None)
        for actor in actors:
            self.renderer.RemoveActor(actor)
            if self._manual_overlay_renderer is not None:
                self._manual_overlay_renderer.RemoveActor(actor)

    def _renderer_for_overlay_group(self, group_name: str) -> vtkRenderer:
        if group_name in {
            "manual_curve_preview",
            "manual_curve_control_points",
            "selected_manual_curve_result",
        }:
            return self._ensure_manual_overlay_renderer()
        return self.renderer

    def _ensure_manual_overlay_renderer(self) -> vtkRenderer:
        if self.render_window is None:
            return self.renderer
        if self._manual_overlay_renderer is not None:
            self._manual_overlay_renderer.SetActiveCamera(self.renderer.GetActiveCamera())
            return self._manual_overlay_renderer

        self._manual_overlay_renderer = vtkRenderer()
        self._manual_overlay_renderer.SetLayer(2)
        self._manual_overlay_renderer.SetViewport(0.0, 0.0, 1.0, 1.0)
        self._manual_overlay_renderer.InteractiveOff()
        self._manual_overlay_renderer.SetActiveCamera(self.renderer.GetActiveCamera())
        try:
            self._manual_overlay_renderer.SetBackgroundAlpha(0.0)
        except AttributeError:
            pass
        try:
            current_layers = int(self.render_window.GetNumberOfLayers())
        except AttributeError:
            current_layers = 1
        if current_layers < 3:
            self.render_window.SetNumberOfLayers(3)
        self.render_window.AddRenderer(self._manual_overlay_renderer)
        return self._manual_overlay_renderer

    def _set_actor_visible(self, actor: vtkActor, visible: bool) -> None:
        actor.SetVisibility(1 if visible else 0)

    def _bounds_key(self) -> tuple[tuple[float, ...] | None, tuple[float, ...] | None]:
        return (_array_key(self._mesh_min_bound), _array_key(self._mesh_max_bound))

    def _rotation_overlay_key(
        self,
        mesh: TriangleMeshData | None,
        active_transform_mode: str | None,
        active_axis: str | None,
    ) -> tuple[int, str, tuple[float, ...], tuple[float, ...]] | None:
        if mesh is None or active_transform_mode != "rotate" or active_axis is None:
            return None

        bounds = self._rotation_overlay_bounds(mesh)
        if bounds is None:
            return None

        minimum_bound, maximum_bound = bounds
        return (
            id(mesh),
            active_axis,
            _array_key(minimum_bound) or tuple(),
            _array_key(maximum_bound) or tuple(),
        )

    def _rotation_overlay_bounds(
        self,
        mesh: TriangleMeshData | None,
    ) -> tuple[np.ndarray, np.ndarray] | None:
        if mesh is None or self._mesh_min_bound is None or self._mesh_max_bound is None:
            self._reset_rotation_overlay_bounds()
            return None

        mesh_id = id(mesh)
        if (
            self._rotation_overlay_mesh_id != mesh_id
            or self._rotation_overlay_min_bound is None
            or self._rotation_overlay_max_bound is None
        ):
            self._rotation_overlay_mesh_id = mesh_id
            self._rotation_overlay_min_bound = self._mesh_min_bound.copy()
            self._rotation_overlay_max_bound = self._mesh_max_bound.copy()

        return (
            self._rotation_overlay_min_bound,
            self._rotation_overlay_max_bound,
        )

    def _reset_rotation_overlay_bounds(self) -> None:
        self._rotation_overlay_mesh_id = None
        self._rotation_overlay_min_bound = None
        self._rotation_overlay_max_bound = None

    def frame_model(self) -> None:
        self.reset_view()

    def set_named_view(self, name: str) -> None:
        view_key = str(name).strip().lower()
        direction, view_up = _named_view_vectors(view_key)
        extent = max(float(self._view_extent), 1.0)
        focal_point = np.asarray(
            self.renderer.GetActiveCamera().GetFocalPoint(),
            dtype=float,
        )
        distance = extent * 2.8
        position = focal_point + direction * distance

        camera = self.renderer.GetActiveCamera()
        camera.SetFocalPoint(
            float(focal_point[0]),
            float(focal_point[1]),
            float(focal_point[2]),
        )
        camera.SetPosition(
            float(position[0]),
            float(position[1]),
            float(position[2]),
        )
        camera.SetViewUp(
            float(view_up[0]),
            float(view_up[1]),
            float(view_up[2]),
        )
        self.renderer.ResetCameraClippingRange()
        self.request_render(camera_dirty=True)

    def frame_bounds(
        self,
        minimum_bound: Sequence[float],
        maximum_bound: Sequence[float],
    ) -> None:
        minimum = np.asarray(minimum_bound, dtype=float)
        maximum = np.asarray(maximum_bound, dtype=float)
        if minimum.shape != (3,) or maximum.shape != (3,):
            return
        if not (np.all(np.isfinite(minimum)) and np.all(np.isfinite(maximum))):
            return

        center = (minimum + maximum) * 0.5
        extent = max(float(np.max(maximum - minimum)), 1.0)
        camera = self.renderer.GetActiveCamera()
        camera.SetFocalPoint(float(center[0]), float(center[1]), float(center[2]))
        camera.SetPosition(
            float(center[0] + extent * 1.6),
            float(center[1] - extent * 1.8),
            float(center[2] + extent * 1.2),
        )
        camera.SetViewUp(0.0, 0.0, 1.0)
        self.renderer.ResetCameraClippingRange()
        self._render()

    def reset_view(self) -> None:
        camera = self.renderer.GetActiveCamera()
        extent = max(float(self._view_extent), 1.0)
        center = self._view_center
        camera.SetFocalPoint(float(center[0]), float(center[1]), float(center[2]))
        camera.SetPosition(
            float(center[0] + extent * 1.6),
            float(center[1] - extent * 1.8),
            float(center[2] + extent * 1.2),
        )
        camera.SetViewUp(0.0, 0.0, 1.0)
        self.renderer.ResetCameraClippingRange()
        self._render()

    def reset_camera(self) -> None:
        self.reset_view()

    def _add_line_actor(self, geometry: LineGeometry, *, line_width: float) -> vtkActor:
        actor = _line_actor(geometry, line_width=line_width)
        self.renderer.AddActor(actor)
        return actor

    def _add_tube_actor(self, geometry: LineGeometry, *, radius: float) -> vtkActor:
        actor = _tube_actor(geometry, radius=radius)
        self.renderer.AddActor(actor)
        return actor

    def _ensure_mesh_actor(self, mesh: TriangleMeshData) -> vtkActor:
        mesh_id = id(mesh)
        if self._mesh_actor is None or self._mesh_actor_mesh_id != mesh_id:
            self._mesh_actor = _mesh_actor(mesh)
            self._mesh_actor_mesh_id = mesh_id
        return self._mesh_actor

    def _update_view_metrics(
        self,
        mesh: TriangleMeshData | None,
        transform_matrix: np.ndarray,
        scene_bounds_min: Sequence[float] | None = None,
        scene_bounds_max: Sequence[float] | None = None,
    ) -> None:
        if mesh is None:
            self._mesh_local_min_bound = None
            self._mesh_local_max_bound = None
            self._mesh_bounds_mesh_id = None
            return

        if scene_bounds_min is not None and scene_bounds_max is not None:
            local_min_bound = np.asarray(scene_bounds_min, dtype=float)
            local_max_bound = np.asarray(scene_bounds_max, dtype=float)
            self._mesh_bounds_mesh_id = None
            self._mesh_local_min_bound = local_min_bound
            self._mesh_local_max_bound = local_max_bound
            self._mesh_min_bound, self._mesh_max_bound = _transformed_bounds(
                local_min_bound,
                local_max_bound,
                transform_matrix,
            )
            self._view_center = (self._mesh_min_bound + self._mesh_max_bound) * 0.5
            self._view_extent = max(
                float(np.max(self._mesh_max_bound - self._mesh_min_bound)),
                1.0,
            )
            return

        mesh_id = id(mesh)
        if self._mesh_bounds_mesh_id != mesh_id:
            bounds = mesh.get_axis_aligned_bounding_box()
            self._mesh_local_min_bound = np.asarray(bounds.get_min_bound(), dtype=float)
            self._mesh_local_max_bound = np.asarray(bounds.get_max_bound(), dtype=float)
            self._mesh_bounds_mesh_id = mesh_id

        assert self._mesh_local_min_bound is not None
        assert self._mesh_local_max_bound is not None
        self._mesh_min_bound, self._mesh_max_bound = _transformed_bounds(
            self._mesh_local_min_bound,
            self._mesh_local_max_bound,
            transform_matrix,
        )
        self._view_center = (self._mesh_min_bound + self._mesh_max_bound) * 0.5
        self._view_extent = max(float(np.max(self._mesh_max_bound - self._mesh_min_bound)), 1.0)

    def _attach_render_window_to_widget(self) -> None:
        if self.widget is None or self.render_window is None:
            return

        # The Tk-specific VTK interactor needs vtkRenderingTk.dll, which is not
        # included in all wheels. Hosting a normal VTK window avoids that path.
        self.render_window.SetWindowInfo(str(self.widget.winfo_id()))
        self._resize_render_window()

    def request_render(
        self,
        *,
        scene_dirty: bool = False,
        camera_dirty: bool = False,
        overlay_dirty: bool = False,
        gizmo_dirty: bool = False,
        delay_ms: int | None = None,
    ) -> None:
        self.scene_dirty = self.scene_dirty or bool(scene_dirty)
        self.camera_dirty = self.camera_dirty or bool(camera_dirty)
        self.overlay_dirty = self.overlay_dirty or bool(overlay_dirty)
        self.gizmo_dirty = self.gizmo_dirty or bool(gizmo_dirty)

        if self._is_closed:
            self._count_skipped_render()
            self._clear_render_dirty()
            return

        if self.widget is None:
            self._render()
            return

        if self.render_window is None:
            self._count_skipped_render()
            self._clear_render_dirty()
            return

        if self._render_after_id is not None:
            self._count_skipped_render()
            return

        try:
            if delay_ms is not None and delay_ms > 0:
                self._render_after_id = self.widget.after(
                    int(delay_ms),
                    self._flush_requested_render,
                )
            else:
                self._render_after_id = self.widget.after_idle(self._flush_requested_render)
        except TclError:
            self._count_skipped_render()
            self._clear_render_dirty()

    def _flush_requested_render(self) -> None:
        self._render_after_id = None
        if self._is_closed:
            self._count_skipped_render()
            self._clear_render_dirty()
            return

        self._render()

    def _cancel_pending_render(self) -> None:
        if self._render_after_id is None or self.widget is None:
            self._render_after_id = None
            return

        try:
            self.widget.after_cancel(self._render_after_id)
        except TclError:
            pass
        self._render_after_id = None

    def _clear_render_dirty(self) -> None:
        self.scene_dirty = False
        self.camera_dirty = False
        self.overlay_dirty = False
        self.gizmo_dirty = False

    def _count_render(self) -> None:
        if not self._render_counters_enabled:
            return

        self.render_count += 1
        self.last_render_time = time.perf_counter()

    def _count_skipped_render(self) -> None:
        if self._render_counters_enabled:
            self.skipped_render_count += 1

    def _bind_widget_events(self) -> None:
        if self.widget is None:
            return

        self.widget.bind("<Configure>", self._on_configure)
        self.widget.bind("<ButtonPress-1>", self._on_left_button_press)
        self.widget.bind("<ButtonRelease-1>", self._on_left_button_release)
        self.widget.bind("<ButtonPress-2>", self._on_middle_button_press)
        self.widget.bind("<ButtonRelease-2>", self._on_middle_button_release)
        self.widget.bind("<ButtonPress-3>", self._on_right_button_press)
        self.widget.bind("<ButtonRelease-3>", self._on_right_button_release)
        self.widget.bind("<Motion>", self._on_mouse_move)
        self.widget.bind("<Leave>", self._on_mouse_leave)
        self.widget.bind("<MouseWheel>", self._on_mouse_wheel)
        self.widget.bind("<KeyPress>", self._on_key_press)

    def _on_configure(self, _event: Event[Canvas]) -> None:
        self._resize_render_window()
        self.request_render(overlay_dirty=True)

    def _resize_render_window(self) -> None:
        if self.widget is None or self.render_window is None:
            return

        width = max(int(self.widget.winfo_width()), 1)
        height = max(int(self.widget.winfo_height()), 1)
        self.render_window.SetSize(width, height)

    def _on_left_button_press(self, event: Event[Canvas]) -> None:
        self._left_press_position = (int(event.x), int(event.y))
        self._set_mouse_button_pressed("left", True)
        if self._dispatch_pointer_event("left_press", event):
            self.request_render(overlay_dirty=True)
            return

        self._forward_mouse_event(event, "LeftButtonPressEvent")

    def _on_left_button_release(self, event: Event[Canvas]) -> None:
        self._set_mouse_button_pressed("left", False)
        if self._dispatch_pointer_event("left_release", event):
            self._left_press_position = None
            self.request_render(scene_dirty=True, overlay_dirty=True)
            return

        self._forward_mouse_event(event, "LeftButtonReleaseEvent")
        if self._selection_callback is None:
            return

        if not self._is_click_release(event):
            return

        target = self._pick_target(int(event.x), int(event.y))
        self._selection_callback(target)

    def _on_middle_button_press(self, event: Event[Canvas]) -> None:
        self._set_mouse_button_pressed("middle", True)
        if self._dispatch_pointer_event("middle_press", event):
            self.request_render(overlay_dirty=True)
            return

        self._forward_mouse_event(event, "MiddleButtonPressEvent")

    def _on_middle_button_release(self, event: Event[Canvas]) -> None:
        self._set_mouse_button_pressed("middle", False)
        if self._dispatch_pointer_event("middle_release", event):
            self.request_render(overlay_dirty=True)
            return

        self._forward_mouse_event(event, "MiddleButtonReleaseEvent")

    def _on_right_button_press(self, event: Event[Canvas]) -> None:
        self._set_mouse_button_pressed("right", True)
        if self._dispatch_pointer_event("right_press", event):
            self.request_render(overlay_dirty=True)
            return

        self._forward_mouse_event(event, "RightButtonPressEvent")

    def _on_right_button_release(self, event: Event[Canvas]) -> None:
        self._set_mouse_button_pressed("right", False)
        if self._dispatch_pointer_event("right_release", event):
            self.request_render(scene_dirty=True, overlay_dirty=True)
            return

        self._forward_mouse_event(event, "RightButtonReleaseEvent")

    def _on_mouse_move(self, event: Event[Canvas]) -> None:
        if self._dispatch_pointer_event("motion", event):
            self.request_render(scene_dirty=True, overlay_dirty=True)
            return

        if not self._any_mouse_button_pressed() and not self._active_interaction:
            self._remember_mouse_position(event)
            return

        self._forward_mouse_event(event, "MouseMoveEvent")

    def _on_mouse_leave(self, event: Event[Canvas]) -> None:
        if self._dispatch_pointer_event("leave", event):
            self.request_render(overlay_dirty=True)

    def _on_mouse_wheel(self, event: Event[Canvas]) -> None:
        if self.interactor is None:
            return

        self._set_interactor_event(event)
        if int(event.delta) > 0:
            self.interactor.MouseWheelForwardEvent()
        else:
            self.interactor.MouseWheelBackwardEvent()
        self.request_render(camera_dirty=True)

    def _on_key_press(self, event: Event[Canvas]) -> None:
        if self.interactor is None:
            return

        if _is_app_shortcut_key_event(event):
            return

        self._set_interactor_event(event)
        self.interactor.KeyPressEvent()
        self.interactor.CharEvent()
        self._render()

    def _forward_mouse_event(self, event: Event[Canvas], interactor_event: str) -> None:
        if self.interactor is None:
            return

        if self.widget is not None:
            self.widget.focus_set()
        self._set_interactor_event(event)
        getattr(self.interactor, interactor_event)()
        self.request_render(camera_dirty=interactor_event == "MouseMoveEvent")

    def _set_mouse_button_pressed(self, button: str, pressed: bool) -> None:
        if button == "left":
            self._left_button_pressed = bool(pressed)
        elif button == "middle":
            self._middle_button_pressed = bool(pressed)
        elif button == "right":
            self._right_button_pressed = bool(pressed)
        self._active_interaction = self._any_mouse_button_pressed()

    def _any_mouse_button_pressed(self) -> bool:
        return bool(
            self._left_button_pressed
            or self._middle_button_pressed
            or self._right_button_pressed
        )

    def _dispatch_pointer_event(self, event_type: str, event: Event[Canvas]) -> bool:
        if self._pointer_callback is None:
            return False

        x_position = int(getattr(event, "x", self._last_mouse_position[0]))
        y_position = int(getattr(event, "y", self._last_mouse_position[1]))
        self._last_mouse_position = (x_position, y_position)
        state = int(getattr(event, "state", 0))
        shift = bool(state & 0x0001)
        ctrl = bool(state & 0x0004)
        return bool(self._pointer_callback(event_type, x_position, y_position, shift, ctrl))

    def _set_interactor_event(self, event: Event[Canvas]) -> None:
        if self.interactor is None:
            return

        self._remember_mouse_position(event)
        x_position, y_position = self._last_mouse_position
        state = int(getattr(event, "state", 0))
        ctrl = 1 if state & 0x0004 else 0
        shift = 1 if state & 0x0001 else 0
        key_char = str(getattr(event, "char", "") or "")[:1]
        key_symbol = str(getattr(event, "keysym", "") or "")
        self.interactor.SetEventInformationFlipY(
            x_position,
            y_position,
            ctrl,
            shift,
            key_char,
            0,
            key_symbol,
        )

    def _remember_mouse_position(self, event: Event[Canvas]) -> None:
        x_position = int(getattr(event, "x", self._last_mouse_position[0]))
        y_position = int(getattr(event, "y", self._last_mouse_position[1]))
        self._last_mouse_position = (x_position, y_position)

    def _is_click_release(self, event: Event[Canvas]) -> bool:
        if self._left_press_position is None:
            return True

        start_x, start_y = self._left_press_position
        distance = abs(int(event.x) - start_x) + abs(int(event.y) - start_y)
        self._left_press_position = None
        return distance <= 4

    def _pick_target(self, x_position: int, y_position: int) -> str | None:
        if self.widget is None:
            return None

        height = max(int(self.widget.winfo_height()), 1)
        display_point = np.asarray([float(x_position), float(height - y_position)], dtype=float)
        for section_plane_geometry in self._section_plane_pick_geometries:
            if _screen_point_near_geometry(
                self.renderer,
                section_plane_geometry,
                display_point,
                tolerance=12.0,
            ):
                return "section_plane"
        if self._screen_point_inside_mesh_bounds(display_point, padding=10.0):
            return "model"
        return None

    def _screen_point_inside_mesh_bounds(
        self,
        display_point: np.ndarray,
        *,
        padding: float,
    ) -> bool:
        if (
            self._mesh_actor is None
            or self._mesh_min_bound is None
            or self._mesh_max_bound is None
        ):
            return False

        projected = _project_points(
            self.renderer,
            _bounds_corners(self._mesh_min_bound, self._mesh_max_bound),
        )
        if len(projected) == 0:
            return False

        minimum = np.min(projected, axis=0) - float(padding)
        maximum = np.max(projected, axis=0) + float(padding)
        return bool(np.all(display_point >= minimum) and np.all(display_point <= maximum))

    def _render(self) -> None:
        if self.render_window is None or self._is_closed:
            self._count_skipped_render()
            self._clear_render_dirty()
            return

        try:
            if self._should_sync_axis_gizmo_for_render():
                self._sync_axis_gizmo_camera()
            self.render_window.Render()
            self._count_render()
        except TclError:
            self._count_skipped_render()
        finally:
            self._clear_render_dirty()

    def _should_sync_axis_gizmo_for_render(self) -> bool:
        if not self._axis_gizmo_visible:
            return False

        return bool(
            self.camera_dirty
            or self.gizmo_dirty
            or not (self.scene_dirty or self.overlay_dirty)
        )


def _screen_point_near_geometry(
    renderer: vtkRenderer,
    geometry: LineGeometry | None,
    display_point: np.ndarray,
    *,
    tolerance: float,
) -> bool:
    if geometry is None or len(geometry.lines) == 0 or len(geometry.points) == 0:
        return False

    projected = _project_points(renderer, geometry.points)
    if len(projected) == 0:
        return False

    for start_index, end_index in geometry.lines:
        distance = _point_to_segment_distance(
            display_point,
            projected[int(start_index)],
            projected[int(end_index)],
        )
        if distance <= float(tolerance):
            return True
    return False


def _is_app_shortcut_key_event(event: object) -> bool:
    keysym = str(getattr(event, "keysym", "") or "").lower()
    return keysym in APP_SHORTCUT_KEYSYMS


def _project_points(renderer: vtkRenderer, points: Sequence[Sequence[float]]) -> np.ndarray:
    projected: list[tuple[float, float]] = []
    for point in np.asarray(points, dtype=float).reshape((-1, 3)):
        renderer.SetWorldPoint(float(point[0]), float(point[1]), float(point[2]), 1.0)
        renderer.WorldToDisplay()
        display = renderer.GetDisplayPoint()
        if np.isfinite(display[0]) and np.isfinite(display[1]):
            projected.append((float(display[0]), float(display[1])))
    return np.asarray(projected, dtype=float).reshape((-1, 2))


def _bounds_corners(
    minimum: Sequence[float],
    maximum: Sequence[float],
) -> np.ndarray:
    minimum = np.asarray(minimum, dtype=float)
    maximum = np.asarray(maximum, dtype=float)
    return np.asarray(
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


def _point_to_segment_distance(
    point: Sequence[float],
    start: Sequence[float],
    end: Sequence[float],
) -> float:
    point_array = np.asarray(point, dtype=float)
    start_array = np.asarray(start, dtype=float)
    end_array = np.asarray(end, dtype=float)
    segment = end_array - start_array
    length_squared = float(np.dot(segment, segment))
    if length_squared <= 1e-12:
        return float(np.linalg.norm(point_array - start_array))

    projection = float(np.dot(point_array - start_array, segment) / length_squared)
    projection = min(max(projection, 0.0), 1.0)
    closest = start_array + projection * segment
    return float(np.linalg.norm(point_array - closest))


def _curve_display_groups(
    curve_results: Sequence[CurveFitResult],
    *,
    active_curve_id: str | None,
    surface_source_curve_ids: set[str],
) -> tuple[tuple[str, list[CurveFitResult]], ...]:
    grouped: dict[str, list[CurveFitResult]] = {
        category: [] for category in CURVE_DISPLAY_CATEGORY_ORDER
    }
    for curve in curve_results:
        category = _classify_curve_display(
            curve,
            active_curve_id=active_curve_id,
            surface_source_curve_ids=surface_source_curve_ids,
        )
        if category == "hidden":
            continue
        points = np.asarray(getattr(curve, "fitted_points", []), dtype=float)
        if points.ndim != 2 or points.shape[1] != 3 or len(points) < 2:
            continue
        grouped.setdefault(category, []).append(curve)

    return tuple(
        (category, grouped[category])
        for category in CURVE_DISPLAY_CATEGORY_ORDER
        if grouped.get(category)
    )


def _classify_curve_display(
    curve: object,
    *,
    active_curve_id: str | None = None,
    surface_source_curve_ids: set[str] | Sequence[str] | None = None,
) -> str:
    if not bool(getattr(curve, "visible", True)):
        return "hidden"

    curve_id = _curve_identifier(curve)
    source_ids = {str(source_id) for source_id in (surface_source_curve_ids or ())}
    category = "normal"
    if bool(getattr(curve, "is_tiny_fragment", False)):
        category = "tiny"
    if is_repaired_curve(curve):
        category = "repaired"
    if curve_id is not None and curve_id in source_ids:
        category = "active_surface_source"
    if bool(getattr(curve, "selected", False)):
        category = "selected"
    if active_curve_id is not None and curve_id == str(active_curve_id):
        category = "active"
    return category


def _curve_identifier(curve: object) -> str | None:
    curve_id = getattr(curve, "id", None)
    if curve_id is None:
        return None
    return str(curve_id)


def _is_manual_curve_result(curve: object) -> bool:
    metadata = getattr(curve, "metadata", {})
    if not isinstance(metadata, dict):
        return False

    creation_type = str(metadata.get("creation_type", "")).strip().lower()
    snap_mode = str(metadata.get("snap_mode", "")).strip().lower()
    return bool(
        creation_type in {"manual", "curve_on_mesh"}
        or snap_mode == "mesh"
        or "control_points" in metadata
        or metadata.get("snap_to_mesh") is True
    )


def _curve_display_key(curve: CurveFitResult, category: str) -> tuple[object, ...]:
    points = np.asarray(getattr(curve, "fitted_points", []), dtype=float)
    if points.ndim == 2 and points.shape[1] == 3 and len(points) > 0:
        minimum = _array_key(np.min(points, axis=0))
        maximum = _array_key(np.max(points, axis=0))
        first = _array_key(points[0])
        last = _array_key(points[-1])
        point_count = int(len(points))
    else:
        minimum = maximum = first = last = None
        point_count = 0

    return (
        _curve_identifier(curve) or id(curve),
        category,
        point_count,
        minimum,
        maximum,
        first,
        last,
        bool(getattr(curve, "selected", False)),
        bool(getattr(curve, "visible", True)),
    )


def _manual_curve_preview_geometries(
    manual_curve_points: Sequence[Sequence[float]] | np.ndarray | None,
    *,
    closed: bool,
    plane_normal: Sequence[float] | None,
    snap_to_mesh: bool,
    reference_extent: float,
    curve_method: str,
    sample_count: int,
    preview_point: np.ndarray,
    preview_valid: bool,
    preview_snaps_closed: bool,
) -> tuple[list[LineGeometry], list[float], object | None]:
    points = _manual_curve_points_array(manual_curve_points)
    preview = _manual_curve_preview_point_array(
        preview_point,
        preview_valid=preview_valid,
    )
    if len(points) == 0 and len(preview) == 0:
        return ([], [], None)

    normal = _normalized_vector(
        np.asarray(
            [0.0, 0.0, 1.0] if plane_normal is None else plane_normal,
            dtype=float,
        ).reshape(3),
        fallback=np.asarray([0.0, 0.0, 1.0], dtype=float),
    )
    geometries: list[LineGeometry] = []
    line_widths: list[float] = []
    if len(points) >= 2:
        geometries.append(
            _manual_curve_polyline_geometry(
                points,
                closed=bool(closed),
                color=MANUAL_CURVE_CONTROL_POLYGON_COLOR,
            )
        )
        line_widths.append(MANUAL_CURVE_POINT_LINE_WIDTH)
        sampled_points = sample_manual_curve(
            points,
            is_closed=bool(closed),
            method=curve_method,
            sample_count=sample_count,
        )
        if len(sampled_points) >= 2:
            geometries.append(
                _manual_curve_polyline_geometry(
                    sampled_points,
                    closed=False,
                    color=(
                        MANUAL_CURVE_SNAP_POLYLINE_COLOR
                        if snap_to_mesh
                        else MANUAL_CURVE_POLYLINE_COLOR
                    ),
                )
            )
            line_widths.append(MANUAL_CURVE_PREVIEW_LINE_WIDTH)
    if len(preview) == 1 and len(points) >= 1:
        preview_target = points[0] if bool(preview_snaps_closed) and len(points) >= 3 else preview[0]
        geometries.append(
            _manual_curve_polyline_geometry(
                np.asarray([points[-1], preview_target], dtype=float),
                closed=False,
                color=MANUAL_CURVE_PREVIEW_LINE_COLOR,
            )
        )
        line_widths.append(MANUAL_CURVE_GHOST_LINE_WIDTH)

    key = (
        "manual_curve_preview",
        _array_key(points),
        bool(closed),
        bool(snap_to_mesh),
        _array_key(normal),
        str(curve_method).strip().lower(),
        int(sample_count),
        _array_key(preview) if len(preview) else None,
        bool(preview_valid),
        bool(preview_snaps_closed),
        round(float(reference_extent), 9),
    )
    return (geometries, line_widths, key)


def _has_manual_curve_preview(
    manual_curve_points: Sequence[Sequence[float]] | np.ndarray | None,
    *,
    preview_valid: bool = False,
) -> bool:
    return bool(len(_manual_curve_points_array(manual_curve_points)) > 0 or preview_valid)


def _manual_curve_points_array(
    manual_curve_points: Sequence[Sequence[float]] | np.ndarray | None,
) -> np.ndarray:
    if manual_curve_points is None:
        return np.zeros((0, 3), dtype=float)

    points = np.asarray(manual_curve_points, dtype=float)
    if points.size == 0:
        return np.zeros((0, 3), dtype=float)
    try:
        return points.reshape((-1, 3))
    except ValueError:
        return np.zeros((0, 3), dtype=float)


def _manual_curve_preview_point_array(
    preview_point: Sequence[float] | np.ndarray | None,
    *,
    preview_valid: bool,
) -> np.ndarray:
    if not bool(preview_valid) or preview_point is None:
        return np.zeros((0, 3), dtype=float)
    try:
        point = np.asarray(preview_point, dtype=float).reshape((1, 3))
    except (TypeError, ValueError):
        return np.zeros((0, 3), dtype=float)
    if not np.all(np.isfinite(point)):
        return np.zeros((0, 3), dtype=float)
    return point


def _manual_curve_control_point_actors(
    points: Sequence[Sequence[float]] | np.ndarray,
    *,
    reference_extent: float,
    snap_to_mesh: bool,
    selected_index: int | None,
    preview_point: Sequence[Sequence[float]] | np.ndarray,
    preview_valid: bool,
    preview_snaps_closed: bool,
) -> list[vtkActor]:
    point_array = _manual_curve_points_array(points)
    preview = _manual_curve_preview_point_array(
        preview_point,
        preview_valid=preview_valid,
    )
    if len(point_array) == 0 and len(preview) == 0:
        return []

    selected = _valid_manual_curve_selected_index(selected_index, point_count=len(point_array))
    normal_indices: list[int] = []
    first_indices: list[int] = []
    selected_indices: list[int] = []
    closure_indices: list[int] = []
    for index in range(len(point_array)):
        if bool(preview_snaps_closed) and index == 0:
            closure_indices.append(index)
        elif selected is not None and index == selected:
            selected_indices.append(index)
        elif index == 0:
            first_indices.append(index)
        else:
            normal_indices.append(index)

    actors: list[vtkActor] = []
    normal_color = MANUAL_CURVE_POINT_COLOR
    normal_radius = _manual_curve_control_point_radius(reference_extent)
    first_radius = _manual_curve_control_point_radius(reference_extent, prominent=True)
    selected_radius = _manual_curve_control_point_radius(reference_extent, selected=True)
    preview_radius = _manual_curve_control_point_radius(reference_extent, preview=True)
    for indices, color, radius in (
        (normal_indices, normal_color, normal_radius),
        (first_indices, MANUAL_CURVE_FIRST_POINT_COLOR, first_radius),
        (selected_indices, MANUAL_CURVE_SELECTED_POINT_COLOR, selected_radius),
        (closure_indices, MANUAL_CURVE_PREVIEW_POINT_COLOR, preview_radius),
    ):
        if indices:
            actors.append(
                _manual_curve_sphere_actor(
                    point_array[indices],
                    radius=radius,
                    color=color,
                )
            )
    if len(preview) == 1 and not bool(preview_snaps_closed):
        actors.append(
            _manual_curve_sphere_actor(
                preview,
                radius=preview_radius,
                color=MANUAL_CURVE_PREVIEW_POINT_COLOR,
            )
        )
    return actors


def _valid_manual_curve_selected_index(selected_index: int | None, *, point_count: int) -> int | None:
    if selected_index is None:
        return None
    try:
        index = int(selected_index)
    except (TypeError, ValueError):
        return None
    if 0 <= index < point_count:
        return index
    return None


def _manual_curve_control_point_radius(
    reference_extent: float,
    *,
    prominent: bool = False,
    selected: bool = False,
    preview: bool = False,
) -> float:
    try:
        extent = float(reference_extent)
    except (TypeError, ValueError):
        extent = 1.0
    if not np.isfinite(extent) or extent <= 0.0:
        extent = 1.0
    if selected:
        ratio = MANUAL_CURVE_SELECTED_POINT_RADIUS_RATIO
    elif preview:
        ratio = MANUAL_CURVE_PREVIEW_POINT_RADIUS_RATIO
    elif prominent:
        ratio = MANUAL_CURVE_FIRST_POINT_RADIUS_RATIO
    else:
        ratio = MANUAL_CURVE_CONTROL_POINT_RADIUS_RATIO
    return max(extent * ratio, MANUAL_CURVE_MIN_POINT_RADIUS)


def _manual_curve_sphere_actor(
    points: Sequence[Sequence[float]] | np.ndarray,
    *,
    radius: float,
    color: tuple[float, float, float],
) -> vtkActor:
    mapper = vtkPolyDataMapper()
    mapper.SetInputData(_manual_curve_sphere_polydata(points, radius=float(radius)))
    mapper.ScalarVisibilityOff()

    actor = vtkActor()
    actor.SetMapper(mapper)
    try:
        actor.PickableOff()
    except AttributeError:
        pass

    property_ = actor.GetProperty()
    property_.SetColor(*color)
    property_.SetAmbient(0.50)
    property_.SetDiffuse(0.58)
    property_.SetSpecular(0.25)
    property_.SetSpecularPower(18.0)
    property_.SetInterpolationToPhong()
    return actor


def _manual_curve_sphere_polydata(
    points: Sequence[Sequence[float]] | np.ndarray,
    *,
    radius: float,
) -> vtkPolyData:
    centers = _manual_curve_points_array(points)
    if len(centers) == 0:
        return _mesh_polydata(
            TriangleMeshData(
                vertices=np.zeros((0, 3), dtype=float),
                triangles=np.zeros((0, 3), dtype=int),
            )
        )

    unit_vertices, unit_faces = _unit_sphere_mesh()
    radius = max(float(radius), 1e-6)
    vertices: list[np.ndarray] = []
    faces: list[np.ndarray] = []
    for center in centers:
        offset = len(vertices) * len(unit_vertices)
        vertices.append((unit_vertices * radius) + center)
        faces.append(unit_faces + offset)

    return _mesh_polydata(
        TriangleMeshData(
            vertices=np.vstack(vertices),
            triangles=np.vstack(faces),
        )
    )


def _unit_sphere_mesh(
    *,
    latitude_steps: int = 8,
    longitude_steps: int = 16,
) -> tuple[np.ndarray, np.ndarray]:
    latitude_steps = max(int(latitude_steps), 3)
    longitude_steps = max(int(longitude_steps), 6)
    vertices: list[list[float]] = [[0.0, 0.0, 1.0]]
    for latitude_index in range(1, latitude_steps):
        phi = np.pi * float(latitude_index) / float(latitude_steps)
        z_value = float(np.cos(phi))
        radius = float(np.sin(phi))
        for longitude_index in range(longitude_steps):
            theta = 2.0 * np.pi * float(longitude_index) / float(longitude_steps)
            vertices.append(
                [
                    radius * float(np.cos(theta)),
                    radius * float(np.sin(theta)),
                    z_value,
                ]
            )
    bottom_index = len(vertices)
    vertices.append([0.0, 0.0, -1.0])

    faces: list[list[int]] = []
    first_ring = 1
    for longitude_index in range(longitude_steps):
        next_index = (longitude_index + 1) % longitude_steps
        faces.append([0, first_ring + longitude_index, first_ring + next_index])

    for ring_index in range(latitude_steps - 2):
        current_ring = 1 + (ring_index * longitude_steps)
        next_ring = current_ring + longitude_steps
        for longitude_index in range(longitude_steps):
            next_index = (longitude_index + 1) % longitude_steps
            current = current_ring + longitude_index
            current_next = current_ring + next_index
            lower = next_ring + longitude_index
            lower_next = next_ring + next_index
            faces.append([current, lower, current_next])
            faces.append([current_next, lower, lower_next])

    last_ring = 1 + ((latitude_steps - 2) * longitude_steps)
    for longitude_index in range(longitude_steps):
        next_index = (longitude_index + 1) % longitude_steps
        faces.append([bottom_index, last_ring + next_index, last_ring + longitude_index])

    return (
        np.asarray(vertices, dtype=float),
        np.asarray(faces, dtype=int),
    )


def _manual_curve_marker_basis(plane_normal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    normal = _normalized_vector(
        plane_normal,
        fallback=np.asarray([0.0, 0.0, 1.0], dtype=float),
    )
    reference = np.asarray([0.0, 0.0, 1.0], dtype=float)
    if abs(float(np.dot(normal, reference))) > 0.9:
        reference = np.asarray([0.0, 1.0, 0.0], dtype=float)
    u_axis = _normalized_vector(
        np.cross(normal, reference),
        fallback=np.asarray([1.0, 0.0, 0.0], dtype=float),
    )
    v_axis = _normalized_vector(
        np.cross(normal, u_axis),
        fallback=np.asarray([0.0, 1.0, 0.0], dtype=float),
    )
    return (u_axis, v_axis)


def _manual_curve_polyline_geometry(
    points: np.ndarray,
    *,
    closed: bool,
    color: tuple[float, float, float],
) -> LineGeometry:
    lines: list[tuple[int, int]] = []
    colors: list[list[float]] = []
    line_color = list(color)
    for index in range(len(points) - 1):
        lines.append((index, index + 1))
        colors.append(line_color)
    if closed and len(points) >= 3:
        lines.append((len(points) - 1, 0))
        colors.append(line_color)

    return LineGeometry(
        points=np.asarray(points, dtype=float),
        lines=np.asarray(lines, dtype=int),
        colors=np.asarray(colors, dtype=float),
    )


def _mesh_pick_normal(actor: vtkActor, triangle_index: int | None) -> np.ndarray | None:
    if triangle_index is None:
        return None

    mapper = actor.GetMapper()
    if mapper is None:
        return None
    polydata = mapper.GetInput()
    if polydata is None or triangle_index < 0 or triangle_index >= polydata.GetNumberOfCells():
        return None

    normal = _cell_data_normal(polydata, triangle_index)
    if normal is None:
        normal = _cell_geometry_normal(polydata, triangle_index)
    if normal is None:
        return None

    transform = actor.GetMatrix()
    transformed = np.asarray(
        [
            sum(float(transform.GetElement(row, column)) * float(normal[column]) for column in range(3))
            for row in range(3)
        ],
        dtype=float,
    )
    return _normalized_vector(transformed, fallback=normal)


def _cell_data_normal(polydata: vtkPolyData, triangle_index: int) -> np.ndarray | None:
    cell_data = polydata.GetCellData()
    if cell_data is None:
        return None
    normals = cell_data.GetNormals()
    if normals is None or triangle_index >= normals.GetNumberOfTuples():
        return None

    normal = np.asarray(normals.GetTuple(triangle_index), dtype=float).reshape(3)
    if not np.all(np.isfinite(normal)):
        return None
    return _normalized_vector(normal, fallback=np.asarray([0.0, 0.0, 1.0], dtype=float))


def _cell_geometry_normal(polydata: vtkPolyData, triangle_index: int) -> np.ndarray | None:
    cell = polydata.GetCell(int(triangle_index))
    if cell is None or cell.GetNumberOfPoints() < 3:
        return None

    points = cell.GetPoints()
    first = np.asarray(points.GetPoint(0), dtype=float)
    second = np.asarray(points.GetPoint(1), dtype=float)
    third = np.asarray(points.GetPoint(2), dtype=float)
    normal = np.cross(second - first, third - first)
    if not np.all(np.isfinite(normal)):
        return None
    length = float(np.linalg.norm(normal))
    if length <= 1e-12:
        return None
    return normal / length


def _line_actor(geometry: LineGeometry, *, line_width: float) -> vtkActor:
    actor = vtkActor()
    mapper = vtkPolyDataMapper()
    mapper.SetInputData(_line_polydata(geometry))
    actor.SetMapper(mapper)
    actor.GetProperty().SetLineWidth(float(line_width))
    return actor


def _tube_actor(geometry: LineGeometry, *, radius: float) -> vtkActor:
    tube = vtkTubeFilter()
    tube.SetInputData(_line_polydata(geometry))
    tube.SetRadius(float(radius))
    tube.SetNumberOfSides(10)
    tube.CappingOn()
    mapper = vtkPolyDataMapper()
    mapper.SetInputConnection(tube.GetOutputPort())
    actor = vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(1.0, 0.88, 0.05)
    return actor


def _mesh_actor(mesh: TriangleMeshData) -> vtkActor:
    normals = vtkPolyDataNormals()
    normals.SetInputData(_mesh_polydata(mesh))
    normals.ComputePointNormalsOn()
    normals.ComputeCellNormalsOn()
    normals.ConsistencyOn()
    normals.SplittingOff()
    normals.Update()

    mapper = vtkPolyDataMapper()
    mapper.SetInputData(normals.GetOutput())
    mapper.ScalarVisibilityOff()

    actor = vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(0.72, 0.74, 0.78)
    actor.GetProperty().SetRepresentationToSurface()
    actor.GetProperty().EdgeVisibilityOff()
    actor.GetProperty().SetPointSize(1.0)
    actor.GetProperty().SetAmbient(0.18)
    actor.GetProperty().SetDiffuse(0.82)
    actor.GetProperty().SetSpecular(0.12)
    actor.GetProperty().SetSpecularPower(18.0)
    actor.GetProperty().SetInterpolationToPhong()
    return actor


def _surface_preview_actor(
    preview: SurfacePreviewMesh,
    *,
    selected: bool,
) -> vtkActor:
    mapper = vtkPolyDataMapper()
    mapper.SetInputData(_surface_preview_polydata(preview))
    mapper.ScalarVisibilityOff()

    actor = vtkActor()
    actor.SetMapper(mapper)
    property_ = actor.GetProperty()
    opacity = _surface_preview_opacity(preview, selected=selected)
    if selected:
        property_.SetColor(0.0, 0.95, 1.0)
        property_.SetOpacity(opacity)
        property_.SetEdgeColor(0.85, 1.0, 1.0)
        property_.SetLineWidth(2.4)
    else:
        property_.SetColor(0.12, 0.34, 0.48)
        property_.SetOpacity(opacity)
        property_.SetEdgeColor(0.24, 0.58, 0.78)
        property_.SetLineWidth(1.1)
    property_.SetRepresentationToSurface()
    if bool(preview.wireframe_overlay) or selected:
        property_.EdgeVisibilityOn()
    else:
        property_.EdgeVisibilityOff()
    property_.SetAmbient(0.35)
    property_.SetDiffuse(0.65)
    property_.SetSpecular(0.05)
    property_.SetInterpolationToPhong()
    return actor


def _region_selection_actor(
    mesh: TriangleMeshData,
    region_selection: RegionSelection,
) -> vtkActor:
    mapper = vtkPolyDataMapper()
    mapper.SetInputData(_region_selection_polydata(mesh, region_selection.triangle_indices))
    mapper.ScalarVisibilityOff()

    actor = vtkActor()
    actor.SetMapper(mapper)
    property_ = actor.GetProperty()
    property_.SetColor(*REGION_SELECTION_COLOR)
    property_.SetOpacity(REGION_SELECTION_OPACITY)
    property_.SetEdgeColor(*REGION_SELECTION_EDGE_COLOR)
    property_.SetLineWidth(REGION_SELECTION_LINE_WIDTH)
    property_.SetRepresentationToSurface()
    property_.EdgeVisibilityOn()
    property_.SetAmbient(0.42)
    property_.SetDiffuse(0.58)
    property_.SetSpecular(0.05)
    return actor


def _region_selection_polydata(
    mesh: TriangleMeshData,
    triangle_indices: Sequence[int],
) -> vtkPolyData:
    triangles = np.asarray(mesh.triangles, dtype=int).reshape((-1, 3))
    selected_indices = np.asarray(
        [
            int(index)
            for index in triangle_indices
            if 0 <= int(index) < len(triangles)
        ],
        dtype=int,
    )
    if len(selected_indices) == 0:
        return _mesh_polydata(
            TriangleMeshData(
                vertices=np.zeros((0, 3), dtype=float),
                triangles=np.zeros((0, 3), dtype=int),
            )
        )

    selected_triangles = triangles[selected_indices]
    unique_vertex_indices, inverse = np.unique(selected_triangles.ravel(), return_inverse=True)
    compact_vertices = np.asarray(mesh.vertices, dtype=float).reshape((-1, 3))[unique_vertex_indices]
    compact_faces = inverse.reshape((-1, 3))
    return _mesh_polydata(
        TriangleMeshData(
            vertices=compact_vertices,
            triangles=compact_faces,
        )
    )


def _surface_preview_opacity(
    preview: SurfacePreviewMesh,
    *,
    selected: bool,
) -> float:
    default_opacity = 0.58 if selected else 0.22
    if preview.opacity is None:
        opacity = default_opacity
    else:
        try:
            opacity = float(preview.opacity)
        except (TypeError, ValueError):
            opacity = default_opacity
    if not np.isfinite(opacity):
        opacity = default_opacity
    opacity = min(max(opacity, 0.05), 1.0)
    if selected:
        opacity = max(opacity, 0.30)
    return opacity


def _array_key(values: Sequence[float] | np.ndarray | None) -> tuple[float, ...] | None:
    if values is None:
        return None

    return tuple(round(float(value), 9) for value in np.asarray(values, dtype=float).ravel())


def _region_selection_key(
    mesh: TriangleMeshData,
    region_selection: RegionSelection,
) -> tuple[object, ...]:
    return (
        "region_selection",
        id(mesh),
        region_selection.id,
        tuple(int(index) for index in region_selection.triangle_indices),
        bool(region_selection.visible),
        round(float(region_selection.threshold_degrees), 6),
    )


def _axis_gizmo_camera_key(
    forward: np.ndarray,
    view_up: np.ndarray,
) -> tuple[float, ...]:
    return (
        *tuple(round(float(value), 6) for value in np.asarray(forward, dtype=float).ravel()),
        *tuple(round(float(value), 6) for value in np.asarray(view_up, dtype=float).ravel()),
    )


def _axis_plane_origin(axis: str, offset: float) -> np.ndarray:
    return _axis_plane_normal(axis) * float(offset)


def _axis_plane_normal(axis: str) -> np.ndarray:
    normal = np.zeros(3, dtype=float)
    normal[{"X": 0, "Y": 1, "Z": 2}.get(axis.upper(), 2)] = 1.0
    return normal


def _named_view_vectors(name: str) -> tuple[np.ndarray, np.ndarray]:
    views = {
        "top": ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
        "bottom": ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
        "front": ((0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
        "back": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        "left": ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        "right": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        "isometric": ((1.0, -1.0, 0.75), (0.0, 0.0, 1.0)),
        "iso": ((1.0, -1.0, 0.75), (0.0, 0.0, 1.0)),
    }
    try:
        direction_values, view_up_values = views[name]
    except KeyError as exc:
        raise ValueError(f"Unknown named view: {name}") from exc

    direction = _normalized_vector(
        np.asarray(direction_values, dtype=float),
        fallback=np.asarray([1.0, -1.0, 0.75], dtype=float),
    )
    view_up = _normalized_vector(
        np.asarray(view_up_values, dtype=float),
        fallback=np.asarray([0.0, 0.0, 1.0], dtype=float),
    )
    return direction, view_up


def _normalized_vector(vector: np.ndarray, *, fallback: np.ndarray) -> np.ndarray:
    values = np.asarray(vector, dtype=float)
    length = float(np.linalg.norm(values))
    if length <= 1e-12:
        return np.asarray(fallback, dtype=float).copy()
    return values / length


def _active_axis_for_gizmo(mode: str | None, axis: str | None) -> str | None:
    if axis not in {"X", "Y", "Z"}:
        return None
    if mode == "rotate":
        return axis
    if mode == "move":
        return axis
    return None


def _vtk_matrix(matrix: np.ndarray) -> vtkMatrix4x4:
    vtk_matrix = vtkMatrix4x4()
    for row in range(4):
        for column in range(4):
            vtk_matrix.SetElement(row, column, float(matrix[row, column]))
    return vtk_matrix


def _transformed_bounds(
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


def _mesh_polydata(mesh: TriangleMeshData) -> vtkPolyData:
    polydata = vtkPolyData()
    points = numpy_to_vtk(np.asarray(mesh.vertices, dtype=float), deep=True)
    vtk_points = polydata.GetPoints()
    if vtk_points is None:
        from vtkmodules.vtkCommonCore import vtkPoints

        vtk_points = vtkPoints()
        polydata.SetPoints(vtk_points)
    vtk_points.SetData(points)

    triangles = np.asarray(mesh.triangles, dtype=np.int64)
    face_offsets = np.arange(0, (len(triangles) * 3) + 1, 3, dtype=np.int64)
    face_connectivity = triangles.ravel()
    cells = vtkCellArray()
    cells.SetData(
        numpy_to_vtkIdTypeArray(face_offsets, deep=True),
        numpy_to_vtkIdTypeArray(face_connectivity, deep=True),
    )
    polydata.SetPolys(cells)
    if mesh.has_vertex_normals():
        vertex_normals = numpy_to_vtk(np.asarray(mesh.vertex_normals, dtype=float), deep=True)
        vertex_normals.SetName("Normals")
        polydata.GetPointData().SetNormals(vertex_normals)
    if mesh.has_triangle_normals():
        triangle_normals = numpy_to_vtk(np.asarray(mesh.triangle_normals, dtype=float), deep=True)
        triangle_normals.SetName("Normals")
        polydata.GetCellData().SetNormals(triangle_normals)
    return polydata


def _surface_preview_polydata(preview: SurfacePreviewMesh) -> vtkPolyData:
    polydata = vtkPolyData()
    points = numpy_to_vtk(np.asarray(preview.vertices, dtype=float), deep=True)
    vtk_points = polydata.GetPoints()
    if vtk_points is None:
        from vtkmodules.vtkCommonCore import vtkPoints

        vtk_points = vtkPoints()
        polydata.SetPoints(vtk_points)
    vtk_points.SetData(points)

    faces = np.asarray(preview.faces, dtype=np.int64)
    face_offsets = np.arange(0, (len(faces) * 3) + 1, 3, dtype=np.int64)
    face_connectivity = faces.ravel()
    cells = vtkCellArray()
    cells.SetData(
        numpy_to_vtkIdTypeArray(face_offsets, deep=True),
        numpy_to_vtkIdTypeArray(face_connectivity, deep=True),
    )
    polydata.SetPolys(cells)
    return polydata


def _line_polydata(geometry: LineGeometry) -> vtkPolyData:
    polydata = vtkPolyData()
    from vtkmodules.vtkCommonCore import vtkPoints

    vtk_points = vtkPoints()
    vtk_points.SetData(numpy_to_vtk(np.asarray(geometry.points, dtype=float), deep=True))
    polydata.SetPoints(vtk_points)

    lines = np.asarray(geometry.lines, dtype=np.int64)
    line_offsets = np.arange(0, (len(lines) * 2) + 1, 2, dtype=np.int64)
    line_connectivity = lines.ravel()
    cells = vtkCellArray()
    cells.SetData(
        numpy_to_vtkIdTypeArray(line_offsets, deep=True),
        numpy_to_vtkIdTypeArray(line_connectivity, deep=True),
    )
    polydata.SetLines(cells)

    colors = np.clip(np.asarray(geometry.colors, dtype=float), 0.0, 1.0) * 255.0
    vtk_colors = numpy_to_vtk(colors.astype(np.uint8), deep=True, array_type=VTK_UNSIGNED_CHAR)
    vtk_colors.SetName("Colors")
    polydata.GetCellData().SetScalars(vtk_colors)
    return polydata


def _normal_lines(mesh: TriangleMeshData, *, normal_scale: float) -> LineGeometry:
    if mesh.vertex_normals is None or len(mesh.vertex_normals) != len(mesh.vertices):
        return LineGeometry(
            points=np.zeros((0, 3), dtype=float),
            lines=np.zeros((0, 2), dtype=int),
            colors=np.zeros((0, 3), dtype=float),
        )

    extent = max(float(mesh.get_axis_aligned_bounding_box().get_max_extent()), 1.0)
    starts = np.asarray(mesh.vertices, dtype=float)
    ends = starts + np.asarray(mesh.vertex_normals, dtype=float) * extent * normal_scale
    points = np.vstack((starts, ends))
    count = len(starts)
    lines = np.column_stack((np.arange(count), np.arange(count) + count))
    colors = np.tile(np.asarray([[0.1, 0.45, 1.0]], dtype=float), (count, 1))
    return LineGeometry(points=points, lines=lines, colors=colors)


def _polyline_geometry(
    polylines: Sequence[np.ndarray],
    *,
    color: Sequence[float],
) -> LineGeometry:
    points: list[list[float]] = []
    lines: list[tuple[int, int]] = []
    colors: list[list[float]] = []
    for polyline in polylines:
        point_array = np.asarray(polyline, dtype=float)
        if len(point_array) < 2:
            continue

        start_index = len(points)
        points.extend(point_array.tolist())
        for index in range(len(point_array) - 1):
            lines.append((start_index + index, start_index + index + 1))
            colors.append(list(color))

    if not points:
        return LineGeometry(
            points=np.zeros((0, 3), dtype=float),
            lines=np.zeros((0, 2), dtype=int),
            colors=np.zeros((0, 3), dtype=float),
        )

    return LineGeometry(
        points=np.asarray(points, dtype=float),
        lines=np.asarray(lines, dtype=int),
        colors=np.asarray(colors, dtype=float),
    )
