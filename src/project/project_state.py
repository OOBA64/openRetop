"""Project data export helpers for current app state."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from curves.curve_state import CurveCollection, refresh_curve_diagnostics
from curves.manual_curve import ensure_manual_curve_storage
from project.project_data import (
    ProjectCurve,
    ProjectData,
    ProjectDisplaySettings,
    ProjectSectionPlane,
    ProjectSectionResult,
    ProjectSectionSettings,
    ProjectSurface,
    ProjectTransform,
    default_project_data,
)
from sections.section_state import SectionCollection, plane_normal, plane_origin
from surfaces.surface_state import SurfaceCollection


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
    curve_collection: CurveCollection | None = None,
    surface_collection: SurfaceCollection | None = None,
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
    curves = _curves_from_collection(curve_collection)
    surfaces = _surfaces_from_collection(surface_collection)

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
        section_results=section_results,
        curves=curves,
        surfaces=surfaces,
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


def _curves_from_collection(
    curve_collection: CurveCollection | None,
) -> list[ProjectCurve]:
    if curve_collection is None:
        return []

    for curve in curve_collection.curves:
        ensure_manual_curve_storage(curve)
        refresh_curve_diagnostics(curve)

    return [
        ProjectCurve(
            id=str(curve.id),
            name=str(curve.name),
            section_result_id=str(curve.section_result_id),
            plane_id=str(curve.plane_id),
            original_points=_points_from_value(
                curve.original_points,
                "curve_collection.curve.original_points",
            ),
            fitted_points=_points_from_value(
                curve.fitted_points,
                "curve_collection.curve.fitted_points",
            ),
            mean_error=_float_from_value(
                curve.mean_error,
                "curve_collection.curve.mean_error",
            ),
            max_error=_float_from_value(
                curve.max_error,
                "curve_collection.curve.max_error",
            ),
            is_closed=bool(curve.is_closed),
            visible=bool(curve.visible),
            point_count=int(curve.point_count),
            length=_float_from_value(
                curve.length,
                "curve_collection.curve.length",
            ),
            endpoint_distance=_float_from_value(
                curve.endpoint_distance,
                "curve_collection.curve.endpoint_distance",
            ),
            bounding_box_size=_float_from_value(
                curve.bounding_box_size,
                "curve_collection.curve.bounding_box_size",
            ),
            is_tiny_fragment=bool(curve.is_tiny_fragment),
            source_section_result_id=str(curve.section_result_id),
            source_plane_id=str(curve.plane_id),
            metadata=_metadata_from_value(
                curve.metadata,
                "curve_collection.curve.metadata",
            ),
        )
        for curve in curve_collection.curves
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


def _surfaces_from_collection(
    surface_collection: SurfaceCollection | None,
) -> list[ProjectSurface]:
    if surface_collection is None:
        return []

    return [
        ProjectSurface(
            id=str(surface.id),
            name=str(surface.name),
            source_curve_ids=[
                str(curve_id) for curve_id in surface.source_curve_ids
            ],
            surface_type=str(surface.surface_type),
            visible=bool(surface.visible),
            metadata=_metadata_from_value(
                surface.metadata,
                "surface_collection.surface.metadata",
            ),
        )
        for surface in surface_collection.surfaces
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
