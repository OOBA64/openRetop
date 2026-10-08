"""Fitting exact geometry to scan data (Track RE)."""

from openretop.fitting.primitives import (
    PRIMITIVE_KINDS,
    PrimitiveFit,
    classify_region,
    fit_cone,
    fit_cylinder,
    fit_plane,
    fit_primitive,
    fit_sphere,
    fit_torus,
    primitive_distance,
    primitive_normal,
)

__all__ = (
    "primitive_distance",
    "primitive_normal",
    "PRIMITIVE_KINDS",
    "PrimitiveFit",
    "classify_region",
    "fit_cone",
    "fit_cylinder",
    "fit_plane",
    "fit_primitive",
    "fit_sphere",
    "fit_torus",
)
