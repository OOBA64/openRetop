"""Central non-UI state for the openRetop application."""

from __future__ import annotations

from dataclasses import dataclass, field

from geometry.curves import CurveFitResult
from geometry.sections import SectionResult

from app.object_state import MeshObjectState
from app.transform_state import ActiveTransformState


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

    def clear_selection(self) -> None:
        self.selected_item = None
        self.active_transform_mode = None
        self.active_transform_axis = None
        self.transform_state = None

    def clear_sections(self) -> None:
        self.section_result = None
        self.curve_results = []
