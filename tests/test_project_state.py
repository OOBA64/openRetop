from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from curves.curve_state import CurveCollection, StoredCurve, add_curve
from curves.manual_curve import DEFAULT_MANUAL_CURVE_SAMPLE_COUNT
from geometry.sections import SectionPolyline, SectionResult
from project.project_data import PROJECT_VERSION
from project.project_state import project_from_app_state
from sections.section_state import (
    SectionCollection,
    SectionPlaneState,
    StoredSectionResult,
    add_plane,
    add_result,
    set_active_plane,
)
from surfaces.surface_state import SurfaceCollection, SurfacePatch, add_surface


class ProjectStateTests(unittest.TestCase):
    def test_project_from_app_state_uses_defaults_without_mesh(self) -> None:
        project = project_from_app_state(
            mesh_object=None,
            proxy_quality="Low",
            show_grid=False,
            show_axes=False,
            show_normals=True,
            section_axis="Y",
            section_offset=1.25,
            show_section_plane=True,
        )

        self.assertEqual(project.version, PROJECT_VERSION)
        self.assertEqual(project.name, "Untitled Project")
        self.assertIsNone(project.mesh_path)
        self.assertIsNone(project.mesh_name)
        self.assertTrue(project.mesh_visible)
        self.assertEqual(project.transform.location, [0.0, 0.0, 0.0])
        self.assertEqual(project.transform.rotation, [0.0, 0.0, 0.0])
        self.assertEqual(project.transform.scale, 1.0)
        self.assertEqual(project.transform.origin, [0.0, 0.0, 0.0])
        self.assertEqual(project.display.proxy_quality, "Low")
        self.assertFalse(project.display.show_grid)
        self.assertFalse(project.display.show_axes)
        self.assertTrue(project.display.show_normals)
        self.assertEqual(project.section.axis, "Y")
        self.assertEqual(project.section.offset, 1.25)
        self.assertTrue(project.section.show_plane)
        self.assertEqual(project.section_planes, [])
        self.assertIsNone(project.active_section_plane_id)
        self.assertEqual(project.section_results, [])
        self.assertEqual(project.curves, [])
        self.assertEqual(project.surfaces, [])

    def test_project_from_app_state_uses_fake_mesh_transform_and_path(self) -> None:
        mesh_path = Path("models") / "scan.stl"
        mesh_object = SimpleNamespace(
            file_path=mesh_path,
            name="Scan Body",
            visible=False,
            location=np.asarray([1.0, 2.0, 3.0], dtype=float),
            rotation=np.asarray([10.0, 20.0, 30.0], dtype=float),
            scale=2.5,
            origin=np.asarray([0.5, 0.25, 0.0], dtype=float),
        )

        project = project_from_app_state(
            mesh_object=mesh_object,
            proxy_quality="High",
            show_grid=True,
            show_axes=False,
            show_normals=False,
            section_axis="z",
            section_offset=-0.5,
            show_section_plane=False,
        )

        self.assertEqual(project.mesh_path, str(mesh_path))
        self.assertEqual(project.mesh_name, "Scan Body")
        self.assertFalse(project.mesh_visible)
        self.assertEqual(project.transform.location, [1.0, 2.0, 3.0])
        self.assertEqual(project.transform.rotation, [10.0, 20.0, 30.0])
        self.assertEqual(project.transform.scale, 2.5)
        self.assertEqual(project.transform.origin, [0.5, 0.25, 0.0])
        self.assertEqual(project.display.proxy_quality, "High")
        self.assertTrue(project.display.show_grid)
        self.assertFalse(project.display.show_axes)
        self.assertFalse(project.display.show_normals)
        self.assertEqual(project.section.axis, "Z")
        self.assertEqual(project.section.offset, -0.5)
        self.assertFalse(project.section.show_plane)
        self.assertEqual(project.section_planes, [])
        self.assertIsNone(project.active_section_plane_id)

    def test_project_from_app_state_exports_section_collection_planes(self) -> None:
        collection = SectionCollection()
        first_plane = SectionPlaneState(
            id="plane-a",
            name="Base Section",
            axis="z",
            offset=0.25,
            visible=True,
        )
        second_plane = SectionPlaneState(
            id="plane-b",
            name="Side Section",
            axis="x",
            offset=-0.5,
            visible=False,
        )
        add_plane(collection, first_plane)
        add_plane(collection, second_plane)
        set_active_plane(collection, second_plane.id)

        project = project_from_app_state(
            mesh_object=None,
            proxy_quality="Medium",
            show_grid=True,
            show_axes=True,
            show_normals=False,
            section_axis="X",
            section_offset=-0.5,
            show_section_plane=False,
            section_collection=collection,
        )

        self.assertEqual(len(project.section_planes), 2)
        self.assertEqual(project.section_planes[0].id, "plane-a")
        self.assertEqual(project.section_planes[0].name, "Base Section")
        self.assertEqual(project.section_planes[0].axis, "Z")
        self.assertEqual(project.section_planes[0].offset, 0.25)
        self.assertTrue(project.section_planes[0].visible)
        self.assertEqual(project.section_planes[0].origin, [0.0, 0.0, 0.25])
        self.assertEqual(project.section_planes[0].normal, [0.0, 0.0, 1.0])
        self.assertEqual(project.section_planes[1].id, "plane-b")
        self.assertEqual(project.section_planes[1].name, "Side Section")
        self.assertEqual(project.section_planes[1].axis, "X")
        self.assertEqual(project.section_planes[1].offset, -0.5)
        self.assertFalse(project.section_planes[1].visible)
        self.assertEqual(project.section_planes[1].origin, [-0.5, 0.0, 0.0])
        self.assertEqual(project.section_planes[1].normal, [1.0, 0.0, 0.0])
        self.assertEqual(project.active_section_plane_id, "plane-b")

    def test_project_from_app_state_exports_section_results(self) -> None:
        collection = SectionCollection()
        add_plane(
            collection,
            SectionPlaneState(
                id="plane-a",
                name="Cut Plane",
                axis="Z",
                offset=0.25,
                visible=True,
            ),
        )
        add_result(
            collection,
            StoredSectionResult(
                id="section-a",
                name="Rim Section",
                plane_id="plane-a",
                axis="Z",
                offset=0.25,
                visible=False,
                result=SectionResult(
                    axis="Z",
                    offset=0.25,
                    polylines=(
                        SectionPolyline(
                            points=np.asarray(
                                [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                                dtype=float,
                            )
                        ),
                    ),
                    segment_count=1,
                ),
            ),
        )

        project = project_from_app_state(
            mesh_object=None,
            proxy_quality="Medium",
            show_grid=True,
            show_axes=True,
            show_normals=False,
            section_axis="Z",
            section_offset=0.0,
            show_section_plane=False,
            section_collection=collection,
        )

        self.assertEqual(len(project.section_results), 1)
        result = project.section_results[0]
        self.assertEqual(result.id, "section-a")
        self.assertEqual(result.name, "Rim Section")
        self.assertEqual(result.plane_id, "plane-a")
        self.assertEqual(result.axis, "Z")
        self.assertEqual(result.offset, 0.25)
        self.assertFalse(result.visible)
        self.assertEqual(result.plane_origin, [0.0, 0.0, 0.25])
        self.assertEqual(result.plane_normal, [0.0, 0.0, 1.0])
        self.assertFalse(result.is_arbitrary_plane)
        self.assertEqual(result.polylines, [[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]])
        self.assertEqual(result.segment_count, 1)

    def test_project_from_app_state_exports_arbitrary_section_result_metadata(self) -> None:
        collection = SectionCollection()
        plane = SectionPlaneState(
            id="plane-a",
            name="Rotated Plane",
            axis="Z",
            offset=0.0,
            visible=True,
            origin=np.asarray([0.0, 0.0, 0.0], dtype=float),
            normal=np.asarray([1.0, 0.0, 1.0], dtype=float),
        )
        add_plane(collection, plane)
        normal = np.asarray([1.0, 0.0, 1.0], dtype=float)
        normal = normal / np.linalg.norm(normal)
        add_result(
            collection,
            StoredSectionResult(
                id="section-a",
                name="Rotated Section",
                plane_id="plane-a",
                axis="Z",
                offset=0.0,
                visible=True,
                result=SectionResult(
                    axis="Z",
                    offset=0.0,
                    polylines=tuple(),
                    segment_count=0,
                    plane_origin=np.asarray([0.0, 0.0, 0.0], dtype=float),
                    plane_normal=normal,
                    is_arbitrary_plane=True,
                ),
                plane_origin=np.asarray([0.0, 0.0, 0.0], dtype=float),
                plane_normal=normal,
                is_arbitrary_plane=True,
            ),
        )

        project = project_from_app_state(
            mesh_object=None,
            proxy_quality="Medium",
            show_grid=True,
            show_axes=True,
            show_normals=False,
            section_axis="Z",
            section_offset=0.0,
            show_section_plane=False,
            section_collection=collection,
        )

        result = project.section_results[0]
        self.assertEqual(result.plane_origin, [0.0, 0.0, 0.0])
        self.assertTrue(np.allclose(result.plane_normal, normal))
        self.assertTrue(result.is_arbitrary_plane)

    def test_project_from_app_state_exports_all_stored_curves(self) -> None:
        curve_collection = CurveCollection()
        add_curve(
            curve_collection,
            StoredCurve(
                id="curve-a",
                name="Section 1 Curve 1",
                section_result_id="section-a",
                plane_id="plane-a",
                original_points=np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
                fitted_points=np.asarray(
                    [[0.0, 0.0, 0.0], [0.5, 0.25, 0.0], [1.0, 0.0, 0.0]]
                ),
                mean_error=0.05,
                max_error=0.1,
                is_closed=False,
                visible=True,
                metadata={"repair_type": "join", "source_curve_ids": ["old-a"]},
            ),
        )
        add_curve(
            curve_collection,
            StoredCurve(
                id="curve-b",
                name="Section 2 Curve 1",
                section_result_id="section-b",
                plane_id="plane-b",
                original_points=np.asarray([[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]]),
                fitted_points=np.asarray([[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]]),
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
                visible=False,
            ),
        )

        project = project_from_app_state(
            mesh_object=None,
            proxy_quality="Medium",
            show_grid=True,
            show_axes=True,
            show_normals=False,
            section_axis="Z",
            section_offset=0.0,
            show_section_plane=False,
            curve_collection=curve_collection,
        )

        self.assertEqual(len(project.curves), 2)
        self.assertEqual(project.curves[0].id, "curve-a")
        self.assertEqual(project.curves[0].original_points, [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
        self.assertEqual(
            project.curves[0].fitted_points,
            [[0.0, 0.0, 0.0], [0.5, 0.25, 0.0], [1.0, 0.0, 0.0]],
        )
        self.assertEqual(project.curves[0].point_count, 3)
        self.assertAlmostEqual(project.curves[0].length, 1.118033988749895)
        self.assertEqual(project.curves[0].endpoint_distance, 1.0)
        self.assertEqual(project.curves[0].bounding_box_size, 1.0)
        self.assertFalse(project.curves[0].is_tiny_fragment)
        self.assertEqual(project.curves[0].source_section_result_id, "section-a")
        self.assertEqual(project.curves[0].source_plane_id, "plane-a")
        self.assertEqual(
            project.curves[0].metadata,
            {"repair_type": "join", "source_curve_ids": ["old-a"]},
        )
        self.assertTrue(project.curves[0].visible)
        self.assertEqual(project.curves[1].id, "curve-b")
        self.assertFalse(project.curves[1].visible)

    def test_project_from_app_state_exports_manual_curve_metadata(self) -> None:
        curve_collection = CurveCollection()
        points = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
            ],
            dtype=float,
        )
        add_curve(
            curve_collection,
            StoredCurve(
                id="curve-manual",
                name="Manual Curve 1",
                section_result_id="",
                plane_id="plane-a",
                original_points=points.copy(),
                fitted_points=points.copy(),
                mean_error=0.0,
                max_error=0.0,
                is_closed=True,
                visible=True,
                selected=True,
                metadata={
                    "creation_type": "manual",
                    "work_plane_type": "section_plane",
                    "source_section_plane_id": "plane-a",
                    "closed": True,
                },
            ),
        )

        project = project_from_app_state(
            mesh_object=None,
            proxy_quality="Medium",
            show_grid=True,
            show_axes=True,
            show_normals=False,
            section_axis="Z",
            section_offset=0.0,
            show_section_plane=False,
            curve_collection=curve_collection,
        )

        self.assertEqual(len(project.curves), 1)
        curve = project.curves[0]
        self.assertEqual(curve.name, "Manual Curve 1")
        self.assertEqual(curve.section_result_id, "")
        self.assertEqual(curve.plane_id, "plane-a")
        self.assertEqual(curve.mean_error, 0.0)
        self.assertEqual(curve.max_error, 0.0)
        self.assertTrue(curve.is_closed)
        self.assertEqual(
            curve.metadata,
            {
                "creation_type": "manual",
                "work_plane_type": "section_plane",
                "source_section_plane_id": "plane-a",
                "closed": True,
                "control_points": points.tolist(),
                "curve_method": "polyline",
                "sample_count": DEFAULT_MANUAL_CURVE_SAMPLE_COUNT,
                "snap_to_mesh": False,
            },
        )

    def test_project_from_app_state_exports_all_stored_surfaces(self) -> None:
        surface_collection = SurfaceCollection()
        add_surface(
            surface_collection,
            SurfacePatch(
                id="surface-a",
                name="Surface 1",
                source_curve_ids=["curve-a", "curve-b"],
                surface_type="placeholder",
                visible=True,
                metadata={
                    "curve_count": 2,
                    "source": "visible_curves",
                    "note": "Placeholder surface; no geometry generated yet",
                },
            ),
        )
        add_surface(
            surface_collection,
            SurfacePatch(
                id="surface-b",
                name="Hidden Surface",
                source_curve_ids=["curve-b"],
                surface_type="placeholder",
                visible=False,
                metadata={"curve_count": 1, "source": "selected_curve"},
            ),
        )

        project = project_from_app_state(
            mesh_object=None,
            proxy_quality="Medium",
            show_grid=True,
            show_axes=True,
            show_normals=False,
            section_axis="Z",
            section_offset=0.0,
            show_section_plane=False,
            surface_collection=surface_collection,
        )

        self.assertEqual(len(project.surfaces), 2)
        self.assertEqual(project.surfaces[0].id, "surface-a")
        self.assertEqual(project.surfaces[0].source_curve_ids, ["curve-a", "curve-b"])
        self.assertTrue(project.surfaces[0].visible)
        self.assertEqual(project.surfaces[0].metadata["curve_count"], 2)
        self.assertEqual(project.surfaces[1].id, "surface-b")
        self.assertFalse(project.surfaces[1].visible)

    def test_project_from_app_state_handles_mesh_without_file_path(self) -> None:
        mesh_object = SimpleNamespace(
            file_path=None,
            location=[4.0, 5.0, 6.0],
            rotation=(40.0, 50.0, 60.0),
            scale=1.5,
            origin=[1.0, 2.0, 3.0],
        )

        project = project_from_app_state(
            mesh_object=mesh_object,
            proxy_quality="Medium",
            show_grid=True,
            show_axes=True,
            show_normals=False,
            section_axis="X",
            section_offset=0.0,
            show_section_plane=False,
        )

        self.assertIsNone(project.mesh_path)
        self.assertEqual(project.transform.location, [4.0, 5.0, 6.0])
        self.assertEqual(project.transform.rotation, [40.0, 50.0, 60.0])
        self.assertEqual(project.transform.scale, 1.5)
        self.assertEqual(project.transform.origin, [1.0, 2.0, 3.0])

    def test_project_from_app_state_rejects_invalid_mesh_shape(self) -> None:
        mesh_object = SimpleNamespace(
            file_path=Path("broken.stl"),
            location=[1.0, 2.0],
            rotation=[0.0, 0.0, 0.0],
            scale=1.0,
            origin=[0.0, 0.0, 0.0],
        )

        with self.assertRaises(ValueError) as context:
            project_from_app_state(
                mesh_object=mesh_object,
                proxy_quality="Medium",
                show_grid=True,
                show_axes=True,
                show_normals=False,
                section_axis="Z",
                section_offset=0.0,
                show_section_plane=False,
            )

        self.assertIn("mesh_object.location", str(context.exception))


if __name__ == "__main__":
    unittest.main()
