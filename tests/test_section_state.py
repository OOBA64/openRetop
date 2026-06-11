from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from geometry.sections import SectionResult
from sections.section_state import (
    SectionCollection,
    SectionPlaneState,
    StoredSectionResult,
    add_plane,
    add_result,
    clear_results_for_plane,
    create_default_section_plane,
    get_active_plane,
    remove_plane,
    set_active_plane,
)


def _empty_result(axis: str = "Z", offset: float = 0.0) -> SectionResult:
    return SectionResult(axis=axis, offset=offset, polylines=tuple(), segment_count=0)


class SectionStateTests(unittest.TestCase):
    def test_default_section_plane_creation(self) -> None:
        plane = create_default_section_plane(axis="y", offset=1.25)

        self.assertTrue(plane.id.startswith("section-plane-"))
        self.assertEqual(plane.name, "Section Plane 1")
        self.assertEqual(plane.axis, "Y")
        self.assertEqual(plane.offset, 1.25)
        self.assertTrue(plane.visible)
        self.assertFalse(plane.selected)

    def test_default_section_plane_ids_are_unique(self) -> None:
        first_plane = create_default_section_plane()
        second_plane = create_default_section_plane()

        self.assertNotEqual(first_plane.id, second_plane.id)

    def test_adding_first_plane_sets_active_plane(self) -> None:
        collection = SectionCollection()
        plane = create_default_section_plane()

        returned = add_plane(collection, plane)

        self.assertIs(returned, collection)
        self.assertEqual(collection.planes, [plane])
        self.assertEqual(collection.active_plane_id, plane.id)
        self.assertIs(get_active_plane(collection), plane)
        self.assertTrue(plane.selected)

    def test_setting_active_plane_updates_selected_flags(self) -> None:
        collection = SectionCollection()
        first_plane = create_default_section_plane(axis="X")
        second_plane = create_default_section_plane(axis="Z")
        second_plane.name = "Section Plane 2"
        add_plane(collection, first_plane)
        add_plane(collection, second_plane)

        set_active_plane(collection, second_plane.id)

        self.assertIs(get_active_plane(collection), second_plane)
        self.assertFalse(first_plane.selected)
        self.assertTrue(second_plane.selected)

    def test_removing_active_plane_selects_next_available_plane(self) -> None:
        collection = SectionCollection()
        first_plane = create_default_section_plane(axis="X")
        second_plane = create_default_section_plane(axis="Y")
        add_plane(collection, first_plane)
        add_plane(collection, second_plane)
        set_active_plane(collection, second_plane.id)

        remove_plane(collection, second_plane.id)

        self.assertEqual(collection.planes, [first_plane])
        self.assertIs(get_active_plane(collection), first_plane)
        self.assertTrue(first_plane.selected)

    def test_removing_last_active_plane_clears_active_plane(self) -> None:
        collection = SectionCollection()
        plane = create_default_section_plane()
        add_plane(collection, plane)

        remove_plane(collection, plane.id)

        self.assertEqual(collection.planes, [])
        self.assertIsNone(collection.active_plane_id)
        self.assertIsNone(get_active_plane(collection))

    def test_result_stores_plane_id_axis_and_offset(self) -> None:
        collection = SectionCollection()
        plane = create_default_section_plane(axis="X", offset=2.5)
        add_plane(collection, plane)
        section_result = _empty_result(axis="X", offset=2.5)
        stored_result = StoredSectionResult(
            id="result-1",
            name="Section 1",
            plane_id=plane.id,
            axis="x",
            offset=2.5,
            result=section_result,
        )

        add_result(collection, stored_result)

        self.assertEqual(collection.results, [stored_result])
        self.assertEqual(stored_result.plane_id, plane.id)
        self.assertEqual(stored_result.axis, "X")
        self.assertEqual(stored_result.offset, 2.5)
        self.assertIs(stored_result.result, section_result)

    def test_clearing_results_for_plane_leaves_other_plane_results(self) -> None:
        collection = SectionCollection()
        first_plane = create_default_section_plane(axis="X")
        second_plane = create_default_section_plane(axis="Y")
        add_plane(collection, first_plane)
        add_plane(collection, second_plane)
        first_result = StoredSectionResult(
            id="result-1",
            name="Section 1",
            plane_id=first_plane.id,
            axis="X",
            offset=0.0,
            result=_empty_result(axis="X"),
        )
        second_result = StoredSectionResult(
            id="result-2",
            name="Section 2",
            plane_id=second_plane.id,
            axis="Y",
            offset=1.0,
            result=_empty_result(axis="Y", offset=1.0),
        )
        add_result(collection, first_result)
        add_result(collection, second_result)

        clear_results_for_plane(collection, first_plane.id)

        self.assertEqual(collection.results, [second_result])

    def test_invalid_active_plane_id_raises_clear_error(self) -> None:
        collection = SectionCollection()
        add_plane(collection, create_default_section_plane())

        with self.assertRaises(ValueError) as context:
            set_active_plane(collection, "missing-plane")

        self.assertIn("Section plane not found: missing-plane", str(context.exception))

    def test_add_result_rejects_missing_plane_id(self) -> None:
        collection = SectionCollection()
        stored_result = StoredSectionResult(
            id="result-1",
            name="Section 1",
            plane_id="missing-plane",
            axis="Z",
            offset=0.0,
            result=_empty_result(),
        )

        with self.assertRaises(ValueError) as context:
            add_result(collection, stored_result)

        self.assertIn("Section plane not found: missing-plane", str(context.exception))

    def test_add_plane_rejects_duplicate_id(self) -> None:
        collection = SectionCollection()
        plane = create_default_section_plane()
        duplicate = SectionPlaneState(
            id=plane.id,
            name="Duplicate",
            axis="Z",
            offset=0.0,
        )
        add_plane(collection, plane)

        with self.assertRaises(ValueError) as context:
            add_plane(collection, duplicate)

        self.assertIn(f"Section plane already exists: {plane.id}", str(context.exception))


if __name__ == "__main__":
    unittest.main()
