"""Stable, toolkit-neutral labels for scene records."""

from __future__ import annotations

from application.controller_support import is_repaired_curve
from curves.manual_curve import is_manual_curve_like


def curve_display_label(curve: object, fallback_label: str = "Curve") -> str:
    label = str(getattr(curve, "name", "") or fallback_label)
    metadata = getattr(curve, "metadata", {})
    metadata = metadata if isinstance(metadata, dict) else {}
    creation = str(metadata.get("creation_type", "")).strip().lower()
    boundary = creation == "region_boundary" or "source_region_id" in metadata
    manual = is_manual_curve_like(curve)
    tags: list[str] = []
    if creation == "projected_curve":
        tags.append("projected")
        if _is_mesh_snapped(metadata, creation):
            tags.append("mesh")
    elif creation == "rebuilt_curve":
        tags.extend(("rebuilt", _curve_method(metadata)))
    elif boundary:
        tags.extend(("boundary", "closed" if bool(getattr(curve, "is_closed", False)) else "open"))
    elif manual:
        tags.extend(("mesh" if _is_mesh_snapped(metadata, creation) else "manual", _curve_method(metadata)))
    elif is_repaired_curve(curve):
        tags.append("repaired")
    if not manual and not boundary and creation != "rebuilt_curve" and bool(getattr(curve, "is_closed", False)):
        tags.append("closed")
    if not manual and bool(getattr(curve, "is_tiny_fragment", False)):
        tags.append("tiny")
    tags = list(dict.fromkeys(tags))[:2]
    return f"{label} ({', '.join(tags)})" if tags else label


def region_display_label(region: object, fallback_label: str = "Region") -> str:
    label = str(getattr(region, "name", "") or fallback_label)
    return f"{label} ({len(getattr(region, 'triangle_indices', ())):,} tris)"


def surface_display_label(surface: object, fallback_label: str = "Surface") -> str:
    label = str(getattr(surface, "name", "") or fallback_label)
    tag = surface_display_tag(surface)
    return f"{label} ({tag})" if tag else label


def surface_display_tag(surface: object) -> str:
    brep_type = str(getattr(surface, "brep_type", "")).strip().lower()
    metadata = getattr(surface, "metadata", {})
    metadata = metadata if isinstance(metadata, dict) else {}
    if brep_type == "planar_face":
        return "region, planar" if metadata.get("creation_type") == "region_plane_fit_brep" else "curve, planar"
    if brep_type == "loft_surface":
        return "editable, loft" if metadata.get("creation_type") == "editable_loft_feature" else "loft"
    if brep_type:
        return "BREP"
    preview_mode = str(metadata.get("preview_mode", "")).strip().lower()
    surface_type = str(getattr(surface, "surface_type", "")).strip().lower()
    tags = {
        "closed_curve_fill": "fill",
        "preview_fill": "fill",
        "two_curve_loft": "loft",
        "preview_loft": "loft",
        "mesh_conforming_loft": "conforming preview",
        "mesh_conforming_loft_preview": "conforming preview",
        "boundary_patch": "boundary patch",
        "preview_boundary_patch": "boundary patch",
        "four_curve_patch": "4-curve patch",
        "preview_four_curve_patch": "4-curve patch",
        "curve_network_patch": "network patch",
        "preview_curve_network_patch": "network patch",
    }
    return tags.get(preview_mode) or tags.get(surface_type, "")


def _curve_method(metadata: dict[str, object]) -> str:
    return "polyline" if str(metadata.get("curve_method", "catmull_rom")).strip().lower() == "polyline" else "smooth"


def _is_mesh_snapped(metadata: dict[str, object], creation: str) -> bool:
    return creation == "curve_on_mesh" or str(metadata.get("snap_mode", "")).strip().lower() == "mesh" or bool(metadata.get("snap_to_mesh"))


__all__ = (
    "curve_display_label",
    "region_display_label",
    "surface_display_label",
    "surface_display_tag",
)
