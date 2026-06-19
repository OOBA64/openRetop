from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cad_kernel.backend import cad_kernel_status, is_cad_kernel_available
from cad_kernel.occ_backend import detect_cad_kernel_backend
from cad_kernel.types import CadKernelInfo


class CadKernelBackendTests(unittest.TestCase):
    def test_public_status_helpers_do_not_require_cad_dependency(self) -> None:
        self.assertIsInstance(is_cad_kernel_available(), bool)
        status = cad_kernel_status()
        self.assertTrue(
            status.startswith("CAD kernel available:")
            or status.startswith("CAD kernel unavailable:")
        )

    def test_detection_reports_unavailable_without_optional_modules(self) -> None:
        with patch("cad_kernel.occ_backend.importlib.util.find_spec", return_value=None):
            info = detect_cad_kernel_backend()

        self.assertIsInstance(info, CadKernelInfo)
        self.assertFalse(info.available)
        self.assertEqual(info.backend_name, "unavailable")
        self.assertIn("install OCP/pythonocc-core", info.status)

    def test_detection_prefers_ocp_when_available(self) -> None:
        def fake_find_spec(module_name: str) -> object | None:
            if module_name == "OCP":
                return SimpleNamespace(origin="test")
            return None

        with patch("cad_kernel.occ_backend.importlib.util.find_spec", fake_find_spec):
            info = detect_cad_kernel_backend()

        self.assertTrue(info.available)
        self.assertEqual(info.backend_name, "OCP")
        self.assertEqual(info.module_name, "OCP")
        self.assertEqual(info.status, "CAD kernel available: OCP")


if __name__ == "__main__":
    unittest.main()
