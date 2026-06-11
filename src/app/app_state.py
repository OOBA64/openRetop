"""Central non-UI state for the openRetop application."""

from __future__ import annotations

from dataclasses import dataclass, field

from geometry.curves import CurveFitResult
from geometry.sections import SectionResult

from app.object_state import MeshObjectState
from app.transform_state import ActiveTransformState
from sections.section_state import (
    SectionCollection,
    add_plane,
    create_default_section_plane,
)


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
    curve_results: list[CurveFitResult] = field(default_factory=list)
    section_collection: SectionCollection = field(
        default_factory=_default_section_collection
    )

    def clear_selection(self) -> None:
        self.selected_item = None
        self.active_transform_mode = None
        self.active_transform_axis = None
        self.transform_state = None

    def clear_sections(self) -> None:
        self.section_result = None
        self.curve_results = []
        self.section_collection.results = []
