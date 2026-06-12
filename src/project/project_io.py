"""Project serialization helpers."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from json import JSONDecodeError
from pathlib import Path

from project.project_data import (
    PROJECT_VERSION,
    ProjectCurve,
    ProjectData,
    ProjectDisplaySettings,
    ProjectSectionPlane,
    ProjectSectionSettings,
    ProjectSurface,
    ProjectTransform,
    default_project_data,
)


def save_project(project: ProjectData, path: Path) -> None:
    project_path = Path(path)
    project_path.write_text(
        json.dumps(project_to_dict(project), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_project(path: Path) -> ProjectData:
    project_path = Path(path)
    try:
        data = json.loads(project_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except JSONDecodeError as exc:
        raise ValueError(f"Invalid project JSON: {exc.msg}") from exc

    return project_from_dict(data)


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
        "section_planes": [
            {
                "id": plane.id,
                "name": plane.name,
                "axis": plane.axis,
                "offset": float(plane.offset),
                "visible": bool(plane.visible),
            }
            for plane in project.section_planes
        ],
        "active_section_plane_id": project.active_section_plane_id,
        "curves": [
            {
                "id": curve.id,
                "name": curve.name,
                "section_result_id": curve.section_result_id,
                "plane_id": curve.plane_id,
                "original_points": _points_to_nested_lists(
                    curve.original_points,
                    f"curves[{index}].original_points",
                ),
                "fitted_points": _points_to_nested_lists(
                    curve.fitted_points,
                    f"curves[{index}].fitted_points",
                ),
                "mean_error": float(curve.mean_error),
                "max_error": float(curve.max_error),
                "is_closed": bool(curve.is_closed),
                "visible": bool(curve.visible),
            }
            for index, curve in enumerate(project.curves)
        ],
        "surfaces": [
            {
                "id": surface.id,
                "name": surface.name,
                "source_curve_ids": list(surface.source_curve_ids),
                "surface_type": surface.surface_type,
                "visible": bool(surface.visible),
                "metadata": _metadata_dict_value(
                    surface.metadata,
                    f"surfaces[{index}].metadata",
                ),
            }
            for index, surface in enumerate(project.surfaces)
        ],
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
    section_planes = _section_planes_value(
        data.get("section_planes", defaults.section_planes),
        section,
    )
    active_section_plane_id = _optional_string_value(
        data.get("active_section_plane_id", defaults.active_section_plane_id),
        "active_section_plane_id",
    )
    curves = _curves_value(data.get("curves", defaults.curves))
    surfaces = _surfaces_value(data.get("surfaces", defaults.surfaces))
    return ProjectData(
        version=version,
        name=name,
        mesh_path=mesh_path,
        transform=transform,
        display=display,
        section=section,
        section_planes=section_planes,
        active_section_plane_id=active_section_plane_id,
        curves=curves,
        surfaces=surfaces,
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


def _mapping_value(value: object, field_name: str) -> Mapping[str, object]:
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


def _section_planes_value(
    value: object,
    fallback_section: ProjectSectionSettings,
) -> list[ProjectSectionPlane]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("section_planes must be a list.")

    planes: list[ProjectSectionPlane] = []
    seen_ids: set[str] = set()
    for index, raw_plane in enumerate(value):
        field_prefix = f"section_planes[{index}]"
        plane_data = _mapping_value(raw_plane, field_prefix)
        plane_id = _string_value(
            _nested_value(plane_data, "id", ""),
            f"{field_prefix}.id",
        )
        if not plane_id:
            raise ValueError(f"{field_prefix}.id must not be empty.")
        if plane_id in seen_ids:
            raise ValueError(f"{field_prefix}.id must be unique.")
        seen_ids.add(plane_id)

        planes.append(
            ProjectSectionPlane(
                id=plane_id,
                name=_string_value(
                    _nested_value(plane_data, "name", f"Section Plane {index + 1}"),
                    f"{field_prefix}.name",
                ),
                axis=_axis_value(
                    _nested_value(plane_data, "axis", fallback_section.axis),
                    f"{field_prefix}.axis",
                ),
                offset=_float_value(
                    _nested_value(plane_data, "offset", fallback_section.offset),
                    f"{field_prefix}.offset",
                ),
                visible=_bool_value(
                    _nested_value(plane_data, "visible", fallback_section.show_plane),
                    f"{field_prefix}.visible",
                ),
            )
        )

    return planes


def _curves_value(value: object) -> list[ProjectCurve]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("curves must be a list.")

    curves: list[ProjectCurve] = []
    seen_ids: set[str] = set()
    for index, raw_curve in enumerate(value):
        field_prefix = f"curves[{index}]"
        curve_data = _mapping_value(raw_curve, field_prefix)
        curve_id = _string_value(
            _nested_value(curve_data, "id", ""),
            f"{field_prefix}.id",
        )
        if not curve_id:
            raise ValueError(f"{field_prefix}.id must not be empty.")
        if curve_id in seen_ids:
            raise ValueError(f"{field_prefix}.id must be unique.")
        seen_ids.add(curve_id)

        curves.append(
            ProjectCurve(
                id=curve_id,
                name=_string_value(
                    _nested_value(curve_data, "name", f"Curve {index + 1}"),
                    f"{field_prefix}.name",
                ),
                section_result_id=_string_value(
                    _nested_value(curve_data, "section_result_id", ""),
                    f"{field_prefix}.section_result_id",
                ),
                plane_id=_string_value(
                    _nested_value(curve_data, "plane_id", ""),
                    f"{field_prefix}.plane_id",
                ),
                original_points=_points_value(
                    _nested_value(curve_data, "original_points", []),
                    f"{field_prefix}.original_points",
                ),
                fitted_points=_points_value(
                    _nested_value(curve_data, "fitted_points", []),
                    f"{field_prefix}.fitted_points",
                ),
                mean_error=_float_value(
                    _nested_value(curve_data, "mean_error", 0.0),
                    f"{field_prefix}.mean_error",
                ),
                max_error=_float_value(
                    _nested_value(curve_data, "max_error", 0.0),
                    f"{field_prefix}.max_error",
                ),
                is_closed=_bool_value(
                    _nested_value(curve_data, "is_closed", False),
                    f"{field_prefix}.is_closed",
                ),
                visible=_bool_value(
                    _nested_value(curve_data, "visible", True),
                    f"{field_prefix}.visible",
                ),
            )
        )

    return curves


def _surfaces_value(value: object) -> list[ProjectSurface]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("surfaces must be a list.")

    surfaces: list[ProjectSurface] = []
    seen_ids: set[str] = set()
    for index, raw_surface in enumerate(value):
        field_prefix = f"surfaces[{index}]"
        surface_data = _mapping_value(raw_surface, field_prefix)
        surface_id = _string_value(
            _nested_value(surface_data, "id", ""),
            f"{field_prefix}.id",
        )
        if not surface_id:
            raise ValueError(f"{field_prefix}.id must not be empty.")
        if surface_id in seen_ids:
            raise ValueError(f"{field_prefix}.id must be unique.")
        seen_ids.add(surface_id)

        surfaces.append(
            ProjectSurface(
                id=surface_id,
                name=_string_value(
                    _nested_value(surface_data, "name", f"Surface {index + 1}"),
                    f"{field_prefix}.name",
                ),
                source_curve_ids=_string_list_value(
                    _nested_value(surface_data, "source_curve_ids", []),
                    f"{field_prefix}.source_curve_ids",
                ),
                surface_type=_string_value(
                    _nested_value(surface_data, "surface_type", "placeholder"),
                    f"{field_prefix}.surface_type",
                ),
                visible=_bool_value(
                    _nested_value(surface_data, "visible", True),
                    f"{field_prefix}.visible",
                ),
                metadata=_metadata_dict_value(
                    _nested_value(surface_data, "metadata", {}),
                    f"{field_prefix}.metadata",
                ),
            )
        )

    return surfaces


def _string_list_value(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list of strings.")

    return [
        _string_value(item, f"{field_name}[{index}]")
        for index, item in enumerate(value)
    ]


def _metadata_dict_value(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
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
    if isinstance(value, Mapping):
        return _metadata_dict_value(value, field_name)
    raise ValueError(f"{field_name} must be JSON-safe.")


def _points_value(value: object, field_name: str) -> list[list[float]]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list of 3D points.")

    points: list[list[float]] = []
    for index, raw_point in enumerate(value):
        point_field = f"{field_name}[{index}]"
        if not isinstance(raw_point, list | tuple):
            raise ValueError(f"{point_field} must be a list of three numbers.")
        if len(raw_point) != 3:
            raise ValueError(f"{point_field} must contain exactly three values.")
        points.append(
            [
                _float_value(component, f"{point_field}[{component_index}]")
                for component_index, component in enumerate(raw_point)
            ]
        )
    return points


def _points_to_nested_lists(value: object, field_name: str) -> list[list[float]]:
    if isinstance(value, str) or not isinstance(value, Iterable):
        raise ValueError(f"{field_name} must be an iterable of 3D points.")

    point_rows: list[list[object]] = []
    for index, point in enumerate(value):
        if isinstance(point, str) or not isinstance(point, Iterable):
            raise ValueError(f"{field_name}[{index}] must be an iterable of three numbers.")
        point_rows.append(list(point))

    return _points_value(point_rows, field_name)


def _axis_value(value: object, field_name: str) -> str:
    axis = _string_value(value, field_name).upper()
    if axis not in {"X", "Y", "Z"}:
        raise ValueError(f"{field_name} must be X, Y, or Z.")
    return axis
