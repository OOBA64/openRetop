from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openretop.geometry.units import get_unit, unit_scale
from openretop.infrastructure.persistence import JsonProjectRepository
from openretop.project.atomic_io import write_text_atomic
from openretop.project.migrations import migrate_project_dict
from openretop.project.project_data import PROJECT_VERSION, ProjectRegion, default_project_data
from openretop.project.project_io import load_project, save_project

FIXTURES = Path(__file__).parent / "fixtures"


class AtomicWriteTests(unittest.TestCase):
    def test_failed_write_keeps_previous_file_and_leaves_no_temp_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "p.openretop"
            target.write_text("original", encoding="utf-8")
            with mock.patch("openretop.project.atomic_io.os.replace", side_effect=OSError("disk gone")):
                with self.assertRaises(OSError):
                    write_text_atomic(target, "replacement")
            self.assertEqual(target.read_text(encoding="utf-8"), "original")
            self.assertEqual([p.name for p in Path(directory).iterdir()], ["p.openretop"])

    def test_write_replaces_file_and_creates_parent_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "nested" / "p.openretop"
            write_text_atomic(target, "one")
            write_text_atomic(target, "two")
            self.assertEqual(target.read_text(encoding="utf-8"), "two")
            self.assertEqual(len(list(target.parent.iterdir())), 1)

    def test_save_project_serialisation_error_does_not_touch_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "p.openretop"
            target.write_text("keep me", encoding="utf-8")
            with self.assertRaises(ValueError):
                save_project("not a project", target)  # type: ignore[arg-type]
            self.assertEqual(target.read_text(encoding="utf-8"), "keep me")


class AtomicProjectSaveTests(unittest.TestCase):
    def test_both_save_paths_survive_a_failed_replace(self) -> None:
        for save in (
            lambda project, path: save_project(project, path),
            lambda project, path: JsonProjectRepository().write(project, path),
        ):
            with tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "p.openretop"
                target.write_text("original", encoding="utf-8")
                with mock.patch("openretop.project.atomic_io.os.replace", side_effect=OSError("boom")):
                    try:
                        save(default_project_data(), target)
                    except OSError:
                        pass
                self.assertEqual(target.read_text(encoding="utf-8"), "original")


class RelativeMeshPathTests(unittest.TestCase):
    def test_mesh_path_is_saved_relative_and_resolves_after_moving_both(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a" / "scans").mkdir(parents=True)
            mesh = root / "a" / "scans" / "part.stl"
            mesh.write_bytes(b"x")
            project = default_project_data()
            project.mesh_path = str(mesh)
            repository = JsonProjectRepository()
            project_file = root / "a" / "job.openretop"
            self.assertTrue(repository.write(project, project_file).success)

            raw = json.loads(project_file.read_text(encoding="utf-8"))
            self.assertEqual(raw["mesh_path"], "scans/part.stl")
            self.assertEqual(project.mesh_path, str(mesh), "in-memory project must not change")

            (root / "a").rename(root / "b")
            moved = repository.read(root / "b" / "job.openretop")
            self.assertEqual(moved.resolved_mesh_path, (root / "b" / "scans" / "part.stl").resolve())
            self.assertFalse([w for w in moved.warnings if w.code == "missing_mesh"])

    def test_mesh_in_parent_directory_uses_dotdot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "proj").mkdir()
            project = default_project_data()
            project.mesh_path = str(root / "scan.stl")
            JsonProjectRepository().write(project, root / "proj" / "x.openretop")
            raw = json.loads((root / "proj" / "x.openretop").read_text(encoding="utf-8"))
            self.assertEqual(raw["mesh_path"], "../scan.stl")


class MigrationTests(unittest.TestCase):
    def test_current_version_is_two_and_unversioned_data_migrates_through_chain(self) -> None:
        self.assertEqual(PROJECT_VERSION, 2)
        migrated, applied = migrate_project_dict({"name": "old"})
        self.assertEqual(applied, [0, 1])
        self.assertEqual(migrated["version"], 2)
        self.assertEqual(migrated["units"], "mm")
        self.assertTrue(migrated["units_assumed"])

    def test_v1_fixture_loads_with_assumed_units_and_reports_migration(self) -> None:
        result = JsonProjectRepository().read(FIXTURES / "v3_complete.openretop")
        self.assertTrue(result.success, result.errors)
        self.assertTrue(result.migrated)
        self.assertEqual(result.project.version, PROJECT_VERSION)
        self.assertEqual(result.project.units, "mm")
        self.assertTrue(result.project.units_assumed)
        codes = {w.code for w in result.warnings}
        self.assertIn("migrated_project", codes)
        self.assertIn("units_assumed", codes)

    def test_current_version_needs_no_migration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "p.openretop"
            project = default_project_data()
            project.units = "in"
            save_project(project, path)
            result = JsonProjectRepository().read(path)
            self.assertFalse(result.migrated)
            self.assertEqual(result.project.units, "in")
            self.assertFalse(result.project.units_assumed)
            self.assertEqual(load_project(path), project)

    def test_newer_version_and_bad_versions_are_rejected(self) -> None:
        for bad in (PROJECT_VERSION + 1, -1, True, "2", 1.5):
            with self.assertRaises(ValueError, msg=repr(bad)):
                migrate_project_dict({"version": bad})

    def test_unknown_unit_is_rejected_on_load(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "p.openretop"
            path.write_text(json.dumps({"version": 2, "units": "furlongs"}), encoding="utf-8")
            result = JsonProjectRepository().read(path)
            self.assertFalse(result.success)


class RegionPersistenceTests(unittest.TestCase):
    def test_region_selection_round_trips_through_repository(self) -> None:
        project = default_project_data()
        project.region = ProjectRegion(
            id="region-1",
            name="Top face",
            triangle_indices=[4, 5, 9],
            threshold_degrees=12.5,
            max_triangle_count=1000,
            source_mesh_identifier="mesh-1",
            source_mesh_name="part",
            seed_triangle_index=5,
            visible=True,
            selected=True,
            metadata={"triangle_count": 3},
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "r.openretop"
            repository = JsonProjectRepository()
            repository.write(project, path)
            loaded = repository.read(path).project
        self.assertEqual(loaded.region, project.region)


class UnitTests(unittest.TestCase):
    def test_conversions(self) -> None:
        self.assertAlmostEqual(unit_scale("in", "mm"), 25.4)
        self.assertAlmostEqual(unit_scale("m", "mm"), 1000.0)
        self.assertAlmostEqual(unit_scale("mm", "in"), 1 / 25.4)
        self.assertEqual(get_unit("Inches").code, "in")
        with self.assertRaises(ValueError):
            get_unit("parsec")


if __name__ == "__main__":
    unittest.main()
