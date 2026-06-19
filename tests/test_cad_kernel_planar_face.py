from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cad_kernel.backend import build_planar_face_from_curve
from cad_kernel.types import CadCurveInput, CadKernelInfo


def _curve_input(
    points: object,
    *,
    is_closed: bool = True,
    curve_id: str = "curve-1",
    name: str = "Curve 1",
    metadata: dict[str, object] | None = None,
) -> CadCurveInput:
    point_array = np.asarray(points, dtype=float)
    curve_metadata = {"source_point_count": int(len(point_array))}
    curve_metadata.update(metadata or {})
    return CadCurveInput(
        points=point_array,
        is_closed=is_closed,
        name=name,
        curve_id=curve_id,
        metadata=curve_metadata,
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


class CadKernelPlanarFaceTests(unittest.TestCase):
    def test_square_closed_curve_builds_planar_face_with_clean_points(self) -> None:
        sentinel_face = object()
        captured: dict[str, np.ndarray] = {}

        def fake_builder(points: object) -> object:
            captured["points"] = np.asarray(points, dtype=float)
            return sentinel_face

        curve_input = _curve_input(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0],
            ],
            curve_id="square",
            name="Square",
        )
        fake_backend = SimpleNamespace(build_planar_face_from_points=fake_builder)

        with (
            patch("cad_kernel.backend.cad_kernel_info", return_value=_available_info()),
            patch("cad_kernel.backend.import_cad_backend", return_value=fake_backend),
        ):
            result = build_planar_face_from_curve(curve_input)

        self.assertTrue(result.success)
        self.assertIs(result.cad_object, sentinel_face)
        self.assertEqual(result.reason, "Planar BREP face built.")
        self.assertEqual(len(captured["points"]), 4)
        self.assertTrue(np.allclose(captured["points"][-1], [0.0, 1.0, 0.0]))
        self.assertEqual(result.metadata["brep_type"], "planar_face")
        self.assertEqual(result.metadata["source_curve_id"], "square")
        self.assertEqual(result.metadata["source_curve_name"], "Square")
        self.assertEqual(result.metadata["source_point_count"], 5)
        self.assertEqual(result.metadata["clean_point_count"], 4)
        self.assertEqual(result.metadata["backend"], "FakeCAD")
        self.assertEqual(result.metadata["build_method"], "closed_wire_planar_face")
        self.assertAlmostEqual(result.metadata["planarity_error"], 0.0)

    def test_triangle_closed_curve_builds_planar_face(self) -> None:
        sentinel_face = object()
        curve_input = _curve_input(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
            ],
            curve_id="triangle",
        )
        fake_backend = SimpleNamespace(
            build_planar_face_from_points=lambda points: sentinel_face
        )

        with (
            patch("cad_kernel.backend.cad_kernel_info", return_value=_available_info()),
            patch("cad_kernel.backend.import_cad_backend", return_value=fake_backend),
        ):
            result = build_planar_face_from_curve(curve_input)

        self.assertTrue(result.success)
        self.assertIs(result.cad_object, sentinel_face)
        self.assertEqual(result.metadata["clean_point_count"], 3)

    def test_open_curve_is_rejected_before_backend_import(self) -> None:
        curve_input = _curve_input(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0]],
            is_closed=False,
        )

        with patch("cad_kernel.backend.import_cad_backend") as import_backend:
            result = build_planar_face_from_curve(curve_input)

        self.assertFalse(result.success)
        self.assertIsNone(result.cad_object)
        self.assertIn("requires a closed curve", result.reason)
        import_backend.assert_not_called()

    def test_degenerate_closed_curve_is_rejected(self) -> None:
        curve_input = _curve_input(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [2.0, 0.0, 0.0],
            ],
            curve_id="line",
        )

        result = build_planar_face_from_curve(curve_input)

        self.assertFalse(result.success)
        self.assertIn("degenerate", result.reason)

    def test_clearly_non_planar_curve_is_rejected(self) -> None:
        curve_input = _curve_input(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.5],
                [0.0, 1.0, 0.0],
            ],
            curve_id="non-planar",
            metadata={"planarity_tolerance": 1e-4},
        )

        result = build_planar_face_from_curve(curve_input)

        self.assertFalse(result.success)
        self.assertIn("too non-planar", result.reason)

    def test_slightly_non_planar_curve_warns_and_builds(self) -> None:
        sentinel_face = object()
        curve_input = _curve_input(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0001],
                [0.0, 1.0, 0.0],
            ],
            curve_id="slightly-non-planar",
        )
        fake_backend = SimpleNamespace(
            build_planar_face_from_points=lambda points: sentinel_face
        )

        with (
            patch("cad_kernel.backend.cad_kernel_info", return_value=_available_info()),
            patch("cad_kernel.backend.import_cad_backend", return_value=fake_backend),
        ):
            result = build_planar_face_from_curve(curve_input)

        self.assertTrue(result.success)
        self.assertIs(result.cad_object, sentinel_face)
        self.assertEqual(
            result.warnings,
            ["Curve is slightly non-planar; using best-fit plane for planar face."],
        )
        self.assertGreater(result.metadata["planarity_error"], 0.0)

    def test_unavailable_cad_backend_returns_failure_without_crashing(self) -> None:
        curve_input = _curve_input(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
                [0.0, 1.0, 0.0],
            ]
        )

        with (
            patch("cad_kernel.backend.cad_kernel_info", return_value=_unavailable_info()),
            patch("cad_kernel.backend.import_cad_backend") as import_backend,
        ):
            result = build_planar_face_from_curve(curve_input)

        self.assertFalse(result.success)
        self.assertIsNone(result.cad_object)
        self.assertEqual(result.reason, "CAD kernel unavailable for test")
        self.assertEqual(result.metadata["backend"], "unavailable")
        import_backend.assert_not_called()

    def test_backend_build_error_returns_failure_without_crashing(self) -> None:
        def failing_builder(points: object) -> object:
            raise RuntimeError("wire failed")

        curve_input = _curve_input(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
                [0.0, 1.0, 0.0],
            ]
        )
        fake_backend = SimpleNamespace(build_planar_face_from_points=failing_builder)

        with (
            patch("cad_kernel.backend.cad_kernel_info", return_value=_available_info()),
            patch("cad_kernel.backend.import_cad_backend", return_value=fake_backend),
        ):
            result = build_planar_face_from_curve(curve_input)

        self.assertFalse(result.success)
        self.assertIsNone(result.cad_object)
        self.assertIn("CAD kernel failed to build planar face", result.reason)
        self.assertIn("wire failed", result.reason)


if __name__ == "__main__":
    unittest.main()
