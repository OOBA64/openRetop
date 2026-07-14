"""UI-independent preview-surface workflow controller."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import math
from typing import Sequence
from uuid import uuid4

import numpy as np

from application.controller_support import (
    CallbackUndoPayload,
    ControllerBase,
    MODEL_SYNC_UI_REQUESTS,
    MODEL_SYNC_VIEWPORT_REQUESTS,
    SelectionFamilySnapshot,
    publish_scene_change,
    select_surface_exclusively,
    selection_snapshot_for_state,
)
from application.events import SelectionChangedEvent
from application.feature_dependencies import (
    plan_feature_dependency_removal,
    prune_feature_dependencies,
)
from application.results import CommandResult
from application.state import AppState
from curves.curve_state import StoredCurve, get_selected_curves, refresh_curve_diagnostics
from curves.validation import (
    CurveSurfaceReadiness,
    validate_curve_for_fill,
    validate_curves_for_loft,
)
from surfaces.four_boundary_feature import (
    FourBoundaryPatchFeatureCollection,
    FourBoundaryPatchFeatureRecord,
    add_four_boundary_feature,
    mark_four_boundary_features_dirty_for_curve,
)
from surfaces.brep_state import (
    BrepSurfaceCollection,
    clear_brep_surface_selection,
    set_active_brep_surface,
)
from surfaces.loft_feature import LoftFeatureCollection
from surfaces.surface_preview import (
    BOUNDARY_PATCH,
    CLOSED_CURVE_FILL,
    CURVE_NETWORK_PATCH,
    FOUR_CURVE_PATCH,
    MESH_CONFORMING_LOFT,
    TWO_CURVE_LOFT,
    SurfacePreviewBuildResult,
    build_surface_preview,
)
from surfaces.surface_state import (
    SurfaceCollection,
    SurfacePatch,
    add_surface,
    get_active_surface,
    remove_surface,
    set_active_surface,
)


@dataclass(frozen=True, slots=True)
class SurfaceWorkflowSnapshot:
    """State covered by one preview-surface undo payload."""

    surfaces: SurfaceCollection
    brep_surfaces: BrepSurfaceCollection
    loft_features: LoftFeatureCollection
    four_boundary_features: FourBoundaryPatchFeatureCollection
    selection: SelectionFamilySnapshot


class SurfaceController(ControllerBase):
    """Create and mutate preview surfaces without widgets or render actors."""

    def __init__(
        self,
        state: AppState,
        events=None,
        *,
        mesh_query_service: object | None = None,
    ) -> None:
        super().__init__(state, events)
        self._mesh_query_service = mesh_query_service

    @property
    def mesh_query_service(self) -> object | None:
        return self._mesh_query_service

    def create_fill(
        self,
        *,
        curve_ids: Sequence[str] | None = None,
        surface_id: str | None = None,
        name: str | None = None,
    ) -> CommandResult:
        if not self.state.curve_collection.curves:
            return CommandResult.failure("No curves available", status="No curves available")
        if (failure := self._validate_new_ids(surface_id=surface_id)) is not None:
            return failure
        if (failure := self._validate_requested_curve_ids(curve_ids)) is not None:
            return failure
        curves = self._source_curves(curve_ids)
        if len(curves) != 1:
            return CommandResult.failure("Select exactly one closed curve to fill")
        readiness = validate_curve_for_fill(curves[0])
        if readiness.errors:
            return CommandResult.failure(
                *readiness.errors,
                warnings=tuple(readiness.warnings),
                metadata={"readiness": (readiness,)},
            )
        return self.create_preview(
            curves,
            surface_type="preview_fill",
            preview_mode=CLOSED_CURVE_FILL,
            source_label="selected_curve",
            name_prefix="Fill Surface",
            success_action="Filled",
            surface_id=surface_id,
            name=name,
            readiness=(readiness,),
        )

    def create_loft(
        self,
        *,
        curve_ids: Sequence[str] | None = None,
        surface_id: str | None = None,
        name: str | None = None,
    ) -> CommandResult:
        if not self.state.curve_collection.curves:
            return CommandResult.failure("No curves available", status="No curves available")
        if (failure := self._validate_new_ids(surface_id=surface_id)) is not None:
            return failure
        if (failure := self._validate_requested_curve_ids(curve_ids)) is not None:
            return failure
        curves = self._source_curves(curve_ids)
        if len(curves) != 2:
            return CommandResult.failure("Select exactly two curves to loft")
        readiness = validate_curves_for_loft(curves)
        errors = _readiness_errors(readiness)
        if errors:
            return CommandResult.failure(
                *errors,
                warnings=tuple(_readiness_warnings(readiness)),
                metadata={"readiness": tuple(readiness)},
            )
        return self.create_preview(
            curves,
            surface_type="preview_loft",
            preview_mode=TWO_CURVE_LOFT,
            source_label="selected_curves",
            name_prefix="Loft Surface",
            success_action="Lofted",
            surface_id=surface_id,
            name=name,
            readiness=readiness,
        )

    def create_mesh_conforming_loft(
        self,
        *,
        curve_ids: Sequence[str] | None = None,
        mesh: object | None,
        mesh_revision: object | None = None,
        source_mesh_name: str = "",
        projection_distance_threshold: float | None = 0.05,
        show_projection_error_heatmap: bool = False,
        surface_id: str | None = None,
        name: str | None = None,
    ) -> CommandResult:
        if mesh is None:
            return CommandResult.failure(
                "Load a mesh before creating a conforming loft preview."
            )
        if (failure := self._validate_new_ids(surface_id=surface_id)) is not None:
            return failure
        if (failure := self._validate_requested_curve_ids(curve_ids)) is not None:
            return failure
        curves = self._source_curves(curve_ids)
        if len(curves) < 2:
            return CommandResult.failure(
                "Select at least two open curves for a mesh-conforming loft preview."
            )
        if any(curve.is_closed for curve in curves):
            return CommandResult.failure(
                "Mesh-conforming loft preview requires open curves."
            )
        return self.create_preview(
            curves,
            surface_type="mesh_conforming_loft_preview",
            preview_mode=MESH_CONFORMING_LOFT,
            source_label="selected_open_curves",
            name_prefix="Conforming Loft Preview",
            success_action="Created",
            surface_id=surface_id,
            name=name,
            mesh=mesh,
            mesh_revision=mesh_revision,
            extra_metadata={
                "conforming_preview": True,
                "source_mesh_name": str(source_mesh_name),
                "projection_distance_threshold": projection_distance_threshold,
                "show_projection_error_heatmap": bool(
                    show_projection_error_heatmap
                ),
                "wireframe_overlay": False,
                "is_brep": False,
            },
        )

    def create_boundary_patch(
        self,
        *,
        curve_ids: Sequence[str] | None = None,
        surface_id: str | None = None,
        name: str | None = None,
    ) -> CommandResult:
        if not self.state.curve_collection.curves:
            return CommandResult.failure("No curves available", status="No curves available")
        if (failure := self._validate_new_ids(surface_id=surface_id)) is not None:
            return failure
        if (failure := self._validate_requested_curve_ids(curve_ids)) is not None:
            return failure
        curves = self._source_curves(curve_ids)
        if len(curves) != 1:
            return CommandResult.failure(
                "Create Boundary Patch requires one closed curve."
            )
        readiness = validate_curve_for_fill(curves[0])
        if readiness.errors:
            message = (
                "Create Boundary Patch requires one closed curve."
                if not readiness.is_closed
                else readiness.errors[0]
            )
            return CommandResult.failure(
                message,
                warnings=tuple(readiness.warnings),
                metadata={"readiness": (readiness,)},
            )
        curve = curves[0]
        return self.create_preview(
            curves,
            surface_type="preview_boundary_patch",
            preview_mode=BOUNDARY_PATCH,
            source_label="selected_curve",
            name_prefix="Boundary Patch",
            success_action="Created",
            surface_id=surface_id,
            name=name,
            readiness=(readiness,),
            extra_metadata={
                "boundary_curve_id": curve.id,
                "boundary_curve_name": curve.name,
            },
        )

    def create_four_curve_patch(
        self,
        *,
        curve_ids: Sequence[str] | None = None,
        surface_id: str | None = None,
        feature_id: str | None = None,
        name: str | None = None,
    ) -> CommandResult:
        if not self.state.curve_collection.curves:
            return CommandResult.failure("No curves available", status="No curves available")
        if (
            failure := self._validate_new_ids(
                surface_id=surface_id,
                feature_id=feature_id,
            )
        ) is not None:
            return failure
        if (failure := self._validate_requested_curve_ids(curve_ids)) is not None:
            return failure
        curves = self._source_curves(curve_ids)
        warnings, errors = _surface_patch_validation_messages(
            curves, preview_mode=FOUR_CURVE_PATCH
        )
        if errors:
            return CommandResult.failure(*errors, warnings=tuple(warnings))
        result = self.create_preview(
            curves,
            surface_type="preview_four_curve_patch",
            preview_mode=FOUR_CURVE_PATCH,
            source_label="selected_curves",
            name_prefix="Four-Curve Patch",
            success_action="Created",
            surface_id=surface_id,
            name=name,
            validation_warnings=warnings,
            extra_metadata={"curve_order": [curve.id for curve in curves]},
            create_four_boundary_feature=True,
            feature_id=feature_id,
        )
        return result

    def create_curve_network_patch(
        self,
        *,
        curve_ids: Sequence[str] | None = None,
        surface_id: str | None = None,
        name: str | None = None,
    ) -> CommandResult:
        if not self.state.curve_collection.curves:
            return CommandResult.failure("No curves available", status="No curves available")
        if (failure := self._validate_new_ids(surface_id=surface_id)) is not None:
            return failure
        if (failure := self._validate_requested_curve_ids(curve_ids)) is not None:
            return failure
        curves = self._source_curves(curve_ids)
        warnings, errors = _surface_patch_validation_messages(
            curves, preview_mode=CURVE_NETWORK_PATCH
        )
        if errors:
            return CommandResult.failure(*errors, warnings=tuple(warnings))
        return self.create_preview(
            curves,
            surface_type="preview_curve_network_patch",
            preview_mode=CURVE_NETWORK_PATCH,
            source_label="selected_curves",
            name_prefix="Network Patch",
            success_action="Created",
            surface_id=surface_id,
            name=name,
            validation_warnings=warnings,
        )

    def create_preview(
        self,
        source_curves: Sequence[StoredCurve],
        *,
        surface_type: str,
        preview_mode: str,
        source_label: str,
        name_prefix: str,
        success_action: str,
        surface_id: str | None = None,
        name: str | None = None,
        readiness: Sequence[CurveSurfaceReadiness] | None = None,
        validation_warnings: Sequence[str] = (),
        validation_errors: Sequence[str] = (),
        extra_metadata: dict[str, object] | None = None,
        mesh: object | None = None,
        mesh_revision: object | None = None,
        create_four_boundary_feature: bool = False,
        feature_id: str | None = None,
    ) -> CommandResult:
        curves = list(source_curves)
        if not curves:
            return CommandResult.failure("No curves available.")
        existing_ids = {curve.id for curve in self.state.curve_collection.curves}
        missing_ids = [curve.id for curve in curves if curve.id not in existing_ids]
        if missing_ids:
            return CommandResult.failure(
                f"Source curve not found: {missing_ids[0]}",
                metadata={"missing_curve_ids": tuple(missing_ids)},
            )
        if surface_id is not None and any(
            item.id == str(surface_id)
            for item in self.state.surface_collection.surfaces
        ):
            return CommandResult.failure(
                f"Surface ID already exists: {surface_id}",
                metadata={"duplicate_surface_id": str(surface_id)},
            )
        if create_four_boundary_feature and feature_id is not None and any(
            item.id == str(feature_id)
            for item in self.state.four_boundary_feature_collection.features
        ):
            return CommandResult.failure(
                f"Four-boundary feature ID already exists: {feature_id}",
                metadata={"duplicate_feature_id": str(feature_id)},
            )

        metadata: dict[str, object] = {
            "curve_count": len(curves),
            "source_curve_count": len(curves),
            "source_curve_ids": [curve.id for curve in curves],
            "source_curve_names": [curve.name for curve in curves],
            "source": str(source_label),
            "preview_mode": str(preview_mode),
            "source_curve_validation_warnings": [],
            "source_curve_validation_errors": [],
        }
        if preview_mode == TWO_CURVE_LOFT:
            metadata.update(
                {
                    "overbuild_enabled": True,
                    "overbuild_amount": 0.10,
                    "overbuild_u_start": 0.10,
                    "overbuild_u_end": 0.10,
                    "overbuild_v_start": 0.10,
                    "overbuild_v_end": 0.10,
                    "show_overbuild_handles": True,
                    "overbuild_preview_only": True,
                }
            )
        metadata.update(_surface_source_lineage_metadata(curves))
        if readiness is not None:
            metadata.update(_surface_validation_metadata(readiness))
        metadata["source_curve_validation_warnings"] = _merged_metadata_strings(
            metadata.get("source_curve_validation_warnings"), validation_warnings
        )
        metadata["source_curve_validation_errors"] = _merged_metadata_strings(
            metadata.get("source_curve_validation_errors"), validation_errors
        )
        if extra_metadata:
            metadata.update(copy.deepcopy(extra_metadata))

        surface = SurfacePatch(
            id=str(surface_id or f"surface-{uuid4().hex}"),
            name=str(name or self._next_surface_name(name_prefix)),
            source_curve_ids=[curve.id for curve in curves],
            surface_type=str(surface_type),
            metadata=metadata,
        )
        preview_result = build_surface_preview(
            surface,
            self.state.curve_collection.curves,
            mesh=mesh,
            mesh_query_service=self._mesh_query_service,
            mesh_revision=mesh_revision,
        )
        _apply_preview_diagnostics(surface, preview_result)
        if preview_result.mesh is None:
            return CommandResult.failure(
                f"Surface preview unavailable: {preview_result.reason}",
                warnings=(() if preview_result.warning is None else (preview_result.warning,)),
                metadata={"preview_result": preview_result, "surface": surface},
            )

        before = self._snapshot()
        try:
            add_surface(self.state.surface_collection, surface)
            created_feature: FourBoundaryPatchFeatureRecord | None = None
            if create_four_boundary_feature:
                created_feature = FourBoundaryPatchFeatureRecord(
                    id=str(feature_id or f"four-boundary-feature-{uuid4().hex}"),
                    name=surface.name,
                    source_curve_ids=[curve.id for curve in curves],
                    preserve_corners=True,
                    match_directions=True,
                    fill_method="coons_preview",
                    preview_surface_id=surface.id,
                    last_build_status="Four-boundary patch preview built.",
                    metadata={"four_boundary_feature_dirty": False},
                )
                add_four_boundary_feature(
                    self.state.four_boundary_feature_collection, created_feature
                )
                surface.metadata["four_boundary_feature_id"] = created_feature.id
                surface.metadata["editable_feature"] = True
            select_surface_exclusively(self.state, surface.id, brep=False)
        except Exception:
            self._restore(before, reason="surface_create_rollback")
            raise
        after = self._snapshot()
        undo = self._undo_payload("Create Surface", before, after)
        publish_scene_change(
            self.events,
            reason="surface_created",
            object_ids=(surface.id,),
            changed_fields=("surface_collection", "four_boundary_feature_collection"),
        )
        self.events.publish(
            SelectionChangedEvent(
                selection_snapshot_for_state(self.state),
                reason="surface_created",
            )
        )
        curve_label = "curve" if len(curves) == 1 else "curves"
        status = f"{success_action} {surface.name} from {len(curves)} {curve_label}"
        warnings = _merged_metadata_strings(
            surface.metadata.get("source_curve_validation_warnings"),
            (() if preview_result.warning is None else (preview_result.warning,)),
        )
        return CommandResult.ok(
            status=status,
            changed=True,
            dirty=True,
            warnings=tuple(warnings),
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=undo,
            metadata={
                "created_surface_id": surface.id,
                "surface": surface,
                "preview_result": preview_result,
                "created_feature_id": (
                    None if created_feature is None else created_feature.id
                ),
            },
        )

    def rebuild_four_boundary_feature(
        self,
        surface_id: str | None = None,
        *,
        mesh: object | None = None,
        mesh_revision: object | None = None,
    ) -> CommandResult:
        surface = self._surface(surface_id)
        if surface is None:
            return CommandResult.failure(
                "Select a four-boundary patch feature to rebuild."
            )
        feature = next(
            (
                item
                for item in self.state.four_boundary_feature_collection.features
                if item.preview_surface_id == surface.id
            ),
            None,
        )
        if feature is None:
            return CommandResult.failure(
                "Selected surface is not an editable four-boundary patch."
            )
        before = self._snapshot()
        result = build_surface_preview(
            surface,
            self.state.curve_collection.curves,
            mesh=mesh,
            mesh_query_service=self._mesh_query_service,
            mesh_revision=mesh_revision,
        )
        _apply_preview_diagnostics(surface, result)
        feature.last_build_status = result.reason
        feature.metadata["four_boundary_feature_dirty"] = not result.preview_available
        after = self._snapshot()
        publish_scene_change(
            self.events,
            reason="four_boundary_feature_rebuilt",
            object_ids=(surface.id, feature.id),
            changed_fields=("surface_collection", "four_boundary_feature_collection"),
        )
        status = (
            "Rebuilt four-boundary patch feature."
            if result.preview_available
            else result.reason
        )
        return CommandResult.ok(
            status=status,
            changed=True,
            dirty=True,
            warnings=(() if result.warning is None else (result.warning,)),
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=self._undo_payload(
                "Rebuild Four-Boundary Patch", before, after
            ),
            metadata={"surface": surface, "feature": feature, "preview_result": result},
        )

    def update_surface(
        self,
        surface_id: str,
        *,
        name: str | None = None,
        visible: bool | None = None,
        opacity: float | None = None,
        wireframe_overlay: bool | None = None,
    ) -> CommandResult:
        surface = self._surface(surface_id)
        if surface is None:
            return CommandResult.failure(f"Surface not found: {surface_id}")

        candidate_name: str | None = None
        candidate_opacity: float | None = None
        if name is not None:
            candidate_name = str(name).strip()
            if not candidate_name:
                return CommandResult.failure("Surface name cannot be empty.")
            if any(
                other.id != surface.id and other.name == candidate_name
                for other in self.state.surface_collection.surfaces
            ):
                return CommandResult.failure(
                    f"Surface name already exists: {candidate_name}"
                )
        if opacity is not None:
            try:
                candidate_opacity = float(opacity)
            except (TypeError, ValueError):
                return CommandResult.failure("Surface opacity must be a number.")
            if not math.isfinite(candidate_opacity):
                return CommandResult.failure("Surface opacity must be finite.")
            candidate_opacity = min(max(candidate_opacity, 0.05), 1.0)

        before = self._snapshot()
        changed_fields: list[str] = []
        if candidate_name is not None:
            if candidate_name != surface.name:
                surface.name = candidate_name
                changed_fields.append("name")
        if visible is not None and bool(visible) != surface.visible:
            surface.visible = bool(visible)
            changed_fields.append("visible")
        if candidate_opacity is not None:
            if (
                float(surface.metadata.get("display_opacity", 0.22))
                != candidate_opacity
            ):
                surface.metadata["display_opacity"] = candidate_opacity
                changed_fields.append("display_opacity")
        if wireframe_overlay is not None:
            value = bool(wireframe_overlay)
            if bool(surface.metadata.get("wireframe_overlay", False)) != value:
                surface.metadata["wireframe_overlay"] = value
                changed_fields.append("wireframe_overlay")
        if not changed_fields:
            return CommandResult.ok(status=f"Selected: {surface.name}")
        after = self._snapshot()
        publish_scene_change(
            self.events,
            reason="surface_updated",
            object_ids=(surface.id,),
            changed_fields=changed_fields,
        )
        return CommandResult.ok(
            status=f"Updated: {surface.name}",
            changed=True,
            dirty=True,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=self._undo_payload("Update Surface", before, after),
            metadata={"surface": surface, "changed_fields": tuple(changed_fields)},
        )

    def delete_surface(self, surface_id: str | None = None) -> CommandResult:
        surface = self._surface(surface_id)
        if surface is None:
            return CommandResult.failure("Select a surface to delete.")
        before = self._snapshot()
        dependency_change = plan_feature_dependency_removal(
            self.state,
            preview_surface_ids=(surface.id,),
        )
        prune_feature_dependencies(self.state, dependency_change)
        if not self.state.surface_collection.surfaces:
            breps = self.state.brep_surface_collection.surfaces
            if breps:
                set_active_brep_surface(
                    self.state.brep_surface_collection, breps[0].id
                )
                self.state.selected_item = "surface"
            else:
                clear_brep_surface_selection(self.state.brep_surface_collection)
                self.state.selected_item = None
        after = self._snapshot()
        publish_scene_change(
            self.events,
            reason="surface_deleted",
            object_ids=(
                *dependency_change.removed_surface_ids,
                *dependency_change.removed_loft_feature_ids,
                *dependency_change.removed_four_boundary_feature_ids,
            ),
            changed_fields=(
                "surface_collection",
                "brep_surface_collection",
                "loft_feature_collection",
                "four_boundary_feature_collection",
            ),
        )
        self.events.publish(
            SelectionChangedEvent(
                selection_snapshot_for_state(self.state),
                reason="surface_deleted",
            )
        )
        return CommandResult.ok(
            status=f"Deleted: {surface.name}",
            changed=True,
            dirty=True,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=self._undo_payload("Delete Surface", before, after),
            metadata={
                "deleted_surface_id": surface.id,
                **dependency_change.as_metadata(),
            },
        )

    def mark_source_curve_changed(self, curve_id: str) -> CommandResult:
        changed = mark_four_boundary_features_dirty_for_curve(
            self.state.four_boundary_feature_collection, curve_id
        )
        if not changed:
            return CommandResult.ok(status="No dependent surface features.")
        feature_ids = tuple(feature.id for feature in changed)
        publish_scene_change(
            self.events,
            reason="surface_source_curve_changed",
            object_ids=(str(curve_id), *feature_ids),
            changed_fields=("four_boundary_feature_collection",),
        )
        return CommandResult.ok(
            status=f"Marked {len(changed)} surface feature(s) dirty.",
            changed=True,
            dirty=True,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            metadata={"dirty_feature_ids": feature_ids},
        )

    def _source_curves(
        self, curve_ids: Sequence[str] | None
    ) -> list[StoredCurve]:
        if curve_ids is None:
            selected = get_selected_curves(self.state.curve_collection)
            if selected:
                return selected
            active_id = self.state.curve_collection.active_curve_id
            if active_id is None:
                return []
            curve_ids = (active_id,)
        curve_by_id = {
            curve.id: curve for curve in self.state.curve_collection.curves
        }
        return [curve_by_id[curve_id] for curve_id in curve_ids if curve_id in curve_by_id]

    def _validate_requested_curve_ids(
        self,
        curve_ids: Sequence[str] | None,
    ) -> CommandResult | None:
        if curve_ids is None:
            return None
        requested = [str(value) for value in curve_ids]
        if len(requested) != len(set(requested)):
            return CommandResult.failure(
                "Source curve IDs must be unique.",
                metadata={"duplicate_curve_ids": tuple(requested)},
            )
        existing = {curve.id for curve in self.state.curve_collection.curves}
        missing = tuple(value for value in requested if value not in existing)
        if missing:
            return CommandResult.failure(
                f"Source curve not found: {missing[0]}",
                metadata={"missing_curve_ids": missing},
            )
        return None

    def _validate_new_ids(
        self,
        *,
        surface_id: str | None = None,
        feature_id: str | None = None,
    ) -> CommandResult | None:
        if surface_id is not None and any(
            item.id == str(surface_id)
            for item in self.state.surface_collection.surfaces
        ):
            return CommandResult.failure(
                f"Surface ID already exists: {surface_id}",
                metadata={"duplicate_surface_id": str(surface_id)},
            )
        if feature_id is not None and any(
            item.id == str(feature_id)
            for item in self.state.four_boundary_feature_collection.features
        ):
            return CommandResult.failure(
                f"Four-boundary feature ID already exists: {feature_id}",
                metadata={"duplicate_feature_id": str(feature_id)},
            )
        return None

    def _surface(self, surface_id: str | None) -> SurfacePatch | None:
        if surface_id is None:
            return get_active_surface(self.state.surface_collection)
        return next(
            (
                surface
                for surface in self.state.surface_collection.surfaces
                if surface.id == str(surface_id)
            ),
            None,
        )

    def _next_surface_name(self, prefix: str) -> str:
        existing_names = {
            surface.name for surface in self.state.surface_collection.surfaces
        }
        index = 1
        while f"{prefix} {index}" in existing_names:
            index += 1
        return f"{prefix} {index}"

    def _snapshot(self) -> SurfaceWorkflowSnapshot:
        return SurfaceWorkflowSnapshot(
            surfaces=copy.deepcopy(self.state.surface_collection),
            brep_surfaces=copy.deepcopy(self.state.brep_surface_collection),
            loft_features=copy.deepcopy(self.state.loft_feature_collection),
            four_boundary_features=copy.deepcopy(
                self.state.four_boundary_feature_collection
            ),
            selection=SelectionFamilySnapshot.capture(self.state),
        )

    def _restore(self, snapshot: SurfaceWorkflowSnapshot, *, reason: str) -> None:
        self.state.surface_collection = copy.deepcopy(snapshot.surfaces)
        self.state.brep_surface_collection = copy.deepcopy(snapshot.brep_surfaces)
        self.state.loft_feature_collection = copy.deepcopy(snapshot.loft_features)
        self.state.four_boundary_feature_collection = copy.deepcopy(
            snapshot.four_boundary_features
        )
        snapshot.selection.restore(self.state)
        publish_scene_change(
            self.events,
            reason=reason,
            object_ids=(
                *(surface.id for surface in self.state.surface_collection.surfaces),
                *(
                    feature.id
                    for feature in self.state.four_boundary_feature_collection.features
                ),
            ),
            changed_fields=(
                "surface_collection",
                "brep_surface_collection",
                "loft_feature_collection",
                "four_boundary_feature_collection",
            ),
        )
        self.events.publish(
            SelectionChangedEvent(
                selection_snapshot_for_state(self.state),
                reason=reason,
            )
        )

    def _undo_payload(
        self,
        name: str,
        before: SurfaceWorkflowSnapshot,
        after: SurfaceWorkflowSnapshot,
    ) -> CallbackUndoPayload:
        return CallbackUndoPayload(
            name,
            undo_action=lambda: self._restore(before, reason="surface_undo"),
            redo_action=lambda: self._restore(after, reason="surface_redo"),
        )


def _apply_preview_diagnostics(
    surface: SurfacePatch, result: SurfacePreviewBuildResult
) -> None:
    surface.metadata["preview_available"] = bool(result.preview_available)
    surface.metadata["preview_reason"] = result.reason
    surface.metadata.update(copy.deepcopy(result.diagnostics))
    surface.metadata["preview_warning"] = result.warning or ""
    backend_warnings = result.diagnostics.get("warnings")
    if isinstance(backend_warnings, list):
        surface.metadata["source_curve_validation_warnings"] = _merged_metadata_strings(
            surface.metadata.get("source_curve_validation_warnings"), backend_warnings
        )


def _surface_source_lineage_metadata(
    source_curves: Sequence[StoredCurve],
) -> dict[str, object]:
    creation_types: list[str] = []
    tags: list[str] = []
    region_ids: list[str] = []
    mesh_names: list[str] = []
    for curve in source_curves:
        metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
        creation_type = str(metadata.get("creation_type", "")).strip()
        creation_types.append(creation_type)
        tags.extend(_surface_source_curve_tags(curve))
        region_id = metadata.get("source_region_id")
        mesh_name = metadata.get("source_mesh_name")
        if region_id:
            region_ids.append(str(region_id))
        if mesh_name:
            mesh_names.append(str(mesh_name))
    result: dict[str, object] = {
        "source_curve_creation_types": creation_types,
        "source_curve_tags": list(dict.fromkeys(tags)),
    }
    if region_ids:
        result["source_region_ids"] = list(dict.fromkeys(region_ids))
    if mesh_names:
        result["source_mesh_names"] = list(dict.fromkeys(mesh_names))
    return result


def _surface_source_curve_tags(curve: StoredCurve) -> list[str]:
    metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
    explicit_tags = metadata.get("source_curve_tags", metadata.get("tags"))
    tags: list[str] = []
    if isinstance(explicit_tags, list):
        tags.extend(str(tag) for tag in explicit_tags if str(tag))
    creation_type = str(metadata.get("creation_type", "")).strip().lower()
    if creation_type == "projected_curve":
        tags.append("projected")
    elif creation_type == "rebuilt_curve":
        tags.append("rebuilt")
    elif creation_type == "region_boundary" or "source_region_id" in metadata:
        tags.append("boundary")
    elif creation_type in {"manual", "curve_on_mesh"}:
        tags.append("manual")
    if str(metadata.get("snap_mode", "")).strip().lower() == "mesh" or metadata.get(
        "snap_to_mesh"
    ):
        tags.append("mesh")
    curve_method = str(metadata.get("curve_method", "")).strip().lower()
    if curve_method == "polyline":
        tags.append("polyline")
    elif curve_method:
        tags.append("smooth")
    return list(dict.fromkeys(tags))


def _surface_validation_metadata(
    readiness_items: Sequence[CurveSurfaceReadiness],
) -> dict[str, object]:
    planarity_values = [
        item.planarity_error
        for item in readiness_items
        if item.planarity_error is not None
    ]
    projection_values = [
        item.mesh_projection_max_distance
        for item in readiness_items
        if item.mesh_projection_max_distance is not None
    ]
    metadata: dict[str, object] = {
        "source_curve_validation_warnings": _readiness_warnings(readiness_items),
        "source_curve_validation_errors": _readiness_errors(readiness_items),
    }
    if planarity_values:
        metadata["source_curve_planarity_error"] = max(
            float(value) for value in planarity_values
        )
    if projection_values:
        metadata["source_curve_projection_distance"] = max(
            float(value) for value in projection_values
        )
    return metadata


def _readiness_warnings(items: Sequence[CurveSurfaceReadiness]) -> list[str]:
    return list(
        dict.fromkeys(
            warning for item in items for warning in item.warnings if warning
        )
    )


def _readiness_errors(items: Sequence[CurveSurfaceReadiness]) -> list[str]:
    return list(
        dict.fromkeys(error for item in items for error in item.errors if error)
    )


def _surface_patch_validation_messages(
    curves: Sequence[StoredCurve],
    *,
    preview_mode: str,
) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    if preview_mode == FOUR_CURVE_PATCH and len(curves) != 4:
        errors.append("Select exactly four curves for a four-curve patch.")
    if preview_mode == CURVE_NETWORK_PATCH and len(curves) < 3:
        errors.append("Select at least three curves for a curve network patch.")
    if errors:
        return warnings, errors

    curve_points: list[np.ndarray] = []
    for curve in curves:
        points = _surface_patch_curve_points(curve)
        if len(points) < 2:
            errors.append(f"{curve.name} has too few usable points.")
            continue
        if _surface_patch_curve_length(points) <= 1e-8:
            errors.append(f"{curve.name} is degenerate.")
            continue
        curve_points.append(points)
    if errors:
        return warnings, errors

    warnings.extend(_surface_source_mismatch_warnings(curves))
    closed_values: list[bool] = []
    for curve in curves:
        refresh_curve_diagnostics(curve)
        closed_values.append(bool(curve.is_closed or curve.endpoint_distance <= 1e-8))
    if any(closed_values) and not all(closed_values):
        warnings.append("Surface patch mixes open and closed curves.")

    point_counts = [len(points) for points in curve_points]
    if point_counts and _surface_count_ratio(min(point_counts), max(point_counts)) > 3.0:
        warnings.append("Surface patch source curves have very different point counts.")

    if preview_mode == FOUR_CURVE_PATCH:
        warnings.append("Curve order inferred from scene order; inspect patch.")
        corner_gaps = _four_curve_corner_gaps(curve_points)
        if corner_gaps:
            average_length = max(
                float(
                    np.mean(
                        [_surface_patch_curve_length(points) for points in curve_points]
                    )
                ),
                1e-8,
            )
            if max(corner_gaps) > average_length * 0.25:
                warnings.append("Four-curve patch endpoint gaps are large.")

    if preview_mode == CURVE_NETWORK_PATCH:
        if _curve_network_spacing_ratio(curve_points) > 3.0:
            warnings.append("Curve network spacing varies heavily; inspect patch.")
    return list(dict.fromkeys(warnings)), []


def _surface_patch_curve_points(curve: StoredCurve) -> np.ndarray:
    try:
        points = np.asarray(curve.fitted_points, dtype=float)
    except (TypeError, ValueError):
        return np.zeros((0, 3), dtype=float)
    if points.size == 0:
        return np.zeros((0, 3), dtype=float)
    try:
        points = points.reshape((-1, 3))
    except ValueError:
        return np.zeros((0, 3), dtype=float)
    points = points[np.all(np.isfinite(points), axis=1)]
    if len(points) <= 1:
        return points.astype(float, copy=True)
    cleaned = [points[0]]
    for point in points[1:]:
        if np.linalg.norm(point - cleaned[-1]) > 1e-8:
            cleaned.append(point)
    if len(cleaned) > 1 and np.linalg.norm(cleaned[0] - cleaned[-1]) <= 1e-8:
        cleaned.pop()
    return np.asarray(cleaned, dtype=float).reshape((-1, 3))


def _surface_patch_curve_length(points: np.ndarray) -> float:
    if len(points) < 2:
        return 0.0
    return float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())


def _surface_count_ratio(first: int | float, second: int | float) -> float:
    smaller = max(min(float(first), float(second)), 1e-8)
    larger = max(float(first), float(second), 1e-8)
    return larger / smaller


def _four_curve_corner_gaps(curve_points: Sequence[np.ndarray]) -> list[float]:
    if len(curve_points) != 4:
        return []
    bottom, right, top, left = curve_points
    return [
        float(np.linalg.norm(bottom[0] - left[0])),
        float(np.linalg.norm(bottom[-1] - right[0])),
        float(min(np.linalg.norm(top[0] - left[-1]), np.linalg.norm(top[-1] - left[-1]))),
        float(min(np.linalg.norm(top[-1] - right[-1]), np.linalg.norm(top[0] - right[-1]))),
    ]


def _curve_network_spacing_ratio(curve_points: Sequence[np.ndarray]) -> float:
    if len(curve_points) < 2:
        return 1.0
    target_count = min(max(max(len(points) for points in curve_points), 2), 64)
    resampled: list[np.ndarray] = []
    for points in curve_points:
        candidate = _resample_surface_patch_points(points, target_count)
        if candidate is None:
            return 1.0
        if resampled:
            direct = float(np.mean(np.linalg.norm(resampled[-1] - candidate, axis=1)))
            reversed_candidate = candidate[::-1]
            reversed_distance = float(
                np.mean(np.linalg.norm(resampled[-1] - reversed_candidate, axis=1))
            )
            if reversed_distance < direct:
                candidate = reversed_candidate
        resampled.append(candidate)
    strip_distances = [
        float(np.mean(np.linalg.norm(first - second, axis=1)))
        for first, second in zip(resampled, resampled[1:])
    ]
    if not strip_distances:
        return 1.0
    return _surface_count_ratio(min(strip_distances), max(strip_distances))


def _resample_surface_patch_points(
    points: np.ndarray,
    target_count: int,
) -> np.ndarray | None:
    if len(points) == target_count:
        return points.copy()
    segment_lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    total_length = float(np.sum(segment_lengths))
    if total_length <= 1e-8:
        return None
    cumulative = np.concatenate(([0.0], np.cumsum(segment_lengths)))
    distances = np.linspace(0.0, total_length, target_count)
    segment_indices = np.searchsorted(cumulative, distances, side="right") - 1
    segment_indices = np.clip(segment_indices, 0, len(segment_lengths) - 1)
    local_lengths = segment_lengths[segment_indices].reshape((-1, 1))
    fractions = np.divide(
        (distances - cumulative[segment_indices]).reshape((-1, 1)),
        local_lengths,
        out=np.zeros((len(distances), 1), dtype=float),
        where=local_lengths > 1e-8,
    )
    lower = segment_indices
    upper = np.minimum(segment_indices + 1, len(points) - 1)
    resampled = points[lower] * (1.0 - fractions) + points[upper] * fractions
    resampled[0] = points[0]
    resampled[-1] = points[-1]
    return resampled


def _surface_source_mismatch_warnings(
    curves: Sequence[StoredCurve],
) -> list[str]:
    mesh_names: set[str] = set()
    region_ids: set[str] = set()
    for curve in curves:
        metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
        if metadata.get("source_mesh_name"):
            mesh_names.add(str(metadata["source_mesh_name"]))
        if metadata.get("source_region_id"):
            region_ids.add(str(metadata["source_region_id"]))
    warnings: list[str] = []
    if len(mesh_names) > 1:
        warnings.append("Surface source curves come from different source meshes.")
    if len(region_ids) > 1:
        warnings.append("Surface source curves come from different source regions.")
    return warnings


def _merged_metadata_strings(
    existing: object, additions: Sequence[object]
) -> list[str]:
    values: list[str] = []
    if isinstance(existing, list):
        values.extend(str(value) for value in existing if str(value))
    elif existing:
        values.append(str(existing))
    values.extend(str(value) for value in additions if str(value))
    return list(dict.fromkeys(values))


__all__ = (
    "SurfaceController",
    "SurfaceWorkflowSnapshot",
)
