from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from curves.manual_curve import (
    CURVE_POINT_CORNER,
    CURVE_POINT_SMOOTH,
    CURVE_POINT_SOURCE_LEGACY,
    CURVE_POINT_SOURCE_MANUAL,
    MANUAL_CURVE_METHOD_POLYLINE,
    ManualCurveControlDataV2,
    ManualCurvePoint,
)
from curves.manual_curve_session import ManualCurveSessionState


class ManualCurveSessionStateTests(unittest.TestCase):
    def test_defaults_are_valid(self) -> None:
        session = ManualCurveSessionState()

        session.validate_invariants()

        self.assertFalse(session.active)
        self.assertEqual(session.submode, "inactive")
        self.assertEqual(session.control_points, [])
        self.assertTrue(np.allclose(session.plane_normal, [0.0, 0.0, 1.0]))

    def test_reset_clears_all_transient_state(self) -> None:
        session = self._new_session()
        session.append_point([0.0, 0.0, 0.0], snapped=True)
        session.select_point(0)
        session.drag_candidate_index = 0
        session.drag_active = True
        session.set_preview(point=[1.0, 2.0, 3.0], valid=True, snaps_to_mesh=True)

        session.reset()

        session.validate_invariants()
        self.assertFalse(session.active)
        self.assertFalse(session.editing)
        self.assertEqual(session.control_points, [])
        self.assertEqual(session.snap_flags, [])
        self.assertEqual(session.snapped_point_count, 0)
        self.assertIsNone(session.selected_control_point_index)
        self.assertIsNone(session.preview_point)
        self.assertFalse(session.preview_valid)

    def test_begin_new_initializes_draw_submode_and_normalizes_plane(self) -> None:
        session = ManualCurveSessionState()

        session.begin_new_curve(
            plane_origin=[1.0, 2.0, 3.0],
            plane_normal=[0.0, 0.0, 5.0],
            plane_type="section_plane",
            plane_label="Section A",
            source_section_plane_id="plane-a",
        )

        self.assertTrue(session.active)
        self.assertFalse(session.editing)
        self.assertEqual(session.submode, "draw_add_points")
        self.assertTrue(session.placing_enabled)
        self.assertTrue(np.allclose(session.plane_normal, [0.0, 0.0, 1.0]))

    def test_begin_edit_loads_curve_and_snap_metadata(self) -> None:
        control_data = ManualCurveControlDataV2(
            points=[
                ManualCurvePoint(
                    position=[0.0, 0.0, 0.0],
                    point_type=CURVE_POINT_CORNER,
                    snap_triangle_index=7,
                    snap_normal=[0.0, 0.0, 1.0],
                    metadata={"point_type_source": CURVE_POINT_SOURCE_MANUAL},
                ),
                ManualCurvePoint(
                    position=[1.0, 0.0, 0.0],
                    metadata={"point_type_source": CURVE_POINT_SOURCE_LEGACY},
                ),
                ManualCurvePoint(position=[1.0, 1.0, 0.0]),
            ],
            is_closed=True,
            curve_method=MANUAL_CURVE_METHOD_POLYLINE,
            sample_count=64,
            corner_angle_threshold_degrees=120.0,
            preserve_corners=False,
            metadata={
                "smoothness": 6,
                "control_point_revision": 11,
                "corner_detection_revision": 9,
            },
        )
        session = ManualCurveSessionState()

        session.begin_edit_curve(
            control_data,
            curve_id="curve-a",
            metadata={
                "snap_to_mesh": True,
                "keep_curve_on_mesh": True,
                "snap_projection_distances": [0.1, 0.2, 0.3],
            },
        )

        session.validate_invariants()
        self.assertTrue(session.editing)
        self.assertEqual(session.edit_curve_id, "curve-a")
        self.assertEqual(session.submode, "edit_select")
        self.assertFalse(session.placing_enabled)
        self.assertEqual(session.curve_method, MANUAL_CURVE_METHOD_POLYLINE)
        self.assertEqual(session.sample_count, 64)
        self.assertEqual(session.smoothness, 6)
        self.assertEqual(session.control_point_revision, 11)
        self.assertEqual(session.corner_detection_revision, 9)
        self.assertEqual(session.point_type_sources[1], CURVE_POINT_SOURCE_LEGACY)
        self.assertEqual(session.snapped_point_count, 3)
        self.assertEqual(session.projection_distances, [0.1, 0.2, 0.3])

    def test_point_mutations_keep_parallel_arrays_aligned(self) -> None:
        session = self._new_session()
        session.append_point([0.0, 0.0, 0.0], snapped=True, triangle_index=1)
        session.append_point([2.0, 0.0, 0.0])
        inserted = session.insert_point(
            1,
            [1.0, 0.0, 0.0],
            point_type=CURVE_POINT_CORNER,
            point_type_source=CURVE_POINT_SOURCE_MANUAL,
        )
        session.move_point(inserted, [1.0, 1.0, 0.0], snapped=True)
        session.remove_point(0)

        session.validate_invariants()
        lengths = {
            len(session.control_points),
            len(session.point_types),
            len(session.point_type_sources),
            len(session.snap_flags),
            len(session.snap_triangle_indices),
            len(session.snap_normals),
            len(session.projection_distances),
        }
        self.assertEqual(lengths, {2})
        self.assertEqual(session.snapped_point_count, 1)

    def test_normalize_clears_invalid_indices_and_repairs_arrays(self) -> None:
        session = self._new_session()
        session.control_points = [np.asarray([0.0, 0.0, 0.0])]
        session.point_types = []
        session.snap_flags = [True, True]
        session.selected_control_point_index = 10
        session.hover_control_point_index = -1
        session.drag_candidate_index = 4
        session.drag_active = True

        session.normalize_parallel_arrays()

        session.validate_invariants()
        self.assertEqual(session.point_types, [CURVE_POINT_SMOOTH])
        self.assertEqual(session.snap_flags, [True])
        self.assertEqual(session.snapped_point_count, 1)
        self.assertIsNone(session.selected_control_point_index)
        self.assertIsNone(session.hover_control_point_index)
        self.assertIsNone(session.drag_candidate_index)
        self.assertFalse(session.drag_active)

    def test_validate_rejects_misaligned_parallel_arrays(self) -> None:
        session = self._new_session()
        session.append_point([0.0, 0.0, 0.0])
        session.point_types.clear()

        with self.assertRaises(ValueError):
            session.validate_invariants()

    def test_closing_requires_three_points(self) -> None:
        session = self._new_session()
        session.append_point([0.0, 0.0, 0.0])
        session.append_point([1.0, 0.0, 0.0])

        self.assertFalse(session.set_closed(True))
        self.assertFalse(session.is_closed)
        session.append_point([1.0, 1.0, 0.0])
        self.assertTrue(session.set_closed(True))
        self.assertTrue(session.is_closed)

    def test_non_finite_points_are_rejected(self) -> None:
        session = self._new_session()

        with self.assertRaises(ValueError):
            session.append_point([np.nan, 0.0, 0.0])

    def test_preview_clear_is_complete(self) -> None:
        session = self._new_session()
        session.set_preview(
            point=[1.0, 2.0, 3.0],
            valid=True,
            snaps_closed=True,
            snaps_to_mesh=True,
            triangle_index=8,
            normal=[0.0, 1.0, 0.0],
        )

        session.clear_preview()

        self.assertIsNone(session.preview_point)
        self.assertFalse(session.preview_valid)
        self.assertFalse(session.preview_snaps_closed)
        self.assertFalse(session.preview_snaps_to_mesh)
        self.assertIsNone(session.preview_triangle_index)
        self.assertIsNone(session.preview_normal)

    @staticmethod
    def _new_session() -> ManualCurveSessionState:
        session = ManualCurveSessionState()
        session.begin_new_curve(
            plane_origin=[0.0, 0.0, 0.0],
            plane_normal=[0.0, 0.0, 1.0],
        )
        return session


if __name__ == "__main__":
    unittest.main()
