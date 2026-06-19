from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cad_kernel.export_step import export_step


class DirectStepWriter:
    def __init__(self, payload: str = "ISO-10303-21") -> None:
        self.payload = payload
        self.paths: list[str] = []

    def export_step(self, path: str) -> None:
        self.paths.append(path)
        Path(path).write_text(self.payload, encoding="utf-8")


class EmptyStepWriter:
    def export_step(self, path: str) -> None:
        Path(path).touch()


class CadKernelStepExportTests(unittest.TestCase):
    def test_export_step_uses_object_export_method_and_normalizes_suffix(self) -> None:
        writer = DirectStepWriter()

        with TemporaryDirectory() as tmpdir:
            requested_path = Path(tmpdir) / "face"
            result = export_step(writer, requested_path)
            expected_path = requested_path.with_suffix(".step")

            self.assertTrue(result.success)
            self.assertEqual(result.path, str(expected_path))
            self.assertEqual(writer.paths, [str(expected_path)])
            self.assertEqual(expected_path.read_text(encoding="utf-8"), "ISO-10303-21")

    def test_export_step_rejects_missing_cad_object(self) -> None:
        result = export_step(None, Path("missing.step"))

        self.assertFalse(result.success)
        self.assertIsNone(result.path)
        self.assertIn("No CAD object", result.reason)

    def test_export_step_reports_empty_output_file(self) -> None:
        with TemporaryDirectory() as tmpdir:
            result = export_step(EmptyStepWriter(), Path(tmpdir) / "empty.step")

        self.assertFalse(result.success)
        self.assertIn("output file was not written", result.reason)

    def test_export_step_reports_unsupported_object_without_cad_dependency(self) -> None:
        with TemporaryDirectory() as tmpdir:
            with patch(
                "cad_kernel.export_step._export_step_with_opencascade",
                side_effect=ModuleNotFoundError("missing"),
            ):
                result = export_step(object(), Path(tmpdir) / "unsupported.step")

        self.assertFalse(result.success)
        self.assertIn("supported STEP export API", result.reason)


if __name__ == "__main__":
    unittest.main()
