"""Project serialization helpers."""

from __future__ import annotations

from collections.abc import Mapping

from project.project_data import (
    PROJECT_VERSION,
    ProjectData,
    ProjectDisplaySettings,
    ProjectSectionSettings,
    ProjectTransform,
    default_project_data,
)


def project_to_dict(project: ProjectData) -> dict[str, object]:
    if not isinstance(project, ProjectData):
        raise ValueError("Expected ProjectData.")

    return {
        "version": int(project.version),
        "name": project.name,
        "mesh_path": project.mesh_path,
        "transform": {
            "location": list(project.transform.location),
            "rotation": list(project.transform.rotation),
            "scale": float(project.transform.scale),
            "origin": list(project.transform.origin),
        },
        "display": {
            "proxy_quality": project.display.proxy_quality,
            "show_grid": bool(project.display.show_grid),
            "show_axes": bool(project.display.show_axes),
            "show_normals": bool(project.display.show_normals),
        },
        "section": {
            "axis": project.section.axis,
            "offset": float(project.section.offset),
            "show_plane": bool(project.section.show_plane),
        },
    }


def project_from_dict(data: dict[str, object]) -> ProjectData:
    if not isinstance(data, Mapping):
        raise ValueError("Project data must be a dictionary.")

    defaults = default_project_data()
    version = _project_version(data.get("version", defaults.version))
    name = _string_value(data.get("name", defaults.name), "name")
    mesh_path = _optional_string_value(
        data.get("mesh_path", defaults.mesh_path),
        "mesh_path",
    )
    transform_data = _optional_mapping(data.get("transform"), "transform")
    display_data = _optional_mapping(data.get("display"), "display")
    section_data = _optional_mapping(data.get("section"), "section")

    transform = ProjectTransform(
        location=_vector3_value(
            _nested_value(transform_data, "location", defaults.transform.location),
            "transform.location",
        ),
        rotation=_vector3_value(
            _nested_value(transform_data, "rotation", defaults.transform.rotation),
            "transform.rotation",
        ),
        scale=_positive_float_value(
            _nested_value(transform_data, "scale", defaults.transform.scale),
            "transform.scale",
        ),
        origin=_vector3_value(
            _nested_value(transform_data, "origin", defaults.transform.origin),
            "transform.origin",
        ),
    )
    display = ProjectDisplaySettings(
        proxy_quality=_string_value(
            _nested_value(display_data, "proxy_quality", defaults.display.proxy_quality),
            "display.proxy_quality",
        ),
        show_grid=_bool_value(
            _nested_value(display_data, "show_grid", defaults.display.show_grid),
            "display.show_grid",
        ),
        show_axes=_bool_value(
            _nested_value(display_data, "show_axes", defaults.display.show_axes),
            "display.show_axes",
        ),
        show_normals=_bool_value(
            _nested_value(display_data, "show_normals", defaults.display.show_normals),
            "display.show_normals",
        ),
    )
    section = ProjectSectionSettings(
        axis=_axis_value(
            _nested_value(section_data, "axis", defaults.section.axis),
            "section.axis",
        ),
        offset=_float_value(
            _nested_value(section_data, "offset", defaults.section.offset),
            "section.offset",
        ),
        show_plane=_bool_value(
            _nested_value(section_data, "show_plane", defaults.section.show_plane),
            "section.show_plane",
        ),
    )
    return ProjectData(
        version=version,
        name=name,
        mesh_path=mesh_path,
        transform=transform,
        display=display,
        section=section,
    )


def _project_version(value: object) -> int:
    version = _int_value(value, "version")
    if version != PROJECT_VERSION:
        raise ValueError(f"Unsupported project version: {version}")
    return version


def _optional_mapping(value: object, field_name: str) -> Mapping[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a dictionary.")
    return value


def _nested_value(
    data: Mapping[str, object] | None,
    key: str,
    default: object,
) -> object:
    if data is None:
        return default
    return data.get(key, default)


def _vector3_value(value: object, field_name: str) -> list[float]:
    if not isinstance(value, list | tuple):
        raise ValueError(f"{field_name} must be a list of three numbers.")
    if len(value) != 3:
        raise ValueError(f"{field_name} must contain exactly three values.")
    return [
        _float_value(component, f"{field_name}[{index}]")
        for index, component in enumerate(value)
    ]


def _positive_float_value(value: object, field_name: str) -> float:
    number = _float_value(value, field_name)
    if number <= 0.0:
        raise ValueError(f"{field_name} must be greater than zero.")
    return number


def _float_value(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field_name} must be a number.")
    return float(value)


def _int_value(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer.")
    return int(value)


def _bool_value(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be true or false.")
    return value


def _string_value(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string.")
    return value


def _optional_string_value(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _string_value(value, field_name)


def _axis_value(value: object, field_name: str) -> str:
    axis = _string_value(value, field_name).upper()
    if axis not in {"X", "Y", "Z"}:
        raise ValueError(f"{field_name} must be X, Y, or Z.")
    return axis
