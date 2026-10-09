"""UI-independent scene naming and deletion for the scan-side objects: section planes, section
results and the region selection. (Model surfaces, bodies and sketch curves belong to the
modelling controller.)"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from openretop.application.controller_support import (
    MODEL_SYNC_UI_REQUESTS,
    MODEL_SYNC_VIEWPORT_REQUESTS,
    CallbackUndoPayload,
    ControllerBase,
    publish_scene_change,
)
from openretop.application.events import SelectionChangedEvent
from openretop.application.results import CommandResult
from openretop.application.scene_ids import (
    NODE_MESH,
    NODE_REGIONS,
    NODE_SECTION_PLANES,
    NODE_SECTION_RESULTS,
    region_id_from_node,
    region_node_id,
    section_plane_id_from_node,
    section_plane_node_id,
    section_result_id_from_node,
    section_result_node_id,
)
from openretop.application.selection import SelectionSnapshot
from openretop.application.selection_controller import (
    SELECT_SECTION_PLANE,
    SELECT_SECTION_RESULT,
    SelectionController,
)
from openretop.application.state import AppState
from openretop.sections.section_state import (
    add_plane,
    clear_plane_selection,
    clear_result_selection,
    create_default_section_plane,
    set_active_plane,
    set_active_result,
)


@dataclass(frozen=True, slots=True)
class SceneDeleteTargets:
    section_plane_ids: tuple[str, ...] = ()
    section_result_ids: tuple[str, ...] = ()
    region_ids: tuple[str, ...] = ()

    @property
    def deleted_count(self) -> int:
        return len(self.section_plane_ids) + len(self.section_result_ids) + len(self.region_ids)

    def as_metadata(self) -> Mapping[str, object]:
        return {
            "removed_section_plane_ids": self.section_plane_ids,
            "removed_section_result_ids": self.section_result_ids,
            "removed_region_ids": self.region_ids,
        }


@dataclass(slots=True)
class _SceneStateSnapshot:
    selected_item: str | None
    active_transform_mode: str | None
    active_transform_axis: str | None
    transform_state: object | None
    section_result: object | None
    section_collection: object
    region_collection: object

    @classmethod
    def capture(cls, state: AppState) -> _SceneStateSnapshot:
        return cls(
            selected_item=state.selected_item,
            active_transform_mode=state.active_transform_mode,
            active_transform_axis=state.active_transform_axis,
            transform_state=copy.deepcopy(state.transform_state),
            section_result=copy.deepcopy(state.section_result),
            section_collection=copy.deepcopy(state.section_collection),
            region_collection=copy.deepcopy(state.region_collection),
        )

    def restore(self, state: AppState) -> None:
        state.selected_item = self.selected_item
        state.active_transform_mode = self.active_transform_mode
        state.active_transform_axis = self.active_transform_axis
        state.transform_state = copy.deepcopy(self.transform_state)
        state.section_result = copy.deepcopy(self.section_result)
        state.section_collection = copy.deepcopy(self.section_collection)  # type: ignore[assignment]
        state.region_collection = copy.deepcopy(self.region_collection)  # type: ignore[assignment]


class SceneController(ControllerBase):
    """Coordinate scene record naming and deletion."""

    def rename(self, node_id: str, new_name: object) -> CommandResult:
        normalized_name = str(new_name).strip()
        if not normalized_name:
            return CommandResult.failure("Name cannot be empty.", status="Name cannot be empty")
        owner = self._name_owner(self.state, str(node_id))
        if owner is None:
            return CommandResult.failure("No renameable scene object was found.", status="No renameable selection")
        old_name = str(owner.name)
        if old_name == normalized_name:
            return CommandResult.ok(status=f"Selected: {old_name}")
        target_state = self.state
        target_node_id = str(node_id)
        owner.name = normalized_name
        publish_scene_change(self.events, reason="scene_object_renamed", object_ids=(target_node_id,), changed_fields=("name",))
        undo_payload = CallbackUndoPayload(
            name=self._rename_command_name(target_node_id),
            undo_action=lambda: self._restore_name(target_state, target_node_id, old_name, reason="rename_undo"),
            redo_action=lambda: self._restore_name(target_state, target_node_id, normalized_name, reason="rename_redo"),
        )
        return CommandResult.ok(
            status=f"Selected: {normalized_name}",
            changed=True,
            dirty=region_id_from_node(target_node_id) is None,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=undo_payload,
            metadata={"object_ids": (target_node_id,), "old_name": old_name, "new_name": normalized_name},
        )

    def delete(self, node_ids: Iterable[str]) -> CommandResult:
        requested = tuple(dict.fromkeys(str(value) for value in node_ids if str(value)))
        if not requested:
            return CommandResult.failure("No selection.", status="No selection")
        if NODE_MESH in requested:
            return CommandResult.failure(
                "Mesh deletion requires the presentation confirmation workflow.",
                status="Mesh deletion requires confirmation",
                metadata={"requires_mesh_confirmation": True},
            )
        targets = self.delete_targets(requested)
        if targets.deleted_count == 0:
            return CommandResult.failure("No deletable scene object was found.", status="No deletable selection")

        target_state = self.state
        before_selection = self._selection_snapshot(target_state)
        before = _SceneStateSnapshot.capture(target_state)
        self._apply_delete_targets(target_state, targets)
        self._select_delete_fallback(target_state, targets)
        after = _SceneStateSnapshot.capture(target_state)
        after_selection = self._selection_snapshot(target_state)
        affected_node_ids = self._node_ids_for_targets(targets)
        publish_scene_change(self.events, reason="scene_objects_deleted", object_ids=affected_node_ids, changed_fields=("scene", "selection"))
        if before_selection != after_selection:
            self.events.publish(SelectionChangedEvent(after_selection, reason="delete_fallback"))
        undo_payload = CallbackUndoPayload(
            name="Delete Region" if targets.region_ids and targets.deleted_count == 1 else "Delete Objects",
            undo_action=lambda: self._restore_scene_state(target_state, before, affected_node_ids, reason="delete_undo"),
            redo_action=lambda: self._restore_scene_state(target_state, after, affected_node_ids, reason="delete_redo"),
        )
        count = targets.deleted_count
        only_regions = bool(targets.region_ids) and count == len(targets.region_ids)
        status = "Region deleted." if count == 1 and targets.region_ids else "Deleted selected object" if count == 1 else f"Deleted {count} selected objects"
        return CommandResult.ok(
            status=status,
            changed=True,
            dirty=not only_regions,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=undo_payload,
            metadata={**targets.as_metadata(), "object_ids": affected_node_ids, "selection": after_selection},
        )

    def delete_targets(self, node_ids: Iterable[str]) -> SceneDeleteTargets:
        state = self.state
        plane_ids: set[str] = set()
        result_ids: set[str] = set()
        region_ids: set[str] = set()
        for node_id in tuple(dict.fromkeys(str(value) for value in node_ids)):
            if node_id == NODE_SECTION_PLANES:
                plane_ids.update(plane.id for plane in state.section_collection.planes)
            elif (plane_id := section_plane_id_from_node(node_id)) is not None:
                plane_ids.add(plane_id)
            elif node_id == NODE_SECTION_RESULTS:
                result_ids.update(result.id for result in state.section_collection.results)
            elif (result_id := section_result_id_from_node(node_id)) is not None:
                result_ids.add(result_id)
            elif node_id == NODE_REGIONS:
                region = state.region_collection.active_region
                if region is not None:
                    region_ids.add(region.id)
            elif (region_id := region_id_from_node(node_id)) is not None:
                region_ids.add(region_id)
        plane_ids.intersection_update(plane.id for plane in state.section_collection.planes)
        result_ids.update(result.id for result in state.section_collection.results if result.plane_id in plane_ids)
        result_ids.intersection_update(result.id for result in state.section_collection.results)
        region = state.region_collection.active_region
        region_ids.intersection_update(set() if region is None else {region.id})
        return SceneDeleteTargets(
            section_plane_ids=tuple(sorted(plane_ids)),
            section_result_ids=tuple(sorted(result_ids)),
            region_ids=tuple(sorted(region_ids)),
        )

    def _apply_delete_targets(self, state: AppState, targets: SceneDeleteTargets) -> None:
        plane_ids = set(targets.section_plane_ids)
        result_ids = set(targets.section_result_ids)
        region = state.region_collection.active_region
        if region is not None and region.id in set(targets.region_ids):
            state.region_collection.clear()
        collection = state.section_collection
        collection.results = [result for result in collection.results if result.id not in result_ids and result.plane_id not in plane_ids]
        remaining_results = {result.id for result in collection.results}
        collection.selected_result_ids.intersection_update(remaining_results)
        if collection.active_result_id not in remaining_results:
            collection.active_result_id = None
        for result in collection.results:
            result.selected = result.id in collection.selected_result_ids
        collection.planes = [plane for plane in collection.planes if plane.id not in plane_ids]
        remaining_planes = {plane.id for plane in collection.planes}
        collection.selected_plane_ids.intersection_update(remaining_planes)
        if collection.active_plane_id not in remaining_planes:
            collection.active_plane_id = None
        for plane in collection.planes:
            plane.selected = plane.id in collection.selected_plane_ids
        self._ensure_default_plane(state)
        self._sync_derived_state(state)

    def _select_delete_fallback(self, state: AppState, targets: SceneDeleteTargets) -> None:
        clear_plane_selection(state.section_collection)
        clear_result_selection(state.section_collection)
        region = state.region_collection.active_region
        if region is not None:
            region.selected = False
        if targets.section_result_ids and state.section_collection.results:
            set_active_result(state.section_collection, state.section_collection.results[-1].id)
            state.selected_item = SELECT_SECTION_RESULT
        elif targets.section_plane_ids and state.section_collection.planes:
            set_active_plane(state.section_collection, state.section_collection.planes[0].id)
            state.selected_item = SELECT_SECTION_PLANE
        else:
            state.selected_item = None
        state.active_transform_mode = None
        state.active_transform_axis = None
        state.transform_state = None
        self._sync_derived_state(state)

    @staticmethod
    def _ensure_default_plane(state: AppState) -> None:
        if not state.section_collection.planes:
            add_plane(state.section_collection, create_default_section_plane())
        elif state.section_collection.active_plane_id is None:
            set_active_plane(state.section_collection, state.section_collection.planes[0].id)

    @staticmethod
    def _sync_derived_state(state: AppState) -> None:
        active = next((result for result in state.section_collection.results if result.id == state.section_collection.active_result_id), None)
        state.section_result = active.result if active is not None and active.visible else None

    def _restore_scene_state(self, state: AppState, snapshot: _SceneStateSnapshot, object_ids: tuple[str, ...], *, reason: str) -> None:
        before_selection = self._selection_snapshot(state)
        snapshot.restore(state)
        after_selection = self._selection_snapshot(state)
        publish_scene_change(self.events, reason=reason, object_ids=object_ids, changed_fields=("scene", "selection"))
        if before_selection != after_selection:
            self.events.publish(SelectionChangedEvent(after_selection, reason=reason))

    def _restore_name(self, state: AppState, node_id: str, name: str, *, reason: str) -> None:
        owner = self._name_owner(state, node_id)
        if owner is None or owner.name == name:
            return
        owner.name = name
        publish_scene_change(self.events, reason=reason, object_ids=(node_id,), changed_fields=("name",))

    @staticmethod
    def _selection_snapshot(state: AppState) -> SelectionSnapshot:
        return SelectionController(state).snapshot()

    @staticmethod
    def _name_owner(state: AppState, node_id: str) -> object | None:
        if node_id == NODE_MESH:
            return state.mesh_object
        plane_id = section_plane_id_from_node(node_id)
        if plane_id is not None:
            return next((plane for plane in state.section_collection.planes if plane.id == plane_id), None)
        result_id = section_result_id_from_node(node_id)
        if result_id is not None:
            return next((result for result in state.section_collection.results if result.id == result_id), None)
        region_id = region_id_from_node(node_id)
        region = state.region_collection.active_region
        return region if region_id is not None and region is not None and region.id == region_id else None

    @staticmethod
    def _rename_command_name(node_id: str) -> str:
        if node_id == NODE_MESH:
            return "Rename Mesh"
        if section_plane_id_from_node(node_id) is not None:
            return "Rename Section Plane"
        if section_result_id_from_node(node_id) is not None:
            return "Rename Section Result"
        return "Rename Region"

    @staticmethod
    def _node_ids_for_targets(targets: SceneDeleteTargets) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                [
                    *(section_plane_node_id(value) for value in targets.section_plane_ids),
                    *(section_result_node_id(value) for value in targets.section_result_ids),
                    *(region_node_id(value) for value in targets.region_ids),
                ]
            )
        )


__all__ = ("SceneController", "SceneDeleteTargets")
