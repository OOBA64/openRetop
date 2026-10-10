"""P-04: the regions of a constrained sketch, picked by click, extruded by the kernel."""

from __future__ import annotations

import math
import unittest

try:
    import cadquery  # noqa: F401
    import OCP  # noqa: F401

    HAVE_KERNEL = True
except ImportError:  # pragma: no cover
    HAVE_KERNEL = False

from openretop.modeling.sketch2d import Sketch2D
from openretop.modeling.sketch_profiles import find_profiles

FRAME = {"origin": [0.0, 0.0, 0.0], "u": [1.0, 0.0, 0.0], "v": [0.0, 1.0, 0.0]}


def plate_with_holes(width: float = 100.0, height: float = 60.0, diameter: float = 8.0) -> tuple[Sketch2D, tuple[str, ...], list[str]]:
    sketch = Sketch2D()
    lines = sketch.add_rectangle((0.0, 0.0), (width, height))
    holes = [
        sketch.add_circle((x, y), diameter / 2)
        for x, y in ((10, 10), (width - 10, 10), (width - 10, height - 10), (10, height - 10))
    ]
    return sketch, lines, holes


def split_rectangle() -> Sketch2D:
    """A 10 x 6 rectangle with a line across it at x = 4 (the top and bottom split there)."""

    sketch = Sketch2D()
    a, b, c, d = (sketch.add_point(*xy) for xy in ((0, 0), (10, 0), (10, 6), (0, 6)))
    m, n = sketch.add_point(4, 0), sketch.add_point(4, 6)
    for start, end in ((a, m), (m, b), (b, c), (c, n), (n, d), (d, a), (m, n)):
        sketch.add_line(start, end)
    return sketch


class RegionTests(unittest.TestCase):
    def test_a_rectangle_is_one_region(self) -> None:
        sketch = Sketch2D()
        lines = sketch.add_rectangle((0, 0), (10, 5))
        profiles = find_profiles(sketch)
        (region,) = profiles.regions
        self.assertAlmostEqual(region.area, 50.0)
        self.assertEqual(region.key, "|".join(sorted(lines)))
        self.assertEqual(profiles.open_chains, [])

    def test_holes_are_islands_and_regions_of_their_own(self) -> None:
        sketch, lines, holes = plate_with_holes()
        profiles = find_profiles(sketch)
        self.assertEqual(len(profiles.regions), 5)
        plate = profiles.region("|".join(sorted(lines)))
        assert plate is not None
        self.assertEqual(sorted(plate.children), sorted(holes))
        self.assertTrue(all(profiles.region(hole).parent == plate.key for hole in holes))  # type: ignore[union-attr]
        # a click in the plate picks the plate; in a hole, the hole
        self.assertEqual(profiles.region_at((50.0, 30.0)).key, plate.key)  # type: ignore[union-attr]
        self.assertEqual(profiles.region_at((10.5, 10.5)).key, holes[0])  # type: ignore[union-attr]
        self.assertIsNone(profiles.region_at((200.0, 30.0)))

    def test_a_line_across_a_rectangle_makes_two_regions(self) -> None:
        profiles = find_profiles(split_rectangle())
        self.assertEqual(sorted(round(region.area, 6) for region in profiles.regions), [24.0, 36.0])
        self.assertTrue(all(region.parent is None for region in profiles.regions))
        self.assertAlmostEqual(profiles.region_at((2.0, 3.0)).area, 24.0)  # type: ignore[union-attr]

    def test_lines_and_fillet_arcs_close_a_loop(self) -> None:
        sketch = Sketch2D()
        r = 2.0
        p = [sketch.add_point(*xy) for xy in ((r, 0), (10 - r, 0), (10, r), (10, 6 - r), (10 - r, 6), (r, 6), (0, 6 - r), (0, r))]
        sketch.add_line(p[0], p[1])
        sketch.add_arc((10 - r, r), p[1], p[2])
        sketch.add_line(p[2], p[3])
        sketch.add_arc((10 - r, 6 - r), p[3], p[4])
        sketch.add_line(p[4], p[5])
        sketch.add_arc((r, 6 - r), p[5], p[6])
        sketch.add_line(p[6], p[7])
        sketch.add_arc((r, r), p[7], p[0])
        (region,) = find_profiles(sketch).regions
        self.assertAlmostEqual(region.area, 60.0 - (4 - math.pi) * r * r, delta=0.05)  # sampled arcs
        self.assertEqual([segment.kind for segment in region.outer.segments].count("arc"), 4)

    def test_points_held_together_by_a_constraint_join_the_loop(self) -> None:
        sketch = Sketch2D()
        sketch.add_line((0, 0), (10, 0))
        sketch.add_line((10, 0), (10, 5))
        sketch.add_line((10, 5), (0, 0.2))
        ends = list(sketch.points)
        # the last line's end was drawn near the first line's start, then constrained onto it
        self.assertTrue(sketch.constrain("coincident", ends[0], ends[-1]).ok)
        (region,) = find_profiles(sketch).regions
        self.assertAlmostEqual(region.area, 25.0, places=6)

    def test_construction_and_dangling_curves_enclose_nothing(self) -> None:
        sketch = Sketch2D()
        sketch.add_rectangle((0, 0), (10, 5))
        sketch.add_line((0, 0), (10, 5), construction=True)  # a diagonal for symmetry
        sketch.add_line((10, 5), (14, 8))  # sticks out of a corner
        profiles = find_profiles(sketch)
        self.assertEqual(len(profiles.regions), 1)
        self.assertEqual(len(profiles.open_chains), 1)
        self.assertEqual(len(profiles.all_loops()), 2)

    def test_region_keys_survive_a_dimension_change(self) -> None:
        sketch, lines, holes = plate_with_holes()
        keys = sorted(region.key for region in find_profiles(sketch).regions)
        width = sketch.constrain("distance", lines[0], value=100.0)
        self.assertTrue(sketch.set_value(width.constraint_id or "", 140.0).ok)
        self.assertEqual(sorted(region.key for region in find_profiles(sketch).regions), keys)

    def test_picking_regions_builds_the_loops_to_extrude(self) -> None:
        sketch, lines, holes = plate_with_holes()
        profiles = find_profiles(sketch)
        plate_key = "|".join(sorted(lines))
        self.assertEqual(len(profiles.loops_for([plate_key]) or []), 5)  # plate and its four holes
        self.assertEqual(len(profiles.loops_for([plate_key, holes[0]]) or []), 4)  # one hole filled
        self.assertEqual(len(profiles.loops_for([holes[1]]) or []), 1)  # just a disc
        self.assertIsNone(profiles.loops_for(["no such region"]))


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class ExtrudeRegionTests(unittest.TestCase):
    def volume(self, loops: list[dict[str, object]]) -> float:
        from openretop.cad_kernel import jobs

        result = jobs.extrude(FRAME, loops, [(0.0, 10.0)] * len(loops))
        self.assertTrue(result["solid"])
        return float(result["volume"])

    def test_the_plate_extrudes_with_its_holes_and_picked_ones_fill(self) -> None:
        sketch, lines, holes = plate_with_holes()
        profiles = find_profiles(sketch)
        hole_area = math.pi * 16.0
        plate_key = "|".join(sorted(lines))
        self.assertAlmostEqual(self.volume(profiles.all_loops()), (6000 - 4 * hole_area) * 10, delta=0.5)
        self.assertAlmostEqual(self.volume(profiles.loops_for([plate_key, holes[0]]) or []), (6000 - 3 * hole_area) * 10, delta=0.5)
        self.assertAlmostEqual(self.volume(profiles.loops_for([holes[2]]) or []), hole_area * 10, delta=0.05)

    def test_two_regions_side_by_side_extrude_as_one_block(self) -> None:
        profiles = find_profiles(split_rectangle())
        keys = [region.key for region in profiles.regions]
        self.assertEqual(len(keys), 2)
        self.assertAlmostEqual(self.volume(profiles.loops_for(keys) or []), 10 * 6 * 10, delta=0.01)
        self.assertAlmostEqual(self.volume(profiles.loops_for(keys[:1]) or []), profiles.regions[0].area * 10, delta=0.01)


if __name__ == "__main__":
    unittest.main()
