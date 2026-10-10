"""Apply persistent project records to the UI-independent V3 application state.

Projects from versions with the older curve and surface tools: their curves come back as 3D
Sketch curves (``ProjectRestoreResult.legacy_curves``, added once the model is loaded); their
mesh-preview and BREP surfaces cannot be rebuilt and are left out, with a warning.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from openretop.application.scene_ids import region_node_id
from openretop.application.state import AppState
from openretop.application.transform_math import build_object_transform_matrix
from openretop.geometry.sections import SectionPolyline, SectionResult, normalize_axis
from openretop.project.project_data import ProjectData
from openretop.regions.region_state import RegionCollection, RegionSelection
from openretop.sections.section_state import (
    SectionCollection,
    SectionPlaneState,
    StoredSectionResult,
    add_plane,
    add_result,
    create_default_section_plane,
    set_active_plane,
)
from openretop.settings.settings_data import DISPLAY_COLOR_FIELDS, AppSettings


@dataclass(frozen=True, slots=True)
class ProjectRestoreResult:
    warnings: tuple[str, ...] = ()
    selected_scene_ids: tuple[str, ...] = ()
    primary_selection_id: str | None = None
    # curves saved by the older curve tools: (name, points, closed), for the Surface Sketch
    legacy_curves: tuple[tuple[str, np.ndarray, bool], ...] = ()


def restore_project_state(
    state: AppState,
    project: ProjectData,
    *,
    settings: AppSettings | None = None,
) -> ProjectRestoreResult:
    """Restore all persistent V3 records while keeping controller state identity stable."""

    warnings: list[str] = []
    state.units = project.units
    state.units_assumed = bool(project.units_assumed)
    _restore_display(settings, project)
    _restore_mesh(state, project)
    state.section_collection = _restore_sections(project, warnings)
    state.region_collection = _restore_region(project)
    legacy_curves = _legacy_curves(project)
    dropped = len(project.surfaces) + len(project.brep_surfaces)
    if dropped:
        warnings.append(
            f"{dropped} surface(s) made with the older surface tools were not loaded: rebuild them from the curves "
            "(now in the Surface Sketch) with Loft, Fill or Face From Curves."
        )
    state.section_result = (
        state.section_collection.results[-1].result
        if state.section_collection.results
        else None
    )
    state.clear_selection()
    known = {item.id for item in state.section_collection.planes} | {item.id for item in state.section_collection.results}
    if project.region is not None:
        known.add(project.region.id)
    selected_ids = tuple(
        dict.fromkeys(str(value) for value in project.selected_scene_ids if any(str(value).endswith(item) for item in known))
    )
    if not selected_ids and project.region is not None and project.region.selected:
        selected_ids = (region_node_id(project.region.id),)
    return ProjectRestoreResult(
        legacy_curves=legacy_curves,
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


def _legacy_curves(project: ProjectData) -> tuple[tuple[str, np.ndarray, bool], ...]:
    result = []
    for saved in project.curves:
        points = np.asarray(saved.fitted_points if len(saved.fitted_points) >= 2 else saved.original_points, dtype=float)
        points = points.reshape(-1, 3) if points.size else np.zeros((0, 3))
        if len(points) >= 2 and np.all(np.isfinite(points)):
            result.append((str(saved.name), points, bool(saved.is_closed)))
    return tuple(result)


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
