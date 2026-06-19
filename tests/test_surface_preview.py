from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from curves.curve_state import StoredCurve
from surfaces.surface_preview import (
    BOUNDARY_PATCH,
    CLOSED_CURVE_FILL,
    CURVE_NETWORK_PATCH,
    FOUR_CURVE_PATCH,
    FAN_FILL_WARNING,
    LOFT_PAIR_DISTANCE_WARNING,
    SurfacePreviewMesh,
    build_boundary_patch_preview,
    build_curve_network_patch_preview,
    build_four_curve_patch_preview,
    build_surface_preview,
    build_surface_preview_mesh,
)
from surfaces.surface_state import SurfacePatch


def _curve(
    curve_id: str,
    points: list[tuple[float, float, float]],
    *,
    is_closed: bool,
) -> StoredCurve:
    point_array = np.asarray(points, dtype=float)
    return StoredCurve(
        id=curve_id,
        name=curve_id,
        section_result_id="section-result",
        plane_id="plane",
        original_points=point_array.copy(),
        fitted_points=point_array.copy(),
        mean_error=0.0,
        max_error=0.0,
        is_closed=is_closed,
    )


def _surface(
    source_curve_ids: list[str],
    *,
    surface_id: str = "surface-1",
    surface_type: str = "placeholder",
    preview_mode: str | None = None,
) -> SurfacePatch:
    metadata = {} if preview_mode is None else {"preview_mode": preview_mode}
    return SurfacePatch(
        id=surface_id,
        name="Surface 1",
        source_curve_ids=source_curve_ids,
        surface_type=surface_type,
        metadata=metadata,
    )


class SurfacePreviewTests(unittest.TestCase):
    def test_one_closed_curve_creates_fan_mesh(self) -> None:
        curve = _curve(
            "curve-1",
            [
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (1.0, 1.0, 0.0),
                (0.0, 1.0, 0.0),
            ],
            is_closed=True,
        )

        result = build_surface_preview(_surface([curve.id]), [curve])

        self.assertTrue(result.preview_available)
        self.assertEqual(result.reason, "fan fill preview generated")
        self.assertEqual(result.warning, FAN_FILL_WARNING)
        preview = result.mesh
        self.assertIsInstance(preview, SurfacePreviewMesh)
        assert preview is not None
        self.assertEqual(preview.source_surface_id, "surface-1")
        self.assertEqual(preview.vertices.shape, (5, 3))
        self.assertEqual(preview.faces.shape, (4, 3))
        self.assertTrue(np.allclose(preview.vertices[0], [0.5, 0.5, 0.0]))

    def test_repeated_closing_point_is_removed_for_fan_mesh(self) -> None:
        curve = _curve(
            "curve-1",
            [
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (1.0, 1.0, 0.0),
                (0.0, 1.0, 0.0),
                (0.0, 0.0, 0.0),
            ],
            is_closed=True,
        )

        preview = build_surface_preview_mesh(_surface([curve.id]), [curve])

        assert preview is not None
        self.assertEqual(preview.vertices.shape, (5, 3))
        self.assertEqual(preview.faces.shape, (4, 3))

    def test_two_curves_create_loft_mesh(self) -> None:
        first_curve = _curve(
            "curve-1",
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)],
            is_closed=False,
        )
        second_curve = _curve(
            "curve-2",
            [(0.0, 1.0, 0.0), (1.0, 1.0, 0.0), (2.0, 1.0, 0.0)],
            is_closed=False,
        )

        preview = build_surface_preview_mesh(
            _surface([first_curve.id, second_curve.id]),
            [first_curve, second_curve],
        )

        assert preview is not None
        self.assertEqual(preview.vertices.shape, (6, 3))
        self.assertEqual(preview.faces.shape, (4, 3))
        self.assertTrue(np.all(preview.faces < len(preview.vertices)))

    def test_two_curves_resample_by_arc_length_and_preserve_open_endpoints(self) -> None:
        first_curve = _curve(
            "curve-1",
            [(0.0, 0.0, 0.0), (3.0, 0.0, 0.0)],
            is_closed=False,
        )
        second_curve = _curve(
            "curve-2",
            [
                (0.0, 1.0, 0.0),
                (1.0, 1.0, 0.0),
                (2.0, 1.0, 0.0),
                (3.0, 1.0, 0.0),
            ],
            is_closed=False,
        )

        preview = build_surface_preview_mesh(
            _surface([first_curve.id, second_curve.id]),
            [first_curve, second_curve],
        )

        assert preview is not None
        self.assertEqual(preview.vertices.shape, (8, 3))
        self.assertEqual(preview.faces.shape, (6, 3))
        result = build_surface_preview(
            _surface([first_curve.id, second_curve.id]),
            [first_curve, second_curve],
        )
        self.assertEqual(result.diagnostics["resampled_point_count"], 4)
        assert result.mesh is not None
        self.assertEqual(len(result.mesh.vertices[:4]), len(result.mesh.vertices[4:]))
        self.assertTrue(np.allclose(preview.vertices[0], [0.0, 0.0, 0.0]))
        self.assertTrue(np.allclose(preview.vertices[1], [1.0, 0.0, 0.0]))
        self.assertTrue(np.allclose(preview.vertices[3], [3.0, 0.0, 0.0]))

    def test_reversed_second_curve_reduces_pairing_distance(self) -> None:
        first_curve = _curve(
            "curve-1",
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)],
            is_closed=False,
        )
        second_curve = _curve(
            "curve-2",
            [(2.0, 1.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)],
            is_closed=False,
        )

        result = build_surface_preview(
            _surface([first_curve.id, second_curve.id]),
            [first_curve, second_curve],
        )

        self.assertTrue(result.preview_available)
        self.assertEqual(result.reason, "loft generated with reversed second curve")
        self.assertTrue(result.diagnostics["reversed_second_curve"])
        self.assertFalse(result.diagnostics["seam_shift_applied"])
        self.assertEqual(result.diagnostics["resampled_point_count"], 3)
        assert result.mesh is not None
        first_points = result.mesh.vertices[:3]
        paired_second_points = result.mesh.vertices[3:]
        original_second_points = second_curve.fitted_points
        direct_distance = float(np.mean(np.linalg.norm(first_points - original_second_points, axis=1)))
        paired_distance = float(np.mean(np.linalg.norm(first_points - paired_second_points, axis=1)))
        self.assertLess(paired_distance, direct_distance)
        self.assertTrue(np.allclose(paired_second_points[0], [0.0, 1.0, 0.0]))

    def test_closed_curve_seam_alignment_rotates_second_curve(self) -> None:
        first_curve = _curve(
            "curve-1",
            [
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (1.0, 1.0, 0.0),
                (0.0, 1.0, 0.0),
            ],
            is_closed=True,
        )
        second_curve = _curve(
            "curve-2",
            [
                (1.0, 1.0, 1.0),
                (0.0, 1.0, 1.0),
                (0.0, 0.0, 1.0),
                (1.0, 0.0, 1.0),
            ],
            is_closed=True,
        )

        result = build_surface_preview(
            _surface([first_curve.id, second_curve.id]),
            [first_curve, second_curve],
        )

        self.assertTrue(result.preview_available)
        self.assertEqual(result.reason, "loft generated with seam-aligned second curve")
        self.assertFalse(result.diagnostics["reversed_second_curve"])
        self.assertTrue(result.diagnostics["seam_shift_applied"])
        self.assertEqual(result.diagnostics["seam_shift_index"], 2)
        assert result.mesh is not None
        self.assertTrue(
            np.allclose(
                result.mesh.vertices[4:],
                [
                    [0.0, 0.0, 1.0],
                    [1.0, 0.0, 1.0],
                    [1.0, 1.0, 1.0],
                    [0.0, 1.0, 1.0],
                ],
            )
        )

    def test_degenerate_loft_triangles_are_skipped(self) -> None:
        first_curve = _curve(
            "curve-1",
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)],
            is_closed=False,
        )
        second_curve = _curve(
            "curve-2",
            [(0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (2.0, 1.0, 0.0)],
            is_closed=False,
        )

        result = build_surface_preview(
            _surface([first_curve.id, second_curve.id]),
            [first_curve, second_curve],
        )

        self.assertTrue(result.preview_available)
        assert result.mesh is not None
        self.assertLess(result.mesh.faces.shape[0], 4)
        self.assertGreater(result.mesh.faces.shape[0], 0)
        for face in result.mesh.faces:
            vertices = result.mesh.vertices[face]
            area = np.linalg.norm(np.cross(vertices[1] - vertices[0], vertices[2] - vertices[0])) * 0.5
            self.assertGreater(area, 1e-10)

    def test_loft_diagnostics_include_pair_distances_and_warning(self) -> None:
        first_curve = _curve(
            "curve-1",
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)],
            is_closed=False,
        )
        second_curve = _curve(
            "curve-2",
            [(0.0, 10.0, 0.0), (1.0, 10.0, 0.0)],
            is_closed=False,
        )

        result = build_surface_preview(
            _surface([first_curve.id, second_curve.id]),
            [first_curve, second_curve],
        )

        self.assertTrue(result.preview_available)
        self.assertEqual(result.warning, LOFT_PAIR_DISTANCE_WARNING)
        self.assertEqual(result.diagnostics["average_pair_distance"], 10.0)
        self.assertEqual(result.diagnostics["max_pair_distance"], 10.0)

    def test_closed_circle_loft_seam_alignment_avoids_obvious_twist(self) -> None:
        angles = np.linspace(0.0, 2.0 * np.pi, 12, endpoint=False)
        first_points = [
            (float(np.cos(angle)), float(np.sin(angle)), 0.0)
            for angle in angles
        ]
        shifted_points = first_points[4:] + first_points[:4]
        second_points = [
            (float(point[0]), float(point[1]), 1.0)
            for point in shifted_points
        ]
        first_curve = _curve("curve-1", first_points, is_closed=True)
        second_curve = _curve("curve-2", second_points, is_closed=True)

        result = build_surface_preview(
            _surface([first_curve.id, second_curve.id]),
            [first_curve, second_curve],
        )

        self.assertTrue(result.preview_available)
        self.assertTrue(result.diagnostics["seam_shift_applied"])
        assert result.mesh is not None
        first_ring = result.mesh.vertices[:12]
        second_ring = result.mesh.vertices[12:]
        self.assertTrue(np.allclose(first_ring[:, :2], second_ring[:, :2], atol=1e-8))
        self.assertTrue(np.allclose(second_ring[:, 2], 1.0))

    def test_invalid_or_missing_curves_return_none(self) -> None:
        open_curve = _curve(
            "curve-1",
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)],
            is_closed=False,
        )
        short_curve = _curve(
            "curve-2",
            [(0.0, 0.0, 0.0)],
            is_closed=True,
        )
        malformed_curve = _curve(
            "curve-3",
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0)],
            is_closed=True,
        )
        malformed_curve.fitted_points = np.asarray([0.0, 1.0, 2.0], dtype=float)

        self.assertIsNone(build_surface_preview_mesh(_surface([]), [open_curve]))
        self.assertIsNone(build_surface_preview_mesh(_surface(["missing"]), [open_curve]))
        self.assertIsNone(build_surface_preview_mesh(_surface([open_curve.id]), [open_curve]))
        self.assertIsNone(build_surface_preview_mesh(_surface([short_curve.id]), [short_curve]))
        self.assertIsNone(
            build_surface_preview_mesh(_surface([malformed_curve.id]), [malformed_curve])
        )

        missing_result = build_surface_preview(_surface(["missing"]), [open_curve])
        self.assertFalse(missing_result.preview_available)
        self.assertEqual(missing_result.reason, "missing source curve")
        open_result = build_surface_preview(_surface([open_curve.id]), [open_curve])
        self.assertEqual(open_result.reason, "single curve is not closed")
        short_result = build_surface_preview(_surface([short_curve.id]), [short_curve])
        self.assertEqual(short_result.reason, "curve has too few points")
        malformed_result = build_surface_preview(_surface([malformed_curve.id]), [malformed_curve])
        self.assertEqual(malformed_result.reason, "curve has invalid point data")

    def test_degenerate_closed_curve_is_rejected(self) -> None:
        degenerate_curve = _curve(
            "curve-1",
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)],
            is_closed=True,
        )

        result = build_surface_preview(_surface([degenerate_curve.id]), [degenerate_curve])

        self.assertFalse(result.preview_available)
        self.assertIsNone(result.mesh)
        self.assertEqual(result.reason, "curve is degenerate")

    def test_unsupported_curve_count_returns_clear_reason(self) -> None:
        curves = [
            _curve(f"curve-{index}", [(0.0, float(index), 0.0), (1.0, float(index), 0.0)], is_closed=False)
            for index in range(3)
        ]

        result = build_surface_preview(
            _surface([curve.id for curve in curves]),
            curves,
        )

        self.assertFalse(result.preview_available)
        self.assertIsNone(result.mesh)
        self.assertEqual(result.reason, "preview unavailable: unsupported curve count")

    def test_boundary_patch_rejects_open_curve(self) -> None:
        curve = _curve(
            "curve-open",
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0)],
            is_closed=False,
        )

        result = build_boundary_patch_preview(
            _surface([curve.id], preview_mode=BOUNDARY_PATCH),
            curve,
        )

        self.assertFalse(result.preview_available)
        self.assertIsNone(result.mesh)
        self.assertEqual(result.reason, "boundary patch requires one closed curve")

    def test_boundary_patch_accepts_closed_curve_with_planarity_diagnostics(self) -> None:
        curve = _curve(
            "curve-boundary",
            [
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (1.0, 1.0, 0.0),
                (0.0, 1.0, 0.0),
            ],
            is_closed=True,
        )

        result = build_surface_preview(
            _surface([curve.id], surface_type="preview_boundary_patch"),
            [curve],
        )

        self.assertTrue(result.preview_available)
        self.assertEqual(result.reason, "boundary patch preview generated")
        self.assertEqual(result.diagnostics["preview_mode"], BOUNDARY_PATCH)
        self.assertEqual(result.diagnostics["source_curve_count"], 1)
        self.assertEqual(result.diagnostics["input_point_count"], 4)
        self.assertEqual(result.diagnostics["planarity_error"], 0.0)
        self.assertEqual(result.diagnostics["triangulation_method"], "ear_clipping")
        self.assertIsInstance(result.mesh, SurfacePreviewMesh)
        assert result.mesh is not None
        self.assertEqual(result.mesh.vertices.shape, (4, 3))
        self.assertEqual(result.mesh.faces.shape, (2, 3))

    def test_four_curve_patch_rejects_wrong_curve_count(self) -> None:
        curves = [
            _curve("curve-a", [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)], is_closed=False),
            _curve("curve-b", [(1.0, 0.0, 0.0), (1.0, 1.0, 0.0)], is_closed=False),
            _curve("curve-c", [(0.0, 1.0, 0.0), (1.0, 1.0, 0.0)], is_closed=False),
        ]

        result = build_four_curve_patch_preview(
            _surface([curve.id for curve in curves], preview_mode=FOUR_CURVE_PATCH),
            curves,
        )

        self.assertFalse(result.preview_available)
        self.assertEqual(result.reason, "four-curve patch requires exactly four curves")

    def test_four_curve_patch_accepts_rectangular_input_and_creates_grid(self) -> None:
        curves = [
            _curve("bottom", [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)], is_closed=False),
            _curve("right", [(1.0, 0.0, 0.0), (1.0, 1.0, 0.0)], is_closed=False),
            _curve("top", [(0.0, 1.0, 0.0), (1.0, 1.0, 0.0)], is_closed=False),
            _curve("left", [(0.0, 0.0, 0.0), (0.0, 1.0, 0.0)], is_closed=False),
        ]

        result = build_surface_preview(
            _surface([curve.id for curve in curves], preview_mode=FOUR_CURVE_PATCH),
            curves,
        )

        self.assertTrue(result.preview_available)
        self.assertEqual(result.reason, "four-curve patch preview generated")
        self.assertEqual(result.warning, "Curve order inferred from scene order; inspect patch.")
        self.assertEqual(result.diagnostics["grid_u_count"], 2)
        self.assertEqual(result.diagnostics["grid_v_count"], 2)
        self.assertEqual(result.diagnostics["max_corner_gap"], 0.0)
        assert result.mesh is not None
        self.assertEqual(result.mesh.vertices.shape, (4, 3))
        self.assertEqual(result.mesh.faces.shape, (2, 3))

    def test_curve_network_patch_rejects_fewer_than_three_curves(self) -> None:
        curves = [
            _curve("curve-a", [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)], is_closed=False),
            _curve("curve-b", [(0.0, 1.0, 0.0), (1.0, 1.0, 0.0)], is_closed=False),
        ]

        result = build_curve_network_patch_preview(
            _surface([curve.id for curve in curves], preview_mode=CURVE_NETWORK_PATCH),
            curves,
        )

        self.assertFalse(result.preview_available)
        self.assertEqual(result.reason, "curve network patch requires at least three curves")

    def test_curve_network_patch_accepts_parallel_curves_and_creates_strips(self) -> None:
        curves = [
            _curve(
                f"curve-{index}",
                [(0.0, float(index), 0.0), (0.5, float(index), 0.0), (1.0, float(index), 0.0)],
                is_closed=False,
            )
            for index in range(3)
        ]

        result = build_surface_preview(
            _surface([curve.id for curve in curves], preview_mode=CURVE_NETWORK_PATCH),
            curves,
        )

        self.assertTrue(result.preview_available)
        self.assertEqual(result.reason, "curve network patch preview generated")
        self.assertEqual(result.diagnostics["preview_mode"], CURVE_NETWORK_PATCH)
        self.assertEqual(result.diagnostics["network_curve_count"], 3)
        self.assertEqual(result.diagnostics["strip_count"], 2)
        self.assertEqual(result.diagnostics["resampled_point_count"], 3)
        self.assertEqual(result.diagnostics["average_pair_distance"], 1.0)
        self.assertEqual(result.diagnostics["max_pair_distance"], 1.0)
        assert result.mesh is not None
        self.assertEqual(result.mesh.vertices.shape, (9, 3))
        self.assertEqual(result.mesh.faces.shape, (8, 3))

    def test_curve_network_patch_stores_spacing_warning(self) -> None:
        curves = [
            _curve("curve-a", [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)], is_closed=False),
            _curve("curve-b", [(0.0, 0.2, 0.0), (1.0, 0.2, 0.0)], is_closed=False),
            _curve("curve-c", [(0.0, 5.0, 0.0), (1.0, 5.0, 0.0)], is_closed=False),
        ]

        result = build_surface_preview(
            _surface([curve.id for curve in curves], preview_mode=CURVE_NETWORK_PATCH),
            curves,
        )

        self.assertTrue(result.preview_available)
        self.assertEqual(result.warning, "Curve network spacing varies heavily; inspect patch.")
        self.assertIn(
            "Curve network spacing varies heavily; inspect patch.",
            result.diagnostics["warnings"],
        )


if __name__ == "__main__":
    unittest.main()
