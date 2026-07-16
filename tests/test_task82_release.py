from __future__ import annotations

from pathlib import Path
import unittest

from bootstrap import create_application
from application.state import AppState
from cad_kernel.types import CadKernelInfo
from infrastructure.cad_adapter import PublicCadAdapter
from infrastructure.persistence import JsonProjectRepository
from project.project_session import restore_project_state


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

    def test_complete_v3_fixture_restores_retained_workflow_records(self) -> None:
        result = JsonProjectRepository().read(
            ROOT / "tests" / "fixtures" / "v3_complete.openretop"
        )
        self.assertTrue(result.success)
        state = AppState()
        restored = restore_project_state(state, result.project)

        self.assertEqual(len(state.section_collection.results), 1)
        self.assertEqual([item.id for item in state.curve_collection.curves], ["curve-a"])
        self.assertEqual([item.id for item in state.surface_collection.surfaces], ["surface-a"])
        self.assertEqual(state.region_collection.active_region.id, "region-a")
        self.assertEqual(restored.primary_selection_id, "region:region-a")
        self.assertEqual(result.project.metadata["fixture_extension"], {"preserve": True})

    def test_composition_and_capability_report_are_release_safe(self) -> None:
        composition = create_application()
        self.assertIsNotNone(composition.scene_builder)
        self.assertIn("trim", composition.cad.capabilities.__dataclass_fields__)
        self.assertFalse(composition.cad.capabilities.trim)
        self.assertFalse(composition.cad.capabilities.intersection)

    def test_composition_starts_with_cad_explicitly_unavailable(self) -> None:
        unavailable = PublicCadAdapter(
            CadKernelInfo(False, "unavailable", None, "CAD unavailable for test")
        )
        composition = create_application(cad_adapter=unavailable)

        self.assertFalse(composition.cad.capabilities.available)
        self.assertFalse(composition.cad.capabilities.step_export)
        self.assertIsNotNone(composition.workflow)
        self.assertFalse(composition.cad.build_wire(object()).success)
        self.assertFalse(composition.cad.export_step(object(), "unused.step").success)

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
