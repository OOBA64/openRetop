from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from openretop.cad_kernel.backend import cad_kernel_status, is_cad_kernel_available
from openretop.cad_kernel.occ_backend import detect_cad_kernel_backend
from openretop.cad_kernel.types import CadKernelInfo


class CadKernelBackendTests(unittest.TestCase):
    def test_public_status_helpers_do_not_require_cad_dependency(self) -> None:
        self.assertIsInstance(is_cad_kernel_available(), bool)
        status = cad_kernel_status()
        self.assertTrue(
            status.startswith("CAD kernel available:")
            or status.startswith("CAD kernel unavailable:")
        )

    def test_detection_reports_unavailable_without_optional_modules(self) -> None:
        with patch("openretop.cad_kernel.occ_backend.importlib.util.find_spec", return_value=None):
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

        with patch("openretop.cad_kernel.occ_backend.importlib.util.find_spec", fake_find_spec):
            info = detect_cad_kernel_backend()

        self.assertTrue(info.available)
        self.assertEqual(info.backend_name, "OCP")
        self.assertEqual(info.module_name, "OCP")
        self.assertEqual(info.status, "CAD kernel available: OCP")


if __name__ == "__main__":
    unittest.main()
