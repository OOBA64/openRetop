"""Build declarative viewport scenes from UI-independent application state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import numpy as np

from openretop.application.scene_ids import (
    NODE_MESH,
    NODE_REGIONS,
    NODE_SECTION_PLANES,
    NODE_SECTION_RESULTS,
    region_node_id,
    section_plane_node_id,
    section_result_node_id,
)
from openretop.sections.section_state import plane_normal, plane_origin
from openretop.viewer.modeling_scene import ModelingSceneInput, modeling_items
from openretop.viewer.scene_types import (
    CameraRequest,
    DisplayStyleSnapshot,
    MeshRenderItem,
    RegionRenderItem,
    SceneSnapshot,
    SectionPlaneRenderItem,
    SectionResultRenderItem,
    SelectionRenderState,
    ToolPreviewState,
    geometry_revision,
)


@dataclass(frozen=True, slots=True)
class SceneBuildOptions:
    show_grid: bool = True
    show_axes: bool = True
    show_axis_gizmo: bool = True
    show_viewcube: bool = True
    show_section_plane: bool = True
    show_normals: bool = False
    hide_expensive_overlays: bool = False
    display_colors: Mapping[str, object] = field(default_factory=dict)
    region_color: object = (0.0, 0.82, 1.0)
    region_edge_color: object = (0.88, 1.0, 1.0)
    region_opacity: float = 0.34


_last_mesh_revision: tuple[object, object, int] | None = None


def _mesh_revision(vertices: object, triangles: object) -> int:
    """The scan's geometry revision, hashed once per vertex/triangle array.

    Hashing a large scan cost ~10 ms on every snapshot (every mouse move of a tool). The
    mesh code replaces these arrays rather than editing them in place (translate and
    restore assign new arrays), so the same array objects mean the same geometry.
    """

    global _last_mesh_revision
    cached = _last_mesh_revision
    if cached is not None and cached[0] is vertices and cached[1] is triangles:
        return cached[2]
    revision = geometry_revision(vertices, triangles)
    _last_mesh_revision = (vertices, triangles, revision)
    return revision


class SceneBuilder:
    """Translate application state and prepared geometry into a snapshot.

    The model (surfaces, bodies, Surface Sketch curves) arrives as ``modeling``, already
    tessellated; the builder only describes prepared geometry.
    """

    def build(
        self,
        state: object,
        *,
        options: SceneBuildOptions | None = None,
        tool_preview: ToolPreviewState | None = None,
        camera_request: CameraRequest | None = None,
        object_origin: object | None = None,
        active_transform_angle_delta: float | None = None,
        modeling: ModelingSceneInput | None = None,
    ) -> SceneSnapshot:
        build_options = options or SceneBuildOptions()
        mesh_object = getattr(state, "mesh_object", None)
        meshes = self._mesh_items(mesh_object, build_options)
        mesh_world_bounds = meshes[0].world_bounds if meshes else None

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
        model_faces, model_edges, scan_overlays = (
            ((), (), ()) if modeling is None else modeling_items(modeling, mesh_object)
        )
        preview = tool_preview or ToolPreviewState()
        selection = SelectionRenderState(
            selected_ids=frozenset(self._selected_ids(state)),
            selected_item=getattr(state, "selected_item", None),
        )
        revision = geometry_revision(
            tuple((item.id, item.revision, item.visible) for item in meshes),
            tuple((item.id, item.revision, item.visible) for item in regions),
            tuple((item.id, item.revision, item.visible) for item in section_planes),
            tuple((item.id, item.revision, item.visible) for item in section_results),
            tuple((item.id, item.revision, item.visible, item.style) for item in model_faces),
            tuple((item.id, item.revision, item.visible, item.style) for item in model_edges),
            tuple((item.id, item.revision, item.visible) for item in scan_overlays),
            preview.revision,
        )
        return SceneSnapshot(
            revision=revision,
            meshes=meshes,
            regions=regions,
            section_planes=section_planes,
            section_results=section_results,
            model_faces=model_faces,
            model_edges=model_edges,
            scan_overlays=scan_overlays,
            tool_preview=preview,
            selection=selection,
            display={
                "show_grid": bool(build_options.show_grid),
                "show_axes": bool(build_options.show_axes),
                "show_axis_gizmo": bool(build_options.show_axis_gizmo),
                "show_viewcube": bool(build_options.show_viewcube),
                "show_normals": bool(build_options.show_normals),
                "show_section_plane": bool(build_options.show_section_plane),
                "display_colors": dict(build_options.display_colors),
            },
            camera_request=camera_request or CameraRequest(),
            object_origin=None if object_origin is None else tuple(np.asarray(object_origin, dtype=float)),
            active_transform_mode=getattr(state, "active_transform_mode", None),
            active_transform_axis=getattr(state, "active_transform_axis", None),
            active_transform_constraint=getattr(
                getattr(state, "transform_state", None),
                "axis_constraint",
                None,
            ),
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
        revision = _mesh_revision(getattr(mesh, "vertices", None), getattr(mesh, "triangles", None))
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
        )
        for collection, attribute in collection_specs:
            selected.update(str(value) for value in getattr(collection, attribute, ()))
        region = getattr(getattr(state, "region_collection", None), "active_region", None)
        if region is not None and bool(getattr(region, "selected", False)):
            selected.add(str(getattr(region, "id", "")))
        return selected


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
