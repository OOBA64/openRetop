from __future__ import annotations

import unittest
from pathlib import Path

from openretop.application.state import AppState
from openretop.bootstrap import create_application
from openretop.infrastructure.persistence import JsonProjectRepository
from openretop.project.project_session import restore_project_state

ROOT = Path(__file__).resolve().parents[1]


class ReleaseCandidateTests(unittest.TestCase):
    def test_legacy_and_v3_fixtures_load_without_data_loss(self) -> None:
        repository = JsonProjectRepository()
        legacy = repository.read(ROOT / "tests" / "fixtures" / "legacy_minimal.openretop")
        current = repository.read(ROOT / "tests" / "fixtures" / "v3_minimal.openretop")
        self.assertTrue(legacy.success)
        self.assertTrue(current.success)
        self.assertTrue(legacy.migrated)
        self.assertEqual(current.project.metadata["fixture"], "v3")

    def test_complete_v3_fixture_restores_retained_workflow_records(self) -> None:
        result = JsonProjectRepository().read(
            ROOT / "tests" / "fixtures" / "v3_complete.openretop"
        )
        self.assertTrue(result.success)
        state = AppState()
        restored = restore_project_state(state, result.project)

        self.assertEqual(len(state.section_collection.results), 1)
        # its curve comes back for the 3D Sketch; its old preview surface is reported as dropped
        self.assertEqual([name for name, _points, _closed in restored.legacy_curves], ["Fixture Manual Curve"])
        self.assertTrue(any("older surface tools" in text for text in restored.warnings))
        self.assertEqual(state.region_collection.active_region.id, "region-a")
        self.assertEqual(restored.primary_selection_id, "region:region-a")
        self.assertEqual(result.project.metadata["fixture_extension"], {"preserve": True})

    def test_composition_is_release_safe(self) -> None:
        composition = create_application()
        self.assertIsNotNone(composition.scene_builder)
        self.assertIsNotNone(composition.workflow)
        self.assertIsNotNone(composition.modeling_controller)

    def test_supported_entry_point_and_framework_metadata_are_present(self) -> None:
        entry = (ROOT / "src" / "openretop" / "main.py").read_text(encoding="utf-8")
        package_metadata = (ROOT / "packages" / "workbench_ui" / "pyproject.toml").read_text(
            encoding="utf-8"
        )
        self.assertIn("run_v3_app", entry)
        self.assertIn('name = "openretop-workbench-ui"', package_metadata)
        self.assertIn("PySide6", package_metadata)


if __name__ == "__main__":
    unittest.main()
