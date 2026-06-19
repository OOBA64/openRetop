from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from curves.curve_state import StoredCurve
from geometry.sections import SectionPolyline, SectionResult
from mesh.triangle_mesh import TriangleMeshData
from regions.region_state import RegionSelection
from sections.section_state import SectionPlaneState, set_plane_axis_offset
from surfaces.surface_preview import SurfacePreviewMesh
from viewer.embedded_viewport import (
    ACTIVE_CURVE_COLOR,
    ACTIVE_CURVE_LINE_WIDTH,
    EmbeddedVTKViewport,
    MANUAL_CURVE_ACTIVE_LINE_WIDTH,
    MANUAL_CURVE_CONTROL_POINT_RADIUS_RATIO,
    MANUAL_CURVE_CONTROL_POLYGON_COLOR,
    MANUAL_CURVE_FIRST_POINT_COLOR,
    MANUAL_CURVE_FIRST_POINT_RADIUS_RATIO,
    MANUAL_CURVE_GHOST_LINE_WIDTH,
    MANUAL_CURVE_MIN_POINT_RADIUS,
    MANUAL_CURVE_POINT_COLOR,
    MANUAL_CURVE_POINT_LINE_WIDTH,
    MANUAL_CURVE_POLYLINE_COLOR,
    MANUAL_CURVE_PREVIEW_LINE_COLOR,
    MANUAL_CURVE_PREVIEW_LINE_WIDTH,
    MANUAL_CURVE_PREVIEW_POINT_COLOR,
    MANUAL_CURVE_SELECTED_POINT_COLOR,
    MANUAL_CURVE_SELECTED_POINT_RADIUS_RATIO,
    MANUAL_CURVE_SNAP_POINT_COLOR,
    MANUAL_CURVE_SNAP_POLYLINE_COLOR,
    MeshPickResult,
    REPAIRED_CURVE_LINE_WIDTH,
    SELECTION_BOUNDING_BOX_LINE_WIDTH,
    SECTION_RESULT_LINE_WIDTH,
    SELECTED_CURVE_LINE_WIDTH,
    SURFACE_SOURCE_CURVE_LINE_WIDTH,
    TINY_CURVE_LINE_WIDTH,
    UNSELECTED_CURVE_LINE_WIDTH,
    _bounds_corners,
    _classify_curve_display,
    _line_polydata,
    _mesh_actor,
    _mesh_polydata,
    _point_to_segment_distance,
    _unit_sphere_mesh,
)
from viewer.overlays import build_bounding_box_outline


class FakeRenderWindow:
    def __init__(self) -> None:
        self.layer_count = 1
        self.added_renderers: list[object] = []
        self.removed_renderers: list[object] = []
        self.render_count = 0
        self.window_info: str | None = None
        self.size: tuple[int, int] | None = None

    def GetNumberOfLayers(self) -> int:
        return self.layer_count

    def SetNumberOfLayers(self, layer_count: int) -> None:
        self.layer_count = int(layer_count)

    def AddRenderer(self, renderer: object) -> None:
        self.added_renderers.append(renderer)

    def RemoveRenderer(self, renderer: object) -> None:
        self.removed_renderers.append(renderer)

    def SetWindowInfo(self, window_info: str) -> None:
        self.window_info = window_info

    def SetSize(self, width: int, height: int) -> None:
        self.size = (int(width), int(height))

    def Render(self) -> None:
        self.render_count += 1


class FakeViewportWidget:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self.after_idle_callbacks: list[object] = []
        self.after_callbacks: list[tuple[int, object]] = []
        self.cancelled_ids: list[str] = []
        self.focus_count = 0
        self.width = 640
        self.height = 480
        self.binds: dict[str, object] = {}

    def after_idle(self, callback: object) -> str:
        after_id = f"idle-{len(self.after_idle_callbacks) + 1}"
        self.after_idle_callbacks.append(callback)
        return after_id

    def after(self, delay_ms: int, callback: object) -> str:
        after_id = f"after-{len(self.after_callbacks) + 1}"
        self.after_callbacks.append((int(delay_ms), callback))
        return after_id

    def after_cancel(self, after_id: str) -> None:
        self.cancelled_ids.append(after_id)

    def bind(self, sequence: str, callback: object) -> None:
        self.binds[sequence] = callback

    def destroy(self) -> None:
        pass

    def focus_set(self) -> None:
        self.focus_count += 1

    def pack(self, **_kwargs: object) -> None:
        pass

    def update_idletasks(self) -> None:
        pass

    def winfo_id(self) -> int:
        return 1234

    def winfo_width(self) -> int:
        return self.width

    def winfo_height(self) -> int:
        return self.height


class FakeInteractor:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def SetEventInformationFlipY(self, *_args: object) -> None:
        self.calls.append("event")

    def SetRenderWindow(self, _render_window: object) -> None:
        self.calls.append("set_render_window")

    def SetInteractorStyle(self, _style: object) -> None:
        self.calls.append("set_style")

    def Initialize(self) -> None:
        self.calls.append("initialize")

    def Enable(self) -> None:
        self.calls.append("enable")

    def MouseMoveEvent(self) -> None:
        self.calls.append("mouse_move")

    def LeftButtonPressEvent(self) -> None:
        self.calls.append("left_press")

    def LeftButtonReleaseEvent(self) -> None:
        self.calls.append("left_release")

    def MiddleButtonPressEvent(self) -> None:
        self.calls.append("middle_press")

    def MiddleButtonReleaseEvent(self) -> None:
        self.calls.append("middle_release")

    def RightButtonPressEvent(self) -> None:
        self.calls.append("right_press")

    def RightButtonReleaseEvent(self) -> None:
        self.calls.append("right_release")

    def MouseWheelForwardEvent(self) -> None:
        self.calls.append("wheel_forward")

    def MouseWheelBackwardEvent(self) -> None:
        self.calls.append("wheel_backward")


class EmbeddedViewportSceneTests(unittest.TestCase):
    def test_manual_curve_visual_constants_use_refined_white_and_orange_scheme(self) -> None:
        vertices, faces = _unit_sphere_mesh()

        self.assertEqual(MANUAL_CURVE_POINT_COLOR, (1.0, 1.0, 1.0))
        self.assertEqual(MANUAL_CURVE_POLYLINE_COLOR, (1.0, 1.0, 1.0))
        self.assertEqual(MANUAL_CURVE_CONTROL_POLYGON_COLOR, (0.65, 0.68, 0.70))
        self.assertEqual(MANUAL_CURVE_PREVIEW_POINT_COLOR, (1.0, 0.48, 0.08))
        self.assertEqual(MANUAL_CURVE_PREVIEW_LINE_COLOR, (1.0, 0.48, 0.08))
        self.assertLess(MANUAL_CURVE_CONTROL_POINT_RADIUS_RATIO, 0.006)
        self.assertGreater(
            MANUAL_CURVE_FIRST_POINT_RADIUS_RATIO,
            MANUAL_CURVE_CONTROL_POINT_RADIUS_RATIO,
        )
        self.assertGreater(
            MANUAL_CURVE_SELECTED_POINT_RADIUS_RATIO,
            MANUAL_CURVE_FIRST_POINT_RADIUS_RATIO,
        )
        self.assertLessEqual(MANUAL_CURVE_MIN_POINT_RADIUS, 0.0035)
        self.assertGreater(MANUAL_CURVE_ACTIVE_LINE_WIDTH, MANUAL_CURVE_PREVIEW_LINE_WIDTH)
        self.assertGreater(len(vertices), 62)
        self.assertGreater(len(faces), 120)

    def _triangle_mesh(self) -> TriangleMeshData:
        return TriangleMeshData(
            vertices=np.asarray(
                [
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                ],
                dtype=float,
            ),
            triangles=np.asarray([[0, 1, 2]], dtype=int),
        )

    def _stored_curve(
        self,
        curve_id: str = "curve-1",
        *,
        selected: bool = False,
        visible: bool = True,
        is_closed: bool = False,
        metadata: dict[str, object] | None = None,
        points: np.ndarray | None = None,
    ) -> StoredCurve:
        curve_points = (
            np.asarray(points, dtype=float)
            if points is not None
            else np.asarray(
                [
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                ],
                dtype=float,
            )
        )
        return StoredCurve(
            id=curve_id,
            name=f"Curve {curve_id}",
            section_result_id="section-result-1",
            plane_id="plane-1",
            original_points=curve_points.copy(),
            fitted_points=curve_points.copy(),
            mean_error=0.0,
            max_error=0.0,
            is_closed=is_closed,
            visible=visible,
            selected=selected,
            metadata=dict(metadata or {}),
        )

    def _viewport(self) -> EmbeddedVTKViewport:
        viewport = EmbeddedVTKViewport(parent=object())
        viewport._is_started = True
        viewport._render = lambda: None  # type: ignore[method-assign]
        return viewport

    def _set_basic_scene(
        self,
        viewport: EmbeddedVTKViewport,
        mesh: TriangleMeshData | None,
        **kwargs: object,
    ) -> None:
        scene_kwargs = {
            "transform_matrix": np.identity(4),
            "show_grid": True,
            "show_axes": True,
            "show_normals": False,
            "show_section_plane": True,
            "section_axis": "Z",
            "section_offset": 0.0,
            "selected_item": None,
            "object_origin": None,
            "scene_bounds_min": None,
            "scene_bounds_max": None,
            "active_transform_mode": None,
            "active_transform_axis": None,
            "active_transform_angle_delta": None,
            "section_result": None,
            "curve_results": [],
            "surface_previews": [],
            "active_surface_id": None,
            "reset_camera": False,
        }
        scene_kwargs.update(kwargs)
        viewport.set_scene(mesh, **scene_kwargs)

    def _actor_count(self, viewport: EmbeddedVTKViewport) -> int:
        return int(viewport.renderer.GetActors().GetNumberOfItems())

    def _actor_points(self, actor: object) -> np.ndarray:
        polydata = actor.GetMapper().GetInput()
        return np.asarray(
            [polydata.GetPoint(index) for index in range(polydata.GetNumberOfPoints())],
            dtype=float,
        )

    def _ring_radius(self, actor: object, origin: tuple[float, float, float]) -> float:
        points = self._actor_points(actor)
        origin_array = np.asarray(origin, dtype=float)
        distances = np.linalg.norm(points - origin_array, axis=1)
        return float(np.mean(distances))

    def test_app_shortcut_keys_are_not_forwarded_to_vtk_interactor(self) -> None:
        class FakeInteractor:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def SetEventInformationFlipY(self, *_args: object) -> None:
                self.calls.append("event")

            def KeyPressEvent(self) -> None:
                self.calls.append("key")

            def CharEvent(self) -> None:
                self.calls.append("char")

        viewport = EmbeddedVTKViewport(parent=object())
        interactor = FakeInteractor()
        viewport.interactor = interactor  # type: ignore[assignment]
        render_calls: list[bool] = []
        viewport._render = lambda: render_calls.append(True)  # type: ignore[method-assign]

        for key in ("r", "n"):
            viewport._on_key_press(SimpleNamespace(keysym=key, char=key, x=4, y=5, state=0))

        self.assertEqual(interactor.calls, [])
        self.assertEqual(render_calls, [])

    def test_non_app_shortcut_keys_still_forward_to_vtk_interactor(self) -> None:
        class FakeInteractor:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def SetEventInformationFlipY(self, *_args: object) -> None:
                self.calls.append("event")

            def KeyPressEvent(self) -> None:
                self.calls.append("key")

            def CharEvent(self) -> None:
                self.calls.append("char")

        viewport = EmbeddedVTKViewport(parent=object())
        interactor = FakeInteractor()
        viewport.interactor = interactor  # type: ignore[assignment]
        render_calls: list[bool] = []
        viewport._render = lambda: render_calls.append(True)  # type: ignore[method-assign]

        viewport._on_key_press(SimpleNamespace(keysym="a", char="a", x=4, y=5, state=0))

        self.assertEqual(interactor.calls, ["event", "key", "char"])
        self.assertEqual(render_calls, [True])

    def test_request_render_coalesces_repeated_requests(self) -> None:
        viewport = EmbeddedVTKViewport(parent=object())
        widget = FakeViewportWidget()
        render_window = FakeRenderWindow()
        viewport.widget = widget  # type: ignore[assignment]
        viewport.render_window = render_window  # type: ignore[assignment]
        viewport._render_counters_enabled = True

        viewport.request_render(scene_dirty=True)
        viewport.request_render(camera_dirty=True)

        self.assertEqual(render_window.render_count, 0)
        self.assertEqual(len(widget.after_idle_callbacks), 1)
        self.assertEqual(viewport.skipped_render_count, 1)
        self.assertTrue(viewport.scene_dirty)
        self.assertTrue(viewport.camera_dirty)

        widget.after_idle_callbacks[0]()  # type: ignore[operator]

        self.assertEqual(render_window.render_count, 1)
        self.assertEqual(viewport.render_count, 1)
        self.assertIsNotNone(viewport.last_render_time)
        self.assertFalse(viewport.scene_dirty)
        self.assertFalse(viewport.camera_dirty)
        self.assertIsNone(viewport._render_after_id)

    def test_passive_mouse_motion_does_not_forward_or_render(self) -> None:
        viewport = EmbeddedVTKViewport(parent=object())
        widget = FakeViewportWidget()
        render_window = FakeRenderWindow()
        interactor = FakeInteractor()
        viewport.widget = widget  # type: ignore[assignment]
        viewport.render_window = render_window  # type: ignore[assignment]
        viewport.interactor = interactor  # type: ignore[assignment]

        viewport._on_mouse_move(SimpleNamespace(x=40, y=50, state=0))

        self.assertEqual(interactor.calls, [])
        self.assertEqual(widget.after_idle_callbacks, [])
        self.assertEqual(render_window.render_count, 0)
        self.assertEqual(viewport._last_mouse_position, (40, 50))

    def test_mouse_drag_forwards_to_vtk_and_requests_render(self) -> None:
        viewport = EmbeddedVTKViewport(parent=object())
        widget = FakeViewportWidget()
        render_window = FakeRenderWindow()
        interactor = FakeInteractor()
        viewport.widget = widget  # type: ignore[assignment]
        viewport.render_window = render_window  # type: ignore[assignment]
        viewport.interactor = interactor  # type: ignore[assignment]
        viewport._left_button_pressed = True
        viewport._active_interaction = True

        viewport._on_mouse_move(SimpleNamespace(x=41, y=52, state=0))

        self.assertEqual(interactor.calls, ["event", "mouse_move"])
        self.assertEqual(len(widget.after_idle_callbacks), 1)
        self.assertEqual(render_window.render_count, 0)
        self.assertTrue(viewport.camera_dirty)

        widget.after_idle_callbacks[0]()  # type: ignore[operator]

        self.assertEqual(render_window.render_count, 1)
        self.assertFalse(viewport.camera_dirty)

    def test_configure_coalesces_render_requests(self) -> None:
        viewport = EmbeddedVTKViewport(parent=object())
        widget = FakeViewportWidget()
        render_window = FakeRenderWindow()
        viewport.widget = widget  # type: ignore[assignment]
        viewport.render_window = render_window  # type: ignore[assignment]
        viewport._render_counters_enabled = True
        widget.width = 810
        widget.height = 456

        viewport._on_configure(SimpleNamespace())
        viewport._on_configure(SimpleNamespace())

        self.assertEqual(render_window.size, (810, 456))
        self.assertEqual(render_window.render_count, 0)
        self.assertEqual(len(widget.after_idle_callbacks), 1)
        self.assertEqual(viewport.skipped_render_count, 1)

        widget.after_idle_callbacks[0]()  # type: ignore[operator]

        self.assertEqual(render_window.render_count, 1)
        self.assertFalse(viewport.overlay_dirty)

    def test_axis_gizmo_sync_does_not_run_when_hidden(self) -> None:
        viewport = EmbeddedVTKViewport(parent=object())
        render_window = FakeRenderWindow()
        viewport.render_window = render_window  # type: ignore[assignment]
        sync_calls: list[bool] = []

        def sync_gizmo(*, force: bool = False) -> None:
            sync_calls.append(force)

        viewport._sync_axis_gizmo_camera = sync_gizmo  # type: ignore[method-assign]

        viewport._render()

        self.assertEqual(sync_calls, [])
        self.assertEqual(render_window.render_count, 1)

    def test_startup_renders_once(self) -> None:
        render_window = FakeRenderWindow()
        created_interactors: list[FakeInteractor] = []

        def create_interactor() -> FakeInteractor:
            interactor = FakeInteractor()
            created_interactors.append(interactor)
            return interactor

        with (
            patch("viewer.embedded_viewport.Canvas", FakeViewportWidget),
            patch("viewer.embedded_viewport.vtkRenderWindow", lambda: render_window),
            patch("viewer.embedded_viewport.vtkRenderWindowInteractor", create_interactor),
        ):
            viewport = EmbeddedVTKViewport(parent=object())
            viewport.start()

        self.assertEqual(render_window.render_count, 1)
        self.assertEqual(render_window.size, (640, 480))
        self.assertEqual(len(created_interactors), 1)
        self.assertTrue(viewport._is_started)

    def test_get_camera_vectors_returns_screen_basis_without_raw_camera(self) -> None:
        viewport = self._viewport()
        camera = viewport.renderer.GetActiveCamera()
        camera.SetPosition(0.0, 0.0, 10.0)
        camera.SetFocalPoint(0.0, 0.0, 0.0)
        camera.SetViewUp(0.0, 1.0, 0.0)

        vectors = viewport.get_camera_vectors()

        self.assertTrue(np.allclose(vectors.forward, [0.0, 0.0, -1.0]))
        self.assertTrue(np.allclose(vectors.right, [1.0, 0.0, 0.0]))
        self.assertTrue(np.allclose(vectors.up, [0.0, 1.0, 0.0]))
        self.assertTrue(np.allclose(vectors.position, [0.0, 0.0, 10.0]))
        self.assertTrue(np.allclose(vectors.focal_point, [0.0, 0.0, 0.0]))

    def test_triangle_mesh_converts_to_vtk_polydata(self) -> None:
        mesh = self._triangle_mesh()
        mesh.compute_vertex_normals()

        polydata = _mesh_polydata(mesh)

        self.assertEqual(polydata.GetNumberOfPoints(), 3)
        self.assertEqual(polydata.GetNumberOfPolys(), 1)
        self.assertIsNotNone(polydata.GetPointData().GetNormals())

    def test_mesh_actor_renders_as_smooth_surface(self) -> None:
        actor = _mesh_actor(self._triangle_mesh())
        prop = actor.GetProperty()

        self.assertEqual(prop.GetRepresentation(), 2)
        self.assertEqual(prop.GetEdgeVisibility(), 0)
        self.assertEqual(prop.GetInterpolation(), 2)

    def test_mesh_actor_is_reused_for_same_display_mesh(self) -> None:
        viewport = EmbeddedVTKViewport(parent=object())
        mesh = self._triangle_mesh()

        first_actor = viewport._ensure_mesh_actor(mesh)
        second_actor = viewport._ensure_mesh_actor(mesh)
        replacement_actor = viewport._ensure_mesh_actor(mesh.copy())

        self.assertIs(first_actor, second_actor)
        self.assertIsNot(first_actor, replacement_actor)

    def test_mesh_pick_result_structure_and_empty_scene_miss(self) -> None:
        hit_result = MeshPickResult(
            hit=True,
            position=np.asarray([1.0, 2.0, 3.0], dtype=float),
            normal=np.asarray([0.0, 0.0, 1.0], dtype=float),
            triangle_index=7,
        )

        self.assertTrue(hit_result.hit)
        self.assertTrue(np.allclose(hit_result.position, [1.0, 2.0, 3.0]))
        self.assertTrue(np.allclose(hit_result.normal, [0.0, 0.0, 1.0]))
        self.assertEqual(hit_result.triangle_index, 7)

        viewport = self._viewport()
        miss_result = viewport.pick_mesh_at_screen_point(20, 30)

        self.assertFalse(miss_result.hit)
        self.assertIsNone(miss_result.position)
        self.assertIsNone(miss_result.normal)
        self.assertIsNone(miss_result.triangle_index)

    def test_view_metrics_can_use_source_bounds_instead_of_display_bounds(self) -> None:
        viewport = EmbeddedVTKViewport(parent=object())
        mesh = self._triangle_mesh()
        matrix = np.identity(4)
        matrix[0, 3] = 3.0

        viewport._update_view_metrics(
            mesh,
            matrix,
            scene_bounds_min=(-2.0, -3.0, -4.0),
            scene_bounds_max=(2.0, 3.0, 4.0),
        )

        self.assertTrue(np.allclose(viewport._mesh_min_bound, [1.0, -3.0, -4.0]))
        self.assertTrue(np.allclose(viewport._mesh_max_bound, [5.0, 3.0, 4.0]))

    def test_interactive_transform_updates_existing_actor_matrix(self) -> None:
        viewport = EmbeddedVTKViewport(parent=object())
        mesh = self._triangle_mesh()
        actor = viewport._ensure_mesh_actor(mesh)
        transform_key = viewport._active_mesh_transform_key(mesh, "move", "X", "model")
        viewport._interactive_transform_key = transform_key
        render_calls: list[bool] = []
        viewport._render = lambda: render_calls.append(True)  # type: ignore[method-assign]
        matrix = np.identity(4)
        matrix[0, 3] = 4.0

        handled = viewport._try_update_interactive_mesh_transform(
            mesh,
            matrix,
            transform_key=transform_key,
            reset_camera=False,
            show_grid=False,
            show_axes=False,
            show_normals=False,
            show_section_plane=False,
            section_axis="Z",
            section_offset=0.0,
            section_planes=None,
            active_section_plane_id=None,
            selected_item="model",
            object_origin=(4.0, 0.0, 0.0),
            active_transform_mode="move",
            active_transform_axis="X",
            active_transform_angle_delta=None,
            section_result=None,
            curve_results=[],
        )

        self.assertTrue(handled)
        self.assertEqual(render_calls, [True])
        self.assertIs(actor, viewport._mesh_actor)
        self.assertAlmostEqual(actor.GetUserMatrix().GetElement(0, 3), 4.0)

    def test_interactive_mesh_fast_path_skips_axis_gizmo_when_visibility_is_unchanged(self) -> None:
        viewport = EmbeddedVTKViewport(parent=object())
        mesh = self._triangle_mesh()
        viewport._ensure_mesh_actor(mesh)
        transform_key = viewport._active_mesh_transform_key(mesh, "move", "X", "model")
        viewport._interactive_transform_key = transform_key
        viewport._axis_gizmo_requested_visible = True
        viewport._axis_gizmo_visible = True
        axis_gizmo_calls: list[bool] = []
        viewport._update_axis_gizmo = axis_gizmo_calls.append  # type: ignore[method-assign]
        viewport._render = lambda: None  # type: ignore[method-assign]

        handled = viewport._try_update_interactive_mesh_transform(
            mesh,
            np.identity(4),
            transform_key=transform_key,
            reset_camera=False,
            show_grid=False,
            show_axes=False,
            show_normals=False,
            show_section_plane=False,
            section_axis="Z",
            section_offset=0.0,
            section_planes=None,
            active_section_plane_id=None,
            selected_item="model",
            object_origin=(0.0, 0.0, 0.0),
            active_transform_mode="move",
            active_transform_axis="X",
            active_transform_angle_delta=None,
            section_result=None,
            curve_results=[],
            show_axis_gizmo=True,
        )

        self.assertTrue(handled)
        self.assertEqual(axis_gizmo_calls, [])

        handled = viewport._try_update_interactive_mesh_transform(
            mesh,
            np.identity(4),
            transform_key=transform_key,
            reset_camera=False,
            show_grid=False,
            show_axes=False,
            show_normals=False,
            show_section_plane=False,
            section_axis="Z",
            section_offset=0.0,
            section_planes=None,
            active_section_plane_id=None,
            selected_item="model",
            object_origin=(0.0, 0.0, 0.0),
            active_transform_mode="move",
            active_transform_axis="X",
            active_transform_angle_delta=None,
            section_result=None,
            curve_results=[],
            show_axis_gizmo=False,
        )

        self.assertTrue(handled)
        self.assertEqual(axis_gizmo_calls, [False])

    def test_interactive_move_updates_selection_overlays_without_duplicate_actors(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()
        self._set_basic_scene(
            viewport,
            mesh,
            selected_item="model",
            object_origin=(0.0, 0.0, 0.0),
            active_transform_mode="move",
            active_transform_axis="X",
        )
        first_actor = viewport._mesh_actor
        first_count = self._actor_count(viewport)
        first_selection_actors = list(viewport._actor_groups["selection_overlays"])
        first_gizmo_actors = list(viewport._actor_groups["active_transform_gizmo"])
        first_selection_key = viewport._group_keys["selection_overlays"]
        first_gizmo_key = viewport._group_keys["active_transform_gizmo"]
        translated = np.identity(4)
        translated[0, 3] = 2.0

        self._set_basic_scene(
            viewport,
            mesh,
            transform_matrix=translated,
            selected_item="model",
            object_origin=(2.0, 0.0, 0.0),
            active_transform_mode="move",
            active_transform_axis="X",
        )

        self.assertIs(viewport._mesh_actor, first_actor)
        self.assertEqual(self._actor_count(viewport), first_count)
        self.assertEqual(viewport._actor_groups["selection_overlays"], first_selection_actors)
        self.assertEqual(viewport._actor_groups["active_transform_gizmo"], first_gizmo_actors)
        self.assertNotEqual(viewport._group_keys["selection_overlays"], first_selection_key)
        self.assertNotEqual(viewport._group_keys["active_transform_gizmo"], first_gizmo_key)
        self.assertIn((2.0, 0.0, 0.0), viewport._group_keys["selection_overlays"])
        self.assertIn((2.0, 0.0, 0.0), viewport._group_keys["active_transform_gizmo"])

    def test_model_selection_bounding_box_is_thin_and_selection_only(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()

        self._set_basic_scene(
            viewport,
            mesh,
            selected_item="model",
            object_origin=(0.0, 0.0, 0.0),
        )

        selection_actors = viewport._actor_groups["selection_overlays"]
        self.assertGreaterEqual(len(selection_actors), 1)
        self.assertAlmostEqual(
            selection_actors[0].GetProperty().GetLineWidth(),
            SELECTION_BOUNDING_BOX_LINE_WIDTH,
        )

        self._set_basic_scene(viewport, mesh, selected_item=None, object_origin=None)

        self.assertNotIn("selection_overlays", viewport._actor_groups)
        self.assertNotIn("selection_overlays", viewport._group_keys)

    def test_interactive_rotate_updates_selection_bounds_without_duplicate_actors(self) -> None:
        viewport = self._viewport()
        mesh = TriangleMeshData(
            vertices=np.asarray(
                [
                    [0.0, 0.0, 0.0],
                    [2.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                ],
                dtype=float,
            ),
            triangles=np.asarray([[0, 1, 2]], dtype=int),
        )
        self._set_basic_scene(
            viewport,
            mesh,
            selected_item="model",
            object_origin=(0.0, 0.0, 0.0),
            active_transform_mode="rotate",
            active_transform_axis="Z",
        )
        first_actor = viewport._mesh_actor
        first_count = self._actor_count(viewport)
        first_selection_key = viewport._group_keys["selection_overlays"]
        rotation = np.asarray(
            [
                [0.0, -1.0, 0.0, 0.0],
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ],
            dtype=float,
        )

        self._set_basic_scene(
            viewport,
            mesh,
            transform_matrix=rotation,
            selected_item="model",
            object_origin=(0.0, 0.0, 0.0),
            active_transform_mode="rotate",
            active_transform_axis="Z",
        )

        self.assertIs(viewport._mesh_actor, first_actor)
        self.assertEqual(self._actor_count(viewport), first_count)
        self.assertNotEqual(viewport._group_keys["selection_overlays"], first_selection_key)
        self.assertTrue(np.allclose(viewport._mesh_min_bound, [-1.0, 0.0, 0.0]))
        self.assertTrue(np.allclose(viewport._mesh_max_bound, [0.0, 2.0, 0.0]))

    def test_rotation_ring_radius_uses_axis_specific_object_extents(self) -> None:
        viewport = self._viewport()
        mesh = TriangleMeshData(
            vertices=np.asarray(
                [
                    [0.0, 0.0, 0.0],
                    [2.0, 0.0, 0.0],
                    [0.0, 4.0, 0.0],
                    [0.0, 0.0, 6.0],
                ],
                dtype=float,
            ),
            triangles=np.asarray([[0, 1, 2], [0, 1, 3]], dtype=int),
        )

        expected_by_axis = {"X": 3.6, "Y": 3.6, "Z": 2.4}
        for axis, expected_radius in expected_by_axis.items():
            viewport._reset_rotation_overlay_bounds()
            self._set_basic_scene(
                viewport,
                mesh,
                selected_item="model",
                object_origin=(0.0, 0.0, 0.0),
                active_transform_mode="rotate",
                active_transform_axis=axis,
                active_transform_angle_delta=0.0,
            )

            ring_actor = viewport._actor_groups["active_transform_gizmo"][1]
            ring_points = self._actor_points(ring_actor)
            self.assertAlmostEqual(self._ring_radius(ring_actor, (0.0, 0.0, 0.0)), expected_radius)
            if axis == "X":
                self.assertTrue(np.allclose(ring_points[:, 0], 0.0))
            elif axis == "Y":
                self.assertTrue(np.allclose(ring_points[:, 1], 0.0))
            else:
                self.assertTrue(np.allclose(ring_points[:, 2], 0.0))

    def test_rotation_ring_radius_stays_stable_during_active_rotation(self) -> None:
        viewport = self._viewport()
        mesh = TriangleMeshData(
            vertices=np.asarray(
                [
                    [0.0, 0.0, 0.0],
                    [2.0, 0.0, 0.0],
                    [0.0, 4.0, 0.0],
                    [0.0, 0.0, 1.0],
                ],
                dtype=float,
            ),
            triangles=np.asarray([[0, 1, 2], [0, 1, 3]], dtype=int),
        )
        self._set_basic_scene(
            viewport,
            mesh,
            selected_item="model",
            object_origin=(0.0, 0.0, 0.0),
            active_transform_mode="rotate",
            active_transform_axis="Z",
            active_transform_angle_delta=0.0,
        )
        initial_radius = self._ring_radius(
            viewport._actor_groups["active_transform_gizmo"][1],
            (0.0, 0.0, 0.0),
        )
        rotation = np.asarray(
            [
                [0.0, -1.0, 0.0, 0.0],
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ],
            dtype=float,
        )

        self._set_basic_scene(
            viewport,
            mesh,
            transform_matrix=rotation,
            selected_item="model",
            object_origin=(0.0, 0.0, 0.0),
            active_transform_mode="rotate",
            active_transform_axis="Z",
            active_transform_angle_delta=25.0,
        )

        updated_radius = self._ring_radius(
            viewport._actor_groups["active_transform_gizmo"][1],
            (0.0, 0.0, 0.0),
        )
        self.assertAlmostEqual(updated_radius, initial_radius)

    def test_rotation_angle_indicator_updates_live_with_angle_delta(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()

        self._set_basic_scene(
            viewport,
            mesh,
            selected_item="model",
            object_origin=(0.0, 0.0, 0.0),
            active_transform_mode="rotate",
            active_transform_axis="Z",
            active_transform_angle_delta=0.0,
        )
        self.assertEqual(len(viewport._actor_groups["active_transform_gizmo"]), 2)

        self._set_basic_scene(
            viewport,
            mesh,
            selected_item="model",
            object_origin=(0.0, 0.0, 0.0),
            active_transform_mode="rotate",
            active_transform_axis="Z",
            active_transform_angle_delta=30.0,
        )

        gizmo_actors = viewport._actor_groups["active_transform_gizmo"]
        self.assertEqual(len(gizmo_actors), 3)
        angle_points = self._actor_points(gizmo_actors[2])
        self.assertGreater(len(angle_points), 3)
        self.assertTrue(np.allclose(angle_points[:, 2], 0.0))

    def test_repeated_set_scene_calls_do_not_duplicate_actors(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()

        self._set_basic_scene(viewport, mesh)
        first_count = self._actor_count(viewport)
        self._set_basic_scene(viewport, mesh)
        second_count = self._actor_count(viewport)
        self._set_basic_scene(viewport, mesh)
        third_count = self._actor_count(viewport)

        self.assertEqual(first_count, 4)
        self.assertEqual(second_count, first_count)
        self.assertEqual(third_count, first_count)
        self.assertEqual(
            set(viewport._actors_by_role),
            {"mesh", "grid", "axes"},
        )
        self.assertEqual(set(viewport._actor_groups), {"section_planes"})
        self.assertEqual(len(viewport._actor_groups["section_planes"]), 1)

    def test_axis_gizmo_toggle_tracks_state_without_scene_actor(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()

        self._set_basic_scene(viewport, mesh, show_axis_gizmo=False)

        self.assertFalse(viewport._axis_gizmo_visible)
        self.assertEqual(self._actor_count(viewport), 4)

        self._set_basic_scene(viewport, mesh, show_axis_gizmo=True)

        self.assertTrue(viewport._axis_gizmo_visible)
        self.assertEqual(self._actor_count(viewport), 4)

    def test_axis_gizmo_uses_existing_render_window_renderer_layer(self) -> None:
        viewport = EmbeddedVTKViewport(parent=object())
        render_window = FakeRenderWindow()
        viewport.render_window = render_window  # type: ignore[assignment]

        viewport._update_axis_gizmo(True)

        self.assertEqual(render_window.layer_count, 2)
        self.assertEqual(len(render_window.added_renderers), 1)
        self.assertIs(viewport._axis_gizmo_renderer, render_window.added_renderers[0])
        self.assertIsNotNone(viewport._axis_gizmo_actor)
        self.assertIsNone(viewport.interactor)
        self.assertFalse(hasattr(viewport, "_orientation_marker_widget"))
        assert viewport._axis_gizmo_renderer is not None
        self.assertEqual(
            tuple(round(value, 2) for value in viewport._axis_gizmo_renderer.GetViewport()),
            (0.84, 0.58, 0.98, 0.74),
        )

        first_renderer = viewport._axis_gizmo_renderer
        first_actor = viewport._axis_gizmo_actor
        viewport._update_axis_gizmo(True)

        self.assertEqual(len(render_window.added_renderers), 1)
        self.assertIs(viewport._axis_gizmo_renderer, first_renderer)
        self.assertIs(viewport._axis_gizmo_actor, first_actor)

        viewport._update_axis_gizmo(False)

        self.assertFalse(viewport._axis_gizmo_visible)
        assert first_actor is not None
        self.assertEqual(first_actor.GetVisibility(), 0)
        self.assertEqual(len(render_window.added_renderers), 1)

        viewport._update_axis_gizmo(True)

        self.assertTrue(viewport._axis_gizmo_visible)
        self.assertEqual(first_actor.GetVisibility(), 1)
        self.assertEqual(len(render_window.added_renderers), 1)

    def test_axis_gizmo_camera_sync_updates_only_when_camera_orientation_changes(self) -> None:
        viewport = EmbeddedVTKViewport(parent=object())
        render_window = FakeRenderWindow()
        viewport.render_window = render_window  # type: ignore[assignment]
        viewport._update_axis_gizmo(True)
        first_key = viewport._axis_gizmo_camera_key

        viewport._render()

        self.assertEqual(viewport._axis_gizmo_camera_key, first_key)
        self.assertEqual(render_window.render_count, 1)

        camera = viewport.renderer.GetActiveCamera()
        camera.SetPosition(0.0, 10.0, 0.0)
        camera.SetFocalPoint(0.0, 0.0, 0.0)
        camera.SetViewUp(0.0, 0.0, 1.0)
        viewport._render()

        self.assertNotEqual(viewport._axis_gizmo_camera_key, first_key)
        self.assertEqual(render_window.render_count, 2)

    def test_multiple_section_planes_render_visible_planes_with_selected_styling(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()
        first_plane = SectionPlaneState(
            id="plane-1",
            name="Section Plane 1",
            axis="Z",
            offset=0.0,
            visible=True,
            selected=False,
        )
        second_plane = SectionPlaneState(
            id="plane-2",
            name="Section Plane 2",
            axis="X",
            offset=0.25,
            visible=True,
            selected=True,
        )
        hidden_plane = SectionPlaneState(
            id="plane-3",
            name="Section Plane 3",
            axis="Y",
            offset=0.5,
            visible=False,
            selected=False,
        )

        self._set_basic_scene(
            viewport,
            mesh,
            show_section_plane=False,
            section_planes=(first_plane, second_plane, hidden_plane),
            active_section_plane_id=second_plane.id,
        )

        self.assertEqual(self._actor_count(viewport), 5)
        self.assertEqual(len(viewport._section_plane_actors), 2)
        self.assertEqual(len(viewport._section_plane_pick_geometries), 2)
        self.assertEqual(len(viewport._actor_groups["section_planes"]), 2)
        self.assertEqual(
            [
                actor.GetProperty().GetLineWidth()
                for actor in viewport._section_plane_actors
            ],
            [2.0, 3.0],
        )
        first_points = self._actor_points(viewport._section_plane_actors[0])
        second_points = self._actor_points(viewport._section_plane_actors[1])
        self.assertTrue(np.allclose(first_points[:, 2], 0.0))
        self.assertTrue(np.allclose(second_points[:, 0], 0.25))

        first_plane.visible = False
        second_plane.visible = False
        self._set_basic_scene(
            viewport,
            mesh,
            show_section_plane=True,
            section_planes=(first_plane, second_plane, hidden_plane),
            active_section_plane_id=second_plane.id,
        )

        self.assertEqual(self._actor_count(viewport), 3)
        self.assertEqual(viewport._section_plane_actors, [])
        self.assertEqual(viewport._section_plane_pick_geometries, [])
        self.assertNotIn("section_planes", viewport._actor_groups)

    def test_rotated_section_plane_preview_uses_origin_and_normal(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()
        normal = np.asarray([1.0, 0.0, 1.0], dtype=float)
        normal = normal / np.linalg.norm(normal)
        plane = SectionPlaneState(
            id="plane-1",
            name="Rotated Plane",
            axis="Z",
            offset=0.0,
            visible=True,
            selected=True,
            origin=np.asarray([0.0, 0.0, 0.0], dtype=float),
            normal=normal,
        )

        self._set_basic_scene(
            viewport,
            mesh,
            section_planes=(plane,),
            active_section_plane_id=plane.id,
        )

        points = self._actor_points(viewport._section_plane_actors[0])
        self.assertTrue(np.allclose(points @ normal, 0.0, atol=1e-7))

    def test_section_plane_preview_updates_existing_actor_during_offset_changes(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()
        plane = SectionPlaneState(
            id="plane-1",
            name="Section Plane 1",
            axis="Z",
            offset=0.0,
            visible=True,
            selected=True,
        )

        self._set_basic_scene(
            viewport,
            mesh,
            section_planes=(plane,),
            active_section_plane_id=plane.id,
        )
        first_actor = viewport._section_plane_actors[0]
        first_actor_count = self._actor_count(viewport)
        first_key = viewport._group_keys["section_planes"]

        set_plane_axis_offset(plane, "Z", 0.25)
        self._set_basic_scene(
            viewport,
            mesh,
            section_planes=(plane,),
            active_section_plane_id=plane.id,
        )

        self.assertIs(viewport._section_plane_actors[0], first_actor)
        self.assertEqual(self._actor_count(viewport), first_actor_count)
        self.assertNotEqual(viewport._group_keys["section_planes"], first_key)
        updated_points = self._actor_points(first_actor)
        self.assertTrue(np.allclose(updated_points[:, 2], 0.25))
        self.assertTrue(
            np.allclose(viewport._section_plane_pick_geometries[0].points[:, 2], 0.25)
        )

    def test_curve_display_classifier_marks_repaired_and_tiny_curves(self) -> None:
        repaired_curve = self._stored_curve(
            metadata={"repair_type": "join"},
        )
        tiny_curve = self._stored_curve(
            curve_id="curve-tiny",
            points=np.asarray(
                [
                    [0.0, 0.0, 0.0],
                    [0.001, 0.0, 0.0],
                ],
                dtype=float,
            ),
        )

        self.assertEqual(_classify_curve_display(repaired_curve), "repaired")
        self.assertEqual(_classify_curve_display(tiny_curve), "tiny")
        self.assertEqual(
            _classify_curve_display(
                self._stored_curve(metadata={"operation": "simplify"}),
            ),
            "repaired",
        )
        self.assertEqual(
            _classify_curve_display(
                self._stored_curve(metadata={"processing_type": "smooth"}),
            ),
            "repaired",
        )

    def test_curve_display_classifier_prioritizes_selected_and_active(self) -> None:
        repaired_selected = self._stored_curve(
            curve_id="curve-selected",
            selected=True,
            metadata={"repair_type": "auto_close"},
        )
        active_selected = self._stored_curve(
            curve_id="curve-active",
            selected=True,
            metadata={"repair_type": "join"},
        )

        self.assertEqual(_classify_curve_display(repaired_selected), "selected")
        self.assertEqual(
            _classify_curve_display(
                active_selected,
                active_curve_id=active_selected.id,
            ),
            "active",
        )

    def test_selected_surface_source_curves_render_with_source_style(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()
        source_curve = self._stored_curve("curve-source")
        normal_curve = self._stored_curve("curve-normal")

        self._set_basic_scene(
            viewport,
            mesh,
            curve_results=[normal_curve, source_curve],
            surface_source_curve_ids=[source_curve.id],
        )

        self.assertIn("curve_results", viewport._actor_groups)
        line_widths = [
            actor.GetProperty().GetLineWidth()
            for actor in viewport._actor_groups["curve_results"]
        ]
        self.assertTrue(
            np.allclose(
                line_widths,
                [UNSELECTED_CURVE_LINE_WIDTH, SURFACE_SOURCE_CURVE_LINE_WIDTH],
            )
        )

    def test_hidden_surface_source_curve_is_not_rendered(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()
        hidden_source = self._stored_curve("curve-hidden", visible=False)
        normal_curve = self._stored_curve("curve-normal")

        self._set_basic_scene(
            viewport,
            mesh,
            curve_results=[hidden_source, normal_curve],
            surface_source_curve_ids=[hidden_source.id],
        )

        self.assertIn("curve_results", viewport._actor_groups)
        actors = viewport._actor_groups["curve_results"]
        self.assertEqual(len(actors), 1)
        self.assertAlmostEqual(
            actors[0].GetProperty().GetLineWidth(),
            UNSELECTED_CURVE_LINE_WIDTH,
            places=5,
        )

    def test_curve_styles_use_distinct_line_widths_for_repaired_tiny_selected_and_active(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()
        tiny_curve = self._stored_curve(
            "curve-tiny",
            points=np.asarray(
                [
                    [0.0, 0.0, 0.0],
                    [0.001, 0.0, 0.0],
                ],
                dtype=float,
            ),
        )
        repaired_curve = self._stored_curve(
            "curve-repaired",
            metadata={"operation": "smooth"},
        )
        selected_curve = self._stored_curve("curve-selected", selected=True)
        active_curve = self._stored_curve("curve-active", selected=True)

        self._set_basic_scene(
            viewport,
            mesh,
            curve_results=[tiny_curve, repaired_curve, selected_curve, active_curve],
            active_curve_id=active_curve.id,
        )

        line_widths = [
            actor.GetProperty().GetLineWidth()
            for actor in viewport._actor_groups["curve_results"]
        ]
        self.assertTrue(
            np.allclose(
                line_widths,
                [
                    TINY_CURVE_LINE_WIDTH,
                    REPAIRED_CURVE_LINE_WIDTH,
                    SELECTED_CURVE_LINE_WIDTH,
                    ACTIVE_CURVE_LINE_WIDTH,
                ],
            )
        )

    def test_selected_curve_renders_with_selected_overlay(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()
        points = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
            ],
            dtype=float,
        )
        first_curve = StoredCurve(
            id="curve-1",
            name="Section 1 Curve 1",
            section_result_id="section-result-1",
            plane_id="plane-1",
            original_points=points,
            fitted_points=points.copy(),
            mean_error=0.0,
            max_error=0.0,
            is_closed=False,
            selected=False,
        )
        second_curve = StoredCurve(
            id="curve-2",
            name="Section 2 Curve 1",
            section_result_id="section-result-2",
            plane_id="plane-2",
            original_points=points,
            fitted_points=points.copy(),
            mean_error=0.0,
            max_error=0.0,
            is_closed=False,
            selected=True,
        )

        self._set_basic_scene(
            viewport,
            mesh,
            curve_results=[first_curve, second_curve],
            active_curve_id=second_curve.id,
        )

        self.assertIn("curve_results", viewport._actor_groups)
        self.assertNotIn("curve_result", viewport._actors_by_role)
        line_widths = [
            actor.GetProperty().GetLineWidth()
            for actor in viewport._actor_groups["curve_results"]
        ]
        self.assertTrue(
            np.allclose(
                line_widths,
                [UNSELECTED_CURVE_LINE_WIDTH, ACTIVE_CURVE_LINE_WIDTH],
            )
        )

    def test_manual_curve_preview_renders_smooth_pending_points_and_clears(self) -> None:
        viewport = self._viewport()
        viewport.render_window = FakeRenderWindow()  # type: ignore[assignment]
        mesh = self._triangle_mesh()
        pending_points = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
            ],
            dtype=float,
        )

        self._set_basic_scene(
            viewport,
            mesh,
            manual_curve_points=pending_points,
            manual_curve_closed=True,
            manual_curve_plane_normal=(0.0, 0.0, 1.0),
            manual_curve_selected_control_point_index=1,
            show_axis_gizmo=False,
        )

        self.assertIn("manual_curve_preview", viewport._actor_groups)
        actors = viewport._actor_groups["manual_curve_preview"]
        self.assertEqual(len(actors), 2)
        self.assertIsNotNone(viewport._manual_overlay_renderer)
        self.assertEqual(viewport.render_window.layer_count, 3)
        self.assertIn(viewport._manual_overlay_renderer, viewport.render_window.added_renderers)
        self.assertAlmostEqual(
            actors[0].GetProperty().GetLineWidth(),
            MANUAL_CURVE_POINT_LINE_WIDTH,
            places=5,
        )
        self.assertAlmostEqual(
            actors[1].GetProperty().GetLineWidth(),
            MANUAL_CURVE_PREVIEW_LINE_WIDTH,
            places=5,
        )
        self.assertEqual(actors[0].GetMapper().GetInput().GetNumberOfLines(), 3)
        self.assertGreater(actors[1].GetMapper().GetInput().GetNumberOfLines(), 3)
        self.assertIn("manual_curve_control_points", viewport._actor_groups)
        point_actors = viewport._actor_groups["manual_curve_control_points"]
        self.assertEqual(len(point_actors), 3)
        self.assertTrue(
            all(actor.GetMapper().GetInput().GetNumberOfPolys() > 0 for actor in point_actors)
        )
        point_colors = [actor.GetProperty().GetColor() for actor in point_actors]
        self.assertTrue(
            any(np.allclose(color, MANUAL_CURVE_FIRST_POINT_COLOR) for color in point_colors)
        )
        self.assertTrue(
            any(np.allclose(color, MANUAL_CURVE_SELECTED_POINT_COLOR) for color in point_colors)
        )

        self._set_basic_scene(
            viewport,
            mesh,
            manual_curve_points=pending_points[:1],
            show_axis_gizmo=False,
        )

        self.assertNotIn("manual_curve_preview", viewport._actor_groups)
        self.assertIn("manual_curve_control_points", viewport._actor_groups)
        point_actors = viewport._actor_groups["manual_curve_control_points"]
        self.assertEqual(len(point_actors), 1)
        self.assertGreater(point_actors[0].GetMapper().GetInput().GetNumberOfPolys(), 0)

        self._set_basic_scene(
            viewport,
            mesh,
            manual_curve_points=[],
            show_axis_gizmo=False,
        )

        self.assertNotIn("manual_curve_preview", viewport._actor_groups)
        self.assertNotIn("manual_curve_control_points", viewport._actor_groups)

    def test_manual_curve_preview_respects_polyline_curve_method(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()
        pending_points = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
            ],
            dtype=float,
        )

        self._set_basic_scene(
            viewport,
            mesh,
            manual_curve_points=pending_points,
            manual_curve_closed=True,
            manual_curve_method="polyline",
            show_axis_gizmo=False,
        )

        actors = viewport._actor_groups["manual_curve_preview"]
        self.assertEqual(actors[0].GetMapper().GetInput().GetNumberOfLines(), 3)
        self.assertEqual(actors[1].GetMapper().GetInput().GetNumberOfLines(), 3)

    def test_manual_curve_snap_preview_uses_distinct_colors(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()
        pending_points = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
            ],
            dtype=float,
        )

        self._set_basic_scene(
            viewport,
            mesh,
            manual_curve_points=pending_points,
            manual_curve_snap_to_mesh=True,
        )

        actors = viewport._actor_groups["manual_curve_preview"]
        line_colors = actors[1].GetMapper().GetInput().GetCellData().GetScalars()
        point_actors = viewport._actor_groups["manual_curve_control_points"]
        point_colors = [actor.GetProperty().GetColor() for actor in point_actors]
        self.assertTrue(
            any(np.allclose(color, MANUAL_CURVE_SNAP_POINT_COLOR) for color in point_colors)
        )
        self.assertTrue(
            np.allclose(
                np.asarray(line_colors.GetTuple3(0), dtype=float) / 255.0,
                MANUAL_CURVE_SNAP_POLYLINE_COLOR,
                atol=1.0 / 255.0,
            )
        )

    def test_manual_curve_ghost_preview_uses_orange_without_recoloring_placed_lines(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()
        preview_point = np.asarray([0.25, 0.5, 0.0], dtype=float)

        self._set_basic_scene(
            viewport,
            mesh,
            manual_curve_points=[],
            manual_curve_preview_point=preview_point,
            manual_curve_preview_valid=True,
            show_axis_gizmo=False,
        )

        self.assertNotIn("manual_curve_preview", viewport._actor_groups)
        point_actors = viewport._actor_groups["manual_curve_control_points"]
        self.assertEqual(len(point_actors), 1)
        self.assertTrue(
            np.allclose(
                point_actors[0].GetProperty().GetColor(),
                MANUAL_CURVE_PREVIEW_POINT_COLOR,
            )
        )

        self._set_basic_scene(
            viewport,
            mesh,
            manual_curve_points=np.asarray([[0.0, 0.0, 0.0]], dtype=float),
            manual_curve_preview_point=np.asarray([1.0, 0.0, 0.0], dtype=float),
            manual_curve_preview_valid=True,
            show_axis_gizmo=False,
        )

        line_actor = viewport._actor_groups["manual_curve_preview"][0]
        line_colors = line_actor.GetMapper().GetInput().GetCellData().GetScalars()
        self.assertAlmostEqual(
            line_actor.GetProperty().GetLineWidth(),
            MANUAL_CURVE_GHOST_LINE_WIDTH,
            places=5,
        )
        self.assertTrue(
            np.allclose(
                np.asarray(line_colors.GetTuple3(0), dtype=float) / 255.0,
                MANUAL_CURVE_PREVIEW_LINE_COLOR,
                atol=1.0 / 255.0,
            )
        )

        placed_points = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
            ],
            dtype=float,
        )
        self._set_basic_scene(
            viewport,
            mesh,
            manual_curve_points=placed_points,
            manual_curve_preview_point=np.asarray([0.01, 0.0, 0.0], dtype=float),
            manual_curve_preview_valid=True,
            manual_curve_preview_snaps_closed=True,
            show_axis_gizmo=False,
        )

        line_actors = viewport._actor_groups["manual_curve_preview"]
        self.assertEqual(len(line_actors), 3)
        control_colors = line_actors[0].GetMapper().GetInput().GetCellData().GetScalars()
        sampled_colors = line_actors[1].GetMapper().GetInput().GetCellData().GetScalars()
        closing_polydata = line_actors[2].GetMapper().GetInput()
        closing_colors = closing_polydata.GetCellData().GetScalars()
        self.assertTrue(
            np.allclose(
                np.asarray(control_colors.GetTuple3(0), dtype=float) / 255.0,
                MANUAL_CURVE_CONTROL_POLYGON_COLOR,
                atol=1.0 / 255.0,
            )
        )
        self.assertTrue(
            np.allclose(
                np.asarray(sampled_colors.GetTuple3(0), dtype=float) / 255.0,
                MANUAL_CURVE_POLYLINE_COLOR,
                atol=1.0 / 255.0,
            )
        )
        self.assertTrue(
            np.allclose(
                np.asarray(closing_colors.GetTuple3(0), dtype=float) / 255.0,
                MANUAL_CURVE_PREVIEW_LINE_COLOR,
                atol=1.0 / 255.0,
            )
        )
        self.assertTrue(np.allclose(closing_polydata.GetPoint(0), placed_points[-1]))
        self.assertTrue(np.allclose(closing_polydata.GetPoint(1), placed_points[0]))
        point_colors = [
            actor.GetProperty().GetColor()
            for actor in viewport._actor_groups["manual_curve_control_points"]
        ]
        self.assertTrue(
            any(np.allclose(color, MANUAL_CURVE_PREVIEW_POINT_COLOR) for color in point_colors)
        )

    def test_selected_manual_curve_result_renders_in_top_overlay_layer(self) -> None:
        viewport = self._viewport()
        viewport.render_window = FakeRenderWindow()  # type: ignore[assignment]
        mesh = self._triangle_mesh()
        points = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
            ],
            dtype=float,
        )
        manual_curve = StoredCurve(
            id="manual-curve-1",
            name="Manual Curve 1",
            section_result_id="",
            plane_id="",
            original_points=points,
            fitted_points=points.copy(),
            mean_error=0.0,
            max_error=0.0,
            is_closed=False,
            selected=True,
            metadata={
                "creation_type": "manual",
                "control_points": points.tolist(),
            },
        )

        self._set_basic_scene(
            viewport,
            mesh,
            curve_results=[manual_curve],
            active_curve_id=manual_curve.id,
            show_axis_gizmo=False,
        )

        self.assertIn("selected_manual_curve_result", viewport._actor_groups)
        self.assertIsNotNone(viewport._manual_overlay_renderer)
        self.assertEqual(viewport.render_window.layer_count, 3)
        self.assertIn(viewport._manual_overlay_renderer, viewport.render_window.added_renderers)
        actors = viewport._actor_groups["selected_manual_curve_result"]
        self.assertEqual(len(actors), 1)
        colors = actors[0].GetMapper().GetInput().GetCellData().GetScalars()
        self.assertTrue(
            np.allclose(
                np.asarray(colors.GetTuple3(0), dtype=float) / 255.0,
                ACTIVE_CURVE_COLOR,
                atol=1.0 / 255.0,
            )
        )

    def test_region_selection_overlay_renders_selected_triangles_and_clears(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()
        region = RegionSelection(
            id="region-1",
            name="Region 1",
            triangle_indices=(0,),
            threshold_degrees=20.0,
            max_triangle_count=50_000,
            source_mesh_identifier="sample.stl",
            source_mesh_name="sample.stl",
        )

        self._set_basic_scene(
            viewport,
            mesh,
            region_selection=region,
            region_selection_color="#FF8800",
            region_selection_edge_color="#FFFFFF",
            region_selection_opacity=0.62,
        )

        self.assertIn("region_selection", viewport._actors_by_role)
        actor = viewport._actors_by_role["region_selection"]
        polydata = actor.GetMapper().GetInput()
        self.assertEqual(polydata.GetNumberOfCells(), 1)
        self.assertAlmostEqual(actor.GetProperty().GetOpacity(), 0.62)
        self.assertTrue(np.allclose(actor.GetProperty().GetColor(), (1.0, 0.533333, 0.0)))
        self.assertTrue(np.allclose(actor.GetProperty().GetEdgeColor(), (1.0, 1.0, 1.0)))
        self.assertTrue(actor.GetProperty().GetEdgeVisibility())

        self._set_basic_scene(viewport, mesh, region_selection=None)

        self.assertNotIn("region_selection", viewport._actors_by_role)

    def test_surface_previews_render_and_clear_with_selected_styling(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()
        first_preview = SurfacePreviewMesh(
            vertices=np.asarray(
                [
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                ],
                dtype=float,
            ),
            faces=np.asarray([[0, 1, 2]], dtype=int),
            source_surface_id="surface-1",
            opacity=0.12,
            wireframe_overlay=False,
        )
        second_preview = SurfacePreviewMesh(
            vertices=np.asarray(
                [
                    [0.0, 0.0, 0.1],
                    [1.0, 0.0, 0.1],
                    [0.0, 1.0, 0.1],
                ],
                dtype=float,
            ),
            faces=np.asarray([[0, 1, 2]], dtype=int),
            source_surface_id="surface-2",
            opacity=0.08,
            wireframe_overlay=False,
        )

        self._set_basic_scene(
            viewport,
            mesh,
            surface_previews=[first_preview, second_preview],
            active_surface_id="surface-2",
        )

        self.assertIn("surface_previews", viewport._actor_groups)
        surface_actors = viewport._actor_groups["surface_previews"]
        self.assertEqual(len(surface_actors), 2)
        self.assertAlmostEqual(surface_actors[0].GetProperty().GetOpacity(), 0.12)
        self.assertEqual(surface_actors[0].GetProperty().GetEdgeVisibility(), 0)
        self.assertLess(surface_actors[0].GetProperty().GetOpacity(), 1.0)
        self.assertGreater(
            surface_actors[1].GetProperty().GetOpacity(),
            surface_actors[0].GetProperty().GetOpacity(),
        )
        self.assertAlmostEqual(surface_actors[1].GetProperty().GetOpacity(), 0.30)
        self.assertEqual(surface_actors[1].GetProperty().GetEdgeVisibility(), 1)
        count_with_previews = self._actor_count(viewport)

        self._set_basic_scene(
            viewport,
            mesh,
            surface_previews=[],
            active_surface_id=None,
        )

        self.assertNotIn("surface_previews", viewport._actor_groups)
        self.assertEqual(self._actor_count(viewport), count_with_previews - 2)

    def test_clearing_mesh_preserves_view_metrics_and_reference_actors(self) -> None:
        viewport = self._viewport()
        mesh = TriangleMeshData(
            vertices=np.asarray(
                [
                    [-2.0, -1.0, 0.0],
                    [4.0, -1.0, 0.0],
                    [-2.0, 3.0, 5.0],
                ],
                dtype=float,
            ),
            triangles=np.asarray([[0, 1, 2]], dtype=int),
        )
        self._set_basic_scene(viewport, mesh)
        view_center = viewport._view_center.copy()
        view_extent = viewport._view_extent
        grid_actor = viewport._actors_by_role["grid"]
        axes_actor = viewport._actors_by_role["axes"]

        self._set_basic_scene(viewport, None, reset_camera=False)

        self.assertTrue(np.allclose(viewport._view_center, view_center))
        self.assertEqual(viewport._view_extent, view_extent)
        self.assertNotIn("mesh", viewport._actors_by_role)
        self.assertIs(viewport._actors_by_role["grid"], grid_actor)
        self.assertIs(viewport._actors_by_role["axes"], axes_actor)

    def test_set_scene_reuses_mesh_actor_when_mesh_identity_is_unchanged(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()
        self._set_basic_scene(viewport, mesh)
        first_actor = viewport._mesh_actor
        translated = np.identity(4)
        translated[0, 3] = 2.5

        self._set_basic_scene(viewport, mesh, transform_matrix=translated)

        self.assertIs(viewport._mesh_actor, first_actor)
        self.assertIs(viewport._actors_by_role["mesh"], first_actor)
        self.assertAlmostEqual(first_actor.GetUserMatrix().GetElement(0, 3), 2.5)

    def test_set_scene_replaces_mesh_actor_when_mesh_identity_changes(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()
        self._set_basic_scene(viewport, mesh)
        first_actor = viewport._mesh_actor

        self._set_basic_scene(viewport, mesh.copy())

        self.assertIsNot(viewport._mesh_actor, first_actor)
        self.assertIs(viewport._actors_by_role["mesh"], viewport._mesh_actor)

    def test_named_view_changes_camera_direction_and_renders_once(self) -> None:
        viewport = self._viewport()
        render_calls: list[bool] = []
        viewport._render = lambda: render_calls.append(True)  # type: ignore[method-assign]
        viewport._view_extent = 4.0
        camera = viewport.renderer.GetActiveCamera()
        camera.SetFocalPoint(3.0, 4.0, 5.0)

        viewport.set_named_view("top")

        self.assertEqual(len(render_calls), 1)
        self.assertTrue(np.allclose(camera.GetFocalPoint(), (3.0, 4.0, 5.0)))
        self.assertTrue(np.allclose(camera.GetDirectionOfProjection(), (0.0, 0.0, -1.0)))
        self.assertTrue(np.allclose(camera.GetViewUp(), (0.0, 1.0, 0.0)))
        self.assertAlmostEqual(
            np.linalg.norm(np.asarray(camera.GetPosition()) - np.asarray(camera.GetFocalPoint())),
            11.2,
        )

        viewport.set_named_view("right")

        self.assertEqual(len(render_calls), 2)
        self.assertTrue(np.allclose(camera.GetDirectionOfProjection(), (-1.0, 0.0, 0.0)))
        self.assertTrue(np.allclose(camera.GetViewUp(), (0.0, 0.0, 1.0)))

    def test_named_view_does_not_change_mesh_transform_or_scene_actors(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()
        transform = np.identity(4)
        transform[0, 3] = 2.0
        transform[1, 3] = -3.0
        self._set_basic_scene(viewport, mesh, transform_matrix=transform)
        actor_count = self._actor_count(viewport)
        mesh_actor = viewport._mesh_actor
        assert mesh_actor is not None
        matrix_before = np.asarray(
            [
                [mesh_actor.GetUserMatrix().GetElement(row, column) for column in range(4)]
                for row in range(4)
            ],
            dtype=float,
        )

        viewport.set_named_view("isometric")

        matrix_after = np.asarray(
            [
                [mesh_actor.GetUserMatrix().GetElement(row, column) for column in range(4)]
                for row in range(4)
            ],
            dtype=float,
        )
        self.assertTrue(np.allclose(matrix_after, matrix_before))
        self.assertIs(viewport._mesh_actor, mesh_actor)
        self.assertEqual(self._actor_count(viewport), actor_count)

    def test_clearing_section_result_removes_section_actor(self) -> None:
        viewport = self._viewport()
        mesh = self._triangle_mesh()
        section_result = SectionResult(
            axis="Z",
            offset=0.0,
            polylines=(
                SectionPolyline(
                    points=np.asarray(
                        [
                            [0.0, 0.0, 0.0],
                            [1.0, 0.0, 0.0],
                            [0.0, 1.0, 0.0],
                        ],
                        dtype=float,
                    )
                ),
            ),
            segment_count=2,
        )

        self._set_basic_scene(viewport, mesh, section_result=section_result)
        section_count = self._actor_count(viewport)
        section_actor = viewport._actors_by_role["section_result"]
        self.assertAlmostEqual(
            section_actor.GetProperty().GetLineWidth(),
            SECTION_RESULT_LINE_WIDTH,
            places=5,
        )
        self.assertLess(SECTION_RESULT_LINE_WIDTH, SELECTED_CURVE_LINE_WIDTH)

        self._set_basic_scene(viewport, mesh, section_result=None)

        self.assertNotIn("section_result", viewport._actors_by_role)
        self.assertEqual(self._actor_count(viewport), section_count - 1)
        self.assertIsNot(viewport._actors_by_role.get("section_result"), section_actor)

    def test_line_geometry_converts_to_vtk_polydata_with_cell_colors(self) -> None:
        lines = build_bounding_box_outline((0.0, 0.0, 0.0), (1.0, 2.0, 3.0))

        polydata = _line_polydata(lines)

        self.assertEqual(polydata.GetNumberOfPoints(), 8)
        self.assertEqual(polydata.GetNumberOfLines(), 12)
        self.assertIsNotNone(polydata.GetCellData().GetScalars())

    def test_screen_selection_helpers_are_constant_size(self) -> None:
        corners = _bounds_corners((-1.0, -2.0, -3.0), (4.0, 5.0, 6.0))

        self.assertEqual(corners.shape, (8, 3))
        self.assertAlmostEqual(
            _point_to_segment_distance((5.0, 5.0), (0.0, 0.0), (10.0, 0.0)),
            5.0,
        )
        self.assertAlmostEqual(
            _point_to_segment_distance((11.0, 0.0), (0.0, 0.0), (10.0, 0.0)),
            1.0,
        )


if __name__ == "__main__":
    unittest.main()
