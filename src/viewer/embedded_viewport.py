"""Embed a VTK viewport inside a Tk frame."""

from __future__ import annotations

from dataclasses import dataclass
from tkinter import Canvas, Event, TclError
from typing import Callable, Sequence

import numpy as np

from geometry.curves import CurveFitResult
from geometry.sections import SectionResult
from mesh.triangle_mesh import TriangleMeshData
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
    "delete",
    "escape",
    "f",
    "g",
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
SELECTED_CURVE_COLOR = (0.0, 0.95, 1.0)
SELECTED_CURVE_LINE_WIDTH = 4.6


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


class EmbeddedVTKViewport:
    """VTK viewport hosted inside a Tk frame."""

    def __init__(self, parent: object) -> None:
        self.parent = parent
        self.renderer = vtkRenderer()
        self.renderer.SetBackground(0.08, 0.09, 0.1)
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
        self._selection_callback: Callable[[str | None], None] | None = None
        self._pointer_callback: Callable[[str, int, int, bool, bool], bool] | None = None
        self._left_press_position: tuple[int, int] | None = None
        self._last_mouse_position = (0, 0)

    def start(self) -> None:
        if self._is_started:
            return

        self.widget = Canvas(
            self.parent,
            background="#14171a",
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

    def close(self) -> None:
        self._is_closed = True
        if self.render_window is not None and self._axis_gizmo_renderer is not None:
            self.render_window.RemoveRenderer(self._axis_gizmo_renderer)
        self._axis_gizmo_renderer = None
        self._axis_gizmo_actor = None
        self._axis_gizmo_camera_key = None
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
        surface_previews: Sequence[SurfacePreviewMesh] | None = None,
        active_surface_id: str | None = None,
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
            surface_previews=surface_previews,
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
        self._update_curve_result_actor(curve_results)

        if reset_camera:
            self.reset_view()

        self._render()
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
        show_axis_gizmo: bool = True,
        surface_previews: Sequence[SurfacePreviewMesh] | None = None,
    ) -> bool:
        if (
            transform_key is None
            or transform_key != self._interactive_transform_key
            or reset_camera
            or show_normals
            or section_result is not None
            or curve_results
            or surface_previews
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
        self._render()
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
            selection_actors = [
                _line_actor(
                    build_bounding_box_outline(self._mesh_min_bound, self._mesh_max_bound),
                    line_width=SELECTION_BOUNDING_BOX_LINE_WIDTH,
                )
            ]
            if object_origin is not None:
                selection_actors.append(
                    _line_actor(
                        build_origin_marker(object_origin, self._view_extent),
                        line_width=2.2,
                    )
                )
            self._replace_overlay_group(
                "selection_overlays",
                selection_actors,
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

        gizmo_actors: list[vtkActor] = []
        if active_axis is not None:
            gizmo_actors.append(
                _line_actor(
                    build_active_axis_indicator(
                        object_origin,
                        active_axis,
                        self._view_extent,
                    ),
                    line_width=2.8,
                )
            )
        if active_transform_mode == "rotate":
            rotation_bounds = self._rotation_overlay_bounds(mesh)
            assert rotation_bounds is not None
            ring_min_bound, ring_max_bound = rotation_bounds
            ring_radius = rotation_ring_radius_for_axis(
                ring_min_bound,
                ring_max_bound,
                active_axis or "Z",
            )
            gizmo_actors.append(
                _line_actor(
                    build_rotation_ring(
                        object_origin,
                        active_axis or "Z",
                        self._view_extent,
                        radius=ring_radius,
                    ),
                    line_width=2.4,
                )
            )
            if active_transform_angle_delta is not None:
                angle_indicator = build_rotation_angle_indicator(
                    object_origin,
                    active_axis or "Z",
                    ring_radius,
                    active_transform_angle_delta,
                )
                if len(angle_indicator.lines) > 0:
                    gizmo_actors.append(
                        _line_actor(
                            angle_indicator,
                            line_width=2.0,
                        )
                    )
        self._replace_overlay_group(
            "active_transform_gizmo",
            gizmo_actors,
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
        self._axis_gizmo_actor.SetTotalLength(0.85, 0.85, 0.85)
        self._axis_gizmo_actor.SetShaftTypeToCylinder()
        self._axis_gizmo_actor.SetCylinderRadius(0.045)
        self._axis_gizmo_actor.SetConeRadius(0.16)
        self._axis_gizmo_actor.SetSphereRadius(0.08)

        self._axis_gizmo_renderer = vtkRenderer()
        self._axis_gizmo_renderer.SetLayer(1)
        self._axis_gizmo_renderer.SetViewport(0.82, 0.78, 0.98, 0.98)
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
        self._axis_gizmo_visible = bool(visible)
        if self._axis_gizmo_actor is not None:
            self._axis_gizmo_actor.SetVisibility(1 if visible else 0)
        if self._axis_gizmo_renderer is not None:
            try:
                self._axis_gizmo_renderer.SetDraw(1 if visible else 0)
            except AttributeError:
                pass
        if not visible:
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

        section_actors: list[vtkActor] = []
        section_geometries: list[LineGeometry] = []
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
            section_actors.append(
                _line_actor(
                    section_geometry,
                    line_width=3.0 if plane.selected else 2.0,
                )
            )

        self._section_plane_actors = section_actors
        self._section_plane_pick_geometries = section_geometries
        self._section_plane_pick_geometry = section_geometries[0]
        self._remove_actor("section_plane")
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

        gizmo_actors: list[vtkActor] = []
        if active_axis is not None:
            gizmo_actors.append(
                _line_actor(
                    build_active_axis_indicator(
                        origin,
                        active_axis,
                        self._view_extent,
                    ),
                    line_width=2.8,
                )
            )
        if active_transform_mode == "rotate":
            axis = active_axis or "Z"
            ring_radius = rotation_ring_radius_for_axis(
                self._mesh_min_bound if self._mesh_min_bound is not None else origin - 1.0,
                self._mesh_max_bound if self._mesh_max_bound is not None else origin + 1.0,
                axis,
            )
            gizmo_actors.append(
                _line_actor(
                    build_rotation_ring(
                        origin,
                        axis,
                        self._view_extent,
                        radius=ring_radius,
                    ),
                    line_width=2.4,
                )
            )
            if active_transform_angle_delta is not None:
                angle_indicator = build_rotation_angle_indicator(
                    origin,
                    axis,
                    ring_radius,
                    active_transform_angle_delta,
                )
                if len(angle_indicator.lines) > 0:
                    gizmo_actors.append(
                        _line_actor(
                            angle_indicator,
                            line_width=2.0,
                        )
                    )

        self._replace_overlay_group(
            "active_transform_gizmo",
            gizmo_actors,
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
    ) -> None:
        if not curve_results:
            self._remove_actor("curve_result")
            self._clear_overlay_group("selected_curve_result")
            return

        unselected_results = [
            result for result in curve_results if not getattr(result, "selected", False)
        ]
        selected_results = [
            result for result in curve_results if getattr(result, "selected", False)
        ]
        key = (
            "curve_result",
            tuple(id(result) for result in curve_results),
            tuple(len(result.fitted_points) for result in curve_results),
            tuple(bool(getattr(result, "selected", False)) for result in curve_results),
        )
        selected_key = (
            "selected_curve_result",
            tuple(id(result) for result in selected_results),
            tuple(len(result.fitted_points) for result in selected_results),
        )
        unselected_actor_matches = (
            (
                bool(unselected_results)
                and self._actor_keys.get("curve_result") == key
                and "curve_result" in self._actors_by_role
            )
            or (
                not unselected_results
                and self._actor_keys.get("curve_result") == key
                and "curve_result" not in self._actors_by_role
            )
        )
        selected_actor_matches = (
            (
                bool(selected_results)
                and self._group_keys.get("selected_curve_result") == selected_key
                and "selected_curve_result" in self._actor_groups
            )
            or (
                not selected_results
                and "selected_curve_result" not in self._actor_groups
            )
        )
        if (
            unselected_actor_matches
            and selected_actor_matches
        ):
            return

        if unselected_results:
            fitted_lines = _polyline_geometry(
                [result.fitted_points for result in unselected_results],
                color=UNSELECTED_CURVE_COLOR,
            )
            self._replace_actor(
                "curve_result",
                _line_actor(fitted_lines, line_width=UNSELECTED_CURVE_LINE_WIDTH),
                key=key,
            )
        else:
            self._remove_actor("curve_result")
            self._actor_keys["curve_result"] = key

        if selected_results:
            selected_lines = _polyline_geometry(
                [result.fitted_points for result in selected_results],
                color=SELECTED_CURVE_COLOR,
            )
            self._replace_overlay_group(
                "selected_curve_result",
                [_line_actor(selected_lines, line_width=SELECTED_CURVE_LINE_WIDTH)],
                key=selected_key,
            )
        else:
            self._clear_overlay_group("selected_curve_result")

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
        for actor in actor_list:
            self.renderer.AddActor(actor)

    def _clear_overlay_group(self, group_name: str) -> None:
        actors = self._actor_groups.pop(group_name, [])
        self._group_keys.pop(group_name, None)
        for actor in actors:
            self.renderer.RemoveActor(actor)

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
        self.widget.bind("<MouseWheel>", self._on_mouse_wheel)
        self.widget.bind("<KeyPress>", self._on_key_press)

    def _on_configure(self, _event: Event[Canvas]) -> None:
        self._resize_render_window()
        self._render()

    def _resize_render_window(self) -> None:
        if self.widget is None or self.render_window is None:
            return

        width = max(int(self.widget.winfo_width()), 1)
        height = max(int(self.widget.winfo_height()), 1)
        self.render_window.SetSize(width, height)

    def _on_left_button_press(self, event: Event[Canvas]) -> None:
        self._left_press_position = (int(event.x), int(event.y))
        if self._dispatch_pointer_event("left_press", event):
            return

        self._forward_mouse_event(event, "LeftButtonPressEvent")

    def _on_left_button_release(self, event: Event[Canvas]) -> None:
        if self._dispatch_pointer_event("left_release", event):
            self._left_press_position = None
            return

        self._forward_mouse_event(event, "LeftButtonReleaseEvent")
        if self._selection_callback is None:
            return

        if not self._is_click_release(event):
            return

        target = self._pick_target(int(event.x), int(event.y))
        self._selection_callback(target)

    def _on_middle_button_press(self, event: Event[Canvas]) -> None:
        if self._dispatch_pointer_event("middle_press", event):
            return

        self._forward_mouse_event(event, "MiddleButtonPressEvent")

    def _on_middle_button_release(self, event: Event[Canvas]) -> None:
        if self._dispatch_pointer_event("middle_release", event):
            return

        self._forward_mouse_event(event, "MiddleButtonReleaseEvent")

    def _on_right_button_press(self, event: Event[Canvas]) -> None:
        if self._dispatch_pointer_event("right_press", event):
            return

        self._forward_mouse_event(event, "RightButtonPressEvent")

    def _on_right_button_release(self, event: Event[Canvas]) -> None:
        if self._dispatch_pointer_event("right_release", event):
            return

        self._forward_mouse_event(event, "RightButtonReleaseEvent")

    def _on_mouse_move(self, event: Event[Canvas]) -> None:
        if self._dispatch_pointer_event("motion", event):
            return

        self._forward_mouse_event(event, "MouseMoveEvent")

    def _on_mouse_wheel(self, event: Event[Canvas]) -> None:
        if self.interactor is None:
            return

        self._set_interactor_event(event)
        if int(event.delta) > 0:
            self.interactor.MouseWheelForwardEvent()
        else:
            self.interactor.MouseWheelBackwardEvent()
        self._render()

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
        self._render()

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

        x_position = int(getattr(event, "x", self._last_mouse_position[0]))
        y_position = int(getattr(event, "y", self._last_mouse_position[1]))
        self._last_mouse_position = (x_position, y_position)
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
        if self.render_window is not None and not self._is_closed:
            try:
                self._sync_axis_gizmo_camera()
                self.render_window.Render()
            except TclError:
                return


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
    if selected:
        property_.SetColor(0.08, 0.9, 0.95)
        property_.SetOpacity(0.48)
        property_.SetEdgeColor(0.85, 1.0, 1.0)
        property_.SetLineWidth(1.8)
    else:
        property_.SetColor(0.16, 0.56, 0.9)
        property_.SetOpacity(0.28)
        property_.SetEdgeColor(0.36, 0.78, 1.0)
        property_.SetLineWidth(1.1)
    property_.SetRepresentationToSurface()
    property_.EdgeVisibilityOn()
    property_.SetAmbient(0.35)
    property_.SetDiffuse(0.65)
    property_.SetSpecular(0.05)
    property_.SetInterpolationToPhong()
    return actor


def _array_key(values: Sequence[float] | np.ndarray | None) -> tuple[float, ...] | None:
    if values is None:
        return None

    return tuple(round(float(value), 9) for value in np.asarray(values, dtype=float).ravel())


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


def _normalized_vector(vector: np.ndarray, *, fallback: np.ndarray) -> np.ndarray:
    values = np.asarray(vector, dtype=float)
    length = float(np.linalg.norm(values))
    if length <= 1e-12:
        return np.asarray(fallback, dtype=float).copy()
    return values / length


def _active_axis_for_gizmo(mode: str | None, axis: str | None) -> str | None:
    if mode == "rotate":
        return axis or "Z"
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
