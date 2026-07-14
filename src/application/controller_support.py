"""Shared UI-free support for V3 workflow controllers."""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from application.events import EventPublisher, SceneChangedEvent, StateChangedEvent
from application.results import (
    UIRequest,
    UIRequestKind,
    ViewportRequest,
    ViewportRequestKind,
)
from application.selection import SelectionSnapshot
from application.state import AppState
from curves.curve_state import StoredCurve, is_repaired_curve
from curves.manual_curve import is_manual_curve_like
from application.scene_ids import (
    CURVE_GROUP_MANUAL_ID,
    CURVE_GROUP_PROJECTED_ID,
    CURVE_GROUP_REBUILT_ID,
    CURVE_GROUP_REGION_BOUNDARIES_ID,
    CURVE_GROUP_REPAIRED_ID,
    NODE_MESH,
    curve_node_id,
    region_node_id,
    section_plane_node_id,
    section_result_node_id,
    surface_node_id,
)


MODEL_SYNC_VIEWPORT_REQUESTS = (
    ViewportRequest(ViewportRequestKind.REFRESH),
)
MODEL_SYNC_UI_REQUESTS = (
    UIRequest(UIRequestKind.REFRESH_SCENE_BROWSER),
    UIRequest(UIRequestKind.SYNC_WORKFLOW),
    UIRequest(UIRequestKind.REFRESH_ACTIONS),
)
SELECTION_SYNC_VIEWPORT_REQUESTS = MODEL_SYNC_VIEWPORT_REQUESTS
SELECTION_SYNC_UI_REQUESTS = MODEL_SYNC_UI_REQUESTS


@dataclass(slots=True)
class SelectionFamilySnapshot:
    """Exact cross-family selection/session state used by controller undo."""

    selected_item: str | None
    active_transform_mode: str | None
    active_transform_axis: str | None
    transform_state: object | None
    active_plane_id: str | None
    selected_plane_ids: set[str]
    active_result_id: str | None
    selected_result_ids: set[str]
    active_curve_id: str | None
    selected_curve_ids: set[str]
    active_preview_surface_id: str | None
    selected_preview_surface_ids: set[str]
    active_brep_surface_id: str | None
    selected_brep_surface_ids: set[str]
    region_selected: bool

    @classmethod
    def capture(cls, state: AppState) -> SelectionFamilySnapshot:
        region = state.region_collection.active_region
        return cls(
            selected_item=state.selected_item,
            active_transform_mode=state.active_transform_mode,
            active_transform_axis=state.active_transform_axis,
            transform_state=copy.deepcopy(state.transform_state),
            active_plane_id=state.section_collection.active_plane_id,
            selected_plane_ids=set(state.section_collection.selected_plane_ids),
            active_result_id=state.section_collection.active_result_id,
            selected_result_ids=set(state.section_collection.selected_result_ids),
            active_curve_id=state.curve_collection.active_curve_id,
            selected_curve_ids=set(state.curve_collection.selected_curve_ids),
            active_preview_surface_id=state.surface_collection.active_surface_id,
            selected_preview_surface_ids=set(
                state.surface_collection.selected_surface_ids
            ),
            active_brep_surface_id=state.brep_surface_collection.active_surface_id,
            selected_brep_surface_ids=set(
                state.brep_surface_collection.selected_surface_ids
            ),
            region_selected=bool(region is not None and region.selected),
        )

    def restore(self, state: AppState) -> None:
        state.selected_item = self.selected_item
        state.active_transform_mode = self.active_transform_mode
        state.active_transform_axis = self.active_transform_axis
        state.transform_state = copy.deepcopy(self.transform_state)
        state.section_collection.active_plane_id = self.active_plane_id
        state.section_collection.selected_plane_ids = set(self.selected_plane_ids)
        state.section_collection.active_result_id = self.active_result_id
        state.section_collection.selected_result_ids = set(self.selected_result_ids)
        state.curve_collection.active_curve_id = self.active_curve_id
        state.curve_collection.selected_curve_ids = set(self.selected_curve_ids)
        state.surface_collection.active_surface_id = self.active_preview_surface_id
        state.surface_collection.selected_surface_ids = set(
            self.selected_preview_surface_ids
        )
        state.brep_surface_collection.active_surface_id = self.active_brep_surface_id
        state.brep_surface_collection.selected_surface_ids = set(
            self.selected_brep_surface_ids
        )
        for plane in state.section_collection.planes:
            plane.selected = plane.id in self.selected_plane_ids
        for result in state.section_collection.results:
            result.selected = result.id in self.selected_result_ids
        for curve in state.curve_collection.curves:
            curve.selected = curve.id in self.selected_curve_ids
        for surface in state.surface_collection.surfaces:
            surface.selected = surface.id in self.selected_preview_surface_ids
        for surface in state.brep_surface_collection.surfaces:
            surface.selected = surface.id in self.selected_brep_surface_ids
        region = state.region_collection.active_region
        if region is not None:
            region.selected = self.region_selected


def select_surface_exclusively(
    state: AppState,
    surface_id: str,
    *,
    brep: bool,
) -> None:
    state.clear_selection()
    collection = (
        state.brep_surface_collection if brep else state.surface_collection
    )
    collection.active_surface_id = str(surface_id)
    collection.selected_surface_ids = {str(surface_id)}
    for surface in collection.surfaces:
        surface.selected = surface.id == str(surface_id)
    state.selected_item = "surface"


def selection_snapshot_for_state(state: AppState) -> SelectionSnapshot:
    selected_item = state.selected_item
    ids: list[str] = []
    primary_id: str | None = None
    if selected_item == "model" and state.mesh_object is not None:
        ids = [NODE_MESH]
    elif selected_item == "section_plane":
        ids = [
            section_plane_node_id(value)
            for value in state.section_collection.selected_plane_ids
        ]
        if state.section_collection.active_plane_id in state.section_collection.selected_plane_ids:
            primary_id = section_plane_node_id(state.section_collection.active_plane_id)
    elif selected_item == "section_result":
        ids = [
            section_result_node_id(value)
            for value in state.section_collection.selected_result_ids
        ]
        ids.extend(curve_node_id(value) for value in state.curve_collection.selected_curve_ids)
        if state.section_collection.active_result_id in state.section_collection.selected_result_ids:
            primary_id = section_result_node_id(state.section_collection.active_result_id)
    elif selected_item == "curve":
        ids = [curve_node_id(value) for value in state.curve_collection.selected_curve_ids]
        if state.curve_collection.active_curve_id in state.curve_collection.selected_curve_ids:
            primary_id = curve_node_id(state.curve_collection.active_curve_id)
    elif selected_item == "surface":
        ids = [surface_node_id(value) for value in state.surface_collection.selected_surface_ids]
        ids.extend(
            surface_node_id(value)
            for value in state.brep_surface_collection.selected_surface_ids
            if surface_node_id(value) not in ids
        )
        active_id = (
            state.surface_collection.active_surface_id
            or state.brep_surface_collection.active_surface_id
        )
        if active_id is not None and surface_node_id(active_id) in ids:
            primary_id = surface_node_id(active_id)
    elif selected_item == "region":
        region = state.region_collection.active_region
        if region is not None and region.selected:
            ids = [region_node_id(region.id)]
    return SelectionSnapshot.from_ids(ids, primary_id=primary_id)


@dataclass(slots=True)
class CallbackUndoPayload:
    """Task 75 undo payload implemented by two explicit callbacks."""

    name: str
    undo_action: Callable[[], None]
    redo_action: Callable[[], None]

    def __post_init__(self) -> None:
        self.name = str(self.name).strip()
        if not self.name:
            raise ValueError("Undo payload name must not be empty.")
        if not callable(self.undo_action) or not callable(self.redo_action):
            raise TypeError("Undo and redo actions must be callable.")

    def undo(self) -> None:
        self.undo_action()

    def redo(self) -> None:
        self.redo_action()


class ControllerBase:
    """Common explicit, rebindable state and event composition contract."""

    def __init__(
        self,
        state: AppState,
        events: EventPublisher | None = None,
    ) -> None:
        self._events = events if events is not None else EventPublisher()
        if not isinstance(self._events, EventPublisher):
            raise TypeError("events must be an EventPublisher.")
        self.rebind_state(state)

    @property
    def state(self) -> AppState:
        return self._state

    @property
    def events(self) -> EventPublisher:
        return self._events

    def rebind_state(self, state: AppState) -> None:
        if not isinstance(state, AppState):
            raise TypeError("state must be an AppState.")
        self._state = state

    def bind_state(self, state: AppState) -> None:
        """Compatibility spelling for composition roots that bind controllers."""

        self.rebind_state(state)


def publish_scene_change(
    events: EventPublisher,
    *,
    reason: str,
    object_ids: Iterable[str] = (),
    changed_fields: Iterable[str] = (),
) -> None:
    """Publish coherent scene/state notifications after a completed mutation."""

    normalized_ids = tuple(dict.fromkeys(str(value) for value in object_ids))
    normalized_fields = tuple(dict.fromkeys(str(value) for value in changed_fields))
    events.publish(SceneChangedEvent(reason=str(reason), object_ids=normalized_ids))
    if normalized_fields:
        events.publish(
            StateChangedEvent(
                reason=str(reason),
                changed_fields=normalized_fields,
            )
        )


def curve_creation_type(curve: StoredCurve) -> str:
    metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
    return str(metadata.get("creation_type", "")).strip().lower()


def is_projected_curve(curve: StoredCurve) -> bool:
    return curve_creation_type(curve) == "projected_curve"


def is_rebuilt_curve(curve: StoredCurve) -> bool:
    return curve_creation_type(curve) == "rebuilt_curve"


def is_region_boundary_curve(curve: StoredCurve) -> bool:
    metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
    return curve_creation_type(curve) == "region_boundary" or "source_region_id" in metadata


def curve_ids_for_group(state: AppState, group_id: str) -> tuple[str, ...]:
    """Resolve a stable scene curve-group ID without importing presentation."""

    curves = state.curve_collection.curves
    result_ids = {result.id for result in state.section_collection.results}
    if group_id == CURVE_GROUP_REPAIRED_ID:
        selected = (curve for curve in curves if is_repaired_curve(curve))
    elif group_id == CURVE_GROUP_PROJECTED_ID:
        selected = (curve for curve in curves if is_projected_curve(curve))
    elif group_id == CURVE_GROUP_REBUILT_ID:
        selected = (curve for curve in curves if is_rebuilt_curve(curve))
    elif group_id == CURVE_GROUP_REGION_BOUNDARIES_ID:
        selected = (curve for curve in curves if is_region_boundary_curve(curve))
    elif group_id == CURVE_GROUP_MANUAL_ID:
        selected = (curve for curve in curves if is_manual_curve_like(curve))
    elif group_id == "":
        selected = (
            curve
            for curve in curves
            if curve.section_result_id not in result_ids
            and not is_repaired_curve(curve)
            and not is_projected_curve(curve)
            and not is_rebuilt_curve(curve)
            and not is_region_boundary_curve(curve)
            and not is_manual_curve_like(curve)
        )
    else:
        selected = (
            curve
            for curve in curves
            if curve.section_result_id == group_id
            and not is_projected_curve(curve)
            and not is_rebuilt_curve(curve)
            and not is_region_boundary_curve(curve)
            and not is_manual_curve_like(curve)
        )
    return tuple(curve.id for curve in selected)


__all__ = (
    "CallbackUndoPayload",
    "ControllerBase",
    "MODEL_SYNC_UI_REQUESTS",
    "MODEL_SYNC_VIEWPORT_REQUESTS",
    "SELECTION_SYNC_UI_REQUESTS",
    "SELECTION_SYNC_VIEWPORT_REQUESTS",
    "curve_creation_type",
    "curve_ids_for_group",
    "is_projected_curve",
    "is_rebuilt_curve",
    "is_region_boundary_curve",
    "publish_scene_change",
)
