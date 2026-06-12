"""Surface state models."""

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
from surfaces.surface_preview import SurfacePreviewMesh, build_surface_preview_mesh

__all__ = [
    "SurfaceCollection",
    "SurfacePatch",
    "SurfacePreviewMesh",
    "add_surface",
    "build_surface_preview_mesh",
    "clear_surfaces_for_curve",
    "get_active_surface",
    "get_visible_surfaces",
    "remove_surface",
    "set_active_surface",
]
