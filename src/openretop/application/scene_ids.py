"""Stable scene-object identifiers shared by UI-independent controllers."""

from __future__ import annotations

NODE_SCENE = "scene"
NODE_EMPTY_SCENE = "empty_scene"
NODE_MESH = "model"
NODE_SECTION_PLANES = "section_planes"
NODE_SECTION_PLANE = "section_plane"
NODE_SECTION_RESULTS = "section_results"
NODE_SECTION_RESULT = "section_result"
NODE_REGIONS = "regions"
NODE_REGION = "region"


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


def region_node_id(region_id: object) -> str:
    return _child_node_id(NODE_REGION, region_id)


def region_id_from_node(node_id: str | None) -> str | None:
    return _object_id_from_node(node_id, NODE_REGION)


__all__ = tuple(
    name
    for name in globals()
    if not name.startswith("_")
    and (
        name.startswith("NODE_")
        or name.endswith("_node_id")
        or name.endswith("_id_from_node")
    )
)
