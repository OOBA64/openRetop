"""Embed a VTK viewport inside a Tk frame."""

from __future__ import annotations

from tkinter import Canvas, Event, TclError
from typing import Callable, Sequence

import numpy as np

from geometry.curves import CurveFitResult
from geometry.sections import SectionResult
from mesh.triangle_mesh import TriangleMeshData
from viewer.overlays import (
    LineGeometry,
    build_active_axis_indicator,
    build_bounding_box_outline,
    build_origin_marker,
    build_rotation_ring,
    build_section_plane_preview,
    build_world_axes,
    build_xy_grid,
    reference_extent,
)

try:
    from vtkmodules.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray
    from vtkmodules.vtkCommonCore import VTK_UNSIGNED_CHAR
    from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
    from vtkmodules.vtkCommonMath import vtkMatrix4x4
    from vtkmodules.vtkFiltersCore import vtkPolyDataNormals, vtkTubeFilter
    from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera
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
        self._mesh_bounds_mesh_id: int | None = None
        self._mesh_local_min_bound: np.ndarray | None = None
        self._mesh_local_max_bound: np.ndarray | None = None
        self._interactive_transform_key: tuple[int, str, str | None, str | None] | None = None
        self._section_plane_actors: list[vtkActor] = []
        self._section_plane_pick_geometry: LineGeometry | None = None
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
        selected_item: str | None = None,
        object_origin: Sequence[float] | None = None,
        scene_bounds_min: Sequence[float] | None = None,
        scene_bounds_max: Sequence[float] | None = None,
        active_transform_mode: str | None = None,
        active_transform_axis: str | None = None,
        section_result: SectionResult | None = None,
        curve_results: Sequence[CurveFitResult] | None = None,
        reset_camera: bool = False,
    ) -> None:
        if not self._is_started:
            self.start()

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
        if self._try_update_interactive_mesh_transform(
            mesh,
            matrix,
            transform_key=transform_key,
            reset_camera=reset_camera,
            show_normals=show_normals,
            section_result=section_result,
            curve_results=curve_results,
        ):
            return

        self.renderer.RemoveAllViewProps()
        self._section_plane_actors = []
        self._section_plane_pick_geometry = None
        if mesh is None:
            self._mesh_actor = None
            self._mesh_actor_mesh_id = None
        self._update_view_metrics(mesh, matrix, scene_bounds_min, scene_bounds_max)

        if mesh is not None:
            self._mesh_actor = self._ensure_mesh_actor(mesh)
            self._mesh_actor.SetUserMatrix(_vtk_matrix(matrix))
            self.renderer.AddActor(self._mesh_actor)
            if (
                selected_item == "model"
                and self._mesh_min_bound is not None
                and self._mesh_max_bound is not None
            ):
                self._add_line_actor(
                    build_bounding_box_outline(self._mesh_min_bound, self._mesh_max_bound),
                    line_width=1.6,
                )
                if object_origin is not None:
                    self._add_line_actor(
                        build_origin_marker(object_origin, self._view_extent),
                        line_width=2.2,
                    )
                    active_axis = _active_axis_for_gizmo(
                        active_transform_mode,
                        active_transform_axis,
                    )
                    if active_axis is not None:
                        self._add_line_actor(
                            build_active_axis_indicator(
                                object_origin,
                                active_axis,
                                self._view_extent,
                            ),
                            line_width=2.8,
                        )
                    if active_transform_mode == "rotate":
                        self._add_line_actor(
                            build_rotation_ring(
                                object_origin,
                                active_axis or "Z",
                                self._view_extent,
                            ),
                            line_width=2.4,
                        )

        if show_grid:
            self._add_line_actor(
                build_xy_grid(self._mesh_min_bound, self._mesh_max_bound),
                line_width=1.0,
            )

        if show_axes:
            self._add_line_actor(
                build_world_axes(reference_extent(self._mesh_min_bound, self._mesh_max_bound)),
                line_width=3.0,
            )

        if mesh is not None and show_normals and mesh.has_vertex_normals():
            normal_actor = self._add_line_actor(
                _normal_lines(mesh, normal_scale=0.012),
                line_width=1.0,
            )
            normal_actor.SetUserMatrix(_vtk_matrix(matrix))

        if (
            mesh is not None
            and show_section_plane
            and self._mesh_min_bound is not None
            and self._mesh_max_bound is not None
        ):
            section_geometry = build_section_plane_preview(
                section_axis,
                section_offset,
                self._mesh_min_bound,
                self._mesh_max_bound,
                selected=(selected_item == "section_plane"),
            )
            self._section_plane_pick_geometry = section_geometry
            section_actor = self._add_line_actor(
                section_geometry,
                line_width=3.0 if selected_item == "section_plane" else 2.0,
            )
            self._section_plane_actors.append(section_actor)

        if section_result is not None:
            section_lines = _polyline_geometry(
                [polyline.points for polyline in section_result.polylines],
                color=(1.0, 0.88, 0.05),
            )
            self._add_tube_actor(section_lines, radius=max(self._view_extent * 0.002, 0.002))

        if curve_results:
            fitted_lines = _polyline_geometry(
                [result.fitted_points for result in curve_results],
                color=(0.1, 0.78, 0.28),
            )
            self._add_line_actor(fitted_lines, line_width=2.5)

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
        show_normals: bool,
        section_result: SectionResult | None,
        curve_results: Sequence[CurveFitResult] | None,
    ) -> bool:
        if (
            transform_key is None
            or transform_key != self._interactive_transform_key
            or reset_camera
            or show_normals
            or section_result is not None
            or curve_results
            or mesh is None
            or self._mesh_actor is None
            or self._mesh_actor_mesh_id != id(mesh)
        ):
            return False

        self._mesh_actor.SetUserMatrix(_vtk_matrix(matrix))
        self._render()
        return True

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
        actor = vtkActor()
        mapper = vtkPolyDataMapper()
        mapper.SetInputData(_line_polydata(geometry))
        actor.SetMapper(mapper)
        actor.GetProperty().SetLineWidth(float(line_width))
        self.renderer.AddActor(actor)
        return actor

    def _add_tube_actor(self, geometry: LineGeometry, *, radius: float) -> vtkActor:
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
            self._mesh_min_bound = None
            self._mesh_max_bound = None
            self._mesh_local_min_bound = None
            self._mesh_local_max_bound = None
            self._mesh_bounds_mesh_id = None
            self._view_center = np.asarray([0.0, 0.0, 0.0], dtype=float)
            self._view_extent = 2.0
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
        if _screen_point_near_geometry(
            self.renderer,
            self._section_plane_pick_geometry,
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
