"""Stable scene-object identifiers shared by UI-independent controllers."""

from __future__ import annotations


NODE_SCENE = "scene"
NODE_EMPTY_SCENE = "empty_scene"
NODE_MESH = "model"
NODE_SECTION_PLANES = "section_planes"
NODE_SECTION_PLANE = "section_plane"
NODE_SECTION_RESULTS = "section_results"
NODE_SECTION_RESULT = "section_result"
NODE_CURVES = "curves"
NODE_CURVE = "curve"
NODE_CURVE_GROUP = "curve_group"
NODE_CURVE_GROUP_UNASSIGNED = f"{NODE_CURVE_GROUP}:unassigned"
NODE_CURVE_GROUP_PROJECTED = f"{NODE_CURVE_GROUP}:projected"
NODE_CURVE_GROUP_REBUILT = f"{NODE_CURVE_GROUP}:rebuilt"
NODE_CURVE_GROUP_REGION_BOUNDARIES = f"{NODE_CURVE_GROUP}:region_boundaries"
NODE_CURVE_GROUP_REPAIRED = f"{NODE_CURVE_GROUP}:repaired"
NODE_CURVE_GROUP_MANUAL = f"{NODE_CURVE_GROUP}:manual"
CURVE_GROUP_PROJECTED_ID = "__projected_curves__"
CURVE_GROUP_REBUILT_ID = "__rebuilt_curves__"
CURVE_GROUP_REGION_BOUNDARIES_ID = "__region_boundary_curves__"
CURVE_GROUP_REPAIRED_ID = "__repaired_curves__"
CURVE_GROUP_MANUAL_ID = "__manual_curves__"
NODE_SURFACES = "surfaces"
NODE_BREP_SURFACES = "brep_surfaces"
NODE_SURFACE = "surface"
NODE_REGIONS = "regions"
NODE_REGION = "region"
NODE_FEATURES = "features"
NODE_LOFT_FEATURE = "loft_feature"
NODE_FOUR_BOUNDARY_FEATURE = "four_boundary_feature"


def _child_node_id(prefix: str, object_id: object) -> str:
    value = str(object_id)
    if not value:
        raise ValueError("Scene object IDs must not be empty.")
    return f"{prefix}:{value}"


def _object_id_from_node(node_id: str | None, prefix: str) -> str | None:
    if node_id is None:
        return None
    marker = f"{prefix}:"
    value = str(node_id)
    if not value.startswith(marker):
        return None
    object_id = value[len(marker) :]
    return object_id or None


def section_plane_node_id(plane_id: object) -> str:
    return _child_node_id(NODE_SECTION_PLANE, plane_id)


def section_plane_id_from_node(node_id: str | None) -> str | None:
    return _object_id_from_node(node_id, NODE_SECTION_PLANE)


def section_result_node_id(result_id: object) -> str:
    return _child_node_id(NODE_SECTION_RESULT, result_id)


def section_result_id_from_node(node_id: str | None) -> str | None:
    return _object_id_from_node(node_id, NODE_SECTION_RESULT)


def curve_node_id(curve_id: object) -> str:
    return _child_node_id(NODE_CURVE, curve_id)


def curve_id_from_node(node_id: str | None) -> str | None:
    return _object_id_from_node(node_id, NODE_CURVE)


def curve_group_node_id(section_result_id: object) -> str:
    return _child_node_id(NODE_CURVE_GROUP, section_result_id)


def curve_group_id_from_node(node_id: str | None) -> str | None:
    if node_id is None:
        return None
    special_groups = {
        NODE_CURVE_GROUP_UNASSIGNED: "",
        NODE_CURVE_GROUP_PROJECTED: CURVE_GROUP_PROJECTED_ID,
        NODE_CURVE_GROUP_REBUILT: CURVE_GROUP_REBUILT_ID,
        NODE_CURVE_GROUP_REGION_BOUNDARIES: CURVE_GROUP_REGION_BOUNDARIES_ID,
        NODE_CURVE_GROUP_REPAIRED: CURVE_GROUP_REPAIRED_ID,
        NODE_CURVE_GROUP_MANUAL: CURVE_GROUP_MANUAL_ID,
    }
    if node_id in special_groups:
        return special_groups[node_id]
    return _object_id_from_node(node_id, NODE_CURVE_GROUP)


def surface_node_id(surface_id: object) -> str:
    return _child_node_id(NODE_SURFACE, surface_id)


def surface_id_from_node(node_id: str | None) -> str | None:
    return _object_id_from_node(node_id, NODE_SURFACE)


def region_node_id(region_id: object) -> str:
    return _child_node_id(NODE_REGION, region_id)


def region_id_from_node(node_id: str | None) -> str | None:
    return _object_id_from_node(node_id, NODE_REGION)


def loft_feature_node_id(feature_id: object) -> str:
    return _child_node_id(NODE_LOFT_FEATURE, feature_id)


def loft_feature_id_from_node(node_id: str | None) -> str | None:
    return _object_id_from_node(node_id, NODE_LOFT_FEATURE)


def four_boundary_feature_node_id(feature_id: object) -> str:
    return _child_node_id(NODE_FOUR_BOUNDARY_FEATURE, feature_id)


def four_boundary_feature_id_from_node(node_id: str | None) -> str | None:
    return _object_id_from_node(node_id, NODE_FOUR_BOUNDARY_FEATURE)


__all__ = tuple(
    name
    for name in globals()
    if not name.startswith("_")
    and (
        name.startswith("NODE_")
        or name.startswith("CURVE_GROUP_")
        or name.endswith("_node_id")
        or name.endswith("_id_from_node")
    )
)
