"""UI-independent controller for section-plane and section-result workflows."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import math
from uuid import uuid4

import numpy as np

from application.controller_support import (
    CallbackUndoPayload,
    ControllerBase,
    MODEL_SYNC_UI_REQUESTS,
    MODEL_SYNC_VIEWPORT_REQUESTS,
    publish_scene_change,
)
from application.feature_dependencies import (
    FeatureDependencyChange,
    plan_feature_dependency_removal,
    prune_feature_dependencies,
)
from application.results import CommandResult
from application.state import AppState
from curves.curve_state import (
    CurveCollection,
    StoredCurve,
    add_curve,
    clear_curves_for_plane,
    clear_curves_for_section_result,
    get_visible_curves,
    refresh_curve_diagnostics,
)
from geometry.curves import fit_section_polylines
from geometry.sections import extract_section, extract_section_by_plane, normalize_axis
from sections.section_state import (
    SectionCollection,
    SectionPlaneState,
    StoredSectionResult,
    add_plane,
    add_result,
    axis_normal,
    clear_results_for_plane,
    create_default_section_plane,
    get_active_plane,
    plane_normal,
    plane_origin,
    remove_plane,
    set_active_plane,
    set_active_result,
    set_plane_axis_offset,
)
from surfaces.brep_state import BrepSurfaceCollection
from surfaces.four_boundary_feature import FourBoundaryPatchFeatureCollection
from surfaces.loft_feature import LoftFeatureCollection
from surfaces.surface_state import SurfaceCollection


SELECT_SECTION_PLANE = "section_plane"


@dataclass(slots=True)
class SectionWorkflowSnapshot:
    """Copy of persistent state affected by a section dependency cascade."""

    section_collection: SectionCollection
    curve_collection: CurveCollection
    surface_collection: SurfaceCollection
    brep_surface_collection: BrepSurfaceCollection
    loft_feature_collection: LoftFeatureCollection
    four_boundary_feature_collection: FourBoundaryPatchFeatureCollection
    section_result: object | None
    curve_results: list[object]
    selected_item: str | None


def capture_section_workflow_state(state: AppState) -> SectionWorkflowSnapshot:
    """Capture only section-owned state, excluding the potentially large mesh."""

    return SectionWorkflowSnapshot(
        section_collection=copy.deepcopy(state.section_collection),
        curve_collection=copy.deepcopy(state.curve_collection),
        surface_collection=copy.deepcopy(state.surface_collection),
        brep_surface_collection=copy.deepcopy(state.brep_surface_collection),
        loft_feature_collection=copy.deepcopy(state.loft_feature_collection),
        four_boundary_feature_collection=copy.deepcopy(
            state.four_boundary_feature_collection
        ),
        section_result=copy.deepcopy(state.section_result),
        curve_results=copy.deepcopy(list(state.curve_results)),
        selected_item=state.selected_item,
    )


def restore_section_workflow_state(
    state: AppState,
    snapshot: SectionWorkflowSnapshot,
) -> None:
    """Restore a snapshot without sharing its mutable collections with callers."""

    state.section_collection = copy.deepcopy(snapshot.section_collection)
    state.curve_collection = copy.deepcopy(snapshot.curve_collection)
    state.surface_collection = copy.deepcopy(snapshot.surface_collection)
    state.brep_surface_collection = copy.deepcopy(snapshot.brep_surface_collection)
    state.loft_feature_collection = copy.deepcopy(snapshot.loft_feature_collection)
    state.four_boundary_feature_collection = copy.deepcopy(
        snapshot.four_boundary_feature_collection
    )
    state.section_result = copy.deepcopy(snapshot.section_result)
    state.curve_results = copy.deepcopy(snapshot.curve_results)
    state.selected_item = snapshot.selected_item


def sync_display_section_result(
    state: AppState,
    stored_result: StoredSectionResult | None = None,
) -> StoredSectionResult | None:
    """Synchronize legacy display fields from authoritative stored records."""

    existing = state.section_collection.results
    if stored_result is not None:
        stored_result = next(
            (result for result in existing if result.id == stored_result.id),
            None,
        )
    if stored_result is None and existing:
        stored_result = existing[-1]

    if stored_result is None:
        state.section_collection.active_result_id = None
        state.section_collection.selected_result_ids.clear()
        for result in existing:
            result.selected = False
        state.section_result = None
    else:
        set_active_result(state.section_collection, stored_result.id)
        state.section_result = stored_result.result if stored_result.visible else None

    for curve in state.curve_collection.curves:
        refresh_curve_diagnostics(curve)
    state.curve_results = list(get_visible_curves(state.curve_collection))
    return stored_result


def invalidate_section_plane_dependencies(
    state: AppState,
    plane_id: str,
) -> FeatureDependencyChange:
    """Remove results and every downstream feature sourced by one plane."""

    result_ids = {
        result.id
        for result in state.section_collection.results
        if result.plane_id == str(plane_id)
    }
    curve_ids = {
        curve.id
        for curve in state.curve_collection.curves
        if curve.plane_id == str(plane_id)
        or curve.section_result_id in result_ids
    }
    change = plan_feature_dependency_removal(state, curve_ids=curve_ids)
    prune_feature_dependencies(state, change)
    clear_curves_for_plane(state.curve_collection, str(plane_id))
    clear_results_for_plane(state.section_collection, str(plane_id))
    sync_display_section_result(state)
    return change


def invalidate_section_result_dependencies(
    state: AppState,
    result_id: str,
) -> FeatureDependencyChange:
    """Remove one stored result and everything derived from its fitted curves."""

    normalized_id = str(result_id)
    curve_ids = {
        curve.id
        for curve in state.curve_collection.curves
        if curve.section_result_id == normalized_id
    }
    change = plan_feature_dependency_removal(state, curve_ids=curve_ids)
    prune_feature_dependencies(state, change)
    clear_curves_for_section_result(state.curve_collection, normalized_id)
    state.section_collection.results = [
        result
        for result in state.section_collection.results
        if result.id != normalized_id
    ]
    state.section_collection.selected_result_ids.discard(normalized_id)
    if state.section_collection.active_result_id == normalized_id:
        state.section_collection.active_result_id = None
    sync_display_section_result(state)
    return change


class SectionController(ControllerBase):
    """Coordinate section state, geometry extraction, and dependency invalidation."""

    def add_plane(
        self,
        *,
        axis: str = "Z",
        offset: float = 0.0,
        visible: bool = True,
        name: str | None = None,
    ) -> CommandResult:
        if self.state.mesh_object is None:
            return CommandResult.failure("No mesh is loaded.", status="No selection")
        try:
            axis_key = normalize_axis(axis)
            offset_value = _finite_number(offset, "Section offset")
        except ValueError as exc:
            return CommandResult.failure(str(exc), status="Section plane was not added")

        before = capture_section_workflow_state(self.state)
        plane = create_default_section_plane(axis=axis_key, offset=offset_value)
        plane.name = str(name).strip() if name is not None else self.next_plane_name()
        if not plane.name:
            plane.name = self.next_plane_name()
        plane.visible = bool(visible)
        add_plane(self.state.section_collection, plane)
        set_active_plane(self.state.section_collection, plane.id)
        self.state.selected_item = SELECT_SECTION_PLANE
        after = capture_section_workflow_state(self.state)
        undo = self._workflow_undo("Add Section Plane", before, after)
        return self._changed_result(
            status=f"Added: {plane.name}",
            reason="section_plane_added",
            object_ids=(plane.id,),
            changed_fields=("section_collection", "selected_item"),
            undo=undo,
            metadata={"section_plane_id": plane.id},
        )

    def ensure_default_plane(self) -> SectionPlaneState:
        active = get_active_plane(self.state.section_collection)
        if active is not None:
            return active
        if self.state.section_collection.planes:
            set_active_plane(
                self.state.section_collection,
                self.state.section_collection.planes[0].id,
            )
            active = get_active_plane(self.state.section_collection)
            assert active is not None
            return active
        plane = create_default_section_plane()
        add_plane(self.state.section_collection, plane)
        return plane

    def set_axis_offset(
        self,
        *,
        axis: str,
        offset: float,
        plane_id: str | None = None,
        offset_bounds: tuple[float, float] | None = None,
        clamp: bool = False,
        visible: bool | None = None,
    ) -> CommandResult:
        plane = self._plane(plane_id)
        if plane is None:
            return CommandResult.failure("No section plane is active.", status="No section plane")
        try:
            axis_key = normalize_axis(axis)
            offset_value = _finite_number(offset, "Section offset")
            if clamp and offset_bounds is not None:
                minimum = _finite_number(offset_bounds[0], "Minimum offset")
                maximum = _finite_number(offset_bounds[1], "Maximum offset")
                if minimum > maximum:
                    minimum, maximum = maximum, minimum
                offset_value = min(max(offset_value, minimum), maximum)
        except (IndexError, TypeError, ValueError) as exc:
            return CommandResult.failure(str(exc), status="Section plane was not changed")

        old_origin = plane_origin(plane)
        old_normal = plane_normal(plane)
        old_visible = bool(plane.visible)
        next_visible = old_visible if visible is None else bool(visible)
        next_origin = axis_normal(axis_key) * offset_value
        geometry_changed = not (
            np.allclose(old_origin, next_origin, atol=1e-12)
            and np.allclose(old_normal, axis_normal(axis_key), atol=1e-12)
            and plane.axis == axis_key
        )
        if not geometry_changed and old_visible == next_visible:
            return CommandResult.ok(
                status=f"Section plane: {axis_key} = {offset_value:.3f}",
                metadata={"offset": offset_value, "axis": axis_key},
            )

        before = capture_section_workflow_state(self.state)
        reset_to_axis_aligned = not np.allclose(
            old_normal,
            axis_normal(axis_key),
            atol=1e-6,
        )
        set_plane_axis_offset(plane, axis_key, offset_value)
        plane.visible = next_visible
        dependency_change = (
            invalidate_section_plane_dependencies(self.state, plane.id)
            if geometry_changed
            else plan_feature_dependency_removal(self.state)
        )
        after = capture_section_workflow_state(self.state)
        undo = self._workflow_undo("Change Section Plane", before, after)
        status = (
            f"Section plane reset to axis-aligned {axis_key} mode"
            if reset_to_axis_aligned
            else f"Section plane: {axis_key} = {offset_value:.3f}"
        )
        metadata = {
            "axis": axis_key,
            "offset": offset_value,
            "reset_to_axis_aligned": reset_to_axis_aligned,
            **dependency_change.as_metadata(),
        }
        return self._changed_result(
            status=status,
            reason="section_plane_changed",
            object_ids=(plane.id,),
            changed_fields=(
                "section_collection",
                "curve_collection",
                "surface_collection",
                "brep_surface_collection",
            ),
            undo=undo,
            metadata=metadata,
        )

    def set_offset(
        self,
        offset: float,
        *,
        plane_id: str | None = None,
        offset_bounds: tuple[float, float] | None = None,
        clamp: bool = False,
    ) -> CommandResult:
        plane = self._plane(plane_id)
        if plane is None:
            return CommandResult.failure("No section plane is active.", status="No section plane")
        return self.set_axis_offset(
            axis=plane.axis,
            offset=offset,
            plane_id=plane.id,
            offset_bounds=offset_bounds,
            clamp=clamp,
        )

    def cycle_axis(
        self,
        *,
        plane_id: str | None = None,
        offset_bounds: tuple[float, float] | None = None,
    ) -> CommandResult:
        plane = self._plane(plane_id)
        if plane is None:
            return CommandResult.failure("No section plane is active.", status="No section plane")
        axes = ("X", "Y", "Z")
        next_axis = axes[(axes.index(normalize_axis(plane.axis)) + 1) % len(axes)]
        result = self.set_axis_offset(
            axis=next_axis,
            offset=plane.offset,
            plane_id=plane.id,
            offset_bounds=offset_bounds,
            clamp=offset_bounds is not None,
        )
        if result.success and result.changed:
            return CommandResult.ok(
                status=f"Section plane axis cycled to {next_axis}",
                changed=True,
                dirty=result.dirty,
                viewport_requests=result.viewport_requests,
                ui_requests=result.ui_requests,
                undo_payload=result.undo_payload,
                metadata=result.metadata,
            )
        return result

    def compute(
        self,
        mesh: object,
        *,
        plane_id: str | None = None,
        result_name: str | None = None,
    ) -> CommandResult:
        if self.state.mesh_object is None:
            return CommandResult.failure("No mesh is loaded.", status="No selection")
        if mesh is None:
            return CommandResult.failure(
                "A transformed source mesh is required.",
                status="Section computation failed",
            )
        plane = self._plane(plane_id)
        if plane is None:
            return CommandResult.failure("No section plane is active.", status="No section plane")

        active_origin = plane_origin(plane)
        active_normal = plane_normal(plane)
        arbitrary = not self.is_axis_aligned(plane)
        try:
            if arbitrary:
                section_result = extract_section_by_plane(
                    mesh,
                    active_origin,
                    active_normal,
                    axis=plane.axis,
                    offset=plane.offset,
                )
            else:
                section_result = extract_section(
                    mesh,
                    axis=plane.axis,
                    offset=plane.offset,
                )
            curve_fits = tuple(fit_section_polylines(section_result.polylines))
        except (TypeError, ValueError) as exc:
            return CommandResult.failure(str(exc), status="Section computation failed")

        before = capture_section_workflow_state(self.state)
        name = str(result_name).strip() if result_name is not None else self.next_result_name()
        if not name:
            name = self.next_result_name()
        stored = StoredSectionResult(
            id=f"section-result-{uuid4().hex}",
            name=name,
            plane_id=plane.id,
            axis=plane.axis,
            offset=plane.offset,
            result=section_result,
            plane_origin=active_origin,
            plane_normal=active_normal,
            is_arbitrary_plane=arbitrary,
        )
        add_result(self.state.section_collection, stored)
        created_curve_ids: list[str] = []
        for index, curve_fit in enumerate(curve_fits, start=1):
            curve = StoredCurve(
                id=f"curve-{uuid4().hex}",
                name=f"{stored.name} Curve {index}",
                section_result_id=stored.id,
                plane_id=stored.plane_id,
                original_points=curve_fit.original_points,
                fitted_points=curve_fit.fitted_points,
                mean_error=curve_fit.mean_error,
                max_error=curve_fit.max_error,
                is_closed=curve_fit.is_closed,
            )
            add_curve(self.state.curve_collection, curve)
            created_curve_ids.append(curve.id)
        sync_display_section_result(self.state, stored)
        after = capture_section_workflow_state(self.state)
        undo = self._workflow_undo("Compute Section", before, after)
        status = (
            f"Computed arbitrary section from {plane.name}"
            if arbitrary
            else f"Section computed: {stored.name} - {section_result.segment_count} segments"
        )
        return self._changed_result(
            status=status,
            reason="section_computed",
            object_ids=(stored.id, *created_curve_ids),
            changed_fields=("section_collection", "curve_collection"),
            undo=undo,
            metadata={
                "section_result_id": stored.id,
                "curve_ids": tuple(created_curve_ids),
                "segment_count": section_result.segment_count,
                "is_arbitrary_plane": arbitrary,
            },
        )

    compute_section = compute

    def clear_active_results(self) -> CommandResult:
        plane = get_active_plane(self.state.section_collection)
        if plane is None:
            return CommandResult.ok(status="Section cleared")
        has_results = any(
            result.plane_id == plane.id
            for result in self.state.section_collection.results
        )
        has_curves = any(
            curve.plane_id == plane.id for curve in self.state.curve_collection.curves
        )
        if not has_results and not has_curves:
            return CommandResult.ok(status="Section cleared")

        before = capture_section_workflow_state(self.state)
        change = invalidate_section_plane_dependencies(self.state, plane.id)
        after = capture_section_workflow_state(self.state)
        undo = self._workflow_undo("Clear Section", before, after)
        return self._changed_result(
            status="Section cleared",
            reason="section_results_cleared",
            object_ids=(plane.id,),
            changed_fields=(
                "section_collection",
                "curve_collection",
                "surface_collection",
                "brep_surface_collection",
            ),
            undo=undo,
            metadata=change.as_metadata(),
        )

    clear_section = clear_active_results
    clear_active_section_result = clear_active_results

    def delete_result(self, result_id: str | None = None) -> CommandResult:
        normalized_id = (
            self.state.section_collection.active_result_id
            if result_id is None
            else str(result_id)
        )
        result = next(
            (
                candidate
                for candidate in self.state.section_collection.results
                if candidate.id == normalized_id
            ),
            None,
        )
        if result is None:
            return CommandResult.failure("Section result not found.")
        before = capture_section_workflow_state(self.state)
        change = invalidate_section_result_dependencies(self.state, result.id)
        after = capture_section_workflow_state(self.state)
        undo = self._workflow_undo("Delete Section Result", before, after)
        return self._changed_result(
            status=f"Deleted: {result.name}",
            reason="section_result_deleted",
            object_ids=(result.id,),
            changed_fields=(
                "section_collection",
                "curve_collection",
                "surface_collection",
                "brep_surface_collection",
            ),
            undo=undo,
            metadata=change.as_metadata(),
        )

    def clear_all_results(self) -> CommandResult:
        state = self.state
        curve_ids = tuple(curve.id for curve in state.curve_collection.curves)
        preview_ids = tuple(surface.id for surface in state.surface_collection.surfaces)
        brep_ids = tuple(surface.id for surface in state.brep_surface_collection.surfaces)
        changed = bool(
            state.section_collection.results
            or curve_ids
            or preview_ids
            or brep_ids
            or state.loft_feature_collection.features
            or state.four_boundary_feature_collection.features
        )
        if not changed:
            return CommandResult.ok(status="All section results cleared")

        before = capture_section_workflow_state(state)
        dependency_change = plan_feature_dependency_removal(
            state,
            curve_ids=curve_ids,
            preview_surface_ids=preview_ids,
            brep_surface_ids=brep_ids,
        )
        prune_feature_dependencies(state, dependency_change)
        state.section_collection.results = []
        state.section_collection.active_result_id = None
        state.section_collection.selected_result_ids.clear()
        state.curve_collection = CurveCollection()
        state.surface_collection = SurfaceCollection()
        state.brep_surface_collection = BrepSurfaceCollection()
        state.loft_feature_collection = LoftFeatureCollection()
        state.four_boundary_feature_collection = FourBoundaryPatchFeatureCollection()
        sync_display_section_result(state)
        after = capture_section_workflow_state(state)
        undo = self._workflow_undo("Clear All Section Results", before, after)
        return self._changed_result(
            status="All section results cleared",
            reason="all_section_results_cleared",
            object_ids=tuple((*curve_ids, *preview_ids, *brep_ids)),
            changed_fields=(
                "section_collection",
                "curve_collection",
                "surface_collection",
                "brep_surface_collection",
                "loft_feature_collection",
                "four_boundary_feature_collection",
            ),
            undo=undo,
            metadata=dependency_change.as_metadata(),
        )

    clear_all_section_results = clear_all_results

    def delete_plane(self, plane_id: str | None = None) -> CommandResult:
        if self.state.mesh_object is None:
            return CommandResult.failure("No mesh is loaded.", status="No selection")
        plane = self._plane(plane_id)
        if plane is None:
            created = self.ensure_default_plane()
            self.state.selected_item = SELECT_SECTION_PLANE
            return CommandResult.ok(
                status="Selected: Section Plane",
                changed=True,
                viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
                ui_requests=MODEL_SYNC_UI_REQUESTS,
                metadata={"section_plane_id": created.id},
            )

        before = capture_section_workflow_state(self.state)
        removed_name = plane.name or "Section Plane"
        change = invalidate_section_plane_dependencies(self.state, plane.id)
        remove_plane(self.state.section_collection, plane.id)
        replacement = self.ensure_default_plane()
        sync_display_section_result(self.state)
        self.state.selected_item = SELECT_SECTION_PLANE
        after = capture_section_workflow_state(self.state)
        undo = self._workflow_undo("Delete Section Plane", before, after)
        return self._changed_result(
            status=f"Deleted: {removed_name}",
            reason="section_plane_deleted",
            object_ids=(plane.id,),
            changed_fields=(
                "section_collection",
                "curve_collection",
                "surface_collection",
                "brep_surface_collection",
                "selected_item",
            ),
            undo=undo,
            metadata={
                "section_plane_id": plane.id,
                "active_section_plane_id": replacement.id,
                **change.as_metadata(),
            },
        )

    delete_active_section_plane = delete_plane

    def next_plane_name(self) -> str:
        names = {plane.name for plane in self.state.section_collection.planes}
        index = 1
        while f"Section Plane {index}" in names:
            index += 1
        return f"Section Plane {index}"

    def next_result_name(self) -> str:
        names = {result.name for result in self.state.section_collection.results}
        index = 1
        for name in names:
            if name.startswith("Section ") and name[8:].isdigit():
                index = max(index, int(name[8:]) + 1)
        while f"Section {index}" in names:
            index += 1
        return f"Section {index}"

    @staticmethod
    def is_axis_aligned(plane: SectionPlaneState) -> bool:
        axis_key = normalize_axis(plane.axis)
        normal = axis_normal(axis_key)
        origin_offset = float(np.dot(plane_origin(plane), normal))
        return bool(
            np.allclose(plane_normal(plane), normal, atol=1e-6)
            and abs(origin_offset - float(plane.offset)) <= 1e-6
        )

    def _plane(self, plane_id: str | None) -> SectionPlaneState | None:
        if plane_id is None:
            return get_active_plane(self.state.section_collection)
        return next(
            (
                plane
                for plane in self.state.section_collection.planes
                if plane.id == str(plane_id)
            ),
            None,
        )

    def _workflow_undo(
        self,
        name: str,
        before: SectionWorkflowSnapshot,
        after: SectionWorkflowSnapshot,
    ) -> CallbackUndoPayload:
        target_state = self.state

        def restore(snapshot: SectionWorkflowSnapshot, reason: str) -> None:
            restore_section_workflow_state(target_state, snapshot)
            publish_scene_change(
                self.events,
                reason=reason,
                changed_fields=(
                    "section_collection",
                    "curve_collection",
                    "surface_collection",
                    "brep_surface_collection",
                ),
            )

        return CallbackUndoPayload(
            name=name,
            undo_action=lambda: restore(before, "section_undo"),
            redo_action=lambda: restore(after, "section_redo"),
        )

    def _changed_result(
        self,
        *,
        status: str,
        reason: str,
        object_ids: tuple[str, ...],
        changed_fields: tuple[str, ...],
        undo: CallbackUndoPayload,
        metadata: dict[str, object],
    ) -> CommandResult:
        publish_scene_change(
            self.events,
            reason=reason,
            object_ids=object_ids,
            changed_fields=changed_fields,
        )
        return CommandResult.ok(
            status=status,
            changed=True,
            dirty=True,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=undo,
            metadata=metadata,
        )


def _finite_number(value: object, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a number.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite.")
    return number


__all__ = (
    "SectionController",
    "SectionWorkflowSnapshot",
    "capture_section_workflow_state",
    "invalidate_section_plane_dependencies",
    "invalidate_section_result_dependencies",
    "restore_section_workflow_state",
    "sync_display_section_result",
)
