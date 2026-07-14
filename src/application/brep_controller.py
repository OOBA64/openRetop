"""UI-independent BREP and editable-loft workflow controller."""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import math
from pathlib import Path
from typing import Protocol, runtime_checkable
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
from curves.curve_state import (
    CurveCollection,
    StoredCurve,
    get_selected_curves,
    refresh_curve_diagnostics,
)
from curves.manual_curve import (
    parse_manual_curve_metadata_v2,
    sample_hybrid_manual_curve,
)
from curves.validation import validate_curve_for_fill, validate_curves_for_loft
from surfaces.brep_state import (
    BREP_TYPE_LOFT_SURFACE,
    BREP_TYPE_PLANAR_FACE,
    BrepSurfaceCollection,
    BrepSurfaceRecord,
    add_brep_surface,
    clear_brep_surface_selection,
    get_active_brep_surface,
    remove_brep_surface,
    set_active_brep_surface,
)
from surfaces.four_boundary_feature import (
    FourBoundaryPatchFeatureCollection,
    mark_four_boundary_features_dirty_for_curve,
)
from surfaces.loft_feature import (
    LoftFeatureCollection,
    LoftFeatureOptions,
    LoftFeatureRecord,
    add_loft_feature,
    loft_feature_for_brep_surface,
    mark_loft_features_dirty_for_curve,
    remove_loft_feature,
)
from surfaces.surface_state import (
    SurfaceCollection,
    clear_surface_selection,
    remove_surface,
    set_active_surface,
)


@runtime_checkable
class CadBuildOutcome(Protocol):
    """Kernel-neutral subset consumed by the application controller."""

    success: bool
    cad_object: object | None
    reason: str
    warnings: Sequence[str]
    metadata: Mapping[str, object]


@runtime_checkable
class StepExportOutcome(Protocol):
    success: bool
    path: str | None
    reason: str
    warnings: Sequence[str]


@runtime_checkable
class CadBackendPort(Protocol):
    """Injected public-CAD-kernel operations; no concrete kernel dependency."""

    def build_planar_face(self, curve: StoredCurve) -> CadBuildOutcome:
        ...

    def build_loft(
        self,
        curves: Sequence[StoredCurve],
        options: LoftFeatureOptions | None = None,
    ) -> CadBuildOutcome:
        ...

    def export_step(self, cad_object: object, path: Path) -> StepExportOutcome:
        ...


@dataclass(slots=True)
class FunctionCadBackend:
    """Composition adapter for the repository's existing CAD functions."""

    planar_face_builder: Callable[[StoredCurve], CadBuildOutcome]
    loft_builder: Callable[
        [Sequence[StoredCurve], LoftFeatureOptions | None], CadBuildOutcome
    ]
    step_exporter: Callable[[object, Path], StepExportOutcome] | None = None

    def build_planar_face(self, curve: StoredCurve) -> CadBuildOutcome:
        return self.planar_face_builder(curve)

    def build_loft(
        self,
        curves: Sequence[StoredCurve],
        options: LoftFeatureOptions | None = None,
    ) -> CadBuildOutcome:
        return self.loft_builder(curves, options)

    def export_step(self, cad_object: object, path: Path) -> StepExportOutcome:
        if self.step_exporter is None:
            raise RuntimeError("STEP export is unavailable.")
        return self.step_exporter(cad_object, path)


@dataclass(frozen=True, slots=True)
class BrepWorkflowSnapshot:
    brep_surfaces: BrepSurfaceCollection
    loft_features: LoftFeatureCollection
    four_boundary_features: FourBoundaryPatchFeatureCollection
    preview_surfaces: SurfaceCollection
    curves: CurveCollection
    selection: SelectionFamilySnapshot
    runtime_objects: dict[str, object]
    rebuild_revision: int


class BrepController(ControllerBase):
    """Coordinate BREP records, opaque runtime objects, and editable lofts."""

    def __init__(
        self,
        state: AppState,
        events=None,
        *,
        cad_backend: CadBackendPort | None = None,
        runtime_objects: dict[str, object] | None = None,
    ) -> None:
        super().__init__(state, events)
        self._cad_backend = cad_backend
        self.runtime_objects = (
            runtime_objects if runtime_objects is not None else {}
        )
        self.rebuild_revision = 0

    @property
    def cad_backend(self) -> CadBackendPort | None:
        return self._cad_backend

    def rebind_state(self, state: AppState) -> None:
        super().rebind_state(state)
        if hasattr(self, "rebuild_revision"):
            self.rebuild_revision = 0

    def set_cad_backend(self, value: CadBackendPort | None) -> None:
        self._cad_backend = value

    def create_face(
        self,
        *,
        curve_id: str | None = None,
        surface_id: str | None = None,
        name: str | None = None,
        extra_metadata: Mapping[str, object] | None = None,
    ) -> CommandResult:
        if (failure := self._validate_requested_curve_ids(
            None if curve_id is None else (curve_id,)
        )) is not None:
            return failure
        if (failure := self._validate_new_ids(surface_id=surface_id)) is not None:
            return failure
        backend = self._require_backend()
        if isinstance(backend, CommandResult):
            return backend
        curves = self._source_curves(None if curve_id is None else (curve_id,))
        if len(curves) != 1:
            return CommandResult.failure(
                "Select exactly one closed curve for BREP face creation."
            )
        readiness = validate_curve_for_fill(curves[0])
        if readiness.errors:
            return CommandResult.failure(
                *readiness.errors,
                warnings=tuple(readiness.warnings),
                metadata={"readiness": (readiness,)},
            )
        try:
            build = backend.build_planar_face(curves[0])
        except Exception as exc:
            return CommandResult.failure(f"BREP face creation failed: {exc}")
        return self._finish_build(
            build,
            curves,
            fallback_brep_type=BREP_TYPE_PLANAR_FACE,
            name_prefix="BREP Face",
            status_prefix="Created BREP face",
            surface_id=surface_id,
            name=name,
            extra_metadata=extra_metadata,
            undo_name="Create BREP Surface",
        )

    def adopt_planar_face_build(
        self,
        build: CadBuildOutcome,
        *,
        curve_id: str,
        surface_id: str | None = None,
        name: str | None = None,
        extra_metadata: Mapping[str, object] | None = None,
    ) -> CommandResult:
        """Adopt a specialized planar build produced by an infrastructure adapter."""

        if (failure := self._validate_new_ids(surface_id=surface_id)) is not None:
            return failure

        curves, missing = self._curves_for_ids((curve_id,))
        if missing or len(curves) != 1:
            return CommandResult.failure(
                f"Source curve not found: {curve_id}",
                metadata={"missing_curve_ids": tuple(missing or (curve_id,))},
            )
        return self._finish_build(
            build,
            curves,
            fallback_brep_type=BREP_TYPE_PLANAR_FACE,
            name_prefix="BREP Face",
            status_prefix="Created BREP face",
            surface_id=surface_id,
            name=name,
            extra_metadata=extra_metadata,
            undo_name="Create BREP Surface",
        )

    def create_loft(
        self,
        *,
        curve_ids: Sequence[str] | None = None,
        surface_id: str | None = None,
        name: str | None = None,
        options: LoftFeatureOptions | None = None,
        extra_metadata: Mapping[str, object] | None = None,
    ) -> CommandResult:
        if (failure := self._validate_requested_curve_ids(curve_ids)) is not None:
            return failure
        if (failure := self._validate_new_ids(surface_id=surface_id)) is not None:
            return failure
        backend = self._require_backend()
        if isinstance(backend, CommandResult):
            return backend
        curves = self._source_curves(curve_ids)
        if len(curves) != 2:
            return CommandResult.failure(
                "Select exactly two curves for BREP loft creation."
            )
        readiness = validate_curves_for_loft(curves)
        errors = _readiness_errors(readiness)
        if errors:
            return CommandResult.failure(
                *errors,
                warnings=tuple(_readiness_warnings(readiness)),
                metadata={"readiness": tuple(readiness)},
            )
        try:
            build = backend.build_loft(curves, options)
        except Exception as exc:
            return CommandResult.failure(f"BREP loft creation failed: {exc}")
        return self._finish_build(
            build,
            curves,
            fallback_brep_type=BREP_TYPE_LOFT_SURFACE,
            name_prefix="BREP Loft",
            status_prefix="Created BREP loft",
            surface_id=surface_id,
            name=name,
            extra_metadata=extra_metadata,
            undo_name="Create BREP Surface",
        )

    def create_editable_loft(
        self,
        *,
        curve_ids: Sequence[str] | None = None,
        options: LoftFeatureOptions | None = None,
        surface_id: str | None = None,
        feature_id: str | None = None,
        name: str | None = None,
        surface_name: str | None = None,
    ) -> CommandResult:
        if (failure := self._validate_requested_curve_ids(curve_ids)) is not None:
            return failure
        if (
            failure := self._validate_new_ids(
                surface_id=surface_id,
                feature_id=feature_id,
            )
        ) is not None:
            return failure
        backend = self._require_backend()
        if isinstance(backend, CommandResult):
            return backend
        curves = self._source_curves(curve_ids)
        if len(curves) < 2:
            return CommandResult.failure(
                "Select at least two curves for an editable BREP loft."
            )
        feature_options = copy.deepcopy(options) if options is not None else LoftFeatureOptions(
            source_curve_ids=[curve.id for curve in curves]
        )
        feature_options.source_curve_ids = [curve.id for curve in curves]
        before = self._snapshot()
        try:
            build = backend.build_loft(
                _prepared_loft_source_curves(curves, feature_options),
                feature_options,
            )
        except Exception as exc:
            return CommandResult.failure(f"Editable BREP loft creation failed: {exc}")
        if not _build_succeeded(build):
            return _build_failure_result(build, "Editable BREP loft creation failed")

        feature_name = str(name or self._next_loft_feature_name())
        feature = LoftFeatureRecord(
            id=str(feature_id or f"loft-feature-{uuid4().hex}"),
            name=feature_name,
            options=feature_options,
            last_build_success=True,
            last_build_reason=str(build.reason),
            last_build_warnings=[str(value) for value in build.warnings],
            metadata={"loft_feature_dirty": False, "last_rebuild_session": 0},
        )
        surface = self._build_record(
            build,
            curves,
            fallback_brep_type=BREP_TYPE_LOFT_SURFACE,
            name_prefix="Editable Loft",
            surface_id=surface_id,
            name=(
                surface_name
                or self._next_brep_surface_name("Editable BREP Loft")
            ),
            extra_metadata={
                "creation_type": "editable_loft_feature",
                "loft_feature_id": feature.id,
                "loft_feature_dirty": False,
                "editable_feature": True,
                **_loft_overbuild_metadata(feature_options),
            },
        )
        feature.brep_surface_id = surface.id
        try:
            add_brep_surface(self.state.brep_surface_collection, surface)
            add_loft_feature(self.state.loft_feature_collection, feature)
            self.runtime_objects[surface.id] = build.cad_object
            select_surface_exclusively(self.state, surface.id, brep=True)
        except Exception:
            self._restore(before, reason="editable_loft_create_rollback")
            raise
        after = self._snapshot()
        publish_scene_change(
            self.events,
            reason="editable_loft_created",
            object_ids=(surface.id, feature.id, *(curve.id for curve in curves)),
            changed_fields=("brep_surface_collection", "loft_feature_collection"),
        )
        self.events.publish(
            SelectionChangedEvent(
                selection_snapshot_for_state(self.state),
                reason="editable_loft_created",
            )
        )
        return CommandResult.ok(
            status=f"Created editable loft {feature.name}",
            changed=True,
            dirty=True,
            warnings=tuple(str(value) for value in build.warnings),
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=self._undo_payload("Create Editable Loft", before, after),
            metadata={
                "surface": surface,
                "feature": feature,
                "runtime_object": build.cad_object,
                "created_surface_id": surface.id,
                "created_feature_id": feature.id,
            },
        )

    def rebuild_surface(self, surface_id: str | None = None) -> CommandResult:
        backend = self._require_backend()
        if isinstance(backend, CommandResult):
            return backend
        surface = self._surface(surface_id)
        if surface is None:
            return CommandResult.failure("Select a BREP surface to rebuild.")
        curves, missing = self._curves_for_ids(surface.source_curve_ids)
        if missing:
            return CommandResult.failure(
                f"Cannot rebuild {surface.name}; missing source curve: {missing[0]}",
                metadata={"missing_curve_ids": tuple(missing)},
            )
        feature = loft_feature_for_brep_surface(
            self.state.loft_feature_collection, surface.id
        )
        before = self._snapshot()
        try:
            if surface.brep_type == BREP_TYPE_PLANAR_FACE:
                if len(curves) != 1:
                    return CommandResult.failure(
                        "BREP face rebuild requires exactly one source curve."
                    )
                build = backend.build_planar_face(curves[0])
            else:
                if len(curves) < 2:
                    return CommandResult.failure(
                        "BREP loft rebuild requires at least two source curves."
                    )
                options = None if feature is None else feature.options
                build_curves = (
                    curves
                    if options is None
                    else _prepared_loft_source_curves(curves, options)
                )
                build = backend.build_loft(build_curves, options)
        except Exception as exc:
            return CommandResult.failure(f"BREP rebuild failed: {exc}")
        if not _build_succeeded(build):
            return _build_failure_result(build, "BREP rebuild failed")

        surface.backend = str(build.metadata.get("backend", surface.backend))
        surface.metadata.update(copy.deepcopy(dict(build.metadata)))
        surface.metadata["warnings"] = [str(value) for value in build.warnings]
        surface.metadata["runtime_status"] = "ready"
        surface.metadata["build_reason"] = str(build.reason)
        self.runtime_objects[surface.id] = build.cad_object
        self.rebuild_revision += 1
        surface.metadata["rebuild_revision"] = self.rebuild_revision
        if feature is not None:
            feature.last_build_success = True
            feature.last_build_reason = str(build.reason)
            feature.last_build_warnings = [str(value) for value in build.warnings]
            feature.metadata["loft_feature_dirty"] = False
            surface.metadata["loft_feature_dirty"] = False
        after = self._snapshot()
        publish_scene_change(
            self.events,
            reason="brep_surface_rebuilt",
            object_ids=(surface.id, *(curve.id for curve in curves)),
            changed_fields=("brep_surface_collection", "loft_feature_collection"),
        )
        return CommandResult.ok(
            status=f"Rebuilt {surface.name}",
            changed=True,
            dirty=True,
            warnings=tuple(str(value) for value in build.warnings),
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=self._undo_payload("Rebuild BREP Surface", before, after),
            metadata={
                "surface": surface,
                "feature": feature,
                "runtime_object": build.cad_object,
            },
        )

    def adopt_rebuild_build(
        self,
        surface_id: str,
        build: CadBuildOutcome,
    ) -> CommandResult:
        """Apply a specialized infrastructure rebuild as an atomic state change."""

        surface = self._surface(surface_id)
        if surface is None:
            return CommandResult.failure(f"BREP surface not found: {surface_id}")
        if not _build_succeeded(build):
            return _build_failure_result(build, "BREP rebuild failed")
        before = self._snapshot()
        surface.backend = str(build.metadata.get("backend", surface.backend))
        surface.metadata.update(copy.deepcopy(dict(build.metadata)))
        surface.metadata["warnings"] = [str(value) for value in build.warnings]
        surface.metadata["runtime_status"] = "ready"
        surface.metadata["build_reason"] = str(build.reason)
        self.runtime_objects[surface.id] = build.cad_object
        self.rebuild_revision += 1
        surface.metadata["rebuild_revision"] = self.rebuild_revision
        feature = loft_feature_for_brep_surface(
            self.state.loft_feature_collection, surface.id
        )
        if feature is not None:
            feature.last_build_success = True
            feature.last_build_reason = str(build.reason)
            feature.last_build_warnings = [str(value) for value in build.warnings]
            feature.metadata["loft_feature_dirty"] = False
            surface.metadata["loft_feature_dirty"] = False
        after = self._snapshot()
        publish_scene_change(
            self.events,
            reason="brep_surface_rebuilt",
            object_ids=(surface.id, *surface.source_curve_ids),
            changed_fields=("brep_surface_collection", "loft_feature_collection"),
        )
        return CommandResult.ok(
            status=f"Rebuilt {surface.name}",
            changed=True,
            dirty=True,
            warnings=tuple(str(value) for value in build.warnings),
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=self._undo_payload("Rebuild BREP Surface", before, after),
            metadata={
                "surface": surface,
                "feature": feature,
                "runtime_object": build.cad_object,
            },
        )

    def rebuild_loft_feature(self, feature_id: str | None = None) -> CommandResult:
        feature = self._feature(feature_id)
        if feature is None:
            return CommandResult.failure("Select an editable loft feature to rebuild.")
        if feature.brep_surface_id is None:
            return CommandResult.failure("Editable loft has no linked BREP surface.")
        return self.rebuild_surface(feature.brep_surface_id)

    def reorder_source_curve(
        self, feature_id: str, curve_id: str, offset: int
    ) -> CommandResult:
        feature = self._feature(feature_id)
        if feature is None:
            return CommandResult.failure(f"Loft feature not found: {feature_id}")
        source_ids = list(feature.options.source_curve_ids)
        if curve_id not in source_ids:
            return CommandResult.failure(f"Source curve not found: {curve_id}")
        index = source_ids.index(curve_id)
        next_index = min(max(index + int(offset), 0), len(source_ids) - 1)
        if next_index == index:
            return CommandResult.ok(status="Source curve order unchanged.")
        before = self._snapshot()
        source_ids[index], source_ids[next_index] = source_ids[next_index], source_ids[index]
        feature.options.source_curve_ids = source_ids
        feature.metadata["loft_feature_dirty"] = True
        if feature.brep_surface_id:
            surface = self._surface(feature.brep_surface_id)
            if surface is not None:
                surface.source_curve_ids = list(source_ids)
                surface.metadata["source_curve_ids"] = list(source_ids)
                surface.metadata["loft_feature_dirty"] = True
        after = self._snapshot()
        publish_scene_change(
            self.events,
            reason="loft_source_order_changed",
            object_ids=(feature.id, curve_id),
            changed_fields=("loft_feature_collection", "brep_surface_collection"),
        )
        return CommandResult.ok(
            status="Reordered loft source curve.",
            changed=True,
            dirty=True,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=self._undo_payload("Reorder Loft Source", before, after),
            metadata={"feature": feature, "source_curve_ids": tuple(source_ids)},
        )

    def source_curve_changed(
        self,
        curve_id: str,
        *,
        before_curve: StoredCurve | None = None,
    ) -> CommandResult:
        """Invalidate and optionally rebuild all features depending on a curve edit.

        ``before_curve`` lets a curve-edit adapter request one atomic undo payload
        covering both the curve geometry and every dependent feature/runtime object.
        """

        curve = next(
            (item for item in self.state.curve_collection.curves if item.id == curve_id),
            None,
        )
        if curve is None:
            return CommandResult.failure(f"Source curve not found: {curve_id}")
        before = self._snapshot()
        if before_curve is not None:
            for index, item in enumerate(before.curves.curves):
                if item.id == curve_id:
                    before.curves.curves[index] = copy.deepcopy(before_curve)
                    break

        dirty_lofts = mark_loft_features_dirty_for_curve(
            self.state.loft_feature_collection, curve_id
        )
        dirty_patches = mark_four_boundary_features_dirty_for_curve(
            self.state.four_boundary_feature_collection, curve_id
        )
        rebuilt_ids: list[str] = []
        backend = self._cad_backend
        for feature in dirty_lofts:
            surface = (
                None
                if feature.brep_surface_id is None
                else self._surface(feature.brep_surface_id)
            )
            if surface is not None:
                surface.metadata["loft_feature_dirty"] = True
            if not feature.options.rebuild_on_source_edit or backend is None:
                continue
            curves, missing = self._curves_for_ids(feature.options.source_curve_ids)
            if missing:
                feature.last_build_success = False
                feature.last_build_reason = f"Missing loft source curve: {missing[0]}"
                continue
            try:
                build = backend.build_loft(
                    _prepared_loft_source_curves(curves, feature.options),
                    feature.options,
                )
            except Exception as exc:
                feature.last_build_success = False
                feature.last_build_reason = f"Editable BREP loft rebuild failed: {exc}"
                continue
            feature.last_build_success = _build_succeeded(build)
            feature.last_build_reason = str(build.reason)
            feature.last_build_warnings = [str(value) for value in build.warnings]
            if not feature.last_build_success or surface is None:
                continue
            self.rebuild_revision += 1
            feature.metadata["loft_feature_dirty"] = False
            feature.metadata["last_rebuild_session"] = self.rebuild_revision
            surface.backend = str(build.metadata.get("backend", surface.backend))
            surface.metadata.update(copy.deepcopy(dict(build.metadata)))
            surface.metadata.update(
                {
                    "loft_feature_dirty": False,
                    "runtime_status": "ready",
                    "build_reason": str(build.reason),
                    "warnings": [str(value) for value in build.warnings],
                    **_loft_overbuild_metadata(feature.options),
                }
            )
            self.runtime_objects[surface.id] = build.cad_object
            rebuilt_ids.append(feature.id)

        dependent_ids = tuple(
            [*(item.id for item in dirty_lofts), *(item.id for item in dirty_patches)]
        )
        changed = before_curve is not None or bool(dependent_ids)
        if not changed:
            return CommandResult.ok(status="No dependent surface features.")
        after = self._snapshot()
        publish_scene_change(
            self.events,
            reason="source_curve_changed",
            object_ids=(curve_id, *dependent_ids),
            changed_fields=(
                "curve_collection",
                "loft_feature_collection",
                "four_boundary_feature_collection",
                "brep_surface_collection",
            ),
        )
        status = (
            "Loft source curve changed; rebuilt loft."
            if rebuilt_ids
            else "Loft source curve changed; rebuild loft."
            if dirty_lofts
            else "Curve edits saved"
        )
        return CommandResult.ok(
            status=status,
            changed=True,
            dirty=True,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=self._undo_payload(
                "Edit Manual Curve" if before_curve is not None else "Update Source Curve",
                before,
                after,
            ),
            metadata={
                "dirty_feature_ids": dependent_ids,
                "rebuilt_feature_ids": tuple(rebuilt_ids),
            },
        )

    def update_loft_feature(
        self,
        feature_id: str,
        *,
        options: LoftFeatureOptions,
        name: str | None = None,
    ) -> CommandResult:
        """Replace editable-loft settings gathered by a presentation adapter."""

        feature = self._feature(feature_id)
        if feature is None:
            return CommandResult.failure(f"Loft feature not found: {feature_id}")
        candidate_name = feature.name if name is None else str(name).strip()
        if not candidate_name:
            return CommandResult.failure("Loft feature name cannot be empty.")
        replacement = copy.deepcopy(options)
        replacement.source_curve_ids = list(feature.options.source_curve_ids)
        if feature.name == candidate_name and feature.options == replacement:
            return CommandResult.ok(status=f"Selected: {feature.name}")
        before = self._snapshot()
        feature.name = candidate_name
        feature.options = replacement
        feature.metadata["loft_feature_dirty"] = True
        feature.metadata["overbuild_preview_revision"] = int(
            feature.metadata.get("overbuild_preview_revision", 0)
        ) + 1
        surface = (
            None
            if feature.brep_surface_id is None
            else self._surface(feature.brep_surface_id)
        )
        if surface is not None:
            surface.source_curve_ids = list(replacement.source_curve_ids)
            surface.metadata["loft_feature_dirty"] = True
            surface.metadata.update(_loft_overbuild_metadata(replacement))
        after = self._snapshot()
        object_ids = (feature.id,) if surface is None else (feature.id, surface.id)
        publish_scene_change(
            self.events,
            reason="loft_feature_options_changed",
            object_ids=object_ids,
            changed_fields=("loft_feature_collection", "brep_surface_collection"),
        )
        return CommandResult.ok(
            status=f"Updated {feature.name}",
            changed=True,
            dirty=True,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=self._undo_payload("Update Loft Feature", before, after),
            metadata={"feature": feature, "surface": surface},
        )

    def reverse_source_curve(
        self, curve_id: str, *, feature_id: str | None = None
    ) -> CommandResult:
        curve = next(
            (item for item in self.state.curve_collection.curves if item.id == curve_id),
            None,
        )
        if curve is None:
            return CommandResult.failure(f"Source curve not found: {curve_id}")
        feature = self._feature(feature_id)
        if feature_id is not None and feature is None:
            return CommandResult.failure(f"Loft feature not found: {feature_id}")
        if feature is not None and curve.id not in feature.options.source_curve_ids:
            return CommandResult.failure(
                f"Curve {curve.name} is not a source of {feature.name}."
            )
        before = self._snapshot()
        _reverse_curve_geometry_in_place(curve)
        curve.metadata["curve_direction_reversed"] = not bool(
            curve.metadata.get("curve_direction_reversed", False)
        )
        curve.metadata["source_curve_revision"] = int(
            curve.metadata.get("source_curve_revision", 0)
        ) + 1
        refresh_curve_diagnostics(curve)
        dirty_lofts = mark_loft_features_dirty_for_curve(
            self.state.loft_feature_collection, curve.id
        )
        dirty_patches = mark_four_boundary_features_dirty_for_curve(
            self.state.four_boundary_feature_collection, curve.id
        )
        for item in dirty_lofts:
            if item.brep_surface_id:
                surface = self._surface(item.brep_surface_id)
                if surface is not None:
                    surface.metadata["loft_feature_dirty"] = True
        after = self._snapshot()
        dependent_ids = tuple(
            [*(item.id for item in dirty_lofts), *(item.id for item in dirty_patches)]
        )
        publish_scene_change(
            self.events,
            reason="loft_source_curve_reversed",
            object_ids=(curve.id, *dependent_ids),
            changed_fields=(
                "curve_collection",
                "loft_feature_collection",
                "four_boundary_feature_collection",
            ),
        )
        return CommandResult.ok(
            status=f"Reversed {curve.name}",
            changed=True,
            dirty=True,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=self._undo_payload("Reverse Loft Source Curve", before, after),
            metadata={"curve": curve, "dirty_feature_ids": dependent_ids},
        )

    def duplicate_loft_feature(
        self,
        feature_id: str | None = None,
        *,
        new_feature_id: str | None = None,
        new_surface_id: str | None = None,
        name: str | None = None,
        surface_name: str | None = None,
    ) -> CommandResult:
        feature = self._feature(feature_id)
        if feature is None:
            return CommandResult.failure("Select an editable loft feature to duplicate.")
        return self.create_editable_loft(
            curve_ids=feature.options.source_curve_ids,
            options=copy.deepcopy(feature.options),
            surface_id=new_surface_id,
            feature_id=new_feature_id,
            name=name or self._next_loft_feature_name(),
            surface_name=surface_name,
        )

    def delete_loft_feature(self, feature_id: str | None = None) -> CommandResult:
        feature = self._feature(feature_id)
        if feature is None:
            return CommandResult.failure("Select an editable loft feature to delete.")
        before = self._snapshot()
        surface_ids = tuple(
            value
            for value in (feature.preview_surface_id, feature.brep_surface_id)
            if value
        )
        if feature.preview_surface_id:
            remove_surface(
                self.state.surface_collection, feature.preview_surface_id
            )
        if feature.brep_surface_id:
            remove_brep_surface(
                self.state.brep_surface_collection, feature.brep_surface_id
            )
            self.runtime_objects.pop(feature.brep_surface_id, None)
        remove_loft_feature(self.state.loft_feature_collection, feature.id)
        self._select_surface_fallback()
        after = self._snapshot()
        publish_scene_change(
            self.events,
            reason="loft_feature_deleted",
            object_ids=(feature.id, *surface_ids),
            changed_fields=(
                "loft_feature_collection",
                "surface_collection",
                "brep_surface_collection",
            ),
        )
        self.events.publish(
            SelectionChangedEvent(
                selection_snapshot_for_state(self.state),
                reason="loft_feature_deleted",
            )
        )
        return CommandResult.ok(
            status=f"Deleted {feature.name}",
            changed=True,
            dirty=True,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=self._undo_payload("Delete Loft Feature", before, after),
            metadata={
                "deleted_feature_id": feature.id,
                "deleted_surface_ids": surface_ids,
            },
        )

    def delete_surface(self, surface_id: str | None = None) -> CommandResult:
        surface = self._surface(surface_id)
        if surface is None:
            return CommandResult.failure("Select a BREP surface to delete.")
        before = self._snapshot()
        dependency_change = plan_feature_dependency_removal(
            self.state,
            brep_surface_ids=(surface.id,),
        )
        removed_runtime = {
            value: self.runtime_objects.pop(value)
            for value in dependency_change.removed_brep_surface_ids
            if value in self.runtime_objects
        }
        prune_feature_dependencies(self.state, dependency_change)
        self._select_surface_fallback()
        after = self._snapshot()
        publish_scene_change(
            self.events,
            reason="brep_surface_deleted",
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
                reason="brep_surface_deleted",
            )
        )
        return CommandResult.ok(
            status=f"Deleted: {surface.name}",
            changed=True,
            dirty=True,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=self._undo_payload("Delete BREP Surface", before, after),
            metadata={
                "deleted_surface_id": surface.id,
                "runtime_objects": removed_runtime,
                **dependency_change.as_metadata(),
            },
        )

    def update_surface_display(
        self,
        surface_id: str,
        *,
        opacity: float | None = None,
        wireframe_overlay: bool | None = None,
    ) -> CommandResult:
        """Update persistent BREP display metadata without touching render actors."""

        surface = self._surface(surface_id)
        if surface is None:
            return CommandResult.failure(f"BREP surface not found: {surface_id}")

        candidate_opacity: float | None = None
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
            reason="brep_surface_display_changed",
            object_ids=(surface.id,),
            changed_fields=tuple(changed_fields),
        )
        return CommandResult.ok(
            status=f"Selected: {surface.name}",
            changed=True,
            dirty=True,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=self._undo_payload("Update BREP Surface", before, after),
            metadata={"surface": surface, "changed_fields": tuple(changed_fields)},
        )

    def export_surface(self, path: Path, surface_id: str | None = None) -> CommandResult:
        backend = self._require_backend()
        if isinstance(backend, CommandResult):
            return backend
        surface = self._surface(surface_id)
        if surface is None:
            return CommandResult.failure("Select a BREP surface to export.")
        runtime = self.runtime_objects.get(surface.id)
        if runtime is None:
            return CommandResult.failure(
                "Rebuild the selected BREP surface before exporting it."
            )
        try:
            outcome = backend.export_step(runtime, Path(path))
        except Exception as exc:
            return CommandResult.failure(f"STEP export failed: {exc}")
        if not bool(outcome.success):
            return CommandResult.failure(
                str(outcome.reason), warnings=tuple(str(v) for v in outcome.warnings)
            )
        surface.metadata["last_export_path"] = str(outcome.path or path)
        surface.metadata["last_export_reason"] = str(outcome.reason)
        publish_scene_change(
            self.events,
            reason="brep_surface_exported",
            object_ids=(surface.id,),
            changed_fields=("brep_surface_collection",),
        )
        return CommandResult.ok(
            status=str(outcome.reason),
            changed=True,
            dirty=True,
            warnings=tuple(str(v) for v in outcome.warnings),
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            metadata={"surface": surface, "export_path": str(outcome.path or path)},
        )

    def prune_runtime_objects(self, surface_ids: Sequence[str]) -> None:
        for surface_id in surface_ids:
            self.runtime_objects.pop(str(surface_id), None)

    def _select_surface_fallback(self) -> None:
        previews = self.state.surface_collection.surfaces
        breps = self.state.brep_surface_collection.surfaces
        if previews:
            clear_brep_surface_selection(self.state.brep_surface_collection)
            set_active_surface(self.state.surface_collection, previews[0].id)
            self.state.selected_item = "surface"
        elif breps:
            clear_surface_selection(self.state.surface_collection)
            set_active_brep_surface(self.state.brep_surface_collection, breps[0].id)
            self.state.selected_item = "surface"
        else:
            clear_surface_selection(self.state.surface_collection)
            clear_brep_surface_selection(self.state.brep_surface_collection)
            self.state.selected_item = None

    def _finish_build(
        self,
        build: CadBuildOutcome,
        curves: Sequence[StoredCurve],
        *,
        fallback_brep_type: str,
        name_prefix: str,
        status_prefix: str,
        surface_id: str | None,
        name: str | None,
        extra_metadata: Mapping[str, object] | None,
        undo_name: str,
    ) -> CommandResult:
        if not _build_succeeded(build):
            return _build_failure_result(build, f"{status_prefix} failed")
        surface = self._build_record(
            build,
            curves,
            fallback_brep_type=fallback_brep_type,
            name_prefix=name_prefix,
            surface_id=surface_id,
            name=name,
            extra_metadata=extra_metadata,
        )
        before = self._snapshot()
        try:
            add_brep_surface(self.state.brep_surface_collection, surface)
            self.runtime_objects[surface.id] = build.cad_object
            select_surface_exclusively(self.state, surface.id, brep=True)
        except Exception:
            self._restore(before, reason="brep_create_rollback")
            raise
        after = self._snapshot()
        publish_scene_change(
            self.events,
            reason="brep_surface_created",
            object_ids=(surface.id, *(curve.id for curve in curves)),
            changed_fields=("brep_surface_collection",),
        )
        self.events.publish(
            SelectionChangedEvent(
                selection_snapshot_for_state(self.state),
                reason="brep_surface_created",
            )
        )
        return CommandResult.ok(
            status=f"{status_prefix}: {surface.name}",
            changed=True,
            dirty=True,
            warnings=tuple(str(value) for value in build.warnings),
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=self._undo_payload(undo_name, before, after),
            metadata={
                "surface": surface,
                "runtime_object": build.cad_object,
                "created_surface_id": surface.id,
            },
        )

    def _build_record(
        self,
        build: CadBuildOutcome,
        curves: Sequence[StoredCurve],
        *,
        fallback_brep_type: str,
        name_prefix: str,
        surface_id: str | None,
        name: str | None,
        extra_metadata: Mapping[str, object] | None,
    ) -> BrepSurfaceRecord:
        metadata = copy.deepcopy(dict(build.metadata))
        if build.warnings:
            metadata["warnings"] = [str(value) for value in build.warnings]
        metadata.update(_source_lineage_metadata(curves))
        metadata["source_curve_ids"] = [curve.id for curve in curves]
        metadata["source_curve_names"] = [curve.name for curve in curves]
        metadata["source_curve_count"] = len(curves)
        metadata["runtime_status"] = "ready"
        metadata["build_reason"] = str(build.reason)
        if fallback_brep_type == BREP_TYPE_LOFT_SURFACE:
            metadata.update(
                {
                    "overbuild_enabled": True,
                    "overbuild_amount": 0.10,
                    "overbuild_u_start": 0.10,
                    "overbuild_u_end": 0.10,
                    "overbuild_v_start": 0.10,
                    "overbuild_v_end": 0.10,
                    "show_overbuild_handles": False,
                    "overbuild_preview_only": True,
                }
            )
        if extra_metadata:
            metadata.update(copy.deepcopy(dict(extra_metadata)))
        return BrepSurfaceRecord(
            id=str(surface_id or f"brep-{uuid4().hex}"),
            name=str(name or self._next_brep_surface_name(name_prefix)),
            source_curve_ids=[curve.id for curve in curves],
            brep_type=str(metadata.get("brep_type", fallback_brep_type)),
            backend=str(metadata.get("backend", "")),
            metadata=metadata,
        )

    def _source_curves(
        self, curve_ids: Sequence[str] | None
    ) -> list[StoredCurve]:
        if curve_ids is None:
            selected = get_selected_curves(self.state.curve_collection)
            if selected:
                return selected
            active_id = self.state.curve_collection.active_curve_id
            curve_ids = () if active_id is None else (active_id,)
        return self._curves_for_ids(curve_ids)[0]

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
            for item in self.state.brep_surface_collection.surfaces
        ):
            return CommandResult.failure(
                f"BREP surface ID already exists: {surface_id}",
                metadata={"duplicate_surface_id": str(surface_id)},
            )
        if feature_id is not None and any(
            item.id == str(feature_id)
            for item in self.state.loft_feature_collection.features
        ):
            return CommandResult.failure(
                f"Loft feature ID already exists: {feature_id}",
                metadata={"duplicate_feature_id": str(feature_id)},
            )
        return None

    def _curves_for_ids(
        self, curve_ids: Sequence[str]
    ) -> tuple[list[StoredCurve], list[str]]:
        by_id = {curve.id: curve for curve in self.state.curve_collection.curves}
        normalized = [str(value) for value in curve_ids]
        return (
            [by_id[value] for value in normalized if value in by_id],
            [value for value in normalized if value not in by_id],
        )

    def _surface(self, surface_id: str | None) -> BrepSurfaceRecord | None:
        if surface_id is None:
            return get_active_brep_surface(self.state.brep_surface_collection)
        return next(
            (
                item
                for item in self.state.brep_surface_collection.surfaces
                if item.id == str(surface_id)
            ),
            None,
        )

    def _feature(self, feature_id: str | None) -> LoftFeatureRecord | None:
        if feature_id is None:
            feature_id = self.state.loft_feature_collection.active_feature_id
        return next(
            (
                item
                for item in self.state.loft_feature_collection.features
                if item.id == feature_id
            ),
            None,
        )

    def _require_backend(self) -> CadBackendPort | CommandResult:
        if self._cad_backend is None:
            return CommandResult.failure("CAD kernel is unavailable.")
        return self._cad_backend

    def _next_brep_surface_name(self, prefix: str) -> str:
        existing = {
            surface.name for surface in self.state.brep_surface_collection.surfaces
        }
        index = 1
        while f"{prefix} {index}" in existing:
            index += 1
        return f"{prefix} {index}"

    def _next_loft_feature_name(self) -> str:
        existing = {
            feature.name for feature in self.state.loft_feature_collection.features
        }
        index = 1
        while f"Editable Loft {index}" in existing:
            index += 1
        return f"Editable Loft {index}"

    def _snapshot(self) -> BrepWorkflowSnapshot:
        return BrepWorkflowSnapshot(
            brep_surfaces=copy.deepcopy(self.state.brep_surface_collection),
            loft_features=copy.deepcopy(self.state.loft_feature_collection),
            four_boundary_features=copy.deepcopy(
                self.state.four_boundary_feature_collection
            ),
            preview_surfaces=copy.deepcopy(self.state.surface_collection),
            curves=copy.deepcopy(self.state.curve_collection),
            selection=SelectionFamilySnapshot.capture(self.state),
            runtime_objects=dict(self.runtime_objects),
            rebuild_revision=self.rebuild_revision,
        )

    def _restore(self, snapshot: BrepWorkflowSnapshot, *, reason: str) -> None:
        self.state.brep_surface_collection = copy.deepcopy(snapshot.brep_surfaces)
        self.state.loft_feature_collection = copy.deepcopy(snapshot.loft_features)
        self.state.four_boundary_feature_collection = copy.deepcopy(
            snapshot.four_boundary_features
        )
        self.state.surface_collection = copy.deepcopy(snapshot.preview_surfaces)
        self.state.curve_collection = copy.deepcopy(snapshot.curves)
        snapshot.selection.restore(self.state)
        self.runtime_objects.clear()
        self.runtime_objects.update(snapshot.runtime_objects)
        self.rebuild_revision = snapshot.rebuild_revision
        publish_scene_change(
            self.events,
            reason=reason,
            object_ids=(
                *(surface.id for surface in self.state.brep_surface_collection.surfaces),
                *(feature.id for feature in self.state.loft_feature_collection.features),
            ),
            changed_fields=(
                "brep_surface_collection",
                "loft_feature_collection",
                "four_boundary_feature_collection",
                "surface_collection",
                "curve_collection",
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
        before: BrepWorkflowSnapshot,
        after: BrepWorkflowSnapshot,
    ) -> CallbackUndoPayload:
        return CallbackUndoPayload(
            name,
            undo_action=lambda: self._restore(before, reason="brep_undo"),
            redo_action=lambda: self._restore(after, reason="brep_redo"),
        )


def _build_succeeded(result: CadBuildOutcome) -> bool:
    return bool(result.success and result.cad_object is not None)


def _build_failure_result(result: CadBuildOutcome, prefix: str) -> CommandResult:
    reason = str(result.reason or prefix)
    return CommandResult.failure(
        reason,
        warnings=tuple(str(value) for value in result.warnings),
        metadata={"build_result": result},
    )


def _readiness_warnings(items: Sequence[object]) -> list[str]:
    return list(
        dict.fromkeys(
            str(warning)
            for item in items
            for warning in getattr(item, "warnings", ())
            if str(warning)
        )
    )


def _readiness_errors(items: Sequence[object]) -> list[str]:
    return list(
        dict.fromkeys(
            str(error)
            for item in items
            for error in getattr(item, "errors", ())
            if str(error)
        )
    )


def _source_lineage_metadata(curves: Sequence[StoredCurve]) -> dict[str, object]:
    creation_types: list[str] = []
    region_ids: list[str] = []
    mesh_names: list[str] = []
    for curve in curves:
        metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
        creation_types.append(str(metadata.get("creation_type", "")))
        if metadata.get("source_region_id"):
            region_ids.append(str(metadata["source_region_id"]))
        if metadata.get("source_mesh_name"):
            mesh_names.append(str(metadata["source_mesh_name"]))
    result: dict[str, object] = {
        "source_curve_creation_types": creation_types,
    }
    if region_ids:
        result["source_region_ids"] = list(dict.fromkeys(region_ids))
    if mesh_names:
        result["source_mesh_names"] = list(dict.fromkeys(mesh_names))
    return result


def _loft_overbuild_metadata(options: LoftFeatureOptions) -> dict[str, object]:
    return {
        "overbuild_enabled": bool(options.overbuild_enabled),
        "overbuild_amount": float(options.overbuild_amount),
        "overbuild_u_start": float(options.overbuild_u_start),
        "overbuild_u_end": float(options.overbuild_u_end),
        "overbuild_v_start": float(options.overbuild_v_start),
        "overbuild_v_end": float(options.overbuild_v_end),
        "show_overbuild_handles": bool(options.show_overbuild_handles),
        "overbuild_preview_only": True,
    }


def _prepared_loft_source_curves(
    source_curves: Sequence[StoredCurve],
    options: LoftFeatureOptions,
) -> list[StoredCurve]:
    """Preserve the established direction/seam preparation on working copies."""

    prepared = [copy.deepcopy(curve) for curve in source_curves]
    if len(prepared) < 2:
        return prepared
    reference_points = np.asarray(
        prepared[0].fitted_points, dtype=float
    ).reshape((-1, 3))
    for curve in prepared[1:]:
        points = np.asarray(curve.fitted_points, dtype=float).reshape((-1, 3))
        if len(reference_points) < 2 or len(points) < 2:
            continue
        if options.match_curve_directions:
            direct = float(
                np.linalg.norm(reference_points[0] - points[0])
                + np.linalg.norm(reference_points[-1] - points[-1])
            )
            reversed_distance = float(
                np.linalg.norm(reference_points[0] - points[-1])
                + np.linalg.norm(reference_points[-1] - points[0])
            )
            if reversed_distance < direct:
                _reverse_curve_geometry_in_place(curve)
        if options.align_closed_curve_seams and curve.is_closed:
            controls = parse_manual_curve_metadata_v2(curve)
            if controls is None or not controls.points:
                continue
            seam_index = int(
                np.argmin(
                    np.linalg.norm(
                        controls.control_points - reference_points[0], axis=1
                    )
                )
            )
            controls.points = controls.points[seam_index:] + controls.points[:seam_index]
            curve.metadata["control_points"] = controls.control_points.tolist()
            curve.metadata["control_points_v2"] = [
                {
                    "position": point.position.tolist(),
                    "point_type": point.point_type,
                    "weight": point.weight,
                    "tangent_in": (
                        None if point.tangent_in is None else point.tangent_in.tolist()
                    ),
                    "tangent_out": (
                        None if point.tangent_out is None else point.tangent_out.tolist()
                    ),
                    "snap_triangle_index": point.snap_triangle_index,
                    "snap_normal": point.snap_normal,
                    "metadata": dict(point.metadata),
                }
                for point in controls.points
            ]
            curve.metadata["point_types"] = [
                point.point_type for point in controls.points
            ]
            curve.fitted_points = sample_hybrid_manual_curve(controls)
    return prepared


def _reverse_curve_geometry_in_place(curve: StoredCurve) -> None:
    curve.original_points = np.asarray(curve.original_points, dtype=float)[::-1].copy()
    curve.fitted_points = np.asarray(curve.fitted_points, dtype=float)[::-1].copy()
    metadata = copy.deepcopy(curve.metadata) if isinstance(curve.metadata, dict) else {}
    for key in (
        "control_points",
        "control_points_v2",
        "point_types",
        "point_type_sources",
        "snap_flags",
        "snap_triangle_indices",
        "snap_normals",
        "snap_projection_distances",
    ):
        value = metadata.get(key)
        if isinstance(value, list):
            metadata[key] = list(reversed(value))
    curve.metadata = metadata


__all__ = (
    "BrepController",
    "BrepWorkflowSnapshot",
    "CadBackendPort",
    "CadBuildOutcome",
    "FunctionCadBackend",
    "StepExportOutcome",
)
