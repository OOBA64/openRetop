"""Apply persistent project records to the UI-independent V3 application state."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from application.state import AppState
from application.scene_ids import region_node_id, surface_node_id
from application.transform_math import build_object_transform_matrix
from curves.curve_state import CurveCollection, StoredCurve, refresh_curve_diagnostics
from curves.manual_curve import ensure_manual_curve_storage
from geometry.sections import SectionPolyline, SectionResult, normalize_axis
from project.project_data import ProjectData
from regions.region_state import RegionCollection, RegionSelection
from sections.section_state import (
    SectionCollection,
    SectionPlaneState,
    StoredSectionResult,
    add_plane,
    add_result,
    create_default_section_plane,
    set_active_plane,
)
from settings.settings_data import AppSettings, DISPLAY_COLOR_FIELDS
from surfaces.brep_state import BrepSurfaceCollection, BrepSurfaceRecord
from surfaces.four_boundary_feature import (
    FourBoundaryPatchFeatureCollection,
    FourBoundaryPatchFeatureRecord,
)
from surfaces.loft_feature import (
    LoftFeatureCollection,
    LoftFeatureOptions,
    LoftFeatureRecord,
)
from surfaces.surface_state import SurfaceCollection, SurfacePatch


@dataclass(frozen=True, slots=True)
class ProjectRestoreResult:
    warnings: tuple[str, ...] = ()
    selected_scene_ids: tuple[str, ...] = ()
    primary_selection_id: str | None = None


def restore_project_state(
    state: AppState,
    project: ProjectData,
    *,
    settings: AppSettings | None = None,
) -> ProjectRestoreResult:
    """Restore all persistent V3 records while keeping controller state identity stable."""

    warnings: list[str] = []
    _restore_display(settings, project)
    _restore_mesh(state, project)
    state.section_collection = _restore_sections(project, warnings)
    state.curve_collection = _restore_curves(project)
    state.region_collection = _restore_region(project)
    (
        state.surface_collection,
        state.brep_surface_collection,
        state.loft_feature_collection,
        state.four_boundary_feature_collection,
    ) = _restore_surfaces(project, state.curve_collection, warnings)
    state.section_result = (
        state.section_collection.results[-1].result
        if state.section_collection.results
        else None
    )
    state.curve_results = [
        curve for curve in state.curve_collection.curves if curve.visible
    ]
    state.clear_selection()
    selected_ids = tuple(dict.fromkeys(str(value) for value in project.selected_scene_ids))
    if not selected_ids:
        legacy_selected: list[str] = []
        if project.region is not None and project.region.selected:
            legacy_selected.append(region_node_id(project.region.id))
        legacy_selected.extend(
            surface_node_id(item.id) for item in project.brep_surfaces if item.selected
        )
        selected_ids = tuple(legacy_selected)
    return ProjectRestoreResult(
        warnings=tuple(warnings),
        selected_scene_ids=selected_ids,
        primary_selection_id=(
            project.primary_selection_id
            if project.primary_selection_id in selected_ids
            else (selected_ids[0] if selected_ids else None)
        ),
    )


def _restore_display(settings: AppSettings | None, project: ProjectData) -> None:
    if settings is None:
        return
    settings.import_settings.default_proxy_quality = project.display.proxy_quality
    settings.display.show_grid = bool(project.display.show_grid)
    settings.display.show_axes = bool(project.display.show_axes)
    settings.display.show_normals = bool(project.display.show_normals)
    for field_name, value in project.display.colors.items():
        if field_name in DISPLAY_COLOR_FIELDS:
            setattr(settings.display, field_name, str(value))


def _restore_mesh(state: AppState, project: ProjectData) -> None:
    mesh = state.mesh_object
    if mesh is None:
        return
    if project.mesh_name and project.mesh_name.strip():
        mesh.name = project.mesh_name.strip()
    mesh.visible = bool(project.mesh_visible)
    mesh.location = np.asarray(project.transform.location, dtype=float)
    mesh.rotation = np.asarray(project.transform.rotation, dtype=float)
    mesh.scale = float(project.transform.scale)
    mesh.origin = np.asarray(project.transform.origin, dtype=float)
    mesh.transform_matrix = build_object_transform_matrix(
        mesh.location,
        mesh.rotation,
        mesh.scale,
        mesh.origin,
    )


def _restore_sections(
    project: ProjectData,
    warnings: list[str],
) -> SectionCollection:
    collection = SectionCollection()
    used_names: set[str] = set()
    if project.section_planes:
        for index, saved in enumerate(project.section_planes, start=1):
            plane = SectionPlaneState(
                id=saved.id,
                name=_unique_name(saved.name, f"Section Plane {index}", used_names),
                axis=saved.axis,
                offset=float(saved.offset),
                visible=bool(saved.visible),
                origin=np.asarray(saved.origin, dtype=float),
                normal=np.asarray(saved.normal, dtype=float),
            )
            try:
                add_plane(collection, plane)
            except ValueError as exc:
                warnings.append(f"Skipped section plane {saved.id}: {exc}")
    if not collection.planes:
        plane = create_default_section_plane(
            axis=project.section.axis,
            offset=project.section.offset,
        )
        plane.visible = bool(project.section.show_plane)
        add_plane(collection, plane)
    requested_active = project.active_section_plane_id
    try:
        set_active_plane(
            collection,
            requested_active
            if requested_active and any(item.id == requested_active for item in collection.planes)
            else collection.planes[0].id,
        )
    except ValueError:
        set_active_plane(collection, collection.planes[0].id)

    plane_ids = {item.id for item in collection.planes}
    for saved in project.section_results:
        if saved.plane_id not in plane_ids:
            warnings.append(
                f"Skipped section result {saved.id}: missing plane {saved.plane_id}."
            )
            continue
        result = SectionResult(
            axis=normalize_axis(saved.axis),
            offset=float(saved.offset),
            polylines=tuple(
                SectionPolyline(points=np.asarray(points, dtype=float))
                for points in saved.polylines
            ),
            segment_count=int(saved.segment_count),
            plane_origin=np.asarray(saved.plane_origin, dtype=float),
            plane_normal=np.asarray(saved.plane_normal, dtype=float),
            is_arbitrary_plane=bool(saved.is_arbitrary_plane),
        )
        try:
            add_result(
                collection,
                StoredSectionResult(
                    id=saved.id,
                    name=saved.name,
                    plane_id=saved.plane_id,
                    axis=saved.axis,
                    offset=float(saved.offset),
                    result=result,
                    visible=bool(saved.visible),
                    plane_origin=np.asarray(saved.plane_origin, dtype=float),
                    plane_normal=np.asarray(saved.plane_normal, dtype=float),
                    is_arbitrary_plane=bool(saved.is_arbitrary_plane),
                ),
            )
        except ValueError as exc:
            warnings.append(f"Skipped section result {saved.id}: {exc}")
    return collection


def _restore_curves(project: ProjectData) -> CurveCollection:
    curves: list[StoredCurve] = []
    for saved in project.curves:
        curve = StoredCurve(
            id=saved.id,
            name=saved.name,
            section_result_id=saved.section_result_id,
            plane_id=saved.plane_id,
            original_points=np.asarray(saved.original_points, dtype=float),
            fitted_points=np.asarray(saved.fitted_points, dtype=float),
            mean_error=float(saved.mean_error),
            max_error=float(saved.max_error),
            is_closed=bool(saved.is_closed),
            visible=bool(saved.visible),
            metadata=dict(saved.metadata),
        )
        ensure_manual_curve_storage(curve)
        refresh_curve_diagnostics(curve)
        curves.append(curve)
    return CurveCollection(curves=curves)


def _restore_region(project: ProjectData) -> RegionCollection:
    saved = project.region
    if saved is None:
        return RegionCollection()
    return RegionCollection(
        active_region=RegionSelection(
            id=saved.id,
            name=saved.name,
            triangle_indices=tuple(int(value) for value in saved.triangle_indices),
            threshold_degrees=float(saved.threshold_degrees),
            max_triangle_count=int(saved.max_triangle_count),
            source_mesh_identifier=saved.source_mesh_identifier,
            source_mesh_name=saved.source_mesh_name,
            seed_triangle_index=saved.seed_triangle_index,
            visible=bool(saved.visible),
            selected=False,
            metadata=dict(saved.metadata),
        )
    )


def _restore_surfaces(
    project: ProjectData,
    curves: CurveCollection,
    warnings: list[str],
) -> tuple[
    SurfaceCollection,
    BrepSurfaceCollection,
    LoftFeatureCollection,
    FourBoundaryPatchFeatureCollection,
]:
    curve_ids = {item.id for item in curves.curves}
    previews: list[SurfacePatch] = []
    for saved in project.surfaces:
        metadata = _with_missing_curves(saved.metadata, saved.source_curve_ids, curve_ids)
        if metadata.get("missing_curve_ids"):
            warnings.append(f"Surface {saved.id} has missing source curves.")
        previews.append(
            SurfacePatch(
                id=saved.id,
                name=saved.name,
                source_curve_ids=list(saved.source_curve_ids),
                surface_type=saved.surface_type,
                visible=bool(saved.visible),
                metadata=metadata,
            )
        )

    breps: list[BrepSurfaceRecord] = []
    for saved in project.brep_surfaces:
        metadata = _with_missing_curves(saved.metadata, saved.source_curve_ids, curve_ids)
        metadata.update(
            {
                "runtime_status": "rebuild_required",
                "build_reason": "BREP surface record loaded; rebuild required before export.",
            }
        )
        breps.append(
            BrepSurfaceRecord(
                id=saved.id,
                name=saved.name,
                source_curve_ids=list(saved.source_curve_ids),
                brep_type=saved.brep_type,
                backend=saved.backend,
                visible=bool(saved.visible),
                selected=False,
                metadata=metadata,
            )
        )

    lofts = [
        LoftFeatureRecord(
            id=saved.id,
            name=saved.name,
            options=_loft_options(saved.options),
            brep_surface_id=saved.brep_surface_id,
            preview_surface_id=saved.preview_surface_id,
            last_build_success=bool(saved.last_build_success),
            last_build_reason=saved.last_build_reason,
            last_build_warnings=list(saved.last_build_warnings),
            metadata=dict(saved.metadata),
        )
        for saved in project.loft_features
    ]
    four_boundary = [
        FourBoundaryPatchFeatureRecord(
            id=saved.id,
            name=saved.name,
            source_curve_ids=list(saved.source_curve_ids),
            preserve_corners=bool(saved.preserve_corners),
            match_directions=bool(saved.match_directions),
            fill_method=saved.fill_method,
            brep_surface_id=saved.brep_surface_id,
            preview_surface_id=saved.preview_surface_id,
            last_build_status=saved.last_build_status,
            metadata=dict(saved.metadata),
        )
        for saved in project.four_boundary_patch_features
    ]
    return (
        SurfaceCollection(surfaces=previews),
        BrepSurfaceCollection(surfaces=breps),
        LoftFeatureCollection(
            features=lofts,
            active_feature_id=lofts[0].id if lofts else None,
        ),
        FourBoundaryPatchFeatureCollection(
            features=four_boundary,
            active_feature_id=four_boundary[0].id if four_boundary else None,
        ),
    )


def _loft_options(value: dict[str, object]) -> LoftFeatureOptions:
    data = dict(value)
    return LoftFeatureOptions(
        source_curve_ids=list(data.get("source_curve_ids", [])),
        source_order_locked=bool(data.get("source_order_locked", True)),
        use_cad_wires=bool(data.get("use_cad_wires", True)),
        match_curve_directions=bool(data.get("match_curve_directions", True)),
        align_closed_curve_seams=bool(data.get("align_closed_curve_seams", True)),
        preserve_corners=bool(data.get("preserve_corners", True)),
        cap_start=bool(data.get("cap_start", False)),
        cap_end=bool(data.get("cap_end", False)),
        create_solid_if_closed=bool(data.get("create_solid_if_closed", False)),
        ruled=bool(data.get("ruled", False)),
        smoothing=str(data.get("smoothing", "normal")),
        rebuild_on_source_edit=bool(data.get("rebuild_on_source_edit", True)),
        overbuild_enabled=bool(data.get("overbuild_enabled", True)),
        overbuild_amount=data.get("overbuild_amount", 0.10),
        overbuild_u_start=data.get("overbuild_u_start", 0.10),
        overbuild_u_end=data.get("overbuild_u_end", 0.10),
        overbuild_v_start=data.get("overbuild_v_start", 0.10),
        overbuild_v_end=data.get("overbuild_v_end", 0.10),
        show_overbuild_handles=bool(data.get("show_overbuild_handles", True)),
        metadata=dict(data.get("metadata", {}))
        if isinstance(data.get("metadata"), dict)
        else {},
    )


def _with_missing_curves(
    metadata: dict[str, object],
    source_ids: list[str],
    existing_ids: set[str],
) -> dict[str, object]:
    result = dict(metadata)
    missing = [item for item in source_ids if item not in existing_ids]
    if missing:
        result["missing_curve_ids"] = missing
    return result


def _unique_name(value: str, fallback: str, used: set[str]) -> str:
    base = str(value).strip() or fallback
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base} {suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


__all__ = ("ProjectRestoreResult", "restore_project_state")
