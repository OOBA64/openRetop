"""Shared UI-free support for V3 workflow controllers."""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from openretop.application.events import EventPublisher, SceneChangedEvent, StateChangedEvent
from openretop.application.results import (
    UIRequest,
    UIRequestKind,
    ViewportRequest,
    ViewportRequestKind,
)
from openretop.application.scene_ids import (
    NODE_MESH,
    region_node_id,
    section_plane_node_id,
    section_result_node_id,
)
from openretop.application.selection import SelectionSnapshot
from openretop.application.state import AppState

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
        for plane in state.section_collection.planes:
            plane.selected = plane.id in self.selected_plane_ids
        for result in state.section_collection.results:
            result.selected = result.id in self.selected_result_ids
        region = state.region_collection.active_region
        if region is not None:
            region.selected = self.region_selected


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
        if state.section_collection.active_result_id in state.section_collection.selected_result_ids:
            primary_id = section_result_node_id(state.section_collection.active_result_id)
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


__all__ = (
    "CallbackUndoPayload",
    "ControllerBase",
    "MODEL_SYNC_UI_REQUESTS",
    "MODEL_SYNC_VIEWPORT_REQUESTS",
    "SELECTION_SYNC_UI_REQUESTS",
    "SELECTION_SYNC_VIEWPORT_REQUESTS",
    "publish_scene_change",
)
