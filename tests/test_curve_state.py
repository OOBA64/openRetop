from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from curves.curve_state import (
    CurveCollection,
    StoredCurve,
    add_curve,
    clear_curves_for_plane,
    clear_curves_for_section_result,
    get_visible_curves,
    remove_curve,
    set_active_curve,
)


def _curve(
    curve_id: str,
    *,
    section_result_id: str = "section-result-1",
    plane_id: str = "plane-1",
    visible: bool = True,
) -> StoredCurve:
    points = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
        ],
        dtype=float,
    )
    return StoredCurve(
        id=curve_id,
        name=f"Curve {curve_id}",
        section_result_id=section_result_id,
        plane_id=plane_id,
        original_points=points,
        fitted_points=points.copy(),
        mean_error=0.0,
        max_error=0.0,
        is_closed=False,
        visible=visible,
    )


class CurveStateTests(unittest.TestCase):
    def test_add_curve_sets_active_curve(self) -> None:
        collection = CurveCollection()
        curve = _curve("curve-1")

        returned = add_curve(collection, curve)

        self.assertIs(returned, collection)
        self.assertEqual(collection.curves, [curve])
        self.assertEqual(collection.active_curve_id, curve.id)
        self.assertTrue(curve.selected)

    def test_remove_active_curve_selects_next_curve(self) -> None:
        collection = CurveCollection()
        first_curve = _curve("curve-1")
        second_curve = _curve("curve-2")
        add_curve(collection, first_curve)
        add_curve(collection, second_curve)
        set_active_curve(collection, second_curve.id)

        remove_curve(collection, second_curve.id)

        self.assertEqual(collection.curves, [first_curve])
        self.assertEqual(collection.active_curve_id, first_curve.id)
        self.assertTrue(first_curve.selected)

    def test_get_visible_curves_filters_hidden_curves(self) -> None:
        collection = CurveCollection()
        visible_curve = _curve("curve-1", visible=True)
        hidden_curve = _curve("curve-2", visible=False)
        add_curve(collection, visible_curve)
        add_curve(collection, hidden_curve)

        self.assertEqual(get_visible_curves(collection), [visible_curve])

    def test_clear_curves_for_section_result_leaves_other_results(self) -> None:
        collection = CurveCollection()
        first_curve = _curve("curve-1", section_result_id="section-result-1")
        second_curve = _curve("curve-2", section_result_id="section-result-2")
        add_curve(collection, first_curve)
        add_curve(collection, second_curve)

        clear_curves_for_section_result(collection, "section-result-1")

        self.assertEqual(collection.curves, [second_curve])

    def test_clear_curves_for_plane_leaves_other_planes(self) -> None:
        collection = CurveCollection()
        first_curve = _curve("curve-1", plane_id="plane-1")
        second_curve = _curve("curve-2", plane_id="plane-2")
        add_curve(collection, first_curve)
        add_curve(collection, second_curve)

        clear_curves_for_plane(collection, "plane-1")

        self.assertEqual(collection.curves, [second_curve])

    def test_multiple_section_results_keep_separate_curve_records(self) -> None:
        collection = CurveCollection()
        first_curve = _curve(
            "curve-1",
            section_result_id="section-result-1",
            plane_id="plane-1",
        )
        second_curve = _curve(
            "curve-2",
            section_result_id="section-result-2",
            plane_id="plane-2",
        )

        add_curve(collection, first_curve)
        add_curve(collection, second_curve)

        self.assertEqual(collection.curves, [first_curve, second_curve])
        self.assertEqual(get_visible_curves(collection), [first_curve, second_curve])

    def test_set_active_curve_rejects_missing_curve_id(self) -> None:
        collection = CurveCollection()
        add_curve(collection, _curve("curve-1"))

        with self.assertRaises(ValueError) as context:
            set_active_curve(collection, "missing-curve")

        self.assertIn("Curve not found: missing-curve", str(context.exception))

    def test_add_curve_rejects_duplicate_id(self) -> None:
        collection = CurveCollection()
        add_curve(collection, _curve("curve-1"))

        with self.assertRaises(ValueError) as context:
            add_curve(collection, _curve("curve-1"))

        self.assertIn("Curve already exists: curve-1", str(context.exception))


if __name__ == "__main__":
    unittest.main()
