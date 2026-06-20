from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from tkinter import TclError, Tk
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.main_window import (
    COMPUTE_SECTION_PROGRESS_STAGES,
    GENERATED_GEOMETRY_TRANSFORM_WARNING,
    LOAD_PROGRESS_STAGES,
    SURFACE_PREVIEW_PROGRESS_STAGES,
    LoadProgressDialog,
    OPEN_MODEL_MENU_INDEX,
    OpenRetopWindow,
)
from cad_kernel.types import CadBuildResult, StepExportResult
from app.scene_browser import (
    NODE_BREP_SURFACES,
    NODE_CURVES,
    NODE_CURVE_GROUP_MANUAL,
    NODE_CURVE_GROUP_PROJECTED,
    NODE_CURVE_GROUP_REGION_BOUNDARIES,
    NODE_CURVE_GROUP_REBUILT,
    NODE_CURVE_GROUP_UNASSIGNED,
    NODE_CURVE_GROUP_REPAIRED,
    NODE_EMPTY_SCENE,
    NODE_MESH,
    NODE_REGIONS,
    NODE_SCENE,
    NODE_SECTION_PLANES,
    NODE_SECTION_RESULTS,
    NODE_SURFACES,
    curve_group_node_id,
    curve_id_from_node,
    curve_node_id,
    region_node_id,
    section_result_id_from_node,
    section_plane_node_id,
    section_result_node_id,
    surface_id_from_node,
    surface_node_id,
)
from curves.curve_state import StoredCurve, add_curve
from curves.manual_curve import (
    DEFAULT_MANUAL_CURVE_METHOD,
    DEFAULT_MANUAL_CURVE_SAMPLE_COUNT,
)
from mesh.loader import LoadedMesh, MeshMetadata
from mesh.triangle_mesh import TriangleMeshData
from project.project_data import (
    ProjectCurve,
    ProjectSectionPlane,
    ProjectSurface,
    default_project_data,
)
from project.project_io import load_project, save_project
from regions.region_state import RegionSelection
from settings.settings_data import default_app_settings
from settings.settings_io import load_settings, save_settings
from sections.section_state import (
    SectionPlaneState,
    StoredSectionResult,
    add_plane,
    plane_normal,
    plane_origin,
    set_active_plane,
    set_plane_origin_normal,
)
from surfaces.surface_state import SurfacePatch, add_surface
from surfaces.brep_state import BrepSurfaceRecord, add_brep_surface
from viewer.embedded_viewport import MeshPickResult


class FakeBounds:
    def __init__(
        self,
        minimum: tuple[float, float, float],
        maximum: tuple[float, float, float],
    ) -> None:
        self.minimum = minimum
        self.maximum = maximum

    def get_min_bound(self) -> tuple[float, float, float]:
        return self.minimum

    def get_max_bound(self) -> tuple[float, float, float]:
        return self.maximum

    def get_extent(self) -> tuple[float, float, float]:
        return tuple(maximum - minimum for minimum, maximum in zip(self.minimum, self.maximum))

    def get_max_extent(self) -> float:
        return max(self.get_extent())

    def get_center(self) -> tuple[float, float, float]:
        return tuple((minimum + maximum) * 0.5 for minimum, maximum in zip(self.minimum, self.maximum))


class FakeMesh:
    def __init__(self) -> None:
        self.vertices = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 2.0, 3.0)]
        self.triangles = [(0, 1, 2)]

    def copy(self) -> FakeMesh:
        copied = FakeMesh()
        copied.vertices = list(self.vertices)
        copied.triangles = list(self.triangles)
        return copied

    def get_axis_aligned_bounding_box(self) -> FakeBounds:
        points = np.asarray(self.vertices, dtype=float)
        return FakeBounds(tuple(points.min(axis=0)), tuple(points.max(axis=0)))

    def has_vertex_normals(self) -> bool:
        return True

    def has_triangle_normals(self) -> bool:
        return True

    def has_vertex_colors(self) -> bool:
        return False

    def is_empty(self) -> bool:
        return len(self.vertices) == 0 or len(self.triangles) == 0

    def paint_uniform_color(self, _color: list[float]) -> None:
        return None

    def transform(self, matrix: np.ndarray) -> None:
        points = np.asarray(self.vertices, dtype=float)
        homogeneous = np.column_stack((points, np.ones(len(points))))
        transformed = (np.asarray(matrix, dtype=float) @ homogeneous.T).T[:, :3]
        self.vertices = [tuple(point) for point in transformed]

    def translate(self, offset: list[float]) -> None:
        points = np.asarray(self.vertices, dtype=float) + np.asarray(offset, dtype=float)
        self.vertices = [tuple(point) for point in points]

    def compute_vertex_normals(self) -> None:
        return None

    def compute_triangle_normals(self) -> None:
        return None


class FakeViewport:
    def __init__(self, _parent: object) -> None:
        self.scene_calls: list[dict[str, object]] = []
        self.frame_count = 0
        self.reset_count = 0
        self.named_views: list[str] = []
        self.framed_bounds: list[tuple[np.ndarray, np.ndarray]] = []
        self.closed = False
        self.selection_callback = None
        self.pointer_callback = None
        self.camera_right = np.asarray([1.0, 0.0, 0.0], dtype=float)
        self.camera_up = np.asarray([0.0, 1.0, 0.0], dtype=float)
        self.projected_points: list[np.ndarray | None] = []
        self.projection_calls: list[dict[str, object]] = []
        self.mesh_pick_results: list[MeshPickResult] = []
        self.mesh_pick_calls: list[dict[str, int]] = []

    def start(self) -> None:
        return None

    def set_selection_callback(self, callback: object) -> None:
        self.selection_callback = callback

    def set_pointer_callback(self, callback: object) -> None:
        self.pointer_callback = callback

    def set_scene(self, mesh: object, **kwargs: object) -> None:
        self.scene_calls.append({"mesh": mesh, **kwargs})

    def screen_point_to_plane(
        self,
        x_position: int,
        y_position: int,
        plane_origin: object,
        plane_normal: object,
    ) -> np.ndarray | None:
        self.projection_calls.append(
            {
                "x": int(x_position),
                "y": int(y_position),
                "plane_origin": np.asarray(plane_origin, dtype=float),
                "plane_normal": np.asarray(plane_normal, dtype=float),
            }
        )
        if self.projected_points:
            point = self.projected_points.pop(0)
            return None if point is None else np.asarray(point, dtype=float)
        return np.asarray([float(x_position), float(y_position), 0.0], dtype=float)

    def pick_mesh_at_screen_point(self, x_position: int, y_position: int) -> MeshPickResult:
        self.mesh_pick_calls.append({"x": int(x_position), "y": int(y_position)})
        if self.mesh_pick_results:
            return self.mesh_pick_results.pop(0)
        return MeshPickResult(hit=False)

    def frame_model(self) -> None:
        self.frame_count += 1

    def frame_bounds(self, minimum_bound: object, maximum_bound: object) -> None:
        self.framed_bounds.append(
            (
                np.asarray(minimum_bound, dtype=float),
                np.asarray(maximum_bound, dtype=float),
            )
        )

    def reset_view(self) -> None:
        self.reset_count += 1

    def reset_camera(self) -> None:
        self.reset_count += 1

    def set_named_view(self, name: str) -> None:
        self.named_views.append(str(name))

    def get_camera_vectors(self) -> object:
        return SimpleNamespace(
            right=self.camera_right,
            up=self.camera_up,
            forward=np.asarray([0.0, 0.0, -1.0], dtype=float),
            position=np.asarray([0.0, 0.0, 1.0], dtype=float),
            focal_point=np.asarray([0.0, 0.0, 0.0], dtype=float),
        )

    def close(self) -> None:
        self.closed = True


def _create_window(*, settings_path: Path | None = None) -> OpenRetopWindow:
    settings_tmpdir: TemporaryDirectory[str] | None = None
    if settings_path is None:
        settings_tmpdir = TemporaryDirectory()
        settings_path = Path(settings_tmpdir.name) / "settings.json"

    try:
        window = OpenRetopWindow(settings_path=settings_path)
    except TclError as exc:
        if settings_tmpdir is not None:
            settings_tmpdir.cleanup()
        raise unittest.SkipTest(f"Tk is unavailable: {exc}") from exc

    if settings_tmpdir is not None:
        original_destroy = window.root.destroy

        def destroy_with_settings_cleanup() -> None:
            try:
                original_destroy()
            finally:
                settings_tmpdir.cleanup()

        window.root.destroy = destroy_with_settings_cleanup  # type: ignore[method-assign]

    window.root.update_idletasks()
    if window._start_viewport_after_id is not None:
        window.root.after_cancel(window._start_viewport_after_id)
        window._start_viewport_after_id = None
    return window


def _widget_descendants(widget: object) -> list[object]:
    descendants: list[object] = []
    for child in widget.winfo_children():
        descendants.append(child)
        descendants.extend(_widget_descendants(child))
    return descendants


def _button_by_text(widget: object, text: str) -> object:
    for child in _widget_descendants(widget):
        if child.winfo_class() == "TButton" and child.cget("text") == text:
            return child
    raise AssertionError(f"Button not found: {text}")


def _widgets_with_text(widget: object, text: str) -> list[object]:
    matches: list[object] = []
    for child in _widget_descendants(widget):
        try:
            if child.cget("text") == text:
                matches.append(child)
        except TclError:
            continue
    return matches


def _window_is_zoomed(window: OpenRetopWindow) -> bool:
    try:
        return str(window.root.state()) == "zoomed"
    except TclError:
        return False


def _assert_startup_size_or_zoomed(
    test_case: unittest.TestCase,
    window: OpenRetopWindow,
    expected_size: str,
) -> None:
    if _window_is_zoomed(window):
        return
    test_case.assertTrue(window.root.geometry().startswith(expected_size))


def _make_curve_closed(curve: StoredCurve) -> None:
    closed_points = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0],
        ],
        dtype=float,
    )
    curve.original_points = closed_points.copy()
    curve.fitted_points = closed_points.copy()
    curve.is_closed = True


def _sharp_region_mesh() -> TriangleMeshData:
    return TriangleMeshData(
        vertices=np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [-0.5, 0.0, 0.5],
            ],
            dtype=float,
        ),
        triangles=np.asarray(
            [
                [0, 1, 2],
                [0, 2, 3],
            ],
            dtype=int,
        ),
    )


def _load_sample_model(window: OpenRetopWindow) -> None:
    mesh = FakeMesh()
    metadata = MeshMetadata(
        file_path=Path("sample.stl"),
        file_name="sample.stl",
        extension=".stl",
        vertex_count=3,
        triangle_count=1,
        had_vertex_normals=True,
        had_triangle_normals=True,
        computed_vertex_normals=False,
        computed_triangle_normals=False,
    )
    with patch(
        "app.main_window.load_mesh",
        return_value=LoadedMesh(mesh=mesh, metadata=metadata),
    ):
        window.load_model(Path("sample.stl"))


def _build_two_section_scene(
    window: OpenRetopWindow,
) -> tuple[
    SectionPlaneState,
    SectionPlaneState,
    StoredSectionResult,
    StoredSectionResult,
    StoredCurve,
    StoredCurve,
    SurfacePatch,
    SurfacePatch,
]:
    _load_sample_model(window)
    window.compute_section()
    first_plane = window.app_state.section_collection.planes[0]
    first_result = window.app_state.section_collection.results[0]
    first_curve = window.app_state.curve_collection.curves[0]

    window.add_section_plane()
    second_plane = window.app_state.section_collection.planes[1]
    window.section_axis.set("X")
    window._on_section_axis_changed()
    window._set_section_offset(0.5, clamp=True, refresh=True)
    window.compute_section()
    second_result = window.app_state.section_collection.results[1]
    second_curve = window.app_state.curve_collection.curves[1]

    first_surface = SurfacePatch(
        id="surface-1",
        name="Surface 1",
        source_curve_ids=[first_curve.id],
        surface_type="preview_fill",
    )
    second_surface = SurfacePatch(
        id="surface-2",
        name="Surface 2",
        source_curve_ids=[second_curve.id],
        surface_type="preview_fill",
    )
    add_surface(window.app_state.surface_collection, first_surface)
    add_surface(window.app_state.surface_collection, second_surface)
    window._refresh_viewport(reset_camera=False)
    return (
        first_plane,
        second_plane,
        first_result,
        second_result,
        first_curve,
        second_curve,
        first_surface,
        second_surface,
    )


def _create_manual_curve(
    window: OpenRetopWindow,
    points: list[tuple[float, float, float]],
    *,
    closed: bool = False,
    snap_to_mesh: bool = False,
    triangle_indices: list[int | None] | None = None,
) -> StoredCurve:
    window.start_manual_curve_mode()
    window.manual_curve_snap_to_mesh.set(snap_to_mesh)
    window._on_manual_curve_snap_to_mesh_changed()
    if snap_to_mesh:
        triangle_indices = triangle_indices or [None] * len(points)
        window.viewport.mesh_pick_results = [
            MeshPickResult(
                hit=True,
                position=np.asarray(point, dtype=float),
                normal=np.asarray([0.0, 0.0, 1.0], dtype=float),
                triangle_index=triangle_indices[index],
            )
            for index, point in enumerate(points)
        ]
    else:
        window.viewport.projected_points = [np.asarray(point, dtype=float) for point in points]
    for index, _point in enumerate(points):
        if not _manual_curve_click(window, 10 + index, 20 + index):
            raise AssertionError("Manual curve point click was not handled")
    if closed:
        window._handle_shortcut("C")
    window._handle_shortcut("Enter")
    return window.app_state.curve_collection.curves[-1]


def _manual_curve_click(window: OpenRetopWindow, x_position: int, y_position: int) -> bool:
    press_handled = window._on_viewport_pointer_event(
        "left_press",
        x_position,
        y_position,
    )
    release_handled = window._on_viewport_pointer_event(
        "left_release",
        x_position,
        y_position,
    )
    return bool(press_handled and release_handled)


def _region_click(window: OpenRetopWindow, x_position: int, y_position: int) -> bool:
    press_handled = window._on_viewport_pointer_event(
        "left_press",
        x_position,
        y_position,
    )
    release_handled = window._on_viewport_pointer_event(
        "left_release",
        x_position,
        y_position,
    )
    return bool(press_handled and release_handled)


class MainWindowUiTests(unittest.TestCase):
    def test_menu_bar_and_initial_no_selection_context_match_instructions(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            self.assertEqual(window.menu_bar.entrycget(0, "label"), "File")
            self.assertEqual(window.menu_bar.entrycget(1, "label"), "Edit")
            self.assertEqual(window.menu_bar.entrycget(2, "label"), "View")
            self.assertEqual(window.menu_bar.entrycget(3, "label"), "Help")
            self.assertEqual(window.menu_bar.index("end"), 3)
            self.assertEqual(window.file_menu.entrycget(0, "label"), "New Project")
            self.assertEqual(window.file_menu.entrycget(1, "label"), "Open Project")
            self.assertEqual(window.file_menu.entrycget(2, "label"), "Save Project")
            self.assertEqual(window.file_menu.entrycget(3, "label"), "Save Project As")
            self.assertEqual(window.file_menu.entrycget(4, "label"), "Open Model")
            self.assertEqual(window.file_menu.entrycget(5, "label"), "Recent Files")
            self.assertEqual(window.file_menu.entrycget(6, "label"), "Exit")
            self.assertEqual(window.edit_menu.entrycget(0, "label"), "Undo")
            self.assertEqual(window.edit_menu.entrycget(1, "label"), "Redo")
            self.assertEqual(window.edit_menu.entrycget(0, "state"), "disabled")
            self.assertEqual(window.edit_menu.entrycget(1, "state"), "disabled")
            self.assertEqual(window.edit_menu.entrycget(2, "label"), "Rename Selected")
            self.assertEqual(window.edit_menu.entrycget(3, "label"), "Delete Selected")
            self.assertEqual(window.edit_menu.entrycget(4, "label"), "Preferences")
            self.assertEqual(window.view_menu.entrycget(0, "label"), "Frame All")
            self.assertEqual(window.view_menu.entrycget(1, "label"), "Frame Selected")
            self.assertEqual(window.view_menu.entrycget(2, "label"), "Reset View")
            self.assertEqual(window.view_menu.entrycget(3, "label"), "Top View")
            self.assertEqual(window.view_menu.entrycget(4, "label"), "Bottom View")
            self.assertEqual(window.view_menu.entrycget(5, "label"), "Front View")
            self.assertEqual(window.view_menu.entrycget(6, "label"), "Back View")
            self.assertEqual(window.view_menu.entrycget(7, "label"), "Left View")
            self.assertEqual(window.view_menu.entrycget(8, "label"), "Right View")
            self.assertEqual(window.view_menu.entrycget(9, "label"), "Isometric View")
            self.assertEqual(window.view_menu.entrycget(10, "label"), "Show Grid")
            self.assertEqual(window.view_menu.entrycget(11, "label"), "Show Axes")
            self.assertEqual(window.view_menu.entrycget(12, "label"), "Show Axis Gizmo")
            self.assertEqual(window.view_menu.entrycget(13, "label"), "Show View Controls")
            self.assertEqual(window.view_menu.index("end"), 13)
            self.assertEqual(window.view_menu.type(10), "checkbutton")
            self.assertEqual(window.view_menu.type(11), "checkbutton")
            self.assertEqual(window.view_menu.type(12), "checkbutton")
            self.assertEqual(window.view_menu.type(13), "checkbutton")
            self.assertEqual(window.scene_menu.entrycget(0, "label"), "Rename Selected")
            self.assertEqual(window.scene_menu.entrycget(1, "label"), "Delete Selected")
            self.assertEqual(window.scene_menu.entrycget(2, "label"), "Toggle Visibility")
            self.assertEqual(window.sections_menu.entrycget(0, "label"), "Add Section Plane")
            self.assertEqual(window.sections_menu.entrycget(2, "label"), "Compute Section")
            self.assertEqual(window.curves_menu.entrycget(0, "label"), "Fill Closed Curve")
            self.assertEqual(window.curves_menu.entrycget(1, "label"), "Join Selected Curves")
            self.assertEqual(window.curves_menu.entrycget(2, "label"), "Auto-Close Selected Curve")
            self.assertEqual(window.curves_menu.entrycget(7, "label"), "Select Tiny Curves")
            self.assertEqual(window.curves_menu.entrycget(8, "label"), "Hide Tiny Curves")
            self.assertEqual(window.curves_menu.entrycget(9, "label"), "Delete Tiny Curves")
            self.assertEqual(window.curves_menu.entrycget(10, "label"), "Simplify Selected Curve")
            self.assertEqual(window.curves_menu.entrycget(11, "label"), "Smooth Selected Curve")
            self.assertEqual(window.curves_menu.entrycget(12, "label"), "Project Selected Curve to Mesh")
            self.assertEqual(window.curves_menu.entrycget(13, "label"), "Rebuild Selected Curve")
            self.assertEqual(window.curves_menu.entrycget(14, "label"), "Loft Between Two Curves")
            self.assertEqual(window.curves_menu.entrycget(15, "label"), "Create Manual Curve")
            self.assertEqual(window.curves_menu.entrycget(16, "label"), "Extract Region Boundary")
            self.assertEqual(window.curves_menu.entrycget(17, "label"), "Snap to Mesh")
            self.assertEqual(window.curves_menu.type(17), "checkbutton")
            self.assertEqual(window.surfaces_menu.entrycget(0, "label"), "Fill Closed Curve")
            self.assertEqual(window.surfaces_menu.entrycget(1, "label"), "Loft Between Two Curves")
            self.assertEqual(
                window.surfaces_menu.entrycget(2, "label"),
                "Create BREP Face From Closed Curve",
            )
            self.assertEqual(
                window.surfaces_menu.entrycget(3, "label"),
                "Create BREP Loft From Two Curves",
            )
            self.assertEqual(
                window.surfaces_menu.entrycget(4, "label"),
                "Export Selected BREP Surface to STEP",
            )
            self.assertEqual(
                window.surfaces_menu.entrycget(5, "label"),
                "Rebuild Selected BREP Surface",
            )
            self.assertEqual(window.surfaces_menu.entrycget(6, "label"), "Create Boundary Patch")
            self.assertEqual(window.surfaces_menu.entrycget(7, "label"), "Create Four-Curve Patch")
            self.assertEqual(window.surfaces_menu.entrycget(8, "label"), "Create Curve Network Patch")
            self.assertEqual(window.surfaces_menu.entrycget(9, "label"), "Select Source Curves")
            self.assertEqual(window.surfaces_menu.entrycget(10, "label"), "Isolate Source Curves")
            self.assertEqual(window.surfaces_menu.entrycget(11, "label"), "Show Source Curves")
            self.assertEqual(window.surfaces_menu.entrycget(12, "label"), "Frame Source Curves")
            self.assertEqual(
                window.surfaces_menu.entrycget(15, "label"),
                "Create BREP Face From Selected Region",
            )
            self.assertEqual(window.tools_menu.entrycget(0, "label"), "Select Model")
            self.assertEqual(window.tools_menu.entrycget(1, "label"), "Select Section Plane")
            self.assertEqual(window.tools_menu.entrycget(2, "label"), "Move")
            self.assertEqual(window.tools_menu.entrycget(3, "label"), "Rotate")
            self.assertEqual(window.help_menu.entrycget(0, "label"), "Hotkeys")
            self.assertEqual(window.help_menu.entrycget(1, "label"), "About")

            self.assertTrue(window.show_grid.get())
            self.assertTrue(window.show_axes.get())
            self.assertTrue(window.show_axis_gizmo.get())
            self.assertTrue(window.show_viewcube.get())
            self.assertEqual(window.viewcube_frame.winfo_manager(), "place")
            self.assertIs(window.view_controls_frame, window.viewcube_frame)
            self.assertTrue(_widgets_with_text(window.view_controls_frame, "View"))
            self.assertFalse(_widgets_with_text(window.view_controls_frame, "ViewCube"))
            self.assertFalse(_widgets_with_text(window.view_controls_frame, "View Controls"))
            self.assertEqual(
                [button.cget("text") for button in window.view_controls_buttons],
                ["Top", "Front", "Right", "Iso"],
            )
            self.assertTrue(
                all(int(button.cget("width")) == 5 for button in window.view_controls_buttons)
            )
            self.assertEqual(window.view_controls_frame.place_info().get("anchor"), "ne")
            self.assertEqual(window.view_controls_frame.place_info().get("x"), "-10")
            self.assertEqual(window.view_controls_frame.place_info().get("y"), "10")
            self.assertFalse(window.show_normals.get())
            self.assertFalse(window.show_section_plane.get())
            self.assertEqual(window.proxy_quality.get(), "Medium")
            self.assertEqual(tuple(window.proxy_quality_dropdown.cget("values")), ("Low", "Medium", "High"))
            self.assertEqual(window.status_text.get(), "Open Model to begin")
            self.assertEqual(window.current_mode_text.get(), "No Mode")
            self.assertEqual(
                window.command_prompt_text.get(),
                "Open a model, adjust viewport visibility, or frame the scene.",
            )
            self.assertIn("G=move", window.hotkey_hint_text.get())
            self.assertIsNone(window.current_project_path)
            self.assertFalse(window.project_dirty)
            self.assertEqual(window.root.title(), "openRetop - Untitled Project")
            self.assertIsNone(window.app_state.selected_item)
            self.assertEqual(
                list(window.workbench_panels.keys()),
                ["Scene", "Transform", "Sections", "Curves", "Surfaces", "Manual RE", "Analysis"],
            )
            self.assertEqual(window.current_workbench.get(), "Scene")
            self.assertEqual(window.no_selection_frame.winfo_manager(), "grid")
            self.assertEqual(window.model_context_frame.winfo_manager(), "")
            self.assertEqual(window.section_context_frame.winfo_manager(), "grid")
            self.assertEqual(window.curve_context_frame.winfo_manager(), "grid")
            self.assertEqual(window.surface_context_frame.winfo_manager(), "grid")
            self.assertFalse(hasattr(window, "apply_transform_button"))
            self.assertEqual(str(window.select_model_button.cget("state")), "disabled")
            self.assertEqual(str(window.select_section_plane_button.cget("state")), "disabled")
            self.assertEqual(window.compute_section_button.cget("text"), "Compute Section")
            self.assertEqual(window.clear_section_button.cget("text"), "Clear Active Section Result")
            self.assertEqual(window.section_plane_text.get(), "Section: Z = 0.000")
            self.assertEqual(window.section_result_text.get(), "Section result: none")
            self.assertEqual(window.scale_value.get(), "1.000")
            self.assertGreaterEqual(int(window.sidebar_canvas.cget("width")), 260)
            self.assertLessEqual(int(window.sidebar_canvas.cget("width")), 300)
            self.assertEqual(window.scene_browser.frame.winfo_manager(), "grid")
            self.assertEqual(int(window.scene_browser.frame.cget("width")), 230)
            self.assertEqual(window.scene_browser.tree.item(NODE_SCENE, "text"), "Scene")
            self.assertEqual(window.scene_browser.tree.get_children(NODE_SCENE), (NODE_EMPTY_SCENE,))
            self.assertEqual(window.scene_browser.tree.item(NODE_EMPTY_SCENE, "text"), "No mesh loaded")
        finally:
            window.root.destroy()

    def test_empty_undo_redo_report_no_operation_without_crashing(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            window.undo()
            self.assertEqual(window.status_text.get(), "Nothing to undo")
            window.redo()
            self.assertEqual(window.status_text.get(), "Nothing to redo")
            window.help_menu.invoke(1)
            self.assertEqual(window.status_text.get(), "About: Not implemented yet")
        finally:
            window.root.destroy()

    def test_manual_re_workbench_explains_manual_curve_and_snap_state(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            window._set_active_workbench("Manual RE", set_status=True)

            self.assertEqual(window.current_workbench.get(), "Manual RE")
            self.assertEqual(window.manual_curve_mode_title.get(), "Manual Curve")
            self.assertEqual(
                window.manual_curve_mode_details.get(),
                "Create a manual curve by placing points.",
            )
            self.assertEqual(
                window.manual_curve_snap_help_text.get(),
                "Load a mesh to enable Snap to Mesh.",
            )
            self.assertEqual(str(window.start_manual_curve_button.cget("state")), "disabled")
            self.assertEqual(str(window.edit_manual_curve_button.cget("state")), "disabled")
            self.assertEqual(str(window.done_manual_curve_edit_button.cget("state")), "disabled")
            self.assertEqual(str(window.add_manual_point_button.cget("state")), "disabled")
            self.assertEqual(str(window.insert_manual_point_button.cget("state")), "disabled")
            self.assertEqual(str(window.delete_manual_point_button.cget("state")), "disabled")
            self.assertEqual(str(window.manual_curve_snap_check.cget("state")), "disabled")

            _load_sample_model(window)
            window._set_active_workbench("Manual RE", set_status=True)

            self.assertEqual(str(window.start_manual_curve_button.cget("state")), "normal")
            self.assertEqual(str(window.edit_manual_curve_button.cget("state")), "disabled")
            self.assertEqual(str(window.manual_curve_snap_check.cget("state")), "normal")
            self.assertEqual(
                window.manual_curve_snap_help_text.get(),
                "Snap to Mesh places manual curve points on the scan surface.",
            )

            window.start_manual_curve_mode()

            details = window.manual_curve_mode_details.get()
            self.assertEqual(window.manual_curve_mode_title.get(), "MANUAL CURVE MODE")
            self.assertEqual(window.current_mode_text.get(), "Manual Curve")
            self.assertEqual(
                window.command_prompt_text.get(),
                "Manual Curve: previewing next point. Click to place.",
            )
            self.assertIn("Enter=finish", window.hotkey_hint_text.get())
            self.assertIn("MANUAL CURVE MODE", details)
            self.assertIn("Point count: 0", details)
            self.assertIn("Snap mode: Off", details)
            self.assertIn("Drawing plane: Section Plane", details)
            self.assertIn("Closed: No", details)
            self.assertEqual(str(window.finish_manual_curve_button.cget("state")), "normal")
            self.assertEqual(str(window.cancel_manual_curve_button.cget("state")), "normal")
            self.assertEqual(str(window.remove_manual_point_button.cget("state")), "normal")
            self.assertEqual(str(window.toggle_manual_closed_button.cget("state")), "normal")
            self.assertEqual(str(window.done_manual_curve_edit_button.cget("state")), "disabled")
            self.assertEqual(str(window.add_manual_point_button.cget("state")), "disabled")
            self.assertEqual(str(window.insert_manual_point_button.cget("state")), "disabled")
        finally:
            window.root.destroy()

    def test_named_view_menu_invokes_viewport_without_refreshing_scene(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            scene_call_count = len(window.viewport.scene_calls)
            window.view_menu.invoke(3)

            self.assertEqual(window.viewport.named_views, ["top"])
            self.assertEqual(len(window.viewport.scene_calls), scene_call_count)
            self.assertEqual(window.status_text.get(), "View: Top")
        finally:
            window.root.destroy()

    def test_preferences_dialog_opens_with_startup_values_and_controls(self) -> None:
        settings = default_app_settings()
        settings.display.show_grid = False
        settings.display.show_axes = False
        settings.display.show_normals = True
        settings.display.show_axis_gizmo = False
        settings.display.show_viewcube = False
        settings.display.region_selection_color = "#FF8800"
        settings.display.region_selection_edge_color = "#FFF2CC"
        settings.display.region_selection_opacity = 0.5
        settings.import_settings.default_proxy_quality = "High"

        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"
            save_settings(settings, settings_path)

            with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
                window = _create_window(settings_path=settings_path)

        try:
            window.show_grid.set(True)
            window.show_axes.set(True)
            window.show_normals.set(False)
            window.proxy_quality.set("Medium")

            window.edit_menu.invoke(4)
            window.root.update()
            dialog = window.preferences_dialog
            self.assertIsNotNone(dialog)
            assert dialog is not None

            self.assertEqual(dialog.title(), "Preferences")
            self.assertIsNotNone(window.preferences_notebook)
            assert window.preferences_notebook is not None
            self.assertEqual(
                [
                    window.preferences_notebook.tab(index, "text")
                    for index in range(window.preferences_notebook.index("end"))
                ],
                ["General", "Viewport", "Keybinds", "Advanced"],
            )
            self.assertEqual(window.preferences_vars["window_mode"].get(), "maximized")
            self.assertTrue(window.preferences_vars["remember_window_size"].get())
            self.assertFalse(window.preferences_vars["show_grid"].get())
            self.assertFalse(window.preferences_vars["show_axes"].get())
            self.assertFalse(window.preferences_vars["show_axis_gizmo"].get())
            self.assertFalse(window.preferences_vars["show_viewcube"].get())
            self.assertEqual(window.preferences_vars["region_selection_color"].get(), "#FF8800")
            self.assertEqual(window.preferences_vars["region_selection_edge_color"].get(), "#FFF2CC")
            self.assertEqual(window.preferences_vars["region_selection_opacity"].get(), "0.50")
            self.assertNotIn("show_normals", window.preferences_vars)
            self.assertNotIn("surface_preview_opacity", window.preferences_vars)
            self.assertNotIn("curve_display_thickness", window.preferences_vars)
            self.assertNotIn("selected_highlight_thickness", window.preferences_vars)
            self.assertEqual(window.preferences_vars["default_proxy_quality"].get(), "High")
            self.assertTrue(_widgets_with_text(dialog, "Startup window mode"))
            self.assertTrue(_widgets_with_text(dialog, "Remember last window size"))
            self.assertTrue(_widgets_with_text(dialog, "Default Show Grid"))
            self.assertTrue(_widgets_with_text(dialog, "Default Show Axes"))
            self.assertTrue(_widgets_with_text(dialog, "Default Show Axis Gizmo"))
            self.assertTrue(_widgets_with_text(dialog, "Default Show View Controls"))
            self.assertTrue(_widgets_with_text(dialog, "Region Fill Color"))
            self.assertTrue(_widgets_with_text(dialog, "Region Edge Color"))
            self.assertTrue(_widgets_with_text(dialog, "Region Opacity"))
            self.assertFalse(_widgets_with_text(dialog, "Startup Show Grid"))
            self.assertFalse(_widgets_with_text(dialog, "Startup Show Axes"))
            self.assertFalse(_widgets_with_text(dialog, "Surface preview opacity"))
            self.assertFalse(_widgets_with_text(dialog, "Curve display thickness"))
            self.assertFalse(_widgets_with_text(dialog, "Selected object highlight thickness"))
            self.assertTrue(_widgets_with_text(dialog, "Rename Selected"))
            self.assertTrue(_widgets_with_text(dialog, "Toggle Visibility"))
            self.assertTrue(_widgets_with_text(dialog, "Delete Selected"))
            self.assertTrue(_widgets_with_text(dialog, "Manual Curve"))
            self.assertTrue(_widgets_with_text(dialog, "Finish Curve"))
            self.assertTrue(_widgets_with_text(dialog, "Remove Last Point"))
            self.assertTrue(_widgets_with_text(dialog, "Toggle Closed"))
            self.assertTrue(_widgets_with_text(dialog, "Backspace"))
            self.assertTrue(_widgets_with_text(dialog, "C"))
            self.assertTrue(_widgets_with_text(dialog, "Reset Preferences"))
            self.assertTrue(_widgets_with_text(dialog, "Diagnostics"))
            self.assertFalse(_widgets_with_text(dialog, "Clear Recent Files"))
            self.assertEqual(window.preferences_vars["keybind.rename_selected"].get(), "F2")
            self.assertEqual(window.preferences_vars["keybind.toggle_visibility"].get(), "H")
            self.assertEqual(window.preferences_vars["keybind.isolate_selected"].get(), "Shift+H")
            self.assertFalse(_widgets_with_text(dialog, "Startup Show Normals"))
            self.assertFalse(_widgets_with_text(dialog, "Show Grid"))
            self.assertFalse(_widgets_with_text(dialog, "Show Axes"))
            self.assertFalse(_widgets_with_text(dialog, "Show Normals"))
            self.assertTrue(_widgets_with_text(dialog, "Default Proxy Quality"))
            for button_text in ("OK", "Cancel", "Apply"):
                self.assertIsNotNone(_button_by_text(dialog, button_text))

            comboboxes = [
                widget
                for widget in _widget_descendants(dialog)
                if widget.winfo_class() == "TCombobox"
            ]
            self.assertEqual(len(comboboxes), 2)
            self.assertIn(("Low", "Medium", "High"), [tuple(box.cget("values")) for box in comboboxes])

            existing_dialog = window.preferences_dialog
            window.edit_menu.invoke(4)
            self.assertIs(window.preferences_dialog, existing_dialog)
        finally:
            if window.preferences_dialog is not None:
                window._close_preferences_dialog()
            window.root.destroy()

    def test_preferences_apply_updates_startup_defaults_without_changing_current_scene(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"
            with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
                window = _create_window(settings_path=settings_path)

            try:
                window.edit_menu.invoke(4)
                dialog = window.preferences_dialog
                self.assertIsNotNone(dialog)
                assert dialog is not None

                scene_call_count = len(window.viewport.scene_calls)
                window.preferences_vars["show_grid"].set(False)
                window.preferences_vars["show_axes"].set(False)
                window.preferences_vars["show_axis_gizmo"].set(False)
                window.preferences_vars["show_viewcube"].set(False)
                window.preferences_vars["window_mode"].set("remembered_size")
                window.preferences_vars["remember_window_size"].set(False)
                window.preferences_vars["keybind.toggle_visibility"].set("V")
                window.preferences_vars["default_proxy_quality"].set("Low")
                window.preferences_vars["region_selection_color"].set("#00ff00")
                window.preferences_vars["region_selection_edge_color"].set("#ffffff")
                window.preferences_vars["region_selection_opacity"].set("1.5")
                _button_by_text(dialog, "Apply").invoke()

                self.assertIsNotNone(window.preferences_dialog)
                self.assertTrue(window.show_grid.get())
                self.assertTrue(window.show_axes.get())
                self.assertTrue(window.show_axis_gizmo.get())
                self.assertTrue(window.show_viewcube.get())
                self.assertEqual(window.viewcube_frame.winfo_manager(), "place")
                self.assertFalse(window.show_normals.get())
                self.assertEqual(window.proxy_quality.get(), "Medium")
                self.assertEqual(window.status_text.get(), "Preferences applied")
                self.assertEqual(len(window.viewport.scene_calls), scene_call_count)
                self.assertFalse(window.settings.display.show_grid)
                self.assertFalse(window.settings.display.show_axes)
                self.assertFalse(window.settings.display.show_normals)
                self.assertFalse(window.settings.display.show_axis_gizmo)
                self.assertFalse(window.settings.display.show_viewcube)
                self.assertEqual(window.settings.display.region_selection_color, "#00FF00")
                self.assertEqual(window.settings.display.region_selection_edge_color, "#FFFFFF")
                self.assertEqual(window.settings.display.region_selection_opacity, 1.0)
                self.assertEqual(
                    window.settings.import_settings.default_proxy_quality,
                    "Low",
                )
                self.assertEqual(window.settings.ui.window_mode, "remembered_size")
                self.assertFalse(window.settings.ui.remember_window_size)
                self.assertEqual(window.settings.keybinds.toggle_visibility, "V")

                saved_settings = load_settings(settings_path)
                self.assertFalse(saved_settings.display.show_grid)
                self.assertFalse(saved_settings.display.show_axes)
                self.assertFalse(saved_settings.display.show_normals)
                self.assertFalse(saved_settings.display.show_axis_gizmo)
                self.assertFalse(saved_settings.display.show_viewcube)
                self.assertEqual(saved_settings.display.region_selection_color, "#00FF00")
                self.assertEqual(saved_settings.display.region_selection_edge_color, "#FFFFFF")
                self.assertEqual(saved_settings.display.region_selection_opacity, 1.0)
                self.assertEqual(
                    saved_settings.import_settings.default_proxy_quality,
                    "Low",
                )
                self.assertEqual(saved_settings.ui.window_mode, "remembered_size")
                self.assertFalse(saved_settings.ui.remember_window_size)
                self.assertEqual(saved_settings.keybinds.toggle_visibility, "V")
            finally:
                if window.preferences_dialog is not None:
                    window._close_preferences_dialog()
                window.root.destroy()

            with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
                restored_window = _create_window(settings_path=settings_path)

            try:
                self.assertFalse(restored_window.show_grid.get())
                self.assertFalse(restored_window.show_axes.get())
                self.assertFalse(restored_window.show_axis_gizmo.get())
                self.assertFalse(restored_window.show_viewcube.get())
                self.assertEqual(restored_window.viewcube_frame.winfo_manager(), "")
                self.assertFalse(restored_window.show_normals.get())
                self.assertEqual(restored_window.proxy_quality.get(), "Low")
            finally:
                restored_window.root.destroy()

    def test_preferences_rejects_empty_keybinds(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"
            with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
                window = _create_window(settings_path=settings_path)

            try:
                window.edit_menu.invoke(4)
                dialog = window.preferences_dialog
                self.assertIsNotNone(dialog)
                assert dialog is not None

                window.preferences_vars["keybind.toggle_visibility"].set(" ")
                _button_by_text(dialog, "Apply").invoke()

                self.assertEqual(
                    window.status_text.get(),
                    "Toggle Visibility keybind cannot be empty",
                )
                self.assertEqual(window.settings.keybinds.toggle_visibility, "H")
                self.assertEqual(load_settings(settings_path).keybinds.toggle_visibility, "H")

                _button_by_text(dialog, "OK").invoke()
                self.assertIsNotNone(window.preferences_dialog)
            finally:
                if window.preferences_dialog is not None:
                    window._close_preferences_dialog()
                window.root.destroy()

    def test_preferences_rejects_invalid_region_hex_color(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"
            with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
                window = _create_window(settings_path=settings_path)

            try:
                window.edit_menu.invoke(4)
                dialog = window.preferences_dialog
                self.assertIsNotNone(dialog)
                assert dialog is not None

                window.preferences_vars["region_selection_color"].set("cyan")
                _button_by_text(dialog, "Apply").invoke()

                self.assertEqual(window.status_text.get(), "Region Fill Color must be #RRGGBB.")
                self.assertEqual(window.settings.display.region_selection_color, "#00D1FF")
                self.assertFalse(settings_path.exists())
            finally:
                if window.preferences_dialog is not None:
                    window._close_preferences_dialog()
                window.root.destroy()

    def test_preferences_ok_applies_and_closes_dialog(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"
            with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
                window = _create_window(settings_path=settings_path)

            try:
                window.edit_menu.invoke(4)
                dialog = window.preferences_dialog
                self.assertIsNotNone(dialog)
                assert dialog is not None

                window.preferences_vars["show_grid"].set(False)
                _button_by_text(dialog, "OK").invoke()

                self.assertIsNone(window.preferences_dialog)
                self.assertEqual(window.preferences_vars, {})
                self.assertTrue(window.show_grid.get())
                self.assertFalse(window.settings.display.show_grid)
                self.assertFalse(load_settings(settings_path).display.show_grid)
                self.assertEqual(window.status_text.get(), "Preferences applied")
            finally:
                window.root.destroy()

    def test_preferences_cancel_closes_without_applying(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"
            with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
                window = _create_window(settings_path=settings_path)

            try:
                window.edit_menu.invoke(4)
                dialog = window.preferences_dialog
                self.assertIsNotNone(dialog)
                assert dialog is not None

                window.preferences_vars["show_grid"].set(False)
                window.preferences_vars["default_proxy_quality"].set("High")
                _button_by_text(dialog, "Cancel").invoke()

                self.assertIsNone(window.preferences_dialog)
                self.assertEqual(window.preferences_vars, {})
                self.assertTrue(window.show_grid.get())
                self.assertEqual(window.proxy_quality.get(), "Medium")
                self.assertFalse(settings_path.exists())
            finally:
                window.root.destroy()

    def test_startup_loads_preferences_from_settings_file(self) -> None:
        settings = default_app_settings()
        settings.display.show_grid = False
        settings.display.show_axes = False
        settings.display.show_normals = True
        settings.display.show_axis_gizmo = False
        settings.display.show_viewcube = False
        settings.import_settings.default_proxy_quality = "High"
        settings.ui.window_width = 1120
        settings.ui.window_height = 720

        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"
            save_settings(settings, settings_path)

            with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
                window = _create_window(settings_path=settings_path)

            try:
                self.assertFalse(window.show_grid.get())
                self.assertFalse(window.show_axes.get())
                self.assertFalse(window.show_axis_gizmo.get())
                self.assertFalse(window.show_viewcube.get())
                self.assertEqual(window.viewcube_frame.winfo_manager(), "")
                self.assertFalse(window.show_normals.get())
                self.assertEqual(window.proxy_quality.get(), "High")
                _assert_startup_size_or_zoomed(self, window, "1120x720")
                self.assertEqual(window.display_proxy_text.get(), "Disabled (High)")
            finally:
                window.root.destroy()

    def test_invalid_startup_preferences_recover_to_defaults(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"
            settings_path.write_text("{broken json", encoding="utf-8")

            with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
                window = _create_window(settings_path=settings_path)

            try:
                self.assertTrue(window.show_grid.get())
                self.assertTrue(window.show_axes.get())
                self.assertTrue(window.show_axis_gizmo.get())
                self.assertTrue(window.show_viewcube.get())
                self.assertEqual(window.viewcube_frame.winfo_manager(), "place")
                self.assertFalse(window.show_normals.get())
                self.assertEqual(window.proxy_quality.get(), "Medium")
                _assert_startup_size_or_zoomed(self, window, "1280x800")
            finally:
                window.root.destroy()

    def test_exit_saves_window_size_without_overwriting_startup_preferences(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"

            with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
                window = _create_window(settings_path=settings_path)

            window.show_grid.set(False)
            window.show_axes.set(False)
            window.show_axis_gizmo.set(False)
            window.show_normals.set(True)
            window.proxy_quality.set("Low")
            if _window_is_zoomed(window):
                window.root.state("normal")
            window.root.geometry("1180x740")
            window.root.update_idletasks()
            window._on_exit()

            self.assertTrue(settings_path.exists())
            saved_settings = load_settings(settings_path)
            self.assertTrue(saved_settings.display.show_grid)
            self.assertTrue(saved_settings.display.show_axes)
            self.assertTrue(saved_settings.display.show_axis_gizmo)
            self.assertTrue(saved_settings.display.show_viewcube)
            self.assertFalse(saved_settings.display.show_normals)
            self.assertEqual(saved_settings.import_settings.default_proxy_quality, "Medium")
            self.assertEqual(saved_settings.ui.window_width, 1180)
            self.assertEqual(saved_settings.ui.window_height, 740)

            with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
                restored_window = _create_window(settings_path=settings_path)

            try:
                self.assertTrue(restored_window.show_grid.get())
                self.assertTrue(restored_window.show_axes.get())
                self.assertTrue(restored_window.show_axis_gizmo.get())
                self.assertTrue(restored_window.show_viewcube.get())
                self.assertEqual(restored_window.viewcube_frame.winfo_manager(), "place")
                self.assertFalse(restored_window.show_normals.get())
                self.assertEqual(restored_window.proxy_quality.get(), "Medium")
                _assert_startup_size_or_zoomed(self, restored_window, "1180x740")
            finally:
                restored_window.root.destroy()

    def test_new_project_clears_active_scene_and_project_metadata(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            project_path = Path("saved.openretop")
            (
                _first_plane,
                _second_plane,
                _first_result,
                _second_result,
                _first_curve,
                _second_curve,
                _first_surface,
                _second_surface,
            ) = _build_two_section_scene(window)
            window.current_project_path = project_path
            window._set_project_dirty(True)
            window.select_surface(_first_surface.id)

            with patch("app.main_window.messagebox.askyesnocancel", return_value=False):
                window.file_menu.invoke(0)

            self.assertIsNone(window.current_project_path)
            self.assertFalse(window.project_dirty)
            self.assertEqual(window.root.title(), "openRetop - Untitled Project")
            self.assertEqual(window.status_text.get(), "Project ready: Untitled Project")
            self.assertFalse(window.mesh_state.is_loaded)
            self.assertIsNone(window.app_state.mesh_object)
            self.assertEqual(window.app_state.section_collection.planes, [])
            self.assertEqual(window.app_state.section_collection.results, [])
            self.assertEqual(window.app_state.curve_collection.curves, [])
            self.assertEqual(window.app_state.surface_collection.surfaces, [])
            self.assertIsNone(window.app_state.selected_item)
            self.assertEqual(window.app_state.curve_results, [])
            self.assertIsNone(window.app_state.section_result)
            self.assertEqual(window.file_name_text.get(), "(none)")
            self.assertEqual(window.vertex_count_text.get(), "0")
            self.assertEqual(window.triangle_count_text.get(), "0")
            self.assertEqual(window.location_x.get(), "0.000")
            self.assertEqual(window.rotation_z.get(), "0.000")
            self.assertEqual(window.scale_value.get(), "1.000")
            self.assertEqual(window.scene_browser.tree.get_children(NODE_SCENE), (NODE_EMPTY_SCENE,))
            self.assertEqual(window.scene_browser.tree.item(NODE_EMPTY_SCENE, "text"), "No mesh loaded")
            self.assertIsNone(window.viewport.scene_calls[-1]["mesh"])
            self.assertIsNone(window.viewport.scene_calls[-1]["selected_item"])

            _load_sample_model(window)
            self.assertIsNotNone(window.app_state.mesh_object)
            self.assertEqual(len(window.app_state.section_collection.planes), 1)
            self.assertEqual(window.app_state.section_collection.results, [])
            self.assertEqual(window.app_state.curve_collection.curves, [])
            self.assertEqual(window.app_state.surface_collection.surfaces, [])
            self.assertEqual(
                window.scene_browser.tree.get_children(NODE_SCENE),
                (NODE_MESH, NODE_SECTION_PLANES),
            )
            self.assertEqual(str(window.select_model_button.cget("state")), "normal")
        finally:
            window.root.destroy()

    def test_new_project_dirty_prompt_cancel_keeps_project_metadata(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            project_path = Path("saved.openretop")
            window.current_project_path = project_path
            window._set_project_dirty(True)
            window.status_text.set("Working")

            with patch("app.main_window.messagebox.askyesnocancel", return_value=None) as prompt:
                window.file_menu.invoke(0)

            prompt.assert_called_once()
            self.assertEqual(window.current_project_path, project_path)
            self.assertTrue(window.project_dirty)
            self.assertEqual(window.root.title(), "openRetop - saved.openretop *")
            self.assertEqual(window.status_text.get(), "Working")
        finally:
            window.root.destroy()

    def test_new_project_dirty_prompt_dont_save_resets_metadata(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            window.current_project_path = Path("saved.openretop")
            window._set_project_dirty(True)

            with patch("app.main_window.messagebox.askyesnocancel", return_value=False) as prompt:
                window.file_menu.invoke(0)

            prompt.assert_called_once()
            self.assertIsNone(window.current_project_path)
            self.assertFalse(window.project_dirty)
            self.assertEqual(window.root.title(), "openRetop - Untitled Project")
            self.assertEqual(window.status_text.get(), "Project ready: Untitled Project")
        finally:
            window.root.destroy()

    def test_open_project_without_mesh_path_reads_metadata_only(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with TemporaryDirectory() as tmpdir:
                project_path = Path(tmpdir) / "saved.openretop"
                project = default_project_data()
                project.name = "Saved Metadata"
                project.mesh_path = None
                project.display.show_grid = False
                project.display.show_axes = False
                project.display.show_normals = True
                project.section.axis = "X"
                project.section.offset = 2.0
                project.section.show_plane = True
                save_project(project, project_path)

                scene_call_count = len(window.viewport.scene_calls)
                mesh_object = window.app_state.mesh_object

                with (
                    patch(
                        "app.main_window.filedialog.askopenfilename",
                        return_value=str(project_path),
                    ) as ask_open,
                    patch("app.main_window.load_mesh") as load_mesh,
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(1)

                ask_open.assert_called_once()
                load_mesh.assert_not_called()
                show_error.assert_not_called()
                self.assertEqual(window.current_project_path, project_path)
                self.assertEqual(
                    window.status_text.get(),
                    f"Project loaded: Saved Metadata ({project_path})",
                )
                self.assertFalse(window.project_dirty)
                self.assertEqual(window.root.title(), "openRetop - saved.openretop")
                self.assertIs(window.app_state.mesh_object, mesh_object)
                self.assertEqual(len(window.viewport.scene_calls), scene_call_count)
                self.assertFalse(window.show_grid.get())
                self.assertFalse(window.show_axes.get())
                self.assertFalse(window.show_normals.get())
                self.assertTrue(window.show_section_plane.get())
                self.assertEqual(window.section_axis.get(), "X")
                self.assertEqual(window.section_offset.get(), 2.0)
                self.assertEqual(window.section_offset_text.get(), "2.000")
                self.assertEqual(window.section_plane_text.get(), "Section: X = 2.000")
        finally:
            window.root.destroy()

    def test_open_project_reloads_mesh_and_restores_saved_state(self) -> None:
        mesh = FakeMesh()

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        progress_dialogs: list[object] = []

        class RecordingProgressDialog:
            def __init__(self, _parent: object, file_name: str) -> None:
                self.file_name = file_name
                self.stages: list[str] = []
                self.closed = False
                progress_dialogs.append(self)

            def update_stage(self, stage: str) -> None:
                self.stages.append(stage)

            def close(self) -> None:
                self.closed = True

        try:
            with TemporaryDirectory() as tmpdir:
                mesh_path = Path(tmpdir) / "sample.stl"
                project_path = Path(tmpdir) / "saved.openretop"
                metadata = MeshMetadata(
                    file_path=mesh_path,
                    file_name="sample.stl",
                    extension=".stl",
                    vertex_count=3,
                    triangle_count=1,
                    had_vertex_normals=True,
                    had_triangle_normals=True,
                    computed_vertex_normals=False,
                    computed_triangle_normals=False,
                )
                project = default_project_data()
                project.name = "Restored Project"
                project.mesh_path = str(mesh_path)
                project.transform.location = [4.0, 5.0, 6.0]
                project.transform.rotation = [10.0, 20.0, 30.0]
                project.transform.scale = 1.5
                project.transform.origin = [0.25, 0.5, 0.75]
                project.display.proxy_quality = "High"
                project.display.show_grid = False
                project.display.show_axes = False
                project.display.show_normals = True
                project.section.axis = "X"
                project.section.offset = 0.5
                project.section.show_plane = True
                save_project(project, project_path)

                with (
                    patch("app.main_window.LoadProgressDialog", RecordingProgressDialog),
                    patch(
                        "app.main_window.filedialog.askopenfilename",
                        return_value=str(project_path),
                    ),
                    patch(
                        "app.main_window.load_mesh",
                        return_value=LoadedMesh(mesh=mesh, metadata=metadata),
                    ) as load_mesh,
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(1)

                load_mesh.assert_called_once_with(mesh_path)
                show_error.assert_not_called()
                self.assertEqual(window.current_project_path, project_path)
                self.assertEqual(progress_dialogs[0].file_name, "sample.stl")
                self.assertEqual(progress_dialogs[0].stages, list(LOAD_PROGRESS_STAGES))
                self.assertTrue(progress_dialogs[0].closed)
                self.assertEqual(
                    window.status_text.get(),
                    f"Project loaded: Restored Project ({project_path})",
                )
                self.assertFalse(window.project_dirty)
                self.assertEqual(window.root.title(), "openRetop - saved.openretop")
                self.assertIsNotNone(window.app_state.mesh_object)
                self.assertTrue(np.allclose(window.app_state.mesh_object.location, [4.0, 5.0, 6.0]))
                self.assertTrue(np.allclose(window.app_state.mesh_object.rotation, [10.0, 20.0, 30.0]))
                self.assertAlmostEqual(window.app_state.mesh_object.scale, 1.5)
                self.assertTrue(np.allclose(window.app_state.mesh_object.origin, [0.25, 0.5, 0.75]))
                self.assertEqual(window.location_x.get(), "4.000")
                self.assertEqual(window.location_y.get(), "5.000")
                self.assertEqual(window.location_z.get(), "6.000")
                self.assertEqual(window.rotation_x.get(), "10.000")
                self.assertEqual(window.rotation_y.get(), "20.000")
                self.assertEqual(window.rotation_z.get(), "30.000")
                self.assertEqual(window.scale_value.get(), "1.500")
                self.assertEqual(window.proxy_quality.get(), "High")
                self.assertFalse(window.show_grid.get())
                self.assertFalse(window.show_axes.get())
                self.assertFalse(window.show_normals.get())
                self.assertTrue(window.show_section_plane.get())
                self.assertEqual(window.section_axis.get(), "X")
                self.assertEqual(window.section_offset.get(), 0.5)
                self.assertEqual(window.section_offset_text.get(), "0.500")
                self.assertEqual(window.section_plane_text.get(), "Section: X = 0.500")
                scene = window.viewport.scene_calls[-1]
                self.assertEqual(scene["show_grid"], False)
                self.assertEqual(scene["show_axes"], False)
                self.assertEqual(scene["show_normals"], False)
                self.assertEqual(scene["show_section_plane"], True)
                self.assertEqual(scene["section_axis"], "X")
                self.assertEqual(scene["section_offset"], 0.5)
                self.assertEqual(scene["mesh"], window.app_state.mesh_object.display_mesh)
                self.assertIsNotNone(scene["transform_matrix"])
        finally:
            window.root.destroy()

    def test_open_legacy_project_without_section_planes_restores_single_plane(self) -> None:
        mesh = FakeMesh()

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        class RecordingProgressDialog:
            def __init__(self, _parent: object, _file_name: str) -> None:
                self.closed = False

            def update_stage(self, _stage: str) -> None:
                return None

            def close(self) -> None:
                self.closed = True

        try:
            with TemporaryDirectory() as tmpdir:
                mesh_path = Path(tmpdir) / "sample.stl"
                project_path = Path(tmpdir) / "legacy.openretop"
                project_path.write_text(
                    json.dumps(
                        {
                            "version": 1,
                            "name": "Legacy Section",
                            "mesh_path": str(mesh_path),
                            "section": {
                                "axis": "Y",
                                "offset": 1.25,
                                "show_plane": True,
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                metadata = MeshMetadata(
                    file_path=mesh_path,
                    file_name="sample.stl",
                    extension=".stl",
                    vertex_count=3,
                    triangle_count=1,
                    had_vertex_normals=True,
                    had_triangle_normals=True,
                    computed_vertex_normals=False,
                    computed_triangle_normals=False,
                )

                with (
                    patch("app.main_window.LoadProgressDialog", RecordingProgressDialog),
                    patch(
                        "app.main_window.filedialog.askopenfilename",
                        return_value=str(project_path),
                    ),
                    patch(
                        "app.main_window.load_mesh",
                        return_value=LoadedMesh(mesh=mesh, metadata=metadata),
                    ),
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(1)

                show_error.assert_not_called()
                planes = window.app_state.section_collection.planes
                self.assertEqual(len(planes), 1)
                legacy_plane = planes[0]
                self.assertEqual(legacy_plane.name, "Section Plane 1")
                self.assertEqual(legacy_plane.axis, "Y")
                self.assertEqual(legacy_plane.offset, 1.25)
                self.assertTrue(legacy_plane.visible)
                self.assertTrue(legacy_plane.selected)
                self.assertEqual(window.app_state.section_collection.active_plane_id, legacy_plane.id)
                self.assertEqual(window.section_axis.get(), "Y")
                self.assertEqual(window.section_offset.get(), 1.25)
                self.assertTrue(window.show_section_plane.get())

                tree = window.scene_browser.tree
                legacy_node = section_plane_node_id(legacy_plane.id)
                self.assertEqual(tree.get_children(NODE_SECTION_PLANES), (legacy_node,))
                self.assertEqual(tree.item(legacy_node, "text"), "[V] Section Plane 1")
                self.assertEqual(window.viewport.scene_calls[-1]["section_planes"], planes)
                self.assertEqual(
                    window.viewport.scene_calls[-1]["active_section_plane_id"],
                    legacy_plane.id,
                )
        finally:
            window.root.destroy()

    def test_open_project_with_empty_section_planes_uses_legacy_section_fallback(self) -> None:
        mesh = FakeMesh()

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        class RecordingProgressDialog:
            def __init__(self, _parent: object, _file_name: str) -> None:
                return None

            def update_stage(self, _stage: str) -> None:
                return None

            def close(self) -> None:
                return None

        try:
            with TemporaryDirectory() as tmpdir:
                mesh_path = Path(tmpdir) / "sample.stl"
                project_path = Path(tmpdir) / "empty-planes.openretop"
                project = default_project_data()
                project.name = "Empty Planes"
                project.mesh_path = str(mesh_path)
                project.section.axis = "X"
                project.section.offset = 0.75
                project.section.show_plane = True
                project.section_planes = []
                project.active_section_plane_id = "missing-plane"
                save_project(project, project_path)
                metadata = MeshMetadata(
                    file_path=mesh_path,
                    file_name="sample.stl",
                    extension=".stl",
                    vertex_count=3,
                    triangle_count=1,
                    had_vertex_normals=True,
                    had_triangle_normals=True,
                    computed_vertex_normals=False,
                    computed_triangle_normals=False,
                )

                with (
                    patch("app.main_window.LoadProgressDialog", RecordingProgressDialog),
                    patch(
                        "app.main_window.filedialog.askopenfilename",
                        return_value=str(project_path),
                    ),
                    patch(
                        "app.main_window.load_mesh",
                        return_value=LoadedMesh(mesh=mesh, metadata=metadata),
                    ),
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(1)

                show_error.assert_not_called()
                planes = window.app_state.section_collection.planes
                self.assertEqual(len(planes), 1)
                fallback_plane = planes[0]
                self.assertEqual(fallback_plane.name, "Section Plane 1")
                self.assertEqual(fallback_plane.axis, "X")
                self.assertEqual(fallback_plane.offset, 0.75)
                self.assertTrue(fallback_plane.visible)
                self.assertTrue(fallback_plane.selected)
                self.assertEqual(window.app_state.section_collection.active_plane_id, fallback_plane.id)
                self.assertEqual(window.section_axis.get(), "X")
                self.assertEqual(window.section_offset.get(), 0.75)
                self.assertTrue(window.show_section_plane.get())
        finally:
            window.root.destroy()

    def test_open_project_with_invalid_active_section_plane_selects_first_plane(self) -> None:
        mesh = FakeMesh()

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        class RecordingProgressDialog:
            def __init__(self, _parent: object, _file_name: str) -> None:
                return None

            def update_stage(self, _stage: str) -> None:
                return None

            def close(self) -> None:
                return None

        try:
            with TemporaryDirectory() as tmpdir:
                mesh_path = Path(tmpdir) / "sample.stl"
                project_path = Path(tmpdir) / "invalid-active.openretop"
                project = default_project_data()
                project.name = "Invalid Active"
                project.mesh_path = str(mesh_path)
                project.section_planes = [
                    ProjectSectionPlane(
                        id="plane-a",
                        name="",
                        axis="Z",
                        offset=0.25,
                        visible=True,
                    ),
                    ProjectSectionPlane(
                        id="plane-b",
                        name="Section Plane 1",
                        axis="X",
                        offset=0.5,
                        visible=False,
                    ),
                    ProjectSectionPlane(
                        id="plane-c",
                        name="Custom",
                        axis="Y",
                        offset=0.75,
                        visible=True,
                    ),
                    ProjectSectionPlane(
                        id="plane-d",
                        name="Custom",
                        axis="Y",
                        offset=1.0,
                        visible=True,
                    ),
                ]
                project.active_section_plane_id = "missing-plane"
                save_project(project, project_path)
                metadata = MeshMetadata(
                    file_path=mesh_path,
                    file_name="sample.stl",
                    extension=".stl",
                    vertex_count=3,
                    triangle_count=1,
                    had_vertex_normals=True,
                    had_triangle_normals=True,
                    computed_vertex_normals=False,
                    computed_triangle_normals=False,
                )

                with (
                    patch("app.main_window.LoadProgressDialog", RecordingProgressDialog),
                    patch(
                        "app.main_window.filedialog.askopenfilename",
                        return_value=str(project_path),
                    ),
                    patch(
                        "app.main_window.load_mesh",
                        return_value=LoadedMesh(mesh=mesh, metadata=metadata),
                    ),
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(1)

                show_error.assert_not_called()
                planes = window.app_state.section_collection.planes
                self.assertEqual([plane.id for plane in planes], ["plane-a", "plane-b", "plane-c", "plane-d"])
                self.assertEqual(
                    [plane.name for plane in planes],
                    ["Section Plane 1", "Section Plane 2", "Custom", "Custom 2"],
                )
                self.assertEqual(window.app_state.section_collection.active_plane_id, "plane-a")
                self.assertTrue(planes[0].selected)
                self.assertFalse(planes[1].selected)
                self.assertEqual(window.section_axis.get(), "Z")
                self.assertEqual(window.section_offset.get(), 0.25)
                self.assertTrue(window.show_section_plane.get())

                tree = window.scene_browser.tree
                nodes = tuple(section_plane_node_id(plane.id) for plane in planes)
                self.assertEqual(tree.get_children(NODE_SECTION_PLANES), nodes)
                self.assertEqual(tree.item(nodes[0], "text"), "[V] Section Plane 1")
                self.assertEqual(tree.item(nodes[1], "text"), "[H] Section Plane 2")
                self.assertEqual(tree.item(nodes[2], "text"), "[V] Custom")
                self.assertEqual(tree.item(nodes[3], "text"), "[V] Custom 2")
                self.assertEqual(window.viewport.scene_calls[-1]["active_section_plane_id"], "plane-a")

                window.select_section_plane()
                self.assertEqual(tree.selection(), (nodes[0],))
        finally:
            window.root.destroy()

    def test_open_project_restores_saved_section_planes(self) -> None:
        mesh = FakeMesh()

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        progress_dialogs: list[object] = []

        class RecordingProgressDialog:
            def __init__(self, _parent: object, file_name: str) -> None:
                self.file_name = file_name
                self.stages: list[str] = []
                self.closed = False
                progress_dialogs.append(self)

            def update_stage(self, stage: str) -> None:
                self.stages.append(stage)

            def close(self) -> None:
                self.closed = True

        try:
            with TemporaryDirectory() as tmpdir:
                mesh_path = Path(tmpdir) / "sample.stl"
                project_path = Path(tmpdir) / "planes.openretop"
                metadata = MeshMetadata(
                    file_path=mesh_path,
                    file_name="sample.stl",
                    extension=".stl",
                    vertex_count=3,
                    triangle_count=1,
                    had_vertex_normals=True,
                    had_triangle_normals=True,
                    computed_vertex_normals=False,
                    computed_triangle_normals=False,
                )
                project = default_project_data()
                project.name = "Restored Section Planes"
                project.mesh_path = str(mesh_path)
                project.section.axis = "Y"
                project.section.offset = 1.25
                project.section.show_plane = True
                project.section_planes = [
                    ProjectSectionPlane(
                        id="plane-a",
                        name="Base Section",
                        axis="Z",
                        offset=0.25,
                        visible=True,
                    ),
                    ProjectSectionPlane(
                        id="plane-b",
                        name="Side Section",
                        axis="X",
                        offset=0.5,
                        visible=False,
                    ),
                ]
                project.active_section_plane_id = "plane-b"
                save_project(project, project_path)

                with (
                    patch("app.main_window.LoadProgressDialog", RecordingProgressDialog),
                    patch(
                        "app.main_window.filedialog.askopenfilename",
                        return_value=str(project_path),
                    ),
                    patch(
                        "app.main_window.load_mesh",
                        return_value=LoadedMesh(mesh=mesh, metadata=metadata),
                    ),
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(1)

                show_error.assert_not_called()
                planes = window.app_state.section_collection.planes
                self.assertEqual(len(planes), 2)
                self.assertEqual([plane.id for plane in planes], ["plane-a", "plane-b"])
                self.assertEqual([plane.name for plane in planes], ["Base Section", "Side Section"])
                self.assertEqual([plane.axis for plane in planes], ["Z", "X"])
                self.assertEqual([plane.offset for plane in planes], [0.25, 0.5])
                self.assertEqual([plane.visible for plane in planes], [True, False])
                self.assertFalse(planes[0].selected)
                self.assertTrue(planes[1].selected)
                self.assertEqual(window.app_state.section_collection.active_plane_id, "plane-b")
                self.assertEqual(window.app_state.section_collection.results, [])
                self.assertIsNone(window.app_state.section_result)
                self.assertEqual(window.section_axis.get(), "X")
                self.assertEqual(window.section_offset.get(), 0.5)
                self.assertEqual(window.section_offset_text.get(), "0.500")
                self.assertFalse(window.show_section_plane.get())
                self.assertEqual(window.section_plane_text.get(), "Section: X = 0.500")

                tree = window.scene_browser.tree
                first_node = section_plane_node_id("plane-a")
                second_node = section_plane_node_id("plane-b")
                self.assertEqual(tree.get_children(NODE_SECTION_PLANES), (first_node, second_node))
                self.assertEqual(tree.item(first_node, "text"), "[V] Base Section")
                self.assertEqual(tree.item(second_node, "text"), "[H] Side Section")

                scene = window.viewport.scene_calls[-1]
                self.assertEqual(scene["section_planes"], planes)
                self.assertEqual(scene["active_section_plane_id"], "plane-b")
                self.assertTrue(scene["show_section_plane"])
                self.assertEqual(scene["section_axis"], "X")
                self.assertEqual(scene["section_offset"], 0.5)
        finally:
            window.root.destroy()

    def test_open_project_restores_saved_curves_and_visibility(self) -> None:
        mesh = FakeMesh()

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        class RecordingProgressDialog:
            def __init__(self, _parent: object, _file_name: str) -> None:
                return None

            def update_stage(self, _stage: str) -> None:
                return None

            def close(self) -> None:
                return None

        try:
            with TemporaryDirectory() as tmpdir:
                mesh_path = Path(tmpdir) / "sample.stl"
                project_path = Path(tmpdir) / "curves.openretop"
                metadata = MeshMetadata(
                    file_path=mesh_path,
                    file_name="sample.stl",
                    extension=".stl",
                    vertex_count=3,
                    triangle_count=1,
                    had_vertex_normals=True,
                    had_triangle_normals=True,
                    computed_vertex_normals=False,
                    computed_triangle_normals=False,
                )
                project = default_project_data()
                project.name = "Restored Curves"
                project.mesh_path = str(mesh_path)
                project.section_planes = [
                    ProjectSectionPlane(
                        id="plane-a",
                        name="Base Section",
                        axis="Z",
                        offset=0.0,
                        visible=True,
                    ),
                    ProjectSectionPlane(
                        id="plane-b",
                        name="Side Section",
                        axis="X",
                        offset=0.5,
                        visible=True,
                    ),
                ]
                project.active_section_plane_id = "plane-a"
                project.curves = [
                    ProjectCurve(
                        id="curve-a",
                        name="Section 1 Curve 1",
                        section_result_id="section-a",
                        plane_id="plane-a",
                        original_points=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                        fitted_points=[
                            [0.0, 0.0, 0.0],
                            [0.5, 0.25, 0.0],
                            [1.0, 0.0, 0.0],
                        ],
                        mean_error=0.05,
                        max_error=0.1,
                        is_closed=False,
                        visible=True,
                    ),
                    ProjectCurve(
                        id="curve-b",
                        name="Section 2 Curve 1",
                        section_result_id="section-b",
                        plane_id="plane-b",
                        original_points=[[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]],
                        fitted_points=[[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]],
                        mean_error=0.0,
                        max_error=0.0,
                        is_closed=False,
                        visible=False,
                    ),
                ]
                project.surfaces = [
                    ProjectSurface(
                        id="surface-a",
                        name="Surface 1",
                        source_curve_ids=["curve-a", "curve-b"],
                        surface_type="placeholder",
                        visible=True,
                        metadata={"curve_count": 2, "source": "visible_curves"},
                    ),
                    ProjectSurface(
                        id="surface-b",
                        name="Missing Curve Surface",
                        source_curve_ids=["missing-curve"],
                        surface_type="placeholder",
                        visible=False,
                        metadata={"curve_count": 1, "source": "selected_curve"},
                    ),
                ]
                save_project(project, project_path)

                with (
                    patch("app.main_window.LoadProgressDialog", RecordingProgressDialog),
                    patch(
                        "app.main_window.filedialog.askopenfilename",
                        return_value=str(project_path),
                    ),
                    patch(
                        "app.main_window.load_mesh",
                        return_value=LoadedMesh(mesh=mesh, metadata=metadata),
                    ),
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(1)

                show_error.assert_not_called()
                curves = window.app_state.curve_collection.curves
                self.assertEqual([curve.id for curve in curves], ["curve-a", "curve-b"])
                self.assertEqual([curve.visible for curve in curves], [True, False])
                self.assertIsNone(window.app_state.curve_collection.active_curve_id)
                self.assertEqual(window.app_state.curve_results, [curves[0]])
                self.assertEqual(window.viewport.scene_calls[-1]["curve_results"], [curves[0]])
                surfaces = window.app_state.surface_collection.surfaces
                self.assertEqual([surface.id for surface in surfaces], ["surface-a", "surface-b"])
                self.assertEqual([surface.visible for surface in surfaces], [True, False])
                self.assertIsNone(window.app_state.surface_collection.active_surface_id)
                self.assertEqual(surfaces[0].metadata["curve_count"], 2)
                self.assertEqual(surfaces[1].metadata["missing_curve_ids"], ["missing-curve"])

                tree = window.scene_browser.tree
                first_curve_node = curve_node_id("curve-a")
                second_curve_node = curve_node_id("curve-b")
                self.assertEqual(
                    tree.get_children(NODE_CURVES),
                    (NODE_CURVE_GROUP_UNASSIGNED,),
                )
                self.assertEqual(
                    tree.get_children(NODE_CURVE_GROUP_UNASSIGNED),
                    (first_curve_node, second_curve_node),
                )
                self.assertEqual(tree.item(first_curve_node, "text"), "[V] Section 1 Curve 1")
                self.assertEqual(tree.item(second_curve_node, "text"), "[H] Section 2 Curve 1")
                self.assertEqual(tree.selection(), ())
                first_surface_node = surface_node_id("surface-a")
                second_surface_node = surface_node_id("surface-b")
                self.assertEqual(
                    tree.get_children(NODE_SURFACES),
                    (first_surface_node, second_surface_node),
                )
                self.assertEqual(tree.item(first_surface_node, "text"), "[V] Surface 1")
                self.assertEqual(tree.item(second_surface_node, "text"), "[H] Missing Curve Surface")

                tree.selection_set(second_curve_node)
                tree.event_generate("<<TreeviewSelect>>")
                window.root.update()
                window.curve_visible.set(True)
                window._on_curve_visibility_changed()

                self.assertTrue(curves[1].visible)
                self.assertEqual(window.app_state.curve_results, curves)
                self.assertEqual(window.viewport.scene_calls[-1]["curve_results"], curves)

                tree.selection_set(second_surface_node)
                tree.event_generate("<<TreeviewSelect>>")
                window.root.update()
                self.assertEqual(window.app_state.selected_item, "surface")
                self.assertEqual(window.surface_name_text.get(), "Missing Curve Surface")
                self.assertEqual(window.surface_type_text.get(), "placeholder")
                self.assertEqual(window.surface_source_curve_count_text.get(), "1")
                self.assertFalse(window.surface_visible.get())
                self.assertIn("missing_curve_ids=['missing-curve']", window.surface_metadata_text.get())
        finally:
            window.root.destroy()

    def test_open_project_missing_mesh_path_reports_error_and_keeps_app_usable(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        progress_dialogs: list[object] = []

        class RecordingProgressDialog:
            def __init__(self, _parent: object, file_name: str) -> None:
                self.file_name = file_name
                self.stages: list[str] = []
                self.closed = False
                progress_dialogs.append(self)

            def update_stage(self, stage: str) -> None:
                self.stages.append(stage)

            def close(self) -> None:
                self.closed = True

        try:
            with TemporaryDirectory() as tmpdir:
                project_path = Path(tmpdir) / "missing-mesh.openretop"
                previous_mesh = SimpleNamespace(name="previous.stl")
                window.app_state.mesh_object = previous_mesh
                project = default_project_data()
                project.name = "Missing Mesh Project"
                project.mesh_path = "missing.stl"
                save_project(project, project_path)

                with (
                    patch("app.main_window.LoadProgressDialog", RecordingProgressDialog),
                    patch(
                        "app.main_window.filedialog.askopenfilename",
                        return_value=str(project_path),
                    ),
                    patch(
                        "app.main_window.load_mesh",
                        side_effect=FileNotFoundError("Mesh file does not exist: missing.stl"),
                    ),
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(1)

                show_error.assert_called_once_with(
                    "Could not open project",
                    "Mesh file does not exist: missing.stl",
                )
                self.assertEqual(window.current_project_path, project_path)
                self.assertIs(window.app_state.mesh_object, previous_mesh)
                self.assertEqual(window.status_text.get(), "Project open failed")
                self.assertEqual(str(window.open_model_button.cget("state")), "normal")
                self.assertEqual(
                    window.file_menu.entrycget(OPEN_MODEL_MENU_INDEX, "state"),
                    "normal",
                )
                self.assertEqual(progress_dialogs[0].stages, [LOAD_PROGRESS_STAGES[0]])
                self.assertTrue(progress_dialogs[0].closed)
        finally:
            window.root.destroy()

    def test_open_project_invalid_file_reports_error_without_changing_project_path(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with TemporaryDirectory() as tmpdir:
                project_path = Path(tmpdir) / "broken.openretop"
                previous_path = Path(tmpdir) / "previous.openretop"
                project_path.write_text("{broken json", encoding="utf-8")
                window.current_project_path = previous_path
                scene_call_count = len(window.viewport.scene_calls)

                with (
                    patch(
                        "app.main_window.filedialog.askopenfilename",
                        return_value=str(project_path),
                    ),
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(1)

                show_error.assert_called_once()
                self.assertEqual(show_error.call_args.args[0], "Could not open project")
                self.assertIn("Invalid project JSON", show_error.call_args.args[1])
                self.assertEqual(window.current_project_path, previous_path)
                self.assertEqual(window.status_text.get(), "Project open failed")
                self.assertEqual(len(window.viewport.scene_calls), scene_call_count)
        finally:
            window.root.destroy()

    def test_save_project_prompts_for_path_and_writes_project_without_mesh(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with TemporaryDirectory() as tmpdir:
                project_path = Path(tmpdir) / "empty.openretop"

                with (
                    patch(
                        "app.main_window.filedialog.asksaveasfilename",
                        return_value=str(project_path),
                    ) as ask_save,
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(2)

                ask_save.assert_called_once()
                show_error.assert_not_called()
                self.assertEqual(window.current_project_path, project_path)
                self.assertFalse(window.project_dirty)
                self.assertEqual(window.root.title(), "openRetop - empty.openretop")
                self.assertEqual(window.status_text.get(), f"Project saved: {project_path}")

                project = load_project(project_path)
                self.assertEqual(project.name, "Untitled Project")
                self.assertIsNone(project.mesh_path)
                self.assertEqual(project.transform.location, [0.0, 0.0, 0.0])
                self.assertEqual(project.transform.rotation, [0.0, 0.0, 0.0])
                self.assertEqual(project.transform.scale, 1.0)
                self.assertEqual(project.transform.origin, [0.0, 0.0, 0.0])
                self.assertEqual(project.display.proxy_quality, "Medium")
                self.assertTrue(project.display.show_grid)
                self.assertTrue(project.display.show_axes)
                self.assertFalse(project.display.show_normals)
                self.assertEqual(project.section.axis, "Z")
                self.assertEqual(project.section.offset, 0.0)
                self.assertFalse(project.section.show_plane)
                self.assertEqual(len(project.section_planes), 1)
                section_plane = project.section_planes[0]
                self.assertEqual(section_plane.name, "Section Plane 1")
                self.assertEqual(section_plane.axis, "Z")
                self.assertEqual(section_plane.offset, 0.0)
                self.assertFalse(section_plane.visible)
                self.assertEqual(project.active_section_plane_id, section_plane.id)
        finally:
            window.root.destroy()

    def test_save_project_overwrites_current_project_path_without_prompting(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with TemporaryDirectory() as tmpdir:
                project_path = Path(tmpdir) / "current.openretop"
                project_path.write_text("old contents", encoding="utf-8")
                window.current_project_path = project_path
                window._set_project_dirty(True)
                window.show_grid.set(False)

                with (
                    patch("app.main_window.filedialog.asksaveasfilename") as ask_save,
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(2)

                ask_save.assert_not_called()
                show_error.assert_not_called()
                self.assertEqual(window.current_project_path, project_path)
                self.assertFalse(window.project_dirty)
                self.assertEqual(window.root.title(), "openRetop - current.openretop")
                self.assertEqual(window.status_text.get(), f"Project saved: {project_path}")
                self.assertFalse(load_project(project_path).display.show_grid)
        finally:
            window.root.destroy()

    def test_save_project_writes_multiple_section_planes_from_collection(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            first_plane = window.app_state.section_collection.planes[0]
            first_plane.name = "Base Section"
            first_plane.axis = "Z"
            first_plane.offset = 0.25
            first_plane.visible = True
            second_plane = SectionPlaneState(
                id="plane-b",
                name="Side Section",
                axis="X",
                offset=-0.5,
                visible=False,
            )
            add_plane(window.app_state.section_collection, second_plane)
            set_active_plane(window.app_state.section_collection, second_plane.id)
            window._sync_section_controls_from_active_plane()

            with TemporaryDirectory() as tmpdir:
                project_path = Path(tmpdir) / "planes.openretop"

                with (
                    patch(
                        "app.main_window.filedialog.asksaveasfilename",
                        return_value=str(project_path),
                    ),
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(2)

                show_error.assert_not_called()
                project = load_project(project_path)
                self.assertEqual(len(project.section_planes), 2)
                self.assertEqual(project.section_planes[0].id, first_plane.id)
                self.assertEqual(project.section_planes[0].name, "Base Section")
                self.assertEqual(project.section_planes[0].axis, "Z")
                self.assertEqual(project.section_planes[0].offset, 0.25)
                self.assertTrue(project.section_planes[0].visible)
                self.assertEqual(project.section_planes[1].id, "plane-b")
                self.assertEqual(project.section_planes[1].name, "Side Section")
                self.assertEqual(project.section_planes[1].axis, "X")
                self.assertEqual(project.section_planes[1].offset, -0.5)
                self.assertFalse(project.section_planes[1].visible)
                self.assertEqual(project.active_section_plane_id, "plane-b")
        finally:
            window.root.destroy()

    def test_save_project_preserves_curve_names_and_visibility(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            window.compute_section()
            first_curve = window.app_state.curve_collection.curves[0]
            window.add_section_plane()
            window.section_axis.set("X")
            window._on_section_axis_changed()
            window._set_section_offset(0.5, clamp=True, refresh=True)
            window.compute_section()
            second_curve = window.app_state.curve_collection.curves[1]

            window.select_curve(first_curve.id)
            window.curve_name_text.set("Rim Curve")
            window._on_curve_name_changed()
            window.select_curve(second_curve.id)
            window.curve_visible.set(False)
            window._on_curve_visibility_changed()

            with TemporaryDirectory() as tmpdir:
                project_path = Path(tmpdir) / "curves.openretop"

                with (
                    patch(
                        "app.main_window.filedialog.asksaveasfilename",
                        return_value=str(project_path),
                    ),
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(2)

                show_error.assert_not_called()
                project = load_project(project_path)
                self.assertEqual([curve.id for curve in project.curves], [first_curve.id, second_curve.id])
                self.assertEqual([curve.name for curve in project.curves], ["Rim Curve", "Section 2 Curve 1"])
                self.assertEqual([curve.visible for curve in project.curves], [True, False])
                self.assertEqual(project.curves[0].section_result_id, first_curve.section_result_id)
                self.assertEqual(project.curves[1].plane_id, second_curve.plane_id)
        finally:
            window.root.destroy()

    def test_save_project_preserves_surface_records(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            window.compute_section()
            source_curve = window.app_state.curve_collection.curves[0]
            _make_curve_closed(source_curve)
            window.select_curve(source_curve.id)
            window.create_surface_from_curves()
            surface = window.app_state.surface_collection.surfaces[0]
            window.surface_visible.set(False)
            window._on_surface_visibility_changed()

            with TemporaryDirectory() as tmpdir:
                project_path = Path(tmpdir) / "surfaces.openretop"

                with (
                    patch(
                        "app.main_window.filedialog.asksaveasfilename",
                        return_value=str(project_path),
                    ),
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(2)

                show_error.assert_not_called()
                project = load_project(project_path)
                self.assertEqual(len(project.surfaces), 1)
                project_surface = project.surfaces[0]
                self.assertEqual(project_surface.id, surface.id)
                self.assertEqual(project_surface.name, "Fill Surface 1")
                self.assertEqual(project_surface.source_curve_ids, [source_curve.id])
                self.assertEqual(project_surface.surface_type, "preview_fill")
                self.assertFalse(project_surface.visible)
                self.assertEqual(project_surface.metadata["curve_count"], 1)
                self.assertEqual(project_surface.metadata["source_curve_count"], 1)
                self.assertEqual(project_surface.metadata["source_curve_names"], [source_curve.name])
                self.assertEqual(project_surface.metadata["source"], "selected_curve")
                self.assertEqual(
                    project_surface.metadata["preview_mode"],
                    "closed_curve_fill",
                )
                self.assertTrue(project_surface.metadata["preview_available"])
                self.assertEqual(
                    project_surface.metadata["preview_reason"],
                    "fan fill preview generated",
                )
                self.assertEqual(
                    project_surface.metadata["preview_warning"],
                    "Fan fill preview may be inaccurate for concave curves",
                )
        finally:
            window.root.destroy()

    def test_undo_and_redo_curve_rename(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.compute_section()
            curve = window.app_state.curve_collection.curves[0]
            original_name = curve.name

            window.select_curve(curve.id)
            window.curve_name_text.set("Rim Curve")
            window._on_curve_name_changed()

            self.assertEqual(curve.name, "Rim Curve")
            self.assertTrue(window.undo_stack.can_undo)
            window.undo()
            self.assertEqual(curve.name, original_name)
            self.assertEqual(window.status_text.get(), "Undid Rename Curve")
            window.redo()
            self.assertEqual(curve.name, "Rim Curve")
            self.assertEqual(window.status_text.get(), "Redid Rename Curve")
        finally:
            window.root.destroy()

    def test_undo_curve_visibility_toggle(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.compute_section()
            curve = window.app_state.curve_collection.curves[0]

            window.select_curve(curve.id)
            window.curve_visible.set(False)
            window._on_curve_visibility_changed()

            self.assertFalse(curve.visible)
            window.undo()
            self.assertTrue(curve.visible)
            self.assertTrue(window.curve_visible.get())
            self.assertEqual(window.status_text.get(), "Undid Toggle Visibility")
            window.redo()
            self.assertFalse(curve.visible)
            self.assertFalse(window.curve_visible.get())
            self.assertEqual(window.status_text.get(), "Redid Toggle Visibility")
        finally:
            window.root.destroy()

    def test_undo_delete_curve_restores_dependent_surface(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            (
                _first_plane,
                _second_plane,
                _first_result,
                _second_result,
                first_curve,
                _second_curve,
                first_surface,
                _second_surface,
            ) = _build_two_section_scene(window)

            window.select_curve(first_curve.id)
            window.delete_selected_curve()

            self.assertNotIn(
                first_curve.id,
                [curve.id for curve in window.app_state.curve_collection.curves],
            )
            self.assertNotIn(
                first_surface.id,
                [surface.id for surface in window.app_state.surface_collection.surfaces],
            )
            window.undo()
            self.assertIn(
                first_curve.id,
                [curve.id for curve in window.app_state.curve_collection.curves],
            )
            self.assertIn(
                first_surface.id,
                [surface.id for surface in window.app_state.surface_collection.surfaces],
            )
            self.assertEqual(window.status_text.get(), "Undid Delete Curve")
            window.redo()
            self.assertNotIn(
                first_curve.id,
                [curve.id for curve in window.app_state.curve_collection.curves],
            )
            self.assertNotIn(
                first_surface.id,
                [surface.id for surface in window.app_state.surface_collection.surfaces],
            )
            self.assertEqual(window.status_text.get(), "Redid Delete Curve")
        finally:
            window.root.destroy()

    def test_undo_delete_surface_restores_surface(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            (
                _first_plane,
                _second_plane,
                _first_result,
                _second_result,
                _first_curve,
                _second_curve,
                first_surface,
                _second_surface,
            ) = _build_two_section_scene(window)

            window.select_surface(first_surface.id)
            window.delete_selected_surface()

            self.assertNotIn(
                first_surface.id,
                [surface.id for surface in window.app_state.surface_collection.surfaces],
            )
            window.undo()
            self.assertIn(
                first_surface.id,
                [surface.id for surface in window.app_state.surface_collection.surfaces],
            )
            self.assertEqual(window.status_text.get(), "Undid Delete Surface")
            window.redo()
            self.assertNotIn(
                first_surface.id,
                [surface.id for surface in window.app_state.surface_collection.surfaces],
            )
            self.assertEqual(window.status_text.get(), "Redid Delete Surface")
        finally:
            window.root.destroy()

    def test_undo_create_surface_removes_preview_and_redo_restores_it(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.compute_section()
            source_curve = window.app_state.curve_collection.curves[0]
            _make_curve_closed(source_curve)
            window.select_curve(source_curve.id)

            window.fill_closed_curve()
            surface_id = window.app_state.surface_collection.surfaces[0].id

            self.assertTrue(window.undo_stack.can_undo)
            window.undo()
            self.assertEqual(window.app_state.surface_collection.surfaces, [])
            self.assertEqual(window.status_text.get(), "Undid Create Surface")
            window.redo()
            self.assertEqual(
                [surface.id for surface in window.app_state.surface_collection.surfaces],
                [surface_id],
            )
            self.assertEqual(window.status_text.get(), "Redid Create Surface")
        finally:
            window.root.destroy()

    def test_create_brep_face_from_closed_curve_stores_runtime_object_and_undoes(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.compute_section()
            source_curve = window.app_state.curve_collection.curves[0]
            _make_curve_closed(source_curve)
            window.select_curve(source_curve.id)
            window._set_project_dirty(False)

            cad_object = object()
            result = CadBuildResult(
                success=True,
                cad_object=cad_object,
                reason="created",
                metadata={
                    "brep_type": "planar_face",
                    "backend": "FakeCAD",
                    "build_method": "closed_wire_planar_face",
                    "source_point_count": 4,
                    "planarity_error": 0.0,
                },
            )
            with patch("app.main_window.build_planar_face_from_curve", return_value=result):
                window.surfaces_menu.invoke(2)

            surfaces = window.app_state.brep_surface_collection.surfaces
            self.assertEqual(len(surfaces), 1)
            surface = surfaces[0]
            self.assertEqual(surface.name, "BREP Face 1")
            self.assertEqual(surface.brep_type, "planar_face")
            self.assertEqual(surface.backend, "FakeCAD")
            self.assertEqual(surface.source_curve_ids, [source_curve.id])
            self.assertEqual(surface.metadata["source_curve_ids"], [source_curve.id])
            self.assertEqual(surface.metadata["source_curve_names"], [source_curve.name])
            self.assertEqual(surface.metadata["build_method"], "closed_wire_planar_face")
            self.assertEqual(window._brep_runtime_cache[surface.id], cad_object)
            self.assertEqual(window.app_state.brep_surface_collection.active_surface_id, surface.id)
            self.assertEqual(window.app_state.brep_surface_collection.selected_surface_ids, {surface.id})
            self.assertEqual(window.app_state.selected_item, "surface")
            self.assertEqual(
                window.status_text.get(),
                f"Created BREP planar face from {source_curve.name}.",
            )
            self.assertTrue(window.project_dirty)

            surface_node = surface_node_id(surface.id)
            tree = window.scene_browser.tree
            self.assertIn(surface_node, tree.get_children(NODE_BREP_SURFACES))
            self.assertEqual(tree.item(surface_node, "text"), "[V] BREP Face 1 (curve, planar)")
            self.assertEqual(tree.selection(), (surface_node,))

            with TemporaryDirectory() as tmpdir:
                step_path = Path(tmpdir) / "brep-face.step"
                with (
                    patch(
                        "app.main_window.filedialog.asksaveasfilename",
                        return_value=str(step_path),
                    ) as ask_save,
                    patch(
                        "app.main_window.export_step",
                        return_value=StepExportResult(
                            success=True,
                            path=str(step_path),
                            reason="STEP exported.",
                        ),
                    ) as export_step_fn,
                ):
                    window.surfaces_menu.invoke(4)

                ask_save.assert_called_once()
                export_step_fn.assert_called_once_with(cad_object, step_path)
                self.assertEqual(surface.metadata["last_export_path"], str(step_path))
                self.assertEqual(window.status_text.get(), f"Exported STEP: {step_path}")

            window.undo()
            self.assertEqual(window.app_state.brep_surface_collection.surfaces, [])
            self.assertNotIn(surface.id, window._brep_runtime_cache)
            self.assertEqual(window.status_text.get(), "Undid Create BREP Surface")

            window.redo()
            self.assertEqual(
                [surface.id for surface in window.app_state.brep_surface_collection.surfaces],
                [surface.id],
            )
            self.assertEqual(window._brep_runtime_cache[surface.id], cad_object)
            self.assertEqual(window.status_text.get(), "Redid Create BREP Surface")
        finally:
            window.root.destroy()

    def test_create_brep_loft_from_two_curves_stores_record_and_runtime_cache(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            first_curve = StoredCurve(
                id="curve-loft-a",
                name="Loft A",
                section_result_id="",
                plane_id="",
                original_points=np.asarray(
                    [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                    dtype=float,
                ),
                fitted_points=np.asarray(
                    [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                    dtype=float,
                ),
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
            )
            second_curve = StoredCurve(
                id="curve-loft-b",
                name="Loft B",
                section_result_id="",
                plane_id="",
                original_points=np.asarray(
                    [[0.0, 0.0, 1.0], [1.0, 0.0, 1.0]],
                    dtype=float,
                ),
                fitted_points=np.asarray(
                    [[0.0, 0.0, 1.0], [1.0, 0.0, 1.0]],
                    dtype=float,
                ),
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
            )
            add_curve(window.app_state.curve_collection, first_curve)
            add_curve(window.app_state.curve_collection, second_curve)
            window.select_curves(
                [first_curve.id, second_curve.id],
                active_curve_id=second_curve.id,
            )

            cad_object = object()
            result = CadBuildResult(
                success=True,
                cad_object=cad_object,
                reason="created",
                warnings=["point counts differ"],
                metadata={
                    "brep_type": "loft_surface",
                    "backend": "FakeCAD",
                    "build_method": "two_curve_loft",
                    "source_curve_ids": [first_curve.id, second_curve.id],
                    "source_curve_names": [first_curve.name, second_curve.name],
                    "source_point_counts": [2, 2],
                },
            )
            with patch("app.main_window.build_loft_surface_from_curves", return_value=result):
                window.surfaces_menu.invoke(3)

            surfaces = window.app_state.brep_surface_collection.surfaces
            self.assertEqual(len(surfaces), 1)
            surface = surfaces[0]
            self.assertEqual(surface.name, "BREP Loft 1")
            self.assertEqual(surface.brep_type, "loft_surface")
            self.assertEqual(surface.backend, "FakeCAD")
            self.assertEqual(surface.source_curve_ids, [first_curve.id, second_curve.id])
            self.assertEqual(surface.metadata["build_method"], "two_curve_loft")
            self.assertEqual(surface.metadata["warnings"], ["point counts differ"])
            self.assertEqual(window._brep_runtime_cache[surface.id], cad_object)
            self.assertEqual(window.status_text.get(), "Created BREP loft surface from 2 curves.")

            surface_node = surface_node_id(surface.id)
            self.assertIn(
                surface_node,
                window.scene_browser.tree.get_children(NODE_BREP_SURFACES),
            )
            self.assertEqual(
                window.scene_browser.tree.item(surface_node, "text"),
                "[V] BREP Loft 1 (loft)",
            )

            rebuilt_cad_object = object()
            rebuild_result = CadBuildResult(
                success=True,
                cad_object=rebuilt_cad_object,
                reason="rebuilt",
                metadata={
                    "brep_type": "loft_surface",
                    "backend": "FakeCAD",
                    "build_method": "two_curve_loft",
                    "source_curve_ids": [first_curve.id, second_curve.id],
                },
            )
            window._brep_runtime_cache.pop(surface.id)
            with patch("app.main_window.build_loft_surface_from_curves", return_value=rebuild_result):
                window.surfaces_menu.invoke(5)

            self.assertEqual(window._brep_runtime_cache[surface.id], rebuilt_cad_object)
            self.assertEqual(surface.metadata["runtime_status"], "ready")
            self.assertEqual(surface.metadata["build_reason"], "rebuilt")
            self.assertEqual(window.status_text.get(), "Rebuilt BREP surface.")

            window.delete_selected_surface()
            self.assertEqual(window.app_state.brep_surface_collection.surfaces, [])
            self.assertNotIn(surface.id, window._brep_runtime_cache)

            window.undo()
            self.assertEqual(
                [restored.id for restored in window.app_state.brep_surface_collection.surfaces],
                [surface.id],
            )
            self.assertEqual(window._brep_runtime_cache[surface.id], cad_object)
        finally:
            window.root.destroy()

    def test_create_region_brep_requires_mesh_and_active_region(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            window.create_brep_face_from_selected_region()
            self.assertEqual(
                window.status_text.get(),
                "Load a mesh before creating BREP from region.",
            )

            _load_sample_model(window)
            window.create_brep_face_from_selected_region()
            self.assertEqual(window.status_text.get(), "Select a region first.")
            self.assertEqual(window.app_state.brep_surface_collection.surfaces, [])
        finally:
            window.root.destroy()

    def test_create_and_rebuild_region_brep_preserves_lineage(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.app_state.mesh_object.display_mesh = TriangleMeshData(
                vertices=np.asarray(
                    [
                        [0.0, 0.0, 0.01],
                        [2.0, 0.0, -0.01],
                        [2.0, 1.0, 0.02],
                        [0.0, 1.0, -0.02],
                    ],
                    dtype=float,
                ),
                triangles=np.asarray([[0, 1, 2], [0, 2, 3]], dtype=int),
            )
            region = RegionSelection(
                id="region-plane",
                name="Cheek",
                triangle_indices=(0, 1),
                source_mesh_identifier="sample.stl",
                source_mesh_name="sample.stl",
            )
            window.app_state.region_collection.set_active(region)

            cad_object = object()
            create_result = CadBuildResult(
                success=True,
                cad_object=cad_object,
                reason="created",
                metadata={
                    "brep_type": "planar_face",
                    "backend": "FakeCAD",
                    "build_method": "closed_wire_planar_face",
                },
            )
            with (
                patch("app.main_window.is_cad_kernel_available", return_value=True),
                patch(
                    "app.main_window.build_planar_face_from_curve",
                    return_value=create_result,
                ) as build_face,
            ):
                window.create_brep_face_from_selected_region()

            build_input = build_face.call_args.args[0]
            self.assertTrue(build_input.is_closed)
            self.assertEqual(build_input.points.shape, (4, 3))
            surfaces = window.app_state.brep_surface_collection.surfaces
            self.assertEqual(len(surfaces), 1)
            surface = surfaces[0]
            self.assertEqual(surface.name, "Region Plane 1")
            self.assertEqual(surface.source_curve_ids, [build_input.curve_id])
            self.assertEqual(surface.metadata["creation_type"], "region_plane_fit_brep")
            self.assertEqual(surface.metadata["source_region_id"], region.id)
            self.assertEqual(surface.metadata["source_region_triangle_count"], 2)
            self.assertEqual(surface.metadata["boundary_point_count"], 4)
            self.assertIn("plane_fit_rms_error", surface.metadata)
            self.assertIn("plane_fit_max_error", surface.metadata)
            self.assertEqual(
                surface.metadata["cad_build_method"],
                "region_boundary_projected_to_best_fit_plane",
            )
            self.assertEqual(window._brep_runtime_cache[surface.id], cad_object)
            self.assertEqual(window.brep_source_text.get(), "region")

            boundary_curve = window.app_state.curve_collection.curves[0]
            self.assertEqual(boundary_curve.name, "Cheek Boundary")
            self.assertEqual(boundary_curve.metadata["creation_type"], "region_boundary")
            surface_node = surface_node_id(surface.id)
            self.assertEqual(
                window.scene_browser.tree.item(surface_node, "text"),
                "[V] Region Plane 1 (region, planar)",
            )

            window.app_state.region_collection.clear()
            window._brep_runtime_cache.clear()
            rebuilt_object = object()
            rebuild_result = CadBuildResult(
                success=True,
                cad_object=rebuilt_object,
                reason="rebuilt",
                metadata={"backend": "FakeCAD", "brep_type": "planar_face"},
            )
            with patch(
                "app.main_window.build_planar_face_from_curve",
                return_value=rebuild_result,
            ):
                window.rebuild_selected_brep_surface()

            self.assertEqual(window._brep_runtime_cache[surface.id], rebuilt_object)
            self.assertEqual(
                window.status_text.get(),
                "Rebuilt BREP planar face from region metadata.",
            )
        finally:
            window.root.destroy()

    def test_rebuild_region_brep_fails_when_sources_are_missing(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            surface = BrepSurfaceRecord(
                id="brep-region-missing",
                name="Region Plane 1",
                source_curve_ids=["missing-boundary"],
                brep_type="planar_face",
                backend="FakeCAD",
                metadata={
                    "creation_type": "region_plane_fit_brep",
                    "source_region_id": "missing-region",
                    "boundary_curve_id": "missing-boundary",
                },
            )
            add_brep_surface(window.app_state.brep_surface_collection, surface)
            window.select_surface(surface.id)

            window.rebuild_selected_brep_surface()

            self.assertEqual(
                window.status_text.get(),
                "Cannot rebuild BREP: missing source region and boundary curve.",
            )
            self.assertNotIn(surface.id, window._brep_runtime_cache)
        finally:
            window.root.destroy()

    def test_brep_surface_command_failure_does_not_create_record_or_dirty_project(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.compute_section()
            source_curve = window.app_state.curve_collection.curves[0]
            _make_curve_closed(source_curve)
            window.select_curve(source_curve.id)
            window._set_project_dirty(False)

            result = CadBuildResult(
                success=False,
                cad_object=None,
                reason="CAD backend rejected the curve.",
            )
            with patch("app.main_window.build_planar_face_from_curve", return_value=result):
                window.create_brep_face_from_closed_curve()

            self.assertEqual(window.app_state.brep_surface_collection.surfaces, [])
            self.assertEqual(window._brep_runtime_cache, {})
            self.assertEqual(window.status_text.get(), "CAD backend rejected the curve.")
            self.assertFalse(window.project_dirty)
        finally:
            window.root.destroy()

    def test_undo_stack_clears_on_new_project_and_model_load(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.select_model()
            window.mesh_name_text.set("Renamed Mesh")
            window._on_mesh_name_changed()
            self.assertTrue(window.undo_stack.can_undo)

            with patch("app.main_window.messagebox.askyesnocancel", return_value=False):
                window.new_project()

            self.assertFalse(window.undo_stack.can_undo)
            self.assertFalse(window.undo_stack.can_redo)

            _load_sample_model(window)
            window.select_model()
            window.mesh_name_text.set("Second Rename")
            window._on_mesh_name_changed()
            self.assertTrue(window.undo_stack.can_undo)

            _load_sample_model(window)

            self.assertFalse(window.undo_stack.can_undo)
            self.assertFalse(window.undo_stack.can_redo)
        finally:
            window.root.destroy()

    def test_save_project_preserves_global_renames_and_mesh_visibility(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            window.select_model()
            window.mesh_name_text.set("Scan Body")
            window._on_mesh_name_changed()
            window.mesh_visible.set(False)
            window._on_mesh_visibility_changed()
            active_plane = window.app_state.section_collection.planes[0]
            window.select_section_plane(active_plane.id)
            window.section_plane_name_text.set("Cut Plane")
            window._on_section_plane_name_changed()
            window.compute_section()
            stored_result = window.app_state.section_collection.results[0]
            source_curve = window.app_state.curve_collection.curves[0]
            window.select_section_result(stored_result.id)
            window.section_result_name_text.set("Rim Section")
            window._on_section_result_name_changed()
            window.select_curve(source_curve.id)
            window.curve_name_text.set("Rim Curve")
            window._on_curve_name_changed()
            _make_curve_closed(source_curve)
            window.create_surface_from_curves()
            surface = window.app_state.surface_collection.surfaces[0]
            window.surface_name_text.set("Preview Surface")
            window._on_surface_name_changed()

            with TemporaryDirectory() as tmpdir:
                project_path = Path(tmpdir) / "renamed.openretop"

                with (
                    patch(
                        "app.main_window.filedialog.asksaveasfilename",
                        return_value=str(project_path),
                    ),
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(2)

                show_error.assert_not_called()
                project = load_project(project_path)
                self.assertEqual(project.mesh_path, str(metadata.file_path))
                self.assertEqual(project.mesh_name, "Scan Body")
                self.assertFalse(project.mesh_visible)
                self.assertEqual(project.section_planes[0].name, "Cut Plane")
                self.assertEqual(project.section_results[0].name, "Rim Section")
                self.assertEqual(project.section_results[0].id, stored_result.id)
                self.assertEqual(project.curves[0].name, "Rim Curve")
                self.assertEqual(project.surfaces[0].name, "Preview Surface")
                self.assertEqual(project.surfaces[0].id, surface.id)
        finally:
            window.root.destroy()

    def test_save_project_as_writes_loaded_mesh_transform_and_settings(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            mesh_path = Path("sample.stl")
            window.app_state.mesh_object = SimpleNamespace(
                file_path=mesh_path,
                location=np.asarray([1.0, 2.0, 3.0], dtype=float),
                rotation=np.asarray([10.0, 20.0, 30.0], dtype=float),
                scale=1.75,
                origin=np.asarray([0.5, 0.25, 0.0], dtype=float),
            )
            window.proxy_quality.set("High")
            window.show_grid.set(False)
            window.show_axes.set(False)
            window.show_normals.set(True)
            window.section_axis.set("X")
            window.section_offset.set(0.5)
            window.show_section_plane.set(True)

            with TemporaryDirectory() as tmpdir:
                project_path = Path(tmpdir) / "mesh.openretop"

                with (
                    patch(
                        "app.main_window.filedialog.asksaveasfilename",
                        return_value=str(project_path),
                    ) as ask_save,
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.file_menu.invoke(3)

                ask_save.assert_called_once()
                show_error.assert_not_called()
                self.assertEqual(window.current_project_path, project_path)
                self.assertFalse(window.project_dirty)
                self.assertEqual(window.root.title(), "openRetop - mesh.openretop")
                self.assertEqual(window.status_text.get(), f"Project saved: {project_path}")

                project = load_project(project_path)
                self.assertEqual(project.mesh_path, str(mesh_path))
                self.assertEqual(project.transform.location, [1.0, 2.0, 3.0])
                self.assertEqual(project.transform.rotation, [10.0, 20.0, 30.0])
                self.assertEqual(project.transform.scale, 1.75)
                self.assertEqual(project.transform.origin, [0.5, 0.25, 0.0])
                self.assertEqual(project.display.proxy_quality, "High")
                self.assertFalse(project.display.show_grid)
                self.assertFalse(project.display.show_axes)
                self.assertFalse(project.display.show_normals)
                self.assertEqual(project.section.axis, "X")
                self.assertEqual(project.section.offset, 0.5)
                self.assertTrue(project.section.show_plane)
                self.assertEqual(len(project.section_planes), 1)
                section_plane = project.section_planes[0]
                self.assertEqual(section_plane.name, "Section Plane 1")
                self.assertEqual(section_plane.axis, "X")
                self.assertEqual(section_plane.offset, 0.5)
                self.assertTrue(section_plane.visible)
                self.assertEqual(project.active_section_plane_id, section_plane.id)
        finally:
            window.root.destroy()

    def test_save_project_failure_reports_error(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            window.current_project_path = Path("broken.openretop")

            with (
                patch("app.main_window.save_project", side_effect=OSError("disk full")),
                patch("app.main_window.messagebox.showerror") as show_error,
            ):
                window.file_menu.invoke(2)

            show_error.assert_called_once_with("Could not save project", "disk full")
            self.assertEqual(window.status_text.get(), "Project save failed")
        finally:
            window.root.destroy()

    def test_dirty_close_cancel_keeps_window_open(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            window._set_project_dirty(True)

            with (
                patch("app.main_window.messagebox.askyesnocancel", return_value=None) as prompt,
                patch.object(window.root, "destroy") as destroy,
            ):
                window._on_exit()

            prompt.assert_called_once()
            destroy.assert_not_called()
            self.assertFalse(window.viewport.closed)
            self.assertTrue(window.project_dirty)
            self.assertEqual(window.root.title(), "openRetop - Untitled Project *")
        finally:
            window.root.destroy()

    def test_dirty_close_dont_save_closes_without_saving(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            window._set_project_dirty(True)

            with (
                patch("app.main_window.messagebox.askyesnocancel", return_value=False) as prompt,
                patch.object(window.root, "destroy") as destroy,
                patch("app.main_window.save_project") as save_project_fn,
            ):
                window._on_exit()

            prompt.assert_called_once()
            save_project_fn.assert_not_called()
            destroy.assert_called_once()
            self.assertTrue(window.viewport.closed)
        finally:
            window.root.destroy()

    def test_dirty_close_save_writes_project_then_closes(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with TemporaryDirectory() as tmpdir:
                project_path = Path(tmpdir) / "closing.openretop"
                window.current_project_path = project_path
                window._set_project_dirty(True)

                with (
                    patch("app.main_window.messagebox.askyesnocancel", return_value=True) as prompt,
                    patch.object(window.root, "destroy") as destroy,
                ):
                    window._on_exit()

                prompt.assert_called_once()
                destroy.assert_called_once()
                self.assertTrue(window.viewport.closed)
                self.assertFalse(window.project_dirty)
                self.assertEqual(window.root.title(), "openRetop - closing.openretop")
                self.assertTrue(project_path.exists())
                self.assertEqual(load_project(project_path).name, "Untitled Project")
        finally:
            window.root.destroy()

    def test_tools_menu_commands_keep_existing_no_selection_behavior(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            window.tools_menu.invoke(0)
            self.assertEqual(window.status_text.get(), "No selection")
            window.tools_menu.invoke(1)
            self.assertEqual(window.status_text.get(), "No selection")
            window.tools_menu.invoke(2)
            self.assertEqual(window.status_text.get(), "No selection")
            window.tools_menu.invoke(3)
            self.assertEqual(window.status_text.get(), "No selection")
            window.tools_menu.invoke(5)
            self.assertEqual(window.status_text.get(), "Region selection requires a loaded mesh.")
            window.sections_menu.invoke(0)
            self.assertEqual(window.status_text.get(), "No selection")
            window.sections_menu.invoke(2)
            self.assertEqual(window.status_text.get(), "No selection")
            window.sections_menu.invoke(3)
            self.assertEqual(window.status_text.get(), "Section cleared")
            window.sections_menu.invoke(4)
            self.assertEqual(window.status_text.get(), "All section results cleared")
            window.sections_menu.invoke(1)
            self.assertEqual(window.status_text.get(), "No selection")
            window.curves_menu.invoke(1)
            self.assertEqual(window.status_text.get(), "Select at least two curves to join")
            window.curves_menu.invoke(2)
            self.assertEqual(window.status_text.get(), "Select exactly one open curve to auto-close")
            window.curves_menu.invoke(3)
            self.assertEqual(window.status_text.get(), "No selected curves")
            window.curves_menu.invoke(4)
            self.assertEqual(window.status_text.get(), "No selected curves")
            window.curves_menu.invoke(5)
            self.assertEqual(window.status_text.get(), "No curves available")
            window.curves_menu.invoke(0)
            self.assertEqual(window.status_text.get(), "No curves available")
            window.curves_menu.invoke(10)
            self.assertEqual(window.status_text.get(), "Select exactly one curve to simplify")
            window.curves_menu.invoke(11)
            self.assertEqual(window.status_text.get(), "Select exactly one curve to smooth")
            window.curves_menu.invoke(12)
            self.assertEqual(window.status_text.get(), "Load a mesh before projecting curves.")
            window.curves_menu.invoke(13)
            self.assertEqual(window.status_text.get(), "Select one curve to rebuild.")
            window.curves_menu.invoke(15)
            self.assertEqual(window.status_text.get(), "Load a mesh to use Manual Curve")
            window.curves_menu.invoke(17)
            self.assertEqual(window.status_text.get(), "Load a mesh to use Snap to Mesh")
            window.surfaces_menu.invoke(0)
            self.assertEqual(window.status_text.get(), "No curves available")
            window.surfaces_menu.invoke(1)
            self.assertEqual(window.status_text.get(), "No curves available")
            window.surfaces_menu.invoke(2)
            self.assertEqual(window.status_text.get(), "No curves available")
            window.surfaces_menu.invoke(3)
            self.assertEqual(window.status_text.get(), "No curves available")
            window.surfaces_menu.invoke(4)
            self.assertEqual(window.status_text.get(), "Select a BREP surface to export.")
            window.surfaces_menu.invoke(5)
            self.assertEqual(window.status_text.get(), "Select a BREP surface to rebuild.")
            window.surfaces_menu.invoke(6)
            self.assertEqual(window.status_text.get(), "No curves available")
            window.surfaces_menu.invoke(7)
            self.assertEqual(window.status_text.get(), "No curves available")
            window.surfaces_menu.invoke(8)
            self.assertEqual(window.status_text.get(), "No curves available")
            window.surfaces_menu.invoke(9)
            self.assertEqual(window.status_text.get(), "Select a surface first.")
            window.surfaces_menu.invoke(10)
            self.assertEqual(window.status_text.get(), "Select a surface first.")
            window.surfaces_menu.invoke(11)
            self.assertEqual(window.status_text.get(), "Select a surface first.")
            window.surfaces_menu.invoke(12)
            self.assertEqual(window.status_text.get(), "Select a surface first.")
        finally:
            window.root.destroy()

    def test_loading_progress_dialog_contains_visible_indeterminate_progressbar(self) -> None:
        try:
            root = Tk()
        except TclError as exc:
            raise unittest.SkipTest(f"Tk is unavailable: {exc}") from exc

        dialog: LoadProgressDialog | None = None
        try:
            root.geometry("800x600+120+80")
            root.update_idletasks()
            dialog = LoadProgressDialog(root, "sample.stl")
            progress_bars = [
                widget
                for widget in _widget_descendants(dialog.window)
                if widget.winfo_class() == "TProgressbar"
            ]

            self.assertEqual(len(progress_bars), 1)
            self.assertEqual(str(progress_bars[0].cget("mode")), "indeterminate")
            self.assertGreater(int(progress_bars[0].winfo_width()), 1)
            self.assertTrue(progress_bars[0].winfo_ismapped())

            initial_value = float(progress_bars[0].cget("value"))
            dialog.update_stage(LOAD_PROGRESS_STAGES[0])
            self.assertEqual(dialog.stage_text.get(), LOAD_PROGRESS_STAGES[0])
            self.assertNotEqual(float(progress_bars[0].cget("value")), initial_value)
            expected_x = root.winfo_rootx() + (root.winfo_width() - dialog.window.winfo_width()) // 2
            expected_y = root.winfo_rooty() + (root.winfo_height() - dialog.window.winfo_height()) // 2
            self.assertLessEqual(abs(dialog.window.winfo_rootx() - expected_x), 32)
            self.assertLessEqual(abs(dialog.window.winfo_rooty() - expected_y), 32)
        finally:
            if dialog is not None:
                dialog.close()
            root.destroy()

    def test_compute_section_shows_progress_dialog_stages(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        progress_dialogs: list[object] = []

        class RecordingProgressDialog:
            def __init__(self, _parent: object, title: str, summary: str | None = None) -> None:
                self.title = title
                self.summary = summary
                self.stages: list[str] = []
                self.closed = False
                progress_dialogs.append(self)

            def update_stage(self, stage: str) -> None:
                self.stages.append(stage)

            def close(self) -> None:
                self.closed = True

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            with patch("app.main_window.ComputationProgressDialog", RecordingProgressDialog):
                window.compute_section()

            self.assertEqual(len(progress_dialogs), 1)
            progress = progress_dialogs[0]
            self.assertEqual(progress.title, "Computing Section")
            self.assertEqual(progress.stages, list(COMPUTE_SECTION_PROGRESS_STAGES))
            self.assertTrue(progress.closed)
            self.assertTrue(window.app_state.section_collection.results)
            self.assertEqual(window.status_text.get(), "Section computed: Section 1 - 1 segments")
        finally:
            window.root.destroy()

    def test_loading_mesh_starts_with_scene_context_and_keeps_normals_off(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            self.assertEqual(window.file_name_text.get(), "sample.stl")
            self.assertEqual(window.vertex_count_text.get(), "3")
            self.assertEqual(window.triangle_count_text.get(), "1")
            self.assertEqual(window.bbox_size_text.get(), "1, 2, 3")
            self.assertEqual(
                window.status_text.get(),
                "Source: 1 tris | Display: 1 tris | Reduction: 0.0% | "
                "No proxy (Medium) | Full-resolution source preserved",
            )
            self.assertTrue(window.project_dirty)
            self.assertEqual(window.root.title(), "openRetop - Untitled Project *")
            self.assertIsNone(window.app_state.selected_item)
            self.assertEqual(window.current_workbench.get(), "Scene")
            self.assertEqual(window.no_selection_frame.winfo_manager(), "grid")
            self.assertEqual(window.model_context_frame.winfo_manager(), "")
            self.assertEqual(window.section_context_frame.winfo_manager(), "grid")
            self.assertEqual(str(window.select_model_button.cget("state")), "normal")
            self.assertEqual(str(window.select_section_plane_button.cget("state")), "normal")
            self.assertTrue(window.show_grid.get())
            self.assertTrue(window.show_axes.get())
            self.assertFalse(window.show_section_plane.get())
            self.assertFalse(window.show_normals.get())
            self.assertEqual(window.triangle_count_text.get(), "1")
            self.assertEqual(window.display_triangle_count_text.get(), "1")
            self.assertEqual(window.display_reduction_text.get(), "0.0%")
            self.assertEqual(window.display_proxy_text.get(), "Disabled (Medium)")
            self.assertEqual(window.source_retained_text.get(), "Full-resolution source preserved")
            scene = window.viewport.scene_calls[-1]
            self.assertEqual(scene["show_grid"], True)
            self.assertEqual(scene["show_axes"], True)
            self.assertEqual(scene["show_normals"], False)
            self.assertEqual(scene["show_section_plane"], False)
            self.assertEqual(scene["section_axis"], "Z")
            self.assertEqual(scene["section_offset"], 0.0)
            self.assertEqual(scene["section_planes"], window.app_state.section_collection.planes)
            self.assertEqual(
                scene["active_section_plane_id"],
                window.app_state.section_collection.active_plane_id,
            )
            self.assertIsNone(scene["selected_item"])
            self.assertTrue(np.allclose(scene["scene_bounds_min"], [0.0, 0.0, 0.0]))
            self.assertTrue(np.allclose(scene["scene_bounds_max"], [1.0, 2.0, 3.0]))
        finally:
            window.root.destroy()

    def test_scene_browser_syncs_mesh_section_nodes_and_selection(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            tree = window.scene_browser.tree
            active_plane = window.app_state.section_collection.planes[0]
            section_plane_node = section_plane_node_id(active_plane.id)
            self.assertEqual(
                tree.get_children(NODE_SCENE),
                (NODE_MESH, NODE_SECTION_PLANES),
            )
            self.assertEqual(tree.item(NODE_MESH, "text"), "[V] sample.stl")
            self.assertEqual(tree.item(NODE_SECTION_PLANES, "text"), "[H] Section Planes")
            self.assertEqual(tree.get_children(NODE_SECTION_PLANES), (section_plane_node,))
            self.assertEqual(tree.item(section_plane_node, "text"), "[H] Section Plane 1")
            self.assertFalse(tree.exists(NODE_SECTION_RESULTS))
            self.assertFalse(tree.exists(NODE_CURVES))

            tree.selection_set(NODE_MESH)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()
            self.assertEqual(window.app_state.selected_item, "model")
            self.assertEqual(window.status_text.get(), "Selected: sample.stl")
            self.assertEqual(tree.selection(), (NODE_MESH,))

            tree.selection_set(section_plane_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()
            self.assertEqual(window.app_state.selected_item, "section_plane")
            self.assertEqual(window.status_text.get(), "Selected: Section Plane")
            self.assertEqual(tree.selection(), (section_plane_node,))

            window._on_viewport_selection("model")
            self.assertEqual(window.app_state.selected_item, "model")
            self.assertEqual(tree.selection(), (NODE_MESH,))

            window._on_viewport_selection("section_plane")
            self.assertEqual(window.app_state.selected_item, "section_plane")
            self.assertEqual(tree.selection(), (section_plane_node,))

            window.compute_section()
            stored_result = window.app_state.section_collection.results[0]
            stored_curve = window.app_state.curve_collection.curves[0]
            section_result_node = section_result_node_id(stored_result.id)
            section_curve_group = curve_group_node_id(stored_result.id)
            curve_node = curve_node_id(stored_curve.id)
            self.assertEqual(section_result_id_from_node(section_result_node), stored_result.id)
            self.assertEqual(
                tree.get_children(NODE_SCENE),
                (
                    NODE_MESH,
                    NODE_SECTION_PLANES,
                    NODE_SECTION_RESULTS,
                    NODE_CURVES,
                ),
            )
            self.assertEqual(tree.get_children(NODE_SECTION_PLANES), (section_plane_node,))
            self.assertEqual(tree.get_children(NODE_SECTION_RESULTS), (section_result_node,))
            self.assertEqual(tree.item(NODE_SECTION_RESULTS, "text"), "[V] Section Results")
            self.assertEqual(tree.item(section_result_node, "text"), "[V] Section 1")
            self.assertEqual(tree.item(NODE_CURVES, "text"), "[V] Curves")
            self.assertEqual(tree.get_children(NODE_CURVES), (section_curve_group,))
            self.assertEqual(tree.item(section_curve_group, "text"), "[V] Section: Section 1")
            self.assertEqual(tree.get_children(section_curve_group), (curve_node,))
            self.assertEqual(tree.item(curve_node, "text"), "[V] Section 1 Curve 1")

            tree.selection_set(section_result_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()
            self.assertEqual(window.app_state.selected_item, "section_result")
            self.assertEqual(window.app_state.section_collection.active_result_id, stored_result.id)
            self.assertEqual(window.section_result_context_frame.winfo_manager(), "grid")
            self.assertEqual(window.section_result_name_text.get(), "Section 1")
            self.assertEqual(window.section_result_axis_text.get(), "Z")
            self.assertEqual(window.section_result_offset_text.get(), "0.000")
            self.assertEqual(window.section_result_segment_count_text.get(), "1")
            self.assertEqual(window.section_result_curve_count_text.get(), "1")
            self.assertTrue(window.section_result_visible.get())

            window.section_result_visible.set(False)
            window._on_section_result_visibility_changed()
            self.assertFalse(stored_result.visible)
            self.assertIsNone(window.viewport.scene_calls[-1]["section_result"])
            self.assertEqual(tree.item(section_result_node, "text"), "[H] Section 1")
            self.assertEqual(tree.item(NODE_SECTION_RESULTS, "text"), "[H] Section Results")

            window.section_result_visible.set(True)
            window._on_section_result_visibility_changed()
            self.assertTrue(stored_result.visible)
            self.assertIs(window.viewport.scene_calls[-1]["section_result"], stored_result.result)
            self.assertEqual(tree.item(section_result_node, "text"), "[V] Section 1")
            self.assertEqual(tree.item(NODE_SECTION_RESULTS, "text"), "[V] Section Results")

            window.clear_section()
            self.assertEqual(
                tree.get_children(NODE_SCENE),
                (NODE_MESH, NODE_SECTION_PLANES),
            )
            self.assertEqual(tree.get_children(NODE_SECTION_PLANES), (section_plane_node,))
            self.assertFalse(tree.exists(NODE_SECTION_RESULTS))
            self.assertFalse(tree.exists(NODE_CURVES))
        finally:
            window.root.destroy()

    def test_surface_scene_browser_selection_visibility_and_delete(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            window.compute_section()
            source_curve = window.app_state.curve_collection.curves[0]
            first_surface = SurfacePatch(
                id="surface-1",
                name="Patch A",
                source_curve_ids=[source_curve.id],
                surface_type="loft",
                metadata={"degree": 3, "quality": "draft"},
            )
            second_surface = SurfacePatch(
                id="surface-2",
                name="Patch B",
                source_curve_ids=[source_curve.id, "curve-extra"],
                surface_type="patch",
                visible=False,
            )
            add_surface(window.app_state.surface_collection, first_surface)
            add_surface(window.app_state.surface_collection, second_surface)
            window._refresh_scene_browser()

            tree = window.scene_browser.tree
            first_surface_node = surface_node_id(first_surface.id)
            second_surface_node = surface_node_id(second_surface.id)
            self.assertEqual(surface_id_from_node(second_surface_node), second_surface.id)
            self.assertEqual(
                tree.get_children(NODE_SCENE),
                (
                    NODE_MESH,
                    NODE_SECTION_PLANES,
                    NODE_SECTION_RESULTS,
                    NODE_CURVES,
                    NODE_SURFACES,
                ),
            )
            self.assertEqual(tree.item(NODE_SURFACES, "text"), "[M] Preview Surfaces")
            self.assertEqual(
                tree.get_children(NODE_SURFACES),
                (first_surface_node, second_surface_node),
            )
            self.assertEqual(tree.item(first_surface_node, "text"), "[V] Patch A")
            self.assertEqual(tree.item(second_surface_node, "text"), "[H] Patch B")

            tree.selection_set(first_surface_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()

            self.assertEqual(window.app_state.selected_item, "surface")
            self.assertEqual(window.app_state.surface_collection.active_surface_id, first_surface.id)
            self.assertTrue(first_surface.selected)
            self.assertFalse(second_surface.selected)
            self.assertEqual(tree.selection(), (first_surface_node,))
            self.assertEqual(window.current_workbench.get(), "Surfaces")
            self.assertEqual(window.surface_context_frame.winfo_manager(), "grid")
            self.assertEqual(window.no_selection_frame.winfo_manager(), "grid")
            self.assertEqual(window.surface_name_text.get(), "Patch A")
            self.assertEqual(window.surface_type_text.get(), "loft")
            self.assertEqual(window.surface_source_curve_count_text.get(), "1")
            self.assertEqual(window.surface_source_curve_names_text.get(), source_curve.name)
            self.assertEqual(window.surface_preview_available_text.get(), "(unknown)")
            self.assertEqual(window.surface_preview_reason_text.get(), "(none)")
            self.assertEqual(window.surface_preview_warning_text.get(), "(none)")
            self.assertEqual(window.surface_metadata_text.get(), "degree=3, quality=draft")
            self.assertTrue(window.surface_visible.get())

            window._set_project_dirty(False)
            window.surface_visible.set(False)
            window._on_surface_visibility_changed()

            self.assertFalse(first_surface.visible)
            self.assertTrue(window.project_dirty)
            self.assertEqual(window.status_text.get(), "Selected: Patch A")
            self.assertEqual(tree.get_children(NODE_SURFACES), (first_surface_node, second_surface_node))
            self.assertEqual(tree.item(first_surface_node, "text"), "[H] Patch A")
            self.assertEqual(tree.item(NODE_SURFACES, "text"), "[H] Preview Surfaces")

            tree.selection_set(second_surface_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()
            self.assertEqual(window.app_state.surface_collection.active_surface_id, second_surface.id)
            self.assertFalse(first_surface.selected)
            self.assertTrue(second_surface.selected)
            self.assertFalse(window.surface_visible.get())
            self.assertEqual(window.surface_source_curve_count_text.get(), "2")
            self.assertEqual(window.surface_source_curve_names_text.get(), source_curve.name)
            self.assertEqual(window.surface_preview_available_text.get(), "(unknown)")
            self.assertEqual(window.surface_preview_reason_text.get(), "(none)")
            self.assertEqual(window.surface_preview_warning_text.get(), "(none)")
            self.assertEqual(window.surface_metadata_text.get(), "(none)")

            window.delete_selected_surface()

            self.assertEqual(window.app_state.curve_collection.curves, [source_curve])
            self.assertEqual(window.app_state.surface_collection.surfaces, [first_surface])
            self.assertEqual(window.app_state.surface_collection.active_surface_id, first_surface.id)
            self.assertEqual(tree.get_children(NODE_SURFACES), (first_surface_node,))
            self.assertEqual(tree.selection(), (first_surface_node,))
            self.assertEqual(window.status_text.get(), "Deleted: Patch B")
            self.assertEqual(window.app_state.selected_item, "surface")

            window.delete_selected_surface()

            self.assertEqual(window.app_state.curve_collection.curves, [source_curve])
            self.assertEqual(window.app_state.surface_collection.surfaces, [])
            self.assertIsNone(window.app_state.surface_collection.active_surface_id)
            self.assertFalse(tree.exists(NODE_SURFACES))
            self.assertEqual(window.app_state.selected_item, None)
            self.assertEqual(window.status_text.get(), "Deleted: Patch A")
        finally:
            window.root.destroy()

    def test_scene_browser_visibility_commands_hide_show_curves_and_surfaces(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            window.compute_section()
            stored_result = window.app_state.section_collection.results[0]
            source_curve = window.app_state.curve_collection.curves[0]
            surface = SurfacePatch(
                id="surface-1",
                name="Surface 1",
                source_curve_ids=[source_curve.id],
                surface_type="preview_fill",
            )
            add_surface(window.app_state.surface_collection, surface)
            window._refresh_scene_browser()

            tree = window.scene_browser.tree
            curve_node = curve_node_id(source_curve.id)
            surface_node = surface_node_id(surface.id)
            section_result_node = section_result_node_id(stored_result.id)

            window._set_project_dirty(False)
            window._on_scene_browser_visibility(
                "hide_selected",
                (curve_node, surface_node),
            )

            self.assertFalse(source_curve.visible)
            self.assertFalse(surface.visible)
            self.assertTrue(stored_result.visible)
            self.assertEqual(tree.item(curve_node, "text"), "[H] Section 1 Curve 1")
            self.assertEqual(tree.item(surface_node, "text"), "[H] Surface 1 (fill)")
            self.assertEqual(window.app_state.curve_results, [])
            self.assertEqual(window.viewport.scene_calls[-1]["surface_previews"], [])
            self.assertTrue(window.project_dirty)

            window._on_scene_browser_visibility(
                "show_selected",
                (curve_node, surface_node),
            )

            self.assertTrue(source_curve.visible)
            self.assertTrue(surface.visible)
            self.assertEqual(tree.item(curve_node, "text"), "[V] Section 1 Curve 1")
            self.assertEqual(tree.item(surface_node, "text"), "[V] Surface 1 (fill)")

            window._on_scene_browser_visibility("hide_unselected", (curve_node,))

            self.assertTrue(source_curve.visible)
            self.assertFalse(stored_result.visible)
            self.assertFalse(surface.visible)
            self.assertIsNone(window.viewport.scene_calls[-1]["section_result"])
            self.assertEqual(tree.item(section_result_node, "text"), "[H] Section 1")

            window._on_scene_browser_visibility("show_all", ())

            self.assertTrue(source_curve.visible)
            self.assertTrue(stored_result.visible)
            self.assertTrue(surface.visible)
            self.assertIs(window.viewport.scene_calls[-1]["section_result"], stored_result.result)
            self.assertEqual(tree.item(section_result_node, "text"), "[V] Section 1")
            self.assertEqual(tree.item(surface_node, "text"), "[V] Surface 1 (fill)")
        finally:
            window.root.destroy()

    def test_global_rename_updates_scene_browser_and_contexts(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            tree = window.scene_browser.tree
            window.select_model()
            window._set_project_dirty(False)
            window.mesh_name_text.set("Scan Body")
            window._on_mesh_name_changed()

            self.assertEqual(window.app_state.mesh_object.name, "Scan Body")
            self.assertEqual(window.file_name_text.get(), "sample.stl")
            self.assertEqual(window.selected_object_text.get(), "Scan Body")
            self.assertEqual(tree.item(NODE_MESH, "text"), "[V] Scan Body")
            self.assertTrue(window.project_dirty)

            active_plane = window.app_state.section_collection.planes[0]
            window.select_section_plane(active_plane.id)
            window.section_plane_name_text.set("Cut Plane")
            window._on_section_plane_name_changed()

            plane_node = section_plane_node_id(active_plane.id)
            self.assertEqual(active_plane.name, "Cut Plane")
            self.assertEqual(tree.item(plane_node, "text"), "[H] Cut Plane")

            window.compute_section()
            stored_result = window.app_state.section_collection.results[0]
            stored_curve = window.app_state.curve_collection.curves[0]
            result_node = section_result_node_id(stored_result.id)
            curve_group = curve_group_node_id(stored_result.id)
            window.select_section_result(stored_result.id)
            window.section_result_name_text.set("Rim Section")
            window._on_section_result_name_changed()

            self.assertEqual(stored_result.name, "Rim Section")
            self.assertEqual(tree.item(result_node, "text"), "[V] Rim Section")
            self.assertEqual(tree.item(curve_group, "text"), "[V] Section: Rim Section")

            window.select_curve(stored_curve.id)
            self.assertEqual(window.curve_section_text.get(), "Rim Section")
            self.assertEqual(window.curve_plane_text.get(), "Cut Plane (Z = 0.000)")
            window.curve_name_text.set("Rim Curve")
            window._on_curve_name_changed()

            curve_node = curve_node_id(stored_curve.id)
            self.assertEqual(stored_curve.name, "Rim Curve")
            self.assertEqual(tree.item(curve_node, "text"), "[V] Rim Curve")

            _make_curve_closed(stored_curve)
            window.create_surface_from_curves()
            surface = window.app_state.surface_collection.surfaces[0]
            surface_node = surface_node_id(surface.id)
            window.surface_name_text.set("Preview Surface")
            window._on_surface_name_changed()

            self.assertEqual(surface.name, "Preview Surface")
            self.assertEqual(tree.item(surface_node, "text"), "[V] Preview Surface (fill)")
        finally:
            window.root.destroy()

    def test_f2_focuses_selected_object_name_field(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            window.select_model()
            window._handle_shortcut("F2")

            self.assertEqual(window.status_text.get(), "Rename selected object")
            self.assertTrue(window.mesh_name_entry.selection_present())
        finally:
            window.root.destroy()

    def test_section_result_and_curve_group_selection_select_child_curves(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            window.compute_section()
            first_result = window.app_state.section_collection.results[0]
            first_curve = window.app_state.curve_collection.curves[0]
            window.add_section_plane()
            window.section_axis.set("X")
            window._on_section_axis_changed()
            window._set_section_offset(0.5, clamp=True, refresh=True)
            window.compute_section()
            second_result = window.app_state.section_collection.results[1]
            second_curve = window.app_state.curve_collection.curves[1]

            tree = window.scene_browser.tree
            first_result_node = section_result_node_id(first_result.id)
            tree.selection_set(first_result_node)
            tree.focus(first_result_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()

            self.assertEqual(window.app_state.selected_item, "section_result")
            self.assertEqual(
                window.app_state.curve_collection.selected_curve_ids,
                {first_curve.id},
            )
            self.assertTrue(first_curve.selected)
            self.assertFalse(second_curve.selected)
            self.assertTrue(window.viewport.scene_calls[-1]["curve_results"][0].selected)

            second_group = curve_group_node_id(second_result.id)
            tree.selection_set(second_group)
            tree.focus(second_group)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()

            self.assertEqual(window.app_state.selected_item, "curve")
            self.assertEqual(
                window.app_state.curve_collection.selected_curve_ids,
                {second_curve.id},
            )
            self.assertFalse(first_curve.selected)
            self.assertTrue(second_curve.selected)
        finally:
            window.root.destroy()

    def test_scene_browser_root_selection_selects_all_children_by_family(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            (
                first_plane,
                second_plane,
                first_result,
                second_result,
                first_curve,
                second_curve,
                first_surface,
                second_surface,
            ) = _build_two_section_scene(window)
            first_plane.visible = True
            second_plane.visible = True
            window._refresh_viewport(reset_camera=False)

            tree = window.scene_browser.tree
            first_plane_node = section_plane_node_id(first_plane.id)
            second_plane_node = section_plane_node_id(second_plane.id)
            first_result_node = section_result_node_id(first_result.id)
            second_result_node = section_result_node_id(second_result.id)
            first_curve_node = curve_node_id(first_curve.id)
            second_curve_node = curve_node_id(second_curve.id)
            first_surface_node = surface_node_id(first_surface.id)
            second_surface_node = surface_node_id(second_surface.id)

            tree.selection_set(NODE_SECTION_PLANES)
            tree.focus(NODE_SECTION_PLANES)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()

            self.assertEqual(window.app_state.selected_item, "section_plane")
            self.assertEqual(
                window.app_state.section_collection.selected_plane_ids,
                {first_plane.id, second_plane.id},
            )
            self.assertTrue(first_plane.selected)
            self.assertTrue(second_plane.selected)
            self.assertEqual(set(tree.selection()), {first_plane_node, second_plane_node})

            tree.selection_set(NODE_SECTION_RESULTS)
            tree.focus(NODE_SECTION_RESULTS)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()

            self.assertEqual(window.app_state.selected_item, "section_result")
            self.assertEqual(
                window.app_state.section_collection.selected_result_ids,
                {first_result.id, second_result.id},
            )
            self.assertEqual(
                window.app_state.curve_collection.selected_curve_ids,
                {first_curve.id, second_curve.id},
            )
            self.assertTrue(first_result.selected)
            self.assertTrue(second_result.selected)
            self.assertTrue(first_curve.selected)
            self.assertTrue(second_curve.selected)
            self.assertEqual(
                set(tree.selection()),
                {first_result_node, second_result_node},
            )

            tree.selection_set(NODE_CURVES)
            tree.focus(NODE_CURVES)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()

            self.assertEqual(window.app_state.selected_item, "curve")
            self.assertEqual(
                window.app_state.curve_collection.selected_curve_ids,
                {first_curve.id, second_curve.id},
            )
            self.assertEqual(set(tree.selection()), {first_curve_node, second_curve_node})

            tree.selection_set(NODE_SURFACES)
            tree.focus(NODE_SURFACES)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()

            self.assertEqual(window.app_state.selected_item, "surface")
            self.assertEqual(
                window.app_state.surface_collection.selected_surface_ids,
                {first_surface.id, second_surface.id},
            )
            self.assertTrue(first_surface.selected)
            self.assertTrue(second_surface.selected)
            self.assertEqual(set(tree.selection()), {first_surface_node, second_surface_node})
        finally:
            window.root.destroy()

    def test_scene_browser_multi_selects_planes_results_and_surfaces(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            (
                first_plane,
                second_plane,
                first_result,
                second_result,
                first_curve,
                second_curve,
                first_surface,
                second_surface,
            ) = _build_two_section_scene(window)
            first_plane.visible = True
            second_plane.visible = True
            window._refresh_viewport(reset_camera=False)

            tree = window.scene_browser.tree
            first_plane_node = section_plane_node_id(first_plane.id)
            second_plane_node = section_plane_node_id(second_plane.id)
            tree.selection_set((first_plane_node, second_plane_node))
            tree.focus(second_plane_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()

            self.assertEqual(window.app_state.selected_item, "section_plane")
            self.assertEqual(window.app_state.section_collection.active_plane_id, second_plane.id)
            self.assertEqual(
                window.app_state.section_collection.selected_plane_ids,
                {first_plane.id, second_plane.id},
            )

            first_result_node = section_result_node_id(first_result.id)
            second_result_node = section_result_node_id(second_result.id)
            tree.selection_set((first_result_node, second_result_node))
            tree.focus(second_result_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()

            self.assertEqual(window.app_state.selected_item, "section_result")
            self.assertEqual(window.app_state.section_collection.active_result_id, second_result.id)
            self.assertEqual(
                window.app_state.section_collection.selected_result_ids,
                {first_result.id, second_result.id},
            )
            self.assertEqual(
                window.app_state.curve_collection.selected_curve_ids,
                {first_curve.id, second_curve.id},
            )

            first_surface_node = surface_node_id(first_surface.id)
            second_surface_node = surface_node_id(second_surface.id)
            tree.selection_set((first_surface_node, second_surface_node))
            tree.focus(second_surface_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()

            self.assertEqual(window.app_state.selected_item, "surface")
            self.assertEqual(window.app_state.surface_collection.active_surface_id, second_surface.id)
            self.assertEqual(
                window.app_state.surface_collection.selected_surface_ids,
                {first_surface.id, second_surface.id},
            )
            self.assertTrue(first_surface.selected)
            self.assertTrue(second_surface.selected)
        finally:
            window.root.destroy()

    def test_bulk_visibility_actions_apply_to_selected_planes_and_surfaces(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            (
                first_plane,
                second_plane,
                _first_result,
                _second_result,
                _first_curve,
                _second_curve,
                first_surface,
                second_surface,
            ) = _build_two_section_scene(window)

            tree = window.scene_browser.tree
            first_plane.visible = True
            second_plane.visible = True
            window._refresh_viewport(reset_camera=False)
            tree.selection_set(NODE_SECTION_PLANES)
            tree.focus(NODE_SECTION_PLANES)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()
            window.hide_selected_scene_objects()

            self.assertFalse(first_plane.visible)
            self.assertFalse(second_plane.visible)
            self.assertEqual(window.status_text.get(), "Hidden 2 selected items")

            window.show_all_scene_objects()
            self.assertTrue(first_plane.visible)
            self.assertTrue(second_plane.visible)

            tree.selection_set(NODE_SURFACES)
            tree.focus(NODE_SURFACES)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()
            window.hide_selected_scene_objects()

            self.assertFalse(first_surface.visible)
            self.assertFalse(second_surface.visible)
            self.assertEqual(window.status_text.get(), "Hidden 2 selected items")

            window.toggle_selected_scene_objects()
            self.assertTrue(first_surface.visible)
            self.assertTrue(second_surface.visible)
            self.assertEqual(window.status_text.get(), "Toggled 2 selected items")
        finally:
            window.root.destroy()

    def test_scene_browser_parent_visibility_labels_show_visible_hidden_and_mixed(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            (
                first_plane,
                second_plane,
                first_result,
                second_result,
                first_curve,
                second_curve,
                first_surface,
                second_surface,
            ) = _build_two_section_scene(window)
            first_plane.visible = True
            second_plane.visible = True
            first_result.visible = True
            second_result.visible = False
            first_curve.visible = True
            second_curve.visible = False
            first_surface.visible = False
            second_surface.visible = False
            repaired_curve = StoredCurve(
                id="curve-repaired",
                name="Repaired",
                section_result_id="missing-result",
                plane_id=first_plane.id,
                original_points=np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=float),
                fitted_points=np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=float),
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
                visible=False,
                metadata={"repair_type": "join"},
            )
            unassigned_curve = StoredCurve(
                id="curve-unassigned",
                name="Unassigned",
                section_result_id="missing-result",
                plane_id=first_plane.id,
                original_points=np.asarray([[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]], dtype=float),
                fitted_points=np.asarray([[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]], dtype=float),
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
                visible=True,
            )
            manual_curve = StoredCurve(
                id="curve-manual",
                name="Manual Curve 1",
                section_result_id="",
                plane_id="",
                original_points=np.asarray([[0.0, 2.0, 0.0], [1.0, 2.0, 0.0]], dtype=float),
                fitted_points=np.asarray([[0.0, 2.0, 0.0], [1.0, 2.0, 0.0]], dtype=float),
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
                visible=True,
                metadata={"creation_type": "manual", "snap_to_mesh": False},
            )
            boundary_curve = StoredCurve(
                id="curve-boundary",
                name="Region Boundary 1",
                section_result_id="",
                plane_id="",
                original_points=np.asarray([[0.0, 3.0, 0.0], [1.0, 3.0, 0.0]], dtype=float),
                fitted_points=np.asarray([[0.0, 3.0, 0.0], [1.0, 3.0, 0.0]], dtype=float),
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
                visible=True,
                metadata={
                    "creation_type": "region_boundary",
                    "source_region_id": "region-a",
                },
            )
            add_curve(window.app_state.curve_collection, boundary_curve)
            add_curve(window.app_state.curve_collection, manual_curve)
            add_curve(window.app_state.curve_collection, repaired_curve)
            add_curve(window.app_state.curve_collection, unassigned_curve)
            window._refresh_viewport(reset_camera=False)

            tree = window.scene_browser.tree
            self.assertEqual(tree.item(NODE_SECTION_PLANES, "text"), "[V] Section Planes")
            self.assertEqual(tree.item(NODE_SECTION_RESULTS, "text"), "[M] Section Results")
            self.assertEqual(tree.item(NODE_CURVES, "text"), "[M] Curves")
            self.assertEqual(
                tree.item(curve_group_node_id(first_result.id), "text"),
                "[V] Section: Section 1",
            )
            self.assertEqual(
                tree.item(curve_group_node_id(second_result.id), "text"),
                "[H] Section: Section 2",
            )
            self.assertEqual(tree.item(NODE_CURVE_GROUP_REGION_BOUNDARIES, "text"), "[V] Region Boundaries")
            self.assertEqual(tree.item(NODE_CURVE_GROUP_MANUAL, "text"), "[V] Manual Curves")
            self.assertEqual(tree.item(NODE_CURVE_GROUP_REPAIRED, "text"), "[H] Repaired Curves")
            self.assertEqual(tree.item(NODE_CURVE_GROUP_UNASSIGNED, "text"), "[V] Unassigned")
            self.assertEqual(
                tree.get_children(NODE_CURVES),
                (
                    NODE_CURVE_GROUP_REGION_BOUNDARIES,
                    NODE_CURVE_GROUP_MANUAL,
                    NODE_CURVE_GROUP_REPAIRED,
                    curve_group_node_id(first_result.id),
                    curve_group_node_id(second_result.id),
                    NODE_CURVE_GROUP_UNASSIGNED,
                ),
            )
            self.assertEqual(tree.item(NODE_SURFACES, "text"), "[H] Preview Surfaces")
        finally:
            window.root.destroy()

    def test_scene_browser_curve_labels_include_tiny_repaired_and_closed_tags(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.compute_section()
            result = window.app_state.section_collection.results[0]
            tiny_curve = window.app_state.curve_collection.curves[0]
            tiny_points = np.asarray(
                [
                    [0.0, 0.0, 0.0],
                    [0.001, 0.0, 0.0],
                ],
                dtype=float,
            )
            tiny_curve.original_points = tiny_points.copy()
            tiny_curve.fitted_points = tiny_points.copy()

            repaired_curve = StoredCurve(
                id="curve-repaired",
                name="Smoothed Curve 1",
                section_result_id=result.id,
                plane_id=result.plane_id,
                original_points=np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=float),
                fitted_points=np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=float),
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
                metadata={"operation": "smooth"},
            )
            closed_curve = StoredCurve(
                id="curve-closed",
                name="Loop Curve",
                section_result_id=result.id,
                plane_id=result.plane_id,
                original_points=np.asarray(
                    [
                        [0.0, 0.0, 0.0],
                        [1.0, 0.0, 0.0],
                        [1.0, 1.0, 0.0],
                        [0.0, 0.0, 0.0],
                    ],
                    dtype=float,
                ),
                fitted_points=np.asarray(
                    [
                        [0.0, 0.0, 0.0],
                        [1.0, 0.0, 0.0],
                        [1.0, 1.0, 0.0],
                        [0.0, 0.0, 0.0],
                    ],
                    dtype=float,
                ),
                mean_error=0.0,
                max_error=0.0,
                is_closed=True,
            )
            add_curve(window.app_state.curve_collection, repaired_curve)
            add_curve(window.app_state.curve_collection, closed_curve)
            window._refresh_viewport(reset_camera=False)

            tree = window.scene_browser.tree
            self.assertEqual(
                tree.item(curve_node_id(tiny_curve.id), "text"),
                "[V] Section 1 Curve 1 (tiny)",
            )
            self.assertEqual(
                tree.item(curve_node_id(repaired_curve.id), "text"),
                "[V] Smoothed Curve 1 (repaired)",
            )
            self.assertEqual(
                tree.item(curve_node_id(closed_curve.id), "text"),
                "[V] Loop Curve (closed)",
            )
        finally:
            window.root.destroy()

    def test_select_source_curves_selects_expected_curves_for_active_surface(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            (
                _first_plane,
                _second_plane,
                _first_result,
                _second_result,
                first_curve,
                second_curve,
                _first_surface,
                _second_surface,
            ) = _build_two_section_scene(window)
            loft_surface = SurfacePatch(
                id="surface-loft",
                name="Loft Surface 1",
                source_curve_ids=[second_curve.id, first_curve.id],
                surface_type="preview_loft",
            )
            add_surface(window.app_state.surface_collection, loft_surface)

            window.select_surface(loft_surface.id)
            self.assertEqual(window.app_state.selected_item, "surface")
            self.assertEqual(window.app_state.curve_collection.selected_curve_ids, set())
            self.assertEqual(
                window.viewport.scene_calls[-1]["surface_source_curve_ids"],
                (second_curve.id, first_curve.id),
            )

            window.select_source_curves_for_active_surface()

            self.assertEqual(window.app_state.selected_item, "curve")
            self.assertEqual(
                window.app_state.curve_collection.selected_curve_ids,
                {first_curve.id, second_curve.id},
            )
            self.assertEqual(window.app_state.curve_collection.active_curve_id, second_curve.id)
            self.assertEqual(
                window.status_text.get(),
                "Selected source curves for Loft Surface 1",
            )

            window.clear_selection()
            window.select_source_curves_for_active_surface()
            self.assertEqual(window.status_text.get(), "Select a surface first.")

            window._on_scene_browser_visibility(
                "select_source_curves",
                (surface_node_id(loft_surface.id),),
            )
            self.assertEqual(
                window.app_state.curve_collection.selected_curve_ids,
                {first_curve.id, second_curve.id},
            )
            self.assertEqual(window.app_state.curve_collection.active_curve_id, second_curve.id)
        finally:
            window.root.destroy()

    def test_source_curve_commands_isolate_show_frame_and_report_missing_sources(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            (
                _first_plane,
                _second_plane,
                _first_result,
                _second_result,
                first_curve,
                second_curve,
                _first_surface,
                _second_surface,
            ) = _build_two_section_scene(window)
            surface = SurfacePatch(
                id="surface-source-workflow",
                name="Loft Surface 1",
                source_curve_ids=[first_curve.id, "missing-curve"],
                surface_type="preview_loft",
            )
            add_surface(window.app_state.surface_collection, surface)
            window.select_surface(surface.id)

            first_curve.visible = False
            second_curve.visible = True
            window.show_source_curves_for_active_surface()
            self.assertTrue(first_curve.visible)
            self.assertTrue(second_curve.visible)
            self.assertEqual(
                window.status_text.get(),
                "Shown source curves for Loft Surface 1 (1 missing source curve)",
            )

            window.isolate_source_curves_for_active_surface()
            self.assertTrue(first_curve.visible)
            self.assertFalse(second_curve.visible)
            self.assertEqual(
                window.status_text.get(),
                "Isolated source curves for Loft Surface 1 (1 missing source curve)",
            )

            window.frame_source_curves_for_active_surface()
            self.assertEqual(len(window.viewport.framed_bounds), 1)
            self.assertEqual(
                window.status_text.get(),
                "Framed source curves for Loft Surface 1 (1 missing source curve)",
            )

            missing_surface = SurfacePatch(
                id="surface-missing-only",
                name="Missing Surface",
                source_curve_ids=["missing-a", "missing-b"],
                surface_type="preview_loft",
            )
            add_surface(window.app_state.surface_collection, missing_surface)
            window.select_surface(missing_surface.id)
            window.select_source_curves_for_active_surface()
            self.assertEqual(
                window.status_text.get(),
                "No source curves found for Missing Surface (2 missing source curves)",
            )
        finally:
            window.root.destroy()

    def test_parent_and_group_visibility_actions_affect_child_objects(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            (
                _first_plane,
                _second_plane,
                first_result,
                second_result,
                first_curve,
                second_curve,
                _first_surface,
                _second_surface,
            ) = _build_two_section_scene(window)
            first_curve.visible = True
            second_curve.visible = True
            window._refresh_viewport(reset_camera=False)

            tree = window.scene_browser.tree
            tree.selection_set(NODE_CURVES)
            tree.focus(NODE_CURVES)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()
            window.toggle_selected_scene_objects()

            self.assertFalse(first_curve.visible)
            self.assertFalse(second_curve.visible)
            self.assertEqual(tree.item(NODE_CURVES, "text"), "[H] Curves")

            second_curve.visible = True
            window._refresh_viewport(reset_camera=False)
            first_group = curve_group_node_id(first_result.id)
            tree.selection_set(first_group)
            tree.focus(first_group)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()
            window.toggle_selected_scene_objects()

            self.assertTrue(first_curve.visible)
            self.assertTrue(second_curve.visible)
            self.assertEqual(tree.item(first_group, "text"), "[V] Section: Section 1")
            self.assertEqual(tree.item(curve_group_node_id(second_result.id), "text"), "[V] Section: Section 2")

            first_curve.visible = False
            second_curve.visible = False
            window._refresh_viewport(reset_camera=False)
            window._on_scene_browser_visibility("show_selected", (NODE_CURVES,))

            self.assertTrue(first_curve.visible)
            self.assertTrue(second_curve.visible)
            self.assertEqual(tree.item(NODE_CURVES, "text"), "[V] Curves")
        finally:
            window.root.destroy()

    def test_delete_selected_curve_group_removes_child_curves_and_surfaces(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            (
                _first_plane,
                _second_plane,
                first_result,
                _second_result,
                first_curve,
                second_curve,
                first_surface,
                second_surface,
            ) = _build_two_section_scene(window)

            tree = window.scene_browser.tree
            group_node = curve_group_node_id(first_result.id)
            tree.selection_set(group_node)
            tree.focus(group_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()
            window.delete_selected_scene_objects()

            self.assertNotIn(first_curve, window.app_state.curve_collection.curves)
            self.assertIn(second_curve, window.app_state.curve_collection.curves)
            self.assertNotIn(first_surface, window.app_state.surface_collection.surfaces)
            self.assertIn(second_surface, window.app_state.surface_collection.surfaces)
            self.assertEqual(window.status_text.get(), "Deleted 2 selected objects")
        finally:
            window.root.destroy()

    def test_frame_selected_curve_uses_curve_bounds(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.compute_section()
            curve = window.app_state.curve_collection.curves[0]
            curve.fitted_points = np.asarray(
                [[2.0, 3.0, 4.0], [5.0, 7.0, 11.0]],
                dtype=float,
            )
            window.select_curve(curve.id)

            window.frame_selected()

            self.assertEqual(window.status_text.get(), "View framed to selection")
            self.assertEqual(len(window.viewport.framed_bounds), 1)
            minimum_bound, maximum_bound = window.viewport.framed_bounds[0]
            self.assertTrue(np.allclose(minimum_bound, [2.0, 3.0, 4.0]))
            self.assertTrue(np.allclose(maximum_bound, [5.0, 7.0, 11.0]))
            self.assertEqual(window.viewport.frame_count, 0)
        finally:
            window.root.destroy()

    def test_parent_rename_is_disabled_and_rejected(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _build_two_section_scene(window)
            menu = window.scene_browser._context_menu
            labels = [
                menu.entrycget(index, "label")
                for index in range(menu.index("end") + 1)
                if menu.type(index) != "separator"
            ]
            self.assertIn("Show Selected", labels)
            self.assertFalse(window.scene_browser._is_renameable_node(NODE_CURVES))

            tree = window.scene_browser.tree
            tree.selection_set(NODE_CURVES)
            tree.focus(NODE_CURVES)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()
            window.rename_selected()

            self.assertEqual(window.status_text.get(), "Select one object to rename.")
        finally:
            window.root.destroy()

    def test_visibility_command_can_be_undone_and_redone(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.compute_section()
            curve = window.app_state.curve_collection.curves[0]
            curve_node = curve_node_id(curve.id)

            window._on_scene_browser_visibility("hide_selected", (curve_node,))
            self.assertFalse(curve.visible)
            window.undo()
            self.assertTrue(curve.visible)
            self.assertEqual(window.status_text.get(), "Undid Hide Visibility")
            window.redo()
            self.assertFalse(curve.visible)
            self.assertEqual(window.status_text.get(), "Redid Hide Visibility")
        finally:
            window.root.destroy()

    def test_bulk_delete_selected_curves_and_surfaces(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            (
                _first_plane,
                _second_plane,
                first_result,
                second_result,
                first_curve,
                second_curve,
                first_surface,
                second_surface,
            ) = _build_two_section_scene(window)

            tree = window.scene_browser.tree
            first_surface_node = surface_node_id(first_surface.id)
            second_surface_node = surface_node_id(second_surface.id)
            tree.selection_set((first_surface_node, second_surface_node))
            tree.focus(second_surface_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()
            window.delete_selected_scene_objects()

            self.assertEqual(window.app_state.surface_collection.surfaces, [])
            self.assertEqual(
                {curve.id for curve in window.app_state.curve_collection.curves},
                {first_curve.id, second_curve.id},
            )
            self.assertFalse(tree.exists(NODE_SURFACES))
            self.assertEqual(window.status_text.get(), "Deleted 2 selected objects")

            replacement_surface = SurfacePatch(
                id="surface-3",
                name="Surface 3",
                source_curve_ids=[first_curve.id],
                surface_type="preview_fill",
            )
            add_surface(window.app_state.surface_collection, replacement_surface)
            window._refresh_viewport(reset_camera=False)

            first_curve_node = curve_node_id(first_curve.id)
            second_curve_node = curve_node_id(second_curve.id)
            tree.selection_set((first_curve_node, second_curve_node))
            tree.focus(second_curve_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()
            window.delete_selected_scene_objects()

            self.assertEqual(window.app_state.curve_collection.curves, [])
            self.assertEqual(window.app_state.surface_collection.surfaces, [])
            self.assertEqual(
                {result.id for result in window.app_state.section_collection.results},
                {first_result.id, second_result.id},
            )
            self.assertEqual(window.status_text.get(), "Deleted 3 selected objects")
        finally:
            window.root.destroy()

    def test_bulk_delete_section_result_and_plane_remove_dependents(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            (
                first_plane,
                second_plane,
                first_result,
                second_result,
                first_curve,
                second_curve,
                first_surface,
                second_surface,
            ) = _build_two_section_scene(window)

            tree = window.scene_browser.tree
            tree.selection_set(section_result_node_id(first_result.id))
            tree.focus(section_result_node_id(first_result.id))
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()
            window.delete_selected_scene_objects()

            self.assertNotIn(first_result, window.app_state.section_collection.results)
            self.assertIn(second_result, window.app_state.section_collection.results)
            self.assertNotIn(first_curve, window.app_state.curve_collection.curves)
            self.assertIn(second_curve, window.app_state.curve_collection.curves)
            self.assertNotIn(first_surface, window.app_state.surface_collection.surfaces)
            self.assertIn(second_surface, window.app_state.surface_collection.surfaces)

            tree.selection_set(section_plane_node_id(second_plane.id))
            tree.focus(section_plane_node_id(second_plane.id))
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()
            window.delete_selected_scene_objects()

            self.assertIn(first_plane, window.app_state.section_collection.planes)
            self.assertNotIn(second_plane, window.app_state.section_collection.planes)
            self.assertEqual(window.app_state.section_collection.results, [])
            self.assertEqual(window.app_state.curve_collection.curves, [])
            self.assertEqual(window.app_state.surface_collection.surfaces, [])
            self.assertEqual(window.status_text.get(), "Deleted 4 selected objects")
        finally:
            window.root.destroy()

    def test_rename_rejected_for_multi_selection(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            (
                _first_plane,
                _second_plane,
                _first_result,
                _second_result,
                first_curve,
                second_curve,
                _first_surface,
                _second_surface,
            ) = _build_two_section_scene(window)

            tree = window.scene_browser.tree
            first_curve_node = curve_node_id(first_curve.id)
            second_curve_node = curve_node_id(second_curve.id)
            tree.selection_set((first_curve_node, second_curve_node))
            tree.focus(second_curve_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()

            window.rename_selected()

            self.assertEqual(window.status_text.get(), "Select one object to rename.")
        finally:
            window.root.destroy()

    def test_mesh_visibility_hotkeys_toggle_isolate_and_show_all(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            window.select_model()
            window._handle_shortcut("H")

            self.assertFalse(window.app_state.mesh_object.visible)
            self.assertFalse(window.mesh_visible.get())
            self.assertIsNone(window.viewport.scene_calls[-1]["mesh"])
            self.assertEqual(window.scene_browser.tree.item(NODE_MESH, "text"), "[H] sample.stl")

            window._handle_shortcut("H")

            self.assertTrue(window.app_state.mesh_object.visible)
            self.assertTrue(window.mesh_visible.get())
            self.assertIs(window.viewport.scene_calls[-1]["mesh"], window.app_state.mesh_object.display_mesh)
            self.assertEqual(window.scene_browser.tree.item(NODE_MESH, "text"), "[V] sample.stl")

            active_plane = window.app_state.section_collection.planes[0]
            active_plane.visible = True
            window.show_section_plane.set(True)
            window.select_model()
            window._handle_shortcut("Shift+H")

            self.assertTrue(window.app_state.mesh_object.visible)
            self.assertFalse(active_plane.visible)

            window._handle_shortcut("Alt+H")

            self.assertTrue(window.app_state.mesh_object.visible)
            self.assertTrue(active_plane.visible)
        finally:
            window.root.destroy()

    def test_visibility_keybind_uses_settings_and_ignores_text_entry_focus(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            window.select_model()
            window.settings.keybinds.toggle_visibility = "V"
            window._on_tk_keypress(SimpleNamespace(keysym="h", state=0))
            self.assertTrue(window.app_state.mesh_object.visible)

            window._on_tk_keypress(SimpleNamespace(keysym="v", state=0))
            self.assertFalse(window.app_state.mesh_object.visible)

            window.mesh_name_entry.focus_set()
            window.root.update()
            window._on_tk_keypress(SimpleNamespace(keysym="v", state=0))
            self.assertFalse(window.app_state.mesh_object.visible)
        finally:
            window.root.destroy()

    def test_create_surface_from_selected_curve_adds_placeholder_surface(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            window.compute_section()
            source_curve = window.app_state.curve_collection.curves[0]
            _make_curve_closed(source_curve)
            window.select_curve(source_curve.id)
            window._set_project_dirty(False)

            progress_dialogs: list[object] = []

            class RecordingProgressDialog:
                def __init__(self, _parent: object, title: str, summary: str | None = None) -> None:
                    self.title = title
                    self.summary = summary
                    self.stages: list[str] = []
                    self.closed = False
                    progress_dialogs.append(self)

                def update_stage(self, stage: str) -> None:
                    self.stages.append(stage)

                def close(self) -> None:
                    self.closed = True

            with patch("app.main_window.ComputationProgressDialog", RecordingProgressDialog):
                window.surfaces_menu.invoke(0)

            surfaces = window.app_state.surface_collection.surfaces
            self.assertEqual(len(surfaces), 1)
            surface = surfaces[0]
            self.assertEqual(surface.name, "Fill Surface 1")
            self.assertEqual(surface.surface_type, "preview_fill")
            self.assertEqual(surface.source_curve_ids, [source_curve.id])
            self.assertTrue(surface.visible)
            self.assertTrue(surface.selected)
            self.assertEqual(surface.metadata["curve_count"], 1)
            self.assertEqual(surface.metadata["source_curve_count"], 1)
            self.assertEqual(surface.metadata["source_curve_names"], [source_curve.name])
            self.assertEqual(surface.metadata["source"], "selected_curve")
            self.assertEqual(
                surface.metadata["preview_mode"],
                "closed_curve_fill",
            )
            self.assertTrue(surface.metadata["preview_available"])
            self.assertEqual(surface.metadata["preview_reason"], "fan fill preview generated")
            self.assertEqual(
                surface.metadata["preview_warning"],
                "Fan fill preview may be inaccurate for concave curves",
            )
            self.assertEqual(window.app_state.selected_item, "surface")
            self.assertEqual(window.app_state.surface_collection.active_surface_id, surface.id)
            self.assertEqual(window.status_text.get(), "Filled Fill Surface 1 from 1 curve")
            self.assertEqual(len(progress_dialogs), 1)
            self.assertEqual(progress_dialogs[0].title, "Building Surface Preview")
            self.assertEqual(progress_dialogs[0].stages, list(SURFACE_PREVIEW_PROGRESS_STAGES))
            self.assertTrue(progress_dialogs[0].closed)
            self.assertTrue(window.project_dirty)
            self.assertEqual(window.surface_context_frame.winfo_manager(), "grid")
            self.assertEqual(window.surface_name_text.get(), "Fill Surface 1")
            self.assertEqual(window.surface_type_text.get(), "preview_fill")
            self.assertEqual(window.surface_preview_mode_text.get(), "closed_curve_fill")
            self.assertEqual(window.surface_source_curve_count_text.get(), "1")
            self.assertEqual(window.surface_source_curve_names_text.get(), source_curve.name)
            self.assertEqual(window.surface_preview_available_text.get(), "Yes")
            self.assertEqual(window.surface_preview_reason_text.get(), "fan fill preview generated")
            self.assertEqual(
                window.surface_preview_warning_text.get(),
                "Fan fill preview may be inaccurate for concave curves",
            )
            self.assertEqual(window.surface_grid_size_text.get(), "(none)")
            self.assertEqual(window.surface_planarity_error_text.get(), "0.000")
            self.assertEqual(window.surface_resampled_point_count_text.get(), "(none)")
            self.assertEqual(window.surface_reversed_second_curve_text.get(), "(none)")
            self.assertEqual(window.surface_seam_shift_applied_text.get(), "(none)")
            self.assertEqual(window.surface_average_pair_distance_text.get(), "(none)")
            self.assertEqual(window.surface_max_pair_distance_text.get(), "(none)")
            self.assertEqual(window.surface_validation_warnings_text.get(), "(none)")
            self.assertEqual(window.surface_validation_errors_text.get(), "(none)")
            self.assertEqual(window.surface_opacity_text.get(), "0.22")
            self.assertTrue(window.surface_wireframe_overlay.get())
            self.assertIn("curve_count=1", window.surface_metadata_text.get())
            self.assertIn("source_curve_names=", window.surface_metadata_text.get())
            self.assertIn("source=selected_curve", window.surface_metadata_text.get())
            preview = window.viewport.scene_calls[-1]["surface_previews"][0]
            self.assertAlmostEqual(preview.opacity, 0.22)
            self.assertTrue(preview.wireframe_overlay)

            window._on_surface_opacity_changed("0.35")
            preview = window.viewport.scene_calls[-1]["surface_previews"][0]
            self.assertAlmostEqual(surface.metadata["display_opacity"], 0.35)
            self.assertAlmostEqual(preview.opacity, 0.35)
            self.assertEqual(window.surface_opacity_text.get(), "0.35")

            window.surface_wireframe_overlay.set(False)
            window._on_surface_wireframe_changed()
            preview = window.viewport.scene_calls[-1]["surface_previews"][0]
            self.assertFalse(surface.metadata["wireframe_overlay"])
            self.assertFalse(preview.wireframe_overlay)

            tree = window.scene_browser.tree
            surface_node = surface_node_id(surface.id)
            self.assertEqual(tree.get_children(NODE_SURFACES), (surface_node,))
            self.assertEqual(tree.item(surface_node, "text"), "[V] Fill Surface 1 (fill)")
            self.assertEqual(tree.selection(), (surface_node,))
        finally:
            window.root.destroy()

    def test_create_surface_from_two_selected_curves_creates_loft_with_unique_names(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            window.compute_section()
            first_curve = window.app_state.curve_collection.curves[0]
            window.add_section_plane()
            window.section_axis.set("X")
            window._on_section_axis_changed()
            window._set_section_offset(0.5, clamp=True, refresh=True)
            window.compute_section()
            second_curve = window.app_state.curve_collection.curves[1]

            window.select_curves(
                [first_curve.id, second_curve.id],
                active_curve_id=second_curve.id,
            )
            window.surfaces_menu.invoke(1)
            first_surface = window.app_state.surface_collection.surfaces[0]
            self.assertEqual(first_surface.name, "Loft Surface 1")
            self.assertEqual(
                first_surface.source_curve_ids,
                [first_curve.id, second_curve.id],
            )
            self.assertEqual(first_surface.surface_type, "preview_loft")
            self.assertEqual(first_surface.metadata["curve_count"], 2)
            self.assertEqual(first_surface.metadata["source_curve_count"], 2)
            self.assertEqual(
                first_surface.metadata["source_curve_names"],
                [first_curve.name, second_curve.name],
            )
            self.assertEqual(first_surface.metadata["source"], "selected_curves")
            self.assertEqual(first_surface.metadata["preview_mode"], "two_curve_loft")
            self.assertTrue(first_surface.metadata["preview_available"])
            self.assertIn("loft generated", str(first_surface.metadata["preview_reason"]))
            self.assertIn("reversed_second_curve", first_surface.metadata)
            self.assertIn("seam_shift_applied", first_surface.metadata)
            self.assertGreaterEqual(first_surface.metadata["resampled_point_count"], 2)
            self.assertIn("average_pair_distance", first_surface.metadata)
            self.assertIn("max_pair_distance", first_surface.metadata)
            self.assertEqual(
                window.status_text.get(),
                "Lofted Loft Surface 1 from 2 curves",
            )
            self.assertGreaterEqual(int(window.surface_resampled_point_count_text.get()), 2)
            self.assertIn(
                window.surface_reversed_second_curve_text.get(),
                {"Yes", "No"},
            )
            self.assertIn(
                window.surface_seam_shift_applied_text.get(),
                {"Yes", "No"},
            )
            self.assertNotEqual(window.surface_average_pair_distance_text.get(), "(none)")
            self.assertNotEqual(window.surface_max_pair_distance_text.get(), "(none)")
            self.assertIn("resampled_point_count=", window.surface_metadata_text.get())

            window.select_curves(
                [first_curve.id, second_curve.id],
                active_curve_id=first_curve.id,
            )
            window.surfaces_menu.invoke(1)

            surfaces = window.app_state.surface_collection.surfaces
            self.assertEqual(
                [surface.name for surface in surfaces],
                ["Loft Surface 1", "Loft Surface 2"],
            )
            second_surface = surfaces[1]
            self.assertEqual(second_surface.source_curve_ids, [first_curve.id, second_curve.id])
            self.assertEqual(second_surface.surface_type, "preview_loft")

            window.clear_selection()
            window.surfaces_menu.invoke(1)
            self.assertEqual(
                window.status_text.get(),
                "Select exactly two curves to loft",
            )
            self.assertEqual(len(window.app_state.surface_collection.surfaces), 2)
        finally:
            window.root.destroy()

    def test_patch_surface_commands_create_diagnostics_and_undoable_surfaces(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            boundary_curve = StoredCurve(
                id="curve-boundary",
                name="Boundary Curve",
                section_result_id="",
                plane_id="",
                original_points=np.asarray(
                    [
                        [0.0, 0.0, 0.0],
                        [1.0, 0.0, 0.0],
                        [1.0, 1.0, 0.0],
                        [0.0, 1.0, 0.0],
                    ],
                    dtype=float,
                ),
                fitted_points=np.asarray(
                    [
                        [0.0, 0.0, 0.0],
                        [1.0, 0.0, 0.0],
                        [1.0, 1.0, 0.0],
                        [0.0, 1.0, 0.0],
                    ],
                    dtype=float,
                ),
                mean_error=0.0,
                max_error=0.0,
                is_closed=True,
                metadata={
                    "creation_type": "region_boundary",
                    "source_region_id": "region-a",
                    "source_mesh_name": "sample.stl",
                },
            )
            add_curve(window.app_state.curve_collection, boundary_curve)
            window.select_curve(boundary_curve.id)

            window.create_boundary_patch_from_curve()

            boundary_surface = window.app_state.surface_collection.surfaces[-1]
            self.assertEqual(boundary_surface.name, "Boundary Patch 1")
            self.assertEqual(boundary_surface.surface_type, "preview_boundary_patch")
            self.assertEqual(boundary_surface.source_curve_ids, [boundary_curve.id])
            self.assertEqual(boundary_surface.metadata["preview_mode"], "boundary_patch")
            self.assertEqual(boundary_surface.metadata["boundary_curve_id"], boundary_curve.id)
            self.assertEqual(boundary_surface.metadata["source_region_ids"], ["region-a"])
            self.assertEqual(boundary_surface.metadata["source_mesh_names"], ["sample.stl"])
            self.assertTrue(boundary_surface.metadata["preview_available"])
            self.assertEqual(boundary_surface.metadata["triangulation_method"], "ear_clipping")
            self.assertEqual(window.surface_preview_mode_text.get(), "boundary_patch")
            self.assertEqual(window.surface_planarity_error_text.get(), "0.000")
            self.assertEqual(
                window.scene_browser.tree.item(surface_node_id(boundary_surface.id), "text"),
                "[V] Boundary Patch 1 (boundary patch)",
            )

            window.undo()
            self.assertNotIn(
                boundary_surface.id,
                [surface.id for surface in window.app_state.surface_collection.surfaces],
            )
            window.redo()
            self.assertIn(
                boundary_surface.id,
                [surface.id for surface in window.app_state.surface_collection.surfaces],
            )

            patch_curves = [
                StoredCurve(
                    id="curve-bottom",
                    name="Bottom",
                    section_result_id="",
                    plane_id="",
                    original_points=np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=float),
                    fitted_points=np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=float),
                    mean_error=0.0,
                    max_error=0.0,
                    is_closed=False,
                    metadata={"creation_type": "rebuilt_curve", "curve_method": "catmull_rom"},
                ),
                StoredCurve(
                    id="curve-right",
                    name="Right",
                    section_result_id="",
                    plane_id="",
                    original_points=np.asarray([[1.0, 0.0, 0.0], [1.0, 1.0, 0.0]], dtype=float),
                    fitted_points=np.asarray([[1.0, 0.0, 0.0], [1.0, 1.0, 0.0]], dtype=float),
                    mean_error=0.0,
                    max_error=0.0,
                    is_closed=False,
                    metadata={"creation_type": "rebuilt_curve", "curve_method": "catmull_rom"},
                ),
                StoredCurve(
                    id="curve-top",
                    name="Top",
                    section_result_id="",
                    plane_id="",
                    original_points=np.asarray([[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]], dtype=float),
                    fitted_points=np.asarray([[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]], dtype=float),
                    mean_error=0.0,
                    max_error=0.0,
                    is_closed=False,
                    metadata={"creation_type": "rebuilt_curve", "curve_method": "catmull_rom"},
                ),
                StoredCurve(
                    id="curve-left",
                    name="Left",
                    section_result_id="",
                    plane_id="",
                    original_points=np.asarray([[0.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=float),
                    fitted_points=np.asarray([[0.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=float),
                    mean_error=0.0,
                    max_error=0.0,
                    is_closed=False,
                    metadata={"creation_type": "rebuilt_curve", "curve_method": "catmull_rom"},
                ),
            ]
            for curve in patch_curves:
                add_curve(window.app_state.curve_collection, curve)
            window.select_curves([curve.id for curve in patch_curves], active_curve_id=patch_curves[0].id)

            window.create_four_curve_patch()

            four_curve_surface = window.app_state.surface_collection.surfaces[-1]
            self.assertEqual(four_curve_surface.name, "Four-Curve Patch 1")
            self.assertEqual(four_curve_surface.surface_type, "preview_four_curve_patch")
            self.assertEqual(four_curve_surface.metadata["preview_mode"], "four_curve_patch")
            self.assertEqual(four_curve_surface.metadata["curve_order"], [curve.id for curve in patch_curves])
            self.assertEqual(four_curve_surface.metadata["grid_u_count"], 2)
            self.assertEqual(four_curve_surface.metadata["grid_v_count"], 2)
            self.assertIn(
                "Curve order inferred from scene order; inspect patch.",
                four_curve_surface.metadata["source_curve_validation_warnings"],
            )
            self.assertEqual(window.surface_grid_size_text.get(), "2 x 2")
            self.assertEqual(
                window.scene_browser.tree.item(surface_node_id(four_curve_surface.id), "text"),
                "[V] Four-Curve Patch 1 (4-curve patch)",
            )
            window.undo()
            self.assertNotIn(
                four_curve_surface.id,
                [surface.id for surface in window.app_state.surface_collection.surfaces],
            )
            window.redo()
            self.assertIn(
                four_curve_surface.id,
                [surface.id for surface in window.app_state.surface_collection.surfaces],
            )

            network_curves = patch_curves[:3]
            window.select_curves([curve.id for curve in network_curves], active_curve_id=network_curves[0].id)
            window.create_curve_network_patch()

            network_surface = window.app_state.surface_collection.surfaces[-1]
            self.assertEqual(network_surface.name, "Network Patch 1")
            self.assertEqual(network_surface.surface_type, "preview_curve_network_patch")
            self.assertEqual(network_surface.metadata["preview_mode"], "curve_network_patch")
            self.assertEqual(network_surface.metadata["network_curve_count"], 3)
            self.assertEqual(network_surface.metadata["strip_count"], 2)
            self.assertEqual(network_surface.metadata["resampled_point_count"], 2)
            self.assertEqual(
                window.scene_browser.tree.item(surface_node_id(network_surface.id), "text"),
                "[V] Network Patch 1 (network patch)",
            )
            window.undo()
            self.assertNotIn(
                network_surface.id,
                [surface.id for surface in window.app_state.surface_collection.surfaces],
            )
            window.redo()
            self.assertIn(
                network_surface.id,
                [surface.id for surface in window.app_state.surface_collection.surfaces],
            )
        finally:
            window.root.destroy()

    def test_create_surface_from_short_two_curve_selection_marks_preview_unavailable(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            window.compute_section()
            first_curve = window.app_state.curve_collection.curves[0]
            short_points = np.asarray([[0.0, 0.0, 0.0]], dtype=float)
            short_curve = StoredCurve(
                id="curve-short",
                name="Short Curve",
                section_result_id=first_curve.section_result_id,
                plane_id=first_curve.plane_id,
                original_points=short_points.copy(),
                fitted_points=short_points.copy(),
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
            )
            add_curve(window.app_state.curve_collection, short_curve)

            window.select_curves(
                [first_curve.id, short_curve.id],
                active_curve_id=short_curve.id,
            )
            progress_dialogs: list[object] = []

            class RecordingProgressDialog:
                def __init__(self, _parent: object, title: str, summary: str | None = None) -> None:
                    self.title = title
                    self.summary = summary
                    self.stages: list[str] = []
                    self.closed = False
                    progress_dialogs.append(self)

                def update_stage(self, stage: str) -> None:
                    self.stages.append(stage)

                def close(self) -> None:
                    self.closed = True

            with patch("app.main_window.ComputationProgressDialog", RecordingProgressDialog):
                window.surfaces_menu.invoke(1)

            surfaces = window.app_state.surface_collection.surfaces
            self.assertEqual(surfaces, [])
            self.assertEqual(
                window.status_text.get(),
                "Loft Between Two Curves requires curves with at least two points",
            )
            self.assertEqual(progress_dialogs, [])
            self.assertEqual(window.viewport.scene_calls[-1]["surface_previews"], [])
        finally:
            window.root.destroy()

    def test_scene_browser_multi_selects_curves_and_viewport_marks_each_selected(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            window.compute_section()
            first_curve = window.app_state.curve_collection.curves[0]
            window.add_section_plane()
            window.section_axis.set("X")
            window._on_section_axis_changed()
            window._set_section_offset(0.5, clamp=True, refresh=True)
            window.compute_section()
            second_curve = window.app_state.curve_collection.curves[1]

            tree = window.scene_browser.tree
            first_curve_node = curve_node_id(first_curve.id)
            second_curve_node = curve_node_id(second_curve.id)
            tree.selection_set((first_curve_node, second_curve_node))
            tree.focus(second_curve_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()

            self.assertEqual(window.app_state.selected_item, "curve")
            self.assertEqual(window.app_state.curve_collection.active_curve_id, second_curve.id)
            self.assertEqual(
                window.app_state.curve_collection.selected_curve_ids,
                {first_curve.id, second_curve.id},
            )
            self.assertTrue(first_curve.selected)
            self.assertTrue(second_curve.selected)
            self.assertEqual(tree.selection(), (first_curve_node, second_curve_node))
            self.assertEqual(window.status_text.get(), "Selected: 2 curves")
            self.assertTrue(all(curve.selected for curve in window.viewport.scene_calls[-1]["curve_results"]))
        finally:
            window.root.destroy()

    def test_curve_visibility_commands_hide_selected_unselected_and_show_all(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            window.compute_section()
            first_curve = window.app_state.curve_collection.curves[0]
            window.add_section_plane()
            window.section_axis.set("X")
            window._on_section_axis_changed()
            window._set_section_offset(0.5, clamp=True, refresh=True)
            window.compute_section()
            second_curve = window.app_state.curve_collection.curves[1]

            window.select_curve(first_curve.id)
            window._set_project_dirty(False)
            window.hide_selected_curves()

            self.assertFalse(first_curve.visible)
            self.assertTrue(second_curve.visible)
            self.assertEqual(window.app_state.curve_results, [second_curve])
            self.assertEqual(window.status_text.get(), "Hidden selected curve")
            self.assertTrue(window.project_dirty)

            window.show_all_curves()
            self.assertTrue(first_curve.visible)
            self.assertTrue(second_curve.visible)
            self.assertEqual(window.app_state.curve_results, [first_curve, second_curve])

            window.select_curve(first_curve.id)
            window.hide_unselected_curves()

            self.assertTrue(first_curve.visible)
            self.assertFalse(second_curve.visible)
            self.assertEqual(window.app_state.curve_results, [first_curve])
            self.assertEqual(window.status_text.get(), "Hidden 1 unselected curves")

            window.curves_menu.invoke(5)
            self.assertTrue(first_curve.visible)
            self.assertTrue(second_curve.visible)
            self.assertEqual(window.status_text.get(), "All curves visible")
        finally:
            window.root.destroy()

    def test_tiny_curve_commands_select_hide_delete_and_remove_surfaces(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            window.compute_section()
            regular_curve = window.app_state.curve_collection.curves[0]
            tiny_points = np.asarray([[0.0, 0.0, 0.0], [0.001, 0.0, 0.0]])
            tiny_curve = StoredCurve(
                id="curve-tiny",
                name="Tiny Curve",
                section_result_id=regular_curve.section_result_id,
                plane_id=regular_curve.plane_id,
                original_points=tiny_points.copy(),
                fitted_points=tiny_points.copy(),
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
            )
            add_curve(window.app_state.curve_collection, tiny_curve)
            surface = SurfacePatch(
                id="surface-tiny",
                name="Tiny Surface",
                source_curve_ids=[tiny_curve.id],
                surface_type="preview_fill",
            )
            add_surface(window.app_state.surface_collection, surface)
            window._refresh_viewport(reset_camera=False)

            tree = window.scene_browser.tree
            tiny_curve_node = curve_node_id(tiny_curve.id)
            self.assertEqual(tree.item(tiny_curve_node, "text"), "[V] Tiny Curve (tiny)")
            self.assertFalse(regular_curve.is_tiny_fragment)
            self.assertTrue(tiny_curve.is_tiny_fragment)

            window.select_tiny_curves()

            self.assertEqual(window.app_state.selected_item, "curve")
            self.assertEqual(window.app_state.curve_collection.selected_curve_ids, {tiny_curve.id})
            self.assertEqual(window.curve_tiny_text.get(), "Yes")
            self.assertEqual(window.status_text.get(), "Selected tiny curve")

            window.hide_tiny_curves()

            self.assertFalse(tiny_curve.visible)
            self.assertEqual(window.app_state.curve_results, [regular_curve])
            self.assertEqual(tree.item(tiny_curve_node, "text"), "[H] Tiny Curve (tiny)")
            self.assertEqual(window.status_text.get(), "Hidden tiny curve")

            window.show_all_curves()
            self.assertTrue(tiny_curve.visible)

            window.delete_tiny_curves()

            self.assertEqual(window.app_state.curve_collection.curves, [regular_curve])
            self.assertEqual(window.app_state.surface_collection.surfaces, [])
            self.assertFalse(tree.exists(tiny_curve_node))
            self.assertEqual(window.status_text.get(), "Deleted tiny curve")
        finally:
            window.root.destroy()

    def test_join_selected_curves_creates_repaired_curve_group_and_keeps_originals(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            first_points = np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
            second_points = np.asarray([[2.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
            first_curve = StoredCurve(
                id="curve-a",
                name="Fragment A",
                section_result_id="section-a",
                plane_id="plane-a",
                original_points=first_points.copy(),
                fitted_points=first_points.copy(),
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
            )
            second_curve = StoredCurve(
                id="curve-b",
                name="Fragment B",
                section_result_id="section-a",
                plane_id="plane-a",
                original_points=second_points.copy(),
                fitted_points=second_points.copy(),
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
            )
            add_curve(window.app_state.curve_collection, first_curve)
            add_curve(window.app_state.curve_collection, second_curve)
            window.select_curves([first_curve.id, second_curve.id], active_curve_id=first_curve.id)

            window.join_selected_curves()

            curves = window.app_state.curve_collection.curves
            joined_curve = curves[-1]
            self.assertEqual(curves[:2], [first_curve, second_curve])
            self.assertTrue(first_curve.visible)
            self.assertTrue(second_curve.visible)
            self.assertEqual(joined_curve.name, "Joined Curve 1")
            self.assertEqual(joined_curve.metadata["repair_type"], "join")
            self.assertEqual(joined_curve.metadata["source_curve_ids"], ["curve-a", "curve-b"])
            self.assertEqual(joined_curve.metadata["tolerance_used"], 0.01)
            self.assertTrue(
                np.allclose(
                    joined_curve.fitted_points,
                    [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
                )
            )
            self.assertEqual(window.app_state.curve_collection.selected_curve_ids, {joined_curve.id})
            self.assertEqual(
                window.status_text.get(),
                "Created joined curve from 2 curves (tolerance 0.010)",
            )

            tree = window.scene_browser.tree
            joined_node = curve_node_id(joined_curve.id)
            self.assertEqual(tree.item(NODE_CURVE_GROUP_REPAIRED, "text"), "[V] Repaired Curves")
            self.assertEqual(tree.get_children(NODE_CURVE_GROUP_REPAIRED), (joined_node,))
            self.assertEqual(tree.item(joined_node, "text"), "[V] Joined Curve 1 (repaired)")
        finally:
            window.root.destroy()

    def test_auto_close_selected_curve_creates_repaired_surface_source(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            points = np.asarray(
                [
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                    [0.5, 1.0, 0.0],
                    [0.001, 0.0, 0.0],
                ],
                dtype=float,
            )
            source_curve = StoredCurve(
                id="curve-open",
                name="Open Curve",
                section_result_id="section-a",
                plane_id="plane-a",
                original_points=points.copy(),
                fitted_points=points.copy(),
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
            )
            add_curve(window.app_state.curve_collection, source_curve)
            window.select_curve(source_curve.id)

            window.auto_close_selected_curve()

            repaired_curve = window.app_state.curve_collection.curves[-1]
            self.assertEqual(window.app_state.curve_collection.curves[0], source_curve)
            self.assertFalse(source_curve.is_closed)
            self.assertTrue(repaired_curve.is_closed)
            self.assertEqual(repaired_curve.name, "Auto-Closed Curve 1")
            self.assertEqual(repaired_curve.metadata["repair_type"], "auto_close")
            self.assertEqual(repaired_curve.metadata["source_curve_ids"], ["curve-open"])
            self.assertAlmostEqual(repaired_curve.metadata["original_endpoint_gap"], 0.001)
            self.assertEqual(window.app_state.curve_collection.selected_curve_ids, {repaired_curve.id})
            self.assertEqual(
                window.status_text.get(),
                "Created auto-closed curve (gap 0.001, tolerance 0.010)",
            )
            self.assertEqual(
                window.scene_browser.tree.get_children(NODE_CURVE_GROUP_REPAIRED),
                (curve_node_id(repaired_curve.id),),
            )

            window.create_surface_from_curves()

            surface = window.app_state.surface_collection.surfaces[0]
            self.assertEqual(surface.source_curve_ids, [repaired_curve.id])
            self.assertEqual(surface.surface_type, "preview_fill")
            self.assertTrue(surface.metadata["preview_available"])
            self.assertEqual(
                window.status_text.get(),
                "Filled Fill Surface 1 from 1 curve",
            )
        finally:
            window.root.destroy()

    def test_simplify_selected_curve_creates_generated_curve_and_keeps_original(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            source_points = np.asarray(
                [
                    [0.0, 0.0, 0.0],
                    [1.0, 0.002, 0.0],
                    [2.0, -0.002, 0.0],
                    [3.0, 0.002, 0.0],
                    [4.0, 0.0, 0.0],
                ],
                dtype=float,
            )
            source_curve = StoredCurve(
                id="curve-source",
                name="Source Curve",
                section_result_id="missing-section",
                plane_id="plane-a",
                original_points=source_points.copy(),
                fitted_points=source_points.copy(),
                mean_error=0.12,
                max_error=0.34,
                is_closed=False,
            )
            add_curve(window.app_state.curve_collection, source_curve)
            window.select_curve(source_curve.id)

            window.simplify_selected_curve()

            curves = window.app_state.curve_collection.curves
            simplified_curve = curves[-1]
            self.assertEqual(curves[0], source_curve)
            self.assertTrue(np.allclose(source_curve.fitted_points, source_points))
            self.assertEqual(simplified_curve.name, "Simplified Curve 1")
            self.assertEqual(simplified_curve.metadata["operation"], "simplify")
            self.assertEqual(simplified_curve.metadata["source_curve_id"], source_curve.id)
            self.assertLess(len(simplified_curve.fitted_points), len(source_points))
            self.assertEqual(window.app_state.curve_collection.selected_curve_ids, {simplified_curve.id})
            self.assertIn("Created simplified curve", window.status_text.get())

            generated_node = curve_node_id(simplified_curve.id)
            tree = window.scene_browser.tree
            self.assertIn(generated_node, tree.get_children(NODE_CURVE_GROUP_REPAIRED))
            self.assertEqual(tree.item(generated_node, "text"), "[V] Simplified Curve 1 (repaired)")
        finally:
            window.root.destroy()

    def test_smooth_selected_curve_creates_generated_curve_and_keeps_original(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            source_points = np.asarray(
                [
                    [0.0, 0.0, 0.0],
                    [1.0, 1.0, 0.0],
                    [2.0, -1.0, 0.0],
                    [3.0, 0.0, 0.0],
                ],
                dtype=float,
            )
            source_curve = StoredCurve(
                id="curve-source",
                name="Source Curve",
                section_result_id="missing-section",
                plane_id="plane-a",
                original_points=source_points.copy(),
                fitted_points=source_points.copy(),
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
            )
            add_curve(window.app_state.curve_collection, source_curve)
            window.select_curve(source_curve.id)

            window.smooth_selected_curve()

            smoothed_curve = window.app_state.curve_collection.curves[-1]
            self.assertEqual(window.app_state.curve_collection.curves[0], source_curve)
            self.assertTrue(np.allclose(source_curve.fitted_points, source_points))
            self.assertEqual(smoothed_curve.name, "Smoothed Curve 1")
            self.assertEqual(smoothed_curve.metadata["operation"], "smooth")
            self.assertEqual(smoothed_curve.metadata["source_curve_id"], source_curve.id)
            self.assertEqual(len(smoothed_curve.fitted_points), len(source_points))
            self.assertTrue(np.allclose(smoothed_curve.fitted_points[0], source_points[0]))
            self.assertTrue(np.allclose(smoothed_curve.fitted_points[-1], source_points[-1]))
            self.assertEqual(window.app_state.curve_collection.selected_curve_ids, {smoothed_curve.id})
            self.assertIn("Created smoothed curve", window.status_text.get())

            generated_node = curve_node_id(smoothed_curve.id)
            self.assertIn(
                generated_node,
                window.scene_browser.tree.get_children(NODE_CURVE_GROUP_REPAIRED),
            )
        finally:
            window.root.destroy()

    def test_create_surface_rejects_open_single_curve_and_more_than_two_curves(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            window.compute_section()
            first_curve = window.app_state.curve_collection.curves[0]
            window.select_curve(first_curve.id)
            window.surfaces_menu.invoke(0)

            self.assertEqual(
                window.status_text.get(),
                "Fill Closed Curve requires one closed curve",
            )
            self.assertEqual(window.app_state.surface_collection.surfaces, [])
            window.surfaces_menu.invoke(1)
            self.assertEqual(window.status_text.get(), "Select exactly two curves to loft")

            points = np.asarray(
                [
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                ],
                dtype=float,
            )
            second_curve = StoredCurve(
                id="curve-2",
                name="Curve 2",
                section_result_id="section-result-2",
                plane_id="plane-2",
                original_points=points.copy(),
                fitted_points=points.copy(),
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
            )
            third_curve = StoredCurve(
                id="curve-3",
                name="Curve 3",
                section_result_id="section-result-3",
                plane_id="plane-3",
                original_points=points.copy(),
                fitted_points=points.copy(),
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
            )
            add_curve(window.app_state.curve_collection, second_curve)
            add_curve(window.app_state.curve_collection, third_curve)
            window.select_curves(
                [first_curve.id, second_curve.id, third_curve.id],
                active_curve_id=third_curve.id,
            )
            window.surfaces_menu.invoke(1)

            self.assertEqual(
                window.status_text.get(),
                "Select exactly two curves to loft",
            )
            self.assertEqual(window.app_state.surface_collection.surfaces, [])
        finally:
            window.root.destroy()

    def test_visible_surface_preview_ignores_source_curve_visibility(self) -> None:
        closed_points = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0],
            ],
            dtype=float,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            curve = StoredCurve(
                id="curve-1",
                name="Curve 1",
                section_result_id="section-result-1",
                plane_id="plane-1",
                original_points=closed_points.copy(),
                fitted_points=closed_points.copy(),
                mean_error=0.0,
                max_error=0.0,
                is_closed=True,
                visible=False,
            )
            add_curve(window.app_state.curve_collection, curve)
            surface = SurfacePatch(
                id="surface-1",
                name="Surface 1",
                source_curve_ids=[curve.id],
                surface_type="placeholder",
                visible=True,
            )
            add_surface(window.app_state.surface_collection, surface)

            window._refresh_viewport(reset_camera=False)

            previews = window.viewport.scene_calls[-1]["surface_previews"]
            self.assertEqual(len(previews), 1)
            self.assertEqual(previews[0].source_surface_id, surface.id)

            surface.visible = False
            window._refresh_viewport(reset_camera=False)

            self.assertEqual(window.viewport.scene_calls[-1]["surface_previews"], [])
        finally:
            window.root.destroy()

    def test_model_transform_preserves_generated_surfaces_and_restores_preview(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            window.compute_section()
            source_curve = window.app_state.curve_collection.curves[0]
            _make_curve_closed(source_curve)
            window.select_curve(source_curve.id)
            window.create_surface_from_curves()
            surface = window.app_state.surface_collection.surfaces[0]
            surface_node = surface_node_id(surface.id)

            self.assertEqual(len(window.viewport.scene_calls[-1]["surface_previews"]), 1)
            self.assertTrue(window.scene_browser.tree.exists(surface_node))

            window.select_model()
            window._start_active_transform("move")

            self.assertEqual(window.app_state.surface_collection.surfaces, [surface])
            self.assertTrue(window.scene_browser.tree.exists(surface_node))
            self.assertEqual(window.viewport.scene_calls[-1]["surface_previews"], [])
            self.assertEqual(window.viewport.scene_calls[-1]["curve_results"], [])
            self.assertIsNone(window.viewport.scene_calls[-1]["section_result"])

            window._end_active_transform(commit=True, status="Transform confirmed")

            self.assertEqual(window.app_state.surface_collection.surfaces, [surface])
            self.assertTrue(window.scene_browser.tree.exists(surface_node))
            self.assertEqual(len(window.viewport.scene_calls[-1]["surface_previews"]), 1)
            self.assertEqual(
                window.viewport.scene_calls[-1]["surface_previews"][0].source_surface_id,
                surface.id,
            )
            self.assertEqual(window.status_text.get(), GENERATED_GEOMETRY_TRANSFORM_WARNING)
        finally:
            window.root.destroy()

    def test_deleting_source_curve_removes_dependent_placeholder_surface(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            window.compute_section()
            stored_result = window.app_state.section_collection.results[0]
            source_curve = window.app_state.curve_collection.curves[0]
            source_plane = window.app_state.section_collection.planes[0]
            _make_curve_closed(source_curve)
            window.select_curve(source_curve.id)
            window.curves_menu.invoke(0)
            self.assertEqual(len(window.app_state.surface_collection.surfaces), 1)

            window.select_curve(source_curve.id)
            window.delete_selected_curve()

            self.assertEqual(window.app_state.curve_collection.curves, [])
            self.assertEqual(window.app_state.surface_collection.surfaces, [])
            self.assertIsNone(window.app_state.surface_collection.active_surface_id)
            self.assertEqual(window.app_state.section_collection.results, [stored_result])
            self.assertEqual(window.app_state.section_collection.planes, [source_plane])
            self.assertFalse(window.scene_browser.tree.exists(NODE_SURFACES))
            self.assertEqual(window.status_text.get(), "Deleted: Section 1 Curve 1")
        finally:
            window.root.destroy()

    def test_add_section_plane_command_creates_active_plane_and_updates_browser(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            first_plane = window.app_state.section_collection.planes[0]
            window._set_section_offset(0.5, clamp=True, refresh=True)
            window.section_axis.set("X")
            window._on_section_axis_changed()

            window.sections_menu.invoke(0)

            planes = window.app_state.section_collection.planes
            self.assertEqual(len(planes), 2)
            self.assertIs(planes[0], first_plane)
            second_plane = planes[1]
            self.assertEqual(first_plane.name, "Section Plane 1")
            self.assertEqual(second_plane.name, "Section Plane 2")
            self.assertEqual(second_plane.axis, "X")
            self.assertEqual(second_plane.offset, 0.5)
            self.assertFalse(second_plane.visible)
            self.assertEqual(window.app_state.section_collection.active_plane_id, second_plane.id)
            self.assertFalse(first_plane.selected)
            self.assertTrue(second_plane.selected)
            self.assertEqual(window.section_axis.get(), "X")
            self.assertEqual(window.section_offset.get(), 0.5)
            self.assertEqual(window.section_offset_text.get(), "0.500")
            self.assertEqual(window.status_text.get(), "Added: Section Plane 2")
            self.assertIsNone(window.app_state.section_result)
            self.assertEqual(window.section_result_text.get(), "Section result: none")

            tree = window.scene_browser.tree
            first_node = section_plane_node_id(first_plane.id)
            second_node = section_plane_node_id(second_plane.id)
            self.assertEqual(tree.get_children(NODE_SECTION_PLANES), (first_node, second_node))
            self.assertEqual(tree.item(first_node, "text"), "[H] Section Plane 1")
            self.assertEqual(tree.item(second_node, "text"), "[H] Section Plane 2")
            self.assertEqual(tree.selection(), (second_node,))
            self.assertEqual(window.viewport.scene_calls[-1]["selected_item"], "section_plane")
            self.assertEqual(window.viewport.scene_calls[-1]["section_axis"], "X")
            self.assertEqual(window.viewport.scene_calls[-1]["section_offset"], 0.5)
            self.assertEqual(
                window.viewport.scene_calls[-1]["section_planes"],
                window.app_state.section_collection.planes,
            )
            self.assertEqual(
                window.viewport.scene_calls[-1]["active_section_plane_id"],
                second_plane.id,
            )

            window.section_axis.set("Y")
            window._on_section_axis_changed()
            window._set_section_offset(1.0, clamp=True, refresh=True)
            self.assertEqual(second_plane.axis, "Y")
            self.assertEqual(second_plane.offset, 1.0)

            tree.selection_set(first_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()
            self.assertEqual(window.app_state.section_collection.active_plane_id, first_plane.id)
            self.assertTrue(first_plane.selected)
            self.assertFalse(second_plane.selected)
            self.assertEqual(window.section_axis.get(), "X")
            self.assertEqual(window.section_offset.get(), 0.5)
            self.assertEqual(tree.selection(), (first_node,))

            tree.selection_set(second_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()
            self.assertEqual(window.app_state.section_collection.active_plane_id, second_plane.id)
            self.assertFalse(first_plane.selected)
            self.assertTrue(second_plane.selected)
            self.assertEqual(window.section_axis.get(), "Y")
            self.assertEqual(window.section_offset.get(), 1.0)
            self.assertEqual(tree.selection(), (second_node,))
        finally:
            window.root.destroy()

    def test_compute_section_stores_independent_results_for_active_planes(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            first_plane = window.app_state.section_collection.planes[0]
            window.compute_section()
            first_result = window.app_state.section_collection.results[0]
            self.assertEqual(first_result.name, "Section 1")
            self.assertEqual(first_result.plane_id, first_plane.id)
            self.assertEqual(first_result.axis, "Z")
            self.assertEqual(first_result.offset, 0.0)
            self.assertIs(window.app_state.section_result, first_result.result)
            self.assertEqual(window.section_result_text.get(), "Section result: Section 1 - 1 segments")
            first_curve = window.app_state.curve_collection.curves[0]
            self.assertEqual(first_curve.name, "Section 1 Curve 1")
            self.assertEqual(first_curve.section_result_id, first_result.id)
            self.assertEqual(first_curve.plane_id, first_plane.id)
            self.assertEqual(window.app_state.curve_results, [first_curve])

            window.add_section_plane()
            second_plane = window.app_state.section_collection.planes[1]
            window.section_axis.set("X")
            window._on_section_axis_changed()
            window._set_section_offset(0.5, clamp=True, refresh=True)
            window.compute_section()

            results = window.app_state.section_collection.results
            self.assertEqual(len(results), 2)
            second_result = results[1]
            self.assertEqual(second_result.name, "Section 2")
            self.assertEqual(second_result.plane_id, second_plane.id)
            self.assertEqual(second_result.axis, "X")
            self.assertEqual(second_result.offset, 0.5)
            self.assertIs(window.app_state.section_result, second_result.result)
            self.assertEqual(window.section_result_text.get(), "Section result: Section 2 - 1 segments")
            self.assertEqual(window.status_text.get(), "Section computed: Section 2 - 1 segments")
            second_curve = window.app_state.curve_collection.curves[1]
            self.assertEqual(second_curve.name, "Section 2 Curve 1")
            self.assertEqual(second_curve.section_result_id, second_result.id)
            self.assertEqual(second_curve.plane_id, second_plane.id)
            self.assertEqual(window.app_state.curve_results, [first_curve, second_curve])
            self.assertEqual(
                window.viewport.scene_calls[-1]["curve_results"],
                [first_curve, second_curve],
            )

            tree = window.scene_browser.tree
            first_result_node = section_result_node_id(first_result.id)
            second_result_node = section_result_node_id(second_result.id)
            first_curve_group = curve_group_node_id(first_result.id)
            second_curve_group = curve_group_node_id(second_result.id)
            first_curve_node = curve_node_id(first_curve.id)
            second_curve_node = curve_node_id(second_curve.id)
            self.assertEqual(
                tree.get_children(NODE_SECTION_RESULTS),
                (first_result_node, second_result_node),
            )
            self.assertEqual(tree.item(first_result_node, "text"), "[V] Section 1")
            self.assertEqual(tree.item(second_result_node, "text"), "[V] Section 2")
            self.assertEqual(
                tree.get_children(NODE_CURVES),
                (first_curve_group, second_curve_group),
            )
            self.assertEqual(tree.get_children(first_curve_group), (first_curve_node,))
            self.assertEqual(tree.get_children(second_curve_group), (second_curve_node,))
            self.assertEqual(tree.item(first_curve_node, "text"), "[V] Section 1 Curve 1")
            self.assertEqual(tree.item(second_curve_node, "text"), "[V] Section 2 Curve 1")

            first_plane_node = section_plane_node_id(first_plane.id)
            tree.selection_set(first_plane_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()
            self.assertEqual(window.app_state.section_collection.active_plane_id, first_plane.id)
            self.assertEqual(window.app_state.section_collection.results, [first_result, second_result])

            window.clear_section()
            self.assertEqual(window.app_state.section_collection.results, [second_result])
            self.assertIs(window.app_state.section_result, second_result.result)
            self.assertEqual(window.section_result_text.get(), "Section result: Section 2 - 1 segments")
            self.assertEqual(tree.get_children(NODE_SECTION_RESULTS), (second_result_node,))
            self.assertEqual(window.app_state.curve_collection.curves, [second_curve])
            self.assertEqual(window.app_state.curve_results, [second_curve])
            self.assertEqual(tree.get_children(NODE_CURVES), (second_curve_group,))
            self.assertEqual(tree.get_children(second_curve_group), (second_curve_node,))
        finally:
            window.root.destroy()

    def test_compute_section_uses_rotated_plane_origin_and_normal(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            active_plane = window.app_state.section_collection.planes[0]
            normal = np.asarray([1.0, 0.0, -1.0], dtype=float)
            normal = normal / np.linalg.norm(normal)
            set_plane_origin_normal(
                active_plane,
                np.asarray([0.0, 0.0, 0.0], dtype=float),
                normal,
            )
            window._sync_section_controls_from_plane_orientation(active_plane)

            window.compute_section()

            stored_result = window.app_state.section_collection.results[0]
            self.assertTrue(stored_result.is_arbitrary_plane)
            self.assertTrue(stored_result.result.is_arbitrary_plane)
            self.assertTrue(np.allclose(stored_result.plane_origin, [0.0, 0.0, 0.0]))
            self.assertTrue(np.allclose(stored_result.plane_normal, normal))
            self.assertEqual(
                window.status_text.get(),
                "Computed arbitrary section from Section Plane 1",
            )
            self.assertGreater(stored_result.result.segment_count, 0)
            self.assertEqual(len(window.app_state.curve_collection.curves), 1)
            self.assertEqual(
                window.app_state.curve_collection.curves[0].section_result_id,
                stored_result.id,
            )
        finally:
            window.root.destroy()

    def test_curve_selection_visibility_and_delete_preserve_section_results(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            first_plane = window.app_state.section_collection.planes[0]
            window.compute_section()
            first_result = window.app_state.section_collection.results[0]
            first_curve = window.app_state.curve_collection.curves[0]
            window.add_section_plane()
            second_plane = window.app_state.section_collection.planes[1]
            window.section_axis.set("X")
            window._on_section_axis_changed()
            window._set_section_offset(0.5, clamp=True, refresh=True)
            window.compute_section()
            second_result = window.app_state.section_collection.results[1]
            second_curve = window.app_state.curve_collection.curves[1]

            tree = window.scene_browser.tree
            first_curve_node = curve_node_id(first_curve.id)
            second_curve_node = curve_node_id(second_curve.id)
            self.assertEqual(curve_id_from_node(first_curve_node), first_curve.id)

            tree.selection_set(first_curve_node)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()

            self.assertEqual(window.app_state.selected_item, "curve")
            self.assertEqual(window.app_state.curve_collection.active_curve_id, first_curve.id)
            self.assertEqual(window.app_state.curve_collection.selected_curve_ids, {first_curve.id})
            self.assertTrue(first_curve.selected)
            self.assertFalse(second_curve.selected)
            self.assertEqual(tree.selection(), (first_curve_node,))
            self.assertEqual(window.current_workbench.get(), "Curves")
            self.assertEqual(window.curve_context_frame.winfo_manager(), "grid")
            self.assertEqual(window.no_selection_frame.winfo_manager(), "grid")
            self.assertEqual(window.curve_name_text.get(), "Section 1 Curve 1")
            self.assertEqual(window.curve_section_text.get(), "Section 1")
            self.assertEqual(window.curve_plane_text.get(), f"{first_plane.name} (Z = 0.000)")
            self.assertEqual(window.curve_point_count_text.get(), "2")
            self.assertEqual(window.curve_length_text.get(), "1.000")
            self.assertEqual(window.curve_endpoint_gap_text.get(), "1.000")
            self.assertEqual(window.curve_closed_text.get(), "Open")
            self.assertEqual(window.curve_tiny_text.get(), "No")
            self.assertTrue(window.curve_visible.get())
            self.assertEqual(window.viewport.scene_calls[-1]["curve_results"], [first_curve, second_curve])
            self.assertTrue(window.viewport.scene_calls[-1]["curve_results"][0].selected)
            self.assertFalse(window.viewport.scene_calls[-1]["curve_results"][1].selected)

            window._set_project_dirty(False)
            window.curve_name_text.set("Rim Curve")
            window._on_curve_name_changed()

            self.assertEqual(first_curve.name, "Rim Curve")
            self.assertEqual(tree.item(first_curve_node, "text"), "[V] Rim Curve")
            self.assertEqual(window.status_text.get(), "Selected: Rim Curve")
            self.assertTrue(window.project_dirty)

            window.curve_visible.set(False)
            window._on_curve_visibility_changed()

            self.assertFalse(first_curve.visible)
            self.assertTrue(second_curve.visible)
            self.assertEqual(window.app_state.curve_results, [second_curve])
            self.assertEqual(window.viewport.scene_calls[-1]["curve_results"], [second_curve])
            first_curve_group = curve_group_node_id(first_result.id)
            second_curve_group = curve_group_node_id(second_result.id)
            self.assertEqual(tree.get_children(NODE_CURVES), (first_curve_group, second_curve_group))
            self.assertEqual(tree.get_children(first_curve_group), (first_curve_node,))
            self.assertEqual(tree.get_children(second_curve_group), (second_curve_node,))
            self.assertEqual(tree.selection(), (first_curve_node,))

            window.curve_visible.set(True)
            window._on_curve_visibility_changed()

            self.assertTrue(first_curve.visible)
            self.assertEqual(window.app_state.curve_results, [first_curve, second_curve])
            self.assertEqual(window.viewport.scene_calls[-1]["curve_results"], [first_curve, second_curve])

            window.curve_visible.set(False)
            window._on_curve_visibility_changed()

            window.curves_menu.invoke(6)

            self.assertEqual(window.app_state.section_collection.results, [first_result, second_result])
            self.assertEqual(window.app_state.section_collection.planes, [first_plane, second_plane])
            self.assertEqual(window.app_state.curve_collection.curves, [second_curve])
            self.assertEqual(window.app_state.curve_collection.active_curve_id, second_curve.id)
            self.assertEqual(window.app_state.curve_collection.selected_curve_ids, {second_curve.id})
            self.assertEqual(window.app_state.curve_results, [second_curve])
            self.assertEqual(tree.get_children(NODE_CURVES), (second_curve_group,))
            self.assertEqual(tree.get_children(second_curve_group), (second_curve_node,))
            self.assertEqual(tree.selection(), (second_curve_node,))
            self.assertEqual(window.status_text.get(), "Deleted: Rim Curve")
            self.assertEqual(window.curve_section_text.get(), "Section 2")
            self.assertEqual(window.curve_plane_text.get(), f"{second_plane.name} (X = 0.500)")
        finally:
            window.root.destroy()

    def test_clear_all_section_results_removes_all_result_nodes(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            window.compute_section()
            window.add_section_plane()
            window.section_axis.set("X")
            window._on_section_axis_changed()
            window._set_section_offset(0.5, clamp=True, refresh=True)
            window.compute_section()

            self.assertEqual(len(window.app_state.section_collection.results), 2)
            self.assertEqual(len(window.app_state.curve_collection.curves), 2)
            self.assertTrue(window.scene_browser.tree.exists(NODE_SECTION_RESULTS))
            self.assertTrue(window.scene_browser.tree.exists(NODE_CURVES))

            window.sections_menu.invoke(4)

            self.assertEqual(window.app_state.section_collection.results, [])
            self.assertIsNone(window.app_state.section_result)
            self.assertEqual(window.app_state.curve_collection.curves, [])
            self.assertIsNone(window.app_state.curve_collection.active_curve_id)
            self.assertEqual(window.app_state.curve_results, [])
            self.assertEqual(window.section_result_text.get(), "Section result: none")
            self.assertEqual(window.status_text.get(), "All section results cleared")
            self.assertFalse(window.scene_browser.tree.exists(NODE_SECTION_RESULTS))
            self.assertFalse(window.scene_browser.tree.exists(NODE_CURVES))
            self.assertEqual(len(window.app_state.section_collection.planes), 2)
            self.assertEqual(window.viewport.scene_calls[-1]["section_result"], None)
            self.assertEqual(window.viewport.scene_calls[-1]["curve_results"], [])
        finally:
            window.root.destroy()

    def test_delete_active_section_plane_removes_results_and_restores_default(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            first_plane = window.app_state.section_collection.planes[0]
            window.compute_section()
            first_result = window.app_state.section_collection.results[0]
            first_curve = window.app_state.curve_collection.curves[0]
            window.add_section_plane()
            second_plane = window.app_state.section_collection.planes[1]
            window.section_axis.set("X")
            window._on_section_axis_changed()
            window._set_section_offset(0.5, clamp=True, refresh=True)
            window.compute_section()
            second_result = window.app_state.section_collection.results[1]
            second_curve = window.app_state.curve_collection.curves[1]

            window.sections_menu.invoke(1)

            self.assertEqual(window.app_state.section_collection.planes, [first_plane])
            self.assertEqual(window.app_state.section_collection.active_plane_id, first_plane.id)
            self.assertTrue(first_plane.selected)
            self.assertEqual(window.app_state.section_collection.results, [first_result])
            self.assertNotIn(second_result, window.app_state.section_collection.results)
            self.assertEqual(window.app_state.curve_collection.curves, [first_curve])
            self.assertNotIn(second_curve, window.app_state.curve_collection.curves)
            self.assertEqual(window.app_state.curve_results, [first_curve])
            self.assertIs(window.app_state.section_result, first_result.result)
            self.assertEqual(window.section_result_text.get(), "Section result: Section 1 - 1 segments")
            self.assertEqual(window.section_axis.get(), "Z")
            self.assertEqual(window.section_offset.get(), 0.0)
            self.assertEqual(window.app_state.selected_item, "section_plane")
            self.assertEqual(window.status_text.get(), "Deleted: Section Plane 2")

            tree = window.scene_browser.tree
            first_plane_node = section_plane_node_id(first_plane.id)
            first_result_node = section_result_node_id(first_result.id)
            first_curve_group = curve_group_node_id(first_result.id)
            first_curve_node = curve_node_id(first_curve.id)
            self.assertEqual(tree.get_children(NODE_SECTION_PLANES), (first_plane_node,))
            self.assertEqual(tree.get_children(NODE_SECTION_RESULTS), (first_result_node,))
            self.assertEqual(tree.get_children(NODE_CURVES), (first_curve_group,))
            self.assertEqual(tree.get_children(first_curve_group), (first_curve_node,))
            self.assertEqual(tree.selection(), (first_plane_node,))

            window.sections_menu.invoke(1)

            restored_plane = window.app_state.section_collection.planes[0]
            restored_node = section_plane_node_id(restored_plane.id)
            self.assertEqual(len(window.app_state.section_collection.planes), 1)
            self.assertIsNot(restored_plane, first_plane)
            self.assertEqual(restored_plane.name, "Section Plane 1")
            self.assertEqual(restored_plane.axis, "Z")
            self.assertEqual(restored_plane.offset, 0.0)
            self.assertTrue(restored_plane.selected)
            self.assertEqual(window.app_state.section_collection.active_plane_id, restored_plane.id)
            self.assertEqual(window.app_state.section_collection.results, [])
            self.assertEqual(window.app_state.curve_collection.curves, [])
            self.assertEqual(window.app_state.curve_results, [])
            self.assertIsNone(window.app_state.section_result)
            self.assertEqual(window.section_result_text.get(), "Section result: none")
            self.assertFalse(tree.exists(NODE_SECTION_RESULTS))
            self.assertFalse(tree.exists(NODE_CURVES))
            self.assertEqual(tree.get_children(NODE_SECTION_PLANES), (restored_node,))
            self.assertEqual(tree.selection(), (restored_node,))

            window.clear_selection()
            window.sections_menu.invoke(1)

            next_restored_plane = window.app_state.section_collection.planes[0]
            self.assertEqual(len(window.app_state.section_collection.planes), 1)
            self.assertIsNot(next_restored_plane, restored_plane)
            self.assertEqual(window.app_state.selected_item, "section_plane")
            self.assertIn("Deleted: Section Plane 1", window.status_text.get())
        finally:
            window.root.destroy()

    def test_loading_mesh_shows_progress_stages_and_disables_open_model(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        observed_states: list[tuple[str, str, str]] = []
        progress_dialogs: list[object] = []

        class RecordingProgressDialog:
            def __init__(self, _parent: object, file_name: str) -> None:
                self.file_name = file_name
                self.stages: list[str] = []
                self.closed = False
                progress_dialogs.append(self)
                observed_states.append(
                    (
                        "created",
                        str(window.open_model_button.cget("state")),
                        window.file_menu.entrycget(OPEN_MODEL_MENU_INDEX, "state"),
                    )
                )

            def update_stage(self, stage: str) -> None:
                self.stages.append(stage)
                observed_states.append(
                    (
                        stage,
                        str(window.open_model_button.cget("state")),
                        window.file_menu.entrycget(OPEN_MODEL_MENU_INDEX, "state"),
                    )
                )

            def close(self) -> None:
                self.closed = True

        try:
            with (
                patch("app.main_window.LoadProgressDialog", RecordingProgressDialog),
                patch(
                    "app.main_window.load_mesh",
                    return_value=LoadedMesh(mesh=mesh, metadata=metadata),
                ),
            ):
                window.load_model(Path("sample.stl"))

            progress = progress_dialogs[0]
            self.assertEqual(progress.file_name, "sample.stl")
            self.assertEqual(progress.stages, list(LOAD_PROGRESS_STAGES))
            self.assertTrue(progress.closed)
            self.assertTrue(observed_states)
            self.assertTrue(
                all(
                    button_state == "disabled" and menu_state == "disabled"
                    for _stage, button_state, menu_state in observed_states
                )
            )
            self.assertEqual(str(window.open_model_button.cget("state")), "normal")
            self.assertEqual(
                window.file_menu.entrycget(OPEN_MODEL_MENU_INDEX, "state"),
                "normal",
            )
            self.assertEqual(
                window.status_text.get(),
                "Source: 1 tris | Display: 1 tris | Reduction: 0.0% | "
                "No proxy (Medium) | Full-resolution source preserved",
            )
        finally:
            window.root.destroy()

    def test_loading_mesh_failure_closes_progress_and_reenables_open_model(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        progress_dialogs: list[object] = []

        class RecordingProgressDialog:
            def __init__(self, _parent: object, file_name: str) -> None:
                self.file_name = file_name
                self.stages: list[str] = []
                self.closed = False
                progress_dialogs.append(self)

            def update_stage(self, stage: str) -> None:
                self.stages.append(stage)

            def close(self) -> None:
                self.closed = True

        try:
            with (
                patch("app.main_window.LoadProgressDialog", RecordingProgressDialog),
                patch("app.main_window.load_mesh", side_effect=ValueError("bad mesh")),
                patch("app.main_window.messagebox.showerror") as show_error,
            ):
                window.load_model(Path("broken.stl"))

            progress = progress_dialogs[0]
            self.assertEqual(progress.file_name, "broken.stl")
            self.assertEqual(progress.stages, [LOAD_PROGRESS_STAGES[0]])
            self.assertTrue(progress.closed)
            show_error.assert_called_once_with("Could not open model", "bad mesh")
            self.assertIsNone(window.app_state.mesh_object)
            self.assertEqual(window.status_text.get(), "No selection")
            self.assertEqual(str(window.open_model_button.cget("state")), "normal")
            self.assertEqual(
                window.file_menu.entrycget(OPEN_MODEL_MENU_INDEX, "state"),
                "normal",
            )
        finally:
            window.root.destroy()

    def test_selecting_model_shows_object_context_and_live_transform(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            window.select_model()
            window._set_project_dirty(False)
            self.assertEqual(window.app_state.selected_item, "model")
            self.assertEqual(window.status_text.get(), "Selected: sample.stl")
            self.assertEqual(window.current_workbench.get(), "Transform")
            self.assertEqual(window.no_selection_frame.winfo_manager(), "grid")
            self.assertEqual(window.model_context_frame.winfo_manager(), "grid")
            self.assertEqual(window.section_context_frame.winfo_manager(), "grid")
            self.assertEqual(window.selected_object_text.get(), "sample.stl")
            self.assertEqual(window.viewport.scene_calls[-1]["selected_item"], "model")
            self.assertIsNotNone(window.viewport.scene_calls[-1]["object_origin"])

            window.location_x.set("1.500")
            window._on_object_transform_changed()
            self.assertEqual(window.status_text.get(), "Transforms update live")
            self.assertTrue(window.project_dirty)
            self.assertEqual(window.root.title(), "openRetop - Untitled Project *")
            self.assertAlmostEqual(window.app_state.mesh_object.location[0], 1.5)
            self.assertIsNotNone(window.app_state.mesh_object.transform_matrix)
            self.assertEqual(window.viewport.scene_calls[-1]["mesh"], window.app_state.mesh_object.display_mesh)
            self.assertIsNotNone(window.viewport.scene_calls[-1]["transform_matrix"])

            window.rotation_z.set("90.000")
            window._on_object_transform_changed()
            mapped_origin = window._current_object_matrix() @ np.append(
                window.app_state.mesh_object.origin,
                1.0,
            )
            self.assertTrue(np.allclose(mapped_origin[:3], window.app_state.mesh_object.location))

            window.frame_selected()
            self.assertEqual(window.viewport.frame_count, 1)
            self.assertEqual(window.status_text.get(), "View framed to selection")
        finally:
            window.root.destroy()

    def test_delete_selected_mesh_clears_scene_after_confirmation(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _build_two_section_scene(window)
            window.select_model()
            window._set_project_dirty(False)
            reset_count = window.viewport.reset_count
            with patch("app.main_window.messagebox.askyesno", return_value=True) as confirm:
                window._handle_shortcut("Delete")

            confirm.assert_called_once()
            confirmation_text = confirm.call_args.args[1]
            self.assertIn("Delete mesh and all generated data?", confirmation_text)
            self.assertIn("- 2 section planes", confirmation_text)
            self.assertIn("- 2 section results", confirmation_text)
            self.assertIn("- 2 curves", confirmation_text)
            self.assertIn("- 2 surfaces", confirmation_text)
            self.assertIsNone(window.app_state.mesh_object)
            self.assertEqual(window.app_state.section_collection.planes, [])
            self.assertEqual(window.app_state.section_collection.results, [])
            self.assertEqual(window.app_state.curve_collection.curves, [])
            self.assertEqual(window.app_state.surface_collection.surfaces, [])
            self.assertEqual(window.status_text.get(), "Mesh deleted")
            self.assertTrue(window.project_dirty)
            self.assertEqual(window.root.title(), "openRetop - Untitled Project *")
            self.assertEqual(str(window.select_model_button.cget("state")), "disabled")
            self.assertEqual(str(window.select_section_plane_button.cget("state")), "disabled")
            self.assertEqual(window.viewport.reset_count, reset_count)
            self.assertIsNone(window.viewport.scene_calls[-1]["mesh"])
            self.assertIsNone(window.viewport.scene_calls[-1]["selected_item"])
            self.assertEqual(window.scene_browser.tree.get_children(NODE_SCENE), (NODE_EMPTY_SCENE,))
            self.assertEqual(window.scene_browser.tree.item(NODE_EMPTY_SCENE, "text"), "No mesh loaded")
        finally:
            window.root.destroy()

    def test_save_after_delete_mesh_does_not_reference_old_mesh_path(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _build_two_section_scene(window)
            window.select_model()
            with patch("app.main_window.messagebox.askyesno", return_value=True):
                window._handle_shortcut("Delete")

            with TemporaryDirectory() as tmpdir:
                project_path = Path(tmpdir) / "empty.openretop"
                with (
                    patch(
                        "app.main_window.filedialog.asksaveasfilename",
                        return_value=str(project_path),
                    ),
                    patch("app.main_window.messagebox.showerror") as show_error,
                ):
                    window.save_project_as()

                show_error.assert_not_called()
                project = load_project(project_path)
                self.assertIsNone(project.mesh_path)
                self.assertIsNone(project.mesh_name)
                self.assertEqual(project.section_planes, [])
                self.assertEqual(project.section_results, [])
                self.assertEqual(project.curves, [])
                self.assertEqual(project.surfaces, [])
        finally:
            window.root.destroy()

    def test_hotkey_move_cancel_and_confirm_update_mesh_location(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            self.assertIsNotNone(window.viewport.selection_callback)
            self.assertIsNotNone(window.viewport.pointer_callback)
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            window.select_model()
            start_location = window.app_state.mesh_object.location.copy()
            window._on_viewport_pointer_event("motion", 10, 10)
            window._handle_shortcut("G")
            self.assertTrue(window.status_text.get().startswith("Move mode - press X/Y/Z"))
            self.assertEqual(window.current_mode_text.get(), "Transform: Move")
            self.assertTrue(window.command_prompt_text.get().startswith("Move mode"))
            self.assertIn("Enter/click confirm", window.hotkey_hint_text.get())
            self.assertEqual(window.viewport.scene_calls[-1]["active_transform_mode"], "move")

            window._handle_shortcut("X")
            self.assertEqual(window.status_text.get(), "Move mode - X axis")
            self.assertEqual(window.command_prompt_text.get(), "Move mode - X axis")
            self.assertEqual(window.viewport.scene_calls[-1]["active_transform_axis"], "X")
            window._handle_shortcut("X")
            self.assertTrue(window.status_text.get().startswith("Move mode - press X/Y/Z"))
            self.assertIsNone(window.viewport.scene_calls[-1]["active_transform_axis"])
            window._handle_shortcut("X")

            handled = window._on_viewport_pointer_event("motion", 80, 10)
            self.assertTrue(handled)
            moved_location = window.app_state.mesh_object.location.copy()
            self.assertGreater(moved_location[0], start_location[0])
            self.assertAlmostEqual(moved_location[1], start_location[1])
            self.assertAlmostEqual(moved_location[2], start_location[2])
            self.assertIn("Delta X:", window.status_text.get())
            self.assertEqual(window.location_x.get(), f"{moved_location[0]:.3f}")

            window._handle_shortcut("Escape")
            self.assertEqual(window.status_text.get(), "Transform cancelled")
            self.assertEqual(window.current_mode_text.get(), "No Mode")
            self.assertTrue(np.allclose(window.app_state.mesh_object.location, start_location))
            self.assertEqual(window.location_x.get(), f"{start_location[0]:.3f}")
            self.assertIsNone(window.viewport.scene_calls[-1]["active_transform_mode"])

            window._on_viewport_pointer_event("motion", 0, 0)
            window._handle_shortcut("G")
            window._handle_shortcut("X")
            window._on_viewport_pointer_event("motion", 100, 0)
            normal_location = window.app_state.mesh_object.location.copy()
            window._handle_shortcut("Escape")

            window._on_viewport_pointer_event("motion", 0, 0)
            window._handle_shortcut("G")
            window._handle_shortcut("X")
            window._on_viewport_pointer_event("motion", 100, 0, shift_pressed=True)
            fine_location = window.app_state.mesh_object.location.copy()
            normal_delta = normal_location[0] - start_location[0]
            fine_delta = fine_location[0] - start_location[0]
            self.assertAlmostEqual(fine_delta, normal_delta * 0.1, places=6)
            window._handle_shortcut("Escape")

            window._handle_shortcut("G")
            window._on_viewport_pointer_event("motion", 150, 10)
            confirmed_location = window.app_state.mesh_object.location.copy()
            window._handle_shortcut("Enter")
            self.assertEqual(window.status_text.get(), "Transform confirmed")
            self.assertTrue(np.allclose(window.app_state.mesh_object.location, confirmed_location))
            self.assertGreater(confirmed_location[0], start_location[0])
        finally:
            window.root.destroy()

    def test_unconstrained_grab_uses_viewport_camera_vectors(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            window.viewport.camera_right = np.asarray([0.0, 1.0, 0.0], dtype=float)
            window.viewport.camera_up = np.asarray([0.0, 0.0, 1.0], dtype=float)
            window.select_model()
            start_location = window.app_state.mesh_object.location.copy()
            window._on_viewport_pointer_event("motion", 0, 0)
            window._handle_shortcut("G")

            handled = window._on_viewport_pointer_event("motion", 100, -50)
            moved_location = window.app_state.mesh_object.location.copy()
            delta = moved_location - start_location

            self.assertTrue(handled)
            self.assertAlmostEqual(delta[0], 0.0)
            self.assertGreater(delta[1], 0.0)
            self.assertGreater(delta[2], 0.0)
            self.assertIn("Delta Z:", window.status_text.get())
            window._handle_shortcut("Escape")
            self.assertTrue(np.allclose(window.app_state.mesh_object.location, start_location))
        finally:
            window.root.destroy()

    def test_hotkey_rotate_axis_constraint_updates_mesh_rotation_about_pivot(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            window.select_model()
            window._on_viewport_pointer_event("motion", 0, 0)
            window._handle_shortcut("R")
            self.assertEqual(
                window.status_text.get(),
                "Rotate mode - Z axis - move mouse horizontally",
            )
            self.assertEqual(window.current_mode_text.get(), "Transform: Rotate")
            self.assertEqual(
                window.command_prompt_text.get(),
                "Rotate mode - Z axis - move mouse horizontally",
            )
            self.assertEqual(window.viewport.scene_calls[-1]["active_transform_mode"], "rotate")
            self.assertEqual(window.viewport.scene_calls[-1]["active_transform_axis"], "Z")
            self.assertEqual(window.viewport.scene_calls[-1]["active_transform_angle_delta"], 0.0)
            window._handle_shortcut("X")
            self.assertEqual(window.status_text.get(), "Rotate mode - X axis - move mouse horizontally")
            self.assertEqual(window.viewport.scene_calls[-1]["active_transform_axis"], "X")
            self.assertEqual(window.viewport.scene_calls[-1]["active_transform_angle_delta"], 0.0)

            window._on_viewport_pointer_event("motion", 40, 0)
            self.assertGreater(window.app_state.mesh_object.rotation[0], 0.0)
            self.assertIn("20.0 deg", window.status_text.get())
            self.assertEqual(window.viewport.scene_calls[-1]["active_transform_angle_delta"], 20.0)
            self.assertEqual(window.rotation_x.get(), f"{window.app_state.mesh_object.rotation[0]:.3f}")
            self.assertEqual(window.rotation_y.get(), "0.000")
            self.assertEqual(window.rotation_z.get(), "0.000")

            mapped_origin = window._current_object_matrix() @ np.append(
                window.app_state.mesh_object.origin,
                1.0,
            )
            self.assertTrue(np.allclose(mapped_origin[:3], window.app_state.mesh_object.location))
        finally:
            window.root.destroy()

    def test_selecting_section_plane_shows_section_context_and_compute_clear(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            active_plane = window.app_state.section_collection.planes[0]
            self.assertEqual(active_plane.axis, "Z")
            self.assertEqual(active_plane.offset, 0.0)
            self.assertFalse(active_plane.visible)

            window.select_section_plane()
            self.assertEqual(window.app_state.selected_item, "section_plane")
            self.assertEqual(window.status_text.get(), "Selected: Section Plane")
            self.assertEqual(window.current_workbench.get(), "Sections")
            self.assertEqual(window.no_selection_frame.winfo_manager(), "grid")
            self.assertEqual(window.model_context_frame.winfo_manager(), "")
            self.assertEqual(window.section_context_frame.winfo_manager(), "grid")
            self.assertEqual(window.viewport.scene_calls[-1]["selected_item"], "section_plane")
            self.assertEqual(window.viewport.scene_calls[-1]["show_section_plane"], False)

            window._set_section_offset(0.5, clamp=True, refresh=True)
            self.assertEqual(window.section_plane_text.get(), "Section: Z = 0.500")
            self.assertEqual(window.status_text.get(), "Section plane: Z = 0.500")
            self.assertEqual(window.viewport.scene_calls[-1]["section_offset"], 0.5)
            self.assertEqual(active_plane.offset, 0.5)

            window.section_axis.set("X")
            window._on_section_axis_changed()
            self.assertEqual(active_plane.axis, "X")
            self.assertEqual(active_plane.offset, window.section_offset.get())

            window.reset_view()
            self.assertEqual(window.viewport.reset_count, 1)
            self.assertEqual(window.status_text.get(), "View reset")

            window.compute_section()
            self.assertEqual(window.status_text.get(), "Section computed: Section 1 - 1 segments")
            self.assertEqual(window.section_result_text.get(), "Section result: Section 1 - 1 segments")

            window.clear_section()
            self.assertEqual(window.status_text.get(), "Section cleared")
            self.assertEqual(window.section_result_text.get(), "Section result: none")
            self.assertIsNone(window.viewport.scene_calls[-1]["section_result"])
            self.assertEqual(window.viewport.scene_calls[-1]["show_section_plane"], False)

            window.clear_selection()
            self.assertIsNone(window.app_state.selected_item)
            self.assertEqual(window.viewport.scene_calls[-1]["show_section_plane"], False)

            window.show_section_plane.set(True)
            window._on_section_plane_visibility_changed()
            self.assertEqual(window.viewport.scene_calls[-1]["show_section_plane"], True)
            self.assertTrue(active_plane.visible)
        finally:
            window.root.destroy()

    def test_section_plane_hotkey_move_cancel_confirm_and_rotate(self) -> None:
        mesh = FakeMesh()
        metadata = MeshMetadata(
            file_path=Path("sample.stl"),
            file_name="sample.stl",
            extension=".stl",
            vertex_count=3,
            triangle_count=1,
            had_vertex_normals=True,
            had_triangle_normals=True,
            computed_vertex_normals=False,
            computed_triangle_normals=False,
        )

        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            with patch(
                "app.main_window.load_mesh",
                return_value=LoadedMesh(mesh=mesh, metadata=metadata),
            ):
                window.load_model(Path("sample.stl"))

            window.select_section_plane()
            active_plane = window.app_state.section_collection.planes[0]
            mesh_location = window.app_state.mesh_object.location.copy()
            mesh_rotation = window.app_state.mesh_object.rotation.copy()
            start_offset = window.section_offset.get()
            start_origin = plane_origin(active_plane)
            start_normal = plane_normal(active_plane)
            window.viewport.camera_right = np.asarray([0.0, 1.0, 0.0], dtype=float)
            window.viewport.camera_up = np.asarray([0.0, 0.0, 1.0], dtype=float)

            window._on_viewport_pointer_event("motion", 0, 0)
            window._handle_shortcut("G")
            self.assertEqual(
                window.status_text.get(),
                "Moving Section Plane 1: camera-relative grab "
                "(X/Y/Z constrain, N normal, Enter/click confirm, Esc cancel)",
            )
            window._on_viewport_pointer_event("motion", 50, 0)
            camera_moved_origin = plane_origin(active_plane)
            self.assertAlmostEqual(camera_moved_origin[0], start_origin[0])
            self.assertGreater(camera_moved_origin[1], start_origin[1])
            self.assertIn("Moving Section Plane 1: Delta X", window.status_text.get())

            handled = window._on_viewport_pointer_event("right_release", 50, 0)
            self.assertTrue(handled)
            self.assertEqual(window.status_text.get(), "Transform cancelled")
            self.assertAlmostEqual(window.section_offset.get(), start_offset)
            self.assertAlmostEqual(active_plane.offset, start_offset)
            self.assertTrue(np.allclose(plane_origin(active_plane), start_origin))
            self.assertTrue(np.allclose(plane_normal(active_plane), start_normal))

            window._handle_shortcut("G")
            window._handle_shortcut("N")
            self.assertEqual(
                window.status_text.get(),
                "Moving Section Plane 1 along normal: drag mouse",
            )
            window._on_viewport_pointer_event("motion", 0, -50)
            moved_offset = window.section_offset.get()
            self.assertGreater(moved_offset, start_offset)
            self.assertEqual(window.section_offset_text.get(), f"{moved_offset:.3f}")
            self.assertAlmostEqual(active_plane.offset, moved_offset)
            self.assertIn("Moving Section Plane 1 along normal:", window.status_text.get())
            window._handle_shortcut("Escape")
            self.assertAlmostEqual(active_plane.offset, start_offset)

            window._handle_shortcut("G")
            window._handle_shortcut("X")
            self.assertEqual(window.status_text.get(), "Moving Section Plane 1 along X: drag mouse")
            window._on_viewport_pointer_event("motion", 100, 0)
            moved_origin = plane_origin(active_plane)
            self.assertGreater(moved_origin[0], start_origin[0])
            self.assertAlmostEqual(active_plane.offset, start_offset)
            handled = window._on_viewport_pointer_event("left_release", 100, 0)
            self.assertTrue(handled)
            self.assertEqual(window.status_text.get(), "Transform confirmed")
            self.assertTrue(np.allclose(plane_origin(active_plane), moved_origin))

            window._on_viewport_pointer_event("motion", 0, 0)
            window._handle_shortcut("R")
            self.assertEqual(
                window.status_text.get(),
                "Rotating Section Plane 1 around view: move mouse horizontally",
            )
            self.assertIsNone(window.viewport.scene_calls[-1]["active_transform_axis"])
            window._on_viewport_pointer_event("motion", 40, 0)
            view_rotated_normal = plane_normal(active_plane)
            self.assertFalse(np.allclose(view_rotated_normal, start_normal))
            self.assertIn("Rotating Section Plane 1 around view: 20.0 deg", window.status_text.get())
            self.assertTrue(np.allclose(window.app_state.mesh_object.location, mesh_location))
            self.assertTrue(np.allclose(window.app_state.mesh_object.rotation, mesh_rotation))
            window._handle_shortcut("Esc")
            self.assertEqual(window.status_text.get(), "Transform cancelled")
            self.assertTrue(np.allclose(plane_normal(active_plane), start_normal))

            window._on_viewport_pointer_event("motion", 0, 0)
            window._handle_shortcut("R")
            window._handle_shortcut("X")
            self.assertEqual(
                window.status_text.get(),
                "Rotating Section Plane 1 around X: move mouse horizontally",
            )
            window._on_viewport_pointer_event("motion", 40, 0)
            rotated_normal = plane_normal(active_plane)
            self.assertFalse(np.allclose(rotated_normal, start_normal))
            self.assertEqual(window.status_text.get(), "Rotating Section Plane 1 around X: 20.0 deg")
            self.assertTrue(np.allclose(window.app_state.mesh_object.location, mesh_location))
            self.assertTrue(np.allclose(window.app_state.mesh_object.rotation, mesh_rotation))

            window._handle_shortcut("Esc")
            self.assertEqual(window.status_text.get(), "Transform cancelled")
            self.assertTrue(np.allclose(plane_normal(active_plane), start_normal))

            window._on_viewport_pointer_event("motion", 0, 0)
            window._handle_shortcut("R")
            window._handle_shortcut("X")
            window._on_viewport_pointer_event("motion", 40, 0)
            confirmed_normal = plane_normal(active_plane)
            handled = window._on_viewport_pointer_event("left_release", 40, 0)
            self.assertTrue(handled)
            self.assertEqual(window.status_text.get(), "Transform confirmed")
            self.assertTrue(np.allclose(plane_normal(active_plane), confirmed_normal))
            self.assertFalse(np.allclose(confirmed_normal, start_normal))
        finally:
            window.root.destroy()

    def test_section_plane_transform_affects_active_plane_only_and_rejects_multi_selection(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            first_plane = window.app_state.section_collection.planes[0]
            window.add_section_plane()
            second_plane = window.app_state.section_collection.planes[1]
            first_origin = plane_origin(first_plane)
            first_normal = plane_normal(first_plane)
            second_origin = plane_origin(second_plane)

            window.select_section_planes(
                [first_plane.id, second_plane.id],
                active_plane_id=second_plane.id,
            )
            window._handle_shortcut("G")

            self.assertIsNone(window.app_state.transform_state)
            self.assertEqual(window.status_text.get(), "Select one section plane to transform.")

            window.select_section_plane(second_plane.id)
            window._on_viewport_pointer_event("motion", 0, 0)
            window._handle_shortcut("G")
            window._handle_shortcut("X")
            window._on_viewport_pointer_event("motion", 100, 0)

            self.assertTrue(np.allclose(plane_origin(first_plane), first_origin))
            self.assertTrue(np.allclose(plane_normal(first_plane), first_normal))
            self.assertGreater(plane_origin(second_plane)[0], second_origin[0])
            self.assertTrue(np.allclose(window.app_state.mesh_object.rotation, [0.0, 0.0, 0.0]))
            window._handle_shortcut("Enter")

            second_normal = plane_normal(second_plane)
            window._handle_shortcut("R")
            window._handle_shortcut("X")
            window._on_viewport_pointer_event("motion", 40, 0)

            self.assertTrue(np.allclose(plane_origin(first_plane), first_origin))
            self.assertTrue(np.allclose(plane_normal(first_plane), first_normal))
            self.assertFalse(np.allclose(plane_normal(second_plane), second_normal))
            self.assertTrue(np.allclose(window.app_state.mesh_object.rotation, [0.0, 0.0, 0.0]))
        finally:
            window.root.destroy()

    def test_axis_offset_controls_reset_rotated_section_plane_to_axis_aligned_mode(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.select_section_plane()
            active_plane = window.app_state.section_collection.planes[0]
            set_plane_origin_normal(
                active_plane,
                np.asarray([0.0, 0.0, 0.25], dtype=float),
                np.asarray([1.0, 0.0, 1.0], dtype=float),
            )
            window._sync_section_controls_from_plane_orientation(active_plane)
            self.assertFalse(
                np.allclose(plane_normal(active_plane), np.asarray([0.0, 0.0, 1.0]))
            )

            window.show_section_plane.set(False)
            window._on_section_plane_visibility_changed()
            self.assertFalse(active_plane.visible)
            self.assertFalse(
                np.allclose(plane_normal(active_plane), np.asarray([0.0, 0.0, 1.0]))
            )

            window._set_section_offset(0.5, clamp=True, refresh=True, mark_dirty=True)

            self.assertTrue(np.allclose(plane_normal(active_plane), np.asarray([0.0, 0.0, 1.0])))
            self.assertTrue(np.allclose(plane_origin(active_plane), np.asarray([0.0, 0.0, 0.5])))
            self.assertAlmostEqual(active_plane.offset, 0.5)
            self.assertEqual(
                window.status_text.get(),
                "Section plane reset to axis-aligned Z mode",
            )
        finally:
            window.root.destroy()

    def test_manual_curve_mode_starts_empty_and_places_points_on_active_section_plane(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            active_plane = window.app_state.section_collection.planes[0]
            window.start_manual_curve_mode()

            self.assertTrue(window._manual_curve_active)
            self.assertEqual(window._manual_curve_points, [])
            self.assertFalse(window._manual_curve_closed)
            self.assertEqual(window._manual_curve_plane_type, "section_plane")
            self.assertEqual(window._manual_curve_source_section_plane_id, active_plane.id)
            self.assertIn("Manual Curve: click to place points", window.status_text.get())
            self.assertIn("Manual Curve: using Section Plane", window.status_text.get())
            self.assertEqual(window.viewport.scene_calls[-1]["manual_curve_points"], [])

            projected_point = np.asarray([0.25, 0.5, 0.75], dtype=float)
            window.viewport.projected_points = [projected_point]
            handled = _manual_curve_click(window, 40, 60)

            self.assertTrue(handled)
            self.assertEqual(len(window._manual_curve_points), 1)
            self.assertTrue(np.allclose(window._manual_curve_points[0], projected_point))
            self.assertIn("1 point", window.status_text.get())
            self.assertTrue(
                np.allclose(
                    window.viewport.projection_calls[-1]["plane_origin"],
                    plane_origin(active_plane),
                )
            )
            self.assertTrue(
                np.allclose(
                    window.viewport.projection_calls[-1]["plane_normal"],
                    plane_normal(active_plane),
                )
            )
            self.assertEqual(len(window.app_state.curve_collection.curves), 0)
        finally:
            window.root.destroy()

    def test_manual_curve_preview_updates_on_motion_without_placing_point(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.start_manual_curve_mode()
            preview_point = np.asarray([0.25, 0.5, 0.75], dtype=float)
            window.viewport.projected_points = [preview_point]

            handled = window._on_viewport_pointer_event("motion", 40, 60)

            self.assertTrue(handled)
            self.assertTrue(window._manual_curve_preview_valid)
            self.assertTrue(np.allclose(window._manual_curve_preview_point, preview_point))
            self.assertFalse(window._manual_curve_preview_snaps_to_mesh)
            self.assertFalse(window._manual_curve_preview_snaps_closed)
            self.assertIsNone(window._manual_curve_preview_triangle_index)
            self.assertIsNone(window._manual_curve_preview_normal)
            self.assertEqual(window._manual_curve_points, [])
            self.assertEqual(len(window.app_state.curve_collection.curves), 0)
            self.assertEqual(
                window.status_text.get(),
                "Manual Curve: previewing next point. Click to place.",
            )
            self.assertTrue(
                np.allclose(
                    window.viewport.scene_calls[-1]["manual_curve_preview_point"],
                    preview_point,
                )
            )
            self.assertTrue(window.viewport.scene_calls[-1]["manual_curve_preview_valid"])

            handled = window._on_viewport_pointer_event("leave", 40, 60)

            self.assertTrue(handled)
            self.assertFalse(window._manual_curve_preview_valid)
            self.assertIsNone(window._manual_curve_preview_point)
        finally:
            window.root.destroy()

    def test_manual_curve_preview_tracks_closure_and_clears_on_mode_exit(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.start_manual_curve_mode()
            window._manual_curve_points = [
                np.asarray([0.0, 0.0, 0.0], dtype=float),
                np.asarray([1.0, 0.0, 0.0], dtype=float),
                np.asarray([1.0, 1.0, 0.0], dtype=float),
            ]
            window.viewport.projected_points = [np.asarray([0.01, 0.0, 0.0], dtype=float)]

            window._on_viewport_pointer_event("motion", 10, 10)

            self.assertTrue(window._manual_curve_preview_valid)
            self.assertTrue(window._manual_curve_preview_snaps_closed)
            self.assertEqual(len(window._manual_curve_points), 3)

            window._set_active_workbench("Scene", set_status=False)

            self.assertFalse(window._manual_curve_preview_valid)
            self.assertIsNone(window._manual_curve_preview_point)

            window.viewport.projected_points = [np.asarray([0.5, 0.0, 0.0], dtype=float)]
            window._on_viewport_pointer_event("motion", 20, 20)
            self.assertFalse(window._manual_curve_preview_valid)

            window._handle_shortcut("Esc")

            self.assertFalse(window._manual_curve_preview_valid)
            self.assertIsNone(window._manual_curve_preview_point)
        finally:
            window.root.destroy()

    def test_manual_curve_snap_preview_tracks_mesh_hit_and_miss_without_status_spam(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.start_manual_curve_mode()
            window.manual_curve_snap_to_mesh.set(True)
            window._on_manual_curve_snap_to_mesh_changed()
            hit_point = np.asarray([0.0, 0.0, 0.3], dtype=float)
            window.viewport.mesh_pick_results = [
                MeshPickResult(
                    hit=True,
                    position=hit_point,
                    normal=np.asarray([0.0, 0.0, 1.0], dtype=float),
                    triangle_index=12,
                )
            ]

            window._on_viewport_pointer_event("motion", 50, 60)

            self.assertTrue(window._manual_curve_preview_valid)
            self.assertTrue(np.allclose(window._manual_curve_preview_point, hit_point))
            self.assertTrue(window._manual_curve_preview_snaps_to_mesh)
            self.assertEqual(window._manual_curve_preview_triangle_index, 12)
            self.assertEqual(window._manual_curve_preview_normal, [0.0, 0.0, 1.0])
            self.assertEqual(window._manual_curve_points, [])
            self.assertEqual(
                window.status_text.get(),
                "Manual Curve: Snap to Mesh On. Click scan surface to place.",
            )

            window._on_viewport_pointer_event("motion", 55, 65)

            self.assertFalse(window._manual_curve_preview_valid)
            self.assertIsNone(window._manual_curve_preview_point)
            self.assertEqual(window.status_text.get(), "Manual Curve: no mesh under cursor.")
        finally:
            window.root.destroy()

    def test_manual_curve_preview_clears_on_new_project_and_delete_mesh(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.start_manual_curve_mode()
            window.viewport.projected_points = [np.asarray([0.25, 0.5, 0.0], dtype=float)]
            window._on_viewport_pointer_event("motion", 10, 10)
            self.assertTrue(window._manual_curve_preview_valid)

            window._set_project_dirty(False)
            window.new_project()

            self.assertFalse(window._manual_curve_preview_valid)
            self.assertIsNone(window._manual_curve_preview_point)

            _load_sample_model(window)
            window.start_manual_curve_mode()
            window.viewport.projected_points = [np.asarray([0.5, 0.25, 0.0], dtype=float)]
            window._on_viewport_pointer_event("motion", 20, 20)
            self.assertTrue(window._manual_curve_preview_valid)

            with patch("app.main_window.messagebox.askyesno", return_value=True):
                window.delete_mesh()

            self.assertFalse(window._manual_curve_preview_valid)
            self.assertIsNone(window._manual_curve_preview_point)
        finally:
            window.root.destroy()

    def test_manual_curve_preview_click_safety_requires_valid_click_release(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.start_manual_curve_mode()

            window.viewport.projected_points = [np.asarray([0.1, 0.2, 0.0], dtype=float)]
            self.assertTrue(window._on_viewport_pointer_event("motion", 10, 10))
            self.assertEqual(window._manual_curve_points, [])

            with patch.object(window, "_show_manual_curve_context_menu") as popup:
                self.assertTrue(window._on_viewport_pointer_event("right_release", 12, 12))
            popup.assert_called_once()
            self.assertEqual(window._manual_curve_points, [])

            self.assertFalse(window._on_viewport_pointer_event("middle_press", 15, 15))
            self.assertFalse(window._on_viewport_pointer_event("middle_release", 15, 15))
            self.assertEqual(window._manual_curve_points, [])

            window.viewport.projected_points = [np.asarray([0.4, 0.5, 0.0], dtype=float)]
            self.assertTrue(window._on_viewport_pointer_event("left_press", 20, 20))
            self.assertTrue(window._on_viewport_pointer_event("motion", 30, 30))
            self.assertTrue(window._on_viewport_pointer_event("left_release", 30, 30))
            self.assertEqual(window._manual_curve_points, [])

            window.viewport.projected_points = [np.asarray([0.7, 0.8, 0.0], dtype=float)]
            self.assertTrue(_manual_curve_click(window, 40, 40))
            self.assertEqual(len(window._manual_curve_points), 1)
            self.assertTrue(np.allclose(window._manual_curve_points[0], [0.7, 0.8, 0.0]))

            window.viewport.projected_points = [None]
            self.assertTrue(_manual_curve_click(window, 45, 45))
            self.assertEqual(len(window._manual_curve_points), 1)
            self.assertEqual(
                window.status_text.get(),
                "Manual Curve: could not place point on work plane",
            )
        finally:
            window.root.destroy()

    def test_manual_curve_backspace_escape_and_closed_toggle_behaviors(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.start_manual_curve_mode()
            window.viewport.projected_points = [
                np.asarray([0.0, 0.0, 0.0], dtype=float),
                np.asarray([1.0, 0.0, 0.0], dtype=float),
                np.asarray([1.0, 1.0, 0.0], dtype=float),
            ]
            _manual_curve_click(window, 10, 10)
            _manual_curve_click(window, 20, 20)

            window._handle_shortcut("C")
            self.assertFalse(window._manual_curve_closed)
            self.assertEqual(window.status_text.get(), "Manual Curve: need at least 3 points to close")

            _manual_curve_click(window, 30, 30)
            window._handle_shortcut("C")
            self.assertTrue(window._manual_curve_closed)
            self.assertTrue(window.viewport.scene_calls[-1]["manual_curve_closed"])

            window._handle_shortcut("Backspace")
            self.assertEqual(len(window._manual_curve_points), 2)
            self.assertFalse(window._manual_curve_closed)

            window._handle_shortcut("Esc")
            self.assertFalse(window._manual_curve_active)
            self.assertEqual(window._manual_curve_points, [])
            self.assertEqual(window.status_text.get(), "Manual curve cancelled")
            self.assertIsNone(window.viewport.scene_calls[-1]["manual_curve_points"])
        finally:
            window.root.destroy()

    def test_manual_curve_click_near_first_point_snaps_closed_without_duplicate_point(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.start_manual_curve_mode()
            window.viewport.projected_points = [
                np.asarray([0.0, 0.0, 0.0], dtype=float),
                np.asarray([1.0, 0.0, 0.0], dtype=float),
                np.asarray([1.0, 1.0, 0.0], dtype=float),
                np.asarray([0.02, 0.0, 0.0], dtype=float),
            ]

            for index in range(4):
                handled = _manual_curve_click(window, 10 + index, 20 + index)
                self.assertTrue(handled)

            self.assertTrue(window._manual_curve_closed)
            self.assertEqual(len(window._manual_curve_points), 3)
            self.assertEqual(window.status_text.get(), "Curve closed to first point")

            window._handle_shortcut("Enter")
            curve = window.app_state.curve_collection.curves[-1]
            self.assertTrue(curve.is_closed)
            self.assertEqual(len(curve.original_points), 3)
            self.assertTrue(np.allclose(curve.fitted_points[0], curve.fitted_points[-1]))
        finally:
            window.root.destroy()

    def test_manual_curve_enter_rejects_too_few_points_and_invalid_projection(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.start_manual_curve_mode()
            window._handle_shortcut("Enter")
            self.assertEqual(window.status_text.get(), "Manual Curve: open curve needs at least 2 points")

            window.viewport.projected_points = [None]
            handled = _manual_curve_click(window, 20, 20)
            self.assertTrue(handled)
            self.assertEqual(window._manual_curve_points, [])
            self.assertEqual(window.status_text.get(), "Manual Curve: could not place point on work plane")

            window._manual_curve_points = [
                np.asarray([0.0, 0.0, 0.0], dtype=float),
                np.asarray([1.0, 0.0, 0.0], dtype=float),
            ]
            window._manual_curve_closed = True
            window._handle_shortcut("Enter")
            self.assertEqual(window.status_text.get(), "Manual Curve: closed curve needs at least 3 points")
            self.assertEqual(len(window.app_state.curve_collection.curves), 0)
        finally:
            window.root.destroy()

    def test_manual_curve_enter_creates_stored_curve_with_metadata_and_undo_redo(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            active_plane = window.app_state.section_collection.planes[0]
            expected_points = np.asarray(
                [
                    (0.0, 0.0, 0.0),
                    (1.0, 0.0, 0.0),
                    (1.0, 1.0, 0.0),
                ],
                dtype=float,
            )
            curve = _create_manual_curve(
                window,
                [tuple(point) for point in expected_points],
                closed=True,
            )

            self.assertEqual(curve.name, "Manual Curve 1")
            self.assertTrue(curve.visible)
            self.assertTrue(curve.selected)
            self.assertTrue(curve.is_closed)
            self.assertEqual(curve.mean_error, 0.0)
            self.assertEqual(curve.max_error, 0.0)
            self.assertTrue(np.allclose(curve.original_points, expected_points))
            self.assertGreater(len(curve.fitted_points), len(curve.original_points))
            self.assertTrue(np.allclose(curve.fitted_points[0], curve.fitted_points[-1]))
            self.assertEqual(curve.metadata["creation_type"], "manual")
            self.assertEqual(curve.metadata["work_plane_type"], "section_plane")
            self.assertEqual(curve.metadata["source_section_plane_id"], active_plane.id)
            self.assertTrue(curve.metadata["closed"])
            self.assertEqual(curve.metadata["control_points"], expected_points.tolist())
            self.assertEqual(curve.metadata["curve_method"], DEFAULT_MANUAL_CURVE_METHOD)
            self.assertEqual(curve.metadata["sample_count"], DEFAULT_MANUAL_CURVE_SAMPLE_COUNT)
            self.assertEqual(window.app_state.curve_collection.active_curve_id, curve.id)
            self.assertIn(curve.id, window.app_state.curve_collection.selected_curve_ids)
            self.assertTrue(window._manual_curve_edit_active)
            self.assertEqual(window.current_mode_text.get(), "Manual Curve Edit")
            self.assertEqual(window.status_text.get(), "Created Manual Curve 1. Editing curve.")
            self.assertIn(
                "(manual, smooth)",
                window.scene_browser.tree.item(curve_node_id(curve.id), "text"),
            )

            window.undo()
            self.assertEqual(len(window.app_state.curve_collection.curves), 0)
            self.assertEqual(window.status_text.get(), "Undid Create Manual Curve")

            window.redo()
            self.assertEqual(len(window.app_state.curve_collection.curves), 1)
            restored_curve = window.app_state.curve_collection.curves[0]
            self.assertEqual(restored_curve.name, "Manual Curve 1")
            self.assertEqual(restored_curve.metadata["creation_type"], "manual")
            self.assertEqual(window.status_text.get(), "Redid Create Manual Curve")

            window.select_curve(restored_curve.id)
            window.delete_selected_curve()
            self.assertEqual(window.app_state.curve_collection.curves, [])
            self.assertEqual(window.status_text.get(), "Deleted: Manual Curve 1")

            window.undo()
            self.assertEqual(len(window.app_state.curve_collection.curves), 1)
            self.assertEqual(window.app_state.curve_collection.curves[0].name, "Manual Curve 1")
            self.assertEqual(window.status_text.get(), "Undid Delete Curve")
        finally:
            window.root.destroy()

    def test_manual_curve_finish_enters_edit_mode_and_done_exits_cleanly(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            curve = _create_manual_curve(
                window,
                [
                    (0.0, 0.0, 0.0),
                    (1.0, 0.0, 0.0),
                    (1.0, 1.0, 0.0),
                ],
            )

            self.assertTrue(window._manual_curve_active)
            self.assertTrue(window._manual_curve_edit_active)
            self.assertEqual(window._manual_curve_edit_curve_id, curve.id)
            self.assertFalse(window._manual_curve_placing_enabled)
            self.assertEqual(window.current_workbench.get(), "Manual RE")
            self.assertEqual(window.current_mode_text.get(), "Manual Curve Edit")
            self.assertEqual(window.finish_manual_curve_button.cget("text"), "Apply Edits")
            self.assertEqual(window.cancel_manual_curve_button.cget("text"), "Cancel Edit")
            self.assertEqual(str(window.done_manual_curve_edit_button.cget("state")), "normal")
            self.assertEqual(str(window.add_manual_point_button.cget("state")), "normal")
            self.assertEqual(str(window.insert_manual_point_button.cget("state")), "normal")
            self.assertEqual(str(window.remove_manual_point_button.cget("state")), "disabled")
            self.assertEqual(
                window.status_text.get(),
                "Created Manual Curve 1. Editing curve.",
            )
            self.assertTrue(
                np.allclose(
                    window.viewport.scene_calls[-1]["manual_curve_points"],
                    curve.original_points,
                )
            )

            window.done_manual_curve_editing()

            self.assertFalse(window._manual_curve_active)
            self.assertFalse(window._manual_curve_edit_active)
            self.assertEqual(window.current_mode_text.get(), "No Mode")
            self.assertEqual(window.app_state.curve_collection.active_curve_id, curve.id)
            self.assertIn(curve.id, window.app_state.curve_collection.selected_curve_ids)
            self.assertEqual(window.status_text.get(), "Manual curve editing finished")
            self.assertIsNone(window.viewport.scene_calls[-1]["manual_curve_points"])
        finally:
            window.root.destroy()

    def test_manual_curve_edit_mode_rejects_non_manual_curve(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            points = np.asarray(
                [
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                ],
                dtype=float,
            )
            section_curve = StoredCurve(
                id="section-curve-1",
                name="Section Curve 1",
                section_result_id="section-result-1",
                plane_id="plane-1",
                original_points=points,
                fitted_points=points.copy(),
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
            )
            add_curve(window.app_state.curve_collection, section_curve)
            window.select_curve(section_curve.id)

            window.start_manual_curve_edit_mode()

            self.assertFalse(window._manual_curve_edit_active)
            self.assertEqual(
                window.status_text.get(),
                "Only manual curves can be edited in this mode.",
            )
        finally:
            window.root.destroy()

    def test_manual_curve_edit_add_insert_apply_cancel_and_context_actions(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            curve = _create_manual_curve(
                window,
                [
                    (0.0, 0.0, 0.0),
                    (1.0, 0.0, 0.0),
                    (1.0, 1.0, 0.0),
                ],
            )
            self.assertEqual(len(curve.metadata["control_points"]), 3)

            window.viewport.projected_points = [np.asarray([1.0, 0.0, 0.0], dtype=float)]
            self.assertTrue(_manual_curve_click(window, 20, 20))
            self.assertEqual(window._manual_curve_selected_control_point_index, 1)
            self.assertEqual(window.status_text.get(), "Selected control point 2")
            self.assertEqual(str(window.delete_manual_point_button.cget("state")), "normal")

            menu = window._build_manual_curve_context_menu()
            labels = [
                menu.entrycget(index, "label")
                for index in range(menu.index("end") + 1)
            ]
            self.assertIn("Apply / Finish Current Curve", labels)
            self.assertIn("Cancel Current Action", labels)
            self.assertIn("Restart Current Curve", labels)
            self.assertIn("Done Editing", labels)
            self.assertIn("Toggle Closed", labels)
            self.assertIn("Delete Selected Point", labels)

            before_count = len(window._manual_curve_points)
            with patch.object(window, "_show_manual_curve_context_menu") as popup:
                handled = window._on_viewport_pointer_event("right_release", 40, 40)
            self.assertTrue(handled)
            popup.assert_called_once()
            self.assertEqual(len(window._manual_curve_points), before_count)

            window.activate_manual_curve_add_point()
            self.assertTrue(window._manual_curve_add_point_active)
            add_preview = np.asarray([1.5, 0.5, 0.0], dtype=float)
            window.viewport.projected_points = [add_preview]
            window._on_viewport_pointer_event("motion", 28, 28)
            self.assertTrue(window._manual_curve_preview_valid)
            self.assertTrue(np.allclose(window._manual_curve_preview_point, add_preview))
            self.assertEqual(len(window._manual_curve_points), 3)
            window.viewport.projected_points = [np.asarray([2.0, 1.0, 0.0], dtype=float)]
            self.assertTrue(_manual_curve_click(window, 30, 30))
            self.assertFalse(window._manual_curve_add_point_active)
            self.assertFalse(window._manual_curve_preview_valid)
            self.assertEqual(len(window._manual_curve_points), 4)
            self.assertEqual(window.status_text.get(), "Point added. Add Point mode off.")
            self.assertEqual(len(curve.metadata["control_points"]), 3)

            window.activate_manual_curve_insert_point()
            insert_preview = np.asarray([0.25, 0.0, 0.0], dtype=float)
            window.viewport.projected_points = [insert_preview]
            window._on_viewport_pointer_event("motion", 34, 34)
            self.assertTrue(window._manual_curve_preview_valid)
            self.assertTrue(np.allclose(window._manual_curve_preview_point, insert_preview))
            self.assertEqual(len(window._manual_curve_points), 4)
            window.viewport.projected_points = [np.asarray([0.5, 0.0, 0.0], dtype=float)]
            self.assertTrue(_manual_curve_click(window, 35, 35))
            self.assertFalse(window._manual_curve_insert_point_active)
            self.assertFalse(window._manual_curve_preview_valid)
            self.assertEqual(len(window._manual_curve_points), 5)
            self.assertEqual(window.status_text.get(), "Point inserted. Insert mode off.")

            window.apply_manual_curve_edits()
            self.assertTrue(window._manual_curve_edit_active)
            self.assertEqual(window.status_text.get(), "Curve edits saved")
            self.assertEqual(len(curve.metadata["control_points"]), 5)
            self.assertGreater(len(curve.fitted_points), len(curve.original_points))

            window.undo()
            restored_curve = window.app_state.curve_collection.curves[0]
            self.assertEqual(window.status_text.get(), "Undid Edit Manual Curve")
            self.assertEqual(len(restored_curve.metadata["control_points"]), 3)
            self.assertEqual(len(window._manual_curve_points), 3)

            window.redo()
            curve = window.app_state.curve_collection.curves[0]
            self.assertEqual(window.status_text.get(), "Redid Edit Manual Curve")
            self.assertEqual(len(curve.metadata["control_points"]), 5)
            self.assertEqual(len(window._manual_curve_points), 5)

            window.activate_manual_curve_add_point()
            window.viewport.projected_points = [np.asarray([3.0, 1.0, 0.0], dtype=float)]
            self.assertTrue(_manual_curve_click(window, 45, 45))
            self.assertEqual(len(window._manual_curve_points), 6)

            window.cancel_manual_curve_edit()

            self.assertTrue(window._manual_curve_edit_active)
            self.assertEqual(window.status_text.get(), "Curve edit cancelled")
            self.assertEqual(len(window._manual_curve_points), 5)
            self.assertEqual(len(curve.metadata["control_points"]), 5)
        finally:
            window.root.destroy()

    def test_manual_curve_edit_drag_delete_floor_and_curve_type(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            curve = _create_manual_curve(
                window,
                [
                    (0.0, 0.0, 0.0),
                    (1.0, 0.0, 0.0),
                    (1.0, 1.0, 0.0),
                ],
            )

            window.viewport.projected_points = [np.asarray([1.0, 0.0, 0.0], dtype=float)]
            self.assertTrue(_manual_curve_click(window, 20, 20))
            self.assertEqual(window._manual_curve_selected_control_point_index, 1)

            moved_point = np.asarray([1.5, 0.25, 0.0], dtype=float)
            window.viewport.projected_points = [moved_point]
            self.assertTrue(window._on_viewport_pointer_event("left_press", 20, 20))
            self.assertTrue(window._on_viewport_pointer_event("motion", 30, 31))
            self.assertTrue(window._manual_curve_drag_active)
            self.assertTrue(np.allclose(window._manual_curve_points[1], moved_point))
            self.assertEqual(window.status_text.get(), "Moving control point 2")
            self.assertTrue(window._on_viewport_pointer_event("left_release", 30, 31))
            self.assertFalse(window._manual_curve_drag_active)
            self.assertEqual(window.status_text.get(), "Moved control point 2")

            window.manual_curve_type_text.set("Polyline")
            window._on_manual_curve_type_changed()
            self.assertEqual(window._manual_curve_curve_method, "polyline")
            self.assertEqual(window.status_text.get(), "Curve type: Polyline")
            self.assertEqual(window.viewport.scene_calls[-1]["manual_curve_method"], "polyline")

            window.apply_manual_curve_edits()
            curve = window.app_state.curve_collection.curves[0]
            self.assertEqual(curve.metadata["curve_method"], "polyline")
            self.assertEqual(len(curve.fitted_points), len(curve.original_points))
            self.assertTrue(np.allclose(curve.metadata["control_points"][1], moved_point))

            window.delete_selected_manual_curve_point()
            self.assertEqual(len(window._manual_curve_points), 2)
            self.assertEqual(window.status_text.get(), "Deleted control point 2")
            window.delete_selected_manual_curve_point()
            self.assertEqual(len(window._manual_curve_points), 2)
            self.assertEqual(
                window.status_text.get(),
                "Cannot delete point: curve needs more control points",
            )
        finally:
            window.root.destroy()

    def test_manual_curve_project_restore_upgrades_legacy_manual_curve(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            points = [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
            ]
            project = default_project_data()
            project.curves = [
                ProjectCurve(
                    id="curve-legacy",
                    name="Manual Curve 1",
                    section_result_id="",
                    plane_id="",
                    original_points=points,
                    fitted_points=[],
                    mean_error=0.0,
                    max_error=0.0,
                    is_closed=False,
                    visible=True,
                    metadata={"creation_type": "manual", "closed": False},
                )
            ]

            window._restore_project_curve_collection(project)

            curve = window.app_state.curve_collection.curves[0]
            self.assertEqual(curve.metadata["control_points"], points)
            self.assertEqual(curve.metadata["curve_method"], "polyline")
            self.assertFalse(curve.metadata["snap_to_mesh"])
            self.assertTrue(np.allclose(curve.original_points, points))
            self.assertTrue(np.allclose(curve.fitted_points, points))
            self.assertIn(
                "(manual, polyline)",
                window.scene_browser.tree.item(curve_node_id(curve.id), "text"),
            )
        finally:
            window.root.destroy()

    def test_manual_curve_uses_world_xy_when_no_active_section_plane_exists(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.app_state.section_collection.planes = []
            window.app_state.section_collection.active_plane_id = None
            curve = _create_manual_curve(
                window,
                [
                    (0.0, 0.0, 0.0),
                    (1.0, 0.0, 0.0),
                ],
            )

            self.assertEqual(curve.metadata["work_plane_type"], "world_xy")
            self.assertNotIn("source_section_plane_id", curve.metadata)
            self.assertTrue(
                np.allclose(
                    window.viewport.projection_calls[-1]["plane_origin"],
                    np.asarray([0.0, 0.0, 0.0], dtype=float),
                )
            )
            self.assertTrue(
                np.allclose(
                    window.viewport.projection_calls[-1]["plane_normal"],
                    np.asarray([0.0, 0.0, 1.0], dtype=float),
                )
            )
        finally:
            window.root.destroy()

    def test_manual_curve_snap_to_mesh_no_hit_does_not_add_point(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.start_manual_curve_mode()
            window.manual_curve_snap_to_mesh.set(True)
            window._on_manual_curve_snap_to_mesh_changed()

            handled = _manual_curve_click(window, 50, 60)

            self.assertTrue(handled)
            self.assertEqual(window._manual_curve_points, [])
            self.assertEqual(window.status_text.get(), "Manual Curve: no mesh under cursor.")
            self.assertEqual(window.current_mode_text.get(), "Manual Curve")
            self.assertEqual(
                window.command_prompt_text.get(),
                "Manual Curve: Snap to Mesh On. Click scan surface to place.",
            )
            self.assertEqual(window.viewport.mesh_pick_calls[-1], {"x": 50, "y": 60})
            self.assertEqual(len(window.viewport.projection_calls), 0)
        finally:
            window.root.destroy()

    def test_manual_curve_snap_to_mesh_creates_curve_on_mesh_metadata(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            curve = _create_manual_curve(
                window,
                [
                    (0.0, 0.0, 0.3),
                    (1.0, 0.0, 0.4),
                ],
                snap_to_mesh=True,
                triangle_indices=[4, 9],
            )

            self.assertEqual(curve.metadata["creation_type"], "curve_on_mesh")
            self.assertEqual(curve.metadata["snap_mode"], "mesh")
            self.assertEqual(curve.metadata["source_mesh_name"], "sample.stl")
            self.assertEqual(curve.metadata["snap_triangle_indices"], [4, 9])
            self.assertEqual(
                curve.metadata["snap_normals"],
                [[0.0, 0.0, 1.0], [0.0, 0.0, 1.0]],
            )
            self.assertFalse(curve.metadata["closed"])
            self.assertEqual(
                curve.metadata["control_points"],
                [[0.0, 0.0, 0.3], [1.0, 0.0, 0.4]],
            )
            self.assertEqual(curve.metadata["curve_method"], DEFAULT_MANUAL_CURVE_METHOD)
            self.assertEqual(curve.metadata["sample_count"], DEFAULT_MANUAL_CURVE_SAMPLE_COUNT)
            self.assertTrue(window._manual_curve_edit_active)
            self.assertEqual(window.status_text.get(), "Created Manual Curve 1. Editing curve.")
            self.assertIn(
                "(mesh, smooth)",
                window.scene_browser.tree.item(curve_node_id(curve.id), "text"),
            )
            self.assertTrue(
                np.allclose(
                    curve.original_points,
                    np.asarray([[0.0, 0.0, 0.3], [1.0, 0.0, 0.4]], dtype=float),
                )
            )
            self.assertGreater(len(curve.fitted_points), len(curve.original_points))
            self.assertTrue(np.allclose(curve.fitted_points[0], [0.0, 0.0, 0.3]))
            self.assertTrue(np.allclose(curve.fitted_points[-1], [1.0, 0.0, 0.4]))
            self.assertEqual(len(window.viewport.projection_calls), 0)
        finally:
            window.root.destroy()

    def test_delete_mesh_clears_pending_snapped_manual_curve_mode(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.start_manual_curve_mode()
            window.manual_curve_snap_to_mesh.set(True)
            window._on_manual_curve_snap_to_mesh_changed()
            window.viewport.mesh_pick_results = [
                MeshPickResult(
                    hit=True,
                    position=np.asarray([0.25, 0.5, 0.75], dtype=float),
                    normal=np.asarray([0.0, 0.0, 1.0], dtype=float),
                    triangle_index=2,
                )
            ]
            _manual_curve_click(window, 10, 10)

            self.assertTrue(window._manual_curve_active)
            self.assertEqual(len(window._manual_curve_points), 1)
            self.assertTrue(window.manual_curve_snap_to_mesh.get())

            with patch("app.main_window.messagebox.askyesno", return_value=True):
                window.delete_mesh()

            self.assertFalse(window._manual_curve_active)
            self.assertEqual(window._manual_curve_points, [])
            self.assertEqual(window._manual_curve_snap_point_count, 0)
            self.assertFalse(window.manual_curve_snap_to_mesh.get())
            self.assertEqual(window.status_text.get(), "Mesh deleted")
        finally:
            window.root.destroy()

    def test_region_select_mode_click_creates_visible_region(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            mesh = _sharp_region_mesh()
            window.app_state.mesh_object.display_mesh = mesh
            window.viewport.mesh_pick_results.append(
                MeshPickResult(
                    hit=True,
                    position=np.asarray([0.1, 0.1, 0.0], dtype=float),
                    normal=np.asarray([0.0, 0.0, 1.0], dtype=float),
                    triangle_index=0,
                )
            )

            window.start_region_select_mode()
            self.assertTrue(window._region_select_active)
            self.assertEqual(window.current_mode_text.get(), "Region Select")
            self.assertEqual(
                window.command_prompt_text.get(),
                "Region Select: click a mesh area to grow a connected region.",
            )
            self.assertEqual(
                window.hotkey_hint_text.get(),
                "Esc cancel, click mesh to select region.",
            )
            self.assertEqual(str(window.region_select_button.cget("state")), "normal")
            handled = _region_click(window, 20, 30)

            region = window.app_state.region_collection.active_region
            self.assertTrue(handled)
            self.assertIsNotNone(region)
            self.assertEqual(region.triangle_indices, (0,))
            self.assertEqual(region.source_mesh_name, "sample.stl")
            self.assertIs(window.viewport.scene_calls[-1]["region_selection"], region)
            self.assertEqual(window.region_triangle_count_text.get(), "1")
            self.assertEqual(window.region_seed_triangle_text.get(), "0")
            self.assertEqual(window.app_state.selected_item, "region")
            self.assertEqual(window.current_workbench.get(), "Manual RE")
            self.assertEqual(window.manual_curve_mode_title.get(), "REGION SELECT MODE")
            self.assertIn(
                "Click a mesh area to grow a connected region by normal angle.",
                window.manual_curve_mode_details.get(),
            )
            region_node = region_node_id(region.id)
            self.assertTrue(window.scene_browser.tree.exists(NODE_REGIONS))
            self.assertEqual(window.scene_browser.tree.selection(), (region_node,))
            self.assertEqual(
                window.scene_browser.tree.item(region_node, "text"),
                "[V] Region 1 (1 tris)",
            )
            self.assertEqual(window.status_text.get(), "Selected region: 1 triangle at 20.0\u00b0.")

            window._handle_shortcut("Esc")
            self.assertFalse(window._region_select_active)
            self.assertEqual(window.current_mode_text.get(), "No Mode")
            self.assertIs(window.app_state.region_collection.active_region, region)
            self.assertIs(window.viewport.scene_calls[-1]["region_selection"], region)
            self.assertEqual(window.status_text.get(), "Region Select cancelled")
        finally:
            window.root.destroy()

    def test_region_threshold_affects_click_selection_size(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.app_state.mesh_object.display_mesh = _sharp_region_mesh()
            window.region_threshold_text.set("90")
            window._on_region_threshold_entry_changed()
            window.viewport.mesh_pick_results.append(
                MeshPickResult(hit=True, triangle_index=0)
            )
            window.start_region_select_mode()
            _region_click(window, 20, 30)
            wide_region = window.app_state.region_collection.active_region

            window.region_threshold_text.set("20")
            window._on_region_threshold_entry_changed()
            window.viewport.mesh_pick_results.append(
                MeshPickResult(hit=True, triangle_index=0)
            )
            _region_click(window, 20, 30)
            narrow_region = window.app_state.region_collection.active_region

            self.assertIsNotNone(wide_region)
            self.assertIsNotNone(narrow_region)
            self.assertGreater(
                len(wide_region.triangle_indices),
                len(narrow_region.triangle_indices),
            )
            self.assertEqual(set(wide_region.triangle_indices), {0, 1})
            self.assertEqual(narrow_region.triangle_indices, (0,))
        finally:
            window.root.destroy()

    def test_clear_and_hide_show_region_selection_updates_viewport(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.app_state.mesh_object.display_mesh = _sharp_region_mesh()
            window.viewport.mesh_pick_results.append(
                MeshPickResult(hit=True, triangle_index=0)
            )
            window.start_region_select_mode()
            _region_click(window, 20, 30)
            region = window.app_state.region_collection.active_region
            self.assertIsNotNone(region)

            window.hide_region_selection()
            self.assertFalse(region.visible)
            self.assertIsNone(window.viewport.scene_calls[-1]["region_selection"])

            window.show_region_selection()
            self.assertTrue(region.visible)
            self.assertIs(window.viewport.scene_calls[-1]["region_selection"], region)

            window.clear_region_selection()
            self.assertIsNone(window.app_state.region_collection.active_region)
            self.assertIsNone(window.viewport.scene_calls[-1]["region_selection"])
            self.assertTrue(window._region_select_active)
        finally:
            window.root.destroy()

    def test_region_select_ignores_drag_and_miss_keeps_active_region(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.app_state.mesh_object.display_mesh = _sharp_region_mesh()
            window.viewport.mesh_pick_results.append(
                MeshPickResult(hit=True, triangle_index=0)
            )
            window.start_region_select_mode()
            _region_click(window, 20, 30)
            region = window.app_state.region_collection.active_region
            self.assertIsNotNone(region)

            window.viewport.mesh_pick_results.append(MeshPickResult(hit=False))
            window._on_viewport_pointer_event("left_press", 20, 30)
            window._on_viewport_pointer_event("motion", 40, 30)
            window._on_viewport_pointer_event("left_release", 40, 30)
            self.assertIs(window.app_state.region_collection.active_region, region)
            self.assertEqual(len(window.viewport.mesh_pick_results), 1)

            with patch.object(window, "_show_region_select_context_menu") as popup:
                self.assertTrue(window._on_viewport_pointer_event("right_release", 30, 40))
            popup.assert_called_once()
            self.assertIs(window.app_state.region_collection.active_region, region)
            self.assertEqual(len(window.viewport.mesh_pick_results), 1)

            _region_click(window, 50, 60)
            self.assertIs(window.app_state.region_collection.active_region, region)
            self.assertEqual(window.status_text.get(), "No mesh under cursor.")
        finally:
            window.root.destroy()

    def test_recompute_region_uses_controls_and_rejects_invalid_cap(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.app_state.mesh_object.display_mesh = _sharp_region_mesh()
            window.viewport.mesh_pick_results.append(
                MeshPickResult(hit=True, triangle_index=0)
            )
            window.start_region_select_mode()
            _region_click(window, 20, 30)
            initial_region = window.app_state.region_collection.active_region
            self.assertIsNotNone(initial_region)
            initial_id = initial_region.id

            window.region_threshold_text.set("90")
            window._on_region_threshold_entry_changed()
            window.recompute_region_selection()
            recomputed = window.app_state.region_collection.active_region
            self.assertIsNotNone(recomputed)
            self.assertEqual(recomputed.id, initial_id)
            self.assertEqual(set(recomputed.triangle_indices), {0, 1})
            self.assertEqual(
                window.status_text.get(),
                "Recomputed region: 2 triangles at 90.0\u00b0.",
            )

            window.region_max_triangle_count.set("0")
            window.recompute_region_selection()
            self.assertIs(window.app_state.region_collection.active_region, recomputed)
            self.assertEqual(
                window.status_text.get(),
                "Max triangles must be a whole number >= 1.",
            )
        finally:
            window.root.destroy()

    def test_region_scene_browser_visibility_rename_frame_and_delete(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.app_state.mesh_object.display_mesh = _sharp_region_mesh()
            window.viewport.mesh_pick_results.append(
                MeshPickResult(hit=True, triangle_index=0)
            )
            window.start_region_select_mode()
            _region_click(window, 20, 30)
            region = window.app_state.region_collection.active_region
            self.assertIsNotNone(region)
            region_node = region_node_id(region.id)
            tree = window.scene_browser.tree

            self.assertTrue(tree.exists(NODE_REGIONS))
            self.assertEqual(tree.item(NODE_REGIONS, "text"), "[V] Regions")
            self.assertEqual(tree.get_children(NODE_REGIONS), (region_node,))
            self.assertEqual(tree.item(region_node, "text"), "[V] Region 1 (1 tris)")

            tree.selection_set(NODE_REGIONS)
            tree.focus(NODE_REGIONS)
            with (
                patch.object(window.scene_browser._context_menu, "tk_popup"),
                patch.object(window.scene_browser._context_menu, "grab_release"),
            ):
                self.assertEqual(
                    window.scene_browser._on_tree_context_menu(
                        SimpleNamespace(y=-1, x_root=0, y_root=0)
                    ),
                    "break",
                )
            menu = window.scene_browser._context_menu
            self.assertEqual(
                menu.entrycget(window.scene_browser._select_menu_index, "label"),
                "Select",
            )
            self.assertEqual(
                menu.entrycget(window.scene_browser._hide_selected_menu_index, "label"),
                "Hide Children",
            )
            self.assertEqual(
                menu.entrycget(window.scene_browser._show_selected_menu_index, "label"),
                "Show Children",
            )
            self.assertEqual(
                menu.entrycget(window.scene_browser._delete_selected_menu_index, "label"),
                "Delete Children",
            )
            self.assertEqual(
                menu.entrycget(
                    window.scene_browser._extract_region_boundary_menu_index,
                    "state",
                ),
                "normal",
            )

            window._on_scene_browser_visibility("hide_selected", (region_node,))
            self.assertFalse(region.visible)
            self.assertIsNone(window.viewport.scene_calls[-1]["region_selection"])
            self.assertEqual(tree.item(region_node, "text"), "[H] Region 1 (1 tris)")
            self.assertEqual(tree.item(NODE_REGIONS, "text"), "[H] Regions")

            window._on_scene_browser_visibility("show_selected", (region_node,))
            self.assertTrue(region.visible)
            self.assertIs(window.viewport.scene_calls[-1]["region_selection"], region)
            self.assertEqual(tree.item(region_node, "text"), "[V] Region 1 (1 tris)")

            tree.selection_set(region_node)
            tree.focus(region_node)
            window._on_scene_browser_visibility("select", (region_node,))
            self.assertEqual(window.app_state.selected_item, "region")
            self.assertEqual(window.status_text.get(), "Selected: Region 1")

            window.region_name_text.set("Forehead Patch")
            window._on_region_name_changed()
            self.assertEqual(region.name, "Forehead Patch")
            self.assertEqual(tree.item(region_node, "text"), "[V] Forehead Patch (1 tris)")

            window._on_scene_browser_visibility("frame_selected", (region_node,))
            self.assertEqual(len(window.viewport.framed_bounds), 1)
            self.assertEqual(window.status_text.get(), "Framed: Forehead Patch")

            window._on_scene_browser_visibility("delete_selected", (region_node,))
            self.assertIsNone(window.app_state.region_collection.active_region)
            self.assertFalse(tree.exists(NODE_REGIONS))
            self.assertIsNone(window.viewport.scene_calls[-1]["region_selection"])
            self.assertEqual(window.status_text.get(), "Region deleted.")
        finally:
            window.root.destroy()

    def test_extract_region_boundary_requires_mesh_and_active_region(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            self.assertEqual(
                str(window.extract_region_boundary_button.cget("state")),
                "disabled",
            )
            window.extract_region_boundary()
            self.assertEqual(
                window.status_text.get(),
                "Region boundary extraction requires a loaded mesh.",
            )

            _load_sample_model(window)
            self.assertEqual(
                str(window.extract_region_boundary_button.cget("state")),
                "disabled",
            )
            self.assertEqual(
                str(window.select_region_boundary_curves_button.cget("state")),
                "disabled",
            )
            window.extract_region_boundary()
            self.assertEqual(window.status_text.get(), "No active region to extract.")
        finally:
            window.root.destroy()

    def test_extract_region_boundary_creates_editable_curve_grouped_in_browser(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.app_state.mesh_object.display_mesh = _sharp_region_mesh()
            window.region_threshold_text.set("90")
            window._on_region_threshold_entry_changed()
            window.viewport.mesh_pick_results.append(
                MeshPickResult(hit=True, triangle_index=0)
            )
            window.start_region_select_mode()
            _region_click(window, 20, 30)

            window.extract_region_boundary()

            curves = window.app_state.curve_collection.curves
            self.assertEqual(len(curves), 1)
            curve = curves[0]
            region = window.app_state.region_collection.active_region
            self.assertIsNotNone(region)
            original_region_triangles = tuple(region.triangle_indices)
            self.assertEqual(curve.name, "Region Boundary 1")
            self.assertTrue(curve.is_closed)
            self.assertEqual(curve.original_points.shape, (4, 3))
            self.assertEqual(curve.fitted_points.shape, (4, 3))
            self.assertEqual(curve.metadata["creation_type"], "region_boundary")
            self.assertEqual(curve.metadata["source_region_id"], region.id)
            self.assertEqual(curve.metadata["source_region_name"], "Region 1")
            self.assertEqual(curve.metadata["source_mesh_name"], "sample.stl")
            self.assertEqual(curve.metadata["curve_method"], "polyline")
            self.assertEqual(curve.metadata["region_triangle_count"], 2)
            self.assertEqual(curve.metadata["source_region_triangle_count"], 2)
            self.assertEqual(curve.metadata["boundary_point_count"], 4)
            self.assertIs(curve.metadata["boundary_closed"], True)
            self.assertGreater(curve.metadata["boundary_perimeter"], 0.0)
            self.assertTrue(window._is_editable_manual_curve(curve))
            self.assertTrue(window._curve_is_closed_for_fill(curve))
            self.assertEqual(window.app_state.selected_item, "curve")
            self.assertEqual(window.app_state.curve_collection.active_curve_id, curve.id)
            self.assertEqual(
                window.app_state.curve_collection.selected_curve_ids,
                {curve.id},
            )
            self.assertEqual(
                window.status_text.get(),
                "Extracted 1 closed boundary curve.",
            )
            self.assertEqual(window.region_boundary_curve_count_text.get(), "1")
            self.assertEqual(
                str(window.extract_region_boundary_button.cget("state")),
                "normal",
            )
            self.assertEqual(
                str(window.select_region_boundary_curves_button.cget("state")),
                "normal",
            )

            tree = window.scene_browser.tree
            self.assertTrue(tree.exists(NODE_CURVE_GROUP_REGION_BOUNDARIES))
            self.assertEqual(
                tree.item(NODE_CURVE_GROUP_REGION_BOUNDARIES, "text"),
                "[V] Region Boundaries",
            )
            curve_node = curve_node_id(curve.id)
            self.assertEqual(
                tree.item(curve_node, "text"),
                "[V] Region Boundary 1 (boundary, closed)",
            )

            tree.selection_set(NODE_CURVE_GROUP_REGION_BOUNDARIES)
            tree.focus(NODE_CURVE_GROUP_REGION_BOUNDARIES)
            tree.event_generate("<<TreeviewSelect>>")
            window.root.update()
            self.assertEqual(window.app_state.selected_item, "curve")
            self.assertEqual(
                window.app_state.curve_collection.selected_curve_ids,
                {curve.id},
            )
            self.assertEqual(
                window._expanded_visibility_node_ids(
                    (NODE_CURVE_GROUP_REGION_BOUNDARIES,)
                ),
                {NODE_CURVE_GROUP_REGION_BOUNDARIES, curve_node},
            )

            window.select_boundary_curves_for_active_region()
            self.assertEqual(window.status_text.get(), "Selected 1 boundary curve.")
            self.assertEqual(
                window.app_state.curve_collection.selected_curve_ids,
                {curve.id},
            )

            window.undo()
            self.assertEqual(window.app_state.curve_collection.curves, [])
            self.assertFalse(tree.exists(NODE_CURVE_GROUP_REGION_BOUNDARIES))
            self.assertEqual(window.region_boundary_curve_count_text.get(), "0")
            self.assertEqual(
                str(window.select_region_boundary_curves_button.cget("state")),
                "disabled",
            )

            window.redo()
            curves = window.app_state.curve_collection.curves
            self.assertEqual(len(curves), 1)
            curve = curves[0]
            self.assertTrue(tree.exists(NODE_CURVE_GROUP_REGION_BOUNDARIES))
            self.assertEqual(window.app_state.curve_collection.active_curve_id, curve.id)
            self.assertEqual(
                window.app_state.curve_collection.selected_curve_ids,
                {curve.id},
            )
            self.assertEqual(window.region_boundary_curve_count_text.get(), "1")

            window.start_manual_curve_edit_mode()
            self.assertTrue(window._manual_curve_edit_active)
            self.assertEqual(window.status_text.get(), "Editing Region Boundary 1")
            window.manual_curve_type_text.set("Smooth Curve")
            window._on_manual_curve_type_changed()
            window.apply_manual_curve_edits()

            curve = window.app_state.curve_collection.curves[0]
            region = window.app_state.region_collection.active_region
            self.assertIsNotNone(region)
            self.assertEqual(tuple(region.triangle_indices), original_region_triangles)
            self.assertEqual(curve.metadata["creation_type"], "region_boundary")
            self.assertEqual(curve.metadata["source_region_id"], region.id)
            self.assertEqual(curve.metadata["source_region_name"], "Region 1")
            self.assertEqual(curve.metadata["source_mesh_name"], "sample.stl")
            self.assertEqual(curve.metadata["source_region_triangle_count"], 2)
            self.assertEqual(curve.metadata["boundary_point_count"], len(curve.fitted_points))
            self.assertIs(curve.metadata["boundary_closed"], True)
            self.assertGreater(curve.metadata["boundary_perimeter"], 0.0)
            self.assertEqual(curve.metadata["curve_method"], DEFAULT_MANUAL_CURVE_METHOD)
            self.assertGreater(len(curve.fitted_points), len(curve.original_points))

            window.done_manual_curve_editing()
            self.assertEqual(window.app_state.curve_collection.active_curve_id, curve.id)
            self.assertEqual(
                window.app_state.curve_collection.selected_curve_ids,
                {curve.id},
            )

            window.fill_closed_curve()
            surfaces = window.app_state.surface_collection.surfaces
            self.assertEqual(len(surfaces), 1)
            self.assertEqual(surfaces[0].surface_type, "preview_fill")
            self.assertEqual(surfaces[0].source_curve_ids, [curve.id])
        finally:
            window.root.destroy()

    def test_region_select_exits_manual_curve_mode_and_lifecycle_clears_region(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            window.app_state.mesh_object.display_mesh = _sharp_region_mesh()
            window.start_manual_curve_mode()
            self.assertTrue(window._manual_curve_active)

            window.start_region_select_mode()
            self.assertFalse(window._manual_curve_active)
            self.assertTrue(window._region_select_active)

            window.viewport.mesh_pick_results.append(
                MeshPickResult(hit=True, triangle_index=0)
            )
            _region_click(window, 20, 30)
            self.assertIsNotNone(window.app_state.region_collection.active_region)
            self.assertTrue(window.scene_browser.tree.exists(NODE_REGIONS))

            with patch("app.main_window.messagebox.askyesnocancel", return_value=False):
                window.new_project()

            self.assertIsNone(window.app_state.region_collection.active_region)
            self.assertFalse(window._region_select_active)
            self.assertFalse(window.scene_browser.tree.exists(NODE_REGIONS))

            _load_sample_model(window)
            window.app_state.mesh_object.display_mesh = _sharp_region_mesh()
            window.start_region_select_mode()
            window.viewport.mesh_pick_results.append(
                MeshPickResult(hit=True, triangle_index=0)
            )
            _region_click(window, 20, 30)
            self.assertIsNotNone(window.app_state.region_collection.active_region)

            with patch("app.main_window.messagebox.askyesno", return_value=True):
                window.delete_mesh()

            self.assertIsNone(window.app_state.region_collection.active_region)
            self.assertFalse(window._region_select_active)
            self.assertFalse(window.scene_browser.tree.exists(NODE_REGIONS))
        finally:
            window.root.destroy()

    def test_project_and_rebuild_selected_curve_create_grouped_undoable_curves(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            window.project_selected_curve_to_mesh()
            self.assertEqual(window.status_text.get(), "Load a mesh before projecting curves.")

            _load_sample_model(window)
            window.project_selected_curve_to_mesh()
            self.assertEqual(window.status_text.get(), "Select one curve to project.")
            window.rebuild_selected_curve()
            self.assertEqual(window.status_text.get(), "Select one curve to rebuild.")

            source_curve = _create_manual_curve(
                window,
                [
                    (0.0, 0.0, 0.5),
                    (0.5, 0.5, 0.75),
                    (1.0, 0.0, 0.5),
                ],
            )
            window.done_manual_curve_editing()
            source_points = source_curve.fitted_points.copy()
            source_metadata = dict(source_curve.metadata)
            source_control_count = len(source_metadata["control_points"])

            window.select_curve(source_curve.id)
            window.project_selected_curve_to_mesh()

            curves = window.app_state.curve_collection.curves
            self.assertEqual(len(curves), 2)
            projected_curve = curves[-1]
            self.assertEqual(projected_curve.metadata["creation_type"], "projected_curve")
            self.assertEqual(projected_curve.metadata["source_curve_id"], source_curve.id)
            self.assertEqual(projected_curve.metadata["source_mesh_name"], "sample.stl")
            self.assertEqual(projected_curve.metadata["projection_projected_count"], source_control_count)
            self.assertTrue(np.allclose(source_curve.fitted_points, source_points))
            self.assertEqual(source_curve.metadata, source_metadata)
            self.assertEqual(window.app_state.curve_collection.active_curve_id, projected_curve.id)
            self.assertEqual(
                window.app_state.curve_collection.selected_curve_ids,
                {projected_curve.id},
            )
            self.assertTrue(window.scene_browser.tree.exists(NODE_CURVE_GROUP_PROJECTED))
            self.assertEqual(
                window.scene_browser.tree.item(curve_node_id(projected_curve.id), "text"),
                "[V] Projected Curve 1 (projected, mesh)",
            )

            window.undo()
            self.assertEqual(
                [curve.id for curve in window.app_state.curve_collection.curves],
                [source_curve.id],
            )
            self.assertFalse(window.scene_browser.tree.exists(NODE_CURVE_GROUP_PROJECTED))
            window.redo()
            projected_curve = window.app_state.curve_collection.curves[-1]
            self.assertEqual(projected_curve.metadata["creation_type"], "projected_curve")
            self.assertEqual(window.app_state.curve_collection.active_curve_id, projected_curve.id)

            window.rebuild_target_control_points.set("2")
            window.rebuild_curve_type_text.set("Smooth Curve")
            window.rebuild_sample_count.set("24")
            window.select_curve(projected_curve.id)
            window.rebuild_selected_curve()

            rebuilt_curve = window.app_state.curve_collection.curves[-1]
            self.assertEqual(rebuilt_curve.metadata["creation_type"], "rebuilt_curve")
            self.assertEqual(rebuilt_curve.metadata["source_curve_id"], projected_curve.id)
            self.assertEqual(rebuilt_curve.metadata["source_mesh_name"], "sample.stl")
            self.assertEqual(rebuilt_curve.metadata["projection_projected_count"], source_control_count)
            self.assertEqual(rebuilt_curve.metadata["rebuild_target_control_point_count"], 2)
            self.assertEqual(window.app_state.curve_collection.active_curve_id, rebuilt_curve.id)
            self.assertTrue(window.scene_browser.tree.exists(NODE_CURVE_GROUP_REBUILT))
            self.assertEqual(
                window.scene_browser.tree.item(curve_node_id(rebuilt_curve.id), "text"),
                "[V] Rebuilt Curve 1 (rebuilt, smooth)",
            )

            window.undo()
            self.assertNotIn(
                rebuilt_curve.id,
                [curve.id for curve in window.app_state.curve_collection.curves],
            )
            window.redo()
            self.assertIn(
                rebuilt_curve.id,
                [curve.id for curve in window.app_state.curve_collection.curves],
            )
        finally:
            window.root.destroy()

    def test_fill_and_loft_store_validation_warnings_in_surface_metadata(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            angles = np.linspace(0.0, np.pi * 2.0, 300, endpoint=False)
            dense_points = np.column_stack(
                (np.cos(angles), np.sin(angles), np.zeros(len(angles)))
            )
            dense_curve = StoredCurve(
                id="curve-dense",
                name="Dense Closed Curve",
                section_result_id="",
                plane_id="",
                original_points=dense_points.copy(),
                fitted_points=dense_points.copy(),
                mean_error=0.0,
                max_error=0.0,
                is_closed=True,
            )
            open_curve = StoredCurve(
                id="curve-open",
                name="Open Curve",
                section_result_id="",
                plane_id="",
                original_points=np.asarray(
                    [[0.0, 0.0, 0.25], [1.0, 0.0, 0.25]],
                    dtype=float,
                ),
                fitted_points=np.asarray(
                    [[0.0, 0.0, 0.25], [1.0, 0.0, 0.25]],
                    dtype=float,
                ),
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
            )
            add_curve(window.app_state.curve_collection, dense_curve)
            add_curve(window.app_state.curve_collection, open_curve)

            window.select_curve(dense_curve.id)
            window.fill_closed_curve()

            fill_surface = window.app_state.surface_collection.surfaces[-1]
            self.assertIn(
                "Curve has many points; rebuild it for cleaner surface inputs.",
                fill_surface.metadata["source_curve_validation_warnings"],
            )
            self.assertEqual(fill_surface.metadata["source_curve_validation_errors"], [])
            self.assertGreaterEqual(fill_surface.metadata["source_curve_planarity_error"], 0.0)

            window.select_curves(
                [dense_curve.id, open_curve.id],
                active_curve_id=dense_curve.id,
            )
            window.loft_between_two_curves()

            loft_surface = window.app_state.surface_collection.surfaces[-1]
            self.assertIn(
                "Loft uses one open curve and one closed curve.",
                loft_surface.metadata["source_curve_validation_warnings"],
            )
            self.assertEqual(loft_surface.metadata["source_curve_validation_errors"], [])
        finally:
            window.root.destroy()

    def test_manual_curves_can_create_fill_and_loft_surfaces(self) -> None:
        with patch("app.main_window.EmbeddedVTKViewport", FakeViewport):
            window = _create_window()

        try:
            _load_sample_model(window)
            closed_curve = _create_manual_curve(
                window,
                [
                    (0.0, 0.0, 0.0),
                    (1.0, 0.0, 0.0),
                    (1.0, 1.0, 0.0),
                ],
                closed=True,
            )

            window.fill_closed_curve()
            self.assertEqual(len(window.app_state.surface_collection.surfaces), 1)
            fill_surface = window.app_state.surface_collection.surfaces[0]
            self.assertEqual(fill_surface.surface_type, "preview_fill")
            self.assertEqual(fill_surface.source_curve_ids, [closed_curve.id])

            first_open_curve = _create_manual_curve(
                window,
                [
                    (0.0, 0.0, 0.2),
                    (1.0, 0.0, 0.2),
                ],
            )
            second_open_curve = _create_manual_curve(
                window,
                [
                    (0.0, 1.0, 0.2),
                    (1.0, 1.0, 0.2),
                ],
            )
            window.select_curves(
                [first_open_curve.id, second_open_curve.id],
                active_curve_id=first_open_curve.id,
            )
            window.loft_between_two_curves()

            self.assertEqual(len(window.app_state.surface_collection.surfaces), 2)
            loft_surface = window.app_state.surface_collection.surfaces[1]
            self.assertEqual(loft_surface.surface_type, "preview_loft")
            self.assertEqual(
                loft_surface.source_curve_ids,
                [first_open_curve.id, second_open_curve.id],
            )
        finally:
            window.root.destroy()


if __name__ == "__main__":
    unittest.main()

