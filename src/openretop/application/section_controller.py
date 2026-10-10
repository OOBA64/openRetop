"""UI-independent controller for section-plane and section-result workflows.

A computed section is the scan's cut by a plane, kept as a section result; each loop of the
cut also becomes a Surface Sketch curve (the user's own geometry from then on: lofted, filled,
edited like any curve, and not deleted with the section).
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from uuid import uuid4

import numpy as np

from openretop.application.controller_support import (
    MODEL_SYNC_UI_REQUESTS,
    MODEL_SYNC_VIEWPORT_REQUESTS,
    CallbackUndoPayload,
    ControllerBase,
    publish_scene_change,
)
from openretop.application.results import CommandResult
from openretop.application.state import AppState
from openretop.geometry.curves import fit_section_polylines
from openretop.geometry.sections import extract_section, extract_section_by_plane, normalize_axis
from openretop.geometry.tolerances import curve_fit_tolerance
from openretop.sections.section_state import (
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

SELECT_SECTION_PLANE = "section_plane"


@dataclass(slots=True)
class SectionWorkflowSnapshot:
    """Copy of the state a section command changes (not the potentially large mesh)."""

    section_collection: SectionCollection
    sketch: object
    section_result: object | None
    selected_item: str | None


def capture_section_workflow_state(state: AppState) -> SectionWorkflowSnapshot:
    return SectionWorkflowSnapshot(
        section_collection=copy.deepcopy(state.section_collection),
        sketch=state.model.sketch.copy(),
        section_result=copy.deepcopy(state.section_result),
        selected_item=state.selected_item,
    )


def restore_section_workflow_state(state: AppState, snapshot: SectionWorkflowSnapshot) -> None:
    """Restore a snapshot without sharing its mutable collections with callers."""

    state.section_collection = copy.deepcopy(snapshot.section_collection)
    state.model.sketch = snapshot.sketch.copy()  # type: ignore[attr-defined]
    known = {curve.id for curve in state.model.sketch.curves}
    state.model.selected_curve_ids = [value for value in state.model.selected_curve_ids if value in known]
    state.model.revision += 1
    state.section_result = copy.deepcopy(snapshot.section_result)
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
    return stored_result


def invalidate_section_plane_dependencies(state: AppState, plane_id: str) -> None:
    """Remove the results cut by one plane (their sketch curves stay: they are the user's)."""

    clear_results_for_plane(state.section_collection, str(plane_id))
    sync_display_section_result(state)


def invalidate_section_result_dependencies(state: AppState, result_id: str) -> None:
    """Remove one stored result (its sketch curves stay)."""

    normalized_id = str(result_id)
    state.section_collection.results = [result for result in state.section_collection.results if result.id != normalized_id]
    state.section_collection.selected_result_ids.discard(normalized_id)
    if state.section_collection.active_result_id == normalized_id:
        state.section_collection.active_result_id = None
    sync_display_section_result(state)


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
        if geometry_changed:
            invalidate_section_plane_dependencies(self.state, plane.id)
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
        }
        return self._changed_result(
            status=status,
            reason="section_plane_changed",
            object_ids=(plane.id,),
            changed_fields=("section_collection", "model"),
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

    def _curve_fit_tolerance(self, mesh: object) -> float:
        bounds = mesh.get_axis_aligned_bounding_box()
        return curve_fit_tolerance(float(bounds.get_max_extent()), self.state.units)

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
            curve_fits = tuple(
                fit_section_polylines(
                    section_result.polylines,
                    tolerance=self._curve_fit_tolerance(mesh),
                )
            )
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
        sketch = self.state.model.sketch
        # scraps where the plane grazes a scan fragment (a couple of points, a few tenths of a
        # millimetre) are not curves anyone wants to loft: leave them in the section only
        extent = mesh.get_axis_aligned_bounding_box().get_max_extent()
        shortest = 0.005 * float(extent)
        skipped = 0
        for curve_fit in curve_fits:
            points = curve_fit.fitted_points if len(curve_fit.fitted_points) >= 2 else curve_fit.original_points
            points = np.asarray(points, dtype=float).reshape(-1, 3)
            length = float(np.sum(np.linalg.norm(np.diff(points, axis=0), axis=1))) if len(points) >= 2 else 0.0
            if len(points) < 3 or length < shortest:
                skipped += 1
                continue
            name = f"{stored.name} Curve {len(created_curve_ids) + 1}"
            curve = sketch.add_polyline_curve(points, closed=bool(curve_fit.is_closed), name=name)
            created_curve_ids.append(curve.id)
        self.state.model.selected_curve_ids = list(created_curve_ids)
        self.state.model.revision += 1
        sync_display_section_result(self.state, stored)
        after = capture_section_workflow_state(self.state)
        undo = self._workflow_undo("Compute Section", before, after)
        status = (
            f"Computed arbitrary section from {plane.name}"
            if arbitrary
            else f"Section computed: {stored.name} - {section_result.segment_count} segments"
        ) + f", {len(created_curve_ids)} curve(s)" + (f" ({skipped} scrap(s) left out)" if skipped else "")
        return self._changed_result(
            status=status,
            reason="section_computed",
            object_ids=(stored.id, *created_curve_ids),
            changed_fields=("section_collection", "model"),
            undo=undo,
            metadata={
                "section_result_id": stored.id,
                "curve_ids": tuple(created_curve_ids),
                "skipped_scraps": skipped,
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
        if not has_results:
            return CommandResult.ok(status="Section cleared")

        before = capture_section_workflow_state(self.state)
        invalidate_section_plane_dependencies(self.state, plane.id)
        after = capture_section_workflow_state(self.state)
        undo = self._workflow_undo("Clear Section", before, after)
        return self._changed_result(
            status="Section cleared",
            reason="section_results_cleared",
            object_ids=(plane.id,),
            changed_fields=("section_collection", "model"),
            undo=undo,
            metadata={},
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
        invalidate_section_result_dependencies(self.state, result.id)
        after = capture_section_workflow_state(self.state)
        undo = self._workflow_undo("Delete Section Result", before, after)
        return self._changed_result(
            status=f"Deleted: {result.name}",
            reason="section_result_deleted",
            object_ids=(result.id,),
            changed_fields=("section_collection", "model"),
            undo=undo,
            metadata={},
        )

    def clear_all_results(self) -> CommandResult:
        """Every section result goes (the sketch curves made from them stay)."""

        state = self.state
        if not state.section_collection.results:
            return CommandResult.ok(status="All section results cleared")
        before = capture_section_workflow_state(state)
        result_ids = tuple(result.id for result in state.section_collection.results)
        state.section_collection.results = []
        state.section_collection.active_result_id = None
        state.section_collection.selected_result_ids.clear()
        sync_display_section_result(state)
        after = capture_section_workflow_state(state)
        undo = self._workflow_undo("Clear All Section Results", before, after)
        return self._changed_result(
            status="All section results cleared",
            reason="all_section_results_cleared",
            object_ids=result_ids,
            changed_fields=("section_collection",),
            undo=undo,
            metadata={},
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
        invalidate_section_plane_dependencies(self.state, plane.id)
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
            changed_fields=("section_collection", "model", "selected_item"),
            undo=undo,
            metadata={
                "section_plane_id": plane.id,
                "active_section_plane_id": replacement.id,
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
                changed_fields=("section_collection", "model"),
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
