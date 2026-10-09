"""Project data export helpers for current app state."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from openretop.project.project_data import (
    ProjectData,
    ProjectDisplaySettings,
    ProjectRegion,
    ProjectSectionPlane,
    ProjectSectionResult,
    ProjectSectionSettings,
    ProjectTransform,
    default_project_data,
)
from openretop.regions.region_state import RegionCollection
from openretop.sections.section_state import SectionCollection, plane_normal, plane_origin


def project_from_app_state(
    *,
    mesh_object: object | None,
    proxy_quality: str,
    show_grid: bool,
    show_axes: bool,
    show_normals: bool,
    section_axis: str,
    section_offset: float,
    show_section_plane: bool,
    display_colors: dict[str, str] | None = None,
    section_collection: SectionCollection | None = None,
    region_collection: RegionCollection | None = None,
    selected_scene_ids: Iterable[str] = (),
    primary_selection_id: str | None = None,
    units: str = "mm",
    units_assumed: bool = False,
) -> ProjectData:
    defaults = default_project_data()
    mesh_path = None
    mesh_name = None
    mesh_visible = True
    transform = defaults.transform
    section = ProjectSectionSettings(
        axis=str(section_axis).upper(),
        offset=_float_from_value(section_offset, "section_offset"),
        show_plane=bool(show_section_plane),
    )
    section_planes = _section_planes_from_collection(section_collection)
    section_results = _section_results_from_collection(section_collection)
    active_section_plane_id = _active_plane_id_from_collection(
        section_collection,
        section_planes,
    )
    region = _region_from_collection(region_collection)

    if mesh_object is not None:
        file_path = getattr(mesh_object, "file_path", None)
        mesh_path = str(file_path) if file_path is not None else None
        mesh_name = getattr(mesh_object, "name", None)
        mesh_name = str(mesh_name) if mesh_name is not None else None
        mesh_visible = bool(getattr(mesh_object, "visible", True))
        transform = ProjectTransform(
            location=_vector3_from_value(
                _required_mesh_value(mesh_object, "location"),
                "mesh_object.location",
            ),
            rotation=_vector3_from_value(
                _required_mesh_value(mesh_object, "rotation"),
                "mesh_object.rotation",
            ),
            scale=_positive_float_from_value(
                _required_mesh_value(mesh_object, "scale"),
                "mesh_object.scale",
            ),
            origin=_vector3_from_value(
                _required_mesh_value(mesh_object, "origin"),
                "mesh_object.origin",
            ),
        )

    return ProjectData(
        version=defaults.version,
        name=defaults.name,
        mesh_path=mesh_path,
        mesh_name=mesh_name,
        mesh_visible=mesh_visible,
        units=units,
        units_assumed=bool(units_assumed),
        transform=transform,
        display=ProjectDisplaySettings(
            proxy_quality=str(proxy_quality),
            show_grid=bool(show_grid),
            show_axes=bool(show_axes),
            show_normals=bool(show_normals),
            colors=dict(display_colors or {}),
        ),
        section=section,
        section_planes=section_planes,
        active_section_plane_id=active_section_plane_id,
        section_results=section_results,
        region=region,
        selected_scene_ids=list(dict.fromkeys(str(value) for value in selected_scene_ids)),
        primary_selection_id=(
            None if primary_selection_id is None else str(primary_selection_id)
        ),
    )


def _region_from_collection(collection: RegionCollection | None) -> ProjectRegion | None:
    if collection is None or collection.active_region is None:
        return None
    region = collection.active_region
    return ProjectRegion(
        id=str(region.id),
        name=str(region.name),
        triangle_indices=[int(value) for value in region.triangle_indices],
        threshold_degrees=float(region.threshold_degrees),
        max_triangle_count=int(region.max_triangle_count),
        source_mesh_identifier=str(region.source_mesh_identifier),
        source_mesh_name=str(region.source_mesh_name),
        seed_triangle_index=(
            None if region.seed_triangle_index is None else int(region.seed_triangle_index)
        ),
        visible=bool(region.visible),
        selected=bool(region.selected),
        metadata=_metadata_from_value(region.metadata, "region.metadata"),
    )


def _required_mesh_value(mesh_object: object, attribute: str) -> Any:
    if not hasattr(mesh_object, attribute):
        raise ValueError(f"mesh_object must provide {attribute}.")
    return getattr(mesh_object, attribute)


def _vector3_from_value(value: object, field_name: str) -> list[float]:
    if isinstance(value, str) or not isinstance(value, Iterable):
        raise ValueError(f"{field_name} must be an iterable of three numbers.")

    values = list(value)
    if len(values) != 3:
        raise ValueError(f"{field_name} must contain exactly three values.")

    return [
        _float_from_value(component, f"{field_name}[{index}]")
        for index, component in enumerate(values)
    ]


def _positive_float_from_value(value: object, field_name: str) -> float:
    number = _float_from_value(value, field_name)
    if number <= 0.0:
        raise ValueError(f"{field_name} must be greater than zero.")
    return number


def _float_from_value(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field_name} must be a number.")
    return float(value)


def _section_planes_from_collection(
    section_collection: SectionCollection | None,
) -> list[ProjectSectionPlane]:
    if section_collection is None:
        return []

    return [
        ProjectSectionPlane(
            id=str(plane.id),
            name=str(plane.name),
            axis=str(plane.axis).upper(),
            offset=_float_from_value(plane.offset, "section_collection.plane.offset"),
            visible=bool(plane.visible),
            origin=_vector3_from_value(
                plane_origin(plane),
                "section_collection.plane.origin",
            ),
            normal=_vector3_from_value(
                plane_normal(plane),
                "section_collection.plane.normal",
            ),
        )
        for plane in section_collection.planes
    ]


def _section_results_from_collection(
    section_collection: SectionCollection | None,
) -> list[ProjectSectionResult]:
    if section_collection is None:
        return []

    return [
        ProjectSectionResult(
            id=str(result.id),
            name=str(result.name),
            plane_id=str(result.plane_id),
            axis=str(result.axis).upper(),
            offset=_float_from_value(
                result.offset,
                "section_collection.result.offset",
            ),
            visible=bool(result.visible),
            plane_origin=_vector3_from_value(
                result.plane_origin,
                "section_collection.result.plane_origin",
            ),
            plane_normal=_vector3_from_value(
                result.plane_normal,
                "section_collection.result.plane_normal",
            ),
            is_arbitrary_plane=bool(result.is_arbitrary_plane),
            polylines=[
                _points_from_value(
                    polyline.points,
                    "section_collection.result.polylines",
                )
                for polyline in result.result.polylines
            ],
            segment_count=int(result.result.segment_count),
        )
        for result in section_collection.results
    ]


def _metadata_from_value(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a dictionary.")

    metadata: dict[str, object] = {}
    for key, raw_item in value.items():
        if not isinstance(key, str):
            raise ValueError(f"{field_name} keys must be strings.")
        metadata[key] = _json_safe_value(raw_item, f"{field_name}.{key}")
    return metadata


def _json_safe_value(value: object, field_name: str) -> object:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list):
        return [
            _json_safe_value(item, f"{field_name}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        return _metadata_from_value(value, field_name)
    raise ValueError(f"{field_name} must be JSON-safe.")


def _points_from_value(value: object, field_name: str) -> list[list[float]]:
    if isinstance(value, str) or not isinstance(value, Iterable):
        raise ValueError(f"{field_name} must be an iterable of 3D points.")

    points: list[list[float]] = []
    for index, raw_point in enumerate(value):
        point_field = f"{field_name}[{index}]"
        if isinstance(raw_point, str) or not isinstance(raw_point, Iterable):
            raise ValueError(f"{point_field} must be an iterable of three numbers.")
        point = list(raw_point)
        if len(point) != 3:
            raise ValueError(f"{point_field} must contain exactly three values.")
        points.append(
            [
                _float_from_value(component, f"{point_field}[{component_index}]")
                for component_index, component in enumerate(point)
            ]
        )

    return points


def _active_plane_id_from_collection(
    section_collection: SectionCollection | None,
    section_planes: list[ProjectSectionPlane],
) -> str | None:
    if section_collection is None or section_collection.active_plane_id is None:
        return None

    active_plane_id = str(section_collection.active_plane_id)
    plane_ids = {plane.id for plane in section_planes}
    if active_plane_id not in plane_ids:
        return None
    return active_plane_id
