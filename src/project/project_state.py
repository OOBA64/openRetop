"""Project data export helpers for current app state."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from project.project_data import (
    ProjectData,
    ProjectDisplaySettings,
    ProjectSectionPlane,
    ProjectSectionSettings,
    ProjectTransform,
    default_project_data,
)
from sections.section_state import SectionCollection


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
    section_collection: SectionCollection | None = None,
) -> ProjectData:
    defaults = default_project_data()
    mesh_path = None
    transform = defaults.transform
    section = ProjectSectionSettings(
        axis=str(section_axis).upper(),
        offset=_float_from_value(section_offset, "section_offset"),
        show_plane=bool(show_section_plane),
    )
    section_planes = _section_planes_from_collection(section_collection)
    active_section_plane_id = _active_plane_id_from_collection(
        section_collection,
        section_planes,
    )

    if mesh_object is not None:
        file_path = getattr(mesh_object, "file_path", None)
        mesh_path = str(file_path) if file_path is not None else None
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
        transform=transform,
        display=ProjectDisplaySettings(
            proxy_quality=str(proxy_quality),
            show_grid=bool(show_grid),
            show_axes=bool(show_axes),
            show_normals=bool(show_normals),
        ),
        section=section,
        section_planes=section_planes,
        active_section_plane_id=active_section_plane_id,
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
        )
        for plane in section_collection.planes
    ]


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
