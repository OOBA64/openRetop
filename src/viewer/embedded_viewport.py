"""Embed the classic Open3D visualizer inside a Tk frame on Windows."""

from __future__ import annotations

import ctypes
import time
from tkinter import Frame
from ctypes import wintypes
from typing import Callable, Sequence

import numpy as np
import open3d as o3d

from geometry.curves import CurveFitResult
from geometry.sections import SectionResult
from mesh.import_mesh import (
    build_normal_lines,
    build_polyline_lines,
    build_polyline_tubes,
)
from viewer.overlays import (
    build_bounding_box_outline,
    build_origin_marker,
    build_section_plane_preview,
    build_world_axes,
    build_xy_grid,
    reference_extent,
)


class EmbeddedOpen3DViewport:
    """Classic Open3D viewport hosted as a child of a Tk frame."""

    _GWL_STYLE = -16
    _SWP_NOZORDER = 0x0004
    _SWP_NOACTIVATE = 0x0010
    _SW_SHOW = 5
    _WS_CHILD = 0x40000000
    _WS_VISIBLE = 0x10000000
    _WS_BORDER = 0x00800000
    _WS_CAPTION = 0x00C00000
    _WS_THICKFRAME = 0x00040000

    def __init__(self, parent: Frame) -> None:
        self.parent = parent
        self.visualizer = o3d.visualization.VisualizerWithKeyCallback()
        self.window_title = f"openRetop Viewport {id(self)}"
        self._window_handle: int | None = None
        self._is_started = False
        self._is_closed = False
        self._geometry_names: list[str] = []
        self._view_center = np.asarray([0.0, 0.0, 0.0], dtype=float)
        self._view_extent = 2.0
        self._mesh_min_bound: np.ndarray | None = None
        self._mesh_max_bound: np.ndarray | None = None
        self._current_mesh: o3d.geometry.TriangleMesh | None = None
        self._current_show_section_plane = False
        self._current_section_axis = "Z"
        self._current_section_offset = 0.0
        self._last_mouse_position = (0.0, 0.0)
        self._selection_callback: Callable[[str | None], None] | None = None
        self._key_callback: Callable[[str], None] | None = None

        self.parent.bind("<Configure>", self._on_resize)

    def start(self) -> None:
        if self._is_started:
            return

        self.parent.update_idletasks()
        width = max(int(self.parent.winfo_width()), 320)
        height = max(int(self.parent.winfo_height()), 240)
        self.visualizer.create_window(
            window_name=self.window_title,
            width=width,
            height=height,
            left=80,
            top=80,
            visible=False,
        )
        self._is_started = True
        self._embed_window()
        self._register_input_callbacks()
        self._configure_render_options()
        self._pump_events()

    def close(self) -> None:
        self._is_closed = True
        if self._is_started:
            self.visualizer.destroy_window()

    def set_scene(
        self,
        mesh: o3d.geometry.TriangleMesh | None,
        *,
        show_grid: bool,
        show_axes: bool,
        show_normals: bool,
        show_section_plane: bool,
        section_axis: str,
        section_offset: float,
        selected_item: str | None = None,
        object_origin: Sequence[float] | None = None,
        section_result: SectionResult | None = None,
        curve_results: Sequence[CurveFitResult] | None = None,
        reset_camera: bool = False,
    ) -> None:
        if not self._is_started:
            self.start()

        self.visualizer.clear_geometries()
        self._geometry_names.clear()
        self._update_view_metrics(mesh)
        self._current_mesh = mesh
        self._current_show_section_plane = bool(show_section_plane)
        self._current_section_axis = section_axis
        self._current_section_offset = float(section_offset)
        reset_next_geometry = bool(reset_camera)

        def add_geometry(
            geometry: o3d.geometry.Geometry,
            *,
            may_reset_bounds: bool = False,
        ) -> None:
            nonlocal reset_next_geometry
            reset_bounds = bool(reset_next_geometry and may_reset_bounds)
            self.visualizer.add_geometry(
                geometry,
                reset_bounding_box=reset_bounds,
            )
            if reset_bounds:
                reset_next_geometry = False

        if mesh is not None:
            if not mesh.has_vertex_colors():
                mesh.paint_uniform_color([0.72, 0.74, 0.78])

            add_geometry(mesh, may_reset_bounds=True)
            if (
                selected_item == "model"
                and self._mesh_min_bound is not None
                and self._mesh_max_bound is not None
            ):
                add_geometry(
                    build_bounding_box_outline(self._mesh_min_bound, self._mesh_max_bound)
                )
                if object_origin is not None:
                    for geometry in build_origin_marker(object_origin, self._view_extent):
                        add_geometry(geometry)

        if show_grid:
            add_geometry(
                build_xy_grid(self._mesh_min_bound, self._mesh_max_bound),
                may_reset_bounds=(mesh is None),
            )

        if show_axes:
            for geometry in build_world_axes(
                reference_extent(self._mesh_min_bound, self._mesh_max_bound)
            ):
                add_geometry(geometry, may_reset_bounds=(mesh is None))

        if mesh is not None:
            if show_normals:
                normal_lines = build_normal_lines(mesh, normal_scale=0.012)
                if normal_lines is not None:
                    add_geometry(normal_lines)

            if (
                show_section_plane
                and self._mesh_min_bound is not None
                and self._mesh_max_bound is not None
            ):
                add_geometry(
                    build_section_plane_preview(
                        section_axis,
                        section_offset,
                        self._mesh_min_bound,
                        self._mesh_max_bound,
                        selected=(selected_item == "section_plane"),
                    )
                )

        if section_result is not None:
            mesh_extent = self._view_extent
            for tube in build_polyline_tubes(
                section_result.polylines,
                color=[1.0, 0.88, 0.05],
                radius=mesh_extent * 0.003,
            ):
                add_geometry(tube)

        if curve_results:
            fitted_lines = build_polyline_lines(
                [result.fitted_points for result in curve_results],
                color=[0.1, 0.78, 0.28],
            )
            if fitted_lines is not None:
                add_geometry(fitted_lines)

        if reset_camera:
            self.reset_view()

        self.visualizer.update_renderer()

    def frame_model(self) -> None:
        if not self._is_started:
            return

        self._apply_cad_view(zoom=0.72)
        self.visualizer.update_renderer()

    def reset_view(self) -> None:
        if not self._is_started:
            return

        self._apply_cad_view(zoom=0.68)
        self.visualizer.update_renderer()

    def reset_camera(self) -> None:
        self.reset_view()

    def set_selection_callback(
        self,
        callback: Callable[[str | None], None] | None,
    ) -> None:
        self._selection_callback = callback

    def set_key_callback(self, callback: Callable[[str], None] | None) -> None:
        self._key_callback = callback

    def _pump_events(self) -> None:
        if self._is_closed:
            return

        if self._is_started:
            self.visualizer.poll_events()
            self.visualizer.update_renderer()

        self.parent.after(16, self._pump_events)

    def _configure_render_options(self) -> None:
        render_options = self.visualizer.get_render_option()
        render_options.mesh_show_back_face = True
        render_options.background_color = [0.08, 0.09, 0.1]
        render_options.line_width = 2.0

    def _register_input_callbacks(self) -> None:
        self.visualizer.register_mouse_move_callback(self._on_mouse_move)
        self.visualizer.register_mouse_button_callback(self._on_mouse_button)
        for key in ("G", "R", "X", "Y", "Z", "F"):
            self.visualizer.register_key_action_callback(
                ord(key),
                lambda _vis, action, _mods, key=key: self._on_key_action(key, action),
            )

        for key_code, key_name in ((256, "Escape"), (257, "Enter"), (261, "Delete")):
            self.visualizer.register_key_action_callback(
                key_code,
                lambda _vis, action, _mods, key=key_name: self._on_key_action(
                    key,
                    action,
                ),
            )

    def _on_mouse_move(
        self,
        _visualizer: o3d.visualization.Visualizer,
        x_position: float,
        y_position: float,
    ) -> bool:
        self._last_mouse_position = (float(x_position), float(y_position))
        return False

    def _on_mouse_button(
        self,
        _visualizer: o3d.visualization.Visualizer,
        button: int,
        action: int,
        _mods: int,
    ) -> bool:
        if button == 0 and action == 1 and self._selection_callback is not None:
            target = self._pick_target(*self._last_mouse_position)
            self.parent.after(0, lambda: self._selection_callback(target))

        return False

    def _on_key_action(self, key: str, action: int) -> bool:
        if action == 1 and self._key_callback is not None:
            self.parent.after(0, lambda: self._key_callback(key))

        return False

    def _update_view_metrics(self, mesh: o3d.geometry.TriangleMesh | None) -> None:
        if mesh is None:
            self._mesh_min_bound = None
            self._mesh_max_bound = None
            self._view_center = np.asarray([0.0, 0.0, 0.0], dtype=float)
            self._view_extent = 2.0
            return

        bounding_box = mesh.get_axis_aligned_bounding_box()
        self._mesh_min_bound = np.asarray(bounding_box.get_min_bound(), dtype=float)
        self._mesh_max_bound = np.asarray(bounding_box.get_max_bound(), dtype=float)
        self._view_center = np.asarray(bounding_box.get_center(), dtype=float)
        self._view_extent = max(float(bounding_box.get_max_extent()), 1.0)

    def _apply_cad_view(self, *, zoom: float) -> None:
        view_control = self.visualizer.get_view_control()
        front = np.asarray([0.65, -0.65, 0.38], dtype=float)
        front /= np.linalg.norm(front)
        view_control.set_front(front.tolist())
        view_control.set_up([0.0, 0.0, 1.0])
        view_control.set_lookat(self._view_center.tolist())
        view_control.set_zoom(float(zoom))

    def _pick_target(self, x_position: float, y_position: float) -> str | None:
        if self._current_mesh is None:
            return None

        click = np.asarray([float(x_position), float(y_position)], dtype=float)
        if (
            self._current_show_section_plane
            and self._mesh_min_bound is not None
            and self._mesh_max_bound is not None
        ):
            plane = build_section_plane_preview(
                self._current_section_axis,
                self._current_section_offset,
                self._mesh_min_bound,
                self._mesh_max_bound,
            )
            plane_points = self._project_points(np.asarray(plane.points, dtype=float))
            if plane_points is not None:
                distance = _minimum_line_distance(
                    click,
                    plane_points,
                    np.asarray(plane.lines, dtype=int),
                )
                if distance <= 14.0:
                    return "section_plane"

        if self._mesh_min_bound is None or self._mesh_max_bound is None:
            return None

        corners = _bbox_corners(self._mesh_min_bound, self._mesh_max_bound)
        projected_corners = self._project_points(corners)
        if projected_corners is None:
            return "model"

        minimum = np.min(projected_corners, axis=0) - 8.0
        maximum = np.max(projected_corners, axis=0) + 8.0
        if bool(np.all(click >= minimum) and np.all(click <= maximum)):
            return "model"

        return None

    def _project_points(self, points: np.ndarray) -> np.ndarray | None:
        try:
            params = self.visualizer.get_view_control().convert_to_pinhole_camera_parameters()
        except RuntimeError:
            return None

        if points.size == 0:
            return None

        intrinsic = np.asarray(params.intrinsic.intrinsic_matrix, dtype=float)
        extrinsic = np.asarray(params.extrinsic, dtype=float)
        homogeneous = np.column_stack((points, np.ones(len(points))))
        camera_points = (extrinsic @ homogeneous.T).T[:, :3]
        width = float(params.intrinsic.width)
        height = float(params.intrinsic.height)
        best_projection: np.ndarray | None = None
        best_score = -1

        for z_sign in (1.0, -1.0):
            z_values = camera_points[:, 2] * z_sign
            valid = np.abs(z_values) > 1e-9
            if not np.any(valid):
                continue

            projected = np.empty((len(points), 2), dtype=float)
            projected[:, 0] = intrinsic[0, 0] * camera_points[:, 0] / z_values + intrinsic[0, 2]
            projected[:, 1] = intrinsic[1, 1] * camera_points[:, 1] / z_values + intrinsic[1, 2]
            score = int(
                np.count_nonzero(
                    valid
                    & (projected[:, 0] >= -width)
                    & (projected[:, 0] <= width * 2.0)
                    & (projected[:, 1] >= -height)
                    & (projected[:, 1] <= height * 2.0)
                )
            )
            if score > best_score:
                best_score = score
                best_projection = projected

        return best_projection

    def _embed_window(self) -> None:
        handle = _find_window_by_title(self.window_title, timeout_seconds=5.0)
        if handle is None:
            raise RuntimeError("Could not find the Open3D viewport window to embed.")

        self._window_handle = handle
        parent_handle = int(self.parent.winfo_id())
        user32 = _user32()
        user32.SetParent(handle, parent_handle)

        style = user32.GetWindowLongW(handle, self._GWL_STYLE)
        style |= self._WS_CHILD | self._WS_VISIBLE
        style &= ~(self._WS_CAPTION | self._WS_THICKFRAME | self._WS_BORDER)
        user32.SetWindowLongW(handle, self._GWL_STYLE, style)
        self._resize_child_window()
        user32.ShowWindow(handle, self._SW_SHOW)

    def _on_resize(self, _event: object) -> None:
        self._resize_child_window()

    def _resize_child_window(self) -> None:
        if self._window_handle is None:
            return

        width = max(int(self.parent.winfo_width()), 1)
        height = max(int(self.parent.winfo_height()), 1)
        _user32().SetWindowPos(
            self._window_handle,
            0,
            0,
            0,
            width,
            height,
            self._SWP_NOZORDER | self._SWP_NOACTIVATE,
        )


def _find_window_by_title(
    title: str,
    *,
    timeout_seconds: float,
) -> int | None:
    user32 = _user32()
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        handle = user32.FindWindowW(None, title)
        if handle:
            return int(handle)

        time.sleep(0.05)

    return None


def _bbox_corners(min_bound: np.ndarray, max_bound: np.ndarray) -> np.ndarray:
    return np.asarray(
        [
            [min_bound[0], min_bound[1], min_bound[2]],
            [max_bound[0], min_bound[1], min_bound[2]],
            [min_bound[0], max_bound[1], min_bound[2]],
            [max_bound[0], max_bound[1], min_bound[2]],
            [min_bound[0], min_bound[1], max_bound[2]],
            [max_bound[0], min_bound[1], max_bound[2]],
            [min_bound[0], max_bound[1], max_bound[2]],
            [max_bound[0], max_bound[1], max_bound[2]],
        ],
        dtype=float,
    )


def _minimum_line_distance(
    point: np.ndarray,
    projected_points: np.ndarray,
    lines: np.ndarray,
) -> float:
    if len(projected_points) == 0 or len(lines) == 0:
        return float("inf")

    best_distance = float("inf")
    for start_index, end_index in lines:
        start = projected_points[int(start_index)]
        end = projected_points[int(end_index)]
        segment = end - start
        length_squared = float(np.dot(segment, segment))
        if length_squared <= 1e-12:
            distance = float(np.linalg.norm(point - start))
        else:
            amount = float(np.clip(np.dot(point - start, segment) / length_squared, 0.0, 1.0))
            closest = start + segment * amount
            distance = float(np.linalg.norm(point - closest))

        best_distance = min(best_distance, distance)

    return best_distance


def _user32() -> ctypes.WinDLL:
    user32 = ctypes.windll.user32
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
    user32.SetParent.restype = wintypes.HWND
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    user32.SetWindowLongW.restype = ctypes.c_long
    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    return user32
