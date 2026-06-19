from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from surfaces.brep_state import (
    BREP_TYPE_PLANAR_FACE,
    BREP_TYPE_UNKNOWN,
    BrepSurfaceCollection,
    BrepSurfaceRecord,
    add_brep_surface,
    clear_brep_surface_selection,
    get_active_brep_surface,
    get_visible_brep_surfaces,
    remove_brep_surface,
    set_active_brep_surface,
    set_selected_brep_surfaces,
)


def _brep_surface(
    surface_id: object,
    *,
    source_curve_ids: list[object] | None = None,
    visible: bool = True,
    selected: bool = False,
    brep_type: object = BREP_TYPE_PLANAR_FACE,
    backend: object = "mock",
) -> BrepSurfaceRecord:
    return BrepSurfaceRecord(
        id=surface_id,
        name=f"BREP Surface {surface_id}",
        source_curve_ids=source_curve_ids or ["curve-1"],
        brep_type=brep_type,
        backend=backend,
        visible=visible,
        selected=selected,
    )


class BrepStateTests(unittest.TestCase):
    def test_add_brep_surface_sets_active_surface(self) -> None:
        collection = BrepSurfaceCollection()
        surface = _brep_surface("brep-1")

        returned = add_brep_surface(collection, surface)

        self.assertIs(returned, collection)
        self.assertEqual(collection.surfaces, [surface])
        self.assertEqual(collection.active_surface_id, surface.id)
        self.assertEqual(collection.selected_surface_ids, {surface.id})
        self.assertTrue(surface.selected)

    def test_add_brep_surface_keeps_preview_collection_separate(self) -> None:
        collection = BrepSurfaceCollection()
        surface = _brep_surface("brep-1")

        add_brep_surface(collection, surface)

        self.assertEqual(collection.surfaces, [surface])
        self.assertIsInstance(collection, BrepSurfaceCollection)

    def test_add_brep_surface_normalizes_serializable_record_fields(self) -> None:
        collection = BrepSurfaceCollection()
        surface = _brep_surface(
            12,
            source_curve_ids=[1, "curve-2"],
            brep_type="not-a-known-type",
            backend=42,
        )

        add_brep_surface(collection, surface)

        self.assertEqual(surface.id, "12")
        self.assertEqual(surface.source_curve_ids, ["1", "curve-2"])
        self.assertEqual(surface.brep_type, BREP_TYPE_UNKNOWN)
        self.assertEqual(surface.backend, "42")

    def test_add_brep_surface_rejects_duplicate_id_after_normalization(self) -> None:
        collection = BrepSurfaceCollection()
        add_brep_surface(collection, _brep_surface("12"))

        with self.assertRaises(ValueError) as context:
            add_brep_surface(collection, _brep_surface(12))

        self.assertIn("BREP surface already exists: 12", str(context.exception))

    def test_set_active_brep_surface_updates_selection(self) -> None:
        collection = BrepSurfaceCollection()
        first_surface = _brep_surface("brep-1")
        second_surface = _brep_surface("brep-2")
        add_brep_surface(collection, first_surface)
        add_brep_surface(collection, second_surface)

        set_active_brep_surface(collection, second_surface.id)

        self.assertEqual(get_active_brep_surface(collection), second_surface)
        self.assertFalse(first_surface.selected)
        self.assertTrue(second_surface.selected)

    def test_set_active_brep_surface_rejects_missing_surface_id(self) -> None:
        collection = BrepSurfaceCollection()
        add_brep_surface(collection, _brep_surface("brep-1"))

        with self.assertRaises(ValueError) as context:
            set_active_brep_surface(collection, "missing-brep")

        self.assertIn("BREP surface not found: missing-brep", str(context.exception))

    def test_set_selected_brep_surfaces_supports_multi_selection(self) -> None:
        collection = BrepSurfaceCollection()
        first_surface = _brep_surface("brep-1")
        second_surface = _brep_surface("brep-2")
        add_brep_surface(collection, first_surface)
        add_brep_surface(collection, second_surface)

        set_selected_brep_surfaces(
            collection,
            [first_surface.id, second_surface.id],
            active_surface_id=second_surface.id,
        )

        self.assertEqual(
            collection.selected_surface_ids,
            {first_surface.id, second_surface.id},
        )
        self.assertEqual(collection.active_surface_id, second_surface.id)
        self.assertTrue(first_surface.selected)
        self.assertTrue(second_surface.selected)

    def test_set_selected_brep_surfaces_rejects_missing_ids(self) -> None:
        collection = BrepSurfaceCollection()
        add_brep_surface(collection, _brep_surface("brep-1"))

        with self.assertRaises(ValueError) as context:
            set_selected_brep_surfaces(collection, ["brep-1", "missing-brep"])

        self.assertIn("BREP surface not found: missing-brep", str(context.exception))

    def test_set_selected_brep_surfaces_requires_active_surface_selected(self) -> None:
        collection = BrepSurfaceCollection()
        add_brep_surface(collection, _brep_surface("brep-1"))
        add_brep_surface(collection, _brep_surface("brep-2"))

        with self.assertRaises(ValueError) as context:
            set_selected_brep_surfaces(
                collection,
                ["brep-1"],
                active_surface_id="brep-2",
            )

        self.assertIn(
            "Active BREP surface must be selected: brep-2",
            str(context.exception),
        )

    def test_remove_active_brep_surface_selects_next_surface(self) -> None:
        collection = BrepSurfaceCollection()
        first_surface = _brep_surface("brep-1")
        second_surface = _brep_surface("brep-2")
        add_brep_surface(collection, first_surface)
        add_brep_surface(collection, second_surface)
        set_active_brep_surface(collection, second_surface.id)

        remove_brep_surface(collection, second_surface.id)

        self.assertEqual(collection.surfaces, [first_surface])
        self.assertEqual(collection.active_surface_id, first_surface.id)
        self.assertEqual(collection.selected_surface_ids, {first_surface.id})
        self.assertTrue(first_surface.selected)

    def test_remove_last_active_brep_surface_clears_active_surface(self) -> None:
        collection = BrepSurfaceCollection()
        surface = _brep_surface("brep-1")
        add_brep_surface(collection, surface)

        remove_brep_surface(collection, surface.id)

        self.assertEqual(collection.surfaces, [])
        self.assertIsNone(collection.active_surface_id)
        self.assertEqual(collection.selected_surface_ids, set())

    def test_get_visible_brep_surfaces_filters_hidden_surfaces(self) -> None:
        collection = BrepSurfaceCollection()
        visible_surface = _brep_surface("brep-1", visible=True)
        hidden_surface = _brep_surface("brep-2", visible=False)
        add_brep_surface(collection, visible_surface)
        add_brep_surface(collection, hidden_surface)

        self.assertEqual(get_visible_brep_surfaces(collection), [visible_surface])

    def test_clear_brep_surface_selection_preserves_surface_records(self) -> None:
        collection = BrepSurfaceCollection()
        surface = _brep_surface("brep-1")
        add_brep_surface(collection, surface)

        clear_brep_surface_selection(collection)

        self.assertEqual(collection.surfaces, [surface])
        self.assertIsNone(collection.active_surface_id)
        self.assertEqual(collection.selected_surface_ids, set())
        self.assertFalse(surface.selected)

    def test_brep_surface_metadata_uses_fresh_default_dict(self) -> None:
        surface = _brep_surface("brep-1")
        other_surface = _brep_surface("brep-2")

        surface.metadata["quality"] = "draft"

        self.assertEqual(other_surface.metadata, {})


if __name__ == "__main__":
    unittest.main()
