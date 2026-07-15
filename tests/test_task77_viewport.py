from __future__ import annotations

from dataclasses import replace
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from application.state import AppState, MeshObjectState
from curves.curve_state import CurveCollection, StoredCurve
from mesh.triangle_mesh import TriangleMeshData
from viewer.actor_factories import VTKActorAdapter
from viewer.camera_controller import CameraController, frame_pose, named_view_vectors
from viewer.embedded_viewport import EmbeddedVTKViewport
from viewer.picking_service import PickKind, PickingService
from viewer.scene_builder import SceneBuildOptions, SceneBuilder
from viewer.scene_synchronizer import SceneSynchronizer
from viewer.scene_types import (
    CameraRequest,
    CurveRenderItem,
    DisplayStyleSnapshot,
    MeshRenderItem,
    SceneSnapshot,
    SelectionRenderState,
    SurfaceRenderItem,
    geometry_revision,
)

from vtkmodules.vtkRenderingCore import vtkRenderer


def _mesh() -> TriangleMeshData:
    return TriangleMeshData(
        vertices=np.asarray([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 3.0, 0.0]]),
        triangles=np.asarray([[0, 1, 2]], dtype=int),
    )


def _mesh_item(*, transform: np.ndarray | None = None, revision: int = 1) -> MeshRenderItem:
    return MeshRenderItem(
        id="mesh",
        revision=revision,
        mesh=_mesh(),
        transform=np.identity(4) if transform is None else transform,
        selection_keys=("model",),
    )


class _RecordingAdapter:
    def __init__(self) -> None:
        self.created: list[object] = []
        self.geometry_updates: list[object] = []
        self.style_updates: list[object] = []
        self.transform_updates: list[object] = []
        self.visibility_updates: list[tuple[object, bool]] = []
        self.removed: list[object] = []

    def create_actor(self, _category: str, item: object) -> object:
        actor = SimpleNamespace(id=getattr(item, "id"))
        self.created.append(actor)
        return actor

    def update_geometry(self, actor: object, _category: str, _item: object) -> None:
        self.geometry_updates.append(actor)

    def update_style(self, actor: object, _category: str, _item: object) -> None:
        self.style_updates.append(actor)

    def update_transform(self, actor: object, _category: str, _item: object) -> None:
        self.transform_updates.append(actor)

    def set_visibility(self, actor: object, visible: bool) -> None:
        self.visibility_updates.append((actor, visible))

    def remove_actor(self, actor: object) -> None:
        self.removed.append(actor)


class Task77SceneSnapshotTests(unittest.TestCase):
    def test_visible_bounds_merge_transformed_categories_without_adding_origin(self) -> None:
        transform = np.identity(4)
        transform[:3, 3] = [10.0, -4.0, 2.0]
        curve = CurveRenderItem(
            id="curve-a",
            revision=1,
            points=np.asarray([[20.0, 1.0, 4.0], [21.0, 2.0, 6.0]]),
            selection_keys=("curve:curve-a",),
        )
        surface = SurfaceRenderItem(
            id="surface-a",
            revision=1,
            vertices=np.asarray([[30.0, 0.0, 0.0], [31.0, 0.0, 0.0], [30.0, 1.0, 0.0]]),
            faces=np.asarray([[0, 1, 2]]),
        )
        snapshot = SceneSnapshot(
            revision=1,
            meshes=(_mesh_item(transform=transform),),
            curves=(curve,),
            surfaces=(surface,),
            object_origin=(0.0, 0.0, 0.0),
        )

        self.assertEqual(snapshot.visible_bounds(), ((10.0, -4.0, 0.0), (31.0, 2.0, 6.0)))
        self.assertEqual(snapshot.bounds_for_ids({"curve:curve-a"}), curve.world_bounds)

    def test_scene_builder_is_stable_and_changes_only_mutated_curve_revision(self) -> None:
        mesh = _mesh()
        mesh_state = MeshObjectState(
            source_mesh=mesh,
            display_mesh=mesh,
            file_path=None,
            name="mesh",
            origin=np.zeros(3),
            location=np.zeros(3),
            rotation=np.zeros(3),
            transform_matrix=np.identity(4),
            source_bounds_min=np.asarray([0.0, 0.0, 0.0]),
            source_bounds_max=np.asarray([2.0, 3.0, 0.0]),
        )
        curve = StoredCurve(
            id="curve-a",
            name="Curve A",
            section_result_id="result-a",
            plane_id="plane-a",
            original_points=np.asarray([[0.0, 0.0, 0.0], [1.0, 1.0, 0.0]]),
            fitted_points=np.asarray([[0.0, 0.0, 0.0], [1.0, 1.0, 0.0]]),
            mean_error=0.0,
            max_error=0.0,
            is_closed=False,
        )
        state = AppState(mesh_object=mesh_state, curve_collection=CurveCollection(curves=[curve]))
        builder = SceneBuilder()

        first = builder.build(state, options=SceneBuildOptions(show_section_plane=False))
        second = builder.build(state, options=SceneBuildOptions(show_section_plane=False))
        self.assertEqual(first.revision, second.revision)
        self.assertEqual(first.curves[0].revision, second.curves[0].revision)

        curve.fitted_points[1] = [4.0, 5.0, 6.0]
        third = builder.build(state, options=SceneBuildOptions(show_section_plane=False))
        self.assertNotEqual(second.curves[0].revision, third.curves[0].revision)
        self.assertEqual(second.meshes[0].revision, third.meshes[0].revision)

    def test_snapshot_selection_bounds_support_object_and_group_keys(self) -> None:
        curve = CurveRenderItem(
            id="curve-a",
            revision=1,
            points=np.asarray([[5.0, 6.0, 7.0], [8.0, 9.0, 10.0]]),
            selection_keys=("curve:curve-a", "curve_group:result-a"),
        )
        snapshot = SceneSnapshot(revision=1, curves=(curve,))
        self.assertEqual(
            snapshot.bounds_for_ids({"curve_group:result-a"}),
            ((5.0, 6.0, 7.0), (8.0, 9.0, 10.0)),
        )


class Task77IncrementalSyncTests(unittest.TestCase):
    def test_sync_separates_geometry_style_transform_visibility_remove_and_reuse(self) -> None:
        adapter = _RecordingAdapter()
        synchronizer = SceneSynchronizer(adapter)
        curve = CurveRenderItem(
            id="curve-a",
            revision=1,
            points=np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
        )
        first = SceneSnapshot(revision=1, curves=(curve,))
        self.assertEqual(synchronizer.synchronize(first).created, 1)
        self.assertEqual(synchronizer.synchronize(first).reused, 1)

        styled = replace(curve, style=DisplayStyleSnapshot(color=(1.0, 0.0, 0.0)))
        diagnostics = synchronizer.synchronize(SceneSnapshot(revision=2, curves=(styled,)))
        self.assertEqual(diagnostics.style_updated, 1)
        self.assertEqual(diagnostics.geometry_updated, 0)

        changed = replace(styled, revision=2, points=styled.points + [0.0, 1.0, 0.0])
        diagnostics = synchronizer.synchronize(SceneSnapshot(revision=3, curves=(changed,)))
        self.assertEqual(diagnostics.geometry_updated, 1)

        hidden = replace(changed, visible=False)
        self.assertEqual(
            synchronizer.synchronize(SceneSnapshot(revision=4, curves=(hidden,))).visibility_updated,
            1,
        )
        self.assertEqual(synchronizer.synchronize(SceneSnapshot(revision=5)).removed, 1)

    def test_headless_vtk_sync_reuses_actor_and_updates_mapper_only_on_revision(self) -> None:
        renderer = vtkRenderer()
        synchronizer = SceneSynchronizer(VTKActorAdapter(renderer))
        curve = CurveRenderItem(
            id="curve-a",
            revision=1,
            points=np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
        )
        snapshot = SceneSnapshot(revision=1, curves=(curve,))
        synchronizer.synchronize(snapshot)
        actor = synchronizer.cache.get("curve", "curve-a").actor
        polydata = actor.GetMapper().GetInput()

        synchronizer.synchronize(snapshot)
        self.assertIs(synchronizer.cache.get("curve", "curve-a").actor, actor)
        self.assertIs(actor.GetMapper().GetInput(), polydata)

        changed = replace(curve, revision=2, points=np.asarray([[0, 0, 0], [1, 1, 0], [2, 1, 0]]))
        diagnostics = synchronizer.synchronize(SceneSnapshot(revision=2, curves=(changed,)))
        self.assertEqual(diagnostics.geometry_updated, 1)
        self.assertIs(synchronizer.cache.get("curve", "curve-a").actor, actor)
        self.assertIsNot(actor.GetMapper().GetInput(), polydata)

    def test_mesh_transform_updates_without_geometry_rebuild(self) -> None:
        adapter = _RecordingAdapter()
        synchronizer = SceneSynchronizer(adapter)
        item = _mesh_item()
        synchronizer.synchronize(SceneSnapshot(revision=1, meshes=(item,)))
        transform = np.identity(4)
        transform[0, 3] = 12.0
        moved = replace(item, transform=transform)
        diagnostics = synchronizer.synchronize(SceneSnapshot(revision=2, meshes=(moved,)))
        self.assertEqual(diagnostics.transform_updated, 1)
        self.assertEqual(diagnostics.geometry_updated, 0)


class Task77CameraAndPickingTests(unittest.TestCase):
    def test_camera_pose_is_finite_for_point_and_flat_bounds(self) -> None:
        for bounds in (
            ((4.0, 5.0, 6.0), (4.0, 5.0, 6.0)),
            ((-2.0, -3.0, 0.0), (8.0, 9.0, 0.0)),
        ):
            pose = frame_pose(bounds)
            self.assertTrue(np.all(np.isfinite(pose.position)))
            self.assertTrue(np.all(np.isfinite(pose.view_up)))
            self.assertGreater(pose.clipping_range[0], 0.0)
            self.assertGreater(pose.clipping_range[1], pose.clipping_range[0])

    def test_camera_controller_frames_snapshot_and_named_views_are_finite(self) -> None:
        renderer = vtkRenderer()
        renders: list[bool] = []
        controller = CameraController(renderer, lambda **_kwargs: renders.append(True))
        snapshot = SceneSnapshot(revision=1, meshes=(_mesh_item(),))
        self.assertTrue(controller.apply(CameraRequest.frame_all(), snapshot))
        camera = renderer.GetActiveCamera()
        self.assertTrue(np.all(np.isfinite(camera.GetPosition())))
        self.assertTrue(np.allclose(camera.GetFocalPoint(), [1.0, 1.5, 0.0]))
        self.assertGreater(camera.GetClippingRange()[0], 0.0)

        for name in ("front", "back", "left", "right", "top", "bottom", "isometric"):
            direction, up = named_view_vectors(name)
            self.assertTrue(np.all(np.isfinite(direction)))
            self.assertAlmostEqual(float(np.dot(direction, up)), 0.0, places=7)
            controller.set_named_view(name)
        self.assertEqual(len(renders), 8)

    def test_structured_control_point_curve_and_handle_picks(self) -> None:
        control = PickingService.pick_control_point(
            (10.0, 10.0),
            np.asarray([[10.0, 11.0], [40.0, 40.0]]),
            np.asarray([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]),
        )
        self.assertTrue(control.hit)
        self.assertEqual(control.kind, PickKind.MANUAL_CONTROL_POINT)
        handle = PickingService.pick_overbuild_handle(
            (5.0, 5.0),
            np.asarray([[5.0, 5.0]]),
            np.asarray([[7.0, 8.0, 9.0]]),
            surface_id="surface-a",
        )
        self.assertEqual(handle.surface_id, "surface-a")
        curve = PickingService.pick_curve_segment(
            (5.0, 1.0),
            {"curve-a": np.asarray([[0.0, 0.0], [10.0, 0.0]])},
            {"curve-a": np.asarray([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]])},
        )
        self.assertTrue(curve.hit)
        self.assertEqual(curve.segment_index, 0)
        self.assertTrue(np.allclose(curve.position, [5.0, 0.0, 0.0]))

    def test_frame_selected_uses_surface_category_bounds(self) -> None:
        renderer = vtkRenderer()
        controller = CameraController(renderer)
        surface = SurfaceRenderItem(
            id="surface-a",
            revision=1,
            vertices=np.asarray(
                [[40.0, 50.0, 60.0], [44.0, 50.0, 60.0], [40.0, 56.0, 60.0]]
            ),
            faces=np.asarray([[0, 1, 2]]),
            selection_keys=("surface:surface-a",),
        )
        snapshot = SceneSnapshot(
            revision=1,
            surfaces=(surface,),
            selection=SelectionRenderState(
                selected_ids=frozenset({"surface:surface-a"})
            ),
        )
        self.assertTrue(controller.apply(CameraRequest.frame_selected(()), snapshot))
        self.assertTrue(np.allclose(renderer.GetActiveCamera().GetFocalPoint(), [42.0, 53.0, 60.0]))


class Task77CompatibilityFacadeTests(unittest.TestCase):
    def test_snapshot_frames_after_actor_sync_and_ordinary_refresh_preserves_camera(self) -> None:
        viewport = EmbeddedVTKViewport(parent=object())
        viewport._is_started = True
        viewport._render = lambda: None  # type: ignore[method-assign]
        transform = np.identity(4)
        transform[:3, 3] = [10.0, 20.0, 30.0]
        snapshot = SceneSnapshot(
            revision=1,
            meshes=(_mesh_item(transform=transform),),
            camera_request=CameraRequest.frame_all(),
        )

        viewport.render_scene(snapshot)

        self.assertIsNotNone(viewport._mesh_actor)
        self.assertTrue(
            np.allclose(
                viewport.renderer.GetActiveCamera().GetFocalPoint(),
                [11.0, 21.5, 30.0],
            )
        )
        camera = viewport.renderer.GetActiveCamera()
        camera.SetFocalPoint(7.0, 8.0, 9.0)
        camera.SetPosition(17.0, 18.0, 19.0)
        before = (camera.GetPosition(), camera.GetFocalPoint())

        viewport.render_scene(replace(snapshot, revision=2, camera_request=CameraRequest()))

        self.assertEqual(camera.GetPosition(), before[0])
        self.assertEqual(camera.GetFocalPoint(), before[1])


if __name__ == "__main__":
    unittest.main()
