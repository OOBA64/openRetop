"""UI-independent orchestration for non-manual stored-curve workflows."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from application.controller_support import (
    CallbackUndoPayload,
    ControllerBase,
    MODEL_SYNC_UI_REQUESTS,
    MODEL_SYNC_VIEWPORT_REQUESTS,
)
from application.events import SceneChangedEvent, SelectionChangedEvent
from application.feature_dependencies import (
    plan_feature_dependency_removal,
    prune_feature_dependencies,
)
from application.results import CommandResult
from application.selection import SelectionKind, SelectionSnapshot
from application.state import AppState
from curves.curve_state import (
    DEFAULT_CURVE_REPAIR_TOLERANCE,
    DEFAULT_CURVE_SIMPLIFY_TOLERANCE,
    DEFAULT_CURVE_SMOOTH_ITERATIONS,
    CurveCollection,
    CurveProcessingError,
    CurveRepairError,
    StoredCurve,
    add_curve,
    auto_close_curve,
    get_selected_curves,
    get_tiny_curves,
    join_curves,
    refresh_curve_diagnostics,
    remove_curve,
    set_active_curve,
    set_selected_curves,
    simplify_curve,
    smooth_curve,
)
from curves.projection import project_stored_curve_to_mesh
from curves.rebuild import rebuild_stored_curve
from curves.validation import (
    CurveSurfaceReadiness,
    validate_curve_for_fill,
    validate_curves_for_loft,
)
from mesh.triangle_mesh import TriangleMeshData
from surfaces.brep_state import BrepSurfaceCollection
from surfaces.four_boundary_feature import FourBoundaryPatchFeatureCollection
from surfaces.loft_feature import LoftFeatureCollection
from surfaces.surface_state import SurfaceCollection


class MeshQueryPort(Protocol):
    def query_closest_points(
        self,
        mesh: TriangleMeshData,
        points: object,
        *,
        mesh_revision: object | None = None,
        max_distance: float | None = None,
        preserve_missed_points: bool = True,
    ) -> object: ...


@dataclass
class _CurveMutationSnapshot:
    curve_collection: CurveCollection
    curve_results: list[object]
    surface_collection: SurfaceCollection
    brep_surface_collection: BrepSurfaceCollection
    loft_feature_collection: LoftFeatureCollection
    four_boundary_feature_collection: FourBoundaryPatchFeatureCollection
    selected_item: str | None

    @classmethod
    def capture(cls, state: AppState) -> _CurveMutationSnapshot:
        return cls(
            curve_collection=copy.deepcopy(state.curve_collection),
            curve_results=copy.deepcopy(state.curve_results),
            surface_collection=copy.deepcopy(state.surface_collection),
            brep_surface_collection=copy.deepcopy(state.brep_surface_collection),
            loft_feature_collection=copy.deepcopy(state.loft_feature_collection),
            four_boundary_feature_collection=copy.deepcopy(
                state.four_boundary_feature_collection
            ),
            selected_item=state.selected_item,
        )

    def restore(self, state: AppState) -> None:
        state.curve_collection = copy.deepcopy(self.curve_collection)
        state.curve_results = copy.deepcopy(self.curve_results)
        state.surface_collection = copy.deepcopy(self.surface_collection)
        state.brep_surface_collection = copy.deepcopy(self.brep_surface_collection)
        state.loft_feature_collection = copy.deepcopy(self.loft_feature_collection)
        state.four_boundary_feature_collection = copy.deepcopy(
            self.four_boundary_feature_collection
        )
        state.selected_item = self.selected_item


class CurveController(ControllerBase):
    """Coordinate existing stored-curve algorithms against explicit state."""

    def __init__(
        self,
        state: AppState,
        *,
        events=None,
        mesh_query_service: MeshQueryPort | None = None,
    ) -> None:
        super().__init__(state, events=events)
        self.mesh_query_service = mesh_query_service

    def join_selected(
        self,
        *,
        curve_id: str | None = None,
        name: str | None = None,
        tolerance: float = DEFAULT_CURVE_REPAIR_TOLERANCE,
    ) -> CommandResult:
        selected = self._selected_curves()
        if len(selected) < 2:
            return CommandResult.failure(
                "Select at least two curves to join.",
                status="Select at least two curves to join",
            )
        created_id = curve_id or self._new_curve_id()
        created_name = name or self._unique_name("Joined Curve")
        try:
            curve = join_curves(
                selected,
                curve_id=created_id,
                name=created_name,
                tolerance=tolerance,
            )
        except (CurveRepairError, ValueError) as exc:
            return CommandResult.failure(str(exc), status=str(exc))
        return self._add_generated_curve(
            curve,
            undo_name="Create Curve",
            status=(
                f"Created joined curve from {len(selected)} curves "
                f"(tolerance {float(tolerance):.3f})"
            ),
        )

    def auto_close_selected(
        self,
        *,
        curve_id: str | None = None,
        name: str | None = None,
        tolerance: float = DEFAULT_CURVE_REPAIR_TOLERANCE,
    ) -> CommandResult:
        source = self._single_selected_curve()
        if source is None:
            return CommandResult.failure(
                "Select exactly one open curve to auto-close.",
                status="Select exactly one open curve to auto-close",
            )
        refresh_curve_diagnostics(source)
        try:
            curve = auto_close_curve(
                source,
                curve_id=curve_id or self._new_curve_id(),
                name=name or self._unique_name("Auto-Closed Curve"),
                tolerance=tolerance,
            )
        except (CurveRepairError, ValueError) as exc:
            return CommandResult.failure(str(exc), status=str(exc))
        return self._add_generated_curve(
            curve,
            undo_name="Create Curve",
            status=(
                "Created auto-closed curve "
                f"(gap {source.endpoint_distance:.3f}, tolerance {float(tolerance):.3f})"
            ),
        )

    def simplify_selected(
        self,
        *,
        curve_id: str | None = None,
        name: str | None = None,
        tolerance: float = DEFAULT_CURVE_SIMPLIFY_TOLERANCE,
    ) -> CommandResult:
        source = self._single_selected_curve()
        if source is None:
            return CommandResult.failure(
                "Select exactly one curve to simplify.",
                status="Select exactly one curve to simplify",
            )
        try:
            curve = simplify_curve(
                source,
                curve_id=curve_id or self._new_curve_id(),
                name=name or self._unique_name("Simplified Curve"),
                tolerance=tolerance,
            )
        except (CurveProcessingError, ValueError) as exc:
            return CommandResult.failure(str(exc), status=str(exc))
        return self._add_generated_curve(
            curve,
            undo_name="Create Curve",
            status=(
                f"Simplified {source.name} from {source.point_count} to "
                f"{curve.point_count} points."
            ),
        )

    def smooth_selected(
        self,
        *,
        curve_id: str | None = None,
        name: str | None = None,
        iterations: int = DEFAULT_CURVE_SMOOTH_ITERATIONS,
    ) -> CommandResult:
        source = self._single_selected_curve()
        if source is None:
            return CommandResult.failure(
                "Select exactly one curve to smooth.",
                status="Select exactly one curve to smooth",
            )
        try:
            curve = smooth_curve(
                source,
                curve_id=curve_id or self._new_curve_id(),
                name=name or self._unique_name("Smoothed Curve"),
                iterations=iterations,
            )
        except (CurveProcessingError, ValueError) as exc:
            return CommandResult.failure(str(exc), status=str(exc))
        return self._add_generated_curve(
            curve,
            undo_name="Create Curve",
            status=(
                f"Created smoothed curve ({curve.point_count} points, "
                f"{int(iterations)} iterations)"
            ),
        )

    def project_selected_to_mesh(
        self,
        mesh: TriangleMeshData | None,
        *,
        source_mesh_name: str,
        mesh_revision: object | None = None,
        max_search_distance: float | None = None,
        curve_id: str | None = None,
        name: str | None = None,
    ) -> CommandResult:
        source = self._single_selected_curve(allow_active=True)
        if source is None:
            return CommandResult.failure(
                "Select one curve to project.", status="Select one curve to project."
            )
        if mesh is None or mesh.is_empty():
            return CommandResult.failure(
                "Load a mesh before projecting curves.",
                status="Load a mesh before projecting curves.",
            )
        if self.mesh_query_service is None:
            return CommandResult.failure(
                "Mesh query service is unavailable.",
                status="Mesh query service is unavailable.",
            )
        try:
            curve = project_stored_curve_to_mesh(
                source,
                mesh,
                curve_id=curve_id or self._new_curve_id(),
                name=name or self._unique_name("Projected Curve"),
                source_mesh_name=source_mesh_name,
                max_search_distance=max_search_distance,
                mesh_query_service=self.mesh_query_service,  # type: ignore[arg-type]
                mesh_revision=mesh_revision,
            )
        except (RuntimeError, TypeError, ValueError) as exc:
            return CommandResult.failure(str(exc), status=str(exc))
        warnings = tuple(str(item) for item in curve.metadata.get("projection_warnings", ()))
        return self._add_generated_curve(
            curve,
            undo_name="Project Curve to Mesh",
            status=(
                "Projected "
                f"{curve.metadata.get('projection_projected_count', 0)} points "
                f"to {curve.name}."
            ),
            warnings=warnings,
        )

    def rebuild_selected(
        self,
        *,
        target_control_point_count: int,
        curve_method: str,
        sample_count: int,
        curve_id: str | None = None,
        name: str | None = None,
    ) -> CommandResult:
        source = self._single_selected_curve(allow_active=True)
        if source is None:
            return CommandResult.failure(
                "Select one curve to rebuild.", status="Select one curve to rebuild."
            )
        try:
            curve = rebuild_stored_curve(
                source,
                curve_id=curve_id or self._new_curve_id(),
                name=name or self._unique_name("Rebuilt Curve"),
                target_control_point_count=target_control_point_count,
                curve_method=curve_method,
                sample_count=sample_count,
            )
        except (TypeError, ValueError) as exc:
            return CommandResult.failure(str(exc), status=str(exc))
        warnings = tuple(str(item) for item in curve.metadata.get("rebuild_warnings", ()))
        return self._add_generated_curve(
            curve,
            undo_name="Rebuild Curve",
            status=(
                f"Rebuilt {source.name} into {curve.name} "
                f"({curve.metadata.get('rebuild_target_control_point_count', 0)} controls)."
            ),
            warnings=warnings,
        )

    def validate_selected_for_fill(self) -> CommandResult:
        source = self._single_selected_curve(allow_active=True)
        if source is None:
            return CommandResult.failure(
                "Select curve(s) to validate.", status="Select curve(s) to validate."
            )
        readiness = validate_curve_for_fill(source)
        return self._readiness_result((readiness,), ready_status="Ready for Fill")

    def validate_selected_for_loft(self) -> CommandResult:
        selected = self._selected_curves()
        if not selected:
            return CommandResult.failure(
                "Select curve(s) to validate.", status="Select curve(s) to validate."
            )
        readiness = tuple(validate_curves_for_loft(selected))
        return self._readiness_result(readiness, ready_status="Ready for Loft")

    def select_tiny(self) -> CommandResult:
        curves = self.state.curve_collection.curves
        if not curves:
            return CommandResult.failure("No curves available", status="No curves available")
        for curve in curves:
            refresh_curve_diagnostics(curve)
        tiny = get_tiny_curves(self.state.curve_collection)
        if not tiny:
            return CommandResult.ok(status="No tiny curves found")
        ids = tuple(curve.id for curve in tiny)
        set_selected_curves(
            self.state.curve_collection,
            ids,
            active_curve_id=ids[0],
        )
        self.state.selected_item = "curve"
        self._publish_selection("tiny_curves_selected")
        return CommandResult.ok(
            status=("Selected tiny curve" if len(ids) == 1 else f"Selected {len(ids)} tiny curves"),
            changed=True,
            dirty=False,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            metadata={"selected_curve_ids": ids},
        )

    def delete_tiny(self) -> CommandResult:
        for curve in self.state.curve_collection.curves:
            refresh_curve_diagnostics(curve)
        ids = tuple(curve.id for curve in get_tiny_curves(self.state.curve_collection))
        if not self.state.curve_collection.curves:
            return CommandResult.failure("No curves available", status="No curves available")
        if not ids:
            return CommandResult.ok(status="No tiny curves found")
        return self.delete_curve_ids(ids, undo_name="Delete Tiny Curves")

    def delete_selected(self) -> CommandResult:
        ids = tuple(curve.id for curve in self._selected_curves())
        if not ids:
            return CommandResult.failure("No selected curves", status="No selected curves")
        return self.delete_curve_ids(ids, undo_name="Delete Curve")

    def delete_curve_ids(
        self,
        curve_ids: tuple[str, ...] | list[str],
        *,
        undo_name: str = "Delete Curve",
    ) -> CommandResult:
        requested = tuple(dict.fromkeys(str(curve_id) for curve_id in curve_ids))
        known = {curve.id for curve in self.state.curve_collection.curves}
        missing = tuple(curve_id for curve_id in requested if curve_id not in known)
        if missing:
            return CommandResult.failure(
                f"Curve not found: {missing[0]}", status=f"Curve not found: {missing[0]}"
            )
        if not requested:
            return CommandResult.ok(status="No curves deleted")

        state = self.state
        before = _CurveMutationSnapshot.capture(state)
        dependency_change = plan_feature_dependency_removal(
            state,
            curve_ids=requested,
        )
        prune_feature_dependencies(state, dependency_change)
        for curve_id in requested:
            remove_curve(state.curve_collection, curve_id)
        self._sync_curve_results(state)
        if state.selected_item == "curve" and not state.curve_collection.selected_curve_ids:
            state.selected_item = None
        after = _CurveMutationSnapshot.capture(state)
        affected_ids = (*requested, *dependency_change.removed_surface_ids)
        undo_payload = self._snapshot_undo(
            undo_name,
            state,
            before,
            after,
            affected_ids=affected_ids,
        )
        self._publish_scene("curves_deleted", affected_ids)
        self._publish_selection("curves_deleted")
        count = len(requested)
        metadata = {
            **dependency_change.as_metadata(),
            "removed_curve_ids": requested,
        }
        return CommandResult.ok(
            status=("Deleted curve" if count == 1 else f"Deleted {count} curves"),
            changed=True,
            dirty=True,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=undo_payload,
            metadata=metadata,
        )

    def _add_generated_curve(
        self,
        curve: StoredCurve,
        *,
        undo_name: str,
        status: str,
        warnings: tuple[str, ...] = (),
    ) -> CommandResult:
        state = self.state
        before = _CurveMutationSnapshot.capture(state)
        try:
            add_curve(state.curve_collection, curve)
            set_active_curve(state.curve_collection, curve.id)
        except ValueError as exc:
            before.restore(state)
            return CommandResult.failure(str(exc), status=str(exc))
        state.selected_item = "curve"
        self._sync_curve_results(state)
        after = _CurveMutationSnapshot.capture(state)
        undo_payload = self._snapshot_undo(
            undo_name,
            state,
            before,
            after,
            affected_ids=(curve.id,),
        )
        self._publish_scene("curve_created", (curve.id,))
        self._publish_selection("curve_created")
        source_ids = tuple(
            str(value) for value in curve.metadata.get("source_curve_ids", ())
        )
        return CommandResult.ok(
            status=status,
            changed=True,
            dirty=True,
            warnings=warnings,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=undo_payload,
            metadata={
                "created_curve_id": curve.id,
                "source_curve_ids": source_ids,
            },
        )

    def _snapshot_undo(
        self,
        name: str,
        state: AppState,
        before: _CurveMutationSnapshot,
        after: _CurveMutationSnapshot,
        *,
        affected_ids: tuple[str, ...],
    ) -> CallbackUndoPayload:
        def restore(snapshot: _CurveMutationSnapshot, reason: str) -> None:
            snapshot.restore(state)
            self._publish_scene(reason, affected_ids)
            self._publish_selection(reason)

        return CallbackUndoPayload(
            name=name,
            undo_action=lambda: restore(before, f"undo_{name.lower().replace(' ', '_')}"),
            redo_action=lambda: restore(after, f"redo_{name.lower().replace(' ', '_')}"),
        )

    def _readiness_result(
        self,
        readiness: tuple[CurveSurfaceReadiness, ...],
        *,
        ready_status: str,
    ) -> CommandResult:
        errors = tuple(
            str(error) for item in readiness for error in item.errors if str(error)
        )
        warnings = tuple(
            str(warning)
            for item in readiness
            for warning in item.warnings
            if str(warning)
        )
        metadata = {"readiness": readiness}
        if errors:
            return CommandResult.failure(
                *errors,
                status=errors[0],
                warnings=warnings,
                metadata=metadata,
            )
        return CommandResult.ok(
            status=warnings[0] if warnings else ready_status,
            warnings=warnings,
            metadata=metadata,
        )

    def _selected_curves(self) -> list[StoredCurve]:
        return get_selected_curves(self.state.curve_collection)

    def _single_selected_curve(self, *, allow_active: bool = False) -> StoredCurve | None:
        selected = self._selected_curves()
        if not selected and allow_active:
            active_id = self.state.curve_collection.active_curve_id
            selected = [
                curve
                for curve in self.state.curve_collection.curves
                if curve.id == active_id
            ]
        return selected[0] if len(selected) == 1 else None

    def _unique_name(self, base: str) -> str:
        names = {curve.name for curve in self.state.curve_collection.curves}
        if base not in names:
            return base
        index = 2
        while f"{base} {index}" in names:
            index += 1
        return f"{base} {index}"

    @staticmethod
    def _new_curve_id() -> str:
        return f"curve-{uuid4().hex}"

    @staticmethod
    def _sync_curve_results(state: AppState) -> None:
        state.curve_results = [
            curve for curve in state.curve_collection.curves if bool(curve.visible)
        ]

    def _publish_scene(self, reason: str, object_ids: tuple[str, ...]) -> None:
        self.events.publish(SceneChangedEvent(reason=reason, object_ids=object_ids))

    def _publish_selection(self, reason: str) -> None:
        selected_ids = tuple(
            curve.id
            for curve in self.state.curve_collection.curves
            if curve.id in self.state.curve_collection.selected_curve_ids
        )
        self.events.publish(
            SelectionChangedEvent(
                SelectionSnapshot.from_ids(selected_ids, kind=SelectionKind.CURVE),
                reason=reason,
            )
        )


__all__ = ("CurveController", "MeshQueryPort")
