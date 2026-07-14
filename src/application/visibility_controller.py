"""UI-independent scene visibility controller."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from application.controller_support import (
    CallbackUndoPayload,
    ControllerBase,
    MODEL_SYNC_UI_REQUESTS,
    MODEL_SYNC_VIEWPORT_REQUESTS,
    curve_ids_for_group,
    publish_scene_change,
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
from application.state import AppState


class VisibilityController(ControllerBase):
    """Apply persistent/transient visibility with reversible payloads."""

    def all_node_ids(self) -> tuple[str, ...]:
        state = self.state
        node_ids: list[str] = []
        if state.mesh_object is not None:
            node_ids.append(NODE_MESH)
        node_ids.extend(
            section_plane_node_id(plane.id)
            for plane in state.section_collection.planes
        )
        node_ids.extend(
            section_result_node_id(result.id)
            for result in state.section_collection.results
        )
        node_ids.extend(curve_node_id(curve.id) for curve in state.curve_collection.curves)
        node_ids.extend(
            surface_node_id(surface.id)
            for surface in state.surface_collection.surfaces
        )
        node_ids.extend(
            surface_node_id(surface.id)
            for surface in state.brep_surface_collection.surfaces
            if surface_node_id(surface.id) not in node_ids
        )
        region = state.region_collection.active_region
        if region is not None:
            node_ids.append(region_node_id(region.id))
        return tuple(node_ids)

    def expand_node_ids(self, node_ids: Iterable[str]) -> tuple[str, ...]:
        """Expand scene/group IDs into existing visibility-bearing objects."""

        state = self.state
        expanded: list[str] = []

        def add(node_id: str) -> None:
            if node_id not in expanded:
                expanded.append(node_id)

        for node_id in tuple(dict.fromkeys(str(value) for value in node_ids)):
            if node_id == NODE_MESH:
                if state.mesh_object is not None:
                    add(NODE_MESH)
            elif node_id == NODE_SECTION_PLANES:
                for plane in state.section_collection.planes:
                    add(section_plane_node_id(plane.id))
            elif node_id == NODE_SECTION_RESULTS:
                for result in state.section_collection.results:
                    add(section_result_node_id(result.id))
            elif node_id == NODE_CURVES:
                for curve in state.curve_collection.curves:
                    add(curve_node_id(curve.id))
            elif node_id == NODE_SURFACES:
                for surface in state.surface_collection.surfaces:
                    add(surface_node_id(surface.id))
            elif node_id == NODE_BREP_SURFACES:
                for surface in state.brep_surface_collection.surfaces:
                    add(surface_node_id(surface.id))
            elif node_id == NODE_REGIONS:
                region = state.region_collection.active_region
                if region is not None:
                    add(region_node_id(region.id))
            elif (group_id := curve_group_id_from_node(node_id)) is not None:
                for curve_id in curve_ids_for_group(state, group_id):
                    add(curve_node_id(curve_id))
            elif self._node_exists(node_id):
                add(node_id)
        return tuple(expanded)

    def snapshot(self, node_ids: Iterable[str] | None = None) -> dict[str, bool]:
        targets = self.all_node_ids() if node_ids is None else self.expand_node_ids(node_ids)
        target_set = set(targets)
        state = self.state
        result: dict[str, bool] = {}
        if state.mesh_object is not None and NODE_MESH in target_set:
            result[NODE_MESH] = bool(state.mesh_object.visible)
        for plane in state.section_collection.planes:
            node_id = section_plane_node_id(plane.id)
            if node_id in target_set:
                result[node_id] = bool(plane.visible)
        for section_result in state.section_collection.results:
            node_id = section_result_node_id(section_result.id)
            if node_id in target_set:
                result[node_id] = bool(section_result.visible)
        for curve in state.curve_collection.curves:
            node_id = curve_node_id(curve.id)
            if node_id in target_set:
                result[node_id] = bool(curve.visible)
        for surface in state.surface_collection.surfaces:
            node_id = surface_node_id(surface.id)
            if node_id in target_set:
                result[node_id] = bool(surface.visible)
        for surface in state.brep_surface_collection.surfaces:
            node_id = surface_node_id(surface.id)
            if node_id in target_set:
                result[node_id] = bool(surface.visible)
        region = state.region_collection.active_region
        if region is not None:
            node_id = region_node_id(region.id)
            if node_id in target_set:
                result[node_id] = bool(region.visible)
        return result

    def hide(self, node_ids: Iterable[str]) -> CommandResult:
        return self.set_visibility(node_ids, False, operation="Hide Visibility")

    def show(self, node_ids: Iterable[str]) -> CommandResult:
        return self.set_visibility(node_ids, True, operation="Show Visibility")

    def hide_selected(self, node_ids: Iterable[str]) -> CommandResult:
        return self.hide(node_ids)

    def show_selected(self, node_ids: Iterable[str]) -> CommandResult:
        return self.show(node_ids)

    def set_visibility(
        self,
        node_ids: Iterable[str],
        visible: bool,
        *,
        operation: str | None = None,
    ) -> CommandResult:
        targets = self.expand_node_ids(node_ids)
        if not targets:
            return CommandResult.failure(
                "No visibility target is selected.", status="No selection"
            )
        before = self.snapshot(targets)
        changed_ids = self._set_on_state(self.state, targets, bool(visible))
        after = self.snapshot(targets)
        prefix = "Shown" if visible else "Hidden"
        name = operation or ("Show Visibility" if visible else "Hide Visibility")
        return self._mutation_result(
            name=name,
            before=before,
            after=after,
            changed_ids=changed_ids,
            status=self._status(prefix, len(changed_ids), "selected item"),
        )

    def toggle(self, node_ids: Iterable[str]) -> CommandResult:
        targets = self.expand_node_ids(node_ids)
        if not targets:
            return CommandResult.failure(
                "No visibility target is selected.", status="No selection"
            )
        before = self.snapshot(targets)
        changed_ids = self._toggle_on_state(self.state, targets)
        after = self.snapshot(targets)
        return self._mutation_result(
            name="Toggle Visibility",
            before=before,
            after=after,
            changed_ids=changed_ids,
            status=self._status("Toggled", len(changed_ids), "selected item"),
        )

    def set_values(
        self,
        values: Mapping[str, bool],
        *,
        operation: str = "Set Visibility",
        status: str = "Visibility updated",
    ) -> CommandResult:
        """Apply an explicit visibility map as one reversible operation."""

        requested = {
            str(node_id): bool(value) for node_id, value in values.items()
        }
        targets = self.expand_node_ids(requested)
        if not targets:
            return CommandResult.failure(
                "No visibility target is selected.", status="No selection"
            )
        target_values = {
            node_id: requested[node_id]
            for node_id in targets
            if node_id in requested
        }
        before = self.snapshot(target_values)
        self._set_snapshot_values(self.state, target_values)
        after = self.snapshot(target_values)
        changed_ids = tuple(
            node_id
            for node_id, value in before.items()
            if after.get(node_id) != value
        )
        return self._mutation_result(
            name=operation,
            before=before,
            after=after,
            changed_ids=changed_ids,
            status=status,
        )

    def show_all(self) -> CommandResult:
        targets = self.all_node_ids()
        if not targets:
            return CommandResult.ok(status="No visibility changes")
        before = self.snapshot(targets)
        changed_ids = self._set_on_state(self.state, targets, True)
        after = self.snapshot(targets)
        return self._mutation_result(
            name="Show Visibility",
            before=before,
            after=after,
            changed_ids=changed_ids,
            status="All scene items visible",
        )

    def isolate(self, node_ids: Iterable[str]) -> CommandResult:
        selected = self.expand_node_ids(node_ids)
        if not selected:
            return CommandResult.failure(
                "No visibility target is selected.", status="No selection"
            )
        all_targets = self.all_node_ids()
        selected_set = set(selected)
        before = self.snapshot(all_targets)
        hidden_ids = self._set_on_state(
            self.state,
            (node_id for node_id in all_targets if node_id not in selected_set),
            False,
        )
        shown_ids = self._set_on_state(self.state, selected, True)
        changed_ids = tuple(dict.fromkeys((*hidden_ids, *shown_ids)))
        after = self.snapshot(all_targets)
        return self._mutation_result(
            name="Hide Visibility",
            before=before,
            after=after,
            changed_ids=changed_ids,
            status=self._status("Hidden", len(hidden_ids), "unselected item"),
        )

    def hide_unselected(self, node_ids: Iterable[str]) -> CommandResult:
        return self.isolate(node_ids)

    def apply_snapshot(
        self,
        snapshot: Mapping[str, bool],
        *,
        reason: str = "visibility_restored",
    ) -> tuple[str, ...]:
        return self._apply_snapshot_to_state(self.state, snapshot, reason=reason)

    def _mutation_result(
        self,
        *,
        name: str,
        before: Mapping[str, bool],
        after: Mapping[str, bool],
        changed_ids: Iterable[str],
        status: str,
    ) -> CommandResult:
        changed = tuple(dict.fromkeys(str(value) for value in changed_ids))
        if not changed:
            return CommandResult.ok(status=status)
        target_state = self.state
        before_copy = dict(before)
        after_copy = dict(after)
        self._sync_derived_display_state(target_state)
        publish_scene_change(
            self.events,
            reason="visibility_changed",
            object_ids=changed,
            changed_fields=("visibility",),
        )
        undo_payload = CallbackUndoPayload(
            name=name,
            undo_action=lambda: self._apply_snapshot_to_state(
                target_state, before_copy, reason="visibility_undo"
            ),
            redo_action=lambda: self._apply_snapshot_to_state(
                target_state, after_copy, reason="visibility_redo"
            ),
        )
        return CommandResult.ok(
            status=status,
            changed=True,
            dirty=any(self._is_persistent_node(node_id) for node_id in changed),
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=undo_payload,
            metadata={
                "object_ids": changed,
                "visibility_before": before_copy,
                "visibility_after": after_copy,
            },
        )

    def _apply_snapshot_to_state(
        self,
        state: AppState,
        snapshot: Mapping[str, bool],
        *,
        reason: str,
    ) -> tuple[str, ...]:
        before = self._snapshot_for_state(state, snapshot)
        self._set_snapshot_values(state, snapshot)
        after = self._snapshot_for_state(state, snapshot)
        changed = tuple(
            node_id
            for node_id, value in before.items()
            if node_id in after and after[node_id] != value
        )
        self._sync_derived_display_state(state)
        if changed:
            publish_scene_change(
                self.events,
                reason=reason,
                object_ids=changed,
                changed_fields=("visibility",),
            )
        return changed

    @staticmethod
    def _set_on_state(
        state: AppState,
        node_ids: Iterable[str],
        visible: bool,
    ) -> tuple[str, ...]:
        targets = set(node_ids)
        changed: list[str] = []
        for node_id, owner in VisibilityController._owners(state, targets):
            if bool(owner.visible) != visible:
                owner.visible = visible
                changed.append(node_id)
        return tuple(dict.fromkeys(changed))

    @staticmethod
    def _toggle_on_state(
        state: AppState,
        node_ids: Iterable[str],
    ) -> tuple[str, ...]:
        targets = set(node_ids)
        changed: list[str] = []
        for node_id, owner in VisibilityController._owners(state, targets):
            owner.visible = not bool(owner.visible)
            changed.append(node_id)
        return tuple(dict.fromkeys(changed))

    @staticmethod
    def _set_snapshot_values(
        state: AppState,
        snapshot: Mapping[str, bool],
    ) -> None:
        for node_id, owner in VisibilityController._owners(state, set(snapshot)):
            owner.visible = bool(snapshot[node_id])

    @staticmethod
    def _snapshot_for_state(
        state: AppState,
        requested: Mapping[str, bool],
    ) -> dict[str, bool]:
        return {
            node_id: bool(owner.visible)
            for node_id, owner in VisibilityController._owners(state, set(requested))
        }

    @staticmethod
    def _owners(state: AppState, targets: set[str]) -> tuple[tuple[str, object], ...]:
        owners: list[tuple[str, object]] = []
        if state.mesh_object is not None and NODE_MESH in targets:
            owners.append((NODE_MESH, state.mesh_object))
        owners.extend(
            (section_plane_node_id(plane.id), plane)
            for plane in state.section_collection.planes
            if section_plane_node_id(plane.id) in targets
        )
        owners.extend(
            (section_result_node_id(result.id), result)
            for result in state.section_collection.results
            if section_result_node_id(result.id) in targets
        )
        owners.extend(
            (curve_node_id(curve.id), curve)
            for curve in state.curve_collection.curves
            if curve_node_id(curve.id) in targets
        )
        owners.extend(
            (surface_node_id(surface.id), surface)
            for surface in state.surface_collection.surfaces
            if surface_node_id(surface.id) in targets
        )
        owners.extend(
            (surface_node_id(surface.id), surface)
            for surface in state.brep_surface_collection.surfaces
            if surface_node_id(surface.id) in targets
        )
        region = state.region_collection.active_region
        if region is not None and region_node_id(region.id) in targets:
            owners.append((region_node_id(region.id), region))
        return tuple(owners)

    def _node_exists(self, node_id: str) -> bool:
        if node_id == NODE_MESH:
            return self.state.mesh_object is not None
        if section_plane_id_from_node(node_id) is not None:
            return any(
                plane.id == section_plane_id_from_node(node_id)
                for plane in self.state.section_collection.planes
            )
        if section_result_id_from_node(node_id) is not None:
            return any(
                result.id == section_result_id_from_node(node_id)
                for result in self.state.section_collection.results
            )
        curve_id = curve_id_from_node(node_id)
        if curve_id is not None:
            return any(curve.id == curve_id for curve in self.state.curve_collection.curves)
        surface_id = surface_id_from_node(node_id)
        if surface_id is not None:
            return any(
                surface.id == surface_id
                for surface in (
                    *self.state.surface_collection.surfaces,
                    *self.state.brep_surface_collection.surfaces,
                )
            )
        region_id = region_id_from_node(node_id)
        region = self.state.region_collection.active_region
        return region_id is not None and region is not None and region.id == region_id

    @staticmethod
    def _sync_derived_display_state(state: AppState) -> None:
        active_id = state.section_collection.active_result_id
        active_result = next(
            (
                result
                for result in state.section_collection.results
                if result.id == active_id
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

    @staticmethod
    def _is_persistent_node(node_id: str) -> bool:
        return region_id_from_node(node_id) is None

    @staticmethod
    def _status(prefix: str, changed_count: int, noun: str) -> str:
        if changed_count == 0:
            return "No visibility changes"
        if changed_count == 1:
            return f"{prefix} 1 {noun}"
        return f"{prefix} {changed_count} {noun}s"


__all__ = ("VisibilityController",)
