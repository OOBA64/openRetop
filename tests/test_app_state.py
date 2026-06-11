from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.app_state import AppState
from app.object_state import MeshObjectState
from app.selection_types import SELECT_CURVE, SELECT_MODEL, SELECT_SECTION_PLANE
from app.transform_state import ActiveTransformState
from curves.curve_state import CurveCollection
from geometry.curves import CurveFitResult
from geometry.sections import SectionResult
from mesh.display_proxy import DEFAULT_PROXY_QUALITY
from mesh.triangle_mesh import TriangleMeshData
from sections.section_state import SectionCollection, StoredSectionResult
from surfaces.surface_state import SurfaceCollection


def _mesh() -> TriangleMeshData:
    return TriangleMeshData(
        vertices=np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
            ]
        ),
        triangles=np.asarray([[0, 1, 2]]),
    )


def _mesh_object() -> MeshObjectState:
    mesh = _mesh()
    return MeshObjectState(
        source_mesh=mesh,
        display_mesh=mesh.copy(),
        file_path=Path("sample.stl"),
        name="sample.stl",
        origin=np.asarray([0.0, 0.0, 0.0]),
        location=np.asarray([0.0, 0.0, 0.0]),
        rotation=np.asarray([0.0, 0.0, 0.0]),
    )


def _transform_state() -> ActiveTransformState:
    return ActiveTransformState(
        selected_item=SELECT_MODEL,
        mode="move",
        mouse_start=(10, 20),
        axis_constraint="X",
        location=np.asarray([1.0, 2.0, 3.0]),
        rotation=np.asarray([0.0, 0.0, 45.0]),
        section_axis="Z",
        section_offset=0.25,
    )


def _curve_result() -> CurveFitResult:
    points = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
        ]
    )
    return CurveFitResult(
        original_points=points,
        fitted_points=points.copy(),
        mean_error=0.0,
        max_error=0.0,
        is_closed=False,
    )


class AppStateTests(unittest.TestCase):
    def test_default_values_are_empty_non_ui_state(self) -> None:
        state = AppState()
        other_state = AppState()

        self.assertIsNone(state.mesh_object)
        self.assertIsNone(state.selected_item)
        self.assertIsNone(state.active_transform_mode)
        self.assertIsNone(state.active_transform_axis)
        self.assertIsNone(state.transform_state)
        self.assertIsNone(state.section_result)
        self.assertEqual(state.curve_results, [])
        self.assertIsNot(state.curve_results, other_state.curve_results)
        self.assertIsInstance(state.curve_collection, CurveCollection)
        self.assertIsNot(state.curve_collection, other_state.curve_collection)
        self.assertEqual(state.curve_collection.curves, [])
        self.assertIsNone(state.curve_collection.active_curve_id)
        self.assertIsInstance(state.surface_collection, SurfaceCollection)
        self.assertIsNot(state.surface_collection, other_state.surface_collection)
        self.assertEqual(state.surface_collection.surfaces, [])
        self.assertIsNone(state.surface_collection.active_surface_id)
        self.assertIsInstance(state.section_collection, SectionCollection)
        self.assertIsNot(state.section_collection, other_state.section_collection)
        self.assertEqual(len(state.section_collection.planes), 1)
        self.assertEqual(state.section_collection.results, [])

        active_plane = state.section_collection.planes[0]
        self.assertEqual(state.section_collection.active_plane_id, active_plane.id)
        self.assertEqual(active_plane.name, "Section Plane 1")
        self.assertEqual(active_plane.axis, "Z")
        self.assertEqual(active_plane.offset, 0.0)
        self.assertTrue(active_plane.visible)
        self.assertTrue(active_plane.selected)

    def test_clear_selection_resets_only_selection_and_transform_fields(self) -> None:
        mesh_object = _mesh_object()
        section_result = SectionResult(axis="Z", offset=0.0, polylines=tuple(), segment_count=0)
        curve_result = _curve_result()
        state = AppState(
            mesh_object=mesh_object,
            selected_item=SELECT_MODEL,
            active_transform_mode="move",
            active_transform_axis="X",
            transform_state=_transform_state(),
            section_result=section_result,
            curve_results=[curve_result],
        )

        state.clear_selection()

        self.assertIs(state.mesh_object, mesh_object)
        self.assertIsNone(state.selected_item)
        self.assertIsNone(state.active_transform_mode)
        self.assertIsNone(state.active_transform_axis)
        self.assertIsNone(state.transform_state)
        self.assertIs(state.section_result, section_result)
        self.assertEqual(state.curve_results, [curve_result])

    def test_clear_sections_resets_only_section_results(self) -> None:
        mesh_object = _mesh_object()
        transform_state = _transform_state()
        state = AppState(
            mesh_object=mesh_object,
            selected_item=SELECT_SECTION_PLANE,
            active_transform_mode="move",
            active_transform_axis="Z",
            transform_state=transform_state,
            section_result=SectionResult(axis="Z", offset=0.0, polylines=tuple(), segment_count=0),
            curve_results=[_curve_result()],
        )

        state.clear_sections()

        self.assertIs(state.mesh_object, mesh_object)
        self.assertEqual(state.selected_item, SELECT_SECTION_PLANE)
        self.assertEqual(state.active_transform_mode, "move")
        self.assertEqual(state.active_transform_axis, "Z")
        self.assertIs(state.transform_state, transform_state)
        self.assertIsNone(state.section_result)
        self.assertEqual(state.curve_results, [])
        self.assertEqual(state.curve_collection.curves, [])
        self.assertIsNone(state.curve_collection.active_curve_id)
        self.assertEqual(len(state.section_collection.planes), 1)
        self.assertEqual(state.section_collection.results, [])

    def test_clear_sections_clears_section_collection_results_without_removing_planes(self) -> None:
        state = AppState()
        active_plane = state.section_collection.planes[0]
        stored_result = StoredSectionResult(
            id="result-1",
            name="Section 1",
            plane_id=active_plane.id,
            axis="Z",
            offset=0.0,
            result=SectionResult(
                axis="Z",
                offset=0.0,
                polylines=tuple(),
                segment_count=0,
            ),
        )
        state.section_collection.results.append(stored_result)

        state.clear_sections()

        self.assertEqual(state.section_collection.planes, [active_plane])
        self.assertEqual(state.section_collection.active_plane_id, active_plane.id)
        self.assertEqual(state.section_collection.results, [])

    def test_mesh_object_state_can_be_constructed(self) -> None:
        source_mesh = _mesh()
        display_mesh = source_mesh.copy()

        mesh_object = MeshObjectState(
            source_mesh=source_mesh,
            display_mesh=display_mesh,
            file_path=Path("sample.stl"),
            name="sample.stl",
            origin=np.asarray([0.1, 0.2, 0.3]),
            location=np.asarray([1.0, 2.0, 3.0]),
            rotation=np.asarray([10.0, 20.0, 30.0]),
        )

        self.assertIs(mesh_object.source_mesh, source_mesh)
        self.assertIs(mesh_object.display_mesh, display_mesh)
        self.assertEqual(mesh_object.file_path, Path("sample.stl"))
        self.assertEqual(mesh_object.name, "sample.stl")
        self.assertTrue(np.allclose(mesh_object.origin, [0.1, 0.2, 0.3]))
        self.assertTrue(np.allclose(mesh_object.location, [1.0, 2.0, 3.0]))
        self.assertTrue(np.allclose(mesh_object.rotation, [10.0, 20.0, 30.0]))
        self.assertEqual(mesh_object.scale, 1.0)
        self.assertEqual(mesh_object.proxy_quality, DEFAULT_PROXY_QUALITY)

    def test_active_transform_state_can_be_constructed(self) -> None:
        transform_state = ActiveTransformState(
            selected_item=SELECT_MODEL,
            mode="rotate",
            mouse_start=(12, 34),
            axis_constraint=None,
            location=np.asarray([1.0, 2.0, 3.0]),
            rotation=np.asarray([4.0, 5.0, 6.0]),
            section_axis="Y",
            section_offset=1.25,
        )

        self.assertEqual(transform_state.selected_item, SELECT_MODEL)
        self.assertEqual(transform_state.mode, "rotate")
        self.assertEqual(transform_state.mouse_start, (12, 34))
        self.assertIsNone(transform_state.axis_constraint)
        self.assertTrue(np.allclose(transform_state.location, [1.0, 2.0, 3.0]))
        self.assertTrue(np.allclose(transform_state.rotation, [4.0, 5.0, 6.0]))
        self.assertEqual(transform_state.section_axis, "Y")
        self.assertEqual(transform_state.section_offset, 1.25)

    def test_selection_constants_import_correctly(self) -> None:
        self.assertEqual(SELECT_MODEL, "model")
        self.assertEqual(SELECT_SECTION_PLANE, "section_plane")
        self.assertEqual(SELECT_CURVE, "curve")


if __name__ == "__main__":
    unittest.main()
