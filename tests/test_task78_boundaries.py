from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from bootstrap import create_application
from application.scene_ids import region_node_id
from application.state import AppState
from infrastructure.io_services import ProgressEvent, ProjectFileService
from infrastructure.persistence import JsonProjectRepository
from infrastructure.settings_repository import JsonSettingsRepository
from project.project_data import ProjectRegion, default_project_data
from project.project_session import restore_project_state
from project.project_state import project_from_app_state
from regions.region_state import RegionCollection, RegionSelection
from settings.settings_data import default_app_settings


class Task78ProjectBoundaryTests(unittest.TestCase):
    def test_current_and_unknown_project_data_round_trip_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.openretop"
            payload = {
                "version": 1,
                "name": "Sample",
                "mesh_path": "scan.stl",
                "future_extension": {"keep": [1, 2, 3]},
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            repository = JsonProjectRepository()
            loaded = repository.read(path)
            self.assertTrue(loaded.success)
            self.assertEqual(loaded.resolved_mesh_path, (path.parent / "scan.stl").resolve())
            self.assertEqual(loaded.project.metadata["future_extension"], {"keep": [1, 2, 3]})

            saved = repository.write(loaded.project, path)
            self.assertTrue(saved.success)
            first = path.read_text(encoding="utf-8")
            repository.write(loaded.project, path)
            self.assertEqual(first, path.read_text(encoding="utf-8"))
            self.assertIn("future_extension", first)

    def test_legacy_project_without_version_migrates_in_memory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.openretop"
            path.write_text(json.dumps({"name": "Legacy"}), encoding="utf-8")
            result = JsonProjectRepository().read(path)
            self.assertTrue(result.success)
            self.assertTrue(result.migrated)
            self.assertEqual(result.project.name, "Legacy")
            self.assertTrue(any(item.code == "legacy_project_version" for item in result.warnings))

    def test_missing_mesh_is_recoverable_warning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.openretop"
            path.write_text(json.dumps({"mesh_path": "not-there.stl"}), encoding="utf-8")
            result = JsonProjectRepository().read(path)
            self.assertTrue(result.success)
            self.assertTrue(any(item.code == "missing_mesh" for item in result.warnings))

    def test_region_and_scene_selection_round_trip_and_restore(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "selection.openretop"
            project = default_project_data()
            project.region = ProjectRegion(
                id="region-a",
                name="Region A",
                triangle_indices=[2, 4, 8],
                threshold_degrees=32.0,
                max_triangle_count=500,
                seed_triangle_index=2,
                visible=False,
                selected=True,
                metadata={"source": "test"},
            )
            project.selected_scene_ids = [region_node_id("region-a")]
            project.primary_selection_id = region_node_id("region-a")

            repository = JsonProjectRepository()
            self.assertTrue(repository.write(project, path).success)
            opened = repository.read(path)
            self.assertTrue(opened.success)
            self.assertEqual(opened.project.region.triangle_indices, [2, 4, 8])
            self.assertEqual(opened.project.selected_scene_ids, [region_node_id("region-a")])

            state = AppState()
            restored = restore_project_state(state, opened.project)
            self.assertEqual(state.region_collection.active_region.name, "Region A")
            self.assertFalse(state.region_collection.active_region.visible)
            self.assertEqual(restored.primary_selection_id, region_node_id("region-a"))

    def test_project_snapshot_includes_region_and_deduplicated_selection(self) -> None:
        region = RegionSelection(
            id="region-a",
            name="Region A",
            triangle_indices=(0, 1),
            threshold_degrees=20.0,
            max_triangle_count=100,
            selected=True,
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
            region_collection=RegionCollection(active_region=region),
            selected_scene_ids=(region_node_id("region-a"), region_node_id("region-a")),
            primary_selection_id=region_node_id("region-a"),
        )

        self.assertEqual(project.region.id, "region-a")
        self.assertEqual(project.region.triangle_indices, [0, 1])
        self.assertEqual(project.selected_scene_ids, [region_node_id("region-a")])


class Task78SettingsBoundaryTests(unittest.TestCase):
    def test_settings_repository_recovers_invalid_json_with_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("{broken", encoding="utf-8")
            result = JsonSettingsRepository().read(path)
            self.assertFalse(result.success)
            self.assertEqual(result.settings, default_app_settings())
            self.assertTrue(result.errors)

    def test_settings_round_trip_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            repository = JsonSettingsRepository()
            repository.write(default_app_settings(), path)
            first = path.read_text(encoding="utf-8")
            repository.write(default_app_settings(), path)
            self.assertEqual(first, path.read_text(encoding="utf-8"))


class Task78ServiceAndBootstrapTests(unittest.TestCase):
    def test_project_service_emits_progress_without_dialogs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.openretop"
            events: list[ProgressEvent] = []
            service = ProjectFileService()
            result = service.save_project(default_project_data(), path, progress=events.append)
            self.assertTrue(result.success)
            opened = service.open_project(path, progress=events.append)
            self.assertTrue(opened.success)
            self.assertEqual([event.operation for event in events], ["project_save", "project_save", "project_open", "project_open"])

    def test_composition_root_builds_isolated_testable_graph(self) -> None:
        first = create_application()
        second = create_application()
        self.assertIsNot(first.state, second.state)
        self.assertIsNot(first.mesh_query_service, second.mesh_query_service)
        self.assertIs(first.dependencies.events, first.events)
        self.assertTrue(hasattr(first, "scene_builder"))
        self.assertTrue(hasattr(first.cad, "capabilities"))


if __name__ == "__main__":
    unittest.main()
