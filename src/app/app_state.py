"""Central non-UI state for the openRetop application."""

from __future__ import annotations

from dataclasses import dataclass, field

from curves.curve_state import CurveCollection, StoredCurve
from geometry.curves import CurveFitResult
from geometry.sections import SectionResult
from regions.region_state import RegionCollection

from app.object_state import MeshObjectState
from app.transform_state import ActiveTransformState
from sections.section_state import (
    SectionCollection,
    add_plane,
    create_default_section_plane,
)
from surfaces.brep_state import BrepSurfaceCollection
from surfaces.four_boundary_feature import FourBoundaryPatchFeatureCollection
from surfaces.loft_feature import LoftFeatureCollection
from surfaces.surface_state import SurfaceCollection


def _default_section_collection() -> SectionCollection:
    collection = SectionCollection()
    add_plane(collection, create_default_section_plane())
    return collection


@dataclass
class AppState:
    """Owns mutable application state that is independent from Tk widgets."""

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
