from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from application.analysis_controller import AnalysisController, AnalysisSnapshot
from application.events import ApplicationEvent, EventPublisher, StatusEvent, StatusLevel
from application.state import AppState, MeshObjectState
from mesh.spatial_index import MeshClosestPointResult
from mesh.triangle_mesh import TriangleMeshData


def _mesh() -> TriangleMeshData:
    return TriangleMeshData(
        vertices=np.asarray(
            [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 2.0, 0.0]],
            dtype=float,
        ),
        triangles=np.asarray([[0, 1, 2]], dtype=int),
    )


def _state() -> AppState:
    mesh = _mesh()
    return AppState(
        mesh_object=MeshObjectState(
            source_mesh=mesh,
            display_mesh=mesh,
            file_path=Path("analysis.stl"),
            name="analysis.stl",
            origin=np.zeros(3),
            location=np.zeros(3),
            rotation=np.zeros(3),
            source_triangle_count=1,
            display_triangle_count=1,
        )
    )


class _FakeIndex:
    def query_closest_points(
        self,
        points: object,
        *,
        max_distance: float | None = None,
        preserve_missed_points: bool = True,
    ) -> MeshClosestPointResult:
        del preserve_missed_points
        source = np.asarray(points, dtype=float).reshape((-1, 3))
        closest = source.copy()
        closest[:, 2] = 0.0
        distances = np.abs(source[:, 2])
        hit_mask = np.ones(len(source), dtype=bool)
        if max_distance is not None:
            hit_mask = distances <= float(max_distance)
        closest[~hit_mask] = source[~hit_mask]
        return MeshClosestPointResult(
            source_points=source,
            closest_points=closest,
            distances=distances,
            hit_mask=hit_mask,
            triangle_indices=np.where(hit_mask, 0, -1),
            normals=np.tile([0.0, 0.0, 1.0], (len(source), 1)),
            queried_point_count=len(source),
            hit_count=int(np.count_nonzero(hit_mask)),
            missed_count=int(len(source) - np.count_nonzero(hit_mask)),
            build_time_seconds=0.01,
            query_time_seconds=0.02,
            backend="fake-shared-index",
        )


class _FakeQueryService:
    def __init__(self) -> None:
        self.calls: list[tuple[TriangleMeshData, object | None]] = []
        self.index = _FakeIndex()

    def get_index(
        self,
        mesh: TriangleMeshData,
        *,
        mesh_revision: object | None = None,
    ) -> _FakeIndex:
        self.calls.append((mesh, mesh_revision))
        return self.index


class AnalysisControllerTests(unittest.TestCase):
    def test_inspection_is_read_only_and_returns_immutable_summary(self) -> None:
        state = _state()
        result = AnalysisController(state).inspect_state()

        self.assertTrue(result.success)
        self.assertFalse(result.changed)
        self.assertFalse(result.dirty)
        snapshot = result.metadata["analysis_snapshot"]
        self.assertIsInstance(snapshot, AnalysisSnapshot)
        self.assertEqual(snapshot.mesh_name, "analysis.stl")
        self.assertEqual(snapshot.source_vertex_count, 3)
        self.assertEqual(snapshot.display_triangle_count, 1)
        self.assertEqual(snapshot.minimum_bound, (0.0, 0.0, 0.0))
        self.assertEqual(snapshot.maximum_bound, (2.0, 2.0, 0.0))

    def test_missing_mesh_or_service_returns_typed_failure(self) -> None:
        no_mesh = AnalysisController(AppState()).compute_deviation([[0, 0, 0]])
        no_service = AnalysisController(_state()).compute_deviation([[0, 0, 0]])

        self.assertFalse(no_mesh.success)
        self.assertFalse(no_service.success)
        self.assertIn("loaded mesh", no_mesh.errors[0].lower())
        self.assertIn("query service", no_service.errors[0].lower())

    def test_snapshot_reports_transformed_source_bounds(self) -> None:
        state = _state()
        assert state.mesh_object is not None
        state.mesh_object.location = np.asarray([10.0, 0.0, 0.0])
        state.mesh_object.rotation = np.asarray([0.0, 0.0, 90.0])

        snapshot = AnalysisController(state).snapshot()

        np.testing.assert_allclose(snapshot.minimum_bound, [8.0, 0.0, 0.0])
        np.testing.assert_allclose(snapshot.maximum_bound, [10.0, 2.0, 0.0])

    def test_deviation_uses_injected_shared_index_and_reports_warning(self) -> None:
        state = _state()
        service = _FakeQueryService()
        events = EventPublisher()
        received: list[ApplicationEvent] = []
        events.subscribe(ApplicationEvent, received.append)
        controller = AnalysisController(
            state,
            events=events,
            mesh_query_service=service,
        )
        points = np.asarray([[0.25, 0.25, 1.0], [0.5, 0.25, 2.0]])

        result = controller.compute_deviation(
            points,
            mesh_revision="mesh-rev-7",
            max_distance=1.5,
            signed=True,
        )

        self.assertTrue(result.success)
        self.assertFalse(result.changed)
        self.assertFalse(result.dirty)
        self.assertEqual(len(service.calls), 1)
        self.assertIs(service.calls[0][0], state.mesh_object.display_mesh)  # type: ignore[union-attr]
        self.assertEqual(service.calls[0][1], "mesh-rev-7")
        self.assertEqual(result.metadata["sample_count"], 2)
        self.assertEqual(result.metadata["failed_sample_count"], 1)
        self.assertEqual(result.metadata["query_backend"], "fake-shared-index")
        self.assertEqual(len(result.warnings), 1)
        status_events = [event for event in received if isinstance(event, StatusEvent)]
        self.assertEqual(status_events[-1].level, StatusLevel.WARNING)


if __name__ == "__main__":
    unittest.main()
