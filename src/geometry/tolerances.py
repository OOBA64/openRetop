"""Model tolerances derived from mesh size and length units."""

from __future__ import annotations

from geometry.units import DEFAULT_UNIT, unit_scale

# Relative to the mesh's largest extent, with a floor in millimetres so tiny
# meshes and unit-less test data still get a usable tolerance.
CURVE_FIT_RELATIVE = 5e-4
CURVE_FIT_FLOOR_MM = 0.005
POINT_MERGE_RELATIVE = 1e-6


# Distances below which curve endpoints are considered the same point, and the
# deviation allowed when thinning a curve; both in millimetres.
CURVE_JOIN_MM = 0.01
CURVE_SIMPLIFY_MM = 0.001


def curve_join_tolerance(units: str = DEFAULT_UNIT) -> float:
    return CURVE_JOIN_MM * unit_scale("mm", units)


def curve_simplify_tolerance(units: str = DEFAULT_UNIT) -> float:
    return CURVE_SIMPLIFY_MM * unit_scale("mm", units)


def curve_fit_tolerance(extent: float, units: str = DEFAULT_UNIT) -> float:
    """Maximum deviation allowed between a fitted section curve and its scan points."""

    floor = CURVE_FIT_FLOOR_MM * unit_scale("mm", units)
    return max(float(extent) * CURVE_FIT_RELATIVE, floor)
