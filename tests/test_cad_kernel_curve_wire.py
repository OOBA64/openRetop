from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cad_kernel.backend import (
    build_loft_surface_from_cad_wires,
    build_planar_face_from_cad_wire,
)
from cad_kernel.curve_wire import build_cad_wire_from_curve
from cad_kernel.types import CadKernelInfo
from curves.manual_curve import (
    CURVE_POINT_CORNER,
    CURVE_POINT_SMOOTH,
    MANUAL_CURVE_METHOD_HYBRID,
    build_manual_stored_curve,
)
from curves.curve_state import StoredCurve


def _curve(point_types: list[str], *, closed: bool = True):
    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
        dtype=float,
    )
    return build_manual_stored_curve(
        curve_id="curve-wire",
        name="Wire Curve",
        control_points=points,
        is_closed=closed,
        creation_type="manual",
        snap_to_mesh=False,
        work_plane_type="world_xy",
        curve_method=MANUAL_CURVE_METHOD_HYBRID,
        point_types=point_types,
    )


def _available_info() -> CadKernelInfo:
    return CadKernelInfo(True, "FakeCAD", "fake", "CAD kernel available: FakeCAD")


class CadCurveWireTests(unittest.TestCase):
    def _build_with_fake_backend(self, curve):
        captured: dict[str, object] = {}

        def builder(segments, *, closed):
            captured["segments"] = segments
            captured["closed"] = closed
            return object()

        backend = SimpleNamespace(build_cad_wire_from_segments=builder)
        with (
            patch("cad_kernel.curve_wire.detect_cad_kernel_backend", return_value=_available_info()),
            patch("cad_kernel.curve_wire.import_cad_backend", return_value=backend),
        ):
            result = build_cad_wire_from_curve(curve)
        return result, captured

    def test_corner_square_builds_four_line_edges(self) -> None:
        result, captured = self._build_with_fake_backend(
            _curve([CURVE_POINT_CORNER] * 4)
        )

        self.assertTrue(result.success)
        self.assertEqual(result.metadata["cad_wire_edge_count"], 4)
        self.assertEqual(result.metadata["cad_wire_line_edge_count"], 4)
        self.assertEqual(result.metadata["cad_wire_spline_edge_count"], 0)
        self.assertTrue(captured["closed"])

    def test_smooth_curve_builds_spline_wire(self) -> None:
        result, captured = self._build_with_fake_backend(
            _curve([CURVE_POINT_SMOOTH] * 4)
        )

        self.assertTrue(result.success)
        self.assertEqual(result.metadata["cad_wire_line_edge_count"], 0)
        self.assertEqual(result.metadata["cad_wire_spline_edge_count"], 1)
        self.assertEqual(captured["segments"][0]["kind"], "spline")

    def test_mixed_curve_builds_line_and_spline_edges(self) -> None:
        result, _captured = self._build_with_fake_backend(
            _curve(
                [
                    CURVE_POINT_CORNER,
                    CURVE_POINT_CORNER,
                    CURVE_POINT_SMOOTH,
                    CURVE_POINT_CORNER,
                ]
            )
        )

        self.assertTrue(result.success)
        self.assertGreater(result.metadata["cad_wire_line_edge_count"], 0)
        self.assertGreater(result.metadata["cad_wire_spline_edge_count"], 0)

    def test_unavailable_backend_fails_without_crashing(self) -> None:
        info = CadKernelInfo(False, "unavailable", None, "CAD unavailable")
        with patch(
            "cad_kernel.curve_wire.detect_cad_kernel_backend",
            return_value=info,
        ):
            result = build_cad_wire_from_curve(_curve([CURVE_POINT_CORNER] * 4))

        self.assertFalse(result.success)
        self.assertEqual(result.reason, "CAD unavailable")
        self.assertEqual(result.metadata["cad_wire_line_edge_count"], 4)

    def test_legacy_curve_uses_fitted_point_fallback(self) -> None:
        fitted_points = np.asarray(
            [[0.0, 0.0, 0.0], [0.5, 0.2, 0.0], [1.0, 0.0, 0.0]],
            dtype=float,
        )
        curve = StoredCurve(
            id="legacy",
            name="Legacy",
            section_result_id="",
            plane_id="",
            original_points=fitted_points.copy(),
            fitted_points=fitted_points,
            mean_error=0.0,
            max_error=0.0,
            is_closed=False,
            metadata={
                "control_points": fitted_points.tolist(),
                "curve_method": "catmull_rom",
            },
        )

        result, captured = self._build_with_fake_backend(curve)

        self.assertTrue(result.success)
        self.assertEqual(result.metadata["cad_point_source"], "fitted_points_fallback")
        self.assertEqual(result.metadata["cad_wire_line_edge_count"], 2)
        self.assertEqual(
            [segment["kind"] for segment in captured["segments"]],
            ["line", "line"],
        )

    def test_wire_builders_create_face_and_capped_loft(self) -> None:
        face = object()
        loft = object()
        backend = SimpleNamespace(
            build_planar_face_from_wire=lambda wire: face,
            build_loft_from_wires=lambda wires, **options: loft,
        )
        with (
            patch("cad_kernel.backend.cad_kernel_info", return_value=_available_info()),
            patch("cad_kernel.backend.import_cad_backend", return_value=backend),
        ):
            face_result = build_planar_face_from_cad_wire(object())
            loft_result = build_loft_surface_from_cad_wires(
                [object(), object()],
                closed_profiles=True,
                cap_start=True,
                cap_end=True,
                create_solid_if_closed=True,
            )

        self.assertIs(face_result.cad_object, face)
        self.assertIs(loft_result.cad_object, loft)
        self.assertTrue(loft_result.metadata["cap_start"])
        self.assertTrue(loft_result.metadata["cap_end"])
        self.assertTrue(loft_result.metadata["create_solid_if_closed"])

    def test_open_loft_rejects_caps_with_clear_message(self) -> None:
        result = build_loft_surface_from_cad_wires(
            [object(), object()],
            closed_profiles=False,
            cap_start=True,
        )

        self.assertFalse(result.success)
        self.assertIn("open sheet", result.reason.lower())

    def test_multi_section_loft_fails_clearly(self) -> None:
        result = build_loft_surface_from_cad_wires(
            [object(), object(), object()],
            closed_profiles=True,
        )

        self.assertFalse(result.success)
        self.assertEqual(result.reason, "Multi-section editable loft not implemented yet.")


if __name__ == "__main__":
    unittest.main()
