from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from project.project_data import (
    PROJECT_VERSION,
    ProjectData,
    ProjectDisplaySettings,
    ProjectSectionSettings,
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
            },
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
        ]

        for shape in invalid_shapes:
            with self.subTest(shape=shape):
                with self.assertRaises(ValueError) as context:
                    project_from_dict(shape)  # type: ignore[arg-type]
                self.assertTrue(str(context.exception))


if __name__ == "__main__":
    unittest.main()
