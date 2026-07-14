"""Authoritative UI-independent aggregate application state.

The V3 controllers coordinate mutable domain collections through this module.
Legacy ``app.*_state`` modules re-export these classes so existing imports keep
working while ownership moves inward.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from curves.curve_state import CurveCollection, StoredCurve
from geometry.curves import CurveFitResult
from geometry.sections import SectionResult
from mesh.display_proxy import DEFAULT_PROXY_QUALITY
from mesh.triangle_mesh import TriangleMeshData
from regions.region_state import RegionCollection
from sections.section_state import (
    SectionCollection,
    add_plane,
    create_default_section_plane,
)
from surfaces.brep_state import BrepSurfaceCollection
from surfaces.four_boundary_feature import FourBoundaryPatchFeatureCollection
from surfaces.loft_feature import LoftFeatureCollection
from surfaces.surface_state import SurfaceCollection


@dataclass
class MeshObjectState:
    """Selection-oriented state for the loaded mesh object."""

    source_mesh: TriangleMeshData
    display_mesh: TriangleMeshData
    file_path: Path | None
    name: str
    origin: np.ndarray
    location: np.ndarray
    rotation: np.ndarray
    scale: float = 1.0
    transform_matrix: np.ndarray | None = None
    source_triangle_count: int = 0
    display_triangle_count: int = 0
    display_proxy_enabled: bool = False
    display_reduction_percent: float = 0.0
    proxy_quality: str = DEFAULT_PROXY_QUALITY
    source_bounds_min: np.ndarray | None = None
    source_bounds_max: np.ndarray | None = None
    visible: bool = True


@dataclass
class ActiveTransformState:
    """Start values captured for one viewport transform interaction."""

    selected_item: str
    mode: str
    mouse_start: tuple[int, int]
    axis_constraint: str | None
    location: np.ndarray
    rotation: np.ndarray
    section_axis: str
    section_offset: float
    section_origin: np.ndarray = field(
        default_factory=lambda: np.asarray([0.0, 0.0, 0.0], dtype=float)
    )
    section_normal: np.ndarray = field(
        default_factory=lambda: np.asarray([0.0, 0.0, 1.0], dtype=float)
    )
    section_plane_id: str | None = None
    section_plane_name: str | None = None


def _default_section_collection() -> SectionCollection:
    collection = SectionCollection()
    add_plane(collection, create_default_section_plane())
    return collection


@dataclass
class AppState:
    """Own mutable application state that is independent from UI widgets."""

    mesh_object: MeshObjectState | None = None
    selected_item: str | None = None
    active_transform_mode: str | None = None
    active_transform_axis: str | None = None
    transform_state: ActiveTransformState | None = None
    section_result: SectionResult | None = None
    curve_results: list[CurveFitResult | StoredCurve] = field(default_factory=list)
    section_collection: SectionCollection = field(
        default_factory=_default_section_collection
    )
    curve_collection: CurveCollection = field(default_factory=CurveCollection)
    surface_collection: SurfaceCollection = field(default_factory=SurfaceCollection)
    brep_surface_collection: BrepSurfaceCollection = field(
        default_factory=BrepSurfaceCollection
    )
    loft_feature_collection: LoftFeatureCollection = field(
        default_factory=LoftFeatureCollection
    )
    four_boundary_feature_collection: FourBoundaryPatchFeatureCollection = field(
        default_factory=FourBoundaryPatchFeatureCollection
    )
    region_collection: RegionCollection = field(default_factory=RegionCollection)

    def clear_selection(self) -> None:
        self.selected_item = None
        self.active_transform_mode = None
        self.active_transform_axis = None
        self.transform_state = None
        self.section_collection.selected_plane_ids.clear()
        self.section_collection.selected_result_ids.clear()
        self.curve_collection.selected_curve_ids.clear()
        self.surface_collection.selected_surface_ids.clear()
        self.brep_surface_collection.selected_surface_ids.clear()
        for plane in self.section_collection.planes:
            plane.selected = False
        for result in self.section_collection.results:
            result.selected = False
        for curve in self.curve_collection.curves:
            curve.selected = False
        for surface in self.surface_collection.surfaces:
            surface.selected = False
        for surface in self.brep_surface_collection.surfaces:
            surface.selected = False
        region = self.region_collection.active_region
        if region is not None:
            region.selected = False

    def clear_sections(self) -> None:
        self.section_result = None
        self.curve_results = []
        self.section_collection.results = []
        self.section_collection.active_result_id = None
        self.section_collection.selected_result_ids.clear()
        self.curve_collection.curves = []
        self.curve_collection.active_curve_id = None
        self.curve_collection.selected_curve_ids.clear()
        self.surface_collection.surfaces = []
        self.surface_collection.active_surface_id = None
        self.surface_collection.selected_surface_ids.clear()
        self.brep_surface_collection.surfaces = []
        self.brep_surface_collection.active_surface_id = None
        self.brep_surface_collection.selected_surface_ids.clear()
        self.loft_feature_collection.features = []
        self.loft_feature_collection.active_feature_id = None
        self.four_boundary_feature_collection.features = []
        self.four_boundary_feature_collection.active_feature_id = None


__all__ = ("ActiveTransformState", "AppState", "MeshObjectState")
