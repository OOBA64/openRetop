from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from bootstrap import create_application
from infrastructure.io_services import ProgressEvent, ProjectFileService
from infrastructure.persistence import JsonProjectRepository
from infrastructure.settings_repository import JsonSettingsRepository
from project.project_data import default_project_data
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
