"""UI-independent scene naming and dependency-aware deletion controller."""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from application.controller_support import (
    CallbackUndoPayload,
    ControllerBase,
    MODEL_SYNC_UI_REQUESTS,
    MODEL_SYNC_VIEWPORT_REQUESTS,
    curve_ids_for_group,
    publish_scene_change,
)
from application.events import SelectionChangedEvent
from application.feature_dependencies import (
    FeatureDependencyChange,
    plan_feature_dependency_removal,
    prune_feature_dependencies,
)
from application.results import CommandResult
from application.scene_ids import (
    NODE_BREP_SURFACES,
    NODE_CURVES,
    NODE_MESH,
    NODE_REGIONS,
    NODE_SECTION_PLANES,
    NODE_SECTION_RESULTS,
    NODE_SURFACES,
    curve_group_id_from_node,
    curve_id_from_node,
    curve_node_id,
    region_id_from_node,
    region_node_id,
    section_plane_id_from_node,
    section_plane_node_id,
    section_result_id_from_node,
    section_result_node_id,
    surface_id_from_node,
    surface_node_id,
)
from application.selection import SelectionSnapshot
from application.selection_controller import (
    SELECT_CURVE,
    SELECT_SECTION_PLANE,
    SELECT_SECTION_RESULT,
    SELECT_SURFACE,
    SelectionController,
)
from application.state import AppState
from curves.curve_state import clear_curve_selection, set_active_curve
from sections.section_state import (
    add_plane,
    clear_plane_selection,
    clear_result_selection,
    create_default_section_plane,
    set_active_plane,
    set_active_result,
)
from surfaces.brep_state import (
    clear_brep_surface_selection,
    set_active_brep_surface,
)
from surfaces.surface_state import clear_surface_selection, set_active_surface


@dataclass(frozen=True, slots=True)
class SceneDeleteTargets:
    section_plane_ids: tuple[str, ...] = ()
    section_result_ids: tuple[str, ...] = ()
    curve_ids: tuple[str, ...] = ()
    preview_surface_ids: tuple[str, ...] = ()
    brep_surface_ids: tuple[str, ...] = ()
    region_ids: tuple[str, ...] = ()
    dependencies: FeatureDependencyChange = FeatureDependencyChange()

    @property
    def surface_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(set(self.preview_surface_ids) | set(self.brep_surface_ids))
        )

    @property
    def deleted_count(self) -> int:
        return sum(
            len(values)
            for values in (
                self.section_plane_ids,
                self.section_result_ids,
                self.curve_ids,
                self.preview_surface_ids,
                self.brep_surface_ids,
                self.region_ids,
                self.dependencies.removed_loft_feature_ids,
                self.dependencies.removed_four_boundary_feature_ids,
            )
        )

    def as_metadata(self) -> Mapping[str, object]:
        return {
            "removed_section_plane_ids": self.section_plane_ids,
            "removed_section_result_ids": self.section_result_ids,
            "removed_region_ids": self.region_ids,
            **self.dependencies.as_metadata(),
        }


@dataclass(slots=True)
class _SceneStateSnapshot:
    selected_item: str | None
    active_transform_mode: str | None
    active_transform_axis: str | None
    transform_state: object | None
    section_result: object | None
    curve_results: list[object]
    section_collection: object
    curve_collection: object
    surface_collection: object
    brep_surface_collection: object
    loft_feature_collection: object
    four_boundary_feature_collection: object
    region_collection: object

    @classmethod
    def capture(cls, state: AppState) -> _SceneStateSnapshot:
        return cls(
            selected_item=state.selected_item,
            active_transform_mode=state.active_transform_mode,
            active_transform_axis=state.active_transform_axis,
            transform_state=copy.deepcopy(state.transform_state),
            section_result=copy.deepcopy(state.section_result),
            curve_results=copy.deepcopy(state.curve_results),
            section_collection=copy.deepcopy(state.section_collection),
            curve_collection=copy.deepcopy(state.curve_collection),
            surface_collection=copy.deepcopy(state.surface_collection),
            brep_surface_collection=copy.deepcopy(state.brep_surface_collection),
            loft_feature_collection=copy.deepcopy(state.loft_feature_collection),
            four_boundary_feature_collection=copy.deepcopy(
                state.four_boundary_feature_collection
            ),
            region_collection=copy.deepcopy(state.region_collection),
        )

    def restore(self, state: AppState) -> None:
        state.selected_item = self.selected_item
        state.active_transform_mode = self.active_transform_mode
        state.active_transform_axis = self.active_transform_axis
        state.transform_state = copy.deepcopy(self.transform_state)
        state.section_result = copy.deepcopy(self.section_result)
        state.curve_results = copy.deepcopy(self.curve_results)
        state.section_collection = copy.deepcopy(self.section_collection)
        state.curve_collection = copy.deepcopy(self.curve_collection)
        state.surface_collection = copy.deepcopy(self.surface_collection)
        state.brep_surface_collection = copy.deepcopy(self.brep_surface_collection)
        state.loft_feature_collection = copy.deepcopy(self.loft_feature_collection)
        state.four_boundary_feature_collection = copy.deepcopy(
            self.four_boundary_feature_collection
        )
        state.region_collection = copy.deepcopy(self.region_collection)


class SceneController(ControllerBase):
    """Coordinate scene record identity, naming, and cascading deletion."""

    def rename(self, node_id: str, new_name: object) -> CommandResult:
        normalized_name = str(new_name).strip()
        if not normalized_name:
            return CommandResult.failure(
                "Name cannot be empty.", status="Name cannot be empty"
            )
        owner = self._name_owner(self.state, str(node_id))
        if owner is None:
            return CommandResult.failure(
                "No renameable scene object was found.",
                status="No renameable selection",
            )
        old_name = str(owner.name)
        if old_name == normalized_name:
            return CommandResult.ok(status=f"Selected: {old_name}")
        target_state = self.state
        target_node_id = str(node_id)
        owner.name = normalized_name
        publish_scene_change(
            self.events,
            reason="scene_object_renamed",
            object_ids=(target_node_id,),
            changed_fields=("name",),
        )
        undo_payload = CallbackUndoPayload(
            name=self._rename_command_name(target_node_id),
            undo_action=lambda: self._restore_name(
                target_state, target_node_id, old_name, reason="rename_undo"
            ),
            redo_action=lambda: self._restore_name(
                target_state, target_node_id, normalized_name, reason="rename_redo"
            ),
        )
        return CommandResult.ok(
            status=f"Selected: {normalized_name}",
            changed=True,
            dirty=region_id_from_node(target_node_id) is None,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=undo_payload,
            metadata={
                "object_ids": (target_node_id,),
                "old_name": old_name,
                "new_name": normalized_name,
            },
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
            return CommandResult.failure(
                "No deletable scene object was found.",
                status="No deletable selection",
            )

        target_state = self.state
        before_selection = self._selection_snapshot(target_state)
        before = _SceneStateSnapshot.capture(target_state)
        self._apply_delete_targets(target_state, targets)
        self._select_delete_fallback(target_state, targets)
        after = _SceneStateSnapshot.capture(target_state)
        after_selection = self._selection_snapshot(target_state)
        affected_node_ids = self._node_ids_for_targets(targets)
        publish_scene_change(
            self.events,
            reason="scene_objects_deleted",
            object_ids=affected_node_ids,
            changed_fields=("scene", "selection", "dependencies"),
        )
        if before_selection != after_selection:
            self.events.publish(
                SelectionChangedEvent(after_selection, reason="delete_fallback")
            )

        undo_payload = CallbackUndoPayload(
            name=self._delete_command_name(targets),
            undo_action=lambda: self._restore_scene_state(
                target_state, before, affected_node_ids, reason="delete_undo"
            ),
            redo_action=lambda: self._restore_scene_state(
                target_state, after, affected_node_ids, reason="delete_redo"
            ),
        )
        record_count = (
            len(targets.section_plane_ids)
            + len(targets.section_result_ids)
            + len(targets.curve_ids)
            + len(targets.preview_surface_ids)
            + len(targets.brep_surface_ids)
            + len(targets.region_ids)
        )
        status = (
            "Region deleted."
            if record_count == 1 and targets.region_ids
            else "Deleted selected object"
            if record_count == 1
            else f"Deleted {record_count} selected objects"
        )
        only_regions = bool(targets.region_ids) and record_count == len(
            targets.region_ids
        )
        return CommandResult.ok(
            status=status,
            changed=True,
            dirty=not only_regions,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=undo_payload,
            metadata={
                **targets.as_metadata(),
                "object_ids": affected_node_ids,
                "selection": after_selection,
            },
        )

    def delete_targets(self, node_ids: Iterable[str]) -> SceneDeleteTargets:
        state = self.state
        plane_ids: set[str] = set()
        result_ids: set[str] = set()
        curve_ids: set[str] = set()
        preview_ids: set[str] = set()
        brep_ids: set[str] = set()
        region_ids: set[str] = set()
        existing_preview_ids = {
            surface.id for surface in state.surface_collection.surfaces
        }
        existing_brep_ids = {
            surface.id for surface in state.brep_surface_collection.surfaces
        }

        for node_id in tuple(dict.fromkeys(str(value) for value in node_ids)):
            if node_id == NODE_SECTION_PLANES:
                plane_ids.update(plane.id for plane in state.section_collection.planes)
            elif (plane_id := section_plane_id_from_node(node_id)) is not None:
                plane_ids.add(plane_id)
            elif node_id == NODE_SECTION_RESULTS:
                result_ids.update(result.id for result in state.section_collection.results)
            elif (result_id := section_result_id_from_node(node_id)) is not None:
                result_ids.add(result_id)
            elif node_id == NODE_CURVES:
                curve_ids.update(curve.id for curve in state.curve_collection.curves)
            elif (group_id := curve_group_id_from_node(node_id)) is not None:
                curve_ids.update(curve_ids_for_group(state, group_id))
            elif (curve_id := curve_id_from_node(node_id)) is not None:
                curve_ids.add(curve_id)
            elif node_id == NODE_SURFACES:
                preview_ids.update(existing_preview_ids)
            elif node_id == NODE_BREP_SURFACES:
                brep_ids.update(existing_brep_ids)
            elif (surface_id := surface_id_from_node(node_id)) is not None:
                if surface_id in existing_preview_ids:
                    preview_ids.add(surface_id)
                if surface_id in existing_brep_ids:
                    brep_ids.add(surface_id)
            elif node_id == NODE_REGIONS:
                region = state.region_collection.active_region
                if region is not None:
                    region_ids.add(region.id)
            elif (region_id := region_id_from_node(node_id)) is not None:
                region_ids.add(region_id)

        existing_plane_ids = {plane.id for plane in state.section_collection.planes}
        plane_ids.intersection_update(existing_plane_ids)
        result_ids.update(
            result.id
            for result in state.section_collection.results
            if result.plane_id in plane_ids
        )
        existing_result_ids = {
            result.id for result in state.section_collection.results
        }
        result_ids.intersection_update(existing_result_ids)
        curve_ids.update(
            curve.id
            for curve in state.curve_collection.curves
            if curve.section_result_id in result_ids or curve.plane_id in plane_ids
        )
        existing_curve_ids = {curve.id for curve in state.curve_collection.curves}
        curve_ids.intersection_update(existing_curve_ids)
        dependency_change = plan_feature_dependency_removal(
            state,
            curve_ids=curve_ids,
            preview_surface_ids=preview_ids,
            brep_surface_ids=brep_ids,
        )
        preview_ids.update(dependency_change.removed_preview_surface_ids)
        brep_ids.update(dependency_change.removed_brep_surface_ids)
        region = state.region_collection.active_region
        existing_region_ids = set() if region is None else {region.id}
        region_ids.intersection_update(existing_region_ids)
        return SceneDeleteTargets(
            section_plane_ids=tuple(sorted(plane_ids)),
            section_result_ids=tuple(sorted(result_ids)),
            curve_ids=tuple(sorted(curve_ids)),
            preview_surface_ids=tuple(sorted(preview_ids)),
            brep_surface_ids=tuple(sorted(brep_ids)),
            region_ids=tuple(sorted(region_ids)),
            dependencies=dependency_change,
        )

    def _apply_delete_targets(
        self,
        state: AppState,
        targets: SceneDeleteTargets,
    ) -> None:
        plane_ids = set(targets.section_plane_ids)
        result_ids = set(targets.section_result_ids)
        curve_ids = set(targets.curve_ids)
        region_ids = set(targets.region_ids)
        region = state.region_collection.active_region
        if region is not None and region.id in region_ids:
            state.region_collection.clear()

        prune_feature_dependencies(state, targets.dependencies)
        state.curve_collection.curves = [
            curve
            for curve in state.curve_collection.curves
            if curve.id not in curve_ids
        ]
        remaining_curve_ids = {curve.id for curve in state.curve_collection.curves}
        state.curve_collection.selected_curve_ids.intersection_update(
            remaining_curve_ids
        )
        if state.curve_collection.active_curve_id not in remaining_curve_ids:
            state.curve_collection.active_curve_id = None
        for curve in state.curve_collection.curves:
            curve.selected = curve.id in state.curve_collection.selected_curve_ids

        state.section_collection.results = [
            result
            for result in state.section_collection.results
            if result.id not in result_ids and result.plane_id not in plane_ids
        ]
        remaining_result_ids = {
            result.id for result in state.section_collection.results
        }
        state.section_collection.selected_result_ids.intersection_update(
            remaining_result_ids
        )
        if state.section_collection.active_result_id not in remaining_result_ids:
            state.section_collection.active_result_id = None
        for result in state.section_collection.results:
            result.selected = result.id in state.section_collection.selected_result_ids

        state.section_collection.planes = [
            plane
            for plane in state.section_collection.planes
            if plane.id not in plane_ids
        ]
        remaining_plane_ids = {plane.id for plane in state.section_collection.planes}
        state.section_collection.selected_plane_ids.intersection_update(
            remaining_plane_ids
        )
        if state.section_collection.active_plane_id not in remaining_plane_ids:
            state.section_collection.active_plane_id = None
        for plane in state.section_collection.planes:
            plane.selected = plane.id in state.section_collection.selected_plane_ids
        self._ensure_default_plane(state)
        self._sync_derived_state(state)

    def _select_delete_fallback(
        self,
        state: AppState,
        targets: SceneDeleteTargets,
    ) -> None:
        self._clear_all_selection(state)
        if targets.surface_ids and state.surface_collection.surfaces:
            surface = state.surface_collection.surfaces[0]
            set_active_surface(state.surface_collection, surface.id)
            state.selected_item = SELECT_SURFACE
        elif targets.surface_ids and state.brep_surface_collection.surfaces:
            surface = state.brep_surface_collection.surfaces[0]
            set_active_brep_surface(state.brep_surface_collection, surface.id)
            state.selected_item = SELECT_SURFACE
        elif targets.curve_ids and state.curve_collection.curves:
            curve = state.curve_collection.curves[0]
            set_active_curve(state.curve_collection, curve.id)
            state.selected_item = SELECT_CURVE
        elif targets.section_result_ids and state.section_collection.results:
            result = state.section_collection.results[-1]
            set_active_result(state.section_collection, result.id)
            child_curves = [
                curve
                for curve in state.curve_collection.curves
                if curve.section_result_id == result.id
            ]
            if child_curves:
                state.curve_collection.selected_curve_ids = {
                    curve.id for curve in child_curves
                }
                state.curve_collection.active_curve_id = child_curves[0].id
                for curve in state.curve_collection.curves:
                    curve.selected = (
                        curve.id in state.curve_collection.selected_curve_ids
                    )
            state.selected_item = SELECT_SECTION_RESULT
        elif targets.section_plane_ids and state.section_collection.planes:
            plane = state.section_collection.planes[0]
            set_active_plane(state.section_collection, plane.id)
            state.selected_item = SELECT_SECTION_PLANE
        else:
            state.selected_item = None
        state.active_transform_mode = None
        state.active_transform_axis = None
        state.transform_state = None
        self._sync_derived_state(state)

    @staticmethod
    def _clear_all_selection(state: AppState) -> None:
        clear_plane_selection(state.section_collection)
        clear_result_selection(state.section_collection)
        clear_curve_selection(state.curve_collection)
        clear_surface_selection(state.surface_collection)
        clear_brep_surface_selection(state.brep_surface_collection)
        region = state.region_collection.active_region
        if region is not None:
            region.selected = False

    @staticmethod
    def _ensure_default_plane(state: AppState) -> None:
        if not state.section_collection.planes:
            add_plane(state.section_collection, create_default_section_plane())
        elif state.section_collection.active_plane_id is None:
            set_active_plane(
                state.section_collection,
                state.section_collection.planes[0].id,
            )

    @staticmethod
    def _sync_derived_state(state: AppState) -> None:
        active_result = next(
            (
                result
                for result in state.section_collection.results
                if result.id == state.section_collection.active_result_id
            ),
            None,
        )
        state.section_result = (
            active_result.result
            if active_result is not None and active_result.visible
            else None
        )
        state.curve_results = [
            curve for curve in state.curve_collection.curves if curve.visible
        ]

    def _restore_scene_state(
        self,
        state: AppState,
        snapshot: _SceneStateSnapshot,
        object_ids: tuple[str, ...],
        *,
        reason: str,
    ) -> None:
        before_selection = self._selection_snapshot(state)
        snapshot.restore(state)
        after_selection = self._selection_snapshot(state)
        publish_scene_change(
            self.events,
            reason=reason,
            object_ids=object_ids,
            changed_fields=("scene", "selection", "dependencies"),
        )
        if before_selection != after_selection:
            self.events.publish(SelectionChangedEvent(after_selection, reason=reason))

    def _restore_name(
        self,
        state: AppState,
        node_id: str,
        name: str,
        *,
        reason: str,
    ) -> None:
        owner = self._name_owner(state, node_id)
        if owner is None or owner.name == name:
            return
        owner.name = name
        publish_scene_change(
            self.events,
            reason=reason,
            object_ids=(node_id,),
            changed_fields=("name",),
        )

    @staticmethod
    def _selection_snapshot(state: AppState) -> SelectionSnapshot:
        return SelectionController(state).snapshot()

    @staticmethod
    def _name_owner(state: AppState, node_id: str) -> object | None:
        if node_id == NODE_MESH:
            return state.mesh_object
        plane_id = section_plane_id_from_node(node_id)
        if plane_id is not None:
            return next(
                (
                    plane
                    for plane in state.section_collection.planes
                    if plane.id == plane_id
                ),
                None,
            )
        result_id = section_result_id_from_node(node_id)
        if result_id is not None:
            return next(
                (
                    result
                    for result in state.section_collection.results
                    if result.id == result_id
                ),
                None,
            )
        curve_id = curve_id_from_node(node_id)
        if curve_id is not None:
            return next(
                (
                    curve
                    for curve in state.curve_collection.curves
                    if curve.id == curve_id
                ),
                None,
            )
        surface_id = surface_id_from_node(node_id)
        if surface_id is not None:
            return next(
                (
                    surface
                    for surface in (
                        *state.surface_collection.surfaces,
                        *state.brep_surface_collection.surfaces,
                    )
                    if surface.id == surface_id
                ),
                None,
            )
        region_id = region_id_from_node(node_id)
        region = state.region_collection.active_region
        return (
            region
            if region_id is not None and region is not None and region.id == region_id
            else None
        )

    @staticmethod
    def _rename_command_name(node_id: str) -> str:
        if node_id == NODE_MESH:
            return "Rename Mesh"
        if section_plane_id_from_node(node_id) is not None:
            return "Rename Section Plane"
        if section_result_id_from_node(node_id) is not None:
            return "Rename Section Result"
        if curve_id_from_node(node_id) is not None:
            return "Rename Curve"
        if surface_id_from_node(node_id) is not None:
            return "Rename Surface"
        return "Rename Region"

    @staticmethod
    def _delete_command_name(targets: SceneDeleteTargets) -> str:
        curve_count = len(targets.curve_ids)
        surface_count = len(targets.preview_surface_ids) + len(
            targets.brep_surface_ids
        )
        if curve_count == 1 and surface_count == 0:
            return "Delete Curve"
        if surface_count == 1 and curve_count == 0:
            return "Delete Surface"
        if curve_count > 1 and surface_count == 0:
            return "Delete Curves"
        if surface_count > 1 and curve_count == 0:
            return "Delete Surfaces"
        if len(targets.region_ids) == 1 and targets.deleted_count == 1:
            return "Delete Region"
        return "Delete Objects"

    @staticmethod
    def _node_ids_for_targets(targets: SceneDeleteTargets) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                [
                    *(
                        section_plane_node_id(value)
                        for value in targets.section_plane_ids
                    ),
                    *(
                        section_result_node_id(value)
                        for value in targets.section_result_ids
                    ),
                    *(curve_node_id(value) for value in targets.curve_ids),
                    *(
                        surface_node_id(value)
                        for value in targets.preview_surface_ids
                    ),
                    *(
                        surface_node_id(value)
                        for value in targets.brep_surface_ids
                    ),
                    *(region_node_id(value) for value in targets.region_ids),
                ]
            )
        )


__all__ = ("SceneController", "SceneDeleteTargets")
