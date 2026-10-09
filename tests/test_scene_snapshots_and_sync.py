from __future__ import annotations

import unittest
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
from vtkmodules.vtkRenderingCore import vtkRenderer

from openretop.application.state import AppState, MeshObjectState
from openretop.mesh.triangle_mesh import TriangleMeshData
from openretop.viewer.actor_factories import VTKActorAdapter
from openretop.viewer.camera_controller import CameraController, frame_pose, named_view_vectors
from openretop.viewer.modeling_scene import ModelingSceneInput
from openretop.viewer.picking_service import PickingService, PickKind
from openretop.viewer.scene_builder import SceneBuilder, SceneBuildOptions
from openretop.viewer.scene_synchronizer import SceneSynchronizer
from openretop.viewer.scene_types import (
    CameraRequest,
    CurveRenderItem,
    DisplayStyleSnapshot,
    MeshRenderItem,
    SceneSnapshot,
    SelectionRenderState,
    SurfaceRenderItem,
)


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
        actor = SimpleNamespace(id=item.id)
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


class SceneSnapshotTests(unittest.TestCase):
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

    def test_scene_builder_is_stable_and_changes_only_the_edited_sketch_curve(self) -> None:
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
        state = AppState(mesh_object=mesh_state)
        builder = SceneBuilder()
        options = SceneBuildOptions(show_section_plane=False)
        polyline = np.asarray([[0.0, 0.0, 0.0], [1.0, 1.0, 0.0]])

        def build(line: np.ndarray):
            return builder.build(state, options=options, modeling=ModelingSceneInput(sketch_curves=(("curve-a", line, False),)))

        first, second = build(polyline), build(polyline)
        self.assertEqual(first.revision, second.revision)
        self.assertEqual(first.model_edges[0].revision, second.model_edges[0].revision)

        # editing a sketch curve rebuilds its polyline (a new array)
        third = build(np.asarray([[0.0, 0.0, 0.0], [4.0, 5.0, 6.0]]))
        self.assertNotEqual(second.model_edges[0].revision, third.model_edges[0].revision)
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


class IncrementalSyncTests(unittest.TestCase):
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


class CameraAndPickingTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
