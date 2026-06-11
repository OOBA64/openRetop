from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from surfaces.surface_state import (
    SurfaceCollection,
    SurfacePatch,
    add_surface,
    clear_surfaces_for_curve,
    get_active_surface,
    get_visible_surfaces,
    remove_surface,
    set_active_surface,
)


def _surface(
    surface_id: str,
    *,
    source_curve_ids: list[str] | None = None,
    visible: bool = True,
    selected: bool = False,
) -> SurfacePatch:
    return SurfacePatch(
        id=surface_id,
        name=f"Surface {surface_id}",
        source_curve_ids=source_curve_ids or ["curve-1"],
        surface_type="loft",
        visible=visible,
        selected=selected,
    )


class SurfaceStateTests(unittest.TestCase):
    def test_add_surface_sets_active_surface(self) -> None:
        collection = SurfaceCollection()
        surface = _surface("surface-1")

        returned = add_surface(collection, surface)

        self.assertIs(returned, collection)
        self.assertEqual(collection.surfaces, [surface])
        self.assertEqual(collection.active_surface_id, surface.id)
        self.assertTrue(surface.selected)

    def test_add_surface_rejects_duplicate_id(self) -> None:
        collection = SurfaceCollection()
        add_surface(collection, _surface("surface-1"))

        with self.assertRaises(ValueError) as context:
            add_surface(collection, _surface("surface-1"))

        self.assertIn("Surface already exists: surface-1", str(context.exception))

    def test_set_active_surface_updates_selection(self) -> None:
        collection = SurfaceCollection()
        first_surface = _surface("surface-1")
        second_surface = _surface("surface-2")
        add_surface(collection, first_surface)
        add_surface(collection, second_surface)

        set_active_surface(collection, second_surface.id)

        self.assertEqual(get_active_surface(collection), second_surface)
        self.assertFalse(first_surface.selected)
        self.assertTrue(second_surface.selected)

    def test_set_active_surface_rejects_missing_surface_id(self) -> None:
        collection = SurfaceCollection()
        add_surface(collection, _surface("surface-1"))

        with self.assertRaises(ValueError) as context:
            set_active_surface(collection, "missing-surface")

        self.assertIn("Surface not found: missing-surface", str(context.exception))

    def test_remove_active_surface_selects_next_surface(self) -> None:
        collection = SurfaceCollection()
        first_surface = _surface("surface-1")
        second_surface = _surface("surface-2")
        add_surface(collection, first_surface)
        add_surface(collection, second_surface)
        set_active_surface(collection, second_surface.id)

        remove_surface(collection, second_surface.id)

        self.assertEqual(collection.surfaces, [first_surface])
        self.assertEqual(collection.active_surface_id, first_surface.id)
        self.assertTrue(first_surface.selected)

    def test_remove_last_active_surface_clears_active_surface(self) -> None:
        collection = SurfaceCollection()
        surface = _surface("surface-1")
        add_surface(collection, surface)

        remove_surface(collection, surface.id)

        self.assertEqual(collection.surfaces, [])
        self.assertIsNone(collection.active_surface_id)

    def test_get_visible_surfaces_filters_hidden_surfaces(self) -> None:
        collection = SurfaceCollection()
        visible_surface = _surface("surface-1", visible=True)
        hidden_surface = _surface("surface-2", visible=False)
        add_surface(collection, visible_surface)
        add_surface(collection, hidden_surface)

        self.assertEqual(get_visible_surfaces(collection), [visible_surface])

    def test_clear_surfaces_for_deleted_curve_removes_linked_surfaces(self) -> None:
        collection = SurfaceCollection()
        first_surface = _surface("surface-1", source_curve_ids=["curve-1", "curve-2"])
        second_surface = _surface("surface-2", source_curve_ids=["curve-3"])
        add_surface(collection, first_surface)
        add_surface(collection, second_surface)

        clear_surfaces_for_curve(collection, "curve-1")

        self.assertEqual(collection.surfaces, [second_surface])

    def test_clear_surfaces_for_active_curve_selects_remaining_surface(self) -> None:
        collection = SurfaceCollection()
        first_surface = _surface("surface-1", source_curve_ids=["curve-1"])
        second_surface = _surface("surface-2", source_curve_ids=["curve-2"])
        add_surface(collection, first_surface)
        add_surface(collection, second_surface)

        clear_surfaces_for_curve(collection, "curve-1")

        self.assertEqual(collection.surfaces, [second_surface])
        self.assertEqual(collection.active_surface_id, second_surface.id)
        self.assertTrue(second_surface.selected)

    def test_clear_surfaces_for_unlinked_curve_leaves_collection_unchanged(self) -> None:
        collection = SurfaceCollection()
        surface = _surface("surface-1", source_curve_ids=["curve-1"])
        add_surface(collection, surface)

        clear_surfaces_for_curve(collection, "missing-curve")

        self.assertEqual(collection.surfaces, [surface])
        self.assertEqual(collection.active_surface_id, surface.id)
        self.assertTrue(surface.selected)

    def test_surface_metadata_uses_fresh_default_dict(self) -> None:
        surface = _surface("surface-1")
        other_surface = _surface("surface-2")

        surface.metadata["quality"] = "draft"

        self.assertEqual(other_surface.metadata, {})


if __name__ == "__main__":
    unittest.main()
