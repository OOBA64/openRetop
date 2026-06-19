from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cad_kernel.backend import build_loft_surface_from_curves
from cad_kernel.types import CadCurveInput, CadKernelInfo


def _curve_input(
    points: object,
    *,
    is_closed: bool = False,
    curve_id: str = "curve-1",
    name: str = "Curve 1",
) -> CadCurveInput:
    point_array = np.asarray(points, dtype=float)
    return CadCurveInput(
        points=point_array,
        is_closed=is_closed,
        name=name,
        curve_id=curve_id,
        metadata={"source_point_count": int(len(point_array))},
    )


def _available_info() -> CadKernelInfo:
    return CadKernelInfo(
        available=True,
        backend_name="FakeCAD",
        module_name="fakecad",
        status="CAD kernel available: FakeCAD",
    )


def _unavailable_info() -> CadKernelInfo:
    return CadKernelInfo(
        available=False,
        backend_name="unavailable",
        module_name=None,
        status="CAD kernel unavailable for test",
    )


class CadKernelLoftSurfaceTests(unittest.TestCase):
    def test_parallel_open_curves_build_loft_surface(self) -> None:
        sentinel_surface = object()
        captured: dict[str, object] = {}

        def fake_builder(
            first_points: object,
            second_points: object,
            *,
            closed: bool,
        ) -> object:
            captured["first_points"] = np.asarray(first_points, dtype=float)
            captured["second_points"] = np.asarray(second_points, dtype=float)
            captured["closed"] = bool(closed)
            return sentinel_surface

        first_curve = _curve_input(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            curve_id="curve-a",
            name="Curve A",
        )
        second_curve = _curve_input(
            [[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]],
            curve_id="curve-b",
            name="Curve B",
        )
        fake_backend = SimpleNamespace(build_loft_surface_from_points=fake_builder)

        with (
            patch("cad_kernel.backend.cad_kernel_info", return_value=_available_info()),
            patch("cad_kernel.backend.import_cad_backend", return_value=fake_backend),
        ):
            result = build_loft_surface_from_curves(first_curve, second_curve)

        self.assertTrue(result.success)
        self.assertIs(result.cad_object, sentinel_surface)
        self.assertEqual(result.reason, "Loft BREP surface built.")
        self.assertFalse(captured["closed"])
        self.assertTrue(np.allclose(captured["first_points"], first_curve.points))
        self.assertTrue(np.allclose(captured["second_points"], second_curve.points))
        self.assertEqual(result.metadata["brep_type"], "loft_surface")
        self.assertEqual(result.metadata["source_curve_ids"], ["curve-a", "curve-b"])
        self.assertEqual(result.metadata["source_curve_names"], ["Curve A", "Curve B"])
        self.assertEqual(result.metadata["source_point_counts"], [2, 2])
        self.assertEqual(result.metadata["clean_point_counts"], [2, 2])
        self.assertEqual(result.metadata["backend"], "FakeCAD")
        self.assertEqual(result.metadata["build_method"], "two_curve_loft")

    def test_closed_curves_pass_closed_loft_flag(self) -> None:
        sentinel_surface = object()
        captured: dict[str, object] = {}

        def fake_builder(
            first_points: object,
            second_points: object,
            *,
            closed: bool,
        ) -> object:
            captured["closed"] = bool(closed)
            captured["first_count"] = len(np.asarray(first_points, dtype=float))
            captured["second_count"] = len(np.asarray(second_points, dtype=float))
            return sentinel_surface

        first_curve = _curve_input(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.5, 1.0, 0.0]],
            is_closed=True,
            curve_id="closed-a",
        )
        second_curve = _curve_input(
            [[0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [0.5, 1.0, 1.0]],
            is_closed=True,
            curve_id="closed-b",
        )
        fake_backend = SimpleNamespace(build_loft_surface_from_points=fake_builder)

        with (
            patch("cad_kernel.backend.cad_kernel_info", return_value=_available_info()),
            patch("cad_kernel.backend.import_cad_backend", return_value=fake_backend),
        ):
            result = build_loft_surface_from_curves(first_curve, second_curve)

        self.assertTrue(result.success)
        self.assertTrue(captured["closed"])
        self.assertEqual(captured["first_count"], 3)
        self.assertEqual(captured["second_count"], 3)
        self.assertTrue(result.metadata["closed"])

    def test_mixed_open_closed_curves_fail_clearly(self) -> None:
        first_curve = _curve_input([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
        second_curve = _curve_input(
            [[0.0, 1.0, 0.0], [1.0, 1.0, 0.0], [0.5, 2.0, 0.0]],
            is_closed=True,
        )

        with patch("cad_kernel.backend.import_cad_backend") as import_backend:
            result = build_loft_surface_from_curves(first_curve, second_curve)

        self.assertFalse(result.success)
        self.assertIn("both curves to be open or both closed", result.reason)
        import_backend.assert_not_called()

    def test_invalid_pair_fails_clearly(self) -> None:
        first_curve = _curve_input([[0.0, 0.0, 0.0]])
        second_curve = _curve_input([[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]])

        result = build_loft_surface_from_curves(first_curve, second_curve)

        self.assertFalse(result.success)
        self.assertIn("Loft BREP surface input is invalid", result.reason)

    def test_point_count_mismatch_warns_and_preserves_order(self) -> None:
        sentinel_surface = object()
        first_curve = _curve_input(
            [[0.0, 0.0, 0.0], [0.5, 0.0, 0.0], [1.0, 0.0, 0.0]],
            curve_id="first",
        )
        second_curve = _curve_input(
            [[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]],
            curve_id="second",
        )
        fake_backend = SimpleNamespace(
            build_loft_surface_from_points=lambda first, second, *, closed: sentinel_surface
        )

        with (
            patch("cad_kernel.backend.cad_kernel_info", return_value=_available_info()),
            patch("cad_kernel.backend.import_cad_backend", return_value=fake_backend),
        ):
            result = build_loft_surface_from_curves(first_curve, second_curve)

        self.assertTrue(result.success)
        self.assertEqual(result.metadata["source_curve_ids"], ["first", "second"])
        self.assertEqual(
            result.warnings,
            [
                "Loft source curves have different point counts; rebuild curves for better consistency."
            ],
        )
        self.assertEqual(result.metadata["warnings"], result.warnings)

    def test_unavailable_backend_returns_failure_without_crashing(self) -> None:
        first_curve = _curve_input([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
        second_curve = _curve_input([[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]])

        with (
            patch("cad_kernel.backend.cad_kernel_info", return_value=_unavailable_info()),
            patch("cad_kernel.backend.import_cad_backend") as import_backend,
        ):
            result = build_loft_surface_from_curves(first_curve, second_curve)

        self.assertFalse(result.success)
        self.assertEqual(result.reason, "CAD kernel unavailable for test")
        self.assertEqual(result.metadata["backend"], "unavailable")
        import_backend.assert_not_called()

    def test_backend_build_error_returns_failure_without_crashing(self) -> None:
        def failing_builder(
            first_points: object,
            second_points: object,
            *,
            closed: bool,
        ) -> object:
            raise RuntimeError("loft failed")

        first_curve = _curve_input([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
        second_curve = _curve_input([[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]])
        fake_backend = SimpleNamespace(build_loft_surface_from_points=failing_builder)

        with (
            patch("cad_kernel.backend.cad_kernel_info", return_value=_available_info()),
            patch("cad_kernel.backend.import_cad_backend", return_value=fake_backend),
        ):
            result = build_loft_surface_from_curves(first_curve, second_curve)

        self.assertFalse(result.success)
        self.assertIn("CAD kernel failed to build loft surface", result.reason)
        self.assertIn("loft failed", result.reason)


if __name__ == "__main__":
    unittest.main()
