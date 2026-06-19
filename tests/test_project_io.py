from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from project.project_data import (
    PROJECT_VERSION,
    ProjectCurve,
    ProjectData,
    ProjectDisplaySettings,
    ProjectSectionPlane,
    ProjectSectionResult,
    ProjectSectionSettings,
    ProjectSurface,
    ProjectTransform,
    default_project_data,
)
from project.project_io import (
    load_project,
    project_from_dict,
    project_to_dict,
    save_project,
)


def _sample_project() -> ProjectData:
    return ProjectData(
        version=PROJECT_VERSION,
        name="Scan Cleanup",
        mesh_path="models/scan.stl",
        mesh_name="Scan Object",
        mesh_visible=False,
        transform=ProjectTransform(
            location=[1.0, 2.0, 3.0],
            rotation=[10.0, 20.0, 30.0],
            scale=1.25,
            origin=[0.5, 0.25, 0.0],
        ),
        display=ProjectDisplaySettings(
            proxy_quality="High",
            show_grid=False,
            show_axes=True,
            show_normals=True,
        ),
        section=ProjectSectionSettings(
            axis="Y",
            offset=0.75,
            show_plane=True,
        ),
        section_planes=[
            ProjectSectionPlane(
                id="plane-a",
                name="Base Section",
                axis="Y",
                offset=0.75,
                visible=True,
            ),
            ProjectSectionPlane(
                id="plane-b",
                name="Side Section",
                axis="X",
                offset=-0.25,
                visible=False,
            ),
        ],
        active_section_plane_id="plane-b",
        section_results=[
            ProjectSectionResult(
                id="section-a",
                name="Renamed Section",
                plane_id="plane-a",
                axis="Y",
                offset=0.75,
                visible=True,
                polylines=[[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]],
                segment_count=1,
            ),
        ],
        curves=[
            ProjectCurve(
                id="curve-a",
                name="Section 1 Curve 1",
                section_result_id="section-a",
                plane_id="plane-a",
                original_points=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                fitted_points=[[0.0, 0.0, 0.0], [0.5, 0.25, 0.0], [1.0, 0.0, 0.0]],
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
        ],
        surfaces=[
            ProjectSurface(
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
            ProjectSurface(
                id="surface-b",
                name="Hidden Surface",
                source_curve_ids=["curve-b"],
                surface_type="placeholder",
                visible=False,
                metadata={"curve_count": 1, "source": "selected_curve"},
            ),
        ],
    )


class ProjectDataTests(unittest.TestCase):
    def test_default_project_data_returns_valid_defaults(self) -> None:
        project = default_project_data()

        self.assertEqual(project.version, PROJECT_VERSION)
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
        self.assertEqual(project.section_planes, [])
        self.assertIsNone(project.active_section_plane_id)
        self.assertEqual(project.curves, [])
        self.assertEqual(project.surfaces, [])

    def test_default_project_data_uses_fresh_mutable_values(self) -> None:
        project = default_project_data()
        other_project = default_project_data()

        project.transform.location[0] = 99.0
        project.transform.rotation[0] = 45.0
        project.transform.origin[0] = 12.0

        self.assertEqual(other_project.transform.location, [0.0, 0.0, 0.0])
        self.assertEqual(other_project.transform.rotation, [0.0, 0.0, 0.0])
        self.assertEqual(other_project.transform.origin, [0.0, 0.0, 0.0])


class ProjectIOTests(unittest.TestCase):
    def test_project_to_dict_preserves_all_fields(self) -> None:
        project = _sample_project()

        self.assertEqual(
            project_to_dict(project),
            {
                "version": PROJECT_VERSION,
                "name": "Scan Cleanup",
                "mesh_path": "models/scan.stl",
                "mesh_name": "Scan Object",
                "mesh_visible": False,
                "transform": {
                    "location": [1.0, 2.0, 3.0],
                    "rotation": [10.0, 20.0, 30.0],
                    "scale": 1.25,
                    "origin": [0.5, 0.25, 0.0],
                },
                "display": {
                    "proxy_quality": "High",
                    "show_grid": False,
                    "show_axes": True,
                    "show_normals": True,
                },
                "section": {
                    "axis": "Y",
                    "offset": 0.75,
                    "show_plane": True,
                },
                "section_planes": [
                    {
                        "id": "plane-a",
                        "name": "Base Section",
                        "axis": "Y",
                        "offset": 0.75,
                        "visible": True,
                        "origin": [0.0, 0.75, 0.0],
                        "normal": [0.0, 1.0, 0.0],
                    },
                    {
                        "id": "plane-b",
                        "name": "Side Section",
                        "axis": "X",
                        "offset": -0.25,
                        "visible": False,
                        "origin": [-0.25, 0.0, 0.0],
                        "normal": [1.0, 0.0, 0.0],
                    },
                ],
                "active_section_plane_id": "plane-b",
                "section_results": [
                    {
                        "id": "section-a",
                        "name": "Renamed Section",
                        "plane_id": "plane-a",
                        "axis": "Y",
                        "offset": 0.75,
                        "visible": True,
                        "plane_origin": [0.0, 0.75, 0.0],
                        "plane_normal": [0.0, 1.0, 0.0],
                        "is_arbitrary_plane": False,
                        "polylines": [
                            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                        ],
                        "segment_count": 1,
                    },
                ],
                "curves": [
                    {
                        "id": "curve-a",
                        "name": "Section 1 Curve 1",
                        "section_result_id": "section-a",
                        "plane_id": "plane-a",
                        "original_points": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                        "fitted_points": [
                            [0.0, 0.0, 0.0],
                            [0.5, 0.25, 0.0],
                            [1.0, 0.0, 0.0],
                        ],
                        "mean_error": 0.05,
                        "max_error": 0.1,
                        "is_closed": False,
                        "visible": True,
                        "point_count": 3,
                        "length": 1.118033988749895,
                        "endpoint_distance": 1.0,
                        "bounding_box_size": 1.0,
                        "is_tiny_fragment": False,
                        "source_section_result_id": "section-a",
                        "source_plane_id": "plane-a",
                        "metadata": {},
                    },
                    {
                        "id": "curve-b",
                        "name": "Section 2 Curve 1",
                        "section_result_id": "section-b",
                        "plane_id": "plane-b",
                        "original_points": [[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]],
                        "fitted_points": [[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]],
                        "mean_error": 0.0,
                        "max_error": 0.0,
                        "is_closed": False,
                        "visible": False,
                        "point_count": 2,
                        "length": 1.0,
                        "endpoint_distance": 1.0,
                        "bounding_box_size": 1.0,
                        "is_tiny_fragment": False,
                        "source_section_result_id": "section-b",
                        "source_plane_id": "plane-b",
                        "metadata": {},
                    },
                ],
                "surfaces": [
                    {
                        "id": "surface-a",
                        "name": "Surface 1",
                        "source_curve_ids": ["curve-a", "curve-b"],
                        "surface_type": "placeholder",
                        "visible": True,
                        "metadata": {
                            "curve_count": 2,
                            "source": "visible_curves",
                            "note": "Placeholder surface; no geometry generated yet",
                        },
                    },
                    {
                        "id": "surface-b",
                        "name": "Hidden Surface",
                        "source_curve_ids": ["curve-b"],
                        "surface_type": "placeholder",
                        "visible": False,
                        "metadata": {
                            "curve_count": 1,
                            "source": "selected_curve",
                        },
                    },
                ],
            },
        )

    def test_project_to_dict_converts_numpy_curve_points(self) -> None:
        project = default_project_data()
        project.curves = [
            ProjectCurve(
                id="curve-a",
                name="Curve A",
                section_result_id="section-a",
                plane_id="plane-a",
                original_points=np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),  # type: ignore[arg-type]
                fitted_points=np.asarray([[0.0, 0.0, 0.0], [1.0, 0.5, 0.0]]),  # type: ignore[arg-type]
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
                visible=True,
            ),
        ]

        data = project_to_dict(project)

        self.assertEqual(
            data["curves"],
            [
                {
                    "id": "curve-a",
                    "name": "Curve A",
                    "section_result_id": "section-a",
                    "plane_id": "plane-a",
                    "original_points": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                    "fitted_points": [[0.0, 0.0, 0.0], [1.0, 0.5, 0.0]],
                    "mean_error": 0.0,
                    "max_error": 0.0,
                    "is_closed": False,
                    "visible": True,
                    "point_count": 2,
                    "length": 1.118033988749895,
                    "endpoint_distance": 1.118033988749895,
                    "bounding_box_size": 1.0,
                    "is_tiny_fragment": False,
                    "source_section_result_id": "section-a",
                    "source_plane_id": "plane-a",
                    "metadata": {},
                },
            ],
        )

    def test_project_from_dict_round_trips_to_project_data(self) -> None:
        project = _sample_project()

        self.assertEqual(project_from_dict(project_to_dict(project)), project)

    def test_project_from_dict_uses_defaults_for_missing_optional_fields(self) -> None:
        project = project_from_dict(
            {
                "version": PROJECT_VERSION,
                "name": "Partial",
                "display": {
                    "show_grid": False,
                },
                "section": {
                    "axis": "x",
                },
            }
        )

        self.assertEqual(project.name, "Partial")
        self.assertIsNone(project.mesh_path)
        self.assertIsNone(project.mesh_name)
        self.assertTrue(project.mesh_visible)
        self.assertEqual(project.transform.location, [0.0, 0.0, 0.0])
        self.assertEqual(project.transform.rotation, [0.0, 0.0, 0.0])
        self.assertEqual(project.transform.scale, 1.0)
        self.assertEqual(project.transform.origin, [0.0, 0.0, 0.0])
        self.assertEqual(project.display.proxy_quality, "Medium")
        self.assertFalse(project.display.show_grid)
        self.assertTrue(project.display.show_axes)
        self.assertFalse(project.display.show_normals)
        self.assertEqual(project.section.axis, "X")
        self.assertEqual(project.section.offset, 0.0)
        self.assertFalse(project.section.show_plane)
        self.assertEqual(project.section_planes, [])
        self.assertIsNone(project.active_section_plane_id)
        self.assertEqual(project.section_results, [])
        self.assertEqual(project.curves, [])
        self.assertEqual(project.surfaces, [])

    def test_project_from_dict_preserves_arbitrary_section_result_metadata(self) -> None:
        normal = [0.70710678118, 0.0, 0.70710678118]

        project = project_from_dict(
            {
                "version": PROJECT_VERSION,
                "section_results": [
                    {
                        "id": "section-a",
                        "name": "Rotated Section",
                        "plane_id": "plane-a",
                        "axis": "Z",
                        "offset": 0.0,
                        "visible": True,
                        "plane_origin": [0.0, 0.0, 0.0],
                        "plane_normal": normal,
                        "is_arbitrary_plane": True,
                        "polylines": [
                            [[0.0, 0.0, 0.0], [1.0, 0.0, -1.0]],
                        ],
                        "segment_count": 1,
                    },
                ],
            }
        )

        result = project.section_results[0]
        self.assertEqual(result.plane_origin, [0.0, 0.0, 0.0])
        self.assertEqual(result.plane_normal, normal)
        self.assertTrue(result.is_arbitrary_plane)

        data = project_to_dict(project)

        self.assertEqual(data["section_results"][0]["plane_origin"], [0.0, 0.0, 0.0])
        self.assertEqual(data["section_results"][0]["plane_normal"], normal)
        self.assertTrue(data["section_results"][0]["is_arbitrary_plane"])

    def test_project_from_dict_loads_legacy_single_section_without_new_fields(self) -> None:
        project = project_from_dict(
            {
                "version": PROJECT_VERSION,
                "name": "Legacy",
                "mesh_path": None,
                "section": {
                    "axis": "y",
                    "offset": 1.5,
                    "show_plane": True,
                },
            }
        )

        self.assertEqual(project.section.axis, "Y")
        self.assertEqual(project.section.offset, 1.5)
        self.assertTrue(project.section.show_plane)
        self.assertEqual(project.section_planes, [])
        self.assertIsNone(project.active_section_plane_id)
        self.assertEqual(project.curves, [])
        self.assertEqual(project.surfaces, [])

    def test_project_from_dict_parses_curves(self) -> None:
        project = project_from_dict(
            {
                "version": PROJECT_VERSION,
                "curves": [
                    {
                        "id": "curve-a",
                        "name": "Section 1 Curve 1",
                        "section_result_id": "section-a",
                        "plane_id": "plane-a",
                        "original_points": [[0, 0, 0], [1, 0, 0]],
                        "fitted_points": [[0, 0, 0], [0.5, 0.25, 0], [1, 0, 0]],
                        "mean_error": 0.05,
                        "max_error": 0.1,
                        "is_closed": False,
                        "visible": False,
                    },
                ],
            }
        )

        self.assertEqual(
            project.curves,
            [
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
                    visible=False,
                ),
            ],
        )

    def test_project_from_dict_preserves_repaired_curve_metadata(self) -> None:
        project = project_from_dict(
            {
                "version": PROJECT_VERSION,
                "curves": [
                    {
                        "id": "curve-joined",
                        "name": "Joined Curve 1",
                        "section_result_id": "section-a",
                        "plane_id": "plane-a",
                        "original_points": [[0, 0, 0], [1, 0, 0]],
                        "fitted_points": [[0, 0, 0], [1, 0, 0]],
                        "mean_error": 0.0,
                        "max_error": 0.0,
                        "is_closed": False,
                        "visible": True,
                        "metadata": {
                            "source_curve_ids": ["curve-a", "curve-b"],
                            "repair_type": "join",
                            "tolerance_used": 0.01,
                            "original_endpoint_gap": 0.001,
                        },
                    },
                ],
            }
        )

        curve = project.curves[0]

        self.assertEqual(curve.metadata["repair_type"], "join")
        self.assertEqual(curve.metadata["source_curve_ids"], ["curve-a", "curve-b"])

        data = project_to_dict(project)

        self.assertEqual(
            data["curves"][0]["metadata"],
            {
                "source_curve_ids": ["curve-a", "curve-b"],
                "repair_type": "join",
                "tolerance_used": 0.01,
                "original_endpoint_gap": 0.001,
            },
        )

    def test_save_load_project_preserves_manual_curve_metadata(self) -> None:
        project = default_project_data()
        project.curves = [
            ProjectCurve(
                id="curve-manual",
                name="Manual Curve 1",
                section_result_id="",
                plane_id="plane-a",
                original_points=[
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                    [1.0, 1.0, 0.0],
                ],
                fitted_points=[
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                    [1.0, 1.0, 0.0],
                ],
                mean_error=0.0,
                max_error=0.0,
                is_closed=True,
                visible=True,
                metadata={
                    "creation_type": "manual",
                    "work_plane_type": "section_plane",
                    "source_section_plane_id": "plane-a",
                    "closed": True,
                },
            )
        ]

        with TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir) / "manual.openretop"
            save_project(project, project_path)
            loaded_project = load_project(project_path)

        curve = loaded_project.curves[0]
        self.assertEqual(curve.name, "Manual Curve 1")
        self.assertEqual(curve.section_result_id, "")
        self.assertEqual(curve.plane_id, "plane-a")
        self.assertTrue(curve.is_closed)
        self.assertEqual(
            curve.metadata,
            {
                "creation_type": "manual",
                "work_plane_type": "section_plane",
                "source_section_plane_id": "plane-a",
                "closed": True,
            },
        )

    def test_save_load_project_preserves_snapped_curve_metadata(self) -> None:
        project = default_project_data()
        project.curves = [
            ProjectCurve(
                id="curve-snap",
                name="Manual Curve 1",
                section_result_id="",
                plane_id="",
                original_points=[[0.0, 0.0, 0.2], [1.0, 0.0, 0.4]],
                fitted_points=[[0.0, 0.0, 0.2], [1.0, 0.0, 0.4]],
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
                visible=True,
                metadata={
                    "creation_type": "curve_on_mesh",
                    "snap_mode": "mesh",
                    "source_mesh_name": "sample.stl",
                    "closed": False,
                    "snap_triangle_indices": [4, 9],
                    "snap_normals": [[0.0, 0.0, 1.0], [0.0, 1.0, 0.0]],
                },
            )
        ]

        with TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir) / "snapped.openretop"
            save_project(project, project_path)
            loaded_project = load_project(project_path)

        curve = loaded_project.curves[0]
        self.assertEqual(curve.metadata["creation_type"], "curve_on_mesh")
        self.assertEqual(curve.metadata["snap_mode"], "mesh")
        self.assertEqual(curve.metadata["source_mesh_name"], "sample.stl")
        self.assertEqual(curve.metadata["snap_triangle_indices"], [4, 9])
        self.assertEqual(
            curve.metadata["snap_normals"],
            [[0.0, 0.0, 1.0], [0.0, 1.0, 0.0]],
        )

    def test_save_load_project_preserves_region_boundary_metadata(self) -> None:
        project = default_project_data()
        project.curves = [
            ProjectCurve(
                id="curve-boundary",
                name="Region Boundary 1",
                section_result_id="",
                plane_id="",
                original_points=[
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                    [1.0, 1.0, 0.0],
                    [0.0, 1.0, 0.0],
                ],
                fitted_points=[
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                    [1.0, 1.0, 0.0],
                    [0.0, 1.0, 0.0],
                ],
                mean_error=0.0,
                max_error=0.0,
                is_closed=True,
                visible=True,
                metadata={
                    "creation_type": "region_boundary",
                    "source_region_id": "region-a",
                    "source_region_name": "Region 1",
                    "source_mesh_name": "sample.stl",
                    "source_region_triangle_count": 2,
                    "boundary_point_count": 4,
                    "boundary_closed": True,
                    "boundary_perimeter": 4.0,
                    "boundary_index": 1,
                },
            )
        ]

        with TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir) / "boundary.openretop"
            save_project(project, project_path)
            loaded_project = load_project(project_path)

        curve = loaded_project.curves[0]
        self.assertEqual(curve.metadata["creation_type"], "region_boundary")
        self.assertEqual(curve.metadata["source_region_id"], "region-a")
        self.assertEqual(curve.metadata["source_region_name"], "Region 1")
        self.assertEqual(curve.metadata["source_mesh_name"], "sample.stl")
        self.assertEqual(curve.metadata["source_region_triangle_count"], 2)
        self.assertEqual(curve.metadata["boundary_point_count"], 4)
        self.assertIs(curve.metadata["boundary_closed"], True)
        self.assertEqual(curve.metadata["boundary_perimeter"], 4.0)

    def test_save_load_project_preserves_projected_and_rebuilt_metadata(self) -> None:
        project = default_project_data()
        project.curves = [
            ProjectCurve(
                id="curve-projected",
                name="Projected Curve 1",
                section_result_id="",
                plane_id="",
                original_points=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                fitted_points=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
                visible=True,
                metadata={
                    "creation_type": "projected_curve",
                    "source_curve_id": "curve-boundary",
                    "source_curve_name": "Region Boundary 1",
                    "source_curve_creation_type": "region_boundary",
                    "source_mesh_name": "sample.stl",
                    "source_region_id": "region-a",
                    "source_region_name": "Region 1",
                    "source_region_triangle_count": 2,
                    "projection_projected_count": 2,
                    "projection_missed_count": 0,
                    "projection_mean_distance": 0.125,
                    "projection_max_distance": 0.25,
                    "projection_warnings": [],
                    "control_points": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                    "curve_method": "polyline",
                    "sample_count": 16,
                    "snap_to_mesh": True,
                    "snap_mode": "mesh",
                },
            ),
            ProjectCurve(
                id="curve-rebuilt",
                name="Rebuilt Curve 1",
                section_result_id="",
                plane_id="",
                original_points=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                fitted_points=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
                visible=True,
                metadata={
                    "creation_type": "rebuilt_curve",
                    "source_curve_id": "curve-projected",
                    "source_curve_name": "Projected Curve 1",
                    "source_curve_creation_type": "projected_curve",
                    "source_mesh_name": "sample.stl",
                    "projection_projected_count": 2,
                    "projection_missed_count": 0,
                    "projection_mean_distance": 0.125,
                    "projection_max_distance": 0.25,
                    "rebuild_source_point_count": 32,
                    "rebuild_target_control_point_count": 2,
                    "rebuild_method": "catmull_rom",
                    "rebuild_warnings": [],
                    "control_points": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                    "curve_method": "catmull_rom",
                    "sample_count": 64,
                },
            ),
        ]

        with TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir) / "derived-curves.openretop"
            save_project(project, project_path)
            loaded_project = load_project(project_path)

        projected_metadata = loaded_project.curves[0].metadata
        self.assertEqual(projected_metadata["creation_type"], "projected_curve")
        self.assertEqual(projected_metadata["source_curve_id"], "curve-boundary")
        self.assertEqual(projected_metadata["source_curve_creation_type"], "region_boundary")
        self.assertEqual(projected_metadata["source_mesh_name"], "sample.stl")
        self.assertEqual(projected_metadata["source_region_id"], "region-a")
        self.assertEqual(projected_metadata["source_region_name"], "Region 1")
        self.assertEqual(projected_metadata["source_region_triangle_count"], 2)
        self.assertEqual(projected_metadata["projection_projected_count"], 2)
        self.assertEqual(projected_metadata["projection_missed_count"], 0)
        self.assertEqual(projected_metadata["projection_mean_distance"], 0.125)
        self.assertEqual(projected_metadata["projection_max_distance"], 0.25)
        self.assertEqual(projected_metadata["control_points"], [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
        self.assertEqual(projected_metadata["curve_method"], "polyline")
        self.assertEqual(projected_metadata["sample_count"], 16)

        rebuilt_metadata = loaded_project.curves[1].metadata
        self.assertEqual(rebuilt_metadata["creation_type"], "rebuilt_curve")
        self.assertEqual(rebuilt_metadata["source_curve_id"], "curve-projected")
        self.assertEqual(rebuilt_metadata["source_curve_creation_type"], "projected_curve")
        self.assertEqual(rebuilt_metadata["source_mesh_name"], "sample.stl")
        self.assertEqual(rebuilt_metadata["projection_mean_distance"], 0.125)
        self.assertEqual(rebuilt_metadata["projection_max_distance"], 0.25)
        self.assertEqual(rebuilt_metadata["rebuild_source_point_count"], 32)
        self.assertEqual(rebuilt_metadata["rebuild_target_control_point_count"], 2)
        self.assertEqual(rebuilt_metadata["rebuild_method"], "catmull_rom")
        self.assertEqual(rebuilt_metadata["control_points"], [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
        self.assertEqual(rebuilt_metadata["curve_method"], "catmull_rom")
        self.assertEqual(rebuilt_metadata["sample_count"], 64)

    def test_project_from_dict_rejects_invalid_curve_points_clearly(self) -> None:
        with self.assertRaises(ValueError) as context:
            project_from_dict(
                {
                    "version": PROJECT_VERSION,
                    "curves": [
                        {
                            "id": "curve-a",
                            "name": "Broken Curve",
                            "section_result_id": "section-a",
                            "plane_id": "plane-a",
                            "original_points": [[0.0, 0.0]],
                            "fitted_points": [[0.0, 0.0, 0.0]],
                            "mean_error": 0.0,
                            "max_error": 0.0,
                            "is_closed": False,
                            "visible": True,
                        },
                    ],
                }
            )

        self.assertIn("curves[0].original_points[0]", str(context.exception))

    def test_project_from_dict_parses_surfaces(self) -> None:
        project = project_from_dict(
            {
                "version": PROJECT_VERSION,
                "surfaces": [
                    {
                        "id": "surface-a",
                        "name": "Surface 1",
                        "source_curve_ids": ["curve-a", "curve-b"],
                        "surface_type": "placeholder",
                        "visible": False,
                        "metadata": {
                            "curve_count": 2,
                            "source": "visible_curves",
                            "tags": ["draft", "runtime"],
                        },
                    },
                ],
            }
        )

        self.assertEqual(
            project.surfaces,
            [
                ProjectSurface(
                    id="surface-a",
                    name="Surface 1",
                    source_curve_ids=["curve-a", "curve-b"],
                    surface_type="placeholder",
                    visible=False,
                    metadata={
                        "curve_count": 2,
                        "source": "visible_curves",
                        "tags": ["draft", "runtime"],
                    },
                ),
            ],
        )

    def test_save_load_project_preserves_patch_surface_metadata(self) -> None:
        project = default_project_data()
        project.surfaces = [
            ProjectSurface(
                id="surface-patch",
                name="Four-Curve Patch 1",
                source_curve_ids=["bottom", "right", "top", "left"],
                surface_type="preview_four_curve_patch",
                visible=True,
                metadata={
                    "preview_mode": "four_curve_patch",
                    "source_curve_count": 4,
                    "source_curve_ids": ["bottom", "right", "top", "left"],
                    "source_curve_names": ["Bottom", "Right", "Top", "Left"],
                    "source_curve_creation_types": [
                        "rebuilt_curve",
                        "rebuilt_curve",
                        "rebuilt_curve",
                        "rebuilt_curve",
                    ],
                    "source_curve_tags": ["rebuilt", "smooth"],
                    "source_region_ids": ["region-a"],
                    "source_mesh_names": ["scan.stl"],
                    "preview_available": True,
                    "preview_reason": "four-curve patch preview generated",
                    "preview_warning": "Curve order inferred from scene order; inspect patch.",
                    "source_curve_validation_warnings": [
                        "Curve order inferred from scene order; inspect patch.",
                    ],
                    "source_curve_validation_errors": [],
                    "curve_order": ["bottom", "right", "top", "left"],
                    "grid_u_count": 8,
                    "grid_v_count": 6,
                    "average_corner_gap": 0.01,
                    "max_corner_gap": 0.02,
                },
            )
        ]

        with TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir) / "patch-surface.openretop"
            save_project(project, project_path)
            loaded_project = load_project(project_path)

        metadata = loaded_project.surfaces[0].metadata
        self.assertEqual(metadata["preview_mode"], "four_curve_patch")
        self.assertEqual(metadata["source_curve_ids"], ["bottom", "right", "top", "left"])
        self.assertEqual(metadata["source_curve_tags"], ["rebuilt", "smooth"])
        self.assertEqual(metadata["source_region_ids"], ["region-a"])
        self.assertEqual(metadata["source_mesh_names"], ["scan.stl"])
        self.assertEqual(metadata["preview_available"], True)
        self.assertEqual(metadata["grid_u_count"], 8)
        self.assertEqual(metadata["grid_v_count"], 6)
        self.assertEqual(metadata["curve_order"], ["bottom", "right", "top", "left"])

    def test_project_from_dict_rejects_invalid_surface_shape_clearly(self) -> None:
        with self.assertRaises(ValueError) as context:
            project_from_dict(
                {
                    "version": PROJECT_VERSION,
                    "surfaces": [
                        {
                            "id": "surface-a",
                            "name": "Surface 1",
                            "source_curve_ids": [12],
                            "surface_type": "placeholder",
                            "visible": True,
                            "metadata": {},
                        },
                    ],
                }
            )

        self.assertIn("surfaces[0].source_curve_ids[0]", str(context.exception))

    def test_project_from_dict_parses_section_planes_with_defaults(self) -> None:
        project = project_from_dict(
            {
                "version": PROJECT_VERSION,
                "section": {
                    "axis": "x",
                    "offset": 0.25,
                    "show_plane": True,
                },
                "section_planes": [
                    {
                        "id": "plane-a",
                    },
                    {
                        "id": "plane-b",
                        "name": "Custom Plane",
                        "axis": "z",
                        "offset": -0.5,
                        "visible": False,
                    },
                ],
                "active_section_plane_id": "plane-b",
            }
        )

        self.assertEqual(
            project.section_planes,
            [
                ProjectSectionPlane(
                    id="plane-a",
                    name="Section Plane 1",
                    axis="X",
                    offset=0.25,
                    visible=True,
                    origin=[0.25, 0.0, 0.0],
                    normal=[1.0, 0.0, 0.0],
                ),
                ProjectSectionPlane(
                    id="plane-b",
                    name="Custom Plane",
                    axis="Z",
                    offset=-0.5,
                    visible=False,
                    origin=[0.0, 0.0, -0.5],
                    normal=[0.0, 0.0, 1.0],
                ),
            ],
        )
        self.assertEqual(project.active_section_plane_id, "plane-b")

    def test_project_from_dict_round_trips_rotated_section_plane_orientation(self) -> None:
        project = project_from_dict(
            {
                "version": PROJECT_VERSION,
                "section_planes": [
                    {
                        "id": "plane-a",
                        "name": "Rotated Plane",
                        "axis": "Z",
                        "offset": 0.5,
                        "visible": True,
                        "origin": [0.5, 0.0, 0.0],
                        "normal": [0.70710678, 0.0, 0.70710678],
                    },
                ],
            }
        )

        self.assertEqual(project.section_planes[0].origin, [0.5, 0.0, 0.0])
        self.assertEqual(project.section_planes[0].normal, [0.70710678, 0.0, 0.70710678])
        self.assertEqual(project_from_dict(project_to_dict(project)), project)

    def test_save_and_load_project_round_trips_json(self) -> None:
        project = _sample_project()

        with TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir) / "sample.openretop"

            save_project(project, project_path)

            text = project_path.read_text(encoding="utf-8")
            raw_data = json.loads(text)
            self.assertTrue(text.startswith("{\n"))
            self.assertIn('\n  "version": 1,', text)
            self.assertEqual(raw_data["name"], "Scan Cleanup")
            self.assertEqual(load_project(project_path), project)

    def test_save_and_load_accept_non_openretop_extension_for_now(self) -> None:
        project = _sample_project()

        with TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir) / "sample.json"

            save_project(project, project_path)

            self.assertEqual(load_project(project_path), project)

    def test_load_project_invalid_json_raises_value_error(self) -> None:
        with TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir) / "broken.openretop"
            project_path.write_text("{broken json", encoding="utf-8")

            with self.assertRaises(ValueError) as context:
                load_project(project_path)

        self.assertIn("Invalid project JSON", str(context.exception))

    def test_load_project_missing_file_raises_file_not_found_error(self) -> None:
        with TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir) / "missing.openretop"

            with self.assertRaises(FileNotFoundError):
                load_project(project_path)

    def test_project_to_dict_rejects_non_project_data(self) -> None:
        with self.assertRaises(ValueError) as context:
            project_to_dict(object())  # type: ignore[arg-type]

        self.assertIn("Expected ProjectData", str(context.exception))

    def test_project_from_dict_rejects_invalid_project_shapes(self) -> None:
        invalid_shapes: list[object] = [
            [],
            {"version": False},
            {"version": PROJECT_VERSION + 1},
            {"name": 12},
            {"mesh_path": 12},
            {"transform": []},
            {"transform": {"location": [1.0, 2.0]}},
            {"transform": {"rotation": [1.0, "bad", 3.0]}},
            {"transform": {"scale": 0.0}},
            {"display": []},
            {"display": {"show_grid": 1}},
            {"section": []},
            {"section": {"axis": "A"}},
            {"section": {"offset": False}},
            {"section": {"show_plane": "yes"}},
            {"section_planes": {}},
            {"section_planes": [12]},
            {"section_planes": [{"id": ""}]},
            {"section_planes": [{"id": "plane-a", "name": 12}]},
            {"section_planes": [{"id": "plane-a", "axis": "A"}]},
            {"section_planes": [{"id": "plane-a", "offset": False}]},
            {"section_planes": [{"id": "plane-a", "visible": "yes"}]},
            {"section_planes": [{"id": "plane-a", "origin": [1.0, 2.0]}]},
            {"section_planes": [{"id": "plane-a", "normal": [1.0, "bad", 0.0]}]},
            {"section_planes": [{"id": "plane-a"}, {"id": "plane-a"}]},
            {"active_section_plane_id": 12},
            {"curves": {}},
            {"curves": [12]},
            {"curves": [{"id": ""}]},
            {"curves": [{"id": "curve-a", "name": 12}]},
            {"curves": [{"id": "curve-a", "section_result_id": 12}]},
            {"curves": [{"id": "curve-a", "plane_id": 12}]},
            {"curves": [{"id": "curve-a", "original_points": {}}]},
            {"curves": [{"id": "curve-a", "fitted_points": [[0.0, "bad", 0.0]]}]},
            {"curves": [{"id": "curve-a", "mean_error": False}]},
            {"curves": [{"id": "curve-a", "max_error": False}]},
            {"curves": [{"id": "curve-a", "is_closed": "no"}]},
            {"curves": [{"id": "curve-a", "visible": "yes"}]},
            {"curves": [{"id": "curve-a"}, {"id": "curve-a"}]},
            {"surfaces": {}},
            {"surfaces": [12]},
            {"surfaces": [{"id": ""}]},
            {"surfaces": [{"id": "surface-a", "name": 12}]},
            {"surfaces": [{"id": "surface-a", "source_curve_ids": {}}]},
            {"surfaces": [{"id": "surface-a", "source_curve_ids": [12]}]},
            {"surfaces": [{"id": "surface-a", "surface_type": 12}]},
            {"surfaces": [{"id": "surface-a", "visible": "yes"}]},
            {"surfaces": [{"id": "surface-a", "metadata": []}]},
            {"surfaces": [{"id": "surface-a", "metadata": {"bad": object()}}]},
            {"surfaces": [{"id": "surface-a"}, {"id": "surface-a"}]},
        ]

        for shape in invalid_shapes:
            with self.subTest(shape=shape):
                with self.assertRaises(ValueError) as context:
                    project_from_dict(shape)  # type: ignore[arg-type]
                self.assertTrue(str(context.exception))


if __name__ == "__main__":
    unittest.main()
