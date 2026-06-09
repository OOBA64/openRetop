"""Embed the classic Open3D visualizer inside a Tk frame on Windows."""

from __future__ import annotations

import ctypes
import time
from tkinter import Frame
from ctypes import wintypes
from typing import Sequence

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
        self.visualizer = o3d.visualization.Visualizer()
        self.window_title = f"openRetop Viewport {id(self)}"
        self._window_handle: int | None = None
        self._is_started = False
        self._is_closed = False
        self._geometry_names: list[str] = []
        self._view_center = np.asarray([0.0, 0.0, 0.0], dtype=float)
        self._view_extent = 2.0
        self._mesh_min_bound: np.ndarray | None = None
        self._mesh_max_bound: np.ndarray | None = None

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
        section_result: SectionResult | None = None,
        curve_results: Sequence[CurveFitResult] | None = None,
        reset_camera: bool = False,
    ) -> None:
        if not self._is_started:
            self.start()

        self.visualizer.clear_geometries()
        self._geometry_names.clear()
        self._update_view_metrics(mesh)
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
