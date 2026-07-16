from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from application.scene_labels import surface_display_label
from surfaces.brep_state import BrepSurfaceRecord


class SceneBrowserBrepLabelTests(unittest.TestCase):
    def test_region_plane_label_distinguishes_region_source(self) -> None:
        surface = BrepSurfaceRecord(
            id="brep-region",
            name="Region Plane 1",
            source_curve_ids=["curve-boundary"],
            brep_type="planar_face",
            backend="FakeCAD",
            metadata={"creation_type": "region_plane_fit_brep"},
        )

        self.assertEqual(
            surface_display_label(surface, "Surface 1"),
            "Region Plane 1 (region, planar)",
        )

    def test_curve_face_and_loft_labels_remain_distinct(self) -> None:
        curve_face = BrepSurfaceRecord(
            id="brep-face",
            name="BREP Face 1",
            source_curve_ids=["curve-a"],
            brep_type="planar_face",
            backend="FakeCAD",
        )
        loft = BrepSurfaceRecord(
            id="brep-loft",
            name="BREP Loft 1",
            source_curve_ids=["curve-a", "curve-b"],
            brep_type="loft_surface",
            backend="FakeCAD",
        )

        self.assertEqual(
            surface_display_label(curve_face, "Surface 1"),
            "BREP Face 1 (curve, planar)",
        )
        self.assertEqual(
            surface_display_label(loft, "Surface 2"),
            "BREP Loft 1 (loft)",
        )


if __name__ == "__main__":
    unittest.main()
