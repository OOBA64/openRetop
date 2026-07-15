from __future__ import annotations

from pathlib import Path
import unittest

from bootstrap import create_application
from infrastructure.persistence import JsonProjectRepository


ROOT = Path(__file__).resolve().parents[1]


class Task82ReleaseCandidateTests(unittest.TestCase):
    def test_legacy_and_v3_fixtures_load_without_data_loss(self) -> None:
        repository = JsonProjectRepository()
        legacy = repository.read(ROOT / "tests" / "fixtures" / "legacy_minimal.openretop")
        current = repository.read(ROOT / "tests" / "fixtures" / "v3_minimal.openretop")
        self.assertTrue(legacy.success)
        self.assertTrue(current.success)
        self.assertTrue(legacy.migrated)
        self.assertEqual(current.project.metadata["fixture"], "v3")

    def test_composition_and_capability_report_are_release_safe(self) -> None:
        composition = create_application()
        self.assertIsNotNone(composition.scene_builder)
        self.assertIn("trim", composition.cad.capabilities.__dataclass_fields__)
        self.assertFalse(composition.cad.capabilities.trim)
        self.assertFalse(composition.cad.capabilities.intersection)

    def test_supported_entry_point_and_framework_metadata_are_present(self) -> None:
        entry = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
        package_metadata = (ROOT / "packages" / "workbench_ui" / "pyproject.toml").read_text(
            encoding="utf-8"
        )
        self.assertIn("run_v3_app", entry)
        self.assertIn('name = "openretop-workbench-ui"', package_metadata)
        self.assertIn("PySide6", package_metadata)


if __name__ == "__main__":
    unittest.main()
