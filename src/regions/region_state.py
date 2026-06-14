"""State for transient mesh triangle region selection."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from mesh.adjacency import grow_connected_region
from mesh.triangle_mesh import TriangleMeshData


DEFAULT_REGION_THRESHOLD_DEGREES = 20.0
DEFAULT_REGION_MAX_TRIANGLES = 50_000


@dataclass
class RegionSelection:
    id: str
    name: str
    triangle_indices: tuple[int, ...]
    threshold_degrees: float = DEFAULT_REGION_THRESHOLD_DEGREES
    max_triangle_count: int = DEFAULT_REGION_MAX_TRIANGLES
    source_mesh_identifier: str = ""
    source_mesh_name: str = ""
    seed_triangle_index: int | None = None
    visible: bool = True
    selected: bool = True
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class RegionCollection:
    active_region: RegionSelection | None = None

    def clear(self) -> None:
        self.active_region = None

    def set_active(self, region: RegionSelection | None) -> None:
        self.active_region = region

    def set_visible(self, visible: bool) -> None:
        if self.active_region is not None:
            self.active_region.visible = bool(visible)


def create_region_selection(
    mesh: TriangleMeshData,
    seed_triangle_index: int | None,
    *,
    source_mesh_identifier: str = "",
    source_mesh_name: str = "",
    threshold_degrees: float = DEFAULT_REGION_THRESHOLD_DEGREES,
    max_triangle_count: int = DEFAULT_REGION_MAX_TRIANGLES,
    name: str = "Region 1",
) -> RegionSelection | None:
    result = grow_connected_region(
        mesh,
        seed_triangle_index,
        threshold_degrees=threshold_degrees,
        max_triangle_count=max_triangle_count,
    )
    if not result.triangle_indices:
        return None

    region = RegionSelection(
        id=f"region-{uuid4().hex}",
        name=name,
        triangle_indices=result.triangle_indices,
        threshold_degrees=result.threshold_degrees,
        max_triangle_count=result.max_triangle_count,
        source_mesh_identifier=str(source_mesh_identifier or ""),
        source_mesh_name=str(source_mesh_name or ""),
        seed_triangle_index=None if seed_triangle_index is None else int(seed_triangle_index),
        visible=True,
        selected=True,
        metadata={
            "threshold_degrees": result.threshold_degrees,
            "max_triangle_count": result.max_triangle_count,
            "seed_triangle_index": seed_triangle_index,
            "triangle_count": len(result.triangle_indices),
        },
    )
    return region


# TODO: add/subtract brush.
# TODO: paint region selection.
# TODO: boundary extraction.
# TODO: convert boundary to curve.
# TODO: curvature-based grow.
# TODO: patch fitting from region.
# TODO: auto face detection.
