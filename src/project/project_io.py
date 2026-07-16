"""Project serialization helpers."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from json import JSONDecodeError
from pathlib import Path

from project.project_data import (
    PROJECT_VERSION,
    ProjectBrepSurface,
    ProjectCurve,
    ProjectData,
    ProjectDisplaySettings,
    ProjectFourBoundaryPatchFeature,
    ProjectLoftFeature,
    ProjectRegion,
    ProjectSectionPlane,
    ProjectSectionResult,
    ProjectSectionSettings,
    ProjectSurface,
    ProjectTransform,
    default_project_data,
)


_KNOWN_PROJECT_KEYS = frozenset(
    {
        "version",
        "name",
        "mesh_path",
        "mesh_name",
        "mesh_visible",
        "transform",
        "display",
        "section",
        "section_planes",
        "active_section_plane_id",
        "section_results",
        "curves",
        "region",
        "surfaces",
        "brep_surfaces",
        "loft_features",
        "four_boundary_patch_features",
        "selected_scene_ids",
        "primary_selection_id",
        "metadata",
    }
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

    result: dict[str, object] = {
        "version": int(project.version),
        "name": project.name,
        "mesh_path": project.mesh_path,
        "mesh_name": project.mesh_name,
        "mesh_visible": bool(project.mesh_visible),
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
            "colors": dict(project.display.colors),
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
                "origin": _vector3_value(plane.origin, f"section_planes[{index}].origin"),
                "normal": _vector3_value(plane.normal, f"section_planes[{index}].normal"),
            }
            for index, plane in enumerate(project.section_planes)
        ],
        "active_section_plane_id": project.active_section_plane_id,
        "section_results": [
            {
                "id": result.id,
                "name": result.name,
                "plane_id": result.plane_id,
                "axis": result.axis,
                "offset": float(result.offset),
                "visible": bool(result.visible),
                "plane_origin": _vector3_value(
                    result.plane_origin,
                    f"section_results[{index}].plane_origin",
                ),
                "plane_normal": _vector3_value(
                    result.plane_normal,
                    f"section_results[{index}].plane_normal",
                ),
                "is_arbitrary_plane": bool(result.is_arbitrary_plane),
                "polylines": [
                    _points_to_nested_lists(
                        polyline,
                        f"section_results[{index}].polylines[{polyline_index}]",
                    )
                    for polyline_index, polyline in enumerate(result.polylines)
                ],
                "segment_count": int(result.segment_count),
            }
            for index, result in enumerate(project.section_results)
        ],
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
                "point_count": int(curve.point_count),
                "length": float(curve.length),
                "endpoint_distance": float(curve.endpoint_distance),
                "bounding_box_size": float(curve.bounding_box_size),
                "is_tiny_fragment": bool(curve.is_tiny_fragment),
                "source_section_result_id": curve.source_section_result_id,
                "source_plane_id": curve.source_plane_id,
                "metadata": _metadata_dict_value(
                    curve.metadata,
                    f"curves[{index}].metadata",
                ),
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
        "brep_surfaces": [
            {
                "id": surface.id,
                "name": surface.name,
                "source_curve_ids": list(surface.source_curve_ids),
                "brep_type": surface.brep_type,
                "backend": surface.backend,
                "visible": bool(surface.visible),
                "selected": bool(surface.selected),
                "metadata": _metadata_dict_value(
                    surface.metadata,
                    f"brep_surfaces[{index}].metadata",
                ),
            }
            for index, surface in enumerate(project.brep_surfaces)
        ],
    }
    if project.region is not None:
        result["region"] = {
            "id": project.region.id,
            "name": project.region.name,
            "triangle_indices": list(project.region.triangle_indices),
            "threshold_degrees": float(project.region.threshold_degrees),
            "max_triangle_count": int(project.region.max_triangle_count),
            "source_mesh_identifier": project.region.source_mesh_identifier,
            "source_mesh_name": project.region.source_mesh_name,
            "seed_triangle_index": project.region.seed_triangle_index,
            "visible": bool(project.region.visible),
            "selected": bool(project.region.selected),
            "metadata": _metadata_dict_value(project.region.metadata, "region.metadata"),
        }
    if project.selected_scene_ids:
        result["selected_scene_ids"] = list(project.selected_scene_ids)
    if project.primary_selection_id is not None:
        result["primary_selection_id"] = project.primary_selection_id
    if project.loft_features:
        result["loft_features"] = [
            {
                "id": feature.id,
                "name": feature.name,
                "options": _metadata_dict_value(
                    feature.options,
                    f"loft_features[{index}].options",
                ),
                "brep_surface_id": feature.brep_surface_id,
                "preview_surface_id": feature.preview_surface_id,
                "last_build_success": bool(feature.last_build_success),
                "last_build_reason": feature.last_build_reason,
                "last_build_warnings": list(feature.last_build_warnings),
                "metadata": _metadata_dict_value(
                    feature.metadata,
                    f"loft_features[{index}].metadata",
                ),
            }
            for index, feature in enumerate(project.loft_features)
        ]
    if project.four_boundary_patch_features:
        result["four_boundary_patch_features"] = [
            {
                "id": feature.id,
                "name": feature.name,
                "source_curve_ids": list(feature.source_curve_ids),
                "preserve_corners": bool(feature.preserve_corners),
                "match_directions": bool(feature.match_directions),
                "fill_method": feature.fill_method,
                "brep_surface_id": feature.brep_surface_id,
                "preview_surface_id": feature.preview_surface_id,
                "last_build_status": feature.last_build_status,
                "metadata": _metadata_dict_value(
                    feature.metadata,
                    f"four_boundary_patch_features[{index}].metadata",
                ),
            }
            for index, feature in enumerate(project.four_boundary_patch_features)
        ]
    for key, value in project.metadata.items():
        if key not in result and key != "metadata":
            result[str(key)] = value
    return result


def project_from_dict(data: dict[str, object]) -> ProjectData:
    if not isinstance(data, Mapping):
        raise ValueError("Project data must be a dictionary.")

    defaults = default_project_data()
    raw_metadata = data.get("metadata", {})
    if raw_metadata is not None and not isinstance(raw_metadata, Mapping):
        raise ValueError("metadata must be a dictionary.")
    metadata = {
        **{
            str(key): value
            for key, value in data.items()
            if key not in _KNOWN_PROJECT_KEYS
        },
        **(dict(raw_metadata) if raw_metadata is not None else {}),
    }
    version = _project_version(data.get("version", defaults.version))
    name = _string_value(data.get("name", defaults.name), "name")
    mesh_path = _optional_string_value(
        data.get("mesh_path", defaults.mesh_path),
        "mesh_path",
    )
    mesh_name = _optional_string_value(
        data.get("mesh_name", defaults.mesh_name),
        "mesh_name",
    )
    mesh_visible = _bool_value(
        data.get("mesh_visible", defaults.mesh_visible),
        "mesh_visible",
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
        colors=_display_colors_value(
            _nested_value(display_data, "colors", defaults.display.colors)
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
    section_results = _section_results_value(
        data.get("section_results", defaults.section_results)
    )
    curves = _curves_value(data.get("curves", defaults.curves))
    region = _region_value(data.get("region", defaults.region))
    surfaces = _surfaces_value(data.get("surfaces", defaults.surfaces))
    brep_surfaces = _brep_surfaces_value(
        data.get("brep_surfaces", defaults.brep_surfaces)
    )
    loft_features = _loft_features_value(
        data.get("loft_features", defaults.loft_features)
    )
    four_boundary_patch_features = _four_boundary_features_value(
        data.get(
            "four_boundary_patch_features",
            defaults.four_boundary_patch_features,
        )
    )
    selected_scene_ids = _string_list_value(
        data.get("selected_scene_ids", defaults.selected_scene_ids),
        "selected_scene_ids",
    )
    primary_selection_id = _optional_string_value(
        data.get("primary_selection_id", defaults.primary_selection_id),
        "primary_selection_id",
    )
    return ProjectData(
        version=version,
        name=name,
        mesh_path=mesh_path,
        mesh_name=mesh_name,
        mesh_visible=mesh_visible,
        transform=transform,
        display=display,
        section=section,
        section_planes=section_planes,
        active_section_plane_id=active_section_plane_id,
        section_results=section_results,
        curves=curves,
        region=region,
        surfaces=surfaces,
        brep_surfaces=brep_surfaces,
        loft_features=loft_features,
        four_boundary_patch_features=four_boundary_patch_features,
        selected_scene_ids=selected_scene_ids,
        primary_selection_id=primary_selection_id,
        metadata=metadata,
    )


def _project_version(value: object) -> int:
    version = _int_value(value, "version")
    if version != PROJECT_VERSION:
        raise ValueError(f"Unsupported project version: {version}")
    return version


def _region_value(value: object) -> ProjectRegion | None:
    if value is None:
        return None
    data = _mapping_value(value, "region")
    triangle_values = data.get("triangle_indices", [])
    if not isinstance(triangle_values, list):
        raise ValueError("region.triangle_indices must be a list.")
    triangle_indices = [
        _int_value(item, f"region.triangle_indices[{index}]")
        for index, item in enumerate(triangle_values)
    ]
    seed_value = data.get("seed_triangle_index")
    seed_triangle_index = (
        None if seed_value is None else _int_value(seed_value, "region.seed_triangle_index")
    )
    return ProjectRegion(
        id=_string_value(data.get("id", "region-restored"), "region.id"),
        name=_string_value(data.get("name", "Region 1"), "region.name"),
        triangle_indices=triangle_indices,
        threshold_degrees=_float_value(
            data.get("threshold_degrees", 20.0), "region.threshold_degrees"
        ),
        max_triangle_count=_int_value(
            data.get("max_triangle_count", 50_000), "region.max_triangle_count"
        ),
        source_mesh_identifier=_string_value(
            data.get("source_mesh_identifier", ""), "region.source_mesh_identifier"
        ),
        source_mesh_name=_string_value(
            data.get("source_mesh_name", ""), "region.source_mesh_name"
        ),
        seed_triangle_index=seed_triangle_index,
        visible=_bool_value(data.get("visible", True), "region.visible"),
        selected=_bool_value(data.get("selected", False), "region.selected"),
        metadata=_metadata_dict_value(data.get("metadata", {}), "region.metadata"),
    )


def _display_colors_value(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    colors: dict[str, str] = {}
    for key, color in value.items():
        if not isinstance(key, str) or not isinstance(color, str):
            continue
        normalized = color.strip().upper()
        if len(normalized) != 7 or not normalized.startswith("#"):
            continue
        try:
            int(normalized[1:], 16)
        except ValueError:
            continue
        colors[key] = normalized
    return colors


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

        origin_value = _nested_value(plane_data, "origin", None)
        normal_value = _nested_value(plane_data, "normal", None)
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
                origin=(
                    None
                    if origin_value is None
                    else _vector3_value(origin_value, f"{field_prefix}.origin")
                ),
                normal=(
                    None
                    if normal_value is None
                    else _vector3_value(normal_value, f"{field_prefix}.normal")
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
                point_count=(
                    None
                    if _nested_value(curve_data, "point_count", None) is None
                    else _int_value(
                        _nested_value(curve_data, "point_count", None),
                        f"{field_prefix}.point_count",
                    )
                ),
                length=(
                    None
                    if _nested_value(curve_data, "length", None) is None
                    else _float_value(
                        _nested_value(curve_data, "length", None),
                        f"{field_prefix}.length",
                    )
                ),
                endpoint_distance=(
                    None
                    if _nested_value(curve_data, "endpoint_distance", None) is None
                    else _float_value(
                        _nested_value(curve_data, "endpoint_distance", None),
                        f"{field_prefix}.endpoint_distance",
                    )
                ),
                bounding_box_size=(
                    None
                    if _nested_value(curve_data, "bounding_box_size", None) is None
                    else _float_value(
                        _nested_value(curve_data, "bounding_box_size", None),
                        f"{field_prefix}.bounding_box_size",
                    )
                ),
                is_tiny_fragment=(
                    None
                    if _nested_value(curve_data, "is_tiny_fragment", None) is None
                    else _bool_value(
                        _nested_value(curve_data, "is_tiny_fragment", None),
                        f"{field_prefix}.is_tiny_fragment",
                    )
                ),
                source_section_result_id=(
                    None
                    if _nested_value(curve_data, "source_section_result_id", None) is None
                    else _string_value(
                        _nested_value(curve_data, "source_section_result_id", None),
                        f"{field_prefix}.source_section_result_id",
                    )
                ),
                source_plane_id=(
                    None
                    if _nested_value(curve_data, "source_plane_id", None) is None
                    else _string_value(
                        _nested_value(curve_data, "source_plane_id", None),
                        f"{field_prefix}.source_plane_id",
                    )
                ),
                metadata=_metadata_dict_value(
                    _nested_value(curve_data, "metadata", {}),
                    f"{field_prefix}.metadata",
                ),
            )
        )

    return curves


def _section_results_value(value: object) -> list[ProjectSectionResult]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("section_results must be a list.")

    results: list[ProjectSectionResult] = []
    seen_ids: set[str] = set()
    for index, raw_result in enumerate(value):
        field_prefix = f"section_results[{index}]"
        result_data = _mapping_value(raw_result, field_prefix)
        result_id = _string_value(
            _nested_value(result_data, "id", ""),
            f"{field_prefix}.id",
        )
        if not result_id:
            raise ValueError(f"{field_prefix}.id must not be empty.")
        if result_id in seen_ids:
            raise ValueError(f"{field_prefix}.id must be unique.")
        seen_ids.add(result_id)

        results.append(
            ProjectSectionResult(
                id=result_id,
                name=_string_value(
                    _nested_value(result_data, "name", f"Section {index + 1}"),
                    f"{field_prefix}.name",
                ),
                plane_id=_string_value(
                    _nested_value(result_data, "plane_id", ""),
                    f"{field_prefix}.plane_id",
                ),
                axis=_axis_value(
                    _nested_value(result_data, "axis", "Z"),
                    f"{field_prefix}.axis",
                ),
                offset=_float_value(
                    _nested_value(result_data, "offset", 0.0),
                    f"{field_prefix}.offset",
                ),
                visible=_bool_value(
                    _nested_value(result_data, "visible", True),
                    f"{field_prefix}.visible",
                ),
                plane_origin=(
                    None
                    if _nested_value(result_data, "plane_origin", None) is None
                    else _vector3_value(
                        _nested_value(result_data, "plane_origin", None),
                        f"{field_prefix}.plane_origin",
                    )
                ),
                plane_normal=(
                    None
                    if _nested_value(result_data, "plane_normal", None) is None
                    else _vector3_value(
                        _nested_value(result_data, "plane_normal", None),
                        f"{field_prefix}.plane_normal",
                    )
                ),
                is_arbitrary_plane=_bool_value(
                    _nested_value(result_data, "is_arbitrary_plane", False),
                    f"{field_prefix}.is_arbitrary_plane",
                ),
                polylines=_polyline_list_value(
                    _nested_value(result_data, "polylines", []),
                    f"{field_prefix}.polylines",
                ),
                segment_count=_int_value(
                    _nested_value(result_data, "segment_count", 0),
                    f"{field_prefix}.segment_count",
                ),
            )
        )

    return results


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


def _brep_surfaces_value(value: object) -> list[ProjectBrepSurface]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("brep_surfaces must be a list.")

    surfaces: list[ProjectBrepSurface] = []
    seen_ids: set[str] = set()
    for index, raw_surface in enumerate(value):
        field_prefix = f"brep_surfaces[{index}]"
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
            ProjectBrepSurface(
                id=surface_id,
                name=_string_value(
                    _nested_value(surface_data, "name", f"BREP Surface {index + 1}"),
                    f"{field_prefix}.name",
                ),
                source_curve_ids=_string_list_value(
                    _nested_value(surface_data, "source_curve_ids", []),
                    f"{field_prefix}.source_curve_ids",
                ),
                brep_type=_string_value(
                    _nested_value(surface_data, "brep_type", "unknown"),
                    f"{field_prefix}.brep_type",
                ),
                backend=_string_value(
                    _nested_value(surface_data, "backend", ""),
                    f"{field_prefix}.backend",
                ),
                visible=_bool_value(
                    _nested_value(surface_data, "visible", True),
                    f"{field_prefix}.visible",
                ),
                selected=_bool_value(
                    _nested_value(surface_data, "selected", False),
                    f"{field_prefix}.selected",
                ),
                metadata=_metadata_dict_value(
                    _nested_value(surface_data, "metadata", {}),
                    f"{field_prefix}.metadata",
                ),
            )
        )

    return surfaces


def _loft_features_value(value: object) -> list[ProjectLoftFeature]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("loft_features must be a list.")
    features: list[ProjectLoftFeature] = []
    seen_ids: set[str] = set()
    for index, raw_feature in enumerate(value):
        prefix = f"loft_features[{index}]"
        data = _mapping_value(raw_feature, prefix)
        feature_id = _string_value(_nested_value(data, "id", ""), f"{prefix}.id")
        if not feature_id or feature_id in seen_ids:
            raise ValueError(f"{prefix}.id must be non-empty and unique.")
        seen_ids.add(feature_id)
        warnings = _string_list_value(
            _nested_value(data, "last_build_warnings", []),
            f"{prefix}.last_build_warnings",
        )
        features.append(
            ProjectLoftFeature(
                id=feature_id,
                name=_string_value(
                    _nested_value(data, "name", f"Editable Loft {index + 1}"),
                    f"{prefix}.name",
                ),
                options=_metadata_dict_value(
                    _nested_value(data, "options", {}),
                    f"{prefix}.options",
                ),
                brep_surface_id=_optional_string_value(
                    _nested_value(data, "brep_surface_id", None),
                    f"{prefix}.brep_surface_id",
                ),
                preview_surface_id=_optional_string_value(
                    _nested_value(data, "preview_surface_id", None),
                    f"{prefix}.preview_surface_id",
                ),
                last_build_success=_bool_value(
                    _nested_value(data, "last_build_success", False),
                    f"{prefix}.last_build_success",
                ),
                last_build_reason=_string_value(
                    _nested_value(data, "last_build_reason", "Not built."),
                    f"{prefix}.last_build_reason",
                ),
                last_build_warnings=warnings,
                metadata=_metadata_dict_value(
                    _nested_value(data, "metadata", {}),
                    f"{prefix}.metadata",
                ),
            )
        )
    return features


def _four_boundary_features_value(
    value: object,
) -> list[ProjectFourBoundaryPatchFeature]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("four_boundary_patch_features must be a list.")
    features: list[ProjectFourBoundaryPatchFeature] = []
    seen_ids: set[str] = set()
    for index, raw_feature in enumerate(value):
        prefix = f"four_boundary_patch_features[{index}]"
        data = _mapping_value(raw_feature, prefix)
        feature_id = _string_value(_nested_value(data, "id", ""), f"{prefix}.id")
        if not feature_id or feature_id in seen_ids:
            raise ValueError(f"{prefix}.id must be non-empty and unique.")
        seen_ids.add(feature_id)
        features.append(
            ProjectFourBoundaryPatchFeature(
                id=feature_id,
                name=_string_value(
                    _nested_value(data, "name", f"Four-Boundary Patch {index + 1}"),
                    f"{prefix}.name",
                ),
                source_curve_ids=_string_list_value(
                    _nested_value(data, "source_curve_ids", []),
                    f"{prefix}.source_curve_ids",
                ),
                preserve_corners=_bool_value(
                    _nested_value(data, "preserve_corners", True),
                    f"{prefix}.preserve_corners",
                ),
                match_directions=_bool_value(
                    _nested_value(data, "match_directions", True),
                    f"{prefix}.match_directions",
                ),
                fill_method=_string_value(
                    _nested_value(data, "fill_method", "coons_preview"),
                    f"{prefix}.fill_method",
                ),
                brep_surface_id=_optional_string_value(
                    _nested_value(data, "brep_surface_id", None),
                    f"{prefix}.brep_surface_id",
                ),
                preview_surface_id=_optional_string_value(
                    _nested_value(data, "preview_surface_id", None),
                    f"{prefix}.preview_surface_id",
                ),
                last_build_status=_string_value(
                    _nested_value(data, "last_build_status", "Not built."),
                    f"{prefix}.last_build_status",
                ),
                metadata=_metadata_dict_value(
                    _nested_value(data, "metadata", {}),
                    f"{prefix}.metadata",
                ),
            )
        )
    return features


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


def _polyline_list_value(value: object, field_name: str) -> list[list[list[float]]]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list.")

    return [
        _points_value(polyline, f"{field_name}[{index}]")
        for index, polyline in enumerate(value)
    ]


def _axis_value(value: object, field_name: str) -> str:
    axis = _string_value(value, field_name).upper()
    if axis not in {"X", "Y", "Z"}:
        raise ValueError(f"{field_name} must be X, Y, or Z.")
    return axis
