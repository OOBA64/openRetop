"""Build declarative viewport scenes from UI-independent application state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

import numpy as np

from application.scene_ids import (
    NODE_BREP_SURFACES,
    NODE_CURVES,
    NODE_MESH,
    NODE_REGIONS,
    NODE_SECTION_PLANES,
    NODE_SECTION_RESULTS,
    NODE_SURFACES,
    curve_group_node_id,
    curve_node_id,
    region_node_id,
    section_plane_node_id,
    section_result_node_id,
    surface_node_id,
)
from sections.section_state import plane_normal, plane_origin
from viewer.scene_types import (
    CameraRequest,
    CurveRenderItem,
    DisplayStyleSnapshot,
    MeshRenderItem,
    RegionRenderItem,
    SceneSnapshot,
    SectionPlaneRenderItem,
    SectionResultRenderItem,
    SelectionRenderState,
    SurfaceRenderItem,
    ToolPreviewState,
    finite_bounds,
    geometry_revision,
)


@dataclass(frozen=True, slots=True)
class SceneBuildOptions:
    show_grid: bool = True
    show_axes: bool = True
    show_axis_gizmo: bool = True
    show_section_plane: bool = True
    show_normals: bool = False
    hide_expensive_overlays: bool = False
    display_colors: Mapping[str, object] = field(default_factory=dict)
    region_color: object = (0.0, 0.82, 1.0)
    region_edge_color: object = (0.88, 1.0, 1.0)
    region_opacity: float = 0.34


class SceneBuilder:
    """Translate application state and prepared geometry into a snapshot.

    Surface triangulation and manual-curve sampling remain in their existing
    domain services.  The builder only describes already prepared geometry.
    """

    def build(
        self,
        state: object,
        *,
        options: SceneBuildOptions | None = None,
        surface_previews: Sequence[object] = (),
        tool_preview: ToolPreviewState | None = None,
        camera_request: CameraRequest | None = None,
        visible_curves: Sequence[object] | None = None,
        active_surface_id: str | None = None,
        surface_source_curve_ids: Sequence[str] = (),
        object_origin: object | None = None,
        active_transform_angle_delta: float | None = None,
    ) -> SceneSnapshot:
        build_options = options or SceneBuildOptions()
        mesh_object = getattr(state, "mesh_object", None)
        meshes = self._mesh_items(mesh_object, build_options)
        mesh_world_bounds = meshes[0].world_bounds if meshes else None

        curve_records = (
            tuple(visible_curves)
            if visible_curves is not None
            else tuple(getattr(getattr(state, "curve_collection", None), "curves", ()))
        )
        curves = () if build_options.hide_expensive_overlays else self._curve_items(
            curve_records,
            active_curve_id=getattr(
                getattr(state, "curve_collection", None), "active_curve_id", None
            ),
            surface_source_curve_ids=surface_source_curve_ids,
        )
        surfaces = () if build_options.hide_expensive_overlays else self._surface_items(
            surface_previews,
            active_surface_id=active_surface_id,
        )
        regions = () if build_options.hide_expensive_overlays else self._region_items(
            state,
            mesh_object,
            build_options,
        )
        section_planes = self._section_plane_items(
            state,
            build_options,
            mesh_world_bounds,
        )
        section_results = () if build_options.hide_expensive_overlays else self._section_result_items(
            state
        )
        preview = tool_preview or ToolPreviewState()
        selection = SelectionRenderState(
            selected_ids=frozenset(self._selected_ids(state)),
            selected_item=getattr(state, "selected_item", None),
            active_curve_id=getattr(
                getattr(state, "curve_collection", None), "active_curve_id", None
            ),
            active_surface_id=active_surface_id,
            surface_source_curve_ids=tuple(str(value) for value in surface_source_curve_ids),
        )
        revision = geometry_revision(
            tuple((item.id, item.revision, item.visible) for item in meshes),
            tuple((item.id, item.revision, item.visible, item.category) for item in curves),
            tuple((item.id, item.revision, item.visible) for item in surfaces),
            tuple((item.id, item.revision, item.visible) for item in regions),
            tuple((item.id, item.revision, item.visible) for item in section_planes),
            tuple((item.id, item.revision, item.visible) for item in section_results),
            preview.revision,
        )
        return SceneSnapshot(
            revision=revision,
            meshes=meshes,
            curves=curves,
            surfaces=surfaces,
            regions=regions,
            section_planes=section_planes,
            section_results=section_results,
            tool_preview=preview,
            selection=selection,
            display={
                "show_grid": bool(build_options.show_grid),
                "show_axes": bool(build_options.show_axes),
                "show_axis_gizmo": bool(build_options.show_axis_gizmo),
                "show_normals": bool(build_options.show_normals),
                "show_section_plane": bool(build_options.show_section_plane),
                "display_colors": dict(build_options.display_colors),
            },
            camera_request=camera_request or CameraRequest(),
            object_origin=None if object_origin is None else tuple(np.asarray(object_origin, dtype=float)),
            active_transform_mode=getattr(state, "active_transform_mode", None),
            active_transform_axis=getattr(state, "active_transform_axis", None),
            active_transform_angle_delta=active_transform_angle_delta,
        )

    @staticmethod
    def _mesh_items(mesh_object: object | None, options: SceneBuildOptions) -> tuple[MeshRenderItem, ...]:
        if mesh_object is None:
            return ()
        mesh = getattr(mesh_object, "display_mesh", None)
        if mesh is None:
            return ()
        transform = getattr(mesh_object, "transform_matrix", None)
        if transform is None:
            transform = np.identity(4, dtype=float)
        local_minimum = getattr(mesh_object, "source_bounds_min", None)
        local_maximum = getattr(mesh_object, "source_bounds_max", None)
        local_bounds = None
        if local_minimum is not None and local_maximum is not None:
            minimum = tuple(float(value) for value in np.asarray(local_minimum, dtype=float).reshape(3))
            maximum = tuple(float(value) for value in np.asarray(local_maximum, dtype=float).reshape(3))
            local_bounds = (minimum, maximum)
        revision = geometry_revision(
            getattr(mesh, "vertices", None),
            getattr(mesh, "triangles", None),
        )
        colors = options.display_colors
        return (
            MeshRenderItem(
                id="mesh",
                revision=revision,
                mesh=mesh,
                transform=np.asarray(transform, dtype=float).reshape((4, 4)),
                visible=bool(getattr(mesh_object, "visible", True)),
                selected=False,
                style=DisplayStyleSnapshot(
                    color=_color(colors.get("mesh_color"), (0.72, 0.74, 0.78))
                ),
                local_bounds=local_bounds,
                selection_keys=(NODE_MESH,),
            ),
        )

    @staticmethod
    def _curve_items(
        curves: Sequence[object],
        *,
        active_curve_id: str | None,
        surface_source_curve_ids: Sequence[str],
    ) -> tuple[CurveRenderItem, ...]:
        source_ids = {str(value) for value in surface_source_curve_ids}
        items: list[CurveRenderItem] = []
        for curve in curves:
            points = np.asarray(getattr(curve, "fitted_points", ()), dtype=float)
            if points.ndim != 2 or points.shape[1:] != (3,):
                points = np.zeros((0, 3), dtype=float)
            curve_id = str(getattr(curve, "id", f"curve-{len(items)}"))
            metadata = dict(getattr(curve, "metadata", {}) or {})
            selected = bool(getattr(curve, "selected", False))
            active = active_curve_id is not None and curve_id == str(active_curve_id)
            category = _curve_category(
                curve,
                metadata,
                selected=selected,
                active=active,
                surface_source=curve_id in source_ids,
            )
            group_id = str(getattr(curve, "section_result_id", "") or "")
            selection_keys = [curve_node_id(curve_id), NODE_CURVES]
            if group_id:
                selection_keys.append(curve_group_node_id(group_id))
            items.append(
                CurveRenderItem(
                    id=curve_id,
                    revision=geometry_revision(points, bool(getattr(curve, "is_closed", False))),
                    points=points,
                    visible=bool(getattr(curve, "visible", True)),
                    closed=bool(getattr(curve, "is_closed", False)),
                    category=category,
                    selected=selected,
                    active=active,
                    metadata=metadata,
                    selection_keys=tuple(selection_keys),
                )
            )
        return tuple(items)

    @staticmethod
    def _surface_items(
        previews: Sequence[object],
        *,
        active_surface_id: str | None,
    ) -> tuple[SurfaceRenderItem, ...]:
        items: list[SurfaceRenderItem] = []
        for preview in previews:
            vertices = np.asarray(getattr(preview, "vertices", ()), dtype=float).reshape((-1, 3))
            faces = np.asarray(getattr(preview, "faces", ()), dtype=int).reshape((-1, 3))
            surface_id = str(getattr(preview, "source_surface_id", f"surface-{len(items)}"))
            selected = bool(getattr(preview, "selected", False))
            active = active_surface_id is not None and surface_id == str(active_surface_id)
            role = str(getattr(preview, "display_role", "preview_surface"))
            opacity = getattr(preview, "opacity", None)
            if opacity is None:
                opacity = 0.58 if selected or active else 0.22
            family_key = NODE_BREP_SURFACES if role == "brep_visual_preview" else NODE_SURFACES
            handles = np.asarray(
                getattr(preview, "overbuild_handle_points", ()), dtype=float
            ).reshape((-1, 3))
            items.append(
                SurfaceRenderItem(
                    id=surface_id,
                    revision=geometry_revision(vertices, faces, handles),
                    vertices=vertices,
                    faces=faces,
                    selected=selected,
                    active=active,
                    display_role=role,
                    wireframe_overlay=bool(getattr(preview, "wireframe_overlay", False)),
                    overbuild_handle_points=handles,
                    show_overbuild_handles=bool(
                        getattr(preview, "show_overbuild_handles", False)
                    ),
                    style=DisplayStyleSnapshot(opacity=float(opacity)),
                    selection_keys=(surface_node_id(surface_id), family_key),
                )
            )
        return tuple(items)

    @staticmethod
    def _region_items(
        state: object,
        mesh_object: object | None,
        options: SceneBuildOptions,
    ) -> tuple[RegionRenderItem, ...]:
        region = getattr(getattr(state, "region_collection", None), "active_region", None)
        if region is None or mesh_object is None:
            return ()
        mesh = getattr(mesh_object, "display_mesh", None)
        if mesh is None:
            return ()
        transform = getattr(mesh_object, "transform_matrix", None)
        if transform is None:
            transform = np.identity(4, dtype=float)
        region_id = str(getattr(region, "id", "region"))
        triangle_indices = tuple(int(value) for value in getattr(region, "triangle_indices", ()))
        return (
            RegionRenderItem(
                id=region_id,
                revision=geometry_revision(triangle_indices, getattr(mesh, "triangles", None)),
                mesh=mesh,
                triangle_indices=triangle_indices,
                transform=np.asarray(transform, dtype=float).reshape((4, 4)),
                visible=bool(getattr(region, "visible", True)),
                selected=bool(getattr(region, "selected", False)),
                style=DisplayStyleSnapshot(
                    color=_color(options.region_color, (0.0, 0.82, 1.0)),
                    edge_color=_color(options.region_edge_color, (0.88, 1.0, 1.0)),
                    opacity=float(options.region_opacity),
                    edge_visibility=True,
                ),
                selection_keys=(region_node_id(region_id), NODE_REGIONS),
            ),
        )

    @staticmethod
    def _section_plane_items(
        state: object,
        options: SceneBuildOptions,
        mesh_bounds: object | None,
    ) -> tuple[SectionPlaneRenderItem, ...]:
        collection = getattr(state, "section_collection", None)
        planes = tuple(getattr(collection, "planes", ()))
        if not planes:
            return ()
        items = []
        for plane in planes:
            plane_id = str(getattr(plane, "id", f"plane-{len(items)}"))
            origin = plane_origin(plane)
            normal = plane_normal(plane)
            frame_bounds = _plane_frame_bounds(mesh_bounds, origin)
            items.append(
                SectionPlaneRenderItem(
                    id=plane_id,
                    revision=geometry_revision(origin, normal, frame_bounds),
                    origin=tuple(origin),
                    normal=tuple(normal),
                    axis=str(getattr(plane, "axis", "Z")),
                    offset=float(getattr(plane, "offset", 0.0)),
                    visible=bool(options.show_section_plane and getattr(plane, "visible", True)),
                    selected=bool(getattr(plane, "selected", False)),
                    frame_bounds=frame_bounds,
                    selection_keys=(section_plane_node_id(plane_id), NODE_SECTION_PLANES),
                )
            )
        return tuple(items)

    @staticmethod
    def _section_result_items(state: object) -> tuple[SectionResultRenderItem, ...]:
        result = getattr(state, "section_result", None)
        if result is None:
            return ()
        collection = getattr(state, "section_collection", None)
        active_id = getattr(collection, "active_result_id", None) or "display"
        polylines = tuple(
            np.asarray(getattr(line, "points", ()), dtype=float).reshape((-1, 3))
            for line in getattr(result, "polylines", ())
        )
        return (
            SectionResultRenderItem(
                id=str(active_id),
                revision=geometry_revision(*polylines),
                polylines=polylines,
                selection_keys=(section_result_node_id(active_id), NODE_SECTION_RESULTS),
            ),
        )

    @staticmethod
    def _selected_ids(state: object) -> set[str]:
        selected: set[str] = set()
        mesh_object = getattr(state, "mesh_object", None)
        if mesh_object is not None and getattr(state, "selected_item", None) == "model":
            selected.add(NODE_MESH)
        collection_specs = (
            (getattr(state, "section_collection", None), "selected_plane_ids"),
            (getattr(state, "section_collection", None), "selected_result_ids"),
            (getattr(state, "curve_collection", None), "selected_curve_ids"),
            (getattr(state, "surface_collection", None), "selected_surface_ids"),
            (getattr(state, "brep_surface_collection", None), "selected_surface_ids"),
        )
        for collection, attribute in collection_specs:
            selected.update(str(value) for value in getattr(collection, attribute, ()))
        region = getattr(getattr(state, "region_collection", None), "active_region", None)
        if region is not None and bool(getattr(region, "selected", False)):
            selected.add(str(getattr(region, "id", "")))
        return selected


def _curve_category(
    curve: object,
    metadata: Mapping[str, object],
    *,
    selected: bool,
    active: bool,
    surface_source: bool,
) -> str:
    creation_type = str(metadata.get("creation_type", "")).strip().lower()
    snap_mode = str(metadata.get("snap_mode", "")).strip().lower()
    category = (
        "manual"
        if creation_type in {"manual", "curve_on_mesh"}
        or snap_mode == "mesh"
        or "control_points" in metadata
        or metadata.get("snap_to_mesh") is True
        else "normal"
    )
    if bool(getattr(curve, "is_tiny_fragment", False)):
        category = "tiny"
    if any(key in metadata for key in ("repair_type", "curve_repair", "repair_operation")):
        category = "repaired"
    if surface_source:
        category = "active_surface_source"
    if selected:
        category = "selected"
    if active:
        category = "active"
    return category


def _plane_frame_bounds(mesh_bounds: object | None, origin: object):
    if mesh_bounds is None:
        return None
    minimum = np.asarray(mesh_bounds[0], dtype=float)
    maximum = np.asarray(mesh_bounds[1], dtype=float)
    extent = max(float(np.max(maximum - minimum)), 1e-6) * 0.6
    center = np.asarray(origin, dtype=float).reshape(3)
    return (
        tuple(float(value) for value in center - extent),
        tuple(float(value) for value in center + extent),
    )


def _color(value: object, fallback: tuple[float, float, float]) -> tuple[float, float, float]:
    if isinstance(value, str) and len(value) == 7 and value.startswith("#"):
        try:
            return tuple(int(value[index : index + 2], 16) / 255.0 for index in (1, 3, 5))
        except ValueError:
            return fallback
    try:
        array = np.asarray(value, dtype=float).reshape(3)
    except (TypeError, ValueError):
        return fallback
    if not np.all(np.isfinite(array)):
        return fallback
    return tuple(float(component) for component in np.clip(array, 0.0, 1.0))


__all__ = ("SceneBuildOptions", "SceneBuilder")
