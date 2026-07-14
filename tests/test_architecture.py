from __future__ import annotations

from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
METRICS_PATH = ROOT / "scripts" / "report_architecture_metrics.py"
BASELINE_PATH = ROOT / "tests" / "architecture_dependency_baseline.json"

SPEC = importlib.util.spec_from_file_location("architecture_metrics", METRICS_PATH)
assert SPEC is not None and SPEC.loader is not None
architecture_metrics = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = architecture_metrics
SPEC.loader.exec_module(architecture_metrics)


class ArchitectureBaselineTests(unittest.TestCase):
    def test_dependency_allowlist_contains_no_unreviewed_findings(self) -> None:
        baseline = architecture_metrics.load_dependency_baseline(BASELINE_PATH)
        violations = architecture_metrics.dependency_violations(ROOT)
        allowed = architecture_metrics.baseline_ui_counter(baseline)
        actual = Counter(item.baseline_key for item in violations)
        unexpected = architecture_metrics.unexpected_architecture_findings(
            ROOT,
            BASELINE_PATH,
        )

        print(
            "Architecture baseline: "
            f"{sum((actual & allowed).values())} known UI imports, "
            "0 allowed package cycles, 0 allowed module cycles."
        )
        self.assertEqual(actual - allowed, Counter())
        self.assertEqual(unexpected["ui_imports"], Counter())
        self.assertEqual(unexpected["package_cycles"], set())
        self.assertEqual(unexpected["module_cycles"], set())

    def test_allowlist_is_human_readable_and_documents_every_entry(self) -> None:
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

        self.assertIn("_description", baseline)
        self.assertIn("_ui_import_policy", baseline)
        for entry in baseline["ui_imports"]:
            self.assertTrue(entry["path"])
            self.assertTrue(entry["module"])
            self.assertGreaterEqual(entry["count"], 1)
            self.assertTrue(entry["reason"])

    def test_new_application_package_has_no_ui_toolkit_imports(self) -> None:
        application_violations = [
            item
            for item in architecture_metrics.dependency_violations(ROOT)
            if item.path.startswith("application/")
        ]

        self.assertEqual(application_violations, [])

    def test_protected_modules_have_no_current_ui_rendering_imports(self) -> None:
        protected_prefixes = ("project/", "settings/", "cad_kernel/")
        protected_paths = {
            "mesh/query_service.py",
            "mesh/spatial_index.py",
        }
        protected_violations = [
            item
            for item in architecture_metrics.dependency_violations(ROOT)
            if item.path.startswith(protected_prefixes)
            or item.path in protected_paths
        ]

        self.assertEqual(protected_violations, [])

    def test_no_practical_package_or_module_cycles_exist(self) -> None:
        package_cycles, module_cycles = architecture_metrics.practical_cycles(ROOT)

        self.assertEqual(package_cycles, [])
        self.assertEqual(module_cycles, [])

    def test_metrics_report_required_architecture_dimensions(self) -> None:
        report = architecture_metrics.build_report(
            ROOT,
            BASELINE_PATH,
            largest_limit=5,
        )

        self.assertGreater(report["python"]["src_files"], 0)
        self.assertGreater(report["python"]["src_lines"], 0)
        self.assertGreater(report["python"]["classes"], 0)
        self.assertGreater(report["python"]["functions"], 0)
        self.assertGreater(report["python"]["main_window_methods"], 0)
        self.assertEqual(len(report["largest_modules"]), 5)
        self.assertTrue(report["major_package_imports"])
        self.assertIn("dependency_violations", report)
        self.assertIn("package_cycles", report)
        self.assertIn("duplicate_action_labels", report)

    def test_duplicate_action_label_report_finds_legacy_duplicates(self) -> None:
        duplicates = {
            item.label: item.count
            for item in architecture_metrics.duplicate_action_labels(ROOT)
        }

        self.assertGreaterEqual(duplicates["Delete Selected"], 2)
        self.assertGreaterEqual(duplicates["Frame Selected"], 2)


class ArchitectureScannerCharacterizationTests(unittest.TestCase):
    def test_scanner_detects_ui_imports_in_all_guarded_areas(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            samples = {
                "src/application/bad.py": "import tkinter\n",
                "src/analysis/bad_vtk.py": "from vtk import vtkActor\n",
                "src/curves/bad.py": "from PyQt6 import QtWidgets\n",
                "src/project/bad.py": "import PySide6\n",
                "src/settings/bad.py": (
                    "from vtkmodules.vtkRenderingCore import vtkActor\n"
                ),
                "src/cad_kernel/bad.py": "import pyvista\n",
                "src/mesh/query_service.py": (
                    "from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera\n"
                ),
            }
            for relative, source in samples.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source, encoding="utf-8")

            violations = architecture_metrics.dependency_violations(root)

        self.assertEqual(len(violations), len(samples))
        self.assertEqual(
            {item.path for item in violations},
            {path.removeprefix("src/") for path in samples},
        )

    def test_mesh_query_scanner_allows_computational_vtk_locator_imports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "src" / "mesh" / "spatial_index.py"
            path.parent.mkdir(parents=True)
            path.write_text(
                "\n".join(
                    (
                        "from vtkmodules.util.numpy_support import numpy_to_vtk",
                        "from vtkmodules.vtkCommonDataModel import vtkStaticCellLocator",
                    )
                ),
                encoding="utf-8",
            )

            violations = architecture_metrics.dependency_violations(root)

        self.assertEqual(violations, [])

    def test_cycle_scanner_detects_practical_package_and_module_cycles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = {
                "src/alpha/__init__.py": "",
                "src/alpha/one.py": "from beta import two\n",
                "src/beta/__init__.py": "",
                "src/beta/two.py": "from alpha import one\n",
                "src/gamma/__init__.py": "",
                "src/gamma/left.py": "from . import right\n",
                "src/gamma/right.py": "from . import left\n",
            }
            for relative, source in sources.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source, encoding="utf-8")

            package_cycles, module_cycles = architecture_metrics.practical_cycles(root)

        self.assertEqual(package_cycles, [("alpha", "beta")])
        self.assertEqual(
            module_cycles,
            [
                ("alpha.one", "beta.two"),
                ("gamma.left", "gamma.right"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
