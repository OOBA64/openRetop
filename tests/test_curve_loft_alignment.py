from __future__ import annotations

import math
import unittest
from types import SimpleNamespace

import numpy as np

from openretop.application.brep_controller import _prepared_loft_source_curves
from openretop.curves.curve_state import StoredCurve
from openretop.geometry.curve_alignment import align_closed_points, align_open_points, polygon_normal
from openretop.geometry.curves import fit_smooth_polyline
from openretop.infrastructure.cad_adapter import PublicCadAdapter
from openretop.surfaces.loft_feature import LoftFeatureOptions

try:  # CAD kernel is optional; the tests that need it skip without it.
    import cadquery  # noqa: F401

    HAVE_CADQUERY = True
except ImportError:  # pragma: no cover
    HAVE_CADQUERY = False


def _ring(radius: float, z: float, count: int, *, start: float = 0.0, reverse: bool = False):
    angles = start + np.linspace(0.0, 2.0 * math.pi, count, endpoint=False)
    if reverse:
        angles = angles[::-1]
    points = np.column_stack([radius * np.cos(angles), radius * np.sin(angles), np.full(count, z)])
    return np.vstack([points, points[:1]])


def _curve(name: str, points: np.ndarray) -> StoredCurve:
    fit = fit_smooth_polyline(points)
    return StoredCurve(
        id=name,
        name=name,
        section_result_id="",
        plane_id="",
        original_points=fit.original_points,
        fitted_points=fit.fitted_points,
        mean_error=fit.mean_error,
        max_error=fit.max_error,
        is_closed=True,
    )


class AlignmentMathTests(unittest.TestCase):
    def test_polygon_normal_sign_follows_winding(self) -> None:
        ccw = _ring(5.0, 0.0, 12)[:-1]
        self.assertGreater(polygon_normal(ccw)[2], 0.0)
        self.assertLess(polygon_normal(ccw[::-1])[2], 0.0)

    def test_closed_ring_is_rewound_and_reseamed_to_the_reference(self) -> None:
        reference = _ring(10.0, 0.0, 40)
        other = _ring(7.0, 20.0, 55, start=2.0, reverse=True)

        aligned = align_closed_points(other, reference)

        self.assertGreater(polygon_normal(aligned[:-1])[2], 0.0)
        np.testing.assert_allclose(aligned[0], aligned[-1])
        start_angle = math.atan2(aligned[0, 1], aligned[0, 0])
        self.assertLess(abs(start_angle), 2.0 * math.pi / 55)  # near the reference seam at angle 0
        self.assertEqual(len(aligned), len(other))

    def test_open_curve_is_reversed_only_when_that_helps(self) -> None:
        reference = np.array([[0.0, 0, 0], [10.0, 0, 0]])
        same = np.array([[0.0, 1, 0], [10.0, 1, 0]])
        flipped = same[::-1].copy()
        np.testing.assert_allclose(align_open_points(same, reference), same)
        np.testing.assert_allclose(align_open_points(flipped, reference), same)


@unittest.skipUnless(HAVE_CADQUERY, "cadquery not installed")
class LoftAlignmentCadTests(unittest.TestCase):
    options = LoftFeatureOptions(source_curve_ids=["a", "b"])

    def _lateral_area(self, curves) -> float:
        import cadquery as cq

        result = PublicCadAdapter().build_loft(
            curves,
            SimpleNamespace(
                closed_profiles=True, cap_start=False, cap_end=False,
                create_solid_if_closed=False, ruled=False,
            ),
        )
        self.assertTrue(result.success, result.reason)
        faces = cq.Shape.cast(result.cad_object.wrapped).Faces()
        spline = [face for face in faces if face.geomType() == "BSPLINE"]
        self.assertTrue(spline, "loft must produce a NURBS (B-spline) surface, not planes")
        return sum(face.Area() for face in spline)

    def test_loft_of_mismatched_rings_is_a_clean_frustum(self) -> None:
        bottom = _curve("a", _ring(10.0, 0.0, 120))
        top = _curve("b", _ring(7.0, 20.0, 77, start=2.2, reverse=True))
        prepared = _prepared_loft_source_curves([bottom, top], self.options)

        area = self._lateral_area(prepared)

        slant = math.hypot(10.0 - 7.0, 20.0)
        expected = math.pi * (10.0 + 7.0) * slant
        self.assertAlmostEqual(area / expected, 1.0, delta=0.01)

    def test_section_curves_become_bspline_edges_not_polygons(self) -> None:
        import cadquery as cq

        wire = PublicCadAdapter().build_wire(_curve("a", _ring(10.0, 0.0, 200)))
        self.assertTrue(wire.success, wire.reason)
        edges = cq.Shape.cast(wire.cad_object.wrapped).Edges()
        self.assertEqual([edge.geomType() for edge in edges], ["BSPLINE"])
        self.assertAlmostEqual(edges[0].Length() / (2 * math.pi * 10.0), 1.0, delta=1e-3)


if __name__ == "__main__":
    unittest.main()
